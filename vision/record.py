"""Camera + record: press R to capture a physical prompt bag, then run the factory."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cv2

from factory.fast_path import run_fast_path
from integrations.config import load_settings
from integrations.signoz import tracer_ready
from vision import hud
from vision.recorder import PhysicalPromptRecorder, PromptState
from vision.track import build_tracker


def main() -> int:
    settings = load_settings()
    camera, tracker = build_tracker()
    recorder = PhysicalPromptRecorder(tracker)
    print("physical prompt recorder")
    print("  R = start/stop recording (3–12 s)")
    print("  F = run fast-path factory on last bag")
    print("  ESC / q = quit")
    print(f"  SigNoz: {tracer_ready()}")
    try:
        while True:
            result = tracker.step()
            if recorder.state is PromptState.RECORDING:
                recorder.sample(result)
            frame = hud.draw(result, prompt_state=recorder.state.value)
            if frame is not None:
                cv2.imshow("Bidex — record", frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            if key in (ord("r"), ord("R")):
                state = recorder.toggle(result)
                print(f"  prompt={state.value}")
                if state is PromptState.PROMPTED and recorder.last_bag_path:
                    factory = run_fast_path(Path(recorder.last_bag_path))
                    print(
                        f"  factory done in {factory.elapsed_ms} ms  |  "
                        f"replay={factory.replay.detail}  |  spec={factory.spec_path}"
                    )
            if key in (ord("f"), ord("F")) and recorder.last_bag_path:
                factory = run_fast_path(Path(recorder.last_bag_path), append=True)
                print(
                    f"  factory append in {factory.elapsed_ms} ms  |  "
                    f"replay={factory.replay.detail}"
                )
    finally:
        camera.close()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
