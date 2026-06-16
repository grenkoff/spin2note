"""Read-only analytics queries over ClickHouse.

All queries are scoped to a single ``user_id`` (the hero/owner) and use server-side bound
parameters. They power the presentation-only frontend — no business logic leaks to the client.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import UUID

from clickhouse_connect.driver.asyncclient import AsyncClient

_FORMAT_FILTER = " AND tournament_format = {fmt:String}"

# Membership checks are batched: ClickHouse's HTTP layer rejects an over-long parameter value,
# so a 16k-id IN list must be split into chunks small enough to fit the form field.
_ID_BATCH = 1000


def _batched(items: list[Any], size: int = _ID_BATCH) -> list[list[Any]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _iso(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _cumulative_timeline(rows: list[Any], max_points: int = 1500) -> list[dict[str, Any]]:
    """Turn time-ordered ``(delta, at)`` rows into a downsampled cumulative series.

    Each point is ``{"idx", "at", "cumulative"}``. The running total is computed over *all* rows
    (so the curve is exact), then thinned to at most ``max_points`` evenly-spaced points with the
    last point always kept — bounds the payload when a hero has 100k+ hands.
    """
    total = 0.0
    points: list[dict[str, Any]] = []
    for i, r in enumerate(rows, start=1):
        total += float(r[0])
        points.append({"idx": i, "at": _iso(r[1]), "cumulative": round(total, 2)})
    if len(points) <= max_points:
        return points
    step = len(points) / max_points
    sampled = [points[int(k * step)] for k in range(max_points)]
    if sampled[-1] is not points[-1]:
        sampled[-1] = points[-1]
    return sampled


async def user_has_rows(client: AsyncClient, table: str, user_id: UUID) -> bool:
    """Cheap check used to skip membership queries entirely on a user's first import."""
    if table not in {"hands", "tournaments"}:
        raise ValueError(table)
    res = await client.query(
        f"SELECT 1 FROM {table} WHERE user_id = {{u:UUID}} LIMIT 1",
        parameters={"u": str(user_id)},
    )
    return bool(res.result_rows)


async def existing_hand_ids(client: AsyncClient, user_id: UUID, ids: list[UUID]) -> set[UUID]:
    """Return which of ``ids`` already exist for this user (for input deduplication)."""
    found: set[UUID] = set()
    for batch in _batched(ids):
        res = await client.query(
            "SELECT DISTINCT hand_id FROM hands "
            "WHERE user_id = {u:UUID} AND hand_id IN {ids:Array(UUID)}",
            parameters={"u": str(user_id), "ids": [str(i) for i in batch]},
        )
        found |= {r[0] if isinstance(r[0], UUID) else UUID(str(r[0])) for r in res.result_rows}
    return found


async def existing_tournament_ids(
    client: AsyncClient, user_id: UUID, ids: Iterable[str]
) -> set[str]:
    found: set[str] = set()
    for batch in _batched(list(ids)):
        res = await client.query(
            "SELECT DISTINCT tournament_id FROM tournaments "
            "WHERE user_id = {u:UUID} AND tournament_id IN {ids:Array(String)}",
            parameters={"u": str(user_id), "ids": batch},
        )
        found |= {str(r[0]) for r in res.result_rows}
    return found


