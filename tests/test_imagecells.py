"""The board read cell by cell from a picture (imagecells, 2026-10-19), the copy in the plan (imageplan.copy_spec), the
rows that judge it (imageaudit) and the loop rules E2/E3 (IMAGE-GUIDED-EVAL-CHECKS-2026-10-19)."""
import copy
import json

import pytest

from cbj import brief as B
from cbj import imageaudit, imagecells as IC, imageplan as IP


def small_level():
    """A 4x4 board: a red 1x2 bar on the left with a red gate on the left edge, a blue 2x1 at the bottom right with a blue
    gate at the bottom, one hole cell."""
    return {"gridWidth": 4, "gridHeight": 4, "timerCount": 60, "inactiveCells": [{"x": 3, "y": 3}],
            "GridBlockDatas": [{"gridPosition": {"x": 0, "y": 2}, "blockColor": 3, "shapeOffsets": [{"x": 0, "y": 0}, {"x": 0, "y": -1}]},
                               {"gridPosition": {"x": 2, "y": 0}, "blockColor": 2, "shapeOffsets": [{"x": 0, "y": 0}, {"x": 1, "y": 0}]},
                               {"gridPosition": {"x": 1, "y": 3}, "blockColor": 3, "shapeOffsets": [{"x": 0, "y": 0}]}],
            "ExitDatas": [{"exitNumber": 0, "requiredColor": 3, "gridPosition": {"x": 0, "y": 2}, "direction": 0, "shapeOffsets": [{"x": 0, "y": 0}, {"x": 0, "y": -1}]},
                          {"exitNumber": 0, "requiredColor": 2, "gridPosition": {"x": 2, "y": 0}, "direction": 3, "shapeOffsets": [{"x": 0, "y": 0}, {"x": 1, "y": 0}]},
                          {"exitNumber": 0, "requiredColor": 3, "gridPosition": {"x": 1, "y": 3}, "direction": 2, "shapeOffsets": [{"x": 0, "y": 0}]}]}


def test_cell_names_round_trip():
    assert IC.cell_name(1, 2) == "B3"
    assert IC.parse_cell("B3", 8, 8) == (1, 2)
    assert IC.parse_cell("Z9", 8, 8) is None


def test_corners_are_put_in_order_whatever_the_reader_called_them():
    flipped = {"top_left": [0.1, 0.9], "top_right": [0.9, 0.9], "bottom_right": [0.95, 0.1], "bottom_left": [0.05, 0.1]}
    q = IC.ordered_corners(flipped, 100, 100)
    assert q["top_left"][1] < q["bottom_left"][1] and q["top_left"][0] < q["top_right"][0]
    assert IC.ordered_corners({"top_left": [0.1, 0.1]}, 100, 100) is None


def test_parse_answer_flags_double_and_missing_cells():
    ans = {"blocks": [{"colour": "red", "cells": ["A1", "A2"]}, {"colour": "blue", "cells": ["A2", "B2"]}], "holes": ["B1"], "empty": [],
           "gates": [{"colour": "red", "cells": ["A1"], "direction": "left"}, {"colour": "blue", "cells": ["B2"], "direction": "sideways"}]}
    p = IC.parse_answer(ans, 2, 2)
    assert any("A2 is in two pieces" in x for x in p["problems"])
    assert not any("not accounted" in x for x in p["problems"])  # A1, A2, B2 are pieces, B1 a hole
    assert len(p["gates"]) == 1 and any("unreadable" in x for x in p["problems"])


def test_verify_doubts_an_empty_cell_that_is_block_coloured_but_not_a_hole():
    parsed = IC.parse_answer({"blocks": [{"colour": "red", "cells": ["A1"]}], "holes": ["B1"], "empty": ["A2", "B2"],
                              "gates": [{"colour": "red", "cells": ["A1"], "direction": "left"}]}, 2, 2)
    samples = {(0, 0): {"rgb": (240, 50, 40), "sat": 0.83, "block": True, "family": ("Red",)}, (1, 0): {"rgb": (40, 180, 200), "sat": 0.8, "block": True, "family": ("Blue",)},
               (0, 1): {"rgb": (90, 100, 140), "sat": 0.36, "block": False, "family": None}, (1, 1): {"rgb": (20, 100, 230), "sat": 0.91, "block": True, "family": ("Blue",)}}
    v = IC.verify(parsed, samples, 2, 2)
    assert any(x.startswith("B2: read as empty") for x in v["doubts"])
    assert not any(x.startswith("B1") for x in v["doubts"])  # a hole may show anything


