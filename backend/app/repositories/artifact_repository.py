"""Artifact persistence with automatic version tracking."""

from __future__ import annotations

from sqlalchemy import func, select

from app.core.enums import ArtifactKind
from app.models.artifact import Artifact
from app.models.project import Project
from app.models.run import GenerationRun
from app.repositories.base import BaseRepository


class ArtifactRepository(BaseRepository[Artifact]):
    model = Artifact

    async def list_for_run(
        self, run_id: str, *, kind: ArtifactKind | None = None
    ) -> list[Artifact]:
        stmt = select(Artifact).where(Artifact.run_id == run_id)
        if kind is not None:
            stmt = stmt.where(Artifact.kind == kind)
        stmt = stmt.order_by(Artifact.created_at)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_owned(self, artifact_id: str, owner_id: str) -> Artifact | None:
        """Fetch an artifact only if the caller owns the originating project."""
        stmt = (
            select(Artifact)
            .join(GenerationRun, GenerationRun.id == Artifact.run_id)
            .join(Project, Project.id == GenerationRun.project_id)
            .where(Artifact.id == artifact_id, Project.owner_id == owner_id)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def next_version(self, run_id: str, name: str) -> int:
        """Next version number for an artifact name within a run."""
        stmt = select(func.coalesce(func.max(Artifact.version), 0)).where(
            Artifact.run_id == run_id, Artifact.name == name
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one()) + 1

    async def find_package(self, run_id: str) -> Artifact | None:
        stmt = (
            select(Artifact)
            .where(Artifact.run_id == run_id, Artifact.kind == ArtifactKind.PACKAGE)
            .order_by(Artifact.version.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()
