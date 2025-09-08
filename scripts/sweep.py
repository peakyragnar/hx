#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import median
from typing import Any, Dict, List

import yaml

from heretix.config import load_run_config, RunConfig
from heretix.rpl import run_single_version
import heretix as _heretix_pkg
from dotenv import load_dotenv


def _read_claims(path: Path) -> List[str]:
    claims: List[str] = []
    for line in path.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        try:
            obj = json.loads(s)
            if isinstance(obj, dict) and "claim" in obj:
                claims.append(str(obj["claim"]))
            elif isinstance(obj, str):
                claims.append(obj)
            else:
                claims.append(s)
        except Exception:
            claims.append(s)
    return claims


def _prompt_path_for_version(cfg: RunConfig, version: str) -> Path:
    if cfg.prompts_file:
        return Path(cfg.prompt_file_path)
    return Path(_heretix_pkg.__file__).parent / "prompts" / f"{version}.yaml"


def _pqs_v1(width: float, stability: float, compliance: float) -> int:
    return int(100 * (0.4 * stability + 0.4 * (1 - min(width, 0.5) / 0.5) + 0.2 * compliance))


def main() -> None:
    # Load environment variables from .env so OPENAI_API_KEY works like the CLI
    try:
        load_dotenv()
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Run a prompt version across a cohort of claims and produce a simple HTML summary.")
    ap.add_argument("--claims-file", required=True, help="Path to text/JSONL file with one claim per line")
    ap.add_argument("--config", required=True, help="Path to run config YAML/JSON (single-claim config)")
    ap.add_argument("--prompt-version", required=True, help="Prompt version to run (e.g., rpl_g5_v2)")
    ap.add_argument("--mock", action="store_true", help="Use mock provider (no network)")
    ap.add_argument("--out-jsonl", default=None, help="Output JSONL path (default runs/sweeps/<version>.jsonl)")
    ap.add_argument("--out-html", default=None, help="Output HTML path (default runs/reports/cohort_<version>.html)")
    args = ap.parse_args()

    claims_path = Path(args.claims_file)
    if not claims_path.exists():
        raise SystemExit(f"claims_file not found: {claims_path}")
    claims = _read_claims(claims_path)
    if not claims:
        raise SystemExit("claims_file is empty (no claims to run)")

    cfg = load_run_config(args.config)
    version = args.prompt_version
    out_jsonl = Path(args.out_jsonl) if args.out_jsonl else Path("runs/sweeps") / f"{version}.jsonl"
    out_html = Path(args.out_html) if args.out_html else Path("runs/reports") / f"cohort_{version}.html"

    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    out_html.parent.mkdir(parents=True, exist_ok=True)

    results: List[Dict[str, Any]] = []
    with out_jsonl.open("w") as jf:
        for i, claim in enumerate(claims, 1):
            local = RunConfig(**{**cfg.__dict__})
            local.claim = claim
            local.prompt_version = version
            prompt_file = _prompt_path_for_version(local, version)
            print(f"[{i}/{len(claims)}] {version} :: {claim[:60]}{'...' if len(claim)>60 else ''}")
            res = run_single_version(local, prompt_file=str(prompt_file), mock=bool(args.mock))
            jf.write(json.dumps(res) + "\n")
            results.append(res)

    # Build a simple cohort summary HTML
    rows = []
    widths: List[float] = []
    stabs: List[float] = []
    comps: List[float] = []
    pqss: List[int] = []
    for r in results:
        a = r.get("aggregates", {})
        width = float(a.get("ci_width") or 0.0)
        stab = float(a.get("stability_score") or 0.0)
        comp = float(a.get("rpl_compliance_rate") or 0.0)
        pqs = _pqs_v1(width, stab, comp)
        widths.append(width)
        stabs.append(stab)
        comps.append(comp)
        pqss.append(pqs)
        rows.append(
            {
                "claim": r.get("claim", ""),
                "p": float(a.get("prob_true_rpl") or 0.0),
                "lo": float((a.get("ci95") or [0.0, 0.0])[0]),
                "hi": float((a.get("ci95") or [0.0, 0.0])[1]),
                "width": width,
                "stab": stab,
                "comp": comp,
                "pqs": pqs,
            }
        )

    def med(xs: List[float]) -> float:
        return float(median(xs)) if xs else float("nan")

    agg = {
        "n": len(rows),
        "width_med": med(widths),
        "stab_med": med(stabs),
        "comp_mean": (sum(comps) / len(comps)) if comps else float("nan"),
        "pqs_med": float(median(pqss)) if pqss else float("nan"),
    }

    css = """
    body { font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif; margin: 24px; color: #222; }
    h1 { font-size: 20px; margin: 0 0 16px; }
    h2 { font-size: 16px; margin: 24px 0 8px; }
    table { border-collapse: collapse; margin-top: 12px; width: 100%; }
    th, td { border: 1px solid #ddd; padding: 6px 8px; text-align: left; font-size: 13px; }
    th { background: #f7f7f7; }
    code { background: #f2f2f2; padding: 1px 4px; border-radius: 3px; }
    .muted { color: #666; }
    """

    rows_html = "".join(
        f"<tr><td>{i+1}</td><td>{r['p']:.3f}</td><td>[{r['lo']:.3f},{r['hi']:.3f}]</td><td>{r['width']:.3f}</td><td>{r['stab']:.3f}</td><td>{r['comp']:.2f}</td><td>{r['pqs']}</td><td>{json.dumps(r['claim'])}</td></tr>"
        for i, r in enumerate(rows)
    )
    html_doc = f"""
    <!doctype html>
    <meta charset=\"utf-8\" />
    <title>Cohort Summary — {version}</title>
    <style>{css}</style>
    <h1>Cohort Summary — {version}</h1>
    <div class=\"muted\">Claims file: {claims_path}</div>
    <h2>Aggregates</h2>
    <table><thead><tr><th>N</th><th>Median CI width</th><th>Median Stability</th><th>Mean Compliance</th><th>Median PQS</th></tr></thead>
      <tbody><tr><td>{agg['n']}</td><td>{agg['width_med']:.3f}</td><td>{agg['stab_med']:.3f}</td><td>{agg['comp_mean']:.2f}</td><td>{agg['pqs_med']:.0f}</td></tr></tbody>
    </table>
    <h2>Per-Claim Metrics</h2>
    <table><thead><tr><th>#</th><th>p_RPL</th><th>CI95</th><th>Width</th><th>Stability</th><th>Compliance</th><th>PQS</th><th>Claim</th></tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
    """
    out_html.write_text(html_doc, encoding="utf-8")
    print(f"Wrote {out_jsonl}")
    print(f"Wrote {out_html}")


if __name__ == "__main__":
    main()
