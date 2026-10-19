"""The seven fixes from the 48-prompt audit of 2026-10-15 (t2c-audit-2026-10-15/AUDIT-REPORT.md):
the audit's count regexes, captions on moments the ad has, several separate walls, one-colour
blocks kept apart, a short solve breathing, the blocking move, and one block per named colour."""
import json
import random

import pytest

from cbj import audit
from cbj import brief as B
from cbj.ad import Recording, build_ad
from cbj.events import Event, describe, from_brief
from cbj.generate import GATES_VERSION, Spec, _board, _symmetric_mask, _touching, holes_for
from cbj.level import level_from_dict
from cbj.play import blocking_moves, plan
from cbj.rules import initial_state

from test_ad import LENGTH, make_recording


# ---- 1. the audit reads counts of what is left as no block count, and mistake words as a count

@pytest.mark.parametrize("prompt, blocks, mistakes", [
    ("Show a tense gameplay sequence where the timer runs low while three blocks remain, then quick moves.", None, None),
    ("Near the end, leave one green block close to its matching exit door, but let the timer reach zero.", None, None),
    ("where one red block is trapped near the center by the surrounding colored blocks", None, None),
    ("the clock runs out with two blocks left.", None, None),
    ("Create a medium level with five colored blocks and two open areas.", 5, None),
    ("A 7x7 open board with eight blocks of mixed shapes in four colours.", 8, None),
    ("The player makes two wrong moves, gets stuck, then solves it with one second left.", None, 2),
    ("Create a difficult level with a narrow center section and show gameplay where the player almost fails before solving it.", None, None),
    ("Show the player making one unhelpful repositioning move before clearing the green block.", None, 1),
    ("Show the player initially moving the green block into an unhelpful position, briefly blocking the blue block's route.", None, 1),
    ("A clean solve with no mistakes on a packed board.", None, 0),
    # the bare phrase (the second alternative of _N_MISTAKES, its number in group 4) once crashed the audit
    ("Same ad, but add two mistakes before the solve.", None, 2),
    ("The player makes three mistakes, then clears the board with one second left.", None, 3),
    ("Revise this version; what it missed: I can't see the two mistakes.", None, 2),
])
def test_asked_counts(prompt, blocks, mistakes):
    a = audit.asked(prompt)
    assert a["blocks"] == blocks and a["mistakes"] == mistakes


def test_asked_blocking_move():
    a = audit.asked("Arrange the puzzle so an obvious early move sends the yellow block into a position that blocks the green block's route.")
    assert a["blocks_by"] == ("Yellow", "Green") and a["mistakes"] == 1
    a = audit.asked("Show the player moving a blue block into an unhelpful empty space, which temporarily prevents another block from reaching its exit.")
    assert a["blocks_by"] == ("Blue", None)
    assert audit.asked("the blue block stops because a red block blocks the route")["blocks_by"] is None


# ---- 3. several separate walls, symmetric on every board

def _groups(cells):
    cells, seen, n = set(cells), set(), 0
    for c in cells:
        if c in seen:
            continue
        n += 1
        stack = [c]
        while stack:
            x, y = stack.pop()
            if (x, y) in seen:
                continue
            seen.add((x, y))
            stack += [q for q in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)) if q in cells]
    return n


@pytest.mark.parametrize("w, h", [(5, 5), (5, 6), (6, 6), (6, 7), (7, 7), (7, 8), (8, 9)])
def test_holes_are_several_separate_walls(w, h):
    hs = holes_for("holes", w, h)
    assert _groups(hs) >= 3 and _symmetric_mask(hs, w)
    assert all(0 < x < w - 1 and 0 < y < h - 1 for x, y in hs)  # inside the board, never on its rim
    assert GATES_VERSION == "v9"


# ---- 4. one-colour blocks never touch on a symmetric board (mirror pairs coloured apart)

def test_symmetric_pairs_of_one_colour_never_touch():
    spec = Spec("narrow_center", 6, 8, 8, ["Red", "Blue", "Green", "Yellow"], "medium", style=["symmetric"]).resolved()
    boards = [b for b in (_board(spec, random.Random(s)) for s in range(60)) if b is not None]
    assert boards
    for b in boards:
        same = [(i, j) for i, j in _touching(b, corners=True) if b.blocks[i][2] == b.blocks[j][2]]
        assert not same, (same, b.blocks)


# ---- 2. an asked caption goes on the nearest moment the ad has

def test_result_and_fix_captions_find_a_moment(tmp_path):
    rec = Recording.load(make_recording(tmp_path / "rec", ending="win"))  # a clean win draws no result caption of its own
    ad = build_ad(rec, LENGTH, options={"texts": {"result": "Too easy!", "fix": "Found it!", "cascade": "Go go go"}})
    assert ad["layers"]["cap_result"]["text"] == "Too easy!" and ad["layers"]["cap_result"]["start"]["seg"] == "result"
    notes = [n["text"] for n in ad["brief_notes"]]
    assert any("result caption goes on the game's result screen" in n for n in notes)
    # the fix caption is given the move after the mistake; on this 6 s recording the band then has no room
    # for it next to the mistake caption, and the note says so (a longer play keeps it)
    assert any("fix caption goes on the move right after the mistake" in n for n in notes) or "cap_fix" in ad["layers"]
    assert "cap_fix" in ad["layers"] or any("cap_fix left out" in n for n in notes)


# ---- 6. the blocking move: an event, a planned mistake, its words

