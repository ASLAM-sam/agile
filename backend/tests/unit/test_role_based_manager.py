"""Tests for the 7-slot Gemini-only role-based LLM provider manager.

The 7 dedicated Gemini slots:
  - LLM SLOT 01 (PLANNER_API_KEY01): Manager, Business Analyst, Solution Architect
  - LLM SLOT 02 (FRONTEND_API_KEY01): Frontend Engineer, Documentation Engineer
  - LLM SLOT 03 (BACKEND_API_KEY01): Backend Engineer
  - LLM SLOT 04 (DATABASE_API_KEY01): Database Engineer
  - LLM SLOT 05 (QA_API_KEY01): QA Engineer
  - LLM SLOT 06 (REVIEW_API_KEY01): Review Engineer, Improvement Engineer
  - LLM SLOT 07 (DEBUG_API_KEY01): Final QA, Self-repair/debug
  - Artifact Manager: Deterministic (no LLM slot)
  - Zero cross-role or cross-account failover
  - ONLY gemini-3.6-flash permitted
  - Prompt cache isolated per slot
"""

from __future__ import annotations

import pytest

from app.core.enums import AgentRole
from app.core.exceptions import ConfigurationError, LLMError
from app.llm.agent_model_registry import AGENT_PROVIDER_SLOT, provider_slot_for
from app.llm.cache import PromptCache
from app.llm.manager import RoleBasedProviderManager
from app.llm.types import Completion, PromptBundle, TextCompletion, TokenUsage

# --- Fakes -------------------------------------------------------------------

class FakeProvider:
    """A provider that returns a canned response or raises an error."""

    def __init__(
        self,
        *,
        slot: str = "FRONTEND_API_KEY01",
        response: Completion | TextCompletion | None = None,
        error: Exception | None = None,
        model_errors: dict[str, Exception] | None = None,
    ) -> None:
        self.slot = slot
        self.calls: list[PromptBundle] = []
        self.model_calls: list[str] = []
        self._response = response
        self._error = error
        self._model_errors = model_errors or {}

    @property
    def model(self) -> str:
        return "gemini-3.6-flash"

    async def complete_structured(
        self, prompt: PromptBundle, *, model: str | None = None
    ) -> Completion:
        target_model = model or "gemini-3.6-flash"
        self.calls.append(prompt)
        self.model_calls.append(target_model)
        if target_model in self._model_errors:
            raise self._model_errors[target_model]
        if self._error is not None:
            raise self._error
        if self._response is not None and isinstance(self._response, Completion):
            return self._response
        return Completion(
            data={"result": "ok"},
            usage=TokenUsage(input_tokens=10, output_tokens=5),
            model=target_model,
        )

    async def complete_text(
        self, prompt: PromptBundle, *, model: str | None = None
    ) -> TextCompletion:
        target_model = model or "gemini-3.6-flash"
        self.calls.append(prompt)
        self.model_calls.append(target_model)
        if target_model in self._model_errors:
            raise self._model_errors[target_model]
        if self._error is not None:
            raise self._error
        if self._response is not None and isinstance(self._response, TextCompletion):
            return self._response
        return TextCompletion(text="ok", usage=TokenUsage(), model=target_model)

    async def aclose(self) -> None:
        pass


def make_manager(
    slots: dict[str, FakeProvider] | None = None,
    cache_enabled: bool = False,
) -> RoleBasedProviderManager:
    """Create a manager with fake providers for testing."""
    from unittest.mock import MagicMock

    from app.core.config import Settings

    config = MagicMock(spec=Settings)
    config.llm_cache_enabled = cache_enabled
    config.llm_cache_max_entries = 512
    config.llm_cache_ttl_seconds = 3600.0
    config.llm_max_retries = 1
    config.gemini_model = "gemini-3.6-flash"
    config.gemini_allowed_model = "gemini-3.6-flash"
    config.gemini_fallback_models = []

    cache = PromptCache(enabled=cache_enabled)
    providers = dict(slots or {})

    return RoleBasedProviderManager(
        config=config,
        providers=providers,
        cache=cache,
    )


def prompt_for_agent(role: AgentRole) -> PromptBundle:
    """A minimal structured prompt tagged with the given agent."""
    return PromptBundle(
        cacheable_system="system",
        user_message="do something",
        schema={"type": "object"},
        metadata={"agent": role.value},
    )


