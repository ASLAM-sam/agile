"""UsageLog ORM Model.

Tracks every individual LLM provider request with granular accounting for:
- Request identification & monotonic request numbering
- Agent role, provider, model, and masked credential slot
- Token usage (input, output, total) and measured provider latency
- Status, structured error categories, and safe error messages
- Fallback chain tracking (from/to) and retry counts
- Request budget status (target=10, hard limit=15)
- Quota snapshots (RPM, RPD, TPM) distinguishing provider-confirmed vs local
- STRICT SECURITY: Never stores raw API keys, Authorization headers, or tokens.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow
from app.models.types import JSONType

if TYPE_CHECKING:
    from app.models.agent_execution import AgentExecution
    from app.models.run import GenerationRun


class UsageLog(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Persistent audit record for a single LLM provider invocation."""

    __tablename__ = "usage_logs"
    __table_args__ = (
        Index("ix_usage_logs_run_request_number", "run_id", "request_number"),
        Index("ix_usage_logs_task_request_number", "task_id", "request_number"),
        Index("ix_usage_logs_provider_model", "provider", "model"),
    )

    # Correlation identifiers
    task_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    run_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("generation_runs.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    agent_execution_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("agent_executions.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    # Agent attribution
    agent_name: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_role: Mapped[str] = mapped_column(String(48), index=True, nullable=False)

    # Provider & Model routing
    provider: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    model: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    credential_slot: Mapped[str] = mapped_column(String(48), index=True, nullable=False)
    masked_credential: Mapped[str] = mapped_column(String(32), nullable=False)

    # Request execution details
    request_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    request_number: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Token metrics
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_usage_available: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Performance
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False)

    # Outcome & Error tracking
    status: Mapped[str] = mapped_column(
        String(32), index=True, nullable=False
    )  # success, failed, rate_limited, budget_exceeded, timeout
    error_category: Mapped[str | None] = mapped_column(String(48), index=True, nullable=True)
    error_message_safe: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Fallback & Retry tracking
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fallback_from: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fallback_to: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Budget & Limits
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, index=True, nullable=False
    )
    target_request_budget: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    hard_request_limit: Mapped[int] = mapped_column(Integer, default=15, nullable=False)

    # Optional metadata & snapshots
    provider_request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    finish_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    quota_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    endpoint: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # Relationships
    run: Mapped[GenerationRun | None] = relationship(foreign_keys=[run_id])
    agent_execution: Mapped[AgentExecution | None] = relationship(
        foreign_keys=[agent_execution_id]
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert to safe dictionary representation for APIs and logging."""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "agent_execution_id": self.agent_execution_id,
            "agent_name": self.agent_name,
            "agent_role": self.agent_role,
            "provider": self.provider,
            "model": self.model,
            "credential_slot": self.credential_slot,
            "masked_credential": self.masked_credential,
            "request_id": self.request_id,
            "request_number": self.request_number,
            "attempt_number": self.attempt_number,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "token_usage_available": self.token_usage_available,
            "latency_ms": round(self.latency_ms, 2),
            "status": self.status,
            "error_category": self.error_category,
            "error_message_safe": self.error_message_safe,
            "retry_count": self.retry_count,
            "fallback_used": self.fallback_used,
            "fallback_from": self.fallback_from,
            "fallback_to": self.fallback_to,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "target_request_budget": self.target_request_budget,
            "hard_request_limit": self.hard_request_limit,
            "provider_request_id": self.provider_request_id,
            "finish_reason": self.finish_reason,
            "quota_snapshot": self.quota_snapshot,
            "metadata": self.metadata_json,
            "endpoint": self.endpoint,
        }

    def __repr__(self) -> str:
        return (
            f"<UsageLog #{self.request_number} {self.agent_role} {self.provider}/{self.model} "
            f"slot={self.credential_slot} status={self.status} latency={self.latency_ms:.1f}ms>"
        )
