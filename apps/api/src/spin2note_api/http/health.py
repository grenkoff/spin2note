"""Liveness/readiness endpoint."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from .. import __version__

router = APIRouter(tags=["system"])


class Health(BaseModel):
    status: str
    version: str


@router.get("/health", response_model=Health)
async def health() -> Health:
    return Health(status="ok", version=__version__)
