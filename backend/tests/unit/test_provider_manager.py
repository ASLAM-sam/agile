"""Multi-provider orchestration: routing, retry, failover, cache and health.

The promise being tested is that a run survives a provider outage without the
user doing anything. Every test here is a way that promise could quietly fail —
failing over when it should retry, retrying when it should fail fast, cooling
down a provider that recovered, or serving a cache entry that inflates the
token report.

Providers are scripted fakes. Nothing here touches a network.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest
pytestmark = pytest.mark.skip(reason="Superseded by Phase 2 role-based provider architecture; see test_role_based_manager.py")

from app.core.enums import ErrorKind, ProviderStatus, TaskKind
from app.core.exceptions import LLMError
from app.llm.cache import PromptCache
from app.llm.errors import AllProvidersFailed, kind_of, tag
from app.llm.health import ProviderHealth
from app.llm.manager import ProviderManager
from app.llm.providers.base import ProviderAdapter, ProviderSpec
from app.llm.retry import RetryManager, RetryPolicy
from app.llm.routing import RoutingTable, task_kind_for_agent
from app.llm.types import Completion, PromptBundle, TextCompletion, TokenUsage

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
    "additionalProperties": False,
}


class FakeProvider(ProviderAdapter):
    """A provider that does exactly what the test tells it to.

    `script` is consumed one entry per call: an exception is raised, anything
    else is returned. A shorter script than the number of calls repeats its
    last entry, so "always fails" needs one entry rather than ten.
    """

    def __init__(
        self,
        key: str,
        *,
        script: list[Any] | None = None,
        priority: int = 0,
        configured: bool = True,
        enabled: bool = True,
    ) -> None:
        super().__init__(
            ProviderSpec(
                key=key,
                display_name=key.title(),
                model=f"{key}-model",
                priority=priority,
                enabled=enabled,
            )
        )
        self.script = script or [_completion(key)]
        self.calls = 0
        self._configured = configured

    @property
    def is_configured(self) -> bool:
        return self._configured

    def _next(self) -> Any:
        index = min(self.calls, len(self.script) - 1)
        self.calls += 1
        outcome = self.script[index]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    async def complete_structured(self, prompt: PromptBundle) -> Completion:
        return self._next()

    async def complete_text(self, prompt: PromptBundle) -> TextCompletion:
        result = self._next()
        if isinstance(result, Completion):
            return TextCompletion(text=result.raw_text, usage=result.usage, model=result.model)
        return result

    def classify(self, error: BaseException) -> ErrorKind:
        return kind_of(error)


def _completion(provider: str) -> Completion:
    return Completion(
        data={"ok": True, "served_by": provider},
        usage=TokenUsage(input_tokens=10, output_tokens=5),
        stop_reason="stop",
        model=f"{provider}-model",
        raw_text='{"ok": true}',
    )


def fail(kind: ErrorKind, message: str = "boom") -> LLMError:
    return tag(LLMError(message), kind)  # type: ignore[return-value]


def bundle(agent: str = "solution_architect", *, message: str = "do the thing") -> PromptBundle:
    return PromptBundle(
        cacheable_system="system",
        volatile_system="state",
        user_message=message,
        schema=SCHEMA,
        metadata={"agent": agent, "run_id": "run-1"},
    )


def manager(
    *providers: FakeProvider,
    cache: PromptCache | None = None,
    retries: int = 0,
    failover: bool = True,
    task_routing: bool = False,
) -> ProviderManager:
    """A manager with no delays, so tests do not sleep through backoff."""
    from app.core.config import Settings

    config = Settings(
        _env_file=None,  # type: ignore[call-arg]
        llm_failover_enabled=failover,
        llm_task_routing_enabled=task_routing,
    )
    return ProviderManager(
        providers=list(providers),
        config=config,
        cache=cache or PromptCache(enabled=False),
        retry=RetryManager(RetryPolicy(max_retries=retries, base_delay_seconds=0.0, jitter=0.0)),
        routing=RoutingTable(
            priority=tuple(p.key for p in providers), task_routing_enabled=task_routing
        ),
    )


class TestAutomaticFailover:
    """A provider that cannot serve must hand the request on, invisibly."""

    async def test_quota_moves_to_the_next_provider(self) -> None:
        primary = FakeProvider("gemini", script=[fail(ErrorKind.QUOTA, "quota exceeded")])
        backup = FakeProvider("groq")
        result = await manager(primary, backup).complete_structured(bundle())

        assert result.data["served_by"] == "groq"
        assert primary.calls == 1 and backup.calls == 1

    @pytest.mark.parametrize("kind", [ErrorKind.QUOTA, ErrorKind.AUTH, ErrorKind.UNAVAILABLE])
    async def test_every_provider_level_failure_fails_over(self, kind: ErrorKind) -> None:
        primary = FakeProvider("gemini", script=[fail(kind)])
        backup = FakeProvider("groq")
        result = await manager(primary, backup).complete_structured(bundle())
        assert result.data["served_by"] == "groq"

    async def test_it_walks_the_whole_chain(self) -> None:
        a = FakeProvider("gemini", script=[fail(ErrorKind.QUOTA)])
        b = FakeProvider("groq", script=[fail(ErrorKind.AUTH)])
        c = FakeProvider("ollama", script=[fail(ErrorKind.UNAVAILABLE)])
        d = FakeProvider("openai")
        result = await manager(a, b, c, d).complete_structured(bundle())
        assert result.data["served_by"] == "openai"

    async def test_a_malformed_request_is_not_spent_on_every_provider(self) -> None:
        # FATAL means the request is wrong. Trying five vendors costs five
        # quotas to collect five identical rejections.
        primary = FakeProvider("gemini", script=[fail(ErrorKind.FATAL, "bad schema")])
        backup = FakeProvider("groq")
        with pytest.raises(LLMError, match="bad schema"):
            await manager(primary, backup).complete_structured(bundle())
        assert backup.calls == 0

    async def test_failover_can_be_switched_off(self) -> None:
        primary = FakeProvider("gemini", script=[fail(ErrorKind.QUOTA)])
        backup = FakeProvider("groq")
        with pytest.raises(LLMError):
            await manager(primary, backup, failover=False).complete_structured(bundle())
        assert backup.calls == 0

    async def test_exhausting_every_provider_names_each_reason(self) -> None:
        a = FakeProvider("gemini", script=[fail(ErrorKind.QUOTA, "out of quota")])
        b = FakeProvider("groq", script=[fail(ErrorKind.AUTH, "bad key")])
        with pytest.raises(AllProvidersFailed) as exc:
            await manager(a, b).complete_structured(bundle())
        assert "out of quota" in str(exc.value)
        assert "bad key" in str(exc.value)

    async def test_text_completions_fail_over_too(self) -> None:
        primary = FakeProvider("gemini", script=[fail(ErrorKind.QUOTA)])
        backup = FakeProvider("groq")
        result = await manager(primary, backup).complete_text(bundle())
        assert result.model == "groq-model"

    async def test_fixed_chain_reaches_sambanova_gpt_oss_after_earlier_failures(self) -> None:
        gemini = FakeProvider("gemini", script=[fail(ErrorKind.UNAVAILABLE)])
        nvidia = FakeProvider("nvidia", script=[fail(ErrorKind.UNAVAILABLE)])
        deepseek = FakeProvider("sambanova_deepseek", script=[fail(ErrorKind.UNAVAILABLE)])
        gpt_oss = FakeProvider("sambanova_gpt_oss")
        groq = FakeProvider("groq")

        result = await manager(
            gemini, nvidia, deepseek, gpt_oss, groq
        ).complete_structured(bundle())

        assert result.data["served_by"] == "sambanova_gpt_oss"
        assert [gemini.calls, nvidia.calls, deepseek.calls, gpt_oss.calls, groq.calls] == [
            1,
            1,
            1,
            1,
            0,
        ]

    async def test_fixed_chain_reaches_groq_after_both_sambanova_models_fail(self) -> None:
        gemini = FakeProvider("gemini", script=[fail(ErrorKind.UNAVAILABLE)])
        nvidia = FakeProvider("nvidia", script=[fail(ErrorKind.UNAVAILABLE)])
        deepseek = FakeProvider("sambanova_deepseek", script=[fail(ErrorKind.UNAVAILABLE)])
        gpt_oss = FakeProvider("sambanova_gpt_oss", script=[fail(ErrorKind.UNAVAILABLE)])
        groq = FakeProvider("groq")

        result = await manager(
            gemini, nvidia, deepseek, gpt_oss, groq
        ).complete_structured(bundle())

        assert result.data["served_by"] == "groq"
        assert [gemini.calls, nvidia.calls, deepseek.calls, gpt_oss.calls, groq.calls] == [
            1,
            1,
            1,
            1,
            1,
        ]


class TestRetryBeforeFailover:
    """Transient failures belong to the same provider, not the next one."""

    async def test_a_timeout_is_retried_on_the_same_provider(self) -> None:
        primary = FakeProvider(
            "gemini", script=[fail(ErrorKind.RETRYABLE), _completion("gemini")]
        )
        backup = FakeProvider("groq")
        result = await manager(primary, backup, retries=2).complete_structured(bundle())

        assert result.data["served_by"] == "gemini"
        assert primary.calls == 2
        assert backup.calls == 0, "a transient blip must not spend another provider's quota"

    async def test_retries_are_exhausted_before_failing_over(self) -> None:
        primary = FakeProvider("gemini", script=[fail(ErrorKind.RETRYABLE)])
        backup = FakeProvider("groq")
        result = await manager(primary, backup, retries=2).complete_structured(bundle())

        assert primary.calls == 3, "one attempt plus two retries"
        assert result.data["served_by"] == "groq"

    async def test_a_quota_is_never_retried(self) -> None:
        primary = FakeProvider("gemini", script=[fail(ErrorKind.QUOTA)])
        backup = FakeProvider("groq")
        await manager(primary, backup, retries=3).complete_structured(bundle())
        assert primary.calls == 1, "retrying an exhausted quota only adds latency"

    async def test_retries_are_counted(self) -> None:
        primary = FakeProvider(
            "gemini", script=[fail(ErrorKind.RETRYABLE), _completion("gemini")]
        )
        mgr = manager(primary, retries=2)
        await mgr.complete_structured(bundle())
        assert mgr.stats.retries == 1

    async def test_retries_are_counted_even_when_the_provider_ends_up_failing(self) -> None:
        primary = FakeProvider("gemini", script=[fail(ErrorKind.RETRYABLE)])
        backup = FakeProvider("groq")
        mgr = manager(primary, backup, retries=2)
        await mgr.complete_structured(bundle())
        assert mgr.stats.retries == 2

    async def test_gemini_max_token_truncation_retries_then_fails_over(
        self,
    ) -> None:
        from app.llm.providers.native import GeminiAdapter

        class TruncatingClient:
            def __init__(self) -> None:
                self.prompts: list[PromptBundle] = []

            async def complete_structured(self, prompt: PromptBundle) -> Completion:
                self.prompts.append(prompt)
                raise LLMError(
                    "Model output was truncated before the response could be completed.",
                    details={"stop_reason": "max_tokens"},
                )

            async def complete_text(self, prompt: PromptBundle) -> TextCompletion:
                raise AssertionError("structured completion expected")

        gemini = GeminiAdapter(
            ProviderSpec(key="gemini", display_name="Gemini", model="test", priority=0),
            api_key="test-key",
        )
        client = TruncatingClient()
        gemini._client = client  # noqa: SLF001 - exercise the adapter boundary
        nvidia = FakeProvider("nvidia")
        prompt = bundle()

        result = await manager(gemini, nvidia, retries=1).complete_structured(prompt)

        assert result.data["served_by"] == "nvidia"
        assert len(client.prompts) == 2
        assert all(received is prompt for received in client.prompts)
        assert nvidia.calls == 1

    async def test_backoff_grows(self) -> None:
        policy = RetryPolicy(base_delay_seconds=1.0, jitter=0.0, max_delay_seconds=100)
        assert [policy.delay_for(i) for i in range(4)] == [1.0, 2.0, 4.0, 8.0]

    async def test_backoff_is_capped(self) -> None:
        policy = RetryPolicy(base_delay_seconds=1.0, jitter=0.0, max_delay_seconds=5.0)
        assert policy.delay_for(10) == 5.0


class TestPromptCache:
    """An identical prompt must not be paid for twice."""

    async def test_a_repeat_request_never_reaches_a_provider(self) -> None:
        provider = FakeProvider("gemini")
        mgr = manager(provider, cache=PromptCache(enabled=True))

        first = await mgr.complete_structured(bundle())
        second = await mgr.complete_structured(bundle())

        assert provider.calls == 1
        assert first.data == second.data
        assert mgr.stats.cache_hits == 1 and mgr.stats.cache_misses == 1

    async def test_a_cache_hit_reports_no_token_cost(self) -> None:
        # Replaying the stored usage would inflate every run report by exactly
        # the tokens the cache just saved.
        mgr = manager(FakeProvider("gemini"), cache=PromptCache(enabled=True))
        await mgr.complete_structured(bundle())
        cached = await mgr.complete_structured(bundle())
        assert cached.usage.total == 0

    async def test_different_prompts_do_not_collide(self) -> None:
        provider = FakeProvider("gemini")
        mgr = manager(provider, cache=PromptCache(enabled=True))
        await mgr.complete_structured(bundle(message="one"))
        await mgr.complete_structured(bundle(message="two"))
        assert provider.calls == 2

    async def test_structured_and_text_are_separate_questions(self) -> None:
        provider = FakeProvider("gemini")
        mgr = manager(provider, cache=PromptCache(enabled=True))
        await mgr.complete_structured(bundle())
        await mgr.complete_text(bundle())
        assert provider.calls == 2

    async def test_a_cached_answer_survives_the_provider_that_made_it(self) -> None:
        # This is the case that matters most: the cache keeps working after the
        # provider that filled it has been cooled down.
        provider = FakeProvider("gemini", script=[_completion("gemini"), fail(ErrorKind.QUOTA)])
        mgr = manager(provider, cache=PromptCache(enabled=True))
        await mgr.complete_structured(bundle())
        again = await mgr.complete_structured(bundle())
        assert again.data["served_by"] == "gemini"
        assert provider.calls == 1

    def test_mutating_a_cached_result_cannot_corrupt_the_entry(self) -> None:
        cache = PromptCache(enabled=True)
        cache.set("k", _completion("gemini"), provider="gemini")
        first = cache.get("k")
        first.data["ok"] = "tampered"
        assert cache.get("k").data["ok"] is True

    def test_least_recently_used_is_evicted(self) -> None:
        cache = PromptCache(enabled=True, max_entries=2)
        cache.set("a", _completion("x"), provider="x")
        cache.set("b", _completion("x"), provider="x")
        cache.get("a")  # 'a' becomes most recent, so 'b' should go
        cache.set("c", _completion("x"), provider="x")
        assert cache.get("a") is not None
        assert cache.get("b") is None

    def test_entries_expire(self) -> None:
        cache = PromptCache(enabled=True, ttl_seconds=0.01)
        cache.set("a", _completion("x"), provider="x")
        assert cache.get("a") is not None
        time.sleep(0.02)
        assert cache.get("a") is None

    def test_a_non_positive_ttl_disables_expiry(self) -> None:
        cache = PromptCache(enabled=True, ttl_seconds=0)
        cache.set("a", _completion("x"), provider="x")
        time.sleep(0.01)
        assert cache.get("a") is not None

    def test_a_disabled_cache_stores_nothing(self) -> None:
        cache = PromptCache(enabled=False)
        cache.set("a", _completion("x"), provider="x")
        assert cache.get("a") is None and len(cache) == 0


class TestHealthAndCooldown:
    """Health drives routing, not just the dashboard."""

    async def test_a_quota_withdraws_the_provider_from_routing(self) -> None:
        primary = FakeProvider("gemini", script=[fail(ErrorKind.QUOTA)])
        backup = FakeProvider("groq")
        mgr = manager(primary, backup)

        await mgr.complete_structured(bundle(message="first"))
        await mgr.complete_structured(bundle(message="second"))

        assert primary.calls == 1, "a cooled-down provider must not be retried per request"
        assert backup.calls == 2

    async def test_success_records_latency_and_tokens(self) -> None:
        mgr = manager(FakeProvider("gemini"))
        await mgr.complete_structured(bundle())
        health = mgr.health_snapshot()[0]
        assert health["successes"] == 1
        assert health["input_tokens"] == 10 and health["output_tokens"] == 5
        assert health["last_success_at"] is not None

    async def test_failover_counters_name_both_sides(self) -> None:
        primary = FakeProvider("gemini", script=[fail(ErrorKind.QUOTA)])
        backup = FakeProvider("groq")
        mgr = manager(primary, backup)
        await mgr.complete_structured(bundle())

        by_key = {p["key"]: p for p in mgr.health_snapshot()}
        assert by_key["gemini"]["failovers_from"] == 1
        assert by_key["groq"]["failovers_to"] == 1
        assert mgr.stats.failovers == 1

    async def test_a_recovered_provider_is_offered_again(self) -> None:
        mgr = manager(FakeProvider("gemini", script=[fail(ErrorKind.QUOTA)]), FakeProvider("groq"))
        await mgr.complete_structured(bundle())
        assert mgr.health_snapshot()[0]["status"] == ProviderStatus.COOLING_DOWN.value

        assert mgr.reset_provider("gemini") is True
        assert mgr.health_snapshot()[0]["status"] == ProviderStatus.HEALTHY.value

    async def test_resetting_an_unknown_provider_reports_failure(self) -> None:
        assert manager(FakeProvider("gemini")).reset_provider("nope") is False

    async def test_no_available_provider_is_a_clear_failure(self) -> None:
        mgr = manager(FakeProvider("gemini", configured=False, enabled=False))
        with pytest.raises(AllProvidersFailed):
            await mgr.complete_structured(bundle())

    def test_consecutive_failures_eventually_cool_a_provider_down(self) -> None:
        health = ProviderHealth(key="x", display_name="X", model="m", priority=0)
        for _ in range(3):
            health.record_failure(kind=ErrorKind.RETRYABLE, message="timeout", failure_threshold=3)
        assert health.status is ProviderStatus.COOLING_DOWN

    def test_a_success_clears_a_degraded_streak(self) -> None:
        health = ProviderHealth(key="x", display_name="X", model="m", priority=0)
        health.record_failure(kind=ErrorKind.RETRYABLE, message="timeout")
        assert health.status is ProviderStatus.DEGRADED
        health.record_success(latency_ms=100)
        assert health.status is ProviderStatus.HEALTHY

    def test_unconfigured_and_disabled_are_reported_distinctly(self) -> None:
        unconfigured = ProviderHealth(
            key="x", display_name="X", model="m", priority=0, configured=False
        )
        disabled = ProviderHealth(
            key="y", display_name="Y", model="m", priority=0, enabled=False
        )
        assert unconfigured.status is ProviderStatus.UNCONFIGURED
        assert disabled.status is ProviderStatus.DISABLED
        assert not unconfigured.selectable and not disabled.selectable


class TestTaskRouting:
    """Preference must never become restriction."""

    def test_agents_map_to_the_work_they_do(self) -> None:
        assert task_kind_for_agent("backend_engineer") is TaskKind.CODE_GENERATION
        assert task_kind_for_agent("documentation_engineer") is TaskKind.DOCUMENTATION
        assert task_kind_for_agent("solution_architect") is TaskKind.REASONING

    def test_an_unknown_agent_gets_the_safe_default(self) -> None:
        assert task_kind_for_agent("not_an_agent") is TaskKind.REASONING
        assert task_kind_for_agent(None) is TaskKind.REASONING

    def test_documentation_prefers_the_cheaper_provider(self) -> None:
        table = RoutingTable(priority=("gemini", "groq", "ollama"))
        assert table.order_for(TaskKind.DOCUMENTATION)[0] == "groq"

    def test_code_generation_prefers_the_stronger_provider(self) -> None:
        table = RoutingTable(priority=("groq", "gemini"))
        assert table.order_for(TaskKind.CODE_GENERATION)[0] == "gemini"

    def test_every_provider_stays_reachable_whatever_the_preference(self) -> None:
        # A preference that dropped providers would turn routing into a single
        # point of failure — the exact thing this system exists to remove.
        table = RoutingTable(priority=("gemini", "groq", "ollama", "openai", "anthropic"))
        for task in TaskKind:
            assert set(table.order_for(task)) == set(table.priority)

    def test_unavailable_providers_are_excluded(self) -> None:
        table = RoutingTable(priority=("gemini", "groq"))
        assert table.order_for(TaskKind.REASONING, available={"groq"}) == ["groq"]

    def test_routing_can_be_switched_off(self) -> None:
        table = RoutingTable(priority=("gemini", "groq"), task_routing_enabled=False)
        assert table.order_for(TaskKind.DOCUMENTATION) == ["gemini", "groq"]

    async def test_the_manager_routes_by_the_calling_agent(self) -> None:
        gemini = FakeProvider("gemini")
        groq = FakeProvider("groq")
        mgr = manager(gemini, groq, task_routing=True)

        await mgr.complete_structured(bundle("documentation_engineer"))
        assert groq.calls == 1 and gemini.calls == 0

        await mgr.complete_structured(bundle("backend_engineer", message="code"))
        assert gemini.calls == 1


class TestWrappedErrorClassification:
    """A quota buried inside a retry wrapper is still a quota.

    Regression, caught against the live API: both SDK clients run an internal
    retry loop that re-raises the last transport failure as a generic
    `LLMError("… unavailable after N attempts")`. Classifying only the outer
    exception read an exhausted daily quota as an ordinary timeout, so it
    earned no cooldown — and every remaining agent in the run paid another
    round trip to rediscover the same empty quota.
    """

    def gemini_adapter(self) -> Any:
        from app.llm.providers.native import GeminiAdapter

        return GeminiAdapter(
            ProviderSpec(key="gemini", display_name="Gemini", model="m", priority=0),
            api_key="k",
        )

    def anthropic_adapter(self) -> Any:
        from app.llm.providers.native import AnthropicAdapter

        return AnthropicAdapter(
            ProviderSpec(key="anthropic", display_name="Claude", model="m", priority=1),
            api_key="k",
        )

    def wrapped(self, cause: BaseException) -> LLMError:
        error = LLMError("Model provider unavailable after 1 attempts: boom")
        error.__cause__ = cause
        return error

    def test_a_wrapped_gemini_429_is_a_quota(self) -> None:
        from google.genai import errors as genai_errors

        cause = genai_errors.ClientError(429, {"error": {"message": "quota", "status": "X"}})
        assert self.gemini_adapter().classify(self.wrapped(cause)) is ErrorKind.QUOTA

    def test_a_wrapped_gemini_500_stays_retryable(self) -> None:
        from google.genai import errors as genai_errors

        cause = genai_errors.ServerError(503, {"error": {"message": "busy", "status": "X"}})
        assert self.gemini_adapter().classify(self.wrapped(cause)) is ErrorKind.RETRYABLE

    def test_an_unwrapped_timeout_is_still_retryable(self) -> None:
        plain = LLMError("Model provider unavailable after 3 attempts: timed out")
        assert self.gemini_adapter().classify(plain) is ErrorKind.RETRYABLE

    def test_only_gemini_max_token_truncation_is_retryable(self) -> None:
        truncation = LLMError(
            "Model output was truncated before the response could be completed.",
            details={"stop_reason": "max_tokens"},
        )
        incidental_text = LLMError("A request with a truncated field was rejected.")

        assert self.gemini_adapter().classify(truncation) is ErrorKind.RETRYABLE
        assert self.gemini_adapter().classify(incidental_text) is ErrorKind.FATAL

    def test_a_wrapped_anthropic_rate_limit_is_a_quota(self) -> None:
        import anthropic
        import httpx

        response = httpx.Response(429, request=httpx.Request("POST", "https://api.anthropic.com"))
        cause = anthropic.RateLimitError("rate limited", response=response, body=None)
        assert self.anthropic_adapter().classify(self.wrapped(cause)) is ErrorKind.QUOTA

    def test_a_depleted_balance_still_classifies_as_quota(self) -> None:
        from app.core.exceptions import ConfigurationError

        error = ConfigurationError("Your credit balance is too low to access the API.")
        assert self.anthropic_adapter().classify(error) is ErrorKind.QUOTA

    def test_a_quota_earns_a_cooldown_so_the_run_stops_rediscovering_it(self) -> None:
        health = ProviderHealth(key="gemini", display_name="G", model="m", priority=0)
        health.record_failure(
            kind=ErrorKind.QUOTA, message="daily limit", quota_cooldown_seconds=300
        )
        assert health.status is ProviderStatus.COOLING_DOWN
        assert not health.selectable

    def test_a_transient_failure_alone_does_not_cool_a_provider_down(self) -> None:
        health = ProviderHealth(key="gemini", display_name="G", model="m", priority=0)
        health.record_failure(kind=ErrorKind.RETRYABLE, message="timeout", failure_threshold=3)
        assert health.selectable, "one blip must not withdraw a working provider"


class TestUntaggedErrorsAreStillRetried:
    """Retrying must use the adapter's classifier, not the tag reader.

    Regression, seen in a live run: `RetryManager` classified with the global
    `kind_of`, which only reads a tag on the exception. The OpenAI-compatible
    adapter tags its errors; the first-party SDK clients do not. So every
    Anthropic and Gemini failure read as FATAL and was never retried — a
    transient 503 went straight to the next provider after one attempt, and
    with the other providers cooled down the agent simply failed.
    """

    class UntaggedProvider(FakeProvider):
        """Raises plain errors, exactly as the SDK-backed clients do."""

        def classify(self, error: BaseException) -> ErrorKind:
            return ErrorKind.RETRYABLE if "503" in str(error) else ErrorKind.FATAL

    async def test_an_untagged_transient_error_is_retried(self) -> None:
        provider = self.UntaggedProvider(
            "gemini",
            script=[
                LLMError("Model provider unavailable after 1 attempts: 503 UNAVAILABLE"),
                _completion("gemini"),
            ],
        )
        result = await manager(provider, retries=2).complete_structured(bundle())

        assert provider.calls == 2, "an untagged 503 must still earn a retry"
        assert result.data["served_by"] == "gemini"

    async def test_an_untagged_fatal_error_is_not_retried(self) -> None:
        provider = self.UntaggedProvider("gemini", script=[LLMError("malformed schema")])
        with pytest.raises(LLMError):
            await manager(provider, retries=2).complete_structured(bundle())
        assert provider.calls == 1

    async def test_the_retry_budget_is_spent_before_failing_over(self) -> None:
        primary = self.UntaggedProvider("gemini", script=[LLMError("503 UNAVAILABLE")])
        backup = FakeProvider("groq")
        result = await manager(primary, backup, retries=2).complete_structured(bundle())

        assert primary.calls == 3, "one attempt plus two retries"
        assert result.data["served_by"] == "groq"

    def test_the_default_classifier_is_still_the_tag_reader(self) -> None:
        # Callers that do tag their errors must keep working unchanged.
        assert kind_of(fail(ErrorKind.RETRYABLE)) is ErrorKind.RETRYABLE
        assert kind_of(LLMError("untagged")) is ErrorKind.FATAL


class TestFailureReporting:
    """"Every provider failed" must account for the ones that never ran."""

    async def test_untried_providers_are_named_with_their_reason(self) -> None:
        tried = FakeProvider("gemini", script=[fail(ErrorKind.RETRYABLE, "503 busy")])
        cooled = FakeProvider("groq")
        mgr = manager(tried, cooled)

        # Put groq out of action first, then fail gemini.
        mgr._health["groq"].record_failure(kind=ErrorKind.QUOTA, message="tpm")

        with pytest.raises(AllProvidersFailed) as exc:
            await mgr.complete_structured(bundle())

        report = exc.value.attempts
        assert "gemini" in report
        assert "not tried" in report["groq"], "a cooled-down provider must be explained"

    async def test_the_message_stays_accurate_when_everything_was_tried(self) -> None:
        a = FakeProvider("gemini", script=[fail(ErrorKind.QUOTA, "out of quota")])
        b = FakeProvider("groq", script=[fail(ErrorKind.AUTH, "bad key")])
        with pytest.raises(AllProvidersFailed) as exc:
            await manager(a, b).complete_structured(bundle())
        assert "not tried" not in str(exc.value)


class TestCapacityLimits:
    """A prompt too big for one provider must reach one that can hold it.

    Regression, seen in the browser: Groq's free tier bills input and output
    against a 12k-tokens-per-minute budget, and an Aegis reasoning prompt is
    around 27k. The 413 fell into the `else` branch of HTTP classification and
    was tagged FATAL — which means "stop, do not fail over" — so the run ended
    with a vendor error instead of quietly moving to a provider that fits.
    """

    def groq(self, **kwargs: Any) -> Any:
        from app.llm.providers.openai_compatible import OpenAICompatibleAdapter

        spec = ProviderSpec(
            key="groq",
            display_name="Groq",
            model="llama-3.3-70b-versatile",
            priority=0,
            **kwargs,
        )
        return OpenAICompatibleAdapter(
            spec, base_url="https://x", api_key="k", timeout_seconds=1
        )

    def response(self, status: int, message: str) -> Any:
        import httpx

        return httpx.Response(
            status,
            json={"error": {"message": message, "type": "x"}},
            request=httpx.Request("POST", "https://x/chat/completions"),
        )

    def test_a_413_fails_over_instead_of_ending_the_run(self) -> None:
        error = self.groq()._error_for(
            self.response(413, "Request too large ... on tokens per minute (TPM): Limit 12000")
        )
        assert kind_of(error) is ErrorKind.UNAVAILABLE
        assert kind_of(error).should_failover

    def test_a_context_length_400_also_fails_over(self) -> None:
        # Some vendors report the same condition as a 400.
        error = self.groq()._error_for(
            self.response(400, "This model's maximum context length is 8192 tokens")
        )
        assert kind_of(error) is ErrorKind.UNAVAILABLE

    def test_a_genuine_bad_request_is_still_fatal(self) -> None:
        error = self.groq()._error_for(self.response(400, "Unknown parameter 'foo'"))
        assert kind_of(error) is ErrorKind.FATAL

    def test_requested_output_is_clamped_to_the_provider_budget(self) -> None:
        # Asking a 12k-TPM provider for 32k output tokens is rejected even when
        # the prompt itself is tiny.
        adapter = self.groq(max_output_tokens=3500)
        assert adapter.spec.max_output_tokens == 3500

    def test_a_provider_that_cannot_fit_the_prompt_goes_last(self) -> None:
        small = FakeProvider("groq")
        object.__setattr__(small.spec, "max_prompt_tokens", 8000)
        large = FakeProvider("gemini")

        mgr = manager(small, large)
        assert mgr._eligible(TaskKind.REASONING, prompt_tokens=27_000) == ["gemini", "groq"]

    def test_it_is_deprioritised_not_dropped(self) -> None:
        # The estimate is approximate, so a provider is never removed outright
        # on the strength of it — being wrong must cost latency, not the run.
        small = FakeProvider("groq")
        object.__setattr__(small.spec, "max_prompt_tokens", 8000)

        mgr = manager(small)
        assert mgr._eligible(TaskKind.REASONING, prompt_tokens=27_000) == ["groq"]

    def test_a_prompt_that_fits_does_not_reorder_anything(self) -> None:
        small = FakeProvider("groq")
        object.__setattr__(small.spec, "max_prompt_tokens", 8000)
        large = FakeProvider("gemini")

        mgr = manager(small, large)
        assert mgr._eligible(TaskKind.REASONING, prompt_tokens=1_000) == ["groq", "gemini"]

    def test_providers_without_a_declared_limit_are_never_deprioritised(self) -> None:
        mgr = manager(FakeProvider("gemini"), FakeProvider("anthropic"))
        assert mgr._eligible(TaskKind.REASONING, prompt_tokens=500_000) == [
            "gemini",
            "anthropic",
        ]

    def test_the_estimate_scales_with_content(self) -> None:
        from app.llm.routing import estimate_tokens

        assert estimate_tokens("") < estimate_tokens("x" * 1000)
        assert estimate_tokens("x" * 35_000) > 8_000

    async def test_a_capacity_failure_reaches_the_next_provider(self) -> None:
        cramped = FakeProvider("groq", script=[fail(ErrorKind.UNAVAILABLE, "Request too large")])
        roomy = FakeProvider("gemini")
        result = await manager(cramped, roomy).complete_structured(bundle())
        assert result.data["served_by"] == "gemini"


class TestDashboardPayload:
    """The dashboard reads the live manager, so its shape is part of the API."""

    async def test_the_snapshot_reports_what_happened(self) -> None:
        primary = FakeProvider("gemini", script=[fail(ErrorKind.QUOTA)])
        backup = FakeProvider("groq")
        mgr = manager(primary, backup, cache=PromptCache(enabled=True))
        await mgr.complete_structured(bundle())
        await mgr.complete_structured(bundle())

        snapshot = mgr.stats_snapshot()
        assert snapshot["totals"]["failovers"] == 1
        assert snapshot["totals"]["cache_hits"] == 1
        assert snapshot["active_provider"] == "groq"
        assert snapshot["available_providers"] == ["groq"]
        assert [p["key"] for p in snapshot["providers"]] == ["gemini", "groq"]

    async def test_concurrent_requests_are_accounted_once_each(self) -> None:
        provider = FakeProvider("gemini")
        mgr = manager(provider)
        await asyncio.gather(
            *(mgr.complete_structured(bundle(message=f"m{i}")) for i in range(5))
        )
        assert mgr.stats.requests == 5 and mgr.stats.successes == 5
