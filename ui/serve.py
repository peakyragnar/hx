#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import time
import urllib.parse
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import yaml
from typing import Optional, List
import logging
import re
import html

# Provider adapters (reuse existing harness adapters)
from heretix.provider.openai_gpt5 import score_claim as _score_claim_live
from heretix.provider.mock import score_claim_mock as _score_claim_mock
from openai import OpenAI

from heretix_wel.evaluate_wel import evaluate_wel
from heretix_wel.timeliness import heuristic_is_timely
from heretix_wel.weights import (
    fuse_probabilities,
    recency_score,
    strength_score,
    web_weight,
)


ROOT = Path(__file__).parent
TMP_DIR = Path("runs/ui_tmp")
CFG_PATH_DEFAULT = Path("runs/rpl_example.yaml")
PROMPT_VERSION_DEFAULT = "rpl_g5_v5"  # keep in sync with examples

# Tunables (avoid magic numbers)
MAX_CLAIM_CHARS = 280
RUN_TIMEOUT_SEC = 900
PORT_DEFAULT = 7799

logging.basicConfig(level=logging.INFO)



def _render(path: Path, mapping: dict[str, str]) -> bytes:
    html_text = path.read_text(encoding="utf-8")
    for k, v in mapping.items():
        html_text = html_text.replace("{" + k + "}", v)
    return html_text.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # quieter
        print("[ui]", fmt % args)

    def do_POST(self):  # noqa: N802
        if self.path != "/run":
            self._not_found(); return
        length = int(self.headers.get("Content-Length") or 0)
        data = self.rfile.read(length).decode("utf-8")
        form = {k: v[0] for k, v in urllib.parse.parse_qs(data).items()}

        claim = (form.get("claim") or "").strip()
        if not claim:
            self._bad("Missing claim"); return
        if len(claim) > MAX_CLAIM_CHARS:
            self._bad(f"Claim too long (max {MAX_CLAIM_CHARS} characters)"); return

        # Gather settings (from config file; front-end does not set knobs)
        try:
            cfg_base = yaml.safe_load(CFG_PATH_DEFAULT.read_text(encoding="utf-8")) if CFG_PATH_DEFAULT.exists() else {}
        except Exception as e:
            self._err(f"Failed to read {CFG_PATH_DEFAULT}: {e}"); return

        model = str(cfg_base.get("model") or "gpt-5")
        prompt_version = str(cfg_base.get("prompt_version") or PROMPT_VERSION_DEFAULT)

        # Pull defaults from config; fall back sensibly
        def get_int(name: str, default: int) -> int:
            try:
                return int(cfg_base.get(name) if cfg_base.get(name) is not None else default)
            except Exception:
                return default

        K = get_int("K", 16)
        R = get_int("R", 2)
        T = get_int("T", 8)
        B = get_int("B", 5000)
        max_out = get_int("max_output_tokens", 1024)

        # UI selections (front-end only; for display on results page)
        ui_model_val = (form.get("ui_model") or "gpt-5").strip()
        ui_mode_val = (form.get("ui_mode") or "prior").strip()
        model_labels = {
            "gpt-5": "GPT‑5",
            "claude-4.1": "Claude 4.1",
            "grok-4": "Grok 4",
            "deepseek-r1": "DeepSeek R1",
        }
        mode_labels = {
            "prior": "Internal Knowledge Only (no retrieval)",
            "internet-search": "Internet Search",
            "user-data": "User Data",
        }
        ui_model_label = model_labels.get(ui_model_val, ui_model_val)
        ui_mode_label = mode_labels.get(ui_mode_val, ui_mode_val)

        # Prepare temp files & job record
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        ts = int(time.time() * 1000)
        cfg_path = TMP_DIR / f"cfg_{ts}.json"
        out_path = TMP_DIR / f"out_{ts}.json"

        cfg = dict(cfg_base or {})
        cfg.update({
            "claim": claim,
            "model": model,
            "prompt_version": prompt_version,
            "K": K,
            "R": R,
            "T": T,
            "B": B,
            "max_output_tokens": max_out,
        })
        # Ensure paths are within TMP_DIR (defense in depth)
        try:
            if not cfg_path.resolve().is_relative_to(TMP_DIR.resolve()) or not out_path.resolve().is_relative_to(TMP_DIR.resolve()):
                self._err("Invalid file paths"); return
        except Exception:
            self._err("Invalid file paths"); return
        cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

        # Record job for deferred execution
        job_id = f"{ts}"
        job = {
            "cfg_path": str(cfg_path),
            "out_path": str(out_path),
            "claim": claim,
            "model": model,
            "prompt_version": prompt_version,
            "ui_model": ui_model_label,
            "ui_mode": ui_mode_label,
            "ui_mode_value": ui_mode_val,
        }
        (TMP_DIR / f"job_{job_id}.json").write_text(json.dumps(job), encoding="utf-8")

        # Return a running page with meta refresh to /wait
        # Prefer user-provided image at ui/assets/running_bg.(png|jpg|jpeg); otherwise fallback SVG scene
        bg = None
        for name in ("running_bg.png", "running_bg.jpg", "running_bg.jpeg"):
            p = ROOT / "assets" / name
            if p.exists():
                bg = "/assets/" + name
                break
        escaped_claim = html.escape(claim, quote=True)
        if bg:
            running_html = f"""
            <!doctype html>
            <meta charset='utf-8' />
            <meta http-equiv='refresh' content='1;url=/wait?job={job_id}'>
            <title>HERETIX · Running…</title>
            <style>
              body {{ background:#060606; color:#d8f7d8; font-family:'Inter','Helvetica Neue',Arial,sans-serif; padding:56px 18px; }}
              .wrap {{ max-width:640px; margin:0 auto; text-align:center; }}
              h1 {{ font-size:26px; margin-bottom:18px; color:#00ff41; text-shadow:0 0 18px rgba(0,255,65,0.35); }}
              .claim {{ margin-top:12px; padding:18px 22px; border-radius:14px; background:rgba(255,255,255,0.02); border:1px solid rgba(0,255,65,0.25); font-size:18px; line-height:1.5; }}
              .steps {{ margin:26px auto 0; max-width:420px; text-align:left; list-style:none; padding:0; }}
              .steps li {{ display:flex; gap:14px; align-items:flex-start; padding:14px 16px; margin-bottom:12px; border-radius:12px; background:rgba(0,0,0,0.35); border:1px solid rgba(0,255,65,0.18); color:#8ea88e; position:relative; overflow:hidden; }}
              .steps li::before {{ content:''; position:absolute; left:0; top:0; bottom:0; width:4px; background:rgba(0,255,65,0.45); opacity:0; animation: pulse 3s infinite; }}
              .steps li.active::before {{ opacity:1; }}
              @keyframes pulse {{ 0% {{ transform:scaleY(0); }} 50% {{ transform:scaleY(1); }} 100% {{ transform:scaleY(0); }} }}
              .hero {{ width:340px; height:340px; margin:28px auto; position:relative; background:url('{bg}') center/cover no-repeat; border-radius:12px; box-shadow:0 0 32px rgba(0,255,65,0.25) inset; }}
              .hero::after {{ content:''; position:absolute; right:0; bottom:0; width:56px; height:56px; background: linear-gradient(135deg, rgba(6,6,6,0) 0%, rgba(6,6,6,0.1) 45%, rgba(6,6,6,0.75) 60%, rgba(6,6,6,1) 100%); border-bottom-right-radius:12px; pointer-events:none; }}
              .hero {{ --pill-left: 50%; --pill-top: 48%; }}
              .mask {{ position:absolute; left:var(--pill-left); top:var(--pill-top); width:120px; height:120px; transform: translate(-50%,-50%); pointer-events:none; background: radial-gradient(circle at center, rgba(6,6,6,0.85) 0%, rgba(6,6,6,0.65) 45%, rgba(6,6,6,0.25) 70%, rgba(6,6,6,0.0) 100%); border-radius:50%; filter: blur(1px); }}
              .pill {{ position:absolute; left:var(--pill-left); top:var(--pill-top); width:54px; height:20px; transform: translate(-50%,-50%); background:#ff2b2b; border-radius:999px; box-shadow:0 0 18px rgba(255,0,0,0.45); border:1px solid #ff6b6b; animation: spin 1.6s linear infinite; }}
              @keyframes spin {{ from {{ transform: translate(-50%,-50%) rotate(0deg); }} to {{ transform: translate(-50%,-50%) rotate(360deg); }} }}
              .muted {{ color:#8ea88e; margin-top:12px; }}
            </style>
            <div class='wrap'>
              <h1>Measuring how GPT‑5’s training data anchors this claim…</h1>
              <div class='claim'>{escaped_claim}</div>
              <ol class='steps'>
                <li class='active'>Planning the different phrasings.</li>
                <li>Asking GPT-5 with internal knowledge only.</li>
                <li>Preparing the explanation for the verdict.</li>
              </ol>
              <div class='hero'>
                <div class='mask'></div>
                <div class='pill' aria-label='red pill'></div>
              </div>
              <div class='muted'>This usually takes less than a minute.</div>
            </div>
            </div>
            """.encode("utf-8")
        else:
            running_html = f"""
            <!doctype html>
            <meta charset='utf-8' />
            <meta http-equiv='refresh' content='1;url=/wait?job={job_id}'>
            <title>HERETIX · Running…</title>
            <style>
              body {{ background:#060606; color:#d8f7d8; font-family:'Inter','Helvetica Neue',Arial,sans-serif; padding:56px 18px; }}
              .wrap {{ max-width:640px; margin:0 auto; text-align:center; }}
              h1 {{ font-size:26px; margin-bottom:18px; color:#00ff41; text-shadow:0 0 18px rgba(0,255,65,0.35); }}
              .claim {{ margin-top:12px; padding:18px 22px; border-radius:14px; background:rgba(255,255,255,0.02); border:1px solid rgba(0,255,65,0.25); font-size:18px; line-height:1.5; }}
              .steps {{ margin:26px auto 0; max-width:420px; text-align:left; list-style:none; padding:0; }}
              .steps li {{ display:flex; gap:14px; align-items:flex-start; padding:14px 16px; margin-bottom:12px; border-radius:12px; background:rgba(0,0,0,0.35); border:1px solid rgba(0,255,65,0.18); color:#8ea88e; position:relative; overflow:hidden; }}
              .steps li::before {{ content:''; position:absolute; left:0; top:0; bottom:0; width:4px; background:rgba(0,255,65,0.45); opacity:0; animation: pulse 3s infinite; }}
              .steps li.active::before {{ opacity:1; }}
              @keyframes pulse {{ 0% {{ transform:scaleY(0); }} 50% {{ transform:scaleY(1); }} 100% {{ transform:scaleY(0); }} }}
              .scene {{ width:360px; margin:32px auto; }}
              .pill {{ transform-origin: 180px 86px; animation: levitate 1.8s ease-in-out infinite; }}
              .muted {{ color:#8ea88e; margin-top:12px; }}
            </style>
            <div class='wrap'>
              <h1>Measuring how GPT‑5’s training data anchors this claim…</h1>
              <div class='claim'>{escaped_claim}</div>
              <ol class='steps'>
                <li class='active'>Planning the different phrasings.</li>
                <li>Asking GPT‑5 with internal knowledge only.</li>
                <li>Summarizing why it leans that way.</li>
              </ol>
              <div class='scene'>
              <svg width='360' height='220' viewBox='0 0 360 220' xmlns='http://www.w3.org/2000/svg' role='img' aria-label='matrix silhouette with levitating red pill'>
                <defs>
                  <linearGradient id='g' x1='0' y1='0' x2='0' y2='1'>
                    <stop offset='0%' stop-color='#0a0a0a'/>
                    <stop offset='100%' stop-color='#0e1a0e'/>
                  </linearGradient>
                  <filter id='glow-green' x='-50%' y='-50%' width='200%' height='200%'>
                    <feGaussianBlur stdDeviation='2' result='b'/>
                    <feColorMatrix in='b' type='matrix' values='0 0 0 0 0  0 1 0 0 0  0 0 0 0 0  0 0 0 0.8 0'/>
                  </filter>
                  <filter id='glow-red' x='-50%' y='-50%' width='200%' height='200%'>
                    <feGaussianBlur stdDeviation='1.6' result='r'/>
                    <feColorMatrix in='r' type='matrix' values='1 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0.9 0'/>
                  </filter>
                </defs>
                <rect x='0' y='0' width='360' height='220' fill='url(#g)'/>
                <g fill='#0f120f' stroke='#00ff41' stroke-opacity='0.35' stroke-width='1.2' filter='url(#glow-green)'>
                  <circle cx='180' cy='58' r='18'/>
                  <rect x='162' y='75' width='36' height='40' rx='6'/>
                  <path d='M150 118 C165 112, 195 112, 210 118 L206 134 C192 132, 168 132, 154 134 Z'/>
                  <path d='M150 118 L138 100 L146 96 L158 112 Z'/>
                  <path d='M210 118 L222 132 L214 136 L202 122 Z'/>
                  <path d='M168 134 L168 172 L160 172 L160 134 Z'/>
                  <path d='M192 134 L192 172 L200 172 L200 134 Z'/>
                </g>
                <g fill='#00ff41' opacity='0.9'>
                  <rect x='170' y='54' width='10' height='4' rx='1'/>
                  <rect x='180' y='54' width='10' height='4' rx='1'/>
                  <rect x='179' y='55' width='2' height='2'/>
                </g>
                <g class='pill'>
                  <ellipse cx='146' cy='86' rx='18' ry='7' fill='#ff2b2b' filter='url(#glow-red)' stroke='#ff6b6b' stroke-width='0.8'/>
                  <rect x='134' y='83.4' width='24' height='5' rx='2.5' fill='rgba(255,255,255,0.12)'/>
                </g>
              </svg>
            </div>
            <div class='muted'>This may take up to a minute.</div>
            </div>
            """.encode("utf-8")
        self._ok(running_html, "text/html")
        return

    def do_WAIT_AND_RENDER(self, job: dict, job_file: Optional[Path] = None) -> None:
        # Execute CLI and render results
        cfg_path = Path(job["cfg_path"]) ; out_path = Path(job["out_path"]) 
        claim = str(job.get("claim") or "")
        model = str(job.get("model") or "gpt-5")
        prompt_version = str(job.get("prompt_version") or "rpl_g5_v4")
        ui_model_label = str(job.get("ui_model") or "GPT‑5")
        ui_mode_label = str(job.get("ui_mode") or "Internal Knowledge Only (no retrieval)")
        ui_mode_value = str(job.get("ui_mode_value") or "prior")

        # Re-validate that the job still points to files under runs/ui_tmp before invoking CLI.
        try:
            tmp_root = TMP_DIR.resolve(strict=True)
            cfg_real = cfg_path.resolve(strict=False)
            out_real = out_path.resolve(strict=False)
            if not cfg_real.is_relative_to(tmp_root) or not out_real.is_relative_to(tmp_root):
                logging.error("UI job has unsafe file paths: cfg=%s out=%s", cfg_path, out_path)
                self._err("Invalid job data. Please start a new check."); return
        except Exception as exc:
            logging.error("UI job path validation failed: %s", exc)
            self._err("Invalid job data. Please start a new check."); return

        if not cfg_path.exists():
            logging.error("UI job config missing: %s", cfg_path)
            self._err("This run expired. Please try again."); return

        env = os.environ.copy()
        env.setdefault("HERETIX_DB_PATH", str(Path("runs/heretix_ui.sqlite")))
        env.setdefault("HERETIX_RPL_SEED", "42")

        cmd = ["uv","run","heretix","run","--config",str(cfg_path),"--out",str(out_path)]
        timeout = min(RUN_TIMEOUT_SEC, 600)
        try:
            start = time.time()
            cp = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=timeout, check=True)
            logging.info("UI run ok in %.1fs", time.time()-start)
            if cp.stderr:
                logging.info("UI stderr: %s", cp.stderr[:500])
        except subprocess.CalledProcessError as e:
            msg = (e.stderr or e.stdout or str(e))[:2000]
            logging.error("UI run failed: %s", msg)
            self._err("The run failed. Please try again.", headline="The run failed"); return
        except subprocess.TimeoutExpired:
            logging.error("UI run timed out after %ss", timeout)
            self._err("The run exceeded our time limit.", headline="This took too long"); return

        try:
            # Sanity limit to prevent huge/malformed file issues
            if out_path.stat().st_size > 2_000_000:
                self._err("The output was larger than expected."); return
            doc = json.loads(out_path.read_text(encoding="utf-8"))
            runs_section = doc.get("runs")
            if not isinstance(runs_section, list) or not runs_section:
                raise ValueError("missing runs section")
            run = runs_section[0] or {}
            aggregates = run.get("aggregates")
            if not isinstance(aggregates, dict):
                raise ValueError("missing aggregates")
            p = float(aggregates.get("prob_true_rpl"))
            width = float(aggregates.get("ci_width") or 0.0)
            stability = float(aggregates.get("stability_score") or 0.0)
            compliance = float(aggregates.get("rpl_compliance_rate") or 0.0)
        except Exception as e:
            logging.error("UI parse error: %s", e)
            self._err("We couldn’t read the run output."); return

        prior_p = p
        prior_ci = aggregates.get("ci95") or [None, None]

        def _safe_float(val: object) -> float:
            try:
                return float(val)
            except (TypeError, ValueError):
                return float("nan")

        prior_ci_lo = _safe_float(prior_ci[0] if isinstance(prior_ci, (list, tuple)) else None)
        prior_ci_hi = _safe_float(prior_ci[1] if isinstance(prior_ci, (list, tuple)) else None)
        if prior_ci_lo != prior_ci_lo or prior_ci_hi != prior_ci_hi:
            prior_ci_lo = max(0.0, prior_p - 0.05)
            prior_ci_hi = min(1.0, prior_p + 0.05)
        prior_width = prior_ci_hi - prior_ci_lo
        if prior_width != prior_width:
            prior_width = width

        combined_p = prior_p
        combined_ci = (prior_ci_lo, prior_ci_hi)
        combined_width = prior_width
        web_summary: dict[str, object] | None = None
        web_error: str | None = None

        if ui_mode_value == "internet-search":
            try:
                wel_provider = os.getenv("WEL_PROVIDER", "tavily")
                wel_model = os.getenv("WEL_MODEL", model)
                wel_docs = int(os.getenv("WEL_DOCS", "16"))
                wel_replicates = int(os.getenv("WEL_REPLICATES", "2"))
                wel_per_domain = int(os.getenv("WEL_PER_DOMAIN_CAP", "3"))
                recency_env = os.getenv("WEL_RECENCY_DAYS")
                wel_recency = int(recency_env) if recency_env and recency_env.lower() != "none" else None

                wel_result = evaluate_wel(
                    claim=claim,
                    provider=wel_provider,
                    model=wel_model,
                    k_docs=wel_docs,
                    replicates=wel_replicates,
                    per_domain_cap=wel_per_domain,
                    recency_days=wel_recency,
                )
                web_p = float(wel_result["p"])
                web_ci_tuple = wel_result["ci95"]
                web_ci = (float(web_ci_tuple[0]), float(web_ci_tuple[1]))
                metrics_dict = wel_result["metrics"]
                n_docs = int(metrics_dict.get("n_docs", 0))
                n_domains = int(metrics_dict.get("n_domains", 0))
                median_age = float(metrics_dict.get("median_age_days", 365.0))
                dispersion = float(metrics_dict.get("dispersion", 0.0))
                json_valid_rate = float(metrics_dict.get("json_valid_rate", 1.0))
                recency = recency_score(
                    claim_is_timely=heuristic_is_timely(claim),
                    median_age_days=median_age,
                )
                strength = strength_score(
                    n_docs=n_docs,
                    n_domains=n_domains,
                    dispersion=dispersion,
                    json_valid_rate=json_valid_rate,
                )
                weight = web_weight(recency, strength)
                combined_p, combined_ci = fuse_probabilities(
                    prior_p,
                    (prior_ci_lo, prior_ci_hi),
                    web_p,
                    web_ci,
                    weight,
                )
                combined_width = combined_ci[1] - combined_ci[0]
                ui_mode_label = "Internet Search (Web-Informed)"
                web_summary = {
                    "p": web_p,
                    "ci": web_ci,
                    "metrics": {
                        "n_docs": n_docs,
                        "n_domains": n_domains,
                        "median_age_days": median_age,
                        "dispersion": dispersion,
                        "json_valid_rate": json_valid_rate,
                    },
                    "weight": weight,
                    "recency": recency,
                    "strength": strength,
                    "replicates": wel_result["replicates"],
                }
            except Exception as exc:
                web_error = str(exc)
                logging.error("UI web-informed error: %s", exc)

        p = combined_p
        width = combined_width if combined_width == combined_width else width
        percent = f"{p*100:.1f}%" if p == p else "?"
        prior_percent = f"{prior_p*100:.1f}%"
        web_percent = f"{web_summary['p']*100:.1f}%" if web_summary else None

        if p == p:
            if p >= 0.60:
                verdict = "LIKELY TRUE"
            elif p <= 0.40:
                verdict = "LIKELY FALSE"
            else:
                verdict = "UNCERTAIN"
        else:
            verdict = "UNAVAILABLE"

        if p == p:
            if web_summary:
                if p >= 0.60:
                    interpretation = (
                        f"Combining GPT‑5’s prior ({prior_percent}) with the web snippets "
                        f"({web_percent}) makes this likely true ({percent})."
                    )
                elif p <= 0.40:
                    interpretation = (
                        f"The web snippets ({web_percent}) reinforce GPT‑5’s prior ({prior_percent}), "
                        f"leaving only {percent} chance the claim is true."
                    )
                else:
                    interpretation = (
                        f"GPT‑5’s prior ({prior_percent}) and the web snippets ({web_percent}) disagree; "
                        f"together they settle near {percent}."
                    )
            else:
                pct = percent
                if p >= 0.60:
                    interpretation = f"{ui_model_label} leans true and gives this claim about {pct} chance of being correct."
                elif p <= 0.40:
                    interpretation = f"{ui_model_label} leans false and estimates just {pct} probability that the claim is true."
                else:
                    interpretation = f"{ui_model_label} is unsure—it assigns roughly {pct} chance the claim is true."
        else:
            if web_error and ui_mode_value == "internet-search":
                interpretation = "Web-Informed mode failed; showing the baseline prior instead."
            else:
                interpretation = "We couldn’t calculate the model’s prior for this claim."

        adv_width = f"{width:.3f}" if width == width else "—"
        adv_stability = f"{stability:.2f}" if stability == stability else "—"
        adv_compliance = f"{compliance*100:.0f}%" if compliance == compliance else "—"

        info_title = "How to read this"
        info_note_a = "This is GPT‑5’s belief using the Raw Prior Lens—no web search, no outside evidence."
        info_note_b = "Use it to understand where the model already leans before you add new facts or arguments."
        adv_note = "Narrower confidence widths mean the model gave consistent answers. Stability reflects paraphrase agreement; compliance shows adherence to Raw Prior rules."
        adv_extra_html = ""

        summary_lines = [
            f'Claim: "{claim}"',
            f'Verdict: {verdict} ({percent})',
        ]

        if web_summary:
            metrics = web_summary["metrics"]
            weight = float(web_summary["weight"])
            n_docs = int(metrics.get("n_docs", 0))
            n_domains = int(metrics.get("n_domains", 0))
            median_age = float(metrics.get("median_age_days", 0.0))

            entries = [
                ("Prior width", f"{prior_width:.3f}" if prior_width == prior_width else "—"),
                ("Web docs", f"{n_docs} docs / {n_domains} domains"),
                ("Web recency", f"{median_age:.1f} days"),
                ("Web weight", f"{weight:.2f}"),
            ]
            adv_extra_html = "".join(
                f'<div><div class="metric-label">{html.escape(title, quote=True)}</div>'
                f'<div class="metric-value">{html.escape(value, quote=True)}</div></div>'
                for title, value in entries
            )

            info_title = "How to read this blend"
            info_note_a = "Combined probability blends GPT‑5’s Raw Prior with fresh web snippets."
            info_note_b = f"Prior (no web) was {prior_percent}. Web snippets alone gave {web_percent}. Weight={weight:.2f} determines how much the web shifts the prior."
            adv_note = "Confidence width reflects the combined estimate; template stability and compliance still come from the Raw Prior Lens."

            summary_lines.append(f"Prior (no web): {prior_percent}")
            summary_lines.append(f"Web evidence: {web_percent} (docs={n_docs}, domains={n_domains})")
            summary_lines.append(f"Combined (weight {weight:.2f}): {percent}")
        elif web_error and ui_mode_value == "internet-search":
            safe_err = web_error.splitlines()[0][:120] if web_error else "unknown error"
            info_note_a = "Web search was requested but failed, so only the Raw Prior result is shown."
            info_note_b = f"Error: {safe_err}"
            adv_note = "Confidence, stability, and compliance all reflect the Raw Prior run because web search was unavailable."
            summary_lines.append("Web search failed; showing baseline prior only.")

        summary_lines.append(f'Model: {ui_model_label} · {ui_mode_label}')

        # Generate a brief model explanation via one provider call (same prompt version)
        def _load_prompt(prompts_file: Optional[str], version: str) -> tuple[str, str, List[str]]:
            try:
                if prompts_file:
                    path = Path(prompts_file)
                else:
                    path = Path(__file__).resolve().parents[1] / "heretix" / "prompts" / f"{version}.yaml"
                docp = yaml.safe_load(path.read_text(encoding="utf-8"))
                system_text = str(docp.get("system") or "")
                user_template = str(docp.get("user_template") or "")
                paraphrases = [str(x) for x in (docp.get("paraphrases") or [])]
                return system_text, user_template, paraphrases
            except Exception:
                return "", "Claim: \"{CLAIM}\"\n\nReturn the JSON only.", ["Without retrieval, estimate P(true) for: {CLAIM}"]

        def _explain_live_with_json(claim_text: str, verdict_label: str, tok_cap: int) -> list[str]:
            try:
                client = OpenAI()
                instructions = (
                    "Explain the truth assessment of a short claim for a general audience.\n"
                    "Rules:\n"
                    "- Do not mention models, prompts, probabilities, or process.\n"
                    "- No links or citations.\n"
                    "- Write 2–4 short sentences (≤25 words each) focusing on: definitions of key terms, typical context/scope, and notable exceptions.\n"
                    "Output strict JSON: {\n  \"reasons\": [string, ...]\n}"
                )
                user_text = (
                    f"Claim: \"{claim_text}\"\n"
                    f"Verdict: {verdict_label}\n"
                    "Return only the JSON."
                )
                resp = client.responses.create(
                    model=model,
                    instructions=instructions,
                    input=[{"role": "user", "content": [{"type": "input_text", "text": user_text}]}],
                    max_output_tokens=min(max(tok_cap, 120), 512),
                    reasoning={"effort": "minimal"},
                )
                text = getattr(resp, "output_text", None)
                if not text:
                    # Fallback: walk structured output
                    text = None
                    for o in getattr(resp, "output", []) or []:
                        if getattr(o, "type", None) == "message":
                            for part in getattr(o, "content", []) or []:
                                if getattr(part, "type", None) == "output_text":
                                    text = getattr(part, "text", None)
                                    break
                        if text:
                            break
                if not text:
                    return []
                try:
                    obj = json.loads(text)
                    reasons = obj.get("reasons") or []
                    if not isinstance(reasons, list):
                        reasons = []
                except Exception:
                    # Heuristic extraction: bullets or sentences
                    reasons = []
                    # bullet-style
                    for line in text.splitlines():
                        ls = line.strip().lstrip("-*•0123456789. ").strip()
                        if len(ls.split()) >= 3:
                            reasons.append(ls)
                    if not reasons:
                        # sentence split
                        parts = re.split(r"(?<=[\.!?])\s+", text)
                        for s in parts:
                            ss = s.strip()
                            if 8 <= len(ss.split()) <= 28:
                                reasons.append(ss)
                # Sanitize and cap
                out: list[str] = []
                for s in reasons:
                    if isinstance(s, str):
                        ss = s.strip()
                        if ss:
                            out.append(ss if ss.endswith(".") else ss + ".")
                    if len(out) >= 4:
                        break
                print(f"[ui] live-explainer ok · reasons={len(out)}")
                return out[:4]
            except Exception as e:
                print(f"[ui] live-explainer error: {e}")
                return []

        def _generate_explanation() -> list[str]:
            # Prefer config prompts_file if set
            try:
                cfg_obj = json.loads(cfg_path.read_text(encoding="utf-8"))
            except Exception:
                cfg_obj = {}
            prompts_file = cfg_obj.get("prompts_file")
            max_out = int(cfg_obj.get("max_output_tokens") or 512)

            sys_text, user_tmpl, phrs = _load_prompt(prompts_file, prompt_version)
            paraphrase = phrs[0] if phrs else "Without retrieval, estimate P(true) for: {CLAIM}"

            use_mock = bool(os.getenv("HERETIX_MOCK")) or (os.getenv("OPENAI_API_KEY") is None)
            try:
                # First attempt: dedicated live explainer (JSON reasons), only in live mode
                reasons: list[str] = []
                if not use_mock:
                    verdict_label = (
                        "likely true" if p >= 0.60 else ("likely false" if p <= 0.40 else "uncertain")
                    )
                    reasons = _explain_live_with_json(claim, verdict_label, max_out)
                if reasons:
                    print("[ui] explanation mode: live-explainer")
                    return reasons
                if use_mock:
                    reasons = []  # avoid mock placeholder text
                else:
                    out = _score_claim_live(
                        claim=claim,
                        system_text=sys_text,
                        user_template=user_tmpl,
                        paraphrase_text=paraphrase,
                        model=model,
                        max_output_tokens=max_out,
                    )
                    raw = out.get("raw") or {}
                    bullets = raw.get("reasoning_bullets") or []
                    if not isinstance(bullets, list) or not bullets:
                        bullets = raw.get("contrary_considerations") or []
                    # Choose 2–3 short reasons, remove processing/meta terms
                    ban = ("mock", "retrieval", "citation", "link", "json", "schema", "format", "paraphrase", "prior")
                    reasons = []
                    for x in bullets:
                        if not isinstance(x, str):
                            continue
                        r = x.strip().rstrip(".;")
                        r_low = r.lower()
                        if any(b in r_low for b in ban):
                            continue
                        reasons.append(r)
                        if len(reasons) >= 3:
                            break
            except Exception as e:
                print(f"[ui] explanation bullets path error: {e}")
                reasons = []

            # If no reasons from live call, try assumptions/ambiguity_flags
            if not reasons and not use_mock and raw:
                alt: list[str] = []
                for x in (raw.get("assumptions") or []):
                    if isinstance(x, str) and x.strip():
                        alt.append(x.strip().rstrip(".;"))
                        if len(alt) >= 3:
                            break
                for x in (raw.get("ambiguity_flags") or []):
                    if len(alt) >= 3:
                        break
                    if isinstance(x, str) and x.strip():
                        alt.append(x.strip().rstrip(".;"))
                reasons = alt[:3]
                if reasons:
                    print("[ui] explanation mode: run-fields")

            # Final fallback: simple, claim-facing lines
            if not reasons:
                if p >= 0.60:
                    reasons = ["The claim aligns with common definitions and typical examples."]
                elif p <= 0.40:
                    reasons = ["The claim conflicts with common definitions and typical examples."]
                else:
                    reasons = ["It depends on definitions or missing context."]
                print("[ui] explanation final-fallback used")
            return reasons

        reasons: List[str] = []
        if web_summary:
            seen: set[str] = set()

            def _add_items(items: List[str]) -> bool:
                for item in items or []:
                    if not isinstance(item, str):
                        continue
                    text = item.strip()
                    if not text:
                        continue
                    if text[-1] not in ".!?":
                        text = text + "."
                    if text not in seen:
                        seen.add(text)
                        reasons.append(text)
                    if len(reasons) >= 4:
                        return True
                return False

            for rep in web_summary["replicates"]:
                if _add_items(getattr(rep, "support_bullets", [])):
                    break
            if len(reasons) < 2:
                for rep in web_summary["replicates"]:
                    if _add_items(getattr(rep, "oppose_bullets", [])):
                        break
            if len(reasons) < 2:
                for rep in web_summary["replicates"]:
                    if _add_items(getattr(rep, "notes", [])):
                        break

        if not reasons:
            reasons = _generate_explanation()
        # Build display pieces
        if p >= 0.60:
            why_head = "Why it’s likely true"
            why_kind = "true"
        elif p <= 0.40:
            why_head = "Why it’s likely false"
            why_kind = "false"
        else:
            why_head = "Why it’s uncertain"
            why_kind = "uncertain"

        if reasons:
            summary_lines.append('Reasons:')
            summary_lines.extend(f'- {r}' for r in reasons)
        else:
            summary_lines.append('Reasons: (none)')
        summary_attr = html.escape("\n".join(summary_lines), quote=True)

        # Escape for HTML but preserve Unicode characters (avoid JSON string escapes like \u201c)
        why_items_html = "\n".join(f"<li>{html.escape(r, quote=True)}</li>" for r in reasons)
        body = _render(
            ROOT / "results.html",
            {
                "CLAIM": html.escape(claim, quote=True),
                "PERCENT": percent,
                "VERDICT": html.escape(verdict, quote=True),
                "INTERPRETATION": html.escape(interpretation, quote=True),
                "UI_MODEL": html.escape(ui_model_label, quote=True),
                "UI_MODE": html.escape(ui_mode_label, quote=True),
                "WHY_HEAD": why_head,
                "WHY_ITEMS": why_items_html,
                "WHY_KIND": why_kind,
                "INFO_TITLE": html.escape(info_title, quote=True),
                "INFO_NOTE_A": html.escape(info_note_a, quote=True),
                "INFO_NOTE_B": html.escape(info_note_b, quote=True),
                "ADV_NOTE": html.escape(adv_note, quote=True),
                "ADV_EXTRA": adv_extra_html,
                "ADV_WIDTH": adv_width,
                "ADV_STABILITY": adv_stability,
                "ADV_COMPLIANCE": adv_compliance,
                "SUMMARY_ATTR": summary_attr,
            },
        )
        self._ok(body, "text/html")

        # Best-effort cleanup of temp files
        try:
            cfg_path.unlink(missing_ok=True)
            out_path.unlink(missing_ok=True)
            if job_file:
                Path(job_file).unlink(missing_ok=True)
        except Exception:
            pass

    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path_only = parsed.path or "/"
        if path_only in ("/", "/index.html"):
            html_path = ROOT / "index.html"
            try:
                text = html_path.read_text(encoding="utf-8")
                marker = "</head>"
                inject = "<script>window.HERETIX_UI_LOCAL = true;</script>"
                if marker in text:
                    text = text.replace(marker, inject + marker, 1)
                else:
                    text = inject + text
                body = text.encode("utf-8")
            except Exception:
                body = html_path.read_bytes()
            self._ok(body, "text/html")
            return
        if path_only in ("/how", "/how.html"):
            how_path = ROOT / "how.html"
            if how_path.exists():
                self._ok(how_path.read_bytes(), "text/html")
                return
        if path_only in ("/examples", "/examples.html"):
            ex_path = ROOT / "examples.html"
            if ex_path.exists():
                self._ok(ex_path.read_bytes(), "text/html")
                return
            self._not_found(); return
        if path_only.startswith("/assets/"):
            # serve static assets under ui/assets with strict path validation
            asset_root = (ROOT / "assets").resolve()
            rel = path_only[len("/assets/"):]
            # normalize and prevent traversal
            local = (asset_root / Path(rel)).resolve()
            try:
                if not local.is_relative_to(asset_root):
                    self._not_found(); return
            except Exception:
                self._not_found(); return
            if not local.exists() or not local.is_file():
                self._not_found(); return
            ext = local.suffix.lower()
            ctype = "application/octet-stream"
            if ext in (".png", ".apng"): ctype = "image/png"
            elif ext in (".jpg", ".jpeg"): ctype = "image/jpeg"
            elif ext == ".svg": ctype = "image/svg+xml"
            elif ext == ".gif": ctype = "image/gif"
            self._ok(local.read_bytes(), ctype)
            return
        if path_only.startswith("/wait"):
            # parse ?job=
            q = urllib.parse.parse_qs(parsed.query)
            job_id = (q.get("job") or [""])[0]
            job_file = TMP_DIR / f"job_{job_id}.json"
            # Strictly validate job id and resolved path
            if not job_id or not job_id.isdigit() or not (10 <= len(job_id) <= 20):
                self._bad("Invalid or missing job id"); return
            try:
                if not job_file.resolve().is_relative_to(TMP_DIR.resolve()):
                    self._bad("Invalid or missing job id"); return
            except Exception:
                self._bad("Invalid or missing job id"); return
            if not job_file.exists():
                self._bad("Invalid or missing job id"); return
            try:
                job = json.loads(job_file.read_text(encoding="utf-8"))
            except Exception as e:
                self._err(f"Bad job file: {e}"); return
            return self.do_WAIT_AND_RENDER(job, job_file)
        self._not_found()

    # helpers
    def _ok(self, body: bytes, ctype: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _bad(self, msg: str) -> None:
        body = f"<pre style='color:#eee;background:#222;padding:16px'>400 Bad Request\n\n{msg}</pre>".encode("utf-8")
        self.send_response(400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _err(self, msg: str, headline: str = "We hit a snag") -> None:
        try:
            template = (ROOT / "error.html").read_text(encoding="utf-8")
            body = template.replace("{HEADLINE}", html.escape(headline, quote=True)) \
                           .replace("{MESSAGE}", "We couldn’t finish this check. Please try again in a moment.") \
                           .replace("{DETAILS}", "If the problem persists, please retry later.") \
                           .encode("utf-8")
        except Exception:
            fallback = "<pre style='color:#eee;background:#222;padding:16px'>500 Server Error</pre>"
            body = fallback.encode("utf-8")
        self.send_response(500)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _not_found(self) -> None:
        self.send_response(404)
        self.end_headers()


def main() -> None:
    host = os.getenv("UI_HOST", "127.0.0.1")
    port = int(os.getenv("UI_PORT", str(PORT_DEFAULT)))
    httpd = HTTPServer((host, port), Handler)
    has_key = bool(os.getenv("OPENAI_API_KEY"))
    is_mock = bool(os.getenv("HERETIX_MOCK"))
    print(f"Heretix UI running at http://{host}:{port} · OPENAI_API_KEY={'yes' if has_key else 'no'} · MOCK={'on' if is_mock else 'off'}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
