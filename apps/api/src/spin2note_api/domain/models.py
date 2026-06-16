"""Parsed hand-history entities.

These Pydantic models are the contract between the Rust ``hh_parser`` output (mapped in
``parser.mapping``) and the ClickHouse repositories/batcher. Field order does not matter here;
the physical column order lives in ``clickhouse.client.TABLE_COLUMNS``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from .enums import ActionType, Street, TournamentFormat


def _now() -> datetime:
    return datetime.now(UTC)


class Action(BaseModel):
    hand_id: UUID
    user_id: UUID
    tournament_format: TournamentFormat
    effective_stack_bb: int
    street: Street
    seat: int
    action_index: int
    action_type: ActionType
    amount: float = 0.0
    pot_before: float = 0.0
    to_amount: float = 0.0
    all_in: bool = False


class HandPlayer(BaseModel):
    hand_id: UUID
    user_id: UUID
    tournament_format: TournamentFormat
    effective_stack_bb: int
    seat: int
    is_hero: bool = False
    villain_hash: int = 0  # FNV-1a 64 of the GG opponent id; 0 for hero
    position: str = ""
    starting_stack: float = 0.0
    hole_cards: str = ""
    won: float = 0.0
    result: float = 0.0
    chip_ev: float = 0.0  # all-in-adjusted result; == result unless a 2-way all-in reached showdown
    parsed_at: datetime = Field(default_factory=_now)


class Hand(BaseModel):
    hand_id: UUID
    user_id: UUID
    tournament_format: TournamentFormat
    effective_stack_bb: int
    source_hand_id: str
    tournament_id: str
    level: int = 0
    button_seat: int = 0
    played_at: datetime
    multiplier: float = 0.0  # filled from the tournament summary, not the hand history
    small_blind: float = 0.0
    big_blind: float = 0.0
    board: str = ""
    pot: float = 0.0
    rake: float = 0.0
    parsed_at: datetime = Field(default_factory=_now)

    players: list[HandPlayer] = Field(default_factory=list)
    actions: list[Action] = Field(default_factory=list)


class Tournament(BaseModel):
    tournament_id: str
    user_id: UUID
    name: str = ""
    buy_in: float = 0.0
    currency: str = ""
    players: int = 0
    prize_pool: float = 0.0
    multiplier: int = 0
    started_at: datetime | None = None
    hero_place: int = 0
    # hero's actual cash won (from summary finishes); net $ = hero_prize - buy_in
    hero_prize: float = 0.0
    parsed_at: datetime = Field(default_factory=_now)
