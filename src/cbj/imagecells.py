"""The board of a Color Block Jam picture read cell by cell, so a creative can play THE level in the picture, not a
new level of its type (2026-10-19; the owner's "create a similar game concept" on a level-71 screenshot came back as a
different ring, because rule I9 copied only the board's type).

The reading, in order, with the same reader the picture was read with (Opus through the Claude CLI; the fallback chain
when it is not there):
1. corners: the four corners of the playable grid on the board's crop (fractions; the camera's perspective makes the
   board a trapezoid), checked for order in code;
2. warp: the crop is warped so the grid is square (PIL's QUAD transform), with one cell of margin all round so the rim's
   gates are in view, and a lettered grid (columns A.., rows 1.. from the top) is drawn over it;
3. cells: the reader lists every block (its colour and the cells it covers), every hole cell (a wall, a cut-out) and
   every gate (its colour, the board cells it touches and the way out), in strict JSON;
4. verification in code: every cell is accounted for once; every claimed block cell is block-coloured in the warped
   pixels and of the claimed colour's family, every claimed hole or empty cell is not; every gate sits on an edge of
   the active area facing out. Disagreements are quoted back once and the reading is asked again; what still disagrees
   is recorded (the audit row shows it) or, past CELL_DOUBTS, the reading is refused;
5. the level: the cells become the game's own level JSON (pivot + offsets, exits with their direction), validated by
   level.validate and solved by the tool's solver. A board the solver cannot solve is refused with the reason (a gate
   read on the wrong side is the usual cause): the workflow then builds a board of the picture's type and says why.

Transforms (what a request asks on top of the picture's board, each keeping the rest of the board and checked by the
solver): recolour one colour into another (blocks and gates), add a colour (one block of the commonest colour is
recoloured and gets a gate of its own on the nearest rim the solver accepts), remove a colour (the rarest colour's
blocks and gates become another colour, so the geometry and the solution stay), mirror left-right or top-bottom.

Evidence: studio/_cells/<picture stem>.json (the reading, the verification, the level) and the overlay PNG beside it;
the level itself in studio/levels/picture_<hash>.json, which the version copies as its level.json.
"""

from __future__ import annotations

import colorsys
import copy
import hashlib
import json
import re
import time
from pathlib import Path

from . import brief as B

CELL_PX = 90  # the warped grid's cell, in pixels
MARGIN = 1  # cells of margin round the grid in the warp, for the rim's gates
INNER = 0.3  # the inner band of a cell sampled for its colour (0.3..0.7 each way, clear of the seams and the studs' rims)
CELL_DOUBTS = 2  # more cells than this still disagreeing with the pixels after the re-ask: the reading is refused
SOLVE_STATES = 250_000  # about 20 s at most on this machine; a board the solver cannot settle within it is said, not guessed
REPAIR_STATES = 100_000  # each repair trial's budget
GATE_SIDES = {"left": (-1, 0), "right": (1, 0), "up": (0, 1), "down": (0, -1), "top": (0, 1), "bottom": (0, -1)}
DIRECTION = {"left": 0, "right": 1, "up": 2, "top": 2, "down": 3, "bottom": 3}  # level.ExitDirection
SIDE_WORD = {0: "left", 1: "right", 2: "up", 3: "down"}
# hue families of a sampled block colour (degrees) -> the game slots that family may take
HUE_FAMILIES = ((0, 16, ("Red",)), (16, 36, ("Orange",)), (36, 48, ("Orange", "Yellow")), (48, 72, ("Yellow",)), (72, 172, ("Green", "DarkGreen")),
                (172, 245, ("Blue",)), (245, 262, ("Blue", "Purple")), (262, 322, ("Purple",)), (322, 345, ("Purple", "Red")), (345, 361, ("Red",)))
# 245-262 (2026-10-19, trailer 2's violet at about 258): a violet is purple to a reader and blue to the pixels; both stand;
# 36-48 (trailer 3's yellow plus at about 40, called "yellow" by the reader and "orange" by the old table): both stand

CORNERS_ASK = ("This is a crop of a Color Block Jam board: a grid of cells with coloured toy-brick blocks, framed by a dark "
               "rim that carries coloured gates. Give the four corners of the PLAYABLE GRID (the outer corners of the "
               "outermost cells, just inside the rim), as fractions of this image's width (x, 0 at the left edge) and "
               "height (y, 0 at the TOP edge, 1 at the bottom). top_left is the grid corner nearest the top-left of the "
               'image. Return ONLY JSON: {"top_left":[x,y],"top_right":[x,y],"bottom_right":[x,y],"bottom_left":[x,y]}')


def cells_ask(cols: int, rows: int) -> str:
    return (f"This is a Color Block Jam board warped to a flat grid of {cols} columns (letters A-{chr(64 + cols)}, left to "
            f"right) and {rows} rows (numbers 1-{rows}, top to bottom), with white grid lines drawn over it; the band outside "
            "the grid shows the rim with its coloured gates (a coloured segment with a white arrow). Account for EVERY cell "
            "exactly once: a cell is covered by one block, or is a hole (not part of the board: a wall, a cut-out, water, "
            "the board's frame), or is empty floor. A block is one connected piece of one colour; two touching pieces of "
            "the same colour that are separate blocks have a visible seam between them. A gate is listed by the BOARD "
            "cells it touches (the cells a block stands on just before it slides out) and the way out as seen on this "
            "image. A thin WALL LINE drawn between two neighbouring cells (a divider between rooms that takes no cell of its own) "
            "is listed separately with the rows (for a wall between two columns) or the columns (between two rows) it spans; two "
            "pieces of one colour on either side of such a wall are two blocks. Transparent bubbles, glass or ice covers, counters "
            "and numbers are NOT blocks: list the cells under them as empty floor (or as the coloured block beneath, if one shows). "
            'Return ONLY JSON: {"blocks":[{"colour":"<name as seen>","cells":["B1","C1"]}], "holes":["D4"], '
            '"empty":["A8"], "gates":[{"colour":"<name>","cells":["A1","A2"],"direction":"left|right|up|down"}], '
            '"wall_lines":[{"between_columns":["C","D"],"rows":["1","2","3"]},{"between_rows":["4","5"],"columns":["A","B"]}]}')


# ---------- geometry ----------

def cell_name(c: int, r: int) -> str:
    """Column c (0-based) and viewer row r (0-based from the top) as the overlay labels them: "B3"."""
    return f"{chr(65 + c)}{r + 1}"


def parse_cell(s, cols: int, rows: int) -> tuple[int, int] | None:
    m = re.fullmatch(r"\s*([A-Za-z])\s*(\d{1,2})\s*", str(s or ""))
    if not m:
        return None
    c, r = ord(m.group(1).upper()) - 65, int(m.group(2)) - 1
    return (c, r) if 0 <= c < cols and 0 <= r < rows else None


def ordered_corners(c: dict, w: int, h: int) -> dict | None:
    """The corners in pixels, in their proper places whatever order the reader gave them (the fallback reader once
    answered with y from the bottom): the two highest are the top pair, the leftmost of each pair is its left corner."""
    try:
        pts = [(float(c[k][0]) * w, float(c[k][1]) * h) for k in ("top_left", "top_right", "bottom_right", "bottom_left")]
    except (KeyError, TypeError, ValueError, IndexError):
        return None
    if any(not (0 <= x <= w and 0 <= y <= h) for x, y in pts):
        return None
    by_y = sorted(pts, key=lambda p: p[1])
    top, bottom = sorted(by_y[:2]), sorted(by_y[2:])
    q = {"top_left": top[0], "top_right": top[1], "bottom_left": bottom[0], "bottom_right": bottom[1]}
    if q["top_right"][0] - q["top_left"][0] < w * 0.2 or q["bottom_left"][1] - q["top_left"][1] < h * 0.2:
        return None
    return q


