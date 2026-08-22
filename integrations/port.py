"""Port catalog setup. Creates blueprints only. No ChangeRequest yet."""

from __future__ import annotations

import json
from pathlib import Path

import requests

from integrations.config import ROOT, Settings, load_settings

BLUEPRINTS_DIR = ROOT / "port" / "blueprints"


def _token(settings: Settings) -> str:
    res = requests.post(
        f"{settings.port_api_url}/auth/access_token",
        json={"clientId": settings.port_client_id, "clientSecret": settings.port_client_secret},
        timeout=20,
    )
    res.raise_for_status()
    return res.json()["accessToken"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# Relation targets must exist first.
_BLUEPRINT_ORDER = (
    "physical_prompt",
    "change_request",
    "factory_run",
    "approval",
    "scraper_job",
    "twin_release",
)


def load_blueprints() -> list[dict]:
    by_id = {}
    for path in BLUEPRINTS_DIR.glob("*.json"):
        payload = json.loads(path.read_text())
        by_id[payload["identifier"]] = payload
    missing = [name for name in _BLUEPRINT_ORDER if name not in by_id]
    if missing:
        raise RuntimeError(f"missing blueprint files: {missing}")
    return [by_id[name] for name in _BLUEPRINT_ORDER]


def upsert_blueprint(settings: Settings, token: str, blueprint: dict) -> str:
    ident = blueprint["identifier"]
    url = f"{settings.port_api_url}/blueprints"
    headers = _headers(token)
    created = requests.post(url, json=blueprint, headers=headers, timeout=20)
    if created.status_code in (200, 201):
        return f"created {ident}"
    if created.status_code in (409, 422):
        updated = requests.put(
            f"{url}/{ident}",
            json=blueprint,
            headers=headers,
            timeout=20,
        )
        updated.raise_for_status()
        return f"updated {ident}"
    created.raise_for_status()
    return f"ok {ident}"


def smoke() -> str:
    settings = load_settings()
    if not settings.port_ready:
        names = [item["identifier"] for item in load_blueprints()]
        return f"skipped (no keys). local blueprints: {', '.join(names)}"
    token = _token(settings)
    results = [upsert_blueprint(settings, token, item) for item in load_blueprints()]
    return "; ".join(results)
