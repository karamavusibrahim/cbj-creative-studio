"""The ad as data: ad.json.

A recording (cbj scenario) is gameplay. An ad puts a hook, captions, a cursor, a replay, sound
and an end card around it. ad.json describes all of that as named parts, so a later edit can
change one part and leave everything else exactly as it was (case p.7):

    segments  what plays, in `order`: a range of a recording (`clip`, any speed), a frozen frame
              (`hold`) or a card. Each clip has a `fit`: the whole recorded frame scaled and
              placed on the canvas (letterboxing, never re-framing the game's camera).
    layers    what is drawn on top: text, a tag, an image, the button, the cursor, a red edge
              pulse. Each one starts and ends at a time that is either a number of seconds into a
              segment or a gameplay event (beat.1.start, clock<=5, win, ...), so it stays on its
              moment if the gameplay is re-planned.
    audio     sound effects at events; an optional music file.
    locked    paths an edit may not change (the gameplay, the camera fit, the cursor).

Texts may use facts from the recording only ({clock_left}, {colour}, {timer}, {blocks}); a copy
guard refuses invented odds ("only 1%", "IQ 140"), which ad rules forbid.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from .describe import color_name
from .level import load_level

FPS = 30
W, H = 1080, 1920
SAFE = {"social": {"top": 250, "bottom": 420, "left": 60, "right": 130},  # Meta Reels + TikTok UI
        "network": {"top": 120, "bottom": 160, "left": 0, "right": 0}}
FIT = {"scale": 0.75, "x": 135, "y": 318}  # HUD from y 481, board to y 1498 (the safe bottom is 1500)
NATIVE = {"scale": 1.0, "x": 0, "y": 0}  # full size: reads as a zoom-in after the 0.75 fit
# The one text band, above the HUD, centred on the board and clear of the platform's right-hand
# buttons (social safe area x 60-950): at most 820 px wide, so long lines wrap to two.
BAND = {"y0": 250, "y1": 476, "cx": 540, "cy": 363, "max_w": 820}  # the HUD starts at y 481
STYLES = {"hero": 118, "title_xl": 96, "title_l": 88, "title_m": 66, "title_s": 52, "tag": 54}
TWO_LINE_SIZE = 80
END_CARD_S = (3.0, 5.0)  # shortest and preferred longest end card
END_CARD_MAX_S = 8.0  # longer than this the ad is mostly a card: refused unless asked for
REPLAY_MAX_S = 5.0  # the replay is a payoff, not filler: the last one or two beats, at most 5 s
REPLAY_MAX_BEATS = 2
INTRO_MAX_S = 2.0  # a frozen first frame under the hook, when the ad has time to spare
END_TITLE = "Color Block Jam"

# Copy guard: statements of odds or IQ are not allowed in ads (UK ASA rulings), dares are.
# "Only 1% can", "only 5 people", "your IQ is 140", "1 in 100" are claims about players; a measured
# fact like "only 00:01 to spare" is not.
WHO = r"(people|players|persons|users|gamers|of\s+(you|us|people|players|users))"
UNITS = r"(seconds?|secs?|minutes?|mins?|moves?|drags?|tries|attempts|levels?|blocks?)"
FORBIDDEN = [(r"\d\s*(%|percent\b)", "a percentage"),
             (rf"\bonly\s+(\d+|one|a\s+few)\s*{WHO}", "'only N' about players"),
             (r"\bonly\s+\d+\s*(can|could|will|get|solve)\b", "'only N' about players"),
             (r"\bIQ\b", "an IQ claim")]
# Odds are a fraction: "1 in 100", "one in a hundred", "1/5 of players". Not odds: a count or a
# time ("Level 3 in 12 seconds", "1 in 10 moves"), a counter ("Level 10/12"), "2 in 1".
ODDS = re.compile(r"\b(\d+|one)\s*(?:\bin\b|\bout\s+of\b|/)\s*(?:a\s+)?(\d+|hundred|thousand|million)\b", re.I)
_AMOUNT = {"one": 1, "hundred": 100, "thousand": 1000, "million": 1000000}
FACT_KEYS = ("clock_left", "colour", "timer", "blocks", "time_used", "blocks_left", "blocks_left_phrase")
NUMBER_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}
NBSP = "\u00a0"  # keeps a multi-word fact ("dark green") on one line


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def clock_text(seconds: float) -> str:
    s = max(0, int(seconds))
    return f"{s // 60:02d}:{s % 60:02d}"


# ---------- a recording and its events ----------

@dataclass
class Recording:
    """A `cbj scenario` folder: the video plus what happened on which frame."""

    path: Path
    result: dict
    frames: list[dict]
    play: dict
    level: object
    events: dict[str, list[int]] = field(default_factory=dict)

    @staticmethod
    def load(path: str | Path) -> "Recording":
        p = Path(path)
        for name in ("gameplay.mp4", "result.json", "frames.json", "play.json"):
            if not (p / name).is_file():
                raise ValueError(f"{p}: no {name}; record it with `cbj scenario` first")
        result = json.loads((p / "result.json").read_text())
        frames = json.loads((p / "frames.json").read_text())["frames"]
        play = json.loads((p / "play.json").read_text())
        level_file = p / "level.json"
        level = load_level(level_file) if level_file.is_file() else None
        rec = Recording(p, result, frames, play, level)
        rec.events = rec._events()
        return rec

    @property
    def n(self) -> int:
        return len(self.frames)

    @property
    def video(self) -> Path:
        return self.path / "gameplay.mp4"

    def _events(self) -> dict[str, list[int]]:
        r, ev = self.result, {}

        def put(name, frame):
            if frame is not None and frame >= 0:
                ev.setdefault(name, []).append(int(frame))

        put("first_touch", r.get("first_touch_frame"))
        put("clock_stop", r.get("clock_stopped_frame"))
        put("win", r.get("win_frame"))
        put("fail", r.get("fail_frame"))
        put("end", self.n - 1)
        if self.play.get("end_mode") == "cut":
            put("cut", self.n - 1)
        for i, (s, e) in enumerate(self.play.get("measured", {}).get("beat_frames", [])):
            put(f"beat.{i}.start", s)
            put(f"beat.{i}.end", e)
        for d in r.get("drags", []):
            i = d["index"]
            put(f"drag.{i}.start", d["start_frame"])
            put(f"drag.{i}.exit", d.get("exit_frame", -1))
            put(f"drag.{i}.end", d.get("end_frame", -1))
            put("drag.*.start", d["start_frame"])
            put("drag.*.exit", d.get("exit_frame", -1))
        for i, g in enumerate(r.get("block_gone_frames", [])):
            put(f"block_gone.{i}", g)
        # Clock events: the game's timer, from the first touch until it stops (or runs out).
        start = r.get("first_touch_frame", 0)
        stop = min(x for x in (r.get("clock_stopped_frame", -1), r.get("fail_frame", -1), self.n - 1) if x >= 0)
        prev = None
        for f in self.frames[start:stop + 1]:
            sec = math.floor(f["timer"])
            if prev is not None and sec < prev:
                put("clock_second", f["frame"])
                put(f"clock_second.{sec}", f["frame"])
            prev = sec
        return ev

    def event(self, name: str) -> list[int]:
        """Frames of an event; `clock<=S` is the first frame with S seconds or less on the clock."""
        m = re.fullmatch(r"clock<=(\d+(?:\.\d+)?)", name)
        if m:
            limit = float(m.group(1))
            start = self.result.get("first_touch_frame", 0)
            for f in self.frames[start:]:
                if f["timer"] <= limit:
                    return [f["frame"]]
            return []
        m = re.fullmatch(r"clock_second<=(\d+)", name)
        if m:
            return [f for k, v in self.events.items() if k.startswith("clock_second.")
                    and int(k.split(".")[1]) <= int(m.group(1)) for f in v]
        return list(self.events.get(name, []))

    def facts(self, beat: int | None = None, names: dict[str, str] | None = None) -> dict[str, str]:
        """Facts a text may use, all measured from the recording. names: a display name per colour
        slot ({"Red": "pink"}), for blocks the recorder repainted."""
        r = self.result
        timer = self.play.get("timer_s") or (self.level.timer if self.level else 0)
        gone = r.get("block_gone_frames", [])
        left = sum(1 for g in gone if g < 0)
        word = NUMBER_WORDS.get(left, str(left))
        f = {"clock_left": clock_text(r.get("timer_end", 0)), "timer": str(timer), "blocks": str(len(gone)),
             "time_used": f"{max(0.0, timer - r.get('timer_end', 0)):.0f}", "blocks_left": str(left),
             "blocks_left_phrase": f"{word}{NBSP}block{'' if left == 1 else 's'}"}
        if beat is not None and self.level is not None:
            block = self.play["beats"][beat]["block"]
            slot = self.level.blocks[block].color
            f["colour"] = ((names or {}).get(slot.name) or color_name(slot)).replace(" ", NBSP)
        return f

    def sha(self) -> str:
        return sha256(self.video)


# ---------- the timeline ----------

def seg_frames(seg: dict) -> int:
    if seg["kind"] == "clip":
        return int(round((seg["to"] - seg["from"]) / seg.get("speed", 1)))
    return int(seg["frames"])


def timeline(ad: dict) -> dict[str, tuple[int, int]]:
    """Each segment's output frames [start, end)."""
    out, t = {}, 0
    for sid in ad["order"]:
        n = seg_frames(ad["segments"][sid])
        out[sid] = (t, t + n)
        t += n
    return out


