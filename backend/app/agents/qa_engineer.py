"""QA Engineer agent.

Version 2: Runs REAL commands against the generated workspace as the primary
validation gate. LLM-generated test files are a secondary artifact.

Validation pipeline:
1. Structural checks (fast, free, deterministic)
2. Real command execution: npm install / typecheck / lint / build / pytest
3. Error classification into structured ValidationFailure objects
4. Store results in SharedProjectMemory.validation_runs
5. If failures detected → return them so the repair loop can act

Only if real validation PASSES does the run proceed to Review/Improvement.
The QA Engineer does NOT accept an LLM's claim that "it should work".
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from app.agents.base import CodeAgent
from app.agents.context import AgentContext
from app.agents.results import AgentResult, SkipDecision
from app.core.enums import AgentRole, ArtifactKind, LogLevel
from app.llm import schema as s
from app.validation.classifier import classify_failures
from app.validation.executor import WorkspaceValidator
from app.workflow.memory import ValidationResult

TEST_PLAN_SCHEMA = s.obj(
    {
        "files": s.array(
            s.obj(
                {
                    "path": s.string("Repository-relative test file path."),
                    "content": s.string("Complete, runnable test file."),
                    "description": s.string("What this file tests."),
                }
            ),
            description="Unit test files.",
        ),
        "coverage_notes": s.string("What is covered and what is deliberately not."),
        "manual_checks": s.string_array(
            "Checks a human should perform that automated tests cannot cover."
        ),
    }
)


class QAEngineerAgent(CodeAgent):
    role = AgentRole.QA_ENGINEER
    display_name = "QA Engineer"
    description = (
        "Validates project structure AND runs real build/test commands. "
        "Only passes if the project actually builds and tests pass."
    )
    depends_on = (AgentRole.BACKEND_ENGINEER, AgentRole.FRONTEND_ENGINEER)

    def should_execute(self, ctx: AgentContext) -> SkipDecision:
        if len(ctx.memory.workspace) == 0:
            return SkipDecision.skip("No source files were generated, so there is nothing to test.")
        return SkipDecision.run()

    def system_prompt(self, ctx: AgentContext) -> str:
        return """\
ROLE: QA Engineer

You write the tests that prove the generated project works, and you verify that \
its pieces actually fit together.

## What to test

Test behaviour, not implementation. A test that asserts a function calls \
another function is worthless; a test that asserts the function returns the \
right answer for a given input is valuable.

Priorities, in order:
1. Business logic in services — the code most likely to be wrong.
2. Validation — both that valid input is accepted and that invalid input is \
rejected with the right error.
3. API endpoints — status codes and response shapes for success and failure.
4. Edge cases the requirements imply: empty collections, boundary values, \
missing optional fields, unauthorised access.

## Test quality

- Each test has one clear reason to fail. Its name states what it asserts.
- Arrange / Act / Assert, in that order, visibly separated.
- Tests are independent and can run in any order. No test depends on another \
having run first.
- No network calls, no real database, no sleeping. Substitute dependencies at \
the boundary.
- Use the test framework already configured in the project's manifest.

