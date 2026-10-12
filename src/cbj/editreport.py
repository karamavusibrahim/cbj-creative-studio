"""The edit report: what an edit kept and what it changed, item by item.

The case (p.7) asks that an edit preserve the original's gameplay, timing, camera, composition,
sequence, visual structure and other assets, and change only the requested element. This module
measures each of those between two versions of a creative, from what the versions stored: the
level file, the play script and the game's own log of the recording, the job the recorder ran,
ad.json and the compositor's record of every layer and frame (compose.json). Captions and sound
get rows of their own.

Every difference found is classified on its own:
- asked: the edit asked for exactly this (its field group names it);
- explained: a consequence of what was asked, proven by a check on the measured difference, not
  assumed (a caption counts as "names the colours as shown" only if its template is the same and
  only the facts filled into it changed; a moved caption counts as "waits for the longer hook"
  only if the hook was asked and is longer; a part counts as "moved up" only if a part before it
  was asked to go);
- unexplained: anything else. One unexplained difference makes the row CHANGED WITHOUT BEING
  ASKED and fails the edit.
A row is kept, changed as asked, changed because of the asked change, or not asked. Exact facts
come first (hashes, moves, frame numbers), pixels last.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ITEMS = (("gameplay", "Gameplay"), ("timing", "Timing"), ("camera", "Camera"), ("composition", "Composition"),
         ("sequence", "Sequence"), ("visual", "Visual structure"), ("assets", "Other assets"),
         ("copy", "Captions"), ("sound", "Sound"))
TITLES = dict(ITEMS)
STATUS_WORDS = {"kept": "kept", "asked": "changed, as asked", "side_effect": "changed, because of the asked change",
                "not_asked": "CHANGED WITHOUT BEING ASKED", "changed": "differs"}

LEVEL_GROUPS = ("level.source", "level.shape", "level.size", "level.blocks", "level.colours", "level.difficulty",
                "level.pieces", "level.style")
PLAY_GROUPS = ("gameplay.ending", "gameplay.mistakes", "gameplay.hesitations", "gameplay.retake",
               "gameplay.events", "gameplay.finish", "channel")
PACE_GROUPS = ("pacing.length", "pacing.tempo", "pacing.curve", "gameplay.clock", "gameplay.clock_left")
RECORDING_LOOKS = ("visuals.colours", "visuals.background", "visuals.board", "visuals.hud", "level.label",
                   "visuals.zoom")
LAYER_OF = {"concept.hook": "hook", "concept.mistake": "cap_mistake", "concept.fix": "cap_fix",
            "concept.hurry": "cap_hurry", "concept.cascade": "cap_cascade", "concept.result": "cap_result",
            "concept.end_title": "end_title", "concept.end_fact": "end_fact", "concept.cta": "end_cta"}
TEXT_LAYERS = tuple(LAYER_OF.values()) + ("replay_tag",)
BAND_CAPTIONS = ("hook", "cap_mistake", "cap_fix", "cap_hurry", "cap_cascade")
ASSET_SLOTS = (("logo", "the logo"), ("hook_icon", "the icon beside the hook"), ("end_art", "the end-card picture"),
               ("button", "the button"), ("end_background", "the end card's background"),
               ("cursor", "the cursor"))
SLOT_LAYERS = {"logo": ("logo", "logo_end"), "hook_icon": ("hook",), "end_art": ("end_art",), "button": ("end_cta",),
               "cursor": ("cursor",), "end_background": ()}
PART_OF = {"replay": "replay", "result_screen": "result", "style": "teaser"}  # sequence field -> ad part
LAYER_PART = {"replay_tag": "replay", "cap_result": "result"}  # layers that exist with a part
PLAY_LAYERS = ("cap_mistake", "cap_fix", "cap_hurry", "urgency", "cap_cascade", "cap_result", "replay_tag")
GROUP_NAMES = {"concept.hook": "the hook", "concept.mistake": "the mistake caption", "concept.fix": "the fix caption",
               "concept.hurry": "the 'hurry' caption", "concept.cascade": "the finish caption",
               "concept.result": "the result caption", "concept.end_title": "the end card's title",
               "concept.end_fact": "the end card's line", "concept.cta": "the button's text",
               "assets": "pictures", "audio": "sound", "sequence": "the ad's parts", "language": "language",
               "visuals.colours": "block colours", "visuals.background": "background", "visuals.board": "board colour",
               "visuals.captions": "caption colours", "visuals.zoom": "camera zoom", "visuals.cursor": "cursor",
               "visuals.hud": "HUD", "level.label": "level number", "level.difficulty": "difficulty",
               "gameplay.ending": "ending", "gameplay.mistakes": "mistakes", "gameplay.hesitations": "hesitations",
               "gameplay.retake": "a new take", "gameplay.events": "order of moves", "gameplay.finish": "finish",
               "gameplay.clock_left": "seconds left", "gameplay.clock": "clock", "pacing.length": "length",
               "pacing.tempo": "tempo", "pacing.curve": "pace curve", "channel": "channel", "format": "format"}


def group_names(groups) -> list[str]:
    return [GROUP_NAMES.get(g, g.split(".")[-1].replace("_", " ")) for g in groups]


def _sha_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def asset_ref(name) -> str | None:
    """A file reference as it is compared: its content hash (so a re-upload under the same name
    with other pixels counts as a change), or the name of a built-in."""
    if not name:
        return None
    if isinstance(name, (list, tuple)):
        return "gradient " + " ".join(name)
    if str(name).startswith("builtin:"):
        return str(name)
    from .draw import PROJECT, SPRITES
    for p in (Path(name), PROJECT / SPRITES / str(name)):
        if p.is_file():
            return f"{p.name} ({_sha_file(p)})"
    return f"{name} (missing)"


def asset_slots(ad: dict, compose: dict | None = None) -> dict[str, str | None]:
    """The file behind each asset slot of an ad."""
    L = ad.get("layers", {})
    end = ad.get("segments", {}).get("end", {})
    cursor = L.get("cursor")
    out = {
        "logo": asset_ref((L.get("logo") or {}).get("image")),
        "hook_icon": asset_ref((L.get("hook") or {}).get("icon")),
        "end_art": asset_ref((L.get("end_art") or {}).get("image")),
        "button": asset_ref((L.get("end_cta") or {}).get("image")),
        "end_background": asset_ref(end.get("background") or end.get("gradient")),
        "cursor": None if cursor is None else (asset_ref(cursor.get("image")) or "the tap ring"),
    }
    return out


def beat_key(b: dict) -> tuple:
    """A move as compared between versions: which block, where it ends, whether it leaves (the
    path on the way may differ when other blocks moved). The recording's own check ("Planned
    moves") proves each recorded drag is the planned one."""
    return b["block"], tuple(b["path"][-1]) if b.get("path") else None, bool(b.get("exits"))


def _moves(play: dict) -> list[tuple]:
    return [beat_key(b) for b in play.get("beats", [])]


def common_moves(a: list, b: list) -> tuple[int, int]:
    """(common prefix, longest common subsequence) of two move lists."""
    k = 0
    while k < min(len(a), len(b)) and a[k] == b[k]:
        k += 1
    m = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) - 1, -1, -1):
        for j in range(len(b) - 1, -1, -1):
            m[i][j] = m[i + 1][j + 1] + 1 if a[i] == b[j] else max(m[i + 1][j], m[i][j + 1])
    return k, m[0][0]


def _load(v: dict, studio: Path) -> dict:
    rec = studio / v["recording"]["dir"]
    ad_dir = studio / v["ad_dir"]
    j = lambda p: json.loads(p.read_text()) if p.is_file() else {}
    return {"v": v, "rec": rec, "ad": j(ad_dir / "ad.json"), "compose": j(ad_dir / "compose.json"),
            "result": j(rec / "result.json"), "play": j(rec / "play.json"), "job": j(rec / "job.json"),
            "frames": (j(rec / "frames.json") or {}).get("frames", [])}


def _fmt_s(f: int) -> str:
    return f"{f / 30:.2f} s"


# ---------- the comparison ----------

class _Ctx:
    """What the edit asked for, as facts the checks below use."""

    def __init__(self, a: dict, b: dict, groups: list[str]):
        from .brief import asset_slot
        self.a, self.b, self.groups = a, b, set(groups)
        ba, bb = a["v"]["brief"], b["v"]["brief"]
        self.ba, self.bb = ba, bb
        g = self.groups
        self.level = bool(g & set(LEVEL_GROUPS))
        self.play = bool(g & set(LEVEL_GROUPS + PLAY_GROUPS))  # a new level is new play too
        self.finish = "gameplay.finish" in g
        self.pace = bool(g & set(PACE_GROUPS))
        self.length = "pacing.length" in g
        self.ending = ba["gameplay"]["ending"] != bb["gameplay"]["ending"]
        self.parts = {PART_OF[k] for k in PART_OF if "sequence" in g and ba["sequence"].get(k) != bb["sequence"].get(k)}
        self.looks = g & set(RECORDING_LOOKS)
        self.copy_layers = {LAYER_OF[x] for x in g if x in LAYER_OF}
        if "language" in g or "visuals.captions" in g:
            self.copy_layers |= set(TEXT_LAYERS)
        sa = {asset_slot(x): x for x in ba.get("assets", [])}
        sb = {asset_slot(x): x for x in bb.get("assets", [])}
        self.slots = {s for s in set(sa) | set(sb) if sa.get(s) != sb.get(s)} if "assets" in g else set()
        if "visuals.cursor" in g:
            self.slots.add("cursor")
        self.asset_layers = {lid for s in self.slots for lid in SLOT_LAYERS.get(s, ())}
        self.hud = "visuals.hud" in g
        self.new_play = a["v"]["recording"]["dir"] != b["v"]["recording"]["dir"] and _moves(a["play"]) != _moves(b["play"])
        self.timeline_from = self.play or self.pace or self.length  # a new recording: its own structure


def _check(diffs: list, text: str, how) -> None:
    """Record one difference: how = "asked", a reason (explained), or None (unexplained)."""
    diffs.append((text, how))


def _gameplay(c: _Ctx) -> tuple[str, list]:
    a, b, d = c.a, c.b, []
    va, vb = a["v"], b["v"]
    ma, mb = _moves(a["play"]), _moves(b["play"])
    if va["recording"]["dir"] == vb["recording"]["dir"]:
        return f"the same recording, reused: the same level and the same {len(ma)} moves", d
    if va["level"]["sha"] != vb["level"]["sha"]:
        ed = vb["level"].get("edit")
        txt = (f"the level: {ed['what']} ({ed['direction']}: {ed['before']['min_drags']} -> {ed['after']['min_drags']} "
               f"drags, {ed['before']['extra_drags']} -> {ed['after']['extra_drags']} repositioning)"
               if ed and ed.get("from_version") == va["n"] else "a different level")
        _check(d, txt, "asked" if c.level else None)
    if ma != mb:
        k, lcs = common_moves(ma, mb)
        _check(d, f"moves: the first {k} of {len(mb)} are the same as before ({lcs} of {len(mb)} in common)",
               "asked" if c.play else None)
    if a["result"].get("status") != b["result"].get("status"):
        _check(d, f"ending: {a['result'].get('status')} -> {b['result'].get('status')}", "asked" if c.play else None)
    return f"the same {len(mb)} moves, block by block", d


def _seg_shift(a: dict, b: dict, sid: str) -> int | None:
    ta, tb = a["compose"].get("timeline", {}).get(sid), b["compose"].get("timeline", {}).get(sid)
    if not ta or not tb:
        return None
    return tb["frames"][0] - ta["frames"][0]


def _layer_seg(ad: dict, lid: str) -> str | None:
    lay = ad.get("layers", {}).get(lid) or {}
    return lay.get("seg") or (lay.get("start") or {}).get("seg")


