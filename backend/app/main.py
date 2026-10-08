"""Aegis AI application entrypoint."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.api.deps import CurrentUser, GenerationServiceDep, SessionDep
from app.api.v1.router import api_router
from app.api.v1.routes.artifacts import download_package
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.db.bootstrap import ensure_schema, seed_bootstrap_admin
from app.db.session import dispose_engine
from app.llm.factory import close_llm_provider
from app.services.orchestration_service import get_orchestrator

configure_logging()
logger = get_logger(__name__)

DESCRIPTION = """
**Aegis AI** — a multi-agent AI software engineering platform.

Submit a software idea in plain language. A team of eleven specialised AI
engineers analyses the requirements, decides which capabilities the project
actually needs, designs the architecture and schema, writes the frontend and
backend, reviews and improves its own output, documents everything, and returns
a downloadable, production-oriented starter project.

### Workflow

`Idea → Requirement analysis → Technology recommendation → Stack review →
Workflow engine → Dynamic agent execution → Code review → Improvement →
Packaging → Report → Download`

Agents that a project does not need never run. A portfolio site gets no database
engineer; a banking system gets the whole team.
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start-up and shut-down sequence."""
    logger.info(
        "application_starting",
        extra={
            "version": settings.app_version,
            "environment": settings.environment,
            "llm_model": settings.active_model,
            "llm_configured": settings.llm_configured,
        },
    )

    await ensure_schema()
    await seed_bootstrap_admin()

    if not settings.llm_configured:
        logger.warning(
            "llm_api_key_missing",
            extra={
                "impact": (
                    "Generation is disabled until "
                    f"{settings.active_api_key_variable} is set."
                ),
            },
        )

    yield

    logger.info("application_stopping")
    await get_orchestrator().shutdown()
    await close_llm_provider()
    await dispose_engine()


def create_app() -> FastAPI:
    """Build and configure the ASGI application."""
    app = FastAPI(
        title=settings.app_name,
        description=DESCRIPTION,
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        contact={"name": "Aegis AI"},
        license_info={"name": "Proprietary"},
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition", "X-Process-Time"],
    )

    @app.middleware("http")
    async def add_process_time(request: Request, call_next):  # type: ignore[no-untyped-def]
        """Record server-side latency and log slow requests."""
        started = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - started
        response.headers["X-Process-Time"] = f"{elapsed:.4f}"

        if elapsed > 5.0 and not request.url.path.endswith("/stream"):
            logger.warning(
                "slow_request",
                extra={
                    "path": request.url.path,
                    "method": request.method,
                    "seconds": round(elapsed, 2),
                },
            )
        return response

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get(
        "/api/generations/{generation_id}/artifact",
        response_class=FileResponse,
        include_in_schema=True,
        tags=["Artifacts"],
        summary="Download artifact by generation ID",
    )
    @app.get(
        "/api/runs/{generation_id}/artifact",
        response_class=FileResponse,
        include_in_schema=False,
    )
    @app.get(
        "/api/runs/{generation_id}/download",
        response_class=FileResponse,
        include_in_schema=False,
    )
    async def get_generation_artifact(
        generation_id: str,
        user: CurrentUser,
        generation: GenerationServiceDep,
        session: SessionDep,
    ) -> FileResponse:
        return await download_package(
            run_id=generation_id, user=user, generation=generation, session=session
        )

    @app.get("/", include_in_schema=False)
    async def root() -> JSONResponse:
        return JSONResponse(
            {
                "name": settings.app_name,
                "version": settings.app_version,
                "tagline": (
                    "From idea to production-ready starter project — powered by an "
                    "autonomous AI engineering team."
                ),
                "documentation": "/docs",
                "api": settings.api_prefix,
                "health": f"{settings.api_prefix}/health",
            }
        )

    return app


app = create_app()
