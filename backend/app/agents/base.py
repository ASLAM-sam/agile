"""Agent base classes.

`Agent` defines the contract the workflow engine depends on. `CodeAgent` adds
the two-phase generation strategy used by every code-producing engineer:

  1. **Plan** — the agent emits a file manifest (paths, purpose, dependencies).
     Small, cheap, and forces a coherent structure before any code exists.
  2. **Generate** — files are produced in ordered batches, each batch seeing the
     manifest and the paths already written.

The alternative — asking for an entire application in one completion — reliably
truncates and produces files that reference modules the model forgot to write.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.agents.context import AgentContext
from app.agents.results import AgentResult, SkipDecision
from app.core.config import settings
from app.core.enums import AgentRole, LogLevel
from app.core.exceptions import AgentExecutionError
from app.core.logging import get_logger
from app.llm.schema import FILE_BUNDLE_SCHEMA, FILE_PLAN_SCHEMA
from app.llm.types import PromptBundle, TokenUsage

logger = get_logger(__name__)


PLATFORM_PREAMBLE = """\
You are a senior engineer on an autonomous software engineering team called \
Aegis AI. The team transforms a plain-language software idea into a \
production-ready starter project.

Operating principles that apply to every role on this team:

- Produce production-quality work. No placeholders, no `TODO`, no `pass`, no \
`throw new Error('not implemented')`, no commented-out stubs, no sample data \
standing in for real logic. Every function you write must actually work.
- Follow SOLID principles, clean architecture and clear separation of concerns. \
One responsibility per file.
- Do not repeat yourself. If two pieces of code would be near-identical, factor \
out the shared part.
- Prefer clarity over cleverness. Another engineer must be able to read your \
output and extend it without asking questions.
- Match the conventions you are given exactly. They describe a scaffold that \
already exists; work that ignores them will not integrate.
- You are building a *starter project*: a complete, coherent, runnable \
foundation covering the core domain — not an exhaustive implementation of \
every conceivable feature.
- Only reference files, modules, functions and columns that exist or that you \
are creating in the same response. Never import something that was never \
written.
- Never invent a dependency. Use only libraries present in the manifest the \
scaffold provides.

You will receive project-specific context after this section. Treat it as \
authoritative: it is the shared memory of the whole team, written by the \
engineers who worked before you."""


class Agent(ABC):
    """Base class for every AI engineer on the team."""

    role: AgentRole
    display_name: str
    description: str = ""

    #: **Ordering only.** Roles whose output this agent reads if available. The
    #: engine schedules this agent after all of them, but their failure does not
    #: prevent it running.
    depends_on: tuple[AgentRole, ...] = ()

    #: **Hard requirement.** Roles this agent genuinely cannot function without.
    #: If one of these fails, this agent is skipped rather than run on missing
    #: input. Must be a subset of `depends_on`.
    #:
    #: Kept distinct from `depends_on` deliberately: conflating the two means a
    #: single non-essential agent failing (say, the QA Engineer) cascades into
    #: skipping documentation and packaging, discarding an otherwise complete
    #: project. Most dependencies are ordering, not requirement.
    requires: tuple[AgentRole, ...] = ()

    @abstractmethod
    async def execute(self, ctx: AgentContext) -> AgentResult:
        """Perform this agent's work, mutating shared memory."""

    def should_execute(self, ctx: AgentContext) -> SkipDecision:
        """Decide whether this agent is needed for the current project.

        Default is always-run. Agents whose relevance depends on the requirement
        analysis override this — that is what makes the workflow dynamic.
        """
        return SkipDecision.run()

    # --- prompting helpers ----------------------------------------------

    @abstractmethod
    def system_prompt(self, ctx: AgentContext) -> str:
        """Role-specific instructions appended to the cached platform preamble."""

    def cacheable_prefix(self, ctx: AgentContext) -> str:
        """Stable system prefix eligible for prompt caching.

        Contains only the platform preamble and this agent's role instructions —
        both identical across every call this agent makes in a run.
        """
        return f"{PLATFORM_PREAMBLE}\n\n{'=' * 70}\n\n{self.system_prompt(ctx)}"

    def build_prompt(
        self,
        ctx: AgentContext,
        *,
        instruction: str,
        schema: dict[str, Any] | None = None,
        max_tokens: int | None = None,
        include_files: bool = True,
        extra_context: str = "",
    ) -> PromptBundle:
        """Assemble a request with the standard three-part structure."""
        volatile = ctx.memory.context_digest(include_files=include_files)
        if extra_context:
            volatile = f"{volatile}\n\n{extra_context}"
        return PromptBundle(
            cacheable_system=self.cacheable_prefix(ctx),
            volatile_system=f"CURRENT PROJECT STATE\n{'=' * 70}\n{volatile}",
            user_message=instruction,
            schema=schema,
            max_tokens=max_tokens,
            metadata={"agent": self.role.value, "run_id": ctx.memory.run_id},
        )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<{type(self).__name__} {self.role.value}>"


