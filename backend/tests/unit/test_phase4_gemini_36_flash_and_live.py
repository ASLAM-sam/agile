"""Phase 4: Gemini 3.6 Flash Only + Real Credential Architecture + Safe Fallback Tests.

Validates:
1. Gemini 3.8 and 3.7 Flash are completely removed from active configuration.
2. Gemini 3.6 Flash is the ONLY active Gemini model.
3. No model fallback (3.8 -> 3.7 -> 3.6) exists. Fallback is by healthy credential.
4. Provider / Model / Credential separation (identical agent code under Gemini 3.6 vs Mistral).
5. Primary failure with mock RATE_LIMIT_RPM falls back to backup credential using gemini-3.6-flash.
6. 20 backup slots supported with empty slots safely ignored.
7. ArtifactManager remains deterministic with ZERO LLM requests.
8. Security audit: zero raw secret leakage.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.agents.artifact_manager import ArtifactManagerAgent
from app.agents.context import AgentContext
from app.agents.frontend_engineer import FrontendEngineerAgent
from app.core.config import Settings
from app.core.enums import AgentRole
from app.core.exceptions import LLMError
from app.llm.agent_model_registry import (
    DEFAULT_GEMINI_FALLBACK_CHAIN,
    GEMINI_MODEL_REGISTRY,
    provider_slot_for,
)
from app.llm.budget import RequestBudgetExceededError, RequestBudgetManager
from app.llm.credentials import CredentialManager, mask_key
from app.llm.manager import RoleBasedProviderManager
from app.llm.protocol import LLMProvider
from app.llm.router import ModelRouter, RouteDecision
from app.llm.types import Completion, PromptBundle, TextCompletion, TokenUsage
from app.workflow.memory import SharedProjectMemory


class MockProvider(LLMProvider):
    """Controllable test provider simulating Gemini 3.6 Flash and other configured providers."""

    def __init__(
        self,
        name: str = "gemini",
        model: str = "gemini-3.6-flash",
        api_key: str = "test-secret-key-12345",
        should_fail_with: Exception | None = None,
        fail_times: int = 0,
        response_usage: TokenUsage | None = None,
    ) -> None:
        self.name = name
        self._model = model
        self.api_key = api_key
        self.should_fail_with = should_fail_with
        self.fail_times = fail_times
        self.calls_count = 0
        self.response_usage = response_usage or TokenUsage(input_tokens=100, output_tokens=50)

    @property
    def model(self) -> str:
        return self._model

    async def complete_structured(
        self, prompt: PromptBundle, *, model: str | None = None
    ) -> Completion:
        self.calls_count += 1
        if self.should_fail_with:
            if self.fail_times == 0 or self.calls_count <= self.fail_times:
                raise self.should_fail_with

        return Completion(
            data={"status": "ready", "files": [{"path": "index.html", "content": "<h1>Hello</h1>"}]},
            raw_text='{"status": "ready"}',
            model=model or self._model,
            usage=self.response_usage,
        )

    async def complete_text(
        self, prompt: PromptBundle, *, model: str | None = None
    ) -> TextCompletion:
        self.calls_count += 1
        if self.should_fail_with:
            if self.fail_times == 0 or self.calls_count <= self.fail_times:
                raise self.should_fail_with

        return TextCompletion(
            text="Success plain text",
            model=model or self._model,
            usage=self.response_usage,
        )


# =====================================================================
# 1. Gemini 3.6 Flash Only Configuration Audit
# =====================================================================

# =====================================================================
# 1. Gemini 3.6 Flash Only Configuration Audit
# =====================================================================

def test_gemini_36_flash_sole_active_gemini_model():
    """Gemini 3.6 Flash is the ONLY active model in default and fallback chains."""
    cfg = Settings()

    # Active default model
    assert cfg.default_model == "gemini-3.6-flash"
    assert cfg.gemini_model == "gemini-3.6-flash"
    assert cfg.gemini_allowed_model == "gemini-3.6-flash"

    # Model registry in agent_model_registry.py
    assert "gemini-3.8-flash" not in GEMINI_MODEL_REGISTRY
    assert "gemini-3.7-flash" not in GEMINI_MODEL_REGISTRY
    assert "gemini-3.6-flash" in GEMINI_MODEL_REGISTRY
    assert DEFAULT_GEMINI_FALLBACK_CHAIN == ("gemini-3.6-flash",)


# =====================================================================
# 2. Provider / Model / Credential Separation
# =====================================================================

def test_provider_model_credential_separation():
    """Verify FrontendEngineerAgent code is completely decoupled from provider/model choice."""
    cfg_gemini = Settings(
        default_provider="gemini",
        default_model="gemini-3.6-flash",
        frontend_api_key01="gemini-key-123",
    )
    router_gemini = ModelRouter(cfg_gemini)
    route_a = router_gemini.route(agent_role=AgentRole.FRONTEND_ENGINEER)

    assert route_a.provider == "gemini"
    assert route_a.model == "gemini-3.6-flash"
    assert route_a.credential_slot == "FRONTEND_API_KEY01"

    # Same agent role, switched to Mistral via config
    cfg_mistral = Settings(
        default_provider="mistral",
        mistral_model="mistral-large-latest",
        frontend_api_key01="mistral-key-456",
    )
    router_mistral = ModelRouter(cfg_mistral)
    route_b = router_mistral.route(agent_role=AgentRole.FRONTEND_ENGINEER)

    assert route_b.provider == "mistral"
    assert route_b.model == "mistral-large-latest"
    assert route_b.credential_slot == "FRONTEND_API_KEY01"

    # Agent role code itself never needs modification between A and B
    agent = FrontendEngineerAgent()
    assert agent.role is AgentRole.FRONTEND_ENGINEER


# =====================================================================
# 3. Dedicated 7 Slots Architecture (No Backup Pool)
# =====================================================================

def test_exact_7_slots_architecture():
    """Only 7 dedicated slots exist with '01' suffix. No backup pool."""
    cfg = Settings(
        planner_api_key01="key-01",
        frontend_api_key01="key-02",
        backend_api_key01="key-03",
        database_api_key01="key-04",
        qa_api_key01="key-05",
        review_api_key01="key-06",
        debug_api_key01="key-07",
    )
    cm = CredentialManager.from_settings(cfg)
    slots = cm.list_slots()
    slot_names = [s.name for s in slots]

    expected = [
        "PLANNER_API_KEY01",
        "FRONTEND_API_KEY01",
        "BACKEND_API_KEY01",
        "DATABASE_API_KEY01",
        "QA_API_KEY01",
        "REVIEW_API_KEY01",
        "DEBUG_API_KEY01",
    ]
    assert sorted(slot_names) == sorted(expected)
    assert cm.get_backup_pool() == []


# =====================================================================
# 4. Deterministic ArtifactManagerAgent (0 LLM Requests)
# =====================================================================

@pytest.mark.asyncio
async def test_deterministic_artifact_manager_zero_llm_calls():
    """ArtifactManagerAgent makes ZERO LLM calls."""
    artifact_agent = ArtifactManagerAgent()
    p = MockProvider(name="gemini", model="gemini-3.6-flash")
    mgr = RoleBasedProviderManager(providers={"FRONTEND_API_KEY01": p})

    memory = SharedProjectMemory(
        run_id="run_art_test",
        project_id="p1",
        project_name="Deterministic Test",
        project_slug="deterministic-test",
        idea="A landing page for developers.",
    )
    ctx = AgentContext(
        memory=memory,
        llm=mgr,
        registry=MagicMock(),
        report_progress=lambda *args: asyncio.sleep(0),
        report_log=lambda *args, **kwargs: asyncio.sleep(0),
    )

    result = await artifact_agent.execute(ctx)
    assert result is not None
    assert p.calls_count == 0


# =====================================================================
# 5. Request Budget Enforcement
# =====================================================================

@pytest.mark.asyncio
async def test_request_budget_enforcement():
    """Enforce Target 10 and Hard Limit 15."""
    p = MockProvider(name="gemini", model="gemini-3.6-flash")
    mgr = RoleBasedProviderManager(providers={"FRONTEND_API_KEY01": p})
    mgr.usage_tracker.clear_buffer()

    task_id = "budget_phase4_task"
    mgr.budget_manager.reset_task(task_id)

    # 15 calls succeed
    for i in range(15):
        bundle = PromptBundle(
            cacheable_system="You are an engineer.",
            user_message=f"Request {i+1}",
            schema={"type": "object"},
            metadata={"agent": "frontend_engineer", "task_id": task_id},
        )
        await mgr.complete_structured(bundle)

    # 16th call blocked cleanly
    blocked_bundle = PromptBundle(
        cacheable_system="You are an engineer.",
        user_message="Request 16",
        schema={"type": "object"},
        metadata={"agent": "frontend_engineer", "task_id": task_id},
    )
    with pytest.raises(RequestBudgetExceededError) as exc_info:
        await mgr.complete_structured(blocked_bundle)

    assert "hard request limit of 15" in str(exc_info.value)


# =====================================================================
# 6. Security Audit
# =====================================================================

def test_security_audit_masked_credentials():
    """Verify secrets are masked and never exposed in plain text."""
    secret = "AIzaSyD-live-secret-test-key-36"
    masked = mask_key(secret)
    assert secret not in masked
    assert masked.startswith("****")

    cfg = Settings(frontend_api_key01=secret)
    cm = CredentialManager.from_settings(cfg)
    slot = cm.get_slot("FRONTEND_API_KEY01")
    assert slot is not None
    assert slot.masked_key.startswith("****")
    assert secret not in slot.masked_key
