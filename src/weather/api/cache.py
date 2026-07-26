"""Response caching, backed by Redis.

Weather data changes hourly at most, but a popular endpoint might be asked
for the same city's current conditions many times a minute. Caching turns
all but the first of those into a Redis lookup instead of a database query
— faster for the caller, and lighter on Postgres.

Like the rate limiter, this is best-effort. A cache miss, a serialisation
problem, or an unreachable Redis all fall back to computing the value
fresh. The cache is an optimisation; it must never be the reason a request
fails.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

log = structlog.get_logger()


async def cached_json(
    cache: Any,
    key: str,
    ttl: int,
    produce: Callable[[], Awaitable[Any]],
    *,
    enabled: bool = True,
) -> Any:
    """Returns a cached value, or computes, stores and returns a fresh one.

    `produce` is an async function that does the real work — the database
    query. It runs only on a miss. The result is stored as JSON with the
    given time-to-live, so a stale value can never outlive its window.
    """
    if not enabled:
        return await produce()

    try:
        hit = await cache.get(key)
        if hit is not None:
            return json.loads(hit)
    except Exception as exc:  # noqa: BLE001
        log.warning("cache_read_failed", key=key, error=str(exc))

    value = await produce()

    try:
        await cache.set(key, json.dumps(value, default=str), ex=ttl)
    except Exception as exc:  # noqa: BLE001
        log.warning("cache_write_failed", key=key, error=str(exc))

    return value
