"""Loading the 81 provinces into the database.

Runnable as `python -m weather.db.seed`. It is idempotent by design:
every insert uses the location upsert, so running it once or ten times
leaves the same 81 rows. That property is what lets it run safely on
every deployment, rather than being a one-time command someone has to
remember not to repeat.
"""

from __future__ import annotations

import asyncio

import structlog

from weather.core.config import get_settings
from weather.core.logging import configure_logging
from weather.db.base import make_engine, make_session_factory
from weather.db.provinces import PROVINCES
from weather.db.repository import upsert_location

log = structlog.get_logger()


async def seed_locations() -> int:
    """Upserts every province. Returns how many were processed."""
    settings = get_settings()
    engine = make_engine(str(settings.database_url), echo=settings.db_echo)
    factory = make_session_factory(engine)

    try:
        async with factory() as session:
            for name, latitude, longitude in PROVINCES:
                await upsert_location(
                    session,
                    name=name,
                    latitude=latitude,
                    longitude=longitude,
                )
            await session.commit()
    finally:
        await engine.dispose()

    log.info("seed_complete", provinces=len(PROVINCES))
    return len(PROVINCES)


def main() -> None:
    settings = get_settings()
    configure_logging(json_output=settings.is_production)
    asyncio.run(seed_locations())


if __name__ == "__main__":
    main()
