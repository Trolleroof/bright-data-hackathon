"""Bidex Flight Recorder Web Server.

Serves the telemetry HUD & Trace Waterfall UI, plus live OpenTelemetry trace API:
- GET  /api/traces          -> Returns all organized trace trees
- GET  /api/traces/stream   -> Server-Sent Events (SSE) live span feed
- POST /api/traces/demo     -> Emits a full demo trace tree (Run A or Run B)
- POST /api/traces/clear    -> Clears recorded spans
- GET  /api/status          -> Service status, SigNoz readiness, counters
- GET  /api/live            -> Combined twin + camera state for the live HUD
- POST /api/live/control    -> start/stop/configure the twin and the camera
- GET  /api/sim/stream      -> MJPEG feed of the headless MuJoCo twin
- GET  /api/sim/frame       -> Single JPEG of the twin
- GET  /api/camera/stream   -> MJPEG feed of track_cube with the HUD overlay
- GET  /api/camera/frame    -> Single JPEG of the camera
- GET  /*                   -> Static UI assets
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
from twin.live import TWIN, VIEWS
from vision.live import CAMERA
from integrations.signoz import (
    clear_spans,
    emit_demo_trace,
    get_raw_spans,
    get_trace_trees,
    subscribe_spans,
    tracer_ready,
    unsubscribe_spans,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"

# One MJPEG boundary for both feeds; browsers stream multipart/x-mixed-replace
# straight into an <img>, so the UI needs no player and no WebSocket.
MJPEG_BOUNDARY = "bidexframe"
MJPEG_MAX_FPS = 20.0


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
        elif path == "/api/live":
            self._handle_get_live()
        elif path == "/api/sim/stream":
            self._handle_mjpeg(TWIN.frame_jpeg)
        elif path == "/api/sim/frame":
            self._handle_single_frame(TWIN.frame_jpeg)
        elif path == "/api/camera/stream":
            self._handle_mjpeg(CAMERA.frame_jpeg)
        elif path == "/api/camera/frame":
            self._handle_single_frame(CAMERA.frame_jpeg)
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
        elif path == "/api/live/control":
            self._handle_live_control()
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
            "signoz_endpoint": settings.signoz_endpoint if settings.signoz_ready else None,
            "signoz_ready": settings.signoz_ready,
            "port_ready": settings.port_ready,
            "brightdata_ready": settings.brightdata_ready,
            "total_spans": len(spans),
            "total_traces": len(trees),
        })

    # --- live twin + camera ---------------------------------------------
    def _handle_get_live(self) -> None:
        """One poll for the whole live HUD: twin, camera, and sponsor readiness."""
        settings = load_settings()
        self._send_json({
            "twin": TWIN.state(),
            "camera": CAMERA.state(),
            "views": sorted(VIEWS),
            "apriltag_size_cm": settings.apriltag_size_cm or None,
            "camera_index": settings.camera_index,
            "signoz_ready": settings.signoz_ready,
            "port_ready": settings.port_ready,
            "brightdata_ready": settings.brightdata_ready,
        })

    def _handle_live_control(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        try:
            payload = json.loads(body) if body else {}
        except json.JSONDecodeError:
            payload = {}

        target = str(payload.get("target", "")).lower()
        action = str(payload.get("action", "")).lower()

        if target == "camera":
            if action == "start":
                CAMERA.start()
            elif action == "stop":
                CAMERA.stop()
            elif action == "prompt_state":
                CAMERA.set_prompt_state(str(payload.get("prompt_state", "IDLE")).upper())
            else:
                self._send_json({"error": f"unknown camera action: {action}"}, status=400)
                return
        elif target == "twin":
            # Asking the twin to follow the camera implies starting the camera:
            # otherwise the cube just sits wherever the last source left it.
            if payload.get("source") == "camera" and not CAMERA.running:
                CAMERA.start()
            if action == "start":
                TWIN.start(source=payload.get("source"), view=payload.get("view"))
            elif action == "stop":
                TWIN.stop()
            elif action == "configure":
                TWIN.configure(source=payload.get("source"), view=payload.get("view"))
            elif action == "reset":
                TWIN.reset()
            else:
                self._send_json({"error": f"unknown twin action: {action}"}, status=400)
                return
        else:
            self._send_json({"error": f"unknown target: {target}"}, status=400)
            return

        self._send_json({"status": "ok", "twin": TWIN.state(), "camera": CAMERA.state()})

    def _handle_single_frame(self, source) -> None:
        frame = source()
        if frame is None:
            self._send_json({"error": "no frame yet"}, status=HTTPStatus.SERVICE_UNAVAILABLE)
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(frame)))
        self.end_headers()
        self.wfile.write(frame)

    def _handle_mjpeg(self, source) -> None:
        """multipart/x-mixed-replace: keep pushing the newest JPEG until the tab closes."""
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"multipart/x-mixed-replace; boundary={MJPEG_BOUNDARY}")
        self.send_header("Connection", "close")
        self.end_headers()

        last_frame: bytes | None = None
        min_period = 1.0 / MJPEG_MAX_FPS
        try:
            while True:
                frame = source()
                if frame is None or frame is last_frame:
                    time.sleep(0.02)  # nothing new; do not burn the wire on duplicates
                    continue
                last_frame = frame
                header = (
                    f"--{MJPEG_BOUNDARY}\r\n"
                    f"Content-Type: image/jpeg\r\n"
                    f"Content-Length: {len(frame)}\r\n\r\n"
                ).encode("ascii")
                self.wfile.write(header)
                self.wfile.write(frame)
                self.wfile.write(b"\r\n")
                self.wfile.flush()
                time.sleep(min_period)
        except (BrokenPipeError, ConnectionResetError):
            pass

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
    parser.add_argument("--twin", action="store_true", help="start the headless twin at boot")
    parser.add_argument("--camera", action="store_true", help="start track_cube at boot")
    parser.add_argument(
        "--source",
        choices=["idle", "camera", "skill"],
        default="skill",
        help="what drives the cube in the twin (with --twin)",
    )
    args = parser.parse_args()
    if args.camera:
        state = CAMERA.start()
        print(f" camera: {'running' if state.running else 'unavailable — ' + str(state.error)}")
    if args.twin:
        TWIN.start(source=args.source)
        print(f" twin: headless render started (source={args.source})")
    run_server(port=args.port, host=args.host)
