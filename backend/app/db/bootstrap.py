"""Schema creation and first-run seeding.

Alembic owns migrations for staging/production. `ensure_schema` exists so a
developer can clone the repository and boot the platform with no migration step;
it is a no-op once the tables exist.
"""

from __future__ import annotations

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import engine, session_scope
from app.models import User  # noqa: F401 - registers all models on the metadata
from app.repositories.user_repository import UserRepository

logger = get_logger(__name__)


async def ensure_schema() -> None:
    """Create any missing tables."""
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    logger.info("database_schema_ready", extra={"tables": len(Base.metadata.tables)})


async def seed_bootstrap_admin() -> None:
    """Create the bootstrap administrator when credentials are configured."""
    if not (settings.bootstrap_admin_email and settings.bootstrap_admin_password):
        return

    async with session_scope() as session:
        users = UserRepository(session)
        if await users.email_exists(settings.bootstrap_admin_email):
            return
        await users.add(
            User(
                email=settings.bootstrap_admin_email.strip().lower(),
                full_name="Aegis Administrator",
                password_hash=hash_password(settings.bootstrap_admin_password),
                is_admin=True,
                is_active=True,
            )
        )
    logger.info("bootstrap_admin_created", extra={"email": settings.bootstrap_admin_email})
