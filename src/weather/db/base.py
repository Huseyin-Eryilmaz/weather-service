"""Database plumbing: the base class, the engine, and sessions.

SQLAlchemy has two halves. The *core* speaks SQL directly; the *ORM* maps
Python classes to tables so a row becomes an object and a query returns
objects instead of tuples. This project uses the ORM, and everything ORM
starts from one shared `Base` class — every model inherits from it, and
that is how SQLAlchemy knows which tables exist.

Everything here is async. The API handles many requests at once, and a
request that is waiting on the database should hand the CPU to another
request rather than block. `asyncpg` is the driver that makes Postgres
talk asynchronously; `AsyncSession` is the ORM's async unit of work.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """The parent of every model. Its metadata is the table registry."""


def make_engine(database_url: str, *, echo: bool = False) -> AsyncEngine:
    """Builds an async engine — the pool of connections to the database.

    An engine is created once per process and shared. It is not a single
    connection but a pool of them, handed out as needed and returned when
    done, because opening a connection is slow and reusing one is fast.
    """
    return create_async_engine(
        database_url,
        echo=echo,
        pool_pre_ping=True,  # check a connection is alive before using it
    )


def make_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """A factory that produces sessions bound to this engine.

    `expire_on_commit=False` is set so objects stay usable after the
    session commits. The default would expire them, and the next access
    would trigger a fresh query — awkward in async code, where that lazy
    reload can happen after the session has already closed.
    """
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Yields a session and guarantees it is closed.

    Used as a FastAPI dependency: the session lives for exactly one
    request, commits or rolls back, and is returned to the pool. The
    `async with` is what makes "always closed, even on error" true.
    """
    async with factory() as session:
        yield session
