"""The ad as data (ad.json) and the compositor, on a small synthetic recording, so the tests run
without Unity or the renders folder."""

import copy
import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from cbj import cli
from cbj.ad import (BAND, FIT, Recording, build_ad, check_ad, copy_problems, fill, layer_window, timeline,
                    to_output)
from cbj.compose import audio_events, cursor_track, render
from cbj.video import FrameWriter, read_frames

PROJ = Path(__file__).parent.parent
LEVEL = PROJ / "data/levels/gen/narrow_center_01.json"
W, H = 1080, 1920
N = 150  # frames in the synthetic recording (5 s)
DRAGS = ((8, 16, 14), (50, 62, -1), (80, 90, 88), (100, 112, 110))  # (start, end, exit) per beat


def make_recording(folder: Path, ending: str = "near_fail", shade: int = 0) -> Path:
    """A 150-frame recording shaped like `cbj scenario` output: four beats (solve, a blocked mistake at
    1.67 s, a solve, the final exit), a 7 s clock from the first touch, the clock stopping at frame
    112 and the win screen at 114."""
    folder.mkdir(parents=True, exist_ok=True)
    with FrameWriter(folder / "gameplay.mp4", (W, H), draft=True) as w:
        for i in range(N):
            f = np.empty((H, W, 3), np.uint8)
            f[:] = (222, 236, 255)  # the game's light background
            f[600:1500, 100:980] = (90 + shade, 100, 140)  # the board
            x = 200 + 4 * i
            f[900:1000, x:x + 100] = (40, 200, 60)  # a moving block
            w.write(f)
    first, stop, win = 8, 112, 114
    timer_s = 7
    frames = []
    for i in range(N):
        t = timer_s - max(0, min(i, stop) - first) / 30
        down = any(a <= i < b for a, b, _ in DRAGS)
        frames.append({"frame": i, "timer": t, "finger": down, "finger_x": 250.0 + 4 * i, "finger_y": 950.0,
                       "blocks": [250.0 + 4 * i, 950.0]})
    drags = []
    for k, (a, b, ex) in enumerate(DRAGS):
        drags.append({"index": k, "block": k, "start_frame": a, "exit_frame": ex, "end_frame": b,
                      "cells": [], "cell_frames": [], "result": "exit" if ex >= 0 else "placed"})
    beats = [
        {"kind": "solve", "block": 4, "note": "Y (yellow) leaves through its gate", "push_cells": 0},
        {"kind": "mistake", "block": 2, "note": "D (dark green) heads for its gate, but P (purple) is in the way",
         "push_cells": 0.3, "pickup_f": 3, "frames_per_cell": 4, "path": [[2, 6], [2, 5]]},
        {"kind": "solve", "block": 1, "note": "G (green) leaves through its gate", "push_cells": 0},
        {"kind": "solve", "block": 6, "note": "O (orange) leaves through its gate", "push_cells": 0},
    ]
    result = {"status": "cleared", "frames": N, "first_touch_frame": first, "clock_stopped_frame": stop,
              "win_frame": win if ending != "time_out" else -1, "fail_frame": win if ending == "time_out" else -1,
              "timer_end": timer_s - (stop - first) / 30, "drags": drags, "block_gone_frames": [16, -1, 90, 112]}
    play = {"level": "narrow_center_01", "ending": ending, "end_mode": "win", "timer_s": timer_s, "beats": beats,
            "measured": {"beat_frames": [[a, b] for a, b, _ in DRAGS]}}
    (folder / "result.json").write_text(json.dumps(result))
    (folder / "frames.json").write_text(json.dumps({"frames": frames}))
    (folder / "play.json").write_text(json.dumps(play))
    shutil.copy(LEVEL, folder / "level.json")
    return folder


@pytest.fixture(scope="module")
def rec_dir(tmp_path_factory):
    return make_recording(tmp_path_factory.mktemp("rec") / "nf")


@pytest.fixture(scope="module")
def rec(rec_dir):
    return Recording.load(rec_dir)


@pytest.fixture(scope="module")
def ad(rec):
    return build_ad(rec, length_s=10)


@pytest.fixture(scope="module")
def rendered(ad, tmp_path_factory):
    out = tmp_path_factory.mktemp("ad") / "a"
    return out, render(copy.deepcopy(ad), out, draft=True)


# ---------- events, anchors, time map ----------

