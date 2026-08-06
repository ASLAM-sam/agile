"""Generation routes: analysis, run control and the live event stream."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import StreamingResponse

from app.api.deps import (
    CurrentUser,
    GenerationServiceDep,
    OrchestratorDep,
    ProjectServiceDep,
    SessionDep,
)
from app.core.enums import EventType, RunStatus
from app.core.logging import get_logger
from app.repositories.run_repository import RunEventRepository, RunRepository
from app.schemas.common import MessageResponse
from app.schemas.generation import (
    AgentExecutionResponse,
    AnalysisResponse,
    RunDetail,
    RunEventResponse,
    RunSummary,
    StartRunRequest,
    WorkspaceFileResponse,
)
from app.workflow.events import get_event_bus

logger = get_logger(__name__)

router = APIRouter(tags=["Generation"])

#: Idle interval after which a comment frame is sent to hold the SSE
#: connection open through proxies that close quiet streams.
_HEARTBEAT_SECONDS = 20.0


@router.post(
    "/projects/{project_id}/analyze",
    response_model=AnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Analyse requirements and recommend a technology stack",
)
async def analyse_project(
    project_id: str,
    user: CurrentUser,
    projects: ProjectServiceDep,
    generation: GenerationServiceDep,
) -> AnalysisResponse:
    """Run requirement analysis. Cached per project after the first call."""
    project = await projects.get_owned(project_id, user)
    result = await generation.analyse(project)
    return AnalysisResponse.model_validate(result)


@router.post(
    "/projects/{project_id}/runs",
    response_model=RunDetail,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start a generation run",
)
async def start_run(
    project_id: str,
    payload: StartRunRequest,
    user: CurrentUser,
    projects: ProjectServiceDep,
    generation: GenerationServiceDep,
    orchestrator: OrchestratorDep,
    session: SessionDep,
) -> RunDetail:
    """Queue a run and launch it in the background."""
    project = await projects.get_owned(project_id, user)

    override = payload.tech_stack.model_dump() if payload.tech_stack else None
    run = await generation.create_run(
        project, user, stack_override=override, active_runs=orchestrator.active_count
    )

    # Commit before launching: the background task opens its own session and
    # must be able to read this run.
    await session.commit()

    orchestrator.start(run.id)

    detail = RunDetail.model_validate(run)
    detail.project_name = project.name
    return detail


@router.get(
    "/runs/{run_id}",
    response_model=RunDetail,
    status_code=status.HTTP_200_OK,
    summary="Fetch a run with its full execution state",
)
async def get_run(
    run_id: str, user: CurrentUser, generation: GenerationServiceDep
) -> RunDetail:
    run = await generation.get_owned_run(run_id, user)
    detail = RunDetail.model_validate(run)
    detail.project_name = run.project.name if run.project else None
    detail.agents = [
        AgentExecutionResponse.model_validate(execution)
        for execution in sorted(run.agent_executions, key=lambda e: e.sequence)
    ]
    detail.artifact_count = len(run.artifacts)
    return detail


@router.get(
    "/runs",
    response_model=list[RunSummary],
    status_code=status.HTTP_200_OK,
    summary="Recent runs across all of the caller's projects",
)
async def list_runs(
    user: CurrentUser,
    session: SessionDep,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[RunSummary]:
    runs = await RunRepository(session).list_recent_for_owner(user.id, limit=limit)
    return [RunSummary.model_validate(run) for run in runs]


@router.get(
    "/runs/{run_id}/events",
    response_model=list[RunEventResponse],
    status_code=status.HTTP_200_OK,
    summary="Persisted event history for a run",
)
async def get_run_events(
    run_id: str,
    user: CurrentUser,
    generation: GenerationServiceDep,
    session: SessionDep,
    after: int = Query(default=0, ge=0, description="Return events after this sequence."),
    limit: int = Query(default=500, ge=1, le=2000),
) -> list[RunEventResponse]:
    await generation.get_owned_run(run_id, user)
    events = await RunEventRepository(session).list_for_run(
        run_id, after_sequence=after, limit=limit
    )
    return [RunEventResponse.model_validate(event) for event in events]


@router.get(
    "/runs/{run_id}/files",
    response_model=list[WorkspaceFileResponse],
    status_code=status.HTTP_200_OK,
    summary="File manifest of a completed run",
)
async def get_run_files(
    run_id: str, user: CurrentUser, generation: GenerationServiceDep
) -> list[WorkspaceFileResponse]:
    run = await generation.get_owned_run(run_id, user)
    snapshot = run.memory_snapshot or {}
    return [
        WorkspaceFileResponse(
            path=entry.get("path", ""),
            description=entry.get("description", ""),
            produced_by=entry.get("produced_by"),
            size_bytes=entry.get("size_bytes", 0),
            line_count=entry.get("line_count", 0),
        )
        for entry in snapshot.get("manifest", [])
    ]


@router.post(
    "/runs/{run_id}/cancel",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Cancel an in-flight run",
)
async def cancel_run(
    run_id: str,
    user: CurrentUser,
    generation: GenerationServiceDep,
    orchestrator: OrchestratorDep,
) -> MessageResponse:
    run = await generation.get_owned_run(run_id, user)
    if RunStatus(run.status).is_terminal:
        return MessageResponse(message=f"Run already finished with status '{run.status}'.")

    cancelled = await orchestrator.cancel(run_id)
    return MessageResponse(
        message="Cancellation requested." if cancelled else "Run is not currently executing."
    )


@router.get(
    "/runs/{run_id}/stream",
    summary="Live event stream for a run (Server-Sent Events)",
    response_class=StreamingResponse,
)
async def stream_run(
    run_id: str,
    request: Request,
    user: CurrentUser,
    generation: GenerationServiceDep,
    session: SessionDep,
    after: int = Query(default=0, ge=0, description="Replay persisted events after this sequence."),
) -> StreamingResponse:
    """Stream run events as they happen.

    History is replayed first, then live events are tailed, so a client that
    connects late — or reconnects after a drop — sees the complete timeline
    with no gap. Events already replayed are suppressed by sequence number.
    """
    run = await generation.get_owned_run(run_id, user)
    history = await RunEventRepository(session).list_for_run(run_id, after_sequence=after)
    terminal = RunStatus(run.status).is_terminal

    async def event_source() -> AsyncIterator[str]:
        bus = get_event_bus()
        highest = after

        async with bus.subscribe(run_id) as queue:
            # 1. Replay everything already persisted.
            for event in history:
                highest = max(highest, event.sequence)
                yield _sse(
                    event.event_type.value,
                    {
                        "sequence": event.sequence,
                        "run_id": run_id,
                        "type": event.event_type.value,
                        "level": event.level.value,
                        "agent": event.agent_role,
                        "message": event.message,
                        "payload": event.payload or {},
                        "timestamp": event.created_at.isoformat(),
                    },
                )

            # 2. A finished run has no more live events to wait for.
            if terminal:
                yield _sse("stream.end", {"reason": "run_finished", "status": run.status})
                return

            # 3. Tail live events until the run ends or the client disconnects.
            while True:
                if await request.is_disconnected():
                    break
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=_HEARTBEAT_SECONDS)
                except TimeoutError:
                    yield ": heartbeat\n\n"
                    continue

                if message is None:  # topic closed by the orchestrator
                    yield _sse("stream.end", {"reason": "run_finished"})
                    break

                if message.sequence <= highest:
                    continue  # already delivered during replay
                highest = message.sequence

                yield _sse(message.event_type.value, message.as_dict())

                if message.event_type in {
                    EventType.RUN_COMPLETED,
                    EventType.RUN_FAILED,
                    EventType.RUN_CANCELLED,
                }:
                    yield _sse("stream.end", {"reason": message.event_type.value})
                    break

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            # Disable proxy buffering, which otherwise batches SSE frames and
            # defeats the point of streaming.
            "X-Accel-Buffering": "no",
        },
    )


def _sse(event_name: str, data: dict) -> str:
    """Format one Server-Sent Event frame."""
    payload = json.dumps(data, default=str)
    return f"event: {event_name}\ndata: {payload}\n\n"
