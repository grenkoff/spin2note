---
description: Bring up the full local dev stack (docker infra + API + frontend) and verify it
allowed-tools: Bash(docker*), Bash(cd*), Bash(uv*), Bash(npm*), Bash(curl*), Bash(export*), Bash(pkill*), Read, Write
---

Bring up the complete local development stack and verify each layer is actually serving.
Run servers in the **background** (`run_in_background: true`); never block on them.

## 0. Why this is not just `docker compose up`
The `api` and `worker` compose services **fail to build** (their Dockerfile copies only
`apps/api/pyproject.toml`, which requires a `README.md` that isn't in the build context →
`OSError: Readme file does not exist: README.md`). So we run the **backing stores in Docker**
but run **API + frontend locally** (uv / npm) instead. Do NOT `docker compose up` without a
service list — it will try to build `api` and abort the whole bring-up.

## 1. Backing infra (Docker)
Start only the stores + auth, then wait for health:
```bash
docker compose up -d clickhouse postgres redis minio auth
docker compose ps --format '{{.Service}}\t{{.Status}}'
```
All five should report `healthy`/`Up`. (`postgres` must be healthy before `auth` starts — compose
handles the ordering.)

## 2. Ensure `apps/api/.env` exists
The local API (uvicorn) needs two overrides that differ from the in-code defaults. Create
`apps/api/.env` if missing (do not clobber an existing one without checking it):
```
# GoTrue signs HS256 tokens with this secret (docker-compose default). The API must validate
# with the SAME secret, otherwise it falls back to the empty JWKS path and returns 401 "invalid token".
SUPABASE_JWT_SECRET=super-secret-jwt-token-change-me

# ClickHouse native TCP is published on host port 9009 (host 9000 is taken by MinIO).
CLICKHOUSE_NATIVE_PORT=9009
```
If you change `.env`, the API must be (re)started to pick it up — settings are read once at boot.

## 3. API (FastAPI, port 8000) — run in background
```bash
cd apps/api && uv run uvicorn spin2note_api.main:app --reload
```
First run also needs the Rust parser built (only if `hh_parser` import fails):
```bash
cd apps/api && uv run maturin develop --manifest-path ../../crates/hh-parser/Cargo.toml
```

## 4. Frontend (Next.js, port 3000) — run in background
`npm`/`node` are **not on PATH**; node lives in `~/.local/node-v22.14.0-linux-x64/bin`.
Prepend it (or discover via `find ~/.local -maxdepth 2 -name node -type f` if that path moved):
```bash
export PATH="$HOME/.local/node-v22.14.0-linux-x64/bin:$PATH"
cd apps/web && npm run dev
```

## 5. Verify (don't declare success until these pass)
```bash
curl -s -o /dev/null -w 'auth  %{http_code}\n' http://localhost:9999/health    # -> 200
curl -s -o /dev/null -w 'api   %{http_code}\n' http://localhost:8000/health     # -> 200
curl -s -o /dev/null -w 'web   %{http_code}\n' http://localhost:3000            # -> 200
```
Optionally confirm JWT validation works end-to-end (valid secret -> 200, wrong -> 401) by minting
an HS256 token (`sub`, `aud=authenticated`, `exp`) with `super-secret-jwt-token-change-me` and
calling `GET /stats/overview` with `Authorization: Bearer <token>`.

## Output
Report a compact table: layer -> URL -> status. Endpoints:
- Frontend (main UI): http://localhost:3000
- API + Swagger:      http://localhost:8000/docs
- GoTrue auth:        http://localhost:9999

Note that databases are likely empty on a fresh bring-up (`/db-show` for a snapshot, `/db-migrate`
if tables are missing).
