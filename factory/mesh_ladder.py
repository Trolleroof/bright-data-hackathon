"""The three-rung geometry ladder, in one call that never raises.

  rung 1  the product's own AR model, off the page the scrape already opened
  rung 2  a category mesh discovered across the wider 3D-asset web
  rung 3  the primitive cylinder at scraped dimensions — what we ship today

Rung 3 is a labelled degradation, not a failure: ``acquire()`` always returns a
MeshLadderResult, and the rung it reports is what the HUD shows. Nothing here
is allowed to take the demo down, so every failure is caught and recorded as a
reason string on the way to the next rung.

Scale: the mesh arrives unit-less, and the size it is rescaled to comes from
the scrape (the camera supplies the metric table frame the object sits in, not
its height). Pass ``measured_height_cm`` when a real measurement exists — the
result records which of the two was used in ``scale_source``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from engine.spec import MATERIALS
from factory.mesh_fit import MeshFitError, clear_asset, fit, save_asset
from integrations.brightdata import load_rules
from integrations.config import Settings
from integrations.mesh_discovery import MeshDiscoveryError, find_meshes
from integrations.tracing import record_event, span


@dataclass(frozen=True)
class MeshLadderResult:
    rung: int
    asset: dict[str, Any] | None
    reasons: list[str] = field(default_factory=list)
    attempts: list[dict] = field(default_factory=list)

    @property
    def label(self) -> str:
        from twin.world import rung_label  # noqa: PLC0415 — avoids a cycle at import

        return rung_label(self.asset)


def _fallback_density(material: str | None) -> float:
    physics = MATERIALS.get(str(material or "plastic").lower(), MATERIALS["plastic"])
    return float(physics["density_kg_m3"])


def acquire(
    label: str,
    catalog: dict[str, Any] | None,
    *,
    settings: Settings | None = None,
    measured_height_cm: float | None = None,
    measured_width_cm: float | None = None,
    collision_faces: int | None = None,
    out_dir: Path | None = None,
) -> MeshLadderResult:
    """Search, download, and fit a mesh; fall to the primitive with a reason."""
    catalog = catalog or {}
    if collision_faces is None:
        collision_faces = int(load_rules().get("mesh", {}).get("collision_faces", 400))
    height_cm = measured_height_cm or catalog.get("height_cm")
    width_cm = measured_width_cm or catalog.get("width_cm")
    scale_source = "camera" if measured_height_cm else "scrape"
    reasons: list[str] = []

    if not height_cm or not width_cm:
        clear_asset()
        return MeshLadderResult(3, None, ["no dimensions to scale a mesh to"])

    product_url = catalog.get("url") if catalog.get("source") == "live" else None
    asset = None
    attempts: list[dict] = []
    with span("mesh_search", label=label, product_url=product_url or ""):
        try:
            downloads = find_meshes(label, product_url=product_url, settings=settings)
            # A download that will not load is not a reason to drop to the
            # primitive while other candidates are still queued: keep walking.
            for download in downloads:
                attempts = download.attempts
                record_event(
                    "mesh_found",
                    rung=download.candidate.rung,
                    source=download.candidate.source,
                    url=download.candidate.asset_url,
                    bytes=download.size_bytes,
                    latency_ms=download.latency_ms,
                )
                with span("mesh_fit", source=download.candidate.source, rung=download.candidate.rung):
                    try:
                        asset = fit(
                            download.path,
                            height_cm=float(height_cm),
                            width_cm=float(width_cm),
                            weight_g=catalog.get("weight_g"),
                            fallback_density=_fallback_density(catalog.get("material")),
                            rung=download.candidate.rung,
                            source=download.candidate.source,
                            asset_url=download.candidate.asset_url,
                            page_url=download.candidate.page_url,
                            collision_faces=collision_faces,
                            out_dir=out_dir,
                        )
                    except (MeshFitError, ImportError, OSError, ValueError) as exc:
                        reasons.append(f"fit failed for {download.candidate.asset_url}: {exc}")
                        continue
                break
        except MeshDiscoveryError as exc:
            clear_asset()
            record_event("mesh_result", rung=3, reason=str(exc))
            return MeshLadderResult(3, None, [*reasons, str(exc)], attempts)

    if asset is None:
        clear_asset()
        reasons.append("no candidate mesh could be loaded and fitted")
        record_event("mesh_result", rung=3, reason=reasons[-1])
        return MeshLadderResult(3, None, reasons, attempts)

    payload = save_asset(asset, extra={"scale_source": scale_source})

    record_event(
        "mesh_result",
        rung=asset.rung,
        source=asset.source,
        scale=asset.scale,
        scale_source=scale_source,
        faces_visual=asset.faces_visual,
        faces_collision=asset.faces_collision,
        density_kg_m3=asset.density_kg_m3,
        density_source=asset.density_source,
        width_residual_cm=asset.width_residual_cm,
    )
    return MeshLadderResult(asset.rung, payload, reasons, attempts)
