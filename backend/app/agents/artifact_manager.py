"""Artifact Manager agent.

Finalises the project: emits root-level integration files (Docker Compose,
.gitignore, .editorconfig, licence), organises the workspace and produces the
manifest that the packaging step turns into a ZIP.

This agent is deterministic — no model call. Compose files, ignore rules and
manifests are mechanical derivations of state already in memory.

ZIP RELEASE GATE (Phase 2):
This agent now checks memory.release_eligible before producing a package.
If Final QA failed (blocking failures), this agent produces a failure report
instead of a valid ZIP. The run is still marked COMPLETED but the failure
report describes exactly what failed and why.

A valid ZIP is only produced if:
  1. memory.release_eligible is True (Final QA passed), OR
  2. Final QA was skipped entirely (no source files generated — not our fault)

The ZIP explicitly EXCLUDES:
  - .env files
  - node_modules
  - Python virtual environments
  - __pycache__
  - .git
  - aegis-manifest.json (internal generator file — kept as aegis-manifest.json
    for the user's reference but excluded from the clean extraction)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from app.agents.base import Agent
from app.agents.context import AgentContext
from app.agents.results import AgentResult
from app.core.enums import AgentRole, ArtifactKind, LogLevel
from app.packaging.compose import build_compose_file
from app.packaging.ignore import build_editorconfig, build_gitignore
from app.workflow.memory import ValidationResult


class ArtifactManagerAgent(Agent):
    role = AgentRole.ARTIFACT_MANAGER
    display_name = "Artifact Manager"
    description = (
        "Assembles root-level integration files, organises artifacts and "
        "prepares the downloadable package. Requires Final QA to pass."
    )
    depends_on = (AgentRole.DOCUMENTATION_ENGINEER, AgentRole.FINAL_QA)

    def system_prompt(self, ctx: AgentContext) -> str:
        # Not used: this agent makes no model call.
        return "ROLE: Artifact Manager (deterministic; no model call is made)."

    async def execute(self, ctx: AgentContext) -> AgentResult:
        memory = ctx.memory
        workspace = memory.workspace

        # --- ZIP Release Gate -------------------------------------------
        # Check if Final QA passed before packaging.
        # release_eligible is False unless Final QA explicitly set it to True.
        final_qa = memory.final_qa_result
        if final_qa is not None and not memory.release_eligible:
            return await self._produce_failure_report(ctx, final_qa)

        await ctx.progress(self.role, 20, "Assembling integration files")

        written = 0
        scaffold_ctx = ctx.scaffold_context()

        # docker-compose.yml wiring every service the project actually has.
        compose = build_compose_file(ctx.registry, memory, scaffold_ctx)
        if compose:
            workspace.write(
                "docker-compose.yml",
                compose,
                description="Runs the full stack: database, API and web client.",
                produced_by=self.role,
            )
            written += 1

        workspace.write(
            ".gitignore",
            build_gitignore(memory),
            description="Ignore rules for every language present in the project.",
            produced_by=self.role,
        )
        workspace.write(
            ".editorconfig",
            build_editorconfig(),
            description="Consistent editor settings across the team.",
            produced_by=self.role,
        )
        written += 2

        await ctx.progress(self.role, 55, "Writing the project manifest")

        workspace.write(
            "aegis-manifest.json",
            self._manifest(ctx),
            description="Machine-readable record of how this project was generated.",
            produced_by=self.role,
        )
        written += 1

        await ctx.progress(self.role, 80, "Validating the package")

        warnings = self._validate(ctx)
        for warning in warnings:
            await ctx.log(self.role, warning, level=LogLevel.WARNING)

        # Security check — no credentials in output
        credential_warnings = self._check_credentials(ctx)
        for warning in credential_warnings:
            await ctx.log(self.role, warning, level=LogLevel.ERROR)
        warnings.extend(credential_warnings)

        stats = workspace.statistics()
        qa_status = "VALIDATED" if memory.release_eligible else "UNVALIDATED"
        await ctx.log(
            self.role,
            f"Package ready ({qa_status}): {stats['file_count']} files, "
            f"{stats['total_bytes'] / 1024:.0f} KB",
            **{k: v for k, v in stats.items() if k in {"file_count", "total_lines"}},
        )

        confidence = 1.0 if not warnings else max(0.5, 1.0 - 0.1 * len(warnings))
        if memory.release_eligible:
            confidence = min(confidence + 0.2, 1.0)
        memory.record_confidence("packaging", confidence)

        summary = (
            f"{stats['file_count']} files ({stats['total_lines']} lines, "
            f"{stats['total_bytes'] / 1024:.0f} KB) packaged for download. "
            f"Final QA: {'PASSED' if memory.release_eligible else 'NOT RUN'}."
        )
        memory.record_summary(self.role, summary)
        await ctx.progress(self.role, 100, "Artifacts packaged")

        return AgentResult(
            role=self.role,
            summary=summary,
            output={
                "statistics": stats,
                "manifest_entries": len(workspace),
                "artifact_kind": ArtifactKind.PACKAGE.value,
                "release_eligible": memory.release_eligible,
                "final_qa_passed": memory.release_eligible,
            },
            files_produced=written,
            confidence=confidence,
            warnings=warnings,
        )

    async def _produce_failure_report(self, ctx: AgentContext, final_qa) -> AgentResult:
        """Produce a failure report when Final QA blocks the release."""
        memory = ctx.memory
        workspace = memory.workspace

        if final_qa is None:
            final_qa = ValidationResult(
                passed=False,
                stack="unknown",
                total_commands=1,
                failed_commands=1,
                failures=[{
                    "command": "pipeline_execution",
                    "error": "Pipeline did not pass validation or final QA gate; release is blocked.",
                    "category": "workflow_failure",
                    "responsible_agent": AgentRole.FINAL_QA.value,
                    "severity": "critical",
                }],
            )

        await ctx.progress(self.role, 30, "Final QA failed — producing failure report")

        failure_report = self._build_failure_report(ctx, final_qa)
        workspace.write(
            "AEGIS-FAILURE-REPORT.md",
            failure_report,
            description="Detailed report of why this project failed final validation.",
            produced_by=self.role,
        )

        # Still produce aegis-manifest.json for diagnostic purposes
        workspace.write(
            "aegis-manifest.json",
            self._manifest(ctx),
            description="Generation record (project FAILED validation).",
            produced_by=self.role,
        )

        summary = (
            f"RELEASE BLOCKED: Final QA failed with "
            f"{final_qa.failed_commands} failing command(s). "
            "Failure report produced instead of clean ZIP."
        )
        memory.record_summary(self.role, summary)

        await ctx.log(self.role, summary, level=LogLevel.ERROR)
        await ctx.progress(self.role, 100, "Failure report ready")

        return AgentResult(
            role=self.role,
            summary=summary,
            output={
                "release_eligible": False,
                "final_qa_passed": False,
                "artifact_kind": ArtifactKind.REPORT.value,
                "failure_report": "AEGIS-FAILURE-REPORT.md",
            },
            files_produced=2,
            confidence=0.0,
            warnings=[summary],
        )

    def _manifest(self, ctx: AgentContext) -> str:
        memory = ctx.memory
        payload = {
            "generator": {
                "name": "Aegis AI",
                "version": "2.0.0",
                "generated_at": datetime.now(UTC).isoformat(),
            },
            "project": {
                "name": memory.project_name,
                "slug": memory.project_slug,
                "idea": memory.idea,
                "summary": memory.analysis.executive_summary,
                "complexity": memory.analysis.complexity.value,
            },
            "stack": memory.tech_stack.as_dict(),
            "capabilities": {
                "authentication": memory.needs_auth,
                "database": memory.needs_database,
                "api": memory.analysis.needs_api,
                "backend": memory.needs_backend,
                "frontend": memory.needs_frontend,
            },
            "statistics": memory.workspace.statistics(),
            "agents": memory.agent_summaries,
            "confidence": memory.confidence,
            "validation": {
                "release_eligible": memory.release_eligible,
                "final_qa_passed": memory.release_eligible,
                "repair_cycles": memory.repair_cycle_count,
                "validation_runs": len(memory.validation_runs),
            },
            "files": memory.workspace.manifest(),
        }
        return json.dumps(payload, indent=2) + "\n"

    def _build_failure_report(self, ctx: AgentContext, final_qa) -> str:
        """Build a Markdown failure report for the developer."""
        memory = ctx.memory
        lines = [
            "# Aegis AI — Project Generation Failure Report",
            "",
            f"**Project**: {memory.project_name}",
            f"**Run ID**: {memory.run_id}",
            f"**Generated**: {datetime.now(UTC).isoformat()}",
            "",
            "## ❌ Final Validation Failed",
            "",
            f"- **Commands run**: {final_qa.total_commands}",
            f"- **Commands failed**: {final_qa.failed_commands}",
            f"- **Stack detected**: {final_qa.stack}",
            "",
            "## Failures",
            "",
        ]
        for i, failure in enumerate(final_qa.failures, 1):
            lines.extend([
                f"### Failure {i}: {failure.get('category', 'unknown')}",
                f"- **Command**: `{failure.get('command', '')}`",
                f"- **Exit code**: {failure.get('exit_code', '')}",
                f"- **File**: `{failure.get('file', 'unknown')}`",
                f"- **Responsible agent**: {failure.get('responsible_agent', '')}",
                f"- **Severity**: {failure.get('severity', '')}",
                f"- **Error**: {failure.get('error', '')}",
                "",
            ])

        if memory.repair_cycles:
            lines.extend([
                "## Repair History",
                "",
                f"- **Repair cycles attempted**: {memory.repair_cycle_count}",
                "",
            ])

        lines.extend([
            "## How to Fix",
            "",
            "1. Review the failures above and note the responsible agent for each.",
            "2. Manually edit the files listed in each failure.",
            "3. Run the failing command locally to verify the fix.",
            "4. Or re-submit the project request with more specific requirements.",
            "",
        ])
        return "\n".join(lines)

    @staticmethod
    def _validate(ctx: AgentContext) -> list[str]:
        """Final structural gate: what a person opening the ZIP would immediately notice."""
        memory = ctx.memory
        workspace = memory.workspace
        warnings: list[str] = []

        if not workspace.exists("README.md"):
            warnings.append("No README.md — the package has no entry point for a reader.")
        if memory.needs_backend and not workspace.under("backend"):
            warnings.append("Backend was required but no backend files are present.")
        if memory.needs_frontend and not workspace.under("frontend"):
            warnings.append("Frontend was required but no frontend files are present.")
        if memory.needs_database and memory.tech_stack.database:
            adapter = ctx.registry.database(memory.tech_stack.database)
            schema_path = f"database/{adapter.schema_filename}"
            if not workspace.exists(schema_path):
                warnings.append(f"Database was required but {schema_path} is missing.")

        if workspace.rejections:
            warnings.append(
                f"{len(workspace.rejections)} file(s) were rejected during generation."
            )

        empty = [f.path for f in workspace.files if not f.content.strip()]
        if empty:
            warnings.append(f"{len(empty)} generated file(s) are empty: {', '.join(empty[:3])}")

        return warnings

    @staticmethod
    def _check_credentials(ctx: AgentContext) -> list[str]:
        """Scan the generated output for accidental credential leaks."""
        import re

        # Patterns that strongly suggest real credentials
        credential_patterns = [
            re.compile(r"[A-Za-z0-9_-]{20,}[=][A-Za-z0-9_/+]{30,}", re.IGNORECASE),
            re.compile(r"sk-[A-Za-z0-9]{20,}"),
            re.compile(r"AIza[A-Za-z0-9_-]{30,}"),  # Google API key pattern
            re.compile(r"nvapi-[A-Za-z0-9_-]{30,}"),  # NVIDIA API key
        ]

        # Values that look like real API keys (not obviously placeholder)
        placeholder_markers = {
            "your_key", "your-key", "placeholder", "example", "changeme",
            "secret_here", "api_key_here", "xxxxxxx",
        }

        warnings = []
        for entry in ctx.memory.workspace.files:
            # Only check config/env files
            if not any(entry.path.endswith(ext) for ext in (
                ".env", ".env.local", ".env.production", ".yaml", ".yml", ".json", ".toml"
            )):
                continue

            content = entry.content
            for pattern in credential_patterns:
                match = pattern.search(content)
                if match:
                    value = match.group(0)
                    if not any(marker in value.lower() for marker in placeholder_markers):
                        warnings.append(
                            f"Potential credential leak in {entry.path}: "
                            "found a value matching an API key pattern. "
                            "Review before distributing."
                        )
                        break

        return warnings
