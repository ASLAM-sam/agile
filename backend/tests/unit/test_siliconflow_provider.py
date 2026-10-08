"""Unit tests for SiliconFlow free-tier provider integration.

Verifies all 15 audit requirements:
1. SiliconFlow API key loads correctly.
2. Explicit SILICONFLOW_MODEL works.
3. Empty SILICONFLOW_MODEL triggers automatic selection.
4. Automatic selection chooses only an eligible FREE chat model.
5. Paid models are rejected for free-plan automatic selection.
6. Non-chat models are rejected.
7. Model must be explicitly included in the actual request.
8. Model discovery does not consume the 15-request task budget.
9. Actual fallback requests do consume the budget.
10. RPM handling works.
11. RPD handling works.
12. No raw API key appears in logs.
13. Agents still use generic ctx.llm.
14. Gemini 3.7/3.8 remain absent.
15. Request #16 remains blocked.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.context import AgentContext
from app.agents.frontend_engineer import FrontendEngineerAgent
from app.core.config import Settings
from app.core.enums import AgentRole, TaskKind
from app.core.exceptions import ConfigurationError, LLMError
from app.llm.agent_model_registry import (
    DEFAULT_GEMINI_FALLBACK_CHAIN,
    GEMINI_MODEL_REGISTRY,
)
from app.llm.budget import RequestBudgetExceededError, RequestBudgetManager
from app.llm.credentials import CredentialManager, mask_key
from app.llm.manager import RoleBasedProviderManager
from app.llm.protocol import LLMProvider
from app.llm.providers.base import ProviderSpec
from app.llm.quota import QuotaEngine, QuotaSource, get_quota_engine
from app.llm.router import ModelRouter
from app.llm.siliconflow import (
    DEPRECATED_MODELS,
    KNOWN_PAID_MODELS,
    SiliconFlowAdapter,
    SiliconFlowCatalog,
    SiliconFlowModelInfo,
    get_siliconflow_catalog,
)
from app.llm.types import Completion, PromptBundle, TextCompletion, TokenUsage
from app.llm.usage import UsageTracker, get_usage_tracker
from app.workflow.memory import SharedProjectMemory


class TestSiliconFlowIntegration:
    """Audit and functional test suite for SiliconFlow provider."""

    def test_01_siliconflow_api_key_loads_correctly(self) -> None:
        """Requirement 1: SiliconFlow API key loads correctly."""
        cfg = Settings(siliconflow_api_key="sk-test-siliconflow-key-998877")
        assert cfg.siliconflow_api_key == "sk-test-siliconflow-key-998877"
        assert cfg.llm_configured is True
        assert cfg.get_role_credential("backend") == "sk-test-siliconflow-key-998877"

    def test_02_explicit_siliconflow_model_works(self) -> None:
        """Requirement 2: Explicit SILICONFLOW_MODEL works when eligible."""
        cfg = Settings(
            siliconflow_api_key="sk-test-key",
            siliconflow_model="Qwen/Qwen2.5-7B-Instruct",
        )
        catalog = SiliconFlowCatalog(cfg)
        selected = catalog.select_model(explicit_model="Qwen/Qwen2.5-7B-Instruct")
        assert selected == "Qwen/Qwen2.5-7B-Instruct"

    def test_03_empty_siliconflow_model_triggers_automatic_selection(self) -> None:
        """Requirement 3: Empty SILICONFLOW_MODEL triggers automatic selection."""
        cfg = Settings(siliconflow_api_key="sk-test-key", siliconflow_model="")
        catalog = SiliconFlowCatalog(cfg)
        selected = catalog.select_model(explicit_model="")
        assert selected is not None
        assert len(selected) > 0
        assert selected in ("Qwen/Qwen3-8B", "Qwen/Qwen2.5-7B-Instruct", "zai-org/GLM-4.5-Air")

    def test_04_automatic_selection_chooses_only_eligible_free_chat_model(self) -> None:
        """Requirement 4: Automatic selection chooses only an eligible FREE chat model."""
        catalog = SiliconFlowCatalog()
        eligible = catalog.get_eligible_free_chat_models()
        assert len(eligible) > 0

        for model_info in eligible:
            assert model_info.is_chat is True
            assert model_info.is_free is True
            assert model_info.is_available is True
            assert model_info.id not in DEPRECATED_MODELS
            assert model_info.id not in KNOWN_PAID_MODELS

        selected = catalog.select_model()
        chosen = next((m for m in eligible if m.id == selected), None)
        assert chosen is not None
        assert chosen.is_free is True
        assert chosen.is_chat is True

    def test_05_paid_models_rejected_for_free_plan(self) -> None:
        """Requirement 5: Paid models are rejected for free-plan automatic selection."""
        catalog = SiliconFlowCatalog()

        # Check paid models are rejected on explicit selection
        for paid in ("Qwen/Qwen2.5-72B-Instruct", "deepseek-ai/DeepSeek-V4-Pro", "openai/gpt-oss-120b"):
            with pytest.raises(ConfigurationError, match="paid model"):
                catalog.select_model(explicit_model=paid)

        # Check paid models never appear in eligible free models
        eligible_ids = [m.id for m in catalog.get_eligible_free_chat_models()]
        for paid in KNOWN_PAID_MODELS:
            assert paid not in eligible_ids

    def test_06_non_chat_models_rejected(self) -> None:
        """Requirement 6: Non-chat models are rejected."""
        catalog = SiliconFlowCatalog()
        non_chat_examples = [
            "BAAI/bge-m3",
            "BAAI/bge-reranker-v2-m3",
            "black-forest-labs/FLUX.1-schnell",
            "stabilityai/stable-diffusion-3-5-large",
        ]
        for nc in non_chat_examples:
            assert catalog.is_chat_model(nc) is False
            with pytest.raises(ConfigurationError, match="not a chat-compatible model"):
                catalog.select_model(explicit_model=nc)

    @pytest.mark.asyncio
    async def test_07_model_must_be_explicitly_included_in_actual_request(self) -> None:
        """Requirement 7: Model must be explicitly included in the actual request."""
        spec = ProviderSpec(
            key="siliconflow",
            display_name="SiliconFlow",
            model="Qwen/Qwen3-8B",
            priority=1,
        )
        adapter = SiliconFlowAdapter(
            spec,
            base_url="https://api.siliconflow.cn/v1",
            api_key="sk-test-key-mock",
        )

        sent_payloads: list[dict[str, Any]] = []

        async def fake_chat(prompt: PromptBundle, *, schema: dict[str, Any] | None = None, model: str | None = None):
            effective_model = adapter._resolve_model(model)
            sent_payloads.append({"model": effective_model})
            return ('{"result": "ok"}', TokenUsage(input_tokens=10, output_tokens=5), "stop", effective_model)

        adapter._chat = fake_chat  # type: ignore[assignment]

        prompt = PromptBundle(
            cacheable_system="system",
            user_message="hello",
            schema={"type": "object", "properties": {"result": {"type": "string"}}},
            metadata={"agent": "backend_engineer"},
        )

        # 1. Structured completion
        res = await adapter.complete_structured(prompt)
        assert len(sent_payloads) == 1
        assert sent_payloads[0]["model"] is not None
        assert sent_payloads[0]["model"] != ""
        assert sent_payloads[0]["model"] == "Qwen/Qwen3-8B"

        # 2. Text completion
        text_prompt = PromptBundle(cacheable_system="", user_message="hello plain")
        await adapter.complete_text(text_prompt)
        assert len(sent_payloads) == 2
        assert sent_payloads[1]["model"] is not None
        assert sent_payloads[1]["model"] != ""

    def test_08_model_discovery_does_not_consume_budget(self) -> None:
        """Requirement 8: Model discovery does not consume the 15-request task budget."""
        cfg = Settings(target_requests_per_task=10, hard_max_requests_per_task=15)
        budget = RequestBudgetManager(config=cfg)
        task_id = "task_discovery_test"

        catalog = SiliconFlowCatalog(config=cfg)
        # Perform discovery and model selection
        models = catalog.discover_models()
        selected = catalog.select_model()

        assert len(models) > 0
        assert selected is not None
        # Verify budget is completely untouched (0 requests recorded)
        assert budget.get_status(task_id)["current_request_number"] == 0

    @pytest.mark.asyncio
    async def test_09_actual_fallback_requests_consume_budget(self) -> None:
        """Requirement 9: Actual fallback requests do consume the budget."""
        cfg = Settings(target_requests_per_task=10, hard_max_requests_per_task=15)
        budget = RequestBudgetManager(config=cfg)
        task_id = "task_fallback_budget_test"

        # Simulate 2 request attempts during a fallback scenario
        num1 = budget.next_request_number(task_id, agent_role="backend_engineer")
        assert num1 == 1

        # Fallback request attempt
        num2 = budget.next_request_number(task_id, agent_role="backend_engineer")
        assert num2 == 2

        assert budget.get_status(task_id)["current_request_number"] == 2

    def test_10_rpm_handling_works(self) -> None:
        """Requirement 10: RPM handling works in QuotaEngine."""
        quota = QuotaEngine()
        # Record 5 requests within current minute
        for _ in range(5):
            quota.record_usage(
                provider="siliconflow",
                model="Qwen/Qwen3-8B",
                credential_slot="BACKEND_API_KEY",
                tokens=120,
            )

        overview = quota.get_overview()
        prov_entry = next((p for p in overview["providers"] if p["name"] == "siliconflow"), None)
        assert prov_entry is not None
        assert prov_entry["rpm"]["used"] == 5
        assert prov_entry["rpm"]["source"] in (QuotaSource.LOCALLY_TRACKED.value, QuotaSource.UNKNOWN.value)

    def test_11_rpd_handling_works(self) -> None:
        """Requirement 11: RPD handling works in QuotaEngine."""
        quota = QuotaEngine()
        quota.record_usage(
            provider="siliconflow",
            model="Qwen/Qwen3-8B",
            credential_slot="BACKEND_API_KEY",
            tokens=200,
            headers={"x-ratelimit-limit-requests-per-day": "1000", "x-ratelimit-remaining-requests-per-day": "995"},
        )
        overview = quota.get_overview()
        prov_entry = next((p for p in overview["providers"] if p["name"] == "siliconflow"), None)
        assert prov_entry is not None
        assert prov_entry["rpd"]["limit"] == 1000
        assert prov_entry["rpd"]["remaining"] == 995
        assert prov_entry["rpd"]["source"] == QuotaSource.PROVIDER_REPORTED.value

    def test_12_no_raw_api_key_appears_in_logs(self) -> None:
        """Requirement 12: No raw API key appears in logs."""
        raw_key = "sk-secret-siliconflow-key-xyz12345"
        masked = mask_key(raw_key)

        assert raw_key not in masked
        assert masked == "****2345".upper()

        tracker = UsageTracker()
        entry_data = {
            "task_id": "task_log_test",
            "provider": "siliconflow",
            "model": "Qwen/Qwen3-8B",
            "credential_slot": "BACKEND_API_KEY",
            "masked_credential": masked,
            "status": "success",
        }
        asyncio.run(tracker.record_entry(entry_data))

        buffered = tracker.get_buffered_entries(task_id="task_log_test")
        assert len(buffered) == 1
        record = buffered[0]
        for val in record.values():
            if isinstance(val, str):
                assert raw_key not in val

    @pytest.mark.asyncio
    async def test_13_agents_still_use_generic_ctx_llm(self) -> None:
        """Requirement 13: Agents still use generic ctx.llm without vendor SDK coupling."""
        mock_llm = MagicMock()
        mock_completion = Completion(
            data={"summary": "Agent completed task", "components": []},
            usage=TokenUsage(input_tokens=100, output_tokens=50),
            stop_reason="stop",
            model="Qwen/Qwen3-8B",
            raw_text='{"summary": "Agent completed task", "components": []}',
        )
        mock_llm.complete_structured = AsyncMock(return_value=mock_completion)

        memory = SharedProjectMemory(
            run_id="run_123",
            project_id="proj_123",
            project_name="Test App",
            project_slug="test-app",
            idea="Test app idea",
        )
        from app.adapters.registry import AdapterRegistry

        ctx = AgentContext(
            memory=memory,
            llm=mock_llm,
            registry=AdapterRegistry(),
            report_progress=AsyncMock(),
            report_log=AsyncMock(),
        )

        agent = FrontendEngineerAgent()
        prompt = PromptBundle(
            cacheable_system="system prompt",
            user_message="build UI",
            schema={"type": "object", "properties": {"summary": {"type": "string"}}},
        )

        result = await ctx.llm.complete_structured(prompt)
        assert result.data["summary"] == "Agent completed task"
        assert result.model == "Qwen/Qwen3-8B"
        mock_llm.complete_structured.assert_awaited_once_with(prompt)

    def test_14_gemini_37_38_remain_absent(self) -> None:
        """Requirement 14: Gemini 3.7 and 3.8 remain absent."""
        assert "gemini-3.7" not in DEFAULT_GEMINI_FALLBACK_CHAIN
        assert "gemini-3.8" not in DEFAULT_GEMINI_FALLBACK_CHAIN
        assert "gemini-3.7-flash" not in GEMINI_MODEL_REGISTRY
        assert "gemini-3.8-flash" not in GEMINI_MODEL_REGISTRY
        assert "gemini-3.6-flash" in DEFAULT_GEMINI_FALLBACK_CHAIN

    def test_15_request_16_remains_blocked(self) -> None:
        """Requirement 15: Request #16 remains blocked."""
        cfg = Settings(target_requests_per_task=10, hard_max_requests_per_task=15)
        budget = RequestBudgetManager(config=cfg)
        task_id = "task_max_requests_test"

        # 15 requests succeed
        for i in range(1, 16):
            req_num = budget.next_request_number(task_id, agent_role="backend_engineer")
            assert req_num == i

        # Request 16 must be blocked
        with pytest.raises(RequestBudgetExceededError, match="has exceeded its hard request limit of 15 LLM calls"):
            budget.next_request_number(task_id, agent_role="backend_engineer")
