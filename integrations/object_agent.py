"""The import agent: MuJoCo text in, a sized MuJoCo primitive out.

This replaces the mesh-download path. Nothing binary is fetched and nothing is
fitted; the agent works on *text* and produces numbers, in four steps:

  1. Port     — has this label been catalogued before? If so, reuse its spec
                and touch neither Bright Data nor NIM. The catalog is the
                cheapest source and the one with a human in its history.
  2. Bright   — search MuJoCo's own model ecosystem (Menagerie, scanned
     Data       objects, docs) for a *similar* object and read the MJCF text.
  3. NIM      — an NVIDIA NIM model reads that text next to the product catalog
                dimensions and picks a geom type, size, density, and colour,
                citing the model it copied from. If NIM is not configured or
                fails, ``_offline_spec`` does the same job deterministically
                off the parsed ``<geom>`` elements.
  4. Port     — write the result back as a ``sim_object`` so step 1 can hit
                next time.

The agent is deliberately allowed to be wrong out loud: every spec carries
``agent`` (nim | offline_reader | port_cache), ``mujoco_url``, and a one-line
``reasoning``, and the HUD shows all three. A confident number with no
provenance would be the failure mode worth avoiding here.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from integrations import port as port_api
from integrations.config import Settings, load_settings
from integrations.mjcf_search import MjcfSearchError, MjcfSearchResult, search_mujoco_text
from integrations.nim import NimError, complete_json
from integrations.tracing import record_event, span

# What the twin can actually instantiate today (``twin/world.py`` maps box and
# cylinder; anything else is coerced to the nearest of the two).
SHAPES = ("box", "cylinder", "capsule", "sphere")
_TWIN_SHAPES = {"box": "box", "cylinder": "cylinder", "capsule": "cylinder", "sphere": "cylinder"}

# Nouns whose shape is not in question. A bottle is a cylinder; no amount of
# MJCF reading should be able to turn it into a box, and on a demo stage the
# operator typing "gray water bottle" needs a cylinder to appear, not a
# negotiation about one.
_SHAPE_PRIORS = {
    "cylinder": ("bottle", "can", "cup", "mug", "glass", "jar", "tumbler", "flask", "roll"),
    "box": ("box", "tray", "carton", "crate", "book", "package", "pallet"),
}

# Sanity rails on whatever the model says. A tabletop object the arm has to
# reach around is centimetres, not millimetres and not metres.
_MIN_CM, _MAX_CM = 1.0, 60.0
_MIN_DENSITY, _MAX_DENSITY = 50.0, 12000.0
# How far the camera's measured aspect ratio has to be from square before it is
# allowed to overrule the model on which dimension is the tall one.
_ASPECT_MARGIN = 1.15

# Bumped whenever the agent's reasoning changes in a way that would produce a
# different answer for the same object. Port rows written by an older agent are
# re-derived rather than trusted: a cache that outlives the bug that filled it
# turns one bad import into a permanent one.
SPEC_VERSION = 2

_SYSTEM = """You are a robotics simulation engineer working in MuJoCo.

A webcam gave a coarse label for an object on a table. Bright Data searched \
MuJoCo's own model ecosystem and returned the TEXT of real MJCF models for \
similar objects. Your job is to translate that text into ONE primitive geom \
the twin can instantiate for the detected object.

Rules:
- Copy dimensions and densities from the MJCF text wherever it covers the \
object; MuJoCo sizes are half-extents in metres (cylinder size="radius \
half_height", box size="hx hy hz").
- The product catalog dimensions, when present, describe the REAL object and \
outrank a merely similar MuJoCo model. Use the MJCF for shape, proportion, \
density and colour; use the catalog for absolute size.
- A document marked about_this_object=false is MuJoCo syntax for something \
else entirely. Read it for conventions if you like, but do NOT copy its \
dimensions onto this object.
- The camera measured the object's bounding-box aspect ratio (height / width). \
Respect it: an aspect above 1 means height_cm MUST exceed width_cm.
- Never invent a source. Cite the URL you actually used, or "" if none applied.
- Answer with a JSON object only, no prose:

{"shape": "box|cylinder|capsule|sphere", "height_cm": <number>, \
"width_cm": <number>, "density_kg_m3": <number>, "material": "<string>", \
"rgba": [r, g, b, a], "mujoco_url": "<url or empty>", \
"confidence": <0..1>, "reasoning": "<one sentence, cite the model you copied>"}"""


@dataclass
class ObjectSpec:
    """One instantiable object, and the receipts for every number in it."""

    label: str
    shape: str = "cylinder"
    height_cm: float = 20.0
    width_cm: float = 7.0
    density_kg_m3: float = 950.0
    material: str = "plastic"
    rgba: list[float] = field(default_factory=lambda: [0.15, 0.55, 0.95, 0.75])
    mujoco_source: str = ""
    mujoco_url: str = ""
    reasoning: str = ""
    agent: str = "offline_reader"   # nim | offline_reader | port_cache
    agent_model: str = ""
    confidence: float = 0.4
    port_entity: str = ""
    docs_read: int = 0
    geoms_read: int = 0
    latency_ms: float = 0.0

    @property
    def twin_shape(self) -> str:
        """The geom type ``twin/world.py`` can build, nearest to what was asked."""
        return _TWIN_SHAPES.get(self.shape, "cylinder")

    def as_json(self) -> dict[str, Any]:
        return {**asdict(self), "twin_shape": self.twin_shape}


def _clamp(value: Any, low: float, high: float, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not number or number != number:  # 0 or NaN
        return default
    return round(min(max(number, low), high), 2)


def _rgba(value: Any, default: list[float]) -> list[float]:
    """Four channels from a list or from MJCF's own ``"r g b a"`` string."""
    if isinstance(value, str):
        value = value.replace(",", " ").split()
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return default
    try:
        channels = [min(max(float(c), 0.0), 1.0) for c in list(value)[:4]]
    except (TypeError, ValueError):
        return default
    return [round(c, 3) for c in (channels + [1.0])[:4]]


def _shape(value: Any, fallback: str = "cylinder") -> str:
    text = str(value or "").strip().lower()
    return text if text in SHAPES else fallback


def shape_prior(label: str) -> str | None:
    """The shape a label settles on its own, or None if it is genuinely open."""
    words = set(label.lower().replace("-", " ").split())
    for shape, nouns in _SHAPE_PRIORS.items():
        if words & set(nouns):
            return shape
    return None


def _keep_shape(spec: ObjectSpec) -> ObjectSpec:
    """Hold the agent to the shape the object's own name already settled."""
    prior = shape_prior(spec.label)
    if prior and _TWIN_SHAPES.get(spec.shape) != prior:
        spec.shape = prior
        spec.reasoning = f"{spec.reasoning} (Shape held to {prior} by the object's name.)".strip()
    return spec


def _orient(spec: ObjectSpec, aspect: float | None) -> ObjectSpec:
    """Make the spec agree with the aspect ratio the camera actually measured.

    The camera cannot name an object but it can see that it is twice as tall as
    it is wide, and a language model reading MJCF regularly gets that backwards.
    Measurement wins over inference here, so the two numbers are swapped rather
    than argued with.
    """
    if not aspect or aspect <= 0 or not spec.height_cm or not spec.width_cm:
        return spec
    tall = aspect > _ASPECT_MARGIN
    wide = aspect < 1.0 / _ASPECT_MARGIN
    swapped = (tall and spec.height_cm < spec.width_cm) or (wide and spec.width_cm < spec.height_cm)
    if not swapped:
        return spec
    spec.height_cm, spec.width_cm = spec.width_cm, spec.height_cm
    spec.reasoning = (
        f"{spec.reasoning} (Height and width swapped to match the camera's "
        f"measured aspect ratio of {round(aspect, 2)}.)"
    ).strip()
    return spec


