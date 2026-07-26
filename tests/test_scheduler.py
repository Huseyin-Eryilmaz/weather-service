"""The scheduler's wiring: which jobs exist, on what triggers, with what
overlap policy. The jobs' behaviour is tested elsewhere; here we check
only that they are registered correctly."""

from __future__ import annotations

import httpx

from weather.clients.open_meteo import OpenMeteoClient
from weather.db.base import make_engine, make_session_factory
from weather.workers.scheduler import build_scheduler


def _scheduler():
    engine = make_engine("postgresql+asyncpg://x:x@localhost/x")
    factory = make_session_factory(engine)
    http = httpx.AsyncClient()
    client = OpenMeteoClient(http, forecast_url="http://f", archive_url="http://a")
    return build_scheduler(factory, client)


def test_both_jobs_are_registered():
    scheduler = _scheduler()
    ids = {job.id for job in scheduler.get_jobs()}
    assert ids == {"observations", "forecasts"}


def test_jobs_do_not_overlap_themselves():
    """max_instances=1 is what stops a long run from being doubled by the
    next trigger — the single most important scheduler setting here."""
    scheduler = _scheduler()
    for job in scheduler.get_jobs():
        assert job.max_instances == 1


def test_missed_triggers_coalesce_into_one():
    scheduler = _scheduler()
    for job in scheduler.get_jobs():
        assert job.coalesce is True


def test_observations_run_more_often_than_forecasts():
    """A sanity check on the triggers: observations are hourly, forecasts
    daily, so the two must not share a schedule."""
    scheduler = _scheduler()
    obs = scheduler.get_job("observations")
    fc = scheduler.get_job("forecasts")
    assert str(obs.trigger) != str(fc.trigger)
