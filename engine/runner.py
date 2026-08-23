"""A deterministic state machine: call ``tick(sim_time)`` once per sim frame.

An ``avoid`` step used to only *declare* an obstacle — the twin drew it and the
arm interpolated straight through it. Here it also bends the motion: any
``goto``, ``place`` or ``approach`` whose straight line would clip the obstacle
is routed around it on a curve. The detour is geometric and deterministic, so
the same spec produces the same path every run and the replay exam stays
meaningful.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from engine.spec import SkillSpec, load

# How much room to leave around an obstacle, beyond its own radius. The gripper
# is not a point, and a path that grazes the cylinder reads as a collision even
# when the numbers say it cleared.
_CLEARANCE_M = 0.06


@dataclass(frozen=True)
class Obstacle:
    """Where an ``avoid`` step says something is, and how wide a berth it needs."""

    x: float
    y: float
    radius_m: float

    @property
    def keep_out_m(self) -> float:
        return self.radius_m + _CLEARANCE_M


def _obstacles(spec: SkillSpec) -> list[Obstacle]:
    found: list[Obstacle] = []
    for step in spec.steps:
        if step.get("op") != "avoid":
            continue
        at = step.get("at") or []
        if len(at) < 2:
            continue
        width_cm = float(step.get("width_cm") or 7.0)
        found.append(Obstacle(float(at[0]), float(at[1]), max(width_cm, 1.0) / 200.0))
    return found


def _detour_control(
    start: tuple[float, ...], end: tuple[float, ...], obstacles: list[Obstacle]
) -> tuple[float, float] | None:
    """A control point that pulls the path clear, or None if it already is.

    The straight segment is tested against each obstacle; the first one it
    clips decides which way to bend. Pushing the control point out along the
    normal from the obstacle to the segment sends the curve around the near
    side, which is the shorter way and the one that looks deliberate.
    """
    sx, sy, ex, ey = start[0], start[1], end[0], end[1]
    dx, dy = ex - sx, ey - sy
    span = math.hypot(dx, dy)
    if span < 1e-6:
        return None

    for obstacle in obstacles:
        # Closest point on the segment to the obstacle centre.
        t = ((obstacle.x - sx) * dx + (obstacle.y - sy) * dy) / (span * span)
        t = min(max(t, 0.0), 1.0)
        cx, cy = sx + dx * t, sy + dy * t
        offset_x, offset_y = cx - obstacle.x, cy - obstacle.y
        distance = math.hypot(offset_x, offset_y)
        if distance >= obstacle.keep_out_m:
            continue
        if distance < 1e-6:
            # Dead-on: no near side to pick, so bend along the segment normal.
            offset_x, offset_y = -dy / span, dx / span
        else:
            offset_x, offset_y = offset_x / distance, offset_y / distance
        # A quadratic Bezier sits halfway between its control point and the
        # chord, so the control point goes twice as far out as the curve needs.
        reach = obstacle.keep_out_m * 2.0
        return obstacle.x + offset_x * reach, obstacle.y + offset_y * reach
    return None


def _bend(
    start: tuple[float, ...], end: tuple[float, ...], progress: float,
    control: tuple[float, float] | None,
) -> tuple[float, float]:
    """Straight lerp, or a quadratic Bezier through ``control``."""
    if control is None:
        return (
            start[0] + (end[0] - start[0]) * progress,
            start[1] + (end[1] - start[1]) * progress,
        )
    inverse = 1.0 - progress
    a, b, c = inverse * inverse, 2.0 * inverse * progress, progress * progress
    return (
        a * start[0] + b * control[0] + c * end[0],
        a * start[1] + b * control[1] + c * end[1],
    )


@dataclass(frozen=True)
class Setpoint:
    op: str
    x: float
    y: float
    z: float
    done: bool
    attached: bool = False
    released: bool = False
    obstacle: dict[str, object] | None = None


class Runner:
    def __init__(self, spec: SkillSpec, spec_path: str | Path | None = None) -> None:
        self.spec = spec
        self._spec_path = Path(spec_path) if spec_path is not None else None
        self._mtime_ns = self._spec_path.stat().st_mtime_ns if self._spec_path is not None else None
        self._index = 0
        self._started_at: float | None = None
        self._finished = False
        self._position = (0.0, 0.0, 0.0)
        self._attached = False
        self._obstacles = _obstacles(spec)

    @property
    def at_step_boundary(self) -> bool:
        return self._started_at is None

    @property
    def finished(self) -> bool:
        return self._finished

    def replace(self, spec: SkillSpec) -> None:
        """Install a changed spec only between steps."""
        if not self.at_step_boundary:
            raise RuntimeError("specs can only be replaced between steps")
        self.spec = spec
        self._index = 0
        self._finished = False
        self._position = (0.0, 0.0, 0.0)
        self._attached = False
        self._obstacles = _obstacles(spec)

    def reload_if_changed(self) -> bool:
        """Reload a watched JSON file at a step boundary; return whether it changed."""
        if self._spec_path is None:
            return False
        mtime_ns = self._spec_path.stat().st_mtime_ns
        if mtime_ns == self._mtime_ns or not self.at_step_boundary:
            return False
        self.replace(load(self._spec_path))
        self._mtime_ns = mtime_ns
        return True

    def tick(self, sim_time: float) -> Setpoint | None:
        if self._finished:
            return None
        if self._started_at is None:
            self._started_at = sim_time
        step = self.spec.steps[self._index]
        elapsed = max(0.0, sim_time - self._started_at)
        released = False
        obstacle = None
        if step["op"] == "goto":
            start, end, duration = step["start"], step["end"], step["duration_s"]
            progress = min(1.0, elapsed / duration)
            start = (*start, 0.0)
            end = (*end, 0.0)
        elif step["op"] == "replay_trajectory":
            path = step["path"]
            progress, start, end, duration = _path_segment(path, elapsed)
            start, end = (*start, 0.0), (*end, 0.0)
        elif step["op"] in {"approach", "place"}:
            start = self._position
            end = (*step["at"], step["z"]) if step["op"] == "approach" else step["at"]
            duration = step["duration_s"]
            progress = min(1.0, elapsed / duration)
        elif step["op"] == "grasp":
            self._attached = True
            start = end = self._position
            duration = step["duration_s"]
            progress = min(1.0, elapsed / duration)
        elif step["op"] == "release":
            released = self._attached
            self._attached = False
            start = end = self._position
            duration = 0.0
            progress = 1.0
        else:  # avoid
            start = end = self._position
            duration = 0.0
            progress = 1.0
            obstacle = {
                key: step[key]
                for key in (
                    "at", "geom", "width_m", "height_m", "material", "density_kg_m3",
                    "friction", "mass_kg", "mass_defaulted", "mesh_rung", "mesh_source",
                )
            }
        # Bending only applies to motion; a grasp or an avoid holds position,
        # and a recorded trajectory is what the operator actually did.
        control = (
            _detour_control(start, end, self._obstacles)
            if self._obstacles and step["op"] in {"goto", "approach", "place"}
            else None
        )
        x, y = _bend(start, end, progress, control)
        z = start[2] + (end[2] - start[2]) * progress
        done = progress == 1.0 and elapsed >= duration
        if done:
            self._position = (x, y, z)
            self._index += 1
            self._started_at = None
            self._finished = self._index == len(self.spec.steps)
        return Setpoint(step["op"], x, y, z, done, self._attached, released, obstacle)


def _path_segment(path: list[tuple[float, float, float]], elapsed: float) -> tuple[float, tuple[float, float], tuple[float, float], float]:
    if elapsed <= path[0][2]:
        return 0.0, path[0][:2], path[0][:2], path[-1][2]
    for start, end in zip(path, path[1:]):
        if elapsed <= end[2]:
            return (elapsed - start[2]) / (end[2] - start[2]), start[:2], end[:2], path[-1][2]
    return 1.0, path[-1][:2], path[-1][:2], path[-1][2]
