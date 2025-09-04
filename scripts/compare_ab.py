#!/usr/bin/env python3
"""
Heretix RPL — A/B Compare (Single Claim)

Compares two prompt versions on the same claim, enforcing parity (model, K/R/T, B,
max_output_tokens). Reads from runs/heretix.sqlite and writes a simple HTML report.

Usage:
  uv run python scripts/compare_ab.py --claim "<claim>" \
      --version-a rpl_g5_v2 --version-b rpl_g5_candidate \
      [--model gpt-5] [--since-days 30] [--out runs/reports/ab.html]

Notes:
  - Picks the latest execution per (claim, version) within the time window.
  - Enforces parity across model, K, R, T, B, and max_output_tokens.
  - Prints a clear winner (gates first, then CI width, stability, PQS, prompt length).
"""
from __future__ import annotations

import argparse
import html
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional
from datetime import datetime, timedelta

DB_DEFAULT = Path("runs/heretix.sqlite")


def fetch_latest_exec(conn: sqlite3.Connection, claim: str, version_like: str, since_days: Optional[int], model: Optional[str]) -> Optional[Dict[str, Any]]:
    where = ["claim=?", "prompt_version LIKE ?"]
    params = [claim, f"{version_like}%"]
    if model:
        where.append("model=?")
        params.append(model)
    if since_days:
        ts_cut = int((datetime.now() - timedelta(days=int(since_days))).timestamp())
        where.append("created_at >= ?")
        params.append(ts_cut)
    sql = (
        "SELECT execution_id, run_id, created_at, claim, model, prompt_version, K, R, T, B, seed, "
        "bootstrap_seed, prob_true_rpl, ci_lo, ci_hi, ci_width, stability_score, rpl_compliance_rate, "
        "cache_hit_rate, prompt_char_len_max FROM executions WHERE " + " AND ".join(where) + " ORDER BY created_at DESC LIMIT 1"
    )
    cur = conn.execute(sql, tuple(params))
    row = cur.fetchone()
    if not row:
        return None
    cols = [d[0] for d in cur.description]
    return {cols[i]: row[i] for i in range(len(cols))}


def gates_and_pqs(rec: Dict[str, Any]) -> Dict[str, Any]:
    width = float(rec["ci_width"])
    stability = float(rec["stability_score"])
    compl = float(rec["rpl_compliance_rate"])
    gate_compliance_ok = compl >= 0.98
    gate_stability_ok = stability >= 0.25
    gate_precision_ok = width <= 0.30
    pqs = int((0.4 * stability + 0.4 * (1 - min(width, 0.5) / 0.5) + 0.2 * compl) * 100)
    return {
        "width": width,
        "stability": stability,
        "compl": compl,
        "gate_compliance_ok": gate_compliance_ok,
        "gate_stability_ok": gate_stability_ok,
        "gate_precision_ok": gate_precision_ok,
        "pqs": pqs,
    }


def decide_winner(a: Dict[str, Any], b: Dict[str, Any]) -> str:
    # Gates first
    a_pass = a["gate_compliance_ok"] and a["gate_stability_ok"] and a["gate_precision_ok"]
    b_pass = b["gate_compliance_ok"] and b["gate_stability_ok"] and b["gate_precision_ok"]
    if a_pass and not b_pass:
        return "A"
    if b_pass and not a_pass:
        return "B"
    # Narrower CI width
    if abs(a["width"] - b["width"]) > 1e-9:
        return "A" if a["width"] < b["width"] else "B"
    # Higher stability
    if abs(a["stability"] - b["stability"]) > 1e-9:
        return "A" if a["stability"] > b["stability"] else "B"
    # Higher PQS
    if a["pqs"] != b["pqs"]:
        return "A" if a["pqs"] > b["pqs"] else "B"
    return "tie"


