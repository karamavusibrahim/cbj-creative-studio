"""Text to creative: the brief, the planner (with a fake model, so no network), the level
generator, and the ad options a brief sets. The full loop with Unity is in test_unity_render."""

import copy
import json
import random

import pytest

from cbj import brief as B
from cbj import planner
from cbj.ad import Recording, build_ad, fill
from cbj.compose import Prepared
from cbj.difficulty import rate
from cbj.generate import Spec, band_of, candidate, generate, holes_for
from cbj.level import level_from_dict, validate
from cbj.solver import solve_fast
from cbj.studio import SLOT_ENUM, ad_options, game_visuals

from test_ad import LENGTH, make_recording


class FakeModel:
    """Returns a fixed brief for planning calls and a fixed translation for translation calls."""

    def __init__(self, raw: dict, translation: dict | None = None):
        self.raw, self.translation, self.calls = raw, translation or {}, []
        self.last_model = "fake"

    def complete(self, system, user, schema):
        self.calls.append((system, user))
        if system.startswith("Translate"):
            keys = schema["properties"]
            return json.dumps({k: self.translation.get(k, f"[{k}]") for k in keys})
        return json.dumps(self.raw)


def raw_brief(**sections) -> dict:
    b = B.default_brief()
    for k, v in sections.items():
        if isinstance(v, dict) and isinstance(b.get(k), dict):
            b[k].update(v)
        else:
            b[k] = v
    return b


def asked(b: dict, *controls: str, words: str = "asked") -> dict:
    for c in controls:
        B.control(b, c).update(asked=words, status="applied", plan="as asked")
    return b


def declare(b: dict, *groups: str) -> dict:
    """The field groups the model says the prompt changed."""
    b["changed"] = sorted(set(b.get("changed", [])) | set(groups))
    return b


# ---------- the brief ----------

def test_default_brief_is_valid_and_all_default():
    b = B.check(B.default_brief())
    assert [c["control"] for c in b["controls"]] == list(B.CONTROLS)
    assert {c["status"] for c in b["controls"]} == {"default"}


@pytest.mark.parametrize("theme", ["candy", "pastel", "neon", "dark"])
def test_theme_palettes_keep_gates_apart(theme):
    b = B.check(raw_brief(visuals={"theme": theme}))
    assert B.control(b, "visuals")["status"] == "default"  # no colour had to be taken back


def test_same_colour_for_every_block_is_taken_back_with_a_reason():
    b = raw_brief(visuals={"blocks": [{"slot": s, "hex": "#008080", "name": "teal"} for s in B.COLOURS]})
    b = B.check(b)
    row = B.control(b, "visuals")
    assert row["status"] == "adjusted" and "easy to tell apart" in row["why"]
    # every slot is kept, each deepened toward its own game colour until the gates can be told apart
    shown = [e["hex"] for e in b["visuals"]["blocks"]]
    assert len(shown) == len(B.COLOURS)
    assert all(B.colour_distance(a, c) >= B.MIN_COLOUR_DISTANCE for i, a in enumerate(shown) for c in shown[i + 1:])


def test_display_names_reach_the_captions():
    b = B.check(raw_brief(visuals={"blocks": [{"slot": "Red", "hex": "#FF69B4", "name": "pink"}]}))
    shown = B.display_colours(b)
    assert shown["Red"]["name"] == "pink" and shown["Blue"]["name"] == "blue"
    names = ad_options(b, {})["colour_names"]
    assert names == {"RED": "pink"}
    assert set(SLOT_ENUM) == set(B.COLOURS)


def test_invented_odds_in_copy_are_replaced_and_reported():
    b = B.check(raw_brief(concept={"hook": "Only 1% can solve this!", "end_fact": "Cleared in {time_used} seconds"}))
    assert b["concept"]["hook"] is None and b["concept"]["end_fact"] == "Cleared in {time_used} seconds"
    assert "percentage" in B.control(b, "concept")["why"]


def test_unknown_fact_is_refused():
    b = B.check(raw_brief(concept={"end_fact": "Solved by {player_name}"}))
    assert b["concept"]["end_fact"] is None and "not a fact" in B.control(b, "concept")["why"]


def test_time_out_moves_to_social_and_a_medium_level():
    b = B.check(raw_brief(gameplay={"ending": "time_out"}, level={"difficulty": "easy"}))
    assert b["channel"] == "social" and b["level"]["difficulty"] == "medium"
    assert B.control(b, "gameplay")["status"] == "adjusted"


