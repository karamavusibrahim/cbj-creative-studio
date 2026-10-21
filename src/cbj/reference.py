"""Reference analysis: what an attached image or video is, measured and described, for the planner.

The brief (p.6) asks for images as visual, style or composition references and for videos whose
concept, structure and pacing the tool should understand. The planner is a text model: it only
ever sees file names. So before it plans, each reference file is analysed here:
- an image: its palette is measured in code (PIL, no model) and a multimodal model describes it;
- a video (core requirement 4, 2026-10-16): the request is understood first, then the video is
  read for it (`read_video`):
  1. the reading plan: one call to the planner's own text model (`reading_plan`) decides from the
     request's words and the file's format facts what the multimodal model must look for (the
     focus, the questions, the fields required, what to ignore, what the request already fixes);
     an empty or invalid plan falls back to the word table (`focus_words`), which also checks it;
  2. the format step: any container, codec, orientation or size becomes one small H.264 copy of
     the WHOLE clip (`normalise_video`, at most about 200 frames); nothing about the content is
     measured yet;
  3. the reading: the prompt composed from the plan (`video_ask`) and the copy go to Gemini first
     (`gemini.GeminiVideoClient`, measured best on the tool's own creatives) and to NVIDIA build's
     multimodal model when Gemini fails (`video_client`), whose answer is checked in code
     (`validate_notes`) and asked again once with the problems quoted;
  4. the parts: the model's structure is the segmentation; only when the reading needs it (a hook,
     pacing or structure read, or a part read with low confidence) are cuts and motion measured on
     the copy (`video_facts`), the model's boundaries snapped to cuts and the pace change measured
     (`separate_parts`); the model's own seconds are kept beside the refined ones.
The result is written into the brief (planner.references) so the user can see what was read and
asked, and goes to the planner as plain notes; videoref.py then takes from it what the focus allows.
A failed analysis is reported, never guessed around.
"""

from __future__ import annotations

import base64
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path

NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
# Multimodal models on NVIDIA's hosted API, tried in order. The shared client (images, the viewer's
# review, route.locate_with_vision) keeps the omni model first, as the edit side had it; the 12b fallback
# is end of life (HTTP 410 on every call, 2026-10-16), so the live 120b super-vl is the fallback instead.
VISION_MODELS = ("nvidia/nemotron-3-nano-omni-30b-a3b-reasoning", "nvidia/nemotron-3.5-super-vl-120b-a12b")
# A reference video is read super-vl first (2026-10-16 live run: it takes a base64 mp4 as a video_url part,
# read a 30 s clip in 21 s and a 65 s clip in 9 s, and samples a fixed set of frames whatever the length;
# the omni model took 75-200 s and was busy now and then). Only read_video uses this order (video_client).
VIDEO_MODELS = ("nvidia/nemotron-3.5-super-vl-120b-a12b", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning")
TIMEOUT_S = 180  # an image or a contact sheet
VIDEO_TIMEOUT_S = 300  # a whole clip (the omni model needed up to 200 s)
RETRY_WAITS_S = (10, 20, 40)  # a busy model (HTTP 429, 503 "ResourceExhausted") is asked again after these waits
# A still of the board (the frame, the crop, the colour count, the sizes) is a short ask with its own budget (round 3,
# 2026-10-17: a 1920 px still made super-vl reason for its whole budget, "finish_reason 'length' with 16000 tokens" after
# the doubling, each try waiting out 300 s, then the omni model's 503s and timeouts; the board step took 1379-2413 s):
# one try per model, no doubling, no waits, and a model that gave no answer on a still is not asked again in that read
STILL_MAX_TOKENS = 4000
STILL_TIMEOUT_S = 150
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_EXT = {".mp4", ".mov", ".webm", ".m4v"}
# Words that make an attachment a reference (its look or idea), rather than an asset to place.
REFERENCE_WORDS = ("inspired", "inspiration", "reference", "like this", "similar", "match", "matching", "style",
                   "mood", "palette", "colours of", "colors of", "based on", "this concept", "this video",
                   "this clip", "this ad", "this creative", "this image", "this picture", "look like", "feel",
                   "vibe", "same look", "this look", "adapt", "version of", "recreate", "copy the", "like that",
                   "game like", "level like", "board like", "puzzle like", "design transfer", "style transfer", "same style",
                   "in the style of", "theme of", "colours from", "colors from", "similar to this", "similar to the")
# Words that ask for a picture to be put INTO the ad (then an image is an asset as well).
PLACE_WORDS = ("put", "insert", "place", "replace", "swap", "add", "use it as", "use this as", "as the logo",
               "as our logo", "on the end card", "beside the hook", "as the icon", "as the button", "as the cursor",
               "as the background", "instead of", "attached asset", "this asset", "attach")

# Named colours for the palette (sRGB), so the planner and the user read "pink", not "#FF4F8B".
NAMED = {"red": "#E53935", "crimson": "#B71C1C", "pink": "#FF69B4", "hot pink": "#FF1493", "rose": "#FF7F98",
         "light pink": "#FFD6EC", "orange": "#FF8000", "tangerine": "#FF8A3D", "peach": "#FFB86B",
         "yellow": "#FFCC04", "lemon": "#FFE45C", "butter": "#FFF3A0", "gold": "#D4A017", "lime": "#9ACD32",
         "green": "#14C517", "mint": "#5FD9A0", "sage": "#4FB58A", "dark green": "#065C13", "teal": "#008B8B",
         "pale green": "#BDE6AE", "light green": "#8FE08A", "turquoise": "#30D5C8", "sea blue": "#1E88B8", "coral": "#F36A5A",
         "salmon": "#FA8072", "cream": "#FFF4DC", "sand": "#E7CFA2", "lavender": "#E6D7FA", "ivory": "#FFFFF0",
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


def is_reference_prompt(prompt: str, edit: bool = False) -> bool:
    """Whether attached images are references to read. In an edit, "I like this creative" and
    "this (approved) creative / version" are about the version being edited, not an attachment."""
    text = prompt.lower()
    if edit:
        text = re.sub(r"\b(i|we)\s+(really\s+|do\s+)?(like|love|approve)\b[^.;!?,]*", " ", text)
        text = re.sub(r"\bthis\s+(exact\s+)?(approved\s+)?(creative|version|ad)\b", " ", text)
    return any(w in text for w in REFERENCE_WORDS)


def asks_placement(prompt: str) -> bool:
    text = prompt.lower()
    return any(re.search(rf"\b{re.escape(w)}\b", text) for w in PLACE_WORDS)


MAX_VIDEO_S = 120.0  # longer clips are refused at upload: the brief's references are 30-60 s ads
MAX_FRAMES = 200  # the model sees the whole clip in at most about this many frames
COPY_FPS = (2.0, 8.0)  # the copy's frame rate stays in this range: fps = max(2, min(8, 200 / duration))


def probe_video(path: Path) -> dict:
    """The format facts of a video, with nothing about its content: {duration_s, width, height (as
    displayed, the rotation applied), orientation, rotation, codec, size_mb}."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise ValueError("ffmpeg is not installed, so the video cannot be read")
    probe = subprocess.run([ffprobe, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
                           capture_output=True, text=True)
    if probe.returncode != 0:
        raise ValueError(f"{Path(path).name}: not a readable video")
    info = json.loads(probe.stdout or "{}")
    streams = [s for s in info.get("streams", []) if s.get("codec_type") == "video" and s.get("width")]
    if not streams:
        raise ValueError(f"{Path(path).name}: no video stream")
    s = streams[0]
    rotation = 0
    for sd in s.get("side_data_list") or []:
        if "rotation" in sd:
            rotation = int(round(float(sd["rotation"])))
    if not rotation and (s.get("tags") or {}).get("rotate"):
        rotation = int(float(s["tags"]["rotate"]))
    w, h = int(s["width"]), int(s["height"])
    if rotation % 180 != 0:
        w, h = h, w
    fmt = info.get("format") or {}
    duration = float(fmt.get("duration") or s.get("duration") or 0)
    return {"duration_s": round(duration, 2), "width": w, "height": h,
            "orientation": "portrait" if h > w else "landscape" if w > h else "square",
            "rotation": rotation % 360, "codec": s.get("codec_name"),
            "size_mb": round(int(fmt.get("size") or Path(path).stat().st_size) / 1e6, 1)}


def copy_fps(duration_s: float) -> float:
    """The copy's frame rate: the whole clip in at most about MAX_FRAMES frames, never under 2 or
    over 8 fps (rounded down to a tenth, so the frame count stays under the cap)."""
    if duration_s <= 0:
        return COPY_FPS[1]
    return max(COPY_FPS[0], min(COPY_FPS[1], math.floor(MAX_FRAMES / duration_s * 10) / 10))


def normalise_video(path: Path, out: Path) -> dict:
    """Any format in, one readable copy out (the format step, 2b): H.264, 360 px on the short side,
    the orientation applied, no audio, the WHOLE clip at copy_fps. Returns the format facts plus the
    copy's fps and frame count; analysed_s is the clip's duration (the whole video is read)."""
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise ValueError("ffmpeg is not installed, so the video cannot be read")
    facts = probe_video(path)
    if facts["duration_s"] <= 0:
        raise ValueError(f"{Path(path).name}: the video has no length")
    fps = copy_fps(facts["duration_s"])
    # ffmpeg applies the display rotation while decoding (autorotate), so iw/ih below are as displayed
    r = subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(path), "-an",
                        "-vf", f"scale='if(gt(iw,ih),-2,360)':'if(gt(iw,ih),360,-2)',fps={fps:g}",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "32", "-pix_fmt", "yuv420p",
                        "-movflags", "+faststart", str(out)], capture_output=True, text=True)
    if r.returncode != 0 or not Path(out).is_file():
        raise ValueError(f"{Path(path).name}: the video could not be converted ({r.stderr.strip()[:120]})")
    c = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                        "stream=nb_read_packets,width,height,codec_name", "-of", "json", str(out)],
                       capture_output=True, text=True)
    cs = (json.loads(c.stdout or "{}").get("streams") or [{}])[0]
    facts.update(analysed_s=facts["duration_s"], fps=fps, frames=int(cs.get("nb_read_packets") or 0),
                 copy={"codec": cs.get("codec_name"), "width": cs.get("width"), "height": cs.get("height")})
    return facts


shrink_video = normalise_video  # the old name; it no longer cuts the clip at 24 s


def video_facts(path: Path, small: Path | None = None) -> dict:
    """What can be measured about a reference video without a model: its cuts (ffmpeg's scene
    detector) and how much moves in each second (mean absolute frame difference), so the pacing and
    the structure the model describes can be checked against numbers, as the review does."""
    ffmpeg = shutil.which("ffmpeg")
    src = small if small is not None and small.is_file() else path
    if not ffmpeg:
        return {}
    r = subprocess.run([ffmpeg, "-v", "info", "-i", str(src), "-vf", "scdet=threshold=12:sc_pass=0,signalstats",
                        "-f", "null", "-"], capture_output=True, text=True)
    cuts = sorted({round(float(m), 1) for m in re.findall(r"lavfi\.scd\.time[:=]\s*([0-9.]+)", r.stderr)})
    # motion: the mean absolute difference between frames, per second (signalstats YDIF via showinfo is
    # noisy; the scene score is a cheap proxy, so a second pass reads frame differences directly)
    r2 = subprocess.run([ffmpeg, "-v", "info", "-i", str(src), "-vf", "fps=4,scale=160:-2,format=gray,tblend=all_mode=difference,signalstats,metadata=print:key=lavfi.signalstats.YAVG",
                         "-f", "null", "-"], capture_output=True, text=True)
    vals = [float(m) for m in re.findall(r"lavfi\.signalstats\.YAVG=([0-9.]+)", r2.stderr)]
    per_s = [round(sum(vals[i:i + 4]) / max(1, len(vals[i:i + 4])), 1) for i in range(0, len(vals), 4)]
    out = {"cuts_s": cuts[:40], "motion_per_s": per_s[:60]}
    if per_s:
        third = max(1, len(per_s) // 3)
        a, b = sum(per_s[:third]) / third, sum(per_s[-third:]) / third
        out["motion_first_third"], out["motion_last_third"] = round(a, 1), round(b, 1)
        out["pace_change"] = "speeds up" if b > a * 1.3 else "slows down" if a > b * 1.3 else "even"
        mean = sum(per_s) / len(per_s)
        out["pacing"] = "fast" if mean > 12 else "calm" if mean < 4 else "normal"
    return out


IMAGE_ASK = """This image was attached to a request for a Color Block Jam video ad (a puzzle game: coloured blocks dragged out through gates of their colour, on a grid board with a countdown clock). Describe it for the creative brief. Return ONLY JSON:
{"subject": "what the image shows, one line", "kind": "photo|illustration|game screenshot|logo|character|pattern|other", "style": "art style in a few words", "mood": "a few words", "dominant_colours": ["#RRGGBB", ...], "background_colour": "#RRGGBB", "text_seen": "any text in the image or empty", "composition": "layout in one line", "idea_for_an_ad": "one line: how a Color Block Jam ad could use this (as a look, a mood, a character, a hook)", "board": {"is_puzzle_board": true or false (a grid of coloured blocks or tiles, from this game or a similar puzzle), "grid_cols": integer or null, "grid_rows": integer or null, "block_count": integer or null (separate pieces a viewer can count), "block_colours": ["red", "blue", ...] (plain colour words), "walls": integer or null (fixed obstacle or hole cells), "doors_visible": true or false, "crowded": "packed|normal|spacious", "symmetric": true or false}}
The board object is only about a puzzle board seen in the image; for any other picture set is_puzzle_board to false and the rest to null."""

class VisionClient:
    """NVIDIA's hosted multimodal models, tried in order (VISION_MODELS by default, as the edit side and
    the viewer's review have always used them: the omni model first, 1500 tokens, 180 s). A busy model
    (HTTP 429 or 503) is asked again after each of RETRY_WAITS_S before the next model is tried; a
    server error (500, 502, 504) once after 2 s. With the defaults an empty answer is returned as it
    is and a timeout or a broken connection is tried once more after 2 s, as before. A video reading
    (`long_answers`, video_client) reads super-vl first, which reasons before it answers and can spend
    the whole budget doing so: an answer cut off with no content (finish_reason "length") is asked once
    more with the budget doubled and "the JSON object only", and a model with no answer or no answer
    in time is skipped. `last_model` is the model that answered; `errors` what failed on the way."""

    def __init__(self, models=VISION_MODELS, key: str | None = None, max_tokens: int = 1500, timeout_s: float = TIMEOUT_S,
                 long_answers: bool = False):
        from .planner import load_env
        load_env()
        self.key = key or os.environ.get("NVIDIA_API_KEY")
        if not self.key:
            raise ValueError("no NVIDIA_API_KEY: set it in the environment or in cbj-creative/.env")
        self.models = models
        self.max_tokens = max_tokens
        self.timeout_s = timeout_s
        self.long_answers = long_answers
        self.last_model = None
        self.errors: list[str] = []  # every failure on the way to an answer, for the analysis (analysis["errors"])
        self.sleep = time.sleep  # the waits between tries (tests replace it)
        self._still = False  # a still's short ask (describe_still): STILL_MAX_TOKENS, STILL_TIMEOUT_S, one try a model
        self.still_dead: set[str] = set()  # models that gave no answer on a still: not asked again for stills

    def _post(self, body: dict) -> dict:
        req = urllib.request.Request(NVIDIA_URL, data=json.dumps(body).encode(),
                                     headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=STILL_TIMEOUT_S if self._still else self.timeout_s) as r:
            return json.load(r)

    def describe_still(self, ask: str, part: dict, path: Path | None = None) -> str:
        """A still's short ask (the board's frame, crop, colour count, sizes): STILL_MAX_TOKENS with no doubling,
        STILL_TIMEOUT_S, one try per model, and a model that answered nothing on a still before (a reasoning cut off, a
        timeout) is skipped. The whole clip and the ending keep describe's budgets and retries."""
        self._still = True
        try:
            return self.describe(ask, part, path)
        finally:
            self._still = False

    def describe(self, ask: str, part: dict, path: Path | None = None) -> str:
        errors: list[str] = []
        try:
            for model in self.models:
                if self._still and model in self.still_dead:
                    errors.append(f"{model}: skipped on this still (no answer on an earlier still of this read)")
                    continue
                text = self._answer(model, ask, part, errors)
                if text is not None:
                    self.last_model = model
                    return text
            raise ValueError("no multimodal model answered: " + "; ".join(errors[-3:]))
        finally:
            self.errors += errors

    def _answer(self, model: str, ask: str, part: dict, errors: list[str]) -> str | None:
        """One model's answer, or None with the reason added to `errors`."""
        budget, question, waits, cut, server_retry = self.max_tokens, ask, list(RETRY_WAITS_S), False, True
        net_retry = not self.long_answers
        if self._still:  # one try, a smaller budget, no doubling (STILL_MAX_TOKENS)
            budget, waits, cut, server_retry, net_retry = STILL_MAX_TOKENS, [], True, False, False
        while True:
            body = {"model": model, "temperature": 0, "max_tokens": budget,
                    "messages": [{"role": "user", "content": [{"type": "text", "text": question}, part]}]}
            try:
                out = self._post(body)
            except urllib.error.HTTPError as e:
                errors.append(f"{model}: HTTP {e.code} {e.read()[:160]!r}")
                if e.code in (429, 503) and waits:
                    self.sleep(waits.pop(0))
                    continue
                if e.code in (500, 502, 504) and server_retry:
                    server_retry = False
                    self.sleep(2)
                    continue
                return None
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                errors.append(f"{model}: {e}")
                if net_retry:  # as before for the shared client: once more after 2 s
                    net_retry = False
                    self.sleep(2)
                    continue
                if self._still:
                    self.still_dead.add(model)  # no answer in the still's time: not asked again for stills
                return None
            choice = (out.get("choices") or [{}])[0]
            text = (choice.get("message") or {}).get("content") or ""
            if text.strip() or not self.long_answers:
                return text
            if choice.get("finish_reason") == "length" and not cut:
                # the reasoning spent the budget before the answer began
                cut, budget = True, budget * 2
                question = ask + "\nAnswer with the JSON object only."
                continue
            errors.append(f"{model}: no answer (finish_reason {choice.get('finish_reason')!r} with {budget} tokens)")
            if self._still:
                self.still_dead.add(model)
            return None


def nvidia_video_client() -> "VisionClient":
    """NVIDIA build as a video reader: super-vl first, VIDEO_MAX_TOKENS, VIDEO_TIMEOUT_S (the fallback since 2026-10-16)."""
    return VisionClient(models=VIDEO_MODELS, max_tokens=VIDEO_MAX_TOKENS, timeout_s=VIDEO_TIMEOUT_S, long_answers=True)


def _gemini_client():
    from .gemini import GeminiVideoClient
    return GeminiVideoClient()


def video_client() -> "VideoReader":
    """The client a reference video is read with: Gemini first, NVIDIA build when Gemini fails (VideoReader)."""
    return VideoReader()


class VideoReader:
    """A reference video's reader (2026-10-16, measured on the tool's own 12 creatives: Gemini 3.5 Flash-Lite read
    the ending, hook, call to action, captions and mechanics in 12 of 12 and the structure in 8, in 4-26 s; NVIDIA's
    super-vl the ending in 9 and the structure in 5, in 50-250 s with server errors). Each call tries Gemini
    (gemini.GeminiVideoClient) and then NVIDIA build (nvidia_video_client) when Gemini raises: no key, or no Gemini
    model answered. One interface for read_video: describe(ask, part, path), `last_model`, `errors` (both readers'
    failures, in order), `reader` ("gemini" or "nvidia", the one that answered), `usage` (Gemini's token counts)."""

    ORDER = ("gemini", "nvidia")

    def __init__(self, gemini=None, nvidia=None, order=None):
        self._make = {"gemini": gemini or _gemini_client, "nvidia": nvidia or nvidia_video_client}
        self._clients: dict = {}
        self.errors: list[str] = []
        self.last_model = None
        self.reader = None
        self.order, self.order_from = (tuple(order), "given") if order else reader_order(self.ORDER)

    @property
    def usage(self) -> list[dict]:
        return list(getattr(self._clients.get("gemini"), "usage", None) or [])

    def _client(self, name: str):
        """The reader `name`, made once; None (with the reason in errors) when it cannot be made, such as a missing key."""
        if name not in self._clients:
            try:
                self._clients[name] = self._make[name]()
            except Exception as e:
                self._clients[name] = None
                self.errors.append(f"{name}: {str(e)[:200]}")
        return self._clients[name]

    def describe_still(self, ask: str, part: dict, path: Path | None = None) -> str:
        """A still's short ask: each reader's own still budget when it has one (VisionClient.describe_still)."""
        return self.describe(ask, part, path, still=True)

    def describe(self, ask: str, part: dict, path: Path | None = None, still: bool = False) -> str:
        for name in self.order:
            c = self._client(name)
            if c is None:
                continue
            seen = len(getattr(c, "errors", None) or [])
            try:
                text = (c.describe_still if still and hasattr(c, "describe_still") else c.describe)(ask, part, path)
            except Exception as e:
                new = list((getattr(c, "errors", None) or [])[seen:])
                self.errors += new or [f"{name}: {str(e)[:200]}"]
                continue
            self.errors += list((getattr(c, "errors", None) or [])[seen:])
            self.last_model, self.reader = getattr(c, "last_model", None), name
            return text
        raise ValueError("no video reader answered: " + "; ".join(self.errors[-3:]))


READERS = ("gemini", "nvidia")


def reader_order(default=VideoReader.ORDER) -> tuple[tuple[str, ...], str]:
    """The readers' order: CBJ_VIDEO_READER ("nvidia,gemini" or "gemini,nvidia"; an operator's override, round 3,
    2026-10-17, when Gemini's free quota is used up), else `default`. A reader the variable leaves out is tried last.
    Returns (the order, "CBJ_VIDEO_READER" or "default")."""
    raw = [x.strip().lower() for x in (os.environ.get("CBJ_VIDEO_READER") or "").split(",") if x.strip()]
    named = [x for x in dict.fromkeys(raw) if x in READERS]
    if not named:
        return tuple(default), "default"
    return tuple(named + [x for x in READERS if x not in named]), "CBJ_VIDEO_READER"


def still_ask(client):
    """The client's short ask for a still (VideoReader / VisionClient describe_still), or describe for any other."""
    return getattr(client, "describe_still", None) or client.describe


class _Still:
    """A client seen through its still ask, for _ask_json: describe() is describe_still(); the rest is the client's."""

    def __init__(self, client):
        self._c = client

    def describe(self, ask: str, part: dict, path: Path | None = None) -> str:
        return still_ask(self._c)(ask, part, path)

    def __getattr__(self, name):
        return getattr(self._c, name)


def first_reader(client) -> str | None:
    """The reader a client tries first: a VideoReader's order, "nvidia" for NVIDIA's own client, else None."""
    order = getattr(client, "order", None)
    if isinstance(order, (list, tuple)) and order:
        return order[0]
    return "nvidia" if isinstance(client, VisionClient) else None


def reader_of(model: str | None) -> str | None:
    """Which reader a model name belongs to (for a client that does not say it)."""
    m = str(model or "")
    return "gemini" if m.startswith("gemini") else "nvidia" if m.startswith("nvidia/") else None


def _json_in(text: str) -> dict:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError(f"the model did not return JSON: {text[:120]!r}")
    try:
        return json.loads(text[start:end + 1], strict=False)
    except json.JSONDecodeError:
        # a note after the object ("Extra data"), or braces inside it: the first whole object counts
        obj, _ = json.JSONDecoder(strict=False).raw_decode(text[start:])
        return obj


def _ask_json(client, ask: str, part: dict, path: Path | None, raw: list | None = None) -> dict:
    """The model's JSON answer; prose or broken JSON instead (the hosted model now and then) is asked for
    once more, strictly. `raw` collects the answers' text, so a reading that fails can show what came back."""
    text = None
    try:
        text = client.describe(ask, part, path)
        return _json_in(text)
    except ValueError:
        if raw is not None and text is not None:
            raw.append(text[:3000])
        text = client.describe(ask + "\nAnswer with the JSON object ONLY, starting with '{'.", part, path)
        try:
            return _json_in(text)
        except ValueError:
            if raw is not None:
                raw.append(text[:3000])
            raise


def analyse(path: Path, client=None, log=None, prompt: str | None = None, planner=None) -> dict:
    """What a reference file is: {file, kind, palette, facts, notes, model, seconds} or {..., error}.
    A video is read for the request (`read_video`: `prompt` and the planner's text client `planner`
    make the reading plan); an image is measured and described."""
    path = Path(path)
    ext = path.suffix.lower()
    kind = "image" if ext in IMAGE_EXT else "video" if ext in VIDEO_EXT else None
    out = {"file": path.name, "kind": kind}
    if kind is None:
        return {**out, "error": "not an image or a video"}
    if kind == "video":
        return read_video(path, prompt or "", planner=planner, client=client, log=log)
    t0 = time.time()
    try:
        out["palette"] = palette(path)
        data = base64.b64encode(path.read_bytes()).decode()
        mime = {"jpg": "jpeg"}.get(ext[1:], ext[1:])
        part = {"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{data}"}}
        if client is None:
            from . import llm
            client = llm.vision_client()
        if log:
            log(f"reading {path.name} (image) with a multimodal model...")
        out["notes"] = _ask_json(client, IMAGE_ASK, part, path)
        out["model"] = getattr(client, "last_model", None)
    except Exception as e:  # reported in the brief, never guessed around
        out["error"] = str(e)[:300]
    out["seconds"] = round(time.time() - t0, 1)
    return out


