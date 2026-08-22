"""Prove track_cube geometry without a camera.

Renders a synthetic table: an AprilTag at the origin and a red cube at a known
spot, seen from several camera poses. The recovered x,y must be the same from
every pose — that is exactly "walk the camera, the cube stays planted".
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cv2
import numpy as np

from vision.camera import Intrinsics
from vision.cube import find_red_blob
from vision.tag import TagDetector
from vision.tracker import _pixel_to_plane

WIDTH, HEIGHT = 1280, 720
TAG_SIZE_M = 0.15
CUBE_HALF_M = 0.025
CUBE_XY = (0.18, -0.12)  # truth, in the tag frame
PLANE_Z = CUBE_HALF_M
TOLERANCE_M = 0.025  # colour-blob centroid sits between the top and the visible side face

# Camera poses: (eye, target) in the tag frame. Walking around the table.
POSES = [
    ((0.05, -0.55, 0.55), (0.08, -0.05, 0.0)),
    ((-0.35, -0.50, 0.45), (0.05, -0.05, 0.0)),
    ((0.40, -0.45, 0.60), (0.05, -0.05, 0.0)),
    ((0.00, -0.35, 0.75), (0.05, -0.08, 0.0)),
]


def _look_at(eye: tuple[float, float, float], target: tuple[float, float, float]):
    """World→camera rotation and translation for a camera at `eye` facing `target`."""
    eye_v = np.array(eye, dtype=np.float64)
    forward = np.array(target, dtype=np.float64) - eye_v
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, np.array([0.0, 0.0, 1.0]))
    right /= np.linalg.norm(right)
    down = np.cross(forward, right)
    rotation = np.vstack([right, down, forward])  # rows: camera x, y, z axes
    return rotation, (-rotation @ eye_v).reshape(3, 1)


def _project(points: np.ndarray, rotation, translation, matrix) -> np.ndarray:
    cam = (rotation @ points.T + translation).T
    uv = (matrix @ cam.T).T
    return uv[:, :2] / uv[:, 2:3]


def _tag_image(size_px: int = 400) -> np.ndarray:
    tag = cv2.aruco.generateImageMarker(
        cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11), 0, size_px
    )
    return cv2.cvtColor(tag, cv2.COLOR_GRAY2BGR)


def render(rotation, translation, matrix) -> np.ndarray:
    frame = np.full((HEIGHT, WIDTH, 3), 200, dtype=np.uint8)

    half = TAG_SIZE_M / 2.0
    tag_corners = np.array(
        [[-half, half, 0.0], [half, half, 0.0], [half, -half, 0.0], [-half, -half, 0.0]]
    )
    dst = _project(tag_corners, rotation, translation, matrix).astype(np.float32)
    tag = _tag_image()
    src = np.array(
        [[0, 0], [tag.shape[1] - 1, 0], [tag.shape[1] - 1, tag.shape[0] - 1], [0, tag.shape[0] - 1]],
        dtype=np.float32,
    )
    warp = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(tag, warp, (WIDTH, HEIGHT), borderMode=cv2.BORDER_TRANSPARENT)
    mask = np.zeros((HEIGHT, WIDTH), dtype=np.uint8)
    cv2.fillConvexPoly(mask, dst.astype(int), 255)
    frame[mask > 0] = warped[mask > 0]

    # Red cube: its top face, which is what a colour blob centroid lands on.
    cx, cy = CUBE_XY
    top = np.array(
        [
            [cx - CUBE_HALF_M, cy - CUBE_HALF_M, 2 * CUBE_HALF_M],
            [cx + CUBE_HALF_M, cy - CUBE_HALF_M, 2 * CUBE_HALF_M],
            [cx + CUBE_HALF_M, cy + CUBE_HALF_M, 2 * CUBE_HALF_M],
            [cx - CUBE_HALF_M, cy + CUBE_HALF_M, 2 * CUBE_HALF_M],
        ]
    )
    side = np.array(
        [
            [cx - CUBE_HALF_M, cy - CUBE_HALF_M, 0.0],
            [cx + CUBE_HALF_M, cy - CUBE_HALF_M, 0.0],
            [cx + CUBE_HALF_M, cy - CUBE_HALF_M, 2 * CUBE_HALF_M],
            [cx - CUBE_HALF_M, cy - CUBE_HALF_M, 2 * CUBE_HALF_M],
        ]
    )
    for face, color in ((side, (30, 30, 190)), (top, (40, 40, 220))):
        pts = _project(face, rotation, translation, matrix).astype(int)
        cv2.fillConvexPoly(frame, pts, color)
    return frame


def main() -> int:
    intrinsics = Intrinsics.guess(WIDTH, HEIGHT, 60.0)
    detector = TagDetector(TAG_SIZE_M)
    rows: list[tuple[str, str, str]] = []
    failed = False

    for i, (eye, target) in enumerate(POSES):
        rotation, translation = _look_at(eye, target)
        frame = render(rotation, translation, intrinsics.matrix)
        tag = detector.detect(frame, intrinsics.matrix, intrinsics.distortion)
        if tag is None:
            rows.append((f"pose {i}", "FAIL", "tag 0 not detected"))
            failed = True
            continue
        blob = find_red_blob(frame)
        if blob is None:
            rows.append((f"pose {i}", "FAIL", "red blob not found"))
            failed = True
            continue
        xy = _pixel_to_plane(tag, blob.u, blob.v, intrinsics.matrix, PLANE_Z)
        if xy is None:
            rows.append((f"pose {i}", "FAIL", "ray missed the table plane"))
            failed = True
            continue
        error = float(np.hypot(xy[0] - CUBE_XY[0], xy[1] - CUBE_XY[1]))
        ok = error <= TOLERANCE_M
        failed = failed or not ok
        rows.append(
            (
                f"pose {i}",
                "OK" if ok else "FAIL",
                f"cube {xy[0]:+.3f} {xy[1]:+.3f}  err {error * 100:.1f} cm  from eye {eye}",
            )
        )

    print("track_cube geometry (synthetic, no camera)")
    print(f"  truth: cube at {CUBE_XY[0]:+.3f} {CUBE_XY[1]:+.3f} m, tolerance {TOLERANCE_M * 100:.1f} cm")
    print()
    for name, status, detail in rows:
        print(f"  {name}  {status:4}  {detail}")
    print()
    print("Next: python -m vision.track   (real camera + HUD)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
