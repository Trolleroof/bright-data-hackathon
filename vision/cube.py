"""Lime-green blob → pixel centroid. Colour only; we never classify what the object is."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

# Lime green sits in one HSV band (unlike red). Keep V/S floors low enough that a
# shadowed cube face still passes — same tradeoff as the old red thresholds.
_LIME_LOW = np.array([35, 100, 80], dtype=np.uint8)
_LIME_HIGH = np.array([85, 255, 255], dtype=np.uint8)

_KERNEL = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))


@dataclass(frozen=True)
class Blob:
    u: float
    v: float
    area_px: float
    contour: np.ndarray


def cube_mask(frame: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, _LIME_LOW, _LIME_HIGH)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, _KERNEL)
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, _KERNEL)


def find_cube_blob(frame: np.ndarray, min_area_px: float = 250.0) -> Blob | None:
    mask = cube_mask(frame)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    contour = max(contours, key=cv2.contourArea)
    area = float(cv2.contourArea(contour))
    if area < min_area_px:
        return None
    moments = cv2.moments(contour)
    if moments["m00"] == 0:
        return None
    return Blob(
        u=moments["m10"] / moments["m00"],
        v=moments["m01"] / moments["m00"],
        area_px=area,
        contour=contour,
    )


# Backward-compatible names used in a few call sites / docs.
red_mask = cube_mask
find_red_blob = find_cube_blob


def find_not_cube_blob(frame: np.ndarray, min_area_px: float = 1200.0) -> Blob | None:
    """Largest saturated blob that is not the lime cube — bottle, tape roll, etc."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    not_cube = cv2.bitwise_not(cube_mask(frame))
    saturation = cv2.inRange(hsv, np.array([0, 60, 40], dtype=np.uint8), np.array([179, 255, 255], dtype=np.uint8))
    mask = cv2.bitwise_and(not_cube, saturation)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, _KERNEL)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, _KERNEL)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    contour = max(contours, key=cv2.contourArea)
    area = float(cv2.contourArea(contour))
    if area < min_area_px:
        return None
    moments = cv2.moments(contour)
    if moments["m00"] == 0:
        return None
    return Blob(
        u=moments["m10"] / moments["m00"],
        v=moments["m01"] / moments["m00"],
        area_px=area,
        contour=contour,
    )


find_not_red_blob = find_not_cube_blob
