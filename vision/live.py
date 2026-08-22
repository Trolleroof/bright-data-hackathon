"""Camera as a shared, restartable service.

`python -m vision.track` owns a camera for one process. The web UI needs the
same pipeline running in the background, survivable across page reloads, and
readable as JPEG frames. This wraps CubeTracker in exactly that.

Everything here is best-effort: no camera, no AprilTag size, no OpenCV — the
service reports the reason and the rest of the twin keeps running.
"""

from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass
from typing import Any

_PLACEHOLDER_JPEG_QUALITY = 70


@dataclass
class CameraState:
    running: bool = False
    error: str | None = None
    tag_seen: bool = False
    cube_xy: tuple[float, float] | None = None
    raw_xy: tuple[float, float] | None = None
    surface: str = "?"
    latency_ms: float = 0.0
    fps: float = 0.0
    width: int = 0
    height: int = 0
    frames: int = 0
    prompt_state: str = "IDLE"

    def as_json(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["cube_xy"] = list(self.cube_xy) if self.cube_xy else None
        payload["raw_xy"] = list(self.raw_xy) if self.raw_xy else None
        return payload


class LiveCamera:
    """Singleton-ish camera service. Start it once; read `frame_jpeg()` anywhere."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._jpeg: bytes | None = None
        self._state = CameraState()
        self._camera = None
        self._tracker = None
        self._prompt_state = "IDLE"
        self._frame_event = threading.Event()

    # --- lifecycle -------------------------------------------------------
    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> CameraState:
        with self._lock:
            if self.running:
                return self._state
            self._stop.clear()
            try:
                from vision.track import build_tracker  # noqa: PLC0415 — optional dependency

                camera, tracker = build_tracker()
            except Exception as exc:  # noqa: BLE001 — a missing webcam must not 500 the UI
                self._state = CameraState(running=False, error=str(exc))
                return self._state
            self._camera, self._tracker = camera, tracker
            self._state = CameraState(
                running=True, width=camera.width, height=camera.height
            )
            self._thread = threading.Thread(
                target=self._loop, name="live-camera", daemon=True
            )
            self._thread.start()
            return self._state

    def stop(self) -> CameraState:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
        self._thread = None
        if self._camera is not None:
            try:
                self._camera.close()
            except Exception:  # noqa: BLE001 — closing a dead camera is not an error
                pass
        self._camera = None
        self._tracker = None
        with self._lock:
            self._state.running = False
            self._jpeg = None
        return self._state

    def set_prompt_state(self, prompt_state: str) -> None:
        self._prompt_state = prompt_state

    # --- loop ------------------------------------------------------------
    def _loop(self) -> None:
        import cv2  # noqa: PLC0415 — only needed when the camera actually runs

        from vision import hud  # noqa: PLC0415

        frames = 0
        while not self._stop.is_set():
            try:
                result = self._tracker.step()
            except Exception as exc:  # noqa: BLE001 — a bad frame must not kill the feed
                with self._lock:
                    self._state.error = str(exc)
                time.sleep(0.1)
                continue

            frame = hud.draw(result, prompt_state=self._prompt_state)
            jpeg: bytes | None = None
            if frame is not None:
                ok, buf = cv2.imencode(
                    ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80]
                )
                if ok:
                    jpeg = buf.tobytes()
                    frames += 1

            with self._lock:
                if jpeg is not None:
                    self._jpeg = jpeg
                self._state = CameraState(
                    running=True,
                    error=None,
                    tag_seen=result.tag_seen,
                    cube_xy=result.cube_xy,
                    raw_xy=result.raw_xy,
                    surface=result.surface,
                    latency_ms=result.latency_ms,
                    fps=result.fps,
                    width=self._camera.width if self._camera else 0,
                    height=self._camera.height if self._camera else 0,
                    frames=frames,
                    prompt_state=self._prompt_state,
                )
            self._frame_event.set()
            self._frame_event.clear()

    # --- readers ---------------------------------------------------------
    def frame_jpeg(self) -> bytes | None:
        with self._lock:
            return self._jpeg

    def state(self) -> dict[str, Any]:
        with self._lock:
            return self._state.as_json()

    @property
    def tracker(self):  # noqa: ANN201 — CubeTracker or None, consumed by the twin
        return self._tracker


CAMERA = LiveCamera()
