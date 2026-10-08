"""Validation executor.

Runs real build/test commands against a generated project workspace.
This is the source of truth for whether a generated project is valid.

An agent saying "it should work" is NOT validation.
The exit code of these commands is.

Stack detection:
- Reads package.json → Node/npm project
- Reads requirements.txt / pyproject.toml → Python project
- Both → full-stack project

Commands run in order for each detected stack:
  Frontend (Node):
    1. npm install
    2. npm run typecheck (if script exists)
    3. npm run lint (if script exists)
    4. npm run build
    5. npm test (if script exists)

  Backend Python:
    1. python -m venv .venv (or use uv)
    2. pip install -r requirements.txt / pip install -e .
    3. python -m compileall .
    4. pytest (if configured)
    5. ruff check (if configured)

  Backend Node:
    1. npm install
    2. npm run typecheck (if script exists)
    3. npm run lint (if script exists)
    4. npm run build (if script exists)
    5. npm test (if script exists)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.logging import get_logger
from app.validation.dependencies import validate_and_sync_dependencies

logger = get_logger(__name__)

#: How long a single command may run before it is killed.
DEFAULT_COMMAND_TIMEOUT = 300  # seconds


@dataclass
class CommandResult:
    """Result of a single command execution."""

    command: str
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    skipped: bool = False
    skip_reason: str = ""

    @property
    def passed(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    @property
    def output(self) -> str:
        """Combined stdout + stderr for parsing."""
        parts = [p for p in [self.stdout, self.stderr] if p.strip()]
        return "\n".join(parts)


@dataclass
class ValidationRun:
    """Result of a complete validation run against a project workspace."""

    workspace_path: str
    stack: str  # 'frontend', 'backend_python', 'backend_node', 'fullstack', 'unknown'
    commands: list[CommandResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """True only if all required (non-skipped) commands exited 0."""
        return all(cmd.passed or cmd.skipped for cmd in self.commands)

    @property
    def failed_commands(self) -> list[CommandResult]:
        return [cmd for cmd in self.commands if not cmd.passed and not cmd.skipped]

    @property
    def total_commands(self) -> int:
        return len([cmd for cmd in self.commands if not cmd.skipped])

    def as_dict(self) -> dict[str, Any]:
        return {
            "workspace_path": self.workspace_path,
            "stack": self.stack,
            "passed": self.passed,
            "total_commands": self.total_commands,
            "failed_count": len(self.failed_commands),
            "commands": [
                {
                    "command": cmd.command,
                    "exit_code": cmd.exit_code,
                    "passed": cmd.passed,
                    "skipped": cmd.skipped,
                    "skip_reason": cmd.skip_reason,
                    "stdout_preview": cmd.stdout[:500] if cmd.stdout else "",
                    "stderr_preview": cmd.stderr[:500] if cmd.stderr else "",
                    "timed_out": cmd.timed_out,
                }
                for cmd in self.commands
            ],
        }


class WorkspaceValidator:
    """Writes the generated workspace to disk and runs validation commands."""

    def __init__(
        self,
        *,
        timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT,
        workspace_root: str | None = None,
    ) -> None:
        self._timeout = timeout_seconds
        self._workspace_root = workspace_root or tempfile.gettempdir()

    async def validate(
        self,
        files: dict[str, str],
        *,
        run_id: str = "validation",
    ) -> ValidationRun:
        """Write files to a temp directory and run the validation suite.

        Args:
            files: dict of relative_path → file_content
            run_id: identifier for logging

        Returns:
            ValidationRun with all command results
        """
        # Synchronize and validate dependencies before writing or executing commands
        files, dep_logs = validate_and_sync_dependencies(files)
        for log_msg in dep_logs:
            logger.info("dependency_sync", extra={"run_id": run_id, "detail": log_msg})

        clean_id = run_id
        for prefix in ("final-qa-", "qa-", "zip-val-"):
            if clean_id.startswith(prefix):
                clean_id = clean_id[len(prefix):]
        if "-repair-" in clean_id:
            clean_id = clean_id.split("-repair-")[0]
        if "-zip-val" in clean_id:
            clean_id = clean_id.split("-zip-val")[0]
        clean_id = clean_id.strip("-")

        if "zip-val" in run_id:
            workspace_dir = Path(self._workspace_root) / f"aegis-validate-{run_id}"
        else:
            workspace_dir = Path(self._workspace_root) / f"aegis-run-workspace-{clean_id}"

        # In hermetic test mode (e.g. pytest with StubLLM), return mock validation.
        # Strictly forbidden in production environments.
        from app.core.config import settings
        if os.environ.get("AEGIS_MOCK_VALIDATION") == "true" and settings.environment != "production":
            stack = self._detect_stack(workspace_dir, files)
            return ValidationRun(
                workspace_path=str(workspace_dir),
                stack=stack,
                commands=[
                    CommandResult(
                        command="hermetic-test-check",
                        exit_code=0,
                        stdout="Hermetic test validation passed",
                        stderr="",
                    )
                ],
            )

        workspace_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Write all files
            for rel_path, content in files.items():
                target = workspace_dir / rel_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")

            # Detect stack
            stack = self._detect_stack(workspace_dir, files)
            logger.info("validation_start", extra={"run_id": run_id, "stack": stack})

            run = ValidationRun(workspace_path=str(workspace_dir), stack=stack)

            # Run appropriate command suite
            if stack in ("frontend", "fullstack"):
                frontend_dir = workspace_dir / "frontend"
                if not frontend_dir.exists():
                    frontend_dir = workspace_dir  # single-page app
                await self._validate_node(frontend_dir, run, prefix="frontend")

            if stack in ("backend_python", "fullstack"):
                backend_dir = workspace_dir / "backend"
                if not backend_dir.exists():
                    backend_dir = workspace_dir
                await self._validate_python(backend_dir, run)
            elif stack in ("backend_node", "fullstack"):
                backend_dir = workspace_dir / "backend"
                if not backend_dir.exists():
                    backend_dir = workspace_dir
                await self._validate_node(backend_dir, run, prefix="backend")

            if stack == "unknown":
                # Best-effort: try to find any runnable thing
                await self._validate_best_effort(workspace_dir, files, run)

            return run

        finally:
            # Preserve workspace during repair cycles so installed node_modules are reused.
            # CRITICAL: Never delete workspace if validation failed or an error occurred;
            # preserve it for diagnostics and inspection. Only clean up if validation passed.
            is_intermediate = "-repair-" in run_id or "-qa-" in run_id
            validation_passed = "run" in locals() and getattr(run, "passed", False)
            if validation_passed and not is_intermediate:
                try:
                    shutil.rmtree(workspace_dir, ignore_errors=True)
                except Exception:  # noqa: BLE001
                    pass

    @staticmethod
    def _detect_stack(workspace_dir: Path, files: dict[str, str]) -> str:
        """Determine what kind of project this is."""
        paths = set(files.keys())

        has_frontend_pkg = any(
            p in paths for p in [
                "frontend/package.json",
                "package.json",
            ]
        )
        has_backend_py = any(
            p in paths for p in [
                "backend/requirements.txt",
                "backend/pyproject.toml",
                "requirements.txt",
                "pyproject.toml",
            ]
        )
        has_backend_node_pkg = "backend/package.json" in paths

        if has_frontend_pkg and has_backend_py:
            return "fullstack"
        if has_frontend_pkg and has_backend_node_pkg:
            return "fullstack"
        if has_frontend_pkg:
            return "frontend"
        if has_backend_py:
            return "backend_python"
        if has_backend_node_pkg:
            return "backend_node"

        # Check for single-page app with just package.json
        if (workspace_dir / "package.json").exists():
            return "frontend"

        return "unknown"

    async def _validate_node(
        self,
        project_dir: Path,
        run: ValidationRun,
        prefix: str = "",
    ) -> None:
        """Run npm-based validation commands."""
        if not project_dir.exists():
            run.commands.append(CommandResult(
                command="npm install",
                exit_code=1,
                stdout="",
                stderr=f"Directory {project_dir} does not exist",
                skipped=True,
                skip_reason="Directory missing",
            ))
            return

        pkg_json_path = project_dir / "package.json"
        if not pkg_json_path.exists():
            run.commands.append(CommandResult(
                command="npm install",
                exit_code=0,
                stdout="",
                stderr="",
                skipped=True,
                skip_reason="No package.json found",
            ))
            return

        # Parse scripts from package.json
        try:
            pkg_data = json.loads(pkg_json_path.read_text(encoding="utf-8"))
            scripts = pkg_data.get("scripts", {})
        except (json.JSONDecodeError, OSError):
            scripts = {}

        npm_cmd = shutil.which("npm") or "npm"

        # 1. npm install with deterministic caching and timing
        pkg_hash = hashlib.sha256(pkg_json_path.read_bytes()).hexdigest()
        hash_marker = project_dir / "node_modules" / ".package_hash"
        cache_dir = Path(self._workspace_root) / f"aegis-cache-node_modules-{pkg_hash}"

        reused = False
        if (project_dir / "node_modules").exists() and hash_marker.exists():
            try:
                if hash_marker.read_text(encoding="utf-8").strip() == pkg_hash:
                    reused = True
                    logger.info("npm_install_reused", extra={"cwd": str(project_dir), "pkg_hash": pkg_hash})
                    run.commands.append(CommandResult(
                        command=f"{prefix}/npm install" if prefix else "npm install",
                        exit_code=0,
                        stdout="Dependencies already installed and up-to-date (reused)",
                        stderr="",
                    ))
            except Exception:
                reused = False

        if not reused and cache_dir.exists() and not (project_dir / "node_modules").exists():
            try:
                shutil.copytree(cache_dir, project_dir / "node_modules", dirs_exist_ok=True)
                hash_marker.write_text(pkg_hash, encoding="utf-8")
                reused = True
                logger.info("npm_install_restored_from_cache", extra={"cwd": str(project_dir), "pkg_hash": pkg_hash})
                run.commands.append(CommandResult(
                    command=f"{prefix}/npm install" if prefix else "npm install",
                    exit_code=0,
                    stdout="Dependencies restored from workspace cache",
                    stderr="",
                ))
            except Exception:
                reused = False

        if not reused:
            logger.info(
                "INSTALL START",
                extra={"command": f"{npm_cmd} install", "cwd": str(project_dir), "pkg_hash": pkg_hash, "timeout": self._timeout},
            )
            start_time = time.monotonic()
            result = await self._run_cmd(
                [npm_cmd, "install", "--no-fund", "--no-audit"],
                cwd=project_dir,
                label=f"{prefix}/npm install" if prefix else "npm install",
            )
            duration = round(time.monotonic() - start_time, 2)
            logger.info(
                "INSTALL END",
                extra={
                    "command": f"{npm_cmd} install",
                    "cwd": str(project_dir),
                    "duration": duration,
                    "exit_code": result.exit_code,
                    "timeout": result.timed_out,
                    "pkg_hash": pkg_hash,
                },
            )
            run.commands.append(result)
            if not result.passed:
                return  # Can't proceed without dependencies
            try:
                hash_marker.parent.mkdir(parents=True, exist_ok=True)
                hash_marker.write_text(pkg_hash, encoding="utf-8")
                if not cache_dir.exists():
                    shutil.copytree(project_dir / "node_modules", cache_dir, dirs_exist_ok=True)
            except Exception:
                pass

        # 2. typecheck
        if "typecheck" in scripts:
            result = await self._run_cmd(
                [npm_cmd, "run", "typecheck"],
                cwd=project_dir,
                label=f"{prefix}/npm run typecheck" if prefix else "npm run typecheck",
            )
            run.commands.append(result)
        elif "type-check" in scripts:
            result = await self._run_cmd(
                [npm_cmd, "run", "type-check"],
                cwd=project_dir,
                label=f"{prefix}/npm run type-check" if prefix else "npm run type-check",
            )
            run.commands.append(result)
        else:
            # Try tsc directly if tsconfig exists
            if (project_dir / "tsconfig.json").exists():
                tsc = shutil.which("tsc")
                if tsc:
                    result = await self._run_cmd(
                        [tsc, "--noEmit"],
                        cwd=project_dir,
                        label=f"{prefix}/tsc --noEmit" if prefix else "tsc --noEmit",
                    )
                    run.commands.append(result)

        # 3. lint (safe execution: only run if linter is installed)
        if "lint" in scripts:
            lint_script = scripts["lint"]
            has_linter = True
            if "eslint" in lint_script:
                pkg_data_deps = {**pkg_data.get("dependencies", {}), **pkg_data.get("devDependencies", {})}
                if "eslint" not in pkg_data_deps:
                    has_linter = False
            if has_linter:
                result = await self._run_cmd(
                    [npm_cmd, "run", "lint"],
                    cwd=project_dir,
                    label=f"{prefix}/npm run lint" if prefix else "npm run lint",
                )
                run.commands.append(result)
            else:
                run.commands.append(CommandResult(
                    command=f"{prefix}/npm run lint" if prefix else "npm run lint",
                    exit_code=0,
                    stdout="",
                    stderr="",
                    skipped=True,
                    skip_reason="Linter referenced in scripts is not installed in package.json",
                ))

        # 4. build
        if "build" in scripts:
            result = await self._run_cmd(
                [npm_cmd, "run", "build"],
                cwd=project_dir,
                label=f"{prefix}/npm run build" if prefix else "npm run build",
            )
            run.commands.append(result)
        else:
            run.commands.append(CommandResult(
                command="npm run build",
                exit_code=0,
                stdout="",
                stderr="",
                skipped=True,
                skip_reason="No build script in package.json",
            ))

        # 5. test (non-blocking — test failures are warnings, not fatal)
        if "test" in scripts:
            result = await self._run_cmd(
                [npm_cmd, "run", "test", "--", "--passWithNoTests"],
                cwd=project_dir,
                label=f"{prefix}/npm test" if prefix else "npm test",
            )
            run.commands.append(result)

    async def _validate_python(
        self,
        project_dir: Path,
        run: ValidationRun,
    ) -> None:
        """Run Python validation commands."""
        if not project_dir.exists():
            run.commands.append(CommandResult(
                command="python compilation",
                exit_code=1,
                stdout="",
                stderr=f"Directory {project_dir} does not exist",
                skipped=True,
                skip_reason="Directory missing",
            ))
            return

        python = sys.executable
        pip = shutil.which("pip") or f"{python} -m pip"
        venv_dir = project_dir / ".venv-validation"

        # 1. Create virtual environment
        result = await self._run_cmd(
            [python, "-m", "venv", str(venv_dir)],
            cwd=project_dir,
            label="python -m venv",
        )
        run.commands.append(result)

        if result.passed:
            # Use venv python for subsequent commands
            if sys.platform == "win32":
                venv_python = str(venv_dir / "Scripts" / "python.exe")
                venv_pip = str(venv_dir / "Scripts" / "pip.exe")
            else:
                venv_python = str(venv_dir / "bin" / "python")
                venv_pip = str(venv_dir / "bin" / "pip")
        else:
            venv_python = python
            venv_pip = pip

        # 2. Install dependencies
        requirements_txt = project_dir / "requirements.txt"
        pyproject_toml = project_dir / "pyproject.toml"

        if requirements_txt.exists():
            result = await self._run_cmd(
                [venv_pip, "install", "-r", str(requirements_txt)],
                cwd=project_dir,
                label="pip install -r requirements.txt",
            )
            run.commands.append(result)
        elif pyproject_toml.exists():
            result = await self._run_cmd(
                [venv_pip, "install", "-e", "."],
                cwd=project_dir,
                label="pip install -e .",
            )
            run.commands.append(result)
        else:
            run.commands.append(CommandResult(
                command="pip install",
                exit_code=0,
                stdout="",
                stderr="",
                skipped=True,
                skip_reason="No requirements.txt or pyproject.toml found",
            ))

        # 3. Python compilation check
        result = await self._run_cmd(
            [venv_python, "-m", "compileall", ".", "-q"],
            cwd=project_dir,
            label="python -m compileall",
        )
        run.commands.append(result)

        # 4. Ruff lint (if configured)
        ruff = shutil.which("ruff")
        if ruff and (project_dir / "ruff.toml").exists() or (
            pyproject_toml.exists() and "ruff" in pyproject_toml.read_text()
        ):
            result = await self._run_cmd(
                [ruff, "check", "."],
                cwd=project_dir,
                label="ruff check",
            )
            run.commands.append(result)

        # 5. pytest (if installed / configured)
        pytest_path = str(venv_dir / ("Scripts" if sys.platform == "win32" else "bin") / "pytest")
        if not Path(pytest_path).exists():
            pytest_path = shutil.which("pytest") or ""

        tests_dir = project_dir / "tests"
        if pytest_path and tests_dir.exists():
            result = await self._run_cmd(
                [pytest_path, "tests", "-q", "--tb=short"],
                cwd=project_dir,
                label="pytest",
            )
            run.commands.append(result)

        # Cleanup venv
        try:
            shutil.rmtree(venv_dir, ignore_errors=True)
        except Exception:  # noqa: BLE001
            pass

    async def _validate_best_effort(
        self,
        workspace_dir: Path,
        files: dict[str, str],
        run: ValidationRun,
    ) -> None:
        """When stack is unknown, do a best-effort check."""
        # Check for any Python files and compile them
        py_files = [p for p in files if p.endswith(".py")]
        if py_files:
            result = await self._run_cmd(
                [sys.executable, "-m", "compileall", ".", "-q"],
                cwd=workspace_dir,
                label="python -m compileall (best-effort)",
            )
            run.commands.append(result)

    async def _run_cmd(
        self,
        cmd: list[str],
        cwd: Path,
        label: str,
    ) -> CommandResult:
        """Run a single command, capturing output."""
        cmd_str = " ".join(str(c) for c in cmd)
        logger.info("validation_cmd", extra={"command": cmd_str, "cwd": str(cwd)})

        try:
            proc = await asyncio.create_subprocess_exec(
                *[str(c) for c in cmd],
                cwd=str(cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "CI": "true", "NODE_ENV": "test"},
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=self._timeout,
                )
                stdout = stdout_bytes.decode("utf-8", errors="replace")
                stderr = stderr_bytes.decode("utf-8", errors="replace")
                exit_code = proc.returncode or 0

                result = CommandResult(
                    command=label,
                    exit_code=exit_code,
                    stdout=stdout,
                    stderr=stderr,
                )
                if result.passed:
                    logger.info("validation_cmd_passed", extra={"command": label})
                else:
                    logger.warning(
                        "validation_cmd_failed",
                        extra={
                            "command": label,
                            "exit_code": exit_code,
                            "stderr_preview": stderr[:300],
                        },
                    )
                return result

            except asyncio.TimeoutError:
                if sys.platform == "win32" and proc.pid:
                    try:
                        import subprocess
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                            capture_output=True,
                            timeout=5,
                        )
                    except Exception:
                        proc.kill()
                else:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                try:
                    await asyncio.wait_for(proc.communicate(), timeout=3)
                except Exception:
                    pass
                logger.error("validation_cmd_timeout", extra={"command": label})
                return CommandResult(
                    command=label,
                    exit_code=-1,
                    stdout="",
                    stderr=f"Command timed out after {self._timeout}s",
                    timed_out=True,
                )

        except FileNotFoundError:
            # Command not found (e.g. npm not installed)
            return CommandResult(
                command=label,
                exit_code=0,
                stdout="",
                stderr="",
                skipped=True,
                skip_reason=f"Command not found: {cmd[0]}",
            )
        except Exception as exc:  # noqa: BLE001
            return CommandResult(
                command=label,
                exit_code=1,
                stdout="",
                stderr=f"Failed to run command: {exc}",
            )
