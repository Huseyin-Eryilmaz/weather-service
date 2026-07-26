"""Weather endpoints: current conditions, observation history, forecasts.

These are read-only and paginated. The date-range parameters are optional
so the same endpoint serves both "the last hundred readings" and "exactly
this week", and the limit is capped so no single call can ask for an
unbounded amount of data.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from weather.api.cache import cached_json
from weather.api.dependencies import get_db_session
from weather.api.schemas import (
    ForecastPage,
    ForecastPoint,
    ObservationPage,
    WeatherPoint,
)
from weather.db import queries

router = APIRouter(prefix="/locations/{location_id}", tags=["weather"])

# One hard cap on page size, shared by every list endpoint, so a caller
# cannot request a million rows in a single response.
MAX_LIMIT = 500


async def _require_location(session: AsyncSession, location_id: int) -> None:
    """404s if the location does not exist, so the weather endpoints do
    not silently return empty pages for a mistyped id."""
    if await queries.get_location(session, location_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="location not found")


@router.get("/current", response_model=WeatherPoint)
async def current_conditions(
    location_id: int,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> WeatherPoint:
    """The most recent observation for a location, cached briefly.

    The same current-conditions query can arrive many times a minute; the
    cache turns all but the first into a Redis lookup. On a miss, or if
    Redis is down, the value is computed fresh from the database.
    """
    await _require_location(session, location_id)
    settings = request.app.state.settings

    async def produce() -> dict:
        observation = await queries.latest_observation(session, location_id)
        if observation is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail="no observations recorded for this location yet",
            )
        return WeatherPoint.model_validate(observation).model_dump(mode="json")

    payload = await cached_json(
        request.app.state.cache,
        key=f"current:{location_id}",
        ttl=settings.cache_ttl_seconds,
        produce=produce,
        enabled=settings.cache_enabled,
    )
    return WeatherPoint.model_validate(payload)


@router.get("/observations", response_model=ObservationPage)
async def list_observations(
    location_id: int,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
) -> ObservationPage:
    """Paginated observation history, newest first, optionally by date."""
    await _require_location(session, location_id)
    items, total = await queries.list_observations(
        session, location_id, start=start, end=end, limit=limit, offset=offset
    )
    return ObservationPage(
        total=total,
        limit=limit,
        offset=offset,
        items=[WeatherPoint.model_validate(item) for item in items],
    )


@router.get("/forecasts", response_model=ForecastPage)
async def list_forecasts(
    location_id: int,
    latest_only: bool = True,
    limit: int = Query(default=100, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
) -> ForecastPage:
    """Forecasts for a location.

    By default only the newest prediction of each hour; pass
    `latest_only=false` for the full history of every prediction, which is
    what comparing forecasts against outcomes needs.
    """
    await _require_location(session, location_id)
    items, total = await queries.list_forecasts(
        session,
        location_id,
        latest_only=latest_only,
        limit=limit,
        offset=offset,
    )
    return ForecastPage(
        total=total,
        limit=limit,
        offset=offset,
        items=[ForecastPoint.model_validate(item) for item in items],
    )
