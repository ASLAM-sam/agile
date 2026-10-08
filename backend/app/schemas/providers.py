"""Response models for the provider dashboard.

Updated for the role-based provider architecture (Phase 2).
The schema is deliberately loose to accommodate the simplified manager.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ProviderHealthResponse(BaseModel):
    """Live health for one model provider slot."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    slot: str = Field(default="", description="Provider slot identifier (groq, gemini_frontend, etc.)")
    # Keep 'key' as an alias for backwards compatibility with the frontend
    key: str = Field(default="", description="Alias for slot, for API compatibility.")
    display_name: str = Field(default="", description="Human-readable slot name.")
    role_group: str = Field(default="", description="Roles assigned to this account.")
    model: str = Field(description="Model this slot is configured to use.")
    configured: bool = Field(description="Whether this slot has credentials.")
    selectable: bool = Field(description="Whether this slot can serve requests.")

    requests: int = 0
    successes: int = 0
    failures: int = 0
    rate_limits: int = 0
    retries: int = 0
    success_rate: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0

    # Legacy fields kept for frontend compatibility (always 0 in role-based mode)
    priority: int = Field(default=0, description="Not used in role-based routing.")
    status: str = Field(default="healthy", description="Slot health status.")
    enabled: bool = Field(default=True)
    failovers_from: int = Field(default=0, description="Always 0 in role-based routing.")
    failovers_to: int = Field(default=0, description="Always 0 in role-based routing.")
    consecutive_failures: int = Field(default=0)
    latency_ms: float = Field(default=0.0)
    last_latency_ms: float = Field(default=0.0)
    last_error: str = Field(default="")
    last_error_kind: str = Field(default="")
    last_success_at: str | None = None
    last_failure_at: str | None = None
    cooldown_remaining_seconds: float = Field(default=0.0)
    cooldown_reason: str = Field(default="")


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

    model_config = ConfigDict(extra="ignore")

    requests: int
    successes: int
    failures: int
    retries: int = 0
    failovers: int = 0
    cache_hits: int
    cache_misses: int
    cache_hit_rate: float
    success_rate: float
    active_provider: str = ""


class ProviderDashboardResponse(BaseModel):
    """Everything the provider monitor renders, in one payload."""

    model_config = ConfigDict(extra="ignore")

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
