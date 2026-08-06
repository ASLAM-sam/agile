"""Technology adapter contracts and scaffold correctness."""

from __future__ import annotations

import json

import pytest

from app.adapters.base import ScaffoldContext
from app.adapters.registry import AdapterRegistry
from app.core.enums import AdapterKind
from app.core.exceptions import AdapterNotFoundError
from app.packaging.workspace import normalise_path


@pytest.fixture
def ctx() -> ScaffoldContext:
    return ScaffoldContext(
        project_name="Hospital Manager",
        project_slug="hospital-manager",
        description="Manage patients, appointments and staff.",
        needs_auth=True,
        needs_database=True,
        needs_api=True,
        needs_backend=True,
        needs_frontend=True,
        frontend_key="react",
        backend_key="fastapi",
        database_key="postgresql",
        entities=["Patient", "Appointment"],
    )


class TestRegistry:
    def test_every_first_party_adapter_is_registered(self, adapters: AdapterRegistry) -> None:
        assert set(adapters.keys(AdapterKind.FRONTEND)) == {"react", "nextjs", "angular"}
        assert set(adapters.keys(AdapterKind.BACKEND)) == {"fastapi", "express", "spring-boot"}
        assert set(adapters.keys(AdapterKind.DATABASE)) == {"postgresql", "mysql", "sqlite"}

    def test_unknown_adapter_reports_the_alternatives(self, adapters: AdapterRegistry) -> None:
        with pytest.raises(AdapterNotFoundError) as caught:
            adapters.get(AdapterKind.FRONTEND, "svelte")

        assert "react" in str(caught.value)

    def test_duplicate_registration_is_rejected(self, adapters: AdapterRegistry) -> None:
        from app.adapters.frontend.react import ReactAdapter

        with pytest.raises(ValueError, match="already registered"):
            adapters.register(ReactAdapter())

    def test_catalogue_covers_every_kind(self, adapters: AdapterRegistry) -> None:
        catalogue = adapters.catalogue()
        assert set(catalogue) == {"frontend", "backend", "database"}
        assert all(len(entries) == 3 for entries in catalogue.values())


