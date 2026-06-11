---
description: Regenerate the typed frontend API client from the backend OpenAPI spec
allowed-tools: Bash(cd*), Bash(uv*), Bash(curl*), Bash(npx*)
---

Regenerate the frontend API client from the live OpenAPI 3.1 spec exposed by FastAPI.

1. Make sure the API is running (or start it):
   ```bash
   cd apps/api && uv run uvicorn spin2note_api.main:app --port 8000 &
   ```
2. Export the OpenAPI document:
   ```bash
   curl -s http://localhost:8000/openapi.json -o apps/web/openapi.json
   ```
3. Generate the typed client (frontend lives in `apps/web`; create it if missing — Next.js,
   presentation-only, no backend logic):
   ```bash
   cd apps/web && npx openapi-typescript openapi.json -o src/lib/api/schema.ts
   ```

The frontend never reimplements business logic — it only consumes these typed endpoints.
Report the generated path and any spec/client drift.
