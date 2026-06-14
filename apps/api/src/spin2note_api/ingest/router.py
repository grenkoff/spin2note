"""Upload endpoint: stream raw HH to MinIO and enqueue a parse job."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, UploadFile
from pydantic import BaseModel

from ..config import Settings, get_settings
from ..db.imports import create_import
from ..domain.ids import new_id
from ..http.auth import current_user_id
from .storage import RawStorage

router = APIRouter(prefix="/ingest", tags=["ingest"])


class UploadResult(BaseModel):
    object_key: str
    bytes: int
    queued: bool
    import_id: str
    session_id: str


def _stage(settings: Settings, key: str, raw: bytes) -> None:
    storage = RawStorage(settings)
    storage.ensure_bucket()
    storage.put(key, raw)


def _session_id(header: str | None) -> UUID:
    """Group chunks of one upload action; the browser sends X-Upload-Session per click."""
    try:
        return UUID(header) if header else new_id()
    except ValueError:
        return new_id()


async def _register_and_enqueue(
    settings: Settings, key: str, user_id: str, session_id: UUID
) -> UUID:
    import_id = new_id()
    await create_import(
        import_id=import_id, session_id=session_id, user_id=UUID(user_id), object_key=key
    )
    # Imported lazily so the module has no hard Redis dependency at import time.
    from ..cache import RedisQueue

    queue = RedisQueue(settings.redis_url)
    try:
        await queue.enqueue(
            {"object_key": key, "user_id": user_id, "import_id": str(import_id)}
        )
    finally:
        await queue.close()
    return import_id


@router.post("/upload", response_model=UploadResult)
async def upload_hand_history(
    file: UploadFile,
    settings: Settings = Depends(get_settings),
    user_id: str = Depends(current_user_id),
    x_upload_session: str | None = Header(default=None),
) -> UploadResult:
    """Accept a raw hand-history (or summary) file, stage it in MinIO, enqueue async parsing.

    The heavy parsing happens out-of-band in the worker (Rust ``hh_parser``); the request
    returns as soon as the file is staged so uploads stay fast under bulk imports.
    """
    raw = await file.read()
    stamp = datetime.now(UTC).strftime("%Y/%m/%d")
    key = f"{user_id}/{stamp}/{new_id()}-{file.filename or 'hands.txt'}"

    session_id = _session_id(x_upload_session)
    _stage(settings, key, raw)
    import_id = await _register_and_enqueue(settings, key, user_id, session_id)
    return UploadResult(
        object_key=key, bytes=len(raw), queued=True,
        import_id=str(import_id), session_id=str(session_id),
    )


@router.post("/bulk", response_model=UploadResult)
async def upload_bulk(
    request: Request,
    settings: Settings = Depends(get_settings),
    user_id: str = Depends(current_user_id),
    x_upload_session: str | None = Header(default=None),
) -> UploadResult:
    """Accept a large bundle of concatenated hand-history (or summary) files in one request.

    The browser concatenates many small files into ~16 MB chunks and gzips them, turning a
    base of hundreds of thousands of files into a few dozen requests. The body is the raw
    bundle; ``X-Bundle-Gzip: 1`` marks gzip-compressed payloads. We store the gzip **as-is**
    (5-10x smaller) and let the worker decompress on read — the staged object is transient and
    deleted once parsed. The worker's parsers are multi-record, so one object yields all its
    hands/tournaments in a single pass.
    """
    body = await request.body()
    gzipped = request.headers.get("x-bundle-gzip") == "1"

    stamp = datetime.now(UTC).strftime("%Y/%m/%d")
    suffix = ".txt.gz" if gzipped else ".txt"
    key = f"{user_id}/bulk/{stamp}/{new_id()}{suffix}"

    session_id = _session_id(x_upload_session)
    _stage(settings, key, body)
    import_id = await _register_and_enqueue(settings, key, user_id, session_id)
    return UploadResult(
        object_key=key, bytes=len(body), queued=True,
        import_id=str(import_id), session_id=str(session_id),
    )
