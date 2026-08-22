"""AprilTag 36h11 id 0 → camera pose in the table frame.

Tag frame: origin at the tag center, +x right, +y up along the tag, z out of the
table. The table plane is z = 0 in this frame, which is the whole point.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

TAG_ID = 0
_DICT = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)


@dataclass(frozen=True)
class TagPose:
    rotation: np.ndarray  # 3x3, tag → camera
    translation: np.ndarray  # 3x1, tag origin in camera frame
    corners: np.ndarray  # 4x2 pixel corners, for the HUD

    @property
    def camera_in_tag(self) -> np.ndarray:
        """Camera center expressed in the tag frame."""
        return (-self.rotation.T @ self.translation).reshape(3)

    def ray_in_tag(self, direction_cam: np.ndarray) -> np.ndarray:
        return self.rotation.T @ direction_cam.reshape(3)


class TagDetector:
    def __init__(self, size_m: float) -> None:
        if size_m <= 0:
            raise ValueError("APRILTAG_SIZE_CM must be set and positive")
        self.size_m = size_m
        half = size_m / 2.0
        # Corner order matches cv2.aruco: top-left, top-right, bottom-right, bottom-left.
        self._object_points = np.array(
            [[-half, half, 0.0], [half, half, 0.0], [half, -half, 0.0], [-half, -half, 0.0]],
            dtype=np.float64,
        )
        params = cv2.aruco.DetectorParameters()
        params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        self._detector = cv2.aruco.ArucoDetector(_DICT, params)

    def detect(self, frame: np.ndarray, camera_matrix: np.ndarray, distortion: np.ndarray) -> TagPose | None:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = self._detector.detectMarkers(gray)
        if ids is None:
            return None
        for marker_corners, marker_id in zip(corners, ids.flatten()):
            if int(marker_id) != TAG_ID:
                continue
            image_points = marker_corners.reshape(4, 2).astype(np.float64)
            ok, rvec, tvec = cv2.solvePnP(
                self._object_points,
                image_points,
                camera_matrix,
                distortion,
                flags=cv2.SOLVEPNP_IPPE_SQUARE,
            )
            if not ok:
                return None
            rotation, _ = cv2.Rodrigues(rvec)
            return TagPose(rotation=rotation, translation=tvec.reshape(3, 1), corners=image_points)
        return None
