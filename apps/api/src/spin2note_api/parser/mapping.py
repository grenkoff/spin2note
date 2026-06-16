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


# --- Fast path: build column-ordered tuples directly (no Pydantic) for native inserts. ---
# Tuple order MUST match clickhouse.client.TABLE_COLUMNS for each table.

_EPOCH = datetime(1970, 1, 1)


def build_chunk_rows(
    hands: list[dict[str, Any]], user_id: UUID, parsed_at: datetime
) -> dict[str, list[tuple[Any, ...]]]:
    """Project parsed hand dicts into column-ordered row tuples for hands/hand_players/actions."""
    hand_rows: list[tuple[Any, ...]] = []
    player_rows: list[tuple[Any, ...]] = []
    action_rows: list[tuple[Any, ...]] = []
    for h in hands:
        hid = UUID(h["hand_id"])  # deterministic id computed in Rust
        fmt = h["format"]  # Enum8 label ("3max"/"6max")
        eff = int(h["effective_stack_bb"])
        played = _dt(h["played_at"]) or _EPOCH
        hand_rows.append((
            hid, user_id, fmt, eff, h["source_hand_id"], h["tournament_id"], h["level"],
            h["button_seat"], played, 0.0, h["small_blind"], h["big_blind"], h["board"],
            h["pot"], h["rake"], parsed_at,
        ))
        for p in h["players"]:
            player_rows.append((
                hid, user_id, fmt, eff, p["seat"], int(p["is_hero"]), p["villain_hash"],
                p["position"], p["starting_stack"], p["hole_cards"], p["won"], p["result"],
                parsed_at,
            ))
        for a in h["actions"]:
            action_rows.append((
                hid, user_id, fmt, eff, a["street"], a["seat"], a["action_index"],
                a["action_type"], a["amount"], 0.0, a["to_amount"], int(a["all_in"]),
            ))
    return {"hands": hand_rows, "hand_players": player_rows, "actions": action_rows}


def _hero_prize(summary: dict[str, Any]) -> float:
    """Hero's actual cash won, summed from the summary finish lines ("Nrd : Hero, $X")."""
    return float(sum(f["prize"] for f in summary.get("finishes", []) if f["name"] == "Hero"))


def build_tournament_rows(
    summaries: list[dict[str, Any]], user_id: UUID, parsed_at: datetime
) -> list[tuple[Any, ...]]:
    return [
        (
            s["tournament_id"], user_id, s["name"], s["buy_in"], s["currency"], s["players"],
            s["prize_pool"], s["multiplier"], _dt(s["started_at"]), s["hero_place"],
            _hero_prize(s), parsed_at,
        )
        for s in summaries
    ]


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
        hero_prize=_hero_prize(summary),
    )
