"""Image-guided creative generation: a prompt plus a reference picture in, a new creative out (the case's core
requirement 3, case p.6; rules I1-I16 in ~/rollic-case/REQ3-IMAGE-GUIDED-RULES-2026-10-17.md), with its own evaluate /
feed back / revise loop. See workflows/__init__.py.

The input is a prompt AND a picture (no video: a video, with or without a picture, is the video-guided workflow). The
words say what to take; the picture is what gets read; a value the words state always wins. plan:
1. the request is read first: the planner's text model writes the image reading plan from the words and the
   picture's format facts only (imageread.reading_plan: the focus, the questions, what to ignore, what the request
   fixes; the word table is the fallback and the check);
2. the picture is read (imageread.read: Opus through the Claude CLI reads the whole picture once, strict JSON with
   the plan's questions on top, with the code's measures beside it; Gemini, then NVIDIA, with the video path's board
   read when Opus cannot), and the role is decided: the plan's focus decides the roles, the words the parts inside
   each (imageplan.decide, imageplan.reconcile: style, board, asset, modify);
3. the planner plans the brief from the words, told only what the picture shows and its role (imageplan.planner_view:
   no numbers, no palette, no caption words, so it cannot copy or half-take them);
4. code applies exactly what the roles allow (imageplan.apply: the board part by part with "<seen> -> <built>: <why>"
   for every clamp, the colours to the game's seven rendered slots, the measured look, the screen, never the picture's
   pixels, cells or caption words), and the captions are made to fit the ending (videoref.fit_captions).
make and revise_once run the shared engine (studio, review, audit) as the video-guided workflow does (its helpers are
imported, not copied: guided._carried, best_version, feedback, pin_reference, keep_stated, length_guard,
unchanged_texts, viewer_points); the evaluation adds the image rows (imageaudit.rows) to each version's checks after
studio.make, and their misses are fed back. At most two revisions; the final version is the best one, not the last.
No media model generates anything here: the only model calls are the planner's text model, the picture's reader and
the viewer's review (rule I15).
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from .. import brief as B
from .. import imageaudit, imageplan, imageread, llm, planner, review, route, studio
from . import guided
from .create import keep_asked

MAX_REVISIONS = 2  # evaluate, feed back, make again: at most two rounds after the first version
WORKFLOW = "image_guided"


def pictures(uploads: list[str]) -> list[str]:
    """The attached pictures (not videos, not music), in the order attached."""
    ups = studio.uploads()
    return [n for n in uploads if n in ups and not B.is_audio(n) and Path(n).suffix.lower() in studio.IMAGE_EXT]


SCREENSHOT_PX = 600  # a picture at least this big each way, with no placement words, is a reference (a screenshot, a render)
ENGLISH = frozenset("the a an and with in on of to this that it is for but its as from into one two three use same just make keep show "
                    "only more fewer less like new level board blocks block game play player clock time seconds then also not no "
                    "same design scenario colour color colours colors look ending win fail stop before after".split())


def is_english(prompt: str) -> bool:
    """Whether the words are English enough for the code's parsers (two of the common function words, or a very short
    all-ASCII ask)."""
    words = re.findall(r"[a-zA-Z']+", prompt or "")
    hits = len({w.lower() for w in words} & ENGLISH)
    return hits >= 2 or (hits >= 1 and len(words) <= 5) or (not re.search(r"[^\x00-\x7f]", prompt or "") and len(words) <= 3)


def looks_like_screenshot(name: str) -> bool:
    try:
        from PIL import Image
        with Image.open(studio.uploads()[name]) as im:
            return im.width >= SCREENSHOT_PX and im.height >= SCREENSHOT_PX
    except Exception:
        return False


def applies(prompt: str, uploads: list[str]) -> bool:
    """Whether a new creative is image-guided: no video is attached, a picture is, and the words make it a reference
    ("inspired by this image", "take the board from this screenshot", "as crowded as this one": imageplan.is_image_reference),
    OR (2026-10-19) the picture is screenshot-sized and the words do not place it ("put our logo on the end card" stays in
    the text workflow): a designer who attaches a board, in any language, means it as the reference (the owner's 07:49
    "Use the game's own look, but the red blocks become pink" with a picture attached was planned without the picture; the
    Turkish "Bu tahtayı aynen kullan" has no English cue at all)."""
    from .. import reference as R
    if any(n in studio.videos() for n in uploads):
        return False
    pics = pictures(uploads)
    if not pics:
        return False
    if imageplan.is_image_reference(prompt):
        return True
    return not R.asks_placement(prompt) and looks_like_screenshot(pics[0])


TRANSLATE_SYSTEM = ("You translate a creative brief for a Color Block Jam video ad into plain English for a parser. Keep every "
                    "number, unit, colour word, quoted caption (quoted, untranslated) and the order of the sentences; add nothing.")
TRANSLATE_SCHEMA = {"type": "object", "properties": {"english": {"type": "string"}}, "required": ["english"], "additionalProperties": False}


def english_prompt(prompt: str, client=None, log=None) -> str:
    """The request in English for the code's parsers (the transforms, the asks, the rows); the request itself when it is
    English already, or when no planner client can translate. The original is kept in the brief (prompt_original)."""
    if is_english(prompt):
        return prompt
    try:
        client = client or llm.planner_client()
        raw = client.complete(TRANSLATE_SYSTEM, "Translate: " + prompt.strip(), TRANSLATE_SCHEMA)
        text = json.loads(raw).get("english") if isinstance(raw, str) else (raw or {}).get("english")
        text = str(text or "").strip()
        if text and is_english(text):
            if log:
                log(f"the request is not in English; the parsers read this translation: \"{text[:140]}\"")
            return text
    except Exception as e:
        if log:
            log(f"the request could not be translated ({str(e)[:100]}); the parsers read it as it is")
    return prompt


def plan(log: studio.Log, prompt: str, uploads: list[str], reader=None) -> dict:
    """The brief of an image-guided creative: the picture read, the role decided, planned, applied (the module note).
    `reader`: the picture's reader (default reference.video_client())."""
    if not prompt.strip():
        raise ValueError("write a prompt first: it says what to take from the attached picture")
    pics = pictures(uploads)
    if not pics:
        raise ValueError("attach the reference picture: the image-guided workflow reads a picture with the prompt")
    all_ups = studio.uploads()
    ups = {n: all_ups[n] for n in uploads if n in all_ups}
    name = pics[0]
    log.begin("plan", "an image-guided creative: reading the picture, then the request...")
    rt = route.decide(prompt, manifest=None, uploads=sorted(ups), videos=[])
    log("route: " + route.summary(rt))
    if len(pics) > 1:
        log(f"{len(pics)} pictures are attached: {name} is the reference; the others are offered as pictures to place")
    client = llm.planner_client()  # one client: the reading plan and the brief come from the same planner model
    original = prompt
    prompt = english_prompt(prompt, client, log)
    try:
        facts = imageread.format_facts(all_ups[name])
    except Exception:
        facts = {}
    rplan = imageread.reading_plan(prompt, facts, client=client, log=log)
    log(f"reading plan ({rplan.get('source')}): focus {', '.join(rplan.get('focus') or []) or 'nothing'} ({rplan.get('level')}); "
        f"questions: {' | '.join(rplan.get('questions') or [])}")
    reading = imageread.read(all_ups[name], client=reader, log=log, plan=rplan)
    log("read: " + imageread.summary(reading))
    for line in reading.get("disagreements") or []:
        log(f"measured beside the reader: {line}")
    decision = imageplan.reconcile(imageplan.decide(prompt, reading), rplan, reading)
    log(f"role: {name} is used as {' and '.join(decision['roles']) or 'nothing'} ({'; '.join(decision['why']) or 'the words'})")
    view = imageplan.planner_view(reading, decision, prompt)
    brief = planner.plan(prompt, client=client, uploads=ups, sprites=studio.sprite_names(), current=None,
                         available=all_ups, inventory=None, references={name: all_ups[name]},
                         analyser=lambda p: view, log=None, history=None, parts=None, route=None)
    brief["planner"]["route"] = rt
    brief["planner"]["workflow"] = WORKFLOW
    if prompt != original:
        brief["planner"]["prompt_original"], brief["planner"]["prompt_english"] = original, prompt
    planner_lines = list(brief.get("assumptions") or [])
    prov = imageplan.apply(brief, prompt, reading, decision)
    for note in imageplan.reconcile_numbers(brief, prov, planner_lines) + imageplan.clear_invented_blocks(brief, prompt, prov):
        log(f"plan: {note}")  # H8: the plan's words say the picture's numbers; H15: no invented block colours
    bg = (prov.get("look") or {}).get("background") or []
    if decision.get("bg_hues") and len(bg) == 2 and "visuals.background" in (prov.get("set") or []):
        line = (f"the {'-to-'.join(decision['bg_hues'])} background the words describe is the picture's own, measured: "
                f"{bg[0]} to {bg[1]}")  # H9b
        imageplan._note(brief, line)
        log(f"plan: {line}")
    for note in imageplan.request_values(brief, prompt):  # the request's own values the planner may have missed (I4)
        log(f"from the request: {note}")
    for step in (lambda: [x for x in [imageplan.dark_plate(brief, prov)] if x],  # G5: a night background drawn unlit (its line)
                 lambda: imageplan.palette_choice(brief, prompt, prov),  # G12: which colours a palette word gives
                 lambda: imageplan.fill_play(brief, prompt, prov),  # G1: the gameplay carries the stated length
                 lambda: imageplan.time_out_left(brief, prompt),  # H20: a time-out's blocks left, or its limit said
                 lambda: imageplan.name_stuck(brief, prompt),  # G3: a stuck moment points at one piece
                 lambda: imageplan.honest_cascade(brief, prompt)):  # G6: a cascade as the game can play it
        for note in step():
            log(f"plan: {note}")
    from .. import videoref
    before_fit = dict(brief["concept"])
    for note in videoref.fit_captions(brief):  # no caption may claim what the ending does not show (rule I11)
        log(f"captions: {note}")
    for note in imageplan.keep_quoted(brief, prompt, before_fit):
        log(f"captions: {note}")
    for note in imageplan.sequence_matches(brief, prompt) + imageplan.cliffhanger_replay(brief, prompt):  # G13
        log(f"sequence: {note}")
    for note in imageplan.question_hold(brief, prompt, prov):  # H18: the question holds what the card would take
        log(f"sequence: {note}")
    if (brief.get("level") or {}).get("source") == "picture" and prov.get("board"):
        # a copied board has the moves it has (common with the video path, 2026-10-19): the play its solution needs against the
        # stated length, said at plan time; the loop then does not try to shorten (or lengthen) what the board cannot give
        fixed = set(videoref.stated(prompt, (), video=False))
        line = videoref.copied_board_pace(brief, prompt, fixed, prov, what="the picture's board")
        if line:
            log(f"plan: {line}")
    brief["planner"]["references"] = [imageplan.card_view(reading, decision, prov)]
    log(f"picture to creative: {name} as {' and '.join(prov['roles'])}; taken: {'; '.join(prov['taken']) or 'nothing'}")
    if prov.get("not_taken"):
        log(f"not taken: {'; '.join(prov['not_taken'])}")
    for line in prov.get("clamps") or []:
        log(f"built: {line}")
    log(f"planned by {brief['planner']['model']} in {brief['planner']['seconds']} s")
    return brief


