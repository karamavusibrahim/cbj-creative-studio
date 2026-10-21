"""The asked-facts audit (2026-10-15): what the prompt measurably asks for, read from the prompt
itself (never from the plan), against the brief (planned) and the made creative (made).

The brief's own rubric is the list: the eight prompt controls (p.3), the requested gameplay (p.5: a
type of level, a visually interesting board, a difficult or easy level, a gameplay progression, a
near-fail moment, a satisfying solve, a sequence of interactions), 30-60 s (p.2), and for an edit
the preserved elements (p.7, proven by the edit report). The viewer's review judges the soft side;
this audit measures the countable side and closes the loop:

- at the level stage, a miss the generator can fix (blocks, colours, a named block, the first
  interaction) makes the studio generate again with another seed (`level_misses`);
- after the make, every row goes into the version's checks ("Asked: ...", from "prompt"), so the
  UI shows them and the review gets them as measured facts;
- a miss the plan or the play caused can be fed back (`feedback`) to the planner for a revised
  version (the API's `revise`).

A row: {"check": "Asked: colours", "status": "pass" | "failed" | "info", "detail": ..., "from":
"prompt", "where": "plan" | "level" | "play" | "ad" | None}. `where` says which stage missed it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import brief as B

NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
           "ten": 10, "eleven": 11, "twelve": 12}
_NUM = r"(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
COLOUR_SLOTS = {"green": "Green", "yellow": "Yellow", "blue": "Blue", "red": "Red", "orange": "Orange",
                "purple": "Purple", "dark green": "DarkGreen", "darkgreen": "DarkGreen"}
_COLOUR = r"(dark green|darkgreen|green|yellow|blue|red|orange|purple)"
_SHAPE = re.compile(r"\b(narrow (centre|center|middle|corridor|passage|section|waist|gap)|central (corridor|passage)|"
                    r"corridor|bottleneck|hourglass|waist)\b", re.I)
# "mirror" alone is a transform of a reference ("a left-right mirror image of this board", 2026-10-19 V2), not an ask for a
# mirror-symmetric board
_SYM = re.compile(r"symmetr|mirror[- ]?(symmetric|symmetry)|\bmirrored (board|layout|level)\b(?![^.;]{0,20}\b(of|from|as) (this|that|the)\b)", re.I)
_PACKED = re.compile(r"\b(packed|crowded|cramped|dense|compact)\b|limited (free |empty )?(space|room)|little (free |empty )?(space|room)", re.I)
_SPACIOUS = re.compile(r"\bspacious\b|(?<!block )(?<!blocks )room to move|plenty of (free |empty )?(space|cells|room)|enough (free |empty )?space|not crowded", re.I)
_NO_MISTAKES = re.compile(r"\b(without|no|zero) (any )?(mistakes?|wrong moves?|errors?|misstep)|mistake-free|flawless|efficiently without mistakes", re.I)
# one mistake: "a wrong move", "one unnecessary move", "an obvious but unhelpful move", "into an unhelpful position",
# "a move that blocks the green block's route", "gets stuck"; a near-fail or "almost fails" is an ending, not a count
_A_MISTAKE = re.compile(r"\b(a|an|one|single) (?:\w+ ){0,2}(wrong|mistaken|unhelpful|bad|unnecessary|pointless|tempting|misleading)(?: \w+){0,2} "
                        r"(move|drag|attempt|step|turn)s?\b|\b(a|one) mistake\b|\bwrong block first\b|"
                        r"\binto an? (unhelpful|wrong|bad|useless) (empty )?(position|spot|place|space|cell|corner)\b|"
                        r"\bmove[^.;]{0,60}\b(blocks|blocking|obstructs|cuts off) (the )?\w+ block'?s? (route|path|way)\b|"
                        r"\bits movement stops\b|\bgets? stuck\b", re.I)
_N_MISTAKES = re.compile(r"\b(two|three|2|3) (?:\w+ ){0,2}(wrong|mistaken|unhelpful|bad|unnecessary) (moves|drags|attempts)\b|"
                         r"\b(two|three|2|3) mistakes\b", re.I)
_TIME_OUT = re.compile(r"\b(runs? out of time|out of time|(the )?(time|timer|clock) (should |will |would |must |can |to )?(runs?|running) out|"
                       r"fails? the level|loses? the level|(timer|clock) (should |will )?(hits?|reach(es)?) (zero|0)|out of time screen|"
                       r"(time|the clock) (ends|expires|is up) before)\b", re.I)
# "almost runs out of time before clearing it" is a near-fail, not a time-out (the owner, 2026-10-17, F3: the image
# workflow's A2 read it as a time-out and revised for it); a plain "runs out of time" stays a time-out
_ALMOST_OUT = re.compile(r"\b(almost|nearly|barely|just about|about to|close to)\s+(runs?|running|ran)\s+out of time\b|"
                         r"\balmost (runs?|running|ran) out\b", re.I)
_CLOCK_LEFT = (re.compile(rf"\b(?P<n>{_NUM})\s*(s|sec|secs|seconds?)\s+(left|remaining|to spare|on the (clock|timer))\b", re.I),
               re.compile(rf"\b(with|and)\s+(approximately |about |roughly |around |only )?(?P<n>{_NUM})\s*(s|sec|secs|seconds?)\s+(left|remaining)\b", re.I))
_LENGTH = re.compile(rf"\b(\d{{2}})[\s-]*(s|sec|secs|second|seconds)\b(?!\s*(left|remaining|to spare|on the|clock|timer|time limit))", re.I)
# A range ("a new 30–60 second ad", "30-60s", "30 to 60 seconds", "between 30 and 60 seconds"): on the video-reference
# path (asked(..., case_range=True)) one whose ends lie in the brief's own 30-60 s restates the brief and is no stated
# length (round 3, 2026-10-17: "30–60 second" was read as 60 s, and three ads were made 60 s long with 10-41 s end cards);
# it is kept as length_range (info). The text and image workflows read it as before (the owner: they keep their behaviour)
_LENGTH_RANGE = re.compile(r"\b(?:between\s+)?(\d{2})\s*(?:s|sec|secs|seconds?)?\s*(?:-|–|—|to|and)\s*(\d{2})[\s-]*"
                           r"(s|sec|secs|second|seconds)\b", re.I)
CASE_RANGE_S = (30, 60)
_BLOCKS = re.compile(rf"\b{_NUM}\s+(?:different(?:ly)?[\s-]*)?(?!(?:dark green|green|yellow|blue|red|orange|purple)\b)"
                     rf"(?:colou?red|colou?r|colou?rful|small|large|big|long|mixed|various|assorted|\w+ and \w+|\w+)?\s*(blocks?|pieces?)\b"
                     r"(?!\s*(?:left|remain|remaining|still|are left|on the board|close to|near|trapped|boxed|is|in the way|of each|per colou?r|each))", re.I)
# "while three blocks remain", "with two blocks left", "leave one green block close to its door", "one red block is
# trapped": a count of what is left or a pointer at one block, never the board's block count (audit 2026-10-15)
_LEFT_CONTEXT = re.compile(r"\b(remain|remaining|left|still on|trapped|boxed in|close to its|near its|stuck)\b", re.I)
# "stop before the last three blocks leave", "the final two blocks", "with three blocks left": the blocks left at a
# cliffhanger's cut, never the board's block count (the owner, 2026-10-17, F5: B1 read "the last three blocks" as 3 blocks)
_LAST_N = re.compile(rf"\b(?:the\s+)?(?:last|final)\s+(?P<n>{_NUM})\s+(?:\w+\s+)?(?:blocks?|pieces?)\b", re.I)
_N_LEFT = re.compile(rf"\b(?P<n>{_NUM})\s+(?:\w+\s+)?(?:blocks?|pieces?)\s+(?:left|remaining|still on the board)\b", re.I)
_COLOURED = re.compile(rf"\b{_NUM}\s+(?:different(?:ly)?[\s-]*)?(?:colou?red|colou?r|colou?rful)\s+(blocks?|pieces?)\b", re.I)
_REL_BLOCKS_AFTER = re.compile(r"\s*(fewer|more|less|extra)\b", re.I)
_REL_BLOCKS_BEFORE = re.compile(r"\b(more|fewer|less|extra|additional|remove|add|drop|take away)\s*$", re.I)
_N_COLOURS = re.compile(rf"\b{_NUM}\s+(different\s+)?(colou?rs|shades|hues)\b", re.I)
_PALETTE = re.compile(rf"\b((?:{_COLOUR}(?:,\s*|\s+and\s+|\s+&\s+|\s*/\s*)?)+)\s+(?:\w+\s+){{0,2}}(blocks?|pieces?)\b", re.I)
_DIFFICULTY = (("hard", re.compile(r"\b(hard|difficult|tough|tricky|challenging|brutal)\b", re.I)),
               ("easy", re.compile(r"\b(easy|simple|beginner[- ]friendly|gentle|relaxed)\b", re.I)),
               ("medium", re.compile(r"\b(medium|moderate|mid-level|intermediate)\b", re.I)))
_STUCK_BY = re.compile(rf"\b(?P<mover>{_COLOUR})\s+block\b[^.]{{0,80}}\b(stops?|stopped|blocked|stuck|can't|cannot)\b[^.]{{0,60}}\b(because|by|as)\b[^.]{{0,20}}\b(?P<blocker>{_COLOUR})\s+block", re.I)
# "sends the yellow block into a position that blocks the green block's route", "moving the green block into an
# unhelpful position, briefly blocking the blue block's route", "moving a blue block into an unhelpful empty space,
# which temporarily prevents another block": a wrong move by a named block that gets in another block's way
_BLOCKS_BY = re.compile(rf"\b(?P<mover>{_COLOUR})\s+block\b[^.;]{{0,40}}\binto (a|an|the)\b[^.;]{{0,30}}?\b(position|spot|place|space|cell|corner|row|column)\b"
                        rf"[^.;]{{0,40}}?\b(blocks?|blocking|prevents?|obstructs?|cuts off|in the way of)\b[^.;]{{0,25}}?\b(?P<victim>{_COLOUR})\s+block|"
                        rf"\b(?P<mover2>{_COLOUR})\s+block\b[^.;]{{0,30}}\b(in|into)\s+(the\s+)?(?P<victim2>{_COLOUR})\s+block'?s?\s+(way|path|route)\b|"
                        rf"\b(?P<mover3>{_COLOUR})\s+(block\s+)?(slides?|moves?|is moved|goes|drifts?)\s+(into|in)\s+(the\s+)?(?P<victim3>{_COLOUR})\s+block'?s?\s+(way|path|route)\b|"
                        rf"\b(sends?|puts?|pushes|moves?|drags?)\s+(the\s+)?(?P<mover4>{_COLOUR})\s+(block\s+)?into (a|an|the)\b[^.;]{{0,30}}?\b(position|spot|place|space|cell|corner)\b"
                        rf"[^.;]{{0,30}}?\b(blocks?|blocking|prevents?|obstructs?|cuts off)\b[^.;]{{0,20}}?\b(?P<victim4>{_COLOUR})('?s)?\s+(block|door|route|path|way|exit)", re.I)
_BLOCKS_ANY = re.compile(rf"\b(?P<mover>{_COLOUR})\s+block\b[^.;]{{0,40}}\binto (a|an|the)\b[^.;]{{0,30}}?\b(unhelpful|wrong|bad)\b[^.;]{{0,20}}?\b(position|spot|place|space|cell|corner)\b"
                         r"(?:[^.;]{0,50}?\b(blocks?|blocking|prevents?|obstructs?|in the way)\b)?", re.I)
_SETUP = re.compile(r"\b(at the start|at first|initially|to begin with|sits in|sitting in|is in the way|cannot reach|can'?t reach|"
                    r"is blocked by|blocked by|trapped|boxed in|arrange|set up so|set it up)\b", re.I)
_MOVE_VERB = re.compile(r"\b(moves?|moved|moving|slides?|slid|sends?|sent|puts?|pushes|pushed|drags?|dragged|shifts?|parks?|ends up)\b", re.I)
_ATTEMPT = re.compile(r"\b(tries|tried|trying|attempts?|drags?|dragged|is stopped|gets stopped|bumps?|pulls?)\b", re.I)
_SATISFY = re.compile(r"satisfying|cascade|chain|one after another|quick sequence of (successful )?exits|in a row|flow", re.I)
# ---- added 2026-10-16: the brief's controls the audit did not measure (visuals, assets, sequence, unchanged),
# the hesitations, the clock, the walls, the HUD number, per-colour counts and a caption's moment
_NO_HES = re.compile(r"\b(no|without( any)?|zero) (hesitations?|pauses)\b", re.I)
_HES_N = ((re.compile(r"\b(hesitates|pauses|stops to think|doubts)\s+(?P<n>once|twice|three times|two times|\d)\b", re.I), None),
          (re.compile(rf"\b(?P<n>{_NUM})\s+(short |brief |long |visible |small )?(hesitations|pauses)\b", re.I), None),
          (re.compile(r"\b(hesitates|hesitation)\b[^.;]{0,60}\b(and (again|then|once more)|a second time)\b", re.I), 2),
          (re.compile(r"\b(hesitates|a hesitation|one hesitation)\b", re.I), 1))
_HES_WORDS = {"once": 1, "twice": 2, "two times": 2, "three times": 3}
_TIMER = (re.compile(r"\b(?P<n>\d{2,3})[\s-]*(s|sec|second)\s+(clock|timer|time limit)\b", re.I),
          re.compile(r"\b(clock|timer)\s+(of|set to|at|with|starting at|starts at)\s+(?P<n>\d{2,3})\s*(s|sec|secs|seconds?)\b", re.I))
_NO_WALLS = re.compile(r"\b(no|without( any)?|zero) (fixed |inner |interior |wall )?(walls?|wall tiles|wall cells|blocked cells)\b", re.I)
_WALLS = re.compile(rf"\b(?P<n>{_NUM}|several|a few|some|multiple|many|a couple of)\s+(?P<sep>separate\s+|fixed\s+|inner\s+|interior\s+|scattered\s+)*"
                    r"(walls?|wall tiles|wall cells|wall segments|blocked cells)\b", re.I)
_SOME_WALLS = re.compile(r"\b(fixed|inner|interior|separate) walls?\b|\bwall tiles\b|\bwalls\b", re.I)
_LABEL = re.compile(r"\blevel\s+(?P<n>\d{1,4})\b(?!\s*(s|sec|seconds?|-second|blocks?|colou?rs?|moves?))", re.I)
_COLOUR_COUNT = re.compile(rf"\b(?P<n>{_NUM})\s+(?:\w+\s+)?(?P<c>{_COLOUR})\s+blocks?\b", re.I)
_ONE_EACH = re.compile(rf"\bone (block )?(of )?each\b[^.;]{{0,20}}?\b((?:{_COLOUR}(?:,\s*|\s+and\s+|\s+&\s+)?)+)|"
                       rf"\bone block of each\b|\bone of each colou?r\b", re.I)
_CURSOR_HAND = re.compile(r"\b(pointing[- ]hand|hand|finger)\s+(cursor|pointer|icon)\b|\bpointing hand\b", re.I)
_CURSOR_NONE = re.compile(r"\b(no |without (a |the )?|hide the |remove the )(cursor|tap ring|pointer)\b", re.I)
_MUSIC_OFF = re.compile(r"\b(no|without( any)?|remove the|mute the|drop the) (background )?music\b|\bmusic off\b|\bsilent\b", re.I)
_MUSIC_ON = re.compile(r"\b(upbeat|calm|energetic|background|cheerful|soft|with|add|some|a)\s+(\w+\s+)?music\b|\bmusic track\b|\bsoundtrack\b", re.I)
_RESULT_FIRST = re.compile(r"\b(show|showing|start(s|ing)? with|open(s|ing)? (with|on)) the (win|result|win screen|ending|cleared board) first\b|"
                           r"\b(win|result|result screen) first\b", re.I)
_NO_REPLAY = re.compile(r"\b(no |without (a |the )?|skip the |remove the |drop the )(slow[- ]motion |slow-mo )?replay\b", re.I)
_REPLAY = re.compile(r"\b(slow[- ]motion |slow-mo )?replay\b", re.I)
_NO_END_CARD = re.compile(r"\b(no |without (an |the )?|skip the |remove the )end[- ]card\b", re.I)
_END_CARD = re.compile(r"\bend[- ]card\b", re.I)
_NO_RESULT = re.compile(r"\b(no |without (a |the )?|skip the )(result|win|fail) screen\b", re.I)
_ORIGINAL = re.compile(r"\b(original|the game'?s own|standard|unchanged|default|real|actual|authentic) (game |color block jam |cbj )?"
                       r"(rules|hud|visuals|look|assets|mechanics|block assets|block shapes|art|graphics|gameplay mechanics)\b|"
                       r"\bpreserve the original\b|\bkeep the (game'?s )?(own )?(rules|hud|look|assets|visuals)\b|\b(rules|hud) (and \w+ )?unchanged\b", re.I)
_BG = None  # built on first use from reference.NAMED
_CAP_MOMENTS = (("start", re.compile(r"\b(at|as) the (start|beginning|opening|top)\b|\bopening (caption|line|text)\b|\bas the hook\b|\bhook (caption|line)\b|\bat the very start\b", re.I)),
                ("wrong_move", re.compile(r"\bon (that|the wrong|the bad|the mistaken|this) (move|drag)\b|\bon the mistake\b|\bwhen (the )?(mistake|wrong move) (is made|happens)\b|\bon the error\b", re.I)),
                ("fix", re.compile(r"\bon the (correction|fix|move back|recovery)\b|\bwhen it is (moved|put) back\b|\bon the fix\b|\bwhen the player (corrects|fixes)\b", re.I)),
                ("exit", re.compile(rf"\b(when|as|once) (the )?(?P<c>{_COLOUR}) (block )?(leaves|exits|clears|goes out|is cleared|slides out)\b", re.I)),
                ("result", re.compile(r"\bon (it|the result|the result screen|the win screen|the out of time screen|the fail screen|the time-?out screen|the time-?out|the win|the cleared board)\b|\bscreen with (the )?(caption|text|line)\b|\bon the (result|ending) screen\b", re.I)),
                ("end", re.compile(r"\bin the (last|final) (few |two |three |five )?seconds\b|\bnear the end\b|\bat the end\b|\bas (the )?time runs (low|out)\b|\bwhen the clock (is|gets) low\b", re.I)),
                ("question", re.compile(r"\bat the cut\b|\bon the cut\b|\bending on the question\b|\bas the (closing )?question\b|\bend(s|ing)? on\b", re.I)))


def _n_words(s: str) -> int | None:
    s = s.lower().strip()
    if s in _HES_WORDS:
        return _HES_WORDS[s]
    if s.isdigit():
        return int(s)
    return NUMBERS.get(s)


def _n(s: str) -> int:
    s = s.lower()
    return NUMBERS.get(s) or int(s)


def asked(prompt: str, case_range: bool = False) -> dict:
    """The measurable facts in a prompt. Absent facts are None (not asked). `case_range` (the video-reference workflow
    only): a range inside the brief's 30-60 s is no length (length_s None, length_range kept)."""
    p = re.sub(r"\bcolou?r[\s-]*block[\s-]*jam\b", " ", prompt, flags=re.I)  # the game's name
    out: dict = {"blocks": None, "colours": None, "colour_names": [], "difficulty": None, "length_s": None,
                 "clock_left_s": None, "captions": [], "mistakes": None, "shape": None, "style": [], "ending": None,
                 "stuck_by": None, "blocks_by": None, "satisfying": bool(_SATISFY.search(p)),
                 # 2026-10-16
                 "hesitations": None, "timer_s": None, "walls": None, "walls_separate": False, "label": None,
                 "colour_counts": {}, "cursor": None, "music": None, "background": None,
                 "sequence": {}, "original": False, "caption_moments": [], "blocks_left": None}
    m = _COLOURED.search(p)
    if m:
        out["blocks"] = out["colours"] = _n(m.group(1))
    else:
        m = _N_COLOURS.search(p)
        if m:
            out["colours"] = _n(m.group(1))
        text = re.sub(_N_COLOURS.pattern, " ", p, flags=re.I)
        for m in _BLOCKS.finditer(text):
            if "colou" in m.group(0).lower():
                continue
            if _LEFT_CONTEXT.search(text[m.end():m.end() + 40]) or _LEFT_CONTEXT.search(text[max(0, m.start() - 25):m.start()]):
                continue
            if re.search(r"\b(last|final)\s+$", text[max(0, m.start() - 12):m.start()], re.I):
                continue  # "the last three blocks": blocks left at the cut (_LAST_N), not the count
            if _REL_BLOCKS_AFTER.match(text[m.end():m.end() + 14]) or _REL_BLOCKS_BEFORE.search(text[max(0, m.start() - 14):m.start()]) \
                    or re.search(r"\b(more|fewer|less|extra|additional)\b", m.group(0), re.I):
                continue  # "two blocks fewer", "two more blocks": a change against a reference (imageplan.BLOCKS_REL), not a count
            out["blocks"] = _n(m.group(1))
            break
    m = _LAST_N.search(p) or _N_LEFT.search(p)
    if m and _n(m.group("n")) in (1, 2, 3):
        out["blocks_left"] = _n(m.group("n"))
    for m in _PALETTE.finditer(p):
        names = [COLOUR_SLOTS[c.lower()] for c in re.findall(_COLOUR, m.group(1), flags=re.I)]
        if len(names) >= 2:  # "red, blue and green blocks": a palette; "the red block" alone points at a block
            out["colour_names"] = list(dict.fromkeys(out["colour_names"] + names))
    for word, rx in _DIFFICULTY:
        if rx.search(p):
            out["difficulty"] = word
            break
    single = p
    if case_range:
        out["length_range"] = None
        for m in _LENGTH_RANGE.finditer(p):
            lo, hi = int(m.group(1)), int(m.group(2))
            if CASE_RANGE_S[0] <= lo < hi <= CASE_RANGE_S[1]:
                out["length_range"] = (float(lo), float(hi))
                single = single.replace(m.group(0), " ")
    m = _LENGTH.search(single)
    if m and 10 <= int(m.group(1)) <= 90:
        out["length_s"] = float(m.group(1))
    for rx in _CLOCK_LEFT:
        m = rx.search(p)
        if m:
            out["clock_left_s"] = _n(m.group("n"))
            break
    # 'change "A" to "B"' / 'from "A" to "B"' / 'replace "A" with "B"': A is the old text, not asked (2026-10-18: an
    # edit's old caption was checked as missing from the plan)
    old_quotes = {q for m in re.finditer(r"\b(?:from|change|replace|rename|instead of)\s+(\"[^\"]{1,120}\"|“[^”]{1,120}”)\s+(?:to|with|into|by)\b",
                                         prompt, re.I) for q in B.QUOTED.findall(m.group(1)) for q in [q[0] or q[1]]}
    out["captions"] = [q[0] or q[1] for q in B.QUOTED.findall(prompt) if (q[0] or q[1]) not in old_quotes]
    stuck_n = re.search(r"\b(?:gets?|got|is|be|being)?\s*stuck\s+(once|twice|two times|three times|\d)\b", p, re.I)
    if _NO_MISTAKES.search(p):
        out["mistakes"] = 0
    elif stuck_n:
        out["mistakes"] = _n_words(stuck_n.group(1))  # "gets stuck twice" (2026-10-19, S6: read as one mistake)
    elif _N_MISTAKES.search(p):
        m = _N_MISTAKES.search(p)
        out["mistakes"] = _n(m.group(1) or m.group(4))  # group 4: the bare "two mistakes" alternative
    elif _A_MISTAKE.search(p):
        out["mistakes"] = 1
    to = _TIME_OUT.search(_ALMOST_OUT.sub(" ", p))
    if to and re.search(r"\b(instead of|rather than|not|no longer|without|never)\s*$", p[max(0, to.start() - 16):to.start()], re.I):
        to = None  # "...win with one second left instead of running out of time": the time-out is the old ending (2026-10-18)
    if to:
        out["ending"] = "time_out"
    elif _ALMOST_OUT.search(p) or \
            re.search(r"almost fails?|near[- ]fail|nearly (fails?|loses?)|barely|just in time|seconds? (left|remaining)", p, re.I):
        out["ending"] = "near_fail"
    elif re.search(r"\b(clean|perfect|flawless) (solve|win|run)\b|without mistakes|solves? (it|the puzzle) (efficiently|cleanly)", p, re.I):
        out["ending"] = "win"
    if _SHAPE.search(p):
        out["shape"] = "narrow_center"
    if _SYM.search(p):
        out["style"].append("symmetric")
    if _PACKED.search(p):
        out["style"].append("packed")
    if _SPACIOUS.search(p):
        out["style"].append("spacious")
    m = _STUCK_BY.search(p)
    if m and not _ATTEMPT.search(p[max(0, m.start() - 40):m.end()]) and _SETUP.search(p[max(0, m.start() - 40):m.end()]):
        m = None  # "the red block cannot reach its door because green is in the way": the arrangement, not an attempt
    if m:
        out["stuck_by"] = (COLOUR_SLOTS[m.group("mover").lower()], COLOUR_SLOTS[m.group("blocker").lower()])
    m = _BLOCKS_BY.search(p)
    if m and m.group("mover2") and not _MOVE_VERB.search(m.group(0)) and _SETUP.search(p[max(0, m.start() - 40):m.end()]):
        m = None  # "at the start the green block sits in the red block's route": the arrangement, not a move
    if m:
        mover = m.group("mover") or m.group("mover2") or m.group("mover3") or m.group("mover4")
        victim = m.group("victim") or m.group("victim2") or m.group("victim3") or m.group("victim4")
        out["blocks_by"] = (COLOUR_SLOTS[mover.lower()], COLOUR_SLOTS[victim.lower()])
    else:
        m = _BLOCKS_ANY.search(p)
        if m:
            out["blocks_by"] = (COLOUR_SLOTS[m.group("mover").lower()], None)
    if out["blocks_by"] and out["mistakes"] is None:
        out["mistakes"] = 1
    _asked_more(p, prompt, out)
    return out


