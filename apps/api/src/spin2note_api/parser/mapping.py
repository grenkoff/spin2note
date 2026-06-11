"""Map raw ``hh_parser`` dicts into domain models.

The hero (named "Hero" in GG exports) is the uploading user, so ``user_id`` is injected from
the pipeline context rather than read from the file. ``hand_id`` is derived deterministically
from the natural GG key so re-ingesting the same file dedups in ClickHouse (ReplacingMergeTree).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid5

from ..domain.enums import ActionType, Street, TournamentFormat
from ..domain.models import Action, Hand, HandPlayer, Tournament

# Fixed namespace for deterministic hand ids (uuid5). Do not change — it would re-key history.
_HAND_NS = UUID("6f9b2a1e-0c3d-5e4f-8a7b-1d2c3e4f5a6b")

_FORMAT = {"3max": TournamentFormat.THREE_MAX, "6max": TournamentFormat.SIX_MAX}


def deterministic_hand_id(tournament_id: str, source_hand_id: str) -> UUID:
    return uuid5(_HAND_NS, f"{tournament_id}:{source_hand_id}")


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def build_hand(parsed: dict[str, Any], user_id: UUID) -> Hand:
    fmt = _FORMAT[parsed["format"]]
    eff = int(parsed["effective_stack_bb"])
    hand_id = deterministic_hand_id(parsed["tournament_id"], parsed["source_hand_id"])
    played_at = _dt(parsed["played_at"]) or datetime(1970, 1, 1)

    players = [
        HandPlayer(
            hand_id=hand_id,
            user_id=user_id,
            tournament_format=fmt,
            effective_stack_bb=eff,
            seat=p["seat"],
            is_hero=p["is_hero"],
            villain_hash=p["villain_hash"],
            position=p["position"],
            starting_stack=p["starting_stack"],
            hole_cards=p["hole_cards"],
            won=p["won"],
            result=p["result"],
        )
        for p in parsed["players"]
    ]
    actions = [
        Action(
            hand_id=hand_id,
            user_id=user_id,
            tournament_format=fmt,
            effective_stack_bb=eff,
            street=Street(a["street"]),
            seat=a["seat"],
            action_index=a["action_index"],
            action_type=ActionType(a["action_type"]),
            amount=a["amount"],
            to_amount=a["to_amount"],
            all_in=a["all_in"],
        )
        for a in parsed["actions"]
    ]
    return Hand(
        hand_id=hand_id,
        user_id=user_id,
        tournament_format=fmt,
        effective_stack_bb=eff,
        source_hand_id=parsed["source_hand_id"],
        tournament_id=parsed["tournament_id"],
        level=parsed["level"],
        button_seat=parsed["button_seat"],
        played_at=played_at,
        small_blind=parsed["small_blind"],
        big_blind=parsed["big_blind"],
        board=parsed["board"],
        pot=parsed["pot"],
        rake=parsed["rake"],
        players=players,
        actions=actions,
    )


def build_hands(parsed_list: list[dict[str, Any]], user_id: UUID) -> list[Hand]:
    return [build_hand(p, user_id) for p in parsed_list]


def build_tournament(summary: dict[str, Any], user_id: UUID) -> Tournament:
    return Tournament(
        tournament_id=summary["tournament_id"],
        user_id=user_id,
        name=summary["name"],
        buy_in=summary["buy_in"],
        currency=summary["currency"],
        players=summary["players"],
        prize_pool=summary["prize_pool"],
        multiplier=summary["multiplier"],
        started_at=_dt(summary["started_at"]),
        hero_place=summary["hero_place"],
    )
