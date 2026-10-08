"""AI Engineering Report.

Produced at the end of every run, in two forms: a structured payload for the
dashboard and a Markdown document shipped inside the ZIP.

Effort-saved estimates are derived from the delivered artefacts using published
industry averages, and the report states the basis so a reader can judge the
number rather than take it on faith. An unexplained figure would be marketing;
a stated one is evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.core.enums import AgentStatus
from app.workflow.engine import WorkflowOutcome
from app.workflow.memory import SharedProjectMemory

# Industry-average sustained output for production code, including design,
# review and rework — not raw typing speed.
_LINES_PER_DEVELOPER_DAY = 60
_HOURS_PER_DAY = 8
_DAYS_PER_WEEK = 5

# Fixed-cost activities the platform performs, in developer-hours.
_FIXED_EFFORT_HOURS = {
    "requirements": 12,
    "architecture": 10,
    "database_design": 8,
    "api_design": 6,
    "documentation": 8,
    "project_setup": 6,
}


@dataclass(slots=True)
class EffortEstimate:
    """Estimated manual development effort for the delivered artefacts."""

    hours_low: float
    hours_high: float
    basis: list[str]

    @property
    def weeks_low(self) -> float:
        return round(self.hours_low / (_HOURS_PER_DAY * _DAYS_PER_WEEK), 1)

    @property
    def weeks_high(self) -> float:
        return round(self.hours_high / (_HOURS_PER_DAY * _DAYS_PER_WEEK), 1)

    @property
    def display(self) -> str:
        if self.weeks_high < 1:
            return f"{round(self.hours_low)}–{round(self.hours_high)} hours"
        return f"{self.weeks_low}–{self.weeks_high} weeks"

    def as_dict(self) -> dict[str, Any]:
        return {
            "hours_low": round(self.hours_low),
            "hours_high": round(self.hours_high),
            "weeks_low": self.weeks_low,
            "weeks_high": self.weeks_high,
            "display": self.display,
            "basis": self.basis,
        }


def estimate_effort(memory: SharedProjectMemory) -> EffortEstimate:
    """Estimate the manual effort the generated artefacts represent."""
    stats = memory.workspace.statistics()
    code_lines = sum(
        entry.line_count
        for entry in memory.workspace.files
        if entry.extension in {".py", ".ts", ".tsx", ".js", ".jsx", ".java", ".sql", ".css"}
    )

    basis: list[str] = []
    hours = 0.0

    if code_lines:
        code_hours = (code_lines / _LINES_PER_DEVELOPER_DAY) * _HOURS_PER_DAY
        hours += code_hours
        basis.append(
            f"{code_lines:,} lines of code at ~{_LINES_PER_DEVELOPER_DAY} "
            f"lines/developer-day (industry average including design and review) "
            f"= {code_hours:.0f}h"
        )

    for key, cost in _FIXED_EFFORT_HOURS.items():
        applicable = {
            "requirements": bool(memory.analysis.functional_requirements),
            "architecture": bool(memory.architecture.modules),
            "database_design": memory.database.required and bool(memory.database.tables),
            "api_design": bool(memory.architecture.api_endpoints),
            "documentation": bool(memory.documentation_index),
            "project_setup": stats["file_count"] > 0,
        }[key]
        if applicable:
            hours += cost
            basis.append(f"{key.replace('_', ' ').title()}: {cost}h")

    # A ±35% band reflects genuine variance in team speed and domain
    # familiarity. A single point estimate would imply precision we do not have.
    return EffortEstimate(hours_low=hours * 0.65, hours_high=hours * 1.35, basis=basis)


def build_report(
    memory: SharedProjectMemory,
    outcome: WorkflowOutcome,
    *,
    package_filename: str | None = None,
    package_size_bytes: int = 0,
) -> dict[str, Any]:
    """Assemble the structured AI Engineering Report."""
    stats = memory.workspace.statistics()
    effort = estimate_effort(memory)

    agents = [
        {
            "role": step.role.value,
            "display_name": _role_title(step.role.value),
            "status": step.status.value,
            "summary": (step.result.summary if step.result else step.skip_reason or step.error),
            "duration_seconds": step.duration_seconds,
            "files_produced": step.files_produced,
            "confidence": step.result.confidence if step.result else None,
            "warnings": step.result.warnings if step.result else [],
        }
        for step in outcome.outcomes
    ]

    artifacts = _artifact_checklist(memory)
    status, status_detail = _project_status(memory, outcome)

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "generator": {"name": "Aegis AI", "version": "1.0.0"},
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
        "timing": {
            "duration_seconds": outcome.duration_seconds,
            "duration_display": _format_duration(outcome.duration_seconds),
        },
        "agents": {
            "total": len(outcome.outcomes),
            "executed": len(outcome.executed),
            "skipped": len(outcome.skipped),
            "failed": len(outcome.failures),
            "detail": agents,
        },
        "artifacts": artifacts,
        "statistics": stats,
        "usage": outcome.total_usage.as_dict(),
        "confidence": {
            "dimensions": memory.confidence,
            "overall": round(memory.average_confidence, 3),
        },
        "effort_saved": effort.as_dict(),
        "quality": {
            "review_score": memory.review.quality_score,
            "issues_found": len(memory.review.issues),
            "blocking_issues": len(memory.review.blocking_issues),
            "issues_resolved": len(memory.improvements_applied),
            "test_files": memory.test_plan.get("test_files", 0),
            "assessment": memory.review.overall_assessment,
        },
        "package": {
            "filename": package_filename,
            "size_bytes": package_size_bytes,
            "file_count": stats["file_count"],
        },
        "status": status,
        "status_detail": status_detail,
    }


def render_report_markdown(report: dict[str, Any]) -> str:
    """Render the report as the Markdown document shipped in the ZIP."""
    project = report["project"]
    stack = report["stack"]
    agents = report["agents"]
    stats = report["statistics"]
    confidence = report["confidence"]
    effort = report["effort_saved"]
    quality = report["quality"]

    lines: list[str] = [
        f"# AI Engineering Report — {project['name']}",
        "",
        f"> Generated by Aegis AI v{report['generator']['version']} on "
        f"{report['generated_at'][:10]}",
        "",
        "## Project",
        "",
        f"**{project['name']}**",
        "",
        project["summary"] or project["idea"],
        "",
        f"- **Original idea:** {project['idea']}",
        f"- **Complexity:** {project['complexity'].title()}",
        f"- **Generation time:** {report['timing']['duration_display']}",
        f"- **Status:** {report['status']}",
        "",
        "## Technology stack",
        "",
        "| Layer | Technology |",
        "|-------|------------|",
    ]

    for label, key in (
        ("Frontend", "frontend"),
        ("Backend", "backend"),
        ("Database", "database"),
        ("Authentication", "authentication"),
    ):
        lines.append(f"| {label} | {stack.get(key) or '— not required —'} |")

    team_line = f"{agents['executed']} of {agents['total']} agents executed"
    if agents["skipped"]:
        team_line += f", {agents['skipped']} skipped as unnecessary"
    if agents["failed"]:
        team_line += f", {agents['failed']} failed"

    lines += [
        "",
        "## Engineering team",
        "",
        team_line + ".",
        "",
        "| Agent | Status | Outcome | Files | Time |",
        "|-------|--------|---------|-------|------|",
    ]

    icons = {
        AgentStatus.COMPLETED.value: "done",
        AgentStatus.SKIPPED.value: "skipped",
        AgentStatus.FAILED.value: "failed",
    }
    for agent in agents["detail"]:
        summary = (agent["summary"] or "").replace("|", "/")[:110]
        lines.append(
            f"| {agent['display_name']} "
            f"| {icons.get(agent['status'], agent['status'])} "
            f"| {summary} "
            f"| {agent['files_produced'] or '—'} "
            f"| {agent['duration_seconds']:.1f}s |"
        )

    lines += [
        "",
        "## Artifacts delivered",
        "",
    ]
    for artifact in report["artifacts"]:
        mark = "x" if artifact["delivered"] else " "
        note = f" — {artifact['detail']}" if artifact["detail"] else ""
        lines.append(f"- [{mark}] {artifact['name']}{note}")

    lines += [
        "",
        "## Codebase statistics",
        "",
        f"- **Files:** {stats['file_count']}",
        f"- **Lines:** {stats['total_lines']:,}",
        f"- **Size:** {stats['total_bytes'] / 1024:.0f} KB",
        "",
        "By file type:",
        "",
    ]
    for extension, count in list(stats["by_extension"].items())[:12]:
        lines.append(f"- `{extension}`: {count}")

    lines += [
        "",
        "## Quality verification",
        "",
        f"- **Review score:** {quality['review_score']:.0%}",
        f"- **Issues found:** {quality['issues_found']} "
        f"({quality['blocking_issues']} blocking)",
        f"- **Issues resolved:** {quality['issues_resolved']}",
        f"- **Test files:** {quality['test_files']}",
    ]
    if quality["assessment"]:
        lines += ["", f"> {quality['assessment']}"]

    lines += [
        "",
        "## AI confidence",
        "",
        "Self-reported completeness per dimension, scored against expected "
        "coverage for each artifact type.",
        "",
        "| Dimension | Confidence |",
        "|-----------|-----------|",
    ]
    for dimension, score in sorted(confidence["dimensions"].items()):
        lines.append(f"| {dimension.replace('_', ' ').title()} | {score:.0%} |")
    lines.append(f"| **Overall** | **{confidence['overall']:.0%}** |")

    lines += [
        "",
        "## Estimated manual development effort",
        "",
        f"### {effort['display']}",
        "",
        "This estimate reflects what building the delivered artefacts by hand "
        "would typically cost. It is derived from the output, not asserted:",
        "",
    ]
    for item in effort["basis"]:
        lines.append(f"- {item}")
    lines += [
        "",
        f"Total: {effort['hours_low']}–{effort['hours_high']} developer-hours, "
        "using a ±35% band for team speed and domain familiarity.",
        "",
        "## Token usage",
        "",
        f"- Input: {report['usage']['input_tokens']:,}",
        f"- Output: {report['usage']['output_tokens']:,}",
        f"- Cache reads: {report['usage']['cache_read_tokens']:,}",
        f"- **Total: {report['usage']['total_tokens']:,}**",
        "",
        "---",
        "",
        "## What this is, and what it is not",
        "",
        "This is a **production-oriented starter project**: a complete, coherent "
        "foundation with working code, a real schema, documentation and tests. "
        "It is a strong starting point, not a finished product.",
        "",
        "Before deploying, you should:",
        "",
        "1. Review the generated code against your own standards.",
        "2. Replace every placeholder credential in `.env` files with real values.",
        "3. Run the test suite and extend coverage for your critical paths.",
        "4. Perform a security review appropriate to your risk profile.",
        "5. Validate the database schema against your real data volumes.",
        "",
        f"*Generated by Aegis AI v{report['generator']['version']}*",
        "",
    ]

    return "\n".join(lines)


def _artifact_checklist(memory: SharedProjectMemory) -> list[dict[str, Any]]:
    """Which deliverables were produced, and why any were not."""
    workspace = memory.workspace
    analysis = memory.analysis

    def entry(name: str, delivered: bool, detail: str = "") -> dict[str, Any]:
        return {"name": name, "delivered": delivered, "detail": detail}

    checklist = [
        entry("Executive Summary", bool(analysis.executive_summary)),
        entry("Project Overview", bool(analysis.project_overview)),
        entry(
            "Functional Requirements",
            bool(analysis.functional_requirements),
            f"{len(analysis.functional_requirements)} requirements",
        ),
        entry(
            "Non-Functional Requirements",
            bool(analysis.non_functional_requirements),
            f"{len(analysis.non_functional_requirements)} requirements",
        ),
        entry("Software Requirements Specification", bool(analysis.functional_requirements)),
        entry("User Stories", bool(analysis.user_stories), f"{len(analysis.user_stories)} stories"),
        entry("Use Cases", bool(analysis.use_cases), f"{len(analysis.use_cases)} cases"),
        entry("Project Scope", bool(analysis.scope_in)),
        entry(
            "Recommended Technology Stack",
            bool(memory.tech_stack.backend or memory.tech_stack.frontend),
        ),
        entry("Software Architecture", bool(memory.architecture.style)),
        entry(
            "Module Breakdown",
            bool(memory.architecture.modules),
            f"{len(memory.architecture.modules)} modules",
        ),
        entry("Folder Structure", bool(memory.architecture.folder_structure)),
    ]

    if analysis.needs_database:
        database_is_mongodb = memory.tech_stack.database == "mongodb"
        schema_filename = "schema.js" if database_is_mongodb else "schema.sql"
        object_count = len(memory.database.collections) if database_is_mongodb else len(memory.database.tables)
        checklist += [
            entry(
                "MongoDB Design" if database_is_mongodb else "Database Design",
                bool(memory.database.collections) if database_is_mongodb else bool(memory.database.tables),
                f"{object_count} {'collections' if database_is_mongodb else 'tables'}",
            ),
            entry(
                "MongoDB Schema" if database_is_mongodb else "SQL Schema",
                workspace.exists(f"database/{schema_filename}"),
            ),
            entry(
                "Migration Scripts",
                bool(memory.database.migrations),
                f"{len(memory.database.migrations)} migrations",
            ),
        ]
    else:
        note = "not required for this project"
        checklist += [
            entry("Database Design", True, note),
            entry("SQL Schema", True, note),
            entry("Migration Scripts", True, note),
        ]

    if analysis.needs_api:
        checklist.append(
            entry(
                "API Specification",
                bool(memory.architecture.api_endpoints),
                f"{len(memory.architecture.api_endpoints)} endpoints",
            )
        )
    else:
        checklist.append(entry("API Specification", True, "not required for this project"))

    frontend_files = len(workspace.under("frontend"))
    backend_files = len(workspace.under("backend"))
    checklist += [
        entry(
            "Frontend Source Code",
            frontend_files > 0 or not analysis.needs_frontend,
            f"{frontend_files} files" if frontend_files else "not required for this project",
        ),
        entry(
            "Backend Source Code",
            backend_files > 0 or not analysis.needs_backend,
            f"{backend_files} files" if backend_files else "not required for this project",
        ),
        entry(
            "Environment Configuration",
            any(f.path.endswith(".env.example") for f in workspace.files),
        ),
        entry("README", workspace.exists("README.md")),
        entry("Installation Guide", workspace.exists("docs/INSTALLATION.md")),
        entry(
            "API Documentation",
            workspace.exists("docs/API.md") or not analysis.needs_api,
            "" if analysis.needs_api else "not required for this project",
        ),
        entry("Dockerfile", any(f.path.endswith("Dockerfile") for f in workspace.files)),
        entry("docker-compose.yml", workspace.exists("docker-compose.yml")),
        entry(
            "Unit Tests",
            memory.test_plan.get("test_files", 0) > 0,
            f"{memory.test_plan.get('test_files', 0)} test files",
        ),
        entry("Project Documentation", bool(memory.documentation_index)),
        entry("AI Engineering Report", True),
        entry("Downloadable ZIP Package", True),
    ]
    return checklist


def _project_status(memory: SharedProjectMemory, outcome: WorkflowOutcome) -> tuple[str, str]:
    """Honest one-line verdict on the delivered project."""
    if outcome.failed:
        return "Incomplete", outcome.failure_reason
    if outcome.failures:
        names = ", ".join(o.role.value.replace("_", " ") for o in outcome.failures)
        return "Ready with gaps", f"These agents did not complete: {names}."
    if memory.review.blocking_issues:
        return (
            "Ready for review",
            f"{len(memory.review.blocking_issues)} blocking issue(s) were raised in "
            "code review; check the report before building on this.",
        )
    return "Ready for development", "All required agents completed successfully."


def _role_title(role_value: str) -> str:
    """Human-readable label for an agent role identifier."""
    overrides = {
        "qa_engineer": "QA Engineer",
        "review_engineer": "AI Review Engineer",
        "improvement_engineer": "Code Improvement Engineer",
    }
    return overrides.get(role_value, role_value.replace("_", " ").title())


def _format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f} seconds"
    minutes, remainder = divmod(int(seconds), 60)
    minute_label = "minute" if minutes == 1 else "minutes"
    second_label = "second" if remainder == 1 else "seconds"
    return f"{minutes} {minute_label} {remainder} {second_label}"
