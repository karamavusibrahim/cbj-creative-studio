"""The creative brief: what a prompt asks for, as data the engine can execute.

A planner (an LLM, see planner.py) turns a prompt into a brief. This module defines the brief,
checks it against what the engine can really do, and records every adjustment in the brief
itself, so nothing a prompt asks for is dropped silently.

The brief follows the case's eight prompt controls (p.3). Each one gets a row in `controls`:
what the prompt asked, what the tool will do, and a status:
- applied: asked for, and done as asked;
- default: the prompt said nothing, so the tool's default is used;
- adjusted: asked for, but changed to something the game can do (the reason is in `why`);
- not_supported: asked for, and the tool cannot do it (the reason is in `why`).

Colours have two sides. A block's colour SLOT is one of the game's seven colours: the level,
the gates and the solver use it. Its DISPLAY colour is what the viewer sees: the recorder can
repaint a slot with any colour, and captions then name the display colour ("pink"), never the
slot ("red").
"""

from __future__ import annotations

import copy
import re
from pathlib import Path

from .ad import FACT_KEYS, copy_problems

CONTROLS = ("level", "gameplay", "difficulty_pacing", "visuals", "concept", "sequence", "assets", "unchanged")
CONTROL_TITLES = {
    "level": "Type or structure of the level",
    "gameplay": "Gameplay behaviour",
    "difficulty_pacing": "Difficulty or pacing",
    "visuals": "Visual elements",
    "concept": "Creative concept",
    "sequence": "Sequence of events",
    "assets": "Assets to use",
    "unchanged": "Elements that should remain unchanged",
}
STATUSES = ("applied", "default", "adjusted", "not_supported")
# The game's block colours (slots), in the order of `enum BlockColor` (BlockData.cs).
COLOURS = ("Green", "Yellow", "Blue", "Red", "Orange", "Purple", "DarkGreen")
COLOUR_WORDS = {"Green": "green", "Yellow": "yellow", "Blue": "blue", "Red": "red", "Orange": "orange",
                "Purple": "purple", "DarkGreen": "dark green"}
# The game's own colours (the blocks' `_Color`, from the materials), for contrast checks.
GAME_HEX = {"Green": "#14FF17", "Yellow": "#FFCC04", "Blue": "#1469FF", "Red": "#FF3B2A", "Orange": "#FF8000",
            "Purple": "#D007FD", "DarkGreen": "#065C13"}
ENDINGS = ("win", "near_fail", "cliffhanger", "time_out")
MISTAKE_KINDS = ("blocked", "wrong_way", "fidget")
SHAPES = ("any", "open", "narrow_center", "door", "holes", "cross", "ring", "lanes")
PIECES = ("mixed", "small", "big", "long")
STYLES = ("symmetric", "packed", "colourful")
EVENT_ACTIONS = ("leaves", "moves", "stuck", "hesitates")
EVENT_WHEN = ("first", "next", "last")
EVENT_WHICH = ("any", "biggest", "smallest", "longest")
FINISHES = ("auto", "streak")
CURVES = ("even", "speeds_up", "slows_down")
CLOCK_LEFT_RANGE = (1, 3)
MAX_EVENTS = 6
THEMES = ("game", "candy", "pastel", "neon", "dark", "custom")
SEQUENCES = ("standard", "result_first")
ASSET_ROLES = ("logo", "mascot", "sticker", "cursor", "end_art", "end_background", "button")
ASSET_WHEN = ("whole", "hook", "end_card")
ASSET_WHERE = ("auto", "top_left", "top_right", "beside_hook", "end_card")
KEEP = ("level", "gameplay", "timing", "camera", "visuals", "copy", "sequence", "assets", "sound")
CONCEPT_TEXTS = ("hook", "mistake", "fix", "hurry", "cascade", "result", "end_title", "end_fact", "cta")
FORMATS = ("9:16", "1:1", "4:5", "16:9")
LENGTH_RANGE_S = (30.0, 60.0)  # the case asks for 30-60 second creatives (p.2)
# Hesitations a believable play can show per ending (play.plan refuses more).
MAX_HESITATIONS = {"win": 1, "near_fail": 2, "cliffhanger": 1, "time_out": 1}
ZOOM_RANGE = (1.0, 1.12)  # closer crops the side gates of a typical board out of frame
SHIPPED = range(1, 7)
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

# Palettes for the named themes: a display colour per slot, and the background gradient (top,
# bottom). "game" keeps the game's look; "custom" uses only the colours the prompt gave.
PALETTES = {
    "candy": ({"Green": ("#5FD9A0", "mint"), "Yellow": ("#FFE45C", "lemon"), "Blue": ("#4FB3FF", "sky blue"),
               "Red": ("#FF4F8B", "pink"), "Orange": ("#FF8A3D", "tangerine"), "Purple": ("#A066FF", "grape"),
               "DarkGreen": ("#159E62", "green")}, ("#FFD6EC", "#FFF1F8")),
    "pastel": ({"Green": ("#A8E6A1", "mint"), "Yellow": ("#FFF3A0", "butter"), "Blue": ("#8EC5FF", "baby blue"),
                "Red": ("#FF7F98", "rose"), "Orange": ("#FFB86B", "apricot"), "Purple": ("#C79BFF", "lilac"),
                "DarkGreen": ("#4FB58A", "sage")}, ("#F4F1FF", "#FFFFFF")),
    "neon": ({"Green": ("#39FF14", "neon green"), "Yellow": ("#FFF01F", "neon yellow"), "Blue": ("#1F7BFF", "electric blue"),
              "Red": ("#FF0A54", "hot pink"), "Orange": ("#FF7A00", "neon orange"), "Purple": ("#C013FE", "violet"),
              "DarkGreen": ("#00C957", "lime")}, ("#0B0B2B", "#1A0033")),
    "dark": ({}, ("#141428", "#2A2350")),
}
# The game's own closest pair (red and orange) is about 50 apart on this scale; a repainted colour
# closer than this to another colour of the level makes their gates hard to tell apart.
MIN_COLOUR_DISTANCE = 40


def _nullable(t: dict) -> dict:
    out = dict(t)
    out["type"] = [t["type"], "null"]
    if "enum" in out:
        out["enum"] = [*t["enum"], None]
    return out


