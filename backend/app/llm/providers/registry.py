"""Provider registry and factory.

Constructs provider adapters dynamically from configuration and credentials.
Adding a provider requires registering a factory here — nothing in the agent layer changes.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.core.config import Settings
from app.core.config import settings as default_settings
from app.llm.providers.base import ProviderAdapter, ProviderSpec
from app.llm.providers.gemini import GeminiAdapter
from app.llm.providers.github_models import GitHubModelsAdapter
from app.llm.providers.groq import GroqAdapter
from app.llm.providers.mistral import MistralAdapter
from app.llm.providers.openai import OpenAIAdapter
from app.llm.providers.openai_compatible import OpenAICompatibleAdapter

PROVIDER_LABELS: dict[str, tuple[str, tuple[str, ...]]] = {
    "gemini": ("Google Gemini", ("structured output", "fast", "multimodal")),
    "openai": ("OpenAI", ("structured output", "reasoning", "general")),
    "mistral": ("Mistral AI", ("coding", "multilingual", "open weights")),
    "github_models": ("GitHub Models", ("developer tier", "azure ai")),
    "groq": ("Groq Cloud", ("ultra-fast", "open models")),
    "deepseek": ("DeepSeek", ("reasoning", "coding", "cost-efficient")),
    "sambanova": ("SambaNova", ("fast inference", "open models")),
    "siliconflow": ("SiliconFlow", ("fast inference", "open weights", "free tier", "coding")),
    "nvidia": ("NVIDIA NIM", ("super reasoning", "planning", "qa", "debug", "open weights")),
    "ollama": ("Ollama", ("local", "offline")),
}

ProviderFactory = Callable[[ProviderSpec, Settings, str | None], ProviderAdapter]


def _build_gemini(spec: ProviderSpec, config: Settings, api_key: str | None) -> ProviderAdapter:
    key = api_key or config.frontend_api_key01 or config.planner_api_key01 or config.backend_api_key01
    return GeminiAdapter(spec, api_key=key, slot_name=spec.key)


def _build_openai(spec: ProviderSpec, config: Settings, api_key: str | None) -> ProviderAdapter:
    key = api_key or config.openai_api_key
    return OpenAIAdapter(
        spec,
        api_key=key,
        base_url=config.openai_base_url,
        timeout_seconds=config.llm_timeout_seconds,
    )


def _build_mistral(spec: ProviderSpec, config: Settings, api_key: str | None) -> ProviderAdapter:
    key = api_key or config.mistral_api_key
    return MistralAdapter(
        spec,
        api_key=key,
        base_url=config.mistral_base_url,
        timeout_seconds=config.llm_timeout_seconds,
    )


def _build_github_models(spec: ProviderSpec, config: Settings, api_key: str | None) -> ProviderAdapter:
    token = api_key or config.github_token
    return GitHubModelsAdapter(
        spec,
        token=token,
        base_url=config.github_models_base_url,
        timeout_seconds=config.llm_timeout_seconds,
    )


def _build_groq(spec: ProviderSpec, config: Settings, api_key: str | None) -> ProviderAdapter:
    key = api_key or config.groq_api_key
    return GroqAdapter(
        spec,
        api_key=key,
        base_url=config.groq_base_url,
        timeout_seconds=config.llm_timeout_seconds,
    )


def _build_deepseek(spec: ProviderSpec, config: Settings, api_key: str | None) -> ProviderAdapter:
    key = api_key or config.deepseek_api_key
    return OpenAICompatibleAdapter(
        spec,
        base_url=config.deepseek_base_url,
        api_key=key,
        timeout_seconds=config.llm_timeout_seconds,
        supports_json_schema=True,
        supports_json_object=True,
    )


def _build_sambanova(spec: ProviderSpec, config: Settings, api_key: str | None) -> ProviderAdapter:
    key = api_key or config.sambanova_api_key
    return OpenAICompatibleAdapter(
        spec,
        base_url=config.sambanova_base_url,
        api_key=key,
        timeout_seconds=config.llm_timeout_seconds,
        supports_json_schema=True,
        supports_json_object=True,
    )


def _build_ollama(spec: ProviderSpec, config: Settings, api_key: str | None) -> ProviderAdapter:
    return OpenAICompatibleAdapter(
        spec,
        base_url="http://localhost:11434/v1",
        api_key=None,
        timeout_seconds=config.llm_timeout_seconds,
        supports_json_schema=False,
        supports_json_object=True,
        requires_api_key=False,
    )


def _build_siliconflow(spec: ProviderSpec, config: Settings, api_key: str | None) -> ProviderAdapter:
    import dataclasses
    from app.llm.siliconflow import SiliconFlowAdapter, get_siliconflow_catalog

    key = api_key or config.siliconflow_api_key
    catalog = get_siliconflow_catalog(config)
    resolved_model = catalog.select_model(
        api_key=key,
        explicit_model=config.siliconflow_model or (spec.model if spec.model and spec.model != "unconfigured" else None),
        base_url=config.siliconflow_base_url,
    )
    spec = dataclasses.replace(spec, model=resolved_model)
    return SiliconFlowAdapter(
        spec,
        base_url=config.siliconflow_base_url,
        api_key=key,
        timeout_seconds=config.llm_timeout_seconds,
        config=config,
    )


def _build_nvidia(spec: ProviderSpec, config: Settings, api_key: str | None) -> ProviderAdapter:
    key = (
        api_key
        or config.debug_api_key01
        or config.planner_api_key01
        or config.qa_api_key01
        or config.review_api_key01
        or getattr(config, "nvidia_api_key", None)
    )
    base_url = getattr(config, "nvidia_base_url", "https://integrate.api.nvidia.com/v1")
    return OpenAICompatibleAdapter(
        spec,
        base_url=base_url,
        api_key=key,
        timeout_seconds=config.llm_timeout_seconds,
        supports_json_schema=True,
        supports_json_object=True,
    )


PROVIDER_FACTORIES: dict[str, ProviderFactory] = {
    "gemini": _build_gemini,
    "openai": _build_openai,
    "mistral": _build_mistral,
    "github": _build_github_models,
    "github_models": _build_github_models,
    "groq": _build_groq,
    "deepseek": _build_deepseek,
    "sambanova": _build_sambanova,
    "siliconflow": _build_siliconflow,
    "nvidia": _build_nvidia,
    "ollama": _build_ollama,
}


class ProviderRegistry:
    """Manages available provider factories and adapter instantiation."""

    def __init__(self, config: Settings | None = None, *, settings: Settings | None = None) -> None:
        self.config = settings or config or default_settings
        self._factories: dict[str, ProviderFactory] = dict(PROVIDER_FACTORIES)

    def register_factory(self, name: str, factory: ProviderFactory) -> None:
        self._factories[name.lower()] = factory

    def build_providers(self) -> dict[str, ProviderAdapter]:
        """Construct dictionary of configured provider adapters keyed by provider name."""
        cfg = self.config
        adapters: dict[str, ProviderAdapter] = {}
        priority = 1

        if cfg.frontend_api_key01 or cfg.planner_api_key01 or cfg.backend_api_key01 or getattr(cfg, "debug_api_key01", None):
            adapters["gemini"] = self.build_adapter("gemini", model=cfg.gemini_model, priority=priority)
            priority += 1
        if cfg.openai_api_key:
            adapters["openai"] = self.build_adapter("openai", model=cfg.openai_model, priority=priority)
            priority += 1
        if cfg.mistral_api_key:
            adapters["mistral"] = self.build_adapter("mistral", model=cfg.mistral_model, priority=priority)
            priority += 1
        if cfg.github_models_token or cfg.github_token:
            adapters["github_models"] = self.build_adapter("github_models", model=cfg.github_models_model, priority=priority)
            priority += 1
        if cfg.groq_api_key:
            adapters["groq"] = self.build_adapter("groq", model=cfg.groq_model, priority=priority)
            priority += 1
        if cfg.siliconflow_api_key:
            from app.llm.siliconflow import get_siliconflow_catalog
            catalog = get_siliconflow_catalog(cfg)
            sf_model = catalog.select_model(
                api_key=cfg.siliconflow_api_key,
                explicit_model=cfg.siliconflow_model,
                base_url=cfg.siliconflow_base_url,
            )
            adapters["siliconflow"] = self.build_adapter("siliconflow", model=sf_model, priority=priority)
            priority += 1
        if getattr(cfg, "nvidia_api_key", None) or cfg.planner_api_key01 or cfg.qa_api_key01 or cfg.review_api_key01 or cfg.debug_api_key01:
            adapters["nvidia"] = self.build_adapter("nvidia", model=getattr(cfg, "nvidia_model", "nvidia/nemotron-3-super-120b-a12b"), priority=priority)
            priority += 1

        return adapters

    def build_adapter(
        self,
        provider_name: str,
        *,
        model: str,
        api_key: str | None = None,
        key: str | None = None,
        priority: int = 1,
    ) -> ProviderAdapter:
        p_name = provider_name.lower().strip()
        factory = self._factories.get(p_name)
        if factory is None:
            # Fallback to generic OpenAI compatible
            factory = _build_openai

        display_name, tags = PROVIDER_LABELS.get(p_name, (p_name.title(), ()))
        spec = ProviderSpec(
            key=key or p_name,
            display_name=display_name,
            model=model,
            priority=priority,
            tags=tags,
        )
        return factory(spec, self.config, api_key)

    def list_supported_providers(self) -> list[str]:
        return sorted(self._factories.keys())


def build_providers(config: Settings | None = None) -> list[ProviderAdapter]:
    """Construct standard adapters for configured providers."""
    registry = ProviderRegistry(config)
    cfg = config or default_settings
    adapters: list[ProviderAdapter] = []

    priority = 1
    # Gemini
    if cfg.google_api_key or cfg.frontend_api_key or cfg.get_backup_credentials():
        adapters.append(registry.build_adapter("gemini", model=cfg.gemini_model, priority=priority))
        priority += 1

    # OpenAI
    if cfg.openai_api_key:
        adapters.append(registry.build_adapter("openai", model=cfg.openai_model, priority=priority))
        priority += 1

    # Mistral
    if cfg.mistral_api_key:
        adapters.append(registry.build_adapter("mistral", model=cfg.mistral_model, priority=priority))
        priority += 1

    # GitHub Models
    if cfg.github_token:
        adapters.append(registry.build_adapter("github_models", model=cfg.github_models_model, priority=priority))
        priority += 1

    # Groq
    if cfg.groq_api_key:
        adapters.append(registry.build_adapter("groq", model=cfg.groq_model, priority=priority))
        priority += 1

    # SiliconFlow
    if cfg.siliconflow_api_key:
        from app.llm.siliconflow import get_siliconflow_catalog
        catalog = get_siliconflow_catalog(cfg)
        sf_model = catalog.select_model(
            api_key=cfg.siliconflow_api_key,
            explicit_model=cfg.siliconflow_model,
            base_url=cfg.siliconflow_base_url,
        )
        adapters.append(registry.build_adapter("siliconflow", model=sf_model, priority=priority))
        priority += 1

    # NVIDIA NIM
    if getattr(cfg, "nvidia_api_key", None) or cfg.planner_api_key01 or cfg.qa_api_key01 or cfg.review_api_key01 or cfg.debug_api_key01:
        adapters.append(registry.build_adapter("nvidia", model=getattr(cfg, "nvidia_model", "nvidia/nemotron-3-super-120b-a12b"), priority=priority))
        priority += 1

    return adapters
