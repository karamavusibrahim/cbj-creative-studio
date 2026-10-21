"""Edit routing: the edit's type and its analysis level are decided before anything is planned.

The research note's principle, applied to this tool: analyse only what is necessary, modify only
what is requested, preserve everything else. An edit request and the creative's own metadata
(parts.py: every part, caption, picture, moment and clock reading with its seconds) are enough to
say, in code and before any model runs:
- Level 0, direct: the target is a known layer of the creative (the hook, the logo, the music,
  the texture on a block). No video analysis. When the request gives the new value itself (a
  quoted text, an attached file, "turn the sound off"), the edit is made in code with no planner
  at all (edits.direct_edit); otherwise the planner gets the route and may change only the fields
  the target holds.
- Level 1, targeted: the target is a moment ("the caption that appears when the timer reaches
  five seconds", "the caption before the win", "at 0:12"). It is placed on the timeline from the
  metadata: the clock readings, the moments, the parts. Only when the metadata cannot place it,
  and only if a multimodal model is available, a contact sheet of the ad is read to find the
  second (optional: CBJ_LOCATE_BY_VISION=0 turns it off).
- Level 2, full: a video the tool did not make (a reference, brief p.6; or an uploaded MP4 that
  matches none of the tool's versions) is read as a whole with the multimodal model. An uploaded
  MP4 that IS one of the tool's versions (matched by its bytes) needs no analysis: the edit is
  routed to that version's metadata.
A request that changes the puzzle or the play (a second mistake, a harder level, another ending)
is a retake: the game films it again, keeping what still fits. A request that changes the play
and asks to keep every frame contradicts itself and is refused as such.

After the planner answers, `verify` checks the route deterministically: a Level 0/1 route never
lets the planner change the level, the moves or the length (restored, and said so).
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import brief as B
from . import parts as P

LEVEL_NAMES = {0: "Level 0, direct (from the creative's metadata; no video analysis)",
               1: "Level 1, targeted (a moment placed on the creative's timeline; no video model needed)",
               2: "Level 2, full (a video the tool did not make is read with a multimodal model)"}
PRESERVE_ALL = ("gameplay", "level", "timing", "camera", "captions", "pictures", "audio", "sequence")
GAME_GROUPS = ("level.", "gameplay.", "pacing.length", "pacing.tempo", "pacing.curve", "channel")

_NUM = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
        "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "twenty": 20, "thirty": 30}
_NUM_RE = r"(\d+(?:\.\d+)?|" + "|".join(_NUM) + ")"
_KEEP = re.compile(r"\b(keep|keeps|keeping|same|unchanged|preserve|preserving|leave|leaving|don'?t change|do not change|"
                   r"identical|as (it|they) (is|are|was|were)|exactly as|like before|i like|nothing else|everything else|"
                   r"only (change|that|this)|rest (stays|unchanged)|otherwise)\b", re.I)
_SPLIT = re.compile(r"[.;!?\n]|,\s*(?:but|and|then)\b|\b(?:but|however|except)\b", re.I)
_QUOTED = re.compile(r"\"([^\"]{1,120})\"|“([^”]{1,120})”|(?<!\w)'([^']{1,120})'(?!\w)|‘([^’]{1,120})’|«([^»]{1,120})»")
_CAPTION_NAMES = [
    ("hook", r"\b(opening|first|intro(?:ductory)?|starting|top|headline|title|main)\s+(caption|text|line|words|title)\b|\bhook\b|\bheadline\b|\bfirst words\b"),
    ("end_title", r"\bend[- ]?card'?s?\s+(title|headline|big text)\b|\btitle (on|of) the end[- ]?card\b"),
    ("end_fact", r"\bend[- ]?card'?s?\s+(line|subtitle|second line|small text|text under)\b|\b(line|text) under the title\b"),
    ("end_cta", r"\b(button'?s?\s+(text|label|words)|cta text|call[- ]to[- ]action text|play now text)\b"),
    ("cap_mistake", r"\b(mistake|wrong[- ]move|error)\s+(caption|text|line)\b|\bcaption (on|over|at) the (mistake|wrong move)\b"),
    ("cap_fix", r"\b(fix|recovery|correct[- ]move)\s+(caption|text|line)\b|\bcaption (on|over|at) the (fix|recovery)\b"),
    ("cap_hurry", r"\b(hurry|urgency|last[- ]seconds?|countdown)[!'’\"”]*\s+(caption|text|line)\b|\bcaption (in|at|over) the last seconds\b"),
    ("cap_cascade", r"\b(finish|cascade|fast[- ]finish|streak|final)\s+(caption|text|line)\b|\bcaption (on|over|at) the (finish|cascade)\b"),
    ("cap_result", r"\b(result|win|victory|win[- ]screen|level[- ]completed)\s+(caption|text|line)\b|\bcaption (on|over|at) the (result|win) screen\b"),
]
_PICTURE_NAMES = [
    ("skin", r"\b(texture|skin|pattern|picture|image|art)\b[^.;,]{0,30}\b(on|to|onto|over)\s+(the|a|one)?\s*(\w+)\s+block\b|\b(block'?s?\s+(texture|skin))\b"),
    ("obstacle", r"\b(obstacle|wall picture|the walls?|barrier|blocker)\b"),
    ("logo2", r"\b(sticker|picture|image|icon|badge)\b[^.;,]{0,25}\btop[- ]right\b|\btop[- ]right\s+(sticker|picture|corner picture|icon)\b"),
    ("logo", r"\b(logo|brand mark|brand|badge|watermark)\b|\b(sticker|picture|image|icon)\b[^.;,]{0,25}\btop[- ]left\b"),
    ("hook_icon", r"\b(icon|mascot|sticker|picture)\b[^.;,]{0,20}\b(beside|next to|by)\s+the\s+(hook|opening caption|headline)\b"),
    ("end_art", r"\b(coin pile|coins|trophy|picture|image|art(?:work)?|illustration|mascot)\b[^.;,]{0,20}\bend[- ]?card\b|\bend[- ]?card'?s?\s+(picture|image|art(?:work)?|illustration|mascot)\b"),
    ("button", r"\b(play now|cta|download|install)?\s*button\b(?![^.;,]{0,12}\b(text|label|words)\b)"),
    ("end_background", r"\bend[- ]?card'?s?\s+background\b|\bbackground\b[^.;,]{0,20}\bend[- ]?card\b"),
    ("cursor", r"\b(cursor|pointer|tap ring|tap hand|pointing hand)\b"),
]
_MUSIC = re.compile(r"\b(music|soundtrack|track|song|tune|background audio)\b", re.I)
_SOUND = re.compile(r"\b(sound effects?|sfx|sounds|the sound|audio|mute|silent|silence)\b", re.I)
_SOUND_OFF = re.compile(r"\b(mute|silent|silence|turn (the )?(sound|sfx|sound effects|audio) off|no sound|without sound|remove the sound)\b", re.I)
_SOUND_ON = re.compile(r"\b(unmute|turn (the )?(sound|sfx|sound effects|audio) (back )?on|with sound)\b", re.I)
_BACKGROUND = re.compile(r"\bbackground\b(?![^.;,]{0,20}\b(music|track|audio|end[- ]?card)\b)", re.I)
_CAPTION_LOOK = re.compile(r"\b(caption|text|font)s?\b[^.;,]{0,30}\b(colou?r|outline|yellow|white|red|blue|green|black|dark|light|bold|style)\b|"
                           r"\b(yellow|white|red|blue|green|black|orange|pink|purple)\s+(captions?|texts?)\b", re.I)
_THEME = re.compile(r"\b(theme|look|palette|colou?rs? of the blocks|block colou?rs?|neon|pastel|candy|autumn|winter|toy)\b", re.I)
_REMOVE = re.compile(r"\b(remove|delete|drop|take (out|away|off)|without|get rid of|no longer show|hide)\b", re.I)
_CHANGE_TEXT = re.compile(r"\b(change|replace|rewrite|reword|rename|make .{1,40} say|say|read|set|swap|switch|update|edit|should say|to say|becomes?)\b", re.I)
_GAME = re.compile(r"\b(level|board|puzzle|blocks?(?! (texture|skin))|pieces?|moves?|drags?|mistakes?|wrong move|stuck|harder|easier|"
                   r"difficult(y)?|ending|near[- ]fail|time[- ]?out|cliffhanger|clock|timer|seconds? left|"
                   r"pac(e|ing)|tempo|faster|slower|take|exciting|solve|win|fail|door|gate|wall|"
                   r"more blocks|fewer blocks|retake|film|record)\b", re.I)
_SEQUENCE = re.compile(r"\b(replay|slow[- ]?motion|result screen|win screen|end[- ]?card|intro|opening|still opening|held? (board|result)|"
                       r"victory hold|hold|length|longer|shorter|\d+[- ]second|\d+ s\b|order of the parts|parts|result[- ]first|teaser|"
                       r"show the (win|result) first)\b", re.I)
_KEPT_LEVEL = re.compile(r"\b(keep|keeps|keeping|same|unchanged|preserve|preserving|don'?t change|do not change)\b[^.;]{0,25}\b(level|board|puzzle|layout)\b", re.I)
_GAME_CHANGE = re.compile(r"\b(add|another|second|more|fewer|less|new|harder|easier|different|change|make|instead|without|remove|"
                          r"longer|shorter|faster|slower|exciting|start|end|finish|solve|lose|win|fail|runs? out|stuck)\b", re.I)
_LOCK = re.compile(r"\b(every|each|all)\s+(single\s+)?(frame|pixel)s?\b|\bframe[- ]by[- ]frame\b|\bevery frame\b|"
                   r"\b(whole|entire|complete) video (exactly|unchanged|the same)\b|\b(do not|don'?t|never) (change|touch) the (board|level|moves|gameplay)\b", re.I)
_MOMENT = re.compile(r"\b(caption|text|line|words|picture|sticker|thing|element|object|moment|part)\b[^.;,]{0,25}\b(that|which|shown|appears?|appearing|"
                     r"displayed|visible|on screen|seen)\b[^.;,]{0,25}\b(when|at|before|after|during|while|as|once)\b|"
                     r"\b(at|around|near)\s+(\d+:\d\d|" + _NUM_RE + r"\s*s(?:ec(?:ond)?s?)?)\b|\bwhen the (timer|clock)\b", re.I)
_CLOCK = re.compile(r"\b(timer|clock|countdown|time)\b[^.;,]{0,30}\b(reaches|hits|shows|reads|is at|drops to|gets to|says|at)\s+"
                    r"(?:0:)?" + _NUM_RE + r"(?:\s*s(?:ec(?:ond)?s?)?)?\b", re.I)
_CLOCK2 = re.compile(r"\b(?:0:)?" + _NUM_RE + r"\s*s(?:ec(?:ond)?s?)?\s+(left|remaining|on the (timer|clock))\b", re.I)
_AT = re.compile(r"\b(?:at|around|near)\s+(?:second\s+)?(\d+):(\d\d)\b|\b(?:at|around|near)\s+(?:second\s+)?" + _NUM_RE + r"\s*s(?:ec(?:ond)?s?)?\b|\b" + _NUM_RE + r"\s*s(?:ec(?:ond)?s?)?\s+in(?:to the (?:ad|video))?\b", re.I)
_EVENT_WORDS = [
    ("win", r"\b(win|victory|level completed|solve[ds]?|clears? the board|the end of the (play|gameplay)|cleared)\b"),
    ("time_out", r"\b(time[- ]?out|out of time|fail(ure|s)?|loses?|runs? out of time)\b"),
    ("last_exit", r"\b(last (exit|block|move|drag)|final (exit|block|move|drag))\b"),
    ("wrong_move", r"\b(mistake|wrong move|blocked move|error|gets? stuck|stuck)\b"),
    ("first_move", r"\b(first (move|drag|touch)|start of the (play|gameplay)|the play starts)\b"),
    ("replay", r"\b(replay|slow[- ]?motion)\b"),
    ("result", r"\b(result screen|win screen|level completed screen)\b"),
    ("end", r"\b(end[- ]?card|the end of the (ad|video|creative))\b"),
    ("intro", r"\b(opening|intro|the start of the (ad|video|creative)|the beginning)\b"),
]
_CHANGE_VERBS = re.compile(r"\b(without|add|put|use|replace|change|make|remove|swap|apply|turn|set|rewrite|insert|show|hide|"
                           r"drop|delete|say|rename|switch|update|mute|silence|more|less|fewer|another|new|instead)\b", re.I)
_BEFORE = re.compile(r"\b(before|just before|right before|leading (up )?to|ahead of)\b", re.I)
_AFTER = re.compile(r"\b(after|just after|right after|following|once)\b", re.I)
_REFERENCE_EDIT = re.compile(r"\b(pacing|structure|concept|storytelling|rhythm|like (this|the) (video|reference|clip|ad))\b", re.I)


def quoted(text: str) -> list[str]:
    """The quoted strings of a request, in order (double, curly or single quotes; an apostrophe
    inside a word is not a quote)."""
    return [next(g for g in m.groups() if g is not None).strip() for m in _QUOTED.finditer(text)]


def _num(s: str) -> float | None:
    if s is None:
        return None
    s = s.strip().lower()
    if s in _NUM:
        return float(_NUM[s])
    try:
        return float(s)
    except ValueError:
        return None


def clauses(prompt: str) -> list[str]:
    """The request's clauses: split on punctuation and 'but'/'except', never inside a quote."""
    spans = list(_QUOTED.finditer(prompt))
    masked, keep = prompt, {}
    for i, m in reversed(list(enumerate(spans))):
        keep[i] = m.group(0)
        masked = masked[:m.start()] + f"\x00{i}\x00" + masked[m.end():]
    out = []
    for c in _SPLIT.split(masked):
        c = re.sub(r"\x00(\d+)\x00", lambda g: keep[int(g.group(1))], c or "").strip(" ,")
        if c:
            out.append(c)
    return out


def _mmss(n) -> str:
    try:
        n = int(n)
    except (TypeError, ValueError):
        return str(n)
    return f"{n // 60}:{n % 60:02d}"


# ---------- locating a moment on the timeline ----------

def moment(clause: str, m: dict) -> dict | None:
    """Where a clause points on the ad's timeline, from the manifest: {at_s, how, note} or None
    when the clause names no moment. at_s is None when it names one the ad does not have."""
    c = clause.lower()
    g = _CLOCK.search(c) or _CLOCK2.search(c)
    if g:
        n = _num(g.group(3) if g.re is _CLOCK else g.group(1))
        if n is not None:
            at = P.clock_at(m, int(n))
            tl = m.get("gameplay", {})
            note = (f"the clock shows {_mmss(n)} at {at:g} s" if at is not None else
                    f"the clock never shows {_mmss(n)} in this ad (it runs {_mmss(tl.get('timer_start_s'))} -> "
                    f"{_mmss(tl.get('timer_end_s'))})")
            return {"at_s": at, "how": "clock", "note": note}
    g = _AT.search(c)
    if g:
        if g.group(1) is not None:
            at = int(g.group(1)) * 60 + int(g.group(2))
        else:
            at = _num(g.group(3) or g.group(4))
        if at is not None:
            if m.get("duration_s") is not None and at > m["duration_s"] + 1e-6:
                return {"at_s": None, "how": "time", "note": f"{at:g} s is past the end of the ad ({m['duration_s']:g} s)"}
            return {"at_s": float(at), "how": "time", "note": f"at {at:g} s"}
    for key, rx in _EVENT_WORDS:
        if not re.search(rx, c):
            continue
        at = None
        if key in ("replay", "result", "end", "intro"):
            p = next((x for x in m.get("parts", []) if x["id"] == key), None)
            if p is not None and p.get("from_s") is not None:
                at = p["from_s"] if not _AFTER.search(c) else p["to_s"]
                if _BEFORE.search(c):
                    at = max(0.0, p["from_s"] - 1.0)
                return {"at_s": at, "how": "part", "note": f"the {p['name']} runs {p['from_s']:g}-{p['to_s']:g} s"}
            return {"at_s": None, "how": "part", "note": f"this ad has no {key.replace('_', ' ')} part"}
        mm = next((x for x in m.get("moments", []) if x["id"] == key or x.get("also") == key or x["kind"] == key), None)
        if mm is None or mm.get("at_s") is None:
            return {"at_s": None, "how": "moment", "note": f"this ad has no {key.replace('_', ' ')} moment"}
        at = mm["at_s"]
        if _BEFORE.search(c):
            at = max(0.0, at - 1.0)
        elif _AFTER.search(c):
            at = (mm.get("to_s") or at) + 0.5
        return {"at_s": at, "how": "moment", "note": f"{mm['what']} at {mm['at_s']:g} s"}
    return None


# ---------- targets ----------

def _layer(m: dict, lid: str) -> dict | None:
    return next((L for L in m.get("layers", []) if L["id"] == lid), None)


def _caption_by_text(clause: str, m: dict) -> tuple[dict | None, str | None]:
    """A caption named by its words ("remove the 'Hurry!' caption", "change 'Perfect Solve!' to
    'Can you win?'"): the layer and the new text when a second quote gives it."""
    quotes = quoted(clause)
    caps = [L for L in m.get("layers", []) if L["kind"] == "caption" and L.get("text")]
    if len(quotes) == 1:
        # one quote after "to", "with", "say" or a colon is the NEW text, not the caption it names
        m0 = _QUOTED.search(clause)
        before = clause[:m0.start()].rstrip().lower() if m0 else ""
        if re.search(r"\b(to|with|say|says|saying|read|reads|into|as|be)$|:$", before):
            return None, None
    for i, q in enumerate(quotes):
        hit = next((L for L in caps if L["text"].strip().lower() == q.lower()), None) or \
            next((L for L in caps if q.lower() in L["text"].lower() and len(q) >= 4), None)
        if hit:
            new = quotes[i + 1] if i + 1 < len(quotes) else None
            return hit, new
    return None, None


def _target_caption(clause: str, m: dict) -> dict | None:
    c = clause.lower()
    if not re.search(r"\b(caption|text|hook|headline|title|line|words|say|wording|label)\b", c):
        return None
    by_text, new = _caption_by_text(clause, m)
    quotes = quoted(clause)
    located, layer, how = None, None, "name"
    if by_text is not None:
        layer, how = by_text, "its words"
    else:
        for lid, rx in _CAPTION_NAMES:
            if re.search(rx, c):
                layer, how = _layer(m, lid), "name"
                if layer is None:
                    return {"kind": "caption", "id": lid, "name": dict(P.CAPTIONS)[lid][1] if lid in P.CAPTIONS else lid,
                            "missing": True, "how": how, "note": f"this ad has no {dict(P.CAPTIONS)[lid][1] if lid in P.CAPTIONS else lid}"}
                break
        if layer is None and _MOMENT.search(c):
            located = moment(clause, m)
            if located is not None:
                how = "moment"
                if located["at_s"] is not None:
                    on = P.on_screen(m, located["at_s"], kinds=("caption",))
                    if on:
                        layer = on[0]
                        located["on_screen"] = [L["id"] for L in on]
                    else:
                        return {"kind": "caption", "id": None, "name": "the caption at that moment", "missing": True,
                                "how": how, "located": located,
                                "note": f"no caption is on screen there ({located['note']}); the captions are " +
                                        ", ".join(f"{L['id']} {L['from_s']:g}-{L['to_s']:g} s" for L in m.get("layers", []) if L["kind"] == "caption")}
                else:
                    return {"kind": "caption", "id": None, "name": "the caption at that moment", "missing": True,
                            "how": how, "located": located, "note": located["note"]}
            else:
                return {"kind": "caption", "id": None, "name": "the caption at a moment", "missing": True, "how": "moment",
                        "unlocated": True, "note": "the moment could not be placed on the timeline from the metadata"}
    if layer is None:
        return None
    new = new if new is not None else (quotes[-1] if quotes and (by_text is None) else None)
    if new is not None and new.strip().lower() == (layer.get("text") or "").strip().lower():
        new = None
    out = {"kind": "caption", "id": layer["id"], "name": layer["name"], "field": layer["field"], "how": how,
           "when": [layer["from_s"], layer["to_s"]], "text": layer.get("text")}
    if located:
        out["located"] = located
    if _REMOVE.search(c) and new is None and layer.get("can_remove"):
        out["op"] = {"caption": layer["id"], "text": ""}
    elif new is not None and _CHANGE_TEXT.search(c):
        out["op"] = {"caption": layer["id"], "text": new}
    return out


def _target_picture(clause: str, m: dict, uploads: list[str], colour_of=None) -> dict | None:
    c = clause.lower()
    images = [u for u in uploads if not B.is_audio(u)]
    if re.search(r"\b(texture|skin|picture|image|pattern)\b", c) and re.search(r"\b(door|gate|exit)s?\b", c) and \
            not re.search(r"\bblock\b", c):
        return {"kind": "picture", "id": None, "name": "a picture on a door", "missing": True, "how": "name",
                "note": "the game's doors and gates cannot carry a picture: they are the game's own (brief p.5); a texture "
                        "goes on a block, a picture on the walls"}
    for slot, rx in _PICTURE_NAMES:
        g = re.search(rx, c)
        if not g:
            continue
        if slot == "button" and re.search(r"\bbutton'?s?\s+(text|label|words)\b", c):
            continue
        layer = _layer(m, slot)
        out = {"kind": "picture", "id": slot, "name": P.PICTURES[slot]["name"], "field": f"assets[{slot}]", "how": "name"}
        if layer is not None:
            out.update(when=[layer["from_s"], layer["to_s"]], file=layer.get("file"), empty=layer.get("empty"))
        colour = None
        if slot == "skin":
            cm = re.search(r"\b(green|yellow|blue|red|orange|purple|dark green)\s+block\b", c)
            colour = cm.group(1).title().replace(" G", "G") if cm else None
            if colour == "Dark Green":
                colour = "DarkGreen"
            if colour_of is not None:  # the colour as THIS creative shows it ("the cyan block" on a footage-coloured copy)
                for wm in re.finditer(r"\b((?:light |dark |pale |deep |bright |hot )?[a-z]+)\s+blocks?\b", c):
                    hit = colour_of(wm.group(1))
                    if hit:
                        colour = hit
                        break
            out["block"] = colour
        if _REMOVE.search(c) and not images and slot in P.PICTURES and layer is not None and layer.get("can_remove"):
            out["op"] = {"picture": slot, "file": None}
        elif len(images) == 1 and re.search(r"\b(attached|this|the uploaded|uploaded|with it|use it|apply)\b", c):
            if slot != "skin" or colour:
                out["op"] = {"picture": slot, "file": images[0], **({"block": colour} if slot == "skin" else {})}
        return out
    return None


def _target_audio(clause: str, m: dict, uploads: list[str]) -> dict | None:
    c = clause.lower()
    audio = [u for u in uploads if B.is_audio(u)]
    if _MUSIC.search(c):
        layer = _layer(m, "music")
        out = {"kind": "music", "id": "music", "name": "the music", "field": "audio.music", "how": "name",
               "file": (layer or {}).get("file")}
        if _REMOVE.search(c) and not audio:
            out["op"] = {"music": None}
        elif len(audio) == 1:
            out["op"] = {"music": audio[0]}
        return out
    if _SOUND.search(c):
        out = {"kind": "sound", "id": "sound", "name": "the sound effects", "field": "audio.sfx", "how": "name"}
        if _SOUND_OFF.search(c):
            out["op"] = {"sound": False}
        elif _SOUND_ON.search(c):
            out["op"] = {"sound": True}
        return out
    return None


def _target_look(clause: str) -> dict | None:
    c = clause.lower()
    if _CAPTION_LOOK.search(c):
        return {"kind": "look", "id": "captions_look", "name": "the captions' colours", "field": "visuals.captions", "how": "name"}
    if _BACKGROUND.search(c) and re.search(r"\b(colou?r|light|dark|blue|pink|white|black|green|red|yellow|orange|purple|lavender|mint|grey|gray|beige|cream|navy|teal|picture|image|gradient)\b", c):
        return {"kind": "look", "id": "background", "name": "the background behind the board", "field": "visuals.background", "how": "name"}
    if _THEME.search(c):
        return {"kind": "look", "id": "theme", "name": "the look (theme or block colours)", "field": "visuals.colours", "how": "name"}
    return None


def _target_sequence(clause: str) -> dict | None:
    c = clause.lower()
    if _SEQUENCE.search(c) and (_GAME_CHANGE.search(c) or _REMOVE.search(c)) and not re.search(r"\bend[- ]?card'?s?\s+(title|line|picture|background)\b", c):
        return {"kind": "sequence", "id": "sequence", "name": "the ad's parts and their lengths", "field": "sequence", "how": "name"}
    return None


def _is_game_change(clause: str) -> bool:
    c = clause.lower()
    if re.search(r"\b(texture|skin)\b[^.;,]{0,30}\bblock\b|\bblock'?s?\s+(texture|skin)\b", c):
        return False  # a picture on a block, not the block
    return bool(_GAME.search(c) and _GAME_CHANGE.search(c))


# ---------- the decision ----------

def decide(prompt: str, manifest: dict | None = None, uploads: list[str] | None = None, videos: list[str] | None = None,
           matched: dict | None = None, locate=None, colour_of=None) -> dict:
    """The route of a request: see the module note. uploads: the files attached to the prompt
    (images and music); videos: attached reference videos; matched: {creative_id, n} when an
    attached MP4 was recognised as one of the tool's versions; locate: optional f(prompt) -> second
    or None, the multimodal fallback for a moment the metadata cannot place; colour_of: f(word) -> game slot or None,
    the colour words as this creative shows them (brief.slot_of_colour_word), for a texture on "the cyan block"."""
    uploads, videos = list(uploads or []), list(videos or [])
    out = {"intent": "edit" if manifest is not None else "new", "edit_type": None, "analysis_level": 0,
           "requires_video_analysis": False, "requires_gameplay_regeneration": False, "requires_compositing": True,
           "targets": [], "preserve": [], "allowed_groups": [], "direct_op": None, "feasible": True, "notes": [],
           "matched": matched, "level_name": None}
    if manifest is None:
        if videos:
            out.update(edit_type="adapt_reference", analysis_level=2, requires_video_analysis=True,
                       requires_gameplay_regeneration=True)
            out["notes"].append(f"the attached video ({', '.join(videos)}) is read as a whole: its structure, pacing, hook "
                                f"and ending are adapted with the game's own gameplay (brief p.6)")
            if matched is False:
                out["notes"].append("the attached video is not one of this tool's creatives, so it cannot be edited in place: "
                                    "a new creative is made from its concept, with the change asked")
        else:
            out.update(edit_type="new_creative", analysis_level=0)
        out["level_name"] = LEVEL_NAMES[out["analysis_level"]]
        out["why"] = out["notes"][0] if out["notes"] else "a new creative from the prompt alone: nothing to analyse"
        return out
    kept, targets, game, unknown = [], [], [], []
    for cl in clauses(prompt):
        low = cl.lower()
        if (re.match(r"(keep|keeping|same|leave|preserve|don'?t |do not |i like|everything else|nothing else|the rest|otherwise)", low)
                and not _CHANGE_VERBS.search(low)) \
                or re.fullmatch(r"(same ad|the same ad|this ad|this creative|i like (it|this|this creative|this one))", low):
            kept.append(cl)
            continue
        t = (_target_picture(cl, manifest, uploads, colour_of) or _target_caption(cl, manifest) or _target_audio(cl, manifest, uploads)
             or _target_look(cl) or _target_sequence(cl))
        if t is not None:
            t["clause"] = cl
            targets.append(t)
            continue
        if _is_game_change(cl):
            game.append(cl)
            if _KEPT_LEVEL.search(cl):  # "..., keep the same level and play": the level is locked even in a retake
                out["kept_level"] = True
            continue
        if _KEEP.search(cl):
            kept.append(cl)
            continue
        unknown.append(cl)
    out["targets"] = targets
    # a moment the metadata could not place: the optional multimodal fallback
    for t in targets:
        if t.get("unlocated") and locate is not None:
            try:
                at = locate(t["clause"])
            except Exception as e:  # reported, never guessed around
                out["notes"].append(f"the multimodal model could not place the moment: {str(e)[:120]}")
                at = None
            if at is not None:
                on = P.on_screen(manifest, float(at), kinds=("caption",))
                t.update(located={"at_s": float(at), "how": "vision", "note": f"the multimodal model placed it at {at:g} s"},
                         unlocated=False, missing=not on)
                if on:
                    L = on[0]
                    t.update(id=L["id"], name=L["name"], field=L["field"], when=[L["from_s"], L["to_s"]], text=L.get("text"),
                             note=None)
                    quotes = quoted(t["clause"])
                    if quotes and _CHANGE_TEXT.search(t["clause"]):
                        t["op"] = {"caption": L["id"], "text": quotes[-1]}
                else:
                    t["note"] = f"no caption is on screen at {at:g} s"
            out["requires_video_analysis"] = "optional"
    level = 1 if any(t.get("located") or t.get("unlocated") for t in targets) else 0
    if videos:
        level = 2
        out["requires_video_analysis"] = True
    lock = _LOCK.search(prompt)
    if game and lock:
        out.update(edit_type="conflict", feasible=False, requires_gameplay_regeneration=True)
        out["notes"].append("the request changes the puzzle or the play and also asks to keep every frame: it cannot do both; "
                            "say which may change")
    elif game:
        out.update(edit_type="gameplay_edit", requires_gameplay_regeneration=True)
        out["notes"].append("the request changes the puzzle or the play (" + "; ".join(game)[:160] + "): a retake in the game, "
                            "keeping the level, the moves and the timing that still fit")
        if _REFERENCE_EDIT.search(prompt) and videos:
            out["notes"].append("the attached video's structure is read first and adapted")
    elif targets and not unknown:
        out["edit_type"] = "known_layers"
    elif targets:
        out["edit_type"] = "planner"
        out["notes"].append("part of the request is not a known thing in this ad (" + "; ".join(unknown)[:160] + "): the planner reads it")
    else:
        out["edit_type"] = "planner"
        out["notes"].append("the request names nothing the metadata lists: the planner reads it against the list")
    missing = [t for t in targets if t.get("missing")]
    for t in missing:
        out["notes"].append(t.get("note") or f"this ad has no {t['name']}")
    ops = [t["op"] for t in targets if t.get("op")]
    if out["edit_type"] == "known_layers" and len(targets) == 1 and len(ops) == 1 and not missing:
        out["direct_op"], out["edit_type"] = ops[0], "direct"
    out["analysis_level"] = level
    out["level_name"] = LEVEL_NAMES[level]
    touched = {t["kind"] for t in targets if not t.get("missing")}
    pres = []
    for k in PRESERVE_ALL:
        if out["requires_gameplay_regeneration"] and k in ("gameplay", "level", "timing"):
            continue
        if k == "captions" and "caption" in touched or k == "pictures" and "picture" in touched or \
                k == "audio" and touched & {"music", "sound"}:
            continue
        if k == "sequence" and (game or unknown or "sequence" in touched):
            continue
        if k == "timing" and "sequence" in touched:
            continue
        pres.append(k)
    if out.get("kept_level") and "level" not in pres:
        pres.append("level")  # a retake on the same board (2026-10-18: a length edit regenerated the level)
    out["preserve"] = pres
    groups = []
    for t in targets:
        f = t.get("field")
        if not f:
            continue
        groups.append("assets" if f.startswith("assets[") else "audio" if f == "audio.sfx" else f)
        if f == "sequence":
            groups += ["sequence.timing", "pacing.length", "sequence.caption_times"]
    out["allowed_groups"] = sorted(set(groups))
    if targets:
        what = "; ".join(f"{t['name']}" + (f" ({t['when'][0]:g}-{t['when'][1]:g} s)" if t.get("when") and t["when"][0] is not None else "")
                         + (f", {t['located']['note']}" if t.get("located") else "") for t in targets)
        out["why"] = f"target: {what}"
    else:
        out["why"] = out["notes"][0]
    if out["direct_op"]:
        out["why"] += "; the new value is in the request, so the edit is made in code (no planner)"
    out["kept_clauses"] = kept
    return out


def summary(r: dict) -> str:
    """One line for the log and the UI."""
    head = {"new_creative": "a new creative", "adapt_reference": "a creative adapted from the attached video",
            "direct": "a direct edit, made in code", "known_layers": "an edit of known layers through the planner",
            "planner": "an edit through the planner", "gameplay_edit": "a gameplay edit (a retake)",
            "conflict": "a contradiction (refused)"}.get(r.get("edit_type"), r.get("edit_type"))
    bits = [f"{head}: {r.get('level_name')}", r.get("why", "")]
    if r.get("requires_gameplay_regeneration"):
        bits.append("the game films it again")
    elif r.get("intent") == "edit":
        bits.append("the gameplay render is reused")
    if r.get("preserve"):
        bits.append("preserved: " + ", ".join(r["preserve"]))
    return "; ".join(b for b in bits if b)


def text(r: dict) -> str:
    """The route as lines for the planner's edit prompt (the minimal edit plan it must follow)."""
    lines = [f"ROUTE (decided in code from the creative's metadata, before you): {summary(r)}."]
    for t in r.get("targets", []):
        if t.get("missing"):
            lines.append(f"- {t['name']}: NOT in this ad ({t.get('note')}); say so in that control's row and change nothing for it.")
        else:
            lines.append(f"- change {t['name']} (field {t.get('field')}" + (f", now {t['text']!r}" if t.get("text") else "") + ")")
    if r.get("edit_type") == "known_layers":
        lines.append("- the request names only known layers: change their fields, copy every other field from the current brief, "
                     "and never change the level, the moves, the clock or the length.")
    if r.get("preserve"):
        lines.append("- preserve: " + ", ".join(r["preserve"]))
    return "\n".join(lines)


def verify(brief: dict, r: dict, current: dict) -> list[str]:
    """The deterministic check after the planner: on a route that does not change the play, the
    planner may not change the level, the moves, the clock or the length. Anything it did is
    restored from the current brief and noted. Returns the groups restored."""
    if r.get("intent") == "edit" and r.get("requires_gameplay_regeneration") and "level" in r.get("preserve", []):
        # a retake that keeps the level: the planner may not change the board (its label included)
        restored = []
        for g in list(brief.get("changed", [])):
            if not g.startswith("level.") or g in r.get("allowed_groups", []):
                continue
            for path in B.GROUPS.get(g, (None, ()))[1]:
                B._set(brief, path, json.loads(json.dumps(B._get(current, path))))
            brief["changed"].remove(g)
            restored.append(g)
        if restored:
            names = ", ".join(B.GROUP_NAMES.get(g, g) for g in restored)
            B.engine_note(brief, "unchanged", f"the request keeps the level, so {names} stay as they are (the planner had "
                                              f"changed them)", status=None)
        return restored
    if r.get("intent") != "edit" or r.get("requires_gameplay_regeneration") or r.get("edit_type") not in ("direct", "known_layers", "planner"):
        return []
    if r.get("edit_type") == "planner":
        # a clause the metadata did not recognise: if the planner read a change to the play in it,
        # the route is upgraded to a retake rather than second-guessed
        if any(g.startswith(GAME_GROUPS) and g not in r.get("allowed_groups", []) for g in brief.get("changed", [])):
            r.update(edit_type="gameplay_edit", requires_gameplay_regeneration=True)
            r["notes"].append("the planner read a change to the play in the request: a retake")
            r["preserve"] = [k for k in r.get("preserve", []) if k not in ("gameplay", "level", "timing")]
        return []
    restored = []
    for g in list(brief.get("changed", [])):
        if not g.startswith(GAME_GROUPS) or g in r.get("allowed_groups", []):
            continue
        for path in B.GROUPS.get(g, (None, ()))[1]:
            B._set(brief, path, json.loads(json.dumps(B._get(current, path))))
        brief["changed"].remove(g)
        restored.append(g)
    if restored:
        names = ", ".join(B.GROUP_NAMES.get(g, g) for g in restored)
        B.engine_note(brief, "unchanged", f"the route for this edit does not change the play, so {names} stay as they are "
                                          f"(the planner had changed them)", status=None)
    return restored


def check(r: dict | None, proof: dict) -> dict | None:
    """After the edit: did the result follow the route? {ok, evidence}."""
    if not r or r.get("intent") != "edit":
        return None
    chk = (proof or {}).get("checklist") or {}
    reused = (chk.get("gameplay_render_reused") or {}).get("ok")
    expect = not r.get("requires_gameplay_regeneration")
    ok = reused is None or reused == expect or (not expect)
    ev = (f"{r.get('level_name')}; " + ("the gameplay render was reused as routed" if reused and expect else
                                         "a retake as routed" if not expect else
                                         "the gameplay render was NOT reused although the route did not change the play")
          + ("; made in code, no planner" if r.get("edit_type") == "direct" else ""))
    return {"ok": bool(ok), "evidence": ev, "level": r.get("analysis_level"), "edit_type": r.get("edit_type"),
            "video_analysis": r.get("requires_video_analysis")}


