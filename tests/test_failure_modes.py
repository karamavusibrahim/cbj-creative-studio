"""Failure modes: the system must refuse bad input with a clear ValueError / ReplayError /
SolverLimitError (or CLI exit code 1 and one readable line), report unsolvable levels as
unsolvable, and never hang. Cases come from the Fable 5.1 adversarial run of 2026-10-10.
"""

import json
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from cbj.describe import script_to_drags
from cbj.level import BlockColor as C
from cbj.level import ExitDirection as D
from cbj.level import level_from_dict, load_level, validate
from cbj.solver import Drag, ReplayError, SolverLimitError, replay, solve

from helpers import make_level

PROJ = Path(__file__).parent.parent
LEVEL_01 = PROJ / "data/levels/Level_01.json"
LEVEL_03 = PROJ / "data/levels/Level_03.json"
MOVES_03 = PROJ / "data/solutions/Level_03.moves.json"


# ---------------------------------------------------------------- broken files
@pytest.mark.parametrize("text", ["", "not json {{{", "[1, 2, 3]"])
def test_load_level_rejects_non_level_json_with_value_error(tmp_path, text):
    p = tmp_path / "bad.json"
    p.write_text(text)
    with pytest.raises(ValueError) as e:
        load_level(p)
    assert not isinstance(e.value, json.JSONDecodeError)  # wrapped, not the raw parser error
    assert "bad.json" in str(e.value)


def test_load_level_missing_file_is_value_error(tmp_path):
    with pytest.raises(ValueError, match="no such file"):
        load_level(tmp_path / "nope.json")


def test_load_level_directory_is_value_error(tmp_path):
    with pytest.raises(ValueError, match="not a file"):
        load_level(tmp_path)


@pytest.mark.parametrize("mutate, field", [
    (lambda d: d.pop("gridWidth"), "gridWidth"),
    (lambda d: d.__setitem__("gridWidth", None), "gridWidth"),
    (lambda d: d["GridBlockDatas"][0].__setitem__("gridPosition", {"x": 2}), "gridPosition"),
    (lambda d: d["GridBlockDatas"][0].__setitem__("shapeOffsets", [{"x": 0, "y": 0}, "junk"]), "shapeOffsets"),
    (lambda d: d["GridBlockDatas"][0].__setitem__("blockColor", 7), "blockColor"),
    (lambda d: d["ExitDatas"][0].__setitem__("direction", 9), "direction"),
    (lambda d: d.__setitem__("GridBlockDatas", {"a": 1}), "GridBlockDatas"),
])
def test_level_from_dict_names_the_broken_field(mutate, field):
    d = json.loads(LEVEL_01.read_text())
    mutate(d)
    with pytest.raises(ValueError, match=field):
        level_from_dict(d)


@pytest.mark.parametrize("value", ["4", 4.5, True])
def test_level_from_dict_does_not_coerce_non_int_values(value):
    # The Level Editor only writes integers; "4", 4.5 or true is a broken file, not a 4.
    d = json.loads(LEVEL_01.read_text())
    d["gridWidth"] = value
    with pytest.raises(ValueError, match="gridWidth"):
        level_from_dict(d)


def test_float_position_is_not_silently_truncated():
    d = json.loads(LEVEL_01.read_text())
    d["GridBlockDatas"][0]["gridPosition"]["x"] = 1.9
    with pytest.raises(ValueError, match="gridPosition"):
        level_from_dict(d)


def test_missing_lists_mean_empty_like_jsonutility():
    lvl = level_from_dict({"gridWidth": 3, "gridHeight": 3})
    assert lvl.blocks == () and lvl.exits == () and lvl.inactive == frozenset()


# ---------------------------------------------------------------- impossible levels
def test_validate_rejects_grid_larger_than_the_editor_allows():
    # LevelEditorWindow: IntSlider("Width"/"Height", 1, 12).
    assert any("12x12" in p for p in validate(make_level(13, 13, [], [])))
    assert validate(make_level(10**30, 5, [], [])) != []


