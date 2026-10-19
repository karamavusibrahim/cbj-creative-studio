"""Prompt enhancement (2026-10-18): the user's request rewritten so the planner reads it the way
the user meant it, and nothing more.

Why a separate step. The planner (planner.py) reads a prompt into a typed brief and the engine
makes exactly what the brief says; the evaluation (audit.py) then measures every fact the PROMPT
asked for. So a prompt is a contract: words the planner does not read reliably ("make it pop",
"a bomb clears the row", a Turkish sentence against English word tables) are read as defaults or
mis-read, and words the user did not write must not appear as asks. The enhancer therefore has one
job with two halves: say what the user said in the words the planner and the game understand, and
add nothing. Everything optional it would like to add is returned as a QUESTION the user can tap.

What runs:
1. the model (the same planner backend, llm.planner_client) rewrites the request with the
   vocabulary below (SYSTEM), listing every change it made;
2. code checks the rewrite against the original with the engine's own readers:
   - every quoted caption of the original is kept word for word;
   - no new measurable ask (audit.asked: block count, colours, difficulty, length, ending, mistakes,
     shape, looks, seconds left, clock, walls, level number, cursor, music, background, blocks at
     the cut, new quoted captions); an added ask is turned into a question instead;
   - no field names, enum tokens or hex codes (brief.plain_text);
   - model-added captions under 6 words; no statistics, odds or IQ claims (ad rules);
   One re-ask with the violations listed; if the rewrite still breaks a rule, the original prompt is
   returned unchanged with the violations as warnings (a wrong enhancement is worse than none).
3. the workflow the engine will route the (enhanced) request to is reported, from app.workflow_of,
   so the user sees "this will be read as an image-guided creative" before pressing Generate.

`cbj enhance "<prompt>" [--edit ID]`, POST /api/enhance, the web app's "Enhance prompt" button.
"""
from __future__ import annotations

import json
import re
import time

from . import brief as B
from . import audit, llm, studio

