"""Parser + domain mapping tests against committed GG-format fixtures.

Requires the compiled ``hh_parser`` extension (CI builds it via maturin before pytest).
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest

pytest.importorskip("hh_parser")

from spin2note_api.domain.enums import TournamentFormat  # noqa: E402
from spin2note_api.parser import (  # noqa: E402
    build_hands,
    build_tournament,
    detect_format,
    deterministic_hand_id,
    parse,
    parse_summary,
)

TESTDATA = Path(__file__).resolve().parents[3] / "testdata"
USER = UUID("00000000-0000-0000-0000-000000000009")


def _read(rel: str) -> str:
    return (TESTDATA / rel).read_text()


def test_detect_format() -> None:
    assert detect_format(_read("3max/sample.txt")) == "3max"
    assert detect_format(_read("6max/sample.txt")) == "6max"


def test_three_max_allin_showdown_mapping() -> None:
    hands = build_hands(parse(_read("3max/sample.txt")), USER)
    assert len(hands) == 2

    h = hands[0]
    assert h.tournament_format is TournamentFormat.THREE_MAX
    assert h.effective_stack_bb == 150  # 15bb
    assert h.user_id == USER
    assert h.hand_id == deterministic_hand_id(h.tournament_id, h.source_hand_id)

    hero = next(p for p in h.players if p.is_hero)
    assert hero.position == "SB"
    assert hero.hole_cards == "2h Ah"
    assert hero.result == -300.0
    assert hero.villain_hash == 0

    winner = next(p for p in h.players if p.position == "BB")
    assert winner.won == 600.0
    assert winner.result == 300.0
    assert winner.villain_hash != 0

    # Conservation: net result sums to ~0 with zero rake.
    assert abs(sum(p.result for p in h.players)) < 1e-6


def test_actions_carry_streets_and_allin_flag() -> None:
    hands = build_hands(parse(_read("3max/sample.txt")), USER)
    actions = hands[0].actions
    assert any(a.all_in for a in actions)
    assert {a.street.value for a in actions} >= {"preflop"}


def test_six_max_positions() -> None:
    h = build_hands(parse(_read("6max/sample.txt")), USER)[0]
    assert h.tournament_format is TournamentFormat.SIX_MAX
    positions = {p.position for p in h.players}
    assert positions == {"BTN", "SB", "BB", "UTG", "HJ", "CO"}


def test_rust_hand_id_matches_python() -> None:
    # The Rust parser computes hand_id (uuid5); it must equal the Python derivation, or dedup
    # would key differently between the two.
    for raw in (_read("3max/sample.txt"), _read("6max/sample.txt")):
        for h in parse(raw):
            expected = deterministic_hand_id(h["tournament_id"], h["source_hand_id"])
            assert UUID(h["hand_id"]) == expected


def test_deterministic_hand_id_is_stable() -> None:
    a = deterministic_hand_id("900000001", "SG3000000001")
    b = deterministic_hand_id("900000001", "SG3000000001")
    c = deterministic_hand_id("900000001", "SG3000000002")
    assert a == b
    assert a != c


def test_summary_mapping() -> None:
    summary = parse_summary(_read("summary/sample.txt"))
    assert summary is not None
    t = build_tournament(summary, USER)
    assert t.tournament_id == "900000001"
    assert t.buy_in == 0.25
    assert t.prize_pool == 0.75
    assert t.multiplier == 3
    assert t.players == 3
    assert t.hero_place == 3
    assert t.hero_prize == 0.0  # finished 3rd, "$0"


def test_hero_prize_from_winning_summary() -> None:
    # 6-max, Hero 1st for $4 on a $1 buy-in — prize pool is $6, so NOT winner-take-all:
    # the real parsed prize is required for correct $ P&L.
    raw = (
        "Tournament #283232820, Spin&Gold #11, Hold'em No Limit\n"
        "Buy-in: $1\n6 Players\nTotal Prize Pool: $6\n"
        "Tournament started 2026/05/07 03:14:26\n"
        "1st : Hero, $4\nYou finished in 1st place.\n"
    )
    summary = parse_summary(raw)
    assert summary is not None
    t = build_tournament(summary, USER)
    assert t.buy_in == 1.0
    assert t.hero_prize == 4.0  # net $ = 4 - 1 = +3


def test_build_tournament_rows_matches_table_columns() -> None:
    from datetime import datetime

    from spin2note_api.clickhouse.client import TABLE_COLUMNS
    from spin2note_api.parser import build_tournament_rows

    summary = parse_summary(_read("summary/sample.txt"))
    assert summary is not None
    rows = build_tournament_rows([summary], USER, datetime(2026, 1, 1))
    # Tuple arity is the contract with TABLE_COLUMNS; hero_prize sits before parsed_at.
    assert len(rows[0]) == len(TABLE_COLUMNS["tournaments"])
    assert rows[0][TABLE_COLUMNS["tournaments"].index("hero_prize")] == 0.0
