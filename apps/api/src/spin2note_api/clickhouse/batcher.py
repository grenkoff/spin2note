"""Async batching writer for ClickHouse.

Hard rule (CLAUDE.md §2.2): never perform single-row inserts into ClickHouse. Every row is
buffered per-table and flushed as a block when EITHER the buffer reaches ``max_rows``
(default 1000) OR ``max_interval_seconds`` elapses. A size-triggered flush is always a full
``max_rows`` block; only the periodic timer or an explicit ``stop()`` may emit a smaller tail
block.

The actual insert is injected as ``insert_fn(table, rows)`` so the batcher is transport- and
test-agnostic (the production wiring passes a clickhouse-connect insert; tests pass a spy).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

InsertFn = Callable[[str, Sequence[Any]], Awaitable[None]]

logger = logging.getLogger("spin2note.clickhouse.batcher")


class ClickHouseBatcher:
    def __init__(
        self,
        insert_fn: InsertFn,
        *,
        max_rows: int = 1000,
        max_interval_seconds: float = 1.0,
    ) -> None:
        if max_rows < 1:
            raise ValueError("max_rows must be >= 1")
        self._insert_fn = insert_fn
        self._max_rows = max_rows
        self._max_interval = max_interval_seconds
        self._buffers: dict[str, list[Any]] = {}
        self._lock = asyncio.Lock()
        self._flush_task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._flush_task = asyncio.create_task(self._periodic_flush())

    async def stop(self) -> None:
        """Stop the timer and flush every remaining buffer (tail blocks allowed)."""
        self._running = False
        if self._flush_task is not None:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            self._flush_task = None
        await self.flush_all()

    async def submit(self, table: str, row: Any) -> None:
        """Buffer a single row; flush immediately if the block is full."""
        async with self._lock:
            buf = self._buffers.setdefault(table, [])
            buf.append(row)
            if len(buf) >= self._max_rows:
                ready, self._buffers[table] = buf, []
            else:
                ready = None
        if ready is not None:
            await self._insert_fn(table, ready)

    async def submit_many(self, table: str, rows: Sequence[Any]) -> None:
        for row in rows:
            await self.submit(table, row)

    async def submit_block(self, table: str, rows: Sequence[Any]) -> None:
        """Append many rows at once (one lock), flushing full ``max_rows`` blocks.

        Far cheaper than per-row ``submit`` for bulk ingestion — the hot path adds a whole
        chunk's rows in a single critical section.
        """
        if not rows:
            return
        async with self._lock:
            buf = self._buffers.setdefault(table, [])
            buf.extend(rows)
            ready: list[list[Any]] = []
            while len(buf) >= self._max_rows:
                ready.append(buf[: self._max_rows])
                del buf[: self._max_rows]
        for block in ready:
            await self._insert_fn(table, block)

    async def flush_all(self) -> None:
        async with self._lock:
            pending = {t: rows for t, rows in self._buffers.items() if rows}
            self._buffers = {}
        for table, rows in pending.items():
            await self._insert_fn(table, rows)

    async def _periodic_flush(self) -> None:
        while self._running:
            await asyncio.sleep(self._max_interval)
            try:
                await self.flush_all()
            except Exception:  # noqa: BLE001 - never let the flusher task die silently
                logger.exception("periodic flush failed; will retry on next tick")
