"""The native insert_fn must serialize concurrent calls on one connection.

A single asynch connection cannot run concurrent queries; the batcher's periodic flush can race
a submit_block insert. Regression for the data loss that caused (#missing hands).
"""

from __future__ import annotations

import asyncio

import pytest

from spin2note_api.clickhouse.native import make_native_insert_fn


class _Cursor:
    def __init__(self, conn: _Conn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _Cursor:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def executemany(self, query: str, rows: list) -> None:
        assert not self._conn.busy, "concurrent query on a single connection!"
        self._conn.busy = True
        await asyncio.sleep(0.005)  # force overlap if not serialized
        self._conn.busy = False
        self._conn.total += len(rows)


class _Conn:
    def __init__(self) -> None:
        self.busy = False
        self.total = 0

    def cursor(self) -> _Cursor:
        return _Cursor(self)


async def test_insert_fn_serializes_concurrent_calls() -> None:
    conn = _Conn()
    insert = make_native_insert_fn(conn, {"hands": ["a", "b"]})
    # Fire many inserts concurrently — the lock must prevent overlapping queries.
    await asyncio.gather(*[insert("hands", [(1, 2)] * 10) for _ in range(8)])
    assert conn.total == 80


def test_unknown_table_raises() -> None:
    insert = make_native_insert_fn(_Conn(), {"hands": ["a"]})
    with pytest.raises(KeyError):
        asyncio.run(insert("nope", [(1,)]))