# ── the vocabulary digest the model writes with (shared with trends.py) ───────────────────────────
VOCABULARY = """THE GAME (nothing else exists in it). Color Block Jam: coloured polyomino blocks on a grid; the player drags one block at a time; a block leaves only through a gate (door) of its own colour on the board's edge, when its lane is clear; blocks get in each other's way, so some must be moved aside first; holes (walls) are the only obstacles; a countdown clock; "Level N" and the time in the HUD. Seven colours: green, yellow, blue, red, orange, purple, dark green (other colour words are these slots repainted and named). NOT in the game: boosters, power-ups, bombs, ice, keys, chains, locks, hints, undo, hidden or arrow blocks, doors that open or change colour, characters, enemies, items, textures on blocks, voice-over, a second level in one ad, two blocks leaving at the same moment, choosing a gate side, "regions" of the board, real people, other games, 3D characters.

WHAT A PROMPT CAN ASK (the eight controls of the case) and the words the planner reads reliably:
1 level: board shape (open; narrow centre / hourglass / bottleneck; two rooms joined by a door; holes or pillars; cross; ring; lanes), size ("6x8", "small board" = 6x6, "medium-sized" = 7x7, "big board" = 8x9), number of blocks (2-10), piece shapes (small; big or chunky; long bars; varied), looks (symmetric or mirror; packed or crowded; colourful; spacious: "plenty of empty cells", "room to move"), the colours the board may use ("only red, blue and yellow"), the HUD level number ("level 47"), how many moves the solution takes ("solved in about 10 moves"), one of the game's own levels ("level 3 of the game"). Difficulty is control 3.
2 gameplay: the ending: a clean win; a near-fail (a wrong move, a stuck moment, solved with 1-3 seconds left: "with two seconds left"); a cliffhanger (the video stops with 1-3 blocks left and asks the viewer); a time-out (the clock runs out one move short: only when a fail is wanted). Mistakes 0-3 ("one wrong move", "no mistakes"), their kind (blocked by another block; moved the wrong way; a pointless nudge), hesitations 0-2 ("picks a block up and puts it back"). An ORDER of interactions needs sequencing words: "first ..., then ..., last ..." ("first move the yellow block aside, then the green block leaves, the red block leaves last"; "all the red blocks leave first, then all the blue ones"; "the biggest block leaves last"; "the blue block gets stuck behind a red block first"). A satisfying finish: "one move frees everything", "they all leave one after another", a cascade. The clock's start value ("a 90-second clock").
3 difficulty or pacing: easy / medium / hard; the length in seconds (30-60; shorter is raised to 30); tempo calm / normal / fast; the curve ("speeds up toward the end", "slows down"); relaxing, rage, speedrun, "can you solve it?", tension and "for beginners" are read into these.
4 visual elements: a theme (the game's own look; candy; pastel; neon; dark); block colours by name ("pink blocks", "the blue blocks become red"); the background behind the board (colours, or an attached picture); the board's cell colour; caption colours ("white captions with a soft outline", "make the hook yellow"); a closer camera ("zoom in a little"); a punch-in for a stretch ("push in on the red block from 8 to 11 s"); the cursor (ring, hand, none); hiding the clock or the level badge; the format (9:16 portrait default; 1:1; 4:5; 16:9).
5 creative concept: the angle in one line ("concept: 'beat the clock'"); the captions, each quoted and under 6 words: the hook (first words on screen), the caption on the mistake, on the fix, the hurry caption in the last seconds, the caption on the fast finish, on the result, the end card's title and line, the button's text; the language ("captions in Turkish"). Numbers in copy only as measured facts (the seconds left, the time used, the blocks left); never statistics, odds, percentages, rankings or IQ claims.
6 sequence of events: standard (hook over the gameplay, slow-motion replay, the game's result screen, the end card) or result-first ("show the win first, then how it happened"); with or without the replay or the result screen; the length of the still opening frame and of the held result; moving a caption's entrance or exit ("the hook appears one second later").
7 assets to use: an attached picture and where it goes (a logo in the top-left corner; a sticker in the top-right corner; the icon beside the hook; the picture on the end card; the end card's background; the button; the cursor; a picture on the board's walls "instead of the obstacle"; a texture on ONE block of a colour: "apply the attached texture to the blue block"); the game's own pictures by name (the coin pile, the stopwatch, the blue toy-brick start background, the green button); removing a picture; sound effects on or off; an attached music file ("use the attached track as the music"). An attached file is used only when the prompt says how; a reference video or image is never placed in the ad unless the prompt says to.
8 elements that should remain unchanged: "keep everything else exactly as it is", or a list (the level, the moves, the timing, the camera, the look, the captions, the sequence, the pictures, the sound). In an EDIT, start with what to keep and name the one change.

REFERENCES. An attached video is always a reference: the prompt says what to take from it ("its hook and pacing", "a Color Block Jam version of this concept", "its ending", "its look"); what the prompt states itself always wins over the reference. An attached image is a reference when the prompt says so ("inspired by this image", "its colours", "a board like this screenshot", "as crowded as this"), otherwise it is a picture to place.

DEFAULTS when the prompt says nothing: a hard narrow-centre showcase level (or a generated level when the structure, size, colours or difficulty are given), a near-fail ending, 30 seconds, normal tempo, the game's own look, white captions with a purple outline, a ring cursor, the HUD shown, the standard sequence, English, 9:16, no uploads used, sound effects on, no music."""

