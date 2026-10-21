"""The planner: a natural-language prompt in, a creative brief out.

An LLM fills the brief's JSON schema (brief.SCHEMA) and nothing else. It never makes levels,
moves or pixels: the deterministic engine does, from the brief, so the gameplay is real and an
edit can be proven. The brief is then checked in code (brief.check), and an edit is merged so
that only what the prompt asked to change is taken (brief.merge).

The model runs on NVIDIA's hosted API by default (NVIDIA_API_KEY, from the environment or a .env file in
the repo). Tests use a fake client.
"""

from __future__ import annotations

import copy
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
- pieces: the blocks' shapes: "mixed" (default), "small" (1-2 cells), "big" (chunky 4-6 cell blocks), "long" (bars of 3-4 cells), "varied" (a request for several kinds together, such as small, long and L-shaped blocks: all three are then on the board).
- style: how the board looks, any of: "symmetric" (a mirror-image board), "packed" (crowded like a real jam level: most cells hold blocks, one gate per colour; also "compact board", "limited empty space", "little room to move"), "colourful" (every colour, no two touching blocks the same colour), "spacious" (room to move: few blocks, no two blocks touching, most cells empty; for "plenty of / enough free space", "room to move", "not crowded", "a simple open board for beginners"). [] unless the request asks about the board's look; for "a visually interesting / eye-catching / pretty board" use ["symmetric", "colourful"]. Never packed and spacious together.
- width 4-9, height 4-10, blocks 2-10: ONLY if the request gives them (numbers, or words like "big board": "small board" -> 6x6, "medium-sized board" -> 7x7, "big / large board" -> 8x9); otherwise null and the tool sizes the level to the ad.
- colours: the game colour SLOTS the level uses: Green, Yellow, Blue, Red, Orange, Purple, DarkGreen ([] = any). Only when the request limits the board's colours ("only blue, red and yellow"); a colour named just to point at a block ("the red block gets stuck") goes into the event, not here. If the request names colours the game does not have (pink, teal...), pick the nearest slots here AND repaint them in visuals.blocks.
- difficulty: "easy", "medium", "hard" or "any".
- label: the number in the HUD's Level badge ("level 47" -> 47), else null.
- moves: how many drags the shortest solution takes, 4-16, ONLY when the request gives a number of moves ("solved in 10 to 15 moves" -> 12); else null (the tool sizes the level to the ad's length). Repositioning drags count as moves.
- changes: ONLY in an EDIT, and only for what the request asks to do to the CURRENT board: {"op": "move_gate", "colour": the door's colour, "side": "top"/"bottom"/"left"/"right"/"opposite", "column"/"row": only if given}; {"op": "add_wall", "colour": the block whose route it should block (or null), "column"/"row": the tile if named (1-based from the bottom-left), else null}; {"op": "remove_wall", "column"/"row": if named, else null (the tool picks the wall)}. Walls are the game's holes (its only obstacles). Everything else on the board stays; the tool keeps every move that is still legal and re-plans only the rest. For a NEW ad, and when nothing on the board is moved, added or removed, []. Never use changes for "harder"/"easier" alone (that is difficulty).

gameplay (control "gameplay"):
- ending: "win" (a clean, satisfying solve), "near_fail" (a mistake, a stuck moment, then solved with 00:01 left on the clock), "cliffhanger" (the video stops with two blocks left in each other's way and asks "Can you see the move?"), "time_out" (the clock runs out one move short: ONLY when the request explicitly asks for a fail or losing ending). If the request says nothing about gameplay, use "near_fail".
- mistakes: believable wrong moves, 0-3 (null = the ending's default). mistake_kinds: any of "blocked" (drags a block toward its gate and another block stops it), "wrong_way" (moves a block somewhere unhelpful), "fidget" (a pointless nudge); [] = the tool chooses. hesitations: picking a block up and putting it back, 0-3 (null = default).
- timer_s: seconds on the clock at the start, only if the request gives it. seed: null unless the request asks for a different take of the same ad (then any new integer). "Harder" or "easier" is about the level (level.difficulty), never a new take: the tool edits the board itself.
- events: the ORDER of interactions the request asks for, as steps in order (other moves may come between them). [] unless the request says what particular blocks do or in what order. Each step: block {colour: a game colour or null, which: "any" | "biggest" | "smallest" | "longest", all: true for "all the <colour> blocks"}, action: "leaves" (exits through its gate) | "moves" (moved out of the way) | "stuck" (dragged toward its gate and stopped by another block: a mistake) | "blocks" (moved into a spot where it gets in another block's way: a wrong move the player then undoes; by: the colour of the block it then blocks, when named) | "hesitates" (picked up and put back), when: "first" (the very first move of the video; only the first step) | "next" | "last" (the last block to leave; only the final "leaves" step). Examples: "first move the yellow block out of the way, then the blue one escapes" -> [{yellow, moves, first}, {blue, leaves, next}]; "clear it colour by colour: blue, then red" -> [{blue, all, leaves}, {red, all, leaves}]; "all the red blocks leave first, then all the blue blocks, with the yellow and green blocks cleared at the end" -> FOUR steps, one per colour named, in that order: [{red, all, leaves, next}, {blue, all, leaves, next}, {yellow, all, leaves, next}, {green, all, leaves, last}] (a colour order names EVERY colour it mentions, the ones "at the end" too; leaving them out lets them leave first) (with no colours named, pick three and put them in level.colours too); "the biggest block leaves last" -> [{null, biggest, leaves, last}]; "the red block gets stuck first" -> [{red, stuck, first}] (a stuck step is one of the mistakes); "an obvious early move sends the yellow block into a position that blocks the green block's route" -> [{yellow, blocks, first, by: green}]; "moving a blue block into an unhelpful empty space, which temporarily prevents another block from reaching its exit" -> [{blue, blocks, next, by: null}] (a blocks step is one of the mistakes); by: for a stuck step, the colour of the block that stops it when the request says so ("blue stops because a red block blocks the route" -> {blue, stuck, first, by: red}), else null; "the blue block exits before the yellow one" -> [{blue, leaves, next}, {yellow, leaves, next}] (an order between blocks, not the video's first move). "then the rest" or "then everything else" needs no step: the board is cleared at the end anyway.
- finish: "streak" for a satisfying solve: one key move, then every block leaves one after another ("one move frees everything", "they all fly out", a chain, a cascade); else "auto".
- blocks_left: for a cliffhanger only, how many blocks are still on the board at the cut, 1-3 (1 = "one move from the win", "leaving one block and its door on screen"); null = the tool's own (2: one block pushed into its blocker).
- clock_left_s: for a near_fail only, the seconds on the clock when the last block leaves, 1-3, only if the request gives it ("with 2 seconds left" -> 2); else null.

pacing (control "difficulty_pacing"): length_s 30-60 (default 30; the ads are 30-60 s, shorter requests are raised to 30); tempo "calm", "normal" or "fast" (the pauses between moves); curve "even" (default), "speeds_up" (starts slow and careful, ends fast: tension building), "slows_down".

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
- background: 0, 1 or 2 colours "#RRGGBB" (top and bottom of a gradient): the area behind and around the board during the gameplay (the game's own is a soft gradient from #FFFFFF at the top to #DCE7FF at the bottom; "brighter", "warmer" etc. start from those). background_image: an attached picture shown behind the board during the gameplay instead of the gradient (its file name), or null. board: the board's own cells "#RRGGBB" or null; "the background behind the board" is NEVER the board. The end card's background is a different thing: assets role "end_background".
- caption_fill, caption_outline: "#RRGGBB" or null (the game's white text with a purple outline): every caption.
- caption_colours: one caption's own text colour, [{"caption": "hook"/"mistake"/.../"cta", "fill": "#RRGGBB"}], when the request colours only that caption ("make the opening caption yellow" -> [{"caption": "hook", "fill": "#FFE600"}]); [] otherwise. Group visuals.captions.
- camera_zoom: 1.0-1.12 to frame the board a little closer for the WHOLE ad (more crops the side gates), or null.
- punch_ins: a camera move for a stretch of time only: [{"from_s", "to_s" (seconds of the ad), "zoom" (1.08 = 8% closer, at most 1.25), "toward": the colour of the block it moves toward, or null}]; it eases in and back out inside the window, and never crops the HUD or the board. Group visuals.punch_in. [] otherwise.
- cursor: "ring" (a tap ring, default), "hand" (a pointing hand), "none".
- hud_timer, hud_level: false to hide the HUD's clock or level badge (default true).

concept (control "concept"): angle = the idea in one line. Texts: hook (first frame), mistake (caption on the mistake), fix (on the move that fixes it), hurry (the last 5 seconds), cascade (the fast finish of a win), result (on the result screen), end_title, end_fact, cta (the button). LEAVE EVERY TEXT null UNLESS the request asks for specific copy, a tone, an angle or a language: the defaults are written for each ending and use measured facts. "" removes that caption (not the cta). Keep captions under 6 words. Texts may use facts measured from the recording, in braces: {clock_left} (e.g. 00:01), {time_used} (seconds used), {time_used_phrase} (e.g. "12 seconds"), {colour} (the colour of the block in the mistake or the fix), {blocks_left_phrase} (e.g. "two blocks"), {blocks_left}, {timer}, {blocks}. Any number about the play must be one of these facts. NEVER write statistics, odds, percentages, rankings or IQ claims ("only 1% can solve this" is forbidden by ad rules); dares are fine ("Can you beat it?"). If the request asks for such a claim, write the closest honest dare and set the concept row to "adjusted" with the reason.

sequence (control "sequence"): style "standard" (hook over the gameplay, then replay, result, end card) or "result_first" (the WIN shown for 1.5 s at the very start, then how it happened: only when the request asks to show the result or ending first; a "still / static / frozen opening frame" is NOT this, it is intro_s); replay (a slow-motion replay of the last moves); result_screen (the game's own "Level Completed" / "Out of Time!" screen); end_card (always true: the end card holds the button).
- intro_s: how long the still opening frame (the hook over the frozen first frame, before the first move) lasts, 0-6 s; null = the tool decides. hold_s: how long the finished board / result stays held after the result screen, before the end card, 0-9 s; null = the tool decides. In an EDIT, the ad's parts and their lengths are listed under THINGS IN THIS AD ("intro", "result_hold"): "one second less of opening" -> intro_s = that length minus 1; "extend the victory hold by two seconds" -> hold_s = that length plus 2 (an ad with no "result_hold" part holds it 0 s; the game's "result" screen is not the hold). These change the ad's length by the same time; leave pacing.length as it is. Group sequence.timing.
- caption_times: a caption's entrance or exit moved, [{"caption": "hook"/..., "start_s": seconds later (+) or earlier (-) it appears, "end_s": the same for when it goes}] ("the headline appears one second later, same exit" -> [{"caption": "hook", "start_s": 1, "end_s": 0}]). Group sequence.caption_times. [] otherwise.

assets (control "assets"): role "skin" = an attached texture or picture drawn on ONE block of a colour ("apply this ice texture to the blue block": role skin, block "Blue"; the compositor draws it on that block on every gameplay frame; the block itself, its shape and its moves stay); "block" is that colour, null for every other role. An uploaded file may ONLY be used if the request refers to it (by name, or as "our logo", "this image", "this asset", "the attached ..."). Otherwise leave it out and say so in the assets row's plan. The game's own pictures can also be used by file name: CoinPile.png, stopwatch.png, StartBACKGROUND.png (the game's blue toy-brick background: as visuals.background_image behind the board, or as the end card's background), ContinueButtonEmpty.png (the game's green button), LevelCompleted.png and OutOfTimeText.png (the game's banner art), MainBarCircle.png and RestartButton.png (icons). role: "logo" (small, in a top corner for the whole ad: a brand mark, or the first sticker asked for a top corner), "mascot" or "sticker" (a picture beside the hook, on the end card, or in a top corner: a sticker with where "top_right" is the second corner picture, so two stickers can fill the two top corners), "cursor" (replaces the tap ring), "end_art" (the picture on the end card), "end_background" (the end card's background), "button" (replaces the PLAY NOW button's image; its text stays), "obstacle" (the picture is drawn on the board's walls, the game's only obstacles, during the play: "use this object instead of the current obstacle", "put this on the walls"; on a board without walls the tool puts it beside the hook and says so). when: "whole", "hook", "end_card". where: "auto", "top_left", "top_right", "beside_hook", "end_card". To REMOVE a picture (the logo, the icon beside the hook, the end-card picture), give it file "builtin:none" in its role. Never invent a file name. In an EDIT, the request may point at something in the ad ("this object", "the coin pile", "the clock icon", "the button"): the list THINGS IN THIS AD NOW says what each picture is; replace exactly that slot (its role and when), keep every other asset as it is, and if the request does not say which thing, pick the most likely one and write the assumption with the alternative.

audio (control "assets"): sfx false only if the request asks for no sound effects (or no sound at all). music: the file name of an attached sound file (.wav, .mp3, .m4a, .aac, .ogg, .flac) the request uses as music, a track or a song; null = no music (remove it only if asked; "no sound at all" also means no music). Never put a sound file in assets. There is no voice-over. In an edit, "undo"/"revert" a change means the value it had before that change (EARLIER VERSIONS says what each edit changed).

WHAT THE GAME DOES NOT HAVE. Color Block Jam has no obstacles, enemies, power-ups, boosters, characters or items on the board: only blocks, gates, walls and holes. A request about "the obstacle", "the enemy", "the character" can only mean the board's holes or walls (level.shape "holes") or, in an edit, one of the pictures listed under THINGS IN THIS AD NOW. A picture "instead of the obstacle" or "on the obstacle" is an asset with role "obstacle" (drawn on the walls). Say in assumptions what you took it to mean, and when the game has nothing of the kind, say so plainly ("the game has no obstacles; the object goes beside the hook instead").

A NEW ad has no earlier version. If the request refers to "the last one", "the previous ad" or "like before" and this is not an EDIT, say in assumptions that nothing earlier is available and plan from the request alone. Never claim a previous configuration exists.

REFERENCE FILES. When the message lists REFERENCE FILES, they were analysed before you: a measured palette and a multimodal model's notes. Use them: for "inspired by", "match", "same style", set visuals.theme "custom" and fill visuals.blocks (the game's slots repainted with the reference's colours, named) and visuals.background from the measured palette; take the mood, hook and idea into concept; for a video, take its structure (ending, pacing, mistakes, captions' tone) into gameplay and pacing, and WRITE the hook, the end card's title and the result caption in the reference's spirit (its idea, its hook's tone), declaring those concept groups: a reference's concept is a request for copy in that spirit. Keep the game's own pictures (the stopwatch, the coin pile) unless the request says otherwise: do not list them in assets. A reference video is NEVER an asset. A reference image is placed in the ad only when the request says to put, insert or replace with it. Name the file in the rows it influenced. If a file COULD NOT BE ANALYSED, do not guess what it shows: say so in assumptions and in the visuals row (status "adjusted"). A video is always read in full; its notes say what is applied ("applied: the hook and the pacing (targeted)"): take only that from it; the code then sets those fields from the reading, and the request's own values always win over the reference's. A video read for the board (its notes have a "board") gives the level's type in code (shape, size, blocks, colours, pieces) when the request says nothing about the level: do not set level fields from it yourself, and never add another game's obstacles (bubbles, ice, locks, boosters): they are not used.

WRITE FOR A MARKETING PERSON. plan, why, summary and assumptions are read by someone who does not know this tool: plain words only. Never write field names, roles, enum values, hex codes, file paths or JSON ("end_art", "near_fail", "level.shape", "#FF69B4"). Say "the picture on the end card", "the icon beside the hook", "the logo", "the caption on the mistake", "the clock", "the board", "a near-fail", "pink".

keep (control "unchanged"): what must stay exactly as it is: level, gameplay, timing, camera, visuals, copy, sequence, assets, sound.

controls: exactly 8 rows, one per control, in this order: level, gameplay, difficulty_pacing, visuals, concept, sequence, assets, unchanged.
- asked: an exact excerpt of the USER'S REQUEST about this control, or null if the request says nothing about it (never quote this instruction text or the file list).
- plan: what the tool will do, in plain words.
- status: "applied" (asked and done), "default" (not asked), "adjusted" (asked, but changed to something the game can do), "not_supported" (asked, but impossible here).
- why: the reason for "adjusted" or "not_supported", else null.
Anything the request asks for that no field can express (for example 3D characters, a different game mechanic, voice-over, real people, another game) goes into the closest row as "not_supported" with a short reason. Never ignore part of the request.

assumptions: what you had to guess because the request was ambiguous, each with the alternative (e.g. "'this object' read as the cursor; could also mean the end-card picture"). [] if nothing was guessed.

summary: one sentence describing the ad that will be made.

changed: the field groups the REQUEST asks to set or change, and nothing else. Groups: level.source, level.shape, level.size, level.blocks, level.colours, level.label, level.moves, level.changes, level.difficulty, level.pieces, level.style, gameplay.ending, gameplay.mistakes, gameplay.hesitations, gameplay.retake, gameplay.clock, gameplay.events, gameplay.finish, gameplay.clock_left, gameplay.blocks_left, pacing.length, pacing.tempo, pacing.curve, channel, visuals.colours, visuals.background, visuals.board, visuals.captions, visuals.zoom, visuals.cursor, visuals.hud, format, language, concept.hook, concept.mistake, concept.fix, concept.hurry, concept.cascade, concept.result, concept.end_title, concept.end_fact, concept.cta, sequence, sequence.timing, sequence.caption_times, visuals.punch_in, assets, audio, audio.music. (What to keep goes in "keep", not here.) Only fields in these groups are used; everything else keeps the tool's default (or, for an edit, its current value). So: "no sound effects" -> audio; "replace the music" -> audio.music; "move the blue door to the top" -> level.changes; "use a hand" -> visuals.cursor; "make the hook say X" -> concept.hook only; "a difficult level" -> level.difficulty."""

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


def _parse(text: str) -> dict:
    try:
        return json.loads(text, strict=False)  # strict=False: models sometimes put raw newlines in strings
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1], strict=False)
        raise ValueError(f"the planner did not return JSON: {text[:200]!r}")


def _ask(client, system: str, user: str) -> dict:
    """The model's brief. A reply that is not valid JSON (a cut-off or malformed answer, which the
    hosted model returns now and then) is asked for once more before the request fails."""
    try:
        return _parse(client.complete(system, user, B.SCHEMA))
    except (ValueError, json.JSONDecodeError):
        return _parse(client.complete(system, user, B.SCHEMA))


UPLOAD_WORDS = ("logo", "attach", "upload", "image", "picture", "photo", "png", "jpg", "asset", "mascot",
                "sticker", "icon", "artwork", "graphic", "supplied", "provided", "given", "this one", "the new",
                "pointer", "cursor", "button", "badge", "background", "music", "track", "song")


def _only_mentioned_uploads(raw: dict, prompt: str, uploads: dict, current: dict | None, attached=()) -> None:
    """An uploaded file is used only if the prompt refers to it (its name, or words like "our
    logo", "the attached image"), or the version being edited already uses it. Otherwise it is
    left out, and the assets row says why."""
    text = prompt.lower()
    mentioned = any(re.search(rf"\b{w}", text) for w in UPLOAD_WORDS)
    used = {a["file"] for a in (current or {}).get("assets", [])}
    keep = []
    for a in raw.get("assets", []):
        f = a.get("file", "")
        stem = Path(f).stem.lower()
        named = stem in text or re.sub(r"[_\-]+", " ", stem) in text
        if f in uploads and f not in used and f not in attached and not named:
            # an earlier upload, not attached to this request: never picked by guess
            row = B.control(raw, "assets")
            row["why"] = (row.get("why") or "") + (f" {f} was uploaded earlier but is not attached to this request, so it "
                                                   f"is not used (attach the file, or name it).")
            continue
        if f in uploads and f not in used and not (named or mentioned):
            row = B.control(raw, "assets")
            row["why"] = (row.get("why") or "") + f" {f} was uploaded but the prompt does not say how to use it, so it is left out."
            continue
        keep.append(a)
    raw["assets"] = keep
    # the picture behind the board and the music follow the same rule
    cur_v, cur_a = (current or {}).get("visuals", {}), (current or {}).get("audio", {})
    for box, key, before in ((raw.get("visuals") or {}, "background_image", cur_v.get("background_image")),
                             (raw.get("audio") or {}, "music", cur_a.get("music"))):
        f = box.get(key)
        if not f or f == before or f in attached:
            continue
        stem = Path(f).stem.lower()
        if not (stem in text or re.sub(r"[_\-]+", " ", stem) in text):
            box[key] = before
            row = B.control(raw, "assets" if key == "music" else "visuals")
            row["why"] = (row.get("why") or "") + f" {f} is not attached to this request, so it is not used."


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


# Where an attached picture goes when an edit asks to use it but the model placed it nowhere,
# by the words of the prompt (first match), else the end-card picture.
PLACE_WORDS = (("obstacle", ("obstacle", "obstacles", "the walls", "wall", "pillar", "pillars", "barrier", "blocker")),
               ("button", ("button", "cta")), ("cursor", ("cursor", "hand", "finger", "pointer")),
               ("logo", ("logo", "brand", "watermark")),
               ("hook_icon", ("icon", "stopwatch", "clock icon", "sticker", "beside the hook", "next to the hook")),
               ("end_background", ("end card background", "end-card background", "end card's background",
                                   "closing background", "background of the end card")))
_END_CARD = re.compile(r"\b(end[- ]?card|closing (card|screen)|final (card|screen)|outro|cta screen)\b", re.I)
# An attachment is placed only when the prompt talks about using a picture.
USE_WORDS = ("asset", "attached", "attachment", "upload", "uploaded", "image", "picture", "photo", "object", "file",
             "this one", "this asset", "this image", "this picture", "this object", "mascot", "character", "artwork",
             "supplied", "provided", "new logo", "new badge", "new button", "new icon", "new pointer", "new sticker")


_GATE = r"(door|doors|gate|gates|exit|exits)"
_SIDE = r"(opposite|opposing|top|upper|bottom|lower|left|right|north|south|east|west|same side|outside|around the)"
_GATE_SIDE = re.compile(rf"{_GATE}[^.;]{{0,50}}\b{_SIDE}\b|\b{_SIDE}\b[^.;]{{0,30}}{_GATE}", re.I)


def _own_taste(brief: dict, changed: list[str]) -> None:
    """A change the request never asked about (the row quotes nothing) is the planner's own taste:
    shown as such, so the user knows it can be undone by asking for the game's own."""
    for row in brief["controls"]:
        own = [g for g in changed if g in B.GROUPS and B.GROUPS[g][0] == row["control"]]
        if own and not row.get("asked") and row["status"] != "not_supported" and "not asked for" not in (row.get("why") or ""):
            B.adjust(brief, row["control"], ", ".join(B.GROUP_NAMES.get(g, g) for g in own) +
                     ": not asked for; chosen to fit the request (say so to keep the game's own).")


_SPACIOUS = re.compile(r"\b(plenty of|enough|lots of|loads of|ample|generous|more|much)\s+(free |empty |open |breathing )?(space|room|cells|tiles|squares)\b"
                       r"|\b(space|room)\s+(to|for)\s+(move|moving|movement|manoeuvr\w*|maneuver\w*|breathe)\b"
                       r"|\b(spacious|roomy|uncluttered|sparse|airy)\b|\bnot\s+(too\s+)?(crowded|packed|cramped|busy)\b"
                       r"|\b(lots of|plenty of|many)\s+(empty|free|open)\s+(cells|tiles|squares)\b", re.I)


_PACED = re.compile(r"\b(pause|pauses|pausing|a breath|breathe|breathing)\s+(between|after|before)\b|\bslow(ly)?\s+and\s+deliberate(ly)?\b"
                    r"|\bdeliberate(ly)?\b|\bone\s+(block\s+)?at\s+a\s+time\b|\btakes?\s+(their|its|his|her)\s+time\b|\bunhurried\b|\bno\s+rush\b", re.I)
_CHAIN = re.compile(r"\b(cascade|chain|in a row|one after another|quick succession|all fly out|frees? (them all|everything))\b", re.I)


def _paced_moves(brief: dict, prompt: str) -> None:
    """"A pause between moves", "slow and deliberate", "one at a time": the drags are paced, so the
    finish is not a cascade (the model's own table makes a relaxing ad a streak, which is the
    opposite of pauses between moves) unless the prompt also asks for a chain."""
    if brief["gameplay"].get("finish") != "streak" or not _PACED.search(prompt) or _CHAIN.search(prompt):
        return
    brief["gameplay"]["finish"] = "auto"
    brief["changed"] = [g for g in brief["changed"] if g != "gameplay.finish"]
    brief["assumptions"].append("The request asks for a pause between moves, so the blocks are cleared one by one at "
                                "that pace rather than in a fast chain at the end.")


def _spacious(brief: dict, prompt: str) -> None:
    """Words about free space on the board ("enough free space for movement", "room to move") are
    the board's look "spacious": few blocks, none touching, most cells empty. The model often reads
    them only as "easy" and then the level is sized to the ad's length (10 blocks for 30 s, touching
    each other), which is not what was asked."""
    hits = [m for m in _SPACIOUS.finditer(prompt)
            # "create enough space for the other side" is what the player does, not the board's look
            if not re.search(r"\b(create|creates|make|makes|free|frees|open|opens|clear|clears|gain|gains|up)\s*$", prompt[max(0, m.start() - 12):m.start()], re.I)]
    if not hits or re.search(r"\b(no|little|hardly any|not much|limited|tight|scarce|minimal|less)\s+(free |empty |open )?(space|room|cells)\b",
                             prompt, re.I):
        return  # "limited empty space for movement" is the opposite ask
    style = brief["level"].setdefault("style", [])
    if "spacious" not in style:
        style.append("spacious")
    if "packed" in style:
        style.remove("packed")
    if "level.style" not in brief["changed"]:
        brief["changed"].append("level.style")
    if brief["level"].get("source") == "shipped":
        brief["level"]["source"], brief["level"]["shipped"] = "generate", None


def _gate_sides(brief: dict, prompt: str) -> None:
    """Which edge a gate sits on is not a control (the generator puts each gate where its block's
    path ends): a request about it is told so, instead of a row that quietly claims it."""
    if any(c.get("op") == "move_gate" for c in brief["level"].get("changes") or []):
        return  # an edit moving a door on the current board: boardedit does it
    if _GATE_SIDE.search(prompt) and not any("gate sits" in (r.get("why") or "") for r in brief["controls"]):
        B.adjust(brief, "level", "where a gate sits (which edge, opposite sides, around the outside) cannot be chosen: "
                                 "the generator puts each gate where its block's path ends.")


_FLAT = re.compile(r"\bflat\b[^.;]{0,20}\b(block|blocks|surface|surfaces|design|look|style|shading)\b|\bno shading\b|\bmatte\b|\bno (gloss|shine|highlights)\b", re.I)
_DECOR = re.compile(r"\b(decorations?|decorative|ornaments?|confetti|sparkles?|stickers?|props|embellishments?|garlands?)\b", re.I)


_ONE_GATE = re.compile(r"\b(only|just|a single|one)\s+(a\s+|an\s+)?(\w+\s+)?(gate|door|exit)\b|\b(no|without)\s+(a\s+)?(\w+\s+)?(gates?|doors?|exits?)\b"
                       r"|\b(gates?|doors?|exits?)\s+for\s+(only|just)\b", re.I)
_TIME_OUT_WORDS = ("time out", "time-out", "times out", "runs out", "run out", "clock hits", "fail", "fails", "lose", "loses")


def _one_gate_only(brief: dict, prompt: str, current: dict | None) -> None:
    """A board with a gate for one colour only cannot be won (a block with no gate never leaves):
    every colour on the board gets its gate, and the play is not turned into a time-out for it."""
    if not _ONE_GATE.search(prompt):
        return
    B.adjust(brief, "level", "every colour on the board gets its own gate: a block with no gate could never leave and "
                             "the level could not be won, so a single gate is not made.")
    gp = brief["gameplay"]
    if gp["ending"] == "time_out" and not any(w in prompt.lower() for w in _TIME_OUT_WORDS):
        gp["ending"] = (current or {}).get("gameplay", {}).get("ending") or "win"
        if gp["ending"] == "time_out":
            gp["ending"] = "win"
        gp["mistakes"], gp["mistake_kinds"] = None, []
        B.adjust(brief, "gameplay", "the request does not ask for a fail, so the play is not a time-out; the level is "
                                    "won as usual.")
        if "gameplay.ending" in brief["changed"] and current is not None:
            brief["changed"] = [g for g in brief["changed"] if g != "gameplay.ending"]


_GENEROUS = re.compile(r"\b(generous|relaxed|long|plenty of|lots of|ample|no)\s+(timer|time|clock|time limit)\b|\bno (time )?pressure\b|\bnever feel rushed\b", re.I)


_FAIL_WORDS = re.compile(r"\b(end(s|ing)? in failure|designed to (end in )?fail|failure state|lose the level|loses the level|a loss|fail state|fails the level|closes off|dead end|dead-end|stuck for good|no way out|unsolvable after)\b", re.I)


def _what_failure_is(brief: dict, prompt: str) -> None:
    """In this game a wrong order never closes the solution for good (blocks can always move back):
    the only failure is the clock. A failure creative is a time-out, and says so."""
    if not _FAIL_WORDS.search(prompt):
        return
    gp = brief["gameplay"]
    if gp["ending"] != "time_out":
        gp["ending"] = "time_out"
        if "gameplay.ending" not in brief["changed"]:
            brief["changed"].append("gameplay.ending")
    B.adjust(brief, "gameplay", "in this game a poor order never closes the solution for good (every block can move "
                                "back), so the only real failure is the clock running out: the play is a time-out, "
                                "with the wrong moves shown before it.")


def _generous_clock(brief: dict, prompt: str, current: dict | None) -> None:
    """A generous clock and a near-fail do not go together (a near-fail lands on the last seconds):
    when the request asks for a relaxed clock and no fail, the play is a win."""
    gp = brief["gameplay"]
    if not _GENEROUS.search(prompt) or gp["ending"] not in ("near_fail", "time_out"):
        return
    if any(w in prompt.lower() for w in _TIME_OUT_WORDS) or (current and current["gameplay"]["ending"] == gp["ending"]):
        return
    gp["ending"], gp["mistakes"], gp["mistake_kinds"] = "win", None, []
    B.adjust(brief, "gameplay", "a generous clock does not go with a near-fail (which lands on the last seconds), and "
                                "the request asks for no fail: the play is a win, with the clock as asked.")


_MID_START = re.compile(r"\b(start|starts|starting|open|opens|opening|begin|begins)\b[^.;]{0,40}\b(nearly|almost|half|mostly|partly|partially)[\s-]+(solved|finished|complete|completed|cleared|done|empty)\b"
                        r"|\b(nearly|almost|half|mostly)[\s-]+(solved|finished|complete|cleared) (puzzle|board|level)\b|\bmid-?level\b|\bmidway through\b|\bnear the end of the level\b", re.I)


def _mid_level_start(brief: dict, prompt: str, current: dict | None) -> None:
    """Every ad is filmed from the level's first move: a request to open on a nearly solved board
    gets a small level that is over in a few moves, and is told so."""
    if not _MID_START.search(prompt) or current is not None:
        return
    lv = brief["level"]
    if lv["blocks"] is None or lv["blocks"] > 5:
        lv["blocks"] = 5
        if "level.blocks" not in brief["changed"]:
            brief["changed"].append("level.blocks")
    if lv["source"] == "shipped":  # the game's own levels are not sized to the ad; a generated small one is
        lv["source"], lv["shipped"] = "generate", None
    B.adjust(brief, "gameplay", "the game is filmed from the level's first move, so an ad cannot open on a board that "
                                "is already nearly solved: the nearest thing is a small level (5 blocks) that is over "
                                "in a few moves.")


_NO_CAPTIONS = re.compile(r"\b(no|without|free of|zero)\s+(text|texts|captions?|narration|on-?screen text|words on screen|subtitles?|overlays?|copy)\b"
                          r"|\btext-free\b|\bcaption-free\b|\bwithout (any )?(text|words|captions?)\b|\bactions? alone\b", re.I)
PLAY_TEXTS = ("mistake", "fix", "hurry", "cascade", "result")  # the hook is frame 0's poster text: it stays


def _no_captions(brief: dict, prompt: str) -> None:
    """"Without text narration": no caption over the play ("" removes one); the end card keeps its
    title and button, which are not narration."""
    if not _NO_CAPTIONS.search(prompt):
        return
    cc = brief["concept"]
    if all(cc.get(k) == "" for k in PLAY_TEXTS):
        return
    for k in PLAY_TEXTS:
        cc[k] = ""
        if f"concept.{k}" not in brief["changed"]:
            brief["changed"].append(f"concept.{k}")
    B.adjust(brief, "concept", "no captions over the play, as asked, except the hook on the first frames (it is the "
                               "poster and the first thing a feed shows); the end card keeps its title and button.",
             status="applied")


_EXACT = re.compile(r"\b(this |the |an )?exact(ly)?\b[^.]{0,30}\b(sequence|order|steps)\b|\bin (this|that) (exact )?order\b|\bstep by step\b|\bprecisely (this|these)\b", re.I)


def _exact_sequence(brief: dict, prompt: str) -> None:
    """"This exact sequence: first the yellow block..., then the green..., finally the red": the level has
    exactly the blocks the sequence names, so nothing else leaves in between."""
    gp, lv = brief["gameplay"], brief["level"]
    if not _EXACT.search(prompt) or lv["blocks"] is not None:
        return
    singles = list(dict.fromkeys(e["block"]["colour"] for e in gp.get("events") or []
                                 if (e.get("block") or {}).get("colour") and (e.get("block") or {}).get("which", "any") == "any"
                                 and not (e.get("block") or {}).get("all")))
    if len(singles) < 2:
        return
    lv["blocks"], lv["colours"] = len(singles), singles
    for g in ("level.blocks", "level.colours"):
        if g not in brief["changed"]:
            brief["changed"].append(g)
    B.adjust(brief, "level", f"the exact sequence names {len(singles)} blocks ({', '.join(c.lower() for c in singles)}), "
                             f"so the level has exactly those, and nothing else leaves in between.")


def _one_of_its_kind(brief: dict) -> None:
    """An event about 'the longest blue block' or 'the biggest red block' wants that block to be the
    one of its kind: the other blocks stay ordinary, not all long or all big."""
    gp, lv = brief["gameplay"], brief["level"]
    named = [(e["block"]["which"], e["block"]["colour"]) for e in gp.get("events") or []
             if (e.get("block") or {}).get("colour") and (e.get("block") or {}).get("which") in ("biggest", "longest")]
    if named and lv["pieces"] in ("long", "big", "small"):
        which, colour = named[0]
        was = lv["pieces"]
        lv["pieces"] = "mixed"
        if "level.pieces" not in brief["changed"]:
            brief["changed"].append("level.pieces")
        B.adjust(brief, "level", f"the {colour.lower()} block is the {which} one on the board, so the blocks are not "
                                 f"all {was}: the others stay ordinary sizes and the {colour.lower()} one is bigger.")


def _art_limits(brief: dict, prompt: str, files: list[str]) -> None:
    """What a theme cannot do: the blocks' shading is the game's own art (only their colours change),
    and decorations need a picture to put on the ad."""
    whys = " ".join((r.get("why") or "") for r in brief["controls"])
    if _FLAT.search(prompt) and "shading" not in whys:
        B.adjust(brief, "visuals", "the blocks' shading and shine are the game's own art and cannot be made flat; "
                                   "only their colours change.")
    if _DECOR.search(prompt) and not files and not brief["assets"] and "decorations need" not in whys:
        B.adjust(brief, "assets", "decorations need a picture: none was attached, so the theme is colours only "
                                  "(attach a sticker or a mascot and say where it goes).")


_PIECE = r"\b(blocks?|doors?|gates?|exits?)\b"
_ART = r"\b(versions?|graphics?|textures?|materials?|sprites?|skins?|artwork|pictures?|images?|assets?|gold[- ]edged)\b"
_BLOCK_ART = re.compile(
    rf"\b(replace|swap|change|turn)\b[^.;]{{0,40}}{_PIECE}[^.;]{{0,50}}\bwith\b[^.;]{{0,40}}{_ART}"  # the red block with the gold version
    rf"|\b(use|apply|put|place|map|wrap)\b[^.;]{{0,50}}{_ART}[^.;]{{0,40}}\b(to replace|to|on|onto|over|for|as)\b[^.;]{{0,30}}{_PIECE}"
    r"|\b(block|door|gate|exit)'?s?\s+(surface|texture|material|skin|sprite|artwork)\b"  # the block's texture
    rf"|\b(restyle|reskin|retexture)\b[^.;]{{0,40}}{_PIECE}", re.I)
_BORDER = re.compile(r"\bborders?\b|\bdecorative\s+frames?\b|\bframes?\s+(a?round|on the edges?)\b", re.I)


def _block_art(brief: dict, prompt: str, current: dict | None, attached: list[str]) -> None:
    """A picture, texture or material on a block or a door is not something the game can show: its
    blocks and gates are its own pieces, drawn in their colour slot. The request is answered so,
    nothing is placed somewhere else instead, and no colour is repainted in its place (a repaint
    changes every block of that colour and its gate, never one block)."""
    text = re.sub(r"\bcolou?r[\s-]*block[\s-]*jam\b", " ", prompt, flags=re.I)  # the game's name is no block
    if not _BLOCK_ART.search(text) or not (attached or re.search(r"\b(supplied|attached|provided|uploaded)\b", text, re.I)):
        return
    base = current or B.check(B.default_brief())
    pics = [f for f in attached if not B.is_audio(f)]
    if _skin_on_a_block(brief, text, pics, current):
        return  # a texture on one block of a colour: drawn on it, frame by frame, by the compositor
    brief["assets"] = [a for a in brief["assets"] if a["file"] not in pics] if current is None else copy.deepcopy(base["assets"])
    brief["visuals"]["blocks"] = copy.deepcopy(base["visuals"]["blocks"])
    brief["visuals"]["theme"] = base["visuals"]["theme"]
    brief["changed"] = [g for g in brief["changed"] if g not in ("assets", "visuals.colours")]
    many = re.search(r"\b(two|both|three|several|multiple)\b", prompt, re.I)
    for name in ("visuals", "assets"):  # the model's own plan for it (a repaint, a sticker) is not done
        row = B.control(brief, name)
        row.update(why=None, status="default", plan="Nothing is changed.")
    B.adjust(brief, "visuals", "a picture, texture or material cannot be put on a block or a door: they are the game's "
                               "own pieces, drawn in their colour, and their shape is their collision shape. A colour can "
                               "be repainted instead, but a repaint changes every block of that colour and its gate, "
                               + ("so it cannot pick one of several blocks of the same colour; " if many else "")
                               + "nothing was changed (the picture can go in a top corner, beside the hook or on the "
                                 "end card if wanted).", status="not_supported")


_SKIN_BLOCK = re.compile(r"\b(?:the|that|this|one|a|every|all|each)?\s*((?:light |dark |pale |deep |bright |hot )?[a-z]+)\s+(blocks?|bricks?|pieces?)\b", re.I)
_SKIN_WORDS = re.compile(r"\b(textures?|skins?|materials?|patterns?|surfaces?|pictures?|images?|graphics?|artwork|stickers?|"
                         r"versions?|designs?|sprites?|looks?)\b", re.I)


def _skin_on_a_block(brief: dict, text: str, pics: list[str], current: dict | None) -> bool:
    """"Apply this ice texture to the blue block": one attached picture and one block colour make a
    texture on that block (asset role "skin"): the compositor draws it on the block's cells on every
    gameplay frame from the recorded block positions, so the block's shape, moves and exit stay the
    game's (2026-10-15, after the research note on object masks from the recorder). A door or a gate
    stays refused, and so does a picture with no block colour to put it on."""
    if len(pics) != 1 or not _SKIN_WORDS.search(text) or re.search(r"\b(doors?|gates?|exits?)\b", text, re.I):
        return False
    # the colour word as THIS creative shows it: "the cyan block" on a trailer copy whose green slot is painted cyan
    # resolves through the shown names and shades (brief.slot_of_colour_word), not only the game's seven names
    m, colour = None, None
    for cand in _SKIN_BLOCK.finditer(text):
        colour = B.slot_of_colour_word(cand.group(1), current)
        if colour:
            m = cand
            break
    if m is None:
        return False
    f = pics[0]
    kept = [a for a in (current["assets"] if current is not None else brief["assets"]) if a["file"] != f and a.get("role") != "skin"]
    brief["assets"] = kept + [{"file": f, "role": "skin", "when": "whole", "where": "auto", "block": colour}]
    if "assets" not in brief["changed"]:
        brief["changed"].append("assets")
    brief["changed"] = [g for g in brief["changed"] if g != "visuals.colours"]
    brief["visuals"]["blocks"] = copy.deepcopy((current or B.check(B.default_brief()))["visuals"]["blocks"])
    row = B.control(brief, "assets")
    row.update(plan=f"{f} is drawn as a texture on the {colour.lower()} block on every gameplay frame, following the "
                    f"block; the block's shape, colour identity, moves and exit stay the game's. Every other picture stays.",
               status="applied", why=None)
    vrow = B.control(brief, "visuals")
    if vrow["status"] == "not_supported":
        vrow.update(status="default", why=None, plan="Nothing else is changed.")
    brief["assumptions"] = [x for x in brief.get("assumptions", []) if f not in x]
    brief["assumptions"].append(f"\"{m.group(0).strip()}\" names the block that gets {f}: the texture is composited on "
                                f"that block's cells, not a change to the game's own block.")
    return True


def _no_border(brief: dict, prompt: str, current: dict | None, attached: list[str]) -> None:
    """The ads have no decorative border (or frame) layer: a request for one is told so, and the
    attached picture is not put somewhere else instead."""
    if not _BORDER.search(prompt) or re.search(r"\b(board|cell)s?\s+(border|frame)", prompt, re.I):
        return
    base = current or B.check(B.default_brief())
    pics = [f for f in attached if not B.is_audio(f)]
    if any(a["file"] in pics for a in brief["assets"]) or brief["visuals"].get("background_image") in pics:
        brief["assets"] = copy.deepcopy(base["assets"])
        brief["visuals"]["background_image"] = base["visuals"].get("background_image")
        brief["changed"] = [g for g in brief["changed"] if g not in ("assets", "visuals.background")]
    B.adjust(brief, "assets", "the ads have no decorative border or frame to set: a picture can go in a top corner, "
                              "beside the hook, on the end card, or behind the board; nothing was changed.",
             status="not_supported")


_STILL_OPEN = re.compile(r"\b(open|opens|opening|start|starts|begin|begins)\b[^.;]{0,30}\b(still|static|frozen|freeze)\b"
                         r"|\b(still|static|frozen)\s+(opening|first|start\w*|intro|hook)\b", re.I)
_RESULT_FIRST = re.compile(r"\b(result|win|ending|outcome|victory)\b[^.;]{0,25}\b(first|at the start|up front)\b"
                           r"|\b(start|open)\w*\b[^.;]{0,20}\bwith the (result|win|ending)\b", re.I)


def _still_opening(brief: dict, prompt: str) -> None:
    """"Open on a still frame with the headline" is the still opening frame (intro_s), never the
    result-first teaser, which shows the win before the play."""
    if not _STILL_OPEN.search(prompt):
        return
    sq = brief["sequence"]
    if sq["style"] == "result_first" and not _RESULT_FIRST.search(prompt):
        sq["style"] = "standard"
    if sq.get("intro_s") is None:
        sq["intro_s"] = 2.5
    for g in ("sequence", "sequence.timing"):
        if g not in brief["changed"]:
            brief["changed"].append(g)
    row = B.control(brief, "sequence")
    row["plan"] = f"A still opening frame ({sq['intro_s']:g} s) under the hook, then the gameplay."
    if row["status"] == "default":
        row["status"] = "applied"


_PICTURE_ASK = re.compile(r"\b(replace|swap|use|put|add|insert)\b[^.;]{0,60}\b(image|picture|logo|photo|file|asset|icon|sticker|track|music|song)\b", re.I)


_NEEDS = re.compile(r"\b(?:the\s+)?(?:attached|supplied|provided|uploaded)\s+((?:[a-z][a-z-]*\s+){0,3}?"
                    r"(?:pictures?|images?|photos?|logos?|stickers?|icons?|mascots?|graphics?|artworks?|badges?|buttons?|"
                    r"tracks?|music|songs?|files?|assets?))\b", re.I)


def needs_files(prompt: str, files: list[str]) -> list[str]:
    """The files a request says are attached but are not: "the attached toy pictures", "the supplied
    logo". Plain words, for the question the tool asks instead of making the ad without them."""
    if files:
        return []
    found = []
    for m in _NEEDS.finditer(prompt):
        phrase = " ".join(m.group(1).split()).lower()
        phrase = phrase[4:] if phrase.startswith("the ") else phrase
        if phrase not in found:
            found.append(phrase)
    if not found and _PICTURE_ASK.search(prompt) and re.search(r"\b(uploaded|attached|supplied|provided)\b", prompt, re.I):
        found.append("the file the request refers to")
    return found


def _missing_attachment(brief: dict, prompt: str, files: list[str], current: dict | None) -> None:
    """A request to use a file that is not attached ("the attached logo", "the image I uploaded
    yesterday") gets a question, not a guess: the brief lists what is needed (`needs`), the studio
    refuses to make the ad until the files are attached or the user says to go without them, and
    no earlier upload is taken by guess."""
    needs = needs_files(prompt, files)
    if not needs and (files or not _PICTURE_ASK.search(prompt)):
        return
    if not needs and not re.search(r"\b(uploaded|attached|supplied|provided|sent|yesterday|earlier|before|new)\b", prompt, re.I):
        return
    base = current or B.check(B.default_brief())
    named = [a for a in brief["assets"] if a not in base["assets"] and Path(a["file"]).stem.lower() in prompt.lower()]
    if named:
        return  # an earlier upload named by its file name is a choice, not a guess
    brief["assets"] = copy.deepcopy(base["assets"])
    brief["changed"] = [g for g in brief["changed"] if g != "assets"]
    B.control(brief, "assets").update(why=None, status="default", plan="Every picture stays as it is.")
    if needs:
        brief["needs"] = needs
        B.adjust(brief, "assets", f"this request uses files that are not attached: {' and '.join(needs)}. Attach them "
                                  "and plan again, or choose to make the ad without them; the tool never picks an "
                                  "earlier upload by guess.", status="not_supported")
    else:
        B.adjust(brief, "assets", "no file is attached to this request, and the tool does not pick an earlier upload by "
                                  "guess: attach the picture (or name its file) and say where it goes; nothing was changed.",
                 status="not_supported")


def _one_background(brief: dict, prompt: str, current: dict | None) -> None:
    """A picture asked for behind the board is not also put on the end card's background (the
    model sometimes fills both) unless the prompt names the end card."""
    pic = brief["visuals"].get("background_image")
    if not pic or _END_CARD.search(prompt):
        return
    base = (current or B.check(B.default_brief()))["assets"]
    old_end = [a for a in base if B.asset_slot(a) == "end_background"]
    dup = [a for a in brief["assets"] if a["file"] == pic and B.asset_slot(a) == "end_background" and a not in base]
    if not dup:
        return
    brief["assets"] = [a for a in brief["assets"] if a not in dup] + [a for a in old_end if a not in brief["assets"]]
    if brief["assets"] == base:
        brief["changed"] = [g for g in brief["changed"] if g != "assets"]
        row = B.control(brief, "assets")
        row.update(status="default", plan="Every picture stays as it is.")


_TRANSITION = re.compile(r"\b(dissolves?|cross-?fades?|fade[sd]?( in| out| to)?|wipes?|transitions?)\b", re.I)


def _no_transitions(brief: dict, prompt: str) -> None:
    """The ad's parts cut directly into each other: a request to change or add a dissolve, a fade
    or a wipe between them is answered so (nothing to change), never claimed."""
    sound_fade = r"\b(music|track|song|sound|audio)\b[^.;]{0,30}\bfade|\bfade\w*\b[^.;]{0,30}\b(music|track|song|sound|audio)\b"
    if not _TRANSITION.search(prompt) or re.search(sound_fade, prompt, re.I):
        return
    B.adjust(brief, "sequence", "the ad's parts already cut directly into each other: there are no dissolves, fades "
                                "or wipes between them to change or add, so this part of the request changes nothing.",
             status="not_supported")


MUSIC_WORDS = ("music", "track", "song", "soundtrack", "tune", "melody", "bgm", "jingle")


def _music_from_attachment(brief: dict, prompt: str, attached: list[str]) -> None:
    """An attached sound file the prompt uses as music ("replace the music with the attached track"),
    which the model did not set, becomes the music; a sound file is never a picture."""
    sounds = [f for f in attached if B.is_audio(f)]
    if not sounds or brief["audio"].get("music") in sounds or not B._has_word(prompt.lower(), MUSIC_WORDS):
        return
    brief["audio"]["music"] = sounds[0]
    if "audio.music" not in brief["changed"]:
        brief["changed"].append("audio.music")
    row = B.control(brief, "assets")
    row["asked"] = row["asked"] or prompt.strip()
    row["plan"] = (row["plan"] + " " if row["plan"] else "") + f"{sounds[0]} plays as the music."
    if row["status"] in ("default", "not_supported"):
        row["status"] = "applied"
        row["why"] = None


_EVERYWHERE = re.compile(r"\b(everywhere|every place|wherever|all (the )?places|both places|each place|every time it appears|"
                         r"all (its|of its) appearances)\b", re.I)


def _replace_everywhere(brief: dict, prompt: str, attached: list[str], current: dict | None) -> bool:
    """"Replace the red badge everywhere it appears": every slot showing that picture now (the
    one the prompt describes, or the one used in several places) gets the attached one, each in
    its own place. True when it did so."""
    pics = [f for f in attached if not B.is_audio(f)]
    if current is None or len(pics) != 1 or not _EVERYWHERE.search(prompt):
        return False
    words = set(re.findall(r"[a-z]+", prompt.lower()))
    by_file: dict[str, list[dict]] = {}
    for a in current["assets"]:
        if a["file"] != "builtin:none":
            by_file.setdefault(a["file"], []).append(a)
    def fits(f):
        stem = [w for w in re.findall(r"[a-z]+", Path(f).stem.lower()) if len(w) > 2]
        return stem and sum(w in words for w in stem) >= max(1, len(stem) - 1)
    target = next((f for f in by_file if fits(f)), None) or next((f for f, xs in by_file.items() if len(xs) > 1), None)
    if target is None:
        return False
    from . import edits
    new = copy.deepcopy(brief)
    slots = []
    for a in by_file[target]:
        slot = B.asset_slot(a)
        placed, _ = edits.replace_picture(new, slot, pics[0])
        new["assets"] = placed["assets"]
        slots.append(edits.PICTURES[slot]["name"])
    brief["assets"] = new["assets"]
    if "assets" not in brief["changed"]:
        brief["changed"].append("assets")
    row = B.control(brief, "assets")
    row["asked"] = row["asked"] or prompt.strip()
    row["plan"] = f"{pics[0]} replaces {target} everywhere it appears ({' and '.join(slots)}), each in its own place."
    row["status"] = "applied"
    return True


_OBSTACLE_WORDS = re.compile(r"\b(obstacles?|walls?|pillars?|barriers?|blockers?)\b", re.I)
_PICTURE_WORDS = re.compile(r"\b(this|that|the attached|the uploaded|the new|the supplied|attached|uploaded)\s+"
                            r"(object|picture|image|asset|file|graphic|artwork|sprite|texture|tile)s?\b|\b(attached|uploaded)\b", re.I)
_OBSTACLE_VERBS = re.compile(r"\b(instead of|in place of|replac\w*|put|place|draw|paint|use|swap|cover|turn)\b", re.I)


def _asks_obstacle_picture(prompt: str) -> bool:
    """One sentence that names the obstacle, a picture to use, and a verb that puts one on the other."""
    return any(_OBSTACLE_WORDS.search(x) and _PICTURE_WORDS.search(x) and _OBSTACLE_VERBS.search(x)
               for x in re.split(r"[.;!?\n]", prompt))


def _reference_carries(brief: dict, prompt: str, analyses: list[dict]) -> None:
    """Two things a reference video gives that the model tends to drop or misplace (2026-10-15): the
    game's name stays the end card's title (a fact the model wrote there becomes the line under it,
    unless the request asked for a title), and a level number seen in the clip goes to the badge."""
    cc = brief["concept"]
    title = cc.get("end_title")
    if title and "color block jam" not in title.lower() and not cc.get("end_fact") and not re.search(r"\btitle\b", prompt, re.I):
        cc["end_fact"], cc["end_title"] = title, None
    if brief["level"].get("label") is None and analyses:
        seen = json.dumps([a.get("notes") for a in analyses if a.get("kind") == "video"], ensure_ascii=False)
        m = re.search(r"\blevel\s+(\d{1,4})\b", seen, re.I)
        if m and re.search(r"\b(version of|adapt|concept|like this|recreate|inspired)\b", prompt, re.I):
            brief["level"]["label"] = int(m.group(1))


def _obstacle_picture(brief: dict, prompt: str, attached: list[str]) -> None:
    """"Use this object instead of the current obstacle": an attached picture the request puts on
    the obstacle (the board's walls) gets the obstacle role, wherever the model put it (brief p.6)."""
    if not attached or not _asks_obstacle_picture(prompt):
        return
    pics = [a for a in brief["assets"] if a["file"] in attached and not B.is_audio(a["file"])]
    if len(pics) != 1 or pics[0].get("role") == "obstacle":
        return
    a = pics[0]
    a["role"], a["when"], a["where"] = "obstacle", "whole", "auto"
    if "assets" not in brief["changed"]:
        brief["changed"].append("assets")
    row = B.control(brief, "assets")
    row["plan"] = f"{a['file']} is drawn on the board's walls (the obstacle) during the play; every other picture stays."
    row["status"] = "applied" if row["status"] in ("default", "not_supported", "adjusted") else row["status"]
    row["why"] = None
    brief["assumptions"] = [x for x in brief.get("assumptions", []) if a["file"] not in x or "obstacle" in x.lower()]


_STYLE_USE = re.compile(r"\b(colou?rs?|palette|tones?|shades?|hues?|style|look|mood|feel)\b[^.;]{0,30}\b(from|of|in|like)\s+(this|the attached|the)\s+(image|picture|photo|reference|file)\b"
                        r"|\b(inspired by|in the style of|styled (like|after)|match(ing)? the (colou?rs|palette|look) of)\b", re.I)


def _place_unplaced(brief: dict, prompt: str, attached: list[str], current: dict | None) -> None:
    """An edit that attaches a picture and asks to use it, which the model placed nowhere, puts it
    in the slot the prompt names, else in the end-card picture, and says which (brief p.4: "replace
    this object with the attached asset")."""
    from . import edits
    text = prompt.lower()
    used = {a["file"] for a in brief["assets"]} | {brief["visuals"].get("background_image"), brief["audio"].get("music")}
    todo = [f for f in attached if f not in used and not B.is_audio(f)]
    if current is None or len(todo) != 1 or not B._has_word(text, USE_WORDS):
        return
    if _STYLE_USE.search(text) and any(g.startswith("visuals.") for g in brief.get("changed", [])):
        return  # "take the colours from this image": a style reference the model read into the look, not a picture to place (2026-10-18)
    f = todo[0]
    pictured = re.sub(r"\bbackground\s+(music|track|song|sound|audio|tune)s?\b", " ", text)
    if B._has_word(pictured, ("background", "backdrop")) and not _END_CARD.search(pictured) and not B.is_audio(f):
        # the background behind the board (the gameplay's), not the end card's
        brief["visuals"]["background_image"] = f
        if "visuals.background" not in brief["changed"]:
            brief["changed"].append("visuals.background")
        row = B.control(brief, "visuals")
        row["asked"] = row["asked"] or prompt.strip()
        row["plan"] = f"{f} is shown behind the board during the gameplay; the board, blocks and HUD stay as they are."
        if row["status"] in ("default", "not_supported"):
            row["status"] = "applied"
        return
    slot = next((s for s, words in PLACE_WORDS if B._has_word(text, words)), None)
    if slot == "logo":
        slots = {B.asset_slot(a): a for a in (current or {}).get("assets", [])}
        closing = bool(_END_CARD.search(text)) or re.search(r"\b(closing|final|ending)\b", text)
        if (closing or "logo" not in slots) and "end_art" in slots:
            slot = "end_art"  # the logo this ad shows is the picture on its end card
    guessed = slot is None
    if guessed:
        slot = "end_art" if brief["gameplay"]["ending"] != "cliffhanger" else "hook_icon"
    placed, _ = edits.replace_picture(brief, slot, f)
    brief["assets"] = placed["assets"]
    if "assets" not in brief["changed"]:
        brief["changed"].append("assets")
    name = edits.PICTURES[slot]["name"]
    row = B.control(brief, "assets")
    row["asked"] = row["asked"] or prompt.strip()
    row["plan"] = f"{f} replaces {name}; every other picture stays."
    if row["status"] == "default":
        row["status"] = "applied"
    if guessed:
        brief["assumptions"].append(f"'{f}' read as a replacement for {name}; it could also be the icon beside the "
                                    f"hook or the logo (say which, and it moves there).")


def _note_guessed_slot(brief: dict, prompt: str, attached: list[str], current: dict | None) -> None:
    """"Keep this creative exactly the same, but replace this object with the attached asset" (brief p.4) names
    no thing: when the model placed the one attached picture in a slot by itself, the guess is written as an
    assumption with the alternatives (2026-10-18: a gold star became the PLAY NOW button without a word)."""
    from . import edits
    if current is None:
        return
    text = prompt.lower()
    pics = [f for f in attached if not B.is_audio(f)]
    if len(pics) != 1 or not B._has_word(text, USE_WORDS):
        return
    f = pics[0]
    if any(B._has_word(text, words) for _, words in PLACE_WORDS) or _END_CARD.search(text) or B._has_word(text, ("background", "backdrop")) \
            or re.search(r"\b(block|blocks|texture|skin|music|track)\b", text):
        return  # the request names the thing
    before = {B.asset_slot(a) for a in (current.get("assets") or []) if a.get("file") == f}
    placed = [B.asset_slot(a) for a in brief["assets"] if a.get("file") == f and B.asset_slot(a) not in before]
    if len(placed) != 1 or any(f in a for a in brief.get("assumptions", [])):
        return
    slot = placed[0]
    if any("this object" in a.lower() for a in brief.get("assumptions", [])):
        return  # the planner already said how it read "this object" (E1, 2026-10-19: the same guess written twice)
    name = edits.PICTURES.get(slot, {}).get("name", slot)
    others = [edits.PICTURES[s]["name"] for s in ("hook_icon", "logo", "end_art", "button") if s != slot and s in edits.PICTURES]
    brief["assumptions"].append(f"'This object' names nothing, so '{f}' is read as a replacement for {name}; it could also be "
                                + ", ".join(others[:-1]) + f" or {others[-1]} (say which, and it moves there).")


_REMOVE_OBSTACLE = re.compile(r"\b(remov\w*|delet\w*|take (out|away)|get rid of|drop\w*|without|fewer|clear\w*)\b[^.;]{0,40}"
                              r"\b(obstacles?|walls?|holes?|pillars?|barriers?|blockers?)\b", re.I)


def _no_obstacles_to_remove(brief: dict, prompt: str, current: dict) -> None:
    """An edit that asks to remove an obstacle from a board that has none (an open board: no walls,
    no holes) keeps the board; the model's new board shape is not a removal."""
    if not _REMOVE_OBSTACLE.search(prompt) or current["level"]["shape"] != "open":
        return
    if brief["level"]["shape"] != current["level"]["shape"]:
        brief["level"]["shape"] = current["level"]["shape"]
        brief["changed"] = [g for g in brief["changed"] if g != "level.shape"]
    B.adjust(brief, "level", "the current board is open: it has no walls or holes to remove (the blocks are the only "
                             "things in each other's way), so the board is kept.")


_FROZEN = re.compile(r"\b(keep|leave|preserve|retain|with|while keeping)\b[^.;]{0,40}\b(every|all|each)\b[^.;]{0,40}"
                     r"\b(position|positions|placement|placements|exactly|unchanged|as (it is|they are))\b"
                     r"|\bexactly the same\b[^.;]{0,30}\b(blocks?|positions?|layout|board)\b"
                     r"|\b(blocks?|positions?|layout|board)\b[^.;]{0,40}\bexactly (the same|as (it is|they are)|where)\b", re.I)


_RELATIVE = re.compile(r"\b(harder|easier|more|less|fewer|bigger|smaller|longer|shorter|again|another|darker|lighter|"
                       r"brighter|warmer|cooler|faster|slower|closer|further|extra|add|one more|increase|decrease|undo|"
                       r"revert|swap|toggle|different)\b", re.I)


def _repeat_of(prompt: str, files: list[str], current: dict, history: list[dict] | None) -> bool:
    """Whether an edit is the very request that made the version it edits (an absolute one: "set
    the background to light blue", not "make it harder"), with no new file."""
    if not history:
        return False
    norm = lambda t: re.sub(r"\s+", " ", t.strip().lower())
    used = {a["file"] for a in current.get("assets", [])} | {current.get("visuals", {}).get("background_image"),
                                                           current.get("audio", {}).get("music")}
    return norm(prompt) == norm(history[0]["prompt"]) and not _RELATIVE.search(prompt) and all(f in used for f in files)


_NUM = r"(\d+(?:\.\d+)?|one|two|three|four|five|half a|a)"
_NUMS = {"one": 1.0, "two": 2.0, "three": 3.0, "four": 4.0, "five": 5.0, "half a": 0.5, "a": 1.0}
_HOLD_MORE = re.compile(rf"\b(extend|lengthen|longer|add|hold)\w*\b[^.;]{{0,70}}\b(hold|victory|win|result|ending|completed|cleared)\b"
                        rf"[^.;]{{0,60}}\bby\s+{_NUM}\s*(s|sec|secs|seconds?)\b", re.I)
_INTRO_LESS = re.compile(rf"\b(remove|cut|trim|shorten|drop|take)\w*\b[^.;]{{0,20}}\b{_NUM}\s*(s|sec|secs|seconds?)\b[^.;]{{0,50}}"
                         rf"\b(opening|intro|hook|start|still)\b", re.I)


def _no_timing_drift(brief: dict, current: dict, parts: dict[str, float]) -> None:
    """The model often copies the current opening and hold lengths back as numbers (2.57 s read as
    2.6): a value within a rounding step of what the ad already has is no change."""
    sq, cur = brief["sequence"], current["sequence"]
    for key, part in (("intro_s", "intro"), ("hold_s", "result_hold")):
        new, old = sq.get(key), cur.get(key)
        now = old if old is not None else parts.get(part)
        if new is not None and now is not None and abs(new - now) <= 0.1:
            sq[key] = old
    if sq.get("intro_s") == cur.get("intro_s") and sq.get("hold_s") == cur.get("hold_s"):
        brief["changed"] = [g for g in brief["changed"] if g != "sequence.timing"]


def _timing_by_numbers(brief: dict, prompt: str, parts: dict[str, float]) -> None:
    """"Extend the victory hold by two seconds" and "remove one second of the opening" are worked
    out from the version's real part lengths (the model only sees them as text): the held result
    becomes what it is now plus 2 s, the still opening what it is now minus 1 s."""
    if not parts:
        return
    num = lambda t: _NUMS.get(t.lower(), None) if not t[0].isdigit() else float(t)
    sq, done = brief["sequence"], []
    m = _HOLD_MORE.search(prompt)
    if m:
        sq["hold_s"] = round(parts.get("result_hold", 0.0) + num(m.group(3)), 2)
        done.append(f"the held result: {parts.get('result_hold', 0.0):g} s -> {sq['hold_s']:g} s")
    m = _INTRO_LESS.search(prompt)
    if m and parts.get("intro", 0.0) > 0:
        sq["intro_s"] = round(max(0.0, parts["intro"] - num(m.group(2))), 2)
        done.append(f"the still opening: {parts['intro']:g} s -> {sq['intro_s']:g} s")
    if not done:
        return
    if "sequence.timing" not in brief["changed"]:
        brief["changed"].append("sequence.timing")
    brief["changed"] = [g for g in brief["changed"] if g != "pacing.length"]
    row = B.control(brief, "sequence")
    row["plan"] = "; ".join(done) + "; every other part keeps its length, so the ad's length changes by the difference."
    row["status"] = "applied"


def _history_lines(history: list[dict]) -> str:
    lines = []
    for v, par in zip(history, history[1:] + [None]):
        if par is None:
            lines.append(f"- v{v['n']}: the original ({v['prompt'][:120]!r})")
            continue
        groups = B.changed_groups(par["brief"], v["brief"])
        lines.append(f"- v{v['n']} (from v{par['n']}): {v['prompt'][:120]!r}; changed: "
                     + (", ".join(B.GROUP_NAMES.get(g, g) for g in groups) or "nothing"))
    return "\n".join(lines)


_UNDO = re.compile(r"\b(undo|undoes|revert\w*|roll(ed|s)? back|go back|put back|restore\w*|bring back|reverse)\b", re.I)
_UNDO_TARGETS = (("audio.music", ("music", "track", "song", "soundtrack")),
                 ("audio", ("sound effect", "sound effects", "sfx")),
                 ("assets", ("logo", "picture", "image", "asset", "badge", "button", "icon", "sticker", "cursor")),
                 ("concept.*", ("caption", "headline", "title", "text", "copy", "hook", "wording")),
                 ("visuals.colours", ("colour", "color", "colours", "colors")),
                 ("visuals.background", ("background",)),
                 ("level.*", ("level", "board", "door", "gate", "wall")),
                 ("format", ("format", "square", "aspect")))


def _undo(brief: dict, prompt: str, current: dict, history: list[dict]) -> None:
    """"Undo the music replacement" restores what the most recent edit that changed the music
    replaced, and only that: found in the version chain, never guessed, and never the whole
    original. With no thing named, the version's own last edit is undone."""
    if not _UNDO.search(prompt) or len(history) < 2:
        return
    # what to undo is named in the clause that says undo, not in the ones that say what to keep;
    # "do not undo the caption correction" keeps it
    negated = re.compile(r"\b(not|n't|never|without|no)\s+(\w+\s+)?(undo\w*|revert\w*|roll\w* back|restor\w*|go back|reverse)\b")
    clauses = [c for c in re.split(r"[.;!?,]|\bbut\b|\band\b", prompt.lower()) if _UNDO.search(c) and not negated.search(c)]
    if not clauses:
        return
    text = " ".join(clauses)
    want = [g for g, words in _UNDO_TARGETS if B._has_word(text, words)]
    pairs = list(zip(history, history[1:]))  # (version, its parent), newest first
    if not want:
        want = B.changed_groups(pairs[0][1]["brief"], pairs[0][0]["brief"])
    undone = []
    for pattern in want:
        for v, par in pairs:
            groups = [g for g in B.changed_groups(par["brief"], v["brief"])
                      if g == pattern or (pattern.endswith(".*") and g.startswith(pattern[:-1]))]
            if not groups:
                continue
            for g in groups:
                for path in B.GROUPS[g][1]:
                    B._set(brief, path, copy.deepcopy(B._get(par["brief"], path)))
                if g not in brief["changed"]:
                    brief["changed"].append(g)
            undone.append(f"{', '.join(B.GROUP_NAMES.get(g, g) for g in groups)} back to v{par['n']}'s (undoing v{v['n']})")
            break
    if not undone:
        B.adjust(brief, "unchanged", "nothing to undo: no earlier edit of this creative changed that.", status="not_supported")
        return
    for g in brief["changed"]:  # what was undone was asked: no "not asked for" note on it
        row = B.control(brief, B.GROUPS[g][0]) if g in B.GROUPS else None
        if row is not None and any(g == p or (p.endswith(".*") and g.startswith(p[:-1])) for p in want):
            row["asked"] = row.get("asked") or prompt.strip()
            if row.get("why"):
                row["why"] = re.sub(r"[^.;]*not asked for; chosen to fit the request \(say so to keep the game's own\)\.\s*",
                                    "", row["why"]).strip() or None
            if not row.get("why") and row["status"] == "adjusted":
                row["status"] = "applied"
    B.adjust(brief, "unchanged", "undone: " + "; ".join(undone) + "; everything else stays as it is now.", status="applied")


_NEW_LEVEL = re.compile(r"\b(new|different|another|fresh)\s+(level|board|puzzle|layout)\b|\bregenerat\w*", re.I)


def _recolour_keeps_board(brief: dict, prompt: str, current: dict) -> None:
    """In an edit, "make the red block purple" is a repaint of the red slot (block and gate), not a
    new level: changing the level's colour list would generate another board. Unless the prompt
    asks for a new level, the board is kept and each colour that was swapped is repainted."""
    old, new = current["level"]["colours"], brief["level"]["colours"]
    if old == new or "level.colours" not in brief["changed"] or _NEW_LEVEL.search(prompt):
        return
    if any(g in brief["changed"] for g in ("level.blocks", "level.size", "level.shape", "level.pieces", "level.style",
                                           "level.difficulty", "level.moves", "level.source")):
        return  # the prompt describes another board (its blocks, size, shape...): the colours are that board's
    if not old or len(old) != len(new):
        return  # no colours named before, or more or fewer now: a different board on purpose
    gone, came = [c for c in old if c not in new], [c for c in new if c not in old]
    if len(gone) != len(came):
        return
    swapped = list(zip(gone, came))
    brief["level"]["colours"] = list(old)
    brief["changed"] = [g for g in brief["changed"] if g != "level.colours"]
    shown = {e["slot"]: e for e in brief["visuals"]["blocks"]}
    for a, b in swapped:
        if a not in shown:
            brief["visuals"]["blocks"].append({"slot": a, "hex": B.GAME_HEX[b], "name": B.COLOUR_WORDS[b]})
    if swapped and "visuals.colours" not in brief["changed"]:
        brief["changed"].append("visuals.colours")
    row = B.control(brief, "level")
    row["plan"] = "The board is kept: block positions, gates and the moves stay as they are."
    row["status"] = "default" if row["status"] == "applied" else row["status"]
    B.adjust(brief, "visuals", "a colour change on this creative repaints the colour (the block and its gate together), so "
                               "the board, the path and the moves stay exactly as they were.", status="applied")


_FIRST_MOVE = re.compile(r"\b(first move|very first|first drag|first thing|opening move|start(s|ing)? (with|by)|begin(s|ning)? (with|by)|open(s|ing)? (with|by))\b", re.I)


def _relative_order(brief: dict, prompt: str) -> None:
    """"Blue exits before yellow" is an order between two blocks, not "blue's exit is the video's
    first drag": a step marked "first" is relaxed to "next" unless the prompt speaks of the first
    move itself."""
    evs = brief["gameplay"]["events"]
    if evs and evs[0]["when"] == "first" and re.search(r"\bbefore\b", prompt, re.I) and not _FIRST_MOVE.search(prompt):
        evs[0]["when"] = "next"


_ASIDE = r"(aside|out of the way|away|to the side|to one side|out of the path|out of its way|out of their way)"
_MOVE = r"(mov\w*|push\w*|slid\w*|shift\w*|nudg\w*|drag\w*|clear\w*|get\w*)"
_FIRST_ASIDE = re.compile(rf"\b(first|start(s|ing)? by|begin(s|ning)? by|open(s|ing)? by)\b[^.;]{{0,30}}\b{_MOVE}\b[^.;]{{0,40}}\b{_ASIDE}\b"
                          rf"|\b{_MOVE}\b[^.;]{{0,40}}\b{_ASIDE}\b[^.;]{{0,12}}\bfirst\b", re.I)


def _blocking_move(brief: dict, prompt: str) -> None:
    """"An early move sends the yellow block into a position that blocks the green block's route":
    a wrong move by a named block that gets in another block's way, as an event (the model read it
    as a plain mistake in 3 of 48 audited prompts, 2026-10-15)."""
    from . import audit
    a = audit.asked(prompt)
    if not a["blocks_by"]:
        return
    mover, victim = a["blocks_by"]
    evs = brief["gameplay"]["events"]
    if any(e["action"] == "blocks" and e["block"].get("colour") == mover for e in evs):
        return
    early = re.search(r"\b(first|initially|early|opening|at the start|begins?|starts?)\b", prompt, re.I) is not None
    ev = {"block": {"colour": mover, "which": "any", "all": False}, "action": "blocks",
          "when": "first" if early and not evs else "next"}
    if victim:
        ev["by"] = victim
    evs.insert(0, ev)
    if "gameplay.events" not in brief["changed"]:
        brief["changed"].append("gameplay.events")
    row = B.control(brief, "gameplay")
    row["asked"] = row["asked"] or prompt.strip()
    if row["status"] == "default":
        row["status"] = "applied"


def _mistake_count_from_words(brief: dict, prompt: str) -> None:
    """"One unhelpful repositioning move", "two wrong moves", "an obvious but unhelpful move": the
    mistake count the words give, when the model left it at the ending's default (P6-c had none
    played, 2026-10-15). A clean-solve wording keeps its zero."""
    from . import audit
    a = audit.asked(prompt)
    gp = brief["gameplay"]
    if a["mistakes"] is None or gp["mistakes"] is not None:
        return
    named = sum(e["action"] in ("stuck", "blocks") for e in gp["events"])
    if a["mistakes"] <= named and a["mistakes"] > 0:
        return  # the named wrong moves are the mistakes
    gp["mistakes"] = a["mistakes"]
    if "gameplay.mistakes" not in brief["changed"]:
        brief["changed"].append("gameplay.mistakes")
    row = B.control(brief, "gameplay")
    row["asked"] = row["asked"] or prompt.strip()
    if row["status"] == "default":
        row["status"] = "applied"


def _first_aside(brief: dict, prompt: str) -> None:
    """"First moving a blocking piece aside, then clearing the blocks": the video's first drag is
    the move aside, not merely a move somewhere before the exits (an edit put it at drag 3 while
    two blocks had already left, 2026-10-15)."""
    if not _FIRST_ASIDE.search(prompt):
        return
    evs = brief["gameplay"]["events"]
    moves = [e for e in evs if e["action"] == "moves"]
    if moves and evs[0] is moves[0]:
        if evs[0]["when"] != "first":
            evs[0]["when"] = "first"
    elif not evs:
        evs.insert(0, {"block": {"colour": None, "which": "any", "all": False}, "action": "moves", "when": "first"})
    else:
        return  # other named steps come first, or the move aside is among them later: the request's own order
    if "gameplay.events" not in brief["changed"]:
        brief["changed"].append("gameplay.events")


_FRESH_LEVEL = re.compile(r"^\W*(create|make|build|design|generate|give me|i want|i need)\b[^.;:]{0,90}\b(level|board|puzzle)\b", re.I)
_STYLE_ASKED = {"symmetric": re.compile(r"symmetr|mirror", re.I),
                "packed": re.compile(r"packed|crowded|limited (free |empty )?(space|room)|little (free |empty )?(space|room)|compact|cramped|dense|full board|tight", re.I),
                "colourful": re.compile(r"colou?rful|every colou?r|all (the )?colou?rs|rainbow", re.I),
                "spacious": re.compile(r"spacious|room to move|plenty of|enough (free |empty )?space|open board|not crowded|lots of (free |empty )?(space|cells)|empty cells", re.I)}
_LEVEL_RESET = ("level.size", "level.blocks", "level.colours", "level.moves", "level.pieces", "level.style", "level.shape",
                "level.difficulty")


def _fresh_level(brief: dict, prompt: str, current: dict) -> None:
    """An edit that opens with "Create a ... level ..." describes a new level in full: the level
    settings it does not mention go back to the tool's defaults instead of staying as the earlier
    level had them (a "six colored blocks" edit kept an earlier mirror style, palette and piece set
    and showed four colours, 2026-10-15). The rest of the ad (captions, pictures, look) still stays."""
    # the opening clause only, and not one that keeps the level: "Make it 30 seconds instead of 45, keep the
    # same level and play" matched on "Make ... level" and threw the level away (2026-10-18)
    first = re.split(r"[.;:!?\n]|,\s*(?:but|and|then|keep|keeping|same|while)\b|\b(?:but|however|except|while)\b", prompt, 1)[0]
    m = _FRESH_LEVEL.search(first)
    if m is None or re.search(r"\b(keep|keeps|keeping|same|unchanged|preserve|existing|current)\b", m.group(0), re.I) \
            or brief["level"].get("edit") or brief["level"]["source"] == "shipped":
        return
    default = B.default_brief()["level"]
    reset = []
    for g in _LEVEL_RESET:
        if g in brief["changed"] or B._evidence(g, prompt, brief) is None:
            continue  # asked for by this request (a kept "narrow centre" the model did not re-declare) or changed
        for path in B.GROUPS[g][1]:
            key = path[-1]
            if B._get(brief, path) != default[key]:
                B._set(brief, path, copy.deepcopy(default[key]))
                reset.append(g)
    # a look the earlier level had ("symmetric") stays only when this request asks for it
    style = brief["level"].get("style") or []
    kept = [st for st in style if st in _STYLE_ASKED and _STYLE_ASKED[st].search(prompt)]
    if kept != style:
        brief["level"]["style"] = kept
        reset.append("level.style")
    reset = list(dict.fromkeys(reset))
    if reset:
        brief["changed"] += [g for g in reset if g not in brief["changed"]]
        brief["assumptions"].append("The request describes a new level, so " + ", ".join(B.GROUP_NAMES.get(g, g) for g in reset)
                                    + " are not carried over from the earlier level; the rest of the ad stays as it was.")


_COLOURED_N = re.compile(r"\b(two|three|four|five|six|seven|[2-7])\s+(?:different(?:ly)?[\s-]*)?(?:colou?red|colou?r|colou?rful)\s+(?:blocks?|pieces?)\b", re.I)
_COLOUR_ORDER = ("Red", "Blue", "Green", "Yellow", "Purple", "Orange", "DarkGreen")


def _coloured_count(brief: dict, prompt: str) -> None:
    """"Six coloured blocks" is six blocks, each in its own colour: with no palette named, the
    board's colours are the colours the events name plus the game's next ones, one per block (a
    six-block board showed four colours, 2026-10-15). On a mirrored board pairs share a colour,
    so the count stays and the row says how many colours it can show."""
    m = _COLOURED_N.search(prompt)
    if not m:
        return
    n = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}.get(m.group(1).lower()) or int(m.group(1))
    lv = brief["level"]
    if lv["colours"] and len(lv["colours"]) >= n:
        return  # a palette the request names itself
    if "symmetric" in (lv.get("style") or []):
        B.adjust(brief, "level", f"{n} blocks on a mirrored board show at most {n // 2 + 1} colours (mirror pairs share a "
                                 f"colour), so they cannot be {n} different colours.")
        return
    named = [e["block"]["colour"] for e in brief["gameplay"]["events"] if e["block"].get("colour")]
    named += [e["by"] for e in brief["gameplay"]["events"] if e.get("by")]
    colours = list(dict.fromkeys(named + list(lv["colours"]) + list(_COLOUR_ORDER)))[:n]
    lv["colours"] = colours
    if lv["blocks"] is None:
        lv["blocks"] = n
        if "level.blocks" not in brief["changed"]:
            brief["changed"].append("level.blocks")
    if "level.colours" not in brief["changed"]:
        brief["changed"].append("level.colours")
    brief["assumptions"].append(f"\"{m.group(0)}\" is read as {n} blocks, each in its own colour: "
                                + ", ".join(c.lower() for c in colours) + ".")


_REPOSITION_N = re.compile(r"\b(?:at least|minimum of|min\.?|a minimum of)?\s*(two|three|four|five|2|3|4|5)\s+"
                           r"(?:repositioning|rearrang\w*|set-?up|blocking|preparatory|clearing|moving-aside|move-aside)"
                           r"\s+(?:moves?|drags?|steps?)\b", re.I)


def _repositioning_count(brief: dict, prompt: str) -> None:
    """"At least two repositioning moves" names the tool's hard band: a medium board has one
    repositioning drag. The row says what the asked difficulty gives instead of a vague promise."""
    m = _REPOSITION_N.search(prompt)
    if not m:
        return
    n = {"two": 2, "three": 3, "four": 4, "five": 5}.get(m.group(1).lower()) or int(m.group(1))
    d = brief["level"]["difficulty"]
    if n >= 2 and d in ("easy", "medium"):
        B.adjust(brief, "level", f"{n} repositioning drags (blocks moved aside before they can leave) is what the tool's "
                                 f"hard band gives; a {d} board has {'one' if d == 'medium' else 'none'}. The level is "
                                 f"{d} as asked, so expect {'one' if d == 'medium' else 'no'} such drag; ask for a hard "
                                 f"level for two or more.")


_LOCK_PLAY = re.compile(r"\b(every|each|all)\s+(block\s+)?(trajector\w*|gameplay pixels?|object coordinates)\b"
                        r"|\b(any|every) frame of the (creative|video|ad)\b|\b(complete|whole|entire) video exactly\b"
                        r"|\bsolution sequence\b|\b(do not|don't|never) change the (board|level|moves)\b", re.I)
_PLAY_GROUPS = ("level.", "gameplay.", "pacing.length", "pacing.tempo", "pacing.curve")


def _impossible_locks(brief: dict, prompt: str, current: dict) -> None:
    """An edit that asks to change the puzzle (the board, its difficulty, the moves) and, in the
    same breath, to keep the board, the moves and every frame exactly as they are cannot do both.
    Nothing is changed; the brief says what contradicts what, and what could be relaxed."""
    groups = [g for g in brief["changed"] if g.startswith(_PLAY_GROUPS)]
    if not groups or not _LOCK_PLAY.search(prompt):
        return
    for g in groups:
        for path in B.GROUPS[g][1]:
            B._set(brief, path, copy.deepcopy(B._get(current, path)))
    brief["level"]["edit"] = current["level"].get("edit")
    brief["changed"] = [g for g in brief["changed"] if g not in groups]
    asked = ", ".join(dict.fromkeys(B.GROUP_NAMES.get(g, g) for g in groups))
    B.adjust(brief, "unchanged", f"the request contradicts itself: changing {asked} needs a different board, different "
                                 f"moves or a different clock, and with them other gameplay frames, but it also asks to "
                                 f"keep the board, the moves and every frame exactly as they are. Nothing was changed; "
                                 f"say which may change (for example 'the moves may change').", status="not_supported")


def _relative_difficulty(brief: dict, prompt: str, current: dict) -> None:
    """"Make it harder" edits the level the user is looking at (the closest board that rates
    harder), even when its brief already says hard; never a new take of the same level."""
    d = B.relative_difficulty(prompt)
    if d is None:
        return
    if _FROZEN.search(prompt):
        # every block and gate kept exactly = the puzzle kept: it cannot rate otherwise
        brief["level"]["difficulty"] = current["level"]["difficulty"]
        brief["level"]["edit"] = current["level"].get("edit")  # exactly the current level: nothing to make
        brief["changed"] = [g for g in brief["changed"] if g != "level.difficulty"]
        B.adjust(brief, "level", f"with every block and gate kept exactly where it is, the puzzle is the same puzzle: "
                                 f"it cannot be made {d} without moving something. Allow a small change ('move a block "
                                 f"or two') or ask for a new level.", status="not_supported")
        return
    brief["level"]["edit"] = {"dir": d, "of": None}  # `of` is set to the version it is made from
    if "level.difficulty" not in brief["changed"]:
        brief["changed"].append("level.difficulty")
    order = ["easy", "medium", "hard"]
    old, new = current["level"]["difficulty"], brief["level"]["difficulty"]
    if new in order and old in order and (order.index(new) - order.index(old)) * (1 if d == "harder" else -1) < 0:
        brief["level"]["difficulty"] = old  # the model moved the other way
    row = B.control(brief, "difficulty_pacing")
    row["asked"] = row["asked"] or prompt.strip()
    row["plan"] = (f"the same board, changed as little as possible until it rates {d} than now"
                   + (f" (aiming for {brief['level']['difficulty']})" if brief["level"]["difficulty"] != old else ""))
    if row["status"] == "default":
        row["status"] = "applied"


def plan(prompt: str, client=None, uploads: dict[str, Path] | None = None, sprites: set[str] | None = None,
         current: dict | None = None, available: dict[str, Path] | None = None, inventory: str | None = None,
         references: dict[str, Path] | None = None, analyser=None, log=None, history: list[dict] | None = None,
         parts: dict[str, float] | None = None, route: str | None = None) -> dict:
    """A checked brief for a prompt. With `current`, the prompt edits that brief: only what the
    prompt asks to change may change. uploads: the image files attached to this prompt (offered
    to the model as assets); available: every uploaded image (an edit keeps the ones its version
    uses); references: attached files to analyse first (reference images and videos, brief p.6),
    with `analyser` (reference.analyse) reading each one. route: the edit's route as text (route.text),
    decided in code before the model; it is given to the model with the edit. Returns the brief,
    with `planner` notes."""
    from . import llm, reference
    client = client or llm.planner_client()
    files = sorted(uploads or {})
    available = {**(available or {}), **(uploads or {})}
    user = f"REQUEST:\n{prompt.strip()}\n\nUPLOADED FILES: {', '.join(files) if files else 'none'}"
    analyses = []
    for name, path in sorted((references or {}).items()):
        if log:
            log(f"reading the reference {name}...")
        # a video is read for this request: the reading plan comes from this planner's own model
        a = analyser(Path(path)) if analyser is not None else reference.analyse(Path(path), log=log, prompt=prompt, planner=client)
        analyses.append(a)
        if log:
            log("  " + reference.summary(a))
    if analyses:
        user += ("\n\nREFERENCE FILES (analysed before you; use them as the instructions say, a video is never an "
                 "asset):\n" + "\n".join(reference.notes_text(a) for a in analyses))
    system = SYSTEM
    if current is not None:
        # the fields only: the previous version's reasons and notes would leak into the edit
        shown = {k: v for k, v in current.items() if k not in ("planner", "controls", "assumptions", "summary")}
        if (shown.get("gameplay") or {}).get("prefix"):  # the kept moves are the engine's, not a setting
            shown["gameplay"] = {k: v for k, v in shown["gameplay"].items() if k != "prefix"}
        user = EDIT + json.dumps(shown, indent=1) + "\n\nEDIT " + user
        if inventory:
            user += ("\n\nTHINGS IN THIS AD NOW (what the request may point at; if it asks to change or remove "
                     "something the ad does not have, say so in that control's row):\n" + inventory)
        if history and len(history) > 1:
            user += "\n\nEARLIER VERSIONS (newest first; what each edit changed):\n" + _history_lines(history)
        if route:
            user += "\n\n" + route
    t0 = time.time()
    if current is not None and _repeat_of(prompt, files, current, history):
        # the exact request that made this version: applying it again changes nothing (no drift)
        brief = copy.deepcopy(current)
        brief["changed"], brief["assumptions"] = [], []
        brief["summary"] = "The same request as the one that made this version."
        for row in brief["controls"]:
            row.update(asked=None, why=None, engine=[], status="default", plan="")
        B.adjust(brief, "unchanged", f"this exact request is what made v{history[0]['n']}, and it is already applied; "
                                     f"applying it again changes nothing.", status="not_supported")
        brief["planner"] = {"model": None, "seconds": 0.0, "prompt": prompt.strip(), "edit": True, "restored": [],
                            "references": []}
        return brief
    raw = _ask(client, system, user)
    _only_mentioned_uploads(raw, prompt, available, current, attached=files)
    # Only what the prompt asks to change is taken; everything else keeps its default (a new ad)
    # or its current value (an edit). The model may not fill unasked fields, such as copy.
    base = current if current is not None else B.check(B.default_brief())
    brief, restored = B.merge(base, B.check(raw, available, sprites), prompt, attached=files)
    changed = brief["changed"]
    brief = B.check(brief, available, sprites)
    brief["changed"] = changed
    # A change the model read from the request but the merge did not take is shown as such, not
    # as "applied": the user must not see a promise the engine will not keep.
    declared = set(raw.get("changed") or [])
    for r in restored:
        g, _, why = r.partition(": ")
        if g in declared and g in B.GROUPS and not g.startswith("assets"):
            B.adjust(brief, B.GROUPS[g][0], f"{B.GROUP_NAMES.get(g, g)}: read from the request, but not applied ({why}).")
            if g in ("level.size", "level.blocks", "pacing.length", "gameplay.clock_left"):
                B.drop_numbers(brief, g)
    if current is None and brief["level"].get("changes"):
        brief["level"]["changes"] = []  # a new ad has no current board to change
        brief["changed"] = [g for g in brief["changed"] if g != "level.changes"]
    _own_taste(brief, changed)
    B.plain_texts(brief)
    _spacious(brief, prompt)
    _paced_moves(brief, prompt)
    _gate_sides(brief, prompt)
    _one_gate_only(brief, prompt, current)
    _generous_clock(brief, prompt, current)
    _what_failure_is(brief, prompt)
    _mid_level_start(brief, prompt, current)
    _no_captions(brief, prompt)
    _exact_sequence(brief, prompt)
    _one_of_its_kind(brief)
    _art_limits(brief, prompt, files)
    _reference_files(brief, prompt, analyses, current)
    if analyses:
        from . import imageref
        image_roles = imageref.apply(brief, prompt, analyses, current)  # the image's role and what it gives (brief p.6)
        if current is None and any(a.get("kind") == "video" for a in analyses):
            from . import videoref
            videoref.apply(brief, prompt, analyses)  # what the video's reading focus allows (core requirement 4)
    _music_from_attachment(brief, prompt, files)
    _block_art(brief, prompt, current, files)
    _no_transitions(brief, prompt)
    _still_opening(brief, prompt)
    _missing_attachment(brief, prompt, files, current)
    _one_background(brief, prompt, current)
    _no_border(brief, prompt, current, files)
    if not any(r["status"] == "not_supported" and ("on a block or a door" in (r.get("why") or "")
                                                   or "no decorative border" in (r.get("why") or ""))
               for r in brief["controls"]) and not _replace_everywhere(brief, prompt, files, current):
        _obstacle_picture(brief, prompt, files)
        _place_unplaced(brief, prompt, files, current)
        _note_guessed_slot(brief, prompt, files, current)
    _relative_order(brief, prompt)
    _first_aside(brief, prompt)
    _blocking_move(brief, prompt)
    _mistake_count_from_words(brief, prompt)
    _repositioning_count(brief, prompt)
    if current is not None:
        _fresh_level(brief, prompt, current)
    _coloured_count(brief, prompt)
    if current is None:
        _reference_carries(brief, prompt, analyses)
    if current is not None:
        _undo(brief, prompt, current, history or [])
        _no_timing_drift(brief, current, parts or {})
        _timing_by_numbers(brief, prompt, parts or {})
        _recolour_keeps_board(brief, prompt, current)
        _no_obstacles_to_remove(brief, prompt, current)
        _relative_difficulty(brief, prompt, current)
        _impossible_locks(brief, prompt, current)
    if brief["language"] != "en":
        _translate_defaults(brief, client)
    else:
        brief["visuals"]["names"], brief["visuals"]["names_src"] = {}, {}
    if analyses:
        for a, r in zip(analyses, image_roles):
            if r is not None:
                a["role"] = r
    brief["planner"] = {"model": getattr(client, "last_model", None), "seconds": round(time.time() - t0, 1),
                        "prompt": prompt.strip(), "edit": current is not None, "restored": restored,
                        "references": analyses}
    return brief


def _reference_files(brief: dict, prompt: str, analyses: list[dict], current: dict | None) -> None:
    """A reference file is read, not placed: an analysed image stays out of the ad's pictures unless
    the request asks to put it somewhere; a video never goes in; a file that could not be read is
    not guessed about."""
    from . import reference
    if not analyses:
        return
    place = reference.asks_placement(prompt)
    used_before = {a["file"] for a in (current or {}).get("assets", [])}
    for a in analyses:
        name = a["file"]
        if a.get("error"):
            brief["assets"] = [x for x in brief["assets"] if x["file"] != name or name in used_before]
            note = f"{name} could not be read ({a['error'][:100]}), so nothing was taken from it."
            if note not in brief["assumptions"]:
                brief["assumptions"].append(note)
            B.adjust(brief, "visuals", note)
            continue
        if a.get("kind") == "video" or not place:
            if any(x["file"] == name for x in brief["assets"]) and name not in used_before:
                brief["assets"] = [x for x in brief["assets"] if x["file"] != name]
                B.adjust(brief, "assets", f"{name} is a reference (its {'structure and' if a.get('kind') == 'video' else ''} "
                                          f"colours and mood were read), not a picture placed in the ad; say "
                                          f"'put it on the end card' or 'use it as the logo' to place it.", status="applied")
        row = B.control(brief, "visuals")
        if row["status"] == "default" and a.get("kind") == "image":
            row["status"] = "applied"
        if not any(name in (x or "") for x in brief["assumptions"]):
            brief["assumptions"].append("Read from " + reference.summary(a) + ".")