def warp(crop, q: dict, cols: int, rows: int):
    """The crop warped so the playable grid is a square grid of CELL_PX cells, with MARGIN cells round it (the quad is
    extended outward linearly, which is close enough for the game's mild perspective)."""
    from PIL import Image
    cx = sum(p[0] for p in q.values()) / 4
    cy = sum(p[1] for p in q.values()) / 4
    qe = {k: (x + (x - cx) * (2 * MARGIN / cols), y + (y - cy) * (2 * MARGIN / rows)) for k, (x, y) in q.items()}
    ow, oh = (cols + 2 * MARGIN) * CELL_PX, (rows + 2 * MARGIN) * CELL_PX
    return crop.transform((ow, oh), Image.QUAD,
                          data=(*qe["top_left"], *qe["bottom_left"], *qe["bottom_right"], *qe["top_right"]), resample=Image.BICUBIC)


def overlay(warped, cols: int, rows: int):
    """The warped board with the grid lines and the labels drawn on a copy."""
    from PIL import ImageDraw, ImageFont
    im = warped.copy()
    d = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 28)
    except OSError:
        font = ImageFont.load_default()
    m, cell = MARGIN, CELL_PX
    ow, oh = im.size
    for i in range(cols + 1):
        x = (m + i) * cell
        d.line([(x, m * cell), (x, (m + rows) * cell)], fill=(255, 255, 255), width=2)
    for j in range(rows + 1):
        y = (m + j) * cell
        d.line([(m * cell, y), ((m + cols) * cell, y)], fill=(255, 255, 255), width=2)
    for i in range(cols):
        for y in (8, oh - 40):
            d.text(((m + i) * cell + cell / 2 - 8, y), chr(65 + i), fill=(255, 255, 0), font=font)
    for j in range(rows):
        for x in (10, ow - 40):
            d.text((x, (m + j) * cell + cell / 2 - 14), str(j + 1), fill=(255, 255, 0), font=font)
    return im


def sample(warped, cols: int, rows: int) -> dict:
    """Each cell's inner band on the warped board: {(c, r): {"rgb": (r, g, b), "sat": s, "block": bool, "family": slots | None}}.
    `block` is the video path's strict block mask (saturated, or a bright pastel) on half the inner pixels; the verifier
    uses it beside an adaptive rule, because themed renders paint blocks in muted shades (T3's garden greens, 2026-10-19)."""
    import numpy as np
    from .reference import _block_mask
    a = np.asarray(warped.convert("RGB")).astype(float) / 255
    out = {}
    for r in range(rows):
        for c in range(cols):
            x0, y0 = (MARGIN + c) * CELL_PX, (MARGIN + r) * CELL_PX
            sub = a[int(y0 + INNER * CELL_PX):int(y0 + (1 - INNER) * CELL_PX), int(x0 + INNER * CELL_PX):int(x0 + (1 - INNER) * CELL_PX)]
            mask, _, _ = _block_mask(sub)
            on = bool(mask.size and mask.mean() >= 0.5)
            px = sub[mask] if on else sub.reshape(-1, 3)
            med = tuple(int(round(v * 255)) for v in np.median(px, 0)) if len(px) else (0, 0, 0)
            mx, mn = max(med) / 255, min(med) / 255
            sat = (mx - mn) / mx if mx > 0 else 0.0
            out[(c, r)] = {"rgb": med, "sat": round(sat, 3), "block": on, "family": hue_family(med)}
    return out


def hue_family(rgb) -> tuple[str, ...] | None:
    h, light, s = colorsys.rgb_to_hls(*(v / 255 for v in rgb))
    if s < 0.25 or light < 0.08 or light > 0.95:
        return None
    deg = h * 360
    return next((slots for lo, hi, slots in HUE_FAMILIES if lo <= deg < hi), None)


# ---------- the reading ----------

NOT_BLOCK = re.compile(r"\b(bubble|bubbles|clear|glass|ice|transparent|translucent|obstacle|counter|number|numbered|cover|lock|chain|frozen)\b", re.I)


def parse_answer(ans: dict, cols: int, rows: int) -> dict:
    """The reader's JSON checked for form: {blocks: [{colour, cells: [(c, r)]}], holes: set, empty: set, gates: [{colour,
    cells, direction}], problems: [lines]}. A cell named twice, or not at all, is a problem."""
    problems: list[str] = []
    blocks, seen = [], {}
    not_blocks, extra_empty = [], set()
    for i, b in enumerate(ans.get("blocks") or [] if isinstance(ans, dict) else []):
        if not isinstance(b, dict):
            continue
        cells = [parse_cell(x, cols, rows) for x in (b.get("cells") or [])]
        if not cells or any(x is None for x in cells):
            problems.append(f"block {i + 1} ({b.get('colour')}): a cell is outside the grid or unreadable ({b.get('cells')})")
            cells = [x for x in cells if x]
        name = str(b.get("colour") or "").strip().lower()
        if not name or not cells:
            continue
        if NOT_BLOCK.search(name):  # another game's bubbles and counters (V6, 2026-10-19): not blocks; their cells are floor
            not_blocks.append(name)
            for x in cells:
                if x not in seen:
                    extra_empty.add(x)
            continue
        for x in cells:
            if x in seen:
                problems.append(f"{cell_name(*x)} is in two pieces ({seen[x]} and {name})")
            seen[x] = name
        if not _connected(cells):
            problems.append(f"the {name} block at {', '.join(cell_name(*x) for x in cells)} is not one connected piece")
        blocks.append({"colour": name, "cells": cells})
    holes, empty = set(), set(x for x in extra_empty if x not in seen)
    for key, store in (("holes", holes), ("empty", empty)):
        for x in ans.get(key) or []:
            p = parse_cell(x, cols, rows)
            if p is None:
                problems.append(f"{key}: {x} is not a cell of the grid")
                continue
            if p in seen:
                problems.append(f"{cell_name(*p)} is both {key.rstrip('s')} and part of the {seen[p]} block")
            seen.setdefault(p, key)
            store.add(p)
    missing = [cell_name(c, r) for r in range(rows) for c in range(cols) if (c, r) not in seen]
    if missing:
        problems.append("not accounted for: " + ", ".join(missing[:12]) + (" ..." if len(missing) > 12 else ""))
    walls_v, walls_h = set(), set()  # (k, r): a wall between columns k-1 and k at viewer row r; (c, k): between rows k-1 and k at column c
    for w in ans.get("wall_lines") or []:
        if not isinstance(w, dict):
            continue
        bc, br = w.get("between_columns"), w.get("between_rows")
        try:
            if bc and len(bc) == 2:
                k = max(ord(str(bc[0]).strip().upper()[0]) - 65, ord(str(bc[1]).strip().upper()[0]) - 65)
                for r in w.get("rows") or []:
                    if 1 <= k < cols and 1 <= int(r) <= rows:
                        walls_v.add((k, int(r) - 1))
            elif br and len(br) == 2:
                k = max(int(br[0]), int(br[1])) - 1
                for c in w.get("columns") or []:
                    ci = ord(str(c).strip().upper()[0]) - 65
                    if 1 <= k < rows and 0 <= ci < cols:
                        walls_h.add((ci, k))
        except (TypeError, ValueError, IndexError):
            problems.append(f"wall line unreadable: {w}")
    if walls_v or walls_h:
        split = []
        for b in blocks:
            for part in _split_by_walls(b["cells"], walls_v, walls_h):
                split.append({"colour": b["colour"], "cells": part})
        blocks = split
    gates = []
    for i, g in enumerate(ans.get("gates") or []):
        if not isinstance(g, dict):
            continue
        cells = [parse_cell(x, cols, rows) for x in (g.get("cells") or [])]
        d = str(g.get("direction") or g.get("side") or "").strip().lower()
        name = str(g.get("colour") or "").strip().lower()
        if d not in DIRECTION or not cells or any(x is None for x in cells) or not name:
            problems.append(f"gate {i + 1} ({name or '?'}, {d or '?'}, {g.get('cells')}): unreadable")
            continue
        gates.append({"colour": name, "cells": cells, "direction": d})
    # a gate named differently from its blocks ("purple" gate, "magenta" blocks; T8, 2026-10-19) takes the block name of
    # the same colour family when there is exactly one
    from .imageplan import family_of
    names = list(dict.fromkeys(b["colour"] for b in blocks))
    for g in gates:
        if g["colour"] not in names:
            fam = set(family_of(g["colour"]) or ())
            same = [n for n in names if fam and set(family_of(n) or ()) & fam]
            if len(same) == 1:
                g["colour"] = same[0]
    out = {"blocks": blocks, "holes": holes, "empty": empty, "gates": gates, "problems": problems, "walls_v": walls_v, "walls_h": walls_h}
    if not_blocks:
        out["notes"] = [f"{len(not_blocks)} item(s) the reader listed are not blocks of this game ({', '.join(dict.fromkeys(not_blocks))}): "
                        "their cells are floor"]
    return out


