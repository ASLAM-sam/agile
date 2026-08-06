"""QA Engineer agent.

Runs deterministic structural validation first, then generates unit tests.
Structural checks catch the failures that matter most — a frontend calling an
endpoint the backend never implemented — and they cost nothing to run.
"""

from __future__ import annotations

import re

from app.agents.base import CodeAgent
from app.agents.context import AgentContext
from app.agents.results import AgentResult, SkipDecision
from app.core.enums import AgentRole, ArtifactKind, LogLevel
from app.llm import schema as s

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
        "Validates project structure and API coverage, then writes unit tests "
        "for the generated code."
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
- Use the test framework already configured in the project's manifest. Do not \
introduce a new one.

A test that cannot fail is worse than no test: it produces false confidence. \
Never write an assertion that is true by construction."""

    async def execute(self, ctx: AgentContext) -> AgentResult:
        await ctx.progress(self.role, 10, "Running structural validation")

        findings = self._validate_structure(ctx)
        for finding in findings:
            await ctx.log(self.role, finding, level=LogLevel.WARNING)
        if not findings:
            await ctx.log(self.role, "Structural validation passed with no findings")

        await ctx.progress(self.role, 35, "Writing unit tests")

        target = self._test_target(ctx)
        completion = await ctx.llm.complete_structured(
            self.build_prompt(
                ctx,
                instruction=(
                    "Write unit tests for the generated project.\n\n"
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

        await ctx.progress(self.role, 80, "Recording the test suite")

        files = completion.data.get("files", [])
        accepted, rejected = ctx.memory.workspace.write_many(files, produced_by=self.role)

        warnings = findings + [f"Rejected {r['path']}: {r['reason']}" for r in rejected]

        manual_checks = completion.data.get("manual_checks", [])
        ctx.memory.test_plan = {
            "test_files": len(accepted),
            "coverage_notes": completion.data.get("coverage_notes", ""),
            "manual_checks": manual_checks,
            "structural_findings": findings,
        }

        confidence = self._confidence(len(accepted), findings)
        ctx.memory.record_confidence("quality", confidence)

        summary = (
            f"{len(accepted)} test files written; "
            f"{len(findings)} structural finding(s)."
        )
        ctx.memory.record_summary(self.role, summary)
        await ctx.progress(self.role, 100, "Quality verification complete")

        return AgentResult(
            role=self.role,
            summary=summary,
            output={
                "test_files": len(accepted),
                "structural_findings": findings,
                "manual_checks": manual_checks,
                "coverage_notes": completion.data.get("coverage_notes", ""),
                "artifact_kind": ArtifactKind.TESTS.value,
            },
            usage=completion.usage,
            files_produced=len(accepted),
            confidence=confidence,
            warnings=warnings,
        )

    # --- deterministic validation ---------------------------------------

    def _validate_structure(self, ctx: AgentContext) -> list[str]:
        """Checks that need no model call and cannot produce a false positive."""
        memory = ctx.memory
        workspace = memory.workspace
        findings: list[str] = []

        if memory.needs_backend and not workspace.under("backend"):
            findings.append("Backend was required but no files exist under `backend/`.")
        if memory.needs_frontend and not workspace.under("frontend"):
            findings.append("Frontend was required but no files exist under `frontend/`.")
        if memory.needs_database and not workspace.exists("database/schema.sql"):
            findings.append("Database was required but `database/schema.sql` is missing.")

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
            # Compare on the final static segment; frameworks rewrite prefixes
            # and parameter syntax differs ({id} vs :id), so a literal match on
            # the full path would report false positives.
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
        """Detect stubbed implementations that slipped through."""
        patterns = (
            (re.compile(r"\bTODO\b|\bFIXME\b"), "TODO/FIXME marker"),
            (re.compile(r"not\s+implemented", re.IGNORECASE), "'not implemented'"),
            (re.compile(r"^\s*(pass|\.\.\.)\s*$", re.MULTILINE), "empty Python body"),
            (
                re.compile(r"your[-_ ]?(api[-_ ]?key|secret|token)", re.IGNORECASE),
                "placeholder secret",
            ),
        )
        offenders: dict[str, set[str]] = {}
        for entry in ctx.memory.workspace.files:
            if entry.path.endswith((".md", ".txt", ".example")):
                continue
            for pattern, label in patterns:
                if pattern.search(entry.content):
                    offenders.setdefault(label, set()).add(entry.path)

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
        for manifest, source_prefix, label in (
            ("backend/package.json", "backend/src", "backend"),
            ("frontend/package.json", "frontend/src", "frontend"),
        ):
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
            source_extensions = {".py", ".ts", ".tsx", ".java"}
            candidates = [
                f for f in workspace.files if f.extension in source_extensions
            ][:20]

        listing = "\n".join(f"- {f.path} — {f.description or 'no description'}" for f in candidates)
        return f"FILES MOST WORTH TESTING:\n{listing}"

    @staticmethod
    def _confidence(test_files: int, findings: list[str]) -> float:
        base = min(test_files / 6.0, 1.0)
        penalty = min(len(findings) * 0.12, 0.5)
        return round(max(0.0, base - penalty), 3)
