"""Port catalog setup, fast-path run sync, and the agent's read path.

Port is not only a place runs are written to. ``sim_object`` entities make it
the twin's object catalog: the import agent asks Port what it already knows
about a label *before* it spends a Bright Data search on it, and writes what it
learned back afterwards. The second sighting of the same bottle is therefore a
single authenticated GET, not a scrape and an LLM call.
"""

from __future__ import annotations

import json
import re
import time
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
    "sim_object",
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


# Port access tokens last an hour; the agent reads on every sighting, and
# re-authenticating each time would put a network round trip in front of a
# cache lookup that exists to avoid network round trips.
_TOKEN_TTL_S = 3000.0
_TOKEN_CACHE: dict[str, tuple[str, float]] = {}


def token(settings: Settings) -> str:
    """A valid access token, reused until it is nearly expired."""
    cached = _TOKEN_CACHE.get(settings.port_client_id)
    if cached and time.monotonic() < cached[1]:
        return cached[0]
    fresh = _token(settings)
    _TOKEN_CACHE[settings.port_client_id] = (fresh, time.monotonic() + _TOKEN_TTL_S)
    return fresh


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


# --- read path (the agent's side) -------------------------------------------


def get_entity(
    settings: Settings, token_: str, blueprint: str, identifier: str
) -> dict[str, Any] | None:
    """One entity, or None if Port has never heard of it.

    A 404 here is the normal case on a first sighting, so it is not an error:
    the caller carries on to the scrape.
    """
    res = requests.get(
        f"{_entity_url(settings, blueprint)}/{identifier}",
        headers=_headers(token_),
        timeout=20,
    )
    if res.status_code == 404:
        return None
    res.raise_for_status()
    return (res.json() or {}).get("entity")


def search_entities(
    settings: Settings,
    token_: str,
    blueprint: str,
    rules: list[dict[str, Any]],
    *,
    combinator: str = "and",
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Port's search API, scoped to one blueprint. Returns [] rather than raising."""
    body = {
        "combinator": combinator,
        "rules": [{"property": "$blueprint", "operator": "=", "value": blueprint}, *rules],
    }
    try:
        res = requests.post(
            f"{settings.port_api_url}/entities/search",
            headers=_headers(token_),
            json=body,
            timeout=20,
        )
        res.raise_for_status()
    except requests.RequestException:
        return []
    return ((res.json() or {}).get("entities") or [])[:limit]


def object_id(label: str) -> str:
    """The stable sim_object identifier for a detected label."""
    return f"obj-{_slug(label)}"


def find_sim_object(label: str, settings: Settings | None = None) -> dict[str, Any] | None:
    """What Port already knows about this label, as flat properties.

    Exact identifier first — the same bottle seen twice — then a label search,
    which catches "gray water bottle" after "grey water bottle" was catalogued.
    Any Port failure returns None: the catalog is an accelerator, never a gate.
    """
    settings = settings or load_settings()
    if not settings.port_ready:
        return None
    try:
        token_ = token(settings)
        entity = get_entity(settings, token_, "sim_object", object_id(label))
        if entity is None:
            matches = search_entities(
                settings, token_, "sim_object",
                [{"property": "label", "operator": "=", "value": label}],
                limit=1,
            )
            entity = matches[0] if matches else None
    except (requests.RequestException, KeyError, ValueError):
        return None
    if not entity:
        return None
    return {
        "identifier": entity.get("identifier", ""),
        "title": entity.get("title", ""),
        **(entity.get("properties") or {}),
    }


def list_sim_objects(settings: Settings | None = None, limit: int = 25) -> list[dict[str, Any]]:
    """Everything in the twin's Port object catalog, newest-agnostic order."""
    settings = settings or load_settings()
    if not settings.port_ready:
        return []
    try:
        entities = search_entities(settings, token(settings), "sim_object", [], limit=limit)
    except (requests.RequestException, KeyError, ValueError):
        return []
    return [
        {"identifier": item.get("identifier", ""), **(item.get("properties") or {})}
        for item in entities
    ]


def upsert_sim_object(
    label: str,
    properties: dict[str, Any],
    *,
    settings: Settings | None = None,
    relations: dict[str, Any] | None = None,
) -> str:
    """Write an imported object into the Port catalog. Never raises at the caller."""
    settings = settings or load_settings()
    if not settings.port_ready:
        return "skipped (no keys)"
    identifier = object_id(label)
    try:
        token_ = token(settings)
        ensure_blueprints(settings, token_)
        previous = get_entity(settings, token_, "sim_object", identifier) or {}
        imports = float((previous.get("properties") or {}).get("imports") or 0) + 1
        upsert_entity(
            settings,
            token_,
            "sim_object",
            identifier,
            title=_title(label),
            properties={**properties, "label": label, "imports": imports},
            relations=relations,
        )
    except (requests.RequestException, KeyError, ValueError) as exc:
        return f"failed: {exc}"
    return identifier
