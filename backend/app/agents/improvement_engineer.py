"""Code Improvement Engineer agent.

Applies the Review Engineer's findings by rewriting affected files. Skipped when
the review found nothing actionable — rewriting sound code to look busy is a
regression risk, not an improvement.
"""

from __future__ import annotations

from app.agents.base import CodeAgent
from app.agents.context import AgentContext
from app.agents.results import AgentResult, SkipDecision
from app.core.enums import AgentRole, LogLevel
from app.llm import schema as s

IMPROVEMENT_SCHEMA = s.obj(
    {
        "files": s.array(
            s.obj(
                {
                    "path": s.string("Path of the file being replaced, exactly as given."),
                    "content": s.string("Complete revised file. Never a partial diff."),
                    "description": s.string("What changed and why."),
                }
            ),
            description="Rewritten files. Only files you actually changed.",
        ),
        "resolved_issue_ids": s.string_array("Identifiers of the issues these edits resolve."),
        "unresolved": s.array(
            s.obj(
                {
                    "issue_id": s.string("Identifier of the issue left unresolved."),
                    "reason": s.string("Why it was not addressed in this pass."),
                }
            ),
        ),
        "notes": s.string("Summary of the changes applied."),
    }
)

_MAX_ISSUES_PER_PASS = 12


class ImprovementEngineerAgent(CodeAgent):
    role = AgentRole.IMPROVEMENT_ENGINEER
    display_name = "Code Improvement Engineer"
    description = (
        "Refactors generated code to resolve review findings, improving naming, "
        "readability, structure and maintainability."
    )
    depends_on = (AgentRole.REVIEW_ENGINEER,)

    def should_execute(self, ctx: AgentContext) -> SkipDecision:
        review = ctx.memory.review
        actionable = [
            issue
            for issue in review.issues
            if issue.get("severity") in {"critical", "high", "medium"}
        ]
        if not actionable and not review.duplication:
            return SkipDecision.skip(
                "The code review found no actionable issues, so no refactoring is needed."
            )
        return SkipDecision.run()

    def system_prompt(self, ctx: AgentContext) -> str:
        return """\
ROLE: Code Improvement Engineer

You resolve the specific issues raised in code review by rewriting the affected \
files.

## Scope discipline

Fix what was reported. Do not:
- Rewrite files that have no reported issue.
- Reformat or restyle code that works.
- Add features, abstractions or configuration nobody asked for.
- Change a public interface unless an issue specifically requires it — other \
files import these, and you are not rewriting them.

Unrequested changes are the main way a refactoring pass introduces regressions. \
The narrower your diff, the safer it is.

## How to emit changes

- Return the **complete** file, not a diff or a fragment. Your output replaces \
the file wholesale, so anything you omit is deleted.
- Preserve every import and export the file already had unless an issue \
requires the change.
- Keep the file's existing conventions — naming, structure, error handling — \
even where you would personally have chosen differently. Consistency with the \
rest of the codebase matters more than your preference.

## Honesty

If an issue cannot be fixed without changes beyond your scope, list it in \
`unresolved` with the reason. Silently skipping a reported issue while implying \
it was handled is worse than leaving it open."""

    async def execute(self, ctx: AgentContext) -> AgentResult:
        memory = ctx.memory
        review = memory.review

        issues = sorted(
            (i for i in review.issues if i.get("severity") in {"critical", "high", "medium"}),
            key=lambda i: {"critical": 0, "high": 1, "medium": 2}.get(str(i.get("severity")), 3),
        )[:_MAX_ISSUES_PER_PASS]

        await ctx.progress(self.role, 15, f"Addressing {len(issues)} review finding(s)")

        target_paths = self._target_paths(ctx, issues)
        if not target_paths:
            summary = "No reviewed file could be located in the workspace; nothing changed."
            memory.record_summary(self.role, summary)
            return AgentResult(role=self.role, summary=summary, confidence=0.5)

        sources = "\n\n".join(
            f"--- {path} ---\n{memory.workspace.read(path)}" for path in target_paths
        )
        issue_list = "\n".join(
            f"- [{i.get('id', '?')}] ({i.get('severity')}, {i.get('category')}) "
            f"{i.get('file') or 'project-wide'}: {i.get('description')}\n"
            f"    recommendation: {i.get('recommendation')}"
            for i in issues
        )
        duplication = ""
        if review.duplication:
            duplication = "\n\nDUPLICATION TO CONSOLIDATE:\n" + "\n".join(
                f"- {d.get('description')} (in {', '.join(d.get('files', []))}) "
                f"-> {d.get('recommendation')}"
                for d in review.duplication[:5]
            )

        await ctx.progress(self.role, 40, "Rewriting affected files")

        completion = await ctx.llm.complete_structured(
            self.build_prompt(
                ctx,
                instruction=(
                    "Resolve these review findings by rewriting the affected "
                    f"files.\n\nFINDINGS:\n{issue_list}{duplication}\n\n"
                    f"CURRENT FILE CONTENTS:\n{sources}\n\n"
                    "Return only the files you actually changed, each complete. "
                    "Leave everything else untouched."
                ),
                schema=IMPROVEMENT_SCHEMA,
                include_files=False,
                max_tokens=30000,
            )
        )

        await ctx.progress(self.role, 85, "Applying changes")

        files = completion.data.get("files", [])
        # Constrain rewrites to files that already exist. A "fix" that invents a
        # new file is out of scope and usually a hallucinated path.
        allowed = [
            f
            for f in files
            if isinstance(f, dict) and memory.workspace.exists(str(f.get("path", "")))
        ]
        rejected_new = len(files) - len(allowed)

        accepted, rejected = memory.workspace.write_many(allowed, produced_by=self.role)

        resolved = completion.data.get("resolved_issue_ids", [])
        unresolved = completion.data.get("unresolved", [])
        notes = str(completion.data.get("notes", "")).strip()

        for entry in accepted:
            await ctx.log(self.role, f"Revised {entry.path}", level=LogLevel.DEBUG)
        for item in unresolved:
            await ctx.log(
                self.role,
                f"Unresolved [{item.get('issue_id')}]: {item.get('reason')}",
                level=LogLevel.WARNING,
            )
        if rejected_new:
            await ctx.log(
                self.role,
                f"Ignored {rejected_new} proposed new file(s); this pass only revises "
                "existing files.",
                level=LogLevel.WARNING,
            )

        memory.improvements_applied = [str(r) for r in resolved]
        if notes:
            memory.add_note(f"{self.display_name}: {notes}")

        warnings = [f"Rejected {r['path']}: {r['reason']}" for r in rejected]
        warnings += [f"Unresolved {u.get('issue_id')}: {u.get('reason')}" for u in unresolved]

        confidence = self._confidence(len(issues), len(resolved), len(accepted))
        ctx.memory.record_confidence("improvement", confidence)

        summary = (
            f"Revised {len(accepted)} file(s), resolving {len(resolved)} of "
            f"{len(issues)} finding(s)."
        )
        memory.record_summary(self.role, summary)
        await ctx.progress(self.role, 100, "Improvements applied")

        return AgentResult(
            role=self.role,
            summary=summary,
            output={
                "files_revised": len(accepted),
                "resolved_issue_ids": resolved,
                "unresolved": unresolved,
                "notes": notes,
            },
            usage=completion.usage,
            files_produced=len(accepted),
            confidence=confidence,
            warnings=warnings,
        )

    @staticmethod
    def _target_paths(ctx: AgentContext, issues: list[dict]) -> list[str]:
        """Files named by the findings, capped so the prompt stays bounded."""
        workspace = ctx.memory.workspace
        paths: list[str] = []
        seen: set[str] = set()

        for issue in issues:
            path = str(issue.get("file", "")).strip()
            if path and path not in seen and workspace.exists(path):
                paths.append(path)
                seen.add(path)

        for entry in ctx.memory.review.duplication:
            for path in entry.get("files", []):
                path = str(path).strip()
                if path and path not in seen and workspace.exists(path):
                    paths.append(path)
                    seen.add(path)

        return paths[:14]

    @staticmethod
    def _confidence(total_issues: int, resolved: int, revised: int) -> float:
        if total_issues == 0:
            return 1.0
        resolution_rate = min(resolved / total_issues, 1.0)
        applied = 1.0 if revised > 0 else 0.0
        return round(0.7 * resolution_rate + 0.3 * applied, 3)
