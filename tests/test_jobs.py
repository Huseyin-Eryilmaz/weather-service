"""The collection jobs, run against a real database.

The point of these jobs is fault isolation: a run over many locations
where some fetches fail must still store the successful ones. So the key
tests use a client that fails for specific coordinates and check that the
survivors landed and the failures were counted, not fatal.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select

from weather.clients.open_meteo import OpenMeteoClient
from weather.db.base import make_session_factory
from weather.db.models import Location, Observation
from weather.db.repository import upsert_location
from weather.workers.jobs import collect_forecasts, collect_observations

pytestmark = pytest.mark.asyncio

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "forecast_ankara.json").read_text()
)
# Fixture hours are 2026-07-25 00:00..03:00; pick a "now" after them.
NOW = datetime(2026, 7, 25, 6, 0, tzinfo=UTC)


async def _seed_three(session) -> None:
    await upsert_location(session, name="Ankara", latitude=39.94, longitude=32.86)
    await upsert_location(session, name="Izmir", latitude=38.42, longitude=27.14)
    await upsert_location(session, name="Van", latitude=38.49, longitude=43.41)
    await session.commit()


def _ok_client() -> OpenMeteoClient:
    def handler(request):
        return httpx.Response(200, json=FIXTURE)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OpenMeteoClient(
        http,
        forecast_url="https://example.test/forecast",
        archive_url="https://example.test/archive",
    )


def _client_failing_for(bad_latitude: float) -> OpenMeteoClient:
    """A client that returns a 400 for one location and data for the rest."""

    def handler(request):
        if request.url.params.get("latitude") == str(bad_latitude):
            return httpx.Response(400, text="bad coordinate")
        return httpx.Response(200, json=FIXTURE)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OpenMeteoClient(
        http,
        forecast_url="https://example.test/forecast",
        archive_url="https://example.test/archive",
        max_retries=0,
    )


async def test_a_clean_run_stores_every_location(db_session):
    await _seed_three(db_session)
    factory = make_session_factory(db_session.bind)

    result = await collect_observations(factory, _ok_client(), now=NOW)

    assert result.locations == 3
    assert result.succeeded == 3
    assert result.failed == 0
    assert result.ok


async def test_one_failing_location_does_not_sink_the_others(db_session):
    """The heart of the phase: Izmir's fetch fails, Ankara and Van still
    get stored."""
    await _seed_three(db_session)
    factory = make_session_factory(db_session.bind)

    client = _client_failing_for(38.42)  # Izmir
    result = await collect_observations(factory, client, now=NOW)

    assert result.succeeded == 2
    assert result.failed == 1
    assert result.ok  # a run with survivors is still a good run

    # The survivors' rows really are in the database.
    stored = await db_session.scalar(select(func.count()).select_from(Observation))
    assert stored == 8  # 2 locations x 4 hours


async def test_a_run_where_everything_fails_is_not_ok(db_session):
    await _seed_three(db_session)
    factory = make_session_factory(db_session.bind)

    def handler(request):
        return httpx.Response(400, text="nope")

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = OpenMeteoClient(
        http,
        forecast_url="https://example.test/forecast",
        archive_url="https://example.test/archive",
        max_retries=0,
    )
    result = await collect_observations(factory, client, now=NOW)

    assert result.succeeded == 0
    assert result.failed == 3
    assert not result.ok  # zero successes signals something systemic


async def test_inactive_locations_are_skipped(db_session):
    await _seed_three(db_session)
    # Deactivate Van.
    van = await db_session.scalar(select(Location).where(Location.name == "Van"))
    van.is_active = False
    await db_session.commit()
    factory = make_session_factory(db_session.bind)

    result = await collect_observations(factory, _ok_client(), now=NOW)
    assert result.locations == 2


async def test_forecasts_run_over_every_location(db_session):
    await _seed_three(db_session)
    factory = make_session_factory(db_session.bind)
    issued = datetime(2026, 7, 24, 23, 0, tzinfo=UTC)

    result = await collect_forecasts(factory, _ok_client(), issued_at=issued)
    assert result.succeeded == 3
    assert result.rows == 12  # 3 locations x 4 future hours
