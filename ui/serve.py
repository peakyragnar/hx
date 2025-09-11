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


ROOT = Path(__file__).parent
TMP_DIR = Path("runs/ui_tmp")
CFG_PATH_DEFAULT = Path("runs/rpl_example.yaml")
PROMPT_VERSION_DEFAULT = "rpl_g5_v4"


def _render(path: Path, mapping: dict[str, str]) -> bytes:
    html = path.read_text(encoding="utf-8")
    for k, v in mapping.items():
        html = html.replace("{" + k + "}", v)
    return html.encode("utf-8")


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
        if len(claim) > 280:
            self._bad("Claim too long (max 280 characters, like a standard tweet)"); return

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
        if bg:
            running_html = f"""
            <!doctype html>
            <meta charset='utf-8' />
            <meta http-equiv='refresh' content='1;url=/wait?job={job_id}'>
            <title>HERETIX · Running…</title>
            <style>
              body {{ background:#0a0a0a; color:#cfe9cf; font-family:'Courier New', monospace; text-align:center; padding:48px; }}
              .big {{ color:#00ff41; font-size:28px; text-shadow:0 0 18px rgba(0,255,65,0.35); }}
              .muted {{ color:#7aa37a; margin-top:8px; }}
              .hero {{ width:420px; height:420px; margin:20px auto; position:relative; background:url('{bg}') center/cover no-repeat; border-radius:8px; box-shadow:0 0 28px rgba(0,255,65,0.15) inset; }}
              /* Adjustable pill position to align with the image's pill */
              .hero {{ --pill-left: 50%; --pill-top: 48%; }}
              /* Dark soft mask to diminish the background pill so only the animated one is perceived */
              .mask {{ position:absolute; left:var(--pill-left); top:var(--pill-top); width:120px; height:120px; transform: translate(-50%,-50%); pointer-events:none; background: radial-gradient(circle at center, rgba(10,10,10,0.85) 0%, rgba(10,10,10,0.65) 45%, rgba(10,10,10,0.25) 70%, rgba(10,10,10,0.0) 100%); border-radius:50%; filter: blur(1px); }}
              .pill {{ position:absolute; left:var(--pill-left); top:var(--pill-top); width:54px; height:20px; transform: translate(-50%,-50%); background:#ff2b2b; border-radius:999px; box-shadow:0 0 18px rgba(255,0,0,0.45); border:1px solid #ff6b6b; animation: spin 1.6s linear infinite; }}
              @keyframes spin {{ from {{ transform: translate(-50%,-50%) rotate(0deg); }} to {{ transform: translate(-50%,-50%) rotate(360deg); }} }}
            </style>
            <h1 class='big'>Running analysis…</h1>
            <div class='hero'>
              <div class='mask'></div>
              <div class='pill' aria-label='red pill'></div>
            </div>
            <div class='muted'>This may take up to a minute.</div>
            """.encode("utf-8")
        else:
            running_html = f"""
            <!doctype html>
            <meta charset='utf-8' />
            <meta http-equiv='refresh' content='1;url=/wait?job={job_id}'>
            <title>HERETIX · Running…</title>
            <style>
              body {{ background:#0a0a0a; color:#cfe9cf; font-family:'Courier New', monospace; text-align:center; padding:48px; }}
              .big {{ color:#00ff41; font-size:28px; text-shadow:0 0 18px rgba(0,255,65,0.35); }}
              .muted {{ color:#7aa37a; margin-top:8px; }}
              .scene {{ width:360px; margin:28px auto; }}
              .pill {{ transform-origin: 180px 86px; animation: levitate 1.8s ease-in-out infinite; }}
              @keyframes levitate {{ 0% {{ transform: translateY(0) rotate(0deg); }} 50% {{ transform: translateY(-8px) rotate(180deg); }} 100% {{ transform: translateY(0) rotate(360deg); }} }}
            </style>
            <h1 class='big'>Running analysis…</h1>
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
            """.encode("utf-8")
        self._ok(running_html, "text/html")
        return

    def do_WAIT_AND_RENDER(self, job: dict) -> None:
        # Execute CLI and render results
        cfg_path = Path(job["cfg_path"]) ; out_path = Path(job["out_path"]) 
        claim = str(job.get("claim") or "")
        model = str(job.get("model") or "gpt-5")
        prompt_version = str(job.get("prompt_version") or "rpl_g5_v4")
        ui_model_label = str(job.get("ui_model") or "GPT‑5")
        ui_mode_label = str(job.get("ui_mode") or "Internal Knowledge Only (no retrieval)")

        env = os.environ.copy()
        env.setdefault("HERETIX_DB_PATH", str(Path("runs/heretix_ui.sqlite")))
        env.setdefault("HERETIX_RPL_SEED", "42")

        cmd = ["uv","run","heretix","run","--config",str(cfg_path),"--out",str(out_path)]
        try:
            start = time.time()
            cp = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=900, check=True)
            print(f"[ui] OK in {time.time()-start:.1f}s · out={len(cp.stdout)}B err={len(cp.stderr)}B")
        except subprocess.CalledProcessError as e:
            msg = (e.stderr or e.stdout or str(e))[:2000]
            self._err(f"Run failed\n\n{msg}"); return
        except subprocess.TimeoutExpired:
            self._err("Run timed out"); return

        try:
            doc = json.loads(out_path.read_text(encoding="utf-8"))
            run = (doc.get("runs") or [{}])[0]
            ag = run.get("aggregates") or {}
            p = float(ag.get("prob_true_rpl"))
        except Exception as e:
            self._err(f"Failed to parse output JSON: {e}"); return

        percent = f"{p*100:.1f}" if p == p else "?"
        verdict = "TRUE" if (p == p and p >= 0.5) else ("FALSE" if p == p else "?")

        body = _render(
            ROOT / "results.html",
            {
                "CLAIM": claim,
                "PERCENT": percent,
                "VERDICT": verdict,
                "UI_MODEL": ui_model_label,
                "UI_MODE": ui_mode_label,
            },
        )
        self._ok(body, "text/html")

    def do_GET(self):  # noqa: N802
        if self.path in ("/", "/index.html"):
            body = (ROOT / "index.html").read_bytes()
            self._ok(body, "text/html")
            return
        if self.path.startswith("/assets/"):
            # serve static assets under ui/assets
            local = ROOT / (self.path.lstrip("/"))  # ui/assets/...
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
        if self.path.startswith("/wait"):
            # parse ?job=
            parsed = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(parsed.query)
            job_id = (q.get("job") or [""])[0]
            job_file = TMP_DIR / f"job_{job_id}.json"
            if not job_id or not job_file.exists():
                self._bad("Invalid or missing job id"); return
            try:
                job = json.loads(job_file.read_text(encoding="utf-8"))
            except Exception as e:
                self._err(f"Bad job file: {e}"); return
            return self.do_WAIT_AND_RENDER(job)
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

    def _err(self, msg: str) -> None:
        body = f"<pre style='color:#eee;background:#222;padding:16px'>500 Server Error\n\n{msg}</pre>".encode("utf-8")
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
    port = int(os.getenv("UI_PORT", "8000"))
    httpd = HTTPServer((host, port), Handler)
    print(f"Heretix UI running at http://{host}:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