def source_frame(seg: dict, k: int) -> int:
    """The recording frame shown at output frame k of a segment (k from 0)."""
    if seg["kind"] == "clip":
        return seg["from"] + int(math.floor(k * seg.get("speed", 1) + 1e-9))
    return seg.get("frame", 0)


def to_output(seg: dict, seg_start: int, frame: int) -> int | None:
    """Where a recording frame lands in the output, if this clip shows it."""
    if seg["kind"] != "clip" or not seg["from"] <= frame < seg["to"]:
        return None
    return seg_start + int(math.floor((frame - seg["from"]) / seg.get("speed", 1) + 1e-9))


def resolve_time(ad: dict, recs: dict[str, Recording], spec, default_seg: str | None) -> int:
    """An output frame for {"seg", "at": seconds|"end"} or {"seg", "event", "offset"}."""
    tl = timeline(ad)
    sid = spec.get("seg", default_seg)
    if sid not in ad["segments"]:
        raise ValueError(f"unknown segment {sid!r}")
    if sid not in tl:
        raise ValueError(f"segment {sid!r} is not in the order, so nothing anchored to it can play")
    seg = ad["segments"][sid]
    s0, s1 = tl[sid]
    off = int(round(spec.get("offset", 0) * FPS))
    if "event" in spec:
        rec = recs[seg["src"]] if "src" in seg else None
        frames = rec.event(spec["event"]) if rec else []
        hits = [to_output(seg, s0, f) for f in frames]
        hits = [h for h in hits if h is not None]
        if not hits:
            raise ValueError(f"event {spec['event']!r} is not inside segment {sid!r}")
        return hits[0] + off
    at = spec.get("at", 0)
    return (s1 if at == "end" else s0 + int(round(at * FPS))) + off


