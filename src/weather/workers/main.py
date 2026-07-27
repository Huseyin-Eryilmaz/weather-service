"""The worker process: build the pieces, start the scheduler, stay alive.

Phase 0's heartbeat is gone. The worker now owns three long-lived things
— a database engine, an HTTP client, and the scheduler — and its job is
to build them, start the clock, and keep running until asked to stop.

The `--once` flag runs both jobs immediately and exits, without the
scheduler. That is how the collection is tested end to end by hand, and
how the very first batch of data is pulled without waiting for the top of
the hour.
"""

from __future__ import annotations

import argparse
import asyncio
import signal

import httpx
import redis.asyncio as aioredis
import structlog

from weather.clients.open_meteo import OpenMeteoClient
from weather.core.config import get_settings
from weather.core.logging import configure_logging
from weather.db.base import make_engine, make_session_factory
from weather.workers.jobs import (
    collect_forecasts,
    collect_observations,
    compute_all_accuracy,
)
from weather.workers.metrics import record_run
from weather.workers.scheduler import build_scheduler

log = structlog.get_logger()


def _make_client(http: httpx.AsyncClient) -> OpenMeteoClient:
    settings = get_settings()
    return OpenMeteoClient(
        http,
        forecast_url=settings.open_meteo_forecast_url,
        archive_url=settings.open_meteo_archive_url,
        max_retries=settings.http_max_retries,
    )


async def run_once() -> None:
    """Run both collection jobs a single time, then return."""
    settings = get_settings()
    engine = make_engine(str(settings.database_url))
    factory = make_session_factory(engine)

    timeout = httpx.Timeout(settings.http_timeout_seconds)
    cache = aioredis.from_url(str(settings.redis_url), decode_responses=True)
    async with httpx.AsyncClient(timeout=timeout) as http:
        client = _make_client(http)
        # Record each run's outcome to the heartbeat, exactly as the
        # scheduled path does — so a one-shot run also shows up at /status,
        # not just runs triggered by the clock.
        forecasts = await collect_forecasts(factory, client)
        await record_run(
            cache,
            "forecasts",
            succeeded=forecasts.succeeded,
            failed=forecasts.failed,
            rows=forecasts.rows,
        )
        observations = await collect_observations(factory, client)
        await record_run(
            cache,
            "observations",
            succeeded=observations.succeeded,
            failed=observations.failed,
            rows=observations.rows,
        )
        await compute_all_accuracy(factory)

    await cache.aclose()
    await engine.dispose()


async def run_forever() -> None:
    """Start the scheduler and block until a stop signal arrives."""
    settings = get_settings()
    engine = make_engine(str(settings.database_url))
    factory = make_session_factory(engine)

    timeout = httpx.Timeout(settings.http_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as http:
        client = _make_client(http)
        cache = aioredis.from_url(str(settings.redis_url), decode_responses=True)
        scheduler = build_scheduler(factory, client, cache=cache)

        # A future that a signal handler resolves, so the process waits
        # here until the OS asks it to stop — the clean way to keep an
        # async program alive without a busy loop.
        stop = asyncio.get_running_loop().create_future()

        def _request_stop() -> None:
            if not stop.done():
                stop.set_result(None)

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _request_stop)

        scheduler.start()
        log.info("scheduler_started", jobs=[j.id for j in scheduler.get_jobs()])
        try:
            await stop
        finally:
            scheduler.shutdown(wait=False)
            await cache.aclose()
            log.info("scheduler_stopped")

    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Weather collection worker")
    parser.add_argument(
        "--once",
        action="store_true",
        help="run both jobs immediately and exit, without scheduling",
    )
    args = parser.parse_args()

    settings = get_settings()
    configure_logging(json_output=settings.is_production)

    if args.once:
        asyncio.run(run_once())
    else:
        try:
            asyncio.run(run_forever())
        except KeyboardInterrupt:
            log.info("worker_interrupted")


if __name__ == "__main__":
    main()
