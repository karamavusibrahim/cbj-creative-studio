"""Difficulty numbers and solving from a mid-game position."""

from pathlib import Path

import pytest

from cbj import cli
from cbj.difficulty import naive_play, rate
from cbj.level import BlockColor as C
from cbj.level import ExitDirection as D
from cbj.level import load_level
from cbj.rules import initial_state
from cbj.solver import apply_drag, solve

from helpers import make_level

LEVELS = Path(__file__).parent.parent / "data/levels"


def test_solve_from_a_mid_game_position():
    level = load_level(LEVELS / "Level_03.json")
    full = solve(level)
    after_one = apply_drag(initial_state(level), full.drags[0])
    rest = solve(level, start=after_one)
    assert rest.min_drags == full.min_drags - 1
    assert rest.blocks == len(level.blocks) - 1


def test_solve_rejects_a_start_of_the_wrong_length():
    level = load_level(LEVELS / "Level_03.json")
    with pytest.raises(ValueError, match="3 blocks"):
        solve(level, start=((0, 0),))


@pytest.mark.parametrize("name", ["Level_01", "Level_02", "Level_03", "Level_05", "Level_06"])
def test_shipped_levels_where_taking_any_exit_is_optimal(name):
    # On these boards an exit is always available, so the naive player never wastes a drag.
    d = rate(load_level(LEVELS / f"{name}.json"))
    assert d.extra_drags == 0
    assert d.naive_mean == d.min_drags and d.naive_capped == 0


def test_level_4_needs_a_repositioning_drag_and_the_naive_player_wastes_some():
    d = rate(load_level(LEVELS / "Level_04.json"))
    assert (d.min_drags, d.extra_drags, d.exits_at_start) == (4, 1, 0)
    assert d.naive_mean > d.min_drags
    assert d.naive_ratio > 1


def test_rating_is_repeatable_with_a_seed():
    level = load_level(LEVELS / "Level_04.json")
    assert rate(level, seed=7) == rate(level, seed=7)


def test_unsolvable_level_has_no_rating():
    # One red block, and the only gate is blue.
    level = make_level(3, 3, [(C.RED, (1, 1), [])], [(C.BLUE, D.TOP, (1, 2), [])])
    assert rate(level) is None


def test_naive_play_reports_the_cap():
    import random
    level = load_level(LEVELS / "Level_04.json")
    assert naive_play(level, random.Random(0), cap=1) is None


def test_cli_difficulty_table(capsys):
    assert cli.main(["difficulty", str(LEVELS)]) == 0
    out = capsys.readouterr().out
    assert "| Level_04 | 3 | 4 | 1 | 0 |" in out
    assert out.count("| Level_0") == 6


def test_cli_difficulty_missing_path(capsys):
    assert cli.main(["difficulty", "no/such/place"]) == 1
    assert "no such level file or folder" in capsys.readouterr().err
