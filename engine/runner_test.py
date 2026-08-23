"""An `avoid` step has to move the arm, not just annotate the spec."""

import math

from engine.runner import Obstacle, Runner, _detour_control
from engine.spec import SkillSpec, _validate_step

OBSTACLE = {"op": "avoid", "at": [0.0, 0.0], "geom": "cylinder", "width_cm": 7,
            "height_cm": 20, "material": "plastic", "mesh_rung": 3}


def _spec(steps):
    """Build through the real validator so steps carry the fields the runner reads."""
    return SkillSpec(steps=tuple(_validate_step(step, i) for i, step in enumerate(steps)))


def _run(spec, until=3.0, dt=0.02):
    runner = Runner(spec)
    points, t = [], 0.0
    while t <= until:
        setpoint = runner.tick(t)
        if setpoint is None:
            break
        points.append((setpoint.x, setpoint.y))
        t += dt
    return points


def _closest(points, x=0.0, y=0.0):
    return min(math.hypot(px - x, py - y) for px, py in points)


STRAIGHT_THROUGH = [{"op": "goto", "start": [-0.3, 0.0], "end": [0.3, 0.0], "duration_s": 1.0}]


def test_without_an_avoid_step_the_path_is_straight_through() -> None:
    points = _run(_spec(STRAIGHT_THROUGH))
    assert _closest(points) < 0.01, "no obstacle declared, so nothing should bend"


def test_an_avoid_step_bends_the_path_clear_of_the_cylinder() -> None:
    points = _run(_spec([*STRAIGHT_THROUGH, OBSTACLE]))
    keep_out = Obstacle(0.0, 0.0, 0.035).keep_out_m
    assert _closest(points) > keep_out * 0.8, (
        f"arm passed {_closest(points):.3f} m from a {keep_out:.3f} m keep-out"
    )


def test_the_detour_still_arrives_where_it_was_going() -> None:
    points = _run(_spec([*STRAIGHT_THROUGH, OBSTACLE]))
    assert math.hypot(points[-1][0] - 0.3, points[-1][1]) < 0.01


def test_a_path_that_already_clears_the_obstacle_is_left_alone() -> None:
    assert _detour_control((-0.3, 0.5), (0.3, 0.5), [Obstacle(0.0, 0.0, 0.035)]) is None


def test_a_dead_on_approach_still_picks_a_side() -> None:
    """Centre exactly on the segment: there is no near side, so use the normal."""
    control = _detour_control((-0.3, 0.0), (0.3, 0.0), [Obstacle(0.0, 0.0, 0.035)])
    assert control is not None and abs(control[1]) > 0.05


def test_a_replayed_trajectory_is_never_bent() -> None:
    """Replay is what the operator actually did; the runner must not edit it."""
    spec = _spec([
        {"op": "replay_trajectory", "path": [[-0.3, 0.0, 0.0], [0.0, 0.0, 0.5], [0.3, 0.0, 1.0]]},
        OBSTACLE,
    ])
    assert _closest(_run(spec)) < 0.01


def main() -> None:
    for name, case in sorted(globals().items()):
        if name.startswith("test_") and callable(case):
            case()


if __name__ == "__main__":
    main()
    print("runner avoidance: PASS")
