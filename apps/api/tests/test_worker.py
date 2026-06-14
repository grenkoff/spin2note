"""Worker routing + input dedup. The ClickHouse client is stubbed (no DB needed)."""

from __future__ import annotations

import gzip
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

pytest.importorskip("hh_parser")

from spin2note_api.clickhouse import ClickHouseBatcher  # noqa: E402
from spin2note_api.worker import _decode_object, handle_raw  # noqa: E402

TESTDATA = Path(__file__).resolve().parents[3] / "testdata"
USER = UUID("00000000-0000-0000-0000-000000000009")


class CollectBatcher(ClickHouseBatcher):
    def __init__(self) -> None:
        self.rows: dict[str, list] = {}

        async def _insert(table: str, rows) -> None:  # pragma: no cover - not used
            self.rows.setdefault(table, []).extend(rows)

        super().__init__(_insert, max_rows=1, max_interval_seconds=3600)

    async def submit(self, table: str, row) -> None:  # type: ignore[override]
        self.rows.setdefault(table, []).append(row)

    async def submit_block(self, table: str, rows) -> None:  # type: ignore[override]
        if not rows:
            return
        self.rows.setdefault(table, []).extend(rows)


class FakeCH:
    """Stub ClickHouse client returning a fixed set of already-existing ids."""

    def __init__(self, hands: set | None = None, tournaments: set | None = None) -> None:
        self._hands = hands or set()
        self._tournaments = tournaments or set()

    async def query(self, sql: str, parameters: Any = None) -> Any:
        rows = [(x,) for x in (self._hands if "FROM hands" in sql else self._tournaments)]
        return type("R", (), {"result_rows": rows})()


async def test_routes_hand_history() -> None:
    b = CollectBatcher()
    counts = await handle_raw((TESTDATA / "3max/sample.txt").read_text(), USER, b, FakeCH())
    assert len(b.rows["hands"]) == 2
    assert b.rows["hand_players"] and b.rows["actions"]
    assert "tournaments" not in b.rows
    assert counts.hands_added == 2 and counts.hands_skipped == 0


async def test_routes_summary() -> None:
    b = CollectBatcher()
    counts = await handle_raw((TESTDATA / "summary/sample.txt").read_text(), USER, b, FakeCH())
    assert len(b.rows["tournaments"]) == 1
    assert "hands" not in b.rows
    assert counts.tournaments_added == 1 and counts.tournaments_skipped == 0


async def test_dedup_skips_existing_hands() -> None:
    raw = (TESTDATA / "3max/sample.txt").read_text()
    # First import: nothing exists yet -> both hands added.
    first = CollectBatcher()
    await handle_raw(raw, USER, first, FakeCH())
    seen_ids = {row[0] for row in first.rows["hands"]}  # row[0] = hand_id (column order)
    assert len(seen_ids) == 2

    # Re-import: those hand_ids already exist -> all skipped, nothing submitted.
    second = CollectBatcher()
    counts = await handle_raw(raw, USER, second, FakeCH(hands=seen_ids))
    assert counts.hands_added == 0
    assert counts.hands_skipped == 2
    assert "hands" not in second.rows


def test_decode_object_handles_gzip_and_plain() -> None:
    text = "Poker Hand #SG1: ...\n"
    assert _decode_object("a/b/c.txt", text.encode()) == text
    assert _decode_object("a/b/c.txt.gz", gzip.compress(text.encode())) == text
