"""Workflow planning.

Builds an execution plan from the agent registry, resolving `depends_on` into a
topological order. Planning is deterministic and re-runnable: after the Business
Analyst reports its capability decisions, the engine re-plans so agents that are
no longer relevant are marked skipped before they ever start.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.agents.base import Agent
from app.agents.registry import AgentRegistry
from app.core.enums import AgentRole, AgentStatus
from app.core.exceptions import WorkflowError


@dataclass(slots=True)
class PlannedStep:
    """One agent's slot in the execution plan."""

    role: AgentRole
    display_name: str
    sequence: int
    status: AgentStatus = AgentStatus.WAITING
    skip_reason: str = ""
    depends_on: tuple[AgentRole, ...] = ()
    requires: tuple[AgentRole, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "role": self.role.value,
            "display_name": self.display_name,
            "sequence": self.sequence,
            "status": self.status.value,
            "skip_reason": self.skip_reason,
            "depends_on": [r.value for r in self.depends_on],
        }


@dataclass(slots=True)
class WorkflowPlan:
    """The ordered set of steps for one run."""

    steps: list[PlannedStep] = field(default_factory=list)

    def __iter__(self):
        return iter(self.steps)

    def __len__(self) -> int:
        return len(self.steps)

    @property
    def active_steps(self) -> list[PlannedStep]:
        return [step for step in self.steps if step.status != AgentStatus.SKIPPED]

    def step_for(self, role: AgentRole) -> PlannedStep | None:
        return next((s for s in self.steps if s.role == role), None)

    def mark_skipped(self, role: AgentRole, reason: str) -> None:
        step = self.step_for(role)
        if step is not None:
            step.status = AgentStatus.SKIPPED
            step.skip_reason = reason

    def as_dict(self) -> list[dict[str, Any]]:
        return [step.as_dict() for step in self.steps]

    def summary(self) -> str:
        return " -> ".join(
            step.display_name for step in self.steps if step.status != AgentStatus.SKIPPED
        )


def build_plan(registry: AgentRegistry) -> WorkflowPlan:
    """Order every agent so each runs after the agents it depends on.

    Ties are broken by the registry's canonical order, which keeps plans stable
    and readable rather than merely valid.
    """
    agents = registry.all()
    priority = {agent.role: index for index, agent in enumerate(agents)}
    by_role: dict[AgentRole, Agent] = {agent.role: agent for agent in agents}

    # Dependencies on unregistered roles are ignored rather than fatal, so a
    # trimmed registry (used in tests) still produces a usable plan.
    pending = {
        agent.role: {dep for dep in agent.depends_on if dep in by_role} for agent in agents
    }

    ordered: list[AgentRole] = []
    resolved: set[AgentRole] = set()

    while pending:
        ready = sorted(
            (role for role, deps in pending.items() if deps <= resolved),
            key=lambda role: priority[role],
        )
        if not ready:
            cycle = ", ".join(sorted(role.value for role in pending))
            raise WorkflowError(
                f"Agent dependencies contain a cycle involving: {cycle}",
                details={"unresolved": sorted(r.value for r in pending)},
            )
        for role in ready:
            ordered.append(role)
            resolved.add(role)
            pending.pop(role)

    return WorkflowPlan(
        steps=[
            PlannedStep(
                role=role,
                display_name=by_role[role].display_name,
                sequence=index,
                depends_on=by_role[role].depends_on,
                requires=by_role[role].requires,
            )
            for index, role in enumerate(ordered)
        ]
    )