def _honest_citation(spec: ObjectSpec, found: MjcfSearchResult | None) -> ObjectSpec:
    """Drop a citation that points at a document about something else.

    A model asked for a URL will happily hand back one it merely read. Citing a
    quadruped's MJCF as the source of a bottle's dimensions is worse than
    citing nothing, so an off-topic URL is cleared and the spec says plainly
    that the numbers came from the catalog.
    """
    on_topic = {doc.url for doc in (found.docs if found else []) if doc.usable}
    if spec.mujoco_url and spec.mujoco_url not in on_topic:
        spec.mujoco_url = ""
        spec.mujoco_source = ""
        spec.confidence = min(spec.confidence, 0.4)
    return spec


# --- step 1: Port -----------------------------------------------------------


def spec_from_port(label: str, settings: Settings | None = None) -> ObjectSpec | None:
    """The catalogued spec for this label, if Port has one worth reusing.

    An entry with no usable dimensions is treated as absent rather than
    adopted — a broken cache row must not outrank a live search.
    """
    known = port_api.find_sim_object(label, settings)
    if not known or not known.get("height_cm") or not known.get("width_cm"):
        return None
    if int(known.get("spec_version") or 0) != SPEC_VERSION:
        return None
    return ObjectSpec(
        label=label,
        shape=_shape(known.get("shape")),
        height_cm=_clamp(known.get("height_cm"), _MIN_CM, _MAX_CM, 20.0),
        width_cm=_clamp(known.get("width_cm"), _MIN_CM, _MAX_CM, 7.0),
        density_kg_m3=_clamp(known.get("density_kg_m3"), _MIN_DENSITY, _MAX_DENSITY, 950.0),
        material=str(known.get("material") or "plastic"),
        rgba=_rgba(known.get("rgba"), [0.15, 0.55, 0.95, 0.75]),
        mujoco_source=str(known.get("mujoco_source") or "port"),
        mujoco_url=str(known.get("mujoco_url") or ""),
        reasoning=str(known.get("reasoning") or "Reused the spec already catalogued in Port."),
        agent="port_cache",
        agent_model=str(known.get("agent_model") or ""),
        confidence=_clamp(known.get("confidence"), 0.0, 1.0, 0.6),
    )


# --- step 3a: NIM -----------------------------------------------------------


def _prompt(
    label: str, catalog: dict[str, Any], found: MjcfSearchResult, aspect: float | None = None
) -> str:
    """Everything the model gets: the label, the catalog row, and the MuJoCo text."""
    lines = [
        f"Detected label: {label}",
        f"Camera-measured aspect ratio (height/width): "
        f"{round(aspect, 2) if aspect else 'unknown'}",
        "",
        "Product catalog (Bright Data, may be partial or absent):",
        json.dumps(
            {key: catalog.get(key) for key in ("name", "height_cm", "width_cm", "weight_g", "material", "source", "url")},
            indent=2,
        ),
        "",
        f"MuJoCo documents found ({len(found.docs)}):",
    ]
    for doc in found.docs:
        lines.append(
            f"\n--- {doc.source} | {doc.url} | mjcf={doc.is_mjcf} | "
            f"about_this_object={doc.on_topic} ---"
        )
        if doc.geoms:
            lines.append("parsed geoms: " + json.dumps([geom.as_json() for geom in doc.geoms[:12]]))
        lines.append(doc.text[:4000])
    lines.append("\nReturn the JSON object now.")
    return "\n".join(lines)


