"""MySQL database adapter."""

from __future__ import annotations

from typing import Any

from app.adapters.base import DatabaseAdapter, ScaffoldContext, ScaffoldFile


class MySQLAdapter(DatabaseAdapter):
    key = "mysql"
    display_name = "MySQL"
    language = "SQL"
    version = "8.4"
    description = (
        "Widely deployed relational database with broad hosting support and "
        "a large operational ecosystem."
    )
    tags = ("relational", "acid", "widely-hosted")
    best_for = (
        "Teams with existing MySQL operations",
        "Shared or budget hosting environments",
        "Read-heavy web applications",
    )

    def connection_url(self, ctx: ScaffoldContext, *, host: str = "localhost") -> str:
        return (
            f"mysql://{ctx.package_name}:{ctx.package_name}_password"
            f"@{host}:3306/{ctx.package_name}"
        )

    def type_mapping(self) -> dict[str, str]:
        return {
            "id": "BIGINT AUTO_INCREMENT",
            "uuid": "CHAR(36)",
            "string": "VARCHAR(255)",
            "text": "TEXT",
            "integer": "INT",
            "bigint": "BIGINT",
            "decimal": "DECIMAL(12, 2)",
            "boolean": "TINYINT(1)",
            "date": "DATE",
            "timestamp": "DATETIME",
            "json": "JSON",
            "enum": "VARCHAR(50)",
        }

    def sql_dialect_notes(self) -> str:
        return (
            "MySQL 8.4 dialect rules:\n"
            "- Auto-increment keys use `BIGINT AUTO_INCREMENT PRIMARY KEY`.\n"
            "- Every table declares `ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 "
            "COLLATE=utf8mb4_unicode_ci`.\n"
            "- `VARCHAR` columns must always state a length.\n"
            "- Booleans are `TINYINT(1)`.\n"
            "- Timestamps use `DATETIME` with `DEFAULT CURRENT_TIMESTAMP`; "
            "updated columns add `ON UPDATE CURRENT_TIMESTAMP`.\n"
            "- Indexed `VARCHAR` columns stay at or below 191 characters so the "
            "index fits within the utf8mb4 key-length limit.\n"
            "- Foreign keys are declared inline with explicit `ON DELETE`.\n"
            "- Identifiers are snake_case; table names are plural."
        )

    def compose_service(self, ctx: ScaffoldContext) -> dict[str, Any]:
        return {
            "image": "mysql:8.4",
            "restart": "unless-stopped",
            "environment": {
                "MYSQL_ROOT_PASSWORD": "root_password",
                "MYSQL_USER": ctx.package_name,
                "MYSQL_PASSWORD": f"{ctx.package_name}_password",
                "MYSQL_DATABASE": ctx.package_name,
            },
            "ports": ["3306:3306"],
            "volumes": [
                "mysql_data:/var/lib/mysql",
                "./database/schema.sql:/docker-entrypoint-initdb.d/01-schema.sql:ro",
                "./database/seed.sql:/docker-entrypoint-initdb.d/02-seed.sql:ro",
            ],
            "healthcheck": {
                "test": ["CMD", "mysqladmin", "ping", "-h", "localhost"],
                "interval": "10s",
                "timeout": "5s",
                "retries": 10,
            },
        }

    def scaffold(self, ctx: ScaffoldContext) -> list[ScaffoldFile]:
        return [
            ScaffoldFile(
                path="database/README.md",
                description="Database setup and migration instructions.",
                content=f"""# Database — {ctx.project_name}

MySQL {self.version}.

## Files

| File | Purpose |
|------|---------|
| `schema.sql` | Full DDL: tables, constraints, indexes. |
| `seed.sql` | Minimal reference data for local development. |
| `migrations/` | Ordered, forward-only migration scripts. |

## Running with Docker

```bash
docker compose up -d db
```

The schema and seed scripts are mounted into the MySQL entrypoint and run
automatically the first time the data volume is created.

## Running against an existing server

```bash
mysql -u root -p -e "CREATE DATABASE {ctx.package_name} \\
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql -u root -p {ctx.package_name} < database/schema.sql
mysql -u root -p {ctx.package_name} < database/seed.sql
```

## Connection string

```
{self.connection_url(ctx)}
```

Override via the `DATABASE_URL` environment variable.
""",
            )
        ]

    def conventions(self, ctx: ScaffoldContext) -> str:
        return self.sql_dialect_notes()
