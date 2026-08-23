"""Read MuJoCo's model ecosystem as *text* for an object the camera can't name.

The mesh path (``integrations/mesh_discovery.py``) answered "what shape is
this?" by downloading a binary and fitting it. This module answers the same
question a different way, and never downloads geometry:

    label -> Bright Data SERP over MuJoCo sources
          -> Web Unlocker / raw.githubusercontent fetch of the *text*
          -> MJCF facts pulled out of that text

What comes back is a ``MjcfDoc`` per source: the raw text (truncated), plus
every ``<geom>`` primitive the file declares, in metres, with whatever density
or mass the model author wrote down. Those authors already solved the hard
part — a Menagerie model is in real units with a sane primitive decomposition —
so the agent downstream is translating a known-good description, not inventing
dimensions from a product photo.

Nothing here decides anything. Selection ("which of these is actually like the
gray bottle on my table?") is the agent's job in ``integrations/object_agent``;
this module only makes the text available and records where each line came from.
"""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import requests

from integrations.brightdata import BrightDataError, fetch, load_rules, search
from integrations.config import Settings, load_settings
from integrations.mesh_discovery import asset_links, direct_url
from integrations.tracing import record_event, span

_TIMEOUT_S = 20
_RAW_HOSTS = ("raw.githubusercontent.com", "gist.githubusercontent.com")


class MjcfSearchError(RuntimeError):
    """No MuJoCo text could be read. The caller falls back, loudly."""


@dataclass(frozen=True)
class MjcfGeom:
    """One ``<geom>`` as the model author wrote it. Sizes stay in metres."""

    type: str
    size: list[float]
    body: str = ""
    name: str = ""
    density_kg_m3: float | None = None
    mass_kg: float | None = None
    rgba: list[float] | None = None

    @property
    def height_cm(self) -> float | None:
        """Full height in cm, using MuJoCo's per-type size semantics."""
        if self.type in {"cylinder", "capsule"} and len(self.size) >= 2:
            return round(self.size[1] * 200.0, 2)
        if self.type == "box" and len(self.size) >= 3:
            return round(self.size[2] * 200.0, 2)
        if self.type == "sphere" and self.size:
            return round(self.size[0] * 200.0, 2)
        return None

    @property
    def width_cm(self) -> float | None:
        """Full width (diameter for round types) in cm."""
        if self.type in {"cylinder", "capsule", "sphere"} and self.size:
            return round(self.size[0] * 200.0, 2)
        if self.type == "box" and len(self.size) >= 3:
            return round(self.size[0] * 200.0, 2)
        return None

    def as_json(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "size_m": self.size,
            "body": self.body,
            "name": self.name,
            "height_cm": self.height_cm,
            "width_cm": self.width_cm,
            "density_kg_m3": self.density_kg_m3,
            "mass_kg": self.mass_kg,
            "rgba": self.rgba,
        }


@dataclass(frozen=True)
class MjcfDoc:
    """One MuJoCo document, as text plus the geoms parsed out of it."""

    source: str
    url: str
    text: str
    geoms: list[MjcfGeom] = field(default_factory=list)
    is_mjcf: bool = False
    # Does this document actually talk about the detected object? A SERP query
    # for "water bottle mjcf" happily returns MuJoCo's particle demo: valid
    # MJCF, real geoms, and no relationship to a bottle. Copying numbers out of
    # it would be worse than admitting we found nothing.
    on_topic: bool = False

    @property
    def usable(self) -> bool:
        """MJCF that is both parseable and about the right object."""
        return bool(self.geoms) and self.on_topic

    def as_json(self, *, excerpt_chars: int = 1200) -> dict[str, Any]:
        return {
            "source": self.source,
            "url": self.url,
            "is_mjcf": self.is_mjcf,
            "on_topic": self.on_topic,
            "geoms": [geom.as_json() for geom in self.geoms],
            "excerpt": self.text[:excerpt_chars],
        }


