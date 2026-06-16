---
description: Stop the full local dev stack (frontend + API + docker infra) brought up by /server-up
allowed-tools: Bash(docker*), Bash(pkill*), Bash(curl*), Bash(cd*)
---

Tear down everything `/server-up` started, in reverse order: local processes first, then Docker.
This is the counterpart to `/server-up`. If `$ARGUMENTS` names a layer (`web`, `api`, `infra`),
stop only that one; otherwise stop all.

Data is preserved: we `docker compose stop` (not `down`), so containers and named volumes survive
and `/server-up` restarts fast with the same DB contents.

## 1. Frontend (Next.js, port 3000)
```bash
pkill -f "next dev" || true
```
(`npm run dev` spawns `next dev` / `next-server`; the pattern catches the tree.)

## 2. API (uvicorn, port 8000)
```bash
pkill -f "spin2note_api.main:app" || true
```
Match on `spin2note_api.main:app` (NOT `uvicorn …`): the server runs as `uv run uvicorn …`, so
the `uvicorn` token only appears on the inner process — the `uv run` wrapper and the reloader's
child would survive and keep port 8000 open. The bare module pattern catches the whole tree.
If anything still answers on :8000 afterwards, fall back to killing by PID
(`pgrep -af "spin2note_api.main:app"` then `kill <pids>`).

## 3. Backing infra (Docker)
```bash
docker compose stop
```
Stops clickhouse, postgres, redis, minio, auth (and any others) without deleting them.
Use `docker compose down` instead ONLY if explicitly asked to remove containers; never add `-v`
unless the user explicitly wants to wipe data (that destroys the volumes).

## 4. Verify everything is down
```bash
curl -s -o /dev/null -w 'api  %{http_code}\n' http://localhost:8000/health 2>&1 || echo 'api  down'
curl -s -o /dev/null -w 'web  %{http_code}\n' http://localhost:3000 2>&1        || echo 'web  down'
docker compose ps --format '{{.Service}}\t{{.Status}}'
```
The two curls should fail to connect (port closed); `docker compose ps` should list nothing running.

## Output
Report a compact table: layer -> stopped/still-up. Note that DB data is retained (volumes intact);
a later `/server-up` resumes from the same state.
