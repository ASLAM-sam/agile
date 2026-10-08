"""Unit tests for the self-repair loop."""

from __future__ import annotations

import pytest
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from app.agents.context import AgentContext
from app.core.enums import AgentRole, LogLevel
from app.llm.types import Completion, PromptBundle, TokenUsage
from app.validation.classifier import ClassificationResult, ValidationFailure
from app.validation.executor import CommandResult, ValidationRun, WorkspaceValidator
from app.validation.repair import run_repair_loop
from app.workflow.memory import SharedProjectMemory, ValidationResult


class FakeLLM:
    """Mock LLM returning requested fixed files."""

    def __init__(self, fixes: list[dict[str, Any]] | None = None) -> None:
        self.fixes = fixes or []
        self.calls: list[PromptBundle] = []

    async def complete_structured(self, bundle: PromptBundle) -> Completion:
        self.calls.append(bundle)
        data = self.fixes.pop(0) if self.fixes else {"files": [], "explanation": "no-op"}
        return Completion(data=data, usage=TokenUsage(input_tokens=10, output_tokens=20))


def make_context(memory: SharedProjectMemory, llm: Any) -> AgentContext:
    async def progress(role: AgentRole, percent: int, message: str) -> None:
        pass

    async def log(role: AgentRole, message: str, level: LogLevel = LogLevel.INFO, payload: dict | None = None) -> None:
        pass

    return AgentContext(
        memory=memory,
        llm=llm,
        registry=MagicMock(),
        report_progress=progress,
        report_log=log,
    )