@dataclass(frozen=True)
class MjcfSearchResult:
    label: str
    docs: list[MjcfDoc]
    latency_ms: float
    attempts: list[dict] = field(default_factory=list)

    @property
    def geoms(self) -> list[MjcfGeom]:
        """Geoms worth copying: parsed, and from a document about this object."""
        return [geom for doc in self.docs if doc.usable for geom in doc.geoms]

    @property
    def all_geoms(self) -> list[MjcfGeom]:
        """Every parsed geom, on-topic or not. For traces and debugging."""
        return [geom for doc in self.docs for geom in doc.geoms]

    def as_json(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "latency_ms": self.latency_ms,
            "docs": [doc.as_json() for doc in self.docs],
            "attempts": self.attempts,
        }


def _rules(rules: dict | None = None) -> dict:
    return (rules or load_rules()).get("mjcf", {})


def search_label(label: str, rules: dict | None = None) -> str:
    """The label with colour words removed — what MuJoCo's ecosystem indexes by.

    ``vision/detect.py`` prepends a colour it read off the pixels ("gray water
    bottle"). No MJCF file is catalogued by colour, so leaving it in narrows
    every query to zero results. The colour is still real information, so it
    stays on the label the agent reads; it just does not go into the query.
    """
    drop = {word.lower() for word in _rules(rules).get("drop_words", [])}
    words = [word for word in label.split() if word.lower() not in drop]
    return " ".join(words) or label


def _floats(raw: str | None) -> list[float]:
    if not raw:
        return []
    out = []
    for token in raw.replace(",", " ").split():
        try:
            out.append(float(token))
        except ValueError:
            return []
    return out


def _optional_float(raw: str | None) -> float | None:
    try:
        return float(raw) if raw else None
    except ValueError:
        return None


def parse_mjcf(text: str) -> list[MjcfGeom]:
    """Every primitive ``<geom>`` in an MJCF document, with its owning body.

    Mesh geoms are skipped on purpose: a ``type="mesh"`` geom points at a
    binary this path deliberately does not fetch, so it carries no dimensions
    we can read. Malformed XML yields nothing rather than raising — half the
    URLs a search returns are HTML pages that merely mention MuJoCo.
    """
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []

    geoms: list[MjcfGeom] = []

    def walk(node: ET.Element, body: str) -> None:
        for child in node:
            if child.tag == "body":
                walk(child, child.get("name", body))
                continue
            if child.tag == "geom":
                size = _floats(child.get("size"))
                gtype = child.get("type", "sphere" if size and len(size) == 1 else "")
                if gtype and gtype != "mesh" and size:
                    geoms.append(
                        MjcfGeom(
                            type=gtype,
                            size=size,
                            body=body,
                            name=child.get("name", ""),
                            density_kg_m3=_optional_float(child.get("density")),
                            mass_kg=_optional_float(child.get("mass")),
                            rgba=_floats(child.get("rgba")) or None,
                        )
                    )
            walk(child, body)

    walk(root, root.get("model", ""))
    return geoms


_STOPWORDS = {"the", "and", "for", "with", "model", "object"}
# ``type="box"`` appears in nearly every MJCF file. Matching a detected "blue
# box" against it would make every document look on-topic, so geom type values
# are stripped before the label is looked for.
_TYPE_ATTR = re.compile(r'type\s*=\s*"[^"]*"', re.IGNORECASE)


def _on_topic(text: str, url: str, query_label: str) -> bool:
    """True when the document names the object, not merely MuJoCo.

    The head noun of the (colour-stripped) label must appear — "water bottle"
    therefore rejects MuJoCo's ``particle.xml``, which is valid MJCF with real
    geoms and nothing to do with bottles — and at least half the label's words
    overall, so a model simply called ``bottle`` still counts.
    """
    haystack = _TYPE_ATTR.sub(" ", f"{url}\n{text}").lower()
    words = [
        word.strip(".,\"'()") for word in query_label.lower().split()
        if len(word) > 2 and word not in _STOPWORDS
    ]
    if not words:
        return False
    present = [word for word in words if word in haystack]
    return words[-1] in present and len(present) / len(words) >= 0.5


def _looks_like_mjcf(text: str) -> bool:
    head = text[:4000].lower()
    return "<mujoco" in head or ("<worldbody" in head and "<geom" in head)


def _is_text_file(url: str, extensions: list[str]) -> bool:
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in extensions)


