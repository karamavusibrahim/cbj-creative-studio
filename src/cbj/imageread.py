"""Reading a reference picture for the image-guided workflow (core requirement 3, rules I3, I7, I14; 2026-10-17).

The request is read first, then the picture, for the request (the owner, 2026-10-17, as the video path does):
0. the reading plan (reading_plan): the planner's text model reads the request and the picture's format facts only
   (size, orientation, aspect, format: never its name or content) and names the focus (style, board, asset, modify),
   the questions the request needs answered ("how many blocks: count the board, never a caption"), what to ignore and
   what the request fixes itself; an empty or invalid plan falls back to the word table (plan_from_words). The plan
   narrows what is APPLIED (imageplan.reconcile), never what is read.
1. the reader (image_reader): Opus through the Claude Code CLI with its Read tool (ClaudeImageReader over
   llm.ClaudeCliVision, unchanged) when CBJ_IMAGE_READER=claude[:model[:effort]], or when it is unset and the planner is
   Claude; else, and whenever Opus fails, the video path's chain (reference.video_client: Gemini 3.5 Flash-Lite, then
   NVIDIA build). Which reader read the picture, its model and its seconds are recorded.
2. Opus reads the whole picture ONCE (read_one): the general reading, the same every time (GENERAL_ASK: what it shows,
   whether it is Color Block Jam and its HUD, the board in outline and in the generator's shapes, how many rooms its
   walls make, its blocks, colours, pieces, symmetry and box, the look, the captions word for word, what the game does
   not have) with the plan's questions on top as the request's priorities, in one strict JSON answer checked in code
   (validate_general) and asked once more with the problems quoted. The fallback reads the same ask, then the board on
   its own by the video path's machinery unchanged (reference.read_board, the picture handed to it as a one-second clip
   of that frame: still_clip), and counts the blocks twice on a crop of the board's box where no caption is in view
   (count_on_crop) (read_multi).
3. the code's measures beside the model, whichever reader: the palette (reference.palette), the background at the
   picture's margins, the caption's fill and outline inside its box, and on the board's crop reference.measure_board:
   the block mask against its mirrors decides the symmetry, the share of cells under blocks is the fill (not used when
   it is far from what the blocks read can cover), the colour clusters give a read colour its measured shade. Where
   the reader and a measure disagree it is written down (disagreements) and the measure is used.
The board is counted on the board, never from a caption (pic_x's caption says "12 blocks" over 14): a number a caption
claims is kept as `caption_claims` and set against the count. A failed reading is recorded with its reason and the
creative is planned from the words alone (rule I3); nothing is guessed.
"""

from __future__ import annotations

import base64
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from . import reference as R

# The board's outlines the reading names, and what each is in the generator's words (imageplan maps them).
OUTLINES = ("rectangle", "plus", "hourglass", "ring", "columns", "other")

GENERAL_SCHEMA = {
    "what_it_shows": '"one line"',
    "kind": '"game screenshot|photo|illustration|logo|character|pattern|other"',
    "is_color_block_jam": ("true or false (Color Block Jam: toy-brick blocks with studs on a grid board, coloured gates on "
                           "the board's rim, the HUD's round \"Level n\" badge and \"Time mm:ss\" bar)"),
    "hud": ('{"shown": true or false (a level badge or a clock is on screen), "level": "the number on the level badge, '
            'or null", "clock": "the clock as shown, MM:SS, or null"}'),
    "board": ('{"shown": true or false (a grid board of coloured blocks), "outline": "' + "|".join(OUTLINES) + '" (the '
              'board\'s outline: rectangle; plus = the four corners cut away; hourglass = a wide top and bottom joined by a '
              'narrow neck; ring = a hole in the middle; columns = wall columns between lanes), "shape": "' + "|".join(R.BOARD_SHAPES)
              + '" (' + "; ".join(f"{k}: {v}" for k, v in R.BOARD_SHAPES.items()) + '), "rooms": <how many '
              'separate areas the wall lines or wall cells inside the board split it into; 1 when none>, "centre_wall": '
              'true or false (a wall cell or wall block in the middle of the board), "wall_cells": <wall cells inside the '
              'board, 0 when none>, "columns": <cells across>, "rows": <cells down>, "blocks": <the coloured blocks, '
              'counted one by one>, "colours": ["each distinct block colour once, named as seen (pink and purple, teal '
              'and green, coral and red are different names)"], "colours_hex": ["#RRGGBB of each colour in \'colours\', in the '
              'same order: the blocks\' lit top face as it looks in this picture, never the game\'s usual colour"], '
              '"pieces": "small (1-2 cells) | long (bars of 3-5) | big '
              '(2x2 and larger) | varied | mixed", "symmetric": true or false (the pieces\' shapes and places mirror '
              'left-right or top-bottom), "box": {"x": <left edge 0-1 of the width>, "y": <top edge 0-1 of the height>, '
              '"w": <0-1>, "h": <0-1>}}'),
    "look": ('{"background_top": "#RRGGBB", "background_bottom": "#RRGGBB", "board_colour": "#RRGGBB (the board\'s cells)", '
             '"caption_fill": "#RRGGBB or null (the caption letters\' inside)", "caption_outline": "#RRGGBB or null (their '
             'outline)", "accent": "#RRGGBB or null (the picture\'s brightest accent as it looks here: a neon trim, a glow, '
             'a highlight, the colour caption letters would take to belong to this look; null when there is none)", '
             '"accent_box": {"x": <0-1>, "y": <0-1>, "w": <0-1>, "h": <0-1>} or null (a box around where the accent shows), '
             '"style": "a few words", "mood": "a few words"}'),
    "captions_seen": '["every caption over the picture, its words exactly as shown, letter for letter; [] when none"]',
    "caption_box": ('{"x": <0-1>, "y": <0-1>, "w": <0-1>, "h": <0-1>} (the first caption\'s box, around its letters), or '
                    'null when there is no caption'),
    "not_in_game": ('["anything shown that Color Block Jam does not have, one by one: booster buttons, power-ups, '
                    'characters, ice, keys, chains, bubbles, bombs, coins on the board; [] when none"]'),
    "idea": '"one line: what an ad for Color Block Jam could take from this picture (a look, a board idea, a mood)"',
    "answers": '[{"question": "...", "answer": "..."}] (one per priority question below, in order; [] when there is none)',
}
GENERAL_ASK = ("This picture was attached to a request for a new Color Block Jam video ad (a puzzle game: coloured "
               "toy-brick blocks are dragged out of a grid board through gates of their colour, against a countdown "
               "clock). Read the whole picture once and describe it exactly; count what can be counted, never guess "
               "from a caption's words. Return ONLY JSON:\n{\n"
               + ",\n".join(f'  "{k}": {v}' for k, v in GENERAL_SCHEMA.items()) + "\n}")
