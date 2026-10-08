"""Database Engineer agent.

Skipped entirely when the Business Analyst determined no persistence is
required — a portfolio site gets no schema, no migrations and no `database/`
directory.
"""

from __future__ import annotations

from app.agents.base import CodeAgent
from app.agents.context import AgentContext
from app.agents.results import AgentResult, SkipDecision
from app.core.enums import AgentRole, ArtifactKind
from app.llm import schema as s
from app.workflow.memory import DatabaseDesign

SCHEMA_DESIGN_SCHEMA = s.obj(
    {
        "tables": s.array(
            s.obj(
                {
                    "name": s.string("Table name: plural, snake_case."),
                    "purpose": s.string("What this table stores."),
                    "columns": s.array(
                        s.obj(
                            {
                                "name": s.string("Column name, snake_case."),
                                "type": s.string("Dialect-native column type."),
                                "nullable": s.boolean("Whether NULL is permitted."),
                                "description": s.string("What this column holds."),
                                "constraint": s.string(
                                    "Inline constraint such as PRIMARY KEY, UNIQUE, "
                                    "a CHECK expression, or a DEFAULT. Empty if none."
                                ),
                            }
                        )
                    ),
                }
            ),
            description="Every table in the schema.",
        ),
        "relationships": s.array(
            s.obj(
                {
                    "from_table": s.string("Table holding the foreign key."),
                    "from_column": s.string("Foreign key column."),
                    "to_table": s.string("Referenced table."),
                    "to_column": s.string("Referenced column, normally 'id'."),
                    "cardinality": s.string(
                        "Relationship cardinality.",
                        enum=["one-to-one", "one-to-many", "many-to-many"],
                    ),
                    "on_delete": s.string(
                        "Referential action.",
                        enum=["CASCADE", "RESTRICT", "SET NULL", "NO ACTION"],
                    ),
                }
            )
        ),
        "indexes": s.array(
            s.obj(
                {
                    "name": s.string("Index name, e.g. 'idx_appointments_patient_id'."),
                    "table": s.string("Table being indexed."),
                    "columns": s.string_array("Columns, in index order."),
                    "unique": s.boolean("Whether the index enforces uniqueness."),
                    "rationale": s.string("The query this index serves."),
                }
            )
        ),
        "schema_sql": s.string(
            "Complete, executable DDL: every CREATE TABLE with all constraints, "
            "then every CREATE INDEX. Ordered so no statement references a table "
            "that does not yet exist. Must run without modification."
        ),
        "seed_sql": s.string(
            "INSERT statements providing minimal, realistic reference data for "
            "local development. Ordered to respect foreign keys."
        ),
        "migrations": s.array(
            s.obj(
                {
                    "filename": s.string("e.g. '001_initial_schema.sql'."),
                    "description": s.string("What this migration does."),
                    "sql": s.string("The migration's SQL."),
                }
            ),
            description="Forward-only, numbered migrations. The first is the full schema.",
        ),
        "notes": s.string("Design decisions, normalisation choices and trade-offs."),
    }
)

MONGO_SCHEMA_DESIGN_SCHEMA = s.obj(
    {
        "collections": s.array(
            s.obj(
                {
                    "name": s.string("Collection name: plural, snake_case."),
                    "purpose": s.string("What this collection stores."),
                    "document_shape": s.array(
                        s.obj(
                            {
                                "name": s.string("Field name, including nested paths where useful."),
                                "type": s.string("MongoDB BSON type or ObjectId reference."),
                                "required": s.boolean("Whether the validator requires this field."),
                                "description": s.string("What this field holds."),
                            }
                        )
                    ),
                    "relationships": s.string(
                        "Embedding/reference choice and its rationale. Empty if independent."
                    ),
                }
            ),
            description="Every collection required by the application.",
        ),
        "indexes": s.array(
            s.obj(
                {
                    "name": s.string("Index name."),
                    "collection": s.string("Collection being indexed."),
                    "fields": s.string_array("Fields, in index order."),
                    "unique": s.boolean("Whether the index enforces uniqueness."),
                    "rationale": s.string("The query or constraint this index serves."),
                }
            )
        ),
        "schema_script": s.string(
            "Complete executable mongosh JavaScript. Select the project database, create or modify "
            "every collection with a $jsonSchema validator, then create every index."
        ),
        "seed_script": s.string(
            "Executable mongosh JavaScript inserting minimal realistic reference documents."
        ),
        "migrations": s.array(
            s.obj(
                {
                    "filename": s.string("e.g. '001_initial_schema.js'."),
                    "description": s.string("What this migration does."),
                    "script": s.string("Executable mongosh JavaScript for this migration."),
                }
            ),
            description="Forward-only, numbered mongosh migrations. The first establishes the schema.",
        ),
        "notes": s.string("Document modelling, validation and indexing trade-offs."),
    }
)


