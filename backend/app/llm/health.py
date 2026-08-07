"""Live provider health, and the circuit breaker built on it.

Two jobs. The first is observability: the dashboard needs latency, success rate
and error counts per provider. The second is control — a provider that just
reported an exhausted quota must stop being offered to the next request, or
every agent in the run pays the same timeout to learn the same thing.

Cooldown is what connects them. A quota or a run of consecutive failures
withdraws a provider from routing for a bounded period, after which it is
offered again. Nothing has to be reset by hand.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.core.enums import ErrorKind, ProviderStatus


@dataclass(slots=True)
class ProviderHealth:
    """Rolling health for a single provider."""

    key: str
    display_name: str
    model: str
    priority: int
    enabled: bool = True
    configured: bool = True

    requests: int = 0
    successes: int = 0
    failures: int = 0
    retries: int = 0
    #: Times this provider was skipped or abandoned and another one took over.
    failovers_from: int = 0
    #: Times this provider picked up work another one could not complete.
    failovers_to: int = 0

    consecutive_failures: int = 0
    last_error: str = ""
    last_error_kind: str = ""
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None

    #: Exponential moving average, in milliseconds. Smoother than a plain mean
    #: and it forgets a slow patch once the provider recovers.
    latency_ms: float = 0.0
    last_latency_ms: float = 0.0

    #: Monotonic deadline before which this provider is not offered.
    cooldown_until: float = 0.0
    cooldown_reason: str = ""

    input_tokens: int = 0
    output_tokens: int = 0

    _LATENCY_SMOOTHING: float = field(default=0.3, repr=False)

    # --- derived ---------------------------------------------------------

    @property
    def success_rate(self) -> float:
        return self.successes / self.requests if self.requests else 0.0

    @property
    def cooling_down(self) -> bool:
        return time.monotonic() < self.cooldown_until

    @property
    def cooldown_remaining_seconds(self) -> float:
        return max(0.0, self.cooldown_until - time.monotonic())

    @property
    def status(self) -> ProviderStatus:
        if not self.enabled:
            return ProviderStatus.DISABLED
        if not self.configured:
            return ProviderStatus.UNCONFIGURED
        if self.cooling_down:
            return ProviderStatus.COOLING_DOWN
        if self.consecutive_failures:
            return ProviderStatus.DEGRADED
        return ProviderStatus.HEALTHY

    @property
    def selectable(self) -> bool:
        """Whether routing may offer this provider right now."""
        return self.status.is_selectable

    # --- recording -------------------------------------------------------

    def record_success(self, *, latency_ms: float, retries: int = 0, usage: Any = None) -> None:
        self.requests += 1
        self.successes += 1
        self.retries += retries
        self.consecutive_failures = 0
        self.last_success_at = datetime.now(UTC)
        self.last_latency_ms = latency_ms
        self.latency_ms = (
            latency_ms
            if self.latency_ms == 0.0
            else (self._LATENCY_SMOOTHING * latency_ms)
            + ((1 - self._LATENCY_SMOOTHING) * self.latency_ms)
        )
        # A provider that just answered has clearly recovered.
        self.cooldown_until = 0.0
        self.cooldown_reason = ""
        if usage is not None:
            self.input_tokens += getattr(usage, "input_tokens", 0)
            self.output_tokens += getattr(usage, "output_tokens", 0)

    def record_failure(
        self,
        *,
        kind: ErrorKind,
        message: str,
        retries: int = 0,
        quota_cooldown_seconds: float = 300.0,
        failure_cooldown_seconds: float = 60.0,
        failure_threshold: int = 3,
    ) -> None:
        self.requests += 1
        self.failures += 1
        self.retries += retries
        self.consecutive_failures += 1
        self.last_failure_at = datetime.now(UTC)
        self.last_error = message[:400]
        self.last_error_kind = kind.value

        if kind is ErrorKind.QUOTA:
            self._cool_down(quota_cooldown_seconds, "Quota or rate limit reached.")
        elif kind is ErrorKind.AUTH:
            # Credentials do not fix themselves; hold it back long enough that
            # the run does not keep paying a round trip to be told the same.
            self._cool_down(quota_cooldown_seconds, "Credentials were rejected.")
        elif kind is ErrorKind.UNAVAILABLE:
            self._cool_down(failure_cooldown_seconds, "Model or endpoint unavailable.")
        elif self.consecutive_failures >= failure_threshold:
            self._cool_down(
                failure_cooldown_seconds,
                f"{self.consecutive_failures} consecutive failures.",
            )

    def _cool_down(self, seconds: float, reason: str) -> None:
        deadline = time.monotonic() + max(0.0, seconds)
        # Never shorten an existing cooldown.
        if deadline > self.cooldown_until:
            self.cooldown_until = deadline
            self.cooldown_reason = reason

    def clear_cooldown(self) -> None:
        self.cooldown_until = 0.0
        self.cooldown_reason = ""
        self.consecutive_failures = 0

    # --- presentation ----------------------------------------------------

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "display_name": self.display_name,
            "model": self.model,
            "priority": self.priority,
            "status": self.status.value,
            "enabled": self.enabled,
            "configured": self.configured,
            "selectable": self.selectable,
            "requests": self.requests,
            "successes": self.successes,
            "failures": self.failures,
            "retries": self.retries,
            "failovers_from": self.failovers_from,
            "failovers_to": self.failovers_to,
            "success_rate": round(self.success_rate, 4),
            "consecutive_failures": self.consecutive_failures,
            "latency_ms": round(self.latency_ms, 1),
            "last_latency_ms": round(self.last_latency_ms, 1),
            "last_error": self.last_error,
            "last_error_kind": self.last_error_kind,
            "last_success_at": self.last_success_at.isoformat() if self.last_success_at else None,
            "last_failure_at": self.last_failure_at.isoformat() if self.last_failure_at else None,
            "cooldown_remaining_seconds": round(self.cooldown_remaining_seconds, 1),
            "cooldown_reason": self.cooldown_reason,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }
