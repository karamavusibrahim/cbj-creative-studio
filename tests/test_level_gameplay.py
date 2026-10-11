"""Core requirement 2: level structure and looks, the generator's new options, the brief's new
fields and their rules, and the checks read from a recording."""

import copy
import hashlib
import json
import random
from dataclasses import asdict
from pathlib import Path

import pytest

from cbj import brief as B
from cbj.checks import gameplay_checks
from cbj.events import from_brief
from cbj.generate import (PACKED_FILL, PIECE_SETS, PIECES, Spec, _board, _symmetric_mask, candidate, holes_for,
                          looks)
from cbj.level import level_from_dict, load_level, validate
from cbj.play import plan

LEVELS = Path(__file__).resolve().parents[1] / "data" / "levels"
NC = LEVELS / "gen" / "narrow_center_01.json"


# ---------- board shapes ----------

def test_new_shapes():
    cross = holes_for("cross", 7, 7)
    assert (0, 0) in cross and (6, 6) in cross and (3, 0) not in cross and (3, 3) not in cross
    ring = holes_for("ring", 7, 8)
    assert ring == {(x, y) for x in range(2, 5) for y in range(2, 6)}  # a band two cells wide all round
    lanes = holes_for("lanes", 8, 8)
    assert {x for x, _ in lanes} == {2, 5} and {y for _, y in lanes} == set(range(2, 6))  # two open rows each end
    for shape in ("open", "narrow_center", "holes", "cross", "ring", "lanes"):
        assert _symmetric_mask(holes_for(shape, 8, 8), 8), shape
    assert not _symmetric_mask(holes_for("door", 8, 8), 8)  # a door down the middle of an even width
    assert Spec("door", style=["symmetric"], width=8, difficulty="medium").resolved().width == 9


@pytest.mark.parametrize("shape", ["cross", "ring", "lanes"])
def test_new_shape_candidates_are_valid(shape):
    spec = Spec(shape, difficulty="medium").resolved()
    rng = random.Random(5)
    for _ in range(25):
        d = candidate(spec, rng)
        assert not validate(level_from_dict(d, "t"))
        assert {(c["x"], c["y"]) for c in d["inactiveCells"]} == holes_for(shape, spec.width, spec.height)


def test_ring_gates_can_sit_on_the_inner_rim():
    spec = Spec("ring", difficulty="medium").resolved()
    rng = random.Random(0)
    inner = 0
    for _ in range(40):
        b = _board(spec, rng)
        for _, side, cells in b.gates:
            dx, dy = {"left": (-1, 0), "right": (1, 0), "top": (0, 1), "bottom": (0, -1)}[side]
            x, y = cells[0]
            inner += 0 < x + dx < spec.width - 1 and 0 < y + dy < spec.height - 1
    assert inner > 0


# ---------- pieces and looks ----------

@pytest.mark.parametrize("pieces", ["small", "big", "long"])
def test_piece_sets(pieces):
    spec = Spec("open", difficulty="medium", pieces=pieces, width=8, height=8).resolved()
    rng = random.Random(2)
    for _ in range(15):
        b = _board(spec, rng)
        assert b and all(name in PIECE_SETS[pieces] for name, _, _ in b.blocks)
        assert not validate(level_from_dict(b.to_dict(), "t"))


def test_new_pieces_keep_the_pivot_cell():
    # Block.Initialize adds (0, 0) when it is missing, which would change the shape
    for name, offs in PIECES.items():
        assert (0, 0) in offs, name


def test_packed_boards_are_full_and_share_gates():
    spec = Spec("open", difficulty="medium", style=["packed"], width=6, height=6).resolved()
    rng = random.Random(4)
    fills, shared = [], 0
    for _ in range(20):
        b = _board(spec, rng)
        if b is None:
            continue
        lvl = level_from_dict(b.to_dict(), "t")
        assert not validate(lvl)
        fills.append(looks(lvl, spec)["fill"])
        shared += len(lvl.exits) < len(lvl.blocks)
        colours = {bl.color for bl in lvl.blocks}
        assert colours == {e.color for e in lvl.exits}  # every colour has its gate
    assert sum(f >= PACKED_FILL[0] - 0.05 for f in fills) >= 0.8 * len(fills)
    assert shared >= 0.8 * len(fills)


def test_symmetric_boards_mirror_blocks_colours_and_gates():
    spec = Spec("holes", difficulty="medium", style=["symmetric"]).resolved()
    rng = random.Random(1)
    made = 0
    for _ in range(60):
        b = _board(spec, rng)
        if b is None:
            continue
        lvl = level_from_dict(b.to_dict(), "t")
        assert not validate(lvl)
        assert looks(lvl, spec)["symmetry"] == 1.0
        made += 1
    assert made >= 5


