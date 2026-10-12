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
    card, intro, total = _pinned_card(60, 30, 900, lambda ctl, text, status="adjusted": notes.append(text))
    assert (intro, card, total) == (0, 90, 930) and "1.0 s shorter" in notes[0] and "longer" in notes[1]


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
