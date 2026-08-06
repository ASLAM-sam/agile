"""Catalogue routes.

Exposes the registered technology adapters and the agent roster, so the UI is
driven by the registries rather than a duplicated hardcoded list. Registering a
new adapter makes it selectable with no frontend change.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import AdapterRegistryDep, AgentRegistryDep
from app.core.enums import AdapterKind
from app.schemas.generation import (
    AdapterDescriptorResponse,
    AgentDescriptor,
    CatalogueResponse,
)

router = APIRouter(prefix="/catalog", tags=["Catalogue"])


@router.get(
    "",
    response_model=CatalogueResponse,
    status_code=status.HTTP_200_OK,
    summary="Every technology and agent available to the platform",
)
async def get_catalogue(
    adapters: AdapterRegistryDep, agents: AgentRegistryDep
) -> CatalogueResponse:
    catalogue = adapters.catalogue()

    def described(kind: AdapterKind) -> list[AdapterDescriptorResponse]:
        return [
            AdapterDescriptorResponse.model_validate(descriptor.as_dict())
            for descriptor in catalogue[kind.value]
        ]

    return CatalogueResponse(
        frontend=described(AdapterKind.FRONTEND),
        backend=described(AdapterKind.BACKEND),
        database=described(AdapterKind.DATABASE),
        agents=[AgentDescriptor.model_validate(a) for a in agents.describe()],
    )


@router.get(
    "/agents",
    response_model=list[AgentDescriptor],
    status_code=status.HTTP_200_OK,
    summary="The AI engineering team roster",
)
async def get_agents(agents: AgentRegistryDep) -> list[AgentDescriptor]:
    return [AgentDescriptor.model_validate(a) for a in agents.describe()]
