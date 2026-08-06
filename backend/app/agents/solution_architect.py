"""Solution Architect agent.

Designs the module breakdown, layering and API contract. Runs after the Business
Analyst and before any code agent, so backend and frontend engineers implement
against one agreed contract rather than inventing their own.
"""

from __future__ import annotations

from app.agents.base import Agent
from app.agents.context import AgentContext
from app.agents.results import AgentResult
from app.core.enums import AgentRole
from app.llm import schema as s
from app.workflow.memory import ArchitectureDesign

ARCHITECTURE_SCHEMA = s.obj(
    {
        "style": s.string(
            "Architecture style with a short justification, e.g. "
            "'Layered monolith — single deployable, clear separation, right size "
            "for this scope'."
        ),
        "overview": s.string("Two paragraphs describing how the system fits together."),
        "modules": s.array(
            s.obj(
                {
                    "name": s.string("Module name, e.g. 'Appointments'."),
                    "responsibility": s.string("Single-sentence responsibility."),
                    "entities": s.string_array("Domain entities this module owns."),
                    "depends_on": s.string_array("Other modules it depends on."),
                }
            ),
            description="4 to 10 modules partitioning the domain with no overlap.",
        ),
        "layers": s.array(
            s.obj(
                {
                    "name": s.string("Layer name, e.g. 'Service layer'."),
                    "responsibility": s.string("What belongs in this layer."),
                    "rules": s.string_array("Rules governing what may import what."),
                }
            ),
            description="The layers and the dependency rules between them.",
        ),
        "folder_structure": s.string(
            "ASCII tree of the complete project folder structure, covering every "
            "directory the team will create. Use the exact root directory names "
            "given in the conventions."
        ),
        "api_endpoints": s.array(
            s.obj(
                {
                    "method": s.string(
                        "HTTP method.",
                        enum=["GET", "POST", "PUT", "PATCH", "DELETE"],
                    ),
                    "path": s.string("Full path including prefix, e.g. '/api/v1/patients'."),
                    "summary": s.string("What this endpoint does."),
                    "module": s.string("Owning module."),
                    "auth_required": s.boolean("Whether a valid session is required."),
                    "request_body": s.string(
                        "Field names and types, or empty for methods without a body."
                    ),
                    "response_body": s.string("Success response shape."),
                    "status_codes": s.string_array("Status codes this endpoint returns."),
                }
            ),
            description=(
                "Complete REST API surface. Empty array if the project has no API. "
                "Every endpoint the frontend needs must appear here."
            ),
        ),
        "integrations": s.string_array("External services required. Usually empty."),
        "cross_cutting": s.string_array(
            "Cross-cutting concerns and how each is handled: error handling, "
            "logging, validation, configuration, authentication."
        ),
        "decisions": s.array(
            s.obj(
                {
                    "decision": s.string("The architectural decision made."),
                    "rationale": s.string("Why, including the alternative rejected."),
                }
            ),
            description="3 to 8 significant decisions worth recording.",
        ),
    }
)


