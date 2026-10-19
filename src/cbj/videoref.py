"""Video-guided creative generation (core requirement 4, case p.6): what a reference video gives the brief.

The video has been read for the request before this runs (reference.read_video: the reading plan
from the request, the whole clip read by NVIDIA's multimodal model, the checks in code, the parts
snapped to measured cuts when the reading needed it). Mirroring imageref.py, this module writes into
the brief, in code, only what the reading's focus allows, and only where the request does not state
the value itself (the request always wins: a 45 s request stays 45 s, "no replay" stays):

| focus     | what it sets |
|-----------|--------------|
| concept   | everything below except the look (a "version of this concept" keeps the game's own look) |
| hook      | concept.hook from the hook's function (a question, a challenge, a dare) in the tool's own words |
| pacing    | pacing.tempo, pacing.curve (computed from the moves counted per third: reference.pacing_from), level.moves for a long play |
| captions  | the concept texts by function (challenge, instruction, urgency, result, call to action), own words |
| ending    | gameplay.ending (a question part is a cliffhanger; a hard level for a near-fail), gameplay.mistakes (the wrong moves listed), gameplay.finish streak for a payoff part |
| look      | imageref.style_kit fed with the dominant colours: background and captions; blocks never repainted |
| structure | the length, sequence.replay (a replay part, or a moment shown again), sequence.hold_s, sequence.end_card |
| board     | the level's type when the request says nothing about the level: level.source generate, shape, width/height and blocks (clamped to what the generator makes), colours (mapped to the game's seven), pieces; how busy it looks is info only (the difficulty is the request's, the ending's or the generator's) |

A mechanic the game does not have (another game's bubbles, ice, keys, boosters) is never created, drawn, simulated
or used (2026-10-17, the owner): it is listed as "not used: not in Color Block Jam", one line each, and goes to
not_copied; a MECHANICS row only says which of the game's own parameters (an ending, a finish) the ad keeps.
The level is built only by the generator's own rules from the shape, size, block count, colours and pieces;
the board's exact cells are never copied. brief["reference"] is the provenance, written by code: what was
adapted and what was not copied (the evaluation's "nothing copied" row reads it).
"""

from __future__ import annotations

import re

from . import brief as B
from .reference import covers, focus_text, pace_change_of

NOT_COPIED = ("the reference's gameplay", "its characters and assets", "its exact frames")
GAME_RESULT_S = 2.5  # the game's own result screen in the ad (ad.RESULT_HOLD_S): a longer result part is held
HOLD_MAX_S = 4.0  # ad.RESULT_HOLD_MORE_S: a result held longer than this reads as a frozen screen
LONG_PLAY = 0.5  # one gameplay part this long (a share of the reference) is a long play: more moves
ENDING_WORDS = {"win": "clean win", "near_fail": "near-fail", "time_out": "time-out", "cliffhanger": "cliffhanger"}
ENDING_OF = {"win": "victory", "victory": "victory", "near-fail": "near_fail", "near_fail": "near_fail",
             "near fail": "near_fail", "near miss": "near_fail", "fail": "time_out", "time-out": "time_out",
             "time_out": "time_out", "lose": "time_out", "cliffhanger": "cliffhanger", "stopped": "cliffhanger",
             "stops mid-level": "cliffhanger", "mid-level": "cliffhanger", "stopped mid-level": "cliffhanger"}
# A mechanic the game does not have is never created, drawn, simulated or used (2026-10-17, the owner). A row here only
# names the game's OWN parameter the reference's moment shares (the ending, the finish), and its line says the ad keeps
# that one when the brief has it; the mechanic itself is "not used: not in Color Block Jam" either way. (Before
# 2026-10-17 ice became "a blocked route" and keys "a key move": lines that read as if the foreign thing were kept.)
MECHANICS = (
    (re.compile(r"\b(boosters?|hammers?|power[- ]?ups?|bombs?|extra time|time bonus|time freeze)\b", re.I),
     lambda b: b["gameplay"]["ending"] == "near_fail", "the ad keeps the game's own near-fail"),
    (re.compile(r"\b(merg\w*|match[- ]?(3|three)|three in a row)\b", re.I),
     lambda b: b["gameplay"].get("finish") == "streak", "the ad keeps the game's own fast finish (the blocks leave one after another)"),
)
NOT_SHOWN = re.compile(r"\b(level map|world map|map|chapters?|level select\w*)\b", re.I)  # the ad shows one level
# Another game's things, checked before the game's own names (a "bubble on the gate" is not the game's gate).
FOREIGN = re.compile(r"\b(bubbles?|ice|icy|frozen|freez\w*|keys?|locks?|locked|padlocks?|chains?|chained|crates?|cages?|caged|"
                     r"vacuum\w*|magnets?|rockets?|undo|hints?|boost\w*|"
                     r"bombs?|boosters?|hammers?|power[- ]?ups?|teleport\w*|portals?|rotat\w*|gravity|swap\w*|shuffl\w*|"
                     r"stars?|hearts?|lives|merg\w*|match[- ]?(3|three)|break\w*|crack\w*|melt\w*|shatter\w*)\b", re.I)
# Mechanics the game has under another name.
NATIVE = (
    # the game's own screens and HUD (2026-10-16 creative run: "Level complete screen" and "Level indicator" were
    # written up as "not in Color Block Jam")
    (re.compile(r"\b(level\s+(complete|completed|cleared|completion|failed)|results?\s+screen|win\s+screen|victory\s+screen|"
                r"out\s+of\s+time|fail(ure)?\s+screen|game\s+over)\b", re.I), "{m}: the game's own result screen"),
    (re.compile(r"\b(level\s+(indicator|number|label|counter|progression)|hud|score|coins?|rewards?)\b|(^|\s)\+\s*\d+", re.I),
     "{m}: the game's own HUD"),
    (re.compile(r"\b(slid\w*|drag\w*|mov\w*|push\w*)\b", re.I), "{m} become the game's own drags"),
    (re.compile(r"\b(gates?|doors?|exits?|colou?r[- ]match\w*)\b", re.I), "{m}: the game's own gates of the block's colour"),
    (re.compile(r"\b(timers?|clocks?|countdowns?|time limits?)\b", re.I), "{m}: the game's own countdown clock"),
    (re.compile(r"\b(walls?|wall cells?|blocked cells?|inactive cells?)\b", re.I), "{m}: the game's own walls (the board's shape)"),
    (re.compile(r"\b(grids?|boards?|tiles?|cells?)\b", re.I), "{m}: the game's own board"),
    (re.compile(r"\b(hand|finger|cursor|pointer|tap ring)\b", re.I), "{m}: the ad's own cursor"),
)
# The game's own wall cells as a reader names them among the board's obstacles (v9, 2026-10-17: on the still the tool's own
# grey wall cells came back as "4 dark grey fixed obstacles", "grey barriers", "grey blocks", "blockers"): a fixed,
# grey or dark cell that is no other game's thing is a wall, part of the board's shape, never "not used".
WALL_LIKE = re.compile(r"\b(walls?|wall cells?|barriers?|blockers?|blocked cells?|inactive cells?|fixed|immovable|solid|"
                       r"grey|gray|dark|black|stone|rock)\b", re.I)
NOT_USED = "not used: not in Color Block Jam"
# A tempo the request states itself: the word describes the pace ("fast-paced", "fast pacing", "a calm tempo", "the
# pacing is fast", "tempo: slow"). "How fast the moves come" is a question about the reference's pace, not a stated
# tempo (2026-10-16 creative run, case 06: "the pacing of this video: how fast..." blocked the reference's tempo).
TEMPO = re.compile(r"(?<!how )(?<!how-)\b(fast|quick|rapid|snappy|frantic|energetic|brisk|calm|slow|relaxed|relaxing|leisurely|"
                   r"gentle|steady)[\s-]*(paced|pace|pacing|tempo)\b|"
                   r"\b(tempo|pace|pacing)\s*(:|is|was|should be|stays|feels|to be)?\s*(very |quite |really |a bit |nice and )?"
                   r"(fast|quick|calm|slow|normal|steady|relaxed)\b|\bspeedrun\b", re.I)
CURVE = re.compile(r"\b(speeds? up|speeding up|slows? down|slowing down|builds? (up|tension)|escalat\w*|accelerat\w*|"
                   r"gets? (faster|slower)|starts? slow)\b", re.I)
MOVES = re.compile(r"\b\d{1,2}\s+(moves|drags)\b", re.I)
# the request's relative words for the moves or the blocks (2026-10-17, the owner's "use fewer moves so each one matters":
# the planner read about 6, then the play levers set 10 to fill the reference's pace): stated values on the video path
# (stated(video=True)), so the levers keep the planner's count and never raise it
RELATIVE_MOVES = re.compile(r"\b(fewer|less|more|a few|few|a handful of|a couple of|several)\s+(\w+\s+)?(moves|drags|steps)\b",
                            re.I)
RELATIVE_BLOCKS = re.compile(r"\b(fewer|less|more|a few|few|a handful of|a couple of|several)\s+(\w+\s+)?(blocks|pieces)\b",
                             re.I)


RELATIVE_FEWER, RELATIVE_A_FEW, RELATIVE_MORE = 0.7, (4, 5), 1.3  # of the reference's counted moves
RELATIVE_FLOOR, RELATIVE_MAX = 4, 14  # the fewest moves "fewer" gives; generate._target_drags' most
TEMPO_BASE_MOVES = {"calm": 7, "normal": 9, "fast": 11}  # no usable count: the reference's tempo class, estimated


def reference_moves(a: dict, notes: dict) -> tuple[int | None, str]:
    """The reference's counted moves (reference.pacing_from's moves_by_third, the reading's own, or the structure's
    gameplay parts' moves), with where it came from; (None, "") when nothing usable was counted."""
    for src, thirds in (("counted over its gameplay", (a.get("pacing") or {}).get("moves_by_third")),
                        ("read by thirds", notes.get("moves_by_third"))):
        if isinstance(thirds, list) and thirds and all(isinstance(x, (int, float)) for x in thirds) and sum(thirds) > 0:
            return int(round(sum(thirds))), src
    parts = [s.get("moves") for s in _segs(notes) if s.get("purpose") in PLAY_PURPOSES]
    if parts and all(isinstance(x, (int, float)) for x in parts) and sum(parts) > 0:
        return int(round(sum(parts))), "the gameplay parts' moves"
    return None, ""


def relative_count(phrase: str, a: dict, notes: dict) -> tuple[int, str]:
    """The moves a relative request means (2026-10-17, round 4 case 28: the planner gave no number for "fewer moves" and
    the fill played 10): "fewer"/"less" about 70% of the reference's counted moves (at least 4), "a few"/"a couple of"/"a
    handful of"/"several" 4-5, "more" about 130% (at most 14, the generator's most); with no usable count the reference's
    tempo class gives the base (calm 7, normal 9, fast 11), estimated. Returns (moves, the arithmetic in words)."""
    ref, src = reference_moves(a, notes)
    estimated = ref is None
    if estimated:
        word = str((a.get("pacing") or {}).get("tempo") or notes.get("pacing") or "normal").lower()
        word = word if word in TEMPO_BASE_MOVES else "normal"
        ref, src = TEMPO_BASE_MOVES[word], f"estimated from its {word} tempo (no usable count)"
    p = phrase.lower()
    if re.match(r"(fewer|less)\b", p):
        n, how = max(RELATIVE_FLOOR, int(round(RELATIVE_FEWER * ref))), f"about 70% of {ref}, at least {RELATIVE_FLOOR}"
    elif re.match(r"more\b", p):
        n, how = min(RELATIVE_MAX, int(round(RELATIVE_MORE * ref))), f"about 130% of {ref}, at most {RELATIVE_MAX}"
    else:
        lo, hi = RELATIVE_A_FEW
        n, how = (hi if ref >= 8 else lo), f"{lo}-{hi} ({hi if ref >= 8 else lo} for a reference of {ref})"
    return n, f"\"{phrase}\": {n} moves, {how}; the reference's {ref} moves {src}"


def relative_moves(prompt: str) -> str | None:
    """The request's relative words for the moves or the blocks ("fewer moves", "a few moves", "fewer blocks"), or None."""
    m = RELATIVE_MOVES.search(prompt or "") or RELATIVE_BLOCKS.search(prompt or "")
    return m.group(0).lower() if m else None
HOLD = re.compile(r"\b(hold|held|holds)\b[^.;]{0,30}\b(result|win|ending|board|screen|question)\b|"
                  r"\b(result|win|ending|board|screen|question)\b[^.;]{0,15}\b(held|hold|holds)\b", re.I)
CAPTION_LOOK = re.compile(r"\bcaptions?\b[^.;]{0,30}\b(colou?rs?|white|yellow|black|red|blue|green|pink|purple|orange|outline)\b", re.I)
SAME_TEXT = re.compile(r"\bsame (text|texts|captions?|words|wording|copy|lines)\b|\b(its|their|the) exact (text|captions?|words|"
                       r"wording|lines)\b|\bword for word\b|\bverbatim\b", re.I)
REPEAT = re.compile(r"\b(replay\w*|again|repeat\w*|slow[- ]?mo\w*|slow motion|rewind\w*|second time|once more)\b", re.I)
FAST_FINISH = re.compile(r"\b(fast|quick|rapid|rush\w*|cascade|in a row|one after another|chain|streak|all (fly|leave|clear)\w*|"
                         r"frees? (them all|everything))\b", re.I)
# What a caption does, from its words (2026-10-16: the case's captions are challenges, instructions,
# urgency, results and calls to action).
CTA_RX = re.compile(r"\b(play now|download|install|get it|play (for )?free|try (it )?now|tap to play|play today)\b", re.I)
# In this order: a question or a dare is a challenge before anything else (2026-10-16 creative run, case 07: "Can you
# beat the clock?" came out as urgency because of "clock"); a wrong move's line ("Wait... that's wrong!") is its own
# function, and a correction's ("Found it!") is an instruction, the caption on the fix.
CAPTION_RX = (
    ("challenge", re.compile(r"\?\s*$|\b(can you|bet|only \d|dare|try to|beat (this|it)|challenge|impossible|genius|iq)\b", re.I)),
    ("cta", CTA_RX),
    ("result", re.compile(r"\b(level (complete\w*|cleared|passed)|complete\w*|cleared|you win|victory|done|perfect|great job|"
                          r"nice|awesome|phew|made it|success|solved|so close|not this time|almost had it|just in time)\b", re.I)),
    ("urgency", re.compile(r"\b(hurry|quick|faster|running out|time'?s? (up|running|almost)|last seconds?|almost out|clock)\b", re.I)),
    ("wrong", re.compile(r"\b(wrong|oops|whoops|not that one|nope|uh[- ]oh|mistake)\b", re.I)),
    ("instruction", re.compile(r"^\s*(tap|drag|move|swipe|slide|match|find|clear|free|get|pull|push|use|start with)\b|"
                               r"\b(first|then|next|found it|there it is|got it|that'?s it|aha)\b", re.I)),
)
PURPOSE_FUNCTION = {"hook": "challenge", "mistake": "wrong", "near_fail": "urgency", "victory": "result", "question": "result",
                    "end_card": "cta"}
FIELD_OF = {"challenge": "hook", "wrong": "mistake", "instruction": "fix", "urgency": "hurry", "result": "result", "cta": "cta"}
OWN_LINES = {"instruction": "Move this one first!", "wrong": "Oops!", "urgency": "Hurry up!", "cta": "PLAY NOW",
             "result": {"near_fail": "Just in time!", "win": "Cleared!", "time_out": "So close!",
                        "cliffhanger": "Can you see the move?"}}
HOOK_WORDS = {"question": "the hook's question", "challenge": "the challenge hook", "dare": "the hook's dare"}


# ---------- what the request fixes itself ----------

# The level as the request states it (2026-10-17): its shape, its size, its pieces, its difficulty, the game's own level.
# Words that point at the reference ("the same layout", "its structure") and the gates ("doors") are not a stated shape.
SHAPE_STATED = re.compile(r"\b(narrow|waist|bottleneck|hourglass|doorway|two rooms|holes?|pillars?|cross[- ]shaped|plus[- ]shaped|"
                          r"cross|ring|donut|doughnut|lanes?|corridors?|walls?|wall cells|maze|rectangular|"
                          r"(open|plain|empty|square) (board|grid|level|layout))\b", re.I)
SIZE_STATED = re.compile(r"\b(big|bigger|large|larger|small|smaller|tiny|huge|giant|wide|wider|tall|taller|compact|mini)\s+"
                         r"(board|grid|level|map|puzzle)\b|\b(board|grid)\b[^.;]{0,20}\b(big|bigger|large|small|smaller|tiny|"
                         r"huge|wide|tall)\b", re.I)
NxM = re.compile(r"\b(\d{1,2})\s*(?:x|×|by)\s*(\d{1,2})\b", re.I)
PIECES_STATED = re.compile(r"\b(big|bigger|chunky|large|huge|giant|small|smaller|tiny|little|long|longer|short|l[- ]shaped|"
                           r"t[- ]shaped|square|varied|different|mixed|various|assorted)\s+(blocks?|pieces?|shapes?)\b|"
                           r"\b(long )?bars\b|\bsticks\b|\b(mix|variety) of (block )?shapes\b", re.I)
DIFFICULTY_STATED = re.compile(r"\b(easy|easier|simple|hard|harder|difficult|tough|tricky|challenging|brutal|medium|moderate|"
                               r"intermediate|beginner\w*|expert|impossible|insane)\b", re.I)
# as brief._evidence reads "gameplay.blocks_left": "with two blocks left", "one move away", "the last block"
BLOCKS_LEFT_STATED = re.compile(r"\b(one|1|two|2|three|3|a single|the last|the final)\s+(\w+\s+)?(blocks?|pieces?|moves?)\b[^.]{0,40}"
                                r"\b(left|remaining|away|before|short|to go)\b|\b(one|a single|the last|the final|decisive) "
                                r"(move|drag|block)\b|\bone (move|step|drag) (away|from|short)\b|\bleaving (one|a single|two)\b", re.I)
INTRO_STATED = re.compile(r"\b(still|frozen|static|held)\s+(opening|first frame|intro|start)\b|\bintro\b|"
                          r"\bopening (frame|hold|freeze)\b", re.I)
STYLE_STATED = re.compile(r"\b(symmetr\w*|mirror\w*|packed|crowded|cramped|dense|spacious|roomy|colou?rful|"
                          r"room to move|plenty of space)\b", re.I)  # the level's look (brief.STYLES), as the request words it
GAME_LEVEL = re.compile(r"\b(shipped|the game'?s own|original|real|actual) levels?\b|"
                        r"\blevel\s+\d{1,4}\b(?!\s*(s|sec|seconds?|-second|blocks?|colou?rs?|moves?))", re.I)


FROM_SOURCE = re.compile(r"\b(source|reference|the video|the clip|this video|this clip|original|input|matching)\b", re.I)


def own_constraints(constraints=()) -> list[str]:
    """The reading plan's constraints that are the request's own: one that cites the reference ("Length around 30 s,
    matching the source", round 1 2026-10-17) is the reference's value, not the request's, and fixes nothing."""
    return [str(c) for c in constraints or () if not FROM_SOURCE.search(str(c))]


def stated(prompt: str, constraints=(), video: bool = False) -> set[str]:
    """What the request states itself (and so the reference may not set), from its words and the
    reading plan's constraints: length, ending, mistakes, difficulty, finish, tempo, curve, moves,
    replay, end_card, result_screen, hold, background, caption_colours, no_captions; and the level
    (2026-10-17): shape, size, blocks, colours, pieces, level (the game's own level, or a level number).
    `video` (the video-reference workflow only; round 3): the case's 30-60 s range is no length, the solve phrases
    (SOLVE_PHRASES) state the ending, the breathe words (BREATHE) the hold and the replay, and the relative words for the
    moves or the blocks ("fewer moves", "a few moves", "fewer blocks": RELATIVE_MOVES, RELATIVE_BLOCKS) the moves. The image workflow, which
    reads this too, keeps the rules it had (the owner, 2026-10-17)."""
    from . import audit
    from .planner import _NO_CAPTIONS
    text = (prompt or "") + ". " + ". ".join(own_constraints(constraints))
    a = audit.asked(text, case_range=video)
    out = set()
    for key, name in (("length_s", "length"), ("ending", "ending"), ("mistakes", "mistakes"), ("difficulty", "difficulty"),
                      ("background", "background"), ("blocks", "moves")):
        if a.get(key) is not None:
            out.add(name)
    if a.get("satisfying"):
        out.add("finish")
    out |= {k for k in ("replay", "end_card", "result_screen", "result_first") if k in (a.get("sequence") or {})}
    for rx, name in ((TEMPO, "tempo"), (CURVE, "curve"), (MOVES, "moves"), (HOLD, "hold"), (CAPTION_LOOK, "caption_colours"),
                     (_NO_CAPTIONS, "no_captions")):
        if rx.search(text):
            out.add(name)
    words = re.sub(r"\bcolou?r[\s-]*block[\s-]*jam\b", " ", text, flags=re.I)
    shape_words = re.sub(r"\b[a-z][- ]shaped (blocks?|pieces?)\b|\bshaped (blocks?|pieces?)\b", " ", words, flags=re.I)
    if SHAPE_STATED.search(shape_words) or a.get("shape") or a.get("walls") is not None:
        out.add("shape")
    if SIZE_STATED.search(words) or any(max(int(m.group(1)), int(m.group(2))) >= 4 for m in NxM.finditer(words)):
        out.add("size")
    if a.get("blocks") is not None:
        out.add("blocks")
    if a.get("colour_names") or a.get("colours") is not None or a.get("colour_counts"):
        out.add("colours")
    if PIECES_STATED.search(words):
        out.add("pieces")
    if DIFFICULTY_STATED.search(words):
        out.add("difficulty")
    if GAME_LEVEL.search(words):
        out.add("level")
    if a.get("style") or STYLE_STATED.search(words):
        out.add("style")
    if INTRO_STATED.search(words):
        out.add("intro")
    if BLOCKS_LEFT_STATED.search(words):
        out.add("blocks_left")
    if ENDING_STATED.search(words) or video and SOLVE_STATED.search(words):
        out.add("ending")
    if video and BREATHE.search(words):
        out |= {"hold", "replay"}  # the result held, no replay of the play (breathe)
    if video and (RELATIVE_MOVES.search(words) or RELATIVE_BLOCKS.search(words)):
        out.add("moves")  # "fewer moves", "a few moves", "fewer blocks": the planner's count stays (play_levers)
        if RELATIVE_BLOCKS.search(words):
            out.add("blocks")
    if MISTAKES_STATED.search(words):
        out.add("mistakes")
    if a.get("hesitations") is not None:
        out.add("hesitations")
    return out


