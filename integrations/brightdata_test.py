"""Small regression checks for retailer-agnostic product selection."""

from dataclasses import replace
from unittest.mock import patch

from integrations.brightdata import _extract_page, load_rules, lookup
from integrations.config import load_settings


PRODUCT = """
<html><script type="application/ld+json">
{"@type":"Product","name":"Steel bottle","weight":{"value":300,"unitCode":"GRM"}}
</script><h1>Steel bottle</h1><p>height 24 cm width 7 cm</p></html>
"""
ARTICLE = "<html><title>How much does a bottle weigh?</title><p>height 24 cm</p></html>"


def _ready_settings():
    return replace(
        load_settings(),
        brightdata_api_token="token",
        brightdata_serp_zone="serp",
        brightdata_unlocker_zone="unlocker",
    )


def _lookup(urls, pages):
    with patch("integrations.brightdata.search", return_value=urls), patch(
        "integrations.brightdata.fetch", side_effect=lambda url, _: pages[url]
    ):
        return lookup("water bottle", _ready_settings())


def test_query_template_is_retailer_agnostic() -> None:
    assert load_rules()["search_query_template"] == "{label} product dimensions"


def test_extract_reads_product_schema() -> None:
    fields, has_product_schema = _extract_page(PRODUCT, load_rules())
    assert has_product_schema and fields["name"] == "Steel bottle"


def test_complete_product_page_wins_over_article() -> None:
    result = _lookup(["article", "product"], {"article": ARTICLE, "product": PRODUCT})
    assert result["source"] == "live" and result["url"] == "product"
    assert result["backfilled_fields"] == []


def test_partial_page_stays_live_and_backfills_the_rest() -> None:
    """A page missing one required field beats falling all the way to the fixture."""
    result = _lookup(["article"], {"article": ARTICLE})
    rules = load_rules()
    assert result["source"] == "live" and result["url"] == "article"
    assert result["backfilled_fields"]
    assert all(result.get(field) for field in rules["required_fields"])


def main() -> None:
    for name, case in sorted(globals().items()):
        if name.startswith("test_") and callable(case):
            case()


if __name__ == "__main__":
    main()
    print("brightdata selection: PASS")
