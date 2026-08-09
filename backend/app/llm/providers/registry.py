"""Builds the provider set from configuration.

The single place that knows which vendors exist. Adding one means adding a
factory entry here — no change to the manager, the agents, or anything above
this layer.

Providers that are configured but lack credentials are still constructed and
listed. Hiding them would make "why is Groq not being used?" unanswerable from
the dashboard; showing them as `unconfigured` answers it.
"""

from __future__ import annotations

from collections.abc import Callable

from app.core.config import Settings
from app.core.config import settings as default_settings
from app.llm.providers.base import ProviderAdapter, ProviderSpec
from app.llm.providers.native import AnthropicAdapter, GeminiAdapter
from app.llm.providers.openai_compatible import OpenAICompatibleAdapter

#: Human-facing names and notes for the dashboard.
PROVIDER_LABELS: dict[str, tuple[str, tuple[str, ...]]] = {
    "gemini": ("Google Gemini", ("free tier", "structured output")),
    "groq": ("Groq", ("fast", "free tier")),
    "nvidia": ("NVIDIA NIM", ("large context", "open models")),
    "ollama": ("Ollama", ("local", "offline")),
    "openai": ("OpenAI", ("premium",)),
    "anthropic": ("Anthropic Claude", ("premium", "structured output")),
}

ProviderFactory = Callable[[ProviderSpec, Settings], ProviderAdapter]


def _anthropic(spec: ProviderSpec, config: Settings) -> ProviderAdapter:
    return AnthropicAdapter(spec, api_key=config.anthropic_api_key)


def _gemini(spec: ProviderSpec, config: Settings) -> ProviderAdapter:
    return GeminiAdapter(spec, api_key=config.google_api_key)


def _groq(spec: ProviderSpec, config: Settings) -> ProviderAdapter:
    return OpenAICompatibleAdapter(
        spec,
        base_url=config.groq_base_url,
        api_key=config.groq_api_key,
        timeout_seconds=config.llm_timeout_seconds,
        # Groq honours json_object across its catalogue; json_schema only on
        # some models, so the portable option is the one that always works.
        supports_json_schema=False,
        supports_json_object=True,
    )


def _nvidia(spec: ProviderSpec, config: Settings) -> ProviderAdapter:
    """NVIDIA NIM — hosted at build.nvidia.com or self-hosted.

    NIM exposes the OpenAI chat-completions contract, so it needs no client of
    its own: this is the same adapter Groq and OpenAI use, pointed at a
    different base URL. Structured-output support varies across the NIM
    catalogue, so it is read from configuration instead of being assumed.
    """
    mode = config.nvidia_structured_output
    return OpenAICompatibleAdapter(
        spec,
        base_url=config.nvidia_base_url,
        api_key=config.nvidia_api_key,
        timeout_seconds=config.llm_timeout_seconds,
        supports_json_schema=mode == "json_schema",
        supports_json_object=mode in ("json_schema", "json_object"),
    )


def _openai(spec: ProviderSpec, config: Settings) -> ProviderAdapter:
    return OpenAICompatibleAdapter(
        spec,
        base_url=config.openai_base_url,
        api_key=config.openai_api_key,
        timeout_seconds=config.llm_timeout_seconds,
        supports_json_schema=True,
        supports_json_object=True,
    )


def _ollama(spec: ProviderSpec, config: Settings) -> ProviderAdapter:
    return OpenAICompatibleAdapter(
        spec,
        base_url=config.ollama_base_url,
        api_key=None,
        timeout_seconds=config.llm_timeout_seconds,
        supports_json_schema=False,
        supports_json_object=True,
        requires_api_key=False,
    )


PROVIDER_FACTORIES: dict[str, ProviderFactory] = {
    "anthropic": _anthropic,
    "gemini": _gemini,
    "groq": _groq,
    "nvidia": _nvidia,
    "openai": _openai,
    "ollama": _ollama,
}


def build_providers(config: Settings | None = None) -> list[ProviderAdapter]:
    """Construct every known provider, in configured priority order."""
    config = config or default_settings
    disabled = {key.lower() for key in config.llm_disabled_providers}
    models = config.provider_models

    adapters: list[ProviderAdapter] = []
    for priority, key in enumerate(config.resolved_provider_priority):
        factory = PROVIDER_FACTORIES.get(key)
        if factory is None:
            continue
        display_name, tags = PROVIDER_LABELS.get(key, (key.title(), ()))
        enabled = key not in disabled and (key != "ollama" or config.ollama_enabled)
        spec = ProviderSpec(
            key=key,
            display_name=display_name,
            model=models.get(key, ""),
            priority=priority,
            enabled=enabled,
            tags=tags,
            max_prompt_tokens=getattr(config, f"{key}_max_prompt_tokens", 0),
            max_output_tokens=getattr(config, f"{key}_max_output_tokens", 0),
        )
        adapters.append(factory(spec, config))
    return adapters
