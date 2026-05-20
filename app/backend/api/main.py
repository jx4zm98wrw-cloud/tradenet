"""FastAPI app entry point."""
from __future__ import annotations
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import admin, compare, facets, gazettes, marks, search, stats, today, trademarks, watchlists


def create_app() -> FastAPI:
    app = FastAPI(title="Trademark Gazette", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],  # Next.js dev
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
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

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
