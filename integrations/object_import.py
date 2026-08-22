"""Ask before importing: the camera sees a box, the operator decides.

The bounding-box pass (``vision/detect.py``) finds an object the twin has no
geometry for. Pulling geometry for it means going out to the web through
Bright Data, which costs time and quota — so it is not automatic. This module
holds the one bit of state that makes it a conversation:

    detected -> AWAITING (frontend shows the prompt) -> operator answers
             -> IMPORTING (background thread) -> READY | FAILED
             or DISMISSED, and we stop asking about that label

Two import paths come out of the operator saying yes:

  * **The grey water bottle is hardcoded.** No search, no download, no Bright
    Data call: it drops a grey primitive cylinder at catalogue dimensions
    straight into the twin. The state carries ``hardcoded: true`` and
    ``rung: 3`` so the HUD says stub, not scrape — a demo shortcut that lies
    about its provenance is worse than no shortcut.
  * **Everything else runs the real ladder** (``factory.mesh_ladder.acquire``):
    Bright Data SERP over the 3D-asset web — MuJoCo Menagerie, Thingiverse,
    Printables, Sketchfab — then download, fit, and hot-swap into the scene.

Either way the twin picks the result up by watching ``outputs/mesh_asset.json``
mtime, so nothing here touches the running MuJoCo world directly.
"""

from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from factory.mesh_fit import ASSET_PATH, save_primitive_asset
from integrations.tracing import record_event, span
from vision.detect import Detection, matches_hardcoded

IDLE = "IDLE"
AWAITING = "AWAITING"
IMPORTING = "IMPORTING"
READY = "READY"
FAILED = "FAILED"
DISMISSED = "DISMISSED"

# What the stub bottle is, in centimetres. Same object the Bright Data fixture
# describes, so the hardcoded path and the scraped path agree on the geometry.
GRAY_BOTTLE = {
    "name": "IKEA 365+ water bottle (dark gray)",
    "height_cm": 20.0,
    "width_cm": 7.0,
    "weight_g": 120.0,
    "material": "plastic",
    "rgba": (0.42, 0.44, 0.47, 1.0),
}

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
    source: str | None = None       # "hardcoded_stub" | "brightdata" | None
    rung: int | None = None
    detail: str = ""
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

    # --- detection side ---------------------------------------------------
    def observe(self, detection: Detection | None) -> None:
        """Feed the newest bounding box in. Raises the prompt when it settles.

        Called every detector pass, so it must be cheap and must not re-prompt
        while an import is running or already answered.
        """
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
                detail=(
                    "Hardcoded demo object — imports as a grey primitive cylinder."
                    if detection.hardcoded
                    else "Bright Data will search the 3D-asset web (MuJoCo Menagerie, "
                         "Thingiverse, Printables, Sketchfab) for a matching mesh."
                ),
            )
        record_event(
            "import_prompt",
            label=detection.label,
            hardcoded=detection.hardcoded,
            confidence=round(detection.confidence, 2),
        )

    # --- operator side ----------------------------------------------------
    def decide(self, decision: str) -> dict[str, Any]:
        """``import`` or ``dismiss`` the pending prompt. Returns the new state."""
        decision = decision.lower().strip()
        with self._lock:
            if self._state.status != AWAITING:
                return self._state.as_json()
            label = self._state.label
            hardcoded = self._state.hardcoded
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
            self._state.source = "hardcoded_stub" if hardcoded else "brightdata"
            self._state.detail = (
                "Loading the grey cylinder stub…" if hardcoded
                else "Searching the 3D-asset web via Bright Data…"
            )
            bbox = list(self._state.bbox)

        record_event("import_decision", label=label, decision="import", hardcoded=hardcoded)
        self._thread = threading.Thread(
            target=self._run_import, args=(label, hardcoded, bbox),
            name="object-import", daemon=True,
        )
        self._thread.start()
        return self.state()

    def reset(self) -> dict[str, Any]:
        """Clear the banner and start listening for a new object."""
        with self._lock:
            self._state = ImportState()
            self._streak_label, self._streak = "", 0
        return self.state()

    # --- work -------------------------------------------------------------
    def _run_import(self, label: str, hardcoded: bool, bbox: list[int]) -> None:
        started = time.monotonic()
        with span("object_import", label=label, hardcoded=hardcoded):
            try:
                if hardcoded:
                    asset, rung, detail = self._import_hardcoded(label)
                else:
                    asset, rung, detail = self._import_from_web(label)
            except Exception as exc:  # noqa: BLE001 — a failed import must not kill the feed
                with self._lock:
                    self._state.status = FAILED
                    self._state.error = str(exc)
                    self._state.detail = "Import failed; the twin kept its current geometry."
                    self._state.elapsed_ms = round((time.monotonic() - started) * 1000, 1)
                record_event("import_result", label=label, ok=False, error=str(exc))
                return

        elapsed_ms = round((time.monotonic() - started) * 1000, 1)
        with self._lock:
            self._state.status = READY
            self._state.asset = asset
            self._state.rung = rung
            self._state.detail = detail
            self._state.bbox = bbox
            self._state.elapsed_ms = elapsed_ms
        record_event(
            "import_result", label=label, ok=True, rung=rung,
            source=(asset or {}).get("source"), elapsed_ms=elapsed_ms,
        )

    @staticmethod
    def _import_hardcoded(label: str) -> tuple[dict[str, Any], int, str]:
        """The demo shortcut: a grey cylinder at catalogue size, no network."""
        asset = save_primitive_asset(
            shape="cylinder",
            height_cm=float(GRAY_BOTTLE["height_cm"]),
            width_cm=float(GRAY_BOTTLE["width_cm"]),
            rgba=GRAY_BOTTLE["rgba"],
            weight_g=float(GRAY_BOTTLE["weight_g"]),
            label=label,
            source="hardcoded_stub",
            extra={"name": GRAY_BOTTLE["name"], "material": GRAY_BOTTLE["material"]},
        )
        return (
            asset,
            3,
            f"Loaded a grey {GRAY_BOTTLE['height_cm']:.0f} cm cylinder stub "
            f"(hardcoded — no mesh was downloaded).",
        )

    @staticmethod
    def _import_from_web(label: str) -> tuple[dict[str, Any] | None, int, str]:
        """The real path: scrape dimensions, then walk the mesh ladder."""
        from factory.mesh_ladder import acquire  # noqa: PLC0415 — heavy import chain
        from integrations.brightdata import lookup  # noqa: PLC0415

        catalog = lookup(label)
        result = acquire(label, catalog)
        if result.rung == 3:
            reason = result.reasons[0] if result.reasons else "no usable mesh on the web"
            raise RuntimeError(f"no mesh imported for {label!r}: {reason}")
        source = (result.asset or {}).get("source", "web")
        return result.asset, result.rung, f"Imported {result.label} from {source}."

    # --- readers ----------------------------------------------------------
    def state(self) -> dict[str, Any]:
        with self._lock:
            payload = self._state.as_json()
        payload["asset_path"] = str(ASSET_PATH)
        return payload

    @property
    def prompt_open(self) -> bool:
        with self._lock:
            return self._state.status == AWAITING


IMPORTER = ObjectImporter()
