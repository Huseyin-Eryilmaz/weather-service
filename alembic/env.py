"""Alembic's runtime entry point.

Two things make this file project-specific. First, the database URL
comes from the application settings, not from alembic.ini — one source
of truth. Second, `target_metadata` is wired to the models' Base, which
is what lets `alembic revision --autogenerate` compare the models to the
live database and write the difference for you.

The async engine needs a small dance: Alembic's migration step is
synchronous, so an async connection is run through `run_sync`.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.pool import NullPool

from weather.core.config import get_settings
from weather.db import models  # noqa: F401 - imported so tables register
from weather.db.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    return str(get_settings().database_url)


def run_migrations_offline() -> None:
    """Emit SQL to a script without a live connection."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,  # notice column type changes, not just names
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Apply migrations against the live database."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _database_url()

    engine = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=NullPool,  # migrations are one-shot; no pool needed
    )
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
