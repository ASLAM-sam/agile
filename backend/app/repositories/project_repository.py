"""Project persistence."""

from __future__ import annotations

from sqlalchemy import func, or_, select

from app.models.project import Project
from app.repositories.base import BaseRepository


class ProjectRepository(BaseRepository[Project]):
    model = Project

    async def list_for_owner(
        self,
        owner_id: str,
        *,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Project]:
        stmt = select(Project).where(Project.owner_id == owner_id)
        if search:
            pattern = f"%{search.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(Project.name).like(pattern),
                    func.lower(Project.idea).like(pattern),
                )
            )
        stmt = stmt.order_by(Project.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())

    async def count_for_owner(self, owner_id: str, *, search: str | None = None) -> int:
        stmt = select(func.count()).select_from(Project).where(Project.owner_id == owner_id)
        if search:
            pattern = f"%{search.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(Project.name).like(pattern),
                    func.lower(Project.idea).like(pattern),
                )
            )
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def get_owned(self, project_id: str, owner_id: str) -> Project | None:
        """Fetch a project only if it belongs to the given owner."""
        stmt = select(Project).where(Project.id == project_id, Project.owner_id == owner_id)
        result = await self.session.execute(stmt)
        return result.scalars().unique().first()

    async def slug_taken(self, owner_id: str, slug: str) -> bool:
        stmt = select(func.count()).select_from(Project).where(
            Project.owner_id == owner_id, Project.slug == slug
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one()) > 0