# --- Tests -------------------------------------------------------------------


class TestRoleBasedDispatchMapping:
    """Each of the 12 agent roles resolves to its exact assigned Gemini slot or deterministic."""

    def test_registry_mapping_is_exhaustive(self) -> None:
        """Every AgentRole has an explicit mapping in AGENT_PROVIDER_SLOT."""
        for role in AgentRole:
            assert role in AGENT_PROVIDER_SLOT
            slot = provider_slot_for(role)
            if role == AgentRole.ARTIFACT_MANAGER:
                assert slot == "none"
            else:
                assert slot in {
                    "PLANNER_API_KEY01",
                    "FRONTEND_API_KEY01",
                    "BACKEND_API_KEY01",
                    "DATABASE_API_KEY01",
                    "QA_API_KEY01",
                    "REVIEW_API_KEY01",
                    "DEBUG_API_KEY01",
                }

    @pytest.mark.asyncio
    async def test_manager_dispatches_to_planner_slot(self) -> None:
        p = FakeProvider(slot="PLANNER_API_KEY01")
        mgr = make_manager({"PLANNER_API_KEY01": p})
        await mgr.complete_structured(prompt_for_agent(AgentRole.MANAGER))
        assert len(p.calls) == 1

    @pytest.mark.asyncio
    async def test_frontend_engineer_dispatches_to_frontend_slot(self) -> None:
        p = FakeProvider(slot="FRONTEND_API_KEY01")
        mgr = make_manager({"FRONTEND_API_KEY01": p})
        await mgr.complete_structured(prompt_for_agent(AgentRole.FRONTEND_ENGINEER))
        assert len(p.calls) == 1

    @pytest.mark.asyncio
    async def test_docs_engineer_dispatches_to_frontend_slot(self) -> None:
        p = FakeProvider(slot="FRONTEND_API_KEY01")
        mgr = make_manager({"FRONTEND_API_KEY01": p})
        await mgr.complete_structured(prompt_for_agent(AgentRole.DOCUMENTATION_ENGINEER))
        assert len(p.calls) == 1

    @pytest.mark.asyncio
    async def test_ba_dispatches_to_planner_slot(self) -> None:
        p = FakeProvider(slot="PLANNER_API_KEY01")
        mgr = make_manager({"PLANNER_API_KEY01": p})
        await mgr.complete_structured(prompt_for_agent(AgentRole.BUSINESS_ANALYST))
        assert len(p.calls) == 1

    @pytest.mark.asyncio
    async def test_backend_engineer_dispatches_to_backend_slot(self) -> None:
        p = FakeProvider(slot="BACKEND_API_KEY01")
        mgr = make_manager({"BACKEND_API_KEY01": p})
        await mgr.complete_structured(prompt_for_agent(AgentRole.BACKEND_ENGINEER))
        assert len(p.calls) == 1

    @pytest.mark.asyncio
    async def test_review_engineer_dispatches_to_review_slot(self) -> None:
        p = FakeProvider(slot="REVIEW_API_KEY01")
        mgr = make_manager({"REVIEW_API_KEY01": p})
        await mgr.complete_structured(prompt_for_agent(AgentRole.REVIEW_ENGINEER))
        assert len(p.calls) == 1

    @pytest.mark.asyncio
    async def test_solution_architect_dispatches_to_planner_slot(self) -> None:
        p = FakeProvider(slot="PLANNER_API_KEY01")
        mgr = make_manager({"PLANNER_API_KEY01": p})
        await mgr.complete_structured(prompt_for_agent(AgentRole.SOLUTION_ARCHITECT))
        assert len(p.calls) == 1

    @pytest.mark.asyncio
    async def test_qa_engineer_dispatches_to_qa_slot(self) -> None:
        p = FakeProvider(slot="QA_API_KEY01")
        mgr = make_manager({"QA_API_KEY01": p})
        await mgr.complete_structured(prompt_for_agent(AgentRole.QA_ENGINEER))
        assert len(p.calls) == 1

    @pytest.mark.asyncio
    async def test_final_qa_dispatches_to_debug_slot(self) -> None:
        p = FakeProvider(slot="DEBUG_API_KEY01")
        mgr = make_manager({"DEBUG_API_KEY01": p})
        await mgr.complete_structured(prompt_for_agent(AgentRole.FINAL_QA))
        assert len(p.calls) == 1

    @pytest.mark.asyncio
    async def test_database_engineer_dispatches_to_database_slot(self) -> None:
        p = FakeProvider(slot="DATABASE_API_KEY01")
        mgr = make_manager({"DATABASE_API_KEY01": p})
        await mgr.complete_structured(prompt_for_agent(AgentRole.DATABASE_ENGINEER))
        assert len(p.calls) == 1

    @pytest.mark.asyncio
    async def test_improvement_engineer_dispatches_to_review_slot(self) -> None:
        p = FakeProvider(slot="REVIEW_API_KEY01")
        mgr = make_manager({"REVIEW_API_KEY01": p})
        await mgr.complete_structured(prompt_for_agent(AgentRole.IMPROVEMENT_ENGINEER))
        assert len(p.calls) == 1

    @pytest.mark.asyncio
    async def test_artifact_manager_is_deterministic_and_rejects_llm_calls(self) -> None:
        mgr = make_manager({
            "PLANNER_API_KEY01": FakeProvider(slot="PLANNER_API_KEY01"),
            "FRONTEND_API_KEY01": FakeProvider(slot="FRONTEND_API_KEY01"),
        })
        with pytest.raises(ConfigurationError, match="deterministic"):
            await mgr.complete_structured(prompt_for_agent(AgentRole.ARTIFACT_MANAGER))


