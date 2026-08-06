"""FastAPI backend adapter."""

from __future__ import annotations

from app.adapters.base import BackendAdapter, ScaffoldContext, ScaffoldFile


class FastAPIAdapter(BackendAdapter):
    key = "fastapi"
    display_name = "FastAPI"
    language = "Python"
    version = "0.115"
    description = (
        "Async Python framework with automatic OpenAPI generation and Pydantic "
        "validation. Fast to build, strongly typed, excellent for data and AI work."
    )
    tags = ("python", "async", "openapi", "type-safe")
    best_for = (
        "Data-intensive and AI-backed services",
        "Teams working in Python",
        "APIs where a generated OpenAPI contract matters",
    )
    supported_databases = ("postgresql", "mysql", "sqlite")

    _DRIVERS = {
        "postgresql": ("asyncpg", "postgresql+asyncpg"),
        "mysql": ("aiomysql", "mysql+aiomysql"),
        "sqlite": ("aiosqlite", "sqlite+aiosqlite"),
    }

    def _driver(self, database_key: str | None) -> tuple[str, str]:
        return self._DRIVERS.get(database_key or "sqlite", self._DRIVERS["sqlite"])

    def scaffold(self, ctx: ScaffoldContext) -> list[ScaffoldFile]:
        package, dialect = self._driver(ctx.database_key)
        files: list[ScaffoldFile] = []

        db_deps = ""
        if ctx.needs_database:
            db_deps = (
                f'    "sqlalchemy[asyncio]>=2.0.36",\n'
                f'    "{package}>=0.20.0",\n'
                f'    "alembic>=1.14.0",\n'
                f'    "greenlet>=3.1.0",\n'
            )
        auth_deps = ""
        if ctx.needs_auth:
            auth_deps = '    "pyjwt>=2.10.0",\n    "bcrypt>=4.2.0",\n'

        files.append(
            ScaffoldFile(
                path="backend/pyproject.toml",
                description="Python project metadata and pinned dependencies.",
                content=f"""[project]
name = "{ctx.package_name}-api"
version = "0.1.0"
description = "{ctx.description[:180]}"
requires-python = ">=3.11"

dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "pydantic>=2.9.0",
    "pydantic-settings>=2.6.0",
    "python-multipart>=0.0.17",
{db_deps}{auth_deps}]

[project.optional-dependencies]
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.24.0",
    "httpx>=0.27.0",
    "ruff>=0.8.0",
]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["app*"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "SIM"]
""",
            )
        )

        files.append(
            ScaffoldFile(
                path="backend/requirements.txt",
                description="Pinned dependency list for environments without PEP 621 support.",
                content=self._requirements(ctx, package),
            )
        )

        files.append(
            ScaffoldFile(
                path="backend/Dockerfile",
                description="Production container image for the API.",
                content=self.dockerfile(ctx),
            )
        )

        files.append(
            ScaffoldFile(
                path="backend/.dockerignore",
                description="Build-context exclusions.",
                content="__pycache__/\n*.py[cod]\n.venv/\nvenv/\n.env\n.pytest_cache/\n"
                ".ruff_cache/\n*.db\n.git/\ntests/\n",
            )
        )

        database_url = "" if not ctx.needs_database else self._database_url(ctx, dialect)
        files.append(
            ScaffoldFile(
                path="backend/.env.example",
                description="Documented environment variables. Copy to `.env`.",
                content=self.env_template(ctx, database_url),
            )
        )

        files.append(
            ScaffoldFile(
                path="backend/app/__init__.py",
                description="Application package marker.",
                content='"""API application package."""\n',
            )
        )

        return files

    def _requirements(self, ctx: ScaffoldContext, driver: str) -> str:
        lines = [
            "fastapi>=0.115.0",
            "uvicorn[standard]>=0.32.0",
            "pydantic>=2.9.0",
            "pydantic-settings>=2.6.0",
            "python-multipart>=0.0.17",
        ]
        if ctx.needs_database:
            lines += [
                "sqlalchemy[asyncio]>=2.0.36",
                f"{driver}>=0.20.0",
                "alembic>=1.14.0",
                "greenlet>=3.1.0",
            ]
        if ctx.needs_auth:
            lines += ["pyjwt>=2.10.0", "bcrypt>=4.2.0"]
        return "\n".join(lines) + "\n"

    def _database_url(self, ctx: ScaffoldContext, dialect: str) -> str:
        if ctx.database_key == "sqlite":
            return f"{dialect}:///./{ctx.package_name}.db"
        port = "5432" if ctx.database_key == "postgresql" else "3306"
        return (
            f"{dialect}://{ctx.package_name}:{ctx.package_name}_password"
            f"@localhost:{port}/{ctx.package_name}"
        )

    def env_template(self, ctx: ScaffoldContext, database_url: str) -> str:
        lines = [
            "# Application",
            f'APP_NAME="{ctx.project_name}"',
            "ENVIRONMENT=development",
            "DEBUG=true",
            f"API_PORT={ctx.api_port}",
            "LOG_LEVEL=INFO",
            "",
            "# CORS — comma-separated origins allowed to call this API",
            f"CORS_ORIGINS=http://localhost:{ctx.web_port}",
        ]
        if ctx.needs_database:
            lines += ["", "# Database", f"DATABASE_URL={database_url}"]
        if ctx.needs_auth:
            lines += [
                "",
                "# Authentication",
                "# Generate with: python -c \"import secrets; print(secrets.token_urlsafe(48))\"",
                "SECRET_KEY=change-me-before-deploying",
                "ACCESS_TOKEN_TTL_MINUTES=720",
                "JWT_ALGORITHM=HS256",
            ]
        return "\n".join(lines) + "\n"

    def dockerfile(self, ctx: ScaffoldContext) -> str:
        return f"""# syntax=docker/dockerfile:1

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \\
    PYTHONUNBUFFERED=1 \\
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies are installed in their own layer so application edits do not
# invalidate the cached install.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Run as a non-root user.
RUN useradd --create-home --uid 1001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE {ctx.api_port}

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \\
    CMD python -c "import urllib.request,sys; \\
sys.exit(0 if urllib.request.urlopen('http://localhost:{ctx.api_port}/health').status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "{ctx.api_port}"]
"""

    def conventions(self, ctx: ScaffoldContext) -> str:
        _, dialect = self._driver(ctx.database_key)
        sections = [
            "FastAPI backend conventions. Generated code MUST follow these exactly.",
            "",
            "## Layout — every file goes under `backend/app/`",
            "```",
            "backend/app/",
            "  main.py                 FastAPI instance, middleware, router mounting, lifespan",
            "  core/config.py          Settings via pydantic-settings, read from environment",
            "  core/exceptions.py      Domain exceptions + registered handlers",
            "  api/v1/router.py        Aggregates every resource router",
            "  api/v1/routes/<res>.py  One module per resource, thin HTTP layer only",
            "  api/deps.py             Shared FastAPI dependencies",
            "  schemas/<res>.py        Pydantic request/response models",
            "  services/<res>_service.py   Business logic, no HTTP or SQL imports",
        ]
        if ctx.needs_database:
            sections += [
                "  models/<res>.py         SQLAlchemy 2.0 ORM models",
                "  repositories/<res>_repository.py  All SQL lives here",
                "  db/session.py           Async engine + get_session dependency",
                "  db/base.py              DeclarativeBase",
            ]
        if ctx.needs_auth:
            sections.append("  core/security.py        Password hashing + JWT encode/decode")
        sections += [
            "```",
            "",
            "## Non-negotiable rules",
            "1. Layering is strict: routes -> services -> repositories. A route never "
            "writes SQL; a service never imports `fastapi`.",
            "2. Use SQLAlchemy 2.0 typed mappings (`Mapped[...]`, `mapped_column(...)`). "
            "Never the legacy `Column(...)` declarative style.",
            "3. All I/O is `async def`. Database calls are awaited.",
            "4. Dependencies are injected with `Depends(...)`, never constructed inline "
            "inside a handler.",
            "5. Every route declares an explicit `response_model` and `status_code`.",
            "6. Pydantic v2 syntax: `model_config = ConfigDict(from_attributes=True)`, "
            "`field_validator`, `model_validator`. Never v1 `class Config` or `@validator`.",
            "7. Settings come from `core/config.py`; never call `os.getenv` outside it.",
            "8. Raise domain exceptions from services; let registered handlers convert "
            "them to responses. No `HTTPException` inside services.",
            "9. Every module and public function carries a concise docstring.",
            "10. Full type annotations on every signature.",
        ]
        if ctx.needs_database:
            sections += [
                "",
                "## Database",
                f"- Async engine URL scheme: `{dialect}://...`, read from `DATABASE_URL`.",
                "- Session dependency yields `AsyncSession`, commits on success, "
                "rolls back on exception.",
                "- Repositories accept an `AsyncSession` in `__init__`.",
                "- ORM models must match the SQL schema already produced for this "
                "project — same table names, same columns, same constraints.",
            ]
        if ctx.needs_auth:
            sections += [
                "",
                "## Authentication",
                "- Passwords hashed with bcrypt. Never store or log plaintext.",
                "- JWT access tokens carry `sub`, `exp`, `iat`. Verified in a "
                "`get_current_user` dependency in `api/deps.py`.",
                "- Protected routes depend on `get_current_user`.",
                "- Auth failures raise `AuthenticationError`, never a bare 500.",
            ]
        sections += [
            "",
            "## Do not generate",
            "`pyproject.toml`, `requirements.txt`, `Dockerfile`, `.env.example` — these "
            "already exist in the scaffold and must not be recreated or modified.",
        ]
        return "\n".join(sections)
