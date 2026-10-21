"""What a reference picture gives a new creative, decided and applied in code (core requirement 3, rules I1, I2, I4-I11;
2026-10-17). The picture has been read first (imageread.read); the planner has planned the brief from the words alone
(it sees only what the picture shows and its role, never the board's numbers, the palette or the captions' text). Then:

1. the role (decide): from the words AND the reading together, a picture is a `style` reference (the look: the
   background, the captions, the blocks' colours only when asked), a `board` reference (the level's type from a board
   in the picture), an `asset` (placed: the planner's placement rules) or a `modify` input (on the walls, a block's
   skin). It can have two roles. A request that names nothing about the picture ("inspired by this image") reads it for
   its concept: a board screenshot gives its board and its look, any other picture its look only (I1). "Only X" takes
   X alone; "keep the game's own ..." keeps it (I5).
2. the board (board_spec): each part (shape, size, blocks, colours, pieces, packed, symmetric) the words name is taken;
   with the board role, every other part the words leave open is filled from the picture and marked "filled from the
   image" (its rows are info); a value the request states itself is never replaced (I4). What the generator cannot
   build is clamped and said: "<seen> -> <built>: <why>" (I8). The board is counted on the board, never from a caption (I7).
3. the colours (colour_map): every block colour read goes to the nearest free slot of the game's seven RENDERED colours
   (the block materials' _Color), at the least total distance, so two read colours never share a slot; the mapping
   line is shown ("pink -> purple: the game has no pink"). The blocks are repainted (display colours keep the picture's
   hue) only when the request asks for the picture's block colours or its palette on everything (I6).
4. the look (style_kit): the background measured on the picture's margins, the caption fill and outline measured in the
   caption's box, the caption checked for contrast (3:1) against the background it sits on (I6).
5. the screen (I10): the HUD is hidden only when the request asks, or asks for the picture's look as a whole and the
   picture shows none; a badge number goes to the creative only when "the same level number" is asked.
6. never copied (I9): no pixel of the picture outside an asset or modify slot (the background picture slot is cleared),
   no caption text unless quoted or asked for as "the same words", no exact cells; what the game does not have is
   listed "not used: not in Color Block Jam".
apply() writes all of it into the brief, each line into the assumptions and the control rows, and the provenance into
brief["reference"] (file, roles, taken, not taken, colour mapping, clamps, not used), which the UI's reference card and
the image evaluation (imageaudit) read.
"""

from __future__ import annotations

import copy
import itertools
import re

from . import brief as B

# The game's seven block colours as RENDERED (Materials/BlockMaterials/*.mat _Color, ~/Downloads/CBJ, 2026-10-17).
RENDERED = {"Red": "#FF3B2A", "Orange": "#FF8000", "Yellow": "#FFCC04", "Green": "#14FF17", "DarkGreen": "#065C13",
            "Blue": "#146AFF", "Purple": "#D007FD"}
GAME_GROUND = "#ADD1E9"  # GroundMaterial.mat: the game's own background
GAME_CELLS = "#5E6A94"  # gridColors: the board's cells
# The game's own background as the made poster shows it at its margins (audit.poster_background): measured on 23
# versions made with the game's own look, all #E4F0FE (2026-10-17).
GAME_POSTER_BG = "#E4F0FE"
REPAINT_MIN = 25.0  # a read colour this close (brief.colour_distance) to its slot's rendered colour needs no repaint
CAPTION_CONTRAST = 3.0  # a caption's fill or outline against the background it sits on (WCAG large text)
FILLED = "filled from the image (the request left it open)"
NOT_USED = "not used: not in Color Block Jam"
PARTS = ("shape", "size", "blocks", "colours", "pieces", "packed", "symmetric")
STYLE_PARTS = ("background", "captions", "blocks")


def _words(prompt: str) -> str:
    """The request without the game's name ("Color Block Jam" would read as talk about colours and blocks)."""
    return re.sub(r"\bcolou?r[\s-]*block[\s-]*jam\b", " ", prompt or "", flags=re.I)


# ---------- is the picture a reference at all (dispatch, rule I2) ----------

# Words that make an attached picture a reference: the video path's words (reference.REFERENCE_WORDS) and these, which
# name a part of the picture or compare with it. A bare "this image / picture" with placement words ("put this picture on
# the end card") is a picture to place, so it stays in the text workflow.
STRONG_CUES = re.compile(
    r"\binspired by\b|\binspiration\b|\blike (this|that|these|those|the ones?)\b|\bsimilar to\b|"
    r"\b(this|that|the) (image|picture|photo|screenshot|board)'?s\b|"
    r"\b(of|from|in) (this|that|the attached|the uploaded|the) (image|picture|photo|screenshot|board)\b|"
    r"\bas (crowded|full|packed|busy|dense|cramped|big|large|small|symmetric|many \w+) as\b|"
    r"\bsame [^.;]{0,40}\bas (this|that|the)\b|"
    r"\b(take|use|copy|borrow|keep) (only )?(the|its)\b[^.;]{0,40}\b(of|from|in) (this|that|the)\b|"
    r"\bthis (board|screenshot|grid)\b|"
    r"\bits (\w+ )?(look|colou?rs|palette|style|board|mood|vibe|theme|background|captions?)\b", re.I)
DEICTIC = re.compile(r"\b(this|that|the attached|the uploaded) (image|picture|photo|screenshot|pic)\b", re.I)
_DEICTIC_WORDS = {"this image", "this picture"}


def is_image_reference(prompt: str) -> bool:
    """Whether the words make an attached picture a reference (this workflow) rather than a picture to place."""
    from . import reference as R
    text = _words(prompt)
    low = text.lower()
    if STRONG_CUES.search(text):
        return True
    if any(w in low for w in R.REFERENCE_WORDS if w not in _DEICTIC_WORDS):
        return True
    return bool(DEICTIC.search(text)) and not R.asks_placement(text)


# ---------- the role (rules I1, I2, I3, I5) ----------

# "only the background", "the captions only", "everything else stays the game's own" (not "only one second left")
ONLY = re.compile(r"\bonly (the|its|this|their)\b|\b(the|its) \w+( \w+)? only\b|\bjust the\b|\bnothing else\b|"
                  r"\beverything else (stays|is|keeps)\b|\bthe rest (stays|is)\b", re.I)
# the look as a whole (the background and the captions, the blocks only when named), and the colour phrases that name
# the parts themselves ("its colours for the background and the captions")
LOOK_WORDS = re.compile(r"\b(look|looks|style|styled|palette|theme|themed|mood|vibe|aesthetic|feel|design transfer|style transfer)\b", re.I)
COLOUR_PHRASE = re.compile(r"\b(its|their|(the|this|that) (image|picture|photo|screenshot)'?s?) (\w+ )?colou?rs\b|"
                           r"\bcolou?rs (of|from) (this|that|the|its)\b|\bbackground colou?rs\b|"
                           r"\bcolou?rs for the (background|captions?|text)\b", re.I)
KEEP_LOOK = re.compile(r"\b(keep|keeps|keeping|in|on|with|use|stays?)\b[^.;]{0,20}\bthe game'?s (own |standard |original |usual |default )?"
                       r"(look|style|colou?rs|background|palette|theme)\b", re.I)
KEEP_BLOCKS = re.compile(r"\bthe game'?s (own |standard |original )?(block|blocks'?) colou?rs\b|"
                         r"\bkeep[^.;]{0,25}\bblock colou?rs\b|\bblocks? (keep|stay)[^.;]{0,20}\bcolou?rs\b", re.I)
PART_WORDS = {
    "background": re.compile(r"\b(background|backdrop)s?\b", re.I),
    "captions": re.compile(r"\b(captions?|texts?|lettering|titles?)\b", re.I),
    "blocks": re.compile(r"\bthe blocks too\b|\b(on|to) everything\b|\bblock colou?rs\b|\bcolou?rs of the blocks\b|"
                         r"\b(blocks?|pieces?) (too|as well|included)\b|\b\w+ blocks included\b|\brepaint|\brecolou?r", re.I),
}
EVERYTHING = re.compile(r"\b(on|to) everything\b", re.I)
WHOLE = re.compile(r"\binspired by\b|\binspiration\b|\b(ad|creative|video|version|one) like (this|that) (image|picture|photo|screenshot)\b|"
                   r"\blike this (image|picture|photo|screenshot)\b|\bbased on this (image|picture|photo|screenshot)\b", re.I)
SCREEN_WORDS = re.compile(r"\b(its|their|the same|this (image|picture|photo|screenshot)'?s?) (\w+ ){0,2}(look|style|screen|hud)\b|"
                          r"\bsame screen\b", re.I)
LABEL_WORDS = re.compile(r"\bsame level( number)?\b|\bits level( number)?\b|\bsame (badge|level badge)\b", re.I)
BOARD_ALL = re.compile(r"\b(take|use|copy|borrow) (the|its) (board|level|layout|grid)\b|\bsame (board|level|layout)( idea)?\b|"
                       r"\b(board|level|layout|puzzle)( idea)? (like|similar to|based on|from) (this|that|the (one|image|picture|"
                       r"screenshot|board|photo))\b|\b(level|board) like the one\b|\bboard idea\b|"
                       r"\bmatch (this|that|the) (image|picture|photo|screenshot)'?s? board\b|\bmatch its board\b|"
                       r"\b(board|level)\b(?:(?!\bshaped\b)[^.;]){0,40}\blike (this|that) one\b", re.I)  # not "shaped like": the shape
BOARD_PART = {
    "blocks": re.compile(r"\b(same|similar) number of (blocks|pieces)\b|\bas many (blocks|pieces)\b|\b(block|piece) count\b", re.I),
    "packed": re.compile(r"\bas (crowded|full|packed|busy|dense|cramped)\b|\b(crowded|packed|full) like\b", re.I),
    "pieces": re.compile(r"\b(\w+ )?(blocks|pieces|shapes|bars) like (the ones|these|those|this|that|the ones in)\b|"
                         r"\bsame (pieces|block shapes|shapes)\b", re.I),
    "shape": re.compile(r"\b(shaped|shape) like\b|\bsame shape\b|\bsame (board|grid) shape\b|"
                       r"\b(split|divided) into (\w+ )?(separate )?rooms\b|\brooms (split|divided) by walls\b", re.I),
    "size": re.compile(r"\bsame (grid |board )?size\b|\bsame grid\b|\bas (big|large|small) as\b", re.I),
    "colours": re.compile(r"\bsame (block )?colou?rs\b", re.I),
    "symmetric": re.compile(r"\b(mirror[- ]?symmetric\w*|symmetric\w*|mirrored)\b[^.;]{0,30}\blike\b|\bas symmetric as\b|"
                            r"\bsame symmetry\b", re.I),
}
BOARD_TALK = re.compile(r"\b(board|level|grid|rooms?|walls?|layout)\b", re.I)  # not "blocks": "keep the game's block colours"
# a colour count RELATIVE to the picture's ("one more colour", "an extra colour", "two fewer colours", "more colours";
# 2026-10-19: "create a similar game concept, just use one more color" got the picture's three colours, the +1 lost)
RELATIVE_COLOURS = re.compile(r"\b(?:(?P<n1>one|two|three|an?|1|2|3)\s+(?P<w1>more|extra|additional|fewer|less)\s+(?:block\s+)?colou?rs?"
                              r"|(?P<n2>one|two|three|1|2|3)\s+(?:block\s+)?colou?rs?\s+(?P<w2>more|less|fewer)"
                              r"|(?P<w3>more|fewer|less)\s+(?:block\s+)?colou?rs"
                              r"|(?P<w4>remove|drop|take away|lose|without)\s+(?P<n4>one|two|a|an|1|2)\s+(?:of the\s+|block\s+)?colou?rs?"
                              r"|(?P<w5>add|with)\s+(?P<n5>one|two|a|an|1|2)\s+(?:more\s+|extra\s+|new\s+)(?:block\s+)?colou?rs?)\b", re.I)
_COUNT_WORDS = {"a": 1, "an": 1, "one": 1, "1": 1, "two": 2, "2": 2, "three": 3, "3": 3}


def relative_colours(prompt: str) -> int | None:
    """+n / -n when the request asks for n more or fewer colours than the picture has; None otherwise."""
    m = RELATIVE_COLOURS.search(_words(prompt or ""))
    if not m:
        return None
    n = _COUNT_WORDS.get((m.group("n1") or m.group("n2") or m.group("n4") or m.group("n5") or "one").lower(), 1)
    word = (m.group("w1") or m.group("w2") or m.group("w3") or m.group("w4") or m.group("w5") or "").lower()
    return n if word in ("more", "extra", "additional", "add", "with") else -n
# the board itself, or a new board of its type (2026-10-19): with a CBJ board read cell by cell, the board
# role copies THE board (the design a designer recognises) unless the words ask for a new one
NEW_BOARD = re.compile(r"\b(a |an )?(new|different|another|fresh|other|random)\b[^.;]{0,30}\b(board|level|layout|arrangement|puzzle)\b|"
                       r"\bof (this|that|the same) (type|kind|sort)\b|\bin (this|that|its) spirit\b|\bnot (the same|a copy|identical)\b|"
                       r"\b(rearrange|shuffle|remix)\w*\b|\bdifferent arrangement\b|\b(a |an )?(new|different) (set|mix) of blocks\b", re.I)
MIRROR = re.compile(r"\bmirror(ed|ing)?\b|\bflip(ped)?\b|\breflect(ed|ion)?\b", re.I)
HARDER = re.compile(r"\b(harder|more difficult|tougher|trickier|one more block in the way|an extra block in the way|another block in the way)\b", re.I)
BLOCKS_REL = re.compile(r"\b(?:(?P<n>one|two|three|four|five|\d)\s+)?(?P<w>fewer|less|more|extra|additional)\s+(?:blocks|pieces|bricks)\b"
                        r"(?![^.;]{0,15}\bcolou?rs?)|\b(?:blocks|pieces|bricks)\s+(?P<w2>fewer|less|more)\b|\bhalf (?:the|as many) (?:blocks|pieces)\b"
                        r"|\b(?P<w3>remove|take away|take off|drop|delete|add|put in)\s+(?P<n3>one|two|three|four|five|\d|a|an)\s+(?:more\s+|extra\s+)?(?:blocks?|pieces?|bricks?)\b"
                        r"(?![^.;]{0,6}\b(in the way|colou?rs?)\b)", re.I)
_BLOCK_COUNTS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
EASIER = re.compile(r"\b(easier|simpler|less difficult|one block fewer|one fewer block)\b", re.I)
MIRROR_TB = re.compile(r"\b(top to bottom|top-to-bottom|vertical(ly)?|upside down)\b", re.I)
_CW = r"(red|orange|yellow|green|dark green|blue|purple)"
RECOLOUR = re.compile(r"\b(?:make|turn|paint|recolou?r|swap|replace|change|convert)\b[^.;]{0,20}\bthe " + _CW + r" (?:blocks?|pieces?|ones?)\b"
                      r"(?:[^.;]{0,25}?\b(?:into|to|for|with|become|becomes))?\s+" + _CW + r"\b|"
                      r"\bthe " + _CW + r" (?:blocks?|pieces?|ones?) (?:become|becomes|turn|turns|are|is) (?:now )?" + _CW + r"\b|"
                      r"\b" + _CW + r" (?:blocks?|pieces?)? ?(?:->|→|to|into) " + _CW + r"\b", re.I)
ASSET_WORDS = re.compile(r"\b(logo|sticker|end[- ]card|button|cursor|icon|mascot)\b", re.I)
MODIFY_WORDS = re.compile(r"\binstead of (the |a )?(current )?(obstacle|walls?)\b|\bon the walls\b|\b(texture|skin)\b", re.I)


