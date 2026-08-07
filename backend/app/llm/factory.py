"""Provider construction and lifetime.

`build_llm_provider()` returns the process-wide `ProviderManager`. Sharing it is
the point, not an optimisation: cooldowns, health counters and the prompt cache
only mean anything if they outlive a single run. A manager rebuilt per request
would rediscover an exhausted quota on every agent, and would never serve a
cache hit.

Because the instance is shared, callers must not close it. It is closed once,
at application shutdown, by `close_llm_provider()`.
"""

from __future__ import annotations

from app.core.config import Settings
from app.core.logging import get_logger
from app.llm.manager import ProviderManager

logger = get_logger(__name__)

_manager: ProviderManager | None = None


def build_llm_provider(config: Settings | None = None) -> ProviderManager:
    """Return the shared provider manager, constructing it on first use."""
    global _manager
    if _manager is None:
        _manager = ProviderManager(config=config)
        snapshot = _manager.stats_snapshot()
        logger.info(
            "llm_providers_initialised",
            extra={
                "priority": ",".join(snapshot["priority"]),
                "available": ",".join(snapshot["available_providers"]),
                "failover_enabled": snapshot["failover_enabled"],
                "cache_enabled": snapshot["cache_enabled"],
            },
        )
    return _manager


def get_llm_provider() -> ProviderManager:
    """Alias used by the API layer, where construction is never intended."""
    return build_llm_provider()


async def close_llm_provider() -> None:
    """Release provider transports. Called once from the app lifespan."""
    global _manager
    if _manager is not None:
        await _manager.aclose()
        _manager = None


def reset_llm_provider() -> None:
    """Drop the shared instance so the next call rebuilds it.

    Exists for tests, which need a manager built against their own settings
    rather than whatever a previous test left behind.
    """
    global _manager
    _manager = None