PURPOSES = ("hook", "gameplay", "mistake", "near_fail", "fail", "victory", "replay", "payoff", "question", "end_card", "other")
GAMEPLAY_PURPOSES = ("gameplay", "mistake", "near_fail", "payoff")  # the live play (a replay is not counted)


# What a model calls a part, read as the tool's purpose (2026-10-16 live run: "identity", "reveal", "product
# info", "ad_end_card", "result", "mistake & hint", "tension", "failure" came back on confident readings).
# A label is never a reason to reject a reading: an exact word first, then the first rule whose words
# the label contains, else "other"; the model's own label is kept beside it (purpose_raw).
PURPOSE_WORDS = {"nearfail": "near_fail", "near_miss": "near_fail", "win": "victory", "won": "victory", "cta": "end_card",
                 "endcard": "end_card", "call_to_action": "end_card", "outro": "end_card", "lose": "fail",
                 "loss": "fail", "error": "mistake", "wrong_move": "mistake", "play": "gameplay", "intro": "hook",
                 "opening": "hook"}
PURPOSE_RULES = (  # in this order: "mistake & hint" is a mistake, "replay of the near fail" a replay, "play now" not play
    ("mistake", re.compile(r"mistake|wrong|\berror|\boops|\bblunder", re.I)),
    ("replay", re.compile(r"replay|\bagain\b|slow[ _-]?mo|slow motion|rewind|instant replay", re.I)),
    ("hook", re.compile(r"hook|intro|opening|teaser|attention|challenge", re.I)),
    ("question", re.compile(r"question|what would you|would you|cliff[ _]?hanger|your move|can you see", re.I)),
    ("payoff", re.compile(r"cascade|satisf|all (the )?(blocks )?(leave|fly|clear|exit)|chain|streak|one after another|in a row|payoff|pay[ _]off", re.I)),
    ("near_fail", re.compile(r"\bnear|almost|tension|tense|close[ _]call|last[ _]seconds?|clutch|nail[ _]?biter|hurry|\brush", re.I)),
    ("fail", re.compile(r"fail|\blos(e|es|ing|t)\b|\bloss|game[ _]over|out[ _]of[ _]time|time[ _]?out|\bdefeat", re.I)),
    ("victory", re.compile(r"result|reveal|\bwins?\b|\bwon\b|success|complete|victory|cleared|solved|celebrat|\bdone\b", re.I)),
    ("end_card", re.compile(r"cta|end[ _]?card|call[ _]to[ _]action|\blogo|identity|product|brand|download|install|"
                            r"play[ _]now|store|outro|packshot|tagline", re.I)),
    ("gameplay", re.compile(r"play|level|puzzle|solv|gameplay|moves?|demo|action", re.I)),
)


def purpose_of(raw) -> str:
    """A part's purpose, always one of PURPOSES: "Near-fail" -> near_fail, "win" -> victory, "ad_end_card"
    -> end_card, "mistake & hint" -> mistake, an unknown label -> other."""
    p = str(raw if raw is not None else "other").strip().lower().replace("-", "_").replace(" ", "_")
    p = PURPOSE_WORDS.get(p, p)
    if p in PURPOSES:
        return p
    words = p.replace("_", " ")
    return next((purpose for purpose, rx in PURPOSE_RULES if rx.search(words)), "other")


def _unit(x) -> float | None:
    """A 0-1 number from the model (a number or a numeric string), or None."""
    if isinstance(x, bool) or x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def structure(raw, duration_s=None) -> list[dict]:
    """The reference's segments as the brief keeps them: {from_s, to_s, purpose, what, captions,
    emphasis, evidence_s, confidence}, in order, purposes from PURPOSES (the brief p.6: the creative
    structure and pacing to adapt). The model's own label, when it is not the purpose's name, is
    kept as purpose_raw (the card shows it); a confidence outside 0-1 is clamped."""
    out = []
    for seg in raw if isinstance(raw, list) else []:
        if not isinstance(seg, dict):
            continue
        try:
            f, t = float(seg.get("from_s", 0)), float(seg.get("to_s", 0))
        except (TypeError, ValueError):
            continue
        if duration_s:
            f, t = max(0.0, min(f, float(duration_s))), max(0.0, min(t, float(duration_s)))
        if t <= f:
            continue
        purpose = purpose_of(seg.get("purpose"))
        raw_label = str(seg.get("purpose_raw") or seg.get("purpose") or "").strip()[:60]  # a stored part keeps its own
        caps = seg.get("captions") if isinstance(seg.get("captions"), list) else []
        ev = []
        for x in seg.get("evidence_s") if isinstance(seg.get("evidence_s"), list) else []:
            v = _unit(x)
            if v is not None:
                ev.append(round(v, 1))
        conf = _unit(seg.get("confidence"))
        out.append({"from_s": round(f, 1), "to_s": round(t, 1), "purpose": purpose, "what": str(seg.get("what") or "")[:160],
                    "captions": [str(c)[:80] for c in caps if str(c).strip()][:6],
                    "emphasis": str(seg.get("emphasis") or "")[:120], "evidence_s": ev[:8],
                    "confidence": None if conf is None else round(min(1.0, max(0.0, conf)), 2),
                    **({"purpose_raw": raw_label} if raw_label and _label(raw_label) != purpose else {}),
                    **({"split": str(seg["split"])} if seg.get("split") else {})})
    return long_hooks(sorted(out, key=lambda x: x["from_s"]), duration_s)


HOOK_MAX_S, HOOK_MAX_SHARE = 3.0, 0.25  # a "hook" part longer than both is the play with a caption over it
HOOK_KEEP_S = 1.5  # of such a part, this much stays the hook


