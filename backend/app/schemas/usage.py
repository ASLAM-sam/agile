"""UsageLog API schemas and summary models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from app.schemas.common import APIModel


class UsageLogItem(APIModel):
    """Safe external representation of a single LLM provider request audit."""

    id: str
    task_id: str | None = None
    run_id: str | None = None
    agent_execution_id: str | None = None
    agent_name: str
    agent_role: str
    provider: str
    model: str
    credential_slot: str
    masked_credential: str
    request_id: str
    request_number: int
    attempt_number: int = 1
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    token_usage_available: bool = False
    latency_ms: float
    status: str
    error_category: str | None = None
    error_message_safe: str | None = None
    retry_count: int = 0
    fallback_used: bool = False
    fallback_from: str | None = None
    fallback_to: str | None = None
    timestamp: datetime
    target_request_budget: int = 10
    hard_request_limit: int = 15
    provider_request_id: str | None = None
    finish_reason: str | None = None
    quota_snapshot: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = Field(default=None, alias="metadata_json")
    endpoint: str | None = None


class UsageSummaryResponse(APIModel):
    """Aggregated usage metrics across all requests."""

    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    fallback_requests: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    average_latency_ms: float = 0.0
    requests_by_provider: dict[str, int] = Field(default_factory=dict)
    requests_by_model: dict[str, int] = Field(default_factory=dict)
    requests_by_agent: dict[str, int] = Field(default_factory=dict)
    requests_by_credential: dict[str, int] = Field(default_factory=dict)


class QuotaOverviewResponse(APIModel):
    """Real-time quota consumption overview."""

    providers: list[dict[str, Any]] = Field(default_factory=list)
    models: list[dict[str, Any]] = Field(default_factory=list)
    credentials: list[dict[str, Any]] = Field(default_factory=list)
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    agents: list[dict[str, Any]] = Field(default_factory=list)


class CredentialHealthItem(APIModel):
    """Health and failure metrics for one credential slot."""

    credential_slot: str
    provider: str | None = None
    masked_credential: str
    healthy: bool
    status: str
    is_cooling_down: bool
    cooldown_until: float
    cooldown_reason: str
    last_success: str | None = None
    last_failure: str | None = None
    consecutive_failures: int
    total_requests: int
    successful_requests: int
    failed_requests: int
    rate_limit_count: int
    authentication_failure_count: int
    quota_exhausted_count: int
