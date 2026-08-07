"""Retry policy, owned in one place.

Each provider adapter used to run its own retry loop. Leaving them there and
adding a second loop in the manager would multiply, not compose: three attempts
inside three providers is nine calls and nine times the latency budget before
anyone notices a problem. Adapters are therefore constructed with retries
disabled, and this module is the only thing that decides to try again.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from app.core.enums import ErrorKind
from app.core.logging import get_logger
from app.llm.errors import kind_of

logger = get_logger(__name__)

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """How hard to try before handing the request to another provider."""

    #: Attempts *after* the first. 0 disables retrying entirely.
    max_retries: int = 2
    #: First backoff, doubled each attempt.
    base_delay_seconds: float = 1.0
    #: Ceiling, so a long backoff never outlives the request timeout.
    max_delay_seconds: float = 20.0
    #: Random fraction added to each delay, so concurrent runs do not
    #: synchronise their retries into a burst against a recovering provider.
    jitter: float = 0.5

    def delay_for(self, attempt: int) -> float:
        """Backoff before the given zero-indexed retry."""
        exponential = self.base_delay_seconds * (2.0**attempt)
        capped = min(exponential, self.max_delay_seconds)
        return capped + random.uniform(0, self.jitter)


@dataclass(slots=True)
class RetryOutcome:
    """What happened, for the health monitor and the run log."""

    attempts: int = 1
    retries: int = 0


class RetryManager:
    """Runs one operation under a retry policy."""

    def __init__(self, policy: RetryPolicy | None = None) -> None:
        self._policy = policy or RetryPolicy()

    @property
    def policy(self) -> RetryPolicy:
        return self._policy

    async def run(
        self,
        operation: Callable[[], Awaitable[T]],
        *,
        provider: str,
        classify: Callable[[BaseException], ErrorKind] | None = None,
        context: dict[str, object] | None = None,
        outcome: RetryOutcome | None = None,
    ) -> tuple[T, RetryOutcome]:
        """Execute `operation`, retrying only failures worth retrying.

        Anything not classified `RETRYABLE` is raised immediately: a rejected
        key or an exhausted quota does not improve by being asked again, and
        the caller wants to reach the next provider quickly.

        Pass `outcome` to keep the attempt counts after a raise — the retries a
        provider burned before failing are exactly what the health monitor
        needs, and an exception carries no return value.

        `classify` must be the *adapter's* classifier. The module-level
        `kind_of` only reads a tag, and the first-party SDK clients raise plain
        errors carrying no tag — so defaulting to it silently made every
        Anthropic and Gemini failure look FATAL, and a transient 503 was handed
        straight to the next provider without a single retry.
        """
        outcome = outcome if outcome is not None else RetryOutcome()
        extra = dict(context or {})
        classify = classify or kind_of

        for attempt in range(self._policy.max_retries + 1):
            try:
                result = await operation()
                return result, outcome
            except Exception as exc:
                if not classify(exc).should_retry or attempt >= self._policy.max_retries:
                    raise
                delay = self._policy.delay_for(attempt)
                outcome.attempts += 1
                outcome.retries += 1
                logger.warning(
                    "llm_retry",
                    extra={
                        "provider": provider,
                        "attempt": attempt + 1,
                        "of": self._policy.max_retries + 1,
                        "delay_seconds": round(delay, 2),
                        "error": type(exc).__name__,
                        "kind": ErrorKind.RETRYABLE.value,
                        **extra,
                    },
                )
                await asyncio.sleep(delay)

        raise AssertionError("unreachable: the loop either returns or raises")
