"""UUIDv7 helpers.

Every entity id is a time-ordered UUIDv7 (CLAUDE.md §2.2) so inserts stay roughly
sequential. Note: ClickHouse does NOT sort UUIDv7 chronologically, so time-range scans
must use the explicit `played_at` column — the trailing `hand_id` in the sort key is a
dedup tie-breaker, not a time index.
"""

from __future__ import annotations

from uuid import UUID

from uuid6 import uuid7


def new_id() -> UUID:
    """Generate a fresh time-ordered UUIDv7."""
    return uuid7()
