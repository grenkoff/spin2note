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
