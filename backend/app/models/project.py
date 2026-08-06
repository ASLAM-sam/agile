"""Project model — one software idea and its generation history."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.types import JSONType

if TYPE_CHECKING:
    from app.models.run import GenerationRun
    from app.models.user import User


class Project(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A software idea submitted for autonomous engineering."""

    __tablename__ = "projects"
    __table_args__ = (Index("ix_projects_owner_created", "owner_id", "created_at"),)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    idea: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    slug: Mapped[str] = mapped_column(String(120), index=True, nullable=False)

    owner_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # Latest accepted analysis and stack, denormalised for fast dashboard reads.
    analysis: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    tech_stack: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)

    owner: Mapped[User] = relationship(back_populates="projects", lazy="joined")
    runs: Mapped[list[GenerationRun]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="desc(GenerationRun.created_at)",
        lazy="selectin",
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<Project {self.name}>"
