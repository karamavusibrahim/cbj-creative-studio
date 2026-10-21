"""Image-guided creative generation (brief p.6): what an attached image is FOR, and what it gives.

The brief lists four roles for an image: a visual reference, an asset to insert, a style or
composition reference, and an input for modifying an existing creative. The tool decides the role
from the request's words and from what the multimodal model saw (reference.analyse), and then
takes from the image exactly what that role needs, in code:
- style (design transfer): a style kit measured from the image's palette: the background behind
  the board, the captions' fill and outline (contrast-checked against that background), the
  blocks' colours mapped to the game's seven slots by hue when the request wants the blocks or the
  whole look repainted, and the end card's gradient (which follows the background);
- composition ("a game like this", "a level like this board"): the board the model read in the
  image (grid, block count, colours, crowdedness, walls, symmetry) becomes the level spec, and a
  similar level is generated in that spirit (the exact layout is not copied: doors and solvability
  are the generator's job, and the plan says so);
- asset: the picture is placed (logo, sticker, end card, button, cursor; planner rules);
- modify: the picture replaces the obstacle on the walls or becomes a block's texture (planner rules).
An image can have two roles at once ("inspired by this image, and put its logo on the end card").
"""

from __future__ import annotations

import colorsys
import re

from . import brief as B

STYLE_WORDS = re.compile(r"\b(style|styled|look|looks|palette|colou?rs? (of|from|like)|inspired|inspiration|mood|vibe|feel|"
                         r"theme|themed|design transfer|style transfer|same (style|look|colou?rs|palette|design)|"
                         r"in the style of|like this (image|picture|photo|art|artwork|illustration)|match(ing)? (this|the) (image|picture|photo)|"
                         r"aesthetic|visual(ly)? (like|similar)|based on this (image|picture|photo))\b", re.I)
COMPOSITION_WORDS = re.compile(r"\b(a (game|level|board|puzzle) like (this|that|the (image|picture|screenshot))|"
                               r"(level|board|puzzle|layout|arrangement) (like|similar to|based on|from|of) (this|that|the) (image|picture|screenshot|board|game)?|"
                               r"recreate (this|the) (board|level|puzzle|layout)|copy (this|the) (board|level|layout)|"
                               r"same (board|layout|arrangement)|like (this|that) (board|puzzle|level|game)|"
                               r"similar (board|level|puzzle|game)|this (board|puzzle|level) (as|in) (a|the))\b", re.I)
BLOCK_WORDS = re.compile(r"\b(blocks?|pieces?|tiles?|whole look|entire look|all the colou?rs|design transfer|"
                         r"the game'?s? colou?rs|recolou?r|(repaint|restyle|recolou?r)\s+everything)\b", re.I)  # "keep everything else" is not a repaint
KEEP_BLOCKS = re.compile(r"\b(keep|leave|preserve|original|game'?s own|standard|unchanged)\b[^.;,]{0,25}\b(block|piece)s?\b[^.;,]{0,20}\b(colou?rs?|look)\b|"
                         r"\b(block|piece)s? (colou?rs? )?(stay|stays|unchanged|as (they are|is))\b", re.I)
BACKGROUND_ONLY = re.compile(r"\b(background|backdrop)\b", re.I)
GAME_SLOT_HUE = {"Red": 4, "Orange": 30, "Yellow": 48, "Green": 121, "DarkGreen": 128, "Blue": 213, "Purple": 290}
CROWD_STYLE = {"packed": "packed", "crowded": "packed", "dense": "packed", "spacious": "spacious", "sparse": "spacious",
               "open": "spacious", "roomy": "spacious"}
COLOUR_SLOT = {"red": "Red", "crimson": "Red", "rose": "Red", "pink": "Red", "hot pink": "Red", "light pink": "Red",
               "orange": "Orange", "tangerine": "Orange", "peach": "Orange", "brown": "Orange",
               "yellow": "Yellow", "lemon": "Yellow", "butter": "Yellow", "gold": "Yellow",
               "green": "Green", "lime": "Green", "mint": "Green", "sage": "DarkGreen", "dark green": "DarkGreen", "teal": "DarkGreen",
               "blue": "Blue", "sky blue": "Blue", "cyan": "Blue", "navy": "Blue",
               "purple": "Purple", "violet": "Purple", "lilac": "Purple", "grape": "Purple", "magenta": "Purple"}


# ---------- colour maths ----------

def _rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _hex(rgb) -> str:
    return "#%02X%02X%02X" % tuple(max(0, min(255, int(round(c)))) for c in rgb)


