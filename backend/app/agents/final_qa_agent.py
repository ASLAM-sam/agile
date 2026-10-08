"""Final QA Agent.

Runs after Improvement Engineer to independently validate the final
workspace state. This is mandatory — Improvement Engineer could have
introduced regressions.

Unlike the initial QA Engineer, Final QA:
1. Does NOT regenerate test files (tests already exist)
2. DOES run the full execution validation suite again
3. Records results as the authoritative final_qa_result in memory
4. Sets memory.release_eligible = True only on PASS

The Artifact Manager checks release_eligible before producing a ZIP.
If Final QA fails, the run produces a detailed failure report instead.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.agents.base import Agent
from app.agents.context import AgentContext
from app.agents.results import AgentResult, SkipDecision
from app.core.enums import AgentRole, AgentStatus, LogLevel
import re
from app.validation.classifier import classify_failures
from app.validation.executor import WorkspaceValidator
from app.workflow.memory import ValidationResult


class FinalQAAgent(Agent):
    role = AgentRole.FINAL_QA
    display_name = "Final QA"
    description = (
        "Re-runs real execution validation after all code improvements. "
        "Only a PASS here authorises the Artifact Manager to produce a ZIP."
    )
    depends_on = (AgentRole.IMPROVEMENT_ENGINEER,)

    def system_prompt(self, ctx: AgentContext) -> str:
        # Not used — this agent makes no LLM call
        return "ROLE: Final QA (deterministic execution validation; no model call)."

    def should_execute(self, ctx: AgentContext) -> SkipDecision:
        if len(ctx.memory.workspace) == 0:
            return SkipDecision.skip("No source files — nothing to validate.")
        return SkipDecision.run()

    async def execute(self, ctx: AgentContext) -> AgentResult:
        await ctx.progress(self.role, 10, "Starting final execution validation")

        workspace = ctx.memory.workspace

        # Build file dict
        files: dict[str, str] = {
            entry.path: entry.content
            for entry in workspace.files
            if entry.content
        }

        await ctx.progress(self.role, 20, f"Validating {len(files)} files")

        validation_result = await self._run_validation(ctx, files)
        if not validation_result.passed:
            await ctx.log(
                self.role,
                f"Final validation detected {validation_result.failed_commands} failing command(s). "
                "Running final repair pass.",
                level=LogLevel.WARNING,
            )
            from app.validation.repair import run_repair_loop
            validation_result = await run_repair_loop(ctx, validation_result, max_cycles=2)

        # Enforce all hard release gates
        gate_failures = self._check_hard_release_gates(ctx, files, validation_result)
        if gate_failures:
            validation_result.passed = False
            validation_result.failed_commands = max(
                validation_result.failed_commands, len(gate_failures)
            )
            for gf in gate_failures:
                validation_result.failures.append(gf)
                await ctx.log(
                    self.role,
                    f"Release Gate FAILED [{gf['command']}]: {gf['error']}",
                    level=LogLevel.ERROR,
                )

        ctx.memory.record_final_qa(validation_result)

        await ctx.progress(self.role, 90, "Recording final QA result")

        if validation_result.passed:
            status_msg = (
                f"PASSED — {validation_result.total_commands} commands OK. "
                "Project is release-eligible."
            )
            await ctx.log(self.role, status_msg)
            confidence = 1.0
        else:
            failures_summary = "; ".join(
                f"{f.get('command', '?')}: {f.get('error', '?')[:100]}"
                for f in validation_result.failures[:3]
            )
            status_msg = (
                f"FAILED — {validation_result.failed_commands} command/gate failure(s). "
                f"ZIP release is BLOCKED. Failures: {failures_summary}"
            )
            await ctx.log(self.role, status_msg, level=LogLevel.ERROR)
            confidence = 0.0

        ctx.memory.record_confidence("final_qa", confidence)
        ctx.memory.record_summary(self.role, status_msg)

        await ctx.progress(self.role, 100, "Final QA complete")

        warnings: list[str] = []
        if not validation_result.passed:
            for failure in validation_result.failures:
                warnings.append(
                    f"[{failure.get('command', '?')}] {failure.get('responsible_agent', '?')}: "
                    f"{failure.get('error', '?')[:200]}"
                )

        return AgentResult(
            role=self.role,
            summary=status_msg,
            output={
                "passed": validation_result.passed,
                "stack": validation_result.stack,
                "total_commands": validation_result.total_commands,
                "failed_commands": validation_result.failed_commands,
                "failures": validation_result.failures,
                "release_eligible": ctx.memory.release_eligible,
            },
            confidence=confidence,
            warnings=warnings,
        )

    def _check_hard_release_gates(
        self,
        ctx: AgentContext,
        files: dict[str, str],
        validation_result: ValidationResult,
    ) -> list[dict[str, Any]]:
        """Enforce strict release gates required for project production release."""
        memory = ctx.memory
        workspace = memory.workspace
        gate_failures: list[dict[str, Any]] = []

        # Gate 1: Required applicable agents completed successfully
        if memory.needs_frontend:
            fe_status = memory.get_agent_status(AgentRole.FRONTEND_ENGINEER)
            if fe_status == AgentStatus.FAILED.value:
                err = memory.agent_errors.get(
                    AgentRole.FRONTEND_ENGINEER.value, "Frontend generation failed"
                )
                gate_failures.append({
                    "command": "release_gate_agent_status",
                    "error": f"Critical agent failure: Frontend Engineer failed ({err})",
                    "category": "agent_failure",
                    "responsible_agent": AgentRole.FRONTEND_ENGINEER.value,
                    "severity": "critical",
                })
            elif fe_status is not None and fe_status != AgentStatus.COMPLETED.value:
                gate_failures.append({
                    "command": "release_gate_agent_status",
                    "error": f"Frontend Engineer did not complete successfully (status: {fe_status})",
                    "category": "agent_failure",
                    "responsible_agent": AgentRole.FRONTEND_ENGINEER.value,
                    "severity": "critical",
                })

        if memory.needs_backend:
            be_status = memory.get_agent_status(AgentRole.BACKEND_ENGINEER)
            if be_status == AgentStatus.FAILED.value:
                err = memory.agent_errors.get(
                    AgentRole.BACKEND_ENGINEER.value, "Backend generation failed"
                )
                gate_failures.append({
                    "command": "release_gate_agent_status",
                    "error": f"Critical agent failure: Backend Engineer failed ({err})",
                    "category": "agent_failure",
                    "responsible_agent": AgentRole.BACKEND_ENGINEER.value,
                    "severity": "critical",
                })
            elif be_status is not None and be_status != AgentStatus.COMPLETED.value:
                gate_failures.append({
                    "command": "release_gate_agent_status",
                    "error": f"Backend Engineer did not complete successfully (status: {be_status})",
                    "category": "agent_failure",
                    "responsible_agent": AgentRole.BACKEND_ENGINEER.value,
                    "severity": "critical",
                })

        # Check for any other failed agents recorded in memory
        for role_name, status in memory.agent_statuses.items():
            if status == AgentStatus.FAILED.value and role_name not in {
                AgentRole.FRONTEND_ENGINEER.value,
                AgentRole.BACKEND_ENGINEER.value,
            }:
                err = memory.agent_errors.get(role_name, "failed")
                gate_failures.append({
                    "command": "release_gate_agent_status",
                    "error": f"Critical agent failure: {role_name} failed ({err})",
                    "category": "agent_failure",
                    "responsible_agent": role_name,
                    "severity": "critical",
                })

        # Gate 2: Required files exist and are non-empty
        if memory.needs_frontend:
            if memory.tech_stack.frontend == "html_css_js":
                required_files = [
                    "frontend/index.html",
                    "frontend/css/styles.css",
                    "frontend/js/app.js",
                ]
            elif memory.tech_stack.frontend == "react":
                app_path = (
                    "frontend/src/App.tsx"
                    if workspace.exists("frontend/src/App.tsx")
                    else "frontend/src/App.jsx"
                )
                required_files = [
                    "frontend/package.json",
                    "frontend/index.html",
                    app_path,
                ]
            else:
                required_files = ["frontend/package.json"]
            for req in required_files:
                if not workspace.exists(req):
                    gate_failures.append({
                        "command": "release_gate_required_files",
                        "error": f"Required frontend file missing: {req}",
                        "category": "missing_file",
                        "responsible_agent": AgentRole.FRONTEND_ENGINEER.value,
                        "severity": "critical",
                    })
                else:
                    content = workspace.read(req) or ""
                    if len(content.strip()) < 50:
                        gate_failures.append({
                            "command": "release_gate_non_empty",
                            "error": f"Required frontend file is empty or trivial: {req} (length: {len(content.strip())} chars)",
                            "category": "empty_file",
                            "responsible_agent": AgentRole.FRONTEND_ENGINEER.value,
                            "severity": "critical",
                        })

        # Gate 3: Structural validity
        if workspace.exists("frontend/index.html"):
            html_content = (workspace.read("frontend/index.html") or "").lower()
            if "<html" not in html_content and "<!doctype html" not in html_content:
                gate_failures.append({
                    "command": "release_gate_html_structure",
                    "error": "frontend/index.html lacks valid document root (<html> or <!DOCTYPE html>)",
                    "category": "invalid_structure",
                    "responsible_agent": AgentRole.FRONTEND_ENGINEER.value,
                    "severity": "critical",
                })
            if "<body" not in html_content or re.search(r"<body[^>]*>\s*</body>", html_content, re.IGNORECASE):
                gate_failures.append({
                    "command": "release_gate_html_structure",
                    "error": "frontend/index.html has missing or empty <body>",
                    "category": "invalid_structure",
                    "responsible_agent": AgentRole.FRONTEND_ENGINEER.value,
                    "severity": "critical",
                })

        if workspace.exists("frontend/css/styles.css"):
            css_content = workspace.read("frontend/css/styles.css") or ""
            if "{" not in css_content or "}" not in css_content:
                gate_failures.append({
                    "command": "release_gate_css_structure",
                    "error": "frontend/css/styles.css contains no CSS rule blocks",
                    "category": "invalid_structure",
                    "responsible_agent": AgentRole.FRONTEND_ENGINEER.value,
                    "severity": "critical",
                })
            elif css_content.count("{") != css_content.count("}"):
                gate_failures.append({
                    "command": "release_gate_css_structure",
                    "error": "frontend/css/styles.css contains mismatched braces",
                    "category": "invalid_structure",
                    "responsible_agent": AgentRole.FRONTEND_ENGINEER.value,
                    "severity": "critical",
                })

        if workspace.exists("frontend/js/app.js"):
            js_content = workspace.read("frontend/js/app.js") or ""
            if js_content.count("{") != js_content.count("}"):
                gate_failures.append({
                    "command": "release_gate_js_structure",
                    "error": "frontend/js/app.js contains mismatched curly braces",
                    "category": "invalid_structure",
                    "responsible_agent": AgentRole.FRONTEND_ENGINEER.value,
                    "severity": "critical",
                })
            if js_content.count("(") != js_content.count(")"):
                gate_failures.append({
                    "command": "release_gate_js_structure",
                    "error": "frontend/js/app.js contains mismatched parentheses",
                    "category": "invalid_structure",
                    "responsible_agent": AgentRole.FRONTEND_ENGINEER.value,
                    "severity": "critical",
                })

        # Gate 4: Execution validation
        if not validation_result.passed or validation_result.failed_commands > 0:
            gate_failures.append({
                "command": "release_gate_execution_validation",
                "error": f"Execution validation failed with {validation_result.failed_commands} failing command(s)",
                "category": "execution_failure",
                "responsible_agent": AgentRole.QA_ENGINEER.value,
                "severity": "critical",
            })

        # Gate 5: Unresolved blocking review findings
        blocking_issues = [
            i for i in memory.review.issues
            if i.get("severity") in {"critical", "high"} or i.get("category") == "missing-implementation"
        ]
        unresolved = [
            i for i in blocking_issues
            if str(i.get("id")) not in memory.improvements_applied
        ]
        if unresolved:
            for u in unresolved:
                gate_failures.append({
                    "command": "release_gate_unresolved_review_finding",
                    "error": f"Unresolved blocking review finding [{u.get('id')}]: {u.get('description', '')}",
                    "category": "unresolved_review",
                    "responsible_agent": AgentRole.REVIEW_ENGINEER.value,
                    "severity": "critical",
                })

        return gate_failures

    async def _run_validation(
        self, ctx: AgentContext, files: dict[str, str]
    ) -> ValidationResult:
        """Run the full execution validation suite."""
        try:
            validator = WorkspaceValidator(timeout_seconds=180)
            run = await validator.validate(files, run_id=f"{ctx.memory.run_id}-final-qa")

            classification = classify_failures(run.commands)

            return ValidationResult(
                passed=run.passed,
                stack=run.stack,
                total_commands=run.total_commands,
                failed_commands=len(run.failed_commands),
                failures=[f.as_dict() for f in classification.failures],
                timestamp=datetime.now(UTC).isoformat(),
                workspace_fingerprint=ctx.memory.workspace.fingerprint,
            )

        except Exception as exc:  # noqa: BLE001
            err_msg = f"Final QA validator crashed: {type(exc).__name__}: {exc}"
            await ctx.log(
                self.role,
                err_msg,
                level=LogLevel.ERROR,
            )
            # Never release an unvalidated project when validation crashes.
            return ValidationResult(
                passed=False,
                stack="unknown",
                total_commands=1,
                failed_commands=1,
                failures=[
                    {
                        "command": "final_qa_validation",
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
            )
