"""GitHub Models Provider Adapter.

Uses GitHub Models / Azure AI endpoints with independent token authentication.
"""

from __future__ import annotations

from app.llm.providers.base import ProviderSpec
from app.llm.providers.openai_compatible import OpenAICompatibleAdapter


class GitHubModelsAdapter(OpenAICompatibleAdapter):
    """GitHub Models provider adapter."""

    def __init__(
        self,
        spec: ProviderSpec,
        *,
        token: str | None,
        base_url: str = "https://models.inference.ai.azure.com",
        timeout_seconds: float = 600.0,
    ) -> None:
        super().__init__(
            spec,
            base_url=base_url,
            api_key=token,
            timeout_seconds=timeout_seconds,
            supports_json_schema=True,
            supports_json_object=True,
            requires_api_key=True,
        )
