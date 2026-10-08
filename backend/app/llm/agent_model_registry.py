"""Agent Model Registry & Model Capability Matrix.

Maps each agent role to one of the 7 dedicated Gemini primary credential slots
and defines the model capability registry.

7 DEDICATED GEMINI PRIMARY CREDENTIAL SLOTS:
  1. PLANNER_API_KEY01: Manager, Business Analyst, Solution Architect
  2. FRONTEND_API_KEY01: Frontend Engineer, Documentation Engineer
  3. BACKEND_API_KEY01: Backend Engineer
  4. DATABASE_API_KEY01: Database Engineer
  5. QA_API_KEY01: QA Engineer
  6. REVIEW_API_KEY01: Review Engineer, Improvement Engineer (shared)
  7. DEBUG_API_KEY01: Final QA Agent, Self-repair/debug functionality

Deterministic (0 LLM credentials):
  - Artifact Manager (ZERO LLM calls)

ACTIVE GEMINI MODEL:
  - gemini-3.6-flash ONLY
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.core.enums import AgentRole

if TYPE_CHECKING:
    pass

#: Maps each agent role to one of the 7 dedicated Gemini credential slots.
AGENT_PROVIDER_SLOT: dict[AgentRole, str] = {
    # 1. ManagerAgent -> PLANNER_API_KEY01
    AgentRole.MANAGER: "PLANNER_API_KEY01",
    # 2. BusinessAnalystAgent -> PLANNER_API_KEY01
    AgentRole.BUSINESS_ANALYST: "PLANNER_API_KEY01",
    # 3. SolutionArchitectAgent -> PLANNER_API_KEY01
    AgentRole.SOLUTION_ARCHITECT: "PLANNER_API_KEY01",

    # 4. FrontendEngineerAgent -> FRONTEND_API_KEY01
    AgentRole.FRONTEND_ENGINEER: "FRONTEND_API_KEY01",
    # 5. DocumentationEngineerAgent -> FRONTEND_API_KEY01
    AgentRole.DOCUMENTATION_ENGINEER: "FRONTEND_API_KEY01",

    # 6. BackendEngineerAgent -> BACKEND_API_KEY01
    AgentRole.BACKEND_ENGINEER: "BACKEND_API_KEY01",

    # 7. DatabaseEngineerAgent -> DATABASE_API_KEY01
    AgentRole.DATABASE_ENGINEER: "DATABASE_API_KEY01",

    # 8. QAEngineerAgent -> QA_API_KEY01
    AgentRole.QA_ENGINEER: "QA_API_KEY01",

    # 9. ReviewEngineerAgent -> REVIEW_API_KEY01
    AgentRole.REVIEW_ENGINEER: "REVIEW_API_KEY01",
    # 10. ImprovementEngineerAgent -> REVIEW_API_KEY01 (shares Review slot)
    AgentRole.IMPROVEMENT_ENGINEER: "REVIEW_API_KEY01",

    # 11. FinalQAAgent -> DEBUG_API_KEY01
    AgentRole.FINAL_QA: "DEBUG_API_KEY01",

    # 12. ArtifactManagerAgent is deterministic — ZERO LLM calls, no LLM slot needed
    AgentRole.ARTIFACT_MANAGER: "none",
}

SLOT_DISPLAY_NAMES: dict[str, str] = {
    "PLANNER_API_KEY01": "Planner Slot",
    "FRONTEND_API_KEY01": "Frontend Slot",
    "BACKEND_API_KEY01": "Backend Slot",
    "DATABASE_API_KEY01": "Database Slot",
    "QA_API_KEY01": "QA Slot",
    "REVIEW_API_KEY01": "Review / Improvement Slot",
    "DEBUG_API_KEY01": "Final QA / Debug Slot",
    "none": "Deterministic",
}

SLOT_ROLE_GROUPS: dict[str, str] = {
    "PLANNER_API_KEY01": "Manager / Business Analyst / Solution Architect",
    "FRONTEND_API_KEY01": "Frontend / Documentation",
    "BACKEND_API_KEY01": "Backend Engineer",
    "DATABASE_API_KEY01": "Database Engineer",
    "QA_API_KEY01": "QA Engineer",
    "REVIEW_API_KEY01": "Review Engineer / Improvement Engineer",
    "DEBUG_API_KEY01": "Final QA / Debug / Repair / Frontend Rescue",
}

#: Authoritative default model mapping for each of the 7 slots
SLOT_DEFAULT_MODELS: dict[str, str] = {
    "PLANNER_API_KEY01": "nvidia/nemotron-3-super-120b-a12b",
    "FRONTEND_API_KEY01": "gemini-3.6-flash",
    "BACKEND_API_KEY01": "gemini-3.6-flash",
    "DATABASE_API_KEY01": "gemini-3.6-flash",
    "QA_API_KEY01": "nvidia/nemotron-3-super-120b-a12b",
    "REVIEW_API_KEY01": "nvidia/nemotron-3-super-120b-a12b",
    "DEBUG_API_KEY01": "nvidia/nemotron-3-super-120b-a12b",
    "none": "deterministic",
}

#: Authoritative default model mapping for each agent role
ROLE_DEFAULT_MODELS: dict[AgentRole, str] = {
    AgentRole.MANAGER: "nvidia/nemotron-3-super-120b-a12b",
    AgentRole.BUSINESS_ANALYST: "nvidia/nemotron-3-super-120b-a12b",
    AgentRole.SOLUTION_ARCHITECT: "nvidia/nemotron-3-super-120b-a12b",
    AgentRole.FRONTEND_ENGINEER: "gemini-3.6-flash",
    AgentRole.DOCUMENTATION_ENGINEER: "gemini-3.6-flash",
    AgentRole.BACKEND_ENGINEER: "gemini-3.6-flash",
    AgentRole.DATABASE_ENGINEER: "gemini-3.6-flash",
    AgentRole.QA_ENGINEER: "nvidia/nemotron-3-super-120b-a12b",
    AgentRole.REVIEW_ENGINEER: "nvidia/nemotron-3-super-120b-a12b",
    AgentRole.IMPROVEMENT_ENGINEER: "nvidia/nemotron-3-super-120b-a12b",
    AgentRole.FINAL_QA: "nvidia/nemotron-3-super-120b-a12b",
    AgentRole.ARTIFACT_MANAGER: "deterministic",
}

#: Authoritative fallback models
DEFAULT_GEMINI_FALLBACK_CHAIN: tuple[str, ...] = (
    "gemini-3.6-flash",
)


@dataclass(frozen=True, slots=True)
class ModelCapability:
    """Capability specification for an LLM model."""

    model_id: str
    display_name: str
    tier: str  # "flash" | "pro" | "super"
    stability: str  # "ga" | "preview"
    supports_tools: bool
    supports_structured_output: bool
    supports_vision: bool
    supports_reasoning: bool
    priority: int
    fallback_priority: int
    max_output_tokens: int


#: Official capability specifications for supported models
MODEL_REGISTRY: dict[str, ModelCapability] = {
    "gemini-3.6-flash": ModelCapability(
        model_id="gemini-3.6-flash",
        display_name="Gemini 3.6 Flash",
        tier="flash",
        stability="ga",
        supports_tools=True,
        supports_structured_output=True,
        supports_vision=True,
        supports_reasoning=True,
        priority=1,
        fallback_priority=1,
        max_output_tokens=65536,
    ),
    "nvidia/nemotron-3-super-120b-a12b": ModelCapability(
        model_id="nvidia/nemotron-3-super-120b-a12b",
        display_name="NVIDIA Nemotron-3 Super 120B",
        tier="super",
        stability="ga",
        supports_tools=True,
        supports_structured_output=True,
        supports_vision=False,
        supports_reasoning=True,
        priority=1,
        fallback_priority=1,
        max_output_tokens=65536,
    ),
}
# Backward compatibility alias
GEMINI_MODEL_REGISTRY = MODEL_REGISTRY


def get_model_capability(model_id: str) -> ModelCapability | None:
    """Retrieve capability metadata for a given model ID."""
    return MODEL_REGISTRY.get(model_id)


def validate_task_compatibility(model_id: str, prompt: Any) -> tuple[bool, str]:
    """Verify that a candidate fallback model satisfies all requirements of the prompt."""
    cap = GEMINI_MODEL_REGISTRY.get(model_id)
    if cap is None:
        # Unknown/custom model: allow execution
        return True, ""

    if getattr(prompt, "schema", None) is not None and not cap.supports_structured_output:
        return False, f"Model '{model_id}' does not support structured output required by prompt"

    metadata = getattr(prompt, "metadata", {}) or {}
    if metadata.get("requires_vision") and not cap.supports_vision:
        return False, f"Model '{model_id}' does not support vision processing"

    if metadata.get("requires_tools") and not cap.supports_tools:
        return False, f"Model '{model_id}' does not support function/tool calling"

    return True, ""


def provider_slot_for(role: AgentRole) -> str:
    """Return the provider slot name for a given agent role.

    Returns 'none' for deterministic agents (Artifact Manager).
    Returns 'FRONTEND_API_KEY01' as a safe default for unknown roles.
    """
    return AGENT_PROVIDER_SLOT.get(role, "FRONTEND_API_KEY01")


def provider_slot_for_str(role_str: str) -> str:
    """String-keyed variant used in prompt metadata resolution."""
    try:
        role = AgentRole(role_str)
    except ValueError:
        return "FRONTEND_API_KEY01"
    return provider_slot_for(role)


def model_for_slot(slot: str, config: Any = None) -> str:
    """Return the authoritative model name for a credential slot."""
    if config and hasattr(config, "get_slot_model"):
        return config.get_slot_model(slot)
    return SLOT_DEFAULT_MODELS.get(slot.upper().strip(), "gemini-3.6-flash")


def model_for_role(role: AgentRole, config: Any = None) -> str:
    """Return the authoritative model name for an agent role."""
    if config and hasattr(config, "get_role_model"):
        return config.get_role_model(role.value)
    slot = provider_slot_for(role)
    return model_for_slot(slot, config)


def model_for_role_str(role_str: str, config: Any = None) -> str:
    """String-keyed variant for resolving an agent's assigned model."""
    try:
        role = AgentRole(role_str)
        return model_for_role(role, config)
    except ValueError:
        slot = provider_slot_for_str(role_str)
        return model_for_slot(slot, config)


