"""Controlled editing (case p.7): an edit changes only what it asks for, keeps the original's
gameplay, timing, camera, composition, sequence, look and other assets, and proves it item by
item. Runs on a small synthetic recording (no Unity, no network)."""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from cbj import brief as B
from cbj import editreport as E
from cbj import edits, planner, studio
from cbj.ad import SPRITE_SIZES, Recording, build_ad, drawn_box, timeline
from cbj.compose import render
from cbj.level import load_level

from test_ad import LENGTH, make_recording
from test_text_to_creative import FakeModel, asked, declare, raw_brief

LEVEL = Path(__file__).parent.parent / "data/levels/gen/narrow_center_01.json"


def pin_of(ad: dict) -> dict:
    seg = ad["segments"]
    return {"n": 1, "length_s": ad["length_s"], "intro": seg["intro"]["frames"] if "intro" in ad["order"] else 0,
            "replay_from": seg["replay"]["from"] if "replay" in ad["order"] else None}


@pytest.fixture(scope="module")
def rec(tmp_path_factory):
    return Recording.load(make_recording(tmp_path_factory.mktemp("rec") / "nf"))


# ---------- the pin: an edit keeps the parent's timing ----------

def test_removing_the_replay_keeps_the_gameplay_on_its_frames(rec):
    """Without the pin, the freed time became a frozen intro that moved every gameplay frame."""
    base = build_ad(rec, LENGTH)
    assert "replay" in base["order"]
    ad = build_ad(rec, LENGTH, options={"replay": False}, pin=pin_of(base))
    assert "replay" not in ad["order"]
    assert timeline(ad)["play"] == timeline(base)["play"]  # the gameplay is where it was
    assert ad["length_s"] == base["length_s"]  # and the ad keeps its length: the end card takes the time
    assert ad["layers"]["hook"] == base["layers"]["hook"] and ad["layers"]["cap_mistake"] == base["layers"]["cap_mistake"]


def test_a_pinned_end_card_never_runs_past_ten_seconds(rec):
    base = build_ad(rec, 20, allow_long_card=True)
    ad = build_ad(rec, 20, options={"replay": False, "result_screen": False}, pin=pin_of(base))
    tl = timeline(ad)
    assert tl["play"] == timeline(base)["play"]
    card = (tl["end"][1] - tl["end"][0]) / 30
    assert card <= 10 and ad["length_s"] < 20
    assert any("shorter" in n["text"] for n in ad["brief_notes"])


def test_a_pinned_edit_that_needs_room_makes_the_ad_longer_and_says_so(rec):
    base = build_ad(rec, LENGTH)
    pin = pin_of(base)
    ad = build_ad(rec, LENGTH, options={"teaser": True}, pin=pin)
    tl = timeline(ad)
    assert (tl["end"][1] - tl["end"][0]) >= 90
    if ad["length_s"] > LENGTH:
        assert any("longer" in n["text"] for n in ad["brief_notes"])


def test_the_pinned_replay_is_the_one_the_user_saw(rec):
    base = build_ad(rec, LENGTH)
    pin = pin_of(base)
    ad = build_ad(rec, LENGTH, options={"result_screen": False}, pin=pin)
    assert ad["segments"]["replay"] == base["segments"]["replay"]


# ---------- asset slots ----------

def test_a_replacement_picture_is_drawn_in_the_original_box(rec):
    base = build_ad(rec, LENGTH)
    art = base["layers"]["end_art"]
    ad = build_ad(rec, LENGTH, options={"end_art": "new_art.png"})
    assert ad["layers"]["end_art"]["box"] == drawn_box(art["image"], art["scale"])
    assert ad["layers"]["end_art"]["pos"] == art["pos"]
    assert drawn_box("CoinPile.png", 420 / 669) == [420, 352]
    assert set(SPRITE_SIZES) >= {"CoinPile.png", "stopwatch.png", "ContinueButtonEmpty.png"}


def test_icon_and_end_art_can_be_removed_and_the_button_replaced(rec):
    ad = build_ad(rec, LENGTH, options={"hook_icon": "", "end_art": "", "button_image": "btn.png"})
    assert ad["layers"]["hook"].get("icon") is None
    assert "end_art" not in ad["layers"]
    cta = ad["layers"]["end_cta"]
    assert cta["image"] == "btn.png" and cta["box"] == drawn_box("ContinueButtonEmpty.png", cta["scale"])
    assert cta["text"] == "PLAY NOW"
    texts = [n["text"] for n in ad["brief_notes"]]
    assert any("icon beside the hook is removed" in t for t in texts) and any("end-card picture is removed" in t for t in texts)


