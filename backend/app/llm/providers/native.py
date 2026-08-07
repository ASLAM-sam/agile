"""Adapters for the two vendors with first-party SDK clients.

`LLMClient` and `GeminiClient` already work and are already tested. These
adapters wrap them rather than reimplementing them — the only thing added is
failure classification, which the manager needs and the clients had no reason
to expose.

Both are constructed with `max_retries=0`. Retrying is the `RetryManager`'s
job now; leaving it switched on here as well would multiply attempts instead
of composing them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.core.enums import ErrorKind
from app.core.exceptions import ConfigurationError
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
        """The error and everything it was raised from.

        Both clients run an internal retry loop that wraps the last transport
        failure in a generic `LLMError`. Classifying only the outer exception
        reads an exhausted quota as an ordinary timeout — which then earns no
        cooldown, so every remaining agent in the run pays another round trip
        to rediscover the same empty quota.
        """
        chain: list[BaseException] = []
        current: BaseException | None = error
        while current is not None and len(chain) < limit:
            chain.append(current)
            current = current.__cause__
        return chain

    @staticmethod
    def _classify_common(error: BaseException) -> ErrorKind | None:
        """Classification both clients share.

        Both translate provider-level problems — rejected key, exhausted
        credit or quota, missing model — into `ConfigurationError`. Every one
        of those means *this* provider cannot serve the request while another
        one might, which is precisely a failover.
        """
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
            # A refusal is about this model's judgement, not the request's
            # validity — another vendor may well answer it.
            return ErrorKind.UNAVAILABLE
        return ErrorKind.FATAL


class GeminiAdapter(_SdkAdapter):
    """Google Gemini, via `app.llm.gemini.GeminiClient`."""

    def _build_client(self) -> LLMProvider:
        from app.llm.gemini import GeminiClient

        return GeminiClient(api_key=self._api_key, model=self.model, max_retries=0)

    def classify(self, error: BaseException) -> ErrorKind:
        common = self._classify_common(error)
        if common is not None:
            return common

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
