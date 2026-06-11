"""FastAPI application entrypoint.

Exposes an auto-generated, interactive OpenAPI 3.1 spec (CLAUDE.md §3) at /docs and
/openapi.json — this is what `/generate-client` consumes to build the typed frontend client.
"""

from __future__ import annotations

from fastapi import FastAPI

from . import __version__
from .http import health
from .ingest import router as ingest_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Spin&Gold Analytics API",
        version=__version__,
        description="Hand-history ingestion, parsing and Spin&Gold analytics.",
    )
    app.include_router(health.router)
    app.include_router(ingest_router.router)
    return app


app = create_app()
