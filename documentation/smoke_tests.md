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

## Pytest (optional)
- Phase‑1 new harness tests live in `heretix/tests/` and are the default test path via `pytest.ini`.
- Install test extras (one-time):
```
uv sync --extra test
```
- Then run the new harness suite (default):
```
uv run pytest -q
```

- To also run legacy tests explicitly:
```
uv run pytest heretix/tests legacy/tests -q
```

Note: The repository uses uv. We do not fetch dev dependencies automatically; the CLI smoke path does not require pytest.