class CodeAgent(Agent):
    """An agent that writes source files into the workspace."""

    #: Directory every file this agent writes must live under.
    output_root: str = ""

    async def plan_files(
        self,
        ctx: AgentContext,
        *,
        instruction: str,
        max_tokens: int = 8000,
    ) -> tuple[list[dict[str, Any]], TokenUsage]:
        """Phase 1 — produce the file manifest."""
        completion = await ctx.llm.complete_structured(
            self.build_prompt(
                ctx,
                instruction=instruction,
                schema=FILE_PLAN_SCHEMA,
                max_tokens=max_tokens,
            )
        )
        planned = completion.data.get("files", [])
        if not isinstance(planned, list) or not planned:
            raise AgentExecutionError(
                "The file plan came back empty.", agent=self.role.value
            )

        valid = [entry for entry in planned if self._plan_entry_is_valid(entry)]
        if not valid:
            raise AgentExecutionError(
                f"No planned file was under the required root '{self.output_root}'.",
                agent=self.role.value,
                details={"planned": [str(e.get("path")) for e in planned[:10]]},
            )

        valid.sort(key=lambda entry: int(entry.get("priority", 99)))
        rationale = str(completion.data.get("rationale", ""))
        if rationale:
            ctx.memory.add_note(f"{self.display_name}: {rationale}")

        return valid, completion.usage

    def _plan_entry_is_valid(self, entry: Any) -> bool:
        if not isinstance(entry, dict):
            return False
        path = str(entry.get("path", "")).strip()
        if not path:
            return False
        return not self.output_root or path.startswith(f"{self.output_root}/")

    async def generate_files(
        self,
        ctx: AgentContext,
        planned: list[dict[str, Any]],
        *,
        batch_size: int | None = None,
        progress_from: int = 20,
        progress_to: int = 90,
        extra_instruction: str = "",
    ) -> tuple[int, TokenUsage, list[str]]:
        """Phase 2 — generate file contents in ordered batches.

        Returns (files written, cumulative usage, warnings).
        """
        size = batch_size or settings.generation_batch_size
        batches = [planned[i : i + size] for i in range(0, len(planned), size)]
        total_usage = TokenUsage()
        written = 0
        warnings: list[str] = []

        for index, batch in enumerate(batches, start=1):
            span = progress_to - progress_from
            percent = progress_from + int(span * (index - 1) / max(len(batches), 1))
            await ctx.progress(
                self.role,
                percent,
                f"Writing files {index}/{len(batches)} ({len(batch)} in this batch)",
            )

            manifest = "\n".join(
                f"- {entry.get('path')} — {entry.get('purpose', 'no description')}"
                for entry in batch
            )
            already = ctx.memory.workspace.summary_for_prompt(limit=60)

            instruction = (
                "Generate the complete contents of exactly these files, and no "
                f"others:\n\n{manifest}\n\n"
                "Requirements for this batch:\n"
                "- Emit one entry per file listed above, using the exact path given.\n"
                "- Every file must be complete and immediately runnable. Never "
                "abbreviate with comments like '// rest of implementation'.\n"
                "- Only import from files that already exist (listed below) or that "
                "you are writing in this same batch.\n"
                "- Do not recreate any file that already exists.\n\n"
                f"FILES THAT ALREADY EXIST:\n{already}"
            )
            if extra_instruction:
                instruction = f"{instruction}\n\n{extra_instruction}"

            completion = await ctx.llm.complete_structured(
                self.build_prompt(
                    ctx,
                    instruction=instruction,
                    schema=FILE_BUNDLE_SCHEMA,
                    include_files=False,
                )
            )
            total_usage = total_usage + completion.usage

            files = completion.data.get("files", [])
            if not isinstance(files, list):
                warnings.append(f"Batch {index} returned no usable files.")
                continue

            accepted, rejected = ctx.memory.workspace.write_many(
                files, produced_by=self.role
            )
            written += len(accepted)

            for entry in accepted:
                await ctx.log(
                    self.role,
                    f"Wrote {entry.path}",
                    level=LogLevel.DEBUG,
                    path=entry.path,
                    bytes=entry.size_bytes,
                )
            for failure in rejected:
                message = f"Rejected {failure['path']}: {failure['reason']}"
                warnings.append(message)
                await ctx.log(self.role, message, level=LogLevel.WARNING)

            notes = str(completion.data.get("notes", "")).strip()
            if notes:
                ctx.memory.add_note(f"{self.display_name}: {notes}")

        if written == 0:
            raise AgentExecutionError(
                "No files were produced across any batch.",
                agent=self.role.value,
                details={"planned": len(planned), "warnings": warnings[:5]},
            )

        return written, total_usage, warnings
