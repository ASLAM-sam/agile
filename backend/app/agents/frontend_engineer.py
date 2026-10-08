"""Frontend Engineer agent.

Emits the adapter's deterministic scaffold, then generates pages, components,
routing and API integration against the architect's endpoint contract.
"""

from __future__ import annotations

from app.agents.base import CodeAgent
from app.agents.context import AgentContext
from app.agents.results import AgentResult, SkipDecision
from app.core.enums import AdapterKind, AgentRole, ArtifactKind
from app.llm.types import TokenUsage
from app.packaging.workspace import normalise_path
from app.workflow.memory import SharedProjectMemory


DEPENDENCY_SAFETY_RULES = """\
DEPENDENCY SAFETY RULES

Only import packages that are present in the provided package.json.

Do not invent npm packages.

Do not assume a package is installed because it is commonly used.

If a required capability needs a package that is not installed:

1. Prefer implementing the feature using existing dependencies or browser/platform APIs.
2. Only request a dependency addition when it is genuinely necessary.
3. Never silently import an unavailable package."""

TYPESCRIPT_SAFETY_RULES = """\
TYPESCRIPT SAFETY RULES

The provided tsconfig files are authoritative.

Generate code that compiles under the exact TypeScript configuration provided.

Do not weaken tsconfig settings to make code compile.

Do not introduce implicit any.

Do not create unused variables/imports when noUnusedLocals or similar checks are enabled.

Do not use APIs or syntax incompatible with the configured target/module settings."""

SCAFFOLDED_FILES_RULES = """\
SCAFFOLDED FILES

The following files are controlled by the project scaffold:

- package.json
- tsconfig.json
- tsconfig.node.json
- vite.config.ts
- index.html

Do NOT overwrite these files during normal frontend implementation unless the architecture explicitly requires a change.

Application source files should be generated separately."""

