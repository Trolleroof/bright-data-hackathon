"""Replay bag exam: run the spec in sim-time without MuJoCo."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.runner import Runner
from engine.spec import SpecError, load


@dataclass(frozen=True)
class ReplayResult:
    passed: bool
    steps_completed: int
    duration_s: float
    max_error_cm: float
    detail: str


def replay_test(spec_path: Path, *, dt: float = 0.02) -> ReplayResult:
    try:
        runner = Runner(load(spec_path), spec_path)
    except SpecError as exc:
        return ReplayResult(False, 0, 0.0, 0.0, f"spec rejected: {exc}")

    sim_time = 0.0
    last_xy = (0.0, 0.0)
    max_error_m = 0.0
    steps_done = 0
    guard = 0
    while not runner.finished and guard < 100_000:
        setpoint = runner.tick(sim_time)
        if setpoint is not None:
            err = ((setpoint.x - last_xy[0]) ** 2 + (setpoint.y - last_xy[1]) ** 2) ** 0.5
            max_error_m = max(max_error_m, err)
            last_xy = (setpoint.x, setpoint.y)
            if setpoint.done:
                steps_done += 1
        sim_time += dt
        guard += 1

    passed = runner.finished and steps_done == len(runner.spec.steps)
    return ReplayResult(
        passed=passed,
        steps_completed=steps_done,
        duration_s=sim_time,
        max_error_cm=round(max_error_m * 100, 2),
        detail="PASS" if passed else "FAIL",
    )


def replay_test_dict(spec: dict[str, Any], *, dt: float = 0.02) -> ReplayResult:
    path = Path("outputs/_replay_tmp.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(__import__("json").dumps(spec, indent=2))
    try:
        return replay_test(path, dt=dt)
    finally:
        if path.exists():
            path.unlink()
