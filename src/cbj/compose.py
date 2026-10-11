"""Render an ad.json into a finished ad, with the record that proves what changed between edits.

For every output frame: the gameplay (or card) is placed on the canvas, the active layers are
drawn on top, the frame is hashed (SHA-256 of the raw RGB) and encoded. Sound effects are mixed at
their resolved times. The output folder holds:

    ad.mp4        the finished ad
    ad.json       the document it was made from
    compose.json  the proof: tool versions, source hashes, the timeline with each segment's fit,
                  every layer's frames and pixel box, a SHA-256 per frame, the WAV and MP4 hashes,
                  and the QA results
    poster.png    frame 0 (the thumbnail platforms show)

If the gameplay file's hash and a segment's fit are unchanged between two renders, the gameplay,
camera and timing are unchanged by construction; comparing the frame hashes then shows exactly
which frames an edit touched, and the layer boxes show where.
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from pathlib import Path

import numpy as np
import PIL
from PIL import Image, ImageDraw, ImageFilter

from . import __version__ as CBJ_VERSION
from .ad import (BAND, FPS, SAFE, STYLES, TWO_LINE_SIZE, END_CARD_S, Recording, check_ad, copy_problems, fill,
                 layer_window, reading_s, resolve_time, seg_frames, source_frame, timeline, to_output)
from .draw import (PURPLE, WHITE, blend, clamp01, cover, ease_in_out, ease_out_back, ease_out_cubic, fit_text,
                   scaled, sprite, text_image, wrap)
from .sound import RATE, render_track, write_wav
from .video import FrameWriter, ffmpeg_bin, mux, read_frames

TEXT_TYPES = ("text", "tag", "button")


# ---------- placing gameplay on the canvas ----------

class Placer:
    """Scales a recorded frame by its fit and puts it on a canvas filled with the recording's own
    background gradient, so the letterbox has no visible edge."""

    def __init__(self, first_frame: np.ndarray, fit: dict, size: tuple[int, int], draft: bool = False):
        self.w, self.h = size
        self.fit = fit
        self.filter = Image.BILINEAR if draft else Image.LANCZOS
        s = fit["scale"]
        fh, fw = first_frame.shape[:2]
        self.sw, self.sh = round(fw * s), round(fh * s)
        edge = (first_frame[:, :8].astype(np.float32).mean(1) + first_frame[:, -8:].astype(np.float32).mean(1)) / 2
        rows = np.clip(np.round((np.arange(self.h) - fit["y"]) / s).astype(int), 0, fh - 1)
        self.bg = np.ascontiguousarray(np.repeat(np.round(edge[rows]).astype(np.uint8)[:, None, :], self.w, axis=1))

    def place(self, frame: np.ndarray) -> np.ndarray:
        if self.fit["scale"] == 1 and self.fit["x"] == 0 and self.fit["y"] == 0 and frame.shape[:2] == (self.h, self.w):
            return frame.copy()
        canvas = self.bg.copy()
        small = np.asarray(Image.fromarray(frame).resize((self.sw, self.sh), self.filter))
        x0, y0 = self.fit["x"], self.fit["y"]
        cx0, cy0 = max(0, x0), max(0, y0)
        cx1, cy1 = min(self.w, x0 + self.sw), min(self.h, y0 + self.sh)
        canvas[cy0:cy1, cx0:cx1] = small[cy0 - y0:cy1 - y0, cx0 - x0:cx1 - x0]
        return canvas

    def point(self, x: float, y: float) -> tuple[float, float]:
        s = self.fit["scale"]
        return x * s + self.fit["x"], y * s + self.fit["y"]


# ---------- the cursor ----------

def cursor_track(rec: Recording) -> list[dict]:
    """Per recording frame: where the tap ring is, whether the finger is down, and how long since
    the last press or release. Between drags the ring glides to the next press point."""
    fr = rec.frames
    n = len(fr)
    track = [{"x": f["finger_x"], "y": f["finger_y"], "down": f["finger"], "since": 999, "alpha": 0.0,
              "released": False} for f in fr]
    downs = [i for i in range(n) if fr[i]["finger"] and (i == 0 or not fr[i - 1]["finger"])]
    ups = [i for i in range(1, n) if not fr[i]["finger"] and fr[i - 1]["finger"]]
    # Time since the last change, for the press and release animations.
    last, state = None, None
    released = False
    for i in range(n):
        if fr[i]["finger"] != state:
            released = state is True  # a real lift, not the start of the video
            last, state = i, fr[i]["finger"]
        track[i]["since"] = i - last if last is not None else 999
        track[i]["released"] = released and not fr[i]["finger"]
        track[i]["alpha"] = 1.0 if fr[i]["finger"] else 0.0
    # Before the first press the ring is not shown; after a release it waits at 70%, then glides
    # (ease in-out, up to 18 frames, arriving 2 frames early) to the next press point.
    for u in ups:
        nxt = next((d for d in downs if d > u), None)
        rx, ry = fr[u - 1]["finger_x"], fr[u - 1]["finger_y"]
        end = nxt if nxt is not None else n
        for i in range(u, end):
            track[i]["x"], track[i]["y"], track[i]["alpha"] = rx, ry, 0.7
        if nxt is not None:
            gap = nxt - u
            glide = min(18, max(0, gap - 2))
            tx, ty = fr[nxt]["finger_x"], fr[nxt]["finger_y"]
            g0 = nxt - 2 - glide
            for i in range(max(u, g0), nxt):
                k = ease_in_out((i - g0) / max(1, glide))
                track[i]["x"], track[i]["y"] = rx + (tx - rx) * k, ry + (ty - ry) * k
    return track


def ring_image(size: int, fill_alpha: float, ring_alpha: float = 1.0) -> Image.Image:
    pad = 12
    d = size + 2 * pad
    img = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    halo = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    ImageDraw.Draw(halo).ellipse((pad - 3, pad - 3, pad + size + 3, pad + size + 3), outline=(0, 0, 0, 90), width=10)
    img = Image.alpha_composite(img, halo.filter(ImageFilter.GaussianBlur(3)))
    dr = ImageDraw.Draw(img)
    dr.ellipse((pad, pad, pad + size, pad + size), fill=(255, 255, 255, int(255 * fill_alpha)),
               outline=(255, 255, 255, int(255 * ring_alpha)), width=7)
    return img


def draw_cursor(frame, st: dict, placer: Placer, size: int, speed: float, image: Image.Image | None):
    """The tap ring (or a hand image) at one frame. Animations run in recording frames, so in a
    0.5x replay they play at half speed with everything else."""
    boxes = []
    ripple = st.get("released") and st["since"] < 8
    if st["alpha"] <= 0 and not ripple:
        return boxes
    x, y = placer.point(st["x"], st["y"])
    s = placer.fit["scale"] / 0.75  # the ring keeps its size relative to the board
    if st["down"]:
        k = ease_out_cubic(st["since"] / 4)
        scale = (1.25 - 0.25 * k) * s
        img = image if image is not None else ring_image(int(size * scale), 0.28 + 0.22 * k)
        boxes.append(blend(frame, img, x, y, 1.0))
    else:
        if image is not None:
            boxes.append(blend(frame, image, x, y, st["alpha"]))
            return [b for b in boxes if b]
        boxes.append(blend(frame, ring_image(int(size * s), 0.28), x, y, st["alpha"]))
        if ripple:  # the release ripple
            k = st["since"] / 8
            boxes.append(blend(frame, ring_image(int(size * s * (1 + 0.6 * k)), 0.0, 0.8), x, y, 1 - k))
    return [b for b in boxes if b]


# ---------- text, tags, buttons ----------

def layer_image(layer: dict, text: str) -> Image.Image:
    kind = layer["type"]
    if kind == "tag" and layer.get("shape") == "circle":
        # A round badge, sized to cover the HUD element it sits on (the level circle).
        d = int(layer.get("diameter", 252))
        badge = Image.new("RGBA", (d, d), (0, 0, 0, 0))
        ImageDraw.Draw(badge).ellipse((3, 3, d - 4, d - 4), fill=(*PURPLE, 255), outline=(*WHITE, 255), width=8)
        label = fit_text(text, STYLES.get(layer.get("style", "tag"), 54), int(d * 0.8), int(d * 0.5), shadow=False)
        badge.alpha_composite(label, ((d - label.width) // 2, (d - label.height) // 2))
        return badge
    if kind == "tag":
        label = text_image(text, STYLES.get(layer.get("style", "tag"), 54), shadow=False)
        w, h = label.width + 40, label.height + 10
        pill = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(pill).rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=(*PURPLE, 235),
                                               outline=(*WHITE, 255), width=5)
        pill.alpha_composite(label, ((w - label.width) // 2, (h - label.height) // 2))
        return pill
    if kind == "button":
        btn = scaled(sprite(layer.get("image", "ContinueButtonEmpty.png")), layer.get("scale", 0.9)).copy()
        label = text_image(text, int(84 * layer.get("scale", 0.9) / 0.9), shadow=False)
        btn.alpha_composite(label, ((btn.width - label.width) // 2, max(0, (btn.height - label.height) // 2 - 10)))
        return btn
    size = STYLES.get(layer.get("style", "title_xl"), 96)
    icon = layer.get("icon")
    icon_w = 126 if icon else 0
    if layer.get("slot") == "top":
        # In the band: the largest one- or two-line size that fits between the safe top and the HUD.
        # The pop-in overshoots to about 1.04x, so fit with that room to spare.
        img = fit_text(text, size, int((BAND["max_w"] - icon_w) / 1.05), int((BAND["y1"] - BAND["y0"]) / 1.05))
    else:
        # Placed texts (the end card) fit the safe width too, in one or two lines.
        img = fit_text(text, size, int(BAND["max_w"] / 1.05), layer.get("max_h", 260))
    if icon:
        ic = scaled(sprite(icon), 110 / sprite(icon).width)
        out = Image.new("RGBA", (ic.width + 16 + img.width, max(ic.height, img.height)), (0, 0, 0, 0))
        out.alpha_composite(ic, (0, (out.height - ic.height) // 2))
        out.alpha_composite(img, (ic.width + 16, (out.height - img.height) // 2))
        img = out
    return img


def anim_state(layer: dict, t: int, f0: int, f1: int, total: int | None = None) -> tuple[float, float]:
    """(scale, opacity) of a layer at output frame t. A layer that lasts to the end of the ad holds
    (no fade-out): the last frame is what a feed shows when the ad ends or loops."""
    anim = layer.get("anim", "pop")
    scale, alpha = 1.0, 1.0
    if anim in ("pop",) and t - f0 < 6:
        k = (t - f0) / 6
        scale = 0.6 + 0.4 * ease_out_back(k)
        alpha = clamp01((t - f0 + 1) / 3)
    if anim in ("pop", "pop_out") and f1 - t <= 4 and not (total is not None and f1 >= total):
        k = (f1 - t) / 4
        scale *= 0.85 + 0.15 * k
        alpha *= k
    if layer.get("pulse"):
        scale *= 1 + 0.06 * ease_in_out(0.5 - 0.5 * math.cos(2 * math.pi * (t - f0) / FPS))
    return scale, alpha


def vignette_image(size: tuple[int, int], color) -> Image.Image:
    w, h = size
    yy, xx = np.mgrid[0:h, 0:w]
    dx = np.minimum(xx, w - 1 - xx) / (w * 0.22)
    dy = np.minimum(yy, h - 1 - yy) / (h * 0.14)
    a = np.clip(1 - np.minimum(dx, dy), 0, 1) ** 1.6
    img = np.zeros((h, w, 4), np.uint8)
    img[..., :3] = color
    img[..., 3] = (a * 255).astype(np.uint8)
    return Image.fromarray(img, "RGBA")


# ---------- rendering ----------

ORDER_Z = {"vignette": 0, "cursor": 1, "image": 2, "button": 3, "text": 4, "tag": 5}


class Prepared:
    """An ad.json resolved for drawing: recordings, the timeline, every layer's frames, text and
    image, sound events, and the QA found before any frame is drawn."""

    def __init__(self, ad: dict, draft: bool = False):
        check_ad(ad)
        self.ad, self.draft = ad, draft
        self.size = (ad["output"]["w"], ad["output"]["h"])
        self.recs = {sid: Recording.load(s["recording"]) for sid, s in ad["sources"].items()}
        self.qa = {"failures": [], "warnings": []}
        for sid, s in ad["sources"].items():
            if s.get("sha256") and s["sha256"] != self.recs[sid].sha():
                self.qa["failures"].append(f"source {sid!r}: gameplay.mp4 changed since ad.json was made (hash differs)")
        self.tl = timeline(ad)
        self.total = max(e for _, e in self.tl.values())
        self._check_locked()
        self.layers = self._resolve_layers()
        try:
            self.events = audio_events(ad, self.recs, self.tl, self.total)
        except (ValueError, KeyError) as e:
            self.events = []
            self.qa["failures"].append(f"audio: {e}")
        self.draw_order = sorted(self.layers, key=lambda k: ORDER_Z[self.layers[k]["layer"]["type"]])
        self._placers, self._firsts = {}, {}

    def _check_locked(self):
        """`locked` parts must match the digests written when the ad was made (case p.3: elements
        that must stay unchanged). To change one on purpose, remove it from `locked` first."""
        from .ad import locked_digests
        origin = self.ad.get("origin", {}).get("locked")
        if origin is None:
            if self.ad.get("locked"):
                self.qa["warnings"].append("ad.json has no origin digests, so locked parts cannot be checked")
            return
        now = locked_digests(self.ad)
        for path, digest in now.items():
            if path in origin and origin[path] != digest:
                self.qa["failures"].append(f"locked part {path!r} changed; to change it on purpose, remove it "
                                           f"from 'locked' in ad.json first")

    def _resolve_layers(self) -> dict:
        ad, recs, tl, total, size = self.ad, self.recs, self.tl, self.total, self.size
        layers = {}
        for lid, layer in ad["layers"].items():
            if layer.get("enabled") is False:
                continue
            try:
                f0, f1 = layer_window(ad, recs, lid) if layer["type"] != "cursor" else (0, total)
            except (ValueError, KeyError) as e:
                self.qa["failures"].append(f"layer {lid!r}: {e}")
                continue
            if layer["type"] != "cursor":
                seg_id = layer.get("seg") or layer.get("start", {}).get("seg")
                s0, s1 = tl.get(seg_id, (0, total))
                if not (0 <= f0 < f1 <= total):
                    self.qa["failures"].append(f"layer {lid!r}: frames {f0}-{f1} are not inside the ad (0-{total})")
                    continue
                if f0 >= s1 or f0 < s0:
                    self.qa["failures"].append(f"layer {lid!r}: starts at frame {f0}, outside its segment "
                                               f"{seg_id!r} ({s0}-{s1})")
                    continue
                end_seg = layer.get("end", {}).get("seg", seg_id) if isinstance(layer.get("end"), dict) else seg_id
                if f1 > s1 and end_seg == seg_id:
                    self.qa["failures"].append(f"layer {lid!r}: runs to frame {f1}, past the end of its segment "
                                               f"{seg_id!r} ({s1}); end it there or anchor its end in the next one")
                    continue
            entry = {"layer": layer, "f0": f0, "f1": f1, "boxes": []}
            if layer["type"] in TEXT_TYPES:
                seg_id = layer.get("seg") or layer.get("start", {}).get("seg")
                src = ad["segments"].get(seg_id, {}).get("src") or next(iter(recs))
                try:
                    text = fill(layer["text"], recs[src].facts(layer.get("beat")))
                except ValueError as e:
                    self.qa["failures"].append(f"layer {lid!r}: {e}")
                    continue
                self.qa["failures"] += [f"layer {lid!r}: {p}" for p in copy_problems(text)]
                entry["text"] = text
                entry["image"] = layer_image(layer, text)
                if layer.get("slot") == "top" and entry["image"].height > BAND["y1"] - BAND["y0"]:
                    self.qa["failures"].append(f"layer {lid!r}: too long for the text band even at the smallest size")
                if layer["type"] == "text":
                    need = reading_s(text)  # time to read it
                    if (f1 - f0) / FPS < need - 1e-6:
                        self.qa["failures"].append(f"layer {lid!r}: on screen {(f1 - f0) / FPS:.2f} s; "
                                                   f"its words need {need:.1f} s")
            elif layer["type"] == "image":
                entry["image"] = scaled(sprite(layer["image"]), layer.get("scale", 1.0))
            elif layer["type"] == "vignette":
                entry["image"] = vignette_image(size, layer.get("color", [255, 40, 40]))
                sid = layer["start"].get("seg")
                seg = ad["segments"][sid]
                pulses = [to_output(seg, tl[sid][0], f) for f in recs[seg["src"]].event(layer.get("pulse_on", ""))]
                entry["pulses"] = sorted(p for p in pulses if p is not None)
            elif layer["type"] == "cursor":
                entry["image"] = sprite(layer["image"]) if layer.get("image") else None
                entry["tracks"] = {sid: cursor_track(r) for sid, r in recs.items()}
            layers[lid] = entry
        return layers

    def placer(self, src, fit):
        key = (src, json.dumps(fit, sort_keys=True))
        if key not in self._placers:
            if src not in self._firsts:
                self._firsts[src] = next(read_frames(self.recs[src].video, self.size, 0, 1)).copy()
            self._placers[key] = Placer(self._firsts[src], fit, self.size, self.draft)
        return self._placers[key]

    def card_base(self, seg) -> np.ndarray:
        base = cover(sprite(seg.get("background", "StartBACKGROUND.png")), self.size)
        th = seg.get("thumb")
        if th:
            f = next(read_frames(self.recs[th["src"]].video, self.size, th["frame"], 1))
            y0, y1 = th.get("crop_y", [0, f.shape[0]])
            im = scaled(Image.fromarray(f[y0:y1]).convert("RGBA"), th.get("scale", 0.5))
            framed = Image.new("RGBA", (im.width + 16, im.height + 16), (*WHITE, 255))
            framed.alpha_composite(im, (8, 8))
            blend(base, framed, *th.get("pos", [540, 960]))
        return base

    def keyframes(self) -> list[int]:
        """Every segment and layer boundary starts a GOP, so a change inside one span cannot touch
        the decoded pixels of any other (the MP4 stays local to an edit, not just the frames)."""
        ks = {0}
        for a, b in self.tl.values():
            ks.update((a, b))
        for e in self.layers.values():
            if e["layer"]["type"] != "cursor":
                ks.update((e["f0"], e["f1"]))
        return sorted(k for k in ks if 0 <= k < self.total)

    def frames(self, want: set[int] | None = None):
        """Yield (t, composited RGB frame) for every output frame, or only those in want (the
        others are stepped over without drawing)."""
        W, H = self.size
        for sid in self.ad["order"]:
            seg = self.ad["segments"][sid]
            s0, s1 = self.tl[sid]
            if want is not None and not any(s0 <= t < s1 for t in want):
                continue
            if seg["kind"] == "card":
                base = self.card_base(seg)
                source = (base for _ in range(s1 - s0))
            elif seg["kind"] == "hold":
                still = next(read_frames(self.recs[seg["src"]].video, self.size, seg["frame"], 1)).copy()
                placed = self.placer(seg["src"], seg["fit"]).place(still)
                source = (placed for _ in range(s1 - s0))
            else:
                reader = read_frames(self.recs[seg["src"]].video, self.size, seg["from"], seg["to"] - seg["from"])
                source = _clip_frames(reader, seg, self.placer(seg["src"], seg["fit"]), s1 - s0)
            for k, base in enumerate(source):
                t = s0 + k
                if want is not None and t not in want:
                    continue
                frame = base.copy()
                for lid in self.draw_order:
                    self._draw(lid, frame, t, sid, seg, k, W, H)
                yield t, np.ascontiguousarray(frame)

    def _draw(self, lid, frame, t, sid, seg, k, W, H):
        e = self.layers[lid]
        lay = e["layer"]
        if lay["type"] == "cursor":
            if seg["kind"] == "clip" and sid in lay.get("segments", []):
                st = e["tracks"][seg["src"]][source_frame(seg, k)]
                e["boxes"] += draw_cursor(frame, st, self.placer(seg["src"], seg["fit"]), lay.get("size", 96),
                                          seg.get("speed", 1), e["image"])
            return
        if not e["f0"] <= t < e["f1"]:
            return
        if lay["type"] == "vignette":
            a, pf = 0.0, lay.get("pulse_frames", 10)
            for p in e["pulses"]:
                if p <= t < p + pf:
                    a = max(a, math.sin(math.pi * (t - p) / pf))
            if a > 0:
                b = blend(frame, e["image"], W / 2, H / 2, a * lay.get("max_alpha", 0.35))
                if b:
                    e["boxes"].append(b)
            return
        if e.get("image") is None:
            return
        sc, op = anim_state(lay, t, e["f0"], e["f1"], self.total)
        b = blend(frame, scaled(e["image"], sc), *lay.get("pos", [BAND["cx"], BAND["cy"]]), op)
        if b:
            e["boxes"].append(b)


def render(ad: dict, out_dir: str | Path, draft: bool = False) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for stale in ("ad.mp4", "ad.FAILED.mp4", "poster.png", "audio.wav", "compose.json"):
        (out / stale).unlink(missing_ok=True)
    prep = Prepared(ad, draft)
    qa, total = prep.qa, prep.total
    # Problems found so far (a claim the ad rules forbid, an anchor that cannot resolve, a locked
    # part changed, a text too long to read) stop here, before any frame is drawn.
    if qa["failures"]:
        result = {"rendered": False, "frames": total, "duration_s": round(total / FPS, 3), "draft": draft,
                  "timeline": {}, "layers": {}, "qa": qa}
        (out / "compose.json").write_text(json.dumps(result, indent=1))
        return result
    writer = FrameWriter(out / "video.mp4", prep.size, FPS, ad["output"].get("crf", 16), draft=draft,
                         keyframes=prep.keyframes())
    hashes, poster = [], None
    try:
        for t, frame in prep.frames():
            hashes.append(hashlib.sha256(frame.data).hexdigest()[:32])
            if t == 0:
                poster = frame.copy()
            writer.write(frame)
        writer.close()
    except BaseException:
        writer.proc.kill()
        raise
    track = render_track(prep.events, total / FPS)
    write_wav(track, out / "audio.wav")
    mux(out / "video.mp4", out / "audio.wav", out / "ad.mp4")
    (out / "video.mp4").unlink()
    if poster is not None:
        Image.fromarray(poster).save(out / "poster.png")
    _qa(ad, prep, track, hashes)
    if qa["failures"]:
        (out / "ad.mp4").rename(out / "ad.FAILED.mp4")  # never leave a failed ad looking finished
    (out / "ad.json").write_text(json.dumps(ad, indent=2))
    result = {
        "rendered": True,
        "tool": {"cbj": CBJ_VERSION, "pillow": PIL.__version__, "numpy": np.__version__, "ffmpeg": _ffmpeg_version(),
                 "resize": "bilinear" if draft else "lanczos"},
        "ad_sha256": hashlib.sha256(json.dumps(ad, sort_keys=True).encode()).hexdigest(),
        "sources": {sid: {"recording": s["recording"], "sha256": prep.recs[sid].sha()}
                    for sid, s in ad["sources"].items()},
        "frames": total, "fps": FPS, "duration_s": round(total / FPS, 3),
        "timeline": {sid: {"frames": list(prep.tl[sid]), "kind": ad["segments"][sid]["kind"],
                           "fit": ad["segments"][sid].get("fit")} for sid in ad["order"]},
        "layers": {lid: {"type": e["layer"]["type"], "frames": [e["f0"], e["f1"]], "text": e.get("text"),
                         "box": _union(e["boxes"])} for lid, e in prep.layers.items()},
        "keyframes": prep.keyframes(),
        "audio_events": prep.events,
        "frame_sha256": hashes,  # first 128 bits of each composited RGB frame's SHA-256
        "wav_sha256": hashlib.sha256((out / "audio.wav").read_bytes()).hexdigest(),
        "mp4_sha256": hashlib.sha256(((out / "ad.mp4") if (out / "ad.mp4").exists()
                                      else (out / "ad.FAILED.mp4")).read_bytes()).hexdigest(),
        "draft": draft,
        "qa": qa,
    }
    (out / "compose.json").write_text(json.dumps(result, indent=1))
    return result


def _clip_frames(reader, seg: dict, pl: Placer, n_out: int):
    """Output frames of a clip: each recording frame placed once and repeated as the speed needs."""
    cur_idx, cur = None, None
    it = iter(reader)
    for k in range(n_out):
        want = source_frame(seg, k) - seg["from"]
        while cur_idx is None or cur_idx < want:
            raw = next(it)
            cur_idx = 0 if cur_idx is None else cur_idx + 1
            if cur_idx == want:
                cur = pl.place(raw)
        yield cur


def audio_events(ad: dict, recs: dict, tl: dict, total: int) -> list[dict]:
    """Every sound at its output time. Events at gameplay moments sound in every clip that shows
    them (so a replay replays its pops); pitch "cascade" rises over the last three exits and
    "ticktock" alternates."""
    out = []
    for name, ev in ad.get("audio", {}).get("events", {}).items():
        times = []
        if "event" in ev or "frame" in ev:
            for sid in ad["order"]:
                seg = ad["segments"][sid]
                if seg["kind"] != "clip" or (ev.get("seg") and ev["seg"] != sid):
                    continue
                if ev.get("slowmo") is False and seg.get("speed", 1) < 1:
                    continue  # a clock ticking at half speed sounds wrong in a replay
                frames = [ev["frame"]] if "frame" in ev else recs[seg["src"]].event(ev["event"])
                for i, f in enumerate(sorted(frames)):
                    o = to_output(seg, tl[sid][0], f)
                    if o is not None:
                        times.append((o, i, len(frames)))
        else:
            o = resolve_time(ad, recs, {"seg": ev["seg"], "at": ev.get("at", 0)}, ev["seg"])
            times.append((o, 0, 1))
        for o, i, n in times:
            pitch = ev.get("pitch", 1.0)
            if pitch == "cascade":
                pitch = cascade_pitch(i, n)
            elif pitch == "ticktock":
                pitch = 1.0 if i % 2 == 0 else 0.84
            e = {"name": name, "sound": ev["sound"], "t": round(o / FPS, 4), "gain": ev.get("gain", 0.5)}
            if pitch != 1.0:
                e["pitch"] = pitch
            if o < total:
                out.append(e)
    return sorted(out, key=lambda e: (e["t"], e["name"]))


def cascade_pitch(i: int, n: int) -> float:
    """Exit pops rise over the last three exits: ..., 1.0, 1.12, 1.26 (the final exit highest)."""
    return 1.26 if i == n - 1 else 1.12 if i == n - 2 else 1.0


def _union(boxes):
    if not boxes:
        return None
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]


def _ffmpeg_version() -> str:
    try:
        return subprocess.run([ffmpeg_bin(), "-version"], capture_output=True, text=True).stdout.split("\n")[0]
    except (OSError, ValueError):
        return "unknown"


def _qa(ad, prep, track, hashes):
    qa, layers, tl, total = prep.qa, prep.layers, prep.tl, prep.total
    want = ad.get("length_s")
    if want and total != int(round(want * FPS)):
        qa["failures"].append(f"the ad is {total / FPS:.2f} s, the target is {want} s")
    if len(hashes) != total:
        qa["failures"].append(f"{len(hashes)} frames written, {total} planned")
    safe = SAFE[ad["output"].get("safe", "social")]
    W, H = ad["output"]["w"], ad["output"]["h"]
    area = (safe["left"], safe["top"], W - safe["right"], H - safe["bottom"])
    tops = []
    for lid, e in layers.items():
        lay = e["layer"]
        if lay["type"] not in TEXT_TYPES:
            continue
        box = _union(e["boxes"])
        if lay["type"] == "text" and lay.get("slot") == "top":
            tops.append((e["f0"], e["f1"], lid))
        if box and lay.get("safe_exempt"):
            continue  # placed outside the safe area on purpose; the reason is in ad.json
        if box and not (box[0] >= area[0] and box[1] >= area[1] and box[2] <= area[2] and box[3] <= area[3]):
            msg = f"layer {lid!r}: drawn at {box}, outside the {ad['output'].get('safe', 'social')} safe area {list(area)}"
            (qa["warnings"] if lay["type"] == "tag" else qa["failures"]).append(msg)
    tops.sort()
    for (a0, a1, a), (b0, b1, b) in zip(tops, tops[1:]):
        if b0 < a1:
            qa["failures"].append(f"layers {a!r} and {b!r} overlap in the text band ({b0 / FPS:.2f}-{a1 / FPS:.2f} s)")
    if "hook" in layers and layers["hook"]["f0"] != 0:
        qa["failures"].append("the hook does not start on frame 0 (the poster)")
    if "hook" not in layers:
        qa["warnings"].append("no hook layer")
    cta = [lid for lid, e in layers.items() if e["layer"]["type"] == "button"]
    for lid in cta:
        if layers[lid]["f1"] < total:
            qa["failures"].append(f"layer {lid!r}: the call to action is gone before the last frame")
    ends = [sid for sid in ad["order"] if ad["segments"][sid]["kind"] == "card"]
    if ends:
        n = tl[ends[-1]][1] - tl[ends[-1]][0]
        if n < END_CARD_S[0] * FPS:
            qa["failures"].append(f"end card {n / FPS:.2f} s; at least {END_CARD_S[0]} s")
        elif n > 6 * FPS:
            qa["warnings"].append(f"end card {n / FPS:.2f} s is long; a longer recording would fill the ad better")
    peak = float(np.abs(track).max()) if len(track) else 0.0
    if peak > 10 ** (-1 / 20) + 1e-6:
        qa["failures"].append(f"audio peak {20 * math.log10(peak):.2f} dBFS; above -1 dBFS")
    if abs(len(track) / RATE - total / FPS) > 1 / FPS:
        qa["failures"].append("audio and video lengths differ")


# ---------- comparing two renders (the edit proof) ----------

def diff(a_dir: str | Path, b_dir: str | Path, decode: bool = False) -> dict:
    """What changed between two renders of an ad. Frames are compared by their hashes; for every
    changed frame both ads are composited again (deterministically) and the changed pixels' box
    is measured and checked against the boxes of the layers whose entries changed: every change
    must be one the edit predicts. Also reports locked parts, the gameplay sources, the timeline
    and the sound.

    The MP4: each segment and layer boundary starts a GOP, so with the same keyframes the decoded
    video can differ only inside the GOPs that hold a changed frame; `mp4_may_differ` lists those
    frames. A timing edit moves keyframes, and then the GOPs from the first moved one on may
    differ too. decode=True decodes both files and measures it (`mp4_differs`)."""
    a_dir, b_dir = Path(a_dir), Path(b_dir)
    for d in (a_dir, b_dir):
        c = d / "compose.json"
        if not c.is_file() or not json.loads(c.read_text()).get("rendered"):
            raise ValueError(f"{d}: no finished render there (no compose.json, or its QA stopped the render)")
        fails = json.loads(c.read_text())["qa"]["failures"]
        if fails:
            raise ValueError(f"{d}: that render failed QA, so it is not a usable ad: {fails[0]}")
    ca, cb = (json.loads((d / "compose.json").read_text()) for d in (a_dir, b_dir))
    ada, adb = (json.loads((d / "ad.json").read_text()) for d in (a_dir, b_dir))
    if ca["draft"] != cb["draft"]:
        raise ValueError("one render is a draft and the other is not; their frames are not comparable")
    out = {"frames": (ca["frames"], cb["frames"]), "same_sources": ca["sources"] == cb["sources"],
           "same_timeline": ca["timeline"] == cb["timeline"], "same_sound": ca["wav_sha256"] == cb["wav_sha256"],
           "same_mp4": ca["mp4_sha256"] == cb["mp4_sha256"], "same_keyframes": ca["keyframes"] == cb["keyframes"]}
    la, lb = ada.get("locked", []), adb.get("locked", [])
    from .ad import _get_path
    out["locked_changed"] = [p for p in sorted(set(la) | set(lb))
                             if json.dumps(_get_path(ada, p), sort_keys=True) != json.dumps(_get_path(adb, p), sort_keys=True)]
    out["unlocked"] = sorted(set(la) - set(lb))
    out["locked_violation"] = [p for p in out["locked_changed"] if p not in out["unlocked"]]
    out["layers_changed"] = sorted(k for k in set(ca["layers"]) | set(cb["layers"])
                                   if ca["layers"].get(k) != cb["layers"].get(k) or ada["layers"].get(k) != adb["layers"].get(k))
    out["ok"] = not out["locked_violation"]
    if ca["frames"] != cb["frames"] or not out["same_timeline"]:
        out["changed_frames"] = None
        out["note"] = "the timeline changed (a timing or gameplay edit), so frames are not compared one to one"
        return out
    changed = [i for i, (x, y) in enumerate(zip(ca["frame_sha256"], cb["frame_sha256"])) if x != y]
    out["changed_frames"] = _ranges(changed)
    predicted = [ca["layers"][k]["box"] for k in out["layers_changed"] if k in ca["layers"] and ca["layers"][k]["box"]]
    predicted += [cb["layers"][k]["box"] for k in out["layers_changed"] if k in cb["layers"] and cb["layers"][k]["box"]]
    out["predicted_box"] = _union(predicted)
    measured = None
    if changed:
        want = set(changed)
        pa, pb = Prepared(ada, ca["draft"]), Prepared(adb, cb["draft"])
        for (ta, fa), (tb, fb) in zip(pa.frames(want), pb.frames(want)):
            d = np.any(fa != fb, axis=2)
            ys, xs = np.nonzero(d)
            if len(xs):
                box = [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]
                measured = box if measured is None else _union([measured, box])
    out["measured_box"] = measured
    pb_ = out["predicted_box"]
    out["contained"] = measured is None or (pb_ is not None and measured[0] >= pb_[0] and measured[1] >= pb_[1]
                                            and measured[2] <= pb_[2] and measured[3] <= pb_[3])
    # Which decoded MP4 frames can differ: the GOPs holding a changed frame (same keyframes), or
    # everything from the first keyframe that moved.
    n = ca["frames"]
    if out["same_keyframes"]:
        ks = sorted(set(ca["keyframes"]) | {n})
        may = set()
        for a, b in zip(ks, ks[1:]):
            if any(a <= c < b for c in changed):
                may.update(range(a, b))
    else:
        first = min(set(ca["keyframes"]) ^ set(cb["keyframes"]) | set(changed or [n]))
        may = set(range(min(first, min(changed) if changed else first), n))
    out["mp4_may_differ"] = _ranges(sorted(may))
    if decode:
        da = read_frames(a_dir / "ad.mp4", (ada["output"]["w"], ada["output"]["h"]))
        db = read_frames(b_dir / "ad.mp4", (adb["output"]["w"], adb["output"]["h"]))
        differs = [i for i, (x, y) in enumerate(zip(da, db)) if not np.array_equal(x, y)]
        out["mp4_differs"] = _ranges(differs)
        out["mp4_local"] = set(differs) <= may
    out["ok"] = out["ok"] and out["contained"] and out.get("mp4_local", True)
    return out


def _ranges(idx: list[int]) -> list[list[int]]:
    out = []
    for i in idx:
        if out and i == out[-1][1] + 1:
            out[-1][1] = i
        else:
            out.append([i, i])
    return out
