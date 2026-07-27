"""A status endpoint: is the collection actually running?

The health checks answer "can the API serve requests?". This answers a
different question the health checks cannot: "is the worker alive, and
when did it last do anything?". It reads the heartbeats the worker leaves
in Redis after each run, so a single call tells you whether data is still
flowing — the thing most likely to break silently in a pipeline like this.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from weather.workers.metrics import last_runs

router = APIRouter(prefix="/status", tags=["status"])


@router.get("")
async def status(request: Request) -> dict:
    """The service version and the worker's last runs, if any."""
    runs = await last_runs(request.app.state.cache)
    return {
        "service": request.app.state.settings.app_name,
        "environment": request.app.state.settings.environment,
        "worker": runs or "no runs recorded yet",
    }
