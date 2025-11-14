from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_run_evals_mock(tmp_path: Path):
    claims_file = tmp_path / "claims.jsonl"
    claims_file.write_text(
        "\n".join(
            [
                json.dumps({"id": "true", "claim": "Unit test true claim", "label": 1.0}),
                json.dumps({"id": "false", "claim": "Unit test false claim", "label": 0.0}),
            ]
        )
    )
    out_path = tmp_path / "out.json"

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
        "--mock",
        "--prompt-version",
        "rpl_g5_v2",
        "--B",
        "50",
    ]
    subprocess.run(cmd, check=True)

    data = json.loads(out_path.read_text())
    assert data["provider"] == "openai"
    assert data["logical_model"] == "gpt-5"
    assert isinstance(data["results"], list)
    assert len(data["results"]) == 2
    metrics = data["metrics"]
    assert "brier" in metrics
    assert "ece" in metrics
    assert metrics["count"] == 2
