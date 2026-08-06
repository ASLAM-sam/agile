"""End-to-end workflow execution against a stubbed language model.

Exercises the whole pipeline — planning, dynamic skipping, code generation,
review, packaging and reporting — without a network call, so the orchestration
contract is verified on every test run.
"""

from __future__ import annotations

import zipfile
from typing import Any

import pytest

from app.agents.context import AgentContext
from app.agents.registry import AgentRegistry
from app.core.enums import AgentRole, AgentStatus, LogLevel
from app.packaging.report import build_report, render_report_markdown
from app.packaging.zip_builder import ZipPackager
from app.workflow.engine import WorkflowEngine, preflight_skips
from app.workflow.memory import RequirementAnalysis, SharedProjectMemory, TechStack
from app.workflow.planner import build_plan
from tests.conftest import StubLLM


def file_bundle(paths: list[str], *, note: str = "") -> dict[str, Any]:
    return {
        "files": [
            {"path": path, "content": f"// {path}\nexport const value = 1;\n", "description": path}
            for path in paths
        ],
        "notes": note,
    }


def file_plan(paths: list[str]) -> dict[str, Any]:
    return {
        "files": [
            {"path": path, "purpose": f"Handles {path}", "depends_on": [], "priority": index}
            for index, path in enumerate(paths, start=1)
        ],
        "rationale": "Standard layered structure.",
    }


def make_context(memory: SharedProjectMemory, llm: Any, adapters: Any) -> AgentContext:
    async def progress(role: AgentRole, percent: int, message: str) -> None:
        return None

    async def log(role: AgentRole, level: LogLevel, message: str, payload: dict) -> None:
        return None

    return AgentContext(
        memory=memory, llm=llm, registry=adapters, report_progress=progress, report_log=log
    )


