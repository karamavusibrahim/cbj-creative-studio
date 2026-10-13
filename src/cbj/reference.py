"""Reference analysis: what an attached image or video is, measured and described, for the planner.

The case (p.6) asks for images as visual, style or composition references and for videos whose
concept, structure and pacing the tool should understand. The planner is a text model: it only
ever sees file names. So before it plans, each reference file is analysed here:
- an image: its palette is measured in code (PIL, no model) and a multimodal model describes it;
- a video: it is shrunk with ffmpeg and a multimodal model describes its structure, hook, ending,
  pacing and look.
The result is written into the brief (planner.references) so the user can see what was read, and
goes to the planner as plain notes. A failed analysis is reported, never guessed around.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
# Multimodal models on NVIDIA's hosted API, tried in order. The omni model takes images and a
# base64 mp4 as a video_url part (verified on this account).
VISION_MODELS = ("nvidia/nemotron-3-nano-omni-30b-a3b-reasoning", "nvidia/nemotron-nano-12b-v2-vl")
TIMEOUT_S = 180
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_EXT = {".mp4", ".mov", ".webm", ".m4v"}
# Words that make an attachment a reference (its look or idea), rather than an asset to place.
REFERENCE_WORDS = ("inspired", "inspiration", "reference", "like this", "similar", "match", "matching", "style",
                   "mood", "palette", "colours of", "colors of", "based on", "this concept", "this video",
                   "this clip", "this ad", "this creative", "this image", "this picture", "look like", "feel",
                   "vibe", "same look", "this look", "adapt", "version of", "recreate", "copy the")
# Words that ask for a picture to be put INTO the ad (then an image is an asset as well).
PLACE_WORDS = ("put", "insert", "place", "replace", "swap", "add", "use it as", "use this as", "as the logo",
               "as our logo", "on the end card", "beside the hook", "as the icon", "as the button", "as the cursor",
               "as the background", "instead of", "attached asset", "this asset", "attach")

# Named colours for the palette (sRGB), so the planner and the user read "pink", not "#FF4F8B".
NAMED = {"red": "#E53935", "crimson": "#B71C1C", "pink": "#FF69B4", "hot pink": "#FF1493", "rose": "#FF7F98",
         "light pink": "#FFD6EC", "orange": "#FF8000", "tangerine": "#FF8A3D", "peach": "#FFB86B",
         "yellow": "#FFCC04", "lemon": "#FFE45C", "butter": "#FFF3A0", "gold": "#D4A017", "lime": "#9ACD32",
         "green": "#14C517", "mint": "#5FD9A0", "sage": "#4FB58A", "dark green": "#065C13", "teal": "#008B8B",
         "cyan": "#00BCD4", "sky blue": "#4FB3FF", "blue": "#1469FF", "navy": "#1D3557", "lilac": "#C79BFF",
         "purple": "#8E24AA", "violet": "#5A1E9B", "grape": "#A066FF", "brown": "#795548", "beige": "#F5F5DC",
         "white": "#FFFFFF", "light grey": "#CCCCCC", "grey": "#808080", "dark grey": "#333333", "black": "#000000"}


def _rgb(h: str) -> tuple[int, int, int]:
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def colour_name(hex_: str) -> str:
    r, g, b = _rgb(hex_)
    best, dist = "grey", 1e9
    for name, h in NAMED.items():
        r2, g2, b2 = _rgb(h)
        d = (r - r2) ** 2 + (g - g2) ** 2 + (b - b2) ** 2
        if d < dist:
            best, dist = name, d
    return best


def palette(path: Path, n: int = 6) -> list[dict]:
    """The image's main colours, measured: [{hex, name, share}] by share of pixels (quantised)."""
    from PIL import Image
    im = Image.open(path).convert("RGB")
    im.thumbnail((200, 200))
    q = im.quantize(colors=max(2, n), method=Image.Quantize.MEDIANCUT)
    counts = sorted(q.getcolors(), reverse=True)
    pal = q.getpalette()
    total = sum(c for c, _ in counts)
    out = []
    for count, idx in counts[:n]:
        r, g, b = pal[3 * idx: 3 * idx + 3]
        h = f"#{r:02X}{g:02X}{b:02X}"
        out.append({"hex": h, "name": colour_name(h), "share": round(count / total, 2)})
    return out


