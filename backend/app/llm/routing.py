"""Task-aware provider ordering.

Not every request deserves the same provider. Writing a service layer is worth
the strongest available model; producing an installation guide is not, and
spending a scarce quota on prose is what leaves nothing for the code.

The task kind is derived from the calling agent's role, which every prompt
already carries in its metadata. Agents therefore express *what* they are doing
and never *who* should do it — the rule the brief calls for, achieved without
touching a single agent.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.enums import AgentRole, TaskKind

#: Which kind of work each engineer performs. An agent missing from this map
#: routes as REASONING, the safest default: it prefers the strongest provider.
AGENT_TASK_KINDS: dict[AgentRole, TaskKind] = {
    AgentRole.MANAGER: TaskKind.SUMMARY,
    AgentRole.BUSINESS_ANALYST: TaskKind.REASONING,
    AgentRole.SOLUTION_ARCHITECT: TaskKind.REASONING,
    AgentRole.DATABASE_ENGINEER: TaskKind.REASONING,
    AgentRole.BACKEND_ENGINEER: TaskKind.CODE_GENERATION,
    AgentRole.FRONTEND_ENGINEER: TaskKind.CODE_GENERATION,
    AgentRole.QA_ENGINEER: TaskKind.CODE_GENERATION,
    AgentRole.REVIEW_ENGINEER: TaskKind.REVIEW,
    AgentRole.IMPROVEMENT_ENGINEER: TaskKind.CODE_GENERATION,
    AgentRole.DOCUMENTATION_ENGINEER: TaskKind.DOCUMENTATION,
    AgentRole.ARTIFACT_MANAGER: TaskKind.SUMMARY,
}

#: Provider keys preferred for each task kind, strongest-first. These are
#: *preferences*, not restrictions: anything not named still follows behind in
#: configured priority order, so a preference can never strand a request.
#:
#: NVIDIA NIM sits ahead of Groq on the demanding tasks and behind it on the
#: cheap ones: its catalogue runs large-context open models that hold a full
#: code-review prompt, which the smaller free tiers reject outright, but prose
#: is not worth spending it on. No existing provider moved relative to another.
DEFAULT_TASK_PREFERENCES: dict[TaskKind, tuple[str, ...]] = {
    TaskKind.REASONING: ("gemini", "anthropic", "openai", "nvidia", "groq", "ollama"),
    TaskKind.CODE_GENERATION: ("gemini", "anthropic", "openai", "nvidia", "groq", "ollama"),
    TaskKind.REVIEW: ("gemini", "anthropic", "openai", "nvidia", "groq", "ollama"),
    TaskKind.DOCUMENTATION: ("groq", "gemini", "nvidia", "ollama", "openai", "anthropic"),
    TaskKind.SUMMARY: ("groq", "gemini", "nvidia", "ollama", "openai", "anthropic"),
}


#: Average characters per token across the English prose and source code these
#: prompts contain. Deliberately conservative — under-estimating the prompt is
#: what sends a request to a provider that cannot hold it.
_CHARS_PER_TOKEN = 3.5


def estimate_tokens(*parts: str) -> int:
    """Approximate the token cost of a prompt.

    A real tokeniser would be exact, but it would be a per-vendor dependency
    invoked on every request to answer a question that only needs to be right
    to within a wide margin: does this prompt plausibly fit? The estimate is
    used solely to order and filter candidates, never to bill or truncate.
    """
    characters = sum(len(part) for part in parts if part)
    return int(characters / _CHARS_PER_TOKEN) + 1


def task_kind_for_agent(agent: str | None) -> TaskKind:
    """Map a prompt's `metadata["agent"]` to the work it represents."""
    if not agent:
        return TaskKind.REASONING
    try:
        role = AgentRole(agent)
    except ValueError:
        return TaskKind.REASONING
    return AGENT_TASK_KINDS.get(role, TaskKind.REASONING)


@dataclass(slots=True)
class RoutingTable:
    """Turns a task kind plus a priority list into an ordered candidate list."""

    #: Global fallback order, most preferred first.
    priority: tuple[str, ...]
    #: Per-task overrides layered on top of `priority`.
    preferences: dict[TaskKind, tuple[str, ...]] = field(
        default_factory=lambda: dict(DEFAULT_TASK_PREFERENCES)
    )
    #: When False, `priority` alone decides and task kind is ignored.
    task_routing_enabled: bool = True

    def order_for(self, task: TaskKind, *, available: set[str] | None = None) -> list[str]:
        """Candidate providers for one request, best first.

        Preferred providers come first in preference order; everything else
        follows in configured priority order. The result always contains every
        available provider — routing changes *who is tried first*, never *who
        is reachable*, so a preference can never turn into a single point of
        failure.
        """
        pool = [key for key in self.priority if available is None or key in available]
        if not self.task_routing_enabled:
            return pool

        preferred = self.preferences.get(task, ())
        head = [key for key in preferred if key in pool]
        tail = [key for key in pool if key not in head]
        return head + tail
