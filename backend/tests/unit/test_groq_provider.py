"""Unit tests for the Groq client and provider integration."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.core.config import Settings
from app.core.enums import AgentRole
from app.core.exceptions import ConfigurationError, LLMError
from app.llm.agent_model_registry import AGENT_PROVIDER_SLOT, provider_slot_for
from app.llm.groq import GroqClient, _sanitize_schema_for_groq
from app.llm.manager import RoleBasedProviderManager, _build_slot_providers
from app.llm.types import PromptBundle


class TestGroqClientUnit:
    """Test GroqClient wrapper methods and behavior."""

    def test_missing_api_key_raises_configuration_error(self) -> None:
        with pytest.raises(ConfigurationError, match="GROQ_API_KEY is not configured"):
            GroqClient(api_key=None)

    def test_default_model_and_base_url(self) -> None:
        with patch("openai.AsyncOpenAI") as mock_openai:
            client = GroqClient(api_key="gsk-test")
            assert client.model == "openai/gpt-oss-120b"
            mock_openai.assert_called_once_with(
                api_key="gsk-test",
                base_url="https://api.groq.com/openai/v1",
                timeout=900.0,
                max_retries=0,
            )

    def test_sanitize_schema_for_groq(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "nested": {
                    "type": "object",
                    "properties": {"count": {"type": "integer"}},
                },
            },
        }
        clean = _sanitize_schema_for_groq(schema)
        assert clean["additionalProperties"] is False
        assert clean["properties"]["nested"]["additionalProperties"] is False

    @pytest.mark.asyncio
    async def test_complete_structured_success(self) -> None:
        with patch("openai.AsyncOpenAI") as mock_openai:
            mock_resp = MagicMock()
            mock_choice = MagicMock()
            mock_choice.message.content = '{"greeting": "hello world"}'
            mock_choice.finish_reason = "stop"
            mock_resp.choices = [mock_choice]
            mock_resp.model = "openai/gpt-oss-120b"
            mock_resp.usage.prompt_tokens = 15
            mock_resp.usage.completion_tokens = 5

            mock_instance = MagicMock()
            mock_instance.chat.completions.create = AsyncMock(return_value=mock_resp)
            mock_openai.return_value = mock_instance

            client = GroqClient(api_key="gsk-test")
            prompt = PromptBundle(
                cacheable_system="system",
                user_message="say hello",
                schema={"type": "object", "properties": {"greeting": {"type": "string"}}},
                metadata={"agent": "manager"},
            )

            result = await client.complete_structured(prompt)
            assert result.data == {"greeting": "hello world"}
            assert result.model == "openai/gpt-oss-120b"
            assert result.usage.input_tokens == 15
            assert result.usage.output_tokens == 5

    @pytest.mark.asyncio
    async def test_complete_text_success(self) -> None:
        with patch("openai.AsyncOpenAI") as mock_openai:
            mock_resp = MagicMock()
            mock_choice = MagicMock()
            mock_choice.message.content = "Plain text answer"
            mock_choice.finish_reason = "stop"
            mock_resp.choices = [mock_choice]
            mock_resp.model = "openai/gpt-oss-120b"
            mock_resp.usage.prompt_tokens = 8
            mock_resp.usage.completion_tokens = 4

            mock_instance = MagicMock()
            mock_instance.chat.completions.create = AsyncMock(return_value=mock_resp)
            mock_openai.return_value = mock_instance

            client = GroqClient(api_key="gsk-test")
            prompt = PromptBundle(cacheable_system="", user_message="hello")
            result = await client.complete_text(prompt)
            assert result.text == "Plain text answer"


class TestGeminiRoleRouting:
    """Test role assignment and slot resolution for generic credential architecture."""

    def test_manager_routes_to_planner(self) -> None:
        assert provider_slot_for(AgentRole.MANAGER) == "PLANNER_API_KEY01"
        assert AGENT_PROVIDER_SLOT[AgentRole.MANAGER] == "PLANNER_API_KEY01"

    def test_business_analyst_routes_to_planner(self) -> None:
        assert provider_slot_for(AgentRole.BUSINESS_ANALYST) == "PLANNER_API_KEY01"
        assert AGENT_PROVIDER_SLOT[AgentRole.BUSINESS_ANALYST] == "PLANNER_API_KEY01"

    def test_solution_architect_routes_to_planner(self) -> None:
        assert provider_slot_for(AgentRole.SOLUTION_ARCHITECT) == "PLANNER_API_KEY01"
        assert AGENT_PROVIDER_SLOT[AgentRole.SOLUTION_ARCHITECT] == "PLANNER_API_KEY01"

    def test_documentation_engineer_routes_to_frontend(self) -> None:
        assert provider_slot_for(AgentRole.DOCUMENTATION_ENGINEER) == "FRONTEND_API_KEY01"
        assert AGENT_PROVIDER_SLOT[AgentRole.DOCUMENTATION_ENGINEER] == "FRONTEND_API_KEY01"

    def test_complete_generic_slot_mapping(self) -> None:
        assert AGENT_PROVIDER_SLOT[AgentRole.MANAGER] == "PLANNER_API_KEY01"
        assert AGENT_PROVIDER_SLOT[AgentRole.BUSINESS_ANALYST] == "PLANNER_API_KEY01"
        assert AGENT_PROVIDER_SLOT[AgentRole.SOLUTION_ARCHITECT] == "PLANNER_API_KEY01"
        assert AGENT_PROVIDER_SLOT[AgentRole.FRONTEND_ENGINEER] == "FRONTEND_API_KEY01"
        assert AGENT_PROVIDER_SLOT[AgentRole.DOCUMENTATION_ENGINEER] == "FRONTEND_API_KEY01"
        assert AGENT_PROVIDER_SLOT[AgentRole.BACKEND_ENGINEER] == "BACKEND_API_KEY01"
        assert AGENT_PROVIDER_SLOT[AgentRole.DATABASE_ENGINEER] == "DATABASE_API_KEY01"
        assert AGENT_PROVIDER_SLOT[AgentRole.QA_ENGINEER] == "QA_API_KEY01"
        assert AGENT_PROVIDER_SLOT[AgentRole.FINAL_QA] == "DEBUG_API_KEY01"
        assert AGENT_PROVIDER_SLOT[AgentRole.REVIEW_ENGINEER] == "REVIEW_API_KEY01"
        assert AGENT_PROVIDER_SLOT[AgentRole.IMPROVEMENT_ENGINEER] == "REVIEW_API_KEY01"
        assert AGENT_PROVIDER_SLOT[AgentRole.ARTIFACT_MANAGER] == "none"

    def test_slot_providers_builds_gemini_and_excludes_groq(self) -> None:
        cfg = MagicMock(spec=Settings)
        cfg.llm_max_retries = 3
        cfg.llm_timeout_seconds = 60.0
        cfg.frontend_api_key01 = "test-key-1"
        cfg.gemini_model = "gemini-3.6-flash"
        cfg.get_slot_model.return_value = "gemini-3.6-flash"
        cfg.planner_api_key01 = None
        cfg.backend_api_key01 = None
        cfg.database_api_key01 = None
        cfg.qa_api_key01 = None
        cfg.debug_api_key01 = None
        cfg.review_api_key01 = None

        with patch("google.genai.Client"):
            providers = _build_slot_providers(cfg)
            assert "FRONTEND_API_KEY01" in providers
            assert "groq" not in providers
            assert "grok" not in providers
