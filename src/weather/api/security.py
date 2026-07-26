"""API key authentication for the write endpoints.

The policy is deliberately asymmetric: reading weather is open, but
changing what the service tracks — adding or deactivating a location —
requires a key. That matches how the data is used. A dashboard or a
curious caller should be able to read freely; only a trusted operator
should be able to reshape the collection.

Keys are checked against the configured set. If no keys are configured at
all, auth is effectively off — the sensible default for local
development, where requiring a secret to add a test city would just be
friction. In production, keys are set and the guard bites.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader

# Declaring the scheme (rather than reading the header by hand) is what
# makes the padlock icon and "Authorize" button appear in /docs, so the
# interactive docs can send the key too. auto_error=False: a missing
# header is handled here, with our own message, not a generic 403.
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(
    request: Request,
    api_key: str | None = Depends(_api_key_header),
) -> None:
    """Allows the request through only with a valid key.

    Reads the configured keys from the app's settings (set once at
    startup), so the whole request path shares one settings object.
    Raises 401 when a key is required but missing or wrong. When no keys
    are configured, the endpoint is open — auth is disabled rather than
    impossible to satisfy.
    """
    allowed = request.app.state.settings.api_key_set
    if not allowed:
        return  # auth disabled

    if api_key is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="an API key is required for this operation",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    if api_key not in allowed:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="invalid API key")
