"""The Open-Meteo client: parsing, and the retry policy.

The retry tests use a mock transport that answers however the test wants
without a network, and monkeypatch `asyncio.sleep` so the backoff waits
take no real time. What is verified is the *policy* — how many attempts,
which errors retry and which do not — not httpx itself.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from weather.clients.open_meteo import (
    OpenMeteoClient,
    PermanentError,
    TransientError,
)

FIXTURE = Path(__file__).parent / "fixtures" / "forecast_ankara.json"

pytestmark = pytest.mark.asyncio


def _client(handler, **kwargs) -> OpenMeteoClient:
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport)
    return OpenMeteoClient(
        http,
        forecast_url="https://example.test/forecast",
        archive_url="https://example.test/archive",
        backoff_base=0.0,  # no real waiting in tests
        **kwargs,
    )


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Make backoff instant, so retry tests do not actually pause."""

    async def instant(_seconds):
        return None

    monkeypatch.setattr("weather.clients.open_meteo.asyncio.sleep", instant)


async def test_a_successful_forecast_is_parsed_into_hourly_records():
    payload = json.loads(FIXTURE.read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    client = _client(handler)
    records = await client.fetch_forecast(latitude=39.9, longitude=32.8)

    assert len(records) == 4
    assert records[0].temperature_c == 22.5
    assert records[0].humidity_pct == 55
    assert records[3].wind_speed_kmh == 9.9


async def test_the_request_carries_the_expected_parameters():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return httpx.Response(200, json=json.loads(FIXTURE.read_text()))

    client = _client(handler)
    await client.fetch_forecast(latitude=39.9, longitude=32.8, forecast_days=3)

    assert seen["latitude"] == "39.9"
    assert seen["forecast_days"] == "3"
    assert "temperature_2m" in seen["hourly"]
    assert seen["timezone"] == "UTC"


async def test_a_transient_error_is_retried_then_succeeds():
    """The first two attempts fail with a 503, the third works. The client
    should return the good data, not the earlier failures."""
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json=json.loads(FIXTURE.read_text()))

    client = _client(handler, max_retries=3)
    records = await client.fetch_forecast(latitude=39.9, longitude=32.8)

    assert attempts["count"] == 3
    assert len(records) == 4


async def test_retries_are_bounded_and_then_give_up():
    """A server that never recovers must not loop forever: the client
    tries max_retries + 1 times, then raises."""
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(503)

    client = _client(handler, max_retries=2)
    with pytest.raises(TransientError):
        await client.fetch_forecast(latitude=39.9, longitude=32.8)

    assert attempts["count"] == 3  # 1 initial + 2 retries


async def test_a_timeout_is_treated_as_transient_and_retried():
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise httpx.ConnectTimeout("too slow")
        return httpx.Response(200, json=json.loads(FIXTURE.read_text()))

    client = _client(handler, max_retries=3)
    records = await client.fetch_forecast(latitude=39.9, longitude=32.8)

    assert attempts["count"] == 2
    assert len(records) == 4


async def test_a_client_error_is_permanent_and_not_retried():
    """A 400 means the request is wrong; retrying it wastes three more
    calls to get the same answer. It should raise on the first try."""
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(400, text="invalid coordinate")

    client = _client(handler, max_retries=3)
    with pytest.raises(PermanentError):
        await client.fetch_forecast(latitude=999, longitude=999)

    assert attempts["count"] == 1  # no retries


async def test_a_rate_limit_is_retryable():
    """429 is the one 4xx that is worth waiting out."""
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(429)
        return httpx.Response(200, json=json.loads(FIXTURE.read_text()))

    client = _client(handler, max_retries=3)
    records = await client.fetch_forecast(latitude=39.9, longitude=32.8)
    assert attempts["count"] == 2
    assert len(records) == 4


async def test_the_archive_endpoint_is_used_for_history():
    seen = {"url": None}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url).split("?")[0]
        return httpx.Response(200, json=json.loads(FIXTURE.read_text()))

    client = _client(handler)
    await client.fetch_archive(
        latitude=39.9, longitude=32.8, start_date="2026-01-01", end_date="2026-01-02"
    )
    assert seen["url"] == "https://example.test/archive"