def is_reference_prompt(prompt: str) -> bool:
    text = prompt.lower()
    return any(w in text for w in REFERENCE_WORDS)


def asks_placement(prompt: str) -> bool:
    text = prompt.lower()
    return any(re.search(rf"\b{re.escape(w)}\b", text) for w in PLACE_WORDS)


def shrink_video(path: Path, out: Path, max_s: float = 24.0) -> dict:
    """A small copy of the video for the model (360p, 8 fps, at most max_s seconds), and its facts."""
    ffprobe = shutil.which("ffprobe")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not ffprobe:
        raise ValueError("ffmpeg is not installed, so the video cannot be read")
    probe = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration:stream=width,height",
                            "-of", "json", str(path)], capture_output=True, text=True)
    if probe.returncode != 0:
        raise ValueError(f"{path.name}: not a readable video")
    info = json.loads(probe.stdout or "{}")
    duration = float((info.get("format") or {}).get("duration") or 0)
    streams = [s for s in info.get("streams", []) if s.get("width")]
    w, h = (streams[0]["width"], streams[0]["height"]) if streams else (0, 0)
    r = subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(path), "-t", str(max_s), "-an",
                        "-vf", "scale='if(gt(iw,ih),-2,360)':'if(gt(iw,ih),360,-2)',fps=8",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "32", "-pix_fmt", "yuv420p", str(out)],
                       capture_output=True, text=True)
    if r.returncode != 0 or not out.is_file():
        raise ValueError(f"{path.name}: the video could not be converted ({r.stderr.strip()[:120]})")
    return {"duration_s": round(duration, 1), "width": w, "height": h, "analysed_s": round(min(duration, max_s), 1)}


IMAGE_ASK = """This image was attached to a request for a Color Block Jam video ad (a puzzle game: coloured blocks dragged out through gates of their colour). Describe it for the creative brief. Return ONLY JSON:
{"subject": "what the image shows, one line", "kind": "photo|illustration|game screenshot|logo|character|pattern|other", "style": "art style in a few words", "mood": "a few words", "dominant_colours": ["#RRGGBB", ...], "background_colour": "#RRGGBB", "text_seen": "any text in the image or empty", "composition": "layout in one line", "idea_for_an_ad": "one line: how a Color Block Jam ad could use this (as a look, a mood, a character, a hook)"}"""

VIDEO_ASK = """This video was attached as a reference for a Color Block Jam video ad (a puzzle game: coloured blocks dragged out through gates of their colour; a countdown clock). Describe its creative structure so the ad can adapt the CONCEPT (not copy it frame by frame). Return ONLY JSON:
{"what_it_shows": "one line", "game_or_product": "name or description", "structure": [{"from_s": 0, "to_s": 3, "what": "..."}], "hook": "the first thing shown or said", "captions_seen": ["..."], "ending": "win|fail|near-fail|cliffhanger|none", "pacing": "calm|normal|fast", "pace_change": "even|speeds up|slows down", "mood": "a few words", "visual_style": "a few words", "dominant_colours": ["#RRGGBB", ...], "cta": "the call to action or empty", "mistakes_shown": true, "concept_in_one_line": "the idea of the ad in one line", "how_to_adapt": "one line: the same concept with Color Block Jam gameplay"}"""


