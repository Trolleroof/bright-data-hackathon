"""Patch the hot-swapped skill spec from extracted params."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from factory.extract import ExtractedParams


def avoid_step(
    params: ExtractedParams,
    catalog: dict[str, Any],
    mesh: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The obstacle, fused from all three sources.

    Camera: where it is. Scrape: how big and how heavy. Mesh ladder: what shape
    — and when that came up empty, ``geom`` stays a cylinder and the rung says
    so, which is the labelled degradation, not a hidden one.
    """
    step: dict[str, Any] = {
        "op": "avoid",
        "at": list(params.obstacle_xy),
        "geom": "mesh" if mesh else "cylinder",
        "width_cm": catalog.get("width_cm", 7),
        "height_cm": catalog.get("height_cm", 20),
        "material": catalog.get("material", "plastic"),
        "mesh_rung": int(mesh["rung"]) if mesh else 3,
    }
    if catalog.get("weight_g"):
        step["weight_g"] = catalog["weight_g"]
    if mesh:
        step["density_kg_m3"] = float(mesh["density_kg_m3"])
        step["mesh_source"] = str(mesh.get("source", "web"))
    return step


def build_steps(
    params: ExtractedParams,
    catalog: dict[str, Any] | None = None,
    mesh: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
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
        steps.append(avoid_step(params, catalog, mesh))
    return steps


def patch_spec(
    params: ExtractedParams,
    spec_path: Path,
    catalog: dict[str, Any] | None = None,
    *,
    append: bool = False,
    mesh: dict[str, Any] | None = None,
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
        new_avoid = avoid_step(params, catalog, mesh)
        if any(
            step.get("op") == "avoid" and step.get("at") == new_avoid["at"]
            for step in existing_steps
        ):
            return {"version": 2, "steps": existing_steps}
        spec = {"version": 2, "steps": existing_steps + [new_avoid]}
        spec_path.write_text(json.dumps(spec, indent=2) + "\n")
        return spec

    new_steps = build_steps(params, catalog, mesh)
    spec = {"version": 2, "steps": existing_steps + new_steps if append else new_steps}
    spec_path.write_text(json.dumps(spec, indent=2) + "\n")
    return spec
