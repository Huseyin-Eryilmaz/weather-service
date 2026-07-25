"""The background worker's entry point.

Phase 0 gives it a heartbeat and nothing else: it starts, logs, and
stays alive. That is enough to prove the service definition, the shared
image and the compose wiring all work — the actual scheduled jobs arrive
in Phase 3.

It shares the codebase with the API but runs as a separate process, for
the usual reason: a slow data fetch should never make an HTTP request
wait, and the two need to scale and fail independently.
"""

from __future__ import annotations

import asyncio

import structlog

from weather.core.config import get_settings
from weather.core.logging import configure_logging

log = structlog.get_logger()

HEARTBEAT_SECONDS = 30


async def run() -> None:
    settings = get_settings()
    configure_logging(json_output=settings.is_production)
    log.info("worker_started", environment=settings.environment)

    while True:
        log.info("worker_heartbeat")
        await asyncio.sleep(HEARTBEAT_SECONDS)


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        # Docker sends SIGINT/SIGTERM on `compose down`; exiting quietly
        # keeps the shutdown logs clean instead of printing a traceback.
        log.info("worker_stopped")


if __name__ == "__main__":
    main()
