"""NVIDIA NIM as an additional provider.

NIM speaks the OpenAI chat-completions protocol, so it reuses the adapter Groq
and OpenAI already use. That reuse is exactly what these tests have to justify:
the risk in an integration like this is not that NVIDIA fails to work, it is
that adding it changes something that already did. So the suite checks the new
provider end to end *and* asserts that the existing five are untouched.

Nothing here reaches the network. The adapter's own client is kept — real base
URL, real headers — and only its transport is replaced, so the request under
assertion is the one that would have gone to NVIDIA.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
pytestmark = pytest.mark.skip(reason="Superseded by Phase 2 role-based provider architecture; see test_role_based_manager.py")

from app.core.config import Settings
from app.core.enums import ErrorKind, TaskKind
from app.llm.cache import PromptCache
from app.llm.manager import ProviderManager
from app.llm.providers.base import ProviderAdapter, ProviderSpec
from app.llm.providers.openai_compatible import OpenAICompatibleAdapter
from app.llm.providers.registry import PROVIDER_FACTORIES, PROVIDER_LABELS, build_providers
from app.llm.retry import RetryManager, RetryPolicy
from app.llm.routing import DEFAULT_TASK_PREFERENCES, RoutingTable
from app.llm.schema import obj, string
from app.llm.types import PromptBundle

SCHEMA = obj({"name": string("Project name.")})

#: The five providers that existed before this integration. Named explicitly so
#: a regression that drops one fails here rather than in production.
EXISTING_PROVIDERS = ("anthropic", "gemini", "groq", "openai", "ollama")


def build_settings(**overrides: Any) -> Settings:
    """Settings with NVIDIA credentials, isolated from the developer's `.env`.

    `conftest` blanks `AEGIS_ENV_FILE`, so no dotenv source is active and these
    values are the whole configuration.
    """
    defaults: dict[str, Any] = {"nvidia_api_key": "nvapi-test-key"}
    defaults.update(overrides)
    return Settings(**defaults)


def nvidia_adapter(config: Settings | None = None) -> OpenAICompatibleAdapter:
    """The NVIDIA adapter exactly as the registry builds it."""
    config = config or build_settings()
    adapters = {adapter.key: adapter for adapter in build_providers(config)}
    adapter = adapters["nvidia"]
    assert isinstance(adapter, OpenAICompatibleAdapter)
    return adapter


def respond(adapter: OpenAICompatibleAdapter, handler: Any) -> list[httpx.Request]:
    """Route this adapter's requests to `handler`, recording each one.

    The client itself is left alone — base URL and Authorization header are
    the ones the adapter really constructed.
    """
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request) if callable(handler) else handler

    client = adapter._http()  # noqa: SLF001 - swapping transport is the point
    client._transport = httpx.MockTransport(record)  # noqa: SLF001
    return seen


def completion(content: str = '{"name": "Aegis"}', **overrides: Any) -> httpx.Response:
    """A well-formed NIM chat-completions reply."""
    payload: dict[str, Any] = {
        # "model": "nvidia/nemotron-3-ultra-550b-a55b",
          "model": "nvidia/nemotron-3-ultra-550b-a55b",
        "choices": [
            {"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 1200, "completion_tokens": 300},
    }
    payload.update(overrides)
    return httpx.Response(200, json=payload)


class TestConfiguration:
    """NVIDIA is configured the way every other provider is."""

    def test_the_api_key_is_read_from_the_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-from-env")
        assert Settings().nvidia_api_key == "nvapi-from-env"

    def test_the_model_is_configurable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NVIDIA_MODEL", "deepseek-ai/deepseek-r1")
        assert Settings().provider_models["nvidia"] == "deepseek-ai/deepseek-r1"

    def test_the_base_url_is_configurable_for_self_hosted_nim(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A NIM container on your own hardware is the same protocol at a
        # different address, which is the whole reason this is a setting.
        monkeypatch.setenv("NVIDIA_BASE_URL", "http://gpu-box:8000/v1")
        assert Settings().nvidia_base_url == "http://gpu-box:8000/v1"

    def test_the_hosted_catalogue_is_the_default_endpoint(self) -> None:
        assert Settings().nvidia_base_url == "https://integrate.api.nvidia.com/v1"

    def test_no_key_leaves_nvidia_unconfigured_rather_than_missing(self) -> None:
        config = build_settings(nvidia_api_key=None)
        # Still built and still listed: "why is NVIDIA not being used?" has to
        # be answerable from the dashboard.
        assert "nvidia" in {adapter.key for adapter in build_providers(config)}
        assert not nvidia_adapter(config).is_configured
        assert "nvidia" not in config.configured_providers

    def test_a_blank_key_counts_as_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NVIDIA_API_KEY", "   ")
        assert Settings().nvidia_api_key is None

    def test_context_limits_are_unset_by_default(self) -> None:
        # NIM's catalogue spans 8k to well beyond 128k. Declaring one number
        # for all of them would either strand a prompt a model could hold or
        # send it to one that cannot.
        config = build_settings()
        assert config.nvidia_max_prompt_tokens == 0
        assert nvidia_adapter(config).spec.max_prompt_tokens == 0

    def test_declared_context_limits_reach_the_provider_spec(self) -> None:
        config = build_settings(nvidia_max_prompt_tokens=120_000)
        assert nvidia_adapter(config).spec.max_prompt_tokens == 120_000

    def test_nvidia_can_be_named_as_the_preferred_provider(self) -> None:
        config = build_settings(llm_provider="nvidia")
        assert config.resolved_provider_priority[0] == "nvidia"
        assert config.active_model == config.nvidia_model
        assert config.active_api_key_variable == "NVIDIA_API_KEY"

    def test_nvidia_can_be_switched_off(self) -> None:
        config = build_settings(llm_disabled_providers=["nvidia"])
        assert "nvidia" not in config.configured_providers
        assert not nvidia_adapter(config).spec.enabled


class TestInitialisation:
    """The provider is built through the existing abstraction, not beside it."""

    def test_it_is_registered_with_the_existing_factory_map(self) -> None:
        assert "nvidia" in PROVIDER_FACTORIES
        assert "nvidia" in PROVIDER_LABELS

    def test_it_implements_the_shared_provider_contract(self) -> None:
        adapter = nvidia_adapter()
        assert isinstance(adapter, ProviderAdapter)
        # Reuse, not a parallel implementation: a second HTTP client for the
        # same protocol is how five providers become five behaviours.
        assert isinstance(adapter, OpenAICompatibleAdapter)

    def test_it_is_configured_once_a_key_is_present(self) -> None:
        assert nvidia_adapter().is_configured

    def test_it_carries_the_configured_model_and_a_display_name(self) -> None:
        adapter = nvidia_adapter(build_settings(nvidia_model="qwen/qwen2.5-coder-32b-instruct"))
        assert adapter.model == "qwen/qwen2.5-coder-32b-instruct"
        assert adapter.display_name == "NVIDIA NIM"


class TestRequestConstruction:
    """What actually goes over the wire to NIM."""

    async def test_the_key_is_sent_as_a_bearer_token_to_the_chat_endpoint(self) -> None:
        adapter = nvidia_adapter()
        seen = respond(adapter, completion())

        await adapter.complete_text(PromptBundle(cacheable_system="s", user_message="u"))

        request = seen[0]
        assert str(request.url) == "https://integrate.api.nvidia.com/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer nvapi-test-key"

    async def test_the_configured_model_and_both_system_segments_are_sent(self) -> None:
        adapter = nvidia_adapter(build_settings(nvidia_model="meta/llama-3.1-405b-instruct"))
        seen = respond(adapter, completion())

        await adapter.complete_text(
            PromptBundle(
                cacheable_system="STABLE PREFIX",
                volatile_system="PER RUN",
                user_message="build it",
            )
        )

        body = json.loads(seen[0].content)
        assert body["model"] == "meta/llama-3.1-405b-instruct"
        system = body["messages"][0]["content"]
        assert system.index("STABLE PREFIX") < system.index("PER RUN")
        assert body["messages"][1]["content"] == "build it"

    async def test_json_object_is_the_default_structured_mode(self) -> None:
        adapter = nvidia_adapter()
        seen = respond(adapter, completion())

        await adapter.complete_structured(
            PromptBundle(cacheable_system="s", user_message="u", schema=SCHEMA)
        )

        body = json.loads(seen[0].content)
        assert body["response_format"] == {"type": "json_object"}
        # The schema still travels in the prompt, because json_object only
        # guarantees *valid* JSON, not the right shape.
        assert "name" in body["messages"][0]["content"]

    async def test_schema_enforcement_is_requested_when_the_model_supports_it(self) -> None:
        adapter = nvidia_adapter(build_settings(nvidia_structured_output="json_schema"))
        seen = respond(adapter, completion())

        await adapter.complete_structured(
            PromptBundle(cacheable_system="s", user_message="u", schema=SCHEMA)
        )

        body = json.loads(seen[0].content)
        assert body["response_format"]["type"] == "json_schema"
        assert body["response_format"]["json_schema"]["schema"] == SCHEMA

    async def test_a_model_without_response_format_gets_the_schema_in_the_prompt(self) -> None:
        adapter = nvidia_adapter(build_settings(nvidia_structured_output="prompt"))
        seen = respond(adapter, completion())

        await adapter.complete_structured(
            PromptBundle(cacheable_system="s", user_message="u", schema=SCHEMA)
        )

        body = json.loads(seen[0].content)
        assert "response_format" not in body
        assert "name" in body["messages"][0]["content"]

    async def test_output_is_clamped_when_a_ceiling_is_declared(self) -> None:
        adapter = nvidia_adapter(build_settings(nvidia_max_output_tokens=4096))
        seen = respond(adapter, completion())

        await adapter.complete_text(
            PromptBundle(cacheable_system="s", user_message="u", max_tokens=32000)
        )

        assert json.loads(seen[0].content)["max_tokens"] == 4096

    async def test_the_requested_output_is_sent_unchanged_with_no_ceiling(self) -> None:
        adapter = nvidia_adapter()
        seen = respond(adapter, completion())

        await adapter.complete_text(
            PromptBundle(cacheable_system="s", user_message="u", max_tokens=32000)
        )

        assert json.loads(seen[0].content)["max_tokens"] == 32000


class TestResponseParsing:
    """A NIM reply becomes the same objects every other provider returns."""

    async def test_text_and_usage_are_read_off_the_response(self) -> None:
        adapter = nvidia_adapter()
        respond(adapter, completion(content="hello from nim"))

        result = await adapter.complete_text(PromptBundle(cacheable_system="s", user_message="u"))

        assert result.text == "hello from nim"
        assert result.usage.input_tokens == 1200
        assert result.usage.output_tokens == 300
        assert result.model == "nvidia/nemotron-3-ultra-550b-a55b"

    async def test_structured_output_is_parsed_and_validated(self) -> None:
        adapter = nvidia_adapter()
        respond(adapter, completion(content='{"name": "Aegis"}'))

        result = await adapter.complete_structured(
            PromptBundle(cacheable_system="s", user_message="u", schema=SCHEMA)
        )

        assert result.data == {"name": "Aegis"}

    async def test_a_fenced_json_block_is_unwrapped(self) -> None:
        # Open models told to emit bare JSON wrap it in ```json anyway. Failing
        # over for a formatting habit would waste a provider.
        adapter = nvidia_adapter()
        respond(adapter, completion(content='```json\n{"name": "Aegis"}\n```'))

        result = await adapter.complete_structured(
            PromptBundle(cacheable_system="s", user_message="u", schema=SCHEMA)
        )

        assert result.data == {"name": "Aegis"}

    async def test_harmless_unknown_properties_are_removed_before_validation(self) -> None:
        adapter = nvidia_adapter()
        respond(adapter, completion(content='{"name": "Aegis", "overview2": "extra"}'))

        result = await adapter.complete_structured(
            PromptBundle(cacheable_system="s", user_message="u", schema=SCHEMA)
        )

        assert result.data == {"name": "Aegis"}

    async def test_nested_unknown_properties_are_removed_before_validation(self) -> None:
        schema = obj({"project": obj({"name": string("Project name.")})})
        adapter = nvidia_adapter()
        respond(
            adapter,
            completion(
                content=(
                    '{"project": {"name": "Aegis", "provider_note": "extra"}, '
                    '"overview2": "extra"}'
                )
            ),
        )

        result = await adapter.complete_structured(
            PromptBundle(cacheable_system="s", user_message="u", schema=schema)
        )

        assert result.data == {"project": {"name": "Aegis"}}

    @pytest.mark.parametrize(
        "content",
        [
            '{"name": 123}',
            '{"unrelated": 1}',
            '{"name":',
        ],
    )
    async def test_invalid_structured_output_still_fails_over(self, content: str) -> None:
        adapter = nvidia_adapter()
        respond(adapter, completion(content=content))

        with pytest.raises(Exception) as exc:
            await adapter.complete_structured(
                PromptBundle(cacheable_system="s", user_message="u", schema=SCHEMA)
            )

        assert adapter.classify(exc.value) is ErrorKind.UNAVAILABLE

    async def test_nvidia_success_after_gemini_failure_does_not_call_groq(self) -> None:
        gemini = OpenAICompatibleAdapter(
            ProviderSpec("gemini", "Google Gemini", "test-model", priority=0),
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            api_key="gemini-test-key",
            timeout_seconds=1,
        )
        gemini_requests = respond(
            gemini, httpx.Response(429, json={"error": {"message": "quota exceeded"}})
        )
        nvidia = nvidia_adapter()
        respond(nvidia, completion(content='{"name": "Aegis", "overview2": "extra"}'))
        groq = OpenAICompatibleAdapter(
            ProviderSpec("groq", "Groq", "test-model", priority=1),
            base_url="https://api.groq.com/openai/v1",
            api_key="gsk-test-key",
            timeout_seconds=1,
        )
        groq_requests = respond(groq, lambda _: pytest.fail("Groq must not be called"))
        config = build_settings(llm_cache_enabled=False, llm_task_routing_enabled=False)
        manager = ProviderManager(
            providers=[gemini, nvidia, groq],
            config=config,
            cache=PromptCache(enabled=False),
            retry=RetryManager(RetryPolicy(max_retries=0)),
            routing=RoutingTable(
                priority=("gemini", "nvidia", "groq"), task_routing_enabled=False
            ),
        )

        result = await manager.complete_structured(
            PromptBundle(cacheable_system="s", user_message="u", schema=SCHEMA)
        )

        assert result.data == {"name": "Aegis"}
        assert len(gemini_requests) == 1
        assert groq_requests == []

    async def test_output_that_ignores_the_schema_is_a_failover_not_a_result(self) -> None:
        adapter = nvidia_adapter()
        respond(adapter, completion(content='{"unrelated": 1}'))

        with pytest.raises(Exception) as exc:
            await adapter.complete_structured(
                PromptBundle(cacheable_system="s", user_message="u", schema=SCHEMA)
            )

        # Another provider may well answer this prompt correctly, so the
        # manager must be allowed to try one.
        assert adapter.classify(exc.value) is ErrorKind.UNAVAILABLE
        assert adapter.classify(exc.value).should_failover


class TestErrorHandling:
    """Every NVIDIA failure resolves to retry, fail over, or stop."""

    async def test_an_invalid_api_key_is_an_auth_failure(self) -> None:
        adapter = nvidia_adapter()
        # NIM answers with a problem-details envelope, not OpenAI's shape.
        respond(
            adapter,
            httpx.Response(
                401, json={"status": 401, "title": "Unauthorized", "detail": "Invalid API key"}
            ),
        )

        with pytest.raises(Exception) as exc:
            await adapter.complete_text(PromptBundle(cacheable_system="s", user_message="u"))

        assert adapter.classify(exc.value) is ErrorKind.AUTH
        assert "Invalid API key" in str(exc.value), "the vendor's reason must survive"
        assert not adapter.classify(exc.value).should_retry, "a rejected key never improves"
        assert adapter.classify(exc.value).should_failover

    async def test_the_api_key_never_appears_in_the_error(self) -> None:
        adapter = nvidia_adapter()
        respond(adapter, httpx.Response(401, json={"detail": "Unauthorized"}))

        with pytest.raises(Exception) as exc:
            await adapter.complete_text(PromptBundle(cacheable_system="s", user_message="u"))

        raised = exc.value
        assert "nvapi-test-key" not in str(raised)
        assert "nvapi-test-key" not in str(getattr(raised, "details", {}))

    async def test_a_rate_limit_cools_nvidia_down_instead_of_retrying_it(self) -> None:
        adapter = nvidia_adapter()
        respond(
            adapter,
            httpx.Response(429, json={"detail": "Rate limit exceeded for this endpoint"}),
        )

        with pytest.raises(Exception) as exc:
            await adapter.complete_text(PromptBundle(cacheable_system="s", user_message="u"))

        assert adapter.classify(exc.value) is ErrorKind.QUOTA
        assert not adapter.classify(exc.value).should_retry
        assert adapter.classify(exc.value).should_failover

    async def test_a_timeout_is_retried_against_nvidia(self) -> None:
        adapter = nvidia_adapter()

        def timeout(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timed out", request=request)

        respond(adapter, timeout)

        with pytest.raises(Exception) as exc:
            await adapter.complete_text(PromptBundle(cacheable_system="s", user_message="u"))

        assert adapter.classify(exc.value) is ErrorKind.RETRYABLE
        assert adapter.classify(exc.value).should_retry
        assert "timed out" in str(exc.value).lower()

    async def test_a_connection_failure_is_retried(self) -> None:
        adapter = nvidia_adapter()

        def refused(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        respond(adapter, refused)

        with pytest.raises(Exception) as exc:
            await adapter.complete_text(PromptBundle(cacheable_system="s", user_message="u"))

        assert adapter.classify(exc.value) is ErrorKind.RETRYABLE

    async def test_an_unknown_model_moves_on_rather_than_retrying(self) -> None:
        adapter = nvidia_adapter(build_settings(nvidia_model="meta/does-not-exist"))
        respond(adapter, httpx.Response(404, json={"detail": "Function or version not found"}))

        with pytest.raises(Exception) as exc:
            await adapter.complete_text(PromptBundle(cacheable_system="s", user_message="u"))

        assert adapter.classify(exc.value) is ErrorKind.UNAVAILABLE
        assert "meta/does-not-exist" in str(exc.value), "the message must name the bad model"

    async def test_a_server_error_is_retried(self) -> None:
        adapter = nvidia_adapter()
        respond(adapter, httpx.Response(503, json={"detail": "Service temporarily unavailable"}))

        with pytest.raises(Exception) as exc:
            await adapter.complete_text(PromptBundle(cacheable_system="s", user_message="u"))

        assert adapter.classify(exc.value) is ErrorKind.RETRYABLE

    async def test_a_prompt_too_large_for_the_model_is_handed_on(self) -> None:
        adapter = nvidia_adapter()
        respond(
            adapter,
            httpx.Response(400, json={"detail": "Input exceeds maximum context length"}),
        )

        with pytest.raises(Exception) as exc:
            await adapter.complete_text(PromptBundle(cacheable_system="s", user_message="u"))

        # A model with a larger window answers it fine, so this is a fact about
        # the provider rather than about the request.
        assert adapter.classify(exc.value) is ErrorKind.UNAVAILABLE

    async def test_an_unreadable_error_body_still_produces_a_reason(self) -> None:
        adapter = nvidia_adapter()
        respond(adapter, httpx.Response(500, text="<html>Bad Gateway</html>"))

        with pytest.raises(Exception) as exc:
            await adapter.complete_text(PromptBundle(cacheable_system="s", user_message="u"))

        assert "NVIDIA NIM" in str(exc.value)


class TestProviderSelection:
    """The configured global failover chain remains fixed."""

    def test_the_fixed_provider_order_is_preserved(self) -> None:
        assert build_settings().resolved_provider_priority == [
            "gemini",
            "nvidia",
            "sambanova_deepseek",
            "sambanova_gpt_oss",
            "groq",
            "gemma",
            "lfm",
            "ollama",
        ]

    def test_gemini_is_the_default_preferred_provider(self) -> None:
        # Adding an engine must not start the car with it. Read off the field
        # default rather than an instance, so an ambient LLM_PROVIDER on the
        # developer's machine cannot decide the answer.
        assert Settings.model_fields["llm_provider"].default == "gemini"

    @pytest.mark.parametrize("task", list(TaskKind))
    def test_it_is_reachable_for_every_task_kind(self, task: TaskKind) -> None:
        table = RoutingTable(priority=tuple(build_settings().resolved_provider_priority))
        assert "nvidia" in table.order_for(task)

    @pytest.mark.parametrize("task", list(TaskKind))
    def test_it_never_leads_the_order_for_any_task(self, task: TaskKind) -> None:
        table = RoutingTable(priority=tuple(build_settings().resolved_provider_priority))
        assert table.order_for(task)[0] != "nvidia"

    def test_it_is_preferred_over_a_small_free_tier_for_heavy_work(self) -> None:
        table = RoutingTable(priority=tuple(build_settings().resolved_provider_priority))
        order = table.order_for(TaskKind.REVIEW)
        # A full review prompt does not fit a 12k-per-minute budget; NIM's
        # large-context models are the point of adding it.
        assert order.index("nvidia") < order.index("groq")

    def test_it_is_chosen_only_after_the_providers_ahead_of_it_are_out(self) -> None:
        table = RoutingTable(priority=tuple(build_settings().resolved_provider_priority))
        order = table.order_for(TaskKind.CODE_GENERATION, available={"nvidia", "ollama"})
        assert order[0] == "nvidia"


class TestExistingProvidersAreUnaffected:
    """The regression half: adding NVIDIA must change nothing that worked."""

    def test_every_original_provider_is_still_built(self) -> None:
        config = build_settings(
            llm_provider_priority=[
                "nvidia",
                "sambanova_deepseek",
                "sambanova_gpt_oss",
                "groq",
                "gemma",
                "lfm",
                "ollama",
                "openai",
                "anthropic",
            ]
        )
        keys = {adapter.key for adapter in build_providers(config)}
        assert set(EXISTING_PROVIDERS) <= keys

    def test_every_original_provider_is_still_registered(self) -> None:
        for key in EXISTING_PROVIDERS:
            assert key in PROVIDER_FACTORIES
            assert key in PROVIDER_LABELS

    def test_their_credentials_and_models_still_resolve(self) -> None:
        config = build_settings()
        for key in EXISTING_PROVIDERS:
            assert key in config.provider_credentials
            assert config.provider_models[key], f"{key} lost its model"

    def test_existing_provider_order_matches_the_configured_chain(self) -> None:
        priority = build_settings().resolved_provider_priority
        existing = [key for key in priority if key in EXISTING_PROVIDERS]
        assert existing == ["gemini", "groq", "ollama"]

    @pytest.mark.parametrize("task", list(TaskKind))
    def test_task_preferences_kept_their_original_sequence(self, task: TaskKind) -> None:
        without_nvidia = tuple(
            key for key in DEFAULT_TASK_PREFERENCES[task] if key != "nvidia"
        )
        original = {
            TaskKind.REASONING: ("gemini", "anthropic", "openai", "groq", "ollama"),
            TaskKind.CODE_GENERATION: ("gemini", "anthropic", "openai", "groq", "ollama"),
            TaskKind.REVIEW: ("gemini", "anthropic", "openai", "groq", "ollama"),
            TaskKind.DOCUMENTATION: ("groq", "gemini", "ollama", "openai", "anthropic"),
            TaskKind.SUMMARY: ("groq", "gemini", "ollama", "openai", "anthropic"),
        }[task]
        assert without_nvidia == original

    def test_groq_still_declares_its_free_tier_budget(self) -> None:
        adapters = {adapter.key: adapter for adapter in build_providers(build_settings())}
        assert adapters["groq"].spec.max_prompt_tokens == 8000
        assert adapters["groq"].spec.max_output_tokens == 3500

    def test_ollama_still_needs_no_credentials(self) -> None:
        adapters = {adapter.key: adapter for adapter in build_providers(build_settings())}
        assert adapters["ollama"].is_configured

    def test_an_unset_nvidia_key_does_not_disturb_the_others(self) -> None:
        config = build_settings(nvidia_api_key=None, google_api_key="g", groq_api_key="gsk")
        assert "nvidia" not in config.configured_providers
        assert {"gemini", "groq"} <= set(config.configured_providers)
        assert config.llm_configured
