"""Per-agent execution record within a generation run."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import AgentRole, AgentStatus
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.types import JSONType

if TYPE_CHECKING:
    from app.models.run import GenerationRun


class AgentExecution(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Tracks one agent's slice of work: status, timing, cost and output."""

    __tablename__ = "agent_executions"
    __table_args__ = (
        UniqueConstraint("run_id", "role", name="uq_agent_executions_run_id_role"),
    )

    run_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("generation_runs.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    role: Mapped[AgentRole] = mapped_column(String(48), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[AgentStatus] = mapped_column(
        String(24), default=AgentStatus.WAITING, nullable=False
    )
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skip_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    confidence: Mapped[float | None] = mapped_column(nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    files_produced: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    run: Mapped[GenerationRun] = relationship(back_populates="agent_executions")

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<AgentExecution {self.role} {self.status}>"
