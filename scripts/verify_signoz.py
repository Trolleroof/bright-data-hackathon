"""Comprehensive verification suite for SigNoz & Flight Recorder integration (Issue #5).

Tests:
1. Setup smoke test & fallback behavior
2. Trace generation for Run A (goto) & Run B (compose(goto, avoid))
3. Presence and sequence of all 9 canonical spans:
   detect -> tag_pose -> update_twin -> extract_params -> scrape -> patch_spec -> test -> approve -> skill_exec
4. Events: physical_prompt (recording duration, frames, state) & release (zero_downtime, hot_swap, spec_version)
5. Span attribute validity and OpenTelemetry type sanitization
6. Hierarchical integrity (single root trace tree, parent_id linking, timestamps, duration, depth)
7. Live streaming subscribers & queue management
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from integrations.config import load_settings
from integrations.signoz import (
    clear_spans,
    emit_demo_trace,
    get_raw_spans,
    get_trace_trees,
    record_event,
    smoke,
    span,
    subscribe_spans,
    tracer_ready,
    unsubscribe_spans,
)

CANONICAL_SPANS = [
    "detect",
    "tag_pose",
    "update_twin",
    "extract_params",
    "scrape",
    "patch_spec",
    "test",
    "approve",
    "skill_exec",
]


class TestRunner:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.total = 0

    def assert_true(self, condition: bool, description: str) -> None:
        self.total += 1
        if condition:
            self.passed += 1
            print(f"  [PASS] {description}")
        else:
            self.failed += 1
            print(f"  [FAIL] {description}", file=sys.stderr)

    def assert_equal(self, actual: object, expected: object, description: str) -> None:
        self.total += 1
        if actual == expected:
            self.passed += 1
            print(f"  [PASS] {description}")
        else:
            self.failed += 1
            print(
                f"  [FAIL] {description} — expected {expected!r}, got {actual!r}",
                file=sys.stderr,
            )


def test_setup_and_fallback(runner: TestRunner) -> None:
    print("\n--- 1. Setup & Fallback Smoke Test ---")
    settings = load_settings()
    mode = tracer_ready()
    runner.assert_true(
        mode in ("console", "signoz"),
        f"tracer_ready() returns valid mode ('{mode}')",
    )
    if not settings.signoz_ready:
        runner.assert_equal(mode, "console", "Fallback to 'console' when keys are absent")
    else:
        runner.assert_equal(mode, "signoz", "Reports 'signoz' when keys are present")

    smoke_result = smoke()
    runner.assert_equal(
        smoke_result,
        mode,
        f"smoke() reports '{smoke_result}' matching tracer_ready()",
    )


def test_trace_run_a(runner: TestRunner) -> None:
    print("\n--- 2. Demo Run A: goto (Canonical Spans & Hierarchy) ---")
    clear_spans()
    trace_id = emit_demo_trace("A", sleep_step=0.002)

    runner.assert_true(
        bool(trace_id and len(trace_id) == 32),
        f"Run A returned valid 32-char hex trace_id: {trace_id}",
    )

    trees = get_trace_trees()
    runner.assert_equal(len(trees), 1, "Exactly 1 trace tree produced for Run A")

    tree = trees[0]
    runner.assert_equal(tree["trace_id"], trace_id, "Tree trace_id matches emitted trace_id")
    runner.assert_equal(tree["root_name"], "flight_recorder", "Root span is 'flight_recorder'")
    runner.assert_equal(tree["run_name"], "Demo Run A: goto", "Run name is 'Demo Run A: goto'")
    runner.assert_equal(tree["span_count"], 10, "Span count is 10 (1 root + 9 canonical spans)")

    # Validate canonical sequence of spans
    flat_spans = tree["flat_spans"]
    runner.assert_equal(flat_spans[0]["name"], "flight_recorder", "First span in flat list is root")
    runner.assert_equal(flat_spans[0]["depth"], 0, "Root span depth is 0")

    child_span_names = [s["name"] for s in flat_spans[1:]]
    runner.assert_equal(
        child_span_names,
        CANONICAL_SPANS,
        f"All 9 canonical spans present in exact sequence: {' -> '.join(CANONICAL_SPANS)}",
    )

    for s in flat_spans[1:]:
        runner.assert_equal(s["depth"], 1, f"Child span '{s['name']}' has depth 1")
        runner.assert_equal(
            s["parent_id"],
            flat_spans[0]["span_id"],
            f"Child span '{s['name']}' parent_id links to root span_id",
        )
        runner.assert_equal(s["trace_id"], trace_id, f"Child span '{s['name']}' has trace_id {trace_id}")
        runner.assert_true(s["duration_ms"] > 0, f"Child span '{s['name']}' duration_ms > 0 ({s['duration_ms']}ms)")

    # Validate root attributes
    root_attrs = flat_spans[0]["attributes"]
    runner.assert_equal(root_attrs.get("service.name"), "bidex", "Root attribute service.name == 'bidex'")
    runner.assert_equal(root_attrs.get("run.primitive"), "goto", "Root attribute run.primitive == 'goto'")
    runner.assert_equal(root_attrs.get("run.mode"), "fast_path", "Root attribute run.mode == 'fast_path'")

    # Validate specific span attributes
    by_name = {s["name"]: s for s in flat_spans}

    detect_attrs = by_name["detect"]["attributes"]
    runner.assert_true("camera_fps" in detect_attrs, "detect span has camera_fps attribute")
    runner.assert_true("cube_detected" in detect_attrs, "detect span has cube_detected attribute")

    tag_attrs = by_name["tag_pose"]["attributes"]
    runner.assert_true("tag_family" in tag_attrs, "tag_pose span has tag_family attribute")
    runner.assert_true(tag_attrs.get("tag_seen") is True, "tag_pose span tag_seen is True")

    scrape_attrs = by_name["scrape"]["attributes"]
    runner.assert_equal(scrape_attrs.get("sponsor"), "Bright Data", "scrape span sponsor is 'Bright Data'")
    runner.assert_equal(scrape_attrs.get("status"), "bypassed_for_goto", "scrape span status is 'bypassed_for_goto'")

    patch_attrs = by_name["patch_spec"]["attributes"]
    runner.assert_equal(patch_attrs.get("spec_version"), 2, "patch_spec span spec_version == 2")
    runner.assert_equal(patch_attrs.get("ops"), "goto", "patch_spec span ops == 'goto'")

    test_attrs = by_name["test"]["attributes"]
    runner.assert_equal(test_attrs.get("result"), "PASS", "test span result == 'PASS'")
    runner.assert_equal(test_attrs.get("collision_free"), True, "test span collision_free == True")

    approve_attrs = by_name["approve"]["attributes"]
    runner.assert_equal(approve_attrs.get("gate"), "fast_path_auto_approval", "approve span gate is 'fast_path_auto_approval'")

    skill_attrs = by_name["skill_exec"]["attributes"]
    runner.assert_equal(skill_attrs.get("status"), "COMPLETED", "skill_exec span status == 'COMPLETED'")

    # Validate events in Run A
    events = tree["events"]
    runner.assert_equal(len(events), 2, "Run A has exactly 2 recorded events")
    event_names = [e["name"] for e in events]
    runner.assert_true("physical_prompt" in event_names, "Event 'physical_prompt' recorded")
    runner.assert_true("release" in event_names, "Event 'release' recorded")

    prompt_event = next(e for e in events if e["name"] == "physical_prompt")
    runner.assert_equal(prompt_event["span_name"], "update_twin", "physical_prompt attached to 'update_twin'")
    runner.assert_true("recording_s" in prompt_event["attributes"], "physical_prompt has recording_s attribute")
    runner.assert_true("bag_frames" in prompt_event["attributes"], "physical_prompt has bag_frames attribute")
    runner.assert_equal(prompt_event["attributes"].get("prompt_state"), "PROMPTED", "physical_prompt state == 'PROMPTED'")

    release_event = next(e for e in events if e["name"] == "release")
    runner.assert_equal(release_event["span_name"], "approve", "release event attached to 'approve'")
    runner.assert_equal(release_event["attributes"].get("zero_downtime"), True, "release event zero_downtime == True")
    runner.assert_equal(release_event["attributes"].get("hot_swap"), True, "release event hot_swap == True")
    runner.assert_equal(release_event["attributes"].get("spec_version"), 2, "release event spec_version == 2")


def test_trace_run_b(runner: TestRunner) -> None:
    print("\n--- 3. Demo Run B: compose(goto, avoid) with Bright Data Scrape ---")
    clear_spans()
    trace_id = emit_demo_trace("B", sleep_step=0.002)

    runner.assert_true(
        bool(trace_id and len(trace_id) == 32),
        f"Run B returned valid 32-char hex trace_id: {trace_id}",
    )

    trees = get_trace_trees()
    runner.assert_equal(len(trees), 1, "Exactly 1 trace tree produced for Run B")

    tree = trees[0]
    runner.assert_equal(tree["trace_id"], trace_id, "Tree trace_id matches emitted trace_id")
    runner.assert_equal(tree["run_name"], "Demo Run B: compose(goto, avoid)", "Run name is 'Demo Run B: compose(goto, avoid)'")
    runner.assert_equal(tree["span_count"], 10, "Span count is 10 (1 root + 9 canonical spans)")

    flat_spans = tree["flat_spans"]
    child_span_names = [s["name"] for s in flat_spans[1:]]
    runner.assert_equal(
        child_span_names,
        CANONICAL_SPANS,
        f"All 9 canonical spans present in exact sequence in Run B: {' -> '.join(CANONICAL_SPANS)}",
    )

    by_name = {s["name"]: s for s in flat_spans}

    # Run B Scrape span validation (Bright Data lookup for bottle)
    scrape_attrs = by_name["scrape"]["attributes"]
    runner.assert_equal(scrape_attrs.get("sponsor"), "Bright Data", "scrape span sponsor is 'Bright Data'")
    runner.assert_equal(scrape_attrs.get("item_name"), "IKEA 365+ water bottle", "scrape item_name matches bottle")
    runner.assert_equal(scrape_attrs.get("geom"), "cylinder", "scrape geom is 'cylinder'")
    runner.assert_equal(scrape_attrs.get("width_cm"), 7.0, "scrape width_cm is 7.0")
    runner.assert_equal(scrape_attrs.get("height_cm"), 24.0, "scrape height_cm is 24.0")

    # Run B Patch Spec validation
    patch_attrs = by_name["patch_spec"]["attributes"]
    runner.assert_equal(patch_attrs.get("ops"), "compose(goto, avoid)", "patch_spec ops is 'compose(goto, avoid)'")
    spec_obj = json.loads(patch_attrs.get("spec_json", "[]"))
    runner.assert_equal(len(spec_obj), 2, "patch_spec spec_json contains 2 steps (replay_trajectory, avoid)")

    # Run B Events validation (obstacle_detected + physical_prompt + release)
    events = tree["events"]
    runner.assert_equal(len(events), 3, "Run B has exactly 3 recorded events")
    event_names = [e["name"] for e in events]
    runner.assert_true("obstacle_detected" in event_names, "Event 'obstacle_detected' recorded in Run B")
    runner.assert_true("physical_prompt" in event_names, "Event 'physical_prompt' recorded in Run B")
    runner.assert_true("release" in event_names, "Event 'release' recorded in Run B")

    obs_event = next(e for e in events if e["name"] == "obstacle_detected")
    runner.assert_equal(obs_event["span_name"], "detect", "obstacle_detected attached to 'detect'")
    runner.assert_equal(obs_event["attributes"].get("label"), "bottle", "obstacle_detected label == 'bottle'")

    prompt_event = next(e for e in events if e["name"] == "physical_prompt")
    runner.assert_equal(prompt_event["attributes"].get("obstacle"), True, "physical_prompt obstacle == True in Run B")


def test_attribute_sanitization(runner: TestRunner) -> None:
    print("\n--- 4. Attribute Serialization Robustness Test ---")
    clear_spans()

    # Pass complex structures, dicts, lists, bools, numpy-like items, Path
    test_dict = {"nested": "value", "count": 42}
    test_list_dict = [{"step": 1}, {"step": 2}]
    test_path = Path("/tmp/test_file.json")

    with span(
        "robustness_test_root",
        bool_val=True,
        int_val=100,
        float_val=3.14159,
        str_val="hello",
        dict_val=test_dict,
        list_dict_val=test_list_dict,
        path_val=test_path,
        none_val=None,
    ) as s:
        record_event(
            "test_event",
            ev_dict=test_dict,
            ev_bool=False,
            ev_none=None,
        )

    trees = get_trace_trees()
    runner.assert_equal(len(trees), 1, "Robustness trace recorded successfully")
    root = trees[0]["flat_spans"][0]
    attrs = root["attributes"]

    runner.assert_equal(attrs.get("bool_val"), True, "Boolean attribute serialized properly")
    runner.assert_equal(attrs.get("int_val"), 100, "Integer attribute serialized properly")
    runner.assert_equal(attrs.get("float_val"), 3.14159, "Float attribute serialized properly")
    runner.assert_equal(attrs.get("str_val"), "hello", "String attribute serialized properly")
    runner.assert_equal(json.loads(attrs.get("dict_val", "{}")), test_dict, "Dict attribute JSON-serialized properly")
    runner.assert_equal(attrs.get("path_val"), str(test_path), "Path attribute converted to string properly")
    runner.assert_true("none_val" not in attrs, "None attributes safely omitted")

    ev = trees[0]["events"][0]
    runner.assert_equal(ev["attributes"].get("ev_bool"), False, "Event boolean attribute serialized properly")
    runner.assert_equal(json.loads(ev["attributes"].get("ev_dict", "{}")), test_dict, "Event dict attribute JSON-serialized properly")


def test_streaming_subscribers(runner: TestRunner) -> None:
    print("\n--- 5. Live SSE / Streaming Subscribers Test ---")
    clear_spans()
    q = subscribe_spans()

    with span("stream_test_span", test_id="stream_001"):
        record_event("stream_event", flag=True)

    # Check queue receives the span
    try:
        received = q.get(timeout=2.0)
        runner.assert_equal(received["name"], "stream_test_span", "Subscriber queue received live span")
        runner.assert_equal(received["attributes"].get("test_id"), "stream_001", "Span data in queue is intact")
        runner.assert_equal(len(received["events"]), 1, "Span events delivered to subscriber queue")
    except Exception as exc:
        runner.assert_true(False, f"Subscriber queue failed to receive span: {exc}")
    finally:
        unsubscribe_spans(q)


def main() -> int:
    print("================================================================")
    print(" Bidex SigNoz & Flight Recorder Verification Suite (Issue #5)")
    print("================================================================")

    runner = TestRunner()
    test_setup_and_fallback(runner)
    test_trace_run_a(runner)
    test_trace_run_b(runner)
    test_attribute_sanitization(runner)
    test_streaming_subscribers(runner)

    print("\n================================================================")
    print(f" Summary: {runner.passed}/{runner.total} passed ({runner.failed} failed)")
    print("================================================================")

    if runner.failed == 0:
        print("\nAll SigNoz & Flight Recorder integration tests PASSED (100%).")
        return 0
    else:
        print(f"\n{runner.failed} test(s) FAILED.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
