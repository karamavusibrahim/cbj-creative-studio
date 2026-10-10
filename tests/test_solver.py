import random
from dataclasses import replace
from pathlib import Path

import pytest

from cbj.level import BlockColor as C
from cbj.level import ExitDirection as D
from cbj.level import load_level, validate
from cbj.rules import initial_state
from cbj.solver import ReplayError, SolverLimitError, apply_drag, replay, solve, solve_fast

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
    exits, used = [], set()  # one gate per cell side, as in the Level Editor
    for col in colors:
        for _ in range(rng.randint(1, 2)):
            for _ in range(10):
                d = rng.choice(list(D))
                if d in (D.TOP, D.BOTTOM):
                    y = h - 1 if d == D.TOP else 0
                    x = rng.randrange(w - 1)
                    p, offs, cells = (x, y), [(1, 0)], [(x, y), (x + 1, y)]
                else:
                    x = 0 if d == D.LEFT else w - 1
                    y = rng.randrange(h - 1)
                    p, offs, cells = (x, y), [(0, 1)], [(x, y), (x, y + 1)]
                if not any((c, d) in used for c in cells):
                    used |= {(c, d) for c in cells}
                    exits.append((col, d, p, offs))
                    break
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
    # 3x3 board, hole at column 1 row 2. R1 is a single red cell at column 1 row 1,
    # R2 a red 2-cell bar at columns 2-3 row 1. Red gates: bottom (columns 1-2),
    # left (row 1), right (row 1). R2 touches both the bottom and the right gate.
    # The game only tests the first matching gate in list order:
    # bottom first -> R2's right cell (column 3) is outside the bottom gate, so R2 can
    #                 never use the right gate; it waits for R1 to leave: 3 drags.
    # right first  -> R2 steps up and back down to exit right, then R1 exits: 2 drags.
    blocks = [(C.RED, (0, 0), []), (C.RED, (1, 0), [(1, 0)])]
    bottom = (C.RED, D.BOTTOM, (0, 0), [(1, 0)])
    left = (C.RED, D.LEFT, (0, 0), [])
    right = (C.RED, D.RIGHT, (2, 0), [])
    bottom_first = make_level(3, 3, blocks, [bottom, left, right], inactive=[(0, 1)])
    right_first = make_level(3, 3, blocks, [right, left, bottom], inactive=[(0, 1)])
    for lvl, want in ((bottom_first, 3), (right_first, 2)):
        assert validate(lvl) == []  # buildable in the Level Editor
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


# Minimum drags of the generated levels, found by solve() (5 s for the runner-up, so not re-run here).
GEN_MINIMUM = {"narrow_center_01": 9, "narrow_center_02_runner_up": 8}
GEN_DIR = Path(__file__).parent.parent.joinpath("data/levels/gen")


@pytest.mark.parametrize("path", LEVELS, ids=lambda p: p.stem)
def test_fast_solver_finds_the_same_minimum(path):
    level = load_level(path)
    a, b = solve(level), solve_fast(level)
    assert b.min_drags == a.min_drags and b.extra_drags == a.extra_drags
    assert all(p is None for p in replay(level, b.drags))
    assert b.states_explored <= a.states_explored


@pytest.mark.parametrize("name", sorted(GEN_MINIMUM))
def test_fast_solver_on_the_generated_levels(name):
    level = load_level(GEN_DIR / f"{name}.json")
    b = solve_fast(level)
    assert b.min_drags == GEN_MINIMUM[name]
    assert all(p is None for p in replay(level, b.drags))
    assert b.states_explored < 2000  # solve() needs 43k and 115k


def test_fast_solver_matches_from_every_position_along_a_solution():
    # Along a minimum solution, the drags still needed after k drags are exactly total - k.
    level = load_level(GEN_DIR / "narrow_center_01.json")
    sol = solve_fast(level)
    state = initial_state(level)
    for k, d in enumerate(sol.drags):
        assert solve_fast(level, start=state).min_drags == sol.min_drags - k
        state = apply_drag(state, d)


def test_fast_solver_matches_full_search_on_rich_random_levels():
    rng = random.Random(11)
    compared = solvable = 0
    for _ in range(1500):
        level = rich_random_level(rng)
        if validate(level):
            continue
        try:
            full = solve(level, max_states=100_000, prune_exits=False)
        except SolverLimitError:
            continue
        fast = solve_fast(level)
        compared += 1
        assert (fast is None) == (full is None)
        if full is not None:
            solvable += 1
            assert fast.min_drags == full.min_drags
            assert all(p is None for p in replay(level, fast.drags))
    assert compared >= 250 and solvable >= 100
