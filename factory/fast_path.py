"""Happy path: bag -> extract -> scrape -> patch -> replay test."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from factory.extract import ExtractedParams, extract
from factory.patch import patch_spec
from factory.replay_test import ReplayResult, replay_test
from integrations.brightdata import lookup
from integrations.config import ROOT, load_settings
from integrations.tracing import record_event, span
from vision.bag import PromptBag, load_bag


@dataclass(frozen=True)
class FactoryResult:
    bag_path: Path
    spec_path: Path
    extracted: ExtractedParams
    catalog: dict | None
    replay: ReplayResult
    elapsed_ms: float


def run_fast_path(
    bag_path: Path,
    spec_path: Path | None = None,
    *,
    scrape_label: str | None = None,
    append: bool = False,
) -> FactoryResult:
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
    if params.obstacle_xy:
        label = scrape_label or params.obstacle_label or "water bottle"
        with span("scrape", label=label):
            catalog = lookup(label)
            record_event(
                "scrape_result",
                source=catalog.get("source"),
                url=catalog.get("url"),
                latency_ms=catalog.get("latency_ms"),
                width_cm=catalog.get("width_cm"),
                height_cm=catalog.get("height_cm"),
            )

    with span("patch_spec", spec_path=str(spec_path), append=append):
        spec = patch_spec(params, spec_path, catalog, append=append)
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
    return FactoryResult(bag_path, spec_path, params, catalog, replay, elapsed_ms)


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
