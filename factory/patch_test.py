from factory.extract import ExtractedParams
from factory.patch import SIM_PICK_XY, SIM_PLACE_XY, build_steps


def main() -> None:
    params = ExtractedParams([], (-9, -9), (9, 9), None, "", "pick_and_place")
    steps = build_steps(params)

    assert steps[0]["at"] == list(SIM_PICK_XY)
    assert steps[1]["at"] == list(SIM_PICK_XY)
    assert steps[3]["at"] == [*SIM_PLACE_XY, 0]
    assert steps[-1]["at"] == list(SIM_PLACE_XY)


if __name__ == "__main__":
    main()
