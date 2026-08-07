"""Shared enumerations used across the domain, API and persistence layers."""

from __future__ import annotations

from enum import StrEnum


class RunStatus(StrEnum):
    """Lifecycle of a generation run."""

    PENDING = "pending"
    ANALYZING = "analyzing"
    AWAITING_REVIEW = "awaiting_review"
    RUNNING = "running"
    PACKAGING = "packaging"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}


class AgentStatus(StrEnum):
    """Lifecycle of a single agent execution."""

    WAITING = "waiting"
    RUNNING = "running"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


class AgentRole(StrEnum):
    """Stable identifiers for every engineer on the AI team."""

    MANAGER = "manager"
    BUSINESS_ANALYST = "business_analyst"
    SOLUTION_ARCHITECT = "solution_architect"
    DATABASE_ENGINEER = "database_engineer"
    BACKEND_ENGINEER = "backend_engineer"
    FRONTEND_ENGINEER = "frontend_engineer"
    DOCUMENTATION_ENGINEER = "documentation_engineer"
    QA_ENGINEER = "qa_engineer"
    REVIEW_ENGINEER = "review_engineer"
    IMPROVEMENT_ENGINEER = "improvement_engineer"
    ARTIFACT_MANAGER = "artifact_manager"


class ProviderStatus(StrEnum):
    """Live health of a single model provider."""

    #: Serving normally.
    HEALTHY = "healthy"
    #: Serving, but recent failures suggest it may not keep doing so.
    DEGRADED = "degraded"
    #: Temporarily withdrawn from routing after a quota or repeated failures.
    COOLING_DOWN = "cooling_down"
    #: Present but missing credentials, so it can never be selected.
    UNCONFIGURED = "unconfigured"
    #: Switched off by configuration.
    DISABLED = "disabled"

    @property
    def is_selectable(self) -> bool:
        return self in {ProviderStatus.HEALTHY, ProviderStatus.DEGRADED}


class ErrorKind(StrEnum):
    """What the provider manager should do about a failure.

    The distinction that matters is *whose fault it is*. A timeout is worth
    another attempt at the same provider; an exhausted quota is worth a
    different provider; a malformed request is worth neither, because every
    provider will reject it identically and trying them all just burns quota.
    """

    #: Transient. Retry the same provider.
    RETRYABLE = "retryable"
    #: Rate limited or out of quota. Move on and cool this provider down.
    QUOTA = "quota"
    #: Credentials rejected. Move on; retrying cannot help.
    AUTH = "auth"
    #: Model or endpoint missing. Move on.
    UNAVAILABLE = "unavailable"
    #: The request itself is wrong. Fail fast — do not spend other providers.
    FATAL = "fatal"

    @property
    def should_retry(self) -> bool:
        return self is ErrorKind.RETRYABLE

    @property
    def should_failover(self) -> bool:
        return self is not ErrorKind.FATAL


class TaskKind(StrEnum):
    """What a request is for, so routing can prefer a suitable provider.

    Derived from the calling agent rather than declared at the call site, which
    keeps every agent free of provider knowledge.
    """

    #: Requirements, architecture, schema design — judgement-heavy.
    REASONING = "reasoning"
    #: Writing application source, the largest and most exacting outputs.
    CODE_GENERATION = "code_generation"
    #: Reviewing or improving existing source.
    REVIEW = "review"
    #: Prose deliverables where a cheaper model is sufficient.
    DOCUMENTATION = "documentation"
    #: Short structured summaries.
    SUMMARY = "summary"


class AdapterKind(StrEnum):
    """Categories in the plugin-based technology adapter system."""

    FRONTEND = "frontend"
    BACKEND = "backend"
    DATABASE = "database"


class ArtifactKind(StrEnum):
    """Classification of a generated artifact."""

    REQUIREMENTS = "requirements"
    ARCHITECTURE = "architecture"
    DATABASE = "database"
    API_SPEC = "api_spec"
    FRONTEND_CODE = "frontend_code"
    BACKEND_CODE = "backend_code"
    TESTS = "tests"
    DOCUMENTATION = "documentation"
    DEVOPS = "devops"
    REPORT = "report"
    PACKAGE = "package"


class EventType(StrEnum):
    """Server-sent event names emitted during a run."""

    RUN_STARTED = "run.started"
    RUN_PHASE = "run.phase"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    RUN_CANCELLED = "run.cancelled"
    AGENT_STARTED = "agent.started"
    AGENT_PROGRESS = "agent.progress"
    AGENT_LOG = "agent.log"
    AGENT_COMPLETED = "agent.completed"
    AGENT_SKIPPED = "agent.skipped"
    AGENT_FAILED = "agent.failed"
    ARTIFACT_CREATED = "artifact.created"
    FILE_WRITTEN = "file.written"
    HEARTBEAT = "heartbeat"


class ProjectComplexity(StrEnum):
    """Coarse sizing signal produced by requirement analysis."""

    MINIMAL = "minimal"
    STANDARD = "standard"
    ADVANCED = "advanced"
    ENTERPRISE = "enterprise"


class LogLevel(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
