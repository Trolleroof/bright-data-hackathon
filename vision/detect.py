"""Bounding-box pass: the largest non-cube object on the table, with a label.

`vision/cube.py` finds the lime-green cube because the skill needs its centroid. This
module answers a different question — "is there something else in frame we do
not have geometry for?" — and answers it as a box plus a coarse label, because
that is what the import flow needs: a rectangle to draw on the HUD, and a
string to search the 3D-asset web with.

Labelling is colour + aspect ratio, nothing more. That is honest about what a
webcam heuristic can do: an upright bottle becomes a searchable water-bottle
query, while other blobs get a generic shape label and use the same import
ladder.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from vision.cube import cube_mask

_KERNEL = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))

# Grey = low saturation, mid value. Below _GRAY_V_MIN it is a shadow, above
# _GRAY_V_MAX it is a blown-out highlight or the white table.
_GRAY_S_MAX = 60
_GRAY_V_MIN = 55
_GRAY_V_MAX = 205

# A bottle standing on a table: clearly taller than wide, but not a pen.
_BOTTLE_MIN_ASPECT = 1.9
_BOTTLE_MAX_ASPECT = 5.0

# An object sitting on the table occupies a modest part of the frame. Anything
# bigger is the room: the wall behind the table, the table itself, or a
# lighting gradient the adaptive threshold latched onto. Those used to become a
# permanent "import this?" prompt for a box the size of the picture.
_MAX_AREA_FRAC = 0.30
# ...and it is framed, not cut off. A blob running off three sides of the
# picture is the background with a hole in it, whatever its area.
_MAX_EDGES_TOUCHED = 2
_EDGE_SLACK_PX = 3

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
        """Compatibility field; all detected objects use the searchable path."""
        return False

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


def _is_background(bbox: tuple[int, int, int, int], area: float, shape: tuple[int, ...]) -> bool:
    """True when a blob is the room rather than something standing on the table."""
    x, y, w, h = bbox
    frame_h, frame_w = shape[:2]
    if area > _MAX_AREA_FRAC * frame_w * frame_h:
        return True
    edges = sum(
        (
            x <= _EDGE_SLACK_PX,
            y <= _EDGE_SLACK_PX,
            x + w >= frame_w - _EDGE_SLACK_PX,
            y + h >= frame_h - _EDGE_SLACK_PX,
        )
    )
    return edges > _MAX_EDGES_TOUCHED


def detect_object(
    frame: np.ndarray, min_area_px: float = 2500.0, max_area_frac: float = _MAX_AREA_FRAC
) -> Detection | None:
    """Largest table-sized foreground blob that is not the cube, as a labelled box.

    Returns None on an empty table, and — just as importantly — None when the
    biggest blob is the background. Everything here is deliberately cheap: it
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
    mask = cv2.bitwise_and(mask, cv2.bitwise_not(cube_mask(frame)))  # the cube is not news
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, _KERNEL)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, _KERNEL)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    # Largest *plausible* blob, not simply the largest: on a lit table the
    # biggest contour is usually the room, and skipping past it is the
    # difference between one prompt about the bottle and an endless prompt
    # about the wall.
    contour = None
    for candidate in sorted(contours, key=cv2.contourArea, reverse=True):
        area = float(cv2.contourArea(candidate))
        if area < min_area_px:
            break
        box = cv2.boundingRect(candidate)
        if box[2] <= 0 or box[3] <= 0:
            continue
        if area > max_area_frac * frame.shape[0] * frame.shape[1] or _is_background(box, area, frame.shape):
            continue
        contour = candidate
        break
    if contour is None:
        return None

    area = float(cv2.contourArea(contour))
    x, y, w, h = cv2.boundingRect(contour)

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
