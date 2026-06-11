"""Recent hands endpoint for the dashboard table."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from clickhouse_connect.driver.asyncclient import AsyncClient
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..clickhouse import queries
from ..clickhouse.client import get_api_client
from .auth import require_user

router = APIRouter(prefix="/hands", tags=["analytics"])


class RecentHand(BaseModel):
    source_hand_id: str
    played_at: str
    tournament_format: str
    effective_stack_bb: int
    position: str
    result: float
    board: str


@router.get("/recent", response_model=list[RecentHand])
async def recent(
    limit: int = Query(default=50, ge=1, le=500),
    claims: dict[str, Any] = Depends(require_user),
    client: AsyncClient = Depends(get_api_client),
) -> list[RecentHand]:
    rows = await queries.recent_hands(client, UUID(str(claims["sub"])), limit)
    return [RecentHand(**r) for r in rows]
