# Smoke Tests (New Harness)

This suite validates the end-to-end pipeline without hitting the network, using a deterministic mock provider.

## Why
- Verify prompt YAML loading, deterministic sampler, compliance filter, frozen aggregation, SQLite writes, and CLI output.
- Catch schema or storage issues (e.g., seed overflow) before real runs.

## How to Run
- CLI smoke (recommended):
```
uv run heretix run --config runs/rpl_example.yaml --out runs/smoke.json --mock
```
- Module form (bypasses entry point):
```
uv run -m heretix.cli run --config runs/rpl_example.yaml --out runs/smoke.json --mock
```

Expected:
- A compact summary is printed (p, CI, stability, compliance, cache).
- JSON written to `runs/smoke.json`.
- SQLite database `runs/heretix.sqlite` contains the run in `runs` and sample rows in `samples`.

## Pytest (optional, if installed)
- There is a minimal test at `heretix/tests/test_smoke.py` that uses the mock provider.
- If `pytest` is available in your environment:
```
uv run -m pytest heretix/tests/test_smoke.py -q
```

Note: The repository uses uv. We do not fetch dev dependencies automatically; the CLI smoke path does not require pytest.
