"""The contract every model provider satisfies.

An adapter is a thin seam between one vendor and the provider manager. It owns
exactly two things the manager cannot know for itself: how to call the vendor,
and how to classify what comes back when the call fails.

It deliberately does *not* own retrying, provider selection, caching or health.
Those are cross-provider policies; duplicating them per adapter is how five
providers become five subtly different behaviours.

Adding a provider means one subclass and one registry entry. Nothing in the
agent, workflow, adapter or packaging layers changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.core.enums import ErrorKind
from app.llm.types import Completion, PromptBundle, TextCompletion


@dataclass(frozen=True, slots=True)
class ProviderSpec:
    """Static description of a configured provider."""

    key: str
    display_name: str
    model: str
    priority: int
    enabled: bool = True
    #: Free-form notes shown on the dashboard (e.g. "free tier", "local").
    tags: tuple[str, ...] = ()

    #: Largest prompt this provider will accept, in tokens. 0 means no known
    #: limit. Declaring it lets routing skip a provider that cannot fit the
    #: request instead of spending a round trip to be told so — a free tier
    #: capped at 12k tokens per minute can never serve a 27k-token prompt, and
    #: discovering that once per agent is pure latency.
    max_prompt_tokens: int = 0
    #: Ceiling on requested output tokens. 0 means use the platform default.
    #: Providers that bill input and output against one per-minute budget
    #: reject a large `max_tokens` even when the prompt itself is small.
    max_output_tokens: int = 0

    options: dict[str, Any] = field(default_factory=dict)


class ProviderAdapter(ABC):
    """One vendor, behind a uniform interface."""

    def __init__(self, spec: ProviderSpec) -> None:
        self.spec = spec

    @property
    def key(self) -> str:
        return self.spec.key

    @property
    def display_name(self) -> str:
        return self.spec.display_name

    @property
    def model(self) -> str:
        return self.spec.model

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """Whether this provider has everything it needs to be called.

        A provider missing its key is reported as unconfigured on the
        dashboard rather than being hidden, so the reason it is not
        participating is visible.
        """

    @abstractmethod
    async def complete_structured(self, prompt: PromptBundle) -> Completion:
        """Produce JSON conforming to `prompt.schema`."""

    @abstractmethod
    async def complete_text(self, prompt: PromptBundle) -> TextCompletion:
        """Produce free-form text."""

    @abstractmethod
    def classify(self, error: BaseException) -> ErrorKind:
        """Decide what the manager should do about a failure from this vendor."""

    async def aclose(self) -> None:
        """Release transport resources. Adapters without any need not override."""
        return None

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<{type(self).__name__} {self.key} model={self.model}>"
