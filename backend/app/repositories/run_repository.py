"""Generation run, agent execution and event persistence."""

from __future__ import annotations

from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import selectinload

from app.core.enums import AgentRole, RunStatus
from app.models.agent_execution import AgentExecution
from app.models.project import Project
from app.models.run import GenerationRun
from app.models.run_event import RunEvent
from app.repositories.base import BaseRepository


class RunRepository(BaseRepository[GenerationRun]):
    model = GenerationRun

    async def get_with_details(self, run_id: str) -> GenerationRun | None:
        stmt = (
            select(GenerationRun)
            .where(GenerationRun.id == run_id)
            .options(
                selectinload(GenerationRun.agent_executions),
                selectinload(GenerationRun.artifacts),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().unique().first()

    async def get_owned(self, run_id: str, owner_id: str) -> GenerationRun | None:
        """Fetch a run only if the caller owns its parent project."""
        stmt = (
            select(GenerationRun)
            .join(Project, Project.id == GenerationRun.project_id)
            .where(GenerationRun.id == run_id, Project.owner_id == owner_id)
            .options(
                selectinload(GenerationRun.agent_executions),
                selectinload(GenerationRun.artifacts),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().unique().first()

    async def list_for_project(
        self, project_id: str, *, limit: int = 25, offset: int = 0
    ) -> list[GenerationRun]:
        stmt = (
            select(GenerationRun)
            .where(GenerationRun.project_id == project_id)
            .order_by(GenerationRun.created_at.desc())
            .limit(limit)
            .offset(offset)
            .options(selectinload(GenerationRun.agent_executions))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())

    async def list_recent_for_owner(
        self, owner_id: str, *, limit: int = 20
    ) -> list[GenerationRun]:
        stmt = (
            select(GenerationRun)
            .join(Project, Project.id == GenerationRun.project_id)
            .where(Project.owner_id == owner_id)
            .order_by(GenerationRun.created_at.desc())
            .limit(limit)
            .options(selectinload(GenerationRun.agent_executions))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())

    async def count_active(self) -> int:
        """Number of runs currently occupying an execution slot."""
        active = [
            RunStatus.PENDING,
            RunStatus.ANALYZING,
            RunStatus.RUNNING,
            RunStatus.PACKAGING,
        ]
        stmt = (
            select(func.count())
            .select_from(GenerationRun)
            .where(GenerationRun.status.in_(active))
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def owner_statistics(self, owner_id: str) -> dict[str, Any]:
        """Aggregate dashboard counters for one owner in a single round trip."""
        completed_flag = case(
            (GenerationRun.status == RunStatus.COMPLETED, 1), else_=0
        )
        stmt = (
            select(
                func.count(GenerationRun.id),
                func.coalesce(func.sum(completed_flag), 0),
                func.coalesce(func.sum(GenerationRun.file_count), 0),
                func.coalesce(func.sum(GenerationRun.duration_seconds), 0.0),
            )
            .join(Project, Project.id == GenerationRun.project_id)
            .where(Project.owner_id == owner_id)
        )
        total, completed, files, seconds = (await self.session.execute(stmt)).one()
        return {
            "total_runs": int(total or 0),
            "completed_runs": int(completed or 0),
            "total_files": int(files or 0),
            "total_seconds": float(seconds or 0.0),
        }


class AgentExecutionRepository(BaseRepository[AgentExecution]):
    model = AgentExecution

    async def get_for_run(self, run_id: str, role: AgentRole) -> AgentExecution | None:
        stmt = select(AgentExecution).where(
            AgentExecution.run_id == run_id, AgentExecution.role == role
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_for_run(self, run_id: str) -> list[AgentExecution]:
        stmt = (
            select(AgentExecution)
            .where(AgentExecution.run_id == run_id)
            .order_by(AgentExecution.sequence)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class RunEventRepository(BaseRepository[RunEvent]):
    model = RunEvent

    async def list_for_run(
        self, run_id: str, *, after_sequence: int = 0, limit: int = 1000
    ) -> list[RunEvent]:
        stmt = (
            select(RunEvent)
            .where(RunEvent.run_id == run_id, RunEvent.sequence > after_sequence)
            .order_by(RunEvent.sequence)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def next_sequence(self, run_id: str) -> int:
        stmt = select(func.coalesce(func.max(RunEvent.sequence), 0)).where(
            RunEvent.run_id == run_id
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one()) + 1