def test_to_level_uses_the_games_coordinates_and_solves():
    ans = {"blocks": [{"colour": "red", "cells": ["A1", "A2"]}], "holes": [], "empty": ["B1", "B2"],
           "gates": [{"colour": "red", "cells": ["A1"], "direction": "up"}]}
    parsed = IC.parse_answer(ans, 2, 2)
    lvl = IC.to_level(parsed, 2, 2, {"red": "Red"})
    blk = lvl["GridBlockDatas"][0]
    assert blk["gridPosition"] == {"x": 0, "y": 1} and {"x": 0, "y": -1} in blk["shapeOffsets"]  # A1 is the top row: y = 1
    assert lvl["ExitDatas"][0]["direction"] == 2  # up = TOP (+y)
    ok, how = IC.solvable(lvl)
    assert ok and how.endswith("drags")


def test_mirror_twice_is_the_same_board_and_each_mirror_solves():
    d = small_level()
    assert IC.solvable(d)[0]
    m = IC.mirror(d, "lr")
    assert IC.solvable(m)[0] and not IC.same_board(d, m)[0]
    assert IC.same_board(d, IC.mirror(m, "lr"))[0]
    t = IC.mirror(d, "tb")
    assert IC.solvable(t)[0] and IC.same_board(d, IC.mirror(t, "tb"))[0]


def test_recolour_changes_blocks_and_gates():
    d = IC.recolour(small_level(), "Red", "Yellow")
    assert IC.colours_of(d) == ["Yellow", "Blue"]
    assert {e["requiredColor"] for e in d["ExitDatas"]} == {1, 2}
    assert IC.solvable(d)[0]


def test_add_and_remove_colour_keep_the_board_solvable():
    d = small_level()
    d2, note = IC.add_colour(d, "Green")
    assert d2 is not None and "Green" in IC.colours_of(d2) and len(d2["ExitDatas"]) == len(d["ExitDatas"]) + 1 and "solves" in note
    assert len(IC.colours_of(d2)) == 3
    d3, note = IC.remove_colour(d2)
    assert d3 is not None and len(IC.colours_of(d3)) == 2 and IC.solvable(d3)[0]
    assert IC.remove_colour(d)[0] is None  # two colours: one fewer is refused with the reason


def test_transforms_asked_reads_the_words():
    assert IP.transforms_asked("create a similar game concept, just use one more color") == [{"kind": "colours", "n": 1}]
    assert IP.transforms_asked("make the yellow blocks blue and add one more colour") == [{"kind": "recolour", "from": "Yellow", "to": "Blue"}, {"kind": "colours", "n": 1}]
    assert IP.transforms_asked("flipped top to bottom") == [{"kind": "mirror", "axis": "tb"}]
    assert IP.transforms_asked("the red blocks become pink") == []  # pink is a repaint, not a game colour


def test_copy_conflicts_names_a_new_board_or_a_stated_part():
    d = small_level()
    assert IP.copy_conflicts("A new level shaped like this cross, a different arrangement", d)
    assert IP.copy_conflicts("Take the board from this screenshot but with 6 blocks", d)
    assert IP.copy_conflicts("this board as a 6x6", d)
    assert IP.copy_conflicts("Recreate this exact level, the same blocks and gates", d) == []
    assert IP.copy_conflicts("Use this board but make the red blocks green", d) == []


