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
from typing import Optional, List, Dict, Any
import logging
import re
import html

from heretix.verdicts import verdict_label



ROOT = Path(__file__).parent
TMP_DIR = Path("runs/ui_tmp")
CFG_PATH_DEFAULT = Path("runs/rpl_example.yaml")
PROMPT_VERSION_DEFAULT = "rpl_g5_v5"  # keep in sync with examples

# Tunables (avoid magic numbers)
MAX_CLAIM_CHARS = 280
RUN_TIMEOUT_SEC = 900
PORT_DEFAULT = 7799

logging.basicConfig(level=logging.INFO)

MODEL_CHOICES: Dict[str, Dict[str, str]] = {
    "gpt-5": {"label": "GPT‑5", "cli_model": "gpt-5"},
    "grok-4": {"label": "Grok 4", "cli_model": "grok-4"},
    "gemini-2.5": {"label": "Gemini 2.5", "cli_model": "gemini25-default"},
}
DEFAULT_MODEL_CODES = ["gpt-5"]
MODEL_ENV_REQUIREMENTS: Dict[str, tuple[str, ...]] = {
    "gpt-5": ("OPENAI_API_KEY",),
    "grok-4": ("XAI_API_KEY", "GROK_API_KEY"),
    "gemini25-default": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
}


def _format_percent(value: Optional[float]) -> str:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return "--%"
    if num != num:
        return "--%"
    pct = num * 100.0
    text = f"{pct:.1f}".rstrip("0").rstrip(".")
    return f"{text}%"


def _format_number(value: Optional[float], *, digits: int = 3) -> str:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return "--"
    if num != num:
        return "--"
    return f"{num:.{digits}f}".rstrip("0").rstrip(".") or "0"


def _clean_line(text: Optional[str]) -> str:
    if not text:
        return ""
    line = " ".join(str(text).split()).strip()
    if not line:
        return ""
    if line[-1] not in ".!?":
        line += "."
    return line


def _collect_lines(simple_block: dict, run: dict) -> List[str]:
    lines: List[str] = []
    simple_sources = (
        simple_block.get("lines"),
        simple_block.get("bullets"),
    )
    paragraph_source = simple_block.get("body_paragraphs")
    has_simple_content = any(source for source in (*simple_sources, paragraph_source) if source)
    run_sources = (run.get("explanation_reasons"),) if not has_simple_content else tuple()
    ordered_sources = [*simple_sources]
    if paragraph_source:
        ordered_sources.append(paragraph_source)
    ordered_sources.extend(run_sources)
    for source in ordered_sources:
        if not source:
            continue
        for item in source:
            cleaned = _clean_line(item)
            if cleaned and cleaned not in lines:
                lines.append(cleaned)
            if len(lines) >= 3:
                return lines
    if not lines:
        fallback = simple_block.get("summary")
        if not fallback:
            paras = simple_block.get("body_paragraphs")
            if isinstance(paras, (list, tuple)):
                fallback = next((p for p in paras if _clean_line(p)), None)
        if not fallback and not has_simple_content:
            fallback = run.get("explanation_text")
        cleaned = _clean_line(fallback)
        if cleaned:
            lines.append(cleaned)
    if not lines:
        lines.append("No additional context was provided.")
    return lines[:3]


def _extract_summary_text(simple_block: dict, run: dict) -> str:
    summary = simple_block.get("summary")
    if isinstance(summary, str) and summary.strip():
        return summary
    paras = simple_block.get("body_paragraphs")
    if isinstance(paras, (list, tuple)):
        for para in paras:
            if isinstance(para, str) and para.strip():
                return para
    legacy = run.get("explanation_headline") or run.get("explanation_text")
    if isinstance(legacy, str) and legacy.strip():
        return legacy
    return ""


def _missing_env_reason(cli_model: str) -> Optional[str]:
    required = MODEL_ENV_REQUIREMENTS.get(cli_model)
    if not required:
        return None
    if any(os.getenv(var) for var in required):
        return None
    if len(required) == 1:
        return f"{required[0]} is not set"
    return "Missing one of " + ", ".join(required)


