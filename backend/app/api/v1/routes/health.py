"""Health and readiness routes."""

from __future__ import annotations

from fastapi import APIRouter, status
from sqlalchemy import text

from app.api.deps import OrchestratorDep, SessionDep
from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.common import HealthResponse

logger = get_logger(__name__)

router = APIRouter(tags=["System"])


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Service health and readiness",
)
async def health(session: SessionDep, orchestrator: OrchestratorDep) -> HealthResponse:
    """Report liveness plus the dependencies the service actually needs."""
    try:
        await session.execute(text("SELECT 1"))
        database = "connected"
    except Exception as exc:  # noqa: BLE001 - health must report, not raise
        logger.error("health_database_check_failed", extra={"error": str(exc)})
        database = "unavailable"

    return HealthResponse(
        status="ok" if database == "connected" else "degraded",
        version=settings.app_version,
        environment=settings.environment,
        database=database,
        llm_configured=settings.llm_configured,
        active_runs=orchestrator.active_count,
    )
