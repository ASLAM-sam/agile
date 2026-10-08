"""Google Gemini client wrapper.

A role-specific LLM provider selected by the AgentModelRegistry.
Supports gemini-2.0-flash and newer models.

Key differences from older Gemini SDK usage:
- ThinkingConfig: gemini-2.0-flash does not support thinking_budget=-1.
  We disable thinking entirely (thinking_budget=0) for flash models to
  avoid 400 errors. If a thinking-capable model is configured (gemini-2.0-
  flash-thinking), set GEMINI_*_MODEL accordingly.
- Structured output via response_mime_type="application/json" +
  response_json_schema continues to work unchanged.
- Streaming is used for all completions to avoid HTTP timeouts on large
  code-generation batches.
"""

from __future__ import annotations

import asyncio
import json
import random
import re
from typing import Any

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

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

#: Authoritative Centralized Gemini Model - ONLY this model may be used
GEMINI_MODEL: str = "gemini-3.6-flash"


def validate_gemini_model(model: str | None) -> None:
    """Defensive validation: reject any model other than gemini-3.6-flash."""
    if model and model != GEMINI_MODEL:
        raise ConfigurationError(
            f"Unauthorized Gemini model requested: '{model}'. ONLY '{GEMINI_MODEL}' is allowed."
        )



def classify_provider_error(exc: Exception | None) -> str:
    """Classify an LLM exception into a standard taxonomy.

    Categories:
      - RATE_LIMITED
      - AUTHENTICATION_ERROR
      - TIMEOUT
      - SERVER_ERROR
      - INVALID_REQUEST
      - MODEL_ERROR
      - UNKNOWN_PROVIDER_ERROR
    """
    if exc is None:
        return "UNKNOWN_PROVIDER_ERROR"

    code = getattr(exc, "code", None)
    if code is None and hasattr(exc, "status_code"):
        code = exc.status_code

    msg = str(exc).lower()
    exc_type = type(exc).__name__.lower()

    if (
        code == 429
        or "rate limit" in msg
        or "resource_exhausted" in exc_type
        or "quota" in msg
        or "tpm" in msg
        or "rpm" in msg
        or "free_tier_requests" in msg
        or "generativelanguage.googleapis.com" in msg
    ):
        return "RATE_LIMITED"
    if (
        code in (401, 403)
        or "api key not valid" in msg
        or "permission_denied" in exc_type
        or "unauthenticated" in msg
        or "invalid api key" in msg
    ):
        return "AUTHENTICATION_ERROR"
    if (
        isinstance(exc, (asyncio.TimeoutError, TimeoutError, httpx.TimeoutException))
        or code in (408, 504)
        or "deadline_exceeded" in msg
        or "timed out" in msg
        or "timeout" in msg
    ):
        return "TIMEOUT"
    if (
        (isinstance(code, int) and 500 <= code < 600)
        or code in (500, 502, 503)
        or "internal" in msg
        or "server error" in msg
        or "bad gateway" in msg
        or "service unavailable" in msg
    ):
        return "SERVER_ERROR"
    if code == 404 or "model" in msg or "not found" in msg:
        return "MODEL_ERROR"
    if code == 400 or "invalid_argument" in exc_type or "bad request" in msg:
        return "INVALID_REQUEST"

    return "UNKNOWN_PROVIDER_ERROR"


