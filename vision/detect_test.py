"""The detector must propose objects on the table, never the room behind it."""

import numpy as np

from vision.detect import _is_background, detect_object

FRAME = (720, 1280, 3)


def _table(objects: list[tuple[int, int, int, int]]) -> np.ndarray:
    frame = np.full(FRAME, 245, np.uint8)
    for x, y, w, h in objects:
        frame[y : y + h, x : x + w] = (140, 140, 140)
    return frame


def test_the_reported_background_box_is_rejected() -> None:
    """bbox 389,0,891,720 off a 1280x720 frame: full height, 70% of the picture."""
    assert _is_background((389, 0, 891, 720), 891 * 720, FRAME)


def test_a_bottle_on_the_table_is_not_background() -> None:
    assert not _is_background((560, 120, 90, 260), 90 * 260, FRAME)


def test_a_blob_wedged_into_three_edges_is_background_whatever_its_area() -> None:
    assert _is_background((0, 0, 40, 720), 40 * 720, FRAME)


def test_detect_skips_the_room_and_finds_the_object() -> None:
    """A wall-sized blob must not hide a real object behind it in the ranking."""
    frame = _table([(0, 0, 900, 720), (1000, 300, 70, 200)])
    detection = detect_object(frame)
    assert detection is not None, "the object was lost behind the background blob"
    x, y, w, h = detection.bbox
    assert x >= 900 and w < 200 and h < 400


def test_an_empty_table_proposes_nothing() -> None:
    assert detect_object(_table([])) is None


def main() -> None:
    for name, case in sorted(globals().items()):
        if name.startswith("test_") and callable(case):
            case()


if __name__ == "__main__":
    main()
    print("detect gating: PASS")
