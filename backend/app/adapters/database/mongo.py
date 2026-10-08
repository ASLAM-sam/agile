"""MongoDB database adapter — document storage with Docker Compose support."""

from __future__ import annotations

from typing import Any

from app.adapters.base import DatabaseAdapter, ScaffoldContext, ScaffoldFile


class MongoDBAdapter(DatabaseAdapter):
    key = "mongodb"
    display_name = "MongoDB"
    language = "JavaScript"
    version = "8"
    description = (
        "Document database for evolving, nested application data with explicit "
        "collection validation and query-oriented indexes."
    )
    tags = ("document", "nosql", "collections", "flexible-schema")
    best_for = (
        "Evolving or nested document data",
        "Content, catalogue and event-oriented applications",
        "Concurrent applications that need a managed database service",
    )
    catalogue_priority = 1
    schema_filename = "schema.js"
    seed_filename = "seed.js"
    migration_extension = ".js"
    comment_prefix = "//"

    def connection_url(self, ctx: ScaffoldContext, *, host: str = "localhost") -> str:
        return f"mongodb://{host}:27017/{ctx.package_name}"

    def type_mapping(self) -> dict[str, str]:
        return {
            "id": "ObjectId",
            "uuid": "string",
            "string": "string",
            "text": "string",
            "integer": "int",
            "bigint": "long",
            "decimal": "decimal",
            "boolean": "bool",
            "date": "date",
            "timestamp": "date",
            "json": "object",
            "enum": "string",
        }

    def sql_dialect_notes(self) -> str:
        return self.document_design_notes()

    @staticmethod
    def document_design_notes() -> str:
        return (
            "MongoDB document design rules:\n"
            "- Model collections, document shapes, `$jsonSchema` validators and indexes; do not emit SQL.\n"
            "- Embed values read and written with their parent. Store references only for independently "
            "queried, high-cardinality or many-to-many data.\n"
            "- Include `createdAt` and `updatedAt` dates on every top-level document.\n"
            "- Use `ObjectId` for `_id` and reference fields unless an external stable identifier is required.\n"
            "- Create indexes for every common filter, sort, uniqueness rule and referenced identifier.\n"
            "- `schema.js`, `seed.js` and migration scripts run with `mongosh`; scripts must be idempotent "
            "where practical and use the project database selected below."
        )

    def compose_service(self, ctx: ScaffoldContext) -> dict[str, Any]:
        return {
            "image": "mongo:8",
            "ports": ["27017:27017"],
            "environment": {"MONGO_INITDB_DATABASE": ctx.package_name},
            "volumes": [
                "mongodb_data:/data/db",
                f"./database/{self.schema_filename}:/docker-entrypoint-initdb.d/01-schema.js:ro",
                f"./database/{self.seed_filename}:/docker-entrypoint-initdb.d/02-seed.js:ro",
            ],
            "healthcheck": {
                "test": ["CMD", "mongosh", "--quiet", "--eval", "db.runCommand({ ping: 1 }).ok"],
                "interval": "10s",
                "timeout": "5s",
                "retries": 10,
            },
        }

    def scaffold(self, ctx: ScaffoldContext) -> list[ScaffoldFile]:
        return [
            ScaffoldFile(
                path="database/README.md",
                description="MongoDB setup, collection validation and migration instructions.",
                content=f"""# Database — {ctx.project_name}

MongoDB {self.version} stores the generated project's documents in collections.

## Files

| File | Purpose |
|------|---------|
| `schema.js` | Creates collections, `$jsonSchema` validators and indexes. |
| `seed.js` | Inserts minimal reference documents for local development. |
| `migrations/` | Ordered, forward-only `mongosh` migration scripts. |

## Initialising locally

```bash
mongosh {self.connection_url(ctx)} database/schema.js
mongosh {self.connection_url(ctx)} database/seed.js
```

## Applying migrations

```bash
for f in database/migrations/*.js; do mongosh {self.connection_url(ctx)} "$f"; done
```

## Connection string

```
{self.connection_url(ctx)}
```

## Operational notes

- The Compose service initialises a fresh volume using `schema.js` then `seed.js`.
- Collection validators are guardrails, not a substitute for API validation.
- Create an index before relying on a collection field for filtering or sorting.
- Use `mongodb+srv://...` in production when your managed MongoDB provider supplies it.
""",
            )
        ]

    def conventions(self, ctx: ScaffoldContext) -> str:
        return self.document_design_notes()
