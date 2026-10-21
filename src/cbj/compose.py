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
from .draw import (PURPLE, WHITE, blend, clamp01, cover, cutout, ease_in_out, ease_out_back, ease_out_cubic, fit_text,
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

def cell_homography(rec: Recording) -> np.ndarray | None:
    """The 3x3 map from a board cell (x, y) to recording pixels, fitted on the first frame's logged
    block positions (each block's transform sits on its pivot cell); None without a level or enough
    blocks. The camera is fixed during a recording, so one map serves every frame."""
    if rec.level is None or not rec.frames:
        return None
    pts = rec.frames[0].get("blocks") or []
    cells = [b.pivot for b in rec.level.blocks]
    rows = []
    for i, (cx, cy) in enumerate(cells):
        if 2 * i + 1 >= len(pts) or pts[2 * i] < 0:
            continue
        sx, sy = pts[2 * i], pts[2 * i + 1]
        rows.append([cx, cy, 1, 0, 0, 0, -sx * cx, -sx * cy, -sx])
        rows.append([0, 0, 0, cx, cy, 1, -sy * cx, -sy * cy, -sy])
    if len(rows) < 8:
        return None
    _, _, vt = np.linalg.svd(np.array(rows, dtype=np.float64))
    return vt[-1].reshape(3, 3)


def cell_quads(rec: Recording, which: str = "holes") -> list[list[tuple[float, float]]]:
    """The screen quads (recording pixels, 4 corners each) of the board's inactive cells (the walls)."""
    H = cell_homography(rec)
    if H is None or which != "holes":
        return []

    def proj(x, y):
        v = H @ np.array([x, y, 1.0])
        return float(v[0] / v[2]), float(v[1] / v[2])
    quads = []
    for x0, y0, x1, y1 in wall_rects(set(rec.level.inactive)):
        # one picture per rectangular wall (a 2x2 pillar is one object, not four), per cell otherwise
        quads.append([proj(x0 - 0.5, y1 + 0.5), proj(x1 + 0.5, y1 + 0.5), proj(x1 + 0.5, y0 - 0.5), proj(x0 - 0.5, y0 - 0.5)])
    return quads


def texture_for_multiply(img: Image.Image, target: float = 0.82, strength: float = 0.55) -> Image.Image:
    """A texture prepared for a multiply blend on a shaded brick: its mean brightness is raised to
    `target` (of white) and its darks are lifted (a multiply keeps black black, so `strength` is how
    much of the texture's darkening is kept: 0.55 turns black lines into mid-grey ones), so the
    brick keeps its lightness and its colour identity under the pattern (a crate texture made a
    blue block read as black, viewer review 2026-10-15)."""
    arr = np.asarray(img, dtype=np.float64)
    rgb, a = arr[..., :3], arr[..., 3:4]
    w = a / 255.0
    mean = float((rgb * w).sum() / max(1.0, 3 * w.sum())) / 255.0
    out = arr.copy()
    if 0 < mean < target:
        rgb = np.clip(rgb * (target / mean), 0, 255)
    out[..., :3] = 255 - (255 - rgb) * strength
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA")


def block_quads(rec: Recording, block_id: int, frame: int, shrink: float = 0.84) -> list[list[tuple[float, float]]]:
    """The screen quads (recording pixels) of one block's cells on a recorded frame: the block's
    logged transform position is mapped back to board cell coordinates through the inverse of the
    cell homography (so a lifted, mid-drag block lands where it is drawn), and each cell of its
    shape is projected forward, shrunk a little to stay on the brick's flat top. [] once the block
    has left or when the frame has no record of it. A texture drawn on these follows the block
    exactly, frame by frame (brief p.6 "use this object"; research note of 2026-10-15)."""
    H = cell_homography(rec)
    if H is None or rec.level is None or block_id >= len(rec.level.blocks) or frame >= len(rec.frames):
        return []
    pts = rec.frames[frame].get("blocks") or []
    if 2 * block_id + 1 >= len(pts) or pts[2 * block_id] < 0:
        return []
    sx, sy = pts[2 * block_id], pts[2 * block_id + 1]
    inv = np.linalg.inv(H)
    v = inv @ np.array([sx, sy, 1.0])
    cx, cy = float(v[0] / v[2]), float(v[1] / v[2])

    def proj(x, y):
        w = H @ np.array([x, y, 1.0])
        return float(w[0] / w[2]), float(w[1] / w[2])
    h = shrink / 2
    quads = []
    for ox, oy in rec.level.blocks[block_id].offsets:
        x, y = cx + ox, cy + oy
        quads.append([proj(x - h, y + h), proj(x + h, y + h), proj(x + h, y - h), proj(x - h, y - h)])
    return quads


def wall_rects(cells: set) -> list[tuple[int, int, int, int]]:
    """Connected groups of wall cells as (x0, y0, x1, y1) inclusive rectangles when a group fills
    its bounding box, else one rectangle per cell of that group."""
    left, out = set(cells), []
    while left:
        start = min(left)
        group, todo = {start}, [start]
        while todo:
            x, y = todo.pop()
            for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if n in left and n not in group:
                    group.add(n)
                    todo.append(n)
        left -= group
        xs, ys = [c[0] for c in group], [c[1] for c in group]
        x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
        if len(group) == (x1 - x0 + 1) * (y1 - y0 + 1):
            out.append((x0, y0, x1, y1))
        else:
            out += [(x, y, x, y) for x, y in sorted(group)]
    return sorted(out)


def _perspective_coeffs(dst, src):
    """PIL PERSPECTIVE coefficients mapping output points dst (4) to source points src (4)."""
    rows = []
    for (X, Y), (x, y) in zip(dst, src):
        rows.append([X, Y, 1, 0, 0, 0, -x * X, -x * Y])
        rows.append([0, 0, 0, X, Y, 1, -y * X, -y * Y])
    A = np.array(rows, dtype=np.float64)
    b = np.array([c for xy in src for c in xy], dtype=np.float64)
    return tuple(np.linalg.solve(A, b))


def draw_on_quad(frame: np.ndarray, img: Image.Image, quad: list[tuple[float, float]], mode: str = "normal"):
    """Warp an RGBA picture onto a screen quad (top-left, top-right, bottom-right, bottom-left) and
    blend it in place. mode "multiply" darkens the frame by the picture (a texture on a shaded
    brick keeps the brick's studs and light). Returns the changed box or None."""
    xs, ys = [p[0] for p in quad], [p[1] for p in quad]
    x0, y0 = int(np.floor(min(xs))), int(np.floor(min(ys)))
    x1, y1 = int(np.ceil(max(xs))) + 1, int(np.ceil(max(ys))) + 1
    fh, fw = frame.shape[:2]
    if x1 <= 0 or y1 <= 0 or x0 >= fw or y0 >= fh or x1 - x0 < 2 or y1 - y0 < 2:
        return None
    local = [(x - x0, y - y0) for x, y in quad]
    w, h = img.width, img.height
    coeffs = _perspective_coeffs(local, [(0, 0), (w, 0), (w, h), (0, h)])
    warped = img.convert("RGBA").transform((x1 - x0, y1 - y0), Image.Transform.PERSPECTIVE, coeffs, Image.Resampling.BICUBIC)
    if mode != "multiply":
        return blend(frame, warped, x0 + (x1 - x0) / 2, y0 + (y1 - y0) / 2, 1.0)
    cx0, cy0, cx1, cy1 = max(0, x0), max(0, y0), min(fw, x1), min(fh, y1)
    src = np.asarray(warped, dtype=np.uint16)[cy0 - y0:cy1 - y0, cx0 - x0:cx1 - x0]
    a = src[..., 3:4]
    region = frame[cy0:cy1, cx0:cx1].astype(np.uint32)
    # frame * (1 - a * (1 - rgb/255)): integer maths, exact and repeatable like draw.blend
    darken = a.astype(np.uint32) * (255 - src[..., :3].astype(np.uint32))  # 0..255*255
    out = region * (255 * 255 - darken) // (255 * 255)
    frame[cy0:cy1, cx0:cx1] = out.astype(np.uint8)
    return (cx0, cy0, cx1, cy1)


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


def draw_cursor(frame, st: dict, placer: Placer, size: int, speed: float, image: Image.Image | None,
                hotspot=(0.5, 0.5)):
    """The tap ring (or a hand image) at one frame. Animations run in recording frames, so in a
    0.5x replay they play at half speed with everything else. An image is placed so its hotspot
    (a fingertip, as fractions of its width and height) is on the touch point; it shrinks a little
    while pressed, and a small ripple marks each lift."""
    boxes = []
    ripple = st.get("released") and st["since"] < 8
    if st["alpha"] <= 0 and not ripple:
        return boxes
    x, y = placer.point(st["x"], st["y"])
    s = placer.fit["scale"] / 0.75  # the ring keeps its size relative to the board
    if image is not None:
        k = ease_out_cubic(st["since"] / 4) if st["down"] else 1.0
        img = scaled(image, s * ((1.08 - 0.14 * k) if st["down"] else 1.0))
        if ripple:
            q = st["since"] / 8
            boxes.append(blend(frame, ring_image(int(size * 0.6 * s * (1 + 0.8 * q)), 0.0, 0.8), x, y, 1 - q))
        cx, cy = x + img.width * (0.5 - hotspot[0]), y + img.height * (0.5 - hotspot[1])
        boxes.append(blend(frame, img, cx, cy, 1.0 if st["down"] else st["alpha"]))
        return [b for b in boxes if b]
    if st["down"]:
        k = ease_out_cubic(st["since"] / 4)
        scale = (1.25 - 0.25 * k) * s
        boxes.append(blend(frame, ring_image(int(size * scale), 0.28 + 0.22 * k), x, y, 1.0))
    else:
        boxes.append(blend(frame, ring_image(int(size * s), 0.28), x, y, st["alpha"]))
        if ripple:  # the release ripple
            k = st["since"] / 8
            boxes.append(blend(frame, ring_image(int(size * s * (1 + 0.6 * k)), 0.0, 0.8), x, y, 1 - k))
    return [b for b in boxes if b]


# ---------- text, tags, buttons ----------

def _colour(hex_or_none, default):
    if not hex_or_none:
        return default
    h = hex_or_none.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def layer_image(layer: dict, text: str, band: dict | None = None) -> Image.Image:
    band = band or BAND
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
        im = cutout(sprite(layer.get("image", "ContinueButtonEmpty.png")))  # a generated button on a plain background
        if layer.get("box"):  # a replacement button, fitted in the game button's box
            bw, bh = layer["box"]
            btn = scaled(im, min(bw / im.width, bh / im.height)).copy()
        else:
            btn = scaled(im, layer.get("scale", 0.9)).copy()
        label = text_image(text, int(84 * layer.get("scale", 0.9) / 0.9), shadow=False)
        btn.alpha_composite(label, ((btn.width - label.width) // 2, max(0, (btn.height - label.height) // 2 - 10)))
        return btn
    size = STYLES.get(layer.get("style", "title_xl"), 96)
    icon = layer.get("icon")
    icon_w = 126 if icon else 0
    style = {"fill": _colour(layer.get("fill"), WHITE), "stroke": _colour(layer.get("stroke"), PURPLE)}
    if layer.get("slot") == "top":
        # In the band: the largest one- or two-line size that fits between the safe top and the HUD.
        # The pop-in overshoots to about 1.04x, so fit with that room to spare.
        img = fit_text(text, size, int((band["max_w"] - icon_w) / 1.05), int((band["y1"] - band["y0"]) / 1.05),
                       **style)
    else:
        # Placed texts (the end card) fit the safe width too, in one or two lines.
        img = fit_text(text, size, int(BAND["max_w"] / 1.05), layer.get("max_h", 260), **style)
    if icon:
        ico = cutout(sprite(icon))
        ic = scaled(ico, 110 / max(ico.width, ico.height))  # inside 110x110
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

ORDER_Z = {"object": 0, "skin": 0, "vignette": 0, "cursor": 1, "image": 2, "button": 3, "text": 4, "tag": 5}


class _Zoomed:
    """A placer seen through a camera punch-in: points scale about the anchor."""

    def __init__(self, pl, z: float, ax: float, ay: float):
        self.pl, self.z, self.ax, self.ay = pl, z, ax, ay
        self.fit = {**pl.fit, "scale": pl.fit["scale"] * z}

    def point(self, x: float, y: float) -> tuple[float, float]:
        px, py = self.pl.point(x, y)
        return self.ax + (px - self.ax) * self.z, self.ay + (py - self.ay) * self.z


def zoom_frame(frame: np.ndarray, z: float, ax: float, ay: float) -> np.ndarray:
    """The frame seen `z` times closer, about (ax, ay)."""
    im = Image.fromarray(frame)
    k = 1.0 / z
    return np.array(im.transform(im.size, Image.AFFINE, (k, 0, ax - ax * k, 0, k, ay - ay * k),
                                 resample=Image.BICUBIC))  # a copy: layers are drawn into it


PLAYFIELD = (0, 217, 1080, 1574)  # the HUD and the board in a recorded frame (see formats.py)


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
        self.band = {**BAND, **ad.get("band", {})}  # a logo in a top corner narrows the caption band
        self._check_locked()
        self.layers = self._resolve_layers()
        try:
            self.events = audio_events(ad, self.recs, self.tl, self.total)
        except (ValueError, KeyError) as e:
            self.events = []
            self.qa["failures"].append(f"audio: {e}")
        self.draw_order = sorted(self.layers, key=lambda k: ORDER_Z[self.layers[k]["layer"]["type"]])
        self._placers, self._firsts = {}, {}
        self.camera = self._resolve_camera()

    def _resolve_camera(self) -> list[dict]:
        """Timed punch-ins (ad["camera"]): frames, zoom and the anchor on the canvas, the asked block
        (the one of its colour nearest the board's middle) at the window's middle frame. The zoom is
        capped so the HUD and the whole board stay in the frame."""
        out = []
        for c in self.ad.get("camera", []):
            f0, f1 = int(round(c["from_s"] * FPS)), int(round(c["to_s"] * FPS))
            f0, f1 = max(0, f0), min(self.total, f1)
            if f1 - f0 < 6:
                self.qa["warnings"].append(f"camera punch-in {c['from_s']}-{c['to_s']} s is too short or outside the ad")
                continue
            tm = (f0 + f1) // 2
            sid = next((k for k, (a, b) in self.tl.items() if a <= tm < b), None)
            seg = self.ad["segments"].get(sid) if sid else None
            if not seg or seg["kind"] not in ("clip", "hold"):
                self.qa["warnings"].append(f"camera punch-in {c['from_s']}-{c['to_s']} s is not on the gameplay")
                continue
            rec, pl = self.recs[seg["src"]], self.placer(seg["src"], seg["fit"])
            rf = source_frame(seg, tm - self.tl[sid][0]) if seg["kind"] == "clip" else seg["frame"]
            pos = (rec.frames[min(rf, rec.n - 1)].get("blocks") or [])
            pts = [(i, pos[2 * i], pos[2 * i + 1]) for i in range(len(pos) // 2) if pos[2 * i] >= 0]
            x0, y0, x1, y1 = (pl.point(PLAYFIELD[0], PLAYFIELD[1]) + pl.point(PLAYFIELD[2], PLAYFIELD[3]))
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            want = c.get("toward")
            if want and rec.level is not None:
                from .level import BlockColor
                slot = {"DarkGreen": "DARK_GREEN"}.get(want, want.upper())
                pts = [q for q in pts if rec.level.blocks[q[0]].color == BlockColor[slot]]
            if pts:
                cands = [pl.point(x, y) for _, x, y in pts]
                ax, ay = min(cands, key=lambda q: (q[0] - mx) ** 2 + (q[1] - my) ** 2)
            else:
                ax, ay = mx, my
                if want:
                    self.qa["warnings"].append(f"camera punch-in: no {want} block on screen then; it zooms on the board's middle")
            W, H = self.size
            caps = [c["zoom"]]
            for e, a in ((x0, ax), (y0, ay)):  # the left and top edges stay at or after 0
                if e < a:
                    caps.append(a / (a - e))
            for e, a, lim in ((x1, ax, W), (y1, ay, H)):  # the right and bottom edges stay inside
                if e > a:
                    caps.append((lim - a) / (e - a))
            z = max(1.0, min(caps))
            if z < c["zoom"] - 1e-6:
                self.qa["warnings"].append(f"camera punch-in capped at {z:.3f} so the HUD and the board stay in the frame")
            out.append({"f0": f0, "f1": f1, "zoom": round(z, 4), "anchor": [round(ax, 1), round(ay, 1)],
                        "toward": want})
        return out

    def zoom_at(self, t: int):
        """(z, ax, ay) of the camera at output frame t, or None: eased in over the first 30% of
        the window, held, eased back out over the last 30%."""
        for c in self.camera:
            if c["f0"] <= t < c["f1"]:
                n = c["f1"] - c["f0"]
                ramp = max(1, int(n * 0.3))
                k = t - c["f0"]
                e = 1.0 if ramp <= k < n - ramp else ease_in_out(min(k, n - 1 - k) / ramp)
                return 1.0 + (c["zoom"] - 1.0) * e, c["anchor"][0], c["anchor"][1]
        return None

    def _check_locked(self):
        """`locked` parts must match the digests written when the ad was made (brief p.3: elements
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
                    text = fill(layer["text"], recs[src].facts(layer.get("beat"), ad.get("colour_names")))
                except ValueError as e:
                    self.qa["failures"].append(f"layer {lid!r}: {e}")
                    continue
                self.qa["failures"] += [f"layer {lid!r}: {p}" for p in copy_problems(text)]
                entry["text"] = text
                entry["image"] = layer_image(layer, text, self.band)
                if layer.get("slot") == "top" and entry["image"].height > self.band["y1"] - self.band["y0"]:
                    self.qa["failures"].append(f"layer {lid!r}: too long for the text band even at the smallest size")
                elif layer.get("pos") and layer["type"] == "text" and not layer.get("safe_exempt"):
                    # a placed caption that wraps to two lines (custom copy) stays inside the safe area:
                    # it is moved up as far as it needs, and the ad says so
                    safe = SAFE[ad["output"].get("safe", "social")]
                    bottom = ad["output"]["h"] - safe["bottom"]
                    over = int(layer["pos"][1] + entry["image"].height * 1.05 / 2 - bottom) + 2  # pop-in overshoot
                    if over > 0:
                        layer["pos"] = [layer["pos"][0], layer["pos"][1] - over]
                        self.qa["warnings"].append(f"layer {lid!r}: moved up {over} px to stay inside the safe area "
                                                   f"(its words wrap to two lines)")
                if layer["type"] == "text":
                    need = reading_s(text)  # time to read it
                    if (f1 - f0) / FPS < need - 1e-6:
                        # an entrance or exit the user moved is theirs to choose: said, not refused
                        (self.qa["warnings"] if layer.get("asked_timing") else self.qa["failures"]).append(
                            f"layer {lid!r}: on screen {(f1 - f0) / FPS:.2f} s; its words need {need:.1f} s")
            elif layer["type"] == "image":
                im = cutout(sprite(layer["image"]))  # a picture on a plain background becomes a sticker
                if layer.get("box"):  # fit inside a box (an uploaded picture of any size)
                    bw, bh = layer["box"]
                    entry["image"] = scaled(im, min(bw / im.width, bh / im.height))
                else:
                    entry["image"] = scaled(im, layer.get("scale", 1.0))
            elif layer["type"] == "vignette":
                entry["image"] = vignette_image(size, layer.get("color", [255, 40, 40]))
                sid = layer["start"].get("seg")
                seg = ad["segments"][sid]
                pulses = [to_output(seg, tl[sid][0], f) for f in recs[seg["src"]].event(layer.get("pulse_on", ""))]
                entry["pulses"] = sorted(p for p in pulses if p is not None)
            elif layer["type"] == "object":
                # a picture on the board's cells (the walls): the cells are fitted to the screen from the
                # recorded block positions (an exact homography: the board is a plane under a fixed camera)
                entry["image"] = sprite(layer["image"])
                entry["quads"] = {sid: cell_quads(r, layer.get("cells", "holes")) for sid, r in recs.items()}
            elif layer["type"] == "skin":
                # a texture on one block: drawn on the block's cells on every gameplay frame, following the
                # recorded block position (the game itself is untouched; the block's shape and moves stay)
                entry["image"] = texture_for_multiply(sprite(layer["image"]).convert("RGBA"))
            elif layer["type"] == "cursor":
                img = layer.get("image")
                if img == "builtin:hand":
                    from .draw import hand_image
                    entry["image"] = hand_image(int(layer.get("size", 96) * 1.9))
                elif img:
                    im = cutout(sprite(img))
                    entry["image"] = scaled(im, layer.get("size", 96) * 1.9 / max(im.width, im.height))
                else:
                    entry["image"] = None
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
        if seg.get("gradient"):  # a card in the brief's colours instead of the game's brick art
            top, bottom = (np.array(_colour(c, WHITE), dtype=np.float64) for c in seg["gradient"])
            k = np.linspace(0.0, 1.0, self.size[1])[:, None]
            col = np.round(top * (1 - k) + bottom * k).astype(np.uint8)
            base = np.repeat(col[:, None, :], self.size[0], axis=1).copy()
        else:
            base = cover(sprite(seg.get("background", "StartBACKGROUND.png")), self.size)
        th = seg.get("thumb")
        if th:
            f = next(read_frames(self.recs[th["src"]].video, self.size, th["frame"], 1)).copy()
            drawn = self._board_layers(f, th["src"], th["frame"])  # the walls' picture, a block's texture: on the thumb too
            y0, y1 = th.get("crop_y", [0, f.shape[0]])
            sc = th.get("scale", 0.5)
            im = scaled(Image.fromarray(f[y0:y1]).convert("RGBA"), sc)
            framed = Image.new("RGBA", (im.width + 16, im.height + 16), (*WHITE, 255))
            framed.alpha_composite(im, (8, 8))
            pos = th.get("pos", [540, 960])
            blend(base, framed, *pos)
            ox, oy = int(round(pos[0] - framed.width / 2)) + 8, int(round(pos[1] - framed.height / 2)) + 8
            for lid, b in drawn:  # where it landed on the card, so the frame diff stays inside the layer's boxes
                self.layers[lid]["boxes"].append([int(ox + b[0] * sc) - 2, int(oy + (b[1] - y0) * sc) - 2,
                                                  int(math.ceil(ox + b[2] * sc)) + 2, int(math.ceil(oy + (b[3] - y0) * sc)) + 2])
        return base

    def _board_layers(self, frame: np.ndarray, src: str, fi: int) -> list[tuple[str, tuple]]:
        """The object (walls) and skin (one block) layers drawn on a native recording frame `fi` of `src`, for the
        end card's board picture: a cliffhanger's unsolved board must show the asked picture there too (the viewer
        of E2, 2026-10-19: "the obstacle suddenly changing look at the end feels like a glitch"). Returns the boxes."""
        out = []
        for lid in self.draw_order:
            e = self.layers[lid]
            lay = e["layer"]
            if lay["type"] not in ("object", "skin") or e.get("image") is None:
                continue
            pl = self.placer(src, {"scale": 1.0, "x": 0, "y": 0})
            if lay["type"] == "object":
                quads = e["quads"].get(src, [])
                for quad in quads:
                    b = draw_on_quad(frame, e["image"], [pl.point(x, y) for x, y in quad])
                    if b:
                        out.append((lid, b))
            else:
                for quad in block_quads(self.recs[src], lay["block"], fi):
                    b = draw_on_quad(frame, e["image"], [pl.point(x, y) for x, y in quad], mode=lay.get("blend", "multiply"))
                    if b:
                        out.append((lid, b))
        return out

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
                cam = self.zoom_at(t) if seg["kind"] != "card" else None
                frame = zoom_frame(base, *cam) if cam else base.copy()
                for lid in self.draw_order:
                    self._draw(lid, frame, t, sid, seg, k, W, H)
                yield t, np.ascontiguousarray(frame)

    def _draw(self, lid, frame, t, sid, seg, k, W, H):
        e = self.layers[lid]
        lay = e["layer"]
        if lay["type"] == "object":
            if seg["kind"] != "card" and sid in lay.get("segments", []) and e.get("image") is not None:
                pl = self.placer(seg["src"], seg["fit"])
                cam = self.zoom_at(t)
                pl = _Zoomed(pl, *cam) if cam else pl
                for quad in e["quads"].get(seg["src"], []):
                    b = draw_on_quad(frame, e["image"], [pl.point(x, y) for x, y in quad])
                    if b:
                        e["boxes"].append(b)
            return
        if lay["type"] == "skin":
            if seg["kind"] != "card" and sid in lay.get("segments", []) and e.get("image") is not None:
                pl = self.placer(seg["src"], seg["fit"])
                cam = self.zoom_at(t)
                pl = _Zoomed(pl, *cam) if cam else pl
                for quad in block_quads(self.recs[seg["src"]], lay["block"], source_frame(seg, k)):
                    b = draw_on_quad(frame, e["image"], [pl.point(x, y) for x, y in quad], mode=lay.get("blend", "multiply"))
                    if b:
                        e["boxes"].append(b)
            return
        if lay["type"] == "cursor":
            if seg["kind"] == "clip" and sid in lay.get("segments", []):
                st = e["tracks"][seg["src"]][source_frame(seg, k)]
                hot = lay.get("hotspot") or ((0.36, 0.05) if lay.get("image") == "builtin:hand" else (0.5, 0.5))
                pl = self.placer(seg["src"], seg["fit"])
                cam = self.zoom_at(t)
                e["boxes"] += draw_cursor(frame, st, _Zoomed(pl, *cam) if cam else pl, lay.get("size", 96),
                                          seg.get("speed", 1), e["image"], hot)
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
        b = blend(frame, scaled(e["image"], sc), *lay.get("pos", [self.band["cx"], self.band["cy"]]), op)
        if b:
            e["boxes"].append(b)


def patch_plan(ad: dict, prep: "Prepared", prev_dir: Path) -> dict | None:
    """When `ad` differs from the finished ad in prev_dir only in layers that keep their frame
    windows (a caption's words or colours, a picture swapped in its slot, a layer added or removed
    inside existing boundaries), the GOPs of the approved MP4 that hold no changed frame can be
    copied byte for byte and only the others rendered and encoded again. Returns the plan, or None
    when the edit is not of that kind (then the ad is rendered in full)."""
    try:
        prev = json.loads((prev_dir / "compose.json").read_text())
        prev_ad = json.loads((prev_dir / "ad.json").read_text())
    except (OSError, ValueError):
        return None
    if not prev.get("rendered") or prev.get("draft") or not (prev_dir / "ad.mp4").is_file():
        return None
    if prev.get("frames") != prep.total or prev.get("keyframes") != prep.keyframes():
        return None
    for key in ("order", "segments", "sources", "output", "camera"):
        if prev_ad.get(key) != ad.get(key):
            return None
    if prev_ad["layers"].get("cursor") != ad["layers"].get("cursor"):
        return None  # the cursor runs through every gameplay frame
    changed = sorted(lid for lid in set(prev_ad["layers"]) | set(ad["layers"])
                     if prev_ad["layers"].get(lid) != ad["layers"].get(lid))
    spans = []
    thumb_segs = [sid for sid in ad["order"] if ad["segments"][sid].get("thumb")]
    for lid in changed:
        if lid in prep.layers:
            spans.append((prep.layers[lid]["f0"], prep.layers[lid]["f1"]))
        if lid in prev.get("layers", {}):
            spans.append(tuple(prev["layers"][lid]["frames"]))
        if (ad["layers"].get(lid) or prev_ad["layers"].get(lid) or {}).get("type") in ("object", "skin"):
            for sid in thumb_segs:  # the end card's board picture carries the walls' picture and a block's texture
                spans.append(tuple(prep.tl[sid]))  # (card_base): its GOP is drawn again, never copied (E2, 2026-10-19)
    ks = sorted(set(prev["keyframes"]) | {0, prep.total})
    gops = [(ks[i], ks[i + 1]) for i in range(len(ks) - 1) if ks[i] < ks[i + 1]]
    dirty = [(a, b) for a, b in gops if any(a < s1 and s0 < b for s0, s1 in spans)]
    return {"gops": gops, "dirty": dirty, "changed_layers": changed, "prev": prev, "prev_dir": prev_dir}


def _runs(gops: list, dirty: set) -> list[tuple[int, int, bool]]:
    """Contiguous runs of GOPs, each (start, end, dirty)."""
    out = []
    for a, b in gops:
        d = (a, b) in dirty
        if out and out[-1][2] == d and out[-1][1] == a:
            out[-1] = (out[-1][0], b, d)
        else:
            out.append((a, b, d))
    return out


def _patched_video(ad: dict, prep: "Prepared", plan: dict, out: Path, draft: bool) -> tuple[dict, np.ndarray | None]:
    """The video of a patched render: dirty runs drawn and encoded again (the same encoder, the same
    keyframes), clean runs cut from the approved MP4 without decoding, all joined without
    re-encoding. Returns {frame index: hash} for the rendered frames and the poster if frame 0 was drawn."""
    runs = _runs(plan["gops"], set(plan["dirty"]))
    prev_mp4 = plan["prev_dir"] / "ad.mp4"
    ks = set(plan["prev"]["keyframes"])
    hashes, poster, parts = {}, None, []
    tmp = out / "_patch"
    tmp.mkdir(exist_ok=True)
    for i, (a, b, dirty) in enumerate(runs):
        piece = tmp / f"{i:03d}.mp4"
        if dirty:
            writer = FrameWriter(piece, prep.size, FPS, ad["output"].get("crf", 16), draft=draft,
                                 keyframes=[k - a for k in ks if a <= k < b])
            try:
                for t, frame in prep.frames(want=set(range(a, b))):
                    hashes[t] = hashlib.sha256(frame.data).hexdigest()[:32]
                    if t == 0:
                        poster = frame.copy()
                    writer.write(frame)
                writer.close()
            except BaseException:
                writer.proc.kill()
                raise
        else:
            # -ss just past the keyframe's own time: the copy starts on that keyframe, never the one before
            r = subprocess.run([ffmpeg_bin(), "-v", "error", "-y", "-ss", f"{(a + 0.25) / FPS:.6f}", "-i", str(prev_mp4),
                                "-frames:v", str(b - a), "-c:v", "copy", "-an", "-avoid_negative_ts", "make_zero",
                                str(piece)], capture_output=True, text=True)
            if r.returncode != 0:
                raise ValueError(f"could not copy frames {a}-{b} of the approved ad: {r.stderr.strip()[-200:]}")
        parts.append(piece)
    lst = tmp / "list.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in parts))
    r = subprocess.run([ffmpeg_bin(), "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy",
                        "-movflags", "+faststart", str(out / "video.mp4")], capture_output=True, text=True)
    if r.returncode != 0:
        raise ValueError(f"could not join the patched video: {r.stderr.strip()[-200:]}")
    n = _frame_count(out / "video.mp4")
    if n != prep.total:
        raise ValueError(f"the patched video has {n} frames, not {prep.total}")
    for p_ in parts:
        p_.unlink(missing_ok=True)
    lst.unlink(missing_ok=True)
    tmp.rmdir()
    return hashes, poster


def _frame_count(video: Path) -> int:
    r = subprocess.run([ffmpeg_bin().replace("ffmpeg", "ffprobe"), "-v", "error", "-count_packets", "-select_streams", "v:0",
                        "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", str(video)], capture_output=True, text=True)
    try:
        return int(r.stdout.strip().split(",")[0])
    except ValueError:
        return -1


def _runs_cover(f0: int, f1: int, runs: list[tuple[int, int]]) -> bool:
    """Whether the half-open frame runs cover every frame of [f0, f1)."""
    t = f0
    for a, b in sorted(runs):
        if a > t:
            break
        if b > t:
            t = b
        if t >= f1:
            return True
    return t >= f1


def render(ad: dict, out_dir: str | Path, draft: bool = False, patch_from: str | Path | None = None) -> dict:
    """Render an ad. patch_from: the folder of the finished ad this one edits; when the edit only
    changes layers inside the same frame windows, the approved MP4's untouched GOPs are copied byte
    for byte and only the changed ones are rendered (the result decodes identically to a full render,
    which the encoder's bit-exact settings make checkable)."""
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
    patched = None
    plan = patch_plan(ad, prep, Path(patch_from)) if patch_from and not draft else None
    hashes, poster = [], None
    if plan is not None:
        try:
            got, poster = _patched_video(ad, prep, plan, out, draft)
            prev_h = plan["prev"]["frame_sha256"]
            hashes = [got.get(t, prev_h[t]) for t in range(total)]
            if poster is None and (plan["prev_dir"] / "poster.png").is_file():
                poster = np.asarray(Image.open(plan["prev_dir"] / "poster.png").convert("RGB")).copy()
            copied = sum(b - a for a, b in plan["gops"] if (a, b) not in set(plan["dirty"]))
            patched = {"from": str(plan["prev_dir"]), "changed_layers": plan["changed_layers"], "gops": len(plan["gops"]),
                       "gops_rendered": len(plan["dirty"]), "frames_rendered": total - copied, "frames_copied": copied}
        except Exception as e:  # anything odd: the full render is always right
            patched = {"from": str(plan["prev_dir"]), "note": f"not patched ({str(e)[:160]}); rendered in full"}
            for stale in ("video.mp4",):
                (out / stale).unlink(missing_ok=True)
            hashes, poster = [], None
            plan = None
    if plan is None:
        writer = FrameWriter(out / "video.mp4", prep.size, FPS, ad["output"].get("crf", 16), draft=draft,
                             keyframes=prep.keyframes())
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
    effects = render_track(prep.events, total / FPS)
    music = (ad.get("audio") or {}).get("music")
    track = mix_music(effects, music) if music else effects
    write_wav(track, out / "audio.wav")
    audio_from = None
    if plan is not None and patched.get("frames_copied") and (plan["prev_dir"] / "ad.mp4").is_file() and \
            plan["prev"].get("wav_sha256") == hashlib.sha256((out / "audio.wav").read_bytes()).hexdigest():
        audio_from = plan["prev_dir"] / "ad.mp4"  # the same mix: the approved audio stream, byte for byte
        patched["audio_copied"] = True
    mux(out / "video.mp4", out / "audio.wav", out / "ad.mp4", audio_from=audio_from)
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
        **({"patched": patched} if patched else {}),
        "audio_events": prep.events,
        **({"camera": prep.camera} if prep.camera else {}),
        "frame_sha256": hashes,  # first 128 bits of each composited RGB frame's SHA-256
        "wav_sha256": hashlib.sha256((out / "audio.wav").read_bytes()).hexdigest(),
        # the stems apart, so an edit report can say which one changed
        "sfx_sha256": hashlib.sha256(np.round(effects * 32767).astype("<i2").tobytes()).hexdigest(),
        "music": ({"file": Path(music["file"]).name, "sha256": hashlib.sha256(Path(music["file"]).read_bytes()).hexdigest(),
                   "gain": music["gain"], "fade_out_s": music["fade_out_s"]} if music else None),
        "mp4_sha256": hashlib.sha256(((out / "ad.mp4") if (out / "ad.mp4").exists()
                                      else (out / "ad.FAILED.mp4")).read_bytes()).hexdigest(),
        "draft": draft,
        "qa": qa,
    }
    if plan is not None and patched and patched.get("frames_copied"):
        # a layer with frames outside the rendered GOPs has a partial box here: for those frames the
        # approved render's box is exact (its bytes were copied), so the two are joined; a layer that
        # lies whole inside the rendered GOPs keeps its new box (it may have been drawn differently as
        # a side effect, e.g. a wider caption band once a logo left, 2026-10-15)
        rendered = [(a, b) for a, b in plan["dirty"]]
        for lid, info in result["layers"].items():
            if lid in plan["changed_layers"]:
                continue
            f0, f1 = info["frames"]
            # every frame of the layer must lie in a rendered run, not only its first and last (2026-10-18:
            # the cursor spans the whole ad; a hook edit and an end-card edit rendered its first and last
            # GOPs, the play in between was copied, and its box shrank to the rendered frames' spots, a
            # false "placed differently" in the edit report)
            inside = _runs_cover(f0, max(f0 + 1, f1), rendered)
            if not inside:
                info["box"] = _union([b for b in (plan["prev"]["layers"].get(lid, {}).get("box"), info["box"]) if b])
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


def music_seconds(data: bytes, ext: str) -> float | None:
    """The length of an uploaded sound file in seconds, or None if ffprobe finds no audio in it."""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=ext) as f:
        f.write(data)
        f.flush()
        import shutil
        probe = shutil.which("ffprobe")
        if not probe:
            raise ValueError("ffprobe not found on PATH")
        r = subprocess.run([probe, "-v", "error", "-select_streams", "a:0",
                            "-show_entries", "stream=codec_type:format=duration", "-of", "json", f.name],
                           capture_output=True, text=True)
    try:
        j = json.loads(r.stdout)
        if not j.get("streams"):
            return None
        return float(j["format"]["duration"])
    except (ValueError, KeyError, TypeError):
        return None


def load_music(path: str | Path, seconds: float) -> np.ndarray:
    """A sound file as a mono float track at the ad's rate, exactly `seconds` long: trimmed, or
    looped when shorter."""
    r = subprocess.run([ffmpeg_bin(), "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(RATE), "-f", "f32le", "-"],
                       capture_output=True)
    if r.returncode != 0:
        raise ValueError(f"the music {Path(path).name} could not be read: {r.stderr.decode()[:200]}")
    x = np.frombuffer(r.stdout, dtype="<f4").astype(np.float64)
    n = int(round(seconds * RATE)) + 1
    if len(x) == 0:
        raise ValueError(f"the music {Path(path).name} is empty")
    if len(x) < n:
        x = np.tile(x, n // len(x) + 1)
    return x[:n]


def mix_music(effects: np.ndarray, music: dict) -> np.ndarray:
    """The effects with the music under them: the music at its gain, a 50 ms fade-in and a fade-out
    over the last `fade_out_s`; the sum limited to -1 dBFS like the effects alone."""
    m = load_music(music["file"], (len(effects) - 1) / RATE) * music["gain"]
    fi, fo = int(0.05 * RATE), int(music["fade_out_s"] * RATE)
    m[:fi] *= np.linspace(0, 1, fi)
    if fo:
        m[-fo:] *= np.linspace(1, 0, fo)
    track = effects + m
    peak = np.abs(track).max()
    limit = 10 ** (-1 / 20)
    if peak > limit:
        track *= limit / peak
    return track


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
        # the user may move it later on purpose; then the poster simply has no hook, and it is said
        (qa["warnings"] if layers["hook"]["layer"].get("asked_timing") else qa["failures"]).append(
            "the hook does not start on frame 0 (the poster)")
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

def diff(a_dir: str | Path, b_dir: str | Path, decode: bool = False, boxes: bool = True) -> dict:
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
    if ca.get("camera") != cb.get("camera"):
        # a camera move changes whole frames inside its window: those are the camera's, not a layer's
        cam = {f for c in (ca.get("camera") or []) + (cb.get("camera") or []) for f in range(c["f0"], c["f1"])}
        out["camera_frames"] = _ranges(sorted(cam & set(changed)))
        changed = [i for i in changed if i not in cam]
    predicted = [ca["layers"][k]["box"] for k in out["layers_changed"] if k in ca["layers"] and ca["layers"][k]["box"]]
    predicted += [cb["layers"][k]["box"] for k in out["layers_changed"] if k in cb["layers"] and cb["layers"][k]["box"]]
    out["predicted_box"] = _union(predicted)
    measured = None
    if changed and boxes:  # boxes=False: frames only (an edit that re-filmed the gameplay)
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
