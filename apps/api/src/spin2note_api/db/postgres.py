"""SQLAlchemy async engine/session for PostgreSQL.

Postgres holds low-volume mutable state (users, subscriptions, saved filters, training
metadata). It is shared with the self-hosted Supabase Auth (GoTrue) database. Heavy analytics
never touch Postgres — those live in ClickHouse.
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ..config import get_settings


def _async_url(url: str) -> str:
    # Ensure the async psycopg driver is used.
    if url.startswith("postgresql+psycopg://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


@lru_cache
def get_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(_async_url(settings.database_url), pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)
