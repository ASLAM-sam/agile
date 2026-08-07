"""The provider manager: the only thing that talks to a model vendor.

Agents call `complete_structured` / `complete_text` exactly as they always
have. `ProviderManager` satisfies the same `LLMProvider` protocol the concrete
clients do, so switching the platform onto it changed no agent, no workflow
step and no adapter — the seam was already there for testability, and this is
what it was for.

One request travels through five stages:

    cache  ->  route  ->  retry  ->  fail over  ->  record

* **cache** — an identical prompt already answered is returned immediately and
  costs nothing.
* **route** — the calling agent's role decides which providers are tried
  first; the rest stay behind it, so preference never becomes restriction.
* **retry** — transient failures get exponential backoff against the *same*
  provider, because a timeout is not a reason to spend a different quota.
* **fail over** — a quota, a rejected key or an unavailable model moves to the
  next provider immediately, and cools the failed one down so the rest of the
  run stops paying to rediscover it.
* **record** — latency, tokens, retries and failovers land in the health
  monitor that backs the dashboard.

Only a `FATAL` classification stops the sequence. That is the request itself
being wrong — a malformed schema, a bad parameter — where trying five vendors
costs five quotas to receive five identical rejections.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from app.core.config import Settings
from app.core.config import settings as default_settings
from app.core.enums import TaskKind
from app.core.logging import get_logger
from app.llm.cache import PromptCache
from app.llm.errors import AllProvidersFailed
from app.llm.health import ProviderHealth
from app.llm.providers.base import ProviderAdapter
from app.llm.providers.registry import build_providers
from app.llm.retry import RetryManager, RetryOutcome, RetryPolicy
from app.llm.routing import RoutingTable, estimate_tokens, task_kind_for_agent
from app.llm.types import Completion, PromptBundle, TextCompletion

logger = get_logger(__name__)

T = TypeVar("T")


@dataclass(slots=True)
class ManagerStats:
    """Cross-provider totals for the dashboard."""

    requests: int = 0
    successes: int = 0
    failures: int = 0
    retries: int = 0
    failovers: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    #: Most recent provider to answer successfully.
    active_provider: str = ""

    def as_dict(self) -> dict[str, Any]:
        lookups = self.cache_hits + self.cache_misses
        return {
            "requests": self.requests,
            "successes": self.successes,
            "failures": self.failures,
            "retries": self.retries,
            "failovers": self.failovers,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_hit_rate": round(self.cache_hits / lookups, 4) if lookups else 0.0,
            "success_rate": round(self.successes / self.requests, 4) if self.requests else 0.0,
            "active_provider": self.active_provider,
        }


class ProviderManager:
    """Selects, retries, fails over and records. Agents see none of it."""

    def __init__(
        self,
        *,
        providers: list[ProviderAdapter] | None = None,
        config: Settings | None = None,
        cache: PromptCache | None = None,
        retry: RetryManager | None = None,
        routing: RoutingTable | None = None,
    ) -> None:
        self._config = config or default_settings
        self._providers: dict[str, ProviderAdapter] = {}
        self._health: dict[str, ProviderHealth] = {}

        for adapter in providers if providers is not None else build_providers(self._config):
            self._providers[adapter.key] = adapter
            self._health[adapter.key] = ProviderHealth(
                key=adapter.key,
                display_name=adapter.display_name,
                model=adapter.model,
                priority=adapter.spec.priority,
                enabled=adapter.spec.enabled,
                configured=adapter.is_configured,
            )

        self._cache = cache or PromptCache(
            enabled=self._config.llm_cache_enabled,
            max_entries=self._config.llm_cache_max_entries,
            ttl_seconds=self._config.llm_cache_ttl_seconds,
        )
        self._retry = retry or RetryManager(
            RetryPolicy(max_retries=max(0, self._config.llm_max_retries - 1))
        )
        self._routing = routing or RoutingTable(
            priority=tuple(self._providers),
            task_routing_enabled=self._config.llm_task_routing_enabled,
        )
        self.stats = ManagerStats()

    # --- introspection ---------------------------------------------------

    @property
    def model(self) -> str:
        """The model that would serve the next request."""
        order = self._eligible()
        return self._providers[order[0]].model if order else self._config.active_model

    @property
    def cache(self) -> PromptCache:
        return self._cache

    def health_snapshot(self) -> list[dict[str, Any]]:
        """Per-provider health, in routing order."""
        return [self._health[key].as_dict() for key in self._providers]

    def stats_snapshot(self) -> dict[str, Any]:
        """Everything the dashboard needs in one payload."""
        providers = self.health_snapshot()
        selectable = [p for p in providers if p["selectable"]]
        return {
            "providers": providers,
            "totals": self.stats.as_dict(),
            "cache": self._cache.stats.as_dict(),
            "priority": list(self._providers),
            "failover_enabled": self._config.llm_failover_enabled,
            "task_routing_enabled": self._routing.task_routing_enabled,
            "cache_enabled": self._cache.enabled,
            "retry_limit": self._retry.policy.max_retries,
            "available_providers": [p["key"] for p in selectable],
            "active_provider": self.stats.active_provider or (
                selectable[0]["key"] if selectable else ""
            ),
        }

    def reset_provider(self, key: str) -> bool:
        """Clear a cooldown so a provider is offered again immediately."""
        health = self._health.get(key)
        if health is None:
            return False
        health.clear_cooldown()
        return True

    async def aclose(self) -> None:
        for adapter in self._providers.values():
            await adapter.aclose()

    # --- the protocol agents use -----------------------------------------

    async def complete_structured(self, prompt: PromptBundle) -> Completion:
        if prompt.schema is None:
            raise ValueError("complete_structured requires a schema on the PromptBundle.")
        return await self._dispatch(
            prompt,
            structured=True,
            call=lambda adapter: adapter.complete_structured(prompt),
        )

    async def complete_text(self, prompt: PromptBundle) -> TextCompletion:
        return await self._dispatch(
            prompt,
            structured=False,
            call=lambda adapter: adapter.complete_text(prompt),
        )

    # --- internals -------------------------------------------------------

    def _eligible(
        self, task: TaskKind = TaskKind.REASONING, *, prompt_tokens: int = 0
    ) -> list[str]:
        """Providers that may be tried right now, best first.

        Providers whose declared budget cannot hold the prompt are moved to the
        back rather than dropped. A free tier capped at 12k tokens per minute
        can never serve a 27k-token prompt, and learning that once per agent is
        pure latency — but the estimate is approximate, so a provider is never
        removed outright on the strength of it.
        """
        available = {key for key, health in self._health.items() if health.selectable}
        order = self._routing.order_for(task, available=available)
        if not prompt_tokens:
            return order

        fits, too_small = [], []
        for key in order:
            limit = self._providers[key].spec.max_prompt_tokens
            (too_small if limit and prompt_tokens > limit else fits).append(key)

        if too_small:
            logger.debug(
                "llm_capacity_deprioritised",
                extra={
                    "prompt_tokens": prompt_tokens,
                    "deprioritised": ",".join(too_small),
                    "task": task.value,
                },
            )
        return fits + too_small

    def _cache_key(self, prompt: PromptBundle, *, structured: bool) -> str:
        return self._cache.key_for(
            cacheable_system=prompt.cacheable_system,
            volatile_system=prompt.volatile_system,
            user_message=prompt.user_message,
            schema=prompt.schema,
            max_tokens=prompt.max_tokens,
            structured=structured,
        )

    async def _dispatch(
        self,
        prompt: PromptBundle,
        *,
        structured: bool,
        call: Callable[[ProviderAdapter], Awaitable[T]],
    ) -> T:
        agent = str(prompt.metadata.get("agent") or "")
        task = task_kind_for_agent(agent)
        key = self._cache_key(prompt, structured=structured)

        cached = self._cache.get(key)
        if cached is not None:
            self.stats.cache_hits += 1
            logger.info(
                "llm_cache_hit",
                extra={"agent": agent, "task": task.value, **_scrub(prompt.metadata)},
            )
            return cached  # type: ignore[return-value]
        self.stats.cache_misses += 1

        prompt_tokens = estimate_tokens(
            prompt.cacheable_system, prompt.volatile_system, prompt.user_message
        )
        order = self._eligible(task, prompt_tokens=prompt_tokens)
        if not order:
            self.stats.failures += 1
            raise AllProvidersFailed(self._unavailable_reasons(), task=task.value)

        self.stats.requests += 1
        attempts: dict[str, str] = {}

        for index, provider_key in enumerate(order):
            adapter = self._providers[provider_key]
            health = self._health[provider_key]
            started = time.perf_counter()
            outcome = RetryOutcome()

            try:
                result, outcome = await self._retry.run(
                    lambda adapter=adapter: call(adapter),
                    provider=provider_key,
                    # The adapter's classifier, not the global tag reader: the
                    # SDK-backed providers raise untagged errors, which the
                    # default would read as FATAL and never retry.
                    classify=adapter.classify,
                    context={"agent": agent, "task": task.value},
                    outcome=outcome,
                )
            except Exception as exc:
                kind = adapter.classify(exc)
                elapsed_ms = (time.perf_counter() - started) * 1000
                health.record_failure(
                    kind=kind,
                    message=str(exc),
                    retries=outcome.retries,
                    quota_cooldown_seconds=self._config.llm_quota_cooldown_seconds,
                    failure_cooldown_seconds=self._config.llm_failure_cooldown_seconds,
                    failure_threshold=self._config.llm_failure_threshold,
                )
                attempts[provider_key] = f"{kind.value}: {exc}"
                self.stats.retries += outcome.retries
                logger.warning(
                    "llm_provider_failed",
                    extra={
                        "provider": provider_key,
                        "kind": kind.value,
                        "agent": agent,
                        "task": task.value,
                        "elapsed_ms": round(elapsed_ms, 1),
                        "reason": str(exc)[:300],
                        **_scrub(prompt.metadata),
                    },
                )

                last = index == len(order) - 1
                if not kind.should_failover or not self._config.llm_failover_enabled or last:
                    self.stats.failures += 1
                    if not kind.should_failover or not self._config.llm_failover_enabled:
                        raise
                    raise AllProvidersFailed(
                        self._failure_report(attempts), task=task.value
                    ) from exc

                self.stats.failovers += 1
                health.failovers_from += 1
                self._health[order[index + 1]].failovers_to += 1
                logger.warning(
                    "llm_failover",
                    extra={
                        "from_provider": provider_key,
                        "to_provider": order[index + 1],
                        "reason": kind.value,
                        "agent": agent,
                        **_scrub(prompt.metadata),
                    },
                )
                continue

            elapsed_ms = (time.perf_counter() - started) * 1000
            usage = getattr(result, "usage", None)
            health.record_success(
                latency_ms=elapsed_ms, retries=outcome.retries, usage=usage
            )
            self.stats.successes += 1
            self.stats.retries += outcome.retries
            self.stats.active_provider = provider_key
            self._cache.set(key, result, provider=provider_key)

            logger.info(
                "llm_request",
                extra={
                    "provider": provider_key,
                    "model": adapter.model,
                    "agent": agent,
                    "task": task.value,
                    "elapsed_ms": round(elapsed_ms, 1),
                    "retries": outcome.retries,
                    "failovers": index,
                    "cache": "miss",
                    "input_tokens": getattr(usage, "input_tokens", 0),
                    "output_tokens": getattr(usage, "output_tokens", 0),
                    **_scrub(prompt.metadata),
                },
            )
            return result

        self.stats.failures += 1
        raise AllProvidersFailed(self._failure_report(attempts), task=task.value)

    def _unavailable_reasons(self) -> dict[str, str]:
        """Why each provider is sitting out, for the failure message."""
        reasons: dict[str, str] = {}
        for key, health in self._health.items():
            status = health.status
            if status.is_selectable:
                continue
            reasons[key] = health.cooldown_reason or status.value.replace("_", " ")
        return reasons

    def _failure_report(self, attempts: dict[str, str]) -> dict[str, str]:
        """What was tried, plus why the rest were not.

        Listing only the providers that were actually called makes "every
        provider failed" read as a lie when four of the five were sitting out a
        cooldown. The ones that never got a turn are the more useful half of
        the explanation.
        """
        report = dict(attempts)
        for key, reason in self._unavailable_reasons().items():
            report.setdefault(key, f"not tried ({reason})")
        return report


def _scrub(metadata: dict[str, Any]) -> dict[str, Any]:
    """Log-safe request metadata.

    `agent` is logged explicitly by every call site, so re-emitting it here
    would collide in the LogRecord and raise.
    """
    return {k: v for k, v in metadata.items() if k != "agent"}
