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
from integrations.tracing import tracer_ready
from vision import hud
from vision.keys import is_quit, poll, raw_stdin
from vision.recorder import PhysicalPromptRecorder, PromptState
from vision.track import build_tracker


def main() -> int:
    settings = load_settings()
    camera, tracker = build_tracker()
    recorder = PhysicalPromptRecorder(tracker)
    last_catalog: dict | None = None
    print("physical prompt recorder")
    print("  R = start/stop recording (3–20 s)")
    print("  F = run fast-path factory on last bag")
    print("  ESC / q = quit (HUD window or this terminal)")
    print(f"  tracer: {tracer_ready()}")
    try:
        with raw_stdin():
            while True:
                result = tracker.step()
                if recorder.state is PromptState.RECORDING:
                    recorder.sample(result)
                frame = hud.draw(result, prompt_state=recorder.state.value, catalog=last_catalog)
                if frame is not None:
                    cv2.imshow("Bidex — record", frame)
                key = poll()
                if is_quit(key):
                    break
                if key in (ord("r"), ord("R")):
                    state = recorder.toggle(result)
                    print(f"  prompt={state.value}")
                    if state is PromptState.PROMPTED and recorder.last_bag_path:
                        factory = run_fast_path(Path(recorder.last_bag_path))
                        if factory.catalog is not None:
                            last_catalog = factory.catalog
                        print(
                            f"  factory done in {factory.elapsed_ms} ms  |  "
                            f"replay={factory.replay.detail}  |  spec={factory.spec_path}"
                        )
                if key in (ord("f"), ord("F")) and recorder.last_bag_path:
                    factory = run_fast_path(Path(recorder.last_bag_path), append=True)
                    if factory.catalog is not None:
                        last_catalog = factory.catalog
                    print(
                        f"  factory append in {factory.elapsed_ms} ms  |  "
                        f"replay={factory.replay.detail}"
                    )
    except KeyboardInterrupt:
        print()
    finally:
        camera.close()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
