"""Groq client wrapper.

Groq uses an OpenAI-compatible API endpoint (https://api.groq.com/openai/v1), so this
client uses the openai library rather than a vendor-specific SDK.

Assigned to:
  - Manager
  - Business Analyst
  - Solution Architect
  - Documentation Engineer

Supports:
  - Structured JSON output via response_format with JSON Schema (strict mode) or json_object
  - Plain text completion
  - Usage tracking
  - Retry on transient errors (same provider, no cross-role failover)
  - Timeout handling
  - Error classification (quota, auth, unavailable, fatal)
"""

from __future__ import annotations

import asyncio
import copy
import json
import random
from typing import Any

import httpx

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

#: HTTP status codes that signal a transient server problem.
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


def _sanitize_schema_for_groq(schema: dict[str, Any]) -> dict[str, Any]:
    """Recursively ensure strict JSON schema compatibility for Groq.

    Groq's strict schema validator requires `additionalProperties: False` on all
    object definitions.
    """
    clean = copy.deepcopy(schema)

    def _patch(node: Any) -> None:
        if isinstance(node, dict):
            if (node.get("type") == "object" or "properties" in node) and (
                "additionalProperties" not in node
            ):
                node["additionalProperties"] = False
            for val in node.values():
                _patch(val)
        elif isinstance(node, list):
            for item in node:
                _patch(item)

    _patch(clean)
    return clean


