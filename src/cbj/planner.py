"""The planner: a natural-language prompt in, a creative brief out.

An LLM fills the brief's JSON schema (brief.SCHEMA) and nothing else. It never makes levels,
moves or pixels: the deterministic engine does, from the brief, so the gameplay is real and an
edit can be proven. The brief is then checked in code (brief.check), and an edit is merged so
that only what the prompt asked to change is taken (brief.merge).

The model runs on NVIDIA's hosted API (NVIDIA_API_KEY, from the environment or a .env file in
the repo). Tests use a fake client.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import brief as B

REPO = Path(__file__).resolve().parents[2]
NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
MODELS = ("nvidia/nemotron-3-ultra-550b-a55b", "nvidia/nemotron-3-super-120b-a12b")
# Reasoning is off: with it, a brief took 30-180 s; without, 5-18 s, and still schema-valid.
TIMEOUT_S = 120

SYSTEM = """You turn a request for a Color Block Jam video ad into a creative brief: JSON that follows the given schema exactly.

THE GAME. Color Block Jam is a puzzle game. Coloured blocks (polyomino shapes) sit on a grid; the player drags each block out through a gate of its own colour on the board's edge. Blocks get in each other's way, so some must be moved aside first. A level has a countdown clock. The HUD shows "Level N" and the time.

THE TOOL. It records the REAL game playing a level (real, solvable moves; a scripted finger that looks human), then adds a hook, captions, a tap cursor, sound effects, a slow-motion replay, the game's own result screen and an end card with a "PLAY NOW" button. You decide WHAT to make; the engine makes it. Only fill a field from what the request says; leave the default when it says nothing.

channel: "network" (ad networks; default) or "social" (TikTok, Instagram, Facebook feeds). language: "en" unless the request asks for another language (e.g. "tr", "de"); then write EVERY text in concept in that language. format: "9:16" unless the request asks for another aspect ratio.

level (control "level"; difficulty belongs to control "difficulty_pacing"):
- source: "auto" (the tool's showcase: a hand-checked HARD 6x8 narrow-centre level), "shipped" (the game's own levels 1-6: small tutorial levels, ALL EASY), or "generate" (a new level built to the spec below). Use "generate" whenever the request describes a structure, shape, size, block count, colours or difficulty.
- shape: "narrow_center" (a narrow middle / centre / waist / bottleneck: an hourglass), "door" (two rooms joined by a narrow gap), "holes" (holes or pillars inside the board), "cross" (a plus-shaped board, the corners cut away), "ring" (a big hole in the middle; the blocks go round it), "lanes" (walled lanes joined along the bottom, like parking lanes), "open" (a plain rectangle), or "any".
- pieces: the blocks' shapes: "mixed" (default), "small" (1-2 cells), "big" (chunky 4-6 cell blocks), "long" (bars of 3-4 cells).
- style: how the board looks, any of: "symmetric" (a mirror-image board), "packed" (crowded like a real jam level: most cells hold blocks, one gate per colour), "colourful" (every colour, no two touching blocks the same colour). [] unless the request asks about the board's look; for "a visually interesting / eye-catching / pretty board" use ["symmetric", "colourful"].
- width 4-9, height 4-10, blocks 2-10: ONLY if the request gives them (numbers, or words like "big board"); otherwise null and the tool sizes the level to the ad.
- colours: the game colour SLOTS the level uses: Green, Yellow, Blue, Red, Orange, Purple, DarkGreen ([] = any). Only when the request limits the board's colours ("only blue, red and yellow"); a colour named just to point at a block ("the red block gets stuck") goes into the event, not here. If the request names colours the game does not have (pink, teal...), pick the nearest slots here AND repaint them in visuals.blocks.
- difficulty: "easy", "medium", "hard" or "any".
- label: the number in the HUD's Level badge ("level 47" -> 47), else null.