PIECE_ORDER = ("small", "mixed", "varied", "long", "big")  # by the cells a piece covers (generate.AVG_CELLS)


def _resolver(resolve=None):
    return resolve or (lambda b: studio.resolve_level(b, studio.Log(lambda ln: None)))


def verdict(detail) -> str:
    """A row's verdict without its measures (H7b, 2026-10-18: S6's difficulty row read "12 drags ... medium-to-hard
    (asked: hard)" then "13 drags ..."): the text after the last "->", else the clause holding "(asked: ...)", else the
    whole detail; digits dropped, spaces folded."""
    d = str(detail or "")
    if "->" in d:
        d = d.rsplit("->", 1)[1]
    else:
        m = re.findall(r"[^;,:]*\(asked:[^)]*\)", d)
        if m:
            d = m[-1]
    return re.sub(r"\s+", " ", re.sub(r"[\d.]+", "", d)).strip().lower()


def _at_limit(v: dict) -> bool:
    from .. import videoref as V
    return (((v.get("brief") or {}).get("level") or {}).get("blocks") or 0) >= V.BLOCKS_RANGE[1]


def repeated_miss(a: dict, b: dict) -> dict | None:
    """A shared row (not an image row) that both versions missed with the same verdict, the level in the same limit
    state: the board's limit (H7, H7b)."""
    from .. import audit
    old = {(c.get("check"), verdict(c.get("detail"))) for c in audit.misses(a.get("checks") or [])}
    if _at_limit(a) != _at_limit(b):
        return None
    return next((c for c in audit.misses(b.get("checks") or []) if not str(c.get("check", "")).startswith("Image: ")
                 and (c.get("check"), verdict(c.get("detail"))) in old), None)


EVENT_SEEDS = 3  # more seeds tried when a planned step cannot play on the generated board (H17)
EVENT_PAIRS = 6  # stuck pairs (mover, blocker) tried on this board's colours after that


