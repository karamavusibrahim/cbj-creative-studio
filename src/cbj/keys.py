"""Your own keys, per request (2026-10-19, optional): a user of the site, or of a self-hosted engine, may run the
model calls on their own Gemini API key and their own Anthropic API key instead of the studio's. The browser sends
them as headers on the calls that start work; the engine keeps them in memory for that job only, never on disk and
never in a log; every model client asks `current()` first and falls back to the studio's configuration.

Headers:  X-CBJ-Gemini-Key: <key>          the reference-video reader (gemini.py)
          X-CBJ-Anthropic-Key: <key>       the planner and the picture reader through the Anthropic API (llm.AnthropicClient)
          X-CBJ-Planner: studio | anthropic | anthropic:<model id>
              "studio" (default): the engine's own CBJ_PLANNER (the owner's Claude account through the CLI, or NVIDIA);
              "anthropic": the Anthropic API with the key above (claude-opus-5-5 unless a model id is given).
The same choice for a self-hosted engine: ANTHROPIC_API_KEY + CBJ_PLANNER=anthropic[:<model id>] in cbj-creative/.env."""
from __future__ import annotations

import threading

HEADERS = {"gemini": "x-cbj-gemini-key", "anthropic": "x-cbj-anthropic-key", "planner": "x-cbj-planner"}
MAX_KEY = 400
_local = threading.local()


def from_headers(headers) -> dict:
    """The keys a request carries ({} when none). `headers` is any mapping with case-insensitive get (Starlette's)."""
    out = {}
    for name, h in HEADERS.items():
        v = headers.get(h) if headers is not None else None
        v = (v or "").strip()[:MAX_KEY]
        if v:
            out[name] = v
    if out.get("planner", "studio").lower().split(":")[0] not in ("studio", "anthropic"):
        out.pop("planner", None)
    if out.get("planner", "").lower() == "studio":
        out.pop("planner")
    return out


def set_current(keys: dict | None) -> None:
    _local.keys = dict(keys or {})


def clear() -> None:
    _local.keys = {}


def current() -> dict:
    return dict(getattr(_local, "keys", {}) or {})


def summary(keys: dict | None = None) -> dict:
    """What a request brings, without the keys themselves: for /api/meta and the UI's pill."""
    k = keys if keys is not None else current()
    return {"gemini": bool(k.get("gemini")), "anthropic": bool(k.get("anthropic")),
            "planner": (k.get("planner") or ("anthropic" if k.get("anthropic") else "studio")).split(":")[0]}


def anthropic_choice(keys: dict | None = None) -> tuple[str, str | None] | None:
    """(key, model or None) when this request runs the planner on the Anthropic API, else None: an explicit
    X-CBJ-Planner: anthropic, or an Anthropic key with no planner named."""
    k = keys if keys is not None else current()
    key = k.get("anthropic")
    planner = (k.get("planner") or "").lower()
    if not key:
        return None
    if planner and not planner.startswith("anthropic"):
        return None
    model = planner.split(":", 1)[1] if ":" in planner else None
    return key, (model or None)
