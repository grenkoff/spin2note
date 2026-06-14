"""Import-report endpoint — aggregated added/skipped counts for an upload session."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..db.imports import session_summary
from .auth import require_user

router = APIRouter(prefix="/imports", tags=["ingest"])


class ImportSummary(BaseModel):
    chunks: int
    done: int
    failed: int
    pending: int
    complete: bool
    hands_added: int
    hands_skipped: int
    tournaments_added: int
    tournaments_skipped: int


@router.get("/{session_id}", response_model=ImportSummary)
async def import_summary(
    session_id: UUID,
    claims: dict[str, Any] = Depends(require_user),
) -> ImportSummary:
    data = await session_summary(session_id, UUID(str(claims["sub"])))
    return ImportSummary(**data)
