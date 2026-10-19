"""The viewer's review: does the finished ad match the prompt, and would a viewer watch it and tap?

The deterministic checks prove the gameplay and the edit report proves an edit; neither says
whether the ad reads well to a person scrolling a feed. This module asks a multimodal model to
look at the finished video as that person, against the prompt and the plan, with a fixed rubric
(RUBRIC). What can be measured is measured here and given to the model, never guessed by it: the
second the game first moves, the share of the ad that is a held screen, each caption's time on
screen against its reading time. The model judges what only eyes can: whether what is seen is
what was asked, whether the puzzle reads, whether the captions and the button land, and what one
edit would make it better. The result is stored as review.json next to the version and shown in
the UI; its suggested edit is one click away, which is the loop: review, edit, review.

The contact sheet: one frame a second of the finished ad, in a labelled grid, so the model sees
the whole ad in one picture with the time under each frame.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import brief as B
from .ad import reading_s
from .reference import _json_in
from .video import ffmpeg_bin

CONTROLS = list(B.CONTROLS)
STATIC_PARTS = ("intro", "result_hold", "end")  # held frames and the card: no game motion
COLUMNS = 6
TILE_W = 270  # a 9:16 frame at 270x480

RUBRIC = """You are a person scrolling a social feed who likes casual puzzle games. You see this ad once, with the sound off. Judge it as that person, strictly, against what the marketer asked for.

MATCH, one verdict per control the marketer mentioned ("match", "partial", "no"; "not asked" when the prompt says nothing about it): the level's type or structure; the gameplay behaviour (the ending, mistakes, the order of moves); difficulty or pacing; visual elements; the creative concept (hook and captions); the sequence of events (what comes after what); the assets used (pictures, music); what had to remain unchanged. For each, say what you SEE in the frames (name the seconds) against what was asked. A plan row says what the tool meant to do; judge the frames, not the plan.

VIEWER SCORES 1-5 (5 = excellent). Measured scores are given to you and are final: the first second (does the game move at once?) and dead time (held screens). You score: pace (does the play keep moving at a rate a viewer follows, neither racing nor dragging?), readability (can each caption be read in the time it shows, over what is behind it?), clarity (is it obvious what the game is and what the player must do, from the first seconds?), cta (does the end card make the next step obvious, and is it on screen long enough but not too long?).

WOULD YOU DOWNLOAD: "yes", "maybe" or "no", and why in one sentence from the viewer's seat.