def _obj(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def _enum(values) -> dict:
    return {"type": "string", "enum": list(values)}


_S, _I, _N, _B = {"type": "string"}, {"type": "integer"}, {"type": "number"}, {"type": "boolean"}

# The JSON schema the planner must fill (strict: every field present, null where unknown).
SCHEMA = _obj({
    "summary": _S,
    "controls": {"type": "array", "items": _obj({
        "control": _enum(CONTROLS), "asked": _nullable(_S), "plan": _S, "status": _enum(STATUSES),
        "why": _nullable(_S)})},
    "assumptions": {"type": "array", "items": _S},
    "channel": _enum(("network", "social")),
    "language": _S,
    "format": _enum(FORMATS),
    "level": _obj({
        "source": _enum(("auto", "shipped", "generate")),
        "shipped": _nullable(_I),
        "shape": _enum(SHAPES),
        "width": _nullable(_I), "height": _nullable(_I), "blocks": _nullable(_I),
        "colours": {"type": "array", "items": _enum(COLOURS)},
        "difficulty": _enum(("any", "easy", "medium", "hard")),
        "label": _nullable(_I),
        "pieces": _enum(PIECES),
        "style": {"type": "array", "items": _enum(STYLES)},
    }),
    "gameplay": _obj({
        "ending": _enum(ENDINGS),
        "mistakes": _nullable(_I),
        "mistake_kinds": {"type": "array", "items": _enum(MISTAKE_KINDS)},
        "hesitations": _nullable(_I),
        "timer_s": _nullable(_I),
        "seed": _nullable(_I),
        "events": {"type": "array", "items": _obj({
            "block": _obj({"colour": _nullable(_enum(COLOURS)), "which": _enum(EVENT_WHICH), "all": _B}),
            "action": _enum(EVENT_ACTIONS), "when": _enum(EVENT_WHEN)})},
        "finish": _enum(FINISHES),
        "clock_left_s": _nullable(_I),
    }),
    "pacing": _obj({"length_s": _N, "tempo": _enum(("calm", "normal", "fast")), "curve": _enum(CURVES)}),
    "visuals": _obj({
        "theme": _enum(THEMES),
        "blocks": {"type": "array", "items": _obj({"slot": _enum(COLOURS), "hex": _S, "name": _S})},
        "background": {"type": "array", "items": _S},
        "board": _nullable(_S),
        "caption_fill": _nullable(_S), "caption_outline": _nullable(_S),
        "camera_zoom": _nullable(_N),
        "cursor": _enum(("ring", "hand", "none")),
        "hud_timer": _B, "hud_level": _B,
    }),
    "concept": _obj({"angle": _S, **{k: _nullable(_S) for k in CONCEPT_TEXTS}}),
    "sequence": _obj({"style": _enum(SEQUENCES), "replay": _B, "result_screen": _B, "end_card": _B}),
    "assets": {"type": "array", "items": _obj({
        "file": _S, "role": _enum(ASSET_ROLES), "when": _enum(ASSET_WHEN), "where": _enum(ASSET_WHERE)})},
    "audio": _obj({"sfx": _B}),
    "keep": {"type": "array", "items": _enum(KEEP)},
    "changed": {"type": "array", "items": {"type": "string"}},
})


def default_brief() -> dict:
    """The brief for an empty prompt."""
    return {
        "summary": "",
        "controls": [{"control": c, "asked": None, "plan": "", "status": "default", "why": None} for c in CONTROLS],
        "assumptions": [],
        "channel": "network",
        "language": "en",
        "format": "9:16",
        "level": {"source": "auto", "shipped": None, "shape": "any", "width": None, "height": None,
                  "blocks": None, "colours": [], "difficulty": "any", "label": None, "pieces": "mixed",
                  "style": [], "edit": None},
        "gameplay": {"ending": "near_fail", "mistakes": None, "mistake_kinds": [], "hesitations": None,
                     "timer_s": None, "seed": None, "events": [], "finish": "auto", "clock_left_s": None},
        "pacing": {"length_s": 30.0, "tempo": "normal", "curve": "even"},
        "visuals": {"theme": "game", "blocks": [], "background": [], "board": None, "caption_fill": None,
                    "caption_outline": None, "camera_zoom": None, "cursor": "ring", "hud_timer": True,
                    "hud_level": True, "names": {}, "names_src": {}},
        "concept": {"angle": "", **{k: None for k in CONCEPT_TEXTS}},
        "sequence": {"style": "standard", "replay": True, "result_screen": True, "end_card": True},
        "assets": [],
        "audio": {"sfx": True},
        "keep": [],
        "changed": [],
    }


def control(brief: dict, name: str) -> dict:
    row = next((c for c in brief["controls"] if c["control"] == name), None)
    if row is None:
        row = {"control": name, "asked": None, "plan": "", "status": "default", "why": None}
        brief["controls"].append(row)
    return row


def adjust(brief: dict, name: str, why: str, status: str = "adjusted") -> None:
    """Record that the engine changed (or cannot do) part of what the prompt asked for."""
    row = control(brief, name)
    if row["status"] != "not_supported" or status == "not_supported":
        row["status"] = status
    if row.get("why") and why not in row["why"]:
        row["why"] = f"{row['why']} {why}"
    elif not row.get("why"):
        row["why"] = why


def engine_note(brief: dict, name: str, text: str, status: str | None = "adjusted") -> None:
    """A note from making this version (the level, the recording, the ad), kept apart from the
    planner's reasons and cleared when the next version is made. status None: a confirmation
    (done as asked) that does not change the row's status."""
    row = control(brief, name)
    notes = row.setdefault("engine", [])
    if text not in notes:
        notes.append(text)
    if status and row["status"] != "not_supported":
        row["status"] = status


def _rgb(h: str) -> tuple[int, int, int]:
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def colour_distance(a: str, b: str) -> float:
    """A rough perceptual distance between two #RRGGBB colours (weighted RGB, 'redmean')."""
    (r1, g1, b1), (r2, g2, b2) = _rgb(a), _rgb(b)
    rm = (r1 + r2) / 2
    return ((2 + rm / 256) * (r1 - r2) ** 2 + 4 * (g1 - g2) ** 2 + (2 + (255 - rm) / 256) * (b1 - b2) ** 2) ** 0.5 / 3


def display_colours(brief: dict) -> dict[str, dict]:
    """The colour each slot is shown in, and its name: the theme's palette, then the prompt's own
    colours on top. Slots the brief does not repaint keep the game's colour and name."""
    vs = brief["visuals"]
    out = {s: {"hex": GAME_HEX[s], "name": COLOUR_WORDS[s], "repainted": False} for s in COLOURS}
    for slot, (hx, name) in PALETTES.get(vs["theme"], ({}, ()))[0].items():
        out[slot] = {"hex": hx, "name": name, "repainted": True}
    for e in vs["blocks"]:
        out[e["slot"]] = {"hex": e["hex"], "name": e["name"] or COLOUR_WORDS[e["slot"]], "repainted": True}
    for slot, name in (vs.get("names") or {}).items():  # names in the ad's language
        if slot in out and name:
            out[slot]["name"] = name
    return out


def background(brief: dict) -> list[str]:
    vs = brief["visuals"]
    if vs["background"]:
        return vs["background"]
    return list(PALETTES.get(vs["theme"], ({}, ()))[1])


def _texts_ok(text: str) -> list[str]:
    problems = copy_problems(text)
    for key in re.findall(r"\{(\w+)\}", text):
        if key not in FACT_KEYS:
            problems.append(f"{{{key}}} is not a fact the recording has")
    return problems


def _complete(b: dict) -> dict:
    """Fill anything missing (a hand-written brief, an older brief) from the defaults."""
    base = default_brief()
    for key, value in base.items():
        if key not in b:
            b[key] = copy.deepcopy(value)
        elif isinstance(value, dict):
            for k, v in value.items():
                b[key].setdefault(k, copy.deepcopy(v))
    seen = {c.get("control") for c in b["controls"]}
    b["controls"] = [c for c in b["controls"] if c.get("control") in CONTROLS]
    for c in CONTROLS:
        if c not in seen:
            control(b, c)
    # one row per control, in the case's order
    rows = {}
    for c in b["controls"]:
        rows.setdefault(c["control"], c)
    b["controls"] = [rows[c] for c in CONTROLS]
    return b


def check(brief: dict, uploads: dict[str, Path] | None = None, sprites: set[str] | None = None) -> dict:
    """The brief, completed and made executable. Every change is written into its control row.
    uploads: the user's uploaded files by name; sprites: the game's UI sprite names."""
    b = _complete(copy.deepcopy(brief))
    uploads = uploads or {}
    sprites = sprites or set()
    lv, gp, pc, vs, cc, sq = (b[k] for k in ("level", "gameplay", "pacing", "visuals", "concept", "sequence"))

    if b["format"] != "9:16":
        adjust(b, "visuals", f"only 9:16 (1080x1920) is rendered in this version, not {b['format']}.",
               status="not_supported")
        b["format"] = "9:16"
    if b["channel"] not in ("network", "social"):
        b["channel"] = "network"
    lang = (b["language"] or "en").strip().lower()
    b["language"] = lang
    # ---- level ----
    if lv["source"] == "shipped" and lv["shipped"] not in SHIPPED:
        adjust(b, "level", f"the game ships levels 1-6, not {lv['shipped']}; a level is chosen instead.")
        lv["source"], lv["shipped"] = "auto", None
    if lv["source"] == "shipped" and lv["difficulty"] in ("medium", "hard"):
        adjust(b, "level", "the shipped levels are tutorial-easy, so a harder level is used instead.")
        lv["source"], lv["shipped"] = "auto", None
    for k, lo, hi in (("width", 4, 9), ("height", 4, 10), ("blocks", 2, 10)):
        v = lv[k]
        if v is not None and not lo <= v <= hi:
            lv[k] = min(hi, max(lo, v))
            adjust(b, "level", f"{k} {v} is outside what the board supports ({lo}-{hi}); {lv[k]} is used.")
    if lv["colours"]:
        lv["colours"] = list(dict.fromkeys(c for c in lv["colours"] if c in COLOURS))
    e = lv.get("edit")
    if e is not None and not (isinstance(e, dict) and e.get("dir") in ("harder", "easier")):
        lv["edit"] = None
    if lv["label"] is not None and not 1 <= lv["label"] <= 9999:
        lv["label"] = None
        adjust(b, "level", "the HUD level number must be 1-9999.")
    # ---- gameplay ----
    for k in ("mistakes", "hesitations"):
        v = gp[k]
        if v is not None and not 0 <= v <= 3:
            gp[k] = min(3, max(0, v))
            adjust(b, "gameplay", f"{k} {v} is not believable in one short level; {gp[k]} is used.")
    gp["mistake_kinds"] = [k for k in dict.fromkeys(gp["mistake_kinds"]) if k in MISTAKE_KINDS]
    if gp["ending"] == "time_out":
        if b["channel"] == "network":
            adjust(b, "gameplay", "a staged fail is only used for social channels (Color Block Jam's network ads "
                                  "avoid fails); the channel is set to social.")
            b["channel"] = "social"
        if lv["difficulty"] == "easy":
            adjust(b, "gameplay", "a time-out on an easy level is not believable (the player would just "
                                  "finish); the level is made medium.")
            lv["difficulty"] = "medium"
    max_hes = MAX_HESITATIONS[gp["ending"]]
    if gp["hesitations"] is not None and gp["hesitations"] > max_hes:
        adjust(b, "gameplay", f"a {gp['ending'].replace('_', '-')} shows at most {max_hes} hesitation"
                              f"{'s' if max_hes != 1 else ''} (more looks staged); {max_hes} is used, not "
                              f"{gp['hesitations']}.")
        gp["hesitations"] = max_hes
    if gp["timer_s"] is not None:
        if gp["ending"] != "win":
            adjust(b, "difficulty_pacing", f"the clock is set by the ending ({gp['ending'].replace('_', '-')} "
                                           f"lands on a planned second), so {gp['timer_s']} s on the clock is not used.")
            gp["timer_s"] = None
        elif not 10 <= gp["timer_s"] <= 300:
            gp["timer_s"] = min(300, max(10, gp["timer_s"]))
            adjust(b, "difficulty_pacing", f"the clock must be 10-300 s; {gp['timer_s']} s is used.")
    # ---- level looks, gameplay events, finish, near-fail clock, pacing curve ----
    if lv["pieces"] not in PIECES:
        lv["pieces"] = "mixed"
    lv["style"] = [x for x in dict.fromkeys(lv["style"]) if x in STYLES]
    if lv["source"] == "shipped" and (lv["pieces"] != "mixed" or lv["style"]):
        adjust(b, "level", "the game's own levels are fixed boards; a level is generated to the description instead.")
        lv["source"], lv["shipped"] = "generate", None
    events = []
    for e in gp["events"] or []:
        blk = e.get("block") or {}
        colour = blk.get("colour")
        if e.get("action") not in EVENT_ACTIONS or (colour is not None and colour not in COLOURS):
            adjust(b, "gameplay", f"the event {e} names no game colour or action the engine knows; it is left out.")
            continue
        events.append({"block": {"colour": colour, "which": blk.get("which") if blk.get("which") in EVENT_WHICH else "any",
                                 "all": bool(blk.get("all"))},
                       "action": e["action"], "when": e.get("when") if e.get("when") in EVENT_WHEN else "next"})
    if len(events) > MAX_EVENTS:
        adjust(b, "gameplay", f"{len(events)} steps are more than one short level can show in order; the first "
                              f"{MAX_EVENTS} are played.")
        events = events[:MAX_EVENTS]
    stuck = [e for e in events if e["action"] == "stuck"]
    if len(stuck) > 3:
        adjust(b, "gameplay", "at most 3 blocks can get stuck in one short level; the first 3 are played.")
        events = [e for e in events if e["action"] != "stuck" or e in stuck[:3]]
    if gp["ending"] in ("cliffhanger", "time_out") and any(e["when"] == "last" for e in events):
        why = ("a cliffhanger stops before the last block leaves" if gp["ending"] == "cliffhanger" else
               "a time-out cuts the last block short of its gate")
        adjust(b, "gameplay", f"{why}, so nothing can leave last; that step is played in its order instead.")
        for e in events:
            e["when"] = "next" if e["when"] == "last" else e["when"]
    gp["events"] = events
    if gp["finish"] not in FINISHES:
        gp["finish"] = "auto"
    if gp["finish"] == "streak" and gp["ending"] not in ("win", "near_fail"):
        adjust(b, "gameplay", f"a satisfying finish (one move, then every block leaves) needs a cleared board; a "
                              f"{gp['ending'].replace('_', '-')} stops before that.")
        gp["finish"] = "auto"
    v = gp["clock_left_s"]
    if v is not None:
        lo_c, hi_c = CLOCK_LEFT_RANGE
        if gp["ending"] != "near_fail":
            adjust(b, "difficulty_pacing", f"seconds left on the clock at the end belong to a near-fail win; this ad is "
                                           f"a {gp['ending'].replace('_', '-')}, so {v} s is not used.")
            gp["clock_left_s"] = None
        elif not lo_c <= v <= hi_c:
            gp["clock_left_s"] = min(hi_c, max(lo_c, v))
            adjust(b, "difficulty_pacing", f"a near-fail ends with {lo_c}-{hi_c} s on the clock (with more, there is no "
                                           f"'Hurry!' moment); {gp['clock_left_s']} s is used.")
    if pc["curve"] not in CURVES:
        pc["curve"] = "even"
    # ---- pacing ----
    lo, hi = LENGTH_RANGE_S
    length = pc["length_s"] if isinstance(pc["length_s"], (int, float)) else 30.0
    if not lo <= length <= hi:
        pc["length_s"] = float(min(hi, max(lo, length)))
        adjust(b, "difficulty_pacing", f"{length:g} s is outside {lo:g}-{hi:g} s; {pc['length_s']:g} s is used.")
    else:
        pc["length_s"] = float(length)
    # ---- visuals ----
    good = []
    for e in vs["blocks"]:
        if e.get("slot") in COLOURS and HEX.match(str(e.get("hex", ""))):
            good.append({"slot": e["slot"], "hex": e["hex"].upper(), "name": (e.get("name") or "").strip().lower()})
        else:
            adjust(b, "visuals", f"block colour {e} needs a game colour and a #RRGGBB value; skipped.")
    vs["blocks"] = list({e["slot"]: e for e in good}.values())
    bg = [h for h in vs["background"] if HEX.match(str(h))]
    if len(bg) != len(vs["background"]) or len(bg) > 2:
        adjust(b, "visuals", "the background takes one or two #RRGGBB colours (top, bottom).")
    vs["background"] = [h.upper() for h in bg[:2]]
    for k in ("board", "caption_fill", "caption_outline"):
        if vs[k] is not None and not HEX.match(str(vs[k])):
            adjust(b, "visuals", f"{k} {vs[k]!r} is not a #RRGGBB colour; the game's own is kept.")
            vs[k] = None
    # The board must stay visible against the background behind it (a near-black board on a
    # black background hides the grid).
    bg_now = background(b)
    if vs["board"] is not None and bg_now and min(colour_distance(vs["board"], h) for h in bg_now) < MIN_COLOUR_DISTANCE:
        adjust(b, "visuals", f"the board colour {vs['board']} would disappear into the background; the game's own "
                             f"board colour is kept.")
        vs["board"] = None
    if vs["camera_zoom"] is not None:
        z = vs["camera_zoom"]
        if not ZOOM_RANGE[0] <= z <= ZOOM_RANGE[1]:
            vs["camera_zoom"] = min(ZOOM_RANGE[1], max(ZOOM_RANGE[0], z))
            adjust(b, "visuals", f"zoom {z:g} would crop the board; {vs['camera_zoom']:g} is used.")
    # Gates must stay tell-apart-able: a repainted colour may not come too close to another
    # colour of the level (the game's own pairs, like green and dark green, are its design).
    slots = lv["colours"] or list(COLOURS)
    reverted = []
    for _ in range(len(COLOURS)):
        shown = display_colours(b)
        clash = next(((s1, s2) for i, s1 in enumerate(slots) for s2 in slots[i + 1:]
                      if (shown[s1]["repainted"] or shown[s2]["repainted"])
                      and colour_distance(shown[s1]["hex"], shown[s2]["hex"]) < MIN_COLOUR_DISTANCE), None)
        if clash is None:
            break
        s1, s2 = clash
        back = s2 if shown[s2]["repainted"] else s1  # undo one repaint and look again
        reverted.append(f"{shown[back]['name']} ({COLOUR_WORDS[back]})")
        vs["blocks"] = [e for e in vs["blocks"] if e["slot"] != back]
        if vs["theme"] not in ("game", "custom", "dark"):
            vs["blocks"].append({"slot": back, "hex": GAME_HEX[back], "name": COLOUR_WORDS[back]})
    if reverted:
        adjust(b, "visuals", f"blocks of different colours must stay easy to tell apart (each has its own gate), so "
                             f"these keep the game's own colour: {', '.join(reverted)}.")
    # A repainted block must also stand out from the background behind the board.
    bg_now = background(b)
    faded = []
    for e in list(vs["blocks"]):
        if bg_now and min(colour_distance(e["hex"], h) for h in bg_now) < MIN_COLOUR_DISTANCE:
            faded.append(f"{e['name'] or COLOUR_WORDS[e['slot']]} ({COLOUR_WORDS[e['slot']]})")
            vs["blocks"] = [x for x in vs["blocks"] if x["slot"] != e["slot"]]
            if vs["theme"] not in ("game", "custom", "dark"):
                vs["blocks"].append({"slot": e["slot"], "hex": GAME_HEX[e["slot"]], "name": COLOUR_WORDS[e["slot"]]})
    if faded:
        adjust(b, "visuals", f"a block the colour of the background would vanish into it, so these keep the game's "
                             f"own colour: {', '.join(faded)}.")
    if vs["cursor"] == "hand" and not any(a["role"] == "cursor" for a in b["assets"]):
        b["assets"].append({"file": "builtin:hand", "role": "cursor", "when": "whole", "where": "auto"})
    elif vs["cursor"] != "hand":
        b["assets"] = [a for a in b["assets"] if a["file"] != "builtin:hand"]  # a ring or no cursor now
    # ---- concept: every text through the copy guard and the facts ----
    for k in CONCEPT_TEXTS:
        t = cc[k]
        if t is None:
            continue
        problems = _texts_ok(t)
        if problems:
            cc[k] = None
            adjust(b, "concept", f"the {k} text {t!r} was replaced by the default: {problems[0]}.")
    if cc["cta"] == "":
        cc["cta"] = None
        adjust(b, "concept", "the button text cannot be empty; PLAY NOW is used.")
    # ---- sequence ----
    if sq["style"] == "result_first" and gp["ending"] == "cliffhanger":
        sq["style"] = "standard"
        adjust(b, "sequence", "a cliffhanger has no result to show first; the standard order is used.")
    if not sq["end_card"]:
        adjust(b, "sequence", "the end card holds the call to action; it stays (shortest: 3 s).")
        sq["end_card"] = True
    # ---- assets ----
    kept = []
    for a in b["assets"]:
        f = a.get("file", "")
        if f.startswith("builtin:") or f in uploads or f in sprites:
            kept.append(a)
        else:
            adjust(b, "assets", f"{f!r} was not uploaded and is not one of the game's sprites; it was left out.",
                   status="adjusted" if kept else "not_supported")
    b["assets"] = kept
    b["keep"] = [k for k in dict.fromkeys(b["keep"]) if k in KEEP]
    return b


# ---------- which fields a prompt may change ----------

# Field groups: what the planner declares it changed ("changed" in the brief), the control each
# belongs to, and the brief fields in it.
GROUPS = {
    "level.source": ("level", [("level", "source"), ("level", "shipped")]),
    "level.shape": ("level", [("level", "shape")]),
    "level.size": ("level", [("level", "width"), ("level", "height")]),
    "level.blocks": ("level", [("level", "blocks")]),
    "level.colours": ("level", [("level", "colours")]),
    "level.label": ("level", [("level", "label")]),
    "level.difficulty": ("difficulty_pacing", [("level", "difficulty"), ("level", "edit")]),
    "level.pieces": ("level", [("level", "pieces")]),
    "level.style": ("level", [("level", "style")]),
    "gameplay.ending": ("gameplay", [("gameplay", "ending")]),
    "gameplay.mistakes": ("gameplay", [("gameplay", "mistakes"), ("gameplay", "mistake_kinds")]),
    "gameplay.hesitations": ("gameplay", [("gameplay", "hesitations")]),
    "gameplay.retake": ("gameplay", [("gameplay", "seed")]),
    "gameplay.clock": ("difficulty_pacing", [("gameplay", "timer_s")]),
    "gameplay.events": ("gameplay", [("gameplay", "events")]),
    "gameplay.finish": ("gameplay", [("gameplay", "finish")]),
    "gameplay.clock_left": ("gameplay", [("gameplay", "clock_left_s")]),
    "pacing.length": ("difficulty_pacing", [("pacing", "length_s")]),
    "pacing.tempo": ("difficulty_pacing", [("pacing", "tempo")]),
    "pacing.curve": ("difficulty_pacing", [("pacing", "curve")]),
    "channel": ("gameplay", [("channel",)]),
    "visuals.colours": ("visuals", [("visuals", "theme"), ("visuals", "blocks")]),
    "visuals.background": ("visuals", [("visuals", "background")]),
    "visuals.board": ("visuals", [("visuals", "board")]),
    "visuals.captions": ("visuals", [("visuals", "caption_fill"), ("visuals", "caption_outline")]),
    "visuals.zoom": ("visuals", [("visuals", "camera_zoom")]),
    "visuals.cursor": ("visuals", [("visuals", "cursor")]),
    "visuals.hud": ("visuals", [("visuals", "hud_timer"), ("visuals", "hud_level")]),
    "format": ("visuals", [("format",)]),
    "language": ("concept", [("language",)]),
    **{f"concept.{k}": ("concept", [("concept", k)]) for k in CONCEPT_TEXTS},
    "sequence": ("sequence", [("sequence",)]),
    "assets": ("assets", [("assets",)]),
    "audio": ("assets", [("audio",)]),
}  # "keep" is not a group: it is always this prompt's own list (see merge)
# Plain names for the groups, for what the user reads (never a field path).
GROUP_NAMES = {
    "level.source": "which level is used", "level.shape": "the board's shape", "level.size": "the board's size",
    "level.blocks": "the number of blocks", "level.colours": "the board's colours", "level.label": "the level number",
    "level.difficulty": "the level's difficulty", "level.pieces": "the blocks' shapes", "level.style": "the board's look",
    "gameplay.ending": "the ending", "gameplay.mistakes": "the mistakes", "gameplay.hesitations": "the hesitations",
    "gameplay.retake": "a new take of the play", "gameplay.clock": "the clock", "gameplay.events": "the order of moves",
    "gameplay.finish": "the finish", "gameplay.clock_left": "the seconds left at the end", "pacing.length": "the ad's length",
    "pacing.tempo": "the tempo", "pacing.curve": "the change of pace", "channel": "the channel",
    "visuals.colours": "the block colours", "visuals.background": "the background", "visuals.board": "the board colour",
    "visuals.captions": "the caption colours", "visuals.zoom": "the camera zoom", "visuals.cursor": "the cursor",
    "visuals.hud": "the HUD", "format": "the format", "language": "the language", "concept.hook": "the hook",
    "concept.mistake": "the caption on the mistake", "concept.fix": "the caption on the fix",
    "concept.hurry": "the 'hurry' caption", "concept.cascade": "the caption on the fast finish",
    "concept.result": "the caption on the result", "concept.end_title": "the end card's title",
    "concept.end_fact": "the end card's line", "concept.cta": "the button's text", "sequence": "the sequence of parts",
    "assets": "the pictures", "audio": "the sound",
}
# Groups a model tends to fill without being asked (copy, board sizes, colours, a level number,
# assets): accepted only when declared AND the prompt's words show it asked for them.
PRONE = {"level.size", "level.blocks", "level.colours", "level.label", "assets", "level.pieces", "level.style", "level.shape",
         "level.difficulty", "gameplay.retake",
         "gameplay.events", "gameplay.finish", "gameplay.clock_left", "pacing.curve", "pacing.length",
         *(f"concept.{k}" for k in CONCEPT_TEXTS)}
COLOUR_WORDS_ANY = ("red", "blue", "green", "yellow", "orange", "purple", "pink", "teal", "mint", "lemon", "lilac",
                    "violet", "gold", "black", "white", "brown", "grey", "gray", "cyan", "magenta", "lime", "navy",
                    "turquoise", "peach", "rose", "colour", "color", "candy", "pastel", "neon")
NUMBER_WORDS_ANY = ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "few", "many",
                    "lots", "dozen")
