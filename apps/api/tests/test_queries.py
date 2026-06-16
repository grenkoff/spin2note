"""Dedup membership queries must batch large id lists (ClickHouse HTTP rejects huge params)."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from spin2note_api.clickhouse import queries
from spin2note_api.clickhouse.queries import existing_hand_ids


class CountingClient:
    def __init__(self) -> None:
        self.calls = 0
        self.max_batch = 0

    async def query(self, sql: str, parameters: Any = None) -> Any:
        self.calls += 1
        self.max_batch = max(self.max_batch, len(parameters["ids"]))
        return type("R", (), {"result_rows": []})()


async def test_existing_hand_ids_batches_large_lists() -> None:
    ids = [uuid4() for _ in range(2500)]
    client = CountingClient()
    found = await existing_hand_ids(client, uuid4(), ids)  # type: ignore[arg-type]
    assert found == set()
    assert client.calls == 3  # 1000 + 1000 + 500
    assert client.max_batch <= queries._ID_BATCH


async def test_existing_hand_ids_empty() -> None:
    client = CountingClient()
    assert await existing_hand_ids(client, uuid4(), []) == set()  # type: ignore[arg-type]
    assert client.calls == 0


def test_cumulative_timeline_running_total_and_index() -> None:
    rows = [(100.0, "2026-01-01T00:00:00"), (-30.0, "2026-01-02T00:00:00"),
            (50.0, "2026-01-03T00:00:00")]
    series = queries._cumulative_timeline(rows)  # type: ignore[arg-type]
    assert [p["idx"] for p in series] == [1, 2, 3]
    assert [p["cumulative"] for p in series] == [100.0, 70.0, 120.0]


def test_cumulative_timeline_downsamples_and_keeps_last() -> None:
    rows = [(1.0, f"2026-01-01T00:00:{i:02d}") for i in range(50)]
    series = queries._cumulative_timeline(rows, max_points=10)  # type: ignore[arg-type]
    assert len(series) == 10
    # Index is monotonic and the final cumulative (sum of all 50) is preserved.
    assert [p["idx"] for p in series] == sorted(p["idx"] for p in series)
    assert series[-1]["idx"] == 50
    assert series[-1]["cumulative"] == 50.0
