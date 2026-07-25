"""Structured logging setup.

Plain text logs are written for humans and parsed by nobody. The moment
you have more than one service and want to answer "what happened to this
request?", you need logs that a machine can filter — which means each
line is an object with named fields, not a sentence.

structlog gives that with almost no ceremony: `log.info("fetch_complete",
location="Ankara", rows=24)` becomes a JSON line in production and a
readable coloured line in development. Same call, different rendering.
"""

from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(*, json_output: bool, level: str = "INFO") -> None:
    """Sets up structlog once, at process start."""
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
    )

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