def _split_by_walls(cells: list, walls_v: set, walls_h: set) -> list[list]:
    """A block's cells as connected pieces when thin walls run between some of them (one piece when none does)."""
    allc, parts, left = set(cells), [], set(cells)
    def joined(a, b):
        (c1, r1), (c2, r2) = a, b
        if r1 == r2 and abs(c1 - c2) == 1:
            return (max(c1, c2), r1) not in walls_v
        if c1 == c2 and abs(r1 - r2) == 1:
            return (c1, max(r1, r2)) not in walls_h
        return False
    while left:
        start = next(iter(left))
        todo, seen = [start], {start}
        while todo:
            x = todo.pop()
            for n in ((x[0] + 1, x[1]), (x[0] - 1, x[1]), (x[0], x[1] + 1), (x[0], x[1] - 1)):
                if n in allc and n not in seen and joined(x, n):
                    seen.add(n)
                    todo.append(n)
        parts.append(sorted(seen))
        left -= seen
    return parts


def _connected(cells: list) -> bool:
    todo, seen = [cells[0]], {cells[0]}
    allc = set(cells)
    while todo:
        c, r = todo.pop()
        for n in ((c + 1, r), (c - 1, r), (c, r + 1), (c, r - 1)):
            if n in allc and n not in seen:
                seen.add(n)
                todo.append(n)
    return len(seen) == len(allc)


FLOOR_SAT_GAP = 0.15  # a claimed block cell this close to the floor's saturation, and near its colour, is floor
FLOOR_NEAR = 60.0  # redmean distance to the floor's median colour under which a cell is the floor
BLOCK_SAT_GAP = 0.25  # a claimed empty cell this much more saturated than the floor, and far from it, holds a block
BLOCK_FAR = 90.0


def verify(parsed: dict, samples: dict, cols: int, rows: int, expect_blocks: int | None = None, expect_colours: int | None = None) -> dict:
    """The reading against the pixels and the board's geometry: {doubts: [lines], checked: n, of: m, floor}. The floor
    is what the reader called empty (its median colour and saturation): a claimed block cell is doubted when it looks
    like that floor, a claimed empty cell when it is clearly more saturated and far from it; a claimed block cell that
    is block-coloured but of another hue family than its name is doubted too."""
    from .imageplan import family_of
    from .videoref import _distance
    import numpy as np
    doubts = []
    empties = [samples[x] for x in parsed["empty"] if x in samples]
    if empties:
        floor_rgb = tuple(int(v) for v in np.median(np.array([e["rgb"] for e in empties]), 0))
        floor_sat = float(np.median([e["sat"] for e in empties]))
    else:
        floor_rgb, floor_sat = (94, 106, 148), 0.35  # the game's own cells
    def like_floor(s):
        return s["sat"] < floor_sat + FLOOR_SAT_GAP and _distance(s["rgb"], floor_rgb) < FLOOR_NEAR
    def like_block(s):
        return s["block"] or (s["sat"] > floor_sat + BLOCK_SAT_GAP and _distance(s["rgb"], floor_rgb) > BLOCK_FAR)
    for b in parsed["blocks"]:
        fam = family_of(b["colour"])
        for x in b["cells"]:
            s = samples.get(x)
            if not s:
                continue
            if like_floor(s) and not s["block"]:
                doubts.append(f"{cell_name(*x)}: read as part of a {b['colour']} block, but the pixels show floor")
            elif like_block(s) and fam and s["family"] and not set(fam) & set(s["family"]):
                doubts.append(f"{cell_name(*x)}: read as {b['colour']}, but the pixels are {_family_word(s['family'])}")
    # a hole may show anything (water in a ring's middle, a neon-lit wall, the background through a cut-out), so its pixels
    # are not evidence either way (T2's blue-lit wall column, 2026-10-19)
    for x in parsed["empty"]:
        s = samples.get(x)
        if s and like_block(s) and not like_floor(s):
            doubts.append(f"{cell_name(*x)}: read as empty, but the pixels show a {_family_word(s['family']) or 'coloured'} block")
    if expect_blocks and abs(len(parsed["blocks"]) - expect_blocks) >= 1:
        doubts.append(f"the whole-picture read counted {expect_blocks} blocks; this reading lists {len(parsed['blocks'])}")
    n_names = len({b["colour"] for b in parsed["blocks"]})
    if expect_colours and n_names < expect_colours:  # V3 (2026-10-19): yellow and orange named "orange" together, 6 names for 8 colours
        doubts.append(f"the whole-picture read counted {expect_colours} block colours; this reading names only {n_names}: two colours "
                      "may share a name (yellow and orange, blue and light blue, green and dark green): name each colour distinctly")
    active = {(c, r) for r in range(rows) for c in range(cols)} - parsed["holes"]
    for g in parsed["gates"]:
        dx, dy = GATE_SIDES[g["direction"]]
        for x in g["cells"]:
            if x not in active:
                doubts.append(f"gate {g['colour']} at {cell_name(*x)}: that cell is a hole, not a board cell")
            elif (x[0] + dx, x[1] - dy) in active:  # viewer rows grow downward: "up" is r - 1
                doubts.append(f"gate {g['colour']} at {cell_name(*x)} pointing {g['direction']}: the next cell that way is "
                              f"still the board, so it is not an edge")
    names = {b["colour"] for b in parsed["blocks"]}
    for n in names:
        if not any(g["colour"] == n for g in parsed["gates"]):
            doubts.append(f"no gate was read for the {n} blocks")
    return {"doubts": doubts, "checked": len(samples), "of": cols * rows, "floor": {"rgb": list(floor_rgb), "sat": round(floor_sat, 3)}}


def _family_word(slots) -> str:
    words = {("Red",): "red", ("Orange",): "orange", ("Yellow",): "yellow", ("Green", "DarkGreen"): "green", ("Blue",): "blue",
             ("Purple",): "purple", ("Purple", "Red"): "pink"}
    return words.get(tuple(slots or ()), "another colour")


SHADE_SPLIT = 110.0  # two blocks of one read name whose measured colours differ by more than this (redmean) are two colours


HUE_SPLIT_DEG = 10.0  # one read name whose blocks' hues fall in two clusters this far apart holds two colours