def test_other_formats_are_made_from_the_master():
    b = B.check(raw_brief(format="1:1"))
    assert b["format"] == "1:1" and B.control(b, "visuals")["status"] != "not_supported"
    b = B.check(raw_brief(format="3:2"))
    assert b["format"] == "9:16" and "formats are" in B.control(b, "visuals")["why"]


def test_clock_is_set_by_a_near_fail_not_the_prompt():
    b = B.check(raw_brief(gameplay={"timer_s": 10}))
    assert b["gameplay"]["timer_s"] is None and "set by the ending" in B.control(b, "difficulty_pacing")["why"]


def test_merge_takes_only_the_declared_changes():
    old = B.check(raw_brief(concept={"hook": "Can you beat it?"}, visuals={"theme": "neon"}))
    new = copy.deepcopy(old)
    new["concept"]["hook"] = "Beat this in 20 seconds"
    new["visuals"]["theme"] = "pastel"  # not declared: must come back
    new["gameplay"]["ending"] = "win"  # not declared: must come back
    declare(new, "concept.hook")
    merged, dropped = B.merge(old, new, "make the hook say 'Beat this in 20 seconds'")
    assert merged["concept"]["hook"] == "Beat this in 20 seconds" and merged["changed"] == ["concept.hook"]
    assert merged["visuals"] == old["visuals"] and merged["gameplay"]["ending"] == old["gameplay"]["ending"]
    assert any(d.startswith("visuals.colours") for d in dropped) and any(d.startswith("gameplay.ending") for d in dropped)
    assert B.changed_controls(old, merged) == ["concept"]


def test_a_request_filed_under_the_wrong_row_still_counts_when_declared():
    # "no sound effects" filed by the model under "unchanged" (Fable's P9): declared, so taken
    old = B.check(B.default_brief())
    new = copy.deepcopy(old)
    new["audio"]["sfx"] = False
    asked(new, "unchanged", words="no sound effects")
    declare(new, "audio")
    merged, _ = B.merge(old, new, "A near-fail ad with no sound effects.")
    assert merged["audio"]["sfx"] is False


def test_copy_and_board_size_need_words_in_the_prompt():
    old = B.check(B.default_brief())
    new = copy.deepcopy(old)
    new["concept"]["hook"] = "Thread the needle!"
    new["level"].update(width=9, height=10, blocks=6, colours=["Red", "Blue"], difficulty="hard")
    declare(new, "concept.hook", "level.size", "level.blocks", "level.colours", "level.difficulty")
    merged, dropped = B.merge(old, new, "A hard board with pillars in the middle")
    assert merged["level"]["difficulty"] == "hard"  # asked
    assert (merged["level"]["width"], merged["level"]["blocks"], merged["level"]["colours"]) == (None, None, [])
    assert merged["concept"]["hook"] is None
    assert {d.split(":")[0] for d in dropped} >= {"concept.hook", "level.size", "level.blocks", "level.colours"}
    merged, _ = B.merge(old, new, "An 8x8 board, 6 red and blue blocks, hook 'Thread the needle!'")
    assert merged["level"]["blocks"] == 6 and merged["concept"]["hook"] == "Thread the needle!"


def test_a_new_language_rewrites_the_copy():
    old = B.check(B.default_brief())
    new = copy.deepcopy(old)
    new["language"], new["concept"]["hook"] = "tr", "Saati yenebilir misin?"
    declare(new, "language")
    merged, _ = B.merge(old, new, "Same ad, but in Turkish.")
    assert merged["language"] == "tr" and merged["concept"]["hook"] == "Saati yenebilir misin?"


# ---------- the planner (fake model) ----------

def test_planner_resets_controls_the_prompt_did_not_mention():
    raw = raw_brief(concept={"hook": "Wrong turn!"}, gameplay={"ending": "win"})
    asked(raw, "gameplay", words="a clean solve")
    declare(raw, "gameplay.ending", "concept.hook")
    b = planner.plan("a clean solve", FakeModel(raw))
    assert b["gameplay"]["ending"] == "win"  # asked
    assert b["concept"]["hook"] is None  # copy nobody asked for is not used
    assert b["planner"]["restored"]


def test_planner_uses_an_upload_only_when_the_prompt_refers_to_it(tmp_path):
    up = tmp_path / "logo.png"
    up.write_bytes(b"x")
    raw = raw_brief(assets=[{"file": "logo.png", "role": "logo", "when": "whole", "where": "top_left"}])
    declare(asked(raw, "assets"), "assets")
    assert planner.plan("a clean solve", FakeModel(raw), uploads={"logo.png": up})["assets"] == []
    b = planner.plan("put our logo in the corner", FakeModel(raw), uploads={"logo.png": up})
    assert [a["file"] for a in b["assets"]] == ["logo.png"]