def _spec_from_nim(
    label: str,
    catalog: dict[str, Any],
    found: MjcfSearchResult,
    settings: Settings,
    aspect: float | None = None,
) -> ObjectSpec:
    reply = complete_json(_SYSTEM, _prompt(label, catalog, found, aspect), settings=settings)
    data = reply.data
    url = str(data.get("mujoco_url") or "")
    source = next((doc.source for doc in found.docs if doc.url == url), found.docs[0].source if found.docs else "")
    return ObjectSpec(
        label=label,
        shape=_shape(data.get("shape")),
        height_cm=_clamp(data.get("height_cm"), _MIN_CM, _MAX_CM, 20.0),
        width_cm=_clamp(data.get("width_cm"), _MIN_CM, _MAX_CM, 7.0),
        density_kg_m3=_clamp(data.get("density_kg_m3"), _MIN_DENSITY, _MAX_DENSITY, 950.0),
        material=str(data.get("material") or catalog.get("material") or "plastic"),
        rgba=_rgba(data.get("rgba"), [0.15, 0.55, 0.95, 0.75]),
        mujoco_source=source,
        mujoco_url=url or (found.docs[0].url if found.docs else ""),
        reasoning=str(data.get("reasoning") or "")[:400],
        agent="nim",
        agent_model=reply.model,
        confidence=_clamp(data.get("confidence"), 0.0, 1.0, 0.5),
        docs_read=len(found.docs),
        geoms_read=len(found.geoms),
        latency_ms=reply.latency_ms,
    )


# --- step 3b: the offline reader -------------------------------------------


def _offline_spec(label: str, catalog: dict[str, Any], found: MjcfSearchResult | None) -> ObjectSpec:
    """Deterministic fallback: the largest parsed geom, scaled to catalog size.

    No model, no network beyond what already happened. It picks the biggest
    primitive in the MuJoCo text (the object's body, rather than a screw or a
    site marker), keeps that model's proportions and density, and stretches it
    to the real dimensions the product scrape measured.
    """
    geoms = [geom for geom in (found.geoms if found else []) if geom.height_cm and geom.width_cm]
    lowered = label.lower()
    shape = "box" if any(word in lowered for word in ("box", "tray", "carton")) else "cylinder"
    reasoning = "No MuJoCo geom was readable; sized a primitive from the product catalog alone."
    density = 950.0
    rgba = [0.15, 0.55, 0.95, 0.75]
    height_cm = _clamp(catalog.get("height_cm"), _MIN_CM, _MAX_CM, 20.0)
    width_cm = _clamp(catalog.get("width_cm"), _MIN_CM, _MAX_CM, 7.0)
    url = source = ""

    if shape == "cylinder" and not catalog.get("height_cm") and "bottle" in lowered:
        # A bottle nobody could measure is still a bottle: typical 500 ml.
        height_cm, width_cm = 22.0, 7.0
        reasoning = "No MuJoCo geom and no catalog size; used typical 500 ml bottle dimensions."

    if geoms:
        biggest = max(geoms, key=lambda g: (g.height_cm or 0) * (g.width_cm or 0))
        shape = _TWIN_SHAPES.get(biggest.type, shape)
        density = _clamp(biggest.density_kg_m3, _MIN_DENSITY, _MAX_DENSITY, density)
        rgba = _rgba(biggest.rgba, rgba)
        doc = next((doc for doc in found.docs if biggest in doc.geoms), None) if found else None
        source, url = (doc.source, doc.url) if doc else ("", "")
        # Catalog size wins when it exists; otherwise the model's own numbers do.
        if not catalog.get("height_cm"):
            height_cm = _clamp(biggest.height_cm, _MIN_CM, _MAX_CM, height_cm)
        if not catalog.get("width_cm"):
            width_cm = _clamp(
                (biggest.width_cm or 0) * (height_cm / (biggest.height_cm or height_cm)),
                _MIN_CM, _MAX_CM, width_cm,
            )
        reasoning = (
            f"Copied the largest geom in {source or 'the MuJoCo text'} "
            f"(<geom type=\"{biggest.type}\" name=\"{biggest.name or biggest.body}\">), "
            f"then sized it to the catalog dimensions."
        )

    return ObjectSpec(
        label=label,
        shape=shape,
        height_cm=height_cm,
        width_cm=width_cm,
        density_kg_m3=density,
        material=str(catalog.get("material") or "plastic"),
        rgba=rgba,
        mujoco_source=source,
        mujoco_url=url,
        reasoning=reasoning,
        agent="offline_reader",
        confidence=0.5 if geoms else 0.3,
        docs_read=len(found.docs) if found else 0,
        geoms_read=len(found.geoms) if found else 0,
    )


