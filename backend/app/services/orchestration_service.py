"""Run orchestration.

Bridges the workflow engine to persistence, the event bus and packaging. It
owns the run lifecycle: queue, execute, persist, package, report.

Runs execute as detached asyncio tasks with their own database sessions. A
request-scoped session cannot be used, because the HTTP request returns long
before the run finishes.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Any

from app.adapters.registry import AdapterRegistry, get_registry
from app.agents.context import AgentContext
from app.agents.registry import AgentRegistry, get_agent_registry
from app.core.config import settings
from app.core.enums import (
    AgentRole,
    AgentStatus,
    ArtifactKind,
    EventType,
    LogLevel,
    RunStatus,
)
from app.core.exceptions import ConfigurationError, NotFoundError
from app.core.logging import get_logger
from app.db.session import session_scope
from app.llm.factory import build_llm_provider
from app.llm.protocol import LLMProvider
from app.models.agent_execution import AgentExecution
from app.models.artifact import Artifact
from app.models.run_event import RunEvent
from app.packaging.report import build_report, render_report_markdown
from app.packaging.zip_builder import ZipPackager
from app.repositories.artifact_repository import ArtifactRepository
from app.repositories.run_repository import (
    AgentExecutionRepository,
    RunEventRepository,
    RunRepository,
)
from app.workflow.engine import StepOutcome, WorkflowEngine, preflight_skips
from app.workflow.events import RunEventBus, RunEventMessage, get_event_bus
from app.workflow.memory import RequirementAnalysis, SharedProjectMemory, TechStack
from app.workflow.planner import PlannedStep, WorkflowPlan, build_plan

logger = get_logger(__name__)


class RunOrchestrator:
    """Executes generation runs and records everything they produce."""

    def __init__(
        self,
        *,
        adapters: AdapterRegistry | None = None,
        agents: AgentRegistry | None = None,
        event_bus: RunEventBus | None = None,
        packager: ZipPackager | None = None,
        llm_factory: Any = None,
    ) -> None:
        self._adapters = adapters or get_registry()
        self._agents = agents or get_agent_registry()
        self._bus = event_bus or get_event_bus()
        self._packager = packager or ZipPackager()
        self._llm_factory = llm_factory or build_llm_provider
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._sequence: dict[str, int] = {}

    # --- lifecycle -------------------------------------------------------

    def start(self, run_id: str) -> None:
        """Launch a run in the background. Returns immediately."""
        if run_id in self._tasks and not self._tasks[run_id].done():
            logger.warning("run_already_active", extra={"run_id": run_id})
            return

        task = asyncio.create_task(self._execute(run_id), name=f"aegis-run-{run_id}")
        self._tasks[run_id] = task
        task.add_done_callback(lambda _: self._tasks.pop(run_id, None))

    def is_active(self, run_id: str) -> bool:
        task = self._tasks.get(run_id)
        return task is not None and not task.done()

    @property
    def active_count(self) -> int:
        return sum(1 for task in self._tasks.values() if not task.done())

    async def cancel(self, run_id: str) -> bool:
        """Request cancellation of an in-flight run."""
        task = self._tasks.get(run_id)
        if task is None or task.done():
            return False
        task.cancel()
        return True

    async def shutdown(self) -> None:
        """Cancel every in-flight run and wait for them to unwind."""
        tasks = [task for task in self._tasks.values() if not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("orchestrator_shutdown", extra={"cancelled": len(tasks)})

    # --- execution -------------------------------------------------------

    async def _execute(self, run_id: str) -> None:
        """Full run lifecycle. Never raises; failures are recorded."""
        started_at = datetime.now(UTC)
        started_perf = time.perf_counter()
        memory: SharedProjectMemory | None = None

        try:
            memory = await self._load_memory(run_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("run_load_failed", extra={"run_id": run_id})
            await self._fail(run_id, f"Could not start the run: {exc}")
            return

        llm: LLMProvider | None = None
        try:
            if not settings.llm_configured:
                raise ConfigurationError(
                    f"{settings.active_api_key_variable} is not configured, so generation "
                    f"cannot run. Set it in backend/.env for the selected provider "
                    f"({settings.llm_provider})."
                )
            llm = self._llm_factory()

            await self._set_status(
                run_id, RunStatus.RUNNING, phase="analysis", started_at=started_at
            )
            await self._publish(
                run_id,
                EventType.RUN_STARTED,
                f"Starting generation for {memory.project_name}",
                payload={"project": memory.project_name},
            )

            plan = self._build_plan(memory)
            await self._persist_plan(run_id, plan)

            ctx = AgentContext(
                memory=memory,
                llm=llm,
                registry=self._adapters,
                report_progress=self._make_progress_reporter(run_id),
                report_log=self._make_log_reporter(run_id),
            )

            engine = WorkflowEngine(
                agent_registry=self._agents,
                llm=llm,
                on_step_started=self._make_step_started_hook(run_id, plan),
                on_step_finished=self._make_step_finished_hook(run_id, plan),
            )

            outcome = await engine.run(ctx, plan)

            await self._set_status(run_id, RunStatus.PACKAGING, phase="packaging")
            await self._publish(run_id, EventType.RUN_PHASE, "Packaging artifacts")

            package = None
            if len(memory.workspace) > 0:
                report = build_report(memory, outcome)
                memory.workspace.write(
                    "AI_ENGINEERING_REPORT.md",
                    render_report_markdown(report),
                    description="How this project was generated, and by whom.",
                    produced_by=AgentRole.ARTIFACT_MANAGER,
                )
                package = self._packager.write(
                    memory.workspace, run_id=run_id, project_slug=memory.project_slug
                )
                report = build_report(
                    memory,
                    outcome,
                    package_filename=package.filename,
                    package_size_bytes=package.size_bytes,
                )
            else:
                report = build_report(memory, outcome)

            await self._persist_artifacts(run_id, memory, report, package)

            duration = round(time.perf_counter() - started_perf, 3)
            final_status = RunStatus.FAILED if outcome.failed else RunStatus.COMPLETED

            await self._finalise(
                run_id,
                status=final_status,
                report=report,
                memory=memory,
                outcome_usage=outcome.total_usage.as_dict(),
                duration=duration,
                error=outcome.failure_reason if outcome.failed else None,
            )

            if outcome.failed:
                await self._publish(
                    run_id,
                    EventType.RUN_FAILED,
                    outcome.failure_reason,
                    level=LogLevel.ERROR,
                )
            else:
                await self._publish(
                    run_id,
                    EventType.RUN_COMPLETED,
                    f"Generation complete: {len(memory.workspace)} files in "
                    f"{report['timing']['duration_display']}",
                    payload={
                        "file_count": len(memory.workspace),
                        "duration_seconds": duration,
                        "package": package.filename if package else None,
                    },
                )

            logger.info(
                "run_finished",
                extra={
                    "run_id": run_id,
                    "status": final_status.value,
                    "files": len(memory.workspace),
                    "duration_seconds": duration,
                },
            )

        except asyncio.CancelledError:
            await self._set_status(run_id, RunStatus.CANCELLED, phase="cancelled")
            await self._publish(
                run_id, EventType.RUN_CANCELLED, "Run cancelled", level=LogLevel.WARNING
            )
            raise

        except Exception as exc:  # noqa: BLE001 - orchestrator must never crash
            logger.exception("run_failed", extra={"run_id": run_id})
            message = getattr(exc, "message", None) or f"{type(exc).__name__}: {exc}"
            await self._fail(run_id, message)

        finally:
            if llm is not None and hasattr(llm, "aclose"):
                await llm.aclose()
            await self._bus.close_topic(run_id)

    # --- setup helpers ---------------------------------------------------

    async def _load_memory(self, run_id: str) -> SharedProjectMemory:
        """Rebuild shared memory from the persisted run record."""
        async with session_scope() as session:
            run = await RunRepository(session).get_with_details(run_id)
            if run is None:
                raise NotFoundError(f"Run '{run_id}' does not exist.")

            project = run.project
            memory = SharedProjectMemory(
                run_id=run.id,
                project_id=project.id,
                project_name=project.name,
                project_slug=project.slug,
                idea=project.idea,
            )
            if run.analysis:
                memory.analysis = RequirementAnalysis.from_dict(run.analysis)
            if run.tech_stack:
                memory.tech_stack = TechStack.from_dict(run.tech_stack)
            return memory

    def _build_plan(self, memory: SharedProjectMemory) -> WorkflowPlan:
        """Plan the run, pre-marking skips already implied by the analysis."""
        plan = build_plan(self._agents)
        if memory.analysis.functional_requirements:
            # Analysis already exists (pre-analysed run), so skips are known up
            # front and the UI can show an accurate plan immediately.
            preflight_skips(plan, memory)
        return plan

    # --- reporters and hooks ---------------------------------------------

    def _make_progress_reporter(self, run_id: str):
        async def report(role: AgentRole, percent: int, message: str) -> None:
            await self._publish(
                run_id,
                EventType.AGENT_PROGRESS,
                message,
                agent_role=role.value,
                payload={"progress": percent},
                persist=False,
            )
            async with session_scope() as session:
                execution = await AgentExecutionRepository(session).get_for_run(run_id, role)
                if execution is not None:
                    execution.progress = percent

        return report

    def _make_log_reporter(self, run_id: str):
        async def report(
            role: AgentRole, level: LogLevel, message: str, payload: dict[str, Any]
        ) -> None:
            await self._publish(
                run_id,
                EventType.AGENT_LOG,
                message,
                level=level,
                agent_role=role.value,
                payload=payload,
                persist=level != LogLevel.DEBUG,
            )

        return report

    def _make_step_started_hook(self, run_id: str, plan: WorkflowPlan):
        async def hook(step: PlannedStep) -> None:
            async with session_scope() as session:
                repo = AgentExecutionRepository(session)
                execution = await repo.get_for_run(run_id, step.role)
                if execution is not None:
                    execution.status = AgentStatus.RUNNING
                    execution.started_at = datetime.now(UTC)
            await self._publish(
                run_id,
                EventType.AGENT_STARTED,
                f"{step.display_name} started",
                agent_role=step.role.value,
            )
            await self._update_run_progress(run_id, plan)

        return hook

    def _make_step_finished_hook(self, run_id: str, plan: WorkflowPlan):
        async def hook(step: PlannedStep, outcome: StepOutcome) -> None:
            async with session_scope() as session:
                repo = AgentExecutionRepository(session)
                execution = await repo.get_for_run(run_id, step.role)
                if execution is not None:
                    execution.status = outcome.status
                    execution.finished_at = datetime.now(UTC)
                    execution.duration_seconds = outcome.duration_seconds
                    execution.skip_reason = outcome.skip_reason or None
                    execution.error_message = outcome.error or None
                    execution.files_produced = outcome.files_produced
                    if outcome.status == AgentStatus.COMPLETED:
                        execution.progress = 100
                    if outcome.result is not None:
                        execution.summary = outcome.result.summary
                        execution.output = outcome.result.as_dict()["output"]
                        execution.confidence = outcome.result.confidence
                        execution.input_tokens = outcome.usage.input_tokens
                        execution.output_tokens = outcome.usage.output_tokens

            event_type = {
                AgentStatus.COMPLETED: EventType.AGENT_COMPLETED,
                AgentStatus.SKIPPED: EventType.AGENT_SKIPPED,
                AgentStatus.FAILED: EventType.AGENT_FAILED,
            }.get(outcome.status, EventType.AGENT_COMPLETED)

            message = (
                outcome.result.summary
                if outcome.result
                else outcome.skip_reason or outcome.error or "finished"
            )
            level = LogLevel.ERROR if outcome.status == AgentStatus.FAILED else LogLevel.INFO

            await self._publish(
                run_id,
                event_type,
                f"{step.display_name}: {message}",
                level=level,
                agent_role=step.role.value,
                payload={
                    "duration_seconds": outcome.duration_seconds,
                    "files_produced": outcome.files_produced,
                },
            )
            await self._update_run_progress(run_id, plan)

        return hook

    async def _update_run_progress(self, run_id: str, plan: WorkflowPlan) -> None:
        """Overall run progress: settled steps as a share of the total."""
        settled = sum(
            1
            for step in plan
            if step.status in {AgentStatus.COMPLETED, AgentStatus.SKIPPED, AgentStatus.FAILED}
        )
        percent = int(100 * settled / max(len(plan), 1))
        async with session_scope() as session:
            run = await RunRepository(session).get(run_id)
            if run is not None:
                run.progress = percent

    # --- persistence -----------------------------------------------------

    async def _persist_plan(self, run_id: str, plan: WorkflowPlan) -> None:
        """Write the plan and create an execution row per agent."""
        async with session_scope() as session:
            run_repo = RunRepository(session)
            exec_repo = AgentExecutionRepository(session)

            run = await run_repo.get(run_id)
            if run is not None:
                run.workflow_plan = plan.as_dict()

            existing = {e.role for e in await exec_repo.list_for_run(run_id)}
            for step in plan:
                if step.role in existing:
                    continue
                await exec_repo.add(
                    AgentExecution(
                        run_id=run_id,
                        role=step.role,
                        display_name=step.display_name,
                        sequence=step.sequence,
                        status=step.status,
                        skip_reason=step.skip_reason or None,
                    )
                )

    async def _persist_artifacts(
        self,
        run_id: str,
        memory: SharedProjectMemory,
        report: dict[str, Any],
        package: Any,
    ) -> None:
        """Record every deliverable as an addressable, versioned artifact."""
        async with session_scope() as session:
            repo = ArtifactRepository(session)

            async def store(
                kind: ArtifactKind,
                name: str,
                content: str | None,
                description: str,
                *,
                produced_by: AgentRole | None = None,
                content_type: str = "text/markdown",
                storage_path: str | None = None,
                size_bytes: int = 0,
                checksum: str | None = None,
                metadata: dict[str, Any] | None = None,
            ) -> None:
                if content is None and storage_path is None:
                    return
                await repo.add(
                    Artifact(
                        run_id=run_id,
                        kind=kind,
                        name=name,
                        description=description,
                        produced_by=produced_by,
                        version=await repo.next_version(run_id, name),
                        content=content,
                        content_type=content_type,
                        storage_path=storage_path,
                        size_bytes=size_bytes or (len(content.encode()) if content else 0),
                        checksum=checksum,
                        artifact_metadata=metadata,
                    )
                )

            analysis = memory.analysis
            if analysis.functional_requirements:
                await store(
                    ArtifactKind.REQUIREMENTS,
                    "Software Requirements Specification",
                    _render_srs(memory),
                    "Full SRS: scope, requirements, user stories and use cases.",
                    produced_by=AgentRole.BUSINESS_ANALYST,
                )

            if memory.architecture.style:
                await store(
                    ArtifactKind.ARCHITECTURE,
                    "Software Architecture",
                    _render_architecture(memory),
                    "Architecture, modules, layers and folder structure.",
                    produced_by=AgentRole.SOLUTION_ARCHITECT,
                )

            if memory.database.required and memory.database.schema_sql:
                await store(
                    ArtifactKind.DATABASE,
                    "SQL Schema",
                    memory.workspace.read("database/schema.sql"),
                    f"{len(memory.database.tables)} tables with constraints and indexes.",
                    produced_by=AgentRole.DATABASE_ENGINEER,
                    content_type="application/sql",
                )

            if memory.architecture.api_endpoints:
                await store(
                    ArtifactKind.API_SPEC,
                    "API Specification",
                    _render_api_spec(memory),
                    f"{len(memory.architecture.api_endpoints)} documented endpoints.",
                    produced_by=AgentRole.SOLUTION_ARCHITECT,
                )

            if readme := memory.workspace.read("README.md"):
                await store(
                    ArtifactKind.DOCUMENTATION,
                    "README",
                    readme,
                    "Project overview and quick start.",
                    produced_by=AgentRole.DOCUMENTATION_ENGINEER,
                )

            await store(
                ArtifactKind.REPORT,
                "AI Engineering Report",
                render_report_markdown(report),
                "How this project was generated, and by whom.",
                produced_by=AgentRole.ARTIFACT_MANAGER,
                metadata=report,
            )

            if package is not None:
                await store(
                    ArtifactKind.PACKAGE,
                    f"{memory.project_slug}.zip",
                    None,
                    f"Complete project: {package.file_count} files, {package.size_kb} KB.",
                    produced_by=AgentRole.ARTIFACT_MANAGER,
                    content_type="application/zip",
                    storage_path=str(package.path),
                    size_bytes=package.size_bytes,
                    checksum=package.checksum,
                    metadata={"file_count": package.file_count, "filename": package.filename},
                )

        await self._publish(
            run_id,
            EventType.ARTIFACT_CREATED,
            "Artifacts recorded and package ready for download",
        )

    async def _set_status(
        self,
        run_id: str,
        status: RunStatus,
        *,
        phase: str | None = None,
        started_at: datetime | None = None,
    ) -> None:
        async with session_scope() as session:
            run = await RunRepository(session).get(run_id)
            if run is None:
                return
            run.status = status
            if phase is not None:
                run.phase = phase
            if started_at is not None:
                run.started_at = started_at

    async def _finalise(
        self,
        run_id: str,
        *,
        status: RunStatus,
        report: dict[str, Any],
        memory: SharedProjectMemory,
        outcome_usage: dict[str, int],
        duration: float,
        error: str | None,
    ) -> None:
        async with session_scope() as session:
            run = await RunRepository(session).get(run_id)
            if run is None:
                return
            run.status = status
            run.phase = "complete" if status == RunStatus.COMPLETED else "failed"
            run.progress = 100
            run.finished_at = datetime.now(UTC)
            run.duration_seconds = duration
            run.report = report
            run.memory_snapshot = memory.snapshot()
            run.analysis = memory.analysis.as_dict()
            run.tech_stack = memory.tech_stack.as_dict()
            run.file_count = len(memory.workspace)
            run.input_tokens = outcome_usage.get("input_tokens", 0)
            run.output_tokens = outcome_usage.get("output_tokens", 0)
            run.cached_tokens = outcome_usage.get("cache_read_tokens", 0)
            run.error_message = error

            # Keep the project's denormalised copy current for dashboard reads.
            project = run.project
            if project is not None:
                project.analysis = run.analysis
                project.tech_stack = run.tech_stack
                if memory.analysis.executive_summary:
                    project.summary = memory.analysis.executive_summary
                if memory.project_name and memory.project_name != project.name:
                    project.name = memory.project_name

    async def _fail(self, run_id: str, message: str) -> None:
        async with session_scope() as session:
            run = await RunRepository(session).get(run_id)
            if run is not None:
                run.status = RunStatus.FAILED
                run.phase = "failed"
                run.error_message = message
                run.finished_at = datetime.now(UTC)
        await self._publish(run_id, EventType.RUN_FAILED, message, level=LogLevel.ERROR)

    # --- events ----------------------------------------------------------

    async def _publish(
        self,
        run_id: str,
        event_type: EventType,
        message: str,
        *,
        level: LogLevel = LogLevel.INFO,
        agent_role: str | None = None,
        payload: dict[str, Any] | None = None,
        persist: bool = True,
    ) -> None:
        """Broadcast an event and, unless suppressed, persist it.

        High-frequency progress ticks are broadcast but not persisted: they are
        only meaningful live, and writing every one would bloat the event log
        without making run history more useful.
        """
        sequence = self._sequence.get(run_id, 0) + 1
        self._sequence[run_id] = sequence

        event = RunEventMessage(
            run_id=run_id,
            event_type=event_type,
            message=message,
            sequence=sequence,
            level=level,
            agent_role=agent_role,
            payload=payload or {},
        )
        await self._bus.publish(event)

        if not persist:
            return

        try:
            async with session_scope() as session:
                await RunEventRepository(session).add(
                    RunEvent(
                        run_id=run_id,
                        sequence=sequence,
                        event_type=event_type,
                        level=level,
                        agent_role=agent_role,
                        message=message,
                        payload=payload or None,
                    )
                )
        except Exception:  # noqa: BLE001 - logging must never break a run
            logger.warning("event_persist_failed", extra={"run_id": run_id})


# --- artifact rendering ---------------------------------------------------


def _render_srs(memory: SharedProjectMemory) -> str:
    """Render the SRS as a standalone Markdown document."""
    a = memory.analysis
    lines = [
        f"# Software Requirements Specification — {memory.project_name}",
        "",
        "## 1. Executive summary",
        "",
        a.executive_summary or memory.idea,
        "",
        "## 2. Project overview",
        "",
        a.project_overview,
        "",
        "## 3. Scope",
        "",
        "### In scope",
        "",
    ]
    lines += [f"- {item}" for item in a.scope_in] or ["- Not specified"]
    lines += ["", "### Out of scope", ""]
    lines += [f"- {item}" for item in a.scope_out] or ["- Not specified"]

    if a.actors:
        lines += ["", "## 4. Actors", ""] + [f"- {actor}" for actor in a.actors]

    lines += [
        "",
        "## 5. Functional requirements",
        "",
        "| ID | Title | Priority | Module | Description |",
        "|----|-------|----------|--------|-------------|",
    ]
    for r in a.functional_requirements:
        description = str(r.get("description", "")).replace("|", "/")
        lines.append(
            f"| {r.get('id', '')} | {r.get('title', '')} | {r.get('priority', '')} "
            f"| {r.get('module', '')} | {description} |"
        )

    lines += [
        "",
        "## 6. Non-functional requirements",
        "",
        "| ID | Category | Requirement |",
        "|----|----------|-------------|",
    ]
    for r in a.non_functional_requirements:
        requirement = str(r.get("requirement", "")).replace("|", "/")
        lines.append(f"| {r.get('id', '')} | {r.get('category', '')} | {requirement} |")

    lines += ["", "## 7. User stories", ""]
    for story in a.user_stories:
        lines += [f"### {story.get('id', '')}", "", str(story.get("story", "")), ""]
        criteria = story.get("acceptance_criteria", [])
        if criteria:
            lines.append("**Acceptance criteria:**")
            lines += [f"- {c}" for c in criteria]
            lines.append("")

    lines += ["## 8. Use cases", ""]
    for case in a.use_cases:
        lines += [
            f"### {case.get('id', '')} — {case.get('name', '')}",
            "",
            f"**Actor:** {case.get('actor', '')}",
            "",
            "**Main flow:**",
        ]
        lines += [f"{i}. {step}" for i, step in enumerate(case.get("main_flow", []), 1)]
        if case.get("alternate_flow"):
            lines += ["", f"**Alternate flow:** {case['alternate_flow']}"]
        lines.append("")

    if a.assumptions:
        lines += ["## 9. Assumptions", ""] + [f"- {item}" for item in a.assumptions] + [""]
    if a.clarifications:
        lines += ["## 10. Open questions", ""] + [f"- {item}" for item in a.clarifications] + [""]

    return "\n".join(lines)


def _render_architecture(memory: SharedProjectMemory) -> str:
    """Render the architecture design as a standalone Markdown document."""
    arch = memory.architecture
    lines = [
        f"# Software Architecture — {memory.project_name}",
        "",
        "## Style",
        "",
        arch.style,
        "",
        "## Overview",
        "",
        arch.overview,
        "",
        "## Modules",
        "",
        "| Module | Responsibility | Entities | Depends on |",
        "|--------|----------------|----------|------------|",
    ]
    for module in arch.modules:
        lines.append(
            f"| {module.get('name', '')} | {module.get('responsibility', '')} "
            f"| {', '.join(module.get('entities', []))} "
            f"| {', '.join(module.get('depends_on', [])) or '—'} |"
        )

    if arch.layers:
        lines += ["", "## Layers", ""]
        for layer in arch.layers:
            lines += [f"### {layer.get('name', '')}", "", layer.get("responsibility", ""), ""]
            for rule in layer.get("rules", []):
                lines.append(f"- {rule}")
            lines.append("")

    if arch.folder_structure:
        lines += ["## Folder structure", "", "```", arch.folder_structure, "```", ""]

    if arch.cross_cutting:
        lines += ["## Cross-cutting concerns", ""] + [f"- {c}" for c in arch.cross_cutting] + [""]

    if arch.decisions:
        lines += ["## Architectural decisions", ""]
        for index, decision in enumerate(arch.decisions, 1):
            lines += [
                f"### ADR-{index:02d}: {decision.get('decision', '')}",
                "",
                decision.get("rationale", ""),
                "",
            ]

    return "\n".join(lines)


def _render_api_spec(memory: SharedProjectMemory) -> str:
    """Render the API contract as a standalone Markdown document."""
    lines = [
        f"# API Specification — {memory.project_name}",
        "",
        f"Base path: `/api/v1`  |  {len(memory.architecture.api_endpoints)} endpoints",
        "",
    ]
    by_module: dict[str, list[dict[str, Any]]] = {}
    for endpoint in memory.architecture.api_endpoints:
        by_module.setdefault(str(endpoint.get("module", "General")), []).append(endpoint)

    for module, endpoints in sorted(by_module.items()):
        lines += [f"## {module}", ""]
        for endpoint in endpoints:
            auth = " *(requires authentication)*" if endpoint.get("auth_required") else ""
            lines += [
                f"### `{endpoint.get('method')} {endpoint.get('path')}`{auth}",
                "",
                str(endpoint.get("summary", "")),
                "",
                f"- **Request:** {endpoint.get('request_body') or 'no body'}",
                f"- **Response:** {endpoint.get('response_body') or 'no body'}",
                f"- **Status codes:** "
                f"{', '.join(str(c) for c in endpoint.get('status_codes', []))}",
                "",
            ]
    return "\n".join(lines)


_orchestrator: RunOrchestrator | None = None


def get_orchestrator() -> RunOrchestrator:
    """Process-wide orchestrator singleton."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = RunOrchestrator()
    return _orchestrator