def split_hues(parsed: dict, samples: dict) -> dict:
    """Blocks the reader gave one name but whose pixels form two hue clusters (V3, 2026-10-19: the yellow plus at about 40
    degrees and the orange cubes at 25, both "orange"): the cluster farther from the name's own game hue takes the word of
    the nearest game colour by hue that no block carries yet. Runs before split_shades (lightness inside one family)."""
    import colorsys
    from . import brief as B
    from .imageplan import RENDERED, _rgb, family_of
    import numpy as np

    def hue(rgb):
        h, _, sat = colorsys.rgb_to_hls(*(v / 255 for v in rgb))
        return h * 360 if sat >= 0.1 else None

    def gap(a, b):
        d = abs(a - b) % 360
        return min(d, 360 - d)

    slot_hue = {s: hue(_rgb(RENDERED[s])) for s in B.COLOURS}
    by_name: dict = {}
    for i, b in enumerate(parsed["blocks"]):
        by_name.setdefault(b["colour"], []).append(i)
    taken = set(by_name)
    for name, idx in list(by_name.items()):
        if len(idx) < 2:
            continue
        hues = {}
        for i in idx:
            px = [samples[x]["rgb"] for x in parsed["blocks"][i]["cells"] if x in samples]
            if px:
                h = hue(tuple(int(v) for v in np.median(np.array(px), 0)))
                if h is not None:
                    hues[i] = h
        if len(hues) < 2:
            continue
        order = sorted(hues, key=hues.get)
        gaps = [(gap(hues[order[k + 1]], hues[order[k]]), k) for k in range(len(order) - 1)]
        g, k = max(gaps)
        if g < HUE_SPLIT_DEG:
            continue
        low, high = order[:k + 1], order[k + 1:]
        fam = family_of(name) or ()
        own = slot_hue.get(fam[0]) if fam else None
        if own is None:
            continue
        far = high if gap(float(np.mean([hues[i] for i in high])), own) > gap(float(np.mean([hues[i] for i in low])), own) else low
        far_hue = float(np.mean([hues[i] for i in far]))
        free = [s for s in B.COLOURS if B.COLOUR_WORDS[s] not in taken and s not in fam and slot_hue[s] is not None]
        if not free:
            continue
        slot = min(free, key=lambda s: gap(slot_hue[s], far_hue))
        if gap(slot_hue[slot], far_hue) >= gap(own, far_hue):
            continue  # the far cluster is still nearer the name's own colour than any other: one colour after all
        word = B.COLOUR_WORDS[slot]
        for i in far:
            parsed["blocks"][i]["colour"] = word
        taken.add(word)
        parsed.setdefault("notes", []).append(f"two colours read as one name ({name}): {len(far)} block(s) at hue {far_hue:.0f} are {word} by their pixels")
    return parsed


def split_shades(parsed: dict, samples: dict) -> dict:
    """Blocks the reader gave one name but the pixels show as two shades (T2's dark and bright "green", 2026-10-19): when the
    name's family has two game slots (green: Green and DarkGreen), the darker group is renamed "dark <name>"."""
    from .imageplan import family_of
    from .videoref import _distance
    import numpy as np
    by_name: dict = {}
    for i, b in enumerate(parsed["blocks"]):
        by_name.setdefault(b["colour"], []).append(i)
    for name, idx in by_name.items():
        fam = family_of(name) or ()
        if len(idx) < 2 or len(fam) < 2 or name.startswith("dark"):
            continue
        meds = {}
        for i in idx:
            px = [samples[x]["rgb"] for x in parsed["blocks"][i]["cells"] if x in samples]
            if px:
                meds[i] = tuple(int(v) for v in np.median(np.array(px), 0))
        if len(meds) < 2 or max(_distance(a, b) for a in meds.values() for b in meds.values()) <= SHADE_SPLIT:
            continue
        lum = {i: 0.299 * m[0] + 0.587 * m[1] + 0.114 * m[2] for i, m in meds.items()}
        cut = (max(lum.values()) + min(lum.values())) / 2
        for i, L in lum.items():
            if L < cut:
                parsed["blocks"][i]["colour"] = f"dark {name}"
        parsed.setdefault("notes", []).append(f"two shades of {name} read as one name: the darker blocks are dark {name}")
    return parsed


def slot_map(parsed: dict, samples: dict) -> dict:
    """Each read colour name -> a game slot, the nearest free one by the measured shade (imageplan.colour_map: a name's
    own family first)."""
    from .imageplan import colour_map
    import numpy as np
    cols = []
    for name in dict.fromkeys(b["colour"] for b in parsed["blocks"]):
        px = [samples[x]["rgb"] for b in parsed["blocks"] if b["colour"] == name for x in b["cells"] if x in samples]
        rgb = tuple(int(v) for v in np.median(np.array(px), 0)) if px else None
        from .videoref import colour_rgb
        cols.append({"name": name, "rgb": list(rgb or colour_rgb(name) or (128, 128, 128)), "measured": bool(px)})
    return {m["read"]: m["slot"] for m in colour_map(cols)}


def colour_table(parsed: dict, samples: dict) -> list[dict]:
    """[{name, rgb (measured median), slot, note}] for every read colour name (2026-10-19: the video copy shows the game's
    own footage in its measured colours, imageplan.repaint)."""
    from .imageplan import colour_map
    import numpy as np
    from .videoref import colour_rgb
    cols = []
    for name in dict.fromkeys(b["colour"] for b in parsed["blocks"]):
        px = [samples[x]["rgb"] for b in parsed["blocks"] if b["colour"] == name for x in b["cells"] if x in samples]
        rgb = tuple(int(v) for v in np.median(np.array(px), 0)) if px else None
        cols.append({"name": name, "rgb": list(rgb or colour_rgb(name) or (128, 128, 128)), "measured": bool(px)})
    return [{"name": m["read"], "rgb": m["rgb"], "slot": m["slot"], "note": m.get("note"), "measured": m.get("measured")} for m in colour_map(cols)]


def walls_note(parsed: dict) -> str | None:
    """How thin wall lines are translated, in words, or None when the picture has none."""
    v, h = parsed.get("walls_v") or set(), parsed.get("walls_h") or set()
    if not v and not h:
        return None
    def runs(xs: list) -> str:
        out, start, prev = [], None, None
        for x in xs:
            if start is None:
                start = prev = x
            elif x == prev + 1:
                prev = x
            else:
                out.append(f"{start}-{prev}" if start != prev else f"{start}")
                start = prev = x
        if start is not None:
            out.append(f"{start}-{prev}" if start != prev else f"{start}")
        return ", ".join(out)
    bits = []
    for k in sorted({k for k, _ in v}):
        rs = sorted(r + 1 for kk, r in v if kk == k)
        bits.append(f"between columns {chr(64 + k)} and {chr(65 + k)} (rows {runs(rs)})")
    for k in sorted({k for _, k in h}):
        cs = sorted(c for c, kk in h if kk == k)
        bits.append(f"between rows {k} and {k + 1} (columns {', '.join(chr(65 + c) for c in cs)})")
    return ("the thin wall " + "; ".join(bits) + " becomes a line of wall cells with the same gaps (the game's only obstacle is a "
            "wall cell), so the grid is one cell wider or taller there")


