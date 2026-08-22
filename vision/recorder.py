"""Record ~3–12 s of table-frame cube motion into a prompt bag."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

import numpy as np

from vision.bag import BagFrame, PromptBag, new_bag_id, save_bag
from vision.cube import find_not_red_blob
from vision.tracker import CubeTracker, TrackResult


class PromptState(str, Enum):
    IDLE = "IDLE"
    RECORDING = "RECORDING"
    PROMPTED = "PROMPTED"


@dataclass
class RecorderConfig:
    min_duration_s: float = 3.0
    max_duration_s: float = 12.0
    min_frames: int = 10


class PhysicalPromptRecorder:
    """Manual start/stop only — walking the camera never starts a recording."""

    def __init__(self, tracker: CubeTracker, config: RecorderConfig | None = None) -> None:
        self.tracker = tracker
        self.config = config or RecorderConfig()
        self.state = PromptState.IDLE
        self._frames: list[BagFrame] = []
        self._started_at: float | None = None
        self._started_iso = ""
        self._bag_id = ""
        self.last_bag_path: str | None = None

    def toggle(self, result: TrackResult) -> PromptState:
        if self.state is PromptState.PROMPTED:
            self.reset()
        if self.state is PromptState.IDLE:
            return self.start()
        return self.stop(result)

    def start(self) -> PromptState:
        self.state = PromptState.RECORDING
        self._frames = []
        self._started_at = time.perf_counter()
        self._started_iso = datetime.now(timezone.utc).isoformat()
        self._bag_id = new_bag_id()
        self.last_bag_path = None
        return self.state

    def reset(self) -> PromptState:
        self.state = PromptState.IDLE
        self._frames = []
        self._started_at = None
        self._started_iso = ""
        self._bag_id = ""
        return self.state

    def sample(self, result: TrackResult) -> PromptState:
        if self.state is not PromptState.RECORDING or self._started_at is None:
            return self.state

        elapsed = time.perf_counter() - self._started_at
        obstacle_xy = self._obstacle_xy(result)
        self._frames.append(
            BagFrame(
                t=elapsed,
                cube_xy=result.cube_xy,
                obstacle_xy=obstacle_xy,
                tag_seen=result.tag_seen,
            )
        )
        if elapsed >= self.config.max_duration_s:
            return self.stop(result)
        return self.state

    def stop(self, result: TrackResult | None = None) -> PromptState:
        if self.state is not PromptState.RECORDING or self._started_at is None:
            return self.state
        if result is not None:
            self.sample(result)

        elapsed = time.perf_counter() - self._started_at
        valid = [frame for frame in self._frames if frame.cube_xy is not None]
        if elapsed < self.config.min_duration_s or len(valid) < self.config.min_frames:
            print(
                f"  recording too short ({elapsed:.1f}s, {len(valid)} cube frames); "
                f"need {self.config.min_duration_s}s and {self.config.min_frames} frames"
            )
            self.reset()
            return self.state

        bag = PromptBag(
            frames=self._frames,
            started_at=self._started_iso,
            duration_s=elapsed,
            bag_id=self._bag_id,
        )
        path = save_bag(bag)
        self.last_bag_path = str(path)
        self.state = PromptState.PROMPTED
        print(f"  PROMPTED  |  saved {path.name}  |  {len(self._frames)} frames  |  {elapsed:.1f}s")
        return self.state

    def _obstacle_xy(self, result: TrackResult) -> tuple[float, float] | None:
        if result.frame is None or result.tag is None:
            return None
        blob = find_not_red_blob(result.frame)
        if blob is None:
            return None
        matrix = self.tracker.camera.intrinsics.matrix
        from vision.tracker import _pixel_to_plane  # noqa: PLC0415 — shared geometry helper

        point = _pixel_to_plane(
            result.tag,
            blob.u,
            blob.v,
            matrix,
            self.tracker.plane_z_m,
        )
        return point
