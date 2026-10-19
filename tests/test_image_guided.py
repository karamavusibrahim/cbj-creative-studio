"""The image-guided workflow (core requirement 3, rules I1-I16, 2026-10-17): the dispatch of a prompt plus a picture,
the picture's role, the colours to the game's seven rendered slots, the board to what the generator builds with every
clamp said, the caption against the board, "only X", never copying, and the image rows measured on made files.
No real model is called: the reader and the planner are fakes, and studio.make is never run."""
import json
import re
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from cbj import brief as B
from cbj import imageaudit as IA
from cbj import imageplan as IP
from cbj import imageread as IR
from cbj import studio

REQ3 = Path.home() / "rollic-case" / "req3-image-guided-2026-10-17"
PROMPTS = {
    "A1": ("pic_w.png", "Create a Color Block Jam creative inspired by this image: use its colours for the background and the captions, but keep the game's own block colours. A clean, satisfying win in 30 seconds."),
    "A2": ("pic_w.png", "Make a 40-second ad with this picture's sunset palette on everything, the blocks too, on a narrow-centre level like the one in the image. The player almost runs out of time before clearing it."),
    "A3": ("pic_w.png", "Use only the background colours of this image; everything else stays the game's own. A hard level where the clock runs out with one block still on the board, 35 seconds."),
    "B1": ("pic_x.png", "Make a level with the same number of blocks as this board and stop the ad before the last three blocks leave, asking the viewer what to move next. 40 seconds."),
    "B2": ("pic_x.png", "A Color Block Jam creative with a board as crowded as this one, in the game's own look, ending in a fast cascade win. 30 seconds."),
    "B3": ("pic_x.png", "Take the board from this screenshot: the same grid size, the same colours and about as many blocks. Show the player stuck twice, then the timer runs out. 45 seconds."),
    "C1": ("pic_y.png", "Create a creative with a board shaped like this one, a plus shape with the wall in the middle, and finish with only one second left on the clock. 40 seconds."),
    "C2": ("pic_y.png", "Make a mirror-symmetric level like this picture and end on a question before the final move. Keep the game's own colours and background."),
    "C3": ("pic_y.png", "Inspired by this image: the same board idea and the same block colours, the pink blocks included. A calm, satisfying solve, 45 seconds."),
    "D1": ("pic_z.png", "Create a Color Block Jam ad like this image: its dark neon look, no level badge or timer on screen, and a board split into separate rooms by walls. End before the last move with the caption \"Which one goes first?\"."),
    "D2": ("pic_z.png", "Use this picture's night look for the background and the captions only, on a level with 6 blocks and a few wall cells. Time runs out just before the last block escapes. 30 seconds."),
    "D3": ("pic_z.png", "Make a hard level with big blocks like the ones in this picture, keep the game's standard look and the timer, and let the player barely beat the clock. 50 seconds."),
}


def test_the_test_set_prompts_are_the_ones_in_prompts_md():
    if not (REQ3 / "PROMPTS.md").is_file():
        pytest.skip("the req3 test set is not on this machine")
    text = (REQ3 / "PROMPTS.md").read_text()
    for cid, (pic, prompt) in PROMPTS.items():
        assert re.search(rf"\| {cid} \| {re.escape(pic)} \|[^|]+\| {re.escape(prompt)} \|", text), cid


# ---------- dispatch (rule I2) ----------

