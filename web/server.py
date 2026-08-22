"""Bidex Flight Recorder Web Server.

Serves the telemetry HUD & Trace Waterfall UI, plus live OpenTelemetry trace API:
- GET  /api/traces          -> Returns all organized trace trees
- GET  /api/traces/stream   -> Server-Sent Events (SSE) live span feed
- POST /api/traces/demo     -> Emits a full demo trace tree (Run A or Run B)
- POST /api/traces/clear    -> Clears recorded spans
- GET  /api/status         -> Service status, tracer readiness, counters
- GET  /*                  -> Static UI assets
"""

from __future__ import annotations

import json
import os
import queue
import sys
import threading
import time
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from integrations.config import load_settings
from integrations.tracing import (
    clear_spans,
    emit_demo_trace,
    get_raw_spans,
    get_trace_trees,
    subscribe_spans,
    tracer_ready,
    unsubscribe_spans,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"


class TraceAPIHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/traces":
            self._handle_get_traces()
        elif path == "/api/traces/stream":
            self._handle_sse_stream()
        elif path == "/api/status":
            self._handle_get_status()
        elif path == "/api/traces/demo":
            # Allow GET trigger as well for convenience
            query = parse_qs(parsed.query)
            run_type = query.get("run", ["A"])[0]
            self._emit_demo_async(run_type)
            self._send_json({"status": "emitted", "run": run_type})
        else:
            # Fallback to index.html for SPA routes if file doesn't exist
            requested_file = STATIC_DIR / path.lstrip("/")
            if not requested_file.exists() or requested_file.is_dir():
                self.path = "/index.html"
            super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/traces/demo":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
            try:
                payload = json.loads(body) if body else {}
            except Exception:
                payload = {}
            run_type = payload.get("run", "A")
            trace_id = self._emit_demo_async(run_type)
            self._send_json({"status": "ok", "run": run_type, "trace_id": trace_id})
        elif path == "/api/traces/clear":
            clear_spans()
            self._send_json({"status": "cleared"})
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def _send_json(self, data: object, status: int = 200) -> None:
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _handle_get_traces(self) -> None:
        trees = get_trace_trees()
        self._send_json({"traces": trees, "count": len(trees)})

    def _handle_get_status(self) -> None:
        settings = load_settings()
        spans = get_raw_spans()
        trees = get_trace_trees()
        self._send_json({
            "service": settings.otel_service_name,
            "tracer_mode": tracer_ready(),
            "port_ready": settings.port_ready,
            "brightdata_ready": settings.brightdata_ready,
            "total_spans": len(spans),
            "total_traces": len(trees),
        })

    def _emit_demo_async(self, run_type: str) -> str:
        # Run in thread with realistic staggered span emission
        def _run():
            emit_demo_trace(run_type, sleep_step=0.08)
        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return "async_emission_started"

    def _handle_sse_stream(self) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        sub_q = subscribe_spans()
        try:
            # Send initial greeting
            self.wfile.write(b": connected\n\n")
            self.wfile.flush()

            while True:
                try:
                    span_item = sub_q.get(timeout=1.0)
                    msg = f"event: span\ndata: {json.dumps(span_item)}\n\n".encode("utf-8")
                    self.wfile.write(msg)
                    self.wfile.flush()
                except queue.Empty:
                    # Keep-alive heartbeat ping
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            unsubscribe_spans(sub_q)


def run_server(port: int = 8080, host: str = "0.0.0.0") -> None:
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((host, port), TraceAPIHandler)
    print(f"=======================================================")
    print(f" Flight Recorder HUD & Trace Viewer running at:")
    print(f" http://localhost:{port}")
    print(f" Mode: {tracer_ready()}  |  Static: {STATIC_DIR}")
    print(f"=======================================================")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")
        server.server_close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Bidex Flight Recorder Web UI")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host address")
    args = parser.parse_args()
    run_server(port=args.port, host=args.host)
