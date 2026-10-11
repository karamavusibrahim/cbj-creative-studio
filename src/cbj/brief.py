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
SHAPES = ("any", "open", "narrow_center", "door", "holes")
THEMES = ("game", "candy", "pastel", "neon", "dark", "custom")
SEQUENCES = ("standard", "result_first")
ASSET_ROLES = ("logo", "mascot", "sticker", "cursor", "end_art", "end_background")
ASSET_WHEN = ("whole", "hook", "end_card")
ASSET_WHERE = ("auto", "top_left", "top_right", "beside_hook", "end_card")
KEEP = ("level", "gameplay", "timing", "camera", "visuals", "copy", "sequence", "assets", "sound")
CONCEPT_TEXTS = ("hook", "mistake", "fix", "hurry", "cascade", "result", "end_title", "end_fact", "cta")
FORMATS = ("9:16", "1:1", "4:5", "16:9")
LENGTH_RANGE_S = (15.0, 60.0)
ZOOM_RANGE = (1.0, 1.6)
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
    }),
    "gameplay": _obj({
        "ending": _enum(ENDINGS),
        "mistakes": _nullable(_I),
        "mistake_kinds": {"type": "array", "items": _enum(MISTAKE_KINDS)},
        "hesitations": _nullable(_I),
        "timer_s": _nullable(_I),
        "seed": _nullable(_I),
    }),
    "pacing": _obj({"length_s": _N, "tempo": _enum(("calm", "normal", "fast"))}),
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
                  "blocks": None, "colours": [], "difficulty": "any", "label": None},
        "gameplay": {"ending": "near_fail", "mistakes": None, "mistake_kinds": [], "hesitations": None,
                     "timer_s": None, "seed": None},
        "pacing": {"length_s": 30.0, "tempo": "normal"},
        "visuals": {"theme": "game", "blocks": [], "background": [], "board": None, "caption_fill": None,
                    "caption_outline": None, "camera_zoom": None, "cursor": "ring", "hud_timer": True,
                    "hud_level": True},
        "concept": {"angle": "", **{k: None for k in CONCEPT_TEXTS}},
        "sequence": {"style": "standard", "replay": True, "result_screen": True, "end_card": True},
        "assets": [],
        "audio": {"sfx": True},
        "keep": [],
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


def engine_note(brief: dict, name: str, text: str, status: str = "adjusted") -> None:
    """A note from making this version (the level, the recording, the ad), kept apart from the
    planner's reasons and cleared when the next version is made."""
    row = control(brief, name)
    notes = row.setdefault("engine", [])
    if text not in notes:
        notes.append(text)
    if row["status"] != "not_supported":
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
    if gp["timer_s"] is not None:
        if gp["ending"] != "win":
            adjust(b, "difficulty_pacing", f"the clock is set by the ending ({gp['ending'].replace('_', '-')} "
                                           f"lands on a planned second), so {gp['timer_s']} s on the clock is not used.")
            gp["timer_s"] = None
        elif not 10 <= gp["timer_s"] <= 300:
            gp["timer_s"] = min(300, max(10, gp["timer_s"]))
            adjust(b, "difficulty_pacing", f"the clock must be 10-300 s; {gp['timer_s']} s is used.")
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
    if vs["cursor"] == "hand" and not any(a["role"] == "cursor" for a in b["assets"]):
        b["assets"].append({"file": "builtin:hand", "role": "cursor", "when": "whole", "where": "auto"})
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


# The brief fields each control owns (a path of keys; one key = the whole section). An edit may
# only change the fields of the controls it asks about.
OWNS = {
    "level": [("level", k) for k in ("source", "shipped", "shape", "width", "height", "blocks", "colours", "label")],
    "gameplay": [("gameplay", k) for k in ("ending", "mistakes", "mistake_kinds", "hesitations", "seed")],
    "difficulty_pacing": [("level", "difficulty"), ("pacing", "length_s"), ("pacing", "tempo"), ("gameplay", "timer_s")],
    "visuals": [("visuals", k) for k in ("theme", "blocks", "background", "board", "caption_fill", "caption_outline",
                                         "camera_zoom", "cursor", "hud_timer", "hud_level")] + [("format",)],
    "concept": [("concept",)],
    "sequence": [("sequence",)],
    "assets": [("assets",), ("audio",)],
}
# Fields a prompt can reach through more than one control: "a difficult level" may be read as the
# level control, "solves it fast" as gameplay, "use a hand" as assets, "no sound" as concept. Such
# a field is restored only if none of its controls was asked about.
ALSO = {("level", "difficulty"): ("level",), ("pacing", "tempo"): ("gameplay",), ("gameplay", "timer_s"): ("gameplay",),
        ("visuals", "cursor"): ("assets",), ("assets",): ("visuals",), ("audio",): ("concept",)}


def _get(d: dict, path: tuple):
    for k in path:
        d = d[k]
    return d


def _set(d: dict, path: tuple, value) -> None:
    for k in path[:-1]:
        d = d[k]
    d[path[-1]] = value


def merge_edit(old: dict, new: dict, keep_plans: bool = True) -> tuple[dict, list[str]]:
    """An edit may only change what the edit prompt asked about: the fields of every control the
    planner did not mark as asked are restored from the previous version (the case's "only the
    requested element should change", p.7). Returns the merged brief and what was restored."""
    merged = copy.deepcopy(new)
    asked = {c["control"] for c in new["controls"] if c.get("asked")}
    restored = []
    for ctl, paths in OWNS.items():
        if ctl in asked:
            continue
        for path in paths:
            if any(o in asked for o in ALSO.get(path, ())):
                continue
            if _get(merged, path) != _get(old, path):
                _set(merged, path, copy.deepcopy(_get(old, path)))
                restored.append(f"{'.'.join(path)} (not asked about: {CONTROL_TITLES[ctl].lower()})")
        if keep_plans:
            control(merged, ctl)["plan"] = control(old, ctl).get("plan") or control(merged, ctl)["plan"]
    merged["keep"] = sorted(set(new.get("keep", [])) & set(KEEP))
    return merged, restored


def changed_controls(old: dict, new: dict) -> list[str]:
    """The controls whose fields differ between two briefs."""
    return [ctl for ctl, paths in OWNS.items() if any(_get(old, p) != _get(new, p) for p in paths)]
