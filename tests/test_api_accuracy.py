"""Accuracy endpoints over HTTP, backed by scored data in Postgres."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tests.conftest import _test_database_url
from weather.db.accuracy import compute_accuracy
from weather.db.base import make_engine, make_session_factory
from weather.db.repository import (
    upsert_forecast,
    upsert_location,
    upsert_observation,
)

pytestmark = pytest.mark.asyncio
UTC = UTC


async def _seed_scored(api_client) -> int:
    """Create a location with two forecasts (6h and 48h ahead) scored."""
    engine = make_engine(_test_database_url())
    factory = make_session_factory(engine)
    async with factory() as s:
        await upsert_location(s, name="Ankara", latitude=39.93, longitude=32.85)
        await s.commit()
        from weather.db.models import Location

        loc_id = await s.scalar(__import__("sqlalchemy").select(Location.id))
        t1 = datetime(2026, 7, 26, 12, tzinfo=UTC)
        t2 = datetime(2026, 7, 26, 18, tzinfo=UTC)
        await upsert_forecast(
            s,
            location_id=loc_id,
            issued_at=t1 - timedelta(hours=6),
            target_time=t1,
            temperature_c=21.0,
        )
        await upsert_forecast(
            s,
            location_id=loc_id,
            issued_at=t2 - timedelta(hours=48),
            target_time=t2,
            temperature_c=25.0,
        )
        await upsert_observation(
            s, location_id=loc_id, observed_at=t1, temperature_c=20.0
        )
        await upsert_observation(
            s, location_id=loc_id, observed_at=t2, temperature_c=20.0
        )
        await s.commit()
        await compute_accuracy(s, location_id=loc_id)
    await engine.dispose()
    return loc_id


async def test_summary_reports_overall_error(api_client):
    loc_id = await _seed_scored(api_client)
    response = await api_client.get(f"/accuracy/summary?location_id={loc_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["metric"] == "temperature"
    assert body["stats"]["count"] == 2
    # errors 1 and 5 -> MAE 3
    assert body["stats"]["mae"] == 3.0


async def test_summary_is_empty_when_nothing_is_scored(api_client):
    created = await api_client.post(
        "/locations", json={"name": "Empty", "latitude": 41.0, "longitude": 28.0}
    )
    loc_id = created.json()["id"]
    response = await api_client.get(f"/accuracy/summary?location_id={loc_id}")
    assert response.status_code == 200
    assert response.json()["stats"] is None


async def test_by_horizon_shows_error_growing_with_lead_time(api_client):
    loc_id = await _seed_scored(api_client)
    response = await api_client.get(f"/accuracy/by-horizon?location_id={loc_id}")
    assert response.status_code == 200
    buckets = {b["horizon_hours"]: b["stats"] for b in response.json()["buckets"]}
    assert buckets[6]["mae"] == 1.0
    assert buckets[48]["mae"] == 5.0
    assert buckets[48]["mae"] > buckets[6]["mae"]


async def test_max_horizon_narrows_the_summary(api_client):
    loc_id = await _seed_scored(api_client)
    response = await api_client.get(
        f"/accuracy/summary?location_id={loc_id}&max_horizon=24"
    )
    body = response.json()
    assert body["stats"]["count"] == 1  # only the 6h forecast
    assert body["stats"]["mae"] == 1.0
