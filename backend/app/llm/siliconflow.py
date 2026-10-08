"""SiliconFlow Free-Tier Provider Integration.

Implements:
1. Dynamic model catalog discovery & verification via SiliconFlow API.
2. Paid model rejection & protection for free plan users.
3. Non-chat model rejection (filtering embeddings, rerankers, diffusion, etc.).
4. Deterministic local ranking for AgileAgent roles (coding, reasoning, tools, structured output).
5. OpenAI-compatible adapter with quota tracking (RPM/RPD) and usage logging.
6. Strictly preserves generic LLM abstraction (ctx.llm) and 15-request hard limit.
"""

from __future__ import annotations

import copy
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import Settings
from app.core.config import settings as default_settings
from app.core.enums import AgentRole, ErrorKind, TaskKind
from app.core.exceptions import ConfigurationError, LLMError
from app.core.logging import get_logger
from app.llm.credentials import mask_key
from app.llm.errors import tag
from app.llm.providers.base import ProviderAdapter, ProviderSpec
from app.llm.providers.openai_compatible import OpenAICompatibleAdapter
from app.llm.quota import get_quota_engine
from app.llm.types import Completion, PromptBundle, TextCompletion, TokenUsage
from app.llm.usage import generate_request_id, get_usage_tracker
from app.llm.validation import describe_schema, normalize_unknown_fields, validate

logger = get_logger(__name__)

#: Deprecated / retired SiliconFlow models that must never be selected
DEPRECATED_MODELS: frozenset[str] = frozenset({
    "Hunyuan-MT-7B",
    "THUDM/GLM-4-9B-0414",
    "THUDM/glm-4-9b-chat",
    "tencent/Hunyuan-MT-7B",
})

#: Known paid / pro models that MUST be rejected on the free plan
KNOWN_PAID_MODELS: frozenset[str] = frozenset({
    "Qwen/Qwen2.5-72B-Instruct",
    "Qwen/Qwen3.8-27B",
    "Qwen/Qwen3.8-2.4T-A95B",
    "Qwen/Qwen3.6-35B-A3B",
    "Qwen/Qwen3.6-27B",
    "Qwen/Qwen3.5-122B-A10B",
    "Qwen/Qwen3.5-35B-A3B",
    "Qwen/Qwen3.5-27B",
    "deepseek-ai/DeepSeek-V4-Pro",
    "deepseek-ai/DeepSeek-V4-Pro-0813",
    "deepseek-ai/DeepSeek-V4-Flash-0731",
    "openai/gpt-oss-120b",
    "moonshotai/Kimi-K3",
    "MiniMaxAI/MiniMax-M3",
    "deepseek-ai/DeepSeek-V3",
    "deepseek-ai/DeepSeek-R1",
    "google/gemma-4-31B-it",
    "google/gemma-4-26B-A4B-it",
})

#: Known non-chat models that must be rejected
NON_CHAT_SUBTYPES_OR_PREFIXES: tuple[str, ...] = (
    "bge-m3",
    "bge-large",
    "bge-reranker",
    "reranker",
    "embedding",
    "text-to-image",
    "image-to-image",
    "speech-to-text",
    "text-to-video",
    "FLUX",
    "stable-diffusion",
    "Kolors",
    "sensevoice",
    "cosyvoice",
)


@dataclass(frozen=True)
class SiliconFlowModelInfo:
    """Capability and status metadata for a SiliconFlow model."""

    id: str
    display_name: str
    is_chat: bool
    is_free: bool
    is_available: bool
    coding_score: float  # 0.0 to 10.0
    reasoning_score: float  # 0.0 to 10.0
    agent_tool_score: float  # 0.0 to 10.0
    structured_output_score: float  # 0.0 to 10.0
    context_window: int
    latency_score: float  # 0.0 (slow) to 10.0 (fast)
    rpm_limit: int | None = None
    rpd_limit: int | None = None