def decide(prompt: str, reading: dict) -> dict:
    """The picture's role(s) and what each takes, from the words and the reading:
    {roles, style: {parts, only, keep_blocks} | None, board: {named, all} | None, asset, modify, screen, label,
    keep_look, why: [lines]}."""
    from . import reference as R
    text = _words(prompt)
    notes = reading.get("notes") or {}
    has_board = bool(reading.get("board")) and not reading.get("error")
    is_board_picture = has_board or bool(notes.get("is_color_block_jam"))
    only = bool(ONLY.search(text))
    keep_look = bool(KEEP_LOOK.search(text))
    keep_blocks = bool(KEEP_BLOCKS.search(text)) or keep_look
    why: list[str] = []
    # the style: the look words, or a whole-picture cue that names nothing
    named_style = [p for p, rx in PART_WORDS.items() if rx.search(text)]
    if EVERYTHING.search(text):
        named_style = list(STYLE_PARTS)
    look_words = bool(LOOK_WORDS.search(KEEP_LOOK.sub(" ", text)))
    style_words = look_words or bool(COLOUR_PHRASE.search(text))
    whole = bool(WHOLE.search(text))
    board_named = [p for p, rx in BOARD_PART.items() if rx.search(text)]
    board_all = bool(BOARD_ALL.search(text))
    names_nothing = whole and not (style_words or board_named or board_all or named_style)
    # the picture's own background described in the words ("with the arcade purple-to-pink glow for the background" in a
    # sentence about this picture; H9, 2026-10-18: the planner guessed it "by eye"): the background part is the picture's,
    # measured, unless the words name a colour of their own ("a purple background") or keep the game's
    from . import audit
    pic_bg = (not keep_look and audit.asked(prompt).get("background") is None and
              any(PART_WORDS["background"].search(x) and (STRONG_CUES.search(x) or DEICTIC.search(x) or re.search(r"\bits\b", x, re.I))
                  for x in re.split(r"(?<=[.!?;])\s+", text)))
    bg_hues = [] if keep_look else bg_hues_match(prompt, reading)
    if bg_hues and not pic_bg:
        pic_bg = True
        why.append(f"the {' and '.join(bg_hues)} the words give the background are the picture's own (measured)")
    if pic_bg and "background" not in named_style:
        named_style = named_style + ["background"]
    if pic_bg and not style_words and not names_nothing:
        style_words = True
        why.append("the words describe the picture's own background, so it is measured")
    style = None
    if not keep_look and (style_words or names_nothing):
        named_ok = [p for p in named_style if p != "blocks" or not keep_blocks]
        if only or (not look_words and named_ok):
            parts = named_ok  # "only the background colours", "its colours for the background and the captions"
        else:
            parts = ["background", "captions"] + (["blocks"] if "blocks" in named_ok else [])  # the look as a whole
        if not parts:
            parts = ["background", "captions"]
        if names_nothing and not keep_blocks:
            parts = parts + ["blocks"]  # the concept as a whole: the picture's measured block colours too (H15)
        style = {"parts": [p for p in STYLE_PARTS if p in parts], "only": only, "keep_blocks": keep_blocks,
                 "concept": names_nothing}
        why.append("look words" if style_words else "the request names nothing, so the picture is read for its concept")
    elif "blocks" in named_style and not keep_blocks and (board_all or board_named):
        # "the same block colours, the pink blocks included" with a board: the blocks' display colours alone
        style = {"parts": ["blocks"], "only": only, "keep_blocks": False}
        why.append("the picture's block colours are asked")
    if keep_look:
        why.append("the game's own look is kept, as the request says")
    # the board
    board = None
    if board_all or board_named or (whole and is_board_picture and (names_nothing or (BOARD_TALK.search(text) and not only))):
        if is_board_picture:
            board = {"named": list(PARTS) if (board_all or names_nothing) else
                     (board_named or [p for p in ("shape", "size", "blocks", "colours", "pieces") if _stated_part(prompt, p)]),
                     "all": bool(board_all or names_nothing), "specific": list(board_named)}
            why.append("board words" if (board_all or board_named) else "a board screenshot read for its concept")
        else:
            why.append("the request asks for a board like the picture's, but the picture shows no board, so its look is taken")
            if style is None and not keep_look:
                style = {"parts": ["background", "captions"], "only": False, "keep_blocks": keep_blocks}
    if names_nothing and not is_board_picture and style is None and not keep_look:
        style = {"parts": ["background", "captions"], "only": False, "keep_blocks": keep_blocks}
    asset = bool(R.asks_placement(text) and ASSET_WORDS.search(text))
    modify = bool(MODIFY_WORDS.search(text))
    screen = bool(style and not only and (SCREEN_WORDS.search(text) or names_nothing) and "background" in style["parts"]
                  and "captions" in style["parts"])
    roles = [r for r, on in (("style", style), ("board", board), ("asset", asset), ("modify", modify)) if on]
    if not roles:
        # a reference with no part this tool can take (the words point at the picture, nothing more): its look
        roles, style = ["style"], {"parts": ["background", "captions"], "only": False, "keep_blocks": keep_blocks}
        why.append("no part named: the look is taken")
    return {"roles": roles, "primary": roles[0], "style": style, "board": board, "asset": asset, "modify": modify,
            "screen": screen, "label": bool(LABEL_WORDS.search(text)), "keep_look": keep_look, "only": only, "why": why,
            "named_style": named_style, "keep_blocks": keep_blocks, "bg_hues": bg_hues}


HUE_WORDS = ("red", "orange", "yellow", "gold", "lime", "green", "mint", "teal", "turquoise", "cyan", "aqua", "blue", "navy",
             "indigo", "violet", "purple", "lilac", "lavender", "magenta", "pink", "rose", "coral", "peach", "brown")
HUE_NEAR = 40 / 360  # a named hue this close to a measured background colour's hue is that colour's family


def bg_hues_match(prompt: str, reading: dict) -> list[str]:
    """The hues the words give the background ("the arcade purple-to-pink glow for the background") that match the
    picture's measured background (its top and bottom margins): the words describe the picture's own look (H9b,
    2026-10-18: S8's planner picked #3A0A6B -> #FF3FA4 "by my pick" while the picture measures #581E63 -> #240F3F).
    [] when none match, the words keep the game's look, or state a background the shared reading takes."""
    import colorsys
    from . import audit
    from .videoref import colour_rgb
    text = _words(prompt)
    if KEEP_LOOK.search(text) or audit.asked(prompt).get("background") is not None:
        return []
    m = reading.get("margins") or {}
    hexes = [str(m.get(k) or "").upper() for k in ("top", "bottom")]
    hues = []
    for h in hexes:
        if re.fullmatch(r"#[0-9A-F]{6}", h):
            hue, light, sat = colorsys.rgb_to_hls(*(v / 255 for v in _rgb(h)))
            if sat >= 0.2 and 0.06 <= light <= 0.94:
                hues.append(hue)
    if not hues:
        return []
    out = []
    for x in re.split(r"(?<=[.!?;:])\s+", text):
        if not PART_WORDS["background"].search(x):
            continue
        for w in re.findall(r"[a-z]+", x.lower()):
            if w in HUE_WORDS and w not in out:
                rgb = colour_rgb(w)
                if not rgb:
                    continue
                hw = colorsys.rgb_to_hls(*(v / 255 for v in rgb))[0]
                if any(min(abs(hw - hh), 1 - abs(hw - hh)) <= HUE_NEAR for hh in hues):
                    out.append(w)
    return out


def reconcile(decision: dict, plan: dict | None, reading: dict) -> dict:
    """The reading plan's focus decides the roles (it was written from the request before the picture was read, as the
    video path's reading plan decides its focus); the words decide the parts inside each role (which parts of the look,
    which parts of the board, "only", "keep the game's own"). A role the plan names that the words did not gets its
    default parts; a role the words read that the plan does not is dropped, and both are written in the plan's checks.
    A board role needs a board in the picture. A plan of level "none" takes nothing. No plan: the words' decision."""
    if not plan or plan.get("source") != "planner":
        return decision
    d = dict(decision)
    focus = [f for f in plan.get("focus") or [] if f in ("style", "board", "asset", "modify")]
    has_board = bool(reading.get("board")) and not reading.get("error")
    checks = plan.setdefault("checks", [])
    if plan.get("level") == "none" and not focus:
        checks.append("the plan takes nothing from the picture: no role")
        d.update(roles=[], primary=None, style=None, board=None, asset=False, modify=False, screen=False)
        return d
    if "board" in focus and not has_board:
        checks.append("the plan asks for the board, but no board was read in the picture: its look is taken instead")
        focus = [f for f in focus if f != "board"] + ([] if "style" in focus else ["style"])
    if "style" in focus and not d.get("style") and not d.get("keep_look"):
        # the words' own parts when they name any ("on everything, the blocks too": H12, 2026-10-18, S10 kept the game's
        # blocks because this default left them out)
        named = [x for x in d.get("named_style") or [] if x != "blocks" or not d.get("keep_blocks")]
        parts = named or ["background", "captions"]
        d["style"] = {"parts": [x for x in STYLE_PARTS if x in parts], "only": d.get("only"),
                      "keep_blocks": bool(d.get("keep_blocks")) or "blocks" not in parts}
        checks.append("the plan takes the look: " + ", ".join(d["style"]["parts"]) +
                      (" (the parts the words name)" if named else " (the words name no part of it)"))
    if "board" in focus and not d.get("board"):
        d["board"] = {"named": [], "all": False, "specific": []}
        checks.append("the plan takes the board, the words name no part of it: every part is filled from the image")
    if "style" not in focus and d.get("bg_hues"):
        # the words' hues are the picture's measured background (H9b): the background is taken, measured, whatever the plan
        st = dict(d.get("style") or {"only": d.get("only"), "keep_blocks": True})
        st["parts"] = [x for x in STYLE_PARTS if x in set((st.get("parts") or [])) | {"background"}]
        d["style"] = st
        focus = focus + ["style"]
        checks.append(f"the {' and '.join(d['bg_hues'])} the words give the background are the picture's own background, "
                      f"so it is measured")
    for role in ("style", "board"):
        if role not in focus and d.get(role):
            checks.append(f"the words read the picture's {role} too; the plan does not take it, so it is not applied")
            d[role] = None
    d["asset"], d["modify"] = "asset" in focus, "modify" in focus
    d["screen"] = bool(d.get("screen") and d.get("style"))
    d["roles"] = [r for r, on in (("style", d.get("style")), ("board", d.get("board")), ("asset", d["asset"]),
                                  ("modify", d["modify"])) if on]
    d["primary"] = d["roles"][0] if d["roles"] else None
    d["why"] = list(d.get("why") or []) + [f"the reading plan: {', '.join(focus)} ({plan.get('why') or 'the planner'})"]
    return d


def _stated_part(prompt: str, part: str) -> bool:
    from .videoref import stated
    return part in stated(prompt)


# ---------- the colours (rule I6) ----------

def _rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


HUE_WEIGHT = 2.0  # per degree of hue between a read colour and a slot's rendered colour, on top of the RGB distance


def hue_gap(rgb, slot: str) -> float:
    """Degrees of hue between a colour and a slot's rendered colour (0-180); 0 for a grey."""
    import colorsys
    h1, _, s1 = colorsys.rgb_to_hls(*(v / 255 for v in rgb))
    h2, _, _ = colorsys.rgb_to_hls(*(v / 255 for v in _rgb(RENDERED[slot])))
    if s1 < 0.1:
        return 0.0
    d = abs(h1 - h2) * 360
    return min(d, 360 - d)


def slot_distance(rgb, slot: str) -> float:
    from .videoref import _distance
    return _distance(tuple(rgb), _rgb(RENDERED[slot]))


# The colour family a read name belongs to, and its game slots in order (H16, 2026-10-18: the fallback reader's
# "light green" (151,207,126) went to YELLOW by RGB distance alone, 160 against 173 to green). Checked longest word first.
FAMILIES = (
    ("dark green", ("DarkGreen", "Green")), ("forest", ("DarkGreen", "Green")), ("emerald", ("Green", "DarkGreen")),
    ("green", ("Green", "DarkGreen")), ("lime", ("Green", "DarkGreen")), ("mint", ("Green", "DarkGreen")), ("olive", ("DarkGreen", "Green")),
    ("magenta", ("Purple",)), ("pink", ("Purple", "Red")), ("violet", ("Purple",)), ("purple", ("Purple",)),
    ("lavender", ("Purple",)), ("lilac", ("Purple",)), ("plum", ("Purple",)), ("fuchsia", ("Purple",)),
    ("orange", ("Orange",)), ("coral", ("Orange", "Red")), ("peach", ("Orange",)), ("amber", ("Orange", "Yellow")),
    ("tangerine", ("Orange",)), ("yellow", ("Yellow",)), ("lemon", ("Yellow",)), ("gold", ("Yellow",)), ("mustard", ("Yellow",)),
    ("red", ("Red",)), ("crimson", ("Red",)), ("scarlet", ("Red",)), ("cherry", ("Red",)), ("maroon", ("Red",)),
    ("teal", ("Blue", "Green")), ("cyan", ("Blue",)), ("turquoise", ("Blue", "Green")), ("aqua", ("Blue",)), ("navy", ("Blue",)),
    ("azure", ("Blue",)), ("cobalt", ("Blue",)), ("blue", ("Blue",)),
)
SLOT_FAMILY = {"Green": ("Green", "DarkGreen"), "DarkGreen": ("Green", "DarkGreen")}  # slots that read as one colour family
FAMILY_ORDER_COST = 40.0  # inside a family the first slot is preferred by this much (V1, 2026-10-19: a lime green read as DarkGreen by RGB alone)
FAMILY_COST = 10_000.0  # a slot outside the name's family costs this much more: taken only when its family is full


def family_of(name: str) -> tuple[str, ...] | None:
    n = str(name or "").lower()
    return next((slots for word, slots in FAMILIES if re.search(rf"\b{word}\b", n)), None)


def colour_map(colours: list[dict], keep: list[str] | None = None) -> list[dict]:
    """Each read colour ({name, rgb}) to a distinct game slot, at most seven: the slots of the name's own family first
    (a green name gets Green or DarkGreen while one is free, FAMILIES), then the distance to the RENDERED colours, at the
    least total cost over all colours (each takes its nearest free slot unless a closer colour needs it): [{read, rgb,
    slot, distance, family, cross, note}]. The shade stays the measured one. A note says why a colour became a slot it
    is not ("pink -> purple: the game has no pink"; "... red is taken by coral"); `cross` marks a slot outside the
    name's family (its family's slots were all taken)."""
    words = set(B.COLOUR_WORDS.values())
    cols = [c for c in colours if c.get("rgb")][:7]
    if not cols:
        return []
    slots = tuple(B.COLOURS)
    fams = [family_of(c.get("name")) for c in cols]
    dist = {(i, s): slot_distance(c["rgb"], s) for i, c in enumerate(cols) for s in slots}
    # outside the name's family (or with no family) the hue counts too (2026-10-19: trailer 2's violet, with magenta on the
    # purple slot, went to DARK GREEN by RGB alone; by hue magenta is nearer red than violet is to anything but purple, so the
    # violet keeps purple and the magenta becomes red); inside the family the owner's order stands (H16: coral -> orange)
    cost = {(i, s): dist[i, s] + (FAMILY_ORDER_COST * fams[i].index(s) if fams[i] and s in fams[i] else
                                  (FAMILY_COST if fams[i] else 0.0) + HUE_WEIGHT * hue_gap(cols[i]["rgb"], s))
            for i in range(len(cols)) for s in slots}
    best = min(itertools.permutations(slots, len(cols)), key=lambda perm: sum(cost[i, s] for i, s in enumerate(perm)))
    owner = {s: cols[i]["name"] for i, s in enumerate(best)}
    out = []
    for i, (c, s) in enumerate(zip(cols, best)):
        natural = min(slots, key=lambda x: cost[i, x])
        name = str(c["name"])
        cross = bool(fams[i]) and s not in fams[i]
        why = ([] if name in words else [f"the game has no {name}"]) + \
              ([f"{B.COLOUR_WORDS[natural]} is taken by {owner[natural]}"] if natural != s else [])
        word = B.COLOUR_WORDS[s]
        out.append({"read": name, "rgb": list(c["rgb"]), "measured": bool(c.get("measured")), "source": c.get("source"), "slot": s,
                    "distance": round(dist[i, s], 1), "family": list(fams[i] or []), "cross": cross,
                    "note": f"{name} -> {word}: {', '.join(why)}" if why else (f"{name} -> {word}" if name != word else None)})
    return out