SIZE_WORDS = ("big", "large", "small", "tiny", "huge", "wide", "tall", "narrow board", "compact")
DIFFICULTY_WORDS = ("easy", "easier", "simple", "hard", "harder", "difficult", "difficulty", "tough", "tricky",
                    "challenging", "challenge", "medium", "moderate", "impossible", "beginner", "beginners", "kid",
                    "kids", "child", "children", "novice", "expert", "brutal", "insane", "relaxing", "relax", "calm",
                    "asmr", "rage", "frustrating", "frustration", "nightmare", "brain", "genius", "nothing can leave",
                    "level up", "makes you think", "make you think", "nobody can solve", "no one can solve",
                    "can't solve", "cannot solve", "experienced", "pro", "pros", "advanced", "intense", "chill",
                    "laid-back", "laid back", "relaxed", "hardcore", "casual")
SHAPE_WORDS = ("narrow", "centre", "center", "middle", "waist", "bottleneck", "hourglass", "door", "doorway", "room",
               "rooms", "gap", "hole", "holes", "pillar", "pillars", "obstacle", "obstacles", "cross", "plus", "ring",
               "donut", "doughnut", "loop", "lane", "lanes", "corridor", "corridors", "shape", "shaped", "open",
               "rectangle", "square", "layout", "structure", "wall", "walls", "maze", "empty", "plain", "corner",
               "corners", "column", "columns", "row", "rows")