def test_colourful_keeps_touching_blocks_apart():
    spec = Spec("open", difficulty="medium", style=["colourful"], blocks=8, width=7, height=7).resolved()
    rng = random.Random(3)
    vals = [looks(level_from_dict(b.to_dict(), "t"), spec)["contrast"] for b in (_board(spec, rng) for _ in range(20)) if b]
    assert sum(vals) / len(vals) >= 0.9


def test_old_specs_keep_their_cache_key():
    """A spec written before pieces, style, events and finish existed hashes as it did then."""
    r = Spec("narrow_center", difficulty="hard", target_drags=8).resolved()
    old = {k: v for k, v in asdict(r).items() if k not in ("pieces", "style", "events", "finish")}
    assert r.key() == hashlib.sha256(json.dumps(old, sort_keys=True).encode()).hexdigest()[:12]
    assert Spec("narrow_center", difficulty="hard", target_drags=8, style=["packed"]).resolved().key() != r.key()


# ---------- the brief ----------

def raw(**parts):
    b = B.default_brief()
    for k, v in parts.items():
        if isinstance(b[k], dict):
            b[k].update(v)
        else:
            b[k] = v
    return b


def test_brief_rules_for_the_new_fields():
    b = B.check(raw(gameplay={"ending": "win", "clock_left_s": 2, "finish": "streak"}))
    assert b["gameplay"]["clock_left_s"] is None and b["gameplay"]["finish"] == "streak"  # 2 s left needs a near-fail
    b = B.check(raw(gameplay={"ending": "near_fail", "clock_left_s": 9}))
    assert b["gameplay"]["clock_left_s"] == 3 and B.control(b, "difficulty_pacing")["status"] == "adjusted"
    b = B.check(raw(gameplay={"ending": "cliffhanger", "finish": "streak",
                              "events": [{"block": {"colour": "Red", "which": "any", "all": False}, "action": "leaves",
                                          "when": "last"}]}))
    assert b["gameplay"]["finish"] == "auto" and b["gameplay"]["events"][0]["when"] == "next"
    ev = {"block": {"colour": "Red", "which": "any", "all": False}, "action": "leaves", "when": "next"}
    b = B.check(raw(gameplay={"events": [ev] * 8 + [{"block": {"colour": "Pink"}, "action": "leaves"}]}))
    assert len(b["gameplay"]["events"]) == B.MAX_EVENTS
    b = B.check(raw(level={"pieces": "huge", "style": ["packed", "sparkly", "packed"]}))
    assert b["level"]["pieces"] == "mixed" and b["level"]["style"] == ["packed"]


@pytest.mark.parametrize("group,prompt,ok", [
    ("gameplay.events", "First move the yellow block out of the way, then the blue one escapes", True),
    ("gameplay.events", "A red and blue level", False),  # colours, but no order
    ("gameplay.finish", "A satisfying solve: one move frees everything", True),
    ("gameplay.finish", "A clean win", False),
    ("gameplay.clock_left", "wins with 2 seconds left", True),
    ("gameplay.clock_left", "a near-fail", False),
    ("level.style", "a symmetric, colourful board", True),
    ("level.style", "a hard level", False),
    ("level.pieces", "chunky blocks", True),
    ("pacing.curve", "start slow and speed up until the end", True),
    ("pacing.curve", "a fast solve", False),
])
def test_evidence_for_the_new_groups(group, prompt, ok):
    assert (B._evidence(group, prompt, B.default_brief()) is None) == ok


def test_old_briefs_are_completed():
    old = B.default_brief()
    del old["level"]["pieces"], old["gameplay"]["events"], old["pacing"]["curve"]
    b = B._complete(copy.deepcopy(old))
    assert b["level"]["pieces"] == "mixed" and b["gameplay"]["events"] == [] and b["pacing"]["curve"] == "even"
    assert B.changed_controls(b, B.check(B.default_brief())) == []


# ---------- checks, from a recording ----------