gameplay (control "gameplay"):
- ending: "win" (a clean, satisfying solve), "near_fail" (a mistake, a stuck moment, then solved with 00:01 left on the clock), "cliffhanger" (the video stops with two blocks left in each other's way and asks "Can you see the move?"), "time_out" (the clock runs out one move short: ONLY when the request explicitly asks for a fail or losing ending). If the request says nothing about gameplay, use "near_fail".
- mistakes: believable wrong moves, 0-3 (null = the ending's default). mistake_kinds: any of "blocked" (drags a block toward its gate and another block stops it), "wrong_way" (moves a block somewhere unhelpful), "fidget" (a pointless nudge); [] = the tool chooses. hesitations: picking a block up and putting it back, 0-3 (null = default).
- timer_s: seconds on the clock at the start, only if the request gives it. seed: null unless the request asks for a different take of the same ad (then any new integer).
- events: the ORDER of interactions the request asks for, as steps in order (other moves may come between them). [] unless the request says what particular blocks do or in what order. Each step: block {colour: a game colour or null, which: "any" | "biggest" | "smallest" | "longest", all: true for "all the <colour> blocks"}, action: "leaves" (exits through its gate) | "moves" (moved out of the way) | "stuck" (dragged toward its gate and stopped by another block: a mistake) | "hesitates" (picked up and put back), when: "first" (the very first move of the video; only the first step) | "next" | "last" (the last block to leave; only the final "leaves" step). Examples: "first move the yellow block out of the way, then the blue one escapes" -> [{yellow, moves, first}, {blue, leaves, next}]; "clear it colour by colour: blue, then red" -> [{blue, all, leaves}, {red, all, leaves}] (with no colours named, pick three and put them in level.colours too); "the biggest block leaves last" -> [{null, biggest, leaves, last}]; "the red block gets stuck first" -> [{red, stuck, first}] (a stuck step is one of the mistakes). "then the rest" or "then everything else" needs no step: the board is cleared at the end anyway.
- finish: "streak" for a satisfying solve: one key move, then every block leaves one after another ("one move frees everything", "they all fly out", a chain, a cascade); else "auto".
- clock_left_s: for a near_fail only, the seconds on the clock when the last block leaves, 1-3, only if the request gives it ("with 2 seconds left" -> 2); else null.

pacing (control "difficulty_pacing"): length_s 15-60 (default 30); tempo "calm", "normal" or "fast" (the pauses between moves); curve "even" (default), "speeds_up" (starts slow and careful, ends fast: tension building), "slows_down".

CONCEPT TO GAMEPLAY. When the request names a mood or concept but not the settings, use these, and say in assumptions which words you read that way:
- relaxing, calm, ASMR, oddly satisfying: ending win, difficulty easy, finish streak, tempo calm.
- a satisfying solve: ending win, finish streak.
- rage, frustrating, "almost impossible": difficulty hard, ending near_fail, mistakes 2.
- speedrun, pro player, fast: ending win, tempo fast, finish streak, mistakes 0.
- "can you solve it?", "what's the move?", a puzzle challenge: ending cliffhanger.
- tension building, against the clock: ending near_fail, curve speeds_up.
- for beginners or kids: difficulty easy, ending win, tempo calm.
Things the game cannot do go into the gameplay or level row as "not_supported" with the reason: two blocks leaving at the same moment (one drag moves one block), choosing which gate side a block leaves through, regions of the board ("clear the left half first"), more than one level in one ad (one level per ad in this version).

visuals (control "visuals"):
- theme: "game" (the game's own look), "candy", "pastel", "neon", "dark", or "custom" (only the colours given below).
- blocks: repaint colour slots: [{"slot": "Red", "hex": "#FF69B4", "name": "pink"}]. name is how captions call that colour. Only slots the request wants repainted.
- background: 0, 1 or 2 colours "#RRGGBB" (top and bottom of a gradient). board: the board's cell colour "#RRGGBB" or null.
- caption_fill, caption_outline: "#RRGGBB" or null (the game's white text with a purple outline).
- camera_zoom: 1.0-1.12 to frame the board a little closer (more crops the side gates), or null. cursor: "ring" (a tap ring, default), "hand" (a pointing hand), "none".
- hud_timer, hud_level: false to hide the HUD's clock or level badge (default true).

concept (control "concept"): angle = the idea in one line. Texts: hook (first frame), mistake (caption on the mistake), fix (on the move that fixes it), hurry (the last 5 seconds), cascade (the fast finish of a win), result (on the result screen), end_title, end_fact, cta (the button). LEAVE EVERY TEXT null UNLESS the request asks for specific copy, a tone, an angle or a language: the defaults are written for each ending and use measured facts. "" removes that caption (not the cta). Keep captions under 6 words. Texts may use facts measured from the recording, in braces: {clock_left} (e.g. 00:01), {time_used} (seconds used), {colour} (the colour of the block in the mistake or the fix), {blocks_left_phrase} (e.g. "two blocks"), {blocks_left}, {timer}, {blocks}. Any number about the play must be one of these facts. NEVER write statistics, odds, percentages, rankings or IQ claims ("only 1% can solve this" is forbidden by ad rules); dares are fine ("Can you beat it?"). If the request asks for such a claim, write the closest honest dare and set the concept row to "adjusted" with the reason.

sequence (control "sequence"): style "standard" (hook over the gameplay, then replay, result, end card) or "result_first" (the result for 1.5 s at the very start, then how it happened); replay (a slow-motion replay of the last moves); result_screen (the game's own "Level Completed" / "Out of Time!" screen); end_card (always true: the end card holds the button).

assets (control "assets"): an uploaded file may ONLY be used if the request refers to it (by name, or as "our logo", "this image", "the attached ..."). Otherwise leave it out and say so in the assets row's plan. The game's own sprites can also be used: CoinPile.png, stopwatch.png. role: "logo" (small, in a top corner for the whole ad), "mascot" or "sticker" (a picture beside the hook, or on the end card), "cursor" (replaces the tap ring), "end_art" (the picture on the end card), "end_background" (the end card's background). when: "whole", "hook", "end_card". where: "auto", "top_left", "top_right", "beside_hook", "end_card". Never invent a file name.

audio (control "assets"): sfx false only if the request asks for no sound. There is no music or voice-over.

keep (control "unchanged"): what must stay exactly as it is: level, gameplay, timing, camera, visuals, copy, sequence, assets, sound.

controls: exactly 8 rows, one per control, in this order: level, gameplay, difficulty_pacing, visuals, concept, sequence, assets, unchanged.
- asked: an exact excerpt of the USER'S REQUEST about this control, or null if the request says nothing about it (never quote this instruction text or the file list).
- plan: what the tool will do, in plain words.
- status: "applied" (asked and done), "default" (not asked), "adjusted" (asked, but changed to something the game can do), "not_supported" (asked, but impossible here).
- why: the reason for "adjusted" or "not_supported", else null.
Anything the request asks for that no field can express (for example 3D characters, a different game mechanic, voice-over, music, real people, another game) goes into the closest row as "not_supported" with a short reason. Never ignore part of the request.

assumptions: what you had to guess because the request was ambiguous, each with the alternative (e.g. "'this object' read as the cursor; could also mean the end-card picture"). [] if nothing was guessed.

summary: one sentence describing the ad that will be made.

changed: the field groups the REQUEST asks to set or change, and nothing else. Groups: level.source, level.shape, level.size, level.blocks, level.colours, level.label, level.difficulty, level.pieces, level.style, gameplay.ending, gameplay.mistakes, gameplay.hesitations, gameplay.retake, gameplay.clock, gameplay.events, gameplay.finish, gameplay.clock_left, pacing.length, pacing.tempo, pacing.curve, channel, visuals.colours, visuals.background, visuals.board, visuals.captions, visuals.zoom, visuals.cursor, visuals.hud, format, language, concept.hook, concept.mistake, concept.fix, concept.hurry, concept.cascade, concept.result, concept.end_title, concept.end_fact, concept.cta, sequence, assets, audio. (What to keep goes in "keep", not here.) Only fields in these groups are used; everything else keeps the tool's default (or, for an edit, its current value). So: "no sound" -> audio; "use a hand" -> visuals.cursor; "make the hook say X" -> concept.hook only; "a difficult level" -> level.difficulty."""

EDIT = """This is an EDIT of an existing ad. The current brief is below. Return the complete brief with ONLY the changes the edit request asks for; copy every other field exactly. Mark "asked" only for the controls the edit request talks about (others: asked null, status "default", but keep their plan text). If the request says to keep something, list it in keep. If the request says "keep everything else" or similar, list everything except what it changes.

CURRENT BRIEF:
"""


def load_env(path: Path = REPO / ".env") -> None:
    if path.is_file():
        for line in path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class NvidiaClient:
    """Chat completions with a JSON schema, on NVIDIA's hosted API, trying the models in order."""

    def __init__(self, models=MODELS, key: str | None = None):
        load_env()
        self.key = key or os.environ.get("NVIDIA_API_KEY")
        if not self.key:
            raise ValueError("no NVIDIA_API_KEY: set it in the environment or in cbj-creative/.env")
        self.models = models
        self.last_model = None

    def complete(self, system: str, user: str, schema: dict) -> str:
        errors = []
        for model in self.models:
            body = {"model": model, "temperature": 0, "max_tokens": 6000,
                    "chat_template_kwargs": {"enable_thinking": False},
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                    "response_format": {"type": "json_schema",
                                        "json_schema": {"name": "brief", "schema": schema, "strict": True}}}
            req = urllib.request.Request(NVIDIA_URL, data=json.dumps(body).encode(),
                                         headers={"Authorization": f"Bearer {self.key}",
                                                  "Content-Type": "application/json"})
            for attempt in range(2):
                try:
                    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
                        out = json.load(r)
                    self.last_model = model
                    return out["choices"][0]["message"].get("content") or ""
                except urllib.error.HTTPError as e:
                    errors.append(f"{model}: HTTP {e.code} {e.read()[:200]!r}")
                    if e.code not in (429, 500, 502, 503, 504):
                        break
                except (urllib.error.URLError, TimeoutError) as e:
                    errors.append(f"{model}: {e}")
                time.sleep(2 * (attempt + 1))
        raise ValueError("the planner could not reach a model: " + "; ".join(errors[-3:]))


def _ask(client, system: str, user: str) -> dict:
    text = client.complete(system, user, B.SCHEMA)
    try:
        return json.loads(text, strict=False)  # strict=False: models sometimes put raw newlines in strings
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1], strict=False)
        raise ValueError(f"the planner did not return JSON: {text[:200]!r}")


UPLOAD_WORDS = ("logo", "attach", "upload", "image", "picture", "photo", "png", "jpg", "asset", "mascot",
                "sticker", "icon", "artwork", "graphic")


def _only_mentioned_uploads(raw: dict, prompt: str, uploads: dict, current: dict | None) -> None:
    """An uploaded file is used only if the prompt refers to it (its name, or words like "our
    logo", "the attached image"), or the version being edited already uses it. Otherwise it is
    left out, and the assets row says why."""
    text = prompt.lower()
    mentioned = any(re.search(rf"\b{w}", text) for w in UPLOAD_WORDS)
    used = {a["file"] for a in (current or {}).get("assets", [])}
    keep = []
    for a in raw.get("assets", []):
        f = a.get("file", "")
        if f in uploads and f not in used and not (Path(f).stem.lower() in text or mentioned):
            row = B.control(raw, "assets")
            row["why"] = (row.get("why") or "") + f" {f} was uploaded but the prompt does not say how to use it, so it is left out."
            continue
        keep.append(a)
    raw["assets"] = keep


TRANSLATE = """Translate these short ad captions for the puzzle game Color Block Jam into the language with code "{lang}". Keep each one short and punchy. Keep anything in braces exactly as it is (for example {{clock_left}} or {{colour}}): those are filled in later. Do not add claims, numbers or statistics. Return JSON with the same keys."""


def _translate_defaults(brief: dict, client) -> None:
    """A non-English ad must not mix languages: the default captions the prompt did not write are
    translated by the model (and checked like any text)."""
    from .ad import END_FACTS, HOOKS
    ending = brief["gameplay"]["ending"]
    defaults = {"hook": HOOKS[ending], "mistake": "I can't reach {colour}!", "fix": "Aha! Move {colour} first",
                "hurry": "Hurry!", "cascade": "So satisfying!", "end_fact": END_FACTS[ending], "cta": "PLAY NOW",
                "result": {"near_fail": "Phew! {clock_left} left", "time_out": "So close!",
                           "cliffhanger": "Can you see the move?"}.get(ending)}
    todo = {k: v for k, v in defaults.items() if v and brief["concept"].get(k) is None}
    fresh = {**brief, "visuals": {**brief["visuals"], "names": {}}}  # names in English, before any translation
    english = {slot: v["name"] for slot, v in B.display_colours(fresh).items()}  # for the {colour} fact
    old, src = brief["visuals"].get("names") or {}, brief["visuals"].get("names_src") or {}
    # an edit keeps the earlier translation of a colour whose English name did not change, so
    # captions it does not touch stay the same
    brief["visuals"]["names"] = {s: n for s, n in old.items() if src.get(s) == english.get(s)}
    brief["visuals"]["names_src"] = {s: english[s] for s in brief["visuals"]["names"]}
    names = {f"colour_{slot}": name for slot, name in english.items() if slot not in brief["visuals"]["names"]}
    todo.update(names)
    if not todo:
        return
    schema = {"type": "object", "properties": {k: {"type": "string"} for k in todo}, "required": list(todo),
              "additionalProperties": False}
    try:
        out = json.loads(client.complete(TRANSLATE.format(lang=brief["language"]), json.dumps(todo), schema),
                         strict=False)
    except Exception as e:  # the ad still works in English; say so
        B.adjust(brief, "concept", f"the default captions could not be translated ({e}); they stay in English.")
        return
    for k, v in out.items():
        if not (k in todo and isinstance(v, str) and v.strip()):
            continue
        if k.startswith("colour_"):
            slot = k[len("colour_"):]
            brief["visuals"]["names"][slot] = v.strip().lower()
            brief["visuals"]["names_src"][slot] = english[slot]
        elif not B._texts_ok(v):
            brief["concept"][k] = v.strip()
    row = B.control(brief, "concept")
    if row.get("why") and "english" in row["why"].lower():
        row["why"] = None  # the model's own "stays in English" no longer holds
        if row["status"] == "adjusted":
            row["status"] = "applied"
    left = [k for k in todo if not k.startswith("colour_") and brief["concept"].get(k) is None]
    if left:
        B.adjust(brief, "concept", f"no {brief['language']} text could be made for {', '.join(left)}; those stay "
                                   f"in English.")


def plan(prompt: str, client=None, uploads: dict[str, Path] | None = None, sprites: set[str] | None = None,
         current: dict | None = None, available: dict[str, Path] | None = None) -> dict:
    """A checked brief for a prompt. With `current`, the prompt edits that brief: only what the
    prompt asks to change may change. uploads: the files attached to this prompt (offered to
    the model); available: every uploaded file (an edit keeps the ones its version uses).
    Returns the brief, with `planner` notes."""
    client = client or NvidiaClient()
    files = sorted(uploads or {})
    available = {**(available or {}), **(uploads or {})}
    user = f"REQUEST:\n{prompt.strip()}\n\nUPLOADED FILES: {', '.join(files) if files else 'none'}"
    system = SYSTEM
    if current is not None:
        # the fields only: the previous version's reasons and notes would leak into the edit
        shown = {k: v for k, v in current.items() if k not in ("planner", "controls", "assumptions", "summary")}
        user = EDIT + json.dumps(shown, indent=1) + "\n\nEDIT " + user
    t0 = time.time()
    raw = _ask(client, system, user)
    _only_mentioned_uploads(raw, prompt, available, current)
    # Only what the prompt asks to change is taken; everything else keeps its default (a new ad)
    # or its current value (an edit). The model may not fill unasked fields, such as copy.
    base = current if current is not None else B.check(B.default_brief())
    brief, restored = B.merge(base, B.check(raw, available, sprites), prompt)
    brief = B.check(brief, available, sprites)
    if brief["language"] != "en":
        _translate_defaults(brief, client)
    else:
        brief["visuals"]["names"], brief["visuals"]["names_src"] = {}, {}
    brief["planner"] = {"model": getattr(client, "last_model", None), "seconds": round(time.time() - t0, 1),
                        "prompt": prompt.strip(), "edit": current is not None, "restored": restored}
    return brief