def test_recording_events(rec):
    assert rec.event("beat.1.start") == [50]
    assert rec.event("win") == [114] and rec.event("clock_stop") == [112]
    assert rec.event("drag.*.exit") == [14, 88, 110]
    assert rec.event("clock<=5") == [68]  # 7 s on the clock from frame 8, two seconds later
    assert rec.event("clock_second") == [9, 39, 69, 99]  # 7 -> 6 just after the touch, then each second
    assert rec.facts(beat=1)["colour"] == "dark green"  # from the block, never typed by hand
    assert rec.facts()["clock_left"] == "00:03"


def test_a_replay_maps_events_to_half_speed():
    seg = {"kind": "clip", "from": 40, "to": 60, "speed": 0.5}
    assert to_output(seg, 100, 40) == 100 and to_output(seg, 100, 50) == 120 and to_output(seg, 100, 60) is None


def test_build_ad_lands_exactly_on_the_length(ad, rec):
    tl = timeline(ad)
    assert max(e for _, e in tl.values()) == 300
    assert ad["order"][0] == "play" and ad["order"][-1] == "end"
    assert ad["segments"]["play"]["fit"] == FIT
    assert tl["end"][1] - tl["end"][0] >= 90  # at least 3 s of end card
    assert layer_window(ad, {"main": rec}, "cap_mistake")[0] == 50  # anchored to the mistake beat


def test_texts_use_facts_only():
    assert fill("Phew! {clock_left} left", {"clock_left": "00:01"}) == "Phew! 00:01 left"
    with pytest.raises(ValueError, match="unknown fact"):
        fill("{level_name}", {})
    with pytest.raises(ValueError, match="needs the layer's beat"):
        fill("I can't reach {colour}!", {"clock_left": "00:01"})


@pytest.mark.parametrize("text,bad", [("Only 1% can solve this", True), ("Your IQ is 140", True),
                                      ("1 in 100 can do it", True), ("only 5 people", True),
                                      ("Can you beat the clock?", False), ("Phew! 00:01 left", False)])
def test_copy_guard(text, bad):
    assert bool(copy_problems(text)) == bad


def test_check_ad_names_the_problem(ad):
    bad = copy.deepcopy(ad)
    bad["order"].append("nope")
    with pytest.raises(ValueError, match="'nope'"):
        check_ad(bad)
    bad = copy.deepcopy(ad)
    bad["segments"]["play"]["to"] = 0
    with pytest.raises(ValueError, match="from < to"):
        check_ad(bad)


# ---------- rendering ----------

def test_render_writes_the_ad_and_its_proof(rendered):
    out, r = rendered
    assert r["qa"]["failures"] == []
    assert r["frames"] == 300 and len(r["frame_sha256"]) == 300
    assert (out / "ad.mp4").is_file() and (out / "poster.png").is_file() and (out / "compose.json").is_file()
    assert r["layers"]["hook"]["frames"][0] == 0  # the hook is on the poster frame
    box = r["layers"]["hook"]["box"]
    assert BAND["y0"] <= box[1] and box[3] <= BAND["y1"]  # in the text band, clear of the HUD
    assert r["sources"]["main"]["sha256"]


def test_same_ad_gives_identical_frames_and_bytes(ad, rendered, tmp_path):
    _, first = rendered
    again = render(copy.deepcopy(ad), tmp_path / "b", draft=True)
    assert again["frame_sha256"] == first["frame_sha256"]
    assert again["wav_sha256"] == first["wav_sha256"]
    assert again["mp4_sha256"] == first["mp4_sha256"]  # bit-exact encode


def test_editing_one_text_changes_only_its_frames(ad, rendered, tmp_path):
    """Case p.7: change one thing, keep everything else. Only the hook's frames may change."""
    _, first = rendered
    edited = copy.deepcopy(ad)
    edited["layers"]["hook"]["text"] = "Beat this clock?"
    r = render(edited, tmp_path / "c", draft=True)
    f0, f1 = first["layers"]["hook"]["frames"]
    changed = [i for i, (a, b) in enumerate(zip(first["frame_sha256"], r["frame_sha256"])) if a != b]
    assert changed and all(f0 <= i < f1 for i in changed)
    assert r["sources"] == first["sources"] and r["timeline"] == first["timeline"]
    assert r["wav_sha256"] == first["wav_sha256"]  # the sound track is untouched
    for lid in first["layers"]:
        if lid != "hook":
            assert r["layers"][lid] == first["layers"][lid]


