"""The FastAPI application: wiring, lifespan, and the health endpoint.

Two ideas shape this file.

**Lifespan.** Connections to Postgres and Redis are expensive to make and
cheap to keep. Opening one per request would waste most of the request's
time on a handshake, so they are created once when the process starts and
closed once when it stops. FastAPI's `lifespan` context manager is where
that happens: everything before `yield` runs at startup, everything after
at shutdown — including when the container is asked to stop, which is
what lets it shut down cleanly instead of dropping connections.

**Health checks that actually check.** An endpoint that returns `{"ok":
true}` unconditionally is worse than none: it tells Docker the service is
fine while the database is unreachable. So `/health/ready` really talks
to Postgres and Redis, and reports which one is broken. The distinction
between "live" and "ready" is the standard one — live means the process
is running, ready means it can serve traffic.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

import redis.asyncio as aioredis
import structlog
from fastapi import Depends, FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from weather.core.config import Settings, get_settings
from weather.db.base import make_session_factory

log = structlog.get_logger()


class HealthResponse(BaseModel):
    """The shape of a health check reply, documented automatically."""

    status: Literal["ok", "degraded"]
    checks: dict[str, str] = {}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Opens shared resources at startup and closes them at shutdown."""
    # Use the settings the app was built with, if any, so a test that
    # constructs the app with its own settings (auth on, cache off) sees
    # them here too — rather than lifespan quietly re-reading the cached
    # global and undoing the override.
    settings = getattr(app.state, "settings", None) or get_settings()

    engine = create_async_engine(
        str(settings.database_url),
        pool_size=settings.db_pool_size,
        echo=settings.db_echo,
        # Verify a pooled connection is still alive before handing it out.
        # Databases and proxies drop idle connections; without this, the
        # first request after a quiet period fails for no visible reason.
        pool_pre_ping=True,
    )
    cache = aioredis.from_url(str(settings.redis_url), decode_responses=True)

    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.cache = cache
    app.state.settings = settings

    log.info("startup", environment=settings.environment)
    try:
        yield
    finally:
        await engine.dispose()
        await cache.aclose()
        log.info("shutdown")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Builds the application.

    A factory rather than a module-level `app = FastAPI()` so tests can
    construct an instance with their own settings, and so nothing
    connects to anything at import time.
    """
    settings = settings or get_settings()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Weather data with forecast accuracy tracking",
        lifespan=lifespan,
    )

    # Stash the chosen settings so lifespan uses these, not the cached
    # global — this is what lets tests override auth, cache and limits.
    app.state.settings = settings

    # The React frontend runs on a different port during development,
    # which browsers treat as a different origin. Without this, every
    # request from it would be blocked before it reached us.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from weather.api.middleware import RequestContextMiddleware

    app.add_middleware(RequestContextMiddleware)

    from weather.api.ratelimit import enforce_rate_limit
    from weather.api.routers import accuracy, locations
    from weather.api.routers import status as status_router
    from weather.api.routers import weather as weather_router

    # Rate limiting applies to every route, so it is a router-level
    # dependency rather than something each endpoint remembers to add.
    app.include_router(locations.router, dependencies=[Depends(enforce_rate_limit)])
    app.include_router(
        weather_router.router, dependencies=[Depends(enforce_rate_limit)]
    )
    app.include_router(accuracy.router, dependencies=[Depends(enforce_rate_limit)])
    app.include_router(status_router.router, dependencies=[Depends(enforce_rate_limit)])

    @app.get("/health/live", response_model=HealthResponse, tags=["health"])
    async def health_live() -> HealthResponse:
        """Is the process alive? Deliberately checks nothing else.

        Docker restarts a container that fails this. If it depended on the
        database, a database blip would restart a perfectly healthy API —
        making an outage worse instead of better.
        """
        return HealthResponse(status="ok")

    @app.get("/health/ready", response_model=HealthResponse, tags=["health"])
    async def health_ready() -> JSONResponse:
        """Can this instance actually serve requests?

        Checks every dependency and names the ones that are broken, so a
        failure points at the culprit instead of just saying "not ready".
        """
        checks: dict[str, str] = {}

        engine: AsyncEngine = app.state.engine
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception as exc:  # noqa: BLE001 - report, never crash
            checks["database"] = f"error: {type(exc).__name__}"

        try:
            await app.state.cache.ping()
            checks["cache"] = "ok"
        except Exception as exc:  # noqa: BLE001
            checks["cache"] = f"error: {type(exc).__name__}"

        healthy = all(value == "ok" for value in checks.values())
        body = HealthResponse(status="ok" if healthy else "degraded", checks=checks)
        return JSONResponse(
            content=body.model_dump(),
            status_code=(
                status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE
            ),
        )

    @app.get("/", tags=["meta"])
    async def root() -> dict[str, str]:
        return {
            "service": settings.app_name,
            "docs": "/docs",
            "health": "/health/ready",
        }

    return app


app = create_app()
