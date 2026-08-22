"""Red blob → pixel centroid. Colour only; we never classify what the object is."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

# Red wraps around the hue circle, so it takes two bands. The value floor is
# low on purpose: a shadowed cube face is still red, and dropping it bites a
# chunk out of the outline the pose solve has to explain.
_LOW_1 = np.array([0, 120, 50], dtype=np.uint8)
_HIGH_1 = np.array([10, 255, 255], dtype=np.uint8)
_LOW_2 = np.array([170, 120, 50], dtype=np.uint8)
_HIGH_2 = np.array([180, 255, 255], dtype=np.uint8)

_KERNEL = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))


@dataclass(frozen=True)
class Blob:
    u: float
    v: float
    area_px: float
    contour: np.ndarray


def red_mask(frame: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.bitwise_or(cv2.inRange(hsv, _LOW_1, _HIGH_1), cv2.inRange(hsv, _LOW_2, _HIGH_2))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, _KERNEL)
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, _KERNEL)


def find_red_blob(frame: np.ndarray, min_area_px: float = 250.0) -> Blob | None:
    mask = red_mask(frame)
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