BLOCK_COUNT_ASK = ('Count the coloured blocks on this game board one by one (each separate piece once; not the gates on the '
                   'rim, not the walls, not the caption\'s words). Return ONLY JSON: {"blocks": <n>, "pieces": '
                   '["one entry per block: its colour and shape, such as \\"red bar of 3\\""]}')
SIZE_REREADS = 2  # Opus's size asked this many more times on the board's crop: the median of three
COUNT_READS = 2  # the blocks counted this many times on the board's crop, beside the board read: the median of three
STILL_CLIP_S = 1.0  # the picture as a one-second clip for read_board (it reads the frame at 0.3 s)
MARGIN_BAND = 0.04  # the picture's top and bottom bands (this share of its height) are its background
CAPTION_MIN_SHARE = 0.05  # a colour under this share of the caption box is an edge, not the letters' fill or outline
FILL_DOUBT = 0.3  # a measured fill this far from what the blocks read can cover is not used (board_of_reading)
PAIR_MAX = 150.0  # a measured cluster stands for a read colour only this close (redmean): pic_z's cyan glow read as "blue"
CAPTION_CLAIM = re.compile(r"\b(\d{1,2})\s+(blocks?|pieces?|moves?|seconds?|secs?|s)\b", re.I)


def image_part(path: Path) -> dict:
    """The picture as the tool's data-URL part (reference.analyse's form; Gemini's client makes it inline_data)."""
    ext = Path(path).suffix.lower()[1:]
    mime = {"jpg": "jpeg"}.get(ext, ext)
    return {"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{base64.b64encode(Path(path).read_bytes()).decode()}"}}