SYSTEM = f"""You improve a request for a Color Block Jam video ad before it is planned. The planner is a language model that reads the request into a typed brief; a deterministic engine then builds the level, records the real game and composes the ad; an evaluator measures every fact the request asked for. Your rewrite is what the planner will read, so it must be clear, in English, in the vocabulary below, and it must contain exactly what the user asked for: no more, no less.

{VOCABULARY}

RULES FOR THE REWRITE.
- Keep the user's intent and every concrete ask. Keep every quoted caption word for word (the quotes too). Keep every number (seconds, counts, sizes, level numbers) exactly.
- Say each ask once, in the control's own words from the vocabulary, in a natural paragraph: a marketing person wrote it and a marketing person reads the plan. No field names, no technical tokens, no hex codes, no JSON, no headings or bullet lists.
- Add NOTHING the user did not ask for: no ending, length, difficulty, colours, block count, captions, look or music they did not mention. The planner has defaults for all of that and the plan shows them as "default"; an addition would show as "asked". If you think the user would want to decide something they left open, put it in questions instead (at most three), each with a one-sentence option they can append. Every concrete ask in your rewrite must come from the user's words: when you translate or replace them, the change entry's `before` quotes the user's exact words and `after` gives yours ("Zor bir seviye" -> "a hard level"; "only 1% can solve it" -> "the hook caption is \"Can you beat it?\""). An ask you cannot tie to their words that way is an invention: make it a question.
- Translate the request into English when it is in another language. Do not decide the captions' language from the request's language: if the user wrote in another language and did not say which language the captions should be in, ask (a question with options "Captions in <that language>." and "Captions in English.").
- Make the gameplay legal: one block per drag; a block leaves only through a gate of its own colour; an order of interactions written with "first / then / last"; mistakes 0-3; a near-fail with 1-3 seconds left; one level per ad; 30-60 seconds.
- Replace what the game cannot do with the closest thing it can, and list it as a "replaced" change with the reason (a bomb that clears a row -> one key move that frees several blocks at once; two blocks leaving together -> one right after the other; ice or locks -> a block in the way that must be moved aside first; a character or mascot -> an attached sticker in a corner, if the user attaches one; a second level -> one level; "only 1% can solve this" -> an honest dare such as "Can you beat it?"). Never drop an ask silently.
- Attached files: name each the way the user did and say where it goes; if the user attached a picture or video and did not say how to use it, do not guess: ask (a question).
- Vague mood words ("make it pop", "more engaging", "premium") are not asks the engine can measure: keep them only if the user tied them to something concrete; otherwise turn them into a question with concrete options from the vocabulary.
- Pronouns that point at nothing ("replace this", "change it") in a NEW request: ask what is meant. In an EDIT, THINGS IN THIS AD lists what the request may point at: resolve the pointer to that name when it is unambiguous, and ask when two things fit.
- An EDIT rewrite starts with what to keep ("Keep everything exactly the same, but ...") unless the user already said so, names the one change (or the few changes) and nothing else, and keeps the user's own words for the change.
- If the request is already clear and complete, return it unchanged (changed false) and say so.

OUTPUT (JSON following the schema): prompt (the rewrite, one paragraph, plain English), changed (false when identical in meaning and wording), changes (one entry per edit you made: kind "clarified" | "translated" | "replaced" | "removed" | "reordered", before = the user's words, after = yours, why = one short reason), questions (optional things the user may want to add, each with 2-3 options; an option is ONE sentence that can be appended to the prompt as it is), warnings (things the user should know: an ask that cannot be measured, a file that is missing, a caption over 6 words of their own)."""

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["prompt", "changed", "changes", "questions", "warnings"],
    "properties": {
        "prompt": {"type": "string"},
        "changed": {"type": "boolean"},
        "changes": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["kind", "before", "after", "why"],
            "properties": {"kind": {"type": "string", "enum": ["clarified", "translated", "replaced", "removed", "reordered"]},
                           "before": {"type": "string"}, "after": {"type": "string"}, "why": {"type": "string"}}}},
        "questions": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["question", "options"],
            "properties": {"question": {"type": "string"},
                           "options": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 3}}}},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
}

# The asked facts an enhancement may never introduce (audit.asked keys). A key whose original value is
# empty and whose enhanced value is not is an added ask.
FACT_KEYS = ("blocks", "colours", "colour_names", "difficulty", "length_s", "clock_left_s", "mistakes", "shape", "style",
             "ending", "stuck_by", "blocks_by", "hesitations", "timer_s", "walls", "label", "colour_counts", "cursor",
             "music", "background", "blocks_left")
FACT_WORDS = {"blocks": "a number of blocks", "colours": "a number of colours", "colour_names": "the board's colours",
              "difficulty": "a difficulty", "length_s": "a length", "clock_left_s": "the seconds left at the end",
              "mistakes": "a number of mistakes", "shape": "a board shape", "style": "a look for the board", "ending": "an ending",
              "stuck_by": "a stuck move", "blocks_by": "a blocking move", "hesitations": "hesitations", "timer_s": "the clock's start",
              "walls": "walls", "label": "a level number", "colour_counts": "blocks per colour", "cursor": "the cursor",
              "music": "music", "background": "a background", "blocks_left": "blocks left at the cut"}
STATS = re.compile(r"(\d+\s*%|\bpercent\b|\bonly\s+\d+\b|\bIQ\b|\btop\s+\d+\b|\branked?\b|\bodds\b|\bgenius(es)?\b)", re.I)
MAX_CAPTION_WORDS = 6
MAX_QUESTIONS = 3


def _empty(v) -> bool:
    return v is None or v is False or v == [] or v == {} or v == ""


def quotes(text: str) -> list[str]:
    return [q[0] or q[1] for q in B.QUOTED.findall(text)]


def _justified(key_words: str, fact_in, original: str, changes: list[dict]) -> bool:
    """An added ask is allowed when a change entry ties it to the user's own words: its `before` is in the
    original request and its `after` carries the fact (a translation, or a replacement of an impossible ask).
    The user sees that entry and can undo it; an ask with no such entry is an invention."""
    on = _normal(original)
    for c in changes or []:
        before, after = _normal(c.get("before") or ""), c.get("after") or ""
        if len(before) >= 3 and before in on and fact_in(after):
            return True
    return False


