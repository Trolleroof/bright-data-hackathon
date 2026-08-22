"""Happy path: bag -> extract -> scrape -> patch -> replay test."""

from __future__ import annotations

import time
import json
from dataclasses import dataclass
from pathlib import Path

from factory.extract import ExtractedParams, extract
from factory.mesh_ladder import MeshLadderResult, acquire
from factory.patch import patch_spec
from factory.replay_test import ReplayResult, replay_test
from integrations.brightdata import lookup
from integrations.config import ROOT, load_settings
from integrations.port import sync_fast_path_run
from integrations.tracing import record_event, span
from vision.bag import PromptBag, load_bag


@dataclass(frozen=True)
class FactoryResult:
    bag_path: Path
    spec_path: Path
    extracted: ExtractedParams
    catalog: dict | None
    mesh: MeshLadderResult | None
    replay: ReplayResult
    elapsed_ms: float


def run_fast_path(
    bag_path: Path,
    spec_path: Path | None = None,
    *,
    scrape_label: str | None = None,
    append: bool = False,
    mesh: bool = True,
    measured_height_cm: float | None = None,
    measured_width_cm: float | None = None,
) -> FactoryResult:
    """Run the factory. The bag gives the obstacle's position, not its size, so
    mesh scale comes from the scrape unless a caller passes a real measurement
    in ``measured_*`` — ``mesh_rung`` records which of the two was used."""
    started = time.perf_counter()
    spec_path = spec_path or (ROOT / "outputs" / "skill_spec.json")
    bag = load_bag(bag_path)

    with span("extract_params", extractor="waypoint_fast_path", input_bag=bag.bag_id):
        params = extract(bag)
        record_event(
            "physical_prompt",
            recording_s=bag.duration_s,
            bag_frames=len(bag.frames),
            motion=params.motion,
            start=list(params.start),
            end=list(params.end),
        )

    catalog = None
    mesh_result: MeshLadderResult | None = None
    # Skill A (plain R / no --label) must never hit Bright Data. Hands, sleeves,
    # and table clutter look like not-red blobs, so obstacle_xy is not enough.
    # Only Run B (F / --append) or an explicit scrape_label may look up the web.
    want_scrape = append or scrape_label is not None
    if want_scrape and params.obstacle_xy:
        label = scrape_label or params.obstacle_label or "water bottle"
        print(f"  scrape started  |  label={label!r}", flush=True)
        with span("scrape", label=label, sponsor="Bright Data"):
            catalog = lookup(label)
            record_event(
                "scrape_result",
                source=catalog.get("source"),
                url=catalog.get("url"),
                latency_ms=catalog.get("latency_ms"),
                width_cm=catalog.get("width_cm"),
                height_cm=catalog.get("height_cm"),
            )

        # Shape is the one thing neither the camera nor the scrape can produce.
        # Rung 3 (the primitive) is a normal outcome here, not an error path.
        if mesh:
            mesh_result = acquire(
                label,
                catalog,
                measured_height_cm=measured_height_cm,
                measured_width_cm=measured_width_cm,
            )
            record_event(
                "mesh_rung",
                rung=mesh_result.rung,
                label=mesh_result.label,
                scale_source=(mesh_result.asset or {}).get("scale_source", "none"),
            )
    else:
        with span(
            "scrape",
            status="bypassed_for_skill_a",
            sponsor="Bright Data",
            required=False,
            obstacle_seen=params.obstacle_xy is not None,
        ):
            pass
        print(
            "  scrape skipped  |  skill A (press F to append obstacle + Bright Data)",
            flush=True,
        )

    with span("patch_spec", spec_path=str(spec_path), append=append):
        spec = patch_spec(
            params,
            spec_path,
            catalog if want_scrape else None,
            append=append,
            mesh=mesh_result.asset if mesh_result else None,
        )
        record_event("spec_patched", step_count=len(spec["steps"]), motion=params.motion)

    with span("test", test_gate="replay_bag_exam"):
        replay = replay_test(spec_path)
        record_event(
            "replay_exam",
            result=replay.detail,
            steps_completed=replay.steps_completed,
            max_error_cm=replay.max_error_cm,
        )

    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    with span("port_sync", integration="Port", blocking=False) as port_span:
        try:
            spec_obj = json.loads(spec_path.read_text())
            spec_step_count = len(spec_obj.get("steps", [])) if isinstance(spec_obj, dict) else 0
            synced = sync_fast_path_run(
                bag_id=bag.bag_id,
                duration_s=bag.duration_s,
                motion=params.motion,
                replay_passed=replay.passed,
                replay_detail=replay.detail,
                elapsed_ms=elapsed_ms,
                append=append,
                spec_step_count=spec_step_count,
                catalog=catalog,
            )
            result = "skipped" if synced.startswith("skipped") else "synced"
            port_span.set_attribute("result", result)
            record_event("port_entities_upserted", summary=synced)
            print(f"  port synced     |  {synced}", flush=True)
        except Exception as exc:  # noqa: BLE001 - Port must not block the factory
            port_span.set_attribute("result", "error")
            record_event("port_sync_failed", error=str(exc))
            print(f"  port skipped    |  {exc}", flush=True)
    return FactoryResult(bag_path, spec_path, params, catalog, mesh_result, replay, elapsed_ms)


def smoke_from_synthetic_bag() -> FactoryResult:
    """Offline factory check when no camera recording exists yet."""
    from vision.bag import BagFrame, PromptBag, save_bag

    frames = [
        BagFrame(t=0.0, cube_xy=(0.0, 0.0), obstacle_xy=None, tag_seen=True),
        BagFrame(t=1.0, cube_xy=(0.14, 0.09), obstacle_xy=None, tag_seen=True),
        BagFrame(t=2.0, cube_xy=(0.28, 0.18), obstacle_xy=None, tag_seen=True),
    ]
    bag = PromptBag(frames=frames, started_at="synthetic", duration_s=2.0, bag_id="bag_smoke")
    path = save_bag(bag, ROOT / "recordings" / "bag_smoke.json")
    return run_fast_path(path)
