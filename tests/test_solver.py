import random
from dataclasses import replace
from pathlib import Path

import pytest

from cbj.level import BlockColor as C
from cbj.level import ExitDirection as D
from cbj.level import load_level, validate
from cbj.solver import ReplayError, SolverLimitError, replay, solve

from helpers import make_level, rich_random_level

LEVELS = sorted(Path(__file__).parent.parent.joinpath("data/levels").glob("*.json"))

# Minimum drags found by BFS. Levels 1-5 were also confirmed by BFS without exit pruning.
# Level 6 equals its block count, the lower bound (each block needs at least one drag).
EXPECTED_MIN_DRAGS = {"Level_01": 2, "Level_02": 2, "Level_03": 3, "Level_04": 4, "Level_05": 5, "Level_06": 8}


@pytest.mark.parametrize("path", LEVELS, ids=lambda p: p.stem)
def test_shipped_level_solves_and_replays(path):
    level = load_level(path)
    sol = solve(level)
    assert sol is not None, f"{level.name} unsolvable"
    final = replay(level, sol.drags)
    assert all(p is None for p in final)
    assert sol.min_drags == EXPECTED_MIN_DRAGS[level.name]
    assert sol.min_drags >= len(level.blocks)
    exited = [d.block for d in sol.drags if d.exits]
    assert sorted(exited) == list(range(len(level.blocks)))  # every block exits exactly once


@pytest.mark.parametrize("name", ["Level_01", "Level_02", "Level_03", "Level_04", "Level_05"])
def test_exit_pruning_keeps_the_optimum_on_shipped_levels(name):
    level = load_level(Path(__file__).parent.parent / "data/levels" / f"{name}.json")
    assert solve(level).min_drags == solve(level, prune_exits=False).min_drags


def _random_level(rng: random.Random):
    w, h = rng.randint(3, 4), rng.randint(3, 4)
    shapes = [[], [(1, 0)], [(0, 1)], [(1, 0), (0, 1)], [(1, 0), (2, 0)]]
    colors = rng.sample([C.RED, C.BLUE, C.GREEN], rng.randint(2, 3))
    blocks, taken = [], set()
    for col in colors:
        for _ in range(30):
            offs = rng.choice(shapes)
            p = (rng.randrange(w), rng.randrange(h))
            cells = {(p[0] + ox, p[1] + oy) for ox, oy in [(0, 0)] + offs}
            if all(0 <= x < w and 0 <= y < h for x, y in cells) and not cells & taken:
                blocks.append((col, p, offs))
                taken |= cells
                break
    exits = []
    for col in colors:
        for _ in range(rng.randint(1, 2)):
            d = rng.choice(list(D))
            if d in (D.TOP, D.BOTTOM):
                y = h - 1 if d == D.TOP else 0
                x = rng.randrange(w - 1)
                exits.append((col, d, (x, y), [(1, 0)]))
            else:
                x = 0 if d == D.LEFT else w - 1
                y = rng.randrange(h - 1)
                exits.append((col, d, (x, y), [(0, 1)]))
    return make_level(w, h, blocks, exits)


def test_exit_pruning_matches_full_search_on_random_small_levels():
    rng = random.Random(20261010)
    compared = solvable = 0
    for _ in range(250):
        level = _random_level(rng)
        if validate(level):
            continue
        try:
            full = solve(level, max_states=200_000, prune_exits=False)
        except SolverLimitError:
            continue
        pruned = solve(level)
        compared += 1
        assert (pruned is None) == (full is None)
        if full is not None:
            solvable += 1
            assert pruned.min_drags == full.min_drags
            replay(level, pruned.drags)
    assert compared >= 150 and solvable >= 50


def test_exit_pruning_matches_full_search_on_rich_random_levels():
    # Holes, gates on hole rims, repeated colours, L/T/2x2 shapes, 1-3 cell gates.
    rng = random.Random(7)
    compared = solvable = 0
    for _ in range(1500):
        level = rich_random_level(rng)
        if validate(level):
            continue
        try:
            full = solve(level, max_states=100_000, prune_exits=False)
        except SolverLimitError:
            continue
        pruned = solve(level)
        compared += 1
        assert (pruned is None) == (full is None)
        if full is not None:
            solvable += 1
            assert pruned.min_drags == full.min_drags
            replay(level, pruned.drags)
    assert compared >= 250 and solvable >= 100


def test_gate_order_in_the_file_changes_the_minimum():
    # Green 3-bar in column 3 touches the green TOP gate and the green RIGHT gate.
    # The game only tests the first matching gate in list order:
    # TOP first  -> the bar exits upward (step down, step back up): 2 drags in total.
    # RIGHT first -> the right lane check always fails for a 3-tall bar, so it must use
    #               the bottom-left gate after blue moves out of column 1: 3 drags.
    blocks = [(C.BLUE, (0, 2), []), (C.GREEN, (2, 1), [(0, 1), (0, 2)])]
    green_top = (C.GREEN, D.TOP, (2, 3), [])
    green_bottom = (C.GREEN, D.BOTTOM, (0, 0), [])
    green_right = (C.GREEN, D.RIGHT, (2, 2), [])
    blue_top = (C.BLUE, D.TOP, (2, 3), [])
    top_first = make_level(3, 4, blocks, [green_top, green_bottom, green_right, blue_top])
    right_first = make_level(3, 4, blocks, [blue_top, green_right, green_bottom, green_top])
    for lvl, want in ((top_first, 2), (right_first, 3)):
        sol = solve(lvl)
        assert sol.min_drags == want
        assert solve(lvl, prune_exits=False).min_drags == want
        replay(lvl, sol.drags)


def test_level_with_no_gate_for_a_colour_is_unsolvable():
    lvl = make_level(3, 3, [(C.RED, (0, 0), []), (C.BLUE, (2, 2), [])], [(C.RED, D.TOP, (0, 2), [])])
    assert solve(lvl) is None


def test_replay_rejects_broken_solutions():
    level = load_level(Path(__file__).parent.parent / "data/levels/Level_04.json")
    drags = solve(level).drags

    # Skipping the repositioning drag: the orange bar's route is blocked by yellow.
    with pytest.raises(ReplayError):
        replay(level, drags[1:])

    # Claiming the first drag exits when the game would only stop there.
    with pytest.raises(ReplayError):
        replay(level, [replace(drags[0], exits=True)] + drags[1:])

    # A path that jumps two cells in one step.
    jumpy = replace(drags[1], path=(drags[1].path[0],) + drags[1].path[2:])
    with pytest.raises(ReplayError):
        replay(level, [drags[0], jumpy] + drags[2:])

    # Naming a different gate than the one the game picks.
    wrong_gate = replace(drags[1], exit_index=(drags[1].exit_index + 1) % len(level.exits))
    with pytest.raises(ReplayError):
        replay(level, [drags[0], wrong_gate] + drags[2:])

    # A block that does not exist.
    with pytest.raises(ReplayError):
        replay(level, [replace(drags[0], block=99)])


def test_replay_accepts_pick_up_and_put_back():
    # Lifting a block and releasing it on the same cell is legal and changes nothing.
    level = load_level(Path(__file__).parent.parent / "data/levels/Level_01.json")
    drags = solve(level).drags
    noop = replace(drags[0], path=(drags[0].path[0],), exits=False, exit_index=None)
    assert all(p is None for p in replay(level, [noop] + drags))
    with pytest.raises(ReplayError):
        replay(level, [replace(noop, exits=True)] + drags)