def layer_window(ad: dict, recs: dict[str, Recording], lid: str) -> tuple[int, int]:
    layer = ad["layers"][lid]
    seg = layer.get("seg")
    if "start" in layer:
        f0 = resolve_time(ad, recs, layer["start"], seg)
        seg = layer["start"].get("seg", seg)
    else:
        f0 = timeline(ad)[seg][0]
    if "end" in layer:
        f1 = resolve_time(ad, recs, layer["end"], seg)
    elif "dur" in layer:
        f1 = f0 + int(round(layer["dur"] * FPS))
    else:
        f1 = timeline(ad)[seg][1]
    return f0, f1


def fill(text: str, facts: dict[str, str]) -> str:
    def rep(m):
        key = m.group(1)
        if key not in FACT_KEYS:
            raise ValueError(f"unknown fact {{{key}}}; texts may use {', '.join('{' + k + '}' for k in FACT_KEYS)}")
        if key not in facts:
            raise ValueError(f"fact {{{key}}} is not available here (a colour needs the layer's beat)")
        return facts[key]
    return re.sub(r"\{(\w+)\}", rep, text)


def reading_s(text: str) -> float:
    """Seconds a caption needs on screen: 0.4 s plus 0.3 s a word, at least 0.8 s."""
    return max(0.8, 0.4 + 0.3 * len(text.replace(NBSP, " ").split()))


def _states_odds(text: str) -> bool:
    for m in ODDS.finditer(text):
        num, den = (int(g) if g.isdigit() else _AMOUNT[g.lower()] for g in m.groups())
        before, after = text[:m.start()], text[m.end():]
        if (num < den and not re.match(rf"\s*{UNITS}\b", after, re.I)
                and not re.search(r"\b(level|lvl|stage)\s*$", before, re.I)):
            return True
    return False


def copy_problems(text: str) -> list[str]:
    found = [what for pat, what in FORBIDDEN if re.search(pat, text, re.I)]
    if _states_odds(text):
        found.append("odds")
    return [f"text {text!r} states {what}; ad rules allow dares, not invented odds" for what in found]


# ---------- building the default ad ----------

def _text(text, start, end=None, dur=None, style="title_xl", anim="pop", beat=None, **kw):
    layer = {"type": "text", "text": text, "style": style, "slot": "top", "start": start, "anim": anim}
    if end is not None:
        layer["end"] = end
    if dur is not None:
        layer["dur"] = dur
    if beat is not None:
        layer["beat"] = beat
    layer.update(kw)
    return layer


HOOKS = {"near_fail": "Can you beat the clock?", "time_out": "Can you beat the clock?",
         "win": "Can you clear it?", "cliffhanger": "Can you clear it?"}
# With the result shown first (a 1.5 s teaser of the result screen), the hook asks how.
TEASER_HOOKS = {"near_fail": "How did they make it?", "win": "Can you clear it this fast?",
                "time_out": "So close! What went wrong?"}
