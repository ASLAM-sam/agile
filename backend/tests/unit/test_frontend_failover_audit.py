"""Master Frontend 7-Slot Architecture & Quality Assurance Audit Test Suite.

Covers:
1. Frontend primary succeeds normally (1 request, FRONTEND_API_KEY01, budget incremented).
2. Primary returns 503 (SERVER_ERROR) -> bounded retry on same slot, 2 requests counted, both in UsageLogs.
3. Primary returns RPM rate limit (429) -> marked cooling down, halts cleanly without cross-account borrowing.
4. Primary returns RPD quota exhaustion (429) -> marked cooling down for window, halts cleanly.
5. Primary returns 401 authentication error -> marked auth_failed, fail-fast without retry.
6. All attempts fail -> bounded retry (max 1 retry), stops cleanly, no runaway loop.
7. No cross-role borrowing: Failing frontend NEVER calls or consumes backend/planner/etc. slots.
8. Request budget hard cap (15 requests max): Request #16 is strictly BLOCKED.
9. No false fallback: 400 Bad Request / Schema violation halts immediately without cycling.
10. Test-only safe fault-injection mechanism (FRONTEND_PRIMARY_FAILURE_TEST).
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

from app.core.config import Settings
from app.core.enums import AgentRole
from app.llm.budget import RequestBudgetExceededError, get_budget_manager
from app.llm.errors import AllProvidersFailed, GeminiAllAccountsUnavailableError, LLMErrorCategory
from app.llm.manager import RoleBasedProviderManager
from app.llm.types import Completion, PromptBundle, TextCompletion, TokenUsage
from app.llm.usage import get_usage_tracker


class MockProvider:
    """Mock provider recording calls and simulating specific errors or successes."""

    def __init__(
        self,
        *,
        name: str = "gemini",
        model: str = "gemini-3.6-flash",
        slot: str = "FRONTEND_API_KEY01",
        error: Exception | None = None,
        errors: list[Exception] | None = None,
        response_text: str = "Frontend scaffold generated successfully",
    ) -> None:
        self.name = name
        self.model = model
        self.slot = slot
        self.error = error
        self.errors = list(errors) if errors else []
        self.response_text = response_text
        self.calls: list[PromptBundle] = []
        self.model_calls: list[str] = []

    async def complete_text(self, prompt: PromptBundle, *, model: str | None = None) -> TextCompletion:
        target_model = model or self.model
        self.calls.append(prompt)
        self.model_calls.append(target_model)
        if self.errors:
            err = self.errors.pop(0)
            if err is not None:
                raise err
        elif self.error is not None:
            raise self.error
        return TextCompletion(
            text=self.response_text,
            usage=TokenUsage(input_tokens=100, output_tokens=50),
            model=target_model,
        )

    async def complete_structured(self, prompt: PromptBundle, *, model: str | None = None) -> Completion:
        target_model = model or self.model
        self.calls.append(prompt)
        self.model_calls.append(target_model)
        if self.errors:
            err = self.errors.pop(0)
            if err is not None:
                raise err
        elif self.error is not None:
            raise self.error
        return Completion(
            data={"status": "success", "files": ["index.html", "css/styles.css", "js/app.js"]},
            usage=TokenUsage(input_tokens=100, output_tokens=50),
            model=target_model,
        )

    async def aclose(self) -> None:
        pass


def make_test_prompt(task_id: str = "task_audit_01", structured: bool = False) -> PromptBundle:
    return PromptBundle(
        cacheable_system="You are a frontend engineer.",
        user_message="Generate modern task manager web app",
        schema={"type": "object"} if structured else None,
        metadata={
            "agent": "FrontendEngineerAgent",
            "task_id": task_id,
            "run_id": f"run_{task_id}",
        },
    )


def make_audit_manager(
    providers: dict[str, MockProvider],
    target_budget: int = 10,
    hard_max: int = 15,
) -> RoleBasedProviderManager:
    config = MagicMock(spec=Settings)
    config.llm_cache_enabled = False
    config.llm_cache_max_entries = 512
    config.llm_cache_ttl_seconds = 3600.0
    config.llm_max_retries = 3
    config.llm_timeout_seconds = 30.0
    config.target_requests_per_task = target_budget
    config.hard_max_requests_per_task = hard_max
    config.gemini_model = "gemini-3.6-flash"
    config.gemini_fallback_models = []
    config.siliconflow_api_key = None
    config.get_backup_credentials = lambda: []

    mgr = RoleBasedProviderManager(config=config, providers=providers)  # type: ignore[arg-type]
    return mgr


# =============================================================================
# AUDIT TESTS
# =============================================================================

@pytest.mark.asyncio
async def test_1_frontend_primary_succeeds_normally():
    """TEST 1: Frontend primary succeeds normally with 1 request."""
    primary = MockProvider(name="gemini", model="gemini-3.6-flash", slot="FRONTEND_API_KEY01")

    mgr = make_audit_manager({"FRONTEND_API_KEY01": primary})

    task_id = "test_primary_success"
    prompt = make_test_prompt(task_id=task_id)

    res = await mgr.complete_text(prompt)

    assert "Frontend scaffold" in res.text
    assert len(primary.calls) == 1

    # Budget was incremented to 1
    status = mgr.budget_manager.get_status(task_id)
    assert status["current_request_number"] == 1

    # UsageLog was recorded
    logs = [log for log in mgr.usage_tracker._buffer if log.get("task_id") == task_id]
    assert len(logs) == 1
    assert logs[0]["status"] == "success"
    assert logs[0]["credential_slot"] == "FRONTEND_API_KEY01"
    assert logs[0]["fallback_used"] is False
    assert logs[0]["request_number"] == 1


@pytest.mark.asyncio
async def test_2_frontend_primary_503_transient_retry_success():
    """TEST 2: Primary returns 503 SERVER_ERROR on attempt 1, retries and succeeds on attempt 2."""
    class Mock503Error(Exception):
        error_kind = "SERVER_ERROR"
        status_code = 503

    primary = MockProvider(
        name="gemini",
        model="gemini-3.6-flash",
        slot="FRONTEND_API_KEY01",
        errors=[Mock503Error("503 Service Unavailable"), None],
        response_text="Recovered on retry",
    )

    mgr = make_audit_manager({"FRONTEND_API_KEY01": primary})

    task_id = "test_primary_503"
    prompt = make_test_prompt(task_id=task_id)

    res = await mgr.complete_text(prompt)

    assert res.text == "Recovered on retry"
    assert len(primary.calls) == 2

    # Request budget correctly advanced across attempts (Attempt 1 = 1, Attempt 2 = 2)
    status = mgr.budget_manager.get_status(task_id)
    assert status["current_request_number"] == 2

    # Usage logs verify both attempts recorded
    logs = [log for log in mgr.usage_tracker._buffer if log.get("task_id") == task_id]
    assert len(logs) == 2

    # Attempt 1: primary failed
    assert logs[0]["request_number"] == 1
    assert logs[0]["attempt_number"] == 1
    assert logs[0]["status"] == "failed"
    assert logs[0]["credential_slot"] == "FRONTEND_API_KEY01"
    assert logs[0]["error_category"] == "SERVER_ERROR"

    # Attempt 2: primary retry succeeded
    assert logs[1]["request_number"] == 2
    assert logs[1]["attempt_number"] == 2
    assert logs[1]["status"] == "success"
    assert logs[1]["credential_slot"] == "FRONTEND_API_KEY01"


@pytest.mark.asyncio
async def test_3_frontend_primary_rpm_rate_limit():
    """TEST 3: Primary returns 429 RPM limit -> marked cooling down, halts cleanly without borrowing."""
    class MockRPMError(Exception):
        error_kind = "RATE_LIMITED"
        status_code = 429
        retry_after = 45.0

    primary = MockProvider(
        name="gemini",
        model="gemini-3.6-flash",
        slot="FRONTEND_API_KEY01",
        error=MockRPMError("429 Too Many Requests: RPM exceeded"),
    )

    mgr = make_audit_manager({"FRONTEND_API_KEY01": primary})

    task_id = "test_rpm_failover"
    prompt = make_test_prompt(task_id=task_id)

    with pytest.raises(AllProvidersFailed):
        await mgr.complete_text(prompt)

    assert mgr._accounts["FRONTEND_API_KEY01"].is_cooling_down is True
    assert mgr._accounts["FRONTEND_API_KEY01"].status == "cooling_down"

    status = mgr.budget_manager.get_status(task_id)
    assert status["current_request_number"] == 1


@pytest.mark.asyncio
async def test_4_frontend_primary_rpd_quota_exhaustion():
    """TEST 4: Primary returns 429 RPD/Daily quota exhaustion -> marked cooling down, halts cleanly."""
    class MockRPDError(Exception):
        error_kind = "RATE_LIMITED"
        status_code = 429
        retry_after = 600.0

    primary = MockProvider(
        name="gemini",
        model="gemini-3.6-flash",
        slot="FRONTEND_API_KEY01",
        error=MockRPDError("429 Resource Exhausted: daily quota exceeded"),
    )

    mgr = make_audit_manager({"FRONTEND_API_KEY01": primary})

    task_id = "test_rpd_failover"
    prompt = make_test_prompt(task_id=task_id)

    with pytest.raises(AllProvidersFailed):
        await mgr.complete_text(prompt)

    acc = mgr._accounts["FRONTEND_API_KEY01"]
    assert acc.is_cooling_down is True
    assert acc.cooldown_remaining_seconds > 100.0


@pytest.mark.asyncio
async def test_5_frontend_primary_auth_failure():
    """TEST 5: Primary authentication error (401) -> marked auth_failed, fail-fast without retry."""
    class MockAuthError(Exception):
        error_kind = "AUTHENTICATION_ERROR"
        status_code = 401

    primary = MockProvider(
        name="gemini",
        model="gemini-3.6-flash",
        slot="FRONTEND_API_KEY01",
        error=MockAuthError("401 Unauthorized: API key invalid"),
    )

    mgr = make_audit_manager({"FRONTEND_API_KEY01": primary})

    task_id = "test_auth_failure"
    prompt = make_test_prompt(task_id=task_id)

    with pytest.raises(AllProvidersFailed):
        await mgr.complete_text(prompt)

    acc = mgr._accounts["FRONTEND_API_KEY01"]
    assert acc.status == "auth_failed"
    assert acc.is_selectable is False
    assert len(primary.calls) == 1  # Exactly 1 call, NO retry on 401


@pytest.mark.asyncio
async def test_6_all_frontend_credentials_fail_bounded_stop():
    """TEST 6: All attempts fail -> bounded failure (at most 1 retry), stops cleanly."""
    class Mock503(Exception):
        error_kind = "SERVER_ERROR"
        status_code = 503

    primary = MockProvider(name="gemini", slot="FRONTEND_API_KEY01", error=Mock503("503 Fail"))

    mgr = make_audit_manager({"FRONTEND_API_KEY01": primary})

    task_id = "test_all_fail"
    prompt = make_test_prompt(task_id=task_id)

    with pytest.raises(AllProvidersFailed):
        await mgr.complete_text(prompt)

    # Exactly 2 calls made (initial + 1 bounded retry), no runaway loop
    assert len(primary.calls) == 2

    status = mgr.budget_manager.get_status(task_id)
    assert status["current_request_number"] == 2
    assert status["current_request_number"] <= 15


@pytest.mark.asyncio
async def test_7_no_cross_role_borrowing():
    """TEST 7: Failing frontend role NEVER borrows or consumes another role's slot (e.g. BACKEND_API_KEY01)."""
    class Mock503(Exception):
        error_kind = "SERVER_ERROR"
        status_code = 503

    primary = MockProvider(name="gemini", slot="FRONTEND_API_KEY01", error=Mock503("503 Fail"))
    backend = MockProvider(name="gemini", slot="BACKEND_API_KEY01", response_text="Backend data")

    mgr = make_audit_manager({
        "FRONTEND_API_KEY01": primary,
        "BACKEND_API_KEY01": backend,
    })

    task_id = "test_no_cross_borrow"
    prompt = make_test_prompt(task_id=task_id)

    with pytest.raises(AllProvidersFailed):
        await mgr.complete_text(prompt)

    # Primary made bounded attempts, backend was NEVER touched
    assert len(primary.calls) == 2
    assert len(backend.calls) == 0


