"""SambaNova logical providers reuse the shared OpenAI-compatible adapter."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
pytestmark = pytest.mark.skip(reason="Superseded by Phase 2 role-based provider architecture; see test_role_based_manager.py")

from app.core.config import Settings
from app.core.enums import ErrorKind
from app.llm.providers.openai_compatible import OpenAICompatibleAdapter
from app.llm.providers.registry import PROVIDER_FACTORIES, PROVIDER_LABELS, build_providers
from app.llm.schema import obj, string
from app.llm.types import PromptBundle

SCHEMA = obj({"name": string("Project name.")})
KEYS = ("sambanova_deepseek", "sambanova_gpt_oss")
MODELS = {"sambanova_deepseek": "DeepSeek-V3.1", "sambanova_gpt_oss": "gpt-oss-120b"}
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


def build_settings(**overrides: Any) -> Settings:
    defaults: dict[str, Any] = {"sambanova_api_key": "test-sambanova-key"}
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
            "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 4},
        },
    )


class TestSambaNovaConfiguration:
    def test_the_fixed_global_order_is_preserved(self) -> None:
        settings = build_settings()
        assert settings.resolved_provider_priority == EXPECTED_ORDER
        assert not settings.llm_task_routing_enabled

    @pytest.mark.parametrize("key", KEYS)
    def test_logical_provider_is_registered_with_the_shared_key_and_model(self, key: str) -> None:
        settings = build_settings()
        assert key in PROVIDER_FACTORIES
        assert key in PROVIDER_LABELS
        assert settings.provider_credentials[key] == "test-sambanova-key"
        assert settings.provider_models[key] == MODELS[key]
        assert adapter(key, settings).model == MODELS[key]

    def test_missing_shared_key_leaves_both_logical_providers_unconfigured(self) -> None:
        settings = build_settings(sambanova_api_key=None)
        assert set(KEYS).isdisjoint(settings.configured_providers)
        assert not adapter("sambanova_deepseek", settings).is_configured
        assert not adapter("sambanova_gpt_oss", settings).is_configured

    @pytest.mark.parametrize("key", KEYS)
    def test_each_preferred_logical_provider_names_the_shared_key(self, key: str) -> None:
        assert build_settings(llm_provider=key).active_api_key_variable == "SAMBANOVA_API_KEY"


class TestSambaNovaRequests:
    @pytest.mark.parametrize("key", KEYS)
    async def test_structured_request_uses_sambanova_and_validates_the_result(
        self, key: str
    ) -> None:
        selected = adapter(key)
        requests = respond(selected, completion())

        result = await selected.complete_structured(
            PromptBundle(cacheable_system="s", user_message="u", schema=SCHEMA)
        )

        request = requests[0]
        assert str(request.url) == "https://api.sambanova.ai/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-sambanova-key"
        assert json.loads(request.content)["model"] == MODELS[key]
        assert json.loads(request.content)["response_format"]["type"] == "json_schema"
        assert result.data == {"name": "Aegis"}

    async def test_invalid_structured_response_is_rejected_as_provider_failure(self) -> None:
        selected = adapter("sambanova_deepseek")
        respond(selected, completion('{"name": 42}'))

        with pytest.raises(Exception) as exc:
            await selected.complete_structured(
                PromptBundle(cacheable_system="s", user_message="u", schema=SCHEMA)
            )

        assert selected.classify(exc.value) is ErrorKind.UNAVAILABLE

    @pytest.mark.parametrize(
        ("status", "payload", "expected"),
        [
            (429, {"error": {"message": "rate limit"}}, ErrorKind.QUOTA),
            (401, {"error": {"message": "invalid key"}}, ErrorKind.AUTH),
            (404, {"error": {"message": "missing model"}}, ErrorKind.UNAVAILABLE),
            (400, {"error": {"message": "invalid parameter"}}, ErrorKind.FATAL),
        ],
    )
    async def test_error_statuses_keep_existing_classification(
        self, status: int, payload: dict[str, Any], expected: ErrorKind
    ) -> None:
        selected = adapter("sambanova_gpt_oss")
        respond(selected, httpx.Response(status, json=payload))

        with pytest.raises(Exception) as exc:
            await selected.complete_text(PromptBundle(cacheable_system="s", user_message="u"))

        assert selected.classify(exc.value) is expected
