"""Skill A must not call Bright Data, even if the bag saw a not-red blob."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from factory.fast_path import run_fast_path
from vision.bag import BagFrame, PromptBag, save_bag


def _bag_with_obstacle(path: Path) -> Path:
    bag = PromptBag(
        frames=[
            BagFrame(t=0.0, cube_xy=(0.0, 0.0), obstacle_xy=(-0.1, 0.05), tag_seen=True),
            BagFrame(t=1.0, cube_xy=(0.05, 0.02), obstacle_xy=(-0.1, 0.05), tag_seen=True),
            BagFrame(t=2.0, cube_xy=(0.12, 0.08), obstacle_xy=(-0.1, 0.05), tag_seen=True),
        ],
        started_at="test",
        duration_s=2.0,
        bag_id="bag_skill_a",
    )
    return save_bag(bag, path)


def main() -> None:
    with TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        bag_path = _bag_with_obstacle(tmp_path / "bag.json")
        spec_a = tmp_path / "skill_a.json"
        spec_b = tmp_path / "skill_b.json"

        with (
            patch("factory.fast_path.lookup") as lookup,
            patch("factory.fast_path.acquire") as acquire,
        ):
            result_a = run_fast_path(bag_path, spec_a)
            lookup.assert_not_called()
            acquire.assert_not_called()
            assert result_a.catalog is None
            assert result_a.mesh is None
            assert all(step["op"] != "avoid" for step in __import__("json").loads(spec_a.read_text())["steps"])

            lookup.return_value = {
                "name": "IKEA 365+ water bottle",
                "width_cm": 7.0,
                "height_cm": 20.0,
                "source": "live",
                "url": "https://example.test/bottle",
                "latency_ms": 1.0,
            }
            acquire.return_value = type("Mesh", (), {"asset": None, "rung": 3, "label": "rung 3", "reasons": []})()
            result_b = run_fast_path(bag_path, spec_b, append=True)
            lookup.assert_called_once()
            assert result_b.catalog is not None

    print("fast_path skill A skips scrape: PASS")


if __name__ == "__main__":
    main()
