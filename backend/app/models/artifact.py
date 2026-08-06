"""Artifact model — a versioned deliverable produced by a run."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import AgentRole, ArtifactKind
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.types import JSONType

if TYPE_CHECKING:
    from app.models.run import GenerationRun


class Artifact(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A document, code bundle or package emitted during generation.

    Text-bearing artifacts (SRS, architecture, reports) store their content
    inline. Binary deliverables (the ZIP package) store a filesystem path.
    """

    __tablename__ = "artifacts"

    run_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("generation_runs.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    kind: Mapped[ArtifactKind] = mapped_column(String(32), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    produced_by: Mapped[AgentRole | None] = mapped_column(String(48), nullable=True)

    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_type: Mapped[str] = mapped_column(String(80), default="text/markdown", nullable=False)
    storage_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    artifact_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)

    run: Mapped[GenerationRun] = relationship(back_populates="artifacts")

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<Artifact {self.kind}:{self.name} v{self.version}>"
