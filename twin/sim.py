"""Open the live twin window.

Default: sim only. With --camera, track_cube runs: the AprilTag anchors the
table, the red blob is the cube, and the cube stays planted while you walk the
camera around. Factory (record → params → ship) is not wired yet.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mujoco
import mujoco.viewer
import numpy as np

from integrations.config import load_settings
from integrations.signoz import span, tracer_ready

SCENE = Path(__file__).with_name("scene.xml")
TABLE_TOP_Z = 0.76
CUBE_HALF = 0.025


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
        # Tag frame origin in world: the tag taped to the back-left of the table.
        self.origin = np.array(model.site_pos[site][:2], dtype=np.float64)
        # Table half-extents, so a bad frame cannot fling the cube off the world.
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
        # Kinematic while tracked: no leftover velocity to fight the camera.
        data.qvel[self._dof_adr : self._dof_adr + 6] = 0.0
        return float(xy[0]), float(xy[1])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera", action="store_true", help="run track_cube from the webcam")
    parser.add_argument("--no-hud", action="store_true", help="camera mode without the HUD window")
    args = parser.parse_args()

    settings = load_settings()
    model = mujoco.MjModel.from_xml_path(str(SCENE))
    data = mujoco.MjData(model)

    # Parked pose: arm reaches slightly over the table, not a skill.
    data.ctrl[:] = [0.35, -0.6, 0.0]

    tracker = None
    camera = None
    hud = None
    cv2 = None
    anchor = None
    if args.camera:
        import cv2 as _cv2  # noqa: PLC0415 — optional dependency, sim-only mode must still run

        from vision import hud as _hud
        from vision.track import build_tracker

        cv2, hud = _cv2, _hud
        camera, tracker = build_tracker()
        anchor = CubeAnchor(model)
        tracker.start()

    tag_cm = settings.apriltag_size_cm or "?"
    mode = "track_cube" if args.camera else "sim only"
    print(f"twin running  |  prompt=IDLE  |  {mode}  |  close the window to quit")
    print(f"tag size in .env: {tag_cm} cm  |  SigNoz tracer: {tracer_ready()}")

    last_log = 0.0
    with span("update_twin", prompt_state="IDLE"):
        pass

    try:
        with mujoco.viewer.launch_passive(model, data) as viewer:
            while viewer.is_running():
                step_start = time.time()

                result = tracker.latest if tracker is not None else None
                if result is not None and result.cube_xy is not None and anchor is not None:
                    anchor.apply(data, result.cube_xy)

                mujoco.mj_step(model, data)
                viewer.sync()

                if hud is not None and result is not None and not args.no_hud:
                    frame = hud.draw(result)
                    if frame is not None:
                        cv2.imshow("ScaleTwin — track_cube", frame)
                        cv2.waitKey(1)

                now = time.time()
                if now - last_log > 2.0:
                    x, y = _cube_xy(model, data)
                    if result is not None:
                        seen = "yes" if result.tag_seen else "no"
                        print(
                            f"  cube x={x:+.3f} y={y:+.3f}  tag={seen}  "
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
        if cv2 is not None:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