PIECE_WORDS = ("big", "bigger", "chunky", "large", "huge", "giant", "small", "smaller", "tiny", "little", "long",
               "longer", "bar", "bars", "stick", "sticks", "line", "lines", "short")
STYLE_WORDS = ("symmetric", "symmetrical", "symmetry", "mirror", "mirrored", "packed", "full", "jam", "jammed",
               "crowded", "dense", "busy", "colourful", "colorful", "rainbow", "every colour", "every color",
               "all colours", "all colors", "all the colours", "all the colors", "visually", "pretty", "beautiful",
               "interesting", "eye-catching", "eye catching", "striking", "satisfying to look", "looks", "gorgeous",
               "stunning", "lots of colours", "lots of colors", "many colours", "many colors", "eye candy")
ORDER_WORDS = ("first", "then", "last", "before", "after", "order", "one by one", "colour by colour",
               "color by color", "finally", "next", "followed", "sequence", "until", "stuck", "hesitate",
               "hesitates", "doubt", "pick up", "picks up", "picked up", "grab", "grabs", "out of the way",
               "start", "starts", "start with", "begin", "begins", "end", "ends", "at the end", "very end",
               "finish with", "finishes with", "escape", "escapes", "exit", "exits", "aside", "save", "saved",
               "blocked", "gets blocked", "trapped", "can't reach", "cannot reach")
