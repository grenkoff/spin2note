"""Worker routing: hand-history files -> hands/players/actions; summary files -> tournaments."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest

pytest.importorskip("hh_parser")

from spin2note_api.clickhouse import ClickHouseBatcher  # noqa: E402
from spin2note_api.worker import handle_raw  # noqa: E402

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


async def test_routes_hand_history() -> None:
    b = CollectBatcher()
    await handle_raw((TESTDATA / "3max/sample.txt").read_text(), USER, b)
    assert len(b.rows["hands"]) == 2
    assert b.rows["hand_players"]
    assert b.rows["actions"]
    assert "tournaments" not in b.rows


async def test_routes_summary() -> None:
    b = CollectBatcher()
    await handle_raw((TESTDATA / "summary/sample.txt").read_text(), USER, b)
    assert len(b.rows["tournaments"]) == 1
    assert "hands" not in b.rows
