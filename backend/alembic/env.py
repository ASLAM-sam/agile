"""Alembic migration environment.

Reads the database URL from application settings rather than `alembic.ini`, so
migrations always target the same database the application does and no
credential is committed to the repository.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig
from typing import Any

import sqlalchemy as sa
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.core.config import settings
from app.db.base import Base
from app.models import (  # noqa: F401 - imported so autogenerate sees every table
    AgentExecution,
    Artifact,
    GenerationRun,
    Project,
    RunEvent,
    User,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def render_item(type_: str, obj: Any, autogen_context: Any) -> str | bool:
    """Render `JSONType` columns correctly in generated migrations.

    Left to itself, autogenerate emits
    `sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql')`
    but never adds the `Text` import, so the generated migration raises
    `NameError` the moment it runs. Rendering the variant explicitly drops the
    redundant `astext_type` and sidesteps the problem entirely.

    Returning False for anything else defers to Alembic's default rendering.
    """
    if type_ == "type" and isinstance(obj, sa.JSON):
        autogen_context.imports.add("from sqlalchemy.dialects import postgresql")
        return 'sa.JSON().with_variant(postgresql.JSONB(), "postgresql")'
    return False


def _configure(connection: Connection) -> None:
    """Shared configuration for both online modes."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        render_item=render_item,
        # SQLite cannot ALTER most columns in place; batch mode recreates the
        # table and copies the data, so the same migration runs on both
        # PostgreSQL and the SQLite development fallback.
        render_as_batch=settings.is_sqlite,
    )


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting to a database."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_item=render_item,
        render_as_batch=settings.is_sqlite,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_sync(connection: Connection) -> None:
    _configure(connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Apply migrations against the configured database."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(_run_sync)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
