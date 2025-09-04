#!/usr/bin/env python3
"""
Heretix RPL — Lightweight HTML Report

Generates a simple HTML report for the latest execution (or a specified run_id)
from the SQLite database at runs/heretix.sqlite. Outputs to runs/report.html
by default.

Usage:
  uv run python scripts/report.py                # latest execution
  uv run python scripts/report.py --run-id <id>  # specific run
  uv run python scripts/report.py --out runs/my_report.html
"""
from __future__ import annotations

import argparse
import html
import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional
import hashlib
import yaml

DEFAULT_DB = Path("runs/heretix.sqlite")


def rowdict(cur: sqlite3.Cursor) -> Optional[Dict[str, Any]]:
    row = cur.fetchone()
    if not row:
        return None
    cols = [d[0] for d in cur.description]
    return {cols[i]: row[i] for i in range(len(cols))}


def query_all(cur: sqlite3.Cursor) -> List[Dict[str, Any]]:
    cols = [d[0] for d in cur.description]
    return [{cols[i]: r[i] for i in range(len(cols))} for r in cur.fetchall()]


def gen_report(db_path: Path, out_path: Path, run_id: Optional[str]) -> None:
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = None
    cur = conn.cursor()

    exec_sql = (
        "SELECT execution_id, run_id, datetime(created_at,'unixepoch','localtime') AS ts, "
        "claim, model, prompt_version, K, R, T, B, seed, bootstrap_seed, prob_true_rpl, "
        "ci_lo, ci_hi, ci_width, stability_score, imbalance_ratio, rpl_compliance_rate, cache_hit_rate, "
        "prompt_char_len_max "
        "FROM executions "
    )
    if run_id:
        cur.execute(exec_sql + "WHERE run_id=? ORDER BY created_at DESC LIMIT 1", (run_id,))
    else:
        cur.execute(exec_sql + "ORDER BY created_at DESC LIMIT 1")
    exec_row = rowdict(cur)
    if not exec_row:
        raise SystemExit("No executions found. Run the harness first.")

    run_id = exec_row["run_id"]

    # Fetch corresponding runs row (for counts and config/sampler JSON)
    cur.execute(
        "SELECT artifact_json_path, counts_by_template_json, config_json, sampler_json "
        "FROM runs WHERE run_id=? ORDER BY created_at DESC LIMIT 1",
        (run_id,),
    )
    run_row = rowdict(cur) or {}
    counts_by_tpl = {}
    try:
        if run_row.get("counts_by_template_json"):
            counts_by_tpl = json.loads(run_row["counts_by_template_json"]) or {}
    except Exception:
        counts_by_tpl = {}

    # Load prompt file (system, user_template, paraphrases)
    cfg_obj = {}
    prompt_file_path: Optional[str] = None
    try:
        cfg_obj = json.loads(run_row.get("config_json") or "{}")
        prompt_file_path = cfg_obj.get("prompt_file_path")
    except Exception:
        cfg_obj = {}
    claim_text = exec_row.get("claim") or cfg_obj.get("claim") or ""
    prompt_doc: Dict[str, Any] = {}
    system_text = ""
    user_template = ""
    paraphrases: List[str] = []
    if prompt_file_path and Path(prompt_file_path).exists():
        try:
            prompt_doc = yaml.safe_load(Path(prompt_file_path).read_text())
            system_text = str(prompt_doc.get("system", ""))
            user_template = str(prompt_doc.get("user_template", ""))
            paraphrases = [str(x) for x in prompt_doc.get("paraphrases", [])]
        except Exception:
            pass
    # Recreate the schema instruction string used in the harness
    schema_instructions = (
        "Return ONLY JSON matching this schema: "
        "{ \"prob_true\": 0..1, \"confidence_self\": 0..1, "
        "\"assumptions\": [string], \"reasoning_bullets\": [3-6 strings], "
        "\"contrary_considerations\": [2-4 strings], \"ambiguity_flags\": [string] } "
        "Output the JSON object only."
    )
    full_instructions = (system_text + "\n\n" + schema_instructions).strip()

    # Determine templates chosen for this run (indices)
    sampler = {}
    tpl_indices: List[int] = []
    try:
        sampler = json.loads(run_row.get("sampler_json") or "{}")
        tpl_indices = list(sampler.get("tpl_indices") or [])
    except Exception:
        tpl_indices = []

    # Per-paraphrase stats from samples
    cur.execute(
        "SELECT paraphrase_idx, COUNT(*) AS n, SUM(json_valid) AS valid, AVG(prob_true) AS mean_prob "
        "FROM samples WHERE run_id=? GROUP BY paraphrase_idx ORDER BY paraphrase_idx",
        (run_id,),
    )
    per_tpl = query_all(cur)

    # Build HTML
    title = f"Heretix RPL Report — {html.escape(exec_row['claim'] or '')}"
    css = """
    body { font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif; margin: 24px; color: #222; }
    h1 { font-size: 20px; margin: 0 0 16px; }
    h2 { font-size: 16px; margin: 24px 0 8px; }
    .grid { display: grid; grid-template-columns: 220px 1fr; gap: 6px 12px; max-width: 960px; }
    .muted { color: #666; }
    table { border-collapse: collapse; margin-top: 8px; min-width: 520px; }
    th, td { border: 1px solid #ddd; padding: 6px 8px; text-align: left; font-size: 13px; }
    th { background: #f7f7f7; }
    code { background: #f2f2f2; padding: 1px 4px; border-radius: 3px; }
    .pill { display:inline-block; padding: 2px 6px; border-radius: 10px; font-size: 12px; }
    .ok { background:#e6f4ea; color:#137333; }
    .warn { background:#fef7e0; color:#b06000; }
    .bad { background:#fce8e6; color:#c5221f; }
    """

    def pill(label: str, kind: str) -> str:
        return f"<span class=\"pill {kind}\">{html.escape(label)}</span>"

    p = float(exec_row["prob_true_rpl"] or 0.0)
    width = float(exec_row["ci_width"] or 0.0)
    stability = float(exec_row["stability_score"] or 0.0)
    compl = float(exec_row["rpl_compliance_rate"] or 0.0)
    cache = float(exec_row["cache_hit_rate"] or 0.0)
    band = "ok" if width <= 0.20 else ("warn" if width <= 0.35 else "bad")

    head = f"""
    <div class="grid">
      <div class="muted">Run ID</div><div><code>{html.escape(run_id)}</code></div>
      <div class="muted">Execution</div><div><code>{html.escape(exec_row['execution_id'])}</code> · {html.escape(exec_row['ts'])}</div>
      <div class="muted">Claim</div><div>{html.escape(exec_row['claim'] or '')}</div>
      <div class="muted">Model · Prompt</div><div>{html.escape(exec_row['model'])} · {html.escape(exec_row['prompt_version'])}</div>
      <div class="muted">Sampling</div><div>K={exec_row['K']} · R={exec_row['R']} · T={exec_row['T']} · B={exec_row['B']}</div>
      <div class="muted">Bootstrap Seed</div><div>{html.escape(str(exec_row['bootstrap_seed']))}</div>
      <div class="muted">Prompt Len (max)</div><div>{html.escape(str(exec_row.get('prompt_char_len_max') or ''))}</div>
    </div>
    <h2>Aggregates</h2>
    <div class="grid">
      <div class="muted">p_RPL</div><div>{p:.3f}</div>
      <div class="muted">CI95</div><div>[{float(exec_row['ci_lo']):.3f}, {float(exec_row['ci_hi']):.3f}] · width {pill(f"{width:.3f}", band)}</div>
      <div class="muted">Stability</div><div>{stability:.3f}</div>
      <div class="muted">Compliance · Cache</div><div>{compl:.2f} · {cache:.2f}</div>
    </div>
    """

    # Per-template table
    rows_tpl = []
    for r in per_tpl:
        idx = int(r["paraphrase_idx"]) if r["paraphrase_idx"] is not None else -1
        n = int(r["n"] or 0)
        valid = int(r["valid"] or 0)
        mean_prob = float(r["mean_prob"]) if r["mean_prob"] is not None else float("nan")
        mean_disp = "" if mean_prob != mean_prob else f"{mean_prob:.3f}"
        rows_tpl.append(
            f"<tr><td>{idx}</td><td>{n}</td><td>{valid}</td><td>{mean_disp}</td></tr>"
        )
    empty_tpl_html = '<tr><td colspan="4" class="muted">no samples</td></tr>'
    table_tpl = (
        "<h2>Per-Template Stats (by paraphrase_idx)</h2>"
        "<table><thead><tr><th>paraphrase_idx</th><th>n</th><th>valid</th><th>mean prob_true</th></tr></thead>"
        f"<tbody>{(''.join(rows_tpl)) or empty_tpl_html}</tbody></table>"
    )

    # Counts by template hash (from aggregation diag)
    rows_hash = []
    for h, cnt in (counts_by_tpl or {}).items():
        rows_hash.append(f"<tr><td><code>{html.escape(h)}</code></td><td>{int(cnt)}</td></tr>")
    empty_hash_html = '<tr><td colspan="2" class="muted">no template counts</td></tr>'
    table_hash = (
        "<h2>Counts by Template (prompt_sha256)</h2>"
        "<table><thead><tr><th>prompt_sha256</th><th>count</th></tr></thead>"
        f"<tbody>{(''.join(rows_hash)) or empty_hash_html}</tbody></table>"
    )

    # Build used templates section HTML
    used_templates: List[str] = []
    for i in tpl_indices:
        try:
            raw_para = paraphrases[i] if 0 <= i < len(paraphrases) else ""
        except Exception:
            raw_para = ""
        para_resolved = raw_para.replace("{CLAIM}", claim_text)
        ut_resolved = (user_template or "").replace("{CLAIM}", claim_text)
        user_text_resolved = para_resolved + "\n\n" + ut_resolved
        prompt_full = (full_instructions + "\n\n" + user_text_resolved)
        sha = hashlib.sha256(prompt_full.encode("utf-8")).hexdigest()
        plen = len(prompt_full)
        block = (
            "<details><summary>template #" + str(i) + "</summary>"
            + '<div style="margin:8px 0">'
            + '<div class="muted">prompt_sha256 · length</div>'
            + '<div><code>' + html.escape(sha) + '</code> · ' + str(plen) + '</div>'
            + '<div class="muted" style="margin-top:6px">resolved user text</div>'
            + '<pre>' + html.escape(user_text_resolved) + '</pre>'
            + '</div></details>'
        )
        used_templates.append(block)
    used_templates_section = (
        "<p class=\"muted\">No sampler indices recorded.</p>" if not used_templates else "".join(used_templates)
    )

    html_doc = f"""
    <!doctype html>
    <meta charset="utf-8" />
    <title>{html.escape(title)}</title>
    <style>{css}</style>
    <h1>{html.escape(title)}</h1>
    {head}
    <h2>Prompt</h2>
    <div class="grid">
      <div class="muted">System</div><div><pre>{html.escape(system_text or '')}</pre></div>
      <div class="muted">Schema</div><div><pre>{html.escape(schema_instructions)}</pre></div>
      <div class="muted">User Template</div><div><pre>{html.escape(user_template or '')}</pre></div>
    </div>
    <h2>Used Templates (resolved with claim)</h2>
    <div class="muted">Showing templates selected for this run (tpl_indices from sampler).</div>
    {used_templates_section}
    {table_tpl}
    {table_hash}
    <p class="muted">Artifact JSON: {html.escape(str((run_row or {}).get('artifact_json_path') or ''))}</p>
    """

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_doc, encoding="utf-8")
    print(f"Wrote {out_path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB), help="Path to SQLite DB (default runs/heretix.sqlite)")
    ap.add_argument("--out", default="runs/report.html", help="Output HTML file path")
    ap.add_argument("--run-id", default=None, help="Specific run_id to report (default latest execution)")
    args = ap.parse_args()
    gen_report(Path(args.db), Path(args.out), args.run_id)


if __name__ == "__main__":
    main()
