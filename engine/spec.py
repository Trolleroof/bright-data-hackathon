"""Load the small, fixed JSON language used by the skill engine."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class SpecError(ValueError):
    """A skill spec cannot be safely executed."""


@dataclass(frozen=True)
class SkillSpec:
    steps: tuple[dict[str, Any], ...]


def _point(value: Any, name: str) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2 or not all(isinstance(n, (int, float)) for n in value):
        raise SpecError(f"{name} must be [x, y]")
    return float(value[0]), float(value[1])


def _point3(value: Any, name: str) -> tuple[float, float, float]:
    if not isinstance(value, list) or len(value) != 3 or not all(isinstance(n, (int, float)) for n in value):
        raise SpecError(f"{name} must be [x, y, z]")
    return float(value[0]), float(value[1]), float(value[2])


def _duration(step: dict[str, Any], index: int) -> float:
    duration = step.get("duration_s", 1.0)
    if not isinstance(duration, (int, float)) or duration <= 0:
        raise SpecError(f"steps[{index}].duration_s must be positive")
    return float(duration)


def _validate_step(step: Any, index: int) -> dict[str, Any]:
    if not isinstance(step, dict):
        raise SpecError(f"steps[{index}] must be an object")
    op = step.get("op")
    if op == "replay_trajectory":
        path = step.get("path")
        if not isinstance(path, list) or len(path) < 2:
            raise SpecError(f"steps[{index}].path must contain at least two [x, y, t] points")
        points: list[tuple[float, float, float]] = []
        for point_index, point in enumerate(path):
            if not isinstance(point, list) or len(point) != 3 or not all(isinstance(n, (int, float)) for n in point):
                raise SpecError(f"steps[{index}].path[{point_index}] must be [x, y, t]")
            points.append((float(point[0]), float(point[1]), float(point[2])))
        if points[0][2] != 0 or any(b[2] <= a[2] for a, b in zip(points, points[1:])):
            raise SpecError(f"steps[{index}].path must start at t=0 with strictly increasing times")
        return {"op": op, "path": points}
    if op == "goto":
        start = _point(step.get("start"), f"steps[{index}].start")
        end = _point(step.get("end"), f"steps[{index}].end")
        return {"op": op, "start": start, "end": end, "duration_s": _duration(step, index)}
    if op == "approach":
        height_cm = step.get("height_cm")
        if not isinstance(height_cm, (int, float)) or height_cm <= 0:
            raise SpecError(f"steps[{index}].height_cm must be positive")
        return {"op": op, "at": _point(step.get("at"), f"steps[{index}].at"), "z": float(height_cm) / 100, "duration_s": _duration(step, index)}
    if op == "place":
        return {"op": op, "at": _point3(step.get("at"), f"steps[{index}].at"), "duration_s": _duration(step, index)}
    if op in {"grasp", "release"}:
        if set(step) != {"op"}:
            raise SpecError(f"steps[{index}].{op} takes no parameters")
        return {"op": op}
    if op == "avoid":
        geom = step.get("geom", "cylinder")
        if geom not in {"cylinder", "box"}:
            raise SpecError(f"steps[{index}].geom must be cylinder or box")
        width_cm, height_cm = step.get("width_cm"), step.get("height_cm")
        if not isinstance(width_cm, (int, float)) or width_cm <= 0 or not isinstance(height_cm, (int, float)) or height_cm <= 0:
            raise SpecError(f"steps[{index}].width_cm and height_cm must be positive")
        return {"op": op, "at": _point(step.get("at"), f"steps[{index}].at"), "geom": geom, "width_m": float(width_cm) / 100, "height_m": float(height_cm) / 100}
    raise SpecError(f"steps[{index}].op must be replay_trajectory or goto")


def load(path: str | Path) -> SkillSpec:
    """Read and validate a version-2 skill file."""
    source = Path(path)
    try:
        raw = json.loads(source.read_text())
    except OSError as exc:
        raise SpecError(f"cannot read {source}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SpecError(f"invalid JSON in {source}: {exc.msg}") from exc
    if not isinstance(raw, dict) or raw.get("version") != 2:
        raise SpecError("spec version must be 2")
    steps = raw.get("steps")
    if not isinstance(steps, list) or not steps:
        raise SpecError("spec must contain a non-empty steps array")
    return SkillSpec(tuple(_validate_step(step, index) for index, step in enumerate(steps)))
