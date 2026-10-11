"""Drawing for the compositor: text in the game's style, sprites from the Unity project, easing,
and exact alpha blending onto video frames.

Fonts and sprites are read at run time from the provided Unity project (../CBJ by default) and are
never copied into this repo: the game's font (Tobi, Rodrigotypo) is "all rights reserved" and
licensed to Rollic for the game. Without the project, an open fallback font is used.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

REPO = Path(__file__).resolve().parents[2]
PROJECT = Path(os.environ.get("CBJ_PROJECT", REPO.parent / "CBJ"))
GAME_FONT = "Assets/Fonts/Tobi Greek Cyrillic Regular.otf"
FALLBACK_FONTS = ("Assets/TextMesh Pro/Fonts/LiberationSans.ttf",
                  "/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf",
                  "/System/Library/Fonts/Supplemental/Arial Bold.ttf")
SPRITES = "Assets/Sprites/UI"

PURPLE = (84, 22, 140)  # the outline colour of the game's own titles
WHITE = (255, 255, 255)
YELLOW = (255, 226, 60)


@lru_cache(maxsize=None)
def font_path() -> str:
    for rel in (GAME_FONT, *FALLBACK_FONTS):
        p = Path(rel) if rel.startswith("/") else PROJECT / rel
        if p.is_file():
            return str(p)
    raise ValueError(f"no font found (looked in {PROJECT} and the system fonts)")


@lru_cache(maxsize=64)
def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(font_path(), size)


@lru_cache(maxsize=None)
def sprite(name: str) -> Image.Image:
    """A sprite from the game's UI folder, or an image file path, as RGBA."""
    p = Path(name)
    if not p.is_file():
        p = PROJECT / SPRITES / name
    if not p.is_file():
        raise ValueError(f"image {name!r} not found (looked for a file and in {PROJECT / SPRITES})")
    return Image.open(p).convert("RGBA")


def wrap(text: str, size: int, max_width: int) -> list[str]:
    """Lines for a text. Explicit newlines are kept; words split on plain spaces only, so a
    non-breaking space keeps a fact like "dark green" on one line. A paragraph that needs two
    lines breaks where the two halves are most even, not greedily."""
    f = font(size)
    lines = []
    for para in text.split("\n"):
        words = [w for w in para.split(" ") if w]
        if not words:
            lines.append("")
            continue
        if f.getlength(" ".join(words)) <= max_width or len(words) == 1:
            lines.append(" ".join(words))
            continue
        # Two lines if any split fits: the one with the shortest longer line.
        best = None
        for k in range(1, len(words)):
            a, b = " ".join(words[:k]), " ".join(words[k:])
            wa, wb = f.getlength(a), f.getlength(b)
            if wa <= max_width and wb <= max_width and (best is None or max(wa, wb) < best[0]):
                best = (max(wa, wb), [a, b])
        if best:
            lines += best[1]
            continue
        line = ""  # more than two lines: greedy
        for word in words:
            trial = f"{line} {word}".strip()
            if not line or f.getlength(trial) <= max_width:
                line = trial
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines


def text_image(text: str, size: int, fill=WHITE, stroke=PURPLE, stroke_width: int | None = None,
               max_width: int = 960, shadow: bool = True, line_gap: float = 1.08) -> Image.Image:
    """Text in the game's title style (fill, thick outline, soft drop shadow) as a tight RGBA image."""
    sw = max(2, size // 9) if stroke_width is None else stroke_width
    f = font(size)
    lines = wrap(text, size, max_width - 2 * sw)
    asc, desc = f.getmetrics()
    lh = int((asc + desc) * line_gap)
    w = int(max(f.getlength(ln) for ln in lines)) + 2 * sw + 8
    h = lh * len(lines) + 2 * sw + 8
    pad = size // 6 if shadow else 0
    img = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    if shadow:
        sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(sh)
        for i, ln in enumerate(lines):
            d.text((img.width // 2, pad + sw + 4 + i * lh + size // 14), ln, font=f, anchor="ma",
                   fill=(0, 0, 0, 110), stroke_width=sw, stroke_fill=(0, 0, 0, 110))
        img = Image.alpha_composite(img, sh.filter(ImageFilter.GaussianBlur(size / 18)))
    d = ImageDraw.Draw(img)
    for i, ln in enumerate(lines):
        d.text((img.width // 2, pad + sw + 4 + i * lh), ln, font=f, anchor="ma", fill=fill,
               stroke_width=sw, stroke_fill=stroke)
    return img


def fit_text(text: str, max_size: int, max_w: int, max_h: int, min_size: int = 48, **kw) -> Image.Image:
    """The largest text image (one or two lines, from max_size down) that fits max_w x max_h."""
    for size in range(max_size, min_size - 1, -2):
        img = text_image(text, size, max_width=max_w, line_gap=1.0, **kw)
        lines = len(wrap(text, size, max_w - 2 * max(2, size // 9)))
        if lines <= 2 and img.width <= max_w and img.height <= max_h:
            return img
    return text_image(text, min_size, max_width=max_w, line_gap=1.0, **kw)


# ---------- easing ----------

def clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def ease_out_back(x: float, s: float = 1.7) -> float:
    x = clamp01(x) - 1
    return 1 + (s + 1) * x ** 3 + s * x ** 2


def ease_out_cubic(x: float) -> float:
    return 1 - (1 - clamp01(x)) ** 3


def ease_in_out(x: float) -> float:
    x = clamp01(x)
    return 3 * x * x - 2 * x * x * x


# ---------- blending ----------

def scaled(img: Image.Image, scale: float) -> Image.Image:
    if abs(scale - 1) < 1e-6:
        return img
    w, h = max(1, round(img.width * scale)), max(1, round(img.height * scale))
    return img.resize((w, h), Image.LANCZOS)


def blend(frame: np.ndarray, img: Image.Image, cx: float, cy: float, opacity: float = 1.0):
    """Alpha-blend an RGBA image onto an RGB frame (in place), centred at (cx, cy). Integer maths, so
    the result is exact and repeatable. Returns the changed box (x0, y0, x1, y1) or None."""
    if opacity <= 0:
        return None
    h, w = frame.shape[:2]
    x0, y0 = int(round(cx - img.width / 2)), int(round(cy - img.height / 2))
    x1, y1 = x0 + img.width, y0 + img.height
    cx0, cy0, cx1, cy1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
    if cx0 >= cx1 or cy0 >= cy1:
        return None
    src = np.asarray(img, dtype=np.uint16)[cy0 - y0:cy1 - y0, cx0 - x0:cx1 - x0]
    a = src[..., 3:4]
    if opacity < 1:
        a = (a * int(round(opacity * 255)) + 127) // 255
    dst = frame[cy0:cy1, cx0:cx1].astype(np.uint16)
    frame[cy0:cy1, cx0:cx1] = ((src[..., :3] * a + dst * (255 - a) + 127) // 255).astype(np.uint8)
    return (cx0, cy0, cx1, cy1)


def cover(img: Image.Image, size: tuple[int, int]) -> np.ndarray:
    """Scale and centre-crop an image to fill size (w, h); returns an RGB frame."""
    w, h = size
    s = max(w / img.width, h / img.height)
    r = img.convert("RGB").resize((round(img.width * s), round(img.height * s)), Image.LANCZOS)
    x0, y0 = (r.width - w) // 2, (r.height - h) // 2
    return np.array(r.crop((x0, y0, x0 + w, y0 + h)))
