"""
REST API — deliberately built on the standard library (http.server +
socketserver) rather than FastAPI/Flask, so the whole service runs with
`python3 -m gp_pulse.api` and nothing to pip install. Swap this module
for a FastAPI app later with zero changes to detection/briefs/storage —
this file is a thin HTTP wrapper around pipeline.py and storage.py only.

Endpoints:
    GET  /api/health
    GET  /api/gps                 -> all monitored GPs, worst drift first
    GET  /api/gps/flagged         -> only flagged GPs
    GET  /api/gps/<gp_id>         -> single GP detail
    GET  /api/briefs              -> all generated briefs
    GET  /api/briefs/<gp_id>      -> single brief
    POST /api/recompute           -> re-run the pipeline
                                      body: {"n_gps": 200, "csv_path": null}
    GET  /                        -> serves the dashboard (frontend/dashboard.html)

CORS is wide open (Access-Control-Allow-Origin: *) since this is a
hackathon prototype with no real data — tighten before this ever touches
production traffic.
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from http.server import HTTPServer
from urllib.parse import urlparse

from . import pipeline, storage
from .config import AppConfig, load_config

FRONTEND_FILE = os.path.join(os.path.dirname(__file__), "..", "frontend", "dashboard.html")


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def _json_bytes(obj) -> bytes:
    return json.dumps(obj, default=str).encode("utf-8")


def make_handler(cfg: AppConfig):
    class Handler(BaseHTTPRequestHandler):
        server_version = "GPPulse/0.2"

        def log_message(self, fmt, *args):  # quieter default logging
            sys.stderr.write(f"[gp-pulse-api] {self.address_string()} - {fmt % args}\n")

        def _send_json(self, status: int, payload) -> None:
            body = _json_bytes(payload)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, status: int, html: str) -> None:
            body = html.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self):  # CORS preflight
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"

            try:
                if path == "/":
                    self._serve_dashboard()
                elif path == "/api/health":
                    self._send_json(200, {"status": "ok", "brief_mode": cfg.brief.mode})
                elif path == "/api/gps":
                    self._serve_gps(flagged_only=False)
                elif path == "/api/gps/flagged":
                    self._serve_gps(flagged_only=True)
                elif path.startswith("/api/gps/"):
                    gp_id = path[len("/api/gps/"):]
                    self._serve_gp_detail(gp_id)
                elif path == "/api/briefs":
                    self._serve_briefs()
                elif path.startswith("/api/briefs/"):
                    gp_id = path[len("/api/briefs/"):]
                    self._serve_brief_detail(gp_id)
                else:
                    self._send_json(404, {"error": "not found", "path": path})
            except Exception as exc:  # keep the server alive on any handler bug
                self._send_json(500, {"error": str(exc)})

        def do_POST(self):
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            if path != "/api/recompute":
                self._send_json(404, {"error": "not found", "path": path})
                return
            try:
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length) if length else b"{}"
                body = json.loads(raw or b"{}")
                summary = pipeline.run_pipeline(
                    cfg,
                    csv_path=body.get("csv_path"),
                    n_gps=int(body.get("n_gps", 16)),
                )
                self._send_json(200, summary)
            except Exception as exc:
                self._send_json(500, {"error": str(exc)})

        # -- helpers --------------------------------------------------

        def _serve_dashboard(self):
            try:
                with open(FRONTEND_FILE, "r", encoding="utf-8") as f:
                    self._send_html(200, f.read())
            except FileNotFoundError:
                self._send_html(200, "<h1>GP Pulse API is running</h1><p>Dashboard file not found at frontend/dashboard.html</p>")

        def _serve_gps(self, flagged_only: bool):
            with storage.connect(cfg.db_path) as conn:
                results = storage.get_flagged_gps(conn) if flagged_only else storage.get_all_gps(conn)
            self._send_json(200, [r.to_dict() for r in results])

        def _serve_gp_detail(self, gp_id: str):
            with storage.connect(cfg.db_path) as conn:
                result = storage.get_gp(conn, gp_id)
            if result is None:
                self._send_json(404, {"error": "GP not found", "gp_id": gp_id})
                return
            self._send_json(200, result.to_dict())

        def _serve_briefs(self):
            with storage.connect(cfg.db_path) as conn:
                all_briefs = storage.get_all_briefs(conn)
            self._send_json(200, [b.to_dict() for b in all_briefs])

        def _serve_brief_detail(self, gp_id: str):
            with storage.connect(cfg.db_path) as conn:
                brief = storage.get_brief(conn, gp_id)
            if brief is None:
                self._send_json(404, {"error": "No brief for this GP (not flagged, or briefs not yet generated)", "gp_id": gp_id})
                return
            self._send_json(200, brief.to_dict())

    return Handler


def serve(cfg: AppConfig | None = None) -> None:
    cfg = cfg or load_config()
    handler = make_handler(cfg)
    httpd = ThreadingHTTPServer((cfg.api_host, cfg.api_port), handler)
    print(f"GP Pulse API serving on http://{cfg.api_host}:{cfg.api_port}  (brief mode: {cfg.brief.mode})")
    print(f"Dashboard: http://{cfg.api_host}:{cfg.api_port}/")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()


if __name__ == "__main__":
    serve()
