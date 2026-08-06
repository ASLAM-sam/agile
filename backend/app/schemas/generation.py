"""Generation run, analysis and stack schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, model_validator

from app.schemas.common import APIModel


class TechStackSelection(APIModel):
    """A user-chosen or recommended technology stack."""

    frontend: str | None = None
    backend: str | None = None
    database: str | None = None
    authentication: str | None = None

    @model_validator(mode="after")
    def _at_least_one(self) -> TechStackSelection:
        if not any((self.frontend, self.backend, self.database)):
            raise ValueError("Select at least one technology.")
        return self


class ScoredOptionResponse(APIModel):
    """One ranked technology option with its reasoning."""

    key: str
    display_name: str
    score: float
    reasons: list[str]


class AnalysisResponse(APIModel):
    """Requirement analysis plus the recommended stack."""

    project_id: str
    analysis: dict[str, Any]
    recommended_stack: dict[str, Any]
    options: dict[str, list[ScoredOptionResponse]]
    workflow_preview: list[dict[str, Any]]


class StartRunRequest(APIModel):
    """Begin generation, optionally overriding the recommended stack."""

    tech_stack: TechStackSelection | None = Field(
        default=None,
        description="Override the recommendation. Omit to accept it as-is.",
    )


class AgentExecutionResponse(APIModel):
    """One agent's execution state."""

    role: str
    display_name: str
    sequence: int
    status: str
    progress: int
    summary: str | None = None
    skip_reason: str | None = None
    error_message: str | None = None
    confidence: float | None = None
    files_produced: int
    duration_seconds: float | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class RunSummary(APIModel):
    """Run as shown in list views."""

    id: str
    project_id: str
    status: str
    phase: str | None
    progress: int
    file_count: int
    duration_seconds: float | None
    created_at: datetime
    finished_at: datetime | None


class RunDetail(RunSummary):
    """Run with its full execution state."""

    project_name: str | None = None
    tech_stack: dict[str, Any] | None = None
    analysis: dict[str, Any] | None = None
    workflow_plan: list[dict[str, Any]] | None = None
    report: dict[str, Any] | None = None
    error_message: str | None = None
    agents: list[AgentExecutionResponse] = Field(default_factory=list)
    artifact_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0


class RunEventResponse(APIModel):
    """One entry in a run's timeline."""

    sequence: int
    type: str = Field(validation_alias="event_type")
    level: str
    agent: str | None = Field(default=None, validation_alias="agent_role")
    message: str
    payload: dict[str, Any] | None = None
    timestamp: datetime = Field(validation_alias="created_at")


class ArtifactSummary(APIModel):
    """A generated deliverable."""

    id: str
    kind: str
    name: str
    description: str | None
    produced_by: str | None
    version: int
    content_type: str
    size_bytes: int
    is_downloadable: bool = False
    created_at: datetime


class ArtifactDetail(ArtifactSummary):
    """A deliverable including its inline content."""

    content: str | None = None
    artifact_metadata: dict[str, Any] | None = None


class WorkspaceFileResponse(APIModel):
    """One file in a generated project."""

    path: str
    description: str
    produced_by: str | None
    size_bytes: int
    line_count: int


class AgentDescriptor(APIModel):
    """A member of the AI engineering team, for the roster view."""

    role: str
    display_name: str
    description: str
    depends_on: str


class AdapterDescriptorResponse(APIModel):
    """A registered technology, for the stack-selection screen."""

    key: str
    display_name: str
    kind: str
    language: str
    version: str
    description: str
    tags: list[str]
    best_for: list[str]


class CatalogueResponse(APIModel):
    """Everything the platform can build with."""

    frontend: list[AdapterDescriptorResponse]
    backend: list[AdapterDescriptorResponse]
    database: list[AdapterDescriptorResponse]
    agents: list[AgentDescriptor]