def long_hooks(segs: list[dict], duration_s=None) -> list[dict]:
    """A "hook" part longer than max(HOOK_MAX_S, HOOK_MAX_SHARE of the clip) is play (round 3, case 18: another game's
    15 s ad read "0-12 s hook; 12-14.9 s end card", and the ad took a 12 s hook and a 13 s play): its first HOOK_KEEP_S
    stay the hook (with its captions), the rest is gameplay, both marked `split` with the reason. Idempotent."""
    dur = float(duration_s or 0) or max((float(s.get("to_s") or 0) for s in segs), default=0.0)
    limit = max(HOOK_MAX_S, HOOK_MAX_SHARE * dur)
    out = []
    for s in segs:
        f, t = float(s.get("from_s") or 0), float(s.get("to_s") or 0)
        if s.get("purpose") != "hook" or t - f <= limit:
            out.append(s)
            continue
        cut = round(f + HOOK_KEEP_S, 1)
        why = (f"a {t - f:g} s hook is longer than a hook ({limit:.1f} s at most: {HOOK_MAX_S:g} s or "
               f"{HOOK_MAX_SHARE:.0%} of the clip), so after its first {HOOK_KEEP_S:g} s it is play")
        ev = [x for x in s.get("evidence_s") or [] if isinstance(x, (int, float))]
        out.append({**s, "to_s": cut, "evidence_s": [x for x in ev if x < cut], "split": why})
        out.append({**s, "from_s": cut, "purpose": "gameplay", "captions": [], "evidence_s": [x for x in ev if x >= cut],
                    "purpose_raw": str(s.get("purpose_raw") or "hook"), "split": why})
    return out


def structure_text(segs: list[dict]) -> str:
    return "; ".join(f"{x['from_s']:g}-{x['to_s']:g} s {x['purpose'].replace('_', '-')}" + (f" ({x['what']})" if x.get("what") else "")
                     for x in segs or [])


def notes_text(a: dict) -> str:
    """The analysis as plain notes for the planner. A targeted video read gives only the fields of
    its focus (the planner takes nothing else from it); a low-confidence read says so."""
    lines = [f"- {a['file']} ({a.get('kind')})"]
    if a.get("error"):
        lines.append(f"  COULD NOT BE ANALYSED: {a['error']}. Do not guess what it shows; say so in assumptions.")
        return "\n".join(lines)
    if a.get("skipped"):
        lines.append(f"  NOT READ: {a['skipped']}. Take nothing from it.")
        return "\n".join(lines)
    if a.get("palette"):
        lines.append("  measured palette (share of pixels): " + ", ".join(
            f"{p['hex']} {p['name']} {p['share']:.0%}" for p in a["palette"]))
    if a.get("facts"):
        f = a["facts"]
        lines.append(f"  video: {f.get('duration_s')} s, {f.get('width')}x{f.get('height')} {f.get('orientation') or ''}".rstrip()
                     + (f"; the whole clip was read ({f.get('frames')} frames at {f.get('fps'):g} fps)" if f.get("fps") else ""))
        if f.get("motion_per_s"):
            lines.append(f"  measured: cuts at {f.get('cuts_s') or 'none'} s; pacing {f.get('pacing')}, {f.get('pace_change')} "
                         f"(motion first third {f.get('motion_first_third')}, last third {f.get('motion_last_third')})")
    focus = a.get("focus") or []
    if a.get("plan") and a.get("level") == "none":  # read in full (2026-10-17), but the request asks nothing of it
        lines.append(f"  read, but the request asks nothing of it ({a['plan'].get('why') or 'no focus'}): take nothing from it")
        return "\n".join(lines)
    if a.get("plan"):
        p = a["plan"]
        lines.append(f"  read in full; applied: {focus_text(focus)} ({a.get('level')}): {p.get('why') or ''}".rstrip(": "))
        if a.get("level") == "targeted":
            lines.append(f"  take from it only {focus_text(focus)}; everything else follows the request")
    if a.get("parts_dropped"):
        lines.append(f"  {a['parts_dropped']}: no part timings; the rest of the reading stands")
    if a.get("notes"):
        n = a["notes"]
        if isinstance(n, dict) and a.get("level") == "targeted":
            keep = {x for f in focus for x in FOCUS_FIELDS.get(f, ())} | {"confidence", "roles"}
            n = {k: v for k, v in n.items() if k in keep}
        if isinstance(n, dict) and n.get("structure"):
            lines.append("  structure (purpose per segment): " + structure_text(n["structure"]))
        if isinstance(n, dict):
            n = {k: v for k, v in n.items() if k != "structure_model"}
        lines.append("  what a multimodal model saw: " + json.dumps(n, ensure_ascii=False))
    return "\n".join(lines)


def summary(a: dict) -> str:
    """One line for the user: what was read from the file."""
    if a.get("error"):
        return f"{a['file']}: could not be read ({a['error'][:80]})"
    if a.get("skipped"):
        return f"{a['file']}: not read ({a['skipped']})"
    n = a.get("notes") or {}
    if a.get("kind") == "image":
        pal = ", ".join(p["name"] for p in (a.get("palette") or [])[:4])
        return f"{a['file']}: {n.get('subject') or 'an image'}; colours {pal}; mood {n.get('mood') or '?'}"
    read = f"; read in full, applied: {focus_text(a.get('focus') or [])} ({a.get('level')})" if a.get("plan") else ""
    low = "; read with low confidence" if a.get("low_confidence") else ""
    return (f"{a['file']}: {n.get('concept_in_one_line') or n.get('what_it_shows') or 'a video'}; ending "
            f"{n.get('ending') or '?'}, pacing {n.get('pacing') or '?'}{read}{low}")


# ---------- reading a video for the request (core requirement 4, 2026-10-16) ----------

FOCI = ("concept", "hook", "pacing", "captions", "ending", "look", "structure", "board", "board_colours", "screen")
LEVELS = ("none", "targeted", "full")
SNAP_S = 1.5  # a model boundary moves to a measured cut this close
LOW_CONFIDENCE = 0.4  # an overall confidence under this is shown on the card and the row; it decides nothing
CALM_DPS, FAST_DPS = 0.25, 0.6  # drags a second over the gameplay: calm under, fast over (as audit.pace_of_play)
PLAUSIBLE_DPS = 1.0  # more counted moves than about one a second of gameplay are not a count: the word is the model's
EDGE_S = 0.5  # the model's seconds are rounded: a part may end this far past the clip before it is rejected
VIDEO_MAX_TOKENS = 8000  # a full reading (parts, captions, adaptation) after the model's reasoning

# The board shapes the game's generator makes (generate.holes_for), as the reading's schema describes them (2026-10-17).
# (v9, 2026-10-17: "two rooms ... with a two-cell gap" for the door read every hourglass as a door: the rooms of an
# hourglass are a top and a bottom half, a door's are a left and a right one.)
BOARD_SHAPES = {
    "open": "a plain rectangle, every cell playable",
    "narrow_center": "an hourglass: the middle rows are wall across the board's whole width except a two-cell passage in "
                     "the centre, so a top half and a bottom half are joined only there",
    "door": "two rooms side by side, left and right, split by a wall column down the middle with a two-cell door in it",
    "holes": "a rectangle with one or a few separate wall pieces inside it (a single cell or a short wall), the rest open",
    "cross": "a plus shape, the four corners cut away",
    "ring": "a big hole in the middle with a band of cells all round it",
    "lanes": "wall columns between two-cell lanes, joined at the top and the bottom",
}

# The analysis schema (2d). The keys of the first two lines keep the names and meaning they had
# before 2026-10-16 (the planner and videoref read them); the rest are new.
NOTE_FIELDS = {
    "what_it_shows": '"one line"',
    "game_or_product": '"name or description"',
    "concept_in_one_line": '"the idea of the ad in one line"',
    "how_to_adapt": '"one line: the same concept with Color Block Jam gameplay"',
    "hook": '"the first thing shown or said, and what it does (a question, a challenge, a dare)"',
    "captions_seen": ('["every caption the ad overlays, in order, its words exactly as shown, letter for letter (never a '
                      'description of it), the end card\'s title, its fact line and its button included"]'),
    "screen_text": ('["the gameplay\'s HUD only: the level label, the clock, +50, REPLAY, Continue, Level Completed, Level '
                    'Failed, Out of time (the end card\'s title, fact line and button are captions, not screen_text)"]'),
    "ending": ('"win | near-fail (a win with 5 s or less on the clock) | time-out (the out-of-time screen) | cliffhanger '
               '(cut before the result, often with a question) | stopped (the clip stops mid-level: no result, no question) | none"'),
    "hud": ('{"level": "the level label at the first frame of play, as shown on screen, or null when none is shown", '
            '"clock": "the countdown clock at the first frame of play, MM:SS, or null when none is shown", "clock_last": '
            '"the last clock reading, MM:SS, or null"}'),
    "extras_seen": ('["anything on screen Color Block Jam does not have, named one by one: booster buttons (freeze, hammer, '
                    'vacuum...), power-ups, characters, other menus; [] when none"]'),
    "framing": ('{"board_share": <the share of the frame\'s width the board takes at the first frame of play, 0-1>, '
                '"hand_cursor": true or false (a hand or finger pointer is shown), "other_items": ["anything else on screen '
                'besides the board and the HUD: buttons, banners, characters; [] when none"]}'),
    "pacing": '"calm|normal|fast"',
    "pace_change": '"even|speeds up|slows down"',
    "moves_by_third": ("[first, middle, last] (how many moves, one drag each, you count in the first, the middle and the last "
                       "third of the gameplay parts only; never the replay)"),
    "mood": '"a few words"',
    "visual_style": '"a few words"',
    "dominant_colours": '["#RRGGBB", ...]',
    "cta": '"the call to action, or empty"',
    "mistakes": ('[{"at_s": <seconds>, "what": "the wrong move"}] (one entry per wrong move the player visibly corrects, or '
                 'a block stopped by another block; not a drag the clock cuts short, not a hesitation; [] when none)'),
    "mistakes_shown": "true or false (is any wrong move shown at all)",
    "structure": ('[{"from_s": <seconds>, "to_s": <seconds>, "purpose": '
                  '"hook|gameplay|mistake|near_fail|fail|victory|replay|payoff|question|end_card|other", "what": "what is '
                  'seen", "captions": ["the captions on screen in this part, word for word"], "emphasis": "what the part '
                  'stresses (a zoom, a red clock, slow motion) or empty", "evidence_s": [seconds where it is seen], '
                  '"confidence": 0.0-1.0}] (a part ends where what is on screen changes: a cut, a new screen, a caption '
                  'appearing or leaving; the hook part ends when the opening caption leaves the screen; replay: a moment '
                  'shown again; payoff: the satisfying run of exits; question: the cut before the result that asks the viewer)'),
    "roles": '["concept"|"hook"|"pacing"|"captions"|"ending"|"look"|"structure"|"board"|"screen"] (what this reading was for)',
    "board": ('{"columns": <cells across at the first frame of play>, "rows": <cells down>, "shape": "' + "|".join(BOARD_SHAPES) +
              '" (' + "; ".join(f"{k}: {v}" for k, v in BOARD_SHAPES.items()) + '; read from the board\'s outline and its '
              'wall cells only: a wall cell (often a grey or dark cell) is part of the board no block can enter, so it makes '
              'the shape and is never an obstacle; another game\'s obstacle (a bubble, ice, a crate, a counter) is not a wall '
              'and never makes a shape), "blocks": <the coloured blocks at the first frame '
              'of play, counted one by one; never an obstacle>, "colours": ["each distinct block colour ONCE, in order of '
              'appearance, named as you see it: two colours that look different get different names (purple and magenta, '
              'blue and light blue, green and dark green, red and pink)"], "pieces": "small (1-2 cells) | long (bars of 3-4) | big (2x2 and larger) | varied (small, long and '
              'L-shaped together) | mixed (the usual mix)", "gates_sides": <how many of the board\'s four sides have gates>, '
              '"symmetric": true or false (do the pieces\' shapes and places mirror each other left-right or top-bottom, '
              'even where the mirrored pieces have different colours), "wall_cells": <how many wall cells are inside the '
              'board (cells no block can enter, not the rim around it); 0 when none>, '
              '"obstacles": ["anything inside the board that is neither a block nor a wall cell, named, with its count or '
              'number; [] when there is none"], "busy": "simple|medium|busy (how full and tangled the board looks)"}'),
    "mechanics_seen": '["each mechanic of the game shown, in your words"]',
    "adaptation": ('{"transferable": ["what an ad for this game can take"], "translation": ["how it becomes Color Block '
                   'Jam gameplay"], "do_not_copy": ["what must not be copied"]}'),
    "confidence": "0.0-1.0 (how sure you are of this reading as a whole)",
}
# The fields each focus needs; a plan with no fields of its own requires these.
FOCUS_FIELDS = {
    "concept": ("concept_in_one_line", "structure", "hook", "ending", "mistakes", "moves_by_third", "captions_seen",
                "dominant_colours", "mechanics_seen", "adaptation", "board"),
    "hook": ("hook", "structure", "captions_seen"),
    "pacing": ("moves_by_third", "pacing", "pace_change", "structure"),
    "captions": ("captions_seen", "structure", "cta"),
    "ending": ("ending", "mistakes", "mistakes_shown", "structure"),
    "look": ("dominant_colours", "visual_style", "mood"),
    "structure": ("structure", "cta"),
    "board": ("board", "mechanics_seen"),
    "screen": ("framing", "hud"),
    "board_colours": ("board",),
}
# The questions of the word table's plan (the fallback), per focus.
FOCUS_QUESTIONS = {
    "concept": ("What is the idea of this ad in one line, and what makes a viewer keep watching?",
                "What happens in each part, with the seconds: the opening, the play, the moment that goes wrong or gets "
                "tense, the payoff, the end card?",
                "How does it end: a win, a near miss, a fail, or a cut before the end?",
                "How many moves (drags) do you count in each third of the gameplay, not counting a replay?",
                "What do the captions say and what does each one do (challenge, instruction, urgency, result, call to action)?",
                "What is the look: the colours, the mood, where the text sits?",
                "Which mechanics of the other game are shown (name them; one this game does not have is not used)?"),
    "hook": ("What happens in the first seconds, with the seconds, and what makes a viewer stop scrolling?",
             "What does the opening say or show: a question, a challenge, a dare, a surprise?"),
    "pacing": ("How many moves (drags) do you count in the first, the middle and the last third of the gameplay, not "
               "counting a replay?",),
    "captions": ("What does each caption say, when, and what does it do (challenge, instruction, urgency, result, call to action)?",),
    "ending": ("How does it end: a win, a near miss, a fail, or a cut before the end, and at which second?",
               "Which wrong moves are shown, and at which seconds?"),
    "look": ("What is the look: the main colours (as #RRGGBB), the mood, where the text sits?",),
    "structure": ("What are the parts in order, with their seconds and what each one is for?",
                  "Is any moment shown again (a replay)?"),
    "board": (),  # the fixed BOARD_QUESTION, asked whenever the focus covers the board
    "screen": (),  # the general reading's framing question, asked of every reading
    "board_colours": (),  # the fixed BOARD_QUESTION asks the blocks' colours
}
FOCUS_NAMES = {f: f"the {f}" for f in FOCI}
# The board is no longer ignored (2026-10-17, the owner's test: a reference's simple open board came out as the showcase
# narrow centre): the level's type is read from it (videoref.board_of), never its exact cells.
DEFAULT_IGNORE = ("the other game's characters and art", "its exact caption wording")
# The word table (2a): the fallback for the reading plan and its sanity check, in the table's order.
# "Inspired by this video's hook" names the hook, not the concept (2026-10-16 creative run, case 10).
_NOT_ITS_PART = (r"(?!'s\s+(?:hooks?|opening|intro|pac(?:e|ing)|tempo|rhythm|captions?|texts|copy|ending|finish|payoff|look|style|"
                 r"colou?rs|palette|mood|structure|sequence|parts|board|level|layout|grid|blocks|pieces)\b)")
