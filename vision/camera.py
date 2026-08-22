"""Webcam capture + a usable pinhole model when we have no calibration file."""

from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class Intrinsics:
    matrix: np.ndarray
    distortion: np.ndarray

    @classmethod
    def guess(cls, width: int, height: int, fov_deg: float) -> "Intrinsics":
        """No calibration: assume a centered pinhole with the given horizontal FOV.

        Good enough to keep the cube planted; a real calibration only tightens it.
        """
        fx = (width / 2.0) / math.tan(math.radians(fov_deg) / 2.0)
        matrix = np.array(
            [[fx, 0.0, width / 2.0], [0.0, fx, height / 2.0], [0.0, 0.0, 1.0]],
            dtype=np.float64,
        )
        return cls(matrix=matrix, distortion=np.zeros((5, 1), dtype=np.float64))


class Camera:
    """Thin cv2.VideoCapture wrapper that knows its own intrinsics."""

    def __init__(self, index: int = 0, width: int = 1280, height: int = 720, fps: int = 60, fov_deg: float = 60.0) -> None:
        self._cap = cv2.VideoCapture(index)
        if not self._cap.isOpened():
            raise RuntimeError(f"camera {index} did not open (check macOS camera permission)")
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self._cap.set(cv2.CAP_PROP_FPS, fps)
        self.width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH) or width)
        self.height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or height)
        self.intrinsics = Intrinsics.guess(self.width, self.height, fov_deg)

    def read(self) -> np.ndarray | None:
        ok, frame = self._cap.read()
        return frame if ok else None

    def close(self) -> None:
        self._cap.release()

    def __enter__(self) -> "Camera":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
