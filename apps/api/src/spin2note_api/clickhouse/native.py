"""Native-protocol ClickHouse inserts (asynch) for the worker's hot path.

The HTTP client (clickhouse-connect) is kept for reads; bulk inserts go over the native TCP
protocol, which is markedly faster for large column blocks. Rows are tuples in
``TABLE_COLUMNS`` order; Enum8 columns receive their label strings (the driver maps them).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from asynch import Connection

from ..config import Settings


async def make_native_conn(settings: Settings) -> Any:
    host = settings.clickhouse_url.split("://", 1)[-1].split(":")[0]
    conn = Connection(
        host=host,
        port=settings.clickhouse_native_port,
        user=settings.clickhouse_user,
        password=settings.clickhouse_password,
        database=settings.clickhouse_database,
    )
    await conn.connect()
    return conn


def make_native_insert_fn(
    conn: Any, columns: dict[str, list[str]]
) -> Callable[[str, Sequence[Any]], Awaitable[None]]:
    """Build an ``insert_fn(table, rows)`` for ClickHouseBatcher backed by the native conn."""

    async def insert_fn(table: str, rows: Sequence[Any]) -> None:
        cols = ", ".join(columns[table])
        async with conn.cursor() as cur:
            await cur.executemany(f"INSERT INTO {table} ({cols}) VALUES", list(rows))

    return insert_fn
