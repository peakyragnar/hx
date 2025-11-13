from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console
from rich.table import Table

from heretix.provider.json_utils import extract_and_validate
from heretix.schemas import CombinedBlockV1, PriorBlockV1, RPLSampleV1


def _raw_payload() -> str:
    payload = {
        "belief": {"prob_true": "0.64", "label": "likely"},
        "reasons": ["CPI prints are cooling"],
        "assumptions": ["No new tariffs"],
        "uncertainties": ["Energy shocks"],
    }
    return f"LLM output (mock):```json\n{json.dumps(payload)}\n```<eom>"


def test_schema_pipeline_rich_logging(tmp_path: Path):
    console = Console(record=True, width=120)
    console.rule("Schema pipeline smoke test")

    sample, warnings = extract_and_validate(_raw_payload(), RPLSampleV1)
    console.log("parsed_sample", sample.model_dump(), warnings)

    prior = PriorBlockV1(
        prob_true=sample.belief.prob_true,
        ci_lo=0.52,
        ci_hi=0.74,
        width=0.22,
        stability=0.88,
        compliance_rate=0.97,
    )
    combined = CombinedBlockV1(
        prob_true=0.62,
        ci_lo=0.5,
        ci_hi=0.73,
        label="Likely true",
        weight_prior=0.75,
        weight_web=0.25,
    )

    table = Table(title="Schema objects", expand=True)
    table.add_column("Component", style="bold cyan")
    table.add_column("prob_true")
    table.add_column("ci")
    table.add_column("notes", overflow="fold")
    table.add_row("Prior", f"{prior.prob_true:.2f}", f"[{prior.ci_lo:.2f},{prior.ci_hi:.2f}]", "stability=0.88")
    table.add_row("Combined", f"{combined.prob_true:.2f}", f"[{combined.ci_lo:.2f},{combined.ci_hi:.2f}]", "weights=0.75/0.25")
    console.print(table)

    log_path = tmp_path / "schema_pipeline.log"
    log_text = console.export_text(clear=False)
    log_path.write_text(log_text)

    assert "Schema pipeline smoke test" in log_text
    assert "json_repaired_simple" in log_text  # markdown fence removal
    assert "validation_coerced" in log_text  # string -> float coercion
    assert "weights=0.75/0.25" in log_text
    assert log_path.exists()
