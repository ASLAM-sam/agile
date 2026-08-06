"""Project service."""

from __future__ import annotations

import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.models.project import Project
from app.models.user import User
from app.repositories.project_repository import ProjectRepository
from app.repositories.run_repository import RunRepository

logger = get_logger(__name__)

_SLUG_INVALID = re.compile(r"[^a-z0-9]+")
_STOPWORDS = frozenset(
    {"a", "an", "the", "for", "with", "and", "of", "to", "in", "on", "build", "create", "make"}
)


class ProjectService:
    """Project lifecycle and dashboard aggregation."""

    def __init__(self, session: AsyncSession) -> None:
        self._projects = ProjectRepository(session)
        self._runs = RunRepository(session)

    async def create(
        self, owner: User, *, idea: str, name: str | None = None, tags: list[str] | None = None
    ) -> Project:
        """Create a project from an idea."""
        display_name = (name or derive_name(idea)).strip()[:200]
        slug = await self._unique_slug(owner.id, display_name)

        project = await self._projects.add(
            Project(
                name=display_name,
                idea=idea,
                slug=slug,
                owner_id=owner.id,
                tags=tags or [],
            )
        )
        logger.info(
            "project_created", extra={"project_id": project.id, "owner_id": owner.id}
        )
        return project

    async def get_owned(self, project_id: str, owner: User) -> Project:
        project = await self._projects.get_owned(project_id, owner.id)
        if project is None:
            raise NotFoundError("Project not found.")
        return project

    async def list_for_owner(
        self, owner: User, *, search: str | None = None, limit: int = 25, offset: int = 0
    ) -> tuple[list[Project], int]:
        projects = await self._projects.list_for_owner(
            owner.id, search=search, limit=limit, offset=offset
        )
        total = await self._projects.count_for_owner(owner.id, search=search)
        return projects, total

    async def update(
        self,
        project: Project,
        *,
        name: str | None = None,
        tags: list[str] | None = None,
    ) -> Project:
        if name is not None:
            project.name = name.strip()[:200]
        if tags is not None:
            project.tags = tags
        await self._projects.flush()
        return project

    async def delete(self, project: Project) -> None:
        """Delete a project and everything it owns."""
        await self._projects.delete(project)
        logger.info("project_deleted", extra={"project_id": project.id})

    async def dashboard_stats(self, owner: User, *, active_runs: int) -> dict[str, object]:
        stats = await self._runs.owner_statistics(owner.id)
        return {
            "total_projects": await self._projects.count_for_owner(owner.id),
            "total_runs": stats["total_runs"],
            "completed_runs": stats["completed_runs"],
            "total_files_generated": stats["total_files"],
            "total_generation_seconds": round(stats["total_seconds"], 1),
            "active_runs": active_runs,
        }

    async def _unique_slug(self, owner_id: str, name: str) -> str:
        """Slug unique within one owner's projects."""
        base = slugify(name)
        candidate = base
        suffix = 2
        while await self._projects.slug_taken(owner_id, candidate):
            candidate = f"{base}-{suffix}"
            suffix += 1
            if suffix > 100:  # pragma: no cover - pathological
                candidate = f"{base}-{owner_id[:6]}"
                break
        return candidate


def slugify(value: str) -> str:
    """URL and filesystem safe identifier."""
    slug = _SLUG_INVALID.sub("-", value.lower()).strip("-")
    return (slug or "project")[:60].rstrip("-")


def derive_name(idea: str) -> str:
    """Derive a readable project name from a free-text idea.

    A provisional name only — the Manager agent replaces it with a considered
    one during the run.
    """
    words = re.findall(r"[A-Za-z0-9]+", idea)
    meaningful = [w for w in words if w.lower() not in _STOPWORDS][:4]
    if not meaningful:
        return "Untitled Project"
    return " ".join(word.capitalize() for word in meaningful)[:200]