def test_assets_merge_slot_by_slot():
    logo = {"file": "logo.png", "role": "logo", "when": "whole", "where": "top_left"}
    art = {"file": "art.png", "role": "end_art", "when": "end_card", "where": "auto"}
    base = B.check(B.default_brief())
    base["assets"] = [logo]
    new = copy.deepcopy(base)
    new["assets"] = [art]  # the model left the logo out while adding the end art
    declare(new, "assets")
    merged, dropped = B.merge(base, new, "replace the end card picture with art.png")
    assert {a["file"] for a in merged["assets"]} == {"logo.png", "art.png"}  # the logo stays
    assert any("assets.logo" in d for d in dropped)
    merged, _ = B.merge(base, new, "remove the logo and use art.png on the end card")
    assert {a["file"] for a in merged["assets"]} == {"art.png"}
    # not declared, but the file was attached to this prompt: taken
    new2 = copy.deepcopy(new)
    new2["changed"] = []
    merged, _ = B.merge(base, new2, "use this on the end card", attached=["art.png"])
    assert "art.png" in {a["file"] for a in merged["assets"]}
    merged, _ = B.merge(base, new2, "use this on the end card")
    assert "art.png" not in {a["file"] for a in merged["assets"]}
    # "keep the logo" is not a removal
    assert not B.asks_removal("keep the logo, no sound", "logo")
    assert B.asks_removal("no logo please", "logo") and B.asks_removal("without the stopwatch", "hook_icon")


def test_an_attached_picture_the_model_did_not_place_replaces_the_end_art(tmp_path):
    up = tmp_path / "mascot.png"
    up.write_bytes(b"x")
    current = B.check(B.default_brief())
    raw = copy.deepcopy(current)  # the model changed nothing
    b = planner.plan("I like this creative. Keep everything exactly the same, but replace this asset.",
                     FakeModel(raw), uploads={"mascot.png": up}, current=current)
    assert [(a["file"], a["role"]) for a in b["assets"]] == [("mascot.png", "end_art")]
    assert "assets" in b["changed"]
    assert any("mascot.png" in a and "could also be" in a for a in b["assumptions"])
    b = planner.plan("Swap the button for this one", FakeModel(copy.deepcopy(current)), uploads={"mascot.png": up},
                     current=current)
    assert [(a["file"], a["role"]) for a in b["assets"]] == [("mascot.png", "button")]
    assert not any("could also be" in a for a in b["assumptions"])


def test_the_planner_sees_the_inventory(tmp_path):
    model = FakeModel(B.check(B.default_brief()))
    planner.plan("replace the coin pile", model, current=B.check(B.default_brief()),
                 inventory="- picture end_art = the picture on the end card: shows a coin pile")
    assert "THINGS IN THIS AD NOW" in model.calls[0][1] and "coin pile" in model.calls[0][1]


def test_exact_edits_change_one_group():
    b = B.check(B.default_brief())
    out, words = edits.direct_edit(b, {"picture": "end_art", "file": "art.png"}, {"art.png": Path("art.png")}, set())
    assert out["changed"] == ["assets"] and out["assets"][-1]["file"] == "art.png" and "keep everything" in words
    out, _ = edits.direct_edit(b, {"caption": "hook", "text": "Beat this!"}, {}, set())
    assert out["changed"] == ["concept.hook"] and out["concept"]["hook"] == "Beat this!"
    out, _ = edits.direct_edit(b, {"sound": False}, {}, set())
    assert out["changed"] == ["audio"] and out["audio"]["sfx"] is False
    out, _ = edits.direct_edit(b, {"picture": "hook_icon", "file": None}, {}, set())
    assert out["assets"][-1]["file"] == "builtin:none"
    with pytest.raises(ValueError):
        edits.direct_edit(b, {"picture": "button", "file": None}, {}, set())
    with pytest.raises(ValueError):
        edits.direct_edit(b, {"picture": "end_art", "file": "not_uploaded.png"}, {}, set())
    with pytest.raises(ValueError):
        edits.direct_edit(b, {"caption": "end_cta", "text": " "}, {}, set())


def test_ad_options_map_slots(tmp_path):
    b = B.check(B.default_brief())
    b["assets"] = [{"file": "builtin:none", "role": "sticker", "when": "hook", "where": "auto"},
                   {"file": "btn.png", "role": "button", "when": "end_card", "where": "auto"},
                   {"file": "builtin:none", "role": "end_art", "when": "end_card", "where": "auto"}]
    o = studio.ad_options(b, {"btn.png": tmp_path / "btn.png"})
    assert o["hook_icon"] == "" and o["end_art"] == "" and o["button_image"] == str(tmp_path / "btn.png")


# ---------- the edit report ----------

@pytest.fixture(scope="module")
def versions(tmp_path_factory):
    """Three versions in a studio folder: v1 the default ad, v2 a hook edit, v3 a hook edit that
    also (wrongly) changed the button text."""
    root = tmp_path_factory.mktemp("studio")
    rec_dir = make_recording(root / "recordings" / "r1")
    rec = Recording.load(rec_dir)
    sha = hashlib.sha256((rec_dir / "level.json").read_bytes()).hexdigest()
    out = {}
    for n, opts in ((1, {}), (2, {"texts": {"hook": "Beat this clock?"}}),
                    (3, {"texts": {"hook": "Beat this clock?", "cta": "GO"}})):
        ad = build_ad(rec, LENGTH, options=opts)
        d = root / "c" / f"v{n}" / "ad"
        render(ad, d, draft=True)
        b = B.check(B.default_brief())
        out[n] = {"n": n, "brief": b, "level": {"sha": sha}, "recording": {"dir": "recordings/r1"},
                  "ad_dir": f"c/v{n}/ad"}
    return root, out