def _asked_more(p: str, prompt: str, out: dict) -> None:
    """The facts added on 2026-10-16 (see the regexes above)."""
    if _NO_HES.search(p):
        out["hesitations"] = 0
    else:
        for rx, fixed in _HES_N:
            m = rx.search(p)
            if m:
                out["hesitations"] = fixed if fixed is not None else _n_words(m.group("n"))
                break
    for rx in _TIMER:
        m = rx.search(p)
        if m:
            out["timer_s"] = int(m.group("n"))
            break
    if _NO_WALLS.search(p):
        out["walls"] = 0
    else:
        m = _WALLS.search(p)
        if m:
            w = m.group("n").lower()
            out["walls"] = _n_words(w) if (w.isdigit() or w in NUMBERS) else "several"
            out["walls_separate"] = "separate" in (m.group(0) or "").lower()
        elif _SOME_WALLS.search(p):
            out["walls"] = "some"
    m = _LABEL.search(p)
    if m:
        out["label"] = int(m.group("n"))
    for m in _COLOUR_COUNT.finditer(p):
        if _LEFT_CONTEXT.search(p[m.end():m.end() + 30]):  # "one red block is trapped": a pointer, not a count
            continue
        out["colour_counts"].setdefault(COLOUR_SLOTS[m.group("c").lower()], _n(m.group("n")))
    m = _ONE_EACH.search(p)
    if m:
        names = [COLOUR_SLOTS[c.lower()] for c in re.findall(_COLOUR, m.group(3) or "", flags=re.I)] or out["colour_names"]
        for c in names:
            out["colour_counts"].setdefault(c, 1)
    if _CURSOR_NONE.search(p):
        out["cursor"] = "none"
    elif _CURSOR_HAND.search(p):
        out["cursor"] = "hand"
    if _MUSIC_OFF.search(p):
        out["music"] = False
    elif _MUSIC_ON.search(p):
        out["music"] = True
    global _BG
    if _BG is None:
        from .reference import NAMED
        names = sorted(NAMED, key=len, reverse=True)
        _BG = re.compile(r"\b(?:a |an |the )?(?:soft |light |pale |deep |dark |warm |cool |muted |bright )?(?P<c>" + "|".join(re.escape(n) for n in names)
                         + r")(?: |-)(?:coloured |colored |toned )?(background|backdrop)\b", re.I)
    m = _BG.search(p)
    if m:
        out["background"] = m.group("c").lower()
    seq = {}
    if _RESULT_FIRST.search(p):
        seq["result_first"] = True
    if _NO_REPLAY.search(p):
        seq["replay"] = False
    elif _REPLAY.search(p):
        seq["replay"] = True
    if _NO_END_CARD.search(p):
        seq["end_card"] = False
    elif _END_CARD.search(p):
        seq["end_card"] = True
    if _NO_RESULT.search(p):
        seq["result_screen"] = False
    out["sequence"] = seq
    out["original"] = bool(_ORIGINAL.search(p))
    for m in B.QUOTED.finditer(prompt):
        text = m.group(1) or m.group(2)
        after, before = prompt[m.end():m.end() + 70], prompt[max(0, m.start() - 60):m.start()]
        after = re.split(r"[.;]|\band\s+[\"\u201c']", after)[0]
        found = None
        # the words right after the quote first (the earliest match), else the words before it (the latest, nearest the quote)
        for text_at, nearest in ((after, lambda mm: mm.start()), (before, lambda mm: -mm.end())):
            hits = [(nearest(mm), key, mm) for key, rx in _CAP_MOMENTS for mm in [rx.search(text_at)] if mm]
            if hits:
                _, key, mm = min(hits, key=lambda h: h[0])
                found = (key, COLOUR_SLOTS[mm.group("c").lower()] if key == "exit" else None)
                break
        if found:
            out["caption_moments"].append({"text": text, "moment": found[0], "colour": found[1]})


def _row(check: str, ok: bool | None, detail: str, where: str | None = None) -> dict:
    return {"check": f"Asked: {check}", "status": "pass" if ok else "info" if ok is None else "failed",
            "detail": detail, "from": "prompt", "where": None if ok else where}


