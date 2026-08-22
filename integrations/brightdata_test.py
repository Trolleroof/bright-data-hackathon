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


def main() -> None:
    rules = load_rules()
    assert rules["search_query_template"] == "{label} product dimensions"
    fields, has_product_schema = _extract_page(PRODUCT, rules)
    assert has_product_schema and fields["name"] == "Steel bottle"

    settings = replace(
        load_settings(),
        brightdata_api_token="token",
        brightdata_serp_zone="serp",
        brightdata_unlocker_zone="unlocker",
    )
    with patch("integrations.brightdata.search", return_value=["article", "product"]), patch(
        "integrations.brightdata.fetch", side_effect=lambda url, _: ARTICLE if url == "article" else PRODUCT
    ):
        result = lookup("water bottle", settings)
    assert result["source"] == "live" and result["url"] == "product"
    assert result["backfilled_fields"] == []


if __name__ == "__main__":
    main()
    print("brightdata selection: PASS")
