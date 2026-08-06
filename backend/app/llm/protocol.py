"""Provider-agnostic interface consumed by the agent layer.

Agents depend on this protocol rather than on `LLMClient` directly, so the
provider can be swapped and tests can substitute a deterministic double without
touching agent code (dependency inversion).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.llm.types import Completion, PromptBundle, TextCompletion


@runtime_checkable
class LLMProvider(Protocol):
    """Minimal surface an agent needs from a language model."""

    @property
    def model(self) -> str: ...

    async def complete_structured(self, prompt: PromptBundle) -> Completion: ...

    async def complete_text(self, prompt: PromptBundle) -> TextCompletion: ...
