"""Gemini as the reader of a reference video (core requirement 4, 2026-10-16).

Measured first, on the tool's own 12 creatives with neutral file names and the same reading pipeline
(~/rollic-case/req4-e2e-2026-10-16/READING-ACCURACY-gemini.md): Gemini 3.5 Flash-Lite with low thinking
read the ending, the hook, the call to action, the captions and the mechanics right in 12 of 12, the
structure in 8 of 12 (37 of 44 boundaries within 1 s, 0.5 s mean error), in 4-26 s a reading with no
errors; NVIDIA build's super-vl on the same files read the ending in 9 of 12 and the structure in 5 of 12
(1.3 s mean error), in 50-250 s with server errors. So reference.video_client reads a video with this
client first and falls back to NVIDIA build when it fails.

The interface is reference.VisionClient's (describe(ask, part, path) -> text; last_model; errors), so
read_video is unchanged: the tool's part ({"type": "video_url", "video_url": {"url": "data:video/mp4;base64,
..."}}) becomes Gemini's inline_data (the small H.264 copy is well under the 20 MB inline limit), the answer
is asked as JSON with low thinking (minutes became seconds with the parts still close). Models in order
(GEMINI_MODELS, the owner's choice: Flash-Lite only; 3.7 and 3.8 Flash answered 503 "high demand" all
evening and 3.6 Flash hit the free quota), each retried after 10, 20 and 40 s on 429, 500, 502, 503 and 504.
The key is GEMINI_API_KEY in the environment or cbj-creative/.env (free tier: Google may use free-tier
content to improve its products, except for UK and EEA accounts; see the README's limitations).
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request

GEMINI_MODELS = ("gemini-3.5-flash-lite",)  # the owner's order: Flash-Lite, then NVIDIA build (reference.video_client)
URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
BACKOFF_S = (10, 20, 40)
RETRY_CODES = (429, 500, 502, 503, 504)
TIMEOUT_S = 300
TEMPERATURE = 0.2
THINKING = "low"
# Models whose free daily quota is used up, for the rest of the process (2026-10-17: a per-day 429 waited the full
# 10/20/40 s backoff on every call before NVIDIA answered; one reading took 27 minutes): {model: what to say}.
EXHAUSTED: dict[str, str] = {}


def daily_quota(body: str) -> str | None:
    """The per-day quota a 429's body names (google.rpc.QuotaFailure, a quotaId with "PerDay"), as "(500 requests)"
    words, or None for any other 429 (a per-minute quota keeps the backoff)."""
    try:
        details = (json.loads(body).get("error") or {}).get("details") or []
    except (ValueError, AttributeError):
        return None
    for d in details:
        for v in d.get("violations") or [] if isinstance(d, dict) else []:
            if "PerDay" in str(v.get("quotaId") or ""):
                value = v.get("quotaValue")
                return f"{value} requests" if value else "its daily limit"
    return None


def models_from_env() -> tuple[str, ...]:
    """GEMINI_MODELS, or the comma-separated CBJ_GEMINI_MODELS when it is set (an operator's override)."""
    raw = (os.environ.get("CBJ_GEMINI_MODELS") or "").strip()
    return tuple(m.strip() for m in raw.split(",") if m.strip()) or GEMINI_MODELS


class GeminiVideoClient:
    """A reference video read by Gemini through the API, with reference.VisionClient's interface. `last_model`
    is the model that answered, `errors` every failure on the way, `usage` the token counts of each answer
    ({model, prompt, candidates, thoughts})."""

    def __init__(self, models=None, key: str | None = None, timeout_s: float = TIMEOUT_S):
        from . import keys as K
        from .planner import load_env
        load_env()
        self.key = key or K.current().get("gemini") or os.environ.get("GEMINI_API_KEY")  # the request's own key first
        if not self.key:
            raise ValueError("no GEMINI_API_KEY: set it in the environment or in cbj-creative/.env to read videos with "
                             "Gemini (the NVIDIA reader is used instead)")
        self.models = tuple(models) if models else models_from_env()
        self.timeout_s = timeout_s
        self.last_model = None
        self.errors: list[str] = []
        self.usage: list[dict] = []
        self.sleep = time.sleep  # the waits between tries (tests replace it)

    @staticmethod
    def inline(part: dict) -> dict:
        """The tool's data-URL part ({"type": "video_url", "video_url": {"url": "data:<mime>;base64,<data>"}}, or an
        image_url) as Gemini's inline_data part."""
        url = (part.get("video_url") or part.get("image_url") or {}).get("url", "")
        m = re.match(r"data:([^;,]+);base64,(.*)$", url, re.S)
        if not m:
            raise ValueError("the part is not a base64 data URL, so it cannot be sent inline")
        return {"inline_data": {"mime_type": m.group(1), "data": m.group(2)}}

    def body(self, ask: str, part: dict) -> dict:
        """The request: the video inline, then the composed prompt; JSON out, low thinking."""
        return {"contents": [{"parts": [self.inline(part), {"text": ask}]}],
                "generationConfig": {"responseMimeType": "application/json", "temperature": TEMPERATURE,
                                     "thinkingConfig": {"thinkingLevel": THINKING}}}

    def _call(self, model: str, body: dict) -> dict:
        req = urllib.request.Request(URL.format(model=model), data=json.dumps(body).encode(),
                                     headers={"x-goog-api-key": self.key, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
            return json.loads(r.read())

    def describe(self, ask: str, part: dict, path=None) -> str:
        body = self.body(ask, part)
        errors: list[str] = []
        try:
            for model in self.models:
                for i, wait in enumerate((0,) + BACKOFF_S):
                    if wait:
                        self.sleep(wait)
                    if model in EXHAUSTED:
                        if EXHAUSTED[model] not in self.errors + errors:
                            errors.append(EXHAUSTED[model])  # once per reading
                        break  # no call, no wait: the next model, or NVIDIA
                    try:
                        out = self._call(model, body)
                    except urllib.error.HTTPError as e:
                        raw = e.read().decode(errors="replace")
                        per_day = daily_quota(raw) if e.code == 429 else None
                        if per_day:
                            EXHAUSTED[model] = f"{model}: daily free quota used up ({per_day})"
                            errors.append(EXHAUSTED[model])
                            break
                        errors.append(f"{model}: HTTP {e.code} {raw[:200].replace(chr(10), ' ')}")
                        if e.code in RETRY_CODES and i < len(BACKOFF_S):
                            continue
                        break
                    except Exception as e:  # a timeout or a broken connection: the next model
                        errors.append(f"{model}: {str(e)[:120]}")
                        break
                    cands = out.get("candidates") or []
                    text = "".join(p.get("text", "") for c in cands[:1] for p in (c.get("content") or {}).get("parts") or [])
                    meta = out.get("usageMetadata") or {}
                    self.usage.append({"model": model, "prompt": meta.get("promptTokenCount"),
                                       "candidates": meta.get("candidatesTokenCount"), "thoughts": meta.get("thoughtsTokenCount")})
                    if not text.strip():
                        errors.append(f"{model}: empty answer (finish {cands[0].get('finishReason') if cands else 'none'})")
                        break
                    self.last_model = model
                    return text
            raise ValueError("no Gemini model answered: " + "; ".join(errors)[:400])
        finally:
            self.errors += errors
