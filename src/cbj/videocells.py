"""A reference video's own board, read cell by cell from its first frame of play (2026-10-19).

The owner's creative of 2026-10-19 ("use same game design, same scenario just use fewer blocks" on the game's own
trailer) got a board of the trailer's TYPE: the video workflow took the shape, the size, the block count and the colours
(videoref._apply_board) and the generator built a new board, because a sampled video reading cannot place cells. The
image workflow can (imagecells): the board in a still is read cell by cell, verified against the pixels, solved and
played as read. So when the words ask for the video's board itself, the first frame of play is taken as a still and read
that way; the level is that board with the asked changes (fewer blocks, one more colour, a mirror...), as for a picture.
"same kind of level", "a board like this", "its energy" keep the type path (REQ4 rules, section 1).

Evidence: studio/_cells/<video stem>_t<seconds>.png (the frame) and the cell reading's files beside it."""
from __future__ import annotations

import re
import shutil
import subprocess
import time
from pathlib import Path

from . import imageplan as IP

# the words that mean THE board of the video: same/this/that/exact + a board noun, not followed by a part word ("same
# level number", "board shape") and not a comparison ("as this board", "like this level")
COPY = re.compile(r"\b(same|this|that|exact|exactly the|the exact|identical)\b(?P<gap>[^.;]{0,16}?)\b(game design|design|board|level|layout|puzzle|grid)\b"
                  r"(?![^.;]{0,3}\b(number|badge|label|count|size|shape|type|kind|colou?rs?|style|look)\b)", re.I)
NOT_COPY_GAP = re.compile(r"\b(kind|type|sort|style|size|shape|number|amount|count|colou?rs?|look|feel|idea|mood|energy|pace|pacing|flow|"
                          r"concept|scenario|story|difficulty)\b", re.I)
COMPARISON = re.compile(r"\b(like|as|than|resembl\w+|similar to)\s*$", re.I)
EXACT = re.compile(r"\b(exactly as shown|as shown|as it is|as is|cell (for|by) cell|one to one|1:1|the (very )?same board)\b", re.I)
# "take the board from this video" (a translation of V2 once read "...exactly, but mirror it": no "as it is", so the
# copy was missed and a board of the type was built, 2026-10-19 13:18): a copy verb on THE board of THIS video is a copy
BOARD_FROM = re.compile(r"\b(take|took|copy|copies|use|uses|rebuild|rebuilds|recreate|reuse|keep|keeps|lift)\b[^.;]{0,12}"
                        r"\bthe (board|level|layout|puzzle|grid)\s+(from|in|of|out of|shown in|seen in)\s+(this|that|the)\s+"
                        r"(video|clip|ad|trailer|reference|footage|creative)\b", re.I)
NOT_BOARD_FROM = re.compile(r"\b(inspir\w+|similar|like the|kind of|type of|sort of|in the spirit|based on the idea)\b", re.I)
FRAME_AFTER_S = 0.3  # into the first play part: the board before the first drag, the hand usually still off it


def copy_asked(prompt: str) -> bool:
    """Whether the words ask for the video's own board (copied), not a board of its type."""
    text = IP._words(prompt or "")
    if IP.NEW_BOARD.search(text):
        return False
    if EXACT.search(text):
        return True
    for m in BOARD_FROM.finditer(text):
        sentence = re.split(r"[.;]", text[:m.end()])[-1] + re.split(r"[.;]", text[m.end():])[0]
        if not NOT_BOARD_FROM.search(sentence):
            return True
    for m in COPY.finditer(text):
        if NOT_COPY_GAP.search(m.group("gap")):
            continue
        if COMPARISON.search(text[max(0, m.start() - 14):m.start()]):
            continue
        return True
    return False


def frame_time(a: dict) -> float:
    """When the board is whole: the start of the first play part the reading found, plus a little; 0.3 s when none."""
    from .reference import GAMEPLAY_PURPOSES
    notes = a.get("notes") if isinstance(a.get("notes"), dict) else {}
    dur = float(((a.get("facts") or {}).get("duration_s")) or 0) or None
    t = FRAME_AFTER_S
    for seg in notes.get("structure") or []:
        try:
            if str(seg.get("purpose")) in GAMEPLAY_PURPOSES:
                t = float(seg.get("from_s") or 0) + FRAME_AFTER_S
                break
        except (TypeError, ValueError):
            continue
    if dur:
        t = min(t, max(0.0, dur - 0.2))
    return round(max(0.0, t), 1)


def board_frame(video: Path, t: float, folder: Path | None = None) -> Path:
    """The frame at t seconds as a PNG in studio/_cells (full resolution; ffmpeg applies the display rotation)."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise ValueError("ffmpeg is not installed, so no frame can be taken from the video")
    folder = folder or (Path(__file__).resolve().parents[2] / "studio" / "_cells")
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / f"{Path(video).stem}_t{t:g}.png"
    r = subprocess.run([ffmpeg, "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1", str(out)],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0 or not out.is_file():
        raise ValueError(f"ffmpeg could not take the frame at {t} s ({(r.stderr or '').strip()[:120]})")
    return out


def read_board(video: Path, a: dict, log=None) -> dict:
    """The video's starting board read as a picture (imageread.read with the board as the focus, then imagecells):
    {frame, t, cells, board, seconds, model} or {..., error}. Never raises: the type path stands when this fails."""
    from . import imageread
    t0 = time.time()
    try:
        t = frame_time(a)
        frame = board_frame(Path(video), t)
        if log:
            log(f"the video's board: the frame at {t} s ({frame.name}) read cell by cell, as a picture...")
        plan = {"focus": ["board"], "level": "full", "source": "video", "why": "the request asks for the video's own board",
                "questions": [], "ignore": [], "constraints": []}
        reading = imageread.read(frame, client=None, log=log, plan=plan)
        cells = reading.get("cells") or {}
        notes = reading.get("notes") if isinstance(reading.get("notes"), dict) else {}
        out = {"frame": str(frame), "t": t, "cells": cells, "board": reading.get("board"), "model": reading.get("model"),
               "cbj": bool(notes.get("is_color_block_jam")),
               "reader": reading.get("reader"), "seconds": round(time.time() - t0, 1)}
        if reading.get("error"):
            out["error"] = reading["error"]
        elif not cells:
            out["error"] = "the frame was read, but no board was read cell by cell (no Color Block Jam board with a size and a box)"
        elif cells.get("error"):
            out["error"] = cells["error"]
        if log:
            lvl = cells.get("level") or {}
            log("the video's board: " + (f"could not be copied ({out['error'][:160]})" if out.get("error") else
                                        f"{len(lvl.get('GridBlockDatas') or [])} blocks, {len(lvl.get('ExitDatas') or [])} gates read in {out['seconds']} s"))
        return out
    except Exception as e:
        return {"error": str(e)[:300], "seconds": round(time.time() - t0, 1)}