BLOCK_WORDS = ("biggest", "smallest", "longest", "big", "small", "long", "block", "blocks", "piece", "one")
FINISH_WORDS = ("satisfying", "satisfy", "one move", "single move", "chain", "cascade", "domino", "combo", "streak",
                "in a row", "fly out", "flies out", "frees", "free them", "unlock", "relaxing", "relax", "asmr",
                "calming", "calm", "oddly", "smooth", "speedrun", "flow", "one after another", "one after the other")
CURVE_WORDS = ("tension", "tense", "build", "builds", "building", "rise", "rising", "rises", "escalate", "escalates",
               "speeds up", "speed up", "speeding up", "speeding", "faster", "faster and faster", "gets faster",
               "getting faster", "accelerate", "accelerates", "accelerating", "quicker and quicker", "pace",
               "slows down", "slow down", "slowing down", "slowing", "slower", "slower and slower", "gets slower",
               "build up", "builds up", "ramp",
               "start slow", "starts slow", "slow start", "start fast", "starts fast", "picks up pace", "pick up pace")
RETAKE_WORDS = ("take", "retake", "re-take", "reshoot", "re-shoot", "different moves", "other moves", "new moves",
                "another version", "variation", "variant", "shuffle", "different play", "play it differently",
                "different way", "another way", "differently", "again", "seed", "random")