def test_a_hook_edit_changes_only_the_hook(versions):
    root, v = versions
    r = E.report(v[1], v[2], root, groups=["concept.hook"])
    by = {x["item"]: x for x in r["rows"]}
    assert by["copy"]["status"] == "asked" and "Beat this clock?" in by["copy"]["detail"]
    for item in ("gameplay", "camera", "sequence", "visual", "assets", "sound"):
        assert by[item]["status"] == "kept", item
    assert r["ok"] and "Only what was asked changed" in r["verdict"]


def test_an_unasked_change_fails_the_edit(versions):
    root, v = versions
    r = E.report(v[1], v[3], root, groups=["concept.hook"])
    by = {x["item"]: x for x in r["rows"]}
    assert by["copy"]["status"] == "not_asked" and "end_cta" in by["copy"]["detail"]
    assert not r["ok"] and "Changed without being asked" in r["verdict"]


def test_identical_versions_report_nothing_changed(versions):
    root, v = versions
    r = E.report(v[1], v[1], root, groups=[])
    assert r["verdict"] == "Nothing changed." and all(x["status"] == "kept" for x in r["rows"])


def test_common_moves():
    assert E.common_moves([1, 2, 3, 4], [1, 2, 4]) == (2, 3)
    assert E.common_moves([], [1]) == (0, 0)


def test_a_default_hook_follows_only_a_new_ending(versions):
    """The default hook is written from the ending: a new ending explains a new default hook; more
    mistakes do not."""
    root, v = versions
    r = E.report(v[1], v[2], root, groups=["gameplay.mistakes"])
    assert {x["item"]: x["status"] for x in r["rows"]}["copy"] == "not_asked"
    win = copy.deepcopy(v[2])
    win["brief"]["gameplay"]["ending"] = "win"
    r = E.report(v[1], win, root, groups=["gameplay.ending"],
                 notes=["cap_mistake starts at 3.10 s so it does not overlap another caption"])
    by = {x["item"]: x for x in r["rows"]}
    assert by["copy"]["status"] == "side_effect" and "new ending" in by["copy"]["detail"]


# ---------- the closest play ----------

def test_a_gameplay_edit_keeps_as_many_moves_as_it_can(tmp_path):
    level = load_level(LEVEL)
    b = B.check(B.default_brief())
    prev = studio._plan(b, level, 0)
    rec = tmp_path / "rec"
    rec.mkdir()
    (rec / "play.json").write_text(json.dumps({"beats": prev.to_dict(level)["beats"]}))
    nb = copy.deepcopy(b)
    nb["gameplay"]["mistakes"] = 2
    assert studio._replans(b, nb)
    studio.closest_seed(nb, LEVEL, rec, 1, studio.Log(lambda line: None), seeds=8, budget_s=5)
    note = B.control(nb, "gameplay")["engine"][-1]
    assert "closest to v1" in note and "in common" in note
    chosen = studio._plan(nb, level, nb["gameplay"]["seed"] or 0)
    k, lcs = E.common_moves([E.beat_key(x) for x in prev.to_dict(level)["beats"]],
                            [E.beat_key(x) for x in chosen.to_dict(level)["beats"]])
    for s in range(8):  # no other seed tried keeps more
        other = studio._plan(nb, level, s)
        assert E.common_moves([E.beat_key(x) for x in prev.to_dict(level)["beats"]],
                              [E.beat_key(x) for x in other.to_dict(level)["beats"]]) <= (k, lcs)
    retake = copy.deepcopy(b)
    retake["gameplay"]["seed"] = 5
    assert not studio._replans(b, retake)  # a new take on purpose is not searched


def test_same_frames_and_pin_of(tmp_path, monkeypatch):
    a = make_recording(tmp_path / "a")
    b = make_recording(tmp_path / "b", shade=30)  # filmed again with another look: the same play
    assert studio.same_frames(a, a) and studio.same_frames(a, b)
    r = json.loads((b / "result.json").read_text())
    r["drags"][1]["start_frame"] += 3
    (b / "result.json").write_text(json.dumps(r))
    assert not studio.same_frames(a, b)
    monkeypatch.setattr(studio, "STUDIO", tmp_path)
    ad = build_ad(Recording.load(a), LENGTH)
    (tmp_path / "v1" / "ad").mkdir(parents=True)
    (tmp_path / "v1" / "ad" / "ad.json").write_text(json.dumps(ad))
    pin = studio.pin_of({"n": 1, "ad_dir": "v1/ad"})
    assert pin["length_s"] == ad["length_s"] and pin["replay_from"] == ad["segments"]["replay"]["from"]


# ---------- inventory ----------

def test_inventory_names_every_picture_and_caption(versions):
    root, v = versions
    d = root / v[1]["ad_dir"]
    inv = edits.inventory(json.loads((d / "ad.json").read_text()), json.loads((d / "compose.json").read_text()))
    ids = {x["id"] for x in inv}
    assert {"hook_icon", "end_art", "button", "end_background", "cursor", "sound", "hook", "end_cta"} <= ids
    art = next(x for x in inv if x["id"] == "end_art")
    assert art["shows"] == "a stopwatch" and art["can_remove"] and art["when"][1] == LENGTH
    cursor = next(x for x in inv if x["id"] == "cursor")
    assert cursor["when"][1] < LENGTH  # the cursor is on the gameplay parts only
    text = edits.describe_for_planner(inv)
    assert "role 'end_art'" in text and "field concept.hook" in text


