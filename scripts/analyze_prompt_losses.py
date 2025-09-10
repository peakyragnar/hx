#!/usr/bin/env python3
"""
Heretix RPL — Analyze Prompt Losses (Which Paraphrases Drive Wider CIs)

Find claims where Version B (e.g., rpl_g5_v3) has a larger CI width than Version A
(e.g., rpl_g5_v2) under parity (model,K,R,T,B). For each losing claim, report the
v3 per-paraphrase stats to flag the likely drivers: deviation from run p_RPL and low
compliance.

Usage:
  uv run python scripts/analyze_prompt_losses.py \
    --version-a rpl_g5_v2 --version-b rpl_g5_v3 --since-days 365 \
    [--model gpt-5] [--claims-file cohort/claims.txt] \
    [--out runs/reports/v3_losses.txt]

Output: human-readable text summary to --out and stdout.
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import json

DB_DEFAULT = Path("runs/heretix.sqlite")


def q(conn: sqlite3.Connection, sql: str, params: Tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
    cur = conn.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [{cols[i]: r[i] for i in range(len(cols))} for r in cur.fetchall()]


def load_claims(path: Optional[str]) -> Optional[List[str]]:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    return [line.strip() for line in p.read_text().splitlines() if line.strip() and not line.strip().startswith('#')]


def by_claim_and_parity(rows: List[Dict[str, Any]]) -> Dict[str, Dict[tuple, Dict[str, Any]]]:
    out: Dict[str, Dict[tuple, Dict[str, Any]]] = {}
    for r in rows:
        c = r.get("claim")
        if not c:
            continue
        key = (r.get("model"), r.get("K"), r.get("R"), r.get("T"), r.get("B"))
        if c not in out:
            out[c] = {}
        prev = out[c].get(key)
        if (prev is None) or (r["created_at"] > prev["created_at"]):
            out[c][key] = r
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB_DEFAULT), help="SQLite DB path")
    ap.add_argument("--version-a", required=True, help="Prompt version A prefix (baseline)")
    ap.add_argument("--version-b", required=True, help="Prompt version B prefix (candidate)")
    ap.add_argument("--model", default=None, help="Model filter (e.g., gpt-5)")
    ap.add_argument("--since-days", type=int, default=365, help="Time window (days)")
    ap.add_argument("--claims-file", default=None, help="Optional file with one claim per line to restrict cohort")
    ap.add_argument("--out", default="runs/reports/prompt_losses.txt", help="Output text path")
    ap.add_argument("--min-delta", type=float, default=0.0, help="Only include losses where width_B - width_A >= this")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    ts_cut = int((datetime.now() - timedelta(days=int(args.since_days))).timestamp())

    where_a = ["created_at >= ?", "prompt_version LIKE ?"]
    params_a: List[Any] = [ts_cut, f"{args.version_a}%"]
    if args.model:
        where_a.append("model=?")
        params_a.append(args.model)
    where_b = ["created_at >= ?", "prompt_version LIKE ?"]
    params_b: List[Any] = [ts_cut, f"{args.version_b}%"]
    if args.model:
        where_b.append("model=?")
        params_b.append(args.model)

    a_rows = q(conn, "SELECT * FROM executions WHERE " + " AND ".join(where_a), tuple(params_a))
    b_rows = q(conn, "SELECT * FROM executions WHERE " + " AND ".join(where_b), tuple(params_b))

    a_by = by_claim_and_parity(a_rows)
    b_by = by_claim_and_parity(b_rows)

    restrict = load_claims(args.claims_file)
    claims = sorted(set(a_by.keys()) & set(b_by.keys()))
    if restrict:
        claims = [c for c in claims if c in set(restrict)]

    lines: List[str] = []
    lines.append(f"Prompt Loss Analysis — {args.version_a} (A) vs {args.version_b} (B)")
    lines.append("")

    n_total = 0
    n_losses = 0
    driver_counts: Dict[int, int] = {}
    driver_preview: Dict[int, str] = {}

    for c in claims:
        common = set(a_by[c].keys()) & set(b_by[c].keys())
        if not common:
            continue
        # pick the pair with freshest min timestamp
        best_key = max(common, key=lambda k: min(a_by[c][k]["created_at"], b_by[c][k]["created_at"]))
        ra = a_by[c][best_key]
        rb = b_by[c][best_key]
        n_total += 1
        dw = float(rb["ci_width"]) - float(ra["ci_width"])  # B - A
        if dw < float(args.min_delta):
            continue
        n_losses += 1

        # per-paraphrase stats for B (candidate)
        run_id_b = rb["run_id"]
        p_b = float(rb["prob_true_rpl"]) if rb["prob_true_rpl"] is not None else float("nan")
        tpl_stats = q(
            conn,
            """
            SELECT paraphrase_idx,
                   COUNT(*) AS attempted,
                   SUM(json_valid) AS valid,
                   AVG(CASE WHEN json_valid=1 THEN prob_true END) AS mean_p
            FROM samples
            WHERE run_id=?
            GROUP BY paraphrase_idx
            ORDER BY paraphrase_idx
            """,
            (run_id_b,),
        )
        # Mark drivers by deviation and compliance
        drivers = []
        for t in tpl_stats:
            idx = int(t["paraphrase_idx"]) if t["paraphrase_idx"] is not None else -1
            attempted = int(t["attempted"] or 0)
            valid = int(t["valid"] or 0)
            compl = (valid / attempted) if attempted else 0.0
            mp = t.get("mean_p")
            if mp is None:
                continue
            mp = float(mp)
            dev = abs(mp - p_b)
            drivers.append({"idx": idx, "attempted": attempted, "valid": valid, "compl": compl, "mean_p": mp, "abs_dev": dev})
        drivers.sort(key=lambda d: (d["abs_dev"], 1.0 - d["compl"]))
        top = list(reversed(drivers))[:3]
        low_comp = sorted(drivers, key=lambda d: d["compl"])[:2]

        # Try paraphrase preview text for B from prompts table
        preview_map: Dict[int, str] = {}
        try:
            prow = q(conn, "SELECT paraphrases_json FROM prompts WHERE prompt_version=?", (rb["prompt_version"],))
            if prow:
                arr = json.loads(prow[0]["paraphrases_json"] or "[]")
                for i, txt in enumerate(arr or []):
                    preview = (str(txt).replace("\n", " ")[:90] + ("…" if len(str(txt)) > 90 else ""))
                    preview_map[i] = preview
        except Exception:
            pass

        lines.append(f"Claim: {c}")
        lines.append(f"  Width A={float(ra['ci_width']):.3f}  B={float(rb['ci_width']):.3f}  Δ(B−A)={dw:+.3f}")
        lines.append(f"  p_RPL B={p_b:.3f}  Stability B={float(rb['stability_score']):.3f}  Compliance B={float(rb['rpl_compliance_rate']):.2f}")
        if top:
            lines.append("  Spread drivers (by |mean_p − p_RPL|, top 3):")
            for d in top:
                lines.append(
                    f"    idx {d['idx']:>2} · mean_p={d['mean_p']:.3f} · dev={d['abs_dev']:.3f} · compl={d['compl']:.2f} · preview='{preview_map.get(d['idx'],'')}'"
                )
                driver_counts[d['idx']] = driver_counts.get(d['idx'], 0) + 1
                if d['idx'] not in driver_preview and preview_map.get(d['idx']):
                    driver_preview[d['idx']] = preview_map.get(d['idx'],'')
        if low_comp:
            lines.append("  Lowest compliance paraphrases:")
            for d in low_comp:
                lines.append(f"    idx {d['idx']:>2} · compl={d['compl']:.2f} (valid={d['valid']}/{d['attempted']}) · preview='{preview_map.get(d['idx'],'')}'")
        lines.append("")

    header = [
        f"Total comparable claims: {n_total}",
        f"Losses where width_B − width_A ≥ {args.min_delta:.3f}: {n_losses}",
        "",
    ]
    # Summary of frequent drivers
    if driver_counts:
        lines_summary = ["Top driver paraphrases in B (frequency across losses):"]
        for idx, cnt in sorted(driver_counts.items(), key=lambda kv: kv[1], reverse=True)[:8]:
            prev = driver_preview.get(idx, "")
            lines_summary.append(f"  idx {idx:>2} · {cnt} hits · '{prev}'")
        lines = [*lines_summary, "", *lines]

    out_text = "\n".join([*header, *lines])
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(out_text, encoding="utf-8")
    print(out_text)


if __name__ == "__main__":
    main()