def _text_urls(urls: list[str], extensions: list[str], host: str) -> list[str]:
    """SERP hits worth fetching: text files first, then pages on the right host."""
    files, pages = [], []
    for url in urls:
        direct = direct_url(url)
        if _is_text_file(direct, extensions):
            files.append(direct)
        elif not host or host in urlparse(direct).netloc:
            pages.append(direct)
    return files + pages


def linked_text_urls(html: str, page_url: str, extensions: list[str]) -> list[str]:
    """The ``.xml``/``.md`` files a repo page links to, as raw URLs.

    A SERP query for a MuJoCo model almost never lands on the model file
    itself; it lands on the repository page that lists it. That page is one
    hop from the MJCF, and GitHub renders the listing as plain ``<a href>``
    blob links, so harvesting them turns a useless landing page into the
    actual text. ``.md`` is dropped here — a README linked off a repo page is
    rarely about the object, and it would crowd out the model file.
    """
    links = asset_links(html, page_url, [ext for ext in extensions if ext != ".md"])
    return [url for url in links if urlparse(url).netloc in _RAW_HOSTS or _is_text_file(url, extensions)]


def fetch_text(url: str, settings: Settings) -> str:
    """Fetch a document's text. Raw hosts are plain GETs; pages go through Unlocker.

    raw.githubusercontent.com serves files with no anti-bot wall in front of
    them, so paying Unlocker quota for one would be waste — the wall is on the
    HTML page, which is exactly where ``fetch`` is still used.
    """
    if urlparse(url).netloc in _RAW_HOSTS:
        res = requests.get(url, timeout=_TIMEOUT_S, headers={"User-Agent": "bidex/1.0"})
        res.raise_for_status()
        return res.text
    return fetch(url, settings)


def _run_searches(
    sources: list[dict], query_label: str, settings: Settings, limit: int, attempts: list[dict]
) -> list[tuple[str, str]]:
    """Every source's SERP query at once, results kept in source order.

    The queries are independent and each costs seconds, so running them in
    sequence spends the operator's attention on nothing. Ordering is restored
    afterwards, because source order encodes which ecosystem we trust most.
    """
    def one(source: dict) -> tuple[str, list[str]]:
        try:
            return source["name"], search(source["query"].format(label=query_label), settings, limit=limit)
        except (requests.RequestException, BrightDataError) as exc:
            attempts.append({"source": source["name"], "stage": "search", "error": str(exc)})
            return source["name"], []

    with ThreadPoolExecutor(max_workers=max(1, len(sources))) as pool:
        found = list(pool.map(one, sources))
    return [(name, url) for (name, urls), source in zip(found, sources) for url in urls]


def _read(
    candidates: list[tuple[str, str]],
    query_label: str,
    settings: Settings,
    max_chars: int,
    attempts: list[dict],
) -> list[MjcfDoc]:
    """Fetch a batch of documents in parallel and turn each into an MjcfDoc."""
    def one(item: tuple[str, str]) -> MjcfDoc | None:
        name, url = item
        try:
            text = fetch_text(url, settings)[:max_chars]
        except (requests.RequestException, BrightDataError) as exc:
            attempts.append({"source": name, "stage": "fetch", "url": url, "error": str(exc)})
            return None
        geoms = parse_mjcf(text)
        doc = MjcfDoc(name, url, text, geoms, _looks_like_mjcf(text), _on_topic(text, url, query_label))
        attempts.append(
            {"source": name, "stage": "fetch", "url": url, "chars": len(text),
             "geoms": len(geoms), "mjcf": doc.is_mjcf, "on_topic": doc.on_topic}
        )
        return doc

    with ThreadPoolExecutor(max_workers=max(1, len(candidates))) as pool:
        return [doc for doc in pool.map(one, candidates) if doc is not None]