def test_duplicate_offsets_in_one_block_are_not_reported_as_self_overlap():
    problems = validate(make_level(4, 4, [(C.RED, (0, 0), [(1, 0), (1, 0)])], []))
    assert all("overlaps block 0" not in p for p in problems)


# ---------------------------------------------------------------- unsolvable levels
def test_gate_order_quirk_can_make_a_level_unsolvable():
    # The first-listed matching gate always fails for this 1x2 block; the other is never tried.
    exits = [(C.RED, D.LEFT, (1, 1), []), (C.RED, D.TOP, (1, 1), [])]
    assert solve(make_level(3, 2, [(C.RED, (1, 0), [(0, 1)])], exits, inactive=[(0, 1)])) is None
    sol = solve(make_level(3, 2, [(C.RED, (1, 0), [(0, 1)])], list(reversed(exits)), inactive=[(0, 1)]))
    assert sol is not None and sol.min_drags == 1


def test_one_by_one_board_is_unsolvable_because_exit_check_needs_a_cell_change():
    assert solve(make_level(1, 1, [(C.RED, (0, 0), [])], [(C.RED, D.TOP, (0, 0), [])])) is None


def test_gate_narrower_than_block_is_unsolvable():
    assert solve(make_level(3, 1, [(C.RED, (0, 0), [(1, 0)])], [(C.RED, D.TOP, (0, 0), [])])) is None


def test_colour_without_a_gate_is_unsolvable():
    assert solve(make_level(3, 3, [(C.RED, (0, 0), [])], [(C.BLUE, D.TOP, (0, 2), [])])) is None


# ---------------------------------------------------------------- solver limits
def test_cell_limit_stops_a_single_drag_on_a_huge_corridor():
    def alarm(*_):
        raise TimeoutError("solve did not return within 5 s")

    signal.signal(signal.SIGALRM, alarm)
    signal.alarm(5)
    try:
        with pytest.raises(SolverLimitError, match="more than 144 cells"):
            solve(make_level(100_000, 1, [(C.RED, (0, 0), [])], []), max_states=100)
    finally:
        signal.alarm(0)


def test_state_limit_stops_a_search_on_a_real_size_board():
    # Open 12x12 board, three blocks, no gates: unsolvable, and the positions explode.
    lvl = make_level(12, 12, [(C.RED, (0, 0), []), (C.BLUE, (5, 5), []), (C.GREEN, (11, 11), [])], [])
    with pytest.raises(SolverLimitError, match="more than 5 states"):
        solve(lvl, max_states=5)


@pytest.mark.parametrize("bad", [-1, 0, True, 2.5])
def test_bad_max_states_is_a_value_error(bad):
    with pytest.raises(ValueError, match="max_states"):
        solve(make_level(3, 3, [(C.RED, (0, 0), [])], []), max_states=bad)


# ---------------------------------------------------------------- illegal moves
BASE = make_level(4, 3, [(C.RED, (0, 0), []), (C.BLUE, (2, 0), [])],
                  [(C.RED, D.TOP, (0, 2), []), (C.BLUE, D.RIGHT, (3, 0), [])], inactive=[(3, 2)])


@pytest.mark.parametrize("drag, why", [
    (Drag(0, ((0, 0), (1, 0), (2, 0)), False), "through another block"),
    (Drag(1, ((2, 0), (2, 1), (2, 2), (3, 2)), False), "into a hole"),
    (Drag(0, ((0, 0), (0, 1), (0, 2), (1, 2)), False), "passes over the gate cell mid-path"),
    (Drag(0, ((0, 0), (0, 1), (0, 2)), False), "claims stop where the game exits"),
    (Drag(0, ((0, 0), (1, 0)), True, 0), "claims exit where the game only stops"),
    (Drag(0, ((0, 0), (0, 1), (0, 2)), True, 1), "wrong exit_index"),
    (Drag(0, ((0, 0),), True, 0), "1-cell path claiming exit"),
    (Drag(0, ((0, 0), (1, 1)), False), "diagonal step"),
    (Drag(0, ((0, 0), (-1, 0)), False), "off the board"),
    (Drag("0", ((0, 0), (0, 1)), False), "block given as a string"),
    (Drag(0, ((0, 0), (0, 1)), "no"), "exits not a boolean"),
    (Drag(0, ((0, 0), "x"), False), "malformed cell"),
])
def test_replay_rejects_illegal_drags(drag, why):
    with pytest.raises(ReplayError):
        replay(BASE, [drag])


