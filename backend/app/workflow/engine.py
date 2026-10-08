"""Workflow engine.

Owns execution: selects the next agent, enforces dependency order, evaluates
skip decisions, validates outputs and aggregates cost. It is deliberately
deterministic — the intelligence lives in the agents, the guarantees live here.

Skip decisions are re-evaluated immediately before each agent runs, not once up
front. That is what makes the workflow dynamic: the Business Analyst's
capability decisions land in shared memory mid-run and silence the agents that
are no longer relevant.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from app.agents.base import Agent
from app.agents.context import AgentContext
from app.agents.registry import AgentRegistry
from app.agents.results import AgentResult
from app.core.enums import AgentRole, AgentStatus, LogLevel
from app.core.exceptions import AgentExecutionError, LLMError
from app.core.logging import get_logger
from app.llm.protocol import LLMProvider
from app.llm.types import TokenUsage
from app.workflow.memory import SharedProjectMemory
from app.workflow.planner import PlannedStep, WorkflowPlan, build_plan

logger = get_logger(__name__)

#: Agents whose failure aborts the run. Everything else degrades: a run that
#: produced working code but no tests is still worth delivering.
CRITICAL_ROLES: frozenset[AgentRole] = frozenset(
    {AgentRole.BUSINESS_ANALYST, AgentRole.SOLUTION_ARCHITECT, AgentRole.ARTIFACT_MANAGER}
)

StepStartedHook = Callable[[PlannedStep], Awaitable[None]]
StepFinishedHook = Callable[[PlannedStep, "StepOutcome"], Awaitable[None]]


@dataclass(slots=True)
class StepOutcome:
    """The result of attempting one step."""

    role: AgentRole
    status: AgentStatus
    result: AgentResult | None = None
    skip_reason: str = ""
    error: str = ""
    duration_seconds: float = 0.0

    @property
    def usage(self) -> TokenUsage:
        return self.result.usage if self.result else TokenUsage()

    @property
    def files_produced(self) -> int:
        return self.result.files_produced if self.result else 0


@dataclass(slots=True)
class WorkflowOutcome:
    """The aggregate result of a whole run."""

    plan: WorkflowPlan
    outcomes: list[StepOutcome] = field(default_factory=list)
    total_usage: TokenUsage = field(default_factory=TokenUsage)
    duration_seconds: float = 0.0
    failed: bool = False
    failure_reason: str = ""

    @property
    def executed(self) -> list[StepOutcome]:
        return [o for o in self.outcomes if o.status == AgentStatus.COMPLETED]

    @property
    def skipped(self) -> list[StepOutcome]:
        return [o for o in self.outcomes if o.status == AgentStatus.SKIPPED]

    @property
    def failures(self) -> list[StepOutcome]:
        return [o for o in self.outcomes if o.status == AgentStatus.FAILED]

    @property
    def total_files(self) -> int:
        return sum(o.files_produced for o in self.outcomes)


class WorkflowEngine:
    """Executes the multi-agent workflow for a single run."""

    def __init__(
        self,
        *,
        agent_registry: AgentRegistry,
        llm: LLMProvider,
        on_step_started: StepStartedHook | None = None,
        on_step_finished: StepFinishedHook | None = None,
    ) -> None:
        self._agents = agent_registry
        self._llm = llm
        self._on_started = on_step_started
        self._on_finished = on_step_finished

    def plan(self) -> WorkflowPlan:
        """Build the initial execution plan."""
        return build_plan(self._agents)

    async def run(self, ctx: AgentContext, plan: WorkflowPlan | None = None) -> WorkflowOutcome:
        """Execute every eligible agent in dependency order."""
        plan = plan or self.plan()
        outcome = WorkflowOutcome(plan=plan)
        started = time.perf_counter()

        for step in plan:
            if step.status == AgentStatus.SKIPPED:
                outcome.outcomes.append(
                    StepOutcome(
                        role=step.role,
                        status=AgentStatus.SKIPPED,
                        skip_reason=step.skip_reason,
                    )
                )
                continue

            agent = self._agents.get(step.role)

            # Re-evaluate now: memory has changed since the plan was built.
            decision = agent.should_execute(ctx)
            if decision.skipped:
                step.status = AgentStatus.SKIPPED
                step.skip_reason = decision.reason
                ctx.memory.record_agent_status(step.role, AgentStatus.SKIPPED)
                step_outcome = StepOutcome(
                    role=step.role,
                    status=AgentStatus.SKIPPED,
                    skip_reason=decision.reason,
                )
                outcome.outcomes.append(step_outcome)
                await self._notify_finished(step, step_outcome)
                logger.info(
                    "agent_skipped",
                    extra={"agent": step.role.value, "reason": decision.reason},
                )
                continue

            # A dependency that failed leaves this agent without its input.
            blocker = self._blocked_by(step, outcome)
            if blocker is not None:
                reason = f"Blocked because {blocker} did not complete."
                step.status = AgentStatus.BLOCKED
                step.skip_reason = reason
                ctx.memory.record_agent_status(step.role, AgentStatus.BLOCKED)
                step_outcome = StepOutcome(
                    role=step.role, status=AgentStatus.BLOCKED, skip_reason=reason
                )
                outcome.outcomes.append(step_outcome)
                await self._notify_finished(step, step_outcome)
                continue

            step_outcome = await self._execute_step(agent, step, ctx)
            outcome.outcomes.append(step_outcome)
            outcome.total_usage = outcome.total_usage + step_outcome.usage

            if step_outcome.status == AgentStatus.FAILED:
                if step.role in CRITICAL_ROLES:
                    outcome.failed = True
                    outcome.failure_reason = (
                        f"{agent.display_name} failed and is required: {step_outcome.error}"
                    )
                    break
                elif (
                    (step.role == AgentRole.FRONTEND_ENGINEER and ctx.memory.needs_frontend)
                    or (step.role == AgentRole.BACKEND_ENGINEER and ctx.memory.needs_backend)
                    or (step.role == AgentRole.DATABASE_ENGINEER and ctx.memory.needs_database)
                ):
                    outcome.failed = True
                    if not outcome.failure_reason:
                        outcome.failure_reason = (
                            f"{agent.display_name} failed: {step_outcome.error}"
                        )

        outcome.duration_seconds = round(time.perf_counter() - started, 3)
        return outcome

    async def _execute_step(
        self, agent: Agent, step: PlannedStep, ctx: AgentContext
    ) -> StepOutcome:
        """Run one agent, converting any failure into a recorded outcome."""
        step.status = AgentStatus.RUNNING
        await self._notify_started(step)
        started = time.perf_counter()

        logger.info("agent_started", extra={"agent": step.role.value, "run_id": ctx.memory.run_id})

        try:
            result = await agent.execute(ctx)
            duration = round(time.perf_counter() - started, 3)

            self._validate_result(agent, result)

            step.status = AgentStatus.COMPLETED
            ctx.memory.record_agent_status(step.role, AgentStatus.COMPLETED)
            step_outcome = StepOutcome(
                role=step.role,
                status=AgentStatus.COMPLETED,
                result=result,
                duration_seconds=duration,
            )
            logger.info(
                "agent_completed",
                extra={
                    "agent": step.role.value,
                    "duration_seconds": duration,
                    "files": result.files_produced,
                    "output_tokens": result.usage.output_tokens,
                },
            )

        except (AgentExecutionError, LLMError) as exc:
            duration = round(time.perf_counter() - started, 3)
            step.status = AgentStatus.FAILED
            ctx.memory.record_agent_status(step.role, AgentStatus.FAILED, error=exc.message)
            step_outcome = StepOutcome(
                role=step.role,
                status=AgentStatus.FAILED,
                error=exc.message,
                duration_seconds=duration,
            )
            logger.error(
                "agent_failed",
                extra={"agent": step.role.value, "error": exc.message},
            )
            await ctx.log(step.role, f"Failed: {exc.message}", level=LogLevel.ERROR)

        except Exception as exc:  # noqa: BLE001 - one agent must not kill the run
            duration = round(time.perf_counter() - started, 3)
            step.status = AgentStatus.FAILED
            message = f"{type(exc).__name__}: {exc}"
            ctx.memory.record_agent_status(step.role, AgentStatus.FAILED, error=message)
            step_outcome = StepOutcome(
                role=step.role,
                status=AgentStatus.FAILED,
                error=message,
                duration_seconds=duration,
            )
            logger.exception("agent_crashed", extra={"agent": step.role.value})
            await ctx.log(step.role, f"Unexpected failure: {message}", level=LogLevel.ERROR)

        await self._notify_finished(step, step_outcome)
        return step_outcome

    @staticmethod
    def _validate_result(agent: Agent, result: AgentResult) -> None:
        """Reject a result that would corrupt downstream state."""
        if result.role != agent.role:
            raise AgentExecutionError(
                f"Result role '{result.role.value}' does not match the executing "
                f"agent '{agent.role.value}'.",
                agent=agent.role.value,
            )
        if not result.summary.strip():
            raise AgentExecutionError("Agent returned an empty summary.", agent=agent.role.value)

    @staticmethod
    def _blocked_by(step: PlannedStep, outcome: WorkflowOutcome) -> str | None:
        """Name of a failed hard requirement, if any.

        Only `requires` blocks — a failed *ordering* dependency does not. The
        Documentation Engineer can still write docs when the QA Engineer fails,
        and the Artifact Manager must always get the chance to package whatever
        was produced. Skipped dependencies never block.
        """
        failed = {o.role for o in outcome.outcomes if o.status == AgentStatus.FAILED}
        for requirement in step.requires:
            if requirement in failed:
                return requirement.value.replace("_", " ")
        return None

    async def _notify_started(self, step: PlannedStep) -> None:
        if self._on_started is not None:
            await self._on_started(step)

    async def _notify_finished(self, step: PlannedStep, outcome: StepOutcome) -> None:
        if self._on_finished is not None:
            await self._on_finished(step, outcome)


def preflight_skips(plan: WorkflowPlan, memory: SharedProjectMemory) -> dict[str, str]:
    """Mark agents that memory already rules out, before execution starts.

    Used to show an accurate plan in the UI the moment a run is queued, rather
    than revealing skips one at a time as execution reaches them.
    """
    decisions: dict[str, str] = {}

    if not memory.needs_database:
        reason = "No persistent data, so no database is required."
        plan.mark_skipped(AgentRole.DATABASE_ENGINEER, reason)
        decisions[AgentRole.DATABASE_ENGINEER.value] = reason

    if not memory.needs_backend:
        reason = "Client-only project, so no server-side application is required."
        plan.mark_skipped(AgentRole.BACKEND_ENGINEER, reason)
        decisions[AgentRole.BACKEND_ENGINEER.value] = reason

    if not memory.needs_frontend:
        reason = "No user interface, so no frontend is required."
        plan.mark_skipped(AgentRole.FRONTEND_ENGINEER, reason)
        decisions[AgentRole.FRONTEND_ENGINEER.value] = reason

    return decisions


__all__ = [
    "CRITICAL_ROLES",
    "StepOutcome",
    "WorkflowEngine",
    "WorkflowOutcome",
    "preflight_skips",
]
