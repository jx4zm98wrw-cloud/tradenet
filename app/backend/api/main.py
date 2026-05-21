"""FastAPI app entry point.

Builds the app, wires middleware in dependency-order (request-ID first so
everything downstream can log it), and exposes health probes. Real settings
(CORS, secret key, sentry DSN) come from `Settings`; defaults in
`api/settings.py` are dev-friendly.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text

from .errors import RequestIDMiddleware, register_exception_handlers
from .rate_limit import limiter
from .routes import (
    admin,
    compare,
    facets,
    gazettes,
    marks,
    search,
    stats,
    today,
    trademarks,
    watchlists,
)
from .settings import get_settings


def _init_sentry() -> None:
    settings = get_settings()
    if settings.sentry_dsn:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.env,
            traces_sample_rate=0.1 if settings.is_production else 0.0,
            send_default_pii=False,
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    from .logging_config import configure_logging

    configure_logging(get_settings().env)
    _init_sentry()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Trademark Gazette",
        version="1.0.0",
        description="NOIP Vietnam trademark gazette workbench",
        lifespan=lifespan,
        openapi_url="/openapi.json",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url=None,
    )

    # ---- Middleware (ordered: outer-most first; runs in reverse on response) ----
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    # ---- Error handlers ----
    register_exception_handlers(app)

    @app.exception_handler(RateLimitExceeded)
    async def _ratelimit(request: Request, exc: RateLimitExceeded):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": "too_many_requests",
                    "message": str(exc.detail),
                    "request_id": getattr(request.state, "request_id", None),
                    "details": None,
                }
            },
        )

    app.state.limiter = limiter

    # ---- Routes ----
    app.include_router(gazettes.router)
    app.include_router(trademarks.router)
    app.include_router(stats.router)
    app.include_router(facets.router)
    app.include_router(today.router)
    app.include_router(search.router)
    app.include_router(marks.router)
    app.include_router(compare.router)
    app.include_router(watchlists.router)
    app.include_router(admin.router)

    # ---- Health probes ----
    @app.get("/health", tags=["meta"])
    async def health() -> dict:
        """Liveness — does the process answer HTTP? No external deps checked."""
        return {"status": "ok"}

    @app.get("/health/ready", tags=["meta"])
    async def ready() -> dict:
        """Readiness — DB + Redis reachable? Used by orchestrators to gate traffic."""
        from .db import engine

        deps: dict[str, str] = {}
        # DB
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            deps["database"] = "ok"
        except Exception as e:
            deps["database"] = f"down: {type(e).__name__}"
        # Redis
        try:
            from redis import Redis

            r = Redis.from_url(get_settings().redis_url, socket_timeout=2)
            r.ping()
            deps["redis"] = "ok"
        except Exception as e:
            deps["redis"] = f"down: {type(e).__name__}"

        all_ok = all(v == "ok" for v in deps.values())
        return {"status": "ok" if all_ok else "degraded", "deps": deps}

    # ---- Prometheus metrics (env-toggled) ----
    if settings.enable_prometheus:
        from prometheus_fastapi_instrumentator import Instrumentator

        Instrumentator(should_group_status_codes=True).instrument(app).expose(
            app, endpoint="/metrics", include_in_schema=False
        )

    return app


app = create_app()
