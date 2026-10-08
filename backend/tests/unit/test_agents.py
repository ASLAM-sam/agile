"""Agent behaviour: capability reconciliation, skip decisions and packaging."""

from __future__ import annotations

from typing import Any

from app.agents.artifact_manager import ArtifactManagerAgent
from app.agents.backend_engineer import BackendEngineerAgent
from app.agents.business_analyst import BusinessAnalystAgent
from app.agents.context import AgentContext
from app.agents.database_engineer import DatabaseEngineerAgent
from app.agents.frontend_engineer import FrontendEngineerAgent
from app.agents.qa_engineer import QAEngineerAgent
from app.agents.review_engineer import ReviewEngineerAgent
from app.core.enums import AgentRole, LogLevel
from app.workflow.memory import (
    ArchitectureDesign,
    RequirementAnalysis,
    ReviewFindings,
    SharedProjectMemory,
    TechStack,
)


def make_context(memory: SharedProjectMemory, llm: Any, adapters: Any) -> AgentContext:
    async def progress(role: AgentRole, percent: int, message: str) -> None:
        return None

    async def log(
        role: AgentRole, level: LogLevel, message: str, payload: dict[str, Any]
    ) -> None:
        return None

    return AgentContext(
        memory=memory,
        llm=llm,
        registry=adapters,
        report_progress=progress,
        report_log=log,
    )


class TestBusinessAnalyst:
    async def test_records_the_analysis_in_shared_memory(
        self, memory, stub_llm, adapters, full_analysis_payload
    ) -> None:
        stub_llm.queue(full_analysis_payload)
        ctx = make_context(memory, stub_llm, adapters)

        result = await BusinessAnalystAgent().execute(ctx)

        assert result.role is AgentRole.BUSINESS_ANALYST
        assert memory.analysis.needs_database is True
        assert memory.analysis.needs_backend is True
        assert len(memory.analysis.functional_requirements) == 9
        assert memory.confidence["requirements"] > 0.8

    async def test_detects_a_static_site(
        self, memory, stub_llm, adapters, static_site_analysis_payload
    ) -> None:
        stub_llm.queue(static_site_analysis_payload)
        ctx = make_context(memory, stub_llm, adapters)

        await BusinessAnalystAgent().execute(ctx)

        assert memory.needs_database is False
        assert memory.needs_backend is False
        assert memory.needs_frontend is True

    async def test_reconciles_contradictory_capabilities(
        self, memory, stub_llm, adapters, full_analysis_payload
    ) -> None:
        """A database implies a backend; the contradiction must not propagate."""
        payload = dict(full_analysis_payload)
        payload["capabilities"] = {
            "needs_authentication": False,
            "needs_database": True,
            "needs_api": False,
            "needs_backend": False,  # contradicts needs_database
            "needs_frontend": True,
        }
        stub_llm.queue(payload)
        ctx = make_context(memory, stub_llm, adapters)

        await BusinessAnalystAgent().execute(ctx)

        assert memory.analysis.needs_backend is True
        assert memory.analysis.needs_api is True
        assert any("reconciled" in note.lower() for note in memory.notes)


class TestSkipDecisions:
    def _ctx(self, memory, stub_llm, adapters) -> AgentContext:
        return make_context(memory, stub_llm, adapters)

    def test_database_engineer_skips_without_persistence(
        self, memory, stub_llm, adapters
    ) -> None:
        memory.analysis = RequirementAnalysis(needs_database=False)
        decision = DatabaseEngineerAgent().should_execute(self._ctx(memory, stub_llm, adapters))

        assert decision.skipped is True
        assert "no database" in decision.reason.lower()

    def test_database_engineer_runs_with_persistence(
        self, memory, stub_llm, adapters
    ) -> None:
        memory.analysis = RequirementAnalysis(needs_database=True)
        memory.tech_stack = TechStack(database="sqlite")

        assert not DatabaseEngineerAgent().should_execute(
            self._ctx(memory, stub_llm, adapters)
        ).skipped

    def test_backend_engineer_skips_for_client_only_projects(
        self, memory, stub_llm, adapters
    ) -> None:
        memory.analysis = RequirementAnalysis(needs_backend=False)
        decision = BackendEngineerAgent().should_execute(self._ctx(memory, stub_llm, adapters))

        assert decision.skipped is True

    def test_frontend_engineer_skips_for_headless_projects(
        self, memory, stub_llm, adapters
    ) -> None:
        memory.analysis = RequirementAnalysis(needs_frontend=False)
        decision = FrontendEngineerAgent().should_execute(self._ctx(memory, stub_llm, adapters))

        assert decision.skipped is True

    def test_qa_skips_when_nothing_was_generated(self, memory, stub_llm, adapters) -> None:
        decision = QAEngineerAgent().should_execute(self._ctx(memory, stub_llm, adapters))
        assert decision.skipped is True

    def test_review_skips_below_the_source_threshold(
        self, memory, stub_llm, adapters
    ) -> None:
        memory.workspace.write("a.py", "print(1)")
        decision = ReviewEngineerAgent().should_execute(self._ctx(memory, stub_llm, adapters))

        assert decision.skipped is True


