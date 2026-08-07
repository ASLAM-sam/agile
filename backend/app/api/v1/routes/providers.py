"""Provider monitoring routes.

Read-only views onto the live provider manager, plus one corrective action.
Everything is derived from the running manager rather than stored, so the
dashboard shows the state routing is actually using — not a copy that can drift
from it.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import CurrentUser
from app.core.exceptions import NotFoundError
from app.llm.factory import get_llm_provider
from app.llm.routing import AGENT_TASK_KINDS
from app.schemas.providers import (
    ProviderDashboardResponse,
    ProviderHealthResponse,
    ProviderResetResponse,
)

router = APIRouter(prefix="/providers", tags=["Providers"])


@router.get(
    "",
    response_model=ProviderDashboardResponse,
    status_code=status.HTTP_200_OK,
    summary="Live provider health, routing order and cache statistics",
)
async def get_provider_dashboard(_: CurrentUser) -> ProviderDashboardResponse:
    """Everything the provider monitor needs in a single request."""
    return ProviderDashboardResponse.model_validate(get_llm_provider().stats_snapshot())


@router.get(
    "/health",
    response_model=list[ProviderHealthResponse],
    status_code=status.HTTP_200_OK,
    summary="Per-provider health only",
)
async def list_provider_health(_: CurrentUser) -> list[ProviderHealthResponse]:
    """The provider table on its own, for lighter polling."""
    return [
        ProviderHealthResponse.model_validate(entry)
        for entry in get_llm_provider().health_snapshot()
    ]


@router.get(
    "/routing",
    status_code=status.HTTP_200_OK,
    summary="Which kind of work each agent produces",
)
async def get_routing_map(_: CurrentUser) -> dict[str, str]:
    """The agent-to-task mapping that drives provider preference.

    Exposed so the routing decision is inspectable rather than folded away
    inside the manager.
    """
    return {role.value: task.value for role, task in AGENT_TASK_KINDS.items()}


@router.post(
    "/{provider_key}/reset",
    response_model=ProviderResetResponse,
    status_code=status.HTTP_200_OK,
    summary="Clear a provider's cooldown so it is offered again",
)
async def reset_provider(provider_key: str, _: CurrentUser) -> ProviderResetResponse:
    """Return a cooled-down provider to routing immediately.

    Useful after topping up a quota: without it the provider waits out a
    cooldown that is no longer justified.
    """
    if not get_llm_provider().reset_provider(provider_key):
        raise NotFoundError(f"No provider named {provider_key!r} is configured.")
    return ProviderResetResponse(
        key=provider_key,
        cleared=True,
        message=f"{provider_key} is available for routing again.",
    )
