"""Bright Data lookup: search -> fetch -> extract. No collector id, no selectors.

The camera gives position, never identity or size. This module fills that gap
by reading the live web: SERP API turns a rough label into a candidate product
URL, Web Unlocker fetches the page past anti-bot/JS walls, and extract() pulls
{name, height_cm, width_cm, weight_g, material} out of the HTML — from
schema.org Product JSON-LD when the page has it, text heuristics otherwise.

Every result carries `source` (live | fixture) and `latency_ms` so the HUD and
the trace timeline can show, not claim, whether a scrape actually happened. The fixture at
brightdata/fixtures/bottle.json is a labeled fallback, not a silent one — a
caller must not treat a fixture result as indistinguishable from a live one.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import requests
import yaml
from bs4 import BeautifulSoup

from integrations.config import ROOT, Settings, load_settings

RULES_PATH = ROOT / "brightdata" / "rules.yaml"
FIXTURE_PATH = ROOT / "brightdata" / "fixtures" / "bottle.json"
_SERP_ATTEMPTS = 3
_SERP_RETRY_S = 1.0

BRIGHTDATA_REQUEST_URL = "https://api.brightdata.com/request"
_TIMEOUT_S = 25

_UNIT_CM = {"cm": 1.0, "centimeter": 1.0, "centimeters": 1.0, "in": 2.54, "inch": 2.54, "inches": 2.54, '"': 2.54}
_UNIT_G = {"g": 1.0, "gram": 1.0, "grams": 1.0, "kg": 1000.0, "lb": 453.592, "lbs": 453.592, "oz": 28.3495}

_DIM_RE = re.compile(
    r"(height|width|depth|length)\D{0,15}?(\d+(?:\.\d+)?)\s*(cm|centimeters?|in|inches?|\")",
    re.IGNORECASE,
)
_WEIGHT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(kg|lbs?|oz|g|grams?)\b", re.IGNORECASE)


class BrightDataError(RuntimeError):
    """A scrape step failed. Callers should fall back to the fixture, loudly."""


def load_rules() -> dict:
    return yaml.safe_load(RULES_PATH.read_text())


def load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text())


def _headers(settings: Settings) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.brightdata_api_token}",
    }


def search(query: str, settings: Settings, limit: int = 5) -> list[str]:
    """SERP API: query -> ranked candidate URLs. Proves we didn't type the URL."""
    target = f"https://www.google.com/search?q={requests.utils.quote(query)}&brd_json=1"
    # The SERP endpoint intermittently answers 200 with an empty body. That is a
    # transient blank, not a real "no results", so retry before believing it.
    payload = None
    for attempt in range(_SERP_ATTEMPTS):
        res = requests.post(
            BRIGHTDATA_REQUEST_URL,
            headers=_headers(settings),
            json={"zone": settings.brightdata_serp_zone, "url": target, "format": "raw"},
            timeout=_TIMEOUT_S,
        )
        res.raise_for_status()
        if res.text.strip():
            payload = res.json()
            break
        if attempt + 1 < _SERP_ATTEMPTS:
            time.sleep(_SERP_RETRY_S)
    if payload is None:
        raise BrightDataError(
            f"SERP API returned an empty body {_SERP_ATTEMPTS}x for {query!r}"
        )

    urls: list[str] = []
    for key in ("shopping", "organic", "results"):
        for item in payload.get(key, []) or []:
            link = item.get("link") or item.get("url")
            if link and link not in urls:
                urls.append(link)
    if not urls:
        raise BrightDataError(f"SERP API returned no candidate URLs for {query!r}")
    return urls[:limit]


def fetch(url: str, settings: Settings) -> str:
    """Web Unlocker: fetch a page through JS render + anti-bot handling."""
    res = requests.post(
        BRIGHTDATA_REQUEST_URL,
        headers=_headers(settings),
        json={"zone": settings.brightdata_unlocker_zone, "url": url, "format": "raw"},
        timeout=_TIMEOUT_S,
    )
    res.raise_for_status()
    return res.text


def fetch_naive(url: str) -> tuple[int, str]:
    """Plain requests.get, no unlocker. For the side-by-side anti-bot beat.

    Returns (status_code, body_preview). Callers show this next to a Web
    Unlocker fetch of the same URL — most retail pages 403 or return a JS
    shell here, which is the differentiator demonstrated instead of claimed.
    """
    try:
        res = requests.get(url, timeout=10, headers={"User-Agent": "curl/8.0"})
        return res.status_code, res.text[:200]
    except requests.RequestException as exc:
        return 0, str(exc)


