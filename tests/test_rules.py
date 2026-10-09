"""Exit rule and drag model, checked against the behaviour of the Unity C# code.

Coordinates are 0-based grid cells, y up. Each test names the C# behaviour it pins.
"""

from cbj.level import BlockColor as C
from cbj.level import ExitDirection as D
from cbj.rules import can_block_exit, initial_state, occupancy
from cbj.solver import drag_outcomes

from helpers import make_level


def exit_ok(level, block_id, pivot):
    state = list(initial_state(level))
    state[block_id] = pivot
    return can_block_exit(level, block_id, pivot, occupancy(level, tuple(state)))


def test_block_on_gate_with_clear_lane_exits():
    lvl = make_level(3, 3, [(C.RED, (1, 2), [])], [(C.RED, D.TOP, (1, 2), [])])
    assert exit_ok(lvl, 0, (1, 2))


def test_wrong_colour_gate_does_not_count():
    lvl = make_level(3, 3, [(C.RED, (1, 2), [])], [(C.BLUE, D.TOP, (1, 2), [])])
    assert not exit_ok(lvl, 0, (1, 2))


def test_block_must_overlap_a_gate_cell():
    # FindMatchingExit needs an overlap; a clear lane alone is not enough.
    lvl = make_level(3, 3, [(C.RED, (1, 1), [])], [(C.RED, D.TOP, (1, 2), [])])
    assert not exit_ok(lvl, 0, (1, 1))


def test_every_block_column_must_be_inside_the_gate_span():
    # 2-wide bar on the top row, gate covers only column 1.
    lvl = make_level(3, 3, [(C.RED, (0, 2), [(0, 0), (1, 0)])], [(C.RED, D.TOP, (1, 2), [])])
    assert not exit_ok(lvl, 0, (0, 2))
    wide = make_level(3, 3, [(C.RED, (0, 2), [(0, 0), (1, 0)])], [(C.RED, D.TOP, (0, 2), [(1, 0)])])
    assert exit_ok(wide, 0, (0, 2))


def test_other_block_in_the_lane_blocks_the_exit():
    # L piece: cells (1,2) on the gate, (1,1) and (2,1) below. Blue at (2,2) sits in (2,1)'s lane.
    shape = [(0, 0), (0, -1), (1, -1)]
    gate = (C.RED, D.TOP, (1, 2), [(1, 0)])
    blocked = make_level(3, 3, [(C.RED, (1, 2), shape), (C.BLUE, (2, 2), [])], [gate])
    assert not exit_ok(blocked, 0, (1, 2))
    clear = make_level(3, 3, [(C.RED, (1, 2), shape)], [gate])
    assert exit_ok(clear, 0, (1, 2))


def test_inactive_cell_does_not_block_the_lane():
    # Game quirk: GridManager.GetCell returns null for an inactive cell and
    # ExitService.IsPathClear only fails on a cell that holds another block.
    shape = [(0, 0), (0, -1), (1, -1)]
    lvl = make_level(3, 3, [(C.RED, (1, 2), shape)], [(C.RED, D.TOP, (1, 2), [(1, 0)])], inactive=[(2, 2)])
    assert exit_ok(lvl, 0, (1, 2))


def test_only_the_first_matching_gate_is_checked():
    # Game quirk: FindMatchingExit returns the first colour-matching overlapping
    # gate in list order; IsPathClear is never tried on a later gate.
    # Red L: (0,2), (0,1), (1,1). Blue at (1,2) blocks the Top lane of (1,1).
    shape = [(0, 0), (0, -1), (1, -1)]
    blocks = [(C.RED, (0, 2), shape), (C.BLUE, (1, 2), [])]
    top = (C.RED, D.TOP, (0, 2), [])
    left = (C.RED, D.LEFT, (0, 1), [(0, 1)])
    top_first = make_level(3, 3, blocks, [top, left])
    left_first = make_level(3, 3, blocks, [left, top])
    assert not exit_ok(top_first, 0, (0, 2))
    assert exit_ok(left_first, 0, (0, 2))


def test_drag_ends_at_the_first_cell_where_the_exit_passes():
    # Single red cell at (0,2) dragged right along the top row: gate at (1,2).
    # The drag cannot pass over (1,2) to stop at (2,2) without exiting at (1,2) first,
    # but (2,2) is still reachable by going around underneath.
    lvl = make_level(3, 3, [(C.RED, (0, 2), [])], [(C.RED, D.TOP, (1, 2), [])])
    outs = drag_outcomes(lvl, initial_state(lvl), 0)
    exits = [o for o in outs if o.exits]
    assert [o.path for o in exits] == [((0, 2), (1, 2))]
    stop_at_22 = [o for o in outs if not o.exits and o.end == (2, 2)]
    assert stop_at_22 and (1, 2) not in stop_at_22[0].path


def test_block_already_on_its_gate_must_step_away_and_back():
    # The check runs only when the pivot enters a different cell. A block that starts
    # in an exit position leaves by stepping out and back in.
    lvl = make_level(3, 3, [(C.RED, (1, 2), [])], [(C.RED, D.TOP, (1, 2), [])])
    outs = drag_outcomes(lvl, initial_state(lvl), 0)
    exits = [o for o in outs if o.exits]
    assert len(exits) == 1
    path = exits[0].path
    assert path[0] == path[-1] == (1, 2) and len(path) == 3


def test_block_may_move_into_its_own_previous_cells():
    lvl = make_level(4, 1, [(C.RED, (0, 0), [(1, 0)])], [])
    ends = {o.end for o in drag_outcomes(lvl, initial_state(lvl), 0)}
    assert ends == {(1, 0), (2, 0)}


def test_holes_and_other_blocks_stop_movement():
    lvl = make_level(4, 1, [(C.RED, (0, 0), []), (C.BLUE, (3, 0), [])], [], inactive=[(2, 0)])
    ends = {o.end for o in drag_outcomes(lvl, initial_state(lvl), 0)}
    assert ends == {(1, 0)}
