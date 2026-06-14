# spin2note

High-performance SaaS analytics for **GGPoker / PokerOK Spin&Gold** tournaments
(3-max and 6-max). It ingests raw hand histories, parses them at speed, and serves
aggregated stats, graphs, and a GTO training module.

> **Single-locale (`en`), UUID-first, cloud-agnostic.** Heavy aggregation runs inside
> ClickHouse; the only CPU-bound work left in app code is parsing — done in Rust.

---

## Architecture

| Layer | Tech | Role |
|------|------|------|
| **API / glue / analytics** | Python 3.12 + FastAPI (pkg manager: `uv`) | REST API, OpenAPI spec, pipeline orchestration |
| **Hot path (parsing)** | Rust (`crates/hh-parser`) via PyO3/maturin → `hh_parser` module | Hand-history parsing |
| **Analytics store** | ClickHouse | Hands/tournaments/actions, graphs, leak finders |
| **App state** | PostgreSQL (shared with Supabase Auth) | Mutable state, import jobs, saved filters |
| **Raw HH staging** | MinIO (S3) | Transient upload staging |
| **Parse queue** | Redis | Async parse jobs |
| **Auth** | Supabase Auth (GoTrue), self-hosted | FastAPI validates JWT (JWKS / HS256 in dev) |
| **Frontend** | Next.js (`apps/web`) | Presentation only — consumes the FastAPI OpenAPI client |

**Ingestion pipeline:** raw text → stream to MinIO → parse asynchronously (Rust) →
batch-insert into ClickHouse.

### Key invariants
- **Never single-row insert into ClickHouse.** All writes go through `ClickHouseBatcher`
  (`apps/api/src/spin2note_api/clickhouse/batcher.py`): blocks of ≥1000 rows or a 1s timer flush.
- **Every entity id is UUIDv7** (`domain/ids.py`). For time-range queries use the explicit
  `played_at` column (UUIDv7 is not ClickHouse-sortable by time).
- ClickHouse primary key: `(user_id, tournament_format, effective_stack_bb, hand_id)`;
  `effective_stack_bb` is `UInt16` (BB×10). Opponents are anonymized via `sipHash64` → `villain_hash`.

---

## Layout

```
apps/
  api/    FastAPI service — src/spin2note_api/:
            domain/      UUIDv7 ids, enums, parsed models
            parser/      wrapper over the hh_parser Rust module
            clickhouse/  async batcher, client, migration runner
            cache/       Redis queue
            ingest/      MinIO upload
            db/          Postgres
            http/        routers, JWT
            worker.py    parse pipeline
  web/    Next.js frontend (presentation only)
crates/
  hh-parser/  Rust parser + PyO3 bindings
migrations/
  clickhouse/*.sql
  postgres/   (Alembic)
testdata/{3max,6max}/   sample logs for parser regression tests
railway.json            Railway-specific deploy config
docker-compose.yml      local infra (clickhouse, postgres, redis, minio, gotrue, api, worker, web)
```

---

## Quick start

### Local infrastructure (from repo root)
```bash
docker compose up -d   # clickhouse, postgres, redis, minio, gotrue (+ api, worker, web)
```

### Backend (from `apps/api/`)
```bash
uv sync --dev                                                              # install deps
uv run maturin develop --manifest-path ../../crates/hh-parser/Cargo.toml   # build hh_parser
uv run uvicorn spin2note_api.main:app --reload                             # API → http://localhost:8000/docs
uv run python -m spin2note_api.worker                                      # parse-pipeline worker
```

### Frontend (from `apps/web/`)
```bash
npm install
npm run dev        # http://localhost:3000
```

---

## Tests & checks

```bash
# Backend (from apps/api/)
uv run pytest                       # tests incl. batcher contract
uv run ruff check . && uv run mypy src
cargo test --manifest-path ../../crates/hh-parser/Cargo.toml

# Frontend (from apps/web/)
npm run typecheck && npm run lint
```

---

## Tooling (slash commands)

| Command | Purpose |
|---------|---------|
| `/db-migrate` | Apply ClickHouse SQL migrations + Alembic |
| `/parse-validate` | Regression-test the parser on 3-max and 6-max samples |
| `/generate-client` | Regenerate the frontend API client from the OpenAPI spec |

---

## Deployment

Cloud-agnostic, 12-factor: plain Docker + env-var config. Railway specifics live only in
`railway.json` — swap any DSN/URL to move off Railway. Merges to `main` trigger GitHub Actions
(lint, type-check, parser tests) and deploy.

---

## License

**Proprietary — All rights reserved.** This source is published for reference only; no usage,
copying, modification, or deployment is permitted without prior written permission. See
[`LICENSE`](./LICENSE). Licensing inquiries: a.grenkov@gmail.com
