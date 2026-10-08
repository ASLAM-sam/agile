"""One adapter for every OpenAI-compatible endpoint.

Groq, OpenAI and Ollama all expose the same `/chat/completions` contract, so
they are one implementation with three configurations rather than three
near-identical modules. That is what makes "add a provider" a config change:
any future vendor speaking this protocol needs a registry entry and nothing
else.

`httpx` is used directly instead of the vendor SDKs. It is already a
dependency, it is the same client for all three, and it keeps error handling
at the HTTP status level — which is where the distinction between "retry" and
"fail over" actually lives.

Structured output degrades in three steps, because support is uneven:

1. `json_schema` — the server enforces the shape (OpenAI, newer Groq models).
2. `json_object` — the server guarantees valid JSON; the schema goes in the
   prompt and the response is validated here.
3. Neither — the schema goes in the prompt, JSON is extracted from the reply
   and validated here.

A response that fails validation is reported as a provider failure, so the
manager fails over instead of handing a malformed object to an agent.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.enums import ErrorKind
from app.core.exceptions import LLMError
from app.core.logging import get_logger
from app.llm.errors import tag
from app.llm.providers.base import ProviderAdapter, ProviderSpec
from app.llm.types import Completion, PromptBundle, TextCompletion, TokenUsage
from app.llm.validation import describe_schema, normalize_unknown_fields, validate

logger = get_logger(__name__)


class OpenAICompatibleAdapter(ProviderAdapter):
    """Any vendor speaking the OpenAI chat-completions protocol."""

    def __init__(
        self,
        spec: ProviderSpec,
        *,
        base_url: str,
        api_key: str | None,
        timeout_seconds: float,
        supports_json_schema: bool = False,
        supports_json_object: bool = True,
        requires_api_key: bool = True,
    ) -> None:
        super().__init__(spec)
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._supports_json_schema = supports_json_schema
        self._supports_json_object = supports_json_object
        self._requires_api_key = requires_api_key
        self._client: httpx.AsyncClient | None = None

    @property
    def is_configured(self) -> bool:
        # Ollama runs locally and authenticates nothing, so a key requirement
        # would make a working provider look broken.
        return bool(self._api_key) or not self._requires_api_key

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {"Content-Type": "application/json"}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers=headers,
                timeout=self._timeout,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # --- completions -----------------------------------------------------

    async def complete_text(
        self, prompt: PromptBundle, *, model: str | None = None
    ) -> TextCompletion:
        text, usage, finish, resolved_model = await self._chat(prompt, schema=None, model=model)
        return TextCompletion(text=text, usage=usage, stop_reason=finish, model=resolved_model)

    async def complete_structured(
        self, prompt: PromptBundle, *, model: str | None = None
    ) -> Completion:
        if prompt.schema is None:
            raise ValueError("complete_structured requires a schema on the PromptBundle.")

        text, usage, finish, resolved_model = await self._chat(
            prompt, schema=prompt.schema, model=model
        )

        if finish == "length":
            raise tag(
                LLMError(
                    "Model output was truncated before the response could be completed. "
                    "Reduce the requested batch size or raise llm_max_tokens.",
                    details={"stop_reason": "length", "provider": self.key},
                ),
                ErrorKind.RETRYABLE,
            )

        payload = _extract_json_object(text)
        if payload is None:
            raise tag(
                LLMError(
                    f"{self.display_name} returned output that was not a JSON object.",
                    details={"preview": text[:500], "provider": self.key},
                ),
                # Another provider may well produce clean JSON for this prompt.
                ErrorKind.UNAVAILABLE,
            )

        # OpenAI-compatible providers can return valid JSON with harmless
        # extras even when asked for a strict schema.  Normalize only those
        # extras at this provider boundary; the unchanged application schema
        # still decides whether the resulting payload is usable.
        payload = normalize_unknown_fields(payload, prompt.schema)
        problems = validate(payload, prompt.schema)
        if problems:
            raise tag(
                LLMError(
                    f"{self.display_name} returned JSON that does not match the required "
                    f"schema: {'; '.join(problems[:5])}",
                    details={"problems": problems[:20], "provider": self.key},
                ),
                ErrorKind.UNAVAILABLE,
            )

        return Completion(
            data=payload,
            usage=usage,
            stop_reason=finish,
            model=resolved_model,
            raw_text=text,
        )

    # --- transport -------------------------------------------------------

    async def _chat(
        self,
        prompt: PromptBundle,
        *,
        schema: dict[str, Any] | None,
        model: str | None = None,
    ) -> tuple[str, TokenUsage, str, str]:
        system = prompt.cacheable_system
        if prompt.volatile_system:
            system = f"{system}\n\n{prompt.volatile_system}"

        # Providers that bill input and output against one per-minute budget
        # reject a large `max_tokens` even when the prompt is small, so the
        # request is clamped to what this provider actually allows.
        requested_output = prompt.max_tokens or 8192
        if self.spec.max_output_tokens:
            requested_output = min(requested_output, self.spec.max_output_tokens)

        effective_model = model or self.model
        body: dict[str, Any] = {
            "model": effective_model,
            "max_tokens": requested_output,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt.user_message},
            ],
        }

        if schema is not None:
            if self._supports_json_schema:
                body["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {"name": "aegis_output", "schema": schema, "strict": True},
                }
            else:
                if self._supports_json_object:
                    body["response_format"] = {"type": "json_object"}
                body["messages"][0]["content"] = f"{system}\n\n{describe_schema(schema)}"

        try:
            response = await self._http().post("/chat/completions", json=body)
        except httpx.TimeoutException as exc:
            raise tag(
                LLMError(f"{self.display_name} timed out.", details={"provider": self.key}),
                ErrorKind.RETRYABLE,
            ) from exc
        except httpx.HTTPError as exc:
            raise tag(
                LLMError(
                    f"{self.display_name} could not be reached: {exc}",
                    details={"provider": self.key},
                ),
                ErrorKind.RETRYABLE,
            ) from exc

        if response.status_code >= 400:
            raise self._error_for(response)

        return self._parse(response.json())

    def _parse(self, data: dict[str, Any]) -> tuple[str, TokenUsage, str, str]:
        choices = data.get("choices") or []
        if not choices:
            raise tag(
                LLMError(
                    f"{self.display_name} returned no choices.",
                    details={"provider": self.key},
                ),
                ErrorKind.UNAVAILABLE,
            )
        choice = choices[0]
        text = (choice.get("message") or {}).get("content") or ""
        finish = choice.get("finish_reason") or ""

        raw_usage = data.get("usage") or {}
        usage = TokenUsage(
            input_tokens=int(raw_usage.get("prompt_tokens") or 0),
            output_tokens=int(raw_usage.get("completion_tokens") or 0),
            cache_read_tokens=int(
                (raw_usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
            ),
        )
        return text, usage, finish, str(data.get("model") or self.model)

    def _error_for(self, response: httpx.Response) -> LLMError:
        """Turn an HTTP failure into a classified platform error."""
        message = _message_from(response)
        status = response.status_code

        if status == 429:
            kind = ErrorKind.QUOTA
            text = f"{self.display_name} rate limit or quota reached: {message}"
        elif status in (401, 403):
            kind = ErrorKind.AUTH
            text = f"{self.display_name} rejected the credentials: {message}"
        elif status == 404:
            kind = ErrorKind.UNAVAILABLE
            text = f"{self.display_name} has no model {self.model!r}: {message}"
        elif status == 413 or _is_capacity_message(message):
            # The prompt does not fit this provider's per-request or
            # per-minute token budget. That is a fact about the provider, not
            # about the request: a model with a larger window answers it fine,
            # so hand it on rather than failing the run.
            kind = ErrorKind.UNAVAILABLE
            text = f"{self.display_name} cannot fit this request: {message}"
        elif status >= 500:
            kind = ErrorKind.RETRYABLE
            text = f"{self.display_name} is unavailable ({status}): {message}"
        else:
            kind = ErrorKind.FATAL
            text = f"{self.display_name} rejected the request ({status}): {message}"

        return tag(LLMError(text, details={"provider": self.key, "status": status}), kind)

    def classify(self, error: BaseException) -> ErrorKind:
        """Errors are tagged where they are raised, so read the tag."""
        from app.llm.errors import kind_of

        return kind_of(error)


#: Phrases vendors use when a prompt exceeds a context window or token budget.
#: Matched only as a *fallback* for vendors that return 400 instead of 413 —
#: the status code is checked first, because message wording is not a contract.
_CAPACITY_MARKERS = (
    "too large",
    "context length",
    "context_length",
    "maximum context",
    "reduce your message",
    "tokens per minute",
    "request too large",
)


def _is_capacity_message(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in _CAPACITY_MARKERS)


def _message_from(response: httpx.Response) -> str:
    """The vendor's human-readable message, without the JSON envelope."""
    try:
        payload = response.json()
    except ValueError:
        return response.text[:300].strip() or response.reason_phrase
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return error["message"].strip()
        if isinstance(error, str):
            return error.strip()
        if isinstance(payload.get("message"), str):
            return payload["message"].strip()
        # NVIDIA NIM answers with a problem-details envelope
        # ({"status": 401, "title": "Unauthorized", "detail": "..."}) rather
        # than OpenAI's {"error": {...}}. Without this the reason reaching the
        # dashboard would be the repr of a dict.
        if isinstance(payload.get("detail"), str):
            return payload["detail"].strip()
    return str(payload)[:300]


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """Parse a JSON object out of a reply, tolerating a markdown fence.

    Models told to emit bare JSON sometimes wrap it in ```json anyway. Fixing
    that here is cheaper than failing over for a formatting habit.
    """
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.split("\n", 1)[-1] if "\n" in candidate else ""
        if candidate.rstrip().endswith("```"):
            candidate = candidate.rstrip()[: -len("```")]
    candidate = candidate.strip()

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            parsed = json.loads(candidate[start : end + 1])
        except json.JSONDecodeError:
            return None

    return parsed if isinstance(parsed, dict) else None
