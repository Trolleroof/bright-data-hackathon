"""Build the scene the twin actually loads: primitive obstacle, or a real mesh.

``twin/scene.xml`` is the rung-3 world — the blue cylinder sized from scraped
dimensions. When the mesh ladder has produced an asset
(``outputs/mesh_asset.json``), this module rewrites the obstacle body to use
that mesh instead and writes the result next to ``scene.xml`` so the relative
``<include>`` of the SO-101 model still resolves.

MuJoCo compiles meshes in, so a mesh cannot be attached to a live model. The
swap therefore happens by rebuilding the model and carrying ``qpos``/``qvel``
across — see ``LiveTwin._build_world``. From the outside that is still one
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


def is_primitive(asset: dict[str, Any] | None) -> bool:
    return bool(asset) and asset.get("kind") == "primitive"


def rung_label(asset: dict[str, Any] | None) -> str:
    rung = int(asset["rung"]) if asset else 3
    if is_primitive(asset):
        # Still rung 3, but say *which* primitive: an imported stub sized from a
        # catalogue is not the same thing as the stock obstacle in scene.xml.
        label = str(asset.get("label") or "object")
        return f"rung 3: primitive {asset.get('shape', 'cylinder')} ({label})"
    return f"rung {rung}: {RUNG_LABELS.get(rung, 'unknown')}"


def _mesh_assets_xml(asset: dict[str, Any]) -> str:
    return (
        f'    <mesh name="obstacle_visual_mesh" file="{asset["visual_path"]}"/>\n'
        f'    <mesh name="obstacle_collision_mesh" file="{asset["collision_path"]}"/>\n'
        f"  {_ASSET_CLOSE}"
    )


def _primitive_body_xml(asset: dict[str, Any]) -> str:
    """A sized, coloured primitive — the hardcoded grey-bottle import lands here.

    No <asset> entry is needed: MuJoCo primitives carry their own geometry, so
    the swap is a body rewrite and nothing else.
    """
    radius = float(asset.get("radius_m", 0.035))
    half_height = float(asset.get("half_height_m", 0.12))
    density = float(asset.get("density_kg_m3", 950.0))
    r, g, b, a = (list(asset.get("rgba", [0.42, 0.44, 0.47, 1.0])) + [1.0])[:4]
    shape = "box" if str(asset.get("shape")) == "box" else "cylinder"
    size = (
        f"{radius} {radius} {half_height}" if shape == "box" else f"{radius} {half_height}"
    )
    return (
        f'<body name="obstacle" pos="0 0 {round(0.761 + half_height, 4)}">\n'
        '      <freejoint name="obstacle_free"/>\n'
        f'      <geom name="obstacle_geom" type="{shape}" size="{size}"\n'
        f'            density="{density}" rgba="{r} {g} {b} {a}"/>\n'
        "    </body>"
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


class SceneBuildError(RuntimeError):
    """scene.xml could not be rewritten to carry the mesh."""


def build_scene(asset: dict[str, Any] | None, out_path: Path | None = None) -> Path:
    """Return the scene file to load. No asset means the untouched primitive scene.

    Raises SceneBuildError if the obstacle body cannot be rewritten — silently
    returning the primitive here would leave the HUD reporting a mesh rung the
    twin is not actually running. Callers that want the primitive instead
    should use ``resolve_scene``.
    """
    if not asset:
        return SCENE
    xml = SCENE.read_text()
    if is_primitive(asset):
        body = _primitive_body_xml(asset)
    else:
        xml = xml.replace(_ASSET_CLOSE, _mesh_assets_xml(asset), 1)
        body = _mesh_body_xml(asset)
    xml, count = _OBSTACLE_BODY.subn(body, xml, count=1)
    if count != 1:
        raise SceneBuildError(f'no <body name="obstacle"> to replace in {SCENE.name}')
    out_path = out_path or GENERATED
    out_path.write_text(xml)
    return out_path


def resolve_scene(
    asset: dict[str, Any] | None, out_path: Path | None = None
) -> tuple[Path, dict[str, Any] | None]:
    """Scene to load plus the asset it really uses — None when we fell to rung 3.

    Pair the returned asset with ``rung_label`` so what the HUD shows and what
    MuJoCo compiled can never disagree.
    """
    try:
        return build_scene(asset, out_path), asset
    except (SceneBuildError, OSError):
        return SCENE, None