async def overview(client: AsyncClient, user_id: UUID, fmt: str | None) -> dict[str, Any]:
    params: dict[str, Any] = {"u": str(user_id)}
    f_hands = ""
    if fmt:
        params["fmt"] = fmt
        f_hands = _FORMAT_FILTER

    totals = await client.query(
        f"SELECT count() FROM hands WHERE user_id = {{u:UUID}}{f_hands}", parameters=params
    )
    total_hands = int(totals.result_rows[0][0]) if totals.result_rows else 0

    tourneys = await client.query(
        "SELECT count(), avg(multiplier) FROM tournaments WHERE user_id = {u:UUID}",
        parameters={"u": str(user_id)},
    )
    t_row = tourneys.result_rows[0] if tourneys.result_rows else (0, 0.0)
    total_tournaments = int(t_row[0] or 0)
    avg_multiplier = round(float(t_row[1] or 0.0), 2)

    by_stack = await client.query(
        f"""
        SELECT
            toUInt16(round(effective_stack_bb / 10)) AS bb,
            count() AS hands,
            sum(result) AS total_result,
            sum(chip_ev) AS total_ev,
            countIf(result > 0) / count() AS winrate
        FROM hand_players
        WHERE user_id = {{u:UUID}} AND is_hero = 1{f_hands}
        GROUP BY bb ORDER BY bb
        """,
        parameters=params,
    )
    stacks = [
        {
            "effective_stack_bb": int(r[0]),
            "hands": int(r[1]),
            "result": round(float(r[2]), 2),
            "result_ev": round(float(r[3]), 2),
            "winrate": round(float(r[4]), 4),
        }
        for r in by_stack.result_rows
    ]

    # Same aggregation grouped by hero position (UTG/HJ/CO/BTN/SB/BB); ordered client-side.
    by_position = await client.query(
        f"""
        SELECT
            position,
            count() AS hands,
            sum(result) AS total_result,
            sum(chip_ev) AS total_ev,
            countIf(result > 0) / count() AS winrate
        FROM hand_players
        WHERE user_id = {{u:UUID}} AND is_hero = 1{f_hands}
        GROUP BY position
        """,
        parameters=params,
    )
    positions = [
        {
            "position": str(r[0]),
            "hands": int(r[1]),
            "result": round(float(r[2]), 2),
            "result_ev": round(float(r[3]), 2),
            "winrate": round(float(r[4]), 4),
        }
        for r in by_position.result_rows
    ]

    # Cumulative chips P&L over hero hands (time-ordered). Respects the format filter.
    chips_series = await client.query(
        f"""
        SELECT hp.result AS result, h.played_at AS at
        FROM hand_players AS hp
        INNER JOIN hands AS h ON hp.hand_id = h.hand_id
        WHERE hp.user_id = {{u:UUID}} AND hp.is_hero = 1{f_hands}
        ORDER BY h.played_at
        """,
        parameters=params,
    )
    chips_timeline = _cumulative_timeline(chips_series.result_rows)

    # Cumulative real-money P&L per tournament (net = hero_prize - buy_in), time-ordered.
    # The tournaments table has no tournament_format column, so this series spans all formats.
    dollars_series = await client.query(
        """
        SELECT (hero_prize - buy_in) AS net, started_at AS at
        FROM tournaments
        WHERE user_id = {u:UUID}
        ORDER BY started_at
        """,
        parameters={"u": str(user_id)},
    )
    dollars_timeline = _cumulative_timeline(dollars_series.result_rows)

    return {
        "total_hands": total_hands,
        "total_tournaments": total_tournaments,
        "avg_multiplier": avg_multiplier,
        "by_stack": stacks,
        "by_position": positions,
        "chips_timeline": chips_timeline,
        "dollars_timeline": dollars_timeline,
    }


async def recent_hands(client: AsyncClient, user_id: UUID, limit: int) -> list[dict[str, Any]]:
    res = await client.query(
        """
        SELECT
            h.source_hand_id AS source_hand_id,
            h.played_at AS played_at,
            h.tournament_format AS tournament_format,
            toUInt16(round(hp.effective_stack_bb / 10)) AS effective_stack_bb,
            hp.position AS position,
            hp.result AS result,
            h.board AS board
        FROM hand_players AS hp
        INNER JOIN hands AS h ON hp.hand_id = h.hand_id
        WHERE hp.user_id = {u:UUID} AND hp.is_hero = 1
        ORDER BY h.played_at DESC
        LIMIT {lim:UInt32}
        """,
        parameters={"u": str(user_id), "lim": limit},
    )
    return [
        {
            "source_hand_id": r[0],
            "played_at": r[1].isoformat() if hasattr(r[1], "isoformat") else str(r[1]),
            "tournament_format": str(r[2]),
            "effective_stack_bb": int(r[3]),
            "position": r[4],
            "result": round(float(r[5]), 2),
            "board": r[6],
        }
        for r in res.result_rows
    ]