def _dims_to_cm(html_text: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for label, value, unit in _DIM_RE.findall(html_text):
        field = f"{label.lower()}_cm"
        if field in out:
            continue
        out[field] = round(float(value) * _UNIT_CM[unit.lower()], 2)
    return out


def _weight_to_g(html_text: str) -> float | None:
    match = _WEIGHT_RE.search(html_text)
    if not match:
        return None
    value, unit = match.groups()
    return round(float(value) * _UNIT_G[unit.lower()], 1)


def _material(html_text: str, rules: dict) -> str | None:
    lowered = html_text.lower()
    for material in rules.get("material_density_kg_m3", {}):
        if material.replace("_", " ") in lowered or material in lowered:
            return material
    return None


def _extract_page(html: str, rules: dict) -> tuple[dict[str, Any], bool]:
    """Pull fields and the Product-schema signal from a page.

    Tries schema.org Product JSON-LD first (structured, when present), then
    falls back to text heuristics. No CSS selectors — a page redesign can't
    break this the way it breaks a hand-wired selector.
    """
    soup = BeautifulSoup(html, "html.parser")
    fields: dict[str, Any] = {}
    has_product_schema = False

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        candidates = data if isinstance(data, list) else [data]
        if isinstance(data, dict) and isinstance(data.get("@graph"), list):
            candidates = data["@graph"]
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            types = candidate.get("@type", [])
            if isinstance(types, str):
                types = [types]
            if "Product" in types:
                has_product_schema = True
                if candidate.get("name"):
                    fields.setdefault("name", candidate["name"])
                weight = candidate.get("weight")
                if isinstance(weight, dict) and weight.get("value"):
                    unit = str(weight.get("unitCode", "GRM")).upper()
                    scale = {"GRM": 1.0, "KGM": 1000.0, "LBR": 453.592, "ONZ": 28.3495}.get(unit, 1.0)
                    fields.setdefault("weight_g", round(float(weight["value"]) * scale, 1))

    text = soup.get_text(" ", strip=True)
    if "name" not in fields:
        h1 = soup.find("h1")
        if h1 and h1.get_text(strip=True):
            fields["name"] = h1.get_text(strip=True)
        elif soup.title and soup.title.get_text(strip=True):
            fields["name"] = soup.title.get_text(strip=True)

    for field, value in _dims_to_cm(text).items():
        fields.setdefault(field, value)

    if "weight_g" not in fields:
        weight = _weight_to_g(text)
        if weight is not None:
            fields["weight_g"] = weight

    material = _material(text, rules)
    if material:
        fields["material"] = material

    return fields, has_product_schema


def extract(html: str, rules: dict) -> dict[str, Any]:
    """Pull {name, height_cm, width_cm, weight_g, material} from a page."""
    return _extract_page(html, rules)[0]


def lookup(label: str, settings: Settings | None = None) -> dict[str, Any]:
    """search -> fetch -> extract, with a labeled fixture fallback on any failure.

    Always returns required_fields (backfilled from the fixture if a live
    result is missing them) plus source/url/latency_ms for the HUD/traces.
    """
    settings = settings or load_settings()
    rules = load_rules()
    fixture = load_fixture()
    started = time.monotonic()

    if settings.brightdata_ready:
        try:
            query = settings.brightdata_catalog_url or rules["search_query_template"].format(label=label)
            urls = search(query, settings) if not settings.brightdata_catalog_url else [settings.brightdata_catalog_url]
            last_error: Exception | None = None
            candidates: list[tuple[int, str, dict[str, Any], list[str]]] = []
            for url in urls or [rules["fallback_catalog_url"]]:
                try:
                    html = fetch(url, settings)
                    fields, has_product_schema = _extract_page(html, rules)
                    missing_required = [f for f in rules["required_fields"] if not fields.get(f)]
                    if not missing_required:
                        candidates.append((int(has_product_schema), url, fields, missing_required))
                except (requests.RequestException, BrightDataError) as exc:
                    last_error = exc
                    continue
            if candidates:
                _, url, fields, missing_required = max(candidates, key=lambda candidate: candidate[0])
                return {
                    **fields,
                    "source": "live",
                    "url": url,
                    "latency_ms": round((time.monotonic() - started) * 1000, 1),
                    "backfilled_fields": missing_required,
                }
            raise last_error or BrightDataError("no candidate URL produced complete product fields")
        except (requests.RequestException, BrightDataError):
            pass  # falls through to the labeled fixture below

    return {
        **fixture,
        "source": "fixture",
        "url": fixture.get("catalog_url", rules["fallback_catalog_url"]),
        "latency_ms": round((time.monotonic() - started) * 1000, 1),
    }


def smoke() -> str:
    settings = load_settings()
    rules = load_rules()
    fixture = load_fixture()
    missing = [field for field in rules["required_fields"] if field not in fixture]
    if missing:
        raise RuntimeError(f"fixture missing fields: {missing}")

    if not settings.brightdata_ready:
        return f"skipped (no keys). fixture {fixture['name']} {fixture['width_cm']}cm wide"

    result = lookup(label="water bottle", settings=settings)
    return (
        f"source={result['source']} url={result['url']} "
        f"name={result.get('name')!r} {result.get('width_cm')}x{result.get('height_cm')}cm "
        f"({result['latency_ms']}ms)"
    )
