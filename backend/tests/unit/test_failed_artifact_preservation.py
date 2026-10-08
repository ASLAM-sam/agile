"""Comprehensive test suite for Failed Generation Artifact Preservation in AEGIS AI.

Validates the invariant: RELEASE BLOCKED != ARTIFACT DELETED.
When generation fails for ANY reason (build failure, typecheck failure, LLM timeout,
malformed response, budget exhaustion, repair exhaustion, unexpected exception),
a deterministic partial archive (project-partial.zip) must be created and preserved.
"""

from __future__ import annotations

import io
import json
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.enums import AgentRole, ArtifactKind, RunStatus
from app.core.exceptions import BudgetExceededError, ValidationError
from app.packaging.diagnostics import (
    MODEL_ROUTING_CONFIG,
    build_diagnostics,
    build_generation_status_readme,
    count_preserved_files,
)
from app.packaging.workspace import ProjectWorkspace
from app.packaging.zip_builder import ZipPackager
from app.schemas.generation import RunArtifactInfo, RunDetail, RunSummary
from app.services.orchestration_service import RunOrchestrator
from app.workflow.engine import WorkflowOutcome
from app.workflow.memory import RepairCycle, SharedProjectMemory, ValidationResult


class TestFailedArtifactPreservation:
    """Test suite covering all required failure modes and packaging invariants."""

    def _create_sample_workspace(self) -> ProjectWorkspace:
        ws = ProjectWorkspace()
        ws.write("package.json", '{"name": "test-app", "version": "1.0.0"}')
        ws.write("tsconfig.json", '{"compilerOptions": {"target": "ES2022"}}')
        ws.write("frontend/src/App.tsx", "export function App() { return <h1>Hello</h1>; }")
        ws.write("frontend/src/main.tsx", "import { App } from './App';")
        return ws

    def test_test1_build_failure_creates_partial_zip(self) -> None:
        """Test 1: Build failure → partial ZIP exists."""
        workspace = self._create_sample_workspace()
        with tempfile.TemporaryDirectory() as tmp_dir:
            packager = ZipPackager(artifact_root=tmp_dir)
            orchestrator = RunOrchestrator(packager=packager)

            memory = SharedProjectMemory(
                run_id="run-build-fail",
                project_id="p-1",
                project_name="BuildFailApp",
                project_slug="build-fail-app",
                idea="Portfolio",
            )
            memory.workspace = workspace
            memory.release_eligible = False

            val_res = ValidationResult(
                passed=False,
                stack="frontend",
                total_commands=1,
                failed_commands=1,
                failures=[
                    {
                        "command": "npm run build",
                        "exit_code": 1,
                        "error": "Failed to compile: build error in vite",
                    }
                ],
            )
            memory.final_qa_result = val_res

            outcome = WorkflowOutcome(
                plan=MagicMock(),
                failed=True,
                failure_reason="Build failed: npm run build exited with code 1",
            )

            pkg = orchestrator._create_partial_package(
                run_id="run-build-fail",
                memory=memory,
                outcome=outcome,
                failed_stage="Final QA",
                failed_command="npm run build",
                exit_code=1,
            )

            assert pkg is not None
            assert pkg.path.exists()
            assert "partial" in pkg.filename
            assert pkg.size_bytes > 0

    def test_test2_typescript_failure_creates_partial_zip(self) -> None:
        """Test 2: TypeScript failure → partial ZIP exists with failed command info."""
        workspace = self._create_sample_workspace()
        with tempfile.TemporaryDirectory() as tmp_dir:
            packager = ZipPackager(artifact_root=tmp_dir)
            orchestrator = RunOrchestrator(packager=packager)

            memory = SharedProjectMemory(
                run_id="run-ts-fail",
                project_id="p-1",
                project_name="TSFailApp",
                project_slug="ts-fail-app",
                idea="Portfolio",
            )
            memory.workspace = workspace
            memory.release_eligible = False

            val_res = ValidationResult(
                passed=False,
                stack="frontend",
                total_commands=2,
                failed_commands=1,
                failures=[
                    {
                        "command": "npm run typecheck",
                        "exit_code": 2,
                        "error": "TS2304: Cannot find name 'MissingType'",
                    }
                ],
            )
            memory.final_qa_result = val_res

            outcome = WorkflowOutcome(
                plan=MagicMock(),
                failed=True,
                failure_reason="Typecheck failed: TS2304",
            )

            pkg = orchestrator._create_partial_package(
                run_id="run-ts-fail",
                memory=memory,
                outcome=outcome,
                failed_stage="Final QA",
                failed_command="npm run typecheck",
                exit_code=2,
            )

            assert pkg.path.exists()
            with zipfile.ZipFile(pkg.path, "r") as archive:
                readme = archive.read("aegis-generation-partial/README-GENERATION-STATUS.md").decode("utf-8")
                assert "Failed command: npm run typecheck" in readme
                assert "Exit code: 2" in readme
                assert "RELEASE BLOCKED" in readme

    def test_test3_llm_timeout_creates_partial_zip(self) -> None:
        """Test 3: LLM timeout → partial ZIP exists with files produced before timeout."""
        workspace = self._create_sample_workspace()
        with tempfile.TemporaryDirectory() as tmp_dir:
            packager = ZipPackager(artifact_root=tmp_dir)
            orchestrator = RunOrchestrator(packager=packager)

            memory = SharedProjectMemory(
                run_id="run-timeout",
                project_id="p-1",
                project_name="TimeoutApp",
                project_slug="timeout-app",
                idea="Portfolio",
            )
            memory.workspace = workspace

            outcome = WorkflowOutcome(
                plan=MagicMock(),
                failed=True,
                failure_reason="TimeoutError: LLM call to Google Gemini timed out after 90s",
            )

            pkg = orchestrator._create_partial_package(
                run_id="run-timeout",
                memory=memory,
                outcome=outcome,
                failed_stage="LLM Timeout",
            )

            assert pkg.path.exists()
            with zipfile.ZipFile(pkg.path, "r") as archive:
                readme = archive.read("aegis-generation-partial/README-GENERATION-STATUS.md").decode("utf-8")
                assert "Failed stage: LLM Timeout" in readme
                assert "Frontend files: 3" in readme or "Frontend files: 4" in readme

    def test_test4_malformed_llm_response_creates_partial_zip(self) -> None:
        """Test 4: Malformed LLM response → partial ZIP exists."""
        workspace = self._create_sample_workspace()
        with tempfile.TemporaryDirectory() as tmp_dir:
            packager = ZipPackager(artifact_root=tmp_dir)
            orchestrator = RunOrchestrator(packager=packager)

            memory = SharedProjectMemory(
                run_id="run-malformed",
                project_id="p-1",
                project_name="MalformedApp",
                project_slug="malformed-app",
                idea="Portfolio",
            )
            memory.workspace = workspace

            outcome = WorkflowOutcome(
                plan=MagicMock(),
                failed=True,
                failure_reason="ValidationError: LLM response failed JSON validation: expecting value",
            )

            pkg = orchestrator._create_partial_package(
                run_id="run-malformed",
                memory=memory,
                outcome=outcome,
                failed_stage="Frontend Engineer",
            )

            assert pkg.path.exists()
            with zipfile.ZipFile(pkg.path, "r") as archive:
                diag = json.loads(archive.read("aegis-generation-partial/aegis-diagnostics/generation-report.json"))
                assert diag["status"] == "failed"
                assert diag["release_eligible"] is False

    def test_test5_budget_exceeded_creates_partial_zip(self) -> None:
        """Test 5: Budget exceeded → partial ZIP exists."""
        workspace = self._create_sample_workspace()
        with tempfile.TemporaryDirectory() as tmp_dir:
            packager = ZipPackager(artifact_root=tmp_dir)
            orchestrator = RunOrchestrator(packager=packager)

            memory = SharedProjectMemory(
                run_id="run-budget",
                project_id="p-1",
                project_name="BudgetApp",
                project_slug="budget-app",
                idea="Portfolio",
            )
            memory.workspace = workspace

            mock_ctx = MagicMock()
            mock_ctx.llm.budget.total_used = 15
            mock_ctx.llm.budget.hard_limit = 15

            outcome = WorkflowOutcome(
                plan=MagicMock(),
                failed=True,
                failure_reason="BudgetExceededError: Request budget limit (15) reached.",
            )

            pkg = orchestrator._create_partial_package(
                run_id="run-budget",
                memory=memory,
                outcome=outcome,
                ctx=mock_ctx,
                failed_stage="Request Budget Exhaustion",
            )

            assert pkg.path.exists()
            with zipfile.ZipFile(pkg.path, "r") as archive:
                readme = archive.read("aegis-generation-partial/README-GENERATION-STATUS.md").decode("utf-8")
                assert "LLM requests used: 15 / 15" in readme
                assert "Request Budget Exhaustion" in readme

    def test_test6_repair_exhaustion_creates_partial_zip(self) -> None:
        """Test 6: Repair exhaustion → partial ZIP exists with cycle count."""
        workspace = self._create_sample_workspace()
        with tempfile.TemporaryDirectory() as tmp_dir:
            packager = ZipPackager(artifact_root=tmp_dir)
            orchestrator = RunOrchestrator(packager=packager)

            memory = SharedProjectMemory(
                run_id="run-repair-exh",
                project_id="p-1",
                project_name="RepairExhaustedApp",
                project_slug="repair-exhausted-app",
                idea="Portfolio",
            )
            memory.workspace = workspace
            memory.release_eligible = False

            # Add two recorded repair cycles
            memory.record_repair_cycle(
                RepairCycle(
                    cycle_number=1,
                    failures_found=2,
                    agents_involved=["frontend_engineer"],
                    files_modified=["frontend/src/App.tsx"],
                    validation_passed_after=False,
                    timestamp="2026-01-01T00:00:00Z",
                    model="google/gemini-2.5-flash",
                    failure_signature_before="sig1",
                    failure_signature_after="sig2",
                    result="failed",
                )
            )
            memory.record_repair_cycle(
                RepairCycle(
                    cycle_number=2,
                    failures_found=1,
                    agents_involved=["nemotron_frontend_rescue"],
                    files_modified=["frontend/src/App.tsx"],
                    validation_passed_after=False,
                    timestamp="2026-01-01T00:01:00Z",
                    model="nvidia/nemotron-3-super-120b-a12b",
                    failure_signature_before="sig2",
                    failure_signature_after="sig2",
                    result="failed",
                )
            )

            outcome = WorkflowOutcome(
                plan=MagicMock(),
                failed=True,
                failure_reason="Repair limit reached: persistent failure after 2 cycles.",
            )

            pkg = orchestrator._create_partial_package(
                run_id="run-repair-exh",
                memory=memory,
                outcome=outcome,
                failed_stage="Final QA",
                failed_command="npm run build",
                exit_code=1,
            )

            assert pkg.path.exists()
            with zipfile.ZipFile(pkg.path, "r") as archive:
                readme = archive.read("aegis-generation-partial/README-GENERATION-STATUS.md").decode("utf-8")
                assert "Repair cycles: 2" in readme
                diag = json.loads(archive.read("aegis-generation-partial/aegis-diagnostics/generation-report.json"))
                assert diag["repair_cycles"] == 2

    def test_test7_unexpected_exception_creates_partial_zip(self) -> None:
        """Test 7: Unexpected exception → partial ZIP exists."""
        workspace = self._create_sample_workspace()
        with tempfile.TemporaryDirectory() as tmp_dir:
            packager = ZipPackager(artifact_root=tmp_dir)
            orchestrator = RunOrchestrator(packager=packager)

            memory = SharedProjectMemory(
                run_id="run-unhandled",
                project_id="p-1",
                project_name="UnhandledApp",
                project_slug="unhandled-app",
                idea="Portfolio",
            )
            memory.workspace = workspace

            outcome = WorkflowOutcome(
                plan=MagicMock(),
                failed=True,
                failure_reason="RuntimeError: unexpected OS thread crash",
            )

            pkg = orchestrator._create_partial_package(
                run_id="run-unhandled",
                memory=memory,
                outcome=outcome,
                failed_stage="RuntimeError",
            )

            assert pkg.path.exists()
            assert pkg.file_count == len(workspace)

    def test_test8_successful_generation_creates_normal_project_zip(self) -> None:
        """Test 8: Successful generation → normal project.zip exists without partial prefix."""
        workspace = self._create_sample_workspace()
        with tempfile.TemporaryDirectory() as tmp_dir:
            packager = ZipPackager(artifact_root=tmp_dir)

            pkg = packager.write(
                workspace,
                run_id="run-success",
                project_slug="success-app",
            )

            assert pkg.path.exists()
            assert "partial" not in pkg.filename
            with zipfile.ZipFile(pkg.path, "r") as archive:
                names = archive.namelist()
                # Complete project has files under success-app/
                assert any("App.tsx" in n for n in names)
                # Does NOT contain failure README or diagnostics
                assert not any("README-GENERATION-STATUS.md" in n for n in names)

    def test_test9_failed_generation_does_not_delete_partial_zip(self) -> None:
        """Test 9: Failed generation does not delete partial ZIP."""
        workspace = self._create_sample_workspace()
        with tempfile.TemporaryDirectory() as tmp_dir:
            packager = ZipPackager(artifact_root=tmp_dir)
            orchestrator = RunOrchestrator(packager=packager)

            memory = SharedProjectMemory(
                run_id="run-nodelete",
                project_id="p-1",
                project_name="NoDeleteApp",
                project_slug="no-delete-app",
                idea="Portfolio",
            )
            memory.workspace = workspace
            memory.release_eligible = False

            outcome = WorkflowOutcome(
                plan=MagicMock(),
                failed=True,
                failure_reason="Validation failed",
            )

            pkg = orchestrator._create_partial_package(
                run_id="run-nodelete",
                memory=memory,
                outcome=outcome,
                failed_stage="Independent ZIP Validation",
            )

            path = pkg.path
            assert path.exists()
            # Simulate what previously ran: package.path.unlink() was removed!
            # Verify file persists
            assert Path(path).is_file()

    def test_test10_partial_zip_contains_generated_files_before_failure(self) -> None:
        """Test 10: Partial ZIP contains exact files generated before failure."""
        workspace = ProjectWorkspace()
        workspace.write("package.json", '{"name": "partial-files-app"}')
        workspace.write("tsconfig.json", '{"compilerOptions": {}}')
        workspace.write("frontend/src/App.tsx", "export const App = () => <div>Incomplete</div>;")

        with tempfile.TemporaryDirectory() as tmp_dir:
            packager = ZipPackager(artifact_root=tmp_dir)
            pkg = packager.write_partial(
                workspace,
                run_id="run-files-check",
                project_slug="partial-files-app",
            )

            with zipfile.ZipFile(pkg.path, "r") as archive:
                names = set(archive.namelist())
                assert "aegis-generation-partial/project/package.json" in names
                assert "aegis-generation-partial/project/tsconfig.json" in names
                assert "aegis-generation-partial/project/frontend/src/App.tsx" in names

                content = archive.read("aegis-generation-partial/project/frontend/src/App.tsx").decode("utf-8")
                assert "export const App = () => <div>Incomplete</div>;" in content

    def test_test11_partial_zip_contains_deterministic_diagnostics(self) -> None:
        """Test 11: Partial ZIP contains deterministic diagnostics and README."""
        workspace = self._create_sample_workspace()
        counts = count_preserved_files(workspace)

        readme = build_generation_status_readme(
            failed_stage="Final QA",
            failed_command="npm run typecheck",
            exit_code=2,
            failure_count=3,
            repair_cycles=2,
            llm_requests_used=10,
            llm_request_limit=15,
            frontend_files=counts["frontend"],
            backend_files=counts["backend"],
            database_files=counts["database"],
        )

        diag = build_diagnostics(
            generation_id="run-diag-test",
            failed_stage="Final QA",
            llm_requests_used=10,
            llm_request_limit=15,
            repair_cycles=2,
            files_generated=len(workspace),
            files_modified=2,
            commands_passed=["npm run lint"],
            commands_failed=["npm run typecheck"],
            failure_signatures=["TS2304_missing_name"],
            models_used=["nvidia/nemotron-3-super-120b-a12b", "google/gemini-2.5-flash"],
            validation_failures=[{"command": "npm run typecheck", "exit_code": 2}],
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            packager = ZipPackager(artifact_root=tmp_dir)
            pkg = packager.write_partial(
                workspace,
                run_id="run-diag-test",
                project_slug="diag-test",
                diagnostics=diag,
                readme_content=readme,
            )

            with zipfile.ZipFile(pkg.path, "r") as archive:
                # 1. README check
                readme_content = archive.read("aegis-generation-partial/README-GENERATION-STATUS.md").decode("utf-8")
                assert "RELEASE BLOCKED" in readme_content
                assert "Failed stage: Final QA" in readme_content
                assert "Failed command: npm run typecheck" in readme_content
                assert "Exit code: 2" in readme_content
                assert "LLM requests used: 10 / 15" in readme_content

                # 2. Diagnostics JSON files
                gen_report = json.loads(archive.read("aegis-generation-partial/aegis-diagnostics/generation-report.json"))
                assert gen_report["generation_id"] == "run-diag-test"
                assert gen_report["status"] == "failed"
                assert gen_report["release_eligible"] is False
                assert gen_report["llm_requests_used"] == 10
                assert gen_report["llm_request_limit"] == 15
                assert gen_report["repair_cycles"] == 2
                assert gen_report["commands_failed"] == ["npm run typecheck"]

                val_failures = json.loads(archive.read("aegis-generation-partial/aegis-diagnostics/validation-failures.json"))
                assert len(val_failures) == 1
                assert val_failures[0]["command"] == "npm run typecheck"

                routing = json.loads(archive.read("aegis-generation-partial/aegis-diagnostics/model-routing.json"))
                assert routing["PLANNER"]["model"] == "nvidia/nemotron-3-super-120b-a12b"
                assert routing["FRONTEND"]["model"] == "google/gemini-2.5-flash"
                assert routing["DEBUG"]["model"] == "nvidia/nemotron-3-super-120b-a12b"

    def test_test12_api_schema_exposes_partial_artifact(self) -> None:
        """Test 12: API schema exposes artifact information for failed runs."""
        artifact_info = RunArtifactInfo(
            available=True,
            type="partial",
            name="project-partial.zip",
        )
        detail = RunDetail(
            id="run-api-1",
            project_id="p-1",
            status="failed",
            phase="failed",
            progress=50,
            file_count=4,
            duration_seconds=15.0,
            created_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
            finished_at=datetime(2026, 1, 1, 0, 0, 15, tzinfo=UTC),
            release_eligible=False,
            artifact=artifact_info,
        )

        dump = detail.model_dump()
        assert dump["status"] == "failed"
        assert dump["release_eligible"] is False
        assert dump["artifact"]["available"] is True
        assert dump["artifact"]["type"] == "partial"
        assert dump["artifact"]["name"] == "project-partial.zip"