def keep_events(log: studio.Log, prompt: str, brief: dict, resolve=None) -> list[str]:
    """Every planned step plays on the board the take uses (H17, 2026-10-18: S1's "the red block stopped by a yellow
    block" could not play on its generated ring; the player dropped it silently, "0 mistakes", and the revision replanned
    the same): studio's own cannot-play check on the generated level; when a step cannot play, three more seeds, then
    the stuck step re-planned with this board's own colours (a single-block mover first, each blocker of another colour),
    then the stuck step dropped with its wrong move kept, said. Never an exception. Returns the notes."""
    from ..level import load_level
    resolve = _resolver(resolve)
    gp = brief["gameplay"]
    if not gp.get("events"):
        return []

    def why_not() -> str | None:
        try:
            return studio._cannot_play(brief, resolve(brief)[0])
        except Exception as e:
            return f"the board could not be checked ({str(e)[:120]})"
    why = why_not()
    if why is None:
        return []
    seed0 = gp.get("seed") or 0
    for k in range(1, EVENT_SEEDS + 1):
        gp["seed"] = seed0 + k
        if why_not() is None:
            return [f"a planned step could not play on the first board ({why}); seed {seed0 + k} plays it"]
    gp["seed"] = seed0
    events0 = copy.deepcopy(gp["events"])
    stuck = [i for i, e in enumerate(events0) if e.get("action") == "stuck"]
    if stuck:
        try:
            level = load_level(resolve(brief)[0])
            counts: dict = {}
            for b in level.blocks:
                c = B.COLOURS[int(b.color)]
                counts[c] = counts.get(c, 0) + 1
        except Exception:
            counts = {}
        movers = sorted(counts, key=lambda c: (counts[c] != 1, B.COLOURS.index(c)))
        pairs = [(m, b) for m in movers for b in counts if b != m][:EVENT_PAIRS]
        for mover, blocker in pairs:
            evs = copy.deepcopy(events0)
            for i in stuck:
                evs[i]["block"] = dict(evs[i].get("block") or {}, colour=mover, which="any", all=False)
                evs[i]["by"] = blocker
            gp["events"] = evs
            if why_not() is None:
                line = (f"the planned stuck moment could not play on this board ({why}); it is played with this board's own "
                        f"blocks: the {B.COLOUR_WORDS[mover]} block heads for its gate and a {B.COLOUR_WORDS[blocker]} block "
                        f"is in the way")
                imageplan._note(brief, line)
                if "gameplay.events" not in brief.setdefault("changed", []):
                    brief["changed"].append("gameplay.events")
                return [line]
        gp["events"] = [e for i, e in enumerate(events0) if i not in stuck]
        if why_not() is None:
            line = (f"no stuck moment plays on this board ({why}); the wrong move is played as an ordinary one, without a "
                    f"blocker named")
            imageplan._note(brief, line)
            return [line]
    gp["events"] = events0
    line = f"a planned step cannot play on this board ({why}); the take reports it"
    imageplan._note(brief, line)
    return [line]


FALLBACK_ENDING = {"time_out": "near_fail", "cliffhanger": "near_fail", "near_fail": "win", "win": "win"}


def playable(log: studio.Log, prompt: str, brief: dict, resolve=None) -> list[str]:
    """The planned ending plays on the board the take uses (H11, 2026-10-18: S9's time-out had no creative, because the
    player found "the last block is one cell from its gate ... a time-out needs a last exit of at least two cells"):
    the player's plan is dry-run on the generated level (studio._plan with the seed the take uses); when it cannot play,
    three more seeds are tried (the generator colours and the player plans by the seed), then one more block, and when
    none plays, the nearest ending the words allow, said. Never an exception. Returns the notes."""
    from ..level import load_level
    from .. import videoref as V
    resolve = _resolver(resolve)
    gp, lv = brief["gameplay"], brief["level"]

    def plays() -> str | None:
        try:
            studio._plan(brief, load_level(resolve(brief)[0]), gp.get("seed") or 0)
            return None
        except Exception as e:  # the player's or the generator's own refusal
            return str(e).split(": ", 1)[-1][:200] or type(e).__name__
    why = plays()
    if why is None:
        return []
    ending = gp["ending"].replace("_", "-")
    seed0 = gp.get("seed") or 0
    for k in range(1, 4):
        gp["seed"] = seed0 + k
        if plays() is None:
            return [f"the first board could not play the {ending} ({why}); seed {seed0 + k} plays it"]
    gp["seed"] = seed0
    if lv.get("blocks") and lv["blocks"] < V.BLOCKS_RANGE[1] and lv.get("source") != "picture":  # a copied board is fixed
        lv["blocks"] += 1
        if plays() is None:
            return [f"the board could not play the {ending} ({why}); one more block ({lv['blocks']}) plays it"]
        lv["blocks"] -= 1
    to = FALLBACK_ENDING.get(gp["ending"], "win")
    if to == gp["ending"]:
        return [f"the board could not play the {ending} before the take ({why}); the take reports it"]
    gp["ending"] = to
    if to != "cliffhanger":
        gp["blocks_left"] = None
    line = (f"no board tried could play a {ending} ({why}), so the creative ends as a {to.replace('_', '-')}, the nearest "
            f"ending that plays")
    imageplan._note(brief, line)
    return [line]


def verify_pieces(log: studio.Log, brief: dict, resolve=None) -> list[str]:
    """The piece class the picture shows, tried first (imageplan.fit_board, H1), is checked on the board the take uses:
    when the generator could not place the count with it, one class smaller, said."""
    from .. import imageaudit as IA
    prov = brief.get("reference") or {}
    bd = prov.get("board") or {}
    read = (bd.get("seen") or {}).get("pieces")
    lv = brief["level"]
    if read not in imageplan.DEFINITE_PIECES or lv.get("pieces") != read or not lv.get("blocks"):
        return []
    resolve = _resolver(resolve)
    try:
        made = IA.made_level(resolve(brief)[0])["blocks"]
    except Exception:
        made = 0
    if made >= lv["blocks"] - 1:
        return []
    smaller = PIECE_ORDER[max(0, PIECE_ORDER.index(read) - 1)] if read in PIECE_ORDER else "mixed"
    lv["pieces"] = smaller
    line = f"the picture's {read} pieces could not all be placed ({made} of {lv['blocks']}), so {smaller} pieces are built"
    imageplan._note(brief, line)
    return [line]