# ---------- an uploaded MP4: one of ours, or not ----------

def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


_MEDIA = r"(video|clip|ad|creative|reel|one|reference)"
_NEW_FROM_OWN = re.compile(
    r"\b(version of|same idea|inspired|inspiration|concept|based on (this|the|that)|new (ad|creative|video)|adapt\w*)\b|"
    rf"\b(from|of) (this|that|the attached|the uploaded) {_MEDIA}\b|\b(this|that) {_MEDIA}'s\b|"
    rf"\bthe way (this|that|the) {_MEDIA}\b|(?<!\bi )(?<!\bwe )(?<!\bi really )\blike (this|that)\b|"
    r"\bmatch(es|ing)?\b[^.;]{0,40}\b(of )?(this|that|the attached)\b|\btake\b[^.;]{0,60}\bfrom\b|"
    r"\bonly the (hook|pacing|captions?|ending|look|structure|opening|colou?rs)\b", re.I)
_EDIT_OF_OWN = re.compile(r"\b(keep|keeping|change|changing|replace|replacing|swap|same ad|same creative|same video)\b", re.I)
_SAME_AD_BUT = re.compile(r"\bsame (ad|creative|video)\b[^.;]{0,15}\bbut\b|\bkeep (everything|the rest|it all|all)\b", re.I)


def upload_intent(prompt: str) -> str | None:
    """What one of the tool's own MP4s attached to a new request is for, from the words, checked
    before its bytes route it (2026-10-16, core requirement 4). "create": a NEW creative from it, read
    as a reference by the guided workflow, when the words point at the video as a source ("a version
    of this concept", "same idea", "inspired", "the hook from this video", "the pacing of this clip",
    "this video's ending", "the way this video ends", "like this", "match the look of this", "take
    ... from", "only the hook"), or when no edit word is used and the request describes a creative of
    its own (it states both its length and its ending). "edit": the bytes route the edit to that
    version, as before, for "same ad but", "keep everything", or an edit word ("keep", "change",
    "replace", "swap") that comes before any source word. None: no words either way (an edit).
    (2026-10-16 live run: "Take only the hook from this video ... a clean win, 30 seconds" was routed
    as an edit of the creative it was taken from.)"""
    text = prompt or ""
    new, edit = _NEW_FROM_OWN.search(text), _EDIT_OF_OWN.search(text)
    if _SAME_AD_BUT.search(text):
        return "edit"
    if new and edit:
        return "create" if new.start() < edit.start() else "edit"
    if new:
        return "create"
    if edit:
        return "edit"
    from . import audit  # a request that describes a creative of its own (its length and its ending)
    a = audit.asked(text)
    return "create" if a.get("length_s") is not None and a.get("ending") else None


def match_upload(path: Path, studio: Path) -> dict | None:
    """The tool's version an uploaded video is a copy of ({creative_id, n, file}), matched by
    size first and then by its bytes, or None."""
    path = Path(path)
    if not path.is_file() or not studio.is_dir():
        return None
    size = path.stat().st_size
    sha = None
    for folder in sorted(studio.iterdir(), reverse=True):
        if not folder.is_dir():
            continue
        for vj in folder.glob("v*/version.json"):
            try:
                v = json.loads(vj.read_text())
            except ValueError:
                continue
            for key in ("video", "master"):
                f = studio / v[key] if v.get(key) else None
                if f is None or not f.is_file() or f.stat().st_size != size:
                    continue
                sha = sha or _sha(path)
                if _sha(f) == sha:
                    return {"creative_id": v["id"], "n": v["n"], "file": v[key]}
    return None


# ---------- the optional multimodal fallback ----------

LOCATE_ASK = """This is a contact sheet of a Color Block Jam video ad: one frame per second, left to right then top to bottom, starting at 0 s, {cols} frames per row, {n} frames in all. The request below points at a moment of the ad. Give the second at which that moment is on screen. Return ONLY JSON: {{"at_s": <number or null>, "why": "one line"}}.
REQUEST: {clause}"""


def locate_with_vision(video: Path, clause: str, duration_s: float | None = None, client=None) -> float | None:
    """The second a clause points at, read from a contact sheet of the ad by the multimodal model
    (the research note's Level 1 on pixels). Optional: off with CBJ_LOCATE_BY_VISION=0."""
    if os.environ.get("CBJ_LOCATE_BY_VISION", "1") == "0":
        return None
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not Path(video).is_file():
        return None
    from .reference import _json_in
    if client is None:
        from . import llm
        client = llm.vision_client()
    n = int(math.ceil(duration_s)) if duration_s else 60
    cols = 6
    rows = max(1, -(-n // cols))
    with tempfile.TemporaryDirectory() as tmp:
        sheet = Path(tmp) / "sheet.png"
        subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(video), "-vf", f"fps=1,scale=180:-2,tile={cols}x{rows}",
                        "-frames:v", "1", str(sheet)], check=True)
        data = base64.b64encode(sheet.read_bytes()).decode()
        part = {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{data}"}}
        ask = LOCATE_ASK.format(cols=cols, n=n, clause=clause)
        out = _json_in(client.describe(ask, part, sheet))
    at = out.get("at_s") if isinstance(out, dict) else None
    return float(at) if isinstance(at, (int, float)) else None

