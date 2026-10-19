"""What every workflow does the same way (workflows/__init__.py, "Common to all four", 2026-10-19): the request
translated once, the best version kept, a repeated miss as the limit, the values the request states kept, a fixed
board's pace said at plan time in both directions."""
import copy
import json

import pytest

from cbj import brief as B
from cbj import studio
from cbj.workflows import create, edit, guided, image_guided


def _brief(**over):
    b = B.check(B.default_brief())
    b["planner"] = {"model": "fake", "seconds": 1}
    b["changed"], b["needs"], b["assumptions"] = [], [], []
    for k, v in over.items():
        a, _, c = k.partition(".")
        if c:
            b[a][c] = v
        else:
            b[a] = v
    return b


def test_create_plan_translates_once_and_says_the_time_out_limit(monkeypatch):
    seen = {}
    monkeypatch.setattr(image_guided, "english_prompt", lambda p, client=None, log=None: "The clock runs out with two blocks left, 30 seconds." if "saniye" in p else p)

    def fake_plan(prompt, **kw):
        seen["prompt"] = prompt
        return _brief(**{"gameplay.ending": "time_out"})
    monkeypatch.setattr(create.planner, "plan", fake_plan)
    monkeypatch.setattr(studio, "uploads", lambda: {})
    monkeypatch.setattr(studio, "videos", lambda: {})
    b = create.plan(studio.Log(), "Saat iki blok kala bitsin, 30 saniye.", [])
    assert seen["prompt"].startswith("The clock runs out") and b["planner"]["prompt_english"] == seen["prompt"]
    assert b["planner"]["prompt_original"].startswith("Saat")
    row = next(r for r in b["controls"] if r["control"] == "gameplay")
    assert "ends with exactly one block" in (row.get("why") or "") and row["status"] == "adjusted"
    # an English request: nothing recorded, nothing adjusted
    b2 = create.plan(studio.Log(), "An easy level, a clean win.", [])
    assert "prompt_english" not in b2["planner"]


def test_edit_plan_translates_before_the_route(tmp_path, monkeypatch):
    monkeypatch.setattr(studio, "STUDIO", tmp_path / "studio")
    cid = "1019-160000-an-ad"
    d = tmp_path / "studio" / cid / "v1"
    d.mkdir(parents=True)
    base = _brief()
    (d / "version.json").write_text(json.dumps({"n": 1, "id": cid, "prompt": "An ad.", "brief": base, "workflow": "create", "length_s": 30.0,
                                                "created": "2026-10-19 12:00:00", "edit": False, "level": {"file": f"{cid}/v1/level.json", "why": "x", "sha": "s"},
                                                "recording": {"dir": "recordings/x", "reused": False}, "checks": [], "video": f"{cid}/v1/ad/ad.mp4", "ad_dir": f"{cid}/v1/ad"}))
    (d / "level.json").write_text(json.dumps({"GridBlockDatas": [{"blockColor": 0}]}))
    monkeypatch.setattr(image_guided, "english_prompt", lambda p, client=None, log=None: 'Change the hook to "Beat it!"' if "kancayı" in p.lower() else p)
    seen = {}

    def fake_plan(prompt, **kw):
        seen["prompt"] = prompt
        b = copy.deepcopy(base)
        b["concept"]["hook"] = "Beat it!"
        b["changed"] = ["concept.hook"]
        b["planner"] = {"model": "fake", "seconds": 1, "restored": []}
        return b
    monkeypatch.setattr(edit.planner, "plan", fake_plan)
    monkeypatch.setattr(studio, "uploads", lambda: {})
    monkeypatch.setattr(studio, "videos", lambda: {})
    b = edit.plan(studio.Log(), 'Kancayı "Beat it!" yap.', cid, 1, [])
    assert b["planner"]["prompt_english"] == 'Change the hook to "Beat it!"' and b["planner"]["prompt_original"].startswith("Kancayı")
    # the route read the translation (the hook is its target; without a parts manifest here the planner gets the route),
    # and the planner read the translation too
    rt = b["planner"]["route"]
    assert rt["edit_type"] == "known_layers" and rt["targets"][0]["id"] == "hook" and seen["prompt"] == 'Change the hook to "Beat it!"'