def test_the_games_name_is_not_evidence():
    """'Color Block Jam' in a prompt is the game's name, not a request for a jam-packed board, colours
    or blocks (the case's own p.4 prompt got a packed, symmetric, colourful board from it)."""
    p4 = ("Create a difficult Color Block Jam level with a narrow center section and show gameplay where the "
          "player almost fails before solving it.")
    for group in ("level.style", "level.colours", "gameplay.events"):
        assert B._evidence(group, p4, B.default_brief()) is not None, group
    assert B._evidence("level.style", "Make it packed like a real jam level", B.default_brief()) is None
    assert B._evidence("level.shape", p4, B.default_brief()) is None  # the narrow centre is asked for


# ---------- difficulty edits keep the board ----------

def test_board_from_dict_round_trips_the_hand_level():
    from cbj.generate import board_from_dict
    d = json.loads(LEVEL.read_text())
    b = board_from_dict(d)
    assert b is not None
    again = b.to_dict()
    for k in ("gridWidth", "gridHeight", "GridBlockDatas", "ExitDatas"):
        assert again[k] == d[k], k


def test_harder_edits_the_same_board():
    from cbj.generate import Spec, board_changes, board_from_dict, edit_board, hardness
    from cbj.difficulty import rate
    from cbj.level import level_from_dict
    d = json.loads(LEVEL.read_text())
    got = edit_board(d, Spec(shape="narrow_center", width=6, height=8, blocks=7, difficulty="hard"), "harder",
                     budget_s=15)
    assert got is not None
    new, full, stats = got
    ch = board_changes(board_from_dict(d), board_from_dict(new))
    assert 1 <= ch["count"] <= 3 and ch == {k: stats["edit"][k] for k in ch}
    assert hardness(full) >= hardness(rate(level_from_dict(d, name="x"))) + 0.5
    assert full.naive_capped <= 0.05 * full.runs  # still fair


def test_harder_is_a_level_edit_not_a_new_take():
    current = B.check(B.default_brief())
    current["level"]["difficulty"] = "hard"
    raw = copy.deepcopy(current)
    raw["gameplay"]["seed"] = 7  # what the model did live: a "harder instance" by a new seed
    declare(raw, "gameplay.retake")
    b = planner.plan("Keep everything, but make the level harder.", FakeModel(raw), current=current)
    assert b["gameplay"]["seed"] == current["gameplay"]["seed"]  # no evidence for a new take
    assert b["level"]["edit"] == {"dir": "harder", "of": None} and "level.difficulty" in b["changed"]
    assert b["level"]["difficulty"] == "hard"
    assert B.relative_difficulty("a bit easier please") == "easier" and B.relative_difficulty("new hook") is None
    assert B._evidence("gameplay.retake", "give me another take", current) is None


def test_difficulty_only_level_changes_edit_the_board():
    a = B.default_brief()["level"]
    b = {**a, "difficulty": "hard"}
    c = {**a, "edit": {"dir": "harder", "of": 2}}
    d = {**a, "difficulty": "hard", "shape": "ring"}
    assert studio._difficulty_only(a, b) and studio._difficulty_only(a, c) and not studio._difficulty_only(a, d)
    assert not studio._difficulty_only(a, a)


# ---------- regressions from the Fable 5.1 check ----------

def test_a_pinned_edit_never_adds_a_replay_nobody_saw(rec):
    """Fable #1: removing the result screen freed time, and the pinned build filled it with a replay."""
    base = build_ad(rec, LENGTH, options={"replay": False})
    pin = {**pin_of(base), "add_replay": False}
    ad = build_ad(rec, LENGTH, options={"result_screen": False}, pin=pin)
    assert "replay" not in ad["order"] and "replay_tag" not in ad["layers"]
    turned_on = build_ad(rec, LENGTH, options={}, pin={**pin, "add_replay": True})
    assert "replay" in turned_on["order"] or any("no slow-motion replay" in n["text"] for n in turned_on["brief_notes"])


def test_the_pinned_intro_note_gives_the_cut():
    from cbj.ad import _pinned_card
    notes = []
    card, intro, hold, total = _pinned_card(60, 30, 0, 900, lambda ctl, text, status="adjusted": notes.append(text))
    assert (intro, hold, card, total) == (0, 0, 90, 930) and "1.0 s shorter" in notes[0] and "longer" in notes[1]
    # an ad of the case's length is never shortened under 30 s: the freed time fills the card instead
    notes = []
    card, intro, hold, total = _pinned_card(600, 0, 0, 930, lambda ctl, text, status="adjusted": notes.append(text))
    assert total == 900 and card > 300 and any("not shortened under 30" in n for n in notes)


