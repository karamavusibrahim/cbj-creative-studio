"""The video's own board (videocells, 2026-10-19), the block-count transforms and the hue-aware slot mapping."""
import json

from cbj import imagecells as IC
from cbj import imageplan as IP
from cbj import videocells as VC
from cbj.level import door_problems, level_from_dict

LEVEL = {"gridWidth": 4, "gridHeight": 6, "timerCount": 60, "inactiveCells": [],
         "GridBlockDatas": [{"gridPosition": {"x": 0, "y": 5}, "blockColor": 2, "shapeOffsets": [{"x": 0, "y": 0}, {"x": 0, "y": -1}]},
                            {"gridPosition": {"x": 2, "y": 5}, "blockColor": 2, "shapeOffsets": [{"x": 0, "y": 0}]},
                            {"gridPosition": {"x": 1, "y": 2}, "blockColor": 5, "shapeOffsets": [{"x": 0, "y": 0}, {"x": 1, "y": 0}]},
                            {"gridPosition": {"x": 3, "y": 1}, "blockColor": 3, "shapeOffsets": [{"x": 0, "y": 0}]},
                            {"gridPosition": {"x": 0, "y": 0}, "blockColor": 3, "shapeOffsets": [{"x": 0, "y": 0}]}],
         "ExitDatas": [{"exitNumber": 0, "requiredColor": 2, "gridPosition": {"x": 0, "y": 0}, "direction": 3, "shapeOffsets": [{"x": 0, "y": 0}]},
                       {"exitNumber": 0, "requiredColor": 5, "gridPosition": {"x": 3, "y": 2}, "direction": 1, "shapeOffsets": [{"x": 0, "y": 0}]},
                       {"exitNumber": 0, "requiredColor": 3, "gridPosition": {"x": 3, "y": 5}, "direction": 2, "shapeOffsets": [{"x": 0, "y": 0}]}]}


def test_copy_asked_words():
    yes = ["use same game design, same scenario just use fewer blocks", "Use this video's board and what it shows on screen",
           "The board exactly as shown but flipped top to bottom", "This exact level with the same colours, but harder",
           "the same board as in the clip, mirrored", "Take this level, remove two blocks", "Rebuild this ad's board in Color Block Jam exactly"]
    no = ["Same kind of level as this video, but easier", "Build the same packed look as this board", "A new level shaped like this cross",
          "Same colours and board shape as this ad", "Give me this video's energy", "a board like this one, 30 seconds",
          "Inspired by this image, with the same level number and clock on screen", "create a similar game in Color Block Jam",
          "a new board of this type"]
    assert all(VC.copy_asked(p) for p in yes), [p for p in yes if not VC.copy_asked(p)]
    assert not any(VC.copy_asked(p) for p in no), [p for p in no if VC.copy_asked(p)]


def test_frame_time_from_the_structure():
    a = {"notes": {"structure": [{"from_s": 0, "to_s": 2.5, "purpose": "hook"}, {"from_s": 2.5, "to_s": 20, "purpose": "gameplay"}]},
         "facts": {"duration_s": 25}}
    assert VC.frame_time(a) == 2.8
    assert VC.frame_time({"notes": {}, "facts": {}}) == VC.FRAME_AFTER_S
    assert VC.frame_time({"notes": {"structure": [{"from_s": 9.9, "to_s": 10, "purpose": "gameplay"}]}, "facts": {"duration_s": 10}}) == 9.8


def test_block_transform_words():
    t = {p: IP.transforms_asked(p) for p in ["fewer blocks", "two more blocks", "half the blocks", "remove one block", "add a block",
                                             "one more block in the way", "one fewer colour", "easier"]}
    assert t["fewer blocks"] == [{"kind": "blocks", "n": -2, "half": False}]
    assert t["two more blocks"] == [{"kind": "blocks", "n": 2, "half": False}]
    assert t["half the blocks"][0]["half"] is True and t["half the blocks"][0]["n"] < 0
    assert t["remove one block"] == [{"kind": "blocks", "n": -1, "half": False}]
    assert t["add a block"] == [{"kind": "blocks", "n": 1, "half": False}]
    assert t["one more block in the way"] == [{"kind": "harder"}]
    assert t["one fewer colour"] == [{"kind": "colours", "n": -1}]
    assert t["easier"] == [{"kind": "easier"}]