def _model_subject_text(entries: List[Dict[str, str]]) -> tuple[str, str]:
    labels = [
        item.get("label") or item.get("code") or item.get("cli_model") or "GPT‑5"
        for item in entries
        if isinstance(item, dict)
    ]
    if not labels:
        return "GPT‑5", "GPT‑5’s"
    if len(labels) == 1:
        base = labels[0]
        return base, f"{base}’s"
    return "the selected models", "the selected models’"



def _render(path: Path, mapping: dict[str, str]) -> bytes:
    html_text = path.read_text(encoding="utf-8")
    for k, v in mapping.items():
        html_text = html_text.replace("{" + k + "}", v)
    return html_text.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # quieter
        print("[ui]", fmt % args)

    def do_POST(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/run":
            self._not_found(); return
        query = urllib.parse.parse_qs(parsed.query)
        response_format = (query.get("format") or ["html"])[0].lower()
        wants_json = response_format == "json"
        length = int(self.headers.get("Content-Length") or 0)
        data = self.rfile.read(length).decode("utf-8")
        form_multi = urllib.parse.parse_qs(data)
        form = {k: v[-1] for k, v in form_multi.items() if v}

        claim = (form.get("claim") or "").strip()
        if not claim:
            self._bad("Missing claim", as_json=wants_json); return
        if len(claim) > MAX_CLAIM_CHARS:
            self._bad(f"Claim too long (max {MAX_CLAIM_CHARS} characters)", as_json=wants_json); return

        # Gather settings (from config file; front-end does not set knobs)
        try:
            cfg_base = yaml.safe_load(CFG_PATH_DEFAULT.read_text(encoding="utf-8")) if CFG_PATH_DEFAULT.exists() else {}
        except Exception as e:
            self._err(f"Failed to read {CFG_PATH_DEFAULT}: {e}", as_json=wants_json); return

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
        raw_models = form_multi.get("ui_model") or []
        if not raw_models and form.get("ui_model"):
            raw_models = [form.get("ui_model")]  # legacy single-select
        model_entries: List[Dict[str, str]] = []
        seen_cli = set()
        skipped_models: List[Dict[str, str]] = []
        for code in raw_models:
            code = (code or "").strip().lower()
            if not code:
                continue
            entry = MODEL_CHOICES.get(code)
            if not entry:
                continue
            cli_model = entry["cli_model"]
            reason_missing = _missing_env_reason(cli_model)
            if reason_missing:
                skipped_models.append({
                    "code": code,
                    "label": entry["label"],
                    "reason": reason_missing,
                })
                logging.warning("UI skipping %s: %s", entry["label"], reason_missing)
                continue
            if cli_model in seen_cli:
                continue
            seen_cli.add(cli_model)
            model_entries.append({
                "code": code,
                "label": entry["label"],
                "cli_model": cli_model,
            })
            if len(model_entries) >= 4:
                break
        if not model_entries:
            for fallback_code in DEFAULT_MODEL_CODES:
                entry = MODEL_CHOICES.get(fallback_code)
                if not entry:
                    continue
                cli_model = entry["cli_model"]
                reason_missing = _missing_env_reason(cli_model)
                if reason_missing:
                    skipped_models.append({
                        "code": fallback_code,
                        "label": entry["label"],
                        "reason": reason_missing,
                    })
                    logging.warning("UI skipping %s: %s", entry["label"], reason_missing)
                    continue
                model_entries.append({
                    "code": fallback_code,
                    "label": entry["label"],
                    "cli_model": cli_model,
                })
                seen_cli.add(cli_model)
                break
        if not model_entries:
            details = "; ".join(f"{item['label']} ({item['reason']})" for item in skipped_models) or "no providers available"
            self._err(
                f"No providers are configured for this environment. {details}",
                as_json=wants_json,
            )
            return
        ui_model_val = model_entries[0]["code"]
        ui_mode_val = (form.get("ui_mode") or "prior").strip()
        model_labels = {
            "gpt-5": "GPT‑5",
            "claude-4.1": "Claude 4.1",
            "grok-4": "Grok 4",
        }
        mode_labels = {
            "prior": "Internal Knowledge Only (no retrieval)",
            "internet-search": "Internet Search",
            "user-data": "User Data",
        }
        ui_model_label = ", ".join(m["label"] for m in model_entries)
        ui_mode_label = mode_labels.get(ui_mode_val, ui_mode_val)

        # Prepare temp files & job record
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        ts = int(time.time() * 1000)
        cfg_path = TMP_DIR / f"cfg_{ts}.json"
        out_path = TMP_DIR / f"out_{ts}.json"

        cfg = dict(cfg_base or {})
        cli_models = [m["cli_model"] for m in model_entries]
        cfg.update({
            "claim": claim,
            "model": cli_models[0],
            "models": cli_models,
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
            "model": cli_models[0],
            "prompt_version": prompt_version,
            "models": model_entries,
            "skipped_models": skipped_models,
            "ui_model": ui_model_label,
            "ui_mode": ui_mode_label,
            "ui_mode_value": ui_mode_val,
        }
        (TMP_DIR / f"job_{job_id}.json").write_text(json.dumps(job), encoding="utf-8")

        if wants_json:
            self._json({
                "job": job_id,
                "wait_url": f"/wait?job={job_id}",
                "poll_url": f"/wait?job={job_id}&format=json",
                "claim": claim,
                "mode": ui_mode_val,
                "mode_label": ui_mode_label,
                "models": model_entries,
                "skipped_models": skipped_models,
            })
            return

        # Return a running page with meta refresh to /wait
        is_web_mode = ui_mode_val == "internet-search"
        subject_text, possessive_text = _model_subject_text(model_entries)
        loading_headline = (
            f"Synthesizing {possessive_text} web-informed view of this claim…"
            if is_web_mode
            else f"Measuring how {possessive_text} training data anchors this claim…"
        )
        step2_text = (
            "Gathering and filtering fresh web snippets."
            if is_web_mode
            else f"Asking {subject_text} with internal knowledge only."
        )
        step3_text = (
            "Preparing the web-informed verdict."
            if is_web_mode
            else "Preparing the explanation for the verdict."
        )
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
              <h1>{loading_headline}</h1>
              <div class='claim'>{escaped_claim}</div>
              <ol class='steps'>
                <li class='active'>Planning the different phrasings.</li>
                <li>{step2_text}</li>
                <li>{step3_text}</li>
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
              <h1>{loading_headline}</h1>
              <div class='claim'>{escaped_claim}</div>
              <ol class='steps'>
                <li class='active'>Planning the different phrasings.</li>
                <li>{step2_text}</li>
                <li>{step3_text}</li>
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

    def do_WAIT_AND_RENDER(
        self,
        job: dict,
        job_file: Optional[Path] = None,
        *,
        response_format: str = "html",
    ) -> None:
        cfg_path = Path(job["cfg_path"])
        out_path = Path(job["out_path"])
        claim = str(job.get("claim") or "")
        prompt_version = str(job.get("prompt_version") or PROMPT_VERSION_DEFAULT)
        ui_mode_label = str(job.get("ui_mode") or "Internal Knowledge Only (no retrieval)")
        ui_mode_value = str(job.get("ui_mode_value") or "prior")
        wants_json = response_format.lower() == "json"

        model_entries = job.get("models")
        if not isinstance(model_entries, list) or not model_entries:
            model_entries = [{
                "label": job.get("ui_model") or "GPT‑5",
                "cli_model": job.get("model", "gpt-5"),
                "code": job.get("model", "gpt-5"),
            }]
        skipped_models = job.get("skipped_models")
        if not isinstance(skipped_models, list):
            skipped_models = []

        try:
            tmp_root = TMP_DIR.resolve(strict=True)
            cfg_real = cfg_path.resolve(strict=False)
            out_real = out_path.resolve(strict=False)
            if not cfg_real.is_relative_to(tmp_root) or not out_real.is_relative_to(tmp_root):
                self._err("Invalid job data. Please start a new check.", as_json=wants_json)
                return
        except Exception as exc:
            logging.error("UI job path validation failed: %s", exc)
            self._err("Invalid job data. Please start a new check.", as_json=wants_json)
            return

        if not cfg_path.exists():
            logging.error("UI job config missing: %s", cfg_path)
            self._err("This run expired. Please try again.", as_json=wants_json)
            return

        env = os.environ.copy()
        env.setdefault("DATABASE_URL", f"sqlite:///{Path('runs/heretix_ui.sqlite').resolve()}")
        env.setdefault("HERETIX_RPL_SEED", "42")

        mode_flag = "web_informed" if ui_mode_value == "internet-search" else "baseline"
        cmd = [
            "uv",
            "run",
            "heretix",
            "run",
            "--config",
            str(cfg_path),
            "--out",
            str(out_path),
            "--mode",
            mode_flag,
        ]
        timeout = min(RUN_TIMEOUT_SEC, 600)
        try:
            start = time.time()
            cp = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=timeout, check=True)
            logging.info("UI run ok in %.1fs", time.time() - start)
            if cp.stderr:
                logging.info("UI stderr: %s", cp.stderr[:500])
        except subprocess.CalledProcessError as e:
            msg = (e.stderr or e.stdout or str(e))[:2000]
            logging.error("UI run failed: %s", msg)
            self._err("The run failed. Please try again.", headline="The run failed", as_json=wants_json)
            return
        except subprocess.TimeoutExpired:
            logging.error("UI run timed out after %ss", timeout)
            self._err("The run exceeded our time limit.", headline="This took too long", as_json=wants_json)
            return

        try:
            if out_path.stat().st_size > 2_000_000:
                self._err("The output was larger than expected.", as_json=wants_json)
                return
            doc = json.loads(out_path.read_text(encoding="utf-8"))
            runs_section = doc.get("runs")
            if not isinstance(runs_section, list) or not runs_section:
                raise ValueError("missing runs section")
        except Exception as e:
            logging.error("UI parse error: %s", e)
            self._err("We couldn’t read the run output.", as_json=wants_json)
            return

        is_web_mode = ui_mode_value == "internet-search"
        card_blocks: List[str] = []
        for idx, run in enumerate(runs_section):
            if not isinstance(run, dict):
                continue
            meta = model_entries[idx] if idx < len(model_entries) else {
                "label": run.get("model", f"Model {idx+1}"),
                "cli_model": run.get("model", ""),
                "code": run.get("model", ""),
            }
            card_blocks.append(self._build_card_html(run, meta, ui_mode_label, is_web_mode))

        if not card_blocks:
            self._err("We couldn’t read the run output.", as_json=wants_json)
            return

        models_phrase = f"{len(card_blocks)} model{'s' if len(card_blocks) != 1 else ''} evaluated"
        skip_note = ""
        if skipped_models:
            detail = ", ".join(f"{item.get('label')} ({item.get('reason')})" for item in skipped_models if item.get("label") and item.get("reason"))
            if detail:
                skip_note = f" · Skipped: {detail}"
        model_note_text = f"{models_phrase} · {ui_mode_label}{skip_note}"
        if wants_json:
            self._json({
                "claim": claim,
                "model_note": model_note_text,
                "mode_label": ui_mode_label,
                "cards_block": "\n".join(card_blocks),
                "cards": card_blocks,
                "runs": runs_section,
                "models": model_entries,
                "skipped_models": skipped_models,
            })
        else:
            body = _render(
                ROOT / "results.html",
                {
                    "CLAIM": html.escape(claim, quote=True),
                    "MODEL_NOTE": html.escape(model_note_text, quote=True),
                    "CARDS_BLOCK": "\n".join(card_blocks),
                },
            )
            self._ok(body, "text/html")

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
            response_format = (q.get("format") or ["html"])[0].lower()
            wants_json = response_format == "json"
            job_file = TMP_DIR / f"job_{job_id}.json"
            # Strictly validate job id and resolved path
            if not job_id or not job_id.isdigit() or not (10 <= len(job_id) <= 20):
                self._bad("Invalid or missing job id", as_json=wants_json); return
            try:
                if not job_file.resolve().is_relative_to(TMP_DIR.resolve()):
                    self._bad("Invalid or missing job id", as_json=wants_json); return
            except Exception:
                self._bad("Invalid or missing job id", as_json=wants_json); return
            if not job_file.exists():
                self._bad("Invalid or missing job id", as_json=wants_json); return
            try:
                job = json.loads(job_file.read_text(encoding="utf-8"))
            except Exception as e:
                self._err(f"Bad job file: {e}", as_json=wants_json); return
            return self.do_WAIT_AND_RENDER(job, job_file, response_format=response_format)
        self._not_found()

    # helpers
    def _ok(self, body: bytes, ctype: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _bad(self, msg: str, *, as_json: bool = False) -> None:
        if as_json:
            self._json({"error": msg}, status=400)
            return
        body = f"<pre style='color:#eee;background:#222;padding:16px'>400 Bad Request\n\n{msg}</pre>".encode("utf-8")
        self.send_response(400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _err(self, msg: str, headline: str = "We hit a snag", *, as_json: bool = False) -> None:
        if as_json:
            self._json({"error": msg, "headline": headline}, status=500)
            return
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

    def _build_card_html(
        self,
        run: Dict[str, Any],
        meta: Dict[str, str],
        ui_mode_label: str,
        is_web_mode: bool,
    ) -> str:
        combined = run.get("combined") if isinstance(run.get("combined"), dict) else {}
        aggregates = run.get("aggregates") if isinstance(run.get("aggregates"), dict) else {}
        simple_block = run.get("simple_expl") if isinstance(run.get("simple_expl"), dict) else {}
        web_block = run.get("web") if isinstance(run.get("web"), dict) else None

        probability = combined.get("p")
        if probability is None:
            probability = aggregates.get("prob_true_rpl")
        percent_text = _format_percent(probability)
        verdict_text = combined.get("label") or verdict_label(probability)

        model_label = meta.get("label") or run.get("model") or "Model"
        pill_text = f"{model_label} · {ui_mode_label}".strip()

        title_text = simple_block.get("title") or verdict_text or ""
        summary_text = _extract_summary_text(simple_block, run) or "This model did not return an explanation."
        summary_bits = []
        if title_text:
            summary_bits.append(f"<strong>{html.escape(title_text)}</strong>")
        if summary_text:
            summary_bits.append(html.escape(summary_text))
        summary_clause = " ".join(summary_bits)

        lines = _collect_lines(simple_block, run)
        summary_clean = _clean_line(summary_text)
        if summary_clean:
            lines = [line for line in lines if line != summary_clean]
        lines_html = "".join(f"<li>{html.escape(line)}</li>" for line in lines)

        resolved_html = ""
        if is_web_mode and web_block and web_block.get("resolved"):
            truth_raw = web_block.get("resolved_truth")
            truth_label = "Resolved"
            classes = ["resolved-note"]
            if truth_raw is False:
                truth_label = "Resolved false"
                classes.append("false")
            elif truth_raw is True:
                truth_label = "Resolved true"
            reason = _clean_line(web_block.get("resolved_reason")) or "Resolver confirmed this verdict from web evidence."
            resolved_html = (
                f"<div class=\"{' '.join(classes)}\">"
                f"{html.escape(truth_label)} · {html.escape(reason)}"
                "</div>"
            )

        summary_for_copy = "\n".join([line for line in [title_text, summary_text, *lines] if line])
        summary_attr = html.escape(summary_for_copy, quote=True)

        card_parts = [
            "<article class=\"result-card\">",
            f"<div class=\"card-pill\">{html.escape(pill_text)}</div>",
            f"<div class=\"card-percent\">{html.escape(percent_text)}</div>",
            f"<div class=\"card-verdict\">{html.escape(verdict_text)}</div>",
            f"<p class=\"card-summary\">{summary_clause}</p>",
        ]
        if lines_html:
            card_parts.append(f"<ul class=\"card-lines\">{lines_html}</ul>")
        if resolved_html:
            card_parts.append(resolved_html)
        card_parts.append(
            f"<button type=\"button\" class=\"btn btn-secondary card-copy\" data-summary=\"{summary_attr}\">Copy summary</button>"
        )
        card_parts.append("</article>")
        return "".join(card_parts)


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
