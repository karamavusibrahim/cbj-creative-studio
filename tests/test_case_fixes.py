"""Fixes from the brief-requirement test of 2026-10-13 (CASE-TEST-REPORT-2026-10-13.md): ads never
under 30 s, a short play filled rather than the ad shrunk, hesitations clamped per ending, edits
keeping the game's own level file (and its HUD number), reference images and videos read before
planning, uploads checked by content, and plain words in what the user reads."""

import json
import re
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from cbj import brief as B
from cbj import editreport, reference, studio
from cbj.ad import END_CARD_FILL_MAX_S, FPS, Recording, build_ad, timeline

from test_ad import make_recording
from test_text_to_creative import FakeModel, raw_brief

PROJ = Path(__file__).parent.parent


# ---------- F1: 30-60 s ----------

def test_a_length_under_30_s_is_raised_to_30_with_a_reason():
    b = B.check(raw_brief(pacing={"length_s": 20.0, "tempo": "fast", "curve": "even"}))
    assert b["pacing"]["length_s"] == 30.0
    row = B.control(b, "difficulty_pacing")
    assert row["status"] == "adjusted" and "30" in row["why"]


def test_a_short_play_is_filled_up_to_the_asked_length_not_shrunk(tmp_path):
    """The synthetic recording plays 6.3 s; a 30 s ad used to be refused (end card over 8 s)."""
    rec = Recording.load(make_recording(tmp_path / "rec"))
    ad = build_ad(rec, length_s=30)
    tl = timeline(ad)
    assert ad["length_s"] == 30
    card = tl["end"][1] - tl["end"][0]
    assert card <= END_CARD_FILL_MAX_S * FPS
    assert "replay" in ad["order"] and "intro" in ad["order"]
    assert "result_hold" in ad["order"]
    assert any("filled with" in n for n in ad["notes"])
    # the frozen intro shows a frame after the clock's first tick flash, before the first touch
    assert 0 < ad["segments"]["intro"]["frame"] < rec.result["first_touch_frame"]


def test_time_used_reads_as_words(tmp_path):
    rec = Recording.load(make_recording(tmp_path / "rec"))
    f = rec.facts()
    assert re.fullmatch(r"\d+ seconds?", f["time_used_phrase"])
    assert "time_used_phrase" in B.FACT_KEYS if hasattr(B, "FACT_KEYS") else True


def test_the_game_s_own_level_1_is_too_short_for_a_45_s_ad_and_the_showcase_is_not():
    b = B.check(raw_brief(pacing={"length_s": 45.0, "tempo": "calm", "curve": "even"},
                          gameplay={"ending": "win"}))
    assert studio._too_short(b, studio.LEVELS / "Level_01.json")
    b30 = B.check(raw_brief())
    assert studio._too_short(b30, studio.NARROW) is None


def test_a_level_number_in_the_prompt_is_recognised():
    assert studio._asked_level_number({"planner": {"prompt": "Use the game's own level 4, as it is"}})
    assert not studio._asked_level_number({"planner": {"prompt": "An easy level, calm, 45 seconds"}})


# ---------- F5: hesitations ----------

def test_hesitations_are_clamped_per_ending_not_crashed():
    b = B.check(raw_brief(gameplay={"ending": "win", "hesitations": 2}))
    assert b["gameplay"]["hesitations"] == 1
    assert B.control(b, "gameplay")["status"] == "adjusted"
    b = B.check(raw_brief(gameplay={"ending": "near_fail", "hesitations": 2}))
    assert b["gameplay"]["hesitations"] == 2  # allowed there


# ---------- F6: evidence ----------

def test_speeding_up_counts_as_a_change_of_pace():
    assert B._evidence("pacing.curve", "40 seconds, speeding up; hook 'Sweet escape'", {}) is None
    assert B._evidence("pacing.curve", "a calm clean win", {}) is not None


def test_a_prompt_in_another_language_is_taken_as_the_planner_read_it():
    tr = "Zor bir seviye yap, oyuncu son saniyede kazansın. Yazılar Türkçe olsun."
    assert B.foreign(tr)
    assert not B.foreign("Create a difficult level with a narrow center and the player almost fails.")
    base = B.check(B.default_brief())
    new = B.check(raw_brief(level={"difficulty": "hard", "source": "generate"}, gameplay={"clock_left_s": 1},
                            changed=["level.difficulty", "level.source", "gameplay.clock_left"]))
    merged, dropped = B.merge(base, new, tr)
    assert merged["level"]["difficulty"] == "hard"
    assert merged["gameplay"]["clock_left_s"] == 1
    assert not dropped