# The request's own words for a solved level (round 3, case 19: "give the final solution a satisfying moment to breathe"
# kept the reference's cliffhanger and the board was never solved): the solution, the solve, a satisfying clear, the
# last move clears, the whole board cleared
# round 4, case 30: words that imply a win ("a replay of the winning move", "after the win", "once it's solved", "the level
# completed screen") are the request's own ending too
SOLVE_PHRASES = (r"\bthe winning move\b|\b(after|show|see) the win\b|\breplay(s|ing)? (of )?the (win|winning move|solve|solution|"
                 r"last move)\b|\bonce (it'?s|it is|the (level|board|puzzle) is) (solved|cleared)\b|\bthe level complete(d)? screen\b|"
                 r"\bthe (final |last )?(solution|solve|solved board)\b|\ba satisfying (solve|solution|finish|clear)\b|"
                 r"\bclears? the (whole |entire )?board\b|\bthe (last|final) move clears\b|\bfinish(es|ed|ing)? the level\b")

# the request speaks of how the level ends ("show the player stuck once before solving it", round 2 case 14; "stop
# before the level is solved", case 05): its ending is its own, never filled from the reference (2026-10-17)
ENDING_STATED = re.compile(
    r"\b(solv(e|es|ed|ing)|clear(s|ed|ing)?|beat(s|ing)?|win(s|ning)?|los(e|es|ing)|fail(s|ed|ing)?|finish(es|ed|ing)?)\s+"
    r"(it|the (level|board|puzzle|game|round|stage))\b"
    r"|\b(level|board|puzzle|round|stage) (is|gets|was) (solved|cleared|beaten|finished|lost|failed)\b"
    r"|\bcliff-?hanger\b|\b(a|the) (win|victory|fail|loss)\b|\b(win|victory|fail) screen\b"
    r"|\b(un|never )(solved|finished)\b", re.I)
SOLVE_STATED = re.compile(SOLVE_PHRASES, re.I)  # stated(video=True) only: the video-reference workflow's ending words

# A plain solve (round 2, case 14: "show the player stuck once before solving it" was planned as a near-fail): a solve
# the request names with nothing about the clock is a clean win, unless the reference's own ending is a near-fail
SOLVE_WORDS = re.compile(
    r"\b(solv(e|es|ed|ing)|clear(s|ed|ing)?|beat(s|ing)?|finish(es|ed|ing)?|complet(e|es|ed|ing))\s+"
    r"(it|the (level|board|puzzle|round|stage))\b|\b(level|board|puzzle|round|stage) (is|gets) (solved|cleared|beaten|finished|"
    r"completed)\b|" + SOLVE_PHRASES, re.I)
# A moment for the result (round 3, case 19: "a satisfying moment to breathe" got a replay of an unfinished move and no
# held result): the result held BREATHE_HOLD_S longer and no replay of the play
BREATHE = re.compile(r"\b(a )?moments? to breathe\b|\bbreath(e|es|ing)\b|\bling(er|ers|ering)\b|\blet (it|the \w+) land\b|"
                     r"\bhold (on )?the (solved|empty|cleared|final) board\b", re.I)
BREATHE_HOLD_S = 1.5  # the result held this much longer (sequence.hold_s; brief.validate allows 0-9 s)
STOP_BEFORE = re.compile(r"\b(stops?|stopping|cuts?|cutting|ends?|ending|freez\w*|paus\w*)\b[^.;]{0,30}\bbefore\b", re.I)
CLOCK_WORDS = re.compile(r"\b(clock|timer|seconds?|time|barely|just in time|almost|nearly|close call|near[- ]fail\w*|"
                         r"last[- ]second|tense|nail-?biting)\b", re.I)


COLOUR_WORDS = re.compile(r"\b(" + "|".join(c for c in B.COLOUR_WORDS_ANY if c not in ("colour", "color")) + r"|dark green)\b", re.I)


def stuck_step(brief: dict, prompt: str, fixed: set) -> str | None:
    """The stuck moment, written so it points at one clear piece (round 2 rerun 3, case 14: "O1 (orange) heads for its
    gate, but O2 (orange) is in the way", with "I can't reach orange!" over two orange blocks): when the plan has a
    blocked move (a mistake, of the blocked kind or any) and the request names no colours and no stuck step of its own,
    a stuck step is added whose mover and blocker are two different colours of the board's palette. A colour an event
    points at is one block on the generated board (generate's singles), so the mover's colour is unique; the blocker's
    colour is asked of the generator (its named-blocker swap). Only with the board's colours known (a reference's board
    or the plan's); otherwise nothing, said. Returns the provenance line, or None."""
    from . import audit
    gp, lv = brief["gameplay"], brief["level"]
    planned = gp["mistakes"] if gp.get("mistakes") is not None else {"near_fail": 1, "time_out": 1}.get(gp["ending"], 0)
    if not planned or gp["ending"] == "cliffhanger":
        return None  # a cliffhanger's blocked attempt is its own last beat
    kinds = gp.get("mistake_kinds") or []
    if kinds and "blocked" not in kinds:
        return None
    events = list(gp.get("events") or [])
    if any(e.get("action") in ("stuck", "blocks") for e in events) or "colours" in fixed or \
            audit.asked(prompt).get("colour_names") or COLOUR_WORDS.search(re.sub(r"\bcolou?r[\s-]*block[\s-]*jam\b", " ", prompt or "", flags=re.I)):
        return None
    colours = [c for c in lv.get("colours") or [] if c in B.COLOURS]
    if len(colours) < 2:
        _note(brief, "the stuck moment's colours are left to the generator: the board's colours are not set, and naming "
                     "two would change its palette")
        return None
    taken = {e.get("block", {}).get("colour") for e in events}
    mover = next((c for c in colours if c not in taken), colours[0])
    blocker = next(c for c in colours if c != mover)
    events.append({"block": {"colour": mover, "which": "any", "all": False}, "action": "stuck", "when": "next", "by": blocker})
    gp["events"] = events
    _changed(brief, "gameplay.events")
    word = lambda c: B.COLOUR_WORDS.get(c, c.lower())  # noqa: E731
    return (f"the stuck moment points at one piece: the only {word(mover)} block heads for its gate and a {word(blocker)} "
            f"block is in the way (two colours, so \"I can't reach {word(mover)}!\" names a single block)")


PLANNER_CITES_REQUEST = re.compile(r"\b(because|since|as) you (asked|want|requested)\b|\byou asked for\b|\bthe request asks\b", re.I)
PLANNER_ENDING_WORDS = re.compile(r"\b(win|wins|cliff-?hanger|near[- ]?fail|time[- ]?out|ending|ends|solved?|cleared|unsolved)\b", re.I)
CLOSE_CALL = re.compile(r"\b(barely|just in time|close call|near[- ]fail\w*|last[- ]second|nail-?biting|seconds? (left|to spare))\b",
                        re.I)


def planner_ending(brief: dict) -> bool:
    """The planner set the ending from the request's words (round 4, case 30: "Because you asked for a replay of the
    winning move, this ad ends with a full win instead" was then replaced by the reference's cliffhanger): one of its
    assumptions cites the request and speaks of the ending. Then the reference's ending is read, not applied."""
    return any(PLANNER_CITES_REQUEST.search(str(x)) and PLANNER_ENDING_WORDS.search(str(x)) for x in brief.get("assumptions") or [])


def replay_ending(brief: dict, prompt: str, fixed: set) -> str | None:
    """A replay the request asks for ("a replay of the winning move", "replay the best move") is stated (sequence.replay
    True, pinned) and needs an ending that has one: ad.py plays no replay on a cliffhanger, so the ending is the request's
    (in `fixed`) and a cliffhanger becomes a win, a near-fail when the words speak of a close call (round 4, case 30: the
    reference's cut with 3 blocks left took the win the planner had set, and "Asked: the replay" failed). Returns the
    note, or None."""
    from . import audit
    if (audit.asked(prompt or "").get("sequence") or {}).get("replay") is not True:
        return None
    fixed |= {"replay", "ending"}
    gp, sq = brief["gameplay"], brief["sequence"]
    if sq.get("replay") is not True:
        sq["replay"] = True
        _changed(brief, "sequence")
    if gp["ending"] != "cliffhanger":
        return None
    gp["ending"] = "near_fail" if CLOSE_CALL.search(prompt or "") else "win"
    gp["blocks_left"] = None
    _changed(brief, "gameplay.ending")
    line = (f"the request asks for a replay, and a cliffhanger has none (ad.py plays no replay on a cut), so the level is "
            f"solved: a {ENDING_WORDS[gp['ending']]}")
    _note(brief, line)
    return line


def plain_solve(brief: dict, prompt: str, notes: dict) -> str | None:
    """The ending the request's solve words ask for: the request names a solve ("before solving it", "the final
    solution", "clears the whole board"), says nothing about the clock or a close call and does not stop before the
    solve. A near-fail the planner made of it becomes a win unless the reference's own ending is a near-fail (round 2,
    case 14); a cliffhanger or a time-out, from the plan or the reference, becomes a win: the request's words win (R3;
    round 3, case 19: "give the final solution a satisfying moment to breathe" ended on the reference's cliffhanger).
    Returns the note, or None."""
    from . import audit
    gp, words = brief["gameplay"], prompt or ""
    if not SOLVE_WORDS.search(words) or STOP_BEFORE.search(words) or CLOCK_WORDS.search(words) or \
            audit.asked(words).get("ending") not in (None, "win"):
        return None
    was = gp["ending"]
    if was == "near_fail" and mapped_ending(notes) != "near_fail":
        line = ("the request names a plain solve with nothing about the clock, so the ending is a win, not a near-fail "
                "(a near-fail needs the request's words or the reference's own ending)")
        said = "The level ends in a clean win: the request names a plain solve and nothing about the clock."
    elif was in ("cliffhanger", "time_out"):
        line = (f"the request names the solve, so the level is solved: a win, not the {ENDING_WORDS[was]} "
                f"{'the reference ends on' if mapped_ending(notes) == was else 'the plan had'} (the request's words win)")
        said = "The level is solved and ends in a clean win: the request names the solve."
        if was == "cliffhanger" and gp.get("blocks_left") is not None:
            gp["blocks_left"] = None  # a cut's blocks left: nothing is left on a solved board
    else:
        return None
    gp["ending"] = "win"
    if "gameplay.ending" not in brief["changed"]:
        brief["changed"].append("gameplay.ending")
    _note(brief, line)
    row = B.control(brief, "gameplay")
    row["plan"] = f"{row['plan']} {said}".strip() if row.get("plan") else said
    return line


def breathe(brief: dict, prompt: str) -> str | None:
    """A moment for the result the request asks for ("a satisfying moment to breathe", "let it land", "hold the solved
    board"; round 3, case 19): the result held BREATHE_HOLD_S longer (sequence.hold_s, never lowered) and no replay of
    the play, unless the request asks for a replay itself. Returns the note, or None."""
    from . import audit
    if not BREATHE.search(prompt or ""):
        return None
    sq, did = brief["sequence"], []
    if float(sq.get("hold_s") or 0) < BREATHE_HOLD_S:
        sq["hold_s"] = BREATHE_HOLD_S
        did.append(f"the {'question' if brief['gameplay']['ending'] == 'cliffhanger' else 'result'} held {BREATHE_HOLD_S:g} s longer")
        if "sequence.timing" not in brief["changed"]:
            brief["changed"].append("sequence.timing")
    if sq.get("replay") and (audit.asked(prompt).get("sequence") or {}).get("replay") is not True:
        sq["replay"] = False
        did.append("no replay of the play")
        if "sequence" not in brief["changed"]:
            brief["changed"].append("sequence")
    if not did:
        return None
    line = "the request asks for a moment to breathe: " + " and ".join(did)
    _note(brief, line)
    row = B.control(brief, "sequence")
    said = line[0].upper() + line[1:] + "."
    if said not in (row.get("plan") or ""):
        row["plan"] = f"{row['plan']} {said}".strip() if row.get("plan") else said
    if row.get("status") in ("default", "not_supported"):
        row["status"] = "applied"
    return line


# the request speaks of the wrong moves ("show the player stuck once", round 2 case 14): its count is its own
MISTAKES_STATED = re.compile(r"\bstuck\b|\bwrong (moves?|drags?|blocks?)\b|\bmistakes?\b|\bblocked (moves?|attempts?)\b", re.I)

REPLAY_ROOM_S = 40.0  # under this asked length, a replay is not taken from the reference


def _asked_length(prompt: str, constraints=()) -> float | None:
    """The length the request (or the reading plan's constraints) states itself, in seconds, or None."""
    from . import audit
    return audit.asked((prompt or "") + ". " + ". ".join(own_constraints(constraints)), case_range=True).get("length_s")


def _caption_stated(brief: dict, prompt: str, field: str) -> bool:
    """A concept text the request wrote itself (a quoted caption the planner put in that field)."""
    from . import audit
    value = (brief["concept"].get(field) or "").lower()
    return bool(value) and any(q.strip().lower() in value for q in audit.asked(prompt)["captions"] if q.strip())


# ---------- reading the analysis ----------

def _segs(notes: dict) -> list[dict]:
    """The reading's parts, a hook over most of the clip read as play (reference.long_hooks: a reading stored before
    that rule, round 3 case 18)."""
    from .reference import long_hooks
    return long_hooks([s for s in notes.get("structure") or [] if isinstance(s, dict)])


def _len(s: dict) -> float:
    return max(0.0, float(s.get("to_s") or 0) - float(s.get("from_s") or 0))


WIN_SCREEN = re.compile(r"level\s+complete\w*|level\s+cleared|level\s+passed|\bcleared\b|you\s+win|win\s+screen|victory\s+screen", re.I)
OUT_OF_TIME_SCREEN = re.compile(r"out\s+of\s+time|time'?s\s+up|level\s+failed|game\s+over|fail\s+screen", re.I)


def screens_seen(notes: dict) -> tuple[bool, bool]:
    """(a win screen, an out-of-time screen) transcribed anywhere in the reading: the captions, the game's own text, the
    parts' captions and descriptions, and the ending's second read."""
    texts = [str(x) for x in (notes.get("captions_seen") or []) + (notes.get("screen_text") or [])]
    texts += [f"{s.get('what', '')} {' '.join(str(c) for c in s.get('captions') or [])}" for s in _segs(notes)]
    er = notes.get("ending_read") if isinstance(notes.get("ending_read"), dict) else {}
    win = er.get("win_screen") is True or any(WIN_SCREEN.search(x) for x in texts)
    oot = er.get("out_of_time_screen") is True or any(OUT_OF_TIME_SCREEN.search(x) for x in texts)
    return win, oot


def _ending_word(x) -> str:
    """The ending's word without what a model copied from the schema ("time-out (the out-of-time screen)" -> "time-out")."""
    return str(x or "").split("(")[0].strip().lower()


def _clock_s(x) -> int | None:
    m = re.search(r"(\d{1,2}):(\d{2})", str(x or ""))
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def mapped_ending(notes: dict) -> str | None:
    """The reference's ending as the game's (section 3). The ending read again on the clip's last seconds
    (notes.ending_read, reference.read_ending) wins over the whole clip's, checked against what that read transcribed:
    a near-fail whose last clock reading is over 5 s is a win, and a cliffhanger with a win screen transcribed falls
    back to the whole clip's ending. A question (a question part, or a question
    caption in the last seconds) makes it a cliffhanger unless a win screen or an out-of-time screen was transcribed
    (2026-10-16: a cliffhanger was read as a near-fail with its question part found). Otherwise a victory is a near-fail
    when the reference has a near-fail part, else a clean win; a fail is a time-out. None: unread."""
    purposes = {s.get("purpose") for s in _segs(notes)}
    er = notes.get("ending_read") if isinstance(notes.get("ending_read"), dict) else {}
    last = er.get("ending") if er.get("ending") in ("win", "near_fail", "time_out", "cliffhanger") else None
    clock = _clock_s(er.get("last_clock"))
    if last == "near_fail" and clock is not None and clock > 5:
        last = "win"  # its own clock says the win came with more than 5 s left (v7: 3-clean, "near-fail" at 00:08)
    if last == "cliffhanger" and screens_seen({k: v for k, v in notes.items() if k != "ending_read"})[0] | (er.get("win_screen") is True):
        last = None  # a win screen was transcribed: the end card's question is a win's (v7: 2-clean, "Can you do it faster?")
    whole = notes.get("ending_whole") if er.get("ending") and notes.get("ending_whole") is not None else notes.get("ending")
    e = last or ENDING_OF.get(_ending_word(whole))
    question = "question" in purposes or "?" in str(er.get("question_caption") or "")
    if question and not any(screens_seen(notes)):
        return "cliffhanger"
    if e is None:
        if "fail" in purposes:
            return "time_out"
        if "victory" not in purposes:
            return None
        e = "victory"
    if e == "victory":
        return "near_fail" if "near_fail" in purposes else "win"
    return e


def mistakes_of(notes: dict) -> int | None:
    """Mistakes shown: the larger of the wrong moves the model listed and its mistake parts (at most 3);
    when both are empty, the model's own yes/no (mistakes_shown: 1 or 0); None unread. (2026-10-16: the
    list alone missed the wrong moves of two cliffhangers the parts and the yes/no had.)"""
    listed = notes.get("mistakes") if isinstance(notes.get("mistakes"), list) else None
    n = min(3, max(len(listed or []), sum(1 for s in _segs(notes) if s.get("purpose") == "mistake")))
    if n:
        return n
    shown = notes.get("mistakes_shown")
    if shown is True:
        return 1
    return 0 if shown is False or listed is not None else None


MISTAKE_PARTS_MAX = 1  # the most wrong moves a concept read or a filled ending takes from the reference


def mistake_parts(notes: dict) -> int | None:
    """Mistakes from the reading's mistake parts alone (timestamped, so seen), at most MISTAKE_PARTS_MAX; never the free
    list or the yes/no (round 3, case 16). None when no parts were read."""
    segs = _segs(notes)
    if not segs:
        return None
    return min(MISTAKE_PARTS_MAX, sum(1 for s in segs if s.get("purpose") == "mistake"))


def caption_function(text: str, purpose: str | None = None) -> str | None:
    """What a caption does: challenge, wrong (the wrong move's line), instruction (the correction), urgency, result or
    cta (from its words, in CAPTION_RX's order, else from the part it is on), or None. A caption on a question part (a
    cliffhanger's cut) is its result line."""
    if purpose == "question" and not CTA_RX.search(text or ""):
        return "result"
    for fn, rx in CAPTION_RX:
        if rx.search(text or ""):
            return fn
    return PURPOSE_FUNCTION.get(purpose or "")


def _part_of(text: str, segs: list[dict]) -> str | None:
    """The purpose of the part a caption is on (for its function when its words do not say it)."""
    t = text.strip().lower()
    return next((s.get("purpose") for s in segs if any(t and t == str(c).strip().lower() for c in s.get("captions") or [])), None)


def caption_functions(notes: dict) -> dict[str, str]:
    """The caption functions the reference has, in order: {function: its first caption}, from
    captions_seen only (the ad's own captions, word for word; the game's HUD text is screen_text)."""
    out: dict[str, str] = {}
    segs = _segs(notes)
    pairs = [(c, _part_of(c, segs)) for c in notes.get("captions_seen") or [] if isinstance(c, str) and c.strip()]
    for text, purpose in pairs:
        fn = caption_function(str(text), purpose)
        if fn and fn not in out:
            out[fn] = str(text)
    return out


def hook_function(notes: dict) -> str | None:
    """The hook's function: what the model said it does, else its words (a "?" asks a question; "can
    you" with it is a challenge; "bet", "only", "can't" dare the viewer)."""
    said = str(notes.get("hook") or "").lower()
    for word, fn in (("dare", "dare"), ("challenge", "challenge"), ("question", "question")):
        if re.search(rf"\b{word}", said):
            return fn
    texts = [said] + [str(c).lower() for s in _segs(notes) if s.get("purpose") == "hook" for c in s.get("captions") or []]
    for t in texts:
        if re.search(r"\b(bet|only \d|can'?t|dare)\b", t):
            return "dare"
        if "?" in t:
            return "challenge" if re.search(r"\b(can you|could you|are you|think you)\b", t) else "question"
        if re.search(r"\b(try|beat|solve|clear)\b", t):
            return "challenge"
    return None


GAMEPLAY_HOOK = re.compile(r"\b(board|blocks?|hand|cursor|finger|pointer|gameplay|puzzle|drags?|pieces?|grid|level|moves?)\b", re.I)
TEXT_HOOK = re.compile(r"\b(text|caption|title|headline|says|reads|written|words?|banner)\b|[\"\u201c]", re.I)


def hook_kind(notes: dict) -> str | None:
    """The hook's kind (round 2 rerun, case 14: "the video starts directly with a puzzle board and a hand cursor pointing
    at a block" was taken as its timing alone, and the ad opened on a "Can you clear it?" headline): "caption" (a
    question, a challenge or a dare in words, or captions in the hook part), "gameplay" (the play from the first frame,
    no caption: no caption seen at all, or none in the hook part and a description of the board and the play), or None."""
    segs = _segs(notes)
    hook_caps = [c for s in segs if s.get("purpose") == "hook" for c in s.get("captions") or [] if str(c).strip()]
    if hook_function(notes) or hook_caps:
        return "caption"
    said = str(notes.get("hook") or "")
    seen = [c for c in notes.get("captions_seen") or [] if str(c).strip()]
    if GAMEPLAY_HOOK.search(said) and not TEXT_HOOK.search(said) and (not seen or not any(s.get("purpose") == "hook" for s in segs)):
        return "gameplay"
    return None


def hook_line(fn: str, ending: str) -> str:
    """The tool's own words for a hook of that function (dares, never odds: ad.copy_problems)."""
    if fn == "dare":
        return "Bet you can't clear this!"
    if fn == "question":
        return "Can you see the move?"
    return "Can you clear it in time?" if ending in ("near_fail", "time_out") else "Can you clear it?"


def fast_finish(notes: dict) -> bool:
    """Whether the reference ends its play fast (a payoff part, a rush, a cascade): the game's streak finish."""
    if any(s.get("purpose") == "payoff" for s in _segs(notes)):
        return True
    segs = [s for s in _segs(notes) if s.get("purpose") in ("gameplay", "near_fail", "victory")]
    words = [f"{s.get('what', '')} {s.get('emphasis', '')}" for s in segs[-2:]]
    ad = notes.get("adaptation") if isinstance(notes.get("adaptation"), dict) else {}
    words += [str(x) for x in (ad.get("transferable") or []) + (ad.get("translation") or [])]
    return any(FAST_FINISH.search(w) for w in words)


def _keyword(x: str) -> str | None:
    m = FOREIGN.search(x)
    return m.group(0).lower().rstrip("s") if m else None


def _wall_like(x: str) -> bool:
    """Whether a named obstacle is the game's own wall cell (grey, dark, fixed, a barrier) rather than another game's thing."""
    return bool(WALL_LIKE.search(x)) and not FOREIGN.search(x)


