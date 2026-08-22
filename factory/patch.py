"""Patch the hot-swapped skill spec from extracted params."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from factory.extract import ExtractedParams


def build_steps(params: ExtractedParams, catalog: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    if params.motion == "pick_and_place":
        steps.extend(
            [
                {"op": "approach", "at": list(params.start), "height_cm": 8, "duration_s": 0.8},
                {"op": "grasp"},
                {"op": "place", "at": [params.end[0], params.end[1], 0], "duration_s": 1.2},
                {"op": "release"},
            ]
        )
    elif params.motion == "replay_trajectory":
        steps.append({"op": "replay_trajectory", "path": params.path})
    else:
        steps.append(
            {
                "op": "goto",
                "start": list(params.start),
                "end": list(params.end),
                "duration_s": max(params.path[-1][2], 0.1),
            }
        )

    if params.obstacle_xy and catalog:
        steps.append(
            {
                "op": "avoid",
                "at": list(params.obstacle_xy),
                "geom": "cylinder",
                "width_cm": catalog.get("width_cm", 7),
                "height_cm": catalog.get("height_cm", 20),
                "material": catalog.get("material", "plastic"),
                **({"weight_g": catalog["weight_g"]} if catalog.get("weight_g") else {}),
            }
        )
    return steps


def patch_spec(
    params: ExtractedParams,
    spec_path: Path,
    catalog: dict[str, Any] | None = None,
    *,
    append: bool = False,
) -> dict[str, Any]:
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    existing_steps: list[dict[str, Any]] = []
    if append and spec_path.exists():
        try:
            raw = json.loads(spec_path.read_text())
            if isinstance(raw, dict) and isinstance(raw.get("steps"), list):
                existing_steps = list(raw["steps"])
        except json.JSONDecodeError:
            existing_steps = []

    if append and existing_steps:
        if not (params.obstacle_xy and catalog):
            return {"version": 2, "steps": existing_steps}
        avoid_step = {
            "op": "avoid",
            "at": list(params.obstacle_xy),
            "geom": "cylinder",
            "width_cm": catalog.get("width_cm", 7),
            "height_cm": catalog.get("height_cm", 20),
            "material": catalog.get("material", "plastic"),
            **({"weight_g": catalog["weight_g"]} if catalog.get("weight_g") else {}),
        }
        if any(
            step.get("op") == "avoid" and step.get("at") == avoid_step["at"]
            for step in existing_steps
        ):
            return {"version": 2, "steps": existing_steps}
        spec = {"version": 2, "steps": existing_steps + [avoid_step]}
        spec_path.write_text(json.dumps(spec, indent=2) + "\n")
        return spec

    new_steps = build_steps(params, catalog)
    spec = {"version": 2, "steps": existing_steps + new_steps if append else new_steps}
    spec_path.write_text(json.dumps(spec, indent=2) + "\n")
    return spec
