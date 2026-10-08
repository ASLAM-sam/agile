"""AI Review Engineer agent.

Reviews the generated codebase for architectural drift, duplication, missing
implementations and security issues. Its findings are the input to the Code
Improvement Engineer, so precision matters more than volume.
"""

from __future__ import annotations

from app.agents.base import Agent
from app.agents.context import AgentContext
from app.agents.results import AgentResult, SkipDecision
from app.core.enums import AgentRole, LogLevel
from app.llm import schema as s
from app.workflow.memory import ReviewFindings

REVIEW_SCHEMA = s.obj(
    {
        "issues": s.array(
            s.obj(
                {
                    "id": s.string("Stable identifier, e.g. 'ISS-01'."),
                    "severity": s.string(
                        "How much this matters.",
                        enum=["critical", "high", "medium", "low"],
                    ),
                    "category": s.string(
                        "Issue category.",
                        enum=[
                            "architecture",
                            "duplication",
                            "missing-implementation",
                            "security",
                            "correctness",
                            "consistency",
                            "maintainability",
                            "accessibility",
                        ],
                    ),
                    "file": s.string("The file path this concerns. Empty if project-wide."),
                    "description": s.string("The specific problem, stated concretely."),
                    "impact": s.string("What goes wrong if this is not fixed."),
                    "recommendation": s.string("The specific change that fixes it."),
                }
            ),
            description=(
                "Real, actionable issues only. An empty array is a valid and "
                "expected result for well-generated code."
            ),
        ),
        "strengths": s.string_array("What the codebase genuinely does well."),
        "missing_apis": s.string_array(
            "Endpoints in the API contract with no corresponding backend "
            "implementation. Empty if all are implemented."
        ),
        "duplication": s.array(
            s.obj(
                {
                    "description": s.string("The logic that appears more than once."),
                    "files": s.string_array("Files containing the duplicate."),
                    "recommendation": s.string("Where the shared code should live."),
                }
            )
        ),
        "overall_assessment": s.string("Two to three sentences of overall judgement."),
        "quality_score": s.number("Overall quality from 0.0 to 1.0."),
    }
)


