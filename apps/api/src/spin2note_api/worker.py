"""Parse-pipeline worker.

Loop: pop a job from Redis -> stream the raw file from MinIO -> parse with the Rust
``hh_parser`` -> map to domain models -> submit to the ClickHouse batcher (blocks >= 1000
rows, never single-row). Run as a separate process from the API so bulk imports don't compete
with request handling.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .cache import RedisQueue
from .clickhouse import ClickHouseBatcher
from .clickhouse.client import make_client, make_insert_fn
from .config import get_settings
from .ingest.storage import RawStorage
from .parser import ParserUnavailable, parse

logger = logging.getLogger("spin2note.worker")


async def _handle(job: dict[str, Any], storage: RawStorage, batcher: ClickHouseBatcher) -> None:
    raw = storage.get(job["object_key"]).decode("utf-8", errors="replace")
    try:
        hands = parse(raw)
    except ParserUnavailable:
        logger.error("hh_parser not built; skipping job %s", job["object_key"])
        return
    for hand in hands:
        await batcher.submit("hands", hand)
        for player in hand.get("players", []):
            await batcher.submit("hand_players", player)
        for action in hand.get("actions", []):
            await batcher.submit("actions", action)


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
