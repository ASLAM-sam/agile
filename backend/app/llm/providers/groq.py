"""Groq Cloud Provider Adapter.

Uses Groq Cloud's OpenAI-compatible endpoint.
"""

from __future__ import annotations

from app.llm.providers.base import ProviderSpec
from app.llm.providers.openai_compatible import OpenAICompatibleAdapter


class GroqAdapter(OpenAICompatibleAdapter):
    """Groq Cloud provider adapter."""

    def __init__(
        self,
        spec: ProviderSpec,
        *,
        api_key: str | None,
        base_url: str = "https://api.groq.com/openai/v1",
        timeout_seconds: float = 300.0,
    ) -> None:
        super().__init__(
            spec,
            base_url=base_url,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            supports_json_schema=True,
            supports_json_object=True,
            requires_api_key=True,
        )
