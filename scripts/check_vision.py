"""Prove track_cube geometry without a camera.

Renders a synthetic table: an AprilTag at the origin and a lime-green cube at a known
spot, seen from several camera poses. The recovered x,y must match the truth
from every pose — that is exactly "walk the camera, the cube stays planted".

Two lighting cases, because they fail differently:

* `silhouette` — the whole cube reads lime green.
* `top` — the sides are shadowed and only the top square passes the threshold.
  This one is the drift you notice by eye: the blob floats a cube-height above
  the table, so a naive back-projection slides with the camera angle.
* `partial` — what a real desk actually gives you: the top plus the lit side,
  with the shadowed side bitten out of the outline.
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
from vision.cube import find_cube_blob
from vision.tag import TagDetector
from vision.solve import fit_cube
from vision.tracker import _pixel_to_plane

WIDTH, HEIGHT = 1280, 720
TAG_SIZE_M = 0.15
CUBE_HALF_M = 0.025
CUBE_XY = (0.18, -0.12)  # truth, in the tag frame
PLANE_Z = CUBE_HALF_M
# A blob that is exactly one of the two hypotheses solves to well under a
# millimetre. A partly shadowed one sits between them, so it gets more room.
TOLERANCE_M = {"silhouette": 0.005, "top": 0.005, "partial": 0.010}

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


def render(rotation, translation, matrix, surface: str) -> np.ndarray:
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

    # Lime-green cube: either its full outline, or just the top face when the sides are
    # too dark to pass the colour threshold.
    cx, cy = CUBE_XY
    size = 2 * CUBE_HALF_M
    top = [
        [cx + sx * CUBE_HALF_M, cy + sy * CUBE_HALF_M, size]
        for sx in (-1.0, 1.0)
        for sy in (-1.0, 1.0)
    ]
    base = [
        [cx + sx * CUBE_HALF_M, cy + sy * CUBE_HALF_M, 0.0]
        for sx in (-1.0, 1.0)
        for sy in (-1.0, 1.0)
    ]
    if surface == "top":
        corners = np.array(top)
    elif surface == "partial":
        # Only the two base corners closest to the camera survive: the far side
        # of the cube is in shadow and never passes the colour threshold.
        eye = (-rotation.T @ translation).reshape(3)
        nearest = sorted(base, key=lambda c: np.linalg.norm(np.array(c) - eye))[:2]
        corners = np.array(top + nearest)
    else:
        corners = np.array(top + base)
    pts = _project(corners, rotation, translation, matrix).astype(np.float32)
    cv2.fillConvexPoly(frame, cv2.convexHull(pts).astype(int), (50, 255, 50))
    return frame


def main() -> int:
    intrinsics = Intrinsics.guess(WIDTH, HEIGHT, 60.0)
    detector = TagDetector(TAG_SIZE_M)
    rows: list[tuple[str, str, str]] = []
    failed = False

    for surface, (i, (eye, target)) in [
        (s, p) for s in ("silhouette", "top", "partial") for p in enumerate(POSES)
    ]:
        rotation, translation = _look_at(eye, target)
        frame = render(rotation, translation, intrinsics.matrix, surface)
        label = f"{surface:10} pose {i}"
        tag = detector.detect(frame, intrinsics.matrix, intrinsics.distortion)
        if tag is None:
            rows.append((label, "FAIL", "tag 0 not detected"))
            failed = True
            continue
        blob = find_cube_blob(frame)
        if blob is None:
            rows.append((label, "FAIL", "lime cube blob not found"))
            failed = True
            continue
        seed = _pixel_to_plane(tag, blob.u, blob.v, intrinsics.matrix, PLANE_Z)
        if seed is None:
            rows.append((label, "FAIL", "ray missed the table plane"))
            failed = True
            continue
        fit = fit_cube(
            tag,
            (blob.u, blob.v),
            blob.area_px,
            intrinsics.matrix,
            2 * CUBE_HALF_M,
            seed,
            blob.contour,
        )
        if fit is None:
            rows.append((label, "FAIL", "surface solve did not converge"))
            failed = True
            continue
        xy = fit.xy
        error = float(np.hypot(xy[0] - CUBE_XY[0], xy[1] - CUBE_XY[1]))
        naive = float(np.hypot(seed[0] - CUBE_XY[0], seed[1] - CUBE_XY[1]))
        ok = error <= TOLERANCE_M[surface]
        failed = failed or not ok
        rows.append(
            (
                label,
                "OK" if ok else "FAIL",
                f"err {error * 100:.2f} cm  (raw centroid {naive * 100:.2f} cm)  "
                f"read as {fit.surface}  from eye {eye}",
            )
        )

    print("track_cube geometry (synthetic, no camera)")
    tolerances = "  ".join(f"{k} {v * 100:.1f} cm" for k, v in TOLERANCE_M.items())
    print(f"  truth: cube at {CUBE_XY[0]:+.3f} {CUBE_XY[1]:+.3f} m")
    print(f"  tolerance: {tolerances}")
    print()
    for name, status, detail in rows:
        print(f"  {name}  {status:4}  {detail}")
    print()
    print("Next: python -m vision.track   (real camera + HUD)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