def mechanic_items(notes: dict) -> list[str]:
    """What the reference shows that may be a mechanic: mechanics_seen, then the board's obstacles (2026-10-17). A
    mechanics_seen entry about the same foreign thing as the board's obstacles ("bubble obstacles with counters" beside
    "a bubble with the counter 3") gives way to them: they are more exact."""
    seen = [str(m).strip().rstrip(".")[:80] for m in notes.get("mechanics_seen") or [] if str(m).strip()]
    bd = notes.get("board") if isinstance(notes.get("board"), dict) else {}
    obstacles = [str(o).strip().rstrip(".")[:80] for o in (bd.get("obstacles") if isinstance(bd.get("obstacles"), list) else [])
                 if str(o).strip()]
    extras = [str(x).strip().rstrip(".")[:80] for x in notes.get("extras_seen") or [] if str(x).strip()]
    keys = {_keyword(o) for o in obstacles} - {None}
    seen = [m for m in seen if _keyword(m) is None or _keyword(m) not in keys]
    keys |= {_keyword(m) for m in seen} - {None}
    kept = []
    for x in extras:  # what the game does not have, once per thing (the whole clip and the still name the same buttons)
        k = _keyword(x)
        if k is None or k not in keys:
            kept.append(x)
            keys |= {k} - {None}
    return list(dict.fromkeys(seen + obstacles + kept))


def mechanic_lines(notes: dict, brief: dict | None = None) -> tuple[list[str], list[str]]:
    """One assumption line per mechanic the model saw (and per obstacle on its board), and what is therefore not copied.
    A mechanic the game has is named as the game's own; any other is "not used: not in Color Block Jam" and goes to
    not_copied (never created, drawn or simulated, 2026-10-17); a MECHANICS row adds which of the game's own parameters
    the ad keeps, only when the brief has it."""
    lines, not_copied = [], []
    for m in mechanic_items(notes):
        its = "its " + re.sub(r"^(a|an|the)\s+", "", m, flags=re.I)
        row = next(((rx, has, keeps) for rx, has, keeps in MECHANICS if rx.search(m)), None)
        if row is not None:
            lines.append(f"{m}: {NOT_USED}" + (f"; {row[2]}" if brief is not None and row[1](brief) else ""))
            not_copied.append(its)
            continue
        if NOT_SHOWN.search(m) and not FOREIGN.search(m):
            lines.append(f"{m}: not used: an ad shows one level")
            continue
        native = None if FOREIGN.search(m) else next((tpl for rx, tpl in NATIVE if rx.search(m)), None)
        if native is None and _wall_like(m):
            native = "{m}: the game's own walls (the board's shape)"
        if native:
            lines.append(native.format(m=m))
        else:
            lines.append(f"{m}: {NOT_USED}")
            not_copied.append(its)
    return lines, not_copied


# ---------- the board (2026-10-17) ----------

# A block colour as read, to the game's seven. Each name has a game-like shade; the game's own seven are their own
# (brief.GAME_HEX: the game's Purple is a magenta, its Blue a bright blue). Distinct reference colours stay distinct
# (2026-10-17, the owner's trailers: purple and magenta both read as purple lost a colour): board_colours assigns the
# read colours to distinct game colours at the least total distance, so each takes its nearest free one.
COLOUR_RGB = {
    "red": (255, 59, 42), "crimson": (220, 20, 60), "scarlet": (255, 36, 0), "maroon": (128, 0, 0), "cherry": (210, 30, 60),
    "ruby": (200, 20, 60), "pink": (240, 60, 220), "hot pink": (255, 50, 190), "light pink": (255, 150, 220),
    "magenta": (255, 0, 255), "fuchsia": (255, 0, 255), "purple": (208, 7, 253), "violet": (140, 70, 230),
    "lilac": (200, 160, 230), "lavender": (180, 150, 240), "mauve": (200, 120, 200), "plum": (142, 69, 133),
    "indigo": (75, 0, 130), "blue": (20, 105, 255), "light blue": (100, 180, 255), "sky blue": (90, 190, 250),
    "navy": (20, 30, 120), "dark blue": (20, 40, 160), "cobalt": (0, 71, 171), "azure": (0, 127, 255),
    "cyan": (0, 220, 240), "teal": (0, 180, 180), "turquoise": (64, 224, 208), "aqua": (0, 230, 230),
    "green": (20, 255, 23), "light green": (120, 240, 120), "bright green": (20, 255, 23), "lime": (150, 255, 0),
    "mint": (100, 240, 180), "emerald": (0, 190, 100), "dark green": (6, 92, 19), "forest green": (34, 139, 34),
    "forest": (34, 139, 34), "olive": (128, 128, 0), "bottle green": (0, 106, 78), "yellow": (255, 204, 4),
    "gold": (255, 200, 0), "golden": (255, 200, 0), "lemon": (255, 245, 80), "amber": (255, 190, 0),
    "mustard": (225, 173, 1), "orange": (255, 128, 0), "tangerine": (255, 150, 40), "peach": (255, 180, 130),
    "apricot": (251, 206, 177), "coral": (255, 127, 80),
}
_COLOUR_KEYS = sorted(COLOUR_RGB, key=len, reverse=True)


def _hex(h: str) -> tuple[int, int, int]:
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def colour_name(name) -> str:
    """A colour as named, plain: "Pink/Magenta" -> "pink", "light-blue" -> "light blue"."""
    s = str(name or "").strip().lower().split("/")[0].split(" or ")[0]
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", " ", s)).strip()


def colour_rgb(name) -> tuple[int, int, int] | None:
    """The shade a colour name stands for: the name itself, else the longest known name in it ("lime green" -> lime),
    else None (white, black, grey, brown: not a block colour)."""
    s = colour_name(name)
    if s in COLOUR_RGB:
        return COLOUR_RGB[s]
    return next((COLOUR_RGB[k] for k in _COLOUR_KEYS if re.search(rf"\b{k}\b", s)), None)


def _distance(a, b) -> float:
    """The "redmean" colour distance (a cheap perceptual weighting of RGB)."""
    r = (a[0] + b[0]) / 2
    dr, dg, db = a[0] - b[0], a[1] - b[1], a[2] - b[2]
    return ((2 + r / 256) * dr * dr + 4 * dg * dg + (2 + (255 - r) / 256) * db * db) ** 0.5


def _slots_by_distance(rgb) -> list[str]:
    from .brief import COLOURS, GAME_HEX
    return sorted(COLOURS, key=lambda s: _distance(rgb, _hex(GAME_HEX[s])))


def board_colour(name) -> str | None:
    """A block colour as the model named it ("light blue", "pink/magenta") -> its nearest game colour, or None."""
    rgb = colour_rgb(name)
    return _slots_by_distance(rgb)[0] if rgb else None


COUNT_MERGE_MAX = 250.0  # a surplus name this close to a counted colour is that colour (cyan/blue 233, magenta/purple 52)


def board_colours(read, count: int | None = None, counted=None) -> dict:
    """The read colours to distinct game colours: {slots (in order of appearance), map [{read, slot, note}], unmapped,
    dropped}. Each distinct name (as named) gets its own game colour, at the least total distance over all of them
    (so a name takes its nearest colour unless a closer name needs it: purple and magenta give purple and red); more
    than seven names, or more than `count` (the distinct colours counted on the board's crop): the two closest names
    are taken as one colour until that many are left (refs-v1: a reader split seven colours into nine names). A note says why a name became a colour it is not ("magenta -> red: the game has
    no magenta, purple is taken by purple")."""
    import itertools
    from .brief import COLOURS, COLOUR_WORDS, GAME_HEX
    names, unmapped = [], []
    for c in read or []:
        n = colour_name(c)
        if not n or n in names or n in unmapped:
            continue
        (names if colour_rgb(n) else unmapped).append(n)
    dropped = []
    words = set(COLOUR_WORDS.values())

    def merge_cost(i, j):  # two of the game's own colour words are never one colour; names nearest one game colour first
        a, b = names[i], names[j]
        d = _distance(colour_rgb(a), colour_rgb(b))
        same = _slots_by_distance(colour_rgb(a))[0] == _slots_by_distance(colour_rgb(b))[0]
        return d * (0.5 if same else 1.0) + (10_000 if a in words and b in words else 0)
    counted = [colour_name(c) for c in counted or [] if colour_rgb(c)]
    if count and counted:
        # the colours counted on the board's crop, with their names (round 1: LolTap's six read as eight names): a name the
        # count does not have, close to one it has, is that colour; a name far from all of them is one the count missed
        # (refs-v4: trailer 2's teal), so it stays
        while len(names) > count:
            cands = [(min(_distance(colour_rgb(n), colour_rgb(c)) for c in counted), i) for i, n in enumerate(names)
                     if n not in counted]
            cands = [x for x in cands if x[0] <= COUNT_MERGE_MAX]
            if not cands:
                break
            _, i = min(cands)
            near = min(counted, key=lambda c: _distance(colour_rgb(names[i]), colour_rgb(c)))
            dropped.append(f"{names[i]} (as {near})")
            names.pop(i)
            if near not in names:
                names.insert(i, near)
        keep = 7
    else:
        keep = min(7, count) if count else 7  # a count without names: the closest names merge down to it
    while len(names) > keep:  # more names than colours: the two closest are one colour (the later name goes)
        i, j = min(((i, j) for i in range(len(names)) for j in range(i + 1, len(names))), key=lambda ij: merge_cost(*ij))
        dropped.append(f"{names[j]} (as {names[i]})")
        names.pop(j)
    rgbs = [colour_rgb(n) for n in names]
    cost = {(i, s): _distance(rgbs[i], _hex(GAME_HEX[s])) for i in range(len(names)) for s in COLOURS}
    best = min(itertools.permutations(COLOURS, len(names)), key=lambda perm: sum(cost[i, s] for i, s in enumerate(perm))) if names else ()
    owner = {s: names[i] for i, s in enumerate(best)}
    out = []
    for i, (n, s) in enumerate(zip(names, best)):
        natural = _slots_by_distance(rgbs[i])[0]
        why = ([] if n in words else [f"the game has no {n}"]) + \
              ([f"{COLOUR_WORDS[natural]} is taken by {owner[natural]}"] if natural != s and natural in owner else [])
        out.append({"read": n, "slot": s, "note": f"{n} -> {COLOUR_WORDS[s]}: {', '.join(why)}" if why else None})
    return {"slots": list(best), "map": out, "unmapped": unmapped, "dropped": dropped}


BOARD_W, BOARD_H = (4, 9), (4, 10)  # what the brief accepts (brief.validate)
# The smallest board each shape is built on: generate_for_brief's own fixes (a narrow centre needs 6 rows, lanes 7x6, a
# ring 6x6), and room around the cut for a cross and a door.
SHAPE_MIN = {"narrow_center": (4, 6), "lanes": (7, 6), "ring": (6, 6), "cross": (5, 5), "door": (5, 4)}
BLOCKS_RANGE = (2, 10)  # brief.validate; the generator's MAX_BLOCKS is 12
# How busy the board looks is recorded and shown, never applied (2026-10-17, R10): against the level's difficulty it read
# 1-2 of 12 (READING-ACCURACY-v9.md, v9b), so the difficulty is left to the request, the ending rule and the generator.
BUSY = ("simple", "medium", "busy")
SHAPE_ALIASES = {"narrow_centre": "narrow_center", "hourglass": "narrow_center", "two_rooms": "door", "plus": "cross",
                 "walled": "holes", "rectangle": "open", "square": "open"}


def _int(x) -> int | None:
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return int(round(x))
    m = re.search(r"\d{1,3}", str(x or ""))
    return int(m.group(0)) if m else None


def board_of(notes: dict) -> dict | None:
    """The board the reading gives, in the game's terms: {columns, rows, shape, blocks, colours (the game's slots,
    de-duplicated, in order of appearance), colours_read, colours_unmapped, pieces, gates_sides, obstacles, busy}, or
    None when no board was read. Another game's obstacles are only listed: they never add a block, a wall or a shape;
    the game's own wall cells named among them (`WALL_LIKE`) are walls, and make an "open" board a holes board."""
    bd = notes.get("board") if isinstance(notes, dict) else None
    if not isinstance(bd, dict):
        return None
    from . import brief as B
    from .reference import BOARD_SHAPES
    read = [str(c).strip() for c in (bd.get("colours") if isinstance(bd.get("colours"), list) else []) if str(c).strip()]
    count = _int(bd.get("colour_count"))
    cm = board_colours(read, count if count and count >= 1 else None, bd.get("colours_counted"))
    shape = str(bd.get("shape") or "").strip().lower().replace("-", "_").replace(" ", "_").split("(")[0].strip("_")
    pieces = str(bd.get("pieces") or "").strip().lower().split(" ")[0].strip("(,;")
    busy = str(bd.get("busy") or "").strip().lower().split(" ")[0].strip("(,;")
    gates = _int(bd.get("gates_sides"))
    obstacles = [str(o).strip()[:80] for o in (bd.get("obstacles") if isinstance(bd.get("obstacles"), list) else []) if str(o).strip()]
    walls = [o for o in obstacles if _wall_like(o)]
    shape = SHAPE_ALIASES.get(shape, shape)
    shape = shape if shape in BOARD_SHAPES else None
    walled = shape == "open" and bool(walls)  # an "open" board with wall cells named inside it has the game's walls
    out = {"columns": _int(bd.get("columns")), "rows": _int(bd.get("rows")),
           "shape": "holes" if walled else shape, "shape_read": bd.get("shape"), "walls_named": walls,
           "blocks": _int(bd.get("blocks")), "colours": cm["slots"], "colours_read": read, "colour_map": cm["map"],
           "colours_unmapped": cm["unmapped"] + cm["dropped"],
           "pieces": pieces if pieces in B.PIECES else None, "gates_sides": gates if gates is not None and 0 <= gates <= 4 else None,
           "obstacles": [o for o in obstacles if o not in walls],
           "busy": busy if busy in BUSY else None,
           "symmetric": bd.get("symmetric") if isinstance(bd.get("symmetric"), bool) else None,
           "wall_cells": _int(bd.get("wall_cells")), "colour_count": count,
           "occupancy": bd.get("occupancy") if isinstance(bd.get("occupancy"), (int, float)) else None}
    if not any(out[k] for k in ("columns", "rows", "shape", "blocks", "colours", "pieces")):
        return None
    return out


def board_size(shape: str | None, columns: int | None, rows: int | None) -> tuple[int | None, int | None]:
    """The board's columns and rows clamped to what the generator builds for that shape."""
    lo_w, lo_h = SHAPE_MIN.get(shape or "open", (BOARD_W[0], BOARD_H[0]))
    w = None if columns is None else min(BOARD_W[1], max(lo_w, columns))
    h = None if rows is None else min(BOARD_H[1], max(lo_h, rows))
    return w, h


def walls_of(shape: str, w: int, h: int) -> int:
    """The inner wall cells the generator builds for a shape and size (generate.holes_for)."""
    from .generate import holes_for
    return len(holes_for(shape, w, h)) if shape != "open" else 0


WALL_SLACK = 1  # wall cells off that count as the reading's error, not a different board (wall_choice)


def wall_choice(wall_cells: int, w: int, h: int, want: int | None, pieces: str | None,
                grow: bool = True) -> tuple[str, int, tuple[int, int, int | None]]:
    """For a board read as open or holes with `wall_cells` inner wall cells: the closest board the generator builds,
    open (no walls) or holes (its fewest walls are 3, on an odd width under 8 rows), at the size read or a cell more
    each way when the size is the reference's. A wall cell off is within the reading's error (round 2 rerun 3, case 05:
    trailer 2's one 2-cell wall read as 4 kept the 4x7 holes board, 4 walls, and cut 9 blocks to 6, where 5x8, 5
    walls, keeps them): walls off beyond one cell first, then the fewest blocks short of `want` (grow before cut, both
    sides), then the fewest walls off, then the smallest board, open before holes. Returns (shape, walls, (width,
    height, blocks that fit))."""
    best = None
    for shape in ("open", "holes"):
        for dw, dh in ((0, 0), (1, 0), (0, 1), (1, 1)) if grow else ((0, 0),):
            gw, gh = board_size(shape, w + dw, h + dh)
            if gw is None or gh is None or (dw or dh) and (gw, gh) != (w + dw, h + dh):
                continue  # a grown size the generator does not build for this shape
            walls = walls_of(shape, gw, gh)
            fits = board_blocks(want, shape, gw, gh, pieces) if want else None
            off = abs(walls - wall_cells)
            key = (max(0, off - WALL_SLACK), max(0, (want or 0) - (fits or 0)), off, gw * gh, shape != "open")
            if best is None or key < best[0]:
                best = (key, shape, walls, (gw, gh, fits))
    return best[1], best[2], best[3]


FULL_FILL = 0.6  # this share of the board's cells under blocks (measured on the crop, else estimated): a packed board


def board_full(bd: dict, lv: dict) -> str | None:
    """Why the reference's board is full (packed), or None: FULL_FILL or more of its cells under blocks, as the code
    measured on the crop (the grid's block cells). Only the measure decides: "busy" scored 2 of 12 and an estimate from
    the blocks read is no measure (R10, 2026-10-17)."""
    occ = bd.get("occupancy")
    return f"{occ:.0%} of its cells under blocks, measured" if isinstance(occ, (int, float)) and occ >= FULL_FILL else None


def keep_fill(n: int, fill: float, shape: str | None, w: int, h: int, pieces: str | None) -> tuple[int, int] | None:
    """The board, no bigger than w x h and as the generator builds the shape, on which n blocks keep `fill` blocks per
    cell, near the read's proportions, and that still holds n (board_blocks)."""
    import math
    target = n / fill if fill else w * h
    best = None
    lo_w, lo_h = SHAPE_MIN.get(shape or "open", (BOARD_W[0], BOARD_H[0]))
    for cw in range(max(lo_w, BOARD_W[0]), w + 1):
        for ch in range(max(lo_h, BOARD_H[0]), h + 1):
            if board_blocks(n, shape, cw, ch, pieces) < n:
                continue
            score = abs(cw * ch - target) / target + abs(math.log((cw / ch) / (w / h)))
            if best is None or (score, -cw * ch) < best[0]:
                best = ((score, -cw * ch), (cw, ch))
    return best[1] if best else None


def grow_for_blocks(want: int, shape: str | None, w: int, h: int, pieces: str | None) -> tuple[int, int, int] | None:
    """The smallest board, at most a cell more each way and within what the generator builds for the shape, on which
    `want` blocks fit (board_blocks); else the one that holds the most. (width, height, blocks) or None."""
    options = []
    for dw, dh in ((0, 0), (1, 0), (0, 1), (1, 1)):
        gw, gh = board_size(shape, w + dw, h + dh)
        if gw is None or gh is None:
            continue
        options.append((gw, gh, board_blocks(want, shape, gw, gh, pieces)))
    if not options:
        return None
    fits = [o for o in options if o[2] >= want]
    return min(fits, key=lambda o: (o[0] * o[1], o[1])) if fits else max(options, key=lambda o: (o[2], -o[0] * o[1]))


def board_blocks(n: int | None, shape: str | None, w: int | None, h: int | None, pieces: str | None) -> int | None:
    """The block count clamped to the brief's range and to what the board's free cells hold at the generator's packed
    fill with those pieces (generate.PACKED_FILL, AVG_CELLS)."""
    if n is None:
        return None
    from .generate import AVG_CELLS, PACKED_FILL, holes_for
    hi = BLOCKS_RANGE[1]
    if w and h:
        free = w * h - len(holes_for(shape or "open", w, h))
        hi = min(hi, max(BLOCKS_RANGE[0], int(free * PACKED_FILL[1] / AVG_CELLS.get(pieces or "mixed", 2.3))))
    return min(hi, max(BLOCKS_RANGE[0], n))


def _shape_words(shape: str | None) -> str:
    from .generate import SHAPE_WORDS
    return SHAPE_WORDS.get(shape or "", "")


def board_text(bd: dict) -> str:
    """The board in words: "an open 6x6 board, 11 blocks in 6 colours (green, blue, ...), mixed pieces, gates on 4 sides,
    simple; obstacles (not used): ...". """
    words = _shape_words(bd.get("shape"))
    size = f"{bd['columns']}x{bd['rows']} " if bd.get("columns") and bd.get("rows") else ""
    head = f"{'an' if words[:1] in 'aeiou' and words else 'a'} {words + ' ' if words else ''}{size}board".replace("  ", " ")
    bits = [head]
    if bd.get("blocks") is not None:
        cols = [c.lower().replace("darkgreen", "dark green") for c in bd.get("colours") or []]
        bits.append(f"{bd['blocks']} blocks" + (f" in {len(cols)} colours ({', '.join(cols)})" if cols else ""))
    if bd.get("pieces"):
        bits.append(f"{bd['pieces']} pieces")
    if bd.get("gates_sides") is not None:
        bits.append(f"gates on {bd['gates_sides']} side{'s' if bd['gates_sides'] != 1 else ''}")
    if bd.get("busy"):
        bits.append(f"looks {bd['busy']}")
    if bd.get("symmetric"):
        bits.append("mirror-symmetric")
    text = ", ".join(bits)
    notes_ = [m["note"] for m in bd.get("colour_map") or [] if m.get("note")]
    if notes_:
        text += "; colours: " + "; ".join(notes_)
    if bd.get("colours_unmapped"):
        text += f"; colours not used (not a block colour of the game, or past its seven): {', '.join(bd['colours_unmapped'])}"
    if bd.get("walls_named"):
        text += f"; wall cells (the game's own): {'; '.join(bd['walls_named'])}" + (
            " (so the shape is holes, not open)" if str(bd.get("shape_read") or "").lower().startswith("open") else "")
    if bd.get("obstacles"):
        text += f"; obstacles ({NOT_USED}): {'; '.join(bd['obstacles'])}"
    return text


# ---------- writing into the brief ----------

def _changed(brief: dict, group: str) -> None:
    if group not in brief["changed"]:
        brief["changed"].append(group)
    ref = brief.get("reference")
    if isinstance(ref, dict) and isinstance(ref.get("set"), list) and group not in ref["set"]:
        ref["set"].append(group)  # what the reference set (a revision keeps it: workflows/guided.revise_once)


def _row(brief: dict, control: str, text: str, prompt: str, file: str, replace: bool = False) -> None:
    """The plan row of a control says what the reference set, in words; replace: the code's line stands alone (a copied
    board, 2026-10-19: the planner's "a new board built like the trailer's" contradicted it)."""
    row = B.control(brief, control)
    row["asked"] = row["asked"] or prompt.strip()
    line = f"From the reference video {file}: {text}."
    if replace:
        row["plan"] = line
    elif line not in (row["plan"] or ""):
        row["plan"] = f"{row['plan']} {line}".strip() if row["plan"] else line
    if row["status"] in ("default", "not_supported"):
        row["status"] = "applied"


