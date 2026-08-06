"""Technology adapter contracts.

An adapter encapsulates everything the platform knows about one technology:
the deterministic scaffold it emits, the conventions its generated code must
follow, its container definition and its dependency manifest.

The split is deliberate. Adapters emit build tooling — `package.json`,
`tsconfig.json`, `vite.config.ts`, `pyproject.toml`, Dockerfiles — as
hand-verified, version-pinned code. Agents never generate build configuration,
because a subtly wrong build file breaks a project in ways a reader cannot
diagnose. Agents generate only application logic, guided by the adapter's
`conventions()` prompt fragment.

Adding a technology means adding one subclass and registering it. No workflow,
agent or API code changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.core.enums import AdapterKind


@dataclass(slots=True, frozen=True)
class ScaffoldFile:
    """A deterministic file contributed by an adapter."""

    path: str
    content: str
    description: str = ""
    executable: bool = False


@dataclass(slots=True)
class ScaffoldContext:
    """Everything an adapter needs to emit a correct scaffold."""

    project_name: str
    project_slug: str
    description: str
    needs_auth: bool = False
    needs_database: bool = False
    needs_api: bool = False
    needs_backend: bool = False
    needs_frontend: bool = False
    frontend_key: str | None = None
    backend_key: str | None = None
    database_key: str | None = None
    api_port: int = 8000
    web_port: int = 5173
    entities: list[str] = field(default_factory=list)

    @property
    def package_name(self) -> str:
        """Python/Java friendly identifier derived from the slug."""
        return self.project_slug.replace("-", "_")

    @property
    def api_base_url(self) -> str:
        return f"http://localhost:{self.api_port}"


@dataclass(slots=True, frozen=True)
class AdapterDescriptor:
    """Catalogue entry surfaced to the UI for stack selection."""

    key: str
    display_name: str
    kind: AdapterKind
    language: str
    version: str
    description: str
    tags: tuple[str, ...] = ()
    best_for: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "display_name": self.display_name,
            "kind": self.kind.value,
            "language": self.language,
            "version": self.version,
            "description": self.description,
            "tags": list(self.tags),
            "best_for": list(self.best_for),
        }


class TechnologyAdapter(ABC):
    """Base class for every pluggable technology."""

    key: str
    display_name: str
    kind: AdapterKind
    language: str
    version: str
    description: str = ""
    tags: tuple[str, ...] = ()
    best_for: tuple[str, ...] = ()

    def descriptor(self) -> AdapterDescriptor:
        return AdapterDescriptor(
            key=self.key,
            display_name=self.display_name,
            kind=self.kind,
            language=self.language,
            version=self.version,
            description=self.description,
            tags=self.tags,
            best_for=self.best_for,
        )

    @abstractmethod
    def scaffold(self, ctx: ScaffoldContext) -> list[ScaffoldFile]:
        """Deterministic files this adapter contributes to the project."""

    @abstractmethod
    def conventions(self, ctx: ScaffoldContext) -> str:
        """Prompt fragment describing how generated code must be written.

        This is the contract handed to the code-generating agent. It must be
        precise about paths, imports, naming and style so generated files drop
        into the scaffold without manual reconciliation.
        """

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<{type(self).__name__} {self.key}>"


class FrontendAdapter(TechnologyAdapter):
    """A client-side application framework."""

    kind = AdapterKind.FRONTEND
    root_dir = "frontend"
    source_dir = "frontend/src"

    @abstractmethod
    def dockerfile(self, ctx: ScaffoldContext) -> str:
        """Container definition for the frontend service."""

    def compose_service(self, ctx: ScaffoldContext) -> dict[str, Any]:
        return {
            "build": {"context": f"./{self.root_dir}"},
            "ports": [f"{ctx.web_port}:{ctx.web_port}"],
            "environment": {"VITE_API_BASE_URL": ctx.api_base_url},
            "depends_on": ["api"] if ctx.needs_backend else [],
        }


class BackendAdapter(TechnologyAdapter):
    """A server-side application framework."""

    kind = AdapterKind.BACKEND
    root_dir = "backend"
    supported_databases: tuple[str, ...] = ()

    @abstractmethod
    def dockerfile(self, ctx: ScaffoldContext) -> str:
        """Container definition for the API service."""

    @abstractmethod
    def env_template(self, ctx: ScaffoldContext, database_url: str) -> str:
        """Contents of the backend `.env.example` file."""

    def supports_database(self, database_key: str) -> bool:
        return not self.supported_databases or database_key in self.supported_databases

    def compose_service(self, ctx: ScaffoldContext) -> dict[str, Any]:
        service: dict[str, Any] = {
            "build": {"context": f"./{self.root_dir}"},
            "ports": [f"{ctx.api_port}:{ctx.api_port}"],
            "env_file": [f"./{self.root_dir}/.env"],
        }
        if ctx.needs_database:
            service["depends_on"] = {"db": {"condition": "service_healthy"}}
        return service


class DatabaseAdapter(TechnologyAdapter):
    """A relational database engine."""

    kind = AdapterKind.DATABASE
    requires_service = True

    @abstractmethod
    def connection_url(self, ctx: ScaffoldContext, *, host: str = "localhost") -> str:
        """Connection URL for application configuration."""

    @abstractmethod
    def sql_dialect_notes(self) -> str:
        """Prompt fragment describing dialect-specific SQL rules."""

    @abstractmethod
    def type_mapping(self) -> dict[str, str]:
        """Canonical logical type -> dialect-native column type."""

    def compose_service(self, ctx: ScaffoldContext) -> dict[str, Any] | None:
        """Compose service definition, or None for embedded engines."""
        return None