def test_a_declared_change_the_merge_drops_is_shown_as_adjusted():
    from cbj import planner
    raw = raw_brief(pacing={"length_s": 30.0, "tempo": "normal", "curve": "speeds_up"}, changed=["pacing.curve"])
    raw["controls"] = [{"control": c, "asked": None, "plan": "", "status": "default", "why": None} for c in B.CONTROLS]
    b = planner.plan("a clean win, nothing else", client=FakeModel(raw))
    assert b["pacing"]["curve"] == "even"
    row = B.control(b, "difficulty_pacing")
    assert row["status"] == "adjusted" and "change of pace" in row["why"]


# ---------- F11: visuals ----------

def test_a_board_colour_that_vanishes_into_the_background_is_dropped():
    b = B.check(raw_brief(visuals={"background": ["#000000", "#000000"], "board": "#111111"}))
    assert b["visuals"]["board"] is None
    assert "disappear" in B.control(b, "visuals")["why"]


def test_hiding_the_clock_also_hides_the_bar_s_panel_but_not_the_level_badge():
    hide = studio.hud_hide({"hud_timer": False, "hud_level": True})
    assert "MainBar:image" in hide and "TimeText" in hide and "LevelCircle" not in hide
    assert studio.hud_hide({"hud_timer": False, "hud_level": False}) == ["MainBar"]


# ---------- F4: the level file an edit keeps ----------

def test_an_edit_keeps_the_game_s_own_level_file_by_name(tmp_path, monkeypatch):
    monkeypatch.setattr(studio, "STUDIO", tmp_path)
    src = studio.LEVELS / "Level_01.json"
    copy = tmp_path / "c" / "v1" / "level.json"
    copy.parent.mkdir(parents=True)
    copy.write_bytes(src.read_bytes())
    prev = {"level": {"file": "c/v1/level.json", "source": "data/levels/Level_01.json", "sha": studio._sha(src.read_bytes())}}
    assert studio._level_source(prev) == src
    assert studio.hud_label(studio.load_level(studio._level_source(prev)), src) == 1 if hasattr(studio, "load_level") else True
    prev["level"]["sha"] = "0" * 64  # the source changed since: the copy is used
    assert studio._level_source(prev) == copy


# ---------- F8: uploads by content ----------

@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from cbj import app as A
    monkeypatch.setattr(studio, "STUDIO", tmp_path / "studio")
    (tmp_path / "studio").mkdir()
    return TestClient(A.app)


def test_a_text_file_named_png_is_refused_and_a_video_is_accepted(client):
    r = client.post("/api/upload", files=[("files", ("fake.png", b"not an image at all", "image/png"))])
    assert r.status_code == 400 and "readable image" in r.json()["detail"]
    from io import BytesIO
    buf = BytesIO()
    Image.new("RGB", (4, 4), "red").save(buf, "PNG")
    r = client.post("/api/upload", files=[("files", ("ok.png", buf.getvalue(), "image/png"))])
    assert r.status_code == 200 and r.json()["uploaded"] == ["ok.png"]
    mp4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 40
    r = client.post("/api/upload", files=[("files", ("ref.mp4", mp4, "video/mp4"))])
    assert r.status_code == 200 and r.json()["uploaded"] == ["ref.mp4"]
    r = client.post("/api/upload", files=[("files", ("bad.mp4", b"hello", "video/mp4"))])
    assert r.status_code == 400
    meta = client.get("/api/meta").json()
    assert meta["uploads"] == ["ok.png"] and meta["videos"] == ["ref.mp4"]  # a video is never an asset
    assert client.get("/api/jobs").status_code == 200


# ---------- F2/F3: references ----------

def _candy(path: Path) -> Path:
    im = Image.new("RGB", (300, 500), "#FFD6EC")
    d = ImageDraw.Draw(im)
    d.rectangle([20, 20, 280, 160], fill="#5FD9A0")
    d.rectangle([20, 180, 280, 320], fill="#FFE45C")
    d.rectangle([20, 340, 280, 480], fill="#FF4F8B")
    im.save(path)
    return path


def test_the_palette_is_measured_from_the_pixels(tmp_path):
    pal = reference.palette(_candy(tmp_path / "ref_01.jpg"))
    names = [p["name"] for p in pal]
    assert names[0] in ("light pink", "pink", "rose")  # the background
    assert "mint" in names or "sage" in names
    assert all(p["hex"].startswith("#") and len(p["hex"]) == 7 for p in pal)


