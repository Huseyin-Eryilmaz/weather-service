"""Middleware that makes a request traceable from start to finish.

The problem it solves is mundane but real: when something goes wrong in
production, the logs are a single stream with many requests interleaved,
and "what happened to *this* request?" is unanswerable unless every line
it produced can be picked out. The fix is a correlation id — one unique
value per request, attached to every log line that request emits.

structlog's contextvars are what carry it. Binding the id once at the top
of the request puts it into a context that every `log` call inside that
request reads automatically, without any function having to pass it along.
The same mechanism records the method, path, status and duration, so each
request leaves exactly one summary line whether it succeeded or failed —
and failures leave a line too, rather than only a stack trace.
"""

from __future__ import annotations

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

log = structlog.get_logger()

# The header a caller (or an upstream proxy) can use to supply their own
# id, so a trace can span more than one service. Absent, we mint one.
REQUEST_ID_HEADER = "X-Request-ID"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns each request an id, logs its outcome, and echoes the id back."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex

        # Bind the id (and the basics) into the logging context for the
        # duration of this request. clear_contextvars first so nothing
        # leaks in from a previous request handled on the same worker.
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # Log the failure with its context, then re-raise so the normal
            # error handling still runs. Without this, an unhandled error
            # would leave only a bare traceback with no request id.
            duration_ms = (time.perf_counter() - start) * 1000
            log.exception("request_failed", duration_ms=round(duration_ms, 1))
            raise

        duration_ms = (time.perf_counter() - start) * 1000
        log.info(
            "request_completed",
            status=response.status_code,
            duration_ms=round(duration_ms, 1),
        )

        # Hand the id back so a caller can quote it in a bug report, and a
        # log search finds exactly their request.
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
