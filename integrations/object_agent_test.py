"""The import agent: Port first, NIM when configured, offline reader always."""

from dataclasses import replace
from unittest.mock import patch

from integrations.config import load_settings
from integrations.mjcf_search import MjcfDoc, MjcfSearchError, MjcfSearchResult, parse_mjcf
from integrations.nim import NimError, NimReply, _json_object
from integrations.object_agent import SPEC_VERSION, describe_object, _offline_spec

MJCF = """
<mujoco model="bottle">
  <worldbody><body name="bottle">
    <geom name="body" type="cylinder" size="0.04 0.10" density="1100" rgba="0.2 0.4 0.9 1"/>
    <geom name="cap" type="cylinder" size="0.015 0.01" density="950"/>
  </body></worldbody>
</mujoco>
"""
CATALOG = {"name": "Steel bottle", "height_cm": 24.0, "width_cm": 7.0, "material": "stainless_steel"}


def _found() -> MjcfSearchResult:
    doc = MjcfDoc("mujoco_menagerie", "https://raw.example/bottle.xml", MJCF, parse_mjcf(MJCF), True, True)
    return MjcfSearchResult("gray water bottle", [doc], 12.0)


def _settings(*, nim: bool):
    return replace(
        load_settings(),
        brightdata_api_token="token",
        brightdata_serp_zone="serp",
        brightdata_unlocker_zone="unlocker",
        nvidia_api_key="key" if nim else "",
        nvidia_model="test/model",
    )


def _run(settings, *, search=None, nim=None, aspect=None):
    search = search or (lambda label, **kwargs: _found())
    with patch("integrations.object_agent.search_mujoco_text", side_effect=search), patch(
        "integrations.object_agent.complete_json", side_effect=nim or NimError("off")
    ):
        return describe_object(
            "gray water bottle", CATALOG, aspect=aspect, settings=settings, use_port=False
        )


def test_offline_reader_copies_the_largest_geom_and_catalog_size() -> None:
    spec = _offline_spec("gray water bottle", CATALOG, _found())
    assert spec.agent == "offline_reader" and spec.shape == "cylinder"
    # Catalog size wins over the MuJoCo model's own 20 cm.
    assert spec.height_cm == 24.0 and spec.width_cm == 7.0
    # Density and colour still come from the model that was read.
    assert spec.density_kg_m3 == 1100.0 and spec.mujoco_url.endswith("bottle.xml")


def test_offline_reader_falls_back_to_model_size_without_a_catalog() -> None:
    spec = _offline_spec("gray water bottle", {}, _found())
    assert spec.height_cm == 20.0 and spec.width_cm == 8.0


def test_nim_result_is_used_when_configured() -> None:
    reply = NimReply(
        data={
            "shape": "cylinder", "height_cm": 23.5, "width_cm": 7.2,
            "density_kg_m3": 1100, "material": "stainless_steel",
            "rgba": [0.6, 0.6, 0.62, 1], "mujoco_url": "https://raw.example/bottle.xml",
            "confidence": 0.8, "reasoning": "Copied the menagerie bottle body geom.",
        },
        model="test/model", latency_ms=900.0,
    )
    spec = _run(_settings(nim=True), nim=lambda *a, **k: reply)
    assert spec.agent == "nim" and spec.agent_model == "test/model"
    assert spec.height_cm == 23.5 and spec.mujoco_source == "mujoco_menagerie"


def test_nim_failure_degrades_to_the_offline_reader() -> None:
    def boom(*_args, **_kwargs):
        raise NimError("502 from NIM")

    spec = _run(_settings(nim=True), nim=boom)
    assert spec.agent == "offline_reader" and spec.height_cm == 24.0


def test_search_failure_still_returns_a_usable_spec() -> None:
    def boom(*_args, **_kwargs):
        raise MjcfSearchError("no keys")

    spec = _run(_settings(nim=False), search=boom)
    assert spec.agent == "offline_reader" and spec.height_cm == 24.0
    assert spec.geoms_read == 0 and spec.mujoco_url == ""


