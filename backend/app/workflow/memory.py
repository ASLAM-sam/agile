"""Shared project memory.

A single, typed state object threaded through every agent. It is the reason
agents behave like colleagues on one project rather than independent prompts:
the Backend Engineer sees the schema the Database Engineer designed, the QA
Engineer sees the code the others wrote, and the Documentation Engineer sees
everything.

Version 1 deliberately uses no vector store. The state is small, structured and
fully enumerable, so exact recall beats similarity search.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.core.enums import AgentRole, ProjectComplexity
from app.packaging.workspace import ProjectWorkspace


@dataclass(slots=True)
class RequirementAnalysis:
    """Output of the Business Analyst, and the input that shapes the workflow."""

    executive_summary: str = ""
    project_overview: str = ""
    scope_in: list[str] = field(default_factory=list)
    scope_out: list[str] = field(default_factory=list)
    functional_requirements: list[dict[str, Any]] = field(default_factory=list)
    non_functional_requirements: list[dict[str, Any]] = field(default_factory=list)
    user_stories: list[dict[str, Any]] = field(default_factory=list)
    use_cases: list[dict[str, Any]] = field(default_factory=list)
    actors: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    clarifications: list[str] = field(default_factory=list)

    # Capability decisions that drive dynamic agent selection.
    needs_authentication: bool = False
    needs_database: bool = False
    needs_api: bool = False
    needs_backend: bool = False
    needs_frontend: bool = True
    complexity: ProjectComplexity = ProjectComplexity.STANDARD
    rationale: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "executive_summary": self.executive_summary,
            "project_overview": self.project_overview,
            "scope_in": self.scope_in,
            "scope_out": self.scope_out,
            "functional_requirements": self.functional_requirements,
            "non_functional_requirements": self.non_functional_requirements,
            "user_stories": self.user_stories,
            "use_cases": self.use_cases,
            "actors": self.actors,
            "entities": self.entities,
            "assumptions": self.assumptions,
            "clarifications": self.clarifications,
            "capabilities": {
                "needs_authentication": self.needs_authentication,
                "needs_database": self.needs_database,
                "needs_api": self.needs_api,
                "needs_backend": self.needs_backend,
                "needs_frontend": self.needs_frontend,
            },
            "complexity": self.complexity.value,
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RequirementAnalysis:
        capabilities = data.get("capabilities", {})
        raw_complexity = data.get("complexity", ProjectComplexity.STANDARD.value)
        try:
            complexity = ProjectComplexity(raw_complexity)
        except ValueError:
            complexity = ProjectComplexity.STANDARD
        return cls(
            executive_summary=data.get("executive_summary", ""),
            project_overview=data.get("project_overview", ""),
            scope_in=data.get("scope_in", []),
            scope_out=data.get("scope_out", []),
            functional_requirements=data.get("functional_requirements", []),
            non_functional_requirements=data.get("non_functional_requirements", []),
            user_stories=data.get("user_stories", []),
            use_cases=data.get("use_cases", []),
            actors=data.get("actors", []),
            entities=data.get("entities", []),
            assumptions=data.get("assumptions", []),
            clarifications=data.get("clarifications", []),
            needs_authentication=capabilities.get("needs_authentication", False),
            needs_database=capabilities.get("needs_database", False),
            needs_api=capabilities.get("needs_api", False),
            needs_backend=capabilities.get("needs_backend", False),
            needs_frontend=capabilities.get("needs_frontend", True),
            complexity=complexity,
            rationale=data.get("rationale", ""),
        )


@dataclass(slots=True)
class TechStack:
    """The resolved technology selection for a run."""

    frontend: str | None = None
    backend: str | None = None
    database: str | None = None
    authentication: str | None = None
    rationale: dict[str, str] = field(default_factory=dict)
    user_customised: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "frontend": self.frontend,
            "backend": self.backend,
            "database": self.database,
            "authentication": self.authentication,
            "rationale": self.rationale,
            "user_customised": self.user_customised,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TechStack:
        return cls(
            frontend=data.get("frontend"),
            backend=data.get("backend"),
            database=data.get("database"),
            authentication=data.get("authentication"),
            rationale=data.get("rationale", {}),
            user_customised=data.get("user_customised", False),
        )


@dataclass(slots=True)
class ArchitectureDesign:
    """Output of the Solution Architect."""

    style: str = ""
    overview: str = ""
    modules: list[dict[str, Any]] = field(default_factory=list)
    layers: list[dict[str, Any]] = field(default_factory=list)
    folder_structure: str = ""
    api_endpoints: list[dict[str, Any]] = field(default_factory=list)
    integrations: list[str] = field(default_factory=list)
    cross_cutting: list[str] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "style": self.style,
            "overview": self.overview,
            "modules": self.modules,
            "layers": self.layers,
            "folder_structure": self.folder_structure,
            "api_endpoints": self.api_endpoints,
            "integrations": self.integrations,
            "cross_cutting": self.cross_cutting,
            "decisions": self.decisions,
        }


@dataclass(slots=True)
class DatabaseDesign:
    """Output of the Database Engineer."""

    required: bool = False
    engine: str | None = None
    tables: list[dict[str, Any]] = field(default_factory=list)
    relationships: list[dict[str, Any]] = field(default_factory=list)
    indexes: list[dict[str, Any]] = field(default_factory=list)
    schema_sql: str = ""
    seed_sql: str = ""
    migrations: list[dict[str, str]] = field(default_factory=list)
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "required": self.required,
            "engine": self.engine,
            "tables": self.tables,
            "relationships": self.relationships,
            "indexes": self.indexes,
            "has_schema": bool(self.schema_sql),
            "migration_count": len(self.migrations),
            "notes": self.notes,
        }


@dataclass(slots=True)
class ReviewFindings:
    """Output of the AI Review Engineer."""

    issues: list[dict[str, Any]] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    missing_apis: list[str] = field(default_factory=list)
    duplication: list[dict[str, Any]] = field(default_factory=list)
    overall_assessment: str = ""
    quality_score: float = 0.0

    @property
    def blocking_issues(self) -> list[dict[str, Any]]:
        return [i for i in self.issues if i.get("severity") in {"critical", "high"}]

    def as_dict(self) -> dict[str, Any]:
        return {
            "issues": self.issues,
            "strengths": self.strengths,
            "missing_apis": self.missing_apis,
            "duplication": self.duplication,
            "overall_assessment": self.overall_assessment,
            "quality_score": self.quality_score,
            "blocking_count": len(self.blocking_issues),
        }


@dataclass
class SharedProjectMemory:
    """The single state object shared by every agent in a run."""

    run_id: str
    project_id: str
    project_name: str
    project_slug: str
    idea: str

    workspace: ProjectWorkspace = field(default_factory=ProjectWorkspace)
    analysis: RequirementAnalysis = field(default_factory=RequirementAnalysis)
    tech_stack: TechStack = field(default_factory=TechStack)
    architecture: ArchitectureDesign = field(default_factory=ArchitectureDesign)
    database: DatabaseDesign = field(default_factory=DatabaseDesign)
    review: ReviewFindings = field(default_factory=ReviewFindings)

    api_spec: dict[str, Any] = field(default_factory=dict)
    test_plan: dict[str, Any] = field(default_factory=dict)
    documentation_index: list[str] = field(default_factory=list)
    confidence: dict[str, float] = field(default_factory=dict)
    agent_summaries: dict[str, str] = field(default_factory=dict)
    improvements_applied: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    # --- mutation --------------------------------------------------------

    def record_summary(self, role: AgentRole, summary: str) -> None:
        self.agent_summaries[role.value] = summary

    def record_confidence(self, dimension: str, score: float) -> None:
        """Store a 0–1 confidence score, clamped to range."""
        self.confidence[dimension] = max(0.0, min(1.0, score))

    def add_note(self, note: str) -> None:
        if note and note not in self.notes:
            self.notes.append(note)

    # --- derived views ---------------------------------------------------

    @property
    def needs_backend(self) -> bool:
        return self.analysis.needs_backend

    @property
    def needs_frontend(self) -> bool:
        return self.analysis.needs_frontend

    @property
    def needs_database(self) -> bool:
        return self.analysis.needs_database

    @property
    def needs_auth(self) -> bool:
        return self.analysis.needs_authentication

    @property
    def average_confidence(self) -> float:
        if not self.confidence:
            return 0.0
        return sum(self.confidence.values()) / len(self.confidence)

    def context_digest(self, *, include_files: bool = True) -> str:
        """Compact project context injected into every agent prompt.

        Ordering matters: this is rendered after the cached system prefix, so
        it must contain only project-specific content.
        """
        lines = [
            f"PROJECT: {self.project_name}",
            f"IDEA: {self.idea}",
        ]
        if self.analysis.executive_summary:
            lines.append(f"SUMMARY: {self.analysis.executive_summary}")

        stack = self.tech_stack
        if any((stack.frontend, stack.backend, stack.database)):
            parts = [
                f"frontend={stack.frontend or 'none'}",
                f"backend={stack.backend or 'none'}",
                f"database={stack.database or 'none'}",
                f"auth={stack.authentication or 'none'}",
            ]
            lines.append("STACK: " + ", ".join(parts))

        lines.append(
            "CAPABILITIES: "
            f"auth={self.needs_auth}, database={self.needs_database}, "
            f"api={self.analysis.needs_api}, backend={self.needs_backend}, "
            f"frontend={self.needs_frontend}"
        )

        if self.analysis.entities:
            lines.append("ENTITIES: " + ", ".join(self.analysis.entities[:25]))

        if self.architecture.style:
            lines.append(f"ARCHITECTURE: {self.architecture.style}")
        if self.architecture.modules:
            names = [str(m.get("name", "")) for m in self.architecture.modules[:15]]
            lines.append("MODULES: " + ", ".join(n for n in names if n))

        if self.database.tables:
            names = [str(t.get("name", "")) for t in self.database.tables[:25]]
            lines.append("TABLES: " + ", ".join(n for n in names if n))

        if self.architecture.api_endpoints:
            endpoints = [
                f"{e.get('method', 'GET')} {e.get('path', '')}"
                for e in self.architecture.api_endpoints[:30]
            ]
            lines.append("API ENDPOINTS:\n  " + "\n  ".join(endpoints))

        if include_files and len(self.workspace) > 0:
            lines.append(f"EXISTING FILES ({len(self.workspace)}):")
            lines.append(self.workspace.summary_for_prompt(limit=80))

        return "\n".join(lines)

    def snapshot(self) -> dict[str, Any]:
        """Serialisable state, persisted with the run for audit and replay."""
        return {
            "run_id": self.run_id,
            "project_id": self.project_id,
            "project_name": self.project_name,
            "project_slug": self.project_slug,
            "idea": self.idea,
            "analysis": self.analysis.as_dict(),
            "tech_stack": self.tech_stack.as_dict(),
            "architecture": self.architecture.as_dict(),
            "database": self.database.as_dict(),
            "review": self.review.as_dict(),
            "api_spec": self.api_spec,
            "test_plan": self.test_plan,
            "documentation_index": self.documentation_index,
            "confidence": self.confidence,
            "agent_summaries": self.agent_summaries,
            "improvements_applied": self.improvements_applied,
            "notes": self.notes,
            "workspace": self.workspace.statistics(),
            "manifest": self.workspace.manifest(),
        }
