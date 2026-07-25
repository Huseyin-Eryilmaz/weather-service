"""Shared test fixtures.

The API is built through a factory, so tests can construct their own
instance with their own settings — no import-time connections, no shared
global application between test files.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from weather.api.main import create_app
from weather.core.config import Settings


@pytest.fixture()
def settings() -> Settings:
    return Settings(environment="test", debug=True)


@pytest.fixture()
async def client(settings: Settings) -> AsyncIterator[AsyncClient]:
    """An HTTP client wired straight into the app, with no network.

    ASGITransport calls the application in-process: the request never
    touches a socket, which makes these tests fast and independent of
    whether a server happens to be running.
    """
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
