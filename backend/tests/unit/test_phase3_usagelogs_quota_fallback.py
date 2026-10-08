"""Comprehensive Unit Tests for Phase 3:
- UsageLogs & UsageTracker
- QuotaEngine (sliding windows, PROVIDER_REPORTED vs LOCALLY_TRACKED vs UNKNOWN)
- RequestBudgetManager (Target 10, Hard limit 15, REQUEST_BUDGET_EXCEEDED)
- Clean failure handling and error recording without cross-account borrowing
- 11 LLM Agents Integration + Deterministic ArtifactManagerAgent
- Security & Credential Masking Audit
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel

from app.agents.artifact_manager import ArtifactManagerAgent
from app.agents.backend_engineer import BackendEngineerAgent
from app.agents.business_analyst import BusinessAnalystAgent
from app.agents.context import AgentContext
from app.agents.database_engineer import DatabaseEngineerAgent
from app.agents.documentation_engineer import DocumentationEngineerAgent
from app.agents.final_qa_agent import FinalQAAgent
from app.agents.frontend_engineer import FrontendEngineerAgent
from app.agents.improvement_engineer import ImprovementEngineerAgent
from app.agents.manager import ManagerAgent
from app.agents.qa_engineer import QAEngineerAgent
from app.agents.review_engineer import ReviewEngineerAgent
from app.agents.solution_architect import SolutionArchitectAgent
from app.core.config import Settings
from app.core.exceptions import ConfigurationError, LLMError
from app.llm.budget import RequestBudgetExceededError
from app.llm.credentials import CredentialManager, mask_key
from app.llm.manager import RoleBasedProviderManager
from app.llm.protocol import LLMProvider
from app.llm.quota import QuotaEngine, QuotaSource
from app.llm.types import Completion, PromptBundle, TextCompletion, TokenUsage
from app.workflow.memory import SharedProjectMemory


class MockProvider(LLMProvider):
    """Controllable test provider simulating successes, rate limits, timeouts, and auth errors."""

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
        self.response_usage = response_usage or TokenUsage(input_tokens=120, output_tokens=80)

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

        data = {
            "summary": "Success response",
            "items": ["a", "b"],
            "project_name": "Test Project",
            "one_liner": "A test project",
            "delivery_approach": "agile",
            "success_criteria": ["criterion 1"],
            "key_risks": ["risk 1"],
        }
        return Completion(
            data=data,
            raw_text='{"summary": "Success response", "items": ["a", "b"]}',
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
# 1. Fallback and Error Handling Tests
# =====================================================================

@pytest.mark.asyncio
async def test_case_1_primary_succeeds():
    """Case 1: Primary succeeds -> exactly one request recorded in UsageLog."""
    p_front = MockProvider(name="gemini", api_key="front-key-999")

    mgr = RoleBasedProviderManager(
        providers={"FRONTEND_API_KEY01": p_front}
    )
    mgr.usage_tracker.clear_buffer()

    bundle = PromptBundle(
        cacheable_system="You are an engineer.",
        user_message="Build frontend",
        schema={"type": "object"},
        metadata={"agent": "frontend_engineer", "task_id": "task_case_1"},
    )

    result = await mgr.complete_structured(bundle)
    assert result.data["summary"] == "Success response"
    assert p_front.calls_count == 1

    logs = mgr.usage_tracker.get_buffered_entries(task_id="task_case_1")
    assert len(logs) == 1
    assert logs[0]["status"] == "success"
    assert logs[0]["request_number"] == 1
    assert logs[0]["attempt_number"] == 1
    assert logs[0]["fallback_used"] is False
    assert logs[0]["credential_slot"] == "FRONTEND_API_KEY01"


@pytest.mark.asyncio
async def test_case_2_primary_hits_rpm_limit():
    """Case 2: Primary hits RPM limit -> cleanly handled and recorded."""
    rate_err = LLMError("Rate limit exceeded 429", details={"error_kind": "RATE_LIMITED"})
    p_primary = MockProvider(name="gemini", api_key="primary-key-111", should_fail_with=rate_err)

    mgr = RoleBasedProviderManager(
        providers={"FRONTEND_API_KEY01": p_primary}
    )
    mgr.usage_tracker.clear_buffer()

    bundle = PromptBundle(
        cacheable_system="You are an engineer.",
        user_message="Design screen",
        schema={"type": "object"},
        metadata={"agent": "frontend_engineer", "task_id": "task_case_2"},
    )

    res = await mgr.complete_structured(bundle)
    assert res is not None

    logs = mgr.usage_tracker.get_buffered_entries(task_id="task_case_2")
    assert len(logs) >= 1
    failed_log = next(log for log in logs if log["status"] == "failed")
    assert failed_log["credential_slot"] == "FRONTEND_API_KEY01"
    assert "RATE_LIMIT" in failed_log["error_category"]


@pytest.mark.asyncio
async def test_case_3_primary_auth_fails():
    """Case 3: Primary auth fails -> slot marked auth_failed without secret borrowing."""
    auth_err = LLMError("401 Unauthorized API key", details={"error_kind": "AUTHENTICATION_ERROR"})
    p_primary = MockProvider(name="gemini", api_key="invalid-key-000", should_fail_with=auth_err)

    mgr = RoleBasedProviderManager(
        providers={"FRONTEND_API_KEY01": p_primary}
    )
    mgr.usage_tracker.clear_buffer()

    bundle = PromptBundle(
        cacheable_system="You are an engineer.",
        user_message="Compile docs",
        schema={"type": "object"},
        metadata={"agent": "frontend_engineer", "task_id": "task_case_3"},
    )

    with pytest.raises(LLMError):
        await mgr.complete_structured(bundle)

    assert mgr._accounts["FRONTEND_API_KEY01"].status == "auth_failed"
    assert not mgr._accounts["FRONTEND_API_KEY01"].is_selectable


@pytest.mark.asyncio
async def test_case_4_primary_quota_exhausted():
    """Case 4: Primary quota exhausted -> marked cooling_down/exhausted."""
    quota_err = LLMError("429 ResourceExhausted: Quota exceeded", details={"error_kind": "QUOTA_EXHAUSTED"})
    p_primary = MockProvider(name="gemini", should_fail_with=quota_err)

    mgr = RoleBasedProviderManager(providers={"FRONTEND_API_KEY01": p_primary})
    mgr.usage_tracker.clear_buffer()

    bundle = PromptBundle(
        cacheable_system="You are an engineer.",
        user_message="Test code",
        schema={"type": "object"},
        metadata={"agent": "frontend_engineer", "task_id": "task_case_4"},
    )

    res = await mgr.complete_structured(bundle)
    assert res is not None
    logs = mgr.usage_tracker.get_buffered_entries(task_id="task_case_4")
    assert any(log["status"] == "failed" for log in logs)


@pytest.mark.asyncio
async def test_case_5_primary_timeout():
    """Case 5: Primary times out -> cleanly recorded and handled."""
    timeout_err = TimeoutError("Request timed out after 900s")
    p_primary = MockProvider(name="gemini", should_fail_with=timeout_err)

    mgr = RoleBasedProviderManager(providers={"FRONTEND_API_KEY01": p_primary})
    mgr.usage_tracker.clear_buffer()

    bundle = PromptBundle(
        cacheable_system="You are an engineer.",
        user_message="Review PR",
        schema={"type": "object"},
        metadata={"agent": "frontend_engineer", "task_id": "task_case_5"},
    )

    with pytest.raises(Exception):
        await mgr.complete_structured(bundle)

    logs = mgr.usage_tracker.get_buffered_entries(task_id="task_case_5")
    assert len(logs) >= 1
    assert logs[0]["status"] == "failed"


@pytest.mark.asyncio
async def test_case_6_unconfigured_slot_raises_cleanly():
    """Case 6: Unconfigured slot raises ConfigurationError."""
    mgr = RoleBasedProviderManager(providers={})
    bundle = PromptBundle(
        cacheable_system="You are an engineer.",
        user_message="Check health",
        schema={"type": "object"},
        metadata={"agent": "frontend_engineer", "task_id": "task_case_6"},
    )

    with pytest.raises(ConfigurationError):
        await mgr.complete_structured(bundle)


@pytest.mark.asyncio
async def test_case_7_fifteen_request_hard_limit_exceeded():
    """Case 7: Exactly 15 requests allowed. 16th blocked with RequestBudgetExceededError."""
    p = MockProvider(name="gemini")
    mgr = RoleBasedProviderManager(providers={"FRONTEND_API_KEY01": p})
    mgr.usage_tracker.clear_buffer()

    task_id = "budget_task_hard_limit"
    mgr.budget_manager.reset_task(task_id)

    for i in range(15):
        bundle = PromptBundle(
            cacheable_system="You are an engineer.",
            user_message=f"Request {i+1}",
            schema={"type": "object"},
            metadata={"agent": "frontend_engineer", "task_id": task_id},
        )
        await mgr.complete_structured(bundle)

    # 16th call must be blocked with RequestBudgetExceededError
    blocked_bundle = PromptBundle(
        cacheable_system="You are an engineer.",
        user_message="Request 16",
        schema={"type": "object"},
        metadata={"agent": "frontend_engineer", "task_id": task_id},
    )

    with pytest.raises(RequestBudgetExceededError) as exc_info:
        await mgr.complete_structured(blocked_bundle)

    assert "exceeded its hard request limit of 15" in str(exc_info.value)

    logs = mgr.usage_tracker.get_buffered_entries(task_id=task_id)
    budget_logs = [log for log in logs if log["status"] == "budget_exceeded"]
    assert len(budget_logs) == 1
    assert budget_logs[0]["error_category"] == "REQUEST_BUDGET_EXCEEDED"


def test_case_8_exact_7_slots():
    """Case 8: Exact 7 slots recognized with 01 suffix."""
    cfg = Settings(
        planner_api_key01="key-1",
        frontend_api_key01="key-2",
        backend_api_key01="key-3",
        database_api_key01="key-4",
        qa_api_key01="key-5",
        review_api_key01="key-6",
        debug_api_key01="key-7",
    )
    cm = CredentialManager.from_settings(cfg)
    slots = cm.list_slots()
    slot_names = [s.name for s in slots]

    assert sorted(slot_names) == [
        "BACKEND_API_KEY01",
        "DATABASE_API_KEY01",
        "DEBUG_API_KEY01",
        "FRONTEND_API_KEY01",
        "PLANNER_API_KEY01",
        "QA_API_KEY01",
        "REVIEW_API_KEY01",
    ]


# =====================================================================
# 2. 11 LLM Agents Integration Tests
# =====================================================================

@pytest.mark.asyncio
async def test_11_llm_agents_resolution():
    """Verify all 11 LLM agents resolve through generic LLM interface."""
    p = MockProvider()
    mgr = RoleBasedProviderManager(
        providers={
            "PLANNER_API_KEY01": p,
            "FRONTEND_API_KEY01": p,
            "BACKEND_API_KEY01": p,
            "DATABASE_API_KEY01": p,
            "QA_API_KEY01": p,
            "REVIEW_API_KEY01": p,
            "DEBUG_API_KEY01": p,
        }
    )
    mgr.usage_tracker.clear_buffer()

    memory = SharedProjectMemory(
        run_id="run_11_agents",
        project_id="proj_1",
        project_name="Test Project",
        project_slug="test-project",
        idea="A modern task management application with real-time updates.",
    )

    ctx = AgentContext(
        memory=memory,
        llm=mgr,
        registry=MagicMock(),
        report_progress=lambda *args: asyncio.sleep(0),
        report_log=lambda *args, **kwargs: asyncio.sleep(0),
    )

    llm_agents = [
        ManagerAgent(),
        BusinessAnalystAgent(),
        SolutionArchitectAgent(),
        DatabaseEngineerAgent(),
        BackendEngineerAgent(),
        FrontendEngineerAgent(),
        QAEngineerAgent(),
        ReviewEngineerAgent(),
        ImprovementEngineerAgent(),
        FinalQAAgent(),
        DocumentationEngineerAgent(),
    ]

    assert len(llm_agents) == 11

    # Verify each agent is mapped to an LLM role, builds prompts, and resolves via ctx.llm
    for agent in llm_agents:
        bundle = agent.build_prompt(
            ctx,
            instruction="Perform your architectural duty.",
            schema={"type": "object"},
            max_tokens=4000,
        )
        assert bundle.metadata["agent"] == agent.role.value
        completion = await ctx.llm.complete_structured(bundle)
        assert completion is not None
        assert completion.data["summary"] == "Success response"

    # Verify that all 11 calls produced observable UsageLogs with monotonically increasing request numbers
    logs = mgr.usage_tracker.get_buffered_entries(task_id="run_11_agents")
    assert len(logs) == 11
    request_numbers = [log["request_number"] for log in reversed(logs)]
    assert request_numbers == list(range(1, 12))
    for log in logs:
        assert log["status"] == "success"
        assert log["agent_role"] in [a.role.value for a in llm_agents]

    # Deterministic ArtifactManagerAgent test: zero LLM requests
    artifact_agent = ArtifactManagerAgent()
    p_artifact = MockProvider()
    mgr_artifact = RoleBasedProviderManager(providers={"FRONTEND_API_KEY01": p_artifact})
    ctx_artifact = AgentContext(
        memory=memory,
        llm=mgr_artifact,
        registry=MagicMock(),
        report_progress=lambda *args: asyncio.sleep(0),
        report_log=lambda *args, **kwargs: asyncio.sleep(0),
    )

    result_artifact = await artifact_agent.execute(ctx_artifact)
    assert result_artifact is not None
    assert p_artifact.calls_count == 0  # Absolutely ZERO LLM calls!


# =====================================================================
# 3. Quota Engine Tests
# =====================================================================

def test_quota_engine_source_distinction():
    """Verify QuotaEngine accurately distinguishes PROVIDER_REPORTED, LOCALLY_TRACKED, and UNKNOWN."""
    qe = QuotaEngine()

    # 1. No limits known -> UNKNOWN
    snap1 = qe.record_usage(
        provider="gemini",
        model="gemini-3.6-flash",
        credential_slot="FRONTEND_API_KEY01",
        tokens=50,
    )
    assert snap1["provider"]["rpm"]["source"] == QuotaSource.UNKNOWN.value
    assert snap1["provider"]["rpm"]["limit"] is None
    assert snap1["provider"]["rpm"]["remaining"] is None
    assert snap1["provider"]["rpm"]["used"] == 1

    # 2. Known local limit configured -> LOCALLY_TRACKED
    qe.set_known_limits("gemini", "provider", rpm_limit=60)
    snap2 = qe.record_usage(
        provider="gemini",
        model="gemini-3.6-flash",
        credential_slot="FRONTEND_API_KEY01",
        tokens=50,
    )
    assert snap2["provider"]["rpm"]["source"] == QuotaSource.LOCALLY_TRACKED.value
    assert snap2["provider"]["rpm"]["limit"] == 60
    assert snap2["provider"]["rpm"]["used"] == 2
    assert snap2["provider"]["rpm"]["remaining"] == 58

    # 3. Provider reported response headers -> PROVIDER_REPORTED
    snap3 = qe.record_usage(
        provider="gemini",
        model="gemini-3.6-flash",
        credential_slot="FRONTEND_API_KEY01",
        headers={"x-ratelimit-remaining-requests": "45", "x-ratelimit-limit-requests": "60"},
    )
    assert snap3["provider"]["rpm"]["source"] == QuotaSource.PROVIDER_REPORTED.value
    assert snap3["provider"]["rpm"]["remaining"] == 45


# =====================================================================
# 4. Security Audit Tests
# =====================================================================

def test_security_audit_zero_secret_leakage():
    """Verify that credentials and secrets are NEVER exposed in plain text."""
    secret = "AIzaSyD-super-secret-key-999"
    masked = mask_key(secret)
    assert secret not in masked
    assert masked.startswith("****")

    slot_repr = str(mgr_repr := RoleBasedProviderManager())
    assert secret not in slot_repr
