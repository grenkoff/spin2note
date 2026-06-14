"""MinIO object storage for raw hand-history files (transient pipeline staging).

Raw bundles are NOT a long-term archive — ClickHouse is the source of truth. The worker
deletes each object after a successful parse; a bucket lifecycle TTL expires anything that
slips through (e.g. a job that never parsed), so storage stays bounded as users scale.
"""

from __future__ import annotations

import io

from minio import Minio
from minio.commonconfig import ENABLED, Filter
from minio.lifecycleconfig import Expiration, LifecycleConfig, Rule

from ..config import Settings


class RawStorage:
    def __init__(self, settings: Settings) -> None:
        self._client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        self._bucket = settings.minio_bucket_raw
        self._retention_days = settings.raw_retention_days

    def ensure_bucket(self) -> None:
        if not self._client.bucket_exists(self._bucket):
            self._client.make_bucket(self._bucket)
        self._apply_lifecycle()

    def _apply_lifecycle(self) -> None:
        """Expire all raw objects after the retention window (idempotent safety net)."""
        try:
            config = LifecycleConfig(
                [
                    Rule(
                        ENABLED,
                        rule_id="expire-raw",
                        rule_filter=Filter(prefix=""),
                        expiration=Expiration(days=self._retention_days),
                    )
                ]
            )
            self._client.set_bucket_lifecycle(self._bucket, config)
        except Exception:  # noqa: BLE001 - lifecycle is best-effort; never block uploads
            pass

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        self._client.put_object(
            self._bucket, key, io.BytesIO(data), length=len(data), content_type=content_type
        )
        return key

    def get(self, key: str) -> bytes:
        response = self._client.get_object(self._bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def delete(self, key: str) -> None:
        self._client.remove_object(self._bucket, key)
