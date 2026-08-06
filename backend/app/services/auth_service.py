"""Authentication service."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError, ConflictError, NotFoundError
from app.core.logging import get_logger
from app.core.security import (
    create_token,
    decode_token,
    hash_password,
    token_expiry_seconds,
    verify_password,
)
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import TokenResponse

logger = get_logger(__name__)


class AuthService:
    """Registration, login and token lifecycle."""

    def __init__(self, session: AsyncSession) -> None:
        self._users = UserRepository(session)

    async def register(self, *, email: str, full_name: str, password: str) -> User:
        """Create an account. Fails if the email is already registered."""
        normalised = email.strip().lower()
        if await self._users.email_exists(normalised):
            raise ConflictError("An account with this email address already exists.")

        user = await self._users.add(
            User(
                email=normalised,
                full_name=full_name.strip(),
                password_hash=hash_password(password),
                is_active=True,
            )
        )
        logger.info("user_registered", extra={"user_id": user.id})
        return user

    async def authenticate(self, *, email: str, password: str) -> User:
        """Verify credentials and return the user."""
        user = await self._users.get_by_email(email)

        # Hash even when the user is absent, so response time does not reveal
        # whether an address is registered.
        password_hash = user.password_hash if user else _DUMMY_HASH
        password_ok = verify_password(password, password_hash)

        if user is None or not password_ok:
            raise AuthenticationError("Incorrect email address or password.")
        if not user.is_active:
            raise AuthenticationError("This account has been deactivated.")

        return user

    async def refresh(self, refresh_token: str) -> tuple[User, TokenResponse]:
        """Exchange a refresh token for a new token pair."""
        claims = decode_token(refresh_token, expected_type="refresh")
        user = await self._users.get(str(claims["sub"]))
        if user is None:
            raise AuthenticationError("The account for this token no longer exists.")
        if not user.is_active:
            raise AuthenticationError("This account has been deactivated.")
        return user, self.issue_tokens(user)

    async def get_user(self, user_id: str) -> User:
        user = await self._users.get(user_id)
        if user is None:
            raise NotFoundError("User not found.")
        return user

    async def update_profile(
        self, user: User, *, full_name: str | None = None, theme: str | None = None
    ) -> User:
        if full_name is not None:
            user.full_name = full_name.strip()
        if theme is not None:
            user.theme_preference = theme
        await self._users.flush()
        return user

    @staticmethod
    def issue_tokens(user: User) -> TokenResponse:
        """Mint an access/refresh token pair for a user."""
        return TokenResponse(
            access_token=create_token(
                user.id, "access", extra_claims={"email": user.email, "admin": user.is_admin}
            ),
            refresh_token=create_token(user.id, "refresh"),
            expires_in=token_expiry_seconds("access"),
        )


#: A real bcrypt hash of a value no user can supply, used to equalise the cost
#: of the "unknown email" path against the "wrong password" path.
_DUMMY_HASH = "$2b$12$C6UzMDM.H6dfI/f/IKcEe.OcaZ0hLKQ8xhV0lQxJhVEXcaqR8oJoO"