def fake_recording(folder: Path, level_path: Path, script, tamper=None) -> Path:
    """A recording as the game would log a perfect run of the script."""
    folder.mkdir(parents=True, exist_ok=True)
    level = load_level(level_path)
    d = script.to_dict(level)
    drags, frame, gone = [], 30, [-1] * len(level.blocks)
    for k, b in enumerate(d["beats"]):
        start, end = frame + b["pause_f"], frame + b["pause_f"] + 10 * max(1, len(b["path"]))
        result = "interrupted" if b["kind"] == "short" else ("exit" if b["exits"] else "placed")
        drags.append({"index": k, "block": b["block"], "start_frame": start, "end_frame": end,
                      "exit_frame": end if b["exits"] else -1, "cells": [{"x": x, "y": y} for x, y in b["path"][1:]],
                      "result": result})
        if b["exits"]:
            gone[b["block"]] = end
        frame = end
    if tamper:
        tamper(drags)
    left = sum(g < 0 for g in gone)
    status = {"win": "cleared", "near_fail": "cleared", "cliffhanger": "unresolved", "time_out": "failed"}[d["ending"]]
    result = {"status": status, "frames": frame + 60, "timer_end": 0.5 + d.get("clock_left", 1) if d["ending"] == "near_fail" else 55.0,
              "drags": drags, "block_gone_frames": gone}
    d["measured"] = {"beat_frames": [[x["start_frame"], x["end_frame"]] for x in drags]}
    (folder / "result.json").write_text(json.dumps(result))
    (folder / "play.json").write_text(json.dumps(d))
    return folder


def ev(colour, action, which="any", all_=False, when="next"):
    return {"block": {"colour": colour, "which": which, "all": all_}, "action": action, "when": when}


def by_name(checks):
    return {c["check"]: c for c in checks}


def test_checks_pass_on_a_faithful_recording(tmp_path):
    level = load_level(NC)
    events = [ev("Red", "moves", when="first"), ev("Blue", "leaves"), ev("Purple", "leaves", when="last")]
    b = B.check(raw(gameplay={"ending": "near_fail", "events": events, "clock_left_s": 2}))
    script = plan(level, "near_fail", events=from_brief(level, events)[0], clock_left=2)
    c = by_name(gameplay_checks(b, fake_recording(tmp_path / "r", NC, script), NC))
    assert c["Planned moves"]["status"] == "pass"
    assert c["Ending"]["status"] == "pass" and "00:02" in c["Ending"]["detail"]
    assert c["Order of interactions"]["status"] == "pass", c["Order of interactions"]
    assert "the red block moves out of the way first: drag 1" in c["Order of interactions"]["detail"]


def test_checks_catch_a_recording_that_breaks_the_order(tmp_path):
    level = load_level(NC)
    events = [ev("Blue", "leaves"), ev("Red", "leaves")]
    b = B.check(raw(gameplay={"ending": "win", "events": events}))
    script = plan(level, "win", events=from_brief(level, events)[0])

    def swap(drags):  # the game moved another block than planned
        drags[0]["block"] = (drags[0]["block"] + 1) % 7
    c = by_name(gameplay_checks(b, fake_recording(tmp_path / "r", NC, script, swap), NC))
    assert c["Planned moves"]["status"] == "failed" and "drag(s) 1" in c["Planned moves"]["detail"]


def test_streak_and_curve_checks(tmp_path):
    level = load_level(NC)
    b = B.check(raw(gameplay={"ending": "win", "finish": "streak"}, pacing={"curve": "speeds_up"}))
    script = plan(level, "win", finish="streak", curve="speeds_up")
    assert any(x.tag == "key" for x in script.beats)
    c = by_name(gameplay_checks(b, fake_recording(tmp_path / "r", NC, script), NC))
    assert c["Satisfying finish"]["status"] == "pass" and "last 7 of 7 blocks" in c["Satisfying finish"]["detail"]
    assert c["Pacing curve"]["status"] == "pass"


def test_stuck_event_is_checked_on_the_mistake(tmp_path):
    level = load_level(NC)
    events = [ev("Red", "stuck", when="first")]
    b = B.check(raw(gameplay={"ending": "near_fail", "events": events}))
    script = plan(level, "near_fail", events=from_brief(level, events)[0])
    assert script.beats[0].kind == "mistake" and level.blocks[script.beats[0].drag.block].color.name == "RED"
    c = by_name(gameplay_checks(b, fake_recording(tmp_path / "r", NC, script), NC))
    assert c["Order of interactions"]["status"] == "pass" and "drag 1" in c["Order of interactions"]["detail"]


# ---------- fixes from the Fable 5.1 check ----------

