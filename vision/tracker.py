"""track_cube: every frame, turn the camera image into a table-frame cube x,y.

The AprilTag gives us where the camera is. The red blob gives us where the cube
is on screen. Back-project that pixel onto the table plane and you get metres in
the table frame — so walking the camera moves nothing in the twin.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, replace

import numpy as np

from vision.camera import Camera
from vision.cube import Blob, find_red_blob
from vision.solve import fit_cube
from vision.tag import TagDetector, TagPose


@dataclass(frozen=True)
class TrackResult:
    frame: np.ndarray | None = None
    tag: TagPose | None = None
    blob: Blob | None = None
    cube_xy: tuple[float, float] | None = None  # metres, table frame, smoothed
    raw_xy: tuple[float, float] | None = None
    surface: str = "?"  # which cube surface explained the blob: silhouette / top
    latency_ms: float = 0.0
    fps: float = 0.0

    @property
    def tag_seen(self) -> bool:
        return self.tag is not None


def _pixel_to_plane(
    tag: TagPose,
    u: float,
    v: float,
    camera_matrix: np.ndarray,
    plane_z: float,
) -> tuple[float, float] | None:
    """Intersect the ray through pixel (u, v) with the table plane z = plane_z."""
    inv_k = np.linalg.inv(camera_matrix)
    direction_cam = inv_k @ np.array([u, v, 1.0], dtype=np.float64)
    direction_tag = tag.ray_in_tag(direction_cam)
    origin_tag = tag.camera_in_tag
    if abs(direction_tag[2]) < 1e-9:
        return None  # camera looking edge-on at the table
    scale = (plane_z - origin_tag[2]) / direction_tag[2]
    if scale <= 0:
        return None  # plane is behind the camera
    point = origin_tag + scale * direction_tag
    return float(point[0]), float(point[1])


class CubeTracker:
    """Runs the per-frame pipeline. Call `step()` yourself or `start()` a thread."""

    def __init__(
        self,
        camera: Camera,
        tag_size_m: float,
        cube_size_m: float = 0.05,
        plane_z_m: float = 0.025,
        smoothing: float = 0.35,
        max_jump_m: float = 0.30,
    ) -> None:
        self.camera = camera
        self.detector = TagDetector(tag_size_m)
        self.cube_size_m = cube_size_m
        self.plane_z_m = plane_z_m
        self.smoothing = smoothing
        self.max_jump_m = max_jump_m

        self._smoothed: tuple[float, float] | None = None
        self._latest = TrackResult()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._last_frame_t = 0.0

    # --- one frame -------------------------------------------------------
    def step(self) -> TrackResult:
        started = time.perf_counter()
        frame = self.camera.read()
        if frame is None:
            return self._publish(replace(self._latest, frame=None))

        tag = self.detector.detect(frame, self.camera.intrinsics.matrix, self.camera.intrinsics.distortion)
        blob = find_red_blob(frame)
        raw_xy: tuple[float, float] | None = None
        surface = "?"
        if tag is not None and blob is not None:
            raw_xy, surface = self._blob_to_table(tag, blob)

        cube_xy = self._smooth(raw_xy)

        now = time.perf_counter()
        fps = 1.0 / (now - self._last_frame_t) if self._last_frame_t else 0.0
        self._last_frame_t = now
        return self._publish(
            TrackResult(
                frame=frame,
                tag=tag,
                blob=blob,
                cube_xy=cube_xy,
                raw_xy=raw_xy,
                surface=surface,
                latency_ms=(now - started) * 1000.0,
                fps=fps,
            )
        )

    def _blob_to_table(self, tag: TagPose, blob: Blob) -> tuple[tuple[float, float] | None, str]:
        """Blob → cube centre on the table, with the visible-surface bias removed."""
        matrix = self.camera.intrinsics.matrix
        seed = _pixel_to_plane(tag, blob.u, blob.v, matrix, self.plane_z_m)
        if seed is None:
            return None, "?"
        fit = fit_cube(
            tag, (blob.u, blob.v), blob.area_px, matrix, self.cube_size_m, seed, blob.contour
        )
        if fit is None:
            return seed, "raw"  # solve failed: the plane hit beats nothing
        return fit.xy, fit.surface

    def _smooth(self, raw_xy: tuple[float, float] | None) -> tuple[float, float] | None:
        if raw_xy is None:
            return self._smoothed  # tag or cube lost: hold the last known spot
        if self._smoothed is None:
            self._smoothed = raw_xy
            return self._smoothed
        dx = raw_xy[0] - self._smoothed[0]
        dy = raw_xy[1] - self._smoothed[1]
        if (dx * dx + dy * dy) ** 0.5 > self.max_jump_m:
            self._smoothed = raw_xy  # real teleport (cube picked up), snap
            return self._smoothed
        a = self.smoothing
        self._smoothed = (self._smoothed[0] + a * dx, self._smoothed[1] + a * dy)
        return self._smoothed

    def _publish(self, result: TrackResult) -> TrackResult:
        with self._lock:
            self._latest = result
        return result

    # --- background mode -------------------------------------------------
    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="cube-tracker", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.step()
            except Exception as exc:  # noqa: BLE001 — a bad frame must not kill the twin
                print(f"  tracker: {exc}")
                time.sleep(0.1)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

    @property
    def latest(self) -> TrackResult:
        with self._lock:
            return self._latest
