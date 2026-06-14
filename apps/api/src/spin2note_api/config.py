"""Application settings.

Cloud-agnostic by design: every external dependency is configured through environment
variables (12-factor). Nothing here is Railway-specific — swap any DSN/URL to move the
component to another provider.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    app_name: str = "spin2note-api"
    environment: str = "development"

    # ClickHouse (analytics store)
    clickhouse_url: str = "http://localhost:8123"  # HTTP, used for reads (clickhouse-connect)
    clickhouse_native_port: int = 9000  # native TCP, used for fast inserts (asynch)
    clickhouse_user: str = "default"
    clickhouse_password: str = ""
    clickhouse_database: str = "spin2note"

    # PostgreSQL (mutable app state; shared with Supabase Auth)
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/spin2note"

    # Redis (parse-pipeline queue / cache)
    redis_url: str = "redis://localhost:6379/0"

    # MinIO (raw hand-history staging)
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_secure: bool = False
    minio_bucket_raw: str = "raw-hh"
    # Raw bundles are a transient staging buffer: the worker deletes each object after a
    # successful parse, and this lifecycle TTL is the safety net for objects that never parsed.
    raw_retention_days: int = 1

    # Supabase Auth (self-hosted GoTrue) — JWT validation
    supabase_jwks_url: str = "http://localhost:9999/.well-known/jwks.json"
    supabase_jwt_audience: str = "authenticated"
    # Fallback HS256 secret for local dev when JWKS is unavailable.
    supabase_jwt_secret: str = ""

    # ClickHouse batching (hard rule: never single-row inserts; bigger blocks = far fewer
    # native round-trips, which dominates bulk-insert throughput).
    batch_max_rows: int = 50000
    batch_max_interval_seconds: float = 1.0

    # Fallback owner id for uploads without an authenticated user (local dev / bulk import).
    default_user_id: str = "00000000-0000-0000-0000-000000000001"

    # CORS origins allowed to call the API (the Next.js frontend).
    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
