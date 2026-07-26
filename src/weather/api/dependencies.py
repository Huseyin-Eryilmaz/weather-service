"""Dependencies the route handlers ask for.

FastAPI's dependency injection is what keeps handlers thin: a handler
declares it needs a database session, and FastAPI calls this to provide
one, scoped to that single request and closed afterwards. The handler
never opens a connection, never remembers to close it, and never shares
one between requests by accident.

The session factory is built once at startup and stashed on the app, so
this reaches through the request to find it rather than creating an
engine per call.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yields a request-scoped session from the app's factory."""
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        yield session
