"""Model and Provider Routing.

Decouples agent identities from specific providers, models, and credentials.
Determines:
  1. Primary Provider (e.g. 'gemini', 'openai', 'mistral', 'github_models', 'groq')
  2. Model Name (e.g. 'gemini-3.6-flash', 'gpt-4o-mini', 'mistral-large-latest')
  3. Credential Slot Name (e.g. 'FRONTEND_API_KEY', 'BACKEND_API_KEY')
  4. Fallback Model and Provider Chains
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.config import Settings
from app.core.config import settings as default_settings
from app.core.enums import AgentRole, TaskKind


@dataclass(slots=True, frozen=True)
class RouteTarget:
    """A specific execution attempt target in the fallback chain."""

    provider: str
    model: str
    credential_slot: str
    step_description: str = ""


@dataclass(slots=True, frozen=True)
class RouteDecision:
    """The resolved execution target for a task or agent."""

    agent_role: str
    task_kind: TaskKind
    provider: str
    model: str
    credential_slot: str
    fallback_models: tuple[str, ...] = ()
    fallback_providers: tuple[str, ...] = ()


AGENT_TASK_KINDS: dict[AgentRole, TaskKind] = {
    AgentRole.MANAGER: TaskKind.REASONING,
    AgentRole.BUSINESS_ANALYST: TaskKind.REASONING,
    AgentRole.SOLUTION_ARCHITECT: TaskKind.REASONING,
    AgentRole.DATABASE_ENGINEER: TaskKind.CODE_GENERATION,
    AgentRole.BACKEND_ENGINEER: TaskKind.CODE_GENERATION,
    AgentRole.FRONTEND_ENGINEER: TaskKind.CODE_GENERATION,
    AgentRole.QA_ENGINEER: TaskKind.CODE_GENERATION,
    AgentRole.REVIEW_ENGINEER: TaskKind.REVIEW,
    AgentRole.IMPROVEMENT_ENGINEER: TaskKind.REVIEW,
    AgentRole.FINAL_QA: TaskKind.CODE_GENERATION,
    AgentRole.DOCUMENTATION_ENGINEER: TaskKind.DOCUMENTATION,
    AgentRole.ARTIFACT_MANAGER: TaskKind.SUMMARY,
}


class ModelRouter:
    """Config-driven router assigning providers, models, and slots to requests."""

    def __init__(self, config: Settings | None = None, *, settings: Settings | None = None) -> None:
        self.config = settings or config or default_settings

    def task_kind_for_role(self, role: AgentRole | str) -> TaskKind:
        if isinstance(role, AgentRole):
            return AGENT_TASK_KINDS.get(role, TaskKind.CODE_GENERATION)
        try:
            enum_role = AgentRole(role)
            return AGENT_TASK_KINDS.get(enum_role, TaskKind.CODE_GENERATION)
        except ValueError:
            return TaskKind.CODE_GENERATION

    def route(
        self,
        agent: AgentRole | str | None = None,
        *,
        agent_role: AgentRole | str | None = None,
        task_kind: TaskKind | None = None,
        preferred_provider: str | None = None,
        preferred_model: str | None = None,
    ) -> RouteDecision:
        """Calculate the target provider, model, slot, and fallbacks for an agent."""
        target_role = agent if agent is not None else agent_role
        if target_role is None:
            raise ValueError("Must provide either agent or agent_role")
        role_str = target_role.value if isinstance(target_role, AgentRole) else str(target_role)
        kind = task_kind or self.task_kind_for_role(target_role)
        cfg = self.config

        # 1. Determine Provider
        provider = preferred_provider or cfg.default_provider
        # Normalize provider string
        provider = provider.lower().strip()

        # 2. Determine Model based on provider and config
        if preferred_model:
            model = preferred_model
        elif provider == "openai":
            model = cfg.openai_model
        elif provider == "mistral":
            model = cfg.mistral_model
        elif provider in ("github", "github_models"):
            model = cfg.github_models_model
        elif provider == "groq":
            model = cfg.groq_model
        elif provider == "deepseek":
            model = cfg.deepseek_primary_model
        elif provider == "siliconflow":
            from app.llm.siliconflow import get_siliconflow_catalog
            catalog = get_siliconflow_catalog(cfg)
            model = catalog.select_model(
                api_key=cfg.siliconflow_api_key,
                explicit_model=preferred_model or cfg.siliconflow_model,
                agent_role=target_role,
                base_url=cfg.siliconflow_base_url,
            )
        else:
            # Default to authoritative Gemini model (gemini-3.6-flash)
            model = cfg.gemini_model

        # 3. Determine Primary Credential Slot
        normalized_role = role_str.lower()
        if "artifact_manager" in normalized_role:
            slot = "none"
        elif "planner" in normalized_role or "manager" in normalized_role or "analyst" in normalized_role or "architect" in normalized_role:
            slot = "PLANNER_API_KEY01"
        elif "frontend" in normalized_role or "documentation" in normalized_role:
            slot = "FRONTEND_API_KEY01"
        elif "backend" in normalized_role:
            slot = "BACKEND_API_KEY01"
        elif "database" in normalized_role:
            slot = "DATABASE_API_KEY01"
        elif "final_qa" in normalized_role:
            slot = "DEBUG_API_KEY01"
        elif "qa" in normalized_role:
            slot = "QA_API_KEY01"
        elif "debug" in normalized_role:
            slot = "DEBUG_API_KEY01"
        elif "review" in normalized_role:
            slot = "REVIEW_API_KEY01"
        elif "improvement" in normalized_role:
            slot = "REVIEW_API_KEY01"
        else:
            slot = "BACKEND_API_KEY01"

        # 4. Determine Fallback Models and Providers
        fallback_models: list[str] = []
        if provider == "gemini":
            fallback_models = []
        elif provider == "openai":
            fallback_models = ["gpt-4o", "gpt-4o-mini"]
        elif provider == "mistral":
            fallback_models = ["mistral-large-latest", "codestral-latest", "mistral-small-latest"]
        elif provider == "groq":
            fallback_models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
        elif provider == "siliconflow":
            from app.llm.siliconflow import get_siliconflow_catalog
            catalog = get_siliconflow_catalog(cfg)
            eligible = catalog.get_eligible_free_chat_models(
                api_key=cfg.siliconflow_api_key,
                base_url=cfg.siliconflow_base_url,
            )
            fallback_models = [m.id for m in eligible if m.id != model]
            if not fallback_models and model != "Qwen/Qwen2.5-7B-Instruct":
                fallback_models = ["Qwen/Qwen2.5-7B-Instruct"]

        fallback_providers: list[str] = []
        candidate_providers = ["gemini", "openai", "mistral", "github_models", "groq"]
        if getattr(cfg, "siliconflow_api_key", None):
            candidate_providers.append("siliconflow")
        for p in candidate_providers:
            if p != provider:
                fallback_providers.append(p)

        return RouteDecision(
            agent_role=role_str,
            task_kind=kind,
            provider=provider,
            model=model,
            credential_slot=slot,
            fallback_models=tuple(fallback_models),
            fallback_providers=tuple(fallback_providers),
        )

    def default_model_for_provider(self, provider: str) -> str:
        cfg = self.config
        p = provider.lower().strip()
        if p == "openai":
            return cfg.openai_model
        if p == "mistral":
            return cfg.mistral_model
        if p in ("github", "github_models"):
            return cfg.github_models_model
        if p == "groq":
            return cfg.groq_model
        if p == "deepseek":
            return cfg.deepseek_primary_model
        if p == "siliconflow":
            from app.llm.siliconflow import get_siliconflow_catalog
            catalog = get_siliconflow_catalog(cfg)
            return catalog.select_model(
                api_key=cfg.siliconflow_api_key,
                explicit_model=cfg.siliconflow_model,
                base_url=cfg.siliconflow_base_url,
            )
        return cfg.gemini_model

    def get_fallback_plan(
        self,
        decision: RouteDecision,
        backup_slots: list[str] | None = None,
    ) -> list[RouteTarget]:
        """Construct ordered fallback targets according to Priority 1 -> 2 -> 3 -> 4 -> 5.
        
        1. Current provider + current model + primary credential
        2. Same provider + same model + next healthy credential (backup slots)
        3. Same provider + configured fallback model
        4. Next configured provider + configured model
        5. Next healthy backup credential/provider combination
        """
        plan: list[RouteTarget] = []
        seen: set[tuple[str, str, str]] = set()

        def add_target(p: str, m: str, slot: str, desc: str) -> None:
            key = (p.lower(), m.lower(), slot)
            if key not in seen:
                seen.add(key)
                plan.append(RouteTarget(provider=p, model=m, credential_slot=slot, step_description=desc))

        # 1. Primary target
        add_target(decision.provider, decision.model, decision.credential_slot, "Primary Target")

        # 2. Same provider + same model + backup credentials
        for backup_slot in (backup_slots or []):
            add_target(
                decision.provider,
                decision.model,
                backup_slot,
                f"Same provider/model on backup credential {backup_slot}",
            )

        # 3. Same provider + configured fallback models
        for fb_model in decision.fallback_models:
            add_target(
                decision.provider,
                fb_model,
                decision.credential_slot,
                f"Same provider with fallback model {fb_model}",
            )

        # 4. Next configured providers + configured model
        for fb_prov in decision.fallback_providers:
            fb_model = self.default_model_for_provider(fb_prov)
            add_target(
                fb_prov,
                fb_model,
                decision.credential_slot,
                f"Fallback provider {fb_prov} ({fb_model})",
            )

        # 5. Next healthy backup credential / provider combinations
        for fb_prov in decision.fallback_providers:
            fb_model = self.default_model_for_provider(fb_prov)
            for backup_slot in (backup_slots or []):
                add_target(
                    fb_prov,
                    fb_model,
                    backup_slot,
                    f"Fallback provider {fb_prov} on backup credential {backup_slot}",
                )

        return plan
