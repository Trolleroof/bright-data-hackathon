"""Ask before importing: the camera sees a box, the operator decides.

The bounding-box pass (``vision/detect.py``) finds an object the twin has no
geometry for. Pulling geometry for it means going out to the web through
Bright Data, which costs time and quota — so it is not automatic. This module
holds the one bit of state that makes it a conversation:

    scanning off (default) -> nothing is proposed, ever
    operator turns scanning on -> detected -> AWAITING (frontend shows the
             prompt) -> operator answers -> IMPORTING (background thread)
             -> READY | FAILED, or DISMISSED

Scanning is **off until asked for**. A detector running against a live kitchen
will always find *something*, and an unsolicited "import this?" banner over a
demo is worse than no feature at all. The operator turns it on when they want
an object in the twin, and it turns itself back off as soon as one prompt has
been answered.

Every accepted object goes through ``integrations.object_agent``, which never
downloads geometry. It asks Port whether the object is already catalogued,
then has Bright Data search MuJoCo's own model ecosystem (Menagerie, scanned
objects, docs) for a *similar* object and read the MJCF **text**; an NVIDIA NIM
model turns that text into one sized primitive, and the result goes back into
Port for next time. Text in, numbers out — no mesh, no fit, no conversion.

Either way the twin picks the result up by watching ``outputs/mesh_asset.json``
mtime, so nothing here touches the running MuJoCo world directly.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from dataclasses import asdict, dataclass, field
from typing import Any

from factory.mesh_fit import ASSET_PATH, save_primitive_asset
from integrations.config import ROOT
from integrations.tracing import record_event, span
from vision.detect import Detection

SPEC_PATH = ROOT / "outputs" / "skill_spec.json"
# Fallback spot for an imported object when the running skill has no motion to
# read. The table origin is also the arm's home position, so an object left
# here is one the arm starts inside — usable only when there is nothing better.
OBSTACLE_XY = (0.0, 0.0)

IDLE = "IDLE"
AWAITING = "AWAITING"
IMPORTING = "IMPORTING"
READY = "READY"
FAILED = "FAILED"
DISMISSED = "DISMISSED"

# Don't re-ask about the same label for this long after a dismissal.
_DISMISS_COOLDOWN_S = 120.0
# The box has to hold still before we interrupt the operator with a dialog.
_STABLE_FRAMES = 5


@dataclass
class ImportState:
    status: str = IDLE
    label: str = ""
    bbox: list[int] = field(default_factory=list)
    confidence: float = 0.0
    hardcoded: bool = False
    source: str | None = None       # "brightdata" | "port_cache" | None
    rung: int | None = None
    detail: str = ""
    agent: str | None = None        # "nim" | "offline_reader" | "port_cache"
    agent_model: str | None = None
    mujoco_url: str | None = None
    reasoning: str | None = None
    port_entity: str | None = None
    error: str | None = None
    asset: dict[str, Any] | None = None
    started_at: float | None = None
    elapsed_ms: float | None = None

    def as_json(self) -> dict[str, Any]:
        return asdict(self)


class ObjectImporter:
    """One pending import at a time. Thread-safe; polled by ``/api/live``."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = ImportState()
        self._thread: threading.Thread | None = None
        self._dismissed: dict[str, float] = {}
        self._streak_label = ""
        self._streak = 0
        self._scanning = False

    # --- scanning switch --------------------------------------------------
    @property
    def scanning(self) -> bool:
        """Whether the detector should be looking for objects at all."""
        with self._lock:
            return self._scanning

    def set_scanning(self, on: bool) -> dict[str, Any]:
        """Turn object scanning on or off. Off also clears anything pending.

        Turning it on is an explicit request for one object, so the dismissal
        cooldown is cleared too: the operator pointing at the same bottle again
        means they changed their mind, not that we should keep ignoring it.
        """
        with self._lock:
            self._scanning = on
            self._streak_label, self._streak = "", 0
            if on:
                self._dismissed.clear()
                if self._state.status in {IDLE, DISMISSED}:
                    self._state = ImportState(status=IDLE, detail="Scanning for a new object…")
            elif self._state.status in {AWAITING, DISMISSED}:
                self._state = ImportState()
        record_event("import_scanning", on=on)
        return self.state()

    # --- detection side ---------------------------------------------------
    def observe(self, detection: Detection | None) -> None:
        """Feed the newest bounding box in. Raises the prompt when it settles.

        Called every detector pass, so it must be cheap and must not re-prompt
        while an import is running or already answered.
        """
        with self._lock:
            if not self._scanning:
                return

        if detection is None:
            self._streak_label, self._streak = "", 0
            return

        if detection.label == self._streak_label:
            self._streak += 1
        else:
            self._streak_label, self._streak = detection.label, 1

        with self._lock:
            if self._state.status in {AWAITING, IMPORTING}:
                # Keep the box on the prompt fresh so the outline tracks the
                # object while the operator is deciding.
                if self._state.status == AWAITING and detection.label == self._state.label:
                    self._state.bbox = list(detection.bbox)
                    self._state.confidence = round(detection.confidence, 2)
                return
            if self._state.status == READY and self._state.label == detection.label:
                return  # already in the scene
            if self._streak < _STABLE_FRAMES:
                return
            until = self._dismissed.get(detection.label)
            if until is not None and time.monotonic() < until:
                return

            self._state = ImportState(
                status=AWAITING,
                label=detection.label,
                bbox=list(detection.bbox),
                confidence=round(detection.confidence, 2),
                hardcoded=detection.hardcoded,
                detail="Bright Data will search MuJoCo's model ecosystem (Menagerie, scanned objects, docs) for a similar object and read its MJCF text; the agent turns that text into sized MuJoCo geometry. No mesh is downloaded.",
            )
        record_event(
            "import_prompt",
            label=detection.label,
            hardcoded=detection.hardcoded,
            confidence=round(detection.confidence, 2),
        )

    # --- operator side, typed ---------------------------------------------
    def request(self, label: str) -> dict[str, Any]:
        """Import an object the operator named, with no camera involved.

        The camera is one way to find out an object exists; typing its name is
        another, and the rest of the pipeline does not care which it was. There
        is no bounding box here, so no measured aspect ratio — the agent leans
        on the product catalog for size instead of a pixel measurement.
        """
        label = " ".join(str(label).split())[:60]
        if not label:
            return {"error": "an object needs a name"}
        with self._lock:
            if self._state.status == IMPORTING:
                return self._state.as_json()
            self._scanning = False
            self._streak_label, self._streak = "", 0
            self._state = ImportState(
                status=IMPORTING,
                label=label,
                started_at=time.time(),
                source="operator",
                detail=f"Reading MuJoCo model text for {label!r} via Bright Data…",
            )
        record_event("import_request", label=label, origin="operator")
        self._thread = threading.Thread(
            target=self._run_import, args=(label, False, []),
            name="object-import", daemon=True,
        )
        self._thread.start()
        return self.state()

    # --- operator side ----------------------------------------------------
    def decide(self, decision: str) -> dict[str, Any]:
        """``import`` or ``dismiss`` the pending prompt. Returns the new state."""
        decision = decision.lower().strip()
        with self._lock:
            if self._state.status != AWAITING:
                return self._state.as_json()
            label = self._state.label
            hardcoded = self._state.hardcoded
            # Either answer ends this scan. The operator asked for one object.
            self._scanning = False
            self._streak_label, self._streak = "", 0
            if decision in {"dismiss", "decline", "no"}:
                self._dismissed[label] = time.monotonic() + _DISMISS_COOLDOWN_S
                self._state = ImportState(status=DISMISSED, label=label, hardcoded=hardcoded,
                                          detail="Operator declined the import.")
                record_event("import_decision", label=label, decision="dismiss")
                return self._state.as_json()
            if decision not in {"import", "accept", "yes"}:
                self._state.error = f"unknown decision: {decision}"
                return self._state.as_json()

            self._state.status = IMPORTING
            self._state.started_at = time.time()
            self._state.source = "brightdata"
            self._state.detail = "Reading MuJoCo model text via Bright Data…"
            bbox = list(self._state.bbox)

        record_event("import_decision", label=label, decision="import", hardcoded=hardcoded)
        self._thread = threading.Thread(
            target=self._run_import, args=(label, hardcoded, bbox),
            name="object-import", daemon=True,
        )
        self._thread.start()
        return self.state()

    def reset(self) -> dict[str, Any]:
        """Clear the banner. Does not resume scanning — that stays deliberate."""
        with self._lock:
            self._state = ImportState()
            self._streak_label, self._streak = "", 0
        return self.state()

    # --- work -------------------------------------------------------------
    def _run_import(self, label: str, hardcoded: bool, bbox: list[int]) -> None:
        started = time.monotonic()
        # The camera cannot name the object, but it measured how tall it is
        # relative to how wide. That is the one dimension fact the agent must
        # not be allowed to contradict.
        aspect = (bbox[3] / bbox[2]) if len(bbox) == 4 and bbox[2] else None
        with span("object_import", label=label, hardcoded=hardcoded):
            try:
                asset, rung, detail = self._import_from_web(label, aspect)
            except Exception as exc:  # noqa: BLE001 — a failed import must not kill the feed
                with self._lock:
                    self._state.status = FAILED
                    self._state.error = str(exc)
                    self._state.detail = "Import failed; the twin kept its current geometry."
                    self._state.elapsed_ms = round((time.monotonic() - started) * 1000, 1)
                record_event("import_result", label=label, ok=False, error=str(exc))
                return

        elapsed_ms = round((time.monotonic() - started) * 1000, 1)
        spec = (asset or {}).get("spec") or {}
        with self._lock:
            self._state.status = READY
            self._state.asset = asset
            self._state.rung = rung
            self._state.detail = detail
            self._state.source = spec.get("agent") or self._state.source
            self._state.agent = spec.get("agent")
            self._state.agent_model = spec.get("agent_model") or None
            self._state.mujoco_url = spec.get("mujoco_url") or None
            self._state.reasoning = spec.get("reasoning") or None
            self._state.port_entity = spec.get("port_entity") or None
            self._state.bbox = bbox
            self._state.elapsed_ms = elapsed_ms
        try:
            added = add_avoid_step(asset or {})
        except Exception as exc:  # noqa: BLE001 — geometry landed; the spec is a bonus
            added = f"avoid step not written: {exc}"
        with self._lock:
            self._state.detail = f"{detail} {added}".strip()

        record_event(
            "import_result", label=label, ok=True, rung=rung, avoid=added,
            source=(asset or {}).get("source"), agent=spec.get("agent", ""),
            mujoco_url=spec.get("mujoco_url", ""), elapsed_ms=elapsed_ms,
        )

    @staticmethod
    def _import_from_web(
        label: str, aspect: float | None = None
    ) -> tuple[dict[str, Any] | None, int, str]:
        """Text-only import: MuJoCo model text -> agent -> one sized primitive.

        The agent decides shape, size, density and colour; this method only
        writes what it decided into the asset record the twin watches. The rung
        stays 3 because a primitive is what lands in the scene — the difference
        from the old rung 3 is that its numbers now come from a real MuJoCo
        model instead of a guess, and the record says which one.
        """
        from integrations.brightdata import lookup  # noqa: PLC0415 — heavy import chain
        from integrations.object_agent import describe_object  # noqa: PLC0415

        catalog = lookup(label)
        if catalog.get("source") == "fixture" and "bottle" not in label.lower():
            # A bottle fixture is useful for offline bottle demos, but must not
            # pretend every unknown object has bottle dimensions.
            catalog = {
                **catalog,
                "name": label,
                "height_cm": None,
                "width_cm": None,
                "weight_g": None,
                "material": "plastic",
            }

        spec = describe_object(label, catalog, aspect=aspect)
        # The twin draws the object where the asset says, and the avoid step
        # names the same spot — one number, written once, or the arm routes
        # around empty air while the cylinder sits somewhere else.
        place_at = obstacle_xy(_current_steps())
        asset = save_primitive_asset(
            shape=spec.twin_shape,
            height_cm=spec.height_cm,
            width_cm=spec.width_cm,
            rgba=tuple(spec.rgba),
            label=label,
            source=f"mujoco_text:{spec.agent}",
            extra={
                "name": catalog.get("name", label),
                "material": spec.material,
                "density_kg_m3": spec.density_kg_m3,
                "density_source": f"mujoco_text:{spec.agent}",
                "agent": spec.agent,
                "agent_model": spec.agent_model,
                "mujoco_source": spec.mujoco_source,
                "mujoco_url": spec.mujoco_url,
                "reasoning": spec.reasoning,
                "confidence": spec.confidence,
                "docs_read": spec.docs_read,
                "geoms_read": spec.geoms_read,
                "pos_xy": list(place_at),
            },
        )
        origin = spec.mujoco_source or ("Port catalog" if spec.agent == "port_cache" else "the product catalog")
        detail = (
            f"Imported {label!r} as a {spec.twin_shape} "
            f"{spec.width_cm}x{spec.height_cm} cm from {origin}."
        )
        return {**asset, "spec": spec.as_json()}, 3, detail

    # --- readers ----------------------------------------------------------
    def state(self) -> dict[str, Any]:
        with self._lock:
            payload = self._state.as_json()
            payload["scanning"] = self._scanning
        payload["asset_path"] = str(ASSET_PATH)
        return payload

    @property
    def prompt_open(self) -> bool:
        with self._lock:
            return self._state.status == AWAITING


