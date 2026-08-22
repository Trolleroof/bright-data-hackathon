"""A deterministic state machine: call ``tick(sim_time)`` once per sim frame."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from engine.spec import SkillSpec, load


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
        x = start[0] + (end[0] - start[0]) * progress
        y = start[1] + (end[1] - start[1]) * progress
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
