"""Find a real 3D mesh on the web for a label the camera cannot classify.

The camera gives scale and position, the product scrape gives mass and
material, and neither can produce shape. This module is the third source: it
searches the 3D-asset web through Bright Data's SERP API, opens the candidate
pages through Web Unlocker, and pulls the direct asset link (``.stl``,
``.glb``, ``.usdz``, ...) out of the HTML.

Two rungs of a three-rung ladder live here (rung 3, the primitive cylinder, is
what the twin already ships and needs no download):

  rung 1  the product's own AR model — the exact object, off its own page
  rung 2  a category mesh from the wider 3D-asset web, many sources at once

Discovery goes through Bright Data because it is a search problem. The binary
download itself is a plain GET: Web Unlocker returns text, and a CDN file is
not the thing behind the anti-bot wall — the page in front of it is.

Every return value carries where it came from and which rung fired, so the HUD
can label a degradation instead of hiding it.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from integrations.brightdata import BrightDataError, fetch, load_rules, search
from integrations.config import ROOT, Settings, load_settings

DOWNLOAD_DIR = ROOT / "outputs" / "meshes" / "downloads"
_TIMEOUT_S = 30
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class MeshDiscoveryError(RuntimeError):
    """No usable mesh was found. Callers drop to the next rung, loudly."""


@dataclass(frozen=True)
class MeshCandidate:
    asset_url: str
    page_url: str
    source: str
    rung: int
    ext: str


@dataclass(frozen=True)
class MeshDownload:
    path: Path
    candidate: MeshCandidate
    size_bytes: int
    latency_ms: float
    attempts: list[dict] = field(default_factory=list)


def _mesh_rules(rules: dict | None = None) -> dict:
    return (rules or load_rules()).get("mesh", {})


def _ext_of(url: str, extensions: list[str]) -> str | None:
    path = urlparse(url).path.lower()
    for ext in extensions:
        if path.endswith(ext):
            return ext
    return None


def asset_links(html: str, base_url: str, extensions: list[str]) -> list[str]:
    """Every direct 3D-asset URL a page exposes, absolute and deduplicated.

    Product pages hide the AR model behind ``<model-viewer src>`` or an
    ``ios-src``; asset sites put it on a plain ``<a href>``. Both are read
    here, plus a raw-text sweep for links that only exist inside inline JSON.
    """
    found: list[str] = []

    def _add(raw: str | None) -> None:
        if not raw:
            return
        url = urljoin(base_url, raw.strip())
        if _ext_of(url, extensions) and url not in found:
            found.append(url)

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["a", "link"]):
        _add(tag.get("href"))
    for tag in soup.find_all(["model-viewer", "source", "iframe", "meta"]):
        _add(tag.get("src") or tag.get("ios-src") or tag.get("content"))

    pattern = "|".join(re.escape(ext.lstrip(".")) for ext in extensions)
    for match in re.finditer(rf"https?://[^\s\"'<>\\]+?\.({pattern})\b", html, re.IGNORECASE):
        _add(match.group(0))
    return found


def _page_candidates(
    page_url: str, source: str, rung: int, settings: Settings, extensions: list[str]
) -> list[MeshCandidate]:
    html = fetch(page_url, settings)
    return [
        MeshCandidate(url, page_url, source, rung, _ext_of(url, extensions) or "")
        for url in asset_links(html, page_url, extensions)
    ]


def product_ar_candidates(
    product_url: str, settings: Settings, rules: dict | None = None
) -> list[MeshCandidate]:
    """Rung 1: the exact product's AR model, off the page the scrape already read."""
    mesh_rules = _mesh_rules(rules)
    return _page_candidates(product_url, "product_ar", 1, settings, mesh_rules["extensions"])


