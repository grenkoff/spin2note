---
description: Stop the full local dev stack (frontend + API + docker infra) brought up by /server-up
allowed-tools: Bash(docker*), Bash(pgrep*), Bash(kill*), Bash(xargs*), Bash(curl*), Bash(cd*)
---

Tear down everything `/server-up` started, in reverse order: local processes first, then Docker.
This is the counterpart to `/server-up`. If `$ARGUMENTS` names a layer (`web`, `api`, `infra`),
stop only that one; otherwise stop all.

Data is preserved: we `docker compose stop` (not `down`), so containers and named volumes survive
and `/server-up` restarts fast with the same DB contents.

**Run each kill below as its OWN Bash call — do NOT chain them on one line.** A combined
`pkill … ; pkill …` line has repeatedly aborted after the first command (exit 144) and left the
API alive. Killing by PID via `pgrep | xargs` is deterministic and won't signal the wrong process.

## 1. Frontend (Next.js, port 3000)
```bash
pgrep -f "next dev" | xargs -r kill 2>/dev/null; true
```
(`npm run dev` spawns `next dev` / `next-server`; the pattern catches the tree.)

## 2. API (uvicorn, port 8000) — separate Bash call
```bash
pgrep -f "spin2note_api.main:app" | xargs -r kill 2>/dev/null; true
```
Match on `spin2note_api.main:app` (NOT `uvicorn …`): the server runs as `uv run uvicorn …`, so the
`uvicorn` token only appears on the inner process — the `uv run` wrapper and the reloader's child
would survive and keep port 8000 open. The bare module pattern catches the whole tree. If `:8000`
still answers in step 4, re-run this line (or `kill -9` the leftover PIDs from `pgrep -af`).

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