@pytest.mark.asyncio
async def test_8_request_budget_hard_cap_blocks_request_16():
    """TEST 8: Global request budget enforcement: Request #16 is strictly BLOCKED."""
    class Mock503(Exception):
        error_kind = "SERVER_ERROR"
        status_code = 503

    primary = MockProvider(name="gemini", slot="FRONTEND_API_KEY01", error=Mock503("503 Fail"))

    mgr = make_audit_manager(
        {"FRONTEND_API_KEY01": primary},
        target_budget=10,
        hard_max=15,
    )

    task_id = "test_budget_cap_15"

    # Pre-consume 15 requests (reaching the hard limit)
    state = mgr.budget_manager.get_or_create(task_id, target_limit=10, hard_limit=15)
    for _ in range(15):
        state.check_and_increment(agent_role="mock_agent")

    assert state.current_request_number == 15

    prompt = make_test_prompt(task_id=task_id)

    # Calling complete_text:
    # Attempting to acquire request #16 -> strictly BLOCKED by RequestBudgetExceededError!
    with pytest.raises(RequestBudgetExceededError):
        await mgr.complete_text(prompt)

    # Verify state is locked at hard limit 15, request #16 was NEVER sent to provider!
    assert state.current_request_number == 15
    assert len(primary.calls) == 0

    # UsageLog records budget_exceeded
    logs = [log for log in mgr.usage_tracker._buffer if log.get("task_id") == task_id]
    blocked_logs = [l for l in logs if l.get("status") == "budget_exceeded"]
    assert len(blocked_logs) >= 1
    assert blocked_logs[0]["error_category"] == "REQUEST_BUDGET_EXCEEDED"