def web_candidates(
    label: str, settings: Settings, rules: dict | None = None, *, attempts: list[dict] | None = None
) -> list[MeshCandidate]:
    """Rung 2: one SERP query per 3D-asset source, then read each result page.

    Searching several sources answers the obvious objection to this whole step:
    if one curated dataset were the only source, a pip install would do and the
    scrape would have added nothing. Breadth is what search buys.
    """
    mesh_rules = _mesh_rules(rules)
    extensions = mesh_rules["extensions"]
    max_pages = int(mesh_rules.get("max_pages_per_source", 2))
    log = attempts if attempts is not None else []
    candidates: list[MeshCandidate] = []

    for source in mesh_rules.get("sources", []):
        name = source["name"]
        try:
            urls = search(source["query"].format(label=label), settings, limit=max_pages + 3)
        except (requests.RequestException, BrightDataError) as exc:
            log.append({"source": name, "stage": "search", "error": str(exc)})
            continue

        host = source.get("host") or ""
        pages = [url for url in urls if host in urlparse(url).netloc][:max_pages]
        for url in urls:
            # A SERP hit that already *is* the file needs no page fetch.
            if _ext_of(url, extensions):
                candidates.append(MeshCandidate(url, url, name, 2, _ext_of(url, extensions) or ""))

        for page in pages:
            try:
                page_hits = _page_candidates(page, name, 2, settings, extensions)
            except (requests.RequestException, BrightDataError) as exc:
                log.append({"source": name, "stage": "fetch", "url": page, "error": str(exc)})
                continue
            log.append({"source": name, "stage": "fetch", "url": page, "assets": len(page_hits)})
            candidates.extend(page_hits)

    # Printable formats first: MuJoCo eats STL directly, glTF needs conversion.
    order = {ext: index for index, ext in enumerate(extensions)}
    return sorted(candidates, key=lambda c: order.get(c.ext, len(order)))


def download(candidate: MeshCandidate, dest_dir: Path | None = None, *, max_bytes: int = 33_554_432) -> Path:
    """Stream the asset to disk, refusing anything over the cap mid-stream."""
    dest_dir = dest_dir or DOWNLOAD_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^a-zA-Z0-9_.-]+", "_", Path(urlparse(candidate.asset_url).path).name) or "mesh"
    target = dest_dir / f"{candidate.source}_{stem}"
    if not target.name.lower().endswith(candidate.ext):
        target = target.with_name(target.name + candidate.ext)

    written = 0
    with requests.get(
        candidate.asset_url,
        stream=True,
        timeout=_TIMEOUT_S,
        headers={"User-Agent": _BROWSER_UA, "Referer": candidate.page_url},
    ) as res:
        res.raise_for_status()
        with target.open("wb") as handle:
            for chunk in res.iter_content(chunk_size=65_536):
                written += len(chunk)
                if written > max_bytes:
                    handle.close()
                    target.unlink(missing_ok=True)
                    raise MeshDiscoveryError(f"{candidate.asset_url} exceeds {max_bytes} bytes")
                handle.write(chunk)
    if written == 0:
        target.unlink(missing_ok=True)
        raise MeshDiscoveryError(f"{candidate.asset_url} returned an empty body")
    return target


def find_mesh(
    label: str,
    *,
    product_url: str | None = None,
    settings: Settings | None = None,
    dest_dir: Path | None = None,
    max_candidates: int = 6,
) -> MeshDownload:
    """Walk the ladder: exact product AR model, then the wider 3D web.

    Raises MeshDiscoveryError when both rungs come up empty — that is rung 3,
    the primitive, and the caller is expected to say so on the HUD.
    """
    settings = settings or load_settings()
    rules = load_rules()
    mesh_rules = _mesh_rules(rules)
    max_bytes = int(mesh_rules.get("max_bytes", 33_554_432))
    started = time.monotonic()
    attempts: list[dict] = []

    if not settings.brightdata_ready:
        raise MeshDiscoveryError("Bright Data keys missing; mesh discovery needs search")

    candidates: list[MeshCandidate] = []
    if product_url:
        try:
            candidates.extend(product_ar_candidates(product_url, settings, rules))
        except (requests.RequestException, BrightDataError) as exc:
            attempts.append({"source": "product_ar", "stage": "fetch", "url": product_url, "error": str(exc)})
    if not candidates:
        candidates = web_candidates(label, settings, rules, attempts=attempts)

    for candidate in candidates[:max_candidates]:
        try:
            path = download(candidate, dest_dir, max_bytes=max_bytes)
        except (requests.RequestException, MeshDiscoveryError) as exc:
            attempts.append({"source": candidate.source, "stage": "download", "url": candidate.asset_url, "error": str(exc)})
            continue
        attempts.append({"source": candidate.source, "stage": "download", "url": candidate.asset_url, "bytes": path.stat().st_size})
        return MeshDownload(
            path=path,
            candidate=candidate,
            size_bytes=path.stat().st_size,
            latency_ms=round((time.monotonic() - started) * 1000, 1),
            attempts=attempts,
        )

    raise MeshDiscoveryError(
        f"no downloadable mesh for {label!r} after {len(candidates)} candidates"
    )
