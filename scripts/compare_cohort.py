#!/usr/bin/env python3
"""
Heretix RPL — Cohort Compare (Broad View)

Compares two prompt versions across a cohort of claims by querying the DB for
the latest execution per (claim, version) within a time window, enforcing parity
on core knobs. Produces an HTML report with aggregate metrics and per-claim deltas.

Usage:
  uv run python scripts/compare_cohort.py --version-a rpl_g5_v2 --version-b rpl_g5_candidate \
      [--model gpt-5] [--since-days 30] [--claims-file runs/claims.txt] [--out runs/reports/cohort.html]

Notes:
  - If --claims-file is omitted, uses all claims that have both versions within the window.
  - Parity enforced on model, K, R, T, B; claims failing parity are excluded and listed.
"""
from __future__ import annotations

import argparse
import html
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import statistics as stats

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


def pqs(width: float, stability: float, compl: float) -> int:
    return int((0.4 * stability + 0.4 * (1 - min(width, 0.5) / 0.5) + 0.2 * compl) * 100)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB_DEFAULT), help="SQLite DB path")
    ap.add_argument("--version-a", required=True, help="Prompt version A prefix")
    ap.add_argument("--version-b", required=True, help="Prompt version B prefix")
    ap.add_argument("--model", default=None, help="Model filter (e.g., gpt-5)")
    ap.add_argument("--since-days", type=int, default=30, help="Time window (days)")
    ap.add_argument("--claims-file", default=None, help="Optional file with one claim per line to restrict cohort")
    ap.add_argument("--out", default="runs/reports/cohort.html", help="Output HTML path")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    ts_cut = int((datetime.now() - timedelta(days=int(args.since_days))).timestamp())

    base_where = ["created_at >= ?", "prompt_version LIKE ?"]
    base_params: List[Any] = [ts_cut, f"{args.version_a}%"]
    if args.model:
        base_where.append("model=?")
        base_params.append(args.model)

    a_rows = q(conn, "SELECT * FROM executions WHERE " + " AND ".join(base_where), tuple(base_params))

    where_b = ["created_at >= ?", "prompt_version LIKE ?"]
    base_params_b: List[Any] = [ts_cut, f"{args.version_b}%"]
    if args.model:
        where_b.append("model=?")
        base_params_b.append(args.model)
    b_rows = q(conn, "SELECT * FROM executions WHERE " + " AND ".join(where_b), tuple(base_params_b))

    # Group rows by claim and parity key (model,K,R,T,B) and keep latest per key
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

    a_by = by_claim_and_parity(a_rows)
    b_by = by_claim_and_parity(b_rows)

    # Cohort selection
    restrict_claims = load_claims(args.claims_file)
    claims_all = set(a_by.keys()) & set(b_by.keys())
    if restrict_claims:
        claims_all &= set(restrict_claims)
    claims = sorted(list(claims_all))

    rows: List[Dict[str, Any]] = []
    excluded: List[Tuple[str, str]] = []
    for c in claims:
        keys_a = set(a_by[c].keys())
        keys_b = set(b_by[c].keys())
        common = keys_a & keys_b
        if not common:
            # Build helpful reason from latest heads
            la = max(a_by[c].values(), key=lambda r: r["created_at"]) if a_by[c] else None
            lb = max(b_by[c].values(), key=lambda r: r["created_at"]) if b_by[c] else None
            def fmt(r: Optional[Dict[str, Any]]) -> str:
                return "none" if not r else f"{r.get('model')},K={r.get('K')},R={r.get('R')},T={r.get('T')},B={r.get('B')}"
            excluded.append((c, f"no parity match; latest A=({fmt(la)}), latest B=({fmt(lb)})"))
            continue
        # Choose the parity key with the freshest pair (maximize min timestamps)
        def pair_score(k: tuple) -> int:
            return min(a_by[c][k]["created_at"], b_by[c][k]["created_at"])  # prefer pairs that are recent on both sides
        best_key = max(common, key=pair_score)
        ra = a_by[c][best_key]
        rb = b_by[c][best_key]
        wa = float(ra["ci_width"]); wb = float(rb["ci_width"]) 
        sa = float(ra["stability_score"]); sb = float(rb["stability_score"]) 
        ca = float(ra["rpl_compliance_rate"]); cb = float(rb["rpl_compliance_rate"]) 
        rows.append({
            "claim": c,
            "version_a": ra["prompt_version"],
            "version_b": rb["prompt_version"],
            "width_a": wa,
            "width_b": wb,
            "stab_a": sa,
            "stab_b": sb,
            "comp_a": ca,
            "comp_b": cb,
            "pqs_a": pqs(wa, sa, ca),
            "pqs_b": pqs(wb, sb, cb),
        })

    # Aggregates
    def med(vals: List[float]) -> float:
        return float('nan') if not vals else float(stats.median(vals))

    agg = {
        "n": len(rows),
        "width_med_a": med([r["width_a"] for r in rows]),
        "width_med_b": med([r["width_b"] for r in rows]),
        "stab_med_a": med([r["stab_a"] for r in rows]),
        "stab_med_b": med([r["stab_b"] for r in rows]),
        "comp_mean_a": (sum(r["comp_a"] for r in rows) / len(rows)) if rows else float('nan'),
        "comp_mean_b": (sum(r["comp_b"] for r in rows) / len(rows)) if rows else float('nan'),
        "pqs_med_a": med([r["pqs_a"] for r in rows]),
        "pqs_med_b": med([r["pqs_b"] for r in rows]),
    }

    # Winner on cohort:
    # 1) Narrower median CI width, with tie threshold: if |Δwidth| < 0.003 treat as tie on width
    # 2) Higher median PQS
    # 3) Higher median Stability
    THRESH = 0.003
    wa = agg["width_med_a"]; wb = agg["width_med_b"]
    sa = agg["stab_med_a"]; sb = agg["stab_med_b"]
    pa = agg["pqs_med_a"]; pb = agg["pqs_med_b"]

    def is_finite(x: float) -> bool:
        return isinstance(x, (int, float)) and (x == x)

    if is_finite(wa) and is_finite(wb):
        d = float(wb) - float(wa)
        if abs(d) >= THRESH:
            cohort_winner = "A" if wa < wb else "B"
        else:
            # Width tie → use PQS, then Stability
            if is_finite(pa) and is_finite(pb) and pa != pb:
                cohort_winner = "A" if pa > pb else "B"
            elif is_finite(sa) and is_finite(sb) and sa != sb:
                cohort_winner = "A" if sa > sb else "B"
            else:
                cohort_winner = "tie"
    else:
        # Fallback if widths are NaN: compare PQS then Stability
        if is_finite(pa) and is_finite(pb) and pa != pb:
            cohort_winner = "A" if pa > pb else "B"
        elif is_finite(sa) and is_finite(sb) and sa != sb:
            cohort_winner = "A" if sa > sb else "B"
        else:
            cohort_winner = "tie"

    # HTML
    css = """
    body { font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif; margin: 24px; color: #222; }
    h1 { font-size: 20px; margin: 0 0 16px; }
    h2 { font-size: 16px; margin: 24px 0 8px; }
    table { border-collapse: collapse; margin-top: 12px; min-width: 760px; }
    th, td { border: 1px solid #ddd; padding: 6px 8px; text-align: left; font-size: 13px; }
    th { background: #f7f7f7; }
    code { background: #f2f2f2; padding: 1px 4px; border-radius: 3px; }
    .winner { background:#e8f0fe; padding: 6px 8px; border-radius: 6px; display:inline-block; }
    .muted { color: #666; }
    """
    title = f"Cohort Compare — {args.version_a} vs {args.version_b}"
    win_text = ("A" if cohort_winner == "A" else ("B" if cohort_winner == "B" else "tie"))
    hdr = f"<h2>Winner: <span class=\"winner\">{html.escape(win_text)}</span> · N={agg['n']}</h2>"

    rows_html = []
    rows_html.append(
        f"<tr><th>Median CI width</th><td>{agg['width_med_a']:.3f}</td><td>{agg['width_med_b']:.3f}</td><td>{(agg['width_med_b']-agg['width_med_a']):+.3f}</td></tr>"
    )
    rows_html.append(
        f"<tr><th>Median Stability</th><td>{agg['stab_med_a']:.3f}</td><td>{agg['stab_med_b']:.3f}</td><td>{(agg['stab_med_b']-agg['stab_med_a']):+.3f}</td></tr>"
    )
    rows_html.append(
        f"<tr><th>Mean Compliance</th><td>{agg['comp_mean_a']:.2f}</td><td>{agg['comp_mean_b']:.2f}</td><td>{(agg['comp_mean_b']-agg['comp_mean_a']):+.2f}</td></tr>"
    )
    rows_html.append(
        f"<tr><th>Median PQS</th><td>{agg['pqs_med_a']:.0f}</td><td>{agg['pqs_med_b']:.0f}</td><td>{(agg['pqs_med_b']-agg['pqs_med_a']):+.0f}</td></tr>"
    )

    table_head = "<thead><tr><th>Claim</th><th>ver A</th><th>ver B</th><th>Δ CI width</th><th>Δ Stability</th><th>Δ PQS</th></tr></thead>"
    table_rows = []
    for r in rows:
        d_width = r["width_b"] - r["width_a"]
        d_stab = r["stab_b"] - r["stab_a"]
        d_pqs = r["pqs_b"] - r["pqs_a"]
        table_rows.append(
            f"<tr><td>{html.escape(r['claim'])}</td><td>{html.escape(str(r['version_a']))}</td><td>{html.escape(str(r['version_b']))}</td><td>{d_width:+.3f}</td><td>{d_stab:+.3f}</td><td>{d_pqs:+.0f}</td></tr>"
        )

    excl_html = ""
    if excluded:
        excl_lines = [f"<li>{html.escape(c)} — {html.escape(reason)}" for (c, reason) in excluded]
        excl_html = "<h2>Excluded (parity)</h2><ul>" + "".join(excl_lines) + "</ul>"

    # Build per-claim tbody safely (avoid backslashes in f-expr)
    no_overlap_html = '<tr><td colspan="6" class="muted">No overlapping claims</td></tr>'
    tbody_claims = ("".join(table_rows)) if table_rows else no_overlap_html

    html_doc = f"""
    <!doctype html>
    <meta charset="utf-8" />
    <title>{html.escape(title)}</title>
    <style>{css}</style>
    <h1>{html.escape(title)}</h1>
    <p class="muted">Model: {html.escape(args.model or 'any')} · Window: last {int(args.since_days)} days</p>
    {hdr}
    <table><thead><tr><th>Metric</th><th>A</th><th>B</th><th>Δ (B−A)</th></tr></thead><tbody>
    {''.join(rows_html)}
    </tbody></table>
    <h2>Per-Claim Deltas</h2>
    <table>{table_head}<tbody>{tbody_claims}</tbody></table>
    {excl_html}
    """
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_doc, encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
