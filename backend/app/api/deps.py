"""FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.registry import AdapterRegistry, get_registry
from app.agents.registry import AgentRegistry, get_agent_registry
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.core.security import decode_token
from app.db.session import get_session
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService
from app.services.generation_service import GenerationService
from app.services.orchestration_service import RunOrchestrator, get_orchestrator
from app.services.project_service import ProjectService

# `auto_error=False` so a missing header raises our AuthenticationError with a
# consistent body, rather than Starlette's default 403.
_bearer = HTTPBearer(auto_error=False, description="JWT access token")

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    """Resolve the authenticated user from the bearer token."""
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Authentication is required for this endpoint.")

    claims = decode_token(credentials.credentials, expected_type="access")
    user = await UserRepository(session).get(str(claims["sub"]))

    if user is None:
        raise AuthenticationError("The account for this token no longer exists.")
    if not user.is_active:
        raise AuthenticationError("This account has been deactivated.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_admin_user(user: CurrentUser) -> User:
    """Require administrator privileges."""
    if not user.is_admin:
        raise AuthorizationError("This endpoint requires administrator privileges.")
    return user


AdminUser = Annotated[User, Depends(get_admin_user)]


def get_auth_service(session: SessionDep) -> AuthService:
    return AuthService(session)


def get_project_service(session: SessionDep) -> ProjectService:
    return ProjectService(session)


def get_generation_service(session: SessionDep) -> GenerationService:
    return GenerationService(session)


def get_adapter_registry() -> AdapterRegistry:
    return get_registry()


def get_agents() -> AgentRegistry:
    return get_agent_registry()


def get_run_orchestrator() -> RunOrchestrator:
    return get_orchestrator()


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]
GenerationServiceDep = Annotated[GenerationService, Depends(get_generation_service)]
AdapterRegistryDep = Annotated[AdapterRegistry, Depends(get_adapter_registry)]
AgentRegistryDep = Annotated[AgentRegistry, Depends(get_agents)]
OrchestratorDep = Annotated[RunOrchestrator, Depends(get_run_orchestrator)]