def test_all_of_a_colour_can_leave_last():
    from cbj.events import Event, check_events, try_solve_events
    from cbj.level import BlockColor
    lvl = load_level(LEVELS / "Level_06.json")
    yellow = frozenset(i for i, b in enumerate(lvl.blocks) if b.color == BlockColor.YELLOW)
    evs = [Event("leaves", yellow, all=True, when="last", text="all yellow last")]
    s = try_solve_events(lvl, evs)
    assert s is not None and {d.block for d in s.drags[-len(yellow):]} == yellow
    assert check_events(lvl, evs, s.drags).ok


def test_an_impossible_order_is_refused_at_once_not_after_a_long_search():
    import time
    from cbj.events import Event, try_solve_events
    lvl = load_level(NC)
    red = frozenset(i for i, b in enumerate(lvl.blocks) if b.color.name == "RED")
    t = time.time()
    assert try_solve_events(lvl, [Event("leaves", red), Event("moves", red)]) is None
    assert time.time() - t < 0.5


def test_time_out_never_cuts_short_a_block_an_event_needs():
    from cbj.events import check_events
    lvl = load_level(NC)
    evs, _ = from_brief(lvl, [ev("Orange", "leaves")])
    s = plan(lvl, "time_out", events=evs)
    assert s.beats[-1].kind == "short" and s.beats[-1].drag.block not in evs[0].blocks
    assert check_events(lvl, evs, s.drags, [b.kind for b in s.beats]).ok
    b = B.check(raw(gameplay={"ending": "time_out", "events": [ev("Purple", "leaves", when="last")]}, channel="social"))
    assert b["gameplay"]["events"][0]["when"] == "next" and "time-out" in B.control(b, "gameplay")["why"]


def test_a_mistake_before_a_first_step_breaks_it():
    from cbj.events import Event, check_events
    lvl = load_level(NC)
    s = plan(lvl, "near_fail", seed=0)
    first_block = s.beats[1].drag.block
    evs = [Event("moves" if not s.beats[1].drag.exits else "leaves", frozenset({first_block}), when="first", text="x")]
    kinds = ["mistake"] + [b.kind for b in s.beats[1:]]
    c = check_events(lvl, evs, s.drags, kinds)
    assert not c.ok and "is a mistake" in c.problem


def test_event_hesitations_and_dropped_stuck_steps_are_counted_right():
    lvl = load_level(NC)
    evs, _ = from_brief(lvl, [ev("Red", "hesitates")])
    s = plan(lvl, "near_fail", events=evs)
    assert sum(b.kind == "hesitate" for b in s.beats) == 2  # the ending's default two, one of them the asked one
    evs, _ = from_brief(lvl, [ev("Yellow", "stuck")])  # yellow is never trapped on this level
    s = plan(lvl, "win", events=evs)
    assert not any("mistake(s)" in n for n in s.notes) and any("never traps" in n for n in s.notes)


def test_checks_stop_on_a_short_recording_and_keep_repeated_steps_apart(tmp_path):
    lvl = load_level(NC)
    events = [ev("Red", "leaves"), ev("Red", "leaves")]  # NC has one red block: the second is refused
    b = B.check(raw(gameplay={"ending": "win"}))
    script = plan(lvl, "win")

    def cut(drags):
        del drags[-1]
    c = gameplay_checks(b, fake_recording(tmp_path / "r", NC, script, cut), NC)
    assert [x["check"] for x in c] == ["Planned moves"] and c[0]["status"] == "failed"


def test_satisfying_finish_check_never_calls_a_mistake_the_key_move(tmp_path):
    lvl = load_level(NC)
    b = B.check(raw(gameplay={"ending": "near_fail", "finish": "streak"}))
    for seed in range(12):
        script = plan(lvl, "near_fail", finish="streak", seed=seed)
        c = by_name(gameplay_checks(b, fake_recording(tmp_path / f"r{seed}", NC, script), NC))["Satisfying finish"]
        assert "mistake" not in c["detail"] or c["status"] == "adjusted"


@pytest.mark.parametrize("group,prompt", [
    ("gameplay.events", "Start with the red block, finish with the blue one"),
    ("gameplay.events", "Save the biggest block for the end"),
    ("gameplay.events", "Begin by moving the yellow block aside so the blue one can leave"),
    ("pacing.curve", "Tension building, against the clock"),
    ("gameplay.finish", "Everything leaves one after another at the end"),
    ("level.difficulty", "A really hard level"),
])
def test_natural_phrasings_count_as_asking(group, prompt):
    assert B._evidence(group, prompt, B.default_brief()) is None