def repaint(mapping: list[dict]) -> tuple[list[dict], list[str]]:
    """The display colours of a repaint: each mapped slot shown in the picture's own colour as measured on its pixels
    (imageread.apply_named; F2, 2026-10-17: pic_w's coral, lemon, lavender and mint were named with the game's words, so a
    shade from the name alone left them the game's own); a colour known only by its name keeps the slot's colour when
    it is that colour (REPAINT_MIN). The contrast against the board's cells is said. ([{slot, hex, name}], notes)."""
    out, notes = [], []
    for m in mapping:
        hx = "#%02X%02X%02X" % tuple(int(x) for x in m["rgb"])
        if B.colour_distance(hx, RENDERED[m["slot"]]) < REPAINT_MIN:
            # the game's own colour as the picture's light shows it (a screenshot's red is the game's red): kept, not repainted
            notes.append(f"{m['read']} -> {B.COLOUR_WORDS[m['slot']]}: the picture's {m['read']} is the game's own {B.COLOUR_WORDS[m['slot']]}")
            continue
        out.append({"slot": m["slot"], "hex": hx, "name": m["read"]})
        d = B.colour_distance(hx, GAME_CELLS)
        notes.append(f"{B.COLOUR_WORDS[m['slot']]} blocks are shown {m['read']} {hx}" +
                     (f" (only {d:.0f} from the board's cells {GAME_CELLS}: they may read darker)" if d < B.MIN_COLOUR_DISTANCE else ""))
    return out, notes


# ---------- the board (rules I7, I8) ----------

def board_shape(bd: dict) -> tuple[str, str, str | None]:
    """The generator's shape for a board read: (shape, what the picture shows in words, the clamp line or None)."""
    outline, read, rooms = bd.get("outline"), bd.get("shape_read"), bd.get("rooms") or 1
    walls, centre = bd.get("wall_cells") or 0, bd.get("centre_wall")
    read = {"narrow_centre": "narrow_center", "hourglass": "narrow_center", "plus": "cross"}.get(read, read)
    # the board read (asked with the generator's shapes defined) first, the whole picture's outline where it is silent;
    # rooms split by walls before either (round 1, 2026-10-17: pic_w's hourglass outlined as a plus once, pic_z's four
    # rooms read as a cross)
    if rooms >= 3:
        return ("door", f"{rooms} rooms split by walls",
                f"{rooms} rooms split by walls -> two rooms joined by a door: the tool builds at most two rooms")
    if read == "narrow_center" or (outline == "hourglass" and read in (None, "open", "holes", "door", "other")):
        return "narrow_center", "an hourglass (a narrow centre)", None
    if read == "cross" or (outline == "plus" and read in (None, "open", "holes", "other")):
        if centre or (walls and outline == "plus"):
            return ("cross", "a plus shape with a wall in the middle",
                    "a plus shape with a wall in the middle -> a cross: the tool cuts the corners away but does not "
                    "combine a wall cell with the cross, so the middle is open")
        return "cross", "a plus shape", None
    if read == "ring" or (outline == "ring" and read in (None, "open", "holes", "other")):
        return "ring", "a ring", None
    if rooms == 2 or read == "door":
        return "door", "two rooms joined by a gap", None
    if outline == "columns" or read == "lanes":
        return "lanes", "columns of lanes", None
    if read == "holes" or walls:
        return "holes", f"{walls or 'a few'} separate wall cell{'s' if walls != 1 else ''}", None
    return "open", "a plain rectangle", None


def _pieces_word(p: str | None) -> str | None:
    p = str(p or "").lower()
    return p if p in B.PIECES else None


SIZE_SPREAD_MAX = 2  # size reads further apart than this (cells a side) are not a size: the count and the fill decide
SIZE_FILL_OFF = 0.25  # a read size on which the count read would cover this much more or less than the board's fill
TYPICAL_FILL = 0.55  # the fill a filled size aims at when the picture's own was not measured reliably


THEMED_FILL_LOW = 0.30  # a fill measured under this on a themed render is not trusted against agreeing size reads (H4b)


def size_from_fill(bd: dict, shape: str, size: tuple[int, int], pieces: str, read: tuple | None = None,
                   themed: bool = False) -> dict | None:
    """The size a FILLED board takes when its read size does not agree with the blocks counted and the fill measured
    (F13, 2026-10-17: pic_z read 12x12 once and 7x7 once, so D3 built 6 big blocks on a sparse 9x10): when the size
    reads spread more than SIZE_SPREAD_MAX, or the count would cover SIZE_FILL_OFF more or less than the fill, the
    board no bigger than the read on which the count keeps the fill (videoref.keep_fill). None when the read stands."""
    from .generate import AVG_CELLS, holes_for
    from .videoref import keep_fill
    n, (w, h) = bd.get("blocks"), size
    if not n or not w or not h:
        return None
    occ = bd.get("occupancy")
    target = occ if isinstance(occ, (int, float)) else TYPICAL_FILL
    free = w * h - len(holes_for(shape, w, h))
    covers = n * AVG_CELLS.get(pieces, 2.3) / max(1, free)
    spread = bd.get("size_spread")
    if spread == 0 and len(bd.get("size_reads") or []) >= 3:
        return None  # three reads agree (H4, 2026-10-18: S3's 7x9 read three times was resized for a low fill measured on a garden render)
    reads = [tuple(x) for x in bd.get("size_reads") or [] if isinstance(x, (list, tuple)) and len(x) == 2]
    if len(reads) >= 3 and themed and isinstance(occ, (int, float)) and occ < THEMED_FILL_LOW and \
            max(reads.count(x) for x in reads) >= 2:
        # two of three reads agree and the fill was measured low on a themed render (H4b, 2026-10-18: S3's 7x10, 7x9, 7x9
        # against 24 % measured on the garden's stone tiles; the truth is 43 %): the median read stands, the fill only
        # picks the pieces
        return None
    wide = spread is not None and spread > SIZE_SPREAD_MAX
    if wide:
        # the reads disagree (D1, D3: pic_z read 12x12 and 7x7/7x8): the read the count and the fill agree with is the size
        from .videoref import board_size
        options = []
        for rw, rh in bd.get("size_reads") or []:
            gw, gh = board_size(shape, rw, rh)
            if gw and gh:
                fr = gw * gh - len(holes_for(shape, gw, gh))
                options.append((abs(n * AVG_CELLS.get(pieces, 2.3) / max(1, fr) - target), (gw, gh), (rw, rh)))
        if options:
            _, kept, raw = min(options)
            if tuple(kept) == (w, h):
                return None
            why = (f"the size reads spread over {spread} cells ({', '.join(f'{a}x{b}' for a, b in bd.get('size_reads') or [])}); "
                   f"{raw[0]}x{raw[1]} is the read on which {n} {pieces} pieces fill the board about like the picture")
            return {"size": list(kept), "why": why,
                    "line": (f"a {read[0]}x{read[1]} board read" + (f" ({w}x{h} the largest the tool builds)" if read and tuple(read) != (w, h) else "")
                             if read else f"a {w}x{h} board") + f" -> {kept[0]}x{kept[1]}: {why}"}
    if abs(covers - target) <= SIZE_FILL_OFF:
        return None
    kept = keep_fill(n, target, shape, w, h, pieces)
    if not kept or tuple(kept) == (w, h):
        return None
    why = (f"the size reads spread over {spread} cells ({', '.join(f'{a}x{b}' for a, b in bd.get('size_reads') or [])})" if wide else
           f"{n} {pieces} pieces would cover about {covers:.0%} of a {w}x{h} board, the picture's is "
           + (f"{occ:.0%} full (measured)" if isinstance(occ, (int, float)) else f"not measured (about {TYPICAL_FILL:.0%} aimed at)"))
    return {"size": list(kept), "why": why,
            "line": (f"a {read[0]}x{read[1]} board read" + (f" ({w}x{h} the largest the tool builds)" if read and tuple(read) != (w, h) else "")
                     if read else f"a {w}x{h} board read") + f" -> {kept[0]}x{kept[1]}: {why}, so the board is sized for its {n} blocks"}


DEFINITE_PIECES = ("small", "long", "big")  # a read piece class the build tries first (H1: S1's 10 big pieces fit its ring)
PACK_MARGIN = 0.65  # a fitted board is expected packed when its blocks' cells cover this share (the row's bar is 0.58)
PACKED_TOP = 0.72  # generate.PACKED_FILL[1]: the generator never packs a board fuller than this


def fit_board(seen: int, shape: str, size: tuple[int, int], pieces: str, pieces_free: bool, size_mode: str, packed: bool,
              target_fill: float, judge_blocks: bool = True, judge_packed: bool = False, margin: float | None = None) -> dict:
    """The block count, pieces and size the generator is asked for, from the count seen on the board: at most the
    brief's limit (BLOCKS_RANGE, 10: brief.check and generate_for_brief both cap a count there; generate.MAX_BLOCKS 12
    is never reached from a brief), the most that fits (videoref.board_blocks) with pieces and a size the request leaves
    open (a cell a side at most; never a size the request names or states), and, when the board must be packed
    like the picture, its blocks covering `margin` (PACK_MARGIN) of the cells. The choice: the most judged rows expected
    to pass (the count within two of the limit, the fill), then the most blocks, then the read size, then the read
    pieces, then the fill nearest the picture's. {blocks, pieces, size, target, cut, fill, lines}."""
    from .generate import AVG_CELLS, holes_for
    from .videoref import BLOCKS_RANGE, board_blocks, board_size
    margin = PACK_MARGIN if margin is None else margin
    limit = BLOCKS_RANGE[1]
    target = max(BLOCKS_RANGE[0], min(seen, limit))
    w0, h0 = size
    sizes = [(w0, h0)]
    if size_mode == "free":  # a size the request names ("the same grid size") or states stays as it is
        for dw, dh in ((-1, 0), (0, -1), (1, 0), (0, 1), (-1, -1), (1, 1)):
            gw, gh = board_size(shape, w0 + dw, h0 + dh)
            if (gw, gh) == (w0 + dw, h0 + dh) and (gw, gh) not in sizes:
                sizes.append((gw, gh))
    kinds = [pieces] + ([k for k in ("small", "mixed", "varied", "long", "big") if k != pieces] if pieces_free else [])
    best = None
    for nb in range(target, BLOCKS_RANGE[0] - 1, -1):
        for pc in kinds:
            for (w, h) in sizes:
                if (board_blocks(nb, shape, w, h, pc) or 0) < nb and not (pc == pieces and pieces in DEFINITE_PIECES):
                    continue  # a definite class the picture shows is tried first; the take's own build checks it (H1)
                free = w * h - len(holes_for(shape, w, h))
                fill = nb * AVG_CELLS.get(pc, 2.3) / max(1, free)
                passes = int(judge_blocks and abs(nb - target) <= 2) + int(judge_packed and fill >= margin)
                key = (passes, nb, (w, h) == (w0, h0), pc == pieces, -abs(min(fill, PACKED_TOP) - target_fill) if packed else 0)
                if best is None or key > best[0]:
                    best = (key, nb, pc, (w, h), fill)
    if best is None:
        nb, pc, (w, h), fill = target, pieces, (w0, h0), 0.0
    else:
        _, nb, pc, (w, h), fill = best
    lines, cut = [], None
    if seen > limit:
        lines.append(f"{seen} blocks -> {min(nb, limit)}: the tool builds at most {limit} blocks in one level")
    if nb < target:
        if packed and judge_packed:
            cut = (f"{target} blocks -> {nb}: {target} blocks would leave the {w0}x{h0} board less full than the picture's; "
                   f"{nb} {pc} pieces cover about {min(fill, 1):.0%} of it")
        else:
            cut = f"{target} blocks -> {nb}: a {w}x{h} board holds about {nb} {pc} pieces"
        lines.append(cut)
    if pc != pieces:
        lines.append(f"{pieces} pieces -> {pc}: the picture's piece sizes are not read reliably, and {pc} pieces let {nb} "
                     f"blocks " + ("fill the board like the picture" if packed and fill >= margin else "fit the board"))
    if (w, h) != (w0, h0):
        lines.append(f"a {w0}x{h0} board -> {w}x{h}: so {nb} blocks " + ("fill it like the picture" if packed else "fit"))
    if packed and fill < margin:
        # the count won over the fill (G10, B1: 10 small pieces on 5x6 came out 53 % full)
        lines.append(f"{nb} {pc} pieces fill about {min(fill, 1):.0%} of the {w}x{h} board; the picture's is about "
                     f"{target_fill:.0%} full" + (" (the count the request names comes first)" if judge_blocks else ""))
    return {"blocks": nb, "pieces": pc, "size": [w, h], "target": target, "cut": cut, "fill": round(fill, 2), "lines": lines}


def themed_look(reading: dict) -> bool:
    """The picture is a themed render (not the game's own light look): its top margin is far from the game's poster
    background, so its fill measure (stone tiles, shadows, glows between the blocks) is less reliable."""
    top = ((reading.get("margins") or {}).get("top") or "").upper()
    return bool(re.fullmatch(r"#[0-9A-F]{6}", top)) and B.colour_distance(top, GAME_POSTER_BG) > THEMED_DIST


THEMED_DIST = 40.0  # redmean distance of the top margin from the game poster background (measured: the game's own screenshots 7, S3's garden 65)


def transforms_asked(prompt: str) -> list[dict]:
    """What the words ask on top of the picture's board, in the order applied: [{kind: recolour|colours|mirror, ...}]."""
    text = _words(prompt)
    out = []
    m = RECOLOUR.search(text)
    if m:
        a, b = (m.group(1) or m.group(3) or m.group(5)), (m.group(2) or m.group(4) or m.group(6))
        slot = {v: k for k, v in B.COLOUR_WORDS.items()}
        if a and b and a.lower() in slot and b.lower() in slot and a.lower() != b.lower():
            out.append({"kind": "recolour", "from": slot[a.lower()], "to": slot[b.lower()]})
    n = relative_colours(prompt)
    if n:
        out.append({"kind": "colours", "n": n})
    if MIRROR.search(text):
        out.append({"kind": "mirror", "axis": "tb" if MIRROR_TB.search(text) else "lr"})
    m = BLOCKS_REL.search(text)
    if m:  # "fewer blocks", "two more blocks", "half the blocks" (2026-10-19, the owner's video creative)
        raw = (m.group("n") or m.group("n3") or "").lower()
        n = _BLOCK_COUNTS.get(raw) or (int(raw) if raw.isdigit() else None) or (1 if raw in ("a", "an") else 2)
        word = (m.group("w") or m.group("w2") or m.group("w3") or "").lower()
        word = {"add": "more", "put in": "more"}.get(word, word)
        half = m.group(0).lower().startswith("half")
        out.append({"kind": "blocks", "n": n if word in ("more", "extra", "additional") else -n, "half": half})
    if HARDER.search(text):
        out.append({"kind": "harder"})
    elif EASIER.search(text):
        out.append({"kind": "easier"})
    return out


def copy_conflicts(prompt: str, level: dict) -> list[str]:
    """Why the picture's board cannot be used as it is: the words state a board part of their own (a size, a block count,
    a shape or colours) that differs from the picture's, or ask for a new board of its type. [] when it can."""
    from . import audit
    from .imagecells import colours_of
    from .videoref import stated
    text = _words(prompt)
    out = []
    if NEW_BOARD.search(text):
        out.append("the request asks for a new board of this type")
    st = stated(prompt)
    a = audit.asked(prompt)
    if "blocks" in st and a.get("blocks") is not None and a["blocks"] != len(level["GridBlockDatas"]):
        out.append(f"the request names {a['blocks']} blocks; the picture's board has {len(level['GridBlockDatas'])}")
    if "size" in st:
        m = re.search(r"\b(\d{1,2})\s*(?:x|by|×)\s*(\d{1,2})\b", text)
        if m and (int(m.group(1)), int(m.group(2))) != (level["gridWidth"], level["gridHeight"]):
            out.append(f"the request names a {m.group(1)}x{m.group(2)} board; the picture's is {level['gridWidth']}x{level['gridHeight']}")
    if "shape" in st and a.get("shape") and not BOARD_ALL.search(text):
        out.append(f"the request names a {a['shape']} shape of its own")
    names = {c.capitalize() for c in a.get("colour_names") or []}
    if names and not any(t["kind"] == "recolour" for t in transforms_asked(prompt)) and a.get("colours") is None:
        have = set(colours_of(level))
        if not names <= have:
            out.append("the request names colours the picture's board does not have (" + ", ".join(sorted(names - have)) + ")")
    if a.get("colours") is not None and a["colours"] != len(colours_of(level)) and relative_colours(prompt) is None:
        out.append(f"the request asks for {a['colours']} colours; the picture's board has {len(colours_of(level))}")
    return out


