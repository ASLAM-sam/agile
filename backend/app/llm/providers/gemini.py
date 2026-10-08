"""Google Gemini Provider Adapter.

Wraps the Gemini client into the uniform ProviderAdapter interface.
"""

from __future__ import annotations

from typing import Any

from app.core.enums import ErrorKind
from app.llm.errors import LLMErrorCategory
from app.llm.gemini import GeminiClient, classify_provider_error, validate_gemini_model
from app.llm.providers.base import ProviderAdapter, ProviderSpec
from app.llm.types import Completion, PromptBundle, TextCompletion


class GeminiAdapter(ProviderAdapter):
    """Google Gemini provider adapter supporting structured and text completion."""

    def __init__(
        self,
        spec: ProviderSpec,
        *,
        api_key: str | None,
        slot_name: str = "gemini",
    ) -> None:
        super().__init__(spec)
        validate_gemini_model(spec.model)
        self._api_key = api_key
        self._slot_name = slot_name
        self._client: GeminiClient | None = None

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    def _get_client(self) -> GeminiClient:
        if self._client is None:
            self._client = GeminiClient(
                api_key=self._api_key,
                model=self.model,
                max_retries=0,
                slot_name=self._slot_name,
            )
        return self._client

    async def complete_structured(
        self, prompt: PromptBundle, *, model: str | None = None
    ) -> Completion:
        return await self._get_client().complete_structured(prompt, model=model)

    async def complete_text(
        self, prompt: PromptBundle, *, model: str | None = None
    ) -> TextCompletion:
        return await self._get_client().complete_text(prompt, model=model)

    def classify(self, error: BaseException) -> ErrorKind:
        category = self.classify_category(error)
        return category.to_error_kind()

    def classify_category(self, error: BaseException) -> LLMErrorCategory:
        tax = classify_provider_error(error if isinstance(error, Exception) else None)
        if tax == "RATE_LIMITED":
            msg = str(error).lower()
            if "daily" in msg or "rpd" in msg or "quota" in msg:
                return LLMErrorCategory.RATE_LIMIT_RPD
            if "tpm" in msg or "tokens per minute" in msg:
                return LLMErrorCategory.RATE_LIMIT_TPM
            return LLMErrorCategory.RATE_LIMIT_RPM
        if tax == "AUTHENTICATION_ERROR":
            return LLMErrorCategory.AUTHENTICATION
        if tax == "TIMEOUT":
            return LLMErrorCategory.TIMEOUT
        if tax == "SERVER_ERROR":
            return LLMErrorCategory.SERVER_ERROR
        if tax == "INVALID_REQUEST":
            return LLMErrorCategory.BAD_REQUEST
        if tax == "MODEL_ERROR":
            return LLMErrorCategory.INVALID_MODEL
        return LLMErrorCategory.UNKNOWN

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
