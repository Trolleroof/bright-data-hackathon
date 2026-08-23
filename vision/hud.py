"""HUD overlay: tag seen yes/no, cube x,y, latency, scrape provenance."""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from vision.tracker import TrackResult

_GREEN = (80, 220, 120)
_LIME = (50, 255, 50)
_RED = (60, 60, 235)
_AMBER = (0, 170, 255)
_WHITE = (245, 245, 245)

_MAX_URL_CHARS = 52


def _draw_line(frame: np.ndarray, text: str, x: int, y: int, color, scale: float = 0.62) -> None:
    cv2.putText(frame, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(frame, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1, cv2.LINE_AA)


_IMPORT_COLORS = {
    "AWAITING": _AMBER,
    "IMPORTING": (255, 180, 60),
    "READY": _GREEN,
    "FAILED": _RED,
}


def _draw_detection(frame: np.ndarray, detection: Any, import_status: str) -> None:
    """The bounding box, plus what the import flow currently thinks of it."""
    x, y, w, h = detection.bbox
    color = _IMPORT_COLORS.get(import_status, _WHITE)
    cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
    caption = f"{detection.label}  {detection.confidence:.0%}"
    if import_status in _IMPORT_COLORS:
        caption += f"  [{import_status}]"
    # Above the box normally, inside it when the box starts at the top of the
    # frame — otherwise the caption lands on the stats block and the two render
    # over each other into an unreadable smear.
    caption_y = y - 8 if y > 24 else min(y + 20, frame.shape[0] - 6)
    _draw_line(frame, caption, x, caption_y, color, scale=0.55)


def draw(
    result: TrackResult,
    prompt_state: str = "IDLE",
    catalog: dict[str, Any] | None = None,
    detection: Any | None = None,
    import_state: dict[str, Any] | None = None,
) -> np.ndarray | None:
    if result.frame is None:
        return None
    frame = result.frame.copy()

    if result.tag is not None:
        corners = result.tag.corners.astype(int)
        cv2.polylines(frame, [corners], True, _GREEN, 2)
        cv2.putText(frame, "tag 0", tuple(corners[0]), cv2.FONT_HERSHEY_SIMPLEX, 0.5, _GREEN, 1)
    if result.blob is not None:
        cv2.drawContours(frame, [result.blob.contour], -1, _LIME, 2)
        cv2.circle(frame, (int(result.blob.u), int(result.blob.v)), 4, _WHITE, -1)
    if detection is not None:
        _draw_detection(frame, detection, str((import_state or {}).get("status", "IDLE")))

    state_color = _GREEN if prompt_state == "IDLE" else (60, 180, 255) if prompt_state == "RECORDING" else (255, 180, 60)
    lines = [
        (f"prompt: {prompt_state}", state_color),
        ("tag: YES" if result.tag_seen else "tag: NO", _GREEN if result.tag_seen else _RED),
        (
            f"cube: {result.cube_xy[0]:+.3f} {result.cube_xy[1]:+.3f} m"
            if result.cube_xy
            else "cube: --",
            _WHITE if result.cube_xy else _RED,
        ),
        (f"surface: {result.surface}", _WHITE),
        (f"latency: {result.latency_ms:5.1f} ms   fps: {result.fps:4.1f}", _WHITE),
    ]
    y = 28
    for text, color in lines:
        _draw_line(frame, text, 12, y, color)
        y += 28

    status = str((import_state or {}).get("status", "IDLE"))
    if status in _IMPORT_COLORS:
        label = str((import_state or {}).get("label", "object"))
        text = {
            "AWAITING": f"import {label}? -> answer in the dashboard",
            "IMPORTING": f"importing {label}…",
            "READY": f"{label} loaded into the twin",
            "FAILED": f"import failed: {(import_state or {}).get('error', '')}"[:70],
        }[status]
        _draw_line(frame, text, 12, y, _IMPORT_COLORS[status])
        y += 28

    if catalog is not None:
        y = _draw_provenance(frame, catalog, y)
    return frame


def _draw_provenance(frame: np.ndarray, catalog: dict[str, Any], y: int) -> int:
    """Bright Data proof strip: source (live vs fixture), URL, latency — not silent fallback."""
    source = str(catalog.get("source", "unknown")).upper()
    is_live = source == "LIVE"
    badge_color = _GREEN if is_live else _AMBER
    label = "BRIGHTDATA: LIVE SCRAPE" if is_live else "BRIGHTDATA: FIXTURE FALLBACK"

    y += 10
    (w, h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.62, 2)
    cv2.rectangle(frame, (8, y - h - 8), (18 + w, y + 8), badge_color, -1)
    cv2.putText(frame, label, (13, y), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (15, 15, 15), 2, cv2.LINE_AA)
    y += 30

    url = str(catalog.get("url") or "--")
    if len(url) > _MAX_URL_CHARS:
        url = url[: _MAX_URL_CHARS - 1] + "…"
    _draw_line(frame, f"url: {url}", 12, y, _WHITE, scale=0.52)
    y += 24

    latency = catalog.get("latency_ms")
    name = catalog.get("name")
    detail = f"latency: {latency:.1f} ms" if isinstance(latency, (int, float)) else "latency: --"
    if name:
        detail += f"   {name}"
    _draw_line(frame, detail, 12, y, _WHITE, scale=0.52)
    y += 24
    return y
