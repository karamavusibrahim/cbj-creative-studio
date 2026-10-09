import json
from pathlib import Path

import pytest

from cbj.level import BlockColor as C
from cbj.level import ExitDirection as D
from cbj.level import level_to_dict, load_level, normalize_block_offsets, validate

from helpers import make_level

LEVELS = sorted(Path(__file__).parent.parent.joinpath("data/levels").glob("*.json"))


def test_six_shipped_levels_present():
    assert [p.stem for p in LEVELS] == [f"Level_0{i}" for i in range(1, 7)]


@pytest.mark.parametrize("path", LEVELS, ids=lambda p: p.stem)
def test_round_trip_matches_shipped_json(path):
    assert level_to_dict(load_level(path)) == json.loads(path.read_text())


@pytest.mark.parametrize("path", LEVELS, ids=lambda p: p.stem)
def test_shipped_levels_are_valid(path):
    assert validate(load_level(path, strict=False)) == []


def test_offsets_follow_block_initialize():
    # Block.Initialize: empty list becomes [(0,0)]; a missing (0,0) is appended.
    assert normalize_block_offsets([]) == ((0, 0),)
    assert normalize_block_offsets([(1, 0), (2, 0)]) == ((1, 0), (2, 0), (0, 0))
    assert normalize_block_offsets([(0, 0), (0, -1)]) == ((0, 0), (0, -1))


def test_validate_reports_overlap_bounds_and_inactive():
    lvl = make_level(
        3, 3,
        blocks=[(C.RED, (0, 0), [(0, 0), (1, 0)]), (C.BLUE, (1, 0), []), (C.GREEN, (2, 2), [(1, 0)])],
        exits=[(C.RED, D.TOP, (1, 1), [])],
        inactive=[(2, 2)],
    )
    problems = " | ".join(validate(lvl))
    assert "overlaps" in problems
    assert "out of bounds" in problems
    assert "inactive" in problems
    assert "does not face an edge on its top side" in problems


def test_gate_on_the_rim_of_a_hole_is_valid():
    # GridManager.NeedsBorder treats an inactive neighbour as an edge, so Unity draws and uses this gate.
    lvl = make_level(4, 3, [(C.RED, (3, 1), [])], [(C.RED, D.LEFT, (1, 1), [])], inactive=[(0, 1)])
    assert validate(lvl) == []


def test_gate_on_an_inactive_cell_is_flagged():
    lvl = make_level(3, 3, [(C.RED, (1, 1), [])], [(C.RED, D.TOP, (1, 2), [])], inactive=[(1, 2)])
    assert any("inactive cell, so no block can reach it" in p for p in validate(lvl))


def test_round_trip_keeps_inactive_cell_order():
    lvl = make_level(4, 4, [(C.RED, (0, 0), [])], [(C.RED, D.BOTTOM, (0, 0), [])], inactive=[(3, 3), (1, 2), (2, 1)])
    assert [(c["x"], c["y"]) for c in level_to_dict(lvl)["inactiveCells"]] == [(3, 3), (1, 2), (2, 1)]