class DatabaseEngineerAgent(CodeAgent):
    role = AgentRole.DATABASE_ENGINEER
    display_name = "Database Engineer"
    description = "Designs the selected database's schema, indexes and migrations."
    depends_on = (AgentRole.BUSINESS_ANALYST, AgentRole.SOLUTION_ARCHITECT)
    # A schema without entities or an architecture would be guesswork.
    requires = (AgentRole.BUSINESS_ANALYST, AgentRole.SOLUTION_ARCHITECT)
    output_root = "database"

    def should_execute(self, ctx: AgentContext) -> SkipDecision:
        if not ctx.memory.needs_database:
            return SkipDecision.skip(
                "This project holds no persistent state, so no database is required."
            )
        if not ctx.memory.tech_stack.database:
            return SkipDecision.skip("No database engine was selected for this project.")
        return SkipDecision.run()

    def system_prompt(self, ctx: AgentContext) -> str:
        if ctx.memory.tech_stack.database == "mongodb":
            return """\
ROLE: Database Engineer

You design the MongoDB document model every other engineer codes against. The
scripts you emit are run with `mongosh`, so they must be correct on the first run.

## Requirements for the document model

- Model every entity the Business Analyst identified as a collection, embedded
  document, or intentionally documented reference.
- Make embedding-versus-reference choices from access patterns and document them.
- Every top-level document has `createdAt` and `updatedAt`; never store plaintext
  passwords (use `passwordHash`).
- Use MongoDB `$jsonSchema` validators with the correct BSON types and required
  fields. Validation complements, never replaces, API validation.
- Add a named index for every common filter, sort, uniqueness rule and reference.
- Use `ObjectId` for `_id` and references unless an external stable identifier is
  explicitly required.

## Scripts must actually run

`schema_script`, `seed_script`, and every migration are executed as-is with
`mongosh`. They must select the target database, create collections and indexes
in a safe order, and use valid JavaScript and MongoDB commands. Do not emit SQL.
"""
        return """\
ROLE: Database Engineer

You design the relational schema every other engineer codes against. The DDL \
you emit is executed verbatim during setup, so it must be correct on the first \
run.

## Requirements for the schema

- Third normal form unless a documented, justified reason to denormalise exists.
- Every table has a primary key.
- Every foreign key declares an explicit `ON DELETE` action. Choose \
deliberately: `CASCADE` where children are meaningless without the parent, \
`RESTRICT` where deletion should be blocked, `SET NULL` where the link is \
optional.
- Every foreign key column is indexed. Every column used to filter or sort a \
listed query is indexed.
- Add `created_at` and `updated_at` to every entity table.
- Use `CHECK` constraints for enumerated values and for invariants such as \
non-negative quantities.
- Never store a password in plaintext. Password columns are named \
`password_hash` and hold a hash.
- Many-to-many relationships get an explicit join table with a composite \
primary key.

## The SQL must actually run

`schema_sql` is executed as-is. Order `CREATE TABLE` statements so that no \
foreign key references a table declared later. `seed_sql` is executed after it, \
so its inserts must respect the same ordering. Use only syntax valid in the \
target dialect stated below — a statement that is valid in another engine but \
not this one is a defect.

## Coverage

Model every entity the Business Analyst identified. If an entity in that list \
has no table, the backend will have nowhere to store it."""

    async def execute(self, ctx: AgentContext) -> AgentResult:
        memory = ctx.memory
        adapter = ctx.registry.database(memory.tech_stack.database or "sqlite")

        await ctx.progress(self.role, 15, f"Designing the {adapter.display_name} schema")

        entities = ", ".join(memory.analysis.entities) or "as implied by the requirements"
        type_map = "\n".join(f"  {k} -> {v}" for k, v in adapter.type_mapping().items())
        is_mongodb = adapter.key == "mongodb"
        artifact_kind = "document model" if is_mongodb else "schema"
        output_contract = (
            "Model every entity as a collection or embedded document. Include collection validators, "
            "indexes, executable mongosh schema and seed scripts, and JavaScript migrations. Do not emit SQL."
            if is_mongodb
            else "Model every entity listed. Add any join tables, lookup tables or audit columns the "
            "requirements imply. The SQL must execute without modification."
        )

        completion = await ctx.llm.complete_structured(
            self.build_prompt(
                ctx,
                instruction=(
                    f"Design the complete {adapter.display_name} {artifact_kind} for this "
                    "project.\n\n"
                    f"TARGET DIALECT: {adapter.display_name} {adapter.version}\n"
                    f"{adapter.sql_dialect_notes()}\n\n"
                    f"CANONICAL TYPE MAPPING:\n{type_map}\n\n"
                    f"ENTITIES TO MODEL: {entities}\n\n"
                    + output_contract
                    + (
                        "\n\nThis project uses authentication, so include a users "
                        + ("collection with a `passwordHash` field" if is_mongodb else "table with a `password_hash` column")
                        + " and whatever role or permission structure the requirements imply."
                        if memory.needs_auth
                        else ""
                    )
                ),
                schema=MONGO_SCHEMA_DESIGN_SCHEMA if is_mongodb else SCHEMA_DESIGN_SCHEMA,
                include_files=False,
                max_tokens=28000,
            )
        )

        await ctx.progress(self.role, 70, "Writing schema, seed data and migrations")

        data = completion.data
        design = DatabaseDesign(
            required=True,
            engine=adapter.key,
            tables=data.get("tables", []),
            relationships=data.get("relationships", []),
            indexes=data.get("indexes", []),
            collections=data.get("collections", []),
            schema_sql=data.get("schema_sql", ""),
            seed_sql=data.get("seed_sql", ""),
            schema_script=data.get("schema_script", ""),
            seed_script=data.get("seed_script", ""),
            migrations=data.get("migrations", []),
            notes=data.get("notes", ""),
        )
        memory.database = design

        written = 0
        schema_content = design.schema_script if is_mongodb else design.schema_sql
        seed_content = design.seed_script if is_mongodb else design.seed_sql
        if schema_content:
            memory.workspace.write(
                f"database/{adapter.schema_filename}",
                self._with_header(schema_content, "Schema", memory.project_name, adapter),
                description="Complete database schema, validators and indexes.",
                produced_by=self.role,
            )
            written += 1
        if seed_content:
            memory.workspace.write(
                f"database/{adapter.seed_filename}",
                self._with_header(seed_content, "Seed data", memory.project_name, adapter),
                description="Minimal reference data for local development.",
                produced_by=self.role,
            )
            written += 1

        for migration in design.migrations:
            filename = str(migration.get("filename", "")).strip()
            script = str(migration.get("script" if is_mongodb else "sql", "")).strip()
            if not filename or not script:
                continue
            if not filename.endswith(adapter.migration_extension):
                filename = f"{filename}{adapter.migration_extension}"
            memory.workspace.write(
                f"database/migrations/{filename}",
                self._with_header(
                    script,
                    str(migration.get("description", "Migration")),
                    memory.project_name,
                    adapter,
                ),
                description=str(migration.get("description", "Database migration.")),
                produced_by=self.role,
            )
            written += 1

        # The adapter contributes the database README deterministically.
        for scaffold_file in adapter.scaffold(ctx.scaffold_context()):
            memory.workspace.write(
                scaffold_file.path,
                scaffold_file.content,
                description=scaffold_file.description,
                produced_by=self.role,
            )
            written += 1

        await ctx.log(
            self.role,
            f"Designed {len(design.collections) if is_mongodb else len(design.tables)} "
            f"{'collections' if is_mongodb else 'tables'} with {len(design.indexes)} indexes",
            database_objects=[
                item.get("name") for item in (design.collections if is_mongodb else design.tables)
            ][:20],
        )

        confidence = self._confidence(design, memory.analysis.entities)
        memory.record_confidence("database", confidence)

        summary = (
            f"{len(design.collections) if is_mongodb else len(design.tables)} "
            f"{'collections' if is_mongodb else 'tables'}, "
            f"{len(design.relationships)} relationships, "
            f"{len(design.indexes)} indexes and {len(design.migrations)} migrations "
            f"for {adapter.display_name}."
        )
        memory.record_summary(self.role, summary)
        await ctx.progress(self.role, 100, "Database design complete")

        return AgentResult(
            role=self.role,
            summary=summary,
            output={**design.as_dict(), "artifact_kind": ArtifactKind.DATABASE.value},
            usage=completion.usage,
            files_produced=written,
            confidence=confidence,
        )

    @staticmethod
    def _with_header(script: str, title: str, project: str, adapter: object) -> str:
        name = getattr(adapter, "display_name", "Database")
        prefix = getattr(adapter, "comment_prefix", "--")
        return (
            f"{prefix} {title} — {project}\n"
            f"{prefix} Target: {name}\n"
            f"{prefix} Generated by Aegis AI. Review before running against production data.\n\n"
            f"{script.strip()}\n"
        )

    @staticmethod
    def _confidence(design: DatabaseDesign, entities: list[str]) -> float:
        is_mongodb = design.engine == "mongodb"
        objects = design.collections if is_mongodb else design.tables
        object_names = {str(item.get("name", "")).lower() for item in objects}
        covered = sum(
            1
            for entity in entities
            if any(entity.lower().rstrip("s") in name for name in object_names)
        )
        coverage = covered / len(entities) if entities else 1.0
        checks = [
            bool(design.schema_script if is_mongodb else design.schema_sql),
            bool(design.seed_script if is_mongodb else design.seed_sql),
            len(objects) >= 1,
            len(design.indexes) >= len(objects),
            bool(design.migrations),
            coverage >= 0.8,
            bool(design.relationships) or len(objects) <= 1,
            ("$jsonschema" in design.schema_script.lower()) if is_mongodb else "primary key" in design.schema_sql.lower(),
        ]
        return round(sum(checks) / len(checks), 3)
