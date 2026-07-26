"""What the worker actually does, independent of when it does it.

The scheduling — every hour, every day — lives next door in
`scheduler.py`. This module holds the jobs themselves: fetch every active
location's weather and store it. Keeping the two apart means a job can be
tested by calling it once, with no clock and no scheduler involved, the
same way the game core could be tested without a terminal.

The governing rule here is that *one city's bad luck must not sink the
rest*. A single failed fetch — a timeout, a 500, a coordinate Open-Meteo
dislikes — is caught, logged, and counted, and the loop moves on. A run
that touches 81 cities and fails on 2 is a success with 2 failures, not a
crashed run that stored nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from weather.clients.ingest import ingest_forecasts, ingest_observations
from weather.clients.open_meteo import OpenMeteoClient, WeatherAPIError
from weather.db.models import Location

log = structlog.get_logger()


@dataclass
class JobResult:
    """The tally from one run across all locations."""

    locations: int = 0
    succeeded: int = 0
    failed: int = 0
    rows: int = 0

    @property
    def ok(self) -> bool:
        """A run is healthy if at least one location succeeded.

        Zero successes means something systemic — the API is down, the
        network is gone — rather than a couple of unlucky cities, and that
        is worth surfacing as a failed run.
        """
        return self.locations == 0 or self.succeeded > 0


async def _active_locations(session) -> list[Location]:
    result = await session.execute(
        select(Location).where(Location.is_active.is_(True)).order_by(Location.id)
    )
    return list(result.scalars().all())


async def collect_observations(
    session_factory: async_sessionmaker,
    client: OpenMeteoClient,
    *,
    now: datetime | None = None,
) -> JobResult:
    """Fetches and stores current-hour observations for every location."""
    now = now or datetime.now(UTC)
    result = JobResult()

    async with session_factory() as session:
        locations = await _active_locations(session)

    result.locations = len(locations)
    log.info("observation_run_started", locations=result.locations)

    for location in locations:
        # A fresh session per location, so one city's rollback cannot
        # discard another city's already-stored rows.
        async with session_factory() as session:
            try:
                rows = await ingest_observations(
                    session,
                    client,
                    location_id=location.id,
                    latitude=location.latitude,
                    longitude=location.longitude,
                    now=now,
                )
                result.succeeded += 1
                result.rows += rows
            except WeatherAPIError as exc:
                result.failed += 1
                log.warning(
                    "location_failed",
                    location=location.name,
                    error=str(exc),
                )

    log.info(
        "observation_run_finished",
        succeeded=result.succeeded,
        failed=result.failed,
        rows=result.rows,
    )
    return result


async def collect_forecasts(
    session_factory: async_sessionmaker,
    client: OpenMeteoClient,
    *,
    forecast_days: int = 7,
    issued_at: datetime | None = None,
) -> JobResult:
    """Fetches and stores forecasts for every location."""
    issued_at = issued_at or datetime.now(UTC)
    result = JobResult()

    async with session_factory() as session:
        locations = await _active_locations(session)

    result.locations = len(locations)
    log.info("forecast_run_started", locations=result.locations)

    for location in locations:
        async with session_factory() as session:
            try:
                rows = await ingest_forecasts(
                    session,
                    client,
                    location_id=location.id,
                    latitude=location.latitude,
                    longitude=location.longitude,
                    forecast_days=forecast_days,
                    issued_at=issued_at,
                )
                result.succeeded += 1
                result.rows += rows
            except WeatherAPIError as exc:
                result.failed += 1
                log.warning(
                    "location_failed",
                    location=location.name,
                    error=str(exc),
                )

    log.info(
        "forecast_run_finished",
        succeeded=result.succeeded,
        failed=result.failed,
        rows=result.rows,
    )
    return result
