"""Mistral AI Provider Adapter.

Uses Mistral's OpenAI-compatible endpoint with independent credentials and configuration.
"""

from __future__ import annotations

from app.llm.providers.base import ProviderSpec
from app.llm.providers.openai_compatible import OpenAICompatibleAdapter


class MistralAdapter(OpenAICompatibleAdapter):
    """Mistral AI API provider adapter."""

    def __init__(
        self,
        spec: ProviderSpec,
        *,
        api_key: str | None,
        base_url: str = "https://api.mistral.ai/v1",
        timeout_seconds: float = 600.0,
    ) -> None:
        super().__init__(
            spec,
            base_url=base_url,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            supports_json_schema=False,
            supports_json_object=True,
            requires_api_key=True,
        )
