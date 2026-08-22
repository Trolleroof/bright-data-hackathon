"""SigNoz via OTLP/HTTP + in-memory flight recorder for live HUD/timeline.

Emits full demo spans:
detect -> tag_pose -> update_twin -> extract_params -> scrape -> patch_spec -> test -> approve -> skill_exec
Events:
- physical_prompt (when recording ends)
- release (when spec hot-swaps)
"""

from __future__ import annotations

import json
import queue
import threading
import time
from contextlib import contextmanager
from typing import Any, Iterator

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from integrations.config import load_settings

_booted = False
_lock = threading.Lock()
_raw_spans: list[dict[str, Any]] = []
_subscribers: list[queue.Queue[dict[str, Any]]] = []


class LocalSpanCollector(SpanProcessor):
    """Captures spans locally with microsecond precision and broadcasts to subscribers."""

    def on_start(self, span: Any, parent_context: Any = None) -> None:
        pass

    def on_end(self, span: ReadableSpan) -> None:
        ctx = span.get_span_context()
        parent_span_id = (
            f"{span.parent.span_id:016x}" if span.parent and span.parent.span_id else None
        )

        events = []
        for ev in span.events:
            events.append({
                "name": ev.name,
                "timestamp_ns": ev.timestamp,
                "attributes": dict(ev.attributes or {}),
            })

        status_code = span.status.status_code.name if span.status else "UNSET"
        status_desc = span.status.description or "" if span.status else ""

        span_data = {
            "name": span.name,
            "trace_id": f"{ctx.trace_id:032x}",
            "span_id": f"{ctx.span_id:016x}",
            "parent_id": parent_span_id,
            "start_time_ns": span.start_time,
            "end_time_ns": span.end_time,
            "duration_ms": max(0.001, (span.end_time - span.start_time) / 1_000_000.0),
            "attributes": dict(span.attributes or {}),
            "events": events,
            "status": {
                "code": status_code,
                "description": status_desc,
            },
        }

        with _lock:
            _raw_spans.append(span_data)
            # Limit stored raw spans to prevent unbounded memory growth
            if len(_raw_spans) > 2000:
                _raw_spans.pop(0)

            # Broadcast copy to live subscribers
            dead_subs = []
            for sub in _subscribers:
                try:
                    sub.put_nowait(span_data)
                except queue.Full:
                    dead_subs.append(sub)
            for sub in dead_subs:
                if sub in _subscribers:
                    _subscribers.remove(sub)

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


def subscribe_spans() -> queue.Queue[dict[str, Any]]:
    """Subscribe to real-time spans for SSE or WebSocket streaming."""
    q: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=500)
    with _lock:
        _subscribers.append(q)
    return q


def unsubscribe_spans(q: queue.Queue[dict[str, Any]]) -> None:
    with _lock:
        if q in _subscribers:
            _subscribers.remove(q)


def get_raw_spans() -> list[dict[str, Any]]:
    with _lock:
        return list(_raw_spans)


def clear_spans() -> None:
    with _lock:
        _raw_spans.clear()


def _sanitize_attr_value(val: Any) -> Any:
    """Ensure attribute values conform to OpenTelemetry supported types."""
    if val is None:
        return None
    if isinstance(val, (bool, str, bytes, int, float)):
        return val
    if hasattr(val, "item") and callable(getattr(val, "item")):
        try:
            val = val.item()
            if isinstance(val, (bool, str, bytes, int, float)):
                return val
        except Exception:
            pass
    if isinstance(val, (list, tuple)):
        if not val:
            return []
        first = val[0]
        if isinstance(first, (bool, str, bytes, int, float)) and all(
            isinstance(x, type(first)) for x in val
        ):
            return list(val)
        try:
            return json.dumps(val, default=str)
        except Exception:
            return str(val)
    if isinstance(val, dict):
        try:
            return json.dumps(val, default=str)
        except Exception:
            return str(val)
    try:
        return str(val)
    except Exception:
        return repr(val)


