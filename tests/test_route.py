"""Edit routing (route.py) on the parts manifest (parts.py): the edit's type and analysis level
are decided in code from the creative's own metadata before anything is planned; a direct edit
needs no planner; a moment is placed on the timeline without a video model; an uploaded MP4 of one
of the tool's versions is recognised by its bytes. Runs on the small synthetic recording."""

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from cbj import brief as B
from cbj import parts as P
from cbj import route as R
from cbj.ad import Recording, build_ad
from cbj.compose import render

from test_ad import LENGTH, make_recording


@pytest.fixture(scope="module")
def version(tmp_path_factory):
    """One rendered version in a studio folder, with its record as version.json keeps it."""
    root = tmp_path_factory.mktemp("studio")
    rec_dir = make_recording(root / "recordings" / "r1")
    rec = Recording.load(rec_dir)
    ad = build_ad(rec, LENGTH, options={"texts": {"hook": "Beat this clock?"}})
    d = root / "c" / "v1" / "ad"
    render(ad, d, draft=True)
    v = {"n": 1, "id": "c", "prompt": "a near-fail", "edit": False, "from": None, "brief": B.check(B.default_brief()),
         "level": {"sha": hashlib.sha256((rec_dir / "level.json").read_bytes()).hexdigest(), "file": "c/v1/level.json"},
         "recording": {"dir": "recordings/r1"}, "ad_dir": "c/v1/ad", "video": "c/v1/ad/ad.mp4", "poster": "c/v1/ad/poster.png"}
    shutil.copy(rec_dir / "level.json", root / "c" / "v1" / "level.json")
    (root / "c" / "v1" / "version.json").write_text(json.dumps(v))
    return root, v


@pytest.fixture(scope="module")
def manifest(version):
    root, v = version
    return P.write(root / "c" / "v1", v, root)


def test_the_manifest_lists_parts_layers_moments_and_the_clock(version, manifest):
    root, v = version
    m = manifest
    assert (root / "c" / "v1" / "parts.json").is_file() and P.load(v, root)["parts"] == m["parts"]
    ids = [p["id"] for p in m["parts"]]
    assert "play" in ids and ids == json.loads((root / v["ad_dir"] / "ad.json").read_text())["order"]
    play = next(p for p in m["parts"] if p["id"] == "play")
    assert play["gameplay"] and play["from_s"] < play["to_s"] and play["field"] == "gameplay"
    layers = {L["id"]: L for L in m["layers"]}
    assert layers["hook"]["kind"] == "caption" and layers["hook"]["text"] == "Beat this clock?" and layers["hook"]["field"] == "concept.hook"
    assert layers["hook"]["from_s"] == 0 and layers["hook"]["to_s"] > 0 and layers["hook"]["route"] == "direct"
    assert layers["music"]["field"] == "audio.music" and layers["sound"]["field"] == "audio.sfx"
    assert layers["end_art"]["field"] == "assets[end_art]"
    first = next(x for x in m["moments"] if x.get("also") == "first_move")
    assert abs(first["at_s"] - (play["from_s"] + 8 / 30)) < 0.01  # the recorder's first touch (frame 8) on the ad's clock
    wrong = next(x for x in m["moments"] if x.get("also") == "wrong_move")
    assert wrong["kind"] == "mistake" and "wrong move" in wrong["what"]
    assert any(x["kind"] == "win" for x in m["moments"])
    # the clock: 7 s from the first touch, so 0:06 shows one second after it
    assert P.clock_at(m, 7) is not None
    assert abs(P.clock_at(m, 6) - (first["at_s"] + 1)) < 0.05
    assert P.clock_at(m, 99) is None
    assert "the clock shows" in P.text(m) and "caption hook" in P.text(m) and "first_move" in P.text(m)


@pytest.mark.parametrize("prompt, uploads, want", [
    ("Keep the gameplay and timing unchanged, but replace the opening caption with \"Can you solve this?\".", [],
     {"caption": "hook", "text": "Can you solve this?"}),
    ("Keep everything exactly the same, but make the hook say 'Beat this in 20 seconds'.", [], {"caption": "hook", "text": "Beat this in 20 seconds"}),
    ("Keep the video unchanged, but replace the background music with the attached track.", ["calm.wav"], {"music": "calm.wav"}),
    ("I like this creative. Keep everything exactly the same, but replace the logo with the attached image.", ["logo.png"],
     {"picture": "logo", "file": "logo.png"}),
    ("Keep everything exactly the same, but apply this ice texture to the blue block.", ["ice.png"], {"picture": "skin", "file": "ice.png", "block": "Blue"}),
    ("Turn the sound effects off, keep everything else.", [], {"sound": False}),
    ("Keep everything, but change the end card's title to 'Go!'.", [], {"caption": "end_title", "text": "Go!"}),
])
def test_level_0_edits_with_the_value_in_the_request_are_made_in_code(manifest, prompt, uploads, want):
    r = R.decide(prompt, manifest=manifest, uploads=uploads)
    assert r["edit_type"] == "direct" and r["analysis_level"] == 0 and r["direct_op"] == want, r
    assert r["requires_video_analysis"] is False and not r["requires_gameplay_regeneration"]
    assert "gameplay" in r["preserve"] and "level" in r["preserve"] and "timing" in r["preserve"]
    assert "no planner" in r["why"]