class SolutionArchitectAgent(Agent):
    role = AgentRole.SOLUTION_ARCHITECT
    display_name = "Solution Architect"
    description = (
        "Designs the architecture, module breakdown, folder structure and API "
        "contract that every other engineer implements against."
    )
    depends_on = (AgentRole.BUSINESS_ANALYST,)
    # Without requirements there is nothing to design.
    requires = (AgentRole.BUSINESS_ANALYST,)

    def system_prompt(self, ctx: AgentContext) -> str:
        return """\
ROLE: Solution Architect

You design the structure every other engineer builds within. Your output is a \
contract: the Backend Engineer implements your endpoints, the Frontend Engineer \
calls them, the Database Engineer models your entities. Ambiguity here becomes \
integration failure later.

## Sizing

Match the architecture to the actual scope. A layered monolith is the correct \
answer for almost every starter project. Do not propose microservices, event \
sourcing, CQRS or a message bus unless the requirements genuinely demand them — \
unwarranted complexity is an architectural defect, not sophistication.

## The API contract

If the project has an API, `api_endpoints` must be complete. Every operation \
implied by the functional requirements needs an endpoint, and every endpoint \
the frontend will call must be listed. A missing endpoint means the frontend \
calls something that was never built.

For each endpoint:
- Paths are plural, lowercase, hyphenated: `/api/v1/patient-records`.
- Use path parameters for identity (`/api/v1/patients/{id}`), query parameters \
for filtering and pagination.
- Choose the correct method: GET reads, POST creates, PUT replaces, PATCH \
partially updates, DELETE removes.
- List realistic status codes, including the failure cases (400, 401, 404, 409).
- Set `auth_required` accurately per endpoint. Public read endpoints on an \
otherwise authenticated system are common and correct.

## Folder structure

`folder_structure` must be a complete ASCII tree using the exact root directory \
names given in the conventions below. This is the map the whole team navigates \
by; every directory another engineer will write into must appear.

## Modules

Modules partition the domain with no overlap. Each owns its entities. \
Dependencies between modules must be acyclic — if two modules depend on each \
other, you have drawn the boundary in the wrong place."""

    async def execute(self, ctx: AgentContext) -> AgentResult:
        await ctx.progress(self.role, 15, "Analysing requirements and selecting a style")

        conventions = self._conventions(ctx)

        completion = await ctx.llm.complete_structured(
            self.build_prompt(
                ctx,
                instruction=(
                    "Design the complete architecture for this project.\n\n"
                    "The folder structure must use exactly these root directories "
                    "and follow these technology conventions:\n\n"
                    f"{conventions}\n\n"
                    "Ensure every functional requirement maps onto at least one "
                    "module, and — if this project has an API — onto at least one "
                    "endpoint."
                ),
                schema=ARCHITECTURE_SCHEMA,
                include_files=False,
                max_tokens=24000,
            )
        )

        await ctx.progress(self.role, 80, "Recording the API contract and decisions")

        data = completion.data
        endpoints = data.get("api_endpoints", []) if ctx.memory.analysis.needs_api else []

        architecture = ArchitectureDesign(
            style=data.get("style", ""),
            overview=data.get("overview", ""),
            modules=data.get("modules", []),
            layers=data.get("layers", []),
            folder_structure=data.get("folder_structure", ""),
            api_endpoints=endpoints,
            integrations=data.get("integrations", []),
            cross_cutting=data.get("cross_cutting", []),
            decisions=data.get("decisions", []),
        )
        ctx.memory.architecture = architecture

        if endpoints:
            ctx.memory.api_spec = {
                "version": "v1",
                "base_path": "/api/v1",
                "endpoint_count": len(endpoints),
                "endpoints": endpoints,
            }

        await ctx.log(
            self.role,
            f"Designed {len(architecture.modules)} modules and "
            f"{len(endpoints)} API endpoints",
            style=architecture.style[:80],
        )

        confidence = self._confidence(ctx, architecture)
        ctx.memory.record_confidence("architecture", confidence)

        summary = (
            f"{architecture.style.split('—')[0].strip() or 'Layered'} architecture with "
            f"{len(architecture.modules)} modules"
            + (f" and {len(endpoints)} API endpoints." if endpoints else ".")
        )
        ctx.memory.record_summary(self.role, summary)
        await ctx.progress(self.role, 100, "Architecture complete")

        return AgentResult(
            role=self.role,
            summary=summary,
            output=architecture.as_dict(),
            usage=completion.usage,
            confidence=confidence,
        )

    def _conventions(self, ctx: AgentContext) -> str:
        """Root directory layout implied by the selected stack."""
        memory = ctx.memory
        parts: list[str] = []
        roots: list[str] = []

        if memory.needs_frontend and memory.tech_stack.frontend:
            adapter = ctx.registry.frontend(memory.tech_stack.frontend)
            roots.append(f"`{adapter.root_dir}/` — {adapter.display_name} application")
            conventions = adapter.conventions(ctx.scaffold_context())
            parts.append(f"FRONTEND ({adapter.display_name}):\n{conventions}")

        if memory.needs_backend and memory.tech_stack.backend:
            adapter = ctx.registry.backend(memory.tech_stack.backend)
            roots.append(f"`{adapter.root_dir}/` — {adapter.display_name} API")
            conventions = adapter.conventions(ctx.scaffold_context())
            parts.append(f"BACKEND ({adapter.display_name}):\n{conventions}")

        if memory.needs_database and memory.tech_stack.database:
            adapter = ctx.registry.database(memory.tech_stack.database)
            roots.append("`database/` — schema, seed data and migrations")
            parts.append(f"DATABASE ({adapter.display_name}):\n{adapter.sql_dialect_notes()}")

        roots.append("`docs/` — project documentation")

        header = "ROOT DIRECTORIES:\n" + "\n".join(f"- {r}" for r in roots)
        return header + "\n\n" + "\n\n".join(parts)

    @staticmethod
    def _confidence(ctx: AgentContext, architecture: ArchitectureDesign) -> float:
        needs_api = ctx.memory.analysis.needs_api
        checks = [
            len(architecture.modules) >= 3,
            bool(architecture.folder_structure),
            bool(architecture.style),
            bool(architecture.overview),
            len(architecture.layers) >= 2,
            len(architecture.decisions) >= 3,
            bool(architecture.cross_cutting),
            len(architecture.api_endpoints) >= 4 if needs_api else True,
            # Every module should be reachable from at least one endpoint.
            (
                not needs_api
                or not architecture.modules
                or any(
                    e.get("module") == m.get("name")
                    for m in architecture.modules
                    for e in architecture.api_endpoints
                )
            ),
        ]
        return round(sum(checks) / len(checks), 3)
