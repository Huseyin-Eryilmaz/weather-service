"""Rate limiting, backed by Redis.

The goal is modest but real: stop one caller — a runaway script, a scraper
— from monopolising the service. The method is a fixed window counter, the
simplest scheme that works: for each client, count requests in the current
minute, and refuse once the count crosses the limit.

Redis is the right home for the counter for two reasons. It is shared, so
the limit holds across however many API processes are running rather than
being per-process. And it can expire a key on its own: the counter for a
minute is set to live exactly that long, so old windows clean themselves
up and there is no bookkeeping to sweep them away.

The whole thing is best-effort. If Redis is unreachable, the limiter fails
*open* — it lets the request through rather than taking the API down with
the cache. A rate limiter that causes an outage when it breaks is worse
than no rate limiter.
"""

from __future__ import annotations

import time

import structlog
from fastapi import HTTPException, Request, status

log = structlog.get_logger()


def _client_id(request: Request) -> str:
    """Identifies the caller: their API key if present, else their IP.

    Keying on the API key when there is one means an authenticated caller
    gets their own budget regardless of address; falling back to the IP
    covers anonymous readers.
    """
    key = request.headers.get("X-API-Key")
    if key:
        return f"key:{key}"
    client = request.client
    return f"ip:{client.host}" if client else "ip:unknown"


async def enforce_rate_limit(request: Request) -> None:
    """Counts this request and refuses it if the window is full."""
    settings = request.app.state.settings
    if not settings.rate_limit_enabled:
        return

    cache = request.app.state.cache
    limit = settings.rate_limit_per_minute
    window = int(time.time() // 60)  # current minute
    redis_key = f"ratelimit:{_client_id(request)}:{window}"

    try:
        # INCR returns the new value; the first caller in a window creates
        # the key, and we give it a 60s life so the window expires itself.
        count = await cache.incr(redis_key)
        if count == 1:
            await cache.expire(redis_key, 60)
    except Exception as exc:  # noqa: BLE001
        # Fail open: a broken limiter must not break the API.
        log.warning("rate_limit_unavailable", error=str(exc))
        return

    if count > limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"rate limit exceeded: {limit} requests per minute",
            headers={"Retry-After": "60"},
        )