# The words a planner's text uses for a field's value (rerun 5, case 14: the gameplay plan said "solve the level with a
# second left on the clock" and an assumption argued for a near-fail after plain_solve made the ending a win).
OLD_VALUE_WORDS = {
    ("gameplay", "ending"): {"near_fail": r"near[- ]?fail|seconds? left|a second to spare|just in time|on the clock",
                             "win": r"\bclean win\b|with time to spare", "cliffhanger": r"cliff-?hanger|stops? before|unsolved",
                             "time_out": r"time[- ]?out|runs? out of time|out of time"},
    ("pacing", "tempo"): {"calm": r"\bcalm\b|relax", "fast": r"\bfast (tempo|pace)\b|\bquick pace\b|rapid"},
    ("pacing", "curve"): {"speeds_up": r"speeds? up|gets faster|faster toward", "slows_down": r"slows? down|gets slower|slower toward"},
    ("visuals", "hud_level"): {True: r"\bhud (is |stays )?(shown|visible|on)|level (badge|number|label) (is |stays )?"
                                     r"(shown|visible)|shows? the (level|hud)"},
    ("visuals", "hud_timer"): {True: r"clock (is |now )?(shown|visible|on screen)|shows? the clock",
                               False: r"no clock|clock (is |stays )?hidden|without (a|the) clock"},
    ("gameplay", "hesitations"): {0: r"no hesitation"},
}


def correct_texts(before: dict, brief: dict) -> list[str]:
    """A field a rule changed after the planner (plain_solve, the play levers, the screen, a revision's guard) takes the
    planner's words for its old value with it: the sentences of that control's plan text that name the old value go
    (the reference's own "From the reference video" lines stay), and so do the planner's assumptions that argued for
    it. Returns the controls rewritten."""
    out = []
    for (sec, key), words in OLD_VALUE_WORDS.items():
        old, new = (before.get(sec) or {}).get(key), (brief.get(sec) or {}).get(key)
        if old == new or old not in words:
            continue
        rx = re.compile(words[old], re.I)
        ctl = next((c for g, (c, paths) in B.GROUPS.items() if [sec, key] in [list(x) for x in paths]), None)
        if ctl:
            row, was = B.control(brief, ctl), B.control(before, ctl)
            planned = re.split(r"(?<=[.!?])\s+", was.get("plan") or "")
            text = row.get("plan") or ""
            added = text[len(was.get("plan") or ""):] if text.startswith(was.get("plan") or "") else ""
            kept = [s for s in planned if s and not rx.search(s)]
            if len(kept) != len([s for s in planned if s]):
                row["plan"] = " ".join(kept + ([added.strip()] if added.strip() else [])).strip()
                out.append(ctl)
        planner_lines = set(before.get("assumptions") or [])
        brief["assumptions"] = [x for x in brief.get("assumptions") or [] if not (x in planner_lines and rx.search(x))]
    return out


def apply(brief: dict, prompt: str, analyses: list[dict], current: dict | None = None) -> list[dict | None]:
    """Take from each analysed reference video what its focus allows, into the brief (section 3).
    The first readable video steers the brief; another one is noted. Returns the provenance per
    analysis (None for an image), which is also brief["reference"] for the first video."""
    import copy
    planned = copy.deepcopy({k: brief.get(k) for k in ("gameplay", "pacing", "visuals", "level", "controls", "assumptions")})
    try:
        return _apply(brief, prompt, analyses, current)
    finally:
        correct_texts(planned, brief)


def _apply(brief: dict, prompt: str, analyses: list[dict], current: dict | None = None) -> list[dict | None]:
    out: list[dict | None] = []
    done = False
    for a in analyses:
        if a.get("kind") != "video":
            out.append(None)
            continue
        if done:
            line = f"{a['file']} was read too, but only the first reference video steers the brief"
            if line not in brief["assumptions"]:
                brief["assumptions"].append(line)
            out.append(None)
            continue
        done = True
        out.append(_apply_one(brief, prompt, a))
        if not any(x.get("kind") == "image" and not x.get("error") for x in analyses):
            _look_guard(brief, prompt, a)
    return out


LOOK_WORDS = re.compile(r"\b(" + "|".join(B.COLOUR_WORDS_ANY) + r"|colours?|colors?|background|backdrop|theme|themed|palette|style|"
                        r"look|looks|mood|vibe|aesthetic|captions? colou?rs?)\b", re.I)
BLOCK_COLOUR_WORDS = re.compile(r"\b(" + "|".join(B.COLOUR_WORDS_ANY) + r")\b[^.;]{0,30}\b(blocks?|pieces?)\b|"
                                r"\b(blocks?|pieces?)\b[^.;]{0,20}\b(in|coloured|colored)\b", re.I)


def _look_guard(brief: dict, prompt: str, a: dict) -> None:
    """The look a video gives is taken only when the look is a focus, and never the blocks' colours
    (section 3): what the planner's model took from a video's colours on its own is put back to the
    game's own, unless the request's words ask for a look themselves."""
    vs, default = brief["visuals"], B.default_brief()["visuals"]
    words = re.sub(r"\bcolou?r[\s-]*block[\s-]*jam\b", " ", prompt or "", flags=re.I)
    focus = list(a.get("focus") or [])
    reset = []
    if vs.get("blocks") and not BLOCK_COLOUR_WORDS.search(words) and not (brief.get("reference") or {}).get("repaint_from_copy"):
        reset += ["blocks"] + (["theme"] if "look" not in focus and vs.get("theme") == "custom" else [])
    if "look" not in focus and not LOOK_WORDS.search(words):
        reset += [k for k in ("theme", "background", "caption_fill", "caption_outline") if vs.get(k) != default[k]]
    reset = list(dict.fromkeys(reset))
    if not reset:
        return
    for k in reset:
        vs[k] = list(default[k]) if isinstance(default[k], list) else default[k]
    gone = {"blocks": "visuals.colours", "theme": "visuals.colours", "background": "visuals.background",
            "caption_fill": "visuals.captions", "caption_outline": "visuals.captions"}
    dropped = {gone[k] for k in reset}
    if vs.get("theme") != default["theme"]:
        dropped.discard("visuals.colours")  # a look read keeps its custom theme; only the blocks went back
    brief["changed"] = [g for g in brief["changed"] if g not in dropped]
    line = (f"the game's own look is kept ({', '.join(k.replace('_', ' ') for k in reset)}): {a['file']} was read for "
            f"{focus_text(focus)}, and a video's colours never repaint the blocks")
    if line not in brief["assumptions"]:
        brief["assumptions"].append(line)
    row = B.control(brief, "visuals")
    if row["status"] == "applied" and not LOOK_WORDS.search(words):
        row.update(status="default", plan="the game's own look", why=None)


PURE_PLAY = 0.9  # a reference this much play, with no end card, is play from start to end (round 1: both trailers)
SHORTER = 0.9  # a reference shorter than this share of the ad is stretched: the play takes the extra time (LolTap 15 s)
BUSY_CUT = 3  # a cliffhanger reference that stops with this many blocks or more still on the board: a busy cut
BLOCKS_LEFT_MAX = 3  # the most blocks a cliffhanger may cut with (brief.validate)
PLAY_PURPOSES = ("gameplay", "mistake", "near_fail", "payoff", "replay")


def play_share(segs: list[dict]) -> float:
    total = sum(_len(s) for s in segs)
    return sum(_len(s) for s in segs if s.get("purpose") in PLAY_PURPOSES) / total if total else 0.0


def _pure_play(brief: dict, prompt: str, a: dict, segs: list[dict], fixed: set, did: list, prov: dict) -> None:
    """A reference that is play from start to end (PURE_PLAY or more of it play, and no end card; round 1, 2026-10-17:
    both trailers, whose ads came out 56-64% play with the question held 9 s). The ad keeps as much play as the
    engine allows, through the brief's own fields only: no still opening (sequence.intro_s 0: the hook caption runs
    over the play), the question or the result held as briefly as the engine allows (sequence.hold_s 0), and a calm
    tempo, so the recording's pauses lengthen to fill the room the ad leaves (studio picks the longest recording that
    fits for a calm tempo; at a normal tempo it keeps the planned pauses). The end card keeps what is left: its 3 s
    minimum when the play fills the room. Each only where the request does not state it."""
    kind = fill_kind(brief, a, segs)
    if kind is None:
        return
    pure, share, dur = kind
    sq, f = brief["sequence"], a["file"]
    took = []
    if "intro" not in fixed and sq.get("intro_s") != 0.0:
        sq["intro_s"] = 0.0
        took.append("no still opening (the hook caption runs over the play)")
    if "hold" not in fixed and sq.get("hold_s") != 0.0:
        sq["hold_s"] = 0.0
        took.append(f"the {'question' if brief['gameplay']['ending'] == 'cliffhanger' else 'result'} held as briefly as the engine allows")
    if took:
        _changed(brief, "sequence.timing")
    # the tempo and the moves that fill the play are one decision with the pacing's (play_levers, after the board)
    if pure:
        prov["pure_play"] = round(share, 2)
        why = f"play from start to end ({share:.0%} of the reference is play, no end card)"
    else:
        prov["stretched"] = {"reference_s": round(dur, 1), "ad_s": brief["pacing"]["length_s"]}
        why = (f"the reference ({dur:g} s) is shorter than the ad ({brief['pacing']['length_s']:g} s): its hook and end card "
               f"keep their own seconds and the play takes the extra time")
    if not took:
        return
    did.append(why + ": " + "; ".join(took))
    _row(brief, "sequence", why + ": " + "; ".join(took) + "; the end card keeps what is left", prompt, f)


def fill_kind(brief: dict, a: dict, segs: list[dict]) -> tuple[bool, float, float] | None:
    """Whether the reference's play is to fill the ad: play from start to end (PURE_PLAY, no end card) or a reference
    shorter than the ad (SHORTER). (pure, play share, the reference's seconds) or None."""
    if not segs:
        return None
    share = play_share(segs)
    pure = share >= PURE_PLAY and not any(s.get("purpose") == "end_card" for s in segs)
    dur = float((a.get("facts") or {}).get("duration_s") or 0) or sum(_len(s) for s in segs)
    shorter = bool(dur) and dur < SHORTER * brief["pacing"]["length_s"]
    return (pure, share, dur) if pure or shorter else None


# Captions that contradict the ending (round 2, 2026-10-17): LolTap's cliffhanger showed "Board cleared!", trailer 2's
# unfinished board "Can you beat the clock?" on its end card.
WIN_CLAIM = re.compile(r"\b(cleared|solved|done|you did it|level complete\w*|you win|you won|victory|all clear|"
                       r"just in time|made it)\b", re.I)
CLOCK_CLAIM = re.compile(r"\bbeat (the |that )?(clock|timer)\b", re.I)
FAIL_CLAIM = re.compile(r"\b(out of time|time'?s up|failed|game over|so close)\b", re.I)
UNFINISHED_LINE = "Can you finish it?"
TIME_OUT_LINES = {"result": "So close!"}
TIME_OUT_LINE = "Can you finish it in time?"


def claims_against(text: str, ending: str) -> str | None:
    """What a caption claims that the ending played does not show: a clear, a win or a beaten clock on a cliffhanger, a
    win on a time-out, a fail on a win or a near-fail; None when it fits."""
    t = str(text or "")
    if ending == "cliffhanger" and (WIN_CLAIM.search(t) or CLOCK_CLAIM.search(t)):
        return "a clear or a beaten clock"
    if ending == "time_out" and WIN_CLAIM.search(t):
        return "a win"
    if ending in ("win", "near_fail") and FAIL_CLAIM.search(t):
        return "a fail"
    return None


# A caption that promises a chain of exits (round 3, case 19: "One move. Everything flies!" over a play with no chain):
# only with the game's streak finish (gameplay.finish "streak"); otherwise the tool's own words
CHAIN_CLAIM = re.compile(r"\b(fl(y|ies|ying)|all (leave|go|fly|clear|exit)\w*|one after another|chain\w*|cascad\w*|in a row|"
                         r"domino\w*|everything (goes|leaves|clears))\b", re.I)
CHAIN_FREE_LINES = {"cascade": "Almost there!", "result": None, "end_title": "Can you clear it?", "end_fact": "Can you clear it?",
                    "hook": "Can you clear it?"}


# The request's line for the end (2026-10-17, the owner's "End unsolved with a 'your turn' line": the planner put "Your
# turn!" as the result line, fit_captions dropped it as a cliffhanger's result and the ad showed "Can you see the move?"):
# a quoted line whose sentence speaks of the end ("end ... with", "ends with", "finish", "stop ... and ask", "last",
# "final"), or an unquoted "a your-turn line"
END_LINE_WORDS = re.compile(r"\b(end(s|ed|ing)?|finish(es|ed|ing)?|clos(e|es|ing)|stop(s|ped|ping)?|last|final)\b|"
                            r"\bask(s|ing)?\s*$", re.I)
END_CARD_WORDS = re.compile(r"\bend[- ]?card\b|\bend title\b", re.I)
YOUR_TURN = re.compile(r"\b(?:a|an|the)\s+(your[- ]turn|your[- ]move)\s+(line|caption|question|text|title)\b", re.I)


def end_line(prompt: str | None) -> tuple[str, str] | None:
    """(the line, where) the request asks for at the end: where is "end_card" when its sentence names the end card, else
    "question" (a cliffhanger's question caption, concept.result). A quoted line keeps the request's words; "a your-turn
    line" with no quote gets the tool's words, "Your turn!". None when the request asks for no end line."""
    from . import audit
    text = prompt or ""
    for q in audit.asked(text)["captions"]:
        q = q.strip()
        i = text.lower().find(q.lower())
        if not q or i < 0:
            continue
        start = max(text.rfind(c, 0, i) for c in ".!?\n") + 1
        before = text[start:i].rstrip(" \"'“‘«")
        stop = min([j for j in (text.find(c, i + len(q)) for c in ".!?\n") if j >= 0] or [len(text)])
        sentence = text[start:stop + 1]
        after = text[i + len(q):i + len(q) + 24]
        card = bool(END_CARD_WORDS.search(sentence) or re.match(r"[\"'”’»]?\s*(end[- ]?|title )?card\b", after, re.I))
        if END_LINE_WORDS.search(before) or card and END_LINE_WORDS.search(sentence):
            return q[0].upper() + q[1:], "end_card" if card else "question"
    m = YOUR_TURN.search(text)
    if m:
        start = max(text.rfind(c, 0, m.start()) for c in ".!?\n") + 1
        stop = min([j for j in (text.find(c, m.end()) for c in ".!?\n") if j >= 0] or [len(text)])
        sentence = text[start:stop + 1]
        if END_LINE_WORDS.search(sentence):
            words = "Your turn!" if "turn" in m.group(1).lower() else "Your move!"
            return words, "end_card" if END_CARD_WORDS.search(sentence) else "question"
    return None


def fit_captions(brief: dict, prompt: str | None = None, chain: bool = False) -> list[str]:
    """The concept texts made to fit the ending and the play (the guided workflow, after videoref.apply): a cliffhanger's
    result line is cleared (its question is the result moment), and a text that claims a clear, a win or a beaten clock
    becomes "Can you finish it?"; a time-out's win claims become its own lines; a mistake caption with no wrong move
    planned is cleared; with `chain` (the video-reference workflow only, guided.py; the image workflow keeps its captions
    as before) a caption that promises a chain of exits (CHAIN_CLAIM) without the streak finish gets the tool's own words
    (a caption the request quotes stays), and on a cliffhanger the line the request asks for at the end (end_line: "End
    unsolved with a 'your turn' line") is the question caption, or, for any ending, the end card's title when the request
    puts it there ("on the end card", "a 'Can you do it faster?' card": round 4, case 30), never dropped.
    Each change is an assumption; returns them."""
    from . import audit
    from .brief import CONCEPT_TEXTS
    ending, cc = brief["gameplay"]["ending"], brief["concept"]
    out = []
    quoted = [q.strip().lower() for q in audit.asked(prompt or "")["captions"] if q.strip()]
    if chain and brief["gameplay"].get("finish") != "streak":
        for k in CONCEPT_TEXTS:
            v = cc.get(k)
            if k == "cta" or not v or not CHAIN_CLAIM.search(v) or any(q in v.lower() for q in quoted):
                continue
            new = CHAIN_FREE_LINES.get(k) or (OWN_LINES["result"].get(ending) if k == "result" else "Can you clear it?")
            out.append(f"\"{v}\" ({k.replace('_', ' ')}) promises a chain of exits the play does not have (no streak "
                       f"finish); \"{new}\" is used")
            cc[k] = new
            if f"concept.{k}" not in brief.setdefault("changed", []):
                brief["changed"].append(f"concept.{k}")
    asked_end = end_line(prompt) if chain else None
    if asked_end and asked_end[1] == "question" and ending != "cliffhanger":
        asked_end = None  # a question line is the cliffhanger's; another ending keeps the planner's captions
    if asked_end:
        # the request's line for the end is never dropped (video workflow only, 2026-10-17): on a cliffhanger it is the
        # question caption (concept.result, the question moment ad.py draws), or the end card's title when the request
        # puts it there; the planner's text is kept when it already carries the request's words
        line, where = asked_end
        key = "result" if where == "question" else "end_title"
        have = cc.get(key)
        want = have if have and line.lower().rstrip("!?. ") in have.lower() else line
        if have != want:
            cc[key] = want
            if f"concept.{key}" not in brief.setdefault("changed", []):
                brief["changed"].append(f"concept.{key}")
        out.append(f"the request asks for \"{want}\" at the end: it is the "
                   + ("cliffhanger's question caption (its result moment), not the stock \"Can you see the move?\""
                      if key == "result" else "end card's title"))
        if key == "end_title":
            # the end card shows two lines: the fact under the title is never the same text (round 4 rerun, case 30: the
            # planner put "Can you do it faster?" on both); the planner's fact stays when it differs, else the result's
            # own fact (ad.END_FACTS, NO_CLOCK with the clock hidden)
            from .ad import END_FACTS, NO_CLOCK, SHORT_WIN_FACT
            same = lambda v: bool(v) and line.lower().rstrip("!?. ") in str(v).lower()  # noqa: E731
            fact = cc.get("end_fact")
            if same(fact) or (fact is None and same(SHORT_WIN_FACT) and ending == "win"):
                clock = brief["visuals"].get("hud_timer", True) is not False
                own = END_FACTS[ending] if clock else NO_CLOCK["end_fact"].get(ending, END_FACTS[ending])
                own = own if not same(own) else "Cleared!"
                cc["end_fact"] = own
                if "concept.end_fact" not in brief["changed"]:
                    brief["changed"].append("concept.end_fact")
                out.append(f"the end card's second line is \"{own}\": the title already says \"{want}\"")
            if same(cc.get("cta")):
                cc["cta"] = None  # the button keeps its own words
            # the line is the end card's (round 4, case 30: "a 'Can you do it faster?' card"): not also a caption over the
            # play or the result, which on a win is the win screen, not a question
            for k in CONCEPT_TEXTS:
                v = cc.get(k)
                if k not in ("end_title", "end_fact", "cta") and v and same(v):
                    cc[k] = None
                    if f"concept.{k}" not in brief["changed"]:
                        brief["changed"].append(f"concept.{k}")
                    out.append(f"\"{v}\" ({k.replace('_', ' ')}) is left out: the request puts that line on the end card")
    if ending == "cliffhanger" and cc.get("result") and not (asked_end and asked_end[1] == "question"):
        out.append(f"the result line \"{cc['result']}\" is left out: a cliffhanger's result moment is its question")
        cc["result"] = None
    gp = brief["gameplay"]
    planned = gp.get("mistakes") if gp.get("mistakes") is not None else {"near_fail": 1, "time_out": 1}.get(ending, 0)
    if cc.get("mistake") and not planned and ending != "cliffhanger":
        # a mistake caption with no wrong move to stand on (round 2, case 09: "I can't reach yellow!" read as a stuck
        # moment the viewer never saw); a cliffhanger always ends on a blocked attempt, which is one
        out.append(f"the mistake caption \"{cc['mistake']}\" is left out: no wrong move is planned")
        cc["mistake"] = None
        if "concept.mistake" not in brief.setdefault("changed", []):
            brief["changed"].append("concept.mistake")
    if ending in ("cliffhanger", "time_out"):
        for k in CONCEPT_TEXTS:
            v = cc.get(k)
            what = claims_against(v, ending) if v else None
            if what:
                new = UNFINISHED_LINE if ending == "cliffhanger" else TIME_OUT_LINES.get(k, TIME_OUT_LINE)
                out.append(f"\"{v}\" ({k.replace('_', ' ')}) claims {what} the {ending.replace('_', '-')} does not show; "
                           f"\"{new}\" is used")
                cc[k] = new
                if f"concept.{k}" not in brief.setdefault("changed", []):
                    brief["changed"].append(f"concept.{k}")
    for line in out:
        _note(brief, line)
    return out


# The seconds a drag takes in the ad's play part (the recording to the win or the cut, as audit.pace_of_play measures
# it), by tempo and by the pacing studio gives the solve (studio._short_solve: none, "slow", "deliberate", "thinking"),
# and what a wrong move adds beyond its own drag: fitted on the tool's own recordings (studio/recordings, 2026-10-17;
# 12 to 166 recordings a row, about 1.5 s median error). A calm tempo slows the play only through studio's pacing grades
# (round 2, case 07: 10 drags of an easy board at a calm tempo, 0.77 drags a second, where the reference has 0.31); a
# paced solve absorbs its wrong moves in the fitted pauses.
SEC_PER_DRAG = {("calm", "deliberate"): 3.36, ("calm", "thinking"): 2.49, ("calm", None): 1.43,
                ("normal", "slow"): 2.62, ("normal", "deliberate"): 2.40, ("normal", "thinking"): 2.38, ("normal", None): 1.67,
                ("fast", None): 1.64}
MISTAKE_EXTRA_S = {("calm", None): 3.2, ("normal", None): 1.4}
PACE_DPS = {k: round(1 / v, 2) for k, v in SEC_PER_DRAG.items()}
TEMPO_MIDDLE = {"calm": 0.2, "normal": 0.42, "fast": 0.75}  # a tempo word without a count: the middle of its class
PACE_SCALE = (0.6, 1.6)  # how far a measured take may correct the table (a revision's calibration)
DIFFICULTY_REPOSITION = {"easy": 0, "medium": 1, "hard": 2, "any": 1}  # generate: blocks = target drags minus this


def tempo_class(dps: float) -> str:
    from .reference import CALM_DPS, FAST_DPS
    return "calm" if dps < CALM_DPS else "fast" if dps > FAST_DPS else "normal"


