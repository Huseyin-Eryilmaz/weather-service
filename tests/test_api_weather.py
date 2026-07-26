"""Weather endpoints, over HTTP against a real database.

These seed data directly through the repository, then read it back
through the API — so they test the query layer, the pagination and the
serialisation together, the way a caller would exercise them.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from weather.db.base import make_engine, make_session_factory
from weather.db.repository import (
    upsert_forecast,
    upsert_location,
    upsert_observation,
)

pytestmark = pytest.mark.asyncio


async def _seed(api_client):
    """Insert one location with three observations and two forecasts."""
    engine = make_engine(_db_url())
    factory = make_session_factory(engine)
    async with factory() as s:
        await upsert_location(s, name="Ankara", latitude=39.93, longitude=32.85)
        await s.commit()
        from sqlalchemy import select

        from weather.db.models import Location

        loc = (
            await s.execute(select(Location).where(Location.name == "Ankara"))
        ).scalar_one()
        for hour, temp in enumerate((18.0, 19.0, 20.0)):
            await upsert_observation(
                s,
                location_id=loc.id,
                observed_at=datetime(2026, 7, 25, hour, tzinfo=UTC),
                temperature_c=temp,
            )
        # two forecasts for the same target hour, issued a day apart
        target = datetime(2026, 7, 26, 12, tzinfo=UTC)
        await upsert_forecast(
            s,
            location_id=loc.id,
            issued_at=datetime(2026, 7, 24, tzinfo=UTC),
            target_time=target,
            temperature_c=25.0,
        )
        await upsert_forecast(
            s,
            location_id=loc.id,
            issued_at=datetime(2026, 7, 25, tzinfo=UTC),
            target_time=target,
            temperature_c=23.0,
        )
        await s.commit()
    await engine.dispose()
    return loc.id


def _db_url() -> str:
    import os

    return os.environ["DATABASE_URL"]


async def test_current_returns_the_newest_observation(api_client):
    location_id = await _seed(api_client)
    response = await api_client.get(f"/locations/{location_id}/current")
    assert response.status_code == 200
    assert response.json()["temperature_c"] == 20.0  # the latest hour


async def test_current_is_404_when_there_is_no_data(api_client):
    created = await api_client.post(
        "/locations", json={"name": "Empty", "latitude": 41.0, "longitude": 28.0}
    )
    location_id = created.json()["id"]
    response = await api_client.get(f"/locations/{location_id}/current")
    assert response.status_code == 404


async def test_observations_are_paginated_with_a_total(api_client):
    location_id = await _seed(api_client)
    response = await api_client.get(f"/locations/{location_id}/observations?limit=2")
    body = response.json()
    assert body["total"] == 3  # all that match
    assert len(body["items"]) == 2  # this page
    assert body["limit"] == 2


async def test_observations_come_back_newest_first(api_client):
    location_id = await _seed(api_client)
    response = await api_client.get(f"/locations/{location_id}/observations")
    temps = [item["temperature_c"] for item in response.json()["items"]]
    assert temps == [20.0, 19.0, 18.0]


async def test_a_date_range_filters_observations(api_client):
    location_id = await _seed(api_client)
    response = await api_client.get(
        f"/locations/{location_id}/observations"
        "?start=2026-07-25T01:00:00Z&end=2026-07-25T02:00:00Z"
    )
    assert response.json()["total"] == 2


async def test_forecasts_return_only_the_latest_prediction_by_default(api_client):
    """Two forecasts were made for the same hour; the default view shows
    only the most recently issued one."""
    location_id = await _seed(api_client)
    response = await api_client.get(f"/locations/{location_id}/forecasts")
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["temperature_c"] == 23.0  # the later issue


async def test_forecasts_can_return_the_full_history(api_client):
    location_id = await _seed(api_client)
    response = await api_client.get(
        f"/locations/{location_id}/forecasts?latest_only=false"
    )
    assert response.json()["total"] == 2  # both predictions


async def test_a_limit_over_the_cap_is_rejected(api_client):
    location_id = await _seed(api_client)
    response = await api_client.get(
        f"/locations/{location_id}/observations?limit=99999"
    )
    assert response.status_code == 422  # exceeds MAX_LIMIT


async def test_weather_endpoints_404_for_a_missing_location(api_client):
    response = await api_client.get("/locations/99999/observations")
    assert response.status_code == 404
