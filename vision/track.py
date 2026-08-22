"""Camera-only check: python -m vision.track

Shows the HUD so you can confirm the tag is seen and the cube x,y is sane
before you point the twin at it. Press q or ESC to quit.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cv2

from integrations.config import load_settings
from vision import hud
from vision.camera import Camera
from vision.tracker import CubeTracker


def build_tracker(camera: Camera | None = None) -> tuple[Camera, CubeTracker]:
    """Camera + tracker wired from .env. Raises if APRILTAG_SIZE_CM is missing."""
    settings = load_settings()
    if settings.apriltag_size_m <= 0:
        raise RuntimeError("set APRILTAG_SIZE_CM in .env (outer black square of the printed tag)")
    if camera is None:
        camera = Camera(
            index=settings.camera_index,
            width=settings.camera_width,
            height=settings.camera_height,
            fov_deg=settings.camera_fov_deg,
        )
    tracker = CubeTracker(
        camera=camera,
        tag_size_m=settings.apriltag_size_m,
        cube_size_m=settings.cube_size_cm / 100.0,
        plane_z_m=settings.cube_track_height_cm / 100.0,
    )
    return camera, tracker


def main() -> int:
    camera, tracker = build_tracker()
    print("track_cube  |  q or ESC to quit")
    try:
        while True:
            result = tracker.step()
            frame = hud.draw(result)
            if frame is not None:
                cv2.imshow("ScaleTwin — track_cube", frame)
            if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                break
    finally:
        camera.close()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
