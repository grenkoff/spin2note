"""Batcher contract: blocks of >= 1000 rows, never single-row inserts (CLAUDE.md §2.2)."""

from __future__ import annotations

import pytest

from spin2note_api.clickhouse import ClickHouseBatcher


class InsertSpy:
    def __init__(self) -> None:
        self.batches: list[tuple[str, int]] = []

    async def __call__(self, table: str, rows) -> None:
        self.batches.append((table, len(rows)))

    @property
    def sizes(self) -> list[int]:
        return [n for _, n in self.batches]

    @property
    def total(self) -> int:
        return sum(self.sizes)


async def test_size_triggered_blocks_are_full_and_lossless() -> None:
    spy = InsertSpy()
    # Large interval so only the size trigger fires during submit.
    batcher = ClickHouseBatcher(spy, max_rows=1000, max_interval_seconds=3600)

    for i in range(2500):
        await batcher.submit("actions", {"i": i})

    # Two full blocks flushed mid-stream; 500 still buffered.
    assert spy.sizes == [1000, 1000]

    await batcher.stop()  # flushes the 500-row tail

    assert spy.total == 2500, "no rows lost"
    assert spy.sizes[:2] == [1000, 1000], "size-triggered blocks are full"
    assert all(n > 1 for n in spy.sizes), "never a single-row insert"
    assert all(table == "actions" for table, _ in spy.batches)


async def test_multiple_tables_are_buffered_independently() -> None:
    spy = InsertSpy()
    batcher = ClickHouseBatcher(spy, max_rows=1000, max_interval_seconds=3600)

    for i in range(1000):
        await batcher.submit("hands", {"i": i})
    for i in range(3):
        await batcher.submit("actions", {"i": i})

    assert ("hands", 1000) in spy.batches  # full block flushed
    await batcher.stop()

    by_table = {t: n for t, n in spy.batches}
    assert by_table["actions"] == 3  # tail flush, still not single-row-per-insert
    assert spy.total == 1003


@pytest.mark.parametrize("bad", [0, -1])
async def test_rejects_invalid_max_rows(bad: int) -> None:
    with pytest.raises(ValueError):
        ClickHouseBatcher(InsertSpy(), max_rows=bad)
