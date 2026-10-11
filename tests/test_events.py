"""Gameplay events (a requested order of interactions) and the satisfying finish."""

import random

import pytest

from cbj.events import Event, best_finish, check_events, from_brief, resolve, solve_events, trailing_exits
from cbj.generate import Spec, candidate
from cbj.level import BlockColor, level_from_dict, load_level, validate
from cbj.rules import initial_state
from cbj.solver import SolverLimitError, replay, solve_fast

from pathlib import Path

NC = Path(__file__).resolve().parents[1] / "data" / "levels" / "gen" / "narrow_center_01.json"


@pytest.fixture(scope="module")
def nc():
    return load_level(NC)


def ids(level, colour):
    return frozenset(i for i, b in enumerate(level.blocks) if b.color == colour)


def test_no_events_gives_the_minimum_on_random_boards():
    rng = random.Random(11)
    checked = 0
    while checked < 25:
        spec = Spec(shape=rng.choice(["open", "narrow_center", "door", "holes"]),
                    difficulty=rng.choice(["easy", "medium", "hard"])).resolved()
        try:
            lvl = level_from_dict(candidate(spec, rng), "x")
        except ValueError:
            continue
        if validate(lvl):
            continue
        try:
            a = solve_fast(lvl, max_states=8000)
        except SolverLimitError:
            continue
        if a is None:
            continue
        b = solve_events(lvl, [], max_states=200_000)
        assert b.min_drags == a.min_drags
        checked += 1


def test_order_of_exits(nc):
    evs = [Event("leaves", ids(nc, BlockColor.BLUE), text="blue"), Event("leaves", ids(nc, BlockColor.RED), text="red")]
    s = solve_events(nc, evs)
    assert s.min_drags == solve_fast(nc).min_drags  # this order costs nothing on this level
    blue, red = s.done_at
    assert blue < red and s.drags[blue].exits and s.drags[red].exits
    assert all(p is None for p in replay(nc, s.drags))
    assert check_events(nc, evs, s.drags).ok


def test_last_means_the_board_is_empty_after_it(nc):
    evs = [Event("leaves", ids(nc, BlockColor.PURPLE), when="last", text="purple last")]
    s = solve_events(nc, evs)
    assert s.drags[-1].block in ids(nc, BlockColor.PURPLE) and s.done_at == [len(s.drags) - 1]


def test_first_must_be_the_first_drag(nc):
    # green cannot leave at the start on this level, so "green leaves first" is impossible
    assert solve_events(nc, [Event("leaves", ids(nc, BlockColor.GREEN), when="first")]) is None
    s = solve_events(nc, [Event("moves", ids(nc, BlockColor.RED), when="first", text="red moves first")])
    assert s.done_at == [0] and s.drags[0].block in ids(nc, BlockColor.RED) and not s.drags[0].exits


def test_stuck_and_hesitates_are_not_solver_events(nc):
    with pytest.raises(ValueError):
        solve_events(nc, [Event("stuck", ids(nc, BlockColor.RED))])


def test_references_resolve_on_the_level():
    lvl = load_level(Path(NC).parents[1] / "Level_06.json")
    yellow = [i for i, b in enumerate(lvl.blocks) if b.color == BlockColor.YELLOW]
    assert resolve(lvl, "Yellow", "any")[0] == frozenset(yellow)
    assert resolve(lvl, "Yellow", "any", all_=True)[0] == frozenset(yellow)
    big, note = resolve(lvl, None, "biggest")
    assert len(big) == 1 and lvl.blocks[next(iter(big))].size == max(b.size for b in lvl.blocks)
    assert note and "equally big" in note  # six blocks of 3 cells: the tie is reported
    assert resolve(lvl, "Orange", "any")[0] == frozenset()  # no orange block on Level 6


def test_from_brief_drops_what_the_level_cannot_do_and_says_why():
    lvl = load_level(Path(NC).parents[1] / "Level_06.json")
    raw = [{"block": {"colour": "Orange", "which": "any", "all": False}, "action": "leaves", "when": "next"},
           {"block": {"colour": "Red", "which": "any", "all": False}, "action": "leaves", "when": "last"},
           {"block": {"colour": "Blue", "which": "any", "all": True}, "action": "leaves", "when": "first"}]
    evs, notes = from_brief(lvl, raw)
    assert [e.text for e in evs] == ["the red block leaves", "all the blue blocks leave"]
    assert evs[0].when == "next" and evs[1].when == "next" and evs[1].all
    assert any("no such block" in n for n in notes) and any("only the final" in n for n in notes)
    assert any("only the first event" in n for n in notes)


def test_check_catches_a_broken_order(nc):
    sol = solve_fast(nc).drags
    first_exit = next(d.block for d in sol if d.exits)
    other = next(i for i in range(len(nc.blocks)) if i != first_exit)
    evs = [Event("leaves", frozenset({other}), text="other first"), Event("leaves", frozenset({first_exit}), text="x")]
    c = check_events(nc, evs, sol)
    assert not c.ok and "breaks the order" in c.problem


def test_an_event_must_name_a_block():
    with pytest.raises(ValueError):
        Event("leaves", frozenset(), text="pink block")


def test_best_finish_ends_on_one_long_run(nc):
    f = best_finish(nc)
    assert f.method == "every repositioning drag first"
    assert len(f.drags) == solve_fast(nc).min_drags  # no extra drags
    assert all(p is None for p in replay(nc, f.drags))
    assert f.streak == trailing_exits(f.drags) == 7  # one key move, then all seven leave in a row
    assert f.streak >= trailing_exits(solve_fast(nc).drags)
    assert not f.drags[f.key].exits