def _timing(c: _Ctx) -> tuple[str, list]:
    a, b, d = c.a, c.b, []
    same_moves = _moves(a["play"]) == _moves(b["play"])
    if a["v"]["recording"]["dir"] != b["v"]["recording"]["dir"] and (
            [x["start_frame"] for x in a["result"]["drags"]] != [x["start_frame"] for x in b["result"]["drags"]]
            or len(a["frames"]) != len(b["frames"])):
        why = "asked" if c.pace else ("the new moves take their own time" if c.play else None)
        _check(d, f"the recording: {len(a['frames'])} -> {len(b['frames'])} frames"
                  + ("; the same moves with other pauses" if same_moves else ""), why)
    ta, tb = a["compose"].get("timeline", {}), b["compose"].get("timeline", {})
    for sid in dict.fromkeys([*ta, *tb]):
        fa, fb = (ta.get(sid) or {}).get("frames"), (tb.get(sid) or {}).get("frames")
        if fa == fb:
            continue
        txt = f"part '{sid}': " + (f"{_fmt_s(fa[0])}-{_fmt_s(fa[1])}" if fa else "none") + " -> " + \
              (f"{_fmt_s(fb[0])}-{_fmt_s(fb[1])}" if fb else "none")
        if sid in c.parts:
            why = "asked"
        elif c.timeline_from:
            why = "asked" if c.length or c.pace else "the new play has its own length"
        elif c.parts and (fa is None or fb is None or sid in ("end", "intro")):
            why = "the end card (or the frozen intro) takes the time of the part that was added or removed"
        elif c.parts and fa and fb and fb[1] - fb[0] == fa[1] - fa[0]:
            why = "moved by the part that was added or removed before it"
        else:
            why = None
        _check(d, txt, why)
    la, lb = a["compose"].get("layers", {}), b["compose"].get("layers", {})
    resized = [x for x in c.copy_layers if x in la and x in lb and x in BAND_CAPTIONS and la[x]["frames"] != lb[x]["frames"]]
    for lid in la:
        if lid not in lb or la[lid]["frames"] == lb[lid]["frames"]:
            continue
        sh = _seg_shift(a, b, _layer_seg(b["ad"], lid) or "")
        fa, fb = la[lid]["frames"], lb[lid]["frames"]
        if sh is not None and sh != 0 and fb[0] - fa[0] == sh and fb[1] - fa[1] == sh:
            continue  # it moved with its part (reported above)
        txt = f"{lid} on screen {_fmt_s(fa[0])}-{_fmt_s(fa[1])} -> {_fmt_s(fb[0])}-{_fmt_s(fb[1])}"
        if lid in c.copy_layers or lid in c.asset_layers:
            why = "asked"
        elif lid in BAND_CAPTIONS and resized and fb[1] - fb[0] == fa[1] - fa[0]:
            # one caption at a time in the band: a longer asked caption makes the next one wait, a
            # shorter one lets it go back to its moment
            why = f"one caption at a time in the band, and {', '.join(resized)} now runs {'longer' if fb[0] > fa[0] else 'shorter'}"
        elif c.new_play or c.timeline_from:
            why = "it follows its moment in the new play"
        elif c.parts:
            why = "its part moved"
        else:
            why = None
        _check(d, txt, why)
    return f"{b['compose'].get('duration_s')} s; every part and every caption on the same frames", d


def _camera(c: _Ctx) -> tuple[str, list]:
    a, b, d = c.a, c.b, []
    if a["job"].get("camera") != b["job"].get("camera"):
        _check(d, f"in-game camera: {a['job'].get('camera')} -> {b['job'].get('camera')}",
               "asked" if "visuals.zoom" in c.groups else None)
    ta, tb = a["compose"].get("timeline", {}), b["compose"].get("timeline", {})
    for s in ta:
        if s in tb and ta[s].get("fit") != tb[s].get("fit"):
            _check(d, f"framing of '{s}'", None)
    same_moves = _moves(a["play"]) == _moves(b["play"])
    fin = lambda fr: [(round(f.get("finger_x", 0)), round(f.get("finger_y", 0)), f.get("finger")) for f in fr]
    if (a["v"]["recording"]["dir"] != b["v"]["recording"]["dir"] and same_moves
            and len(a["frames"]) == len(b["frames"]) and fin(a["frames"]) != fin(b["frames"])):
        _check(d, "the finger's path on screen", "the board is framed closer" if "visuals.zoom" in c.groups else None)
    return "the game's camera, the framing of every part" + (" and the finger's path" if same_moves else ""), d


def _texts(x: dict) -> dict:
    return {k: v.get("text") for k, v in x["compose"].get("layers", {}).items() if v.get("text") is not None}