FOCUS_WORDS = (
    ("concept", re.compile(r"\bversion of (this|that|the|its)\b" + _NOT_ITS_PART + r"|\badapt\w*\b|"
                           r"\blike (this|that|the) (video|clip|ad|reference)\b" + _NOT_ITS_PART + r"|"
                           r"\bsame idea\b|\brecreate (the|this|that|its) concept\b|"
                           r"\binspired by (this|that|the) (video|clip|ad)\b" + _NOT_ITS_PART + r"|"
                           r"\b(this|that|the|its) concept\b", re.I)),
    ("hook", re.compile(r"\bhooks?\b|\bopening\b|\bfirst (few )?seconds\b|\bintro\b", re.I)),
    ("pacing", re.compile(r"\bpac(e|ing)\b|\btempo\b|\brhythm\b|\bspeed\w*\b|\bas (fast|slow|quick)\b", re.I)),
    ("captions", re.compile(r"\bcaptions?\b|\btexts\b|\b(its|the|same) copy\b|\bwhat it says\b|\bthe lines\b", re.I)),
    ("ending", re.compile(r"\bending\b|\bhow it ends\b|\bthe finish\b|\bthe payoff\b", re.I)),
    ("look", re.compile(r"\b(the|its|same|this|that) look\b|'s look\b|\bstyle\b|\bcolou?rs\b|\bpalette\b|\bmood\b|\bvisual(s|ly)?\b", re.I)),
    ("structure", re.compile(r"\bstructure\b|\bsequence\b|\border of (the )?scenes\b|\bthe parts\b", re.I)),
    # the board's own words; a bare "level" or "blocks" names the request's own level as often as the video's (round 2,
    # case 10: "a narrow centre level" was read as the reference's board)
    ("board", re.compile(r"\b(boards?|map|grid|layout|same level|same blocks|same pieces)\b|"
                         r"\b(this|that|its|the video'?s|the clip'?s) (level|blocks|pieces)\b|"
                         r"\b(level|blocks|pieces) (of|from|in) (this|that|the) (video|clip|ad)\b", re.I)),
    ("screen", re.compile(r"\b(framing|camera|close[- ]?up|zoom\w*|what it shows on screen|on screen|hud|interface|cursor|pointer)\b", re.I)),
    ("board_colours", re.compile(r"\bblock colou?rs\b|\bcolou?rs of the (blocks|pieces)\b|\b(the )?blocks'? colou?rs\b|"
                                 r"\bpiece colou?rs\b|\bcolou?red blocks of (this|the|that) (video|clip)\b", re.I)),
)
SAME_COLOURS = re.compile(r"\b(same|its|their|the video'?s) colou?rs\b|\bcolou?rs\b", re.I)
BOARD_TALK = re.compile(r"\b(board|blocks?|pieces?|level)\b", re.I)
LOOK_NOT_COLOURS = re.compile(r"\b(the|its|same|this|that) look\b|'s look\b|\bstyle\b|\bpalette\b|\bmood\b|\bvisual(s|ly)?\b|"
                              r"\bbackground\b|\bbackdrop\b|\bcaption colou?rs?\b", re.I)


def _request_words(prompt: str) -> str:
    """The request without the game's name ("Color Block Jam" is not talk about colours)."""
    return re.sub(r"\bcolou?r[\s-]*block[\s-]*jam\b", " ", prompt or "", flags=re.I)


def focus_words(prompt: str) -> dict:
    """The word table: {focus, level, found}. `found` is what the request's words name; a request
    with no words about the video is read for the concept, in full. The word "ending" in a request
    that states its own ending ("a near-fail ending with 3 seconds left") is the request's, not a
    question about the reference's (the same detection as videoref.stated: audit.asked)."""
    text = _request_words(prompt)
    found = [f for f, rx in FOCUS_WORDS if rx.search(text)]
    # the blocks' colours are the board's, not the look's (round 2, case 10: "take only the block colours" became the
    # background): colours named with the board or the blocks are board_colours; the look needs its own words
    if "board_colours" not in found and SAME_COLOURS.search(text) and BOARD_TALK.search(text) and \
            not LOOK_NOT_COLOURS.search(text):
        found.append("board_colours")
    if "board_colours" in found and "look" in found and not LOOK_NOT_COLOURS.search(text):
        found.remove("look")
    if "ending" in found:
        from .audit import asked
        if asked(prompt).get("ending"):
            found.remove("ending")
    focus = found or ["concept"]
    return {"focus": focus, "level": "full" if "concept" in focus else "targeted", "found": found}


def covers(focus, what: str) -> bool:
    """Whether a reading's focus covers an aspect. The concept covers everything but the look: a
    "version of this concept" keeps the game's own look, which is taken only when asked for. The board
    (2026-10-17) is covered by the concept and by its own focus "board"."""
    focus = list(focus or [])
    if what == "screen":  # the framing and the HUD are the look's too, not the concept's (round 2, case 09)
        return "screen" in focus or "look" in focus
    if what == "board_colours":  # the blocks' colours: their own focus, or the board's (round 2, case 10)
        return "board_colours" in focus or covers(focus, "board")
    return what in focus or ("concept" in focus and what != "look")


def focus_text(focus) -> str:
    """["hook", "pacing"] -> "the hook and the pacing"."""
    names = [FOCUS_NAMES.get(f, f) for f in focus or []]
    if not names:
        return "nothing"
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _strs(x, n: int = 10) -> list[str]:
    return [str(s).strip().rstrip(".")[:200] for s in (x if isinstance(x, list) else []) if str(s).strip()][:n]


@dataclass
class ReadingPlan:
    """What the multimodal model must look for in a reference video, decided from the request before
    the video is read (2a step 1). `source` is "planner" (the planner's model wrote it) or "words"
    (the word table, the fallback); `checks` says what the word table changed or noticed."""
    focus: list[str]
    level: str
    questions: list[str]
    required_fields: list[str]
    ignore: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    why: str = ""
    source: str = "planner"
    checks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_words(cls, prompt: str, why: str = "") -> "ReadingPlan":
        """The word table's plan: its focus, the questions and fields of that focus, the usual ignores."""
        w = focus_words(prompt)
        return cls(focus=list(w["focus"]), level=w["level"],
                   questions=list(dict.fromkeys(q for f in w["focus"] for q in FOCUS_QUESTIONS[f])),
                   required_fields=list(dict.fromkeys(x for f in w["focus"] for x in FOCUS_FIELDS[f])),
                   ignore=list(DEFAULT_IGNORE), constraints=[],
                   why=why or (f"read from the request's words: {focus_text(w['focus'])}" if w["found"] else
                               "the request says nothing about the video, so it is read for its concept"),
                   source="words")

    @classmethod
    def parse(cls, raw) -> tuple["ReadingPlan | None", str]:
        """A plan from the planner's JSON, checked in code: the focus against the allowed set, the
        level, the questions and the fields. (None, the reason) when it is empty or invalid."""
        if not isinstance(raw, dict):
            return None, "the answer is not a JSON object"
        given = [str(f).strip().lower() for f in raw.get("focus") or [] if isinstance(f, str)]
        focus = list(dict.fromkeys(f for f in given if f in FOCI))
        dropped = [f for f in given if f not in FOCI]
        level = str(raw.get("level") or "").strip().lower()
        questions = list(dict.fromkeys(q.strip()[:300] for q in raw.get("questions") or []
                                       if isinstance(q, str) and q.strip()))[:12]
        common = {"ignore": _strs(raw.get("ignore")), "constraints": _strs(raw.get("constraints")),
                  "why": str(raw.get("why") or "")[:300]}
        if level == "none" and not focus:
            return cls(focus=[], level="none", questions=[], required_fields=[], **common), ""
        if not focus:
            return None, "no focus from the allowed set" + (f" (it said {', '.join(dropped)})" if dropped else "")
        if not questions:
            return None, "no questions for the model"
        checks = [f"focus {', '.join(dropped)}: not an allowed value, dropped"] if dropped else []
        if level not in LEVELS or level == "none":
            new = "full" if "concept" in focus else "targeted"
            checks.append(f"level {level or 'missing'} with a focus: read as {new}")
            level = new
        if "concept" in focus and level != "full":
            checks.append("a concept read is a full read")
            level = "full"
        required = [x for x in dict.fromkeys(str(r) for r in raw.get("required_fields") or []) if x in NOTE_FIELDS]
        if not required:
            required = list(dict.fromkeys(x for f in focus for x in FOCUS_FIELDS[f]))
        return cls(focus=focus, level=level, questions=questions, required_fields=required, checks=checks, **common), ""


PLAN_SYSTEM = (
    "You decide what a multimodal model must look for in this video so that a Color Block Jam ad can be made from the "
    "request. Name the focus, the questions, the fields required, what to ignore and what the request already fixes. "
    "Do not analyse the video; you cannot see it.\n"
    "Color Block Jam is a puzzle game: coloured blocks are dragged out through gates of their colour on a grid board "
    "with a countdown clock.\n"
    "focus: what the request wants from the video, from " + ", ".join(FOCI) + " (concept: the idea as a whole, with its "
    "parts, hook, pacing, captions, ending and board; look: the background, the caption colours and the mood, never the "
    "blocks, only when the request asks for them; board_colours: the blocks' colours only; board: the level's type, "
    "size, block count, pieces and colours; screen: the camera framing, the HUD and what else is on screen, only when "
    "the request asks for them). "
    "level: none (the request asks nothing of the video), targeted (some aspects), full (the concept as a whole). "
    "questions: what the model must answer, one per entry, in your own words. required_fields: the fields of the "
    "reading that must be filled, from " + ", ".join(NOTE_FIELDS) + ". ignore: what the request says not to take, and "
    "what an adaptation must not copy. constraints: values the request fixes itself (a length, an ending, 'no "
    "replay'). why: one line on how you read the request.")
PLAN_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {"focus": {"type": "array", "items": {"type": "string", "enum": list(FOCI)}},
                   "level": {"type": "string", "enum": list(LEVELS)},
                   "questions": {"type": "array", "items": {"type": "string"}},
                   "required_fields": {"type": "array", "items": {"type": "string", "enum": list(NOTE_FIELDS)}},
                   "ignore": {"type": "array", "items": {"type": "string"}},
                   "constraints": {"type": "array", "items": {"type": "string"}},
                   "why": {"type": "string"}},
    "required": ["focus", "level", "questions", "required_fields", "ignore", "constraints", "why"],
}


def format_line(facts: dict) -> str:
    """The file's format facts in one line (nothing about its content)."""
    return (f"{facts.get('file') or 'the video'}, {facts.get('duration_s', 0):g} s, {facts.get('width')}x{facts.get('height')} "
            f"{facts.get('orientation') or ''}, {facts.get('size_mb', '?')} MB").replace(" ,", ",")


def reading_plan(prompt: str, facts: dict, client=None, log=None) -> ReadingPlan:
    """Step 1: understand the request. One call to the planner's text model (the client planner.plan
    uses: the Claude CLI or NVIDIA text, llm.planner_client) with the request's words and the file's
    format facts; an empty or invalid plan falls back to the word table, and the fallback is logged.
    A valid plan wins outright: the word table only logs what it would have read differently, and adds
    nothing (2026-10-16 creative run, case 10: it added "concept" and "ending" to a correct hook-and-pacing
    plan, and the tool took a wrong move, the part lengths and the captions nobody asked for)."""
    say = log or (lambda *_: None)
    if client is None:
        plan = ReadingPlan.from_words(prompt)
        plan.checks.append("no planner model was given, so the word table read the request")
        say(f"reading plan: {plan.checks[-1]}")
        return plan
    user = (f"REQUEST:\n{prompt.strip() or '(no words about the video)'}\n\n"
            f"THE ATTACHED VIDEO (its format only; you cannot see it): {format_line(facts)}")
    try:
        from .planner import _parse
        plan, why_not = ReadingPlan.parse(_parse(client.complete(PLAN_SYSTEM, user, PLAN_SCHEMA)))
    except Exception as e:  # the fallback is the word table, never a guess
        plan, why_not = None, f"the planner's model gave no plan: {str(e)[:120]}"
    if plan is None:
        plan = ReadingPlan.from_words(prompt)
        plan.checks.append(f"the planner's plan was empty or invalid ({why_not}); the word table read the request")
        say(f"reading plan: {plan.checks[-1]}")
        return plan
    for c in plan.checks:
        say(f"reading plan: {c}")
    w = focus_words(prompt)
    if plan.level == "none":
        plan.checks.append(f"the planner reads nothing to take from the video; the word table would read "
                           f"{focus_text(w['focus'])}: the plan wins")
        say(f"reading plan: {plan.checks[-1]}")
    elif set(plan.focus) != set(w["focus"]):
        plan.checks.append(f"the planner reads {focus_text(plan.focus)} where the word table would read "
                           f"{focus_text(w['focus'])}: the plan wins")
        say(f"reading plan: {plan.checks[-1]}")
    return plan


PREAMBLE = ("Color Block Jam is a puzzle game: coloured blocks are dragged out through gates of their colour on a grid "
            "board with a countdown clock. You are reading a reference video so that an ad for this game can ADAPT its "
            "concept. Never describe how to copy frames. Use only the measured timestamps below. Do not invent "
            "mechanics this game does not have. Say what you see apart from what you infer.")


# The one fixed question in every reading (2026-10-16, READING-ACCURACY-v5.md): in three Gemini passes two cliffhangers
# were read right exactly when the planner's own ending question happened to name the cliffhanger.
ENDING_QUESTION = ("How does it end, among these: a win; a near-fail (a win with 5 s or less on the clock); a time-out "
                   "(the out-of-time screen); a cliffhanger (the clip cuts before any result, often with a question "
                   "caption); or it stops mid-level (no result, no question: the game's cliffhanger too)?")


# The ending's second read (2026-10-16): the whole-clip read samples thinly at the end, where the ending is decided, and
# the ending was 9-12 of 12 across four Gemini passes; the last 10 s are read once more on their own, at 8 fps.
ENDING_READ_S = 10.0
ENDING_READ_MIN_S = 12.0  # a shorter clip is read whole anyway
ENDING_READ_FPS = 8
ENDING_NAMES = {"win": "win", "victory": "win", "near-fail": "near_fail", "near_fail": "near_fail", "near fail": "near_fail",
                "time-out": "time_out", "time_out": "time_out", "timeout": "time_out", "fail": "time_out",
                "cliffhanger": "cliffhanger", "stopped": "cliffhanger", "stops mid-level": "cliffhanger",
                "mid-level": "cliffhanger", "stopped mid-level": "cliffhanger"}
ENDING_SPELLING = {"win": "win", "near_fail": "near-fail", "time_out": "time-out", "cliffhanger": "cliffhanger"}


def tail_copy(copy: Path, out: Path, duration_s: float, seconds: float = ENDING_READ_S, fps: int = ENDING_READ_FPS) -> dict:
    """The clip's last `seconds`, cut from the normalised copy at `fps` with the format step's ffmpeg settings, for the
    ending's second read. Returns {from_s, to_s, fps, frames}."""
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise ValueError("ffmpeg is not installed, so the ending cannot be read again")
    start = max(0.0, float(duration_s) - seconds)
    r = subprocess.run([ffmpeg, "-v", "error", "-y", "-ss", f"{start:.2f}", "-i", str(copy), "-an", "-vf", f"fps={fps}",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "32", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                        str(out)], capture_output=True, text=True)
    if r.returncode != 0 or not Path(out).is_file():
        raise ValueError(f"the last {seconds:g} s could not be cut ({r.stderr.strip()[:120]})")
    c = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                        "stream=nb_read_packets", "-of", "json", str(out)], capture_output=True, text=True)
    frames = int(((json.loads(c.stdout or "{}").get("streams") or [{}])[0]).get("nb_read_packets") or 0)
    return {"from_s": round(start, 2), "to_s": round(float(duration_s), 2), "fps": fps, "frames": frames}


