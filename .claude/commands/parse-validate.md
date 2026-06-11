---
description: Regression-test the HH parser on 3-max and 6-max sample logs
allowed-tools: Bash(cd*), Bash(uv*), Bash(maturin*)
---

Run end-to-end regression validation of the Rust `hh_parser` against the sample logs in
`testdata/3max` and `testdata/6max`.

1. Ensure the extension is built and importable:
   ```bash
   cd apps/api && uv run maturin develop --manifest-path ../../crates/hh-parser/Cargo.toml
   ```
2. Parse each sample and check format, structure and chip conservation (net result ~0):
   ```bash
   cd apps/api && uv run python - <<'PY'
   from pathlib import Path
   from spin2note_api.parser import detect_format, parse

   root = Path("../../testdata")
   for fmt_dir, expected in [("3max", "3max"), ("6max", "6max")]:
       for path in sorted((root / fmt_dir).glob("*.txt")):
           raw = path.read_text()
           hands = parse(raw)
           assert hands, f"{path}: no hands parsed"
           assert all(h["format"] == expected for h in hands), f"{path}: format mismatch"
           for h in hands:
               net = sum(p["result"] for p in h["players"])
               assert abs(net + h["rake"]) < 1e-6, f"{path}/{h['source_hand_id']}: net={net}"
           print(f"OK {path.name}: {len(hands)} hands, format={expected}")
   print("parse-validate: PASS")
   PY
   ```
   To validate against a private real export, point `root` at `testdata/real/handhistory`
   (gitignored). The full pytest suite (`uv run pytest`) also exercises the domain mapping.
3. Run the Rust unit tests too:
   ```bash
   cargo test --manifest-path crates/hh-parser/Cargo.toml
   ```

Report PASS/FAIL per sample set (both 3-max and 6-max must pass). When the parser gains
full street/action extraction, extend this with snapshot comparisons.