def search_mujoco_text(
    label: str,
    *,
    settings: Settings | None = None,
    rules: dict | None = None,
    max_docs: int = 2,
) -> MjcfSearchResult:
    """Every MuJoCo document Bright Data can find for ``label``, as text.

    Searches all sources at once, then reads the candidates in parallel waves,
    stopping as soon as ``max_docs`` documents are both MJCF and about this
    object. A wave of on-topic landing pages earns one more wave, because the
    model file is usually one link off the page the search landed on.

    Raises MjcfSearchError only when nothing at all could be read.
    """
    settings = settings or load_settings()
    rules = rules or load_rules()
    mjcf_rules = _rules(rules)
    extensions = mjcf_rules.get("extensions", [".xml", ".md"])
    max_pages = int(mjcf_rules.get("max_pages_per_source", 2))
    max_chars = int(mjcf_rules.get("max_chars_per_doc", 12000))
    max_fetches = int(mjcf_rules.get("max_fetches", 6))
    query_label = search_label(label, rules)
    started = time.monotonic()
    attempts: list[dict] = []
    docs: list[MjcfDoc] = []
    # Sources overlap heavily — most of the queries are GitHub-shaped, so the
    # same model file comes back more than once. Reading it twice would spend
    # quota to hand the agent a duplicate.
    seen: set[str] = set()

    if not settings.brightdata_ready:
        raise MjcfSearchError("Bright Data keys missing; the MuJoCo text search needs SERP")

    with span("mjcf_search", label=label, query_label=query_label):
        sources = list(mjcf_rules.get("sources", []))
        hits = _run_searches(sources, query_label, settings, max_pages + 4, attempts)
        hosts = {source["name"]: source.get("host", "") for source in sources}

        queue: list[tuple[str, str]] = []
        for name, url in hits:
            for candidate in _text_urls([url], extensions, hosts.get(name, "")):
                if candidate not in seen:
                    seen.add(candidate)
                    queue.append((name, candidate))

        # Text files ahead of landing pages: a raw .xml is the thing we came for.
        queue.sort(key=lambda item: not _is_text_file(item[1], extensions))

        waves = 0
        while queue and len(docs) < max_fetches and waves < 2:
            batch, queue = queue[:max_pages + 1], queue[max_pages + 1 :]
            wave = _read(batch, query_label, settings, max_chars, attempts)
            docs.extend(wave)
            waves += 1
            if sum(1 for doc in docs if doc.usable) >= max_docs:
                break
            # A landing page carries no geoms but links the file that does.
            # Only pages about this object earn the hop: the MuJoCo repo roots
            # link thousands of files the query had nothing to do with.
            linked: list[tuple[str, str]] = []
            for doc in wave:
                if doc.usable or not doc.on_topic or _is_text_file(doc.url, extensions):
                    continue
                fresh = [url for url in linked_text_urls(doc.text, doc.url, extensions) if url not in seen]
                if fresh:
                    attempts.append({"source": doc.source, "stage": "harvest", "url": doc.url, "linked": len(fresh)})
                seen.update(fresh[:max_pages])
                linked.extend((doc.source, url) for url in fresh[:max_pages])
            queue = linked + queue

    if not docs:
        raise MjcfSearchError(f"no MuJoCo text could be read for {label!r}")

    # MJCF with real geoms first: that is the text the agent can actually copy
    # numbers out of. Prose keeps its place behind it as supporting context.
    docs.sort(key=lambda doc: (doc.usable, doc.on_topic, doc.is_mjcf, len(doc.geoms)), reverse=True)
    result = MjcfSearchResult(
        label=label,
        docs=docs,
        latency_ms=round((time.monotonic() - started) * 1000, 1),
        attempts=attempts,
    )
    record_event(
        "mjcf_search",
        label=label,
        query_label=query_label,
        docs=len(docs),
        mjcf_docs=sum(doc.is_mjcf for doc in docs),
        usable_docs=sum(doc.usable for doc in docs),
        geoms=len(result.geoms),
        latency_ms=result.latency_ms,
    )
    return result


def smoke() -> str:
    settings = load_settings()
    if not settings.brightdata_ready:
        sources = [source["name"] for source in _rules().get("sources", [])]
        return f"skipped (no keys). mujoco text sources: {', '.join(sources)}"
    result = search_mujoco_text("water bottle", settings=settings)
    best = result.docs[0]
    return (
        f"{len(result.docs)} docs, {len(result.geoms)} on-topic geoms "
        f"({len(result.all_geoms)} total) in {result.latency_ms}ms; "
        f"best {best.source} {best.url} mjcf={best.is_mjcf} on_topic={best.on_topic}"
    )


if __name__ == "__main__":
    print(smoke())
