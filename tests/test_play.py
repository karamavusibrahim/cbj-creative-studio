"""Scenario scripts (play.py): plans, mistakes, pacing and the pause-only fit. These tests do
not start Unity; tests/test_unity_render.py records each ending (opt-in)."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from cbj import cli, render
from cbj.difficulty import rate
from cbj.level import load_level
from cbj.play import (CALM_MARGIN_S, CASCADE_DRAGS, CLIFF_LEFT_S, DRY_TIMER_S, ENDINGS, FPS, MIN_PAUSE_F,
                      NEAR_FAIL_LEFT_S, NEAR_FAIL_MARGIN_S, NEAR_FAIL_RANGE_S, PAUSES, PlayScript, _can_exit_now,
                      blocked_attempts, bumps, check_ending, fit_clock, fit_length, length_range, mistake_options, plan, predict,
                      spread, time_out_allowed, TIME_OUT_TOUCH_F)
from cbj.rules import initial_state, occupancy
from cbj.solver import apply_drag, drag_outcomes, replay, solve_fast

PROJ = Path(__file__).parent.parent
NARROW = PROJ / "data/levels/gen/narrow_center_01.json"
SPEEDS = {4, 5, 6, 8}  # frames per cell: 7.5, 6, 5, 3.75 cells per second


@pytest.fixture(scope="module")
def narrow():
    return load_level(NARROW)


@pytest.fixture(scope="module")
def plans(narrow):
    return {e: plan(narrow, e) for e in ENDINGS}


def left_after(level, script):
    return sum(p is not None for p in replay(level, script.drags))


# ---------- plans ----------

@pytest.mark.parametrize("ending", ENDINGS)
def test_the_same_seed_gives_the_same_plan(narrow, plans, ending):
    assert plan(narrow, ending).to_dict(narrow) == plans[ending].to_dict(narrow)


@pytest.mark.parametrize("ending,left", [("win", 0), ("near_fail", 0), ("cliffhanger", 2), ("time_out", 1)])
def test_every_plan_is_legal_and_ends_with_the_right_blocks_left(narrow, plans, ending, left):
    assert plans[ending].left == left
    assert left_after(narrow, plans[ending]) == left


def test_the_pause_table_is_human():
    for name, (lo, base, hi) in PAUSES.items():
        assert lo <= base <= hi
        if name != "start":
            assert lo >= MIN_PAUSE_F and hi <= (84 if name == "calm" else 75)  # nothing longer than 2.5 s, 2.8 s at a calm tempo
    assert PAUSES["start"] == (0, 0, 0)


@pytest.mark.parametrize("seed", range(6))
@pytest.mark.parametrize("ending", ENDINGS)
def test_pacing_uses_exact_speeds_and_pauses_inside_their_ranges(narrow, ending, seed):
    script = plan(narrow, ending, seed=seed)
    for i, b in enumerate(script.beats):
        lo, _, hi = PAUSES[b.pause]
        assert lo <= b.pause_f <= hi
        assert (b.pause_f >= MIN_PAUSE_F) if i else (b.pause_f == 0)
        assert b.frames_per_cell in SPEEDS
        if b.kind not in ("hesitate", "short"):
            assert 3 <= b.pickup_f <= 5  # 0.10-0.17 s
        # What the runner gets turns back into exactly these frames.
        dp = b.pacing()
        assert round(FPS / dp.cells_per_s) == b.frames_per_cell
        assert round(dp.pause_before_s * FPS) == b.pause_f and round(dp.pickup_s * FPS) == b.pickup_f


def test_the_seed_only_chooses_mistakes_and_hesitations(narrow):
    plans_by_seed = [plan(narrow, "near_fail", seed=s) for s in range(8)]
    for p in plans_by_seed:
        for b in p.beats:
            assert b.frames_per_cell in SPEEDS
    # Different seeds may pick different mistakes, but the planned ending is the same.
    assert {p.left for p in plans_by_seed} == {0}
    assert len({tuple((b.kind, b.drag) for b in p.beats) for p in plans_by_seed}) >= 2


# ---------- mistakes ----------

def test_mistake_census_on_the_narrow_level(narrow):
    state = apply_drag(initial_state(narrow), solve_fast(narrow).drags[0])  # after the first exit
    base = solve_fast(narrow, start=state).min_drags
    options = mistake_options(narrow, state)
    assert len(options) >= 5
    assert options[0].kind == "blocked"  # "I can't reach <colour>" comes first
    for m in options:
        assert m.kind in ("blocked", "wrong_way", "fidget")
        assert not m.drag.exits and 1 <= m.drag.cells_moved
        after = solve_fast(narrow, start=apply_drag(state, m.drag)).min_drags
        assert m.cost == after + 1 - base and 1 <= m.cost <= 2  # costs the player 1-2 drags
        if m.kind == "fidget":  # never a block that could simply leave
            assert not _can_exit_now(narrow, state, m.drag.block, occupancy(narrow, state))
    replay(narrow, solve_fast(narrow).drags[:1] + [m.drag for m in options[:1]])


def test_a_blocked_attempt_ends_against_another_block(narrow):
    state = apply_drag(initial_state(narrow), solve_fast(narrow).drags[0])
    blocked = [m for m in mistake_options(narrow, state) if m.kind == "blocked"]
    assert blocked
    occ = occupancy(narrow, state)
    for m in blocked:
        (ax, ay), (bx, by) = m.drag.path[-2], m.drag.path[-1]
        ahead = narrow.blocks[m.drag.block].cells_at((2 * bx - ax, 2 * by - ay))
        assert {occ.get(c) for c in ahead} - {None, m.drag.block}  # a block, not a wall, stops it
        assert not _can_exit_now(narrow, state, m.drag.block, occ)  # it really was trapped


@pytest.mark.parametrize("seed", range(6))
@pytest.mark.parametrize("ending", ["near_fail", "time_out"])
def test_mistakes_come_early_and_never_in_the_last_drags(narrow, ending, seed):
    beats = plan(narrow, ending, seed=seed).beats
    moves = [b for b in beats if b.kind != "hesitate"]
    at = [i for i, b in enumerate(moves) if b.kind == "mistake"]
    assert len(at) == 1
    assert at[0] <= 2  # drag 1, 2 or 3
    assert len(moves) - at[0] - 1 >= 3  # never in the last two drags, room to recover


def test_two_mistakes_are_spaced_and_at_most_one_is_a_fidget(narrow):
    for seed in range(4):
        beats = plan(narrow, "near_fail", mistakes=2, seed=seed).beats
        moves = [b for b in beats if b.kind != "hesitate"]
        at = [i for i, b in enumerate(moves) if b.kind == "mistake"]
        assert len(at) == 2 and at[1] - at[0] >= 3
        assert sum("nudged" in b.note for b in beats) <= 1


# ---------- endings ----------

def test_near_fail_doubts_the_last_block_then_finishes_quickly(plans):
    beats = plans["near_fail"].beats
    last, before = beats[-1], beats[-2]
    assert last.drag.exits and before.kind == "hesitate"
    assert before.drag.block == last.drag.block and len(before.drag.path) == 1
    solves = [b for b in beats if b.kind == "solve"]
    assert [b.pause for b in solves[-2:]] == ["cascade", "cascade"]  # the quick closing drags
    assert all(b.pause in ("cascade", "after_mistake", "stuck") for b in solves[-CASCADE_DRAGS:])
    assert sum(b.kind == "hesitate" for b in beats) == 2


def test_a_plain_win_has_no_mistakes_or_hesitations(plans, narrow):
    beats = plans["win"].beats
    assert {b.kind for b in beats} == {"solve"}
    assert len(beats) == solve_fast(narrow).min_drags


def test_cliffhanger_ends_pushing_a_trapped_block_into_its_blocker(narrow, plans):
    script = plans["cliffhanger"]
    bump = script.beats[-1]
    assert bump.kind == "bump" and bump.push_cells > 0 and bump.hold_f >= 24  # 0.8 s against it
    state = replay(narrow, script.drags[:-1])
    assert sum(p is not None for p in state) == 2
    occ = occupancy(narrow, state)
    assert not _can_exit_now(narrow, state, bump.drag.block, occ)
    sol = solve_fast(narrow, start=state)
    assert sol is not None and sol.extra_drags >= 1  # a real puzzle: "can you see the move?"
    assert any(d == bump.drag for d, _, _ in bumps(narrow, state))


def test_time_out_stops_one_cell_short_of_the_gate(narrow, plans):
    script = plans["time_out"]
    short = script.beats[-1]
    assert short.kind == "short" and not short.drag.exits
    state = replay(narrow, script.drags[:-1])
    assert sum(p is not None for p in state) == 1
    exits = [o for o in drag_outcomes(narrow, state, short.drag.block) if o.exits]
    assert any(o.path[:-1] == short.drag.path for o in exits)  # one more cell and it would leave


def test_cliffhanger_set_up_drags_into_a_blocker_are_played_as_attempts(narrow, plans):
    script = plans["cliffhanger"]
    attempts = [(i, b) for i, b in enumerate(script.beats) if b.kind == "attempt"]
    assert attempts
    for i, b in attempts:
        state = replay(narrow, script.drags[:i])
        assert any(a.block == b.drag.block and a.end == b.drag.end for a, _ in blocked_attempts(narrow, state))
        assert b.push_cells > 0 and b.hold_f > 0 and b.frames_per_cell == 4


def test_the_time_out_race_starts_with_a_second_on_the_clock(plans):
    short = plans["time_out"].beats[-1]
    assert short.pause == "thinking"  # no long stare with one block left
    # The clock hits zero as the block enters its last cell (half-way into the last step), about
    # 1.5 s after the touch, so 00:01 shows for half a second (the Unity test checks the frames).
    race = short.drag.cells_moved * short.frames_per_cell - short.frames_per_cell // 2
    assert short.pickup_f + race >= TIME_OUT_TOUCH_F >= FPS + 15


def test_a_time_out_needs_a_race_of_two_cells():
    level = load_level(PROJ / "data/levels/Level_06.json")  # its last exit is one cell
    with pytest.raises(ValueError, match="one cell from its gate"):
        plan(level, "time_out")


@pytest.mark.parametrize("name", ["Level_04", "Level_05", "Level_06"])
def test_shipped_level_cliffhangers_cut_on_a_real_puzzle(name):
    level = load_level(PROJ / f"data/levels/{name}.json")
    script = plan(level, "cliffhanger")
    assert script.beats[-1].kind == "bump"
    sol = solve_fast(level, start=replay(level, script.drags[:-1]))
    assert sol.extra_drags >= 1  # "can you see the move?" has a move to see


@pytest.mark.parametrize("name", ["Level_04", "Level_05", "Level_06", "gen/narrow_center_01"])
def test_every_mistake_gets_a_reaction(name):
    level = load_level(PROJ / f"data/levels/{name}.json")
    for ending in ("near_fail", "time_out"):
        for seed in range(5):
            try:
                beats = plan(level, ending, seed=seed).beats
            except ValueError:
                continue  # a time-out refused on this level
            for i, b in enumerate(beats):
                if b.kind == "mistake":
                    nxt = beats[i + 1]
                    assert nxt.kind == "hesitate" or nxt.pause_f >= PAUSES["after_mistake"][0], (ending, seed, i)
                    if nxt.pause == "stuck":
                        assert not nxt.drag.exits  # never a long stare before an obvious exit


@pytest.mark.parametrize("name", ["Level_01", "Level_03"])
def test_easy_levels_degrade_instead_of_failing(name):
    level = load_level(PROJ / f"data/levels/{name}.json")
    nf = plan(level, "near_fail")
    assert not any(b.kind == "mistake" for b in nf.beats) and "believable" in nf.notes[0]
    assert left_after(level, nf) == 0
    cl = plan(level, "cliffhanger")
    assert cl.left == min(2, len(level.blocks) - 1) and left_after(level, cl) == cl.left
    assert cl.beats[-1].kind == "hesitate" and any("hesitation" in n for n in cl.notes)


def test_time_out_is_only_for_hard_levels(narrow):
    assert time_out_allowed(rate(narrow))[0]
    assert time_out_allowed(rate(load_level(PROJ / "data/levels/Level_04.json")))[0]
    ok, why = time_out_allowed(rate(load_level(PROJ / "data/levels/Level_03.json")))
    assert not ok and "0 repositioning" in why


def test_bad_plan_arguments_are_refused(narrow):
    with pytest.raises(ValueError, match="ending must be"):
        plan(narrow, "lose")
    with pytest.raises(ValueError, match="mistakes must be"):
        plan(narrow, "near_fail", mistakes=4)
    with pytest.raises(ValueError, match="hesitations must be"):
        plan(narrow, "win", hesitations=2)
    with pytest.raises(ValueError, match="exactly one block"):
        plan(narrow, "time_out", left=2)
    with pytest.raises(ValueError, match="left must be"):
        plan(narrow, "cliffhanger", left=7)
    with pytest.raises(ValueError, match="clears the board"):
        plan(narrow, "win", left=2)


def test_play_json_round_trips(narrow, plans):
    for script in plans.values():
        d = script.to_dict(narrow)
        assert PlayScript.from_dict(json.loads(json.dumps(d))).to_dict(narrow) == d


# ---------- fitting: pauses only ----------

def test_spread_moves_exactly_delta_frames_inside_the_ranges(plans):
    beats = plans["near_fail"].beats
    idx = list(range(1, len(beats)))
    up = sum(PAUSES[b.pause][2] - b.pause_f for b in beats[1:])
    down = sum(b.pause_f - max(PAUSES[b.pause][0], MIN_PAUSE_F) for b in beats[1:])
    for delta in (-down, -7, -1, 1, up // 2, up):
        for proportional in (True, False):
            out = spread(beats, delta, idx, proportional)
            assert sum(b.pause_f - a.pause_f for a, b in zip(beats, out)) == delta
            for b in out[1:]:
                lo, _, hi = PAUSES[b.pause]
                assert max(lo, MIN_PAUSE_F) <= b.pause_f <= hi
            assert out == spread(beats, delta, idx, proportional)  # deterministic
    assert spread(beats, 0, idx) == beats


def test_spread_fills_in_the_given_order(plans):
    beats = plans["near_fail"].beats
    first = 1
    room = PAUSES[beats[first].pause][2] - beats[first].pause_f
    out = spread(beats, room, [first, 2, 3], proportional=False)
    assert out[first].pause_f == PAUSES[beats[first].pause][2] and out[2:] == beats[2:]


def test_spread_refuses_more_than_the_pauses_can_take(plans):
    beats = plans["win"].beats
    idx = list(range(1, len(beats)))
    up = sum(PAUSES[b.pause][2] - b.pause_f for b in beats[1:])
    with pytest.raises(ValueError, match=f"only {up} frames"):
        spread(beats, up + 1, idx)


def test_length_is_fitted_with_pauses_and_refused_out_of_human_range(plans):
    beats = plans["near_fail"].beats
    dry = 650
    lo, hi = length_range(beats, dry)
    assert lo < dry / FPS < hi
    out = fit_length(beats, dry, 22.0)
    assert dry + sum(b.pause_f - a.pause_f for a, b in zip(beats, out)) == 22 * FPS
    assert [(b.frames_per_cell, b.pickup_f) for b in out] == [(b.frames_per_cell, b.pickup_f) for b in beats]
    with pytest.raises(ValueError, match="human pauses"):
        fit_length(beats, dry, 60.0)
    with pytest.raises(ValueError, match="human pauses"):
        fit_length(beats, dry, 5.0)


def dry_frames(n, first_touch=30):
    """A dry run's frames: the clock starts at the first touch and runs at FPS."""
    return [{"frame": f, "timer": DRY_TIMER_S - max(0, f - first_touch) / FPS} for f in range(n)]