def fit_fill(log: studio.Log, prompt: str, brief: dict, resolve=None) -> list[str]:
    """A packed board measured on the board the take will use (G17, 2026-10-17: B3's 9 mixed pieces were expected to cover
    69 % and covered 57 %): the level is generated through studio's own cached generator (the take loads the same one)
    and its fill measured; under the packed bar, once more with the pieces one class bigger (when the words do not state
    them) or one more block (within the limit), and the fuller board is kept, if its planned steps still play. The fill
    measured is kept for the packed row (imageaudit: a clamped count is judged against it). Returns the notes."""
    from .. import imageaudit as IA
    from .. import videoref as V
    prov = brief.get("reference") or {}
    bd = prov.get("board") or {}
    built = bd.get("built") or {}
    lv = brief["level"]
    if not built.get("packed") or "packed" not in (lv.get("style") or []):
        return []
    resolve = _resolver(resolve)
    try:
        fill = IA.made_level(resolve(brief)[0])["fill"]
    except Exception as e:
        log(f"fill: the board could not be measured before the take ({str(e)[:120]})")
        return []
    notes = []
    if fill < IA.PACKED_MADE:
        trial = copy.deepcopy(brief)
        tl = trial["level"]
        pieces = tl.get("pieces") or "mixed"
        if "pieces" not in V.stated(prompt) and pieces in PIECE_ORDER[:-1]:
            tl["pieces"] = PIECE_ORDER[PIECE_ORDER.index(pieces) + 1]
        elif (tl.get("blocks") or 0) < V.BLOCKS_RANGE[1]:
            tl["blocks"] = (tl.get("blocks") or 0) + 1
        if tl != lv:
            try:
                tpath = resolve(trial)[0]
                tfill = IA.made_level(tpath)["fill"]
                lost = studio._cannot_play(trial, tpath) if trial["gameplay"].get("events") else None
            except Exception:
                tfill, lost = 0.0, "not generated"
            if tfill > fill and not lost:
                notes.append(f"the board was {fill:.0%} full; with {tl['blocks']} {tl['pieces']} pieces it is {tfill:.0%}")
                brief["level"] = tl
                built.update(blocks=tl.get("blocks"), packed=True)
                fill = tfill
    built["fill_generated"] = round(fill, 2)
    seen = (bd.get("seen") or {})
    if fill < IA.PACKED_MADE and (seen.get("blocks") or 0) > (lv.get("blocks") or 0):
        occ = seen.get("fill")
        notes.append(f"the picture's {seen.get('blocks')} blocks fill " + (f"{occ:.0%}" if isinstance(occ, (int, float)) else "its board")
                     + f"; the tool's {brief['level'].get('blocks')} fill {fill:.0%} of {brief['level'].get('width')}x"
                       f"{brief['level'].get('height')}, the most it builds here")
    for line in notes:
        imageplan._note(brief, line)
    return notes


def keep_steps(log: studio.Log, before: dict, after: dict, resolve=None) -> list[str]:
    """A revision lever that changes the level must keep the planned steps playable (G17: B3's +blocks lever rebuilt the
    board and its second stuck moment could not be played): the new board is generated and checked with studio's own
    cannot-play check; when a step is lost, another board once (another seed), else the version before's board is kept."""
    lb, la = before["level"], after["level"]
    if la == lb or not after["gameplay"].get("events"):
        return []
    resolve = _resolver(resolve)
    try:
        why = studio._cannot_play(after, resolve(after)[0])
        if why:
            seed = after["gameplay"].get("seed") or 0
            after["gameplay"]["seed"] = seed + 1
            why2 = studio._cannot_play(after, resolve(after)[0])
            if not why2:
                return [f"the board change kept its planned steps on another board (seed {seed + 1})"]
            after["gameplay"]["seed"] = seed
            after["level"] = copy.deepcopy(lb)
            after["changed"] = [g for g in after.get("changed") or [] if not g.startswith("level.")]
            return [f"the board change would lose a planned step ({why}); the board is kept"]
    except Exception as e:
        log(f"revision: the new board could not be checked ({str(e)[:120]})")
    return []


def real_cut(log: studio.Log, prompt: str, brief: dict, resolve=None) -> list[str]:
    """Before the first take of a cliffhanger (G15): the level the take will use (studio.resolve_level: deterministic
    and cached, so the take loads the same one) is solved, and the cut is moved to the latest position where a remaining
    block is trapped (imageplan.cut_choice), the blocks left raised up to 3 when needed. With no such position, the board
    is made a little tighter once (two more blocks when the picture filled the count), else the plan says so. A count
    the request names itself ("before the last three blocks leave") is kept. Returns the notes."""
    from ..imageaudit import blocks_left_asked
    from ..level import load_level
    gp, lv = brief["gameplay"], brief["level"]
    if gp.get("ending") != "cliffhanger":
        return []
    resolve = resolve or (lambda b: studio.resolve_level(b, studio.Log(lambda ln: None)))
    prov = brief.get("reference") or {}
    asked = blocks_left_asked(prompt)
    k0 = asked or gp.get("blocks_left") or 2
    notes = []
    def choose(level):
        # the take's own planned path first (its wrong moves and hesitations), the bare solve as the fallback
        return imageplan.cut_choice_planned(level, k0, brief) or imageplan.cut_choice(level, k0)
    try:
        choice = choose(load_level(resolve(brief)[0]))
        if choice is None and not asked:
            bd = prov.get("board") or {}
            from .. import videoref as V
            if "blocks" in (bd.get("filled") or []) and (lv.get("blocks") or 0) + 2 <= V.BLOCKS_RANGE[1]:
                lv["blocks"] = lv["blocks"] + 2
                notes.append(f"the planned path shows no trapped block at the cut, so the board is made a little tighter: "
                             f"{lv['blocks']} blocks")
                choice = choose(load_level(resolve(brief)[0]))
    except Exception as e:  # the take still runs; the row measures it
        log(f"cut: the level could not be checked before the take ({str(e)[:120]})")
        return []
    q = (brief.get("concept") or {}).get("result") or "Can you see the move?"  # the tool's own question at the cut
    if choice is None:
        notes.append("the planned path shows no trapped block at the cut, so the question may have an easy answer; the "
                     "recording is measured")
    elif asked:
        if choice["left"] != asked:
            notes.append(f"the request asks to stop with {asked} blocks left; on this board a block is trapped only with "
                         f"{choice['left']} left, so the request's count is kept")
    elif choice["left"] != (gp.get("blocks_left") or 2) or gp.get("blocks_left") is None:
        gp["blocks_left"] = choice["left"]
        if "gameplay.blocks_left" not in brief.setdefault("changed", []):
            brief["changed"].append("gameplay.blocks_left")
        notes.append(f"the ad stops with {choice['left']} blocks left, where {choice['words']}, so \"{q}\" is a real choice")
    else:
        notes.append(f"at the cut with {choice['left']} blocks left, {choice['words']}, so \"{q}\" is a real choice")
    prov["cut"] = choice
    for line in notes:
        imageplan._note(brief, line)
    return notes


