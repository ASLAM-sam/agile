"""Backend Engineer agent.

Emits the adapter's deterministic scaffold, then generates application code in
planned batches against the architect's API contract and the database
engineer's schema.
"""

from __future__ import annotations

from app.agents.base import CodeAgent
from app.agents.context import AgentContext
from app.agents.results import AgentResult, SkipDecision
from app.core.enums import AgentRole, ArtifactKind


class BackendEngineerAgent(CodeAgent):
    role = AgentRole.BACKEND_ENGINEER
    display_name = "Backend Engineer"
    description = (
        "Implements APIs, models, services, business logic, validation and "
        "authentication against the agreed contract."
    )
    depends_on = (
        AgentRole.BUSINESS_ANALYST,
        AgentRole.SOLUTION_ARCHITECT,
        AgentRole.DATABASE_ENGINEER,
    )
    # The API contract is binding, so the architecture is essential. The schema
    # is ordering-only: a project with no database skips that agent entirely,
    # and one whose schema failed is still worth building routes for.
    requires = (AgentRole.BUSINESS_ANALYST, AgentRole.SOLUTION_ARCHITECT)
    output_root = "backend"

    def should_execute(self, ctx: AgentContext) -> SkipDecision:
        if not ctx.memory.needs_backend:
            return SkipDecision.skip(
                "This project is client-only, so no server-side application is required."
            )
        if not ctx.memory.tech_stack.backend:
            return SkipDecision.skip("No backend framework was selected for this project.")
        return SkipDecision.run()

    def system_prompt(self, ctx: AgentContext) -> str:
        return """\
ROLE: Backend Engineer

You implement the server-side application: routes, services, data access, \
validation, error handling and — where the project requires it — \
authentication.

## The contract you implement

The Solution Architect has published an API contract and the Database Engineer \
has published a schema. Both are binding:

- Implement **every** endpoint in the contract, at the exact path and method \
given. The frontend is being written against that list; a missing endpoint is a \
broken application.
- Your data-access code must match the schema exactly — same table names, same \
column names, same types. A query against a column that does not exist fails at \
runtime, not at generation time.

## What "production-ready" means here

- Validate every input at the boundary. Never trust a request body.
- Every database query is parameterised. String-concatenated SQL is forbidden.
- Errors return a consistent JSON shape with an accurate status code. An \
unhandled exception reaching the client as a 500 with a stack trace is a defect.
- Log at boundaries — request received, operation failed — never inside tight \
loops, and never log secrets, tokens or password hashes.
- Read configuration from the environment through one configuration module. No \
hardcoded connection strings, ports, or secrets anywhere in the code.
- Where the project has authentication: hash passwords with a real algorithm \
(bcrypt), never return a password hash in a response, and enforce authorisation \
on every endpoint the contract marks as requiring it.

## Completeness

Every file you emit must be complete and runnable. If a service method is \
listed in your plan, its body must contain a working implementation — not a \
signature with a comment describing what it would do."""

    async def execute(self, ctx: AgentContext) -> AgentResult:
        memory = ctx.memory
        adapter = ctx.registry.backend(memory.tech_stack.backend or "fastapi")
        scaffold_ctx = ctx.scaffold_context()

        await ctx.progress(self.role, 5, f"Preparing the {adapter.display_name} scaffold")

        scaffold_files = adapter.scaffold(scaffold_ctx)
        for scaffold_file in scaffold_files:
            memory.workspace.write(
                scaffold_file.path,
                scaffold_file.content,
                description=scaffold_file.description,
                produced_by=self.role,
            )
        await ctx.log(
            self.role,
            f"Emitted {len(scaffold_files)} scaffold files "
            f"({adapter.display_name} {adapter.version})",
        )

        conventions = adapter.conventions(scaffold_ctx)
        endpoints = self._endpoint_listing(ctx)
        schema_context = self._schema_context(ctx)

        await ctx.progress(self.role, 15, "Planning the backend file structure")

        planned, plan_usage = await self.plan_files(
            ctx,
            instruction=(
                "Plan every application source file for the backend.\n\n"
                f"{conventions}\n\n"
                f"{endpoints}\n\n"
                f"{schema_context}\n\n"
                "Planning rules:\n"
                "- Every path starts with `backend/`.\n"
                "- Do NOT plan any file the scaffold already provides (listed in "
                "the conventions under 'Do not generate').\n"
                "- One responsibility per file.\n"
                "- Include the application entrypoint, configuration, every "
                "route module, every service, every data-access module, every "
                "schema/DTO module and the error-handling module.\n"
                "- Set `priority` so foundational files (config, base classes, "
                "database session) come before the modules that import them.\n"
                "- Aim for 12–30 files. Prefer several focused files over a few "
                "large ones."
            ),
        )

        await ctx.log(self.role, f"Planned {len(planned)} backend source files")

        written, gen_usage, warnings = await self.generate_files(
            ctx,
            planned,
            progress_from=20,
            progress_to=95,
            extra_instruction=(
                f"{conventions}\n\n{endpoints}\n\n{schema_context}\n\n"
                "Every file must be complete and immediately runnable."
            ),
        )

        total_usage = plan_usage + gen_usage
        total_files = written + len(scaffold_files)

        confidence = self._confidence(ctx, written, warnings)
        memory.record_confidence("backend", confidence)

        summary = (
            f"{total_files} backend files for {adapter.display_name} "
            f"({written} generated, {len(scaffold_files)} scaffolded)"
            + (f", {len(warnings)} warnings." if warnings else ".")
        )
        memory.record_summary(self.role, summary)
        await ctx.progress(self.role, 100, "Backend implementation complete")

        return AgentResult(
            role=self.role,
            summary=summary,
            output={
                "framework": adapter.key,
                "generated_files": written,
                "scaffold_files": len(scaffold_files),
                "planned_files": len(planned),
                "artifact_kind": ArtifactKind.BACKEND_CODE.value,
            },
            usage=total_usage,
            files_produced=total_files,
            confidence=confidence,
            warnings=warnings,
        )

    @staticmethod
    def _endpoint_listing(ctx: AgentContext) -> str:
        endpoints = ctx.memory.architecture.api_endpoints
        if not endpoints:
            return "API CONTRACT: none defined; expose only what the requirements imply."

        rows = []
        for endpoint in endpoints:
            auth = " [auth required]" if endpoint.get("auth_required") else ""
            rows.append(
                f"- {endpoint.get('method', 'GET')} {endpoint.get('path', '')}{auth}\n"
                f"    purpose: {endpoint.get('summary', '')}\n"
                f"    request: {endpoint.get('request_body') or 'none'}\n"
                f"    response: {endpoint.get('response_body') or 'none'}\n"
                f"    statuses: {', '.join(str(c) for c in endpoint.get('status_codes', []))}"
            )
        return (
            "API CONTRACT — implement every one of these exactly:\n" + "\n".join(rows)
        )

    @staticmethod
    def _schema_context(ctx: AgentContext) -> str:
        design = ctx.memory.database
        if not design.required or not design.tables:
            return "DATABASE: none. Do not generate data-access code."

        rows = []
        for table in design.tables:
            columns = ", ".join(
                f"{c.get('name')} {c.get('type')}"
                f"{'' if c.get('nullable') else ' NOT NULL'}"
                for c in table.get("columns", [])
            )
            rows.append(f"- {table.get('name')}({columns})")

        relationships = [
            f"- {r.get('from_table')}.{r.get('from_column')} -> "
            f"{r.get('to_table')}.{r.get('to_column')} "
            f"({r.get('cardinality')}, ON DELETE {r.get('on_delete')})"
            for r in design.relationships
        ]

        block = (
            "DATABASE SCHEMA — your data-access code must match this exactly:\n"
            + "\n".join(rows)
        )
        if relationships:
            block += "\n\nRELATIONSHIPS:\n" + "\n".join(relationships)
        return block

    @staticmethod
    def _confidence(ctx: AgentContext, written: int, warnings: list[str]) -> float:
        paths = " ".join(ctx.memory.workspace.paths).lower()
        endpoint_count = len(ctx.memory.architecture.api_endpoints)
        checks = [
            written >= 8,
            len(warnings) == 0,
            "config" in paths,
            "route" in paths or "controller" in paths or "api" in paths,
            "service" in paths,
            "error" in paths or "exception" in paths,
            not ctx.memory.needs_database
            or ("repositor" in paths or "model" in paths or "entit" in paths),
            not ctx.memory.needs_auth or ("auth" in paths or "security" in paths),
            endpoint_count == 0 or written >= max(4, endpoint_count // 3),
        ]
        return round(sum(checks) / len(checks), 3)
