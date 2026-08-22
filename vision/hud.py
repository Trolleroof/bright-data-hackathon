"""HUD overlay: tag seen yes/no, cube x,y, latency."""

from __future__ import annotations

import cv2
import numpy as np

from vision.tracker import TrackResult

_GREEN = (80, 220, 120)
_RED = (60, 60, 235)
_WHITE = (245, 245, 245)


def draw(result: TrackResult) -> np.ndarray | None:
    if result.frame is None:
        return None
    frame = result.frame.copy()

    if result.tag is not None:
        corners = result.tag.corners.astype(int)
        cv2.polylines(frame, [corners], True, _GREEN, 2)
        cv2.putText(frame, "tag 0", tuple(corners[0]), cv2.FONT_HERSHEY_SIMPLEX, 0.5, _GREEN, 1)
    if result.blob is not None:
        cv2.drawContours(frame, [result.blob.contour], -1, _RED, 2)
        cv2.circle(frame, (int(result.blob.u), int(result.blob.v)), 4, _WHITE, -1)

    lines = [
        ("tag: YES" if result.tag_seen else "tag: NO", _GREEN if result.tag_seen else _RED),
        (
            f"cube: {result.cube_xy[0]:+.3f} {result.cube_xy[1]:+.3f} m"
            if result.cube_xy
            else "cube: --",
            _WHITE if result.cube_xy else _RED,
        ),
        (f"latency: {result.latency_ms:5.1f} ms   fps: {result.fps:4.1f}", _WHITE),
    ]
    y = 28
    for text, color in lines:
        cv2.putText(frame, text, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(frame, text, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.62, color, 1, cv2.LINE_AA)
        y += 28
    return frame
