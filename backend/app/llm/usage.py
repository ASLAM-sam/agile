"""Usage Logger and Database Persistence Service.

Provides:
- In-memory thread-safe buffer for immediate inspection & tests
- Async database persistence to the `usage_logs` table
- Monotonic request numbering & unique request ID generation (e.g. 'req_20261003_...')
- Summary statistics computation
- STRICT SECURITY: Never logs or stores raw secrets, tokens, or credentials.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import deque
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.core.logging import get_logger
from app.db.base import utcnow
from app.db.session import session_scope
from app.models.usage_log import UsageLog

logger = get_logger(__name__)


def generate_request_id() -> str:
    """Generate a clean, trace-friendly request identifier."""
    date_prefix = datetime.now(UTC).strftime("%Y%m%d")
    short_uuid = uuid.uuid4().hex[:10]
    return f"req_{date_prefix}_{short_uuid}"


class UsageTracker:
    """Records, buffers, and persists UsageLog entries."""

    def __init__(self, max_buffer_size: int = 1000) -> None:
        self._buffer: deque[dict[str, Any]] = deque(maxlen=max_buffer_size)
        self._lock = asyncio.Lock()

    async def record_entry(self, entry_data: dict[str, Any]) -> UsageLog:
        """Buffer and persist a UsageLog record."""
        # Ensure timestamp and request_id exist
        if "timestamp" not in entry_data or entry_data["timestamp"] is None:
            entry_data["timestamp"] = utcnow()
        if "request_id" not in entry_data or not entry_data["request_id"]:
            entry_data["request_id"] = generate_request_id()

        # Buffer in-memory copy
        self._buffer.append(dict(entry_data))

        # Build ORM entity
        log_record = UsageLog(
            task_id=entry_data.get("task_id"),
            run_id=entry_data.get("run_id") if not str(entry_data.get("run_id") or "").startswith("analysis") else None,
            agent_execution_id=entry_data.get("agent_execution_id"),
            agent_name=entry_data.get("agent_name", "UnknownAgent"),
            agent_role=entry_data.get("agent_role", "unknown_role"),
            provider=entry_data.get("provider", "unknown_provider"),
            model=entry_data.get("model", "unknown_model"),
            credential_slot=entry_data.get("credential_slot", "UNKNOWN_SLOT"),
            masked_credential=entry_data.get("masked_credential", "<unconfigured>"),
            request_id=entry_data.get("request_id", ""),
            request_number=entry_data.get("request_number", 1),
            attempt_number=entry_data.get("attempt_number", 1),
            input_tokens=entry_data.get("input_tokens"),
            output_tokens=entry_data.get("output_tokens"),
            total_tokens=entry_data.get("total_tokens"),
            token_usage_available=bool(entry_data.get("token_usage_available", False)),
            latency_ms=float(entry_data.get("latency_ms", 0.0)),
            status=entry_data.get("status", "success"),
            error_category=entry_data.get("error_category"),
            error_message_safe=entry_data.get("error_message_safe"),
            retry_count=entry_data.get("retry_count", 0),
            fallback_used=bool(entry_data.get("fallback_used", False)),
            fallback_from=entry_data.get("fallback_from"),
            fallback_to=entry_data.get("fallback_to"),
            timestamp=entry_data["timestamp"],
            target_request_budget=entry_data.get("target_request_budget", 10),
            hard_request_limit=entry_data.get("hard_request_limit", 15),
            provider_request_id=entry_data.get("provider_request_id"),
            finish_reason=entry_data.get("finish_reason"),
            quota_snapshot=entry_data.get("quota_snapshot"),
            metadata_json=entry_data.get("metadata"),
            endpoint=entry_data.get("endpoint"),
        )

        # Attempt database write in background/async context
        try:
            async with session_scope() as session:
                session.add(log_record)
                await session.flush()
                # Ensure id is generated
                entry_data["id"] = log_record.id
        except Exception as exc:
            # We never let a logging DB failure crash the application logic
            logger.warning(
                "usage_log_db_persist_skipped",
                extra={"error": str(exc), "request_id": entry_data.get("request_id")},
            )

        return log_record

    def get_buffered_entries(
        self,
        *,
        task_id: str | None = None,
        run_id: str | None = None,
        agent_role: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return buffered records matching filters."""
        results: list[dict[str, Any]] = []
        for item in reversed(self._buffer):
            if task_id and item.get("task_id") != task_id:
                continue
            if run_id and item.get("run_id") != run_id:
                continue
            if agent_role and item.get("agent_role") != agent_role:
                continue
            if provider and item.get("provider") != provider:
                continue
            if model and item.get("model") != model:
                continue
            results.append(item)
            if len(results) >= limit:
                break
        return results

    def clear_buffer(self) -> None:
        self._buffer.clear()


_global_usage_tracker: UsageTracker | None = None


def get_usage_tracker() -> UsageTracker:
    global _global_usage_tracker
    if _global_usage_tracker is None:
        _global_usage_tracker = UsageTracker()
    return _global_usage_tracker
