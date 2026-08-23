"""The MJCF text reader: parse real MuJoCo markup, ignore everything else."""

from dataclasses import replace
from unittest.mock import patch

from integrations.config import load_settings
from integrations.mjcf_search import (
    MjcfSearchError,
    parse_mjcf,
    search_mujoco_text,
    _looks_like_mjcf,
    _text_urls,
)

BOTTLE_MJCF = """
<mujoco model="bottle">
  <worldbody>
    <body name="bottle">
      <geom name="body" type="cylinder" size="0.035 0.11" density="1000" rgba="0.2 0.4 0.9 1"/>
      <geom name="cap" type="cylinder" size="0.015 0.012" density="950"/>
      <geom name="scanned" type="mesh" mesh="bottle_mesh"/>
    </body>
  </worldbody>
</mujoco>
"""
README = "# Bottle\nA 22 cm tall bottle model.\n"


def _ready_settings():
    return replace(
        load_settings(),
        brightdata_api_token="token",
        brightdata_serp_zone="serp",
        brightdata_unlocker_zone="unlocker",
    )


def test_parse_reads_primitive_geoms_in_metres() -> None:
    geoms = parse_mjcf(BOTTLE_MJCF)
    body = next(geom for geom in geoms if geom.name == "body")
    assert body.type == "cylinder" and body.body == "bottle"
    # size="radius half_height" -> 7 cm across, 22 cm tall.
    assert body.width_cm == 7.0 and body.height_cm == 22.0
    assert body.density_kg_m3 == 1000.0


def test_parse_skips_mesh_geoms() -> None:
    """A mesh geom points at a binary this path deliberately never fetches."""
    assert not any(geom.type == "mesh" for geom in parse_mjcf(BOTTLE_MJCF))


def test_parse_survives_non_xml() -> None:
    assert parse_mjcf("<html>not mjcf<p>") == []
    assert _looks_like_mjcf(BOTTLE_MJCF) and not _looks_like_mjcf(README)


def test_text_urls_prefer_files_and_rewrite_github_blobs() -> None:
    urls = _text_urls(
        [
            "https://github.com/google-deepmind/mujoco_menagerie/blob/main/bottle/bottle.xml",
            "https://github.com/google-deepmind/mujoco_menagerie",
            "https://example.com/unrelated",
        ],
        [".xml", ".md"],
        "github.com",
    )
    assert urls[0].startswith("https://raw.githubusercontent.com/") and urls[0].endswith(".xml")
    assert "example.com" not in " ".join(urls)


def _search(docs: dict[str, str]):
    with patch("integrations.mjcf_search.search", return_value=list(docs)), patch(
        "integrations.mjcf_search.fetch_text", side_effect=lambda url, _: docs[url]
    ):
        return search_mujoco_text("water bottle", settings=_ready_settings())


def test_mjcf_documents_sort_ahead_of_prose() -> None:
    result = _search({"a.md": README, "b.xml": BOTTLE_MJCF})
    assert result.docs[0].url == "b.xml" and result.docs[0].is_mjcf
    assert len(result.geoms) == 2  # the mesh geom is not counted


def test_off_topic_mjcf_contributes_no_geoms() -> None:
    """MuJoCo's particle demo is valid MJCF and says nothing about bottles."""
    particle = '<mujoco model="particle"><worldbody><geom type="sphere" size="0.2"/></worldbody></mujoco>'
    result = _search({"particle.xml": particle})
    assert result.docs[0].is_mjcf and not result.docs[0].on_topic
    assert result.geoms == [] and len(result.all_geoms) == 1


def test_no_readable_text_raises() -> None:
    with patch("integrations.mjcf_search.search", return_value=[]):
        try:
            search_mujoco_text("water bottle", settings=_ready_settings())
        except MjcfSearchError:
            return
    raise AssertionError("expected MjcfSearchError when nothing could be read")


def main() -> None:
    for name, case in sorted(globals().items()):
        if name.startswith("test_") and callable(case):
            case()


if __name__ == "__main__":
    main()
    print("mjcf search: PASS")
