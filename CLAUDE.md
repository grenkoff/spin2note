# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Stack (decided 2026-06-11, first session)
- **Backend:** Python 3.12 + **FastAPI** (API/glue/analytics). Package manager: **uv**.
- **Hot path:** hand-history parsing in **Rust** (`crates/hh-parser`), exposed to Python via
  **PyO3/maturin** as the `hh_parser` module. Heavy aggregation runs inside ClickHouse, so the
  only CPU-bound work left in app code is parsing — hence Rust there, Python everywhere else.
- **Stores (polyglot persistence):** **ClickHouse** (analytics/graphs), **PostgreSQL** (mutable
  app state, shared with Supabase Auth), **MinIO** (raw HH staging), **Redis** (parse queue).
- **Auth:** self-hosted **Supabase Auth (GoTrue)**; FastAPI validates JWT (JWKS, or HS256 secret
  in local dev). No bespoke crypto.
- **Frontend (later):** Next.js, **presentation-only** — never put parsing/ClickHouse/GTO or any
  business logic in Next; it consumes the FastAPI OpenAPI client.
- **Portability:** cloud-agnostic. Everything is plain Docker + env-var config (12-factor).
  Railway specifics live only in `railway.json`; swap any DSN/URL to move off Railway.

## Layout
- `apps/api/` — FastAPI service. Source under `src/spin2note_api/`:
  `domain/` (UUIDv7 ids, enums, parsed models), `clickhouse/` (async **batcher**, client,
  migration runner), `cache/` (Redis queue), `ingest/` (MinIO upload), `parser/` (wrapper over
  `hh_parser`), `db/` (Postgres), `http/` (routers, JWT), `worker.py` (pipeline).
- `crates/hh-parser/` — Rust parser + PyO3 bindings.
- `migrations/clickhouse/*.sql` and `migrations/postgres/` (Alembic).
- `testdata/{3max,6max}/` — sample logs for `/parse-validate`.

## Build, Run & Test
All Python commands run from `apps/api/`:
```bash
uv sync --dev                                                   # install deps
uv run maturin develop --manifest-path ../../crates/hh-parser/Cargo.toml  # build hh_parser
uv run uvicorn spin2note_api.main:app --reload                  # API → http://localhost:8000/docs
uv run python -m spin2note_api.worker                           # parse-pipeline worker
uv run pytest                                                   # tests (incl. batcher contract)
uv run pytest tests/test_batcher.py::test_size_triggered_blocks_are_full_and_lossless  # one test
uv run ruff check . && uv run mypy src                          # lint + types
cargo test --manifest-path ../../crates/hh-parser/Cargo.toml    # Rust tests
```
Local infra (from repo root): `docker compose up -d` (clickhouse, postgres, redis, minio, gotrue).

## Slash commands
- `/db-migrate` — apply ClickHouse SQL migrations + Alembic.
- `/parse-validate` — regression-test the parser on 3-max and 6-max samples.
- `/generate-client` — regenerate the frontend client from the OpenAPI spec.

## Non-negotiable invariants
- **Never single-row insert into ClickHouse.** All writes go through `ClickHouseBatcher`
  (`apps/api/src/spin2note_api/clickhouse/batcher.py`): blocks of ≥1000 rows, or a 1s timer flush.
- Every entity id is **UUIDv7** (`domain/ids.py`). For time-range queries use the explicit
  `played_at` column — ClickHouse does not sort UUIDv7 chronologically.
- ClickHouse primary key is `(user_id, tournament_format, effective_stack_bb, hand_id)`;
  `effective_stack_bb` is `UInt16` (BB×10). Opponents are anonymized via `sipHash64` → `villain_hash`.

---

# Spin&Gold SaaS Analytics System (High-Performance Poker Engine) — Project Brief

## 1. Project Vision & Role
You are a critical-thinking, pragmatic Principal Software Architect and Full-Stack Developer. Your goal is to build a high-performance, single-locale (`en`), UUID-first SaaS platform for GGPoker/PokerOK Spin&Gold analytics (supporting both 3-max and 6-max formats). 

