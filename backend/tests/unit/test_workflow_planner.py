"""Workflow planning: topological ordering and dynamic skip decisions."""

from __future__ import annotations

import pytest

from app.agents.registry import AgentRegistry
from app.core.enums import AgentRole, AgentStatus
from app.core.exceptions import WorkflowError
from app.workflow.engine import preflight_skips
from app.workflow.memory import RequirementAnalysis, SharedProjectMemory
from app.workflow.planner import build_plan


class TestTopologicalOrdering:
    def test_every_agent_appears_exactly_once(self, agent_registry: AgentRegistry) -> None:
        plan = build_plan(agent_registry)
        roles = [step.role for step in plan]

        assert len(roles) == len(agent_registry)
        assert len(set(roles)) == len(roles)

    def test_dependencies_precede_dependants(self, agent_registry: AgentRegistry) -> None:
        """The core guarantee: no agent runs before its inputs exist."""
        plan = build_plan(agent_registry)
        position = {step.role: step.sequence for step in plan}

        for step in plan:
            for dependency in step.depends_on:
                assert position[dependency] < position[step.role], (
                    f"{step.role.value} runs before its dependency {dependency.value}"
                )

    def test_documentation_runs_after_improvement(self, agent_registry: AgentRegistry) -> None:
        """Docs must describe the final code, not the pre-refactor version."""
        plan = build_plan(agent_registry)
        position = {step.role: step.sequence for step in plan}

        assert position[AgentRole.DOCUMENTATION_ENGINEER] > position[AgentRole.IMPROVEMENT_ENGINEER]
        assert position[AgentRole.ARTIFACT_MANAGER] == len(plan) - 1

    def test_cycle_is_reported_not_silently_dropped(self) -> None:
        from app.agents.base import Agent
        from app.agents.context import AgentContext
        from app.agents.results import AgentResult

        class AgentA(Agent):
            role = AgentRole.BACKEND_ENGINEER
            display_name = "A"
            depends_on = (AgentRole.FRONTEND_ENGINEER,)

            def system_prompt(self, ctx: AgentContext) -> str:
                return ""

            async def execute(self, ctx: AgentContext) -> AgentResult:
                raise NotImplementedError

        class AgentB(Agent):
            role = AgentRole.FRONTEND_ENGINEER
            display_name = "B"
            depends_on = (AgentRole.BACKEND_ENGINEER,)

            def system_prompt(self, ctx: AgentContext) -> str:
                return ""

            async def execute(self, ctx: AgentContext) -> AgentResult:
                raise NotImplementedError

        registry = AgentRegistry((AgentA, AgentB))
        with pytest.raises(WorkflowError, match="cycle"):
            build_plan(registry)


class TestDynamicSkips:
    @staticmethod
    def _memory(**capabilities: bool) -> SharedProjectMemory:
        memory = SharedProjectMemory(
            run_id="r", project_id="p", project_name="P", project_slug="p", idea="idea"
        )
        memory.analysis = RequirementAnalysis(**capabilities)
        return memory

    def test_full_stack_project_engages_everyone(self, agent_registry: AgentRegistry) -> None:
        plan = build_plan(agent_registry)
        preflight_skips(
            plan,
            self._memory(
                needs_authentication=True,
                needs_database=True,
                needs_api=True,
                needs_backend=True,
                needs_frontend=True,
            ),
        )

        assert len(plan.active_steps) == len(plan)

    def test_static_site_skips_database_and_backend(self, agent_registry: AgentRegistry) -> None:
        """The headline behaviour: a portfolio site gets no database engineer."""
        plan = build_plan(agent_registry)
        skipped = preflight_skips(
            plan,
            self._memory(
                needs_authentication=False,
                needs_database=False,
                needs_api=False,
                needs_backend=False,
                needs_frontend=True,
            ),
        )

        assert AgentRole.DATABASE_ENGINEER.value in skipped
        assert AgentRole.BACKEND_ENGINEER.value in skipped
        assert len(plan.active_steps) == len(plan) - 2

        database_step = plan.step_for(AgentRole.DATABASE_ENGINEER)
        assert database_step is not None
        assert database_step.status == AgentStatus.SKIPPED
        assert "no database" in database_step.skip_reason.lower()

    def test_skip_reasons_explain_the_decision(self, agent_registry: AgentRegistry) -> None:
        plan = build_plan(agent_registry)
        skipped = preflight_skips(
            plan,
            self._memory(
                needs_database=False, needs_backend=False, needs_frontend=True
            ),
        )

        for reason in skipped.values():
            assert len(reason) > 20, "A skip reason must explain itself to the user"
            assert reason.endswith('.')

    def test_headless_project_skips_frontend(self, agent_registry: AgentRegistry) -> None:
        plan = build_plan(agent_registry)
        skipped = preflight_skips(
            plan,
            self._memory(
                needs_database=True, needs_api=True, needs_backend=True, needs_frontend=False
            ),
        )

        assert AgentRole.FRONTEND_ENGINEER.value in skipped
        assert AgentRole.BACKEND_ENGINEER.value not in skipped


class TestDependencySemantics:
    """`requires` (hard) must be a subset of `depends_on` (ordering)."""

    def test_requires_is_always_a_subset_of_depends_on(
        self, agent_registry: AgentRegistry
    ) -> None:
        for agent in agent_registry.all():
            assert set(agent.requires) <= set(agent.depends_on), (
                f"{agent.role.value} declares a hard requirement it does not order after"
            )

    def test_packaging_and_documentation_have_no_hard_requirements(
        self, agent_registry: AgentRegistry
    ) -> None:
        """These must always get the chance to run, so partial work is never lost."""
        assert agent_registry.get(AgentRole.ARTIFACT_MANAGER).requires == ()
        assert agent_registry.get(AgentRole.DOCUMENTATION_ENGINEER).requires == ()
        assert agent_registry.get(AgentRole.QA_ENGINEER).requires == ()
        assert agent_registry.get(AgentRole.REVIEW_ENGINEER).requires == ()

    def test_design_agents_require_their_inputs(
        self, agent_registry: AgentRegistry
    ) -> None:
        architect = agent_registry.get(AgentRole.SOLUTION_ARCHITECT)
        assert AgentRole.BUSINESS_ANALYST in architect.requires

        backend = agent_registry.get(AgentRole.BACKEND_ENGINEER)
        assert AgentRole.SOLUTION_ARCHITECT in backend.requires
        # The schema is ordering-only, not a hard requirement.
        assert AgentRole.DATABASE_ENGINEER not in backend.requires
