---
description: Apply ClickHouse and PostgreSQL migrations
allowed-tools: Bash(cd*), Bash(uv*), Bash(docker*)
---

Apply all pending database migrations for both stores.

1. **ClickHouse** — run the SQL migration runner (applies `migrations/clickhouse/*.sql` in
   order, idempotent via the `schema_migrations` table):
   ```bash
   cd apps/api && uv run python -m spin2note_api.clickhouse.migrate
   ```
2. **PostgreSQL** — apply Alembic migrations for app-state:
   ```bash
   cd migrations/postgres && DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://postgres:postgres@localhost:5432/spin2note}" uv run --with alembic --with "psycopg[binary]" alembic upgrade head
   ```
3. Verify the ClickHouse tables exist with the expected engines:
   ```bash
   docker compose exec clickhouse clickhouse-client -q "SHOW TABLES FROM spin2note"
   ```

Report which migrations were applied (or that everything was already up to date). Connection
settings come from env vars (`CLICKHOUSE_URL`, `DATABASE_URL`); never hardcode credentials.