def evaluated(log: studio.Log, prompt: str, v: dict) -> dict:
    """The image rows added to a made version's checks (studio.make wrote the text and reference rows), saved."""
    vdir = studio.STUDIO / v["id"] / f"v{v['n']}"
    try:
        extra = imageaudit.rows(prompt, v["brief"], v, vdir)
    except Exception as e:  # never lose a made version over its evaluation
        log(f"image rows skipped: {e}")
        return v
    base = imageaudit.rejudge(prompt, v["brief"], [c for c in v.get("checks") or [] if not str(c.get("check", "")).startswith("Image: ")])
    for before, after in zip([c for c in v.get("checks") or [] if not str(c.get("check", "")).startswith("Image: ")], base):
        if before.get("status") != after.get("status"):
            log(f"image: {after['check']} is judged against the request's words here: {before['status']} -> {after['status']}")
    try:
        cov = imageaudit.coverage_rows(prompt, v["brief"], base + extra)
    except Exception as e:  # the coverage row is a report of the tool; it never loses a made version
        log(f"coverage row skipped: {e}")
        cov = []
    v["checks"] = base + extra + cov
    v["asked_prompt"] = prompt
    ev = v.setdefault("evaluation", {})
    ev["kind"] = "image"
    ev["what"] = ("image-guided: as text-to-creative, plus the image rows (the role, what was taken, the board's parts on "
                  "the made level, the look on the made frames, the screen, nothing copied, counted on the board)")
    ev["groups"] = list(dict.fromkeys(list(ev.get("groups") or []) + ["image"]))
    from .. import audit
    miss = audit.misses(extra)
    for c in miss:
        log(f"image: {c['check']}: failed ({c['detail']})")
    log(f"image rows: {len(extra) - len(miss)} of {len(extra)} met" + (f"; missed: {', '.join(c['check'] for c in miss)}" if miss else ""))
    (vdir / "version.json").write_text(json.dumps(v, indent=1, ensure_ascii=False))
    return v


def make(log: studio.Log, prompt: str, brief: dict, draft: bool = False, review_on: bool = False,
         without_files: bool = False, revise: bool = True) -> dict:
    """Make the creative, add the image rows, review it as a viewer, then run the loop until nothing measurable is
    missed (the text rows, the reference rows and the image rows), nothing can be changed, or MAX_REVISIONS rounds are
    done; the final version is the best one. Every version is kept."""
    if (brief.get("planner") or {}).get("prompt_english") and not is_english(prompt):
        prompt = brief["planner"]["prompt_english"]  # the rows, the review and the loop read the translation the plan used
    checked = guided._carried(brief, B.check(brief, studio.uploads(), studio.sprite_names()))
    for note in imageplan.restore_repaint(checked, checked.get("reference") or {}):  # G11: the picture's block colours kept
        log(f"colours: {note}")
    if not draft:
        for note in verify_pieces(log, checked) + playable(log, prompt, checked) + keep_events(log, prompt, checked):
            log(f"level: {note}")  # H1, H11, H17: the board the take uses plays the ending and every planned step
        for note in fit_fill(log, prompt, checked):  # G17: a packed board measured on the board the take uses
            log(f"fill: {note}")
        for note in real_cut(log, prompt, checked):  # G15: the cliffhanger's question is a real choice
            log(f"cut: {note}")
    v = studio.make(prompt, checked, None, log, draft=draft, allow_missing=without_files, workflow=WORKFLOW)
    v = evaluated(log, prompt, v)
    if review_on and not draft:
        v = _reviewed(log, prompt, v)
    if revise and not draft:
        from .. import audit
        made = [v]
        for _ in range(MAX_REVISIONS):
            v = revise_once(log, prompt, v, review_on)
            if (v.get("revision") or {}).get("status") != "made":
                break
            made.append(v)
            if not audit.misses(v.get("checks") or []):
                break
            same = repeated_miss(made[-2], made[-1])
            if same:
                # the same shared row missed twice with the same measure (H7, 2026-10-18: S6's "medium-to-hard (asked:
                # hard)" at the 10-block limit took three versions): the limit, said; no more revisions
                log(f"revision: {same['check']} missed twice with the same measure ({str(same.get('detail'))[:160]}): that is "
                    f"the limit of this board, so no more revisions")
                for x in made[-2:]:  # whichever is kept says it
                    x["limit_note"] = f"{same['check']}: {same.get('detail')}"
                break
        v = best_version(log, made)
    return v


def asked_misses(v: dict) -> int:
    """Misses of what the request itself asks (the "Asked:" rows, the played mistakes and order), which weigh more than a
    miss of what the picture filled in (G17)."""
    from .. import audit
    return sum(1 for c in audit.misses(v.get("checks") or []) if c.get("from") == "prompt" or
               str(c.get("check", "")).startswith(("Asked:", "Mistakes", "Order")))


def coverage_gaps(v: dict) -> list[str]:
    """The asks of the request no row measures (imageaudit.coverage_rows: "Coverage: not measured"); [] when every ask has
    a row, or when no coverage row was written."""
    row = next((c for c in v.get("checks") or [] if str(c.get("check", "")).startswith("Coverage: not measured")), None)
    return [str(row.get("detail"))] if row else []


def loop_verdict(prompt: str, v: dict) -> str:
    """The verdict the loop ranks by (E3, 2026-10-19): "fix" when a measured row failed, or when the viewer says no or
    partial on a control the request asks about and the rows do not measure every ask (coverage_gaps) or one of that
    control's rows failed; else "ship". review.overall alone turns to "fix" only on a "no"."""
    from .. import audit
    rv = v.get("review") or {}
    if audit.misses(v.get("checks") or []):
        return "fix"
    if not rv or rv.get("error"):
        return "fix"
    asked = guided.asked_controls(prompt, v.get("brief") or {})
    rows = {c.get("check"): c.get("status") for c in v.get("checks") or []}
    gaps = coverage_gaps(v)
    for m in rv.get("match") or []:
        ctl = guided.control_of(m.get("control"))
        if m.get("verdict") in ("no", "partial") and ctl in asked:
            mine = [r for r in CONTROL_ROWS.get(ctl, ()) if r in rows]
            if gaps or not mine or any(rows[r] == "failed" for r in mine):
                return "fix"
    return "fix" if rv.get("overall") == "fix" else "ship"