FIXES: up to three concrete, plain-words changes that would most improve the ad, in order of effect; each must be something an edit prompt can ask this tool for (a caption, a colour, the hook, the pace, the length of a part, a picture, the music, the ending, the level's difficulty or size). Then ONE edit prompt, in the marketer's voice, that applies the best fix and keeps everything else ("Keep everything, but ..."); empty if nothing is worth changing.

Write plain words a marketer reads: no field names, no JSON keys, no hex codes."""

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["match", "viewer", "would_download", "why", "fixes", "suggested_edit"],
          "properties": {
              "match": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                                   "required": ["control", "verdict", "seen"],
                                                   "properties": {"control": {"type": "string"},
                                                                  "verdict": {"type": "string", "enum": ["match", "partial", "no", "not asked"]},
                                                                  "seen": {"type": "string"}}}},
              "viewer": {"type": "object", "additionalProperties": False, "required": ["pace", "readability", "clarity", "cta"],
                         "properties": {k: {"type": "integer", "minimum": 1, "maximum": 5} for k in ("pace", "readability", "clarity", "cta")}},
              "would_download": {"type": "string", "enum": ["yes", "maybe", "no"]},
              "why": {"type": "string"},
              "fixes": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
              "suggested_edit": {"type": "string"}}}

COLOUR_NAMES = ("green", "yellow", "blue", "red", "orange", "purple", "dark green")  # the game's BlockColor order

CONTROL_WORDS = {"level": "the type or structure of the level", "gameplay": "gameplay behaviour",
                 "difficulty_pacing": "difficulty or pacing", "visuals": "visual elements", "concept": "the creative concept",
                 "sequence": "the sequence of events", "assets": "the assets to use", "unchanged": "what should remain unchanged"}


def facts(version: dict, studio_dir: Path) -> dict:
    """What can be measured about the finished ad: its parts, when the game first moves, how much
    of it is a held screen, and each caption's time on screen against its reading time."""
    vdir = studio_dir / version["id"] / f"v{version['n']}"
    compose = json.loads((vdir / "ad" / "compose.json").read_text())
    fps = compose.get("fps", 30)
    total = compose["frames"] / fps
    parts = {name: round((w["frames"][1] - w["frames"][0]) / fps, 1) for name, w in compose["timeline"].items()}
    static = sum(parts.get(p, 0) for p in STATIC_PARTS)
    rec = json.loads((studio_dir / version["recording"]["dir"] / "result.json").read_text())
    intro = compose["timeline"].get("intro", {"frames": [0, 0]})["frames"]
    first_move_s = round((intro[1] - intro[0] + rec.get("first_touch_frame", 0)) / fps, 1)
    captions = []
    for lid, lay in compose["layers"].items():
        if lay.get("type") == "text" and lay.get("text"):
            on = (lay["frames"][1] - lay["frames"][0]) / fps
            captions.append({"id": lid, "text": lay["text"], "from_s": round(lay["frames"][0] / fps, 1),
                             "to_s": round(lay["frames"][1] / fps, 1), "needs_s": round(reading_s(lay["text"]), 1),
                             "readable": on >= reading_s(lay["text"])})
    drags = []
    try:
        level = json.loads((vdir / "level.json").read_text())
        names = {i: COLOUR_NAMES[b["blockColor"]] for i, b in enumerate(level["GridBlockDatas"])}
        lead = intro[1] - intro[0] - rec.get("first_touch_frame", 0)  # ad time = recording frame + lead
        for i, d in enumerate(rec.get("drags") or []):
            what = "leaves" if d.get("result") == "exit" else "is stopped" if d.get("result") == "interrupted" else "moves"
            drags.append(f"drag {i + 1}: {names.get(d.get('block'), 'a')} block {what} "
                         f"({(d['start_frame'] + lead) / fps:.1f}-{(d['end_frame'] + lead) / fps:.1f} s)")
    except (OSError, KeyError, IndexError, TypeError, ValueError):
        pass
    return {"length_s": round(total, 1), "parts": parts, "first_move_s": first_move_s, "drags": drags,
            "static_s": round(static, 1), "static_share": round(static / total, 2) if total else 0.0,
            "captions": captions, "checks": [c for c in version.get("checks", []) if c.get("status") not in ("pass", "info")],
            "qa": version.get("qa", {}).get("warnings", [])}


def measured_scores(f: dict) -> dict:
    """The two scores that numbers decide: the first second and dead time."""
    m = f["first_move_s"]
    first = 5 if m <= 1.5 else 4 if m <= 2.5 else 3 if m <= 3.5 else 2 if m <= 5 else 1
    s = f["static_share"]
    dead = 5 if s <= 0.25 else 4 if s <= 0.35 else 3 if s <= 0.45 else 2 if s <= 0.55 else 1
    return {"first_second": first, "dead_time": dead}


def contact_sheet(video: Path, out: Path, every_s: float = 1.0) -> Path:
    """One frame every `every_s` seconds of the video, in a grid with the second under each frame."""
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([ffmpeg_bin(), "-v", "error", "-i", str(video), "-vf", f"fps=1/{every_s},scale={TILE_W}:-2",
                        str(Path(tmp) / "f%04d.png")], check=True)
        frames = sorted(Path(tmp).glob("f*.png"))
        if not frames:
            raise ValueError(f"no frames read from {video}")
        tiles = [Image.open(f).convert("RGB") for f in frames]
    tw, th = tiles[0].size
    label_h = 26
    cols = min(COLUMNS, len(tiles))
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw, rows * (th + label_h)), (20, 20, 28))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 18)
    except OSError:
        font = ImageFont.load_default()
    for i, tile in enumerate(tiles):
        x, y = (i % cols) * tw, (i // cols) * (th + label_h)
        sheet.paste(tile, (x, y))
        draw.text((x + 6, y + th + 4), f"{i * every_s:g} s", fill=(240, 240, 240), font=font)
    sheet.save(out)
    return out


def question(prompt: str, brief: dict, f: dict, edit_of: dict | None = None) -> str:
    rows = "\n".join(f"- {CONTROL_WORDS.get(r['control'], r['control'])}: {r['status']}; asked: {r['asked'] or 'nothing'}; "
                     f"the tool's plan: {r['plan']}" for r in brief.get("controls", []))
    caps = "\n".join(f"- {c['from_s']}-{c['to_s']} s: \"{c['text']}\" (needs {c['needs_s']} s to read; "
                     f"{'enough' if c['readable'] else 'TOO SHORT'})" for c in f["captions"]) or "- none"
    parts = ", ".join(f"{k} {v} s" for k, v in f["parts"].items())
    drags = "; ".join(f.get("drags") or []) or "not recorded"
    measured = measured_scores(f)
    extra = ""
    if edit_of:
        px = edit_of.get("pixels") or {}
        where = ""
        if px.get("layers"):
            where = (f" Measured: the changed pixels sit in the layer(s) {', '.join(px['layers'])}"
                     + (f" inside the box x {px['box'][0]}-{px['box'][2]}, y {px['box'][1]}-{px['box'][3]} of the 1080x1920 frame" if px.get("box") else "")
                     + f", {px.get('frames_changed', '?')} of {px.get('frames', '?')} frames; a small change (a texture, a colour) can be hard to see on this sheet, so judge its presence from this fact, not from the thumbnails.")
        extra = (f"\nTHIS IS AN EDIT of an approved version; the request names one change and everything else must "
                 f"stay. The edit report's verdict: {edit_of.get('verdict', '?')}{where}\n")
    return f"""{RUBRIC}

THE MARKETER'S REQUEST:
{prompt.strip()}
{extra}
WHAT THE TOOL SAYS IT DID (one row per control):
{rows}

MEASURED FACTS (final, do not re-estimate): the ad is {f['length_s']} s; parts: {parts}. The game first moves at {f['first_move_s']} s (first-second score {measured['first_second']}/5). Held screens (frozen opening, held result, end card) take {f['static_s']} s, {f['static_share']:.0%} of the ad (dead-time score {measured['dead_time']}/5).
THE GAME'S OWN RECORD OF THE DRAGS (final; a 1 fps sheet can miss a short drag): {drags}.
CAPTIONS AND THEIR TIME ON SCREEN:
{caps}
CHECKS THAT DID NOT PASS: {', '.join(c['check'] + ': ' + c['detail'] for c in f['checks']) or 'none'}
QA NOTES: {'; '.join(f['qa']) or 'none'}

THE PICTURE is a contact sheet of the finished ad: one frame per second, left to right, top to bottom, the second written under each frame. The game board is in the middle of the frame, the clock and level badge at the top, captions over the board, the end card with its button at the end.

Answer with JSON only, with exactly these keys: match (list of {{control, verdict, seen}}), viewer ({{pace, readability, clarity, cta}} integers 1-5), would_download, why, fixes (list of strings), suggested_edit (string)."""


def review(version: dict, prompt: str, studio_dir: Path, client=None, log=None, edit_of: dict | None = None) -> dict:
    """The viewer's review of a finished version, written to review.json in its folder."""
    t0 = time.time()
    vdir = studio_dir / version["id"] / f"v{version['n']}"
    f = facts(version, studio_dir)
    sheet = contact_sheet(studio_dir / version["video"], vdir / "review_sheet.png")
    if log:
        log(f"reviewing v{version['n']} as a viewer: {f['length_s']} s, game moves at {f['first_move_s']} s, "
            f"held screens {f['static_share']:.0%}...")
    if client is None:
        from . import llm
        client = llm.vision_client()
    import base64
    data = base64.b64encode(sheet.read_bytes()).decode()
    part = {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{data}"}}
    text = client.describe(question(prompt, version["brief"], f, edit_of), part, sheet)
    raw = _json_in(text)
    out = _complete(raw, f)
    out.update({"model": getattr(client, "last_model", None), "seconds": round(time.time() - t0, 1),
                "sheet": str(sheet.relative_to(studio_dir)), "facts": f})
    (vdir / "review.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    if log:
        log(f"review: {summary(out)}")
    return out


def _complete(raw: dict, f: dict) -> dict:
    """The model's answer made whole: measured scores added, verdicts normalised, an overall verdict."""
    viewer = {k: max(1, min(5, int(raw.get("viewer", {}).get(k, 3) or 3))) for k in ("pace", "readability", "clarity", "cta")}
    viewer.update(measured_scores(f))
    match = []
    for m in raw.get("match") or []:
        v = str(m.get("verdict", "")).lower().strip()
        if v not in ("match", "partial", "no", "not asked"):
            v = "partial"
        match.append({"control": str(m.get("control", ""))[:60], "verdict": v, "seen": str(m.get("seen", ""))[:400]})
    fixes = [str(x)[:300] for x in (raw.get("fixes") or [])][:3]
    would = str(raw.get("would_download", "maybe")).lower()
    would = would if would in ("yes", "maybe", "no") else "maybe"
    low = [k for k, s in viewer.items() if s <= 2]
    overall = "fix" if any(m["verdict"] == "no" for m in match) or low else "ship"
    return {"match": match, "viewer": viewer, "would_download": would, "why": str(raw.get("why", ""))[:500],
            "fixes": fixes, "suggested_edit": str(raw.get("suggested_edit", "") or "")[:600], "overall": overall,
            "low": low}


def summary(r: dict) -> str:
    v = r["viewer"]
    scores = ", ".join(f"{k.replace('_', ' ')} {v[k]}" for k in ("first_second", "dead_time", "pace", "readability", "clarity", "cta"))
    bad = [m for m in r["match"] if m["verdict"] in ("no", "partial")]
    return (f"{r['overall']}; would download: {r['would_download']}; {scores}"
            + (f"; not as asked: {', '.join(m['control'] for m in bad)}" if bad else ""))
