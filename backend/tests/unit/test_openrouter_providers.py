"""Gemma and LFM are logical OpenRouter providers, not new SDK integrations."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
pytestmark = pytest.mark.skip(reason="Superseded by Phase 2 role-based provider architecture; see test_role_based_manager.py")

from app.core.config import Settings
from app.llm.providers.openai_compatible import OpenAICompatibleAdapter
from app.llm.providers.registry import PROVIDER_FACTORIES, PROVIDER_LABELS, build_providers
from app.llm.schema import obj, string
from app.llm.types import PromptBundle

SCHEMA = obj({"name": string("Project name.")})
EXPECTED_ORDER = [
    "gemini",
    "nvidia",
    "sambanova_deepseek",
    "sambanova_gpt_oss",
    "groq",
    "gemma",
    "lfm",
    "ollama",
]
MODELS = {
    "gemma": "google/gemma-4-31b-it:free",
    "lfm": "liquid/lfm-2.5-2.6b:free",
}


def build_settings(**overrides: Any) -> Settings:
    defaults: dict[str, Any] = {"openrouter_api_key": "test-openrouter-key"}
    defaults.update(overrides)
    return Settings(**defaults)


def adapter(key: str, config: Settings | None = None) -> OpenAICompatibleAdapter:
    selected = {item.key: item for item in build_providers(config or build_settings())}[key]
    assert isinstance(selected, OpenAICompatibleAdapter)
    return selected


def respond(adapter: OpenAICompatibleAdapter, response: httpx.Response) -> list[httpx.Request]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return response

    adapter._http()._transport = httpx.MockTransport(record)  # noqa: SLF001
    return seen


def completion(content: str = '{"name": "Aegis"}') -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "openrouter-test-model",
            "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 4},
        },
    )


class TestOpenRouterConfiguration:
    def test_the_exact_fixed_order_and_global_routing_setting_are_preserved(self) -> None:
        settings = build_settings()
        assert settings.resolved_provider_priority == EXPECTED_ORDER
        assert not settings.llm_task_routing_enabled

    @pytest.mark.parametrize("key", ["gemma", "lfm"])
    def test_provider_is_registered_and_uses_the_expected_model(self, key: str) -> None:
        settings = build_settings()
        assert key in PROVIDER_FACTORIES
        assert key in PROVIDER_LABELS
        assert settings.provider_credentials[key] == "test-openrouter-key"
        assert settings.provider_models[key] == MODELS[key]
        assert adapter(key, settings).model == MODELS[key]

    def test_both_providers_are_unconfigured_without_the_shared_key(self) -> None:
        settings = build_settings(openrouter_api_key=None)
        assert {"gemma", "lfm"}.isdisjoint(settings.configured_providers)
        assert not adapter("gemma", settings).is_configured
        assert not adapter("lfm", settings).is_configured

    @pytest.mark.parametrize("key", ["gemma", "lfm"])
    def test_the_preferred_logical_provider_names_the_shared_key(self, key: str) -> None:
        assert build_settings(llm_provider=key).active_api_key_variable == "OPENROUTER_API_KEY"


class TestOpenRouterRequests:
    @pytest.mark.parametrize("key", ["gemma", "lfm"])
    async def test_requests_use_openrouter_and_complete_structured_output(self, key: str) -> None:
        selected = adapter(key)
        seen = respond(selected, completion())

        result = await selected.complete_structured(
            PromptBundle(cacheable_system="s", user_message="u", schema=SCHEMA)
        )

        request = seen[0]
        body = json.loads(request.content)
        assert str(request.url) == "https://openrouter.ai/api/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-openrouter-key"
        assert body["model"] == MODELS[key]
        assert result.data == {"name": "Aegis"}

    async def test_gemma_uses_json_object_and_lfm_requests_json_schema(self) -> None:
        gemma = adapter("gemma")
        gemma_requests = respond(gemma, completion())
        await gemma.complete_structured(
            PromptBundle(cacheable_system="s", user_message="u", schema=SCHEMA)
        )

        lfm = adapter("lfm")
        lfm_requests = respond(lfm, completion())
        await lfm.complete_structured(
            PromptBundle(cacheable_system="s", user_message="u", schema=SCHEMA)
        )

        assert json.loads(gemma_requests[0].content)["response_format"] == {"type": "json_object"}
        assert json.loads(lfm_requests[0].content)["response_format"]["type"] == "json_schema"
