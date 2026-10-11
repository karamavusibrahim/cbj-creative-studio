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
REPLAY_MAX_S = 8.0
END_TITLE = "Color Block Jam"

# Copy guard: statements of odds or IQ are not allowed in ads (UK ASA rulings), dares are.
FORBIDDEN = [(r"\d\s*%", "a percentage"), (r"\bonly\s+\d", "'only N'"), (r"\bIQ\b", "an IQ claim"),
             (r"\b\d+\s*(in|out of)\s*\d+\b", "odds")]
FACT_KEYS = ("clock_left", "colour", "timer", "blocks", "time_used")


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

    def facts(self, beat: int | None = None) -> dict[str, str]:
        r = self.result
        timer = self.play.get("timer_s") or (self.level.timer if self.level else 0)
        f = {"clock_left": clock_text(r.get("timer_end", 0)), "timer": str(timer),
             "blocks": str(len(r.get("block_gone_frames", []))),
             "time_used": f"{max(0.0, timer - r.get('timer_end', 0)):.0f}"}
        if beat is not None and self.level is not None:
            block = self.play["beats"][beat]["block"]
            f["colour"] = color_name(self.level.blocks[block].color)
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


def copy_problems(text: str) -> list[str]:
    return [f"text {text!r} states {what}; ad rules allow dares, not invented odds"
            for pat, what in FORBIDDEN if re.search(pat, text, re.I)]


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
END_FACTS = {"near_fail": "Cleared with {clock_left} left", "time_out": "Out of time. One block left!",
             "win": "Cleared in {time_used} seconds", "cliffhanger": "Two blocks left. Your move!"}


