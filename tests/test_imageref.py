"""Image-guided creative generation (case p.6): the role of an attached image (style, composition,
asset, modify) and what each role takes from it: a measured style kit (background, captions,
blocks by hue), a board read in the picture as a level spec, through the planner into the brief."""
from pathlib import Path

import pytest
from PIL import Image

from cbj import brief as B
from cbj import imageref as IR
from cbj import reference

from test_text_to_creative import FakeModel, raw_brief


def _image(path: Path, colours: list[tuple], size=(120, 120)) -> Path:
    """Vertical bands of the given colours: a palette the measure reads back."""
    im = Image.new("RGB", size)
    w = size[0] // len(colours)
    for i, c in enumerate(colours):
        for x in range(i * w, size[0] if i == len(colours) - 1 else (i + 1) * w):
            for y in range(size[1]):
                im.putpixel((x, y), c)
    im.save(path)
    return path


@pytest.mark.parametrize("prompt, kind, want", [
    ("Create a Color Block Jam creative inspired by this image.", "photo", "style"),
    ("Use the colours from this picture for the background and the captions.", "illustration", "style"),
    ("I want to create a game like that.", "game screenshot", "composition"),
    ("Make a level like this board, medium difficulty.", "game screenshot", "composition"),
    ("Put our logo (attached) in the top left corner.", "logo", "asset"),
    ("Use this object instead of the current obstacle.", "illustration", "modify"),
    ("Apply this texture to the blue block.", "pattern", "modify"),
    ("A game like that, same style.", "photo", "style"),  # not a board: the look is what can be taken
])
def test_the_role_of_an_image(prompt, kind, want):
    a = {"file": "x.png", "kind": "image", "notes": {"kind": kind, "board": {"is_puzzle_board": kind == "game screenshot"}}}
    assert IR.role(prompt, a)["primary"] == want


def test_style_kit_measures_background_captions_and_blocks(tmp_path):
    img = _image(tmp_path / "pastel.png", [(243, 238, 255), (230, 215, 250), (255, 79, 139), (20, 150, 255), (255, 204, 4), (60, 200, 90)])
    a = {"file": "pastel.png", "kind": "image", "palette": reference.palette(img), "notes": {}}
    kit = IR.style_kit(a, "inspired by this image: use its palette for the background, the captions and the blocks")
    assert len(kit["background"]) == 2 and IR.luminance(kit["background"][0]) >= IR.luminance(kit["background"][1])
    assert IR.contrast(kit["caption_fill"], kit["background"][0]) >= 3.0
    slots = {b["slot"] for b in kit["blocks"]}
    assert {"Red", "Blue", "Yellow"} <= slots or {"Red", "Blue", "Green"} <= slots
    assert all(b["name"] for b in kit["blocks"]) and kit["theme"] == "custom"
    kit2 = IR.style_kit(a, "inspired by this image, keep the game's own block colours")
    assert kit2["blocks"] == [] and kit2["background"] == kit["background"]
    dark = _image(tmp_path / "dark.png", [(10, 10, 40), (30, 0, 60), (255, 40, 120)])
    kd = IR.style_kit({"file": "dark.png", "kind": "image", "palette": reference.palette(dark), "notes": {}}, "this look")
    assert kd["dark"] and kd["caption_fill"] == "#FFFFFF" and IR.luminance(kd["background"][1]) < 0.2


def test_board_facts_become_a_level_spec():
    a = {"file": "shot.png", "kind": "image", "notes": {"kind": "game screenshot", "board": {
        "is_puzzle_board": True, "grid_cols": 7, "grid_rows": 8, "block_count": 8, "block_colours": ["red", "blue", "lime", "gold"],
        "walls": 2, "doors_visible": True, "crowded": "packed", "symmetric": False}}}
    f = IR.board_facts(a)
    assert (f["width"], f["height"], f["blocks"]) == (7, 8, 8) and f["colours"] == ["Red", "Blue", "Green", "Yellow"]
    assert f["style"] == ["packed"] and f["shape"] == "holes" and "7x8" in f["note"]
    assert IR.board_facts({"notes": {"board": {"is_puzzle_board": False}}}) is None


def test_the_planner_applies_the_style_kit_and_the_board(tmp_path):
    from cbj import planner
    img = _image(tmp_path / "ref.png", [(250, 240, 230), (240, 220, 200), (220, 40, 60), (30, 90, 220), (250, 200, 30)])
    pal = reference.palette(img)
    style_analysis = {"file": "ref.png", "kind": "image", "palette": pal, "notes": {"kind": "illustration", "subject": "a warm scene",
                                                                                    "mood": "warm", "board": {"is_puzzle_board": False}}}
    raw = raw_brief()
    raw["controls"] = [{"control": c, "asked": None, "plan": "", "status": "default", "why": None} for c in B.CONTROLS]
    b = planner.plan("Create a Color Block Jam creative inspired by this image: use its colours for the background, the captions and the blocks.",
                     client=FakeModel(raw), uploads={"ref.png": img}, references={"ref.png": img}, analyser=lambda p: dict(style_analysis))
    assert b["visuals"]["background"] and b["visuals"]["caption_fill"] and b["visuals"]["theme"] == "custom"
    assert b["visuals"]["blocks"], b["visuals"]
    assert "visuals.background" in b["changed"] and "visuals.colours" in b["changed"]
    assert b["planner"]["references"][0]["role"]["primary"] == "style"
    assert any("style reference" in a and "background" in a for a in b["assumptions"])
    assert b["assets"] == []  # read, not placed
    board_analysis = {"file": "ref.png", "kind": "image", "palette": pal, "notes": {"kind": "game screenshot", "subject": "a block puzzle",
                      "board": {"is_puzzle_board": True, "grid_cols": 6, "grid_rows": 6, "block_count": 5, "block_colours": ["red", "green", "blue"],
                                "walls": 0, "crowded": "spacious", "symmetric": False}}}
    b2 = planner.plan("I want to create a game like that, 30 seconds.", client=FakeModel(raw), uploads={"ref.png": img},
                      references={"ref.png": img}, analyser=lambda p: dict(board_analysis))
    lv = b2["level"]
    assert (lv["source"], lv["width"], lv["height"], lv["blocks"], lv["colours"], lv["style"]) == ("generate", 6, 6, 5, ["Red", "Green", "Blue"], ["spacious"])
    assert b2["planner"]["references"][0]["role"]["primary"] == "composition"
    assert any("board reference" in a for a in b2["assumptions"])
    assert "image_url" not in str(b2["assets"])


def test_reference_words_cover_design_transfer():
    assert reference.is_reference_prompt("I want to create a game like that")
    assert reference.is_reference_prompt("design transfer from this picture")
    assert reference.is_reference_prompt("use the colors from this image")
