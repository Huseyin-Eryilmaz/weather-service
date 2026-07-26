"""Shared test fixtures.

Three kinds of test live in this suite. Pure tests (config, data files,
the health endpoint with fakes) need nothing external. Endpoint tests
need a real Postgres, because the upserts under test are a Postgres
feature. Security tests additionally need Redis, for rate limiting and
caching. The database and Redis fixtures skip cleanly when their service
is unreachable, so `pytest` still runs everywhere.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from weather.api.main import create_app
from weather.core.config import Settings, get_settings
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


def _test_redis_url() -> str:
    return os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/0")


async def _make_api_client(settings: Settings) -> AsyncIterator[AsyncClient]:
    """A client over a freshly-migrated DB, built with the given settings.

    The settings are passed to `create_app`, which stashes them where the
    lifespan and the auth/rate-limit/cache code all read from — so a test
    that turns auth on or the cache off actually gets that behaviour.
    Redis is flushed before and after, so no cached value or rate-limit
    window leaks between tests.
    """
    os.environ["DATABASE_URL"] = _test_database_url()
    os.environ["REDIS_URL"] = _test_redis_url()
    get_settings.cache_clear()

    engine = make_engine(_test_database_url())
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
    except Exception:  # noqa: BLE001
        await engine.dispose()
        pytest.skip("no Postgres reachable for API tests")
    await engine.dispose()

    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=transport, base_url="http://test") as ac,
    ):
        # Flush Redis so no cached value or rate-limit window leaks in from
        # a previous test. If Redis is unreachable the app is fail-open, so
        # a flush failure is not a reason to skip — only the handful of
        # tests that assert on caching or throttling need a live Redis, and
        # they check for it themselves.
        async def _flush() -> None:
            with contextlib.suppress(Exception):
                await app.state.cache.flushdb()

        await _flush()
        try:
            yield ac
        finally:
            await _flush()


def make_test_settings(**overrides) -> Settings:
    """Settings pointed at the test database and Redis, plus any overrides.

    The URLs must live on the settings object, not just the environment,
    because the lifespan builds its engine and cache from these — the
    default `redis://cache:6379` would try to reach the compose hostname
    and fail outside Docker.
    """
    base = {
        "environment": "test",
        "database_url": _test_database_url(),
        "redis_url": _test_redis_url(),
    }
    base.update(overrides)
    return Settings(**base)


@pytest.fixture()
async def api_client() -> AsyncIterator[AsyncClient]:
    """The default endpoint client: auth and rate limiting off, cache off,
    so the general endpoint tests are neither throttled nor served stale
    values. Security tests build their own client with these turned on."""
    settings = make_test_settings(rate_limit_enabled=False, cache_enabled=False)
    async for ac in _make_api_client(settings):
        yield ac


@pytest.fixture()
async def db_session() -> AsyncIterator[AsyncSession]:
    """A session against a real Postgres, with a clean schema each time."""
    from sqlalchemy import text

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
