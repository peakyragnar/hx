from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_run_evals_script_mock(tmp_path: Path) -> None:
    claims_file = Path("tests/data/eval_claims_smoke.jsonl")
    assert claims_file.exists(), "smoke claims file missing"

    out_path = tmp_path / "results.json"

    cmd = [
        sys.executable,
        "scripts/run_evals.py",
        "--claims-file",
        str(claims_file),
        "--out",
        str(out_path),
        "--provider",
        "openai",
        "--logical-model",
        "gpt-5",
        "--mode",
        "baseline",
        "--K",
        "4",
        "--R",
        "1",
        "--T",
        "2",
        "--B",
        "4",
        "--max-output-tokens",
        "48",
        "--mock",
    ]

    subprocess.run(cmd, check=True, cwd=Path(__file__).resolve().parents[2])

    payload = json.loads(out_path.read_text())
    assert isinstance(payload, dict)
    assert isinstance(payload.get("results"), list)
    assert payload.get("results"), "Expected at least one eval result"
    first = payload["results"][0]
    assert "claim" in first
    assert "prob" in first
    metrics = payload.get("metrics")
    assert metrics is not None
    assert "brier" in metrics
