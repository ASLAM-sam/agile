"""Value objects exchanged with the language-model provider."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True, frozen=True)
class TokenUsage:
    """Token accounting for a single completion."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cache_write_tokens=self.cache_write_tokens + other.cache_write_tokens,
        )

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens

    def as_dict(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "total_tokens": self.total,
        }


@dataclass(slots=True)
class Completion:
    """A structured response from the model."""

    data: dict[str, Any]
    usage: TokenUsage
    stop_reason: str | None = None
    model: str = ""
    raw_text: str = ""


@dataclass(slots=True)
class TextCompletion:
    """A free-form text response from the model."""

    text: str
    usage: TokenUsage
    stop_reason: str | None = None
    model: str = ""


@dataclass(slots=True)
class PromptBundle:
    """A fully assembled request to the model.

    `cacheable_system` is the stable prefix eligible for prompt caching; it must
    not contain per-request values such as timestamps or identifiers.
    """

    cacheable_system: str
    volatile_system: str = ""
    user_message: str = ""
    schema: dict[str, Any] | None = None
    max_tokens: int | None = None
    effort: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
