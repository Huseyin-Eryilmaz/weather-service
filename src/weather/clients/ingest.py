"""Joining the client to the database: fetch, then store.

The client returns clean `WeatherReading` objects; the repository knows
how to upsert. This module is the thin seam between them — it decides
what an observation is versus a forecast, and it commits.

The one real decision here is what counts as each. An *observation* is
the weather that has already happened, so from a forecast response we
keep only the hours at or before now. A *forecast* is the weather still
to come, and it carries the extra timestamp — `issued_at`, the moment we
asked — that the accuracy analysis will later need.
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from weather.clients.open_meteo import OpenMeteoClient
from weather.clients.schemas import WeatherReading
from weather.db.repository import upsert_forecast, upsert_observation

log = structlog.get_logger()


def _aware(value: datetime) -> datetime:
    """Treats a naive timestamp as UTC.

    Open-Meteo, asked for `timezone=UTC`, returns times without an offset.
    They *are* UTC, but Python calls them naive, and comparing a naive to
    an aware datetime raises. Stamping UTC on them makes the comparison —
    and the storage — unambiguous.
    """
    return value if value.tzinfo else value.replace(tzinfo=UTC)


async def ingest_observations(
    session: AsyncSession,
    client: OpenMeteoClient,
    *,
    location_id: int,
    latitude: float,
    longitude: float,
    now: datetime | None = None,
) -> int:
    """Fetches recent weather and stores the past hours as observations.

    Returns the number of hours stored. `now` is injectable so a test can
    pin "the present" instead of depending on the wall clock.
    """
    now = _aware(now or datetime.now(UTC))
    readings = await client.fetch_forecast(
        latitude=latitude, longitude=longitude, forecast_days=1
    )

    stored = 0
    for reading in readings:
        if _aware(reading.time) <= now:
            await _store_observation(session, location_id, reading)
            stored += 1

    await session.commit()
    log.info("observations_ingested", location_id=location_id, hours=stored)
    return stored


async def ingest_forecasts(
    session: AsyncSession,
    client: OpenMeteoClient,
    *,
    location_id: int,
    latitude: float,
    longitude: float,
    forecast_days: int = 7,
    issued_at: datetime | None = None,
) -> int:
    """Fetches upcoming weather and stores the future hours as forecasts."""
    issued_at = _aware(issued_at or datetime.now(UTC))
    readings = await client.fetch_forecast(
        latitude=latitude, longitude=longitude, forecast_days=forecast_days
    )

    stored = 0
    for reading in readings:
        if _aware(reading.time) > issued_at:
            await upsert_forecast(
                session,
                location_id=location_id,
                issued_at=issued_at,
                target_time=_aware(reading.time),
                temperature_c=reading.temperature_c,
                humidity_pct=reading.humidity_pct,
                wind_speed_kmh=reading.wind_speed_kmh,
                precipitation_mm=reading.precipitation_mm,
                weather_code=reading.weather_code,
            )
            stored += 1

    await session.commit()
    log.info("forecasts_ingested", location_id=location_id, hours=stored)
    return stored


async def _store_observation(
    session: AsyncSession, location_id: int, reading: WeatherReading
) -> None:
    await upsert_observation(
        session,
        location_id=location_id,
        observed_at=_aware(reading.time),
        temperature_c=reading.temperature_c,
        humidity_pct=reading.humidity_pct,
        wind_speed_kmh=reading.wind_speed_kmh,
        precipitation_mm=reading.precipitation_mm,
        weather_code=reading.weather_code,
    )