HARDER_WORDS = ("harder", "more difficult", "tougher", "trickier", "more challenging", "more of a challenge",
                "less easy", "make it hard", "make it difficult")
EASIER_WORDS = ("easier", "simpler", "less difficult", "less hard", "less tricky", "not so hard", "too hard",
                "make it easy", "more relaxed")


# Words that make a "harder"/"easier" clause about the ad's copy or pictures, not the level.
NOT_LEVEL_WORDS = ("hook", "caption", "captions", "text", "texts", "read", "title", "button", "cta", "logo", "picture",
                   "image", "font", "word", "words", "say", "says", "copy", "ignore", "spot", "see", "notice",
                   "message", "line", "tagline", "slogan", "headline", "end card", "background", "colours", "colors",
                   "eyes", "look", "looks")


def clauses(text: str) -> list[str]:
    """A prompt cut into clauses: at punctuation and at "but", "and", "except", "then", "while"."""
    return [c for c in re.split(r"[.,;:!?\n]|\b(?:but|and|except|then|while|however|also)\b", text.lower()) if c.strip()]


def relative_difficulty(prompt: str) -> str | None:
    """'harder' or 'easier' when an edit asks to change the level's difficulty relative to what it
    has. A clause about copy or pictures ("make the hook harder to ignore") does not count."""
    h = e = False
    for cl in clauses(prompt):
        if _has_word(cl, NOT_LEVEL_WORDS):
            continue
        h, e = h or _has_word(cl, HARDER_WORDS), e or _has_word(cl, EASIER_WORDS)
    return "harder" if h and not e else "easier" if e and not h else None


