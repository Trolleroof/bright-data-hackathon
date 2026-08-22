"""Open the live twin window.

Default: sim only. With --camera, track_cube runs: the AprilTag anchors the
table, the red blob is the cube, and the cube stays planted while you walk the
camera around. Keys in this terminal (not the MuJoCo window):

  R  start/stop recording (~3–12 s pick-and-place) → fast-path factory on stop
  F  append avoid step from last bag (Run B)
  S  approve + run the skill spec in sim
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from contextlib import nullcontext
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mujoco
import mujoco.viewer
import numpy as np

from engine.runner import Runner, Setpoint
from engine.spec import SpecError, load
from factory.mesh_fit import load_asset
from integrations.config import load_settings
from integrations.tracing import record_event, span, tracer_ready
from twin.world import resolve_scene, rung_label

SCENE = Path(__file__).with_name("scene.xml")
TABLE_TOP_Z = 0.76
CUBE_HALF = 0.025
HUD_W, HUD_H = 480, 270
LETTER_TAG_CM = 15.3


def _cube_xy(model: mujoco.MjModel, data: mujoco.MjData) -> tuple[float, float]:
    bid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "cube")
    pos = data.xpos[bid]
    return float(pos[0]), float(pos[1])


class CubeAnchor:
    """Writes a table-frame x,y onto the cube's free joint, kept on the table."""

    def __init__(self, model: mujoco.MjModel) -> None:
        joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "cube_free")
        self._qpos_adr = int(model.jnt_qposadr[joint])
        self._dof_adr = int(model.jnt_dofadr[joint])
        site = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, "tag_origin")
        self.origin = np.array(model.site_pos[site][:2], dtype=np.float64)
        tabletop = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "tabletop")
        self._limit = np.array(model.geom_size[tabletop][:2], dtype=np.float64) - CUBE_HALF

    def world_xy(self, tag_xy: tuple[float, float]) -> np.ndarray:
        xy = self.origin + np.array(tag_xy, dtype=np.float64)
        return np.clip(xy, -self._limit, self._limit)

    def apply(self, data: mujoco.MjData, tag_xy: tuple[float, float]) -> tuple[float, float]:
        xy = self.world_xy(tag_xy)
        a = self._qpos_adr
        data.qpos[a : a + 2] = xy
        data.qpos[a + 2] = TABLE_TOP_Z + CUBE_HALF
        data.qpos[a + 3 : a + 7] = (1.0, 0.0, 0.0, 0.0)
        data.qvel[self._dof_adr : self._dof_adr + 6] = 0.0
        return float(xy[0]), float(xy[1])


