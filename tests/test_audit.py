"""The asked-facts audit (audit.py, 2026-10-15): measurable facts read from the prompt itself, judged on
the brief, the level, the recording and the ad; the game's rules replayed on the recording; the
feedback text for the revision round."""
import json
from pathlib import Path

from cbj import audit
from cbj import brief as B

STUDIO = Path(__file__).resolve().parents[1] / "studio"
P1 = ('Create a medium Color Block Jam level with five colored blocks and a narrow central corridor that requires at least '
      'two repositioning moves. Show an experienced player solving the puzzle efficiently without mistakes, first moving a '
      'blocking piece aside, then clearing the available blocks one after another. Add the opening caption "Perfect Solve!" '
      'and make it a 30-second portrait creative.')
P2 = ("Create a nearly symmetrical Color Block Jam level with a narrow shared corridor, several small red, blue and green "
      "blocks, and one larger yellow block near the center. Hard difficulty and a 40-second portrait creative.")
P3 = ('Create a difficult Color Block Jam level with six colored blocks, a narrow central passage and limited space for '
      'repositioning. Show the player first attempting to slide the blue block toward its matching door, but its movement '
      'stops because a red block blocks the route. Finish with a quick sequence of successful exits and approximately three '
      'seconds remaining on the timer. A 45-second portrait creative with the caption "Wrong block first?".')


def test_asked_facts_are_read_from_the_prompt():
    a = audit.asked(P1)
    assert (a["blocks"], a["colours"], a["difficulty"], a["length_s"]) == (5, 5, "medium", 30.0)
    assert a["mistakes"] == 0 and a["captions"] == ["Perfect Solve!"] and a["shape"] == "narrow_center" and a["ending"] == "win"
    a = audit.asked(P2)
    assert a["colour_names"] == ["Red", "Blue", "Green"] and a["style"] == ["symmetric"] and a["difficulty"] == "hard"
    assert a["blocks"] is None and a["colours"] is None
    a = audit.asked(P3)
    assert (a["blocks"], a["colours"], a["clock_left_s"], a["mistakes"]) == (6, 6, 3, 1)
    assert a["stuck_by"] == ("Blue", "Red") and a["style"] == ["packed"] and a["ending"] == "near_fail" and a["satisfying"]
    assert audit.asked("Create a Color Block Jam level with four blocks.")["colours"] is None
    assert audit.asked("A calm 35-second ad with 2 seconds left on the clock.")["clock_left_s"] == 2


def test_level_rows_judge_the_board_not_the_plan():
    """A six-block, six-colour board meets P3's count and colours; a symmetric board that lost its
    yellow and merged two reds fails the named-colour and the visible-piece rows."""
    lvl = {"gridWidth": 6, "gridHeight": 6, "timerCount": 60, "inactiveCells": [],
           "GridBlockDatas": [{"gridPosition": {"x": x, "y": 2}, "blockColor": c, "shapeOffsets": [{"x": 0, "y": 0}]}
                              for x, c in zip(range(6), (0, 1, 2, 3, 4, 5))],
           "ExitDatas": [{"exitNumber": 0, "requiredColor": c, "gridPosition": {"x": x, "y": 0}, "direction": 3,
                          "shapeOffsets": [{"x": 0, "y": 0}]} for x, c in zip(range(6), (0, 1, 2, 3, 4, 5))]}
    path = STUDIO / "levels" / "_audit_test.json"
    path.write_text(json.dumps(lvl))
    try:
        b = B.check(B.default_brief()); b["level"].update(blocks=6, colours=[], difficulty="hard", shape="narrow_center")
        rows = {r["check"]: r for r in audit.level_rows(P3, b, path)}
        assert rows["Asked: block count"]["status"] == "pass" and rows["Asked: colours"]["status"] == "pass"
        assert rows["Asked: blocks a viewer can count"]["status"] == "pass"
        assert rows["Asked: the blocked attempt"]["status"] == "failed" and rows["Asked: the blocked attempt"]["where"] == "plan"
        lvl["GridBlockDatas"][4]["blockColor"] = 3  # two reds side by side: one piece to a viewer
        path.write_text(json.dumps(lvl))
        b2 = B.check(B.default_brief()); b2["level"].update(colours=["Red", "Blue", "Green", "Yellow"], style=["symmetric"], difficulty="hard")
        rows = {r["check"]: r for r in audit.level_rows(P2, b2, path)}
        # red, blue, green and yellow are there, but so are orange and purple: a palette is exclusive (2026-10-15)
        assert rows["Asked: named colours"]["status"] == "failed" and "purple (not asked)" in rows["Asked: named colours"]["detail"]
        lvl["GridBlockDatas"][5]["blockColor"] = 2  # the purple block in blue: only the named colours now
        path.write_text(json.dumps(lvl))
        rows = {r["check"]: r for r in audit.level_rows(P2, b2, path)}
        assert rows["Asked: named colours"]["status"] == "pass"
        assert rows["Asked: blocks a viewer can count"]["status"] == "failed"
        assert audit.level_misses(P2, b2, path)
    finally:
        path.unlink(missing_ok=True)


