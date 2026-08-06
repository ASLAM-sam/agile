"""Documentation Engineer agent.

Produces the README, installation guide, API documentation and developer guide.
Runs after the code agents so instructions describe what was actually built.
"""

from __future__ import annotations

from app.agents.base import CodeAgent
from app.agents.context import AgentContext
from app.agents.results import AgentResult
from app.core.enums import AgentRole, ArtifactKind
from app.llm import schema as s

DOCS_SCHEMA = s.obj(
    {
        "readme": s.string(
            "Complete root README.md. Must open with the project name and a "
            "one-line description, then cover: what it does, the technology "
            "stack, prerequisites with exact versions, quick start, project "
            "structure, available scripts, and a link to the other docs."
        ),
        "installation_guide": s.string(
            "Complete docs/INSTALLATION.md: step-by-step setup from a clean "
            "machine, covering both the Docker path and the manual path, plus a "
            "troubleshooting section for the failures a newcomer actually hits."
        ),
        "api_documentation": s.string(
            "Complete docs/API.md documenting every endpoint: method, path, auth "
            "requirement, request body, response body, status codes and a working "
            "curl example. Empty string if the project has no API."
        ),
        "developer_guide": s.string(
            "Complete docs/DEVELOPMENT.md: architecture overview, folder layout, "
            "the conventions the codebase follows, how to add a new feature "
            "end-to-end, and how to run the tests."
        ),
        "environment_reference": s.string(
            "Complete docs/CONFIGURATION.md: a table of every environment "
            "variable with its purpose, whether it is required, and its default."
        ),
    }
)


