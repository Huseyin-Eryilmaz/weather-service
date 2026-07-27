"""Request tracing and the worker status endpoint.

The middleware tests assert on the response contract — that an id comes
back, and a supplied one is preserved. The status tests go through Redis,
reading back a run the way the worker would have written it.
"""

from __future__ import annotations

import pytest

from weather.workers.metrics import last_runs, record_run

pytestmark = pytest.mark.asyncio


# ----------------------------------------------------------------------
# Request tracing
# ----------------------------------------------------------------------
async def test_every_response_carries_a_request_id(api_client):
    response = await api_client.get("/locations")
    assert "X-Request-ID" in response.headers
    assert len(response.headers["X-Request-ID"]) > 0


async def test_a_supplied_request_id_is_preserved(api_client):
    """A caller (or upstream proxy) can supply an id so a trace spans
    services; we must not overwrite it."""
    response = await api_client.get(
        "/locations", headers={"X-Request-ID": "trace-abc-123"}
    )
    assert response.headers["X-Request-ID"] == "trace-abc-123"


async def test_each_request_gets_a_distinct_id(api_client):
    first = await api_client.get("/locations")
    second = await api_client.get("/locations")
    assert first.headers["X-Request-ID"] != second.headers["X-Request-ID"]


# ----------------------------------------------------------------------
# Status endpoint
# ----------------------------------------------------------------------
async def test_status_reports_no_runs_before_the_worker_has_run(api_client):
    response = await api_client.get("/status")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "weather-service"
    assert body["worker"] == "no runs recorded yet"


async def test_status_reports_the_workers_last_run(api_client):
    # Simulate what the worker records after a collection run.
    await record_run(
        api_client._transport.app.state.cache,
        "observations",
        succeeded=79,
        failed=2,
        rows=79,
    )
    response = await api_client.get("/status")
    body = response.json()
    assert body["worker"]["observations"]["succeeded"] == 79
    assert body["worker"]["observations"]["failed"] == 2


# ----------------------------------------------------------------------
# The heartbeat helper itself
# ----------------------------------------------------------------------
async def test_recording_a_run_is_readable_back(api_client):
    cache = api_client._transport.app.state.cache
    await record_run(cache, "forecasts", succeeded=81, failed=0, rows=567)
    runs = await last_runs(cache)
    assert runs["forecasts"]["rows"] == 567


async def test_a_later_run_overwrites_the_earlier_one(api_client):
    """Only the last run of each job is kept — the footprint stays tiny."""
    cache = api_client._transport.app.state.cache
    await record_run(cache, "observations", succeeded=1, failed=0, rows=1)
    await record_run(cache, "observations", succeeded=81, failed=0, rows=81)
    runs = await last_runs(cache)
    assert runs["observations"]["rows"] == 81


# ----------------------------------------------------------------------
# The --once run records heartbeats too (regression: it used not to)
# ----------------------------------------------------------------------
async def test_a_one_shot_run_records_heartbeats(api_client, monkeypatch):
    """`--once` must leave a heartbeat, exactly as the scheduled path does,
    so /status reflects a manual collection and not only clock-triggered
    ones."""
    import json
    from pathlib import Path

    import httpx

    import weather.workers.main as wmain
    from weather.clients.open_meteo import OpenMeteoClient

    fixture = json.loads(
        (Path(__file__).parent / "fixtures" / "forecast_ankara.json").read_text()
    )

    # Seed a couple of locations to collect for.
    for name, lat, lon in [("Ankara", 39.94, 32.86), ("Izmir", 38.42, 27.14)]:
        await api_client.post(
            "/locations", json={"name": name, "latitude": lat, "longitude": lon}
        )

    def fake_client(http):
        def handler(request):
            return httpx.Response(200, json=fixture)

        transport = httpx.MockTransport(handler)
        return OpenMeteoClient(
            httpx.AsyncClient(transport=transport),
            forecast_url="http://f",
            archive_url="http://a",
        )

    monkeypatch.setattr(wmain, "_make_client", fake_client)

    cache = api_client._transport.app.state.cache
    await cache.delete("worker:lastrun:observations", "worker:lastrun:forecasts")

    await wmain.run_once()

    # Both heartbeats should now exist.
    from weather.workers.metrics import last_runs

    runs = await last_runs(cache)
    assert "observations" in runs
    assert "forecasts" in runs