A test that cannot fail is worse than no test: it produces false confidence. \
Never write an assertion that is true by construction."""

    async def execute(self, ctx: AgentContext) -> AgentResult:
        await ctx.progress(self.role, 5, "Running structural validation")

        # 1. Structural checks (fast, free)
        structural_findings = self._validate_structure(ctx)
        for finding in structural_findings:
            await ctx.log(self.role, finding, level=LogLevel.WARNING)
        if not structural_findings:
            await ctx.log(self.role, "Structural validation passed with no findings")

        await ctx.progress(self.role, 20, "Running real execution validation")

        # 2. Real execution validation
        validation_result = await self._run_execution_validation(ctx)
        ctx.memory.record_validation_run(validation_result)

        if not validation_result.passed:
            await ctx.log(
                self.role,
                f"Execution validation FAILED: {validation_result.failed_commands} "
                f"command(s) failed. Starting automatic repair loop.",
                level=LogLevel.WARNING,
            )
            from app.validation.repair import run_repair_loop
            validation_result = await run_repair_loop(ctx, validation_result)
            ctx.memory.record_validation_run(validation_result)
        else:
            await ctx.log(
                self.role,
                f"Execution validation PASSED: {validation_result.total_commands} commands OK",
            )

        await ctx.progress(self.role, 55, "Writing unit tests")

        # 3. Generate test files (regardless of validation result — they help repair)
        target = self._test_target(ctx)
        completion = await ctx.llm.complete_structured(
            self.build_prompt(
                ctx,
                instruction=(
                    "Write unit tests for the generated project.\n\n"
                    f"PROJECT GOAL: {ctx.memory.idea or ctx.memory.user_prompt or ''}\n\n"
                    f"{target}\n\n"
                    "Produce 4 to 10 focused test files covering the highest-value "
                    "behaviour. Every test must be complete and runnable with the "
                    "framework already configured in the project. Do not test "
                    "framework internals or scaffold configuration."
                ),
                schema=TEST_PLAN_SCHEMA,
                max_tokens=28000,
            )
        )

        files = completion.data.get("files", [])
        sanitized_files = []
        for file_spec in files:
            path = str(file_spec.get("path", ""))
            content = str(file_spec.get("content", ""))
            desc = str(file_spec.get("description", ""))
            if ("tasks.js" in content) and not ctx.memory.workspace.exists("frontend/js/tasks.js"):
                if ctx.memory.workspace.exists("frontend/js/app.js"):
                    content = content.replace("../js/tasks.js", "../js/app.js").replace("./tasks.js", "./app.js")
            sanitized_files.append({"path": path, "content": content, "description": desc})

        accepted, rejected = ctx.memory.workspace.write_many(sanitized_files, produced_by=self.role)

        warnings = structural_findings + [f"Rejected {r['path']}: {r['reason']}" for r in rejected]

        # Add validation failures to warnings
        if not validation_result.passed:
            for failure in validation_result.failures[:5]:
                cmd = failure.get("command", "")
                err = failure.get("error", "")
                warnings.append(f"EXECUTION FAILURE [{cmd}]: {err[:200]}")

        manual_checks = completion.data.get("manual_checks", [])
        ctx.memory.test_plan = {
            "test_files": len(accepted),
            "coverage_notes": completion.data.get("coverage_notes", ""),
            "manual_checks": manual_checks,
            "structural_findings": structural_findings,
            "execution_validation": validation_result.as_dict(),
        }

        confidence = self._confidence(len(accepted), structural_findings, validation_result)
        ctx.memory.record_confidence("quality", confidence)

        status = "PASSED" if validation_result.passed else "FAILED"
        summary = (
            f"Execution validation {status}; "
            f"{len(accepted)} test files written; "
            f"{len(structural_findings)} structural finding(s)."
        )
        ctx.memory.record_summary(self.role, summary)
        await ctx.progress(self.role, 100, "QA complete")

        return AgentResult(
            role=self.role,
            summary=summary,
            output={
                "test_files": len(accepted),
                "structural_findings": structural_findings,
                "manual_checks": manual_checks,
                "coverage_notes": completion.data.get("coverage_notes", ""),
                "artifact_kind": ArtifactKind.TESTS.value,
                "execution_validation": validation_result.as_dict(),
                "validation_passed": validation_result.passed,
            },
            usage=completion.usage,
            files_produced=len(accepted),
            confidence=confidence,
            warnings=warnings,
        )

    # --- real execution validation ---------------------------------------

    async def _run_execution_validation(self, ctx: AgentContext) -> ValidationResult:
        """Run actual build/test commands against the workspace files."""
        workspace = ctx.memory.workspace

        # Build file dict from workspace
        files: dict[str, str] = {}
        for entry in workspace.files:
            if entry.content:
                files[entry.path] = entry.content

        if not files:
            return ValidationResult(
                passed=True,  # Nothing to validate
                stack="empty",
                timestamp=datetime.now(UTC).isoformat(),
            )

        try:
            validator = WorkspaceValidator(timeout_seconds=120)
            run = await validator.validate(files, run_id=ctx.memory.run_id)

            # Classify failures
            classification = classify_failures(run.commands)

            return ValidationResult(
                passed=run.passed,
                stack=run.stack,
                total_commands=run.total_commands,
                failed_commands=len(run.failed_commands),
                failures=[f.as_dict() for f in classification.failures],
                timestamp=datetime.now(UTC).isoformat(),
                workspace_fingerprint=workspace.fingerprint,
            )

        except Exception as exc:  # noqa: BLE001
            err_msg = f"Validation executor error: {type(exc).__name__}: {exc}"
            await ctx.log(
                self.role,
                err_msg,
                level=LogLevel.ERROR,
            )
            return ValidationResult(
                passed=False,
                stack="unknown",
                total_commands=1,
                failed_commands=1,
                failures=[
                    {
                        "command": "qa_execution_validation",
                        "exit_code": 1,
                        "file": "N/A",
                        "line": "N/A",
                        "error": err_msg,
                        "category": "runtime_error",
                        "responsible_agent": AgentRole.QA_ENGINEER.value,
                        "severity": "critical",
                    }
                ],
                timestamp=datetime.now(UTC).isoformat(),
                workspace_fingerprint=workspace.fingerprint,
            )

    # --- deterministic structural checks --------------------------------

    def _validate_structure(self, ctx: AgentContext) -> list[str]:
        """Checks that need no model call and cannot produce a false positive."""
        memory = ctx.memory
        workspace = memory.workspace
        findings: list[str] = []

        if memory.needs_backend and not workspace.under("backend"):
            findings.append("Backend was required but no files exist under `backend/`.")
        if memory.needs_frontend and not workspace.under("frontend"):
            findings.append("Frontend was required but no files exist under `frontend/`.")
        if memory.needs_database and memory.tech_stack.database:
            adapter = ctx.registry.database(memory.tech_stack.database)
            schema_path = f"database/{adapter.schema_filename}"
            if not workspace.exists(schema_path):
                findings.append(f"Database was required but `{schema_path}` is missing.")

        findings.extend(self._check_endpoint_coverage(ctx))
        findings.extend(self._check_placeholders(ctx))
        findings.extend(self._check_orphan_config(ctx))

        return findings

    @staticmethod
    def _check_endpoint_coverage(ctx: AgentContext) -> list[str]:
        """Every contracted endpoint path should appear in backend source."""
        endpoints = ctx.memory.architecture.api_endpoints
        backend_files = ctx.memory.workspace.under("backend")
        if not endpoints or not backend_files:
            return []

        haystack = "\n".join(f.content for f in backend_files)
        missing: list[str] = []
        for endpoint in endpoints:
            path = str(endpoint.get("path", ""))
            if not path:
                continue
            segments = [seg for seg in path.split("/") if seg and not seg.startswith(("{", ":"))]
            if not segments:
                continue
            if segments[-1] not in haystack:
                missing.append(f"{endpoint.get('method', 'GET')} {path}")

        if not missing:
            return []
        listed = ", ".join(missing[:6])
        suffix = f" (+{len(missing) - 6} more)" if len(missing) > 6 else ""
        return [
            f"No backend code found for {len(missing)} contracted "
            f"endpoint(s): {listed}{suffix}"
        ]

    @staticmethod
    def _check_placeholders(ctx: AgentContext) -> list[str]:
        """Detect stubbed implementations that slipped through, with file-type awareness."""
        general_patterns = (
            (re.compile(r"\bTODO\b|\bFIXME\b"), "TODO/FIXME marker"),
            (re.compile(r"not\s+implemented", re.IGNORECASE), "'not implemented'"),
            (
                re.compile(r"your[-_ ]?(api[-_ ]?key|secret|token)", re.IGNORECASE),
                "placeholder secret",
            ),
        )
        python_empty_body = re.compile(r"^\s*(pass|\.\.\.)\s*$", re.MULTILINE)

        offenders: dict[str, set[str]] = {}
        workspace = ctx.memory.workspace

        for entry in workspace.files:
            if entry.path.endswith((".md", ".txt", ".example", ".json", ".lock", ".gitignore")):
                continue

            content = entry.content

            # Empty file check
            if not content.strip():
                offenders.setdefault("empty file (0 bytes)", set()).add(entry.path)
                continue

            # General marker checks
            for pattern, label in general_patterns:
                if pattern.search(content):
                    offenders.setdefault(label, set()).add(entry.path)

            # Python-specific empty body check — NEVER run on HTML/CSS/JS
            if entry.path.endswith(".py"):
                if python_empty_body.search(content):
                    offenders.setdefault("empty Python body", set()).add(entry.path)

            # HTML-specific structural checks
            elif entry.path.endswith(".html"):
                lower = content.lower()
                if "<html" not in lower and "<!doctype html" not in lower:
                    offenders.setdefault("missing HTML document root", set()).add(entry.path)
                if "<body" not in lower:
                    offenders.setdefault("missing HTML body", set()).add(entry.path)
                if re.search(r"<body[^>]*>\s*</body>", content, re.IGNORECASE):
                    offenders.setdefault("empty HTML body", set()).add(entry.path)

            # CSS-specific structural checks
            elif entry.path.endswith(".css"):
                if "{" not in content or "}" not in content:
                    offenders.setdefault("missing CSS style rules", set()).add(entry.path)
                elif content.count("{") != content.count("}"):
                    offenders.setdefault("mismatched CSS braces", set()).add(entry.path)

            # JavaScript-specific structural checks
            elif entry.path.endswith((".js", ".mjs")):
                if content.count("{") != content.count("}"):
                    offenders.setdefault("mismatched JavaScript braces", set()).add(entry.path)
                if content.count("(") != content.count(")"):
                    offenders.setdefault("mismatched JavaScript parentheses", set()).add(entry.path)

        findings = []
        for label, paths in offenders.items():
            sample = ", ".join(sorted(paths)[:3])
            extra = f" (+{len(paths) - 3} more)" if len(paths) > 3 else ""
            findings.append(f"Found {label} in {len(paths)} file(s): {sample}{extra}")
        return findings

    @staticmethod
    def _check_orphan_config(ctx: AgentContext) -> list[str]:
        """A manifest with no source beside it means generation stopped early."""
        workspace = ctx.memory.workspace
        findings = []
        is_vanilla_frontend = (
            ctx.memory.tech_stack.frontend == "html_css_js"
        )

        for manifest, source_prefix, label in (
            ("backend/package.json", "backend/src", "backend"),
            ("frontend/package.json", "frontend/src", "frontend"),
        ):
            if label == "frontend" and is_vanilla_frontend:
                # Vanilla HTML/CSS/JS puts files in frontend/ directly (index.html, css/, js/)
                # Do NOT require frontend/src/
                has_vanilla_sources = (
                    workspace.exists("frontend/index.html")
                    or bool(workspace.under("frontend/js"))
                    or bool(workspace.under("frontend/css"))
                )
                if workspace.exists(manifest) and not has_vanilla_sources:
                    findings.append(
                        f"`{manifest}` exists but no HTML/CSS/JS files exist under `frontend/`."
                    )
            else:
                if workspace.exists(manifest) and not workspace.under(source_prefix):
                    findings.append(
                        f"`{manifest}` exists but `{source_prefix}/` is empty — "
                        f"{label} source generation appears incomplete."
                    )
        return findings

    @staticmethod
    def _test_target(ctx: AgentContext) -> str:
        workspace = ctx.memory.workspace
        candidates = [
            f
            for f in workspace.files
            if any(
                marker in f.path
                for marker in ("service", "repositor", "controller", "route", "util", "hook")
            )
            and not f.path.endswith((".json", ".md", ".yml", ".yaml"))
        ][:25]

        if not candidates:
            source_extensions = {".py", ".ts", ".tsx", ".java", ".js"}
            candidates = [
                f for f in workspace.files if f.extension in source_extensions
            ][:20]

        listing = "\n".join(
            f"- {f.path} — {f.description or 'no description'}" for f in candidates
        )
        return f"FILES MOST WORTH TESTING:\n{listing}"

    @staticmethod
    def _confidence(
        test_files: int, findings: list[str], validation: ValidationResult
    ) -> float:
        base = min(test_files / 6.0, 1.0)
        structural_penalty = min(len(findings) * 0.08, 0.3)
        execution_penalty = 0.0 if validation.passed else 0.4
        return round(max(0.0, base - structural_penalty - execution_penalty), 3)