TEASER_S = 1.5
# Options a brief can set on the default ad (see build_ad).
AD_OPTIONS = {"replay": True, "result_screen": True, "teaser": False, "texts": {}, "fill": None, "stroke": None,
              "colour_names": {}, "logo": None, "hook_icon": None, "end_art": None, "end_background": None,
              "end_gradient": None, "cursor": "ring", "cursor_image": None, "sfx": True, "clock_visible": True}
# With the HUD's clock hidden, the default copy may not quote it (the viewer never saw it).
NO_CLOCK = {"hook": "Can you clear it?", "result": {"near_fail": "Phew! Just in time!"},
            "end_fact": {"near_fail": "Cleared just in time!", "win": "Cleared!"}}
TEXT_LAYERS = {"hook": "hook", "mistake": "cap_mistake", "fix": "cap_fix", "hurry": "cap_hurry",
               "cascade": "cap_cascade", "result": "cap_result", "end_title": "end_title", "end_fact": "end_fact",
               "cta": "end_cta"}
LOGO_BOX = 150  # px; a logo in a top corner, inside the safe area, beside a narrowed caption band
END_FACTS = {"near_fail": "Cleared with {clock_left} left", "time_out": "Out of time with {blocks_left_phrase} left!",
             "win": "Cleared in {time_used} seconds", "cliffhanger": "Your move: {blocks_left_phrase} to go!"}


