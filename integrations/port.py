"""Port catalog setup and fast-path run sync."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import requests

from integrations.config import ROOT, Settings, load_settings

BLUEPRINTS_DIR = ROOT / "port" / "blueprints"
_SYNCED_BLUEPRINTS: set[str] = set()


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


def ensure_blueprints(settings: Settings, token: str) -> None:
    if settings.port_api_url in _SYNCED_BLUEPRINTS:
        return
    for item in load_blueprints():
        upsert_blueprint(settings, token, item)
    _SYNCED_BLUEPRINTS.add(settings.port_api_url)


def _entity_url(settings: Settings, blueprint: str) -> str:
    return f"{settings.port_api_url}/blueprints/{blueprint}/entities"


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "item"


def _title(text: str) -> str:
    return text.replace("_", " ").replace("-", " ").strip().title()


def upsert_entity(
    settings: Settings,
    token: str,
    blueprint: str,
    identifier: str,
    *,
    title: str | None = None,
    properties: dict[str, Any] | None = None,
    relations: dict[str, Any] | None = None,
) -> str:
    payload: dict[str, Any] = {"identifier": identifier}
    if title:
        payload["title"] = title
    if properties:
        payload["properties"] = properties
    if relations:
        payload["relations"] = relations
    res = requests.post(
        _entity_url(settings, blueprint),
        headers=_headers(token),
        json=payload,
        timeout=20,
    )
    res.raise_for_status()
    return identifier


def build_run_payloads(
    *,
    bag_id: str,
    duration_s: float,
    motion: str,
    replay_passed: bool,
    replay_detail: str,
    elapsed_ms: float,
    append: bool,
    spec_step_count: int,
    catalog: dict[str, Any] | None,
) -> list[tuple[str, str, dict[str, Any]]]:
    mode = "append" if append else "base"
    prompt_id = _slug(bag_id)
    request_id = f"cr-{prompt_id}"
    run_id = f"run-{prompt_id}-{mode}"
    approval_id = f"approval-{prompt_id}-{mode}"
    release_id = f"release-{prompt_id}-{mode}"
    skill = "compose" if spec_step_count > 1 else motion
    stage = "release" if replay_passed else "test"
    decision = "approved" if replay_passed else "rejected"
    status = "passed" if replay_passed else "failed"
    payloads: list[tuple[str, str, dict[str, Any]]] = [
        (
            "physical_prompt",
            prompt_id,
            {
                "title": f"Prompt {bag_id}",
                "properties": {
                    "status": "PROMPTED",
                    "duration_s": round(duration_s, 2),
                    "run_id": run_id,
                },
            },
        ),
        (
            "change_request",
            request_id,
            {
                "title": f"Change Request {bag_id}",
                "properties": {
                    "stage": stage,
                    "summary": f"{motion} -> {replay_detail} in {elapsed_ms} ms",
                },
                "relations": {"prompt": prompt_id},
            },
        ),
        (
            "factory_run",
            run_id,
            {
                "title": f"Factory Run {bag_id} {mode}",
                "properties": {"skill": skill, "status": status},
                "relations": {"change_request": request_id},
            },
        ),
    ]
    if catalog is not None:
        scraper_id = f"scrape-{prompt_id}-{mode}"
        payloads.append(
            (
                "scraper_job",
                scraper_id,
                {
                    "title": f"Scraper Job {bag_id} {mode}",
                    "properties": {
                        "catalog_url": catalog.get("url", ""),
                        "status": "ok" if catalog.get("source") == "live" else "repaired",
                        "object_name": catalog.get("name") or catalog.get("label") or "object",
                        "width_cm": catalog.get("width_cm"),
                        "height_cm": catalog.get("height_cm"),
                    },
                    "relations": {"run": run_id},
                },
            )
        )
    payloads.append(
        (
            "approval",
            approval_id,
            {
                "title": f"Approval {bag_id} {mode}",
                "properties": {"decision": decision},
                "relations": {"run": run_id},
            },
        )
    )
    if replay_passed:
        payloads.append(
            (
                "twin_release",
                release_id,
                {
                    "title": f"Twin Release {bag_id} {mode}",
                    "properties": {
                        "skill": skill,
                        "composed": spec_step_count > 1,
                    },
                    "relations": {"approval": approval_id},
                },
            )
        )
    return payloads


def sync_fast_path_run(
    *,
    bag_id: str,
    duration_s: float,
    motion: str,
    replay_passed: bool,
    replay_detail: str,
    elapsed_ms: float,
    append: bool,
    spec_step_count: int,
    catalog: dict[str, Any] | None,
) -> str:
    settings = load_settings()
    if not settings.port_ready:
        return "skipped (no keys)"
    token = _token(settings)
    ensure_blueprints(settings, token)
    synced: list[str] = []
    for blueprint, identifier, payload in build_run_payloads(
        bag_id=bag_id,
        duration_s=duration_s,
        motion=motion,
        replay_passed=replay_passed,
        replay_detail=replay_detail,
        elapsed_ms=elapsed_ms,
        append=append,
        spec_step_count=spec_step_count,
        catalog=catalog,
    ):
        upsert_entity(
            settings,
            token,
            blueprint,
            identifier,
            title=payload.get("title"),
            properties=payload.get("properties"),
            relations=payload.get("relations"),
        )
        synced.append(f"{blueprint}:{identifier}")
    return ", ".join(synced)


def smoke() -> str:
    settings = load_settings()
    if not settings.port_ready:
        names = [item["identifier"] for item in load_blueprints()]
        return f"skipped (no keys). local blueprints: {', '.join(names)}"
    token = _token(settings)
    results = [upsert_blueprint(settings, token, item) for item in load_blueprints()]
    _SYNCED_BLUEPRINTS.add(settings.port_api_url)
    return "; ".join(results)
