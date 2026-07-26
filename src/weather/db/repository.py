"""Writing data without creating duplicates.

The worker will fetch the same hours more than once — schedules overlap,
retries repeat, a backfill covers ground already covered. If every fetch
simply inserted, the tables would fill with duplicate readings and every
average would be wrong.

The fix is an *upsert*: insert, but if a row with the same unique key
already exists, update it instead of failing. Postgres spells this
`INSERT ... ON CONFLICT ... DO UPDATE`, and doing it in one statement
matters — checking "does it exist?" and then inserting would leave a gap
where two workers could both decide it does not, and both insert.

These functions take a session but never commit. Committing is the
caller's job, so several writes can share one transaction: either all of
them land or none do.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from weather.db.models import Forecast, Location, Observation


async def upsert_location(
    session: AsyncSession,
    *,
    name: str,
    latitude: float,
    longitude: float,
    country: str = "TR",
) -> None:
    """Inserts a location, or leaves the existing one untouched.

    Locations use DO NOTHING rather than DO UPDATE: re-seeding should not
    quietly overwrite a name someone may have corrected by hand.
    """
    statement = pg_insert(Location).values(
        name=name,
        latitude=latitude,
        longitude=longitude,
        country=country,
    )
    statement = statement.on_conflict_do_nothing(constraint="uq_location_coords")
    await session.execute(statement)


async def upsert_observation(
    session: AsyncSession,
    *,
    location_id: int,
    observed_at: datetime,
    temperature_c: float | None = None,
    humidity_pct: float | None = None,
    wind_speed_kmh: float | None = None,
    precipitation_mm: float | None = None,
) -> None:
    """Inserts or refreshes one observation for a location and hour."""
    values = {
        "location_id": location_id,
        "observed_at": observed_at,
        "temperature_c": temperature_c,
        "humidity_pct": humidity_pct,
        "wind_speed_kmh": wind_speed_kmh,
        "precipitation_mm": precipitation_mm,
    }
    statement = pg_insert(Observation).values(**values)
    # On a repeat, refresh the measurements — a later fetch may carry a
    # corrected value — but not the identifying columns.
    statement = statement.on_conflict_do_update(
        constraint="uq_observation_location_time",
        set_={
            "temperature_c": statement.excluded.temperature_c,
            "humidity_pct": statement.excluded.humidity_pct,
            "wind_speed_kmh": statement.excluded.wind_speed_kmh,
            "precipitation_mm": statement.excluded.precipitation_mm,
        },
    )
    await session.execute(statement)


async def upsert_forecast(
    session: AsyncSession,
    *,
    location_id: int,
    issued_at: datetime,
    target_time: datetime,
    temperature_c: float | None = None,
    humidity_pct: float | None = None,
    wind_speed_kmh: float | None = None,
    precipitation_mm: float | None = None,
) -> None:
    """Inserts or refreshes one forecast reading."""
    values = {
        "location_id": location_id,
        "issued_at": issued_at,
        "target_time": target_time,
        "temperature_c": temperature_c,
        "humidity_pct": humidity_pct,
        "wind_speed_kmh": wind_speed_kmh,
        "precipitation_mm": precipitation_mm,
    }
    statement = pg_insert(Forecast).values(**values)
    statement = statement.on_conflict_do_update(
        constraint="uq_forecast_location_issue_target",
        set_={
            "temperature_c": statement.excluded.temperature_c,
            "humidity_pct": statement.excluded.humidity_pct,
            "wind_speed_kmh": statement.excluded.wind_speed_kmh,
            "precipitation_mm": statement.excluded.precipitation_mm,
        },
    )
    await session.execute(statement)