def build_ad(rec: Recording, length_s: float = 30, src: str = "main", allow_long_card: bool = False,
             options: dict | None = None) -> dict:
    """The default ad for a recording, from its ending: hook, mistake caption, urgency, replay,
    the game's own result screen, end card. Sized to exactly length_s:
    - the replay is the last one or two beats in slow motion (at most 5 s);
    - if time is left, a frozen first frame (up to 2 s) gives the hook room;
    - the end card takes the rest: at least 3 s, and over 8 s only with allow_long_card (the
      recording is then too short for the length, and the ad would be mostly a card).
    options (AD_OPTIONS) come from a brief: replay, result screen, a result-first teaser, texts
    ("" removes a caption), caption colours, colour names for repainted blocks, a logo, a picture
    beside the hook, end-card art and background, the cursor, and sound on or off. What an
    option could not do is written into the ad's notes."""
    o = {**AD_OPTIONS, **(options or {})}
    ending = rec.play.get("ending")
    brief_notes: list[dict] = []  # what the ad could not do, or did as asked, per control of the brief

    def note(control: str, text: str, status: str | None = "adjusted"):
        notes.append(text)
        brief_notes.append({"control": control, "status": status, "text": text})
    if ending not in HOOKS:
        raise ValueError(f"{rec.path}: unknown ending {ending!r}")
    beats = rec.play["beats"]
    bf = rec.play["measured"]["beat_frames"]
    total = int(round(length_s * FPS))
    end_of_play = {"near_fail": rec.event("win"), "win": rec.event("win"), "time_out": rec.event("fail"),
                   "cliffhanger": [rec.n]}[ending]
    if not end_of_play:
        raise ValueError(f"{rec.path}: the recording has no {ending} moment to build the ad around")
    p = end_of_play[0]
    notes: list[str] = []
    seg = {"play": {"kind": "clip", "src": src, "from": 0, "to": p, "speed": 1, "fit": dict(FIT)}}
    after = []
    if ending == "cliffhanger":
        seg["question"] = {"kind": "hold", "src": src, "frame": rec.n - 1, "frames": 2 * FPS, "fit": dict(FIT)}
        after = ["question"]
    elif o["result_screen"]:
        # The game's own result screen dims the whole screen, so it plays full size (like the replay).
        seg["result"] = {"kind": "clip", "src": src, "from": p, "to": rec.n, "speed": 1, "fit": dict(NATIVE)}
        after = ["result"]
    teaser = 0
    if o["teaser"]:
        t0 = p + 12  # the result screen once it has dimmed and shown its banner
        teaser = int(TEASER_S * FPS)
        if ending == "cliffhanger" or t0 + teaser > rec.n:
            note("sequence", "result-first teaser left out: this recording has no result screen to show first")
            teaser = 0
        else:
            # Letterboxed like the gameplay, so the hook sits in the band above it, not on the game's
            # own "Level Completed" banner.
            seg["teaser"] = {"kind": "clip", "src": src, "from": t0, "to": t0 + teaser, "speed": 1, "fit": dict(FIT)}
    fixed = p + sum(seg_frames(seg[a]) for a in after) + teaser
    replay_from, card = None, total - fixed
    for k in range(len(bf) - 1, max(-1, len(bf) - 1 - REPLAY_MAX_BEATS) if o["replay"] else len(bf) - 1, -1):
        r = 2 * (p - bf[k][0])
        if r > REPLAY_MAX_S * FPS or total - fixed - r < END_CARD_S[0] * FPS:
            break
        replay_from, card = bf[k][0], total - fixed - r
        if card <= END_CARD_S[1] * FPS:
            break
    intro = 0
    if card > END_CARD_S[1] * FPS and not teaser:
        intro = min(int(INTRO_MAX_S * FPS), card - int(END_CARD_S[1] * FPS))
        card -= intro
    if card < END_CARD_S[0] * FPS:
        raise ValueError(f"the recording runs {fixed / FPS:.1f} s, too long for a {length_s:g} s ad with a "
                         f"{END_CARD_S[0]:g} s end card; record a shorter scenario or ask for a longer ad")
    if card > END_CARD_MAX_S * FPS and not allow_long_card:
        raise ValueError(f"the recording is too short for a {length_s:g} s ad: the end card would run "
                         f"{card / FPS:.1f} s (at most {END_CARD_MAX_S:g}); record a longer scenario (a bigger "
                         f"level, more mistakes), ask for a shorter ad, or allow a long card")
    order = ["teaser"] if teaser else []
    if intro:
        seg["intro"] = {"kind": "hold", "src": src, "frame": 0, "frames": intro, "fit": dict(FIT)}
        order.append("intro")
    order.append("play")
    if replay_from is not None:
        seg["replay"] = {"kind": "clip", "src": src, "from": replay_from, "to": p, "speed": 0.5, "fit": dict(NATIVE)}
        order.append("replay")
    order += after + ["end"]
    seg["end"] = {"kind": "card", "frames": card, "background": "StartBACKGROUND.png"}
    if ending == "cliffhanger":
        # The unsolved board stays on the end card: the viewer is left with the puzzle.
        seg["end"]["thumb"] = {"src": src, "frame": rec.n - 1, "crop_y": [200, 1600], "scale": 0.40,
                               "pos": [540, 960]}

    layers = {}
    first = next((i for i, b in enumerate(beats) if b["kind"] in ("mistake", "attempt")), None)
    # The hook is on screen 1.5-3 s from frame 0; it gives way early to a mistake, never drops it.
    intro_s = intro / FPS
    default_hook = TEASER_HOOKS.get(ending, HOOKS[ending]) if teaser else HOOKS[ending]
    if not o["clock_visible"] and "clock" in default_hook:
        default_hook = NO_CLOCK["hook"]
    hook_text = o["texts"].get("hook") or default_hook
    if o["texts"].get("hook") == "":
        note("concept", "the hook stays: frame 0 needs it (it is the poster and the first thing a feed shows)")
    hook_min = max(1.5, reading_s(fill(hook_text, rec.facts(None))))
    hook_play_end = max(1.0 if intro else 2.4, hook_min - intro_s)
    if first is not None:
        m = bf[first][0] / FPS
        if m - 0.1 < hook_play_end:
            hook_play_end = max(hook_min - intro_s, m - 0.1, 0.0)
    if first is not None and abs(hook_play_end - (bf[first][0] / FPS - 0.1)) < 1e-9:
        hook_end = {"seg": "play", "event": f"beat.{first}.start", "offset": -0.1}
    else:
        hook_end = {"seg": "play", "at": round(hook_play_end, 4)}
    if teaser:
        # The hook asks how, over the result shown first, and stays into the gameplay until it can
        # be read.
        hook_end = {"seg": "play", "at": round(max(0.3, hook_min - TEASER_S + 0.2), 4)}
    layers["hook"] = _text(hook_text, {"seg": order[0], "at": 0}, end=hook_end, anim="pop_out",
                           icon="stopwatch.png" if ending in ("near_fail", "time_out") and not teaser
                           and o["clock_visible"] else None)
    if first is not None:
        kind = beats[first]["kind"]
        text = "I can't reach {colour}!" if "in the way" in beats[first]["note"] else "Oops!"
        layers["cap_mistake"] = _text(text, {"seg": "play", "event": f"beat.{first}.start"}, dur=2.0,
                                      style="title_l", beat=first, why=f"the {kind} beat")
        fix = first + 1
        drags = rec.result.get("drags", [])
        if (ending in ("near_fail", "time_out") and fix < len(beats) and beats[fix]["kind"] == "solve"
                and fix < len(drags) and drags[fix].get("exit_frame", -1) < 0):
            # The fix after the mistake: a block moved out of the way first.
            layers["cap_fix"] = _text("Aha! Move {colour} first", {"seg": "play", "event": f"beat.{fix}.start"},
                                      dur=2.0, style="title_l", beat=fix)
    if ending in ("near_fail", "time_out") and rec.event("clock<=5"):
        last_drag = len(rec.result["drags"]) - 1
        hurry_end = {"seg": "play", "event": f"drag.{last_drag}.start"}
        layers["cap_hurry"] = _text("Hurry!", {"seg": "play", "event": "clock<=5"}, end=hurry_end, style="title_xl")
        layers["urgency"] = {"type": "vignette", "color": [255, 40, 40], "max_alpha": 0.35, "pulse_frames": 10,
                             "pulse_on": "clock_second<=5", "start": {"seg": "play", "event": "clock<=5"},
                             "end": {"seg": "play", "at": "end"}}
    if "replay" in seg:
        # Over the HUD's Level badge: the one spot of a full-size frame that never hides the play.
        circle = next((u for u in rec.result.get("ui_rects", []) if u["name"] == "LevelCircle"), None)
        pos = [round(circle["x"] + circle["w"] / 2), round(circle["y"] + circle["h"] / 2)] if circle else [218, 337]
        diameter = round(max(circle["w"], circle["h"]) + 12) if circle else 252
        layers["replay_tag"] = {"type": "tag", "text": "REPLAY", "style": "tag", "pos": pos, "shape": "circle",
                                "diameter": diameter,
                                "safe_exempt": "covers the game's own HUD level circle, which sits there",
                                "start": {"seg": "replay", "at": 0}, "end": {"seg": "replay", "at": "end"}}
    key = next((i for i, b in enumerate(beats) if b.get("tag") == "key"), None)
    if ending == "win" and key is not None and key + 2 < len(bf):
        # A satisfying finish: from the key move, every block leaves one after another.
        layers["cap_cascade"] = _text("One move frees them all!", {"seg": "play", "event": f"beat.{key}.start"},
                                      end={"seg": "play", "at": "end"}, style="title_l")
    elif ending == "win" and len(bf) >= 3:
        # The closing cascade is the satisfying part of a clean solve.
        layers["cap_cascade"] = _text("So satisfying!", {"seg": "play", "event": f"beat.{len(bf) - 3}.start"},
                                      end={"seg": "play", "at": "end"}, style="title_xl")
    # Result captions wait 0.3 s for the game to dim the screen (the full-size HUD is in the band).
    if ending == "near_fail" and "result" in seg:
        # Under the game's "+50" button: the banner and coins fill the top half of the win screen.
        phew = "Phew! {clock_left} left" if o["clock_visible"] else NO_CLOCK["result"]["near_fail"]
        layers["cap_result"] = _text(phew, {"seg": "result", "at": 0.3},
                                     end={"seg": "result", "at": "end"}, style="title_l", slot="free", pos=[540, 1418])
    elif ending == "time_out" and "result" in seg:
        layers["cap_result"] = _text("So close!", {"seg": "result", "at": 0.3}, end={"seg": "result", "at": "end"})
    elif ending == "cliffhanger":
        layers["cap_result"] = _text("Can you see the move?", {"seg": "question", "at": 0},
                                     end={"seg": "question", "at": "end"}, style="title_l")
    for key, text in o["texts"].items():
        lid = TEXT_LAYERS.get(key)
        if text is None or lid is None or lid.startswith("end_") or lid == "hook":
            continue
        if lid not in layers:
            note("concept", f"no {key} moment in this {ending.replace('_', '-')} ad, so its text is not used")
        elif text == "":
            del layers[lid]
            note("concept", f"the {key} caption is removed, as asked", None)
        else:
            layers[lid]["text"] = text
    if o["hook_icon"] and "hook" in layers:
        layers["hook"]["icon"] = o["hook_icon"]
    names = o["colour_names"]
    for n in _schedule_band(layers, ["hook", "cap_mistake", "cap_fix", "cap_hurry", "cap_cascade", "cap_result"],
                            seg, order, rec, src, names):
        note("concept", n, "adjusted" if "left out" in n else None)
    layers["cursor"] = {"type": "cursor", "image": o["cursor_image"] or ("builtin:hand" if o["cursor"] == "hand" else None),
                        "size": 96, "segments": ["play", "replay"]}
    if o["cursor"] == "none" and not o["cursor_image"]:
        del layers["cursor"]
    cliff = ending == "cliffhanger"
    layers["end_title"] = {"type": "text", "seg": "end", "text": END_TITLE, "style": "hero", "max_h": 150,
                           "pos": [540, 420 if cliff else 520], "anim": "pop"}
    end_fact = END_FACTS[ending] if o["clock_visible"] else NO_CLOCK["end_fact"].get(ending, END_FACTS[ending])
    layers["end_fact"] = {"type": "text", "seg": "end", "text": end_fact, "style": "title_m",
                          "max_h": 120, "pos": [540, 560 if cliff else 700], "anim": "pop"}
    if not cliff:
        art = "CoinPile.png" if ending == "win" else "stopwatch.png"
        layers["end_art"] = {"type": "image", "seg": "end", "image": art, "scale": 340 / 512 if art == "stopwatch.png"
                             else 420 / 669, "pos": [540, 1000], "anim": "pop"}
    layers["end_cta"] = {"type": "button", "seg": "end", "image": "ContinueButtonEmpty.png", "text": "PLAY NOW",
                         "pos": [540, 1360 if cliff else 1250], "scale": 0.8 if cliff else 0.9, "pulse": True}
    layers["end_footer"] = {"type": "text", "seg": "end", "text": "Contains in-app purchases", "style": "title_s",
                            "pos": [540, 1460], "enabled": False}
    for key in ("end_title", "end_fact", "cta"):
        text = o["texts"].get(key)
        lid = TEXT_LAYERS[key]
        if text == "" and key != "cta":
            del layers[lid]
            note("concept", f"the {key.replace('_', ' ')} is removed, as asked", None)
        elif text:
            layers[lid]["text"] = text
    if o["end_art"]:
        if cliff:
            note("assets", "end-card picture not used: the cliffhanger's end card shows the unsolved board there")
        else:
            layers["end_art"] = {"type": "image", "seg": "end", "image": o["end_art"], "box": [460, 420],
                                 "pos": [540, 1000], "anim": "pop"}
    if o["end_background"]:
        seg["end"]["background"] = o["end_background"]
    elif o["end_gradient"]:
        seg["end"]["gradient"] = list(o["end_gradient"])
    for lay in layers.values():  # caption colours, on every text the ad draws
        if lay["type"] == "text":
            if o["fill"]:
                lay["fill"] = o["fill"]
            if o["stroke"]:
                lay["stroke"] = o["stroke"]
    band = None
    if o["logo"]:
        # A logo in a top corner, inside the safe area, for the gameplay and the end card; the
        # caption band narrows to make room. It steps aside during the full-size replay and result
        # screens, where the HUD sits in that corner.
        where = o["logo"].get("where", "top_left")
        x = SAFE["social"]["left"] + LOGO_BOX // 2 if where != "top_right" else W - SAFE["social"]["right"] - LOGO_BOX // 2
        y = SAFE["social"]["top"] + LOGO_BOX // 2
        logo = {"type": "image", "image": o["logo"]["file"], "box": [LOGO_BOX, LOGO_BOX], "pos": [x, y], "anim": "none"}
        first_fit = next(sid for sid in order if sid in ("intro", "play"))
        layers["logo"] = {**logo, "start": {"seg": first_fit, "at": 0}, "end": {"seg": "play", "at": "end"}}
        layers["logo_end"] = {**logo, "seg": "end"}
        shift = (LOGO_BOX + 20) // 2
        band = {"cx": BAND["cx"] + (shift if where != "top_right" else -shift), "max_w": BAND["max_w"] - 2 * shift}

    audio = {"music": None, "events": {
        "taps": {"sound": "click", "event": "drag.*.start", "gain": 0.25},
        "pops": {"sound": "pop", "event": "drag.*.exit", "gain": 0.5, "pitch": "cascade"},
        "ticks": {"sound": "tick", "event": "clock_second<=10", "gain": 0.3, "pitch": "ticktock", "slowmo": False},
        "card": {"sound": "whoosh", "seg": "end", "at": 0, "gain": 0.35}}}
    if ending in ("near_fail", "win") and "result" in seg:
        audio["events"]["win"] = {"sound": "chord", "event": "win", "gain": 0.6}
    if ending == "time_out" and "result" in seg:
        audio["events"]["fail"] = {"sound": "womp", "event": "fail", "gain": 0.5}
    if "replay" in seg:
        audio["events"]["rewind"] = {"sound": "whoosh", "seg": "replay", "at": 0, "gain": 0.3}
    bumps = [i for i, b in enumerate(beats) if b.get("push_cells", 0) > 0]
    for i in bumps:
        b = beats[i]
        at = bf[i][0] + b["pickup_f"] + (len(b["path"]) - 1) * b["frames_per_cell"] + 2
        audio["events"][f"bump.{i}"] = {"sound": "bump", "frame": at, "gain": 0.4}
    if intro:
        notes.append(f"a {intro / FPS:.1f} s frozen intro gives the hook room (the recording is short for "
                     f"{length_s:g} s)")
    if not o["sfx"]:
        audio["events"] = {}
        note("assets", "no sound effects, as asked (the track is silent)", None)
    if not o["clock_visible"]:
        for key in ("hook", "result", "end_fact"):
            if "{clock_left}" in (o["texts"].get(key) or "") or "{time_used}" in (o["texts"].get(key) or ""):
                note("concept", f"the {key.replace('_', ' ')} quotes the clock, which is hidden in this ad")

    ad = {
        "version": 1,
        "concept": ending,
        **({"band": band} if band else {}),
        **({"colour_names": names} if names else {}),
        "brief_notes": brief_notes,
        "length_s": length_s,
        "output": {"w": W, "h": H, "fps": FPS, "safe": "social", "crf": 16},
        "sources": {src: {"recording": str(rec.path.resolve()), "sha256": rec.sha()}},
        "order": order,
        "segments": seg,
        "layers": {k: v for k, v in layers.items()},
        "audio": audio,
        "locked": ["sources", "segments", "layers/cursor"],
        "notes": notes,
    }
    ad["origin"] = {"locked": locked_digests(ad)}
    return ad


