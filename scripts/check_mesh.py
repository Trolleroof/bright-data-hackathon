"""Prove the geometry ladder without a camera, a stage, or (by default) a network.

Offline it fabricates the exact pathology a downloaded mesh has — unit-less,
Y-up, off-origin, high-poly — fits it to the scraped dimensions, compiles the
twin scene around it, and reports what changed. ``--live`` runs the real thing:
Bright Data search across the 3D-asset web, download, fit, hot-swap file.

  python scripts/check_mesh.py            # offline, no keys needed
  python scripts/check_mesh.py --live --label "water bottle"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mujoco

from factory.mesh_fit import fit, load_asset, save_asset
from factory.mesh_ladder import acquire
from integrations.brightdata import load_fixture, lookup
from integrations.config import load_settings
from twin.world import build_scene, rung_label

SCRATCH = ROOT / "outputs" / "meshes" / "check"


def _synthetic_download() -> Path:
    """A cylinder that is 2.0 units tall, lying on its side, centred nowhere.

    That is what the 3D web actually hands you: shape with no units, no agreed
    up axis, and an origin wherever the modeller left it.
    """
    import numpy as np
    import trimesh

    mesh = trimesh.creation.cylinder(radius=0.35, height=2.0, sections=180)
    mesh.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    mesh.apply_translation([12.0, -4.0, 3.0])
    SCRATCH.mkdir(parents=True, exist_ok=True)
    path = SCRATCH / "downloaded.stl"
    mesh.export(path)
    return path


def offline() -> int:
    catalog = load_fixture()
    raw = _synthetic_download()
    asset = fit(
        raw,
        height_cm=float(catalog["height_cm"]),
        width_cm=float(catalog["width_cm"]),
        weight_g=float(catalog["weight_g"]),
        rung=2,
        source="synthetic",
        asset_url="file://" + str(raw),
        out_dir=SCRATCH,
    )
    print(f"downloaded : {raw.name} (unit-less, Y-up, off-origin)")
    print(f"scaled by  : {asset.scale:.5f}  ->  {asset.height_cm} cm tall")
    print(f"width       : mesh {asset.measured_width_cm} cm vs scraped {asset.width_cm} cm "
          f"(residual {asset.width_residual_cm:+.2f} cm)")
    print(f"triangles   : visual {asset.faces_visual}  collision {asset.faces_collision}")
    print(f"density     : {asset.density_kg_m3} kg/m3 from {asset.density_source}")

    payload = save_asset(asset, path=SCRATCH / "mesh_asset.json", extra={"scale_source": "scrape"})
    scene = build_scene(payload, out_path=ROOT / "twin" / "scene_check.xml")
    try:
        model = mujoco.MjModel.from_xml_path(str(scene))
        geom = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "obstacle_geom")
        body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "obstacle")
        if geom < 0 or int(model.geom_type[geom]) != int(mujoco.mjtGeom.mjGEOM_MESH):
            raise RuntimeError("obstacle_geom did not become a mesh")
        print(f"scene       : compiled, obstacle mass {model.body_mass[body] * 1000:.1f} g")
    finally:
        scene.unlink(missing_ok=True)

    print(f"rung        : {rung_label(payload)}")
    return 0


def live(label: str) -> int:
    settings = load_settings()
    if not settings.brightdata_ready:
        print("live mode needs BRIGHTDATA_API_TOKEN + zones in .env")
        return 1
    catalog = lookup(label, settings)
    print(f"scrape      : source={catalog.get('source')} {catalog.get('name')!r} "
          f"{catalog.get('width_cm')}x{catalog.get('height_cm')} cm")
    result = acquire(label, catalog, settings=settings)
    for attempt in result.attempts:
        print(f"  attempt   : {attempt}")
    print(f"rung        : {result.label}")
    for reason in result.reasons:
        print(f"  reason    : {reason}")
    if result.asset:
        print(f"visual      : {result.asset['visual_path']}")
        print(f"collision   : {result.asset['collision_path']} "
              f"({result.asset['faces_collision']} faces)")
        print(f"density     : {result.asset['density_kg_m3']} kg/m3 "
              f"from {result.asset['density_source']}")
        print("the running web twin picks this up within a second")
    return 0 if result.rung < 3 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="really search and download")
    parser.add_argument("--label", default="water bottle")
    args = parser.parse_args()
    print(f"current asset on disk: {rung_label(load_asset())}")
    return live(args.label) if args.live else offline()


if __name__ == "__main__":
    raise SystemExit(main())
