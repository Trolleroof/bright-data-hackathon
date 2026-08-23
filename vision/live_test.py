"""Small contract check for browser-triggered Skill A/B recording."""

from vision.live import LiveCamera
from vision.recorder import PromptState


class _Recorder:
    state = PromptState.IDLE
    last_bag_path = None

    def start(self):
        self.state = PromptState.RECORDING
        return self.state

    def stop(self, _result):
        self.state = PromptState.PROMPTED
        self.last_bag_path = "recordings/bag_test.json"
        return self.state


def main() -> None:
    camera = LiveCamera()
    camera._recorder, camera._latest = _Recorder(), object()  # browser path; no webcam needed
    factory_calls = []

    def start_factory(*args):
        # The bag must be consumed before the factory is launched; otherwise
        # the capture loop can launch the same run a second time.
        assert camera._recorder.last_bag_path is None
        factory_calls.append(args)

    camera._start_factory = start_factory
    assert camera.toggle_recording("A") == ("RECORDING", None, "A")
    assert camera.toggle_recording("B") == ("PROMPTED", "recordings/bag_test.json", "A")
    assert factory_calls == [("recordings/bag_test.json", "A")]
    print("live recording toggle: PASS")


if __name__ == "__main__":
    main()