def _copy_reason(c: _Ctx, lid: str) -> str | None:
    """Why a caption the edit did not name shows other words, if a check proves it."""
    ta = (c.a["ad"].get("layers", {}).get(lid) or {}).get("text")
    tb = (c.b["ad"].get("layers", {}).get(lid) or {}).get("text")
    if ta is not None and ta == tb:  # the same template: only the facts filled into it changed
        if c.looks & {"visuals.colours"}:
            return "it names the colours as shown"
        if c.new_play or c.pace or c.play:
            return "it quotes the new play (its colours, its clock)"
        return None
    key = next((k for k, v in LAYER_OF.items() if v == lid), None)
    default = key is not None and c.ba["concept"].get(key.split(".")[1]) is None and \
        c.bb["concept"].get(key.split(".")[1]) is None
    # What each default caption is written from: the ending (hook, result, end line), the mistake
    # (its caption and the fix's), the finish (the cascade); never the title or the button.
    if default and lid in ("hook", "cap_result", "end_fact", "cap_hurry") and c.ending:
        return "the default caption for the new ending"
    if default and lid in ("cap_mistake", "cap_fix") and c.play:
        return "the default caption for the new mistake"
    if default and lid == "cap_cascade" and (c.finish or c.ending or c.play):
        return "the default caption for the new finish"
    if default and c.hud:
        return "with the clock hidden, captions do not quote it"
    if default and lid == "hook" and "teaser" in c.parts:
        return "the hook is written for the result shown first"
    return None


def _copy(c: _Ctx) -> tuple[str, list]:
    xa, xb, d = _texts(c.a), _texts(c.b), []
    for lid in dict.fromkeys([*xa, *xb]):
        if xa.get(lid) == xb.get(lid):
            continue
        txt = f"{lid}: {xa.get(lid)!r} -> {xb.get(lid)!r}"
        if lid in c.copy_layers:
            why = "asked"
        elif lid not in xa or lid not in xb:
            why = _presence_reason(c, lid)
        else:
            why = _copy_reason(c, lid)
        _check(d, txt, why)
    return f"all {len(xb)} texts word for word", d


def _presence_reason(c: _Ctx, lid: str) -> str | None:
    """Why a layer appeared or went, if a check proves it."""
    part = LAYER_PART.get(lid)
    if part and part in c.parts:
        return f"it belongs to the {part}, which was asked to change"
    if lid in PLAY_LAYERS and (c.new_play or c.timeline_from):
        return "it belongs to a moment of the play, which changed"
    if lid in c.copy_layers or lid in c.asset_layers:
        return "asked"
    if lid in ("end_art",) and c.ending:
        return "the end card's picture follows the ending"
    return None


def _composition(c: _Ctx, copy_diffs: list) -> tuple[str, list]:
    a, b, d = c.a, c.b, []
    la, lb = a["compose"].get("layers", {}), b["compose"].get("layers", {})
    explained_text = {t.split(":")[0] for t, how in copy_diffs if how}
    band_asked = "logo" in c.slots
    band_changed = a["ad"].get("band") != b["ad"].get("band")
    if band_changed:
        _check(d, "the caption band", "asked" if band_asked else None)
    for lid in dict.fromkeys([*la, *lb]):
        if lid in la and lid in lb and la[lid].get("box") == lb[lid].get("box"):
            continue
        if lid not in la or lid not in lb:
            why = _presence_reason(c, lid)
            _check(d, f"{'added' if lid not in la else 'removed'}: {lid}", why)
            continue
        txt = f"{lid} placed or sized differently"
        if lid in c.copy_layers or lid in c.asset_layers:
            why = "asked"
        elif lid in explained_text:
            why = "its size follows its new wording"
        elif band_changed and band_asked and lid in BAND_CAPTIONS:
            why = "the logo in a top corner narrows the caption band"
        elif lid == "cursor" and (c.new_play or c.timeline_from or "replay" in c.parts):
            why = "the cursor follows the moves on screen"
        elif lid == "hook" and c.hud:
            why = "a hidden clock also hides the stopwatch beside the hook"
        elif lid == "end_art" and c.ending:
            why = "the end card's picture follows the ending"
        else:
            why = None
        _check(d, txt, why)
    return f"all {len(lb)} layers in the same place and size", d