def test_blocking_move_is_an_event_and_a_planned_mistake():
    raw = {"block": {"colour": "Yellow", "which": "any", "all": False}, "action": "blocks", "when": "first", "by": "Green"}
    assert describe(raw) == "the yellow block is moved into the green block's way first"
    b = B.check({**B.default_brief(), "gameplay": {**B.default_brief()["gameplay"], "events": [raw]}})
    assert b["gameplay"]["events"][0]["action"] == "blocks" and b["gameplay"]["events"][0]["by"] == "Green"
    spec = Spec("holes", 6, 7, 6, ["Red", "Blue", "Green", "Yellow"], "medium").resolved()
    found = None
    for seed in range(40):
        board = _board(spec, random.Random(seed))
        if board is None:
            continue
        lv = level_from_dict(board.to_dict())
        opts = blocking_moves(lv, initial_state(lv), frozenset(range(len(lv.blocks))))
        if opts:
            found = (lv, opts)
            break
    assert found, "no random board offered a blocking move"
    lv, opts = found
    mover = opts[0].drag.block
    evs, notes = from_brief(lv, [{"block": {"colour": None, "which": "any", "all": False}, "action": "blocks", "when": "first"}])
    sc = plan(lv, "win", events=[Event("blocks", frozenset({mover}), when="first", text="the block is moved into another block's way")])
    assert sc.beats[0].kind == "mistake" and "'s way" in sc.beats[0].note
    assert sum(b.kind == "mistake" for b in sc.beats) == 1  # the blocking move is the mistake, not one more


# ---- 7. one block per named colour when every named colour is pointed at

def test_one_block_per_named_colour(tmp_path, monkeypatch):
    from cbj import generate as G
    seen = {}

    def fake_generate(spec, log=None):
        seen["spec"] = spec
        raise RuntimeError("stop")
    monkeypatch.setattr(G, "generate", fake_generate)
    b = B.check(B.default_brief())
    b["pacing"]["length_s"] = 40.0
    b["level"].update(colours=["Red", "Blue", "Green", "Yellow"], difficulty="medium")
    b["gameplay"]["events"] = [{"block": {"colour": "Green", "which": "any", "all": False}, "action": "stuck", "when": "first", "by": "Yellow"},
                               {"block": {"colour": "Yellow", "which": "any", "all": False}, "action": "leaves", "when": "next"},
                               {"block": {"colour": "Red", "which": "any", "all": False}, "action": "moves", "when": "next"},
                               {"block": {"colour": "Blue", "which": "any", "all": False}, "action": "leaves", "when": "next"}]
    b["gameplay"]["ending"] = "win"
    with pytest.raises(RuntimeError):
        G.generate_for_brief(b, tmp_path, lambda *a: None)
    assert seen["spec"].blocks == 4 and set(seen["spec"].colours) == {"Red", "Blue", "Green", "Yellow"}
    assert any("pointed at as one block" in n for row in b["controls"] for n in row.get("engine", []))
    # one colour named in the plural ("the remaining blue blocks"): that colour gets two or three blocks
    b2 = B.check(B.default_brief())
    b2["pacing"]["length_s"] = 50.0
    b2["level"].update(colours=["Red", "Blue", "Green", "Yellow"], difficulty="medium")
    b2["gameplay"]["events"] = [e for e in b["gameplay"]["events"] if e["block"]["colour"] != "Blue"]
    with pytest.raises(RuntimeError):
        G.generate_for_brief(b2, tmp_path, lambda *a: None)
    assert seen["spec"].blocks == 6


# ---- F3, F5 (the owner, 2026-10-17): "almost runs out of time" and "the last three blocks" read right ----

@pytest.mark.parametrize("prompt, ending", [
    ("The player almost runs out of time before clearing it.", "near_fail"),
    ("Make a 40-second ad; the player nearly runs out of time but clears it.", "near_fail"),
    ("A hard level where the clock runs out with one block still on the board.", "time_out"),
    ("The player runs out of time.", "time_out"),
])
def test_almost_running_out_of_time_is_a_near_fail(prompt, ending):
    assert audit.asked(prompt)["ending"] == ending


def test_the_last_three_blocks_are_blocks_left_not_the_count():
    a = audit.asked("Make a level with the same number of blocks as this board and stop the ad before the last three "
                    "blocks leave, asking the viewer what to move next. 40 seconds.")
    assert a["blocks"] is None and a["blocks_left"] == 3
    a = audit.asked("A level with 3 blocks.")
    assert a["blocks"] == 3 and a["blocks_left"] is None
    assert audit.asked("End the cliffhanger with two blocks left.")["blocks_left"] == 2


def test_blocks_left_at_the_cut_is_measured_on_the_recording(tmp_path):
    import json
    from cbj import brief as B
    b = B.check(B.default_brief())
    b["gameplay"]["ending"], b["gameplay"]["blocks_left"] = "cliffhanger", 3
    rec = tmp_path / "rec"
    rec.mkdir()
    (rec / "result.json").write_text(json.dumps({"block_gone_frames": [-1, -1, -1, 40]}))
    vdir = tmp_path / "v"
    (vdir / "ad").mkdir(parents=True)
    prompt = "Stop the ad before the last three blocks leave."
    rows = audit._ad_rows_more(audit.asked(prompt), b, {}, vdir, rec)
    row = next(r for r in rows if r["check"] == "Asked: blocks left at the cut")
    assert row["status"] == "pass" and "stops with 3" in row["detail"]
    (rec / "result.json").write_text(json.dumps({"block_gone_frames": [-1, -1, 30, 40]}))
    row = next(r for r in audit._ad_rows_more(audit.asked(prompt), b, {}, vdir, rec) if r["check"] == "Asked: blocks left at the cut")
    assert row["status"] == "failed"
