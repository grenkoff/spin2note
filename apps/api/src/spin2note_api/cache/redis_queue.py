"""Tiny Redis list queue for parse jobs.

Ingest pushes a job (the MinIO object key of an uploaded raw hand-history file); the worker
pops it, streams the object back, parses and batches into ClickHouse.
"""

from __future__ import annotations

import json
from typing import Any

import redis.asyncio as redis
from redis.exceptions import TimeoutError as RedisTimeoutError

PARSE_QUEUE = "parse:jobs"


class RedisQueue:
    def __init__(self, url: str, *, queue: str = PARSE_QUEUE) -> None:
        # socket_timeout must exceed the BLPOP server timeout, else the client read aborts.
        self._redis = redis.from_url(url, decode_responses=True, socket_timeout=None)
        self._queue = queue

    async def enqueue(self, job: dict[str, Any]) -> None:
        await self._redis.rpush(self._queue, json.dumps(job))

    async def dequeue(self, *, timeout: int = 5) -> dict[str, Any] | None:
        try:
            item = await self._redis.blpop([self._queue], timeout=timeout)
        except (TimeoutError, RedisTimeoutError):
            return None  # empty queue within the window — treat as "no job"
        if item is None:
            return None
        _, payload = item
        job: dict[str, Any] = json.loads(payload)
        return job

    async def close(self) -> None:
        await self._redis.aclose()
