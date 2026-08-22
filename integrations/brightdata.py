"""Bright Data lookup. Setup loads the local bottle fixture. No live scrape."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from integrations.config import ROOT, load_settings

RULES_PATH = ROOT / "brightdata" / "rules.yaml"
FIXTURE_PATH = ROOT / "brightdata" / "fixtures" / "bottle.json"


def load_rules() -> dict:
    return yaml.safe_load(RULES_PATH.read_text())


def load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text())


def smoke() -> str:
    settings = load_settings()
    rules = load_rules()
    fixture = load_fixture()
    missing = [field for field in rules["required_fields"] if field not in fixture]
    if missing:
        raise RuntimeError(f"fixture missing fields: {missing}")

    aimed = settings.brightdata_catalog_url or rules["default_catalog_url"]
    if settings.brightdata_ready:
        return (
            f"keys present, scrape not run. collector={settings.brightdata_collector_id} "
            f"url={aimed} fixture={fixture['name']}"
        )
    return f"skipped (no keys). fixture {fixture['name']} {fixture['width_cm']}cm wide, url={aimed}"
