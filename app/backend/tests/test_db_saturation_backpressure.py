"""DB-saturation → graceful 503 backpressure (not a 500-storm).

Root cause (load test, concurrency 100): the search API has no admission
control, so when the DB saturates the driver/pool exception propagates
unhandled and FastAPI maps it to a blank 500. Two concrete saturation
classes were observed end-to-end:

  - ``sqlalchemy.exc.TimeoutError`` — QueuePool acquire timeout (production
    pool exhausted).
  - ``asyncpg.exceptions.TooManyConnectionsError`` — Postgres ``max_connections``
    ceiling hit (raw, connect-phase; the dev/NullPool path).

`register_exception_handlers` must convert BOTH into ``503 Service
Unavailable`` + a ``Retry-After`` header so clients back off instead of
hammering a saturated service. A generic exception must STILL yield 500
(the catch-all is unchanged).
"""

from __future__ import annotations

import asyncpg.exceptions
import pytest
import pytest_asyncio
import sqlalchemy.exc
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.errors import RequestIDMiddleware, register_exception_handlers


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)
    register_exception_handlers(app)

    @app.get("/boom/pool-timeout")
    async def _pool_timeout() -> dict:
        raise sqlalchemy.exc.TimeoutError(
            "QueuePool limit of size 20 overflow 10 reached, connection timed out"
        )

    @app.get("/boom/too-many-connections")
    async def _too_many() -> dict:
        raise asyncpg.exceptions.TooManyConnectionsError("sorry, too many clients already")

    @app.get("/boom/generic")
    async def _generic() -> dict:
        raise RuntimeError("a real bug, not saturation")

    return app


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    # raise_app_exceptions=False: Starlette's ServerErrorMiddleware (which owns
    # the bare Exception->500 handler) re-raises after sending the response, so
    # we must let the transport return the 500 instead of propagating it. The
    # specific saturation handlers go through ExceptionMiddleware (no re-raise).
    transport = ASGITransport(app=_app(), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/boom/pool-timeout", "/boom/too-many-connections"])
async def test_saturation_returns_503_with_retry_after(client: AsyncClient, path: str) -> None:
    resp = await client.get(path)
    assert resp.status_code == 503, f"{path} should backpressure with 503, got {resp.status_code}"
    # Retry-After present and a positive integer number of seconds.
    retry_after = resp.headers.get("Retry-After")
    assert retry_after is not None, "503 backpressure must include a Retry-After header"
    assert int(retry_after) > 0
    body = resp.json()
    assert body["error"]["code"] == "service_unavailable"
    # Error envelope is preserved (request id echoed).
    assert body["error"]["request_id"]


@pytest.mark.asyncio
async def test_generic_exception_still_500(client: AsyncClient) -> None:
    """Regression guard: only saturation maps to 503; real bugs stay 500."""
    resp = await client.get("/boom/generic")
    assert resp.status_code == 500
    assert "Retry-After" not in resp.headers
    assert resp.json()["error"]["code"] == "internal_error"