class DocumentationEngineerAgent(CodeAgent):
    role = AgentRole.DOCUMENTATION_ENGINEER
    display_name = "Documentation Engineer"
    description = (
        "Writes the README, installation guide, API reference and developer "
        "documentation for the generated project."
    )
    # Depends on QA and Improvement as well as the code agents so the docs
    # describe the *final* state of the project: the test commands exist, and
    # any file the improvement pass rewrote is already in its final form.
    depends_on = (
        AgentRole.SOLUTION_ARCHITECT,
        AgentRole.BACKEND_ENGINEER,
        AgentRole.FRONTEND_ENGINEER,
        AgentRole.QA_ENGINEER,
        AgentRole.IMPROVEMENT_ENGINEER,
    )
    output_root = "docs"

    def system_prompt(self, ctx: AgentContext) -> str:
        return """\
ROLE: Documentation Engineer

You write the documentation someone reads at 9am on their first day. It has to \
get them from a clean machine to a running application without them asking \
anyone a question.

## Accuracy above all

Document what was actually built. Every command you write must work against the \
real file structure; every path must exist; every environment variable must be \
one the code actually reads. A confident instruction that fails is worse than \
no instruction, because the reader trusts it and loses time.

Check your claims against the project state you were given. If a script is not \
in the manifest, do not tell the reader to run it.

## Style

- Write in the imperative for instructions: "Run `npm install`", not "You "
"should run `npm install`".
- Every command sits in a fenced block with its language tag, and each block \
runs from a stated working directory.
- State exact version requirements. "Node 20 or later", not "a recent Node".
- Explain *why* where a step is non-obvious. A reader who understands why a \
step exists can recover when it fails.
- Use tables for reference material (environment variables, endpoints, scripts) \
and prose for explanation.
- Never include a real credential in an example. Use an obvious placeholder and \
say where the real value comes from.

## Troubleshooting

Include the failures a newcomer genuinely hits — port already in use, database \
not reachable, dependency version mismatch, missing `.env`. For each, give the \
symptom and the fix."""

    async def execute(self, ctx: AgentContext) -> AgentResult:
        memory = ctx.memory

        await ctx.progress(self.role, 15, "Reviewing the built project")

        stack_summary = self._stack_summary(ctx)
        commands = self._command_reference(ctx)
        api_block = self._api_block(ctx)

        await ctx.progress(self.role, 35, "Writing documentation")

        completion = await ctx.llm.complete_structured(
            self.build_prompt(
                ctx,
                instruction=(
                    "Write the complete documentation set for this project.\n\n"
                    f"{stack_summary}\n\n"
                    f"{commands}\n\n"
                    f"{api_block}\n\n"
                    f"PROJECT FILE TREE:\n{memory.workspace.tree(max_entries=140)}\n\n"
                    "Every command must be correct for this exact project structure. "
                    "Do not reference a file or script that does not appear above."
                ),
                schema=DOCS_SCHEMA,
                include_files=False,
                max_tokens=32000,
            )
        )

        await ctx.progress(self.role, 85, "Writing documentation files")

        data = completion.data
        documents = [
            ("README.md", data.get("readme", ""), "Project overview and quick start."),
            (
                "docs/INSTALLATION.md",
                data.get("installation_guide", ""),
                "Step-by-step installation and troubleshooting.",
            ),
            (
                "docs/DEVELOPMENT.md",
                data.get("developer_guide", ""),
                "Architecture, conventions and contribution guide.",
            ),
            (
                "docs/CONFIGURATION.md",
                data.get("environment_reference", ""),
                "Environment variable reference.",
            ),
        ]
        if memory.architecture.api_endpoints:
            documents.append(
                ("docs/API.md", data.get("api_documentation", ""), "Complete API reference.")
            )

        written = 0
        index: list[str] = []
        for path, content, description in documents:
            if not content or not content.strip():
                continue
            memory.workspace.write(
                path, content.strip() + "\n", description=description, produced_by=self.role
            )
            index.append(path)
            written += 1

        memory.documentation_index = index

        confidence = self._confidence(written, bool(memory.architecture.api_endpoints), index)
        memory.record_confidence("documentation", confidence)

        summary = f"{written} documentation files: {', '.join(index)}."
        memory.record_summary(self.role, summary)
        await ctx.progress(self.role, 100, "Documentation complete")

        return AgentResult(
            role=self.role,
            summary=summary,
            output={
                "documents": index,
                "artifact_kind": ArtifactKind.DOCUMENTATION.value,
            },
            usage=completion.usage,
            files_produced=written,
            confidence=confidence,
        )

    @staticmethod
    def _stack_summary(ctx: AgentContext) -> str:
        memory = ctx.memory
        rows = []
        if memory.tech_stack.frontend and memory.needs_frontend:
            adapter = ctx.registry.frontend(memory.tech_stack.frontend)
            rows.append(
                f"- Frontend: {adapter.display_name} {adapter.version} "
                f"({adapter.language})"
            )
        if memory.tech_stack.backend and memory.needs_backend:
            adapter = ctx.registry.backend(memory.tech_stack.backend)
            rows.append(f"- Backend: {adapter.display_name} {adapter.version} ({adapter.language})")
        if memory.tech_stack.database and memory.needs_database:
            adapter = ctx.registry.database(memory.tech_stack.database)
            rows.append(f"- Database: {adapter.display_name} {adapter.version}")
        if memory.needs_auth:
            rows.append(f"- Authentication: {memory.tech_stack.authentication or 'JWT'}")
        return "TECHNOLOGY STACK:\n" + "\n".join(rows)

    @staticmethod
    def _command_reference(ctx: AgentContext) -> str:
        """Real commands derived from the manifests actually in the workspace."""
        memory = ctx.memory
        workspace = memory.workspace
        lines: list[str] = []

        if workspace.exists("frontend/package.json"):
            lines += [
                "Frontend (run from `frontend/`):",
                "  npm install       install dependencies",
                "  npm run dev       start the dev server",
                "  npm run build     production build",
                "  npm test          run tests",
            ]
        if workspace.exists("backend/pyproject.toml"):
            lines += [
                "Backend (run from `backend/`):",
                "  python -m venv .venv && source .venv/bin/activate  "
                "(Windows: .venv\\Scripts\\activate)",
                "  pip install -r requirements.txt",
                "  uvicorn app.main:app --reload",
                "  pytest",
            ]
        elif workspace.exists("backend/package.json"):
            lines += [
                "Backend (run from `backend/`):",
                "  npm install       install dependencies",
                "  npm run dev       start with hot reload",
                "  npm run build     compile TypeScript",
                "  npm test          run tests",
            ]
        elif workspace.exists("backend/build.gradle"):
            lines += [
                "Backend (run from `backend/`):",
                "  ./gradlew bootRun  start the application",
                "  ./gradlew build    build the jar",
                "  ./gradlew test     run tests",
            ]
        if workspace.exists("docker-compose.yml"):
            lines += [
                "Full stack (run from the project root):",
                "  docker compose up --build   start every service",
                "  docker compose down          stop and remove containers",
            ]

        return "VERIFIED COMMANDS (these match the generated manifests):\n" + "\n".join(lines)

    @staticmethod
    def _api_block(ctx: AgentContext) -> str:
        endpoints = ctx.memory.architecture.api_endpoints
        if not endpoints:
            return "API: this project has no HTTP API. Omit docs/API.md entirely."
        rows = [
            f"- {e.get('method')} {e.get('path')}"
            f"{' [auth]' if e.get('auth_required') else ''} — {e.get('summary')}"
            f" | request: {e.get('request_body') or 'none'}"
            f" | response: {e.get('response_body') or 'none'}"
            f" | statuses: {', '.join(str(c) for c in e.get('status_codes', []))}"
            for e in endpoints
        ]
        return "API ENDPOINTS TO DOCUMENT (all of them):\n" + "\n".join(rows)

    @staticmethod
    def _confidence(written: int, needs_api: bool, index: list[str]) -> float:
        expected = 5 if needs_api else 4
        checks = [
            written >= expected - 1,
            "README.md" in index,
            "docs/INSTALLATION.md" in index,
            "docs/DEVELOPMENT.md" in index,
            "docs/CONFIGURATION.md" in index,
            not needs_api or "docs/API.md" in index,
        ]
        return round(sum(checks) / len(checks), 3)