def best_version(log: studio.Log, made: list[dict]) -> dict:
    """The fewest measured misses, then the fewest misses of what the request asks (G17, 2026-10-17: B3's v2 lost an asked
    stuck moment and was kept over v1, whose only miss was a filled-in fill), then the viewer's ship, then the later
    version; saved."""
    from .. import audit
    if len(made) > 1:
        def key(v):
            verdict = loop_verdict(v.get("asked_prompt") or v.get("prompt") or "", v)
            return (len(audit.misses(v.get("checks") or [])), asked_misses(v), guided.VERDICT_RANK.get(verdict, 1), -int(v.get("n") or 0))
        best = min(made, key=key)
        why = (f"{len(audit.misses(best.get('checks') or []))} measured miss(es) ({asked_misses(best)} of what the request "
               f"asks), the viewer's {(best.get('review') or {}).get('overall') or 'no'} verdict")
        best["final"] = {"version": best.get("n"), "of": sorted(x.get("n") for x in made), "why": why}
        log(f"final: v{best.get('n')} is kept as the final version ({why})")
    else:
        best = made[0]
    if best.get("final"):
        vdir = studio.STUDIO / best["id"] / f"v{best['n']}"
        if vdir.is_dir():
            (vdir / "version.json").write_text(json.dumps(best, indent=1, ensure_ascii=False))
    return best


def with_facts(v: dict) -> dict:
    """The version as the viewer's review reads it, with what the picture gave written into the plan's rows as measured
    facts (G2, 2026-10-17: the viewer judged A2's measured picture colours against its own idea of "sunset"). The review
    shows each control row's plan; the version itself is not changed."""
    facts = imageplan.review_facts((v.get("brief") or {}).get("reference") or {})
    if not facts:
        return v
    out = copy.deepcopy(v)
    look = [f for f in facts if any(w in f for w in ("block colours", "background", "captions", "gradient"))]
    rest = [f for f in facts if f not in look]
    for control, lines in (("visuals", look), ("level", rest)):
        if lines:
            row = B.control(out["brief"], control)
            row["plan"] = (row.get("plan") or "") + " MEASURED FROM THE PICTURE (final): " + "; ".join(lines) + "."
    return out


def _reviewed(log: studio.Log, prompt: str, v: dict) -> dict:
    log.begin("review", "the viewer's review...")
    try:
        v["review"] = review.review(with_facts(v), prompt, studio.STUDIO, log=log)
    except Exception as e:  # a review that fails never loses the version
        log(f"review failed: {e}")
        v["review"] = {"error": str(e)[:300]}
    vdir = studio.STUDIO / v["id"] / f"v{v['n']}"
    if vdir.is_dir():
        (vdir / "version.json").write_text(json.dumps(v, indent=1, ensure_ascii=False))
    return v


# The viewer's controls and the image rows that measure them (G2b): a point on a control whose rows all pass is about
# what the picture set, measured, and starts no revision.
CONTROL_ROWS = {
    "visuals": ("Image: the background", "Image: the caption colours", "Image: the block colours", "Image: not taken stays the game's own"),
    "level": ("Image: the board's shape", "Image: the board's size", "Image: the board's blocks", "Image: the board's colours",
              "Image: mirror-symmetric", "Image: packed", "Image: the board is the picture's", "Image: more or fewer colours than the picture",
              "Image: a colour became another", "Image: the board mirrored", "Image: looks like the picture (viewer)"),
    "difficulty_pacing": ("Image: the play fills the ad", "Image: the fast finish"),
    "gameplay": ("Image: blocks left at the cut", "Image: the stuck moment is visible", "Image: the fast finish"),
}


def feedback(prompt: str, v: dict) -> str | None:
    """The measured misses (the text, reference and image rows) first, then the viewer's first fix when it is about what
    the request asks or the picture set (guided.feedback). A viewer point on a control whose image rows are measured and
    all pass starts no revision (G2b, 2026-10-17: A2's "the blocks are not sunset" against the picture's measured block
    colours ran a revision that changed nothing); the viewer's words stay in the version (review_set_by_picture)."""
    rv = v.get("review") or {}
    if rv and not rv.get("error"):
        rows = {c.get("check"): c.get("status") for c in v.get("checks") or []}
        gaps = coverage_gaps(v)
        dropped, kept = [], []
        for m in rv.get("match") or []:
            ctl = guided.control_of(m.get("control"))
            mine = [r for r in CONTROL_ROWS.get(ctl, ()) if r in rows]
            # E2 (2026-10-19): the viewer's point is dropped only when the rows measure every ask of the request (no
            # "Coverage: not measured" row) and all of this control's rows pass; the owner's "one more colour" had no row,
            # the type rows passed, and the viewer's correct point was discarded
            if m.get("verdict") in ("no", "partial") and mine and not gaps and all(rows[r] != "failed" for r in mine):
                dropped.append(m)
            else:
                kept.append(m)
        if dropped:
            v["review_set_by_picture"] = [f"{m.get('control')}: {m.get('seen')}" for m in dropped]
            v = {**v, "review": {**rv, "match": kept}}
    return guided.feedback(prompt, v)


LOOK_ROWS = {"visuals.background": "Image: the background", "visuals.captions": "Image: the caption colours",
             "visuals.colours": "Image: the block colours"}
LOOK_FIELDS = {"visuals.background": ("background", "background_image", "theme"),
               "visuals.captions": ("caption_fill", "caption_outline"), "visuals.colours": ("blocks", "theme")}


def pin_look(before: dict, after: dict, misses: list[dict]) -> list[str]:
    """A revision keeps the look the picture gave (the background, the captions, the blocks' display colours), as the
    video path keeps the board (guided.pin_reference): the revised plan never re-plans a measured look. A miss of its
    own row at the plan restores the picture's kit itself. Returns what was kept."""
    prov = before.get("reference") or {}
    kit = prov.get("look") or {}
    kept = []
    missed = {c.get("check") for c in misses if c.get("where") == "plan"}
    for g, fields in LOOK_FIELDS.items():
        if g not in (prov.get("set") or []):
            continue
        for f in fields:
            if after["visuals"].get(f) != before["visuals"].get(f):
                after["visuals"][f] = copy.deepcopy(before["visuals"].get(f))
                kept.append(g)
        if LOOK_ROWS[g] in missed and kit:
            if g == "visuals.background" and kit.get("background"):
                after["visuals"]["background"] = list(kit["background"])
            if g == "visuals.captions" and kit.get("caption_fill"):
                after["visuals"]["caption_fill"], after["visuals"]["caption_outline"] = kit["caption_fill"], kit["caption_outline"]
    kept = list(dict.fromkeys(kept))
    if kept:
        after["changed"] = [g for g in after.get("changed") or [] if g not in kept]
        guided.restore_texts(before, after, kept)
    return [f"the picture's look is kept ({', '.join(kept)})"] if kept else []


LEVEL_FIELDS = ("source", "shipped", "file", "shape", "width", "height", "blocks", "colours", "difficulty", "edit", "moves", "changes",
                "pieces", "style", "label")