class TestRepairLoop:
    @pytest.mark.asyncio
    async def test_repair_loop_skips_when_initial_validation_passed(self) -> None:
        memory = SharedProjectMemory(
            run_id="run-1", project_id="p-1", project_name="Test", project_slug="test", idea="idea"
        )
        llm = FakeLLM()
        ctx = make_context(memory, llm)

        initial = ValidationResult(passed=True, stack="frontend", total_commands=5, failed_commands=0)
        result = await run_repair_loop(ctx, initial)

        assert result.passed is True
        assert len(llm.calls) == 0
        assert len(memory.repair_cycles) == 0

    @pytest.mark.asyncio
    async def test_repair_loop_fixes_error_and_records_cycle(self) -> None:
        memory = SharedProjectMemory(
            run_id="run-2", project_id="p-2", project_name="Test", project_slug="test", idea="idea"
        )
        memory.workspace.write("frontend/src/App.tsx", "const x = 1;")

        # Mock LLM returns fixed content
        llm = FakeLLM([
            {
                "files": [
                    {"path": "frontend/src/App.tsx", "content": "export const x: number = 1;", "description": "Add export"}
                ],
                "explanation": "Added export statement and type annotation.",
            }
        ])
        ctx = make_context(memory, llm)

        initial = ValidationResult(
            passed=False,
            stack="frontend",
            total_commands=3,
            failed_commands=1,
            failures=[
                {
                    "command": "npm run build",
                    "exit_code": 1,
                    "file": "frontend/src/App.tsx",
                    "line": "1",
                    "error": "TS2304: Cannot find name 'x'",
                    "category": "type_error",
                    "responsible_agent": AgentRole.FRONTEND_ENGINEER.value,
                    "severity": "high",
                }
            ],
        )

        mock_validator = MagicMock(spec=WorkspaceValidator)
        # Re-validation after fix passes
        mock_validator.validate = AsyncMock(
            return_value=ValidationRun(
                workspace_path="/tmp/fake",
                stack="frontend",
                commands=[CommandResult(command="npm run build", exit_code=0, stdout="Build OK", stderr="")],
            )
        )

        result = await run_repair_loop(ctx, initial, validator=mock_validator, max_cycles=3)

        assert result.passed is True
        assert len(llm.calls) == 1
        assert llm.calls[0].metadata["agent"] == AgentRole.FRONTEND_ENGINEER.value
        assert len(memory.repair_cycles) == 1
        assert memory.repair_cycles[0].cycle_number == 1
        assert memory.repair_cycles[0].validation_passed_after is True
        assert "frontend/src/App.tsx" in memory.repair_cycles[0].files_modified
        assert memory.workspace.read("frontend/src/App.tsx") == "export const x: number = 1;"

    @pytest.mark.asyncio
    async def test_repair_loop_stops_at_max_cycles(self) -> None:
        memory = SharedProjectMemory(
            run_id="run-3", project_id="p-3", project_name="Test", project_slug="test", idea="idea"
        )
        memory.workspace.write("backend/main.py", "invalid python")

        llm = FakeLLM([
            {"files": [{"path": "backend/main.py", "content": "still invalid", "description": "attempt 1"}], "explanation": "e1"},
            {"files": [{"path": "backend/main.py", "content": "still invalid 2", "description": "attempt 2"}], "explanation": "e2"},
        ])
        ctx = make_context(memory, llm)

        initial = ValidationResult(
            passed=False,
            stack="backend_python",
            total_commands=2,
            failed_commands=1,
            failures=[
                {
                    "command": "python -m compileall",
                    "exit_code": 1,
                    "file": "backend/main.py",
                    "line": "1",
                    "error": "SyntaxError: invalid syntax",
                    "category": "syntax_error",
                    "responsible_agent": AgentRole.BACKEND_ENGINEER.value,
                    "severity": "critical",
                }
            ],
        )

        mock_validator = MagicMock(spec=WorkspaceValidator)
        # Re-validation keeps failing
        mock_validator.validate = AsyncMock(
            return_value=ValidationRun(
                workspace_path="/tmp/fake",
                stack="backend_python",
                commands=[
                    CommandResult(
                        command="python -m compileall",
                        exit_code=1,
                        stdout="",
                        stderr="SyntaxError: invalid syntax\n  File 'backend/main.py', line 1",
                    )
                ],
            )
        )

        result = await run_repair_loop(ctx, initial, validator=mock_validator, max_cycles=2)

        assert result.passed is False
        assert len(llm.calls) == 2
        assert len(memory.repair_cycles) == 2
        assert memory.repair_cycles[1].validation_passed_after is False

    @pytest.mark.asyncio
    async def test_repair_loop_detects_stagnation_and_breaks(self) -> None:
        """When identical failure repeats 3 times, repair loop aborts early."""
        memory = SharedProjectMemory(
            run_id="run-stagnate", project_id="p-s", project_name="Test", project_slug="test", idea="idea"
        )
        memory.workspace.write("src/index.ts", "const a = 1;")
        llm = FakeLLM([
            {"files": [{"path": "src/index.ts", "content": "const a = 2;", "description": "fix 1"}], "explanation": "e1"},
            {"files": [{"path": "src/index.ts", "content": "const a = 3;", "description": "fix 2"}], "explanation": "e2"},
            {"files": [{"path": "src/index.ts", "content": "const a = 4;", "description": "fix 3"}], "explanation": "e3"},
            {"files": [{"path": "src/index.ts", "content": "const a = 5;", "description": "fix 4"}], "explanation": "e4"},
            {"files": [{"path": "src/index.ts", "content": "const a = 6;", "description": "fix 5"}], "explanation": "e5"},
        ])
        ctx = make_context(memory, llm)

        initial = ValidationResult(
            passed=False,
            stack="frontend",
            total_commands=1,
            failed_commands=1,
            failures=[
                {
                    "command": "npm run build",
                    "exit_code": 1,
                    "file": "src/index.ts",
                    "line": "1",
                    "error": "Error: recurring issue",
                    "category": "build_error",
                    "responsible_agent": AgentRole.FRONTEND_ENGINEER.value,
                }
            ],
        )

        mock_validator = MagicMock(spec=WorkspaceValidator)
        # Always returns the exact same failure
        mock_validator.validate = AsyncMock(
            return_value=ValidationRun(
                workspace_path="/tmp/fake",
                stack="frontend",
                commands=[
                    CommandResult(
                        command="npm run build",
                        exit_code=1,
                        stdout="",
                        stderr="Error: recurring issue",
                    )
                ],
            )
        )

        result = await run_repair_loop(ctx, initial, validator=mock_validator, max_cycles=5)
        # Should stop after at most 3 cycles due to stagnation
        assert len(llm.calls) <= 3
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_repair_loop_rolls_back_on_regression(self) -> None:
        """When an edit introduces more failing commands, workspace is restored to pre-cycle state."""
        memory = SharedProjectMemory(
            run_id="run-rollback", project_id="p-r", project_name="Test", project_slug="test", idea="idea"
        )
        original_code = "print('hello')"
        memory.workspace.write("app/main.py", original_code)

        llm = FakeLLM([
            # Bad fix that breaks everything
            {
                "files": [{"path": "app/main.py", "content": "corrupted!!! syntax error", "description": "bad fix"}],
                "explanation": "broke it",
            }
        ])
        ctx = make_context(memory, llm)

        initial = ValidationResult(
            passed=False,
            stack="backend_python",
            total_commands=1,
            failed_commands=1,
            failures=[
                {
                    "command": "pytest",
                    "exit_code": 1,
                    "file": "tests/test_main.py",
                    "line": "10",
                    "error": "AssertionError: False != True",
                    "category": "test_failure",
                    "responsible_agent": AgentRole.BACKEND_ENGINEER.value,
                }
            ],
        )

        mock_validator = MagicMock(spec=WorkspaceValidator)
        # Re-validation has MORE failed commands (2 instead of 1)
        mock_validator.validate = AsyncMock(
            return_value=ValidationRun(
                workspace_path="/tmp/fake",
                stack="backend_python",
                commands=[
                    CommandResult(command="python -m compileall", exit_code=1, stdout="", stderr="SyntaxError: invalid syntax"),
                    CommandResult(command="pytest", exit_code=1, stdout="", stderr="Tests failed"),
                    CommandResult(command="ruff check", exit_code=1, stdout="", stderr="Lint failed"),
                ],
            )
        )

        result = await run_repair_loop(ctx, initial, validator=mock_validator, max_cycles=1)
        assert result.passed is False
        # The workspace file must have been rolled back to original_code!
        assert memory.workspace.read("app/main.py") == original_code