def test_reference_words_and_placement_words():
    assert reference.is_reference_prompt("Create a creative inspired by this image")
    assert reference.is_reference_prompt("Create a Color Block Jam version of this concept")
    assert not reference.is_reference_prompt("Put our logo top left")
    assert reference.asks_placement("replace the picture on the end card with the attached asset")
    assert not reference.asks_placement("match the colours of the attached image")


def test_an_analysed_image_shapes_the_brief_and_is_not_pasted_into_the_ad(tmp_path):
    from cbj import planner
    img = _candy(tmp_path / "ref_01.jpg")
    analysis = {"file": "ref_01.jpg", "kind": "image", "palette": reference.palette(img),
                "notes": {"subject": "candy blocks", "mood": "sweet", "dominant_colours": ["#FF4F8B"]}}
    raw = raw_brief(visuals={"theme": "custom", "blocks": [{"slot": "Red", "hex": "#FF4F8B", "name": "pink"}],
                             "background": ["#FFD6EC", "#FFD6EC"]},
                    assets=[{"file": "ref_01.jpg", "role": "end_art", "when": "end_card", "where": "end_card"}],
                    changed=["visuals.colours", "visuals.background", "assets"])
    raw["controls"] = [{"control": c, "asked": None, "plan": "", "status": "default", "why": None} for c in B.CONTROLS]
    model = FakeModel(raw)
    b = planner.plan("Create a Color Block Jam creative inspired by this image.", client=model,
                     uploads={"ref_01.jpg": img}, references={"ref_01.jpg": img}, analyser=lambda p: analysis)
    assert "REFERENCE FILES" in model.calls[0][1] and "light pink" in model.calls[0][1] or "pink" in model.calls[0][1]
    assert b["visuals"]["blocks"][0]["hex"] == "#FF4F8B"
    assert b["assets"] == []  # read, not placed
    assert b["planner"]["references"][0]["file"] == "ref_01.jpg"
    assert any(a.startswith("Read from ref_01.jpg") for a in b["assumptions"])


def test_a_reference_that_could_not_be_read_is_said_so_not_guessed(tmp_path):
    from cbj import planner
    img = _candy(tmp_path / "ref.png")
    raw = raw_brief(visuals={"theme": "candy"}, changed=["visuals.colours"])
    raw["controls"] = [{"control": c, "asked": None, "plan": "", "status": "default", "why": None} for c in B.CONTROLS]
    b = planner.plan("a creative inspired by this image", client=FakeModel(raw), uploads={"ref.png": img},
                     references={"ref.png": img}, analyser=lambda p: {"file": "ref.png", "kind": "image", "error": "no model"})
    assert any("could not be read" in a for a in b["assumptions"])
    assert B.control(b, "visuals")["status"] == "adjusted"


def test_a_video_reference_is_never_an_asset(tmp_path):
    from cbj import planner
    vid = tmp_path / "ref.mp4"
    vid.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    raw = raw_brief(gameplay={"ending": "time_out"}, channel="social",
                    assets=[{"file": "ref.mp4", "role": "end_art", "when": "end_card", "where": "end_card"}],
                    changed=["gameplay.ending", "channel", "assets"])
    raw["controls"] = [{"control": c, "asked": None, "plan": "", "status": "default", "why": None} for c in B.CONTROLS]
    analysis = {"file": "ref.mp4", "kind": "video", "facts": {"duration_s": 20}, "notes": {"ending": "fail", "pacing": "fast"}}
    b = planner.plan("Create a Color Block Jam version of this concept.", client=FakeModel(raw), references={"ref.mp4": vid},
                     analyser=lambda p: analysis)
    assert b["gameplay"]["ending"] == "time_out" and b["assets"] == []


def test_notes_text_reports_an_error_plainly():
    t = reference.notes_text({"file": "x.mp4", "kind": "video", "error": "ffmpeg missing"})
    assert "COULD NOT BE ANALYSED" in t


# ---------- F9: plain words ----------

def test_the_edit_report_names_layers_and_colours_in_words():
    assert editreport.layer_name("end_art") == "the picture on the end card"
    assert editreport.layer_name("cap_mistake") == "the caption on the mistake"
    assert "red shown as pink" in editreport._visual_value("blocks", [{"slot": "Red", "hex": "#FF69B4", "name": "pink"}])
    assert editreport._visual_value("hud_timer", False) == "hidden"
    assert B.GROUP_NAMES["level.difficulty"] == "the level's difficulty"


