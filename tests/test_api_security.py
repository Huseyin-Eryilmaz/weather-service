"""Authentication, rate limiting and caching over HTTP.

Each concern builds a client with the relevant setting turned on, since
the default test client keeps them off to avoid throttling the other
suites. All three run against real Postgres and Redis.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tests.conftest import _make_api_client, _test_database_url, make_test_settings
from weather.db.base import make_engine, make_session_factory
from weather.db.repository import upsert_observation

pytestmark = pytest.mark.asyncio


# ----------------------------------------------------------------------
# Authentication
# ----------------------------------------------------------------------
def _auth_settings():
    return make_test_settings(
        api_keys="secret-key",
        rate_limit_enabled=False,
        cache_enabled=False,
    )


async def test_writing_without_a_key_is_rejected():
    async for client in _make_api_client(_auth_settings()):
        response = await client.post(
            "/locations",
            json={"name": "X", "latitude": 40.0, "longitude": 30.0},
        )
        assert response.status_code == 401


async def test_writing_with_a_wrong_key_is_rejected():
    async for client in _make_api_client(_auth_settings()):
        response = await client.post(
            "/locations",
            json={"name": "X", "latitude": 40.0, "longitude": 30.0},
            headers={"X-API-Key": "not-the-key"},
        )
        assert response.status_code == 401


async def test_writing_with_the_right_key_succeeds():
    async for client in _make_api_client(_auth_settings()):
        response = await client.post(
            "/locations",
            json={"name": "Ankara", "latitude": 39.93, "longitude": 32.85},
            headers={"X-API-Key": "secret-key"},
        )
        assert response.status_code == 201


async def test_reading_never_requires_a_key():
    """Auth is asymmetric: reads stay open even when writes are locked."""
    async for client in _make_api_client(_auth_settings()):
        response = await client.get("/locations")
        assert response.status_code == 200


async def test_auth_is_disabled_when_no_keys_are_configured():
    """The local-development default: with no keys set, writes are open."""
    settings = make_test_settings(
        api_keys="",
        rate_limit_enabled=False,
        cache_enabled=False,
    )
    async for client in _make_api_client(settings):
        response = await client.post(
            "/locations",
            json={"name": "Open", "latitude": 40.0, "longitude": 30.0},
        )
        assert response.status_code == 201


# ----------------------------------------------------------------------
# Rate limiting
# ----------------------------------------------------------------------
async def test_requests_over_the_limit_are_throttled():
    settings = make_test_settings(
        rate_limit_enabled=True,
        rate_limit_per_minute=5,
        cache_enabled=False,
    )
    async for client in _make_api_client(settings):
        codes = [(await client.get("/locations")).status_code for _ in range(8)]
        assert codes.count(200) == 5
        assert codes.count(429) == 3


async def test_a_throttled_response_says_when_to_retry():
    settings = make_test_settings(rate_limit_enabled=True, rate_limit_per_minute=1)
    async for client in _make_api_client(settings):
        await client.get("/locations")  # uses the budget
        blocked = await client.get("/locations")
        assert blocked.status_code == 429
        assert "Retry-After" in blocked.headers


# ----------------------------------------------------------------------
# Caching
# ----------------------------------------------------------------------
async def test_current_conditions_are_served_from_cache():
    """After the first call, changing the database does not change the
    response until the cached value expires — proof it is being served
    from Redis, not recomputed."""
    settings = make_test_settings(
        rate_limit_enabled=False,
        cache_enabled=True,
        cache_ttl_seconds=30,
    )
    async for client in _make_api_client(settings):
        created = await client.post(
            "/locations",
            json={"name": "Ankara", "latitude": 39.93, "longitude": 32.85},
        )
        location_id = created.json()["id"]

        url = _test_database_url()
        engine = make_engine(url)
        factory = make_session_factory(engine)
        async with factory() as s:
            await upsert_observation(
                s,
                location_id=location_id,
                observed_at=datetime(2026, 7, 25, 12, tzinfo=UTC),
                temperature_c=20.0,
            )
            await s.commit()
        await engine.dispose()

        first = await client.get(f"/locations/{location_id}/current")
        assert first.json()["temperature_c"] == 20.0

        # Change the underlying value.
        engine = make_engine(url)
        factory = make_session_factory(engine)
        async with factory() as s:
            await upsert_observation(
                s,
                location_id=location_id,
                observed_at=datetime(2026, 7, 25, 12, tzinfo=UTC),
                temperature_c=99.0,
            )
            await s.commit()
        await engine.dispose()

        # Still the cached value, not the new one.
        second = await client.get(f"/locations/{location_id}/current")
        assert second.json()["temperature_c"] == 20.0