def ending_ask(tail: dict, duration_s: float) -> str:
    """The one short question of the ending's second read: the four endings, the last clock reading, the screens."""
    return (f"These are the last {tail['to_s'] - tail['from_s']:g} s ({tail['from_s']:g}-{tail['to_s']:g} s) of a "
            f"{float(duration_s):g} s ad for the puzzle game Color Block Jam: coloured blocks are dragged out through gates "
            f"of their colour on a grid board with a countdown clock. Answer only how it ends. {ENDING_QUESTION}\n"
            'Return ONLY JSON: {"ending": "win|near-fail|time-out|cliffhanger|stopped", "last_clock": "MM:SS, the last clock '
            'reading you see, or null", "win_screen": true or false (a Level Completed or win screen is shown), '
            '"out_of_time_screen": true or false (an out-of-time or fail screen is shown), "question_caption": "the '
            'question caption shown at the end, or empty", "blocks_left": <how many coloured blocks are still on the board '
            'at the last frame of play>, "why": "one line: what you see that decides it"}')


def read_ending(client, copy: Path, facts: dict, log=None) -> dict:
    """The ending read a second time, on the clip's last ENDING_READ_S seconds only, by the same reader: {ending (win,
    near_fail, time_out, cliffhanger), last_clock, win_screen, out_of_time_screen, question_caption, why, from_s, to_s,
    fps, frames, model, reader, seconds}, or {skipped} under ENDING_READ_MIN_S, or {error}. About 4 s of the reader."""
    say = log or (lambda *_: None)
    dur = float(facts.get("duration_s") or 0)
    if dur < ENDING_READ_MIN_S:
        return {"skipped": f"the clip is under {ENDING_READ_MIN_S:g} s, so its ending was read with the whole clip"}
    t0 = time.time()
    rec: dict = {}
    try:
        tail_path = Path(copy).parent / "tail.mp4"
        rec.update(tail_copy(copy, tail_path, dur))
        part = {"type": "video_url", "video_url": {"url": "data:video/mp4;base64," + base64.b64encode(tail_path.read_bytes()).decode()}}
        answer = _ask_json(client, ending_ask(rec, dur), part, None)
        e = ENDING_NAMES.get(str(answer.get("ending") or "").split("(")[0].strip().lower())
        rec.update(ending=e, last_clock=answer.get("last_clock") or None, win_screen=answer.get("win_screen") is True,
                   out_of_time_screen=answer.get("out_of_time_screen") is True,
                   question_caption=str(answer.get("question_caption") or "")[:120], why=str(answer.get("why") or "")[:200],
                   blocks_left=_int_or_none(answer.get("blocks_left")))
        if e is None:
            rec["error"] = f"no ending among the four: {answer.get('ending')!r}"
    except Exception as e:  # the whole-clip ending stands
        rec["error"] = str(e)[:200]
    rec["model"] = getattr(client, "last_model", None)
    rec["reader"] = getattr(client, "reader", None) or reader_of(rec["model"])
    rec["seconds"] = round(time.time() - t0, 1)
    return rec


# The one fixed board question (2026-10-17), asked whenever the focus covers the board: the level's type is taken from it
# when the request says nothing about the level (videoref), so it is asked in the same words every time.
BOARD_QUESTION = ("What is the board at the first frame of play: how many columns and rows of cells, its shape, how many "
                  "blocks (only the coloured blocks that leave through gates; never another game's obstacle), their distinct "
                  "colours (each once, named as seen: colours that look different get different names), "
                  "the pieces' sizes, how many sides have gates, whether the layout is mirror-symmetric (the pieces' "
                  "shapes and places mirror left-right or top-bottom, whatever their colours), how many wall cells are "
                  "inside it, anything inside it that is not a block, and how busy it looks?")


# The board's second read (2026-10-17): the whole clip is read at 360p, where another game's board is a few hundred
# pixels (the owner's test: a 12-block board read as 7 blocks on 5x5, its bubbles missed); one still of the first frame
# of play is read again at the source's resolution (up to 1920 px on the long side), with only the board question and
# the board's box. When the board fills under a quarter of the frame (the owner's trailer: a portrait game window in a
# 1920x1080 frame), the still is cropped to the box with a margin and the board is read once more on the crop, which wins.
BOARD_STILL_PX = 1920  # the still's long side at most (the source's own when smaller)
BOARD_STILL_PX_NVIDIA = 1280  # with NVIDIA build read first (round 3: the 1920 px still made super-vl reason for 16000 tokens)
BOARD_READ_BUDGET_S = 300.0  # the board step's wall clock: past it the optional asks (crop, colour count, sizes) are skipped
BOARD_AT_S = 0.3  # into the first part with the board on screen
PLAY_PURPOSES = ("hook", "gameplay", "mistake", "near_fail")
BOARD_CROP_AREA = 0.25  # a board box under this share of the frame is read again on a crop
BOARD_CROP_MARGIN = 0.10  # of the box's width and height, on each side
BOARD_CROP_MIN_PX = 1024  # a smaller crop is enlarged to this long side before it is read


def board_still(path: Path, out: Path, at_s: float, px: int = BOARD_STILL_PX) -> dict:
    """One frame of the original file at `at_s`, its long side at most `px`, as a JPEG: {at_s, width, height}."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise ValueError("ffmpeg is not installed, so the board cannot be read on a still")
    r = subprocess.run([ffmpeg, "-v", "error", "-y", "-ss", f"{at_s:.2f}", "-i", str(path), "-frames:v", "1", "-vf",
                        f"scale='if(gt(iw,ih),min({px},iw),-2)':'if(gt(iw,ih),-2,min({px},ih))'", "-q:v", "2", str(out)],
                       capture_output=True, text=True)
    if r.returncode != 0 or not Path(out).is_file():
        raise ValueError(f"no frame at {at_s:g} s ({r.stderr.strip()[:120]})")
    from PIL import Image
    with Image.open(out) as im:
        w, h = im.size
    return {"at_s": round(at_s, 2), "width": w, "height": h}


def board_at(notes: dict, duration_s: float) -> float:
    """When the board is first seen in play: just into the first part with play on screen (the hook is shown over the
    board in most ads), else just into the clip."""
    segs = [s for s in notes.get("structure") or [] if isinstance(s, dict)]
    first = next((s for s in segs if s.get("purpose") in PLAY_PURPOSES), None)
    at = (float(first.get("from_s") or 0) if first else 0.0) + BOARD_AT_S
    return max(0.0, min(at, float(duration_s or 0) - 0.1)) if duration_s else at


BOX_FIELD = ('"box": {"x": <the board\'s left edge, 0-1 of the frame\'s width>, "y": <its top edge, 0-1 of the height>, '
             '"w": <its width, 0-1>, "h": <its height, 0-1>} (the game board with its gates, normalised to the frame), '
             '"extras_seen": ["anything else on screen Color Block Jam does not have, named one by one: booster buttons '
             '(freeze, hammer, vacuum...), power-ups, characters, other menus; [] when none"]')


def board_ask(crop: bool = False) -> str:
    where = ("This is a crop, around the game board, of one frame at the first frame of play" if crop else
             "This is one frame, at the first frame of play,")
    return (f"{where} of an ad for a puzzle game. The game it is adapted for, Color Block Jam, drags coloured blocks out "
            "through gates of their colour on a grid board. Read only the board. "
            f"{BOARD_QUESTION}\nReturn ONLY JSON: {{\"board\": {NOTE_FIELDS['board']}"
            + ("" if crop else f", {BOX_FIELD}") + "}")


def board_box(x, width: int | None = None, height: int | None = None) -> dict | None:
    """The board's box from an answer, normalised to the frame: {x, y, w, h} in 0-1, or None. Pixels (any value over 1)
    are divided by the frame's size; a list [x, y, w, h] is read in that order."""
    if isinstance(x, (list, tuple)) and len(x) == 4:
        x = dict(zip("xywh", x))
    if not isinstance(x, dict):
        return None
    try:
        v = {k: float(x.get(k)) for k in "xywh"}
    except (TypeError, ValueError):
        return None
    if any(n > 1.0 for n in v.values()) and width and height:
        v = {"x": v["x"] / width, "y": v["y"] / height, "w": v["w"] / width, "h": v["h"] / height}
    if not (0 < v["w"] <= 1 and 0 < v["h"] <= 1 and 0 <= v["x"] < 1 and 0 <= v["y"] < 1):
        return None
    v["w"], v["h"] = min(v["w"], 1 - v["x"]), min(v["h"], 1 - v["y"])
    return {k: round(n, 4) for k, n in v.items()}


def crop_to_box(still: Path, out: Path, box: dict) -> dict:
    """The still cropped to the board's box with BOARD_CROP_MARGIN on each side, enlarged to BOARD_CROP_MIN_PX on its
    long side when smaller: {x0, y0, x1, y1 (pixels of the still), width, height (of the crop as read)}."""
    from PIL import Image
    with Image.open(still) as im:
        W, H = im.size
        mx, my = box["w"] * BOARD_CROP_MARGIN, box["h"] * BOARD_CROP_MARGIN
        x0, y0 = max(0, int((box["x"] - mx) * W)), max(0, int((box["y"] - my) * H))
        x1, y1 = min(W, int(round((box["x"] + box["w"] + mx) * W))), min(H, int(round((box["y"] + box["h"] + my) * H)))
        c = im.convert("RGB").crop((x0, y0, x1, y1))
        if max(c.size) < BOARD_CROP_MIN_PX:
            k = BOARD_CROP_MIN_PX / max(c.size)
            c = c.resize((max(1, round(c.size[0] * k)), max(1, round(c.size[1] * k))), Image.LANCZOS)
        c.save(out, quality=92)
        return {"x0": x0, "y0": y0, "x1": x1, "y1": y1, "width": c.size[0], "height": c.size[1]}


def _board_in(answer) -> dict | None:
    if not isinstance(answer, dict):
        return None
    board = answer.get("board") if isinstance(answer.get("board"), dict) else answer if "columns" in answer else None
    return board if isinstance(board, dict) and any(board.get(k) for k in ("columns", "rows", "blocks", "colours")) else None


def _image_part(path: Path) -> dict:
    return {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(Path(path).read_bytes()).decode()}}


# Short asks on the board's crop (2026-10-17, round 1): the symmetry read the same trailer both ways on two passes, so it
# is asked three times and the majority taken; the reader named eight colours for LolTap's six, so it is asked how many
# distinct block colours there are, and that many names are kept (videoref.board_colours merges the closest).
SIZE_READS = 3  # the size, asked three more times on the crop: the median per side
SIZE_ASK = ('Count the cells of this game board: how many columns and how many rows of cells does its grid have (the '
            'playing cells under and between the blocks, not the rim, not the gates)? Return ONLY JSON: {"columns": <n>, '
            '"rows": <n>}')
COLOUR_COUNT_ASK = ('Look only at the coloured blocks on this game board (not the gates on its rim, not the walls). How many '
                    'distinct block colours are there? Count two colours as one when they look the same. Return ONLY JSON: '
                    '{"colour_count": <n>, "colours": ["each distinct colour once, named as seen"]}')


def _int_or_none(x) -> int | None:
    try:
        return int(round(float(x)))
    except (TypeError, ValueError):
        return None


