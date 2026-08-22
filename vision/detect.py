"""Bounding-box pass: the largest non-cube object on the table, with a label.

`vision/cube.py` finds the red cube because the skill needs its centroid. This
module answers a different question — "is there something else in frame we do
not have geometry for?" — and answers it as a box plus a coarse label, because
that is what the import flow needs: a rectangle to draw on the HUD, and a
string to search the 3D-asset web with.

Labelling is colour + aspect ratio, nothing more. That is honest about what a
webcam heuristic can do, and it is enough for the one case the demo hardcodes:
a **grey water bottle** — desaturated, upright, roughly 2.5-3.5x taller than
wide. Everything else gets a generic shape label ("blue bottle", "dark box")
and goes through the real Bright Data mesh ladder instead of the shortcut.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from vision.cube import red_mask

# The hardcoded case. `matches_hardcoded()` is the single place that decides
# whether the shortcut fires, so the import service never re-derives it.
GRAY_BOTTLE_LABEL = "gray water bottle"

_KERNEL = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))

# Grey = low saturation, mid value. Below _GRAY_V_MIN it is a shadow, above
# _GRAY_V_MAX it is a blown-out highlight or the white table.
_GRAY_S_MAX = 60
_GRAY_V_MIN = 55
_GRAY_V_MAX = 205

# A bottle standing on a table: clearly taller than wide, but not a pen.
_BOTTLE_MIN_ASPECT = 1.9
_BOTTLE_MAX_ASPECT = 5.0

_HUE_NAMES = (
    (10, "red"), (25, "orange"), (35, "yellow"), (85, "green"),
    (100, "cyan"), (130, "blue"), (160, "purple"), (180, "red"),
)


@dataclass(frozen=True)
class Detection:
    """One bounding box the twin has no geometry for."""

    label: str
    bbox: tuple[int, int, int, int]  # x, y, w, h in pixels
    area_px: float
    aspect: float  # h / w
    confidence: float
    is_gray: bool

    @property
    def hardcoded(self) -> bool:
        """True when this is the grey-bottle case the demo ships a stub for."""
        return matches_hardcoded(self.label)

    def as_json(self) -> dict:
        return {
            "label": self.label,
            "bbox": list(self.bbox),
            "area_px": round(self.area_px, 1),
            "aspect": round(self.aspect, 2),
            "confidence": round(self.confidence, 2),
            "is_gray": self.is_gray,
            "hardcoded": self.hardcoded,
        }


def matches_hardcoded(label: str) -> bool:
    """Whether `label` is the grey water bottle we import without a download."""
    text = label.lower()
    return ("gray" in text or "grey" in text) and "bottle" in text


def _hue_name(hue: float) -> str:
    for edge, name in _HUE_NAMES:
        if hue <= edge:
            return name
    return "red"


def _label_for(frame_hsv: np.ndarray, mask: np.ndarray, aspect: float) -> tuple[str, bool]:
    """Colour word + shape word. Grey + bottle-ish aspect is the hardcoded case."""
    hue, saturation, value = (float(np.median(frame_hsv[..., i][mask > 0])) for i in range(3))
    is_gray = saturation <= _GRAY_S_MAX and _GRAY_V_MIN <= value <= _GRAY_V_MAX
    colour = "gray" if is_gray else _hue_name(hue)

    if _BOTTLE_MIN_ASPECT <= aspect <= _BOTTLE_MAX_ASPECT:
        shape = "water bottle" if is_gray else "bottle"
    elif aspect > _BOTTLE_MAX_ASPECT:
        shape = "rod"
    elif aspect < 0.6:
        shape = "tray"
    else:
        shape = "box"
    return f"{colour} {shape}", is_gray


def detect_object(frame: np.ndarray, min_area_px: float = 2500.0) -> Detection | None:
    """Largest foreground blob that is not the red cube, as a labelled box.

    Returns None on an empty table. Everything here is deliberately cheap: it
    runs on the same thread as the tracker, a few times a second.
    """
    if frame is None or frame.size == 0:
        return None
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # Foreground = anything that stands out from the table by saturation or by
    # being darker/lighter than its surroundings. Adaptive thresholding keeps a
    # grey bottle (which has almost no saturation) from vanishing.
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.adaptiveThreshold(
        cv2.GaussianBlur(gray, (5, 5), 0), 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 8,
    )
    saturated = cv2.inRange(hsv, np.array([0, 70, 40], np.uint8), np.array([179, 255, 255], np.uint8))
    mask = cv2.bitwise_or(edges, saturated)
    mask = cv2.bitwise_and(mask, cv2.bitwise_not(red_mask(frame)))  # the cube is not news
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, _KERNEL)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, _KERNEL)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    contour = max(contours, key=cv2.contourArea)
    area = float(cv2.contourArea(contour))
    if area < min_area_px:
        return None

    x, y, w, h = cv2.boundingRect(contour)
    if w <= 0 or h <= 0:
        return None

    blob_mask = np.zeros(mask.shape, np.uint8)
    cv2.drawContours(blob_mask, [contour], -1, 255, cv2.FILLED)
    aspect = h / float(w)
    label, is_gray = _label_for(hsv, blob_mask, aspect)

    # Fill ratio doubles as the confidence: a clean object fills its box, a
    # lighting artefact does not.
    confidence = float(np.clip(area / float(w * h), 0.0, 1.0))
    return Detection(
        label=label,
        bbox=(int(x), int(y), int(w), int(h)),
        area_px=area,
        aspect=float(aspect),
        confidence=confidence,
        is_gray=is_gray,
    )