class SkillDriver:
    """Drive the real SO-101 gripper to each table-frame skill setpoint."""

    def __init__(self, model: mujoco.MjModel) -> None:
        joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "cube_free")
        self._cube_qpos = int(model.jnt_qposadr[joint])
        self._cube_dof = int(model.jnt_dofadr[joint])
        self._cursor = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, "skill_ee")
        self._ee = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, "gripperframe")
        self._arm_joints = [
            mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
            for name in ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll")
        ]
        self._arm_qpos = [int(model.jnt_qposadr[joint]) for joint in self._arm_joints]
        self._arm_dof = [int(model.jnt_dofadr[joint]) for joint in self._arm_joints]
        self._gripper = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, "gripper")
        # Keep the visual arm from shoving a released cube; the table still
        # collides with it and keeps it on the tabletop.
        robot_geoms = np.flatnonzero(model.geom_group == 3)
        model.geom_contype[robot_geoms] = 2
        model.geom_conaffinity[robot_geoms] = 2
        self._obstacle_body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "obstacle")
        self._obstacle_geom = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "obstacle_geom")
        self._obstacle_qpos = int(
            model.jnt_qposadr[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "obstacle_free")]
        )

    def _obstacle(self, model: mujoco.MjModel, data: mujoco.MjData, obstacle: dict[str, object] | None) -> None:
        if obstacle is None:
            return
        x, y = obstacle["at"]
        q = self._obstacle_qpos
        data.qpos[q : q + 3] = (x, y, TABLE_TOP_Z + float(obstacle["height_m"]) / 2)
        data.qpos[q + 3 : q + 7] = (1.0, 0.0, 0.0, 0.0)
        # A mesh obstacle was already scaled to the measured size on disk, and
        # geom_size means nothing for a mesh geom — only the primitive resizes.
        # Ask the compiled model, not the spec: the two disagree whenever the
        # asset the spec was written against is no longer the one we loaded.
        is_mesh = int(model.geom_type[self._obstacle_geom]) == int(mujoco.mjtGeom.mjGEOM_MESH)
        if not is_mesh:
            model.geom_size[self._obstacle_geom][:2] = (float(obstacle["width_m"]) / 2, float(obstacle["height_m"]) / 2)
        model.geom_friction[self._obstacle_geom][0] = float(obstacle["friction"])
        if obstacle["mass_kg"] is not None:
            model.body_mass[self._obstacle_body] = float(obstacle["mass_kg"])
        mujoco.mj_setConst(model, data)

    def _cube(self, data: mujoco.MjData, x: float, y: float, z: float) -> None:
        a = self._cube_qpos
        data.qpos[a : a + 3] = (x, y, TABLE_TOP_Z + z + CUBE_HALF)
        data.qpos[a + 3 : a + 7] = (1.0, 0.0, 0.0, 0.0)
        data.qvel[self._cube_dof : self._cube_dof + 6] = 0.0

    def reset_cube(self, data: mujoco.MjData, xy: tuple[float, float]) -> None:
        self._cube(data, *xy, 0.0)

    def apply(self, model: mujoco.MjModel, data: mujoco.MjData, setpoint: Setpoint) -> None:
        target = np.array((setpoint.x, setpoint.y, TABLE_TOP_Z + setpoint.z + CUBE_HALF))
        model.site_pos[self._cursor] = target
        mujoco.mj_forward(model, data)
        jac = np.zeros((3, model.nv))
        for _ in range(8):
            mujoco.mj_jacSite(model, data, jac, None, self._ee)
            error = target - data.site_xpos[self._ee]
            if np.linalg.norm(error) < 1e-4:
                break
            arm_jac = jac[:, self._arm_dof]
            delta = arm_jac.T @ np.linalg.solve(
                arm_jac @ arm_jac.T + 1e-5 * np.eye(3), error * 0.8
            )
            for qpos, step, joint in zip(self._arm_qpos, np.clip(delta, -0.08, 0.08), self._arm_joints):
                data.qpos[qpos] = np.clip(
                    data.qpos[qpos] + step, model.jnt_range[joint, 0], model.jnt_range[joint, 1]
                )
            mujoco.mj_forward(model, data)
        data.ctrl[:5] = data.qpos[self._arm_qpos]
        data.ctrl[self._gripper] = 0.0 if setpoint.attached else 0.35
        self._obstacle(model, data, setpoint.obstacle)
        if setpoint.attached or setpoint.op in {"replay_trajectory", "goto"}:
            self._cube(data, setpoint.x, setpoint.y, setpoint.z)
        mujoco.mj_forward(model, data)


def _size_tag_to_env(model: mujoco.MjModel, tag_size_m: float) -> None:
    if tag_size_m <= 0:
        return
    geom = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "apriltag")
    model.geom_size[geom][0] = tag_size_m / 2.0
    model.geom_size[geom][1] = tag_size_m / 2.0


def _overlay(
    viewer,
    result,
    world_xy: tuple[float, float] | None,
    tag_cm: str,
    hud,
    cv2,
    *,
    prompt_state: str = "IDLE",
    factory_busy: bool = False,
    geometry: str = "rung 3: primitive cylinder",
) -> None:
    tag = "YES" if result.tag_seen else "NO"
    cube = f"{world_xy[0]:+.3f}  {world_xy[1]:+.3f}" if world_xy else "--"
    raw = (
        f"{result.cube_xy[0]:+.3f}  {result.cube_xy[1]:+.3f}"
        if result.cube_xy
        else "--"
    )
    factory_line = "busy" if factory_busy else "idle"
    viewer.set_texts(
        (
            mujoco.mjtFontScale.mjFONTSCALE_150,
            mujoco.mjtGridPos.mjGRID_TOPLEFT,
            "prompt\nfactory\ngeom\ntag\ncube world\ncube tag\nscale\nlatency",
            f"{prompt_state}\n{factory_line}\n{geometry}\n{tag}\n{cube}\n{raw}\n"
            f"{tag_cm} cm\n{result.latency_ms:.0f} ms",
        )
    )
    if result.frame is None or cv2 is None:
        return
    frame = hud.draw(result, prompt_state=prompt_state)
    if frame is None:
        return
    rgb = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), (HUD_W, HUD_H))
    viewer.set_images((mujoco.MjrRect(16, 16, HUD_W, HUD_H), rgb))


