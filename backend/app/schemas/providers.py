"""Response models for the provider dashboard."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ProviderHealthResponse(BaseModel):
    """Live health for one model provider."""

    key: str = Field(description="Stable provider identifier.")
    display_name: str
    model: str = Field(description="Model this provider is configured to use.")
    priority: int = Field(description="Position in the routing order; lower is tried first.")
    status: str = Field(description="healthy | degraded | cooling_down | unconfigured | disabled")
    enabled: bool
    configured: bool
    selectable: bool = Field(description="Whether routing may choose it right now.")

    requests: int
    successes: int
    failures: int
    retries: int
    failovers_from: int = Field(description="Times work was handed away from this provider.")
    failovers_to: int = Field(description="Times this provider picked up another's work.")
    success_rate: float
    consecutive_failures: int

    latency_ms: float = Field(description="Smoothed average round trip.")
    last_latency_ms: float

    last_error: str
    last_error_kind: str
    last_success_at: str | None
    last_failure_at: str | None

    cooldown_remaining_seconds: float
    cooldown_reason: str

    input_tokens: int
    output_tokens: int


class CacheStatsResponse(BaseModel):
    """Prompt cache counters."""

    hits: int
    misses: int
    stores: int
    evictions: int
    lookups: int
    hit_rate: float


class ProviderTotalsResponse(BaseModel):
    """Aggregate counters across every provider."""

    requests: int
    successes: int
    failures: int
    retries: int
    failovers: int
    cache_hits: int
    cache_misses: int
    cache_hit_rate: float
    success_rate: float
    active_provider: str


class ProviderDashboardResponse(BaseModel):
    """Everything the provider monitor renders, in one payload."""

    providers: list[ProviderHealthResponse]
    totals: ProviderTotalsResponse
    cache: CacheStatsResponse
    priority: list[str] = Field(description="Configured routing order.")
    available_providers: list[str]
    active_provider: str
    failover_enabled: bool
    task_routing_enabled: bool
    cache_enabled: bool
    retry_limit: int = Field(description="Retries per provider before failing over.")


class ProviderResetResponse(BaseModel):
    """Result of clearing a provider's cooldown."""

    key: str
    cleared: bool
    message: str