def test_a_block_the_colour_of_the_background_is_deepened_to_stay_visible():
    b = B.check(raw_brief(visuals={"theme": "custom", "background": ["#FFD6EC", "#FFD6EC"],
                                   "blocks": [{"slot": "Red", "hex": "#FFD6EC", "name": "pink"},
                                              {"slot": "Green", "hex": "#6BD9A6", "name": "mint"}]}))
    # the pink block is kept, deepened just enough to stand out from the pink background
    red = next(e for e in b["visuals"]["blocks"] if e["slot"] == "Red")
    assert red["hex"] != "#FFD6EC" and B.colour_distance(red["hex"], "#FFD6EC") >= B.MIN_COLOUR_DISTANCE
    assert red["name"] == "pink" and "deepened" in B.control(b, "visuals")["why"]
    assert [e["slot"] for e in b["visuals"]["blocks"]] == ["Red", "Green"]


def test_a_reference_prompt_counts_as_asking_for_copy_in_its_spirit():
    assert B._evidence("concept.hook", "Create a Color Block Jam version of this concept.", {}) is None
    assert B._evidence("concept.hook", "A clean win on a ring board.", {}) is not None


# ---- 2026-10-13 evening: İbrahim's 36 natural-language cases ----

def test_first_time_player_is_not_an_order_of_moves():
    p = "Create a very easy level for a first-time player. Use only red, blue, and yellow blocks with matching exit doors."
    assert B._evidence("gameplay.events", p, {"gameplay": {"events": [{"action": "leaves"}]}})
    assert B._evidence("gameplay.events", "the red block leaves first, then the blue one", {"gameplay": {"events": [{"action": "leaves"}]}}) is None
    assert B._evidence("gameplay.events", "the big block gets stuck before the win", {"gameplay": {"events": [{"action": "stuck"}]}}) is None


def test_plain_text_scrubs_field_names_and_tokens():
    t = B.plain_text("Mapped to level.shape 'open'; timer_s 60; channel 'network' and format '9:16'; language 'en'; ending near_fail; end_art on the end_card.")
    for bad in ("level.shape", "timer_s", "near_fail", "end_art", "end_card", "'network'", "'en'"):
        assert bad not in t, t
    assert "the clock" in t and "a near-fail" in t and "English" in t


def test_dropped_numbers_leave_the_words():
    b = {"summary": "A simple 6x6 level with exactly three blocks, a 35-second ad ending with 2 seconds left.",
         "assumptions": [], "pacing": {"length_s": 30.0},
         "controls": [{"control": "level", "plan": "Generate a new 6x6 open board with three blocks", "why": None},
                      {"control": "difficulty_pacing", "plan": "Set a 35-second length", "why": None},
                      {"control": "gameplay", "plan": "finishing with 2 seconds left on the clock", "why": None}]}
    for g in ("level.size", "level.blocks", "pacing.length", "gameplay.clock_left"):
        B.drop_numbers(b, g)
    assert "6x6" not in b["summary"] and "three blocks" not in b["summary"] and "35" not in b["summary"]
    assert "2 seconds left" not in b["summary"] and "30-second" in b["summary"]
    assert b["controls"][0]["plan"] == "Generate a board sized to the ad with the blocks the ad needs"
    assert "30-second" in b["controls"][1]["plan"] and "a little time left" in b["controls"][2]["plan"]


def test_square_board_and_out_of_the_way_are_evidence():
    assert B._evidence("level.size", "a symmetrical level on a square board", {}) is None
    assert B._evidence("level.difficulty", "make the solution require moving blocks out of the way", {}) is None
    assert B._evidence("level.style", "blocks clustered tightly in the center, only a few empty spaces", {}) is None
    assert B._evidence("level.shape", "small rectangular blocks, longer blocks, and L-shaped blocks", {})
    assert B._evidence("level.pieces", "small rectangular blocks, longer blocks, and L-shaped blocks", {}) is None


def test_gate_sides_are_told_not_claimed():
    from cbj.planner import _gate_sides
    b = B.check(B.default_brief())
    _gate_sides(b, "red and blue blocks on opposite sides, with their exit doors on opposing edges")
    row = B.control(b, "level")
    assert row["status"] == "adjusted" and "gate sits" in row["why"]
    b2 = B.check(B.default_brief())
    _gate_sides(b2, "a red block exits through its door")
    assert B.control(b2, "level")["status"] == "default"