class GroqClient:
    """Async wrapper around the Groq Cloud API (OpenAI-compatible).

    Uses openai.AsyncOpenAI pointed at https://api.groq.com/openai/v1.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "openai/gpt-oss-120b",
        base_url: str = "https://api.groq.com/openai/v1",
        max_retries: int = 3,
        timeout_seconds: float = 900.0,
    ) -> None:
        if not api_key:
            raise ConfigurationError(
                "GROQ_API_KEY is not configured. "
                "Get a key at https://console.groq.com/ and set GROQ_API_KEY in your .env file."
            )
        try:
            import openai  # noqa: PLC0415 - deferred import
        except ImportError as exc:
            raise ConfigurationError(
                "The 'openai' package is required for the Groq provider. "
                "Run: pip install openai"
            ) from exc

        self._client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
            max_retries=0,  # retries are handled by this class
        )
        self._model = model
        self._max_retries = max_retries

    @property
    def model(self) -> str:
        return self._model

    async def complete_structured(self, prompt: PromptBundle) -> Completion:
        """Run a completion constrained to `prompt.schema`."""
        if prompt.schema is None:
            raise ValueError("complete_structured requires a schema on the PromptBundle.")

        messages = self._build_messages(prompt)
        sanitized_schema = _sanitize_schema_for_groq(prompt.schema)
        response_format = self._build_json_schema_format(sanitized_schema)

        try:
            raw = await self._send(
                messages,
                response_format=response_format,
                max_tokens=prompt.max_tokens or 32000,
                metadata=prompt.metadata,
            )
        except AegisError as exc:
            # If Groq rejects strict json_schema, fallback to json_object mode
            if "invalid json schema" in str(exc).lower() or "schema" in str(exc).lower():
                logger.warning("groq_json_schema_fallback", extra={"error": str(exc)})
                fallback_messages = list(messages)
                schema_json = json.dumps(prompt.schema)
                schema_hint = (
                    "\n\nRespond with a valid JSON object matching this schema:\n"
                    f"{schema_json}"
                )
                fallback_messages[-1]["content"] += schema_hint
                raw = await self._send(
                    fallback_messages,
                    response_format={"type": "json_object"},
                    max_tokens=prompt.max_tokens or 32000,
                    metadata=prompt.metadata,
                )
            else:
                raise

        text = (raw.choices[0].message.content or "").strip()
        if not text:
            raise LLMError(
                "Groq returned an empty response where structured output was required.",
                details=prompt.metadata,
            )

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError(
                f"Groq returned output that was not valid JSON: {exc}",
                details={"preview": text[:500]},
            ) from exc

        if not isinstance(data, dict):
            raise LLMError("Structured output must be a JSON object.")

        usage = self._extract_usage(raw)
        return Completion(
            data=data,
            usage=usage,
            stop_reason=raw.choices[0].finish_reason,
            model=raw.model,
            raw_text=text,
        )

    async def complete_text(self, prompt: PromptBundle) -> TextCompletion:
        """Run a free-form completion returning plain text."""
        messages = self._build_messages(prompt)
        raw = await self._send(
            messages,
            response_format=None,
            max_tokens=prompt.max_tokens or 32000,
            metadata=prompt.metadata,
        )
        text = raw.choices[0].message.content or ""
        usage = self._extract_usage(raw)
        return TextCompletion(
            text=text,
            usage=usage,
            stop_reason=raw.choices[0].finish_reason,
            model=raw.model,
        )

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.close()

    # --- internals -------------------------------------------------------

    @staticmethod
    def _build_messages(prompt: PromptBundle) -> list[dict[str, str]]:
        """Convert PromptBundle to OpenAI message format."""
        messages: list[dict[str, str]] = []
        system_parts = [part for part in [
            prompt.cacheable_system,
            prompt.volatile_system,
        ] if part]
        if system_parts:
            messages.append({"role": "system", "content": "\n\n".join(system_parts)})
        if prompt.user_message:
            messages.append({"role": "user", "content": prompt.user_message})
        return messages

    @staticmethod
    def _build_json_schema_format(schema: dict[str, Any]) -> dict[str, Any]:
        """Build the response_format dict for JSON Schema output."""
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "response",
                "strict": True,
                "schema": schema,
            },
        }

    async def _send(
        self,
        messages: list[dict[str, str]],
        *,
        response_format: dict[str, Any] | None,
        max_tokens: int,
        metadata: dict[str, Any],
    ) -> Any:
        """Issue the request with retry and exponential backoff."""
        last_error: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                kwargs: dict[str, Any] = {
                    "model": self._model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                }
                if response_format is not None:
                    kwargs["response_format"] = response_format

                response = await self._client.chat.completions.create(**kwargs)
                logger.debug(
                    "llm_completion",
                    extra={
                        "provider": "groq",
                        "model": response.model,
                        "finish_reason": (
                            response.choices[0].finish_reason if response.choices else ""
                        ),
                        "output_tokens": response.usage.completion_tokens if response.usage else 0,
                        "attempt": attempt + 1,
                        **{k: v for k, v in metadata.items() if k != "agent"},
                    },
                )
                return response

            except Exception as exc:  # noqa: BLE001
                if not self._is_retryable(exc):
                    raise self._translate(exc, metadata) from exc
                last_error = exc

            if attempt >= self._max_retries:
                break

            delay = min(2.0**attempt + random.uniform(0, 1), 30.0)
            logger.warning(
                "llm_retry",
                extra={
                    "provider": "groq",
                    "attempt": attempt + 1,
                    "delay_seconds": round(delay, 2),
                    "error": type(last_error).__name__,
                },
            )
            await asyncio.sleep(delay)

        raise LLMError(
            f"Groq unavailable after {self._max_retries + 1} attempts: {last_error}",
            details=metadata,
        ) from last_error

    @staticmethod
    def _extract_usage(response: Any) -> TokenUsage:
        usage = getattr(response, "usage", None)
        if usage is None:
            return TokenUsage()
        return TokenUsage(
            input_tokens=getattr(usage, "prompt_tokens", 0),
            output_tokens=getattr(usage, "completion_tokens", 0),
        )

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        """Whether another attempt on the same provider could succeed."""
        status = getattr(exc, "status_code", None)
        if isinstance(status, int):
            return status in _RETRYABLE_STATUS
        if isinstance(exc, _RETRYABLE_TRANSPORT):
            return True
        exc_type = type(exc).__name__
        return exc_type in {
            "RateLimitError",
            "APITimeoutError",
            "APIConnectionError",
            "InternalServerError",
        }

    @staticmethod
    def _translate(exc: Exception, metadata: dict[str, Any]) -> AegisError:
        """Turn a provider error into one that describes the real problem."""
        message = str(exc)
        status = getattr(exc, "status_code", None)

        if status in (401, 403) or "auth" in message.lower() or "api key" in message.lower():
            return ConfigurationError(
                f"The configured GROQ_API_KEY was rejected: {message}. "
                "Get a key at https://console.groq.com/ and set GROQ_API_KEY in your .env file."
            )
        if status == 429 or "rate limit" in message.lower() or "quota" in message.lower():
            return ConfigurationError(
                f"Groq quota exhausted: {message}. Wait for the window to reset."
            )
        if status == 404 or ("model" in message.lower() and "not found" in message.lower()):
            return ConfigurationError(
                f"The configured Groq model is not available: {message}. "
                "Check GROQ_MODEL in your .env file."
            )
        return LLMError(
            f"Groq rejected the request: {message}",
            details=metadata,
        )