def still_clip(picture: Path, out: Path, seconds: float = STILL_CLIP_S) -> Path:
    """The picture as a short clip of that one frame (H.264, 4:4:4, near-lossless), so the video path's board reading
    (reference.read_board, which takes a still from a clip) reads the picture itself at its own resolution."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise ValueError("ffmpeg is not installed, so the board cannot be read on the picture")
    r = subprocess.run([ffmpeg, "-v", "error", "-y", "-loop", "1", "-framerate", "10", "-i", str(picture), "-t", f"{seconds:g}",
                        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv444p", "-c:v", "libx264", "-preset", "veryfast",
                        "-crf", "8", str(out)], capture_output=True, text=True)
    if r.returncode != 0 or not Path(out).is_file():
        raise ValueError(f"the picture could not be turned into a still clip ({r.stderr.strip()[:120]})")
    return Path(out)


def _hex(rgb) -> str:
    return "#%02X%02X%02X" % tuple(int(round(c)) for c in rgb[:3])


def margins(path: Path) -> dict:
    """The picture's background measured in code: the median colour of its top and bottom bands (MARGIN_BAND of the
    height, the full width) and of its left and right edges at mid-height (where the made poster's background is read,
    audit.poster_background). {top, bottom, sides, width, height}."""
    import numpy as np
    from PIL import Image
    with Image.open(path) as im:
        a = np.asarray(im.convert("RGB")).astype(float)
    h, w = a.shape[:2]
    band = max(1, int(h * MARGIN_BAND))
    top = np.median(a[:band].reshape(-1, 3), 0)
    bottom = np.median(a[h - band:].reshape(-1, 3), 0)
    edge = max(1, int(w * 0.03))
    rows = slice(int(h * 0.38), int(h * 0.62))
    sides = np.median(np.concatenate([a[rows, :edge].reshape(-1, 3), a[rows, w - edge:].reshape(-1, 3)]), 0)
    return {"top": _hex(top), "bottom": _hex(bottom), "sides": _hex(sides), "width": w, "height": h}


def caption_colours(path: Path, box: dict | None, background: str | None = None) -> dict | None:
    """The caption's fill and outline measured inside its box: the box's colours (median cut, 4), less the one nearest
    the background behind it; of the other two biggest, the lighter-or-more-saturated larger one is the fill, the other
    the outline. {fill, outline, box} or None when there is no usable box."""
    from PIL import Image
    if not isinstance(box, dict):
        return None
    with Image.open(path) as im:
        W, H = im.size
        b = R.board_box(box, W, H)
        if not b or b["w"] * b["h"] < 0.002:
            return None
        crop = im.convert("RGB").crop((int(b["x"] * W), int(b["y"] * H), int((b["x"] + b["w"]) * W), int((b["y"] + b["h"]) * H)))
    crop.thumbnail((240, 240))
    q = crop.quantize(colors=5, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()
    counts = sorted(q.getcolors(), reverse=True)
    total = sum(n for n, _ in counts) or 1
    cols = [(n, tuple(pal[3 * i:3 * i + 3])) for n, i in counts]
    bg = R._rgb(background) if background else cols[0][1]
    cols.sort(key=lambda c: sum((x - y) ** 2 for x, y in zip(c[1], bg)))
    cols = [c for c in cols[1:] if c[0] / total >= CAPTION_MIN_SHARE]  # less the background showing between the letters
    if len(cols) < 2:
        return None
    # the letters' inside is the lightest of the rest, their outline the darkest (round 1: pic_z's neon glow, a grey
    # teal, outnumbered the yellow letters, and the two biggest were taken)
    from .imageref import luminance
    fill = max(cols, key=lambda c: luminance(_hex(c[1])))
    outline = min((c for c in cols if c is not fill), key=lambda c: luminance(_hex(c[1])))
    return {"fill": _hex(fill[1]), "outline": _hex(outline[1]), "box": b}


def _ints(x) -> int | None:
    try:
        n = int(round(float(x)))
    except (TypeError, ValueError):
        return None
    return n if 0 <= n <= 200 else None


def _median(xs: list) -> int | None:
    xs = sorted(x for x in xs if isinstance(x, int))
    return xs[(len(xs) - 1) // 2] if xs else None


def pair_colours(names: list[str], clusters: list[dict]) -> list[dict]:
    """Each read colour name with the measured cluster it stands for (the assignment that pairs the most names within
    PAIR_MAX at the least total distance, as reference.confirmed_names chooses): [{name, rgb, measured}]
    where rgb is the cluster's measured colour when paired, else the name's own shade (videoref.colour_rgb)."""
    import itertools
    from .videoref import _distance, colour_name, colour_rgb
    plain = list(dict.fromkeys(colour_name(n) for n in names if colour_name(n)))[:7]
    cl = sorted(clusters or [], key=lambda c: -c.get("cells", 0))[:8]
    pairs: dict[str, tuple] = {}
    named = [n for n in plain if colour_rgb(n)]
    if named and cl:
        best = None
        k = min(len(named), len(cl))
        for ns in itertools.permutations(named, k) if len(named) > len(cl) else [tuple(named)]:
            for cs in itertools.permutations(range(len(cl)), k):
                ok = [(n, i) for n, i in zip(ns, cs) if _distance(colour_rgb(n), cl[i]["rgb"]) <= PAIR_MAX]
                key = (-len(ok), sum(_distance(colour_rgb(n), cl[i]["rgb"]) for n, i in ok))
                if best is None or key < best[0]:
                    best = (key, ok)
        pairs = {n: tuple(cl[i]["rgb"]) for n, i in best[1]}
    out = []
    for n in plain:
        rgb = pairs.get(n) or colour_rgb(n)
        out.append({"name": n, "rgb": list(rgb) if rgb else None, "measured": n in pairs})
    return out


def count_on_crop(client, path: Path, box: dict | None, reads: int = COUNT_READS) -> list[int | None]:
    """The blocks counted on a crop of the board's box, where no caption can be seen (rule I7: pic_x's "12 blocks"
    caption pulled the whole-picture counts to 12 over a board of 14), `reads` times; [] when there is no box."""
    if not box:
        return []
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        crop = Path(tmp) / "board.jpg"
        try:
            R.crop_to_box(path, crop, box)
        except Exception:
            return []
        for _ in range(reads):
            try:
                out.append(_ints(R._ask_json(client, BLOCK_COUNT_ASK, image_part(crop), None).get("blocks")))
            except Exception:
                out.append(None)
    return out


def board_of_reading(general: dict, rec: dict | None, count_read: list | int | None, claimed: bool = False) -> dict | None:
    """The board as the reading gives it, one record for the plan: the board read (read_board) for the size (the median
    of four reads), the shape word, the colours (with their measured colours), the pieces, the walls, the symmetry and
    the fill (both measured in code on the crop); the whole-picture read for the outline, the rooms and the wall in the
    middle; the blocks as the median of the three counts. None when no board was read."""
    g = (general or {}).get("board") if isinstance((general or {}).get("board"), dict) else {}
    b = (rec or {}).get("board") if isinstance((rec or {}).get("board"), dict) else {}
    if not b and not g.get("shown"):
        return None
    measured = (rec or {}).get("measured") or {}
    names = [str(c) for c in (b.get("colours") or g.get("colours") or []) if str(c).strip()]
    counted = [str(c) for c in (rec or {}).get("colours_counted") or [] if str(c).strip()]
    n_col = (rec or {}).get("colour_count")
    if counted and n_col and len(counted) == n_col:
        # the colours the reader counted on their own (COLOUR_COUNT_ASK): the board question names more shades than there
        # are colours (pic_w: seven names for five colours, 2026-10-17)
        names, source = counted, "counted"
    else:
        from .videoref import board_colours
        cm = board_colours(names, n_col, counted)  # the closest names merged down to the count
        names, source = [m["read"] for m in cm["map"]], "board read"
    colours = pair_colours(names, measured.get("clusters") or [])
    # the board read and the counts on the board's crop decide; the whole picture's count (where a caption is in view)
    # only when there is nothing else
    crop_counts = [c for c in (count_read if isinstance(count_read, list) else [count_read]) if c is not None]
    counts = [_ints(b.get("blocks"))] + crop_counts
    if not claimed or not [c for c in counts if c is not None]:
        # the whole picture's count joins when no caption in view claims a number of blocks (round 1: pic_w's crop
        # counts took gates for blocks, 10 and 10 over 7; the board read and the whole picture both said 7)
        counts.append(_ints(g.get("blocks")))
    cols, rows = _ints(b.get("columns")) or _ints(g.get("columns")), _ints(b.get("rows")) or _ints(g.get("rows"))
    occ = b.get("occupancy") if isinstance(b.get("occupancy"), (int, float)) else None
    blocks = _median(counts)
    pieces_w = str(b.get("pieces") or g.get("pieces") or "").strip().lower().split(" ")[0].strip("(,;") or None
    fill_doubt = None
    if occ is not None and blocks and cols and rows:
        from .generate import AVG_CELLS
        # at most 0.9: a full board's estimate past its cells is no evidence against a measured 73 % (round 2: pic_x's 14
        # pieces read "varied" estimated 120 %)
        est = min(0.9, blocks * AVG_CELLS.get(pieces_w or "mixed", 2.3) / (cols * rows))
        if abs(occ - est) > FILL_DOUBT:
            # the code's block mask took a glow, a dark floor or a cut-away corner for blocks (pic_z's neon edges, pic_y's
            # plus outline): the measure is kept beside, never used
            fill_doubt = f"measured {occ:.0%}, but {blocks} {pieces_w or 'mixed'} pieces on {cols}x{rows} cover about {min(est, 1):.0%}"
            occ = None
    shape = str(b.get("shape") or "").strip().lower().replace("-", "_").replace(" ", "_") or None
    outline = str(g.get("outline") or "").strip().lower() or None
    # wall cells count only as far as both reads see them (round 1, 2026-10-17: the board read saw 2 walls in pic_x's
    # empty floor cells, the whole-picture read none)
    walls = [w for w in (_ints(b.get("wall_cells")), _ints(g.get("wall_cells"))) if w is not None]
    sym = b.get("symmetric") if isinstance(b.get("symmetric"), bool) else g.get("symmetric") if isinstance(g.get("symmetric"), bool) else None
    pieces = pieces_w
    first = b.get("size_first") if isinstance(b.get("size_first"), list) else [cols, rows]
    sreads = [x for x in [first] + list((rec or {}).get("size_reads") or []) if isinstance(x, list) and all(x)]
    spread = max(max(x[i] for x in sreads) - min(x[i] for x in sreads) for i in (0, 1)) if sreads else None
    return {"size_reads": sreads, "size_spread": spread,"columns": cols, "rows": rows, "shape_read": shape, "outline": outline if outline in OUTLINES else None,
            "rooms": _ints(g.get("rooms")), "centre_wall": bool(g.get("centre_wall")) if isinstance(g.get("centre_wall"), bool) else None,
            "wall_cells": min(walls) if walls else None, "wall_cells_reads": walls, "blocks": blocks, "blocks_reads": counts,
            "blocks_whole_picture": _ints(g.get("blocks")),
            "colours": colours, "colours_source": source, "colour_count": n_col or len(colours) or None,
            "pieces": pieces, "symmetric": sym, "symmetric_source": b.get("symmetric_source") or ("model" if sym is not None else None),
            "mirror": [measured.get("mirror_lr"), measured.get("mirror_tb")] if measured else None,
            "occupancy": occ, "occupancy_measured": b.get("occupancy"), "fill_doubt": fill_doubt,
            "obstacles": [str(o)[:80] for o in b.get("obstacles") or [] if str(o).strip()] if isinstance(b.get("obstacles"), list) else [],
            "gates_sides": _ints(b.get("gates_sides"))}


def caption_claims(captions: list[str]) -> list[dict]:
    """Numbers the captions claim ("12 blocks. 45 seconds."): evidence of the idea, never a fact about the board."""
    out = []
    for c in captions or []:
        for m in CAPTION_CLAIM.finditer(str(c)):
            unit = m.group(2).lower()
            what = "blocks" if unit.startswith(("block", "piece")) else "moves" if unit.startswith("move") else "seconds"
            out.append({"caption": str(c), "n": int(m.group(1)), "what": what})
    return out


def hud_of(general: dict) -> dict:
    """The HUD as read: {shown, level (int or None), clock (MM:SS or None)}."""
    h = (general or {}).get("hud") if isinstance((general or {}).get("hud"), dict) else {}
    level = _ints(re.sub(r"[^\d]", "", str(h.get("level") or ""))) if re.search(r"\d", str(h.get("level") or "")) else None
    clock = str(h.get("clock") or "").strip() or None
    clock = clock if clock and re.fullmatch(r"\d{1,2}:\d{2}", clock) else None
    shown = h.get("shown") if isinstance(h.get("shown"), bool) else bool(level or clock)
    return {"shown": bool(shown or level or clock), "level": level, "clock": clock}


# ---------- the reader (2026-10-17, the owner: Opus reads the picture; Gemini, then NVIDIA, when it cannot) ----------

class ClaudeImageReader:
    """Opus (or another Claude model) reading the picture through the Claude Code CLI with its Read tool
    (llm.ClaudeCliVision, unchanged), with the readers' interface: describe(ask, part, path), last_model, reader
    "claude", errors. A part with no file behind it (reference.read_board's crops pass none) is written to a
    temporary file first, so the CLI can read it."""

    reader = "claude"

    def __init__(self, model: str = "opus", effort: str = "low"):
        from .llm import ClaudeCliVision
        self.vision = ClaudeCliVision(model, effort)
        self.model, self.effort = model, effort
        self.last_model = None
        self.errors: list[str] = []

    def describe(self, ask: str, part: dict, path: Path | None = None) -> str:
        if path is None or Path(path).suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
            url = (part.get("image_url") or {}).get("url", "")
            m = re.match(r"data:image/(\w+);base64,(.*)$", url, re.S)
            if not m:
                raise ValueError("the Claude reader reads pictures only")
            tmp = Path(tempfile.mkdtemp(prefix="cbj_img_"))
            path = tmp / f"picture.{'jpg' if m.group(1) == 'jpeg' else m.group(1)}"
            path.write_bytes(base64.b64decode(m.group(2)))
        try:
            text = self.vision.describe(ask, {"type": "image_url"}, Path(path))
        except Exception as e:
            self.errors.append(f"claude-cli/{self.model}: {str(e)[:200]}")
            raise
        self.last_model = self.vision.last_model
        return text


def reader_setting() -> str:
    """CBJ_IMAGE_READER (claude[:model[:effort]], gemini or nvidia); empty: Claude when the planner is Claude."""
    from .planner import load_env
    load_env()
    return (os.environ.get("CBJ_IMAGE_READER") or "").strip().lower()


def image_reader():
    """The picture's reader: Opus through the Claude CLI when CBJ_IMAGE_READER says claude, or says nothing and the
    planner is Claude (llm.is_claude); else the video path's chain (reference.video_client: Gemini 3.5 Flash-Lite, then
    NVIDIA build), or NVIDIA alone for CBJ_IMAGE_READER=nvidia."""
    from . import llm
    s = reader_setting()
    if s.startswith("claude") or (not s and llm.is_claude()):
        model, effort = llm._claude_parts(s if s.startswith("claude") else "claude:opus")
        return ClaudeImageReader(model, effort)
    if s == "nvidia":
        return R.nvidia_video_client()
    return R.video_client()


# ---------- the reading plan: the request read first (2026-10-17, the owner; as reference.reading_plan for a video) ----------

IMAGE_FOCI = ("style", "board", "asset", "modify")
PLAN_LEVELS = ("none", "targeted", "full")
FOCUS_QUESTIONS = {
    "style": ["the background's colour at the top and at the bottom of the picture",
              "the captions' letter colour and outline colour", "the look in a few words"],
    "board": ["the board's outline and shape, and how many rooms its walls make", "how many columns and rows of cells",
              "how many blocks are on the board: count the board itself, never a number a caption says",
              "each distinct block colour", "the pieces' sizes", "whether the blocks' shapes and places mirror each other",
              "how full the board is"],
    "asset": ["what the picture shows that could be placed in the ad (a logo, a sticker, an end card)"],
    "modify": ["what the picture shows that could cover the walls or a block"],
}
PLAN_SYSTEM = (
    "You decide what a multimodal model must look for in a picture attached to a request for a new Color Block Jam "
    "video ad, so the ad can take from the picture what the request asks. You cannot see the picture; do not describe "
    "it. Color Block Jam is a puzzle game: coloured toy-brick blocks are dragged out of a grid board through gates of "
    "their colour, against a countdown clock.\n"
    "focus: what the request takes from the picture, from " + ", ".join(IMAGE_FOCI) + " (style: the look: the "
    "background, the captions' colours, the blocks' colours only when the request asks for them; board: the level's "
    "type from a board in the picture: its shape, size, block count, colours, pieces, symmetry, fullness; asset: the "
    "picture placed in the ad as a logo, sticker, end card, button or cursor; modify: the picture on the walls or as a "
    "block's skin). Several may apply; a request that names nothing about the picture (\"inspired by this image\") "
    "reads it for its concept: style and board.\n"
    "level: none (the request takes nothing from the picture), targeted (some parts), full (its concept as a whole). "
    "questions: what the model must answer for this request, one per entry, in your own words (for a count: count "
    "the board, never trust a caption's number). ignore: what the request says not to take (\"keep the game's own "
    "block colours\", \"only the background\"), and what must never be copied (its captions' words, its exact cells). "
    "constraints: values the request fixes itself (a length, an ending, a block count, a shape it names). why: one "
    "line on how you read the request.")
PLAN_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {"focus": {"type": "array", "items": {"type": "string", "enum": list(IMAGE_FOCI)}},
                   "level": {"type": "string", "enum": list(PLAN_LEVELS)},
                   "questions": {"type": "array", "items": {"type": "string"}},
                   "ignore": {"type": "array", "items": {"type": "string"}},
                   "constraints": {"type": "array", "items": {"type": "string"}},
                   "why": {"type": "string"}},
    "required": ["focus", "level", "questions", "ignore", "constraints", "why"],
}


def format_facts(path: Path) -> dict:
    """The picture's format only (never its name or content): {width, height, orientation, aspect, format, size_mb}."""
    from PIL import Image
    with Image.open(path) as im:
        w, h, fmt = im.size[0], im.size[1], (im.format or Path(path).suffix[1:]).upper()
    from math import gcd
    g = gcd(w, h) or 1
    return {"width": w, "height": h, "orientation": "portrait" if h > w else "landscape" if w > h else "square",
            "aspect": f"{w // g}:{h // g}" if max(w // g, h // g) <= 32 else f"{w / h:.2f}", "format": fmt,
            "size_mb": round(Path(path).stat().st_size / 1e6, 2)}


def plan_from_words(prompt: str, why: str = "") -> dict:
    """The word table's plan (the fallback): the roles imageplan.decide reads from the words for a board picture."""
    from . import imageplan
    d = imageplan.decide(prompt, {"file": "", "board": {"columns": 1}, "notes": {"is_color_block_jam": True}, "hud": {}})
    focus = list(d["roles"])
    return {"focus": focus, "level": "full" if (d.get("board") or {}).get("all") and d.get("style") else "targeted",
            "questions": list(dict.fromkeys(q for f in focus for q in FOCUS_QUESTIONS[f])),
            "ignore": ["its captions' words", "its exact cells"], "constraints": [],
            "why": why or f"read from the request's words: {', '.join(focus)}", "source": "words", "checks": []}


def parse_plan(raw) -> tuple[dict | None, str]:
    if not isinstance(raw, dict):
        return None, "the answer is not a JSON object"
    given = [str(f).strip().lower() for f in raw.get("focus") or [] if isinstance(f, str)]
    focus = list(dict.fromkeys(f for f in given if f in IMAGE_FOCI))
    level = str(raw.get("level") or "").strip().lower()
    questions = list(dict.fromkeys(q.strip()[:300] for q in raw.get("questions") or [] if isinstance(q, str) and q.strip()))[:10]
    strs = lambda x: [str(v).strip()[:200] for v in x or [] if str(v).strip()][:10] if isinstance(x, list) else []  # noqa: E731
    plan = {"focus": focus, "level": level if level in PLAN_LEVELS else "targeted", "questions": questions,
            "ignore": strs(raw.get("ignore")), "constraints": strs(raw.get("constraints")),
            "why": str(raw.get("why") or "")[:300], "source": "planner", "checks": []}
    if level == "none" and not focus:
        return plan, ""
    if not focus:
        return None, "no focus from the allowed set" + (f" (it said {', '.join(given)})" if given else "")
    if not questions:
        return None, "no questions for the reader"
    return plan, ""


def reading_plan(prompt: str, facts: dict, client=None, log=None) -> dict:
    """The request understood before the picture is read: one call to the planner's text model with the request and the
    picture's format facts (no name, no content); an empty or invalid plan falls back to the word table. A valid plan
    wins; the word table only notes where it would read otherwise. The plan narrows what is applied, never what is read:
    the reader always gives the whole reading, the plan's questions on top."""
    say = log or (lambda *_: None)
    if client is None:
        plan = plan_from_words(prompt)
        plan["checks"].append("no planner model was given, so the word table read the request")
        return plan
    user = (f"REQUEST:\n{prompt.strip() or '(no words about the picture)'}\n\nTHE ATTACHED PICTURE (its format only; you "
            f"cannot see it): {facts.get('width')}x{facts.get('height')} {facts.get('orientation')} ({facts.get('aspect')}), "
            f"{facts.get('format')}, {facts.get('size_mb')} MB")
    try:
        from .planner import _parse
        plan, why_not = parse_plan(_parse(client.complete(PLAN_SYSTEM, user, PLAN_SCHEMA)))
    except Exception as e:  # the fallback is the word table, never a guess
        plan, why_not = None, f"the planner's model gave no plan: {str(e)[:120]}"
    if plan is None:
        plan = plan_from_words(prompt)
        plan["checks"].append(f"the planner's plan was empty or invalid ({why_not}); the word table read the request")
        say(f"reading plan: {plan['checks'][-1]}")
        return plan
    plan["model"] = getattr(client, "last_model", None)
    words = plan_from_words(prompt)["focus"]
    if set(words) != set(plan["focus"]):
        plan["checks"].append(f"the planner reads {', '.join(plan['focus']) or 'nothing'} where the word table would read "
                              f"{', '.join(words)}: the plan wins")
        say(f"reading plan: {plan['checks'][-1]}")
    return plan


def general_ask(plan: dict | None = None) -> str:
    """The whole-picture ask, the same every time, with the plan's questions on top as the request's priorities."""
    ask = GENERAL_ASK
    qs = (plan or {}).get("questions") or []
    if qs:
        ask += ("\n\nTHE REQUEST'S PRIORITIES. Read the whole picture as above, and answer these too, one entry each in "
                "\"answers\" ([{\"question\": ..., \"answer\": ...}]), in the same order:\n"
                + "\n".join(f"{i + 1}. {q}" for i, q in enumerate(qs)))
    if (plan or {}).get("ignore"):
        ask += "\nThe request does not take these (describe them anyway): " + "; ".join(plan["ignore"])
    return ask


HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def validate_general(notes, plan: dict | None = None) -> list[str]:
    """What is wrong with a whole-picture answer, checked in code (the strict JSON the readers must give)."""
    if not isinstance(notes, dict):
        return ["the answer is not a JSON object"]
    out = []
    for k in ("what_it_shows", "is_color_block_jam", "hud", "board", "look", "captions_seen"):
        if k not in notes:
            out.append(f"\"{k}\" is missing")
    if "is_color_block_jam" in notes and not isinstance(notes["is_color_block_jam"], bool):
        out.append("\"is_color_block_jam\" must be true or false")
    hud = notes.get("hud")
    if hud is not None and not (isinstance(hud, dict) and isinstance(hud.get("shown"), bool)):
        out.append("\"hud.shown\" must be true or false")
    b = notes.get("board")
    if isinstance(b, dict) and b.get("shown"):
        for k in ("columns", "rows", "blocks"):
            if _ints(b.get(k)) is None or not 1 <= (_ints(b.get(k)) or 0) <= 30:
                out.append(f"\"board.{k}\" must be a whole number of cells or blocks")
        if not isinstance(b.get("colours"), list) or not b.get("colours"):
            out.append("\"board.colours\" must list each block colour once")
        if not isinstance(b.get("box"), dict):
            out.append("\"board.box\" must give the board's box, 0-1 of the picture")
    elif b is not None and not isinstance(b, dict):
        out.append("\"board\" must be an object")
    look = notes.get("look")
    if isinstance(look, dict):
        for k in ("background_top", "background_bottom"):
            if not HEX.match(str(look.get(k) or "")):
                out.append(f"\"look.{k}\" must be #RRGGBB")
    if "captions_seen" in notes and not isinstance(notes["captions_seen"], list):
        out.append("\"captions_seen\" must be a list of the captions' words")
    qs = (plan or {}).get("questions") or []
    if qs and (not isinstance(notes.get("answers"), list) or len(notes["answers"]) < len(qs)):
        out.append(f"\"answers\" must answer each of the {len(qs)} priority questions")
    return out


def ask_general(client, path: Path, plan: dict | None, raw: list | None = None) -> tuple[dict, list[str]]:
    """The whole-picture reading, checked in code, asked once more with the problems quoted: (notes, problems left)."""
    ask = general_ask(plan)
    notes = R._ask_json(client, ask, image_part(path), path, raw)
    problems = validate_general(notes, plan)
    if problems:
        again = R._ask_json(client, ask + "\n\nYOUR LAST ANSWER HAD THESE PROBLEMS: " + "; ".join(problems)
                            + ". Answer again with the whole JSON object only.", image_part(path), path, raw)
        left = validate_general(again, plan)
        if len(left) <= len(problems):
            notes, problems = again, left
    return (notes if isinstance(notes, dict) else {}), problems


def _base(path: Path) -> dict:
    out = {"file": Path(path).name, "kind": "image", "palette": R.palette(path), "margins": margins(path),
           "facts": format_facts(path)}
    return out


def _finish(out: dict, path: Path, notes: dict, rec: dict | None, counts, client, t0: float) -> dict:
    out["hud"] = hud_of(notes)
    caps = [str(c).strip() for c in notes.get("captions_seen") or [] if str(c).strip()] if isinstance(notes.get("captions_seen"), list) else []
    out["captions"] = caps
    out["caption_claims"] = caption_claims(caps)
    out["board"] = board_of_reading(notes, rec, counts, claimed=any(x["what"] == "blocks" for x in out["caption_claims"]))
    g = notes.get("board") if isinstance(notes.get("board"), dict) else {}
    try:
        out["colours_measured"] = apply_named(out["board"], notes, path, (rec or {}).get("box") or R.board_box(g.get("box")))
    except Exception as e:
        out["colours_measured"] = {"error": str(e)[:120]}
    try:
        out["caption_measured"] = caption_colours(path, notes.get("caption_box"), out["margins"]["top"]) if caps else None
    except Exception as e:
        out["caption_measured"] = {"error": str(e)[:120]}
    try:
        out["accent_measured"] = accent_of(path, notes)
    except Exception as e:
        out["accent_measured"] = {"error": str(e)[:120]}
    out["answers"] = notes.get("answers") if isinstance(notes.get("answers"), list) else []
    extras = [str(x).strip()[:80] for x in notes.get("not_in_game") or [] if str(x).strip()] if isinstance(notes.get("not_in_game"), list) else []
    extras += [x for x in (rec or {}).get("extras_seen") or [] if x not in extras]
    out["not_in_game"] = extras + [o for o in ((out["board"] or {}).get("obstacles") or []) if o not in extras]
    out["disagreements"] = disagreements(out, notes)
    out["model"] = getattr(client, "last_model", None)
    out["reader"] = getattr(client, "reader", None) or R.reader_of(out["model"])
    out["errors"] = list(out.get("errors") or []) + list(getattr(client, "errors", None) or [])[-6:]
    out["seconds"] = round(time.time() - t0, 1)
    return out


def accent_of(path: Path, notes: dict) -> dict | None:
    """The accent colour the reader names (look.accent), measured on the picture's pixels in the box it points at (the
    whole picture when it gives none): {hex_read, hex, share, confirmed} (H3b, 2026-10-18: S2's neon trims are not in
    the margins, so the captions fell back to white). None when the reader names no accent."""
    look = notes.get("look") if isinstance(notes.get("look"), dict) else {}
    hx = str(look.get("accent") or "").upper()
    if not HEX.match(hx):
        return None
    box = look.get("accent_box") if isinstance(look.get("accent_box"), dict) else None
    try:
        box = {k: min(1.0, max(0.0, float(box[k]))) for k in ("x", "y", "w", "h")} if box else None
    except (KeyError, TypeError, ValueError):
        box = None
    if not box or box["w"] <= 0 or box["h"] <= 0:
        box = {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0}
    m = measure_named(path, box, {"accent": hx}).get("accent") or {}
    rgb = m.get("rgb")
    return {"hex_read": hx, "hex": ("#%02X%02X%02X" % tuple(rgb)) if rgb and m.get("confirmed") else None,
            "share": m.get("share"), "confirmed": bool(m.get("confirmed"))}


PIXEL_MATCH = 60.0  # RGB distance: a crop pixel this close to the reader's hex is that block colour
PIXEL_SHARE = 0.004  # this share of the crop's pixels confirms a colour (a 1-cell block on a 7x9 board is about 1 %)


def measure_named(path: Path, box: dict | None, hexes: dict) -> dict:
    """Each block colour the reader gave a hex for, checked on the picture's pixels inside the board's box (rule I3:
    measured in code): the pixels within PIXEL_MATCH of the hex; PIXEL_SHARE of the crop or more confirms it, and their
    median is the colour as measured (2026-10-17, F2: the reader named pic_w's pastels with the game's words, so their
    shades were the game's own and the repaint skipped them). {name: {hex_read, rgb, share, confirmed}}."""
    import numpy as np
    from PIL import Image
    if not box or not hexes:
        return {}
    with Image.open(path) as im:
        W, H = im.size
        a = np.asarray(im.convert("RGB").crop((int(box["x"] * W), int(box["y"] * H), int((box["x"] + box["w"]) * W),
                                               int((box["y"] + box["h"]) * H)))).reshape(-1, 3).astype(float)
    out = {}
    names = list(hexes)
    cs = np.array([R._rgb(hexes[n]) for n in names], float)
    d = np.sqrt(((a[:, None, :] - cs[None, :, :]) ** 2).sum(2)) if a.size else np.zeros((0, len(names)))
    nearest = d.argmin(1) if a.size else np.zeros(0, int)
    for i, name in enumerate(names):
        hx = hexes[name]
        # each pixel counts for the reader's hex nearest to it, within PIXEL_MATCH (two close colours, pic_w's teal and
        # mint, keep their own pixels instead of both taking the same ones)
        m = (nearest == i) & (d[:, i] <= PIXEL_MATCH) if a.size else np.zeros(0, bool)
        share = float(m.mean()) if a.size else 0.0
        rgb = [int(v) for v in np.median(a[m], 0)] if m.sum() else None
        out[name] = {"hex_read": hx, "rgb": rgb, "share": round(share, 4), "confirmed": share >= PIXEL_SHARE}
    return out


def apply_named(board: dict | None, notes: dict, path: Path, box: dict | None) -> dict:
    """The board's colours given their measured shade: the pixels the reader's hex points at when they confirm it, else
    the reader's hex (said: not confirmed), else what pair_colours gave (a cluster or the name's shade)."""
    from .videoref import colour_name
    g = notes.get("board") if isinstance(notes.get("board"), dict) else {}
    names = [colour_name(c) for c in g.get("colours") or []]
    hexes = [str(h).upper() for h in g.get("colours_hex") or [] if HEX.match(str(h))] if isinstance(g.get("colours_hex"), list) else []
    pairs = {n: h for n, h in zip(names, hexes)}
    if not board or not pairs:
        return {}
    measured = measure_named(path, box, pairs)
    for c in board.get("colours") or []:
        mm = measured.get(c["name"])
        if not mm:
            continue
        if mm["confirmed"] and mm["rgb"]:
            c.update(rgb=mm["rgb"], measured=True, source="pixels", hex_read=mm["hex_read"], share=mm["share"])
        elif not c.get("measured"):
            c.update(rgb=list(R._rgb(mm["hex_read"])), source="the reader's hex (not confirmed on the pixels)",
                     hex_read=mm["hex_read"], share=mm["share"])
    return measured


def disagreements(out: dict, notes: dict) -> list[str]:
    """Where the code's measures and the reader's words differ (the measure wins where it is used: the symmetry by the
    mirror mask, the fill, the background and the caption colours)."""
    from .videoref import _distance
    lines = []
    bd = out.get("board") or {}
    g = notes.get("board") if isinstance(notes.get("board"), dict) else {}
    if bd.get("symmetric_source") == "measured" and isinstance(g.get("symmetric"), bool) and g["symmetric"] != bd.get("symmetric"):
        lines.append(f"symmetry: the reader said {'symmetric' if g['symmetric'] else 'not symmetric'}, the mirror mask measures "
                     f"{bd.get('mirror')} ({'symmetric' if bd.get('symmetric') else 'not symmetric'}): the measure is used")
    if bd.get("fill_doubt"):
        lines.append(f"fill: {bd['fill_doubt']}: not used")
    look = notes.get("look") if isinstance(notes.get("look"), dict) else {}
    m = out.get("margins") or {}
    for k, key in (("background_top", "top"), ("background_bottom", "bottom")):
        if HEX.match(str(look.get(k) or "")) and m.get(key) and _distance(R._rgb(look[k].upper()), R._rgb(m[key])) > 120:
            lines.append(f"{k.replace('_', ' ')}: the reader said {look[k]}, the picture's margin measures {m[key]}: the measure is used")
    cm = out.get("caption_measured") if isinstance(out.get("caption_measured"), dict) else {}
    for k, key in (("caption_fill", "fill"), ("caption_outline", "outline")):
        if HEX.match(str(look.get(k) or "")) and cm.get(key) and _distance(R._rgb(look[k].upper()), R._rgb(cm[key])) > 150:
            lines.append(f"{k.replace('_', ' ')}: the reader said {look[k]}, the caption's box measures {cm[key]}: the measure is used")
    n_names, n_cl = len(bd.get("colours") or []), bd.get("clusters_measured")
    if n_cl and n_cl != n_names:
        lines.append(f"colours: the reader named {n_names}, the code clusters {n_cl} on the crop (its names are kept; a measured "
                     f"cluster gives a named colour its shade)")
    return lines


def read_one(path: Path, client, plan: dict | None = None, log=None) -> dict:
    """The Opus reading: the whole picture once, strict JSON with the plan's questions on top (one re-ask with the
    problems quoted), then the code's measures on the board's box beside it (reference.measure_board on the crop: the
    mirror mask's symmetry, the fill, the colour clusters)."""
    t0 = time.time()
    out = _base(path)
    out["plan"] = plan
    if log:
        log(f"reading {path.name} with {getattr(client, 'model', 'the reader')}: the whole picture and the request's questions...")
    raw: list = []
    notes, problems = ask_general(client, path, plan, raw)
    if problems and not notes.get("board"):
        raise ValueError("the reading did not pass its checks: " + "; ".join(problems))
    out["notes"], out["validation"] = notes, {"status": "passed" if not problems else "passed with problems", "problems": problems}
    g = notes.get("board") if isinstance(notes.get("board"), dict) else {}
    rec = None
    box = R.board_box(g.get("box"))
    if g.get("shown") and box:
        cols, rows = _ints(g.get("columns")), _ints(g.get("rows"))
        rec = {"box": box, "board": {k: g.get(k) for k in ("columns", "rows", "shape", "blocks", "colours", "pieces",
                                                            "symmetric", "wall_cells")}}
        with tempfile.TemporaryDirectory() as tmp:
            crop = Path(tmp) / "board.jpg"
            try:
                R.crop_to_box(path, crop, box)
            except Exception as e:
                crop, rec["measure_error"] = None, str(e)[:160]
            if crop is not None:
                # the size asked SIZE_REREADS more times on the board's crop: the median per side of three reads (round 2,
                # 2026-10-17: one Opus read counted pic_z's floor tiles, 12x12 for 7x7)
                sizes = []
                for _ in range(SIZE_REREADS):
                    try:
                        sz = R._ask_json(client, R.SIZE_ASK, image_part(crop), crop)
                        c_, r_ = _ints(sz.get("columns")), _ints(sz.get("rows"))
                        sizes.append([c_, r_] if c_ and r_ and 2 <= c_ <= 16 and 2 <= r_ <= 16 else None)
                    except Exception:
                        sizes.append(None)
                rec["size_reads"] = sizes
                med = R.median_size([cols, rows], sizes)
                if med:
                    cols, rows = med
                    rec["board"].update(columns=cols, rows=rows, size_first=[g.get("columns"), g.get("rows")])
            if crop is not None and cols and rows and 2 <= cols <= 16 and 2 <= rows <= 16:
                try:
                    measured = R.measure_board(crop, cols, rows)
                    rec["measured"] = measured
                    grid = [x for row in measured["grid"] for x in row]
                    rec["board"].update(occupancy=round(sum(grid) / len(grid), 2), symmetric=measured["symmetric"],
                                        symmetric_first=g.get("symmetric"), symmetric_source="measured")
                except Exception as e:
                    rec["measure_error"] = str(e)[:160]
        rec["colour_count"] = len([c for c in g.get("colours") or [] if str(c).strip()]) or None
        rec["colours_counted"] = [str(c) for c in g.get("colours") or []]
    out["board_read"] = rec
    out = _finish(out, path, notes, rec, [], client, t0)
    if out.get("board") and rec and rec.get("measured"):
        out["board"]["clusters_measured"] = rec["measured"].get("colour_count")
        out["disagreements"] = disagreements(out, notes)
    return out


def read_multi(path: Path, client, plan: dict | None = None, log=None) -> dict:
    """The fallback reading (Gemini, then NVIDIA): the whole picture with the plan's questions, the board read again on
    its own by reference.read_board with the picture as the still, the blocks counted twice on the board's crop."""
    t0 = time.time()
    out = _base(path)
    out["plan"] = plan
    if log:
        log(f"reading {path.name}: the whole picture...")
    notes, problems = ask_general(client, path, plan)
    out["notes"], out["validation"] = notes, {"status": "passed" if not problems else "passed with problems", "problems": problems}
    g = notes.get("board") if isinstance(notes.get("board"), dict) else {}
    rec, count_read = None, None
    if g.get("shown") or notes.get("is_color_block_jam"):
        if log:
            log(f"reading {path.name}: the board on its own (the video path's board read, the picture as the still)...")
        with tempfile.TemporaryDirectory() as tmp:
            try:
                clip = still_clip(path, Path(tmp) / "still.mp4")
                rec = R.read_board(client, clip, {}, {"duration_s": STILL_CLIP_S}, log=log)
            except Exception as e:
                rec = {"error": str(e)[:200]}
        count_read = count_on_crop(client, path, (rec or {}).get("box") or R.board_box(g.get("box")))
        out["block_counts"] = count_read
        out["board_read"] = rec
    return _finish(out, path, notes, rec, count_read, client, t0)


def read(path: Path, client=None, log=None, plan: dict | None = None, fallback=None) -> dict:
    """The picture read for the plan: {file, kind "image", facts, palette, margins, plan, notes (the whole-picture
    reading), validation, answers (the plan's questions), board_read, board (board_of_reading), hud, captions,
    caption_claims, caption_measured, not_in_game, disagreements, model, reader, errors, seconds, fell_back} or, when the
    picture could not be read, {..., error}. The reader is image_reader() unless given: Opus reads once (read_one);
    when it fails, the fallback chain (reference.video_client) reads with the full board read (read_multi)."""
    path = Path(path)
    t0 = time.time()
    try:
        _base(path)
    except Exception as e:  # not a picture PIL can open: nothing to read
        return {"file": path.name, "kind": "image", "error": f"the picture could not be opened ({str(e)[:160]})",
                "seconds": round(time.time() - t0, 1), "plan": plan}
    client = client or image_reader()
    first_errors: list[str] = []
    if getattr(client, "reader", None) == "claude":
        try:
            return with_cells(read_one(path, client, plan, log), path, plan, client, log)
        except Exception as e:  # Opus could not read it: the fallback chain reads
            first_errors = [f"{getattr(client, 'last_model', None) or 'claude'}: {str(e)[:200]}"]
            if log:
                log(f"the Claude reader failed ({str(e)[:120]}); reading with Gemini, then NVIDIA")
            client = fallback or R.video_client()
    try:
        out = read_multi(path, client, plan, log)
    except Exception as e:  # reported in the brief, never guessed around
        return {"file": path.name, "kind": "image", "error": str(e)[:300], "plan": plan,
                "errors": first_errors + list(getattr(client, "errors", None) or [])[-6:], "seconds": round(time.time() - t0, 1)}
    if first_errors:
        out["errors"] = first_errors + out["errors"]
        out["fell_back"] = first_errors[0]
    out = with_cells(out, path, plan, client, log)
    out["seconds"] = round(time.time() - t0, 1)
    return out


def wants_cells(out: dict, plan: dict | None) -> bool:
    """Whether the board is read cell by cell too (imagecells, 2026-10-19): a Color Block Jam board with a box and a size
    was read, and the reading plan does not rule the board out (its focus names the board, or it is the word table's
    plan, or it reads everything)."""
    bd, notes = out.get("board") or {}, out.get("notes") or {}
    box = (out.get("board_read") or {}).get("box")
    if out.get("error") or not bd or not box or not (bd.get("columns") and bd.get("rows")):
        return False
    if not (2 <= bd["columns"] <= 12 and 2 <= bd["rows"] <= 12):
        return False
    if not (notes.get("is_color_block_jam") or (notes.get("kind") == "game screenshot") or (plan or {}).get("source") == "video"):
        return False  # a video's frame is a game board by the route that sent it (V6, 2026-10-19: LolTap's wooden board called no game)
    focus = (plan or {}).get("focus") or []
    return (plan or {}).get("level") != "none" and ("board" in focus or (plan or {}).get("source") != "planner" or not focus
                                                    or (plan or {}).get("level") == "full")


def with_cells(out: dict, path: Path, plan: dict | None, client, log=None) -> dict:
    """The reading with the board read cell by cell (out["cells"]) when wants_cells; never raises."""
    if not wants_cells(out, plan):
        return out
    from . import imagecells
    bd = out["board"]
    try:
        out["cells"] = imagecells.read_cells(path, out["board_read"]["box"], bd["columns"], bd["rows"], client, log=log,
                                             expect_blocks=bd.get("blocks"), expect_colours=len(bd.get("colours") or []) or None)
    except Exception as e:  # the cell reading is an extra: the type reading stands
        out["cells"] = {"error": str(e)[:200]}
    return out


def summary(r: dict) -> str:
    """One line for the log and the card: what was read."""
    if r.get("error"):
        return f"{r['file']}: could not be read ({r['error'][:100]})"
    n, bd, hud = r.get("notes") or {}, r.get("board") or {}, r.get("hud") or {}
    bits = [str(n.get("what_it_shows") or "a picture")]
    if n.get("is_color_block_jam"):
        bits.append("Color Block Jam itself")
    if bd:
        bits.append(f"a board {bd.get('columns') or '?'}x{bd.get('rows') or '?'} ({bd.get('outline') or bd.get('shape_read') or '?'}"
                    + (f", {bd['rooms']} rooms" if (bd.get("rooms") or 0) > 1 else "") + f"), {bd.get('blocks') or '?'} blocks in "
                    + ", ".join(c["name"] for c in bd.get("colours") or []) + (", symmetric" if bd.get("symmetric") else "")
                    + (f", {bd['occupancy']:.0%} filled" if isinstance(bd.get("occupancy"), (int, float)) else ""))
    bits.append("HUD " + (f"shown (level {hud.get('level')}, clock {hud.get('clock')})" if hud.get("shown") else "not shown"))
    m = r.get("margins") or {}
    bits.append(f"background {m.get('top')} to {m.get('bottom')}")
    if r.get("captions"):
        bits.append("captions " + " / ".join(f'"{c}"' for c in r["captions"]))
    return f"{r['file']}: " + "; ".join(bits) + f" (read by {r.get('model') or '?'} in {r.get('seconds')} s)"
