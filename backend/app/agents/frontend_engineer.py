"""Frontend Engineer agent.

Emits the adapter's deterministic scaffold, then generates pages, components,
routing and API integration against the architect's endpoint contract.
"""

from __future__ import annotations

from app.agents.base import CodeAgent
from app.agents.context import AgentContext
from app.agents.results import AgentResult, SkipDecision
from app.core.enums import AgentRole, ArtifactKind


class FrontendEngineerAgent(CodeAgent):
    role = AgentRole.FRONTEND_ENGINEER
    display_name = "Frontend Engineer"
    description = (
        "Builds the user interface: pages, routing, reusable components, "
        "responsive layout and API integration."
    )
    depends_on = (
        AgentRole.BUSINESS_ANALYST,
        AgentRole.SOLUTION_ARCHITECT,
        AgentRole.BACKEND_ENGINEER,
    )
    # The backend is ordering-only: the UI is built against the architect's API
    # contract, so it remains buildable even if backend generation failed.
    requires = (AgentRole.BUSINESS_ANALYST, AgentRole.SOLUTION_ARCHITECT)
    output_root = "frontend"

    def should_execute(self, ctx: AgentContext) -> SkipDecision:
        if not ctx.memory.needs_frontend:
            return SkipDecision.skip(
                "This project exposes no user interface, so no frontend is required."
            )
        if not ctx.memory.tech_stack.frontend:
            return SkipDecision.skip("No frontend framework was selected for this project.")
        return SkipDecision.run()

    def system_prompt(self, ctx: AgentContext) -> str:
        return """\
ROLE: Frontend Engineer

You build the interface people actually use. Structure and correctness matter, \
and so does the experience: a technically correct UI that is ugly, confusing or \
unusable has failed.

## Design quality

- Establish a consistent visual language — spacing scale, type scale, a small \
colour palette — and hold to it across every screen.
- Use clear hierarchy. The most important thing on a screen should be the most \
prominent thing on that screen.
- Give content room. Cramped interfaces read as unfinished.
- Every screen must work from a 360px phone up to a wide desktop. Design \
mobile-first, then add breakpoints.

## States are not optional

Every view that loads data renders four states explicitly:
1. **Loading** — a skeleton or spinner, never a blank screen.
2. **Error** — a human-readable message and a way to retry.
3. **Empty** — an explanation and, where sensible, a primary action.
4. **Success** — the data.

A component that handles only the success path is incomplete and will be \
rejected in review.

## Accessibility

- Semantic HTML: `<button>` for actions, `<a>` for navigation, real heading \
levels in order, `<label>` bound to every input.
- Every interactive element is reachable and operable by keyboard, with a \
visible focus ring.
- Images carry meaningful `alt` text; decorative images carry `alt=""`.
- Do not convey meaning through colour alone.
- Form errors are associated with their field and announced to assistive \
technology.

## Integration

Call only endpoints that appear in the API contract, at the exact paths given. \
Do not invent an endpoint because it would be convenient — if the contract \
lacks something, work with what exists.

## Reuse

Shared markup becomes a component in the components directory. If you would \
otherwise paste the same block of markup into a second file, extract it first."""

    async def execute(self, ctx: AgentContext) -> AgentResult:
        memory = ctx.memory
        adapter = ctx.registry.frontend(memory.tech_stack.frontend or "react")
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
        api_context = self._api_context(ctx)
        screens = self._screen_guidance(ctx)

        await ctx.progress(self.role, 15, "Planning pages, components and routes")

        planned, plan_usage = await self.plan_files(
            ctx,
            instruction=(
                "Plan every source file for the frontend application.\n\n"
                f"{conventions}\n\n"
                f"{api_context}\n\n"
                f"{screens}\n\n"
                "Planning rules:\n"
                "- Every path starts with `frontend/`.\n"
                "- Do NOT plan any file the scaffold already provides (listed in "
                "the conventions under 'Do not generate'), but DO plan the global "
                "stylesheet the conventions require you to generate.\n"
                "- Include: the application entrypoint, root component, routing, "
                "one page per primary screen, shared UI primitives (button, card, "
                "input, spinner, empty state), layout components, and typed "
                "domain models.\n"
                "- Set `priority` so shared primitives and types come before the "
                "pages that import them.\n"
                "- Aim for 15–35 files."
            ),
        )

        await ctx.log(self.role, f"Planned {len(planned)} frontend source files")

        written, gen_usage, warnings = await self.generate_files(
            ctx,
            planned,
            progress_from=20,
            progress_to=95,
            extra_instruction=(
                f"{conventions}\n\n{api_context}\n\n"
                "Every component must render loading, error and empty states where "
                "it loads data. Every interactive element must be keyboard "
                "accessible with a visible focus ring."
            ),
        )

        total_usage = plan_usage + gen_usage
        total_files = written + len(scaffold_files)

        confidence = self._confidence(ctx, written, warnings)
        memory.record_confidence("frontend", confidence)

        summary = (
            f"{total_files} frontend files for {adapter.display_name} "
            f"({written} generated, {len(scaffold_files)} scaffolded)"
            + (f", {len(warnings)} warnings." if warnings else ".")
        )
        memory.record_summary(self.role, summary)
        await ctx.progress(self.role, 100, "Frontend implementation complete")

        return AgentResult(
            role=self.role,
            summary=summary,
            output={
                "framework": adapter.key,
                "generated_files": written,
                "scaffold_files": len(scaffold_files),
                "planned_files": len(planned),
                "artifact_kind": ArtifactKind.FRONTEND_CODE.value,
            },
            usage=total_usage,
            files_produced=total_files,
            confidence=confidence,
            warnings=warnings,
        )

    @staticmethod
    def _api_context(ctx: AgentContext) -> str:
        endpoints = ctx.memory.architecture.api_endpoints
        if not endpoints:
            return (
                "API: this project has no backend. Manage all state client-side; "
                "do not generate network calls or an API client."
            )
        rows = [
            f"- {e.get('method', 'GET')} {e.get('path', '')}"
            f"{' [auth required]' if e.get('auth_required') else ''}"
            f" — {e.get('summary', '')}"
            f" | returns: {e.get('response_body') or 'none'}"
            for e in endpoints
        ]
        return (
            "API CONTRACT — call only these endpoints, at exactly these paths:\n"
            + "\n".join(rows)
        )

    @staticmethod
    def _screen_guidance(ctx: AgentContext) -> str:
        memory = ctx.memory
        modules = [str(m.get("name", "")) for m in memory.architecture.modules]
        stories = [str(s.get("story", "")) for s in memory.analysis.user_stories[:12]]

        parts = []
        if modules:
            parts.append("MODULES NEEDING A UI: " + ", ".join(n for n in modules if n))
        if stories:
            parts.append(
                "USER JOURNEYS TO SUPPORT:\n" + "\n".join(f"- {s}" for s in stories if s)
            )
        if memory.needs_auth:
            parts.append(
                "AUTHENTICATION: include login and registration screens, an "
                "authenticated shell with sign-out, and route protection that "
                "redirects unauthenticated users."
            )
        return "\n\n".join(parts)

    @staticmethod
    def _confidence(ctx: AgentContext, written: int, warnings: list[str]) -> float:
        frontend_paths = " ".join(
            f.path.lower() for f in ctx.memory.workspace.under("frontend")
        )
        has_styles = any(
            f.path.endswith(".css") for f in ctx.memory.workspace.under("frontend")
        )
        checks = [
            written >= 10,
            len(warnings) == 0,
            "page" in frontend_paths or "app/" in frontend_paths,
            "component" in frontend_paths,
            has_styles,
            "type" in frontend_paths or "model" in frontend_paths,
            not ctx.memory.architecture.api_endpoints
            or ("api" in frontend_paths or "service" in frontend_paths),
            not ctx.memory.needs_auth or "auth" in frontend_paths or "login" in frontend_paths,
        ]
        return round(sum(checks) / len(checks), 3)
