"""Reading data back out: the queries behind the API endpoints.

The write side had `repository.py`; this is the read side. Keeping the
SQL here rather than inside the route handlers means a handler stays a
thin translation between HTTP and a function call, and a query can be
tested on its own against a real database without going through the web
layer at all.

Every list query is paginated. A location can accumulate thousands of
hourly rows, and an endpoint that returned all of them would eventually
try to serialise a year of weather into one response. `limit`/`offset`
with a total count keeps every response bounded and lets the caller walk
the rest deliberately.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from weather.db.models import Forecast, Location, Observation


async def list_locations(
    session: AsyncSession, *, active_only: bool = True
) -> list[Location]:
    query = select(Location).order_by(Location.name)
    if active_only:
        query = query.where(Location.is_active.is_(True))
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_location(session: AsyncSession, location_id: int) -> Location | None:
    return await session.get(Location, location_id)


async def find_location_by_coords(
    session: AsyncSession, latitude: float, longitude: float
) -> Location | None:
    result = await session.execute(
        select(Location).where(
            Location.latitude == latitude, Location.longitude == longitude
        )
    )
    return result.scalars().first()


async def create_location(
    session: AsyncSession,
    *,
    name: str,
    latitude: float,
    longitude: float,
    country: str = "TR",
) -> Location:
    """Inserts a location and returns it, populated with its new id."""
    location = Location(
        name=name, latitude=latitude, longitude=longitude, country=country
    )
    session.add(location)
    await session.commit()
    await session.refresh(location)
    return location


async def deactivate_location(
    session: AsyncSession, location_id: int
) -> Location | None:
    """Marks a location inactive rather than deleting it.

    A soft delete keeps the history intact: the observations and forecasts
    already collected stay queryable, and collection simply stops. A hard
    delete would cascade and throw all of that away.
    """
    location = await session.get(Location, location_id)
    if location is None:
        return None
    location.is_active = False
    await session.commit()
    await session.refresh(location)
    return location


async def latest_observation(
    session: AsyncSession, location_id: int
) -> Observation | None:
    result = await session.execute(
        select(Observation)
        .where(Observation.location_id == location_id)
        .order_by(Observation.observed_at.desc())
        .limit(1)
    )
    return result.scalars().first()


async def list_observations(
    session: AsyncSession,
    location_id: int,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Observation], int]:
    """A page of observations, newest first, with the total that match.

    The total is counted with the same filters but without the limit, so
    the caller learns how many pages there are, not just what is on this
    one. Both run in one function so the filters cannot drift apart.
    """
    conditions = [Observation.location_id == location_id]
    if start is not None:
        conditions.append(Observation.observed_at >= start)
    if end is not None:
        conditions.append(Observation.observed_at <= end)

    total = await session.scalar(
        select(func.count()).select_from(Observation).where(*conditions)
    )

    result = await session.execute(
        select(Observation)
        .where(*conditions)
        .order_by(Observation.observed_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), total or 0


async def list_forecasts(
    session: AsyncSession,
    location_id: int,
    *,
    latest_only: bool = True,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Forecast], int]:
    """A page of forecasts for a location.

    With `latest_only`, only the most recent prediction of each target
    hour is returned — the one a user asking "what is the forecast?"
    actually wants, rather than every stale prediction ever made for that
    hour. The full history stays available with the flag off, which is
    what the accuracy analysis in a later phase will need.
    """
    conditions = [Forecast.location_id == location_id]

    if latest_only:
        # For each target_time, the greatest issued_at.
        newest = (
            select(
                Forecast.target_time,
                func.max(Forecast.issued_at).label("issued_at"),
            )
            .where(Forecast.location_id == location_id)
            .group_by(Forecast.target_time)
            .subquery()
        )
        base = (
            select(Forecast)
            .join(
                newest,
                (Forecast.target_time == newest.c.target_time)
                & (Forecast.issued_at == newest.c.issued_at),
            )
            .where(Forecast.location_id == location_id)
        )
    else:
        base = select(Forecast).where(*conditions)

    total_query = select(func.count()).select_from(base.subquery())
    total = await session.scalar(total_query)

    result = await session.execute(
        base.order_by(Forecast.target_time).limit(limit).offset(offset)
    )
    return list(result.scalars().all()), total or 0