@pytest.mark.parametrize("stop", [500, 507, 515, 522])
def test_near_fail_clock_leaves_one_and_a_half_seconds(narrow, plans, stop):
    script = replace(plans["near_fail"])
    frames = dry_frames(stop + 100)
    beats, timer, fit = fit_clock(script, narrow, script.beats, {"clock_stopped_frame": stop}, frames)
    elapsed = (stop - 30) / FPS + fit["delta_f"] / FPS
    assert abs(timer - elapsed - NEAR_FAIL_LEFT_S) <= 0.5 / FPS
    assert sum(b.pause_f - a.pause_f for a, b in zip(script.beats, beats)) == fit["delta_f"]
    assert int(timer - elapsed) == 1  # the HUD shows 00:01


def test_near_fail_fit_uses_the_other_second_when_the_pauses_cannot_stretch(narrow, plans):
    script = replace(plans["near_fail"])
    full = [replace(b, pause_f=PAUSES[b.pause][2]) if i else b for i, b in enumerate(script.beats)]
    script = replace(script, beats=full)  # no pause can grow
    lo, hi = NEAR_FAIL_RANGE_S
    for stop in range(500, 530):
        beats, timer, fit = fit_clock(script, narrow, full, {"clock_stopped_frame": stop}, dry_frames(stop + 10))
        assert fit["delta_f"] <= 0 and lo <= fit["clock_left_s"] <= hi


