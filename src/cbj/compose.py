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
                 layer_window, resolve_time, seg_frames, source_frame, timeline, to_output)
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


def anim_state(layer: dict, t: int, f0: int, f1: int) -> tuple[float, float]:
    """(scale, opacity) of a layer at output frame t."""
    anim = layer.get("anim", "pop")
    scale, alpha = 1.0, 1.0
    if anim in ("pop",) and t - f0 < 6:
        k = (t - f0) / 6
        scale = 0.6 + 0.4 * ease_out_back(k)
        alpha = clamp01((t - f0 + 1) / 3)
    if anim in ("pop", "pop_out") and f1 - t <= 4:
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

def render(ad: dict, out_dir: str | Path, draft: bool = False) -> dict:
    check_ad(ad)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    size = (ad["output"]["w"], ad["output"]["h"])
    W, H = size
    recs = {sid: Recording.load(s["recording"]) for sid, s in ad["sources"].items()}
    qa = {"failures": [], "warnings": []}
    for sid, s in ad["sources"].items():
        if s.get("sha256") and s["sha256"] != recs[sid].sha():
            qa["failures"].append(f"source {sid!r}: gameplay.mp4 changed since ad.json was made (hash differs)")
    tl = timeline(ad)
    total = max(e for _, e in tl.values())

    # Resolve every layer: its frames, its text (facts filled in), its image.
    layers = {}
    for lid, layer in ad["layers"].items():
        if layer.get("enabled") is False:
            continue
        try:
            f0, f1 = layer_window(ad, recs, lid) if layer["type"] != "cursor" else (0, total)
        except (ValueError, KeyError) as e:
            qa["failures"].append(f"layer {lid!r}: {e}")
            continue
        entry = {"layer": layer, "f0": f0, "f1": f1, "boxes": []}
        if layer["type"] in TEXT_TYPES:
            seg = layer.get("seg") or layer.get("start", {}).get("seg")
            src = ad["segments"].get(seg, {}).get("src") or next(iter(recs))
            try:
                text = fill(layer["text"], recs[src].facts(layer.get("beat")))
            except ValueError as e:
                qa["failures"].append(f"layer {lid!r}: {e}")
                continue
            qa["failures"] += [f"layer {lid!r}: {p}" for p in copy_problems(text)]
            entry["text"] = text
            entry["image"] = layer_image(layer, text)
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

    # Problems found so far (a claim the ad rules forbid, an anchor that cannot resolve, a sound at a
    # moment that is not in the ad) stop here, before any frame is drawn.
    try:
        events = audio_events(ad, recs, tl, total)
    except (ValueError, KeyError) as e:
        events = []
        qa["failures"].append(f"audio: {e}")
    if qa["failures"]:
        result = {"rendered": False, "frames": total, "duration_s": round(total / FPS, 3), "draft": draft,
                  "timeline": {}, "layers": {}, "qa": qa}
        (out / "compose.json").write_text(json.dumps(result, indent=1))
        return result

    # Placers (one per source and fit), cards.
    placers, firsts = {}, {}
    for sid, rec in recs.items():
        firsts[sid] = next(read_frames(rec.video, size, 0, 1)).copy()

    def placer(src, fit):
        key = (src, json.dumps(fit, sort_keys=True))
        if key not in placers:
            placers[key] = Placer(firsts[src], fit, size, draft)
        return placers[key]

    def card_base(seg) -> np.ndarray:
        base = cover(sprite(seg.get("background", "StartBACKGROUND.png")), size)
        th = seg.get("thumb")
        if th:
            f = next(read_frames(recs[th["src"]].video, size, th["frame"], 1))
            y0, y1 = th.get("crop_y", [0, f.shape[0]])
            im = Image.fromarray(f[y0:y1]).convert("RGBA")
            im = scaled(im, th.get("scale", 0.5))
            frame_img = Image.new("RGBA", (im.width + 16, im.height + 16), (*WHITE, 255))
            frame_img.alpha_composite(im, (8, 8))
            blend(base, frame_img, *th.get("pos", [540, 960]))
        return base

    order_z = {"vignette": 0, "cursor": 1, "image": 2, "button": 3, "text": 4, "tag": 5}
    draw_order = sorted(layers, key=lambda k: order_z[layers[k]["layer"]["type"]])
    writer = FrameWriter(out / "video.mp4", size, FPS, ad["output"].get("crf", 16), draft=draft)
    hashes = []
    poster = None
    try:
        for sid in ad["order"]:
            seg = ad["segments"][sid]
            s0, s1 = tl[sid]
            if seg["kind"] == "card":
                base = card_base(seg)
                source = (base for _ in range(s1 - s0))
            elif seg["kind"] == "hold":
                still = next(read_frames(recs[seg["src"]].video, size, seg["frame"], 1)).copy()
                pl = placer(seg["src"], seg["fit"])
                placed = pl.place(still)
                source = (placed for _ in range(s1 - s0))
            else:
                pl = placer(seg["src"], seg["fit"])
                reader = read_frames(recs[seg["src"]].video, size, seg["from"], seg["to"] - seg["from"])
                source = _clip_frames(reader, seg, pl, s1 - s0)
            for k, base in enumerate(source):
                t = s0 + k
                frame = base.copy()
                for lid in draw_order:
                    e = layers[lid]
                    lay = e["layer"]
                    if lay["type"] == "cursor":
                        if seg["kind"] == "clip" and sid in lay.get("segments", []):
                            src_f = source_frame(seg, k)
                            st = e["tracks"][seg["src"]][src_f]
                            e["boxes"] += draw_cursor(frame, st, placer(seg["src"], seg["fit"]), lay.get("size", 96),
                                                      seg.get("speed", 1), e["image"])
                        continue
                    if not e["f0"] <= t < e["f1"]:
                        continue
                    if lay["type"] == "vignette":
                        a = 0.0
                        pf = lay.get("pulse_frames", 10)
                        for p in e["pulses"]:
                            if p <= t < p + pf:
                                a = max(a, math.sin(math.pi * (t - p) / pf))
                        if a > 0:
                            b = blend(frame, e["image"], W / 2, H / 2, a * lay.get("max_alpha", 0.35))
                            if b:
                                e["boxes"].append(b)
                        continue
                    if e.get("image") is None:
                        continue
                    sc, op = anim_state(lay, t, e["f0"], e["f1"])
                    img = scaled(e["image"], sc)
                    cx, cy = lay.get("pos", [BAND["cx"], BAND["cy"]])
                    b = blend(frame, img, cx, cy, op)
                    if b:
                        e["boxes"].append(b)
                frame = np.ascontiguousarray(frame)
                hashes.append(hashlib.sha256(frame.data).hexdigest()[:32])
                if t == 0:
                    poster = frame.copy()
                writer.write(frame)
        writer.close()
    except BaseException:
        writer.proc.kill()
        raise

    # Sound.
    track = render_track(events, total / FPS)
    write_wav(track, out / "audio.wav")
    mux(out / "video.mp4", out / "audio.wav", out / "ad.mp4")
    (out / "video.mp4").unlink()
    if poster is not None:
        Image.fromarray(poster).save(out / "poster.png")

    # QA.
    _qa(ad, layers, tl, total, track, hashes, qa)
    (out / "ad.json").write_text(json.dumps(ad, indent=2))
    result = {
        "rendered": True,
        "tool": {"cbj": CBJ_VERSION, "pillow": PIL.__version__, "numpy": np.__version__, "ffmpeg": _ffmpeg_version()},
        "ad_sha256": hashlib.sha256(json.dumps(ad, sort_keys=True).encode()).hexdigest(),
        "sources": {sid: {"recording": s["recording"], "sha256": recs[sid].sha()} for sid, s in ad["sources"].items()},
        "frames": total, "fps": FPS, "duration_s": round(total / FPS, 3),
        "timeline": {sid: {"frames": list(tl[sid]), "kind": ad["segments"][sid]["kind"],
                           "fit": ad["segments"][sid].get("fit")} for sid in ad["order"]},
        "layers": {lid: {"type": e["layer"]["type"], "frames": [e["f0"], e["f1"]], "text": e.get("text"),
                         "box": _union(e["boxes"])} for lid, e in layers.items()},
        "audio_events": events,
        "frame_sha256": hashes,  # first 128 bits of each composited RGB frame's SHA-256
        "wav_sha256": hashlib.sha256((out / "audio.wav").read_bytes()).hexdigest(),
        "mp4_sha256": hashlib.sha256((out / "ad.mp4").read_bytes()).hexdigest(),
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
                pitch = {n - 3: 1.0, n - 2: 1.12, n - 1: 1.26}.get(i, 1.0)
            elif pitch == "ticktock":
                pitch = 1.0 if i % 2 == 0 else 0.84
            e = {"name": name, "sound": ev["sound"], "t": round(o / FPS, 4), "gain": ev.get("gain", 0.5)}
            if pitch != 1.0:
                e["pitch"] = pitch
            if o < total:
                out.append(e)
    return sorted(out, key=lambda e: (e["t"], e["name"]))


def _union(boxes):
    if not boxes:
        return None
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]