PACK_MARGIN_RETRY = 0.72  # a packed miss: the next take's blocks must cover this much of the board (the first asks 0.65)


def pin_level(prompt: str, before: dict, after: dict, misses: list[dict]) -> list[str]:
    """A revision never changes the level for what the level does not answer (F6, F11, 2026-10-17: a miss of the look,
    or of "packed", came back as an easier board with a gate moved, and the play fell to 13-18 s of a 30-45 s ad):
    - the difficulty (and its relative edit) stays the base's unless the request states one and its row missed;
    - with no miss at the level or the play, every level field stays the base's;
    - a miss of "Image: packed" is answered with the board's own levers: more blocks, bigger pieces or a smaller board,
      fitted again to a fuller board (imageplan.fit_board with PACK_MARGIN_RETRY), and a new take.
    Returns what was kept or changed."""
    from .. import videoref as V
    notes = []
    lb, la = before["level"], after["level"]
    checks = {c.get("check") for c in misses}
    level_miss = any(c.get("where") in ("level", "play") for c in misses)
    diff_asked = "difficulty" in V.stated(prompt) and "Asked: difficulty" in checks
    if not diff_asked and (la.get("difficulty") != lb.get("difficulty") or la.get("edit") != lb.get("edit")):
        la["difficulty"], la["edit"] = lb.get("difficulty"), copy.deepcopy(lb.get("edit"))
        notes.append("the level's difficulty stays the version before's (no miss is about the difficulty)")
    if not level_miss:
        moved = [k for k in LEVEL_FIELDS if la.get(k) != lb.get(k)]
        for k in moved:
            la[k] = copy.deepcopy(lb.get(k))
        if moved:
            notes.append(f"the level stays the version before's ({', '.join(moved)}): no miss is about the board or the play")
    if "Image: the play fills the ad" in checks:
        # G1: the play was thin for the ad: more blocks on a board the picture filled, one more wrong move on a named
        # count when the request allows it; never the difficulty
        bd = (before.get("reference") or {}).get("board") or {}
        from .. import videoref as V2
        if "blocks" in (bd.get("filled") or []) and (lb.get("blocks") or 0) < V2.BLOCKS_RANGE[1]:
            want = min(V2.BLOCKS_RANGE[1], (lb.get("blocks") or 0) + 2)
            shape = lb.get("shape") if lb.get("shape") not in (None, "any") else "open"
            if lb.get("width") and lb.get("height") and (V2.board_blocks(want, shape, lb["width"], lb["height"], lb.get("pieces")) or 0) < want:
                grown = V2.grow_for_blocks(want, shape, lb["width"], lb["height"], lb.get("pieces"))
                if grown:
                    la["width"], la["height"], want = grown[0], grown[1], min(want, grown[2])
            if want > (lb.get("blocks") or 0):
                la["blocks"] = want
                notes.append(f"the play was thin for the ad: {want} blocks, not {lb.get('blocks')}, on a board the picture filled")
        else:
            # a count at the limit or one the request names: one more early wrong move or hesitation, if one is left
            g = after["gameplay"]
            line, _ = imageplan.extra_beat(after, prompt, la.get("blocks") or lb.get("blocks") or 0,
                                           imageplan.expected_play(after, la.get("blocks") or lb.get("blocks") or 0),
                                           named="blocks" not in (bd.get("filled") or []))
            if line:
                notes.append("the play was thin for the ad: " + line)
            else:
                notes.append("the play is as long as this level allows; no revision for it")
    if "Image: the cliffhanger is a real choice" in checks:
        from ..imageaudit import blocks_left_asked
        g = after["gameplay"]
        if blocks_left_asked(prompt) is None and (before["gameplay"].get("blocks_left") or 2) < imageplan.CUT_MAX_LEFT:
            g["blocks_left"] = (before["gameplay"].get("blocks_left") or 2) + 1
            if "gameplay.blocks_left" not in after.setdefault("changed", []):
                after["changed"].append("gameplay.blocks_left")
            notes.append(f"the cut had no trapped block: it now stops with {g['blocks_left']} blocks left")
    if "Image: packed" in checks:
        fa = (((before.get("reference") or {}).get("board") or {}).get("fit_args"))
        if fa:
            fit = imageplan.fit_board(**{**fa, "size": tuple(fa["size"])}, margin=PACK_MARGIN_RETRY)
            la.update(blocks=fit["blocks"], pieces=fit["pieces"], width=fit["size"][0], height=fit["size"][1])
            la["style"] = list(dict.fromkeys(list(la.get("style") or []) + ["packed"]))
            notes.append(f"the board must be packed like the picture: {fit['blocks']} {fit['pieces']} pieces on "
                         f"{fit['size'][0]}x{fit['size'][1]} (about {fit['fill']:.0%} of the cells), a new take")
    after["changed"] = [g for g in after.get("changed") or [] if not g.startswith("level.") or
                        any(B._get(after, path) != B._get(before, path) for path in B.GROUPS.get(g, ("", []))[1])]
    for g in ("level.blocks", "level.pieces", "level.size", "level.style"):
        if any(B._get(after, path) != B._get(before, path) for path in B.GROUPS[g][1]) and g not in after["changed"]:
            after["changed"].append(g)
    return notes