def test_replay_rejects_a_raw_dict_instead_of_a_drag():
    with pytest.raises(ReplayError, match="expected a Drag"):
        replay(BASE, [{"block": 0, "path": [[0, 0], [0, 1]], "exits": False}])


def test_replay_accepts_list_cells():
    # Cells read straight from JSON arrive as [x, y] lists.
    assert replay(BASE, [Drag(0, ([0, 0], [0, 1]), False)])[0] == (0, 1)


def test_move_script_round_trip_and_tampering():
    level = load_level(LEVEL_03)
    drags = script_to_drags(json.loads(MOVES_03.read_text()))
    assert all(p is None for p in replay(level, drags))
    with pytest.raises(ReplayError):
        replay(level, [drags[0], drags[2], drags[1]])  # red cannot pass blue


@pytest.mark.parametrize("script", [
    [], {"drags": "x"}, {"drags": [1]}, {"drags": [{"block": 0, "exits": False}]},
    {"drags": [{"block": 0, "path": [[0, 0.5]], "exits": False}]},
])
def test_malformed_move_scripts_are_value_errors(script):
    with pytest.raises(ValueError):
        script_to_drags(script)


# ---------------------------------------------------------------- command line
def cbj(*args):
    return subprocess.run([sys.executable, "-m", "cbj.cli", *args], cwd=PROJ,
                          capture_output=True, text=True, timeout=60)


@pytest.mark.parametrize("make", [
    lambda t: t / "missing.json",
    lambda t: (t / "broken.json", (t / "broken.json").write_text("{bad"))[0],
    lambda t: t,
])
@pytest.mark.parametrize("command", ["solve", "show"])
def test_cli_bad_level_file_exits_1_with_one_readable_line(tmp_path, make, command):
    r = cbj(command, str(make(tmp_path)))
    assert r.returncode == 1
    assert "Traceback" not in r.stderr
    assert r.stderr.startswith("cbj: ")


def test_cli_unsolvable_level_says_so(tmp_path):
    p = tmp_path / "Level_x.json"
    p.write_text(json.dumps({"gridWidth": 3, "gridHeight": 1, "timerCount": 30, "inactiveCells": [],
                             "GridBlockDatas": [{"gridPosition": {"x": 0, "y": 0}, "blockColor": 3,
                                                 "shapeOffsets": [{"x": 1, "y": 0}]}],
                             "ExitDatas": [{"exitNumber": 0, "gridPosition": {"x": 0, "y": 0}, "requiredColor": 3,
                                            "direction": 2, "shapeOffsets": []}]}))
    r = cbj("solve", str(p))
    assert r.returncode == 1 and "UNSOLVABLE" in r.stdout


def test_cli_table_skips_a_bad_file_and_reports_it(tmp_path):
    (tmp_path / "Level_01.json").write_text(LEVEL_01.read_text())
    (tmp_path / "Level_bad.json").write_text("not json")
    r = cbj("table", str(tmp_path))
    assert "Traceback" not in r.stderr
    assert "Level_01" in r.stdout and "| Level_bad |" in r.stdout and "ERROR" in r.stdout
    assert "Level_bad.json" in r.stderr
    assert r.returncode == 1


def test_cli_table_on_missing_folder_fails(tmp_path):
    r = cbj("table", str(tmp_path / "nope"))
    assert r.returncode == 1 and "no such folder" in r.stderr and "Traceback" not in r.stderr


