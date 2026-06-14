---
description: Generate tests for a target (module/function/file) following this repo's conventions, then run them
argument-hint: <target> — e.g. spin2note_api.clickhouse.queries, apps/api/src/.../worker.py, or crates/hh-parser
allowed-tools: Read, Edit, Write, Bash(cd*), Bash(uv*), Bash(cargo*), Bash(. *)
---

Generate tests for **$ARGUMENTS** that match how this project already writes tests, then run
them and confirm they pass. Do not invent a new style — mirror the existing tests.

## 1. Read the target and a sibling test
- Read the target code (`$ARGUMENTS`) and identify the behaviours worth covering: happy path,
  edge cases, error paths, and any invariant the code protects (e.g. "never single-row insert",
  "dedup skips existing", "Rust hand_id == Python").
- Read the closest existing test to copy its conventions. Map of patterns:
  - **`tests/test_batcher.py`** — pure async unit test with an injected spy `insert_fn`; asserts
    block sizes / no-loss. Use for batcher/queue/pure-logic code.
  - **`tests/test_worker.py`** — stubs `FakeCH` (async `query` returning canned `result_rows`)
    and a `CollectBatcher` subclass; `pytest.importorskip("hh_parser")` then `# noqa: E402`
    imports; fixtures read from `TESTDATA = parents[3]/"testdata"`. Use for worker/parser-backed.
  - **`tests/test_api.py`** — FastAPI `TestClient` + `app.dependency_overrides` for `require_user`
    / `get_api_client`, and `monkeypatch.setattr(queries, ...)`. Use for HTTP routes.
  - **`tests/test_native.py`** / **`tests/test_queries.py`** — fake ClickHouse conn/client that
    counts calls; assert serialization / batching invariants. Use for clickhouse layer.

## 2. Write the test
- **Python:** create/extend `apps/api/tests/test_<area>.py`. Rules: `from __future__ import
  annotations`; `asyncio_mode=auto` (async tests are plain `async def test_...`, no decorator);
  if it imports the compiled parser, add `pytest.importorskip("hh_parser")` before those imports;
  never hit real ClickHouse/Postgres/Redis/MinIO — stub them (reuse `FakeCH`/`CollectBatcher`
  patterns); read sample data from `testdata/` not the gitignored `testdata/real/`. Keep line
  length ≤100 (ruff).
- **Rust:** add an inline `#[cfg(test)] mod tests { ... }` block in the relevant
  `crates/hh-parser/src/*.rs` (see `parser.rs`/`summary.rs`), with `const` fixtures inline.
- **Frontend:** no test setup exists yet — if asked, propose adding Vitest first, don't fake it.

## 3. Run and confirm (must pass before finishing)
```bash
cd apps/api && uv run ruff check . && uv run mypy src && uv run pytest -q   # Python
cargo test --manifest-path crates/hh-parser/Cargo.toml                      # Rust (from repo root)
```
If a Python test needs the parser, build it once: `uv run maturin develop --manifest-path
../../crates/hh-parser/Cargo.toml`. Report which cases were added and the passing result. Never
weaken an assertion to make it pass — fix the test or surface the real bug.