def _get_path(ad: dict, path: str):
    node = ad
    for part in path.split("/"):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def locked_digests(ad: dict) -> dict[str, str]:
    """A hash of each locked part, written when the ad is made; an edit that changes one fails QA."""
    return {path: hashlib.sha256(json.dumps(_get_path(ad, path), sort_keys=True).encode()).hexdigest()[:32]
            for path in ad.get("locked", [])}


def _schedule_band(layers: dict, priority: list[str], segments: dict, order: list[str], rec: Recording,
                   src: str, names: dict | None = None) -> list[str]:
    """One text at a time in the band. A caption that overlaps a higher-priority one starts after
    it, keeping its anchor (with a later offset) and its length, cut at the end of its segment;
    one that can then not be read in time (reading_s) is left out. Returns what was changed."""
    probe = {"order": order, "segments": segments, "layers": layers}
    recs = {src: rec}
    tl = timeline(probe)
    taken, notes = [], []
    for lid in priority:
        if lid not in layers or layers[lid].get("slot") != "top":
            continue  # only captions in the shared band compete for time
        lay = layers[lid]
        f0_orig, f1 = layer_window(probe, recs, lid)
        f0 = f0_orig
        for a, b in sorted(taken):
            end = f1 + (f0 - f0_orig) if "dur" in lay else f1  # a fixed end does not move with the start
            if f0 < b and a < end:
                f0 = max(f0, b)
        seg_id = lay["start"].get("seg", "play")
        s1 = tl[seg_id][1]
        if "dur" in lay:
            f1 = min(f0 + int(round(lay["dur"] * FPS)), s1)
        text = fill(lay["text"], rec.facts(lay.get("beat"), names))
        if (f1 - f0) / FPS < reading_s(text) - 1e-6:
            del layers[lid]
            notes.append(f"{lid} left out: it would overlap another caption or be too short to read")
            continue
        if f0 != f0_orig:
            st = lay["start"]
            delta = (f0 - f0_orig) / FPS
            if "event" in st:
                st["offset"] = round(st.get("offset", 0) + delta, 4)
            elif st.get("at") != "end":
                st["at"] = round(st.get("at", 0) + delta, 4)
            notes.append(f"{lid} starts at {f0 / FPS:.2f} s so it does not overlap another caption")
        if "dur" in lay:
            lay["dur"] = round((f1 - f0) / FPS, 4)
        taken.append((f0, f1))
    return notes