def test_planner_drops_a_level_number_the_prompt_did_not_give():
    raw = declare(asked(raw_brief(level={"label": 1}), "level"), "level.label")
    assert planner.plan("an easy level", FakeModel(raw))["level"]["label"] is None
    raw = declare(asked(raw_brief(level={"label": 142}), "level"), "level.label")
    assert planner.plan("level 142, easy", FakeModel(raw))["level"]["label"] == 142


def test_planner_translates_the_default_captions():
    raw = declare(asked(raw_brief(language="tr", concept={"hook": "Saati yenebilir misin?"}), "concept"), "language")
    model = FakeModel(raw, {"mistake": "{colour} rengine ulaşamıyorum!", "cta": "HEMEN OYNA"})
    b = planner.plan("Türkçe reklam", model)
    assert b["concept"]["hook"] == "Saati yenebilir misin?"
    assert b["concept"]["mistake"] == "{colour} rengine ulaşamıyorum!" and b["concept"]["cta"] == "HEMEN OYNA"
    assert any(s.startswith("Translate") for s, _ in model.calls)


def test_planner_edit_keeps_the_rest():
    current = planner.plan("a near-fail", FakeModel(asked(raw_brief(), "gameplay")))
    current = {k: v for k, v in current.items() if k != "planner"}
    raw = copy.deepcopy(current)
    raw["concept"]["hook"] = "Beat this!"
    raw["pacing"]["length_s"] = 45.0  # not asked
    declare(asked(raw, "concept"), "concept.hook")
    b = planner.plan("change the hook to 'Beat this!'", FakeModel(raw), current=current)
    assert b["concept"]["hook"] == "Beat this!" and b["pacing"]["length_s"] == current["pacing"]["length_s"]
    assert b["planner"]["edit"]


# ---------- the level generator ----------

@pytest.mark.parametrize("shape", ["open", "narrow_center", "door", "holes"])
def test_candidates_are_valid_levels(shape):
    spec = Spec(shape, difficulty="medium").resolved()
    rng = random.Random(3)
    ok = 0
    for _ in range(30):
        d = candidate(spec, rng)
        lvl = level_from_dict(d, name="t")
        assert not validate(lvl), validate(lvl)
        holes = holes_for(shape, spec.width, spec.height)
        assert {(c["x"], c["y"]) for c in d["inactiveCells"]} == holes
        ok += 1
    assert ok == 30


def test_generator_hits_the_band_and_is_repeatable():
    spec = Spec("open", difficulty="easy", width=6, height=6, blocks=5, colours=["Red", "Blue"], budget_s=8, seed=4)
    d1, r1, st1 = generate(spec)
    d2, _, _ = generate(spec)
    assert d1 == d2  # the same spec and seed give the same level
    assert band_of(r1) == "easy" and r1.blocks == 5
    assert {b["blockColor"] for b in d1["GridBlockDatas"]} <= {2, 3}  # Blue, Red
    lvl = level_from_dict(d1, name="g")
    assert solve_fast(lvl).min_drags == r1.min_drags


def test_rate_uses_the_fast_solver_with_the_same_numbers():
    from cbj.level import load_level
    from test_ad import LEVEL
    d = rate(load_level(LEVEL))
    assert (d.min_drags, d.extra_drags, d.exits_at_start) == (9, 2, 1)
    assert round(d.naive_ratio, 2) == 1.26  # 1.29 before the naive player stopped repeating positions


# ---------- the ad options a brief sets ----------

@pytest.fixture(scope="module")
def rec(tmp_path_factory):
    return Recording.load(make_recording(tmp_path_factory.mktemp("rec") / "nf"))


def test_no_replay_and_removed_caption(rec):
    ad = build_ad(rec, LENGTH, options={"replay": False, "texts": {"hurry": "", "mistake": "Stuck on {colour}!"}})
    assert "replay" not in ad["order"] and "replay_tag" not in ad["layers"]
    assert "cap_hurry" not in ad["layers"] and ad["layers"]["cap_mistake"]["text"] == "Stuck on {colour}!"
    assert any("removed" in n for n in ad["notes"])


