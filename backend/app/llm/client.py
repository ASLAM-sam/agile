"""Anthropic Claude client wrapper.

Responsibilities:
  * one place that knows how to talk to the model provider
  * strict JSON schema enforcement for agent outputs
  * retry with exponential backoff on transient failures
  * prompt caching of the stable system prefix
  * token accounting fed back into run statistics

Streaming is used unconditionally: agent completions routinely request tens of
thousands of output tokens, and non-streaming requests at that size hit HTTP
timeouts.
"""

from __future__ import annotations

import asyncio
import json
import random
from typing import Any

import anthropic

from app.core.config import settings
from app.core.exceptions import AegisError, ConfigurationError, LLMError
from app.core.logging import get_logger
from app.llm.types import Completion, PromptBundle, TextCompletion, TokenUsage

logger = get_logger(__name__)

_RETRYABLE = (
    anthropic.RateLimitError,
    anthropic.APIConnectionError,
    anthropic.InternalServerError,
    anthropic.APITimeoutError,
)


class LLMClient:
    """Async wrapper around the Anthropic Messages API."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        max_retries: int | None = None,
    ) -> None:
        key = api_key or getattr(settings, "anthropic_api_key", None)
        if not key:
            raise ConfigurationError(
                "ANTHROPIC_API_KEY is not configured. Set it in the environment "
                "before starting a generation run."
            )
        self._client = anthropic.AsyncAnthropic(
            api_key=key,
            timeout=settings.llm_timeout_seconds,
            max_retries=0,  # retry policy is owned by this class
        )
        self._model = model or getattr(settings, "llm_model", "claude-3-7-sonnet-20250219")
        self._max_retries = max_retries if max_retries is not None else settings.llm_max_retries

    @property
    def model(self) -> str:
        return self._model

    async def complete_structured(self, prompt: PromptBundle) -> Completion:
        """Run a completion constrained to `prompt.schema`.

        The response is guaranteed by the API to satisfy the schema, so the
        JSON parse below cannot see partial or malformed objects except when
        the response was truncated at `max_tokens`.
        """
        if prompt.schema is None:
            raise ValueError("complete_structured requires a schema on the PromptBundle.")

        message = await self._send(
            prompt,
            output_config={
                "effort": prompt.effort or getattr(settings, "llm_effort", "medium"),
                "format": {"type": "json_schema", "schema": prompt.schema},
            },
        )

        text = self._extract_text(message)
        if message.stop_reason == "max_tokens":
            raise LLMError(
                "Model output was truncated before the response could be completed. "
                "Reduce the requested batch size or raise llm_max_tokens.",
                details={"stop_reason": "max_tokens", "chars": len(text)},
            )
        if message.stop_reason == "refusal":
            raise LLMError(
                "The model declined this request.",
                details={"stop_reason": "refusal"},
            )

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:  # pragma: no cover - schema makes this unreachable
            raise LLMError(
                f"Model returned output that was not valid JSON: {exc}",
                details={"preview": text[:500]},
            ) from exc

        if not isinstance(data, dict):
            raise LLMError("Structured output must be a JSON object.")

        return Completion(
            data=data,
            usage=self._usage(message),
            stop_reason=message.stop_reason,
            model=message.model,
            raw_text=text,
        )

    async def complete_text(self, prompt: PromptBundle) -> TextCompletion:
        """Run a free-form completion returning plain text."""
        message = await self._send(
            prompt,
            output_config={"effort": prompt.effort or settings.llm_effort},
        )
        if message.stop_reason == "refusal":
            raise LLMError("The model declined this request.", details={"stop_reason": "refusal"})
        return TextCompletion(
            text=self._extract_text(message),
            usage=self._usage(message),
            stop_reason=message.stop_reason,
            model=message.model,
        )

    # --- internals -------------------------------------------------------

    @staticmethod
    def _provider_message(exc: anthropic.APIStatusError) -> str:
        """The provider's human-readable message, without the JSON envelope.

        `str(exc)` is the whole response body — status code, type discriminators
        and request id. That is the wrong thing to put in front of a user who
        just wants to know what to do next.
        """
        body = getattr(exc, "body", None)
        if isinstance(body, dict):
            error = body.get("error")
            if isinstance(error, dict):
                message = error.get("message")
                if isinstance(message, str) and message.strip():
                    return message.strip()
        return str(exc)

    def _translate_bad_request(
        self, exc: anthropic.BadRequestError, prompt: PromptBundle
    ) -> AegisError:
        """Turn a provider 400 into the error that describes the real problem.

        A depleted credit balance arrives as a 400 alongside genuine request
        defects, but it is an account state rather than a bug: it needs a
        billing action, not a stack trace and not a retry.
        """
        message = self._provider_message(exc)
        if "credit balance" in message.lower():
            return ConfigurationError(
                f"{message} Aegis cannot analyse requirements or generate code "
                "until the Anthropic account has available credit."
            )
        return LLMError(
            f"The model provider rejected the request: {message}",
            details=prompt.metadata,
        )

    async def _send(self, prompt: PromptBundle, *, output_config: dict[str, Any]) -> Any:
        """Issue the request with retry and backoff."""
        system = self._build_system(prompt)
        max_tokens = prompt.max_tokens or settings.llm_max_tokens

        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                async with self._client.messages.stream(
                    model=self._model,
                    max_tokens=max_tokens,
                    system=system,
                    thinking={"type": "adaptive"},
                    output_config=output_config,
                    messages=[{"role": "user", "content": prompt.user_message}],
                ) as stream:
                    message = await stream.get_final_message()

                logger.debug(
                    "llm_completion",
                    extra={
                        "model": message.model,
                        "stop_reason": message.stop_reason,
                        "output_tokens": message.usage.output_tokens,
                        "attempt": attempt + 1,
                        **prompt.metadata,
                    },
                )
                return message

            except _RETRYABLE as exc:
                last_error = exc
                if attempt >= self._max_retries:
                    break
                delay = min(2.0**attempt + random.uniform(0, 1), 30.0)
                logger.warning(
                    "llm_retry",
                    extra={
                        "attempt": attempt + 1,
                        "delay_seconds": round(delay, 2),
                        "error": type(exc).__name__,
                        **prompt.metadata,
                    },
                )
                await asyncio.sleep(delay)

            except anthropic.BadRequestError as exc:
                raise self._translate_bad_request(exc, prompt) from exc

            except anthropic.AuthenticationError as exc:
                raise ConfigurationError(
                    "The configured ANTHROPIC_API_KEY was rejected."
                ) from exc

        raise LLMError(
            f"Model provider unavailable after {self._max_retries + 1} attempts: {last_error}",
            details=prompt.metadata,
        ) from last_error

    @staticmethod
    def _build_system(prompt: PromptBundle) -> list[dict[str, Any]]:
        """Assemble the system blocks, caching the stable prefix.

        The cache breakpoint sits on the last stable block. Volatile content
        (project specifics that change per request) follows it uncached, so the
        expensive shared preamble is billed at cache-read rates across the many
        calls a single run makes.
        """
        blocks: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": prompt.cacheable_system,
                "cache_control": {"type": "ephemeral"},
            }
        ]
        if prompt.volatile_system:
            blocks.append({"type": "text", "text": prompt.volatile_system})
        return blocks

    @staticmethod
    def _extract_text(message: Any) -> str:
        """Concatenate text blocks, ignoring thinking blocks."""
        return "".join(
            block.text for block in message.content if getattr(block, "type", None) == "text"
        ).strip()

    @staticmethod
    def _usage(message: Any) -> TokenUsage:
        usage = message.usage
        return TokenUsage(
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
        )

    async def aclose(self) -> None:
        await self._client.close()