def test_side_effects_must_be_proven(versions):
    """Fable #2: a colour edit cannot excuse a new hook text or a new icon."""
    root, v = versions
    r = E.report(v[1], v[2], root, groups=["visuals.colours"])
    assert {x["item"]: x["status"] for x in r["rows"]}["copy"] == "not_asked" and not r["ok"]
    rec_dir = root / "recordings" / "r1"
    ad = build_ad(Recording.load(rec_dir), LENGTH, options={"hook_icon": "CoinPile.png"})
    render(ad, root / "c" / "v9" / "ad", draft=True)
    v9 = {**v[1], "n": 9, "ad_dir": "c/v9/ad"}
    r = E.report(v[1], v9, root, groups=["visuals.colours"])
    by = {x["item"]: x for x in r["rows"]}
    assert by["assets"]["status"] == "not_asked" and "NOT ASKED" in by["assets"]["detail"]
    b9 = copy.deepcopy(v[1]["brief"])
    b9["assets"] = [{"file": "CoinPile.png", "role": "sticker", "when": "hook", "where": "auto"}]
    r = E.report(v[1], {**v9, "brief": b9}, root, groups=["assets"])
    assert r["ok"] and {x["item"]: x["status"] for x in r["rows"]}["assets"] == "asked"


def test_compare_mode_only_says_differs(versions):
    root, v = versions
    r = E.report(v[1], v[3], root, groups=[], compare=True)
    assert {x["status"] for x in r["rows"]} <= {"kept", "changed"} and r["verdict"].startswith("These differ")


def test_a_replaced_logo_keeps_its_corner():
    """Fable #4: Replace moved a top-right logo to the top left (and so re-laid every caption)."""
    b = B.check(B.default_brief())
    b["assets"] = [{"file": "logo.png", "role": "logo", "when": "whole", "where": "top_right"}]
    out, _ = edits.replace_picture(b, "logo", "new.png")
    assert out["assets"] == [{"file": "new.png", "role": "logo", "when": "whole", "where": "top_right"}]


@pytest.mark.parametrize("prompt,want", [
    ("Keep everything the same, but make the hook harder to ignore: 'Bet you can't beat this clock'.", None),
    ("The hook is too hard to read, make it bigger", None),
    ("Keep the level; make the captions simpler", None),
    ("Make the mistake trickier to spot", None),
    ("Keep everything, but make the level harder.", "harder"),
    ("make it a bit easier", "easier"),
    ("Make it harder and change the hook to 'Go!'", "harder"),
])
def test_difficulty_words_about_copy_are_not_level_edits(prompt, want):
    """Fable #5: "make the hook harder to ignore" became a new board."""
    assert B.relative_difficulty(prompt) == want


@pytest.mark.parametrize("prompt,slot,want", [
    ("Hide the timer, keep our logo", "logo", False),
    ("Drop the 'Hurry!' caption, keep the logo as it is", "logo", False),
    ("keep the logo, no sound", "logo", False),
    ("remove the logo", "logo", True), ("no logo please", "logo", True),
    ("without the stopwatch", "hook_icon", True),
])
def test_removal_needs_the_slot_in_the_same_clause(prompt, slot, want):
    """Fable #6: "keep our logo" deleted the logo."""
    assert B.asks_removal(prompt.lower(), slot) is want


def test_an_attachment_on_a_caption_edit_is_not_placed(tmp_path):
    """Fable #11: "Change the hook to 'Beat this!'" put an unmentioned attachment beside the hook."""
    up = tmp_path / "oops.png"
    up.write_bytes(b"x")
    current = B.check(B.default_brief())
    b = planner.plan("Change the hook to 'Beat this!'", FakeModel(copy.deepcopy(current)),
                     uploads={"oops.png": up}, current=current)
    assert b["assets"] == []


def test_confirmation_edge_cases(versions):
    """Fable's confirmation: a shorter hook is not a failure (A); the button's text never follows
    the play (B); a play edit does not excuse a new level (C)."""
    root, v = versions
    r = E.report(v[2], v[1], root, groups=["concept.hook"])  # the hook gets shorter again
    assert r["ok"], r["verdict"]
    r = E.report(v[1], v[3], root, groups=["gameplay.mistakes"])  # the button's text changed too
    assert {x["item"]: x["status"] for x in r["rows"]}["copy"] == "not_asked"
    other_level = {**v[2], "level": {"sha": "0" * 64}}
    by = {x["item"]: x["status"] for x in
          E.report(v[1], {**other_level, "recording": {"dir": "recordings/r1"}}, root, groups=["gameplay.hesitations"])["rows"]}
    assert by["gameplay"] == "kept"  # the same recording: nothing to judge
    rec2 = make_recording(root / "recordings" / "r2", shade=10)
    v4 = {**other_level, "n": 4, "recording": {"dir": "recordings/r2"}}
    by = {x["item"]: x["status"] for x in E.report(v[2], v4, root, groups=["gameplay.hesitations"])["rows"]}
    assert by["gameplay"] == "not_asked"
    by = {x["item"]: x["status"] for x in E.report(v[2], v4, root, groups=["level.difficulty"])["rows"]}
    assert by["gameplay"] == "asked"


def test_removal_reads_lists_and_phrasings():
    assert B.asks_removal("remove the hurry caption and the logo", "logo")
    assert B.asks_removal("take the logo out", "logo") and B.asks_removal("i don't want the logo anymore", "logo")
    assert not B.asks_removal("keep the logo and remove the hook icon", "logo")
    assert B.relative_difficulty("the end card looks too hard on the eyes, soften it") is None