COPY_WORDS = ("hook", "caption", "text", "copy", "say", "says", "tone", "angle", "line", "title", "button", "cta",
              "message", "slogan", "tagline", "ask", "question", "headline", "word", "write", "end card")


def _get(d: dict, path: tuple):
    for k in path:
        d = d[k]
    return d


def _set(d: dict, path: tuple, value) -> None:
    for k in path[:-1]:
        d = d[k]
    d[path[-1]] = value


def _has_word(text: str, words) -> bool:
    return any(re.search(rf"\b{re.escape(w)}\b", text) for w in words)


QUOTED = re.compile(r"[\"“«]([^\"”»]{2,})[\"”»]|(?<![a-z])['‘]([^'’]{2,})['’](?![a-z])")


ENGLISH_WORDS = {"a", "an", "the", "and", "with", "but", "then", "of", "in", "on", "to", "it", "this", "that", "is",
                 "make", "keep", "level", "block", "blocks", "player", "same", "ad", "show", "no", "not", "for",
                 "at", "as", "all", "one", "first", "last", "hard", "easy", "fast", "slow", "seconds", "second",
                 "before", "after", "where", "wins", "win", "fails", "fail", "colour", "color", "use", "our"}


def foreign(prompt: str) -> bool:
    """True when the prompt is not written in English (the evidence word lists are English, so a
    request in another language is taken as the planner read it)."""
    words = re.findall(r"[^\W\d_]+", prompt.lower())
    if len(words) < 3:
        return False
    return sum(w in ENGLISH_WORDS for w in words) / len(words) < 0.12


def _evidence(group: str, prompt: str, new: dict) -> str | None:
    """None if the prompt's words support changing this group, else the reason it is not used."""
    if foreign(prompt):
        return None
    # The game's name is not a request: "Color Block Jam" says nothing about a "jam"-packed board.
    text = re.sub(r"\bcolou?r[\s-]*block[\s-]*jam\b", " ", prompt.lower())
    # numbers that are lengths, clocks or counts of other things are not board sizes
    sized = re.sub(r"\d+(\.\d+)?\s*-?\s*(s|sec|secs|second|seconds|min|minute|minutes|%|percent)\b", " ", text)
    sized = re.sub(r"\b(level|lvl)\s*\d+", " ", sized)
    if group == "level.size":
        if re.search(r"\d\s*(x|by|×)\s*\d", sized) or _has_word(sized, ("big", "large", "small", "tiny", "huge", "wide",
                                                                           "tall", "compact")):
            return None
        return "the prompt gives no board size"
    if group == "level.blocks":
        if re.search(r"\d", sized) or _has_word(sized, NUMBER_WORDS_ANY):
            return None
        return "the prompt gives no block count"
    if group == "level.colours":
        if _has_word(text, COLOUR_WORDS_ANY + ("colours", "colors")):
            return None
        return "the prompt names no colours"
    if group == "level.label":
        label = new["level"]["label"]
        return None if label is None or str(label) in text else "the prompt gives no level number"
    if group == "level.difficulty":
        return None if _has_word(text, DIFFICULTY_WORDS) else "the prompt asks for no difficulty"
    if group == "gameplay.retake":
        return None if _has_word(text, RETAKE_WORDS) else "the prompt asks for no new take of the play"
    if group == "pacing.length":
        clock = r"(?!\s*(left|remaining|on the clock|to spare|to go))"  # "2 seconds left" is the clock, not the ad
        if re.search(rf"\d+\s*-?\s*(s|sec|secs|second|seconds|min|minute|minutes)\b{clock}", text) or \
                _has_word(text, ("short", "shorter", "long", "longer", "minute", "half a minute", "quick ad", "brief",
                                 "snappy", "quick one", "shortest", "longest")):
            return None
        return "the prompt gives no length for the ad"
    if group == "level.shape":
        return None if _has_word(text, SHAPE_WORDS) else "the prompt asks for no board shape"
    if group == "level.pieces":
        return None if _has_word(text, PIECE_WORDS) else "the prompt says nothing about the blocks' shapes"
    if group == "level.style":
        return None if _has_word(text, STYLE_WORDS) else "the prompt asks for no particular look of the board"
    if group == "gameplay.events":
        if _has_word(text, ORDER_WORDS) and (_has_word(text, COLOUR_WORDS_ANY) or _has_word(text, BLOCK_WORDS)):
            return None
        return "the prompt names no order of moves for particular blocks"
    if group == "gameplay.finish":
        return None if _has_word(text, FINISH_WORDS) else "the prompt asks for no particular finish"
    if group == "gameplay.clock_left":
        if re.search(r"\d+\s*(s|sec|secs|second|seconds)\b", text) or re.search(r"\b0?0:0\d\b", text) or \
                _has_word(text, ("one second", "two seconds", "three seconds", "last second", "a second")):
            return None
        return "the prompt gives no seconds left on the clock"
    if group == "pacing.curve":
        return None if _has_word(text, CURVE_WORDS) else "the prompt asks for no change of pace over the video"
    if group.startswith("concept."):
        from .reference import is_reference_prompt
        if QUOTED.search(prompt) or _has_word(text, COPY_WORDS + ("captions", "texts", "words", "says", "saying")):
            return None
        if is_reference_prompt(prompt):
            return None  # a reference's idea, hook and tone are an ask for copy in that spirit
        return "the prompt asks for no wording"
    return None