def test_a_script_too_short_to_fit_is_refused_clearly(narrow, plans):
    script = replace(plans["near_fail"])
    script = replace(script, beats=script.beats[:1])  # one beat: no pause to move
    with pytest.raises(ValueError, match="too short to fit"):
        fit_clock(script, narrow, script.beats, {"clock_stopped_frame": 480}, dry_frames(500))  # 15.0 s


@pytest.mark.parametrize("target", [19.5, 20.0, 20.5, 21.0, 22.0])
def test_the_clock_fit_keeps_a_fitted_length(narrow, plans, target):
    # A real dry run (the game's float clock). For 20.5 s, clocks of 18 s and 19 s both leave
    # 1.50 s; the smaller pause change (-1 frame) must win over +29, or the clock fit would
    # undo --length (it did before the fix: 644 frames instead of 614).
    real = json.loads((PROJ / "tests/data/nc01_near_fail_dry.json").read_text())
    frames = [{"frame": i, "timer": t} for i, t in enumerate(real["timers"])]
    dry = {"clock_stopped_frame": real["clock_stopped_frame"]}
    script = replace(plans["near_fail"])
    script.beats = fit_length(script.beats, real["frames"], target)
    for keep in (False, True):
        beats, timer, fit = fit_clock(script, narrow, plans["near_fail"].beats, dry, frames, keep_length=keep)
        total = real["frames"] + sum(b.pause_f - a.pause_f for a, b in zip(plans["near_fail"].beats, beats))
        # The clock stays NEAR_FAIL_MARGIN_S inside its range (a fit on the edge, 1.30 s, was measured
        # as 1.2999 by the game and failed), which can cost the length up to 10 frames.
        assert abs(fit["delta_f"]) <= (10 if keep else 15) and abs(total - target * FPS) <= (10 if keep else 15)
        lo, hi = NEAR_FAIL_RANGE_S
        assert lo + NEAR_FAIL_MARGIN_S - 1e-6 <= fit["clock_left_s"] <= hi - NEAR_FAIL_MARGIN_S + 1e-6


