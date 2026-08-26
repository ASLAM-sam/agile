# """Generation run — one end-to-end execution of the AI engineering team."""

# from __future__ import annotations

# from datetime import datetime
# from typing import TYPE_CHECKING, Any
# # from xmlrpc.client import DateTime

# # from sqlalchemy import ForeignKey, Index, Integer, String, Text
# from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
# from sqlalchemy.orm import Mapped, mapped_column, relationship

# from app.core.enums import RunStatus
# from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
# from app.models.types import JSONType

# if TYPE_CHECKING:
#     from app.models.agent_execution import AgentExecution
#     from app.models.artifact import Artifact
#     from app.models.project import Project
#     from app.models.run_event import RunEvent


# class GenerationRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
#     """A single orchestrated pass over the multi-agent workflow."""

#     __tablename__ = "generation_runs"
#     __table_args__ = (Index("ix_runs_project_created", "project_id", "created_at"),)

#     project_id: Mapped[str] = mapped_column(
#         String(32), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
#     )

#     status: Mapped[RunStatus] = mapped_column(
#         String(32), default=RunStatus.PENDING, index=True, nullable=False
#     )
#     phase: Mapped[str | None] = mapped_column(String(64), nullable=True)
#     progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

#     # Inputs resolved at run start.
#     tech_stack: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
#     analysis: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
#     workflow_plan: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONType, nullable=True)

#     # Outputs.
#     report: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
#     memory_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
#     error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

#     # Accounting.
#     # started_at: Mapped[datetime | None] = mapped_column(nullable=True)
#     # finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
#     started_at: Mapped[datetime | None] = mapped_column(
#         DateTime(timezone=True), nullable=True
#     )
#     finished_at: Mapped[datetime | None] = mapped_column(
#         DateTime(timezone=True), nullable=True
#     )
#     duration_seconds: Mapped[float | None] = mapped_column(nullable=True)
#     input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
#     output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
#     cached_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
#     file_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

#     project: Mapped[Project] = relationship(back_populates="runs", lazy="joined")
#     agent_executions: Mapped[list[AgentExecution]] = relationship(
#         back_populates="run",
#         cascade="all, delete-orphan",
#         order_by="AgentExecution.sequence",
#         lazy="selectin",
#     )
#     artifacts: Mapped[list[Artifact]] = relationship(
#         back_populates="run",
#         cascade="all, delete-orphan",
#         lazy="selectin",
#     )
#     events: Mapped[list[RunEvent]] = relationship(
#         back_populates="run",
#         cascade="all, delete-orphan",
#         order_by="RunEvent.sequence",
#         lazy="noload",
#     )

#     @property
#     def total_tokens(self) -> int:
#         return self.input_tokens + self.output_tokens

#     def __repr__(self) -> str:  # pragma: no cover - debugging helper
#         return f"<GenerationRun {self.id} {self.status}>"


"""Generation run — one end-to-end execution of the AI engineering team."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import RunStatus
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.types import JSONType

if TYPE_CHECKING:
    from app.models.agent_execution import AgentExecution
    from app.models.artifact import Artifact
    from app.models.project import Project
    from app.models.run_event import RunEvent


class GenerationRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A single orchestrated pass over the multi-agent workflow."""

    __tablename__ = "generation_runs"
    __table_args__ = (
        Index("ix_runs_project_created", "project_id", "created_at"),
    )

    project_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    status: Mapped[RunStatus] = mapped_column(
        String(32),
        default=RunStatus.PENDING,
        index=True,
        nullable=False,
    )

    phase: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    progress: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    # Inputs resolved at run start.
    tech_stack: Mapped[dict[str, Any] | None] = mapped_column(
        JSONType,
        nullable=True,
    )

    analysis: Mapped[dict[str, Any] | None] = mapped_column(
        JSONType,
        nullable=True,
    )

    workflow_plan: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONType,
        nullable=True,
    )

    # Outputs.
    report: Mapped[dict[str, Any] | None] = mapped_column(
        JSONType,
        nullable=True,
    )

    memory_snapshot: Mapped[dict[str, Any] | None] = mapped_column(
        JSONType,
        nullable=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Accounting.
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    duration_seconds: Mapped[float | None] = mapped_column(
        nullable=True,
    )

    input_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    output_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    cached_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    file_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    project: Mapped[Project] = relationship(
        back_populates="runs",
        lazy="joined",
    )

    agent_executions: Mapped[list[AgentExecution]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="AgentExecution.sequence",
        lazy="selectin",
    )

    artifacts: Mapped[list[Artifact]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    events: Mapped[list[RunEvent]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="RunEvent.sequence",
        lazy="noload",
    )

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def __repr__(self) -> str:
        return f"<GenerationRun {self.id} {self.status}>"