def to_level(parsed: dict, cols: int, rows: int, slots: dict) -> dict:
    """The game's level JSON from the cells (viewer rows from the top -> the game's y from the bottom). A thin wall line
    between two columns (or rows) becomes an inserted column (row) of wall cells where the line runs and open cells where
    it does not: the game has no thin walls (T9's two rooms, 2026-10-19)."""
    from .generate import TIMER_S
    vcuts = sorted({k for k, _ in parsed.get("walls_v") or set()})
    hcuts = sorted({k for _, k in parsed.get("walls_h") or set()})
    W, H = cols + len(vcuts), rows + len(hcuts)
    nx = lambda c: c + sum(1 for k in vcuts if k <= c)  # noqa: E731
    nr = lambda r: r + sum(1 for k in hcuts if k <= r)  # noqa: E731
    y = lambda r: H - 1 - nr(r)  # noqa: E731
    blocks = []
    for b in parsed["blocks"]:
        cells = sorted(b["cells"], key=lambda x: (x[1], x[0]))  # the top-left cell is the pivot
        px, py = nx(cells[0][0]), y(cells[0][1])
        blocks.append({"gridPosition": {"x": px, "y": py}, "blockColor": B.COLOURS.index(slots[b["colour"]]),
                       "shapeOffsets": [{"x": nx(c) - px, "y": y(r) - py} for c, r in cells]})
    exits = []
    for g in parsed["gates"]:
        if g["colour"] not in slots:
            continue  # a gate of a colour no block has: the game would ignore it
        cells = sorted(g["cells"], key=lambda x: (x[1], x[0]))
        px, py = nx(cells[0][0]), y(cells[0][1])
        exits.append({"exitNumber": 0, "requiredColor": B.COLOURS.index(slots[g["colour"]]), "gridPosition": {"x": px, "y": py},
                      "direction": DIRECTION[g["direction"]], "shapeOffsets": [{"x": nx(c) - px, "y": y(r) - py} for c, r in cells]})
    holes = {(nx(c), y(r)) for c, r in parsed["holes"]}
    for i, k in enumerate(vcuts):  # the inserted column sits at new x = k + i; wall cells where the line runs
        x = k + i
        for r in range(rows):
            if (k, r) in parsed["walls_v"]:
                holes.add((x, y(r)))
    for j, k in enumerate(hcuts):
        yy = H - 1 - (k + j)
        for c in range(cols):
            if (c, k) in parsed["walls_h"]:
                holes.add((nx(c), yy))
    return {"gridWidth": W, "gridHeight": H, "timerCount": TIMER_S,
            "inactiveCells": [{"x": x, "y": yv} for x, yv in sorted(holes, key=lambda h: (-h[1], h[0]))],
            "GridBlockDatas": blocks, "ExitDatas": exits}


def solvable(d: dict, max_states: int = SOLVE_STATES) -> tuple[bool, str]:
    """(True, "<n> drags") when the level is valid and the solver solves it; else (False, why)."""
    from .level import level_from_dict, validate
    from .solver import SolverLimitError, solve_fast
    try:
        L = level_from_dict(d, name="picture")
    except ValueError as e:
        return False, str(e)[:160]
    problems = validate(L)
    if problems:
        return False, problems[0][:160]
    try:
        sol = solve_fast(L, max_states=max_states)
    except SolverLimitError:
        return False, f"the solver gave up after {max_states} positions (the board is too complex to settle in time)"
    if sol is None:
        return False, "the board has no solution"
    return True, f"{sol.min_drags} drags"


