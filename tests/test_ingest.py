"""Ingest: fetch through a mock client, store in a real database.

These tie the two halves together. The HTTP side is mocked (deterministic,
no network), the database side is real Postgres (the upsert behaviour is
the point). `now` is injected so "past" and "future" are fixed, not tied
to when the test happens to run.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select

from weather.clients.ingest import ingest_forecasts, ingest_observations
from weather.clients.open_meteo import OpenMeteoClient
from weather.db.models import Forecast, Location, Observation
from weather.db.repository import upsert_location

pytestmark = pytest.mark.asyncio

FIXTURE = Path(__file__).parent / "fixtures" / "forecast_ankara.json"
# The fixture's hours are 2026-07-25 00:00..03:00 UTC.
FIXTURE_HOURS = ["00:00", "01:00", "02:00", "03:00"]


def _client_returning_fixture() -> OpenMeteoClient:
    payload = json.loads(FIXTURE.read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OpenMeteoClient(
        http,
        forecast_url="https://example.test/forecast",
        archive_url="https://example.test/archive",
    )


async def _location(session) -> int:
    await upsert_location(session, name="Ankara", latitude=39.94, longitude=32.86)
    await session.commit()
    return await session.scalar(select(Location.id))


async def test_past_hours_are_stored_as_observations(db_session):
    location_id = await _location(db_session)
    client = _client_returning_fixture()
    # Pretend "now" is after all four fixture hours.
    now = datetime(2026, 7, 25, 4, 0, tzinfo=UTC)

    stored = await ingest_observations(
        db_session,
        client,
        location_id=location_id,
        latitude=39.94,
        longitude=32.86,
        now=now,
    )

    assert stored == 4
    count = await db_session.scalar(select(func.count()).select_from(Observation))
    assert count == 4


async def test_only_hours_up_to_now_become_observations(db_session):
    """The future hours in the response are not observations yet."""
    location_id = await _location(db_session)
    client = _client_returning_fixture()
    # "now" falls between the 2nd and 3rd fixture hour.
    now = datetime(2026, 7, 25, 1, 30, tzinfo=UTC)

    stored = await ingest_observations(
        db_session,
        client,
        location_id=location_id,
        latitude=39.94,
        longitude=32.86,
        now=now,
    )

    assert stored == 2  # 00:00 and 01:00 only


async def test_future_hours_are_stored_as_forecasts(db_session):
    location_id = await _location(db_session)
    client = _client_returning_fixture()
    # "now" before all fixture hours: all four are in the future.
    issued = datetime(2026, 7, 24, 23, 0, tzinfo=UTC)

    stored = await ingest_forecasts(
        db_session,
        client,
        location_id=location_id,
        latitude=39.94,
        longitude=32.86,
        issued_at=issued,
    )

    assert stored == 4
    count = await db_session.scalar(select(func.count()).select_from(Forecast))
    assert count == 4


async def test_a_forecast_records_when_it_was_issued(db_session):
    location_id = await _location(db_session)
    client = _client_returning_fixture()
    issued = datetime(2026, 7, 24, 23, 0, tzinfo=UTC)

    await ingest_forecasts(
        db_session,
        client,
        location_id=location_id,
        latitude=39.94,
        longitude=32.86,
        issued_at=issued,
    )

    stored_issue = await db_session.scalar(select(Forecast.issued_at))
    assert stored_issue.replace(tzinfo=UTC) == issued


async def test_re_ingesting_the_same_hours_does_not_duplicate(db_session):
    """The whole reason for upserts: running collection twice is safe."""
    location_id = await _location(db_session)
    client = _client_returning_fixture()
    now = datetime(2026, 7, 25, 4, 0, tzinfo=UTC)

    for _ in range(3):
        await ingest_observations(
            db_session,
            client,
            location_id=location_id,
            latitude=39.94,
            longitude=32.86,
            now=now,
        )

    count = await db_session.scalar(select(func.count()).select_from(Observation))
    assert count == 4  # not 12