def _sequence(c: _Ctx) -> tuple[str, list]:
    a, b, d = c.a, c.b, []
    oa, ob = a["ad"].get("order", []), b["ad"].get("order", [])
    for sid in dict.fromkeys([*oa, *ob]):
        if (sid in oa) == (sid in ob):
            continue
        txt = f"{'added' if sid not in oa else 'removed'}: the {sid}"
        if sid in c.parts:
            why = "asked"
        elif sid == "intro" and c.parts:
            why = "the frozen intro gives way to the part that was added"
        elif c.timeline_from:
            why = "the new play has its own length, so the parts are fitted again"
        else:
            why = None
        _check(d, txt, why)
    ka, kb = [x["kind"] for x in a["play"].get("beats", [])], [x["kind"] for x in b["play"].get("beats", [])]
    if ka != kb:
        _check(d, f"the play's moments: {', '.join(ka)} -> {', '.join(kb)}", "asked" if c.play else None)
    return f"{' > '.join(ob)}; the play's moments in the same order", d


VISUAL_GROUP = {"theme": "visuals.colours", "blocks": "visuals.colours", "background": "visuals.background",
                "board": "visuals.board", "hud_timer": "visuals.hud", "hud_level": "visuals.hud",
                "caption_fill": "visuals.captions", "caption_outline": "visuals.captions"}


def _visual(c: _Ctx) -> tuple[str, list]:
    a, b, d = c.a, c.b, []
    for k, g in VISUAL_GROUP.items():
        x, y = c.ba["visuals"].get(k), c.bb["visuals"].get(k)
        if x != y:
            _check(d, f"{k.replace('_', ' ')}: {x} -> {y}", "asked" if g in c.groups else None)
    if a["job"].get("level_label") != b["job"].get("level_label"):
        _check(d, f"the HUD level number: {a['job'].get('level_label')} -> {b['job'].get('level_label')}",
               "asked" if "level.label" in c.groups else None)
    same_rec = a["v"]["recording"]["dir"] == b["v"]["recording"]["dir"]
    if not same_rec and not c.new_play and len(a["frames"]) == len(b["frames"]):
        ident = sum(x.get("hash") == y.get("hash") for x, y in zip(a["frames"], b["frames"]))
        if ident < len(a["frames"]):
            _check(d, f"recorded frames: {ident} of {len(a['frames'])} identical",
                   "asked" if c.looks else ("the same moves with other pauses" if c.pace else None))
        return "filmed again: every recorded frame identical", d
    return ("the same recording, the same look" if same_rec else "the same look"), d


def _assets(c: _Ctx) -> tuple[str, list]:
    sa, sb, d = asset_slots(c.a["ad"]), asset_slots(c.b["ad"]), []
    names = dict(ASSET_SLOTS)
    for k in sa:
        if sa[k] == sb[k]:
            continue
        txt = f"{names[k]}: {sa[k] or 'none'} -> {sb[k] or 'none'}"
        stopwatch = (sa[k] or "").startswith("stopwatch.png")
        defaults = all(x is None or x.startswith(("stopwatch.png", "CoinPile.png")) for x in (sa[k], sb[k]))
        if k in c.slots:
            why = "asked"
        elif k == "hook_icon" and stopwatch and sb[k] is None and c.hud:
            why = "a hidden clock also hides the stopwatch beside the hook"
        elif k == "hook_icon" and defaults and (c.ending or "teaser" in c.parts):
            why = "the stopwatch goes with a clock ending, not with the result shown first"
        elif k == "end_art" and defaults and c.ending:
            why = "the end card's picture follows the ending"
        else:
            why = None
        _check(d, txt, why)
    return "every picture (same file contents)", d


def _sound(c: _Ctx) -> tuple[str, list]:
    a, b, d = c.a, c.b, []
    on = lambda x: bool(x["ad"].get("audio", {}).get("events"))
    if on(a) != on(b):
        _check(d, f"sound effects {'on' if on(a) else 'off'} -> {'on' if on(b) else 'off'}",
               "asked" if "audio" in c.groups else None)
    elif a["compose"].get("wav_sha256") != b["compose"].get("wav_sha256"):
        _check(d, "the effects play at other moments",
               "the effects follow the new moves and parts" if c.new_play or c.timeline_from or c.parts else None)
    return "the same sound track, sample for sample", d


def _grouped(diffs: list) -> list:
    """Differences with the same reason, said once: "part 'end', part 'replay' (the new play has
    its own length)" rather than a line each. Layers that moved for the same reason are counted."""
    out, seen = [], {}
    for text, how in diffs:
        if how in (None, "asked") or how not in seen:
            seen.setdefault(how, len(out))
            out.append([[text], how])
        else:
            out[seen[how]][0].append(text)
    res = []
    for texts, how in out:
        layers = [t for t in texts if " on screen " in t]
        rest = [t for t in texts if " on screen " not in t]
        if len(layers) > 2:
            rest.append(f"{len(layers)} captions and pictures on screen at other times "
                        f"({', '.join(t.split(' on screen ')[0] for t in layers)})")
        else:
            rest += layers
        res.append(("; ".join(rest), how))
    return res