class TestQAStructuralValidation:
    def test_flags_endpoints_with_no_implementation(
        self, memory, stub_llm, adapters
    ) -> None:
        memory.analysis = RequirementAnalysis(
            needs_backend=True, needs_frontend=False, needs_api=True
        )
        memory.architecture = ArchitectureDesign(
            api_endpoints=[
                {"method": "GET", "path": "/api/v1/patients", "summary": "List"},
                {"method": "POST", "path": "/api/v1/invoices", "summary": "Create"},
            ]
        )
        memory.workspace.write("backend/app/routes.py", "@router.get('/patients')")

        findings = QAEngineerAgent()._validate_structure(  # noqa: SLF001 - unit under test
            make_context(memory, stub_llm, adapters)
        )

        assert any("invoices" in finding for finding in findings)

    def test_flags_placeholder_implementations(self, memory, stub_llm, adapters) -> None:
        memory.workspace.write(
            "backend/app/service.py", "def create():\n    # TODO: implement\n    pass\n"
        )

        findings = QAEngineerAgent()._validate_structure(  # noqa: SLF001
            make_context(memory, stub_llm, adapters)
        )

        assert any("TODO" in finding for finding in findings)

    def test_flags_a_manifest_with_no_source(self, memory, stub_llm, adapters) -> None:
        memory.workspace.write("frontend/package.json", '{"name": "web"}')

        findings = QAEngineerAgent()._validate_structure(  # noqa: SLF001
            make_context(memory, stub_llm, adapters)
        )

        assert any("frontend/src" in finding for finding in findings)

    def test_clean_project_produces_no_findings(self, memory, stub_llm, adapters) -> None:
        memory.analysis = RequirementAnalysis(needs_backend=False, needs_frontend=True)
        memory.workspace.write("frontend/package.json", '{"name": "web"}')
        memory.workspace.write("frontend/src/App.tsx", "export function App() { return null; }")

        findings = QAEngineerAgent()._validate_structure(  # noqa: SLF001
            make_context(memory, stub_llm, adapters)
        )

        assert findings == []


class TestArtifactManager:
    async def test_emits_integration_files_and_manifest(
        self, memory, stub_llm, adapters
    ) -> None:
        memory.analysis = RequirementAnalysis(
            needs_database=True, needs_api=True, needs_backend=True, needs_frontend=True
        )
        memory.tech_stack = TechStack(
            frontend="react", backend="fastapi", database="sqlite"
        )
        memory.workspace.write("README.md", "# Project")
        memory.workspace.write("backend/app/main.py", "app = FastAPI()")
        memory.workspace.write("frontend/src/App.tsx", "export const App = () => null;")
        memory.workspace.write("database/schema.sql", "CREATE TABLE patients (id BIGSERIAL);")

        result = await ArtifactManagerAgent().execute(make_context(memory, stub_llm, adapters))

        assert memory.workspace.exists("docker-compose.yml")
        assert memory.workspace.exists(".gitignore")
        assert memory.workspace.exists(".editorconfig")
        assert memory.workspace.exists("aegis-manifest.json")
        assert result.warnings == []

        compose = memory.workspace.read("docker-compose.yml") or ""
        assert "services:" in compose
        assert "db:" not in compose and "api:" in compose and "web:" in compose

    async def test_warns_about_a_missing_readme(self, memory, stub_llm, adapters) -> None:
        memory.analysis = RequirementAnalysis(needs_backend=False, needs_frontend=True)
        memory.tech_stack = TechStack(frontend="react")
        memory.workspace.write("frontend/src/App.tsx", "export const App = () => null;")

        result = await ArtifactManagerAgent().execute(make_context(memory, stub_llm, adapters))

        assert any("README" in warning for warning in result.warnings)

    async def test_compose_omits_services_the_project_lacks(
        self, memory, stub_llm, adapters
    ) -> None:
        memory.analysis = RequirementAnalysis(
            needs_database=False, needs_backend=False, needs_frontend=True
        )
        memory.tech_stack = TechStack(frontend="react")
        memory.workspace.write("README.md", "# Portfolio")
        memory.workspace.write("frontend/src/App.tsx", "export const App = () => null;")

        await ArtifactManagerAgent().execute(make_context(memory, stub_llm, adapters))

        compose = memory.workspace.read("docker-compose.yml") or ""
        assert "web:" in compose
        assert "db:" not in compose
        assert "api:" not in compose


class TestImprovementSkip:
    def test_skips_when_review_found_nothing(self, memory, stub_llm, adapters) -> None:
        from app.agents.improvement_engineer import ImprovementEngineerAgent

        memory.review = ReviewFindings(issues=[], duplication=[])
        decision = ImprovementEngineerAgent().should_execute(
            make_context(memory, stub_llm, adapters)
        )

        assert decision.skipped is True
        assert "no actionable issues" in decision.reason.lower()

    def test_runs_when_review_found_an_issue(self, memory, stub_llm, adapters) -> None:
        from app.agents.improvement_engineer import ImprovementEngineerAgent

        memory.review = ReviewFindings(
            issues=[{"id": "ISS-01", "severity": "high", "description": "SQL injection"}]
        )
        decision = ImprovementEngineerAgent().should_execute(
            make_context(memory, stub_llm, adapters)
        )

        assert decision.skipped is False


class TestAnalysisIsNotRepeated:
    """The approved analysis must not be silently re-derived during a run.

    The user picks a technology stack against the analysis they were shown.
    Re-running the Business Analyst mid-run could produce different capability
    decisions from the ones they approved.
    """

    def test_skips_when_the_project_was_already_analysed(
        self, memory, stub_llm, adapters
    ) -> None:
        memory.analysis = RequirementAnalysis(
            functional_requirements=[{"id": "FR-01", "title": "Book", "description": "…"}],
            needs_database=True,
        )
        decision = BusinessAnalystAgent().should_execute(
            make_context(memory, stub_llm, adapters)
        )

        assert decision.skipped is True
        assert "approved" in decision.reason.lower()

    def test_runs_when_there_is_no_analysis_yet(self, memory, stub_llm, adapters) -> None:
        decision = BusinessAnalystAgent().should_execute(
            make_context(memory, stub_llm, adapters)
        )
        assert decision.skipped is False
