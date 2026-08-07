"""Generation service.

Owns the pre-run path: requirement analysis, technology recommendation, stack
validation and run creation. Execution itself belongs to the orchestrator.

Analysis runs synchronously because the user waits on its result to review the
recommended stack. It is a single, bounded model call.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.registry import AdapterRegistry, get_registry
from app.agents.business_analyst import BusinessAnalystAgent
from app.agents.context import AgentContext
from app.agents.registry import get_agent_registry
from app.core.config import settings
from app.core.enums import AgentRole, LogLevel, RunStatus
from app.core.exceptions import ConfigurationError, NotFoundError, RateLimitError, ValidationError
from app.core.logging import get_logger
from app.llm.factory import build_llm_provider
from app.llm.protocol import LLMProvider
from app.models.project import Project
from app.models.run import GenerationRun
from app.models.user import User
from app.repositories.run_repository import RunRepository
from app.services.recommendation_service import RecommendationService, validate_stack
from app.workflow.engine import preflight_skips
from app.workflow.memory import RequirementAnalysis, SharedProjectMemory, TechStack
from app.workflow.planner import build_plan

logger = get_logger(__name__)


class GenerationService:
    """Analysis, recommendation and run creation."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        adapters: AdapterRegistry | None = None,
        llm_factory: Any = None,
    ) -> None:
        self._session = session
        self._runs = RunRepository(session)
        self._adapters = adapters or get_registry()
        self._recommender = RecommendationService(self._adapters)
        self._llm_factory = llm_factory or build_llm_provider

    # --- analysis --------------------------------------------------------

    async def analyse(self, project: Project) -> dict[str, Any]:
        """Analyse requirements and recommend a stack.

        Cached on the project: re-opening the review screen must not re-bill an
        analysis that has not changed.
        """
        if project.analysis:
            analysis = RequirementAnalysis.from_dict(project.analysis)
            logger.debug("analysis_cache_hit", extra={"project_id": project.id})
        else:
            analysis = await self._run_analysis(project)
            project.analysis = analysis.as_dict()
            await self._session.flush()

        recommendation = self._recommender.recommend(project.idea, analysis)
        project.tech_stack = recommendation.stack.as_dict()
        if analysis.executive_summary and not project.summary:
            project.summary = analysis.executive_summary
        await self._session.flush()

        return {
            "project_id": project.id,
            "analysis": analysis.as_dict(),
            "recommended_stack": recommendation.stack.as_dict(),
            "options": {
                kind: [option.as_dict() for option in options]
                for kind, options in recommendation.options.items()
            },
            "workflow_preview": self._workflow_preview(analysis),
        }

    async def _run_analysis(self, project: Project) -> RequirementAnalysis:
        """Execute the Business Analyst agent for its capability decisions."""
        if not settings.llm_configured:
            raise ConfigurationError(
                f"{settings.active_api_key_variable} is not configured, so requirements "
                f"cannot be analysed. Set it in backend/.env for the selected provider "
                f"({settings.llm_provider})."
            )

        memory = SharedProjectMemory(
            run_id="analysis",
            project_id=project.id,
            project_name=project.name,
            project_slug=project.slug,
            idea=project.idea,
        )

        # The provider manager is process-wide and is closed at application
        # shutdown. Closing it here would tear down the transports, cooldowns
        # and cache that every other run depends on.
        llm: LLMProvider = self._llm_factory()
        ctx = AgentContext(
            memory=memory,
            llm=llm,
            registry=self._adapters,
            report_progress=_noop_progress,
            report_log=_noop_log,
        )
        await BusinessAnalystAgent().execute(ctx)

        logger.info(
            "analysis_complete",
            extra={
                "project_id": project.id,
                "requirements": len(memory.analysis.functional_requirements),
                "needs_database": memory.analysis.needs_database,
                "needs_backend": memory.analysis.needs_backend,
            },
        )
        return memory.analysis

    def _workflow_preview(self, analysis: RequirementAnalysis) -> list[dict[str, Any]]:
        """The plan the user will see before committing to a run."""
        memory = SharedProjectMemory(
            run_id="preview", project_id="", project_name="", project_slug="", idea=""
        )
        memory.analysis = analysis
        plan = build_plan(get_agent_registry())
        preflight_skips(plan, memory)
        return plan.as_dict()

    # --- run creation ----------------------------------------------------

    async def create_run(
        self,
        project: Project,
        owner: User,
        *,
        stack_override: dict[str, str | None] | None = None,
        active_runs: int = 0,
    ) -> GenerationRun:
        """Queue a run with a validated stack."""
        if active_runs >= settings.max_concurrent_runs:
            raise RateLimitError(
                f"{active_runs} runs are already in flight (limit "
                f"{settings.max_concurrent_runs}). Wait for one to finish."
            )

        if not project.analysis:
            raise ValidationError(
                "Analyse the project before starting generation."
            )

        analysis = RequirementAnalysis.from_dict(project.analysis)
        stack = self._resolve_stack(project, analysis, stack_override)

        problems = validate_stack(self._adapters, stack, analysis)
        if problems:
            raise ValidationError(
                "The selected technology stack is not valid.",
                details={"problems": problems},
            )

        run = await self._runs.add(
            GenerationRun(
                project_id=project.id,
                status=RunStatus.PENDING,
                phase="queued",
                progress=0,
                analysis=analysis.as_dict(),
                tech_stack=stack.as_dict(),
            )
        )
        project.tech_stack = stack.as_dict()
        await self._session.flush()

        logger.info(
            "run_queued",
            extra={"run_id": run.id, "project_id": project.id, "owner_id": owner.id},
        )
        return run

    def _resolve_stack(
        self,
        project: Project,
        analysis: RequirementAnalysis,
        override: dict[str, str | None] | None,
    ) -> TechStack:
        """Merge any user override onto the recommendation."""
        recommended = self._recommender.recommend(project.idea, analysis).stack

        if not override:
            return recommended

        stack = TechStack(
            frontend=override.get("frontend") or recommended.frontend,
            backend=override.get("backend") or recommended.backend,
            database=override.get("database") or recommended.database,
            authentication=override.get("authentication") or recommended.authentication,
            rationale=recommended.rationale,
            user_customised=True,
        )

        # Never carry a technology the analysis says is unnecessary.
        if not analysis.needs_frontend:
            stack.frontend = None
        if not analysis.needs_backend:
            stack.backend = None
        if not analysis.needs_database:
            stack.database = None
        if not analysis.needs_authentication:
            stack.authentication = None

        return stack

    async def get_owned_run(self, run_id: str, owner: User) -> GenerationRun:
        run = await self._runs.get_owned(run_id, owner.id)
        if run is None:
            raise NotFoundError("Run not found.")
        return run


async def _noop_progress(role: AgentRole, percent: int, message: str) -> None:
    """Analysis runs outside a run context, so progress has nowhere to go."""
    return None


async def _noop_log(
    role: AgentRole, level: LogLevel, message: str, payload: dict[str, Any]
) -> None:
    return None