def revise_once(log: studio.Log, prompt: str, v: dict, review_on: bool) -> dict:
    """One round of the loop (the case p.10), as guided.revise_once, with the picture's board and look kept (the
    reading is not repeated). A miss of a board row is the generator's: it makes a new take (another seed) even when the
    planner finds nothing to change."""
    from .. import audit, videoref
    text = feedback(prompt, v)
    if v.get("review_set_by_picture"):
        log("revision: the viewer's point is on what the picture set, and its measured rows pass ("
            + "; ".join(x.split(":")[0] for x in v["review_set_by_picture"]) + "): it starts no revision; the viewer's words are kept")
    if text is None:
        if v.get("review_not_asked"):
            log("revision: nothing measurable was missed, and the viewer's \"not as asked\" is about what the request does "
                f"not ask and the picture did not set ({'; '.join(x.split(':')[0] for x in v['review_not_asked'])}); "
                "no revised version")
        else:
            log("revision: nothing measurable was missed; no revised version is needed")
        return v
    misses_now = audit.misses(v.get("checks") or [])
    if misses_now and all(c.get("check") == "Image: the play fills the ad" for c in misses_now) and \
            not imageplan.play_levers_left(v["brief"], prompt, v["brief"].get("reference") or {}):
        log("revision: the play is as long as this level allows; no revision for it")
        v["revision"] = {"status": "unchanged", "feedback": text, "why": "no lever is left that lengthens the play"}
        return v
    if (v["brief"].get("level") or {}).get("source") == "picture" and misses_now and \
            all(c.get("check") == "Asked: length" for c in misses_now) and (v["brief"].get("reference") or {}).get("play_overrun"):
        # a copied board's play cannot be shortened; the plan said the overrun (common with the video path, 2026-10-19)
        log("revision: the only miss is the length, and the plan said the picture's board needs more play than the stated length "
            "holds; a copied board cannot be shortened, so no revised version is made")
        v["revision"] = {"status": "unchanged", "feedback": text, "why": "a copied board's play cannot be shortened (said in the plan)"}
        return v
    log.begin("revise", "the result missed part of the request or the picture; planning a revised take...")
    try:
        misses = audit.misses(v.get("checks") or [])
        current = {k: x for k, x in v["brief"].items() if k != "planner"}
        brief2 = planner.plan(text, uploads={}, sprites=studio.sprite_names(), current=current, available=studio.uploads(),
                              inventory=studio.planner_context(v["id"], v["n"]), references={}, log=log,
                              history=studio.history(v["id"], v["n"]), parts=studio.part_lengths(v["id"], v["n"]), route=None)
        level_miss = any(c.get("where") in ("level", "play") for c in misses) or any(c["check"] == "Asked: length" for c in misses)
        if not B.changed_groups(v["brief"], brief2) and not level_miss:
            log("revision: the planner found nothing to change; the version stands with its report")
            v["revision"] = {"status": "unchanged", "feedback": text}
            return v
        brief2 = guided._carried(brief2, B.check(brief2, studio.uploads(), studio.sprite_names()))
        brief2["planner"]["workflow"] = WORKFLOW
        brief2["planner"]["references"] = (v["brief"].get("planner") or {}).get("references") or []
        if v["brief"].get("reference"):
            brief2["reference"] = v["brief"]["reference"]
        for note in keep_asked(prompt, v["brief"], brief2):
            log(f"revision: {note}")
        for note in guided.pin_reference(v["brief"], brief2, misses):
            log(f"revision: {note}")
        for note in pin_look(v["brief"], brief2, misses):
            log(f"revision: {note}")
        for note in pin_level(prompt, v["brief"], brief2, misses):
            log(f"revision: {note}")
        if (v["brief"].get("level") or {}).get("source") == "picture" and brief2["level"] != v["brief"]["level"]:
            # the picture's board is fixed (2026-10-19): a revision changes the play, the pacing or the captions, never the board
            brief2["level"] = copy.deepcopy(v["brief"]["level"])
            brief2["changed"] = [g for g in brief2.get("changed") or [] if not g.startswith("level.")]
            log("revision: the board stays the picture's (copied cell by cell); the revision changes the play, not the level")
        for note in keep_steps(log, v["brief"], brief2):  # G17: a level lever never loses a planned step
            log(f"revision: {note}")
        for note in imageplan.request_values(brief2, prompt):
            log(f"revision: from the request: {note}")
        for note in imageplan.restore_repaint(brief2, brief2.get("reference") or {}):
            log(f"revision: colours: {note}")
        for note in imageplan.honest_cascade(brief2, prompt):  # G6, G14: the revised captions promise nothing unplayable
            log(f"revision: captions: {note}")
        for note in imageplan.clear_invented_blocks(brief2, prompt, brief2.get("reference") or {}):  # H12, H15
            log(f"revision: colours: {note}")
        for note in guided.keep_stated(prompt, v["brief"], brief2, misses):
            log(f"revision: {note}")
        guarded = guided.length_guard(v, brief2, prompt)
        if guarded:
            log(f"revision: {guarded}")
        before_fit = dict(brief2["concept"])
        for note in videoref.fit_captions(brief2):
            log(f"revision: captions: {note}")
        for note in imageplan.keep_quoted(brief2, prompt, before_fit):
            log(f"revision: captions: {note}")
        for note in imageplan.sequence_matches(brief2, prompt) + imageplan.cliffhanger_replay(brief2, prompt):
            log(f"revision: sequence: {note}")
        texts = guided.unchanged_texts(v["brief"], brief2)
        if texts:
            log(f"revision: the plan's text for {', '.join(texts)} is the version before's (none of their fields changed)")
        if not misses:
            points = guided.viewer_points(prompt, v)
            changed = set(B.changed_controls(v["brief"], brief2))
            if points and not changed & points:
                log(f"revision: the revised plan changes {', '.join(sorted(changed)) or 'nothing'}, nothing the viewer's points "
                    f"are about ({', '.join(sorted(points))}); no new version")
                v["revision"] = {"status": "unchanged", "feedback": text, "why": "nothing the viewer's points are about changed"}
                return v
        if level_miss:
            # the same spec gives the same cached board and film: a miss in the board, the play or the length is a new take
            brief2["gameplay"]["seed"] = (v["brief"]["gameplay"].get("seed") or 0) + 1
            if "gameplay.retake" not in brief2["changed"]:
                brief2["changed"].append("gameplay.retake")
        if not B.changed_groups(v["brief"], brief2):
            log("revision: with the picture's fields kept, nothing is left to change; the version stands with its report")
            v["revision"] = {"status": "unchanged", "feedback": text}
            return v
        for note in playable(log, prompt, brief2) + keep_events(log, prompt, brief2):  # H11, H17: the revised board too
            log(f"revision: level: {note}")
        v2 = studio.make(text, brief2, v["id"], log, base=v["n"], allow_missing=True, asked=prompt, workflow=WORKFLOW)
        v2["revision"] = {"status": "made", "of": v["n"], "feedback": text, "original_prompt": prompt}
        v2 = evaluated(log, prompt, v2)
        if review_on:
            log.begin("review", "the viewer's review of the revised version...")
            try:
                v2["review"] = review.review(with_facts(v2), prompt, studio.STUDIO, log=log)
            except Exception as e:
                v2["review"] = {"error": str(e)[:300]}
        miss2 = audit.misses(v2.get("checks") or [])
        log(f"revision: v{v2['n']} made; {'everything measurable met' if not miss2 else 'still missed: ' + ', '.join(c['check'] for c in miss2)}")
        vdir = studio.STUDIO / v2["id"] / f"v{v2['n']}"
        (vdir / "version.json").write_text(json.dumps(v2, indent=1, ensure_ascii=False))
        return v2
    except Exception as e:  # a failed revision never loses the first version
        if "identical to v" in str(e):
            log(f"revision: {e}")
            v["revision"] = {"status": "unchanged", "feedback": text, "why": str(e)[:300]}
            return v
        log(f"revision failed: {e}")
        v["revision"] = {"status": "failed", "error": str(e)[:300], "feedback": text}
        return v