def test_copy_spec_sets_the_picture_source_and_applies_the_asked_change(monkeypatch, tmp_path):
    real_save = IC.save
    monkeypatch.setattr(IC, "save", lambda d, folder=None: real_save(d, tmp_path))
    reading = {"file": "pic.png", "board": {"columns": 4, "rows": 4, "blocks": 3}, "notes": {"is_color_block_jam": True},
               "cells": {"level": small_level(), "verify": {"doubts": [], "checked": 16}, "asks": 2}}
    decision = {"board": {"named": [], "all": True}, "roles": ["board"], "style": None, "asset": False, "modify": False}
    cs = IP.copy_spec("create a similar game concept, just use one more color", B.default_brief(), reading, decision)
    assert cs["set"]["source"] == "picture" and cs["set"]["file"].startswith("picture_") and len(cs["set"]["colours"]) == 3
    assert cs["board"]["copied"] and cs["board"]["transforms"][0]["kind"] == "colours"
    cs2 = IP.copy_spec("A new level like this one, a different arrangement", B.default_brief(), reading, decision)
    assert cs2["skipped"]
    assert IP.copy_spec("Use this board", B.default_brief(), {"file": "pic.png", "cells": {"error": "x"}}, decision) is None


def test_brief_check_leaves_a_picture_level_as_it_is():
    b = B.default_brief()
    b["level"].update(source="picture", file="picture_0123456789ab.json", width=12, height=12, blocks=14)
    out = B.check(b, {}, set())
    assert (out["level"]["width"], out["level"]["height"], out["level"]["blocks"]) == (12, 12, 14)


def test_resolve_level_plays_the_pictures_file(tmp_path, monkeypatch):
    from cbj import studio
    lv = IC.save(small_level(), studio.STUDIO / "levels")
    try:
        b = B.default_brief()
        b["level"].update(source="picture", file=lv.name)
        path, why = studio.resolve_level(b, studio.Log(lambda ln: None))
        assert path == lv and "cell by cell" in why
    finally:
        lv.unlink(missing_ok=True)


def test_copied_board_rows_judge_identity_and_the_transform(tmp_path):
    pic = small_level()
    want, note = IC.add_colour(pic, "Green")
    prov = {"board": {"copied": True, "level": want, "picture_level": pic, "text": IC.describe(pic), "verify": {"doubts": [], "checked": 16, "asks": 2, "solve": "3 drags"},
                      "transforms": [{"kind": "colours", "n": 1, "note": note}], "transforms_failed": []}}
    (tmp_path / "level.json").write_text(json.dumps(want))
    rows = {r["check"]: r for r in imageaudit.copied_board_rows("one more colour", prov, tmp_path)}
    assert rows["Image: the board is the picture's"]["status"] == "pass"
    assert rows["Image: more or fewer colours than the picture"]["status"] == "pass"
    (tmp_path / "level.json").write_text(json.dumps(pic))  # the made level forgot the change
    rows = {r["check"]: r for r in imageaudit.copied_board_rows("one more colour", prov, tmp_path)}
    assert rows["Image: the board is the picture's"]["status"] == "failed"
    assert rows["Image: more or fewer colours than the picture"]["status"] == "failed"


def test_coverage_rows_name_an_ask_without_a_row():
    checks = [{"check": "Asked: length", "status": "pass"}, {"check": "Image: the board's colours", "status": "pass"}]
    rows = imageaudit.coverage_rows("create a similar game concept, just use one more color, 30 seconds", {}, checks)
    assert rows[0]["check"] == "Coverage: not measured" and "colour" in rows[0]["detail"]
    checks.append({"check": "Image: more or fewer colours than the picture", "status": "pass"})
    rows = imageaudit.coverage_rows("create a similar game concept, just use one more color, 30 seconds", {}, checks)
    assert rows[0]["check"] == "Coverage: every ask has a measured row"


def test_the_loop_keeps_a_viewer_point_on_an_asked_control():
    from cbj.workflows import image_guided as W
    b = B.default_brief()
    b["level"]["colours"] = ["Yellow", "Orange", "Red"]
    v = {"brief": b, "checks": [{"check": "Image: the board's colours", "status": "pass", "detail": ""},
                                {"check": "Coverage: not measured", "status": "info", "detail": "NOT MEASURED: +1 colour(s) against the picture"}],
         "review": {"overall": "ship", "match": [{"control": "the level's type or structure", "verdict": "partial", "seen": "no fourth colour"}],
                    "fixes": ["Add a fourth block colour"], "error": None}}
    prompt = "a level with yellow, orange and red blocks and one more colour"
    text = W.feedback(prompt, copy.deepcopy(v))
    assert text and "no fourth colour" in text  # an ask without a row: the viewer's point stands (E2)
    assert W.loop_verdict(prompt, v) == "fix"
    v2 = copy.deepcopy(v)
    v2["checks"][1] = {"check": "Coverage: every ask has a measured row", "status": "info", "detail": "..."}
    v2["checks"].append({"check": "Image: more or fewer colours than the picture", "status": "pass", "detail": ""})
    assert W.feedback(prompt, copy.deepcopy(v2)) is None  # every ask measured and passing: the viewer's taste starts nothing
    assert W.loop_verdict(prompt, v2) == "ship"


