"""The Open-Meteo client: the one place that talks to the outside world.

An external API is the least reliable part of any system. It times out,
it rate-limits, it returns a 503 during a deploy, the network between here
and there hiccups. None of that should crash the worker or lose the other
80 cities because one request failed. So this client is built around a
single question: which failures are worth retrying, and which are not?

  - A timeout, a connection error, a 429, a 5xx: *transient*. The server
    or the network is briefly unhappy; waiting and trying again usually
    works. These are retried, with an exponential backoff so a struggling
    server is not hammered — 1s, then 2s, then 4s.

  - A 400 or 404: *permanent*. The request itself is wrong; retrying the
    same wrong request just fails three more times. These raise
    immediately.

The backoff is the important courtesy. Retrying instantly turns one
service's bad moment into a stampede from every client at once; spacing
the attempts out, and lengthening the gap each time, gives it room to
recover.
"""

from __future__ import annotations

import asyncio

import httpx
import structlog

from weather.clients.schemas import ForecastResponse, WeatherReading

log = structlog.get_logger()

_HOURLY_VARIABLES = (
    "temperature_2m",
    "relative_humidity_2m",
    "wind_speed_10m",
    "precipitation",
    "weather_code",
)


class WeatherAPIError(Exception):
    """A request failed in a way not worth retrying, or ran out of tries."""


class TransientError(WeatherAPIError):
    """A failure that might succeed on a later attempt."""


class PermanentError(WeatherAPIError):
    """A failure that will not: the request itself is the problem."""


# Status codes worth trying again. Everything else in the 4xx range means
# "you asked wrong", which a retry cannot fix.
_RETRYABLE_STATUS = {425, 429, 500, 502, 503, 504}


class OpenMeteoClient:
    """A thin, retrying wrapper over the Open-Meteo HTTP API.

    The `httpx.AsyncClient` is injected rather than created here, so tests
    can pass one wired to a mock transport — no network, no waiting, fully
    deterministic. In production the worker builds a real one and shares
    it across all 81 cities, reusing connections instead of reopening one
    per request.
    """

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        forecast_url: str,
        archive_url: str,
        max_retries: int = 3,
        backoff_base: float = 1.0,
    ) -> None:
        self._http = http
        self._forecast_url = forecast_url
        self._archive_url = archive_url
        self._max_retries = max_retries
        self._backoff_base = backoff_base

    async def fetch_forecast(
        self, *, latitude: float, longitude: float, forecast_days: int = 7
    ) -> list[WeatherReading]:
        """Upcoming hourly weather for a coordinate."""
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": ",".join(_HOURLY_VARIABLES),
            "forecast_days": forecast_days,
            "timezone": "UTC",
        }
        payload = await self._get(self._forecast_url, params)
        return ForecastResponse.model_validate(payload).to_records()

    async def fetch_archive(
        self,
        *,
        latitude: float,
        longitude: float,
        start_date: str,
        end_date: str,
    ) -> list[WeatherReading]:
        """Historical hourly weather for a coordinate and date range.

        Dates are ISO strings (YYYY-MM-DD); the archive endpoint requires
        an explicit range rather than a day count.
        """
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": ",".join(_HOURLY_VARIABLES),
            "start_date": start_date,
            "end_date": end_date,
            "timezone": "UTC",
        }
        payload = await self._get(self._archive_url, params)
        return ForecastResponse.model_validate(payload).to_records()

    async def _get(self, url: str, params: dict) -> dict:
        """One GET, with retries on transient failures.

        The loop runs up to `max_retries + 1` times. A permanent error
        breaks out immediately; a transient one waits and tries again,
        until the attempts run out and the last failure is re-raised as a
        `TransientError` so the caller can tell the two apart.
        """
        last_error: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                response = await self._http.get(url, params=params)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                # No response at all — the network failed. Always transient.
                last_error = exc
                log.warning("request_failed", url=url, attempt=attempt, error=str(exc))
            else:
                if response.status_code == 200:
                    return response.json()

                if response.status_code in _RETRYABLE_STATUS:
                    last_error = TransientError(f"HTTP {response.status_code}")
                    log.warning(
                        "retryable_status",
                        url=url,
                        attempt=attempt,
                        status=response.status_code,
                    )
                else:
                    # 400, 404, ...: the request is wrong. Do not retry.
                    raise PermanentError(
                        f"HTTP {response.status_code}: {response.text[:200]}"
                    )

            # Wait before the next attempt, unless that was the last one.
            if attempt < self._max_retries:
                await asyncio.sleep(self._backoff_base * (2**attempt))

        raise TransientError(
            f"giving up on {url} after {self._max_retries + 1} attempts"
        ) from last_error