def test_a_known_layer_without_its_value_goes_to_the_planner_with_the_route(manifest):
    r = R.decide("Keep everything exactly the same, but change the background behind the board to light blue.", manifest=manifest)
    assert r["edit_type"] == "known_layers" and r["direct_op"] is None and r["allowed_groups"] == ["visuals.background"]
    t = R.text(r)
    assert t.startswith("ROUTE") and "never change the level" in t and "preserve:" in t
    r2 = R.decide("Same ad, but remove the 'Hurry!' caption.", manifest=manifest)  # a caption this ad does not have
    assert r2["targets"][0]["missing"] and "no" in r2["notes"][0] and r2["direct_op"] is None


def test_a_moment_is_placed_on_the_timeline_from_the_metadata(manifest):
    r = R.decide("Change the caption that appears when the timer reaches six seconds to 'Hurry up!'.", manifest=manifest)
    assert r["analysis_level"] == 1 and r["requires_video_analysis"] is False
    t = r["targets"][0]
    assert t["located"]["how"] == "clock" and "0:06" in t["located"]["note"]
    # one second after the first touch, the hook (0 - ~1.5 s of the ad) may or may not still be on screen:
    # either the caption on screen then is named, or the answer says none is and lists the captions
    assert (t.get("id") and t["op"] == {"caption": t["id"], "text": "Hurry up!"}) or ("no caption is on screen" in t["note"])
    r = R.decide("Change the caption shown at 0:02 to 'Now!'.", manifest=manifest)
    loc = r["targets"][0]["located"]
    assert (loc["at_s"], loc["how"], loc["note"]) == (2.0, "time", "at 2 s") and loc["on_screen"] == ["cap_mistake"]
    assert r["targets"][0]["op"] == {"caption": "cap_mistake", "text": "Now!"}
    r = R.decide("Change the caption that appears when the clock shows 0:55 to 'Last one!'.", manifest=manifest)
    assert r["targets"][0]["missing"] and "never shows 0:55" in r["targets"][0]["note"]
    r = R.decide("Change the caption that appears just before the win to 'Phew!'.", manifest=manifest)
    assert r["targets"][0]["located"]["how"] == "moment" and "win" in r["targets"][0]["located"]["note"]


def test_a_moment_the_metadata_cannot_place_may_use_the_multimodal_fallback(manifest):
    prompt = "Change the caption that appears while the green block is halfway to its door to 'Almost'."
    r = R.decide(prompt, manifest=manifest)
    assert r["analysis_level"] == 1 and r["targets"][0].get("unlocated")
    seen = []
    r2 = R.decide(prompt, manifest=manifest, locate=lambda clause: seen.append(clause) or 0.5)
    assert seen and r2["requires_video_analysis"] == "optional"
    t = r2["targets"][0]
    assert t["located"]["how"] == "vision" and t["located"]["at_s"] == 0.5 and t["id"] == "hook" and t["op"]["text"] == "Almost"
    r3 = R.decide(prompt, manifest=manifest, locate=lambda clause: (_ for _ in ()).throw(ValueError("no key")))
    assert any("could not place" in n for n in r3["notes"]) and r3["targets"][0].get("unlocated")


def test_gameplay_changes_are_retakes_and_locked_frames_a_conflict(manifest):
    r = R.decide("Same ad, but add a second mistake before the solve.", manifest=manifest)
    assert r["edit_type"] == "gameplay_edit" and r["requires_gameplay_regeneration"] and "gameplay" not in r["preserve"]
    assert "captions" in r["preserve"] and "the game films it again" in R.summary(r)
    r = R.decide("Change the level to a harder one but keep every frame of the video exactly the same.", manifest=manifest)
    assert r["edit_type"] == "conflict" and r["feasible"] is False
    r = R.decide("Same ad without the slow-motion replay.", manifest=manifest)
    assert r["edit_type"] == "known_layers" and r["targets"][0]["kind"] == "sequence" and not r["requires_gameplay_regeneration"]
    assert "sequence" in r["allowed_groups"] and "pacing.length" in r["allowed_groups"]