def _sanitize_attributes(attrs: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for k, v in attrs.items():
        if v is not None:
            sanitized = _sanitize_attr_value(v)
            if sanitized is not None:
                cleaned[str(k)] = sanitized
    return cleaned


def _boot() -> None:
    global _booted
    if _booted:
        return
    with _lock:
        if _booted:
            return
        settings = load_settings()
        provider = TracerProvider(
            resource=Resource.create({
                "service.name": settings.otel_service_name,
                "deployment.environment": "production" if settings.signoz_ready else "development",
            })
        )
        # Always add our in-memory local collector
        provider.add_span_processor(LocalSpanCollector())

        if settings.signoz_ready:
            try:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

                endpoint = settings.signoz_endpoint.rstrip("/")
                if not endpoint.endswith("/v1/traces"):
                    endpoint = f"{endpoint}/v1/traces"
                exporter = OTLPSpanExporter(
                    endpoint=endpoint,
                    headers={"signoz-ingestion-key": settings.signoz_ingestion_key},
                )
                provider.add_span_processor(BatchSpanProcessor(exporter))
            except Exception as exc:
                print(f"[SigNoz] OTLP exporter init warning: {exc}")

        trace.set_tracer_provider(provider)
        _booted = True


def tracer_ready() -> str:
    settings = load_settings()
    return "signoz" if settings.signoz_ready else "console"


def get_tracer():
    _boot()
    return trace.get_tracer("bidex")


@contextmanager
def span(name: str, **attrs: object) -> Iterator[trace.Span]:
    """Starts an OpenTelemetry span, sets attributes, and handles active scope."""
    _boot()
    tracer = get_tracer()
    clean_attrs = _sanitize_attributes(attrs)
    with tracer.start_as_current_span(name, attributes=clean_attrs) as current:
        yield current


def record_event(name: str, **attrs: object) -> None:
    """Records an OpenTelemetry event on the current active span."""
    _boot()
    current = trace.get_current_span()
    if current and current.is_recording():
        clean_attrs = _sanitize_attributes(attrs)
        current.add_event(name, attributes=clean_attrs)


def get_trace_trees() -> list[dict[str, Any]]:
    """Organizes captured spans into hierarchical trace trees for visualizers."""
    spans = get_raw_spans()
    if not spans:
        return []

    by_trace: dict[str, list[dict[str, Any]]] = {}
    for s in spans:
        by_trace.setdefault(s["trace_id"], []).append(s)

    trees = []
    for trace_id, trace_spans in by_trace.items():
        # Sort chronologically
        trace_spans.sort(key=lambda x: x["start_time_ns"])
        min_start = min(s["start_time_ns"] for s in trace_spans)
        max_end = max(s["end_time_ns"] for s in trace_spans)
        total_duration_ms = max(0.001, (max_end - min_start) / 1_000_000.0)

        span_map: dict[str, dict[str, Any]] = {}
        all_events: list[dict[str, Any]] = []

        for s in trace_spans:
            offset_ms = (s["start_time_ns"] - min_start) / 1_000_000.0
            span_node = {
                **s,
                "offset_ms": round(offset_ms, 2),
                "duration_ms": round(s["duration_ms"], 2),
                "percent_start": round((offset_ms / total_duration_ms) * 100, 2) if total_duration_ms > 0 else 0,
                "percent_width": max(0.5, round((s["duration_ms"] / total_duration_ms) * 100, 2)) if total_duration_ms > 0 else 100,
                "children": [],
            }
            span_map[s["span_id"]] = span_node

            for ev in s["events"]:
                ev_offset_ms = (ev["timestamp_ns"] - min_start) / 1_000_000.0
                all_events.append({
                    "name": ev["name"],
                    "span_id": s["span_id"],
                    "span_name": s["name"],
                    "timestamp_ns": ev["timestamp_ns"],
                    "offset_ms": round(ev_offset_ms, 2),
                    "percent_offset": round((ev_offset_ms / total_duration_ms) * 100, 2) if total_duration_ms > 0 else 0,
                    "attributes": ev["attributes"],
                })

        roots: list[dict[str, Any]] = []
        for s in trace_spans:
            span_id = s["span_id"]
            node = span_map[span_id]
            parent_id = s["parent_id"]
            if parent_id and parent_id in span_map:
                span_map[parent_id]["children"].append(node)
            else:
                roots.append(node)

        # Label root operation
        root_name = roots[0]["name"] if roots else "pipeline"
        run_name = roots[0]["attributes"].get("run.name", root_name) if roots else root_name

        # Flatten nodes in display order with depth
        flat_ordered: list[dict[str, Any]] = []
        def _traverse(node: dict[str, Any], depth: int = 0) -> None:
            flat_ordered.append({**node, "depth": depth})
            for ch in node["children"]:
                _traverse(ch, depth + 1)
        for r in roots:
            _traverse(r, 0)

        trees.append({
            "trace_id": trace_id,
            "root_name": root_name,
            "run_name": run_name,
            "span_count": len(trace_spans),
            "event_count": len(all_events),
            "start_time_ns": min_start,
            "end_time_ns": max_end,
            "total_duration_ms": round(total_duration_ms, 2),
            "events": all_events,
            "root_spans": roots,
            "flat_spans": flat_ordered,
        })

    trees.sort(key=lambda t: t["start_time_ns"], reverse=True)
    return trees


def emit_demo_trace(run_type: str = "A", sleep_step: float = 0.05) -> str:
    """Emits the full canonical timeline trace tree for demo runs A or B.

    Sequence:
    detect -> tag_pose -> update_twin -> (event: physical_prompt)
    -> extract_params -> scrape -> patch_spec -> test -> approve
    -> (event: release) -> skill_exec
    """
    _boot()
    is_run_b = (run_type.upper() == "B" or "avoid" in run_type.lower() or "bottle" in run_type.lower())

    root_title = "Demo Run B: compose(goto, avoid)" if is_run_b else "Demo Run A: goto"
    primitive = "compose(goto, avoid)" if is_run_b else "goto"

    with span(
        "flight_recorder",
        **{
            "service.name": "bidex",
            "run.name": root_title,
            "run.primitive": primitive,
            "run.mode": "fast_path",
            "table.tag_id": 0,
            "zero_downtime": "true",
        }
    ):
        # 1. detect
        if sleep_step > 0:
            time.sleep(sleep_step)
        with span("detect", camera_fps=30.0, resolution="1280x720", cube_detected=True, cube_area_px=1480):
            if is_run_b:
                record_event("obstacle_detected", color="blue", contour_area_px=3420, label="bottle")
            if sleep_step > 0:
                time.sleep(sleep_step)

        # 2. tag_pose
        with span("tag_pose", tag_family="tag36h11", tag_size_cm=6.5, tag_seen=True, distance_m=0.72):
            if sleep_step > 0:
                time.sleep(sleep_step)

        # 3. update_twin
        with span("update_twin", prompt_state="RECORDING", body="cube", drift_compensation_mm=0.2):
            if sleep_step > 0:
                time.sleep(sleep_step)
            # Event 1: physical_prompt when recording ends!
            record_event(
                "physical_prompt",
                recording_s=8.14,
                bag_frames=244,
                prompt_state="PROMPTED",
                target_square="back_right",
                obstacle=is_run_b,
            )

        # 4. extract_params
        with span("extract_params", extractor="waypoint_fast_path", input_bag="bag_20260822_01.npz", waypoints_count=48):
            if sleep_step > 0:
                time.sleep(sleep_step)

        # 5. scrape
        if is_run_b:
            with span(
                "scrape",
                sponsor="Bright Data",
                catalog_url="https://www.ikea.com/us/en/p/ikea-365-water-bottle-dark-gray-70478228/",
                item_name="IKEA 365+ water bottle",
                width_cm=7.0,
                height_cm=24.0,
                weight_g=120.0,
                material="plastic",
                density_kg_m3=950.0,
                friction=0.35,
                mass_defaulted=False,
                cached=False,
                geom="cylinder",
            ):
                if sleep_step > 0:
                    time.sleep(sleep_step)
        else:
            with span("scrape", status="bypassed_for_goto", sponsor="Bright Data", required=False):
                if sleep_step > 0:
                    time.sleep(sleep_step)

        # 6. patch_spec
        steps_spec = [
            {"op": "replay_trajectory", "path": [[0.0, 0.0, 0.0], [0.28, 0.18, 2.0]]},
            {"op": "avoid", "at": [-0.12, 0.05], "geom": "cylinder", "width_cm": 7.0, "height_cm": 24.0, "weight_g": 120.0, "material": "plastic"}
        ] if is_run_b else [
            {"op": "goto", "start": [0.0, 0.0], "end": [0.28, 0.18], "duration_s": 2.0}
        ]
        with span("patch_spec", spec_version=2, ops=primitive, spec_json=json.dumps(steps_spec)):
            if sleep_step > 0:
                time.sleep(sleep_step)

        # 7. test
        with span("test", test_gate="replay_bag_exam", collision_free=True, max_error_cm=0.38, result="PASS"):
            if sleep_step > 0:
                time.sleep(sleep_step)

        # 8. approve
        with span("approve", gate="fast_path_auto_approval", operator="auto", latency_ms=45.2):
            if sleep_step > 0:
                time.sleep(sleep_step)
            # Event 2: release when spec hot-swaps!
            record_event(
                "release",
                hot_swap=True,
                zero_downtime=True,
                spec_version=2,
                twin_state="UNINTERRUPTED",
            )

        # 9. skill_exec
        with span("skill_exec", engine="mujoco_so101", duration_s=2.2, trajectory_fidelity=0.998, status="COMPLETED"):
            if sleep_step > 0:
                time.sleep(sleep_step)

    provider = trace.get_tracer_provider()
    if hasattr(provider, "force_flush"):
        provider.force_flush(timeout_millis=5000)

    trees = get_trace_trees()
    return trees[0]["trace_id"] if trees else ""


def smoke() -> str:
    """Emit setup spans without firing physical_prompt."""
    with span("detect", setup="true"):
        with span("tag_pose", setup="true"):
            with span("update_twin", setup="true"):
                pass
    provider = trace.get_tracer_provider()
    if hasattr(provider, "force_flush"):
        provider.force_flush(timeout_millis=5000)
    return tracer_ready()
