"""Scanning is opt-in: nothing is proposed until the operator asks."""

from integrations.object_import import AWAITING, DISMISSED, IDLE, ObjectImporter
from vision.detect import Detection

BOX = Detection("red box", (283, 0, 254, 240), 5000.0, 0.9, 0.62, False)


def _settle(importer: ObjectImporter, times: int = 10) -> str:
    for _ in range(times):
        importer.observe(BOX)
    return importer.state()["status"]


def test_a_fresh_importer_scans_for_nothing() -> None:
    importer = ObjectImporter()
    assert importer.state()["scanning"] is False
    assert _settle(importer) == IDLE, "an unasked-for prompt is worse than no feature"


def test_scanning_has_to_be_asked_for() -> None:
    importer = ObjectImporter()
    importer.set_scanning(True)
    assert _settle(importer) == AWAITING


def test_answering_a_prompt_ends_the_scan() -> None:
    """One request, one object: the banner must not come back on its own."""
    importer = ObjectImporter()
    importer.set_scanning(True)
    _settle(importer)
    importer.decide("dismiss")
    assert importer.state()["scanning"] is False
    assert _settle(importer) == DISMISSED


def test_stopping_mid_scan_clears_a_pending_prompt() -> None:
    importer = ObjectImporter()
    importer.set_scanning(True)
    _settle(importer)
    assert importer.set_scanning(False)["status"] == IDLE


def test_rescanning_forgets_an_earlier_dismissal() -> None:
    """Pointing at the same object again means they changed their mind."""
    importer = ObjectImporter()
    importer.set_scanning(True)
    _settle(importer)
    importer.decide("dismiss")
    importer.set_scanning(True)
    assert _settle(importer) == AWAITING


def main() -> None:
    for name, case in sorted(globals().items()):
        if name.startswith("test_") and callable(case):
            case()


if __name__ == "__main__":
    main()
    print("import scanning: PASS")
