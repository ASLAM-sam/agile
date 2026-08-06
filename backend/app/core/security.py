"""Password hashing and JSON Web Token issuance/verification."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import bcrypt
import jwt

from app.core.config import settings
from app.core.exceptions import AuthenticationError

TokenType = Literal["access", "refresh"]

_MAX_PASSWORD_BYTES = 72  # bcrypt truncates beyond this; reject instead of silently cutting.


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    encoded = password.encode("utf-8")
    if len(encoded) > _MAX_PASSWORD_BYTES:
        raise ValueError("Password exceeds the maximum supported length of 72 bytes.")
    return bcrypt.hashpw(encoded, bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time verification of a password against its hash."""
    encoded = password.encode("utf-8")
    if len(encoded) > _MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(encoded, password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_token(
    subject: str,
    token_type: TokenType,
    *,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Mint a signed JWT for the given subject."""
    now = datetime.now(UTC)
    ttl = (
        timedelta(minutes=settings.access_token_ttl_minutes)
        if token_type == "access"
        else timedelta(days=settings.refresh_token_ttl_days)
    )
    claims: dict[str, Any] = {
        "sub": subject,
        "typ": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
        "jti": uuid.uuid4().hex,
        "iss": settings.app_name,
        **(extra_claims or {}),
    }
    return jwt.encode(claims, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str, *, expected_type: TokenType) -> dict[str, Any]:
    """Decode and validate a JWT, enforcing its declared type."""
    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.app_name,
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError("Token is invalid.") from exc

    if claims.get("typ") != expected_type:
        raise AuthenticationError(f"Expected a {expected_type} token.")
    if not claims.get("sub"):
        raise AuthenticationError("Token is missing a subject claim.")
    return claims


def token_expiry_seconds(token_type: TokenType) -> int:
    """Lifetime of a freshly minted token, in seconds."""
    if token_type == "access":
        return settings.access_token_ttl_minutes * 60
    return settings.refresh_token_ttl_days * 24 * 60 * 60