def added_facts(original: str, enhanced: str, changes: list[dict] | None = None) -> list[str]:
    """The measurable asks present in the rewrite, absent from the original and not justified by a change entry
    (see _justified), in plain words."""
    a, b = audit.asked(original), audit.asked(enhanced)
    out = []
    for k in FACT_KEYS:
        added = (_empty(a.get(k)) and not _empty(b.get(k))) or \
                (isinstance(a.get(k), list) and isinstance(b.get(k), list) and bool(set(b[k]) - set(a[k])))
        if not added:
            continue
        if _justified(k, lambda after, k=k: not _empty(audit.asked(after).get(k)), original, changes or []):
            continue
        out.append(FACT_WORDS[k])
    new_quotes = [q for q in quotes(enhanced) if q not in quotes(original)]
    new_quotes = [q for q in new_quotes if not _justified(q, lambda after, q=q: q in after, original, changes or [])]
    if new_quotes:
        out.append("a caption (" + "; ".join(f"“{q}”" for q in new_quotes[:3]) + ")")
    return out


def violations(original: str, out: dict) -> list[str]:
    """What the rewrite breaks, each as one plain sentence; [] when it is acceptable."""
    text = (out.get("prompt") or "").strip()
    changes = out.get("changes") or []
    v = []
    if not text:
        return ["the rewrite is empty"]
    missing = [q for q in quotes(original) if q not in text]
    removed = {_normal(c.get("before") or "") for c in changes if c.get("kind") in ("removed", "replaced")}
    missing = [q for q in missing if not any(_normal(q) in r for r in removed)]  # a quoted claim the model replaced, and said so
    if missing:
        v.append("these quoted words of the request must stay word for word: " + "; ".join(f"“{q}”" for q in missing[:4]))
    for f in added_facts(original, text, changes):
        v.append(f"the rewrite adds {f}, which the request did not ask for: either list a change whose 'before' quotes the "
                 f"user's words that mean it, or offer it as a question")
    if B.plain_text(text) != text:
        v.append("the rewrite contains technical names (field names, tokens or hex codes); write plain words")
    for q in quotes(text):
        if q not in quotes(original) and len(q.split()) > MAX_CAPTION_WORDS:
            v.append(f"the caption “{q}” has more than {MAX_CAPTION_WORDS} words")
    if STATS.search(text) and not STATS.search(original):
        v.append("the rewrite adds a statistic, ranking or IQ claim, which ad rules forbid")
    if re.search(r"^\s*[-*•#]|\n\s*[-*•]\s", text):
        v.append("the rewrite uses bullet points or headings; write one paragraph")
    return v


def _own_warnings(original: str, uploads: list[str]) -> list[str]:
    w = []
    for q in quotes(original):
        if len(q.split()) > MAX_CAPTION_WORDS:
            w.append(f"Your caption “{q}” is over {MAX_CAPTION_WORDS} words; the ad shows captions for a few seconds, shorter reads better.")
    if STATS.search(original):
        w.append("Statistics, odds and IQ claims are not allowed in the ad's copy; the planner will replace them with an honest dare.")
    m = re.search(r"\b(\d{1,3})\s*(?:s|sec|secs|seconds?)\b", original, re.I)
    if m and not 30 <= int(m.group(1)) <= 60:
        w.append(f"The case asks for 30-60 second ads; {m.group(1)} seconds will be brought into that range.")
    return w


def workflow_for(prompt: str, uploads: list[str], creative_id: str | None) -> str:
    """The workflow the engine will route this request to (app.workflow_of), as the engine decides it."""
    from .app import workflow_of  # lazy: app imports this module
    return workflow_of(prompt, list(uploads), creative_id)


WORKFLOW_WORDS = {
    "create": "a new creative from the text (pictures attached, if any, are placed as assets)",
    "image_guided": "a new creative guided by the attached picture (it is read as a reference)",
    "guided": "a new creative guided by the attached video (it is read whole as a reference)",
    "edit": "an edit of the chosen creative: only what the request names changes, and the edit report proves it",
}