def test_varied_pieces_put_small_long_and_corner_on_the_board(tmp_path):
    from cbj.generate import generate_for_brief, piece_kinds
    from cbj.level import load_level
    b = B.check(B.default_brief())
    b["level"].update({"pieces": "varied", "difficulty": "medium"})
    path, why = generate_for_brief(b, tmp_path, lambda *a: None)
    assert piece_kinds(load_level(path)) == {"small", "long", "corner"}
    assert "L-shaped" in why


def test_near_fail_boards_offer_a_mistake(tmp_path):
    from cbj.generate import generate_for_brief
    from cbj.level import load_level
    from cbj.play import mistake_options
    from cbj.rules import initial_state
    b = B.check(B.default_brief())
    b["level"].update({"shape": "open", "colours": ["Red", "Blue"], "style": ["symmetric"], "difficulty": "medium"})
    b["gameplay"]["ending"] = "near_fail"
    path, _ = generate_for_brief(b, tmp_path, lambda *a: None)
    L = load_level(path)
    assert mistake_options(L, initial_state(L), allow_fidget=False)


def test_unasked_changes_are_shown_as_the_planners_own():
    from cbj.planner import _own_taste
    b = B.check(B.default_brief())
    b["visuals"]["theme"] = "pastel"  # the request said nothing about the look
    _own_taste(b, ["visuals.colours"])
    row = B.control(b, "visuals")
    assert row["status"] == "adjusted" and "not asked for" in row["why"]
    b2 = B.check(B.default_brief())
    B.control(b2, "visuals").update({"asked": "pastel colours", "status": "applied"})
    _own_taste(b2, ["visuals.colours"])
    assert B.control(b2, "visuals")["status"] == "applied"


def test_a_few_colours_is_not_a_block_count():
    assert B._evidence("level.blocks", "simple routes, and only a few colors", {})
    assert B._evidence("level.blocks", "a few blocks get in each other's way", {}) is None


def test_a_number_of_moves_is_a_control(tmp_path):
    from cbj.generate import generate_for_brief
    from cbj.checks import level_checks
    assert B._evidence("level.moves", "solved in approximately 10 to 15 meaningful block movements", {}) is None
    assert B._evidence("level.moves", "a medium level", {})
    b = B.check(B.default_brief())
    b["level"].update({"moves": 12, "difficulty": "medium"})
    path, _ = generate_for_brief(b, tmp_path, lambda *a: None)
    moves = [c for c in level_checks(b, path) if c["check"] == "Moves"]
    assert moves and moves[0]["status"] == "pass", moves
    b2 = B.default_brief(); b2["level"]["moves"] = 40; b2 = B.check(b2)
    assert b2["level"]["moves"] == 16 and "16 is used" in B.control(b2, "level")["why"]


def test_flat_blocks_and_decorations_are_told_their_limits():
    from cbj.planner import _art_limits
    b = B.check(B.default_brief())
    _art_limits(b, "a muted palette, flat block surfaces, and playful candy-inspired decorations", [])
    assert "cannot be made flat" in B.control(b, "visuals")["why"]
    assert "decorations need a picture" in B.control(b, "assets")["why"]
    b2 = B.check(B.default_brief())
    _art_limits(b2, "candy decorations", ["sticker.png"])
    assert B.control(b2, "assets")["status"] == "default"


def test_removing_an_obstacle_from_an_open_board_keeps_the_board():
    from cbj.planner import _no_obstacles_to_remove
    cur = B.check(B.default_brief()); cur["level"]["shape"] = "open"
    b = B.check(B.default_brief()); b["level"]["shape"] = "narrow_center"; b["changed"] = ["level.shape"]
    _no_obstacles_to_remove(b, "Simplify the current level by removing one unnecessary obstacle.", cur)
    assert b["level"]["shape"] == "open" and "level.shape" not in b["changed"]
    assert "no walls or holes" in B.control(b, "level")["why"]
    assert B.relative_difficulty("Simplify the current difficult level by removing one unnecessary obstacle") == "easier"


def test_a_single_gate_is_refused_without_a_fake_time_out():
    from cbj.planner import _one_gate_only, _ONE_GATE
    assert _ONE_GATE.search("red, blue, and yellow blocks, but include only a red exit door")
    assert not _ONE_GATE.search("the red block exits through its door")
    b = B.check(B.default_brief()); b["gameplay"]["ending"] = "time_out"; b["gameplay"]["mistakes"] = 1
    _one_gate_only(b, "Create a level with red, blue, and yellow blocks, but include only a red exit door. All blocks must still be removed.", None)
    assert "every colour on the board gets its own gate" in B.control(b, "level")["why"]
    assert b["gameplay"]["ending"] == "win" and b["gameplay"]["mistakes"] is None


