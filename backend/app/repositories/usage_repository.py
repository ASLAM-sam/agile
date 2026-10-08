"""Usage repository for querying and aggregating UsageLog records."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.usage_log import UsageLog


class UsageRepository:
    """Encapsulates database operations for LLM usage logs."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, log_id: str) -> UsageLog | None:
        return await self._session.get(UsageLog, log_id)

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
    ) -> tuple[list[UsageLog], int]:
        """Query usage logs with filtering and pagination."""
        query = select(UsageLog)

        if task_id:
            query = query.where(UsageLog.task_id == task_id)
        if run_id:
            query = query.where(UsageLog.run_id == run_id)
        if agent_role:
            query = query.where(UsageLog.agent_role == agent_role)
        if provider:
            query = query.where(UsageLog.provider == provider)
        if model:
            query = query.where(UsageLog.model == model)
        if credential_slot:
            query = query.where(UsageLog.credential_slot == credential_slot)
        if status:
            query = query.where(UsageLog.status == status)
        if error_category:
            query = query.where(UsageLog.error_category == error_category)

        count_query = select(func.count()).select_from(query.subquery())
        total = (await self._session.execute(count_query)).scalar() or 0

        paged_query = (
            query.order_by(UsageLog.timestamp.desc(), UsageLog.request_number.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(paged_query)
        items = list(result.scalars().all())

        return items, total

    async def get_summary(
        self,
        *,
        task_id: str | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """Compute aggregated statistics across usage logs."""
        query = select(UsageLog)
        if task_id:
            query = query.where(UsageLog.task_id == task_id)
        if run_id:
            query = query.where(UsageLog.run_id == run_id)

        result = await self._session.execute(query)
        logs = list(result.scalars().all())

        if not logs:
            return {
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "fallback_requests": 0,
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_tokens": 0,
                "average_latency_ms": 0.0,
                "requests_by_provider": {},
                "requests_by_model": {},
                "requests_by_agent": {},
                "requests_by_credential": {},
            }

        total_requests = len(logs)
        successful = sum(1 for log in logs if log.status == "success")
        failed = sum(1 for log in logs if log.status != "success")
        fallbacks = sum(1 for log in logs if log.fallback_used)
        total_in = sum(log.input_tokens or 0 for log in logs)
        total_out = sum(log.output_tokens or 0 for log in logs)
        total_tok = sum(log.total_tokens or 0 for log in logs)
        avg_lat = sum(log.latency_ms for log in logs) / total_requests if total_requests else 0.0

        by_provider: dict[str, int] = {}
        by_model: dict[str, int] = {}
        by_agent: dict[str, int] = {}
        by_cred: dict[str, int] = {}

        for log in logs:
            by_provider[log.provider] = by_provider.get(log.provider, 0) + 1
            by_model[log.model] = by_model.get(log.model, 0) + 1
            by_agent[log.agent_role] = by_agent.get(log.agent_role, 0) + 1
            by_cred[log.credential_slot] = by_cred.get(log.credential_slot, 0) + 1

        return {
            "total_requests": total_requests,
            "successful_requests": successful,
            "failed_requests": failed,
            "fallback_requests": fallbacks,
            "total_input_tokens": total_in,
            "total_output_tokens": total_out,
            "total_tokens": total_tok,
            "average_latency_ms": round(avg_lat, 2),
            "requests_by_provider": by_provider,
            "requests_by_model": by_model,
            "requests_by_agent": by_agent,
            "requests_by_credential": by_cred,
        }