def _start_skill(
    model: mujoco.MjModel, data: mujoco.MjData, spec_path: Path
) -> tuple[Runner, SkillDriver] | tuple[None, None]:
    if not spec_path.exists():
        print(f"  no spec at {spec_path}; record a prompt first (R)")
        return None, None
    try:
        spec = load(spec_path)
        driver = SkillDriver(model)
        first_approach = next((step for step in spec.steps if step["op"] == "approach"), None)
        if first_approach is not None:
            driver.reset_cube(data, tuple(first_approach["at"]))
            mujoco.mj_forward(model, data)
        return Runner(spec, spec_path), driver
    except SpecError as exc:
        print(f"  skill spec rejected: {exc}")
        return None, None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera", action="store_true", help="track_cube + record + factory from the webcam")
    parser.add_argument("--skill", action="store_true", help="run outputs/skill_spec.json (no camera)")
    parser.add_argument("--spec", type=Path, default=ROOT / "outputs" / "skill_spec.json")
    args = parser.parse_args()

    settings = load_settings()
    # A native viewer holds one compiled model for its lifetime, and MuJoCo
    # compiles meshes in, so the rung is fixed at launch here. The web twin
    # (twin/live.py) rebuilds and carries state across, which is the live swap.
    mesh_asset = load_asset()
    scene, mesh_asset = resolve_scene(mesh_asset)
    model = mujoco.MjModel.from_xml_path(str(scene))
    _size_tag_to_env(model, settings.apriltag_size_m)
    data = mujoco.MjData(model)
    data.ctrl[:] = 0.0

    runner: Runner | None = None
    driver: SkillDriver | None = None
    skill_active = False
    if args.skill and not args.camera:
        runner, driver = _start_skill(model, data, args.spec)
        if runner is None:
            raise SystemExit(1)
        skill_active = True

    tracker = None
    camera = None
    hud = None
    cv2 = None
    anchor = None
    recorder = None
    if args.camera:
        import cv2 as _cv2  # noqa: PLC0415

        from factory.fast_path import run_fast_path
        from vision import hud as _hud
        from vision.keys import poll, raw_stdin
        from vision.recorder import PhysicalPromptRecorder, PromptState
        from vision.track import build_tracker

        cv2, hud = _cv2, _hud
        camera, tracker = build_tracker()
        anchor = CubeAnchor(model)
        recorder = PhysicalPromptRecorder(tracker)
        tracker.start()
    else:
        run_fast_path = None  # type: ignore[assignment,misc]
        poll = raw_stdin = None  # type: ignore[assignment,misc]
        PromptState = None  # type: ignore[assignment,misc]

    tag_cm = settings.apriltag_size_cm or "?"
    if args.camera:
        mode = "track_cube + record"
    elif args.skill:
        mode = "skill engine"
    else:
        mode = "sim only"
    print(f"twin running  |  {mode}  |  close the MuJoCo window to quit")
    print(f"tag size in .env: {tag_cm} cm  |  tracer: {tracer_ready()}")
    print(f"obstacle geometry: {rung_label(mesh_asset)}")
    if args.camera:
        print("  keys in THIS terminal: R = record  |  F = factory append  |  S = run skill")
    try:
        configured = float(settings.apriltag_size_cm)
    except ValueError:
        configured = 0.0
    if args.camera and configured and abs(configured - LETTER_TAG_CM) > 2.0:
        print(
            f"  scale warning: letter print at 100% is {LETTER_TAG_CM} cm; "
            f".env has {configured} cm"
        )

    last_log = 0.0
    hud_ok = hud is not None
    factory_busy = False
    factory_lock = threading.Lock()
    last_replay_passed = False

    def _factory_done(result) -> None:
        nonlocal factory_busy, last_replay_passed
        with factory_lock:
            factory_busy = False
            last_replay_passed = result.replay.passed
        print(
            f"  factory done in {result.elapsed_ms} ms  |  replay={result.replay.detail}  |  "
            f"spec={result.spec_path.name}"
        )
        if result.mesh:
            print(f"  mesh: {result.mesh.label}" + (f" ({'; '.join(result.mesh.reasons)})" if result.mesh.reasons else ""))
            if result.mesh.rung < 3:
                print("  restart the twin to load it (the web twin swaps it live)")
        if result.catalog:
            print(
                f"  scrape: {result.catalog.get('name')} "
                f"{result.catalog.get('width_cm')}x{result.catalog.get('height_cm')} cm"
            )
        with span("approve", gate="fast_path_auto_approval", operator="auto"):
            if result.replay.passed:
                record_event(
                    "release",
                    hot_swap=True,
                    zero_downtime=True,
                    spec_version=2,
                    source="twin_factory",
                    status="ZERO_DOWNTIME",
                )
        print("  press S to run the skill (walk the camera meanwhile)")

    def _run_factory(bag_path: Path, *, append: bool = False) -> None:
        nonlocal factory_busy
        with factory_lock:
            if factory_busy:
                print("  factory already running")
                return
            factory_busy = True
        print(f"  factory started  |  bag={bag_path.name}  |  append={append}", flush=True)

        def _work() -> None:
            nonlocal factory_busy
            try:
                result = run_fast_path(bag_path, args.spec, append=append)
            except Exception as exc:  # noqa: BLE001
                with factory_lock:
                    factory_busy = False
                print(f"  factory failed: {exc}")
                return
            _factory_done(result)

        threading.Thread(target=_work, name="bidex-factory", daemon=True).start()

    with span("update_twin", prompt_state="IDLE"):
        pass

    stdin_ctx = raw_stdin() if args.camera else nullcontext()
    try:
        with stdin_ctx, mujoco.viewer.launch_passive(model, data) as viewer:
            while viewer.is_running():
                step_start = time.time()

                result = tracker.latest if tracker is not None else None
                prompt_state = recorder.state.value if recorder is not None else "IDLE"
                world_xy = None
                tracking = (
                    args.camera
                    and anchor is not None
                    and result is not None
                    and (not skill_active or (runner is not None and runner.finished))
                )
                if tracking and result.cube_xy is not None:
                    world_xy = anchor.apply(data, result.cube_xy)

                if recorder is not None and result is not None and recorder.state is PromptState.RECORDING:
                    recorder.sample(result)

                if runner is not None and driver is not None and skill_active and not runner.finished:
                    setpoint = runner.tick(data.time)
                    if setpoint is not None:
                        driver.apply(model, data, setpoint)
                    if runner.finished:
                        skill_active = False
                        print("  skill complete — back to track_cube")
                    try:
                        if runner.reload_if_changed():
                            print("skill spec reloaded")
                            with span("patch_spec", hot_swap=True, spec_version=2):
                                record_event(
                                    "release",
                                    hot_swap=True,
                                    zero_downtime=True,
                                    spec_version=2,
                                    source="twin_hot_swap",
                                    status="ZERO_DOWNTIME",
                                )
                    except SpecError as exc:
                        print(f"skill spec rejected; keeping current skill: {exc}")

                if args.camera and poll is not None:
                    key = poll(use_cv2=False)
                    if key in (ord("r"), ord("R")) and recorder is not None and result is not None:
                        state = recorder.toggle(result)
                        print(f"  prompt={state.value}")
                        if state is PromptState.PROMPTED and recorder.last_bag_path:
                            _run_factory(Path(recorder.last_bag_path))
                    elif key in (ord("f"), ord("F")) and recorder is not None and recorder.last_bag_path:
                        _run_factory(Path(recorder.last_bag_path), append=True)
                    elif key in (ord("s"), ord("S")):
                        if not last_replay_passed and not args.spec.exists():
                            print("  record a prompt first (R), wait for factory PASS, then S")
                        else:
                            runner, driver = _start_skill(model, data, args.spec)
                            if runner is not None:
                                skill_active = True
                                print("  skill running")
                                with span("skill_exec", spec_path=str(args.spec), source="twin_key"):
                                    pass

                mujoco.mj_step(model, data)
                if result is not None and hud is not None:
                    try:
                        with factory_lock:
                            busy = factory_busy
                        _overlay(
                            viewer,
                            result,
                            world_xy,
                            tag_cm,
                            hud,
                            cv2,
                            prompt_state=prompt_state,
                            factory_busy=busy,
                            geometry=rung_label(mesh_asset),
                        )
                    except Exception as exc:  # noqa: BLE001
                        if hud_ok:
                            print(f"  overlay skipped: {exc}")
                            hud_ok = False
                viewer.sync()

                now = time.time()
                if now - last_log > 2.0:
                    x, y = _cube_xy(model, data)
                    if result is not None:
                        seen = "yes" if result.tag_seen else "no"
                        print(
                            f"  cube x={x:+.3f} y={y:+.3f}  tag={seen}  prompt={prompt_state}  "
                            f"{result.latency_ms:.1f} ms  {result.fps:.1f} fps"
                        )
                    else:
                        print(f"  cube x={x:+.3f} y={y:+.3f}  t={data.time:.1f}s")
                    last_log = now

                leftover = model.opt.timestep - (time.time() - step_start)
                if leftover > 0:
                    time.sleep(leftover)
    finally:
        if tracker is not None:
            tracker.stop()
        if camera is not None:
            camera.close()


if __name__ == "__main__":
    main()
