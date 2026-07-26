"""Shared test fixtures.

Two kinds of test live in this suite. Pure tests (config, data files, the
health endpoint with fakes) need nothing external. Database tests need a
real Postgres, because the whole point of the code under test — upserts
via ON CONFLICT — is a Postgres feature that SQLite cannot stand in for.

The database fixtures therefore connect to a real server (the one CI
starts as a service container, or a local one) and are skipped cleanly
when none is reachable, so `pytest` still runs everywhere.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from weather.api.main import create_app
from weather.core.config import Settings
from weather.db.base import Base, make_engine, make_session_factory


@pytest.fixture()
def settings() -> Settings:
    return Settings(environment="test", debug=True)


@pytest.fixture()
async def client(settings: Settings) -> AsyncIterator[AsyncClient]:
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _test_database_url() -> str:
    return os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://weather:weather@localhost:5432/weather_test",
    )


@pytest.fixture()
async def db_session() -> AsyncIterator[AsyncSession]:
    """A session against a real Postgres, with a clean schema each time.

    The tables are dropped and recreated per test, so tests never see one
    another's rows. Slower than a shared schema, but the isolation is
    worth it for a suite this size, and it removes an entire class of
    order-dependent flakes.
    """
    engine = make_engine(_test_database_url())
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        await engine.dispose()
        pytest.skip("no Postgres reachable for database tests")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    factory = make_session_factory(engine)
    async with factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