@pytest.mark.asyncio
async def test_9_no_false_fallback_on_bad_request_or_schema_error():
    """TEST 9: 400 Bad Request or Schema error halts immediately without retrying."""
    class Mock400Error(Exception):
        error_kind = "INVALID_REQUEST"
        status_code = 400

    primary = MockProvider(
        name="gemini",
        slot="FRONTEND_API_KEY01",
        error=Mock400Error("400 Bad Request: Invalid argument syntax"),
    )

    mgr = make_audit_manager({"FRONTEND_API_KEY01": primary})

    task_id = "test_no_false_fallback"
    prompt = make_test_prompt(task_id=task_id)

    with pytest.raises(Mock400Error):
        await mgr.complete_text(prompt)

    # Primary failed on bad request, halts immediately (fail-fast, exactly 1 call)
    assert len(primary.calls) == 1


@pytest.mark.asyncio
async def test_10_safe_fault_injection_mechanism():
    """TEST 10: Safe test-only fault injection via FRONTEND_PRIMARY_FAILURE_TEST env var."""
    primary = MockProvider(name="gemini", model="gemini-3.6-flash", slot="FRONTEND_API_KEY01")

    mgr = make_audit_manager({"FRONTEND_API_KEY01": primary})

    task_id = "test_fault_injection_env"
    prompt = make_test_prompt(task_id=task_id)

    # Enable fault injection simulating 503 server error on primary frontend slot
    os.environ["FRONTEND_PRIMARY_FAILURE_TEST"] = "SERVER_ERROR"
    try:
        with pytest.raises(AllProvidersFailed):
            await mgr.complete_text(prompt)

        # Primary provider was NOT even called with real API (fault-injected before call)
        assert len(primary.calls) == 0

        # Attempts recorded in UsageLog with SERVER_ERROR
        logs = [log for log in mgr.usage_tracker._buffer if log.get("task_id") == task_id]
        assert len(logs) >= 1
        assert logs[0]["status"] == "failed"
        assert logs[0]["error_category"] == "SERVER_ERROR"
    finally:
        os.environ.pop("FRONTEND_PRIMARY_FAILURE_TEST", None)
