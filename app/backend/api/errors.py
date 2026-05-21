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

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware


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
