"""Plugin-based technology adapter system."""

from app.adapters.base import (
    AdapterDescriptor,
    BackendAdapter,
    DatabaseAdapter,
    FrontendAdapter,
    ScaffoldContext,
    ScaffoldFile,
    TechnologyAdapter,
)
from app.adapters.registry import AdapterRegistry, build_default_registry, get_registry

__all__ = [
    "AdapterDescriptor",
    "AdapterRegistry",
    "BackendAdapter",
    "DatabaseAdapter",
    "FrontendAdapter",
    "ScaffoldContext",
    "ScaffoldFile",
    "TechnologyAdapter",
    "build_default_registry",
    "get_registry",
]
