"""Video-guided creative generation (core requirement 4, REQ4-SPEC-2026-10-16): the reading plan
from the request (2a), the word table, the format step (2b), the composed prompt (2c), the checks in
code (2e), the parts after the understanding (2g), what the focus lets videoref take into the brief
(3), the tool's own creative attached with words (3), the reference evaluation rows (5), and the
guided workflow end to end without the network. No network and no Unity: the planner and the vision
client are fakes; ffmpeg makes the synthetic clips."""
import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from cbj import audit
from cbj import brief as B
from cbj import reference as R
from cbj import videoref as V

FFMPEG = shutil.which("ffmpeg")
needs_ffmpeg = pytest.mark.skipif(not FFMPEG or not shutil.which("ffprobe"), reason="ffmpeg")
PROMPT = "Based on this video, create a Color Block Jam version of this concept."
FACTS = {"file": "reference_clip.mp4", "duration_s": 38.0, "width": 720, "height": 1280, "orientation": "portrait", "size_mb": 6.2}
PLAN = {  # the reading plan of the spec's worked example (3b)
    "focus": ["concept"], "level": "full",
    "questions": ["What is the idea of this ad in one line, and what makes a viewer keep watching?",
                  "What happens in each part, with the seconds: the opening, the play, the moment that goes wrong or gets tense, the payoff, the end card?",
                  "How does it end: a win, a near miss, a fail, or a cut before the end?",
                  "What is the pacing, and does it speed up or slow down?",
                  "What do the captions say and what does each one do (challenge, instruction, urgency, result, call to action)?",
                  "What is the look: the colours, the mood, where the text sits?",
                  "Which mechanics of the other game are shown (name them; they will be translated, not copied)?"],
    "required_fields": ["concept_in_one_line", "structure", "hook", "ending", "pacing", "pace_change", "captions_seen",
                        "dominant_colours", "mechanics_seen", "adaptation"],
    "ignore": ["the other game's characters and art", "its exact caption wording", "its board and pieces"],
    "constraints": [], "why": "the request asks for the concept as a whole, so the reading is full"}
NOTES = {  # the analysis of the worked example (3b), as the model returns it
    "what_it_shows": "a timed block puzzle ad", "game_or_product": "another block puzzle",
    "concept_in_one_line": "a player almost loses a timed block puzzle, then clears it in a rush",
    "how_to_adapt": "a near-fail on a hard board", "hook": "a challenge question over the board",
    "captions_seen": ["Can you solve this?", "Hurry!", "Level complete", "PLAY NOW"],
    "ending": "near-fail", "pacing": "normal", "pace_change": "speeds up", "mood": "tense", "visual_style": "bright cartoon",
    "dominant_colours": ["#FF69B4", "#FFD6EC", "#1D3557"], "cta": "PLAY NOW", "mistakes_shown": True,
    "structure": [
        {"from_s": 0, "to_s": 3, "purpose": "hook", "what": "a question caption over a crowded board", "captions": ["Can you solve this?"], "confidence": 0.9},
        {"from_s": 3, "to_s": 21, "purpose": "gameplay", "what": "steady moves, one piece is dragged the wrong way and bounces", "confidence": 0.8},
        {"from_s": 21, "to_s": 34, "purpose": "near_fail", "what": "the clock turns red, moves get fast", "captions": ["Hurry!"], "confidence": 0.8},
        {"from_s": 34, "to_s": 38, "purpose": "end_card", "what": "the win screen then a Play Now button", "captions": ["Level complete", "PLAY NOW"], "confidence": 0.9}],
    "roles": ["concept"], "mechanics_seen": ["sliding pieces", "a bomb tile that clears neighbours"],
    "adaptation": {"transferable": ["a challenge question at the start", "one wrong move early", "red-clock rush", "a fast finish"],
                   "translation": ["a blocked attempt by a block, then the solve", "a near-fail with two seconds left"],
                   "do_not_copy": ["the other game's pieces and board", "the bomb tile", "its captions' wording", "its frames"]},
    "confidence": 0.78}


class FakePlanner:
    """The planner's text model: a reading plan for the reading-plan schema, a brief for the brief's."""

    def __init__(self, plan=None, brief=None, fail=False):
        self.plan, self.brief, self.fail, self.calls = plan, brief, fail, []
        self.last_model = "fake-planner"

    def complete(self, system, user, schema):
        self.calls.append((system, user, schema))
        if self.fail:
            raise ValueError("no answer")
        if schema is R.PLAN_SCHEMA:
            return self.plan if isinstance(self.plan, str) else json.dumps(self.plan)
        return json.dumps(self.brief or B.default_brief())


class FakeVision:
    """The NVIDIA multimodal model: fixed JSON answers, in order (the last one repeats)."""

    def __init__(self, *answers):
        self.answers, self.asks = list(answers), []
        self.last_model = "fake-omni"

    def describe(self, ask, part, path=None):
        self.asks.append(ask)
        a = self.answers[min(len(self.asks), len(self.answers)) - 1]
        return a if isinstance(a, str) else json.dumps(a)


def _ffmpeg(*args):
    subprocess.run([FFMPEG, "-v", "error", "-y", *args], check=True)


@pytest.fixture(scope="module")
def clips(tmp_path_factory):
    """Synthetic clips: a 6 s test pattern; one with hard cuts at 4 and 9 s (red, blue, green); a 70 s
    pattern; a rotated MOV (a phone's portrait recording); a WebM."""
    if not FFMPEG:
        pytest.skip("ffmpeg")
    d = tmp_path_factory.mktemp("clips")
    _ffmpeg("-f", "lavfi", "-i", "testsrc=size=320x180:rate=10:duration=6", "-c:v", "libx264", "-preset", "ultrafast",
            "-pix_fmt", "yuv420p", str(d / "short.mp4"))
    _ffmpeg("-f", "lavfi", "-i", "color=c=red:s=160x90:d=4", "-f", "lavfi", "-i", "color=c=blue:s=160x90:d=5",
            "-f", "lavfi", "-i", "color=c=green:s=160x90:d=5", "-filter_complex", "[0][1][2]concat=n=3:v=1:a=0",
            "-r", "8", "-pix_fmt", "yuv420p", str(d / "cuts.mp4"))
    _ffmpeg("-f", "lavfi", "-i", "testsrc=size=320x180:rate=10:duration=70", "-c:v", "libx264", "-preset", "ultrafast",
            "-pix_fmt", "yuv420p", str(d / "long.mp4"))
    _ffmpeg("-display_rotation", "90", "-i", str(d / "short.mp4"), "-c", "copy", str(d / "phone.mov"))
    _ffmpeg("-f", "lavfi", "-i", "testsrc=size=320x180:rate=10:duration=8", "-c:v", "libvpx", "-deadline", "realtime",
            "-cpu-used", "8", "-b:v", "300k", str(d / "clip.webm"))
    return d


# ---------- 2a: the reading plan, the word table, the composed prompt ----------

def test_the_reading_plan_writes_the_prompt_the_model_sees():
    planner = FakePlanner(PLAN)
    lines = []
    plan = R.reading_plan(PROMPT, FACTS, planner, lines.append)
    assert plan.source == "planner" and plan.focus == ["concept"] and plan.level == "full"
    system, user, schema = planner.calls[0]
    assert "Do not analyse the video; you cannot see it." in system and schema is R.PLAN_SCHEMA
    assert PROMPT in user and "38 s" in user and "portrait" in user  # the request and the format facts, nothing else
    ask = R.video_ask(plan, FACTS, PROMPT)
    assert f'THE REQUEST this reading serves: "{PROMPT}"' in ask
    # the general reading always (2026-10-17), the plan's questions on top as the user's priorities
    general = ask.split("WHAT TO LOOK FOR (always, the whole reading):")[1].split("THE USER ASKS IN PARTICULAR")[0]
    assert all(f"- {q}" in general for q in R.GENERAL_QUESTIONS)
    asked = ask.split("THE USER ASKS IN PARTICULAR (look for these first, as priorities):")[1].split("IGNORE:")[0]
    assert all(f"- {q}" in asked for q in PLAN["questions"])
    assert "IGNORE: the other game's characters and art; its exact caption wording; its board and pieces." in ask
    assert "the clip is 38.0 s long" in ask and "cuts" not in ask.split("TIME REFERENCE")[1].split("Return")[0]
    assert "REQUIRED: what_it_shows, game_or_product, concept_in_one_line, structure, hook, ending, captions_seen, screen_text, " \
           "hud, framing, board, mechanics_seen, extras_seen, pacing, pace_change, dominant_colours, adaptation, moves_by_third, mistakes, " \
           "mistakes_shown; OPTIONAL: the rest" in ask  # the general fields, the plan's, and those the code reads
    assert f"- {R.BOARD_QUESTION}" in ask and ask.count(R.BOARD_QUESTION) == 1
    # the schema (v2, 2026-10-16): no numbers to copy in the structure example, captions word for word, the game's own text apart
    assert '"from_s": <seconds>, "to_s": <seconds>' in ask and '"from_s": 0, "to_s": 3' not in ask
    assert "the hook part ends when the opening caption leaves the screen" in ask and "letter for letter" in ask
    assert '"screen_text"' in ask and '"moves_by_third"' in ask and '"mistakes": [{"at_s"' in ask
    assert "near-fail (a win with 5 s or less on the clock)" in ask and "replay|payoff|question" in ask
    order = [ask.index(x) for x in ("Never describe how to copy frames", "THE REQUEST", "WHAT TO LOOK FOR", "IGNORE:", "TIME REFERENCE", "REQUIRED:")]
    assert order == sorted(order)


@pytest.mark.parametrize("answer", [
    {"focus": ["dance"], "level": "full", "questions": ["x"], "required_fields": [], "ignore": [], "constraints": [], "why": ""},
    {"focus": ["hook"], "level": "targeted", "questions": [], "required_fields": [], "ignore": [], "constraints": [], "why": ""},
    "not json at all",
    None,  # the planner fails
])
def test_an_invalid_plan_falls_back_to_the_word_table_and_says_so(answer):
    lines = []
    planner = FakePlanner(answer, fail=answer is None)
    plan = R.reading_plan("Use the hook and the pacing of this video.", FACTS, planner, lines.append)
    assert plan.source == "words" and plan.focus == ["hook", "pacing"] and plan.level == "targeted"
    assert any("word table" in x for x in lines) and any("word table" in c for c in plan.checks)


def test_a_valid_plan_wins_outright():
    """2026-10-16 creative run, case 10: the word table added "concept" and "ending" to a correct hook-and-pacing plan.
    A valid plan now wins outright; the word table only logs what it would have read differently."""
    lines = []
    prompt = "Inspired by this video's hook and pacing. A near-fail ending with 3 seconds left, 45 seconds."
    plan = R.reading_plan(prompt, FACTS, FakePlanner({**PLAN, "focus": ["hook", "pacing"], "level": "targeted",
                                                      "required_fields": ["hook", "pacing"]}), lines.append)
    assert plan.focus == ["hook", "pacing"] and plan.level == "targeted" and not any("added" in c for c in plan.checks)
    # the plan lacks a focus the words name: not added, only logged
    lines.clear()
    plan = R.reading_plan("Copy the hook and the pacing of this clip.", FACTS,
                          FakePlanner({**PLAN, "focus": ["hook"], "level": "targeted", "questions": ["How does it open?"],
                                       "required_fields": ["hook"]}), lines.append)
    assert plan.focus == ["hook"] and plan.required_fields == ["hook"]
    assert any("the word table would read the hook and the pacing: the plan wins" in x for x in lines)
    # the plan reads something the words do not: the plan wins, and it is said
    lines.clear()
    plan = R.reading_plan("Use the hook of this clip.", FACTS,
                          FakePlanner({**PLAN, "focus": ["hook", "ending"], "level": "targeted", "required_fields": ["hook", "ending"]}), lines.append)
    assert plan.focus == ["hook", "ending"] and any("the plan wins" in x for x in lines)


@pytest.mark.parametrize("prompt, found", [
    ("Inspired by this video's hook and pacing. A near-fail ending with 3 seconds left, 45 seconds.", ["hook", "pacing"]),
    ("Inspired by this video's captions.", ["captions"]),
    ("Like this video's look.", ["look"]),
    ("Inspired by this video.", ["concept"]),
    ("Take the ending of this video.", ["ending"]),               # the reference's ending
    ("A clean win ending, like this video's pacing.", ["pacing"]),  # the request's own ending is not a focus
    ("End it the way it ends: the payoff.", ["ending"]),
])
def test_the_word_table_reads_whose_hook_and_whose_ending(prompt, found):
    assert R.focus_words(prompt)["found"] == found


@pytest.mark.parametrize("prompt, focus, level", [
    ("Based on this video, create a Color Block Jam version of this concept.", ["concept"], "full"),
    ("Adapt this for our game.", ["concept"], "full"),
    ("Make one like this video.", ["concept"], "full"),
    ("Same idea, our game.", ["concept"], "full"),
    ("Inspired by this video, make an ad.", ["concept"], "full"),
    ("Make an ad.", ["concept"], "full"),  # a video attached with no words about it
    ("Use its hook.", ["hook"], "targeted"),
    ("Take the first seconds and the intro.", ["hook"], "targeted"),
    ("Match the tempo of this, as fast as it is.", ["pacing"], "targeted"),
    ("Use the captions and what it says.", ["captions"], "targeted"),
    ("End it the way it ends: the payoff.", ["ending"], "targeted"),
    ("Take its palette and mood.", ["look"], "targeted"),
    ("Follow the structure and the order of scenes.", ["structure"], "targeted"),
    ("Use the hook and pacing of this video.", ["hook", "pacing"], "targeted"),
])
def test_focus_words(prompt, focus, level):
    w = R.focus_words(prompt)
    assert (w["focus"], w["level"]) == (focus, level)


def test_the_game_name_is_not_talk_about_colours():
    assert R.focus_words("A Color Block Jam ad like this video.")["focus"] == ["concept"]


# ---------- 2b: the format step ----------

@needs_ffmpeg
@pytest.mark.parametrize("name, orientation", [("long.mp4", "landscape"), ("phone.mov", "portrait"), ("clip.webm", "landscape")])
def test_any_format_becomes_one_small_h264_copy_of_the_whole_clip(clips, tmp_path, name, orientation):
    out = tmp_path / "copy.mp4"
    f = R.normalise_video(clips / name, out)
    assert f["analysed_s"] == f["duration_s"] and f["orientation"] == orientation
    assert f["fps"] <= 8 and f["frames"] <= 220 and f["copy"]["codec"] == "h264"
    assert min(f["copy"]["width"], f["copy"]["height"]) == 360
    copy_facts = R.probe_video(out)
    assert copy_facts["orientation"] == orientation and copy_facts["rotation"] == 0  # the rotation applied, not carried
    assert abs(copy_facts["duration_s"] - f["duration_s"]) < 0.6  # the whole clip: no 24 s cut
    if name == "long.mp4":
        assert f["duration_s"] == 70.0 and f["fps"] == R.copy_fps(70.0) < 3


def test_the_copy_frame_rate_keeps_about_200_frames():
    assert R.copy_fps(10) == 8 and R.copy_fps(38) == 5.2 and R.copy_fps(120) == 2
    assert all(R.copy_fps(d) * d <= R.MAX_FRAMES for d in (25, 38, 60, 100))


# ---------- 2e: the checks in code ----------

GOOD = {"structure": [{"from_s": 0, "to_s": 3, "purpose": "hook", "confidence": 0.9},
                      {"from_s": 3, "to_s": 30, "purpose": "Near-fail", "confidence": 0.7},
                      {"from_s": 30, "to_s": 38.3, "purpose": "end_card"}], "confidence": 0.8}


def _bad(i, **kw):
    n = copy.deepcopy(GOOD)
    n["structure"][i].update(kw)
    return n


@pytest.mark.parametrize("notes, words", [
    (_bad(2, to_s=45), "outside the clip"),
    (_bad(0, from_s=-2), "outside the clip"),
    (_bad(1, to_s=2), "not after it starts"),
    ({**GOOD, "structure": [GOOD["structure"][1], GOOD["structure"][0]]}, "not in order"),
    ({**GOOD, "structure": []}, "structure is empty"),
    ({**GOOD, "structure": [{"from_s": "soon", "purpose": "hook"}]}, "structure is empty"),  # no usable part
])
def test_validate_notes_rejects_only_the_time_and_an_empty_structure(notes, words):
    problems = R.validate_notes(notes, {"duration_s": 38.0}, focus=["concept"])
    assert any(words in p for p in problems), problems


def test_the_seconds_must_be_on_the_clips_clock():
    """2026-10-16 creative run, case 10: on a 45 s clip the model answered in the wrong unit (hook 0-0.2 s ... end card
    4.5-45 s); every part was inside the clip and in order, so the reading passed. Now it is asked again."""
    case10 = [{"from_s": 0, "to_s": 0.2, "purpose": "hook"}, {"from_s": 0.3, "to_s": 0.8, "purpose": "gameplay"},
              {"from_s": 0.9, "to_s": 1.0, "purpose": "mistake"}, {"from_s": 1.1, "to_s": 3.2, "purpose": "gameplay"},
              {"from_s": 3.3, "to_s": 3.6, "purpose": "near_fail"}, {"from_s": 3.7, "to_s": 4.0, "purpose": "fail"},
              {"from_s": 4.1, "to_s": 4.4, "purpose": "payoff"}, {"from_s": 4.5, "to_s": 45, "purpose": "end_card"}]
    problems = R.validate_notes({"structure": case10}, {"duration_s": 45.0}, ["hook", "pacing"])
    assert problems and problems[0].startswith("the seconds are not on the clip's clock: the parts before the end card cover 3.8 s of 45 s")
    assert R.validate_notes(NOTES, {"duration_s": 38.0}, ["concept"]) == []  # a normal one passes
    # only the wrong-unit signature (2026-10-17): a long last GAMEPLAY part is valid
    no_card = [{"from_s": 0, "to_s": 2, "purpose": "hook"}, {"from_s": 2, "to_s": 40, "purpose": "gameplay"}]
    assert R.validate_notes({"structure": no_card}, {"duration_s": 45.0}, ["hook"]) == []
    long_other = [{"from_s": 0, "to_s": 2, "purpose": "hook"}, {"from_s": 2, "to_s": 45, "purpose": "result screen"}]
    assert R.validate_notes({"structure": long_other}, {"duration_s": 45.0}, ["hook"])  # a long last result: wrong unit
    assert R.validate_notes({"structure": [{"from_s": 0, "to_s": 0.5, "purpose": "hook"}, {"from_s": 0.5, "to_s": 6, "purpose": "end_card"}]},
                            {"duration_s": 6.0}, ["hook"]) == []  # off for clips under 8 s


def test_validate_notes_passes_a_valid_answer():
    assert R.validate_notes(GOOD, {"duration_s": 38.0}, focus=["concept"]) == []
    assert R.validate_notes({"structure": [], "hook": "x"}, {"duration_s": 38.0}, focus=["hook"]) == []  # a targeted read may leave it
    assert R.validate_notes(NOTES, {"duration_s": 38.0}, focus=["concept"]) == []


def test_a_label_or_a_confidence_never_rejects_a_reading():
    """2026-10-16 live run: confident readings labelled 'identity', 'reveal', 'product info', 'ad_end_card',
    'result', 'mistake & hint', 'tension', 'failure' were rejected twice and the ad planned without them."""
    labels = ["identity", "reveal", "product info", "ad_end_card", "result", "mistake & hint", "tension", "failure", "dance break"]
    notes = {"structure": [{"from_s": 4 * i, "to_s": 4 * i + 4, "purpose": x} for i, x in enumerate(labels)], "confidence": 1.4}
    notes["structure"][0]["confidence"] = -3
    assert R.validate_notes(notes, {"duration_s": 38.0}, focus=["concept"]) == []
    segs = R.structure(notes["structure"], 38)
    assert [s["purpose"] for s in segs] == ["end_card", "victory", "end_card", "end_card", "victory", "mistake", "near_fail", "fail", "other"]
    assert [s["purpose_raw"] for s in segs] == labels and segs[0]["confidence"] == 0.0
    assert "purpose_raw" not in R.structure([{"from_s": 0, "to_s": 2, "purpose": "Near-fail"}])[0]  # only a different label is kept


@pytest.mark.parametrize("label, purpose", [
    ("failure", "fail"), ("lose", "fail"), ("loss", "fail"), ("game over", "fail"), ("out of time", "fail"),
    ("result", "victory"), ("reveal", "victory"), ("win", "victory"), ("won", "victory"), ("success", "victory"),
    ("complete", "victory"), ("Level complete", "victory"),
    ("replay", "replay"), ("slow-mo replay", "replay"), ("shown again", "replay"), ("near_fail|victory replay", "replay"),
    ("payoff", "payoff"), ("satisfying cascade", "payoff"), ("all leave", "payoff"),
    ("question", "question"), ("what would you do?", "question"), ("cliffhanger", "question"), ("hook question", "hook"),
    ("tension", "near_fail"), ("close call", "near_fail"), ("last seconds", "near_fail"), ("almost", "near_fail"), ("Near-fail", "near_fail"),
    ("cta", "end_card"), ("ad_end_card", "end_card"), ("logo", "end_card"), ("identity", "end_card"), ("product info", "end_card"),
    ("brand", "end_card"), ("download", "end_card"), ("play now", "end_card"),
    ("mistake & hint", "mistake"), ("wrong move", "mistake"), ("a wrong turn", "mistake"),
    ("play", "gameplay"), ("level", "gameplay"), ("puzzle", "gameplay"), ("solving", "gameplay"),
    ("hook", "hook"), ("opening", "hook"), ("dance break", "other"), (None, "other"), ("", "other"),
])
def test_purpose_labels_are_mapped(label, purpose):
    assert R.purpose_of(label) == purpose


# ---------- 2g: the parts after the understanding ----------

def _plan(**kw):
    return R.ReadingPlan(**{"focus": ["structure"], "level": "targeted", "questions": ["What are the parts?"],
                            "required_fields": ["structure"], **kw})


@needs_ffmpeg
def test_parts_snap_to_measured_cuts_and_the_model_seconds_are_kept(clips):
    # the first part is play: a 5 s "hook" on a 14 s clip would be split by reference.long_hooks (round 3)
    notes = {"structure": R.structure([{"from_s": 0, "to_s": 5, "purpose": "gameplay", "confidence": 0.9},
                                       {"from_s": 5, "to_s": 10, "purpose": "gameplay", "confidence": 0.9},
                                       {"from_s": 10, "to_s": 12, "purpose": "victory", "confidence": 0.9},
                                       {"from_s": 12, "to_s": 14, "purpose": "end_card", "confidence": 0.9}], 14)}
    facts = {"duration_s": 14.0}
    lines = []
    rec = R.separate_parts(notes, facts, _plan(), clips / "cuts.mp4", log=lines.append)
    assert rec["ran"] and any(3.5 <= c <= 4.5 for c in facts["cuts_s"]) and any(8.5 <= c <= 9.5 for c in facts["cuts_s"])
    b = [(s["from_s"], s["to_s"]) for s in notes["structure"]]
    assert 3.5 <= b[0][1] <= 4.5 and b[0][1] == b[1][0]  # 1 s off a cut: snapped to it
    assert 8.5 <= b[1][1] <= 9.5
    assert b[2][1] == 12 and b[3] == (12, 14)  # 3 s off the nearest cut: kept
    assert [(s["from_s"], s["to_s"]) for s in notes["structure_model"]] == [(0, 5), (5, 10), (10, 12), (12, 14)]
    assert rec["snapped"] == 2 and "pace_change" in facts and any("snapped" in x for x in lines)


def test_snap_moves_only_boundaries_near_a_cut():
    segs = [{"from_s": 0, "to_s": 5, "purpose": "hook"}, {"from_s": 5, "to_s": 20, "purpose": "gameplay"},
            {"from_s": 20, "to_s": 30, "purpose": "end_card"}]
    out, n = R.snap(segs, [4.0, 23.0], 30.0)
    assert [(s["from_s"], s["to_s"]) for s in out] == [(0, 4.0), (4.0, 20), (20, 30)] and n["snapped"] == 1


def test_no_measurement_for_a_concept_read_without_a_pacing_question():
    def measure(_):
        raise AssertionError("no measurement may run")
    notes = {"structure": R.structure(GOOD["structure"], 38)}
    concept = _plan(focus=["concept"], level="full", questions=["What is the idea?"], required_fields=["structure"])
    rec = R.separate_parts(notes, {"duration_s": 38.0}, concept, Path("unused.mp4"), measure=measure)
    assert rec["ran"] is False and "structure_model" not in notes
    # the model's confidence decides nothing (v2): a part read with low confidence does not measure either
    low = {"structure": R.structure([{**GOOD["structure"][0], "confidence": 0.1}] + GOOD["structure"][1:], 38)}
    assert R.separate_parts(low, {"duration_s": 38.0}, concept, Path("x.mp4"), measure=measure)["ran"] is False
    # a pacing question, or the moves counted per third, does measure
    seen = []
    for q, req in (("Does it speed up?", ["structure"]), ("What is the idea?", ["structure", "moves_by_third"])):
        paced = _plan(focus=["concept"], level="full", questions=[q], required_fields=req)
        R.separate_parts({"structure": R.structure(GOOD["structure"], 38)}, {"duration_s": 38.0}, paced, Path("y.mp4"),
                         measure=lambda p: seen.append(p) or {"cuts_s": []})
    assert len(seen) == 2


def test_the_motion_pace_change_is_measured_over_the_gameplay_only():
    """v2: the whole clip said "speeds up" 9 times in 12 because the replay, confetti and end card fill its last
    third; the gameplay parts alone are measured, and the whole clip's value is kept beside it."""
    segs = [{"from_s": 0, "to_s": 3, "purpose": "hook"}, {"from_s": 3, "to_s": 21, "purpose": "gameplay"},
            {"from_s": 21, "to_s": 30, "purpose": "replay"}, {"from_s": 30, "to_s": 38, "purpose": "end_card"}]
    per_s = [5] * 21 + [20] * 17  # even motion while playing, a busy replay and end card
    notes = {"structure": R.structure(segs, 38), "pace_change": "speeds up"}
    facts, lines = {"duration_s": 38.0}, []
    R.separate_parts(notes, facts, _plan(focus=["pacing"]), Path("x.mp4"), log=lines.append,
                     measure=lambda p: {"cuts_s": [], "pace_change": "speeds up", "motion_per_s": per_s})
    assert facts["pace_change"] == "even" and facts["pace_change_clip"] == "speeds up" and facts["pace_change_model"] == "speeds up"
    assert R.gameplay_motion_change(per_s, notes["structure"]) == "even" and any("the gameplay's motion" in x for x in lines)


@pytest.mark.parametrize("counts, tempo, source", [
    ([2, 2, 2], "normal", "counts"),     # 6 moves over 18 s of gameplay: 0.33 a second
    ([1, 1, 2], "calm", "counts"),       # 4 over 18 s: 0.22
    ([4, 4, 4], "fast", "counts"),       # 12 over 18 s: 0.67
    ([10, 10, 10], "fast", "model"),     # 30 over 18 s is not a count (v2 read [10, 10, 10] for 12 drags): the model's word
    ([0, 0, 0], "fast", "model"),        # no move counted: the model's word
])
def test_the_tempo_word_comes_from_plausible_counts_only(counts, tempo, source):
    """v3 (2026-10-16): the counts give the tempo word only when plausible (1 move at least, about 1 a second at most);
    they never give the pace change, which is the motion measured over the gameplay, else the model's word."""
    notes = {"structure": R.structure([{"from_s": 0, "to_s": 3, "purpose": "hook"}, {"from_s": 3, "to_s": 21, "purpose": "gameplay"},
                                       {"from_s": 21, "to_s": 25, "purpose": "replay"}], 25),
             "moves_by_third": counts, "pacing": "fast", "pace_change": "speeds up"}
    p = R.pacing_from(notes, {"pace_change_play": "slows down", "pace_change": "slows down"}, {"ran": True})
    assert (p["gameplay_s"], p["tempo"], p["tempo_source"]) == (18.0, tempo, source)
    assert (p["change"], p["source"]) == ("slows down", "motion")  # never from the counts
    assert ("counts_dropped" in p) == (source == "model")  # said in the log and kept in the analysis
    # no motion measured over the gameplay: the model's own word for the change
    m = R.pacing_from(notes, {"pace_change": "slows down"}, {"ran": False})
    assert (m["change"], m["source"]) == ("speeds up", "model")
    assert R.pace_change_of({"pacing": p}) == ("slows down", "motion")


@pytest.mark.parametrize("text, hud", [
    ("Level 155", True), ("Lv 12", True), ("Time 00:18", True), ("00:09", True), ("0:09", True), ("+50", True), ("+100", True),
    ("REPLAY", True), ("Continue", True), ("Level Completed", True), ("Level Complete", True), ("Level Failed", True),
    ("Out of time!", True), ("Level", True), ("155", True),  # v5: "Level 155" came back as two entries
    ("Phew! 00:02 left", False), ("Color Block Jam", False), ("Cleared with 00:02 left", False),
    ("PLAY NOW", False), ("Can you finish it?", False),
])
def test_the_game_hud_is_told_from_the_ads_captions(text, hud):
    assert bool(R.HUD_TEXT.match(text)) == hud


def test_captions_filed_as_the_games_text_are_moved_back():
    notes = {"captions_seen": ["Can you beat the clock?", "Hurry!"],
             "screen_text": ["Level 28", "Time 00:32", "+50", "REPLAY", "Level Completed", "Phew! 00:02 left", "Color Block Jam",
                             "Cleared with 00:02 left", "PLAY NOW", "hurry!"]}
    moved = R.captions_from_screen_text(notes)
    assert moved == ["Phew! 00:02 left", "Color Block Jam", "Cleared with 00:02 left", "PLAY NOW"]  # in order, no duplicate
    assert notes["captions_seen"] == ["Can you beat the clock?", "Hurry!"] + moved
    assert R.captions_from_screen_text({"screen_text": ["Level 3"]}) == []


# ---------- read_video: the steps together ----------

@needs_ffmpeg
def test_read_video_stores_the_plan_the_prompt_and_the_checks(clips):
    lines = []
    vision = FakeVision({**NOTES, "structure": [{**s, "to_s": min(s["to_s"], 6)} for s in NOTES["structure"][:1]]
                         + [{"from_s": 3, "to_s": 6, "purpose": "gameplay", "confidence": 0.9}]})
    a = R.read_video(clips / "short.mp4", PROMPT, planner=FakePlanner(PLAN), client=vision, log=lines.append,
                     measure=lambda p: {"cuts_s": [], "pace_change": "speeds up"})
    assert not a.get("error"), a.get("error")
    assert a["plan"]["focus"] == ["concept"] and a["ask"] == vision.asks[0] and PROMPT in a["ask"]
    assert (a["focus"], a["level"], a["analysed_s"]) == (["concept"], "full", a["facts"]["duration_s"])
    assert a["validation"]["status"] == "passed" and a["confidence"] == 0.78 and a["separated"]["ran"]
    assert a["read_all"] is True and a["applied"] == ["concept"]
    for words in ("format:", "reading short.mp4 in full; applied to the brief: the concept (full)", "validation: passed",
                  "parts: separated"):
        assert any(words in x for x in lines), words


@needs_ffmpeg
def test_a_reading_with_its_own_labels_is_kept_and_the_model_recorded(clips):
    labelled = {**NOTES, "structure": [{"from_s": 0, "to_s": 2, "purpose": "identity", "confidence": 0.9},
                                       {"from_s": 2, "to_s": 4, "purpose": "tension", "confidence": 0.9},
                                       {"from_s": 4, "to_s": 6, "purpose": "ad_end_card", "confidence": 0.9}]}
    vision = FakeVision(labelled)
    lines = []
    a = R.read_video(clips / "short.mp4", PROMPT, planner=FakePlanner(PLAN), client=vision, log=lines.append,
                     measure=lambda p: {"cuts_s": []})
    # the whole clip, then the board's still (a concept read covers the board; under 12 s the ending is not read again)
    assert not a.get("error") and len(vision.asks) == 2 and a["validation"]["status"] == "passed"
    assert vision.asks[1].startswith("This is one frame, at the first frame of play")
    assert [s["purpose"] for s in a["notes"]["structure"]] == ["end_card", "near_fail", "end_card"]
    assert a["notes"]["structure"][0]["purpose_raw"] == "identity" and a["model"] == "fake-omni"
    assert any("'tension' as near_fail" in x for x in a["validation"]["relabelled"]) and any("labels read" in x for x in lines)


@needs_ffmpeg
def test_read_video_asks_once_more_then_drops_only_the_parts(clips):
    """2026-10-17 (the owner's trailer): validation is per section. Parts that fail the checks after the one re-ask are
    dropped; the concept, the board, the ending, the hook and the captions are kept and applied."""
    bad = {**NOTES, "structure": [{"from_s": 0, "to_s": 50, "purpose": "hook"}]}
    a = R.read_video(clips / "short.mp4", PROMPT, planner=FakePlanner(PLAN), client=FakeVision(bad, NOTES | {"structure": [
        {"from_s": 0, "to_s": 6, "purpose": "gameplay", "confidence": 0.9}]}), measure=lambda p: {"cuts_s": []})
    assert a["validation"]["status"] == "passed after one re-ask" and "outside the clip" in a["validation"]["first"][0]
    vision, lines = FakeVision(bad), []
    a = R.read_video(clips / "short.mp4", PROMPT, planner=FakePlanner(PLAN), client=vision, log=lines.append,
                     measure=lambda p: {"cuts_s": []})
    assert not a.get("error") and a["validation"]["status"] == "passed without the parts" and a["model"] == "fake-omni"
    assert a["parts_dropped"].startswith("the parts were not usable: part 1 (0-50 s) is outside the clip")
    assert a["notes"]["structure"] == [] and a["notes"]["structure_rejected"] == bad["structure"]
    assert a["notes"]["hook"] == NOTES["hook"] and a["notes"]["ending"] == "near-fail"  # the rest is kept
    assert "YOUR LAST ANSWER WAS REJECTED" in vision.asks[1] and "outside the clip" in vision.asks[1]
    assert "the parts were not usable" in R.notes_text(a) and "COULD NOT BE ANALYSED" not in R.notes_text(a)
    assert any("the rest of the reading is kept" in x for x in lines)
    b = _fresh()
    prov = V.apply(b, PROMPT, [a])[0]
    assert b["gameplay"]["ending"] == "near_fail" and b["concept"]["hook"] and prov["parts_dropped"] == a["parts_dropped"]
    assert any("the parts were not usable" in x for x in b["assumptions"])
    low = R.read_video(clips / "short.mp4", PROMPT, planner=FakePlanner(PLAN), client=FakeVision({**NOTES, "confidence": 0.2,
                       "structure": [{"from_s": 0, "to_s": 6, "purpose": "gameplay", "confidence": 0.9}]}), measure=lambda p: {"cuts_s": []})
    assert low["low_confidence"] and not low.get("error") and low["notes"]["hook"]  # shown, and nothing is gated on it
    assert "LOW CONFIDENCE" not in R.notes_text(low)


@needs_ffmpeg
def test_a_request_that_asks_nothing_of_the_video_reads_it_and_applies_nothing(clips):
    """2026-10-17: every reference is read in full; the plan decides what is applied, here nothing."""
    vision = FakeVision({**NOTES, "structure": [{"from_s": 0, "to_s": 6, "purpose": "gameplay"}]})
    a = R.read_video(clips / "short.mp4", "Ignore the clip; make a calm win.", planner=FakePlanner(
        {"focus": [], "level": "none", "questions": [], "required_fields": [], "ignore": ["the clip"], "constraints": [], "why": "ignore it"}),
        client=vision, measure=lambda p: {"cuts_s": []})
    assert a["level"] == "none" and a["read_all"] and a["applied"] == [] and vision.asks and not a.get("skipped")
    assert "THE USER ASKS IN PARTICULAR: nothing beyond the reading above." in vision.asks[0]
    assert "take nothing from it" in R.notes_text(a) and "what a multimodal model saw" not in R.notes_text(a)
    b = _fresh()
    V.apply(b, "Ignore the clip; make a calm win.", [a])
    assert b["gameplay"] == _fresh()["gameplay"] and b["level"] == _fresh()["level"] and b["pacing"] == _fresh()["pacing"]


# ---------- 3: what the focus lets videoref take ----------

TRACKED = ("gameplay.ending", "gameplay.mistakes", "gameplay.finish", "level.difficulty", "level.moves", "pacing.tempo",
           "pacing.curve", "pacing.length_s", "sequence.replay", "sequence.hold_s", "sequence.end_card", "concept.hook",
           "concept.fix", "concept.hurry", "concept.result", "concept.cta", "visuals.background", "visuals.theme",
           "visuals.caption_fill", "visuals.caption_outline", "visuals.blocks")
ALLOWED = {
    "hook": {"concept.hook"},
    "pacing": {"pacing.tempo", "pacing.curve", "level.moves"},
    "captions": {"concept.hook", "concept.fix", "concept.hurry", "concept.result", "concept.cta"},
    "ending": {"gameplay.ending", "gameplay.mistakes", "gameplay.finish", "level.difficulty"},
    "look": {"visuals.background", "visuals.theme", "visuals.caption_fill", "visuals.caption_outline"},
    "structure": {"pacing.length_s", "sequence.replay", "sequence.hold_s", "sequence.end_card"},
}
ALLOWED["concept"] = set().union(*(v for k, v in ALLOWED.items() if k != "look"))
# round 4, case 29 (2026-10-17): every guided creative gets the play decision (the fill), whatever the focus: the tempo,
# the moves and a replay neither the request nor the reference has are the play's, not the focus's
PLAY_FILL = {"level.moves", "pacing.tempo", "sequence.replay"}
for _k in ALLOWED:
    ALLOWED[_k] = ALLOWED[_k] | PLAY_FILL


def _analysis(focus, notes=None, **kw):
    return {"file": "ref.mp4", "kind": "video", "focus": focus, "level": "full" if "concept" in focus else "targeted",
            "analysed_s": 38.0, "facts": {"duration_s": 38.0}, "notes": copy.deepcopy(notes or NOTES), "confidence": 0.78,
            "plan": {"constraints": []}, **kw}


def _get(b, path):
    k1, k2 = path.split(".")
    return b[k1].get(k2)


def _fresh():
    return B.check(B.default_brief())


@pytest.mark.parametrize("focus", ["concept", "hook", "pacing", "captions", "ending", "look", "structure"])
def test_each_focus_changes_only_its_fields(focus):
    b0 = _fresh()
    b = copy.deepcopy(b0)
    # "only": nothing the request leaves open is filled (round 2, case 14: without it the board, the ending and the
    # flow are filled from the reading too: test_what_the_request_leaves_open_is_filled_from_the_reading)
    V.apply(b, f"Use only the {focus} of this video." if focus != "concept" else PROMPT, [_analysis([focus])])
    changed = {p for p in TRACKED if _get(b, p) != _get(b0, p)}
    assert changed and changed <= ALLOWED[focus], changed - ALLOWED[focus]
    assert b["visuals"]["blocks"] == []  # never repainted from a video
    for line in [b["concept"][k] for k in ("hook", "fix", "hurry", "result", "cta") if b["concept"][k]]:
        from cbj.ad import copy_problems
        assert copy_problems(line) == [], line


def test_the_worked_example_becomes_this_brief():
    b = _fresh()
    V.apply(b, PROMPT, [_analysis(["concept"])])
    gp, pc, sq, cc = b["gameplay"], b["pacing"], b["sequence"], b["concept"]
    # a concept read takes the wrong moves from the mistake parts only (round 3, case 16): the worked example has none, so
    # the near-fail's own wrong move (the ending rule's default, None) stays
    assert (gp["ending"], gp["mistakes"], gp["finish"], b["level"]["difficulty"]) == ("near_fail", None, "streak", "hard")
    # the pacing is read but not applied: the request does not ask about it (round 2, case 03); the tempo is the play
    # decision's fill (round 4, case 29), not the reference's
    assert (pc["tempo"], pc["curve"], pc["length_s"]) == (b["reference"]["play"]["tempo"], "even", 38.0)
    assert b["reference"]["play"]["mode"] == "fill"
    assert any(x.startswith("the reference's pacing (normal, speeds up) is read but not applied") for x in b["assumptions"])
    assert cc["hook"] == "Can you clear it in time?" and cc["hook"] != "Can you solve this?"  # own words, never its text
    assert cc["hurry"] and cc["result"] == "Just in time!" and cc["cta"] == "PLAY NOW"
    assert sq["replay"] is False and sq["end_card"] is True
    assert b["visuals"] == _fresh()["visuals"]  # the look was not the focus
    assert b["level"]["moves"] == b["reference"]["play"]["moves"]  # the fill's moves (round 4, case 29)
    long = copy.deepcopy(NOTES)
    long["structure"] = [{"from_s": 0, "to_s": 3, "purpose": "hook"}, {"from_s": 3, "to_s": 30, "purpose": "gameplay"},
                         {"from_s": 30, "to_s": 38, "purpose": "end_card"}]
    b2 = _fresh()
    V.apply(b2, PROMPT, [_analysis(["concept"], long)])
    assert b2["level"]["moves"] and any(x.startswith("a long play") for x in b2["reference"]["adapted"])
    # an asked pacing sets the moves with its levers instead (round 2, case 07)
    b3 = _fresh()
    V.apply(b3, "Use the pacing of this video.", [_analysis(["pacing"], long)])
    assert b3["level"]["moves"] == b3["reference"]["play"]["moves"]
    assert not any(x.startswith("a long play") for x in b3["reference"]["adapted"])
    assert "a bomb tile that clears neighbours: not used: not in Color Block Jam; the ad keeps the game's own near-fail" in b["assumptions"]
    assert "sliding pieces become the game's own drags" in b["assumptions"]


def test_the_request_wins_over_the_reference():
    b = _fresh()
    b["pacing"]["length_s"], b["sequence"]["replay"], b["gameplay"]["ending"] = 45.0, False, "win"
    notes = copy.deepcopy(NOTES)
    notes["structure"][1]["what"] = "the key move, then a slow-motion replay of it"  # the reference repeats a moment
    V.apply(b, "A 45-second version of this concept, no replay, a clean win.", [_analysis(["concept"], notes)])
    assert b["pacing"]["length_s"] == 45.0 and b["sequence"]["replay"] is False and b["gameplay"]["ending"] == "win"
    assert {"length", "replay", "ending"} <= set(b["reference"]["stated"])
    b2 = _fresh()
    V.apply(b2, PROMPT, [_analysis(["concept"], notes)])
    assert b2["sequence"]["replay"] is True  # without the request's words, the repeat gives a replay
    b3 = _fresh()
    b3["concept"]["hook"] = "Only geniuses solve this"
    V.apply(b3, 'Use its hook, but the hook says "Only geniuses solve this".', [_analysis(["hook"])])
    assert b3["concept"]["hook"] == "Only geniuses solve this"


def test_a_long_reference_is_brought_into_30_60_seconds():
    b = _fresh()
    V.apply(b, PROMPT, [{**_analysis(["structure"]), "facts": {"duration_s": 95.0}}])
    assert any("the reference's 95 s brought into the case's 30-60 s" in x for x in b["reference"]["adapted"])
    # the play decision then fits the length to the play (R12; round 4, case 29: it runs for every guided creative)
    rec = b["reference"]["play"]
    assert b["pacing"]["length_s"] == (rec["length"]["to"] if rec.get("length") else 60.0) and 30.0 <= b["pacing"]["length_s"] <= 60.0


@pytest.mark.parametrize("seen, words", [
    # another game's things are never created, drawn or simulated (2026-10-17): "not used", and not copied
    ("ice tiles", "not used: not in Color Block Jam"), ("frozen blocks", "not used: not in Color Block Jam"),
    ("a key and a lock", "not used: not in Color Block Jam"), ("a teleporter", "not used: not in Color Block Jam"),
    ("bubble obstacles with counters", "not used: not in Color Block Jam"),
    ("a bubble sitting on the red gate", "not used: not in Color Block Jam"),  # not the game's gate
    ("match-3 merging", "not used: not in Color Block Jam"), ("a hammer booster", "not used: not in Color Block Jam"),
    ("a level map", "not used: an ad shows one level"), ("chapters", "not used: an ad shows one level"),
    ("sliding pieces", "become the game's own drags"),
    ("fixed walls", "the game's own walls (the board's shape)"),
    # the tool's own grey wall cells as the still read named them (v9, 2026-10-17)
    ("4 dark grey fixed obstacles", "the game's own walls (the board's shape)"), ("grey barriers: 12", "the game's own walls (the board's shape)"),
    ("a stone that breaks", "not used: not in Color Block Jam"), ("dark ice", "not used: not in Color Block Jam"),
    # the game's own screens and HUD (2026-10-16 creative run: these were written up as "not in Color Block Jam")
    ("Level complete screen", "the game's own result screen"), ("level completed screen", "the game's own result screen"),
    ("Level cleared screen", "the game's own result screen"), ("result screen", "the game's own result screen"),
    ("win screen", "the game's own result screen"), ("Out of time screen", "the game's own result screen"),
    ("fail screen", "the game's own result screen"), ("game over screen", "the game's own result screen"),
    ("Level indicator", "the game's own HUD"), ("level number", "the game's own HUD"), ("level label", "the game's own HUD"),
    ("HUD", "the game's own HUD"), ("score counter", "the game's own HUD"), ("coins", "the game's own HUD"),
    ("+50 reward", "the game's own HUD"),
])
def test_the_mechanics_table(seen, words):
    lines, not_copied = V.mechanic_lines({"mechanics_seen": [seen]})
    assert len(lines) == 1 and words in lines[0] and seen in lines[0]
    its = "its " + seen.removeprefix("a ")
    foreign = "not in Color Block Jam" in words
    assert (its in not_copied) == foreign
    # never a line that reads as if the other game's thing were kept (2026-10-17: "a blocked route", "a key move")
    assert not any(w in lines[0] for w in ("blocked route", "key move", "kept as", "recovered by", "cascade of exits"))


@pytest.mark.parametrize("seen, ending, finish, keeps", [
    ("a hammer booster", "near_fail", "auto", "the ad keeps the game's own near-fail"),
    ("a hammer booster", "win", "auto", None),  # the brief has no near-fail: only "not used"
    ("match-3 merging", "win", "streak", "the ad keeps the game's own fast finish"),
    ("match-3 merging", "win", "auto", None),
])
def test_a_mechanics_row_names_only_the_games_own_parameter(seen, ending, finish, keeps):
    b = _fresh()
    b["gameplay"]["ending"], b["gameplay"]["finish"] = ending, finish
    lines, not_copied = V.mechanic_lines({"mechanics_seen": [seen]}, b)
    assert lines[0].startswith(f"{seen}: not used: not in Color Block Jam") and f"its {seen.removeprefix('a ')}" in not_copied
    assert (keeps in lines[0]) if keeps else lines[0] == f"{seen}: not used: not in Color Block Jam"


def test_the_provenance_record():
    b = _fresh()
    V.apply(b, PROMPT, [_analysis(["concept"])])
    ref = b["reference"]
    assert {"file", "focus", "level", "analysed_s", "adapted", "not_copied"} <= set(ref)
    assert (ref["file"], ref["focus"], ref["level"], ref["analysed_s"]) == ("ref.mp4", ["concept"], "full", 38.0)
    for x in ("the challenge hook", "a near-fail ending", "a fast finish", "no replay (the reference has none)"):
        assert x in ref["adapted"], x
    assert not any(x.startswith("the pacing (") for x in ref["adapted"])  # not asked (round 2, case 03)
    assert any(x.startswith("the parts' lengths (3 s hook, play, 4 s end card") for x in ref["adapted"])
    for x in ("the reference's gameplay", "its characters and assets", "its exact frames", "its caption text",
              "its bomb tile that clears neighbours"):
        assert x in ref["not_copied"], x
    b2 = _fresh()
    V.apply(b2, "A version of this concept with the same captions.", [_analysis(["captions"])])
    assert "its caption text" not in b2["reference"]["not_copied"] and b2["concept"]["hurry"] == "Hurry!"
    b3 = _fresh()
    V.apply(b3, PROMPT, [{"file": "ref.mp4", "kind": "video", "error": "the reading failed the checks twice", "focus": ["concept"],
                          "level": "full", "analysed_s": 38.0}])
    assert b3["reference"]["not_read"] and b3["reference"]["adapted"] == [] and b3["gameplay"] == _fresh()["gameplay"]


def test_the_look_guard_keeps_the_game_look_when_the_look_was_not_asked():
    b = _fresh()
    b["visuals"].update(theme="custom", background=["#FFD6EC", "#FF69B4"],
                        blocks=[{"slot": "Red", "hex": "#FF69B4", "name": "pink"}])
    V.apply(b, PROMPT, [_analysis(["concept"])])
    assert b["visuals"]["blocks"] == [] and b["visuals"]["background"] == [] and b["visuals"]["theme"] == "game"
    b = _fresh()
    V.apply(b, "Use the look of this video.", [_analysis(["look"])])
    assert b["visuals"]["background"] and b["visuals"]["theme"] == "custom" and b["visuals"]["blocks"] == []


# ---------- the tool's own creative attached: the words decide ----------

@pytest.mark.parametrize("prompt, want", [
    ("Create a Color Block Jam version of this concept.", "create"),
    ("Same idea, but faster.", "create"),
    ("Inspired by this one, make a new ad; keep it 45 s.", "create"),
    # the live run's reference phrasings (2026-10-16): the tool's own creative attached as inspiration
    ("Take only the hook from this video. Everything else is mine: a clean win on a medium level, 30 seconds, no replay.", "create"),
    ("Match the pacing of this video for a near-fail.", "create"),
    ("End the ad the way this video ends.", "create"),
    ("Take the look and colours of this video for a calm win.", "create"),
    ("Use this video's captions on a new level.", "create"),
    ("Make one like this.", "create"),
    ("A 45-second near-fail ad.", "create"),  # it describes a creative of its own: its length and its ending
    ("Same ad but a blue background.", "edit"),
    ("Keep everything, change the hook to 'Go'.", "edit"),
    ("Replace the music with the attached track.", "edit"),
    ("Keep the concept but change the background.", "edit"),
    ("I like this creative, change the hook to 'Go'.", "edit"),
    ("Make the background blue.", None),
    ("Make it.", None),
])
def test_the_words_decide_what_an_own_creative_is_for(prompt, want):
    from cbj import route
    assert route.upload_intent(prompt) == want