class TestModelEnforcementAndNoBorrowing:
    """Strictly gemini-3.6-flash is allowed, and no secret key borrowing across roles."""

    @pytest.mark.asyncio
    async def test_only_gemini_36_flash_allowed(self) -> None:
        backend_acc = FakeProvider(slot="BACKEND_API_KEY01")
        mgr = make_manager({"BACKEND_API_KEY01": backend_acc})

        p = prompt_for_agent(AgentRole.BACKEND_ENGINEER)
        p.metadata["model"] = "gemini-3.8-flash"

        # Requesting an unapproved model is immediately rejected
        with pytest.raises(ConfigurationError, match="Unauthorized Gemini model"):
            await mgr.complete_structured(p)

    @pytest.mark.asyncio
    async def test_no_cross_role_secret_borrowing(self) -> None:
        """If a role slot is unconfigured, do NOT silently borrow another role's slot."""
        # Only FRONTEND_API_KEY01 is configured; BACKEND_API_KEY01 is not
        frontend_acc = FakeProvider(slot="FRONTEND_API_KEY01")
        mgr = make_manager({"FRONTEND_API_KEY01": frontend_acc})

        with pytest.raises(ConfigurationError, match="BACKEND_API_KEY01"):
            await mgr.complete_structured(prompt_for_agent(AgentRole.BACKEND_ENGINEER))

        assert len(frontend_acc.calls) == 0

    @pytest.mark.asyncio
    async def test_clean_failure_on_quota_exhausted(self) -> None:
        """429 ResourceExhausted raises cleanly without infinite cycling."""
        qa_acc = FakeProvider(
            slot="QA_API_KEY01",
            error=LLMError("429 ResourceExhausted", details={"error_kind": "QUOTA_EXHAUSTED"}),
        )
        mgr = make_manager({"QA_API_KEY01": qa_acc})

        with pytest.raises(LLMError, match="429"):
            await mgr.complete_structured(prompt_for_agent(AgentRole.QA_ENGINEER))

        # Only attempted on QA slot, no borrowing
        assert len(qa_acc.calls) == 1

    @pytest.mark.asyncio
    async def test_clean_failure_on_auth_rejection(self) -> None:
        """401/403 stops cleanly without retry loops."""
        plan_acc = FakeProvider(
            slot="PLANNER_API_KEY01",
            error=LLMError("401 Unauthorized", details={"error_kind": "AUTHENTICATION"}),
        )
        mgr = make_manager({"PLANNER_API_KEY01": plan_acc})

        with pytest.raises(LLMError, match="401"):
            await mgr.complete_structured(prompt_for_agent(AgentRole.SOLUTION_ARCHITECT))

        assert len(plan_acc.calls) == 1


