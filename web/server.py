"""Bidex Flight Recorder Web Server.

Serves the telemetry HUD & Trace Waterfall UI, plus live OpenTelemetry trace API:
- GET  /api/traces          -> Returns all organized trace trees
- GET  /api/traces/stream   -> Server-Sent Events (SSE) live span feed
- POST /api/traces/demo     -> Emits a full demo trace tree (Run A or Run B)
- POST /api/traces/clear    -> Clears recorded spans
- GET  /api/status          -> Service status, tracer readiness, counters
- GET  /api/live            -> Combined twin + camera state for the live HUD
- WS   /api/live/ws         -> Combined twin + camera state stream
- POST /api/live/control    -> start/stop/configure the twin and the camera
- GET  /api/import          -> Pending object-import prompt / progress / result
- POST /api/import/request  -> Ask for an object by name: {"label": "gray water bottle"}
- POST /api/import/decision -> {"decision": "scan"|"stop"|"import"|"dismiss"|"reset"}
                               Scanning is off until asked for.
- GET  /api/sim/stream      -> MJPEG feed of the headless MuJoCo twin
- GET  /api/sim/frame       -> Single JPEG of the twin
- GET  /api/camera/stream   -> MJPEG feed of track_cube with the HUD overlay
- GET  /api/camera/frame    -> Single JPEG of the camera
- GET  /api/checks          -> Available checks (which are runnable headless)
- POST /api/checks/run      -> Start a check or the whole suite, returns job_id
- GET  /api/checks/job      -> Poll a job for new output lines and results
- POST /api/checks/cancel   -> Terminate a running job
- GET  /*                   -> Static UI assets
"""

from __future__ import annotations

import errno
import base64
import hashlib
import json
import os
import queue
import sys
import socket
import struct
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
from integrations.object_import import IMPORTER
from twin.live import TWIN, VIEWS
from vision.live import CAMERA
from integrations.tracing import (
    clear_spans,
    emit_demo_trace,
    get_raw_spans,
    get_trace_trees,
    subscribe_spans,
    tracer_ready,
    unsubscribe_spans,
)

_WEB_DIR = str(Path(__file__).resolve().parent)
if _WEB_DIR not in sys.path:
    sys.path.insert(0, _WEB_DIR)

from checks import SUITE, cancel_job, list_checks, public_job, start_job

STATIC_DIR = Path(__file__).resolve().parent / "static"