def target_dps(a: dict, tempo: str | None = None) -> float | None:
    """The reference's drags a second: counted over its gameplay (reference.pacing_from) when plausible, else the middle
    of its tempo word's class."""
    p = a.get("pacing") or {}
    if p.get("tempo_source") == "counts" and isinstance(p.get("dps"), (int, float)) and p["dps"] > 0:
        return float(p["dps"])
    word = tempo or p.get("tempo") or str((a.get("notes") or {}).get("pacing") or "").lower()
    return TEMPO_MIDDLE.get(word)


def solve_pace(tempo: str, drags: int, length_s: float, ending: str, mistakes: int | None,
               blocks_left: int | None = None) -> str | None:
    """The pacing studio gives a solve of `drags` drags (studio._short_solve's arithmetic on a drag count instead of a
    level file; a unit test checks the two agree): "deliberate", "thinking", "slow" or None."""
    from .ad import END_CARD_MAX_S, END_CARD_S
    from .studio import PACE_EXTRA_S
    if tempo == "fast" or ending not in ("win", "near_fail", "cliffhanger"):
        return None
    d = drags - (blocks_left or (2 if ending == "cliffhanger" else 0))
    m = mistakes if mistakes is not None else {"near_fail": 1}.get(ending, 0)
    estimate = d * 1.6 + 3 + 3.5 * m
    fits = length_s - END_CARD_S[0] - 2.5 - 1.0
    if tempo == "calm":
        if estimate + PACE_EXTRA_S["calm"] * max(0, d - 1) <= fits:
            return "deliberate"
        return "thinking" if estimate + PACE_EXTRA_S["calm"] * max(0, d // 2) <= fits else None
    room = length_s - END_CARD_MAX_S - 7.0
    if estimate >= room:
        return None
    slowed = max(0, (d - 1) // 2)
    rest = max(0, d - 2 - slowed)
    if estimate + PACE_EXTRA_S["deliberate"] * slowed + PACE_EXTRA_S["thinking"] * rest <= fits and \
            estimate + PACE_EXTRA_S["deliberate"] * slowed < room - 2.0:
        return "slow"
    for grade in ("deliberate", "thinking"):
        if estimate + PACE_EXTRA_S[grade] * slowed <= fits:
            return grade
    return None


def play_target(brief: dict, segs: list[dict]) -> tuple[float, float, float]:
    """The play seconds first (round 2 rerun, cases 05 and 14: the end card absorbed what the play did not fill): the ad's
    length minus the end card the reference keeps (3-4 s, or the shortest when it has none), the result or the
    cliffhanger's question, a still opening and a replay; capped by what studio records (its longest recording keeps
    room for a replay, REPLAY_EST_S, and the end card's shortest: studio._length_pick). Returns (target, room, cap)."""
    from . import audit
    from .ad import END_CARD_S, RESULT_HOLD_S
    from .play import END_HOLD_S
    from .studio import REPLAY_EST_S
    gp, sq = brief["gameplay"], brief["sequence"]
    L, ending = float(brief["pacing"]["length_s"]), gp["ending"]
    ref = audit.ref_part_lengths(segs) if segs else {}
    end_s = min(4.0, max(END_CARD_S[0], ref["end"])) if ref.get("end") else END_CARD_S[0]
    result_s = (2.0 if ending == "cliffhanger" else RESULT_HOLD_S) + float(sq.get("hold_s") or 0)
    room = L - end_s - result_s - float(sq.get("intro_s") or 0) - (REPLAY_EST_S if sq.get("replay") else 0.0)
    cap = L - END_CARD_S[0] - REPLAY_EST_S - (2.0 if ending == "cliffhanger" else 0.0) - END_HOLD_S.get(ending, 2.5)
    return round(min(room, cap), 1), round(room, 1), round(cap, 1)


# with a speeds-up curve, a normal-tempo play this close to its seconds fills (calm only otherwise): the curve's careful
# early pauses add to the table's estimate (rerun 4, case 09: 44.4 s became 45.4 s with a speeds-up curve)
RISING_FILL_SLACK_S = 2.5
HESITATION_S = 1.5  # a pick-up and put-back (play: the "hesitate" pause, a 0.7 s hold, the reach): its own pace in any grade
MAX_HESITATIONS = {"win": 1, "near_fail": 2, "cliffhanger": 1, "time_out": 1}  # play.plan's limits


def expected_play(brief: dict, tempo: str, moves: int, scale: float = 1.0,
                  hesitations: int | None = None) -> tuple[float, float, str | None]:
    """(play seconds, drags a second, studio's pacing grade) expected for a level of `moves` drags at `tempo`: the drags
    played are the moves minus the blocks a cut leaves, plus the wrong moves; a hesitation adds HESITATION_S and a drag;
    `scale` is a measured take's correction of the drag rate."""
    gp = brief["gameplay"]
    ending = gp["ending"]
    left = (gp.get("blocks_left") or 2) if ending == "cliffhanger" else 0
    mistakes = gp["mistakes"] if gp.get("mistakes") is not None else {"near_fail": 1, "time_out": 1}.get(ending, 0)
    hes = hesitations if hesitations is not None else \
        (gp["hesitations"] if gp.get("hesitations") is not None else {"near_fail": 2}.get(ending, 0))
    drags = max(1, moves - left) + mistakes
    grade = solve_pace(tempo, moves, brief["pacing"]["length_s"], ending, gp.get("mistakes"), gp.get("blocks_left"))
    play = (drags * SEC_PER_DRAG[(tempo, grade)] + MISTAKE_EXTRA_S.get((tempo, grade), 0.0) * mistakes) / scale \
        + HESITATION_S * hes
    return play, (drags + hes) / play, grade


def expected_dps(brief: dict, tempo: str, drags: int, scale: float = 1.0) -> float:
    return expected_play(brief, tempo, drags, scale)[1]


def play_levers(brief: dict, fixed: set, segs: list[dict], rate: float | None = None, scale: float = 1.0,
                why: str = "", read_size: tuple[int, int] | None = None) -> tuple[str | None, dict]:
    """One decision for the play (round 2 rerun: the stretch rule and the pacing levers both wrote the tempo, and the
    levers won with 9 moves and a 19.9 s play in a 30 s ad, the end card 8.1 s): the play seconds come first
    (play_target), then the tempo, the level's moves and the hesitations, through the brief's own levers. With the
    pacing taken (`rate`, the reference's drags a second) the rate is pinned to the reference's class (calm, normal,
    fast) and, inside it, the levers that fill the play best win, the nearer rate on a tie; without it (a pure-play or
    shorter reference) the tempo is calm, so studio stretches the pauses, and the moves and hesitations fill. The moves
    are the drags the level needs: the drags played plus the blocks a cut leaves. The moves never go under the board's
    blocks; above what its blocks supply (blocks plus the difficulty's repositioning drags) the blocks rise, at most 10,
    and the board grows a cell a side from the size read to hold them (grow_for_blocks). A hesitation (a pick-up and
    put-back, its own pace in any grade) adds time without costing studio's pacing grade (rerun 4, case 05: six played
    drags is the most studio paces with a long look in a 30 s ad). When the best still falls short, `cap` says which
    limit stops it. The request's own tempo, moves, blocks, size and hesitations stay; its relative words for the moves
    ("fewer moves", brief.reference.moves_asked from stated(video=True)) keep the planner's count, never raised, and
    the shorter play is accepted with the cause first in `cap` ("the request asks for fewer moves: 6 kept; the play
    fills 13 of 21 s"). Returns the provenance line and
    the record {mode, target_s, expected_s, rate, tempo, moves, hesitations, blocks, grade, scale, cap}."""
    from .generate import _target_drags
    gp, pc, lv = brief["gameplay"], brief["pacing"], brief["level"]
    scale = min(PACE_SCALE[1], max(PACE_SCALE[0], scale))
    target_s, room, cap = play_target(brief, segs)
    # a speeds-up curve (round 3, case 16: a calm fill paused 2.05 s and 2.50 s a third, "even" where it was asked to speed
    # up): the fill comes from more moves at a normal tempo, calm only when nothing else fills
    rising = pc.get("curve") == "speeds_up" and not rate and "tempo" not in fixed
    tempos = [pc["tempo"]] if "tempo" in fixed else (["calm", "normal", "fast"] if rate else ["normal", "calm"] if rising else ["calm"])
    reposition = DIFFICULTY_REPOSITION.get(lv.get("difficulty") or "any", 1)
    if "moves" in fixed or "blocks" in fixed and lv.get("moves") is not None:
        counts = [lv["moves"] if lv.get("moves") is not None else _target_drags(brief)]
    else:
        lo = max(3, lv.get("blocks") or 3)  # each block leaves once: never fewer drags than blocks
        most = (lv["blocks"] if "blocks" in fixed and lv.get("blocks") else board_most(lv, read_size, fixed)) + reposition
        counts = list(range(lo, max(lo, min(16, most)) + 1))
    # the request's count, or the plan's own (a "clean win" read as none), stays; one the levers set before is theirs
    hes_fixed = "hesitations" in fixed or (gp.get("hesitations") is not None and
                                           "gameplay.hesitations" not in ((brief.get("reference") or {}).get("set") or []))
    hes_options = [gp.get("hesitations")] if hes_fixed else list(range(0, MAX_HESITATIONS.get(gp["ending"], 1) + 1))
    # the pace taken and the moves the request's own (round 4 rerun, case 28: "fewer moves", 6, at the reference's normal
    # 0.31 drags a second chose a calm tempo and a hesitation, and the gaps grew from 0.60 s to 1.60 s, failing the even
    # pacing): the play cannot fill, so the reference's own tempo class with no added hesitation, and a shorter play;
    # the calm and hesitation stretch is for a fill the request allows
    own_moves = bool(rate) and "moves" in fixed and "tempo" not in fixed
    if own_moves:
        tempos = [tempo_class(rate)]
        if not hes_fixed:
            hes_options = [0]

    def outcome(c):
        play, r, grade = expected_play(brief, c[0], c[1], scale, c[2])
        if play > cap:  # studio never records longer than its cap: the same drags, quicker
            play, r = cap, r * play / cap
        return play, r, grade

    def score(c):
        play, r, _ = outcome(c)
        miss = (target_s - play) * 1.5 if play < target_s else play - target_s  # a short play costs more: the card absorbs it
        if rate:
            # the taken pace wins over the fill (rerun 5, case 05: a calm 0.24 reference, no option in the calm class,
            # and the fill won with 0.5 drags a second): in the class, the best fill; with none in it, the nearest rate
            off = tempo_class(r) != tempo_class(rate)
            return (off, round(abs(r - rate), 2) if off else 0, round(miss), round(abs(r - rate), 2), c[2] or 0, -c[1])
        return (round(miss, 1), c[2] or 0, -c[1])

    options = [(t, n, h) for t in tempos for n in counts for h in hes_options]
    tempo, moves, hes = min(options, key=score)
    rising_note = None
    if rising:
        brisk = [o for o in options if o[0] != "calm"]
        best_brisk = min(brisk, key=score)
        if outcome(best_brisk)[0] >= target_s - RISING_FILL_SLACK_S:
            tempo, moves, hes = best_brisk
            rising_note = "the curve speeds up, so the fill comes from more moves at a normal tempo, not from calm looks"
        else:
            tempo, moves, hes = min(options, key=score)
            rising_note = (f"the curve speeds up, but no normal-tempo play fills {target_s:g} s (at most about "
                           f"{outcome(best_brisk)[0]:.0f} s), so the fill is {tempo}")
    play, r, grade = outcome((tempo, moves, hes))
    pace_gap = None
    if rate and tempo_class(r) != tempo_class(rate):
        slowest = max(SEC_PER_DRAG.values()) / scale
        pace_gap = (f"the reference's {tempo_class(rate)} pace ({rate:.2f} drags a second) is "
                    + (f"slower than play.py's longest look allows (about {1 / slowest:.2f} drags a second: the calm pause "
                       f"at its longest), so the nearest pace is kept and the play is shorter" if rate < r else
                       "faster than the play reaches with these moves, so the nearest pace is kept"))
    changed = []
    if "tempo" not in fixed:
        if pc["tempo"] != tempo:
            changed.append(f"a {tempo} tempo")
        pc["tempo"] = tempo
        _changed(brief, "pacing.tempo")  # always the reference's: pinned through revisions, even when unchanged
    if "moves" not in fixed and lv.get("moves") != moves:
        lv["moves"] = moves
        _changed(brief, "level.moves")
        changed.append(f"{moves} moves")
    blocks = lv.get("blocks")
    need = moves - reposition
    asked_count = (brief.get("reference") or {}).get("moves_asked") if "moves" in fixed else None
    if blocks is not None and need > blocks and "blocks" not in fixed and not asked_count:
        want = min(BLOCKS_RANGE[1], need)
        w, h = lv.get("width"), lv.get("height")
        if w and h and "size" not in fixed:
            # a cell a side at most from the board read (the board may have grown once already: _apply_board)
            rw, rh = read_size or (w, h)
            grown = grow_for_blocks(want, lv.get("shape") if lv.get("shape") != "any" else None, min(w, rw), min(h, rh),
                                    lv.get("pieces"))
            if grown and grown[0] * grown[1] < w * h:
                grown = (w, h, board_blocks(want, lv.get("shape"), w, h, lv.get("pieces")))
            if grown:
                if (grown[0], grown[1]) != (w, h):
                    lv["width"], lv["height"] = grown[0], grown[1]
                    _changed(brief, "level.size")
                want = min(want, grown[2])
        if want > blocks:
            lv["blocks"] = want
            _changed(brief, "level.blocks")
            changed.append(f"{want} blocks" + (f" on {lv['width']}x{lv['height']}" if lv.get("width") else ""))
    if not hes_fixed and gp["ending"] in ("win", "cliffhanger", "near_fail", "time_out") and gp.get("hesitations") != hes:
        gp["hesitations"] = hes  # chosen: studio adds quick pick-ups to a short solve when none is set
        _changed(brief, "gameplay.hesitations")
        changed.append("no added hesitation" if not hes else f"{hes} hesitation{'s' if hes != 1 else ''} (a pick-up and put-back)")
    elif not hes_fixed:
        _changed(brief, "gameplay.hesitations")
    limit = cap_reason(brief, tempo, moves, hes, grade, play, target_s, cap, counts, hes_options, fixed, read_size) \
        if play < target_s - 0.5 else None
    # the request's relative words for the moves (2026-10-17: "use fewer moves so each one matters" was overridden by a
    # fill of 10): the planner's count stays, the shorter play is accepted, and the cause is said first
    if pace_gap:
        limit = pace_gap if not limit else f"{pace_gap}; {limit}"
    elif rate and play < target_s - 0.5:
        limit = f"the reference's {tempo_class(rate)} pace is kept over the fill; " + (limit or "")
    # the request's relative words for the moves (2026-10-17: "use fewer moves so each one matters" was overridden by a
    # fill of 10): the planner's count stays, the shorter play is accepted, and the cause is said first
    asked_moves = (brief.get("reference") or {}).get("moves_asked") if "moves" in fixed else None
    derived = asked_moves if asked_moves and ":" in asked_moves else None  # the count derived from the reading (case 28)
    if asked_moves:
        asked_moves = asked_moves.split(":")[0].strip('"') if derived else asked_moves
    if asked_moves and play < target_s - 0.5:
        rest_bits = [b for b in (limit or "").split("; ") if b and not b.startswith("the request's own")]
        limit = "; ".join([f"the request asks for {asked_moves}: {moves} kept; the play fills {play:.0f} of {target_s:g} s"]
                          + rest_bits)
    rec = {"mode": "pace" if rate else "fill", "target_s": target_s, "expected_s": round(play, 1), "rate": round(r, 2),
           "tempo": tempo, "moves": moves, "hesitations": hes, "blocks": lv.get("blocks"), "grade": grade,
           "scale": round(scale, 2), "cap": limit}
    if rate:
        rec["reference_rate"] = round(rate, 2)
    if own_moves:
        rec["own_moves"] = True  # the reference's tempo class, no added hesitation (round 4 rerun, case 28)
    if asked_moves:
        rec["moves_asked"] = asked_moves
        if derived:
            rec["moves_derived"] = derived
    paced = {"deliberate": "a long look before each drag" if tempo == "calm" else "a long look before every other drag",
             "thinking": "a thought before every other drag" if tempo == "calm" else "a thought before each drag",
             "slow": "a long look before every other drag and a thought before the rest"}.get(grade, "the planned pauses")
    head = (f"the play fills about {play:.0f} of {target_s:g} s" + (f" (studio records at most {cap:g} s of play)" if room > cap else "")
            + (f" at the reference's {tempo_class(rate)} pace ({rate:.2f} drags a second)" if rate else ""))
    rest = [c for c in changed if "tempo" not in c and "moves" not in c]
    line = (f"{head}: a {tempo} tempo, {moves} moves" + (", " + ", ".join(rest) if rest else "")
            + f" ({paced}; about {r:.2f} drags a second expected" + (f", corrected by the last take's measure x{scale:.2f}"
                                                                     if scale != 1.0 else "") + ")"
            + (f"; it stops there: {limit}" if limit else "") + (f"; {rising_note}" if rising_note else "")
            + (f"; the moves: {derived}" if derived else "")
            + (f"; the request's own moves keep the reference's {tempo} tempo with no added hesitation (a calm stretch "
               f"would make the gaps uneven), so the play is shorter" if own_moves and play < target_s - 0.5 else "")
            + (f"{why}" if why else ""))
    if rising_note:
        rec["curve"] = rising_note
    return line, rec


LENGTH_FIT_TRIES = 4  # the lengths tried below the first one, each where the last one's play fell short


def lever_state(brief: dict) -> dict:
    """What the play levers may change (the level, the gameplay, the pacing, the changed groups and what the reference
    set), copied, so the levers can be run again at another length from the same start (fit_length)."""
    import copy
    return copy.deepcopy({"level": brief["level"], "gameplay": brief["gameplay"], "pacing": brief["pacing"],
                          "changed": brief.get("changed"), "set": (brief.get("reference") or {}).get("set")})


def _restore_levers(brief: dict, state: dict) -> None:
    import copy
    for k in ("level", "gameplay", "pacing", "changed"):
        brief[k] = copy.deepcopy(state[k])
    if isinstance(brief.get("reference"), dict) and state.get("set") is not None:
        brief["reference"]["set"][:] = copy.deepcopy(state["set"])


def fit_length(brief: dict, fixed: set, segs: list[dict], line: str, rec: dict, state: dict, rate: float | None = None,
               read_size: tuple[int, int] | None = None) -> tuple[str, dict]:
    """The ad's length from the play, not the play from a length (round 3, case 17: a 60 s ad from a 30 s reference
    played 37 s and held a 21 s end card): when the request states no single length and the levers fall short of the
    play seconds with no lever left, the length drops (down to 30 s) by what the play misses, and the levers run again
    there from the same start (`state`, lever_state), a few times; the length whose play misses least wins (a short play
    costs more, as in play_levers' score; on a tie the longer). It never rises: the first length is the reference's own
    brought into the case's range, or the plan's. Returns the play line and record, with rec["length"] {from, to, why}
    when the length changed."""
    import math
    pc, lo = brief["pacing"], B.LENGTH_RANGE_S[0]
    L0 = float(pc["length_s"])
    if "length" in fixed or L0 <= lo or rec["expected_s"] >= rec["target_s"] - 0.5:
        return line, rec

    def miss(r):
        short = r["target_s"] - r["expected_s"]
        return round(short * 1.5 if short > 0 else -short, 1)
    tried = {L0: miss(rec)}
    first = (rec["expected_s"], rec["target_s"], rec.get("cap"))
    L, r = L0, rec
    for _ in range(LENGTH_FIT_TRIES):
        short = r["target_s"] - r["expected_s"]
        new = max(lo, float(math.floor(L - short)))
        if short <= 0.5 or new >= L or new in tried:
            break
        _restore_levers(brief, state)
        pc = brief["pacing"]
        pc["length_s"] = new
        _, r = play_levers(brief, fixed, segs, rate=rate, read_size=read_size)
        tried[new], L = miss(r), new
    best = min(tried, key=lambda k: (tried[k], -k))
    _restore_levers(brief, state)
    brief["pacing"]["length_s"] = best
    line, rec = play_levers(brief, fixed, segs, rate=rate, read_size=read_size)
    if best == L0:
        return line, rec
    _changed(brief, "pacing.length")
    why = (f"at {L0:g} s the play fills about {first[0]:.0f} of {first[1]:g} s and no lever is left"
           + (f" ({first[2]})" if first[2] else ""))
    rec["length"] = {"from": L0, "to": best, "why": why}
    line += (f"; the ad is {best:g} s, not {L0:g} s: {why}, so the length drops (the case's 30 s at the least) "
             f"instead of the end card growing")
    return line, rec


def board_most(lv: dict, read_size: tuple[int, int] | None, fixed: set) -> int:
    """The most blocks the board can hold: within a cell a side of the size read (or the board as it is when its size
    is the request's or unknown), at the generator's packed fill; BLOCKS_RANGE's top when there is no board yet."""
    w, h = lv.get("width"), lv.get("height")
    if not (w and h):
        return BLOCKS_RANGE[1]
    if "size" in fixed:
        return board_blocks(BLOCKS_RANGE[1], lv.get("shape"), w, h, lv.get("pieces")) or BLOCKS_RANGE[1]
    rw, rh = read_size or (w, h)
    grown = grow_for_blocks(BLOCKS_RANGE[1], lv.get("shape") if lv.get("shape") != "any" else None, min(w, rw), min(h, rh),
                            lv.get("pieces"))
    return max(grown[2] if grown else 0, lv.get("blocks") or 0) or BLOCKS_RANGE[1]


def cap_reason(brief: dict, tempo: str, moves: int, hes: int, grade: str | None, play: float, target_s: float, cap: float,
               counts: list[int], hes_options: list, fixed: set, read_size) -> str:
    """Which limit stops the play short of its seconds, in words (rerun 4, case 05: "the play again" chose the same
    levers and said nothing of why)."""
    gp, L = brief["gameplay"], brief["pacing"]["length_s"]
    bits = []
    if play >= cap - 0.5:
        bits.append(f"studio records at most {cap:g} s of play in a {L:g} s ad (studio._length_pick keeps "
                    f"room for a replay and the shortest end card)")
    if grade in ("deliberate", "thinking", "slow") and moves + 1 <= 16:
        nxt = solve_pace(tempo, moves + 1, L, gp["ending"], gp.get("mistakes"), gp.get("blocks_left"))
        if nxt != grade:
            left = (gp.get("blocks_left") or 2) if gp["ending"] == "cliffhanger" else 0
            bits.append(f"studio paces a solve with {'a long look' if grade == 'deliberate' else 'a thought'} before its "
                        f"drags only up to {moves - left} played drags in a {L:g} s ad (studio._short_solve); one more "
                        f"drag loses it, and the play gets shorter")
    if counts and moves >= max(counts) and "moves" not in fixed:
        lv = brief["level"]
        if "size" in fixed and lv.get("width") and lv.get("height"):
            bits.append(f"the request's own {lv['width']}x{lv['height']} board holds at most "
                        f"{board_blocks(BLOCKS_RANGE[1], lv.get('shape'), lv['width'], lv['height'], lv.get('pieces')) or max(counts)}"
                        f" blocks, so at most {max(counts)} moves")
        else:
            bits.append(f"the board holds at most {lv.get('blocks') or max(counts)} blocks within a cell a side of the "
                        f"size read, so at most {max(counts)} moves")
    if hes_options and hes >= max(h for h in hes_options if h is not None) and len(hes_options) > 1:
        bits.append(f"{hes} hesitation{'s' if hes != 1 else ''}, the most this ending plays")
    if "tempo" in fixed or "moves" in fixed or "blocks" in fixed:
        bits.append("the request's own " + ", ".join(k for k in ("tempo", "moves", "blocks") if k in fixed))
    return "; ".join(bits) or "the levers' best estimate"


def _note(brief: dict, line: str) -> None:
    if line not in brief["assumptions"]:
        brief["assumptions"].append(line)


def _apply_board_colours(brief: dict, prompt: str, a: dict, notes: dict, fixed: set, did: list, prov: dict) -> None:
    """The blocks' colours alone (round 2, case 10: "take only the block colours of this video" had put the reference's
    palette into the background and left the level's colours empty): level.colours from the board read, mapped to the
    game's own (board_colours), nothing else of the board; the request's own colours win."""
    bd = board_of(notes)
    f, lv = a["file"], brief["level"]
    if bd is None or not bd["colours"]:
        _note(brief, f"{f}: no block colours were read, so the level's colours follow the request")
        return
    if "colours" in fixed:
        _note(brief, f"the request names the blocks' colours itself, so the colours of {f} are not taken")
        return
    lv["colours"] = list(bd["colours"])[:7]
    _changed(brief, "level.colours")
    words = ", ".join(c.lower().replace("darkgreen", "dark green") for c in lv["colours"])
    did.append(f"the blocks' colours ({words})")
    _row(brief, "level", f"the blocks' colours of the reference: {words} (the game's own colours nearest the ones read; "
                         f"the board itself is the request's)", prompt, f)
    for m in bd.get("colour_map") or []:
        if m.get("note"):
            _note(brief, m["note"])
    prov["board"] = {"read": bd, "text": board_text(bd), "took": ["colours"], "busy": bd["busy"], "fit": None,
                     "kept": [], "colours_only": True}


def _words_of(prompt: str) -> str:
    return re.sub(r"\bcolou?r[\s-]*block[\s-]*jam\b", " ", prompt or "", flags=re.I)


def _copy_board(brief: dict, prompt: str, a: dict, fixed: set, did: list, prov: dict) -> bool:
    """The video's own board (2026-10-19): when the words ask for THE board (videocells.copy_asked) and its first frame of
    play was read cell by cell (a["cells_copy"], videocells.read_board), the level is that board with the asked changes
    (imageplan.copy_spec: fewer or more blocks, one more or fewer colour, a recolour, a mirror, harder, easier), source
    "picture", as the image workflow does. True when copied; False (with the reason noted) leaves the type path to run."""
    from . import imageplan as IP
    f, lv, cc = a["file"], brief["level"], a.get("cells_copy") or {}
    if "level" in fixed:
        _note(brief, f"the request names the game's own level, so the board of {f} is not copied")
        return False
    cells = cc.get("cells") or {}
    if cc.get("error") or not cells.get("level"):
        _note(brief, f"the video's board could not be read cell by cell from its frame ({str(cc.get('error') or 'no board')[:160]}); "
                     "a board of its type is built instead")
        return False
    spec = IP.copy_spec(prompt, brief, {"cells": cells}, {"board": True})
    if not spec or spec.get("skipped"):
        why = "; ".join(spec.get("skipped") or []) if spec else "the words ask for a new board"
        _note(brief, f"the video's board is not copied ({why}); a board of its type is built instead")
        return False
    for k, v in spec["set"].items():
        lv[k] = v
    lv["shipped"], lv["pieces"], lv["style"], lv["difficulty"] = None, lv.get("pieces") or "varied", [], "any"
    for g in ("level.source", "level.size", "level.blocks", "level.colours", "level.shape", "level.pieces", "level.style"):
        _changed(brief, g)
    t = cc.get("t")
    from .audit import asked as _asked
    own_look = bool(_asked(prompt).get("original"))  # "in the game's own look" (V2, 2026-10-19): the build's colours, mapped and said
    if cc.get("cbj") and cells.get("colours") and not BLOCK_COLOUR_WORDS.search(_words_of(prompt)) and not own_look:
        # the video is Color Block Jam itself: its board is shown in the colours the footage shows (the live game's palette
        # differs from the build's; 2026-10-19 V0: the viewer called the build's colours "swapped"), each slot's block and
        # door together; the mapping is said. A request naming block colours keeps its own.
        shown, lines = IP.repaint([{"read": c["name"], "rgb": c["rgb"], "slot": c["slot"]} for c in cells["colours"] if c.get("rgb")])
        if shown:
            brief["visuals"]["blocks"] = [{"slot": x["slot"], "hex": x["hex"], "name": x["name"]} for x in shown]
            _changed(brief, "visuals.colours")
            prov["repaint_from_copy"] = True
            for line in lines:
                _note(brief, line)
            prov.setdefault("taken", []).append("the blocks' colours as the footage shows them: " + ", ".join(f"{x['name']} on the {B.COLOUR_WORDS[x['slot']]} slot" for x in shown))
    elif cc.get("cbj") and cells.get("colours") and own_look:
        _note(brief, "the game's own look is asked, so the video's colours are not painted on the blocks: " +
              ", ".join(f"{c['name']} -> {B.COLOUR_WORDS[c['slot']]}" for c in cells["colours"]))
    board = dict(spec["board"])
    board.update(frame=cc.get("frame"), frame_t=t, took=["board"], text=board.get("text"))
    prov["board"] = board
    prov["board_copied"] = True
    for line in spec["notes"]:
        _note(brief, line)
    changes = [d["note"] for d in board.get("transforms") or [] if d.get("kind") not in ("walls", "repair")]
    what = (f"the board itself, copied cell by cell from the frame at {t:g} s ({board.get('text')})"
            + (": " + "; ".join(changes) if changes else ""))
    did.append(what)
    _row(brief, "level", f"{what}. Say 'a new board of this type' or 'a level like this' for a fresh board like it", prompt, f, replace=True)
    return True


PACE_MARGIN_S = 3.0  # a fit within this of the room is no fit (V3 third run: calm "fitted" by 2 s on paper and played 44 s)
PACE_SCRIPT_MAX_BLOCKS = 10  # above this the play is not scripted at plan time (V3's 16 blocks: minutes); the solve is scaled instead
PACE_PARK_FACTOR = 1.0  # the per-drag table (SEC_PER_DRAG, measured on recordings) already holds the engine's parking drags: V3 played 44 s for 24 + 2 drags, the table says 49


PACE_SHORT_S = 8.0  # a copied board whose play leaves this much more room than the shortest end card: said at plan time


def copied_board_pace(brief: dict, prompt: str, fixed: set, prov: dict, what: str = "the video's board") -> str | None:
    """A copied board has the moves it has (V3, 2026-10-19: trailer 3's 16 blocks, 24 drags at least, played 44 s in a 45 s
    ad; two revisions could not shorten it). The play its solution needs is estimated for the planner's tempo; when the
    stated length cannot hold it, the fastest tempo that fits is set (unless the request states the tempo), and when none
    fits the plan says so and the length the ad will need; the loop then does not try to shorten what cannot be shortened
    (guided.revise_once). Returns the line for the provenance, or None."""
    from . import imagecells as IC
    from .ad import END_CARD_S, RESULT_HOLD_S
    from .studio import REPLAY_EST_S
    level = ((prov.get("board") or {}).get("level")) or {}
    if not level:
        return None
    m = re.search(r"(\d+) drags", str(((prov.get("board") or {}).get("verify") or {}).get("solve") or ""))
    moves = int(m.group(1)) if m else IC.min_drags(level)  # the reading's own solve first (a 16-block board costs 20 s to solve again)
    if moves is None:
        return None
    gp, pc, sq = brief["gameplay"], brief["pacing"], brief["sequence"]
    hes = None
    big = len(level.get("GridBlockDatas") or []) > PACE_SCRIPT_MAX_BLOCKS
    if big:  # scripting a big board's play takes minutes; the engine's parking moves are allowed for instead
        moves = int(round(moves * PACE_PARK_FACTOR))
    try:  # the play as the engine would script it (its parking moves and mistakes), not the bare minimum (V3: 24 drags, 44 s)
        if big:
            raise ValueError("a big board: estimated from the solve")
        from .level import level_from_dict
        from .play import plan as play_plan
        script = play_plan(level_from_dict(level, name="copied"), gp["ending"], mistakes=gp.get("mistakes"), hesitations=gp.get("hesitations"),
                           left=gp.get("blocks_left"), clock_left=gp.get("clock_left_s") or 1)
        kinds = [b.kind for b in script.beats]
        left = (gp.get("blocks_left") or 2) if gp["ending"] == "cliffhanger" else 0
        moves = max(moves, sum(1 for k in kinds if k in ("solve", "bump", "short")) + left)
        hes = sum(1 for k in kinds if k == "hesitate")
    except Exception:
        pass
    room = pc["length_s"] - END_CARD_S[0] - (2.0 if gp["ending"] == "cliffhanger" else RESULT_HOLD_S) - \
        (REPLAY_EST_S if sq.get("replay") else 0.0) - float(sq.get("intro_s") or 0)
    tempos = ("calm", "normal", "fast")
    own = expected_play(brief, pc["tempo"], moves, hesitations=hes)[0]
    if own <= room - PACE_MARGIN_S:
        if own < room - PACE_SHORT_S and "length" not in fixed:
            # the other direction (S3, S5, 2026-10-19: a 6-block board in a 40 s ad left a 15 s end card): said at plan time, the
            # length kept (the request's), the end-card row judges the result; a stated length is the user's choice
            line = (f"{what} ({len(level['GridBlockDatas'])} blocks, {moves} drags) gives about {own:.0f} s of play at a {pc['tempo']} tempo; "
                    f"the {pc['length_s']:g} s ad holds about {room:g} s, so about {room - own:.0f} s goes to the held result and the end "
                    f"card (ask for a shorter ad, more blocks, or a calmer play with mistakes)")
            _note(brief, line)
            prov["play_short"] = {"play_s": round(own, 1), "room_s": round(room, 1), "moves": moves}
            return line
        return None
    fits = [(expected_play(brief, tp, moves, hesitations=hes)[0], tp) for tp in tempos]
    best = next((x for x in fits if x[0] <= room - PACE_MARGIN_S), None)
    if best and "tempo" not in fixed and best[1] != pc["tempo"]:
        pc["tempo"] = best[1]
        _changed(brief, "pacing.tempo")
        line = (f"{what} needs about {own:.0f} s of play at a {pc['tempo']} tempo for its {moves} drags; the {pc['length_s']:g} s ad "
                f"holds about {room:g} s, so the tempo is {best[1]} (about {best[0]:.0f} s)")
        _note(brief, line)
        return line
    shortest = min(fits)
    need = shortest[0] + (pc["length_s"] - room)
    line = (f"{what} ({len(level['GridBlockDatas'])} blocks, {moves} drags at least) needs about {shortest[0]:.0f} s of play even at a "
            f"{shortest[1]} tempo; the {pc['length_s']:g} s asked holds about {room:g} s, so the ad will run about {need:.0f} s: a copied "
            f"board cannot be shortened (ask for fewer blocks, or a longer ad)")
    _note(brief, line)
    prov["play_overrun"] = {"need_s": round(need, 1), "room_s": round(room, 1), "moves": moves}
    row = B.control(brief, "difficulty_pacing")
    row["plan"] = f"{row['plan']} {line}.".strip() if row.get("plan") else line
    if row.get("status") in ("default", "applied"):
        row["status"] = "adjusted"
    return line


def _apply_board(brief: dict, prompt: str, a: dict, notes: dict, fixed: set, did: list, prov: dict) -> None:
    """The level's type from the reference's board (2026-10-17, the owner's rule: when the request says nothing about the
    level, the board's shape, size, block count, colours and piece sizes come from the reference). Each part the
    request states itself stays the request's; a request naming the game's own level ("level 3", "a shipped level")
    takes nothing. The level is then generated and solved by the generator's own rules; the cells are not copied (a
    sampled reading cannot place them, and the case asks for no frame-by-frame copy), and another game's obstacles
    never add a block, a wall or a shape. How busy the board looks is info only: the difficulty stays the request's,
    the ending rule's (hard for a near-fail) or the generator's default (R10: it read 1-2 of 12)."""
    f, lv, gp = a["file"], brief["level"], brief["gameplay"]
    bd = board_of(notes)
    if bd is None:
        _note(brief, f"{f}: no board was read, so the level follows the request")
        return
    if "level" in fixed:
        _note(brief, f"the request names the game's own level, so the board of {f} is not taken")
        return
    took, notes_ = [], []
    if bd["shape"] and "shape" not in fixed:
        lv["shape"] = bd["shape"]
        _changed(brief, "level.shape")
        took.append("shape")
    shape = lv["shape"] if lv["shape"] != "any" else None
    if (bd["columns"] or bd["rows"]) and "size" not in fixed:
        w, h = board_size(shape, bd["columns"], bd["rows"])
        if w and h:
            lv["width"], lv["height"] = w, h
            _changed(brief, "level.size")
            took.append("size")
            if (w, h) != (bd["columns"], bd["rows"]):
                notes_.append(f"the reference's {bd['columns']}x{bd['rows']} board is made {w}x{h}, the nearest the generator "
                              f"builds for {'an' if (_shape_words(shape) or 'open')[:1] in 'aeiou' else 'a'} "
                              f"{_shape_words(shape) or 'open'} board")
    if bd["pieces"] and "pieces" not in fixed:
        lv["pieces"] = bd["pieces"]
        _changed(brief, "level.pieces")
        took.append("pieces")
    want = min(bd["blocks"], BLOCKS_RANGE[1]) if bd["blocks"] is not None and not {"blocks", "moves"} & fixed else None
    walls_chosen = False
    if bd.get("wall_cells") is not None and "shape" not in fixed and lv["shape"] in ("open", "holes") and lv.get("width"):
        # a few inner walls (round 1: ONE 2-cell wall became five wall cells in a V): the closest board the generator
        # builds, open (none) or holes with the fewest walls, within a cell a side of the size read
        sw, walls, (gw, gh, _) = wall_choice(bd["wall_cells"], lv["width"], lv["height"], want, lv["pieces"],
                                             grow="size" in took)
        n_w = bd["wall_cells"]
        prov["board_walls"] = (f"the reference shows {n_w} wall cell{'s' if n_w != 1 else ''} inside the board; "
                               + ("an open board (no walls) is the closest the generator builds" if sw == "open" else
                                  f"the closest the generator builds is its holes board with {walls} walls on {gw}x{gh}"
                                  + (" (a wall cell off the reading, which is within its error, so the blocks read fit)"
                                     if abs(walls - n_w) == WALL_SLACK and want else "")))
        if sw != lv["shape"]:
            lv["shape"] = sw
            _changed(brief, "level.shape")
            if "shape" not in took:
                took.append("shape")
        if (gw, gh) != (lv["width"], lv["height"]):
            lv["width"], lv["height"] = gw, gh
            _changed(brief, "level.size")
        notes_.append(prov["board_walls"])
        shape, walls_chosen = sw, True
    if want is not None:
        n = board_blocks(bd["blocks"], shape, lv["width"], lv["height"], lv["pieces"])
        if n < want and "size" in took and not walls_chosen:  # grow the board first (a cell a side at most), then cut
            grown = grow_for_blocks(want, shape, lv["width"], lv["height"], lv["pieces"])
            if grown and grown[:2] != (lv["width"], lv["height"]):
                (w0, h0), (lv["width"], lv["height"], n2) = (lv["width"], lv["height"]), grown
                fit = (f"the board read {w0}x{h0} holds {n}; {lv['width']}x{lv['height']} is used so {n2} fit"
                       + ("" if n2 >= want else f" (of the {bd['blocks']} read; a cell a side is the most the board grows)"))
                notes_.append(fit)
                prov.setdefault("board_fit", fit)
                n = n2
        if bd["blocks"] > BLOCKS_RANGE[1] and n >= want and "size" in took and bd.get("columns") and bd.get("rows"):
            # the block count is capped (round 1: trailer 3's 16 blocks became 10 on a sparse 9x10): the board shrinks so
            # the made board keeps the reference's fill, blocks per cell
            fill = bd["blocks"] / (bd["columns"] * bd["rows"])
            kept = keep_fill(n, fill, shape, lv["width"], lv["height"], lv["pieces"])
            if kept and kept != (lv["width"], lv["height"]):
                w0, h0 = lv["width"], lv["height"]
                lv["width"], lv["height"] = kept
                _changed(brief, "level.size")
                fit = (f"the reference has {bd['blocks']} blocks on {bd['columns']}x{bd['rows']} ({fill:.2f} a cell); the "
                       f"brief takes {n} at most, so the board is {kept[0]}x{kept[1]}, not {w0}x{h0}, to keep that fill")
                notes_.append(fit)
                prov.setdefault("board_fit", fit)
        lv["blocks"] = n
        _changed(brief, "level.blocks")
        took.append("blocks")
        if n != bd["blocks"] and "board_fit" not in prov:
            fit = f"the reference shows {bd['blocks']} blocks; {n} is the most this board takes in a generated level"
            notes_.append(fit)
            prov["board_fit"] = fit
    if bd["colours"] and "colours" not in fixed:
        lv["colours"] = list(bd["colours"])[:7]
        _changed(brief, "level.colours")
        took.append("colours")
    if bd["colours"] and "colours" not in fixed:
        notes_ += [m["note"] for m in bd.get("colour_map") or [] if m.get("note")]
    full = board_full(bd, lv)
    if full and "style" not in fixed and "packed" not in (lv.get("style") or []) and "spacious" not in (lv.get("style") or []):
        lv["style"] = list(lv.get("style") or []) + ["packed"]  # the generator's own packed look
        _changed(brief, "level.style")
        took.append("packed")
        notes_.append(f"the reference's board is full ({full}), so the level is packed")
    if bd.get("symmetric") and "style" not in fixed and "symmetric" not in (lv.get("style") or []):
        lv["style"] = list(lv.get("style") or []) + ["symmetric"]  # the generator's own mirror-symmetric look
        _changed(brief, "level.style")
        took.append("symmetric")
    if bd["colours_unmapped"]:
        notes_.append(f"block colours the game does not have ({', '.join(bd['colours_unmapped'])}) are not used")
    if not took:
        _note(brief, f"the request states the level itself, so the board of {f} is not taken ({board_text(bd)})")
        return
    lv["source"], lv["shipped"] = "generate", None
    _changed(brief, "level.source")
    if "style" not in fixed and "level.style" not in prov["set"]:
        prov["set"].append("level.style")  # the board's look was read too (none taken is a reading): a revision keeps it
    words = _shape_words(lv["shape"]) if lv["shape"] != "any" else ""
    size = f"{lv['width']}x{lv['height']} " if lv.get("width") and lv.get("height") else ""
    what = f"{'an' if words[:1] in 'aeiou' and words else 'a'} {(words + ' ') if words else ''}{size}board".replace("  ", " ")
    if lv.get("blocks") is not None:
        what += f" with {lv['blocks']} blocks"
    if lv.get("colours"):
        what += f" in {len(lv['colours'])} colours"
    if lv.get("pieces") and lv["pieces"] != "mixed":
        what += f" ({lv['pieces']} pieces)"
    if "symmetric" in took:
        what += ", mirror-symmetric"
    if "packed" in took:
        what += ", packed"
    _row(brief, "level", f"{what}; a new board of this type is generated and solved, its cells are not copied", prompt, f)
    did.append(f"the board ({what})")
    if "its exact layout" not in prov["not_copied"]:
        prov["not_copied"].append("its exact layout")
    prov["board"] = {"read": bd, "text": board_text(bd), "took": took, "busy": bd["busy"], "fit": prov.pop("board_fit", None),
                     "kept": sorted({"shape", "size", "blocks", "colours", "pieces"} & fixed)}
    for line in notes_:
        _note(brief, line)


CBJ_NAME = re.compile(r"colou?r\s*block\s*jam", re.I)
LEVEL_LABEL = re.compile(r"\blevel\s*(\d{1,4})\b", re.I)


GENERIC_GAME = re.compile(r"^(a|an|another|the|some|this)?\s*([a-z-]+\s+){0,4}(game|puzzle|app|ad|title)s?\b", re.I)


def named_game(game: str) -> bool:
    """Whether the reading names a game (a proper name: "Wood Color Jam", "Toy Blast", a quoted title) rather than
    describing one ("Another puzzle game", "Brick puzzle game", "A toy brick sliding puzzle game")."""
    g = str(game or "").strip()
    if not g or CBJ_NAME.search(g):
        return False
    if re.search(r"[\"“'‘][^\"”'’]{2,}[\"”'’]", g):
        return True
    words = re.findall(r"[A-Za-z][\w'-]*", g)
    caps = [w for i, w in enumerate(words) if w[0].isupper() and i > 0 or (i == 0 and len(words) > 1 and w[0].isupper()
                                                                            and words[1][0].isupper())]
    return len(caps) >= 2 and not GENERIC_GAME.match(g)


def hud_of(notes: dict) -> dict:
    """The HUD at the first frame of play: {level (the number), clock_s (the clock in seconds), cbj (whether the reference
    is Color Block Jam itself: the model says so, or the HUD reads "LEVEL n" with the game's clock)}. The level and the
    clock come from notes.hud, else from the first matching screen_text entries."""
    hud = notes.get("hud") if isinstance(notes.get("hud"), dict) else {}
    texts = [str(x) for x in notes.get("screen_text") or []]
    m = LEVEL_LABEL.search(str(hud.get("level") or "")) or next((LEVEL_LABEL.search(x) for x in texts if LEVEL_LABEL.search(x)), None)
    level = int(m.group(1)) if m else None
    clock = _clock_s(hud.get("clock")) if hud.get("clock") else next((_clock_s(x) for x in texts if _clock_s(x) is not None), None)
    clock = clock or None  # a clock at 00:00 when play starts is no clock (refs-v8: LolTap's invented one)
    game = str(notes.get("game_or_product") or "").strip()
    # Color Block Jam itself: the model says so, or the HUD reads the game's "LEVEL n" with its clock and no OTHER game is
    # named (refs-v8: another game was given "LEVEL 25" and "00:00", copied from the schema's own example; round 2:
    # trailer 2 read as "Another puzzle game", a description, not a name, must not lose its Level 25)
    cbj = bool(CBJ_NAME.search(game)) or (level is not None and clock is not None and not named_game(game))
    return {"level": level, "clock_s": clock, "cbj": cbj}


START_TIME_WISH = re.compile(r"\b(same|its|the video'?s|the reference'?s|this video'?s)\b[^.;]{0,40}\bstart(ing)?\s+"
                             r"(time|clock|timer)\b|\bstart(ing)?\s+(time|clock|timer)\b[^.;]{0,30}\b(as|like|of|from)\s+"
                             r"(this|the)\s+(video|clip|reference)\b", re.I)
AD_PLAY_S = {"win": 0, "near_fail": 5, "time_out": 0}  # the clock left when the play ends, by the ending


def clock_unreachable(start_s: int, brief: dict) -> str | None:
    """Why a starting clock cannot be the reference's for the brief's ending, or None. A win and a cliffhanger can start
    at any clock (a cliffhanger stops mid-level); a near-fail ends with 5 s or less and a time-out at 0, so the play
    (about the ad's length less 8 s of hook, result and end card) must bring the clock down that far."""
    ending = brief["gameplay"]["ending"]
    if ending in ("win", "cliffhanger"):
        return None
    play = max(0.0, brief["pacing"]["length_s"] - 8.0)
    left = start_s - play
    if left > AD_PLAY_S.get(ending, 0):
        mmss = f"{start_s // 60:02d}:{start_s % 60:02d}"
        return (f"a {ending.replace('_', '-')} ends with {AD_PLAY_S[ending]} s or less on the clock, and about {play:g} s "
                f"of play brings {mmss} down only to about {left:g} s")
    return None


def _apply_hud(brief: dict, prompt: str, a: dict, notes: dict, fixed: set, did: list, prov: dict) -> None:
    """When the reference is Color Block Jam itself (2026-10-17, the owner's trailers), its HUD's level number goes to
    level.label and its clock at the first frame of play to gameplay.timer_s, each only when the request does not
    state its own. The clock is taken for a win and a cliffhanger (which stops mid-level, so its start is free), and
    for a near-fail or a time-out only when the play can bring it down to the ending's seconds (clock_unreachable);
    a request that asks for the reference's starting time has it set whatever the ending, and the plan row says when
    the ending makes it impossible (round 2, case 05). brief.validate keeps a starting clock for a win only, so for the
    other endings the clock set here is dropped there, with its own note (brief.py is not changed)."""
    hud = hud_of(notes)
    if not hud["cbj"]:
        return
    f, lv, gp = a["file"], brief["level"], brief["gameplay"]
    from . import audit
    asked = audit.asked((prompt or "") + ". " + ". ".join(own_constraints((a.get("plan") or {}).get("constraints") or [])))
    took = []
    if hud["level"] is not None and "level" not in fixed and asked.get("label") is None and lv.get("label") is None:
        if 1 <= hud["level"] <= 9999:
            lv["label"] = hud["level"]
            _changed(brief, "level.label")
            took.append(f"the HUD's Level {hud['level']}")
            _row(brief, "level", f"the HUD shows Level {hud['level']}, as in the reference", prompt, f)
    if hud["clock_s"] is not None and asked.get("timer_s") is None and gp.get("timer_s") is None:
        mmss = f"{hud['clock_s'] // 60:02d}:{hud['clock_s'] % 60:02d}"
        wish = bool(START_TIME_WISH.search(prompt or ""))  # "the same starting time as this video": the request's own
        why = clock_unreachable(hud["clock_s"], brief)
        if not 10 <= hud["clock_s"] <= 300:
            _note(brief, f"the reference's clock ({mmss} at the start) is not used: the game's clock is 10-300 s")
        elif why and not wish:
            _note(brief, f"the reference's clock ({mmss} at the start) is not used: {why}")
        else:
            gp["timer_s"] = hud["clock_s"]
            _changed(brief, "gameplay.clock")
            took.append(f"the clock at {mmss}")
            _row(brief, "difficulty_pacing", f"the clock starts at {mmss}, as in the reference" + (
                f" (asked; but {why})" if why else ""), prompt, f)
            if why:
                B.adjust(brief, "difficulty_pacing", f"the request asks for the reference's starting clock ({mmss}), but {why}.")
    if took:
        did.append(", ".join(took) + " (the reference is Color Block Jam itself)")
    prov["hud"] = {**hud, "took": took}


CLOSE_UP_SHARE = (0.55, 0.75)  # the board's share of the frame's width: no zoom at the first, the most at the second
ZOOM_STATED = re.compile(r"\bzoom(ed|s)?\b[^.;]{0,20}\d|\b(no|without) zoom\b|\bzoom(ed)? (in|out)\b", re.I)
HUD_STATED = re.compile(r"\b(hide|hidden|no|without|show|showing|keep)\b[^.;]{0,20}\b(hud|clock|timer|level (badge|label|number))\b"
                        r"|\b(hud|clock|timer)\b[^.;]{0,15}\b(hidden|visible|shown|off|on)\b", re.I)
# the request's own cursor ("a hand cursor", "no cursor"); "its cursor", "this ad's cursor" ask for the reference's
CURSOR_STATED = re.compile(r"\b(hand|finger|ring|no|without( a| the)?|hide the|a)\s+(cursor|pointer)\b|\btap ring\b", re.I)


def board_share(a: dict, notes: dict) -> float | None:
    """The board's share of the frame's width at the first frame of play: the box the board's still read gave (a
    measure on the frame), else the reading's own framing.board_share."""
    box = (a.get("board_read") or {}).get("box")
    if isinstance(box, dict) and isinstance(box.get("w"), (int, float)):
        return float(box["w"])
    fr = notes.get("framing") if isinstance(notes.get("framing"), dict) else {}
    v = fr.get("board_share")
    return float(v) if isinstance(v, (int, float)) and 0 < v <= 1 else None


def zoom_for(share: float | None) -> float | None:
    """The camera zoom for a board taking `share` of the frame's width: none at CLOSE_UP_SHARE[0] or less, the most the
    brief allows (brief.ZOOM_RANGE) at CLOSE_UP_SHARE[1] or more, in between in proportion."""
    if share is None:
        return None
    lo, hi = CLOSE_UP_SHARE
    zmin, zmax = B.ZOOM_RANGE
    if share <= lo:
        return None
    k = min(1.0, (share - lo) / (hi - lo))
    return round(zmin + k * (zmax - zmin), 2)


# ---------- the HUD over the board (2026-10-17, the owner's "zoom in closer on the board" on trailer 2) ----------
# The game's HUD bar (the Level badge and the Time pill) is a canvas fixed on screen; FitCamera frames the board to the
# video's aspect and the zoom moves the camera toward the framing's look-at point, so the board's top edge rises under the
# bar. Measured with tests/data/hud_margin.py on 58 of the tool's own 1080x1920 recordings (audit.hud_measure on the first
# frame of play; the HUD's bottom edge, with its outline and badge, is at y 636): the board's top at zoom 1 depends on
# its rows beyond its columns (FitCamera fits the width or the tilted height, whichever is larger), not on the rows alone:
#   rows - cols  -1: y 736-750 (7x6, 9x8)       0: y 708-721 (5x5, 6x6, 7x7, 8x8)     1: y 673-680 (5x6, 6x7, 7x8, 8x9, 9x10)
#                 2: y 627-636 (5x7, 6x8, 7x9)  3: y 567-581, under the HUD (4x7, 5x8)  4: y 523-553, under (4x8, 6x10)
#                 5-6: the top hidden under the bar (4x9, 4x10)
# and the zoom scales about y 1020 (6x6 715 -> 678 and 7x7 711 -> 673 at 1.12, 6x8 633 -> 595 at 1.1: 1013-1027), so the
# top at zoom z is 1020 - (1020 - top) * z; it stays clear of the HUD (within audit.HUD_TOL, 10 px) while
# z <= (1020 - 626) / (1020 - top). The owner's 4x9 at zoom 1.1 measured y 451, 185 px under the bar's bottom edge.
HUD_BOTTOM_Y, ZOOM_CENTRE_Y, HUD_TOL_PX = 636, 1020, 10
SAFE_ZOOM_BY_EXTRA_ROWS = {-1: 1.12, 0: 1.12, 1: 1.1, 2: 1.0}  # rows - columns -> the most zoom with the HUD shown
# (1: 394/347 = 1.135 would leave 5 px under the edge at 1.12, so 1.1, 2 px clear; 2: 394/393 = 1.0)
COVERED_EXTRA_ROWS = 3  # rows - columns from which the HUD covers the top row at zoom 1 already (measured 3, 4, 5, 6)
# rows -> the most zoom with the HUD shown when the columns are not known: the narrowest board the generator builds (4
# columns) is the worst case, so rows - 4 is looked up above
SAFE_ZOOM_BY_ROWS = {4: 1.12, 5: 1.1, 6: 1.0, 7: 1.0, 8: 1.0, 9: 1.0, 10: 1.0}
ZOOM_IN = re.compile(r"\bzoom(ed|s|ing)?\b(?!\s*out)|\bcloser\b|\bclose[- ]?ups?\b|\bfill(s|ing)? the (screen|frame)\b|"
                     r"\btight(er)? (crop|fram\w*|shot)\b", re.I)
HUD_WORDS = re.compile(r"\b(hud|clock|timer|level (badge|label|number)|interface|on[- ]screen|its screen|the same screen)\b", re.I)


def zoom_stated(prompt: str) -> bool:
    """The request states the zoom itself ("zoom in", "closer", "close-up", "fill the screen", "zoom 1.1")."""
    return bool(ZOOM_STATED.search(prompt or "") or ZOOM_IN.search(prompt or ""))


def hud_asked(prompt: str) -> bool:
    """The request names the HUD (the clock, the timer, the level badge, the HUD, what is on screen) or the seconds on
    the clock: the HUD is asked, never hidden for a zoom (the zoom is capped instead)."""
    from . import audit
    if HUD_STATED.search(prompt or "") or HUD_WORDS.search(prompt or ""):
        return True
    a = audit.asked(prompt or "")
    return a.get("clock_left_s") is not None or a.get("timer_s") is not None


def safe_zoom(columns: int | None, rows: int | None) -> tuple[float | None, bool | None]:
    """(the most zoom that keeps the board's top row clear of the HUD, whether the HUD covers it at zoom 1 already) for a
    board of `columns` x `rows` (SAFE_ZOOM_BY_EXTRA_ROWS); with the rows alone, SAFE_ZOOM_BY_ROWS and covered unknown;
    (None, None) when the rows are not known."""
    if not isinstance(rows, int):
        return None, None
    if isinstance(columns, int):
        extra = rows - columns
        if extra >= COVERED_EXTRA_ROWS:
            return 1.0, True
        return SAFE_ZOOM_BY_EXTRA_ROWS.get(max(-1, extra), B.ZOOM_RANGE[1]), False
    return SAFE_ZOOM_BY_ROWS.get(min(10, max(4, rows)), 1.0), None


def hud_clear(brief: dict, prompt: str, did: list | None = None) -> str | None:
    """The board's top row is never under the HUD (video workflow, 2026-10-17: "zoom in closer" took zoom 1.1 and the HUD
    filled from the reference covered a 4x9 board's top row). With the HUD shown and the zoom over safe_zoom (or a board
    the HUD covers at zoom 1): the request's own words win over a filled value (R3). A zoom the request states with a HUD
    it does not ask for (hud_asked): the HUD is hidden. A HUD the request asks for: the zoom is capped at the safe zoom
    (at zoom 1 nothing is left: the game's framing, said). Neither asked (the reference's or the plan's zoom, the
    reference's or the default HUD): the zoom is capped, and the HUD hidden when even zoom 1 covers the row. A board size
    not known at plan time (a generated "any" size) takes the most conservative cap, 1, when the zoom is stated. Records
    brief.reference.hud_clear; returns the line (also in the assumptions and the visuals row), or None."""
    vs, lv = brief["visuals"], brief["level"]
    if not (vs.get("hud_level") or vs.get("hud_timer")):
        return None
    z = float(vs.get("camera_zoom") or 1.0)
    cols, rows = _int(lv.get("width")), _int(lv.get("height"))
    if lv.get("source") not in (None, "auto", "generate", "picture"):
        cols = rows = None  # a shipped level's size is not in the brief
    safe, at1 = safe_zoom(cols, rows)
    stated_zoom = zoom_stated(prompt)
    unknown = safe is None
    if unknown:
        if not (stated_zoom and z > 1.0 + 1e-6):
            return None
        safe = 1.0
    over = z > safe + 1e-6
    if not over and not at1:
        return None
    size = (f"a {cols}x{rows} board" if cols and rows else f"a board of {rows} rows" if rows else
            "a board whose size is generated later (the most conservative cap, 1)")
    asked = hud_asked(prompt)
    prov = brief.get("reference") if isinstance(brief.get("reference"), dict) else {}
    from_ref = bool((prov.get("hud") or {}).get("cbj")) or "screen" in (prov.get("filled") or []) or \
        (prov.get("screen") or {}).get("hud_level") is not None
    hud_src = "the reference" if from_ref else "the game's default"
    line = None
    if stated_zoom and not asked and over:
        vs["hud_level"] = vs["hud_timer"] = False
        _changed(brief, "visuals.hud")
        line = (f"the HUD is hidden: the closer zoom would put it over the board's top row; the request asked for the zoom, "
                f"the HUD came from {hud_src} ({size}: zoom {z:g}, at most {safe:g} with the HUD shown)")
        action = "hid the HUD"
    elif over:
        new = safe
        vs["camera_zoom"] = None if new <= 1.0 + 1e-6 else new
        _changed(brief, "visuals.zoom")
        why = "the request names the HUD" if asked else f"the HUD ({hud_src}) stays"
        line = (f"the zoom is capped at {new:g}, not {z:g}: {why}, and {size}'s top row would go under it above {new:g} "
                f"(videoref.SAFE_ZOOM_BY_EXTRA_ROWS, measured on the tool's own recordings)")
        action = f"capped the zoom at {new:g}"
        if at1 and not asked:
            vs["hud_level"] = vs["hud_timer"] = False
            _changed(brief, "visuals.hud")
            line += f"; even at zoom 1 the game's framing of {size} puts the HUD over its top row, so the HUD is hidden"
            action += " and hid the HUD"
    elif at1 and not asked:
        vs["hud_level"] = vs["hud_timer"] = False
        _changed(brief, "visuals.hud")
        line = (f"the HUD is hidden: the game's framing of {size} puts it over the board's top row even at zoom 1 (measured "
                f"on the tool's own recordings); the request does not ask for the HUD, it came from {hud_src}")
        action = "hid the HUD"
    else:
        line = (f"the HUD stays as asked, though the game's framing of {size} puts it over the board's top row at zoom 1 "
                f"(CreativeRunner.FitCamera frames the board, not a brief field)")
        action = "none: the HUD is asked and the zoom is the game's own"
    if isinstance(brief.get("reference"), dict) and isinstance(brief["reference"].get("screen"), dict):
        brief["reference"]["screen"].update(zoom=vs.get("camera_zoom"), hud_level=vs.get("hud_level"), hud_timer=vs.get("hud_timer"))
    if isinstance(brief.get("reference"), dict):
        brief["reference"]["hud_clear"] = {"zoom": z, "safe": safe, "size": [cols, rows], "covered_at_1": at1,
                                           "zoom_stated": stated_zoom, "hud_asked": asked, "action": action,
                                           "size_known": not unknown}
    _note(brief, line)
    row = B.control(brief, "visuals")
    if line not in (row.get("plan") or ""):
        row["plan"] = f"{row['plan']} {line[0].upper() + line[1:]}.".strip() if row.get("plan") else line[0].upper() + line[1:] + "."
    if did is not None:
        did.append(line)
    if not vs.get("hud_timer") and brief["gameplay"]["ending"] in ("near_fail", "time_out"):
        hidden_clock_captions(brief, prompt)
    return line


HAND_SEEN = re.compile(r"\b(hand|finger|pointer)\b|\bcursor\b", re.I)
CURSOR_WORDS = re.compile(r"\b(cursor|pointer)s?\b|\btap ring\b", re.I)
SCREEN_WIDE = re.compile(r"\b(framing|framed|camera|close[- ]?ups?|zoom\w*|on[- ]screen|screen|hud|interface|timer|clock|"
                         r"level (badge|number))\b", re.I)


def cursor_only(prompt: str) -> bool:
    """The request names the reference's cursor and nothing else of its screen ("Use this ad's hook and its cursor", round
    2 case 14): the cursor is taken, the zoom and the HUD are left as they are."""
    return bool(CURSOR_WORDS.search(prompt or "")) and not SCREEN_WIDE.search(prompt or "")


def _apply_screen(brief: dict, prompt: str, a: dict, notes: dict, fixed: set, did: list, prov: dict) -> None:
    """What the reference shows on screen (round 2, case 09: "keep this video's camera framing, what it shows on screen"
    on trailer 3, a close-up with no HUD, kept the HUD and no zoom): the camera zoom from the board's share of the frame
    (as close as brief.ZOOM_RANGE allows), the HUD's level badge and clock shown or hidden as the reference shows them,
    the cursor from what is seen (the game's hand, or none), each only where the request does not state it. With the
    clock hidden, a near-fail's or a time-out's seconds are carried by a caption."""
    vs, gp, cc, f = brief["visuals"], brief["gameplay"], brief["concept"], a["file"]
    words = prompt or ""
    took = []
    just_cursor = cursor_only(words)
    if not ZOOM_STATED.search(words) and not just_cursor:
        z = zoom_for(board_share(a, notes))
        if z and z > B.ZOOM_RANGE[0] and vs.get("camera_zoom") != z:
            vs["camera_zoom"] = z
            _changed(brief, "visuals.zoom")
            took.append(f"a zoom of {z:g} (the board fills {board_share(a, notes):.0%} of the reference's width)")
    hud = notes.get("hud") if isinstance(notes.get("hud"), dict) else None
    if hud is not None and not HUD_STATED.search(words) and not just_cursor:
        level_on = bool(str(hud.get("level") or "").strip()) or any(LEVEL_LABEL.search(str(x)) for x in notes.get("screen_text") or [])
        clock_on = bool(_clock_s(hud.get("clock")))
        if (vs.get("hud_level"), vs.get("hud_timer")) != (level_on, clock_on):
            vs["hud_level"], vs["hud_timer"] = level_on, clock_on
            _changed(brief, "visuals.hud")
            took.append("no HUD" if not (level_on or clock_on) else
                        f"the HUD as the reference shows it ({'level' if level_on else 'no level'}, {'clock' if clock_on else 'no clock'})")
    fr = notes.get("framing") if isinstance(notes.get("framing"), dict) else {}
    hand = fr.get("hand_cursor") if isinstance(fr.get("hand_cursor"), bool) else None
    if hand is None:  # no framing answer (a reading before the framing question): a hand the reader listed as seen
        seen = [str(x) for x in (notes.get("extras_seen") or []) + ((a.get("board_read") or {}).get("extras_seen") or [])]
        hand = True if any(HAND_SEEN.search(x) for x in seen) else None
    if hand is not None and not CURSOR_STATED.search(words):
        cur = "hand" if hand else "none"
        if vs.get("cursor") != cur:
            vs["cursor"] = cur
            _changed(brief, "visuals.cursor")
            took.append("the hand cursor" if cur == "hand" else "no cursor")
    if not took:
        return
    did.append("the screen: " + ", ".join(took))
    _row(brief, "visuals", "the screen as the reference: " + ", ".join(took), prompt, f)
    prov["screen"] = {"share": board_share(a, notes), "zoom": vs.get("camera_zoom"), "hud_level": vs.get("hud_level"),
                      "hud_timer": vs.get("hud_timer"), "cursor": vs.get("cursor")}
    if not vs.get("hud_timer") and gp["ending"] in ("near_fail", "time_out"):
        hidden_clock_captions(brief, prompt)


HURRY_WORD = "Hurry!"


def one_line(options: list[str], style: str = "title_l") -> str:
    """The first text that fits one line of the caption's style in the safe width (round 2 rerun, case 09: "Phew! 2
    seconds left!" wrapped to two lines on the result screen, was moved up 41 px and sat on the game's "+50" button);
    the measure is the compositor's own (draw.wrap, ad.STYLES, ad.BAND), read, never changed. The last option when none
    fits."""
    from .ad import BAND, STYLES
    from .draw import wrap
    size = STYLES[style]
    width = int(BAND["max_w"] / 1.05) - 2 * max(2, size // 9)
    return next((o for o in options if len(wrap(o, size, width)) == 1), options[-1])


def hidden_clock_captions(brief: dict, prompt: str) -> list[str]:
    """With the clock hidden, captions carry a near-fail's or a time-out's seconds (round 2, case 09). ad.py shows the
    hurry caption from the clock's 5 s to the last drag's start, often under a second (0.93 s in case 09's first take),
    and leaves out a caption it cannot read in that time: "2 seconds left!" (1.3 s to read) never appeared. So the hurry
    caption is the one word "Hurry!" (0.8 s), and the seconds go on the result caption, which the result screen holds
    for 2.5 s: "Phew! 2 seconds left!" (a time-out: "Out of time!"). A caption the request quotes is its own. Returns
    the notes."""
    gp, cc = brief["gameplay"], brief["concept"]
    n = gp.get("clock_left_s") or 2
    seconds = f"{n} second{'s' if n != 1 else ''} left!"
    out = []
    if not _caption_stated(brief, prompt, "hurry") and cc.get("hurry") != HURRY_WORD:
        cc["hurry"] = HURRY_WORD
        _changed(brief, "concept.hurry")
        out.append(f"the hurry caption is \"{HURRY_WORD}\": ad.py shows it only from the clock's 5 s to the last drag, "
                   f"often under a second, too short for a longer line")
    want = one_line([f"Phew! {seconds}", f"Phew! {n} s left!", f"{n} s left!"]) if gp["ending"] == "near_fail" else "Out of time!"
    have = str(cc.get("result") or "")
    carries = (str(n) in have and one_line([have, ""]) == have) if gp["ending"] == "near_fail" else bool(FAIL_CLAIM.search(have))
    if not _caption_stated(brief, prompt, "result") and not carries:
        cc["result"] = want
        _changed(brief, "concept.result")
        out.append(f"the clock is hidden as in the reference, so the result caption carries the "
                   f"{gp['ending'].replace('_', '-')}: \"{want}\"")
    for line in out:
        _note(brief, line)
    return out


EXCLUSIVE = re.compile(r"\bonly\b|\bjust the\b|\bnothing else\b|\beverything else is (mine|my own)\b|\bthe rest is (mine|my own)\b",
                       re.I)
FILLED = "filled from the reference (the request left it open)"
STRUCTURE_STATED = {"length", "replay", "end_card", "result_screen", "result_first", "hold"}
LEVEL_STATED = {"shape", "size", "blocks", "moves", "colours", "pieces", "style", "level", "difficulty"}


def open_aspects(prompt: str, a: dict, notes: dict, fixed: set, focus: list) -> list[str]:
    """The aspects the request leaves open, filled from the general reading (round 2, case 14: "Use this ad's hook and
    its cursor, and show the player stuck once" took the hook alone and left the level to the defaults): the board, the
    ending, the flow (structure), and the screen when the reference is Color Block Jam or the request names it; each
    only when the plan's focus does not already cover it, the request states nothing about it (stated()), and the
    request has no "only" / "just the" / "nothing else" / "everything else is mine" wording. The look (the background)
    is never filled: it needs the request's words."""
    if EXCLUSIVE.search(prompt or "") or not focus:
        return []
    out = []
    if not covers(focus, "board") and not covers(focus, "board_colours") and not LEVEL_STATED & fixed:
        out.append("board")
    if not covers(focus, "ending") and "ending" not in fixed:
        out.append("ending")
    if not covers(focus, "structure") and not STRUCTURE_STATED & fixed:
        out.append("structure")
    if not covers(focus, "screen") and hud_of(notes)["cbj"] and not named_screen(prompt) and not (
            ZOOM_STATED.search(prompt or "") or HUD_STATED.search(prompt or "")):
        out.append("screen")
    return out


def named_screen(prompt: str) -> bool:
    """The request's own words name the screen (its cursor, its HUD, its framing): asked, not left open, even when the
    reading plan missed it (round 2, case 14: "its cursor" with a plan focus of the hook alone)."""
    from .reference import focus_words
    return "screen" in focus_words(prompt)["found"]


def _tag_filled(did: list, start: int, aspect: str, focus: list, filled: list) -> int:
    """Marks what an aspect filled from the reference added to the provenance; returns the new mark."""
    if aspect in filled and not covers(focus, aspect):
        for i in range(start, len(did)):
            if FILLED not in did[i]:
                did[i] += f" ({FILLED})"
    return len(did)


def _apply_one(brief: dict, prompt: str, a: dict) -> dict:
    same_text = bool(SAME_TEXT.search(prompt or ""))
    prov = {"file": a["file"], "focus": list(a.get("focus") or []), "level": a.get("level") or "none",
            "analysed_s": a.get("analysed_s") or 0.0, "adapted": [], "set": [],
            "not_copied": list(NOT_COPIED) + ([] if same_text else ["its caption text"]),
            "confidence": a.get("confidence")}
    brief["reference"] = prov
    notes = a.get("notes") if isinstance(a.get("notes"), dict) else {}
    if a.get("error") or a.get("skipped") or not notes:
        prov["not_read"] = a.get("error") or a.get("skipped") or "nothing was read"
        return prov
    facts = a.get("facts") or {}
    if a.get("parts_dropped"):  # per-section validation (2026-10-17): the rest of the reading is still applied
        prov["parts_dropped"] = a["parts_dropped"]
        _note(brief, f"{a['file']}: {a['parts_dropped']}; the rest of the reading (the concept, the board, the ending, the "
                     f"hook, the captions) is used")
    fixed = stated(prompt, (a.get("plan") or {}).get("constraints") or [], video=True)
    asked_length = _asked_length(prompt, (a.get("plan") or {}).get("constraints") or [])
    prov["stated"] = sorted(fixed)
    if "moves" in fixed and relative_moves(prompt):
        prov["moves_asked"] = relative_moves(prompt)  # the play levers keep the planner's count (play_levers)
        if brief["level"].get("moves") is None and RELATIVE_MOVES.search(prompt or ""):
            # the planner gave no number (round 4, case 28: the fill played 10 for "fewer moves"): the count comes from
            # the reading; a cliffhanger's board holds the moves minus the blocks its cut leaves
            n, why = relative_count(prov["moves_asked"], a, notes)
            lv0, gp0 = brief["level"], brief["gameplay"]
            lv0["moves"] = n
            _changed(brief, "level.moves")
            if gp0["ending"] == "cliffhanger" and lv0.get("blocks") is None and "blocks" not in fixed:
                left = gp0.get("blocks_left") or 2
                lv0["blocks"] = min(BLOCKS_RANGE[1], max(BLOCKS_RANGE[0], n - left))
                _changed(brief, "level.blocks")
                why += f"; {lv0['blocks']} blocks (the cliffhanger's cut leaves {left})"
            prov["moves_asked"] = why
            _note(brief, f"the request asks for {why}")
    if asked_length is not None and "length" in fixed:
        # the request's own single length is the brief's before anything is planned on it (R3; round 3, case 18: the
        # play was planned for the plan's 30 s and the ad then made at the asked length)
        want_len = float(min(B.LENGTH_RANGE_S[1], max(B.LENGTH_RANGE_S[0], asked_length)))
        if brief["pacing"]["length_s"] != want_len:
            brief["pacing"]["length_s"] = want_len
            if "pacing.length" not in brief["changed"]:
                brief["changed"].append("pacing.length")
            _note(brief, f"the request asks for {asked_length:g} s, so the ad is planned at {want_len:g} s")
    replay_ending(brief, prompt, fixed)  # a replay the request asks for needs an ending that has one (round 4, case 30)
    if planner_ending(brief):
        fixed.add("ending")  # the planner set the ending from the request's words ("because you asked ...")
    prov["stated"] = sorted(fixed)
    plain_solve(brief, prompt, notes)
    did, focus, f = prov["adapted"], prov["focus"], a["file"]
    segs = _segs(notes)
    gp, pc, sq, cc, lv = (brief[k] for k in ("gameplay", "pacing", "sequence", "concept", "level"))
    # what the request leaves open is filled from the general reading (round 2, case 14): the plan's focus first, then
    # these, each tagged in the provenance and judged as info
    filled = open_aspects(prompt, a, notes, fixed, focus)
    if filled:
        prov["filled"] = filled
    named = ["screen"] if focus and not covers(focus, "screen") and named_screen(prompt) else []
    if named:  # the request names it; the plan missed it: applied as asked
        prov["named"] = named
    use = list(focus) + filled + named
    mark = len(did)

    if covers(use, "ending"):
        want = mapped_ending(notes)
        if want and "ending" in fixed and want != brief["gameplay"]["ending"]:
            _note(brief, f"the reference's {ENDING_WORDS[want]} ending is read, not applied (the request sets its own ending)")
        if want and "ending" not in fixed:
            gp["ending"] = want
            _changed(brief, "gameplay.ending")
            did.append(f"a {ENDING_WORDS[want]} ending")
            _row(brief, "gameplay", f"a {ENDING_WORDS[want]} ending", prompt, f)
            if want == "near_fail" and "difficulty" not in fixed and lv["difficulty"] == "any":
                lv["difficulty"] = "hard"
                _changed(brief, "level.difficulty")
                _row(brief, "difficulty_pacing", "a hard level (a near-fail needs a board where a wrong move is possible)", prompt, f)
        er = notes.get("ending_read") if isinstance(notes.get("ending_read"), dict) else {}
        left = er.get("blocks_left") if isinstance(er.get("blocks_left"), int) else None
        if gp["ending"] == "cliffhanger" and left is not None and left >= BUSY_CUT and "blocks_left" not in fixed:
            # the reference stops mid-level with the board still crowded (round 1, trailer 3; the viewer asked for it):
            # the cut comes with the most blocks left the tool allows
            gp["blocks_left"] = BLOCKS_LEFT_MAX
            _changed(brief, "gameplay.blocks_left")
            did.append(f"the cut with {BLOCKS_LEFT_MAX} blocks left (the reference stops with {left} on the board)")
            _row(brief, "gameplay", f"the cut comes with {BLOCKS_LEFT_MAX} blocks left, the most the game's cliffhanger "
                                    f"allows (the reference stops with {left} still on the board)", prompt, f)
        # the free list of wrong moves is approximate (8 of 12): a concept read or a filled ending takes only the mistake
        # parts, timestamped, at most one (round 3, case 16: trailer 2 has none); a targeted ending read keeps the count
        approximate = a.get("level") != "targeted" or "ending" not in focus or "ending" in filled
        n = mistake_parts(notes) if approximate else mistakes_of(notes)
        if approximate and n == 0 and gp["ending"] in ("near_fail", "time_out"):
            n = None  # no wrong move seen: a near-fail's or a time-out's own wrong move (the ending rule) stays as planned
        if n is not None and "mistakes" not in fixed:
            gp["mistakes"] = n
            _changed(brief, "gameplay.mistakes")
            if n:
                did.append("one wrong move" if n == 1 else f"{n} wrong moves")
                _row(brief, "gameplay", "one wrong move" if n == 1 else f"{n} wrong moves", prompt, f)
        if gp["ending"] in ("win", "near_fail") and "finish" not in fixed and fast_finish(notes):
            gp["finish"] = "streak"
            _changed(brief, "gameplay.finish")
            did.append("a fast finish")
            _row(brief, "gameplay", "a fast finish (the blocks leave one after another)", prompt, f)
    mark = _tag_filled(did, mark, "ending", focus, filled)

    if covers(use, "structure"):
        dur = float(facts.get("duration_s") or 0)
        if dur and "length" not in fixed:
            length = float(min(B.LENGTH_RANGE_S[1], max(B.LENGTH_RANGE_S[0], round(dur))))
            pc["length_s"] = length
            _changed(brief, "pacing.length")
            did.append(f"the length ({length:g} s" + (")" if length == round(dur) else f"; the reference's {dur:g} s brought into the case's 30-60 s)"))
            _row(brief, "difficulty_pacing", f"{length:g} s long", prompt, f)
        repeats = any(s.get("purpose") == "replay" for s in segs) or \
            any(REPEAT.search(f"{s.get('what', '')} {s.get('emphasis', '')}") for s in segs)
        seq = []
        if "replay" not in fixed and repeats and asked_length is not None and asked_length < REPLAY_ROOM_S:
            # a replay needs room (2026-10-16 creative run, case 13: a reference replay and a long play on a 30 s ask
            # overran the length, then the replay was dropped); the engine still adds one when the ad has room
            line = (f"the reference's replay is not taken: the request fixes {asked_length:g} s, too short to be sure a "
                    f"replay fits (the ad adds one when there is room)")
            if line not in brief["assumptions"]:
                brief["assumptions"].append(line)
        elif "replay" not in fixed:
            sq["replay"] = repeats
            _changed(brief, "sequence")
            did.append("a replay (the reference shows a moment twice)" if repeats else "no replay (the reference has none)")
            seq.append("a replay" if repeats else "no replay")
        result = [s for s in segs if s.get("purpose") in ("victory", "fail")]
        held = round(sum(_len(s) for s in result) - GAME_RESULT_S, 1)
        if result and held >= 0.5 and "hold" not in fixed:
            sq["hold_s"] = min(HOLD_MAX_S, held)
            _changed(brief, "sequence.timing")
            did.append(f"a held result ({sum(_len(s) for s in result):g} s in the reference)")
            seq.append(f"the result held {sq['hold_s']:g} s")
        ends = [s for s in segs if s.get("purpose") == "end_card"]
        cta = str(notes.get("cta") or "").strip() or "cta" in caption_functions(notes)
        if (ends or cta) and "end_card" not in fixed:
            sq["end_card"] = True
            _changed(brief, "sequence")
            seq.append("an end card")
        groups = []
        hook = sum(_len(s) for s in segs if s.get("purpose") == "hook")
        if hook:
            groups.append(f"{hook:g} s hook")
        if any(s.get("purpose") in ("gameplay", "mistake", "near_fail") for s in segs):
            groups.append("play")
        if result:
            groups.append("result")
        if ends:
            groups.append(f"{sum(_len(s) for s in ends):g} s end card")
        if groups:
            did.append(f"the parts' lengths ({', '.join(groups)})")
        if seq:
            _row(brief, "sequence", ", ".join(seq), prompt, f)

    mark = _tag_filled(did, mark, "structure", focus, filled)

    pace_target = None
    if covers(focus, "pacing"):
        from .audit import pacing_asked
        tempo = str(notes.get("pacing") or "").strip().lower()  # computed from the moves counted (reference.pacing_from)
        change, source = pace_change_of(a)
        took = []
        # the pacing is applied only when the request asks about it (round 2, case 03: a concept read took the
        # reference's approximate "slows down", and the ad's own Pacing curve check then failed on a request that never
        # asked about the pacing); the pure-play rule's calm tempo is a structural device and stays
        asked_pace = pacing_asked(prompt, a)
        if asked_pace and tempo in ("calm", "normal", "fast") and "tempo" not in fixed:
            pace_target = target_dps(a, tempo)
            pc["tempo"] = tempo  # the levers below may change it to reach the reference's drags a second
            _changed(brief, "pacing.tempo")
            took.append(tempo)
        if asked_pace and change and "curve" not in fixed:
            pc["curve"] = {"speeds up": "speeds_up", "slows down": "slows_down", "even": "even"}[change]
            _changed(brief, "pacing.curve")
            took.append(change + {"motion": " (measured on the gameplay)"}.get(source, ""))
        if took:
            did.append(f"the pacing ({', '.join(took)})")
            _row(brief, "difficulty_pacing", f"the pacing {', '.join(took)}", prompt, f)
            line = "the pacing was read approximately from a sampled reference"
            if line not in brief["assumptions"]:
                brief["assumptions"].append(line)
        elif not asked_pace and (tempo or change):
            _note(brief, f"the reference's pacing ({tempo or '?'}, {change or '?'}) is read but not applied: the request "
                         f"does not ask about the pacing, and a sampled reading gets it only approximately")
        dur = float(facts.get("duration_s") or 0)
        play = max([_len(s) for s in segs if s.get("purpose") == "gameplay"] or [0.0])
        long_play = dur and play / dur >= LONG_PLAY and "moves" not in fixed and lv.get("moves") is None and \
            lv.get("blocks") is None and pace_target is None and (fill_kind(brief, a, segs) is None or not covers(use, "structure"))
        # an asked pacing, or a reference whose play fills the ad, sets the moves with the play levers instead
        if long_play and "length" in fixed:
            # the request's own length wins: more moves would overrun it (case 13)
            line = f"the reference's long play is not taken: the request fixes {asked_length or pc['length_s']:g} s"
            if line not in brief["assumptions"]:
                brief["assumptions"].append(line)
        elif long_play:
            from .generate import _target_drags
            lv["moves"] = min(16, _target_drags(brief) + 2)
            _changed(brief, "level.moves")
            did.append(f"a long play (one gameplay part is {play / dur:.0%} of the reference: {lv['moves']} moves)")

    mark = len(did)
    if covers(use, "structure"):
        _pure_play(brief, prompt, a, segs, fixed, did, prov)
    mark = _tag_filled(did, mark, "structure", focus, filled)

    copied = _copy_board(brief, prompt, a, fixed, did, prov) if a.get("cells_copy") else False
    if copied:
        _apply_hud(brief, prompt, a, notes, fixed, did, prov)
        line = copied_board_pace(brief, prompt, fixed, prov)
        if line:
            did.append(line)
    elif covers(use, "board"):
        _apply_board(brief, prompt, a, notes, fixed, did, prov)
        _apply_hud(brief, prompt, a, notes, fixed, did, prov)
    elif covers(use, "board_colours"):
        _apply_board_colours(brief, prompt, a, notes, fixed, did, prov)
    mark = _tag_filled(did, mark, "board", focus, filled)

    line = breathe(brief, prompt)  # the request's own moment for the result, before the play's seconds are counted
    if line:
        did.append(line)

    # the play: one decision for the tempo and the moves (the pacing taken, or a reference whose play fills the ad),
    # after the board and the flow, which it needs
    fills = covers(use, "structure") and fill_kind(brief, a, segs) is not None
    # every guided creative gets the play decision (round 4, case 29: a screen, look and colours read made no play
    # decision; a 40 s win played 20.6 s and studio filled it with an 11 s slow replay): with no pace taken, the play
    # seconds for the brief's length are filled with moves and blocks, before studio's own filling (R6, case p.2)
    fill_all = pace_target is None and not fills and lv.get("source") in (None, "auto", "generate") and "level" not in fixed \
        and bool(focus)  # a plan that takes nothing from the clip ("ignore the clip") changes nothing
    if pace_target is not None or fills or fill_all:
        bd = board_of(notes) if covers(use, "board") else None
        read_size = (bd["columns"], bd["rows"]) if bd and bd.get("columns") and bd.get("rows") else None
        replay_off = None
        ref_repeats = any(s.get("purpose") == "replay" or REPEAT.search(f"{s.get('what', '')} {s.get('emphasis', '')}")
                          for s in segs)
        if fill_all and "replay" not in fixed and sq.get("replay") and not ref_repeats:
            # a replay neither the request nor the reference has stays off while the play can fill
            replay_off, sq["replay"] = sq["replay"], False
        state = lever_state(brief)
        line, rec = play_levers(brief, fixed, segs, rate=pace_target, read_size=read_size)
        if replay_off is not None and rec["expected_s"] < rec["target_s"] - 1.5:
            _restore_levers(brief, state)  # the play cannot fill: the replay comes back and the levers run again
            sq = brief["sequence"]
            sq["replay"] = replay_off
            line, rec = play_levers(brief, fixed, segs, rate=pace_target, read_size=read_size)
            line += "; the replay stays: the play cannot fill the ad without it"
        elif replay_off is not None:
            _changed(brief, "sequence")
            line += "; no replay (the request and the reference have none, and the play fills the ad)"
        # the length from the play (round 3): with no single length stated, a play the levers cannot stretch to the
        # length shortens the ad instead of growing the end card
        line, rec = fit_length(brief, fixed, segs, line, rec, state, rate=pace_target, read_size=read_size)
        gp, pc, sq, cc, lv = (brief[k] for k in ("gameplay", "pacing", "sequence", "concept", "level"))
        if rec.get("length") and isinstance(prov.get("stretched"), dict):
            prov["stretched"]["ad_s"] = pc["length_s"]
        prov["play"] = rec
        if pace_target is None and "structure" in filled:
            line += f" ({FILLED})"
        did.append(line)
        _row(brief, "difficulty_pacing", line, prompt, f)

    hook_set = False
    if covers(focus, "hook"):
        fn = hook_function(notes)
        kind = hook_kind(notes)
        if kind:
            prov["hook_kind"] = kind
        if kind == "gameplay" and not _caption_stated(brief, prompt, "hook"):
            # the reference opens on the play itself: no still opening; the hand is the screen's (named or filled);
            # ad.py keeps a hook caption on frame 0 (the poster), which the brief cannot remove
            if "intro" not in fixed and sq.get("intro_s") != 0.0:
                sq["intro_s"] = 0.0
                _changed(brief, "sequence.timing")
            line = ("the hook's kind: the play from the first frame, as the reference opens on the board with no caption "
                    "(no still opening; the ad keeps its own hook caption on frame 0, which ad.py always draws)")
            did.append(line)
            _row(brief, "concept", line, prompt, f)
        if fn and not _caption_stated(brief, prompt, "hook"):
            theirs = next((str(c) for s in segs if s.get("purpose") == "hook" for c in s.get("captions") or []), None)
            from .ad import copy_problems
            cc["hook"] = theirs if same_text and theirs and not copy_problems(theirs) else hook_line(fn, gp["ending"])
            _changed(brief, "concept.hook")
            did.append(HOOK_WORDS[fn])
            _row(brief, "concept", f"{HOOK_WORDS[fn]}, as \"{cc['hook']}\"", prompt, f)
            hook_set = True

    if covers(focus, "captions"):
        from .ad import copy_problems
        fns = caption_functions(notes)
        took = []
        for fn, theirs in fns.items():
            fld = FIELD_OF[fn]
            if (fld == "hook" and hook_set) or _caption_stated(brief, prompt, fld):
                continue
            if "no_captions" in fixed and fld in ("mistake", "fix", "hurry", "result"):
                continue
            own = OWN_LINES.get(fn) if fn != "challenge" else hook_line(hook_function(notes) or "challenge", gp["ending"])
            if isinstance(own, dict):
                own = own.get(gp["ending"])
            line = theirs if same_text and not copy_problems(theirs) else own
            if not line:
                continue
            cc[fld] = line
            _changed(brief, f"concept.{fld}")
            took.append(fn)
        if took:
            words = "the reference's own words, as asked" if same_text else "the tool's own words"
            did.append(f"the captions' functions ({', '.join(took)}) in {words}")
            _row(brief, "concept", f"a caption for each function the reference has ({', '.join(took)}), in {words}", prompt, f)

    mark = len(did)
    if covers(use, "screen"):
        _apply_screen(brief, prompt, a, notes, fixed, did, prov)
    mark = _tag_filled(did, mark, "screen", focus, filled)

    # the board's top row clear of the HUD (2026-10-17), after the board, the play levers (which may grow it) and the screen
    hud_clear(brief, prompt, did)

    line = stuck_step(brief, prompt, fixed)
    if line:
        did.append(line)
        _row(brief, "gameplay", line, prompt, f)

    if "look" in focus:
        from .imageref import style_kit
        cols = [h for h in notes.get("dominant_colours") or [] if isinstance(h, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", h)]
        kit = style_kit({"notes": {"dominant_colours": cols}}, prompt) if cols else None
        vs = brief["visuals"]
        if kit and kit["background"] and "background" not in fixed:
            vs["background"], vs["theme"] = kit["background"], "custom"
            _changed(brief, "visuals.background")
            took = [f"background {kit['background'][0]} to {kit['background'][1]}"]
            if kit.get("captions", True) and "caption_colours" not in fixed:
                vs["caption_fill"], vs["caption_outline"] = kit["caption_fill"], kit["caption_outline"]
                _changed(brief, "visuals.captions")
                took.append(f"captions {kit['caption_fill']} with a {kit['caption_outline']} outline")
            did.append("the palette for the background" + (" and captions" if len(took) > 1 else ""))
            _row(brief, "visuals", "; ".join(took) + "; the blocks keep the game's own colours (never repainted from a video)", prompt, f)
        elif not cols:
            line = f"{f}: no dominant colours were read, so the look stays the game's own"
            if line not in brief["assumptions"]:
                brief["assumptions"].append(line)

    lines, more = mechanic_lines(notes, brief)
    prov["mechanics"] = [x for x in lines if ": not used" not in x]  # the game's own, under the reference's name
    prov["not_used"] = [x for x in lines if ": not used" in x]  # never created, drawn or simulated (2026-10-17)
    prov["not_copied"] += [x for x in more if x not in prov["not_copied"]]
    for line in lines:
        if line not in brief["assumptions"]:
            brief["assumptions"].append(line)
    prov["adapted"] = list(dict.fromkeys(did))
    line = (f"{f} is a reference video read for {focus_text(focus)} ({prov['level']}): "
            + ("adapted " + "; ".join(prov["adapted"]) if prov["adapted"] else "nothing taken that the request did not state itself")
            + "; not copied: " + ", ".join(prov["not_copied"]))
    if line not in brief["assumptions"]:
        brief["assumptions"].append(line)
    return prov
