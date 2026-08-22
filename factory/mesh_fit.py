"""Turn a downloaded web mesh into a MuJoCo-usable geom.

A web mesh has shape and nothing else. It is unit-less (a "20 cm" bottle
arrives 1.0 units tall, or 200, depending on who exported it), it is centred
wherever the modeller's origin happened to be, it may be Y-up, and it is often
100k triangles of visual detail that a physics solver has no use for.

The other two sources fill exactly those gaps: the camera measured the real
size in centimetres, and the scrape read the mass and the material. So:

  recentre on the bounding box -> stand the long axis up -> rescale to the
  measured height -> decimate a collision copy -> density = scraped mass over
  the now-real volume.

Output is two STLs (visual, collision) plus a JSON record of what was done,
including the width residual: the camera measured a width, the mesh has its
own, and the gap between them is the honest error bar on the fusion.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from integrations.config import ROOT

MESH_DIR = ROOT / "outputs" / "meshes"
ASSET_PATH = ROOT / "outputs" / "mesh_asset.json"

# A density outside this range is a unit or volume bug, not a material.
_MIN_DENSITY = 50.0
_MAX_DENSITY = 20_000.0


class MeshFitError(RuntimeError):
    """The downloaded file is not a mesh we can put in a physics scene."""


@dataclass(frozen=True)
class MeshAsset:
    visual_path: str
    collision_path: str
    rung: int
    source: str
    asset_url: str
    page_url: str
    ext: str
    height_cm: float
    width_cm: float
    measured_width_cm: float
    width_residual_cm: float
    scale: float
    faces_visual: int
    faces_collision: int
    volume_cm3: float
    mass_g: float | None
    density_kg_m3: float
    density_source: str

    def as_json(self) -> dict[str, Any]:
        return asdict(self)


def _load_mesh(path: Path):
    import trimesh  # noqa: PLC0415 — heavy, and only the mesh rungs need it

    try:
        mesh = trimesh.load(path, force="mesh")
    except Exception as exc:  # noqa: BLE001 — every loader raises its own type
        raise MeshFitError(f"{path.name}: {exc}") from exc
    if getattr(mesh, "faces", None) is None or len(mesh.faces) == 0:
        raise MeshFitError(f"{path.name}: no triangles (scene or point cloud?)")
    mesh.remove_infinite_values()
    mesh.merge_vertices()
    return mesh


def _stand_up(mesh) -> None:
    """Rotate the longest extent onto +Z. Sources disagree on up; we do not."""
    import numpy as np  # noqa: PLC0415
    import trimesh  # noqa: PLC0415

    axis = int(np.argmax(mesh.extents))
    if axis == 2:
        return
    rotation_axis = [0, 1, 0] if axis == 0 else [1, 0, 0]
    mesh.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, rotation_axis))


def _decimate(mesh, target_faces: int):
    """A collision copy the solver can afford.

    Quadric decimation first, convex hull second. Both are optional installs
    (fast-simplification, scipy), so a missing one degrades to a fatter
    collision mesh rather than taking the rung down.
    """
    if len(mesh.faces) <= target_faces:
        return mesh.copy()
    for name in ("simplify_quadric_decimation", "simplify_quadratic_decimation"):
        simplify = getattr(mesh, name, None)
        if simplify is None:
            continue
        try:
            reduced = simplify(face_count=target_faces)
        except TypeError:
            try:
                reduced = simplify(target_faces)
            except Exception:  # noqa: BLE001 — fall through to the hull
                continue
        except Exception:  # noqa: BLE001 — fall through to the hull
            continue
        # trimesh returns the mesh untouched (no exception) when its optional
        # decimation backend is missing, so insist on an actual reduction.
        if reduced is not None and 0 < len(reduced.faces) < len(mesh.faces):
            return reduced
    try:
        return mesh.convex_hull
    except Exception:  # noqa: BLE001 — no scipy: ship the mesh as it came
        return mesh.copy()


def _density(mass_g: float | None, volume_m3: float, fallback: float) -> tuple[float, str]:
    if mass_g is None or volume_m3 <= 0:
        return fallback, "material"
    density = (mass_g / 1000.0) / volume_m3
    if not _MIN_DENSITY <= density <= _MAX_DENSITY:
        return fallback, "material (scraped mass gave an implausible density)"
    return round(density, 1), "scraped mass / mesh volume"


def fit(
    raw_path: Path,
    *,
    height_cm: float,
    width_cm: float,
    weight_g: float | None = None,
    fallback_density: float = 950.0,
    rung: int = 2,
    source: str = "web",
    asset_url: str = "",
    page_url: str = "",
    collision_faces: int = 400,
    out_dir: Path | None = None,
) -> MeshAsset:
    """Scale a raw web mesh to the size the camera measured and give it mass."""
    if height_cm <= 0:
        raise MeshFitError("height_cm must be positive; the camera/scrape supplies scale")
    out_dir = out_dir or MESH_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    mesh = _load_mesh(raw_path)
    _stand_up(mesh)
    mesh.apply_translation(-mesh.bounding_box.centroid)

    extent_z = float(mesh.extents[2])
    if extent_z <= 0:
        raise MeshFitError(f"{raw_path.name}: mesh is flat along its long axis")
    scale = (height_cm / 100.0) / extent_z
    mesh.apply_scale(scale)

    collision = _decimate(mesh, collision_faces)
    visual_path = out_dir / "obstacle_visual.stl"
    collision_path = out_dir / "obstacle_collision.stl"
    mesh.export(visual_path)
    collision.export(collision_path)

    volume_m3 = float(abs(mesh.volume))
    density, density_source = _density(weight_g, volume_m3, fallback_density)
    measured_width_cm = round(float(max(mesh.extents[0], mesh.extents[1])) * 100, 2)

    return MeshAsset(
        visual_path=str(visual_path),
        collision_path=str(collision_path),
        rung=rung,
        source=source,
        asset_url=asset_url,
        page_url=page_url,
        ext=raw_path.suffix.lower(),
        height_cm=round(float(height_cm), 2),
        width_cm=round(float(width_cm), 2),
        measured_width_cm=measured_width_cm,
        width_residual_cm=round(measured_width_cm - float(width_cm), 2),
        scale=round(scale, 6),
        faces_visual=int(len(mesh.faces)),
        faces_collision=int(len(collision.faces)),
        volume_cm3=round(volume_m3 * 1e6, 2),
        mass_g=float(weight_g) if weight_g else None,
        density_kg_m3=float(density),
        density_source=density_source,
    )


def save_asset(asset: MeshAsset, path: Path | None = None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Write the asset record the twin watches; returns exactly what was written."""
    path = path or ASSET_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {**asset.as_json(), **(extra or {})}
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return payload


def load_asset(path: Path | None = None) -> dict[str, Any] | None:
    """The current mesh asset, or None when the twin is on the primitive rung."""
    path = path or ASSET_PATH
    try:
        asset = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(asset, dict):
        return None
    for key in ("visual_path", "collision_path"):
        if not asset.get(key) or not Path(asset[key]).exists():
            return None
    return asset


def clear_asset(path: Path | None = None) -> None:
    """Drop back to the primitive rung."""
    (path or ASSET_PATH).unlink(missing_ok=True)