def test_two_corner_stickers_fill_both_top_corners():
    """"The attached toy pictures as stickers in the two top corners": a second corner is its own
    slot, so the second sticker never overwrites the first (2026-10-14, found by the viewer's review)."""
    from cbj import edits
    from cbj.ad import AD_OPTIONS, BAND
    assert B.asset_slot({"role": "sticker", "when": "whole", "where": "top_left"}) == "logo"
    assert B.asset_slot({"role": "sticker", "when": "whole", "where": "top_right"}) == "logo2"
    assert B.asset_slot({"role": "logo", "when": "whole", "where": "top_right"}) == "logo"
    b = B.check(raw_brief(assets=[{"file": "teddy.png", "role": "sticker", "when": "whole", "where": "top_left"},
                                  {"file": "bricks.png", "role": "sticker", "when": "whole", "where": "top_right"}]),
                uploads={"teddy.png": Path("teddy.png"), "bricks.png": Path("bricks.png")})
    assert sorted(B.asset_slot(a) for a in b["assets"]) == ["logo", "logo2"]
    assert edits.PICTURES["logo2"]["name"].startswith("the sticker")


def test_coloured_blocks_is_talk_about_colours():
    """"Five colored blocks" in an edit of a red/green/blue creative: the prompt speaks of the blocks'
    colours, so the planner's palette (any colours) is taken and the old three-colour limit goes;
    the block count is five blocks, not five colours (2026-10-15)."""
    p = "Create a medium Color Block Jam level with five colored blocks and a narrow central corridor."
    assert B._evidence("level.colours", p, B.default_brief()) is None
    assert B._evidence("level.blocks", p, B.default_brief()) is None
    assert B._evidence("level.colours", "Create a medium level with five blocks.", B.default_brief()) is not None
    cur = B.check(B.default_brief()); cur["level"]["colours"] = ["Red", "Green", "Blue"]
    new = B.check(B.default_brief()); new["level"]["blocks"] = 5
    new["changed"] = ["level.blocks", "level.colours"]
    new["controls"] = [{"control": "level", "asked": "five colored blocks", "plan": "", "status": "applied", "why": None, "engine": []}]
    merged, dropped = B.merge(cur, new, p)
    assert merged["level"]["colours"] == [] and "level.colours" in merged["changed"] and merged["level"]["blocks"] == 5
    assert not any(d.startswith("level.colours") for d in dropped)


# ---------- the preservation checklist, the timeline numbers and a chain of edits (2026-10-15) ----------

@pytest.fixture(scope="module")
def chain(tmp_path_factory):
    """Four versions, each one edit on the previous (compose only, the same recording): the hook,
    then the button text, then the result caption."""
    root = tmp_path_factory.mktemp("studio")
    rec_dir = make_recording(root / "recordings" / "r1")
    rec = Recording.load(rec_dir)
    sha = hashlib.sha256((rec_dir / "level.json").read_bytes()).hexdigest()
    texts, out = {}, {}
    steps = [(1, None, None), (2, "hook", "Beat this clock?"), (3, "cta", "GO"), (4, "result", "Phew! Just made it")]
    for n, key, text in steps:
        if key:
            texts[key] = text
        ad = build_ad(rec, LENGTH, options={"texts": dict(texts)} if texts else {})
        d = root / "c" / f"v{n}" / "ad"
        render(ad, d, draft=True)
        out[n] = {"n": n, "brief": B.check(B.default_brief()), "level": {"sha": sha}, "recording": {"dir": "recordings/r1"},
                  "ad_dir": f"c/v{n}/ad"}
    return root, out


def test_a_chain_of_edits_does_not_accumulate_unrelated_changes(chain):
    """Three edits in a row: every step changes only its caption, and v1 to v4 differ only in the
    three captions asked along the way (the designer chain v1-v11 of 2026-10-15, as a test)."""
    root, v = chain
    groups = {2: ["concept.hook"], 3: ["concept.cta"], 4: ["concept.result"]}
    for n in (2, 3, 4):
        r = E.report(v[n - 1], v[n], root, groups=groups[n])
        by = {x["item"]: x for x in r["rows"]}
        assert by["copy"]["status"] == "asked", (n, by["copy"])
        # a caption's band resizes with its words: Composition may be "asked", never "not asked"
        assert all(x["status"] == "kept" or (k == "composition" and x["status"] == "asked") for k, x in by.items() if k != "copy"), \
            (n, [(k, x["status"]) for k, x in by.items()])
        assert r["ok"] and "Only what was asked changed" in r["verdict"]
    r = E.report(v[1], v[4], root, groups=["concept.hook", "concept.cta", "concept.result"])
    by = {x["item"]: x for x in r["rows"]}
    assert by["copy"]["status"] == "asked" and all(x["status"] == "kept" or (k == "composition" and x["status"] == "asked")
                                                   for k, x in by.items() if k != "copy")
    assert "Beat this clock?" in by["copy"]["detail"] and "GO" in by["copy"]["detail"] and "Phew! Just made it" in by["copy"]["detail"]