def test_time_out_clock_runs_out_on_the_planned_frame(narrow, plans):
    script = replace(plans["time_out"])
    last = len(script.beats) - 1
    drags = [{"start_frame": 0}] * last + [{"start_frame": 560, "cell_frames": [566, 571, 576, 582]}]
    for shift in range(0, 30, 7):
        frames = dry_frames(700, first_touch=30 + shift)
        beats, timer, fit = fit_clock(script, narrow, script.beats, {"drags": drags}, frames)
        target = fit["fail_target_frame"]
        assert target == 582 + fit["delta_f"]
        assert abs((target - 30 - shift) / FPS - timer) < 1e-6  # the clock hits zero on that frame
        # The pause before the last drag absorbs it first.
        assert beats[last].pause_f - script.beats[last].pause_f == fit["delta_f"] or abs(fit["delta_f"]) > 9


def test_cliffhanger_clock_shows_eight_seconds_at_the_cut(narrow, plans):
    script = replace(plans["cliffhanger"])
    frames = dry_frames(517)
    beats, timer, fit = fit_clock(script, narrow, script.beats, {}, frames)
    assert beats == script.beats
    assert CLIFF_LEFT_S <= fit["clock_left_s"] < CLIFF_LEFT_S + 1


def test_a_win_keeps_the_clock_out_of_the_red(narrow, plans):
    script = replace(plans["win"])
    _, timer, fit = fit_clock(script, narrow, script.beats, {"clock_stopped_frame": 480}, dry_frames(560))
    assert timer == 15 + CALM_MARGIN_S and fit["clock_left_s"] >= 50  # the level's 60 s would dip below 0:50
    _, timer, _ = fit_clock(script, narrow, script.beats, {"clock_stopped_frame": 120}, dry_frames(200))
    assert timer is None  # 60 s is plenty for a 3 s solve


