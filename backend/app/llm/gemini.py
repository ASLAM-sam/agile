"""Google Gemini client wrapper.

A second implementation of `LLMProvider`, selected by `LLM_PROVIDER=gemini`.
It exists so the platform can run on Gemini's free tier, and it satisfies the
same contract the agent layer already depends on — no agent, adapter or
workflow code changes when the provider does.

Differences from the Anthropic client, all deliberate:

* **Schema enforcement** uses `response_json_schema`, which accepts standard
  JSON Schema. Every construct `llm/schema.py` emits — `type`, `properties`,
  `required`, `additionalProperties`, `enum`, `items`, `description` — is on
  Gemini's supported list, so schemas transfer unchanged.
* **Thinking** is left on automatic. Effort is an Anthropic control; Gemini
  sizes its own budget, and passing a hand-picked token budget is the main way
  to earn a 400 from a model whose allowed range differs.
* **Prompt caching** is not attempted. Gemini's explicit cache is a separate
  resource with a large minimum token count that agent prompts do not reach.

Streaming is used unconditionally for the same reason as the Anthropic client:
code-generation batches request tens of thousands of output tokens, and a
single non-streamed request at that size hits HTTP timeouts.
"""

from __future__ import annotations

import asyncio
import json
import random
from typing import Any

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from app.core.config import settings
from app.core.exceptions import AegisError, ConfigurationError, LLMError
from app.core.logging import get_logger
from app.llm.types import Completion, PromptBundle, TextCompletion, TokenUsage

logger = get_logger(__name__)

#: Transport-level failures worth another attempt.
_RETRYABLE_TRANSPORT = (
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.ConnectTimeout,
    httpx.RemoteProtocolError,
)