class TestStatsAndRateLimits:
    """Usage stats and rate limits are tracked per slot."""

    @pytest.mark.asyncio
    async def test_successful_request_increments_counters(self) -> None:
        p = FakeProvider(slot="PLANNER_API_KEY01")
        mgr = make_manager({"PLANNER_API_KEY01": p})

        await mgr.complete_structured(prompt_for_agent(AgentRole.MANAGER))

        assert mgr.stats.requests == 1
        assert mgr.stats.successes == 1
        assert mgr.stats.failures == 0
        stat = mgr._slot_stats["PLANNER_API_KEY01"]
        assert stat.requests == 1
        assert stat.successes == 1
        assert stat.failures == 0
        assert stat.rate_limits == 0

    @pytest.mark.asyncio
    async def test_rate_limited_request_increments_rate_limits_counter(self) -> None:
        p = FakeProvider(
            slot="PLANNER_API_KEY01",
            error=LLMError("429 rate limit", details={"error_kind": "RATE_LIMITED"}),
        )
        mgr = make_manager({"PLANNER_API_KEY01": p})

        with pytest.raises(LLMError):
            await mgr.complete_structured(prompt_for_agent(AgentRole.SOLUTION_ARCHITECT))

        assert mgr.stats.requests == 1
        assert mgr.stats.failures == 1
        stat = mgr._slot_stats["PLANNER_API_KEY01"]
        assert stat.requests == 1
        assert stat.failures == 1
        assert stat.rate_limits == 1
        assert stat.last_error_kind == "RATE_LIMITED"


class TestPromptCachePerSlot:
    """Prompt cache works with role-based routing and is slot-isolated."""

    @pytest.mark.asyncio
    async def test_cache_hit_skips_provider(self) -> None:
        p = FakeProvider(slot="PLANNER_API_KEY01")
        mgr = make_manager({"PLANNER_API_KEY01": p}, cache_enabled=True)
        prompt = prompt_for_agent(AgentRole.MANAGER)

        await mgr.complete_structured(prompt)
        assert len(p.calls) == 1
        assert mgr.stats.cache_misses == 1
        assert mgr.stats.cache_hits == 0

        await mgr.complete_structured(prompt)
        assert len(p.calls) == 1  # still 1
        assert mgr.stats.cache_hits == 1

    @pytest.mark.asyncio
    async def test_different_roles_same_prompt_are_separate_cache_entries(self) -> None:
        planner = FakeProvider(slot="PLANNER_API_KEY01")
        backend = FakeProvider(slot="BACKEND_API_KEY01")
        mgr = make_manager(
            {"PLANNER_API_KEY01": planner, "BACKEND_API_KEY01": backend},
            cache_enabled=True,
        )

        bundle1 = PromptBundle(
            cacheable_system="same system",
            user_message="same message",
            schema={"type": "object"},
            metadata={"agent": AgentRole.MANAGER.value},
        )
        bundle2 = PromptBundle(
            cacheable_system="same system",
            user_message="same message",
            schema={"type": "object"},
            metadata={"agent": AgentRole.BACKEND_ENGINEER.value},
        )

        await mgr.complete_structured(bundle1)
        await mgr.complete_structured(bundle2)

        assert len(planner.calls) == 1
        assert len(backend.calls) == 1


class TestHealthSnapshot:
    """Dashboard snapshots report the 7 Gemini slots with role groups."""

    def test_unconfigured_slots_are_reported(self) -> None:
        mgr = make_manager({})
        snapshot = mgr.health_snapshot()

        slots = {p["slot"] for p in snapshot}
        assert slots == {
            "PLANNER_API_KEY01",
            "FRONTEND_API_KEY01",
            "BACKEND_API_KEY01",
            "DATABASE_API_KEY01",
            "QA_API_KEY01",
            "REVIEW_API_KEY01",
            "DEBUG_API_KEY01",
        }

        for p in snapshot:
            assert p["configured"] is False
            assert "Slot" in p["display_name"]
            assert len(p["role_group"]) > 0

    def test_configured_slots_show_as_configured(self) -> None:
        frontend = FakeProvider(slot="FRONTEND_API_KEY01")
        mgr = make_manager({"FRONTEND_API_KEY01": frontend})
        snapshot = mgr.health_snapshot()

        fe_entry = next(p for p in snapshot if p["slot"] == "FRONTEND_API_KEY01")
        assert fe_entry["configured"] is True
        assert fe_entry["selectable"] is True
        assert fe_entry["display_name"] == "Frontend Slot"
        assert fe_entry["role_group"] == "Frontend / Documentation"