def test_a_thin_wall_line_becomes_an_inserted_column_of_wall_cells_with_its_gap():
    ans = {"blocks": [{"colour": "yellow", "cells": ["A1", "B1", "C1", "D1"]}, {"colour": "blue", "cells": ["A3"]}],
           "holes": [], "empty": ["A2", "B2", "C2", "D2", "B3", "C3", "D3"],
           "gates": [{"colour": "yellow", "cells": ["A1", "B1"], "direction": "up"}, {"colour": "yellow", "cells": ["C1", "D1"], "direction": "up"},
                     {"colour": "blue", "cells": ["A3"], "direction": "left"}],
           "wall_lines": [{"between_columns": ["B", "C"], "rows": ["1", "2"]}]}
    p = IC.parse_answer(ans, 4, 3)
    assert len(p["blocks"]) == 3  # the yellow bar is two blocks, one each side of the wall
    lvl = IC.to_level(p, 4, 3, {"yellow": "Yellow", "blue": "Blue"})
    assert lvl["gridWidth"] == 5 and lvl["gridHeight"] == 3
    holes = {(c["x"], c["y"]) for c in lvl["inactiveCells"]}
    assert holes == {(2, 2), (2, 1)}  # the wall runs at rows 1-2 (the top two), open at row 3
    assert IC.walls_note(p).startswith("the thin wall between columns B and C (rows 1-2)")
    assert IC.solvable(lvl)[0]


def test_a_picture_level_name_outside_the_tools_files_is_refused():
    from cbj import studio
    b = B.default_brief()
    b["level"].update(source="picture", file="../../.env")
    out = B.check(b, {}, set())
    assert out["level"]["source"] == "generate" and out["level"]["file"] is None
    from cbj import studio
    import re
    assert re.fullmatch(r"picture_[0-9a-f]{12}\.json", "picture_0123456789ab.json")
    assert studio.STUDIO / "levels" == (studio.STUDIO / "levels")  # the resolver confines the file to this folder (studio.resolve_level)


def test_english_detection_and_translation_for_the_parsers():
    from cbj.workflows import image_guided as W
    assert W.is_english("create a similar game concept, just use one more color")
    assert not W.is_english("Bu tahtayı aynen kullan ama bir renk eksilt; şeker görünümünü koru.")

    class Fake:
        def complete(self, system, user, schema):
            assert "Translate:" in user
            return json.dumps({"english": "Use this board as it is but one colour fewer; keep the candy look."})
    out = W.english_prompt("Bu tahtayı aynen kullan ama bir renk eksilt; şeker görünümünü koru.", Fake())
    assert out.startswith("Use this board") and IP.transforms_asked(out) == [{"kind": "colours", "n": -1}]
    assert W.english_prompt("a plain English ask with the board", Fake()) == "a plain English ask with the board"


def test_a_screenshot_sized_picture_with_no_placement_words_is_a_reference(tmp_path, monkeypatch):
    from PIL import Image
    from cbj import studio
    from cbj.workflows import image_guided as W
    big, small = tmp_path / "shot.png", tmp_path / "logo.png"
    Image.new("RGB", (768, 1376), (200, 220, 240)).save(big)
    Image.new("RGB", (120, 60), (255, 0, 0)).save(small)
    monkeypatch.setattr(studio, "uploads", lambda: {"shot.png": big, "logo.png": small})
    monkeypatch.setattr(studio, "videos", lambda: set())
    assert W.applies("Use the game's own look, but the red blocks become pink.", ["shot.png"])
    assert W.applies("Bu tahtayı aynen kullan ama bir renk eksilt.", ["shot.png"])
    assert not W.applies("A clean win with our logo on the end card", ["logo.png"])  # small, and placement words
    assert not W.applies("A clean win in 30 seconds", ["logo.png"])  # a small picture without words: placed, as before