#: Finish reasons that mean the model refused rather than failed.
_REFUSAL_REASONS = frozenset(
    {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION", "IMAGE_SAFETY"}
)


class GeminiClient:
    """Async wrapper around the Gemini `generateContent` API."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        max_retries: int | None = None,
    ) -> None:
        key = api_key or settings.google_api_key
        if not key:
            raise ConfigurationError(
                "GOOGLE_API_KEY is not configured, but LLM_PROVIDER is set to "
                "'gemini'. Create a key at https://aistudio.google.com/apikey "
                "and set it in backend/.env before starting a generation run."
            )
        self._client = genai.Client(
            api_key=key,
            http_options=genai_types.HttpOptions(
                # The SDK expects milliseconds.
                timeout=int(settings.llm_timeout_seconds * 1000),
            ),
        )
        self._model = model or settings.gemini_model
        self._max_retries = max_retries if max_retries is not None else settings.llm_max_retries

    @property
    def model(self) -> str:
        return self._model

    async def complete_structured(self, prompt: PromptBundle) -> Completion:
        """Run a completion constrained to `prompt.schema`."""
        if prompt.schema is None:
            raise ValueError("complete_structured requires a schema on the PromptBundle.")

        result = await self._send(
            prompt,
            response_mime_type="application/json",
            response_json_schema=prompt.schema,
        )

        if result.finish_reason == "MAX_TOKENS":
            raise LLMError(
                "Model output was truncated before the response could be completed. "
                "Reduce the requested batch size or raise llm_max_tokens.",
                details={"stop_reason": "max_tokens", "chars": len(result.text)},
            )
        self._guard_refusal(result)

        text = result.text.strip()
        if not text:
            raise LLMError(
                "The model returned an empty response where structured output was required.",
                details={"finish_reason": result.finish_reason, **prompt.metadata},
            )

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError(
                f"Model returned output that was not valid JSON: {exc}",
                details={"preview": text[:500]},
            ) from exc

        if not isinstance(data, dict):
            raise LLMError("Structured output must be a JSON object.")

        return Completion(
            data=data,
            usage=result.usage,
            stop_reason=result.finish_reason,
            model=result.model,
            raw_text=text,
        )

    async def complete_text(self, prompt: PromptBundle) -> TextCompletion:
        """Run a free-form completion returning plain text."""
        result = await self._send(prompt)
        self._guard_refusal(result)
        return TextCompletion(
            text=result.text,
            usage=result.usage,
            stop_reason=result.finish_reason,
            model=result.model,
        )

    async def aclose(self) -> None:
        """Release the underlying transport.

        Mirrors `LLMClient.aclose` so callers need no provider-specific
        branching. The SDK manages its own connection pool and exposes no
        async close, so there is nothing to await.
        """
        return None

    # --- internals -------------------------------------------------------

    @staticmethod
    def _guard_refusal(result: _Result) -> None:
        if result.finish_reason in _REFUSAL_REASONS:
            raise LLMError(
                "The model declined this request.",
                details={"finish_reason": result.finish_reason},
            )

    def _build_config(
        self,
        prompt: PromptBundle,
        *,
        response_mime_type: str | None,
        response_json_schema: dict[str, Any] | None,
    ) -> genai_types.GenerateContentConfig:
        """Assemble the request configuration.

        Both system segments are concatenated. Gemini has no cache-control
        marker, so the split that matters to Anthropic is irrelevant here — but
        the stable prefix is still placed first, which is the ordering the
        provider's implicit caching rewards.
        """
        system = prompt.cacheable_system
        if prompt.volatile_system:
            system = f"{system}\n\n{prompt.volatile_system}"

        return genai_types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=prompt.max_tokens or settings.llm_max_tokens,
            response_mime_type=response_mime_type,
            response_json_schema=response_json_schema,
            # -1 is "decide for me". A hand-picked budget is model-dependent and
            # a wrong value is rejected outright.
            thinking_config=genai_types.ThinkingConfig(thinking_budget=-1),
        )

    async def _send(
        self,
        prompt: PromptBundle,
        *,
        response_mime_type: str | None = None,
        response_json_schema: dict[str, Any] | None = None,
    ) -> _Result:
        """Issue the request with retry and backoff."""
        config = self._build_config(
            prompt,
            response_mime_type=response_mime_type,
            response_json_schema=response_json_schema,
        )

        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                result = await self._stream_once(prompt, config)
                logger.debug(
                    "llm_completion",
                    extra={
                        "provider": "gemini",
                        "model": result.model,
                        "finish_reason": result.finish_reason,
                        "output_tokens": result.usage.output_tokens,
                        "attempt": attempt + 1,
                        **prompt.metadata,
                    },
                )
                return result

            except genai_errors.APIError as exc:
                if not self._is_retryable(exc):
                    raise self._translate(exc, prompt) from exc
                last_error = exc
            except _RETRYABLE_TRANSPORT as exc:
                last_error = exc

            if attempt >= self._max_retries:
                break
            delay = min(2.0**attempt + random.uniform(0, 1), 30.0)
            logger.warning(
                "llm_retry",
                extra={
                    "provider": "gemini",
                    "attempt": attempt + 1,
                    "delay_seconds": round(delay, 2),
                    "error": type(last_error).__name__,
                    **prompt.metadata,
                },
            )
            await asyncio.sleep(delay)

        # Chained deliberately: the provider manager classifies a failure by
        # walking `__cause__`, and a 429 buried here must still be recognised
        # as an exhausted quota rather than as a generic timeout.
        raise LLMError(
            f"Model provider unavailable after {self._max_retries + 1} attempts: {last_error}",
            details=prompt.metadata,
        ) from last_error

    async def _stream_once(
        self, prompt: PromptBundle, config: genai_types.GenerateContentConfig
    ) -> _Result:
        """Consume one streamed response into a complete result."""
        chunks: list[str] = []
        usage = TokenUsage()
        finish_reason = ""
        model_version = self._model

        stream = await self._client.aio.models.generate_content_stream(
            model=self._model,
            contents=prompt.user_message,
            config=config,
        )
        async for chunk in stream:
            text = getattr(chunk, "text", None)
            if text:
                chunks.append(text)
            if chunk.model_version:
                model_version = chunk.model_version
            # Usage is cumulative and repeated on each chunk; the last one wins.
            if chunk.usage_metadata is not None:
                usage = self._usage(chunk.usage_metadata)
            for candidate in chunk.candidates or ():
                if candidate.finish_reason is not None:
                    finish_reason = str(getattr(candidate.finish_reason, "name", ""))

        return _Result(
            text="".join(chunks),
            usage=usage,
            finish_reason=finish_reason,
            model=model_version,
        )

    @staticmethod
    def _usage(metadata: genai_types.GenerateContentResponseUsageMetadata) -> TokenUsage:
        """Map Gemini's accounting onto the platform's shape.

        Thinking tokens are billed as output but reported separately, so they
        are folded in — otherwise a reasoning-heavy run looks far cheaper than
        it was.
        """
        return TokenUsage(
            input_tokens=metadata.prompt_token_count or 0,
            output_tokens=(metadata.candidates_token_count or 0)
            + (metadata.thoughts_token_count or 0),
            cache_read_tokens=metadata.cached_content_token_count or 0,
        )

    @staticmethod
    def _is_retryable(exc: genai_errors.APIError) -> bool:
        """Whether another attempt could plausibly succeed.

        429 is included because the free tier enforces per-minute limits that
        clear on their own. A daily quota does not, but it is not distinguished
        here — the backoff costs one wasted minute and the message that
        eventually surfaces says which it was.
        """
        code = getattr(exc, "code", None)
        return code == 429 or (isinstance(code, int) and 500 <= code < 600)

    @staticmethod
    def _provider_message(exc: genai_errors.APIError) -> str:
        """The provider's human-readable message, without the JSON envelope."""
        payload = getattr(exc, "details", None)
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                message = error.get("message")
                if isinstance(message, str) and message.strip():
                    return message.strip()
        message = getattr(exc, "message", None)
        if isinstance(message, str) and message.strip():
            return message.strip()
        return str(exc)

    def _translate(self, exc: genai_errors.APIError, prompt: PromptBundle) -> AegisError:
        """Turn a provider error into the one that describes the real problem."""
        message = self._provider_message(exc)
        lowered = message.lower()
        code = getattr(exc, "code", None)

        if code in (401, 403) or "api key not valid" in lowered:
            return ConfigurationError(
                f"The configured GOOGLE_API_KEY was rejected: {message} "
                "Create a fresh key at https://aistudio.google.com/apikey."
            )
        if code == 429:
            return ConfigurationError(
                f"Gemini quota exhausted: {message} The free tier limits requests per "
                "minute and per day; wait for the window to reset, or reduce "
                "GENERATION_BATCH_SIZE and MAX_CONCURRENT_RUNS."
            )
        if code == 404 and "model" in lowered:
            return ConfigurationError(
                f"The configured GEMINI_MODEL ({self._model}) is not available to this "
                f"key: {message}"
            )
        return LLMError(
            f"The model provider rejected the request: {message}",
            details=prompt.metadata,
        )


class _Result:
    """One assembled completion, provider types kept out of the agent layer."""

    __slots__ = ("finish_reason", "model", "text", "usage")

    def __init__(self, *, text: str, usage: TokenUsage, finish_reason: str, model: str) -> None:
        self.text = text
        self.usage = usage
        self.finish_reason = finish_reason
        self.model = model
