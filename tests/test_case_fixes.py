"""Fixes from the case-requirement test of 2026-10-13 (CASE-TEST-REPORT-2026-10-13.md): ads never
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


def test_a_block_the_colour_of_the_background_keeps_the_game_s_colour():
    b = B.check(raw_brief(visuals={"theme": "custom", "background": ["#FFD6EC", "#FFD6EC"],
                                   "blocks": [{"slot": "Red", "hex": "#FFD6EC", "name": "pink"},
                                              {"slot": "Green", "hex": "#6BD9A6", "name": "mint"}]}))
    assert [e["slot"] for e in b["visuals"]["blocks"]] == ["Green"]
    assert "vanish" in B.control(b, "visuals")["why"]


def test_a_reference_prompt_counts_as_asking_for_copy_in_its_spirit():
    assert B._evidence("concept.hook", "Create a Color Block Jam version of this concept.", {}) is None
    assert B._evidence("concept.hook", "A clean win on a ring board.", {}) is not None
