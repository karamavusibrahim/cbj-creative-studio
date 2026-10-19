"""The game's door and colour rules as measured rows (2026-10-19): level.door_problems / fits_door, audit.door_rows,
audit.colour_rows. Before these, "Rules: the level" claimed "every block has a door of its colour" without a check."""
import copy
import json
from pathlib import Path

import pytest

from cbj import audit
from cbj import brief as B
from cbj.level import door_problems, fits_door, level_from_dict, load_level, validate

SHIPPED = sorted(Path("/Users/ibrahimkaramavus/rollic-case/CBJ/Assets/Levels").glob("Level_*.json"))


def small(blocks, exits, w=4, h=4, inactive=()):
    return level_from_dict({"gridWidth": w, "gridHeight": h, "timerCount": 60, "inactiveCells": [{"x": x, "y": y} for x, y in inactive],
                            "GridBlockDatas": [{"gridPosition": {"x": x, "y": y}, "blockColor": c,
                                                "shapeOffsets": [{"x": ox, "y": oy} for ox, oy in offs]} for x, y, c, offs in blocks],
                            "ExitDatas": [{"exitNumber": 0, "requiredColor": c, "gridPosition": {"x": x, "y": y}, "direction": d,
                                           "shapeOffsets": [{"x": ox, "y": oy} for ox, oy in offs]} for x, y, c, d, offs in exits]})


def test_shipped_levels_keep_the_door_rules():
    assert SHIPPED, "the Unity project's levels"
    for f in SHIPPED:
        assert door_problems(load_level(f)) == [], f.name


def test_block_colour_without_a_door_and_door_without_a_block():
    lv = small([(1, 1, 2, [(0, 0)]), (2, 2, 0, [(0, 0)])],  # a blue 1x1 and a green 1x1
               [(0, 0, 2, 3, [(0, 0)]), (3, 3, 1, 2, [(0, 0)])])  # a blue door at the bottom, a YELLOW door at the top
    assert validate(lv) == []  # Unity loads it: validate() never saw the problem
    p = door_problems(lv)
    assert any("green block has no door" in x for x in p)
    assert any("yellow door with no yellow block" in x for x in p)


def test_a_wide_block_needs_a_wide_door():
    # a 2-wide blue bar with a one-cell blue door at the bottom: it can never leave (every cell must be in the door's columns)
    lv = small([(1, 2, 2, [(0, 0), (1, 0)])], [(0, 0, 2, 3, [(0, 0)])])
    assert any("fits through no blue door" in x for x in door_problems(lv))
    # the same bar with a two-cell door fits
    ok = small([(1, 2, 2, [(0, 0), (1, 0)])], [(0, 0, 2, 3, [(0, 0), (1, 0)])])
    assert door_problems(ok) == []
    assert fits_door(ok, ok.blocks[0], ok.exits[0])
    # and a one-cell door on the LEFT takes the bar lengthwise
    side = small([(1, 2, 2, [(0, 0), (1, 0)])], [(0, 0, 2, 0, [(0, 0)])])
    assert door_problems(side) == []


def test_door_rows_pass_and_fail(tmp_path):
    lv = small([(1, 1, 2, [(0, 0)])], [(0, 0, 2, 3, [(0, 0)])])
    rows = audit.door_rows(lv)
    assert [r["check"] for r in rows] == ["Rules: doors and colours"]
    assert rows[0]["status"] == "pass" and "blue 1 door" in rows[0]["detail"]
    bad = small([(1, 1, 2, [(0, 0)])], [(0, 0, 3, 3, [(0, 0)])])  # the only door is red
    r = audit.door_rows(bad)[0]
    assert r["status"] == "failed" and r["where"] == "level" and "blue block has no door" in r["detail"]


def _brief(theme="game", blocks=()):
    b = B.default_brief()
    b["visuals"]["theme"] = theme
    b["visuals"]["blocks"] = list(blocks)
    return b


def test_colour_rows_catch_two_blues(tmp_path):
    lv = small([(1, 1, 2, [(0, 0)]), (2, 2, 5, [(0, 0)])], [(0, 0, 2, 3, [(0, 0)]), (3, 3, 5, 2, [(0, 0)])])
    from cbj.level import level_to_dict
    path = tmp_path / "lv.json"
    path.write_text(json.dumps(level_to_dict(lv)))
    ok = audit.colour_rows(path, _brief())
    assert ok[0]["status"] == "pass" and "blue" in ok[0]["detail"] and "purple" in ok[0]["detail"]
    two_blues = _brief(blocks=[{"slot": "Purple", "hex": "#2A74FF", "name": "blue"}])
    r = audit.colour_rows(path, two_blues)[0]
    assert r["status"] == "failed" and r["where"] == "plan"
    assert "only" in r["detail"] and "both called 'blue'" in r["detail"]


def test_every_theme_palette_keeps_the_slots_apart():
    for theme, (pal, _) in B.PALETTES.items():
        shown = {s: pal.get(s, (B.GAME_HEX[s],))[0] for s in B.COLOURS}
        for i, a in enumerate(B.COLOURS):
            for b in B.COLOURS[i + 1:]:
                assert B.colour_distance(shown[a], shown[b]) >= B.MIN_COLOUR_DISTANCE, (theme, a, b)


def test_rules_level_row_no_longer_claims_the_door_rule(tmp_path):
    lv = small([(1, 1, 2, [(0, 0)])], [(0, 0, 3, 3, [(0, 0)])])  # loads in Unity, breaks the door rule
    from cbj.level import level_to_dict
    path = tmp_path / "lv.json"
    path.write_text(json.dumps(level_to_dict(lv)))
    rows = audit.rules_rows(path, tmp_path)  # no result.json: the level rows only
    by = {r["check"]: r for r in rows}
    assert by["Rules: the level"]["status"] == "pass" and "door of its colour" not in by["Rules: the level"]["detail"]
    assert by["Rules: doors and colours"]["status"] == "failed"


def test_cliffhanger_keeps_an_asked_clock():
    """2026-10-19: "keep its clock" on a trailer that stops mid-level at 00:39 from 01:05."""
    b = B.default_brief()
    b["gameplay"]["ending"], b["gameplay"]["timer_s"] = "cliffhanger", 65
    out = B.check(b, {}, [])
    assert out["gameplay"]["timer_s"] == 65, [a for a in out.get("adjustments") or [] if "clock" in str(a)]
    b2 = B.default_brief()
    b2["gameplay"]["ending"], b2["gameplay"]["timer_s"] = "near_fail", 65
    out2 = B.check(b2, {}, [])
    assert out2["gameplay"]["timer_s"] is None


def test_a_time_out_says_its_one_block_limit():
    b = B.default_brief()
    b["gameplay"]["ending"], b["gameplay"]["blocks_left"] = "time_out", 2
    out = B.check(b, {}, [])
    assert out["gameplay"]["blocks_left"] is None
    assert any("exactly one block" in (r.get("why") or "") for r in out["controls"]), [r.get("why") for r in out["controls"]]