def asset_slot(a: dict) -> str:
    """The picture slot an asset fills: logo, hook_icon, end_art, button, end_background, cursor."""
    role, when = a.get("role"), a.get("when")
    if role == "end_art" or (role in ("mascot", "sticker") and when == "end_card"):
        return "end_art"
    if role in ("mascot", "sticker"):
        return "hook_icon"
    return str(role)


REMOVE_WORDS = ("remove", "removed", "delete", "drop", "get rid", "hide", "take out", "take away", "lose")
SLOT_WORDS = {"logo": ("logo", "brand", "watermark"),
              "hook_icon": ("icon", "stopwatch", "clock icon", "sticker", "hook icon", "next to the hook",
                            "beside the hook"),
              "end_art": ("coin", "coins", "coin pile", "end card picture", "end-card picture", "picture", "art",
                          "artwork", "image", "mascot", "character", "object", "end card"),
              "button": ("button", "cta"), "end_background": ("background",),
              "cursor": ("cursor", "hand", "finger", "pointer")}


def asks_removal(text: str, slot: str) -> bool:
    """Whether the prompt asks to remove a picture slot ("remove the logo", "no logo", "without
    the stopwatch")."""
    words = SLOT_WORDS.get(slot, ())
    alt = "|".join(re.escape(w) for w in words)
    # Clauses end at punctuation and "but"/"except", not at "and" ("remove the caption and the logo").
    parts = [c for c in re.split(r"[.,;:!?\n]|\b(?:but|except|however|while)\b", text) if c.strip()]
    for cl in parts:  # the remove word and the slot word in one clause, and no "keep" there
        if not _has_word(cl, words) or _has_word(cl, ("keep", "same", "preserve", "leave", "stay", "stays")):
            continue
        if (_has_word(cl, REMOVE_WORDS) or re.search(rf"\b(no|without)\s+(the\s+|a\s+|our\s+|any\s+)?({alt})\b", cl)
                or re.search(r"\btake\b.*\bout\b|\b(don't|do not|no longer) (want|need)\b", cl)):
            return True
    return False


def _merge_assets(base: list, new: list, prompt: str, declared: bool, attached) -> tuple[list, list[str], list[str]]:
    """Assets merge slot by slot, so replacing one picture never drops another. A slot the planner
    left out keeps its picture unless the prompt asks to remove it (file "builtin:none" removes
    one on purpose). A changed slot is taken when the change was declared, or uses a file
    attached to this prompt. Returns (assets, slots taken, reasons for slots not taken)."""
    text = prompt.lower()
    bs = {asset_slot(a): a for a in base}
    ns = {asset_slot(a): a for a in new}
    out, took, why = dict(bs), [], []
    for slot in dict.fromkeys([*bs, *ns]):
        b, n = bs.get(slot), ns.get(slot)
        if b == n:
            continue
        if n is None:  # left out: removed only if the prompt says so
            if asks_removal(text, slot):
                del out[slot]
                took.append(slot)
            else:
                why.append(f"assets.{slot}: left out by the planner, but the prompt does not ask to remove it; kept")
            continue
        if declared or n.get("file") in attached or (n.get("file") == "builtin:none" and asks_removal(text, slot)):
            out[slot] = copy.deepcopy(n)
            took.append(slot)
        else:
            why.append(f"assets.{slot}: not among the changes the prompt asked for")
    return list(out.values()), took, why


def merge(base: dict, new: dict, prompt: str, attached=()) -> tuple[dict, list[str]]:
    """The planner's brief, keeping only what the prompt asked to change: every other field keeps
    its value in `base` (the defaults for a new ad, the current version for an edit). The case:
    "only the requested element should change" (p.7). Returns the brief and what was not taken,
    with the reason."""
    merged = copy.deepcopy(base)
    for k in ("summary", "controls", "assumptions"):
        merged[k] = copy.deepcopy(new.get(k, merged.get(k)))
    merged["concept"]["angle"] = new["concept"].get("angle", "")
    declared = set(new.get("changed") or [])
    asked = {c["control"] for c in new["controls"] if c.get("asked") and c["control"] != "unchanged"}
    lang_changed = new.get("language") != base.get("language")
    # What to keep is always this prompt's own list: never inherited from the version being
    # edited (it would contradict the next edit) and never gated (it changes nothing by itself).
    merged["keep"] = [k for k in dict.fromkeys(new.get("keep") or []) if k in KEEP]
    taken, dropped = [], []
    for group, (ctl, paths) in GROUPS.items():
        if all(_get(new, p) == _get(base, p) for p in paths):
            continue
        if group == "assets":
            merged["assets"], took, why = _merge_assets(base["assets"], new["assets"], prompt, group in declared,
                                                        set(attached))
            if took:
                taken.append(group)
            dropped += why
            continue
        if group in PRONE:
            ok = group in declared or (group.startswith("concept.") and lang_changed)
            why = _evidence(group, prompt, new) if ok else "not among the changes the prompt asked for"
            if group.startswith("concept.") and lang_changed:
                why = None  # a new language rewrites the copy
        else:
            ok = group in declared or ctl in asked
            why = None if ok else "not among the changes the prompt asked for"
        if why is None:
            for path in paths:
                _set(merged, path, copy.deepcopy(_get(new, path)))
            taken.append(group)
        else:
            dropped.append(f"{group}: {why}")
    merged["changed"] = taken
    return merged, dropped


def changed_groups(old: dict, new: dict) -> list[str]:
    """The field groups whose fields differ between two briefs."""
    return [g for g, (_, paths) in GROUPS.items() if any(_get(old, p) != _get(new, p) for p in paths)]


def changed_controls(old: dict, new: dict) -> list[str]:
    """The controls whose fields differ between two briefs, in the case's order."""
    out = []
    for group, (ctl, paths) in GROUPS.items():
        if any(_get(old, p) != _get(new, p) for p in paths) and ctl not in out:
            out.append(ctl)
    return sorted(out, key=CONTROLS.index)


SCHEMA["properties"]["changed"] = {"type": "array", "items": _enum(GROUPS),
                                   "description": "Every field group the request asks to set or change."}
