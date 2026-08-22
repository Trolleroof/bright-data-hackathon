"""Run the fast-path factory on a saved prompt bag."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from factory.fast_path import run_fast_path, smoke_from_synthetic_bag


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bag", type=Path, nargs="?", help="recordings/bag_*.json")
    parser.add_argument("--spec", type=Path, default=ROOT / "outputs" / "skill_spec.json")
    parser.add_argument("--append", action="store_true", help="append avoid step to existing spec")
    parser.add_argument("--smoke", action="store_true", help="run synthetic bag offline")
    parser.add_argument("--label", type=str, default="", help="Bright Data search label override")
    args = parser.parse_args()

    if args.smoke:
        result = smoke_from_synthetic_bag()
    else:
        if args.bag is None:
            parser.error("bag path required unless --smoke")
        result = run_fast_path(
            args.bag,
            args.spec,
            scrape_label=args.label or None,
            append=args.append,
        )

    print(f"bag:     {result.bag_path}")
    print(f"spec:    {result.spec_path}")
    print(f"motion:  {result.extracted.motion}")
    print(f"steps:   {result.replay.steps_completed} completed")
    print(f"replay:  {result.replay.detail} (max_error_cm={result.replay.max_error_cm})")
    print(f"elapsed: {result.elapsed_ms} ms")
    if result.catalog:
        print(
            f"scrape:  source={result.catalog.get('source')} "
            f"{result.catalog.get('width_cm')}x{result.catalog.get('height_cm')} cm"
        )
    return 0 if result.replay.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
