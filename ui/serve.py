#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import time
import urllib.parse
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


ROOT = Path(__file__).parent
TMP_DIR = Path("runs/ui_tmp")

DEFAULTS = {
    "model": "gpt-5",
    "prompt_version": "rpl_g5_v4",
    "K": 16,
    "R": 2,
    "T": 8,
    "B": 5000,
    "max_output_tokens": 1024,
}


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

        # Gather settings
        model = (form.get("model") or DEFAULTS["model"]).strip()
        prompt_version = (form.get("prompt_version") or DEFAULTS["prompt_version"]).strip()
        use_mock = "mock" in form

        def to_int(name: str, default: int, lo: int, hi: int) -> int:
            val = form.get(name)
            if not val:
                return default
            try:
                x = int(val)
                return max(lo, min(hi, x))
            except Exception:
                return default

        K = to_int("K", DEFAULTS["K"], 1, 64)
        R = to_int("R", DEFAULTS["R"], 1, 8)
        T = to_int("T", DEFAULTS["T"], 1, 32)
        B = to_int("B", DEFAULTS["B"], 100, 10000)
        max_out = to_int("max_output_tokens", DEFAULTS["max_output_tokens"], 64, 4096)

        # Prepare temp files
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        ts = int(time.time())
        cfg_path = TMP_DIR / f"cfg_{ts}.json"
        out_path = TMP_DIR / f"out_{ts}.json"

        cfg = {
            "claim": claim,
            "model": model,
            "prompt_version": prompt_version,
            "K": K,
            "R": R,
            "T": T,
            "B": B,
            "max_output_tokens": max_out,
        }
        cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

        env = os.environ.copy()
        env.setdefault("HERETIX_DB_PATH", str(Path("runs/heretix_ui.sqlite")))
        env.setdefault("HERETIX_RPL_SEED", "42")

        cmd = [
            "uv", "run", "heretix", "run",
            "--config", str(cfg_path),
            "--out", str(out_path),
        ]
        if use_mock:
            cmd.append("--mock")

        try:
            start = time.time()
            cp = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=900, check=True)
            dur = time.time() - start
            print(f"[ui] OK in {dur:.1f}s · out={len(cp.stdout)}B err={len(cp.stderr)}B")
        except subprocess.CalledProcessError as e:
            msg = (e.stderr or e.stdout or str(e))[:2000]
            self._err(f"Run failed\n\n{msg}"); return
        except subprocess.TimeoutExpired:
            self._err("Run timed out"); return

        # Parse output JSON
        try:
            doc = json.loads(out_path.read_text(encoding="utf-8"))
            run = (doc.get("runs") or [{}])[0]
            ag = run.get("aggregates") or {}
            p = float(ag.get("prob_true_rpl"))
            ci = ag.get("ci95") or [None, None]
            width = float(ag.get("ci_width")) if ag.get("ci_width") is not None else float("nan")
            stab = float(ag.get("stability_score")) if ag.get("stability_score") is not None else float("nan")
            compl = float(ag.get("rpl_compliance_rate")) if ag.get("rpl_compliance_rate") is not None else float("nan")
        except Exception as e:
            self._err(f"Failed to parse output JSON: {e}"); return

        percent = f"{p*100:.1f}" if p == p else "?"
        verdict = "TRUE" if (p == p and p >= 0.5) else ("FALSE" if p == p else "?")
        if isinstance(ci, list) and len(ci) == 2 and all(isinstance(x,(int,float)) for x in ci):
            ci_str = f"[{ci[0]:.3f}, {ci[1]:.3f}]"
        else:
            ci_str = "[?, ?]"

        body = _render(
            ROOT / "results.html",
            {
                "CLAIM": claim,
                "PERCENT": percent,
                "VERDICT": verdict,
                "CI95": ci_str,
                "WIDTH": f"{width:.3f}" if width == width else "?",
                "STABILITY": f"{stab:.3f}" if stab == stab else "?",
                "COMPLIANCE": f"{compl:.2f}" if compl == compl else "?",
                "PROMPT_VERSION": prompt_version,
                "MODEL": model,
            },
        )
        self._ok(body, "text/html")

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