def test_create_keeps_the_best_version_and_stops_on_a_repeated_miss(monkeypatch):
    miss = lambda n: {"check": "Asked: length", "status": "failed", "detail": f"the ad is {n} s (asked: 30)", "from": "prompt", "where": "play"}  # noqa: E731
    v1 = {"id": "c", "n": 1, "brief": _brief(), "checks": [miss(36)], "review": {"overall": "fix"}}
    v2 = {"id": "c", "n": 2, "brief": _brief(), "checks": [], "review": {"overall": "ship"}, "revision": {"status": "made"}}
    v3 = {"id": "c", "n": 3, "brief": _brief(), "checks": [miss(36), {"check": "Asked: ending", "status": "failed", "detail": "x", "from": "prompt"}],
          "review": {"overall": "fix"}, "revision": {"status": "made"}}
    monkeypatch.setattr(studio, "make", lambda *a, **k: copy.deepcopy(v1))
    monkeypatch.setattr(studio, "uploads", lambda: {})
    monkeypatch.setattr(studio, "sprite_names", lambda: set())
    monkeypatch.setattr(guided, "save_record", lambda v: None)
    rounds = iter([copy.deepcopy(v2), copy.deepcopy(v3)])
    monkeypatch.setattr(create, "revise_once", lambda log, p, v, r: next(rounds))
    # v2 met everything: the loop stops there and v2 is final
    out = create.make(studio.Log(), "an ad", _brief(), review_on=False, revise=True)
    assert out["n"] == 2
    # the same miss twice with the same measure: the limit, said; v1 (fewer misses than v3) is final
    rounds = iter([copy.deepcopy(dict(v3, n=2, checks=[miss(36)])), copy.deepcopy(dict(v3, n=3, checks=[miss(36)]))])
    monkeypatch.setattr(create, "revise_once", lambda log, p, v, r: next(rounds))
    log = studio.Log()
    out = create.make(log, "an ad", _brief(), review_on=False, revise=True)
    assert any("missed twice with the same measure" in ln["text"] for ln in log.lines)
    # the loop stopped after the second miss: two versions made, the later of the tie is final, the limit noted on both
    assert out["n"] == 2 and out["final"]["of"] == [1, 2] and out.get("limit_note", "").startswith("Asked: length")


def test_a_fixed_boards_pace_is_said_in_both_directions():
    from cbj import videoref as V
    level = {"gridWidth": 4, "gridHeight": 4, "timerCount": 30, "inactiveCells": [],
             "GridBlockDatas": [{"gridPosition": {"x": 0, "y": 0}, "blockColor": 0, "shapeOffsets": [{"x": 0, "y": 0}]},
                                {"gridPosition": {"x": 3, "y": 3}, "blockColor": 2, "shapeOffsets": [{"x": 0, "y": 0}]}],
             "ExitDatas": [{"gridPosition": {"x": 0, "y": 0}, "requiredColor": 0, "direction": 0, "shapeOffsets": [{"x": 0, "y": 0}]},
                           {"gridPosition": {"x": 3, "y": 3}, "requiredColor": 2, "direction": 1, "shapeOffsets": [{"x": 0, "y": 0}]}]}
    b = _brief(**{"pacing.length_s": 45.0, "pacing.tempo": "normal", "gameplay.ending": "victory"})
    prov = {"board": {"level": level, "verify": {"solve": "solved in 2 drags"}}}
    line = V.copied_board_pace(b, "a 45 second ad", set(), prov, what="the picture's board")
    assert line and line.startswith("the picture's board (2 blocks, 2 drags) gives about") and "goes to the held result" in line
    assert prov["play_short"]["moves"] == 2 and b["pacing"]["length_s"] == 45.0
    # a stated length is the user's choice: nothing said when the request fixes it
    prov2 = {"board": {"level": level, "verify": {"solve": "solved in 2 drags"}}}
    assert V.copied_board_pace(_brief(**{"pacing.length_s": 45.0}), "exactly 45 seconds", {"length"}, prov2) is None
    # the overrun direction keeps its words, with the caller's name for the board
    big = {**level, "GridBlockDatas": level["GridBlockDatas"] * 1}
    b3 = _brief(**{"pacing.length_s": 30.0, "pacing.tempo": "calm"})
    prov3 = {"board": {"level": big, "verify": {"solve": "solved in 60 drags"}}}
    line3 = V.copied_board_pace(b3, "30 seconds", {"tempo"}, prov3, what="the picture's board")
    assert line3 and "cannot be shortened" in line3 and line3.startswith("the picture's board") and prov3["play_overrun"]["moves"] == 60
