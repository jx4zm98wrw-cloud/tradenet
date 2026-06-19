"""FastAPI app entry point.

Builds the app, wires middleware in dependency-order (request-ID first so
everything downstream can log it), and exposes health probes. Real settings
(CORS, secret key, sentry DSN) come from `Settings`; defaults in
`api/settings.py` are dev-friendly.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text

from .errors import RequestIDMiddleware, register_exception_handlers
from .rate_limit import limiter
from .routes import (
    admin,
    compare,
    domestic_sweep,
    facets,
    gazettes,
    madrid_sweep,
    marks,
    search,
    stats,
    today,
    trademarks,
    watchlists,
)
from .routes import (
    auth as auth_routes,
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
    # Explicit allow_headers (not ["*"]) — combined with allow_credentials=True,
    # a wildcard headers list lets any whitelisted origin send arbitrary headers
    # (including Authorization, Content-Type overrides, custom auth headers).
    # Listing only what the frontend actually sends shrinks the cross-origin
    # attack surface without breaking legitimate usage. If you add a new
    # client header (e.g. X-Client-Version), add it here explicitly.
    #
    # CSRF posture: when cookie-based auth lands (sprint 1 C1), the cookie
    # must be `SameSite=Lax` + `Secure` + `HttpOnly`, AND state-changing
    # endpoints (POST/PUT/DELETE) must validate a CSRF token submitted as
    # a header (double-submit-cookie pattern). The combination of
    # allow_credentials=True + same-site cookies + CSRF header is the
    # standard browser-app defense.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=[
            "Accept",
            "Accept-Language",
            "Authorization",
            "Content-Type",
            "X-Request-ID",
            "X-CSRF-Token",  # reserved for future CSRF wiring (C1)
        ],
        expose_headers=["X-Request-ID"],
        max_age=600,  # cache preflight 10 minutes — reduces OPTIONS chatter
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
    app.include_router(auth_routes.router)
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
    app.include_router(madrid_sweep.router)
    app.include_router(domestic_sweep.router)

    # ---- Static files (extracted trademark logos) ----
    # Served under /static/image/<year>/<pdf_stem>/<id>.png. Trademark rows
    # carry logo_path relative to <data_dir>/image, e.g. "2026/A_T2_2026/4-2026-00001.png".
    # The image/ directory may be absent in fresh checkouts — mount lazily.
    startup_log = logging.getLogger("api.startup")
    image_root = settings.data_dir / "image"
    if image_root.is_dir():
        app.mount("/static/image", StaticFiles(directory=image_root), name="static-image")
        # Smoke signal at boot: if the mount succeeds but contains zero PNGs,
        # /static/image/* will return 404 for every logo URL the API hands
        # the frontend. Logging the count makes the "no logos extracted yet"
        # case visible in startup logs instead of silently 404-ing later.
        png_count = sum(1 for _ in image_root.rglob("*.png"))
        startup_log.info("Mounted /static/image from %s (%d PNGs found)", image_root, png_count)
    else:
        startup_log.info("No image/ directory at %s — /static/image not mounted", image_root)

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
