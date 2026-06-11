"""Upload endpoint: stream raw HH to MinIO and enqueue a parse job."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, UploadFile
from pydantic import BaseModel

from ..config import Settings, get_settings
from ..domain.ids import new_id
from ..http.auth import current_user_id
from .storage import RawStorage

router = APIRouter(prefix="/ingest", tags=["ingest"])


class UploadResult(BaseModel):
    object_key: str
    bytes: int
    queued: bool


@router.post("/upload", response_model=UploadResult)
async def upload_hand_history(
    file: UploadFile,
    settings: Settings = Depends(get_settings),
    user_id: str = Depends(current_user_id),
) -> UploadResult:
    """Accept a raw hand-history (or summary) file, stage it in MinIO, enqueue async parsing.

    The heavy parsing happens out-of-band in the worker (Rust ``hh_parser``); the request
    returns as soon as the file is staged so uploads stay fast under bulk imports.
    """
    raw = await file.read()
    stamp = datetime.now(UTC).strftime("%Y/%m/%d")
    key = f"{user_id}/{stamp}/{new_id()}-{file.filename or 'hands.txt'}"

    storage = RawStorage(settings)
    storage.ensure_bucket()
    storage.put(key, raw)

    # Importing here avoids a hard Redis dependency at module import time (keeps tests light).
    from ..cache import RedisQueue

    queue = RedisQueue(settings.redis_url)
    try:
        await queue.enqueue({"object_key": key, "user_id": user_id})
    finally:
        await queue.close()

    return UploadResult(object_key=key, bytes=len(raw), queued=True)