class VisionClient:
    def __init__(self, models=VISION_MODELS, key: str | None = None):
        from .planner import load_env
        load_env()
        self.key = key or os.environ.get("NVIDIA_API_KEY")
        if not self.key:
            raise ValueError("no NVIDIA_API_KEY: set it in the environment or in cbj-creative/.env")
        self.models = models
        self.last_model = None

    def describe(self, ask: str, part: dict) -> str:
        errors = []
        for model in self.models:
            body = {"model": model, "temperature": 0, "max_tokens": 1500,
                    "messages": [{"role": "user", "content": [{"type": "text", "text": ask}, part]}]}
            req = urllib.request.Request(NVIDIA_URL, data=json.dumps(body).encode(),
                                         headers={"Authorization": f"Bearer {self.key}",
                                                  "Content-Type": "application/json"})
            for attempt in range(2):
                try:
                    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
                        out = json.load(r)
                    self.last_model = model
                    return out["choices"][0]["message"].get("content") or ""
                except urllib.error.HTTPError as e:
                    errors.append(f"{model}: HTTP {e.code} {e.read()[:160]!r}")
                    if e.code not in (429, 500, 502, 503, 504):
                        break
                except (urllib.error.URLError, TimeoutError) as e:
                    errors.append(f"{model}: {e}")
                time.sleep(2 * (attempt + 1))
        raise ValueError("no multimodal model answered: " + "; ".join(errors[-2:]))


def _json_in(text: str) -> dict:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError(f"the model did not return JSON: {text[:120]!r}")
    return json.loads(text[start:end + 1], strict=False)


def analyse(path: Path, client=None, log=None) -> dict:
    """What a reference file is: {file, kind, palette, facts, notes, model, seconds} or {..., error}."""
    path = Path(path)
    ext = path.suffix.lower()
    kind = "image" if ext in IMAGE_EXT else "video" if ext in VIDEO_EXT else None
    out = {"file": path.name, "kind": kind}
    if kind is None:
        return {**out, "error": "not an image or a video"}
    t0 = time.time()
    try:
        if kind == "image":
            out["palette"] = palette(path)
            data = base64.b64encode(path.read_bytes()).decode()
            mime = {"jpg": "jpeg"}.get(ext[1:], ext[1:])
            part = {"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{data}"}}
            ask = IMAGE_ASK
        else:
            with tempfile.TemporaryDirectory() as tmp:
                small = Path(tmp) / "small.mp4"
                out["facts"] = shrink_video(path, small)
                data = base64.b64encode(small.read_bytes()).decode()
            part = {"type": "video_url", "video_url": {"url": f"data:video/mp4;base64,{data}"}}
            ask = VIDEO_ASK
        client = client or VisionClient()
        if log:
            log(f"reading {path.name} ({kind}) with a multimodal model...")
        out["notes"] = _json_in(client.describe(ask, part))
        out["model"] = getattr(client, "last_model", None)
    except Exception as e:  # reported in the brief, never guessed around
        out["error"] = str(e)[:300]
    out["seconds"] = round(time.time() - t0, 1)
    return out


def notes_text(a: dict) -> str:
    """The analysis as plain notes for the planner."""
    lines = [f"- {a['file']} ({a.get('kind')})"]
    if a.get("error"):
        lines.append(f"  COULD NOT BE ANALYSED: {a['error']}. Do not guess what it shows; say so in assumptions.")
        return "\n".join(lines)
    if a.get("palette"):
        lines.append("  measured palette (share of pixels): " + ", ".join(
            f"{p['hex']} {p['name']} {p['share']:.0%}" for p in a["palette"]))
    if a.get("facts"):
        f = a["facts"]
        lines.append(f"  video: {f.get('duration_s')} s, {f.get('width')}x{f.get('height')} (first {f.get('analysed_s')} s read)")
    if a.get("notes"):
        lines.append("  what a multimodal model saw: " + json.dumps(a["notes"], ensure_ascii=False))
    return "\n".join(lines)


def summary(a: dict) -> str:
    """One line for the user: what was read from the file."""
    if a.get("error"):
        return f"{a['file']}: could not be read ({a['error'][:80]})"
    n = a.get("notes") or {}
    if a.get("kind") == "image":
        pal = ", ".join(p["name"] for p in (a.get("palette") or [])[:4])
        return f"{a['file']}: {n.get('subject') or 'an image'}; colours {pal}; mood {n.get('mood') or '?'}"
    return (f"{a['file']}: {n.get('concept_in_one_line') or n.get('what_it_shows') or 'a video'}; ending "
            f"{n.get('ending') or '?'}, pacing {n.get('pacing') or '?'}")
