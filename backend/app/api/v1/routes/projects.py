"""Project routes."""

from __future__ import annotations

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, OrchestratorDep, ProjectServiceDep
from app.schemas.common import MessageResponse, Page
from app.schemas.generation import RunSummary
from app.schemas.project import (
    CreateProjectRequest,
    DashboardStats,
    ProjectDetail,
    ProjectSummary,
    UpdateProjectRequest,
)

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.post(
    "",
    response_model=ProjectDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a software idea",
)
async def create_project(
    payload: CreateProjectRequest, user: CurrentUser, service: ProjectServiceDep
) -> ProjectDetail:
    project = await service.create(
        user, idea=payload.idea, name=payload.name, tags=payload.tags
    )
    return ProjectDetail.model_validate(project)


@router.get(
    "",
    response_model=Page[ProjectSummary],
    status_code=status.HTTP_200_OK,
    summary="List the caller's projects",
)
async def list_projects(
    user: CurrentUser,
    service: ProjectServiceDep,
    search: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> Page[ProjectSummary]:
    projects, total = await service.list_for_owner(
        user, search=search, limit=limit, offset=offset
    )
    return Page[ProjectSummary](
        items=[ProjectSummary.model_validate(p) for p in projects],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/stats",
    response_model=DashboardStats,
    status_code=status.HTTP_200_OK,
    summary="Dashboard counters",
)
async def dashboard_stats(
    user: CurrentUser, service: ProjectServiceDep, orchestrator: OrchestratorDep
) -> DashboardStats:
    stats = await service.dashboard_stats(user, active_runs=orchestrator.active_count)
    return DashboardStats.model_validate(stats)


@router.get(
    "/{project_id}",
    response_model=ProjectDetail,
    status_code=status.HTTP_200_OK,
    summary="Fetch one project",
)
async def get_project(
    project_id: str, user: CurrentUser, service: ProjectServiceDep
) -> ProjectDetail:
    project = await service.get_owned(project_id, user)
    detail = ProjectDetail.model_validate(project)
    detail.run_count = len(project.runs)
    if project.runs:
        latest = project.runs[0]
        detail.latest_run_id = latest.id
        detail.latest_run_status = latest.status.value if hasattr(latest.status, "value") else str(latest.status)
    return detail


@router.patch(
    "/{project_id}",
    response_model=ProjectDetail,
    status_code=status.HTTP_200_OK,
    summary="Update a project",
)
async def update_project(
    project_id: str,
    payload: UpdateProjectRequest,
    user: CurrentUser,
    service: ProjectServiceDep,
) -> ProjectDetail:
    project = await service.get_owned(project_id, user)
    updated = await service.update(project, name=payload.name, tags=payload.tags)
    return ProjectDetail.model_validate(updated)


@router.delete(
    "/{project_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete a project and all its runs",
)
async def delete_project(
    project_id: str, user: CurrentUser, service: ProjectServiceDep
) -> MessageResponse:
    project = await service.get_owned(project_id, user)
    await service.delete(project)
    return MessageResponse(message=f"Project '{project.name}' was deleted.")


@router.get(
    "/{project_id}/runs",
    response_model=list[RunSummary],
    status_code=status.HTTP_200_OK,
    summary="List a project's generation runs",
)
async def list_project_runs(
    project_id: str, user: CurrentUser, service: ProjectServiceDep
) -> list[RunSummary]:
    project = await service.get_owned(project_id, user)
    return [RunSummary.model_validate(run) for run in project.runs]
