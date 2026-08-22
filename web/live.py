"""Small browser-facing live view: webcam perception beside a MuJoCo render."""

from __future__ import annotations

import threading
import time

import cv2
import mujoco

from twin.sim import CubeAnchor, SCENE
from vision import hud
from vision.track import build_tracker


class LiveView:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._error: str | None = None
        self._tracker = None
        self._camera = None
        self._model = None
        self._data = None
        self._renderer = None
        self._render_camera = None
        self._render_thread: threading.Thread | None = None
        self._sim_frame: bytes | None = None
        self._anchor = None
        self._synced_xy: tuple[float, float] | None = None

    def start(self) -> dict:
        with self._lock:
            if self._tracker is not None:
                return self.status()
            self._error = None
            try:
                self._model = mujoco.MjModel.from_xml_path(str(SCENE))
                self._data = mujoco.MjData(self._model)
                mujoco.mj_forward(self._model, self._data)
                self._anchor = CubeAnchor(self._model)
                self._camera, self._tracker = build_tracker()
                self._tracker.start()
                self._render_thread = threading.Thread(
                    target=self._render_loop, name="twin-renderer", daemon=True
                )
                self._render_thread.start()
            except Exception as exc:  # Camera permissions / headless GL are user-facing state.
                self._error = str(exc)
            return self.status()

    def status(self) -> dict:
        result = self._tracker.latest if self._tracker is not None else None
        return {
            "running": self._tracker is not None,
            "error": self._error,
            "tag_seen": bool(result and result.tag_seen),
            "cube_xy": result.cube_xy if result else None,
            "synced_xy": self._synced_xy,
            "fps": round(result.fps, 1) if result else 0,
        }

    def sync(self) -> dict:
        with self._lock:
            if self._tracker is None or self._anchor is None or self._data is None:
                return {**self.status(), "synced": False, "error": "Start the camera first."}
            result = self._tracker.latest
            if not result.tag_seen or result.cube_xy is None:
                return {**self.status(), "synced": False, "error": "AprilTag 36h11 id 0 is not visible, so the twin will not use a stale cube position."}
            self._synced_xy = self._anchor.apply(self._data, result.cube_xy)
            mujoco.mj_forward(self._model, self._data)
            return {**self.status(), "synced": True, "synced_xy": self._synced_xy}

    def camera_jpeg(self) -> bytes | None:
        if self._tracker is None:
            return None
        frame = hud.draw(self._tracker.latest)
        if frame is None:
            return None
        ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 82])
        return encoded.tobytes() if ok else None

    def sim_jpeg(self) -> bytes | None:
        with self._lock:
            return self._sim_frame

    def _render_loop(self) -> None:
        """Own the OpenGL context and publish frames for HTTP threads."""
        try:
            renderer = mujoco.Renderer(self._model, height=480, width=640)
            camera = mujoco.MjvCamera()
            camera.type = mujoco.mjtCamera.mjCAMERA_FREE
            camera.lookat[:] = (0.0, 0.0, 0.55)
            camera.distance = 1.45
            camera.azimuth = 135
            camera.elevation = -28
            self._renderer = renderer
            self._render_camera = camera
            while True:
                with self._lock:
                    renderer.update_scene(self._data, camera=camera)
                    rgb = renderer.render()
                ok, encoded = cv2.imencode(
                    ".jpg",
                    cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR),
                    [cv2.IMWRITE_JPEG_QUALITY, 82],
                )
                if ok:
                    with self._lock:
                        self._sim_frame = encoded.tobytes()
                time.sleep(0.1)
        except Exception as exc:  # Surface renderer failures in the dashboard.
            with self._lock:
                self._error = f"Twin renderer failed: {exc}"


live_view = LiveView()
