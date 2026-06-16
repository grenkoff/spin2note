"""Read-only analytics endpoints consumed by the dashboard."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from clickhouse_connect.driver.asyncclient import AsyncClient
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..clickhouse import queries
from ..clickhouse.client import get_api_client
from .auth import require_user

router = APIRouter(prefix="/stats", tags=["analytics"])


class StackBucket(BaseModel):
    effective_stack_bb: int
    hands: int
    result: float
    winrate: float


class TimelinePoint(BaseModel):
    idx: int          # sequential hand# (chips) or tournament# (dollars)
    at: str           # ISO timestamp
    cumulative: float  # running total


class Overview(BaseModel):
    total_hands: int
    total_tournaments: int
    avg_multiplier: float
    by_stack: list[StackBucket]
    chips_timeline: list[TimelinePoint]
    dollars_timeline: list[TimelinePoint]


def _user_id(claims: dict[str, Any]) -> UUID:
    return UUID(str(claims["sub"]))


@router.get("/overview", response_model=Overview)
async def overview(
    fmt: str | None = Query(default=None, pattern="^(3max|6max)$", alias="format"),
    claims: dict[str, Any] = Depends(require_user),
    client: AsyncClient = Depends(get_api_client),
) -> Overview:
    data = await queries.overview(client, _user_id(claims), fmt)
    return Overview(**data)
