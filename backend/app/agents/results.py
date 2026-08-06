"""Agent result value objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.enums import AgentRole
from app.llm.types import TokenUsage


@dataclass(slots=True)
class AgentResult:
    """What an agent returns to the workflow engine."""

    role: AgentRole
    summary: str
    output: dict[str, Any] = field(default_factory=dict)
    usage: TokenUsage = field(default_factory=TokenUsage)
    files_produced: int = 0
    confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "role": self.role.value,
            "summary": self.summary,
            "output": self.output,
            "usage": self.usage.as_dict(),
            "files_produced": self.files_produced,
            "confidence": self.confidence,
            "warnings": self.warnings,
        }


@dataclass(slots=True)
class SkipDecision:
    """Why an agent was not required for this project."""

    skipped: bool
    reason: str = ""

    @classmethod
    def run(cls) -> SkipDecision:
        return cls(skipped=False)

    @classmethod
    def skip(cls, reason: str) -> SkipDecision:
        return cls(skipped=True, reason=reason)
