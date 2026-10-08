"""OpenAI Provider Adapter.

Uses the OpenAI chat completions endpoint via the reusable OpenAICompatibleAdapter.
"""

from __future__ import annotations

from app.llm.providers.base import ProviderSpec
from app.llm.providers.openai_compatible import OpenAICompatibleAdapter


class OpenAIAdapter(OpenAICompatibleAdapter):
    """OpenAI API provider adapter."""

    def __init__(
        self,
        spec: ProviderSpec,
        *,
        api_key: str | None,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 600.0,
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
