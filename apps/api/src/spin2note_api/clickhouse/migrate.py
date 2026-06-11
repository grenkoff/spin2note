"""Minimal ClickHouse migration runner used by the /db-migrate slash command.

Applies ``migrations/clickhouse/*.sql`` in lexical order and records applied versions in a
``schema_migrations`` table so re-runs are idempotent. Each .sql file may contain multiple
statements separated by ``;``.
"""

from __future__ import annotations

import re
from pathlib import Path

import clickhouse_connect

from ..config import get_settings

_MIGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version String,
    applied_at DateTime DEFAULT now()
) ENGINE = MergeTree ORDER BY version
"""


def _statements(sql: str) -> list[str]:
    # Strip `--` line comments first so a ';' inside a comment doesn't split a statement
    # (migrations contain no string literals with `--`).
    no_comments = re.sub(r"--[^\n]*", "", sql)
    return [s.strip() for s in no_comments.split(";") if s.strip()]


def run(migrations_dir: Path) -> int:
    settings = get_settings()
    host = settings.clickhouse_url.split("://", 1)[-1].split(":")[0]
    port = int(settings.clickhouse_url.rsplit(":", 1)[-1])
    client = clickhouse_connect.get_client(
        host=host,
        port=port,
        username=settings.clickhouse_user,
        password=settings.clickhouse_password,
    )
    client.command(f"CREATE DATABASE IF NOT EXISTS {settings.clickhouse_database}")
    client.database = settings.clickhouse_database
    client.command(_MIGRATIONS_TABLE)

    applied = {r[0] for r in client.query("SELECT version FROM schema_migrations").result_rows}
    files = sorted(migrations_dir.glob("*.sql"))
    count = 0
    for path in files:
        version = path.stem
        if version in applied:
            continue
        for stmt in _statements(path.read_text()):
            client.command(stmt)
        client.insert("schema_migrations", [[version]], column_names=["version"])
        print(f"applied {version}")
        count += 1
    if count == 0:
        print("clickhouse: nothing to migrate")
    return count


def main() -> None:
    # .../apps/api/src/spin2note_api/clickhouse/migrate.py -> repo root is parents[5]
    root = Path(__file__).resolve().parents[5]
    run(root / "migrations" / "clickhouse")


if __name__ == "__main__":
    main()