def test_rules_replay_on_a_recording():
    rec = sorted(p for p in (STUDIO / "recordings").glob("*/result.json"))
    if not rec:
        return
    rec_dir = rec[-1].parent
    level = rec_dir / "level.json"
    if not level.is_file():
        return
    rows = {r["check"]: r for r in audit.rules_rows(level, rec_dir)}
    assert set(rows) == {"Rules: the level", "Rules: doors and colours", "Rules: the moves", "Rules: the clock", "Rules: doors used",
                         "Rules: the result"}
    assert all(r["status"] == "pass" for r in rows.values() if r["check"] != "Rules: doors used"), rows
    assert rows["Rules: doors used"]["status"] == "info"


def test_feedback_names_the_misses():
    checks = [{"check": "Asked: colours", "status": "failed", "detail": "6 asked, 4 shown", "from": "prompt", "where": "plan"},
              {"check": "Difficulty", "status": "pass", "detail": "", "from": "level"}]
    text = audit.feedback(P3, checks, {"match": [{"control": "gameplay", "verdict": "no", "seen": "no red blocker"}], "fixes": ["make red block blue"]})
    assert "colours: 6 asked, 4 shown" in text and "suggested fix: make red block blue" in text and P3[:40] in text
    assert audit.feedback(P3, [{"check": "Asked: colours", "status": "pass", "detail": "", "from": "prompt"}], None) is None
    assert audit.misses(checks) == checks[:1]


def test_a_video_references_segments_get_a_purpose():
    """The reference's structure is kept as {from_s, to_s, purpose, what} with purposes from a fixed
    list, clamped to the clip and in order (brief p.6: the structure and pacing to adapt; 2026-10-15)."""
    from cbj.reference import structure, structure_text
    raw = [{"from_s": 3, "to_s": 29, "what": "sliding blocks", "purpose": "gameplay"},
           {"from_s": 0, "to_s": 3, "what": "big text", "purpose": "Hook"},
           {"from_s": 29, "to_s": 36, "what": "clock in red", "purpose": "near-fail"},
           {"from_s": 36, "to_s": 60, "what": "win screen", "purpose": "win"},
           {"from_s": "x", "to_s": 2}, "junk", {"from_s": 5, "to_s": 5}]
    segs = structure(raw, duration_s=40)
    assert [s["purpose"] for s in segs] == ["hook", "gameplay", "near_fail", "victory"]
    assert segs[-1]["to_s"] == 40 and segs[0]["from_s"] == 0
    assert structure_text(segs).startswith("0-3 s hook (big text); 3-29 s gameplay")
    assert structure(None) == [] and structure([{"from_s": 0, "to_s": 4, "purpose": "something else"}])[0]["purpose"] == "other"