def test_predict_moves_every_later_drag_by_the_pause_change(plans):
    beats = plans["win"].beats
    dry = {"drags": [{"start_frame": 10 * i, "exit_frame": -1 if i % 2 else 10 * i + 5, "end_frame": 10 * i + 8}
                     for i in range(len(beats))]}
    moved = list(beats)
    moved[2] = replace(moved[2], pause_f=moved[2].pause_f + 5)
    p = predict(dry, beats, moved)
    assert [d["start_frame"] for d in p[:2]] == [0, 10]
    assert all(d["start_frame"] == 10 * i + 5 for i, d in enumerate(p) if i >= 2)
    assert p[3]["exit_frame"] == -1


def test_check_ending_flags_a_wrong_ending(plans):
    nf = plans["near_fail"]
    ok = {"timer_end": 1.5, "block_gone_frames": [10] * 7, "drags": [], "problems": []}
    assert check_ending(nf, ok, 7) == []
    assert "00:01" in check_ending(nf, dict(ok, timer_end=2.3), 7)[0]
    to = plans["time_out"]
    placed = {"timer_end": 0.0, "block_gone_frames": [10] * 6 + [-1], "fail_frame": 541,
              "drags": [{"result": "placed"}], "problems": []}
    assert any("cut short" in p for p in check_ending(to, placed, 7))
    assert any("planned 600" in p for p in check_ending(to, placed, 7, fail_target=600))
    p = check_ending(nf, dict(ok, drags=[{"start_frame": 3, "exit_frame": -1, "end_frame": 9}]), 7,
                     predicted=[{"start_frame": 4, "exit_frame": -1, "end_frame": 9}])
    assert any("predicted 4" in x for x in p)


