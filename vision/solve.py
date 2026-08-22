"""Recover the cube's table position from whatever surface the camera actually sees.

A red blob is not the cube: it is the part of the cube that survived the colour
threshold. Two cases show up on a real table.

* **Silhouette** — the cube is lit evenly, top and sides both read red, and the
  blob is the cube's full outline.
* **Top face only** — the sides are shadowed or too dark to pass the threshold,
  so the blob is just the top square, floating 5 cm above the table.

Back-projecting the centroid onto a fixed plane is wrong in both cases, and
wrong by a *different* amount depending on where you stand — which is precisely
the drift you see when you walk the camera. So do the forward thing: for a
candidate x,y we know exactly where each hypothesis would put the blob, in both
centroid and area. Iterate x,y until the centroid matches, then keep whichever
hypothesis explains the measured area.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from vision.tag import TagPose

_ITERATIONS = 6
_TOLERANCE_PX = 0.3


@dataclass(frozen=True)
class CubeFit:
    xy: tuple[float, float]
    surface: str  # "silhouette" or "top"
    area_ratio: float  # predicted / measured; 1.0 is a perfect explanation


def project(tag: TagPose, points_tag: np.ndarray, camera_matrix: np.ndarray) -> np.ndarray | None:
    """Tag-frame points → pixels. None if anything falls behind the camera."""
    cam = (tag.rotation @ points_tag.T + tag.translation).T
    if np.any(cam[:, 2] <= 1e-6):
        return None
    uv = (camera_matrix @ cam.T).T
    return uv[:, :2] / uv[:, 2:3]


def _corners(x: float, y: float, size_m: float, surface: str) -> np.ndarray:
    half = size_m / 2.0
    heights = (size_m,) if surface == "top" else (0.0, size_m)
    return np.array(
        [
            [x + sx * half, y + sy * half, z]
            for sx in (-1.0, 1.0)
            for sy in (-1.0, 1.0)
            for z in heights
        ],
        dtype=np.float64,
    )


def predict(
    tag: TagPose, x: float, y: float, size_m: float, camera_matrix: np.ndarray, surface: str
) -> tuple[np.ndarray, float] | None:
    """Blob centroid and area in pixels if the cube sat at x, y showing `surface`."""
    uv = project(tag, _corners(x, y, size_m, surface), camera_matrix)
    if uv is None:
        return None
    hull = cv2.convexHull(uv.astype(np.float32))
    moments = cv2.moments(hull)
    if moments["m00"] == 0:
        return None
    centroid = np.array([moments["m10"] / moments["m00"], moments["m01"] / moments["m00"]])
    return centroid, float(moments["m00"])


def _solve_one(
    tag: TagPose,
    measured_uv: np.ndarray,
    camera_matrix: np.ndarray,
    size_m: float,
    seed_xy: tuple[float, float],
    surface: str,
) -> tuple[tuple[float, float], float] | None:
    """Fixed-point solve under one surface hypothesis. Returns x,y and its area."""
    from vision.tracker import _pixel_to_plane  # local: tracker owns the plane maths

    plane_z = size_m if surface == "top" else size_m / 2.0
    x, y = seed_xy
    area = 0.0
    for _ in range(_ITERATIONS):
        predicted = predict(tag, x, y, size_m, camera_matrix, surface)
        if predicted is None:
            return None
        centroid, area = predicted
        if float(np.linalg.norm(measured_uv - centroid)) < _TOLERANCE_PX:
            break
        # Locally the measured and predicted centroids differ by the same
        # homography, so shifting x,y by their difference on one plane converges.
        measured_on_plane = _pixel_to_plane(tag, measured_uv[0], measured_uv[1], camera_matrix, plane_z)
        predicted_on_plane = _pixel_to_plane(tag, centroid[0], centroid[1], camera_matrix, plane_z)
        if measured_on_plane is None or predicted_on_plane is None:
            return None
        x += measured_on_plane[0] - predicted_on_plane[0]
        y += measured_on_plane[1] - predicted_on_plane[1]
    return (float(x), float(y)), area


def fit_cube(
    tag: TagPose,
    measured_uv: tuple[float, float],
    measured_area_px: float,
    camera_matrix: np.ndarray,
    size_m: float,
    seed_xy: tuple[float, float],
) -> CubeFit | None:
    """Best x,y for the blob, choosing the surface hypothesis that fits its area."""
    measured = np.array(measured_uv, dtype=np.float64)
    best: CubeFit | None = None
    for surface in ("silhouette", "top"):
        solved = _solve_one(tag, measured, camera_matrix, size_m, seed_xy, surface)
        if solved is None:
            continue
        xy, area = solved
        if area <= 0 or measured_area_px <= 0:
            continue
        ratio = area / measured_area_px
        candidate = CubeFit(xy=xy, surface=surface, area_ratio=ratio)
        if best is None or abs(np.log(ratio)) < abs(np.log(best.area_ratio)):
            best = candidate
    return best
