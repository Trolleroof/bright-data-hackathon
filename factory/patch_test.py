from factory.extract import ExtractedParams
from factory.patch import SIM_TAG_ORIGIN_XY, build_steps


def main() -> None:
    params = ExtractedParams([], (0.086, -0.225), (0.340, -0.178), None, "", "pick_and_place")
    steps = build_steps(params)

    start = [a + b for a, b in zip(SIM_TAG_ORIGIN_XY, params.start)]
    end = [a + b for a, b in zip(SIM_TAG_ORIGIN_XY, params.end)]
    assert steps[0]["at"] == start
    assert steps[1]["at"] == start
    assert steps[1]["height_cm"] == 1.5
    assert steps[2] == {"op": "grasp", "duration_s": 0.4}
    assert steps[3]["at"] == [*end, 0]
    assert steps[-1]["at"] == end
    assert steps[-1]["height_cm"] == 8


if __name__ == "__main__":
    main()