IMPORTER = ObjectImporter()


def _current_steps() -> list[Any]:
    """The running skill's steps, or [] when there is no spec on disk yet."""
    try:
        spec = json.loads(SPEC_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    steps = spec.get("steps")
    return steps if isinstance(steps, list) else []


def obstacle_xy(steps: list[Any]) -> tuple[float, float]:
    """Put the object where the arm would otherwise drive straight through.

    An imported obstacle is only an obstacle if it is in the way. The midpoint
    between where the skill picks up and where it puts down is exactly that
    spot, so avoidance is demonstrated rather than asserted — and the arm's
    home position at the origin is left clear.
    """
    waypoints = [
        list(step["at"])[:2]
        for step in steps
        if isinstance(step, dict) and step.get("op") in {"approach", "place"} and step.get("at")
    ]
    if len(waypoints) < 2:
        return OBSTACLE_XY
    first, last = waypoints[0], waypoints[-1]
    return (
        round((float(first[0]) + float(last[0])) / 2.0, 4),
        round((float(first[1]) + float(last[1])) / 2.0, 4),
    )


def add_avoid_step(asset: dict[str, Any], spec_path: Path | None = None) -> str:
    """Teach the running skill to route around the object that just landed.

    Importing geometry that the arm then drives straight through is a demo that
    contradicts itself, so the asset and the spec are updated together. An
    Re-importing replaces the obstacle rather than adding one: the twin has a
    single obstacle body, so a second avoid step would describe geometry that
    is not in the scene.
    """
    path = spec_path or SPEC_PATH
    if not asset:
        return ""
    try:
        spec = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return "no skill spec to add an avoid step to."
    steps = spec.get("steps")
    if not isinstance(steps, list):
        return "skill spec has no steps."

    at = obstacle_xy(steps)
    avoid = {
        "op": "avoid",
        "at": list(at),
        "geom": "cylinder" if str(asset.get("shape")) != "box" else "box",
        "width_cm": float(asset.get("width_cm") or 7.0),
        "height_cm": float(asset.get("height_cm") or 20.0),
        "material": str(asset.get("material") or "plastic"),
        "mesh_rung": int(asset.get("rung") or 3),
    }
    # Every existing avoid step goes, not just one at the same spot. The twin
    # carries exactly one obstacle body, so a second avoid step would describe
    # geometry that is not in the scene — and re-importing means the object
    # moved or changed size, never that there are now two of them.
    kept = [step for step in steps if not (isinstance(step, dict) and step.get("op") == "avoid")]
    spec = {"version": spec.get("version", 2), "steps": [*kept, avoid]}
    path.write_text(json.dumps(spec, indent=2) + "\n")
    return f"Placed at {at[0]:+.2f}, {at[1]:+.2f} m; the arm will route around it."
