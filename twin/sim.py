"""Open the live twin window. Camera + factory are not wired yet."""

from __future__ import annotations

import time
from pathlib import Path

import mujoco
import mujoco.viewer

from integrations.config import load_settings
from integrations.signoz import span, tracer_ready

SCENE = Path(__file__).with_name("scene.xml")


def _cube_xy(model: mujoco.MjModel, data: mujoco.MjData) -> tuple[float, float]:
    bid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "cube")
    pos = data.xpos[bid]
    return float(pos[0]), float(pos[1])


def main() -> None:
    settings = load_settings()
    model = mujoco.MjModel.from_xml_path(str(SCENE))
    data = mujoco.MjData(model)

    # Parked pose: arm reaches slightly over the table, not a skill.
    data.ctrl[:] = [0.35, -0.6, 0.0]

    tag_cm = settings.apriltag_size_cm or "?"
    print("twin running  |  prompt=IDLE  |  close the window to quit")
    print(f"tag size in .env: {tag_cm} cm  |  SigNoz tracer: {tracer_ready()}")

    last_log = 0.0
    with span("update_twin", prompt_state="IDLE"):
        pass

    with mujoco.viewer.launch_passive(model, data) as viewer:
        while viewer.is_running():
            step_start = time.time()
            mujoco.mj_step(model, data)
            viewer.sync()

            now = time.time()
            if now - last_log > 2.0:
                x, y = _cube_xy(model, data)
                print(f"  cube x={x:+.3f} y={y:+.3f}  t={data.time:.1f}s")
                last_log = now

            leftover = model.opt.timestep - (time.time() - step_start)
            if leftover > 0:
                time.sleep(leftover)


if __name__ == "__main__":
    main()
