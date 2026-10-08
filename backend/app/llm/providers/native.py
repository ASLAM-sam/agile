"""Adapters for the vendors with first-party or specialised clients.

`LLMClient` (Anthropic) and `GeminiClient` already work and are already tested.
`GroqClient` wraps the Groq API via the OpenAI-compatible endpoint.

These adapters wrap them rather than reimplementing them — the only thing added
is failure classification, which the manager needs and the clients had no reason
to expose.

All are constructed with max_retries=0 when used through the manager (which
handles retries). The clients themselves may still perform internal retries
for the standalone use case.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.core.enums import ErrorKind
from app.core.exceptions import ConfigurationError, LLMError
from app.llm.providers.base import ProviderAdapter, ProviderSpec
from app.llm.types import Completion, PromptBundle, TextCompletion

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.llm.protocol import LLMProvider


class _SdkAdapter(ProviderAdapter):
    """Shared plumbing for adapters backed by a first-party client."""

    def __init__(self, spec: ProviderSpec, *, api_key: str | None) -> None:
        super().__init__(spec)
        self._api_key = api_key
        self._client: LLMProvider | None = None

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    def _require_client(self) -> LLMProvider:
        """Build the client on first use.

        Deferred so an unconfigured provider can still be listed on the
        dashboard without its constructor raising at import time.
        """
        if self._client is None:
            self._client = self._build_client()
        return self._client

    def _build_client(self) -> LLMProvider:  # pragma: no cover - overridden
        raise NotImplementedError

    async def complete_structured(self, prompt: PromptBundle) -> Completion:
        return await self._require_client().complete_structured(prompt)

    async def complete_text(self, prompt: PromptBundle) -> TextCompletion:
        return await self._require_client().complete_text(prompt)

    async def aclose(self) -> None:
        client: Any = self._client
        if client is not None and hasattr(client, "aclose"):
            await client.aclose()

    @staticmethod
    def _chain(error: BaseException, *, limit: int = 5) -> list[BaseException]:
        """The error and everything it was raised from."""
        chain: list[BaseException] = []
        current: BaseException | None = error
        while current is not None and len(chain) < limit:
            chain.append(current)
            current = current.__cause__
        return chain

    @staticmethod
    def _classify_common(error: BaseException) -> ErrorKind | None:
        """Classification shared across all adapters."""
        if isinstance(error, ConfigurationError):
            message = str(error).lower()
            if "quota" in message or "credit" in message or "rate limit" in message:
                return ErrorKind.QUOTA
            if "key" in message:
                return ErrorKind.AUTH
            return ErrorKind.UNAVAILABLE
        return None


class AnthropicAdapter(_SdkAdapter):
    """Anthropic Claude, via `app.llm.client.LLMClient`."""

    def _build_client(self) -> LLMProvider:
        from app.llm.client import LLMClient

        return LLMClient(api_key=self._api_key, model=self.model, max_retries=0)

    def classify(self, error: BaseException) -> ErrorKind:
        common = self._classify_common(error)
        if common is not None:
            return common

        import anthropic

        transient = (
            anthropic.APIConnectionError,
            anthropic.APITimeoutError,
            anthropic.InternalServerError,
        )
        for candidate in self._chain(error):
            if isinstance(candidate, anthropic.RateLimitError):
                return ErrorKind.QUOTA
            if isinstance(candidate, anthropic.AuthenticationError):
                return ErrorKind.AUTH
            if isinstance(candidate, transient):
                return ErrorKind.RETRYABLE

        message = str(error).lower()
        if "unavailable after" in message:
            return ErrorKind.RETRYABLE
        if "declined this request" in message:
            return ErrorKind.UNAVAILABLE
        return ErrorKind.FATAL


class GeminiAdapter(_SdkAdapter):
    """Google Gemini, via `app.llm.gemini.GeminiClient`.

    Each role slot gets its own adapter instance with its own API key.
    """

    def __init__(
        self, spec: ProviderSpec, *, api_key: str | None, slot_name: str = "gemini"
    ) -> None:
        super().__init__(spec, api_key=api_key)
        self._slot_name = slot_name

    def _build_client(self) -> LLMProvider:
        from app.llm.gemini import GeminiClient

        return GeminiClient(
            api_key=self._api_key,
            model=self.model,
            max_retries=0,
            slot_name=self._slot_name,
        )

    def classify(self, error: BaseException) -> ErrorKind:
        common = self._classify_common(error)
        if common is not None:
            return common

        if isinstance(error, LLMError) and error.details.get("stop_reason") == "max_tokens":
            return ErrorKind.RETRYABLE

        from google.genai import errors as genai_errors

        for candidate in self._chain(error):
            if not isinstance(candidate, genai_errors.APIError):
                continue
            code = getattr(candidate, "code", None)
            if code == 429:
                return ErrorKind.QUOTA
            if code in (401, 403):
                return ErrorKind.AUTH
            if code == 404:
                return ErrorKind.UNAVAILABLE
            if isinstance(code, int) and 500 <= code < 600:
                return ErrorKind.RETRYABLE
            return ErrorKind.FATAL

        message = str(error).lower()
        if "unavailable after" in message:
            return ErrorKind.RETRYABLE
        if "declined this request" in message:
            return ErrorKind.UNAVAILABLE
        return ErrorKind.FATAL


class GroqAdapter(_SdkAdapter):
    """Groq, via `app.llm.groq.GroqClient`."""

    def _build_client(self) -> LLMProvider:
        from app.llm.groq import GroqClient

        return GroqClient(
            api_key=self._api_key,
            model=self.model,
            base_url="https://api.groq.com/openai/v1",
            max_retries=0,
        )

    def classify(self, error: BaseException) -> ErrorKind:
        common = self._classify_common(error)
        if common is not None:
            return common

        message = str(error).lower()
        status = getattr(error, "status_code", None)

        if status in (401, 403) or "api key" in message or "unauthorized" in message:
            return ErrorKind.AUTH
        if status == 429 or "rate limit" in message or "quota" in message:
            return ErrorKind.QUOTA
        if status == 404 or ("not found" in message and "model" in message):
            return ErrorKind.UNAVAILABLE
        if status and isinstance(status, int) and 500 <= status < 600:
            return ErrorKind.RETRYABLE
        if "timeout" in message or "connection" in message:
            return ErrorKind.RETRYABLE
        if "declined" in message or "refused" in message:
            return ErrorKind.UNAVAILABLE

        return ErrorKind.FATAL