def _hls(h: str) -> tuple[float, float, float]:
    r, g, b = (c / 255 for c in _rgb(h))
    hh, ll, ss = colorsys.rgb_to_hls(r, g, b)
    return hh * 360, ll, ss


def luminance(h: str) -> float:
    """Relative luminance 0-1 (sRGB)."""
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = _rgb(h)
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _lighten(h: str, amount: float) -> str:
    hh, ll, ss = _hls(h)
    r, g, b = colorsys.hls_to_rgb(hh / 360, min(1.0, ll + amount * (1 - ll)), ss)
    return _hex((r * 255, g * 255, b * 255))


def _darken(h: str, amount: float) -> str:
    hh, ll, ss = _hls(h)
    r, g, b = colorsys.hls_to_rgb(hh / 360, ll * (1 - amount), ss)
    return _hex((r * 255, g * 255, b * 255))


def _hue_distance(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)


# ---------- the role ----------

def _words(prompt: str) -> str:
    """The request without the game's name ("Color Block Jam" would read as talk about blocks)."""
    return re.sub(r"\bcolou?r[\s-]*block[\s-]*jam\b", " ", prompt or "", flags=re.I)


def role(prompt: str, analysis: dict | None = None, edit: bool = False) -> dict:
    """What an attached image is for: flags style / composition / asset / modify and the primary
    role, from the request's words and the model's reading (kind: logo, character, game screenshot...)."""
    from .reference import asks_placement, is_reference_prompt
    notes = (analysis or {}).get("notes") or {}
    kind = str(notes.get("kind") or "").lower()
    board = notes.get("board") or {}
    text = _words(prompt)
    composition = bool(COMPOSITION_WORDS.search(text)) or (bool(board.get("is_puzzle_board")) and
                                                          re.search(r"\b(like (this|that)|similar|recreate|same|based on)\b", text, re.I) is not None)
    style = bool(STYLE_WORDS.search(text)) and not composition or (is_reference_prompt(text, edit=edit) and not composition
                                                                   and kind not in ("logo",) and not asks_placement(text))
    modify = bool(re.search(r"\b(instead of|replace|swap|on the walls|the obstacle|texture|skin|on the \w+ block)\b", text, re.I)) and \
        bool(re.search(r"\b(this|the attached|attached|uploaded)\b", text, re.I))
    asset = (asks_placement(text) or kind in ("logo",) and re.search(r"\b(logo|our|brand)\b", text, re.I) is not None) and not modify
    if composition and (kind in ("photo", "illustration", "character", "pattern") and not board.get("is_puzzle_board")):
        # "a game like this" with a picture that is not a board: the look is what can be taken
        composition, style = False, True
    flags = {"style": style, "composition": composition, "asset": asset, "modify": modify}
    primary = next((k for k in ("modify", "composition", "asset", "style") if flags[k]), None)
    if primary is None and analysis is not None:
        primary = "style" if kind not in ("logo",) else "asset"
        flags[primary] = True
    return {**flags, "primary": primary, "kind": kind}


# ---------- the style kit ----------

