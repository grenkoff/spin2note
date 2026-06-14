"""Import-report persistence (PostgreSQL).

Each staged object becomes one ``import_job`` row (a bulk folder upload = many rows sharing a
``session_id``). The upload endpoint creates it as ``pending``; the worker fills in the
added/skipped counts and marks it ``done``/``failed``. The UI aggregates by ``session_id`` to
show the user how much was imported and how many duplicates were skipped.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlmodel import Field, SQLModel, col

from .postgres import get_sessionmaker


@dataclass
class ImportCounts:
    kind: str = ""  # "hands" | "summary"
    hands_added: int = 0
    hands_skipped: int = 0
    tournaments_added: int = 0
    tournaments_skipped: int = 0


class ImportJob(SQLModel, table=True):
    __tablename__ = "import_job"

    id: UUID = Field(primary_key=True)
    session_id: UUID = Field(index=True)
    user_id: UUID = Field(index=True)
    object_key: str
    status: str = "pending"  # pending | done | failed
    kind: str = ""
    hands_added: int = 0
    hands_skipped: int = 0
    tournaments_added: int = 0
    tournaments_skipped: int = 0
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None


async def create_import(
    *, import_id: UUID, session_id: UUID, user_id: UUID, object_key: str
) -> None:
    async with get_sessionmaker()() as session:
        session.add(
            ImportJob(
                id=import_id,
                session_id=session_id,
                user_id=user_id,
                object_key=object_key,
            )
        )
        await session.commit()


async def finish_import(
    import_id: UUID, *, status: str, counts: ImportCounts | None = None, error: str | None = None
) -> None:
    async with get_sessionmaker()() as session:
        job = await session.get(ImportJob, import_id)
        if job is None:
            return
        job.status = status
        job.error = error
        job.finished_at = datetime.now(UTC)
        if counts is not None:
            job.kind = counts.kind
            job.hands_added = counts.hands_added
            job.hands_skipped = counts.hands_skipped
            job.tournaments_added = counts.tournaments_added
            job.tournaments_skipped = counts.tournaments_skipped
        await session.commit()


async def session_summary(session_id: UUID, user_id: UUID) -> dict[str, Any]:
    """Aggregate all chunks of one upload session into a single report."""
    async with get_sessionmaker()() as session:
        result = await session.execute(
            select(
                func.count().label("chunks"),
                func.count().filter(col(ImportJob.status) == "done").label("done"),
                func.count().filter(col(ImportJob.status) == "failed").label("failed"),
                func.count().filter(col(ImportJob.status) == "pending").label("pending"),
                func.coalesce(func.sum(col(ImportJob.hands_added)), 0),
                func.coalesce(func.sum(col(ImportJob.hands_skipped)), 0),
                func.coalesce(func.sum(col(ImportJob.tournaments_added)), 0),
                func.coalesce(func.sum(col(ImportJob.tournaments_skipped)), 0),
            ).where(col(ImportJob.session_id) == session_id, col(ImportJob.user_id) == user_id)
        )
        row = result.one()
        return {
            "chunks": row[0],
            "done": row[1],
            "failed": row[2],
            "pending": row[3],
            "hands_added": row[4],
            "hands_skipped": row[5],
            "tournaments_added": row[6],
            "tournaments_skipped": row[7],
            "complete": row[3] == 0,
        }