PROTECTED_SCAFFOLD_FILES = frozenset({
    "frontend/package.json",
    "frontend/tsconfig.json",
    "frontend/tsconfig.app.json",
    "frontend/tsconfig.node.json",
    "frontend/vite.config.ts",
    "frontend/vite.config.js",
    "frontend/index.html",
})


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
        target_frontend = memory.tech_stack.frontend
        if not target_frontend:
            from app.core.config import settings
            default_stack = getattr(settings, "default_frontend_stack", "html_css_js")
            target_frontend = default_stack if ctx.registry.has(AdapterKind.FRONTEND, default_stack) else "react"
        adapter = ctx.registry.frontend(target_frontend)
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

        # 1. Read actual project configuration files directly from workspace after scaffolding
        config_context = self.build_configuration_context(memory)

        conventions = adapter.conventions(scaffold_ctx)
        api_context = self._api_context(ctx)
        screens = self._screen_guidance(ctx)

        await ctx.progress(self.role, 15, "Planning pages, components and routes")

        user_req = memory.idea or memory.user_prompt or memory.analysis.project_overview
        if adapter.key == "html_css_js":
            planned = [
                {
                    "path": "frontend/index.html",
                    "purpose": "Complete semantic HTML5 application structure with all required sections, navigation, interactive controls, and clean markup.",
                    "priority": 1,
                },
                {
                    "path": "frontend/css/styles.css",
                    "purpose": "Comprehensive modern responsive CSS styling with variables, card layouts, animations, and mobile/tablet media queries.",
                    "priority": 2,
                },
                {
                    "path": "frontend/js/app.js",
                    "purpose": "Complete interactive JavaScript application logic, navigation toggling, animations, and state handling.",
                    "priority": 3,
                },
            ]
            arch_folder = str(memory.architecture.folder_structure or "")
            arch_modules = [m.get("name", "").lower() for m in (memory.architecture.modules or [])]
            if "tasks.js" in arch_folder or any("task" in m for m in arch_modules):
                planned.append({
                    "path": "frontend/js/tasks.js",
                    "purpose": "Task data operations, validation, filtering, and statistical metrics.",
                    "priority": 4,
                })
            plan_usage = TokenUsage()
            await ctx.log(self.role, f"Planned {len(planned)} frontend source files deterministically")
        elif adapter.key == "react" and (not memory.needs_backend or "portfolio" in str(user_req).lower()):
            planned = [
                {
                    "path": "frontend/src/index.css",
                    "purpose": "Tailwind directives and modern responsive design system styling tokens.",
                    "priority": 1,
                },
                {
                    "path": "frontend/src/App.tsx",
                    "purpose": "Complete production React + TypeScript component hierarchy implementing all requested sections.",
                    "priority": 2,
                },
                {
                    "path": "frontend/src/main.tsx",
                    "purpose": "Root application render mounting <App /> in StrictMode into DOM root.",
                    "priority": 3,
                },
            ]
            plan_usage = TokenUsage()
            await ctx.log(self.role, f"Planned {len(planned)} React source files deterministically")
        else:
            plan_rules = (
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
            )

            planned, plan_usage = await self.plan_files(
                ctx,
                instruction=(
                    f"PROJECT REQUIREMENTS:\n{user_req}\n\n"
                    "Plan every source file for the frontend application.\n\n"
                    f"{conventions}\n\n"
                    f"{api_context}\n\n"
                    f"{screens}\n\n"
                    f"{plan_rules}"
                ),
            )
            await ctx.log(self.role, f"Planned {len(planned)} frontend source files")

        batch_size = len(planned) if adapter.key in ("html_css_js", "react") else None
        html_rules = ""
        if adapter.key == "html_css_js":
            arch_summary = memory.architecture.overview or ""
            html_rules = (
                f"\n\nPROJECT REQUIREMENTS:\n{user_req}\n"
                f"{f'ARCHITECTURE OVERVIEW: {arch_summary}' if arch_summary else ''}\n\n"
                "COMPLETE SINGLE-PASS IMPLEMENTATION REQUIREMENTS:\n"
                "- Produce the COMPLETE, fully-implemented, production-ready frontend in this single response.\n"
                "- In `frontend/index.html`: implement complete semantic HTML structure matching all user requirements, "
                "with full navigation, all content sections (hero, about, skills, projects, experience, contact, etc.), "
                "forms, and footer.\n"
                "- In `frontend/css/styles.css`: implement complete, beautiful modern responsive CSS styling with :root variables, "
                "cards, smooth transitions, hover effects, flexbox/grid layouts, and responsive breakpoints.\n"
                "- In `frontend/js/app.js`: implement complete interactive logic, mobile menu toggling, smooth scrolling, "
                "active link highlighting, form submission handling, and animations.\n"
                "- Do NOT write placeholders or comments like '// Add remaining code here'. Write the full code.\n"
            )
        elif adapter.key == "react":
            arch_summary = memory.architecture.overview or ""
            html_rules = (
                f"\n\nPROJECT REQUIREMENTS:\n{user_req}\n"
                f"{f'ARCHITECTURE OVERVIEW: {arch_summary}' if arch_summary else ''}\n\n"
                "COMPLETE SINGLE-PASS REACT IMPLEMENTATION REQUIREMENTS:\n"
                "- Produce the COMPLETE, fully-implemented, production-ready React 18 + TypeScript frontend.\n"
                "- In `frontend/src/index.css`: implement Tailwind directives and global styles.\n"
                "- In `frontend/src/App.tsx`: implement complete React component hierarchy matching all user requirements, "
                "with full navigation, mobile menu, all content sections (hero, about, skills, projects, experience, education, services, contact), "
                "animations, project cards, social links, CV download button, and footer.\n"
                "- In `frontend/src/main.tsx`: import React, ReactDOM from 'react-dom/client', App from './App', and './index.css', "
                "mounting <App /> in StrictMode into document.getElementById('root')!.\n"
                "- Do NOT write placeholders or comments like '// Add remaining code here'. Write the full code.\n"
            )

        # Determine protected scaffold files
        scaffold_paths = {normalise_path(f.path) for f in scaffold_files}
        planned_paths = {normalise_path(str(p.get("path", ""))) for p in planned}
        protected_paths = (PROTECTED_SCAFFOLD_FILES | scaffold_paths) - planned_paths

        instruction_parts = [
            DEPENDENCY_SAFETY_RULES,
            TYPESCRIPT_SAFETY_RULES,
            SCAFFOLDED_FILES_RULES,
            conventions,
            api_context,
            (
                "Every component must render loading, error and empty states where "
                "it loads data. Every interactive element must be keyboard accessible."
            ),
        ]
        if html_rules:
            instruction_parts.append(html_rules)
        extra_instruction = "\n\n".join(part for part in instruction_parts if part)

        written, gen_usage, warnings = await self.generate_files(
            ctx,
            planned,
            batch_size=batch_size,
            progress_from=20,
            progress_to=95,
            config_context=config_context,
            extra_instruction=extra_instruction,
            protected_paths=protected_paths,
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

    @classmethod
    def build_configuration_context(cls, memory: SharedProjectMemory) -> str:
        """Retrieve actual scaffold configuration files directly from the workspace."""
        candidate_paths = [
            "frontend/package.json",
            "frontend/tsconfig.json",
            "frontend/tsconfig.app.json",
            "frontend/tsconfig.node.json",
            "frontend/vite.config.ts",
            "frontend/index.html",
        ]
        file_blocks: list[str] = []
        for path in candidate_paths:
            content = memory.workspace.read(path)
            if content is not None:
                file_blocks.append(f"=== {path} ===\n{content.strip()}")

        if not file_blocks:
            return ""

        return (
            "PROJECT CONFIGURATION CONTEXT\n\n"
            "The following files already exist in the project.\n\n"
            "You MUST treat them as authoritative.\n\n"
            + "\n\n".join(file_blocks)
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
