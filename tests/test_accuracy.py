"""Matching forecasts to observations and scoring them, against Postgres.

These build a small but deliberate scenario: forecasts made at different
lead times for the same hours, and observations of what actually happened,
so the horizon breakdown and the error measures can be checked against
values worked out by hand.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from weather.db.accuracy import (
    accuracy_by_horizon,
    accuracy_summary,
    compute_accuracy,
)
from weather.db.models import ForecastAccuracy
from weather.db.repository import (
    upsert_forecast,
    upsert_location,
    upsert_observation,
)

pytestmark = pytest.mark.asyncio

UTC = UTC


async def _location(session) -> int:
    await upsert_location(session, name="Ankara", latitude=39.93, longitude=32.85)
    await session.commit()
    from weather.db.models import Location

    return await session.scalar(select(Location.id))


async def test_a_forecast_with_a_matching_observation_is_scored(db_session):
    location_id = await _location(db_session)
    target = datetime(2026, 7, 26, 12, tzinfo=UTC)

    await upsert_forecast(
        db_session,
        location_id=location_id,
        issued_at=datetime(2026, 7, 25, 12, tzinfo=UTC),  # 24h ahead
        target_time=target,
        temperature_c=25.0,
    )
    await upsert_observation(
        db_session,
        location_id=location_id,
        observed_at=target,
        temperature_c=23.0,  # actual: forecast was 2 too warm
    )
    await db_session.commit()

    scored = await compute_accuracy(db_session)
    assert scored == 1

    row = await db_session.scalar(select(ForecastAccuracy))
    assert row.absolute_error == pytest.approx(2.0)
    assert row.horizon_hours == 24


async def test_a_forecast_without_an_observation_is_not_scored(db_session):
    location_id = await _location(db_session)
    await upsert_forecast(
        db_session,
        location_id=location_id,
        issued_at=datetime(2026, 7, 25, tzinfo=UTC),
        target_time=datetime(2026, 7, 26, 12, tzinfo=UTC),
        temperature_c=25.0,
    )
    await db_session.commit()

    scored = await compute_accuracy(db_session)
    assert scored == 0


async def test_recomputing_does_not_duplicate_scores(db_session):
    """Idempotency again: scoring the same pair twice updates one row."""
    location_id = await _location(db_session)
    target = datetime(2026, 7, 26, 12, tzinfo=UTC)
    await upsert_forecast(
        db_session,
        location_id=location_id,
        issued_at=datetime(2026, 7, 25, 12, tzinfo=UTC),
        target_time=target,
        temperature_c=25.0,
    )
    await upsert_observation(
        db_session, location_id=location_id, observed_at=target, temperature_c=23.0
    )
    await db_session.commit()

    await compute_accuracy(db_session)
    await compute_accuracy(db_session)

    count = await db_session.scalar(select(func.count()).select_from(ForecastAccuracy))
    assert count == 1


async def test_the_summary_aggregates_the_error(db_session):
    location_id = await _location(db_session)
    # three hours, forecasts off by 2, 4, 0
    base = datetime(2026, 7, 26, 12, tzinfo=UTC)
    issue = datetime(2026, 7, 25, 12, tzinfo=UTC)
    for i, (fc, obs) in enumerate([(22.0, 20.0), (24.0, 20.0), (20.0, 20.0)]):
        hour = base + timedelta(hours=i)
        await upsert_forecast(
            db_session,
            location_id=location_id,
            issued_at=issue,
            target_time=hour,
            temperature_c=fc,
        )
        await upsert_observation(
            db_session, location_id=location_id, observed_at=hour, temperature_c=obs
        )
    await db_session.commit()
    await compute_accuracy(db_session)

    stats = await accuracy_summary(db_session, location_id=location_id)
    assert stats.count == 3
    assert stats.mae == pytest.approx((2 + 4 + 0) / 3)
    assert stats.bias == pytest.approx((2 + 4 + 0) / 3)  # all over-forecast


async def test_error_grows_with_horizon(db_session):
    """The headline finding the analysis exists to show: a forecast made
    further ahead misses by more. Two forecasts for the same hour, one made
    6h ahead and accurate, one made 48h ahead and badly off."""
    location_id = await _location(db_session)
    target = datetime(2026, 7, 26, 12, tzinfo=UTC)

    # 6h ahead, off by 1
    await upsert_forecast(
        db_session,
        location_id=location_id,
        issued_at=target - timedelta(hours=6),
        target_time=target,
        temperature_c=21.0,
    )
    # a different target hour, 48h ahead, off by 5
    target2 = datetime(2026, 7, 26, 18, tzinfo=UTC)
    await upsert_forecast(
        db_session,
        location_id=location_id,
        issued_at=target2 - timedelta(hours=48),
        target_time=target2,
        temperature_c=25.0,
    )
    await upsert_observation(
        db_session, location_id=location_id, observed_at=target, temperature_c=20.0
    )
    await upsert_observation(
        db_session, location_id=location_id, observed_at=target2, temperature_c=20.0
    )
    await db_session.commit()
    await compute_accuracy(db_session)

    by_horizon = await accuracy_by_horizon(db_session, location_id=location_id)
    assert by_horizon[6].mae == pytest.approx(1.0)
    assert by_horizon[48].mae == pytest.approx(5.0)
    # the whole point: the longer lead time is less accurate
    assert by_horizon[48].mae > by_horizon[6].mae


async def test_max_horizon_filters_the_summary(db_session):
    location_id = await _location(db_session)
    target = datetime(2026, 7, 26, 12, tzinfo=UTC)
    await upsert_forecast(
        db_session,
        location_id=location_id,
        issued_at=target - timedelta(hours=6),
        target_time=target,
        temperature_c=21.0,  # off by 1, horizon 6
    )
    target2 = datetime(2026, 7, 26, 18, tzinfo=UTC)
    await upsert_forecast(
        db_session,
        location_id=location_id,
        issued_at=target2 - timedelta(hours=72),
        target_time=target2,
        temperature_c=30.0,  # off by 10, horizon 72
    )
    await upsert_observation(
        db_session, location_id=location_id, observed_at=target, temperature_c=20.0
    )
    await upsert_observation(
        db_session, location_id=location_id, observed_at=target2, temperature_c=20.0
    )
    await db_session.commit()
    await compute_accuracy(db_session)

    # only the short-horizon forecast counts
    limited = await accuracy_summary(
        db_session, location_id=location_id, max_horizon=24
    )
    assert limited.count == 1
    assert limited.mae == pytest.approx(1.0)


async def test_no_data_summarises_to_none(db_session):
    location_id = await _location(db_session)
    assert await accuracy_summary(db_session, location_id=location_id) is None
