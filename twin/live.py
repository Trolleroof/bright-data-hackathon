"""The twin, headless, rendered to JPEG for the browser.

`python -m twin.sim` opens a native MuJoCo viewer — great on the demo laptop,
invisible to the web UI. This runs the same model, the same CubeAnchor and the
same SkillDriver in a background thread and renders offscreen instead, so the
frontend can show the twin next to the camera feed and the trace waterfall.

Sources of cube motion, one at a time:
  * ``camera`` — track_cube writes the camera's table-frame x,y onto the cube
  * ``skill``  — the primitive engine replays ``outputs/skill_spec.json``
  * ``idle``   — physics only
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import mujoco

from engine.runner import Runner
from engine.spec import SpecError, load
from factory.mesh_fit import ASSET_PATH, load_asset
from integrations.tracing import record_event, span
from twin.sim import CubeAnchor, SkillDriver, _cube_xy
from twin.world import resolve_scene, rung_label
from vision.live import CAMERA

ROOT = Path(__file__).resolve().parent.parent
SCENE = Path(__file__).with_name("scene.xml")
DEFAULT_SPEC = ROOT / "outputs" / "skill_spec.json"

VIEWS: dict[str, dict[str, float]] = {
    "operator": {"azimuth": 135.0, "elevation": -22.0, "distance": 1.5},
    "overhead": {"azimuth": 90.0, "elevation": -85.0, "distance": 1.2},
    "front": {"azimuth": 90.0, "elevation": -15.0, "distance": 1.6},
    "wide": {"azimuth": 160.0, "elevation": -30.0, "distance": 2.1},
}
LOOKAT = (0.0, 0.05, 0.80)

# Run A default: pick at the cube start, place on the taped target square.
SEED_SPEC = {
    "version": 2,
    "steps": [
        {"op": "approach", "at": [0.0, 0.0], "height_cm": 8, "duration_s": 0.8},
        {"op": "approach", "at": [0.0, 0.0], "height_cm": 2.5, "duration_s": 0.5},
        {"op": "grasp"},
        {"op": "place", "at": [0.12, 0.08, 0], "duration_s": 1.2},
        {"op": "release"},
        {"op": "approach", "at": [0.12, 0.08], "height_cm": 8, "duration_s": 0.5},
    ],
}


@dataclass
class TwinState:
    running: bool = False
    error: str | None = None
    source: str = "idle"
    view: str = "operator"
    sim_time: float = 0.0
    cube_xy: tuple[float, float] = (0.0, 0.0)
    ee_xyz: tuple[float, float, float] | None = None
    skill_op: str | None = None
    skill_step: int = 0
    skill_steps: int = 0
    skill_finished: bool = False
    spec_version: int | None = None
    hot_swaps: int = 0
    mesh_rung: int = 3
    mesh_label: str = "rung 3: primitive cylinder"
    mesh_source: str | None = None
    mesh_swaps: int = 0
    render_fps: float = 0.0
    frames: int = 0

    def as_json(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["cube_xy"] = list(self.cube_xy)
        payload["ee_xyz"] = list(self.ee_xyz) if self.ee_xyz else None
        return payload


class LiveTwin:
    """One MuJoCo world, stepped and rendered on its own thread."""

    def __init__(self, width: int = 960, height: int = 640) -> None:
        self.width = width
        self.height = height
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._jpeg: bytes | None = None
        self._state = TwinState()
        self._source = "idle"
        self._view = "operator"
        self._spec_path = DEFAULT_SPEC
        self._reset_requested = threading.Event()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # --- lifecycle -------------------------------------------------------
    def start(self, source: str | None = None, view: str | None = None) -> dict[str, Any]:
        if source is not None:
            self._source = source if source in {"idle", "camera", "skill"} else "idle"
        if view is not None and view in VIEWS:
            self._view = view
        with self._lock:
            if self.running:
                self._state.source = self._source
                self._state.view = self._view
                return self._state.as_json()
            self._stop.clear()
            self._state = TwinState(running=True, source=self._source, view=self._view)
            self._thread = threading.Thread(target=self._loop, name="live-twin", daemon=True)
            self._thread.start()
        return self.state()

    def stop(self) -> dict[str, Any]:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=3.0)
        self._thread = None
        with self._lock:
            self._state.running = False
        return self.state()

    def configure(self, source: str | None = None, view: str | None = None) -> dict[str, Any]:
        """Change the cube source or the render camera without dropping the world."""
        if source in {"idle", "camera", "skill"}:
            self._source = source
            self._reset_requested.set()
        if view in VIEWS:
            self._view = view
        if not self.running:
            return self.start()
        with self._lock:
            self._state.source = self._source
            self._state.view = self._view
        return self.state()

    def reset(self) -> dict[str, Any]:
        self._reset_requested.set()
        return self.state()

    # --- world -----------------------------------------------------------
    def _build_world(self, asset: dict[str, Any] | None):
        """Compile the scene for the current geometry rung.

        MuJoCo compiles meshes into the model, so a new mesh means a new model.
        Everything the loop holds is rebuilt around it.
        """
        scene, effective = resolve_scene(asset)
        model = mujoco.MjModel.from_xml_path(str(scene))
        data = mujoco.MjData(model)
        renderer = mujoco.Renderer(model, self.height, self.width)
        # `effective` is None when the rewrite fell back to the primitive, so
        # the HUD label always matches the model MuJoCo actually compiled.
        return model, data, CubeAnchor(model), SkillDriver(model), renderer, effective

    @staticmethod
    def _asset_stamp() -> int:
        try:
            return ASSET_PATH.stat().st_mtime_ns
        except OSError:
            return 0

    # --- loop ------------------------------------------------------------
    def _loop(self) -> None:
        import cv2  # noqa: PLC0415 — encoding is only needed while streaming

        mesh_asset = load_asset()
        mesh_stamp = self._asset_stamp()
        mesh_swaps = 0
        next_mesh_check = 0.0
        try:
            model, data, anchor, driver, renderer, mesh_asset = self._build_world(mesh_asset)
        except Exception as exc:  # noqa: BLE001 — a broken scene must not 500 the UI
            with self._lock:
                self._state = TwinState(running=False, error=f"scene: {exc}")
            return

        cam = mujoco.MjvCamera()
        cam.lookat[:] = LOOKAT

        runner = self._load_runner()
        hot_swaps = 0
        frames = 0
        last_render = 0.0
        render_fps = 0.0
        render_period = 1.0 / 25.0

        try:
            while not self._stop.is_set():
                step_start = time.time()

                # The mesh ladder writes outputs/mesh_asset.json when it finds
                # real geometry. Swap it in without dropping the world: same
                # joints, same qpos, new obstacle. The viewer never stops.
                if step_start >= next_mesh_check:
                    next_mesh_check = step_start + 1.0
                    stamp = self._asset_stamp()
                    if stamp != mesh_stamp:
                        mesh_stamp = stamp
                        candidate = load_asset()
                        try:
                            new_world = self._build_world(candidate)
                        except Exception as exc:  # noqa: BLE001 — keep the old world
                            with self._lock:
                                self._state.error = f"mesh swap rejected: {exc}"
                        else:
                            qpos, qvel, sim_time = data.qpos.copy(), data.qvel.copy(), data.time
                            renderer.close()
                            model, data, anchor, driver, renderer, candidate = new_world
                            if qpos.shape == data.qpos.shape:
                                data.qpos[:] = qpos
                                data.qvel[:] = qvel
                                data.time = sim_time
                            mujoco.mj_forward(model, data)
                            mesh_asset = candidate
                            with self._lock:
                                # A later good swap clears an earlier rejection;
                                # otherwise the banner sticks for the whole run.
                                if str(self._state.error or "").startswith("mesh swap rejected"):
                                    self._state.error = None
                            mesh_swaps += 1
                            with span("mesh_swap", rung=(candidate or {}).get("rung", 3)):
                                record_event(
                                    "release",
                                    hot_swap=True,
                                    zero_downtime=True,
                                    source="live_twin_mesh_swap",
                                    geometry=rung_label(mesh_asset),
                                    status="ZERO_DOWNTIME",
                                )

                if self._reset_requested.is_set():
                    self._reset_requested.clear()
                    mujoco.mj_resetData(model, data)
                    runner = self._load_runner()

                source = self._source
                setpoint = None

                if source == "camera":
                    tracker = CAMERA.tracker
                    result = tracker.latest if tracker is not None else None
                    if result is not None and result.tag_seen and result.cube_xy is not None:
                        anchor.apply(data, result.cube_xy)
                elif source == "skill" and runner is not None:
                    if not runner.finished:
                        setpoint = runner.tick(data.time)
                        if setpoint is not None:
                            driver.apply(model, data, setpoint)
                    try:
                        if runner.reload_if_changed():
                            hot_swaps += 1
                            version = getattr(runner.spec, "version", 2)
                            with span("patch_spec", hot_swap=True, spec_version=version):
                                record_event(
                                    "release",
                                    hot_swap=True,
                                    zero_downtime=True,
                                    spec_version=version,
                                    source="live_twin_hot_swap",
                                    status="ZERO_DOWNTIME",
                                )
                    except SpecError as exc:
                        with self._lock:
                            self._state.error = f"spec rejected: {exc}"

                mujoco.mj_step(model, data)

                now = time.time()
                if now - last_render >= render_period:
                    preset = VIEWS.get(self._view, VIEWS["operator"])
                    cam.azimuth = preset["azimuth"]
                    cam.elevation = preset["elevation"]
                    cam.distance = preset["distance"]
                    cam.lookat[:] = LOOKAT
                    renderer.update_scene(data, camera=cam)
                    pixels = renderer.render()
                    ok, buf = cv2.imencode(
                        ".jpg", pixels[:, :, ::-1], [int(cv2.IMWRITE_JPEG_QUALITY), 80]
                    )
                    if ok:
                        frames += 1
                        render_fps = 1.0 / (now - last_render) if last_render else 0.0
                        with self._lock:
                            self._jpeg = buf.tobytes()
                    last_render = now

                    x, y = _cube_xy(model, data)
                    with self._lock:
                        self._state = TwinState(
                            running=True,
                            error=self._state.error,
                            source=source,
                            view=self._view,
                            sim_time=float(data.time),
                            cube_xy=(x, y),
                            ee_xyz=(setpoint.x, setpoint.y, setpoint.z) if setpoint else None,
                            skill_op=setpoint.op if setpoint else None,
                            skill_step=self._runner_index(runner),
                            skill_steps=len(runner.spec.steps) if runner else 0,
                            skill_finished=bool(runner.finished) if runner else False,
                            spec_version=getattr(runner.spec, "version", 2) if runner else None,
                            hot_swaps=hot_swaps,
                            mesh_rung=int(mesh_asset["rung"]) if mesh_asset else 3,
                            mesh_label=rung_label(mesh_asset),
                            mesh_source=mesh_asset.get("source") if mesh_asset else None,
                            mesh_swaps=mesh_swaps,
                            render_fps=render_fps,
                            frames=frames,
                        )

                leftover = model.opt.timestep - (time.time() - step_start)
                if leftover > 0:
                    time.sleep(leftover)
        finally:
            renderer.close()
            with self._lock:
                self._state.running = False

    def _load_runner(self) -> Runner | None:
        """The watched spec, seeded with the plan's Run A recipe if absent.

        ``outputs/`` is gitignored, so a fresh clone has no spec at all. Seeding
        one means the skill view has something to show before the factory has
        ever run, and the file stays hot-swappable exactly as before.
        """
        try:
            if not self._spec_path.exists():
                self._spec_path.parent.mkdir(parents=True, exist_ok=True)
                self._spec_path.write_text(json.dumps(SEED_SPEC, indent=2) + "\n")
            return Runner(load(self._spec_path), self._spec_path)
        except (SpecError, OSError) as exc:
            with self._lock:
                self._state.error = f"skill spec unavailable: {exc}"
            return None

    @staticmethod
    def _runner_index(runner: Runner | None) -> int:
        return int(getattr(runner, "_index", 0)) if runner is not None else 0

    # --- readers ---------------------------------------------------------
    def frame_jpeg(self) -> bytes | None:
        with self._lock:
            return self._jpeg

    def state(self) -> dict[str, Any]:
        with self._lock:
            payload = self._state.as_json()
        payload["views"] = sorted(VIEWS)
        payload["spec_path"] = str(self._spec_path)
        return payload


TWIN = LiveTwin()
