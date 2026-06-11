"""Parsed hand-history entities.

These Pydantic models are the structured output the Rust `hh_parser` produces (after the
Python wrapper normalises them) and the input the ClickHouse batcher consumes. Keeping them
here means the parser, pipeline and repositories share one contract.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from .enums import ActionType, Street, TournamentFormat
from .ids import new_id


def _quantize_stack_bb(effective_stack_bb: float) -> int:
    """Quantize effective stack (in big blinds) to UInt16 BB*10 for the sort key."""
    return max(0, min(65535, round(effective_stack_bb * 10)))


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


class HandPlayer(BaseModel):
    hand_id: UUID
    user_id: UUID
    tournament_format: TournamentFormat
    effective_stack_bb: int
    seat: int
    is_hero: bool = False
    villain_hash: int = 0  # sipHash64(player_name); 0 for hero
    position: str = ""
    starting_stack: float = 0.0
    result: float = 0.0


class Hand(BaseModel):
    hand_id: UUID = Field(default_factory=new_id)
    user_id: UUID
    tournament_format: TournamentFormat
    effective_stack_bb: int
    played_at: datetime
    multiplier: float = 0.0
    small_blind: float = 0.0
    big_blind: float = 0.0
    board: str = ""
    pot: float = 0.0
    parsed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    players: list[HandPlayer] = Field(default_factory=list)
    actions: list[Action] = Field(default_factory=list)

    @classmethod
    def quantize_stack(cls, effective_stack_bb: float) -> int:
        return _quantize_stack_bb(effective_stack_bb)
