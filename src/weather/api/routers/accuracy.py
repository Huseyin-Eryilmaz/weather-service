"""Accuracy endpoints: how good the forecasts have turned out to be.

These read the scored `forecast_accuracy` rows and reduce them on the fly.
The summary answers "how far off, on average?"; the horizon breakdown
answers the more interesting "and how does that change with lead time?".
Both accept an optional location, so a caller can ask about one city or
the whole network.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from weather.api.dependencies import get_db_session
from weather.api.schemas import (
    AccuracyByHorizonOut,
    AccuracySummaryOut,
    ErrorStatsOut,
    HorizonBucketOut,
)
from weather.db import accuracy

router = APIRouter(prefix="/accuracy", tags=["accuracy"])


def _stats_out(stats) -> ErrorStatsOut | None:
    if stats is None:
        return None
    rounded = stats.rounded()
    return ErrorStatsOut(
        count=rounded.count, mae=rounded.mae, rmse=rounded.rmse, bias=rounded.bias
    )


@router.get("/summary", response_model=AccuracySummaryOut)
async def summary(
    location_id: int | None = None,
    metric: str = "temperature",
    max_horizon: int | None = Query(default=None, ge=0),
    session: AsyncSession = Depends(get_db_session),
) -> AccuracySummaryOut:
    """Overall error, optionally for one location or one lead-time window."""
    stats = await accuracy.accuracy_summary(
        session, location_id=location_id, metric=metric, max_horizon=max_horizon
    )
    return AccuracySummaryOut(
        location_id=location_id, metric=metric, stats=_stats_out(stats)
    )


@router.get("/by-horizon", response_model=AccuracyByHorizonOut)
async def by_horizon(
    location_id: int | None = None,
    metric: str = "temperature",
    session: AsyncSession = Depends(get_db_session),
) -> AccuracyByHorizonOut:
    """Error broken down by how far ahead the forecast was made."""
    buckets = await accuracy.accuracy_by_horizon(
        session, location_id=location_id, metric=metric
    )
    return AccuracyByHorizonOut(
        location_id=location_id,
        metric=metric,
        buckets=[
            HorizonBucketOut(horizon_hours=h, stats=_stats_out(s))
            for h, s in buckets.items()
            if s is not None
        ],
    )