**Your Operational Mindset:**
- **Autonomy with Guardrails:** You have total freedom to select the optimal technology stack (e.g., Rust, Go, Node.js, or Python) based strictly on performance, single-developer maintainability, and Railway deployment constraints. 
- **Critical Thinking:** Do not blindly accept sub-optimal patterns. If a feature or architectural decision can be implemented better, faster, or cheaper on Railway, you must pause, document your reasoning, and ask the user for confirmation.
- **Single Developer Efficiency:** Prioritize automated workflows, robust open-source integrations, and bulletproof Type safety to ensure one developer can manage the entire system.

---

## 2. Dynamic Architecture & Domain Requirements

### 2.1 Multi-Format Hand History Ingestion & Parsing
- **Variable Tables:** Support both 3-max and 6-max Spin&Gold tournament formats dynamically.
- **Deep Stacks Support:** Nash equilibrium and EV calculations must scale beyond 25 BB to handle deep-stack play occurring in high-multiplier tournaments.
- **Pipeline:** Ingest raw text -> Stream to MinIO -> Parse asynchronously -> Batch-insert to ClickHouse.
- **Anonymization:** Hash or abstract opponent identities to maintain aggregate pool statistics without inflating the database unique-string index.

### 2.2 ClickHouse Performance Engine
- Every entity must use **UUIDv7** (time-ordered) as the primary identifier to ensure fast sequential writes and merging in ClickHouse.
- Optimize table engines (`ReplacingMergeTree`, `SummingMergeTree`) and primary keys `(user_id, tournament_format, effective_stack, hand_id)` for lightning-fast aggregated queries (Graphs, Hero/Field Leak Finders).
- **Strict Rule:** Never perform single-row inserts into ClickHouse. Implement an internal buffering/batching mechanism (minimum 1,000+ rows per block).

### 2.3 GTO & Training Module
- High-speed lookup structures for HRC-scraped Nash tables (handling 3-max/6-max pre-flop actions up to deep-stack limits).
- Gamified Trainer that logs user mistakes and evaluates action EV against the exact GTO matrix, exposing errors in a dedicated review UI.

---

## 3. Technology Stack Selection Rules
- **Backend & Parsing:** Evaluate performance bottlenecks. If text parsing of millions of hands or aggregate calculations require absolute speed, choose Go or Rust. If ecosystem maturity and fast delivery win, use Python/FastAPI or TypeScript/Node.js. You must justify your stack choice in the first session.
- **API Documentation:** Every backend service must strictly expose an auto-generated, interactive **Swagger/OpenAPI** specification.
- **Auth:** Drop-in open-source solutions only (e.g., Supabase Auth, Ory, or Clerk if applicable). No bespoke auth crypto.
- **UI & Styling:** Build a unified, local Design System (e.g., using Tailwind CSS tokens + Radix/Shadcn primitives). No ad-hoc, hardcoded styling.

---

## 4. Git Workflow, CI/CD & Railway Deployment
- **Branching Strategy:** Standard GitHub workflow. Features are developed on separate branches.
- **Automation Pipeline:** Merging or opening a Pull Request to `main` must trigger automated GitHub Actions (linting, type-checking, parser tests) and automatically deploy to **Railway** via its native Nixpacks/Docker integration.
- Ensure all environment configurations, Dockerfiles, or Railway blueprints (`railway.json`) are optimized for Private Networking and resource-efficient vertical scaling.

---

## 5. Claude Code Templates & Workspace Integration
Analyze the `davila7/claude-code-templates` repository patterns and automatically implement the tools best suited for this project:
- **Slash Commands Required:**
  - `/db-migrate` - Automatically detect and apply schemas/migrations for ClickHouse and relational DBs.
  - `/parse-validate` - Run end-to-end regression tests on sample 3-max and 6-max GGPoker hand history logs.
  - `/generate-client` - Regenerate frontend API clients based on the backend Swagger/OpenAPI spec.
- **Git Hooks:** Enforce strict pre-commit hooks for linting, format checks against the Design System, and static analysis.
- **MCP (Model Context Protocol):** Configure local filesystem and GitHub MCP servers to automate context management during refactoring and PR reviews.

---

## 6. Communication Protocol
- If a prompt request violates performance principles (e.g., slow SQL joins, unbuffered ClickHouse inserts) or introduces single-developer technical debt, **stop and challenge it**.
- Provide architectural trade-offs before generating large blocks of code.
- Keep responses concise, focusing on structural accuracy and scannable code blocks.
