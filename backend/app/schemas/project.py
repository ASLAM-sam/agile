"""Project schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, field_validator

from app.schemas.common import APIModel

_MIN_IDEA_LENGTH = 10
_MAX_IDEA_LENGTH = 4000


class CreateProjectRequest(APIModel):
    """Submit a software idea."""

    idea: str = Field(
        min_length=_MIN_IDEA_LENGTH,
        max_length=_MAX_IDEA_LENGTH,
        description="The software idea, in plain language.",
        examples=["A hospital management system for scheduling and patient records"],
    )
    name: str | None = Field(
        default=None,
        max_length=200,
        description="Optional name. Derived from the idea when omitted.",
    )
    tags: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("idea")
    @classmethod
    def _clean_idea(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < _MIN_IDEA_LENGTH:
            raise ValueError(
                f"Describe the idea in at least {_MIN_IDEA_LENGTH} characters so the "
                "requirements can be analysed meaningfully."
            )
        return cleaned

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, value: list[str]) -> list[str]:
        seen: list[str] = []
        for tag in value:
            cleaned = tag.strip().lower()[:40]
            if cleaned and cleaned not in seen:
                seen.append(cleaned)
        return seen


class UpdateProjectRequest(APIModel):
    """Editable project fields."""

    name: str | None = Field(default=None, min_length=2, max_length=200)
    tags: list[str] | None = Field(default=None, max_length=10)


class ProjectSummary(APIModel):
    """Project as shown in list views."""

    id: str
    name: str
    slug: str
    idea: str
    summary: str | None
    tags: list[str]
    created_at: datetime
    updated_at: datetime


class ProjectDetail(ProjectSummary):
    """Project with its latest analysis and stack."""

    analysis: dict[str, Any] | None = None
    tech_stack: dict[str, Any] | None = None
    run_count: int = 0
    latest_run_id: str | None = None
    latest_run_status: str | None = None


class DashboardStats(APIModel):
    """Headline counters for the dashboard."""

    total_projects: int
    total_runs: int
    completed_runs: int
    total_files_generated: int
    total_generation_seconds: float
    active_runs: int