def test_unasked_difficulty_and_length_are_not_taken():
    assert B._evidence("level.difficulty", "Start slow and speed up", B.default_brief())
    assert B._evidence("pacing.length", "A really hard level", B.default_brief())
    assert B._evidence("pacing.length", "Make it 45 seconds", B.default_brief()) is None


def test_colours_named_to_point_at_a_block_are_not_the_only_colours():
    from cbj.generate import board_colours
    stuck_red = [ev("Red", "stuck")]
    cs = board_colours(["Red"], stuck_red, 0)
    assert cs[0] == "Red" and len(cs) == 4
    assert board_colours(["Red"], stuck_red, 0) == cs  # chosen by the seed
    assert board_colours([], stuck_red, 1)[0] == "Red"
    assert board_colours(["Blue", "Red", "Yellow"], [ev("Green", "leaves")], 0) == ["Blue", "Red", "Yellow", "Green"]


# ---------- fixes from the Fable 5.1 confirmation ----------

def test_time_out_with_an_order_keeps_the_order_and_cuts_short_a_block_no_step_names():
    from cbj.events import check_events
    lvl = load_level(NC)
    base = len(plan(lvl, "time_out").beats)
    evs, _ = from_brief(lvl, [ev("Green", "leaves"), ev("Red", "leaves")])
    s = plan(lvl, "time_out", events=evs)
    named = evs[0].blocks | evs[1].blocks
    assert s.beats[-1].kind == "short" and s.beats[-1].drag.block not in named
    assert check_events(lvl, evs, s.drags, [b.kind for b in s.beats]).ok
    assert len(s.beats) <= base + 1  # the order costs at most one drag here (it cost 2-3 before the fix)


def test_a_block_that_cannot_move_gets_no_gate():
    from cbj.generate import _passes, _reach
    active = {(x, y) for x in range(3) for y in range(3)}
    stuck = _reach(active, [(x, y) for x in range(3) for y in range(3)])  # a block filling the board
    assert len(stuck) == 1 and not _passes(stuck, [(0, 0), (1, 0), (2, 0)], "bottom")


def test_colour_by_colour_keeps_exactly_the_named_colours():
    from cbj.generate import board_colours
    order = [ev("Blue", "leaves", all_=True), ev("Red", "leaves", all_=True), ev("Yellow", "leaves", all_=True)]
    assert board_colours(["Blue", "Red", "Yellow"], order, 0) == ["Blue", "Red", "Yellow"]


def test_the_red_block_leaves_last_with_two_red_blocks_is_the_final_exit():
    from cbj.events import try_solve_events
    d = {"gridWidth": 3, "gridHeight": 3, "timerCount": 60, "inactiveCells": [],
         "GridBlockDatas": [{"gridPosition": {"x": 0, "y": 0}, "blockColor": 3, "shapeOffsets": [{"x": 0, "y": 0}]},
                            {"gridPosition": {"x": 2, "y": 0}, "blockColor": 3, "shapeOffsets": [{"x": 0, "y": 0}]},
                            {"gridPosition": {"x": 1, "y": 2}, "blockColor": 2, "shapeOffsets": [{"x": 0, "y": 0}]}],
         "ExitDatas": [{"exitNumber": 0, "requiredColor": 3, "gridPosition": {"x": 0, "y": 0}, "direction": 3,
                        "shapeOffsets": [{"x": 0, "y": 0}]},
                       {"exitNumber": 0, "requiredColor": 3, "gridPosition": {"x": 2, "y": 0}, "direction": 3,
                        "shapeOffsets": [{"x": 0, "y": 0}]},
                       {"exitNumber": 0, "requiredColor": 2, "gridPosition": {"x": 1, "y": 2}, "direction": 2,
                        "shapeOffsets": [{"x": 0, "y": 0}]}]}
    tiny = level_from_dict(d, "tiny")
    evs, _ = from_brief(tiny, [ev("Red", "leaves", when="last")])
    s = try_solve_events(tiny, evs)
    assert s.done_at == [len(s.drags) - 1] and tiny.blocks[s.drags[-1].block].color.name == "RED"


@pytest.mark.parametrize("group,prompt,ok", [
    ("level.difficulty", "Make it intense", True),
    ("level.shape", "A big empty board", True),
    ("level.style", "A gorgeous board", True),
    ("pacing.length", "Keep it snappy, a quick one", True),
    ("pacing.curve", "Make the tempo rise toward the end", True),
    ("pacing.length", "A near-fail with 2 seconds left", False),  # the clock, not the ad's length
])
def test_more_natural_phrasings(group, prompt, ok):
    assert (B._evidence(group, prompt, B.default_brief()) is None) == ok
