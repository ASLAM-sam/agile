"""Usage and Observability API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.schemas.common import Page
from app.schemas.usage import (
    CredentialHealthItem,
    QuotaOverviewResponse,
    UsageLogItem,
    UsageSummaryResponse,
)
from app.services.usage_service import UsageService, get_usage_service

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("/logs", response_model=Page[UsageLogItem])
async def list_usage_logs(
    task_id: str | None = Query(None, description="Filter by task ID"),
    run_id: str | None = Query(None, description="Filter by run ID"),
    agent_role: str | None = Query(None, description="Filter by agent role"),
    provider: str | None = Query(None, description="Filter by provider"),
    model: str | None = Query(None, description="Filter by model"),
    credential_slot: str | None = Query(None, description="Filter by credential slot"),
    status: str | None = Query(None, description="Filter by status (e.g. success, failed, budget_exceeded)"),
    error_category: str | None = Query(None, description="Filter by error category"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    service: UsageService = Depends(get_usage_service),
) -> Page[UsageLogItem]:
    """List paginated LLM usage logs with granular filtering."""
    return await service.list_logs(
        task_id=task_id,
        run_id=run_id,
        agent_role=agent_role,
        provider=provider,
        model=model,
        credential_slot=credential_slot,
        status=status,
        error_category=error_category,
        limit=limit,
        offset=offset,
    )


@router.get("/summary", response_model=UsageSummaryResponse)
async def get_usage_summary(
    task_id: str | None = Query(None, description="Filter by task ID"),
    run_id: str | None = Query(None, description="Filter by run ID"),
    service: UsageService = Depends(get_usage_service),
) -> UsageSummaryResponse:
    """Retrieve aggregated telemetry across all LLM requests."""
    return await service.get_summary(task_id=task_id, run_id=run_id)


@router.get("/quota", response_model=QuotaOverviewResponse)
def get_quota_overview(
    service: UsageService = Depends(get_usage_service),
) -> QuotaOverviewResponse:
    """Retrieve real-time multi-dimensional quota metrics."""
    return service.get_quota_overview()


@router.get("/credentials", response_model=list[CredentialHealthItem])
def get_credential_health(
    service: UsageService = Depends(get_usage_service),
) -> list[CredentialHealthItem]:
    """Retrieve health and failure metrics across all primary and backup credential slots."""
    return service.get_credential_health()