def test_result_first_teaser_puts_the_hook_on_frame_zero(rec):
    ad = build_ad(rec, LENGTH, options={"teaser": True})
    assert ad["order"][0] == "teaser" and ad["layers"]["hook"]["start"] == {"seg": "teaser", "at": 0}
    p = Prepared(ad, draft=True)
    assert not p.qa["failures"], p.qa["failures"]
    assert p.layers["hook"]["f0"] == 0


def test_display_colour_names_fill_the_mistake_caption(rec):
    ad = build_ad(rec, LENGTH, options={"colour_names": {"DARK_GREEN": "mint"}})
    assert ad["colour_names"] == {"DARK_GREEN": "mint"}
    lay = ad["layers"]["cap_mistake"]
    assert fill(lay["text"], rec.facts(lay["beat"], ad["colour_names"])) == "I can't reach mint!"


def test_logo_narrows_the_band_and_stays_in_the_safe_area(rec, tmp_path):
    from PIL import Image
    logo = tmp_path / "logo.png"
    Image.new("RGBA", (300, 200), (255, 200, 0, 255)).save(logo)
    ad = build_ad(rec, LENGTH, options={"logo": {"file": str(logo), "where": "top_left"}})
    assert ad["band"]["max_w"] < 820 and ad["band"]["cx"] > 540
    p = Prepared(ad, draft=True)
    assert not p.qa["failures"], p.qa["failures"]
    assert p.layers["logo"]["image"].width <= 150 and p.layers["logo_end"]["f1"] == p.total


def test_sound_off_and_caption_colours(rec):
    ad = build_ad(rec, LENGTH, options={"sfx": False, "fill": "#FFE45C", "stroke": "#222222"})
    assert ad["audio"]["events"] == {}
    assert ad["layers"]["hook"]["fill"] == "#FFE45C" and ad["layers"]["end_title"]["stroke"] == "#222222"
    assert not Prepared(ad, draft=True).qa["failures"]


def test_hand_cursor_and_end_card_gradient(rec):
    ad = build_ad(rec, LENGTH, options={"cursor": "hand", "end_gradient": ["#2A1145", "#4B1C6F"]})
    assert ad["layers"]["cursor"]["image"] == "builtin:hand" and ad["segments"]["end"]["gradient"]
    p = Prepared(ad, draft=True)
    assert p.layers["cursor"]["image"] is not None
    card = p.card_base(ad["segments"]["end"])
    assert tuple(card[0, 0]) == (0x2A, 0x11, 0x45) and tuple(card[-1, 0]) == (0x4B, 0x1C, 0x6F)


def test_game_visuals_for_the_recorder():
    b = B.check(raw_brief(visuals={"theme": "candy", "board": "#3B2A5C"}))
    v = game_visuals(b)
    assert {x["slot"] for x in v["blocks"]} == set(B.COLOURS) and v["grid"] == "#3B2A5C"
    assert v["background_top"] == "#FFD6EC"
    assert game_visuals(B.check(B.default_brief())) == {"blocks": [], "grid": "", "background_top": "",
                                                        "background_bottom": ""}


def test_generated_level_size_follows_the_ad_and_the_board():
    from cbj.generate import Spec, _target_drags
    b = B.check(raw_brief(level={"shape": "narrow_center", "difficulty": "hard"}, pacing={"length_s": 30.0}))
    assert _target_drags(b) == 8  # 30 s, minus the hook, replay, result and end card, one mistake, two hesitations
    b["gameplay"]["mistakes"] = 2
    assert _target_drags(b) == 5  # each mistake takes time from the drags
    probe = Spec("narrow_center", None, None, None, [], "hard").resolved()
    free = probe.width * probe.height - len(holes_for("narrow_center", probe.width, probe.height))
    assert free // 5 == 8  # a 6x8 hourglass holds at most 8 blocks, whatever the length asks for


# ---------- the fixes from the Fable 5.1 check ----------

def test_no_result_screen_still_makes_a_near_fail(rec):
    ad = build_ad(rec, LENGTH, options={"result_screen": False})
    assert "result" not in ad["order"] and "cap_result" not in ad["layers"]
    assert not Prepared(ad, draft=True).qa["failures"]


def test_hidden_clock_drops_the_copy_that_quotes_it(rec):
    ad = build_ad(rec, LENGTH, options={"clock_visible": False})
    texts = [lay.get("text", "") for lay in ad["layers"].values()]
    assert not any("{clock_left}" in t or "clock" in t.lower() for t in texts)
    assert ad["layers"]["hook"].get("icon") is None