# ---------- command line ----------

def test_cli_time_out_is_opt_in_and_refused_on_easy_levels(capsys):
    assert cli.main(["scenario", str(NARROW), "--ending", "time_out", "--plan-only"]) == 1
    assert "--allow-fail" in capsys.readouterr().err
    level3 = str(PROJ / "data/levels/Level_03.json")
    assert cli.main(["scenario", level3, "--ending", "time_out", "--allow-fail", "--plan-only"]) == 1
    assert "too easy" in capsys.readouterr().err


def test_cli_plan_only_prints_the_beats_and_the_label_note(capsys):
    assert cli.main(["scenario", str(NARROW), "--ending", "near_fail", "--plan-only"]) == 0
    out = capsys.readouterr().out
    assert "mistake" in out and "hesitate" in out and "naive player" in out
    assert "--label" in out  # the file name has no level number


def test_cli_length_with_plan_only_says_it_is_not_applied(capsys):
    assert cli.main(["scenario", str(NARROW), "--ending", "win", "--length", "15", "--plan-only"]) == 0
    assert "fitted after the dry run" in capsys.readouterr().out


def test_rerun_refuses_a_folder_without_a_recording_or_the_same_folder(tmp_path):
    with pytest.raises(ValueError, match="no recording"):
        render.rerun(tmp_path, tmp_path / "again")
    (tmp_path / "job.json").write_text("{}")
    (tmp_path / "result.json").write_text("{}")
    with pytest.raises(ValueError, match="different folder"):
        render.rerun(tmp_path, tmp_path)


def test_cli_render_dry_run_films_nothing(monkeypatch, capsys):
    seen = {}

    def fake_run(job, app=None):
        seen.update(job)
        return {"status": "cleared", "message": "", "frames": 100, "duration_s": 3.33, "fps": 30,
                "drags": [], "win_frame": 90, "timer_end": 50.0, "problems": []}

    monkeypatch.setattr(render, "run_player", fake_run)
    level3 = str(PROJ / "data/levels/Level_03.json")
    assert cli.main(["render", level3, "--dry-run", "-o", "/tmp/cbj-dry-test"]) == 0
    assert seen["capture"] is False
    assert "Dry run" in capsys.readouterr().out


