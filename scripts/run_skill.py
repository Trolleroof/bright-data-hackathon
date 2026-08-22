"""Run a skill spec without a camera or viewer."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.runner import Runner
from engine.spec import SpecError, load
from integrations.signoz import record_event, span


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=ROOT / "outputs" / "skill_spec.json")
    parser.add_argument("--dt", type=float, default=0.02, help="simulated seconds per frame")
    args = parser.parse_args()
    if args.dt <= 0:
        parser.error("--dt must be positive")
    try:
        loaded_spec = load(args.spec)
        runner = Runner(loaded_spec, args.spec)
    except SpecError as exc:
        print(f"skill spec rejected: {exc}", file=sys.stderr)
        return 1

    sim_time = 0.0
    last = None
    step_count = len(loaded_spec.steps)

    with span(
        "skill_exec",
        spec_path=str(args.spec),
        steps_total=step_count,
        dt=args.dt,
        engine="runner",
    ):
        while not runner.finished:
            setpoint = runner.tick(sim_time)
            if setpoint is not None:
                last = setpoint
                if setpoint.done:
                    print(f"{setpoint.op}: x={setpoint.x:+.3f} y={setpoint.y:+.3f} z={setpoint.z:+.3f} complete")
            if runner.reload_if_changed():
                print("skill spec reloaded")
                record_event(
                    "release",
                    hot_swap=True,
                    zero_downtime=True,
                    spec_version=getattr(loaded_spec, "version", 2),
                    spec_path=str(args.spec),
                )
            sim_time += args.dt

        assert last is not None and last.done, "runner did not finish its final step"
        print(f"skill complete in {sim_time:.2f}s")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
