"""Quota Engine.

Tracks quota consumption across independent dimensions:
- Provider (e.g., gemini, openai, mistral)
- Model (e.g., gemini-3.6-flash, gpt-4o)
- Credential slot (e.g., FRONTEND_API_KEY01, BACKEND_API_KEY01)
- Task / Run
- Agent role (e.g., frontend_engineer, backend_engineer)

Accurately tracks sliding-window metrics:
- RPM (Requests Per Minute - 60s sliding window)
- RPD (Requests Per Day - 86,400s sliding window)
- TPM (Tokens Per Minute - 60s sliding window)

STRICT RULE: Never fakes quota data. Distinguishes:
- PROVIDER_REPORTED: confirmed from response headers (e.g. x-ratelimit-*)
- LOCALLY_TRACKED: measured locally via sliding window
- UNKNOWN: when no limit or provider confirmation is available (stores None / null)
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


class QuotaSource(str, Enum):
    PROVIDER_REPORTED = "PROVIDER_REPORTED"
    LOCALLY_TRACKED = "LOCALLY_TRACKED"
    UNKNOWN = "UNKNOWN"


@dataclass
class SlidingWindow:
    """Sliding time window for tracking events (requests or tokens)."""

    window_seconds: float
    _events: deque[tuple[float, int]] = field(default_factory=deque)

    def record(self, count: int = 1, timestamp: float | None = None) -> None:
        now = timestamp or time.monotonic()
        self._prune(now)
        self._events.append((now, count))

    def _prune(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self._events and self._events[0][0] < cutoff:
            self._events.popleft()

    def get_used(self, now: float | None = None) -> int:
        current_time = now or time.monotonic()
        self._prune(current_time)
        return sum(qty for _, qty in self._events)


@dataclass
class DimensionQuotaState:
    """Tracks sliding-window metrics and reported limits for one entity."""

    name: str
    dimension_type: str  # provider, model, credential, task, agent
    rpm_window: SlidingWindow = field(default_factory=lambda: SlidingWindow(window_seconds=60.0))
    rpd_window: SlidingWindow = field(default_factory=lambda: SlidingWindow(window_seconds=86400.0))
    tpm_window: SlidingWindow = field(default_factory=lambda: SlidingWindow(window_seconds=60.0))

    # Known / configured limits (None if unknown)
    rpm_limit: int | None = None
    rpd_limit: int | None = None
    tpm_limit: int | None = None

    # Provider reported remaining values (None if unknown)
    rpm_remaining_reported: int | None = None
    rpd_remaining_reported: int | None = None
    tpm_remaining_reported: int | None = None

    last_header_update: float = 0.0

    def record(
        self,
        *,
        requests: int = 1,
        tokens: int = 0,
        now: float | None = None,
    ) -> None:
        current_time = now or time.monotonic()
        self.rpm_window.record(count=requests, timestamp=current_time)
        self.rpd_window.record(count=requests, timestamp=current_time)
        if tokens > 0:
            self.tpm_window.record(count=tokens, timestamp=current_time)

    def update_from_headers(self, headers: dict[str, str]) -> None:
        """Extract standardized rate limit headers if provided by vendor."""
        if not headers:
            return

        normalized = {k.lower(): str(v).strip() for k, v in headers.items()}

        # 1. RPM / Requests limits
        for key in (
            "x-ratelimit-limit-requests",
            "x-ratelimit-limit-requests-per-minute",
            "ratelimit-limit",
        ):
            if key in normalized:
                try:
                    self.rpm_limit = int(normalized[key])
                    break
                except ValueError:
                    pass

        for key in (
            "x-ratelimit-remaining-requests",
            "x-ratelimit-remaining-requests-per-minute",
            "ratelimit-remaining",
        ):
            if key in normalized:
                try:
                    self.rpm_remaining_reported = int(normalized[key])
                    break
                except ValueError:
                    pass

        # 2. TPM / Tokens limits
        for key in ("x-ratelimit-limit-tokens", "x-ratelimit-limit-tokens-per-minute"):
            if key in normalized:
                try:
                    self.tpm_limit = int(normalized[key])
                    break
                except ValueError:
                    pass

        for key in ("x-ratelimit-remaining-tokens", "x-ratelimit-remaining-tokens-per-minute"):
            if key in normalized:
                try:
                    self.tpm_remaining_reported = int(normalized[key])
                    break
                except ValueError:
                    pass

        # 3. RPD / Daily limits
        for key in ("x-ratelimit-limit-requests-per-day",):
            if key in normalized:
                try:
                    self.rpd_limit = int(normalized[key])
                    break
                except ValueError:
                    pass

        for key in ("x-ratelimit-remaining-requests-per-day",):
            if key in normalized:
                try:
                    self.rpd_remaining_reported = int(normalized[key])
                    break
                except ValueError:
                    pass

        self.last_header_update = time.monotonic()

    def snapshot(self) -> dict[str, Any]:
        """Compute the snapshot distinguishing PROVIDER_REPORTED, LOCALLY_TRACKED, and UNKNOWN."""
        now = time.monotonic()
        rpm_used = self.rpm_window.get_used(now)
        rpd_used = self.rpd_window.get_used(now)
        tpm_used = self.tpm_window.get_used(now)

        # RPM
        if self.rpm_remaining_reported is not None and (now - self.last_header_update) < 60.0:
            rpm_src = QuotaSource.PROVIDER_REPORTED.value
            rpm_rem = self.rpm_remaining_reported
        elif self.rpm_limit is not None:
            rpm_src = QuotaSource.LOCALLY_TRACKED.value
            rpm_rem = max(0, self.rpm_limit - rpm_used)
        else:
            rpm_src = QuotaSource.UNKNOWN.value
            rpm_rem = None

        # RPD
        if self.rpd_remaining_reported is not None and (now - self.last_header_update) < 300.0:
            rpd_src = QuotaSource.PROVIDER_REPORTED.value
            rpd_rem = self.rpd_remaining_reported
        elif self.rpd_limit is not None:
            rpd_src = QuotaSource.LOCALLY_TRACKED.value
            rpd_rem = max(0, self.rpd_limit - rpd_used)
        else:
            rpd_src = QuotaSource.UNKNOWN.value
            rpd_rem = None

        # TPM
        if self.tpm_remaining_reported is not None and (now - self.last_header_update) < 60.0:
            tpm_src = QuotaSource.PROVIDER_REPORTED.value
            tpm_rem = self.tpm_remaining_reported
        elif self.tpm_limit is not None:
            tpm_src = QuotaSource.LOCALLY_TRACKED.value
            tpm_rem = max(0, self.tpm_limit - tpm_used)
        else:
            tpm_src = QuotaSource.UNKNOWN.value
            tpm_rem = None

        return {
            "name": self.name,
            "dimension": self.dimension_type,
            "rpm": {
                "limit": self.rpm_limit,
                "used": rpm_used,
                "remaining": rpm_rem,
                "source": rpm_src,
            },
            "rpd": {
                "limit": self.rpd_limit,
                "used": rpd_used,
                "remaining": rpd_rem,
                "source": rpd_src,
            },
            "tpm": {
                "limit": self.tpm_limit,
                "used": tpm_used,
                "remaining": tpm_rem,
                "source": tpm_src,
            },
        }


class QuotaEngine:
    """Multi-dimensional Quota Engine tracking consumption and limits."""

    def __init__(self) -> None:
        self._providers: dict[str, DimensionQuotaState] = {}
        self._models: dict[str, DimensionQuotaState] = {}
        self._credentials: dict[str, DimensionQuotaState] = {}
        self._tasks: dict[str, DimensionQuotaState] = {}
        self._agents: dict[str, DimensionQuotaState] = {}

    def _get_or_create(
        self,
        table: dict[str, DimensionQuotaState],
        name: str,
        dim_type: str,
    ) -> DimensionQuotaState:
        if name not in table:
            table[name] = DimensionQuotaState(name=name, dimension_type=dim_type)
        return table[name]

    def record_usage(
        self,
        *,
        provider: str,
        model: str,
        credential_slot: str,
        task_id: str | None = None,
        agent_role: str | None = None,
        requests: int = 1,
        tokens: int = 0,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Record an LLM request across all five dimensions and return a structured snapshot."""
        now = time.monotonic()

        prov_state = self._get_or_create(self._providers, provider or "unknown_provider", "provider")
        model_state = self._get_or_create(self._models, model or "unknown_model", "model")
        cred_state = self._get_or_create(self._credentials, credential_slot or "unknown_slot", "credential")

        prov_state.record(requests=requests, tokens=tokens, now=now)
        model_state.record(requests=requests, tokens=tokens, now=now)
        cred_state.record(requests=requests, tokens=tokens, now=now)

        if headers:
            prov_state.update_from_headers(headers)
            model_state.update_from_headers(headers)
            cred_state.update_from_headers(headers)

        if task_id:
            t_state = self._get_or_create(self._tasks, task_id, "task")
            t_state.record(requests=requests, tokens=tokens, now=now)

        if agent_role:
            a_state = self._get_or_create(self._agents, agent_role, "agent")
            a_state.record(requests=requests, tokens=tokens, now=now)

        # Return snapshot focusing on provider + model + slot
        return {
            "provider": prov_state.snapshot(),
            "model": model_state.snapshot(),
            "credential": cred_state.snapshot(),
        }

    def set_known_limits(
        self,
        target_name: str,
        dimension_type: str,
        *,
        rpm_limit: int | None = None,
        rpd_limit: int | None = None,
        tpm_limit: int | None = None,
    ) -> None:
        """Register known limits from config without fabricating data."""
        table = {
            "provider": self._providers,
            "model": self._models,
            "credential": self._credentials,
            "task": self._tasks,
            "agent": self._agents,
        }.get(dimension_type)
        if table is not None:
            state = self._get_or_create(table, target_name, dimension_type)
            if rpm_limit is not None:
                state.rpm_limit = rpm_limit
            if rpd_limit is not None:
                state.rpd_limit = rpd_limit
            if tpm_limit is not None:
                state.tpm_limit = tpm_limit

    def get_overview(self) -> dict[str, Any]:
        """Return full quota snapshot for dashboard/monitoring."""
        return {
            "providers": [s.snapshot() for s in self._providers.values()],
            "models": [s.snapshot() for s in self._models.values()],
            "credentials": [s.snapshot() for s in self._credentials.values()],
            "tasks": [s.snapshot() for s in self._tasks.values()],
            "agents": [s.snapshot() for s in self._agents.values()],
        }


_global_quota_engine: QuotaEngine | None = None


def get_quota_engine() -> QuotaEngine:
    global _global_quota_engine
    if _global_quota_engine is None:
        _global_quota_engine = QuotaEngine()
    return _global_quota_engine
