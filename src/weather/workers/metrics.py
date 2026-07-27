"""A record of what the worker has done, kept in Redis.

A scheduled worker is easy to forget about and hard to see into: it has no
HTTP surface, so "is it still running, and when did it last succeed?" has
no obvious answer. This keeps a small heartbeat in Redis after each job —
when it last ran, how many rows it wrote, whether it succeeded — so the
API can expose that, and a glance tells you the collection is alive.

Redis rather than Postgres because this is operational ephemera, not
data: losing it on a restart costs nothing, and it does not belong in the
same store as the weather itself. Each job's last run overwrites the
previous, so the footprint stays tiny.
"""

from __future__ import annotations

import json
import time
from typing import Any

import structlog

log = structlog.get_logger()

_KEY_PREFIX = "worker:lastrun:"


async def record_run(
    cache: Any,
    job: str,
    *,
    succeeded: int,
    failed: int,
    rows: int,
) -> None:
    """Stores the outcome of one job run. Best-effort: never raises.

    If Redis is unreachable the worker must keep collecting, so a failed
    write here is logged and swallowed — the heartbeat is a convenience,
    not a dependency of the job it describes.
    """
    payload = {
        "job": job,
        "ran_at": time.time(),
        "succeeded": succeeded,
        "failed": failed,
        "rows": rows,
    }
    try:
        await cache.set(f"{_KEY_PREFIX}{job}", json.dumps(payload))
    except Exception as exc:  # noqa: BLE001
        log.warning("run_record_failed", job=job, error=str(exc))


async def last_runs(cache: Any) -> dict[str, dict]:
    """Returns the last recorded run of every job, for the status endpoint."""
    result: dict[str, dict] = {}
    try:
        keys = await cache.keys(f"{_KEY_PREFIX}*")
        for key in keys:
            raw = await cache.get(key)
            if raw:
                entry = json.loads(raw)
                result[entry["job"]] = entry
    except Exception as exc:  # noqa: BLE001
        log.warning("run_read_failed", error=str(exc))
    return result
