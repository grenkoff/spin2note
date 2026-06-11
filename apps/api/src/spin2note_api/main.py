"""FastAPI application entrypoint.

Exposes an auto-generated, interactive OpenAPI 3.1 spec (CLAUDE.md §3) at /docs and
/openapi.json — this is what `/generate-client` consumes to build the typed frontend client.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .config import get_settings
from .http import hands, health, stats
from .ingest import router as ingest_router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Spin&Gold Analytics API",
        version=__version__,
        description="Hand-history ingestion, parsing and Spin&Gold analytics.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(ingest_router.router)
    app.include_router(stats.router)
    app.include_router(hands.router)
    return app


app = create_app()