def load_ad(path: str | Path) -> dict:
    ad = json.loads(Path(path).read_text())
    check_ad(ad)
    return ad


def check_ad(ad: dict) -> None:
    """Structural checks; raises ValueError naming the first problem."""
    for key in ("version", "output", "sources", "order", "segments", "layers"):
        if key not in ad:
            raise ValueError(f"ad.json has no {key!r}")
    for sid in ad["order"]:
        if sid not in ad["segments"]:
            raise ValueError(f"order names segment {sid!r}, which is not defined")
        seg = ad["segments"][sid]
        if seg.get("kind") not in ("clip", "hold", "card"):
            raise ValueError(f"segment {sid!r}: kind must be clip, hold or card")
        if seg["kind"] in ("clip", "hold") and seg.get("src") not in ad["sources"]:
            raise ValueError(f"segment {sid!r}: source {seg.get('src')!r} is not in sources")
        if seg["kind"] == "clip" and not (0 <= seg["from"] < seg["to"] and 0 < seg.get("speed", 1) <= 4):
            raise ValueError(f"segment {sid!r}: needs 0 <= from < to and 0 < speed <= 4")
        if seg["kind"] != "clip" and not int(seg.get("frames", 0)) > 0:
            raise ValueError(f"segment {sid!r}: frames must be positive")
        if seg["kind"] in ("clip", "hold"):
            fit = seg.get("fit")
            if not (isinstance(fit, dict) and all(isinstance(fit.get(k), (int, float)) for k in ("scale", "x", "y"))
                    and fit["scale"] > 0):
                raise ValueError(f"segment {sid!r}: needs a fit {{scale, x, y}} (scale above 0)")
    for lid, layer in ad["layers"].items():
        if layer.get("type") not in ("text", "tag", "image", "button", "cursor", "vignette"):
            raise ValueError(f"layer {lid!r}: unknown type {layer.get('type')!r}")
