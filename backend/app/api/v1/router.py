"""Version 1 API router aggregation."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.routes import artifacts, auth, catalog, generation, health, projects

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(projects.router)
api_router.include_router(generation.router)
api_router.include_router(artifacts.router)
api_router.include_router(catalog.router)

__all__ = ["api_router"]