def render_html(a_row: Dict[str, Any], b_row: Dict[str, Any], a_metrics: Dict[str, Any], b_metrics: Dict[str, Any], out: Path) -> None:
    def pill(label: str, cls: str) -> str:
        return f"<span class=\"pill {cls}\">{html.escape(label)}</span>"

    winner = decide_winner(a_metrics, b_metrics)
    title = f"A/B Compare — {a_row['claim']}"
    css = """
    body { font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif; margin: 24px; color: #222; }
    h1 { font-size: 20px; margin: 0 0 16px; }
    h2 { font-size: 16px; margin: 24px 0 8px; }
    .grid2 { display: grid; grid-template-columns: 280px 1fr 1fr; gap: 6px 12px; max-width: 1100px; }
    .muted { color: #666; }
    code { background: #f2f2f2; padding: 1px 4px; border-radius: 3px; }
    .pill { display:inline-block; padding: 2px 6px; border-radius: 10px; font-size: 12px; }
    .ok { background:#e6f4ea; color:#137333; }
    .warn { background:#fef7e0; color:#b06000; }
    .bad { background:#fce8e6; color:#c5221f; }
    .winner { background:#e8f0fe; padding: 6px 8px; border-radius: 6px; display:inline-block; }
    table { border-collapse: collapse; margin-top: 12px; min-width: 760px; }
    th, td { border: 1px solid #ddd; padding: 6px 8px; text-align: left; font-size: 13px; }
    th { background: #f7f7f7; }
    """

    def fmt_row(label: str, key: str, fmt: str = "{v}", mapper=None) -> str:
        va = a_metrics.get(key) if mapper is None else mapper("A")
        vb = b_metrics.get(key) if mapper is None else mapper("B")
        sa = fmt.format(v=va)
        sb = fmt.format(v=vb)
        return f"<tr><th>{html.escape(label)}</th><td>{html.escape(str(sa))}</td><td>{html.escape(str(sb))}</td></tr>"

    def gate_cell(ok: bool) -> str:
        return pill("PASS", "ok") if ok else pill("FAIL", "bad")

    rows = []
    rows.append(fmt_row("Prompt Version", "", mapper=lambda side: a_row["prompt_version"] if side == "A" else b_row["prompt_version"]))
    rows.append(fmt_row("p_RPL", "", fmt="{v:.3f}", mapper=lambda side: a_row["prob_true_rpl"] if side == "A" else b_row["prob_true_rpl"]))
    rows.append(fmt_row("CI95 width", "width", fmt="{v:.3f}"))
    rows.append(fmt_row("Stability", "stability", fmt="{v:.3f}"))
    rows.append(fmt_row("Compliance", "compl", fmt="{v:.2f}"))
    rows.append(fmt_row("PQS (0-100)", "pqs", fmt="{v}"))
    rows.append("<tr><th>Compliance ≥ 0.98</th><td>" + gate_cell(a_metrics["gate_compliance_ok"]) + "</td><td>" + gate_cell(b_metrics["gate_compliance_ok"]) + "</td></tr>")
    rows.append("<tr><th>Stability ≥ 0.25</th><td>" + gate_cell(a_metrics["gate_stability_ok"]) + "</td><td>" + gate_cell(b_metrics["gate_stability_ok"]) + "</td></tr>")
    rows.append("<tr><th>CI width ≤ 0.30</th><td>" + gate_cell(a_metrics["gate_precision_ok"]) + "</td><td>" + gate_cell(b_metrics["gate_precision_ok"]) + "</td></tr>")

    if winner == "A":
        banner = f"Winner: <span class=\"winner\">{html.escape(a_row['prompt_version'])}</span>"
    elif winner == "B":
        banner = f"Winner: <span class=\"winner\">{html.escape(b_row['prompt_version'])}</span>"
    else:
        banner = "Result: tie"

    html_doc = f"""
    <!doctype html>
    <meta charset="utf-8" />
    <title>{html.escape(title)}</title>
    <style>{css}</style>
    <h1>{html.escape(title)}</h1>
    <p class="muted">Claim: {html.escape(a_row['claim'])} · Model: {html.escape(a_row['model'])}</p>
    <h2>{banner}</h2>
    <table>
      <thead><tr><th>Metric</th><th>A</th><th>B</th></tr></thead>
      <tbody>
        {''.join(rows)}
      </tbody>
    </table>
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_doc, encoding="utf-8")
    print(f"Wrote {out}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB_DEFAULT), help="SQLite DB path (default runs/heretix.sqlite)")
    ap.add_argument("--claim", required=True, help="Claim text to match")
    ap.add_argument("--version-a", required=True, help="Prompt version A (prefix match, e.g., rpl_g5_v2)")
    ap.add_argument("--version-b", required=True, help="Prompt version B (prefix match)")
    ap.add_argument("--model", default=None, help="Model filter (e.g., gpt-5)")
    ap.add_argument("--since-days", type=int, default=90, help="Time window in days (default 90)")
    ap.add_argument("--out", default=None, help="Output HTML path")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    a_row = fetch_latest_exec(conn, args.claim, args.version_a, args.since_days, args.model)
    b_row = fetch_latest_exec(conn, args.claim, args.version_b, args.since_days, args.model)
    if not a_row or not b_row:
        missing = []
        if not a_row:
            missing.append("A")
        if not b_row:
            missing.append("B")
        raise SystemExit(f"Missing latest execution for: {', '.join(missing)}. Ensure both versions exist for the claim.")

    # Parity check
    knobs = ["model", "K", "R", "T", "B"]
    for k in knobs:
        if a_row[k] != b_row[k]:
            raise SystemExit(f"Parity check failed on {k}: {a_row[k]} vs {b_row[k]}")

    a_metrics = gates_and_pqs(a_row)
    b_metrics = gates_and_pqs(b_row)
    out = Path(args.out) if args.out else Path("runs/reports/ab.html")
    render_html(a_row, b_row, a_metrics, b_metrics, out)


if __name__ == "__main__":
    main()

