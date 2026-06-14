"""Parse-pipeline worker.

Loop: pop a job from Redis -> stream the raw file from MinIO -> parse with the Rust
``hh_parser`` -> **deduplicate on input** (skip hands/tournaments already stored for the user,
counting how many were skipped) -> submit only the new rows to the ClickHouse batcher -> record
the per-object import report. Runs as a separate process so bulk imports don't compete with the
API.
"""

from __future__ import annotations

import asyncio
import gzip
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from clickhouse_connect.driver.asyncclient import AsyncClient

from .cache import RedisQueue
from .clickhouse import ClickHouseBatcher
from .clickhouse.client import TABLE_COLUMNS, make_client
from .clickhouse.native import make_native_conn, make_native_insert_fn
from .clickhouse.queries import existing_hand_ids, existing_tournament_ids, user_has_rows
from .config import get_settings
from .db.imports import ImportCounts, finish_import
from .ingest.archives import extract_text_members
from .ingest.storage import RawStorage
from .logging_config import bind_log_context, configure_logging, reset_log_context
from .parser import (
    ParserUnavailable,
    build_chunk_rows,
    build_tournament_rows,
    parse,
    parse_summaries,
)
from .parser.wrapper import looks_like_summary

logger = logging.getLogger("spin2note.worker")


def _decode_object(object_key: str, data: bytes) -> str:
    """Decode a staged object, decompressing gzip bundles (``.gz`` keys)."""
    if object_key.endswith(".gz"):
        data = gzip.decompress(data)
    return data.decode("utf-8", errors="replace")


async def handle_raw(
    raw: str, user_id: UUID, batcher: ClickHouseBatcher, client: AsyncClient
) -> ImportCounts:
    """Parse one raw blob, skip duplicates, submit only new rows, return added/skipped counts.

    Duplicates are detected by the deterministic id (hand_id / tournament_id) against both the
    current batch and what already exists for the user — so re-uploading is a no-op that simply
    reports how many were skipped.
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    if looks_like_summary(raw):
        unique: dict[str, dict[str, Any]] = {}
        for s in parse_summaries(raw):
            unique.setdefault(s["tournament_id"], s)
        total = len(unique)
        existing: set[str] = set()
        if await user_has_rows(client, "tournaments", user_id):
            existing = await existing_tournament_ids(client, user_id, unique.keys())
        new = [s for tid, s in unique.items() if tid not in existing]
        await batcher.submit_block("tournaments", build_tournament_rows(new, user_id, now))
        return ImportCounts(
            kind="summary", tournaments_added=len(new), tournaments_skipped=total - len(new)
        )

    unique_h: dict[UUID, dict[str, Any]] = {}
    for h in parse(raw):
        unique_h.setdefault(UUID(h["hand_id"]), h)
    total = len(unique_h)
    existing_h: set[UUID] = set()
    if await user_has_rows(client, "hands", user_id):
        existing_h = await existing_hand_ids(client, user_id, list(unique_h.keys()))
    new_hands = [h for hid, h in unique_h.items() if hid not in existing_h]
    blocks = build_chunk_rows(new_hands, user_id, now)
    await batcher.submit_block("hands", blocks["hands"])
    await batcher.submit_block("hand_players", blocks["hand_players"])
    await batcher.submit_block("actions", blocks["actions"])
    return ImportCounts(
        kind="hands", hands_added=len(new_hands), hands_skipped=total - len(new_hands)
    )


async def _ingest_chunked(
    parts: list[str], user_id: UUID, batcher: ClickHouseBatcher, client: AsyncClient
) -> ImportCounts:
    """Parse same-blob parts in ~32 MB chunks (bounds memory for huge archives)."""
    out = ImportCounts()
    buf: list[str] = []
    size = 0

    async def flush() -> None:
        nonlocal buf, size
        if not buf:
            return
        c = await handle_raw("\n".join(buf), user_id, batcher, client)
        out.hands_added += c.hands_added
        out.hands_skipped += c.hands_skipped
        out.tournaments_added += c.tournaments_added
        out.tournaments_skipped += c.tournaments_skipped
        buf, size = [], 0

    for part in parts:
        buf.append(part)
        size += len(part)
        if size >= 32 * 1024 * 1024:
            await flush()
    await flush()
    return out


async def handle_archive(
    data: bytes, user_id: UUID, batcher: ClickHouseBatcher, client: AsyncClient
) -> ImportCounts:
    """Extract an archive's .txt members, split into hand-history vs summary, and ingest both."""
    hh_parts: list[str] = []
    summary_parts: list[str] = []
    for _name, text in extract_text_members(data):
        if "Poker Hand #" in text:
            hh_parts.append(text)
        elif "Buy-in:" in text or text.startswith("Tournament #"):
            summary_parts.append(text)
    counts = await _ingest_chunked(hh_parts, user_id, batcher, client)
    sums = await _ingest_chunked(summary_parts, user_id, batcher, client)
    counts.kind = "archive"
    counts.tournaments_added += sums.tournaments_added
    counts.tournaments_skipped += sums.tournaments_skipped
    counts.hands_added += sums.hands_added
    counts.hands_skipped += sums.hands_skipped
    return counts


async def _handle(
    job: dict[str, Any], storage: RawStorage, batcher: ClickHouseBatcher, client: AsyncClient
) -> None:
    settings = get_settings()
    user_id = UUID(job.get("user_id") or settings.default_user_id)
    key = job["object_key"]
    import_id = UUID(job["import_id"]) if job.get("import_id") else None
    reset_log_context()
    bind_log_context(user_id=str(user_id), object_key=key, import_id=str(import_id or ""))
    try:
        data = storage.get(key)
        if job.get("kind") == "archive":
            counts = await handle_archive(data, user_id, batcher, client)
        else:
            counts = await handle_raw(_decode_object(key, data), user_id, batcher, client)
        await batcher.flush_all()  # durable in ClickHouse before dropping raw / reporting
    except ParserUnavailable:
        logger.error("hh_parser not built; leaving %s for retry", key)
        if import_id:
            await finish_import(import_id, status="failed", error="parser unavailable")
        return
    except Exception as exc:  # noqa: BLE001 - keep the worker alive; leave raw for retry
        logger.exception("failed to process %s; leaving raw for retry", key)
        if import_id:
            await finish_import(import_id, status="failed", error=str(exc)[:500])
        return
    storage.delete(key)  # transient staging — raw no longer needed once in ClickHouse
    if import_id:
        await finish_import(import_id, status="done", counts=counts)


async def run() -> None:
    settings = get_settings()
    queue = RedisQueue(settings.redis_url)
    storage = RawStorage(settings)
    client = await make_client(settings)  # HTTP, reads (dedup)
    native = await make_native_conn(settings)  # native TCP, fast inserts
    batcher = ClickHouseBatcher(
        make_native_insert_fn(native, TABLE_COLUMNS),
        max_rows=settings.batch_max_rows,
        max_interval_seconds=settings.batch_max_interval_seconds,
    )
    await batcher.start()
    logger.info("worker started")
    try:
        while True:
            job = await queue.dequeue(timeout=5)
            if job is None:
                continue
            await _handle(job, storage, batcher, client)
    finally:
        await batcher.stop()
        await queue.close()
        await native.close()


def main() -> None:
    configure_logging(get_settings())
    asyncio.run(run())


if __name__ == "__main__":
    main()
