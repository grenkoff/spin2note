"""Parse-pipeline worker.

Loop: pop a job from Redis -> stream the raw file from MinIO -> parse (hand history or
tournament summary) with the Rust ``hh_parser`` -> map to domain models -> submit to the
ClickHouse batcher (blocks >= 1000 rows, never single-row). Runs as a separate process from
the API so bulk imports don't compete with request handling.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from .cache import RedisQueue
from .clickhouse import ClickHouseBatcher
from .clickhouse.client import make_client, make_insert_fn
from .config import get_settings
from .ingest.storage import RawStorage
from .parser import ParserUnavailable, build_hands, build_tournament, parse, parse_summary
from .parser.wrapper import looks_like_summary

logger = logging.getLogger("spin2note.worker")


async def handle_raw(raw: str, user_id: UUID, batcher: ClickHouseBatcher) -> None:
    """Parse one raw file and submit its rows. Shared by the worker and tests."""
    if looks_like_summary(raw):
        summary = parse_summary(raw)
        if summary is not None:
            await batcher.submit("tournaments", build_tournament(summary, user_id))
        return
    for hand in build_hands(parse(raw), user_id):
        await batcher.submit("hands", hand)
        for player in hand.players:
            await batcher.submit("hand_players", player)
        for action in hand.actions:
            await batcher.submit("actions", action)


async def _handle(job: dict[str, Any], storage: RawStorage, batcher: ClickHouseBatcher) -> None:
    settings = get_settings()
    user_id = UUID(job.get("user_id") or settings.default_user_id)
    raw = storage.get(job["object_key"]).decode("utf-8", errors="replace")
    try:
        await handle_raw(raw, user_id, batcher)
    except ParserUnavailable:
        logger.error("hh_parser not built; skipping job %s", job["object_key"])


async def run() -> None:
    settings = get_settings()
    queue = RedisQueue(settings.redis_url)
    storage = RawStorage(settings)
    client = await make_client(settings)
    batcher = ClickHouseBatcher(
        make_insert_fn(client),
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
            await _handle(job, storage, batcher)
    finally:
        await batcher.stop()
        await queue.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())


if __name__ == "__main__":
    main()