def test_cli_json_output_to_an_impossible_path_fails_cleanly():
    r = cbj("solve", str(LEVEL_01), "--json", "/dev/null/x.json")
    assert r.returncode == 1 and "Traceback" not in r.stderr and r.stderr.startswith("cbj: ")


def test_cli_check_accepts_the_shipped_script_and_rejects_a_tampered_one(tmp_path):
    ok = cbj("check", str(LEVEL_03), str(MOVES_03))
    assert ok.returncode == 0 and "board cleared" in ok.stdout
    script = json.loads(MOVES_03.read_text())
    script["drags"][1], script["drags"][2] = script["drags"][2], script["drags"][1]
    bad = tmp_path / "tampered.json"
    bad.write_text(json.dumps(script))
    r = cbj("check", str(LEVEL_03), str(bad))
    assert r.returncode == 1 and r.stderr.startswith("cbj: drag 2") and "Traceback" not in r.stderr


def test_cli_check_flags_an_incomplete_script(tmp_path):
    script = json.loads(MOVES_03.read_text())
    script["drags"] = script["drags"][:2]
    short = tmp_path / "short.json"
    short.write_text(json.dumps(script))
    r = cbj("check", str(LEVEL_03), str(short))
    assert r.returncode == 1 and "still on the board" in r.stdout


# ---------------------------------------------------------------- found in the third Fable review
DEEP = "[" * 100_000 + "]" * 100_000


def test_load_level_deeply_nested_json_is_a_value_error_naming_the_file(tmp_path):
    p = tmp_path / "deep.json"
    p.write_text(DEEP)
    with pytest.raises(ValueError, match="deep.json"):
        load_level(p)


def test_cli_solve_deeply_nested_json_has_no_traceback(tmp_path):
    p = tmp_path / "deep.json"
    p.write_text(DEEP)
    r = cbj("solve", str(p))
    assert r.returncode == 1 and "Traceback" not in r.stderr and r.stderr.startswith("cbj: ")


def test_cli_table_keeps_going_past_a_deeply_nested_file(tmp_path):
    (tmp_path / "Level_01.json").write_text(LEVEL_01.read_text())
    (tmp_path / "Level_deep.json").write_text(DEEP)
    r = cbj("table", str(tmp_path))
    assert "Traceback" not in r.stderr
    assert "| Level_01 |" in r.stdout and "| Level_deep |" in r.stdout and "ERROR" in r.stdout
    assert r.returncode == 1


def test_load_level_huge_integer_literal_names_the_file(tmp_path):
    p = tmp_path / "bigint.json"
    p.write_text('{"gridWidth": ' + "9" * 5000 + ', "gridHeight": 3}')
    with pytest.raises(ValueError, match="bigint.json"):
        load_level(p)


@pytest.mark.parametrize("field", ["timerCount", "gridWidth"])
def test_null_int_field_is_not_reported_as_missing(field):
    d = json.loads(LEVEL_01.read_text())
    d[field] = None
    with pytest.raises(ValueError) as e:
        level_from_dict(d)
    assert field in str(e.value) and "missing" not in str(e.value)


def test_cli_check_rejects_a_script_for_a_different_level():
    r = cbj("check", str(LEVEL_01), str(PROJ / "data/solutions/Level_02.moves.json"))
    assert r.returncode == 1 and "Level_02" in r.stderr and "Traceback" not in r.stderr


def test_replay_of_a_non_list_is_a_replay_error():
    with pytest.raises(ReplayError):
        replay(BASE, None)


def test_file_with_a_utf8_byte_order_mark_loads(tmp_path):
    p = tmp_path / "Level_bom.json"
    p.write_bytes(b"\xef\xbb\xbf" + LEVEL_01.read_bytes())
    assert load_level(p).width == 4


def test_cli_table_prints_results_even_if_writing_scripts_fails(tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        r = cbj("table", str(PROJ / "data/levels"), "--scripts", str(locked / "out"))
    finally:
        locked.chmod(0o700)
    assert r.returncode == 1 and "| Level_06 |" in r.stdout and r.stderr.startswith("cbj: ")
