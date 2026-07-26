"""Idempotent writes against a real Postgres.

These exercise the one thing the repository exists for: writing the same
data twice must not double it. Each test drops and recreates the schema
(via the db_session fixture), so it starts from empty.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from weather.db.models import Forecast, Location, Observation
from weather.db.repository import (
    upsert_forecast,
    upsert_location,
    upsert_observation,
)

pytestmark = pytest.mark.asyncio


async def _make_location(session) -> int:
    await upsert_location(session, name="Testville", latitude=40.0, longitude=30.0)
    await session.commit()
    result = await session.execute(select(Location.id))
    return result.scalars().first()


async def test_a_location_is_inserted_once(db_session):
    await upsert_location(db_session, name="Ankara", latitude=39.93, longitude=32.85)
    await db_session.commit()
    count = await db_session.scalar(select(func.count()).select_from(Location))
    assert count == 1


async def test_re_inserting_a_location_does_not_duplicate_it(db_session):
    for _ in range(3):
        await upsert_location(
            db_session, name="Ankara", latitude=39.93, longitude=32.85
        )
        await db_session.commit()
    count = await db_session.scalar(select(func.count()).select_from(Location))
    assert count == 1


async def test_re_inserting_a_location_keeps_the_original_name(db_session):
    """DO NOTHING, not DO UPDATE: a hand-corrected name must survive a
    re-seed."""
    await upsert_location(db_session, name="Original", latitude=40.0, longitude=30.0)
    await db_session.commit()
    await upsert_location(db_session, name="Overwritten", latitude=40.0, longitude=30.0)
    await db_session.commit()
    name = await db_session.scalar(select(Location.name))
    assert name == "Original"


async def test_an_observation_is_written_once_per_hour(db_session):
    location_id = await _make_location(db_session)
    when = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)
    for _ in range(3):
        await upsert_observation(
            db_session,
            location_id=location_id,
            observed_at=when,
            temperature_c=20.0,
        )
        await db_session.commit()
    count = await db_session.scalar(select(func.count()).select_from(Observation))
    assert count == 1


async def test_re_observing_the_same_hour_updates_the_value(db_session):
    """A later fetch may carry a corrected reading; the row should reflect
    the most recent write."""
    location_id = await _make_location(db_session)
    when = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)
    for temp in (20.0, 21.5, 19.8):
        await upsert_observation(
            db_session, location_id=location_id, observed_at=when, temperature_c=temp
        )
        await db_session.commit()
    final = await db_session.scalar(select(Observation.temperature_c))
    assert final == 19.8


async def test_two_different_hours_are_two_rows(db_session):
    location_id = await _make_location(db_session)
    for hour in (10, 11):
        await upsert_observation(
            db_session,
            location_id=location_id,
            observed_at=datetime(2026, 7, 25, hour, 0, tzinfo=UTC),
            temperature_c=20.0,
        )
    await db_session.commit()
    count = await db_session.scalar(select(func.count()).select_from(Observation))
    assert count == 2


async def test_a_forecast_is_keyed_by_issue_and_target(db_session):
    """The same target hour predicted at two different times is two
    forecasts, not one — this is the distinction accuracy analysis needs."""
    location_id = await _make_location(db_session)
    target = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)
    issued_early = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)
    issued_late = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)

    await upsert_forecast(
        db_session,
        location_id=location_id,
        issued_at=issued_early,
        target_time=target,
        temperature_c=25.0,
    )
    await upsert_forecast(
        db_session,
        location_id=location_id,
        issued_at=issued_late,
        target_time=target,
        temperature_c=23.0,
    )
    await db_session.commit()
    count = await db_session.scalar(select(func.count()).select_from(Forecast))
    assert count == 2


async def test_re_issuing_the_same_forecast_updates_it(db_session):
    location_id = await _make_location(db_session)
    target = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)
    issued = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)
    for temp in (25.0, 24.0):
        await upsert_forecast(
            db_session,
            location_id=location_id,
            issued_at=issued,
            target_time=target,
            temperature_c=temp,
        )
        await db_session.commit()
    count = await db_session.scalar(select(func.count()).select_from(Forecast))
    final = await db_session.scalar(select(Forecast.temperature_c))
    assert count == 1
    assert final == 24.0