def report(prev: dict, cur: dict, studio: Path, groups=None, pixels: dict | None = None,
           notes: list[str] | None = None, compare: bool = False, asked_notes: list[str] | None = None) -> dict:
    """The edit report between two versions (version.json records). groups: the brief field
    groups the edit asked to change (default: the new version's brief["changed"]). pixels: the
    frame diff of the two renders. notes: the engine's notes for the new version. compare: two
    versions that are not an edit and its parent (any two): rows only say kept or differs."""
    groups = list(groups if groups is not None else cur["brief"].get("changed", []))
    a, b = _load(prev, studio), _load(cur, studio)
    c = _Ctx(a, b, groups)
    copy_same, copy_d = _copy(c)
    parts = {"gameplay": _gameplay(c), "timing": _timing(c), "camera": _camera(c),
             "composition": _composition(c, copy_d), "sequence": _sequence(c), "visual": _visual(c),
             "assets": _assets(c), "copy": (copy_same, copy_d), "sound": _sound(c)}
    rows = []
    for item, title in ITEMS:
        same, diffs = parts[item]
        shown = _grouped(diffs) if not compare else diffs
        if not diffs:
            status, detail = "kept", same
        elif compare:
            status, detail = "changed", "; ".join(t for t, _ in diffs)
        elif any(how is None for _, how in diffs):
            status = "not_asked"
            detail = "; ".join(f"{t}" + (" (NOT ASKED)" if how is None else "") for t, how in shown)
        elif all(how == "asked" for _, how in diffs):
            status, detail = "asked", "; ".join(t for t, _ in shown)
        else:
            status = "side_effect"
            detail = "; ".join(t + ("" if how == "asked" else f" ({how})") for t, how in shown)
        row = {"item": item, "title": title, "status": status, "detail": detail}
        reasons = _reasons(diffs, notes or []) if status not in ("kept", "changed") else []
        if reasons:
            row["reasons"] = reasons
        rows.append(row)
    bad = [r["title"] for r in rows if r["status"] == "not_asked"]
    changed = [r["title"] for r in rows if r["status"] != "kept"]
    out = {"asked": groups, "asked_names": group_names(groups), "rows": rows, "ok": not bad}
    leak = pixels is not None and pixels.get("contained") is False
    if pixels is not None:
        out["pixels"] = pixels
    if leak:
        out["ok"] = False
    if compare:
        out["verdict"] = (f"These differ: {', '.join(changed)}." if changed else "The two versions are the same.")
    elif bad:
        out["verdict"] = f"Changed without being asked: {', '.join(bad)}."
    elif not changed and groups:
        why = "; ".join(n.rstrip(".") for n in (asked_notes or [])[:2])
        out["verdict"] = ("Nothing changed: " + (why + "." if why else "what was asked was already so in this version, "
                                                 "or could not be made."))
    elif not changed:
        out["verdict"] = "Nothing changed."
    elif all(r["status"] in ("kept", "asked") for r in rows):
        out["verdict"] = f"Only what was asked changed ({', '.join(changed)}); everything else is identical."
    else:
        side = [r["title"] for r in rows if r["status"] == "side_effect"]
        out["verdict"] = (f"Changed as asked: {', '.join(r['title'] for r in rows if r['status'] == 'asked') or 'none'}; "
                          f"also changed because of it: {', '.join(side)}. Everything else is identical.")
    if leak:
        out["verdict"] = "Some changed pixels are outside the edited layers. " + out["verdict"]
    return out


def _reasons(diffs: list, notes: list[str]) -> list[str]:
    """The engine's own notes that mention a layer or part named in the row's differences."""
    words = {t.split(":")[0].split(" ")[0] for t, _ in diffs} | {w for t, _ in diffs for w in t.split() if "_" in w}
    words = {w.strip("'") for w in words if len(w) > 3}
    return [n for n in notes if any(w in n for w in words)][:3]