@pytest.fixture
def uploads(tmp_path, monkeypatch):
    monkeypatch.setattr(studio, "STUDIO", tmp_path / "studio")
    folder = tmp_path / "studio" / "uploads"
    folder.mkdir(parents=True)
    for n in ("pic_w.png", "pic_x.png", "pic_y.png", "pic_z.png", "logo.png"):
        Image.new("RGB", (8, 8), (200, 100, 50)).save(folder / n)
    (folder / "ref.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64)
    return folder


@pytest.mark.parametrize("cid", sorted(PROMPTS))
def test_every_test_prompt_with_its_picture_goes_to_image_guided(uploads, cid):
    from cbj.app import workflow_of
    pic, prompt = PROMPTS[cid]
    assert workflow_of(prompt, [pic]) == "image_guided"


@pytest.mark.parametrize("prompt", ["Put our logo (attached) on the end card.", "Put this picture on the end card.",
                                    "Use this object instead of the current obstacle.", "Use this image as the background."])
def test_a_picture_only_to_place_stays_in_the_text_workflow(uploads, prompt):
    from cbj.app import workflow_of
    assert workflow_of(prompt, ["logo.png"]) == "create"


def test_a_video_stays_guided_and_an_edit_stays_an_edit(uploads):
    from cbj.app import workflow_of
    prompt = PROMPTS["A1"][1]
    assert workflow_of(prompt, ["ref.mp4"]) == "guided"
    assert workflow_of(prompt, ["ref.mp4", "pic_w.png"]) == "guided"  # a video, with or without a picture
    assert workflow_of(prompt, ["pic_w.png"], creative_id="c") == "edit"
    assert workflow_of("A hard level with a narrow centre.", []) == "create"


def test_make_follows_the_image_guided_plan(monkeypatch):
    from fastapi.testclient import TestClient
    from cbj import app as A
    from test_app import wait
    A.JOBS.clear()
    made = []
    monkeypatch.setattr(A.image_wf, "make", lambda log, p, b, **kw: made.append("image_guided") or {"id": "x", "n": 1})
    monkeypatch.setattr(A.guided_wf, "make", lambda log, p, b, **kw: made.append("guided") or {"id": "x", "n": 1})
    b = B.check(B.default_brief())
    b["planner"] = {"model": "fake", "workflow": "image_guided"}
    j = wait(TestClient(A.app), TestClient(A.app).post("/api/make", json={"prompt": "x", "brief": b}).json()["job"])
    assert j["status"] == "done", j.get("error")
    assert made == ["image_guided"]


# ---------- the role (rules I1, I2, I5) ----------

def _reading(board=True, cbj=True, hud=True, **board_fields):
    bd = {"columns": 5, "rows": 6, "shape_read": "open", "outline": "rectangle", "rooms": 1, "centre_wall": False,
          "wall_cells": 0, "blocks": 14, "colours": [{"name": "red", "rgb": [223, 66, 49]}, {"name": "blue", "rgb": [47, 105, 235]}],
          "pieces": "small", "symmetric": False, "occupancy": 0.74}
    bd.update(board_fields)
    return {"file": "pic.png", "kind": "image", "notes": {"is_color_block_jam": cbj, "what_it_shows": "a board", "look": {}},
            "board": bd if board else None, "hud": {"shown": hud, "level": 42 if hud else None, "clock": "00:45" if hud else None},
            "margins": {"top": "#FDC79F", "bottom": "#F96676"}, "palette": [{"hex": "#FDC79F", "name": "peach", "share": 0.5}],
            "caption_measured": {"fill": "#FEFCFE", "outline": "#531679"}, "captions": ["Can you clear it?"],
            "caption_claims": [], "not_in_game": [], "seconds": 10.0}


@pytest.mark.parametrize("cid, roles, parts, named", [
    ("A1", ["style"], ["background", "captions"], None),
    ("A2", ["style", "board"], ["background", "captions", "blocks"], "all"),
    ("A3", ["style"], ["background"], None),
    ("B1", ["board"], None, ["blocks"]),
    ("B2", ["board"], None, ["packed"]),
    ("B3", ["board"], None, "all"),
    ("C1", ["board"], None, ["shape"]),
    ("C2", ["board"], None, "all"),
    ("C3", ["style", "board"], ["blocks"], "all"),
    ("D1", ["style", "board"], ["background", "captions"], ["shape"]),
    ("D2", ["style"], ["background", "captions"], None),
    ("D3", ["board"], None, ["pieces"]),
])
def test_the_role_and_what_each_takes(cid, roles, parts, named):
    d = IP.decide(PROMPTS[cid][1], _reading(hud=cid[0] != "D"))
    assert d["roles"] == roles
    assert (d["style"] or {}).get("parts") == parts
    want = list(IP.PARTS) if named == "all" else named
    assert (d["board"] or {}).get("named") == want


def test_keep_the_game_own_look_and_block_colours_and_only():
    assert IP.decide(PROMPTS["B2"][1], _reading())["keep_look"]
    assert IP.decide(PROMPTS["D3"][1], _reading())["keep_look"]
    a1 = IP.decide(PROMPTS["A1"][1], _reading())
    assert a1["style"]["keep_blocks"] and not a1["keep_look"]
    assert IP.decide(PROMPTS["A3"][1], _reading())["only"] and IP.decide(PROMPTS["D2"][1], _reading())["only"]
    assert not IP.decide(PROMPTS["C1"][1], _reading())["only"]  # "only one second left" is not a scope


def test_the_screen_is_taken_only_with_the_whole_look_and_a_picture_without_hud():
    assert IP.decide(PROMPTS["D1"][1], _reading(hud=False))["screen"]
    assert not IP.decide(PROMPTS["D2"][1], _reading(hud=False))["screen"]  # background and captions only


def test_inspired_by_names_nothing_board_screenshot_gives_board_and_look_a_photo_its_look():
    p = "Create a Color Block Jam creative inspired by this image."
    assert IP.decide(p, _reading())["roles"] == ["style", "board"]
    photo = IP.decide(p, _reading(board=False, cbj=False))
    assert photo["roles"] == ["style"] and photo["board"] is None
    no_board = IP.decide("Make a level like this picture.", _reading(board=False, cbj=False))
    assert no_board["roles"] == ["style"] and no_board["board"] is None


# ---------- the colours (rule I6) ----------

def test_pink_goes_to_the_nearest_rendered_slot_and_the_line_says_so():
    m = IP.colour_map([{"name": "pink", "rgb": [240, 60, 220]}])
    assert m[0]["slot"] == "Purple" and m[0]["note"] == "pink -> purple: the game has no pink"
    m = IP.colour_map([{"name": "purple", "rgb": [196, 47, 240]}, {"name": "pink", "rgb": [240, 60, 220]}])
    assert [x["slot"] for x in m] == ["Purple", "Red"]  # purple is taken: the next nearest free slot
    assert "purple is taken by purple" in m[1]["note"]


def test_at_most_seven_colours_and_never_a_shared_slot():
    names = ["red", "orange", "yellow", "green", "dark green", "blue", "purple", "pink", "teal"]
    from cbj.videoref import colour_rgb
    m = IP.colour_map([{"name": n, "rgb": colour_rgb(n)} for n in names])
    assert len(m) == 7 and len({x["slot"] for x in m}) == 7
    assert [x["slot"] for x in m[:7]] == ["Red", "Orange", "Yellow", "Green", "DarkGreen", "Blue", "Purple"]


def test_a_repaint_happens_only_when_asked_and_keeps_the_picture_hue():
    r = _reading(colours=[{"name": "coral", "rgb": [248, 140, 128]}, {"name": "lemon", "rgb": [255, 245, 80]}])
    b = B.check(B.default_brief())
    prov = IP.apply(b, PROMPTS["A2"][1], r, IP.decide(PROMPTS["A2"][1], r))
    assert {e["slot"] for e in b["visuals"]["blocks"]} == {m["slot"] for m in prov["colour_map"] if m["read"] == "coral"} | (
        {"Yellow"} if any(e["slot"] == "Yellow" for e in b["visuals"]["blocks"]) else set())
    assert any(e["hex"] == "#F88C80" and e["name"] == "coral" for e in b["visuals"]["blocks"])
    b1 = B.check(B.default_brief())
    IP.apply(b1, PROMPTS["A1"][1], r, IP.decide(PROMPTS["A1"][1], r))
    assert b1["visuals"]["blocks"] == []  # "keep the game's own block colours"


def test_the_caption_contrast_is_checked_against_its_background():
    kit = IP.style_kit({"margins": {"top": "#FFFFFF", "bottom": "#EEEEEE"}, "caption_measured": {"fill": "#FAFAFA", "outline": "#F0F0F0"}},
                       ["background", "captions"])
    assert kit["legible"] and kit["caption_outline"] == "#1A1A1A" and kit["notes"]
    kit = IP.style_kit(_reading(), ["background", "captions"])
    assert kit["contrast"]["outline"] >= 3 and kit["caption_fill"] == "#FEFCFE"


# ---------- the board (rules I7, I8) ----------

def _spec(cid, reading):
    b = B.check(B.default_brief())
    prompt = PROMPTS[cid][1]
    return b, IP.apply(b, prompt, reading, IP.decide(prompt, reading))


def test_fourteen_blocks_are_clamped_with_the_line_and_counted_on_the_board_not_the_caption():
    r = _reading(blocks=14)
    r["captions"], r["caption_claims"] = ["12 blocks. 45 seconds."], IR.caption_claims(["12 blocks. 45 seconds."])
    b, prov = _spec("B1", r)
    assert b["level"]["blocks"] == 10 and b["level"]["source"] == "generate"
    assert "14 blocks -> 10: the tool builds at most 10 blocks in one level" in prov["clamps"]
    assert any(c.startswith("the caption says 12 blocks") and "the board shows 14" in c for c in prov["clamps"])
    assert prov["named"] == ["blocks"] and "size" in prov["filled"]  # the count is named, the rest filled
    assert any("45 seconds" in x for x in prov["not_taken"])  # a caption's number is never the length


def test_a_plus_with_a_centre_wall_is_a_cross_said():
    shape, seen, line = IP.board_shape({"outline": "plus", "shape_read": "cross", "centre_wall": True, "wall_cells": 1})
    assert shape == "cross" and line.startswith("a plus shape with a wall in the middle -> a cross")
    b, prov = _spec("C1", _reading(outline="plus", shape_read="cross", centre_wall=True, columns=7, rows=7, blocks=8))
    assert b["level"]["shape"] == "cross" and any(c.startswith("a plus shape with a wall in the middle -> a cross") for c in prov["clamps"])


def test_rooms_split_by_walls_become_two_rooms_said_and_an_hourglass_a_narrow_centre():
    shape, _, line = IP.board_shape({"outline": "rectangle", "shape_read": "cross", "rooms": 4})
    assert shape == "door" and line == "4 rooms split by walls -> two rooms joined by a door: the tool builds at most two rooms"
    assert IP.board_shape({"outline": "plus", "shape_read": "narrow_center", "rooms": 2})[0] == "narrow_center"
    assert IP.board_shape({"outline": "rectangle", "shape_read": "open", "wall_cells": 0})[0] == "open"


def test_a_size_beyond_the_generator_is_clamped_and_said():
    b, prov = _spec("B3", _reading(columns=12, rows=3, blocks=6))
    assert (b["level"]["width"], b["level"]["height"]) == (9, 4)
    assert any(c.startswith("a 12x3 board -> 9x4") for c in prov["clamps"])


def test_the_request_own_values_win_over_the_picture():
    # A2 states a narrow centre itself (the planner made it one); D2 states 6 blocks and walls and takes no board at all
    b = B.check(B.default_brief())
    b["level"]["shape"] = "narrow_center"
    r = _reading(outline="rectangle", shape_read="open")
    prov = IP.apply(b, PROMPTS["A2"][1], r, IP.decide(PROMPTS["A2"][1], r))
    assert "shape" in prov["board"]["kept"] and b["level"]["shape"] == "narrow_center"
    assert any("the request's words win" in c for c in prov["clamps"])
    b2, prov2 = _spec("D2", _reading(blocks=9))
    assert "board" not in prov2["roles"] and b2["level"]["blocks"] is None


# ---------- only X, the captions, never copying (rules I5, I9, I10, I11) ----------

def test_only_the_background_takes_the_background_alone():
    b, prov = _spec("A3", _reading())
    vs = b["visuals"]
    assert vs["background"] == ["#FDC79F", "#F96676"] and vs["caption_fill"] is None and vs["blocks"] == []
    assert b["level"]["source"] == "auto"  # no board
    assert any(x.startswith("the captions: the game's own (only background is asked)") for x in prov["not_taken"])


def test_the_picture_caption_is_not_reused_unless_quoted():
    r = _reading()
    r["captions"] = ["Which one goes first?"]
    b = B.check(B.default_brief())
    b["concept"]["hook"] = "Which one goes first?"
    IP.apply(b, "Make a level like this picture.", r, IP.decide("Make a level like this picture.", r))
    assert b["concept"]["hook"] is None
    b = B.check(B.default_brief())
    b["concept"]["hook"] = "Which one goes first?"
    IP.apply(b, PROMPTS["D1"][1], r, IP.decide(PROMPTS["D1"][1], r))
    assert b["concept"]["hook"] == "Which one goes first?"  # quoted by the request


def test_the_picture_is_never_drawn_and_missing_mechanics_are_listed():
    r = _reading()
    r["not_in_game"] = ["a hammer booster button", "level indicator"]
    b = B.check(B.default_brief())
    b["visuals"]["background_image"] = "pic.png"
    b["assets"] = [{"file": "pic.png", "role": "end_art", "when": "end_card", "where": "auto"}]
    prov = IP.apply(b, PROMPTS["B2"][1], r, IP.decide(PROMPTS["B2"][1], r))
    assert b["visuals"]["background_image"] is None and b["assets"] == []
    assert any("hammer booster button: not used: not in Color Block Jam" in x for x in prov["not_used"])
    assert any("level indicator" in x and "HUD" in x for x in prov["mechanics"])


def test_a_dark_look_with_no_hud_hides_the_hud_and_a_cliffhanger_caption_is_fitted():
    from cbj import videoref
    r = _reading(hud=False)
    b = B.check(B.default_brief())
    b["gameplay"]["ending"] = "cliffhanger"
    b["concept"]["result"] = "Cleared!"
    prompt = "Create a Color Block Jam ad like this image: its dark neon look and its board."
    prov = IP.apply(b, prompt, r, IP.decide(prompt, r))
    assert not b["visuals"]["hud_timer"] and not b["visuals"]["hud_level"]
    assert "the screen: no HUD, as in the picture" in prov["taken"]
    assert videoref.fit_captions(b) and b["concept"]["result"] is None


def test_the_planner_never_sees_numbers_palette_or_caption_words():
    r = _reading()
    v = IP.planner_view(r, IP.decide(PROMPTS["B3"][1], r))
    assert v["kind"] == "picture" and "palette" not in v
    text = json.dumps(v)
    assert "14" not in text and "Can you clear it" not in text and "#FDC79F" not in text


# ---------- the image rows on made files (rule I13) ----------

def _level(path: Path, mirrored=True) -> Path:
    sq = [{"x": 0, "y": 0}, {"x": 0, "y": -1}, {"x": 1, "y": -1}, {"x": 1, "y": 0}]
    second = {"x": 2, "y": 1} if mirrored else {"x": 2, "y": 3}
    d = {"gridWidth": 4, "gridHeight": 4, "timerCount": 60, "inactiveCells": [],
         "GridBlockDatas": [{"gridPosition": {"x": 0, "y": 1}, "blockColor": 2, "shapeOffsets": sq},
                            {"gridPosition": second, "blockColor": 5, "shapeOffsets": sq}],
         "ExitDatas": [{"exitNumber": 0, "gridPosition": {"x": 0, "y": 3}, "requiredColor": 2, "direction": 2,
                        "shapeOffsets": [{"x": 0, "y": 0}, {"x": 1, "y": 0}]},
                       {"exitNumber": 0, "gridPosition": {"x": 0, "y": 0}, "requiredColor": 5, "direction": 3,
                        "shapeOffsets": [{"x": 0, "y": 0}, {"x": 1, "y": 0}]}]}
    path.write_text(json.dumps(d))
    return path


def _made(tmp_path, monkeypatch, bg="#FDC79F", caption=("#FEFCFE", "#531679"), hide=()):
    """A made version's files: level.json, a poster and a one-second ad.mp4 of it with the hook drawn in its box, the
    parts manifest, the ad's layers and the recording's job."""
    monkeypatch.setattr(studio, "STUDIO", tmp_path / "studio")
    vdir = tmp_path / "studio" / "c" / "v1"
    (vdir / "ad").mkdir(parents=True, exist_ok=True)
    _level(vdir / "level.json")
    im = Image.new("RGB", (1080, 1920), bg)
    d = ImageDraw.Draw(im)
    d.rectangle((160, 284, 919, 441), fill=caption[1])
    d.rectangle((200, 320, 880, 405), fill=caption[0])
    im.save(vdir / "ad" / "poster.png")
    IR.still_clip(vdir / "ad" / "poster.png", vdir / "ad" / "ad.mp4")
    (vdir / "parts.json").write_text(json.dumps({"layers": [{"id": "hook", "from_s": 0.0, "to_s": 0.8, "box": [160, 284, 919, 441]}]}))
    (vdir / "ad" / "ad.json").write_text(json.dumps({"layers": {"hook": {"type": "text", "text": "Can you beat it?"}}}))
    rec = tmp_path / "studio" / "recordings" / "r1"
    rec.mkdir(parents=True, exist_ok=True)
    (rec / "job.json").write_text(json.dumps({"hide": list(hide)}))
    return vdir, {"id": "c", "n": 1, "recording": {"dir": "recordings/r1"}}


def _rowmap(rows):
    return {r["check"]: r for r in rows}


def test_the_board_rows_measure_the_made_level(tmp_path, monkeypatch):
    vdir, record = _made(tmp_path, monkeypatch)
    r = _reading(columns=4, rows=4, blocks=2, pieces="big", symmetric=True, occupancy=None,
                 colours=[{"name": "blue", "rgb": [47, 105, 235]}, {"name": "pink", "rgb": [240, 60, 220]}])
    b, prov = _spec("C2", r)
    rows = _rowmap(IA.rows(PROMPTS["C2"][1], b, record, vdir))
    assert rows["Image: the board's size"]["status"] == "pass"
    assert rows["Image: the board's blocks"]["status"] == "pass"
    assert rows["Image: the board's colours"]["status"] == "pass"  # blue and pink -> purple are on the made board
    assert rows["Image: mirror-symmetric"]["status"] == "pass"
    assert rows["Image: the pieces"]["status"] == "info"  # 2x2 pieces are big, but the pieces' class is not read reliably
    assert "it matches" in rows["Image: the pieces"]["detail"] and "read approximately" in rows["Image: the pieces"]["detail"]
    assert rows["Image: the role"]["status"] == "info" and rows["Image: what was taken"]["status"] == "info"
    _level(vdir / "level.json", mirrored=False)
    rows = _rowmap(IA.rows(PROMPTS["C2"][1], b, record, vdir))
    assert rows["Image: mirror-symmetric"]["status"] == "failed" and rows["Image: mirror-symmetric"]["where"] == "level"


def test_a_filled_part_is_info_and_a_named_part_is_judged(tmp_path, monkeypatch):
    vdir, record = _made(tmp_path, monkeypatch)
    b, prov = _spec("B1", _reading(columns=8, rows=8, blocks=5))  # count named, size filled
    rows = _rowmap(IA.rows(PROMPTS["B1"][1], b, record, vdir))
    assert rows["Image: the board's size"]["status"] == "info" and "filled from the image" in rows["Image: the board's size"]["detail"]
    assert rows["Image: the board's blocks"]["status"] == "failed"  # 5 built, 2 made


def test_the_look_rows_read_the_made_frame(tmp_path, monkeypatch):
    vdir, record = _made(tmp_path, monkeypatch)
    b, prov = _spec("A1", _reading())
    rows = _rowmap(IA.rows(PROMPTS["A1"][1], b, record, vdir))
    assert rows["Image: the background"]["status"] == "pass", rows["Image: the background"]["detail"]
    assert rows["Image: the caption colours"]["status"] == "pass", rows["Image: the caption colours"]["detail"]
    assert rows["Image: not taken stays the game's own"]["status"] == "pass"  # the blocks stay the game's own
    assert rows["Image: nothing copied"]["status"] == "pass"
    vdir, record = _made(tmp_path, monkeypatch, bg="#E4F0FE", caption=("#FFFFFF", "#5A2D82"))
    rows = _rowmap(IA.rows(PROMPTS["A1"][1], b, record, vdir))
    assert rows["Image: the background"]["status"] == "failed" and rows["Image: the background"]["where"] == "ad"


def test_the_game_own_look_when_not_taken_and_the_screen_as_asked(tmp_path, monkeypatch):
    vdir, record = _made(tmp_path, monkeypatch, bg="#E4F0FE", caption=("#FFFFFF", "#5A2D82"))
    b, prov = _spec("B2", _reading())
    rows = _rowmap(IA.rows(PROMPTS["B2"][1], b, record, vdir))
    assert rows["Image: not taken stays the game's own"]["status"] == "pass"
    assert rows["Image: the screen"]["status"] == "pass"  # nothing asked: the game's own HUD, shown
    b, prov = _spec("D1", _reading(hud=False))
    b["visuals"]["hud_timer"] = b["visuals"]["hud_level"] = False  # the planner hides it, as the request asks
    vdir, record = _made(tmp_path, monkeypatch, hide=("MainBar",))
    assert _rowmap(IA.rows(PROMPTS["D1"][1], b, record, vdir))["Image: the screen"]["status"] == "pass"
    vdir, record = _made(tmp_path, monkeypatch, hide=())
    row = _rowmap(IA.rows(PROMPTS["D1"][1], b, record, vdir))["Image: the screen"]
    assert row["status"] == "failed" and row["where"] == "play"


def test_nothing_copied_fails_on_the_picture_in_a_layer_or_its_caption_words(tmp_path, monkeypatch):
    vdir, record = _made(tmp_path, monkeypatch)
    b, prov = _spec("B2", _reading())
    (vdir / "ad" / "ad.json").write_text(json.dumps({"layers": {"end_art": {"type": "image", "image": "pic.png"}}}))
    assert _rowmap(IA.rows(PROMPTS["B2"][1], b, record, vdir))["Image: nothing copied"]["status"] == "failed"
    (vdir / "ad" / "ad.json").write_text(json.dumps({"layers": {}}))
    b["concept"]["hook"] = "Can you clear it?"  # the picture's own caption, not quoted
    assert _rowmap(IA.rows(PROMPTS["B2"][1], b, record, vdir))["Image: nothing copied"]["status"] == "failed"


def test_counted_on_the_board_row():
    r = _reading(blocks=14)
    r["caption_claims"] = IR.caption_claims(["12 blocks. 45 seconds."])
    b, prov = _spec("B1", r)
    row = IA.counted_row(prov)
    assert row["status"] == "pass" and "the board shows 14" in row["detail"]


# ---------- the reading (rule I3), with a fake reader ----------

class FakeReader:
    """Answers each of the reading's questions by its words; never the network."""

    def __init__(self):
        self.asks, self.last_model, self.reader, self.errors = [], "fake-reader", "gemini", []

    def describe(self, ask, part, path=None):
        self.asks.append(ask[:40])
        if ask.startswith("This picture was attached"):
            return json.dumps({"what_it_shows": "a board", "kind": "game screenshot", "is_color_block_jam": True,
                               "hud": {"shown": True, "level": "42", "clock": "00:45"},
                               "board": {"shown": True, "outline": "rectangle", "rooms": 1, "centre_wall": False, "wall_cells": 0,
                                         "columns": 5, "rows": 6, "blocks": 12, "colours": ["red", "blue"],
                                         "box": {"x": 0.1, "y": 0.3, "w": 0.8, "h": 0.4}},
                               "look": {"mood": "calm"}, "captions_seen": ["12 blocks. 45 seconds."],
                               "caption_box": {"x": 0.1, "y": 0.05, "w": 0.8, "h": 0.1}, "not_in_game": []})
        if "Count the coloured blocks" in ask:
            return json.dumps({"blocks": 14})
        if "Count the cells" in ask:
            return json.dumps({"columns": 5, "rows": 6})
        if "distinct block colours" in ask:
            return json.dumps({"colour_count": 2, "colours": ["red", "blue"]})
        return json.dumps({"board": {"columns": 5, "rows": 6, "shape": "open", "blocks": 13, "colours": ["red", "blue"],
                                     "pieces": "small", "symmetric": False, "wall_cells": 0, "obstacles": []},
                           "box": {"x": 0.1, "y": 0.3, "w": 0.8, "h": 0.4}, "extras_seen": []})


def _picture(path: Path) -> Path:
    im = Image.new("RGB", (400, 720), (221, 232, 250))
    d = ImageDraw.Draw(im)
    d.rectangle((40, 216, 360, 504), fill=(94, 106, 148))
    for i in range(5):
        d.rectangle((48 + i * 62, 224, 100 + i * 62, 300), fill=(223, 66, 49) if i % 2 else (47, 105, 235))
    d.rectangle((60, 50, 340, 110), fill=(82, 38, 127))
    d.rectangle((80, 65, 320, 95), fill=(240, 245, 253))
    im.save(path)
    return path


def test_the_reading_counts_on_the_board_and_measures_in_code(tmp_path):
    reader = FakeReader()
    r = IR.read(_picture(tmp_path / "pic.png"), client=reader)
    assert not r.get("error")
    assert r["board"]["blocks"] == 14  # the median of the board read (13) and two counts on the crop (14, 14)
    assert r["caption_claims"] == [{"caption": "12 blocks. 45 seconds.", "n": 12, "what": "blocks"},
                                   {"caption": "12 blocks. 45 seconds.", "n": 45, "what": "seconds"}]
    assert r["margins"]["top"].startswith("#DD") and r["hud"] == {"shown": True, "level": 42, "clock": "00:45"}
    assert r["caption_measured"]["fill"] == "#F0F5FD" and r["caption_measured"]["outline"] == "#52267F"


def test_plan_reads_decides_plans_and_applies_without_a_real_model(tmp_path, monkeypatch):
    from cbj import llm
    from cbj.workflows import image_guided as W
    from test_text_to_creative import FakeModel, raw_brief
    monkeypatch.setattr(studio, "STUDIO", tmp_path / "studio")
    (tmp_path / "studio" / "uploads").mkdir(parents=True)
    _picture(tmp_path / "studio" / "uploads" / "pic_x.png")
    raw = raw_brief(gameplay={"ending": "cliffhanger", "blocks_left": 3}, pacing={"length_s": 40.0})
    raw["changed"] = ["gameplay.ending", "gameplay.blocks_left", "pacing.length"]
    monkeypatch.setattr(llm, "planner_client", lambda: FakeModel(raw))
    lines = []
    brief = W.plan(studio.Log(lambda ln: lines.append(ln["text"])), PROMPTS["B1"][1], ["pic_x.png"], reader=FakeReader())
    assert brief["planner"]["workflow"] == "image_guided"
    prov = brief["reference"]
    assert prov["roles"] == ["board"] and prov["named"] == ["blocks"]
    assert brief["level"]["blocks"] == 10 and brief["level"]["source"] == "generate"
    assert any(l.startswith("built: 14 blocks -> 10: the tool builds at most 10 blocks") for l in lines)
    ref = brief["planner"]["references"][0]
    assert ref["kind"] == "image" and ref["role"]["composition"]


def test_pin_look_keeps_the_picture_look_in_a_revision():
    from cbj.workflows import image_guided as W
    r = _reading()
    before = B.check(B.default_brief())
    IP.apply(before, PROMPTS["A1"][1], r, IP.decide(PROMPTS["A1"][1], r))
    after = json.loads(json.dumps(before))
    after["visuals"]["background"] = ["#000000", "#111111"]
    notes = W.pin_look(before, after, [])
    assert after["visuals"]["background"] == ["#FDC79F", "#F96676"] and notes


# ---------- the Opus reader and the reading plan (2026-10-17, the owner) ----------

class FakeClaude:
    """The Claude reader's interface (reader "claude"), answering the one whole-picture ask; never the CLI."""
    reader = "claude"

    def __init__(self, answer=None, fail=False):
        self.answer, self.fail, self.asks, self.last_model, self.errors, self.model = answer, fail, [], None, [], "opus"
        self.symmetric = None

    def describe(self, ask, part, path=None):
        self.asks.append(ask)
        if self.fail:
            raise ValueError("the claude command answered with an error: usage limit")
        self.last_model = "claude-cli/opus"
        if "Count the cells" in ask:
            return json.dumps({"columns": 5, "rows": 6})
        a = json.loads(FakeReader().describe("This picture was attached", part))
        a["look"] = {"background_top": "#DDE8FA", "background_bottom": "#DDE8FA", "caption_fill": "#F0F5FD",
                     "caption_outline": "#52267F"}
        a["board"].update(blocks=14, symmetric=self.symmetric)
        a["answers"] = [{"question": q, "answer": "14"} for q in re.findall(r"^\d+\. (.+)$", ask, re.M)]
        return json.dumps(self.answer or a)


class FakePlanner:
    last_model = "fake-planner"

    def __init__(self, raw):
        self.raw, self.calls = raw, []

    def complete(self, system, user, schema):
        self.calls.append(user)
        return json.dumps(self.raw)


def test_the_reading_plan_is_written_from_the_request_and_the_format_only(tmp_path):
    pic = _picture(tmp_path / "secret_name_pic.png")
    facts = IR.format_facts(pic)
    assert facts["orientation"] == "portrait" and facts["aspect"] == "5:9"
    planner = FakePlanner({"focus": ["board"], "level": "targeted", "questions": ["how many blocks: count the board"],
                           "ignore": ["its captions' words"], "constraints": ["40 seconds"], "why": "the block count"})
    plan = IR.reading_plan(PROMPTS["B1"][1], facts, client=planner)
    assert plan["source"] == "planner" and plan["focus"] == ["board"] and "secret_name" not in planner.calls[0]
    bad = IR.reading_plan(PROMPTS["B1"][1], facts, client=FakePlanner({"focus": [], "level": "targeted", "questions": []}))
    assert bad["source"] == "words" and bad["focus"] == ["board"] and "word table" in bad["checks"][0]


def test_opus_reads_once_with_the_plan_questions_and_the_code_measures_beside(tmp_path):
    pic = _picture(tmp_path / "pic.png")
    plan = {"focus": ["board"], "level": "targeted", "questions": ["how many blocks are on the board"], "ignore": [],
            "constraints": [], "why": "", "source": "planner", "checks": []}
    reader = FakeClaude()
    reader.symmetric = None
    r0 = IR.read(pic, client=FakeClaude(), plan=plan)
    reader.symmetric = not r0["board"]["symmetric"]
    r = IR.read(pic, client=reader, plan=plan)
    general = [a for a in reader.asks if a.startswith("This picture was attached")]
    assert len(general) == 1 and "1. how many blocks are on the board" in general[0]
    type_asks = [a for a in reader.asks if "corners of the PLAYABLE GRID" not in a and "warped to a flat grid" not in a]
    assert len(type_asks) == 1 + IR.SIZE_REREADS and r["board_read"]["size_reads"] == [[5, 6], [5, 6]]
    assert r["board"]["symmetric"] == r0["board"]["symmetric"]
    assert r["reader"] == "claude" and r["model"] == "claude-cli/opus" and r["plan"] is plan
    assert r["board"]["blocks"] == 14 and r["answers"][0]["answer"] == "14"
    assert r["board"]["symmetric_source"] == "measured"  # the mirror mask decides, not the reader's "symmetric"
    assert any(d.startswith("symmetry: the reader said") and "the measure is used" in d for d in r["disagreements"])
    assert r["caption_measured"]["fill"] == "#F0F5FD"  # measured in the caption's box


def test_a_failing_opus_falls_back_to_gemini_then_nvidia(tmp_path):
    r = IR.read(_picture(tmp_path / "pic.png"), client=FakeClaude(fail=True), fallback=FakeReader())
    assert r["reader"] == "gemini" and r["fell_back"].startswith("claude") and r["board"]["blocks"] == 14


def test_a_wrong_answer_is_asked_again_with_its_problems_quoted(tmp_path):
    reader = FakeClaude(answer={"what_it_shows": "x"})
    IR.read(_picture(tmp_path / "pic.png"), client=reader, fallback=FakeReader())
    assert len(reader.asks) >= 2 and "YOUR LAST ANSWER HAD THESE PROBLEMS" in reader.asks[1]


def test_the_reader_is_opus_when_the_planner_is_claude_or_asked(monkeypatch):
    monkeypatch.setenv("CBJ_IMAGE_READER", "")
    monkeypatch.setenv("CBJ_PLANNER", "claude")
    r = IR.image_reader()
    assert isinstance(r, IR.ClaudeImageReader) and r.model == "opus"
    monkeypatch.setenv("CBJ_IMAGE_READER", "claude:sonnet:medium")
    assert IR.image_reader().model == "sonnet"
    monkeypatch.setenv("CBJ_IMAGE_READER", "gemini")
    from cbj import reference
    assert isinstance(IR.image_reader(), reference.VideoReader)


def test_the_plan_focus_decides_the_roles_and_the_words_the_parts():
    r = _reading()
    d = IP.decide(PROMPTS["A2"][1], r)
    only_style = {"focus": ["style"], "level": "targeted", "source": "planner", "checks": [], "why": "the palette"}
    out = IP.reconcile(d, only_style, r)
    assert out["roles"] == ["style"] and out["style"]["parts"] == ["background", "captions", "blocks"]
    assert any("not applied" in c for c in only_style["checks"])
    board_plan = {"focus": ["board"], "level": "targeted", "source": "planner", "checks": []}
    out = IP.reconcile(IP.decide("Make it calm.", r), board_plan, r)
    assert out["roles"] == ["board"] and out["board"]["named"] == []  # every part filled from the image
    no_board = IP.reconcile(IP.decide("Make it calm.", _reading(board=False, cbj=False)), dict(board_plan, checks=[]),
                            _reading(board=False, cbj=False))
    assert no_board["roles"] == ["style"]
    words = {"focus": ["style"], "source": "words"}
    assert IP.reconcile(d, words, r) is d  # the word table's own plan changes nothing


# ---------- the 12-case run's findings (2026-10-17, F1-F11) ----------

def test_f1_no_board_description_reaches_the_planner_when_the_board_is_not_taken():
    r = _reading()
    r["notes"].update(what_it_shows="an hourglass board with a narrow neck", idea="clear the neck",
                      look={"style": "sunset pastel", "mood": "warm"})
    v = IP.planner_view(r, IP.decide(PROMPTS["A1"][1], r))
    text = json.dumps(v)
    assert "hourglass" not in text and "neck" not in text and "sunset pastel" in text
    b = B.check(B.default_brief())
    B.control(b, "level")["plan"] = "A hard narrow-centre board; it suits the picture's idea of the narrow neck."
    prov = IP.apply(b, PROMPTS["A1"][1], r, IP.decide(PROMPTS["A1"][1], r))
    row = IA.board_not_taken_row(b, prov, {"shape": "narrow_center"})
    assert row["status"] == "failed" and "cites the picture" in row["detail"]
    B.control(b, "level")["plan"] = "A hard narrow-centre board."
    assert IA.board_not_taken_row(b, prov, {"shape": "narrow_center"})["status"] == "pass"


def test_f2_a_repaint_uses_the_measured_colour_of_every_slot(tmp_path):
    pic = tmp_path / "p.png"
    im = Image.new("RGB", (100, 100), (60, 30, 60))
    d = ImageDraw.Draw(im)
    d.rectangle((10, 10, 40, 40), fill=(243, 116, 107))  # coral, named "red" by the reader
    d.rectangle((60, 60, 90, 90), fill=(250, 244, 103))  # lemon, named "yellow"
    im.save(pic)
    board = {"colours": [{"name": "red", "rgb": [255, 59, 42], "measured": False}, {"name": "yellow", "rgb": [255, 204, 4], "measured": False}]}
    notes = {"board": {"colours": ["red", "yellow"], "colours_hex": ["#F07060", "#F8F060"]}}
    IR.apply_named(board, notes, pic, {"x": 0, "y": 0, "w": 1, "h": 1})
    assert board["colours"][0]["rgb"] == [243, 116, 107] and board["colours"][0]["source"] == "pixels"
    shown, _ = IP.repaint(IP.colour_map(board["colours"]))
    assert {e["hex"] for e in shown} == {"#F3746B", "#FAF467"}  # both slots repainted, though named like game colours
    shown, _ = IP.repaint(IP.colour_map([{"name": "red", "rgb": [255, 59, 42]}]))
    assert shown == []  # a name alone with the game's own shade keeps the game's colour


def test_f3_f5_shared_rows_are_judged_against_the_words_and_blocks_left_is_measured(tmp_path, monkeypatch):
    b = B.check(B.default_brief())
    b["gameplay"]["ending"] = "near_fail"
    checks = [{"check": "Asked: ending", "status": "failed", "detail": "time-out asked, the plan says near-fail", "from": "prompt", "where": "plan"}]
    out = IA.rejudge(PROMPTS["A2"][1], b, checks)
    assert out[0]["status"] == "info" and "almost runs out of time" in out[0]["detail"]
    b["gameplay"]["ending"] = "cliffhanger"
    checks = [{"check": "Asked: block count", "status": "failed", "detail": "3 asked, the plan says 8, the board has 8", "from": "prompt", "where": "plan"}]
    assert IA.rejudge(PROMPTS["B1"][1], b, checks)[0]["status"] == "info"
    assert IP.request_values(b, PROMPTS["B1"][1]) and b["gameplay"]["blocks_left"] == 3
    monkeypatch.setattr(studio, "STUDIO", tmp_path)
    (tmp_path / "rec").mkdir()
    (tmp_path / "rec" / "result.json").write_text(json.dumps({"block_gone_frames": [-1, -1, 40, 50]}))
    row = IA.blocks_left_row(PROMPTS["B1"][1], b, {"recording": {"dir": "rec"}})
    assert row["status"] == "failed" and "stops with 2" in row["detail"]
    (tmp_path / "rec" / "result.json").write_text(json.dumps({"block_gone_frames": [-1, -1, -1, 50]}))
    assert IA.blocks_left_row(PROMPTS["B1"][1], b, {"recording": {"dir": "rec"}})["status"] == "pass"


def test_f5_the_best_version_is_the_one_that_stops_with_the_asked_blocks_left():
    from cbj.workflows import image_guided as W
    false_count = {"check": "Asked: block count", "status": "info", "detail": "judged against the words here", "from": "prompt"}
    left = lambda ok: {"check": "Image: blocks left at the cut", "status": "pass" if ok else "failed", "detail": "", "from": "reference", "where": "play"}  # noqa: E731
    v1 = {"id": "c", "n": 1, "checks": [false_count, left(False)], "review": {"overall": "ship"}}
    v2 = {"id": "c", "n": 2, "checks": [false_count, left(True)], "review": {"overall": "fix"}}
    v3 = {"id": "c", "n": 3, "checks": [false_count, left(True)], "review": {"overall": "fix"}}
    assert W.best_version(studio.Log(), [v1, v2, v3])["n"] == 3


def test_f4_f8_the_most_blocks_the_limit_allows_and_the_row_judges_against_it():
    fit = IP.fit_board(14, "open", (5, 6), "varied", True, "free", True, 0.72, judge_blocks=True, judge_packed=False)
    assert fit["blocks"] == 10 and fit["pieces"] == "small" and fit["cut"] is None
    assert fit["lines"][0] == "14 blocks -> 10: the tool builds at most 10 blocks in one level"
    fit = IP.fit_board(14, "open", (5, 6), "varied", True, "named", True, 0.72, judge_blocks=True, judge_packed=True)
    assert fit["size"] == [5, 6] and fit["blocks"] >= 8 and fit["fill"] >= IP.PACK_MARGIN  # "the same grid size" stays
    prov = {"board": {"named": ["blocks"], "filled": [], "seen": {"blocks": 14}, "built": {"blocks": 8, "blocks_target": 10, "blocks_cut": None}}}
    made = {"blocks": 8, "columns": 5, "rows": 6, "colours": [], "shape": "open", "fill": 0.7, "mean_cells": 2, "bars": False,
            "mirror": [0, 0], "symmetric": False}
    row = IA.board_rows(prov, made)[0]
    assert row["check"] == "Image: the board's blocks" and row["status"] == "pass"  # 8 is within 2 of 10
    made["blocks"] = 7
    assert IA.board_rows(prov, made)[0]["status"] == "failed"


def test_f6_crowded_like_the_picture_fits_the_fill_and_a_revision_never_eases_the_level():
    from cbj.workflows import image_guided as W
    r = _reading(blocks=14, pieces="small", occupancy=0.73)
    b, prov = _spec("B2", r)
    lv = b["level"]
    assert "packed" in lv["style"] and prov["board"]["built"]["fill_expected"] >= IP.PACK_MARGIN
    after = json.loads(json.dumps(b))
    after["level"].update(difficulty="easy", edit={"dir": "easier"})
    miss = [{"check": "Image: packed", "status": "failed", "where": "level", "from": "reference"}]
    notes = W.pin_level(PROMPTS["B2"][1], b, after, miss)
    assert after["level"]["difficulty"] == b["level"]["difficulty"] and after["level"]["edit"] == b["level"]["edit"]
    assert any("packed like the picture" in n for n in notes)
    look_only = json.loads(json.dumps(b))
    look_only["level"].update(blocks=4, difficulty="easy")
    W.pin_level(PROMPTS["C3"][1], b, look_only, [{"check": "Image: not taken stays the game's own", "status": "failed", "where": "plan"}])
    assert look_only["level"] == b["level"]  # a look miss never changes the level


def test_f7_a_fast_cascade_reaches_the_play_and_is_judged(tmp_path, monkeypatch):
    b = B.check(B.default_brief())
    b["gameplay"]["ending"] = "win"
    IP.request_values(b, PROMPTS["B2"][1])
    assert b["pacing"]["tempo"] == "fast" and b["gameplay"]["finish"] == "streak"
    monkeypatch.setattr(studio, "STUDIO", tmp_path)
    (tmp_path / "rec").mkdir()
    drags = [{"start_frame": i * 30, "end_frame": i * 30 + 20} for i in range(8)]  # 10 frames apart: 0.33 s pauses
    (tmp_path / "rec" / "result.json").write_text(json.dumps({"drags": drags}))
    assert IA.fast_finish_row(PROMPTS["B2"][1], b, {"recording": {"dir": "rec"}})["status"] == "pass"
    slow = [{"start_frame": i * 60, "end_frame": i * 60 + 20} for i in range(8)]  # 1.33 s pauses
    (tmp_path / "rec" / "result.json").write_text(json.dumps({"drags": slow}))
    assert IA.fast_finish_row(PROMPTS["B2"][1], b, {"recording": {"dir": "rec"}})["status"] == "failed"


def test_f10_a_shape_named_from_the_picture_and_stated_gets_a_judged_row(tmp_path, monkeypatch):
    b = B.check(B.default_brief())
    b["level"]["shape"] = "cross"  # the planner made the stated plus shape a cross
    r = _reading(outline="plus", shape_read="cross", centre_wall=True, columns=7, rows=7, blocks=8)
    prov = IP.apply(b, PROMPTS["C1"][1], r, IP.decide(PROMPTS["C1"][1], r))
    assert "shape" in prov["named"]
    rows = IA.board_rows(prov, {"columns": 7, "rows": 7, "blocks": 8, "colours": [], "shape": "open", "fill": 0.4,
                                "mean_cells": 2, "bars": False, "mirror": [0, 0], "symmetric": False})
    shape = next(x for x in rows if x["check"] == "Image: the board's shape")
    assert shape["status"] == "failed"


def test_f11_a_block_repaint_alone_keeps_the_game_background(tmp_path, monkeypatch):
    vdir, record = _made(tmp_path, monkeypatch, bg="#E4F0FE", caption=("#FFFFFF", "#5A2D82"))
    r = _reading(colours=[{"name": "pink", "rgb": [240, 60, 220], "measured": True}, {"name": "blue", "rgb": [47, 105, 235], "measured": True}])
    b, prov = _spec("C3", r)
    assert b["visuals"]["theme"] == "custom" and b["visuals"]["background"] == []
    row = _rowmap(IA.rows(PROMPTS["C3"][1], b, record, vdir))["Image: not taken stays the game's own"]
    assert row["status"] == "pass", row["detail"]


def test_f12_a_quoted_caption_survives_the_caption_fit_and_is_checked_on_the_parts(tmp_path, monkeypatch):
    from cbj import videoref
    b = B.check(B.default_brief())
    b["gameplay"]["ending"], b["gameplay"]["blocks_left"] = "cliffhanger", 1
    b["concept"]["result"] = "Which one goes first?"
    before = dict(b["concept"])
    videoref.fit_captions(b)
    assert b["concept"]["result"] is None  # the shared fit clears a cliffhanger's result
    notes = IP.keep_quoted(b, PROMPTS["D1"][1], before)
    assert b["concept"]["result"] == "Which one goes first?" and b["gameplay"]["blocks_left"] == 2 and len(notes) == 2
    vdir, record = _made(tmp_path, monkeypatch)
    (vdir / "parts.json").write_text(json.dumps({"layers": [
        {"id": "cap_result", "text": "Which one goes first?", "from_s": 28.0, "to_s": 31.0}]}))
    assert IA.quoted_row(PROMPTS["D1"][1], vdir)["status"] == "pass"
    (vdir / "parts.json").write_text(json.dumps({"layers": [{"id": "cap_result", "text": "Can you see the move?", "from_s": 28.0, "to_s": 31.0}]}))
    assert IA.quoted_row(PROMPTS["D1"][1], vdir)["status"] == "failed"


def test_f10b_rooms_split_by_walls_name_the_shape():
    d = IP.decide(PROMPTS["D1"][1], _reading(hud=False))
    assert "shape" in d["board"]["named"] and "shape" in d["board"]["specific"]


def test_f13_a_filled_size_the_reads_disagree_on_is_sized_by_the_blocks():
    r = _reading(columns=12, rows=12, blocks=6, pieces="big", occupancy=None, size_spread=5,
                 size_reads=[[12, 12], [7, 7], [12, 12]], outline="rectangle", rooms=4, shape_read="cross")
    b, prov = _spec("D3", r)
    w, h = b["level"]["width"], b["level"]["height"]
    assert (w, h) == (7, 7) and any(c.startswith("a 12x12 board read (9x10 the largest the tool builds) -> 7x7") and "7x7 is the read on which 6" in c
                                    for c in prov["clamps"])
    # D1's reads: the median 7x8 is the read the count agrees with, so it stands
    r1 = _reading(columns=7, rows=8, blocks=6, pieces="varied", occupancy=None, size_spread=5,
                  size_reads=[[12, 12], [7, 8], [7, 8]], outline="rectangle", rooms=4, shape_read="cross")
    b1, _ = _spec("D1", r1)
    assert (b1["level"]["width"], b1["level"]["height"]) == (7, 8)
    made = {"columns": w, "rows": h, "blocks": 6, "colours": [], "shape": "door", "fill": 0.5, "mean_cells": 4.5, "bars": False,
            "mirror": [0, 0], "symmetric": False}
    size = next(x for x in IA.board_rows(prov, made) if x["check"] == "Image: the board's size")
    assert size["status"] == "info" and "spread over 5 cells" in size["detail"]


# ---------- round 2's findings (2026-10-17, G1-G12) ----------

def _parts(vdir: Path, play_s: float, total: float):
    (vdir / "parts.json").write_text(json.dumps({"duration_s": total, "layers": [],
                                                 "parts": [{"id": "play", "from_s": 1.0, "to_s": 1.0 + play_s}]}))


def test_g1_a_filled_count_is_raised_so_the_play_carries_the_ad_and_a_named_one_says_its_limit():
    r = _reading(columns=7, rows=7, blocks=8, outline="plus", shape_read="cross", pieces="varied", occupancy=None)
    b = B.check(B.default_brief())
    b["pacing"]["length_s"], b["gameplay"]["ending"] = 45.0, "win"
    prompt = "Make a calm creative with a board shaped like this one. A clean win, 45 seconds."
    prov = IP.apply(b, prompt, r, IP.decide(prompt, r))
    before = IP.expected_play(b, 8)
    notes = IP.fill_play(b, prompt, prov)
    assert b["level"]["blocks"] == 10 and notes and "the gameplay carries the ad" in notes[0]
    assert IP.expected_play(b, 10) > before and b["level"]["difficulty"] == "any"
    b2 = B.check(B.default_brief())
    b2["pacing"]["length_s"], b2["gameplay"]["ending"] = 30.0, "cliffhanger"
    prov2 = IP.apply(b2, PROMPTS["C2"][1], _reading(columns=7, rows=7, blocks=8), IP.decide(PROMPTS["C2"][1], _reading(columns=7, rows=7, blocks=8)))
    before2 = IP.expected_play(b2, 8)
    IP.fill_play(b2, PROMPTS["C2"][1], prov2)
    # a named count: the count stays; one more wrong move or a hesitation, whichever lengthens the play, never the difficulty
    assert b2["level"]["blocks"] == 8 and (b2["gameplay"]["mistakes"] == 1 or b2["gameplay"]["hesitations"] == 1)
    assert prov2["play_fill"]["expected_s"] > before2 and b2["level"]["difficulty"] == "any"
    b3 = B.check(B.default_brief())
    b3["pacing"]["length_s"], b3["gameplay"]["ending"], b3["gameplay"]["hesitations"] = 60.0, "cliffhanger", 1
    prompt3 = "Make a level like this picture, no hesitation, no mistakes, a cliffhanger, 60 seconds."
    r3 = _reading(columns=7, rows=7, blocks=6)
    prov3 = IP.apply(b3, prompt3, r3, IP.decide(prompt3, r3))
    IP.fill_play(b3, prompt3, prov3)
    assert "does not change the difficulty" in prov3["play_fill"]["limit"]  # nothing allowed: the limit is said


def test_g1_the_play_fills_the_ad_row(tmp_path, monkeypatch):
    vdir, record = _made(tmp_path, monkeypatch)
    b, prov = _spec("B2", _reading())
    _parts(vdir, 12.0, 30.0)
    row = IA.play_fills_row(prov, record, vdir)
    assert row["status"] == "failed" and row["where"] == "level" and "12.0 s of the 30 s" in row["detail"]
    _parts(vdir, 18.0, 30.0)
    assert IA.play_fills_row(prov, record, vdir)["status"] == "pass"
    prov["board"]["named"] = ["blocks"]
    prov["play_fill"] = {"limit": "about 13 s of play in a 30 s ad: the count is the request's"}
    _parts(vdir, 12.0, 30.0)
    assert IA.play_fills_row(prov, record, vdir)["status"] == "info"


def test_g1_a_thin_play_miss_raises_the_filled_blocks_never_the_difficulty():
    from cbj.workflows import image_guided as W
    b, prov = _spec("B2", _reading(blocks=6, columns=7, rows=7))
    after = json.loads(json.dumps(b))
    after["level"]["difficulty"] = "easy"
    W.pin_level(PROMPTS["B2"][1], b, after, [{"check": "Image: the play fills the ad", "status": "failed", "where": "level"}])
    assert after["level"]["blocks"] == b["level"]["blocks"] + 2 and after["level"]["difficulty"] == b["level"]["difficulty"]


def test_g2_the_reviewer_reads_what_the_picture_gave_and_its_point_on_passing_rows_starts_no_revision():
    from cbj.workflows import image_guided as W
    r = _reading(colours=[{"name": "coral", "rgb": [240, 109, 98], "measured": True, "source": "pixels"},
                          {"name": "teal", "rgb": [140, 211, 188], "measured": True, "source": "pixels"}])
    b, prov = _spec("A2", r)
    IP.restore_repaint(b, prov)
    v = {"id": "c", "n": 1, "brief": b, "checks": [{"check": "Image: the block colours", "status": "pass", "from": "reference"},
                                                   {"check": "Image: the background", "status": "pass", "from": "reference"}],
         "review": {"overall": "fix", "match": [{"control": "visual elements", "verdict": "no", "seen": "the blocks are not sunset"}],
                    "fixes": ["make the blocks sunset coloured"]}}
    shown = W.with_facts(v)
    row = next(x for x in shown["brief"]["controls"] if x["control"] == "visuals")
    assert "MEASURED FROM THE PICTURE" in row["plan"] and "coral #F06D62" in row["plan"]
    assert "MEASURED" not in (next(x for x in v["brief"]["controls"] if x["control"] == "visuals")["plan"] or "")
    assert W.feedback(PROMPTS["A2"][1], v) is None and v["review_set_by_picture"]


def test_g3_a_stuck_moment_points_at_one_piece_and_its_hold_is_measured(tmp_path, monkeypatch):
    b, prov = _spec("B3", _reading())
    b["gameplay"]["events"] = [{"block": {"colour": None, "which": "any", "all": False}, "action": "stuck", "when": "first"}]
    b["gameplay"]["mistakes"] = 2
    notes = IP.name_stuck(b, PROMPTS["B3"][1])
    e = b["gameplay"]["events"][0]
    assert notes and e["block"]["colour"] in ("Red", "Blue") and e["by"] in ("Red", "Blue") and e["by"] != e["block"]["colour"]
    monkeypatch.setattr(studio, "STUDIO", tmp_path)
    (tmp_path / "rec").mkdir()
    drags = [{"result": "placed", "start_frame": 30, "end_frame": 62}, {"result": "exit", "start_frame": 90, "end_frame": 100},
             {"result": "interrupted", "start_frame": 120, "end_frame": 150}]
    (tmp_path / "rec" / "result.json").write_text(json.dumps({"fps": 30, "drags": drags}))
    assert IA.stuck_visible_row(PROMPTS["B3"][1], b, {"recording": {"dir": "rec"}})["status"] == "pass"
    drags[0]["end_frame"] = 40
    (tmp_path / "rec" / "result.json").write_text(json.dumps({"fps": 30, "drags": drags}))
    assert IA.stuck_visible_row(PROMPTS["B3"][1], b, {"recording": {"dir": "rec"}})["status"] == "failed"


def test_g5_a_night_background_is_drawn_as_a_flat_plate(tmp_path, monkeypatch):
    monkeypatch.setattr(studio, "STUDIO", tmp_path / "studio")
    r = _reading()
    r["margins"] = {"top": "#040926", "bottom": "#040927"}
    b, prov = _spec("D2", r)
    line = IP.dark_plate(b, prov)
    name = prov["plate"]
    assert line and "flat plate" in line and ".png" not in line
    assert b["visuals"]["background_image"] == name and b["visuals"]["background"] == ["#040926", "#040927"]
    im = Image.open(tmp_path / "studio" / "uploads" / name).convert("RGB")
    assert im.size == (1080, 1920) and im.getpixel((0, 0)) == (4, 9, 38) and im.getpixel((1079, 1919)) == (4, 9, 39)
    checked = B.check(b, studio.uploads(), set())
    assert checked["visuals"]["background_image"] == name  # an upload the plan may use
    light = _spec("A1", _reading())[1]
    assert IP.dark_plate(B.check(B.default_brief()), light) is None


def test_g6_a_cascade_is_said_as_the_game_plays_it():
    b = B.check(B.default_brief())
    b["concept"]["cascade"] = "One move frees them all!"
    notes = IP.honest_cascade(b, PROMPTS["B2"][1])
    assert b["concept"]["cascade"] is None and any("one drag frees one block" in n for n in notes)


def test_g4_g10_plain_words_and_the_fill_trade_off_said():
    fit = IP.fit_board(14, "open", (5, 6), "varied", True, "free", True, 0.73, judge_blocks=True, judge_packed=False)
    text = " ".join(fit["lines"])
    assert "fill about 50% of the 5x6 board; the picture's is about 73% full" in text
    for bad in ("brief", "MAX_BLOCKS", ".md", "generator"):
        assert bad not in text
    b, prov = _spec("B1", _reading())
    for line in prov["clamps"] + prov["taken"]:
        assert "brief" not in line and ".md" not in line and "pic.png" not in line


def test_g11_the_picture_block_colours_survive_the_shared_check():
    r = _reading(colours=[{"name": "coral", "rgb": [239, 112, 102], "measured": True, "source": "pixels"},
                          {"name": "teal", "rgb": [137, 208, 195], "measured": True, "source": "pixels"},
                          {"name": "mint", "rgb": [143, 228, 173], "measured": True, "source": "pixels"}])
    r["margins"] = {"top": "#FDC79F", "bottom": "#F96676"}
    b, prov = _spec("A2", r)
    checked = B.check(b, {}, set())
    notes = IP.restore_repaint(checked, prov)
    shown = {e["slot"]: e["hex"] for e in checked["visuals"]["blocks"]}
    coral = next(m["slot"] for m in prov["colour_map"] if m["read"] == "coral")
    assert shown[coral] == "#EF7066"  # moved only for the background: restored
    assert any("too close to tell their gates apart" in n for n in notes)
    vals = list(shown.values())
    assert all(B.colour_distance(a, c) >= B.MIN_COLOUR_DISTANCE for i, a in enumerate(vals) for c in vals[i + 1:])


def test_g12_a_palette_word_on_the_blocks_says_which_colours_it_gives():
    r = _reading(colours=[{"name": "teal", "rgb": [137, 208, 195], "measured": True}, {"name": "lemon", "rgb": [250, 244, 103], "measured": True}])
    b, prov = _spec("A2", r)
    lines = IP.palette_choice(b, PROMPTS["A2"][1], prov)
    assert lines and lines[0].startswith("The blocks take the picture's own block colours (teal, lemon); the sunset gradient")
    assert "the blocks in the background's sunset shades" in lines[0]


def test_g3_stuck_steps_are_added_when_the_request_asks_and_the_plan_has_none():
    b, prov = _spec("B3", _reading())
    b["gameplay"].update(mistakes=2, events=[])
    notes = IP.name_stuck(b, PROMPTS["B3"][1])
    assert len(b["gameplay"]["events"]) == 2 and len(notes) == 2
    movers = [e["block"]["colour"] for e in b["gameplay"]["events"]]
    assert movers[0] != movers[1] and all(e["by"] and e["by"] != e["block"]["colour"] for e in b["gameplay"]["events"])


# ---------- G13: a cliffhanger's question follows the live cut ----------

def test_g13a_the_sequence_words_and_fields_agree():
    b = B.check(B.default_brief())
    B.control(b, "sequence")["plan"] = "Hook over the gameplay, then the end card. There is no replay and no result screen."
    notes = IP.sequence_matches(b, "Make a level.")
    assert b["sequence"]["replay"] is False and b["sequence"]["result_screen"] is False and len(notes) == 2
    b = B.check(B.default_brief())
    b["sequence"]["replay"] = False
    B.control(b, "sequence")["plan"] = "The play, then a slow-motion replay of the finish. Then the end card."
    IP.sequence_matches(b, "Make a level.")
    assert "replay" not in B.control(b, "sequence")["plan"]


def test_g13b_a_cliffhanger_plays_no_replay_unless_asked():
    b = B.check(B.default_brief())
    b["gameplay"]["ending"] = "cliffhanger"
    B.control(b, "sequence")["plan"] = "The play, a replay of the last drags, then the question."
    notes = IP.cliffhanger_replay(b, PROMPTS["C2"][1])
    assert b["sequence"]["replay"] is False and notes == [IP.CLIFF_REPLAY_LINE]
    assert B.control(b, "sequence")["plan"].endswith(IP.CLIFF_REPLAY_LINE) and "a replay of the last drags" not in B.control(b, "sequence")["plan"]
    b2 = B.check(B.default_brief())
    b2["gameplay"]["ending"] = "cliffhanger"
    assert IP.cliffhanger_replay(b2, "End on a question, with a slow-motion replay first.") == [] and b2["sequence"]["replay"]
    b3 = B.check(B.default_brief())
    assert IP.cliffhanger_replay(b3, "A win.") == [] and b3["sequence"]["replay"]  # other endings keep theirs


def test_g13c_the_question_row_reads_the_parts(tmp_path, monkeypatch):
    vdir, record = _made(tmp_path, monkeypatch)
    b = B.check(B.default_brief())
    b["gameplay"]["ending"] = "cliffhanger"
    parts = [{"id": "intro", "kind": "still", "name": "the still opening", "from_s": 0, "to_s": 0.5},
             {"id": "play", "kind": "gameplay", "name": "the gameplay", "from_s": 0.5, "to_s": 15.0},
             {"id": "replay", "kind": "replay", "name": "a slow-motion replay", "from_s": 15.0, "to_s": 18.7},
             {"id": "question", "kind": "still", "name": "the question", "from_s": 18.7, "to_s": 23.2},
             {"id": "end", "kind": "card", "name": "the end card", "from_s": 23.2, "to_s": 30.0}]
    (vdir / "parts.json").write_text(json.dumps({"parts": parts}))
    row = IA.question_row(PROMPTS["C2"][1], b, vdir)
    assert row["status"] == "failed" and "a slow-motion replay 3.7 s" in row["detail"]
    (vdir / "parts.json").write_text(json.dumps({"parts": [x for x in parts if x["id"] != "replay"]}))
    assert IA.question_row(PROMPTS["C2"][1], b, vdir)["status"] == "pass"
    (vdir / "parts.json").write_text(json.dumps({"parts": parts}))
    assert IA.question_row("End on a question after a replay.", b, vdir)["status"] == "info"


def test_g14_no_caption_promises_pairs_or_clears_together():
    b = B.check(B.default_brief())
    b["concept"]["hook"] = "Clear it in perfect pairs"
    b["concept"]["result"] = "Both at once!"
    notes = IP.honest_cascade(b, PROMPTS["C3"][1])
    assert b["concept"]["hook"] is None and b["concept"]["result"] is None and len(notes) == 2
    b["concept"]["hook"] = "Can you clear the cross?"
    assert IP.honest_cascade(b, PROMPTS["C3"][1]) == [] and b["concept"]["hook"] == "Can you clear the cross?"
    b["concept"]["hook"] = "Two at a time"
    IP.honest_cascade(b, 'Use the hook "Two at a time" on a level like this picture.')
    assert b["concept"]["hook"] == "Two at a time"  # quoted by the request: the request's own words
    v = IP.planner_view(_reading(), IP.decide(PROMPTS["C2"][1], _reading()))
    assert "one drag frees one block" in v["notes"]["game_fact"]


# ---------- G15: a cliffhanger's question is a real choice ----------

def _trap_level(path: Path) -> Path:
    one = [{"x": 0, "y": 0}]
    path.write_text(json.dumps({"gridWidth": 4, "gridHeight": 1, "timerCount": 60, "inactiveCells": [],
                                "GridBlockDatas": [{"gridPosition": {"x": 0, "y": 0}, "blockColor": 2, "shapeOffsets": one},
                                                   {"gridPosition": {"x": 1, "y": 0}, "blockColor": 5, "shapeOffsets": one}],
                                "ExitDatas": [{"exitNumber": 0, "gridPosition": {"x": 3, "y": 0}, "requiredColor": 2, "direction": 1, "shapeOffsets": one},
                                              {"exitNumber": 0, "gridPosition": {"x": 1, "y": 0}, "requiredColor": 5, "direction": 2, "shapeOffsets": one}]}))
    return path


def test_g15_the_cut_moves_to_where_a_block_is_trapped():
    from cbj.level import load_level
    from cbj.workflows import image_guided as W
    level = Path(__file__).resolve().parents[1] / "data" / "levels" / "gen" / "narrow_center_01.json"
    c = IP.cut_choice(load_level(level), 2)
    assert c["left"] == 3 and c["trapped"] != c["blocker"] and "is still blocked by" in c["words"]
    b, prov = _spec("D1", _reading(hud=False))
    b["gameplay"]["ending"], b["concept"]["result"] = "cliffhanger", "Which one goes first?"
    planned = IP.cut_choice_planned(load_level(level), 2, b)
    assert planned and planned["left"] == 2 and planned["source"] == "the take's planned path"  # the bare solve needed 3
    notes = W.real_cut(studio.Log(), PROMPTS["D1"][1], b, resolve=lambda br: (level, "test"))
    assert b["gameplay"]["blocks_left"] == 2 and "\"Which one goes first?\" is a real choice" in notes[0]
    b1, _ = _spec("B1", _reading())
    b1["gameplay"].update(ending="cliffhanger", blocks_left=3)
    W.real_cut(studio.Log(), PROMPTS["B1"][1], b1, resolve=lambda br: (level, "test"))
    assert b1["gameplay"]["blocks_left"] == 3  # the request's own count is kept


def test_g15_the_real_choice_row_rebuilds_the_cut(tmp_path, monkeypatch):
    vdir, record = _made(tmp_path, monkeypatch)
    _trap_level(vdir / "level.json")
    job = {"hide": [], "drags": [{"block": 1, "path": [{"x": 1, "y": 0}], "exits": False}]}  # the last drag: the final push
    (tmp_path / "studio" / "recordings" / "r1" / "job.json").write_text(json.dumps(job))
    b = B.check(B.default_brief())
    b["gameplay"]["ending"] = "cliffhanger"
    row = IA.real_choice_row(PROMPTS["D1"][1], b, record, vdir)
    assert row["status"] == "pass" and "the blue block cannot leave yet" in row["detail"]
    one = [{"x": 0, "y": 0}]
    (vdir / "level.json").write_text(json.dumps({"gridWidth": 4, "gridHeight": 1, "timerCount": 60, "inactiveCells": [],
        "GridBlockDatas": [{"gridPosition": {"x": 0, "y": 0}, "blockColor": 2, "shapeOffsets": one},
                           {"gridPosition": {"x": 3, "y": 0}, "blockColor": 5, "shapeOffsets": one}],
        "ExitDatas": [{"exitNumber": 0, "gridPosition": {"x": 0, "y": 0}, "requiredColor": 2, "direction": 0, "shapeOffsets": one},
                      {"exitNumber": 0, "gridPosition": {"x": 3, "y": 0}, "requiredColor": 5, "direction": 1, "shapeOffsets": one}]}))
    (tmp_path / "studio" / "recordings" / "r1" / "job.json").write_text(json.dumps(
        {"hide": [], "drags": [{"block": 1, "path": [{"x": 3, "y": 0}], "exits": False}]}))  # two free blocks
    row = IA.real_choice_row(PROMPTS["D1"][1], b, record, vdir)
    assert row["status"] == "failed" and "every one could leave at once" in row["detail"]
    assert IA.real_choice_row(PROMPTS["B1"][1], b, record, vdir)["status"] == "info"  # the request names the count


def test_g15_a_miss_raises_the_blocks_left_and_d3_colours_are_said():
    from cbj.workflows import image_guided as W
    b, prov = _spec("D1", _reading(hud=False))
    b["gameplay"].update(ending="cliffhanger", blocks_left=2)
    after = json.loads(json.dumps(b))
    W.pin_level(PROMPTS["D1"][1], b, after, [{"check": "Image: the cliffhanger is a real choice", "status": "failed", "where": "play"}])
    assert after["gameplay"]["blocks_left"] == 3
    prov = {"board": {"named": ["colours"], "filled": [], "seen": {"colours": ["a", "b", "c", "d"]},
                      "built": {"colours": ["Red", "Blue", "Green", "Yellow"]}}}
    made = {"columns": 7, "rows": 8, "blocks": 6, "colours": ["Red", "Blue"], "shape": "open", "fill": 0.4, "mean_cells": 4,
            "bars": False, "mirror": [0, 0], "symmetric": False}
    row = IA.board_rows(prov, made)[0]
    assert "4 colours allowed from the picture, the level uses 2 of them (6 blocks on 7x8)" in row["detail"]


# ---------- G16: a thin play at the limit, at a fast tempo ----------

def _b2_brief(prompt):
    r = _reading(blocks=14, columns=5, rows=6, pieces="small", occupancy=0.73)
    b = B.check(B.default_brief())
    b["gameplay"]["ending"], b["pacing"]["length_s"] = "win", 30.0
    prov = IP.apply(b, prompt, r, IP.decide(prompt, r))
    IP.request_values(b, prompt)
    return b, prov


def test_g16_an_at_limit_fast_board_gets_an_early_beat_and_the_estimate_is_calibrated():
    b, prov = _b2_brief(PROMPTS["B2"][1])
    assert b["level"]["blocks"] == 10 and b["pacing"]["tempo"] == "fast" and b["gameplay"]["finish"] == "streak"
    from cbj.videoref import expected_play as table
    assert IP.expected_play(b, 10) == pytest.approx(table(b, "fast", IP._moves(b, 10))[0] * IP.FAST_PLAY_SCALE)
    notes = IP.fill_play(b, PROMPTS["B2"][1], prov)
    assert (b["gameplay"]["mistakes"] or 0) + (b["gameplay"]["hesitations"] or 0) >= 1
    assert any("10 blocks is the most one level takes" in n and "the finish stays fast" in n for n in notes)


def test_g16_no_lever_left_gives_an_info_row_and_no_revision(tmp_path, monkeypatch):
    from cbj import planner
    from cbj.workflows import image_guided as W
    prompt = "A board as crowded as this one, in the game's own look, a flawless fast cascade win with no mistakes and no hesitation. 30 seconds."
    b, prov = _b2_brief(prompt)
    IP.fill_play(b, prompt, prov)
    pf = prov["play_fill"]
    assert pf["levers_left"] == [] and pf["limit"] and "does not change the difficulty" in pf["limit"]
    vdir, record = _made(tmp_path, monkeypatch)
    _parts(vdir, 13.5, 30.0)
    row = IA.play_fills_row(prov, record, vdir)
    assert row["status"] == "info" and "the limit, said in the plan" in row["detail"]
    v = {"id": "c", "n": 1, "brief": b, "checks": [dict(row, status="failed", where="level")], "review": None}
    monkeypatch.setattr(planner, "plan", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no revision may plan")))
    out = W.revise_once(studio.Log(), prompt, v, False)
    assert out["revision"]["status"] == "unchanged" and "no lever" in out["revision"]["why"]


# ---------- G17: B3's three defects ----------

def test_g17_the_stuck_row_judges_only_the_planned_stuck_drags(tmp_path, monkeypatch):
    b, prov = _spec("B3", _reading())
    b["gameplay"]["mistakes"] = 2
    monkeypatch.setattr(studio, "STUDIO", tmp_path)
    (tmp_path / "rec").mkdir()
    drags = [{"result": "placed", "start_frame": 0, "end_frame": 30}, {"result": "placed", "start_frame": 40, "end_frame": 88},
             {"result": "placed", "start_frame": 100, "end_frame": 115}, {"result": "exit", "start_frame": 120, "end_frame": 130},
             {"result": "interrupted", "start_frame": 140, "end_frame": 170}]
    beats = [{"kind": "mistake"}, {"kind": "mistake"}, {"kind": "solve"}, {"kind": "solve"}, {"kind": "solve"}]
    (tmp_path / "rec" / "result.json").write_text(json.dumps({"fps": 30, "drags": drags}))
    (tmp_path / "rec" / "play.json").write_text(json.dumps({"beats": beats}))
    row = IA.stuck_visible_row(PROMPTS["B3"][1], b, {"recording": {"dir": "rec"}})
    assert row["status"] == "pass" and "1.0 s, 1.6 s" in row["detail"] and "0.5 s" not in row["detail"]


def _fill_level(path: Path, n: int) -> Path:
    sq = [{"x": 0, "y": 0}, {"x": 0, "y": -1}, {"x": 1, "y": -1}, {"x": 1, "y": 0}]
    spots = [(0, 1), (2, 1), (0, 3), (2, 3)][:n]
    path.write_text(json.dumps({"gridWidth": 4, "gridHeight": 4, "timerCount": 60, "inactiveCells": [],
                                "GridBlockDatas": [{"gridPosition": {"x": x, "y": y}, "blockColor": c, "shapeOffsets": sq}
                                                   for (x, y), c in zip(spots, (2, 5, 0, 3))],
                                "ExitDatas": [{"exitNumber": 0, "gridPosition": {"x": i, "y": 3}, "requiredColor": c, "direction": 2,
                                               "shapeOffsets": [{"x": 0, "y": 0}]} for i, c in enumerate((2, 5, 0, 3)[:n])]}))
    return path


def test_g17_a_packed_board_is_measured_on_the_built_level_and_a_clamp_is_judged_against_it(tmp_path, monkeypatch):
    from cbj.workflows import image_guided as W
    low, high = _fill_level(tmp_path / "low.json", 2), _fill_level(tmp_path / "high.json", 3)
    b, prov = _spec("B3", _reading(blocks=14, columns=4, rows=4, pieces="mixed", occupancy=0.73))
    monkeypatch.setattr(studio, "_cannot_play", lambda br, path: None)
    start = b["level"]["pieces"]
    notes = W.fit_fill(studio.Log(), PROMPTS["B3"][1], b, resolve=lambda br: (high if br["level"]["pieces"] != start else low, "t"))
    assert b["level"]["pieces"] == W.PIECE_ORDER[W.PIECE_ORDER.index(start) + 1]  # one class bigger
    assert prov["board"]["built"]["fill_generated"] == 0.75 and notes
    prov["board"]["built"]["fill_generated"] = 0.57  # a board as full as the tool builds here, under the bar
    made = {"columns": 5, "rows": 6, "blocks": 9, "colours": [], "shape": "open", "fill": 0.55, "mean_cells": 2.3, "bars": False,
            "mirror": [0, 0], "symmetric": False}
    packed = next(x for x in IA.board_rows(prov, made) if x["check"] == "Image: packed")
    assert packed["status"] == "pass" and "the most it builds here" in packed["detail"]
    made["fill"] = 0.50
    assert next(x for x in IA.board_rows(prov, made) if x["check"] == "Image: packed")["status"] == "failed"


def test_g17_a_level_lever_never_loses_a_planned_step_and_asked_misses_weigh_more(tmp_path, monkeypatch):
    from cbj.workflows import image_guided as W
    b, prov = _spec("B3", _reading())
    b["gameplay"]["events"] = [{"block": {"colour": "Red", "which": "any", "all": False}, "action": "stuck", "when": "next", "by": "Blue"}]
    after = json.loads(json.dumps(b))
    after["level"]["blocks"] = 10
    after["changed"] = ["level.blocks"]
    monkeypatch.setattr(studio, "_cannot_play", lambda br, path: "the yellow block gets stuck: not shown")
    notes = W.keep_steps(studio.Log(), b, after, resolve=lambda br: (tmp_path / "x.json", "t"))
    assert after["level"] == b["level"] and "the board is kept" in notes[0] and "level.blocks" not in after["changed"]
    asked = {"check": "Asked: order of interactions", "status": "failed", "from": "prompt"}
    filled = {"check": "Image: packed", "status": "failed", "from": "reference"}
    v1 = {"id": "c", "n": 1, "checks": [filled], "review": {"overall": "fix"}}
    v2 = {"id": "c", "n": 2, "checks": [asked], "review": {"overall": "ship"}}
    assert W.best_version(studio.Log(), [v1, v2])["n"] == 1


# ---------- round 3's findings (2026-10-18, H1-H16, the edited screens) ----------

def test_h1_the_read_piece_class_is_built_first_and_one_class_smaller_only_when_it_does_not_fit(tmp_path):
    from cbj.workflows import image_guided as W
    assert IP.fit_board(10, "ring", (9, 10), "big", True, "free", False, 0.7)["pieces"] == "big"
    b, prov = _spec("D3", _reading(blocks=10, columns=9, rows=10, pieces="big", occupancy=0.7))
    prov["board"]["seen"]["pieces"], b["level"]["pieces"], b["level"]["blocks"] = "big", "big", 4
    four, two = _fill_level(tmp_path / "four.json", 4), _fill_level(tmp_path / "two.json", 2)
    assert W.verify_pieces(studio.Log(), b, resolve=lambda br: (four, "t")) == [] and b["level"]["pieces"] == "big"
    notes = W.verify_pieces(studio.Log(), b, resolve=lambda br: (two, "t"))
    assert b["level"]["pieces"] == "long" and "could not all be placed (2 of 4), so long pieces are built" in notes[0]
    assert notes[0] in b["assumptions"]


def test_h2_the_badge_and_the_timer_are_read_apart():
    assert IA.expected_hud("Use the picture's neon lab look; hide the level badge as the picture does but keep the timer.", {})[0] == (False, True)
    assert IA.expected_hud("Hide the timer.", {})[0] == (True, False)
    assert IA.expected_hud("No HUD at all.", {})[0] == (False, False)


def test_h3_a_picture_without_a_caption_gives_its_accent_to_the_captions():
    r = _reading()
    r.update(caption_measured=None, captions=[], margins={"top": "#101830", "bottom": "#0A0F20"},
             palette=[{"hex": "#101830", "share": 0.6}, {"hex": "#22D3EE", "share": 0.1}, {"hex": "#808080", "share": 0.1}])
    kit = IP.style_kit(r, ["background", "captions"])
    assert kit["caption_fill"] == "#22D3EE" and "accent colour #22D3EE" in kit["caption_source"] and kit["legible"]
    r["palette"] = [{"hex": "#101830", "share": 0.9}]  # nothing saturated: white stays the fallback
    assert IP.style_kit(r, ["background", "captions"])["caption_fill"] == "#FFFFFF"


def test_h4_a_unanimous_size_read_stands_over_a_low_fill_measure():
    r = _reading(columns=7, rows=9, blocks=9, occupancy=0.24, size_spread=0, size_reads=[[7, 9]] * 3, pieces="varied")
    b, prov = _spec("D3", r)
    assert (b["level"]["width"], b["level"]["height"]) == (7, 9)
    assert IP.size_from_fill(dict(r["board"]), "open", (7, 9), "varied", (7, 9)) is None


def test_h5_a_cliffhanger_plays_about_seventy_percent_of_the_ad():
    r = _reading(columns=7, rows=7, blocks=6, pieces="varied", occupancy=None)
    b = B.check(B.default_brief())
    b["pacing"]["length_s"], b["gameplay"]["ending"] = 40.0, "cliffhanger"
    prompt = "Make a calm creative with a board shaped like this one, a cliffhanger, 40 seconds."
    prov = IP.apply(b, prompt, r, IP.decide(prompt, r))
    IP.fill_play(b, prompt, prov)
    assert prov["play_fill"]["goal"] == IP.PLAY_SHARE_CLIFF == 0.7 and b["level"]["blocks"] > 6
    b2 = B.check(B.default_brief())
    b2["pacing"]["length_s"], b2["gameplay"]["ending"] = 40.0, "win"
    prov2 = IP.apply(b2, prompt, r, IP.decide(prompt, r))
    IP.fill_play(b2, prompt, prov2)
    assert prov2["play_fill"]["goal"] == IP.PLAY_SHARE_PLAN


def test_h6_colours_the_request_names_are_judged_as_the_request_names_them():
    prompt = "Make a creative with a plus-shaped board like this one, with only blue and orange blocks as in the picture."
    r = _reading(colours=[{"name": "blue", "rgb": [47, 105, 235]}, {"name": "orange", "rgb": [240, 140, 40]}])
    b, prov = B.check(B.default_brief()), None
    prov = IP.apply(b, prompt, r, IP.decide(prompt, r))
    assert prov["board"]["built"]["colours_by"] == "request"
    made = {"columns": 5, "rows": 6, "blocks": 8, "colours": ["Blue", "Orange"], "shape": "cross", "fill": 0.6, "mean_cells": 3,
            "bars": False, "mirror": [0, 0], "symmetric": False}
    row = next(x for x in IA.board_rows(prov, made) if x["check"] == "Image: the board's colours")
    assert row["status"] in ("info", "pass") and "0 of 0" not in row["detail"]
    prov["board"]["built"]["colours"] = ["Blue", "Orange"]
    row = next(x for x in IA.board_rows(prov, made) if x["check"] == "Image: the board's colours")
    assert row["status"] == "pass" and "the request names blue, orange" in row["detail"]


def test_h7_a_shared_row_missed_twice_alike_stops_the_loop_and_says_the_limit(tmp_path, monkeypatch):
    from cbj.workflows import image_guided as W
    miss = {"check": "Asked: difficulty", "status": "failed", "detail": "medium-to-hard (asked: hard)", "from": "prompt", "where": "level"}
    v1 = {"id": "c", "n": 1, "checks": [miss], "review": None}
    v2 = {"id": "c", "n": 2, "checks": [dict(miss)], "review": None, "revision": {"status": "made"}}
    assert W.repeated_miss(v1, v2)["check"] == "Asked: difficulty"
    assert W.repeated_miss(v1, {"checks": [dict(miss, detail="medium (asked: hard)")]}) is None
    image_only = {"check": "Image: packed", "status": "failed", "detail": "x", "where": "level"}
    assert W.repeated_miss({"checks": [image_only]}, {"checks": [image_only]}) is None  # image rows have their own levers
    monkeypatch.setattr(studio, "STUDIO", tmp_path)
    for f in ("verify_pieces", "playable", "fit_fill", "real_cut"):
        monkeypatch.setattr(W, f, lambda *a, **k: [])
    monkeypatch.setattr(studio, "make", lambda *a, **k: dict(v1))
    monkeypatch.setattr(W, "evaluated", lambda log, p, v: v)
    made = []
    monkeypatch.setattr(W, "revise_once", lambda log, p, v, r: made.append(1) or dict(v2, n=len(made) + 1))
    out = W.make(studio.Log(), "x", B.check(B.default_brief()))
    assert len(made) == 1 and out["limit_note"] == "Asked: difficulty: medium-to-hard (asked: hard)"


def test_h8_the_plan_words_say_the_picture_size_and_count():
    b, prov = _spec("D3", _reading(columns=5, rows=7, blocks=6, size_spread=0, size_reads=[[5, 7]] * 3))
    lv = b["level"]
    wrong, right = "I read 'small' as a 6 by 6 board.", f"The board is {lv['width']}x{lv['height']}."
    b["assumptions"] += [wrong, right]
    notes = IP.reconcile_numbers(b, prov, [wrong, right])
    assert wrong not in b["assumptions"] and right in b["assumptions"] and "6 by 6" in notes[0]


def test_h9_the_picture_glow_is_its_measured_background_and_a_worded_background_is_judged_against_the_plan(tmp_path, monkeypatch):
    s8 = ("Match this picture's board: as crowded, the same number of blocks and all of its colours, with the arcade "
          "purple-to-pink glow for the background. End on the question \"Which one first?\" with three blocks left. 45 seconds.")
    d = IP.decide(s8, _reading())
    assert "style" in d["roles"] and "background" in d["style"]["parts"]
    vdir, record = _made(tmp_path, monkeypatch, bg="#933091")
    prompt = "Make a board like this one, in the game's own block colours. Put it on a deep-space background."
    b, prov = B.check(B.default_brief()), None
    r = _reading()
    prov = IP.apply(b, prompt, r, IP.decide(prompt, r))
    b["visuals"]["background"] = ["#933091", "#933091"]  # the planner's own, from the words
    row = _rowmap(IA.rows(prompt, b, record, vdir))["Image: not taken stays the game's own"]
    assert row["status"] == "pass" and "set by the words" in row["detail"]


def test_h10_as_crowded_as_the_picture_is_its_fill_and_the_shared_packed_row_is_info():
    s8 = ("Match this picture's board: as crowded, the same number of blocks and all of its colours, with the arcade "
          "purple-to-pink glow for the background. 45 seconds.")
    r = _reading(occupancy=0.33, columns=9, rows=10, blocks=10)
    b = B.check(B.default_brief())
    prov = IP.apply(b, s8, r, IP.decide(s8, r))
    assert "packed" not in b["level"]["style"] and prov["board"]["built"]["fill_target"] == 0.33
    made = {"columns": 9, "rows": 10, "blocks": 10, "colours": [], "shape": "open", "fill": 0.40, "mean_cells": 3, "bars": False,
            "mirror": [0, 0], "symmetric": False}
    row = next(x for x in IA.board_rows(prov, made) if x["check"] == "Image: as crowded as the picture")
    assert row["status"] == "pass" and "about 33% full" in row["detail"]
    shared = {"check": "Asked: packed board", "status": "failed", "detail": "40 % (packed: 55 % or more)", "where": "level", "from": "prompt"}
    out = IA.rejudge(s8, b, [shared])[0]
    assert out["status"] == "info" and "about 33%" in out["detail"] and out["where"] is None


def test_h11_an_ending_the_board_cannot_play_tries_other_seeds_then_a_block_then_the_nearest_ending(tmp_path, monkeypatch):
    from cbj.workflows import image_guided as W
    lvl = _fill_level(tmp_path / "l.json", 3)
    b, prov = _spec("D3", _reading(blocks=6))
    b["gameplay"].update(ending="time_out", seed=0)
    b["level"]["blocks"] = 6
    no = ValueError("plan: the last block is one cell from its gate; a time-out needs a last exit of at least two cells")
    tried = []

    def plan(br, level, seed):
        tried.append((seed, br["level"]["blocks"]))
        if seed == 2:
            return object()
        raise no
    monkeypatch.setattr(studio, "_plan", plan)
    notes = W.playable(studio.Log(), "x", b, resolve=lambda br: (lvl, "t"))
    assert b["gameplay"]["seed"] == 2 and "seed 2 plays it" in notes[0] and b["gameplay"]["ending"] == "time_out"
    b["gameplay"]["seed"] = 0
    monkeypatch.setattr(studio, "_plan", lambda br, level, seed: object() if br["level"]["blocks"] == 7 else (_ for _ in ()).throw(no))
    notes = W.playable(studio.Log(), "x", b, resolve=lambda br: (lvl, "t"))
    assert b["level"]["blocks"] == 7 and "one more block (7)" in notes[0]
    b["level"]["blocks"] = 6
    monkeypatch.setattr(studio, "_plan", lambda *a: (_ for _ in ()).throw(no))
    notes = W.playable(studio.Log(), "x", b, resolve=lambda br: (lvl, "t"))
    assert b["gameplay"]["ending"] == "near_fail" and b["gameplay"]["seed"] == 0 and b["level"]["blocks"] == 6
    assert "ends as a near-fail" in notes[0] and "two cells" in notes[0] and notes[0] in b["assumptions"]
    monkeypatch.setattr(studio, "_plan", lambda *a: (_ for _ in ()).throw(RuntimeError("generator")))
    W.playable(studio.Log(), "x", b, resolve=lambda br: (_ for _ in ()).throw(RuntimeError("no level")))  # never raises


def test_h12_the_blocks_too_switches_the_block_colours_on_and_a_revision_never_keeps_invented_ones():
    p = "Use this picture's underwater colours on everything, the blocks too."
    d = IP.decide(p, _reading())
    assert "blocks" in d["style"]["parts"]
    for words in ("Use the picture's palette on the background, blocks included.", "Its colours on everything."):
        assert "blocks" in IP.decide(words, _reading())["style"]["parts"], words
    b, prov = _spec("A1", _reading())  # "keep the game's own block colours"
    b["visuals"]["blocks"] = [{"slot": "Red", "hex": "#FF2E88", "name": "neon pink"}]  # a revision's planner repainted them
    notes = IP.clear_invented_blocks(b, PROMPTS["A1"][1], prov)
    assert b["visuals"]["blocks"] == [] and "neon pink" in notes[0]
    b2, prov2 = _spec("A2", _reading(colours=[{"name": "coral", "rgb": [248, 140, 128]}]))
    kept = list(b2["visuals"]["blocks"])
    assert IP.clear_invented_blocks(b2, PROMPTS["A2"][1], prov2) == [] and b2["visuals"]["blocks"] == kept


def test_h13_a_length_beyond_one_level_is_said_and_the_fill_row_is_info(tmp_path, monkeypatch):
    r = _reading(columns=9, rows=10, blocks=9, pieces="big", occupancy=None)
    b = B.check(B.default_brief())
    b["pacing"]["length_s"], b["gameplay"]["ending"], b["pacing"]["tempo"] = 60.0, "near_fail", "fast"
    prompt = "Make a fast creative with a board shaped like this one, a near-fail. 60 seconds."
    prov = IP.apply(b, prompt, r, IP.decide(prompt, r))
    notes = IP.fill_play(b, prompt, prov)
    pf = prov["play_fill"]
    assert b["level"]["blocks"] == 10 and pf.get("beyond") and pf["levers_left"] == []
    assert any("one level of 10 blocks fills about" in n and "30-45 s would be tighter" in n for n in notes)
    vdir, record = _made(tmp_path, monkeypatch)
    _parts(vdir, 27.0, 60.0)
    assert IA.play_fills_row(prov, record, vdir)["status"] == "info"


def test_h15_inspired_by_takes_the_measured_block_colours_and_a_not_taken_repaint_is_cleared():
    p = "Create a Color Block Jam creative inspired by this image."
    b, prov = B.check(B.default_brief()), None
    r = _reading(colours=[{"name": "coral", "rgb": [248, 140, 128]}, {"name": "lemon", "rgb": [255, 245, 80]}])
    prov = IP.apply(b, p, r, IP.decide(p, r))
    assert "visuals.colours" in prov["set"] and IP.clear_invented_blocks(b, p, prov) == []
    assert any(e["name"] == "coral" and e["hex"] == "#F88C80" for e in b["visuals"]["blocks"])  # measured, not invented
    one = B.check(B.default_brief())
    r1 = _reading(colours=[{"name": "coral", "rgb": [248, 140, 128]}])  # too few colours to repaint: the game's own
    prov1 = IP.apply(one, p, r1, IP.decide(p, r1))
    one["visuals"]["blocks"] = [{"slot": "Red", "hex": "#FF2E88", "name": "neon pink"}]
    assert IP.clear_invented_blocks(one, p, prov1) and one["visuals"]["blocks"] == []
    b1, prov1 = _spec("B2", _reading())  # the board only, in the game's own look
    b1["visuals"]["blocks"] = [{"slot": "Blue", "hex": "#2EC8FF", "name": "neon blue"}]
    IP.clear_invented_blocks(b1, PROMPTS["B2"][1], prov1)
    assert b1["visuals"]["blocks"] == []
    own = "Make a board like this one with coral blocks."
    b2, _ = B.check(B.default_brief()), None
    prov2 = IP.apply(b2, own, _reading(), IP.decide(own, _reading()))
    b2["visuals"]["blocks"] = [{"slot": "Red", "hex": "#F88C80", "name": "coral"}]
    assert IP.clear_invented_blocks(b2, own, prov2) == [] and b2["visuals"]["blocks"]  # the words name them


def test_h16_the_named_family_wins_over_the_rgb_distance_and_a_cross_mapping_is_flagged():
    m = IP.colour_map([{"name": "light green", "rgb": [151, 207, 126]}])
    assert m[0]["slot"] == "Green" and not m[0]["cross"]
    m = IP.colour_map([{"name": "green", "rgb": [60, 200, 60]}, {"name": "dark green", "rgb": [20, 100, 40]},
                       {"name": "light green", "rgb": [151, 207, 126]}])
    assert [x["slot"] for x in m[:2]] == ["Green", "DarkGreen"] and m[2]["cross"]
    for name, rgb, slot in (("magenta", [220, 40, 200], "Purple"), ("coral", [248, 120, 100], "Orange"), ("teal", [40, 160, 160], "Blue")):
        assert IP.colour_map([{"name": name, "rgb": rgb}])[0]["slot"] == slot, name
    prov = {"board": {"named": [], "filled": []}, "colour_map": m}
    row = next(x for x in IA.board_rows(prov, {"blocks": 0}) if x["check"] == "Image: the colours keep their family")
    assert row["status"] == "info" and "light green -> yellow" in row["detail"]


# ---------- round 3's rerun follow-ups (2026-10-18, H3b-H20) ----------

def test_h17_a_planned_stuck_step_that_cannot_play_is_replanned_on_this_board(tmp_path, monkeypatch):
    from cbj.workflows import image_guided as W
    lvl = _fill_level(tmp_path / "l.json", 3)  # blue, purple, green: one block each
    b, prov = _spec("B3", _reading())
    b["gameplay"].update(seed=0, events=[{"block": {"colour": "Red", "which": "any", "all": False}, "action": "stuck",
                                          "when": "next", "by": "Yellow"}])
    calls = []

    def cannot(br, path):
        e = br["gameplay"]["events"][0] if br["gameplay"]["events"] else None
        calls.append((br["gameplay"]["seed"], e and e["block"]["colour"], e and e.get("by")))
        return None if e and e["block"]["colour"] == "Blue" and e["by"] == "Green" else "the red block gets stuck: not shown"
    monkeypatch.setattr(studio, "_cannot_play", cannot)
    notes = W.keep_events(studio.Log(), "x", b, resolve=lambda br: (lvl, "t"))
    assert [c[0] for c in calls[:4]] == [0, 1, 2, 3]  # three more seeds first
    ev = b["gameplay"]["events"][0]
    assert (ev["block"]["colour"], ev["by"]) == ("Blue", "Green") and b["gameplay"]["seed"] == 0
    assert "the blue block heads for its gate and a green block is in the way" in notes[0] and notes[0] in b["assumptions"]
    b["gameplay"]["events"] = [dict(ev, block=dict(ev["block"], colour="Red"), by="Yellow")]
    monkeypatch.setattr(studio, "_cannot_play", lambda br, path: None if not br["gameplay"]["events"] else "not shown")
    notes = W.keep_events(studio.Log(), "x", b, resolve=lambda br: (lvl, "t"))
    assert b["gameplay"]["events"] == [] and "played as an ordinary one" in notes[0]
    monkeypatch.setattr(studio, "_cannot_play", lambda *a: (_ for _ in ()).throw(RuntimeError("x")))
    b["gameplay"]["events"] = [ev]
    assert W.keep_events(studio.Log(), "x", b, resolve=lambda br: (lvl, "t"))  # never raises


def test_h7b_a_miss_repeated_with_other_numbers_is_the_same_verdict():
    from cbj.workflows import image_guided as W
    d1 = "a generated level: 12 drags minimum, 2 repositioning: medium-to-hard (asked: hard)"
    d2 = "a generated level: 13 drags minimum, 3 repositioning: medium-to-hard (asked: hard)"
    assert W.verdict(d1) == W.verdict(d2) == "medium-to-hard (asked: hard)"
    s6 = ["12 drags minimum, 2 repositioning, 1 block(s) can leave at once, a casual player needs about 2.3x the minimum "
          "-> medium-to-hard (asked: hard)", "13 drags minimum, 3 repositioning, 2 block(s) can leave at once, a casual "
          "player needs about 3.9x the minimum -> medium-to-hard (asked: hard)"]  # S6's rerun, v1 and v2
    assert W.verdict(s6[0]) == W.verdict(s6[1])
    assert W.verdict("easy -> 14 drags, medium") == "drags, medium"
    lv = {"level": {"blocks": 10}}
    miss = lambda d: {"check": "Asked: difficulty", "status": "failed", "detail": d, "from": "prompt"}  # noqa: E731
    v1, v2 = {"brief": lv, "checks": [miss(d1)]}, {"brief": lv, "checks": [miss(d2)]}
    assert W.repeated_miss(v1, v2)["check"] == "Asked: difficulty"
    assert W.repeated_miss(v1, {"brief": lv, "checks": [miss("... medium (asked: hard)")]}) is None
    assert W.repeated_miss(v1, {"brief": {"level": {"blocks": 8}}, "checks": [miss(d2)]}) is None  # another limit state


def test_h20_a_time_out_blocks_left_is_planned_or_its_limit_said_and_judged(tmp_path, monkeypatch):
    s9 = "A mirror-symmetric two-room level like this picture. The clock runs out with two blocks left. 40 seconds."
    b, prov = B.check(B.default_brief()), None
    prov = IP.apply(b, s9, _reading(), IP.decide(s9, _reading()))
    b["gameplay"]["ending"] = "time_out"
    notes = IP.time_out_left(b, s9)
    assert "cannot stop with 2 blocks" in notes[0] and prov["time_out_left"] == {"asked": 2, "played": 1}
    assert IP.time_out_left(b, "The clock runs out with one block left.") == []
    vdir, record = _made(tmp_path, monkeypatch)
    rec = tmp_path / "studio" / "recordings" / "r1"
    (rec / "result.json").write_text(json.dumps({"block_gone_frames": [10, None, 30]}))
    row = IA.blocks_left_row(s9, b, record)
    assert row["status"] == "info" and "exactly 1 block" in row["detail"] and "stops with 1" in row["detail"]
    row1 = IA.blocks_left_row("The clock runs out with one block left.", b, record)
    assert row1["status"] == "pass"


def test_h13b_the_limit_follows_the_predicted_play_not_the_count(tmp_path, monkeypatch):
    r = _reading(columns=8, rows=8, blocks=9, pieces="big", occupancy=None, outline="ring", shape_read="ring")
    b = B.check(B.default_brief())
    b["pacing"]["length_s"], b["gameplay"]["ending"], b["pacing"]["tempo"] = 60.0, "near_fail", "fast"
    prompt = "Use this picture's colours on everything, on a ring board like it, the same number of blocks; a fast tempo. 60 seconds."
    prov = IP.apply(b, prompt, r, IP.decide(prompt, r))
    notes = IP.fill_play(b, prompt, prov)
    pf = prov["play_fill"]
    assert b["level"]["blocks"] == 9 and pf["beyond"] and pf["levers_left"] == []
    assert any(n.startswith("one level of 9 blocks fills about") and "30-45 s would be tighter" in n for n in notes)
    vdir, record = _made(tmp_path, monkeypatch)
    _parts(vdir, 29.2, 60.0)
    assert IA.play_fills_row(prov, record, vdir)["status"] == "info"


def test_h9b_hues_the_words_give_the_background_that_match_the_picture_take_it_measured():
    s8 = ("Match this picture's board: as crowded, the same number of blocks and all of its colours, with the arcade "
          "purple-to-pink glow for the background. 45 seconds.")
    r = _reading()
    r["margins"] = {"top": "#581E63", "bottom": "#240F3F"}
    assert IP.bg_hues_match(s8, r) == ["purple", "pink"]
    d = IP.reconcile(IP.decide(s8, r), {"source": "planner", "focus": ["board"], "level": "image"}, r)
    assert "style" in d["roles"] and d["style"]["parts"] == ["background"]
    b = B.check(B.default_brief())
    prov = IP.apply(b, s8, r, d)
    assert b["visuals"]["background"] == ["#581E63", "#240F3F"]
    r2 = dict(r, margins={"top": "#2A8C5A", "bottom": "#1E6A44"})  # a green picture: the words' purple is their own
    assert IP.bg_hues_match(s8, r2) == []
    assert IP.bg_hues_match("Keep the game's own look, a purple background glow.", r) == []


def test_h4b_two_agreeing_reads_stand_over_a_low_fill_on_a_themed_render():
    bd = {"blocks": 10, "occupancy": 0.24, "size_spread": 1, "size_reads": [[7, 10], [7, 9], [7, 9]]}
    assert IP.size_from_fill(bd, "narrow_center", (7, 9), "varied", (7, 9), themed=True) is None
    assert IP.size_from_fill(bd, "narrow_center", (7, 9), "varied", (7, 9), themed=False) is not None  # the game's look: as before
    assert IP.themed_look({"margins": {"top": "#7FA36B"}}) and not IP.themed_look({"margins": {"top": "#E4F0FE"}})


def test_h18_a_cliffhanger_holds_its_question_instead_of_a_long_card():
    b = B.check(B.default_brief())
    b["pacing"]["length_s"], b["gameplay"]["ending"] = 40.0, "cliffhanger"
    prov = {"play_fill": {"expected_s": 24.0}}
    notes = IP.question_hold(b, "Stop the ad before the last two blocks leave. 40 seconds.", prov)
    assert b["sequence"]["hold_s"] == 5.0 and "the question stays up 5 s longer" in notes[0]
    b2 = B.check(B.default_brief())
    b2["pacing"]["length_s"], b2["gameplay"]["ending"] = 40.0, "cliffhanger"
    assert IP.question_hold(b2, "x", {"play_fill": {"expected_s": 30.0}}) == [] and b2["sequence"]["hold_s"] is None
    b2["gameplay"]["ending"] = "win"
    assert IP.question_hold(b2, "x", prov) == []


def test_h3b_the_reader_accent_is_measured_and_used_for_the_captions(tmp_path):
    pic = tmp_path / "neon.png"
    im = Image.new("RGB", (400, 720), (12, 18, 48))
    ImageDraw.Draw(im).rectangle((0, 300, 400, 330), fill=(40, 220, 240))  # a cyan trim, outside the margins
    im.save(pic)
    acc = IR.accent_of(pic, {"look": {"accent": "#30D8F0", "accent_box": {"x": 0, "y": 0.35, "w": 1, "h": 0.15}}})
    assert acc["confirmed"] and acc["hex"] == "#28DCF0"
    assert IR.accent_of(pic, {"look": {"accent": None}}) is None
    r = _reading()
    r.update(caption_measured=None, captions=[], margins={"top": "#0C1230", "bottom": "#0C1230"},
             palette=[{"hex": "#0C1230", "share": 0.9}], accent_measured=acc)
    kit = IP.style_kit(r, ["background", "captions"])
    assert kit["caption_fill"] == "#28DCF0" and "the accent the reader names" in kit["caption_source"]
    r["accent_measured"] = {"hex_read": "#30D8F0", "hex": None, "confirmed": False}
    assert IP.style_kit(r, ["background", "captions"])["caption_fill"] == "#FFFFFF"  # unconfirmed: white stays


def test_h19_the_plate_says_night_only_for_navy_or_black():
    assert IP.plate_word(["#040926", "#02040F"]) == "night"
    assert IP.plate_word(["#000000", "#111111"]) == "night"
    assert IP.plate_word(["#AD8E71", "#866346"]) == "dark"
    assert IP.plate_word(["#581E63", "#240F3F"]) == "dark"


def test_one_more_colour_than_the_picture_adds_one_to_the_pictures_colours():
    """2026-10-19: "create a similar game concept, just use one more color" on a 3-colour screenshot gave 3 colours."""
    assert IP.relative_colours("create a similar game concept, just use one more color") == 1
    assert IP.relative_colours("Like this board with an extra colour.") == 1 and IP.relative_colours("two fewer colours") == -2
    assert IP.relative_colours("3 colours more than this") == 3 and IP.relative_colours("the same colours as this board") is None
    assert IP.relative_colours("A Color Block Jam level like this") is None
    prompt = "Create a similar game concept, just use one more colour."
    reading = _reading()  # red and blue
    d = IP.decide(prompt, reading)
    b = B.default_brief()
    b["level"]["colours"] = ["Red", "Blue", "Yellow"]  # the planner's own pick of the extra colour is kept
    spec = IP.board_spec(prompt, b, reading, d)
    assert spec["set"]["colours"] == ["Red", "Blue", "Yellow"] and "colours" in spec["took"] and "colours" not in spec["filled"]
    assert any("2 colours in the picture (Red, Blue) + 1 as asked: Yellow" in c for c in spec["clamps"])
    assert spec["built"]["colours_by"] == "request+picture"
    b["level"]["colours"] = []  # no pick: the game's own order fills the gap
    assert IP.board_spec(prompt, b, reading, d)["set"]["colours"] == ["Red", "Blue", "Green"]
    four = _reading(colours=[{"name": "red", "rgb": [223, 66, 49]}, {"name": "blue", "rgb": [47, 105, 235]},
                             {"name": "yellow", "rgb": [250, 210, 40]}, {"name": "green", "rgb": [60, 180, 75]}])
    fewer = "A board like this one with two fewer colours."
    spec = IP.board_spec(fewer, b, four, IP.decide(fewer, four))
    assert spec["set"]["colours"] == ["Red", "Blue"] and any("- 2 as asked" in c for c in spec["clamps"])
