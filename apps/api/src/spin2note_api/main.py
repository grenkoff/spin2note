"""FastAPI application entrypoint.

Exposes an auto-generated, interactive OpenAPI 3.1 spec (CLAUDE.md §3) at /docs and
/openapi.json — this is what `/generate-client` consumes to build the typed frontend client.
"""

from __future__ import annotations

import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .config import get_settings
from .domain.ids import new_id
from .http import hands, health, imports, stats
from .ingest import router as ingest_router
from .logging_config import bind_log_context, configure_logging, reset_log_context

logger = logging.getLogger("spin2note.http")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings)
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

    @app.middleware("http")
    async def log_requests(request: Request, call_next):  # type: ignore[no-untyped-def]
        reset_log_context()
        request_id = request.headers.get("x-request-id") or str(new_id())
        bind_log_context(request_id=request_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("unhandled error: %s %s", request.method, request.url.path)
            raise
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "%s %s -> %d (%.0fms)",
            request.method, request.url.path, response.status_code, elapsed_ms,
        )
        response.headers["x-request-id"] = request_id
        return response
    app.include_router(health.router)
    app.include_router(ingest_router.router)
    app.include_router(stats.router)
    app.include_router(hands.router)
    app.include_router(imports.router)
    return app


app = create_app()