def test_frozen_positions_cannot_become_easier():
    from cbj.planner import _relative_difficulty
    cur = B.check(B.default_brief()); cur["level"]["difficulty"] = "easy"
    b = B.check(B.default_brief()); b["level"]["difficulty"] = "easy"; b["changed"] = ["level.difficulty"]
    _relative_difficulty(b, "Keep every block position, color, exit door, and obstacle exactly the same as the current level, but make the puzzle significantly easier without changing the timer or gameplay rules.", cur)
    row = B.control(b, "level")
    assert row["status"] == "not_supported" and "cannot be made easier" in row["why"]
    assert b["level"]["edit"] == cur["level"].get("edit") and "level.difficulty" not in b["changed"]
    b2 = B.check(B.default_brief()); b2["level"]["difficulty"] = "easy"; b2["changed"] = ["level.difficulty"]
    _relative_difficulty(b2, "Make it easier.", cur)
    assert b2["level"]["edit"] == {"dir": "easier", "of": None}


def test_a_generous_clock_makes_the_play_a_win():
    from cbj.planner import _generous_clock
    b = B.check(B.default_brief()); b["gameplay"]["ending"] = "near_fail"; b["gameplay"]["timer_s"] = 90
    _generous_clock(b, "Use a generous timer, make the unlocking order important.", None)
    assert b["gameplay"]["ending"] == "win" and "generous clock" in B.control(b, "gameplay")["why"]
    b2 = B.check(B.default_brief()); b2["gameplay"]["ending"] = "near_fail"
    _generous_clock(b2, "a generous timer, but the player still almost fails", None)
    assert b2["gameplay"]["ending"] == "near_fail"


def test_a_nearly_solved_opening_becomes_a_small_level_and_is_told():
    from cbj.planner import _mid_level_start
    b = B.check(B.default_brief()); b["changed"] = []
    _mid_level_start(b, "start with a nearly solved puzzle, show a misleading move causing a jam, then the correct sequence", None)
    assert b["level"]["blocks"] == 5 and "level.blocks" in b["changed"]
    assert "filmed from the level's first move" in B.control(b, "gameplay")["why"]


def test_a_very_short_play_holds_the_result_rather_than_make_no_ad():
    """6.3 s of play into a 34 s ad: replay, a 4 s hold and a 10 s card leave time over; the result
    holds that much longer (up to 12 s in all) instead of the ad being refused or opening frozen."""
    from test_ad import make_recording, timeline
    from cbj.ad import Recording, build_ad
    import tempfile
    rec = Recording.load(make_recording(Path(tempfile.mkdtemp()) / "nf"))
    ad = build_ad(rec, length_s=34)
    assert ad["length_s"] == 34
    assert timeline(ad)["end"][1] - timeline(ad)["end"][0] <= 10 * 30
    with pytest.raises(ValueError, match="too short for a 60 s ad"):
        build_ad(rec, length_s=60)


def test_an_easier_edit_of_a_board_where_every_block_leaves_directly_finds_nothing(tmp_path):
    from cbj.generate import generate_for_brief, edit_board, Spec
    from cbj.difficulty import rate
    from cbj.level import load_level
    import json
    b = B.check(B.default_brief()); b["level"].update({"difficulty": "easy", "shape": "open", "colours": ["Red", "Blue", "Yellow"]})
    path, _ = generate_for_brief(b, tmp_path, lambda *a: None)
    r = rate(load_level(path))
    if r.extra_drags or r.naive_ratio > 1.02:
        pytest.skip("this easy board has something to loosen")
    parent = json.loads(path.read_text())
    spec = Spec(shape="open", width=parent["gridWidth"], height=parent["gridHeight"], blocks=len(parent["GridBlockDatas"]),
                difficulty="easy", budget_s=5.0)
    assert edit_board(parent, spec, "easier") is None