#: Seed specifications for verified eligible models in SiliconFlow's ecosystem
KNOWN_FREE_MODELS_METADATA: dict[str, dict[str, Any]] = {
    "Qwen/Qwen3-8B": {
        "display_name": "Qwen 3 (8B) Free Tier",
        "is_chat": True,
        "is_free": True,
        "is_available": True,
        "coding_score": 9.2,
        "reasoning_score": 9.0,
        "agent_tool_score": 9.0,
        "structured_output_score": 9.5,
        "context_window": 32768,
        "latency_score": 8.5,
        "rpm_limit": 60,
        "rpd_limit": 1000,
    },
    "Qwen/Qwen2.5-7B-Instruct": {
        "display_name": "Qwen 2.5 (7B) Instruct Free Tier",
        "is_chat": True,
        "is_free": True,
        "is_available": True,
        "coding_score": 8.8,
        "reasoning_score": 8.5,
        "agent_tool_score": 8.5,
        "structured_output_score": 9.0,
        "context_window": 32768,
        "latency_score": 8.8,
        "rpm_limit": 60,
        "rpd_limit": 1000,
    },
    "Qwen/Qwen3.5-4B": {
        "display_name": "Qwen 3.5 (4B) Free Tier",
        "is_chat": True,
        "is_free": True,
        "is_available": False,  # Updated dynamically by catalog
        "coding_score": 8.0,
        "reasoning_score": 8.2,
        "agent_tool_score": 8.0,
        "structured_output_score": 8.5,
        "context_window": 32768,
        "latency_score": 9.5,
        "rpm_limit": 60,
        "rpd_limit": 1000,
    },
    "zai-org/GLM-4.5-Air": {
        "display_name": "GLM 4.5 Air Free Tier",
        "is_chat": True,
        "is_free": True,
        "is_available": True,
        "coding_score": 7.8,
        "reasoning_score": 8.0,
        "agent_tool_score": 8.0,
        "structured_output_score": 8.5,
        "context_window": 32768,
        "latency_score": 9.0,
        "rpm_limit": 60,
        "rpd_limit": 1000,
    },
}


