"""SQLite database adapter — embedded, zero-configuration."""

from __future__ import annotations

from app.adapters.base import DatabaseAdapter, ScaffoldContext, ScaffoldFile


class SQLiteAdapter(DatabaseAdapter):
    key = "sqlite"
    display_name = "SQLite"
    language = "SQL"
    version = "3"
    description = (
        "Embedded, file-backed database requiring no server process. Ideal for "
        "prototypes, internal tools and single-node deployments."
    )
    tags = ("relational", "embedded", "zero-config")
    best_for = (
        "Prototypes and MVPs",
        "Single-user or internal tools",
        "Deployments where operating a database server is unwarranted",
    )
    requires_service = False
    catalogue_priority = 2

    def connection_url(self, ctx: ScaffoldContext, *, host: str = "localhost") -> str:
        return f"sqlite:///./{ctx.package_name}.db"

    def type_mapping(self) -> dict[str, str]:
        return {
            "id": "INTEGER",
            "uuid": "TEXT",
            "string": "TEXT",
            "text": "TEXT",
            "integer": "INTEGER",
            "bigint": "INTEGER",
            "decimal": "NUMERIC",
            "boolean": "INTEGER",
            "date": "TEXT",
            "timestamp": "TEXT",
            "json": "TEXT",
            "enum": "TEXT",
        }

    def sql_dialect_notes(self) -> str:
        return (
            "SQLite dialect rules:\n"
            "- Auto-increment keys use `INTEGER PRIMARY KEY AUTOINCREMENT`.\n"
            "- SQLite has no native boolean, date or JSON type: use `INTEGER` "
            "for booleans (0/1) and `TEXT` for ISO-8601 timestamps and JSON.\n"
            "- Timestamps default with `DEFAULT (datetime('now'))`.\n"
            "- Foreign keys are only enforced when `PRAGMA foreign_keys = ON` "
            "is issued per connection; the schema file must begin with it.\n"
            "- `ALTER TABLE` support is limited, so migrations that change a "
            "column recreate the table and copy the data.\n"
            "- Add explicit `CREATE INDEX` statements; SQLite indexes only "
            "primary keys automatically.\n"
            "- Identifiers are snake_case; table names are plural."
        )

    def scaffold(self, ctx: ScaffoldContext) -> list[ScaffoldFile]:
        return [
            ScaffoldFile(
                path="database/README.md",
                description="Database setup and migration instructions.",
                content=f"""# Database — {ctx.project_name}

SQLite {self.version}. The database is a single file; no server is required.

## Files

| File | Purpose |
|------|---------|
| `schema.sql` | Full DDL: tables, constraints, indexes. |
| `seed.sql` | Minimal reference data for local development. |
| `migrations/` | Ordered, forward-only migration scripts. |

## Initialising

```bash
sqlite3 {ctx.package_name}.db < database/schema.sql
sqlite3 {ctx.package_name}.db < database/seed.sql
```

## Applying migrations

```bash
for f in database/migrations/*.sql; do sqlite3 {ctx.package_name}.db < "$f"; done
```

## Connection string

```
{self.connection_url(ctx)}
```

## Operational notes

- `PRAGMA foreign_keys = ON` must be issued on every connection; the schema
  file sets it, and the application configures it at connection time.
- The database file is git-ignored. Delete it to start from a clean slate.
- SQLite serialises writes. For concurrent, document-oriented workloads,
  choose MongoDB when selecting the generated-project stack.
""",
            )
        ]

    def conventions(self, ctx: ScaffoldContext) -> str:
        return self.sql_dialect_notes()