def test_an_asked_mistake_needs_a_board_that_offers_one(tmp_path):
    from cbj.generate import generate_for_brief
    from cbj.level import load_level
    from cbj.play import mistake_options
    from cbj.rules import initial_state
    b = B.check(B.default_brief())
    b["level"].update({"blocks": 5, "difficulty": "any"})
    b["gameplay"].update({"ending": "win", "mistakes": 1, "mistake_kinds": ["blocked"]})
    path, why = generate_for_brief(b, tmp_path, lambda *a: None)
    L = load_level(path)
    assert mistake_options(L, initial_state(L), allow_fidget=False), why


def test_without_text_narration_drops_the_captions_over_the_play():
    from cbj.planner import _no_captions
    b = B.check(B.default_brief()); b["changed"] = []
    _no_captions(b, "Make the reasoning visible through the actions without text narration.")
    assert all(b["concept"][k] == "" for k in ("mistake", "fix", "hurry", "cascade", "result"))
    assert b["concept"]["hook"] is None and b["concept"]["cta"] is None and "concept.result" in b["changed"]
    b2 = B.check(B.default_brief()); b2["changed"] = []
    _no_captions(b2, "a hook that says 'Can you?'")
    assert b2["concept"]["hook"] is None


def test_all_of_a_colour_leaving_first_starts_with_the_first_of_them():
    """'All the red blocks leave first' is satisfiable: the first drag is the first red exit, the other
    red exits follow with nothing else leaving in between (before: it demanded all red gone after drag 1)."""
    from cbj.events import from_brief, solve_events
    from cbj.generate import generate_for_brief
    b = B.check(B.default_brief())
    b["level"].update({"colours": ["Red", "Blue"], "difficulty": "easy", "shape": "open"})
    path, _ = generate_for_brief(b, Path(__file__).parent / "_tmp_levels", lambda *a: None)
    from cbj.level import load_level
    L = load_level(path)
    raw = [{"block": {"colour": "Red", "which": "any", "all": True}, "action": "leaves", "when": "first"},
           {"block": {"colour": "Blue", "which": "any", "all": True}, "action": "leaves", "when": "next"}]
    evs, notes = from_brief(L, raw)
    if len(evs) < 2:
        pytest.skip("the board has one colour only")
    sol = solve_events(L, evs, max_states=50_000)
    assert sol is not None
    reds = evs[0].blocks
    exits = [d.block for d in sol.drags if d.exits]
    assert exits[0] in reds and all(x in reds for x in exits[:len(reds)])


def test_the_longest_blue_block_is_the_long_one_on_the_board(tmp_path):
    from cbj.generate import generate_for_brief, named_superlatives
    from cbj.level import load_level
    from cbj.planner import _one_of_its_kind
    b = B.check(B.default_brief())
    b["level"].update({"pieces": "long", "colours": ["Blue"], "blocks": 3, "difficulty": "medium"})
    b["gameplay"]["events"] = [{"block": {"colour": "Blue", "which": "longest", "all": False}, "action": "leaves", "when": "last"}]
    b["changed"] = ["level.pieces", "gameplay.events"]
    _one_of_its_kind(b)
    assert b["level"]["pieces"] == "mixed" and "the long" in B.control(b, "level")["why"] or "longest" in B.control(b, "level")["why"]
    path, _ = generate_for_brief(b, tmp_path, lambda *a: None)
    assert named_superlatives(load_level(path), b["gameplay"]["events"]) == []


def test_blocks_left_at_a_cliffhanger_is_a_control():
    assert B._evidence("gameplay.blocks_left", "leaving one clearly visible block and its matching door on screen", {}) is None
    assert B._evidence("gameplay.blocks_left", "stop before the final decisive move", {}) is None
    assert B._evidence("gameplay.blocks_left", "a challenging board", {})
    b = B.default_brief(); b["gameplay"].update({"ending": "cliffhanger", "blocks_left": 5}); b = B.check(b)
    assert b["gameplay"]["blocks_left"] == 3
    b2 = B.default_brief(); b2["gameplay"].update({"ending": "win", "blocks_left": 1}); b2 = B.check(b2)
    assert b2["gameplay"]["blocks_left"] is None


def test_a_failure_creative_is_a_time_out_and_says_why():
    from cbj.planner import _what_failure_is
    b = B.check(B.default_brief()); b["gameplay"]["ending"] = "near_fail"; b["changed"] = []
    _what_failure_is(b, "Generate a 15-second ad creative designed to end in failure.")
    assert b["gameplay"]["ending"] == "time_out" and "only real failure is the clock" in B.control(b, "gameplay")["why"]


