"""Provider construction and lifetime.

`build_llm_provider()` returns the process-wide `RoleBasedProviderManager`.
Sharing it is the point — the prompt cache only means anything if it outlives
a single run. A manager rebuilt per request would never serve a cache hit.

Because the instance is shared, callers must not close it. It is closed once,
at application shutdown, by `close_llm_provider()`.
"""

from __future__ import annotations

from app.core.config import Settings
from app.core.logging import get_logger
from app.llm.manager import RoleBasedProviderManager

logger = get_logger(__name__)

_manager: RoleBasedProviderManager | None = None

# Keep ProviderManager and LLMManager names for backwards compat
ProviderManager = RoleBasedProviderManager
LLMManager = RoleBasedProviderManager


def build_llm_provider(config: Settings | None = None) -> RoleBasedProviderManager:
    """Return the shared provider manager, constructing it on first use."""
    global _manager
    if _manager is None:
        _manager = RoleBasedProviderManager(config=config)
        snapshot = _manager.stats_snapshot()
        logger.info(
            "llm_providers_initialised",
            extra={
                "configured_slots": ",".join(snapshot["available_providers"]),
                "failover_enabled": snapshot["failover_enabled"],
                "cache_enabled": snapshot["cache_enabled"],
            },
        )
    return _manager


def get_llm_provider() -> RoleBasedProviderManager:
    """Alias used by the API layer, where construction is never intended."""
    return build_llm_provider()


get_llm_manager = get_llm_provider


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