def _level_facts(level_path: Path) -> dict:
    from .level import load_level
    lv = load_level(level_path)
    cells = {}
    for i, b in enumerate(lv.blocks):
        for c in b.cells_at(b.pivot):
            cells[c] = i
    # pieces a viewer can tell apart: blocks of one colour that touch (edge or corner) read as one
    parent = list(range(len(lv.blocks)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for (x, y), i in cells.items():
        for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
            j = cells.get((x + dx, y + dy))
            if j is not None and j != i and lv.blocks[i].color == lv.blocks[j].color:
                parent[find(i)] = find(j)
    visible = len({find(i) for i in range(len(lv.blocks))})
    from .describe import color_name
    names = [color_name(b.color) for b in lv.blocks]
    return {"blocks": len(lv.blocks), "colours": len(set(names)), "names": sorted(set(names)), "visible": visible,
            "level": lv}


def level_rows(prompt: str, brief: dict, level_path: Path, checks: list[dict] | None = None) -> list[dict]:
    """The rows that can be judged on the level alone (before recording)."""
    a = asked(prompt)
    lv = brief["level"]
    f = _level_facts(level_path)
    rows = []
    if a["blocks"] is not None:
        planned = lv["blocks"]
        if planned != a["blocks"]:
            rows.append(_row("block count", False, f"{a['blocks']} asked, the plan says {planned}, the board has {f['blocks']}", "plan"))
        else:
            rows.append(_row("block count", f["blocks"] == a["blocks"], f"{a['blocks']} asked, the board has {f['blocks']}", "level"))
    if a["colours"] is not None:
        planned = len(lv["colours"]) if lv["colours"] else None
        if planned is not None and planned < a["colours"] and "symmetric" not in (lv.get("style") or []):
            rows.append(_row("colours", False, f"{a['colours']} colours asked, the plan limits the board to {planned}", "plan"))
        else:
            rows.append(_row("colours", f["colours"] >= a["colours"], f"{a['colours']} colours asked, the board shows "
                             f"{f['colours']} ({', '.join(f['names'])})", "level"))
    if a["blocks"] is not None or a["colours"] is not None or a["colour_names"]:
        rows.append(_row("blocks a viewer can count", f["visible"] == f["blocks"],
                         f"{f['blocks']} blocks, {f['visible']} pieces a viewer can tell apart" +
                         ("" if f["visible"] == f["blocks"] else " (blocks of one colour touch and read as one piece)"), "level"))
    if a["colour_names"]:
        plain = lambda c: c.lower().replace("darkgreen", "dark green")  # noqa: E731
        missing = [c for c in a["colour_names"] if plain(c) not in [n.lower() for n in f["names"]]]
        # a palette is exclusive: "red, blue, green and yellow blocks" means no orange (P6-a, audit 2026-10-15);
        # a colour named anywhere in the prompt ("one larger yellow block") is allowed too
        allowed = {plain(c) for c in a["colour_names"]} | {c.lower() for c in re.findall(_COLOUR, prompt, flags=re.I)}
        extra = sorted({n.lower() for n in f["names"]} - allowed)
        detail = ", ".join(c.lower() for c in a["colour_names"]) + " asked" + \
            ("; all on the board" if not missing else "; missing: " + ", ".join(c.lower() for c in missing)) + \
            ("; the board also has " + ", ".join(extra) + " (not asked)" if extra else "")
        rows.append(_row("named colours", not missing and not extra, detail,
                         "plan" if (any(c not in (lv["colours"] or []) for c in missing) and lv["colours"]) or
                         (extra and not lv["colours"]) else "level"))
    if a["blocks_by"]:
        mover, victim = a["blocks_by"]
        evs = brief["gameplay"].get("events") or []
        planned = next((e for e in evs if e["action"] == "blocks" and e["block"].get("colour") == mover), None)
        what = f"{mover.lower()} moved into {victim.lower() + chr(39) + 's' if victim else 'another block' + chr(39) + 's'} way asked"
        if planned is None or (victim and planned.get("by") != victim):
            rows.append(_row("the blocking move", False, what + f"; the plan {'has no such step' if planned is None else 'names no block it blocks'}", "plan"))
        else:
            from .events import from_brief
            from .play import blocking_moves
            from .rules import initial_state
            resolved, _ = from_brief(f["level"], evs)
            ev = next((e for e in resolved if e.action == "blocks"), None)
            offers = ev is not None and bool(blocking_moves(f["level"], initial_state(f["level"]), ev.blocks, ev.by))
            rows.append(_row("the blocking move", offers, what + f"; the board {'offers it at the start' if offers else 'does not offer it at the start'}", "level"))
    checks = checks if checks is not None else []
    by_name = {c["check"]: c for c in checks}
    if a["shape"]:
        c = by_name.get("Board shape")
        ok = c is not None and "narrow" in c["detail"]
        rows.append(_row("board shape", ok if c else (lv["shape"] == "narrow_center"),
                         "a narrow centre asked; " + (c["detail"] if c else f"the plan says {lv['shape']}"),
                         "level" if lv["shape"] == "narrow_center" else "plan"))
    if a["difficulty"]:
        c = by_name.get("Difficulty")
        if lv["difficulty"] != a["difficulty"]:
            rows.append(_row("difficulty", False, f"{a['difficulty']} asked, the plan says {lv['difficulty']}", "plan"))
        elif c:
            rows.append(_row("difficulty", c["status"] == "pass", c["detail"], "level"))
    for st in a["style"]:
        if st not in (lv.get("style") or []):
            rows.append(_row(f"{st} board", False, f"{st} asked, not in the plan", "plan"))
        else:
            c = by_name.get("Board looks")
            if c:
                rows.append(_row(f"{st} board", c["status"] == "pass", c["detail"], "level"))
    if a["stuck_by"]:
        mover, blocker = a["stuck_by"]
        evs = brief["gameplay"].get("events") or []
        planned = next((e for e in evs if e["action"] == "stuck" and e["block"].get("colour") == mover), None)
        if planned is None or planned.get("by") != blocker:
            rows.append(_row("the blocked attempt", False, f"{mover.lower()} stopped by a {blocker.lower()} block asked; "
                             f"the plan {'has no such step' if planned is None else 'names no blocker'}", "plan"))
        else:
            from .events import from_brief
            from .play import blocked_attempts
            from .rules import initial_state
            resolved, _ = from_brief(f["level"], evs)
            ev = next((e for e in resolved if e.action == "stuck"), None)
            offers = ev is not None and any(d.block in ev.blocks and (not ev.by or b in ev.by)
                                            for d, b in blocked_attempts(f["level"], initial_state(f["level"])))
            rows.append(_row("the blocked attempt", offers, f"{mover.lower()} stopped by a {blocker.lower()} block asked; "
                             f"the board {'offers it at the start' if offers else 'does not offer it at the start'}", "level"))
    rows += _level_rows_more(a, brief, f)
    return rows


def _components(cells) -> int:
    """How many separate groups the wall cells form (4-neighbour)."""
    left, n = set(tuple(c) for c in cells), 0
    while left:
        n += 1
        stack = [left.pop()]
        while stack:
            x, y = stack.pop()
            for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                c = (x + d[0], y + d[1])
                if c in left:
                    left.remove(c)
                    stack.append(c)
    return n


def _level_rows_more(a: dict, brief: dict, f: dict) -> list[dict]:
    """The rows added on 2026-10-16: walls, the clock, per-colour counts, and the board's interest
    (the brief p.5: "a visually interesting board")."""
    from .describe import color_name
    lv_, gp = f["level"], brief["gameplay"]
    rows = []
    if a["walls"] is not None:
        n, comps = len(lv_.inactive), _components(lv_.inactive)
        want = a["walls"]
        if want == 0:
            ok = n == 0
        elif want == "several":
            ok = n >= 2 and (not a["walls_separate"] or comps >= 2)
        elif want == "some":
            ok = n >= 1
        else:
            ok = n == want
        asked_s = "no walls" if want == 0 else f"{want}{' separate' if a['walls_separate'] else ''} walls"
        rows.append(_row("walls", ok, f"{asked_s} asked; the board has {n} wall cell(s) in {comps} separate group(s)", "level"))
    if a["colour_counts"]:
        names = [color_name(b.color).lower() for b in lv_.blocks]
        plain = lambda c: c.lower().replace("darkgreen", "dark green")  # noqa: E731
        have = {c: names.count(plain(c)) for c in a["colour_counts"]}
        ok = all(have[c] == n for c, n in a["colour_counts"].items())
        rows.append(_row("blocks per colour", ok, "asked " + ", ".join(f"{n} {plain(c)}" for c, n in a["colour_counts"].items())
                         + "; the board has " + ", ".join(f"{have[c]} {plain(c)}" for c in a["colour_counts"]), "level"))
    try:
        from .generate import piece_kinds
        kinds = sorted(piece_kinds(lv_))
    except Exception:
        kinds = []
    rows.append(_row("a visually interesting board (the brief)", None,
                     f"{lv_.width}x{lv_.height}, {len(lv_.blocks)} blocks in {f['colours']} colours, "
                     f"{', '.join(kinds) or 'mixed'} pieces, {len(lv_.inactive)} wall cell(s), {len(lv_.exits)} doors"))
    return rows


def level_misses(prompt: str, brief: dict, level_path: Path, checks: list[dict] | None = None) -> list[dict]:
    """The level-stage rows the generator could still fix with another board."""
    return [r for r in level_rows(prompt, brief, level_path, checks) if r["status"] == "failed" and r["where"] == "level"]


def ad_rows(prompt: str, brief: dict, record: dict, vdir: Path, rec_dir: Path | None = None) -> list[dict]:
    """The rows judged on the recording and the finished ad. A video-reference version reads the brief's range as no
    length (asked(..., case_range=True)); every other workflow as before."""
    a = asked(prompt, case_range=_ref_video(brief) is not None)
    checks = record.get("checks") or []
    by_name = {c["check"]: c for c in checks}
    rows = []
    length = record.get("length_s")
    if length is not None:
        rows.append(_row("30-60 s (the brief)", 29.5 <= length <= 60.5, f"the ad is {length} s", "ad"))
        if a["length_s"] is not None:
            if brief["pacing"]["length_s"] != a["length_s"]:
                rows.append(_row("length", False, f"{a['length_s']:g} s asked, the plan says {brief['pacing']['length_s']:g} s", "plan"))
            else:
                rows.append(_row("length", abs(length - a["length_s"]) <= 1.0, f"{a['length_s']:g} s asked, the ad is {length} s", "ad"))
        elif a.get("length_range"):
            lo, hi = a["length_range"]
            rows.append(_row("length range", None, f"{lo:g}-{hi:g} s restates the brief's range, so no single length is asked; "
                                                   f"the ad is {length} s", None))
    if a["clock_left_s"] is not None:
        c = by_name.get("Ending")
        if brief["gameplay"].get("clock_left_s") != a["clock_left_s"]:
            rows.append(_row("seconds left", False, f"{a['clock_left_s']} s left asked, the plan says {brief['gameplay'].get('clock_left_s')}", "plan"))
        elif c:
            m = re.search(r"00:0?(\d+) on the clock", c["detail"])
            left = int(m.group(1)) if m else None
            rows.append(_row("seconds left", left == a["clock_left_s"], c["detail"], "play"))
    if a["mistakes"] is not None:
        c = by_name.get("Mistakes")
        if brief["gameplay"].get("mistakes") not in (None, a["mistakes"]) and brief["gameplay"].get("mistakes") != a["mistakes"]:
            rows.append(_row("mistakes", False, f"{a['mistakes']} asked, the plan says {brief['gameplay']['mistakes']}", "plan"))
        elif c:  # the count alone; who is in the way is its own row
            m = re.search(r"(\d+) mistake\(s\) played \(asked: (\d+)", c["detail"])
            ok = bool(m) and m.group(1) == m.group(2)
            rows.append(_row("mistakes", ok, c["detail"].split(" (asked: stopped")[0], "play"))
    if a["stuck_by"]:
        c = by_name.get("Mistakes")
        if c and "asked: stopped by" in c["detail"]:
            rows.append(_row("the block in the way", "another block stops it" not in c["detail"], c["detail"], "play"))
    if a["blocks_by"]:
        c = by_name.get("Mistakes")
        if c:
            mover = a["blocks_by"][0].lower().replace("darkgreen", "dark green")
            played = re.search(rf"\(({mover})\) moves into [^;]*'s way", c["detail"]) is not None
            rows.append(_row("the blocking move played", played, c["detail"].split(" (asked:")[0] +
                             ("" if played else f"; no drag moves the {mover} block into another block's way"), "play"))
    c = by_name.get("Order of interactions")
    if c:
        rows.append(_row("order of interactions", c["status"] == "pass", c["detail"], "play"))
    if a["satisfying"]:
        c = by_name.get("Satisfying finish") or by_name.get("Finish")
        if c:
            rows.append(_row("satisfying finish", c["status"] in ("pass", "info"), c["detail"], "play"))
    if a["ending"]:
        if brief["gameplay"]["ending"] != a["ending"] and not (a["ending"] == "near_fail" and brief["gameplay"]["ending"] == "near_fail"):
            rows.append(_row("ending", False, f"{a['ending'].replace('_', '-')} asked, the plan says {brief['gameplay']['ending'].replace('_', '-')}", "plan"))
        else:
            c = by_name.get("Ending")
            if c:
                rows.append(_row("ending", c["status"] == "pass", c["detail"], "play"))
    if a["captions"]:
        texts = []
        try:
            compose = json.loads((vdir / "ad" / "compose.json").read_text())
            texts = [lay.get("text", "") for lay in compose["layers"].values() if lay.get("type") in ("text", "button", "tag")]
        except (OSError, KeyError, ValueError):
            pass
        for q in a["captions"]:
            shown = any(q.strip().lower() in t.lower() for t in texts)
            planned = any(q.strip().lower() in str(v).lower() for v in brief["concept"].values() if isinstance(v, str))
            rows.append(_row(f'caption "{q}"', shown, "on screen" if shown else ("in the plan but not on screen" if planned else "not in the plan"),
                             "ad" if planned else "plan"))
    rows += _ad_rows_more(a, brief, record, vdir, rec_dir)
    return rows


COLOUR_FAMILIES = {
    "beige": {"beige", "cream", "sand", "ivory", "butter", "peach"}, "white": {"white", "ivory", "cream"},
    "grey": {"grey", "light grey", "dark grey"}, "black": {"black", "dark grey"}, "brown": {"brown", "sand"},
    "blue": {"blue", "navy", "sky blue", "sea blue", "cyan", "teal"}, "navy": {"navy", "blue", "violet"},
    "green": {"green", "mint", "sage", "dark green", "lime", "pale green", "light green", "turquoise"},
    "red": {"red", "crimson", "coral", "salmon"}, "pink": {"pink", "hot pink", "rose", "light pink", "salmon"},
    "orange": {"orange", "tangerine", "peach", "coral"}, "yellow": {"yellow", "lemon", "butter", "gold"},
    "purple": {"purple", "violet", "lilac", "lavender", "grape"},
}


def nearest_named(rgb) -> str:
    from .reference import NAMED, _rgb
    r, g, b = rgb
    return min(NAMED, key=lambda n: sum((x - y) ** 2 for x, y in zip(_rgb(NAMED[n]), (r, g, b))))


def same_family(asked_name: str, seen_name: str) -> bool:
    if asked_name == seen_name:
        return True
    fams = [f for f, members in COLOUR_FAMILIES.items() if asked_name in members or asked_name == f]
    return any(seen_name in COLOUR_FAMILIES[f] or seen_name == f for f in fams)


def poster_background(poster: Path):
    """The colour of the frame's margins on the poster (left and right of the board, mid-height)."""
    from PIL import Image
    im = Image.open(poster).convert("RGB")
    w, h = im.size
    pts = [(12, int(h * k)) for k in (0.38, 0.5, 0.62)] + [(w - 13, int(h * k)) for k in (0.38, 0.5, 0.62)]
    px = sorted(im.getpixel(p) for p in pts)
    return px[len(px) // 2]


def _ad_rows_more(a: dict, brief: dict, record: dict, vdir: Path, rec_dir: Path | None) -> list[dict]:
    """The rows added on 2026-10-16 for the brief's controls the audit did not measure: visual elements
    (cursor, background), assets (music), the sequence of events, what should stay the game's own, a
    caption's moment (from the parts manifest), the hesitations, the HUD number, and the brief's
    "gameplay at the centre" (p.2)."""
    rows = []
    gp = brief["gameplay"]
    j = lambda p: json.loads(p.read_text()) if p.is_file() else {}  # noqa: E731
    ad = j(vdir / "ad" / "ad.json")
    manifest = j(vdir / "parts.json")
    play = j(Path(rec_dir) / "play.json") if rec_dir else {}
    job = j(Path(rec_dir) / "job.json") if rec_dir else {}
    if a.get("blocks_left") is not None and gp["ending"] == "cliffhanger":
        # "stop before the last three blocks leave" (F5, 2026-10-17): the blocks that never left in the recording
        res = j(Path(rec_dir) / "result.json") if rec_dir else {}
        gone = res.get("block_gone_frames")
        if gone is None:
            rows.append(_row("blocks left at the cut", None, f"{a['blocks_left']} asked; the recording could not be read"))
        else:
            left = sum(1 for f in gone if f is None or f < 0)
            planned = gp.get("blocks_left")
            rows.append(_row("blocks left at the cut", left == a["blocks_left"],
                             f"{a['blocks_left']} asked; planned {planned if planned is not None else 'the default'}; the recording "
                             f"stops with {left} on the board", "plan" if planned not in (None, a["blocks_left"]) else "play"))
    if a["hesitations"] is not None and play:
        made = sum(1 for b in play.get("beats") or [] if b.get("kind") == "hesitate")
        if gp.get("hesitations") is not None and gp["hesitations"] != a["hesitations"]:
            rows.append(_row("hesitations", False, f"{a['hesitations']} asked, the plan says {gp['hesitations']} "
                                                   f"(a {gp['ending'].replace('_', '-')} shows at most {B.MAX_HESITATIONS[gp['ending']]})", "plan"))
        else:
            rows.append(_row("hesitations", made == a["hesitations"], f"{a['hesitations']} asked, {made} played (a block picked up and put down)", "play"))
    if a["timer_s"] is not None:
        # the clock the game ran with is in the recording (the play writes it into the recorded level), not
        # in the generated level file (2026-10-16: 2-clean's 90 s clock was read as 60 from the wrong file)
        res = j(Path(rec_dir) / "result.json") if rec_dir else {}
        start = res.get("timer_start")
        if gp["ending"] != "win":
            rows.append(_row("the clock", None, f"{a['timer_s']} s on the clock asked; a {gp['ending'].replace('_', '-')} lands on a "
                                                f"planned second, so the play sets the clock" + (f" ({start:g} s here)" if start is not None else "")))
        elif start is not None:
            why = (play.get("fit") or {}).get("why") if play else None
            if round(start) != a["timer_s"] and gp.get("timer_s") == a["timer_s"] and why:
                # the play changed the asked clock for a stated reason (play.fit_clock: the HUD turns red under
                # 0:50, so a 60 s clock would show red for the whole play): reported with the reason, not as a miss
                rows.append(_row("the clock", None, f"{a['timer_s']} s asked; the game's clock started at {start:g} s: {why}"))
            else:
                rows.append(_row("the clock", round(start) == a["timer_s"], f"{a['timer_s']} s asked; the game's clock started at {start:g} s",
                                 "plan" if gp.get("timer_s") != a["timer_s"] else "play"))
    if a["label"] is not None:
        shown = job.get("level_label") if job else brief["level"].get("label")
        rows.append(_row("HUD level number", shown == a["label"], f"level {a['label']} asked; the HUD shows level {shown}",
                         "plan" if brief["level"].get("label") != a["label"] else "play"))
    layers = ad.get("layers") or {}
    if a["cursor"] is not None and ad:
        cur = layers.get("cursor")
        seen = "none" if cur is None else ("hand" if cur.get("image") else "ring")
        rows.append(_row("cursor", seen == a["cursor"], f"a {a['cursor']} cursor asked; the ad shows {seen}" +
                         (" (the tap ring)" if seen == "ring" else ""), "plan" if brief["visuals"].get("cursor") != a["cursor"] else "ad"))
    if a["music"] is not None and ad:
        music = (ad.get("audio") or {}).get("music")
        has = bool(music and music.get("file"))
        rows.append(_row("music", has == a["music"], ("music asked; " if a["music"] else "no music asked; ") +
                         (f"the ad plays {Path(music['file']).name}" if has else "the ad has no music track"),
                         "plan" if bool(brief["audio"].get("music")) != a["music"] else "ad"))
    if a["background"] and (vdir / "ad" / "poster.png").is_file():
        try:
            rgb = poster_background(vdir / "ad" / "poster.png")
            seen = nearest_named(rgb)
            ok = same_family(a["background"], seen)
            rows.append(_row("background", ok, f"a {a['background']} background asked; the frame's margins are "
                                               f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X} (nearest named colour: {seen})",
                             "plan" if not brief["visuals"].get("background") and not brief["visuals"].get("background_image") else "ad"))
        except Exception as e:  # a poster that cannot be read is no reason to lose the audit
            rows.append(_row("background", None, f"a {a['background']} background asked; the poster could not be read ({e})"))
    order = ad.get("order") or [p["id"] for p in manifest.get("parts", [])]
    sq = a["sequence"]
    if sq and order:
        if sq.get("result_first"):
            ok = "result" in order and "play" in order and order.index("result") < order.index("play")
            rows.append(_row("the win first", ok, "the result shown first asked; the ad's order is " + ", ".join(order),
                             "plan" if brief["sequence"].get("style") != "result_first" else "ad"))
        if "replay" in sq:
            has = "replay" in order
            rows.append(_row("the replay", has == sq["replay"], ("a replay asked; " if sq["replay"] else "no replay asked; ") +
                             ("the ad has a replay part" if has else "the ad has no replay part"),
                             "plan" if bool(brief["sequence"].get("replay")) != sq["replay"] else "ad"))
        if "end_card" in sq:
            has = "end" in order
            rows.append(_row("the end card", has == sq["end_card"], ("an end card asked; " if sq["end_card"] else "no end card asked; ") +
                             ("the ad ends on the card" if has else "the ad has no end card"),
                             "plan" if bool(brief["sequence"].get("end_card")) != sq["end_card"] else "ad"))
        if "result_screen" in sq:
            has = "result" in order
            rows.append(_row("the result screen", has == sq["result_screen"], "no result screen asked; " +
                             ("the ad shows one" if has else "the ad has none"),
                             "plan" if bool(brief["sequence"].get("result_screen")) != sq["result_screen"] else "ad"))
    if a["original"]:
        v = brief["visuals"]
        changed = []
        if v.get("theme") not in (None, "game"):
            changed.append(f"theme {v['theme']}")
        if v.get("blocks"):
            changed.append("block colours repainted")
        if v.get("board"):
            changed.append("the board's colour")
        if not v.get("hud_timer", True) or not v.get("hud_level", True):
            changed.append("the HUD hidden")
        if any(x.get("role") in ("skin", "obstacle") for x in brief.get("assets") or []) or \
                any(l.get("type") in ("skin", "object") for l in layers.values()):
            changed.append("a block skin or an object on the board")
        rows.append(_row("the game's own look", not changed, "the original rules, HUD and assets asked; " +
                         ("the game's own look, HUD and block art are kept" if not changed else "changed: " + ", ".join(changed)), "plan"))
    if a["caption_moments"] and manifest:
        rows += _caption_moment_rows(a["caption_moments"], manifest)
    read = facts_read(a)
    rows.append(_row("facts read from the prompt", None, ("; ".join(read) if read else "none the audit measures") +
                     " (a phrasing the audit does not recognise gives no row; the viewer's review covers the rest)"))
    parts = manifest.get("parts") or []
    total = manifest.get("duration_s") or record.get("length_s")
    if parts and total:
        gameplay = sum((p["to_s"] or 0) - (p["from_s"] or 0) for p in parts if p.get("gameplay") or p["id"] == "result")
        share = gameplay / total
        rows.append(_row("gameplay at the centre (the brief)", share >= 0.4,
                         f"gameplay (play, replay, the result clip) is {gameplay:.1f} s of {total:g} s ({share:.0%}); the rest is "
                         f"held screens and the end card" + ("" if share >= 0.4 else "; shorter held screens or a replay would put the game back at the centre"),
                         "plan"))
    return rows


def facts_read(a: dict) -> list[str]:
    """The measurable facts a prompt gave, in words, so a version's checks show what was audited."""
    out = []
    simple = (("blocks", "{} blocks"), ("colours", "{} colours"), ("difficulty", "{}"), ("length_s", "{:g} s"), ("clock_left_s", "{} s left"),
              ("mistakes", "{} mistake(s)"), ("hesitations", "{} hesitation(s)"), ("timer_s", "a {} s clock"), ("label", "level {}"),
              ("shape", "shape {}"), ("ending", "ending {}"), ("cursor", "cursor {}"), ("background", "a {} background"))
    for k, fmt in simple:
        if a.get(k) is not None:
            out.append(fmt.format(a[k]))
    if a.get("length_range") and a.get("length_s") is None:
        out.append(f"{a['length_range'][0]:g}-{a['length_range'][1]:g} s (the brief's range, not a stated length)")
    if a.get("colour_names"):
        out.append("colours " + ", ".join(c.lower() for c in a["colour_names"]))
    if a.get("colour_counts"):
        out.append("per colour " + ", ".join(f"{n} {c.lower()}" for c, n in a["colour_counts"].items()))
    if a.get("walls") is not None:
        out.append(f"walls {a['walls']}" + (" (separate)" if a.get("walls_separate") else ""))
    if a.get("style"):
        out.append("board " + ", ".join(a["style"]))
    if a.get("stuck_by"):
        out.append(f"{a['stuck_by'][0].lower()} stopped by {a['stuck_by'][1].lower()}")
    if a.get("blocks_by"):
        out.append(f"{a['blocks_by'][0].lower()} into {(a['blocks_by'][1] or 'another block').lower()}'s way")
    if a.get("music") is not None:
        out.append("music" if a["music"] else "no music")
    if a.get("sequence"):
        out.append("sequence " + ", ".join(f"{k} {'yes' if v else 'no'}" for k, v in a["sequence"].items()))
    if a.get("original"):
        out.append("the game's own look kept")
    if a.get("satisfying"):
        out.append("a satisfying finish")
    if a.get("captions"):
        out.append("captions " + ", ".join(f'"{c}"' for c in a["captions"]))
    if a.get("caption_moments"):
        out.append("caption moments " + ", ".join(f'"{c["text"]}" {c["moment"]}' for c in a["caption_moments"]))
    return out


def _caption_moment_rows(asked_caps: list[dict], manifest: dict) -> list[dict]:
    """Does each caption show at the moment the prompt put it on? The moment is read from the parts
    manifest (parts.py): the drags, the wrong move, each exit, the win or the time-out, the parts."""
    from . import parts as P
    moments = manifest.get("moments") or []
    layers = [L for L in manifest.get("layers", []) if L["kind"] == "caption" and L.get("text")]
    rows = []
    for c in asked_caps:
        L = next((L for L in layers if c["text"].strip().lower() in (L["text"] or "").lower()), None)
        if L is None or L.get("from_s") is None:
            continue  # its presence has its own row
        f0, f1 = L["from_s"], L["to_s"]
        want_s, what = None, ""
        key = c["moment"]
        if key == "start":
            intro = next((p for p in manifest.get("parts", []) if p["id"] in ("intro", "teaser")), None)
            limit = (intro["to_s"] if intro else 0) + 1.0
            ok = f0 <= limit
            rows.append(_row(f'caption "{c["text"]}" at the start', ok, f"on screen {f0:g}-{f1:g} s" + ("" if ok else f"; the ad opens at 0 s"), "ad"))
            continue
        if key == "wrong_move":
            m = next((m for m in moments if m.get("also") == "wrong_move"), None)
            want_s, what = (m["at_s"] if m else None), "the wrong move"
        elif key == "fix":
            idx = next((i for i, m in enumerate(moments) if m.get("also") == "wrong_move"), None)
            m = moments[idx + 1] if idx is not None and idx + 1 < len(moments) and moments[idx + 1]["id"].startswith("drag") else None
            want_s, what = (m["at_s"] if m else None), "the move after the wrong one (the correction)"
        elif key == "exit":
            colour = (c.get("colour") or "").lower().replace("darkgreen", "dark green")
            m = next((m for m in moments if m["kind"] == "exit" and m.get("block") == colour), None)
            want_s, what = (m["exit_s"] if m else None), f"the {colour} block's exit"
        elif key == "result":
            m = next((m for m in moments if m["kind"] in ("win", "time_out")), None)
            part = P.part_at(manifest, f0 + 0.05)
            ok = (part is not None and part["kind"] in ("result", "still") and part["id"] in ("result", "result_hold", "question")) or \
                 (m is not None and m["at_s"] is not None and f0 - 1.0 <= m["at_s"] <= f1 + 0.5)
            rows.append(_row(f'caption "{c["text"]}" on the result', ok, f"on screen {f0:g}-{f1:g} s, on the part "
                             f"'{part['id'] if part else '?'}'" + (f"; the result comes at {m['at_s']:g} s" if m and m.get("at_s") is not None else ""), "ad"))
            continue
        elif key == "end":
            playp = next((p for p in manifest.get("parts", []) if p["id"] == "play"), None)
            ok = playp is not None and f0 >= playp["to_s"] - 8.0 and f0 <= playp["to_s"] + 0.5
            rows.append(_row(f'caption "{c["text"]}" in the last seconds', ok, f"on screen {f0:g}-{f1:g} s; the play ends at "
                             f"{playp['to_s'] if playp else '?'} s", "ad"))
            continue
        elif key == "question":
            part = P.part_at(manifest, f0 + 0.05)
            ok = part is not None and part["id"] in ("question", "result", "result_hold")
            rows.append(_row(f'caption "{c["text"]}" at the cut', ok, f"on screen {f0:g}-{f1:g} s, on the part '{part['id'] if part else '?'}'", "ad"))
            continue
        if want_s is None:
            rows.append(_row(f'caption "{c["text"]}" on {what}', False, f"on screen {f0:g}-{f1:g} s; the ad has no such moment", "play"))
        else:
            ok = f0 - 1.0 <= want_s <= f1 + 0.5
            rows.append(_row(f'caption "{c["text"]}" on {what}', ok, f"on screen {f0:g}-{f1:g} s; {what} is at {want_s:g} s", "ad"))
    return rows


def door_rows(level) -> list[dict]:
    """The game's design rules for doors and colours (level.door_problems, 2026-10-19: every block colour has a door, every
    door's colour has a block, every block fits through a door of its colour), kept by all six shipped levels. Before this
    row, "Rules: the level" claimed the door rule without measuring it (the owner's video creative, 2026-10-19)."""
    from .level import door_problems
    problems = door_problems(level)
    colours = [B.COLOURS[i] for i in sorted({int(b.color) for b in level.blocks})]  # slot names in BlockColor order
    doors = {c: sum(1 for e in level.exits if B.COLOURS[int(e.color)] == c) for c in colours}
    return [{"check": "Rules: doors and colours", "status": "pass" if not problems else "failed", "from": "rules",
             "where": None if not problems else "level",
             "detail": (f"{len(colours)} colour(s), each with a door of its colour and no door without a block: "
                        + ", ".join(f"{B.COLOUR_WORDS.get(c, c.lower())} {doors[c]} door{'s' if doors[c] != 1 else ''}" for c in colours)
                        + "; every block fits through a door of its colour") if not problems else "; ".join(problems)[:400]}]


def colour_rows(level_path: Path, brief: dict) -> list[dict]:
    """The colours as the viewer sees them (2026-10-19): the slots the level uses, shown in the brief's display colours (the
    game's own, a theme's palette or a repaint), must stay apart by MIN_COLOUR_DISTANCE so two colours never read as one
    ("two blues" through one door), and no two slots may carry one caption name. The runner repaints a slot's block, door
    and particle materials together (CreativeRunner.cs), so a block and its door always share a colour; said here."""
    from .level import load_level
    try:
        level = load_level(level_path)
    except ValueError:
        return []
    shown = B.display_colours(brief)
    slots = [B.COLOURS[i] for i in sorted({int(b.color) for b in level.blocks})]
    close, same = [], []
    for i, a in enumerate(slots):
        for b in slots[i + 1:]:
            d = B.colour_distance(shown[a]["hex"], shown[b]["hex"])
            if d < B.MIN_COLOUR_DISTANCE:
                close.append(f"{shown[a]['name']} {shown[a]['hex']} and {shown[b]['name']} {shown[b]['hex']} are only {d:.0f} apart")
            if shown[a]["name"].strip().lower() == shown[b]["name"].strip().lower():
                same.append(f"{a} and {b} are both called '{shown[a]['name']}'")
    bad = close + same
    names = ", ".join(f"{shown[s]['name']} {shown[s]['hex']}" for s in slots)
    return [{"check": "Rules: colours tell apart", "status": "pass" if not bad else "failed", "from": "rules",
             "where": None if not bad else "plan",
             "detail": (f"{len(slots)} colour(s) shown as {names}; every pair at least {B.MIN_COLOUR_DISTANCE} apart (the game's "
                        f"red and orange are about 50); a block and its door share one material") if not bad else "; ".join(bad)[:400]}]


def rules_rows(level_path: Path, rec_dir: Path) -> list[dict]:
    """Game dynamics and rules, replayed on the game's own record of the drags (the brief's
    "gameplay consistency": CBJ behaves like the game, not like an animation). The rules are the
    Unity project's, re-read in the C# on 2026-10-15: InputHandler drags ONE block at a time and
    checks the exit only while dragging, each time the pivot enters a new cell; releasing never
    exits (ReleaseBlock snaps). BlockMovementService.IsPositionValid: every cell of the block in
    bounds, active and free of other blocks (the game slides continuously; the pivot cell is the
    logical position). ExitService.CanBlockExit: the first exit in file order of the block's colour
    that overlaps a block cell, and a clear straight lane to the edge for every part, ending in the
    exit's rows/columns (rules.py is the port, tested against the C#). GameManager: the clock starts
    at timerCount, counts down, 0 = fail; the win is every block gone, the clock then stops."""
    from .level import load_level, validate
    from .rules import can_block_exit, initial_state, is_position_valid, matching_exit_index, occupancy
    out = []
    level = load_level(level_path)
    problems = validate(level)
    out.append({"check": "Rules: the level", "status": "pass" if not problems else "failed",
                "detail": "a board Unity loads: a grid the Level Editor allows, blocks on active cells, no overlaps, every door on "
                          "an edge, one door per cell side (the doors' colours are the next row)"
                          if not problems else "; ".join(problems)[:300], "from": "rules", "where": None if not problems else "level"})
    out += door_rows(level)
    try:
        result = json.loads((Path(rec_dir) / "result.json").read_text())
    except (OSError, ValueError):
        return out
    state = list(initial_state(level))
    bad, exits_ok, moves, timer_ok, prev_t = [], 0, 0, True, None
    for d in result.get("drags") or []:
        bid = d.get("block")
        cells = [(c["x"], c["y"]) for c in d.get("cells") or []]
        k = d.get("index", moves) + 1
        if bid is None or bid >= len(state) or state[bid] is None:
            bad.append(f"drag {k}: a block that is not on the board")
            continue
        pos = state[bid]
        occ = occupancy(level, tuple(state))
        for c in cells:
            if abs(c[0] - pos[0]) > 1 or abs(c[1] - pos[1]) > 1:  # the pivot enters neighbouring cells only
                bad.append(f"drag {k}: a jump from {pos} to {c}")
                break
            if not is_position_valid(level, bid, c, occ):
                bad.append(f"drag {k}: moved onto a wall or another block at {c}")
                break
            pos = c
        else:
            if d.get("result") == "exit":
                if not can_block_exit(level, bid, pos, occ):
                    bad.append(f"drag {k}: left the board where the rules allow no exit")
                elif d.get("exit_index") is not None and matching_exit_index(level, bid, pos) != d["exit_index"]:
                    bad.append(f"drag {k}: left through a door that is not its own")
                else:
                    exits_ok += 1
                state[bid] = None
            else:
                state[bid] = pos
        moves += 1
        t0, t1 = d.get("timer_start"), d.get("timer_end")
        if t0 is not None and t1 is not None and (t1 > t0 + 1e-6 or t1 < -1e-6 or (prev_t is not None and t0 > prev_t + 1e-6)):
            timer_ok = False
        prev_t = t1 if t1 is not None else prev_t
    out.append({"check": "Rules: the moves", "status": "pass" if not bad else "failed",
                "detail": f"{moves} drags replayed through the game's rules: one block a drag, the pivot through "
                          f"neighbouring free active cells only; {exits_ok} exit(s) through the first door of the block's "
                          f"own colour it touched, with a clear lane, during the drag"
                          + ("" if not bad else "; " + "; ".join(bad[:3])), "from": "rules", "where": None if not bad else "play"})
    out.append({"check": "Rules: the clock", "status": "pass" if timer_ok else "failed",
                "detail": "the clock only counts down and never goes below zero" if timer_ok else
                          "the clock rose or went below zero during a drag", "from": "rules", "where": None if timer_ok else "play"})
    used = {d.get("exit_index") for d in result.get("drags") or [] if d.get("result") == "exit"}
    unused = [j for j in range(len(level.exits)) if j not in used]
    left = sum(1 for g in result.get("block_gone_frames", []) if g < 0)
    out.append({"check": "Rules: doors used", "status": "info", "from": "rules", "where": None,
                "detail": f"{len(level.exits) - len(unused)} of {len(level.exits)} doors used by a leaving block"
                          + (f"; {len(unused)} door(s) unused" + (f" with {left} block(s) still on the board" if left else
                             " although every block left: the same-colour blocks shared a door") if unused else "")})
    gone = sum(1 for g in result.get("block_gone_frames", []) if g >= 0)
    status = result.get("status")
    consistent = (status == "cleared") == (gone == len(level.blocks)) or status == "failed"
    out.append({"check": "Rules: the result", "status": "pass" if consistent else "failed",
                "detail": f"the game reports '{status}' with {gone} of {len(level.blocks)} blocks gone", "from": "rules",
                "where": None if consistent else "play"})
    return out


WORKFLOWS = {
    "text": "text-to-creative: the board, the play, the game's rules, every fact the prompt asks for, the brief's rows",
    "image": "image-guided: as text-to-creative, plus the image's role (style, composition, asset, modify)",
    "video": "video-guided: as text-to-creative, plus the reference rows (the ending, the pacing, the hook, the purposes "
             "in order, the part lengths, the captions, the look, nothing copied, the reading's confidence)",
    "edit": "controlled editing: the edit report (what changed, what was kept) and the facts the edit asks for; "
            "the rules are re-checked only when the play was re-filmed",
}


def workflow(brief: dict, record: dict) -> dict:
    """Which evaluation runs for this version: a plain text-to-creative is judged on what a text
    request can ask for, an edit on its report, a reference-driven creative on the reference too
    (2026-10-16: one evaluation per workflow, not every check on every version). The guided workflow
    (workflows/guided.py) is judged like a creation; its kind (image or video) comes from the
    references it read, as for any creation."""
    refs = ((brief.get("planner") or {}).get("references")) or []
    kinds = {("video" if str(r.get("file", "")).lower().endswith((".mp4", ".mov", ".webm", ".m4v")) else "image") for r in refs if isinstance(r, dict)}
    if record.get("workflow") == "edit" or (record.get("workflow") is None and record.get("edit")):
        kind = "edit"
    elif "video" in kinds:
        kind = "video"
    elif "image" in kinds:
        kind = "image"
    else:
        kind = "text"
    reused = bool((record.get("recording") or {}).get("reused"))
    groups = ["asked facts"]
    if kind != "edit":
        groups = ["board", "play", "rules", "asked facts", "case"]
    else:
        groups = ["edit report", "asked facts"] + (["rules"] if not reused else [])
    if kind in ("image", "video"):
        groups.append("reference")
    return {"kind": kind, "what": WORKFLOWS[kind], "groups": groups}


def rows(prompt: str, brief: dict, level_path: Path, record: dict, vdir: Path, rec_dir: Path | None = None) -> list[dict]:
    wf = workflow(brief, record)
    out = level_rows(prompt, brief, level_path, record.get("checks")) + ad_rows(prompt, brief, record, vdir, rec_dir)
    if "case" not in wf["groups"]:
        out = [r for r in out if "(the brief)" not in r["check"]]
    if rec_dir is not None and "rules" in wf["groups"]:
        out += rules_rows(level_path, rec_dir)
    else:
        try:
            from .level import load_level
            out += door_rows(load_level(level_path))
        except ValueError:
            pass
        if rec_dir is not None:
            out.append({"check": "Rules: the moves", "status": "info", "from": "rules", "where": None,
                        "detail": "the play is reused from the version this edit comes from, where the rules were replayed"})
    out += colour_rows(level_path, brief)
    if "reference" in wf["groups"]:
        out += reference_rows(prompt, brief, record, vdir, rec_dir)
    if (brief.get("reference") or {}).get("kind") != "image":  # the image rows carry these two themselves (2026-10-19)
        try:
            from . import imageaudit as IA
            for r in (IA.blocks_left_row(prompt, brief, record), IA.end_card_row(vdir), IA.real_choice_row(prompt, brief, record, vdir)):
                if r:
                    r["check"] = r["check"].replace("Image: ", "")
                    out.append(r)
        except Exception:  # an extra row never breaks the evaluation
            pass
    return out


def misses(checks: list[dict]) -> list[dict]:
    return [c for c in checks if c.get("from") in ("prompt", "rules", "case", "reference") and c.get("status") == "failed"]


def feedback(prompt: str, checks: list[dict], review: dict | None = None) -> str | None:
    """An edit request for the planner that names what the made version missed, for the revision
    round: measured misses first (they are facts), then the viewer's first fix when it is about
    something the request asked for."""
    miss = misses(checks)
    lines = [f"{c['check'].split(': ', 1)[-1]}: {c['detail']}" for c in miss]
    if review and not review.get("error"):
        bad = [m for m in review.get("match", []) if m.get("verdict") in ("no", "partial")]
        if bad and review.get("fixes"):
            lines.append("the viewer saw: " + "; ".join(f"{m['control']}: {m['seen']}" for m in bad[:2]))
            lines.append("suggested fix: " + review["fixes"][0])
    if not lines:
        return None
    return ("Revise this version so the original request is met; change only what these points need. "
            "The original request was: \"" + prompt.strip() + "\". What the made version missed: " + " | ".join(lines))



# ---------- the reference profile (video-guided creation, core requirement 4, 2026-10-16) ----------

STAGEABLE = ("hook", "gameplay", "mistake", "near_fail", "fail", "victory", "replay", "question", "end_card")
MISTAKE_MOMENTS = ("mistake", "attempt", "bump", "short")
CAPTION_LAYERS = {"challenge": "hook", "wrong": "cap_mistake", "instruction": "cap_fix", "urgency": "cap_hurry", "result": "cap_result",
                  "cta": "end_cta"}
CAPTION_FIELDS = {"challenge": "hook", "wrong": "mistake", "instruction": "fix", "urgency": "hurry", "result": "result", "cta": "cta"}
CALM_DPS, FAST_DPS = 0.25, 0.6  # drags per second over the play: calm under, fast over, normal between
PART_LENGTH_ERROR = 0.2  # the part lengths' normalised mean absolute error that passes (pacing similarity 0.8)


def _rrow(check: str, ok: bool | None, detail: str, where: str | None = None) -> dict:
    return {"check": f"Reference: {check}", "status": "pass" if ok else "info" if ok is None else "failed",
            "detail": detail, "from": "reference", "where": None if ok else where}


def _as_filled(row: dict) -> dict:
    """A row for an aspect the request left open and the reference filled (round 2, case 14): shown with what it measured,
    but info, never a failure: it was not asked."""
    from .videoref import FILLED
    was = {"pass": "matches", "failed": "differs", "info": None}[row["status"]]
    row.update(status="info", where=None,
               detail=f"{FILLED}; not judged" + (f" (it {was})" if was else "") + f": {row['detail']}")
    return row


# The board row (2026-10-17): the made level against the board read in the reference. A part fails the row only when the
# accuracy pass shows the reading reliable for it (10 of 12 or better); the rest is info, "read approximately". On the
# 12 own creatives (READING-ACCURACY-v9.md, re-scored, and v9b, a fresh pass after the last rule): the shape 12 and 10 of
# 12, the size 10 and 12, the blocks within two 11 and 12, the colours 12 and 12; the gates' sides (7 of 12) and how
# busy the board looks (1-2 of 12 against the level's difficulty) are not reliable: not judged, and busy is not applied.
BOARD_RELIABLE = frozenset({"shape", "size", "blocks", "colours"})
BOARD_SIZE_CELLS = 1  # columns and rows: this many cells either way
BOARD_BLOCKS = 2  # blocks: this many either way
BOARD_PARTS = ("shape", "size", "blocks", "colours")
_LEVEL_SLOTS = ("Green", "Yellow", "Blue", "Red", "Orange", "Purple", "DarkGreen")  # BlockColor order (level.json)


def made_board(level_path: Path, brief: dict) -> dict | None:
    """The made level's board: {columns, rows, blocks, colours (the game's slots), shape (the brief's; "open" for a
    generated level with no walls when the brief left it open)}, or None when there is no level file."""
    if not Path(level_path).is_file():
        return None
    d = json.loads(Path(level_path).read_text())
    blocks = d.get("GridBlockDatas") or []
    cols = list(dict.fromkeys(_LEVEL_SLOTS[b["blockColor"]] for b in blocks if 0 <= int(b.get("blockColor", -1)) < 7))
    shape = made_shape(d) or (brief.get("level") or {}).get("shape") or "any"
    return {"columns": d.get("gridWidth"), "rows": d.get("gridHeight"), "blocks": len(blocks), "colours": cols,
            "shape": shape, "walls": len(d.get("inactiveCells") or [])}


def made_shape(level: dict) -> str | None:
    """The generator's shape a level was built as, from its wall cells (generate.holes_for for its size): "open" with
    none; None when no shape's walls match (a hand-made board), and the brief's shape is used."""
    from .generate import SHAPES, holes_for
    w, h = level.get("gridWidth"), level.get("gridHeight")
    walls = {(c.get("x"), c.get("y")) for c in level.get("inactiveCells") or []}
    if not walls:
        return "open"
    if not w or not h:
        return None
    return next((s for s in SHAPES if s != "open" and set(holes_for(s, w, h)) == walls), None)


def board_parts(want: dict, made: dict) -> dict:
    """Each part of the board row: {part: (ok, detail)} for the parts the reading gives."""
    out = {}
    if want.get("shape"):
        read = want.get("shape_read")
        out["shape"] = (made["shape"] == want["shape"], f"shape {read or want['shape']} read"
                        + (f", {want['shape']} taken" if read and read != want["shape"] else "") + f", {made['shape']} made")
    if want.get("columns") and want.get("rows"):
        ok = abs(made["columns"] - want["columns"]) <= BOARD_SIZE_CELLS and abs(made["rows"] - want["rows"]) <= BOARD_SIZE_CELLS
        read = want.get("size_read") or (want["columns"], want["rows"])
        out["size"] = (ok, f"{read[0]}x{read[1]} read" + ("" if tuple(read) == (want["columns"], want["rows"]) else
                                                          f" ({want['columns']}x{want['rows']} the generator builds)") +
                       f", {made['columns']}x{made['rows']} made (within {BOARD_SIZE_CELLS} cell a side)")
    if want.get("blocks") is not None:
        read = want.get("blocks_read", want["blocks"])
        out["blocks"] = (abs(made["blocks"] - want["blocks"]) <= BOARD_BLOCKS,
                         f"{read} blocks read" + ("" if read == want["blocks"] else f" ({want['blocks']} the most this board takes)") +
                         f", {made['blocks']} made (within {BOARD_BLOCKS})")
    if want.get("colours"):
        have = [c for c in want["colours"] if c in made["colours"]]
        out["colours"] = (2 * len(have) >= len(want["colours"]),
                          f"colours {', '.join(c.lower() for c in want['colours'])} read; {len(have)} of {len(want['colours'])} "
                          f"in the level ({', '.join(c.lower() for c in made['colours'])}; at least half)")
    return out


def _ref_video(brief: dict) -> dict | None:
    refs = [r for r in ((brief.get("planner") or {}).get("references") or []) if isinstance(r, dict)]
    return next((r for r in refs if r.get("kind") == "video" or str(r.get("file", "")).lower().endswith((".mp4", ".mov", ".webm", ".m4v"))), None)


def _drag_times(manifest: dict, play: dict) -> list[float]:
    return sorted(m["at_s"] for m in manifest.get("moments") or [] if str(m.get("id", "")).startswith("drag_")
                  and m.get("at_s") is not None and play["from_s"] - 1e-6 <= m["at_s"] <= play["to_s"] + 1e-6)


def pace_of_play(manifest: dict) -> dict | None:
    """The ad's pacing, measured on its drags (the parts manifest): {dps, tempo, change, first, last}.
    calm under 0.25 drags a second, fast over 0.6; the change compares the first and last thirds of
    the play (the reference's motion is compared the same way, reference.video_facts)."""
    play = next((p for p in manifest.get("parts") or [] if p.get("id") == "play" and p.get("from_s") is not None), None)
    if play is None or play["to_s"] <= play["from_s"]:
        return None
    times = _drag_times(manifest, play)
    if not times:
        return None
    dur = play["to_s"] - play["from_s"]
    dps = len(times) / dur
    t1, t2 = play["from_s"] + dur / 3, play["from_s"] + 2 * dur / 3
    a, b = sum(1 for x in times if x < t1), sum(1 for x in times if x >= t2)
    change = "speeds up" if b > a * 1.3 and b - a >= 1 else "slows down" if a > b * 1.3 and a - b >= 1 else "even"
    return {"dps": round(dps, 2), "tempo": "calm" if dps < CALM_DPS else "fast" if dps > FAST_DPS else "normal",
            "change": change, "first": a, "last": b}


TEMPO_MARGIN = 0.1  # drags a second: one class apart, this close to the boundary between them, passes with a note


def _tempo_near(ref_tempo: str, pace: dict) -> str | None:
    """The boundary ("0.25"/"0.6" drags a second) the ad's tempo is within TEMPO_MARGIN of, when it is one class from the
    reference's (2026-10-16 creative run, case 10: 0.59 drags a second failed "fast" against the 0.6 line); else None."""
    order = ("calm", "normal", "fast")
    if pace["tempo"] == ref_tempo or abs(order.index(pace["tempo"]) - order.index(ref_tempo)) != 1:
        return None
    line = CALM_DPS if "calm" in (pace["tempo"], ref_tempo) else FAST_DPS
    return f"{line:g} drags a second" if abs(pace["dps"] - line) <= TEMPO_MARGIN + 1e-9 else None


LOOK_RGB = 48.0  # the look row's RGB distance: a colour this close is the same colour as rendered (2026-10-16, case 12)


def _hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_dist(a: str, b: str) -> float:
    return sum((x - y) ** 2 for x, y in zip(_hex_rgb(a), _hex_rgb(b))) ** 0.5


def _gradient_dist(colour: str, stops: list[str]) -> float:
    """The RGB distance from a colour to a background: to its one colour, or to the nearest point of the gradient
    between its two stops (either stop included: the poster's margins are read at mid-height, inside the gradient)."""
    c = _hex_rgb(colour)
    if len(stops) < 2:
        return _rgb_dist(colour, stops[0])
    a, b = _hex_rgb(stops[0]), _hex_rgb(stops[-1])
    ab = [y - x for x, y in zip(a, b)]
    span = sum(v * v for v in ab)
    k = 0.0 if span == 0 else max(0.0, min(1.0, sum((ci - ai) * v for ci, ai, v in zip(c, a, ab)) / span))
    near = [ai + k * v for ai, v in zip(a, ab)]
    return sum((ci - ni) ** 2 for ci, ni in zip(c, near)) ** 0.5


def pause_pace(rdrags: list[dict]) -> dict | None:
    """The ad's pace change as the "Pacing curve" check measures it (checks.gameplay_checks, step 6), so the reference's
    pacing row and that check can never disagree: the pauses between the recorded drags, the average of the first
    third against the last third, on 6 drags or more; None otherwise. A shorter last pause is a play that speeds up."""
    from .checks import FPS as CHECK_FPS
    if len(rdrags or []) < 6:
        return None
    gaps = [(rdrags[i]["start_frame"] - rdrags[i - 1]["end_frame"]) / CHECK_FPS for i in range(1, len(rdrags))]
    third = max(1, len(gaps) // 3)
    a, b = sum(gaps[:third]) / third, sum(gaps[-third:]) / third
    return {"first": round(a, 2), "last": round(b, 2)}


EVEN_RATIO = 1.3  # reference.video_facts and gameplay_motion_change: thirds within this ratio are "even"


def pause_change_ok(change: str, pauses: dict) -> bool:
    """Whether the pauses show the change, with the "Pacing curve" check's own rule for speeds up (the last third's
    pauses shorter) and slows down (longer); even, which that check never judges, is the reference's own band: its
    measure calls a change "even" when the thirds are within EVEN_RATIO of each other (reference.video_facts,
    gameplay_motion_change), so the ad is held to the same ratio (it was 15 % of the larger, stricter than the reading
    it is compared with; round 2 rerun, case 05: 1.20 s against 0.92 s, a ratio of 1.30, fails either way)."""
    a, b = pauses["first"], pauses["last"]
    if change == "speeds up":
        return b < a
    if change == "slows down":
        return b > a
    return max(a, b) <= EVEN_RATIO * max(min(a, b), 1e-6) + 1e-9


def ad_purposes(manifest: dict, brief: dict) -> list[tuple[float, str]]:
    """The ad's purposes on its own clock, from the parts manifest: the hook caption, the play, each
    wrong move, the near-fail (the first clock reading of 5 s or under, or the hurry caption, on a
    near-fail or a time-out: a time-out's clock passes 5 s too before it runs out), the time-out, the
    win, the replay, a cliffhanger's question, the end card."""
    parts = {p["id"]: p for p in manifest.get("parts") or [] if p.get("from_s") is not None}
    layers = {L["id"]: L for L in manifest.get("layers") or [] if L.get("from_s") is not None}
    ending = (manifest.get("gameplay") or {}).get("ending") or brief["gameplay"]["ending"]  # what was played
    out = []
    if "hook" in layers:
        out.append((layers["hook"]["from_s"], "hook"))
    if "play" in parts:
        out.append((max(parts["play"]["from_s"], layers["hook"]["from_s"] + 0.01 if "hook" in layers else 0), "gameplay"))
    for m in manifest.get("moments") or []:
        if m.get("at_s") is None:
            continue
        if m.get("kind") in MISTAKE_MOMENTS:
            out.append((m["at_s"], "mistake"))
        elif m.get("kind") == "time_out":
            out.append((m["at_s"], "fail"))
        elif m.get("kind") == "win":
            out.append((m["at_s"], "victory"))
    if ending in ("near_fail", "time_out"):
        low = [c["at_s"] for c in manifest.get("clock") or [] if c.get("at_s") is not None and c["clock_s"] <= 5]
        t = min(low) if low else (layers["cap_hurry"]["from_s"] if "cap_hurry" in layers else None)
        if t is not None:
            out.append((t, "near_fail"))
    if not any(p == "victory" for _, p in out) and "result" in parts and ending in ("win", "near_fail"):
        out.append((parts["result"]["from_s"], "victory"))
    for pid in ("replay", "question"):
        if pid in parts:
            out.append((parts[pid]["from_s"], pid))
    if "end" in parts:
        out.append((parts["end"]["from_s"], "end_card"))
    return sorted(out, key=lambda x: x[0])


def _in_order(seq: list[str]) -> list[str]:
    """Purposes in order, each run of one purpose once; gameplay after the first counts as the
    background of a wrong move or a near-fail, not a part of its own."""
    out = []
    for p in seq:
        if (out and out[-1] == p) or (p == "gameplay" and "gameplay" in out):
            continue
        out.append(p)
    return out


def _stages(seq: list[str]) -> list[str]:
    """The stages an order is judged on: the purposes without "gameplay", the background of the play (2026-10-16:
    an ad emits gameplay at the play's start, before its first drag, so a reference that opens on a wrong move could
    never match, and the loop could not fix it)."""
    return _in_order([p for p in seq if p != "gameplay"])


def _subsequence(want: list[str], have: list[str]) -> bool:
    it = iter(have)
    return all(any(h == w for h in it) for w in want)


def ad_part_lengths(manifest: dict, hook_is_play: bool = False) -> dict[str, float]:
    """The ad's parts that match a reference's: hook = the opening plus the hook caption, play = the
    gameplay after it and the replay, result = the result screen and its hold (or a cliffhanger's
    question), end = the end card. hook_is_play: the hook caption over the play is play (a reference
    with no hook part); the hook is then only a still opening."""
    parts = {p["id"]: p for p in manifest.get("parts") or [] if p.get("from_s") is not None}
    layers = {L["id"]: L for L in manifest.get("layers") or [] if L.get("from_s") is not None}
    ln = lambda p: max(0.0, p["to_s"] - p["from_s"])  # noqa: E731
    hook_end = layers["hook"]["to_s"] if "hook" in layers and not hook_is_play else (
        parts["intro"]["to_s"] if "intro" in parts else 0.0)
    out = {"hook": hook_end}
    if "play" in parts:
        out["play"] = max(0.0, ln(parts["play"]) - max(0.0, hook_end - parts["play"]["from_s"])) + \
            (ln(parts["replay"]) if "replay" in parts else 0.0)
    out["result"] = sum(ln(parts[k]) for k in ("result", "result_hold", "question") if k in parts)
    if "end" in parts:
        out["end"] = ln(parts["end"])
    return out


def ref_part_lengths(segs: list[dict]) -> dict[str, float]:
    group = {"hook": "hook", "gameplay": "play", "mistake": "play", "near_fail": "play", "payoff": "play", "replay": "play",
             "victory": "result", "fail": "result", "question": "result", "end_card": "end"}
    out: dict[str, float] = {}
    for s in segs:
        g = group.get(s.get("purpose"))
        if g:
            out[g] = out.get(g, 0.0) + max(0.0, s["to_s"] - s["from_s"])
    return out


def pacing_asked(prompt: str, a: dict) -> bool:
    """Whether the request asks about the reference's pacing. With the planner's reading plan: a plan made for some
    aspects (targeted) that names the pacing; a full concept read names the pacing in most plans whatever the request
    says, so there the request's own words decide, as with no plan (the word table)."""
    from . import reference as R
    plan = a.get("plan") or {}
    if plan.get("source") == "planner" and plan.get("level") == "targeted":
        return "pacing" in (plan.get("focus") or [])
    return "pacing" in R.focus_words(prompt)["found"]


def screen_row(prompt: str, brief: dict, a: dict, notes: dict, focus: list) -> dict:
    """Reference: the screen (round 2, case 09). The HUD shown or hidden as the reference shows it (can fail, at the plan)
    and the camera zoom from the board's share of the frame (info). Info when the screen is not a focus, when the
    reference's HUD was not read, or when the request sets the HUD itself."""
    from . import reference as R
    from . import videoref as V
    if not R.covers(focus, "screen"):
        return _rrow("the screen", None, "not a focus of this reading")
    vs = brief.get("visuals") or {}
    if V.cursor_only(prompt):  # the request names the cursor alone (round 2, case 14): the zoom and the HUD are not asked
        took = ((brief.get("reference") or {}).get("screen") or {}).get("cursor")
        return _rrow("the screen", None, f"the request names the cursor alone: the ad's cursor is {vs.get('cursor') or 'the default'}"
                     + (", taken from the reference" if took else ", the reference's cursor was not read") + " (info)")
    share = V.board_share(a, notes)
    want_z = V.zoom_for(share)
    zoom_bit = (f"zoom {vs.get('camera_zoom') or 1.0:g} in the ad, {want_z or 1.0:g} from the board's share "
                f"({share:.0%} of the reference's width)" if share is not None else "the board's share was not read")
    hud = notes.get("hud") if isinstance(notes.get("hud"), dict) else None
    if hud is None or V.HUD_STATED.search(prompt or ""):
        return _rrow("the screen", None, ("the request sets the HUD itself; " if hud is not None else "the HUD was not read; ")
                     + zoom_bit + " (info)")
    level_on = bool(str(hud.get("level") or "").strip())
    clock_on = bool(V._clock_s(hud.get("clock")))
    have = (bool(vs.get("hud_level", True)), bool(vs.get("hud_timer", True)))
    cleared = (brief.get("reference") or {}).get("hud_clear") or {}
    if "hid the HUD" in str(cleared.get("action") or "") and not any(have):
        # hidden so the board's top row stays clear (videoref.hud_clear, 2026-10-17): the request's zoom or the board's
        # framing wins over the reference's HUD; the HUD-over-board row measures it
        return _rrow("the screen", None, f"the reference shows the HUD; the ad hides it so the board's top row is clear of "
                                         f"it (zoom {cleared.get('zoom'):g}, at most {cleared.get('safe'):g} with the HUD "
                                         f"shown); {zoom_bit} (info)")
    ok = have == (level_on, clock_on)
    words = lambda lv, ck: "no HUD" if not (lv or ck) else f"{'the level' if lv else 'no level'} and {'the clock' if ck else 'no clock'}"  # noqa: E731
    return _rrow("the screen", ok, f"the reference shows {words(level_on, clock_on)}, the ad {words(*have)}; {zoom_bit} (info)",
                 "plan")


# ---------- the HUD over the board (video workflow, 2026-10-17: "zoom in closer" put the HUD bar on a 4x9 board's top row)
# The game's HUD (the Level badge and the Time pill, a Unity canvas) sits at a fixed place on screen; the board is framed by
# CreativeRunner.FitCamera and the zoom moves the camera toward the framing's look-at point (the screen's centre), so a
# tall board's top edge rises under the bar. Measured on the tool's own 1080x1920 recordings (tests/data/hud_margin.py):
# the bar's purple spans x 228-801 and y 510-616, its outline and the badge x 212-818 and y 483-636.
HUD_BOX = (0.196, 0.252, 0.757, 0.331)  # x0, y0, x1, y1 as shares of the frame: the HUD with its badge and outline
HUD_BAR = (0.25, 0.272, 0.72, 0.316)  # the bar's purple inside: the HUD is shown when 30% of it is the HUD's purple
HUD_SHOWN_SHARE = 0.3
HUD_TOL = 10 / 1920  # a board top this close under the bar's bottom edge is the rail's shadow, not a covered row
BOARD_ROW_PIXELS = 12  # a row of the frame is the board's when this many pixels outside the HUD are the board's colours
BOARD_ROW_RUN = 6  # ... for this many rows in a row (a speck of colour is not the board)
HUD_SIDE_SLACK = 0.02  # a board reaching this little past the HUD's sides still counts as within its width (4x9: x 248-819)
FLOOR_BELOW_SHARE = 0.10  # the cells' floor right under the bar: the board's inside already runs under the HUD


def _pixel_classes(a):
    """The pixel classes the HUD guard uses, on an RGB array: the HUD's purple (about (104, 60, 222), dark (61, 33, 140)),
    the board's rail and wall cells (dark slate, about (60, 68, 89)), the cells' floor (about (100, 115, 155)) and the
    blocks and gates (saturated, bright); white and the captions' dark purple outline are none of them."""
    import numpy as np
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    mx, mn = a.max(-1), a.min(-1)
    purple = (b > 130) & (b - r >= 70) & (r > g + 15) & (g < 90)
    rail = (g > r) & (b - r >= 15) & (b - r <= 50) & (mx < 120) & (r >= 35)
    floor = (r >= 80) & (r <= 125) & (g >= 95) & (g <= 140) & (b >= 135) & (b <= 180) & (b - r >= 35)
    block = (mx - mn >= 90) & (mx >= 150) & ~purple
    return purple, rail, floor, block, np


def hud_measure(image) -> dict:
    """Whether the HUD bar covers the board's top on one frame of play (a path or an RGB array). The HUD is shown when
    its bar's purple fills HUD_BAR; the board's top is the first run of BOARD_ROW_RUN rows, from just above the HUD
    (23.5% of the height) down to 65%, with BOARD_ROW_PIXELS pixels of the board's colours (rail, floor, block or gate)
    outside HUD_BOX and away from the frame's own background (each row's margins, 3% a side); the board is under the HUD
    when that top is above the HUD's bottom edge (less HUD_TOL); when the board's first row starts right at that edge
    and lies within the HUD's width (its top cut by the bar: `cut`); or when the cells' floor already shows right under
    the bar (FLOOR_BELOW_SHARE of the band 0-24 px below it, between 35% and 74% of the width). Returns {shown, purple,
    hud_bottom, board_top, cut, margin, floor_below, covered} in pixels of the frame."""
    from PIL import Image
    if not hasattr(image, "shape"):
        with Image.open(image) as im:
            import numpy as np
            image = np.asarray(im.convert("RGB")).astype(int)
    a = image.astype(int)
    H, W = a.shape[:2]
    purple, rail, floor, block, np = _pixel_classes(a)
    bx0, by0, bx1, by1 = (int(round(v * s)) for v, s in zip(HUD_BOX, (W, H, W, H)))
    px0, py0, px1, py1 = (int(round(v * s)) for v, s in zip(HUD_BAR, (W, H, W, H)))
    share = float(purple[py0:py1, px0:px1].mean()) if py1 > py0 and px1 > px0 else 0.0
    shown = share >= HUD_SHOWN_SHARE
    m = max(1, int(0.03 * W))
    bg = np.median(np.concatenate([a[:, :m], a[:, -m:]], axis=1), axis=1)  # each row's own background
    near_bg = np.sqrt(((a - bg[:, None, :]) ** 2).sum(-1)) < 40
    board = (rail | floor | block) & ~near_bg
    board[:, :int(0.04 * W)] = False
    board[:, W - int(0.04 * W):] = False
    if shown:
        board[by0:by1, bx0:bx1] = False
    counts = board.sum(1)
    lo, hi = int(0.235 * H), int(0.65 * H)
    top = None
    for y in range(lo, hi - BOARD_ROW_RUN):
        if all(counts[y + k] >= BOARD_ROW_PIXELS for k in range(BOARD_ROW_RUN)):
            top = y
            break
    band = floor[by1 + 2:by1 + 26, int(0.35 * W):int(0.74 * W)] & ~near_bg[by1 + 2:by1 + 26, int(0.35 * W):int(0.74 * W)]
    floor_below = float(band.mean()) if band.size else 0.0
    # a board narrower than the HUD whose first row starts right at the HUD's bottom edge is cut by it: its top is hidden
    # under the bar (4x9 and 4x10 at zoom 1: the rail and the posts lie inside the HUD's width); a board that reaches past
    # the HUD's sides there would have shown above the edge, so it really starts there (7x9 at zoom 1: x 217-862)
    hidden = False
    if shown and top is not None and top <= by1 + 3:
        xs = np.where(board[top:top + BOARD_ROW_RUN].any(0))[0]
        slack = int(HUD_SIDE_SLACK * W)  # a sliver this thin beside the HUD cannot make a board row above the edge
        hidden = bool(len(xs)) and bool(xs.min() >= bx0 - slack and xs.max() <= bx1 + slack)
    covered = bool(shown and ((top is not None and top < by1 - HUD_TOL * H) or hidden or floor_below >= FLOOR_BELOW_SHARE))
    return {"shown": bool(shown), "purple": round(share, 2), "hud_bottom": by1 if shown else None, "board_top": top, "cut": hidden,
            "margin": (top - by1) if shown and top is not None else None, "floor_below": round(floor_below, 2),
            "covered": covered, "size": [W, H]}


def play_frame(vdir: Path, manifest: dict) -> Path | None:
    """The version's first frame of play (0.5 s into the play part of ad/ad.mp4), saved as hud_frame.png in the version
    folder; the poster when the video cannot be read."""
    import shutil
    import subprocess
    video, out = vdir / "ad" / "ad.mp4", vdir / "hud_frame.png"
    play = next((p for p in manifest.get("parts") or [] if p.get("id") == "play" and p.get("from_s") is not None), None)
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg and video.is_file():
        at = float(play["from_s"]) + 0.5 if play else 0.5
        r = subprocess.run([ffmpeg, "-v", "error", "-y", "-ss", f"{at:.2f}", "-i", str(video), "-frames:v", "1", str(out)],
                           capture_output=True, text=True)
        if r.returncode == 0 and out.is_file():
            return out
    poster = vdir / "ad" / "poster.png"
    return poster if poster.is_file() else None


def hud_row(prompt: str, brief: dict, vdir: Path, manifest: dict) -> dict:
    """The measured guard after recording (video workflow): does the HUD bar cover the board's top row on the version's
    first frame of play (hud_measure)? "Asked: the zoom" when the request states the zoom (videoref.zoom_stated), else
    "Reference: the screen: the HUD over the board". It fails when the bar covers the board and the brief has a lever
    for it: the HUD shown and not asked (the revision hides it, guided.hud_fix), or a zoom above 1 (the revision lowers
    it); with the HUD asked and no zoom left to lower, the game's own framing does it (CreativeRunner.FitCamera, not a
    brief field): info."""
    from . import videoref as V
    vs = brief.get("visuals") or {}
    zoom = float(vs.get("camera_zoom") or 1.0)
    stated_zoom = V.zoom_stated(prompt)
    name = "the zoom" if stated_zoom else "the screen: the HUD over the board"
    make = (lambda ok, d, w=None: _row(name, ok, d, w)) if stated_zoom else (lambda ok, d, w=None: _rrow(name, ok, d, w))  # noqa: E731
    if not (vs.get("hud_level", True) or vs.get("hud_timer", True)):
        return make(None, f"the HUD is hidden, so it covers nothing (zoom {zoom:g})")
    frame = play_frame(vdir, manifest)
    if frame is None:
        return make(None, "no frame of play to measure")
    m = hud_measure(frame)
    where = f"measured on {frame.name}: the HUD's bottom edge at y {m['hud_bottom']}, the board's top at y {m['board_top']}"
    if not m["shown"]:
        return make(None, f"the HUD is not seen on the first frame of play ({m['purple']:.0%} of its bar is its purple)")
    if not m["covered"]:
        return make(True, f"the board's top row is clear of the HUD at zoom {zoom:g} ({where}, {m['margin']} px below it)")
    bits = f"the HUD bar covers the board's top row at zoom {zoom:g} ({where}" + (
        f"; the cells' floor fills {m['floor_below']:.0%} of the band right under the bar" if m["floor_below"] >= FLOOR_BELOW_SHARE else "") + ")"
    if not V.hud_asked(prompt):
        return make(False, bits + "; the HUD is not asked: hide it", "plan")
    if zoom > 1.0 + 1e-6:
        return make(False, bits + "; the request names the HUD: lower the zoom", "plan")
    return make(None, bits + "; the request names the HUD and the zoom is the game's own (1): the game's framing of a "
                             "board this tall puts it there (CreativeRunner.FitCamera, not a brief field)")


WRONG_MOVES = ("mistake", "attempt", "bump")  # parts.py moment kinds a mistake caption may stand on


def hook_row(notes: dict, segs: list[dict], manifest: dict, layers: dict) -> dict:
    """Reference: the hook, its kind as well as its start (round 2 rerun, case 14: the row passed on the start alone
    while the reference opens on the board with no caption and the ad on a headline). A caption hook: the ad's hook
    caption starts within the reference's hook + 1 s and has the same function (question, challenge, dare; a function
    neither text shows is not compared). A gameplay hook: the ad opens on the play (no still opening); its hook caption
    is shown in the row as the difference ad.py makes (it draws one on frame 0, the poster), info, since no brief field
    can remove it."""
    from . import videoref as V
    parts = {p["id"]: p for p in manifest.get("parts") or [] if p.get("from_s") is not None}
    kind = V.hook_kind(notes)
    h = layers.get("hook")
    intro = parts.get("intro")
    still = max(0.0, intro["to_s"] - intro["from_s"]) if intro else 0.0
    if kind == "gameplay":
        if still > 0.05:
            return _rrow("the hook", False, f"the reference opens on the play with no caption; the ad opens on a {still:g} s still "
                                            f"frame", "plan")
        cap = (f"; the ad keeps its hook caption \"{h.get('text')}\" at {h['from_s']:g} s, which ad.py draws on frame 0 (the "
               f"poster), so the headline is not judged" if h else "")
        return _rrow("the hook", True if not h else None, "the reference opens on the play with no caption (a gameplay hook); "
                                                          "the ad opens on the play too" + cap)
    hooks = [s for s in segs if s["purpose"] == "hook"]
    limit = (hooks[0]["to_s"] - hooks[0]["from_s"]) + 1.0 if hooks else 3.0
    if h is None:
        return _rrow("the hook", False, "the ad has no hook caption", "plan")
    fn_ref, fn_ad = V.hook_function(notes), V.hook_function({"hook": h.get("text") or ""})
    same = not (fn_ref and fn_ad) or fn_ref == fn_ad
    on_time = h["from_s"] <= limit + 1e-6
    detail = (f"the ad's hook caption starts at {h['from_s']:g} s; it must start within {limit:g} s ("
              + (f"the reference's {limit - 1:g} s hook + 1 s)" if hooks else "the reference has no hook part)")
              + (f"; its kind: the reference's {fn_ref}, the ad's {fn_ad}" if fn_ref and fn_ad else ""))
    return _rrow("the hook", on_time and same, detail, "ad" if not on_time else "plan")


IN_THE_WAY = re.compile(r"^(\S+) \(([a-z ]+)\) heads for its gate, but (\S+) \(([a-z ]+)\) is in the way")


def stuck_row(manifest: dict, vdir: Path) -> dict | None:
    """Reference: the stuck moment (round 2 rerun 3, case 14: "I can't reach orange!" over two orange blocks, one in the
    other's way), info: the mover's colour is one block on the made level, and the blocker is another colour. From the
    parts manifest's first wrong move, the recording's beat note (play.json) and the made level (level.json). None when
    the play has no wrong move."""
    # the beat the Mistakes check names: the first played "mistake" beat of the recording (rerun 4: the moments' first
    # "wrong_move" can be a hesitation or a cliffhanger's last bump, and the row named the wrong block)
    rec = (manifest.get("gameplay") or {}).get("recording")
    try:
        play = json.loads((Path(vdir).parent.parent / rec / "play.json").read_text()) if rec else {}
    except (OSError, ValueError):
        play = {}
    beats = play.get("beats") or []
    k = next((i for i, b in enumerate(beats) if b.get("kind") == "mistake"), None)
    if k is None:
        return None
    wrong = next((m for m in manifest.get("moments") or [] if m.get("id") == f"drag_{k}"), {})
    note = str(beats[k].get("note") or "")
    m = IN_THE_WAY.match(note)
    lv = Path(vdir) / "level.json"
    counts: dict[str, int] = {}
    if lv.is_file():
        for b in json.loads(lv.read_text()).get("GridBlockDatas") or []:
            c = int(b.get("blockColor", -1))
            if 0 <= c < 7:
                name = _LEVEL_SLOTS[c].lower().replace("darkgreen", "dark green")
                counts[name] = counts.get(name, 0) + 1
    mover = (m.group(2) if m else str(wrong.get("block") or "")).lower()
    bits = [f"drag {k + 1}: the {mover} block is stuck" + (f" at {wrong['at_s']} s" if wrong.get("at_s") is not None else "")]
    if counts.get(mover):
        bits.append(f"{counts[mover]} {mover} block{'s' if counts[mover] != 1 else ''} on the board"
                    + (" (the caption points at one piece)" if counts[mover] == 1 else " (the caption cannot tell which)"))
    if m:
        bits.append(f"the blocker is {m.group(4)}" + (" (another colour)" if m.group(4) != m.group(2) else " (the same colour)"))
    return _rrow("the stuck moment", None, "; ".join(bits))


def captions_fit_row(manifest: dict, brief: dict) -> dict:
    """Asked: the captions fit the ending. Every caption the ad shows against the ending played (videoref.claims_against:
    no clear, win or beaten clock on a cliffhanger, no win on a time-out, no fail on a win or a near-fail), and a mistake
    caption against the play (a wrong move among its moments, 2026-10-17 round 2 case 09). In the
    reference group, so only the guided workflow is judged by it (round 2, 2026-10-17: "Board cleared!" on LolTap's
    unfinished board)."""
    from . import videoref as V
    ending = (manifest.get("gameplay") or {}).get("ending") or brief["gameplay"]["ending"]
    caps = [(L.get("id"), L.get("text")) for L in manifest.get("layers") or [] if L.get("text")]
    bad = [f"{lid} \"{text}\" claims {V.claims_against(text, ending)}" for lid, text in caps if V.claims_against(text, ending)]
    # the play too (round 2, case 09): a mistake caption needs a wrong move in the play (a mistake, a blocked attempt or
    # a cliffhanger's bump among the parts manifest's moments)
    wrong = any(m.get("kind") in WRONG_MOVES for m in manifest.get("moments") or [])  # "also: wrong_move" can be a hesitation
    ending_bad = bool(bad)
    bad += [f"{lid} \"{text}\" claims a wrong move the play does not have" for lid, text in caps
            if lid == "cap_mistake" and not wrong]
    gp = brief["gameplay"]
    planned = gp.get("mistakes") if gp.get("mistakes") is not None else {"near_fail": 1, "time_out": 1}.get(gp["ending"], 0)
    ok = not bad
    return {"check": "Asked: the captions fit the ending", "status": "pass" if ok else "failed",
            "detail": (f"the play ends {ending.replace('_', '-')}; " + ("every caption fits it" if ok else "; ".join(bad))
                       + f" ({len(caps)} captions)"), "from": "reference",
            "where": None if ok else "plan" if ending_bad or not planned else "play"}


STRETCHED_HOOK_MAX_S = 4.0  # the hook a stretched comparison expects is never longer (round 3, case 18: a 12 s "hook")


def _stretched_lengths(ref_len: dict, ad_len: dict, ref_total: float, total: float) -> dict:
    """The part lengths of an ad made from a reference shorter than it (round 1, LolTap: 15 s into 30 s; the share match
    had scaled its 3.9 s end card into 9 s): the hook, the result and the end card keep their own seconds (the end card
    3-4 s: never under the engine's shortest, at most 4 s), the play is the rest. Each part's error is its seconds off,
    over the ad's length; their mean passes at PART_LENGTH_ERROR. The hook expected is at most STRETCHED_HOOK_MAX_S."""
    from .ad import END_CARD_S
    want = {"hook": min(STRETCHED_HOOK_MAX_S, ref_len.get("hook", 0.0)), "result": ref_len.get("result", 0.0),
            "end": min(4.0, max(END_CARD_S[0], ref_len.get("end", 0.0)))}
    want["play"] = max(0.0, total - sum(want.values()))
    groups = [g for g in ("hook", "play", "result", "end") if ref_len.get(g) or g in ("play", "end")]
    errs = {g: abs(ad_len.get(g, 0.0) - want[g]) / total for g in groups}
    mae = sum(errs.values()) / len(errs)
    return _rrow("the part lengths", mae <= PART_LENGTH_ERROR,
                 f"the reference ({ref_total:g} s) is shorter than the ad ({total:g} s), so its hook and end card keep their "
                 f"seconds (the end card 3-4 s) and the play takes the rest: " + "; ".join(
                     f"{g} {want[g]:.1f} s expected, {ad_len.get(g, 0.0):.1f} s in the ad" for g in groups)
                 + f"; mean error {mae:.2f} of the ad's length (at most {PART_LENGTH_ERROR:g} passes)", "plan")


def _board_row(prompt: str, brief: dict, a: dict, notes: dict, focus: list, vdir: Path) -> dict:
    """Reference: the board. The made level (level.json in the version folder) against the board read in the reference,
    each part clamped as videoref clamped it: the shape equal, the size within a cell a side, the blocks within two, at
    least half of the reference's colours in the level. Parts the request states itself are its own; a part the accuracy
    pass does not show reliable is info ("read approximately")."""
    from . import reference as R
    from . import videoref as V
    colours_only = R.covers(focus, "board_colours") and not R.covers(focus, "board")
    if not R.covers(focus, "board") and not colours_only:
        return _rrow("the board", None, "not a focus of this reading")
    bd = V.board_of(notes)
    if bd is None:
        return _rrow("the board", None, "no board was read in the reference")
    fixed = V.stated(prompt, (a.get("plan") or {}).get("constraints") or [], video=True)
    if "level" in fixed:
        return _rrow("the board", None, f"the request names the game's own level; the reference's: {V.board_text(bd)}")
    made = made_board(Path(vdir) / "level.json", brief)
    if made is None:
        return _rrow("the board", None, "the version has no level.json to compare")
    shape = bd["shape"] if bd["shape"] and "shape" not in fixed else None
    w, h = V.board_size(shape or (made["shape"] if made["shape"] != "any" else None), bd["columns"], bd["rows"])
    want = {"shape": shape,
            "columns": w if "size" not in fixed else None, "rows": h if "size" not in fixed else None,
            "blocks": None if {"blocks", "moves"} & fixed else V.board_blocks(bd["blocks"], made["shape"], made["columns"],
                                                                                made["rows"], (brief.get("level") or {}).get("pieces")),
            "colours": [] if "colours" in fixed else bd["colours"], "size_read": (bd["columns"], bd["rows"]),
            "blocks_read": bd["blocks"], "shape_read": bd["shape"]}
    # the target is what the brief took from the reading, as videoref adapted it (the wall choice, the growth, the fill,
    # the colour mapping), not the raw reading (round 2, case 04: "holes, 1 wall cell" read became an open 5x7 by the
    # rules, and the row failed it against the raw "holes 4x7")
    taken, lv = set((brief.get("reference") or {}).get("set") or []), brief.get("level") or {}
    if "level.shape" in taken and lv.get("shape") not in (None, "any") and "shape" not in fixed:
        want["shape"] = lv["shape"]
    if "level.size" in taken and lv.get("width") and lv.get("height") and "size" not in fixed:
        want["columns"], want["rows"] = lv["width"], lv["height"]
    if "level.blocks" in taken and lv.get("blocks") is not None and not {"blocks", "moves"} & fixed:
        want["blocks"] = lv["blocks"]
    if "level.colours" in taken and lv.get("colours") and "colours" not in fixed:
        want["colours"] = list(lv["colours"])
    if colours_only:  # the blocks' colours alone are a focus (round 2, case 10)
        want.update(shape=None, columns=None, rows=None, blocks=None)
    parts = board_parts(want, made)
    if not parts:
        return _rrow("the board", None, "the request states the level itself" if fixed & {"shape", "size", "blocks", "colours"}
                     else "the reading gives no shape, size, blocks or colours")
    judged = {k: v for k, v in parts.items() if k in BOARD_RELIABLE}
    bits = [f"{k}: {'ok' if ok else 'differs'} ({d}){'' if k in BOARD_RELIABLE else ', read approximately'}" for k, (ok, d) in parts.items()]
    if bd.get("wall_cells") is not None and not colours_only:  # info until measured (round 1, 2026-10-17)
        bits.append(f"walls: {bd['wall_cells']} read, {made['walls']} made, read approximately")
    if colours_only:
        bits.append("the shape, the size and the blocks are not a focus (only the blocks' colours)")
    detail = "; ".join(bits) + (f"; the request's own: {', '.join(sorted(fixed & {'shape', 'size', 'blocks', 'colours'}))}"
                                if fixed & {"shape", "size", "blocks", "colours"} else "") + (
        f"; it looks {bd['busy']} (info: not used for the difficulty)" if bd.get("busy") else "")
    if not judged:
        return _rrow("the board", None, detail)
    ok = all(v[0] for v in judged.values())
    lv = brief.get("level") or {}
    carried = (want["shape"] in (None, lv.get("shape")) and (want["columns"] is None or (
               lv.get("width") is not None and lv.get("height") is not None and abs(lv["width"] - w) <= BOARD_SIZE_CELLS
               and abs(lv["height"] - h) <= BOARD_SIZE_CELLS))  # grown a cell a side to fit the blocks (videoref)
               and (want["blocks"] is None or lv.get("blocks") == want["blocks"]))
    return _rrow("the board", ok, detail, "play" if carried else "plan")


def reference_rows(prompt: str, brief: dict, record: dict, vdir: Path, rec_dir: Path | None = None) -> list[dict]:
    """The reference profile (spec section 5): the finished ad measured against the stored reading of
    the reference video. A row an aspect of the reading's focus does not cover is info; `where` is
    "plan" when the brief did not carry the reference's value and "play" or "ad" when it did and the
    result does not show it. An attached reference image gets one info row with its role."""
    from . import reference as R
    from . import videoref as V
    rows = []
    for r in ((brief.get("planner") or {}).get("references") or []):
        if isinstance(r, dict) and r.get("kind") == "image" and isinstance(r.get("role"), dict):
            rows.append(_rrow("the image's role", None, f"{r.get('file')}: {r['role'].get('primary') or 'reference'}"
                              + (f"; {'; '.join(r['role'].get('taken') or [])}" if r["role"].get("taken") else "")))
    a = _ref_video(brief)
    if a is None:
        return rows
    j = lambda p: json.loads(p.read_text()) if p.is_file() else {}  # noqa: E731
    manifest, ad = j(vdir / "parts.json"), j(vdir / "ad" / "ad.json")
    rows.append(captions_fit_row(manifest, brief))
    prov = brief.get("reference") or {}
    notes = a.get("notes") if isinstance(a.get("notes"), dict) else {}
    facts = a.get("facts") or {}
    asked_focus = list(a.get("focus") or []) + list(prov.get("named") or [])  # the plan's focus and what the words name
    filled = [x for x in prov.get("filled") or [] if not R.covers(asked_focus, x)]  # left open, filled from the reference
    focus = asked_focus + filled
    file = a.get("file")
    gp = brief["gameplay"]
    asked_ = asked(prompt, case_range=True)
    read = bool(notes) and not a.get("error") and not a.get("skipped")
    not_cov = "not a focus of this reading"
    start = len(rows)
    if read:
        segs = R.structure(notes.get("structure"), facts.get("duration_s"))
        # the ending
        want = V.mapped_ending(notes)
        if not R.covers(focus, "ending"):
            rows.append(_rrow("the ending", None, not_cov))
        elif asked_["ending"] or "ending" in V.stated(prompt, (a.get("plan") or {}).get("constraints") or [], video=True):
            # its words for the ending ("before solving it", "the final solution": videoref.ENDING_STATED, round 3 case 19)
            own = asked_["ending"] or gp["ending"]
            rows.append(_rrow("the ending", None, f"the request sets the ending itself ({own.replace('_', '-')}); "
                                                  f"the reference's is {(want or 'unread').replace('_', '-')}"))
        elif want is None:
            rows.append(_rrow("the ending", None, "the reference's ending was not read"))
        elif gp["ending"] != want:
            rows.append(_rrow("the ending", False, f"the reference ends {want.replace('_', '-')}; the plan says "
                                                   f"{gp['ending'].replace('_', '-')}", "plan"))
        else:
            played = (manifest.get("gameplay") or {}).get("ending")
            check = next((c for c in record.get("checks") or [] if c.get("check") == "Ending"), None)
            ok = (played in (None, want)) and (check is None or check.get("status") == "pass")
            rows.append(_rrow("the ending", ok, f"the reference ends {want.replace('_', '-')}; the play ends "
                                                f"{(played or want).replace('_', '-')}" + (f" ({check['detail']})" if check else ""), "play"))
        # the pacing: a sampled read gets it only approximately (2026-10-16 accuracy rounds), so it is judged only
        # when the request asks about the pacing: the reading plan says so (round 2, case 07: "Take only how fast the
        # moves come in this video" was planned for the pacing, but the word table has no "how fast"), the word table
        # only when there is no plan
        if not R.covers(focus, "pacing"):
            rows.append(_rrow("the pacing", None, not_cov))
        elif not pacing_asked(prompt, a):
            rows.append(_rrow("the pacing", None, "not judged: the request does not ask about the pacing, and a sampled reading "
                                                  f"gets it only approximately (read: {notes.get('pacing') or '?'}, "
                                                  f"{R.pace_change_of(a)[0] or '?'})"))
        else:
            ref_change, source = R.pace_change_of(a)
            measured = source in ("counts", "motion")
            ref_tempo = str(notes.get("pacing") or "").lower() or None
            fixed = V.stated(prompt, video=True)
            pace = pace_of_play(manifest)  # drags a second over the play: the tempo word only
            result = j(Path(rec_dir) / "result.json") if rec_dir else {}
            pauses = pause_pace(result.get("drags") or [])  # the pace change: the "Pacing curve" check's own measure
            bits, ok, judged, plan_miss = [], True, False, False
            tempo_source = (a.get("pacing") or {}).get("tempo_source")
            if ref_tempo in ("calm", "normal", "fast") and "tempo" not in fixed and tempo_source != "counts":
                bits.append(f"the reference's tempo ({ref_tempo}) is the model's own word, not a count of its moves, so it is "
                            f"not judged")
            elif ref_tempo in ("calm", "normal", "fast") and "tempo" not in fixed:
                if pace is None:
                    bits.append("the ad's tempo could not be read from its parts manifest")
                else:
                    judged = True
                    near = _tempo_near(ref_tempo, pace)
                    ok &= pace["tempo"] == ref_tempo or bool(near)
                    plan_miss |= brief["pacing"]["tempo"] != ref_tempo
                    bits.append(f"tempo {ref_tempo} in the reference, {pace['tempo']} in the ad ({pace['dps']:g} drags a second "
                                f"over the play)" + (f"; within {TEMPO_MARGIN:g} of the {near} boundary, so it passes" if near else ""))
            if ref_change and "curve" not in fixed:
                if pauses is None:
                    bits.append(f"the reference {ref_change}; the ad's change could not be measured (fewer than 6 drags recorded)")
                else:
                    judged = True
                    ok &= pause_change_ok(ref_change, pauses)
                    plan_miss |= brief["pacing"]["curve"] != ref_change.replace(" ", "_")
                    bits.append(f"the reference {ref_change}{' (' + source + ')' if measured else ''}; the ad: average pause "
                                f"{pauses['first']:.2f} s in the first third, {pauses['last']:.2f} s in the last third (the pauses "
                                f"between drags, as the Pacing curve check measures them)")
            if not bits:
                rows.append(_rrow("the pacing", None, "the request sets the pacing itself, or the reference's was not read"))
            elif not judged:
                rows.append(_rrow("the pacing", None, "; ".join(bits)))
            else:
                rows.append(_rrow("the pacing", ok, "; ".join(bits) + " (the reference's pacing was read approximately: a "
                                                                      "sampled read)", "plan" if plan_miss else "play"))
        # the hook
        layers = {L["id"]: L for L in manifest.get("layers") or [] if L.get("from_s") is not None}
        if not R.covers(focus, "hook"):
            rows.append(_rrow("the hook", None, not_cov))
        else:
            rows.append(hook_row(notes, segs, manifest, layers))
        # the purposes in order and the part lengths
        if not R.covers(focus, "structure"):
            rows.append(_rrow("the purposes in order", None, not_cov))
            rows.append(_rrow("the part lengths", None, not_cov))
        elif a.get("parts_dropped") or not segs:  # per-section validation (2026-10-17): no parts, nothing to compare
            why = a.get("parts_dropped") or "the reading gave no parts"
            rows.append(_rrow("the purposes in order", None, why))
            rows.append(_rrow("the part lengths", None, why))
        else:
            want_seq = _in_order([s["purpose"] for s in segs if s["purpose"] in STAGEABLE])
            have_seq = _in_order([p for _, p in ad_purposes(manifest, brief)])
            own_ending = "ending" in V.stated(prompt, video=True)
            # a request with its own ending (case 10: a near-fail asked, a time-out reference): the reference's fail and the
            # ad's victory are both the result
            res = (lambda seq: _in_order(["result" if p in ("victory", "fail") else p for p in seq])) if own_ending else (lambda seq: seq)  # noqa: E731
            want_cmp = _stages(res(want_seq))
            asked_len = asked(prompt, case_range=True).get("length_s")
            replay_optional = (asked_len is not None and asked_len < V.REPLAY_ROOM_S and "replay" in want_cmp
                               and "replay" not in _stages(res(have_seq)))
            if replay_optional:  # a short asked length leaves no room to be sure of a replay (videoref, case 13)
                want_cmp = [p for p in want_cmp if p != "replay"]
            ok = _subsequence(want_cmp, _stages(res(have_seq)))  # the detail still shows both full sequences
            carried = {"mistake": (gp.get("mistakes") or 0) > 0 or gp["ending"] in ("near_fail", "time_out") and gp.get("mistakes") is None,
                       "near_fail": gp["ending"] == "near_fail", "fail": gp["ending"] == "time_out",
                       "victory": gp["ending"] in ("win", "near_fail"), "end_card": bool(brief["sequence"].get("end_card")),
                       "replay": bool(brief["sequence"].get("replay")), "question": gp["ending"] == "cliffhanger"}
            if own_ending:
                carried.update(victory=True, fail=True, near_fail=True)
            where = "plan" if any(not carried.get(p, True) for p in want_seq) else "play"
            rows.append(_rrow("the purposes in order", ok, f"the reference: {' -> '.join(want_seq) or 'none'}; the ad: "
                                                           f"{' -> '.join(have_seq) or 'none'}" +
                              ("; the request sets its own ending, so the reference's win or fail and the ad's are compared as "
                               "the result" if own_ending else "") +
                              (f"; the reference's replay is optional at {asked_len:g} s" if replay_optional else ""), where))
            ref_len = ref_part_lengths(segs)
            # a reference with no hook part: the ad's hook caption runs over its play, which is play (round 1, 2026-10-17)
            ad_len = ad_part_lengths(manifest, hook_is_play=not ref_len.get("hook"))
            ref_total = float(facts.get("duration_s") or 0) or sum(s["to_s"] - s["from_s"] for s in segs)
            total = float(manifest.get("duration_s") or record.get("length_s") or 0)
            groups = [g for g in ("hook", "play", "result", "end") if ref_len.get(g)]
            if ref_total and total and ref_total < V.SHORTER * total and ref_len.get("play"):
                rows.append(_stretched_lengths(ref_len, ad_len, ref_total, total))
                ref_len = None
            kept_cta = 0.0
            if ref_len is None:
                pass
            elif not ref_len.get("end") and ad_len.get("end"):
                # an ad keeps its call to action: with no end card in the reference, the ad's end card up to the engine's
                # shortest is not counted against the play share
                from .ad import END_CARD_S
                kept_cta = min(ad_len["end"], END_CARD_S[0])
                ad_len["end"] -= kept_cta
                total -= kept_cta
            if ref_len is None:
                pass  # compared in seconds above (a reference shorter than the ad)
            elif not groups or not total or not ref_total:
                rows.append(_rrow("the part lengths", None, "no parts to compare"))
            else:
                errs = {g: abs(ref_len[g] / ref_total - ad_len.get(g, 0.0) / total) for g in groups}
                mae = sum(errs.values()) / len(errs)
                rows.append(_rrow("the part lengths", mae <= PART_LENGTH_ERROR,
                                  f"normalised mean absolute error {mae:.2f} (at most {PART_LENGTH_ERROR:g} passes): " + "; ".join(
                                      f"{g} {ref_len[g] / ref_total:.0%} of the reference, {ad_len.get(g, 0.0) / total:.0%} of the ad"
                                      for g in groups)
                                  + (f"; the reference has no end card, so the ad's first {kept_cta:g} s of end card (its call "
                                     f"to action, the engine's shortest) are not counted" if kept_cta else "")
                                  + ("; the reference has no hook part, so the ad's hook caption over the play counts as play"
                                     if not ref_len.get("hook") and ref_len.get("play") else ""), "plan"))
        # the captions
        if not R.covers(focus, "captions"):
            rows.append(_rrow("the captions", None, not_cov))
        else:
            fns = V.caption_functions(notes)
            if not fns:
                rows.append(_rrow("the captions", None, "the reference shows no caption the tool could tell the function of"))
            else:
                missing = [fn for fn in fns if not (layers.get(CAPTION_LAYERS[fn]) or {}).get("text")]
                planned = [fn for fn in missing if brief["concept"].get(CAPTION_FIELDS[fn])]
                rows.append(_rrow("the captions", not missing, f"the reference's captions: {', '.join(fns)}; " +
                                  ("the ad has one for each" if not missing else f"the ad has none for {', '.join(missing)}"),
                                  "play" if missing and len(planned) == len(missing) else "plan"))
        # the look
        if "look" not in focus:
            rows.append(_rrow("the look", None, "the look was not a focus of this reading: the game's own"))
        else:
            dom = [h for h in notes.get("dominant_colours") or [] if isinstance(h, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", h)]
            names = {R.colour_name(h.upper()) for h in dom}
            poster = vdir / "ad" / "poster.png"
            vs = brief["visuals"]
            if not dom:
                rows.append(_rrow("the look", None, "no dominant colours were read in the reference"))
            elif not vs.get("background"):
                rows.append(_rrow("the look", False, "the plan took no background from the reference", "plan"))
            else:
                # (a) the plan: did the brief take the reference's palette (by family or by distance, as the style kit lightens it)
                fam = lambda x: any(same_family(n, x) or same_family(x, n) for n in names)  # noqa: E731
                bg = [h.upper() for h in vs["background"] if isinstance(h, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", h)]
                taken = [(h, min(dom, key=lambda d: _rgb_dist(h, d.upper())).upper()) for h in bg]
                a_ok = any(fam(R.colour_name(h)) or _rgb_dist(h, d) <= LOOK_RGB for h, d in taken)
                plan_bits = "; ".join(f"{h} ({R.colour_name(h)}) is {_rgb_dist(h, d):.0f} from {d} ({R.colour_name(d)})" for h, d in taken)
                # (b) the ad: did the poster show the brief's background (either stop of the gradient, or between them)
                b_ok, ad_bit = None, "the poster could not be read"
                if poster.is_file():
                    rgb = poster_background(poster)
                    seen = "#%02X%02X%02X" % tuple(rgb)
                    dist = _gradient_dist(seen, bg) if bg else 999.0
                    b_ok = dist <= LOOK_RGB
                    ad_bit = f"the frame's margins are {seen} ({nearest_named(rgb)}), {dist:.0f} from the brief's background"
                fill = vs.get("caption_fill")
                fill_name = R.colour_name(fill.upper()) if isinstance(fill, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", fill) else None
                ok_fill = fill_name is None or fam(fill_name) or fill_name in ("white", "black", "dark grey")
                detail = (f"the reference's colours: {', '.join(sorted(names))}; the brief's background {' to '.join(bg) or 'none'}: "
                          f"{plan_bits or 'nothing taken'} ({'taken' if a_ok else 'not taken'}, by family or within {LOOK_RGB:g}); "
                          f"{ad_bit}" + ("" if b_ok is None else f" ({'shown' if b_ok else 'not shown'}, within {LOOK_RGB:g})") +
                          (f"; the captions {fill} ({fill_name}{', for contrast' if fill_name in ('white', 'black', 'dark grey') else ''})"
                           if fill_name else ""))
                if b_ok is None and a_ok:
                    rows.append(_rrow("the look", None, detail))
                else:
                    rows.append(_rrow("the look", bool(a_ok and b_ok and ok_fill), detail, "plan" if not a_ok else "ad"))
        # the board (2026-10-17); copied cell by cell from the video's frame (2026-10-19): the image rows, named for the video
        if (prov.get("board") or {}).get("copied"):
            from . import imageaudit as IA
            for r in IA.copied_board_rows(prompt, prov, vdir) + [x for x in [IA.likeness_row(prov, vdir)] if x]:
                r["check"] = r["check"].replace("Image: ", "Video: ").replace("the picture", "the video's frame").replace("picture's", "video's")
                rows.append(r)
        else:
            rows.append(_board_row(prompt, brief, a, notes, focus, vdir))
        rows.append(screen_row(prompt, brief, a, notes, focus))
        stuck = stuck_row(manifest, vdir)
        if stuck:
            rows.append(stuck)
        # what the request left open and the reference filled is info (round 2, case 14)
        by_aspect = {"the ending": "ending", "the purposes in order": "structure", "the part lengths": "structure",
                     "the board": "board", "the screen": "screen"}
        for row in rows[start:]:
            aspect = by_aspect.get(row["check"].removeprefix("Reference: "))
            if aspect in filled and row["detail"] != not_cov:
                _as_filled(row)
    else:
        rows.append(_rrow("not read", None, f"{file}: {a.get('error') or a.get('skipped') or 'nothing was read'}; the ad was planned without it"))
    if manifest:  # the HUD over the board, measured on the first frame of play (2026-10-17)
        rows.append(hud_row(prompt, brief, vdir, manifest))
    # nothing copied (always measurable)
    uses = sorted({lid for lid, L in (ad.get("layers") or {}).items() if file and file in json.dumps(L)}
                  | {x["file"] for x in brief.get("assets") or [] if x.get("file") == file})
    if uses:
        rows.append(_rrow("nothing copied", False, f"{file} is used by {', '.join(uses)} in the ad", "ad"))
    elif prov.get("not_copied"):
        rows.append(_rrow("nothing copied", True, f"no layer of the ad uses {file}; not copied: {', '.join(prov['not_copied'])}"))
    else:
        rows.append(_rrow("nothing copied", None, f"no layer of the ad uses {file}; the brief has no provenance record"))
    conf = a.get("confidence")
    rows.append(_rrow("read with confidence", None, f"level {a.get('level') or 'none'}, focus {', '.join(asked_focus) or 'none'}"
                                                    + (f", filled from the reference (the request left it open): {', '.join(filled)}"
                                                       if filled else "") + ", "
                                                    f"{float(a.get('analysed_s') or 0):g} s analysed, confidence "
                                                    f"{conf if conf is not None else 'not given'}"
                      + ("; read with low confidence" if a.get("low_confidence") else "")))
    return rows
