"""In-process event bus backing the live generation console.

Each run owns a topic. Subscribers receive an independent bounded queue, so a
slow client cannot stall the run: its queue drops the oldest entries instead.
Events are also persisted by the orchestrator, so history survives a reconnect.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.core.enums import EventType, LogLevel
from app.core.logging import get_logger

logger = get_logger(__name__)

_QUEUE_MAXSIZE = 512


@dataclass(slots=True)
class RunEventMessage:
    """A single event broadcast to console subscribers."""

    run_id: str
    event_type: EventType
    message: str
    sequence: int = 0
    level: LogLevel = LogLevel.INFO
    agent_role: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def as_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "run_id": self.run_id,
            "type": self.event_type.value,
            "level": self.level.value,
            "agent": self.agent_role,
            "message": self.message,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
        }


class RunEventBus:
    """Fan-out broker for run events, keyed by run id."""

    def __init__(self) -> None:
        self._topics: dict[str, set[asyncio.Queue[RunEventMessage | None]]] = {}
        self._lock = asyncio.Lock()

    async def publish(self, event: RunEventMessage) -> None:
        """Broadcast an event to every subscriber of its run."""
        async with self._lock:
            queues = list(self._topics.get(event.run_id, ()))

        for queue in queues:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Drop the oldest entry to make room; a lagging console must
                # never apply backpressure to the generation itself.
                try:
                    queue.get_nowait()
                    queue.put_nowait(event)
                except (asyncio.QueueEmpty, asyncio.QueueFull):  # pragma: no cover
                    logger.warning("event_dropped", extra={"run_id": event.run_id})

    async def close_topic(self, run_id: str) -> None:
        """Signal end-of-stream to every subscriber, then drop the topic."""
        async with self._lock:
            queues = list(self._topics.pop(run_id, ()))
        for queue in queues:
            # The sentinel is best effort: a full queue means the subscriber is
            # already far behind and will see the closed topic on its next read.
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(None)

    @asynccontextmanager
    async def subscribe(self, run_id: str) -> AsyncIterator[asyncio.Queue[RunEventMessage | None]]:
        """Subscribe for the duration of the context."""
        queue: asyncio.Queue[RunEventMessage | None] = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
        async with self._lock:
            self._topics.setdefault(run_id, set()).add(queue)
        try:
            yield queue
        finally:
            async with self._lock:
                subscribers = self._topics.get(run_id)
                if subscribers is not None:
                    subscribers.discard(queue)
                    if not subscribers:
                        self._topics.pop(run_id, None)

    def subscriber_count(self, run_id: str) -> int:
        return len(self._topics.get(run_id, ()))

    @property
    def active_topics(self) -> int:
        return len(self._topics)


_bus: RunEventBus | None = None


def get_event_bus() -> RunEventBus:
    """Process-wide event bus singleton."""
    global _bus
    if _bus is None:
        _bus = RunEventBus()
    return _bus