class ReviewEngineerAgent(Agent):
    role = AgentRole.REVIEW_ENGINEER
    display_name = "AI Review Engineer"
    description = (
        "Reviews generated source for architectural issues, duplicated logic, "
        "missing APIs and security defects."
    )
    depends_on = (AgentRole.BACKEND_ENGINEER, AgentRole.FRONTEND_ENGINEER)

    def should_execute(self, ctx: AgentContext) -> SkipDecision:
        source_files = [
            f
            for f in ctx.memory.workspace.files
            if f.extension in {".py", ".ts", ".tsx", ".js", ".jsx", ".java", ".html", ".css"}
        ]
        if len(source_files) < 3:
            return SkipDecision.skip(
                "Too few source files were generated to warrant a code review."
            )
        return SkipDecision.run()

    def system_prompt(self, ctx: AgentContext) -> str:
        return """\
ROLE: AI Review Engineer

You review the generated codebase the way a senior engineer reviews a pull \
request from a competent colleague: looking for real problems, not for a reason \
to comment.

## What counts as an issue

Report something only if you can point to the specific file and state \
concretely what goes wrong. Every issue needs a defensible answer to "what \
breaks if we ship this?".

Look for, in priority order:
1. **Missing implementation** — an endpoint in the contract with no route; a \
service method referenced but never defined; an import of a module that was \
never written. These break the project outright.
2. **Security** — unparameterised SQL, a secret hardcoded in source, a missing \
authorisation check on an endpoint the contract marks as protected, a password \
hash returned in a response.
3. **Correctness** — logic that does not do what the requirement says.
4. **Architectural drift** — a route containing business logic, a service \
importing the web framework, a layer reaching past its neighbour.
5. **Duplication** — the same non-trivial logic written more than once.
6. **Consistency** — one module following a convention the rest ignore.

## What is not an issue

- Style preferences the conventions do not mandate.
- Absence of a feature that was explicitly out of scope.
- "Could add more tests" without naming what specifically is untested and why \
it matters.
- Hypothetical future problems the current requirements do not create.
- Anything you cannot tie to a specific file and a concrete consequence.

## Calibration

Report every real issue you find, at its honest severity, and stop there. Do \
not pad the list to look thorough — a short, accurate review is more useful \
than a long one padded with nits, because every issue you report becomes work \
for the next engineer. If the code is genuinely sound, return an empty issues \
array and say so.

Reserve `critical` for something that stops the project running, and `high` for \
a security defect or a broken core feature."""

    async def execute(self, ctx: AgentContext) -> AgentResult:
        await ctx.progress(self.role, 15, "Reading the generated codebase")

        code_context = self._code_context(ctx)

        await ctx.progress(self.role, 40, "Reviewing architecture, security and correctness")

        completion = await ctx.llm.complete_structured(
            self.build_prompt(
                ctx,
                instruction=(
                    "Review this generated codebase.\n\n"
                    f"{code_context}\n\n"
                    "Check specifically that every endpoint in the API contract has "
                    "a backend implementation, that no file imports something that "
                    "was never written, and that no secret is hardcoded. Report only "
                    "issues you can tie to a specific file and a concrete "
                    "consequence."
                ),
                schema=REVIEW_SCHEMA,
                max_tokens=6000,
            )
        )

        await ctx.progress(self.role, 85, "Recording findings")

        data = completion.data
        findings = ReviewFindings(
            issues=data.get("issues", []),
            strengths=data.get("strengths", []),
            missing_apis=data.get("missing_apis", []),
            duplication=data.get("duplication", []),
            overall_assessment=data.get("overall_assessment", ""),
            quality_score=float(data.get("quality_score", 0.0) or 0.0),
        )
        ctx.memory.review = findings

        blocking = findings.blocking_issues
        for issue in blocking[:8]:
            await ctx.log(
                self.role,
                f"[{issue.get('severity')}] {issue.get('file') or 'project'}: "
                f"{issue.get('description')}",
                level=LogLevel.WARNING,
            )

        if not findings.issues:
            await ctx.log(self.role, "Review found no actionable issues")

        ctx.memory.record_confidence("review", findings.quality_score)

        summary = (
            f"{len(findings.issues)} issue(s) found "
            f"({len(blocking)} blocking), quality score "
            f"{findings.quality_score:.0%}."
        )
        ctx.memory.record_summary(self.role, summary)
        await ctx.progress(self.role, 100, "Code review complete")

        return AgentResult(
            role=self.role,
            summary=summary,
            output=findings.as_dict(),
            usage=completion.usage,
            confidence=findings.quality_score,
            warnings=[str(i.get("description", "")) for i in blocking],
        )

    @staticmethod
    def _code_context(ctx: AgentContext, *, budget_chars: int = 90_000) -> str:
        """Assemble source for review, prioritising logic over configuration.

        The budget keeps the request well inside the context window on large
        projects; files are included whole so the reviewer never judges a
        truncated fragment.
        """
        workspace = ctx.memory.workspace

        def rank(path: str) -> int:
            lowered = path.lower()
            if any(k in lowered for k in ("service", "repositor", "controller", "route", "api")):
                return 0
            if any(k in lowered for k in ("model", "entit", "schema", "middleware", "security")):
                return 1
            if lowered.endswith((".json", ".yml", ".yaml", ".md", ".css")):
                return 3
            return 2

        candidates = sorted(
            (f for f in workspace.files if f.extension in
             {".py", ".ts", ".tsx", ".js", ".jsx", ".java", ".sql", ".html", ".css"}),
            key=lambda f: (rank(f.path), f.path),
        )

        blocks: list[str] = []
        used = 0
        omitted = 0
        for entry in candidates:
            block = f"--- {entry.path} ---\n{entry.content}\n"
            if used + len(block) > budget_chars:
                omitted += 1
                continue
            blocks.append(block)
            used += len(block)

        header = f"SOURCE UNDER REVIEW ({len(blocks)} files"
        header += f", {omitted} omitted for size)" if omitted else ")"
        return header + ":\n\n" + "\n".join(blocks)