def test_deliberate_pacing_slows_a_short_solve_but_keeps_the_closing_cascade():
    """A 4-drag easy win is all cascade (about 7 s): paced deliberately it thinks before every other drag
    and keeps the last two quick, so a 30 s ad opens on motion instead of a frozen frame (2026-10-14)."""
    from cbj.play import CONFIDENT, PAUSES, PICKUP_CAREFUL, TENTATIVE, Beat, deliberate
    from cbj.solver import Drag
    d = Drag(0, ((0, 0), (0, 1)), True)
    beats = [Beat("solve", d, "start", 0, 3, CONFIDENT, "first"),
             Beat("solve", d, "cascade", 11, 3, CONFIDENT, ""),
             Beat("mistake", d, "before_mistake", 24, 3, CONFIDENT, ""),
             Beat("solve", d, "confident", 14, 3, CONFIDENT, ""),
             Beat("solve", d, "cascade", 11, 3, CONFIDENT, ""),
             Beat("solve", d, "cascade", 11, 3, CONFIDENT, "")]
    out = deliberate(beats)
    assert out[0].pause == "start"  # the first drag still starts at once
    assert out[1].pause == "deliberate" and out[1].pause_f == PAUSES["deliberate"][1]  # a long look, 1.6-2.2 s
    assert out[1].frames_per_cell == TENTATIVE and out[1].pickup_f == PICKUP_CAREFUL  # the slowest finger
    assert out[2].pause == "before_mistake"  # a mistake keeps its own pause
    assert out[3].pause == "confident"  # every other drag: look, drag, drag (uniform long gaps read as dull)
    assert out[4].pause == "cascade" and out[5].pause == "cascade"  # the closing cascade lands the win
    assert sum(b.pause_f for b in out) > sum(b.pause_f for b in beats) + 40


def test_calm_tempo_breathes_between_moves_and_a_short_solve_keeps_one_closing_drag():
    from cbj.play import GLIDE, CONFIDENT, PAUSES, Beat, deliberate
    from cbj.solver import Drag
    d = Drag(0, ((0, 0), (0, 1)), True)
    beats = [Beat("solve", d, "start", 0, 3, CONFIDENT, ""), Beat("solve", d, "cascade", 11, 3, CONFIDENT, ""),
             Beat("solve", d, "cascade", 11, 3, CONFIDENT, ""), Beat("solve", d, "cascade", 11, 3, CONFIDENT, "")]
    out = deliberate(beats, tempo="calm")
    assert [b.pause for b in out] == ["start", "calm", "calm", "cascade"]  # 4 drags: one quick closing drag
    assert out[1].pause_f == PAUSES["calm"][1] and out[1].frames_per_cell == GLIDE
    out = deliberate(beats + beats[1:], tempo="normal")  # 7 drags: two closing drags, a look before every other drag
    assert [b.pause for b in out] == ["start", "deliberate", "cascade", "deliberate", "cascade", "cascade", "cascade"]


def test_an_asked_clock_is_used_as_asked(narrow, plans):
    """A request's clock value is not raised for the HUD's colour (2026-10-16): a 60 s clock on a
    20 s play runs as 60 s and the fit says the HUD shows red for part of it; a clock shorter than
    the play itself becomes the smallest clock the play fits in."""
    from cbj.play import ASKED_CLOCK_MARGIN_S
    script = replace(plans["win"], timer_s=60)
    stop = 30 + 20 * FPS  # the clock stops 20 s after the first touch
    beats, timer, fit = fit_clock(script, narrow, script.beats, {"clock_stopped_frame": stop}, dry_frames(stop + 100))
    assert timer == 60 and fit["asked"] and "red" in fit["why"]
    script = replace(plans["win"], timer_s=120)
    beats, timer, fit = fit_clock(script, narrow, script.beats, {"clock_stopped_frame": stop}, dry_frames(stop + 100))
    assert timer == 120 and fit["asked"] and "why" not in fit
    script = replace(plans["win"], timer_s=15)
    beats, timer, fit = fit_clock(script, narrow, script.beats, {"clock_stopped_frame": stop}, dry_frames(stop + 100))
    assert timer == 20 + ASKED_CLOCK_MARGIN_S and "shorter than the play" in fit["why"]