def test_new_creatives_and_reference_videos(manifest):
    r = R.decide("Create a difficult level with a near-fail.")
    assert r["intent"] == "new" and r["edit_type"] == "new_creative" and r["analysis_level"] == 0
    r = R.decide("Create a Color Block Jam version of this concept.", videos=["ref.mp4"])
    assert r["edit_type"] == "adapt_reference" and r["analysis_level"] == 2 and r["requires_video_analysis"] is True
    r = R.decide("Keep everything the same but change the hook to 'Go'.", videos=["other.mp4"], matched=False)
    assert r["analysis_level"] == 2 and any("not one of this tool's creatives" in n for n in r["notes"])
    r = R.decide("Make it follow the pacing of this reference.", manifest=manifest, videos=["ref.mp4"])
    assert r["analysis_level"] == 2 and r["requires_gameplay_regeneration"]


def test_verify_restores_play_changes_the_route_did_not_allow():
    cur = B.check(B.default_brief())
    b = B.check(B.default_brief())
    b["concept"]["hook"], b["level"]["difficulty"], b["gameplay"]["mistakes"] = "Go", "hard", 2
    b["changed"] = ["concept.hook", "level.difficulty", "gameplay.mistakes"]
    r = {"intent": "edit", "edit_type": "known_layers", "allowed_groups": ["concept.hook"], "requires_gameplay_regeneration": False, "notes": []}
    assert R.verify(b, r, cur) == ["level.difficulty", "gameplay.mistakes"]
    assert b["changed"] == ["concept.hook"] and b["level"]["difficulty"] == "any" and b["gameplay"]["mistakes"] is None
    assert any("stay as they are" in n for row in b["controls"] for n in row.get("engine", []))
    # an unrecognised clause: the planner's reading of the play is trusted and the route upgraded
    b2 = B.check(B.default_brief())
    b2["gameplay"]["mistakes"], b2["changed"] = 2, ["gameplay.mistakes"]
    r2 = {"intent": "edit", "edit_type": "planner", "allowed_groups": [], "requires_gameplay_regeneration": False, "notes": [],
          "preserve": ["gameplay", "captions"]}
    assert R.verify(b2, r2, cur) == [] and r2["edit_type"] == "gameplay_edit" and r2["preserve"] == ["captions"]


def test_the_route_check_reads_the_report(manifest):
    r = {"intent": "edit", "edit_type": "direct", "analysis_level": 0, "requires_gameplay_regeneration": False,
         "level_name": R.LEVEL_NAMES[0], "requires_video_analysis": False}
    ok = R.check(r, {"checklist": {"gameplay_render_reused": {"ok": True}}})
    assert ok["ok"] and "reused as routed" in ok["evidence"] and "no planner" in ok["evidence"]
    bad = R.check(r, {"checklist": {"gameplay_render_reused": {"ok": False}}})
    assert not bad["ok"] and "NOT reused" in bad["evidence"]
    assert R.check(None, {}) is None and R.check({"intent": "new"}, {}) is None


def test_an_uploaded_mp4_of_a_version_is_recognised_by_its_bytes(version, tmp_path):
    root, v = version
    copy = tmp_path / "base-creative_copy.mp4"
    shutil.copy(root / v["video"], copy)
    assert R.match_upload(copy, root) == {"creative_id": "c", "n": 1, "file": "c/v1/ad/ad.mp4"}
    other = tmp_path / "other.mp4"
    other.write_bytes(copy.read_bytes() + b"\x00")
    assert R.match_upload(other, root) is None


def test_clauses_never_split_inside_quotes():
    cl = R.clauses("Keep it, but replace the hook with \"Can you win? Try!\" and keep the rest.")
    assert any('"Can you win? Try!"' in c for c in cl) and len(cl) == 2  # split on 'but', never on the '?' in the quote
    assert R.quoted("change the end card's title to 'Go'") == ["Go"]


