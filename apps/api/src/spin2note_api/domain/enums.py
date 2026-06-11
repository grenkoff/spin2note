"""Shared domain enumerations.

Values mirror the ClickHouse `Enum8` definitions so Python and the DB agree on the
integer encoding.
"""

from __future__ import annotations

from enum import IntEnum, StrEnum


class TournamentFormat(IntEnum):
    """Spin&Gold table size. Integer values match ClickHouse Enum8('3max'=3,'6max'=6)."""

    THREE_MAX = 3
    SIX_MAX = 6

    @property
    def label(self) -> str:
        return "3max" if self is TournamentFormat.THREE_MAX else "6max"


class Street(StrEnum):
    PREFLOP = "preflop"
    FLOP = "flop"
    TURN = "turn"
    RIVER = "river"


class ActionType(StrEnum):
    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    BET = "bet"
    RAISE = "raise"
    ALL_IN = "all_in"
    POST = "post"