def style_kit(analysis: dict, prompt: str = "") -> dict:
    """The look an image gives, measured from its palette: {background: [top, bottom], caption_fill,
    caption_outline, blocks: [{slot, hex, name}], end_gradient, theme, taken: [...]} ."""
    from .reference import colour_name
    pal = [p for p in (analysis.get("palette") or []) if p.get("hex")]
    notes = analysis.get("notes") or {}
    extra = [h for h in (notes.get("dominant_colours") or []) if isinstance(h, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", h)]
    if not pal and extra:
        pal = [{"hex": h.upper(), "name": colour_name(h.upper()), "share": 1 / len(extra)} for h in extra]
    if not pal:
        return {"background": [], "caption_fill": None, "caption_outline": None, "blocks": [], "end_gradient": None,
                "theme": "game", "taken": [], "note": "no colours could be measured in the image"}
    pal = sorted(pal, key=lambda p: -p.get("share", 0))
    mean_l = sum(luminance(p["hex"]) * p.get("share", 1) for p in pal) / max(1e-6, sum(p.get("share", 1) for p in pal))
    dark = mean_l < 0.18
    # the background: the two most dominant soft colours (low saturation or high lightness), lighter at the
    # top; on a dark image the two darkest dominant ones
    soft = [p for p in pal if (_hls(p["hex"])[2] < 0.45 or _hls(p["hex"])[1] > 0.7)] or pal
    if dark:
        soft = sorted(pal, key=lambda p: luminance(p["hex"]))[:2]
        top, bottom = _lighten(soft[0]["hex"], 0.08), soft[-1]["hex"]
    else:
        base = soft[0]["hex"]
        second = next((p["hex"] for p in soft[1:] if _hue_distance(_hls(p["hex"])[0], _hls(base)[0]) < 60), None)
        top = _lighten(base, 0.55 if luminance(base) < 0.6 else 0.25)
        bottom = _lighten(second, 0.2) if second else _lighten(base, 0.15)
        if luminance(top) < luminance(bottom):
            top, bottom = bottom, top
    background = [top, bottom]
    # captions: white on a dark background, the darkest palette colour as the outline; on a light
    # background the most saturated dark colour as the fill with a white outline, if it reads
    darkest = min(pal, key=lambda p: luminance(p["hex"]))["hex"]
    if luminance(bottom) < 0.35:
        fill, outline = "#FFFFFF", _darken(darkest, 0.3)
    else:
        cands = sorted(pal, key=lambda p: (-_hls(p["hex"])[2], luminance(p["hex"])))
        pick = next((p["hex"] for p in cands if contrast(p["hex"], top) >= 3.0 and luminance(p["hex"]) < 0.5), None)
        fill, outline = (pick, "#FFFFFF") if pick else ("#FFFFFF", _darken(darkest, 0.4))
        if contrast(fill, top) < 3.0 and fill == "#FFFFFF":
            fill, outline = _darken(darkest, 0.5), "#FFFFFF"
    # blocks: the saturated colours, distinct in hue, mapped to the nearest game slots
    sat = [p for p in pal if _hls(p["hex"])[2] >= 0.35 and 0.15 <= _hls(p["hex"])[1] <= 0.85]
    blocks, used = [], set()
    for p in sat:
        hue = _hls(p["hex"])[0]
        slot = min((s for s in GAME_SLOT_HUE if s not in used), key=lambda s: _hue_distance(hue, GAME_SLOT_HUE[s]), default=None)
        if slot is None or _hue_distance(hue, GAME_SLOT_HUE[slot]) > 55:
            continue
        if any(_hue_distance(hue, _hls(b["hex"])[0]) < 25 for b in blocks):
            continue  # two blocks of one hue would be told apart only by shade
        used.add(slot)
        blocks.append({"slot": slot, "hex": p["hex"].upper(), "name": colour_name(p["hex"])})
    words = _words(prompt)
    wants_blocks = bool(BLOCK_WORDS.search(words)) and not KEEP_BLOCKS.search(words)
    if not wants_blocks or len(blocks) < 2:
        blocks = []
    captions_too = not BACKGROUND_ONLY.search(words) or re.search(r"\bcaptions?\b", words, re.I) is not None
    taken = [f"background {top} to {bottom}"]
    if captions_too:
        taken.append(f"captions {fill} with a {outline} outline")
    if blocks:
        taken.append("blocks " + ", ".join(f"{b['slot'].lower()} as {b['name']} {b['hex']}" for b in blocks))
    return {"background": background, "caption_fill": fill, "caption_outline": outline, "blocks": blocks,
            "end_gradient": [bottom, top] if not dark else [top, bottom], "theme": "custom", "taken": taken,
            "dark": dark, "wants_blocks": wants_blocks, "block_candidates": len(sat), "captions": captions_too}


# ---------- the board in a picture ----------

def board_facts(analysis: dict) -> dict | None:
    """The level fields a board seen in an image gives: {width, height, blocks, colours, style,
    shape, note} or None when the model saw no puzzle board."""
    notes = analysis.get("notes") or {}
    b = notes.get("board") or {}
    if not b or not b.get("is_puzzle_board"):
        return None
    out: dict = {}
    cols, rows = b.get("grid_cols"), b.get("grid_rows")
    if isinstance(cols, int) and isinstance(rows, int) and 3 <= cols <= 9 and 3 <= rows <= 10:
        out["width"], out["height"] = cols, rows
    n = b.get("block_count")
    if isinstance(n, int) and 2 <= n <= 10:
        out["blocks"] = n
    elif isinstance(n, int) and n > 10:
        out["blocks"] = 10
    colours = []
    for c in b.get("block_colours") or []:
        slot = COLOUR_SLOT.get(str(c).lower().strip())
        if slot and slot not in colours:
            colours.append(slot)
    if colours:
        out["colours"] = colours[:7]
    style = []
    crowd = CROWD_STYLE.get(str(b.get("crowded") or "").lower())
    if crowd:
        style.append(crowd)
    if b.get("symmetric"):
        style.append("symmetric")
    out["style"] = style
    walls = b.get("walls")
    out["shape"] = "holes" if isinstance(walls, int) and walls > 0 else "open"
    desc = (f"{out['width']}x{out['height']}" if "width" in out else "a board") + \
        (f", {out['blocks']} blocks" if "blocks" in out else "") + \
        (f" in {', '.join(c.lower() for c in out['colours'])}" if colours else "") + \
        (f", {crowd}" if crowd else "") + (", mirror-symmetric" if b.get("symmetric") else "") + \
        (f", {walls} wall cell(s)" if isinstance(walls, int) and walls > 0 else "")
    out["note"] = desc
    return out


# ---------- applying it to the brief ----------

def apply(brief: dict, prompt: str, analyses: list[dict], current: dict | None = None) -> list[dict]:
    """Give each analysed image its role and take what the role needs into the brief. Returns the
    roles (kept in planner.references[i]["role"]) for the UI."""
    roles = []
    for a in analyses:
        if a.get("kind") != "image" or a.get("error"):
            roles.append(None)
            continue
        r = role(prompt, a, edit=current is not None)
        r["file"] = a["file"]
        taken = []
        if r["style"]:
            kit = style_kit(a, prompt)
            vs = brief["visuals"]
            if kit["background"]:
                vs["background"] = kit["background"]
                vs["theme"] = "custom"
                _changed(brief, "visuals.background")
                if kit.get("captions", True):
                    vs["caption_fill"], vs["caption_outline"] = kit["caption_fill"], kit["caption_outline"]
                    _changed(brief, "visuals.captions")
                if kit["blocks"]:
                    vs["blocks"] = kit["blocks"]
                    _changed(brief, "visuals.colours")
                elif kit.get("wants_blocks") and kit.get("block_candidates", 0) < 2:
                    taken.append("the image has too few distinct block colours to repaint the blocks, so they keep the game's own")
                taken = kit["taken"] + taken
                row = B.control(brief, "visuals")
                row["asked"] = row["asked"] or prompt.strip()
                row["plan"] = f"the look is taken from {a['file']}: " + "; ".join(kit["taken"]) + \
                    ("" if kit["blocks"] else "; the blocks keep the game's own colours")
                if row["status"] in ("default", "not_supported"):
                    row["status"] = "applied"
                row["why"] = None
            else:
                taken.append(kit.get("note") or "no colours could be measured")
        if r["composition"]:
            facts = board_facts(a)
            lv = brief["level"]
            if facts:
                lv["source"] = "generate"
                for k in ("width", "height", "blocks"):
                    if k in facts:
                        lv[k] = facts[k]
                if facts.get("colours"):
                    lv["colours"] = facts["colours"]
                if facts.get("style"):
                    lv["style"] = list(dict.fromkeys(list(lv.get("style") or []) + facts["style"]))
                if facts.get("shape") == "holes" and lv["shape"] in ("any", "open"):
                    lv["shape"] = "holes"
                for g in ("level.source", "level.size", "level.blocks", "level.colours", "level.style", "level.shape"):
                    _changed(brief, g)
                taken.append(f"a level like the board in the picture: {facts['note']} (a similar level is generated in that "
                             f"spirit; the exact layout, doors and solution are the generator's, so the puzzle is playable)")
                row = B.control(brief, "level")
                row["asked"] = row["asked"] or prompt.strip()
                row["plan"] = f"a level like the board in {a['file']}: {facts['note']}; generated in that spirit, not copied cell by cell."
                if row["status"] in ("default", "not_supported"):
                    row["status"] = "applied"
                row["why"] = None
            else:
                taken.append("no puzzle board could be read in the picture, so the level is planned from the words")
                B.adjust(brief, "level", f"{a['file']} shows no board the tool could read (the model saw "
                                         f"{(a.get('notes') or {}).get('subject') or 'something else'}); the level follows the words of the request.")
        r["taken"] = taken
        roles.append(r)
        if taken:
            line = f"{a['file']} is used as a {_role_words(r)}: " + "; ".join(taken)
            if line not in brief["assumptions"]:
                brief["assumptions"].append(line)
    return roles


def _role_words(r: dict) -> str:
    names = [w for k, w in (("modify", "picture that modifies the creative"), ("composition", "board reference"),
                            ("asset", "picture to place"), ("style", "style reference")) if r.get(k)]
    return " and a ".join(names) if names else "reference"


def _changed(brief: dict, group: str) -> None:
    if group not in brief["changed"]:
        brief["changed"].append(group)
