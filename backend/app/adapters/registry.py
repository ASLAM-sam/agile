"""Adapter registry — the extension point of the plugin system.

New technologies are registered here and become immediately available to the
recommendation engine, the stack-selection UI and every code-generating agent.
Nothing else in the codebase enumerates technologies.
"""

from __future__ import annotations

from typing import overload

from app.adapters.base import (
    AdapterDescriptor,
    BackendAdapter,
    DatabaseAdapter,
    FrontendAdapter,
    TechnologyAdapter,
)
from app.core.enums import AdapterKind
from app.core.exceptions import AdapterNotFoundError
from app.core.logging import get_logger

logger = get_logger(__name__)


class AdapterRegistry:
    """Keyed store of every available technology adapter."""

    def __init__(self) -> None:
        self._adapters: dict[AdapterKind, dict[str, TechnologyAdapter]] = {
            kind: {} for kind in AdapterKind
        }

    def register(self, adapter: TechnologyAdapter) -> None:
        bucket = self._adapters[adapter.kind]
        if adapter.key in bucket:
            raise ValueError(
                f"Adapter '{adapter.key}' is already registered for {adapter.kind.value}."
            )
        bucket[adapter.key] = adapter
        logger.debug("adapter_registered", extra={"key": adapter.key, "kind": adapter.kind.value})

    @overload
    def get(self, kind: AdapterKind, key: str) -> TechnologyAdapter: ...

    def get(self, kind: AdapterKind, key: str) -> TechnologyAdapter:
        """Resolve an adapter, raising a domain error when unknown."""
        adapter = self._adapters[kind].get(key)
        if adapter is None:
            available = ", ".join(sorted(self._adapters[kind])) or "none"
            raise AdapterNotFoundError(
                f"No {kind.value} adapter registered for '{key}'. Available: {available}.",
                details={"kind": kind.value, "requested": key},
            )
        return adapter

    def frontend(self, key: str) -> FrontendAdapter:
        adapter = self.get(AdapterKind.FRONTEND, key)
        assert isinstance(adapter, FrontendAdapter)
        return adapter

    def backend(self, key: str) -> BackendAdapter:
        adapter = self.get(AdapterKind.BACKEND, key)
        assert isinstance(adapter, BackendAdapter)
        return adapter

    def database(self, key: str) -> DatabaseAdapter:
        adapter = self.get(AdapterKind.DATABASE, key)
        assert isinstance(adapter, DatabaseAdapter)
        return adapter

    def list_kind(self, kind: AdapterKind) -> list[TechnologyAdapter]:
        return sorted(
            self._adapters[kind].values(),
            key=lambda adapter: (getattr(adapter, "catalogue_priority", 100), adapter.display_name),
        )

    def catalogue(self) -> dict[str, list[AdapterDescriptor]]:
        """Full catalogue grouped by kind, for the stack-selection screen."""
        return {
            kind.value: [adapter.descriptor() for adapter in self.list_kind(kind)]
            for kind in AdapterKind
        }

    def keys(self, kind: AdapterKind) -> list[str]:
        return sorted(self._adapters[kind])

    def has(self, kind: AdapterKind, key: str) -> bool:
        return key in self._adapters[kind]


def build_default_registry() -> AdapterRegistry:
    """Construct the registry with every first-party adapter installed."""
    from app.adapters.backend.express import ExpressAdapter
    from app.adapters.backend.fastapi_adapter import FastAPIAdapter
    from app.adapters.backend.spring_boot import SpringBootAdapter
    from app.adapters.database.mongo import MongoDBAdapter
    from app.adapters.database.sqlite import SQLiteAdapter
    from app.adapters.frontend.angular import AngularAdapter
    from app.adapters.frontend.html_css_js import HTMLCssJsAdapter
    from app.adapters.frontend.nextjs import NextJSAdapter
    from app.adapters.frontend.react import ReactAdapter

    registry = AdapterRegistry()
    for adapter in (
        HTMLCssJsAdapter(),
        ReactAdapter(),
        NextJSAdapter(),
        AngularAdapter(),
        FastAPIAdapter(),
        ExpressAdapter(),
        SpringBootAdapter(),
        MongoDBAdapter(),
        SQLiteAdapter(),
    ):
        registry.register(adapter)
    return registry


_registry: AdapterRegistry | None = None


def get_registry() -> AdapterRegistry:
    """Process-wide adapter registry singleton."""
    global _registry
    if _registry is None:
        _registry = build_default_registry()
    return _registry
