"""Consistent error envelope.

All errors leaving the API have the shape:
    { "error": { "code": str, "message": str, "request_id": str | null,
                 "details": Any | null } }

Wired via:
- `register_exception_handlers(app)` — converts HTTPException + Pydantic
  ValidationError + uncaught Exception into the envelope.
- `RequestIDMiddleware` — assigns a UUID per request, exposes via
  `request.state.request_id`, echoes in `X-Request-ID` response header.

Client code: read the `request_id` from the response body or header when
reporting issues to support.
"""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy.exc
from asyncpg.exceptions import TooManyConnectionsError
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

# Graceful-backpressure retry hint (seconds). DB saturation clears in well
# under a second once in-flight queries drain, so a small value keeps healthy
# clients responsive while still telling load generators / proxies to back off.
SATURATION_RETRY_AFTER_SECONDS = 1


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        from .logging_config import bind_request_context, clear_request_context

        req_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = req_id
        bind_request_context(req_id)
        try:
            response = await call_next(request)
        finally:
            clear_request_context()
        response.headers["X-Request-ID"] = req_id
        return response


def _envelope(
    code: str, message: str, *, request_id: str | None = None, details: Any | None = None
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
            "details": details,
        }
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(
                code=_code_for_status(exc.status_code),
                message=str(exc.detail) if exc.detail else "Request failed",
                request_id=getattr(request.state, "request_id", None),
            ),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_envelope(
                code="validation_error",
                message="Request payload failed validation",
                request_id=getattr(request.state, "request_id", None),
                details=exc.errors(),
            ),
        )

    # --- DB saturation -> graceful backpressure (503 + Retry-After) ---------
    # Under high concurrency the DB layer saturates and raises one of two
    # operational (NOT bug) exceptions: a QueuePool acquire timeout
    # (`sqlalchemy.exc.TimeoutError`) or a Postgres connection-ceiling refusal
    # (`asyncpg ... TooManyConnectionsError`, raw on the NullPool connect path).
    # Left to the generic handler below these become a 500-storm; they mean
    # "at capacity, retry shortly", which is exactly HTTP 503 + Retry-After.
    # Registering handlers for these specific classes takes precedence over the
    # bare-Exception handler (Starlette matches by closest type in the MRO).
    def _saturation(request: Request) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=_envelope(
                code="service_unavailable",
                message="The service is temporarily at capacity. Please retry shortly.",
                request_id=getattr(request.state, "request_id", None),
            ),
            headers={"Retry-After": str(SATURATION_RETRY_AFTER_SECONDS)},
        )

    @app.exception_handler(sqlalchemy.exc.TimeoutError)
    async def _pool_timeout(request: Request, exc: sqlalchemy.exc.TimeoutError):
        return _saturation(request)

    @app.exception_handler(TooManyConnectionsError)
    async def _too_many_connections(request: Request, exc: TooManyConnectionsError):
        return _saturation(request)

    @app.exception_handler(sqlalchemy.exc.OperationalError)
    async def _operational(request: Request, exc: sqlalchemy.exc.OperationalError):
        # Defensive: in code paths where SQLAlchemy WRAPS the driver error
        # (e.g. a pre-ping reconnect), the connection-ceiling refusal surfaces
        # as OperationalError(orig=TooManyConnectionsError). Treat only that as
        # backpressure; re-raise anything else so it falls through to a 500.
        if isinstance(getattr(exc, "orig", None), TooManyConnectionsError):
            return _saturation(request)
        raise exc

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        # Don't leak internals. The real stack trace goes to logs + Sentry.
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_envelope(
                code="internal_error",
                message="An unexpected error occurred",
                request_id=getattr(request.state, "request_id", None),
            ),
        )


_STATUS_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    413: "payload_too_large",
    422: "validation_error",
    429: "too_many_requests",
    500: "internal_error",
    501: "not_implemented",
    503: "service_unavailable",
}


def _code_for_status(status_code: int) -> str:
    return _STATUS_CODES.get(status_code, "http_error")