def test_the_report_carries_a_preservation_checklist_and_timeline_numbers(chain):
    root, v = chain
    r = E.report(v[1], v[2], root, groups=["concept.hook"])
    c = r["checklist"]
    assert set(c) == {"level_unchanged", "moves_unchanged", "move_timing_unchanged", "gameplay_render_reused", "duration_unchanged",
                      "camera_unchanged", "hud_unchanged", "captions_unchanged", "pictures_unchanged", "audio_unchanged"}
    assert all(c[k]["ok"] for k in c if k != "captions_unchanged") and not c["captions_unchanged"]["ok"]
    assert "recording r1" in c["gameplay_render_reused"]["evidence"]
    assert r["changes"] == ["the hook"] and "Gameplay" in r["preserves"] and "Captions" not in r["preserves"]
    t = next(x for x in r["rows"] if x["item"] == "timing")
    assert t["numbers"]["before"] == t["numbers"]["after"] and t["numbers"]["after"]["fps"] == 30
    assert t["numbers"]["after"]["drags"] == 4 and "fps" in t["detail"] and "play 0.00-" in t["detail"]
    same = E.report(v[1], v[1], root, groups=[])
    assert all(x["ok"] for x in same["checklist"].values())


# ---------- 2026-10-18: the edit scenarios on the ten text creatives ----------

def test_a_pinned_edit_keeps_the_parents_long_end_card():
    """A picture edit on a version whose end card already ran 10.7 s grew the held result by 1.5 s and
    moved the end card (T7 v4); on a 60 s ad with a 25.8 s card it cut the ad to 39.7 s (T10 v4).
    The parent's own card is never freed time."""
    from cbj.ad import FPS, _pinned_card
    notes = []
    note = lambda ctl, text, status=None: notes.append(text)  # noqa: E731
    card, intro, hold, total = _pinned_card(320 + 15 + 30, 15, 30, 900, note, True, parent_card=320)
    assert (card, intro, hold, total) == (320, 15, 30, 900)
    assert not any("freed" in n for n in notes)
    card, intro, hold, total = _pinned_card(774 + 15 + 60, 15, 60, 60 * FPS, note, True, parent_card=774)
    assert (card, hold, total) == (774, 60, 60 * FPS)
    # without the parent's card the old behaviour: the hold grows and the ad is cut
    card, intro, hold, total = _pinned_card(774 + 15 + 60, 15, 60, 60 * FPS, note, True)
    assert hold > 60 and total < 60 * FPS
    # time an edit really freed still goes to the held result first
    card, intro, hold, total = _pinned_card(320 + 45 + 15 + 30, 15, 30, 900, note, True, parent_card=320)
    assert hold == 75 and card == 320 and total == 900


def test_a_revision_may_change_only_what_the_edit_asked():
    """On an open board, 'use this object instead of the current obstacle' was revised by adding a wall
    (a level change) because the viewer saw no obstacle. A revision keeps to the asked groups, except
    to put a group back to what the base version had."""
    from cbj.workflows.edit import keep_to_asked
    base = B.check(B.default_brief())
    v = copy.deepcopy(base)
    v["assets"] = [{"file": "boulder.png", "role": "obstacle", "when": "whole", "where": "auto"}]
    v["changed"] = ["assets"]
    rev = copy.deepcopy(v)
    rev["level"]["changes"] = [{"kind": "wall", "where": "center"}] if "changes" in rev["level"] else rev["level"].get("changes")
    rev["level"]["shape"] = "holes"
    rev["concept"]["hook"] = "Beat this!"
    rev["changed"] = ["level.changes", "level.shape", "concept.hook"]
    widened = set(B.changed_groups(v, rev))
    assert "concept.hook" in widened and "level.shape" in widened
    held = keep_to_asked(rev, v, base, {"assets"})
    assert set(held) == widened
    assert rev["level"] == v["level"] and rev["concept"]["hook"] == v["concept"]["hook"]
    assert "level.shape" not in rev["changed"] and "concept.hook" not in rev["changed"]
    # putting a group back to the base's value is allowed
    v2 = copy.deepcopy(v)
    v2["concept"]["hook"] = "Wrong hook"
    rev2 = copy.deepcopy(v2)
    rev2["concept"]["hook"] = base["concept"]["hook"]
    rev2["changed"] = ["concept.hook"]
    assert keep_to_asked(rev2, v2, base, {"assets"}) == []
    assert rev2["concept"]["hook"] == base["concept"]["hook"]


def test_a_patched_layer_keeps_the_approved_box_unless_every_frame_was_rendered():
    """The cursor spans the whole ad; a hook edit plus an end-card edit render its first and last GOPs
    only, so its box must be joined with the approved render's (the play in between was copied)."""
    from cbj.compose import _runs_cover
    assert _runs_cover(0, 1200, [(0, 90), (90, 1200)])
    assert _runs_cover(100, 200, [(0, 150), (150, 300)])
    assert not _runs_cover(0, 1200, [(0, 90), (1110, 1200)])  # first and last frames rendered, the middle copied
    assert not _runs_cover(100, 200, [(0, 150), (160, 300)])  # a gap
    assert _runs_cover(5, 6, [(0, 10)])