def test_a_forbidden_claim_fails_the_render(ad, tmp_path):
    bad = copy.deepcopy(ad)
    bad["layers"]["hook"]["text"] = "Only 1% can solve this!"
    r = render(bad, tmp_path / "d", draft=True)
    assert any("odds" in f or "'only N'" in f or "percentage" in f for f in r["qa"]["failures"])
    assert r["rendered"] is False and not (tmp_path / "d" / "ad.mp4").exists()  # stopped before drawing


def test_two_recordings_join_into_one_ad(tmp_path):
    """The segment list behind a 60 s ad: clip A, a card, clip B."""
    a = Recording.load(make_recording(tmp_path / "a"))
    b_dir = make_recording(tmp_path / "b", shade=60)
    ad = build_ad(a, length_s=10)
    ad["sources"]["second"] = {"recording": str(b_dir), "sha256": Recording.load(b_dir).sha()}
    ad["segments"]["bridge"] = {"kind": "card", "frames": 30, "background": "StartBACKGROUND.png"}
    ad["segments"]["play2"] = {"kind": "clip", "src": "second", "from": 0, "to": 60, "speed": 1, "fit": FIT}
    ad["order"] = ["play", "bridge", "play2", "end"]
    ad["length_s"] = None
    ad["layers"] = {k: v for k, v in ad["layers"].items() if k not in ("replay_tag", "cap_result")}
    ad["layers"]["cursor"]["segments"] = ["play", "play2"]
    ad["audio"]["events"].pop("rewind", None)  # the replay is not in this ad
    r = render(ad, tmp_path / "joined", draft=True)
    assert r["qa"]["failures"] == []
    assert [r["timeline"][s]["frames"] for s in ("play", "bridge", "play2")] == [[0, 114], [114, 144], [144, 204]]
    assert set(r["sources"]) == {"main", "second"}


def test_the_round_trip_keeps_colours(rec_dir, tmp_path):
    a = [f.copy() for f in read_frames(rec_dir / "gameplay.mp4", (W, H), 10, 5)]
    with FrameWriter(tmp_path / "rt.mp4", (W, H)) as w:
        for f in a:
            w.write(f)
    b = [f.copy() for f in read_frames(tmp_path / "rt.mp4", (W, H), 0, 5)]
    shift = np.mean([(y.astype(int) - x.astype(int)).mean() for x, y in zip(a, b)])
    assert abs(shift) < 0.5


# ---------- cursor and sound ----------

def test_cursor_shows_only_after_the_first_touch_and_ripples_on_release(rec):
    tr = cursor_track(rec)
    assert all(t["alpha"] == 0 and not t["released"] for t in tr[:8])  # nothing on the poster
    assert tr[8]["down"] and tr[8]["since"] == 0
    assert tr[16]["released"] and tr[16]["since"] == 0  # the lift after drag 1
    assert tr[30]["alpha"] == 0.7 and (tr[30]["x"], tr[30]["y"]) == (rec.frames[15]["finger_x"], 950.0)  # waits
    assert (tr[48]["x"], tr[48]["y"]) == (rec.frames[50]["finger_x"], rec.frames[50]["finger_y"])  # arrived early


def test_sound_events_follow_the_gameplay(ad, rec):
    events = audio_events(ad, {"main": rec}, timeline(ad), 300)
    pops = [e for e in events if e["name"] == "pops"]
    play_pops = [e for e in pops if e["t"] < 114 / 30]
    assert [e.get("pitch", 1.0) for e in play_pops] == [1.0, 1.12, 1.26]  # rising over the last three exits
    assert any(e["name"] == "win" for e in events)
    ticks = [e for e in events if e["name"] == "ticks"]
    assert [e.get("pitch", 1.0) for e in ticks[:2]] == [1.0, 0.84]  # tick, tock


def test_an_anchor_to_a_segment_that_does_not_play_is_a_qa_failure(ad, tmp_path):
    bad = copy.deepcopy(ad)
    bad["order"] = [s for s in bad["order"] if s != "replay"]
    r = render(bad, tmp_path / "f", draft=True)
    assert r["rendered"] is False and any("not in the order" in f for f in r["qa"]["failures"])


def test_cli_ad_makes_a_finished_ad(rec_dir, tmp_path, capsys):
    assert cli.main(["ad", str(rec_dir), "--length", "10", "--draft", "-o", str(tmp_path / "e")]) == 0
    out = capsys.readouterr().out
    assert "Ad:" in out and "Proof:" in out and "QA FAILED" not in out