def _extract_retry_after(exc: Exception | None) -> float | None:
    """Extract retry delay in seconds from response headers or error message."""
    if exc is None:
        return None
    if hasattr(exc, "response") and hasattr(exc.response, "headers"):
        ra = exc.response.headers.get("retry-after")
        if ra:
            try:
                return float(ra)
            except ValueError:
                pass
    msg = str(exc)
    m = re.search(r"retry(?:\s+after)?\s+in\s+([\d\.]+)\s*s?", msg, re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return None


class GeminiClient:
    """Async wrapper around the Gemini generateContent API.

    Designed to be instantiated per provider slot (frontend, backend, qa,
    improvement) with its own API key and model. The manager never shares
    instances across roles.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        max_retries: int = 3,
        timeout_seconds: float = 900.0,
        slot_name: str = "gemini",
        retry_on_rate_limit: bool = False,
    ) -> None:
        if not api_key:
            raise ConfigurationError(
                f"Gemini API key for slot '{slot_name}' is not configured "
                "(GOOGLE_API_KEY or GEMINI_*_API_KEY). "
                "Set the appropriate GEMINI_*_API_KEY environment variable. "
                "A free key can be created at https://aistudio.google.com/app/apikey"
            )
        self._client = genai.Client(
            api_key=api_key,
            http_options=genai_types.HttpOptions(
                timeout=int(timeout_seconds * 1000),  # SDK expects milliseconds
            ),
        )
        validate_gemini_model(model)
        self._model = GEMINI_MODEL
        self._max_retries = max_retries
        self._slot_name = slot_name
        self._retry_on_rate_limit = retry_on_rate_limit
        self.api_key = api_key

    @property
    def model(self) -> str:
        return self._model

    async def complete_structured(
        self, prompt: PromptBundle, *, model: str | None = None
    ) -> Completion:
        """Run a completion constrained to `prompt.schema`."""
        if prompt.schema is None:
            raise ValueError("complete_structured requires a schema on the PromptBundle.")

        target_model = model or self._model
        result = await self._send(
            prompt,
            response_mime_type="application/json",
            response_json_schema=prompt.schema,
            model=target_model,
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

    async def complete_text(
        self, prompt: PromptBundle, *, model: str | None = None
    ) -> TextCompletion:
        """Run a free-form completion returning plain text."""
        target_model = model or self._model
        result = await self._send(prompt, model=target_model)
        self._guard_refusal(result)
        return TextCompletion(
            text=result.text,
            usage=result.usage,
            stop_reason=result.finish_reason,
            model=result.model,
        )

    async def aclose(self) -> None:
        """Release the underlying transport.

        The SDK manages its own connection pool internally; nothing to await.
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
        model: str | None = None,
    ) -> genai_types.GenerateContentConfig:
        """Assemble the request configuration for target model."""
        target_model = model or self._model
        validate_gemini_model(target_model)
        system = prompt.cacheable_system
        if prompt.volatile_system:
            system = f"{system}\n\n{prompt.volatile_system}"

        config_kwargs: dict[str, Any] = {
            "system_instruction": system,
            "max_output_tokens": prompt.max_tokens or 32000,
            "response_mime_type": response_mime_type,
            "response_json_schema": response_json_schema,
        }
        return genai_types.GenerateContentConfig(**config_kwargs)

    async def _send(
        self,
        prompt: PromptBundle,
        *,
        response_mime_type: str | None = None,
        response_json_schema: dict[str, Any] | None = None,
        model: str | None = None,
    ) -> _Result:
        """Issue the request with retry and backoff (same provider only)."""
        target_model = model or self._model
        validate_gemini_model(target_model)
        config = self._build_config(
            prompt,
            response_mime_type=response_mime_type,
            response_json_schema=response_json_schema,
            model=target_model,
        )

        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                result = await self._stream_once(prompt, config, model=target_model)
                logger.debug(
                    "llm_completion",
                    extra={
                        "provider": self._slot_name,
                        "model": result.model,
                        "finish_reason": result.finish_reason,
                        "output_tokens": result.usage.output_tokens,
                        "attempt": attempt + 1,
                        **prompt.metadata,
                    },
                )
                return result

            except genai_errors.APIError as exc:
                error_kind = classify_provider_error(exc)
                if (
                    error_kind in ("RATE_LIMITED", "SERVER_ERROR")
                    and not self._retry_on_rate_limit
                ):
                    raise self._translate(exc, prompt, model=target_model) from exc
                ra = _extract_retry_after(exc)
                if error_kind == "RATE_LIMITED" and (
                    "per day" in str(exc).lower()
                    or "daily" in str(exc).lower()
                    or "resource_exhausted" in str(exc).lower()
                    or (ra is not None and ra > 60)
                ):
                    raise self._translate(exc, prompt, model=target_model) from exc
                if not self._is_retryable(exc):
                    raise self._translate(exc, prompt, model=target_model) from exc
                last_error = exc
            except _RETRYABLE_TRANSPORT as exc:
                last_error = exc

            if attempt >= self._max_retries:
                break

            error_kind = classify_provider_error(last_error)
            # Bounded exponential backoff, respecting retry-after if provided
            delay = min(2.0**attempt + random.uniform(0.5, 1.5), 30.0)
            ra = _extract_retry_after(last_error)
            if ra is not None and ra > 0:
                delay = min(max(delay, ra), 60.0)

            logger.warning(
                "llm_retry",
                extra={
                    "provider": self._slot_name,
                    "model": target_model,
                    "attempt": attempt + 1,
                    "delay_seconds": round(delay, 2),
                    "error_kind": error_kind,
                    "error": type(last_error).__name__,
                    **prompt.metadata,
                },
            )
            await asyncio.sleep(delay)

        if last_error is not None:
            raise self._translate(last_error, prompt, model=target_model) from last_error

        raise LLMError(
            f"Gemini ({self._slot_name}) unavailable for model '{target_model}' "
            f"after {self._max_retries + 1} attempts",
            details={
                "error_kind": "UNKNOWN_PROVIDER_ERROR",
                "provider_slot": self._slot_name,
                "model": target_model,
                **prompt.metadata,
            },
        )

    async def _stream_once(
        self,
        prompt: PromptBundle,
        config: genai_types.GenerateContentConfig,
        *,
        model: str | None = None,
    ) -> _Result:
        """Consume one streamed response into a complete result."""
        target_model = model or self._model
        validate_gemini_model(target_model)
        chunks: list[str] = []
        usage = TokenUsage()
        finish_reason = ""
        model_version = target_model

        stream = await self._client.aio.models.generate_content_stream(
            model=target_model,
            contents=prompt.user_message,
            config=config,
        )
        async for chunk in stream:
            text = getattr(chunk, "text", None)
            if text:
                chunks.append(text)
            if chunk.model_version:
                model_version = chunk.model_version
            # Usage is cumulative; the last chunk wins.
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

        Thinking tokens are billed as output but reported separately, so
        they are folded in — otherwise a reasoning-heavy run looks cheaper
        than it was.
        """
        return TokenUsage(
            input_tokens=metadata.prompt_token_count or 0,
            output_tokens=(metadata.candidates_token_count or 0)
            + (metadata.thoughts_token_count or 0),
            cache_read_tokens=metadata.cached_content_token_count or 0,
        )

    @staticmethod
    def _is_retryable(exc: genai_errors.APIError) -> bool:
        """Whether another attempt on the SAME provider could plausibly succeed."""
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

    def _translate(
        self,
        exc: Exception,
        prompt: PromptBundle,
        *,
        model: str | None = None,
    ) -> AegisError:
        """Turn a provider error into one that describes the real problem."""
        target_model = model or self._model
        error_kind = classify_provider_error(exc)
        message = (
            self._provider_message(exc)
            if isinstance(exc, genai_errors.APIError)
            else str(exc)
        )

        err: AegisError
        if error_kind == "AUTHENTICATION_ERROR":
            err = ConfigurationError(
                f"The configured Gemini API key for slot '{self._slot_name}' was rejected: "
                f"{message}. Create a fresh key at https://aistudio.google.com/apikey.",
                details=prompt.metadata,
            )
        elif error_kind == "RATE_LIMITED":
            err = ConfigurationError(
                f"Gemini slot '{self._slot_name}' quota exhausted: {message}. "
                "The free tier limits requests per minute and per day; "
                "wait for the window to reset, "
                "or reduce GENERATION_BATCH_SIZE and MAX_CONCURRENT_RUNS.",
                details=prompt.metadata,
            )
        elif error_kind == "MODEL_ERROR":
            err = ConfigurationError(
                f"The configured GEMINI_MODEL ({target_model}) for slot '{self._slot_name}' "
                f"was rejected: {message}",
                details=prompt.metadata,
            )
        else:
            err = LLMError(
                f"The model provider rejected the request: {message}",
                details=prompt.metadata,
            )

        retry_after = _extract_retry_after(exc)
        if retry_after is None or retry_after <= 0:
            retry_after = 60.0
        err.error_kind = error_kind
        err.provider_slot = self._slot_name
        err.retry_after = retry_after
        err.model = target_model
        err.status = "Rate Limited" if error_kind == "RATE_LIMITED" else "Failed"
        return err


class _Result:
    """One assembled completion, provider types kept out of the agent layer."""

    __slots__ = ("finish_reason", "model", "text", "usage")

    def __init__(self, *, text: str, usage: TokenUsage, finish_reason: str, model: str) -> None:
        self.text = text
        self.usage = usage
        self.finish_reason = finish_reason
        self.model = model