@pytest.fixture
def full_stack_responses(full_analysis_payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Queued stub responses for a complete full-stack run, in agent order."""
    return [
        # Manager
        {
            "project_name": "Meridian Clinic Manager",
            "one_liner": "Appointment and record management for a clinic.",
            "delivery_approach": "A layered monolith with a React client.",
            "success_criteria": ["Book appointments", "View records", "Manage staff", "Sign in"],
            "key_risks": [{"risk": "Ambiguous roles", "mitigation": "Document assumptions"}],
        },
        # Business Analyst
        full_analysis_payload,
        # Solution Architect
        {
            "style": "Layered monolith — right-sized for this scope",
            "overview": "A React client calling a FastAPI service backed by PostgreSQL.",
            "modules": [
                {
                    "name": "Appointments",
                    "responsibility": "Scheduling",
                    "entities": ["Appointment"],
                    "depends_on": [],
                },
                {
                    "name": "Patients",
                    "responsibility": "Records",
                    "entities": ["Patient"],
                    "depends_on": [],
                },
                {
                    "name": "Identity",
                    "responsibility": "Authentication",
                    "entities": ["User"],
                    "depends_on": [],
                },
            ],
            "layers": [
                {"name": "API", "responsibility": "HTTP", "rules": ["No SQL in routes"]},
                {"name": "Service", "responsibility": "Logic", "rules": ["No HTTP imports"]},
            ],
            "folder_structure": "backend/\nfrontend/\ndatabase/\ndocs/",
            "api_endpoints": [
                {
                    "method": "GET",
                    "path": "/api/v1/patients",
                    "summary": "List patients",
                    "module": "Patients",
                    "auth_required": True,
                    "request_body": "",
                    "response_body": "Patient[]",
                    "status_codes": ["200", "401"],
                },
                {
                    "method": "POST",
                    "path": "/api/v1/appointments",
                    "summary": "Create appointment",
                    "module": "Appointments",
                    "auth_required": True,
                    "request_body": "patient_id, starts_at",
                    "response_body": "Appointment",
                    "status_codes": ["201", "400", "401"],
                },
            ],
            "integrations": [],
            "cross_cutting": ["Central error handling", "Structured logging"],
            "decisions": [
                {"decision": "Layered monolith", "rationale": "Simplest thing that works"},
                {"decision": "JWT auth", "rationale": "Stateless API"},
                {"decision": "PostgreSQL", "rationale": "Relational integrity"},
            ],
        },
        # Database Engineer
        {
            "tables": [
                {
                    "name": "patients",
                    "purpose": "Patient records",
                    "columns": [
                        {
                            "name": "id",
                            "type": "BIGSERIAL",
                            "nullable": False,
                            "description": "PK",
                            "constraint": "PRIMARY KEY",
                        }
                    ],
                },
                {
                    "name": "appointments",
                    "purpose": "Bookings",
                    "columns": [
                        {
                            "name": "id",
                            "type": "BIGSERIAL",
                            "nullable": False,
                            "description": "PK",
                            "constraint": "PRIMARY KEY",
                        }
                    ],
                },
            ],
            "relationships": [
                {
                    "from_table": "appointments",
                    "from_column": "patient_id",
                    "to_table": "patients",
                    "to_column": "id",
                    "cardinality": "one-to-many",
                    "on_delete": "CASCADE",
                }
            ],
            "indexes": [
                {
                    "name": "idx_appointments_patient_id",
                    "table": "appointments",
                    "columns": ["patient_id"],
                    "unique": False,
                    "rationale": "FK lookup",
                },
                {
                    "name": "idx_patients_id",
                    "table": "patients",
                    "columns": ["id"],
                    "unique": True,
                    "rationale": "PK",
                },
            ],
            "schema_sql": "CREATE TABLE patients (id BIGSERIAL PRIMARY KEY);\n"
            "CREATE TABLE appointments (id BIGSERIAL PRIMARY KEY, patient_id BIGINT "
            "REFERENCES patients(id) ON DELETE CASCADE);",
            "seed_sql": "INSERT INTO patients (id) VALUES (1);",
            "migrations": [
                {
                    "filename": "001_initial_schema.sql",
                    "description": "Initial schema",
                    "sql": "CREATE TABLE patients (id BIGSERIAL PRIMARY KEY);",
                }
            ],
            "notes": "Third normal form.",
        },
        # Backend Engineer: plan, then one generation batch
        file_plan(["backend/app/main.py", "backend/app/config.py"]),
        file_bundle(["backend/app/main.py", "backend/app/config.py"]),
        # Frontend Engineer: plan, then one generation batch
        file_plan(["frontend/src/main.tsx", "frontend/src/App.tsx"]),
        file_bundle(["frontend/src/main.tsx", "frontend/src/App.tsx"]),
        # QA Engineer
        {
            "files": [
                {
                    "path": "backend/tests/test_patients.py",
                    "content": "def test_list_patients():\n    assert True\n",
                    "description": "Patient endpoint tests",
                }
            ],
            "coverage_notes": "Covers the patient endpoints.",
            "manual_checks": ["Verify the appointment calendar visually"],
        },
        # Review Engineer
        {
            "issues": [],
            "strengths": ["Clear layering", "Consistent error handling"],
            "missing_apis": [],
            "duplication": [],
            "overall_assessment": "Well structured and coherent.",
            "quality_score": 0.9,
        },
        # Documentation Engineer (Improvement is skipped: review found nothing)
        {
            "readme": "# Meridian Clinic Manager\n\nA clinic management system.",
            "installation_guide": "# Installation\n\n1. Clone the repository.",
            "api_documentation": "# API\n\n## GET /api/v1/patients",
            "developer_guide": "# Development\n\n## Architecture",
            "environment_reference": "# Configuration\n\n| Variable | Purpose |",
        },
    ]


class TestFullStackRun:
    async def test_complete_workflow_produces_a_coherent_project(
        self, memory, adapters, full_stack_responses
    ) -> None:
        memory.tech_stack = TechStack(
            frontend="react", backend="fastapi", database="postgresql", authentication="JWT"
        )
        llm = StubLLM(full_stack_responses)
        ctx = make_context(memory, llm, adapters)

        engine = WorkflowEngine(agent_registry=AgentRegistry(), llm=llm)
        outcome = await engine.run(ctx)

        assert not outcome.failed, outcome.failure_reason
        assert len(outcome.failures) == 0, [f.error for f in outcome.failures]

        # The Manager renamed the project.
        assert memory.project_name == "Meridian Clinic Manager"

        # Every layer produced files.
        assert memory.workspace.under("backend")
        assert memory.workspace.under("frontend")
        assert memory.workspace.exists("database/schema.sql")
        assert memory.workspace.exists("README.md")
        assert memory.workspace.exists("docker-compose.yml")
        assert memory.workspace.exists("aegis-manifest.json")

        # Scaffolds were emitted deterministically alongside generated code.
        assert memory.workspace.exists("backend/pyproject.toml")
        assert memory.workspace.exists("frontend/package.json")
        assert memory.workspace.exists("frontend/vite.config.ts")

        # The review found nothing, so the improvement pass was skipped.
        improvement = next(
            o for o in outcome.outcomes if o.role is AgentRole.IMPROVEMENT_ENGINEER
        )
        assert improvement.status is AgentStatus.SKIPPED

        assert outcome.total_usage.output_tokens > 0

    async def test_report_and_package_are_produced(
        self, memory, adapters, full_stack_responses, tmp_path
    ) -> None:
        memory.tech_stack = TechStack(
            frontend="react", backend="fastapi", database="postgresql", authentication="JWT"
        )
        llm = StubLLM(full_stack_responses)
        ctx = make_context(memory, llm, adapters)

        outcome = await WorkflowEngine(agent_registry=AgentRegistry(), llm=llm).run(ctx)
        report = build_report(memory, outcome)

        assert report["status"] in {"Ready for development", "Ready with gaps"}
        assert report["agents"]["executed"] >= 9
        assert report["statistics"]["file_count"] > 15
        assert report["effort_saved"]["hours_low"] > 0
        assert report["effort_saved"]["basis"], "the estimate must state its basis"
        assert report["confidence"]["overall"] > 0

        markdown = render_report_markdown(report)
        assert "AI Engineering Report" in markdown
        assert "Estimated manual development effort" in markdown

        packager = ZipPackager(artifact_root=tmp_path)
        package = packager.write(
            memory.workspace, run_id="testrun01", project_slug=memory.project_slug
        )

        assert package.path.exists()
        assert package.size_bytes > 0

        with zipfile.ZipFile(package.path) as archive:
            names = archive.namelist()
            assert names, "the archive must not be empty"
            # Everything sits under one top-level directory.
            roots = {name.split("/")[0] for name in names}
            assert len(roots) == 1
            assert archive.testzip() is None, "the archive must not be corrupt"


class TestStaticSiteRun:
    async def test_frontend_only_project_skips_backend_and_database(
        self, memory, adapters, static_site_analysis_payload
    ) -> None:
        """The headline behaviour, verified end to end."""
        memory.project_name = "Portfolio"
        memory.idea = "A personal portfolio website"
        memory.tech_stack = TechStack(frontend="react")

        responses: list[dict[str, Any]] = [
            {
                "project_name": "Aurora Portfolio",
                "one_liner": "A personal portfolio site.",
                "delivery_approach": "A static React application.",
                "success_criteria": ["Show projects", "Show skills", "Contact", "Responsive"],
                "key_risks": [{"risk": "Content gaps", "mitigation": "Use placeholders"}],
            },
            static_site_analysis_payload,
            {
                "style": "Static single-page application",
                "overview": "A client-rendered React site with no backend.",
                "modules": [
                    {
                        "name": "Content",
                        "responsibility": "Pages",
                        "entities": [],
                        "depends_on": [],
                    }
                ],
                "layers": [{"name": "UI", "responsibility": "Presentation", "rules": []}],
                "folder_structure": "frontend/\ndocs/",
                "api_endpoints": [],
                "integrations": [],
                "cross_cutting": ["Responsive layout"],
                "decisions": [
                    {"decision": "No backend", "rationale": "Nothing to persist"},
                    {"decision": "React", "rationale": "Component reuse"},
                    {"decision": "Static hosting", "rationale": "Lowest cost"},
                ],
            },
            file_plan(["frontend/src/main.tsx", "frontend/src/App.tsx"]),
            file_bundle(["frontend/src/main.tsx", "frontend/src/App.tsx"]),
            {
                "files": [
                    {
                        "path": "frontend/src/App.test.tsx",
                        "content": "test('renders', () => { expect(true).toBe(true); });",
                        "description": "Smoke test",
                    }
                ],
                "coverage_notes": "Smoke coverage.",
                "manual_checks": [],
            },
            {
                "issues": [],
                "strengths": ["Clean component structure"],
                "missing_apis": [],
                "duplication": [],
                "overall_assessment": "Simple and correct.",
                "quality_score": 0.88,
            },
            {
                "readme": "# Aurora Portfolio",
                "installation_guide": "# Installation",
                "api_documentation": "",
                "developer_guide": "# Development",
                "environment_reference": "# Configuration",
            },
        ]

        llm = StubLLM(responses)
        ctx = make_context(memory, llm, adapters)
        outcome = await WorkflowEngine(agent_registry=AgentRegistry(), llm=llm).run(ctx)

        assert not outcome.failed

        skipped_roles = {o.role for o in outcome.skipped}
        assert AgentRole.DATABASE_ENGINEER in skipped_roles
        assert AgentRole.BACKEND_ENGINEER in skipped_roles

        # No backend or database artefacts exist at all.
        assert not memory.workspace.under("backend")
        assert not memory.workspace.exists("database/schema.sql")
        assert memory.workspace.under("frontend")

        # Compose covers only the web service.
        compose = memory.workspace.read("docker-compose.yml") or ""
        assert "web:" in compose
        assert "db:" not in compose

        report = build_report(memory, outcome)
        database_entry = next(a for a in report["artifacts"] if a["name"] == "SQL Schema")
        assert database_entry["delivered"] is True
        assert "not required" in database_entry["detail"]


class TestFailureHandling:
    async def test_a_non_critical_failure_does_not_abort_the_run(
        self, memory, adapters, full_analysis_payload
    ) -> None:
        """QA failing must not discard working generated code."""
        memory.tech_stack = TechStack(frontend="react")

        class FailingQA(StubLLM):
            async def complete_structured(self, prompt):  # type: ignore[no-untyped-def]
                if prompt.metadata.get("agent") == AgentRole.QA_ENGINEER.value:
                    raise RuntimeError("model provider unavailable")
                return await super().complete_structured(prompt)

        static_payload = dict(full_analysis_payload)
        static_payload["capabilities"] = {
            "needs_authentication": False,
            "needs_database": False,
            "needs_api": False,
            "needs_backend": False,
            "needs_frontend": True,
        }

        llm = FailingQA(
            [
                {
                    "project_name": "Test Site",
                    "one_liner": "A site.",
                    "delivery_approach": "React.",
                    "success_criteria": ["a", "b", "c", "d"],
                    "key_risks": [{"risk": "r", "mitigation": "m"}],
                },
                static_payload,
                {
                    "style": "SPA",
                    "overview": "A client-rendered site.",
                    "modules": [
                        {"name": "UI", "responsibility": "Pages", "entities": [], "depends_on": []}
                    ],
                    "layers": [{"name": "UI", "responsibility": "View", "rules": []}],
                    "folder_structure": "frontend/",
                    "api_endpoints": [],
                    "integrations": [],
                    "cross_cutting": ["Responsive"],
                    "decisions": [
                        {"decision": "a", "rationale": "b"},
                        {"decision": "c", "rationale": "d"},
                        {"decision": "e", "rationale": "f"},
                    ],
                },
                file_plan(["frontend/src/App.tsx"]),
                file_bundle(["frontend/src/App.tsx"]),
                # QA raises instead of returning.
                {
                    "issues": [],
                    "strengths": [],
                    "missing_apis": [],
                    "duplication": [],
                    "overall_assessment": "Fine.",
                    "quality_score": 0.8,
                },
                {
                    "readme": "# Test",
                    "installation_guide": "# Install",
                    "api_documentation": "",
                    "developer_guide": "# Dev",
                    "environment_reference": "# Config",
                },
            ]
        )

        ctx = make_context(memory, llm, adapters)
        outcome = await WorkflowEngine(agent_registry=AgentRegistry(), llm=llm).run(ctx)

        # The run survived and still packaged.
        assert not outcome.failed
        qa = next(o for o in outcome.outcomes if o.role is AgentRole.QA_ENGINEER)
        assert qa.status is AgentStatus.FAILED
        assert memory.workspace.exists("README.md")
        assert memory.workspace.exists("aegis-manifest.json")

    async def test_a_critical_failure_aborts_the_run(self, memory, adapters) -> None:
        """A failed Business Analyst leaves nothing downstream to build on."""

        class FailingAnalyst(StubLLM):
            async def complete_structured(self, prompt):  # type: ignore[no-untyped-def]
                if prompt.metadata.get("agent") == AgentRole.BUSINESS_ANALYST.value:
                    raise RuntimeError("model provider unavailable")
                return await super().complete_structured(prompt)

        llm = FailingAnalyst(
            [
                {
                    "project_name": "Test",
                    "one_liner": "x",
                    "delivery_approach": "y",
                    "success_criteria": ["a", "b", "c", "d"],
                    "key_risks": [{"risk": "r", "mitigation": "m"}],
                }
            ]
        )
        ctx = make_context(memory, llm, adapters)
        outcome = await WorkflowEngine(agent_registry=AgentRegistry(), llm=llm).run(ctx)

        assert outcome.failed
        assert "Business Analyst" in outcome.failure_reason


class TestPlanPreview:
    def test_preview_matches_what_actually_runs(self, adapters) -> None:
        """The plan shown before a run must match the run's real shape."""
        memory = SharedProjectMemory(
            run_id="r", project_id="p", project_name="P", project_slug="p", idea="idea"
        )
        memory.analysis = RequirementAnalysis(
            needs_database=False, needs_backend=False, needs_frontend=True
        )

        plan = build_plan(AgentRegistry())
        preflight_skips(plan, memory)

        previewed_active = {s.role for s in plan.active_steps}
        assert AgentRole.DATABASE_ENGINEER not in previewed_active
        assert AgentRole.BACKEND_ENGINEER not in previewed_active
        assert AgentRole.FRONTEND_ENGINEER in previewed_active
