"""Authentication and user schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import EmailStr, Field, field_validator

from app.schemas.common import APIModel

_MIN_PASSWORD_LENGTH = 10


class RegisterRequest(APIModel):
    """New account registration."""

    email: EmailStr
    full_name: str = Field(min_length=2, max_length=200)
    password: str = Field(min_length=_MIN_PASSWORD_LENGTH, max_length=72)

    @field_validator("password")
    @classmethod
    def _strength(cls, value: str) -> str:
        """Require a mix of character classes.

        Length carries most of the entropy, so the bar is length-first with a
        light composition check rather than a rule set users work around.
        """
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 bytes.")
        if value.isalpha() or value.isdigit():
            raise ValueError("Password must combine letters with numbers or symbols.")
        if value.lower() in {"password12", "changeme123", "letmein123"}:
            raise ValueError("Password is too common.")
        return value

    @field_validator("full_name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Name must not be blank.")
        return cleaned


class LoginRequest(APIModel):
    """Credential exchange."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class RefreshRequest(APIModel):
    """Access token renewal."""

    refresh_token: str = Field(min_length=1)


class TokenResponse(APIModel):
    """Issued token pair."""

    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds.")


class UserResponse(APIModel):
    """A user account, never including the password hash."""

    id: str
    email: str
    full_name: str
    is_active: bool
    is_admin: bool
    theme_preference: str
    created_at: datetime


class UpdateProfileRequest(APIModel):
    """Editable profile fields."""

    full_name: str | None = Field(default=None, min_length=2, max_length=200)
    theme_preference: Literal["dark", "light", "system"] | None = None


class AuthenticatedResponse(APIModel):
    """Tokens plus the authenticated user, returned on login and registration."""

    user: UserResponse
    tokens: TokenResponse