def copy_spec(prompt: str, brief: dict, reading: dict, decision: dict) -> dict | None:
    """The picture's own board as the level (2026-10-19): when the board role is on, the board was read cell by cell
    (reading["cells"]["level"]) and the words neither ask for a new board nor state a conflicting part, the level is
    that board with the asked transforms (recolour, one more / fewer colours, mirror), written to studio/levels and set
    as level.source "picture". Returns {set, board, notes, text} or None (then board_spec builds a board of the type)."""
    from . import imagecells as IC
    from .audit import made_shape
    cells = reading.get("cells") or {}
    level = cells.get("level")
    if not decision.get("board") or not level:
        return None
    why = copy_conflicts(prompt, level)
    if why:
        return {"skipped": why}
    notes, done, failed = [], [], []
    lv = copy.deepcopy(level)
    if cells.get("walls"):
        done.append({"kind": "walls", "note": cells["walls"]})
    if cells.get("repair"):
        done.append({"kind": "repair", "note": cells["repair"]})
    names = {v: k for k, v in (cells.get("slots") or {}).items() if k != B.COLOUR_WORDS.get(v)}  # slot -> the reference's own word
    for t in transforms_asked(prompt):
        if t["kind"] == "recolour":
            if t["from"] not in IC.colours_of(lv):
                failed.append({**t, "why": f"the picture's board has no {B.COLOUR_WORDS[t['from']]} blocks"})
                continue
            if t["to"] in IC.colours_of(lv):
                failed.append({**t, "why": f"the board already has {B.COLOUR_WORDS[t['to']]} blocks, so the two colours would merge"})
                continue
            lv = IC.recolour(lv, t["from"], t["to"])
            ok, how = IC.solvable(lv)
            done.append({**t, "note": f"the {B.COLOUR_WORDS[t['from']]} blocks and their gates become {B.COLOUR_WORDS[t['to']]}"})
        elif t["kind"] == "colours":
            n = t["n"]
            for _ in range(abs(n)):
                if n > 0:
                    free = [c for c in B.COLOURS if c not in IC.colours_of(lv)]
                    # the planner's own choice first (it wrote the picture's colours plus the one it suggests, "blue suits the
                    # underwater theme"), then the first free game colour that is not the dark green
                    # a new colour from a family not on the board yet (V1, 2026-10-19: a bright green beside the board's dark
                    # green read as one colour to the viewer); the planner's own suggestion first when it is such a colour
                    used_fams = {f for c in IC.colours_of(lv) for f in SLOT_FAMILY.get(c, (c,))}
                    fresh = [c for c in free if not set(SLOT_FAMILY.get(c, (c,))) & used_fams and c != "DarkGreen"]
                    planned = [c for c in (brief.get("level") or {}).get("colours") or [] if c in (fresh or free)]
                    new = (planned or fresh or [c for c in free if c != "DarkGreen"] or free or [None])[0]
                    if new is None:
                        failed.append({**t, "why": "the board already uses the game's seven colours"})
                        break
                    lv2, note = IC.add_colour(lv, new)
                else:
                    lv2, note = IC.remove_colour(lv)
                if lv2 is None:
                    failed.append({**t, "why": note})
                    break
                lv = lv2
                done.append({**t, "note": note})
        elif t["kind"] == "mirror":
            lv = IC.mirror(lv, t["axis"])
            done.append({**t, "note": "the board is mirrored " + ("top to bottom" if t["axis"] == "tb" else "left to right") +
                         " (cells, holes and gates; the solution mirrors with it)"})
        elif t["kind"] == "harder":
            lv2, note = IC.add_blocker(lv)
            if lv2 is None:
                failed.append({**t, "why": note})
            else:
                lv = lv2
                done.append({**t, "note": "harder, as asked: " + note})
        elif t["kind"] == "blocks":
            n = -(len(lv["GridBlockDatas"]) // 2) if t.get("half") else int(t["n"])
            lv2, note = IC.remove_blocks(lv, -n, names=names) if n < 0 else IC.add_blocks(lv, n)
            if lv2 is None:
                failed.append({**t, "why": note})
            else:
                lv = lv2
                done.append({**t, "note": note})
        elif t["kind"] == "easier":
            lv2, note = IC.remove_blocks(lv, 1, easier=True, names=names)
            if lv2 is None:
                failed.append({**t, "why": note})
            else:
                lv = lv2
                done.append({**t, "note": note})
    ok, how = IC.solvable(lv)
    if not ok:
        # the pictures are renders, not the game's own levels: a board drawn unplayable gets the smallest gate repair, said
        if "gave up" in how:
            return {"skipped": [f"the picture's board is too complex for the solver to settle in time ({how})"]}
        fixed, note = IC.repair(lv)
        if fixed is None:
            return {"skipped": [f"the picture's board cannot be played as drawn and no small repair makes it playable ({note})"]}
        lv = fixed
        done.append({"kind": "repair", "note": "the board as drawn could not be played; repaired: " + note})
        ok, how = IC.solvable(lv)
    path = IC.save(lv)
    shape = made_shape(lv)
    ver = cells.get("verify") or {}
    set_ = {"source": "picture", "file": path.name, "shipped": None, "width": lv["gridWidth"], "height": lv["gridHeight"],
            "blocks": len(lv["GridBlockDatas"]), "colours": IC.colours_of(lv), "shape": shape if shape in B.SHAPES else "any",
            "edit": None, "moves": None}
    text = IC.describe(lv)
    board = {"copied": True, "file": path.name, "picture_level": level, "level": lv, "text": IC.describe(level), "built_text": text,
             "took": ["board"], "named": [], "filled": [], "kept": [], "fit": None,
             "seen": {"shape": IC.describe(level).split(" ")[0], "size": [level["gridWidth"], level["gridHeight"]],
                      "blocks": len(level["GridBlockDatas"]), "colours": [B.COLOUR_WORDS[c] for c in IC.colours_of(level)]},
             "built": {"copied": True, "size": [lv["gridWidth"], lv["gridHeight"]], "blocks": len(lv["GridBlockDatas"]),
                       "colours": IC.colours_of(lv), "shape": shape, "packed": False, "symmetric": False},
             "transforms": done, "transforms_failed": failed, "verify": {"doubts": ver.get("doubts") or [], "checked": ver.get("checked"),
                                                                        "asks": cells.get("asks"), "solve": how, "model": cells.get("model")},
             "evidence": {"overlay": cells.get("overlay"), "warp": cells.get("warp"), "crop": cells.get("crop")}}
    for d in done:
        notes.append(d["note"])
    for f in failed:
        notes.append(f"not done: {f['why']}")
    return {"set": set_, "board": board, "notes": notes, "text": text, "solve": how}


def board_spec(prompt: str, brief: dict, reading: dict, decision: dict, pack_margin: float | None = None) -> dict:
    """The level the board gives, part by part: {set: {field: value}, took (named), filled (left open, filled), kept
    (stated by the request), clamps (lines), colour_map, seen (what the picture shows), built (what the tool builds)}."""
    from . import audit
    from .videoref import BLOCKS_RANGE, FULL_FILL, board_blocks, board_size, stated
    bd = reading.get("board") or {}
    lv = brief["level"]
    named = set((decision.get("board") or {}).get("named") or [])
    # the count the words point at the picture for ("the same number of blocks as this board") is the picture's even when
    # the word tables read a number in the same sentence ("the last three blocks" read as a count of 3, case B1); a
    # value the words state for another part ("big blocks like the ones in this picture") stays the words' (I4)
    specific = set((decision.get("board") or {}).get("specific") or [])
    fixed = stated(prompt) - (specific & {"blocks"}) - ({"moves"} if "blocks" in specific else set())
    asked = audit.asked(prompt)
    if "blocks" in specific:
        asked = {**asked, "blocks": None}
    out = {"set": {}, "took": [], "filled": [], "kept": [], "clamps": [], "colour_map": [], "seen": {}, "built": {}}

    def put(part, field, value):
        out["set"][field] = value
        if part not in out["took"] + out["filled"]:
            (out["took"] if part in named else out["filled"]).append(part)

    # the shape: the request's own shape word wins when the planner made it one of the generator's
    shape, seen_words, clamp = board_shape(bd)
    out["seen"]["shape"] = seen_words
    if "shape" in fixed and lv.get("shape") not in (None, "any"):
        out["kept"].append("shape")
        built_shape = lv["shape"]
        if built_shape != shape:
            out["clamps"].append(f"{seen_words} (the request names its own shape) -> {built_shape.replace('_', ' ')}: the request's words win")
        elif clamp:
            out["clamps"].append(clamp)
    else:
        built_shape = shape
        put("shape", "shape", shape)
        if clamp:
            out["clamps"].append(clamp)
    out["built"]["shape"] = built_shape
    # the pieces
    pieces = _pieces_word(bd.get("pieces"))
    if pieces and "pieces" in fixed:
        out["kept"].append("pieces")
    elif pieces:
        put("pieces", "pieces", pieces)
    use_pieces = out["set"].get("pieces") or lv.get("pieces") or "mixed"
    if use_pieces not in B.PIECES:
        use_pieces = "mixed"
    out["seen"]["pieces"] = pieces
    # the size, clamped to what the generator builds for the shape
    c, r = bd.get("columns"), bd.get("rows")
    out["seen"]["size"] = [c, r] if c and r else None
    out["seen"]["size_spread"] = bd.get("size_spread")
    if c and r and "size" not in fixed:
        w, h = board_size(built_shape, c, r)
        sized = None if "size" in named else size_from_fill(bd, built_shape, (w, h), use_pieces, read=(c, r),
                                                            themed=themed_look(reading))
        if sized:
            out["clamps"].append(sized["line"])
            out["seen"]["size_decided_by"] = sized["why"]
            w, h = sized["size"]
        put("size", "width", w)
        out["set"]["height"] = h
        if (w, h) != (c, r) and not sized:
            out["clamps"].append(f"a {c}x{r} board -> {w}x{h}: the tool builds {built_shape.replace('_', ' ')} boards of "
                                 f"{'6-9' if built_shape in ('ring', 'lanes') else '4-9'} columns and 4-10 rows")
    elif "size" in fixed:
        out["kept"].append("size")
    W, H = out["set"].get("width") or lv.get("width"), out["set"].get("height") or lv.get("height")
    out["built"]["size"] = [W, H] if W and H else None
    # the look of the board first (the blocks are fitted to it): packed when the measured fill is FULL_FILL or more
    style = list(lv.get("style") or [])
    occ = bd.get("occupancy")
    out["seen"]["fill"] = occ
    out["seen"]["symmetric"] = bd.get("symmetric")
    if "packed" in specific and occ is None:
        out["clamps"].append(f"the board's fill could not be measured ({bd.get('fill_doubt') or 'no measure'}): it is packed "
                             f"because the request asks for it")
    packed = ((isinstance(occ, (int, float)) and occ >= FULL_FILL) or ("packed" in specific and occ is None)) and "spacious" not in style
    if "packed" in specific and isinstance(occ, (int, float)) and occ < FULL_FILL:
        # "as crowded as this picture" on a board that is not packed (H10, 2026-10-18: S8's picture is about a third full,
        # and the shared "packed" bar of 55 % failed three versions): the picture's fill is the target, said
        if "packed" in style:
            style.remove("packed")
            out["set"]["style"] = style
        out["built"]["fill_target"] = round(occ, 2)
        if "packed" not in out["took"] + out["filled"]:  # judged by the image row "as crowded as the picture"
            (out["took"] if "packed" in named else out["filled"]).append("packed")
        out["clamps"].append(f"as crowded as the picture: about {occ:.0%} of its cells under blocks (measured), so the board "
                             f"is built about as full, not as a packed board")
    # the blocks: counted on the board (never a caption's number); the most the brief takes, fitted with the pieces and
    # the size so the board is as full as the picture's where that is judged (F4, F6, F8, 2026-10-17)
    n = bd.get("blocks")
    out["seen"]["blocks"] = n
    claims = [x for x in reading.get("caption_claims") or [] if x.get("what") == "blocks"]
    for x in claims:
        if n is not None and x["n"] != n:
            out["clamps"].append(f"the caption says {x['n']} blocks (\"{x['caption']}\"), the board shows {n}: the board is "
                                 f"counted, not the caption")
    if n is not None and asked.get("blocks") is None and (lv.get("moves") is None or "blocks" in specific) and "moves" not in fixed and W and H:
        size_mode = "fixed" if "size" in fixed else "named" if "size" in named else "free"
        pieces_free = "pieces" not in fixed  # the pieces' class is read approximately (imageaudit.RELIABLE)
        fit_args = dict(seen=n, shape=built_shape, size=[W, H], pieces=use_pieces, pieces_free=pieces_free, size_mode=size_mode,
                        packed=packed, target_fill=min(PACKED_TOP, occ if isinstance(occ, (int, float)) else PACK_MARGIN),
                        judge_blocks="blocks" in named, judge_packed=packed and "packed" in named)
        fit = fit_board(**{**fit_args, "size": tuple(fit_args["size"])}, margin=pack_margin)
        out["fit_args"] = fit_args
        put("blocks", "blocks", fit["blocks"])
        if fit["pieces"] != use_pieces:
            put("pieces", "pieces", fit["pieces"])
        if tuple(fit["size"]) != (W, H):
            put("size", "width", fit["size"][0])
            out["set"]["height"] = fit["size"][1]
            W, H = fit["size"]
            out["built"]["size"] = [W, H]
        out["clamps"] += fit["lines"]
        out["built"].update(blocks=fit["blocks"], blocks_target=fit["target"], blocks_cut=fit["cut"],
                            fill_expected=fit["fill"])
    elif n is not None:
        out["kept"].append("blocks")
        out["built"]["blocks"] = asked.get("blocks") or lv.get("blocks")
        out["built"]["blocks_target"] = out["built"]["blocks"]
    # the colours: to the game's seven, by the rendered colours
    cm = colour_map(bd.get("colours") or [])
    out["colour_map"] = cm
    out["seen"]["colours"] = [m["read"] for m in cm]
    delta = relative_colours(prompt)
    if cm and delta:
        # the picture's colours plus or minus the asked count: the planner's own extra colour first (it fits the theme), then
        # the game's order; fewer: the least-seen colours go, never below two
        base = [m["slot"] for m in cm]
        if delta > 0:
            extras = [c for c in (lv.get("colours") or []) if c in B.COLOURS and c not in base]
            extras += [c for c in B.COLOURS if c not in base and c not in extras]
            colours = base + extras[:delta]
            note = f"{len(base)} colours in the picture ({', '.join(base)}) + {delta} as asked: {', '.join(extras[:delta])}"
        else:
            keep = max(2, len(base) + delta)
            colours = base[:keep]
            note = f"{len(base)} colours in the picture ({', '.join(base)}) - {min(-delta, len(base) - keep)} as asked: {', '.join(base[keep:]) or 'none (two is the least)'}"
        put("colours", "colours", colours)
        if "colours" in out["filled"]:  # the words name the colours (relative to the picture): taken, not filled
            out["filled"].remove("colours")
            out["took"].append("colours")
        for m in cm:
            if m.get("note"):
                out["clamps"].append(m["note"])
        out["clamps"].append(note)
        out["built"]["colours"] = colours
        out["built"]["colours_by"] = "request+picture"
    elif cm and "colours" not in fixed:
        put("colours", "colours", [m["slot"] for m in cm])
        for m in cm:
            if m.get("note"):
                out["clamps"].append(m["note"])
        out["built"]["colours"] = [m["slot"] for m in cm]
    elif cm:
        out["kept"].append("colours")
        out["built"]["colours"] = [c for c in lv.get("colours") or [] if c in B.COLOURS]  # the request's own (H6)
        out["built"]["colours_by"] = "request"
    # packed and mirror-symmetric, the generator's own looks
    if packed:
        if "packed" not in style:
            style.append("packed")
        put("packed", "style", style)
    if bd.get("symmetric") is True and "symmetric" not in style:
        style.append("symmetric")
        put("symmetric", "style", style)
    elif bd.get("symmetric") is True:
        put("symmetric", "style", style)
    out["built"]["packed"] = "packed" in style
    out["built"]["symmetric"] = "symmetric" in style
    if "spacious" in style and isinstance(occ, (int, float)) and occ >= FULL_FILL:
        out["kept"].append("packed")
    return out


# ---------- the look (rule I6) ----------

def style_kit(reading: dict, parts: list[str]) -> dict:
    """The look the picture gives, measured: {background: [top, bottom], caption_fill, caption_outline, contrast,
    legible, source, notes}."""
    from .imageref import contrast, luminance
    m = reading.get("margins") or {}
    look = (reading.get("notes") or {}).get("look") or {}
    hexok = lambda x: isinstance(x, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", x) is not None  # noqa: E731
    top, bottom = (m.get("top") or "").upper(), (m.get("bottom") or "").upper()
    if not (hexok(top) and hexok(bottom)):
        top, bottom = (str(look.get("background_top") or "").upper(), str(look.get("background_bottom") or "").upper())
    kit: dict = {"background": [top, bottom] if hexok(top) and hexok(bottom) else [], "notes": []}
    cap = reading.get("caption_measured") if isinstance(reading.get("caption_measured"), dict) else {}
    fill, outline, source = cap.get("fill"), cap.get("outline"), "measured in the caption's box"
    if not (hexok(fill) and hexok(outline)) and reading.get("captions"):
        fill, outline, source = look.get("caption_fill"), look.get("caption_outline"), "the reader's words"
    acc_m = reading.get("accent_measured") if isinstance(reading.get("accent_measured"), dict) else {}
    if not (hexok(fill) and hexok(outline)) and kit["background"] and hexok(acc_m.get("hex")) and \
            contrast(acc_m["hex"], kit["background"][0]) >= CAPTION_CONTRAST:
        # the accent the reader names, measured on the pixels it points at (H3b, 2026-10-18: S2's neon trims are not in
        # the margins, so the captions fell back to white)
        fill = acc_m["hex"].upper()
        outline = "#111111" if luminance(fill) > 0.3 else "#FFFFFF"
        source = f"the picture has no caption, so the accent the reader names ({acc_m['hex_read']}), measured on its pixels as {fill}"
    if not (hexok(fill) and hexok(outline)) and kit["background"]:
        # the picture has no caption to measure (H3, 2026-10-18: S2's neon lab): its accent, the most saturated colour of
        # its measured palette that reads at 3:1 on the background, with the darkest colour as the outline
        import colorsys
        bg0 = kit["background"][0]
        acc = sorted((p["hex"] for p in reading.get("palette") or [] if hexok(p.get("hex")) and contrast(p["hex"], bg0) >= CAPTION_CONTRAST),
                     key=lambda h: -colorsys.rgb_to_hls(*(v / 255 for v in _rgb(h)))[2])
        if acc and colorsys.rgb_to_hls(*(v / 255 for v in _rgb(acc[0])))[2] >= 0.35:
            darkest = min((p["hex"] for p in reading.get("palette") or [] if hexok(p.get("hex"))), key=luminance, default="#111111")
            fill, outline = acc[0], ("#111111" if luminance(acc[0]) > 0.3 else "#FFFFFF")
            source = f"the picture has no caption, so its accent colour {acc[0]} (the most saturated colour measured on it)"
    if not (hexok(fill) and hexok(outline)) and kit["background"]:
        dark = luminance(kit["background"][0]) < 0.35
        darkest = min((p["hex"] for p in reading.get("palette") or [] if hexok(p.get("hex"))), key=luminance, default="#222222")
        fill, outline, source = ("#FFFFFF", "#111111", "white on a dark background") if dark else ("#FFFFFF", darkest, "white with the darkest colour")
    fill, outline = str(fill).upper(), str(outline).upper()
    kit.update(caption_fill=fill, caption_outline=outline, caption_source=source)
    if kit["background"]:
        bg = kit["background"][0]  # the hook sits at the top, over the background's top colour
        cf, co = contrast(fill, bg), contrast(outline, bg)
        kit["contrast"] = {"fill": round(cf, 2), "outline": round(co, 2), "against": bg}
        kit["legible"] = max(cf, co) >= CAPTION_CONTRAST
        if not kit["legible"]:
            # the caption would vanish into the background: the darker or lighter of the two that reads is used
            fix = "#FFFFFF" if luminance(bg) < 0.35 else "#1A1A1A"
            kit["notes"].append(f"the caption's colours {fill} / {outline} read at {max(cf, co):.1f}:1 on {bg} (under "
                                f"{CAPTION_CONTRAST:g}:1): the outline becomes {fix}")
            kit["caption_outline"] = fix
            kit["contrast"]["outline"] = round(contrast(fix, bg), 2)
            kit["legible"] = True
    kit["parts"] = list(parts)
    return kit


# ---------- the planner's view of the picture ----------

def planner_view(reading: dict, decision: dict, prompt: str | None = None) -> dict:
    """What the planner's text model is told about the picture: what it shows and its role, never the board's numbers,
    the palette or the captions' words (code applies those; the planner would otherwise copy or half-take them). kind
    "picture" keeps the planner's own image step (imageref.apply) out of it: this workflow decides the role itself."""
    if reading.get("error"):
        return {"file": reading["file"], "kind": "picture", "error": reading["error"]}
    n = reading.get("notes") or {}
    take = []
    if not decision.get("board"):
        # the board is not taken: nothing that describes it (F1, 2026-10-17: "an hourglass board" in what_it_shows became
        # an hourglass level and the hook "Can you clear the neck?" for a request that took only the colours)
        look = (n.get("look") or {}) if isinstance(n.get("look"), dict) else {}
        if decision.get("style"):
            take.append("its look (" + ", ".join(decision["style"]["parts"]) + "), applied in code")
        return {"file": reading["file"], "kind": "picture",
                "notes": {"kind": n.get("kind"), "role": decision["roles"], "look": {"style": look.get("style"), "mood": look.get("mood")},
                          "taken_in_code": take or ["nothing but the look"],
                          "do_not_take": ["its board (the level follows the request's words alone)", "its captions' words",
                                          "its HUD numbers", "its pixels"], "game_fact": GAME_FACT}}
    if decision.get("style"):
        take.append("its look (" + ", ".join(decision["style"]["parts"]) + "), applied in code")
    copied = bool((reading.get("cells") or {}).get("level")) and (prompt is None or not copy_conflicts(prompt, reading["cells"]["level"]))
    if decision.get("board") and copied:
        from .imagecells import describe
        take.append("its board itself, copied cell by cell (" + describe(reading["cells"]["level"]) + "), with the request's own "
                    "changes to it (a colour more or fewer, a recolour, a mirror), applied in code; the level fields are set in code")
    elif decision.get("board"):
        take.append("its board's type (" + ", ".join(decision["board"]["named"]) + "), generated and solved by the tool, applied in code")
    return {"file": reading["file"], "kind": "picture",
            "notes": {"what_it_shows": n.get("what_it_shows"), "kind": n.get("kind"), "role": decision["roles"],
                      "taken_in_code": take or ["nothing but the idea"],
                      "do_not_take": ["its captions' words", "its HUD numbers", "its pixels"] + ([] if copied else ["its exact cells", "its gates"]),
                      "game_fact": GAME_FACT,
                      "idea": n.get("idea")}}


def card_view(reading: dict, decision: dict, prov: dict) -> dict:
    """The reading as the UI's references list shows an image (refSummary: subject, palette, mood, board, role), and as
    audit.reference_rows writes its role row."""
    n, bd = reading.get("notes") or {}, reading.get("board") or {}
    out = {"file": reading["file"], "kind": "image", "palette": reading.get("palette") or [], "model": reading.get("model"),
           "seconds": reading.get("seconds"), "workflow": "image_guided"}
    if reading.get("error"):
        out["error"] = reading["error"]
        return out
    out["notes"] = {"subject": n.get("what_it_shows"), "kind": n.get("kind"), "mood": (n.get("look") or {}).get("mood"),
                    "board": {"is_puzzle_board": bool(bd), "grid_cols": bd.get("columns"), "grid_rows": bd.get("rows"),
                              "block_count": bd.get("blocks"), "block_colours": [c["name"] for c in bd.get("colours") or []]}}
    out["role"] = {"style": "style" in decision["roles"], "composition": "board" in decision["roles"],
                   "asset": decision["asset"], "modify": decision["modify"], "primary": decision["primary"],
                   "taken": prov.get("taken") or []}
    return out


# ---------- applying it to the brief ----------

def _changed(brief: dict, group: str, prov: dict) -> None:
    if group not in brief["changed"]:
        brief["changed"].append(group)
    if group not in prov["set"]:
        prov["set"].append(group)


def _note(brief: dict, line: str) -> None:
    if line and line not in brief["assumptions"]:
        brief["assumptions"].append(line)


def _row(brief: dict, control: str, text: str, prompt: str) -> None:
    row = B.control(brief, control)
    row["asked"] = row["asked"] or prompt.strip()
    row["plan"] = f"{row['plan']} {text}".strip() if row.get("plan") and text not in row["plan"] else text
    if row["status"] in ("default", "not_supported"):
        row["status"] = "applied"


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(t or "").lower()).strip()


SAME_WORDS = re.compile(r"\bsame (words?|captions?|text|texts|lines?|wording)\b|\bits (exact )?(captions?|words|text)\b", re.I)
NO_HUD = re.compile(r"\b(no|without|hide|hidden|remove)\b[^.;]{0,30}\b(hud|level badge|badge|timer|clock|level number)\b", re.I)


def apply(brief: dict, prompt: str, reading: dict, decision: dict) -> dict:
    """Write what the roles take into the brief, in code (see the module note). Returns the provenance, also
    brief["reference"]."""
    from . import videoref as V
    file = reading["file"]
    prov = {"file": file, "kind": "image", "roles": decision["roles"], "focus": list(decision["roles"]), "level": "image",
            "named": [], "filled": [], "taken": [], "not_taken": [], "adapted": [], "not_copied": [], "colour_map": [],
            "clamps": [], "not_used": [], "mechanics": [], "set": [], "analysed_s": reading.get("seconds"),
            "why": decision.get("why") or [], "reading": compact(reading), "plan": reading.get("plan"),
            "reader": {"reader": reading.get("reader"), "model": reading.get("model"), "seconds": reading.get("seconds"),
                       "fell_back": reading.get("fell_back")},
            "disagreements": reading.get("disagreements") or []}
    brief["reference"] = prov
    vs, lv = brief["visuals"], brief["level"]
    text = _words(prompt)
    if reading.get("error"):
        prov["not_taken"].append(f"everything: {file} could not be read ({reading['error'][:120]})")
        _note(brief, "the picture could not be read, so the creative follows the words alone")
        B.adjust(brief, "visuals", "the picture could not be read, so nothing was taken from it.")
        return prov
    # the picture itself goes nowhere but an asset or modify slot (I9)
    if not (decision["asset"] or decision["modify"]):
        if vs.get("background_image") == file:
            vs["background_image"] = None
            _note(brief, "the picture is a reference, so it is not drawn behind the board (its colours are read instead)")
        brief["assets"] = [a for a in brief.get("assets") or [] if a.get("file") != file]
    brief["assumptions"] = [x for x in brief["assumptions"] if not x.startswith(f"Read from {file}")]
    # the look
    st = decision.get("style")
    if decision.get("keep_look"):
        default = B.default_brief()["visuals"]
        reset = [k for k in ("theme", "background", "caption_fill", "caption_outline", "blocks") if vs.get(k) != default[k]]
        for k in reset:
            vs[k] = copy.deepcopy(default[k])
        prov["not_taken"].append("the look: the request keeps the game's own")
        if reset:
            _note(brief, "the game's own look is kept, as the request says (" + ", ".join(k.replace("_", " ") for k in reset) + ")")
    kit = None
    if st and st["parts"] and set(st["parts"]) & {"background", "captions"}:
        kit = style_kit(reading, st["parts"])
        prov["look"] = kit
        if "background" in st["parts"] and kit["background"]:
            vs["background"], vs["theme"] = list(kit["background"]), "custom"
            vs["background_image"] = None
            _changed(brief, "visuals.background", prov)
            prov["taken"].append(f"the background {kit['background'][0]} to {kit['background'][1]} (measured on the picture's margins)")
        if "captions" in st["parts"]:
            vs["caption_fill"], vs["caption_outline"] = kit["caption_fill"], kit["caption_outline"]
            _changed(brief, "visuals.captions", prov)
            c = kit.get("contrast") or {}
            prov["taken"].append(f"the captions {kit['caption_fill']} with a {kit['caption_outline']} outline ({kit['caption_source']}; "
                                 f"{max(c.get('fill', 0), c.get('outline', 0)):.1f}:1 on the background)")
        for line in kit["notes"]:
            _note(brief, line)
        _row(brief, "visuals", "From the picture: " + "; ".join(prov["taken"]) + ".", prompt)
    if st:
        for p in STYLE_PARTS:
            if p not in st["parts"] and p != "blocks":
                prov["not_taken"].append(f"the {p}: the game's own" + (" (only " + ", ".join(st["parts"]) + " is asked)" if st["only"] else ""))
    elif not decision.get("keep_look"):
        prov["not_taken"].append("the look: not asked, so the game's own")
    # the board
    spec = None
    cp = copy_spec(prompt, brief, reading, decision) if decision.get("board") else None
    if cp and cp.get("skipped"):
        line = "the picture's board is not copied as it is: " + "; ".join(cp["skipped"]) + "; a board of its type is generated"
        _note(brief, line)
        prov["not_copied"].append("its exact cells (" + "; ".join(cp["skipped"]) + ")")
        cp = None
    elif decision.get("board") and reading.get("board") and (reading.get("cells") or {}).get("error") and not cp:
        line = ("the board could not be read cell by cell (" + str(reading["cells"]["error"])[:140] + "), so a board of its "
                "type is generated and solved")
        _note(brief, line)
        prov["cells_error"] = reading["cells"]["error"]
    if cp:
        for field, value in cp["set"].items():
            lv[field] = copy.deepcopy(value)
        lv["difficulty"] = "any"  # the picture's board is what it is
        for g in ("level.source", "level.shape", "level.size", "level.blocks", "level.colours"):
            _changed(brief, g, prov)
        prov["board"] = cp["board"]
        prov["named"] = ["board"]
        prov["colour_map"] = []
        ver = cp["board"]["verify"]
        what = (f"the board itself, copied cell by cell from the picture ({cp['board']['text']}; every cell checked against the "
                f"picture's pixels" + (f", {len(ver['doubts'])} doubt(s): {'; '.join(ver['doubts'][:2])}" if ver.get("doubts") else "")
                + f"; solvable in {cp['solve']})" + ("; " + "; ".join(cp["notes"]) if cp["notes"] else ""))
        prov["taken"].append("the board: " + what)
        prov["not_copied"].append("nothing of the board: its cells, colours and gates ARE the picture's (the request asks for this board)")
        _row(brief, "level", f"From the picture: {what}. Say 'a new board of this type' for a fresh board like it.", prompt)
        for line in cp["notes"]:
            _note(brief, line)
    elif decision.get("board"):
        if not reading.get("board"):
            prov["not_taken"].append("the board: none could be read in the picture, so the level follows the words")
            B.adjust(brief, "level", "the picture shows no board the tool could read; the level follows the words of the request.")
        else:
            spec = board_spec(prompt, brief, reading, decision)
            for field, value in spec["set"].items():
                lv[field] = copy.deepcopy(value)
            if spec["set"]:
                lv["source"], lv["shipped"] = "generate", None
                for g, fields in (("level.source", ("source",)), ("level.shape", ("shape",)), ("level.size", ("width", "height")),
                                  ("level.blocks", ("blocks",)), ("level.colours", ("colours",)), ("level.pieces", ("pieces",)),
                                  ("level.style", ("style",))):
                    if g == "level.source" or any(f in spec["set"] for f in fields):
                        _changed(brief, g, prov)
            # a part the words both point at the picture for and state ("a board shaped like this one, a plus shape") is
            # judged like a named one (F10, 2026-10-17: C1's cross had no shape row)
            named_dec = set((decision.get("board") or {}).get("named") or []) | set((decision.get("board") or {}).get("specific") or [])
            prov["named"] = sorted(set(spec["took"]) | (named_dec & set(spec["kept"])))
            prov["filled"] = sorted(set(spec["filled"]))
            prov["colour_map"] = spec["colour_map"]
            prov["clamps"] += spec["clamps"]
            built = spec["built"]
            sw = (built.get('shape') or 'any').replace('_', ' ')
            what = (f"{'an' if sw[:1] in 'aeiou' else 'a'} {sw} board" +
                    (f" {built['size'][0]}x{built['size'][1]}" if built.get("size") else "") +
                    (f", {built['blocks']} blocks" if built.get("blocks") is not None else "") +
                    (f" in {', '.join(B.COLOUR_WORDS[s] for s in built['colours'])}" if built.get("colours") else "") +
                    (f", {lv['pieces']} pieces" if "pieces" in spec["took"] + spec["filled"] else "") +
                    (", packed" if built.get("packed") else "") +
                    (f", about {built['fill_target']:.0%} full like the picture" if built.get("fill_target") is not None else "") + (", mirror-symmetric" if built.get("symmetric") else ""))
            took_words = ", ".join(spec["took"]) or "nothing"
            prov["taken"].append(f"the board: {what} (taken from the picture as asked: {took_words}" +
                                 (f"; filled in from the picture where the request said nothing: {', '.join(sorted(set(spec['filled'])))}"
                                  if spec["filled"] else "") + ")")
            if spec["kept"]:
                prov["not_taken"].append("the board's " + ", ".join(sorted(set(spec["kept"]))) + ": the request states it itself")
            prov["board"] = {"fit_args": spec.get("fit_args"), "text": board_words(reading), "took": sorted(set(spec["took"] + spec["filled"])),
                             "fit": "; ".join(spec["clamps"]) or None, "seen": spec["seen"], "built": built,
                             "named": prov["named"], "filled": prov["filled"], "kept": spec["kept"]}
            prov["not_copied"].append("its exact cells and gates (a new board of this type is generated and solved)")
            _row(brief, "level", f"From the picture: {what}; a new board of this type is generated and solved, its cells "
                                 f"are not copied.", prompt)
            for line in spec["clamps"]:
                _note(brief, line)
    elif reading.get("board"):
        prov["not_taken"].append("the board: not asked, so the level follows the words")
    # the blocks' display colours, only when asked (I6)
    if st and "blocks" in st["parts"]:
        mapping = prov["colour_map"] or colour_map((reading.get("board") or {}).get("colours") or [])
        prov["colour_map"] = mapping
        shown, notes_ = repaint(mapping)
        if len(mapping) < 2:
            prov["not_taken"].append("the blocks' colours: the picture has too few distinct block colours to repaint them")
        else:
            vs["blocks"], vs["theme"] = shown, "custom"
            _changed(brief, "visuals.colours", prov)
            if not lv.get("colours") and "colours" not in V.stated(prompt):
                lv["colours"] = [m["slot"] for m in mapping]  # the repainted slots must be on the board to be seen
                _changed(brief, "level.colours", prov)
            prov["taken"].append("the blocks' colours: " + "; ".join(
                f"{m['read']} as {B.COLOUR_WORDS[m['slot']]}" for m in mapping) + (" (shown in the picture's own colours: "
                + ", ".join(f"{x['name']} {x['hex']}" for x in shown) + ")" if shown else " (each is the game's own colour already)"))
            for m in mapping:
                if m.get("note"):
                    _note(brief, m["note"])
            for line in notes_:
                _note(brief, line)
            _row(brief, "visuals", "From the picture: the blocks are shown in the picture's own block colours, measured on its pixels: " + ", ".join(f"{B.COLOUR_WORDS[x['slot']]} as {x['name']} {x['hex']}" for x in shown) + ".", prompt)
    elif decision.get("style") and decision["style"].get("keep_blocks"):
        prov["not_taken"].append("the blocks' colours: the game's own, as the request says")
    elif st:
        prov["not_taken"].append("the blocks' colours: not asked, so the game's own")
    # the screen (I10)
    hud = reading.get("hud") or {}
    if decision.get("screen") and not hud.get("shown") and not V.HUD_STATED.search(text):
        vs["hud_timer"], vs["hud_level"] = False, False
        _changed(brief, "visuals.hud", prov)
        prov["taken"].append("the screen: no HUD, as in the picture")
    if NO_HUD.search(text):
        prov.setdefault("hud", {})["asked"] = "hidden"
    if decision.get("label") and hud.get("level") and lv.get("label") is None:
        lv["label"] = int(hud["level"])
        _changed(brief, "level.label", prov)
        prov["hud"] = {**prov.get("hud", {}), "took": [f"the level number {hud['level']}"]}
        prov["taken"].append(f"the level number {hud['level']} (asked: the same level)")
    elif hud.get("level"):
        prov["not_taken"].append(f"the HUD's numbers (level {hud['level']}, clock {hud.get('clock') or '?'}): not asked")
    # the captions (I9): never the picture's words unless quoted or asked for
    seen = {_norm(c): c for c in reading.get("captions") or []}
    quoted = {_norm(q[0] or q[1]) for q in B.QUOTED.findall(prompt or "")}
    if seen and not SAME_WORDS.search(text):
        for k in B.CONCEPT_TEXTS:
            t = brief["concept"].get(k)
            if t and _norm(t) in seen and _norm(t) not in quoted:
                brief["concept"][k] = None
                _note(brief, f"the {k.replace('_', ' ')} \"{t}\" is the picture's own caption, which the request does not quote: "
                             f"the tool's own line is used")
        prov["not_copied"].append("its captions' words (" + "; ".join(f'"{c}"' for c in seen.values()) + ")"
                                  + (" except the quoted one" if quoted & set(seen) else ""))
    for x in reading.get("caption_claims") or []:
        if x["what"] == "seconds":
            prov["not_taken"].append(f"the caption's \"{x['n']} seconds\": a caption is not a fact (the length is the request's)")
    # what the game does not have
    lines, not_copied = V.mechanic_lines({"mechanics_seen": reading.get("not_in_game") or []}, brief)
    prov["not_used"] = [ln for ln in lines if NOT_USED in ln]
    prov["mechanics"] = [ln for ln in lines if NOT_USED not in ln]
    prov["not_copied"] += not_copied
    prov["not_copied"].append("its pixels (nothing of the picture is drawn into the gameplay or the frame)"
                              if not (decision["asset"] or decision["modify"]) else "its pixels outside the slot it is placed in")
    for ln in prov["not_used"]:
        _note(brief, ln)
    prov["adapted"] = list(prov["taken"])
    line = (f"The picture is used as a {' and a '.join(ROLE_WORDS[r] for r in decision['roles']) or 'reference the request takes nothing from'}: takes "
            + ("; ".join(prov["taken"]) or "nothing measurable") + "; not taken: " + ("; ".join(prov["not_taken"]) or "nothing"))
    _note(brief, line)
    return prov


def request_values(brief: dict, prompt: str) -> list[str]:
    """Two values the request states that the brief must carry (I4), set in code when the planner left them out:
    the blocks left at a cliffhanger's cut ("before the last three blocks leave", F5) and a fast cascade (the fast tempo
    and the streak finish, F7). Returns the notes."""
    from .imageaudit import FAST_WORDS, blocks_left_asked
    gp, pc = brief["gameplay"], brief["pacing"]
    notes = []
    n = blocks_left_asked(prompt)
    if n is not None and gp.get("ending") == "cliffhanger" and gp.get("blocks_left") != n:
        gp["blocks_left"] = n
        if "gameplay.blocks_left" not in brief.setdefault("changed", []):
            brief["changed"].append("gameplay.blocks_left")
        notes.append(f"the cut leaves {n} block{'s' if n != 1 else ''} on the board, as the request says")
    m = FAST_WORDS.search(prompt or "")
    if m:
        if pc.get("tempo") != "fast" and not re.search(r"\b(calm|slow|relaxed|leisurely)\b", prompt or "", re.I):
            pc["tempo"] = "fast"
            if "pacing.tempo" not in brief.setdefault("changed", []):
                brief["changed"].append("pacing.tempo")
            notes.append(f"\"{m.group(0)}\": the fast tempo")
        if gp.get("ending") in ("win", "near_fail") and gp.get("finish") != "streak":
            gp["finish"] = "streak"
            if "gameplay.finish" not in brief["changed"]:
                brief["changed"].append("gameplay.finish")
            notes.append(f"\"{m.group(0)}\": the streak finish (one move frees the rest, which leave one after another)")
    for line in notes:
        _note(brief, line)
    return notes


END_CONTEXT = re.compile(r"\b(end|ends|ending|cut|stop|stops|finish|finishes|before the (last|final) move|at the end|final|"
                         r"question|result)\b", re.I)
WHICH_QUESTION = re.compile(r"\bwhich (one|block|piece|colou?r)\b", re.I)


def keep_quoted(brief: dict, prompt: str, before: dict | None = None) -> list[str]:
    """A caption the request quotes is never dropped (F12, 2026-10-17: D1's "Which one goes first?" was put in the result
    caption, which videoref.fit_captions clears on a cliffhanger, and the cut showed "Can you see the move?"). Run after
    fit_captions with the concept texts from before it: a quoted text no concept field holds any more goes back to the
    field it had, or, when that field is the one fit_captions clears (a cliffhanger's result) or it had none, to the slot
    the ending shows: the result caption, which a cliffhanger draws as its question at the cut, and a win, a near-fail
    or a time-out on their result screen; a quote with no ending words goes to the hook when it is free. A "which one"
    question on a cliffhanger cuts with two blocks or more left. Returns the notes."""
    from .imageaudit import blocks_left_asked
    cc, gp = brief["concept"], brief["gameplay"]
    notes = []
    for m in B.QUOTED.finditer(prompt or ""):
        q = (m.group(1) or m.group(2)).strip()
        if any(_norm(cc.get(k)) == _norm(q) for k in B.CONCEPT_TEXTS):
            continue
        ctx = prompt[max(0, m.start() - 80):m.start()]
        was = next((k for k in B.CONCEPT_TEXTS if _norm((before or {}).get(k)) == _norm(q)), None)
        slot = "result" if (was == "result" or END_CONTEXT.search(ctx)) else (was or ("hook" if not cc.get("hook") else "result"))
        cc[slot] = q
        if f"concept.{slot}" not in brief.setdefault("changed", []):
            brief["changed"].append(f"concept.{slot}")
        where = {"result": "the question at the cut" if gp.get("ending") == "cliffhanger" else "the result caption",
                 "hook": "the hook"}.get(slot, slot)
        notes.append(f"the request quotes \"{q}\": it is {where}, never dropped")
    question = cc.get("result") if gp.get("ending") == "cliffhanger" else None
    if question and WHICH_QUESTION.search(question) and blocks_left_asked(prompt) is None and (gp.get("blocks_left") or 1) < 2:
        gp["blocks_left"] = 2
        if "gameplay.blocks_left" not in brief.setdefault("changed", []):
            brief["changed"].append("gameplay.blocks_left")
        notes.append(f"\"{question}\" asks which block goes first, so the cut leaves 2 blocks to choose from")
    for line in notes:
        _note(brief, line)
    return notes


PLAY_SHARE_PLAN = 0.6  # a planned play under this share of the stated length is raised before the first take (the estimate
# ran 0-4 s over the play made on round 2: C2 16.8 s expected with the default pacing grade, 13.7 s made)
PLAY_SHARE_CLIFF = 0.7  # a cliffhanger's goal: no replay or result screen comes before its question (H5)
PLAY_SHARE_ROW = 0.5  # the row's bar: the live play (first drag to the last exit or the cut) over the ad's length
CLEAN_WORDS = re.compile(r"\b(clean|perfect|flawless|without (any )?mistakes|no mistakes|mistake-free)\b", re.I)


def _moves(brief: dict, blocks: int) -> int:
    """The drags a generated level of `blocks` blocks takes: its blocks and the repositioning its difficulty adds (the
    generator's own default difficulty for the ending when none is asked)."""
    from .videoref import DIFFICULTY_REPOSITION
    lv, gp = brief["level"], brief["gameplay"]
    diff = lv.get("difficulty") if lv.get("difficulty") not in (None, "any") else \
        {"near_fail": "hard", "time_out": "medium", "cliffhanger": "medium", "win": "medium"}[gp["ending"]]
    return blocks + DIFFICULTY_REPOSITION.get(diff, 1)


def expected_play(brief: dict, blocks: int) -> float:
    """The play's seconds the tool expects for `blocks` blocks (videoref.expected_play: the drag-rate table fitted on
    the tool's own recordings, with studio's own pacing grades; on round 2's 16 versions within 3-5 s of the play made)."""
    from .videoref import expected_play as ep
    play = ep(brief, brief["pacing"]["tempo"], _moves(brief, blocks))[0]
    return play * FAST_PLAY_SCALE if brief["pacing"]["tempo"] == "fast" else play


# The fast tempo's estimate against the play made (G16, 2026-10-17): videoref's table has one fast grade, 1.64 s a drag,
# and B2 ("a fast cascade win", 10 blocks on 5x7) played 13.5 s where 18.0 s were expected, in round 2 and again in
# round 4: the tool measures a fast play at 0.75 of the table.
FAST_PLAY_SCALE = 0.75


def mistakes_allowed(brief: dict, prompt: str) -> bool:
    """Whether the request leaves room for one more wrong move: it states no mistakes itself, and a win is not a clean one."""
    from . import audit
    from .videoref import stated
    gp = brief["gameplay"]
    if "mistakes" in stated(prompt) or audit.asked(prompt).get("mistakes") is not None:
        return False
    if gp["ending"] == "win" and CLEAN_WORDS.search(prompt or ""):
        return False  # a streak finish keeps its own last drags: a wrong move is played early (G16)
    return (gp.get("mistakes") or 0) < 3


def extra_beat(brief: dict, prompt: str, n: int, play0: float, named: bool = True) -> tuple[str | None, float]:
    """One more wrong move or one more hesitation, whichever the tool expects to lengthen the play more; neither when the
    play would not grow by half a second (a wrong move can cost studio's slower pacing grade: C2, 17 s became 15 s).
    The wrong move is a blocked attempt, played early (play keeps mistakes out of the last drags; a streak finish keeps
    its run). (the plan's line or None, the expected play)."""
    from .videoref import MAX_HESITATIONS, stated
    gp, L = brief["gameplay"], float(brief["pacing"]["length_s"])
    options = []
    if mistakes_allowed(brief, prompt):
        trial = copy.deepcopy(brief)
        g = trial["gameplay"]
        g["mistakes"] = (g["mistakes"] if g.get("mistakes") is not None else {"near_fail": 1, "time_out": 1}.get(g["ending"], 0)) + 1
        options.append((expected_play(trial, n), "mistake", g["mistakes"]))
    hes = gp.get("hesitations")
    if "hesitations" not in stated(prompt) and (hes or 0) < MAX_HESITATIONS.get(gp["ending"], 1):
        trial = copy.deepcopy(brief)
        trial["gameplay"]["hesitations"] = (hes or 0) + 1
        options.append((expected_play(trial, n), "hesitation", (hes or 0) + 1))
    best = max(options, default=None)
    if not best or best[0] <= play0 + 0.5:
        return None, play0
    play, kind, value = best
    if kind == "mistake":
        gp["mistakes"] = value
        if "blocked" not in (gp.get("mistake_kinds") or []):
            gp["mistake_kinds"] = list(gp.get("mistake_kinds") or []) + ["blocked"]
        group, words = "gameplay.mistakes", "one early wrong move is played"
    else:
        gp["hesitations"] = value
        group, words = "gameplay.hesitations", "the player hesitates once more (picks a block up and puts it back)"
    if group not in brief.setdefault("changed", []):
        brief["changed"].append(group)
    from .videoref import BLOCKS_RANGE
    head = (f"the request names the count ({n} blocks), which gives about {play0:.0f} s of play in a {L:g} s ad" if named else
            f"{n} blocks is the most one level takes, about {play0:.0f} s of play in a {L:g} s ad" if n >= BLOCKS_RANGE[1] else
            f"the board holds {n} blocks, about {play0:.0f} s of play in a {L:g} s ad")
    tail = "; the finish stays fast" if brief["pacing"]["tempo"] == "fast" else ""
    return f"{head}; {words} so the play carries more of the ad (the request allows it), about {play:.0f} s{tail}", play


def play_levers_left(brief: dict, prompt: str, prov: dict) -> list[str]:
    """What a take could still add to a thin play, in plain words: more blocks (a count the picture filled, under the
    limit), one more wrong move (the request allows it), one more hesitation (under the ending's limit). [] when the play
    is as long as this level allows (G16)."""
    from . import audit
    from .videoref import BLOCKS_RANGE, MAX_HESITATIONS, stated
    lv, gp = brief["level"], brief["gameplay"]
    bd = prov.get("board") or {}
    out = []
    if "blocks" in (bd.get("filled") or []) and audit.asked(prompt).get("blocks") is None and (lv.get("blocks") or 0) < BLOCKS_RANGE[1]:
        out.append("more blocks")
    if mistakes_allowed(brief, prompt):
        out.append("a wrong move")
    if "hesitations" not in stated(prompt) and (gp.get("hesitations") or 0) < MAX_HESITATIONS.get(gp["ending"], 1):
        out.append("a hesitation")
    return out


def fill_play(brief: dict, prompt: str, prov: dict) -> list[str]:
    """Gameplay at the centre (the brief, p.2; G1, 2026-10-17: C3's 8 blocks from the picture played 18 s of a 45 s ad):
    before the first take, the play the tool expects is set against the stated length. Under PLAY_SHARE_PLAN, on a
    board whose count the picture FILLED (the request named none), the blocks rise by 2, twice at most, to the most
    one level takes (10), the size a cell a side when the board cannot hold them and its size is the picture's too; on
    a count the request NAMED, one more wrong move when the request allows it, and the limit said when the play still
    cannot fill. Never the difficulty. Returns the notes (also in the assumptions and the provenance)."""
    from . import audit
    from .videoref import BLOCKS_RANGE, board_blocks, grow_for_blocks
    if "board" not in (prov.get("roles") or []) or not prov.get("board"):
        return []
    lv, gp, L = brief["level"], brief["gameplay"], float(brief["pacing"]["length_s"])
    n0 = lv.get("blocks")
    if not n0:
        return []
    bd = prov["board"]
    filled = "blocks" in (bd.get("filled") or []) and audit.asked(prompt).get("blocks") is None
    play0 = expected_play(brief, n0)
    # a cliffhanger has no replay and no result screen before its question (G13), so its play carries more of the ad
    # (H5, 2026-10-18: S3's 25 s of 40 left a 9 s end card)
    goal = PLAY_SHARE_CLIFF if gp["ending"] == "cliffhanger" else PLAY_SHARE_PLAN
    rec = {"expected_s": round(play0, 1), "share": round(play0 / L, 2), "levers": [], "limit": None, "goal": goal}
    prov["play_fill"] = rec
    if play0 / L >= goal:
        return []
    notes = []
    if filled:
        n, play = n0, play0
        size_free = "size" in (bd.get("filled") or [])
        for _ in range(2):
            if play / L >= goal or n >= BLOCKS_RANGE[1]:
                break
            want = min(BLOCKS_RANGE[1], n + 2)
            shape = lv.get("shape") if lv.get("shape") not in (None, "any") else "open"
            w, h, pieces = lv.get("width"), lv.get("height"), lv.get("pieces") or "mixed"
            if w and h and (board_blocks(want, shape, w, h, pieces) or 0) < want:
                grown = grow_for_blocks(want, shape, w, h, pieces) if size_free else None
                if grown and grown[2] >= want:
                    lv["width"], lv["height"] = grown[0], grown[1]
                else:
                    want = max(n, board_blocks(want, shape, w, h, pieces) or n)
            if want <= n:
                break
            n, play = want, expected_play(brief, want)
        if n > n0:
            lv["blocks"] = n
            for g in ("level.blocks", "level.size"):
                if g not in brief.setdefault("changed", []):
                    brief["changed"].append(g)
            bd.setdefault("built", {}).update(blocks=n, blocks_target=n, blocks_cut=None)
            if isinstance(bd.get("fit_args"), dict):  # a packed retry starts from the raised count
                bd["fit_args"]["seen"] = max(bd["fit_args"].get("seen") or 0, n)
            if lv.get("width") and lv.get("height"):
                bd["built"]["size"] = [lv["width"], lv["height"]]
            line = (f"the picture's {n0} blocks would give about {play0:.0f} s of play in a {L:g} s ad; {n} blocks are built "
                    f"(about {play:.0f} s) so the gameplay carries the ad, as the brief asks")
            rec["levers"].append(line)
            notes.append(line)
    else:
        play = play0
    if play / L < goal:
        # one more wrong move or a hesitation, early in the play (a fast finish keeps its last drags): on a named count,
        # and on a filled count already at the most one level takes (G16, 2026-10-17: B2's 10 blocks at a fast tempo)
        line, play = extra_beat(brief, prompt, n0 if not filled else lv["blocks"], play, named=not filled)
        if line:
            rec["levers"].append(line)
            notes.append(line)
    rec["levers_left"] = play_levers_left(brief, prompt, prov)
    if play / L < PLAY_SHARE_ROW and lv.get("blocks", 0) >= BLOCKS_RANGE[1] and not rec["levers_left"]:
        rec["beyond"] = True
    if play / L < PLAY_SHARE_ROW:
        # the play expected at the best count this board reaches stays under the row's bar (H13, H13b, 2026-10-18: S10's
        # 60 s played 26-30 s on 9 blocks, the most its ring holds; two revisions were spent on it): said, the row is
        # info, and nothing more is tried for it
        rec["beyond"] = True
        rec["levers_left"] = []
        line = (f"one level of {lv.get('blocks') or n0} blocks fills about {play:.0f} s; the rest of the {L:g} s ad is "
                f"replay, result and card" + ("; 30-45 s would be tighter" if L > 45 else ""))
        notes.append(line)
    if play / L < goal:
        n = lv.get("blocks") or n0
        rec["limit"] = (f"about {play:.0f} s of play in a {L:g} s ad: " +
                        (f"the count is the request's ({n} blocks), " if not filled else f"{n} blocks is the most one level takes, " if n >= BLOCKS_RANGE[1] else "the board holds no more blocks, ") +
                        ("and the tool does not change the difficulty for the length" if not rec["levers_left"] else
                         "and a take may still add " + ", ".join(rec["levers_left"])))
        notes = [x for x in notes if not x.startswith("about ")] + [rec["limit"]]
    rec.update(expected_s=round(play, 1), share=round(play / L, 2))
    for line in notes:
        _note(brief, line)
    return notes


QUESTION_PARTS_S = 5.0  # a cliffhanger's question, its end hold and the hook's own time beside the play (S3, 2026-10-18:
# 40 s - 25.8 s play - 9.2 s card)
CARD_AIM_S = 6.0  # the predicted end card above this gives its extra seconds to the question (H18)
QUESTION_HOLD_MAX_S = 6.0


def question_hold(brief: dict, prompt: str, prov: dict) -> list[str]:
    """A cliffhanger whose play cannot fill the ad holds its question longer instead of growing the end card (H18,
    2026-10-18: S3 at the 10-block limit played 64 % of 40 s and the card ran 9.2 s): the card the tool predicts from
    the play expected (fill_play) over CARD_AIM_S gives its extra seconds to the question (sequence.hold_s, at most
    QUESTION_HOLD_MAX_S), said. A hold the request states is kept."""
    from .videoref import stated
    gp, sq = brief["gameplay"], brief["sequence"]
    pf = prov.get("play_fill") or {}
    if gp.get("ending") != "cliffhanger" or "hold" in stated(prompt) or sq.get("hold_s") or not pf.get("expected_s"):
        return []
    L = float(brief["pacing"]["length_s"])
    card = L - float(pf["expected_s"]) - QUESTION_PARTS_S
    if card <= CARD_AIM_S + 1:
        return []
    hold = round(min(QUESTION_HOLD_MAX_S, card - CARD_AIM_S), 1)
    sq["hold_s"] = hold
    if "sequence.timing" not in brief.setdefault("changed", []):
        brief["changed"].append("sequence.timing")
    line = (f"the question stays up {hold:g} s longer so the end card keeps near {card - hold:.0f} s (the play is about "
            f"{pf['expected_s']:.0f} s of the {L:g} s ad)")
    _note(brief, line)
    return [line]


TIME_OUT_LEFT = 1  # play.plan: a time-out ends with exactly one block, one cell short of its gate


def time_out_left(brief: dict, prompt: str) -> list[str]:
    """The blocks left when a time-out's clock runs out, from the words ("the clock runs out with two blocks left"; H20,
    2026-10-18: S9 planned none and stopped with one): the game's player ends a time-out with exactly one block one cell
    from its gate, so another count is said as the limit (the row "blocks left at the cut" is then info)."""
    from .imageaudit import blocks_left_asked
    gp = brief["gameplay"]
    n = blocks_left_asked(prompt)
    if gp.get("ending") != "time_out" or n is None:
        return []
    if n == TIME_OUT_LEFT:
        return []
    line = (f"the clock runs out with one block left, one cell from its gate: the game's time-out cannot stop with "
            f"{n} blocks on the board")
    prov = brief.get("reference") or {}
    prov["time_out_left"] = {"asked": n, "played": TIME_OUT_LEFT}
    _note(brief, line)
    return [line]


STUCK_WORDS = re.compile(r"\bstuck\b|\bblocked\b|\bcan'?t (reach|get out)\b|\bwrong moves?\b|\bmistakes?\b", re.I)


def name_stuck(brief: dict, prompt: str) -> list[str]:
    """A stuck moment the viewer can see (G3, 2026-10-17; the video path's rule, R3c: "a stuck moment names one piece"):
    each stuck step the plan has with no colour gets a mover whose colour is a single block on the board and a blocker
    of another colour (the generator places the named blocker in its way), so "I can't reach green!" points at one
    piece. Only with the board's colours known. Returns the notes."""
    from .videoref import COLOUR_WORDS as CW
    gp, lv = brief["gameplay"], brief["level"]
    events = [dict(e, block=dict(e.get("block") or {})) for e in gp.get("events") or []]
    colours = [c for c in lv.get("colours") or [] if c in B.COLOURS]
    if STUCK_WORDS.search(prompt or "") and gp.get("ending") != "cliffhanger" and len(colours) >= 2 and \
            not any(e.get("action") in ("stuck", "blocks") for e in events) and (gp.get("mistakes") or 0) > 0:
        # the request asks for a stuck moment and the plan has wrong moves but no stuck step: one per wrong move, at most
        # two (as videoref.stuck_step adds one for the video path)
        events += [{"block": {"colour": None, "which": "any", "all": False}, "action": "stuck", "when": "next"}
                   for _ in range(min(2, gp["mistakes"]))]
    open_ = [e for e in events if e.get("action") in ("stuck", "blocks") and not e["block"].get("colour")]
    if not open_ or len(colours) < 2 or CW.search(re.sub(r"\bcolou?r[\s-]*block[\s-]*jam\b", " ", prompt or "", flags=re.I)):
        return []
    used = {e["block"].get("colour") for e in events if e["block"].get("colour")}
    free = [c for c in colours if c not in used]
    notes = []
    movers: list[str] = []
    for e in open_:
        if not free:
            break
        mover = free.pop(0)
        # a blocker that is not an earlier stuck block (two blocks stopping each other in turn may not be playable)
        blocker = next((c for c in colours if c != mover and c not in movers), None) or next((c for c in colours if c != mover), None)
        movers.append(mover)
        e["block"].update(colour=mover, which="any", all=False)
        if e.get("action") == "stuck" and blocker:
            e["by"] = blocker
        notes.append(f"the stuck moment points at one piece: the only {B.COLOUR_WORDS[mover]} block heads for its gate and a "
                     f"{B.COLOUR_WORDS[blocker]} block is in the way")
    if notes:
        gp["events"] = events
        if "gameplay.events" not in brief.setdefault("changed", []):
            brief["changed"].append("gameplay.events")
        for line in notes:
            _note(brief, line)
    return notes


DARK_PLATE = 0.2  # a background whose top or bottom is darker than this luminance is drawn as an unlit plate
PLATE_SIZE = (1080, 1920)


def dark_plate(brief: dict, prov: dict) -> str | None:
    """A dark background the picture gave, drawn as a tool-made plate (G5, 2026-10-17: D2's #040926 night came out
    #1C2238 in play, because the runner colours the game's lit Ground and Unity's light lifts dark colours; a picture
    behind the board, visuals.background_image, is drawn unlit on a far canvas with the Ground hidden, and past posters
    show it within 2 of its pixels). The plate is the kit's two colours as a vertical gradient (PIL, 1080x1920), saved
    in the uploads; it holds no pixel of the reference picture. Returns the plan's line, or None."""
    from PIL import Image
    from . import studio
    from .imageref import luminance
    kit = prov.get("look") or {}
    bg = [h.upper() for h in kit.get("background") or []]
    if len(bg) != 2 or "background" not in (kit.get("parts") or []) or min(luminance(h) for h in bg) >= DARK_PLATE:
        return None
    top, bottom = _rgb(bg[0]), _rgb(bg[1])
    name = f"cbj_plate_{bg[0][1:]}_{bg[1][1:]}.png"
    folder = studio.STUDIO / "uploads"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    if not path.is_file():
        w, h = PLATE_SIZE
        im = Image.new("RGB", (1, h))
        for y in range(h):
            k = y / (h - 1)
            im.putpixel((0, y), tuple(round(a + (b - a) * k) for a, b in zip(top, bottom)))
        im.resize((w, h)).save(path)
    vs = brief["visuals"]
    vs["background_image"] = name
    if "visuals.background" not in brief.setdefault("changed", []):
        brief["changed"].append("visuals.background")
    line = (f"the {plate_word(bg)} background {bg[0]} to {bg[1]} is drawn as a flat plate behind the board: the game's lit "
            f"ground would lift its dark colours by about 25")
    prov.setdefault("taken", []).append(line)
    prov["plate"] = name
    _note(brief, line)
    return line


def plate_word(bg: list[str]) -> str:
    """"night" only for a navy or black background; any other dark one is "dark" (H19, 2026-10-18: S7's warm wooden
    brown #AD8E71 -> #866346 was called a night background)."""
    import colorsys
    from .imageref import luminance
    def nightly(h: str) -> bool:
        hue, light, sat = colorsys.rgb_to_hls(*(v / 255 for v in _rgb(h)))
        return luminance(h) < 0.03 or (0.55 <= hue <= 0.75 and luminance(h) < 0.12)
    return "night" if bg and all(nightly(h) for h in bg) else "dark"


CASCADE_CLAIM = re.compile(r"\bfrees? (them |every\w* |all )|\bone move frees\b|\bchain reaction\b", re.I)
# promises the game never plays (G14, 2026-10-17: C3's hook "Clear it in perfect pairs" on a mirror-symmetric board; in
# CBJ one drag frees one block, so the clears never come in pairs, together or all at once)
PAIR_CLAIM = re.compile(r"\b(in |perfect |matching )?pairs?\b|\btogether\b|\bboth at once\b|\b(two|three) at a time\b|"
                        r"\bin one go\b|\ball at once\b|\bat the same time\b|\bsimultaneous\w*\b|\bchains?\b", re.I)
GAME_FACT = ("in Color Block Jam one drag frees one block; the moves of a mirror-symmetric board are not paired; do not "
             "promise pairs, chains or all-at-once clears")
CASCADE_NOTE = ("in Color Block Jam one drag frees one block and each exit slides out in about half a second to a second; "
                "the finish is played at the game's fastest, about 0.3 s between drags")


def honest_cascade(brief: dict, prompt: str) -> list[str]:
    """A "fast cascade" said as the game can play it (G6): the note in the plan, and no planned caption claiming one
    move frees them all (the compositor writes its own "One move frees them all!" only when one drag really frees 3 or
    more blocks: its key move). No planned caption promises pairs, chains or clears together either (G14): the plan
    has no move that frees two blocks in one drag, since the game has none. A caption the request quotes stays."""
    from .imageaudit import FAST_WORDS
    notes = []
    cc = brief["concept"]
    quoted = {_norm(q[0] or q[1]) for q in B.QUOTED.findall(prompt or "")}
    for k in ("cascade", "result"):
        if cc.get(k) and CASCADE_CLAIM.search(cc[k]) and _norm(cc[k]) not in quoted:
            notes.append(f"the {k} line \"{cc[k]}\" is left to the tool: it is written only when one drag really frees "
                         f"three blocks or more")
            cc[k] = None
    for k in ("hook", "mistake", "cascade", "result"):
        if cc.get(k) and PAIR_CLAIM.search(cc[k]) and _norm(cc[k]) not in quoted:
            notes.append(f"the {k.replace('_', ' ')} line \"{cc[k]}\" promises clears the game never plays (one drag frees "
                         f"one block), so the tool's own line is used")
            cc[k] = None
            if f"concept.{k}" not in brief.setdefault("changed", []):
                brief["changed"].append(f"concept.{k}")
    if FAST_WORDS.search(prompt or ""):
        notes.append(CASCADE_NOTE)
    for line in notes:
        _note(brief, line)
    return notes


SAME_SHADE = 12.0  # brief.colour_distance: a shown block colour this close to the picture's measured one is that colour


def restore_repaint(brief: dict, prov: dict) -> list[str]:
    """The picture's block colours kept through the shared brief check (G11, 2026-10-17: A2's coral #EF7066 became brick
    #BA5750 and teal #89D0C3 a plain blue #60ACD8, because brief.check deepens a colour near the BACKGROUND or near another
    block). In this workflow a block sits on the board's cells, not on the background (only its short exit slide crosses
    it): a colour the check moved for the background alone (it is MIN_COLOUR_DISTANCE or more from the board's cells
    and from every other block colour) gets its measured shade back. Two block colours too close to tell their gates
    apart keep a repair, made the smallest step that separates them (the later one moved toward its game colour), and
    said in plain words. Returns the notes."""
    vs = brief["visuals"]
    measured = {m["slot"]: ("#%02X%02X%02X" % tuple(int(x) for x in m["rgb"]), m["read"])
                for m in prov.get("colour_map") or [] if m.get("rgb")}
    shown = {e["slot"]: e for e in vs.get("blocks") or []}
    if not measured or not shown or "visuals.colours" not in (prov.get("set") or []):
        return []
    cells = vs.get("board") or GAME_CELLS
    want = {s: measured[s][0] for s in shown if s in measured}
    notes, done = [], {}
    for slot in [s for s in shown if s in want]:
        hx = want[slot]
        others = [done.get(o, want[o]) for o in want if o != slot]
        close = [o for o in want if o != slot and B.colour_distance(hx, done.get(o, want[o])) < B.MIN_COLOUR_DISTANCE and o in done]
        if B.colour_distance(hx, cells) >= B.MIN_COLOUR_DISTANCE and not close:
            if shown[slot]["hex"].upper() != hx:
                shown[slot]["hex"] = hx
            done[slot] = hx
            continue
        # too close to the cells or to a block colour already placed: the smallest step toward its game colour that separates
        step = next((B._blend(hx, RENDERED[slot], k / 20) for k in range(1, 21)
                     if B.colour_distance(B._blend(hx, RENDERED[slot], k / 20), cells) >= B.MIN_COLOUR_DISTANCE and
                     all(B.colour_distance(B._blend(hx, RENDERED[slot], k / 20), done[o]) >= B.MIN_COLOUR_DISTANCE for o in done)),
                    RENDERED[slot])
        shown[slot]["hex"] = step
        done[slot] = step
        who = [measured[o][1] for o in close] or ["the board's cells"]
        notes.append(f"{measured[slot][1]} and {' and '.join(who)} are too close to tell their gates apart, so "
                     f"{measured[slot][1]} is made a little deeper ({hx} -> {step})")
    for line in notes:
        _note(brief, line)
    prov["repaint_shown"] = {s: shown[s]["hex"] for s in shown}
    return notes


PALETTE_WORDS = re.compile(r"\b(sunset|sunrise|night|neon|pastel|autumn|winter|spring|summer|candy|ocean|forest|desert|"
                           r"tropical|retro|vintage|warm|cool)\b\s*(palette|colou?rs|tones|shades|look)?", re.I)


def palette_choice(brief: dict, prompt: str, prov: dict) -> list[str]:
    """Say which colours a palette word on the blocks gives (G12, 2026-10-17: "this picture's sunset palette on
    everything, the blocks too" can mean the picture's own block colours or the background's sunset shades; the viewer
    wanted the second twice): when the request names a palette word for the blocks and the picture's block colours are
    not the background's hues, the plan says the choice and how to ask for the other."""
    m = PALETTE_WORDS.search(prompt or "")
    if not m or "visuals.colours" not in (prov.get("set") or []):
        return []
    bg = [h for h in ((prov.get("look") or {}).get("background") or [])]
    cm = prov.get("colour_map") or []
    if not bg or not cm:
        return []
    near = [x for x in cm if min(B.colour_distance("#%02X%02X%02X" % tuple(int(v) for v in x["rgb"]), h) for h in bg) < B.MIN_COLOUR_DISTANCE]
    if len(near) * 2 >= len(cm):
        return []  # the blocks are mostly the background's hues already
    word = m.group(1).lower()
    line = (f"The blocks take the picture's own block colours ({', '.join(x['read'] for x in cm)}); the {word} gradient is the "
            f"background. Ask for \"the blocks in the background's {word} shades\" to repaint them from the gradient instead.")
    prov["palette_choice"] = line
    _note(brief, line)
    return [line]


def review_facts(prov: dict) -> list[str]:
    """What the picture gave, as measured facts for the viewer's review (G2): the viewer then judges against the
    picture, not against its own idea of it."""
    out = []
    if prov.get("repaint_shown"):
        names = {m["slot"]: m["read"] for m in prov.get("colour_map") or []}
        out.append("the blocks are shown in the picture's own block colours, measured on its pixels: " +
                   ", ".join(f"{names.get(s, s)} {h}" for s, h in prov["repaint_shown"].items()))
    look = prov.get("look") or {}
    if look.get("background") and "background" in (look.get("parts") or []):
        out.append(f"the background is the picture's, measured on its margins: {look['background'][0]} to {look['background'][1]}")
    if look.get("caption_fill") and "captions" in (look.get("parts") or []):
        out.append(f"the captions are the picture's, measured in its caption: {look['caption_fill']} with a {look['caption_outline']} outline")
    bd = prov.get("board") or {}
    if bd.get("copied"):
        out.append("the board IS the picture's board, copied cell by cell and checked against its pixels (" + str(bd.get("built_text") or bd.get("text")) + ")"
                   + ("; changed as asked: " + "; ".join(t["note"] for t in bd.get("transforms") or []) if bd.get("transforms") else ""))
    elif bd.get("built"):
        b = bd["built"]
        out.append(f"the board is the picture's type: {(b.get('shape') or 'any').replace('_', ' ')}"
                   + (f" {b['size'][0]}x{b['size'][1]}" if b.get("size") else "") + (f", {b['blocks']} blocks" if b.get("blocks") else ""))
    if prov.get("palette_choice"):
        out.append(prov["palette_choice"])
    for line in (prov.get("play_fill") or {}).get("levers") or []:
        out.append(line)
    if (prov.get("play_fill") or {}).get("limit"):
        out.append("the play's limit: " + prov["play_fill"]["limit"])
    return out


REPLAY_ASKED = re.compile(r"\breplay\w*\b|\bslow[- ]?mo(tion)?\b", re.I)
NO_REPLAY_TEXT = re.compile(r"\b(no|without( a| the| any)?)\s+(slow[- ]motion\s+)?replay\b|\bthere is no (slow[- ]motion )?replay\b|"
                            r"\breplay is (left out|dropped|not (shown|used|played))\b", re.I)
NO_RESULT_TEXT = re.compile(r"\b(no|without( a| the)?)\s+result screen\b|\bthere is no result screen\b", re.I)
CLIFF_REPLAY_LINE = ("No slow-motion replay before the question: it would show the move the question asks about. The play "
                     "runs to the cut, then the question, then the end card.")


def _sentences(text: str) -> list[str]:
    return [x for x in re.split(r"(?<=[.!?])\s+", text or "") if x.strip()]


def sequence_matches(brief: dict, prompt: str) -> list[str]:
    """The sequence's words and fields agree (G13a, 2026-10-17: C2's plan said "There is no replay and no result screen"
    while the fields kept both on, and the ad played a replay): a plan text that says no replay or no result screen sets
    that field off, unless the request asks for a replay itself; a field that is off never keeps words promising it.
    Returns the notes."""
    sq, row = brief["sequence"], B.control(brief, "sequence")
    text, notes = row.get("plan") or "", []
    asked = bool(REPLAY_ASKED.search(prompt or ""))
    if NO_REPLAY_TEXT.search(text) and sq.get("replay") and not asked:
        sq["replay"] = False
        notes.append("the plan said no replay; the field is set to match")
    if NO_RESULT_TEXT.search(text) and sq.get("result_screen"):
        sq["result_screen"] = False
        notes.append("the plan said no result screen; the field is set to match")
    if not sq.get("replay"):
        promised = [x for x in _sentences(text) if re.search(r"\breplay", x, re.I) and not NO_REPLAY_TEXT.search(x)]
        if promised:
            row["plan"] = " ".join(x for x in _sentences(text) if x not in promised)
            notes.append("the plan's words promised a replay the ad does not play; they are left out")
    if notes and "sequence" not in brief.setdefault("changed", []):
        brief["changed"].append("sequence")
    return notes


def cliffhanger_replay(brief: dict, prompt: str) -> list[str]:
    """A cliffhanger's question is its payoff, so no slow-motion replay plays before it (G13b, 2026-10-17: C2 and B1
    replayed the last drags right before "Can you see the move?", and the replay showed the block the question asks
    about), unless the request asks for a replay. The time freed goes where the compositor already puts it (the
    question held longer, the end card). The text workflow keeps its own behaviour."""
    sq, gp = brief["sequence"], brief["gameplay"]
    if gp.get("ending") != "cliffhanger" or REPLAY_ASKED.search(prompt or "") or not sq.get("replay"):
        return []
    sq["replay"] = False
    row = B.control(brief, "sequence")
    kept = [x for x in _sentences(row.get("plan") or "") if not re.search(r"\breplay", x, re.I)]
    row["plan"] = " ".join(kept + [CLIFF_REPLAY_LINE])
    if row.get("status") == "default":
        row["status"] = "applied"
    if "sequence" not in brief.setdefault("changed", []):
        brief["changed"].append("sequence")
    _note(brief, CLIFF_REPLAY_LINE)
    return [CLIFF_REPLAY_LINE]


CUT_MAX_LEFT = 3  # brief.check takes a cliffhanger's cut at 1-3 blocks left


def _block_word(level, bid: int) -> str:
    from .describe import color_name
    return f"the {color_name(level.blocks[bid].color)} block"


def cut_choice_planned(level, k0: int, brief: dict) -> dict | None:
    """The cut on the take's own planned path (studio._plan: the play planner with the brief's wrong moves, hesitations
    and steps, at its seed), for k blocks left from k0 up to CUT_MAX_LEFT: the plan ends on a push into a blocker (a
    "bump") when a remaining block is trapped there, else on a hesitation (round 4, B1 and D1: the bare solver's path
    found nothing while the recordings had a blocked block at the cut). {left, words, source} or None."""
    from . import studio
    for k in range(max(1, k0), CUT_MAX_LEFT + 1):
        trial = copy.deepcopy(brief)
        trial["gameplay"]["blocks_left"] = k
        try:
            script = studio._plan(trial, level, trial["gameplay"].get("seed") or 0)
        except Exception:
            continue
        last = script.beats[-1] if script.beats else None
        if last is not None and last.kind == "bump":
            m = re.search(r"but .*?\(([a-z ]+)\) is in the way", last.note or "")
            words = f"{_block_word(level, last.drag.block)} is still blocked" + (f" by a {m.group(1)} block" if m else "")
            return {"left": k, "words": words, "source": "the take's planned path"}
    return None


def cut_choice(level, k0: int) -> dict | None:
    """The cut that makes a cliffhanger's question a real choice (G15, 2026-10-17: D1 cut with 2 blocks left in two rooms,
    each free to leave, so "Which one goes first?" asked nothing): on the solver's own solve of the level, the latest
    position with k blocks left (k from k0 up to CUT_MAX_LEFT) where one remaining block is trapped by another, as the
    player's own cut looks for it (play.bumps). {left, step, trapped, blocker, words} or None when no such position."""
    from . import play
    from .solver import solve_fast
    sol = solve_fast(level)
    if sol is None:
        return None
    states = play._states(level, list(sol.drags))
    for k in range(max(1, k0), CUT_MAX_LEFT + 1):
        for i in reversed([i for i, st in enumerate(states) if play._left(st) == k]):
            options = play.bumps(level, states[i])
            if options:
                drag, blocker, _ = options[0]
                return {"left": k, "step": i, "trapped": drag.block, "blocker": blocker,
                        "words": f"{_block_word(level, drag.block)} is still blocked by {_block_word(level, blocker)}"}
    return None


BLOCK_COLOUR_ASK = re.compile(r"\b(red|blue|green|yellow|orange|purple|pink|teal|mint|lemon|lilac|violet|gold|cyan|"
                              r"magenta|lime|navy|turquoise|peach|rose|neon|pastel|coral|aqua|crimson|salmon|lavender|emerald|amber|"
                              r"indigo|sandy?|brown|beige|black|white|gr[ae]y)\b(?:(?!background|backdrop|captions?)[^.;]){0,30}\b(blocks?|pieces?)\b",
                              re.I)  # a colour word for the blocks themselves, not for a background or captions beside them


def clear_invented_blocks(brief: dict, prompt: str, prov: dict) -> list[str]:
    """Never invented block hexes (H15, 2026-10-18: S13's planner wrote "neon pink #FF2E88 ..." while the blocks were not
    taken, and the not-taken row failed; S10's revision repainted against stale provenance): when the picture's block
    colours are not taken and the words name no block colours of their own, the plan's display colours are cleared
    (the game's own); when they are taken, the picture's measured ones are used (restore_repaint keeps them). Run after
    the plan and after each revision. Returns the notes."""
    vs = brief["visuals"]
    if not vs.get("blocks") or "visuals.colours" in (prov.get("set") or []) or BLOCK_COLOUR_ASK.search(_words(prompt)):
        return []
    names = ", ".join(e.get("name") or e.get("slot") for e in vs["blocks"])
    vs["blocks"] = []
    if vs.get("theme") not in ("game", "custom"):
        vs["theme"] = "game"
    line = f"the plan's own block colours ({names}) are left out: the request does not take the picture's block colours"
    _note(brief, line)
    return [line]


SIZE_TEXT = re.compile(r"\b(\d{1,2})\s*(?:x|by|×)\s*(\d{1,2})\b", re.I)
COUNT_TEXT = re.compile(r"\b(\d{1,2})\s+(?:\w+\s+)?blocks?\b", re.I)


def reconcile_numbers(brief: dict, prov: dict, planner_lines: list[str]) -> list[str]:
    """What the plan says is what was made (H8, 2026-10-18: S7's text said "I read 'small' as a 6 by 6 board" for the
    picture's 5x7): when the picture set the board's size or count, a planner sentence naming another size or count is
    left out, here and in the plan rows. Returns the notes."""
    lv = brief["level"]
    bd = prov.get("board") or {}
    took = set((bd.get("took") or []))
    w, h, n = lv.get("width"), lv.get("height"), lv.get("blocks")

    def wrong(x: str) -> bool:
        if "size" in took and w and h and any((int(a), int(b)) != (w, h) for a, b in SIZE_TEXT.findall(x)):
            return True
        return "blocks" in took and n is not None and any(int(m) != n for m in COUNT_TEXT.findall(x))
    gone = [x for x in planner_lines if wrong(x)]
    brief["assumptions"] = [x for x in brief["assumptions"] if x not in gone]
    for row in brief.get("controls") or []:
        if row.get("control") != "level" or not row.get("plan"):
            continue
        kept = [x for x in _sentences(row["plan"]) if x.startswith("From the picture") or not wrong(x)]
        row["plan"] = " ".join(kept)
    return [f"the planner's words \"{x[:80]}\" are left out: the board is the picture's ({w}x{h}, {n} blocks)" for x in gone]


ROLE_WORDS = {"style": "style reference", "board": "board reference", "asset": "picture to place", "modify": "picture that modifies the creative"}


def board_words(reading: dict) -> str:
    bd = reading.get("board") or {}
    if not bd:
        return "no board"
    shape = board_shape(bd)[1]
    return (f"{shape}, {bd.get('columns') or '?'}x{bd.get('rows') or '?'}, {bd.get('blocks') or '?'} blocks in "
            + ", ".join(c["name"] for c in bd.get("colours") or []) + (f", {bd['pieces']} pieces" if bd.get("pieces") else "")
            + (", mirror-symmetric" if bd.get("symmetric") else "")
            + (f", {bd['occupancy']:.0%} of its cells under blocks" if isinstance(bd.get("occupancy"), (int, float)) else ""))


def compact(reading: dict) -> dict:
    """The reading as the provenance keeps it (the board read's raw answers and the clusters stay out of the brief)."""
    keep = ("file", "facts", "palette", "margins", "notes", "validation", "answers", "board", "hud", "captions", "caption_claims",
            "caption_measured", "accent_measured", "not_in_game", "disagreements", "model", "reader", "seconds", "fell_back", "error", "errors",
            "cells")
    out = {k: copy.deepcopy(reading.get(k)) for k in keep if k in reading}
    br = reading.get("board_read") or {}
    out["board_read"] = {k: br.get(k) for k in ("box", "size_reads", "colour_counts", "colour_count", "colours_counted",
                                                "error", "model", "seconds") if k in br}
    m = br.get("measured") or {}
    if m:
        out["board_read"]["measured"] = {k: m.get(k) for k in ("mirror_lr", "mirror_tb", "symmetric", "clusters", "block_cells")}
    return out
