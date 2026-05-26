"""Structured logging — structlog → JSON in non-TTY environments, pretty
console output in dev TTY. Hooks request_id into the context so every log
line in the request lifecycle carries the correlation ID emitted by
`RequestIDMiddleware`.

Call `configure_logging()` once at process start (done from `main.py`'s
lifespan). After that, all `structlog.get_logger()` calls produce structured
records; standard-library `logging.*` calls are also captured and routed
through the same pipeline.
"""

from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(env: str = "development") -> None:
    is_prod = env.lower() in ("production", "staging")

    # Explicit Processor annotations: without them, mypy infers list[object]
    # from the heterogeneous-looking processor list, and the renderer type
    # gets pinned to whichever branch runs first.
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: structlog.types.Processor
    if is_prod or not sys.stderr.isatty():
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )

    # Route stdlib logging (uvicorn, sqlalchemy, etc.) through the same handler.
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_StdlibRoutingFormatter(shared_processors, renderer))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


class _StdlibRoutingFormatter(logging.Formatter):
    """Forwards stdlib LogRecords into the same structlog renderer."""

    def __init__(self, processors, renderer):
        super().__init__()
        self._proc = structlog.stdlib.ProcessorFormatter(
            processors=[*processors, renderer],
            foreign_pre_chain=[
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso", utc=True),
            ],
        )

    def format(self, record: logging.LogRecord) -> str:
        return self._proc.format(record)


def bind_request_context(request_id: str | None) -> None:
    """Bind a request_id to the logging context for the duration of a request."""
    structlog.contextvars.bind_contextvars(request_id=request_id)


def clear_request_context() -> None:
    structlog.contextvars.clear_contextvars()
