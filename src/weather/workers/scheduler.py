"""When the jobs run, and the guarantees around running them.

APScheduler triggers the jobs on a clock: observations every hour on the
hour, forecasts once a day. Three settings shape its behaviour, and each
answers a specific failure it would otherwise have:

  - `max_instances=1`: never run two copies of the same job at once. If a
    fetch across 81 cities runs long and the next hour arrives before it
    finishes, the new trigger is dropped rather than piling a second run
    on top of the first, doubling the load on Open-Meteo.

  - `coalesce=True`: if the process was asleep or busy and several
    triggers were missed, run the job once on wake, not once per missed
    trigger. Catching up hour-by-hour would be a pointless flood.

  - `misfire_grace_time`: a trigger that fires a little late still counts;
    one that is hopelessly late is skipped. There is no value in fetching
    "this hour's" weather forty minutes into the next hour.
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.ext.asyncio import async_sessionmaker

from weather.clients.open_meteo import OpenMeteoClient
from weather.workers.jobs import collect_forecasts, collect_observations

log = structlog.get_logger()


def build_scheduler(
    session_factory: async_sessionmaker,
    client: OpenMeteoClient,
    *,
    forecast_days: int = 7,
) -> AsyncIOScheduler:
    """Wires the jobs onto a clock and returns the (unstarted) scheduler."""
    scheduler = AsyncIOScheduler(
        timezone="UTC",
        job_defaults={
            "max_instances": 1,
            "coalesce": True,
            "misfire_grace_time": 300,  # 5 minutes
        },
    )

    async def _observations() -> None:
        await collect_observations(session_factory, client, now=datetime.now(UTC))

    async def _forecasts() -> None:
        await collect_forecasts(
            session_factory,
            client,
            forecast_days=forecast_days,
            issued_at=datetime.now(UTC),
        )

    # Observations on the hour; forecasts once a day, just after midnight
    # UTC when a fresh model run is available.
    scheduler.add_job(
        _observations,
        CronTrigger(minute=5),
        id="observations",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _forecasts,
        CronTrigger(hour=0, minute=15),
        id="forecasts",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    return scheduler
