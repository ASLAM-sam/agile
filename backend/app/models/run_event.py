"""Durable event log backing the live console and post-hoc run inspection."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import EventType, LogLevel
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.types import JSONType

if TYPE_CHECKING:
    from app.models.run import GenerationRun


class RunEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One line in a run's timeline.

    Events are persisted as well as broadcast so a client that connects late,
    reloads the page, or reopens a finished run sees the identical history.
    """

    __tablename__ = "run_events"
    __table_args__ = (Index("ix_run_events_run_sequence", "run_id", "sequence"),)

    run_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("generation_runs.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[EventType] = mapped_column(String(40), nullable=False)
    level: Mapped[LogLevel] = mapped_column(String(16), default=LogLevel.INFO, nullable=False)
    agent_role: Mapped[str | None] = mapped_column(String(48), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)

    run: Mapped[GenerationRun] = relationship(back_populates="events")

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<RunEvent {self.sequence} {self.event_type}>"
