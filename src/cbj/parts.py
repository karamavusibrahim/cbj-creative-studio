"""The parts manifest: the metadata of a finished creative that an edit is routed on.

The case (p.7) asks that an edit of an existing creative change only the requested element and
keep the rest. A flat MP4 cannot tell which pixels are the opening caption; this file can. It is
written with every version (parts.json) from what the tool already stored, with no model and no
look at the pixels:
- parts: the ad's sections in order (the still opening, the gameplay, the replay, the result
  screen, the held board, the end card), each with its seconds and the brief field that controls it;
- layers: every caption, picture, the sound and the music, each with its seconds on screen, its box
  in the frame, its text or file, the brief field that holds it and the route that edits it;
- moments: the gameplay's events on the ad's clock (the first move, each drag, the wrong move, each
  exit, the win or the time-out) with the block's colour, read from the recorder's log;
- clock: when the game's timer shows each whole second, so "the caption when the clock reaches
  five seconds" is a lookup, not a video analysis.
The router (route.py) reads it to decide what an edit touches, the planner is given it as text,
and the UI lists it. A video model is needed only for a video the tool did not make.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from .edits import CAPTIONS, PART_NAMES, PICTURES, inventory

FPS = 30
PART_KINDS = {"teaser": "gameplay", "intro": "still", "play": "gameplay", "replay": "replay", "result": "result",
              "question": "still", "result_hold": "still", "end": "card"}
PART_FIELDS = {"teaser": "sequence", "intro": "sequence.timing", "play": "gameplay", "replay": "sequence",
               "result": "sequence", "question": "gameplay.ending", "result_hold": "sequence.timing", "end": "sequence"}
COLOUR_NAMES = ("green", "yellow", "blue", "red", "orange", "purple", "dark green")  # BlockColor order
ROUTES = {
    "direct": "changed in the brief and composited again; the gameplay render, its timing, the camera and the "
              "audio are reused as they are",
    "planner": "the planner reads the request against this list and changes only the fields it names; the "
               "gameplay render is reused when the fields do not touch the play",
    "retake": "the puzzle or the play changes: a new take in the game, keeping the level, the moves and the "
              "timing that still fit",
}


def _loads(v: dict, studio: Path) -> dict:
    rec, ad_dir = studio / v["recording"]["dir"], studio / v["ad_dir"]
    j = lambda p: json.loads(p.read_text()) if p.is_file() else {}  # noqa: E731
    return {"ad": j(ad_dir / "ad.json"), "compose": j(ad_dir / "compose.json"), "result": j(rec / "result.json"),
            "play": j(rec / "play.json"), "frames": (j(rec / "frames.json") or {}).get("frames", []),
            "level": j(rec / "level.json") or (j(studio / v["level"]["file"]) if v.get("level") else {})}


def _colour_of(level: dict, block: int) -> str | None:
    blocks = (level or {}).get("GridBlockDatas") or []
    if 0 <= block < len(blocks):
        c = blocks[block].get("blockColor")
        if isinstance(c, int) and 0 <= c < len(COLOUR_NAMES):
            return COLOUR_NAMES[c]
    return None


def _ad_time(seg: dict, window: list | tuple, rec_frame: int) -> float | None:
    """The ad's second at which a recording frame is shown by a clip segment, or None."""
    if not seg or seg.get("kind") != "clip" or rec_frame is None or rec_frame < 0:
        return None
    if not (seg["from"] <= rec_frame < seg["to"]):
        return None
    k = (rec_frame - seg["from"]) / seg.get("speed", 1)
    return round((window[0] + k) / FPS, 2)


