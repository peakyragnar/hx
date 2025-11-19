#!/usr/bin/env python

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Iterable, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from heretix.config import RunConfig
from heretix.rpl import run_single_version


def load_claims(path: Path) -> List[dict]:
    claims: List[dict] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        claims.append(json.loads(line))
    return claims


def brier_score(pairs: Iterable[Tuple[float, float]]) -> float | None:
    values = list(pairs)
    if not values:
        return None
    return sum((p - y) ** 2 for p, y in values) / len(values)


def expected_calibration_error(pairs: Iterable[Tuple[float, float]], bins: int = 10) -> float | None:
    values = list(pairs)
    if not values:
        return None
    bin_sums = [0.0] * bins
    bin_actual = [0.0] * bins
    bin_counts = [0] * bins
    for prob, label in values:
        idx = min(bins - 1, max(0, int(prob * bins)))
        bin_sums[idx] += prob
        bin_actual[idx] += label
        bin_counts[idx] += 1
    total = len(values)
    ece = 0.0
    for i in range(bins):
        if bin_counts[i] == 0:
            continue
        avg_pred = bin_sums[i] / bin_counts[i]
        avg_true = bin_actual[i] / bin_counts[i]
        ece += (bin_counts[i] / total) * abs(avg_pred - avg_true)
    return ece


def main() -> None:
    parser = argparse.ArgumentParser(description="Run calibration evals over a claims file.")
    parser.add_argument("--claims-file", type=Path, default=Path("cohort/evals/claims_calibration.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("evals/eval_results.json"))
    parser.add_argument("--provider", required=True)
    parser.add_argument("--logical-model", required=True)
    parser.add_argument("--mode", choices=("baseline", "web_informed"), default="baseline")
    parser.add_argument("--prompt-version", default="rpl_g5_v2")
    parser.add_argument("--K", type=int, default=4)
    parser.add_argument("--R", type=int, default=1)
    parser.add_argument("--T", type=int, default=4)
    parser.add_argument("--B", type=int, default=200)
    parser.add_argument("--max-output-tokens", type=int, default=256)
    parser.add_argument("--max-prompt-chars", type=int, default=2000)
    parser.add_argument("--mock", action="store_true", help="Use deterministic mock provider")
    args = parser.parse_args()

    if args.mode != "baseline":
        parser.error("run_evals.py currently supports --mode baseline only; use the CLI for web_informed runs.")

    claims = load_claims(args.claims_file)
    results = []
    metric_pairs: List[Tuple[float, float]] = []

    for entry in claims:
        cfg = RunConfig(
            claim=str(entry.get("claim")),
            model=args.logical_model,
            logical_model=args.logical_model,
            provider=args.provider,
            prompt_version=args.prompt_version,
            K=args.K,
            R=args.R,
            T=args.T,
            B=args.B,
            max_output_tokens=args.max_output_tokens,
            max_prompt_chars=args.max_prompt_chars,
        )
        run = run_single_version(
            cfg,
            prompt_file=str(
                Path(__file__).resolve().parents[1] / "heretix" / "prompts" / f"{args.prompt_version}.yaml"
            ),
            mock=args.mock,
        )
        aggregates = run.get("aggregates", {})
        prob_val = aggregates.get("prob_true_rpl")
        if prob_val is None:
            prob_val = aggregates.get("prob_true")
        prob_num = None
        if prob_val is not None:
            try:
                prob_num = float(prob_val)
            except (TypeError, ValueError):
                prob_num = None
        label = entry.get("label")
        if isinstance(label, (int, float)) and prob_num is not None and not math.isnan(prob_num):
            metric_pairs.append((float(prob_num), float(label)))
        results.append(
            {
                "id": entry.get("id"),
                "claim": entry.get("claim"),
                "label": label,
                "prob": prob_num,
                "ci95": aggregates.get("ci95"),
            }
        )

    metrics = {
        "brier": brier_score(metric_pairs),
        "ece": expected_calibration_error(metric_pairs),
        "count": len(metric_pairs),
    }

    payload = {
        "provider": args.provider,
        "logical_model": args.logical_model,
        "mode": args.mode,
        "mock": args.mock,
        "claims_file": str(args.claims_file),
        "results": results,
        "metrics": metrics,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