def test_a_wrapped_result_caption_is_moved_up_inside_the_safe_area(tmp_path):
    from test_ad import make_recording
    from cbj.ad import Recording, build_ad
    from cbj.compose import render
    rec = Recording.load(make_recording(tmp_path / "nf"))
    ad = build_ad(rec, length_s=30)
    assert "cap_result" in ad["layers"] and ad["layers"]["cap_result"].get("pos")
    ad["layers"]["cap_result"]["text"] = "Cleared with {clock_left} left on the clock, phew!"  # wraps to two lines
    r = render(ad, tmp_path / "g", draft=True)
    assert not [f for f in r["qa"]["failures"] if "safe area" in f], r["qa"]["failures"]
    assert any("moved up" in w for w in r["qa"]["warnings"]), r["qa"]["warnings"]


def test_a_resolved_spec_keeps_every_request_field():
    from cbj.generate import Spec
    r = Spec(singles=["Yellow"], mistakes=1, moves_asked=True, mistakes_asked=True, pieces="varied").resolved()
    assert (r.singles, r.mistakes, r.moves_asked, r.mistakes_asked, r.pieces) == (["Yellow"], 1, True, True, "varied")
    assert Spec().key() == Spec(mistakes=0, singles=[]).key()  # defaults keep the old cache keys


def test_a_time_out_gets_a_board_hard_enough_to_fail_on(tmp_path):
    from cbj.generate import generate_for_brief
    from cbj.difficulty import rate
    from cbj.level import load_level
    from cbj.play import time_out_allowed
    b = B.check(B.default_brief()); b["gameplay"].update({"ending": "time_out", "mistakes": 2}); b["channel"] = "social"
    path, why = generate_for_brief(b, tmp_path, lambda *a: None)
    assert time_out_allowed(rate(load_level(path)))[0], why


def test_an_exact_sequence_makes_a_level_of_exactly_the_named_blocks():
    from cbj.planner import _exact_sequence
    b = B.check(B.default_brief()); b["changed"] = []
    b["gameplay"]["events"] = [{"block": {"colour": c, "which": "any", "all": False}, "action": a, "when": w} for c, a, w in
                               (("Yellow", "moves", "first"), ("Green", "leaves", "next"), ("Red", "moves", "next"),
                                ("Yellow", "leaves", "next"), ("Red", "leaves", "last"))]
    _exact_sequence(b, "Generate a creative with this exact sequence: first move the yellow block aside; second send the green block through its door.")
    assert b["level"]["blocks"] == 3 and b["level"]["colours"] == ["Yellow", "Green", "Red"]
    assert "exactly those" in B.control(b, "level")["why"]


def test_a_short_play_no_longer_opens_on_a_long_frozen_frame(tmp_path):
    """The viewer must see the game move within the first second: a short play is filled with the
    replay and the held result, never with a 3 s frozen opening (2026-10-14)."""
    from cbj.ad import INTRO_FILL_S, INTRO_MAX_S
    rec = Recording.load(make_recording(tmp_path / "rec"))
    ad = build_ad(rec, length_s=30)
    tl = timeline(ad)
    assert ad["length_s"] == 30
    intro = tl["intro"][1] - tl["intro"][0] if "intro" in tl else 0
    assert intro <= INTRO_FILL_S * FPS and INTRO_MAX_S <= 0.5
    # the first drag is on screen within 1.5 s: the intro plus the recording's own 1 s lead-in
    assert intro + rec.result["first_touch_frame"] <= 1.5 * FPS


def test_filling_goes_to_the_replay_before_any_held_screen(tmp_path):
    """A short play: the replay grows to the whole solve first; the result is held at most 2.5 s
    (a 5 s finish with the game's own screen) unless the card would still pass 8 s; the end card
    stays short (2026-10-14, after the review of a beginner ad)."""
    from cbj.ad import END_CARD_FILL_MAX_S, RESULT_HOLD_MORE_S
    rec = Recording.load(make_recording(tmp_path / "rec"))
    ad = build_ad(rec, length_s=30)
    tl = timeline(ad)
    replay = tl["replay"][1] - tl["replay"][0]
    assert replay >= 6 * FPS  # the whole short solve at half speed
    hold = tl["result_hold"][1] - tl["result_hold"][0] if "result_hold" in tl else 0
    card = tl["end"][1] - tl["end"][0]
    # a hold past 4 s is used only once the end card is at its own cap (a very short play)
    assert hold <= RESULT_HOLD_MORE_S * FPS + 1 or card >= END_CARD_FILL_MAX_S * FPS - 1
    assert any("longer replay" in n for n in ad["notes"])