def test_remove_blocks_keeps_every_colour_a_door():
    out, note = IC.remove_blocks(LEVEL, 2)
    assert out is not None and len(out["GridBlockDatas"]) == 3 and "2 blocks fewer" in note
    assert door_problems(level_from_dict(out, name="x")) == []
    # the purple pair is the colour's only block: taking it takes its door too
    out, note = IC.remove_blocks(LEVEL, 4)
    assert out is not None and door_problems(level_from_dict(out, name="x")) == []
    assert "and its door" in note
    out, note = IC.remove_blocks(LEVEL, 1, easier=True)
    assert out is not None and note.startswith("easier")


def test_add_blocks():
    out, note = IC.add_blocks(LEVEL, 1)
    assert out is not None and len(out["GridBlockDatas"]) == 6 and "1 block more" in note
    assert door_problems(level_from_dict(out, name="x")) == []


def test_hue_aware_slot_mapping():
    cols = [{"name": "magenta", "rgb": (230, 60, 220)}, {"name": "purple", "rgb": (112, 64, 208)}, {"name": "teal", "rgb": (40, 190, 190)},
            {"name": "green", "rgb": (90, 200, 40)}]
    got = {m["read"]: m["slot"] for m in IP.colour_map(cols)}
    assert got == {"magenta": "Red", "purple": "Purple", "teal": "Blue", "green": "Green"}, got


def test_violet_is_purple_or_blue_to_the_pixels():
    assert IC.hue_family((112, 64, 208)) == ("Blue", "Purple")
    assert IC.hue_family((20, 105, 255)) == ("Blue",)
    assert IC.hue_family((208, 7, 253)) == ("Purple",)


def test_english_detector_keeps_short_english_asks():
    from cbj.workflows.image_guided import is_english
    assert is_english("use same game design, same scenario just use fewer blocks")
    assert not is_english("Bu videodaki tahtayı aynen al ama sağ-sol ayna görüntüsü olsun")


def test_split_hues_names_the_yellow_blocks_among_the_orange():
    parsed = {"blocks": [{"colour": "orange", "cells": [(0, 0), (1, 0)]}, {"colour": "orange", "cells": [(3, 3)]}, {"colour": "red", "cells": [(5, 5)]}],
              "holes": set(), "empty": set(), "gates": []}
    samples = {(0, 0): {"rgb": (246, 181, 49)}, (1, 0): {"rgb": (246, 181, 49)}, (3, 3): {"rgb": (240, 128, 48)}, (5, 5): {"rgb": (200, 30, 40)}}
    out = IC.split_hues(parsed, samples)
    assert [b["colour"] for b in out["blocks"]] == ["yellow", "orange", "red"], out["blocks"]
    assert any("two colours read as one name" in n for n in out["notes"])


def test_verify_doubts_fewer_colour_names_than_the_board_read():
    parsed = {"blocks": [{"colour": "orange", "cells": [(0, 0)]}, {"colour": "red", "cells": [(1, 1)]}], "holes": set(), "empty": set(),
              "gates": [{"colour": "orange", "cells": [(0, 0)], "direction": "up"}, {"colour": "red", "cells": [(1, 1)], "direction": "up"}]}
    samples = {(0, 0): {"rgb": (240, 128, 48), "sat": 0.8, "block": True, "family": ("Orange",)}, (1, 1): {"rgb": (200, 30, 40), "sat": 0.8, "block": True, "family": ("Red",)}}
    ver = IC.verify(parsed, samples, 2, 2, expect_colours=3)
    assert any("names only 2" in d for d in ver["doubts"])


def test_bubbles_and_counters_are_not_blocks():
    ans = {"blocks": [{"colour": "red", "cells": ["A1", "B1"]}, {"colour": "clear bubble (5)", "cells": ["C1"]}, {"colour": "ice cover", "cells": ["D2", "D3"]}],
           "holes": [], "empty": ["A2"], "gates": [{"colour": "red", "cells": ["A1"], "direction": "up"}]}
    out = IC.parse_answer(ans, 4, 4)
    assert [b["colour"] for b in out["blocks"]] == ["red"]
    assert IC.parse_cell("C1", 4, 4) in out["empty"] and IC.parse_cell("D2", 4, 4) in out["empty"]
    assert any("not blocks of this game" in n for n in out.get("notes") or [])


def test_copy_asked_board_from_this_video_without_as_it_is():
    # V2's fourth run (2026-10-19 13:18): the translation dropped "as it is" and the copy was missed
    assert VC.copy_asked("Take the board from this video exactly, but mirror it left to right and add one more block that blocks the path.")
    assert VC.copy_asked("Use the board in this clip, mirrored top to bottom.")
    assert not VC.copy_asked("Use a board inspired by the board in this video, with more blocks.")
    assert not VC.copy_asked("Make a level similar to the board in this video.")
