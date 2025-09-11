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

    def do_GET(self):  # noqa: N802
        if self.path in ("/", "/index.html"):
            body = (ROOT / "index.html").read_bytes()
            self._ok(body, "text/html")
            return
        self._not_found()

    def do_POST(self):  # noqa: N802
        if self.path != "/run":
            self._not_found(); return
        length = int(self.headers.get("Content-Length") or 0)
        data = self.rfile.read(length).decode("utf-8")
        form = {k: v[0] for k, v in urllib.parse.parse_qs(data).items()}

        claim = (form.get("claim") or "").strip()
        if not claim:
            self._bad("Missing claim"); return
        if len(claim) > 600:
            self._bad("Claim too long (max 600 chars)"); return

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
        }
        (TMP_DIR / f"job_{job_id}.json").write_text(json.dumps(job), encoding="utf-8")

        # Return a running page with meta refresh to /wait
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
            <!-- seated figure (stylized) -->
            <g fill='#0f120f' stroke='#00ff41' stroke-opacity='0.35' stroke-width='1.2' filter='url(#glow-green)'>
              <circle cx='180' cy='58' r='18'/>
              <rect x='162' y='75' width='36' height='40' rx='6'/>
              <path d='M150 118 C165 112, 195 112, 210 118 L206 134 C192 132, 168 132, 154 134 Z'/>
              <path d='M150 118 L138 100 L146 96 L158 112 Z'/> <!-- left forearm/hand up -->
              <path d='M210 118 L222 132 L214 136 L202 122 Z'/> <!-- right arm -->
              <path d='M168 134 L168 172 L160 172 L160 134 Z'/> <!-- left leg -->
              <path d='M192 134 L192 172 L200 172 L200 134 Z'/> <!-- right leg -->
            </g>
            <!-- sunglasses -->
            <g fill='#00ff41' opacity='0.9'>
              <rect x='170' y='54' width='10' height='4' rx='1'/>
              <rect x='180' y='54' width='10' height='4' rx='1'/>
              <rect x='179' y='55' width='2' height='2'/>
            </g>
            <!-- levitating red pill above left hand -->
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
                "PROMPT_VERSION": prompt_version,
                "MODEL": model,
            },
        )
        self._ok(body, "text/html")

    def do_GET(self):  # noqa: N802
        if self.path in ("/", "/index.html"):
            body = (ROOT / "index.html").read_bytes()
            self._ok(body, "text/html")
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
