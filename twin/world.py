"""Build the scene the twin actually loads: primitive obstacle, or a real mesh.

``twin/scene.xml`` is the rung-3 world — the blue cylinder sized from scraped
dimensions. When the mesh ladder has produced an asset
(``outputs/mesh_asset.json``), this module rewrites the obstacle body to use
that mesh instead and writes the result next to ``scene.xml`` so the relative
``<include>`` of the SO-101 model still resolves.

MuJoCo compiles meshes in, so a mesh cannot be attached to a live model. The
swap therefore happens by rebuilding the model and carrying ``qpos``/``qvel``
across — see ``LiveTwin._swap_world``. From the outside that is still one
uninterrupted twin, which is the whole point of the release story.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

SCENE = Path(__file__).with_name("scene.xml")
GENERATED = Path(__file__).with_name("scene_generated.xml")

_OBSTACLE_BODY = re.compile(r'<body name="obstacle".*?</body>', re.DOTALL)
_ASSET_CLOSE = "</asset>"

RUNG_LABELS = {
    1: "product AR mesh",
    2: "web 3D mesh",
    3: "primitive cylinder",
}


def rung_label(asset: dict[str, Any] | None) -> str:
    rung = int(asset["rung"]) if asset else 3
    return f"rung {rung}: {RUNG_LABELS.get(rung, 'unknown')}"


def _mesh_assets_xml(asset: dict[str, Any]) -> str:
    return (
        f'    <mesh name="obstacle_visual_mesh" file="{asset["visual_path"]}"/>\n'
        f'    <mesh name="obstacle_collision_mesh" file="{asset["collision_path"]}"/>\n'
        f"  {_ASSET_CLOSE}"
    )


def _mesh_body_xml(asset: dict[str, Any]) -> str:
    """Collision uses the decimated copy; the high-poly one is visual-only.

    Density comes from the scraped mass over the rescaled mesh volume, so the
    obstacle weighs what the real object weighs even though nobody typed a mass.
    """
    density = float(asset.get("density_kg_m3", 950.0))
    return (
        '<body name="obstacle" pos="0 0 0.88">\n'
        '      <freejoint name="obstacle_free"/>\n'
        f'      <geom name="obstacle_geom" type="mesh" mesh="obstacle_collision_mesh"\n'
        f'            density="{density}" group="3" rgba="0.15 0.55 0.95 0.35"/>\n'
        '      <geom name="obstacle_visual" type="mesh" mesh="obstacle_visual_mesh"\n'
        '            contype="0" conaffinity="0" mass="0" material="obstacle"/>\n'
        "    </body>"
    )


def build_scene(asset: dict[str, Any] | None, out_path: Path | None = None) -> Path:
    """Return the scene file to load. No asset means the untouched primitive scene."""
    if not asset:
        return SCENE
    xml = SCENE.read_text()
    xml = xml.replace(_ASSET_CLOSE, _mesh_assets_xml(asset), 1)
    xml, count = _OBSTACLE_BODY.subn(_mesh_body_xml(asset), xml, count=1)
    if count != 1:
        return SCENE
    out_path = out_path or GENERATED
    out_path.write_text(xml)
    return out_path