# One MJPEG boundary for both feeds; browsers stream multipart/x-mixed-replace
# straight into an <img>, so the UI needs no player.
MJPEG_BOUNDARY = "bidexframe"
MJPEG_MAX_FPS = 20.0
# How long a new stream request waits for the producer's first JPEG before
# giving up with a 503, and how long an open stream tolerates silence.
MJPEG_FIRST_FRAME_S = 4.0
MJPEG_IDLE_TIMEOUT_S = 10.0


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
        elif path == "/api/live/ws":
            self._handle_live_websocket()
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
        elif path == "/api/import":
            self._send_json(IMPORTER.state())
        elif path == "/api/checks":
            self._send_json({"checks": list_checks(), "suite": SUITE})
        elif path == "/api/checks/job":
            self._handle_get_job(parse_qs(parsed.query))
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
        elif path == "/api/import/request":
            payload = self._read_json_body()
            label = str(payload.get("label", ""))
            result = IMPORTER.request(label)
            self._send_json(result, status=400 if result.get("error") else 200)
        elif path == "/api/import/decision":
            payload = self._read_json_body()
            decision = str(payload.get("decision", "")).lower()
            if decision == "reset":
                self._send_json(IMPORTER.reset())
            elif decision in {"scan", "start"}:
                self._send_json(IMPORTER.set_scanning(True))
            elif decision in {"stop", "cancel"}:
                self._send_json(IMPORTER.set_scanning(False))
            elif decision in {"import", "accept", "yes", "dismiss", "decline", "no"}:
                self._send_json(IMPORTER.decide(decision))
            else:
                self._send_json({"error": f"unknown decision: {decision}"}, status=400)
        elif path == "/api/checks/run":
            self._handle_run_checks(self._read_json_body())
        elif path == "/api/checks/cancel":
            payload = self._read_json_body()
            job_id = payload.get("job_id", "")
            self._send_json({"cancelled": cancel_job(job_id), "job_id": job_id})
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def _read_json_body(self) -> dict:
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length <= 0:
            return {}
        raw = self.rfile.read(content_length).decode("utf-8")
        try:
            parsed = json.loads(raw) if raw else {}
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _handle_run_checks(self, payload: dict) -> None:
        checks = payload.get("checks")
        if not checks:
            single = payload.get("check")
            checks = [single] if single else list(SUITE)
        if isinstance(checks, str):
            checks = [checks]
        try:
            job = start_job(list(checks))
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        self._send_json(job)

    def _handle_get_job(self, query: dict) -> None:
        job_id = (query.get("id") or query.get("job_id") or [""])[0]
        try:
            since = int((query.get("since") or ["-1"])[0])
        except ValueError:
            since = -1
        job = public_job(job_id, since=since)
        if job is None:
            self._send_json({"error": "unknown job"}, status=HTTPStatus.NOT_FOUND)
            return
        self._send_json(job)

    def _send_json(self, data: object, status: int = 200) -> None:
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_jpeg(self, image: bytes | None) -> None:
        if image is None:
            self.send_error(HTTPStatus.SERVICE_UNAVAILABLE, "live view is not ready")
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(image)))
        self.end_headers()
        try:
            self.wfile.write(image)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _stream_mjpeg(self, frame, fps: int) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            while True:
                image = frame()
                if image is not None:
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n")
                    self.wfile.write(f"Content-Length: {len(image)}\r\n\r\n".encode())
                    self.wfile.write(image)
                    self.wfile.write(b"\r\n")
                    self.wfile.flush()
                time.sleep(1 / fps)
        except (BrokenPipeError, ConnectionResetError):
            pass

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
            "nim_ready": settings.nim_ready,
            "total_spans": len(spans),
            "total_traces": len(trees),
        })

    # --- live twin + camera ---------------------------------------------
    def _handle_get_live(self) -> None:
        """One poll for the whole live HUD: twin, camera, and sponsor readiness."""
        self._send_json(self._live_payload())

    @staticmethod
    def _live_payload() -> dict:
        settings = load_settings()
        return {
            "twin": TWIN.state(),
            "camera": CAMERA.state(),
            "object_import": IMPORTER.state(),
            "views": sorted(VIEWS),
            "apriltag_size_cm": settings.apriltag_size_cm or None,
            "camera_index": settings.camera_index,
            "tracer_mode": tracer_ready(),
            "port_ready": settings.port_ready,
            "brightdata_ready": settings.brightdata_ready,
            "nim_ready": settings.nim_ready,
        }

    @staticmethod
    def _websocket_frame(payload: bytes, opcode: int = 1) -> bytes:
        """Build one unfragmented server-to-client WebSocket frame."""
        length = len(payload)
        if length < 126:
            header = bytes((0x80 | opcode, length))
        elif length <= 0xFFFF:
            header = bytes((0x80 | opcode, 126)) + struct.pack("!H", length)
        else:
            header = bytes((0x80 | opcode, 127)) + struct.pack("!Q", length)
        return header + payload

    @staticmethod
    def _read_websocket_frame(connection: socket.socket) -> tuple[int, bytes] | None:
        """Read one client frame; browser frames are always masked."""
        header = connection.recv(2)
        if not header:
            return None
        if len(header) != 2:
            raise ConnectionError("partial websocket header")
        first, second = header
        length = second & 0x7F
        if length == 126:
            length = struct.unpack("!H", connection.recv(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", connection.recv(8))[0]
        masked = bool(second & 0x80)
        mask = connection.recv(4) if masked else b""
        payload = connection.recv(length) if length else b""
        if len(payload) != length:
            raise ConnectionError("partial websocket payload")
        if masked:
            payload = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
        return first & 0x0F, payload

    def _handle_live_websocket(self) -> None:
        """Stream live HUD state without a polling request per half-second."""
        if self.headers.get("Upgrade", "").lower() != "websocket":
            self._send_json({"error": "websocket upgrade required"}, status=HTTPStatus.UPGRADE_REQUIRED)
            return
        key = self.headers.get("Sec-WebSocket-Key")
        if not key:
            self._send_json({"error": "missing Sec-WebSocket-Key"}, status=HTTPStatus.BAD_REQUEST)
            return
        accept = base64.b64encode(
            hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()
        ).decode()
        self.connection.sendall(
            (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
            ).encode("ascii")
        )
        self.close_connection = True
        self.connection.settimeout(0.1)
        try:
            while True:
                payload = json.dumps({**self._live_payload(), "backend_online": True}).encode("utf-8")
                self.connection.sendall(self._websocket_frame(payload))
                deadline = time.monotonic() + 0.4
                while time.monotonic() < deadline:
                    try:
                        frame = self._read_websocket_frame(self.connection)
                    except socket.timeout:
                        continue
                    if frame is None:
                        return
                    opcode, data = frame
                    if opcode == 8:
                        self.connection.sendall(self._websocket_frame(data[:125], opcode=8))
                        return
                    if opcode == 9:
                        self.connection.sendall(self._websocket_frame(data[:125], opcode=10))
                        continue
                    break
        except (BrokenPipeError, ConnectionResetError, socket.timeout):
            pass

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
                state = CAMERA.start()
                # Answer with a state the UI can trust: either pixels are
                # flowing, or we say why. Returning "running" before the first
                # grab makes the feed panel look hung.
                if state.running and not CAMERA.wait_for_frame(3.0):
                    self._send_json({
                        "status": "ok",
                        "twin": TWIN.state(),
                        "camera": {**CAMERA.state(), "error": "camera opened but delivered no frame — is another app using it?"},
                    })
                    return
            elif action == "stop":
                CAMERA.stop()
            elif action == "record":
                skill = str(payload.get("skill", "A")).upper()
                if skill not in {"A", "B"}:
                    self._send_json({"error": "skill must be A or B"}, status=400)
                    return
                if not CAMERA.running:
                    CAMERA.start()
                CAMERA.wait_for_frame(3.0)
                try:
                    prompt_state, bag_path, recorded_skill = CAMERA.toggle_recording(skill)
                except RuntimeError as exc:
                    self._send_json({"error": str(exc)}, status=409)
                    return
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

    @staticmethod
    def _await_frame(source, timeout: float) -> bytes | None:
        """Poll a frame source until it yields, or the timeout expires."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            frame = source()
            if frame is not None:
                return frame
            time.sleep(0.05)
        return source()

    def _handle_mjpeg(self, source) -> None:
        """multipart/x-mixed-replace: keep pushing the newest JPEG until the tab closes."""
        # Never open a stream we cannot feed. A 200 that then goes silent leaves
        # the <img> hanging with no load and no error, which the UI can only
        # read as "still opening"; a 503 lets it show the reason and retry.
        first = self._await_frame(source, MJPEG_FIRST_FRAME_S)
        if first is None:
            self.send_error(HTTPStatus.SERVICE_UNAVAILABLE, "live view is not producing frames")
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"multipart/x-mixed-replace; boundary={MJPEG_BOUNDARY}")
        self.send_header("Connection", "close")
        self.end_headers()

        last_frame: bytes | None = None
        idle_since = time.monotonic()
        min_period = 1.0 / MJPEG_MAX_FPS
        try:
            while True:
                frame = source()
                if frame is None or frame is last_frame:
                    # Nothing new; do not burn the wire on duplicates. If the
                    # source stays dry the producer died — close so the client
                    # reconnects instead of watching a frozen picture.
                    if time.monotonic() - idle_since > MJPEG_IDLE_TIMEOUT_S:
                        return
                    time.sleep(0.02)
                    continue
                last_frame = frame
                idle_since = time.monotonic()
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


def bind_server(port: int = 8080, host: str = "0.0.0.0") -> ThreadingHTTPServer:
    """Claim the port before anything expensive opens.

    Grabbing the webcam first and *then* discovering the port is taken leaves
    the device held by a process that is already dying, so the next run cannot
    open it either.
    """
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    try:
        return ThreadingHTTPServer((host, port), TraceAPIHandler)
    except OSError as exc:
        if exc.errno != errno.EADDRINUSE:
            raise
        print(f"\n  port {port} is already in use — another web/server.py is probably running.")
        print(f"  Reuse it at http://localhost:{port}, or free the port with:")
        print(f"      kill $(lsof -ti tcp:{port})")
        print(f"  ...or start this one elsewhere with --port {port + 1}\n")
        raise SystemExit(1) from None


def run_server(port: int = 8080, host: str = "0.0.0.0", server: ThreadingHTTPServer | None = None) -> None:
    if server is None:
        server = bind_server(port, host)
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
    # Bind first: see bind_server(). Nothing below should touch hardware until
    # we know this process is the one that will actually serve.
    server = bind_server(args.port, args.host)
    if args.camera:
        state = CAMERA.start()
        print(f" camera: {'running' if state.running else 'unavailable — ' + str(state.error)}")
    if args.twin:
        TWIN.start(source=args.source)
        print(f" twin: headless render started (source={args.source})")
    run_server(port=args.port, host=args.host, server=server)
