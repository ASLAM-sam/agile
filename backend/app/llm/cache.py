"""Prompt cache shared across agents, runs and providers.

Agents re-ask the same question more often than it looks: a retried run, a
second generation of the same project, and the two-phase code agents all reissue
identical prompts. Serving those from memory removes the single largest source
of avoidable quota spend.

The key is deliberately provider-agnostic. A response produced by Gemini is
served to a later request that would have gone to Groq, because the prompt and
schema — not the vendor — determine what a correct answer looks like. That is
also what makes the cache most valuable during failover.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from app.core.logging import get_logger
from app.llm.types import Completion, TextCompletion, TokenUsage

logger = get_logger(__name__)


def _fingerprint(
    *,
    cacheable_system: str,
    volatile_system: str,
    user_message: str,
    schema: dict[str, Any] | None,
    max_tokens: int | None,
) -> str:
    """A stable identity for one request's *content*.

    `sort_keys` matters: two schemas that differ only in key order describe the
    same constraint and must not occupy two cache entries.
    """
    payload = json.dumps(
        {
            "cacheable_system": cacheable_system,
            "volatile_system": volatile_system,
            "user_message": user_message,
            "schema": schema,
            "max_tokens": max_tokens,
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class _Entry:
    value: Any
    stored_at: float
    provider: str


@dataclass(slots=True)
class CacheStats:
    """Counters surfaced on the provider dashboard."""

    hits: int = 0
    misses: int = 0
    stores: int = 0
    evictions: int = 0

    @property
    def lookups(self) -> int:
        return self.hits + self.misses

    @property
    def hit_rate(self) -> float:
        return self.hits / self.lookups if self.lookups else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "stores": self.stores,
            "evictions": self.evictions,
            "lookups": self.lookups,
            "hit_rate": round(self.hit_rate, 4),
        }


class PromptCache:
    """Bounded, time-limited, in-process response cache.

    In-process rather than shared: version 1 runs as a single API process, and
    a network cache would add a dependency and a failure mode for a component
    whose entire purpose is to make the system more resilient.
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        max_entries: int = 512,
        ttl_seconds: float = 3600.0,
    ) -> None:
        self._enabled = enabled
        self._max_entries = max(1, max_entries)
        self._ttl = ttl_seconds
        self._entries: OrderedDict[str, _Entry] = OrderedDict()
        self.stats = CacheStats()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def __len__(self) -> int:
        return len(self._entries)

    def key_for(
        self,
        *,
        cacheable_system: str,
        volatile_system: str,
        user_message: str,
        schema: dict[str, Any] | None,
        max_tokens: int | None,
        structured: bool,
    ) -> str:
        """Cache key for one request.

        `structured` participates because the same prompt asked for JSON and
        asked for prose are different questions with different answers.
        """
        digest = _fingerprint(
            cacheable_system=cacheable_system,
            volatile_system=volatile_system,
            user_message=user_message,
            schema=schema,
            max_tokens=max_tokens,
        )
        return f"{'structured' if structured else 'text'}:{digest}"

    def get(self, key: str) -> Any | None:
        """Return a live entry, or None on miss or expiry.

        A non-positive `ttl_seconds` disables expiry, leaving size the only
        bound. Entries still go when evicted or when the process restarts.
        """
        if not self._enabled:
            return None
        entry = self._entries.get(key)
        if entry is None:
            self.stats.misses += 1
            return None
        if self._ttl > 0 and (time.monotonic() - entry.stored_at) > self._ttl:
            del self._entries[key]
            self.stats.misses += 1
            self.stats.evictions += 1
            return None
        self._entries.move_to_end(key)
        self.stats.hits += 1
        return self._replay(entry.value)

    def set(self, key: str, value: Any, *, provider: str) -> None:
        """Store a response, evicting the least recently used if full."""
        if not self._enabled:
            return
        self._entries[key] = _Entry(value=value, stored_at=time.monotonic(), provider=provider)
        self._entries.move_to_end(key)
        self.stats.stores += 1
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)
            self.stats.evictions += 1

    def clear(self) -> None:
        self._entries.clear()

    @staticmethod
    def _replay(value: Any) -> Any:
        """Hand back a copy whose usage reads as zero.

        A cache hit costs no tokens. Returning the original object would let a
        caller mutate the cached entry, and reporting the original token counts
        would inflate every run report by the tokens the cache just saved.
        """
        if isinstance(value, Completion):
            return Completion(
                data=json.loads(json.dumps(value.data)),
                usage=TokenUsage(),
                stop_reason=value.stop_reason,
                model=value.model,
                raw_text=value.raw_text,
            )
        if isinstance(value, TextCompletion):
            return TextCompletion(
                text=value.text,
                usage=TokenUsage(),
                stop_reason=value.stop_reason,
                model=value.model,
            )
        return value