def _context(prompt: str, uploads: list[str], creative_id: str | None, base: int | None) -> tuple[str, str]:
    """The user message and the mode ("new" or "edit")."""
    ups = studio.uploads()
    vids = studio.videos()
    files = []
    for n in uploads:
        kind = "video" if n in vids else "music" if B.is_audio(n) else "image" if n in ups else "file"
        files.append(f"{n} ({kind})")
    user = f"REQUEST:\n{prompt.strip()}\n\nATTACHED FILES: {', '.join(files) if files else 'none'}"
    mode = "new"
    if creative_id:
        v = studio.parent(creative_id, base)
        if v is None:
            raise ValueError(f"no creative {creative_id}")
        mode = "edit"
        user = ("MODE: EDIT of an existing creative (version v%d). The rewrite must keep everything the request does not "
                "name and say so.\n\n" % v["n"]) + user
        user += f"\n\nTHE CURRENT CREATIVE: {v['brief'].get('summary') or v['prompt']}"
        try:
            inv = studio.planner_context(creative_id, v["n"])
            if inv:
                user += "\n\nTHINGS IN THIS AD (what the request may point at):\n" + inv
        except Exception:  # noqa: BLE001 - an old version without a manifest still gets a rewrite
            pass
    else:
        user = "MODE: NEW creative.\n\n" + user
    return user, mode


def enhance(prompt: str, uploads: list[str] | None = None, creative_id: str | None = None, base: int | None = None,
            client=None, log=None) -> dict:
    """The enhanced request and what changed. Never raises for a bad rewrite: falls back to the original
    with warnings. Raises ValueError only when the model cannot be reached or the creative does not exist."""
    from .planner import _parse
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("write a prompt first")
    uploads = list(uploads or [])
    user, mode = _context(prompt, uploads, creative_id, base)
    client = client or llm.planner_client()
    t0 = time.time()
    out, bad, tries = None, [], 0
    ask = user
    while tries < 2:
        tries += 1
        if log:
            log("rewriting the request..." if tries == 1 else "rewriting again: " + "; ".join(bad))
        try:
            out = _parse(client.complete(SYSTEM, ask, SCHEMA))
        except (ValueError, json.JSONDecodeError) as e:
            bad = [f"the model did not answer with a usable rewrite ({str(e)[:120]})"]
            out = None
            continue
        bad = violations(prompt, out)
        if not bad:
            break
        ask = user + "\n\nYOUR PREVIOUS REWRITE BROKE THESE RULES; fix them (turn any added ask into a question):\n- " + "\n- ".join(bad)
    seconds = round(time.time() - t0, 1)
    model = getattr(client, "last_model", None)
    warnings = _own_warnings(prompt, uploads)
    if out is None or bad:
        # a wrong enhancement is worse than none: the user's words stand, the model's additions become questions
        questions = _questions(out) if out else []
        return {"prompt": prompt, "original": prompt, "changed": False, "mode": mode,
                "workflow": workflow_for(prompt, uploads, creative_id),
                "changes": [], "questions": questions, "warnings": warnings + ["Kept your wording: " + "; ".join(bad) + "."],
                "model": model, "seconds": seconds}
    text = out["prompt"].strip()
    changed = bool(out.get("changed")) and _normal(text) != _normal(prompt)
    return {"prompt": text if changed else prompt, "original": prompt, "changed": changed, "mode": mode,
            "workflow": workflow_for(text if changed else prompt, uploads, creative_id),
            "changes": [c for c in (out.get("changes") or []) if c.get("after") or c.get("kind") == "removed"] if changed else [],
            "questions": _questions(out), "warnings": warnings + [w for w in (out.get("warnings") or []) if w],
            "model": model, "seconds": seconds}


def _normal(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def _questions(out: dict | None) -> list[dict]:
    qs = []
    for q in (out or {}).get("questions") or []:
        opts = [o.strip() for o in (q.get("options") or []) if o and o.strip()]
        if q.get("question") and opts:
            qs.append({"question": q["question"].strip(), "options": opts[:3]})
    return qs[:MAX_QUESTIONS]


def text(result: dict) -> str:
    """The result for a terminal."""
    lines = [result["prompt"]]
    if result["changed"]:
        lines.append("")
        lines.append(f"Changes ({len(result['changes'])}):")
        for c in result["changes"]:
            lines.append(f"  {c['kind']}: “{c['before']}” -> “{c['after']}” ({c['why']})")
    else:
        lines.append("\n(unchanged)")
    if result["questions"]:
        lines.append("")
        lines.append("You may want to add:")
        for q in result["questions"]:
            lines.append(f"  {q['question']}")
            for o in q["options"]:
                lines.append(f"    - {o}")
    if result["warnings"]:
        lines.append("")
        lines.append("Notes: " + " ".join(result["warnings"]))
    lines.append("")
    lines.append(f"Read as: {WORKFLOW_WORDS.get(result['workflow'], result['workflow'])}. "
                 f"{result['model'] or 'no model'}, {result['seconds']} s.")
    return "\n".join(lines)
