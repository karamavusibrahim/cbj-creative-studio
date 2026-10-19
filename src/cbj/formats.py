"""Other aspect ratios from the 9:16 master (1:1, 4:5, 16:9), without redesigning the ad.

The master is composed for 1080x1920. Another format crops the master to the area where anything
is shown (every caption and picture box, and the HUD and board in every framing the gameplay
parts use), scales that area to fit the new frame, and fills the sides with a blurred, darkened
copy of the frame (side extensions). Nothing moves inside the area, so every board state, caption
and picture keeps its place relative to the others, and the board is never cut.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter

from .video import ffmpeg_bin

W, H = 1080, 1920
SIZES = {"1:1": (1080, 1080), "4:5": (1080, 1350), "16:9": (1920, 1080)}
# The HUD and the board in the recorded frame (y), whatever fit a part uses: the compositor's FIT
# puts the HUD from y 481 and the board to y 1498 at scale 0.75 from y 318.
PLAYFIELD = (0, 217, 1080, 1574)


def window(compose: dict) -> list[int]:
    """The part of the master frame that shows anything: [x0, y0, x1, y1]."""
    boxes = [lay["box"] for lay in compose.get("layers", {}).values() if lay.get("box")]
    for part in compose.get("timeline", {}).values():
        fit = part.get("fit")
        if fit:
            s, x, y = fit["scale"], fit["x"], fit["y"]
            boxes.append([x + PLAYFIELD[0] * s, y + PLAYFIELD[1] * s, x + PLAYFIELD[2] * s, y + PLAYFIELD[3] * s])
    if not boxes:
        return [0, 0, W, H]
    x0 = max(0, min(b[0] for b in boxes)); y0 = max(0, min(b[1] for b in boxes))
    x1 = min(W, max(b[2] for b in boxes)); y1 = min(H, max(b[3] for b in boxes))
    even = lambda v: int(v) // 2 * 2
    return [even(x0), even(y0), even(x1 + 1), even(y1 + 1)]


def plan(compose: dict, fmt: str) -> dict:
    tw, th = SIZES[fmt]
    x0, y0, x1, y1 = window(compose)
    w, h = x1 - x0, y1 - y0
    s = min(tw / w, th / h)
    cw, ch = int(w * s) // 2 * 2, int(h * s) // 2 * 2
    return {"format": fmt, "size": [tw, th], "window": [x0, y0, x1, y1], "scale": round(s, 4),
            "content": [(tw - cw) // 2, (th - ch) // 2, cw, ch]}


def derive(ad_dir: Path, fmt: str) -> dict:
    """Writes ad_<fmt>.mp4 and poster_<fmt>.png next to the master; returns the plan, with the
    file names (also kept in compose.json under "format")."""
    ad_dir = Path(ad_dir)
    compose = json.loads((ad_dir / "compose.json").read_text())
    p = plan(compose, fmt)
    tw, th = p["size"]
    x0, y0, x1, y1 = p["window"]
    cx, cy, cw, ch = p["content"]
    tag = fmt.replace(":", "x")
    out = ad_dir / f"ad_{tag}.mp4"
    graph = (f"[0:v]split=2[a][b];"
             f"[a]scale={tw}:{th}:force_original_aspect_ratio=increase,crop={tw}:{th},boxblur=30:3,"
             f"eq=brightness=-0.06[bg];"
             f"[b]crop={x1 - x0}:{y1 - y0}:{x0}:{y0},scale={cw}:{ch}:flags=lanczos[fg];"
             f"[bg][fg]overlay={cx}:{cy},format=yuv420p[v]")
    r = subprocess.run([ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(ad_dir / "ad.mp4"),
                        "-filter_complex", graph, "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-preset", "medium",
                        "-crf", "16", "-c:a", "copy", "-movflags", "+faststart", str(out)], capture_output=True, text=True)
    if r.returncode != 0:
        raise ValueError(f"the {fmt} version could not be made: {r.stderr[:300]}")
    poster = ad_dir / "poster.png"
    if poster.is_file():
        im = Image.open(poster).convert("RGB")
        bg = im.resize((tw, int(H * tw / W)) if tw / W > th / H else (int(W * th / H), th))
        bg = bg.crop(((bg.width - tw) // 2, (bg.height - th) // 2, (bg.width - tw) // 2 + tw, (bg.height - th) // 2 + th))
        bg = ImageEnhance.Brightness(bg.filter(ImageFilter.GaussianBlur(30))).enhance(0.94)
        bg.paste(im.crop((x0, y0, x1, y1)).resize((cw, ch), Image.LANCZOS), (cx, cy))
        bg.save(ad_dir / f"poster_{tag}.png")
    p["file"], p["poster"] = out.name, f"poster_{tag}.png"
    compose["format"] = p
    (ad_dir / "compose.json").write_text(json.dumps(compose, indent=1))
    return p
