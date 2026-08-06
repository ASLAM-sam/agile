"""Authentication routes."""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import AuthServiceDep, CurrentUser
from app.schemas.auth import (
    AuthenticatedResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UpdateProfileRequest,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=AuthenticatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account",
)
async def register(payload: RegisterRequest, service: AuthServiceDep) -> AuthenticatedResponse:
    user = await service.register(
        email=payload.email, full_name=payload.full_name, password=payload.password
    )
    return AuthenticatedResponse(
        user=UserResponse.model_validate(user), tokens=service.issue_tokens(user)
    )


@router.post(
    "/login",
    response_model=AuthenticatedResponse,
    status_code=status.HTTP_200_OK,
    summary="Exchange credentials for tokens",
)
async def login(payload: LoginRequest, service: AuthServiceDep) -> AuthenticatedResponse:
    user = await service.authenticate(email=payload.email, password=payload.password)
    return AuthenticatedResponse(
        user=UserResponse.model_validate(user), tokens=service.issue_tokens(user)
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Renew an access token",
)
async def refresh(payload: RefreshRequest, service: AuthServiceDep) -> TokenResponse:
    _, tokens = await service.refresh(payload.refresh_token)
    return tokens


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Current authenticated user",
)
async def me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)


@router.patch(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Update the current user's profile",
)
async def update_me(
    payload: UpdateProfileRequest, user: CurrentUser, service: AuthServiceDep
) -> UserResponse:
    updated = await service.update_profile(
        user, full_name=payload.full_name, theme=payload.theme_preference
    )
    return UserResponse.model_validate(updated)