def test_the_obstacle_picture_on_a_board_without_walls_is_an_asked_change(tmp_path):
    """'Use this object instead of the current obstacle' on an open board: the compositor puts the
    picture beside the hook and says so; the report counts that slot as the asked one (T7 v4 reported
    it as changed without being asked)."""
    import shutil
    from PIL import Image
    root = tmp_path / "studio"
    rec_dir = make_recording(root / "recordings" / "r1")
    shutil.copy(Path(__file__).parent.parent / "data/levels/Level_06.json", rec_dir / "level.json")  # 8 blocks, no walls
    rec = Recording.load(rec_dir)
    png = root / "stone.png"
    Image.new("RGBA", (64, 64), (120, 110, 100, 255)).save(png)
    sha = hashlib.sha256((rec_dir / "level.json").read_bytes()).hexdigest()
    out = {}
    for n, opts in ((1, {}), (2, {"obstacle": str(png)})):
        ad = build_ad(rec, LENGTH, options=opts)
        d = root / "c" / f"v{n}" / "ad"
        render(ad, d, draft=True)
        b = B.check(B.default_brief())
        if n == 2:
            b["assets"] = [{"file": "stone.png", "role": "obstacle", "when": "whole", "where": "auto"}]
        out[n] = {"n": n, "brief": b, "level": {"sha": sha}, "recording": {"dir": "recordings/r1"}, "ad_dir": f"c/v{n}/ad"}
    assert "obstacle" not in out and any("beside the hook" in x["text"] for x in ad["brief_notes"])
    r = E.report(out[1], out[2], root, groups=["assets"])
    by = {x["item"]: x for x in r["rows"]}
    assert by["assets"]["status"] == "asked" and "beside the hook" in by["assets"]["detail"]
    assert by["composition"]["status"] in ("kept", "asked", "side_effect"), by["composition"]
    assert r["ok"], r["verdict"]


def test_the_closest_play_must_do_the_asked_order_first(tmp_path):
    """'Keep everything, but the purple block should leave first' (T3, 2026-10-18): the planner falls back to
    no events on a seed that cannot do them, and the closest of those plays won on similarity while dark
    green left first. A play that does the asked order beats a closer one that does not."""
    from dataclasses import replace
    from cbj.events import SOLVER_ACTIONS, check_events, from_brief
    level = load_level(LEVEL)
    b = B.check(B.default_brief())
    prev = studio._plan(b, level, 0)
    rec = tmp_path / "rec"
    rec.mkdir()
    (rec / "play.json").write_text(json.dumps({"beats": prev.to_dict(level)["beats"]}))
    nb = copy.deepcopy(b)
    nb["gameplay"]["events"] = [{"block": {"colour": "Purple", "which": "any", "all": False}, "action": "leaves", "when": "first"}]
    studio.closest_seed(nb, LEVEL, rec, 1, studio.Log(lambda line: None), seeds=8, budget_s=10)
    evs, _ = from_brief(level, nb["gameplay"]["events"])
    solver = [e for e in evs if e.action in SOLVER_ACTIONS]

    def meets(script):
        sd = script.to_dict(level)
        return not any("cannot happen" in n for n in script.notes) and \
            check_events(level, solver, script.drags, [x["kind"] for x in sd["beats"]]).ok
    chosen = studio._plan(nb, level, nb["gameplay"]["seed"] or 0)
    note = B.control(nb, "gameplay")["engine"][-1]
    if any(meets(studio._plan(nb, level, s)) for s in range(8)):
        assert meets(chosen), note
        assert "none of them" not in note
    else:
        assert "none of them does the asked order" in note


def test_a_style_image_is_not_also_placed_as_a_picture():
    """'Keep this creative exactly the same, but take the colours from this image' (T7, 2026-10-18): the model read
    the picture into the look, and the unplaced-attachment rule then also put it on the end card."""
    current = B.check(B.default_brief())
    b = copy.deepcopy(current)
    b["visuals"]["blocks"] = [{"slot": "Red", "hex": "#FF7F50", "name": "coral"}]
    b["changed"] = ["visuals.colours"]
    planner._place_unplaced(b, "Keep this creative exactly the same, but take the colours from this image.", ["ocean.png"], current)
    assert not any(a["file"] == "ocean.png" for a in b["assets"]) and "assets" not in b["changed"]
    b2 = copy.deepcopy(current)
    b2["changed"] = []
    planner._place_unplaced(b2, "Keep this creative exactly the same, but replace this object with the attached asset.", ["star.png"], current)
    assert any(a["file"] == "star.png" for a in b2["assets"])  # the p.4 sentence still places it, with an assumption
    assert any("star.png" in a for a in b2["assumptions"])


def test_a_slot_the_model_guessed_for_this_object_is_written_as_an_assumption():
    current = B.check(B.default_brief())
    b = copy.deepcopy(current)
    b["assets"] = [a for a in b["assets"]] + [{"file": "gold_star.png", "role": "button", "when": "end_card", "where": "auto"}]
    b["changed"] = ["assets"]
    planner._note_guessed_slot(b, "Keep this creative exactly the same, but replace this object with the attached asset.", ["gold_star.png"], current)
    assert any("gold_star.png" in a and "PLAY NOW button" in a and "could also be" in a for a in b["assumptions"]), b["assumptions"]
    b3 = copy.deepcopy(current)
    b3["assets"] = b3["assets"] + [{"file": "gold_star.png", "role": "button", "when": "end_card", "where": "auto"}]
    b3["changed"] = ["assets"]
    planner._note_guessed_slot(b3, "Use gold_star.png as the button.", ["gold_star.png"], current)
    assert not b3["assumptions"]  # the request names the thing