def test_rows_run_for_a_copied_board_and_mirrored_is_not_a_symmetric_ask(tmp_path):
    pic = small_level()
    (tmp_path / "level.json").write_text(json.dumps(IC.mirror(pic, "lr")))
    (tmp_path / "parts.json").write_text(json.dumps({"parts": []}))
    prov = {"kind": "image", "file": "none.png", "roles": ["board"], "board": {"copied": True, "level": IC.mirror(pic, "lr"), "picture_level": pic,
            "text": IC.describe(pic), "verify": {"doubts": [], "checked": 16, "asks": 2}, "transforms": [{"kind": "mirror", "axis": "lr", "note": "mirrored"}],
            "transforms_failed": [], "evidence": {}}, "reader": {}, "plan": {}, "taken": [], "not_taken": []}
    brief = B.default_brief()
    brief["reference"] = prov
    rows = {r["check"]: r for r in imageaudit.rows("the same board mirrored left to right", brief, {}, tmp_path)}
    assert rows["Image: the board is the picture's"]["status"] == "pass" and rows["Image: the board mirrored"]["status"] == "pass"
    out = imageaudit.rejudge("the same board mirrored left to right", brief, [{"check": "Asked: symmetric board", "status": "failed", "detail": "x"}])
    assert out[0]["status"] == "info"


def test_a_gate_named_magenta_belongs_to_the_purple_blocks():
    ans = {"blocks": [{"colour": "magenta", "cells": ["A1"]}, {"colour": "red", "cells": ["B2"]}], "holes": [], "empty": ["B1", "A2"],
           "gates": [{"colour": "purple", "cells": ["A1"], "direction": "up"}, {"colour": "red", "cells": ["B2"], "direction": "down"}]}
    p = IC.parse_answer(ans, 2, 2)
    assert p["gates"][0]["colour"] == "magenta"


def test_harder_adds_one_block_in_the_way_and_is_measured():
    d = small_level()
    assert IP.transforms_asked("This exact level but harder: one more block in the way") == [{"kind": "harder"}]
    d2, note = IC.add_blocker(d)
    assert d2 is not None and len(d2["GridBlockDatas"]) == len(d["GridBlockDatas"]) + 1 and IC.min_drags(d2) > IC.min_drags(d)
    assert "in the way" in note


def test_two_shades_of_one_name_become_two_colours():
    parsed = {"blocks": [{"colour": "green", "cells": [(0, 0)]}, {"colour": "green", "cells": [(1, 0)]}, {"colour": "red", "cells": [(0, 1)]}],
              "holes": set(), "empty": set(), "gates": [], "problems": []}
    samples = {(0, 0): {"rgb": (24, 89, 37), "sat": 0.7, "block": True, "family": ("Green", "DarkGreen")},
               (1, 0): {"rgb": (80, 244, 110), "sat": 0.7, "block": True, "family": ("Green", "DarkGreen")},
               (0, 1): {"rgb": (240, 40, 30), "sat": 0.9, "block": True, "family": ("Red",)}}
    out = IC.split_shades(parsed, samples)
    assert [b["colour"] for b in out["blocks"]] == ["dark green", "green", "red"]
    slots = IC.slot_map(out, samples)
    assert slots["dark green"] == "DarkGreen" and slots["green"] == "Green"


def test_the_end_card_row_flags_padding(tmp_path):
    (tmp_path / "parts.json").write_text(json.dumps({"duration_s": 40.0, "parts": [{"id": "play", "from_s": 1.0, "to_s": 22.0}, {"id": "end", "from_s": 24.5, "to_s": 40.0}]}))
    r = imageaudit.end_card_row(tmp_path)
    assert r["status"] == "failed" and "15.5 s" in r["detail"]
    (tmp_path / "parts.json").write_text(json.dumps({"duration_s": 30.0, "parts": [{"id": "play", "from_s": 1.0, "to_s": 22.0}, {"id": "end", "from_s": 25.0, "to_s": 30.0}]}))
    assert imageaudit.end_card_row(tmp_path)["status"] == "pass"
