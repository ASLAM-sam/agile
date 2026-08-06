"""Artifact Manager agent.

Finalises the project: emits root-level integration files (Docker Compose,
.gitignore, .editorconfig, licence), organises the workspace and produces the
manifest that the packaging step turns into a ZIP.

This agent is deterministic — no model call. Compose files, ignore rules and
manifests are mechanical derivations of state already in memory. Generating
them with a language model would introduce variance with nothing to gain.
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


class ArtifactManagerAgent(Agent):
    role = AgentRole.ARTIFACT_MANAGER
    display_name = "Artifact Manager"
    description = (
        "Assembles root-level integration files, organises artifacts and "
        "prepares the downloadable package."
    )
    depends_on = (AgentRole.DOCUMENTATION_ENGINEER,)

    def system_prompt(self, ctx: AgentContext) -> str:
        # Not used: this agent makes no model call.
        return "ROLE: Artifact Manager (deterministic; no model call is made)."

    async def execute(self, ctx: AgentContext) -> AgentResult:
        memory = ctx.memory
        workspace = memory.workspace

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

        stats = workspace.statistics()
        await ctx.log(
            self.role,
            f"Package ready: {stats['file_count']} files, "
            f"{stats['total_bytes'] / 1024:.0f} KB",
            **{k: v for k, v in stats.items() if k in {"file_count", "total_lines"}},
        )

        confidence = 1.0 if not warnings else max(0.5, 1.0 - 0.1 * len(warnings))
        memory.record_confidence("packaging", confidence)

        summary = (
            f"{stats['file_count']} files ({stats['total_lines']} lines, "
            f"{stats['total_bytes'] / 1024:.0f} KB) packaged for download."
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
            },
            files_produced=written,
            confidence=confidence,
            warnings=warnings,
        )

    def _manifest(self, ctx: AgentContext) -> str:
        memory = ctx.memory
        payload = {
            "generator": {
                "name": "Aegis AI",
                "version": "1.0.0",
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
            "files": memory.workspace.manifest(),
        }
        return json.dumps(payload, indent=2) + "\n"

    @staticmethod
    def _validate(ctx: AgentContext) -> list[str]:
        """Final gate: what a person opening the ZIP would immediately notice."""
        memory = ctx.memory
        workspace = memory.workspace
        warnings: list[str] = []

        if not workspace.exists("README.md"):
            warnings.append("No README.md — the package has no entry point for a reader.")
        if memory.needs_backend and not workspace.under("backend"):
            warnings.append("Backend was required but no backend files are present.")
        if memory.needs_frontend and not workspace.under("frontend"):
            warnings.append("Frontend was required but no frontend files are present.")
        if memory.needs_database and not workspace.exists("database/schema.sql"):
            warnings.append("Database was required but database/schema.sql is missing.")

        if workspace.rejections:
            warnings.append(
                f"{len(workspace.rejections)} file(s) were rejected during generation."
            )

        empty = [f.path for f in workspace.files if not f.content.strip()]
        if empty:
            warnings.append(f"{len(empty)} generated file(s) are empty: {', '.join(empty[:3])}")

        return warnings