def _moments(ad: dict, compose: dict, result: dict, play: dict, frames: list, level: dict) -> tuple[list, list]:
    tl = compose.get("timeline", {})
    seg, window = ad.get("segments", {}).get("play"), (tl.get("play") or {}).get("frames")
    if not seg or not window:
        return [], []
    at = lambda f: _ad_time(seg, window, f)  # noqa: E731
    beats = play.get("beats") or []
    moments, drags = [], result.get("drags") or []
    kinds = {"mistake": "a wrong move", "attempt": "a blocked move", "bump": "a blocked move", "short": "a move cut short",
             "hesitate": "a hesitation"}
    first_wrong = None
    for i, d in enumerate(drags):
        b = beats[i] if i < len(beats) else {}
        colour = _colour_of(level, d.get("block", -1)) or (b.get("label") or "a").lower()
        kind = b.get("kind", "solve")
        exits = d.get("exit_frame", -1) is not None and d.get("exit_frame", -1) >= 0
        if kind in kinds:
            what = f"{kinds[kind]}: the {colour} block"
        elif exits:
            what = f"the {colour} block leaves through its door"
        elif b.get("tag") == "key":
            what = f"the key move: the {colour} block moves aside"
        else:
            what = f"the {colour} block moves" + (" aside" if "out of the way" in (b.get("note") or "") else "")
        m = {"id": f"drag_{i}", "kind": kind if kind in kinds else ("exit" if exits else "move"), "block": colour,
             "what": what, "at_s": at(d.get("start_frame")), "to_s": at(d.get("end_frame")),
             "exit_s": at(d.get("exit_frame")) if exits else None, "frame": d.get("start_frame")}
        if i == 0:
            m["also"] = "first_move"
        if kind in kinds and first_wrong is None:
            first_wrong, m["also"] = i, "wrong_move"
        moments.append(m)
    exits = [m for m in moments if m["kind"] == "exit" and m["exit_s"] is not None]
    if exits:
        exits[-1]["also"] = "last_exit"
    for key, name in (("win_frame", "win"), ("fail_frame", "time_out")):
        f = result.get(key, -1)
        if f is not None and f >= 0:
            t = at(f) or _ad_time(ad["segments"].get("result"), (tl.get("result") or {}).get("frames") or [0], f)
            if t is not None:
                moments.append({"id": name, "kind": name, "block": None, "what": "the win screen" if name == "win"
                                else "the time-out (out of time)", "at_s": t, "to_s": None, "exit_s": None, "frame": f})
    clock = []
    last = None
    for fr in frames:
        f, t = fr.get("frame"), fr.get("timer")
        if t is None or f is None or not (seg["from"] <= f < seg["to"]):
            continue
        s = math.ceil(t - 1e-6)  # the whole second the timer shows (65.0 -> 65, 64.9 -> 65)
        if last is not None and s < last:
            for k in range(last - 1, s - 1, -1):
                clock.append({"clock_s": k, "at_s": at(f)})
        if last is None:
            clock.append({"clock_s": s, "at_s": at(f)})
        last = s
    return moments, clock


def build(v: dict, studio: Path) -> dict:
    """The manifest of a version record (version.json), from its stored files."""
    x = _loads(v, studio)
    ad, comp = x["ad"], x["compose"]
    tl = comp.get("timeline", {})
    parts = []
    for sid in ad.get("order", []):
        fr = (tl.get(sid) or {}).get("frames")
        parts.append({"id": sid, "name": PART_NAMES.get(sid, sid), "kind": PART_KINDS.get(sid, "other"),
                      "from_s": round(fr[0] / FPS, 2) if fr else None, "to_s": round(fr[1] / FPS, 2) if fr else None,
                      "frames": fr, "gameplay": PART_KINDS.get(sid) in ("gameplay", "replay"),
                      "field": PART_FIELDS.get(sid, "sequence"), "route": "planner"})
    layers = []
    for it in inventory(ad, comp):
        field = {"caption": it.get("group"), "sound": "audio.sfx", "music": "audio.music"}.get(it["kind"]) or f"assets[{it['id']}]"
        layers.append({"id": it["id"], "kind": it["kind"], "name": it["name"], "text": it.get("text"),
                       "file": it.get("file"), "shows": it.get("shows"), "from_s": it["when"][0] if it.get("when") else None,
                       "to_s": it["when"][1] if it.get("when") else None, "box": it.get("box"), "field": field,
                       "route": "direct", "empty": bool(it.get("empty")), "can_remove": bool(it.get("can_remove"))})
    moments, clock = _moments(ad, comp, x["result"], x["play"], x["frames"], x["level"])
    res = x["result"]
    return {
        "creative": v.get("id"), "version": v.get("n"), "fps": comp.get("fps", FPS),
        "duration_s": comp.get("duration_s", ad.get("length_s")), "frames": comp.get("frames"),
        "parts": parts, "layers": layers, "moments": moments, "clock": clock,
        "gameplay": {"recording": v["recording"]["dir"], "level_sha": (v.get("level") or {}).get("sha"),
                     "drags": len(res.get("drags") or []), "status": res.get("status"),
                     "timer_start_s": res.get("timer_start"), "timer_end_s": res.get("timer_end"),
                     "ending": x["play"].get("ending")},
        "routes": ROUTES,
    }


