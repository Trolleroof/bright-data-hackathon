"""NVIDIA NIM client: one JSON-returning chat call, no SDK.

NIM exposes an OpenAI-compatible ``/chat/completions``, so a single
``requests.post`` is the whole integration — adding the ``openai`` package to
carry two dicts across would be weight without leverage.

The one thing this module insists on is that the model answers with JSON. NIM
honours ``response_format={"type": "json_object"}`` on the models we use, but
some Nemotron builds still wrap the object in prose or a ``reasoning`` preamble,
so ``_json_object`` recovers the outermost braces rather than trusting the
envelope. A model that cannot be parsed raises ``NimError``; it never returns a
half-filled dict, because the caller's fallback is better than a guess.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any

import requests

from integrations.config import Settings, load_settings

_TIMEOUT_S = 45
_MAX_TOKENS = 1200


class NimError(RuntimeError):
    """NIM was unreachable, refused, or did not answer with JSON."""


@dataclass(frozen=True)
class NimReply:
    data: dict[str, Any]
    model: str
    latency_ms: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None

    def as_json(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "latency_ms": self.latency_ms,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
        }


def _json_object(text: str) -> dict[str, Any]:
    """The outermost JSON object in a reply, however the model wrapped it."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise NimError(f"no JSON object in NIM reply: {text[:200]!r}") from None
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise NimError(f"unparseable JSON from NIM: {exc}") from exc
    if not isinstance(parsed, dict):
        raise NimError(f"NIM returned {type(parsed).__name__}, expected an object")
    return parsed


def complete_json(
    system: str,
    user: str,
    *,
    settings: Settings | None = None,
    temperature: float = 0.2,
    max_tokens: int = _MAX_TOKENS,
) -> NimReply:
    """One chat turn that must come back as a JSON object. Raises NimError otherwise."""
    settings = settings or load_settings()
    if not settings.nim_ready:
        raise NimError("NVIDIA_API_KEY / NVIDIA_MODEL missing; NIM is not configured")

    started = time.monotonic()
    try:
        res = requests.post(
            f"{settings.nvidia_base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.nvidia_api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json={
                "model": settings.nvidia_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
                "stream": False,
            },
            timeout=_TIMEOUT_S,
        )
        res.raise_for_status()
        payload = res.json()
    except requests.RequestException as exc:
        raise NimError(f"NIM request failed: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise NimError(f"NIM returned a non-JSON envelope: {exc}") from exc

    choices = payload.get("choices") or []
    if not choices:
        raise NimError(f"NIM returned no choices: {str(payload)[:200]}")
    content = (choices[0].get("message") or {}).get("content") or ""
    usage = payload.get("usage") or {}
    return NimReply(
        data=_json_object(content),
        model=payload.get("model", settings.nvidia_model),
        latency_ms=round((time.monotonic() - started) * 1000, 1),
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
    )


def smoke() -> str:
    settings = load_settings()
    if not settings.nim_ready:
        return "skipped (no NVIDIA_API_KEY). agent will use its offline MJCF reader"
    reply = complete_json(
        'Reply with JSON only.',
        'Return {"ok": true, "shape": "cylinder"} and nothing else.',
        settings=settings,
    )
    return f"model={reply.model} data={reply.data} ({reply.latency_ms}ms)"


if __name__ == "__main__":
    print(smoke())