def build_ad(rec: Recording, length_s: float = 30, src: str = "main") -> dict:
    """The default ad for a recording, from its ending: hook, mistake caption, urgency, replay,
    the game's own result screen, end card. Sized to exactly length_s."""
    ending = rec.play.get("ending")
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
    seg = {"play": {"kind": "clip", "src": src, "from": 0, "to": p, "speed": 1, "fit": dict(FIT)}}
    after = []
    if ending != "cliffhanger":
        # The game's own result screen dims the whole screen, so it plays full size (like the replay).
        seg["result"] = {"kind": "clip", "src": src, "from": p, "to": rec.n, "speed": 1, "fit": dict(NATIVE)}
        after = ["result"]
    else:
        seg["question"] = {"kind": "hold", "src": src, "frame": rec.n - 1, "frames": 45, "fit": dict(FIT)}
        after = ["question"]
    fixed = p + sum(seg_frames(seg[a]) for a in after)
    # Replay the last beats in slow motion, as many as fit, so the end card lands near 3-5 s.
    replay_from = None
    card = total - fixed
    for k in range(len(bf) - 1, -1, -1):
        r = 2 * (p - bf[k][0])
        if r > REPLAY_MAX_S * FPS or total - fixed - r < END_CARD_S[0] * FPS:
            break
        replay_from, card = bf[k][0], total - fixed - r
        if card <= END_CARD_S[1] * FPS:
            break
    if card < END_CARD_S[0] * FPS:
        raise ValueError(f"the recording runs {fixed / FPS:.1f} s, too long for a {length_s:g} s ad with a "
                         f"{END_CARD_S[0]:g} s end card; record a shorter scenario or ask for a longer ad")
    order = ["play"]
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
    # The hook stays at least 1.5 s; it gives way to an early mistake caption.
    hook_end = {"seg": "play", "at": 2.4}
    if first is not None and 1.6 <= bf[first][0] / FPS < 2.5:
        hook_end = {"seg": "play", "event": f"beat.{first}.start", "offset": -0.1}
    layers["hook"] = _text(HOOKS[ending], {"seg": "play", "at": 0}, end=hook_end, anim="pop_out",
                           icon="stopwatch.png" if ending in ("near_fail", "time_out") else None)
    if first is not None:
        kind = beats[first]["kind"]
        text = "I can't reach {colour}!" if "in the way" in beats[first]["note"] else "Oops!"
        layers["cap_mistake"] = _text(text, {"seg": "play", "event": f"beat.{first}.start"}, dur=2.0,
                                      style="title_l", beat=first, why=f"the {kind} beat")
    if ending in ("near_fail", "time_out") and rec.event("clock<=5"):
        last_drag = len(rec.result["drags"]) - 1
        hurry_end = {"seg": "play", "event": f"drag.{last_drag}.start"}
        layers["cap_hurry"] = _text("Hurry!", {"seg": "play", "event": "clock<=5"}, end=hurry_end, style="title_xl")
        layers["urgency"] = {"type": "vignette", "color": [255, 40, 40], "max_alpha": 0.35, "pulse_frames": 10,
                             "pulse_on": "clock_second<=5", "start": {"seg": "play", "event": "clock<=5"},
                             "end": {"seg": "play", "at": "end"}}
    if "replay" in seg:
        layers["replay_tag"] = {"type": "tag", "text": "REPLAY", "style": "tag", "pos": [300, 560],
                                "start": {"seg": "replay", "at": 0}, "end": {"seg": "replay", "at": "end"}}
    if ending == "win" and len(bf) >= 3:
        # The closing cascade is the satisfying part of a clean solve.
        layers["cap_cascade"] = _text("So satisfying!", {"seg": "play", "event": f"beat.{len(bf) - 3}.start"},
                                      end={"seg": "play", "at": "end"}, style="title_xl")
    if ending == "near_fail":
        layers["cap_result"] = _text("Phew! {clock_left} left", {"seg": "result", "at": 0},
                                     end={"seg": "result", "at": "end"}, style="title_l")
    elif ending == "time_out":
        layers["cap_result"] = _text("So close!", {"seg": "result", "at": 0}, end={"seg": "result", "at": "end"})
    elif ending == "cliffhanger":
        layers["cap_result"] = _text("Can you see the move?", {"seg": "question", "at": 0},
                                     end={"seg": "question", "at": "end"}, style="title_l")
    notes = _schedule_band(layers, ["hook", "cap_mistake", "cap_hurry", "cap_cascade", "cap_result"], seg, order,
                           rec, src)
    layers["cursor"] = {"type": "cursor", "image": None, "size": 96, "segments": ["play", "replay"]}
    cliff = ending == "cliffhanger"
    layers["end_title"] = {"type": "text", "seg": "end", "text": END_TITLE, "style": "hero", "max_h": 150,
                           "pos": [540, 420 if cliff else 520], "anim": "pop"}
    layers["end_fact"] = {"type": "text", "seg": "end", "text": END_FACTS[ending], "style": "title_m",
                          "max_h": 120, "pos": [540, 560 if cliff else 700], "anim": "pop"}
    if not cliff:
        art = "CoinPile.png" if ending == "win" else "stopwatch.png"
        layers["end_art"] = {"type": "image", "seg": "end", "image": art, "scale": 340 / 512 if art == "stopwatch.png"
                             else 420 / 669, "pos": [540, 1000], "anim": "pop"}
    layers["end_cta"] = {"type": "button", "seg": "end", "image": "ContinueButtonEmpty.png", "text": "PLAY NOW",
                         "pos": [540, 1360 if cliff else 1250], "scale": 0.8 if cliff else 0.9, "pulse": True}
    layers["end_footer"] = {"type": "text", "seg": "end", "text": "Contains in-app purchases", "style": "title_s",
                            "pos": [540, 1460], "enabled": False}

    audio = {"music": None, "events": {
        "taps": {"sound": "click", "event": "drag.*.start", "gain": 0.25},
        "pops": {"sound": "pop", "event": "drag.*.exit", "gain": 0.5, "pitch": "cascade"},
        "ticks": {"sound": "tick", "event": "clock_second<=10", "gain": 0.3, "pitch": "ticktock"},
        "card": {"sound": "whoosh", "seg": "end", "at": 0, "gain": 0.35}}}
    if ending in ("near_fail", "win"):
        audio["events"]["win"] = {"sound": "chord", "event": "win", "gain": 0.6}
    if ending == "time_out":
        audio["events"]["fail"] = {"sound": "womp", "event": "fail", "gain": 0.5}
    if "replay" in seg:
        audio["events"]["rewind"] = {"sound": "whoosh", "seg": "replay", "at": 0, "gain": 0.3}
    bumps = [i for i, b in enumerate(beats) if b.get("push_cells", 0) > 0]
    for i in bumps:
        b = beats[i]
        at = bf[i][0] + b["pickup_f"] + (len(b["path"]) - 1) * b["frames_per_cell"] + 2
        audio["events"][f"bump.{i}"] = {"sound": "bump", "frame": at, "gain": 0.4}

    return {
        "version": 1,
        "concept": ending,
        "length_s": length_s,
        "output": {"w": W, "h": H, "fps": FPS, "safe": "social", "crf": 16},
        "sources": {src: {"recording": str(rec.path), "sha256": rec.sha()}},
        "order": order,
        "segments": seg,
        "layers": {k: v for k, v in layers.items()},
        "audio": audio,
        "locked": ["sources", "segments", "layers/cursor"],
        "notes": notes,
    }


def _schedule_band(layers: dict, priority: list[str], segments: dict, order: list[str], rec: Recording,
                   src: str) -> list[str]:
    """One text at a time in the band: a caption that overlaps a higher-priority one starts after it,
    and one left with less than 0.8 s is dropped. Returns what was changed, for ad.json's notes."""
    probe = {"order": order, "segments": segments, "layers": layers}
    recs = {src: rec}
    taken, notes = [], []
    for lid in priority:
        if lid not in layers:
            continue
        f0, f1 = layer_window(probe, recs, lid)
        for a, b in taken:
            if f0 < b and a < f1:
                f0 = b
        if f1 - f0 < int(0.8 * FPS):
            del layers[lid]
            notes.append(f"{lid} left out: it would overlap another caption or last under 0.8 s")
            continue
        start0 = layer_window(probe, recs, lid)[0]
        if f0 != start0:
            seg_id = layers[lid]["start"].get("seg", "play")
            s0 = timeline(probe)[seg_id][0]
            layers[lid]["start"] = {"seg": seg_id, "at": round((f0 - s0) / FPS, 4)}
            if "dur" in layers[lid]:
                layers[lid]["dur"] = round((f1 - f0) / FPS, 4)
            notes.append(f"{lid} starts at {f0 / FPS:.2f} s so it does not overlap another caption")
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
    for lid, layer in ad["layers"].items():
        if layer.get("type") not in ("text", "tag", "image", "button", "cursor", "vignette"):
            raise ValueError(f"layer {lid!r}: unknown type {layer.get('type')!r}")