def _ffmpeg_version() -> str:
    try:
        return subprocess.run([ffmpeg_bin(), "-version"], capture_output=True, text=True).stdout.split("\n")[0]
    except (OSError, ValueError):
        return "unknown"


def _qa(ad, layers, tl, total, track, hashes, qa):
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
        if lay["type"] == "text":
            if lay.get("slot") == "top" and e["image"].height > BAND["y1"] - BAND["y0"]:
                qa["failures"].append(f"layer {lid!r}: too long for the text band even at the smallest size")
            if e["f1"] - e["f0"] < 24:
                qa["failures"].append(f"layer {lid!r}: on screen {(e['f1'] - e['f0']) / FPS:.2f} s; at least 0.8 s")
            if lay.get("slot") == "top":
                tops.append((e["f0"], e["f1"], lid))
        if box and not (box[0] >= area[0] and box[1] >= area[1] and box[2] <= area[2] and box[3] <= area[3]):
            msg = f"layer {lid!r}: drawn at {box}, outside the {ad['output'].get('safe', 'social')} safe area {list(area)}"
            # Inside a full-size replay the tag sits over the board on purpose; text and buttons must be safe.
            (qa["warnings"] if lay["type"] == "tag" else qa["failures"]).append(msg)
    tops.sort()
    for (a0, a1, a), (b0, b1, b) in zip(tops, tops[1:]):
        if b0 < a1:
            qa["failures"].append(f"layers {a!r} and {b!r} overlap in the text band ({b0 / FPS:.2f}-{a1 / FPS:.2f} s)")
    if "hook" in layers and layers["hook"]["f0"] != 0:
        qa["failures"].append("the hook does not start on frame 0 (the poster)")
    if "hook" not in layers:
        qa["warnings"].append("no hook layer")
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
