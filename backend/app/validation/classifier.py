"""Error classifier for validation failures.

Parses command output into structured ValidationFailure objects and maps
each failure to the responsible engineering agent.

A ValidationFailure is NOT "everything failed". It is the smallest unit
of fixable information: one error, its location, its category, and which
agent is responsible for fixing it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.core.enums import AgentRole
from app.validation.executor import CommandResult


@dataclass
class ValidationFailure:
    """A single classified failure from a validation command."""

    command: str
    exit_code: int
    file: str
    line: str
    error: str
    category: str  # 'type_error', 'syntax_error', 'import_error', 'test_failure',
                   # 'build_error', 'lint_error', 'install_error', 'runtime_error', 'unknown'
    responsible_agent: str  # AgentRole value
    severity: str  # 'critical', 'high', 'medium', 'low'
    raw_output: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "exit_code": self.exit_code,
            "file": self.file,
            "line": self.line,
            "error": self.error,
            "category": self.category,
            "responsible_agent": self.responsible_agent,
            "severity": self.severity,
        }


@dataclass
class ClassificationResult:
    """All failures extracted from a validation run."""

    failures: list[ValidationFailure] = field(default_factory=list)

    @property
    def has_critical(self) -> bool:
        return any(f.severity == "critical" for f in self.failures)

    @property
    def has_blocking(self) -> bool:
        return any(f.severity in ("critical", "high") for f in self.failures)

    @property
    def by_agent(self) -> dict[str, list[ValidationFailure]]:
        result: dict[str, list[ValidationFailure]] = {}
        for failure in self.failures:
            result.setdefault(failure.responsible_agent, []).append(failure)
        return result

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_failures": len(self.failures),
            "has_critical": self.has_critical,
            "has_blocking": self.has_blocking,
            "failures": [f.as_dict() for f in self.failures],
            "by_agent": {
                agent: len(failures)
                for agent, failures in self.by_agent.items()
            },
        }


# --- File path → responsible agent mapping -----------------------------------

#: Path prefixes that indicate which agent owns the file.
_PATH_AGENTS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^frontend/"), AgentRole.FRONTEND_ENGINEER.value),
    (re.compile(r"^src/"), AgentRole.FRONTEND_ENGINEER.value),  # SPA structure
    (re.compile(r"\.(tsx?|jsx?|css|scss|html|vue|svelte)$"), AgentRole.FRONTEND_ENGINEER.value),
    (re.compile(r"^backend/"), AgentRole.BACKEND_ENGINEER.value),
    (re.compile(r"\.(py)$"), AgentRole.BACKEND_ENGINEER.value),
    (re.compile(r"^database/|alembic/|migrations/|\.sql$"), AgentRole.DATABASE_ENGINEER.value),
    (re.compile(r"prisma/|schema\.prisma$"), AgentRole.DATABASE_ENGINEER.value),
    (re.compile(r"test[s]?/|\.test\.|\.spec\.|_test\."), AgentRole.QA_ENGINEER.value),
]


def _infer_agent_from_path(file_path: str) -> str:
    """Determine the responsible agent from a file path."""
    if not file_path:
        return AgentRole.BACKEND_ENGINEER.value
    for pattern, agent in _PATH_AGENTS:
        if pattern.search(file_path):
            return agent
    return AgentRole.BACKEND_ENGINEER.value


def _infer_agent_from_category(category: str, file_path: str = "") -> str:
    """Determine responsible agent from error category when path is unclear."""
    if category == "install_error":
        # Could be frontend or backend — check path
        if file_path and ("frontend" in file_path or "package.json" in file_path):
            return AgentRole.FRONTEND_ENGINEER.value
        return AgentRole.BACKEND_ENGINEER.value
    if category in ("test_failure", "test_infrastructure"):
        return AgentRole.QA_ENGINEER.value
    if category == "schema_error":
        return AgentRole.DATABASE_ENGINEER.value
    if category in ("type_error", "lint_error", "syntax_error"):
        return _infer_agent_from_path(file_path)
    if category in ("build_error",):
        return _infer_agent_from_path(file_path)
    return AgentRole.IMPROVEMENT_ENGINEER.value


# --- Error parsers -----------------------------------------------------------

# TypeScript error: src/foo.ts(10,5): error TS2304: Cannot find name 'X'.
_TS_ERROR = re.compile(
    r"(?P<file>[^\s(]+\.tsx?)\((?P<line>\d+),\d+\):\s+error\s+(?P<code>TS\d+):\s*(?P<msg>.+)"
)

# Python error: File "foo.py", line 10, in ...  / SyntaxError: ...
_PY_SYNTAX = re.compile(
    r'File "(?P<file>[^"]+)", line (?P<line>\d+)'
)
_PY_IMPORT = re.compile(
    r"(?:ModuleNotFoundError|ImportError):\s+(?P<msg>.+)"
)
_PY_ERROR = re.compile(
    r"(?P<etype>\w+Error):\s+(?P<msg>.+)"
)

# ESLint: /path/to/file.ts  10:5  error  no-undef
_ESLINT = re.compile(
    r"(?P<file>[^\s]+\.(tsx?|jsx?))\s+(?P<line>\d+):\d+\s+(?P<severity>error|warning)\s+(?P<msg>.+)"
)

# pytest: FAILED tests/test_foo.py::test_bar - AssertionError
_PYTEST_FAIL = re.compile(
    r"FAILED\s+(?P<file>[^\s:]+)::(?P<test>[^\s]+)"
)

# npm/node generic error: Error: ...
_NPM_ERROR = re.compile(r"(?:npm ERR!|Error:)\s+(?P<msg>.+)")


def classify_failures(commands: list[CommandResult]) -> ClassificationResult:
    """Parse all failed commands into structured ValidationFailure objects."""
    result = ClassificationResult()

    for cmd in commands:
        if cmd.passed or cmd.skipped:
            continue

        output = cmd.output
        failures = _parse_command(cmd, output)
        result.failures.extend(failures)

    return result


def _parse_command(cmd: CommandResult, output: str) -> list[ValidationFailure]:
    """Extract failures from a single failed command."""
    failures: list[ValidationFailure] = []
    label = cmd.command.lower()

    if "typecheck" in label or "tsc" in label:
        failures.extend(_parse_typescript(cmd, output))
    elif "lint" in label or "eslint" in label or "ruff" in label:
        failures.extend(_parse_lint(cmd, output))
    elif "build" in label:
        failures.extend(_parse_build(cmd, output))
    elif "test" in label or "pytest" in label:
        failures.extend(_parse_tests(cmd, output))
    elif "install" in label or "pip install" in label:
        failures.extend(_parse_install(cmd, output))
    elif "compileall" in label:
        failures.extend(_parse_python_compile(cmd, output))
    else:
        # Generic fallback
        if not failures:
            failures.append(ValidationFailure(
                command=cmd.command,
                exit_code=cmd.exit_code,
                file="",
                line="",
                error=output[:500] if output else f"Command failed with exit code {cmd.exit_code}",
                category="unknown",
                responsible_agent=AgentRole.IMPROVEMENT_ENGINEER.value,
                severity="high",
                raw_output=output,
            ))

    return failures


def _parse_typescript(cmd: CommandResult, output: str) -> list[ValidationFailure]:
    """Parse TypeScript compiler errors."""
    failures = []
    for match in _TS_ERROR.finditer(output):
        file_path = match.group("file")
        agent = _infer_agent_from_path(file_path)
        code = match.group("code")
        # Critical TS errors
        severity = "critical" if code in {"TS2307", "TS2304", "TS2305"} else "high"
        failures.append(ValidationFailure(
            command=cmd.command,
            exit_code=cmd.exit_code,
            file=file_path,
            line=match.group("line"),
            error=f"{code}: {match.group('msg')}",
            category="type_error",
            responsible_agent=agent,
            severity=severity,
            raw_output=output,
        ))

    if not failures and cmd.exit_code != 0:
        failures.append(ValidationFailure(
            command=cmd.command,
            exit_code=cmd.exit_code,
            file="",
            line="",
            error=output[:500] if output else "TypeScript compilation failed",
            category="type_error",
            responsible_agent=AgentRole.FRONTEND_ENGINEER.value,
            severity="critical",
            raw_output=output,
        ))
    return failures


def _parse_lint(cmd: CommandResult, output: str) -> list[ValidationFailure]:
    """Parse lint errors (ESLint, ruff)."""
    failures = []
    for match in _ESLINT.finditer(output):
        file_path = match.group("file")
        agent = _infer_agent_from_path(file_path)
        failures.append(ValidationFailure(
            command=cmd.command,
            exit_code=cmd.exit_code,
            file=file_path,
            line=match.group("line"),
            error=match.group("msg").strip(),
            category="lint_error",
            responsible_agent=agent,
            severity="medium",
            raw_output=output,
        ))

    if not failures and cmd.exit_code != 0:
        failures.append(ValidationFailure(
            command=cmd.command,
            exit_code=cmd.exit_code,
            file="",
            line="",
            error=output[:500] if output else "Lint check failed",
            category="lint_error",
            responsible_agent=AgentRole.IMPROVEMENT_ENGINEER.value,
            severity="medium",
            raw_output=output,
        ))
    return failures


def _parse_build(cmd: CommandResult, output: str) -> list[ValidationFailure]:
    """Parse build errors (vite build, webpack, etc.)."""
    failures = []
    # TypeScript errors in build output
    ts_failures = _parse_typescript(cmd, output)
    if ts_failures:
        return ts_failures

    # Generic build failure
    if cmd.exit_code != 0:
        file_path = ""
        # Try to find a file reference
        for line in output.splitlines():
            if "error" in line.lower() and ("/" in line or "\\" in line):
                file_path = line.strip()[:100]
                break
        agent = _infer_agent_from_path(file_path) if file_path else AgentRole.FRONTEND_ENGINEER.value
        failures.append(ValidationFailure(
            command=cmd.command,
            exit_code=cmd.exit_code,
            file=file_path,
            line="",
            error=output[:500] if output else "Build failed",
            category="build_error",
            responsible_agent=agent,
            severity="critical",
            raw_output=output,
        ))
    return failures


def _parse_tests(cmd: CommandResult, output: str) -> list[ValidationFailure]:
    """Parse test failures (pytest, jest, vitest)."""
    failures = []
    for match in _PYTEST_FAIL.finditer(output):
        file_path = match.group("file")
        failures.append(ValidationFailure(
            command=cmd.command,
            exit_code=cmd.exit_code,
            file=file_path,
            line="",
            error=f"Test failed: {match.group('test')}",
            category="test_failure",
            responsible_agent=AgentRole.QA_ENGINEER.value,
            severity="high",
            raw_output=output,
        ))

    if not failures and cmd.exit_code != 0:
        failures.append(ValidationFailure(
            command=cmd.command,
            exit_code=cmd.exit_code,
            file="",
            line="",
            error=output[:500] if output else "Tests failed",
            category="test_failure",
            responsible_agent=AgentRole.QA_ENGINEER.value,
            severity="high",
            raw_output=output,
        ))
    return failures


def _parse_install(cmd: CommandResult, output: str) -> list[ValidationFailure]:
    """Parse dependency installation failures."""
    if cmd.exit_code != 0:
        agent = (
            AgentRole.FRONTEND_ENGINEER.value
            if "npm" in cmd.command
            else AgentRole.BACKEND_ENGINEER.value
        )
        return [ValidationFailure(
            command=cmd.command,
            exit_code=cmd.exit_code,
            file="package.json" if "npm" in cmd.command else "requirements.txt",
            line="",
            error=output[:500] if output else "Dependency installation failed",
            category="install_error",
            responsible_agent=agent,
            severity="critical",
            raw_output=output,
        )]
    return []


def _parse_python_compile(cmd: CommandResult, output: str) -> list[ValidationFailure]:
    """Parse Python compilation errors."""
    failures = []
    current_file = ""

    for line in output.splitlines():
        m = _PY_SYNTAX.search(line)
        if m:
            current_file = m.group("file")
            continue

        m_err = _PY_ERROR.search(line)
        if m_err and current_file:
            agent = _infer_agent_from_path(current_file)
            failures.append(ValidationFailure(
                command=cmd.command,
                exit_code=cmd.exit_code,
                file=current_file,
                line="",
                error=f"{m_err.group('etype')}: {m_err.group('msg')}",
                category="syntax_error",
                responsible_agent=agent,
                severity="critical",
                raw_output=output,
            ))
            current_file = ""

    if not failures and cmd.exit_code != 0:
        failures.append(ValidationFailure(
            command=cmd.command,
            exit_code=cmd.exit_code,
            file="",
            line="",
            error=output[:500] if output else "Python compilation failed",
            category="syntax_error",
            responsible_agent=AgentRole.BACKEND_ENGINEER.value,
            severity="critical",
            raw_output=output,
        ))
    return failures
