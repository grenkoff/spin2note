"""ClickHouse client factory and the production insert function for the batcher.

Column order in ``TABLE_COLUMNS`` is the contract between the domain models and the physical
tables; the batcher hands us a list of Pydantic rows and we project them to column-major data
for clickhouse-connect's block insert.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import clickhouse_connect
from clickhouse_connect.driver.asyncclient import AsyncClient

from ..config import Settings

# Column projection per table (names must match migrations/clickhouse).
TABLE_COLUMNS: dict[str, list[str]] = {
    "hands": [
        "hand_id", "user_id", "tournament_format", "effective_stack_bb", "source_hand_id",
        "tournament_id", "level", "button_seat", "played_at", "multiplier", "small_blind",
        "big_blind", "board", "pot", "rake", "parsed_at",
    ],
    "hand_players": [
        "hand_id", "user_id", "tournament_format", "effective_stack_bb", "seat", "is_hero",
        "villain_hash", "position", "starting_stack", "hole_cards", "won", "result", "parsed_at",
    ],
    "actions": [
        "hand_id", "user_id", "tournament_format", "effective_stack_bb", "street", "seat",
        "action_index", "action_type", "amount", "pot_before", "to_amount", "all_in",
    ],
    "tournaments": [
        "tournament_id", "user_id", "name", "buy_in", "currency", "players", "prize_pool",
        "multiplier", "started_at", "hero_place", "parsed_at",
    ],
}


async def make_client(settings: Settings) -> AsyncClient:
    return await clickhouse_connect.get_async_client(
        interface="http",
        host=settings.clickhouse_url.split("://", 1)[-1].split(":")[0],
        port=int(settings.clickhouse_url.rsplit(":", 1)[-1]),
        username=settings.clickhouse_user,
        password=settings.clickhouse_password,
        database=settings.clickhouse_database,
    )


def make_insert_fn(client: AsyncClient) -> Any:
    """Build an ``insert_fn(table, rows)`` for ClickHouseBatcher backed by ``client``."""

    async def insert_fn(table: str, rows: Sequence[Any]) -> None:
        columns = TABLE_COLUMNS[table]
        data = [[_field(row, col) for col in columns] for row in rows]
        await client.insert(table, data, column_names=columns)

    return insert_fn


def _field(row: Any, name: str) -> Any:
    # Accept both domain models (attribute access) and raw parser dicts.
    value = row.get(name) if isinstance(row, dict) else getattr(row, name, None)
    if isinstance(value, bool):
        return int(value)  # UInt8 flags (is_hero, all_in)
    # IntEnum (tournament_format) -> raw int the ClickHouse Enum8 expects.
    return int(value) if hasattr(value, "value") and isinstance(value, int) else value
