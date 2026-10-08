"""Usage service coordinating database queries, quota status, and credential health."""

from __future__ import annotations

from typing import Any

from app.db.session import session_scope
from app.llm.credentials import CredentialManager
from app.llm.quota import get_quota_engine
from app.repositories.usage_repository import UsageRepository
from app.schemas.common import Page
from app.schemas.usage import (
    CredentialHealthItem,
    QuotaOverviewResponse,
    UsageLogItem,
    UsageSummaryResponse,
)


class UsageService:
    """Service layer for querying LLM usage logs and telemetry."""

    def __init__(self, credential_manager: CredentialManager | None = None) -> None:
        self._quota_engine = get_quota_engine()
        self._credential_manager = credential_manager or CredentialManager()

    async def list_logs(
        self,
        *,
        task_id: str | None = None,
        run_id: str | None = None,
        agent_role: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        credential_slot: str | None = None,
        status: str | None = None,
        error_category: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Page[UsageLogItem]:
        async with session_scope() as session:
            repo = UsageRepository(session)
            items, total = await repo.list_logs(
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
            parsed_items = [UsageLogItem.model_validate(item) for item in items]
            return Page(items=parsed_items, total=total, limit=limit, offset=offset)

    async def get_summary(
        self,
        *,
        task_id: str | None = None,
        run_id: str | None = None,
    ) -> UsageSummaryResponse:
        async with session_scope() as session:
            repo = UsageRepository(session)
            data = await repo.get_summary(task_id=task_id, run_id=run_id)
            return UsageSummaryResponse.model_validate(data)

    def get_quota_overview(self) -> QuotaOverviewResponse:
        overview = self._quota_engine.get_overview()
        return QuotaOverviewResponse.model_validate(overview)

    def get_credential_health(self) -> list[CredentialHealthItem]:
        snapshots = self._credential_manager.get_health_snapshot()
        return [CredentialHealthItem.model_validate(s) for s in snapshots]


_global_usage_service: UsageService | None = None


def get_usage_service() -> UsageService:
    global _global_usage_service
    if _global_usage_service is None:
        _global_usage_service = UsageService()
    return _global_usage_service
