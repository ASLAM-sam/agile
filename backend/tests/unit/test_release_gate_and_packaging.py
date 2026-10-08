"""Tests for Release Gate, Zip Packaging, Secret Scanning, and Independent Zip Validation."""

from __future__ import annotations

import io
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.enums import AgentRole
from app.core.exceptions import ValidationError
from app.packaging.workspace import ProjectWorkspace
from app.packaging.zip_builder import ZipPackager, extract_and_verify_zip
from app.services.orchestration_service import RunOrchestrator, _render_failure_report
from app.workflow.engine import WorkflowOutcome
from app.workflow.memory import SharedProjectMemory, ValidationResult


class TestReleaseGateAndPackaging:
    """Verify that release gates strictly prevent broken or insecure projects from producing ZIPs."""

    def test_workspace_modification_invalidates_qa_fingerprint(self) -> None:
        """Modifying workspace after validation marks validation stale."""
        memory = SharedProjectMemory(
            run_id="run-fp", project_id="p-1", project_name="App", project_slug="app", idea="idea"
        )
        memory.workspace.write("src/main.ts", "console.log('v1');")

        # Record validation run for current fingerprint
        val = ValidationResult(
            passed=True,
            stack="frontend",
            total_commands=2,
            failed_commands=0,
            workspace_fingerprint=memory.workspace.fingerprint,
        )
        memory.record_validation_run(val)
        memory.record_final_qa(val)

        assert memory.release_eligible is True
        assert memory.is_validation_current is True

        # Now an agent modifies a file after QA
        memory.workspace.write("src/main.ts", "console.log('v2 modification');")

        # The fingerprint changed, so previous validation is now stale!
        assert memory.is_validation_current is False

    def test_zip_builder_rejects_leaked_secrets(self) -> None:
        """ZipPackager blocks packaging if real API keys or private keys are in code."""
        workspace = ProjectWorkspace()
        # Leaked Gemini key
        workspace.write("src/config.ts", "const apiKey = 'AIzaSyA1234567890123456789012345678901';")

        with tempfile.TemporaryDirectory() as tmp_dir:
            packager = ZipPackager(artifact_root=tmp_dir)
            with pytest.raises(ValidationError, match="Secret or credential detected"):
                packager.write(workspace, run_id="run-secret", project_slug="secret-app")

    def test_zip_builder_allows_example_env_files(self) -> None:
        """ZipPackager allows placeholder keys in .env.example files."""
        workspace = ProjectWorkspace()
        workspace.write("src/index.ts", "console.log('clean');")
        workspace.write(".env.example", "API_KEY=AIzaSyA1234567890123456789012345678901\n")

        with tempfile.TemporaryDirectory() as tmp_dir:
            packager = ZipPackager(artifact_root=tmp_dir)
            res = packager.write(workspace, run_id="run-example", project_slug="clean-app")
            assert res.path.exists()
            assert res.size_bytes > 0

    def test_extract_and_verify_zip_safely_extracts(self) -> None:
        """Independent ZIP extraction works and returns file dictionary."""
        workspace = ProjectWorkspace()
        workspace.write("package.json", '{"name": "test"}')
        workspace.write("src/index.ts", "export const ok = true;")

        with tempfile.TemporaryDirectory() as tmp_dir:
            packager = ZipPackager(artifact_root=tmp_dir)
            res = packager.write(workspace, run_id="run-extract", project_slug="extract-test")

            with tempfile.TemporaryDirectory() as extract_dir:
                extracted = extract_and_verify_zip(res.path, extract_dir)
                assert "package.json" in extracted
                assert "src/index.ts" in extracted
                assert extracted["src/index.ts"] == "export const ok = true;"
                assert (Path(extract_dir) / "extract-test" / "src" / "index.ts").exists()

    def test_render_failure_report_contains_all_diagnostic_sections(self) -> None:
        """Failure report contains requirement, stack, compiler errors, and manual actions."""
        memory = SharedProjectMemory(
            run_id="run-rep", project_id="p-1", project_name="BrokenApp", project_slug="broken-app", idea="Build a portfolio"
        )
        memory.final_qa_result = ValidationResult(
            passed=False,
            failed_commands=1,
            failures=[
                {
                    "command": "npm run build",
                    "file": "src/App.tsx",
                    "line": 42,
                    "category": "type_error",
                    "responsible_agent": "frontend_engineer",
                    "error": "TS2339: Property 'title' does not exist on type 'Props'",
                }
            ],
        )
        outcome = WorkflowOutcome(
            plan=MagicMock(),
            failed=True,
            failure_reason="Final QA failed",
        )

        md = _render_failure_report(memory, outcome)
        assert "# Aegis Release Failure Report — BrokenApp" in md
        assert "Build a portfolio" in md
        assert "npm run build" in md
        assert "TS2339" in md
        assert "frontend_engineer" in md
        assert "Recommended Manual Actions" in md
