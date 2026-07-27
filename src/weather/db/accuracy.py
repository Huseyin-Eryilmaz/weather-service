"""Turning stored forecasts and observations into accuracy records.

This is the join the whole project was built toward. A forecast said the
temperature at a given hour would be X; an observation later recorded that
it was actually Y. Where both exist for the same location, metric and
hour, the pair can be scored — and the forecast's horizon (how far ahead
it was made) travels with the score, because that is the axis the analysis
pivots on.

The work happens in SQL rather than by pulling everything into Python: the
number of forecast rows grows without bound, and matching them to
observations is exactly what a relational join is for. The computed errors
are written to `forecast_accuracy` with an upsert, so recomputing is
idempotent — the same pair scored twice updates one row, it does not
accumulate.

Only temperature is scored for now. It is the metric with a clean
continuous value and an obvious error; precipitation and wind can follow
the same shape later.
"""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from weather.core.metrics import summarise
from weather.db.models import Forecast, ForecastAccuracy, Observation

log = structlog.get_logger()

# The metrics eligible for scoring, mapped to the model columns holding
# them on both the forecast and observation side.
_SCORABLE = {
    "temperature": "temperature_c",
}


async def compute_accuracy(
    session: AsyncSession, *, location_id: int | None = None
) -> int:
    """Scores every forecast that now has a matching observation.

    Joins forecasts to observations on location and hour, computes the
    absolute error and horizon for each, and upserts a row into
    forecast_accuracy. Returns how many pairs were scored. An optional
    location_id restricts the work to one place.
    """
    scored = 0
    for metric, column in _SCORABLE.items():
        forecast_value = getattr(Forecast, column)
        observed_value = getattr(Observation, column)

        # Match a forecast to the observation for the same location and the
        # same hour. Rows where either side is NULL are excluded by the
        # join conditions, so only genuinely comparable pairs survive.
        query = (
            select(
                Forecast.location_id,
                Forecast.target_time,
                Forecast.issued_at,
                forecast_value.label("forecast"),
                observed_value.label("observed"),
            )
            .join(
                Observation,
                (Observation.location_id == Forecast.location_id)
                & (Observation.observed_at == Forecast.target_time),
            )
            .where(
                forecast_value.is_not(None),
                observed_value.is_not(None),
            )
        )
        if location_id is not None:
            query = query.where(Forecast.location_id == location_id)

        rows = (await session.execute(query)).all()

        for row in rows:
            horizon = _horizon_hours(row.issued_at, row.target_time)
            error = abs(row.forecast - row.observed)
            await _upsert_accuracy(
                session,
                location_id=row.location_id,
                target_time=row.target_time,
                metric=metric,
                horizon_hours=horizon,
                forecast_value=row.forecast,
                observed_value=row.observed,
                absolute_error=error,
            )
            scored += 1

    await session.commit()
    log.info("accuracy_computed", pairs=scored, location_id=location_id)
    return scored


def _horizon_hours(issued_at, target_time) -> int:
    """Whole hours between issue and target, clamped at zero."""
    delta = (target_time - issued_at).total_seconds() / 3600
    return max(int(delta), 0)


async def _upsert_accuracy(
    session: AsyncSession,
    *,
    location_id: int,
    target_time,
    metric: str,
    horizon_hours: int,
    forecast_value: float,
    observed_value: float,
    absolute_error: float,
) -> None:
    statement = pg_insert(ForecastAccuracy).values(
        location_id=location_id,
        target_time=target_time,
        metric=metric,
        horizon_hours=horizon_hours,
        forecast_value=forecast_value,
        observed_value=observed_value,
        absolute_error=absolute_error,
    )
    statement = statement.on_conflict_do_update(
        constraint="uq_accuracy_key",
        set_={
            "forecast_value": statement.excluded.forecast_value,
            "observed_value": statement.excluded.observed_value,
            "absolute_error": statement.excluded.absolute_error,
        },
    )
    await session.execute(statement)


async def accuracy_summary(
    session: AsyncSession,
    *,
    location_id: int | None = None,
    metric: str = "temperature",
    max_horizon: int | None = None,
):
    """Aggregates stored accuracy rows into the three error measures.

    Reads the per-pair errors back out and reduces them with the pure
    `summarise`. Filters narrow the question: one location, one metric,
    forecasts no further ahead than max_horizon.
    """
    query = select(
        ForecastAccuracy.forecast_value, ForecastAccuracy.observed_value
    ).where(ForecastAccuracy.metric == metric)

    if location_id is not None:
        query = query.where(ForecastAccuracy.location_id == location_id)
    if max_horizon is not None:
        query = query.where(ForecastAccuracy.horizon_hours <= max_horizon)

    rows = (await session.execute(query)).all()
    pairs = [(row.forecast_value, row.observed_value) for row in rows]
    return summarise(pairs)


async def accuracy_by_horizon(
    session: AsyncSession,
    *,
    location_id: int | None = None,
    metric: str = "temperature",
) -> dict[int, object]:
    """Error broken down by forecast horizon.

    This is the analysis's headline question: does a forecast made further
    ahead miss by more? Returns a horizon → ErrorStats map, so a caller can
    see the error curve grow (or not) with lead time.
    """
    query = select(
        ForecastAccuracy.horizon_hours,
        ForecastAccuracy.forecast_value,
        ForecastAccuracy.observed_value,
    ).where(ForecastAccuracy.metric == metric)

    if location_id is not None:
        query = query.where(ForecastAccuracy.location_id == location_id)

    rows = (await session.execute(query)).all()

    buckets: dict[int, list[tuple[float, float]]] = {}
    for row in rows:
        buckets.setdefault(row.horizon_hours, []).append(
            (row.forecast_value, row.observed_value)
        )

    return {horizon: summarise(pairs) for horizon, pairs in sorted(buckets.items())}