def test_an_own_creative_with_concept_words_is_guided_and_with_edit_words_is_an_edit(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from cbj import app as A
    from cbj import studio
    from test_app import wait
    monkeypatch.setattr(studio, "STUDIO", tmp_path / "studio")
    (tmp_path / "studio" / "uploads").mkdir(parents=True)
    (tmp_path / "studio" / "uploads" / "ours.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64)
    A.JOBS.clear()
    called = []
    monkeypatch.setattr(A.edit_wf, "match", lambda ups: {"creative_id": "c", "n": 2, "file": "c/v2/ad/ad.mp4", "upload": "ours.mp4"})
    monkeypatch.setattr(A.guided_wf, "plan", lambda log, prompt, ups: called.append(("guided", prompt)) or {"planner": {"workflow": "guided"}})
    monkeypatch.setattr(A.edit_wf, "plan", lambda log, prompt, cid, base, ups, matched=None: called.append(("edit", cid, base)) or {"planner": {}})
    client = TestClient(A.app)
    hook_only = "Take only the hook from this video. Everything else is mine: a clean win on a medium level, 30 seconds, no replay."
    for prompt in ("Create a Color Block Jam version of this concept.", "Same ad but a blue background.", hook_only,
                   "Make the background blue."):
        j = wait(client, client.post("/api/plan", json={"prompt": prompt, "uploads": ["ours.mp4"]}).json()["job"])
        assert j["status"] == "done", j.get("error")
    assert called == [("guided", "Create a Color Block Jam version of this concept."), ("edit", "c", 2), ("guided", hook_only),
                      ("edit", "c", 2)]


# ---------- the multimodal models (2026-10-16 live run) ----------

def _client(replies, models=("m1", "m2")):
    """A VisionClient whose calls get the given replies in order: a dict (the API's JSON) or an int (an HTTP error)."""
    import io
    import urllib.error
    c = R.VisionClient(models=models, key="test", max_tokens=4000, long_answers=True)
    c.calls, c.waits = [], []
    c.sleep = c.waits.append
    replies = list(replies)

    def post(body):
        c.calls.append(body)
        r = replies.pop(0)
        if isinstance(r, int):
            raise urllib.error.HTTPError("u", r, "err", {}, io.BytesIO(b"busy"))
        return r
    c._post = post
    return c


def _reply(content, finish="stop"):
    return {"choices": [{"message": {"content": content}, "finish_reason": finish}]}


def test_the_models_are_the_live_ones():
    # the shared client (images, the viewer's review, route.locate_with_vision) keeps the edit side's order and budget
    assert R.VISION_MODELS == ("nvidia/nemotron-3-nano-omni-30b-a3b-reasoning", "nvidia/nemotron-3.5-super-vl-120b-a12b")
    c = R.VisionClient(key="test")
    assert (c.models, c.max_tokens, c.timeout_s, c.long_answers) == (R.VISION_MODELS, 1500, R.TIMEOUT_S, False)
    # only a reference video reads super-vl first, with the long budget and timeout
    assert R.VIDEO_MODELS == ("nvidia/nemotron-3.5-super-vl-120b-a12b", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning")
    assert R.VIDEO_MAX_TOKENS == 8000 and R.VIDEO_TIMEOUT_S == 300 and R.RETRY_WAITS_S == (10, 20, 40)


def test_the_shared_client_behaves_as_before():
    """An empty answer is returned as it is (no budget doubling, no next model), and a broken connection is tried
    once more after 2 s on the same model, as the edit side and the viewer's review had it."""
    import urllib.error
    c = _client([_reply(None, "length")], models=("m1", "m2"))
    c.long_answers = False
    assert c.describe("ask", {}) == "" and len(c.calls) == 1 and c.last_model == "m1"
    c = _client([_reply('{"ok": 1}')])
    c.long_answers = False
    calls = []

    def flaky(body):
        calls.append(body)
        if len(calls) == 1:
            raise urllib.error.URLError("reset")
        return _reply('{"ok": 1}')
    c._post = flaky
    assert c.describe("ask", {}) == '{"ok": 1}' and len(calls) == 2 and c.waits == [2] and c.last_model == "m1"
    assert any("reset" in e for e in c.errors)


def test_an_answer_cut_off_by_the_reasoning_is_asked_again_with_twice_the_budget():
    c = _client([_reply(None, "length"), _reply('{"ok": 1}')])
    assert c.describe("ask", {"type": "text"}) == '{"ok": 1}' and c.last_model == "m1"
    assert [b["max_tokens"] for b in c.calls] == [4000, 8000]
    assert c.calls[1]["messages"][0]["content"][0]["text"].endswith("Answer with the JSON object only.")
    c = _client([_reply(None, "length"), _reply("", "length"), _reply('{"ok": 2}')])  # still cut: the next model
    assert c.describe("ask", {"type": "text"}) == '{"ok": 2}' and c.last_model == "m2"


def test_a_busy_model_is_retried_with_backoff_and_a_gone_one_is_skipped():
    c = _client([503, 429, _reply('{"ok": 1}')])
    assert c.describe("ask", {}) == '{"ok": 1}' and c.waits == [10, 20] and c.last_model == "m1"
    c = _client([503, 503, 503, 503, _reply('{"ok": 2}')])
    assert c.describe("ask", {}) == '{"ok": 2}' and c.waits == [10, 20, 40] and c.last_model == "m2"
    c = _client([410, _reply('{"ok": 3}')])
    assert c.describe("ask", {}) == '{"ok": 3}' and c.waits == [] and c.last_model == "m2"
    c = _client([410, 400])
    with pytest.raises(ValueError, match="HTTP 410.*HTTP 400"):
        c.describe("ask", {})
    assert any("HTTP 410" in e for e in c.errors) and any("HTTP 400" in e for e in c.errors)  # kept for analysis["errors"]


@needs_ffmpeg
def test_a_video_is_read_with_the_video_budget_and_timeout(clips, monkeypatch):
    seen = {}

    def make(**kw):
        seen.update(kw)
        return FakeVision({**NOTES, "structure": [{"from_s": 0, "to_s": 6, "purpose": "gameplay", "confidence": 0.9}]})
    monkeypatch.setattr(R, "VisionClient", make)
    a = R.read_video(clips / "short.mp4", PROMPT, planner=FakePlanner(PLAN), measure=lambda p: {"cuts_s": []})
    # Gemini is unavailable here (tests/conftest.py), so the NVIDIA fallback reads it, with the video budget and order
    assert not a.get("error") and seen == {"models": R.VIDEO_MODELS, "max_tokens": 8000, "timeout_s": 300, "long_answers": True}
    assert a["reader"] == "nvidia" and any(e.startswith("gemini: no GEMINI_API_KEY") for e in a["errors"])


# ---------- 5: the reference rows ----------

def _manifest(**over):
    m = {"duration_s": 38.0,
         "parts": [{"id": "intro", "from_s": 0.0, "to_s": 0.5}, {"id": "play", "from_s": 0.5, "to_s": 31.0},
                   {"id": "result", "from_s": 31.0, "to_s": 33.5}, {"id": "end", "from_s": 33.5, "to_s": 38.0}],
         "layers": [{"id": "hook", "kind": "caption", "text": "Can you clear it in time?", "from_s": 0.0, "to_s": 3.0},
                    {"id": "cap_hurry", "kind": "caption", "text": "Hurry up!", "from_s": 26.0, "to_s": 30.0},
                    {"id": "cap_result", "kind": "caption", "text": "Just in time!", "from_s": 31.3, "to_s": 33.5},
                    {"id": "end_cta", "kind": "caption", "text": "PLAY NOW", "from_s": 33.5, "to_s": 38.0}],
         "moments": [{"id": f"drag_{i}", "kind": "mistake" if i == 1 else "move", "at_s": t}
                     for i, t in enumerate([2.0, 6.0, 12.0, 14.0, 16.5, 19.0, 22.0, 24.0, 26.0, 27.5, 29.0, 30.5])]
                    + [{"id": "win", "kind": "win", "at_s": 30.9}],
         "clock": [{"clock_s": 5, "at_s": 27.0}],
         "gameplay": {"ending": "near_fail"}}
    m.update(over)
    return m


def _guided_brief(focus=("concept",), notes=None, **gp):
    b = _fresh()
    b["gameplay"].update(ending="near_fail", mistakes=1, **gp)
    b["pacing"].update(tempo="normal", curve="speeds_up")
    a = _analysis(list(focus), notes)
    a["notes"]["structure"] = R.structure(a["notes"]["structure"], 38)
    b["planner"] = {"references": [a]}
    b["reference"] = {"file": "ref.mp4", "focus": list(focus), "level": a["level"], "analysed_s": 38.0, "adapted": [],
                      "not_copied": list(V.NOT_COPIED)}
    return b


def _result(gaps_frames):
    """A recording's drags with the given pauses (frames) between them: 20-frame drags."""
    drags, f = [], 30
    for g in [0] + list(gaps_frames):
        f += g
        drags.append({"start_frame": f, "end_frame": f + 20})
        f += 20
    return {"drags": drags}


def _rows(tmp_path, brief, manifest=None, ad=None, prompt=PROMPT, poster=None, result=None):
    rec_dir = None
    if result is not None:
        rec_dir = tmp_path / "rec"
        rec_dir.mkdir(parents=True, exist_ok=True)
        (rec_dir / "result.json").write_text(json.dumps(result))
    vdir = tmp_path / "v1"
    (vdir / "ad").mkdir(parents=True, exist_ok=True)
    (vdir / "parts.json").write_text(json.dumps(manifest or _manifest()))
    (vdir / "ad" / "ad.json").write_text(json.dumps(ad or {"layers": {"hook": {"type": "text", "text": "x"}}}))
    if poster:
        from PIL import Image
        im = Image.new("RGB", (108, 192), poster)
        im.paste((30, 30, 30), (20, 40, 88, 150))
        im.save(vdir / "ad" / "poster.png")
    record = {"checks": [{"check": "Ending", "status": "pass", "detail": "cleared with 00:02 on the clock"}], "length_s": 38.0}
    return {r["check"][len("Reference: "):]: r for r in audit.reference_rows(prompt, brief, record, vdir, rec_dir)}


PACED = PROMPT + " Match its pacing."  # the pacing row is judged only when the request asks about the pacing (v3)


SPEEDS_UP = _result([60, 60, 60, 45, 45, 45, 20, 20, 20])  # the pauses shorten: the play speeds up
EVEN = _result([40] * 9)


def test_reference_rows_pass_on_a_faithful_ad(tmp_path):
    rows = _rows(tmp_path / "a", _guided_brief(), prompt=PACED, result=SPEEDS_UP)
    for k in ("the ending", "the pacing", "the hook", "the purposes in order", "the part lengths", "the captions", "nothing copied"):
        assert rows[k]["status"] == "pass", (k, rows[k])
    assert "read approximately" in rows["the pacing"]["detail"]
    rows = _rows(tmp_path / "b", _guided_brief())  # the request does not ask about the pacing: info, never a miss
    assert rows["the pacing"]["status"] == "info" and "not judged" in rows["the pacing"]["detail"]
    assert rows["the look"]["status"] == "info" and rows["read with confidence"]["status"] == "info"
    assert "0.78" in rows["read with confidence"]["detail"] and "38 s analysed" in rows["read with confidence"]["detail"]
    assert all(r["from"] == "reference" for r in rows.values())


def test_reference_rows_fail_each_once(tmp_path):
    b = _guided_brief()
    b["gameplay"]["ending"] = "win"
    assert _rows(tmp_path / "a", b)["the ending"]["where"] == "plan"
    r = _rows(tmp_path / "b", _guided_brief(), prompt=PACED, result=EVEN)["the pacing"]
    assert r["status"] == "failed" and "average pause 1.33 s in the first third, 1.33 s in the last third" in r["detail"]
    late = _manifest()
    late["layers"][0].update(from_s=5.0, to_s=7.0)
    assert _rows(tmp_path / "c", _guided_brief(), late)["the hook"]["status"] == "failed"
    no_end = _manifest(parts=_manifest()["parts"][:3])
    b = _guided_brief()
    b["sequence"]["end_card"] = False
    r = _rows(tmp_path / "d", b, no_end)["the purposes in order"]
    assert r["status"] == "failed" and r["where"] == "plan"
    long_end = _manifest(duration_s=60.0, parts=_manifest()["parts"][:3] + [{"id": "end", "from_s": 33.5, "to_s": 60.0}])
    r = _rows(tmp_path / "e", _guided_brief(), long_end)["the part lengths"]
    assert r["status"] == "failed" and r["where"] == "plan"
    no_hurry = _manifest(layers=[L for L in _manifest()["layers"] if L["id"] != "cap_hurry"])
    r = _rows(tmp_path / "f", _guided_brief(), no_hurry)["the captions"]
    assert r["status"] == "failed" and "urgency" in r["detail"]
    r = _rows(tmp_path / "g", _guided_brief(), ad={"layers": {"sticker": {"type": "image", "image": "ref.mp4"}}})["nothing copied"]
    assert r["status"] == "failed" and r["where"] == "ad"
    # the look, when it was a focus: the frame's margins against the reference's colours
    look = _guided_brief(focus=("look",))
    look["visuals"].update(background=["#FFD6EC", "#FFB0D8"], caption_fill="#FFFFFF")
    assert _rows(tmp_path / "h", look, poster=(255, 200, 225))["the look"]["status"] == "pass"
    assert _rows(tmp_path / "i", look, poster=(120, 200, 90))["the look"]["status"] == "failed"
    assert _rows(tmp_path / "h", look)["the ending"]["status"] == "info"  # not a focus of a look read


def test_the_guided_evaluation_feeds_the_reference_misses_back(tmp_path):
    b = _guided_brief()
    wf = audit.workflow(b, {"workflow": "guided"})
    assert wf["kind"] == "video" and "reference" in wf["groups"] and "case" in wf["groups"]
    b["gameplay"]["ending"] = "win"
    rows = list(_rows(tmp_path, b).values())
    miss = audit.misses(rows)
    assert [r["check"] for r in miss] == ["Reference: the ending"]
    text = audit.feedback(PROMPT, rows)
    assert "the ending: the reference ends near-fail; the plan says win" in text


# ---------- the guided workflow end to end, without the network ----------

@needs_ffmpeg
def test_guided_plan_reads_the_video_for_the_full_prompt(clips, tmp_path, monkeypatch):
    from cbj import llm, studio
    from cbj.workflows import guided
    monkeypatch.setattr(studio, "STUDIO", tmp_path / "studio")
    (tmp_path / "studio" / "uploads").mkdir(parents=True)
    shutil.copy(clips / "short.mp4", tmp_path / "studio" / "uploads" / "ref.mp4")
    raw = B.default_brief()
    raw["pacing"]["length_s"], raw["changed"] = 40.0, ["pacing.length"]  # the planner reads the request's 40 s
    planner = FakePlanner(PLAN, brief=raw)
    vision = FakeVision({**NOTES, "structure": [{"from_s": 0, "to_s": 2, "purpose": "hook", "captions": ["Can you solve this?"], "confidence": 0.9},
                                                {"from_s": 2, "to_s": 6, "purpose": "near_fail", "what": "the clock turns red", "confidence": 0.9}]})
    monkeypatch.setattr(llm, "planner_client", lambda: planner)
    monkeypatch.setattr(R, "VisionClient", lambda **kw: vision)
    monkeypatch.setattr(R, "video_facts", lambda p, small=None: {"cuts_s": [2.0], "pace_change": "speeds up"})
    prompt = "Based on this video, create a Color Block Jam version of this concept. Keep it 40 seconds."
    lines = []

    class Log:
        def __call__(self, text):
            lines.append(text)

        def begin(self, stage, text):
            lines.append(text)
    b = guided.plan(Log(), prompt, ["ref.mp4"])
    assert prompt in planner.calls[0][1]  # the reading plan receives the full prompt
    a = b["planner"]["references"][0]
    assert a["ask"] == vision.asks[0] and prompt in a["ask"] and a["plan"]["focus"] == ["concept"]
    assert b["planner"]["workflow"] == "guided" and b["reference"]["file"] == "ref.mp4"
    assert b["gameplay"]["ending"] == "near_fail" and b["concept"]["hook"] == "Can you clear it in time?"
    assert b["pacing"]["length_s"] == 40.0 and "length" in b["reference"]["stated"]  # the request's 40 s wins over the clip's length
    for words in ("reading the reference video ref.mp4", "reading ref.mp4 in full; applied to the brief: the concept (full)", "validation: passed",
                  "parts: separated", "reference to creative: ref.mp4"):
        assert any(words in x for x in lines), words



# ---------- v2 (2026-10-16): the schema changes measured on the tool's own creatives ----------

@needs_ffmpeg
def test_read_video_derives_the_mistakes_and_computes_the_pacing(clips):
    notes = {**NOTES, "mistakes": [{"at_s": 1.5, "what": "red stopped by blue"}, {"at_s": 4, "what": "yellow the wrong way"}],
             "moves_by_third": [1, 1, 3], "pacing": "fast", "pace_change": "even", "screen_text": ["Level 28", "00:32"],
             "structure": [{"from_s": 0, "to_s": 1, "purpose": "hook", "confidence": 0.9},
                           {"from_s": 1, "to_s": 6, "purpose": "gameplay", "confidence": 0.9}]}
    notes.pop("mistakes_shown")
    vision = FakeVision(notes)
    vision.errors = ["m0: HTTP 503 busy"]
    a = R.read_video(clips / "short.mp4", PROMPT, planner=FakePlanner(PLAN), client=vision, measure=lambda p: {"cuts_s": []})
    n = a["notes"]
    assert n["mistakes_shown"] is True and V.mistakes_of(n) == 2 and n["mistakes"][1]["at_s"] == 4.0
    # 5 moves over 5 s of gameplay is plausible: the tempo from the counts; no motion measured: the change is the model's
    assert (a["pacing"]["tempo_source"], a["pacing"]["source"]) == ("counts", "model") and (n["pacing"], n["pace_change"]) == ("fast", "even")
    assert (n["pacing_said"], n["pace_change_said"]) == ("fast", "even") and a["errors"] == ["m0: HTTP 503 busy"]
    assert "captions_moved" not in a["validation"] and "Level 28" not in n["captions_seen"]  # the HUD stays screen_text


def test_replay_payoff_and_question_parts_reach_the_brief():
    notes = copy.deepcopy(NOTES)
    notes["structure"] = [{"from_s": 0, "to_s": 2, "purpose": "hook", "captions": ["Can you clear it?"]},
                          {"from_s": 2, "to_s": 25, "purpose": "gameplay"},
                          {"from_s": 25, "to_s": 30, "purpose": "payoff", "what": "the last blocks"},
                          {"from_s": 30, "to_s": 34, "purpose": "replay", "what": "the key move"},
                          {"from_s": 34, "to_s": 38, "purpose": "question", "captions": ["Would you have seen it?"]}]
    notes["ending"] = "none"
    notes["captions_seen"] = ["Can you clear it?", "Would you have seen it?"]
    b = _fresh()
    V.apply(b, PROMPT, [_analysis(["concept"], notes)])
    assert b["gameplay"]["ending"] == "cliffhanger" and b["sequence"]["replay"] is True
    assert V.fast_finish(notes) and V.caption_functions(notes) == {"challenge": "Can you clear it?", "result": "Would you have seen it?"}
    # a near-fail the model saw stays one when a win screen was transcribed; with no screen at all the question wins
    assert V.mapped_ending({**notes, "ending": "near-fail", "captions_seen": notes["captions_seen"] + ["Level Completed"]}) == "near_fail"
    assert V.mapped_ending({**notes, "ending": "near-fail"}) == "cliffhanger"


def test_caption_functions_read_captions_seen_only():
    notes = {"captions_seen": ["Hurry!"], "cta": "PLAY NOW",
             "structure": [{"from_s": 0, "to_s": 3, "purpose": "hook", "captions": ["Level 28", "Time 00:32"]},
                           {"from_s": 3, "to_s": 9, "purpose": "near_fail", "captions": ["Hurry!"]}],
             "screen_text": ["Level 28", "Level Completed", "+50"]}
    assert V.caption_functions(notes) == {"urgency": "Hurry!"}


def test_the_reference_rows_see_the_replay_and_the_question(tmp_path):
    notes = copy.deepcopy(NOTES)
    notes["structure"] = [{"from_s": 0, "to_s": 3, "purpose": "hook"}, {"from_s": 3, "to_s": 30, "purpose": "gameplay"},
                          {"from_s": 30, "to_s": 34, "purpose": "replay"}, {"from_s": 34, "to_s": 38, "purpose": "end_card"}]
    b = _guided_brief(notes=notes)
    m = _manifest(parts=[{"id": "intro", "from_s": 0.0, "to_s": 0.5}, {"id": "play", "from_s": 0.5, "to_s": 28.0},
                         {"id": "replay", "from_s": 28.0, "to_s": 31.0}, {"id": "result", "from_s": 31.0, "to_s": 33.5},
                         {"id": "end", "from_s": 33.5, "to_s": 38.0}])
    r = _rows(tmp_path / "a", b, m)["the purposes in order"]
    assert r["status"] == "pass" and "replay" in r["detail"]
    b["sequence"]["replay"] = False
    no_replay = _manifest()
    r = _rows(tmp_path / "b", b, no_replay)["the purposes in order"]
    assert r["status"] == "failed" and r["where"] == "plan"
    assert audit.ref_part_lengths([{"from_s": 0, "to_s": 4, "purpose": "replay"}, {"from_s": 4, "to_s": 6, "purpose": "question"}]) == \
        {"play": 4.0, "result": 2.0}
    assert audit.ad_part_lengths(m)["play"] == pytest.approx(27.5 - 2.5 + 3.0)



def test_mistakes_count_the_larger_of_the_list_and_the_parts():
    parts = [{"from_s": 0, "to_s": 2, "purpose": "mistake"}, {"from_s": 2, "to_s": 4, "purpose": "mistake"},
             {"from_s": 4, "to_s": 9, "purpose": "gameplay"}]
    assert V.mistakes_of({"mistakes": [{"at_s": 1}], "structure": parts}) == 2
    assert V.mistakes_of({"mistakes": [{"at_s": i} for i in range(5)], "structure": []}) == 3
    # both empty: the model's own yes/no is the backstop (v2's list said none for two cliffhangers with three wrong moves)
    assert V.mistakes_of({"mistakes": [], "structure": [], "mistakes_shown": True}) == 1
    assert V.mistakes_of({"mistakes": [], "structure": [], "mistakes_shown": False}) == 0
    assert V.mistakes_of({"mistakes": [], "structure": []}) == 0 and V.mistakes_of({"structure": []}) is None


@needs_ffmpeg
def test_read_video_moves_end_card_texts_back_and_keeps_the_models_yes_no(clips):
    notes = {**NOTES, "mistakes": [], "mistakes_shown": True, "captions_seen": ["Can you clear it?"],
             "screen_text": ["Level 60", "Time 00:41", "Color Block Jam", "Your move: two blocks to go!", "PLAY NOW", "+50"],
             "structure": [{"from_s": 0, "to_s": 2, "purpose": "hook", "confidence": 0.9},
                           {"from_s": 2, "to_s": 6, "purpose": "gameplay", "confidence": 0.9}]}
    lines = []
    a = R.read_video(clips / "short.mp4", PROMPT, planner=FakePlanner(PLAN), client=FakeVision(notes), log=lines.append,
                     measure=lambda p: {"cuts_s": []})
    n = a["notes"]
    assert a["validation"]["captions_moved"] == ["Color Block Jam", "Your move: two blocks to go!", "PLAY NOW"]
    assert n["captions_seen"] == ["Can you clear it?", "Color Block Jam", "Your move: two blocks to go!", "PLAY NOW"]
    assert n["mistakes_shown"] is True and V.mistakes_of(n) == 1 and any("moved back" in x for x in lines)
    b = _fresh()
    V.apply(b, PROMPT + " Keep its pacing.", [{**_analysis(["concept"], n), "pacing": a["pacing"], "separated": a["separated"]}])
    assert "the pacing was read approximately from a sampled reference" in b["assumptions"]
    b2 = _fresh()
    V.apply(b2, "Use its hook.", [_analysis(["hook"], n)])
    assert "the pacing was read approximately from a sampled reference" not in b2["assumptions"]  # not a focus: nothing taken



@needs_ffmpeg
def test_broken_json_twice_keeps_the_model_and_the_raw_answers(clips):
    """v3 run, 2026-10-16: 2-time-out came back twice as JSON with a missing comma; the reading failed, but the
    analysis said model None and kept nothing to look at."""
    bad = '{"hook": "Can you beat the clock?" "ending": "time-out"}'
    a = R.read_video(clips / "short.mp4", PROMPT, planner=FakePlanner(PLAN), client=FakeVision(bad), measure=lambda p: {"cuts_s": []})
    assert a.get("error") and a["model"] == "fake-omni" and a["raw_answers"] == [bad, bad]
    ok = R.read_video(clips / "short.mp4", PROMPT, planner=FakePlanner(PLAN), client=FakeVision(bad, {**NOTES, "structure": [
        {"from_s": 0, "to_s": 6, "purpose": "gameplay"}]}), measure=lambda p: {"cuts_s": []})
    assert not ok.get("error") and ok["raw_answers"] == [bad]
    good = R.read_video(clips / "short.mp4", PROMPT, planner=FakePlanner(PLAN), client=FakeVision({**NOTES, "structure": [
        {"from_s": 0, "to_s": 6, "purpose": "gameplay"}]}), measure=lambda p: {"cuts_s": []})
    assert "raw_answers" not in good



def _case03():
    """Case 03 of the creative run (2026-10-16): a time-out reference against a time-out ad that has every stage."""
    notes = copy.deepcopy(NOTES)
    notes["ending"] = "time-out"
    notes["structure"] = [{"from_s": 0, "to_s": 3, "purpose": "hook"}, {"from_s": 3, "to_s": 5, "purpose": "mistake"},
                          {"from_s": 5, "to_s": 20, "purpose": "gameplay"}, {"from_s": 20, "to_s": 26, "purpose": "near_fail"},
                          {"from_s": 26, "to_s": 33, "purpose": "replay"}, {"from_s": 33, "to_s": 37, "purpose": "fail"},
                          {"from_s": 37, "to_s": 45, "purpose": "end_card"}]
    b = _guided_brief(notes=notes)
    b["gameplay"]["ending"] = "time_out"
    b["sequence"].update(replay=True, end_card=True)
    m = _manifest(duration_s=45.0, gameplay={"ending": "time_out"},
                  parts=[{"id": "intro", "from_s": 0.0, "to_s": 0.5}, {"id": "play", "from_s": 0.5, "to_s": 27.57},
                         {"id": "replay", "from_s": 27.57, "to_s": 35.23}, {"id": "result", "from_s": 35.23, "to_s": 37.9},
                         {"id": "result_hold", "from_s": 37.9, "to_s": 39.0}, {"id": "end", "from_s": 39.0, "to_s": 45.0}],
                  layers=[{"id": "hook", "kind": "caption", "text": "Can you beat the clock?", "from_s": 0.0, "to_s": 1.9},
                          {"id": "end_cta", "kind": "caption", "text": "PLAY NOW", "from_s": 39.0, "to_s": 45.0}],
                  moments=[{"id": "drag_0", "kind": "mistake", "at_s": 1.53, "also": "wrong_move"},
                           {"id": "drag_1", "kind": "move", "at_s": 5.2}, {"id": "drag_2", "kind": "exit", "at_s": 10.2},
                           {"id": "drag_3", "kind": "short", "at_s": 25.97}, {"id": "time_out", "kind": "time_out", "at_s": 35.23}],
                  clock=[{"clock_s": 6, "at_s": 21.57}, {"clock_s": 5, "at_s": 22.57}, {"clock_s": 4, "at_s": 23.57}])
    return b, m


def test_the_purposes_in_order_skip_the_gameplay_and_see_a_time_outs_last_seconds(tmp_path):
    """2026-10-16 creative run, case 03: the order failed in all three versions and the loop could not fix it, because
    the ad's "gameplay" (emitted at the play's start, before the first drag) came before the reference's opening wrong
    move, and a time-out ad emitted no near-fail although its clock passes 5 s too. Now gameplay is not a stage and a
    time-out's first clock reading of 5 s or under is its near-fail."""
    b, m = _case03()
    have = [p for _, p in audit.ad_purposes(m, b)]
    assert have == ["hook", "gameplay", "mistake", "near_fail", "mistake", "replay", "fail", "end_card"]  # the short drag counts
    r = _rows(tmp_path / "a", b, m)["the purposes in order"]
    assert r["status"] == "pass", r
    assert r["detail"].startswith("the reference: hook -> mistake -> gameplay -> near_fail -> replay -> fail -> end_card; the ad: hook -> gameplay")
    # a reference that wins can still not be matched by an ad that runs out of time
    b2, m2 = _case03()
    b2["planner"]["references"][0]["notes"]["structure"] = R.structure([
        {"from_s": 0, "to_s": 3, "purpose": "hook"}, {"from_s": 3, "to_s": 30, "purpose": "victory"},
        {"from_s": 30, "to_s": 45, "purpose": "end_card"}], 38)
    r2 = _rows(tmp_path / "b", b2, m2)["the purposes in order"]
    assert r2["status"] == "failed" and "victory" in r2["detail"]
    assert audit._stages(["hook", "gameplay", "mistake", "gameplay", "mistake", "end_card"]) == ["hook", "mistake", "end_card"]



def test_case_06_asks_about_the_pace_and_states_no_tempo():
    """2026-10-16 creative run, case 06: "the pacing of this video: how fast the moves come" was read as a stated tempo,
    so the reference's tempo was not taken and the planner's own "calm" stood."""
    s = V.stated("Match the pacing of this video: how fast the moves come and how it builds. A clean win, 45 seconds.")
    assert "tempo" not in s and {"ending", "length"} <= s
    for said in ("the pacing is fast", "fast pacing", "a calm tempo", "fast-paced", "tempo: slow"):
        assert "tempo" in V.stated(said), said
    for asked in ("how slow it starts", "match the pace of this clip", "how fast the blocks go"):
        assert "tempo" not in V.stated(asked), asked


def test_the_reference_pacing_row_and_the_pacing_curve_check_agree(tmp_path):
    """2026-10-16 creative run, case 06: "Reference: the pacing" passed (drags per third) while "Pacing curve" failed
    (pauses) on the same ad. The reference row now measures the change with the check's own pauses."""
    from cbj.checks import gameplay_checks
    from cbj.level import load_level
    from cbj.play import plan
    from test_level_gameplay import NC, fake_recording, raw
    level = load_level(NC)
    seen = set()
    for played in ("speeds_up", "slows_down"):
        rec = fake_recording(tmp_path / played, NC, plan(level, "win", curve=played))
        for asked in ("speeds_up", "slows_down"):
            check = {c["check"]: c for c in gameplay_checks(B.check(raw(gameplay={"ending": "win"}, pacing={"curve": asked})),
                                                            rec, NC)}["Pacing curve"]
            notes = copy.deepcopy(NOTES)
            notes["pacing"] = None  # the change alone
            b = _guided_brief(notes=notes)
            b["pacing"]["curve"] = asked
            b["planner"]["references"][0]["pacing"] = {"change": asked.replace("_", " "), "source": "motion"}
            vdir = tmp_path / f"{played}-{asked}"
            (vdir / "ad").mkdir(parents=True)
            (vdir / "parts.json").write_text(json.dumps(_manifest()))
            (vdir / "ad" / "ad.json").write_text(json.dumps({"layers": {}}))
            row = {r["check"]: r for r in audit.reference_rows(PACED, b, {"checks": [], "length_s": 38.0}, vdir, rec)}["Reference: the pacing"]
            assert row["status"] == check["status"], (played, asked, row, check)
            assert "as the Pacing curve check measures them" in row["detail"]
            seen.add(check["status"])
    assert seen == {"pass", "failed"}  # both verdicts were compared



@pytest.mark.parametrize("text, fn", [
    ("Can you beat the clock?", "challenge"),  # case 07: was urgency because of "clock"
    ("Hurry!", "urgency"),
    ("Wait... that's wrong!", "wrong"),          # case 07: had no function
    ("Found it!", "instruction"),                # case 07: had no function; the caption on the correction
    ("Oops!", "wrong"), ("Not that one", "wrong"), ("There it is!", "instruction"), ("Got it!", "instruction"),
    ("Level complete", "result"), ("So close!", "result"), ("Not this time...", "result"), ("PLAY NOW", "cta"),
    ("Running out of time?", "challenge"),
])
def test_caption_functions_put_a_question_first(text, fn):
    assert V.caption_function(text) == fn


def test_case_07_captions_reach_their_fields():
    notes = copy.deepcopy(NOTES)
    notes["captions_seen"] = ["Can you beat the clock?", "Wait... that's wrong!", "Found it!", "Hurry!", "So close!", "PLAY NOW"]
    assert list(V.caption_functions(notes)) == ["challenge", "wrong", "instruction", "urgency", "result", "cta"]
    b = _fresh()
    V.apply(b, "Use the captions of this video.", [_analysis(["captions"], notes)])
    cc = b["concept"]
    assert cc["hook"] and cc["mistake"] == "Oops!" and cc["fix"] == "Move this one first!" and cc["hurry"] == "Hurry up!"
    assert "Wait... that's wrong!" not in cc.values() and "Found it!" not in cc.values()  # the tool's own words
    from cbj.ad import copy_problems
    assert all(copy_problems(x) == [] for x in cc.values() if isinstance(x, str) and x)
    assert audit.CAPTION_LAYERS["wrong"] == "cap_mistake" and audit.CAPTION_FIELDS["wrong"] == "mistake"



def test_the_tempo_is_judged_only_from_counted_moves(tmp_path):
    """2026-10-16 creative run, case 10: the pacing row failed on "tempo fast in the reference, normal in the ad (0.59
    drags a second)", a tempo that was the model's own word (its counts, 15 moves in 3.3 s, were dropped)."""
    notes = copy.deepcopy(NOTES)
    notes["pacing"] = "fast"
    b = _guided_brief(notes=notes)
    b["pacing"]["tempo"] = "fast"
    b["planner"]["references"][0]["pacing"] = {"change": "speeds up", "source": "motion", "tempo": "fast", "tempo_source": "model"}
    r = _rows(tmp_path / "a", b, prompt=PACED, result=SPEEDS_UP)["the pacing"]
    assert r["status"] == "pass" and "the model's own word, not a count of its moves, so it is not judged" in r["detail"]
    # counted: judged, and one class apart within 0.1 drags a second of the boundary passes with a note
    b["planner"]["references"][0]["pacing"]["tempo_source"] = "counts"
    near = _manifest(moments=[{"id": f"drag_{i}", "kind": "move", "at_s": 1.0 + 0.55 * i} for i in range(18)])  # 18 in 30.5 s: 0.59/s
    r = _rows(tmp_path / "b", b, near, prompt=PACED, result=SPEEDS_UP)["the pacing"]
    assert r["status"] == "pass" and "within 0.1 of the 0.6 drags a second boundary" in r["detail"]
    far = _manifest(moments=[{"id": f"drag_{i}", "kind": "move", "at_s": 1.0 + 3.0 * i} for i in range(10)])  # 0.33/s
    assert _rows(tmp_path / "c", b, far, prompt=PACED, result=SPEEDS_UP)["the pacing"]["status"] == "failed"


def test_an_asked_ending_compares_the_result_not_the_win_or_the_fail(tmp_path):
    """2026-10-16 creative run, case 10: a time-out reference, a near-fail asked by the request itself."""
    notes = copy.deepcopy(NOTES)
    notes["structure"] = [{"from_s": 0, "to_s": 3, "purpose": "hook"}, {"from_s": 3, "to_s": 10, "purpose": "gameplay"},
                          {"from_s": 10, "to_s": 13, "purpose": "mistake"}, {"from_s": 13, "to_s": 28, "purpose": "gameplay"},
                          {"from_s": 28, "to_s": 31, "purpose": "near_fail"}, {"from_s": 31, "to_s": 34, "purpose": "fail"},
                          {"from_s": 34, "to_s": 38, "purpose": "end_card"}]
    b = _guided_brief(notes=notes)
    asked = "Inspired by this video's hook and pacing. A near-fail ending with 3 seconds left, 45 seconds."
    r = _rows(tmp_path / "a", b, prompt=asked)["the purposes in order"]
    assert r["status"] == "pass" and "the request sets its own ending" in r["detail"]
    assert "the reference: hook -> gameplay -> mistake -> near_fail -> fail -> end_card; the ad: hook -> gameplay -> mistake -> " \
           "near_fail -> victory -> end_card" in r["detail"]
    r = _rows(tmp_path / "b", b, prompt=PROMPT)["the purposes in order"]
    assert r["status"] == "failed" and "own ending" not in r["detail"]


def test_the_look_row_judges_the_plan_and_the_ad_apart(tmp_path):
    """2026-10-16 creative run, case 12: the brief took the reference's cream and the poster showed it, but the margins
    were named "light grey", outside the cream family, so the row failed in all three versions. Now: (a) the plan took
    the palette (by family or within 48 RGB of a dominant colour), (b) the poster shows the brief's background (within
    48 RGB of either stop or the gradient between them)."""
    def look(bg, margin, dominant, name):
        notes = copy.deepcopy(NOTES)
        notes["dominant_colours"] = dominant
        b = _guided_brief(focus=("look",), notes=notes)
        b["visuals"].update(background=bg, caption_fill="#800020")
        return _rows(tmp_path / name, b, poster=margin)["the look"]
    pet = ["#FDF5E6", "#E0AC69", "#800020", "#FFD700"]  # the pet reel's dominant colours
    r = look(["#E5DBC9"], (0xDA, 0xD8, 0xD4), pet, "v3")  # case 12 v3: a cream background, margins read #DAD8D4
    assert r["status"] == "pass" and "#DAD8D4" in r["detail"] and "16 from the brief's background" in r["detail"], r
    r = look(["#FEF3DC", "#E6CBA0"], (0xE5, 0xDB, 0xC9), pet, "v2")  # case 12 v2: a gradient, margins read mid-way
    assert r["status"] == "pass", r
    # (a) fails: the game's default background, or a background that is not the reference's, against a red reference
    red = ["#E53935", "#B71C1C"]
    r = look([], (240, 240, 240), red, "default")
    assert r["status"] == "failed" and r["where"] == "plan"
    r = look(["#1469FF"], (20, 105, 255), red, "blue")
    assert r["status"] == "failed" and r["where"] == "plan" and "not taken" in r["detail"]
    # (b) fails: a navy brief taken from a navy reference, but the poster's margins are white
    r = look(["#1D3557"], (255, 255, 255), ["#1D3557", "#FFFFFF"], "navy")
    assert r["status"] == "failed" and r["where"] == "ad" and "not shown" in r["detail"]
    assert audit._gradient_dist("#808080", ["#000000", "#FFFFFF"]) < 2  # mid-way along a black-to-white gradient



def test_a_stated_length_keeps_the_references_long_play_and_replay_out():
    """2026-10-16 creative run, case 13: the pet clip joined before a near-fail creative, a 30 s ask. The reference's
    long play (14 moves) and its replay did not fit 30 s; the ad overran, then dropped the replay, and the loop could
    not fix it. The request's own length wins."""
    notes = copy.deepcopy(NOTES)
    notes["structure"] = [{"from_s": 0, "to_s": 5, "purpose": "hook", "what": "a dog in a bath"},
                          {"from_s": 5, "to_s": 30, "purpose": "gameplay"}, {"from_s": 30, "to_s": 36, "purpose": "replay"},
                          {"from_s": 36, "to_s": 40, "purpose": "victory"}, {"from_s": 40, "to_s": 45, "purpose": "end_card"}]

    def made(prompt):
        b = _fresh()
        b["sequence"]["replay"] = False
        a = {**_analysis(["concept"], notes), "facts": {"duration_s": 45.0}}
        V.apply(b, prompt, [a])
        return b
    b = made("Make a Color Block Jam version of the concept in this video. 30 seconds.")
    # the reference's long play is not taken; the moves are the fill's for the stated 30 s (round 4, case 29)
    assert b["level"]["moves"] == b["reference"]["play"]["moves"] and b["sequence"]["replay"] is False
    assert "the reference's long play is not taken: the request fixes 30 s" in b["assumptions"]
    assert any(x.startswith("the reference's replay is not taken: the request fixes 30 s") for x in b["assumptions"])
    assert not any(x.startswith(("a long play", "a replay")) for x in b["reference"]["adapted"])
    b = made("Make a Color Block Jam version of the concept in this video.")
    assert b["level"]["moves"] and b["sequence"]["replay"] is True
    assert any(x.startswith("a long play") for x in b["reference"]["adapted"]) and "a replay (the reference shows a moment twice)" in b["reference"]["adapted"]
    b = made("Make a Color Block Jam version of the concept in this video. 45 seconds.")  # a long ask has room for the replay
    assert b["sequence"]["replay"] is True and b["level"]["moves"] == b["reference"]["play"]["moves"]  # the fill's



def test_a_short_asked_length_makes_the_references_replay_optional_in_the_order(tmp_path):
    """2026-10-16 creative run, case 13: the reference has a replay, the 30 s ad has none (no room); the order row
    must not fail on it, and so the loop gets no miss it cannot fix. At 45 s the replay is expected."""
    notes = copy.deepcopy(NOTES)
    notes["structure"] = [{"from_s": 0, "to_s": 5, "purpose": "hook"}, {"from_s": 5, "to_s": 25, "purpose": "gameplay"},
                          {"from_s": 25, "to_s": 30, "purpose": "replay"}, {"from_s": 30, "to_s": 34, "purpose": "victory"},
                          {"from_s": 34, "to_s": 38, "purpose": "end_card"}]  # on the 38 s clip of _analysis
    b = _guided_brief(notes=notes)
    r = _rows(tmp_path / "a", b, prompt="Make a Color Block Jam version of the concept in this video. 30 seconds.")["the purposes in order"]
    assert r["status"] == "pass" and "the reference's replay is optional at 30 s" in r["detail"]
    assert "the reference: hook -> gameplay -> replay -> victory -> end_card" in r["detail"]
    assert not audit.misses([r])
    r = _rows(tmp_path / "b", b, prompt="Make a Color Block Jam version of the concept in this video. 45 seconds.")["the purposes in order"]
    assert r["status"] == "failed" and "optional" not in r["detail"]



@pytest.mark.parametrize("plan", [
    R.ReadingPlan.from_words("Based on this video I want to create a Color Block Jam version of this concept."),
    R.ReadingPlan.from_words("Use its hook."),
    R.ReadingPlan(focus=["look"], level="targeted", questions=["What are the colours?"], required_fields=["dominant_colours"]),
    R.ReadingPlan(focus=["concept"], level="full", questions=["How does it end (payoff, fail, cliffhanger, CTA)?"], required_fields=["ending"]),
])
def test_every_composed_prompt_asks_the_four_endings(plan):
    """2026-10-16, READING-ACCURACY-v5.md: two cliffhangers were read right exactly when the planner's own ending
    question named the cliffhanger; the fixed question names the game's four endings in every reading."""
    ask = R.video_ask(plan, {"duration_s": 38.0}, "a request")
    assert "- " + R.ENDING_QUESTION in ask and ask.count(R.ENDING_QUESTION) == 1
    looked = ask.split("WHAT TO LOOK FOR (always, the whole reading):")[1].split("IGNORE:")[0]
    assert R.ENDING_QUESTION in looked and all(q in looked for q in plan.questions)
    for words in ("a win;", "a near-fail (a win with 5 s or less on the clock)", "a time-out (the out-of-time screen)",
                  "a cliffhanger (the clip cuts before any result, often with a question caption)",
                  "it stops mid-level (no result, no question: the game's cliffhanger too)"):  # the fifth wording (2026-10-17)
        assert words in R.ENDING_QUESTION



# ---------- the ending read again on the last seconds (2026-10-16, after READING-ACCURACY-v6.md) ----------

@needs_ffmpeg
def test_the_last_10_s_are_cut_from_the_copy_at_8_fps(clips, tmp_path):
    copy_ = tmp_path / "copy.mp4"
    f = R.normalise_video(clips / "long.mp4", copy_)
    tail = R.tail_copy(copy_, tmp_path / "tail.mp4", f["duration_s"])
    assert (tail["from_s"], tail["to_s"], tail["fps"]) == (60.0, 70.0, 8) and 70 <= tail["frames"] <= 82
    assert abs(R.probe_video(tmp_path / "tail.mp4")["duration_s"] - 10.0) < 0.6


def test_the_ending_question_names_the_four_endings_the_clock_and_the_screens():
    ask = R.ending_ask({"from_s": 35.0, "to_s": 45.0}, 45.0)
    assert ask.startswith("These are the last 10 s (35-45 s) of a 45 s ad") and R.ENDING_QUESTION in ask
    for words in ('"ending": "win|near-fail|time-out|cliffhanger|stopped"', "MM:SS", '"win_screen"', '"out_of_time_screen"',
                  '"question_caption"', "Return ONLY JSON"):
        assert words in ask


def _long_notes(ending, captions):
    return {**NOTES, "ending": ending, "captions_seen": captions, "mistakes": [],
            "structure": [{"from_s": 0, "to_s": 3, "purpose": "hook"}, {"from_s": 3, "to_s": 60, "purpose": "gameplay"},
                          {"from_s": 60, "to_s": 64, "purpose": "victory"}, {"from_s": 64, "to_s": 70, "purpose": "end_card"}]}


@needs_ffmpeg
def test_the_last_seconds_win_over_the_whole_clip_when_they_disagree(clips):
    whole = _long_notes("near-fail", ["Can you clear it?", "Level Completed", "Cleared with 00:08 left", "PLAY NOW"])
    last = {"ending": "win", "last_clock": "00:08", "win_screen": True, "out_of_time_screen": False, "question_caption": "",
            "why": "the clock stops at 00:08 on Level Completed"}
    vision, lines = FakeVision(whole, last), []
    a = R.read_video(clips / "long.mp4", PROMPT, planner=FakePlanner(PLAN), client=vision, log=lines.append,
                     measure=lambda p: {"cuts_s": []})
    assert not a.get("error") and len(vision.asks) == 3 and vision.asks[1].startswith("These are the last 10 s (60-70 s)")
    er = a["ending_read"]
    assert (er["ending"], er["last_clock"], er["win_screen"], er["model"]) == ("win", "00:08", True, "fake-omni")
    assert er["overrode"] == {"whole_clip": "near_fail", "last_s": "win"} and er["seconds"] >= 0 and er["frames"] > 0
    assert a["notes"]["ending"] == "win" and a["notes"]["ending_whole"] == "near-fail" and V.mapped_ending(a["notes"]) == "win"
    assert any("the last seconds win" in x for x in lines)
    # agreeing: nothing overridden, said so
    vision, lines = FakeVision(whole, {**last, "ending": "near-fail"}), []
    a = R.read_video(clips / "long.mp4", PROMPT, planner=FakePlanner(PLAN), client=vision, log=lines.append,
                     measure=lambda p: {"cuts_s": []})
    assert "overrode" not in a["ending_read"] and a["notes"]["ending"] == "near-fail" and any("read agree" in x for x in lines)


@needs_ffmpeg
def test_no_second_read_under_12_s(clips):
    vision = FakeVision({**NOTES, "structure": [{"from_s": 0, "to_s": 6, "purpose": "gameplay", "confidence": 0.9}]})
    a = R.read_video(clips / "short.mp4", PROMPT, planner=FakePlanner(PLAN), client=vision, measure=lambda p: {"cuts_s": []})
    assert a["ending_read"]["skipped"].startswith("the clip is under 12 s") and len(vision.asks) == 2  # the clip, the board's still
    assert "ending_read" not in a["notes"]


def test_a_question_outranks_a_near_fail_or_a_fail_unless_a_screen_was_seen():
    segs = [{"from_s": 0, "to_s": 3, "purpose": "hook"}, {"from_s": 3, "to_s": 36, "purpose": "gameplay"},
            {"from_s": 36, "to_s": 39, "purpose": "question", "captions": ["Can you finish it?"]},
            {"from_s": 39, "to_s": 45, "purpose": "end_card"}]
    n = {"ending": "near-fail", "structure": segs, "captions_seen": ["Can you clear it?", "Can you finish it?"]}
    assert V.mapped_ending(n) == "cliffhanger"                                        # v6 1-cliffhanger
    assert V.mapped_ending({**n, "ending": "time-out"}) == "cliffhanger"
    assert V.mapped_ending({**n, "captions_seen": n["captions_seen"] + ["Level Completed"]}) == "near_fail"  # a win screen
    assert V.mapped_ending({**n, "ending_read": {"ending": "near_fail", "win_screen": True}}) == "near_fail"
    assert V.mapped_ending({**n, "ending": "fail", "screen_text": ["Out of time!"]}) == "time_out"  # an out-of-time screen
    # no question part, but the last seconds show a question caption and no screen: a cliffhanger
    plain = [{"from_s": 0, "to_s": 34, "purpose": "gameplay"}, {"from_s": 34, "to_s": 38.9, "purpose": "fail",
                                                                  "what": "Timer runs out and failure text appears"}]
    assert V.mapped_ending({"ending": "time-out", "structure": plain,
                            "ending_read": {"ending": "time_out", "question_caption": "Would you have seen it?"}}) == "cliffhanger"
    assert V.screens_seen({"captions_seen": ["Cleared with 00:08 left"]}) == (True, False)



def test_the_last_seconds_are_checked_against_their_own_clock_and_screens():
    """v7 (2026-10-16): the second read fixed 1-cliffhanger but turned 3-clean into a near-fail at 00:08 and 2-clean into
    a cliffhanger on its end card's "Can you do it faster?". What it transcribed (the clock, the screens) decides."""
    segs = [{"from_s": 0, "to_s": 3, "purpose": "hook"}, {"from_s": 3, "to_s": 27, "purpose": "gameplay"},
            {"from_s": 27, "to_s": 35, "purpose": "replay"}, {"from_s": 35, "to_s": 45, "purpose": "end_card"}]
    clean3 = {"ending": "near-fail", "ending_whole": "win", "structure": segs,
              "captions_seen": ["Can you clear it?", "Level Completed", "Cleared with 00:08 left", "PLAY NOW"],
              "ending_read": {"ending": "near_fail", "last_clock": "00:08", "win_screen": True, "question_caption": ""}}
    assert V.mapped_ending(clean3) == "win"
    assert V.mapped_ending({**clean3, "ending_read": {**clean3["ending_read"], "last_clock": "00:02"}}) == "near_fail"
    clean2 = {"ending": "cliffhanger", "ending_whole": "win", "structure": segs, "screen_text": ["Level 70", "Level Completed"],
              "captions_seen": ["Can you clear it?", "Can you do it faster?"],
              "ending_read": {"ending": "cliffhanger", "last_clock": None, "win_screen": False, "question_caption": "Can you do it faster?"}}
    assert V.mapped_ending(clean2) == "win"
    cliff1 = {"ending": "cliffhanger", "ending_whole": "near-fail", "structure": segs, "captions_seen": ["Can you finish it?"],
              "ending_read": {"ending": "cliffhanger", "last_clock": "00:08", "win_screen": False, "question_caption": "Can you finish it?"}}
    assert V.mapped_ending(cliff1) == "cliffhanger"
    assert V.mapped_ending({"ending": "time-out (the out-of-time screen)", "structure": []}) == "time_out"  # the schema's words copied


# ---------- the board (2026-10-17, the owner's test: a simple open board came out as the showcase narrow centre) ----------

SIMILAR = "create a similar game in Color Block Jam"
BUBBLES = ["a transparent bubble with the counter 3", "a transparent bubble with the counter 4",
           "a transparent bubble with the counter 5"]
LOLTAP_BOARD = {"columns": 6, "rows": 6, "shape": "open", "blocks": 11,
                "colours": ["green", "light blue", "red", "yellow", "pink/magenta", "orange", "green"],
                "pieces": "mixed", "gates_sides": 4, "obstacles": BUBBLES, "busy": "simple"}


def _board_notes(board=None, **over):
    """A LolTap-style reading: another game's 15 s ad, a simple open board with three bubble obstacles, a clean win."""
    n = copy.deepcopy(NOTES)
    n.update(ending="win", mistakes_shown=False, mistakes=[], mechanics_seen=["sliding coloured blocks", "exits of the block's colour"],
             structure=[{"from_s": 0, "to_s": 2, "purpose": "hook", "captions": ["Can you solve this?"]},
                        {"from_s": 2, "to_s": 12, "purpose": "gameplay"}, {"from_s": 12, "to_s": 15, "purpose": "victory"}],
             board=copy.deepcopy(LOLTAP_BOARD if board is None else board))
    n.update(over)
    return n


def _board_analysis(focus=("concept",), board=None, **over):
    return {**_analysis(list(focus), _board_notes(board, **over)), "facts": {"duration_s": 15.0}}


def test_the_board_question_is_asked_whenever_the_focus_covers_the_board():
    concept = R.ReadingPlan.from_words(PROMPT)
    ask = R.video_ask(concept, FACTS, PROMPT)
    assert ask.count(R.BOARD_QUESTION) == 1 and '"board": {"columns"' in ask and "board" in ask.split("REQUIRED: ")[1].split(";")[0]
    assert "its board and pieces" not in ask and "its board and pieces" not in R.DEFAULT_IGNORE  # no longer ignored
    for shape in R.BOARD_SHAPES:
        assert f"{shape}: " in ask  # one sentence on what each shape looks like
    assert "never makes a shape" in ask and "never an obstacle" in ask  # another game's obstacles are not blocks or walls
    board = R.ReadingPlan.from_words("Make the same level as this video.")
    assert board.focus == ["board"] and R.BOARD_QUESTION in R.video_ask(board, FACTS, "Make the same level as this video.")
    hook = R.ReadingPlan.from_words("Use this video's hook.")
    assert R.BOARD_QUESTION in R.video_ask(hook, FACTS, "Use this video's hook.")  # always read (2026-10-17); applied by the focus
    # a planner plan that already asks it is not asked twice
    plan = R.ReadingPlan(focus=["board"], level="targeted", questions=[R.BOARD_QUESTION], required_fields=["board"])
    assert R.video_ask(plan, FACTS, "x").count(R.BOARD_QUESTION) == 1


@pytest.mark.parametrize("prompt, focus", [
    ("Make the same level as this video.", ["board"]), ("Use this video's layout.", ["board"]),
    ("A board like the one in this clip.", ["board"]), ("Use the grid from this video.", ["board"]),
    ("Inspired by this video's board.", ["board"]),  # its board, not its concept
    (SIMILAR, ["concept"]),
])
def test_the_word_table_reads_the_board(prompt, focus):
    assert R.focus_words(prompt)["focus"] == focus


def test_the_board_is_covered_by_the_concept_and_its_own_focus():
    assert R.covers(["concept"], "board") and R.covers(["board"], "board") and R.covers(["hook", "board"], "board")
    assert not R.covers(["hook"], "board") and not R.covers(["look"], "board") and "board" in R.FOCI


@pytest.mark.parametrize("prompt, names", [
    ("A version of this concept on a narrow centre board.", {"shape"}),
    ("A version of this concept with walls in the middle.", {"shape"}),
    ("A version of this concept on a 7x9 board.", {"size"}),
    ("A version of this concept on a big board.", {"size"}),
    ("A version of this concept with 8 blocks.", {"blocks"}),
    ("A version of this concept with red, blue and green blocks.", {"colours"}),
    ("A version of this concept with three colours.", {"colours"}),
    ("A version of this concept with small pieces.", {"pieces"}),
    ("A version of this concept with L-shaped blocks.", {"pieces"}),  # the pieces, not the board's shape
    ("A version of this concept on a hard level.", {"difficulty"}),
    ("A version of this concept, but simple.", {"difficulty"}),
    ("A version of this concept on the game's own level.", {"level"}),
    ("A version of this concept on level 3.", {"level"}),
    ("A version of this concept, a shipped level.", {"level"}),
    (SIMILAR, set()),
    ("Use the same layout as this video.", set()),  # points at the reference: not a stated shape
    ("A version of this concept where the blocks leave through their doors.", set()),  # the gates, not a door shape
    ("A version of this concept, 30 seconds long.", set()),
])
def test_stated_reads_the_level(prompt, names):
    level = {"shape", "size", "blocks", "colours", "pieces", "difficulty", "level"}
    assert V.stated(prompt) & level == names


@pytest.mark.parametrize("name, slot", [
    ("green", "Green"), ("lime green", "Green"), ("light blue", "Blue"), ("cyan", "Blue"), ("Blue", "Blue"),
    ("pink/magenta", "Purple"), ("magenta", "Purple"), ("pink", "Purple"), ("purple", "Purple"), ("dark green", "DarkGreen"),
    ("yellow", "Yellow"), ("gold", "Yellow"), ("orange", "Orange"), ("red", "Red"), ("brown", None), ("white", None),
])
def test_the_colour_mapping(name, slot):
    assert V.board_colour(name) == slot


def test_the_board_reading_in_the_games_terms():
    bd = V.board_of(_board_notes())
    assert (bd["columns"], bd["rows"], bd["shape"], bd["blocks"], bd["pieces"], bd["gates_sides"], bd["busy"]) == \
        (6, 6, "open", 11, "mixed", 4, "simple")
    assert bd["colours"] == ["Green", "Blue", "Red", "Yellow", "Purple", "Orange"]  # mapped, de-duplicated, in order
    assert bd["obstacles"] == BUBBLES
    odd_words = V.board_of(_board_notes({"columns": "about 7", "rows": 9.0, "shape": "Narrow-centre", "colours": ["teal", "beige"]}))
    assert (odd_words["columns"], odd_words["rows"], odd_words["shape"]) == (7, 9, "narrow_center")
    assert odd_words["colours"] == ["Blue"] and odd_words["colours_unmapped"] == ["beige"]
    odd = V.board_of(_board_notes({"shape": "triangle", "colours": ["beige"], "blocks": "eight"}))
    assert odd is None  # nothing usable: no board
    assert V.board_of({"structure": []}) is None


def test_the_clamping():
    assert V.board_size("open", 6, 6) == (6, 6) and V.board_size("open", 12, 14) == (9, 10) and V.board_size("open", 3, 3) == (4, 4)
    assert V.board_size("narrow_center", 5, 5) == (5, 6) and V.board_size("lanes", 5, 5) == (7, 6) and V.board_size("ring", 5, 7) == (6, 7)
    assert V.board_size(None, 6, 6) == (6, 6)
    assert V.board_blocks(11, "open", 6, 6, "mixed") == 10 and V.board_blocks(1, "open", 6, 6, "mixed") == 2
    assert V.board_blocks(10, "ring", 6, 6, "big") == 5  # 32 free cells hold about five big pieces
    assert V.board_blocks(7, "open", 6, 6, "small") == 7
    b = _fresh()
    V.apply(b, SIMILAR, [_board_analysis(board={**LOLTAP_BOARD, "columns": 12, "rows": 14})])
    assert (b["level"]["width"], b["level"]["height"]) == (9, 10)
    assert any("12x14" in x and "9x10" in x for x in b["assumptions"])
    assert any("11 blocks" in x and "10 is the most" in x for x in b["assumptions"])


def test_the_board_sets_the_level_when_the_request_says_nothing_about_it():
    b = _fresh()
    prov = V.apply(b, SIMILAR, [_board_analysis()])[0]
    lv = b["level"]
    # the difficulty is not taken from how busy the board looks (R10, 2026-10-17: 1-2 of 12): the generator's default stays
    assert (lv["source"], lv["shipped"], lv["shape"], lv["width"], lv["height"], lv["blocks"], lv["pieces"], lv["difficulty"]) == \
        ("generate", None, "open", 6, 6, 10, "mixed", "any")
    assert lv["colours"] == ["Green", "Blue", "Red", "Yellow", "Purple", "Orange"]
    assert "level.difficulty" not in b["changed"]
    for g in ("level.source", "level.shape", "level.size", "level.blocks", "level.colours", "level.pieces"):
        assert g in b["changed"], g
    row = B.control(b, "level")
    assert "From the reference video ref.mp4: an open 6x6 board with 10 blocks in 6 colours" in row["plan"] and row["status"] == "applied"
    assert "its cells are not copied" in row["plan"]
    assert "board looks" not in (B.control(b, "difficulty_pacing")["plan"] or "")
    assert prov["board"]["busy"] == "simple" and "looks simple" in prov["board"]["text"]  # recorded and shown, as info
    assert any(x.startswith("the board (an open 6x6 board") for x in prov["adapted"]) and "its exact layout" in prov["not_copied"]
    # no measured fill in this reading: never packed from the blocks read or a "busy" word (R10, 2026-10-17)
    assert prov["board"]["took"] == ["shape", "size", "pieces", "blocks", "colours"] and prov["board"]["kept"] == []
    # the board as validated by the brief stays as set
    assert B.check(b)["level"] == lv


def test_another_games_obstacles_are_never_blocks_walls_or_a_shape():
    """The owner's amendment (2026-10-17): the three bubbles with counters add no block, no wall and no shape, and are
    three "not used" lines, on the card (not_used) and in the assumptions, and not copied."""
    b = _fresh()
    prov = V.apply(b, SIMILAR, [_board_analysis(board={**LOLTAP_BOARD, "blocks": 7})])[0]
    lv = b["level"]
    assert lv["blocks"] == 7 and lv["shape"] == "open" and lv["style"] == [] and lv["changes"] == []  # 0 extra, no wall
    assert "level.changes" not in b["changed"] and "level.style" not in b["changed"]
    lines = [x for x in prov["not_used"] if "bubble" in x]
    assert len(lines) == 3 and all(x.endswith(": not used: not in Color Block Jam") for x in lines)
    assert all(x in b["assumptions"] for x in lines)
    assert all(f"its transparent bubble with the counter {k}" in prov["not_copied"] for k in (3, 4, 5))
    assert not any("bubble" in x for x in prov["mechanics"])  # never listed as translated
    assert "sliding coloured blocks become the game's own drags" in prov["mechanics"]
    # a mechanics_seen entry about the same bubbles gives way to the board's exact list (still three lines)
    b2 = _fresh()
    prov2 = V.apply(b2, SIMILAR, [_board_analysis(mechanics_seen=["bubble obstacles with counters", "sliding blocks"])])[0]
    assert len([x for x in prov2["not_used"] if "bubble" in x]) == 3


def test_the_request_keeps_its_own_level():
    b = _fresh()
    b["level"].update(shape="narrow_center", difficulty="hard")  # what the planner set from the request's words
    prov = V.apply(b, "A version of this video on a narrow centre board, hard.", [_board_analysis()])[0]
    lv = b["level"]
    assert (lv["shape"], lv["difficulty"]) == ("narrow_center", "hard")  # the request's own
    # the rest from the reference: 11 blocks hold 8 on a 6x6 narrow centre's 28 free cells, so the board grows a column
    # and 10 fit (2026-10-17: grow a cell a side before cutting blocks)
    assert (lv["width"], lv["height"], lv["blocks"], lv["source"]) == (7, 6, 10, "generate")
    assert prov["board"]["kept"] == ["shape"] and "shape" not in prov["board"]["took"]
    b = _fresh()
    b["level"].update(width=7, height=9, blocks=8)
    V.apply(b, "A version of this video with 8 blocks on a 7x9 board.", [_board_analysis()])
    assert (b["level"]["width"], b["level"]["height"], b["level"]["blocks"]) == (7, 9, 8) and b["level"]["shape"] == "open"
    b = _fresh()
    V.apply(b, "A version of this video on the game's own level 3.", [_board_analysis()])
    same = lambda lv: {k: v for k, v in lv.items() if k != "moves"}  # noqa: E731 (moves: the long play, a pacing rule)
    assert same(b["level"]) == same(_fresh()["level"]) and any("game's own level" in x for x in b["assumptions"])
    b = _fresh()
    V.apply(b, "Use only this video's hook.", [_board_analysis(("hook",))])  # the board is not a focus, and "only"
    assert same(b["level"]) == same(_fresh()["level"])  # the moves: the play decision's fill (round 4, case 29)


def test_how_busy_the_board_looks_never_sets_the_difficulty():
    """R10 (2026-10-17): busy against the level's difficulty read 1-2 of 12, so it is info only; the difficulty is the
    request's, the ending rule's (hard for a near-fail) or the generator's default."""
    b = _fresh()
    V.apply(b, SIMILAR, [_board_analysis(ending="near-fail", structure=[
        {"from_s": 0, "to_s": 2, "purpose": "hook"}, {"from_s": 2, "to_s": 10, "purpose": "gameplay"},
        {"from_s": 10, "to_s": 13, "purpose": "near_fail"}, {"from_s": 13, "to_s": 15, "purpose": "victory"}])])
    assert b["gameplay"]["ending"] == "near_fail" and b["level"]["difficulty"] == "hard"  # the ending rule, not busy
    for busy in ("simple", "medium", "busy"):
        b = _fresh()
        prov = V.apply(b, SIMILAR, [_board_analysis(board={**LOLTAP_BOARD, "busy": busy})])[0]
        assert b["level"]["difficulty"] == "any" and "level.difficulty" not in b["changed"] and prov["board"]["busy"] == busy
    b = _fresh()
    b["level"]["difficulty"] = "easy"
    V.apply(b, "A simple version of this video.", [_board_analysis(board={**LOLTAP_BOARD, "busy": "busy"})])
    assert b["level"]["difficulty"] == "easy"  # the request's own


def _board_vdir(tmp_path, level):
    vdir = tmp_path / "v1"
    (vdir / "ad").mkdir(parents=True, exist_ok=True)
    (vdir / "parts.json").write_text(json.dumps(_manifest()))
    (vdir / "ad" / "ad.json").write_text(json.dumps({"layers": {}}))
    (vdir / "level.json").write_text(json.dumps(level))
    return vdir


def _level_json(w=6, h=6, colours=(0, 2, 3, 1, 5, 4, 0, 2, 3, 1), inactive=()):
    return {"gridWidth": w, "gridHeight": h, "inactiveCells": [{"x": x, "y": y} for x, y in inactive],
            "GridBlockDatas": [{"gridPosition": {"x": 0, "y": 0}, "blockColor": c, "shapeOffsets": [{"x": 0, "y": 0}]} for c in colours],
            "ExitDatas": []}


def _board_rows(tmp_path, brief, level, prompt=SIMILAR):
    record = {"checks": [], "length_s": 38.0}
    return {r["check"]: r for r in audit.reference_rows(prompt, brief, record, _board_vdir(tmp_path, level), None)}


def _board_brief(focus=("concept",), board=None):
    b = _fresh()
    a = _board_analysis(focus, board)
    a["notes"]["structure"] = R.structure(a["notes"]["structure"], 15)
    V.apply(b, SIMILAR, [a])
    b["planner"] = {"references": [a]}
    return b


def test_the_board_row(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "BOARD_RELIABLE", frozenset({"shape", "size", "blocks", "colours"}))
    b = _board_brief()
    row = _board_rows(tmp_path / "a", b, _level_json())["Reference: the board"]
    assert row["status"] == "pass" and row["from"] == "reference"
    assert "shape: ok (shape open read, open made)" in row["detail"] and "6x6 read, 6x6 made" in row["detail"]
    assert "11 blocks read (10 the most this board takes), 10 made" in row["detail"] and "6 of 6 in the level" in row["detail"]
    assert "it looks simple (info: not used for the difficulty)" in row["detail"]
    # a level the generator could not make of the brief's type (its own fallback to the showcase narrow centre): the
    # made shape is read from its walls, and the miss is the play's (a new take), the brief carried the board
    from cbj.generate import holes_for
    narrow = _level_json(6, 8, (0, 1, 2, 3, 4, 5, 6), inactive=sorted(holes_for("narrow_center", 6, 8)))
    row = _board_rows(tmp_path / "b", b, narrow)["Reference: the board"]
    assert row["status"] == "failed" and row["where"] == "play" and "shape: differs" in row["detail"] and "6x6 read, 6x8 made" in row["detail"]
    assert "open made" not in row["detail"] and "narrow_center made" in row["detail"]
    row = _board_rows(tmp_path / "c", b, _level_json(colours=(6, 6, 6, 1, 6, 6, 6, 6, 6, 6)))["Reference: the board"]
    assert row["status"] == "failed" and row["where"] == "play" and "1 of 6 in the level" in row["detail"]
    row = _board_rows(tmp_path / "d", b, _level_json(colours=(0, 2, 3, 1, 5, 4, 0)))["Reference: the board"]
    assert row["status"] == "failed" and "(10 the most this board takes), 7 made" in row["detail"]
    row = _board_rows(tmp_path / "e", b, _level_json(colours=(0, 2, 3, 1, 5, 4, 0, 2)))["Reference: the board"]
    assert row["status"] == "pass"  # within two blocks


def test_the_board_row_judges_only_the_reliable_parts(tmp_path, monkeypatch):
    b = _board_brief()
    monkeypatch.setattr(audit, "BOARD_RELIABLE", frozenset({"shape"}))
    row = _board_rows(tmp_path / "a", b, _level_json(colours=(0, 0, 0)))["Reference: the board"]
    assert row["status"] == "pass" and "blocks: differs" in row["detail"] and "read approximately" in row["detail"]
    monkeypatch.setattr(audit, "BOARD_RELIABLE", frozenset())
    row = _board_rows(tmp_path / "b", b, _level_json(8, 9, colours=(0,), inactive=[(1, 1)]))["Reference: the board"]
    assert row["status"] == "info" and row["detail"].count("read approximately") == 4


def test_the_board_row_leaves_the_requests_own_level_and_other_foci(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "BOARD_RELIABLE", frozenset({"shape", "size", "blocks", "colours"}))
    hook = _board_brief(("hook",))
    assert _board_rows(tmp_path / "a", hook, _level_json())["Reference: the board"]["status"] == "info"
    b = _board_brief()
    row = _board_rows(tmp_path / "b", b, _level_json(), prompt="A version of this video on the game's own level 3.")["Reference: the board"]
    assert row["status"] == "info" and "game's own level" in row["detail"]
    row = _board_rows(tmp_path / "c", b, _level_json(8, 9), prompt="A version of this video on an 8x9 board.")["Reference: the board"]
    assert row["status"] == "pass" and "size" not in row["detail"].split("; the request")[0] and "the request's own: size" in row["detail"]
    none = _board_brief(board={})
    assert "no board was read" in _board_rows(tmp_path / "d", none, _level_json())["Reference: the board"]["detail"]


def test_the_board_is_read_when_play_is_first_on_screen():
    segs = [{"from_s": 0, "to_s": 2, "purpose": "other"}, {"from_s": 2, "to_s": 5, "purpose": "hook"},
            {"from_s": 5, "to_s": 9, "purpose": "gameplay"}]
    assert R.board_at({"structure": segs}, 9.0) == 2.3 and R.board_at({"structure": []}, 9.0) == 0.3
    assert R.board_at({"structure": [{"from_s": 8.95, "to_s": 9, "purpose": "gameplay"}]}, 9.0) == 8.9  # inside the clip


@needs_ffmpeg
def test_the_board_is_read_again_on_a_full_resolution_still(clips):
    """The owner's test (2026-10-17): the whole clip at 360p read another game's 12-block 7x7 board as 7 blocks on 5x5; one
    still of the first frame of play is read again with only the board question, and its board wins."""
    whole = {**NOTES, "board": {"columns": 5, "rows": 5, "shape": "open", "blocks": 7, "colours": ["blue"], "busy": "medium"},
             "structure": [{"from_s": 0, "to_s": 2, "purpose": "hook"}, {"from_s": 2, "to_s": 6, "purpose": "gameplay"}]}
    still = {"board": {**LOLTAP_BOARD, "blocks": 12}}
    vision, lines = FakeVision(whole, still), []
    a = R.read_video(clips / "short.mp4", SIMILAR, planner=FakePlanner(PLAN), client=vision, log=lines.append,
                     measure=lambda p: {"cuts_s": []})
    assert not a.get("error") and len(vision.asks) == 6 and vision.asks[1] == R.board_ask() and '"box": {"x"' in vision.asks[1]
    # then the short asks on the board: the colour count once and the size three times (2026-10-17: the symmetry is the
    # code's mirror measure, and the free daily quota counts every call)
    assert vision.asks[2] == R.COLOUR_COUNT_ASK and vision.asks[3:6] == [R.SIZE_ASK] * 3
    assert R.BOARD_QUESTION in vision.asks[1] and '"board": {"columns"' in vision.asks[1]
    br = a["board_read"]
    assert (br["width"], br["height"], br["model"]) == (320, 180, "fake-omni") and br["at_s"] == 0.3 and br["seconds"] >= 0
    assert a["notes"]["board"]["blocks"] == 12 and a["notes"]["board_whole"]["blocks"] == 7
    assert any(x.startswith("board: an open 6x6 board, 12 blocks in 6 colours") and "read on a still at 0.3 s, 320x180" in x
               for x in lines)
    assert any("obstacles (not used: not in Color Block Jam)" in x for x in lines)
    # no board in the still's answer: the whole clip's board stands, and the log says why
    vision, lines = FakeVision(whole, {"ending": "win"}), []
    a = R.read_video(clips / "short.mp4", SIMILAR, planner=FakePlanner(PLAN), client=vision, log=lines.append,
                     measure=lambda p: {"cuts_s": []})
    assert a["board_read"]["error"] == "no board in the answer" and a["notes"]["board"]["blocks"] == 7
    assert "board_whole" not in a["notes"] and any("the whole clip's; the still: no board in the answer" in x for x in lines)
    # a reading applied for the hook only still reads the board (2026-10-17: every reading is a general reading)
    hook = {**PLAN, "focus": ["hook"], "level": "targeted", "required_fields": ["hook"]}
    vision = FakeVision(whole, still)
    a = R.read_video(clips / "short.mp4", "Use this video's hook.", planner=FakePlanner(hook), client=vision,
                     measure=lambda p: {"cuts_s": []})
    assert len(vision.asks) == 6 and a["board_read"]["board"]["blocks"] == 12 and R.BOARD_QUESTION in vision.asks[0]
    b = _fresh()
    V.apply(b, "Use only this video's hook.", [a])
    same = lambda lv: {k: v for k, v in lv.items() if k != "moves"}  # noqa: E731 (moves: the play's fill, round 4)
    assert same(b["level"]) == same(_fresh()["level"])  # read, not applied


def test_the_games_own_wall_cells_named_as_obstacles_are_walls():
    """v9 (2026-10-17): the still read named the tool's own grey wall cells "4 dark grey fixed obstacles" on boards it called
    open. They are the game's walls: the shape is holes, and they are never "not used"; another game's bubbles stay
    obstacles and never make a shape."""
    bd = V.board_of({"board": {"columns": 5, "rows": 5, "shape": "open", "blocks": 6, "colours": ["red"],
                               "obstacles": ["4 dark grey fixed obstacles"]}})
    assert bd["shape"] == "holes" and bd["walls_named"] == ["4 dark grey fixed obstacles"] and bd["obstacles"] == []
    assert "so the shape is holes, not open" in V.board_text(bd)
    bd = V.board_of({"board": {**LOLTAP_BOARD}})
    assert bd["shape"] == "open" and bd["walls_named"] == [] and bd["obstacles"] == BUBBLES
    b = _fresh()
    prov = V.apply(b, SIMILAR, [_board_analysis(board={**LOLTAP_BOARD, "obstacles": ["grey barriers: 3"] + BUBBLES})])[0]
    assert b["level"]["shape"] == "holes" and not any("grey barriers" in x for x in prov["not_used"])
    assert "grey barriers: 3: the game's own walls (the board's shape)" in prov["mechanics"]
    assert len([x for x in prov["not_used"] if "bubble" in x]) == 3


# ---------- 2026-10-17: the owner's trailer (one true gameplay part), the general reading, the board crop, colours, HUD ----------

TRAILER2 = json.loads((Path(__file__).parent / "data" / "trailer2_rejected_reading.json").read_text())


def test_the_trailers_single_gameplay_part_is_now_accepted():
    """studio/1017-000049: Gemini read cbj_trailer_2.mp4 as ONE gameplay part 0-28.86 s (true: the trailer is one continuous
    stretch of play); the clock-scale rule rejected it twice and the whole reading was dropped."""
    notes, facts = TRAILER2["rejected_notes"], TRAILER2["facts"]
    assert notes["structure"] == [{**notes["structure"][0], "from_s": 0, "to_s": 28.86, "purpose": "gameplay"}]
    assert R.validate_notes(notes, facts, ["board", "concept", "structure"], general=True) == []
    # the case-10 wrong-unit structure is still rejected
    case10 = [{"from_s": 0, "to_s": 0.2, "purpose": "hook"}, {"from_s": 0.3, "to_s": 0.8, "purpose": "gameplay"},
              {"from_s": 4.1, "to_s": 4.4, "purpose": "payoff"}, {"from_s": 4.5, "to_s": 45, "purpose": "end_card"}]
    assert R.validate_notes({"structure": case10}, {"duration_s": 45.0}, ["concept"], general=True)[0].startswith(
        "the seconds are not on the clip's clock")
    # and an empty structure on a general reading is a problem of the parts (asked again, then the parts are dropped)
    assert R.validate_notes({"structure": []}, facts, [], general=True) == [
        "the structure is empty: every reading gives the parts, in order, with their seconds"]


def test_the_trailers_reading_becomes_a_brief():
    """The trailer's accepted reading: a Color Block Jam reference (LEVEL 25, TIME 01:05), its board applied, its HUD's level
    number taken, its clock not (the ending sets it unless it is a win)."""
    a = {"file": "cbj_trailer_2.mp4", "kind": "video", "focus": ["board", "concept", "structure"], "level": "full",
         "analysed_s": 28.86, "facts": TRAILER2["facts"], "notes": copy.deepcopy(TRAILER2["rejected_notes"]),
         "plan": {"constraints": []}, "confidence": 0.95}
    a["notes"]["ending"] = "stopped"  # the fifth wording: the clip stops mid-level
    a["notes"]["extras_seen"] = ["a freeze booster button", "a hammer booster button", "a vacuum booster button"]
    b = _fresh()
    prov = V.apply(b, SIMILAR, [a])[0]
    assert b["gameplay"]["ending"] == "cliffhanger" and V.mapped_ending(a["notes"]) == "cliffhanger"
    assert (b["level"]["source"], b["level"]["shape"], b["level"]["width"], b["level"]["height"], b["level"]["label"]) == \
        ("generate", "open", 5, 8, 25)
    assert "level.label" in b["changed"] and "the HUD shows Level 25, as in the reference" in B.control(b, "level")["plan"]
    # round 2, case 05: a cliffhanger takes the reference's starting clock (brief.validate then drops it: see below)
    assert b["gameplay"]["timer_s"] == 65
    assert prov["hud"] == {"level": 25, "clock_s": 65, "cbj": True, "took": ["the HUD's Level 25", "the clock at 01:05"]}
    boosters = [x for x in prov["not_used"] if "booster" in x]
    assert len(boosters) == 3 and all(x.endswith(": not used: not in Color Block Jam") for x in boosters)


@pytest.mark.parametrize("ending, timer", [("win", 65), ("near_fail", None)])
def test_a_color_block_jam_reference_gives_its_clock_only_for_a_win(ending, timer):
    notes = {**NOTES, "game_or_product": "Color Block Jam", "hud": {"level": "LEVEL 25", "clock": "01:05"},
             "board": {"columns": 5, "rows": 7, "shape": "holes", "blocks": 9, "colours": ["purple"]}}
    b = _fresh()
    b["gameplay"]["ending"] = ending
    V.apply(b, "A version of this video, a " + ("clean win" if ending == "win" else "near-fail") + ".", [_analysis(["concept"], notes)])
    assert b["gameplay"]["timer_s"] == timer and b["level"]["label"] == 25
    if timer:
        assert "gameplay.clock" in b["changed"] and "the clock starts at 01:05" in B.control(b, "difficulty_pacing")["plan"]
        assert B.check(b)["gameplay"]["timer_s"] == 65  # within what brief.validate accepts


def test_the_requests_own_label_and_clock_win_and_another_game_gives_neither():
    notes = {**NOTES, "game_or_product": "Color Block Jam", "hud": {"level": "LEVEL 25", "clock": "01:05"},
             "board": {"columns": 5, "rows": 7, "shape": "holes", "blocks": 9, "colours": ["purple"]}}
    b = _fresh()
    b["gameplay"]["ending"], b["gameplay"]["timer_s"] = "win", 90
    V.apply(b, "A version of this video, a clean win, with a 90 second timer.", [_analysis(["concept"], notes)])
    assert b["gameplay"]["timer_s"] == 90
    other = {**notes, "game_or_product": "a rainforest block game", "hud": {"level": None, "clock": None}, "screen_text": []}
    b = _fresh()
    prov = V.apply(b, SIMILAR, [_analysis(["concept"], other)])[0]
    assert b["level"]["label"] is None and "hud" not in prov
    assert V.hud_of({"screen_text": ["LEVEL 7", "TIME 00:59"]}) == {"level": 7, "clock_s": 59, "cbj": True}


@pytest.mark.parametrize("read, slots, note", [
    (["purple", "magenta", "teal", "green"], ["Purple", "Red", "Blue", "Green"],
     "magenta -> red: the game has no magenta, purple is taken by purple"),
    (["dark green", "blue", "light blue", "yellow", "red", "purple", "orange"],
     ["DarkGreen", "Blue", "Green", "Yellow", "Red", "Purple", "Orange"],
     "light blue -> green: the game has no light blue, blue is taken by blue"),
    (["green", "light blue", "red", "yellow", "pink/magenta", "orange", "green"], ["Green", "Blue", "Red", "Yellow", "Purple", "Orange"],
     "pink -> purple: the game has no pink"),
    (["blue", "yellow", "red"], ["Blue", "Yellow", "Red"], None),
])
def test_distinct_reference_colours_stay_distinct(read, slots, note):
    """2026-10-17: the trailers' purple and magenta both read as purple lost a colour. Each distinct colour gets its own
    game colour (the nearest free one), and the card says why."""
    cm = V.board_colours(read)
    assert cm["slots"] == slots and len(set(cm["slots"])) == len(cm["slots"])
    notes_ = [m["note"] for m in cm["map"] if m["note"]]
    assert (note in notes_) if note else notes_ == []
    bd = V.board_of({"board": {"columns": 6, "rows": 6, "colours": read}})
    assert bd["colours"] == slots and (not note or note in V.board_text(bd))
    many = V.board_colours(["green", "yellow", "blue", "red", "orange", "purple", "dark green", "pink", "white"])
    assert len(many["slots"]) == 7 and many["dropped"] == ["pink (as purple)"] and many["unmapped"] == ["white"]
    # nine names for seven colours (refs-v1, trailer 3): the closest names merge, never two of the game's own colours
    nine = V.board_colours(["blue", "dark blue", "light blue", "yellow", "green", "magenta", "red", "orange", "purple"])
    assert len(set(nine["slots"])) == 7 and nine["dropped"][0] == "purple (as magenta)" and not any("orange (" in x for x in nine["dropped"])


@needs_ffmpeg
def test_a_small_board_is_read_again_on_a_crop_of_its_box(clips):
    """2026-10-17, the owner's trailer: the game window is a portrait strip in a 1920x1080 frame. A box under a quarter
    of the frame is cropped (with a 10% margin, enlarged to 1024 px) and read again; the crop's board wins."""
    whole = {**NOTES, "board": {"columns": 5, "rows": 5, "blocks": 7, "colours": ["blue"]},
             "structure": [{"from_s": 0, "to_s": 6, "purpose": "gameplay"}]}
    frame = {"board": {"columns": 5, "rows": 6, "blocks": 7, "colours": ["purple"]}, "box": {"x": 0.3, "y": 0.1, "w": 0.3, "h": 0.6}}
    crop = {"board": {"columns": 5, "rows": 7, "shape": "holes", "blocks": 9, "colours": ["purple", "magenta", "teal", "green"]}}
    vision = FakeVision(whole, frame, crop)
    a = R.read_video(clips / "short.mp4", SIMILAR, planner=FakePlanner(PLAN), client=vision, measure=lambda p: {"cuts_s": []})
    br = a["board_read"]
    assert len(vision.asks) == 7 and vision.asks[2] == R.board_ask(crop=True) and '"box"' not in vision.asks[2]
    assert br["box"] == {"x": 0.3, "y": 0.1, "w": 0.3, "h": 0.6} and br["crop"]["read"] and max(br["crop"]["width"], br["crop"]["height"]) == 1024
    assert (br["crop"]["x0"], br["crop"]["y0"], br["crop"]["x1"], br["crop"]["y1"]) == (86, 7, 202, 137)  # a 10% margin of the box on each side, on 320x180
    assert a["notes"]["board"]["blocks"] == 9 and br["board_frame"]["blocks"] == 7 and a["notes"]["board_whole"]["blocks"] == 7
    # a board that fills the frame is not cropped
    vision = FakeVision(whole, {**frame, "box": {"x": 0.2, "y": 0.05, "w": 0.4, "h": 0.9}})
    a = R.read_video(clips / "short.mp4", SIMILAR, planner=FakePlanner(PLAN), client=vision, measure=lambda p: {"cuts_s": []})
    assert len(vision.asks) == 6 and "crop" not in a["board_read"] and a["notes"]["board"]["rows"] == 6


def test_the_board_box_is_read_in_any_unit():
    assert R.board_box({"x": 0.3, "y": 0.1, "w": 0.3, "h": 0.6}) == {"x": 0.3, "y": 0.1, "w": 0.3, "h": 0.6}
    assert R.board_box([576, 108, 576, 864], 1920, 1080) == {"x": 0.3, "y": 0.1, "w": 0.3, "h": 0.8}
    assert R.board_box({"x": 0.9, "y": 0.0, "w": 0.5, "h": 1.0}) == {"x": 0.9, "y": 0.0, "w": 0.1, "h": 1.0}  # clipped to the frame
    assert R.board_box({"x": "?"}) is None and R.board_box(None) is None and R.board_box({"x": 0, "y": 0, "w": 0, "h": 1}) is None


def test_the_general_reading_asks_the_hud_and_what_the_game_does_not_have():
    for prompt in (SIMILAR, "Use this video's hook.", "Match the look of this video."):
        ask = R.video_ask(R.ReadingPlan.from_words(prompt), FACTS, prompt)
        for q in R.GENERAL_QUESTIONS:
            assert ask.count(q) == 1, (prompt, q)
        assert '"hud": {"level"' in ask and '"extras_seen"' in ask and "stopped (the clip stops mid-level" in ask
        assert "REQUIRED: what_it_shows, game_or_product" in ask and "hud, framing, board, mechanics_seen, extras_seen" in ask


def test_the_part_rows_are_info_when_the_parts_were_dropped(tmp_path):
    b = _guided_brief()
    a = b["planner"]["references"][0]
    a["parts_dropped"], a["notes"]["structure"] = "the parts were not usable: part 1 is outside the clip", []
    rows = _rows(tmp_path, b)
    for k in ("the purposes in order", "the part lengths"):
        assert rows[k]["status"] == "info" and "the parts were not usable" in rows[k]["detail"]
    assert rows["the ending"]["status"] == "pass"  # the rest is still judged


def test_the_board_asks_each_distinct_colour_as_seen():
    """refs-v0 (2026-10-17): told to name every colour as one of the game's seven, the reader called the trailer's magenta
    "purple" and its teal "blue", and two colours were lost before the code could keep them apart."""
    ask = R.video_ask(R.ReadingPlan.from_words(SIMILAR), FACTS, SIMILAR)
    assert "each distinct block colour ONCE" in ask and "purple and magenta" in ask and "pink or magenta is purple" not in ask
    assert "distinct colours (each once, named as seen" in R.BOARD_QUESTION
    assert '"extras_seen": ["anything else on screen' in R.board_ask() and '"extras_seen"' not in R.board_ask(crop=True)


@needs_ffmpeg
def test_the_stills_extras_join_the_reading(clips):
    """refs-v0: the trailer's booster buttons under the board were missed at 360p; the full frame names them."""
    whole = {**NOTES, "extras_seen": ["a coin counter"], "structure": [{"from_s": 0, "to_s": 6, "purpose": "gameplay"}]}
    frame = {"board": {"columns": 5, "rows": 7, "blocks": 9, "colours": ["purple", "magenta"]},
             "box": {"x": 0.05, "y": 0.05, "w": 0.9, "h": 0.9}, "extras_seen": ["a freeze booster button", "a hammer booster button"]}
    a = R.read_video(clips / "short.mp4", SIMILAR, planner=FakePlanner(PLAN), client=FakeVision(whole, frame),
                     measure=lambda p: {"cuts_s": []})
    assert a["notes"]["extras_seen"] == ["a coin counter", "a freeze booster button", "a hammer booster button"]
    lines, _ = V.mechanic_lines(a["notes"])
    assert "a freeze booster button: not used: not in Color Block Jam" in lines and "a coin counter: the game's own HUD" in lines
    assert V.mechanic_lines({"mechanics_seen": ["grid"]})[0] == ["grid: the game's own board"]


def _trailer2_board(**over):
    """The trailer-2 board as refs-v1 read it: 4x7 holes, 10 blocks, varied pieces (the truth: about 5x7, 9 blocks)."""
    return {"columns": 4, "rows": 7, "shape": "holes", "blocks": 10, "colours": ["teal", "magenta", "purple", "green"],
            "pieces": "varied", "gates_sides": 2, "obstacles": [], "busy": "medium", **over}


def test_the_board_grows_a_cell_before_its_blocks_are_cut():
    """2026-10-17 (refs-v1, trailer 2): the 4x7 holes board read holds 6 blocks at the generator's packed fill, and the
    brief took 6 of the 10 read. The board first grows a cell a side (within what the generator builds), then blocks are
    cut, and the card says which."""
    assert V.grow_for_blocks(10, "holes", 4, 7, "varied") == (5, 8, 9)
    assert V.grow_for_blocks(8, "holes", 4, 7, "varied") == (5, 7, 8)  # the smallest board that holds them
    b = _fresh()
    prov = V.apply(b, SIMILAR, [_board_analysis(board=_trailer2_board())])[0]
    lv = b["level"]
    assert (lv["shape"], lv["width"], lv["height"], lv["blocks"]) == ("holes", 5, 8, 9)
    fit = "the board read 4x7 holds 6; 5x8 is used so 9 fit (of the 10 read; a cell a side is the most the board grows)"
    assert prov["board"]["fit"] == fit and fit in b["assumptions"]
    b = _fresh()
    prov = V.apply(b, SIMILAR, [_board_analysis(board=_trailer2_board(blocks=8))])[0]
    assert (b["level"]["width"], b["level"]["height"], b["level"]["blocks"]) == (5, 7, 8)
    assert prov["board"]["fit"] == "the board read 4x7 holds 6; 5x7 is used so 8 fit"
    # the request's own size is never grown: the blocks are cut instead
    b = _fresh()
    b["level"].update(width=4, height=7)
    prov = V.apply(b, "A version of this video on a 4x7 board.", [_board_analysis(board=_trailer2_board())])[0]
    assert (b["level"]["width"], b["level"]["height"], b["level"]["blocks"]) == (4, 7, 6)
    assert prov["board"]["fit"] == "the reference shows 10 blocks; 6 is the most this board takes in a generated level"


def test_a_mirror_symmetric_board_gives_the_generators_symmetric_look():
    """2026-10-17 (trailer 3): a mirror-symmetric layout becomes the generator's own "symmetric" look when the request
    says nothing about the level's look."""
    assert "symmetric" in R.NOTE_FIELDS["board"] and "mirror-symmetric" in R.BOARD_QUESTION
    b = _fresh()
    prov = V.apply(b, SIMILAR, [_board_analysis(board={**LOLTAP_BOARD, "symmetric": True})])[0]
    assert "symmetric" in b["level"]["style"] and "level.style" in b["changed"] and "symmetric" in prov["board"]["took"]
    assert "mirror-symmetric" in B.control(b, "level")["plan"] and "mirror-symmetric" in prov["board"]["text"]
    for prompt in ("A version of this video on a packed board.", "A version of this video, colourful.",
                   "A version of this video with a spacious board."):
        b = _fresh()
        V.apply(b, prompt, [_board_analysis(board={**LOLTAP_BOARD, "symmetric": True})])
        assert "symmetric" not in b["level"]["style"], prompt  # the request's own look
    b = _fresh()
    V.apply(b, SIMILAR, [_board_analysis(board={**LOLTAP_BOARD, "symmetric": False})])
    assert "symmetric" not in b["level"]["style"]


# ---------- round 1 (2026-10-17): pure play, a few walls, symmetry votes, the colour count ----------

def _pure_play_analysis(**over):
    notes = {**NOTES, "ending": "stopped", "mistakes": [], "mistakes_shown": False, "captions_seen": [], "cta": "",
             "structure": [{"from_s": 0, "to_s": 30.1, "purpose": "gameplay"}], "board": _trailer2_board()}
    a = _analysis(["concept"], notes, **over)
    a["facts"] = {"duration_s": 30.1}
    a["plan"] = {"constraints": ["Length around 30 s, matching the source"]}  # the planner's, from the source (round 1)
    return a


def test_a_reference_that_is_all_play_keeps_the_ad_play():
    """Round 1: both trailers are one continuous stretch of play; their ads were 56-64% play, the question held 9 s.
    The brief's own fields now keep the most play the engine allows: no still opening, the shortest hold, a calm tempo
    (studio then picks the longest recording that fits), and the long play's moves (no longer blocked by the planner's
    own "matching the source" length)."""
    b = _fresh()
    prov = V.apply(b, SIMILAR, [_pure_play_analysis()])[0]
    sq, pc, lv = b["sequence"], b["pacing"], b["level"]
    assert (sq["intro_s"], sq["hold_s"], pc["tempo"], b["gameplay"]["ending"]) == (0.0, 0.0, "calm", "cliffhanger")
    assert lv["moves"] and "level.moves" in b["changed"] and "sequence.timing" in b["changed"] and "pacing.tempo" in b["changed"]
    assert prov["pure_play"] == 1.0 and "play from start to end" in B.control(b, "sequence")["plan"]
    assert "length" not in prov["stated"]  # "Length around 30 s, matching the source" is the source's, not the request's
    assert B.check(b)["sequence"]["intro_s"] == 0.0 and B.check(b)["sequence"]["hold_s"] == 0.0  # within brief.validate
    # a reference with an end card, or play under 90%, is not all play
    b = _fresh()
    V.apply(b, SIMILAR, [_analysis(["concept"])])
    assert b["sequence"]["intro_s"] is None and "pure_play" not in b["reference"]
    # the request's own tempo and hold win
    b = _fresh()
    prov = V.apply(b, "A version of this video, fast-paced, with the result held 3 seconds.", [_pure_play_analysis()])[0]
    assert b["pacing"]["tempo"] != "calm" and b["sequence"]["hold_s"] is None and b["sequence"]["intro_s"] == 0.0
    assert V.own_constraints(["Length around 30 s, matching the source", "45 s long", "as in the reference video"]) == ["45 s long"]


def test_the_part_lengths_keep_the_ads_call_to_action_and_its_hook_over_play(tmp_path):
    """Round 1: with no end card in the reference, the ad's end card up to the engine's shortest (3 s) is not counted
    against the play share, and with no hook part the hook caption over the play counts as play."""
    b = _guided_brief(notes={**NOTES, "structure": [{"from_s": 0, "to_s": 30, "purpose": "gameplay"}]})
    b["planner"]["references"][0]["facts"] = {"duration_s": 30.0}
    m = _manifest(duration_s=30.0, parts=[{"id": "play", "from_s": 0.0, "to_s": 22.0}, {"id": "question", "from_s": 22.0, "to_s": 24.0},
                                         {"id": "end", "from_s": 24.0, "to_s": 30.0}],
                  layers=[{"id": "hook", "kind": "caption", "text": "Can you clear it?", "from_s": 0.0, "to_s": 3.0}])
    row = _rows(tmp_path, b, m)["the part lengths"]
    assert row["status"] == "pass" and "play 100% of the reference, 81% of the ad" in row["detail"]
    assert "the ad's first 3 s of end card (its call to action, the engine's shortest) are not counted" in row["detail"]
    assert "the ad's hook caption over the play counts as play" in row["detail"]
    short = _manifest(duration_s=30.0, parts=[{"id": "play", "from_s": 0.0, "to_s": 17.8}, {"id": "question", "from_s": 17.8, "to_s": 22.8},
                                             {"id": "end", "from_s": 22.8, "to_s": 30.0}], layers=m["layers"])
    assert _rows(tmp_path / "b", b, short)["the part lengths"]["status"] == "failed"  # round 1's trailer-3 ad still fails


@pytest.mark.parametrize("walls, shape, size, n_walls", [
    (0, "open", (5, 8), 0), (1, "open", (5, 8), 0), (2, "holes", (5, 7), 3), (3, "holes", (5, 7), 3), (5, "holes", (5, 8), 5),
])
def test_a_few_inner_walls_map_to_the_closest_board_the_generator_builds(walls, shape, size, n_walls):
    """Round 1: trailer 2 has ONE 2-cell inner wall; its 5x8 holes board got five wall cells. The wall count read picks
    open or the generator's fewest-walls holes board (3 walls on an odd width under 8 rows), within a cell a side."""
    assert V.wall_choice(walls, 4, 7, 10, "varied")[:2] == (shape, n_walls)
    b = _fresh()
    prov = V.apply(b, SIMILAR, [_board_analysis(board=_trailer2_board(wall_cells=walls))])[0]
    lv = b["level"]
    assert (lv["shape"], (lv["width"], lv["height"])) == (shape, size)
    from cbj.generate import holes_for
    assert len(holes_for(lv["shape"], lv["width"], lv["height"])) == n_walls if shape == "holes" else True
    assert prov["board_walls"].startswith(f"the reference shows {walls} wall cell") and prov["board_walls"] in b["assumptions"]
    assert ("open board (no walls)" in prov["board_walls"]) == (shape == "open")


def test_the_board_row_shows_the_wall_count_as_info(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "BOARD_RELIABLE", frozenset({"shape", "size", "blocks", "colours"}))
    b = _board_brief(board={**LOLTAP_BOARD, "wall_cells": 0})
    row = _board_rows(tmp_path, b, _level_json(inactive=[(2, 2), (3, 3)]))["Reference: the board"]
    assert "walls: 0 read, 2 made, read approximately" in row["detail"]


FLOOR, RIM, BACK = (112, 122, 150), (58, 64, 84), (228, 230, 240)
GAME = {"green": (79, 187, 29), "dark green": (15, 93, 31), "teal": (31, 188, 176), "blue": (26, 51, 236),
        "light blue": (20, 172, 229), "purple": (114, 50, 210), "magenta": (168, 48, 186), "red": (173, 15, 47),
        "orange": (240, 117, 80), "yellow": (245, 180, 56), "pink": (245, 123, 251)}


def _board_png(path, layout: list[str], colours: dict, cell: int = 60, rim: int = 30, margin: int = 24, buttons: bool = False):
    """A synthetic board crop: a light background, a dark rim, grey-blue floor cells, and a block wherever the layout
    has a letter (colours: letter -> RGB); a thin seam between cells as in the game's render."""
    from PIL import Image, ImageDraw
    rows, cols = len(layout), len(layout[0])
    W, H = cols * cell + 2 * (rim + margin), rows * cell + 2 * (rim + margin) + (2 * cell if buttons else 0)
    im = Image.new("RGB", (W, H), BACK)
    d = ImageDraw.Draw(im)
    bottom = H - margin - (2 * cell if buttons else 0)
    d.rectangle([margin, margin, W - margin, bottom], fill=RIM)
    if buttons:  # a row of booster buttons under the board (trailer 2): not part of the grid
        for k in range(4):
            x = margin + rim + (k + 0.5) * (W - 2 * (margin + rim)) / 4
            d.ellipse([x - cell * 0.4, bottom + cell * 0.6, x + cell * 0.4, bottom + cell * 1.4], fill=(40, 120, 230))
    for r, line in enumerate(layout):
        for c, ch in enumerate(line):
            x, y = margin + rim + c * cell, margin + rim + r * cell
            d.rectangle([x + 1, y + 1, x + cell - 2, y + cell - 2], fill=colours.get(ch, FLOOR) if ch != "." else FLOOR)
    im.save(path)
    return path


SYMMETRIC = ["ab..ba", "cddddc", ".e..e.", "ffgggf", "h....h", "iijjii"]  # mirror-symmetric shapes, colours differ
ASYMMETRIC = ["aab...", "a.bccc", "dd...e", "f..gge", "fhh..e", "....ii"]


@pytest.mark.parametrize("layout, symmetric", [(SYMMETRIC, True), (ASYMMETRIC, False)])
def test_the_symmetry_is_measured_on_the_occupancy_whatever_the_colours(tmp_path, layout, symmetric):
    """Round 1: the reader could not see trailer 3's symmetry. The block mask is compared with its left-right and
    top-bottom mirrors (the best axis near the middle; intersection over union 0.8), the colours ignored; the cell grid's
    own match is kept as info."""
    cols = {ch: list(GAME.values())[i % len(GAME)] for i, ch in enumerate("abcdefghij")}  # mirrored pieces differ in colour
    m = R.measure_board(_board_png(tmp_path / "b.png", layout, cols), 6, 6)
    assert m["grid"] == [[0 if ch == "." else 1 for ch in line] for line in layout]
    assert m["symmetric"] is symmetric and (m["left_right"] == 1.0) is symmetric and (m["mirror_lr"] >= 0.8) is symmetric
    # the same symmetric board read with a wrong grid size is still symmetric (refs-v8: 8x8 for about 8x7)
    if symmetric:
        assert R.measure_board(tmp_path / "b.png", 7, 7)["symmetric"] and R.measure_board(tmp_path / "b.png", 5, 6)["symmetric"]


@pytest.mark.parametrize("names, count", [
    (["purple", "magenta", "teal", "green"], 4),  # trailer 2: purple and magenta stay apart
    (["dark green", "blue", "light blue", "yellow", "red", "purple", "orange"], 7),  # trailer 3: green families, blues
    (["green", "dark green"], 2), (["blue", "light blue"], 2), (["red", "red"], 1),
])
def test_the_colours_are_counted_by_hue_and_lightness(tmp_path, names, count):
    layout = ["aaabbb", "aaabbb", "cccddd", "cccddd", "eeefff", "eeeggg"]
    letters = "abcdefg"
    cols = {letters[i]: GAME[names[i % len(names)]] for i in range(7)}
    m = R.measure_board(_board_png(tmp_path / "c.png", layout, cols), 6, 6)
    assert m["colour_count"] == count, m["clusters"]


@needs_ffmpeg
def test_the_code_measure_decides_the_symmetry_and_can_raise_the_colour_count(clips, monkeypatch):
    """Round 1: the code's measure on the crop decides the symmetry (the reader's three votes kept beside it), and the
    colour count is the larger of the code's and the reader's majority of three asks, at most 7; a colour the code found
    and the reader did not is named from its cluster."""
    whole = {**NOTES, "structure": [{"from_s": 0, "to_s": 6, "purpose": "gameplay"}]}
    frame = {"board": {"columns": 6, "rows": 6, "blocks": 12, "symmetric": False, "colours": ["teal", "purple", "green", "magenta"]},
             "box": {"x": 0.2, "y": 0.05, "w": 0.5, "h": 0.9}}  # the board's own shape (a box off it is rejected)
    measured = {"grid": [[1] * 6] * 6, "left_right": 0.9, "top_bottom": 0.6, "symmetric": True, "colour_count": 4,
                "clusters": [{"rgb": [115, 50, 210], "cells": 6}, {"rgb": [79, 187, 29], "cells": 6},
                             {"rgb": [31, 188, 176], "cells": 5}, {"rgb": [168, 48, 186], "cells": 4}], "region": [0, 0, 1, 1]}
    monkeypatch.setattr(R, "measure_board", lambda image, c, r: measured)
    vision = FakeVision(whole, frame, {"colour_count": 3, "colours": ["teal", "purple", "green"]})
    a = R.read_video(clips / "short.mp4", SIMILAR, planner=FakePlanner(PLAN), client=vision, measure=lambda p: {"cuts_s": []})
    br, bd = a["board_read"], a["notes"]["board"]
    assert R.COLOUR_COUNT_ASK in vision.asks and not any("symmetric\": true or false}" in x for x in vision.asks[2:])
    assert bd["symmetric"] is True and bd["symmetric_first"] is False and bd["symmetric_source"] == "measured"
    assert br["measured"] == measured and "symmetry_votes" not in br
    # the reader counted 3 for its own 4 names; the code's clusters confirm all 4, so none is merged away (trailer 2)
    assert br["colour_counts"] == [3] and (br["colour_count_model"], br["colour_count_code"], br["colour_count"]) == (3, 4, 4)
    assert len(bd["colours"]) == 4 and len(V.board_of(a["notes"])["colours"]) == 4  # four distinct game colours
    assert R.count_majority([6, 7, 6]) == 6 and R.count_majority([5, 6, 7]) == 6 and R.count_majority([None, None, None]) is None
    assert R.majority([True, None, False]) is None and R.majority([False, False, True]) is False
    six = V.board_colours(["green", "cyan", "blue", "red", "yellow", "magenta", "purple", "orange"], 6)
    assert six["slots"] == ["Green", "Blue", "Red", "Yellow", "Purple", "Orange"]


def test_the_code_confirms_read_colours_and_never_adds_one():
    """Round 1, third run (trailer 2): the cut crop held the booster buttons, and their cluster was added as a fifth
    colour, "blue". The code's clusters only confirm the board's own names, one cluster each: a cluster no name stands
    for adds nothing."""
    clusters = [{"rgb": [116, 51, 214], "cells": 9}, {"rgb": [176, 47, 195], "cells": 6}, {"rgb": [32, 176, 172], "cells": 6},
                {"rgb": [63, 107, 214], "cells": 5}, {"rgb": [80, 189, 32], "cells": 4}]  # the run's five, the fourth the buttons
    names = ["magenta", "purple", "teal", "green"]
    assert sorted(R.confirmed_names(clusters, names)) == ["green", "magenta", "purple", "teal"]
    assert R.confirmed_names(clusters, ["teal", "purple", "green"]) == ["teal", "purple", "green"] or \
        sorted(R.confirmed_names(clusters, ["teal", "purple", "green"])) == ["green", "purple", "teal"]
    assert R.confirmed_names([], names) == [] and R.confirmed_names(clusters, ["white"]) == []


def test_the_colour_count_merges_only_names_close_to_a_counted_colour():
    """refs-v4: trailer 2's count said 3 (magenta, purple, green) and missed the teal the board read had; LolTap's said 6
    for 7 names. A surplus name merges into a counted colour only when it is close to one (cyan into blue, magenta into
    purple); a name far from all of them is a colour the count missed, and stays."""
    t2 = V.board_colours(["cyan", "purple", "magenta", "green"], 3, ["magenta", "purple", "green"])
    assert t2["slots"] == ["Blue", "Purple", "Red", "Green"] and t2["dropped"] == []
    lol = V.board_colours(["green", "cyan", "red", "yellow", "purple", "magenta", "orange"], 6,
                          ["green", "red", "yellow", "blue", "purple", "orange"])
    assert lol["slots"] == ["Green", "Blue", "Red", "Yellow", "Purple", "Orange"] and lol["dropped"] == ["magenta (as purple)"]
    t3 = V.board_colours(["blue", "dark green", "yellow", "red", "purple", "light blue", "orange"], 7,
                         ["blue", "green", "yellow", "red", "purple", "light blue", "orange"])
    assert len(set(t3["slots"])) == 7
    # a count without names merges the closest names down to it
    assert len(V.board_colours(["green", "cyan", "blue", "red", "yellow", "magenta", "purple", "orange"], 6)["slots"]) == 6


def test_the_grid_leaves_out_the_buttons_under_the_board(tmp_path):
    """refs-v6: trailer 2's crop holds its booster buttons under the board; the grid is the longest run of board rows,
    so the blue buttons add no colour."""
    layout = ["aaabbb", "aaabbb", "cccddd", "cccddd", "aa..dd", "......"]
    cols = {"a": GAME["purple"], "b": GAME["magenta"], "c": GAME["teal"], "d": GAME["green"]}
    m = R.measure_board(_board_png(tmp_path / "btn.png", layout, cols, buttons=True), 6, 6)
    assert m["colour_count"] == 4 and m["grid"][5] == [0] * 6


# ---------- round 1 rerun (2026-10-17): revisions keep the reference, fill, the busy cut, a shorter reference ----------

def test_a_revision_keeps_what_the_reference_gave():
    """Round 1 rerun, trailer 2: the reference's open board was re-planned as holes and packed after the viewer's "keep
    the board full longer". A guided revision pins the fields videoref set unless the miss is that field's own row."""
    from cbj.workflows import guided
    before = _fresh()
    V.apply(before, SIMILAR, [_board_analysis(board=_trailer2_board(wall_cells=1))])
    assert {"level.shape", "level.size", "level.blocks", "gameplay.ending"} <= set(before["reference"]["set"])
    after = copy.deepcopy(before)
    after["level"].update(shape="holes", style=["packed"], blocks=10)
    after["gameplay"]["ending"] = "near_fail"
    after["concept"]["hook"] = "Keep it full!"
    notes = guided.pin_reference(before, after, [{"check": "Reference: the part lengths", "status": "failed"}])
    assert (after["level"]["shape"], after["level"]["style"], after["level"]["blocks"]) == (before["level"]["shape"],
                                                                                          before["level"]["style"], before["level"]["blocks"])
    assert after["gameplay"]["ending"] == before["gameplay"]["ending"] and after["concept"]["hook"] == "Keep it full!"
    assert any(n.startswith("the reference's board is kept") for n in notes) and any("ending is kept" in n for n in notes)
    # the board's own row missed: still the base version's adapted board (round 2, case 04: the row's miss had let the
    # revisions re-plan the board from the raw reading); the board row's miss is fixed by a new take
    after = copy.deepcopy(before)
    after["level"]["shape"], after["gameplay"]["ending"] = "holes", "near_fail"
    guided.pin_reference(before, after, [{"check": "Reference: the board", "status": "failed"}])
    assert after["level"]["shape"] == before["level"]["shape"] and after["gameplay"]["ending"] == before["gameplay"]["ending"]
    # an asked fact about the board still lets the revision change it
    after = copy.deepcopy(before)
    after["level"]["shape"] = "holes"
    guided.pin_reference(before, after, [{"check": "Asked: board shape", "status": "failed"}])
    assert after["level"]["shape"] == "holes"


CASE04 = json.loads((Path(__file__).parent / "data" / "case04_v1.json").read_text())


def test_case_04_keeps_its_adapted_board(tmp_path, monkeypatch):
    """Round 2, case 04 (studio/1017-092519): v1's brief had the adapted board, open 5x7 with 9 blocks (the single-wall
    rule mapped "holes, 1 wall cell" to open; the growth took 4x7 to 5x7), and the made level matched. The board row
    compared the raw "holes 4x7" reading and failed, and the revisions re-planned holes 4x7. Now the row measures the
    adapted board and passes, and a revision keeps v1's adapted board whatever the planner says."""
    from cbj.workflows import guided
    monkeypatch.setattr(audit, "BOARD_RELIABLE", frozenset({"shape", "size", "blocks", "colours"}))
    v1 = CASE04["brief"]
    assert (v1["level"]["shape"], v1["level"]["width"], v1["level"]["height"], v1["level"]["blocks"]) == ("open", 5, 7, 9)
    assert CASE04["failed"][0]["check"] == "Reference: the board" and "shape holes read, open made" in CASE04["failed"][0]["detail"]
    a = v1["planner"]["references"][0]
    vdir = tmp_path / "v1"
    vdir.mkdir()
    (vdir / "level.json").write_text(json.dumps(CASE04["level"]))
    row = audit._board_row(CASE04["prompt"], v1, a, a["notes"], a["focus"], vdir)
    assert row["status"] == "pass" and "shape holes read, open taken, open made" in row["detail"], row
    after = copy.deepcopy(v1)
    after["level"] = copy.deepcopy(CASE04["v2_level"])  # what the revision planned: holes 4x7 from the reading
    notes = guided.pin_reference(v1, after, CASE04["failed"])
    assert (after["level"]["shape"], after["level"]["width"], after["level"]["height"], after["level"]["blocks"]) == ("open", 5, 7, 9)
    assert any(n.startswith("the reference's board is kept") for n in notes)


def test_a_capped_block_count_keeps_the_references_fill():
    """Round 1 rerun, trailer 3: about 16 blocks on 8x8 became 10 blocks on a sparse 9x10. The board shrinks so 10 blocks
    keep the reference's fill, and a full board takes the generator's packed look."""
    assert V.keep_fill(10, 16 / 64, "open", 8, 8, "varied") in ((6, 7), (7, 6))
    b = _fresh()
    prov = V.apply(b, SIMILAR, [_board_analysis(board={**_trailer2_board(), "columns": 8, "rows": 8, "shape": "open",
                                                       "blocks": 16, "wall_cells": 0, "occupancy": 0.8})])[0]
    lv = b["level"]
    assert lv["blocks"] == 10 and (lv["width"], lv["height"]) in ((6, 7), (7, 6)) and "packed" in lv["style"]
    assert "to keep that fill" in prov["board"]["fit"] and "packed" in B.control(b, "level")["plan"]
    assert any("80% of its cells under blocks, measured" in x for x in b["assumptions"])
    # a board with room is not packed, a "busy" reading alone never packs it, and the request's own look wins
    for board in ({**_trailer2_board(), "blocks": 5, "occupancy": 0.3}, {**_trailer2_board(), "busy": "busy"},
                  {**_trailer2_board(), "busy": "busy", "occupancy": 0.4}):
        b = _fresh()
        V.apply(b, SIMILAR, [_board_analysis(board=board)])
        assert "packed" not in b["level"]["style"], board
    b = _fresh()
    V.apply(b, "A version of this video with a spacious board.", [_board_analysis(board={**_trailer2_board(), "occupancy": 0.9})])
    assert "packed" not in b["level"]["style"]


def test_the_size_is_the_median_of_four_reads():
    assert R.median_size([10, 10], [[8, 8], [8, 7], [9, 8]]) == [8, 8]
    assert R.median_size([5, 8], [[5, 7], None, [5, 7]]) == [5, 7] and R.median_size(None, [None, None]) is None


def test_a_reference_that_stops_with_a_crowded_board_cuts_with_the_most_blocks_left():
    """Round 1 rerun, trailer 3: the reference stops mid-level with the board nearly full; the viewer asked for a busier
    cut. The cut comes with 3 blocks left, the most the game's cliffhanger allows."""
    b = _fresh()
    V.apply(b, SIMILAR, [_board_analysis(ending="stopped", ending_read={"ending": "cliffhanger", "blocks_left": 11})])
    assert b["gameplay"]["ending"] == "cliffhanger" and b["gameplay"]["blocks_left"] == 3
    assert "gameplay.blocks_left" in b["changed"] and B.check(b)["gameplay"]["blocks_left"] == 3
    b = _fresh()
    V.apply(b, SIMILAR, [_board_analysis(ending="stopped", ending_read={"ending": "cliffhanger", "blocks_left": 1})])
    assert b["gameplay"]["blocks_left"] is None
    b = _fresh()
    b["gameplay"]["blocks_left"] = 1
    V.apply(b, "A version of this video that cuts with one block left.", [_board_analysis(
        ending="stopped", ending_read={"ending": "cliffhanger", "blocks_left": 11})])
    assert b["gameplay"]["blocks_left"] == 1


def _lol_analysis():
    notes = {**NOTES, "ending": "stopped", "mistakes": [], "mistakes_shown": False,
             "structure": [{"from_s": 0, "to_s": 4, "purpose": "hook"}, {"from_s": 4, "to_s": 11, "purpose": "gameplay"},
                           {"from_s": 11, "to_s": 14.9, "purpose": "end_card"}], "board": copy.deepcopy(LOLTAP_BOARD)}
    a = _analysis(["concept"], notes)
    a["facts"] = {"duration_s": 14.9}
    return a


def test_a_shorter_reference_stretches_its_play(tmp_path):
    """Round 1 rerun, LolTap: a 15 s reference in a 30 s ad had its 3.9 s end card scaled to 9 s. The hook and the end
    card keep their own seconds and the play takes the extra time; the row compares them in seconds."""
    b = _fresh()
    prov = V.apply(b, SIMILAR, [_lol_analysis()])[0]
    assert b["pacing"]["length_s"] == 30.0 and (b["sequence"]["intro_s"], b["sequence"]["hold_s"], b["pacing"]["tempo"]) == (0.0, 0.0, "calm")
    assert prov["stretched"] == {"reference_s": 14.9, "ad_s": 30.0} and "pure_play" not in prov
    assert "the reference (14.9 s) is shorter than the ad (30 s)" in B.control(b, "sequence")["plan"]
    gb = _guided_brief(notes={**_lol_analysis()["notes"]})
    gb["planner"]["references"][0]["facts"] = {"duration_s": 14.9}
    good = _manifest(duration_s=30.0, parts=[{"id": "play", "from_s": 0.0, "to_s": 24.0}, {"id": "question", "from_s": 24.0, "to_s": 26.0},
                                            {"id": "end", "from_s": 26.0, "to_s": 30.0}],
                     layers=[{"id": "hook", "kind": "caption", "text": "Can you clear it?", "from_s": 0.0, "to_s": 3.5}])
    row = _rows(tmp_path / "a", gb, good)["the part lengths"]
    assert row["status"] == "pass" and "the reference (14.9 s) is shorter than the ad (30 s)" in row["detail"]
    # its 4 s hook is over max(3 s, 25% of 14.9 s): the first 1.5 s stay the hook, the rest is play (round 3, long_hooks)
    assert "end 3.9 s expected, 4.0 s in the ad" in row["detail"] and "hook 1.5 s expected, 3.5 s in the ad" in row["detail"]
    long_card = _manifest(duration_s=30.0, parts=[{"id": "play", "from_s": 0.0, "to_s": 13.0}, {"id": "question", "from_s": 13.0, "to_s": 21.0},
                                                 {"id": "end", "from_s": 21.0, "to_s": 30.0}], layers=good["layers"])
    assert _rows(tmp_path / "b", gb, long_card)["the part lengths"]["status"] == "failed"  # round 1's 9 s end card


def test_another_games_invented_hud_is_not_color_block_jam():
    """refs-v8: the reader gave LolTap "LEVEL 25" and a 00:00 clock (the schema's own example then said LEVEL 25)."""
    assert "LEVEL 25" not in R.NOTE_FIELDS["hud"]
    assert V.hud_of({"game_or_product": "Wood Color Jam", "hud": {"level": "25", "clock": "00:00"}})["cbj"] is False
    assert V.hud_of({"game_or_product": "", "hud": {"level": "LEVEL 25", "clock": "01:05"}})["cbj"] is True
    assert V.hud_of({"game_or_product": "Color Block Jam", "hud": {"level": None, "clock": None}})["cbj"] is True
    assert V.hud_of({"hud": {"clock": "00:00"}})["clock_s"] is None
    b = _fresh()
    notes = {**NOTES, "game_or_product": "Wood Color Jam", "hud": {"level": "25", "clock": "00:00"}, "board": LOLTAP_BOARD}
    V.apply(b, SIMILAR, [_analysis(["concept"], notes)])
    assert b["level"]["label"] is None


@needs_ffmpeg
def test_a_used_up_daily_quota_is_said_once_on_the_analysis(clips):
    vision = FakeVision({**NOTES, "structure": [{"from_s": 0, "to_s": 6, "purpose": "gameplay"}]})
    vision.errors = ["gemini-3.5-flash-lite: daily free quota used up (500 requests)"] * 2
    lines = []
    a = R.read_video(clips / "short.mp4", SIMILAR, planner=FakePlanner(PLAN), client=vision, log=lines.append,
                     measure=lambda p: {"cuts_s": []})
    assert a["quota"] == ["gemini-3.5-flash-lite: daily free quota used up (500 requests)"]
    assert sum("daily free quota used up" in x for x in lines) == 1


# ---------- round 1, third run (2026-10-17): crop sanity, pins that yield, the length, colours confirmed ----------

LOLTAP_READ = json.loads((Path(__file__).parent / "data" / "loltap_board_read.json").read_text())


def test_a_crop_that_disagrees_with_the_full_frame_is_not_used():
    """studio/1017-033814: 3.7-flash boxed LolTap's 6x6 board as a tall strip; the crop of part of it read "open 6x10, 4
    blocks, 3 colours" and won. The box is now rejected for its shape, and a crop that disagrees with the frame loses."""
    frame, crop = LOLTAP_READ["frame"], LOLTAP_READ["crop"]
    assert R.box_disagrees(LOLTAP_READ["box"], frame, LOLTAP_READ["width"], LOLTAP_READ["height"]).startswith(
        "the box is 0.59 wide for its height, the board 6x6 is 1.00")
    assert R.crop_disagrees(crop, frame) == "rows 10 against 6; 4 blocks against 13"
    assert R.crop_disagrees({**frame, "rows": 7, "blocks": 11}, frame) is None  # within 2 cells and 40%
    assert R.crop_disagrees({**frame, "colours": ["blue"]}, frame) == "1 of the frame's 6 colours"


@needs_ffmpeg
def test_the_full_frames_reading_stands_when_the_crop_disagrees(clips):
    whole = {**NOTES, "structure": [{"from_s": 0, "to_s": 6, "purpose": "gameplay"}]}
    frame = {"board": dict(LOLTAP_READ["frame"]), "box": {"x": 0.3, "y": 0.2, "w": 0.3, "h": 0.55}}  # a box of the board's shape
    lines = []
    vision = FakeVision(whole, frame, {"board": dict(LOLTAP_READ["crop"])})
    a = R.read_video(clips / "short.mp4", SIMILAR, planner=FakePlanner(PLAN), client=vision, log=lines.append,
                     measure=lambda p: {"cuts_s": []})
    br = a["board_read"]
    assert br["crop"]["disagreed"] == "rows 10 against 6; 4 blocks against 13" and br["board"]["blocks"] == 13
    assert any("the crop disagreed (rows 10 against 6; 4 blocks against 13): kept the full frame's reading" in x for x in lines)
    assert "measured" not in br  # the code does not measure a crop that is wrong
    # a box whose shape is not the board's is not cropped at all
    vision = FakeVision(whole, {"board": dict(LOLTAP_READ["frame"]), "box": LOLTAP_READ["box"]})
    a = R.read_video(clips / "short.mp4", SIMILAR, planner=FakePlanner(PLAN), client=vision, measure=lambda p: {"cuts_s": []})
    assert "crop" not in a["board_read"] and a["board_read"]["box_rejected"]["box"] == LOLTAP_READ["box"]


def test_a_revision_never_chases_the_part_lengths_with_the_length():
    """Round 1, third run, trailer 2: v1 30 s (the reference's 28.9 s), v3 45 s, raised to chase the part-length row."""
    from cbj.workflows import guided
    before = _fresh()
    V.apply(before, SIMILAR, [_pure_play_analysis()])
    assert "pacing.length" in before["reference"]["set"] and before["pacing"]["length_s"] == 30.0
    after = copy.deepcopy(before)
    after["pacing"]["length_s"] = 45.0
    after["sequence"]["hold_s"] = 1.0
    notes = guided.pin_reference(before, after, [{"check": "Reference: the part lengths", "status": "failed",
                                                  "detail": "play 100% of the reference, 81% of the ad"}])
    # the pure-play rule's timing is kept too (round 2, case 05, 2026-10-17: the revision's changes cut the play)
    assert after["pacing"]["length_s"] == 30.0 and after["sequence"]["hold_s"] == 0.0
    assert any(n.startswith("the reference's length is kept") for n in notes)
    assert any(n.startswith("the reference's timing is kept") for n in notes)


def test_a_board_too_small_to_fill_the_play_may_grow_in_a_revision():
    """Round 1, third run, LolTap: the wrong 4-block board gave 3.5 s of play and a 22 s end card; "gameplay at the
    centre" failed and both revisions kept the reference's 4 blocks. A short play lets the revision raise the blocks
    (and the size a cell a side)."""
    from cbj.workflows import guided
    before = _fresh()
    V.apply(before, SIMILAR, [_board_analysis(board={**LOLTAP_BOARD, "columns": 6, "rows": 6, "blocks": 4})])
    before["level"]["blocks"] = 4  # the board as round 1 read it (the play levers may raise it now)
    after = copy.deepcopy(before)
    notes = guided.pin_reference(before, after, [{"check": "Asked: gameplay at the centre (the case)", "status": "failed",
                                                  "detail": "gameplay is 3.5 s of 30 s (12%)"}])
    assert after["level"]["blocks"] == 7 and abs(after["level"]["width"] - 6) <= 1 and abs(after["level"]["height"] - 6) <= 1
    assert any("the reference's board was too small to fill the play" in n for n in notes)
    assert guided.play_too_short([{"check": "Reference: the part lengths", "detail": "play 100% of the reference, 50% of the ad"}])
    assert guided.play_too_short([{"check": "Reference: the part lengths", "detail": "play 22.1 s expected, 12.0 s in the ad"}])
    # an all-play reference's ad near the engine's cap is not short (round 2, case 05: 72% of the ad, the board grew)
    assert not guided.play_too_short([{"check": "Reference: the part lengths", "detail": "play 100% of the reference, 72% of the ad"}])
    assert not guided.play_too_short([{"check": "Reference: the part lengths", "detail": "play 22.1 s expected, 19.0 s in the ad"}])
    assert not guided.play_too_short([{"check": "Reference: the part lengths", "detail": "play 40% of the reference, 60% of the ad"}])
    # without a short play, the reference's 4 blocks stay
    after = copy.deepcopy(before)
    after["level"]["blocks"] = 9
    guided.pin_reference(before, after, [{"check": "Reference: the hook", "status": "failed"}])
    assert after["level"]["blocks"] == 4


# ---------- round 2 (2026-10-17): captions that fit the ending, which game ----------

def test_captions_that_claim_what_the_ending_does_not_show_are_replaced():
    """studio/1017-092301 (LolTap, a cliffhanger) showed "Board cleared!"; trailer 2's unfinished board had "Can you beat
    the clock?" on its end card."""
    b = _fresh()
    b["gameplay"]["ending"] = "cliffhanger"
    b["concept"].update(hook="Slide them all home!", result="Board cleared!", end_fact="Slide. Match. Relax.")
    notes = V.fit_captions(b)
    assert b["concept"]["result"] is None and b["concept"]["end_fact"] == "Slide. Match. Relax." and b["concept"]["hook"] == "Slide them all home!"
    assert notes == ["the result line \"Board cleared!\" is left out: a cliffhanger's result moment is its question"]
    assert notes[0] in b["assumptions"]
    b = _fresh()
    b["gameplay"]["ending"] = "cliffhanger"
    b["concept"].update(end_fact="Can you beat the clock?", hook="Solved in seconds!")
    V.fit_captions(b)
    assert b["concept"]["end_fact"] == "Can you finish it?" and b["concept"]["hook"] == "Can you finish it?"
    assert any("\"Can you beat the clock?\" (end fact) claims a clear or a beaten clock the cliffhanger does not show" in x
               for x in b["assumptions"])
    b = _fresh()
    b["gameplay"]["ending"] = "time_out"
    b["concept"].update(result="Level complete!", hook="Can you beat the clock?", end_fact="You did it!")
    V.fit_captions(b)
    assert (b["concept"]["result"], b["concept"]["hook"], b["concept"]["end_fact"]) == (
        "So close!", "Can you beat the clock?", "Can you finish it in time?")  # the challenge fits a time-out
    b = _fresh()
    b["gameplay"]["ending"] = "near_fail"
    b["concept"].update(result="Just in time!")
    assert V.fit_captions(b) == [] and b["concept"]["result"] == "Just in time!"


def test_the_captions_fit_row(tmp_path):
    b = _guided_brief()
    cliff = _manifest(gameplay={"ending": "cliffhanger"}, layers=[
        {"id": "hook", "kind": "caption", "text": "Slide them all home!", "from_s": 0.0, "to_s": 3.0},
        {"id": "cap_result", "kind": "caption", "text": "Board cleared!", "from_s": 31.0, "to_s": 33.0},
        {"id": "end_fact", "kind": "caption", "text": "Can you beat the clock?", "from_s": 34.0, "to_s": 38.0}])
    row = {r["check"]: r for r in audit.reference_rows(PROMPT, b, {"checks": []}, _write_v(tmp_path / "a", cliff), None)}[
        "Asked: the captions fit the ending"]
    assert row["status"] == "failed" and row["where"] == "plan" and row["from"] == "reference"
    assert "cap_result \"Board cleared!\" claims a clear or a beaten clock" in row["detail"] and "end_fact" in row["detail"]
    good = {r["check"]: r for r in audit.reference_rows(PROMPT, b, {"checks": []}, _write_v(tmp_path / "b", _manifest()), None)}
    assert good["Asked: the captions fit the ending"]["status"] == "pass"  # a near-fail's "Just in time!" fits
    assert audit.misses([row]) == [row]  # fed back to the loop


def _write_v(vdir, manifest):
    (vdir / "ad").mkdir(parents=True, exist_ok=True)
    (vdir / "parts.json").write_text(json.dumps(manifest))
    (vdir / "ad" / "ad.json").write_text(json.dumps({"layers": {}}))
    return vdir


@pytest.mark.parametrize("game, cbj", [
    ("Another puzzle game", True), ("Brick puzzle game", True), ("A toy brick sliding puzzle game", True),
    ("", True), ("Color Block Jam", True), ("Wood Color Jam", False), ("Toy Blast", False), ("'Block Out'", False),
])
def test_only_a_named_other_game_blocks_the_hud(game, cbj):
    """Round 2: trailer 2 read as "Another puzzle game" lost its Level 25. A description is not a name: with the game's
    LEVEL n and TIME mm:ss on the HUD the reference counts as Color Block Jam; a named other game never does."""
    notes = {**NOTES, "game_or_product": game, "hud": {"level": "LEVEL 25", "clock": "01:05"}, "screen_text": ["LEVEL 25", "TIME 01:05"],
             "board": {"columns": 5, "rows": 7, "shape": "holes", "blocks": 9, "colours": ["purple"]}}
    assert V.hud_of(notes)["cbj"] is cbj
    b = _fresh()
    V.apply(b, SIMILAR, [_analysis(["concept"], notes)])
    assert (b["level"]["label"] == 25) is cbj



def _hud_analysis(**over):
    notes = {**NOTES, "game_or_product": "Color Block Jam", "hud": {"level": "LEVEL 25", "clock": "01:05"},
             "board": _trailer2_board(), "structure": [{"from_s": 0, "to_s": 28.9, "purpose": "gameplay"}], **over}
    a = _analysis(["concept"], notes)
    a["facts"] = {"duration_s": 28.9}
    return a


def test_the_huds_starting_clock_for_a_cliffhanger_and_a_near_fail():
    """Round 2, case 05 ("Use the same level number and starting time as this video ... stop before the level is
    solved"): Level 25 was taken, the clock 01:05 was not. A cliffhanger stops mid-level, so its starting clock is the
    reference's; a near-fail takes it only when the play can bring it down to 5 s; a request that asks for it has it
    set whatever the ending, and the plan row says when the ending makes it impossible. Since 2026-10-19 brief.check keeps
    the clock for a win and a cliffhanger, and drops it for a near-fail and a time-out."""
    b = _fresh()
    V.apply(b, SIMILAR, [_hud_analysis(ending="stopped")])
    assert b["gameplay"]["ending"] == "cliffhanger" and b["gameplay"]["timer_s"] == 65 and b["level"]["label"] == 25
    assert "the clock starts at 01:05, as in the reference" in B.control(b, "difficulty_pacing")["plan"]
    checked = B.check(b)
    # 2026-10-19: brief.check keeps a cliffhanger's starting clock (play.fit_clock cuts wherever it stands); a near-fail's
    # and a time-out's are still the ending's
    assert checked["gameplay"]["timer_s"] == 65
    assert not any("65 s on the clock is not used" in (r.get("why") or "") for r in checked["controls"])
    # a near-fail: about 22 s of play cannot bring 01:05 down to 5 s
    b = _fresh()
    V.apply(b, SIMILAR, [_hud_analysis(ending="near-fail")])
    assert b["gameplay"]["ending"] == "near_fail" and b["gameplay"]["timer_s"] is None
    assert any("brings 01:05 down only to about 43 s" in x for x in b["assumptions"])
    # a near-fail from a clock the play can bring down: taken
    b = _fresh()
    V.apply(b, SIMILAR, [_hud_analysis(ending="near-fail", hud={"level": "LEVEL 25", "clock": "00:25"})])
    assert b["gameplay"]["timer_s"] == 25
    # asked for: set, and the row says the ending makes it impossible
    b = _fresh()
    V.apply(b, "Use the same level number and starting time as this video, a near-fail.", [_hud_analysis(ending="near-fail")])
    assert b["gameplay"]["timer_s"] == 65 and "(asked; but a near-fail ends with 5 s or less" in B.control(b, "difficulty_pacing")["plan"]
    assert B.control(b, "difficulty_pacing")["status"] == "adjusted"



def test_the_pacing_row_is_judged_when_the_plan_reads_for_the_pacing(tmp_path):
    """Round 2, case 07: "Take only how fast the moves come in this video. Everything else is mine: an easy board, a
    clean win, 30 seconds." The plan's focus was the pacing alone, but the row said "not judged" because the word table
    has no "how fast". A targeted plan that names the pacing makes it judged; a full concept read keeps the words."""
    prompt = "Take only how fast the moves come in this video. Everything else is mine: an easy board, a clean win, 30 seconds."
    assert "pacing" not in R.focus_words(prompt)["found"]  # the word table alone would miss it
    b = _guided_brief(focus=("pacing",))
    b["planner"]["references"][0]["plan"] = {"source": "planner", "level": "targeted", "focus": ["pacing"], "constraints": []}
    row = _rows(tmp_path / "a", b, prompt=prompt, result=SPEEDS_UP)["the pacing"]
    assert row["status"] == "pass" and "the request does not ask about the pacing" not in row["detail"]
    assert "average pause" in row["detail"]  # the pace change judged, by the Pacing curve check's measure
    assert audit.pacing_asked(prompt, b["planner"]["references"][0])
    # a full concept plan that lists the pacing: the request's words decide (the planner lists it in most concept plans)
    full = {"plan": {"source": "planner", "level": "full", "focus": ["concept", "pacing"]}}
    assert not audit.pacing_asked(SIMILAR, full) and audit.pacing_asked(PACED, full)
    assert not audit.pacing_asked(prompt, {"plan": {"source": "words", "level": "targeted", "focus": ["pacing"]}})


# ---------- round 2 (2026-10-17): the screen (case 09), the blocks' colours (case 10) ----------

CASE09 = "Keep this video's camera framing, what it shows on screen and its colours. 45 seconds, a near-fail with 2 seconds left."
CASE10 = ("Take only the block colours of this video. Everything else is mine: a narrow centre level, medium difficulty, "
          "40 seconds, a clean win.")
CASE04_PROMPT = "Make a Color Block Jam ad on the same board as this video, with the same size, layout and colours, but let the player clear it with 3 seconds left."
CASE12 = "Keep the mood of this ad in the background colours."


def _close_up(**over):
    notes = {**NOTES, "game_or_product": "Color Block Jam", "hud": {"level": None, "clock": None, "clock_last": None},
             "framing": {"board_share": 0.84, "hand_cursor": False, "other_items": []},
             "board": {**LOLTAP_BOARD, "obstacles": []}, **over}
    a = _analysis(["look", "screen"], notes)
    a["board_read"] = {"box": {"x": 0.08, "y": 0.25, "w": 0.84, "h": 0.53}}
    return a


def test_the_screen_focus_takes_the_framing_the_hud_and_the_cursor():
    """Round 2, case 09: trailer 3 is a close-up of the board with no HUD; the ad kept the HUD and no zoom. The screen
    (asked, or covered by the look) gives the zoom from the board's share, the HUD as the reference shows it, the cursor
    as seen; with the clock hidden a near-fail's seconds go into a caption."""
    assert R.focus_words(CASE09)["found"] == ["look", "screen"] and R.covers(["look"], "screen") and not R.covers(["concept"], "screen")
    b = _fresh()
    b["gameplay"].update(ending="near_fail", clock_left_s=2)
    prov = V.apply(b, CASE09, [_close_up()])[0]
    vs = b["visuals"]
    assert (vs["camera_zoom"], vs["hud_level"], vs["hud_timer"], vs["cursor"]) == (B.ZOOM_RANGE[1], False, False, "none")
    assert {"visuals.zoom", "visuals.hud", "visuals.cursor"} <= set(b["changed"]) and prov["screen"]["share"] == 0.84
    assert (b["concept"]["hurry"], b["concept"]["result"]) == ("Hurry!", "Phew! 2 s left!")  # one line (rerun, case 09)
    assert any("the clock is hidden as in the reference, so the result caption carries the near-fail" in x for x in b["assumptions"])
    checked = B.check(b)["visuals"]
    assert checked["camera_zoom"] == B.ZOOM_RANGE[1] and checked["hud_timer"] is False  # within brief.validate
    # a reference that shows the HUD keeps it, and a hand cursor is the game's hand
    b = _fresh()
    wide = _close_up(hud={"level": "LEVEL 25", "clock": "01:05"}, framing={"board_share": 0.3, "hand_cursor": True})
    wide.pop("board_read")  # no measured box: the reading's own share
    V.apply(b, CASE09, [wide])
    assert (b["visuals"]["hud_level"], b["visuals"]["hud_timer"], b["visuals"]["cursor"], b["visuals"]["camera_zoom"]) == (True, True, "hand", None)
    # the request's own HUD wins
    b = _fresh()
    V.apply(b, "Keep this video's camera framing, but show the clock.", [_close_up()])
    assert b["visuals"]["hud_timer"] is True and b["visuals"]["camera_zoom"] == B.ZOOM_RANGE[1]
    assert V.zoom_for(0.5) is None and V.zoom_for(0.65) == round(1.0 + 0.5 * (B.ZOOM_RANGE[1] - 1.0), 2)


def test_the_screen_row(tmp_path):
    a = _close_up()
    b = _guided_brief(focus=("look", "screen"), notes=a["notes"])
    b["planner"]["references"][0]["board_read"] = a["board_read"]
    b["visuals"].update(hud_level=False, hud_timer=False, camera_zoom=1.12)
    row = _rows(tmp_path / "a", b)["the screen"]
    assert row["status"] == "pass" and "the reference shows no HUD, the ad no HUD" in row["detail"] and "(info)" in row["detail"]
    b["visuals"].update(hud_level=True, hud_timer=True)
    row = _rows(tmp_path / "b", b)["the screen"]
    assert row["status"] == "failed" and row["where"] == "plan"
    b["visuals"].update(hud_level=False, hud_timer=False, camera_zoom=None)
    assert _rows(tmp_path / "c", b)["the screen"]["status"] == "pass"  # the zoom is info only


def test_the_blocks_colours_are_the_boards_not_the_looks(tmp_path, monkeypatch):
    """Round 2, case 10: "take only the block colours" was planned as the look: the reference's palette went into the
    background and the level's colours stayed empty. The blocks' colours are their own focus: level.colours only."""
    assert R.focus_words(CASE10)["found"] == ["board_colours"]
    assert R.focus_words(CASE04_PROMPT)["found"] == ["board", "board_colours"] and R.covers(["board"], "board_colours")
    assert R.focus_words(CASE12)["found"] == ["look"] and not R.covers(["look"], "board_colours")
    assert "board_colours: the blocks' colours only" in R.PLAN_SYSTEM and "never the blocks" in R.PLAN_SYSTEM
    b = _fresh()
    b["level"].update(shape="narrow_center", difficulty="medium")
    a = _analysis(["board_colours"], {**NOTES, "board": {**LOLTAP_BOARD}})
    prov = V.apply(b, CASE10, [a])[0]
    lv = b["level"]
    assert lv["colours"] == ["Green", "Blue", "Red", "Yellow", "Purple", "Orange"]
    assert (lv["shape"], lv["difficulty"], lv["width"], lv["blocks"]) == ("narrow_center", "medium", None, None)  # the request's
    assert b["visuals"] == _fresh()["visuals"] and prov["board"]["colours_only"]  # no background from the video
    assert "the blocks' colours of the reference" in B.control(b, "level")["plan"]
    monkeypatch.setattr(audit, "BOARD_RELIABLE", frozenset({"shape", "size", "blocks", "colours"}))
    b["planner"] = {"references": [a]}
    row = _board_rows(tmp_path, b, _level_json(6, 8, (0, 2, 3, 1, 5, 4)), prompt=CASE10)["Reference: the board"]
    assert row["status"] == "pass" and "6 of 6 in the level" in row["detail"]
    assert "the shape, the size and the blocks are not a focus" in row["detail"] and "6x6 read" not in row["detail"]



# ---------- round 2, case 14 (2026-10-17): what the request leaves open is filled from the general reading ----------

CASE14 = "Use this ad's hook and its cursor, and show the player stuck once before solving it."
CASE07 = "Take only how fast the moves come in this video. Everything else is mine: an easy board, a clean win, 30 seconds."
CASE05 = "Use the same level number and starting time as this video, keep the same flow, and stop before the level is solved."


def _lol_reading(focus):
    a = _lol_analysis()
    a["focus"], a["level"] = list(focus), "targeted"
    a["notes"]["framing"] = {"board_share": 0.4, "hand_cursor": True, "other_items": []}
    return a


def test_what_the_request_leaves_open_is_filled_from_the_reading():
    """Round 2, case 14: the plan's focus was the hook, so only the hook was applied and the level stayed open (any shape,
    no blocks) though the request says nothing about it. What the request names is taken first; what it leaves open is
    filled from the general reading (the board, the ending, the flow, the screen it names), marked in the provenance;
    "only", "just the", "nothing else", "everything else is mine" fill nothing; the request's own values win."""
    b = _fresh()
    b["gameplay"]["ending"] = "win"  # the planner's reading of "before solving it"
    prov = V.apply(b, CASE14, [_lol_reading(["hook"])])[0]
    assert "board" in prov["filled"] and "structure" in prov["filled"] and "ending" not in prov["filled"]
    assert prov["named"] == ["screen"] and "screen" not in prov["filled"]  # "its cursor" is asked, not left open
    lv = b["level"]
    assert (lv["source"], lv["shape"], lv["width"], lv["height"]) == ("generate", "open", 6, 6) and lv["colours"]
    assert b["gameplay"]["ending"] == "win"  # "before solving it" is the request's own ending: the video's cut does not win
    assert b["visuals"]["cursor"] == "hand"  # "its cursor": the reference's hand
    assert (b["visuals"].get("hud_level"), b["visuals"].get("camera_zoom")) == (_fresh()["visuals"].get("hud_level"),
                                                                                _fresh()["visuals"].get("camera_zoom"))  # the cursor alone
    filled = [x for x in prov["adapted"] if V.FILLED in x]
    assert any(x.startswith("the board (") for x in filled)
    assert not any(V.FILLED in x for x in prov["adapted"] if x.startswith("the challenge hook"))  # asked, not filled
    assert b["visuals"]["background"] == _fresh()["visuals"]["background"]  # the look is never filled
    # the same request without the solve leaves the ending open: the video's (a cut before the solve) fills it
    b = _fresh()
    prov = V.apply(b, "Use this ad's hook and its cursor, and show the player stuck once.", [_lol_reading(["hook"])])[0]
    assert prov["filled"][:2] == ["board", "ending"] and b["gameplay"]["ending"] == "cliffhanger"
    assert any("ending" in x and V.FILLED in x for x in prov["adapted"])
    for prompt, focus in ((CASE07, ["pacing"]), (CASE10, ["board_colours"])):
        b = _fresh()
        prov = V.apply(b, prompt, [_lol_reading(focus)])[0]
        assert "filled" not in prov, prompt
        assert b["gameplay"]["ending"] == _fresh()["gameplay"]["ending"] and b["level"]["shape"] == "any"
    # case 05: the request names the level number, the starting time and the flow (a cliffhanger): the board is filled
    b = _fresh()
    a = _hud_analysis(ending="stopped")
    a["focus"], a["level"] = ["structure"], "targeted"
    prov = V.apply(b, CASE05, [a])[0]
    assert "board" in prov["filled"] and "ending" not in prov["filled"]  # "stop before the level is solved" is its own
    assert b["level"]["source"] == "generate" and b["level"]["shape"] != "any" and b["level"]["width"]


def test_filled_aspects_are_judged_as_info(tmp_path):
    """The rows of what the request left open say so and are info, not failures (they were not asked); a screen the
    request's words name ("its cursor") is judged as asked."""
    prompt = "Use this ad's hook and its cursor, and show the player stuck once."
    a = _lol_reading(["hook"])
    b = _fresh()
    V.apply(b, prompt, [a])
    b["gameplay"]["ending"] = "win"  # a plan that differs from the reference: still info, the ending was not asked
    b["planner"] = {"references": [a]}
    rows = _rows(tmp_path, b, prompt=prompt)
    for k in ("the ending", "the purposes in order", "the part lengths", "the board"):
        assert rows[k]["status"] == "info" and rows[k]["detail"].startswith(V.FILLED), (k, rows[k])
    assert "it differs" in rows["the ending"]["detail"]
    assert not rows["the screen"]["detail"].startswith(V.FILLED)
    assert "filled from the reference (the request left it open): board, ending, structure" in rows["read with confidence"]["detail"]
    # case 07: "Take only how fast the moves come ... Everything else is mine": nothing filled, the ending row is not a focus
    b = _fresh()
    a = _lol_reading(["pacing"])
    V.apply(b, CASE07, [a])
    b["planner"] = {"references": [a]}
    rows = _rows(tmp_path, b, prompt=CASE07)
    assert rows["the ending"]["detail"] == "not a focus of this reading" and rows["the board"]["detail"] == "not a focus of this reading"



def test_the_requests_ending_words_are_its_own():
    """"before solving it" (case 14) and "stop before the level is solved" (case 05) state the ending: the reference's
    never replaces it; a request silent on the ending leaves it open."""
    assert "ending" in V.stated(CASE14) and "ending" in V.stated(CASE05)
    for p in ("Use this ad's hook.", "Use this ad's hook and its cursor, and show the player stuck once.",
              "Make it like this video, with a clear hook.", "Keep the board of this clip."):
        assert "ending" not in V.stated(p), p
    for p in ("Let the player lose the level at the end.", "End on a cliffhanger.", "Finish with the win screen.",
              "Keep the puzzle unsolved."):
        assert "ending" in V.stated(p), p


def test_a_cursor_named_alone_takes_only_the_cursor():
    """Round 2, case 14: "its cursor" names the cursor and nothing else of the screen: the hand is taken (from the framing
    answer, or a hand the reading lists as seen when it has none), the HUD and the zoom stay; the screen row is info."""
    a = _lol_reading(["hook"])
    del a["notes"]["framing"]
    a["notes"]["extras_seen"] = ["hand cursor"]
    a["notes"]["hud"] = {"level": None, "clock": None}
    b = _fresh()
    V.apply(b, "Use this ad's hook and its cursor.", [a])
    assert b["visuals"]["cursor"] == "hand" and b["visuals"].get("hud_level") == _fresh()["visuals"].get("hud_level")
    assert V.cursor_only("Use this ad's hook and its cursor.") and not V.cursor_only("Keep its cursor and its HUD.")


# ---------- round 2 rerun (2026-10-17): six fixes ----------

def _pacing_reading(dps=0.31, change="even", plan_level="targeted", focus=("pacing",)):
    a = _analysis(list(focus))
    a["notes"]["pacing"], a["notes"]["pace_change"] = "normal", change
    a["pacing"] = {"moves_by_third": [3.0, 3.0, 3.0], "gameplay_s": 28.9, "dps": dps, "tempo": "normal",
                   "tempo_source": "counts", "change": change, "source": "motion"}
    a["plan"] = {"constraints": [], "source": "planner", "level": plan_level, "focus": list(focus)}
    return a


def test_a_concept_read_does_not_apply_the_pacing():
    """Round 2, case 03: "create a similar game in Color Block Jam", a full read, took the reference's "slows down"; the
    ad's own Pacing curve check then failed. Not asked, the pacing is read and noted, never applied; the pure-play
    rule's calm tempo (a structural device) stays."""
    a = _pure_play_analysis()
    a["notes"]["pacing"], a["notes"]["pace_change"] = "calm", "slows down"
    a["plan"] = {"constraints": [], "source": "planner", "level": "full", "focus": ["concept", "pacing", "structure"]}
    b = _fresh()
    prov = V.apply(b, SIMILAR, [a])[0]
    assert (b["pacing"]["tempo"], b["pacing"]["curve"]) == ("calm", "even") and "pace" not in prov
    assert any("is read but not applied: the request does not ask about the pacing" in x for x in b["assumptions"])
    assert not any(x.startswith("the pacing (") for x in prov["adapted"])
    # asked by the words, it is applied
    b = _fresh()
    V.apply(b, SIMILAR + ", with the same pacing.", [a])
    assert b["pacing"]["curve"] == "slows_down"


def test_the_pacing_levers_match_the_references_drag_rate():
    """Round 2, case 07: the reference plays 0.31 drags a second; the ad played 0.79 (10 drags of an easy board at a
    normal tempo) and 0.77 at a calm one: a calm tempo slows the play only through studio's pacing grades, which a
    10-drag solve in 30 s does not get. The play levers keep the reference's class and fill the play seconds; the
    request's own values stay."""
    b = _fresh()
    b["gameplay"].update(ending="win", mistakes=0)
    b["level"]["difficulty"] = "easy"
    prov = V.apply(b, CASE07, [_pacing_reading()])[0]
    assert (b["pacing"]["tempo"], b["level"]["moves"], b["gameplay"]["hesitations"]) == ("calm", 6, 0)
    rec = prov["play"]
    assert (rec["mode"], rec["tempo"], rec["moves"], rec["grade"], rec["reference_rate"]) == ("pace", "calm", 6, "deliberate", 0.31)
    assert V.tempo_class(rec["rate"]) == "normal" and rec["expected_s"] >= rec["target_s"] - 1.5
    assert any(x.startswith("the play fills about 20 of 20.5 s") and "normal pace (0.31 drags a second)" in x for x in prov["adapted"])
    # a fast reference: the fast class (a clean win; a near-fail's mistake and hesitations cannot go that fast)
    b = _fresh()
    b["gameplay"].update(ending="win", mistakes=0)
    prov = V.apply(b, "Take only the pacing of this video.", [_pacing_reading(dps=0.8)])[0]
    assert V.tempo_class(prov["play"]["rate"]) == "fast"
    # the request's own tempo wins; its own block count bounds the moves
    b = _fresh()
    b["pacing"]["tempo"] = "fast"  # as the planner read "at a fast tempo"
    V.apply(b, "Use the pacing of this video, at a fast tempo.", [_pacing_reading()])
    assert b["pacing"]["tempo"] == "fast"
    b = _fresh()
    b["level"]["blocks"] = 9
    prov = V.apply(b, "Use the pacing of this video with 9 blocks.", [_pacing_reading()])[0]
    assert b["level"]["moves"] is None and b["level"]["blocks"] == 9  # the tempo alone
    # a board the reference fills bounds the moves from below
    b = _fresh()
    b["level"]["blocks"] = 8
    V.apply(b, "Use the pacing of this video.", [_pacing_reading()])
    assert b["level"]["moves"] >= 8


def test_the_play_seconds_come_first_and_the_rate_is_pinned():
    """Round 2 rerun, case 05: the stretch rule ("a calm tempo") and the pacing levers ("a normal tempo, 9 moves") both
    wrote the tempo; the levers won and the play was 19.9 s of a 30 s ad, the end card 8.1 s. One decision now: the play
    seconds first (the ad minus the end card, the result or the question, within what studio records), the rate kept in
    the reference's class, the moves derived, and the board's blocks raised to supply them (a cell a side at most)."""
    nb = _fresh()
    nb["gameplay"]["ending"], nb["sequence"]["replay"] = "cliffhanger", False
    target, room, cap = V.play_target(nb, [])
    assert (room, cap) == (25.0, 21.0) and target == 21.0  # studio keeps room for a replay: 30 - 3 - 3 - 2 - 1
    a = _pure_play_analysis()
    a["pacing"] = {"dps": 0.38, "tempo": "normal", "tempo_source": "counts", "change": "even", "source": "motion"}
    a["notes"]["pacing"] = "normal"
    a["focus"], a["level"] = ["screen", "pacing", "structure"], "targeted"
    a["plan"] = {"constraints": [], "source": "planner", "level": "targeted", "focus": ["screen", "pacing", "structure"]}
    b = _fresh()
    b["gameplay"]["ending"] = "cliffhanger"
    prov = V.apply(b, CASE05, [a])[0]
    tempo_lines = [x for x in prov["adapted"] if "tempo" in x]
    assert len(tempo_lines) == 1 and tempo_lines[0].startswith("the play fills about")  # one decision, reported once
    rec = prov["play"]
    # the board read holds 9 blocks, so at least 9 moves: a calm tempo with a thought before every other drag fills the
    # most at the reference's normal pace (a long look before each drag needs 8 moves or fewer), and a hesitation (its
    # own pace, no cost to studio's grade) fills the rest up to studio's cap (rerun 4, case 05)
    assert rec["mode"] == "pace" and V.tempo_class(rec["rate"]) == "normal" and rec["moves"] >= b["level"]["blocks"] == 9
    assert (rec["tempo"], rec["grade"], rec["hesitations"], rec["expected_s"]) == ("calm", "thinking", 1, 21.0)
    assert b["level"]["moves"] == rec["moves"] and {"pacing.tempo", "level.moves"} <= set(b["reference"]["set"])
    # without the pacing taken, the fill alone: a calm tempo, the moves that fill, and the tempo pinned even when the
    # planner had already set it (round 2 rerun, case 03: the stretch tempo was not recorded, and a revision undid it)
    b = _fresh()
    b["pacing"]["tempo"] = "calm"
    prov = V.apply(b, SIMILAR, [_pure_play_analysis()])[0]
    assert prov["play"]["mode"] == "fill" and b["pacing"]["tempo"] == "calm" and "pacing.tempo" in b["reference"]["set"]
    # more moves than the board's blocks supply raise the blocks, the board a cell a side from the read at most
    b = _fresh()
    prov = V.apply(b, SIMILAR, [_board_analysis(board={**LOLTAP_BOARD, "columns": 6, "rows": 6, "blocks": 4})])[0]
    lv = b["level"]
    assert lv["blocks"] >= 4 and lv["moves"] - DIFF.get(lv["difficulty"], 1) <= lv["blocks"] and lv["width"] <= 7 and lv["height"] <= 7


DIFF = V.DIFFICULTY_REPOSITION


@pytest.mark.parametrize("tempo", ["calm", "normal", "fast"])
@pytest.mark.parametrize("ending,mistakes", [("win", 0), ("near_fail", None), ("cliffhanger", 0), ("win", 1)])
def test_solve_pace_agrees_with_studio(monkeypatch, tempo, ending, mistakes):
    """videoref.solve_pace is studio._short_solve's arithmetic on a drag count (studio.py is not changed): the two agree."""
    import types
    from cbj import level as L, solver, studio
    for drags in range(3, 15):
        monkeypatch.setattr(L, "load_level", lambda p: None)
        monkeypatch.setattr(solver, "solve_fast", lambda lv, n=drags: types.SimpleNamespace(min_drags=n))
        for length in (30.0, 45.0, 60.0):
            b = _fresh()
            b["gameplay"].update(ending=ending, mistakes=mistakes)
            b["pacing"].update(tempo=tempo, length_s=length)
            assert V.solve_pace(tempo, drags, length, ending, mistakes) == studio._short_solve(b, Path("x.json")), (drags, length)


def test_a_pacing_miss_or_a_short_play_reruns_the_levers_with_the_measured_rate(tmp_path, monkeypatch):
    """A revision uses the same levers: the take measured faster than expected, or its play fell short of the planned
    seconds, so the correction re-derives the moves (the rate stays pinned); nothing else calls for it."""
    from cbj import studio
    from cbj.workflows import guided
    monkeypatch.setattr(studio, "STUDIO", tmp_path)
    a = _pacing_reading()
    b = _fresh()
    b["gameplay"].update(ending="win", mistakes=0, hesitations=0)
    b["level"]["difficulty"] = "easy"
    V.apply(b, CASE07, [a])
    b["planner"] = {"references": [a]}
    vdir = tmp_path / "job" / "v1"
    vdir.mkdir(parents=True)

    def take(play_s, drags):
        times = [1.0 + (play_s - 1.5) * i / max(1, drags - 1) for i in range(drags)]
        (vdir / "parts.json").write_text(json.dumps({"parts": [{"id": "play", "from_s": 0.0, "to_s": play_s}],
                                                     "moments": [{"id": f"drag_{i}", "at_s": x} for i, x in enumerate(times)],
                                                     "gameplay": {"drags": drags}}))
    v = {"id": "job", "n": 1, "brief": b}
    miss = [{"check": "Reference: the pacing", "status": "failed", "where": "plan"}]
    first = copy.deepcopy(b)
    first["pacing"]["tempo"], first["level"]["moves"] = "normal", 10  # what the first take played (rerun 1)
    v = {"id": "job", "n": 1, "brief": first}
    take(13.0, 10)  # 0.77 drags a second
    after = copy.deepcopy(first)
    line = guided.play_again(v, after, CASE07, miss)
    assert line and "corrected by the last take's measure" in line and after["reference"]["play"]["measured_dps"] == 0.77
    assert after["reference"]["play"]["reference_rate"] == 0.31 and after["pacing"]["tempo"] == "calm" and after["level"]["moves"] < 10
    assert first["reference"]["play"].get("measured_dps") is None  # the base version's provenance is untouched
    v = {"id": "job", "n": 1, "brief": b}
    take(b["reference"]["play"]["target_s"], 6)  # the play filled and no pacing miss: nothing to do
    assert guided.play_again(v, copy.deepcopy(b), CASE07, []) is None
    take(15.0, 6)  # a short play re-runs the levers even without a pacing miss
    after = copy.deepcopy(b)
    assert "the last take played 15.0 s" in guided.play_again(v, after, CASE07, [])
    v2 = {**v, "brief": {**b, "reference": {**b["reference"], "play": None}}}
    assert guided.play_again(v2, copy.deepcopy(b), CASE07, miss) is None  # no play decision in the plan


def test_a_revision_keeps_the_pure_play_fields_and_the_screen():
    """Round 2, case 05: v1 passed with 78% play; the revision turned the pure-play rule's calm tempo to normal and the
    play fell to 51%, then 61%. Case 09: the revision turned the hidden clock back on to answer "the 2 seconds cannot
    be seen". Both are kept, as the board is."""
    from cbj.workflows import guided
    before = _fresh()
    before["gameplay"]["ending"] = "cliffhanger"
    V.apply(before, SIMILAR, [_pure_play_analysis()])
    assert {"pacing.tempo", "sequence.timing"} <= set(before["reference"]["set"])
    after = copy.deepcopy(before)
    after["pacing"]["tempo"], after["sequence"]["intro_s"], after["sequence"]["hold_s"] = "fast", 1.0, 2.0
    notes = guided.pin_reference(before, after, [{"check": "Reference: the part lengths", "status": "failed"}])
    assert (after["pacing"]["tempo"], after["sequence"]["intro_s"], after["sequence"]["hold_s"]) == (before["pacing"]["tempo"], 0.0, 0.0)
    assert any(n.startswith("the reference's pacing is kept") for n in notes)
    # the screen and the hidden clock's captions
    before = _fresh()
    before["gameplay"].update(ending="near_fail", clock_left_s=2)
    V.apply(before, CASE09, [_close_up()])
    after = copy.deepcopy(before)
    after["visuals"]["hud_timer"], after["concept"]["result"], after["concept"]["hurry"] = True, "", ""
    notes = guided.pin_reference(before, after, [{"check": "Reference: the screen", "status": "failed"}])
    assert after["visuals"]["hud_timer"] is False and after["concept"]["result"] == "Phew! 2 s left!"
    assert after["concept"]["hurry"] == "Hurry!" and any(n.startswith("the reference's screen is kept") for n in notes)


def test_the_hidden_clocks_seconds_fit_the_hurry_window():
    """Round 2, case 09: ad.py shows the hurry caption from the clock's 5 s to the last drag (0.93 s in v1), and left out
    "2 seconds left!" (1.3 s to read); "Hurry!" fits, and the seconds go on the result caption (2.5 s)."""
    from cbj.ad import reading_s
    assert reading_s(V.HURRY_WORD) <= 0.93 < reading_s("2 seconds left!")
    b = _fresh()
    b["gameplay"].update(ending="time_out")
    b["visuals"]["hud_timer"] = False
    V.hidden_clock_captions(b, "a time-out")
    assert (b["concept"]["hurry"], b["concept"]["result"]) == ("Hurry!", "Out of time!")
    b = _fresh()  # a caption the request quotes is its own
    b["gameplay"].update(ending="near_fail", clock_left_s=2)
    b["concept"]["hurry"] = "Two seconds to go"
    V.hidden_clock_captions(b, 'a near-fail, with "Two seconds to go" as the hurry caption')
    assert b["concept"]["hurry"] == "Two seconds to go" and b["concept"]["result"] == "Phew! 2 s left!"


def test_a_mistake_caption_needs_a_wrong_move():
    """Round 2, case 09: the captions-fit row looks at the play too; the plan clears a mistake caption with no mistake
    planned (a cliffhanger's blocked attempt is one)."""
    b = _fresh()
    b["gameplay"].update(ending="win", mistakes=0)
    layers = [{"id": "cap_mistake", "text": "I can't reach yellow!", "from_s": 2.0, "to_s": 4.0}]
    row = audit.captions_fit_row({"gameplay": {"ending": "win"}, "layers": layers, "moments": [{"id": "drag_0", "kind": "move"}]}, b)
    assert row["status"] == "failed" and "claims a wrong move the play does not have" in row["detail"] and row["where"] == "plan"
    row = audit.captions_fit_row({"gameplay": {"ending": "win"}, "layers": layers,
                                  "moments": [{"id": "drag_1", "kind": "mistake", "also": "wrong_move"}]}, b)
    assert row["status"] == "pass"
    b["concept"]["mistake"] = "I can't reach yellow!"
    assert V.fit_captions(b) and b["concept"]["mistake"] is None and "concept.mistake" in b["changed"]
    b = _fresh()
    b["gameplay"].update(ending="cliffhanger", mistakes=0)
    b["concept"]["mistake"] = "Blocked!"
    V.fit_captions(b)
    assert b["concept"]["mistake"] == "Blocked!"


def test_a_revision_restores_what_the_request_states():
    """Round 2, case 14: "show the player stuck once" was planned with one mistake; the revision followed the viewer's
    "the stuck moment is short" to two. Every stated value comes back from the base version, unless its own asked row
    failed at the plan."""
    from cbj.workflows import guided
    before = _fresh()
    before["gameplay"].update(ending="win", mistakes=1, mistake_kinds=["blocked"])
    before["pacing"]["length_s"] = 30.0
    after = copy.deepcopy(before)
    after["gameplay"].update(mistakes=2, hesitations=1)
    after["changed"] = ["gameplay.mistakes", "gameplay.hesitations"]
    notes = guided.keep_stated(CASE14, before, after, [])
    assert after["gameplay"]["mistakes"] == 1 and after["gameplay"]["hesitations"] == 1  # hesitations are not stated
    assert after["changed"] == ["gameplay.hesitations"] and any("the mistakes itself" in n for n in notes)
    after["gameplay"]["mistakes"] = 2
    guided.keep_stated(CASE14, before, after, [{"check": "Asked: mistakes", "status": "failed", "where": "plan"}])
    assert after["gameplay"]["mistakes"] == 2  # the base planned it wrong: the revision may fix it
    # the ending, the length and the board's stated values too
    prompt = "A 45 second ad on a narrow centre board with 6 blocks; end on a cliffhanger."
    before = _fresh()
    before["gameplay"]["ending"], before["pacing"]["length_s"] = "cliffhanger", 45.0
    before["level"].update(shape="narrow_center", blocks=6)
    after = copy.deepcopy(before)
    after["gameplay"]["ending"], after["pacing"]["length_s"] = "win", 30.0
    after["level"].update(shape="open", blocks=8)
    guided.keep_stated(prompt, before, after, [])
    assert (after["gameplay"]["ending"], after["pacing"]["length_s"], after["level"]["shape"], after["level"]["blocks"]) == \
        ("cliffhanger", 45.0, "narrow_center", 6)
    # the request's own screen (case 09's revision answered "no clock visible" with the clock)
    before = _fresh()
    before["visuals"]["hud_timer"] = False
    after = copy.deepcopy(before)
    after["visuals"]["hud_timer"] = True
    guided.keep_stated("A near-fail with the clock hidden.", before, after, [])
    assert after["visuals"]["hud_timer"] is False


def test_a_plain_solve_is_a_win():
    """Round 2, case 14: "show the player stuck once before solving it" was planned as a near-fail. A solve the
    request names, with nothing about the clock, is a clean win unless the reference's own ending is a near-fail."""
    a = _lol_reading(["hook"])
    b = _fresh()
    b["gameplay"]["ending"] = "near_fail"
    V.apply(b, CASE14, [a])
    assert b["gameplay"]["ending"] == "win" and any("plain solve" in x for x in b["assumptions"])
    for prompt in ("Show the player solving it with 2 seconds left.", "Solve the level, barely in time.",
                   "Stop before the level is solved."):
        b = _fresh()
        b["gameplay"]["ending"] = "near_fail"
        assert V.plain_solve(b, prompt, {}) is None and b["gameplay"]["ending"] == "near_fail", prompt
    b = _fresh()
    b["gameplay"]["ending"] = "near_fail"
    assert V.plain_solve(b, CASE14, {"ending": "near_fail", "structure": []}) is None or V.mapped_ending(
        {"ending": "near_fail", "structure": []}) != "near_fail"


# ---------- round 2, second rerun (2026-10-17) ----------

def _version(n, misses=0, overall="ship", brief=None, match=()):
    checks = [{"check": f"Reference: miss {i}", "status": "failed", "detail": "x", "where": "plan", "from": "reference"}
              for i in range(misses)]
    return {"id": "job", "n": n, "checks": checks, "brief": brief or _fresh(),
            "review": {"overall": overall, "match": list(match), "fixes": ["make it faster"]}}


def test_an_unasked_viewer_note_does_not_start_a_revision():
    """Round 2 rerun, case 03: v1 met 20 of 20 and the viewer said ship, but its "not as asked: difficulty or pacing" on
    "create a similar game in Color Block Jam" (the pacing is not asked; the stretch rule's tempo is the flow's) started
    two revisions that undid the play. With nothing measured missed, only a note about what the request asks or the
    reading set starts one."""
    from cbj.workflows import guided
    b = _fresh()
    a = _pure_play_analysis()
    a["plan"] = {"constraints": [], "source": "planner", "level": "full", "focus": ["concept", "pacing", "structure"]}
    V.apply(b, SIMILAR, [a])
    b["planner"] = {"references": [a]}
    assert "difficulty_pacing" not in guided.asked_controls(SIMILAR, b) and "sequence" in guided.asked_controls(SIMILAR, b)
    pace = {"control": "difficulty or pacing", "verdict": "partial", "seen": "slow from 9 to 15 s"}
    v = _version(1, brief=b, match=[pace])
    assert guided.feedback(SIMILAR, v) is None and v["review_not_asked"][0].startswith("difficulty or pacing")
    flow = {"control": "the sequence of events", "verdict": "partial", "seen": "a 6 s end card"}  # the reading set the flow
    assert "the sequence of events" in guided.feedback(SIMILAR, _version(1, brief=b, match=[flow]))
    assert guided.feedback(SIMILAR, _version(1, misses=1, brief=b, match=[pace]))  # a measured miss: as before
    # the pacing asked: the same note starts one
    a7 = _pacing_reading()
    b7 = _fresh()
    V.apply(b7, CASE07, [a7])
    b7["planner"] = {"references": [a7]}
    assert guided.feedback(CASE07, _version(1, brief=b7, match=[pace]))


def test_the_final_version_is_the_best_not_the_last():
    """Round 2 rerun: case 03's v3 (a miss, the viewer's fix) became final over v1 (no miss, ship); case 09's v2 (fix)
    over v1 (ship), both passing every check. Fewest misses, then ship before fix, then the later version."""
    from cbj.workflows import guided
    log = lambda *_: None  # noqa: E731
    v1, v2, v3 = _version(1), _version(2, misses=1, overall="fix"), _version(3, misses=1, overall="fix")
    assert guided.best_version(log, [v1, v2, v3]) is v1 and v1["final"]["of"] == [1, 2, 3]
    v1, v2 = _version(1, overall="ship"), _version(2, overall="fix")
    assert guided.best_version(log, [v1, v2]) is v1
    v1, v2 = _version(1, overall="ship"), _version(2, overall="ship")
    assert guided.best_version(log, [v1, v2]) is v2  # a tie: the later
    v1, v2 = _version(1, misses=2), _version(2, misses=1, overall="fix")
    assert guided.best_version(log, [v1, v2]) is v2


def test_the_hook_is_taken_by_its_kind():
    """Round 2 rerun, case 14: "the video starts directly with a puzzle board and a hand cursor pointing at a block" was
    taken by its timing alone; the ad opened on a headline and the row passed on the start. Its kind is taken now (the
    play from the first frame, no still opening), and the row compares the kind as well as the start."""
    notes = _lol_reading(["hook"])["notes"]
    notes.update(hook="The video starts directly with a puzzle board and a hand cursor pointing at a block, presenting an "
                      "immediate gameplay puzzle.", captions_seen=[])
    assert V.hook_kind(notes) == "gameplay"
    assert V.hook_kind({"hook": "A caption asks 'Can you clear it?' over the board", "structure": []}) == "caption"
    assert V.hook_kind({**notes, "hook": "Text on screen: only 1% can solve this"}) == "caption"
    a = _lol_reading(["hook"])
    a["notes"] = notes
    b = _fresh()
    b["sequence"]["intro_s"] = 1.0
    prov = V.apply(b, CASE14, [a])[0]
    assert prov["hook_kind"] == "gameplay" and b["sequence"]["intro_s"] == 0.0
    assert any(x.startswith("the hook's kind: the play from the first frame") for x in prov["adapted"])
    # the row: a still opening fails; the play from frame 0 with ad.py's own hook caption is shown, not judged
    hook_layer = {"id": "hook", "kind": "caption", "text": "Can you clear it?", "from_s": 0.0, "to_s": 1.6}
    still = {"parts": [{"id": "intro", "from_s": 0.0, "to_s": 1.0}, {"id": "play", "from_s": 1.0, "to_s": 20.0}]}
    row = audit.hook_row(notes, [], still, {"hook": hook_layer})
    assert row["status"] == "failed" and "still frame" in row["detail"]
    row = audit.hook_row(notes, [], {"parts": [{"id": "play", "from_s": 0.0, "to_s": 20.0}]}, {"hook": hook_layer})
    assert row["status"] == "info" and "ad.py draws on frame 0" in row["detail"] and "gameplay hook" in row["detail"]
    # a caption hook: the function as well as the start
    dare = {"hook": "A dare: bet you can't clear this", "structure": [{"from_s": 0, "to_s": 2, "purpose": "hook"}]}
    segs = [{"from_s": 0.0, "to_s": 2.0, "purpose": "hook"}]
    play = {"parts": [{"id": "play", "from_s": 0.0, "to_s": 20.0}]}
    assert audit.hook_row(dare, segs, play, {"hook": hook_layer})["status"] == "failed"  # a challenge for a dare
    assert audit.hook_row(dare, segs, play, {"hook": {**hook_layer, "text": "Bet you can't clear this!"}})["status"] == "pass"


def test_the_hidden_clocks_result_fits_one_line():
    """Round 2 rerun, case 09: "Phew! 2 seconds left!" wrapped to two lines, was moved up 41 px and sat on the "+50"
    button. The result caption takes the first form that fits one line, measured as the compositor does."""
    from cbj.ad import BAND, STYLES
    from cbj.draw import wrap
    width = int(BAND["max_w"] / 1.05) - 2 * max(2, STYLES["title_l"] // 9)
    assert len(wrap("Phew! 2 seconds left!", STYLES["title_l"], width)) == 2
    assert V.one_line(["Phew! 2 seconds left!", "Phew! 2 s left!", "2 s left!"]) == "Phew! 2 s left!"
    b = _fresh()
    b["gameplay"].update(ending="near_fail", clock_left_s=2)
    b["concept"]["result"] = "Phew! 2 seconds left!"  # a two-line form planned earlier is replaced too
    V.hidden_clock_captions(b, CASE09)
    assert b["concept"]["result"] == "Phew! 2 s left!" and len(wrap(b["concept"]["result"], STYLES["title_l"], width)) == 1


def test_even_is_judged_with_the_references_own_band():
    """Round 2 rerun, case 05: the pacing row failed on "even" only (1.20 s of pauses in the first third, 0.92 s in the
    last). The reference calls a change even within a 1.3 ratio of its thirds; the ad is held to the same band (it was
    15 % of the larger, about 1.18). Case 05's 1.30 still fails, by a hair: the band is not widened to pass it."""
    assert audit.pause_change_ok("even", {"first": 1.68, "last": 1.60})  # case 07, fixed
    assert audit.pause_change_ok("even", {"first": 1.2, "last": 0.95})  # 1.26: even for the reference, now for the ad
    assert not audit.pause_change_ok("even", {"first": 1.20, "last": 0.92})  # case 05: 1.304
    assert audit.EVEN_RATIO == 1.3


# ---------- round 2, third rerun (2026-10-17) ----------

def test_a_restored_field_takes_its_plan_text_with_it():
    """Rerun 3, case 09: the final version's visuals text said "The clock is now shown on screen" while the pin had put
    the hidden clock back and the frames show no HUD. A control whose fields are all the base version's again gets the
    base's text; one with other changes loses the sentences about the restored field and says what was kept."""
    from cbj.workflows import guided
    before = _fresh()
    before["gameplay"].update(ending="near_fail", clock_left_s=2)
    V.apply(before, CASE09, [_close_up()])
    base_text = B.control(before, "visuals")["plan"]
    after = copy.deepcopy(before)
    after["visuals"]["hud_timer"] = True
    B.control(after, "visuals")["plan"] = "The reference's framing stays. The clock is now shown on screen so viewers can see time running out."
    guided.pin_reference(before, after, [])
    assert after["visuals"]["hud_timer"] is False and B.control(after, "visuals")["plan"] == base_text
    # mixed: the zoom is a new change the pin does not cover, so the text keeps it and drops the clock sentence
    after = copy.deepcopy(before)
    after["visuals"]["hud_timer"], after["visuals"]["caption_fill"] = True, "#FFFFFF"
    B.control(after, "visuals")["plan"] = "White captions now. The clock is now shown on screen so viewers can see time running out."
    guided.pin_reference(before, after, [])
    text = B.control(after, "visuals")["plan"]
    assert text.startswith("White captions now.") and "clock is now shown" not in text and "Kept as in the version before: the HUD" in text
    # a revision text about a control none of whose fields changed is the base's
    after = copy.deepcopy(before)
    B.control(after, "gameplay")["plan"] = "Now a clean win."
    assert guided.unchanged_texts(before, after) == ["gameplay"] and B.control(after, "gameplay")["plan"] == B.control(before, "gameplay")["plan"]
    # a stated value restored by keep_stated takes its text too
    before = _fresh()
    before["gameplay"].update(ending="win", mistakes=1, mistake_kinds=["blocked"])
    B.control(before, "gameplay")["plan"] = "A win after one stuck moment."
    after = copy.deepcopy(before)
    after["gameplay"]["mistakes"] = 2
    B.control(after, "gameplay")["plan"] = "Two stuck moments now, so the struggle reads longer."
    guided.keep_stated(CASE14, before, after, [])
    assert B.control(after, "gameplay")["plan"] == "A win after one stuck moment."


def test_the_stuck_moment_points_at_one_piece():
    """Rerun 3, case 14: "O1 (orange) heads for its gate, but O2 (orange) is in the way" under "I can't reach orange!".
    With a blocked move planned and no colours named, the guided plan adds a stuck step whose mover and blocker are two
    colours of the board's palette; an event's colour is one block on the generated board (generate's singles), so the
    caption names a single piece. The request's own colours or stuck step, a cliffhanger, or no palette: nothing."""
    from cbj import generate
    a = _lol_reading(["hook"])
    b = _fresh()
    b["gameplay"].update(ending="win", mistakes=1, mistake_kinds=["blocked"])
    prov = V.apply(b, CASE14, [a])[0]
    ev = [e for e in b["gameplay"]["events"] if e["action"] == "stuck"]
    assert len(ev) == 1 and ev[0]["block"]["colour"] != ev[0]["by"] and {ev[0]["block"]["colour"], ev[0]["by"]} <= set(b["level"]["colours"])
    assert "gameplay.events" in b["reference"]["set"] and any(x.startswith("the stuck moment points at one piece") for x in prov["adapted"])
    assert B.check(b)["gameplay"]["events"] == b["gameplay"]["events"]  # valid as the brief's own
    assert "singles" in generate.Spec.__dataclass_fields__  # the generator's one-block-per-named-colour rule
    for prompt, over in (("Use this ad's hook, and show the red block stuck once before solving it.", {}),
                         ("Use this ad's hook and its cursor, and show the player stuck once.", {"ending": "cliffhanger"}),
                         (CASE14, {"mistakes": 0})):
        b = _fresh()
        b["gameplay"].update({"ending": "win", "mistakes": 1, "mistake_kinds": ["blocked"], **over})
        V.apply(b, prompt, [_lol_reading(["hook"])])
        assert not any(e["action"] == "stuck" for e in b["gameplay"]["events"]), (prompt, over)
    b = _fresh()  # no palette known: left to the generator, said
    b["gameplay"].update(ending="win", mistakes=1)
    assert V.stuck_step(b, CASE14, set()) is None and any("left to the generator" in x for x in b["assumptions"])


def test_the_stuck_row_says_whether_the_caption_points_at_one_piece(tmp_path):
    rec = tmp_path / "recordings" / "r1"
    rec.mkdir(parents=True)
    vdir = tmp_path / "job" / "v1"
    vdir.mkdir(parents=True)
    (rec / "play.json").write_text(json.dumps({"beats": [{"kind": "solve", "note": ""},
                                                         {"kind": "mistake", "note": "O1 (orange) heads for its gate, but O2 (orange) is in the way"}]}))
    (vdir / "level.json").write_text(json.dumps({"GridBlockDatas": [{"blockColor": 4}, {"blockColor": 4}, {"blockColor": 5}]}))
    manifest = {"gameplay": {"recording": "recordings/r1"},
                "moments": [{"id": "drag_1", "kind": "mistake", "block": "orange", "at_s": 2.3, "also": "wrong_move"}]}
    row = audit.stuck_row(manifest, vdir)
    assert row["status"] == "info" and "2 orange blocks on the board (the caption cannot tell which)" in row["detail"]
    assert row["detail"].startswith("drag 2: the orange block is stuck at 2.3 s")  # numbered as the Mistakes check
    assert "the blocker is orange (the same colour)" in row["detail"]
    (rec / "play.json").write_text(json.dumps({"beats": [{}, {"kind": "mistake", "note": "O1 (orange) heads for its gate, but P1 (purple) is in the way"}]}))
    (vdir / "level.json").write_text(json.dumps({"GridBlockDatas": [{"blockColor": 4}, {"blockColor": 5}]}))
    row = audit.stuck_row(manifest, vdir)
    assert "1 orange block on the board (the caption points at one piece)" in row["detail"] and "(another colour)" in row["detail"]
    assert audit.stuck_row({"moments": []}, vdir) is None


def test_a_wall_cell_off_does_not_cut_the_blocks():
    """Rerun 3, case 05: trailer 2 (about 5x7, 9 blocks, one 2-cell wall) read as 4x7 holes, 9 blocks, 4 wall cells.
    The 4x7 holes board has exactly 4 walls but holds 6, and the blocks were cut to 6 (7 after the play levers, on
    4x8, the rows grown alone). A wall cell off is within the reading's error: 5x8 holes, 5 walls, keeps the 9."""
    assert V.wall_choice(4, 4, 7, 9, "varied") == ("holes", 5, (5, 8, 9))
    # the earlier choices hold: a 2-3 cell wall is the 3-wall holes board, none or one is open, 5 is 5x8
    assert [V.wall_choice(w, 4, 7, 10, "varied")[:2] for w in (0, 1, 2, 3, 5)] == \
        [("open", 0), ("open", 0), ("holes", 3), ("holes", 3), ("holes", 5)]
    b = _fresh()
    prov = V.apply(b, CASE05, [_board_analysis(board=_trailer2_board(columns=4, rows=7, blocks=9, wall_cells=4))])[0]
    lv = b["level"]
    assert (lv["shape"], lv["width"], lv["height"], lv["blocks"]) == ("holes", 5, 8, 9)
    assert "a wall cell off the reading" in prov["board_walls"]



# ---------- round 2, fourth rerun (2026-10-17) ----------

def test_the_stuck_row_reads_the_beat_the_mistakes_check_names(tmp_path):
    """Rerun 4: 05 (a cliffhanger, no mistake) got "the purple block is stuck at 17.33 s" from its last bump, and 09 got
    "the orange block" from a hesitation while the Mistakes check named drag 4, the blue block. The row reads the first
    "mistake" beat of the recording, numbered as that check does; no mistake played, no row."""
    rec = tmp_path / "recordings" / "r1"
    rec.mkdir(parents=True)
    vdir = tmp_path / "job" / "v1"
    vdir.mkdir(parents=True)
    beats = [{"kind": "solve"}, {"kind": "hesitate", "note": "O1 (orange) is picked up and put back"}, {"kind": "solve"},
             {"kind": "mistake", "note": "B (blue) heads for its gate, but D1 (dark green) is in the way"}]
    (rec / "play.json").write_text(json.dumps({"beats": beats}))
    (vdir / "level.json").write_text(json.dumps({"GridBlockDatas": [{"blockColor": 2}, {"blockColor": 6}, {"blockColor": 4}]}))
    moments = [{"id": "drag_1", "kind": "hesitate", "block": "orange", "at_s": 2.47, "also": "wrong_move"},
               {"id": "drag_3", "kind": "mistake", "block": "blue", "at_s": 6.07}]
    row = audit.stuck_row({"gameplay": {"recording": "recordings/r1"}, "moments": moments}, vdir)
    assert row["detail"].startswith("drag 4: the blue block is stuck at 6.07 s") and "the blocker is dark green (another colour)" in row["detail"]
    (rec / "play.json").write_text(json.dumps({"beats": [{"kind": "solve"}, {"kind": "bump", "note": "P1 (purple) ..."}]}))
    assert audit.stuck_row({"gameplay": {"recording": "recordings/r1"}, "moments": [
        {"id": "drag_1", "kind": "bump", "block": "purple", "at_s": 17.33, "also": "wrong_move"}]}, vdir) is None
    # the captions-fit row: a hesitation is no wrong move
    b = _fresh()
    b["gameplay"].update(ending="win", mistakes=0)
    row = audit.captions_fit_row({"gameplay": {"ending": "win"}, "layers": [{"id": "cap_mistake", "text": "Oops!"}],
                                  "moments": [{"id": "drag_1", "kind": "hesitate", "also": "wrong_move"}]}, b)
    assert row["status"] == "failed"


def _play_take(vdir, play_s, drags, duration_s=30.0):
    times = [1.0 + (play_s - 1.5) * i / max(1, drags - 1) for i in range(drags)]
    (vdir / "parts.json").write_text(json.dumps({"duration_s": duration_s, "parts": [{"id": "play", "from_s": 0.0, "to_s": play_s}],
                                                 "moments": [{"id": f"drag_{i}", "at_s": x} for i, x in enumerate(times)],
                                                 "gameplay": {"drags": drags}}))


def _case05_brief():
    a = _pure_play_analysis()
    a["pacing"] = {"dps": 0.31, "tempo": "normal", "tempo_source": "counts", "change": "even", "source": "motion"}
    a["notes"]["pacing"] = "normal"
    a["focus"], a["level"] = ["screen", "pacing", "structure"], "targeted"
    a["plan"] = {"constraints": [], "source": "planner", "level": "targeted", "focus": ["screen", "pacing", "structure"]}
    a["notes"]["board"] = _trailer2_board(columns=4, rows=7, blocks=9, wall_cells=3)
    b = _fresh()
    b["gameplay"].update(ending="cliffhanger", blocks_left=3)
    V.apply(b, CASE05, [a])
    b["planner"] = {"references": [a]}
    return a, b


def test_a_cut_plays_its_moves_minus_the_blocks_it_leaves_and_a_short_take_turns_a_lever(tmp_path, monkeypatch):
    """Rerun 4, case 05: a cliffhanger cutting with 3 blocks left plays 9 moves as 6 drags; six played drags is the most
    studio paces with a long look in a 30 s ad, and the take played 19.5 of 21 s. The moves are the drags played plus
    the cut's blocks; a hesitation (its own pace, no cost to the grade) fills the rest; a revision whose levers cannot
    change says which limit stops the play."""
    from cbj import studio
    from cbj.workflows import guided
    a, b = _case05_brief()
    rec = b["reference"]["play"]
    play, rate, grade = V.expected_play(b, rec["tempo"], rec["moves"], hesitations=0)
    assert grade == "deliberate" and round((rec["moves"] - 3) / (play / 3.36), 1) == 1.0  # played = moves - the 3 left
    assert rec["hesitations"] == 1 and rec["expected_s"] >= rec["target_s"] - 0.5
    # (b) the board: 3 walls read on 4x7 is the 3-wall 5x7 holes board (5x8 holes has 5 walls, two off), and more blocks
    # would cost studio's long look: the cap says so when the play falls short
    assert (b["level"]["shape"], b["level"]["width"], b["level"]["height"]) == ("holes", 5, 7)
    # (c) a short take whose levers are all turned: the revision says which limit stops it
    monkeypatch.setattr(studio, "STUDIO", tmp_path)
    vdir = tmp_path / "job" / "v1"
    vdir.mkdir(parents=True)
    _play_take(vdir, 17.0, rec["moves"] - 3 + rec["hesitations"])
    v = {"id": "job", "n": 1, "brief": b}
    line = guided.play_again(v, copy.deepcopy(b), CASE05, [])
    assert line.startswith("nothing is left to change for the play") and "because" in line
    assert "studio paces a solve with a long look" in line or "studio records at most" in line or "the board holds" in line


def test_a_revision_of_a_take_over_the_stated_length_does_not_lengthen_it(tmp_path, monkeypatch):
    """Rerun 4, case 09: 44.4 s of recording made the 45 s ad 48 s; the revision added a speeds-up curve (careful early
    pauses) and made it 49 s. A take over the stated length: the revision's lengthening changes go back, and the tempo
    whose play fits the room the stated length leaves is chosen with the take's measure."""
    from cbj import studio
    from cbj.workflows import guided
    monkeypatch.setattr(studio, "STUDIO", tmp_path)
    b = _fresh()
    b["gameplay"].update(ending="near_fail", clock_left_s=2)
    b["pacing"].update(length_s=45.0, tempo="normal", curve="even")
    V.apply(b, CASE09, [_close_up()])
    b["pacing"]["tempo"] = "normal"  # the take's tempo (the fill's own pick is calm: round 4, case 29)
    vdir = tmp_path / "job" / "v1"
    vdir.mkdir(parents=True)
    _play_take(vdir, 41.9, 16, duration_s=48.0)
    v = {"id": "job", "n": 1, "brief": b}
    after = copy.deepcopy(b)
    after["pacing"]["curve"], after["gameplay"]["hesitations"] = "speeds_up", 2
    line = guided.length_guard(v, after, CASE09)
    assert line.startswith("the take ran 48 s for the stated 45 s") and after["pacing"]["curve"] == "even"
    assert after["pacing"]["tempo"] == "fast" and "pacing.tempo" in after["changed"]
    _play_take(vdir, 38.0, 16, duration_s=45.0)  # a take that fitted: nothing
    assert guided.length_guard(v, copy.deepcopy(b), CASE09) is None


def test_a_viewer_revision_must_change_what_the_viewer_points_at():
    """Rerun 4, case 14: the viewer said the stuck moment is quick (gameplay); the revision added a camera punch-in
    (visuals) and re-used the same recording. A revision the viewer alone started changes a control the viewer's points
    are about, or no version is made."""
    from cbj.workflows import guided
    a = _lol_reading(["hook"])
    b = _fresh()
    b["gameplay"].update(ending="win", mistakes=1, mistake_kinds=["blocked"])
    V.apply(b, CASE14, [a])
    b["planner"] = {"references": [a]}
    v = _version(1, brief=b, match=[{"control": "gameplay behaviour", "verdict": "partial", "seen": "the stuck moment is quick"}])
    v["review"]["fixes"] = ["Let the green block bump its blocker and pause for a beat."]
    assert guided.viewer_points(CASE14, v) == {"gameplay"}
    after = copy.deepcopy(b)
    after["visuals"]["punch_ins"] = [{"from_s": 1.0, "to_s": 4.0, "zoom": 1.12, "toward": "Green"}]
    assert not set(B.changed_controls(b, after)) & guided.viewer_points(CASE14, v)


def test_the_mistake_hold_is_play_pys():
    """Rerun 4, case 14: "let the green block bump its blocker and pause for a beat". The press into the blocker is
    play.MISTAKE_HOLD_F (0.6 s) and the look after it play's own pauses; no brief field sets them (reported, play.py is
    not changed)."""
    from cbj import play
    assert play.MISTAKE_HOLD_F == 18 and "hold" not in json.dumps(B.SCHEMA["properties"]["gameplay"])


# ---------- round 2, fifth rerun (2026-10-17) ----------

def test_the_taken_pace_wins_over_the_fill():
    """Rerun 5, case 05: the reader counted 0.24 drags a second (calm); the play decision filled 21 of 21 s with 10 moves
    and a hesitation, and the take played 0.5 drags a second ("normal"), failing the pacing row. With no option in the
    reference's class, the nearest rate wins (fewer moves, no hesitation, a shorter play), and the line says why: the
    reference is slower than play.py's longest look."""
    a, b = _case05_brief()
    a["pacing"].update(dps=0.24, tempo="calm")
    a["notes"]["pacing"] = "calm"
    b = _fresh()
    b["gameplay"].update(ending="cliffhanger", blocks_left=3)
    prov = V.apply(b, CASE05, [a])[0]
    rec = prov["play"]
    best = 1 / max(V.SEC_PER_DRAG.values())
    assert rec["hesitations"] == 0 and abs(rec["rate"] - best) < 0.02 and rec["grade"] == "deliberate"
    assert "slower than play.py's longest look allows" in rec["cap"]
    line = next(x for x in prov["adapted"] if x.startswith("the play fills about"))
    assert "it stops there: the reference's calm pace (0.24 drags a second) is slower than play.py's longest look" in line
    # in the class, the fill still decides (the case-05 normal reading)
    a2, b2 = _case05_brief()
    assert V.tempo_class(b2["reference"]["play"]["rate"]) == "normal"


def test_a_rule_that_changes_a_planned_field_corrects_its_text():
    """Rerun 5, case 14: plain_solve made the ending a win, but the gameplay plan still said "solve the level with a
    second left on the clock" and an assumption argued for a near-fail; the viewer quoted it as a miss. A field a rule
    changes takes the planner's words for its old value with it, in the control's text and the planner's assumptions."""
    a = _lol_reading(["hook"])
    b = _fresh()
    b["gameplay"].update(ending="near_fail", mistakes=1, mistake_kinds=["blocked"])
    B.control(b, "gameplay")["plan"] = ("The player drags one block toward its door once and another block stops it. Then they "
                                        "find the fix and solve the level with a second left on the clock.")
    b["assumptions"] = ["'Solving it' is read as a near-fail finish: one stuck moment, then the solve with a second left.",
                        "'Its hook' is read as the reference's opening."]
    V.apply(b, CASE14, [a])
    plan = B.control(b, "gameplay")["plan"]
    assert b["gameplay"]["ending"] == "win" and "a second left" not in plan and plan.startswith("The player drags one block")
    assert "The level ends in a clean win" in plan
    assert not any("near-fail finish" in x for x in b["assumptions"]) and "'Its hook' is read as the reference's opening." in b["assumptions"]
    # the hidden clock: "the clock is shown" goes when the screen hides it
    before = {"visuals": {"hud_timer": True}, "controls": [{"control": "visuals", "plan": "Dark look. The clock is shown on screen.",
                                                            "status": "applied", "asked": None, "why": None}], "assumptions": []}
    after = copy.deepcopy(before)
    after["visuals"]["hud_timer"] = False
    after["controls"][0]["plan"] += " From the reference video x.mp4: the screen: no HUD."
    assert V.correct_texts(before, after) == ["visuals"]
    assert after["controls"][0]["plan"] == "Dark look. From the reference video x.mp4: the screen: no HUD."


# ---------- round 3 (2026-10-17): the case's range, the length from the play, long hooks, solve and breathe words,
# mistakes from parts only, NVIDIA's still budget ----------

R3_P1 = ("Analyze the attached reference video and generate a new 30–60 second Color Block Jam ad inspired by its main "
         "creative concept. Follow a similar storytelling structure, visual rhythm, and progression of tension and "
         "satisfaction, but adapt everything to authentic Color Block Jam gameplay.")
R3_P2 = ("Create a new Color Block Jam ad using the attached video as a creative reference. Keep its central concept and "
         "overall progression, but make the opening more immediate and the gameplay pacing faster. Build tension through "
         "increasingly rapid interactions, then give the final solution a satisfying moment to breathe.")


def _r3_analysis(dur, structure, board=None, ending="win", focus=("concept",), level="full", **notes):
    return {"file": "ref.mp4", "kind": "video", "focus": list(focus), "level": level, "analysed_s": dur,
            "facts": {"duration_s": dur}, "plan": {"constraints": []},
            "notes": {"structure": structure, "ending": ending, "board": board, "captions_seen": [], "mistakes": [],
                      "mistakes_shown": False, **notes}}


SMALL_BOARD = {"columns": 4, "rows": 4, "shape": "open", "blocks": 3, "colours": ["red", "blue"], "pieces": "small"}


@pytest.mark.parametrize("prompt", [
    "generate a new 30–60 second Color Block Jam ad", "a 30-60 second ad", "make it 30 to 60 seconds long",
    "a 30–60s creative", "between 30 and 60 seconds", R3_P1])
def test_a_range_inside_the_cases_30_to_60_is_no_stated_length(prompt):
    """Round 3, cases 16-18: "a new 30–60 second ad" was read as 60 s, and three ads were made 60 s long with 10-41 s end
    cards. A range whose ends lie in the case's 30-60 s restates the case: no length, kept as length_range (info)."""
    a = audit.asked(prompt, case_range=True)  # the video-reference workflow's reading
    assert a["length_s"] is None and a["length_range"] == (30.0, 60.0)
    assert "length" not in V.stated(prompt, [], video=True)
    assert "30-60 s (the case's range, not a stated length)" in audit.facts_read(a)
    # the text and image workflows read it as before (the owner, 2026-10-17): the range's top as a stated length
    if "30 and 60" not in prompt:
        d = audit.asked(prompt)
        assert d["length_s"] == 60.0 and "length_range" not in d and "length" in V.stated(prompt, [])


@pytest.mark.parametrize("prompt, length", [("a 45 second ad", 45.0), ("a 45 second ad within the case's 30-60 s", 45.0),
                                            ("a 40-second Color Block Jam creative", 40.0)])
def test_a_single_length_is_still_stated(prompt, length):
    assert audit.asked(prompt, case_range=True)["length_s"] == length and "length" in V.stated(prompt, [], video=True)
    assert audit.asked(prompt)["length_s"] == length


def test_the_references_length_decides_inside_the_range():
    """With the range restated, the reference's own length brought into 30-60 s decides (R12): 28.9 s and 15 s give 30 s."""
    for dur, structure in ((28.9, [{"from_s": 0, "to_s": 28.9, "purpose": "gameplay"}]),
                           (14.9, [{"from_s": 0, "to_s": 1.5, "purpose": "hook"}, {"from_s": 1.5, "to_s": 12, "purpose": "gameplay"},
                                   {"from_s": 12, "to_s": 14.9, "purpose": "end_card"}])):
        b = _fresh()
        b["pacing"]["length_s"] = 60.0  # the planner's own pick from "30-60"
        V.apply(b, R3_P1, [_r3_analysis(dur, structure, SMALL_BOARD, ending="cliffhanger")])
        assert b["pacing"]["length_s"] == 30.0, dur


def test_the_length_comes_from_the_play():
    """Round 3, case 17 (a 60 s ad, a 37 s play, a 21 s end card): with no single length stated, a play the levers cannot
    stretch to the length shortens the ad (down to 30 s) instead of growing the end card; said in the play line and
    prov["play"]["length"]. A stated length stays."""
    ref = _r3_analysis(60.0, [{"from_s": 0, "to_s": 60, "purpose": "gameplay"}], SMALL_BOARD)
    b = _fresh()
    prov = V.apply(b, R3_P1, [copy.deepcopy(ref)])[0]
    L, play = b["pacing"]["length_s"], prov["play"]
    assert 30.0 <= L < 60.0 and play["length"]["from"] == 60.0 and play["length"]["to"] == L
    assert play["expected_s"] >= play["target_s"] - 0.5  # the play fills the length it chose
    line = next(x for x in prov["adapted"] if x.startswith("the play fills about"))
    assert f"the ad is {L:g} s, not 60 s" in line and "instead of the end card growing" in line
    assert "pacing.length" in prov["set"]  # a revision keeps it (guided.PINNED)
    b = _fresh()
    prov = V.apply(b, "A 60 second Color Block Jam ad like this video.", [copy.deepcopy(ref)])[0]
    assert b["pacing"]["length_s"] == 60.0 and "length" not in prov["play"]


def test_a_stated_single_length_is_the_briefs_before_the_play_is_planned():
    """Round 3, case 18: the play was planned for the plan's 30 s and the ad was then made at the asked length."""
    b = _fresh()
    assert b["pacing"]["length_s"] == 30.0
    prov = V.apply(b, "A 45 second Color Block Jam ad like this video.",
                   [_r3_analysis(28.9, [{"from_s": 0, "to_s": 28.9, "purpose": "gameplay"}], SMALL_BOARD)])[0]
    assert b["pacing"]["length_s"] == 45.0 and prov["play"]["target_s"] > 30.0


CASE18_STRUCTURE = [{"from_s": 0.0, "to_s": 12.0, "purpose": "hook", "captions": ["Can you solve it?"]},
                    {"from_s": 12.0, "to_s": 14.9, "purpose": "end_card"}]


def test_a_hook_over_most_of_the_clip_is_play():
    """Round 3, case 18: NVIDIA read another game's 15 s ad as "0-12 s hook; 12-14.9 s end card", and the ad took a 12 s
    hook, a 13 s play and a 41 s end card. A hook part longer than max(3 s, 25% of the clip) keeps its first 1.5 s as the
    hook (with its captions) and the rest is gameplay; a stretched comparison never expects a hook over 4 s."""
    segs = R.structure(copy.deepcopy(CASE18_STRUCTURE), 14.91)
    assert [(s["from_s"], s["to_s"], s["purpose"]) for s in segs] == [(0.0, 1.5, "hook"), (1.5, 12.0, "gameplay"),
                                                                        (12.0, 14.9, "end_card")]
    assert segs[0]["captions"] == ["Can you solve it?"] and segs[1]["captions"] == [] and "a 12 s hook" in segs[1]["split"]
    assert R.structure(segs, 14.91) == segs  # idempotent
    assert R.long_hooks([{"from_s": 0, "to_s": 3, "purpose": "hook"}], 14.9)[0]["to_s"] == 3  # a short hook stays
    # the reading stored before the rule: videoref reads it the same way
    b = _fresh()
    prov = V.apply(b, R3_P1, [_r3_analysis(14.91, copy.deepcopy(CASE18_STRUCTURE), SMALL_BOARD, ending="cliffhanger")])[0]
    lengths = next(x for x in prov["adapted"] if x.startswith("the parts' lengths"))
    assert "12 s hook" not in lengths and "1.5 s hook" in lengths
    # the stretched comparison: the old 12 s hook is expected as 4 s at most
    row = audit._stretched_lengths({"hook": 12.0, "end": 2.9}, {"hook": 3.0, "play": 23.0, "end": 4.0}, 14.9, 30.0)
    assert "hook 4.0 s expected" in row["detail"]


@pytest.mark.parametrize("words", [
    "then give the final solution a satisfying moment to breathe", "end on the solve", "show the solved board",
    "a satisfying clear at the end", "the player clears the whole board", "the last move clears it all",
    "until the player finishes the level"])
def test_the_requests_solve_words_make_a_win(words):
    """Round 3, case 19: "give the final solution a satisfying moment to breathe" kept the reference's cliffhanger, and the
    board was never solved. The request's solve words state the ending (a win), also over the reference's cliffhanger."""
    prompt = f"Create a new Color Block Jam ad like this video; {words}."
    assert "ending" in V.stated(prompt, [], video=True)
    b = _fresh()
    b["gameplay"].update(ending="cliffhanger", blocks_left=3)  # the planner took the reference's cut
    V.apply(b, prompt, [_r3_analysis(28.9, [{"from_s": 0, "to_s": 28.9, "purpose": "gameplay"}], SMALL_BOARD, ending="stopped")])
    assert b["gameplay"]["ending"] == "win" and b["gameplay"]["blocks_left"] is None
    assert any("the request names the solve, so the level is solved" in x for x in b["assumptions"])


@pytest.mark.parametrize("prompt", [
    "Create a version of this video; stop just before the final solution.",
    "Create a version of this video; the final solution comes with 2 seconds left on the clock."])
def test_solve_words_with_a_stop_or_the_clock_keep_their_own_ending(prompt):
    b = _fresh()
    b["gameplay"]["ending"] = "cliffhanger"
    assert V.plain_solve(b, prompt, {}) is None and b["gameplay"]["ending"] == "cliffhanger"


@pytest.mark.parametrize("words", ["give it a moment to breathe", "let the win breathe", "let it linger", "let it land",
                                   "hold the solved board"])
def test_a_moment_to_breathe_holds_the_result_and_drops_the_replay(words):
    """Round 3, case 19: the request's "moment to breathe" got a replay of an unfinished move and no held result."""
    prompt = f"A Color Block Jam ad like this video; {words}."
    assert {"hold", "replay"} <= V.stated(prompt, [], video=True)
    assert "replay" not in V.stated(prompt, [])  # the image workflow's stated() is unchanged (HOLD alone reads "hold the ... board")
    b = _fresh()
    b["sequence"].update(replay=True, hold_s=0.0)
    assert V.breathe(b, prompt)
    assert b["sequence"]["hold_s"] == V.BREATHE_HOLD_S and b["sequence"]["replay"] is False
    assert "moment to breathe" in B.control(b, "sequence")["plan"]
    b = _fresh()
    b["sequence"].update(replay=True, hold_s=3.0)
    V.breathe(b, f"{prompt} Add a slow-motion replay.")
    assert b["sequence"]["hold_s"] == 3.0 and b["sequence"]["replay"] is True  # never lowered; an asked replay stays


def test_case_19_ends_solved_with_its_moment():
    b = _fresh()
    b["gameplay"].update(ending="cliffhanger", blocks_left=3)
    b["sequence"]["replay"] = True
    prov = V.apply(b, R3_P2, [_r3_analysis(28.9, [{"from_s": 0, "to_s": 28.9, "purpose": "gameplay"}], SMALL_BOARD,
                                           ending="stopped")])[0]
    assert b["gameplay"]["ending"] == "win" and b["sequence"]["hold_s"] == V.BREATHE_HOLD_S and b["sequence"]["replay"] is False
    assert any(x.startswith("the request asks for a moment to breathe") for x in prov["adapted"])


def test_a_chain_caption_needs_the_streak_finish():
    """Round 3, case 19: "One move. Everything flies!" promised a chain the play never had. A chain caption stays only with
    gameplay.finish "streak"; otherwise the tool's own words; a caption the request quotes stays."""
    b = _fresh()
    b["gameplay"].update(ending="win", finish="auto")
    b["concept"].update(cascade="One move. Everything flies!", result="They all leave one after another!")
    image = copy.deepcopy(b)
    assert V.fit_captions(image) == [] and image["concept"] == b["concept"]  # the image workflow's call: unchanged
    notes = V.fit_captions(b, "A Color Block Jam ad like this video.", chain=True)
    assert b["concept"]["cascade"] == "Almost there!" and b["concept"]["result"] == V.OWN_LINES["result"]["win"]
    assert any("promises a chain of exits" in x for x in notes) and "concept.cascade" in b["changed"]
    b = _fresh()
    b["gameplay"].update(ending="win", finish="streak")
    b["concept"]["cascade"] = "One move. Everything flies!"
    V.fit_captions(b, "A Color Block Jam ad like this video.", chain=True)
    assert b["concept"]["cascade"] == "One move. Everything flies!"
    b = _fresh()
    b["gameplay"].update(ending="win", finish="auto")
    b["concept"]["cascade"] = "Everything flies!"
    V.fit_captions(b, 'A Color Block Jam ad with the caption "Everything flies!".', chain=True)
    assert b["concept"]["cascade"] == "Everything flies!"


def test_a_concept_read_takes_the_mistakes_from_the_parts_only():
    """Round 3, case 16 (trailer 2 has no wrong move): the reading's free list of wrong moves is approximate (8 of 12), so a
    concept read or a filled ending takes only the mistake parts, timestamped, at most one. A targeted ending read keeps
    the larger of the list and the parts; the request's own words keep theirs."""
    listed = [{"at_s": 5.0, "what": "a block bounces"}, {"at_s": 9.0, "what": "another"}]
    play = [{"from_s": 0, "to_s": 28.9, "purpose": "gameplay"}]
    with_parts = [{"from_s": 0, "to_s": 10, "purpose": "gameplay"}, {"from_s": 10, "to_s": 12, "purpose": "mistake"},
                  {"from_s": 12, "to_s": 14, "purpose": "mistake"}, {"from_s": 14, "to_s": 28.9, "purpose": "gameplay"}]
    for structure, want in ((play, 0), (with_parts, 1)):
        b = _fresh()
        V.apply(b, R3_P1, [_r3_analysis(28.9, structure, SMALL_BOARD, ending="stopped", mistakes=listed, mistakes_shown=True)])
        assert b["gameplay"]["mistakes"] == want, structure
    b = _fresh()
    V.apply(b, "End it like this video.", [_r3_analysis(28.9, play, SMALL_BOARD, ending="stopped", focus=["ending"],
                                                        level="targeted", mistakes=listed, mistakes_shown=True)])
    assert b["gameplay"]["mistakes"] == 2
    b = _fresh()
    b["gameplay"]["mistakes"] = 1
    V.apply(b, "Like this video, but show the player stuck once.",
            [_r3_analysis(28.9, play, SMALL_BOARD, ending="stopped", mistakes=listed, mistakes_shown=True)])
    assert b["gameplay"]["mistakes"] == 1
    from cbj.workflows import guided
    assert guided.PINNED["gameplay.mistakes"]  # a revision keeps the reference's count (case 16: 0, then 1, then 2)


def test_a_speeds_up_curve_fills_with_more_moves_not_calm_looks():
    """Round 3, case 16: a calm fill paused 2.05 s and 2.50 s a third where the request asked the play to speed up. With a
    speeds-up curve the fill comes from more moves at a normal tempo; calm only when nothing else fills; said in the line."""
    ref = _r3_analysis(28.9, [{"from_s": 0, "to_s": 28.9, "purpose": "gameplay"}],
                       {**SMALL_BOARD, "columns": 6, "rows": 6, "blocks": 8}, ending="win")
    b = _fresh()
    b["pacing"]["curve"] = "speeds_up"
    prov = V.apply(b, "Build tension like this video, speeding up toward the end.", [copy.deepcopy(ref)])[0]
    assert b["pacing"]["tempo"] != "calm" and "speeds up" in prov["play"]["curve"]
    b = _fresh()
    prov = V.apply(b, R3_P1, [copy.deepcopy(ref)])[0]
    assert b["pacing"]["tempo"] == "calm" and "curve" not in prov["play"]  # an even curve keeps the calm fill


# ---------- NVIDIA build's still budget (round 3) ----------

def test_the_reader_order_can_be_set(monkeypatch):
    calls = []

    class Fake:
        def __init__(self, name):
            self.name, self.errors, self.last_model = name, [], f"{name}-model"

        def describe(self, ask, part, path=None):
            calls.append(self.name)
            return "{}"
    monkeypatch.delenv("CBJ_VIDEO_READER", raising=False)
    assert R.reader_order() == (("gemini", "nvidia"), "default")
    monkeypatch.setenv("CBJ_VIDEO_READER", "nvidia,gemini")
    assert R.reader_order() == (("nvidia", "gemini"), "CBJ_VIDEO_READER")
    reader = R.VideoReader(gemini=lambda: Fake("gemini"), nvidia=lambda: Fake("nvidia"))
    assert reader.order == ("nvidia", "gemini") and reader.describe("a", {}) == "{}" and calls == ["nvidia"]
    assert reader.reader == "nvidia" and R.first_reader(reader) == "nvidia"
    monkeypatch.setenv("CBJ_VIDEO_READER", "nvidia")  # the one left out is tried last
    assert R.reader_order()[0] == ("nvidia", "gemini")
    monkeypatch.setenv("CBJ_VIDEO_READER", "bogus")
    assert R.reader_order() == (("gemini", "nvidia"), "default")


def test_a_still_is_asked_once_a_model_with_its_own_budget():
    """Round 3: super-vl reasoned for 16000 tokens on a 1920 px still (8000 doubled), each try waiting out 300 s, then the
    omni model's 503s. A still's ask: STILL_MAX_TOKENS, no doubling, no waits, one try a model; a model that answered
    nothing on a still is skipped for the read's later stills. The whole clip keeps its budget and its doubling."""
    c = _client([_reply(None, "length"), 503, _reply('{"ok": 1}')])
    with pytest.raises(ValueError):
        c.describe_still("ask", {"type": "text"})
    assert [b["max_tokens"] for b in c.calls] == [R.STILL_MAX_TOKENS] * 2 and c.waits == [] and c.still_dead == {"m1"}
    assert c.describe_still("ask", {"type": "text"}) == '{"ok": 1}' and len(c.calls) == 3 and c.last_model == "m2"
    assert any("skipped on this still" in e for e in c.errors)
    c = _client([_reply(None, "length"), _reply('{"ok": 1}')])  # the whole clip: as before
    assert c.describe("ask", {"type": "text"}) == '{"ok": 1}' and [b["max_tokens"] for b in c.calls] == [4000, 8000]
    c = _client([])

    def slow(body):
        c.calls.append(c._still)
        raise TimeoutError("timed out")
    c._post = slow
    with pytest.raises(ValueError):
        c.describe_still("ask", {})
    assert c.calls == [True, True] and c.waits == [] and c.still_dead == {"m1", "m2"}  # no retry ladder
    assert (R.STILL_MAX_TOKENS, R.STILL_TIMEOUT_S, R.BOARD_READ_BUDGET_S) == (4000, 150, 300.0)


class StillVision(FakeVision):
    """A reader that says which asks came as a still's (describe_still) and is NVIDIA first."""
    order = ("nvidia", "gemini")

    def __init__(self, *answers):
        super().__init__(*answers)
        self.stills = 0

    def describe_still(self, ask, part, path=None):
        self.stills += 1
        return self.describe(ask, part, path)


@needs_ffmpeg
def test_the_board_step_keeps_to_its_budget(clips):
    """Round 3: the board step took 1379-2413 s on NVIDIA. The frame's ask always runs; the crop's ask, the colour count and
    the size re-asks only while BOARD_READ_BUDGET_S remains ("skipped: budget"); the code's measure needs no model. With
    NVIDIA first the still is at most 1280 px; every ask here is a still's."""
    notes = {"structure": [{"from_s": 0, "to_s": 6, "purpose": "gameplay"}]}
    frame = {"board": {"columns": 5, "rows": 6, "blocks": 7, "colours": ["purple"]}, "box": {"x": 0.3, "y": 0.1, "w": 0.3, "h": 0.6}}
    vision = StillVision(frame)
    rec = R.read_board(vision, clips / "short.mp4", notes, {"duration_s": 6.0}, budget_s=0)
    assert len(vision.asks) == 1 and vision.stills == 1 and rec["board"]["blocks"] == 7
    assert rec["skipped"] == ["the crop's ask: skipped: budget", "the colour count: skipped: budget",
                              "size read 1: skipped: budget", "size read 2: skipped: budget", "size read 3: skipped: budget"]
    assert rec["crop"]["skipped"] == "budget" and rec["still_px"] == R.BOARD_STILL_PX_NVIDIA
    assert "measured" in rec or "measure_error" in rec  # the code's measure ran on the crop
    vision = StillVision(frame, {"board": {"columns": 5, "rows": 6, "blocks": 8, "colours": ["purple"]}})
    rec = R.read_board(vision, clips / "short.mp4", notes, {"duration_s": 6.0})
    assert len(vision.asks) == 6 == vision.stills and "skipped" not in rec
    rec = R.read_board(FakeVision(frame), clips / "short.mp4", notes, {"duration_s": 6.0})
    assert rec["still_px"] == R.BOARD_STILL_PX  # Gemini first (or a reader that does not say): the measured 1920 px


def test_the_ending_row_leaves_the_requests_solve_words_their_own(tmp_path):
    """Round 3, case 19: with the request's solve words the ending is its own; the reference's cliffhanger row is info."""
    gb = _guided_brief(notes={**NOTES, "ending": "stopped", "structure": [{"from_s": 0, "to_s": 28.9, "purpose": "gameplay"}]})
    gb["gameplay"]["ending"] = "win"
    row = _rows(tmp_path, gb, _manifest(duration_s=30.0), prompt=R3_P2)["the ending"]
    assert row["status"] == "info" and "the request sets the ending itself (win)" in row["detail"]



def test_the_round_3_rules_stay_on_the_video_path():
    """The owner (2026-10-17): the text and image workflows keep their behaviour. audit.asked reads "30–60 second" as 60 s
    by default; the guided revision's own keep_asked (keep_asked_guided) does not restore it, create.keep_asked still does;
    keep_stated and pin_reference apply the round-3 rules only to a version made from a reference video."""
    from cbj.workflows import guided
    from cbj.workflows.create import keep_asked
    assert audit.asked(R3_P1)["length_s"] == 60.0 and audit.asked(R3_P1, case_range=True)["length_s"] is None
    before, after = _fresh(), _fresh()
    after["pacing"]["length_s"] = 30.0
    assert guided.keep_asked_guided(R3_P1, before, after) == [] and after["pacing"]["length_s"] == 30.0
    assert keep_asked(R3_P1, before, after) and after["pacing"]["length_s"] == 60.0  # the text workflow, as before
    prompt = "A Color Block Jam ad like this picture; give the final solution a moment to breathe."
    for refs, kept in (([{"kind": "image", "file": "a.png"}], False), ([{"kind": "video", "file": "a.mp4"}], True)):
        before, after = _fresh(), _fresh()
        before["planner"] = {"references": refs}
        before["sequence"]["hold_s"], after["sequence"]["hold_s"] = 1.5, 0.0
        guided.keep_stated(prompt, before, after, [])
        assert (after["sequence"]["hold_s"] == 1.5) is kept, refs
        before, after = _fresh(), _fresh()
        before["planner"] = {"references": refs}
        before["reference"] = {"set": ["gameplay.mistakes"]}
        before["gameplay"]["mistakes"], after["gameplay"]["mistakes"] = 0, 2
        guided.pin_reference(before, after, [])
        assert (after["gameplay"]["mistakes"] == 0) is kept, refs


# ---------- the owner's trailer-2 creative (2026-10-17): the HUD over a zoomed board, "fewer moves", the asked end line ----

OWNER = ("I like this video's pace. Keep it, zoom in closer on the board, and use fewer moves so each one matters. "
         "End unsolved with a 'your turn' line.")


def _owner_reading():
    a = _pacing_reading(dps=0.28)
    a["notes"].update(game_or_product="Color Block Jam", hud={"level": "LEVEL 25", "clock": "01:05"},
                      framing={"board_share": 0.21, "hand_cursor": True, "other_items": []})
    return a


def _owner_brief(**level):
    """The brief as the planner left it for the owner's prompt: about 6 moves, zoom 1.1, "Your turn!" as the result."""
    b = _fresh()
    b["gameplay"].update(ending="cliffhanger", mistakes=0)
    b["level"].update(moves=6, **level)
    b["visuals"]["camera_zoom"] = 1.1
    b["concept"]["result"] = "Your turn!"
    b["assumptions"].append("'Fewer moves' read as about 6 moves, down from roughly 8 in the reference video.")
    return b


def test_fewer_moves_are_stated_on_the_video_path_only():
    assert "moves" in V.stated(OWNER, video=True) and "moves" not in V.stated(OWNER)  # the text and image paths: as before
    assert "blocks" in V.stated("Use fewer blocks than this video.", video=True)
    assert V.relative_moves(OWNER) == "fewer moves" and V.relative_moves("a few drags only") == "a few drags"
    assert V.relative_moves("Keep 12 moves.") is None


def test_fewer_moves_keep_the_planners_count_and_say_the_cause():
    """The owner's prompt: the planner read "fewer moves" as about 6; the play levers (the pace taken) set 10 to fill
    21 s. The relative words are the request's own: 6 stay, the shorter play is accepted, and the play line and
    prov["play"]["cap"] say why."""
    b = _owner_brief()
    prov = V.apply(b, OWNER, [_owner_reading()])[0]
    rec = prov["play"]
    assert b["level"]["moves"] == 6 and rec["moves"] == 6 and rec["moves_asked"] == "fewer moves"
    assert rec["expected_s"] < rec["target_s"] - 0.5
    assert rec["cap"].startswith(f"the request asks for fewer moves: 6 kept; the play fills {rec['expected_s']:.0f} of "
                                 f"{rec['target_s']:g} s")
    assert rec["hesitations"] <= V.MAX_HESITATIONS["cliffhanger"]
    line = next(x for x in prov["adapted"] if x.startswith("the play fills about"))
    assert "it stops there: the request asks for fewer moves: 6 kept" in line
    # never raised, also when the planner's count is under the board's blocks and the pace would want more
    b = _owner_brief(blocks=5)
    V.apply(b, OWNER, [_owner_reading()])
    assert b["level"]["moves"] == 6 and b["level"]["blocks"] == 5


def test_the_safe_zoom_table_is_the_measured_one():
    assert V.safe_zoom(4, 9) == (1.0, True) and V.safe_zoom(4, 7) == (1.0, True)  # under the HUD at zoom 1 already
    assert V.safe_zoom(7, 9) == (1.0, False) and V.safe_zoom(6, 8) == (1.0, False)  # rows - cols 2: no zoom room
    assert V.safe_zoom(7, 8) == (1.1, False) and V.safe_zoom(6, 6) == (B.ZOOM_RANGE[1], False)
    assert V.safe_zoom(9, 6) == (B.ZOOM_RANGE[1], False) and V.safe_zoom(None, 9) == (1.0, None)
    assert V.safe_zoom(None, 4) == (B.ZOOM_RANGE[1], None) and V.safe_zoom(None, None) == (None, None)
    # the model the table comes from: the top at zoom z is 1020 - (1020 - top) * z, clear while >= 636 - 10
    for top, z in ((708, 1.12), (673, 1.1), (627, 1.0)):
        assert V.ZOOM_CENTRE_Y - (V.ZOOM_CENTRE_Y - top) * z >= V.HUD_BOTTOM_Y - V.HUD_TOL_PX
    assert V.ZOOM_CENTRE_Y - (V.ZOOM_CENTRE_Y - 673) * 1.12 < V.HUD_BOTTOM_Y - 2  # 1.12 would leave 1 extra row only 2 px


def test_a_stated_zoom_hides_a_filled_hud():
    """The owner's creative: zoom 1.1 from "zoom in closer" and the HUD from the reference covered the board's top row.
    The request's words win over the filled value: the HUD is hidden, said in the assumptions and on the card. The size
    is generated later here ("fewer moves" states the level), so the most conservative cap (1) decides."""
    b = _owner_brief()
    prov = V.apply(b, OWNER, [_owner_reading()])[0]
    vs = b["visuals"]
    assert (vs["camera_zoom"], vs["hud_level"], vs["hud_timer"]) == (1.1, False, False)
    want = ("the HUD is hidden: the closer zoom would put it over the board's top row; the request asked for the zoom, the "
            "HUD came from the reference")
    assert any(x.startswith(want) for x in b["assumptions"]) and any(x.startswith(want) for x in prov["adapted"])
    assert want[0].upper() + want[1:] in B.control(b, "visuals")["plan"]
    hc = prov["hud_clear"]
    assert (hc["safe"], hc["size_known"], hc["zoom_stated"], hc["hud_asked"], hc["action"]) == (1.0, False, True, False, "hid the HUD")
    assert prov["screen"]["hud_level"] is False and "visuals.hud" in prov["set"]
    # a known board with room for the zoom keeps the HUD
    b = _owner_brief(width=9, height=8)
    V.apply(b, OWNER, [_owner_reading()])
    assert (b["visuals"]["camera_zoom"], b["visuals"]["hud_level"]) == (1.1, True)


def test_an_asked_hud_caps_the_zoom():
    b = _owner_brief(width=7, height=8)
    b["visuals"]["camera_zoom"] = 1.12
    prov = V.apply(b, OWNER + " Keep the clock on screen.", [_owner_reading()])[0]
    assert (b["visuals"]["camera_zoom"], b["visuals"]["hud_timer"]) == (1.1, True)
    assert any(x.startswith("the zoom is capped at 1.1, not 1.12: the request names the HUD, and a 7x8 board's top row")
               for x in b["assumptions"])
    assert prov["hud_clear"]["action"] == "capped the zoom at 1.1"
    b = _owner_brief(width=4, height=9)
    V.apply(b, OWNER + " Keep the clock on screen.", [_owner_reading()])
    assert b["visuals"]["camera_zoom"] is None and b["visuals"]["hud_timer"] is True
    assert V.hud_asked("show the timer") and V.hud_asked("with 3 seconds left") and not V.hud_asked(OWNER)
    assert V.zoom_stated(OWNER) and V.zoom_stated("a close-up of the board") and not V.zoom_stated("Take the pacing of this video.")


def test_a_zoom_from_the_reference_is_capped_and_a_tall_board_hides_an_unasked_hud():
    b = _fresh()
    b["level"].update(width=6, height=8)
    b["visuals"]["camera_zoom"] = 1.12
    b["reference"] = {}
    V.hud_clear(b, "Take the pacing of this video.")
    assert b["visuals"]["camera_zoom"] is None and b["visuals"]["hud_timer"] is True  # 6x8: no room, the HUD stays
    b = _fresh()
    b["level"].update(width=4, height=9)
    b["reference"] = {}
    line = V.hud_clear(b, "Take the pacing of this video.")
    assert line.startswith("the HUD is hidden: the game's framing of a 4x9 board puts it over the board's top row even at zoom 1")
    assert b["visuals"]["hud_level"] is False and b["reference"]["hud_clear"]["covered_at_1"] is True
    # the size not known and no zoom stated: left to the measured guard
    b = _fresh()
    b["visuals"]["camera_zoom"] = 1.1
    assert V.hud_clear(b, "Take the pacing of this video.") is None


def test_the_asked_end_line_is_the_cliffhangers_question():
    """The owner's "End unsolved with a 'your turn' line": the planner put "Your turn!" as the result; fit_captions
    dropped it as a cliffhanger's result, the ad showed "Can you see the move?" and the asked caption row failed. On the
    video path the asked end line is the question caption (concept.result), never dropped."""
    assert V.end_line(OWNER) == ("Your turn", "question")
    assert V.end_line("End with a your-turn line on the end card.") == ("Your turn!", "end_card")
    assert V.end_line('Put "Wow" over the hook. End on a cliffhanger.') is None
    b = _owner_brief()
    notes = V.fit_captions(b, OWNER, chain=True)
    assert b["concept"]["result"] == "Your turn!" and not any("is left out" in n for n in notes)
    assert any(n.startswith('the request asks for "Your turn!" at the end: it is the cliffhanger\'s question caption') for n in notes)
    # no exact words of the planner's: the request's
    b = _owner_brief()
    b["concept"]["result"] = None
    V.fit_captions(b, OWNER, chain=True)
    assert b["concept"]["result"] == "Your turn" and "concept.result" in b["changed"]
    # the end card when the request puts it there
    b = _owner_brief()
    V.fit_captions(b, "Stop before the last move, with a your-turn line on the end card.", chain=True)
    assert b["concept"]["end_title"] == "Your turn!" and b["concept"]["result"] is None
    # round 2 case 11 keeps working: the asked question stays
    b = _owner_brief()
    b["concept"]["result"] = "Can you see the move?"
    V.fit_captions(b, 'Stop with 2 blocks left and ask "Can you see the move?"', chain=True)
    assert b["concept"]["result"] == "Can you see the move?"
    # the image workflow (no chain) keeps its old behaviour
    b = _owner_brief()
    V.fit_captions(b, OWNER)
    assert b["concept"]["result"] is None


def _hud_frame(board_top=700, left=160, right=920, floor_from=None, bg=(221, 235, 252), hud=True):
    """A synthetic 1080x1920 frame of play: the background, a board (the rail's dark slate from `board_top` down, the
    cells' floor inside it) and the HUD's purple bar and badge on top."""
    import numpy as np
    a = np.zeros((1920, 1080, 3), np.uint8)
    a[:] = bg
    a[board_top:1500, left:right] = (60, 68, 89)
    a[board_top + 40 if floor_from is None else floor_from:1460, left + 40:right - 40] = (100, 115, 155)
    if hud:
        x0, y0, x1, y1 = (int(round(v * s)) for v, s in zip(audit.HUD_BOX, (1080, 1920, 1080, 1920)))
        a[y0:y1, x0:x1] = (171, 203, 246)  # the outline
        a[y0 + 8:y1 - 8, x0 + 8:x1 - 8] = (104, 60, 222)  # the purple
    return a


def test_hud_measure_on_synthetic_frames():
    clear = audit.hud_measure(_hud_frame(board_top=700))
    assert clear["shown"] and not clear["covered"] and clear["board_top"] == 700 and clear["margin"] == 64
    beside = audit.hud_measure(_hud_frame(board_top=560))  # the board reaches past the HUD's sides: its top seen there
    assert beside["covered"] and beside["board_top"] == 560
    cut = audit.hud_measure(_hud_frame(board_top=520, left=260, right=800, floor_from=600))  # within the HUD's width
    assert cut["covered"] and cut["cut"] and cut["board_top"] == 636
    below = audit.hud_measure(_hud_frame(board_top=640, left=260, right=800, floor_from=640))
    assert below["covered"] and below["floor_below"] >= audit.FLOOR_BELOW_SHARE  # the cells' floor right under the bar
    assert not audit.hud_measure(_hud_frame(board_top=560, hud=False))["shown"]
    dark = audit.hud_measure(_hud_frame(board_top=700, bg=(15, 20, 35)))  # a dark background is not the board
    assert not dark["covered"] and dark["board_top"] == 700


def _hud_vdir(tmp_path, frame):
    from PIL import Image
    vdir = tmp_path / "v1"
    (vdir / "ad").mkdir(parents=True)
    Image.fromarray(frame).save(vdir / "ad" / "poster.png")  # no ad.mp4: play_frame falls back to the poster
    return vdir


def test_the_hud_row_fails_with_a_lever_and_feeds_the_revision(tmp_path):
    from cbj.workflows import guided
    b = _owner_brief(width=4, height=9)
    b["visuals"].update(hud_level=True, hud_timer=True)
    covered = _hud_vdir(tmp_path / "a", _hud_frame(board_top=560))
    row = audit.hud_row(OWNER, b, covered, {})
    assert (row["check"], row["status"], row["where"], row["from"]) == ("Asked: the zoom", "failed", "plan", "prompt")
    assert "the HUD bar covers the board's top row at zoom 1.1" in row["detail"] and "hide it" in row["detail"]
    row = audit.hud_row("Take the pacing of this video.", b, covered, {})
    assert row["check"] == "Reference: the screen: the HUD over the board" and row["status"] == "failed"
    clear = _hud_vdir(tmp_path / "b", _hud_frame(board_top=700))
    assert audit.hud_row(OWNER, b, clear, {})["status"] == "pass"
    b["visuals"]["camera_zoom"] = None
    row = audit.hud_row("Keep the clock on screen.", b, covered, {})
    assert row["status"] == "info" and "CreativeRunner.FitCamera" in row["detail"]  # asked HUD, no zoom left: info
    # the revision: an unasked HUD is hidden; an asked one lowers the zoom
    miss = [{"check": "Asked: the zoom", "status": "failed", "from": "prompt", "where": "plan"}]
    before, after = _owner_brief(width=9, height=8), _owner_brief(width=9, height=8)
    notes = guided.hud_fix(OWNER, before, after, miss)
    assert after["visuals"]["hud_level"] is False and "visuals.hud" in after["changed"] and "is hidden" in notes[0]
    after = _owner_brief(width=9, height=8)
    notes = guided.hud_fix(OWNER + " Keep the clock on screen.", before, after, miss)
    assert after["visuals"]["camera_zoom"] is None and after["visuals"]["hud_timer"] is True  # 1.1 measured covered: to 1
    assert "lowered from 1.1 to 1" in notes[0]


def test_the_guided_record_keeps_its_review_and_the_loops_verdict(tmp_path, monkeypatch):
    """The owner's v1 had review.json but no review in version.json: studio.make wrote the record before the review and
    the guided workflow never wrote it again. The review (or its error) and the loop's verdict are saved with it; a
    revised version keeps how it was made."""
    from cbj import studio
    from cbj.workflows import guided
    monkeypatch.setattr(studio, "STUDIO", tmp_path)
    vdir = tmp_path / "c1" / "v1"
    vdir.mkdir(parents=True)
    v = {"id": "c1", "n": 1, "brief": {}, "review": {"error": "the vision model timed out"}}
    (vdir / "version.json").write_text(json.dumps({"id": "c1", "n": 1}))
    guided.save_record(v)
    assert json.loads((vdir / "version.json").read_text())["review"] == {"error": "the vision model timed out"}
    v2dir = tmp_path / "c1" / "v2"
    v2dir.mkdir()
    (v2dir / "version.json").write_text(json.dumps({"id": "c1", "n": 2, "revision": {"status": "made", "of": 1}}))
    guided.save_record({"id": "c1", "n": 2, "revision": {"status": "unchanged", "feedback": "x"}})
    rec = json.loads((v2dir / "version.json").read_text())
    assert rec["revision"] == {"status": "made", "of": 1} and rec["loop"]["status"] == "unchanged"


def test_the_screen_row_accepts_a_hud_hidden_for_the_board(tmp_path):
    """The HUD hidden by videoref.hud_clear (the owner's zoom over a 4x9 board) is not a miss of "Reference: the screen"
    (the reference shows the HUD): the request's zoom wins, and the HUD-over-board row measures it."""
    b = _owner_brief()
    a = _owner_reading()
    V.apply(b, OWNER, [a])
    b["planner"] = {"references": [a]}
    a["focus"] = ["pacing", "screen"]
    row = audit.screen_row(OWNER, b, a, a["notes"], ["pacing", "screen"])
    assert row["status"] == "info" and "the ad hides it so the board's top row is clear of it" in row["detail"]
    b["reference"]["hud_clear"]["action"] = "capped the zoom at 1"
    b["visuals"].update(hud_level=False, hud_timer=False)
    assert audit.screen_row(OWNER, b, a, a["notes"], ["pacing", "screen"])["status"] == "failed"


def test_fewer_moves_with_no_planner_number_come_from_the_reading():
    """Round 4, case 28: the planner gave no number for "fewer moves" (its text differs run to run), the levers had
    nothing to keep and the fill played 10 drags on an 8x9 board. The count comes from the reading: about 70% of the
    reference's counted moves (9 here: 3 a third), a cliffhanger's board holding the moves minus its cut's blocks."""
    b = _owner_brief()
    b["level"]["moves"] = None
    prov = V.apply(b, OWNER, [_owner_reading()])[0]
    assert b["level"]["moves"] == 6 and b["level"]["blocks"] == 4 and prov["play"]["moves"] == 6
    assert prov["moves_asked"].startswith('"fewer moves": 6 moves, about 70% of 9, at least 4; the reference\'s 9 moves '
                                          'counted over its gameplay; 4 blocks (the cliffhanger\'s cut leaves 2)')
    line = next(x for x in prov["adapted"] if x.startswith("the play fills about"))
    assert "the request asks for fewer moves: 6 kept" in line and "the moves: \"fewer moves\": 6 moves, about 70% of 9" in line
    assert prov["play"]["blocks"] == 4  # never raised to supply the fill
    # "a few moves": 4-5
    b = _owner_brief()
    b["level"]["moves"] = None
    V.apply(b, OWNER.replace("fewer moves", "a few moves"), [_owner_reading()])
    assert b["level"]["moves"] in (4, 5)
    # "more moves": about 130%, at most the generator's 14
    assert V.relative_count("more moves", {"pacing": {"moves_by_third": [4, 4, 4]}}, {})[0] == 14
    # no usable count: the tempo class, estimated
    n, why = V.relative_count("fewer moves", {"pacing": {"tempo": "fast"}}, {})
    assert n == 8 and "estimated from its fast tempo" in why
    # a planner's own number stays
    b = _owner_brief()
    V.apply(b, OWNER, [_owner_reading()])
    assert b["level"]["moves"] == 6 and b["level"]["blocks"] is None
    # the image and text paths: the relative words state nothing there
    assert "moves" not in V.stated(OWNER) and "moves" not in V.stated(OWNER.replace("fewer", "a few"))


# ---------- round 4 (2026-10-17): the play for every guided creative; a win the request implies, with its replay ----------

CASE29 = ("Keep this video's framing and colours; change the level to a narrow-centre board and make it a 40-second "
          "clean win.")
CASE30 = "An ad like this one, but end with a replay of the winning move and a 'Can you do it faster?' card."
CUT = {"ending": "cliffhanger", "last_clock": None, "win_screen": False, "out_of_time_screen": False,
       "question_caption": "", "blocks_left": 8}


def test_every_guided_creative_gets_the_play_decision():
    """Round 4, case 29: a screen, look and colours read made no play decision; the 40 s clean win played 20.6 s and studio
    filled it with an 11 s slow replay. With no pace taken, the play seconds for the brief's length are filled with
    moves (the blocks follow), mode "fill", one play line; a replay neither the request nor the reference has stays off."""
    b = _fresh()
    b["gameplay"].update(ending="win", mistakes=0)
    b["pacing"]["length_s"] = 40.0
    b["level"]["shape"] = "narrow_center"
    a = _close_up(hud={"level": "LEVEL 25", "clock": "01:05"},
                  structure=[{"from_s": 0.0, "to_s": 30.1, "purpose": "gameplay", "what": "Player slides blocks."}])
    a["focus"] = ["screen", "look", "board_colours"]
    a["facts"] = {"duration_s": 30.1}
    prov = V.apply(b, CASE29, [a])[0]
    rec = prov["play"]
    assert rec["mode"] == "fill" and 30.0 <= rec["target_s"] <= 32.0 and b["sequence"]["replay"] is False
    assert b["level"]["moves"] == rec["moves"] and rec["moves"] >= 10 and rec["expected_s"] >= rec["target_s"] - 1.5
    assert b["level"]["shape"] == "narrow_center" and b["pacing"]["length_s"] == 40.0  # the request's own
    line = next(x for x in prov["adapted"] if x.startswith("the play fills about"))
    assert "no replay (the request and the reference have none, and the play fills the ad)" in line
    # a small board the request states keeps its size, and the play line says the cap
    b = _fresh()
    b["gameplay"].update(ending="win", mistakes=0)
    b["level"].update(width=5, height=5)
    prov = V.apply(b, "A version of this video on a 5x5 board, 30 seconds, a clean win.", [_analysis(["hook"])])[0]
    assert (b["level"]["width"], b["level"]["height"]) == (5, 5) and "size" in prov["stated"]
    assert prov["play"]["cap"] is None  # 30 s: the small board fills with studio's long looks
    b = _fresh()
    b["gameplay"].update(ending="win", mistakes=0)
    b["level"].update(width=5, height=5)
    prov = V.apply(b, "A version of this video on a 5x5 board, 45 seconds, a clean win.", [_analysis(["hook"])])[0]
    assert (b["level"]["width"], b["level"]["height"]) == (5, 5)
    assert "the request's own 5x5 board holds at most" in prov["play"]["cap"]
    assert any("it stops there: the request's own 5x5 board" in x for x in prov["adapted"])
    # the game's own level, or a plan that takes nothing: no play decision
    b = _fresh()
    V.apply(b, "A version of this video on the game's own level 3.", [_analysis(["concept"])])
    assert "play" not in b["reference"] or b["reference"]["play"]["mode"] != "fill"


def test_a_win_the_request_implies_and_its_replay_are_its_own():
    """Round 4, case 30: the planner set a win ("Because you asked for a replay of the winning move, this ad ends with a
    full win instead"); the reference's cut with 3 blocks left replaced it, the ad had no win and no replay, and the
    revision pinned the cut. The words that imply a win and an asked replay are the request's own ending."""
    for words in ("a replay of the winning move", "after the win", "once it's solved", "the level completed screen"):
        assert "ending" in V.stated(f"Show {words}.", video=True)
    assert "ending" not in V.stated("Show a replay of the winning move.")  # the text and image paths: as before
    notes = {**copy.deepcopy(NOTES), "ending_read": dict(CUT)}
    b = _fresh()
    b["gameplay"]["ending"] = "win"
    b["assumptions"].append("The reference stops with blocks still on the board. Because you asked for a replay of the "
                            "winning move, this ad ends with a full win instead.")
    b["concept"]["result"] = "Can you do it faster?"
    prov = V.apply(b, CASE30, [_analysis(["concept"], notes)])[0]
    gp = b["gameplay"]
    assert (gp["ending"], gp["blocks_left"], b["sequence"]["replay"]) == ("win", None, True)
    assert {"ending", "replay"} <= set(prov["stated"])
    assert any(x.startswith("the reference's ") and x.endswith("ending is read, not applied (the request sets its own ending)")
               for x in b["assumptions"])
    V.fit_captions(b, CASE30, chain=True)
    assert b["concept"]["end_title"] == "Can you do it faster?" and b["concept"]["result"] is None
    # "replay the best move" on a Color Block Jam trailer that stops mid-level: a replay needs an ending that has one
    b = _fresh()
    b["gameplay"]["ending"] = "cliffhanger"
    cbj = {**copy.deepcopy(NOTES), "ending_read": dict(CUT), "game_or_product": "Color Block Jam"}
    V.apply(b, "Make an ad like this trailer and replay the best move.", [_analysis(["concept"], cbj)])
    assert (b["gameplay"]["ending"], b["sequence"]["replay"]) == ("win", True)
    assert any(x.startswith("the request asks for a replay, and a cliffhanger has none") for x in b["assumptions"])
    # the image path reads the words as before
    assert "ending" not in V.stated(CASE30) or V.ENDING_STATED.search(CASE30)


def test_a_revision_fixes_an_asked_replay_miss():
    from cbj.workflows import guided
    b = _fresh()
    b["gameplay"].update(ending="cliffhanger", blocks_left=3)
    b["sequence"]["replay"] = False
    notes = guided.replay_fix(CASE30, b, [{"check": "Asked: the replay", "status": "failed", "from": "prompt"}])
    assert (b["gameplay"]["ending"], b["gameplay"]["blocks_left"], b["sequence"]["replay"]) == ("win", None, True)
    assert {"gameplay.ending", "gameplay.blocks_left", "sequence"} <= set(b["changed"]) and len(notes) == 2
    assert "Asked: the replay" in guided.PINNED["gameplay.blocks_left"] and "Asked: the replay" in guided.PINNED["gameplay.ending"]
    assert guided.replay_fix(CASE30, b, []) == []


def test_the_requests_own_moves_keep_the_references_tempo_with_no_added_hesitation():
    """Round 4 rerun, case 28: the pace taken (normal, 0.31 drags a second) and "fewer moves" (6): the levers chose a calm
    tempo and a hesitation, the gaps grew from 0.60 s to 1.60 s and the even pacing failed. With the request's own moves
    the play cannot fill: the reference's tempo class, no added hesitation, a shorter play, said."""
    b = _owner_brief()
    a = _owner_reading()
    a["pacing"]["dps"] = 0.31
    prov = V.apply(b, OWNER, [a])[0]
    rec = prov["play"]
    assert (b["pacing"]["tempo"], b["gameplay"]["hesitations"], b["level"]["moves"]) == ("normal", 0, 6)
    assert (rec["tempo"], rec["hesitations"], rec.get("own_moves")) == ("normal", 0, True)
    line = next(x for x in prov["adapted"] if x.startswith("the play fills about"))
    assert "the request's own moves keep the reference's normal tempo with no added hesitation" in line
    # without the request's moves the fill may still stretch (calm, hesitations): the levers choose as before
    b = _fresh()
    b["gameplay"].update(ending="win", mistakes=0)
    b["level"]["difficulty"] = "easy"
    prov = V.apply(b, CASE07, [_pacing_reading()])[0]
    assert not prov["play"].get("own_moves")


def test_the_end_card_never_shows_the_asked_line_twice():
    """Round 4 rerun, case 30: the planner put "Can you do it faster?" on the end card's title and its fact line."""
    b = _fresh()
    b["gameplay"]["ending"] = "win"
    b["concept"].update(end_title="Can you do it faster?", end_fact="Can you do it faster?", result="Solved in {time_used_phrase}")
    notes = V.fit_captions(b, CASE30, chain=True)
    cc = b["concept"]
    assert cc["end_title"] == "Can you do it faster?" and cc["end_fact"] != cc["end_title"]
    assert cc["end_fact"] == "Cleared in {time_used_phrase}" and "concept.end_fact" in b["changed"]
    assert cc["result"] == "Solved in {time_used_phrase}"  # a different line stays
    assert any(n.startswith("the end card's second line is") for n in notes)
    # no fact of the planner's on a win: ad.py's quick-solve fact would repeat the line, so the result's own is set
    b = _fresh()
    b["gameplay"]["ending"] = "win"
    V.fit_captions(b, CASE30, chain=True)
    assert b["concept"]["end_fact"] == "Cleared in {time_used_phrase}"
    # the planner's own different fact stays
    b = _fresh()
    b["gameplay"]["ending"] = "win"
    b["concept"].update(end_fact="Solved with a single replay!", cta="Can you do it faster?")
    V.fit_captions(b, CASE30, chain=True)
    assert b["concept"]["end_fact"] == "Solved with a single replay!" and b["concept"]["cta"] is None