# --- the whole pipeline -----------------------------------------------------


def describe_object(
    label: str,
    catalog: dict[str, Any] | None = None,
    *,
    aspect: float | None = None,
    settings: Settings | None = None,
    use_port: bool = True,
) -> ObjectSpec:
    """Port -> Bright Data MuJoCo text -> NIM -> Port. Never raises.

    Always returns a usable spec. Which of the four sources produced it is on
    the spec itself (``agent``, ``mujoco_url``), because a fallback the operator
    cannot see is a fallback that will be mistaken for a result.
    """
    settings = settings or load_settings()
    catalog = catalog or {}
    started = time.monotonic()

    with span("object_agent", label=label):
        if use_port:
            cached = spec_from_port(label, settings)
            if cached is not None:
                # The guards are not a property of the search path; they are
                # what makes any spec usable, cache included.
                cached = _orient(_keep_shape(cached), aspect)
                cached.latency_ms = round((time.monotonic() - started) * 1000, 1)
                record_event("agent_spec", label=label, agent="port_cache",
                             url=cached.mujoco_url, latency_ms=cached.latency_ms)
                return cached

        found: MjcfSearchResult | None = None
        try:
            found = search_mujoco_text(label, settings=settings)
        except MjcfSearchError as exc:
            record_event("agent_search_failed", label=label, error=str(exc))

        spec: ObjectSpec | None = None
        if found is not None and settings.nim_ready:
            try:
                spec = _spec_from_nim(label, catalog, found, settings, aspect)
            except NimError as exc:
                record_event("agent_nim_failed", label=label, error=str(exc))
        if spec is None:
            spec = _offline_spec(label, catalog, found)
        spec = _orient(_keep_shape(_honest_citation(spec, found)), aspect)

        spec.latency_ms = round((time.monotonic() - started) * 1000, 1)

    record_event(
        "agent_spec", label=label, agent=spec.agent, shape=spec.shape,
        height_cm=spec.height_cm, width_cm=spec.width_cm,
        url=spec.mujoco_url, confidence=spec.confidence, latency_ms=spec.latency_ms,
    )
    if use_port:
        spec.port_entity = spec_to_port(spec)
    return spec


def spec_to_port(spec: ObjectSpec) -> str:
    """Write the spec into the Port catalog. A Port outage is not an import failure."""
    return port_api.upsert_sim_object(
        spec.label,
        {
            "shape": spec.shape,
            "height_cm": spec.height_cm,
            "width_cm": spec.width_cm,
            "density_kg_m3": spec.density_kg_m3,
            "material": spec.material,
            "rgba": " ".join(str(channel) for channel in spec.rgba),
            "mujoco_source": spec.mujoco_source,
            "mujoco_url": spec.mujoco_url,
            "reasoning": spec.reasoning,
            "agent": spec.agent,
            "agent_model": spec.agent_model,
            "confidence": spec.confidence,
            "spec_version": SPEC_VERSION,
        },
    )


def smoke() -> str:
    settings = load_settings()
    spec = describe_object("gray water bottle", settings=settings, use_port=settings.port_ready)
    return (
        f"agent={spec.agent} shape={spec.shape} {spec.width_cm}x{spec.height_cm}cm "
        f"density={spec.density_kg_m3} docs={spec.docs_read} geoms={spec.geoms_read} "
        f"src={spec.mujoco_url or 'none'} ({spec.latency_ms}ms)"
    )


if __name__ == "__main__":
    print(smoke())