def test_hud_hide_lists():
    from cbj.studio import hud_hide
    assert hud_hide({"hud_timer": False, "hud_level": True}) == ["TimerBackground", "TimerImage", "TimeText", "MainBar:image"]
    assert hud_hide({"hud_timer": True, "hud_level": False}) == ["LevelCircle"]
    assert hud_hide({"hud_timer": False, "hud_level": False}) == ["MainBar"]


def test_teaser_is_letterboxed_and_notes_are_structured(rec):
    from cbj.ad import FIT
    ad = build_ad(rec, LENGTH, options={"teaser": True, "sfx": False, "texts": {"hurry": ""}})
    assert ad["segments"]["teaser"]["fit"] == FIT  # the hook in the band, above the game's banner
    by = {(n["control"], n["status"]) for n in ad["brief_notes"]}
    assert ("assets", None) in by and ("concept", None) in by  # done as asked: no status change


def test_a_failed_recording_is_never_reused(tmp_path):
    from cbj.studio import _usable
    folder = make_recording(tmp_path / "r")
    assert not _usable(folder)  # no spec.json
    (folder / "spec.json").write_text("{}")
    assert _usable(folder)
    play = json.loads((folder / "play.json").read_text())
    play["measured"]["problems"] = ["near-fail: the clock stopped with 1.30 s left"]
    (folder / "play.json").write_text(json.dumps(play))
    assert not _usable(folder)


def test_zoom_is_capped_to_keep_the_side_gates():
    b = B.check(raw_brief(visuals={"camera_zoom": 1.3}))
    assert b["visuals"]["camera_zoom"] == B.ZOOM_RANGE[1] and B.control(b, "visuals")["status"] == "adjusted"


# ---------- the fixes from the Fable 5.1 confirmation ----------

def test_keep_is_this_prompts_own_list():
    old = B.check(raw_brief(keep=["level"]))
    new = copy.deepcopy(old)
    new["keep"] = ["level", "assets"]  # not declared as a change: still taken
    merged, dropped = B.merge(old, new, "Keep the level and the logo, but make it harder.")
    assert merged["keep"] == ["level", "assets"] and not any(d.startswith("keep") for d in dropped)
    new["keep"] = []
    merged, _ = B.merge(old, new, "Make it harder.")
    assert merged["keep"] == []  # never inherited from the version being edited


def test_keep_conflict_is_reported():
    from cbj.studio import _keep_conflicts
    old = B.check(B.default_brief())
    new = copy.deepcopy(old)
    new["level"]["difficulty"], new["keep"] = "hard", ["level"]
    _keep_conflicts(old, new, "Keep the level, but make it harder")
    assert any("asked to keep the level" in n for n in B.control(new, "unchanged")["engine"])
    # "keep everything, but X" names nothing to keep: no conflict to report
    quiet = copy.deepcopy(old)
    quiet["level"]["difficulty"], quiet["keep"] = "hard", ["level"]
    _keep_conflicts(old, quiet, "Keep everything exactly the same, but make it harder")
    assert not B.control(quiet, "unchanged").get("engine")


@pytest.mark.parametrize("group,prompt,ok", [
    ("level.colours", "Cleared in a hundred seconds, centred board", False),
    ("level.colours", "red and blue blocks", True),
    ("level.size", "A 20-second ad, level 47", False),
    ("level.size", "An 8x8 board", True),
    ("level.size", "a big board", True),
    ("level.blocks", "A 20-second ad", False),
    ("level.blocks", "with 9 blocks", True),
    ("concept.hook", "the player's first move is wrong", False),
    ("concept.hook", "a rectangle online task", False),
    ("concept.hook", "make the hook say 'Beat this!'", True),
    ("concept.hook", 'end card: "Your turn"', True),
])
def test_evidence_matches_words_not_substrings(group, prompt, ok):
    assert (B._evidence(group, prompt, B.default_brief()) is None) == ok


def test_an_edit_keeps_earlier_colour_translations():
    b = B.check(raw_brief(language="tr"))
    b["visuals"]["names"], b["visuals"]["names_src"] = {"Red": "kırmızı"}, {"Red": "red"}
    model = FakeModel({}, {"colour_Blue": "mavi"})
    planner._translate_defaults(b, model)
    assert b["visuals"]["names"]["Red"] == "kırmızı"  # kept, not asked again
    assert b["visuals"]["names"]["Blue"] == "mavi"
    asked_keys = [json.loads(u) for s, u in model.calls if s.startswith("Translate")][0]
    assert "colour_Red" not in asked_keys
