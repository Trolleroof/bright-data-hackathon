"""Extract skill params from a physical prompt bag."""

from __future__ import annotations

from dataclasses import dataclass

from vision.bag import PromptBag


@dataclass(frozen=True)
class ExtractedParams:
    path: list[list[float]]
    start: tuple[float, float]
    end: tuple[float, float]
    obstacle_xy: tuple[float, float] | None
    obstacle_label: str
    motion: str


def _downsample(points: list[tuple[float, float, float]], max_points: int = 48) -> list[list[float]]:
    if len(points) <= max_points:
        return [[x, y, t] for x, y, t in points]
    stride = max(1, len(points) // max_points)
    sampled = points[::stride]
    if sampled[-1] != points[-1]:
        sampled.append(points[-1])
    return [[x, y, t] for x, y, t in sampled]


def extract(bag: PromptBag) -> ExtractedParams:
    valid = [(frame.t, frame.cube_xy) for frame in bag.frames if frame.cube_xy is not None]
    if len(valid) < 2:
        raise ValueError("bag has fewer than two cube samples")

    t0 = valid[0][0]
    points = [(xy[0], xy[1], t - t0) for t, xy in valid]
    start = points[0][:2]
    end = points[-1][:2]
    path = _downsample(points)

    obstacle_frames = [frame.obstacle_xy for frame in bag.frames if frame.obstacle_xy is not None]
    obstacle_xy = obstacle_frames[len(obstacle_frames) // 2] if obstacle_frames else None

    dx = end[0] - start[0]
    dy = end[1] - start[1]
    distance = (dx * dx + dy * dy) ** 0.5
    motion = "pick_and_place" if distance < 0.04 else "replay_trajectory"

    return ExtractedParams(
        path=path,
        start=start,
        end=end,
        obstacle_xy=obstacle_xy,
        obstacle_label="water bottle" if obstacle_xy else "",
        motion=motion,
    )