class TestScaffolds:
    @pytest.mark.parametrize(
        ("kind", "key"),
        [
            (AdapterKind.FRONTEND, "react"),
            (AdapterKind.FRONTEND, "nextjs"),
            (AdapterKind.FRONTEND, "angular"),
            (AdapterKind.BACKEND, "fastapi"),
            (AdapterKind.BACKEND, "express"),
            (AdapterKind.BACKEND, "spring-boot"),
            (AdapterKind.DATABASE, "postgresql"),
            (AdapterKind.DATABASE, "mysql"),
            (AdapterKind.DATABASE, "sqlite"),
        ],
    )
    def test_scaffold_paths_are_safe_and_content_is_present(
        self, adapters: AdapterRegistry, ctx: ScaffoldContext, kind: AdapterKind, key: str
    ) -> None:
        """Every emitted file must survive path normalisation and be non-empty."""
        ctx.frontend_key = key if kind is AdapterKind.FRONTEND else ctx.frontend_key
        ctx.backend_key = key if kind is AdapterKind.BACKEND else ctx.backend_key
        ctx.database_key = key if kind is AdapterKind.DATABASE else ctx.database_key

        files = adapters.get(kind, key).scaffold(ctx)
        assert files, f"{key} produced no scaffold files"

        seen: set[str] = set()
        for entry in files:
            assert normalise_path(entry.path) == entry.path, f"unsafe path: {entry.path}"
            assert entry.path not in seen, f"duplicate path: {entry.path}"
            seen.add(entry.path)
            if not entry.path.endswith(".gitkeep"):
                assert entry.content.strip(), f"empty content: {entry.path}"

    @pytest.mark.parametrize("key", ["react", "nextjs", "angular"])
    def test_frontend_package_json_is_valid_and_pinned(
        self, adapters: AdapterRegistry, ctx: ScaffoldContext, key: str
    ) -> None:
        ctx.frontend_key = key
        files = {f.path: f.content for f in adapters.frontend(key).scaffold(ctx)}

        manifest = json.loads(files["frontend/package.json"])
        assert manifest["name"] == "hospital-manager-web"
        assert "build" in manifest["scripts"]
        assert manifest["dependencies"], "dependencies must not be empty"
        # Every dependency must carry an explicit version specifier.
        for spec in {**manifest["dependencies"], **manifest["devDependencies"]}.values():
            assert spec and spec[0] in "^~0123456789", f"unpinned dependency: {spec}"

    def test_fastapi_scaffold_reflects_capabilities(
        self, adapters: AdapterRegistry, ctx: ScaffoldContext
    ) -> None:
        files = {f.path: f.content for f in adapters.backend("fastapi").scaffold(ctx)}

        assert "sqlalchemy" in files["backend/requirements.txt"]
        assert "asyncpg" in files["backend/requirements.txt"]
        assert "bcrypt" in files["backend/requirements.txt"]
        assert "DATABASE_URL" in files["backend/.env.example"]
        assert "SECRET_KEY" in files["backend/.env.example"]

    def test_fastapi_scaffold_omits_unneeded_dependencies(
        self, adapters: AdapterRegistry, ctx: ScaffoldContext
    ) -> None:
        """A project with no database must not ship database dependencies."""
        ctx.needs_database = False
        ctx.needs_auth = False
        ctx.database_key = None

        files = {f.path: f.content for f in adapters.backend("fastapi").scaffold(ctx)}
        requirements = files["backend/requirements.txt"]

        assert "sqlalchemy" not in requirements
        assert "bcrypt" not in requirements
        assert "DATABASE_URL" not in files["backend/.env.example"]

    def test_express_uses_esm_and_strict_typescript(
        self, adapters: AdapterRegistry, ctx: ScaffoldContext
    ) -> None:
        files = {f.path: f.content for f in adapters.backend("express").scaffold(ctx)}

        manifest = json.loads(files["backend/package.json"])
        assert manifest["type"] == "module"

        tsconfig = json.loads(files["backend/tsconfig.json"])
        assert tsconfig["compilerOptions"]["strict"] is True

    def test_every_dockerfile_runs_as_non_root(
        self, adapters: AdapterRegistry, ctx: ScaffoldContext
    ) -> None:
        """Containers must not run as root."""
        for kind, key in [
            (AdapterKind.BACKEND, "fastapi"),
            (AdapterKind.BACKEND, "express"),
            (AdapterKind.BACKEND, "spring-boot"),
        ]:
            ctx.backend_key = key
            adapter = adapters.get(kind, key)
            dockerfile = adapter.dockerfile(ctx)  # type: ignore[attr-defined]
            assert "USER " in dockerfile, f"{key} Dockerfile does not drop root"
            assert "HEALTHCHECK" in dockerfile, f"{key} Dockerfile has no health check"


class TestConventions:
    @pytest.mark.parametrize(
        ("kind", "key"),
        [
            (AdapterKind.FRONTEND, "react"),
            (AdapterKind.FRONTEND, "nextjs"),
            (AdapterKind.FRONTEND, "angular"),
            (AdapterKind.BACKEND, "fastapi"),
            (AdapterKind.BACKEND, "express"),
            (AdapterKind.BACKEND, "spring-boot"),
        ],
    )
    def test_conventions_forbid_regenerating_the_scaffold(
        self, adapters: AdapterRegistry, ctx: ScaffoldContext, kind: AdapterKind, key: str
    ) -> None:
        """Agents must be told not to recreate build tooling."""
        conventions = adapters.get(kind, key).conventions(ctx)

        assert len(conventions) > 500, "conventions are too thin to guide generation"
        assert "Do not generate" in conventions

    def test_database_dialect_notes_are_specific(self, adapters: AdapterRegistry) -> None:
        postgres = adapters.database("postgresql").sql_dialect_notes()
        mysql = adapters.database("mysql").sql_dialect_notes()
        sqlite = adapters.database("sqlite").sql_dialect_notes()

        assert "BIGSERIAL" in postgres and "JSONB" in postgres
        assert "AUTO_INCREMENT" in mysql and "utf8mb4" in mysql
        assert "AUTOINCREMENT" in sqlite and "foreign_keys" in sqlite

    def test_type_mappings_cover_the_canonical_types(self, adapters: AdapterRegistry) -> None:
        required = {"id", "string", "integer", "boolean", "timestamp", "json"}
        for key in ("postgresql", "mysql", "sqlite"):
            mapping = adapters.database(key).type_mapping()
            assert required <= set(mapping), f"{key} is missing canonical types"


class TestCompatibility:
    def test_backends_declare_database_support(self, adapters: AdapterRegistry) -> None:
        for key in ("fastapi", "express", "spring-boot"):
            adapter = adapters.backend(key)
            assert adapter.supports_database("postgresql")
            assert not adapter.supports_database("mongodb")
