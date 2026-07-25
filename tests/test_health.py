"""Health endpoints.

The readiness check talks to Postgres and Redis, so these tests replace
those with stand-ins. That is the point of the exercise: the endpoint's
job is to *report* what it finds, and both outcomes need testing —
including the one where a dependency is down, which is hard to arrange
on demand with a real database.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from weather.api.main import create_app
from weather.core.config import Settings


class _FakeConnection:
    async def execute(self, *args, **kwargs):
        return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class _HealthyEngine:
    def connect(self):
        return _FakeConnection()


class _BrokenEngine:
    def connect(self):
        raise ConnectionError("database is down")


class _HealthyCache:
    async def ping(self):
        return True


class _BrokenCache:
    async def ping(self):
        raise ConnectionError("cache is down")


async def _client_with(engine, cache) -> AsyncClient:
    app = create_app(Settings(environment="test"))
    app.state.engine = engine
    app.state.cache = cache
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_liveness_ignores_dependencies():
    """Liveness must not depend on Postgres: a database blip should not
    make Docker restart a perfectly healthy API process."""
    async with await _client_with(_BrokenEngine(), _BrokenCache()) as client:
        response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_readiness_reports_ok_when_everything_answers():
    async with await _client_with(_HealthyEngine(), _HealthyCache()) as client:
        response = await client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"] == {"database": "ok", "cache": "ok"}


@pytest.mark.parametrize(
    ("engine", "cache", "broken"),
    [
        (_BrokenEngine(), _HealthyCache(), "database"),
        (_HealthyEngine(), _BrokenCache(), "cache"),
    ],
)
async def test_readiness_names_the_broken_dependency(engine, cache, broken):
    """A failure that says only "not ready" sends you hunting. This one
    points at the culprit."""
    async with await _client_with(engine, cache) as client:
        response = await client.get("/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"][broken].startswith("error:")


async def test_readiness_survives_both_being_down():
    async with await _client_with(_BrokenEngine(), _BrokenCache()) as client:
        response = await client.get("/health/ready")
    assert response.status_code == 503
    assert len(response.json()["checks"]) == 2


async def test_the_root_endpoint_points_at_the_docs(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert response.json()["docs"] == "/docs"


async def test_openapi_schema_is_generated(client):
    """FastAPI builds this from the type hints; it is what powers /docs
    and what a frontend can generate a typed client from."""
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    assert "/health/ready" in response.json()["paths"]