def test_port_cache_short_circuits_the_search() -> None:
    known = {
        "shape": "box", "height_cm": 18.0, "width_cm": 6.0, "density_kg_m3": 800.0,
        "material": "plastic", "mujoco_url": "https://raw.example/cached.xml",
        "confidence": 0.9, "spec_version": SPEC_VERSION,
    }
    with patch("integrations.object_agent.port_api.find_sim_object", return_value=known), patch(
        "integrations.object_agent.search_mujoco_text"
    ) as searched, patch("integrations.object_agent.spec_to_port", return_value="obj-x"):
        spec = describe_object("catalogued widget", CATALOG, settings=_settings(nim=True))
    assert spec.agent == "port_cache" and spec.height_cm == 18.0
    assert not searched.called, "a catalogued object must not be researched again"


def test_a_cached_row_from_an_older_agent_is_re_derived() -> None:
    """A cache that outlives the bug that filled it makes one bad import permanent."""
    stale = {"shape": "cylinder", "height_cm": 6.35, "width_cm": 10.2, "spec_version": 1}
    with patch("integrations.object_agent.port_api.find_sim_object", return_value=stale), patch(
        "integrations.object_agent.search_mujoco_text", side_effect=lambda *a, **k: _found()
    ), patch("integrations.object_agent.spec_to_port", return_value="obj-x"):
        spec = describe_object("gray water bottle", CATALOG, settings=_settings(nim=False))
    assert spec.agent != "port_cache" and spec.height_cm == 24.0


def test_guards_apply_to_a_cached_spec_too() -> None:
    """The guards are what make any spec usable, cache included."""
    swapped = {"shape": "cylinder", "height_cm": 6.0, "width_cm": 20.0,
               "spec_version": SPEC_VERSION}
    with patch("integrations.object_agent.port_api.find_sim_object", return_value=swapped), patch(
        "integrations.object_agent.spec_to_port", return_value="obj-x"
    ):
        spec = describe_object("gray water bottle", CATALOG, aspect=3.0, settings=_settings(nim=True))
    assert spec.agent == "port_cache" and spec.height_cm == 20.0 and spec.width_cm == 6.0


def test_out_of_range_model_output_is_clamped_not_trusted() -> None:
    reply = NimReply(data={"shape": "toroid", "height_cm": 4000, "width_cm": 0}, model="m", latency_ms=1.0)
    spec = _run(_settings(nim=True), nim=lambda *a, **k: reply)
    assert spec.shape == "cylinder" and spec.height_cm == 60.0 and spec.width_cm == 7.0


def test_nim_reply_json_survives_reasoning_wrappers() -> None:
    assert _json_object('<think>hmm</think>```json\n{"shape": "box"}\n```')["shape"] == "box"
    assert _json_object('Here you go: {"shape": "box"} — done')["shape"] == "box"


def main() -> None:
    for name, case in sorted(globals().items()):
        if name.startswith("test_") and callable(case):
            case()


if __name__ == "__main__":
    main()
    print("object agent: PASS")


def test_camera_aspect_overrules_a_swapped_model_answer() -> None:
    """A tall object stays tall even when the model returns the axes reversed."""
    reply = NimReply(
        data={"shape": "cylinder", "height_cm": 6.4, "width_cm": 20.1,
              "mujoco_url": "https://raw.example/bottle.xml"},
        model="m", latency_ms=1.0,
    )
    spec = _run(_settings(nim=True), nim=lambda *a, **k: reply, aspect=3.1)
    assert spec.height_cm == 20.1 and spec.width_cm == 6.4
    assert "aspect ratio" in spec.reasoning


def test_a_square_bounding_box_does_not_reorder_anything() -> None:
    reply = NimReply(
        data={"shape": "box", "height_cm": 9.0, "width_cm": 11.0,
              "mujoco_url": "https://raw.example/bottle.xml"},
        model="m", latency_ms=1.0,
    )
    spec = _run(_settings(nim=True), nim=lambda *a, **k: reply, aspect=1.02)
    assert spec.height_cm == 9.0 and spec.width_cm == 11.0


def test_a_citation_to_an_off_topic_model_is_dropped() -> None:
    """Citing a quadruped as the source of a bottle's size is worse than no citation."""
    reply = NimReply(
        data={"shape": "cylinder", "height_cm": 24, "width_cm": 7,
              "mujoco_url": "https://raw.example/unitree_go1.xml", "confidence": 0.9},
        model="m", latency_ms=1.0,
    )
    spec = _run(_settings(nim=True), nim=lambda *a, **k: reply)
    assert spec.mujoco_url == "" and spec.mujoco_source == ""
    assert spec.confidence <= 0.4