class SiliconFlowCatalog:
    """Manages SiliconFlow model discovery, availability, and deterministic ranking."""

    def __init__(self, config: Settings | None = None) -> None:
        self.config = config or default_settings
        self._cached_catalog: list[SiliconFlowModelInfo] | None = None
        self._cache_timestamp: float = 0.0
        self._cache_ttl_seconds: float = 600.0  # 10 minutes cache

    def is_chat_model(self, model_id: str, sub_type: str = "chat") -> bool:
        """Verify whether a model is a chat completion model."""
        if not model_id or not isinstance(model_id, str):
            return False
        clean = model_id.strip().lower()
        if sub_type != "chat":
            return False
        for non_chat in NON_CHAT_SUBTYPES_OR_PREFIXES:
            if non_chat.lower() in clean:
                return False
        return True

    def is_free_model(self, model_id: str) -> bool:
        """Verify whether a model is eligible for the free plan."""
        clean = model_id.strip()
        if clean in KNOWN_PAID_MODELS:
            return False

        # Models with explicit large parameter counts (72B, 120B, 122B, Pro) are paid
        upper_clean = clean.upper()
        if any(marker in upper_clean for marker in ("-72B", "-120B", "-122B", "-35B", "-95B", "-PRO")):
            return False

        if clean in KNOWN_FREE_MODELS_METADATA:
            return KNOWN_FREE_MODELS_METADATA[clean]["is_free"]

        # Models with <= 9B parameters or designated Free Tier
        if any(marker in upper_clean for marker in ("-7B", "-8B", "-9B", "-4B", "-1.5B", "-AIR", "-FLASH")):
            return True

        return False

    def discover_models(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        force_refresh: bool = False,
    ) -> list[SiliconFlowModelInfo]:
        """Fetch model catalog from SiliconFlow API without consuming task LLM budget."""
        now = time.monotonic()
        if not force_refresh and self._cached_catalog is not None and (now - self._cache_timestamp) < self._cache_ttl_seconds:
            return self._cached_catalog

        key = api_key or self.config.siliconflow_api_key or self.config.get_role_credential("backend")
        primary_base = (base_url or self.config.siliconflow_base_url or "https://api.siliconflow.cn/v1").rstrip("/")
        candidate_bases = [primary_base]
        if "siliconflow.cn" in primary_base:
            candidate_bases.append("https://api.siliconflow.com/v1")
        elif "siliconflow.com" in primary_base:
            candidate_bases.append("https://api.siliconflow.cn/v1")

        raw_models: list[dict[str, Any]] = []
        if key and not key.startswith("mock_") and not key.startswith("test_"):
            for endpoint_base in candidate_bases:
                try:
                    url = f"{endpoint_base}/models?sub_type=chat"
                    headers = {"Authorization": f"Bearer {key.strip()}"}
                    # Discovery is pure metadata HTTP fetch: does NOT consume LLM task request
                    response = httpx.get(url, headers=headers, timeout=5.0)
                    if response.status_code == 200:
                        data = response.json()
                        raw_models = data.get("data", []) if isinstance(data, dict) else []
                        break
                except Exception as exc:
                    logger.debug("siliconflow_discovery_attempt_failed", extra={"base": endpoint_base, "error": str(exc)})

        # Parse discovered models
        catalog: list[SiliconFlowModelInfo] = []
        discovered_ids = {m.get("id") for m in raw_models if isinstance(m, dict) and m.get("id")}

        # Process live discovered models
        for m in raw_models:
            m_id = m.get("id", "")
            if not m_id:
                continue

            if m_id in DEPRECATED_MODELS:
                continue

            is_chat = self.is_chat_model(m_id)
            if not is_chat:
                continue

            is_free = self.is_free_model(m_id)
            seed = KNOWN_FREE_MODELS_METADATA.get(m_id, {})
            coding_score = float(seed.get("coding_score", 8.0 if "coder" in m_id.lower() or "qwen" in m_id.lower() else 7.0))
            reasoning_score = float(seed.get("reasoning_score", 8.5 if "qwen3" in m_id.lower() else 7.5))
            agent_tool_score = float(seed.get("agent_tool_score", 8.5))
            structured_output_score = float(seed.get("structured_output_score", 9.0))
            context_window = int(seed.get("context_window", 32768))
            latency_score = float(seed.get("latency_score", 8.5))
            rpm_limit = seed.get("rpm_limit", 60 if is_free else None)
            rpd_limit = seed.get("rpd_limit", 1000 if is_free else None)

            catalog.append(
                SiliconFlowModelInfo(
                    id=m_id,
                    display_name=seed.get("display_name", m_id),
                    is_chat=is_chat,
                    is_free=is_free,
                    is_available=True,
                    coding_score=coding_score,
                    reasoning_score=reasoning_score,
                    agent_tool_score=agent_tool_score,
                    structured_output_score=structured_output_score,
                    context_window=context_window,
                    latency_score=latency_score,
                    rpm_limit=rpm_limit,
                    rpd_limit=rpd_limit,
                )
            )

        # Ensure seed models are reflected with accurate availability
        for seed_id, seed in KNOWN_FREE_MODELS_METADATA.items():
            if seed_id in DEPRECATED_MODELS:
                continue
            if not any(item.id == seed_id for item in catalog):
                # If discovery ran against live API, availability is whether API returned it
                avail = bool(seed_id in discovered_ids) if discovered_ids else True
                catalog.append(
                    SiliconFlowModelInfo(
                        id=seed_id,
                        display_name=seed.get("display_name", seed_id),
                        is_chat=seed.get("is_chat", True),
                        is_free=seed.get("is_free", True),
                        is_available=avail,
                        coding_score=float(seed.get("coding_score", 8.0)),
                        reasoning_score=float(seed.get("reasoning_score", 8.0)),
                        agent_tool_score=float(seed.get("agent_tool_score", 8.0)),
                        structured_output_score=float(seed.get("structured_output_score", 9.0)),
                        context_window=int(seed.get("context_window", 32768)),
                        latency_score=float(seed.get("latency_score", 8.0)),
                        rpm_limit=seed.get("rpm_limit", 60),
                        rpd_limit=seed.get("rpd_limit", 1000),
                    )
                )

        self._cached_catalog = catalog
        self._cache_timestamp = now
        return catalog

    def get_eligible_free_chat_models(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> list[SiliconFlowModelInfo]:
        """Return all models that are chat-capable, currently available, and free-tier eligible."""
        all_models = self.discover_models(api_key=api_key, base_url=base_url)
        return [
            m for m in all_models
            if m.is_chat and m.is_free and m.is_available and m.id not in DEPRECATED_MODELS
        ]

    def rank_models_for_agent(
        self,
        models: list[SiliconFlowModelInfo],
        agent_role: AgentRole | str | None = None,
        task_kind: TaskKind | None = None,
    ) -> list[SiliconFlowModelInfo]:
        """Deterministically rank eligible free models according to AgileAgent priorities."""
        role_str = str(agent_role.value if isinstance(agent_role, AgentRole) else (agent_role or "")).lower()

        is_coding_role = any(r in role_str for r in ("backend", "frontend", "database", "qa", "debug"))
        is_reasoning_role = any(r in role_str for r in ("manager", "planner", "analyst", "architect", "review", "improvement"))

        def score(m: SiliconFlowModelInfo) -> float:
            base_score = (
                m.agent_tool_score * 2.0
                + m.structured_output_score * 2.0
                + (m.context_window / 32768.0) * 1.5
                + m.latency_score * 1.0
            )
            if is_coding_role:
                return base_score + m.coding_score * 3.5 + m.reasoning_score * 1.5
            elif is_reasoning_role:
                return base_score + m.reasoning_score * 3.5 + m.coding_score * 1.5
            else:
                return base_score + m.latency_score * 2.0 + m.coding_score * 2.0

        # Deterministic sorting: higher score first, tie-break by ID
        return sorted(models, key=lambda m: (-score(m), m.id))

    def select_model(
        self,
        *,
        api_key: str | None = None,
        explicit_model: str | None = None,
        agent_role: AgentRole | str | None = None,
        base_url: str | None = None,
    ) -> str:
        """Select model adhering to free-tier eligibility and automatic selection rules."""
        raw_explicit = (explicit_model or self.config.siliconflow_model or "").strip()

        if raw_explicit:
            # 1. Reject deprecated models
            if raw_explicit in DEPRECATED_MODELS:
                raise ConfigurationError(
                    f"SiliconFlow model '{raw_explicit}' is deprecated or no longer available."
                )

            # 2. Reject non-chat models
            if not self.is_chat_model(raw_explicit):
                raise ConfigurationError(
                    f"SiliconFlow model '{raw_explicit}' is not a chat-compatible model."
                )

            # 3. Reject paid models on the free plan
            if not self.is_free_model(raw_explicit):
                raise ConfigurationError(
                    f"SiliconFlow model '{raw_explicit}' is a paid model and cannot be selected "
                    f"on the free plan configuration."
                )

            return raw_explicit

        # Empty SILICONFLOW_MODEL: Automatic selection
        eligible = self.get_eligible_free_chat_models(api_key=api_key, base_url=base_url)
        if not eligible:
            # Safe default fallback from verified seed
            return "Qwen/Qwen3-8B"

        ranked = self.rank_models_for_agent(eligible, agent_role=agent_role)
        return ranked[0].id


_global_catalog: SiliconFlowCatalog | None = None


def get_siliconflow_catalog(config: Settings | None = None) -> SiliconFlowCatalog:
    global _global_catalog
    if _global_catalog is None:
        _global_catalog = SiliconFlowCatalog(config)
    return _global_catalog


class SiliconFlowAdapter(OpenAICompatibleAdapter):
    """Adapter for SiliconFlow chat completion endpoint.

    Uses OpenAI-compatible protocol with strict model specification,
    QuotaEngine RPM/RPD tracking, and secret-scrubbed usage logging.
    """

    def __init__(
        self,
        spec: ProviderSpec,
        *,
        base_url: str,
        api_key: str | None,
        timeout_seconds: float = 900.0,
        config: Settings | None = None,
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
        self.config = config or default_settings
        self.catalog = get_siliconflow_catalog(self.config)
        self.quota_engine = get_quota_engine()
        self.usage_tracker = get_usage_tracker()
        self.provider_name = "siliconflow"

    @property
    def name(self) -> str:
        return "siliconflow"

    def _resolve_model(self, model: str | None, role: str | None = None) -> str:
        """Ensure an explicit, non-null, eligible model is always sent."""
        if model and model.strip():
            target_model = model.strip()
        else:
            target_model = self.catalog.select_model(
                api_key=self._api_key,
                explicit_model=self.spec.model if self.spec.model != "unconfigured" else None,
                agent_role=role,
            )
        return target_model

    async def complete_text(
        self, prompt: PromptBundle, *, model: str | None = None
    ) -> TextCompletion:
        agent = str(prompt.metadata.get("agent") or "")
        effective_model = self._resolve_model(model, role=agent)
        return await super().complete_text(prompt, model=effective_model)

    async def complete_structured(
        self, prompt: PromptBundle, *, model: str | None = None
    ) -> Completion:
        agent = str(prompt.metadata.get("agent") or "")
        effective_model = self._resolve_model(model, role=agent)
        return await super().complete_structured(prompt, model=effective_model)