def write(vdir: Path, v: dict, studio: Path) -> dict:
    m = build(v, studio)
    (vdir / "parts.json").write_text(json.dumps(m, indent=1, ensure_ascii=False))
    return m


def load(v: dict, studio: Path) -> dict:
    """A version's manifest: parts.json when it was written with the version, else built now."""
    p = studio / v["id"] / f"v{v['n']}" / "parts.json"
    if p.is_file():
        try:
            return json.loads(p.read_text())
        except ValueError:
            pass
    return build(v, studio)


def on_screen(m: dict, at_s: float, kinds=("caption", "picture")) -> list[dict]:
    """The layers shown at a second of the ad."""
    return [L for L in m.get("layers", []) if L["kind"] in kinds and L.get("from_s") is not None
            and L["from_s"] - 1e-6 <= at_s <= L["to_s"] + 1e-6]


def part_at(m: dict, at_s: float) -> dict | None:
    for p in m.get("parts", []):
        if p.get("from_s") is not None and p["from_s"] - 1e-6 <= at_s < p["to_s"] + 1e-6:
            return p
    return None


def clock_at(m: dict, clock_s: int) -> float | None:
    """The ad's second when the timer first shows a whole second, or None if it never does."""
    for c in m.get("clock", []):
        if c["clock_s"] == clock_s:
            return c["at_s"]
    return None


def text(m: dict) -> str:
    """The manifest as lines for the planner: what each part and layer is and when, and the
    moments and clock readings an edit may point at."""
    s = lambda t: "?" if t is None else f"{t:g}"  # noqa: E731
    lines = [f"- the ad: {s(m.get('duration_s'))} s, {m.get('fps', FPS)} fps; gameplay {m['gameplay'].get('drags')} drags, "
             f"clock {s(m['gameplay'].get('timer_start_s'))} -> {s(m['gameplay'].get('timer_end_s'))} s, "
             f"ending {m['gameplay'].get('ending') or '?'}"]
    lines.append("- parts: " + "; ".join(f"{p['id']} ({p['name']}) {s(p['from_s'])}-{s(p['to_s'])} s, field {p['field']}"
                                         for p in m.get("parts", [])))
    for L in m.get("layers", []):
        when = f" {s(L['from_s'])}-{s(L['to_s'])} s" if L.get("from_s") is not None else ""
        what = (f"{L['text']!r}" if L["kind"] == "caption" else f"shows {L.get('shows')}" if L["kind"] != "sound"
                else L.get("shows"))
        lines.append(f"- {L['kind']} {L['id']} = {L['name']}{when}: {what}; field {L['field']}; route {L['route']}")
    if m.get("moments"):
        lines.append("- moments: " + "; ".join(f"{mm['id']}{' (' + mm['also'] + ')' if mm.get('also') else ''} at {s(mm['at_s'])} s: {mm['what']}"
                                               for mm in m["moments"]))
    cl = [c for c in m.get("clock", []) if c["at_s"] is not None]
    if cl:
        marks = [c for c in cl if c["clock_s"] % 5 == 0 or c["clock_s"] <= 10]
        lines.append("- the clock shows " + ", ".join(f"0:{c['clock_s']:02d} at {s(c['at_s'])} s" for c in marks[:20]))
    return "\n".join(lines)