def read_cells(path: Path, box: dict, cols: int, rows: int, client, log=None, evidence: Path | None = None,
               expect_blocks: int | None = None, expect_colours: int | None = None) -> dict:
    """The whole reading (the module note). Returns {level, parsed, slots, verify, corners, overlay, warp, crop, asks,
    seconds, model, solve} or {..., error}. Never raises."""
    import tempfile
    from PIL import Image
    from . import reference as R
    from .imageread import image_part
    t0 = time.time()
    out: dict = {"cols": cols, "rows": rows, "box": box, "asks": 0}
    evidence = evidence or (Path(__file__).resolve().parents[2] / "studio" / "_cells")
    try:
        evidence.mkdir(parents=True, exist_ok=True)
        stem = Path(path).stem
        crop = evidence / f"{stem}_crop.jpg"
        R.crop_to_box(Path(path), crop, box)
        out["crop"] = crop.name
        if log:
            log(f"reading the board cell by cell: the grid's corners on the crop...")
        ans = R._ask_json(client, CORNERS_ASK, image_part(crop), crop)
        out["asks"] += 1
        im = Image.open(crop).convert("RGB")
        q = ordered_corners(ans, *im.size)
        if q is None:
            raise ValueError(f"the grid's corners could not be read ({str(ans)[:120]})")
        out["corners"] = {k: [round(v[0] / im.size[0], 4), round(v[1] / im.size[1], 4)] for k, v in q.items()}
        warped = warp(im, q, cols, rows)
        ov = overlay(warped, cols, rows)
        wp, op = evidence / f"{stem}_warp.png", evidence / f"{stem}_grid.png"
        warped.save(wp)
        ov.save(op)
        out["warp"], out["overlay"] = wp.name, op.name
        samples = sample(warped, cols, rows)
        out["block_cells_measured"] = sum(1 for s in samples.values() if s["block"])
        if log:
            log(f"cells: {cols}x{rows} grid warped flat; {out['block_cells_measured']} cells are block-coloured in the pixels; "
                f"asking for every block, hole and gate...")
        ans = R._ask_json(client, cells_ask(cols, rows), image_part(op), op)
        out["asks"] += 1
        parsed = parse_answer(ans, cols, rows)
        ver = verify(parsed, samples, cols, rows, expect_blocks, expect_colours)
        out["first"] = {"problems": parsed["problems"], "doubts": ver["doubts"]}
        if parsed["problems"] or ver["doubts"]:
            lines = parsed["problems"] + ver["doubts"]
            if log:
                log(f"cells: {len(lines)} doubt(s) after the first reading ({'; '.join(lines[:3])}{'; ...' if len(lines) > 3 else ''}); asking once more")
            again = (cells_ask(cols, rows) + "\nA previous reading of this same image had these problems; look again at those "
                     "cells and return the corrected JSON (keep what was right): " + " | ".join(lines[:20]))
            ans2 = R._ask_json(client, again, image_part(op), op)
            out["asks"] += 1
            parsed2 = parse_answer(ans2, cols, rows)
            ver2 = verify(parsed2, samples, cols, rows, expect_blocks, expect_colours)
            if len(parsed2["problems"]) + len(ver2["doubts"]) <= len(lines):
                parsed, ver = parsed2, ver2
        out["parsed"] = {"blocks": [{"colour": b["colour"], "cells": [cell_name(*x) for x in b["cells"]]} for b in parsed["blocks"]],
                         "holes": [cell_name(*x) for x in sorted(parsed["holes"])], "empty": [cell_name(*x) for x in sorted(parsed["empty"])],
                         "gates": [{"colour": g["colour"], "cells": [cell_name(*x) for x in g["cells"]], "direction": g["direction"]} for g in parsed["gates"]],
                         "problems": parsed["problems"]}
        out["verify"] = ver
        hard = [x for x in parsed["problems"] if "two pieces" in x or "not accounted" in x or "unreadable" in x]
        if len(ver["doubts"]) + len(hard) > CELL_DOUBTS:
            raise ValueError(f"{len(ver['doubts']) + len(hard)} cells or gates still disagree with the pixels "
                             f"({'; '.join((hard + ver['doubts'])[:3])})")
        if not parsed["blocks"]:
            raise ValueError("no block was read on the board")
        before = copy.deepcopy(parsed)
        parsed = split_hues(parsed, samples)
        parsed = split_shades(parsed, samples)
        names = {b["colour"] for b in parsed["blocks"]}
        if len(names) > 7 and len({b["colour"] for b in before["blocks"]}) <= 7:
            # the splits made more colours than the game has (V6, 2026-10-19: LolTap's bubbles darken the pink and green under
            # them, so the shades split into eight names): the reader's own names stand
            parsed = before
            parsed.setdefault("notes", []).append(f"{len(names)} colours after splitting shades is more than the game's seven: the reader's "
                                                  f"{len({b['colour'] for b in before['blocks']})} names stand")
        for line in parsed.get("notes") or []:
            out.setdefault("notes", []).append(line)
        slots = slot_map(parsed, samples)
        missing = [b["colour"] for b in parsed["blocks"] if b["colour"] not in slots]
        if len({b["colour"] for b in parsed["blocks"]}) > 7 or missing:
            raise ValueError(f"{len({b['colour'] for b in parsed['blocks']})} block colours were read; the game has seven")
        out["slots"] = slots
        out["colours"] = colour_table(parsed, samples)
        out["walls"] = walls_note(parsed)
        level = to_level(parsed, cols, rows, slots)
        ok, why = solvable(level)
        out["solve"] = why
        if not ok:
            # the pictures are renders, not the game's own levels: the smallest gate repair, said (T1, T2, T9, 2026-10-19). A
            # solver that gives up usually means an unsolvable board explored to its budget: the stranded-block repair runs first
            fixed, note = repair(level)
            if fixed is not None:
                level, ok = fixed, True
                out["repair"] = "the board as drawn could not be played; repaired: " + note
                out["solve"] = solvable(level)[1]
                if log:
                    log(f"cells: {out['repair'][:200]}")
        if not ok:
            raise ValueError(f"the board as read cannot be played ({why})")
        out["level"] = level
        out["model"] = getattr(client, "last_model", None)
        out["seconds"] = round(time.time() - t0, 1)
        (evidence / f"{stem}.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
        if log:
            log(f"cells: {len(level['GridBlockDatas'])} blocks in {len(slots)} colours, {len(level['inactiveCells'])} hole cells, "
                f"{len(level['ExitDatas'])} gates; {len(ver['doubts'])} doubt(s) left; solvable in {why} ({out['seconds']} s)")
        return out
    except Exception as e:
        out["error"] = str(e)[:300]
        out["seconds"] = round(time.time() - t0, 1)
        out["model"] = getattr(client, "last_model", None)
        if log:
            log(f"cells: the board could not be read cell by cell ({out['error'][:160]})")
        try:
            (evidence / f"{Path(path).stem}.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
        except OSError:
            pass
        return out


# ---------- transforms ----------

def colours_of(d: dict) -> list[str]:
    return [B.COLOURS[i] for i in sorted({b["blockColor"] for b in d["GridBlockDatas"]})]


def recolour(d: dict, a: str, b: str) -> dict:
    """Every block and gate of slot a becomes slot b."""
    ia, ib = B.COLOURS.index(a), B.COLOURS.index(b)
    out = copy.deepcopy(d)
    for blk in out["GridBlockDatas"]:
        if blk["blockColor"] == ia:
            blk["blockColor"] = ib
    for e in out["ExitDatas"]:
        if e["requiredColor"] == ia:
            e["requiredColor"] = ib
    return out


def mirror(d: dict, axis: str = "lr") -> dict:
    """The board mirrored left-right ("lr") or top-bottom ("tb"): cells, holes and gates; the solution mirrors with it."""
    out = copy.deepcopy(d)
    w, h = d["gridWidth"], d["gridHeight"]
    fx = (lambda x: w - 1 - x) if axis == "lr" else (lambda x: x)
    fy = (lambda y: h - 1 - y) if axis == "tb" else (lambda y: y)
    swap = {0: 1, 1: 0} if axis == "lr" else {2: 3, 3: 2}
    for blk in out["GridBlockDatas"]:
        cells = [(blk["gridPosition"]["x"] + o["x"], blk["gridPosition"]["y"] + o["y"]) for o in blk["shapeOffsets"]] or \
                [(blk["gridPosition"]["x"], blk["gridPosition"]["y"])]
        cells = sorted(((fx(x), fy(y)) for x, y in cells), key=lambda c: (-c[1], c[0]))
        px, py = cells[0]
        blk["gridPosition"] = {"x": px, "y": py}
        blk["shapeOffsets"] = [{"x": x - px, "y": y - py} for x, y in cells]
    for e in out["ExitDatas"]:
        cells = sorted({(e["gridPosition"]["x"], e["gridPosition"]["y"])} | {(e["gridPosition"]["x"] + o["x"], e["gridPosition"]["y"] + o["y"]) for o in e["shapeOffsets"]})
        cells = sorted(((fx(x), fy(y)) for x, y in cells), key=lambda c: (-c[1], c[0]))
        px, py = cells[0]
        e["gridPosition"] = {"x": px, "y": py}
        e["shapeOffsets"] = [{"x": x - px, "y": y - py} for x, y in cells]
        e["direction"] = swap.get(e["direction"], e["direction"])
    out["inactiveCells"] = [{"x": fx(c["x"]), "y": fy(c["y"])} for c in d["inactiveCells"]]
    return out


def _active(d: dict) -> set:
    holes = {(c["x"], c["y"]) for c in d["inactiveCells"]}
    return {(x, y) for x in range(d["gridWidth"]) for y in range(d["gridHeight"]) if (x, y) not in holes}


def _block_cells(blk: dict) -> list:
    px, py = blk["gridPosition"]["x"], blk["gridPosition"]["y"]
    return [(px + o["x"], py + o["y"]) for o in blk["shapeOffsets"]] or [(px, py)]


def _gate_sides(d: dict) -> set:
    used = set()
    for e in d["ExitDatas"]:
        for c in {(e["gridPosition"]["x"], e["gridPosition"]["y"])} | {(e["gridPosition"]["x"] + o["x"], e["gridPosition"]["y"] + o["y"]) for o in e["shapeOffsets"]}:
            used.add((c, e["direction"]))
    return used


def add_colour(d: dict, new: str) -> tuple[dict | None, str]:
    """One block of the commonest colour becomes `new` and gets a gate of its own: the first rim window (an edge of the
    active area facing out, as wide as the block's span on that side, nearest the block) the solver accepts. (level,
    note) or (None, why)."""
    from .level import ExitDirection
    counts: dict = {}
    for blk in d["GridBlockDatas"]:
        counts[blk["blockColor"]] = counts.get(blk["blockColor"], 0) + 1
    if B.COLOURS.index(new) in counts:
        return None, f"the board already has {B.COLOUR_WORDS[new]} blocks"
    active = _active(d)
    used = _gate_sides(d)
    vec = {0: (-1, 0), 1: (1, 0), 2: (0, 1), 3: (0, -1)}
    order = sorted(range(len(d["GridBlockDatas"])), key=lambda i: (-counts[d["GridBlockDatas"][i]["blockColor"]], i))
    for i in order:
        blk = d["GridBlockDatas"][i]
        if counts[blk["blockColor"]] < 2:
            continue  # the old colour must keep a block, or a colour is only renamed
        cells = _block_cells(blk)
        cx = sum(c[0] for c in cells) / len(cells)
        cy = sum(c[1] for c in cells) / len(cells)
        windows = []
        for direction, (dx, dy) in vec.items():
            span = sorted({c[1] for c in cells}) if direction in (0, 1) else sorted({c[0] for c in cells})
            width = len(span)
            edge = [c for c in active if (c[0] + dx, c[1] + dy) not in active]
            for c in edge:
                run = [(c[0], c[1] + k) if direction in (0, 1) else (c[0] + k, c[1]) for k in range(width)]
                if all(r in active and (r[0] + dx, r[1] + dy) not in active and (r, direction) not in used for r in run):
                    dist = abs(c[0] - cx) + abs(c[1] - cy)
                    windows.append((dist, direction, run))
        windows.sort(key=lambda w: (w[0], w[1]))
        for _, direction, run in windows[:24]:
            trial = copy.deepcopy(d)
            trial["GridBlockDatas"][i]["blockColor"] = B.COLOURS.index(new)
            x0, y0 = run[0]
            trial["ExitDatas"].append({"exitNumber": 0, "requiredColor": B.COLOURS.index(new), "gridPosition": {"x": x0, "y": y0},
                                       "direction": direction, "shapeOffsets": [{"x": x - x0, "y": y - y0} for x, y in run]})
            ok, why = solvable(trial)
            if ok:
                old = B.COLOUR_WORDS[B.COLOURS[blk["blockColor"]]]
                side = {0: "left", 1: "right", 2: "top", 3: "bottom"}[direction]
                return trial, (f"one {old} block (at column {x0 + 1}, row {y0 + 1} from the bottom-left) becomes {B.COLOUR_WORDS[new]} "
                               f"and gets a {B.COLOUR_WORDS[new]} gate on the {side} edge; the board still solves in {why}")
    return None, f"no block could become {B.COLOUR_WORDS[new]} with a gate of its own and keep the board solvable"


def remove_colour(d: dict, which: str | None = None) -> tuple[dict | None, str]:
    """One colour fewer: a colour's blocks and gates become another colour, so the geometry stays. The rarest colour into
    the commonest first, then every other pair (S2, 2026-10-19: yellow into red left the candy ring unsolvable, blue into
    red did not); a merge the solver refuses gets the gate repair before the next pair is tried. (level, note) or (None, why)."""
    counts: dict = {}
    for blk in d["GridBlockDatas"]:
        counts[blk["blockColor"]] = counts.get(blk["blockColor"], 0) + 1
    if len(counts) < 3:
        return None, "the board has two colours; one fewer would leave a single colour"
    if which and B.COLOURS.index(which) not in counts:
        return None, f"the board has no {B.COLOUR_WORDS[which]} blocks"
    gones = [B.COLOURS.index(which)] if which else sorted(counts, key=lambda k: (counts[k], k))
    tried = []
    for gone in gones:
        for into in sorted((k for k in counts if k != gone), key=lambda k: (-counts[k], k)):
            out = recolour(d, B.COLOURS[gone], B.COLOURS[into])
            ok, why = solvable(out, REPAIR_STATES)
            words = f"the {B.COLOUR_WORDS[B.COLOURS[gone]]} blocks and their gates become {B.COLOUR_WORDS[B.COLOURS[into]]} ({counts[gone]} block(s))"
            if ok:
                return out, f"{words}; the board still solves in {why}"
            if "gave up" not in why:
                fixed, note = repair(out)
                if fixed is not None:
                    return fixed, f"{words}; that alone cannot be played, so {note}"
            tried.append(f"{B.COLOUR_WORDS[B.COLOURS[gone]]} into {B.COLOUR_WORDS[B.COLOURS[into]]}")
    return None, "no merge of one colour into another leaves a board that can be played (tried " + ", ".join(tried) + ")"


def _block_span(cells: list, direction: int) -> int:
    xs, ys = {c[0] for c in cells}, {c[1] for c in cells}
    return len(ys) if direction in (0, 1) else len(xs)


def _gate_cells(e: dict) -> set:
    return {(e["gridPosition"]["x"], e["gridPosition"]["y"])} | {(e["gridPosition"]["x"] + o["x"], e["gridPosition"]["y"] + o["y"]) for o in e["shapeOffsets"]}


def stranded(d: dict) -> list[tuple[int, str]]:
    """Blocks no gate of their colour is wide enough for (the game lets a block out only through a gate as wide as the
    block's span on that side): [(block index, why)]."""
    out = []
    for i, blk in enumerate(d["GridBlockDatas"]):
        cells = _block_cells(blk)
        fits = False
        for e in d["ExitDatas"]:
            if e["requiredColor"] != blk["blockColor"]:
                continue
            if len(_gate_cells(e)) >= _block_span(cells, e["direction"]):
                fits = True
                break
        if not fits:
            name = B.COLOUR_WORDS[B.COLOURS[blk["blockColor"]]]
            out.append((i, f"the {name} block of {len(cells)} cells at column {min(c[0] for c in cells) + 1}, row "
                           f"{min(c[1] for c in cells) + 1} (from the bottom-left) fits through no {name} gate"))
    return out


def _windows_for(d: dict, cells: list, active: set, used: set) -> list:
    """Outer-edge windows a block of these cells could leave through, nearest first: [(distance, direction, run)]."""
    vec = {0: (-1, 0), 1: (1, 0), 2: (0, 1), 3: (0, -1)}
    cx = sum(c[0] for c in cells) / len(cells)
    cy = sum(c[1] for c in cells) / len(cells)
    out = []
    for direction, (dx, dy) in vec.items():
        width = _block_span(cells, direction)
        edge = [c for c in active if (c[0] + dx, c[1] + dy) not in active]
        for c in edge:
            run = [(c[0], c[1] + k) if direction in (0, 1) else (c[0] + k, c[1]) for k in range(width)]
            if all(r in active and (r[0] + dx, r[1] + dy) not in active and (r, direction) not in used for r in run):
                out.append((abs(c[0] - cx) + abs(c[1] - cy), direction, run))
    out.sort(key=lambda w: (w[0], w[1]))
    return out


def repair(d: dict, tries: int = 24) -> tuple[dict | None, str]:
    """The smallest gate repair that makes a board drawn unplayable playable (2026-10-19: the T1 render's red 3x2 fits
    through no red gate): first a gate for each stranded block on the nearest outer edge it fits, then, when the board
    still has no solution, one more gate for one block at a time (nearest edges first, `tries` solver runs in all).
    (level, what was changed) or (None, why)."""
    active = _active(d)
    cur = copy.deepcopy(d)
    notes = []
    for i, why in stranded(cur):
        blk = cur["GridBlockDatas"][i]
        cells = _block_cells(blk)
        for _, direction, run in _windows_for(cur, cells, active, _gate_sides(cur))[:8]:
            trial = copy.deepcopy(cur)
            x0, y0 = run[0]
            trial["ExitDatas"].append({"exitNumber": 0, "requiredColor": blk["blockColor"], "gridPosition": {"x": x0, "y": y0}, "direction": direction,
                                       "shapeOffsets": [{"x": x - x0, "y": y - y0} for x, y in run]})
            if all(j != i for j, _ in stranded(trial)):
                cur = trial
                side = {0: "left", 1: "right", 2: "top", 3: "bottom"}[direction]
                notes.append(f"{why}: a {B.COLOUR_WORDS[B.COLOURS[blk['blockColor']]]} gate of {len(run)} cells is added on the {side} edge")
                break
    ok, how = solvable(cur, REPAIR_STATES)
    if ok:
        return cur, "; ".join(notes) + f"; the board then solves in {how}" if notes else f"solvable in {how}"
    if "gave up" in how:
        return None, ("; ".join(notes) + "; " if notes else "") + how
    budget = tries
    for i, blk in sorted(enumerate(cur["GridBlockDatas"]), key=lambda t: -len(_block_cells(t[1]))):
        cells = _block_cells(blk)
        for _, direction, run in _windows_for(cur, cells, active, _gate_sides(cur))[:4]:
            if budget <= 0:
                break
            trial = copy.deepcopy(cur)
            x0, y0 = run[0]
            trial["ExitDatas"].append({"exitNumber": 0, "requiredColor": blk["blockColor"], "gridPosition": {"x": x0, "y": y0}, "direction": direction,
                                       "shapeOffsets": [{"x": x - x0, "y": y - y0} for x, y in run]})
            budget -= 1
            ok, how = solvable(trial, REPAIR_STATES)
            if "gave up" in how:
                return None, how
            if ok:
                side = {0: "left", 1: "right", 2: "top", 3: "bottom"}[direction]
                notes.append(f"the board as drawn has no solution: a {B.COLOUR_WORDS[B.COLOURS[blk['blockColor']]]} gate of {len(run)} cells is "
                             f"added on the {side} edge; the board then solves in {how}")
                return trial, "; ".join(notes)
    return None, ("; ".join(notes) + "; " if notes else "") + f"no single added gate makes it playable ({how})"


def min_drags(d: dict, max_states: int = REPAIR_STATES) -> int | None:
    from .level import level_from_dict
    from .solver import SolverLimitError, solve_fast
    try:
        sol = solve_fast(level_from_dict(d, name="x"), max_states=max_states)
    except (SolverLimitError, ValueError):
        return None
    return sol.min_drags if sol else None


def remove_blocks(d: dict, n: int, easier: bool = False, names: dict | None = None) -> tuple[dict | None, str]:
    """Fewer blocks on a copied board (2026-10-19, the owner's video creative "use fewer blocks"): n blocks taken off one at
    a time, each the smallest block whose colour keeps another block (so every colour keeps its door and every door a block,
    level.door_problems) and whose removal keeps the board solvable; when every colour is down to one block, a whole colour
    goes with its doors, said. easier: of the blocks that can go, the one that lowers the solver's minimum most.
    (level, note) or (None, why)."""
    from collections import Counter
    out, removed = copy.deepcopy(d), []
    for _ in range(max(0, n)):
        blocks = out["GridBlockDatas"]
        if len(blocks) <= 2:
            break
        counts = Counter(b["blockColor"] for b in blocks)
        cands = [i for i, b in enumerate(blocks) if counts[b["blockColor"]] > 1] or list(range(len(blocks)))
        cands.sort(key=lambda i: (len(_block_cells(blocks[i])), i))  # the smallest first: the design stays recognisable
        best = None
        for i in cands[:8]:
            trial = copy.deepcopy(out)
            blk = trial["GridBlockDatas"].pop(i)
            last = counts[blk["blockColor"]] == 1
            if last:  # the colour's last block: its doors go with it (no door without a block)
                trial["ExitDatas"] = [e for e in trial["ExitDatas"] if e["requiredColor"] != blk["blockColor"]]
            ok, _ = solvable(trial, REPAIR_STATES)
            if not ok:
                continue
            if easier:
                m = min_drags(trial)
                score = m if m is not None else 999
                if best is None or score < best[0]:
                    best = (score, trial, blk, last)
            else:
                best = (0, trial, blk, last)
                break
        if best is None:
            break
        _, out, blk, last = best
        cells = _block_cells(blk)
        w, h = len({c[0] for c in cells}), len({c[1] for c in cells})
        slot = B.COLOURS[blk["blockColor"]]
        own = f" ({names[slot]} in the reference)" if names and names.get(slot) else ""
        removed.append(f"a {w}x{h} {B.COLOUR_WORDS[slot]}{own}" + (" (and its door: it was the colour's last)" if last else ""))
    if not removed:
        return None, "no block can be taken off and keep the board playable"
    note = (f"{len(removed)} block{'s' if len(removed) != 1 else ''} fewer than the reference's board ({len(d['GridBlockDatas'])} -> "
            f"{len(out['GridBlockDatas'])}): " + ", ".join(removed) + "; every colour left keeps a door")
    if easier:
        a, b = min_drags(d), min_drags(out)
        note = f"easier, as asked: {note}" + (f"; the solve takes {b} drags instead of {a}" if a is not None and b is not None else "")
    if len(removed) < n:
        note += f" (only {len(removed)} of the {n} asked could go and keep the board playable)"
    return out, note


def add_blocker(d: dict, tries: int = 30, harder: bool = True) -> tuple[dict | None, str]:
    """"Harder: one more block in the way" on a copied board (S10, 2026-10-19): a one-cell block of a colour already on
    the board is placed on an empty cell (never on a gate's cells), the first placement that keeps the board solvable and
    needs more drags than before. (level, note) or (None, why)."""
    base = min_drags(d)
    if base is None:
        return None, "the board's own solution could not be settled in time"
    active = _active(d)
    taken = {c for blk in d["GridBlockDatas"] for c in _block_cells(blk)}
    gate_cells = {c for e in d["ExitDatas"] for c in _gate_cells(e)}
    counts: dict = {}
    for blk in d["GridBlockDatas"]:
        counts[blk["blockColor"]] = counts.get(blk["blockColor"], 0) + 1
    colours = sorted(counts, key=lambda k: (-counts[k], k))
    cx = sum(c[0] for c in taken) / max(1, len(taken))
    cy = sum(c[1] for c in taken) / max(1, len(taken))
    empties = sorted(active - taken - gate_cells, key=lambda c: abs(c[0] - cx) + abs(c[1] - cy))  # the middle first: more in the way
    budget = tries
    for cell in empties:
        for colour in colours[:3]:
            if budget <= 0:
                break
            trial = copy.deepcopy(d)
            trial["GridBlockDatas"].append({"gridPosition": {"x": cell[0], "y": cell[1]}, "blockColor": colour, "shapeOffsets": [{"x": 0, "y": 0}]})
            budget -= 1
            n = min_drags(trial)
            if n is not None and (n > base or (not harder and n >= base)):
                return trial, (f"one more {B.COLOUR_WORDS[B.COLOURS[colour]]} block (one cell, at column {cell[0] + 1}, row {cell[1] + 1} from the "
                               f"bottom-left)" + (f" is in the way: the solve takes {n} drags instead of {base}" if n > base else
                                                  f" added; the solve still takes {n} drags"))
    return None, (f"no single added block makes the board harder and keeps it solvable ({tries} placements tried)" if harder else
                  f"no single added block keeps the board solvable ({tries} placements tried)")


def add_blocks(d: dict, n: int) -> tuple[dict | None, str]:
    """More blocks on a copied board (2026-10-19): n one-cell blocks added one at a time where the board stays solvable
    (add_blocker without the 'harder' demand). (level, note) or (None, why)."""
    out, notes = d, []
    for _ in range(max(0, n)):
        nxt, note = add_blocker(out, harder=False)
        if nxt is None:
            break
        out, notes = nxt, notes + [note]
    if not notes:
        return None, "no block can be added and keep the board playable"
    return out, (f"{len(notes)} block{'s' if len(notes) != 1 else ''} more than the reference's board ({len(d['GridBlockDatas'])} -> "
                 f"{len(out['GridBlockDatas'])}): " + "; ".join(notes) + (f" (only {len(notes)} of the {n} asked fit)" if len(notes) < n else ""))


def same_board(a: dict, b: dict) -> tuple[bool, str]:
    """Whether two level files are the same board: the grid, the holes, every block's cells and colour, every gate's
    cells, colour and direction. (same, what differs)."""
    def norm(d):
        blocks = sorted((tuple(sorted(_block_cells(x))), x["blockColor"]) for x in d["GridBlockDatas"])
        gates = sorted((tuple(sorted({(e["gridPosition"]["x"], e["gridPosition"]["y"])} | {(e["gridPosition"]["x"] + o["x"], e["gridPosition"]["y"] + o["y"]) for o in e["shapeOffsets"]})),
                        e["requiredColor"], e["direction"]) for e in d["ExitDatas"])
        return (d["gridWidth"], d["gridHeight"]), sorted((c["x"], c["y"]) for c in d["inactiveCells"]), blocks, gates
    na, nb = norm(a), norm(b)
    if na == nb:
        return True, "the same grid, holes, blocks and gates"
    diffs = []
    for i, what in enumerate(("grid", "holes", "blocks", "gates")):
        if na[i] != nb[i]:
            diffs.append(what)
    return False, "differs in " + ", ".join(diffs)


def describe(d: dict) -> str:
    from .audit import made_shape
    cols = colours_of(d)
    shape = (made_shape(d) or "open").replace("_", " ")
    return (f"{shape} {d['gridWidth']}x{d['gridHeight']}, {len(d['GridBlockDatas'])} blocks in "
            + ", ".join(B.COLOUR_WORDS[c] for c in cols) + f", {len(d['ExitDatas'])} gates"
            + (f", {len(d['inactiveCells'])} hole cells" if d["inactiveCells"] else ""))


def save(d: dict, folder: Path | None = None) -> Path:
    """The level under studio/levels/picture_<hash>.json (the same board gives the same file)."""
    from . import studio
    folder = folder or (studio.STUDIO / "levels")
    folder.mkdir(parents=True, exist_ok=True)
    text = json.dumps(d, indent=2)
    path = folder / f"picture_{hashlib.sha256(text.encode()).hexdigest()[:12]}.json"
    if not path.is_file():
        path.write_text(text)
    return path
