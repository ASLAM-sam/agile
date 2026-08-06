"""Execution context handed to every agent.

Bundles the collaborators an agent needs — model provider, adapter registry,
shared memory and the progress reporter — so agent constructors stay uniform
and the workflow engine can build any agent the same way.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.adapters.base import ScaffoldContext
from app.adapters.registry import AdapterRegistry
from app.core.enums import AgentRole, LogLevel
from app.llm.protocol import LLMProvider
from app.workflow.memory import SharedProjectMemory

ProgressReporter = Callable[[AgentRole, int, str], Awaitable[None]]
LogReporter = Callable[[AgentRole, LogLevel, str, dict[str, Any]], Awaitable[None]]


@dataclass(slots=True)
class AgentContext:
    """Everything an agent needs to do its job."""

    memory: SharedProjectMemory
    llm: LLMProvider
    registry: AdapterRegistry
    report_progress: ProgressReporter
    report_log: LogReporter
    options: dict[str, Any] = field(default_factory=dict)

    async def progress(self, role: AgentRole, percent: int, message: str) -> None:
        """Publish a progress update for the live agent monitor."""
        await self.report_progress(role, max(0, min(100, percent)), message)

    async def log(
        self,
        role: AgentRole,
        message: str,
        *,
        level: LogLevel = LogLevel.INFO,
        **payload: Any,
    ) -> None:
        """Publish a console log line."""
        await self.report_log(role, level, message, payload)

    def scaffold_context(self, *, api_port: int = 8000, web_port: int = 5173) -> ScaffoldContext:
        """Build the adapter scaffold context from current memory state."""
        memory = self.memory
        return ScaffoldContext(
            project_name=memory.project_name,
            project_slug=memory.project_slug,
            description=(
                memory.analysis.executive_summary or memory.idea
            )[:500],
            needs_auth=memory.needs_auth,
            needs_database=memory.needs_database,
            needs_api=memory.analysis.needs_api,
            needs_backend=memory.needs_backend,
            needs_frontend=memory.needs_frontend,
            frontend_key=memory.tech_stack.frontend,
            backend_key=memory.tech_stack.backend,
            database_key=memory.tech_stack.database,
            api_port=api_port,
            web_port=web_port,
            entities=memory.analysis.entities,
        )