def median_size(first, others: list) -> list[int] | None:
    """The board's size as the median per side of the board read's own size and the three short asks (of four reads,
    the lower middle one)."""
    reads = [s for s in [first] + list(others) if s and all(isinstance(x, (int, float)) and x for x in s)]
    if not reads:
        return None
    cols, rows = sorted(int(s[0]) for s in reads), sorted(int(s[1]) for s in reads)
    return [cols[(len(cols) - 1) // 2], rows[(len(rows) - 1) // 2]]


def count_majority(counts: list) -> int | None:
    """The reader's colour count over its asks: the most frequent; when all differ, the middle one."""
    ns = sorted(n for n in counts if n is not None)
    if not ns:
        return None
    best = max(set(ns), key=lambda n: (ns.count(n), n))
    return best if ns.count(best) > 1 else ns[len(ns) // 2]


def confirmed_names(clusters: list[dict], names: list[str]) -> list[str]:
    """The colour names a measured cluster stands for, one cluster each, by the assignment of names to clusters that
    confirms the most names (a pair within videoref.COUNT_MERGE_MAX) at the least total distance (so purple and
    magenta each find their own cluster, not the nearer one twice): the names the code confirms. A cluster no name
    stands for confirms nothing."""
    import itertools
    from .videoref import COUNT_MERGE_MAX, _distance, colour_name, colour_rgb
    plain = list(dict.fromkeys(colour_name(n) for n in names if colour_rgb(n)))[:7]
    cl = sorted(clusters, key=lambda c: -c.get("cells", 0))[:8]
    if not plain or not cl:
        return []
    d = {(n, i): _distance(colour_rgb(n), cl[i]["rgb"]) for n in plain for i in range(len(cl))}
    best = None
    if len(plain) <= len(cl):
        options = ((tuple(plain), perm) for perm in itertools.permutations(range(len(cl)), len(plain)))
    else:
        options = ((perm, tuple(range(len(cl)))) for perm in itertools.permutations(plain, len(cl)))
    for ns, cs in options:
        ok = [(n, i) for n, i in zip(ns, cs) if d[n, i] <= COUNT_MERGE_MAX]
        key = (-len(ok), sum(d[p] for p in ok))
        if best is None or key < best[0]:
            best = (key, [n for n, _ in ok])
    return best[1]


def majority(votes: list) -> bool | None:
    """The majority of the true/false votes (None ones left out); None on a tie or no votes."""
    yes, no = sum(v is True for v in votes), sum(v is False for v in votes)
    return True if yes > no else False if no > yes else None


# The board measured in code on its crop (2026-10-17, round 1): the reader could not see trailer 3's symmetry or trailer
# 2's fourth colour. The crop is divided into the columns x rows read; each cell is a block (saturated) or floor; the
# occupancy is compared with its mirrors (colours ignored, as the truth judges the pieces' shapes and places), and the
# block cells' colours are clustered by hue and lightness (so dark green and green, purple and magenta, blue and light
# blue stay apart).
SYMMETRY_MATCH = 0.85  # this share of cells equal to the mirror's, left-right or top-bottom: symmetric
REGION_MIN = 0.3  # a row (or column) of the grid is at least this much block or floor (the hand and the light near rows dip)
# The symmetry is the block mask against its mirror, not the cell grid: the grid depends on the size read (trailer 3 was
# 0.95 on a 6x7 grid and 0.69 on 8x8). The mask, scaled to MIRROR_N square, is compared with its mirror about the best
# axis near the middle (shifts up to MIRROR_SHIFT of MIRROR_N); intersection over union of MIRROR_IOU or more, left-right
# or top-bottom, is symmetric (trailer 3: 0.85-0.88 in every pass; the other two 0.48-0.59; a synthetic asymmetric
# layout 0.75 top-bottom under the axis search).
MIRROR_N, MIRROR_SHIFT, MIRROR_IOU = 64, 6, 0.8
# a cluster's colours lie within this hue (degrees) and HLS lightness of each other: 24 never over-counted on the owner's
# three boards at any grid read (20 counted LolTap's orange-yellow run as two at 7x7); purple and magenta are 27-29 apart
HUE_UNIT, LIGHT_UNIT = 24.0, 0.3
CLUSTER_MIN_CELLS = 3  # a colour in fewer cells is a side face in shadow, a cursor or a seam (two-cell clusters were
# all such on the owner's three boards), not counted; a real two-cell colour is left to the reader's own count


def _block_mask(rgb):
    """Block pixels: saturated, or a bright pastel (LolTap's pink); never the grey-blue floor, the dark rim, a light
    background or a brown wooden floor (HSV saturation 0.55 at value 0.38)."""
    import numpy as np
    mx, mn = rgb.max(2), rgb.min(2)
    s = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    return ((s >= 0.6) | ((s >= 0.4) & (mx >= 0.6))) & (mx >= 0.25), s, mx


def _grid_region(rgb, block):
    """The grid's area in the crop: the rows and columns mostly block or floor (the grey-blue playing cells), so the
    board's rim and the background fall outside; the whole crop when that leaves too little."""
    import numpy as np
    _, s, v = _block_mask(rgb)
    # the grey-blue cells (saturation up to about 0.37 on the trailers), lighter towards the camera; not the background
    floor = ~block & (s < 0.45) & (v >= 0.35) & (v <= 0.88)
    content = block | floor
    H, W = block.shape

    def span(profile, frac):
        """The longest run of rows (or columns) at `frac` or more, small gaps bridged: the board, not the buttons under it."""
        on = profile >= frac
        gap = max(3, int(len(on) * 0.04))
        runs, start, last = [], None, None
        for i, x in enumerate(on):
            if x:
                if start is None:
                    start = i
                elif i - last > gap:
                    runs.append((start, last + 1))
                    start = i
                last = i
        if start is not None:
            runs.append((start, last + 1))
        return max(runs, key=lambda r: r[1] - r[0]) if runs else None
    # the columns first (relative to the fullest one: the crop's margin can hold a background, a rim and buttons), then
    # the rows inside those columns, then the columns again inside those rows
    xs = span(content.mean(0), 0.5 * content.mean(0).max())
    if xs is None:
        return 0, 0, W, H
    # a row of the board has floor between its blocks, or is nearly all blocks; a row of buttons under the board is
    # neither (round 1, third run: trailer 2's booster buttons became a fifth colour)
    sub_b, sub_f = block[:, xs[0]:xs[1]].mean(1), floor[:, xs[0]:xs[1]].mean(1)
    row_ok = (sub_f >= 0.05) | (sub_b >= 0.6)
    ys = span(np.where(row_ok, content[:, xs[0]:xs[1]].mean(1), 0.0), REGION_MIN)
    if ys is None:
        return 0, 0, W, H
    xs = span(content[ys[0]:ys[1], :].mean(0), REGION_MIN) or xs
    if xs[1] - xs[0] < W * 0.3 or ys[1] - ys[0] < H * 0.3:
        return 0, 0, W, H
    return xs[0], ys[0], xs[1], ys[1]


def _hue_diff(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)


def cluster_colours(cells: list[tuple]) -> list[dict]:
    """Complete-linkage clusters of cell colours [(r, g, b) in 0-1]: two cells join when every pair in the cluster is
    within HUE_UNIT degrees and LIGHT_UNIT of HLS lightness. Clusters of CLUSTER_MIN_CELLS or more: [{rgb (0-255),
    hue, lightness, cells}], the biggest first."""
    import colorsys
    pts = [(colorsys.rgb_to_hls(*c), c) for c in cells]
    near = lambda a, b: _hue_diff(a[0][0] * 360, b[0][0] * 360) <= HUE_UNIT and abs(a[0][1] - b[0][1]) <= LIGHT_UNIT  # noqa: E731
    clusters = [[p] for p in pts]
    while True:
        best = None
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                if all(near(a, b) for a in clusters[i] for b in clusters[j]):
                    d = sum(_hue_diff(a[0][0] * 360, b[0][0] * 360) for a in clusters[i] for b in clusters[j]) / (len(clusters[i]) * len(clusters[j]))
                    if best is None or d < best[0]:
                        best = (d, i, j)
        if best is None:
            break
        _, i, j = best
        clusters[i] += clusters.pop(j)
    out = []
    for c in clusters:
        if len(c) < CLUSTER_MIN_CELLS:
            continue
        r, g, b = (sum(p[1][k] for p in c) / len(c) for k in range(3))
        h, l, _ = colorsys.rgb_to_hls(r, g, b)
        out.append({"rgb": [round(r * 255), round(g * 255), round(b * 255)], "hue": round(h * 360), "lightness": round(l, 2),
                    "cells": len(c)})
    return sorted(out, key=lambda x: -x["cells"])


def measure_board(image: Path, columns: int, rows: int) -> dict:
    """The board measured on its crop: {grid (rows of 1 = block, 0 = floor), left_right, top_bottom (the share of cells
    equal to the mirror's, info), mirror_lr, mirror_tb (the block mask against its mirrors, mirror_iou), symmetric
    (either mirror at MIRROR_IOU or more), clusters, colour_count, region}. A cell is a
    block when half or more of its middle (the middle 40% each way, clear of the seams) is block pixels; its colour is
    the median of those pixels."""
    import numpy as np
    from PIL import Image
    with Image.open(image) as im:
        rgb = np.asarray(im.convert("RGB")).astype(float) / 255
    block, _, _ = _block_mask(rgb)
    x0, y0, x1, y1 = _grid_region(rgb, block)
    cw, ch = (x1 - x0) / columns, (y1 - y0) / rows
    grid, cells = [], []
    for r in range(rows):
        row = []
        for c in range(columns):
            a0, a1 = int(x0 + (c + 0.3) * cw), max(int(x0 + (c + 0.7) * cw), int(x0 + (c + 0.3) * cw) + 1)
            b0, b1 = int(y0 + (r + 0.3) * ch), max(int(y0 + (r + 0.7) * ch), int(y0 + (r + 0.3) * ch) + 1)
            sub = block[b0:b1, a0:a1]
            on = bool(sub.size and sub.mean() >= 0.5)
            row.append(1 if on else 0)
            if on:
                cells.append(tuple(float(x) for x in np.median(rgb[b0:b1, a0:a1][sub], 0)))
        grid.append(row)
    g = np.array(grid)
    lr, tb = float((g == g[:, ::-1]).mean()), float((g == g[::-1, :]).mean())
    clusters = cluster_colours(cells)
    m_lr, m_tb = mirror_iou(block[y0:y1, x0:x1])
    return {"grid": grid, "left_right": round(lr, 2), "top_bottom": round(tb, 2), "mirror_lr": m_lr, "mirror_tb": m_tb,
            "symmetric": max(m_lr, m_tb) >= MIRROR_IOU, "clusters": clusters, "colour_count": len(clusters),
            "region": [x0, y0, x1, y1], "block_cells": len(cells)}


def mirror_iou(mask) -> tuple[float, float]:
    """The block mask against its left-right and top-bottom mirrors: the best intersection over union over axes near
    the middle (the region may hold a rim or a gate on one side). Colours are ignored."""
    import numpy as np
    from PIL import Image
    if not mask.size:
        return 0.0, 0.0
    m = np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).resize((MIRROR_N, MIRROR_N), Image.BILINEAR)) / 255 >= 0.5

    def best(mm):
        out = 0.0
        for s in range(-MIRROR_SHIFT, MIRROR_SHIFT + 1):
            a = np.roll(mm, s, axis=1)
            a = a[:, abs(s):MIRROR_N - abs(s)]
            union = (a | a[:, ::-1]).sum()
            out = max(out, float((a & a[:, ::-1]).sum() / union) if union else 0.0)
        return round(out, 2)
    return best(m), best(m.T)


BOX_ASPECT_OFF = 0.4  # a box whose width:height is this far from the board's columns:rows is not the board's box
CROP_SIZE_CELLS, CROP_BLOCKS_SHARE = 2, 0.4  # the crop agrees: size within 2 cells a side, blocks within 40%, half the colours


def box_disagrees(box: dict, board: dict, width: int, height: int) -> str | None:
    """Why a box cannot be the board's: its width:height is more than BOX_ASPECT_OFF off the board's columns:rows."""
    cols, rows = _int_or_none(board.get("columns")), _int_or_none(board.get("rows"))
    if not cols or not rows or not box.get("w") or not box.get("h"):
        return None
    aspect = (box["w"] * width) / (box["h"] * height)
    off = abs(aspect / (cols / rows) - 1)
    return f"the box is {aspect:.2f} wide for its height, the board {cols}x{rows} is {cols / rows:.2f}" if off > BOX_ASPECT_OFF else None


def crop_disagrees(crop: dict, frame: dict | None) -> str | None:
    """Why the crop's board does not agree with the full frame's (None when it agrees, or there is nothing to compare):
    the size off by more than CROP_SIZE_CELLS a side, the blocks by more than CROP_BLOCKS_SHARE, or fewer than half of
    the frame's colours (as game colours) in the crop's."""
    if not frame:
        return None
    from .videoref import board_colour
    why = []
    for k in ("columns", "rows"):
        a, b = _int_or_none(crop.get(k)), _int_or_none(frame.get(k))
        if a and b and abs(a - b) > CROP_SIZE_CELLS:
            why.append(f"{k} {a} against {b}")
    a, b = _int_or_none(crop.get("blocks")), _int_or_none(frame.get("blocks"))
    if a is not None and b and abs(a - b) > CROP_BLOCKS_SHARE * b:
        why.append(f"{a} blocks against {b}")
    fc = {board_colour(c) for c in frame.get("colours") or []} - {None}
    cc = {board_colour(c) for c in crop.get("colours") or []} - {None}
    if fc and cc and 2 * len(fc & cc) < len(fc):
        why.append(f"{len(fc & cc)} of the frame's {len(fc)} colours")
    return "; ".join(why) or None


def read_board(client, path: Path, notes: dict, facts: dict, log=None, budget_s: float = BOARD_READ_BUDGET_S) -> dict:
    """The board read a second time, on one still of the first frame of play at the source's resolution, by the same
    reader, with the board's box (rejected when its shape is not the board's, box_disagrees); when the box is under
    BOARD_CROP_AREA of the frame, once more on the still cropped to the box, and the crop's board wins when it agrees
    with the frame's (crop_disagrees; else "the crop disagreed: kept the full frame's reading"). Then on the crop: the
    size asked three more times (the median per side), the number of distinct block colours asked once, and the board
    measured in code (measure_board: the block mask against its mirrors decides the symmetry; the colour clusters
    confirm the board's colour names). The colour count is the larger of the confirmed names and the reader's count, at
    most 7, so a confirmed colour is kept; a colour no reader named is never added (round 1, third run). {board, at_s,
    width, height, box, box_rejected, board_frame, crop, size_reads, colour_counts, measured, colour_count,
    colour_count_model, colour_count_code, colour_clusters_measured, colours_counted, still_px, skipped, model, reader,
    seconds}, or {error} (the whole clip's board stands).
    Every ask here is a still's short ask (describe_still: its own budget, one try a model). The frame's ask always runs;
    the crop's ask, the colour count and the size re-asks run only while `budget_s` of wall clock remains, and are
    otherwise skipped ("<ask>: skipped: budget" in rec["skipped"]); the code's measure on the crop needs no model and
    always runs. With NVIDIA build read first the still is at most BOARD_STILL_PX_NVIDIA on its long side."""
    t0, start = time.time(), time.monotonic()
    rec: dict = {}
    asker = _Still(client)
    skipped: list[str] = []

    def room(what: str) -> bool:  # an optional ask runs only while the board step's budget remains
        if time.monotonic() - start < budget_s:
            return True
        skipped.append(f"{what}: skipped: budget")
        return False
    try:
        with tempfile.TemporaryDirectory() as tmp:
            still = Path(tmp) / "board.jpg"
            px = BOARD_STILL_PX_NVIDIA if first_reader(client) == "nvidia" else BOARD_STILL_PX
            rec.update(board_still(path, still, board_at(notes, facts.get("duration_s") or 0), px=px))
            rec["still_px"] = px
            answer = _ask_json(asker, board_ask(), _image_part(still), None)
            board = _board_in(answer)
            box = board_box(answer.get("box") if isinstance(answer, dict) else None, rec["width"], rec["height"])
            if box and board is not None and box_disagrees(box, board, rec["width"], rec["height"]):
                # a box whose shape is not the board's (round 1: LolTap's 6x6 board boxed as a tall strip): no crop
                rec["box_rejected"] = {"box": box, "why": box_disagrees(box, board, rec["width"], rec["height"])}
                box = None
            if box:
                rec["box"] = box
            extras = answer.get("extras_seen") if isinstance(answer, dict) else None
            if isinstance(extras, list):  # the full frame shows what the 360p copy misses (the trailer's booster buttons)
                rec["extras_seen"] = [str(x).strip()[:80] for x in extras if str(x).strip()][:12]
            if box and box["w"] * box["h"] < BOARD_CROP_AREA:
                crop = Path(tmp) / "board_crop.jpg"
                try:
                    rec["crop"] = crop_to_box(still, crop, box)
                    if not room("the crop's ask"):
                        raise _Skipped()
                    cropped = _board_in(_ask_json(asker, board_ask(crop=True), _image_part(crop), None))
                    disagree = crop_disagrees(cropped, board) if cropped else None
                    if cropped and not disagree:
                        rec["board_frame"], board = board, cropped
                        rec["crop"]["read"] = True
                    elif cropped:
                        # the crop's answer wins only when it agrees with the full frame's (round 1: LolTap's crop of part
                        # of the board read 6x10 with 4 blocks for the frame's 6x6 with 13)
                        rec["crop"].update(disagreed=disagree, board_crop=cropped)
                        crop.unlink(missing_ok=True)  # neither the short asks nor the code measure use a crop that is wrong
                        if log:
                            log(f"board: the crop disagreed ({disagree}): kept the full frame's reading")
                    else:
                        rec["crop"]["error"] = "no board in the crop's answer"
                except _Skipped:  # the crop stays for the code's measure; the frame's board stands
                    rec["crop"]["skipped"] = "budget"
                except Exception as e:  # the frame's board stands
                    rec.setdefault("crop", {})["error"] = str(e)[:200]
            if board is not None:
                # the short asks, on the board's crop (made now when the board was large enough not to need one)
                focus = Path(tmp) / "board_crop.jpg"
                trusted = not (rec.get("crop") or {}).get("disagreed")
                if not focus.is_file() and trusted:
                    try:
                        if box:
                            crop_to_box(still, focus, box)
                    except Exception:  # the whole still, then
                        pass
                part = _image_part(focus if focus.is_file() else still)
                # the reader's colour count, asked once (the code's own count covers what it misses); the symmetry is the
                # code's mirror measure alone (2026-10-17: the reader's votes said "not symmetric" every time, and the
                # free daily quota counts every call)
                counts, named = [], []
                try:
                    if not room("the colour count"):
                        raise _Skipped()
                    cc = _ask_json(asker, COLOUR_COUNT_ASK, part, None)
                    n = cc.get("colour_count")
                    counts.append(int(n) if isinstance(n, (int, float)) and 1 <= int(n) <= 12 else None)
                    named.append([str(c) for c in cc.get("colours") or []][:12])
                except Exception:  # a failed or skipped ask is no count
                    counts.append(None)
                    named.append([])
                rec["colour_counts"] = counts
                model_n = count_majority(counts)
                sizes = []  # the size read three times more on the crop: the median per side (round 1: trailer 3 read 10x10)
                for i in range(SIZE_READS):
                    if not room(f"size read {i + 1}"):
                        continue
                    try:
                        sz = _ask_json(asker, SIZE_ASK, part, None)
                        c_, r_ = _int_or_none(sz.get("columns")), _int_or_none(sz.get("rows"))
                        sizes.append([c_, r_] if c_ and r_ and 2 <= c_ <= 16 and 2 <= r_ <= 16 else None)
                    except Exception:
                        sizes.append(None)
                rec["size_reads"] = sizes
                med = median_size([board.get("columns"), board.get("rows")], sizes)
                if med:
                    board = {**board, "columns": med[0], "rows": med[1], "size_first": [board.get("columns"), board.get("rows")]}
                measured = None
                cols, rows_ = _int_or_none(board.get("columns")), _int_or_none(board.get("rows"))
                if cols and rows_ and 2 <= cols <= 16 and 2 <= rows_ <= 16 and focus.is_file():  # only on a trusted crop
                    try:  # the code's measure on the crop decides the symmetry, and may raise the colour count
                        measured = measure_board(focus if focus.is_file() else still, cols, rows_)
                        rec["measured"] = measured
                    except Exception as e:
                        rec["measure_error"] = str(e)[:120]
                if measured and measured.get("grid"):
                    g = [x for row in measured["grid"] for x in row]
                    board = {**board, "occupancy": round(sum(g) / len(g), 2)}  # the share of cells under blocks
                if measured:
                    board = {**board, "symmetric": measured["symmetric"], "symmetric_first": board.get("symmetric"),
                             "symmetric_source": "measured"}
                counted = next((nm for n_, nm in zip(counts, named) if n_ == model_n and nm), [])
                read_names = [str(c) for c in board.get("colours") or []]
                # the code's count is the board's own colour names its clusters confirm, one cluster each: the count is
                # raised only to keep a colour the code measured and a reader named, never to add one (round 1, third
                # run: a cluster from the booster buttons under a cut board was added as a fifth colour, "blue")
                code_n = len(confirmed_names(measured["clusters"], read_names)) if measured else None
                final = min(7, max(x for x in (code_n, model_n) if x is not None)) if (code_n or model_n) else None
                if final:
                    rec.update(colour_count=final, colour_count_model=model_n, colour_count_code=code_n, colours_counted=counted,
                               colour_clusters_measured=measured["colour_count"] if measured else None)
                    added = []
                    board = {**board, "colour_count": final, "colours_counted": counted}
        if board is None:
            rec["error"] = "no board in the answer"
        else:
            rec["board"] = board
    except Exception as e:  # the whole clip's board stands
        rec["error"] = str(e)[:200]
    if skipped:
        rec["skipped"] = skipped
    rec["model"] = getattr(client, "last_model", None)
    rec["reader"] = getattr(client, "reader", None) or reader_of(rec["model"])
    rec["seconds"] = round(time.time() - t0, 1)
    return rec


class _Skipped(Exception):
    """An optional ask of the board step skipped for its budget (read_board)."""


def schema_text() -> str:
    return "{\n" + ",\n".join(f'  "{k}": {v}' for k, v in NOTE_FIELDS.items()) + "\n}"


# The general reading, asked of every reference video whatever the request (2026-10-17, the owner: "the video model always
# analyses the general concept of the reference; when the user says specific things, the model focuses on them as
# well"). The plan's focus decides what is APPLIED to the brief (covers()), never what is read.
GENERAL_QUESTIONS = (
    "What does the video show, and what happens, in order, with the seconds?",
    "Which game is it: Color Block Jam itself (toy-brick blocks with studs, coloured gates on the board's rim, a LEVEL and "
    "TIME HUD) or another game (name it)?",
    "What is the idea of the ad in one line?",
    BOARD_QUESTION,
    ENDING_QUESTION,
    "What is the hook: the first thing shown or said, and what does it do (a question, a challenge, a dare, or simply play)?",
    "Which captions does the ad overlay, word for word, in order (none when there are none)?",
    "What does the HUD show at the first frame of play: the level number and the clock?",
    "How is the game framed: how much of the frame's width does the board take, and is a hand cursor or anything else "
    "on screen besides the board and the HUD?",
    "Which mechanics are shown, and what is on screen that Color Block Jam does not have (booster buttons, power-ups, other menus)?",
)
GENERAL_FIELDS = ("what_it_shows", "game_or_product", "concept_in_one_line", "structure", "hook", "ending", "captions_seen",
                  "screen_text", "hud", "framing", "board", "mechanics_seen", "extras_seen")


def video_ask(plan: ReadingPlan, facts: dict, prompt: str) -> str:
    """Step 2: the prompt the multimodal model sees, in this order: the preamble; the request, quoted; the general
    reading (GENERAL_QUESTIONS, always); the plan's questions on top, as the user's priorities; the ignore list; the
    time reference (the clip's length only: no cuts, no motion, no parts: the understanding comes first); the schema
    with the general fields and the plan's required fields marked REQUIRED and the rest OPTIONAL."""
    request = (prompt or "").strip().replace('"', "'") or "(no words about the video: read it for its concept)"
    lines = [PREAMBLE, "", f'THE REQUEST this reading serves: "{request}"', "",
             "WHAT TO LOOK FOR (always, the whole reading):"]
    lines += [f"- {q}" for q in GENERAL_QUESTIONS]
    own = [q for q in plan.questions if q not in GENERAL_QUESTIONS]
    lines.append("THE USER ASKS IN PARTICULAR (look for these first, as priorities):" if own else
                 "THE USER ASKS IN PARTICULAR: nothing beyond the reading above.")
    lines += [f"- {q}" for q in own]
    lines.append("IGNORE: " + ("; ".join(plan.ignore) if plan.ignore else "nothing is named") + ".")
    lines += ["", f"TIME REFERENCE: the clip is {float(facts.get('duration_s') or 0):.1f} s long; give every second on that clock.", ""]
    required = list(GENERAL_FIELDS) + [f for f in plan.required_fields if f in NOTE_FIELDS and f not in GENERAL_FIELDS]
    for aspect, fld in (("pacing", "moves_by_third"), ("ending", "mistakes"), ("ending", "mistakes_shown")):
        if covers(plan.focus, aspect) and fld not in required:
            required.append(fld)  # the code computes from these (pacing, mistakes)
    lines.append(f"Return ONLY JSON with these fields (REQUIRED: {', '.join(required)}; OPTIONAL: the rest, null when you "
                 f"did not look for it): {schema_text()}")
    lines.append(f'Set "roles" to {json.dumps(plan.focus)}.')
    return "\n".join(lines)


def _label(x) -> str:
    return str(x or "").strip().lower().replace("-", "_").replace(" ", "_")


def validate_notes(notes, facts: dict, focus=(), general: bool = False) -> list[str]:
    """The checks in code on the model's answer (2e), before anything is taken from it. Only the time
    can reject a reading (asked again once, then dropped): a part outside [0, the clip's length]
    (EDGE_S of rounding allowed at the end), a part that ends before it starts, parts out of order, or
    no usable parts on a concept or structure read. A part's label never rejects it (purpose_of reads
    every label, an unknown one as "other"), nor does a confidence outside 0-1 (clamped by structure);
    a part with no seconds is left out. Returns the problems in words ([] = valid). (2026-10-16 live
    run: two confident readings were thrown away over labels such as "identity" and "tension".)"""
    if not isinstance(notes, dict):
        return ["the answer is not a JSON object"]
    problems = []
    dur = float(facts.get("duration_s") or 0) or None
    segs = notes.get("structure")
    segs = segs if isinstance(segs, list) else []
    prev, usable = None, 0
    for i, s in enumerate(segs, 1):
        if not isinstance(s, dict):
            continue
        f, t = _unit(s.get("from_s")), _unit(s.get("to_s"))
        if f is None or t is None:
            continue
        usable += 1
        if f < 0 or t < 0 or (dur and (f > dur or t > dur + EDGE_S)):
            problems.append(f"part {i} ({f:g}-{t:g} s) is outside the clip (0-{dur or 0:g} s)")
        if t <= f:
            problems.append(f"part {i} ends at {t:g} s, not after it starts ({f:g} s)")
        if prev is not None and (f < prev[0] or f < prev[1] - EDGE_S):
            problems.append(f"part {i} ({f:g} s) is not after part {i - 1} ({prev[0]:g}-{prev[1]:g} s): the parts are not in order")
        prev = (f, t)
    if not usable and general:
        problems.append("the structure is empty: every reading gives the parts, in order, with their seconds")
    elif not usable and {"concept", "structure"} & set(focus or ()):
        problems.append(f"the structure is empty, but this reading is for {focus_text([x for x in focus if x in ('concept', 'structure')])}")
    if usable and dur and dur >= PLAUSIBLE_MIN_S:
        problems += _clock_problems([s for s in segs if isinstance(s, dict) and _unit(s.get("from_s")) is not None
                                     and _unit(s.get("to_s")) is not None], dur)
    return problems


PLAUSIBLE_MIN_S = 8.0  # the clock check below is off for shorter clips
END_SHARE_MAX = 0.6  # the end card (or the last part) may be at most this share of the clip
BEFORE_SHARE_MIN = 0.3  # the parts before it must cover at least this share
WRONG_UNIT_LAST = ("end_card", "victory", "fail", "other")  # a long last part of these, with little before it: wrong unit


def _clock_problems(segs: list[dict], dur: float) -> list[str]:
    """Whether the model's seconds are on the clip's clock (2026-10-16 creative run, case 10: on a 45 s clip it answered
    hook 0-0.2 s, gameplay 0.3-0.8 s ... payoff 4.1-4.4 s, end card 4.5-45 s, each part inside the clip and in order). The
    end card, or the last part when there is none, may be at most END_SHARE_MAX of the clip, and the parts before it
    must cover at least BEFORE_SHARE_MIN, when that last part is an end card, a result or "other"; otherwise the parts
    are asked again with the numbers quoted."""
    segs = sorted(segs, key=lambda s: _unit(s.get("from_s")))
    k = len(segs)
    while k > 0 and purpose_of(segs[k - 1].get("purpose")) == "end_card":  # the closing run of end-card parts
        k -= 1
    ends = segs[k:]
    last = ends[0] if ends else segs[-1]
    start = _unit(last.get("from_s"))
    last_len = max(0.0, _unit(last.get("to_s")) - start)
    last_len = max(0.0, max(_unit(s.get("to_s")) for s in (ends or [last])) - start)
    before = sum(max(0.0, min(_unit(s.get("to_s")), start) - _unit(s.get("from_s"))) for s in segs
                 if s is not last and _unit(s.get("from_s")) < start)
    name = "the end card" if ends else "the last part"
    # only the wrong-unit signature (2026-10-17, the owner's trailer: one true gameplay part 0-28.86 s was rejected twice
    # and the whole reading lost): the long last part is an end card, a result or "other", AND the parts before it
    # cover under BEFORE_SHARE_MIN. A single gameplay part over the whole clip, or a long last gameplay part, is valid.
    if purpose_of(last.get("purpose")) in WRONG_UNIT_LAST and last_len > END_SHARE_MAX * dur and before < BEFORE_SHARE_MIN * dur:
        return [f"the seconds are not on the clip's clock: the parts before {name} cover {before:g} s of {dur:g} s, and "
                f"{name} runs {last_len:g} s (give every part's seconds on the clip's own clock, 0-{dur:g} s)"]
    return []


def _pace_words(x) -> str | None:
    s = str(x or "").strip().lower().replace("_", " ")
    return {"speeds up": "speeds up", "speed up": "speeds up", "slows down": "slows down", "slow down": "slows down",
            "even": "even", "steady": "even", "constant": "even"}.get(s)


def asks_pacing(plan: ReadingPlan) -> bool:
    """Whether a plan asks about the pacing (a question about it, or the counts or the pace change required)."""
    return bool({"pace_change", "moves_by_third"} & set(plan.required_fields)) or any(
        re.search(r"\bpac(e|ing)\b|\btempo\b|\bspeeds?\b|\bslows?\b|\bthirds?\b", q, re.I) for q in plan.questions)


def needs_parts(plan: ReadingPlan, notes: dict) -> tuple[bool, str]:
    """Whether the parts are measured after the reading (2g): for a structure, pacing or hook read, or a
    concept read that asks about the pacing; a concept read with no pacing question keeps the model's
    parts as they are. The model's confidence decides nothing (2026-10-16: it was 0.9-1.0 on every
    reading of the tool's own creatives, the wrong ones too)."""
    asked = [f for f in ("structure", "pacing", "hook") if f in plan.focus]
    if asked:
        return True, f"the reading is for {focus_text(asked)}"
    if "concept" in plan.focus and asks_pacing(plan):
        return True, "the concept read asks about the pacing"
    return False, "a read with no pacing question: the model's parts are kept as they are"


def _change(first: float, last: float) -> str:
    """The pace change from the first and the last third (as audit.pace_of_play and video_facts)."""
    if last > first * 1.3 and last - first >= 1:
        return "speeds up"
    if first > last * 1.3 and first - last >= 1:
        return "slows down"
    return "even"


def gameplay_motion_change(per_s: list[float], segs: list[dict]) -> str | None:
    """The motion-based pace change over the gameplay parts only (GAMEPLAY_PURPOSES), not the whole
    clip: on the tool's own 12 creatives the whole clip said "speeds up" 9 times, because the replay,
    the confetti and the end card fill its last third (2026-10-16)."""
    vals = [per_s[i] for s in segs if s.get("purpose") in GAMEPLAY_PURPOSES
            for i in range(int(s["from_s"]), int(math.ceil(s["to_s"]))) if 0 <= i < len(per_s)]
    if len(vals) < 3:
        return None
    third = len(vals) // 3
    a, b = sum(vals[:third]) / third, sum(vals[-third:]) / third
    return "speeds up" if b > a * 1.3 else "slows down" if a > b * 1.3 else "even"


def pacing_from(notes: dict, facts: dict, separated: dict | None) -> dict:
    """The reference's pacing, decided in code (2026-10-16, after two accuracy rounds on the tool's own
    creatives): the tempo word from the moves the model counted over the gameplay parts' length when the
    total is plausible (at least one move, at most about one a second), else the model's own word; the
    pace change from the motion measured over the gameplay parts, else the model's own word. The counts
    never give the change: per third they were not counts ([10, 10, 10] for 12 drags in all). Returns
    {moves_by_third, gameplay_s, dps, tempo, tempo_source, change, source (of the change), said, motion}."""
    said = {"pacing": notes.get("pacing"), "pace_change": notes.get("pace_change")}
    play_s = round(sum(max(0.0, s["to_s"] - s["from_s"]) for s in notes.get("structure") or []
                       if s.get("purpose") in GAMEPLAY_PURPOSES), 1)
    raw = notes.get("moves_by_third")
    counts = [_unit(x) for x in raw] if isinstance(raw, list) and len(raw) == 3 else None
    counts = counts if counts and all(c is not None and c >= 0 for c in counts) else None
    motion = facts.get("pace_change_play") if (separated or {}).get("ran") else None
    rec = {"moves_by_third": counts, "gameplay_s": play_s, "dps": None, "tempo": None, "tempo_source": "model",
           "change": None, "source": "model", "said": said, "motion": motion}
    total = sum(counts) if counts else 0
    if counts and play_s > 0 and 1 <= total <= play_s * PLAUSIBLE_DPS:
        dps = total / play_s
        rec.update(dps=round(dps, 2), tempo="calm" if dps < CALM_DPS else "fast" if dps > FAST_DPS else "normal",
                   tempo_source="counts")
    else:
        word = str(said["pacing"] or "").strip().lower()
        rec["tempo"] = word if word in ("calm", "normal", "fast") else None
        if counts:
            rec["counts_dropped"] = f"{total:g} moves over {play_s:g} s of gameplay is not plausible"
    if motion:
        rec.update(change=motion, source="motion")
    else:
        rec["change"] = _pace_words(said["pace_change"])
    return rec


def pace_change_of(a: dict) -> tuple[str | None, str]:
    """The reference's pace change and where it came from (motion or model), for videoref and the pacing
    row: the analysis's pacing when there is one, else the motion measured over the gameplay (2g),
    else the model's words."""
    p = a.get("pacing") or {}
    if p.get("change"):
        return p["change"], p.get("source") or "model"
    sep, facts, notes = a.get("separated") or {}, a.get("facts") or {}, a.get("notes") or {}
    if sep.get("ran") and facts.get("pace_change_play"):
        return facts["pace_change_play"], "motion"
    return _pace_words(notes.get("pace_change")), "model"


HUD_TEXT = re.compile(
    r"^\s*(?:(?:level|lvl|lv)\.?\s*\d*|\d+|(?:time\s*)?\d{1,2}:\d{2}|time|\+\s*\d+|coins?\s*\+?\s*\d*|replay|continue|"
    r"level\s+complete(?:d)?|level\s+failed|out\s+of\s+time|time'?s\s+up|retry|try\s+again|next)\s*[!.]*\s*$", re.I)


def captions_from_screen_text(notes: dict) -> list[str]:
    """Captions the model filed as the game's own text, moved back (2026-10-16: the v2 schema lost 15 of 75
    caption texts that way, mostly the end card's title and line). Every screen_text entry that is not the
    gameplay's HUD (HUD_TEXT: a level label, a clock reading, +50, REPLAY, Continue, Level Completed / Failed,
    Out of time) is appended to captions_seen, in order, without duplicates. Returns what moved."""
    caps = [str(c) for c in notes.get("captions_seen") or [] if str(c).strip()]
    have = {c.strip().lower() for c in caps}
    moved = []
    for s in notes.get("screen_text") or []:
        s = str(s).strip()
        if s and not HUD_TEXT.match(s) and s.lower() not in have:
            caps.append(s)
            have.add(s.lower())
            moved.append(s)
    if moved or "captions_seen" in notes:
        notes["captions_seen"] = caps
    return moved


def snap(segs: list[dict], cuts: list[float], duration_s: float | None, within: float = SNAP_S) -> tuple[list[dict], dict]:
    """Each model boundary moved to the nearest measured cut within `within` seconds (the clip's start
    and end stay). Returns the refined parts and {boundaries, snapped, at_a_cut}."""
    inner = sorted({v for s in segs for v in (s["from_s"], s["to_s"])
                    if v > 0.05 and not (duration_s and v >= duration_s - 0.05)})
    moved = {}
    at_cut = 0
    for v in inner:
        if not cuts:
            break
        c = min(cuts, key=lambda x: abs(x - v))
        if abs(c - v) <= within:
            if abs(c - v) < 0.05:
                at_cut += 1
            else:
                moved[v] = round(c, 1)
    out = []
    for s in segs:
        f, t = moved.get(s["from_s"], s["from_s"]), moved.get(s["to_s"], s["to_s"])
        if t <= f:  # two boundaries snapped onto one cut: this part keeps the model's seconds
            f, t = s["from_s"], s["to_s"]
        out.append({**s, "from_s": f, "to_s": t, **({"snapped": True} if (f, t) != (s["from_s"], s["to_s"]) else {})})
    return out, {"boundaries": len(inner), "snapped": len(moved), "at_a_cut": at_cut}


def separate_parts(notes: dict, facts: dict, plan: ReadingPlan, copy: Path, measure=None, log=None) -> dict:
    """The parts after the understanding, never before (2g). When needs_parts says so: cuts and the
    motion per second are measured on the normalised copy (video_facts), every model boundary is
    snapped to the nearest cut within SNAP_S, and the pace change is measured (first third against
    last third). The refined structure replaces the model's seconds; the model's own seconds
    (notes.structure_model), the cuts (facts.cuts_s) and the measured pace change (facts.pace_change)
    are kept beside it. A measured pace change that disagrees with the model's is the one used, and
    the disagreement is logged. Returns what ran."""
    say = log or (lambda *_: None)
    run, why = needs_parts(plan, notes)
    rec = {"ran": run, "why": why}
    if not run:
        say(f"parts: not separated ({why})")
        return rec
    m = (measure or video_facts)(copy)
    cuts = list(m.get("cuts_s") or [])
    model = [dict(s) for s in notes.get("structure") or []]
    refined, counts = snap(model, cuts, facts.get("duration_s"))
    notes["structure_model"], notes["structure"] = model, refined
    for k in ("cuts_s", "motion_per_s", "motion_first_third", "motion_last_third", "pacing"):
        if k in m:
            facts[k] = m[k]
    facts["cuts_s"] = cuts
    if m.get("pace_change"):
        facts["pace_change_clip"] = m["pace_change"]  # over the whole clip, kept for comparison
    play_change = gameplay_motion_change(m.get("motion_per_s") or [], refined)
    facts["pace_change_play"] = play_change  # over the gameplay parts only (None when they cannot be told apart)
    facts["pace_change"] = play_change or m.get("pace_change")
    rec.update(counts, cuts=len(cuts))
    said = _pace_words(notes.get("pace_change"))
    if facts.get("pace_change") and said and said != facts["pace_change"]:
        facts["pace_change_model"] = said
        rec["pace_change"] = (f"the model says the pace {said}, the gameplay's motion measured on the copy says "
                              f"{facts['pace_change']}; the moves the model counted decide when it gave them, else the measured one")
        say(f"parts: {rec['pace_change']}")
    say(f"parts: separated ({why}): {len(cuts)} cut(s) measured, {counts['snapped']} of {counts['boundaries']} "
        f"boundaries snapped to a cut within {SNAP_S:g} s ({counts['at_a_cut']} already on one); the gameplay's measured "
        f"pace change {facts.get('pace_change') or 'unknown'}" + ("" if play_change else " (the whole clip's)"))
    return rec


def read_video(path: Path, prompt: str, planner=None, client=None, log=None, measure=None) -> dict:
    """A reference video read for the request (2a-2g): the format step, the reading plan (the
    planner's model, `planner`), the composed prompt, the whole clip read by a multimodal model
    (`client`, video_client() by default: Gemini first, NVIDIA build when Gemini fails; the analysis
    records which, `reader`, and the model),
    the checks in code with one re-ask, then the parts when needed. Returns the analysis with the
    plan and the final prompt stored in it (`plan`, `ask`), its focus, level and seconds analysed,
    the validation result, the confidence and what the part separation did; or `error`, and the
    planner proceeds without it. `measure` replaces video_facts (tests)."""
    path = Path(path)
    say = log or (lambda *_: None)
    out = {"file": path.name, "kind": "video"}
    t0 = time.time()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "copy.mp4"
            facts = normalise_video(path, copy)
            out["facts"] = facts
            say(f"format: {format_line({**facts, 'file': path.name})}; {facts.get('codec')}; copied whole as "
                f"{facts['copy'].get('width')}x{facts['copy'].get('height')} H.264, {facts['frames']} frames at {facts['fps']:g} fps")
            plan = reading_plan(prompt, {**facts, "file": path.name}, planner, log)
            # read in full always; the plan's focus is what is APPLIED to the brief (2026-10-17, the owner)
            out.update(plan=plan.to_dict(), focus=list(plan.focus), level=plan.level, analysed_s=facts["analysed_s"],
                       read_all=True, applied=list(plan.focus))
            say(f"reading {path.name} in full; applied to the brief: {focus_text(plan.focus)} ({plan.level}): {plan.why}")
            ask = video_ask(plan, facts, prompt)
            out["ask"] = ask
            part = {"type": "video_url", "video_url": {"url": "data:video/mp4;base64," + base64.b64encode(copy.read_bytes()).decode()}}
            if client is None:
                client = video_client()
            order = getattr(client, "order", None)
            if order:  # the readers' order, said on the card and in the log (CBJ_VIDEO_READER overrides it)
                out["reader_order"] = {"order": list(order), "from": getattr(client, "order_from", "default")}
                say(f"readers: {' first, then '.join(order)}" + (" (CBJ_VIDEO_READER)" if out["reader_order"]["from"] ==
                                                                  "CBJ_VIDEO_READER" else ""))
            say(f"reading the whole clip ({facts['analysed_s']:g} s) with a multimodal model...")
            raw: list[str] = []
            out["raw_answers"] = raw  # only the answers that could not be parsed (removed when empty)
            notes = _ask_json(client, ask, part, path, raw)
            out["model"] = getattr(client, "last_model", None)
            out["reader"] = getattr(client, "reader", None) or reader_of(out["model"])  # with its model (the second read has its own)
            if not isinstance(notes, dict):
                raise ValueError("the answer is not a JSON object")
            problems = validate_notes(notes, facts, plan.focus, general=True)
            if problems:
                say(f"validation: the parts were rejected ({'; '.join(problems[:3])}); asking once more with the problems quoted")
                again_notes = _ask_json(client, ask + "\n\nYOUR LAST ANSWER WAS REJECTED: " + "; ".join(problems) +
                                        ". Answer again with the JSON object only, fixing these.", part, path, raw)
                out["model"] = getattr(client, "last_model", None)
                out["reader"] = getattr(client, "reader", None) or reader_of(out["model"])
                if isinstance(again_notes, dict):
                    notes = again_notes
                again = validate_notes(notes, facts, plan.focus, general=True)
                if again:
                    # per section (2026-10-17): the parts are dropped, the rest of the reading is kept and applied
                    out["validation"] = {"status": "passed without the parts", "problems": again, "first": problems}
                    out["parts_dropped"] = "the parts were not usable: " + "; ".join(again[:3])
                    notes["structure_rejected"], notes["structure"] = notes.get("structure"), []
                    say(f"validation: {out['parts_dropped']}; the rest of the reading is kept")
                else:
                    out["validation"] = {"status": "passed after one re-ask", "problems": [], "first": problems}
            else:
                out["validation"] = {"status": "passed", "problems": []}
            say(f"validation: {out['validation']['status']} (read by "
                f"{(getattr(client, 'reader', None) or reader_of(out.get('model')) or 'the multimodal model')}: {out.get('model') or '?'})")
            relabelled = [f"{s.get('purpose')!r} as {purpose_of(s.get('purpose'))}" for s in notes.get("structure") or []
                          if isinstance(s, dict) and _label(s.get("purpose")) != purpose_of(s.get("purpose"))]
            if relabelled:
                out["validation"]["relabelled"] = relabelled
                say(f"labels read as the tool's purposes: {'; '.join(relabelled[:6])}")
            notes["structure"] = structure(notes.get("structure"), facts["duration_s"])
            if notes.get("ending") in ("near-fail", "near_fail", "none"):
                seen = json.dumps(notes, ensure_ascii=False).lower()
                if "out of time" in seen or "fail screen" in seen:
                    notes["ending"] = "fail"  # the game's fail screen was seen: a time-out, not a near-fail
            if not isinstance(notes.get("roles"), list) or not notes["roles"]:
                notes["roles"] = list(plan.focus)
            if isinstance(notes.get("mistakes"), list):  # one entry per wrong move; the model's own yes/no stays the backstop
                notes["mistakes"] = [{"at_s": None if _unit(m.get("at_s")) is None else round(_unit(m["at_s"]), 1),
                                      "what": str(m.get("what") or "")[:120]} for m in notes["mistakes"] if isinstance(m, dict)][:6]
                if not isinstance(notes.get("mistakes_shown"), bool):
                    notes["mistakes_shown"] = bool(notes["mistakes"])
            moved = captions_from_screen_text(notes)
            if moved:
                out["validation"]["captions_moved"] = moved
                say(f"captions filed as the game's text, moved back: {'; '.join(moved[:6])}")
            conf = _unit(notes.get("confidence"))
            out["confidence"] = None if conf is None else round(conf, 2)
            if conf is not None and conf < LOW_CONFIDENCE:
                out["low_confidence"] = True  # shown on the card and the confidence row; it decides nothing
                say(f"{path.name}: the model rates its reading {conf:.2f} (shown, not used to decide anything)")
            out["notes"] = notes
            # the ending, read a second time on the last seconds; it wins over the whole clip's when they disagree
            er = read_ending(client, copy, facts, log)
            out["ending_read"] = er
            if er.get("ending"):
                from .videoref import mapped_ending
                whole = mapped_ending(notes)  # the whole-clip read's ending as the tool reads it
                notes["ending_read"] = {k: er.get(k) for k in ("ending", "last_clock", "win_screen", "out_of_time_screen",
                                                               "question_caption", "blocks_left")}
                if er["ending"] != whole:
                    notes["ending_whole"], notes["ending"] = notes.get("ending"), ENDING_SPELLING[er["ending"]]
                    er["overrode"] = {"whole_clip": whole, "last_s": er["ending"]}
                    say(f"ending: the last {ENDING_READ_S:g} s read say {ENDING_SPELLING[er['ending']]} (clock {er.get('last_clock') or '?'}; "
                        f"{er.get('why') or ''}); the whole clip said {(whole or 'nothing').replace('_', '-')}: the last seconds win")
                else:
                    say(f"ending: the last {ENDING_READ_S:g} s read agree ({ENDING_SPELLING[er['ending']]}, clock {er.get('last_clock') or '?'})")
            else:
                say(f"ending: not read again ({er.get('skipped') or er.get('error')}); the whole clip's ending stands")
            # the board, read a second time on a still at the source's resolution, on every reading (2026-10-17)
            from .videoref import board_of, board_text
            br = read_board(client, path, notes, facts, log)
            out["board_read"] = br
            if br.get("board"):
                notes["board_whole"], notes["board"] = notes.get("board"), br["board"]
            if br.get("extras_seen"):
                seen = [str(x) for x in notes.get("extras_seen") or [] if str(x).strip()] if isinstance(notes.get("extras_seen"), list) else []
                notes["extras_seen"] = list(dict.fromkeys(seen + br["extras_seen"]))
            bd = board_of(notes)
            crop = br.get("crop") or {}
            say(f"board: {board_text(bd) if bd else 'no board was read'} (" +
                (f"read on a still at {br['at_s']:g} s, {br['width']}x{br['height']}" +
                 (f", then on a {crop['width']}x{crop['height']} crop of its box" if crop.get("read") else "") if br.get("board") else
                 f"the whole clip's; the still: {br.get('error')}") + f"; {br.get('seconds', 0):g} s)"
                + (f"; past the board step's {BOARD_READ_BUDGET_S:g} s: {', '.join(br['skipped'])}" if br.get("skipped") else ""))
            out["separated"] = separate_parts(notes, facts, plan, copy, measure=measure, log=log)
            out["pacing"] = pacing_from(notes, facts, out["separated"])
            notes["pacing_said"], notes["pace_change_said"] = out["pacing"]["said"]["pacing"], out["pacing"]["said"]["pace_change"]
            if out["pacing"]["tempo"]:
                notes["pacing"] = out["pacing"]["tempo"]
            if out["pacing"]["change"]:
                notes["pace_change"] = out["pacing"]["change"]
            p = out["pacing"]
            say(f"pacing (approximate, a sampled read): tempo {p['tempo'] or '?'} ({p['tempo_source']}"
                + (f": {p['moves_by_third']} moves over {p['gameplay_s']:g} s of gameplay, {p['dps']} a second" if p["tempo_source"] == "counts" else "")
                + f"), change {p['change'] or '?'} ({p['source']}); the model said {p['said']['pacing'] or '?'}, "
                f"{p['said']['pace_change'] or '?'}" + (f"; {p['counts_dropped']}" if p.get("counts_dropped") else ""))
    except Exception as e:  # reported in the brief, never guessed around
        out["error"] = str(e)[:300]
        say(f"{path.name}: not analysed ({out['error'][:160]}); the plan proceeds without it")
    if getattr(client, "errors", None):
        out["errors"] = list(client.errors)[-12:]  # what failed on the way, model by model
        quota = list(dict.fromkeys(e for e in client.errors if "daily free quota used up" in e))
        if quota:  # once per reading, on the card too (2026-10-17)
            out["quota"] = quota
            say("; ".join(quota) + ": the next reader answered")
    if not out.get("model") and getattr(client, "last_model", None):
        out["model"] = client.last_model  # it answered, even if the answer could not be used
    if out.get("model") and not out.get("reader"):
        out["reader"] = getattr(client, "reader", None) or reader_of(out["model"])
    if getattr(client, "usage", None):
        out["usage"] = list(client.usage)[-4:]
    if not out.get("raw_answers"):
        out.pop("raw_answers", None)
    out["seconds"] = round(time.time() - t0, 1)
    return out
