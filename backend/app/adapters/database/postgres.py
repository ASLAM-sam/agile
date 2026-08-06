"""PostgreSQL database adapter."""

from __future__ import annotations

from typing import Any

from app.adapters.base import DatabaseAdapter, ScaffoldContext, ScaffoldFile


class PostgresAdapter(DatabaseAdapter):
    key = "postgresql"
    display_name = "PostgreSQL"
    language = "SQL"
    version = "16"
    description = (
        "Production-grade relational database with strong ACID guarantees, rich "
        "indexing, JSONB support and mature tooling."
    )
    tags = ("relational", "acid", "jsonb", "production")
    best_for = (
        "Transactional systems",
        "Complex relational models",
        "Applications needing JSON and relational data together",
    )

    def connection_url(self, ctx: ScaffoldContext, *, host: str = "localhost") -> str:
        return (
            f"postgresql://{ctx.package_name}:{ctx.package_name}_password"
            f"@{host}:5432/{ctx.package_name}"
        )

    def type_mapping(self) -> dict[str, str]:
        return {
            "id": "BIGSERIAL",
            "uuid": "UUID",
            "string": "VARCHAR",
            "text": "TEXT",
            "integer": "INTEGER",
            "bigint": "BIGINT",
            "decimal": "NUMERIC(12, 2)",
            "boolean": "BOOLEAN",
            "date": "DATE",
            "timestamp": "TIMESTAMPTZ",
            "json": "JSONB",
            "enum": "VARCHAR",
        }

    def sql_dialect_notes(self) -> str:
        return (
            "PostgreSQL 16 dialect rules:\n"
            "- Auto-increment primary keys use `BIGSERIAL PRIMARY KEY`.\n"
            "- Timestamps use `TIMESTAMPTZ`; default with `DEFAULT NOW()`.\n"
            "- Use `JSONB`, never `JSON`, for document columns.\n"
            "- Enumerated values use `VARCHAR` plus a `CHECK (col IN (...))` "
            "constraint rather than native `CREATE TYPE`, so migrations stay "
            "reversible without dropping dependent objects.\n"
            "- Every foreign key declares `ON DELETE` behaviour explicitly.\n"
            "- Index every foreign key column and every column used in a WHERE "
            "clause of a listed query.\n"
            "- Identifiers are snake_case; table names are plural."
        )

    def compose_service(self, ctx: ScaffoldContext) -> dict[str, Any]:
        return {
            "image": "postgres:16-alpine",
            "restart": "unless-stopped",
            "environment": {
                "POSTGRES_USER": ctx.package_name,
                "POSTGRES_PASSWORD": f"{ctx.package_name}_password",
                "POSTGRES_DB": ctx.package_name,
            },
            "ports": ["5432:5432"],
            "volumes": [
                "postgres_data:/var/lib/postgresql/data",
                "./database/schema.sql:/docker-entrypoint-initdb.d/01-schema.sql:ro",
                "./database/seed.sql:/docker-entrypoint-initdb.d/02-seed.sql:ro",
            ],
            "healthcheck": {
                "test": ["CMD-SHELL", f"pg_isready -U {ctx.package_name}"],
                "interval": "10s",
                "timeout": "5s",
                "retries": 5,
            },
        }

    def scaffold(self, ctx: ScaffoldContext) -> list[ScaffoldFile]:
        return [
            ScaffoldFile(
                path="database/README.md",
                description="Database setup and migration instructions.",
                content=f"""# Database — {ctx.project_name}

PostgreSQL {self.version}.

## Files

| File | Purpose |
|------|---------|
| `schema.sql` | Full DDL: tables, constraints, indexes. |
| `seed.sql` | Minimal reference data for local development. |
| `migrations/` | Ordered, forward-only migration scripts. |

## Running with Docker

The Compose stack mounts `schema.sql` and `seed.sql` into the Postgres
entrypoint, so a fresh volume is initialised automatically:

```bash
docker compose up -d db
```

## Running against an existing server

```bash
createdb {ctx.package_name}
psql -d {ctx.package_name} -f database/schema.sql
psql -d {ctx.package_name} -f database/seed.sql
```

## Applying migrations

Migrations are forward-only and numbered. Apply them in filename order:

```bash
for f in database/migrations/*.sql; do psql -d {ctx.package_name} -f "$f"; done
```

## Connection string

```
{self.connection_url(ctx)}
```

Override via the `DATABASE_URL` environment variable. Never commit real
credentials — `.env` is git-ignored and `.env.example` documents the shape.
""",
            )
        ]

    def conventions(self, ctx: ScaffoldContext) -> str:
        return self.sql_dialect_notes()