def test_the_plan_api_routes_a_direct_edit_without_the_planner(version, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from cbj import app as A
    from cbj import studio
    from test_app import wait
    root, v = version
    monkeypatch.setattr(studio, "STUDIO", root)
    A.JOBS.clear()
    monkeypatch.setattr(A.planner, "plan", lambda *a, **k: (_ for _ in ()).throw(AssertionError("the planner must not run")))
    client = TestClient(A.app)
    jid = client.post("/api/plan", json={"prompt": "Keep everything the same, but change the hook to 'Go!'.", "creative_id": "c"}).json()["job"]
    j = wait(client, jid)
    assert j["status"] == "done", j.get("error")
    b = j["result"]
    assert b["concept"]["hook"] == "Go!" and b["changed"] == ["concept.hook"] and b["planner"]["model"] is None
    assert b["planner"]["route"]["edit_type"] == "direct" and b["planner"]["direct"] == {"caption": "hook", "text": "Go!"}
    assert any("route:" in line["text"] for line in client.get(f"/api/jobs/{jid}").json()["lines"])
    m = client.get("/api/parts/c?base=1").json()
    assert m["version"] == 1 and any(L["id"] == "hook" for L in m["layers"])
    # the same edit through the planner: the route goes with the prompt and is checked afterwards
    seen = {}

    def fake_plan(prompt, uploads=None, sprites=None, current=None, available=None, route=None, **kw):
        seen["route"] = route
        b = json.loads(json.dumps(current))
        b["visuals"]["background"] = ["#ADD8E6"]
        b["level"]["difficulty"] = "hard"
        b["changed"] = ["visuals.background", "level.difficulty"]
        b["planner"] = {"model": "fake", "seconds": 0.0, "prompt": prompt, "edit": True, "restored": []}
        return b
    monkeypatch.setattr(A.planner, "plan", fake_plan)
    jid = client.post("/api/plan", json={"prompt": "Keep everything the same, but change the background behind the board to light blue.",
                                          "creative_id": "c"}).json()["job"]
    j = wait(client, jid)
    assert j["status"] == "done", j.get("error")
    assert seen["route"].startswith("ROUTE") and "the background behind the board" in seen["route"]
    b = j["result"]
    assert b["changed"] == ["visuals.background"] and b["level"]["difficulty"] == "any"
    assert b["planner"]["route"]["edit_type"] == "known_layers"


# ---------- 2026-10-18: "keep the same level" inside a retake clause ----------

def test_a_retake_that_keeps_the_level_locks_the_level():
    """'Make it 30 seconds instead of 45, keep the same level and play' is one clause (no 'but'), a
    game change; the kept level must still be preserved, and verify restores any level group the
    planner changed."""
    import json
    from cbj import brief as B
    from cbj import route
    r = route.decide("Make it 30 seconds instead of 45, keep the same level and play.", manifest={"parts": [], "duration_s": 45})
    assert r["intent"] == "edit" and r["requires_gameplay_regeneration"] and r.get("kept_level")
    assert "level" in r["preserve"]
    current = B.check(B.default_brief())
    current["level"]["shape"] = "ring"
    current["level"]["colours"] = ["Red", "Blue"]
    planned = json.loads(json.dumps(current))
    planned["level"]["shape"] = "open"
    planned["level"]["colours"] = ["Green", "Yellow", "Blue"]
    planned["pacing"]["length_s"] = 30.0
    planned["changed"] = ["pacing.length", "level.shape", "level.colours"]
    restored = route.verify(planned, r, current)
    assert set(restored) == {"level.shape", "level.colours"}
    assert planned["level"] == current["level"] and planned["changed"] == ["pacing.length"]
    r2 = route.decide("Keep everything, but make the level harder.", manifest={"parts": [], "duration_s": 30})
    assert r2["requires_gameplay_regeneration"] and not r2.get("kept_level")


def test_a_fresh_level_reading_needs_the_opening_clause_to_describe_one():
    from cbj import brief as B
    from cbj import planner
    current = B.check(B.default_brief())
    current["level"]["shape"] = "ring"
    for prompt in ("Make it 30 seconds instead of 45, keep the same level and play.",
                   "Make the ad shorter but keep the existing level."):
        b = json.loads(json.dumps(current)) if False else __import__("copy").deepcopy(current)
        b["changed"] = []
        planner._fresh_level(b, prompt, current)
        assert b["level"]["shape"] == "ring" and not any(a.startswith("The request describes a new level") for a in b.get("assumptions", []))
    b = __import__("copy").deepcopy(current)
    b["changed"] = []
    planner._fresh_level(b, "Create a medium level with six colored blocks.", current)  # no shape words: the ring is not carried over
    assert any(a.startswith("The request describes a new level") for a in b.get("assumptions", []))


def test_a_texture_on_the_cyan_block_is_a_direct_edit_with_the_slot_shown_cyan(manifest):
    """E4 (2026-10-19): the colour word resolves through colour_of (brief.slot_of_colour_word on the creative)."""
    colour_of = lambda w: {"cyan": "Green", "light blue": "Green", "blue": "Blue"}.get(w.lower())  # noqa: E731
    r = R.decide("Apply the attached ice texture to the cyan block. Everything else stays as it is.", manifest=manifest,
                 uploads=["ice.png"], colour_of=colour_of)
    assert r["direct_op"] == {"picture": "skin", "file": "ice.png", "block": "Green"}
    r2 = R.decide("Apply the attached ice texture to the cyan block.", manifest=manifest, uploads=["ice.png"])
    assert r2["direct_op"] is None and r2["targets"][0]["id"] == "skin"  # without the creative's colours: the planner
