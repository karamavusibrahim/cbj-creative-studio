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
from cbj.compose import Prepared, anim_state, audio_events, cascade_pitch, cursor_track, diff, render
from cbj.video import FrameWriter, read_frames

PROJ = Path(__file__).parent.parent
LEVEL = PROJ / "data/levels/gen/narrow_center_01.json"
W, H = 1080, 1920
N = 190  # frames in the synthetic recording (6.3 s)
DRAGS = ((8, 16, 14), (60, 72, -1), (90, 100, 98), (112, 124, 122))  # (start, end, exit) per beat
LENGTH = 11  # seconds of the test ad


def make_recording(folder: Path, ending: str = "near_fail", shade: int = 0) -> Path:
    """A 190-frame recording shaped like `cbj scenario` output: four beats (solve, a blocked mistake at
    2.0 s, a solve, the final exit), a 7 s clock from the first touch, the clock stopping at frame
    124 and the win screen at 126."""
    folder.mkdir(parents=True, exist_ok=True)
    with FrameWriter(folder / "gameplay.mp4", (W, H), draft=True) as w:
        for i in range(N):
            f = np.empty((H, W, 3), np.uint8)
            f[:] = (222, 236, 255)  # the game's light background
            f[600:1500, 100:980] = (90 + shade, 100, 140)  # the board
            x = 200 + 4 * i
            f[900:1000, x:x + 100] = (40, 200, 60)  # a moving block
            w.write(f)
    first, stop, win = 8, 124, 126
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
              "timer_end": timer_s - (stop - first) / 30, "drags": drags, "block_gone_frames": [16, -1, 100, 124]}
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
    return build_ad(rec, length_s=LENGTH)


@pytest.fixture(scope="module")
def rendered(rec_dir, tmp_path_factory):
    """The default ad, made through the command line as a user would."""
    out = tmp_path_factory.mktemp("ad") / "a"
    assert cli.main(["ad", str(rec_dir), "--length", str(LENGTH), "--draft", "-o", str(out)]) == 0
    return out, json.loads((out / "compose.json").read_text())


@pytest.fixture(scope="module")
def edited(rendered, tmp_path_factory):
    """The same ad with one change: the hook's text."""
    out_a, _ = rendered
    ad = json.loads((out_a / "ad.json").read_text())
    ad["layers"]["hook"]["text"] = "Beat this clock?"
    out = tmp_path_factory.mktemp("ad") / "b"
    return out, render(ad, out, draft=True)


# ---------- events, anchors, time map ----------

def test_recording_events(rec):
    assert rec.event("beat.1.start") == [60]
    assert rec.event("win") == [126] and rec.event("clock_stop") == [124]
    assert rec.event("drag.*.exit") == [14, 98, 122]
    assert rec.event("clock<=5") == [68]  # 7 s on the clock from frame 8, two seconds later
    assert rec.event("clock_second") == [9, 39, 69, 99]  # 7 -> 6 just after the touch, then each second
    assert rec.facts(beat=1)["colour"] == "dark\u00a0green"  # from the block; a non-breaking space keeps it whole
    assert rec.facts()["clock_left"] == "00:03"


def test_a_replay_maps_events_to_half_speed():
    seg = {"kind": "clip", "from": 40, "to": 60, "speed": 0.5}
    assert to_output(seg, 100, 40) == 100 and to_output(seg, 100, 50) == 120 and to_output(seg, 100, 60) is None


def test_build_ad_lands_exactly_on_the_length(ad, rec):
    tl = timeline(ad)
    assert max(e for _, e in tl.values()) == LENGTH * 30
    assert "replay" in tl
    assert ad["order"][0] == "play" and ad["order"][-1] == "end"
    assert ad["segments"]["play"]["fit"] == FIT
    assert tl["end"][1] - tl["end"][0] >= 90  # at least 3 s of end card
    assert layer_window(ad, {"main": rec}, "cap_mistake")[0] == 60  # anchored to the mistake beat
    assert ad["layers"]["cap_mistake"]["start"] == {"seg": "play", "event": "beat.1.start"}


def test_texts_use_facts_only():
    assert fill("Phew! {clock_left} left", {"clock_left": "00:01"}) == "Phew! 00:01 left"
    with pytest.raises(ValueError, match="unknown fact"):
        fill("{level_name}", {})
    with pytest.raises(ValueError, match="needs the layer's beat"):
        fill("I can't reach {colour}!", {"clock_left": "00:01"})


@pytest.mark.parametrize("text,bad", [("Only 1% can solve this", True), ("Your IQ is 140", True),
                                      ("1 in 100 can do it", True), ("only 5 people", True),
                                      ("Only 3 players can solve it", True), ("99 percent fail", True),
                                      ("Can you beat the clock?", False), ("Phew! 00:01 left", False),
                                      ("Only 00:01 to spare!", False), ("Only one block left", False)])
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
    assert r["frames"] == LENGTH * 30 and len(r["frame_sha256"]) == LENGTH * 30
    assert (out / "ad.mp4").is_file() and (out / "poster.png").is_file() and (out / "compose.json").is_file()
    assert r["layers"]["hook"]["frames"][0] == 0  # the hook is on the poster frame
    box = r["layers"]["hook"]["box"]
    assert BAND["y0"] <= box[1] and box[3] <= BAND["y1"]  # in the text band, clear of the HUD
    assert r["sources"]["main"]["sha256"]


def test_same_ad_gives_identical_frames_and_bytes(rendered, tmp_path):
    out_a, first = rendered
    again = render(json.loads((out_a / "ad.json").read_text()), tmp_path / "b", draft=True)
    assert again["frame_sha256"] == first["frame_sha256"]
    assert again["wav_sha256"] == first["wav_sha256"]
    assert again["mp4_sha256"] == first["mp4_sha256"]  # bit-exact encode


def test_editing_one_text_changes_only_its_frames(rendered, edited):
    """Case p.7: change one thing, keep everything else. Only the hook's frames may change."""
    _, first = rendered
    _, r = edited
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
    ad = build_ad(a, length_s=LENGTH)
    ad["sources"]["second"] = {"recording": str(b_dir), "sha256": Recording.load(b_dir).sha()}
    ad["segments"]["bridge"] = {"kind": "card", "frames": 30, "background": "StartBACKGROUND.png"}
    ad["segments"]["play2"] = {"kind": "clip", "src": "second", "from": 0, "to": 60, "speed": 1, "fit": FIT}
    ad["order"] = ["play", "bridge", "play2", "end"]
    ad["length_s"] = None
    ad["layers"] = {k: v for k, v in ad["layers"].items() if k not in ("replay_tag", "cap_result")}
    ad["layers"]["cursor"]["segments"] = ["play", "play2"]
    ad["locked"] = [p for p in ad["locked"] if p not in ("sources", "segments", "layers/cursor")]  # on purpose
    ad["audio"]["events"].pop("rewind", None)  # the replay is not in this ad
    r = render(ad, tmp_path / "joined", draft=True)
    assert r["qa"]["failures"] == []
    assert [r["timeline"][s]["frames"] for s in ("play", "bridge", "play2")] == [[0, 126], [126, 156], [156, 216]]
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
    assert (tr[58]["x"], tr[58]["y"]) == (rec.frames[60]["finger_x"], rec.frames[60]["finger_y"])  # arrived early


def test_sound_events_follow_the_gameplay(ad, rec):
    events = audio_events(ad, {"main": rec}, timeline(ad), LENGTH * 30)
    pops = [e for e in events if e["name"] == "pops"]
    play_pops = [e for e in pops if e["t"] < 126 / 30]
    assert [e.get("pitch", 1.0) for e in play_pops] == [1.0, 1.12, 1.26]  # rising over the last three exits
    assert any(e["name"] == "win" for e in events)
    ticks = [e for e in events if e["name"] == "ticks"]
    assert [e.get("pitch", 1.0) for e in ticks[:2]] == [1.0, 0.84]  # tick, tock


def test_an_anchor_to_a_segment_that_does_not_play_is_a_qa_failure(ad, tmp_path):
    bad = copy.deepcopy(ad)
    bad["order"] = [s for s in bad["order"] if s != "replay"]
    r = render(bad, tmp_path / "f", draft=True)
    assert r["rendered"] is False and any("not in the order" in f for f in r["qa"]["failures"])




# ---------- the fixes from the Fable 5.1 check ----------

def test_ad_diff_proves_the_edit_and_the_mp4_stays_local(rendered, edited, capsys):
    (out_a, first), (out_b, _) = rendered, edited
    d = diff(out_a, out_b)
    f0, f1 = first["layers"]["hook"]["frames"]
    assert d["layers_changed"] == ["hook"] and d["same_sound"] and d["same_sources"] and not d["locked_changed"]
    assert all(f0 <= a and b < f1 for a, b in d["changed_frames"])
    assert d["contained"] and d["measured_box"]  # every changed pixel is inside the hook's box
    # The delivered video, not just the composited frames: decoded, every frame outside the hook's
    # window is identical, because each layer boundary starts a new GOP and the quantizer is fixed.
    a = read_frames(out_a / "ad.mp4", (W, H))
    b = read_frames(out_b / "ad.mp4", (W, H))
    outside = [i for i, (x, y) in enumerate(zip(a, b)) if not f0 <= i < f1 and not np.array_equal(x, y)]
    assert outside == []
    assert cli.main(["ad-diff", str(out_a), str(out_b)]) == 0
    assert "every change is inside them" in capsys.readouterr().out


def test_the_end_card_holds_to_the_last_frame():
    layer = {"anim": "pop"}
    assert anim_state(layer, 299, 200, 300, total=300) == (1.0, 1.0)  # no fade on the ad's last frames
    assert anim_state(layer, 299, 200, 300, total=400)[1] < 1  # a layer that ends earlier still fades


def test_a_locked_part_cannot_change_unless_unlocked(ad):
    moved = copy.deepcopy(ad)
    moved["segments"]["play"]["fit"]["y"] = 200
    assert any("locked part 'segments'" in f for f in Prepared(moved, draft=True).qa["failures"])
    moved["locked"].remove("segments")  # changing the gameplay framing on purpose
    assert not any("locked" in f for f in Prepared(moved, draft=True).qa["failures"])


def test_qa_catches_a_window_outside_its_segment_and_text_too_short_to_read(ad):
    bad = copy.deepcopy(ad)
    bad["layers"]["cap_result"]["start"] = {"seg": "result", "at": 10}
    assert any("cap_result" in f and "outside" in f or "not inside the ad" in f for f in Prepared(bad, True).qa["failures"])
    bad = copy.deepcopy(ad)
    bad["layers"]["cap_mistake"]["text"] = "This caption has far too many words to read in time"
    assert any("cap_mistake" in f and "need" in f for f in Prepared(bad, True).qa["failures"])


def test_a_segment_needs_a_fit(ad):
    bad = copy.deepcopy(ad)
    del bad["segments"]["play"]["fit"]
    with pytest.raises(ValueError, match="needs a fit"):
        check_ad(bad)


def test_end_card_facts_come_from_the_recording(rec):
    f = rec.facts()
    assert f["blocks_left"] == "1" and f["blocks_left_phrase"] == "one\u00a0block"  # one block never left
    assert fill("Out of time with {blocks_left_phrase} left!", f) == "Out of time with one\u00a0block left!"


def test_cascade_pitch_rises_to_the_last_exit():
    assert [cascade_pitch(i, 5) for i in range(5)] == [1.0, 1.0, 1.0, 1.12, 1.26]
    assert [cascade_pitch(i, 2) for i in range(2)] == [1.12, 1.26]
    assert cascade_pitch(0, 1) == 1.26


def test_ticks_are_not_repeated_in_slow_motion(ad, rec):
    tl = timeline(ad)
    r0, r1 = tl["replay"]
    events = audio_events(ad, {"main": rec}, tl, LENGTH * 30)
    assert not [e for e in events if e["name"] == "ticks" and r0 / 30 <= e["t"] < r1 / 30]
    assert [e for e in events if e["name"] == "pops" and r0 / 30 <= e["t"] < r1 / 30]  # pops do replay


def test_an_early_mistake_keeps_its_caption(tmp_path):
    folder = make_recording(tmp_path / "early")
    play = json.loads((folder / "play.json").read_text())
    play["measured"]["beat_frames"][1] = [20, 30]  # the mistake at 0.67 s, inside the hook
    (folder / "play.json").write_text(json.dumps(play))
    ad = build_ad(Recording.load(folder), length_s=LENGTH)
    assert "cap_mistake" in ad["layers"]  # moved after the hook, not dropped
    st = ad["layers"]["cap_mistake"]["start"]
    assert st["event"] == "beat.1.start" and st["offset"] > 0  # still anchored to the mistake
    recs = {"main": Recording.load(folder)}
    assert layer_window(ad, recs, "hook")[1] / 30 >= 1.9  # the hook stays long enough to read


def test_a_short_recording_is_not_padded_with_a_huge_end_card(rec):
    with pytest.raises(ValueError, match="too short for a 20 s ad"):
        build_ad(rec, length_s=20)
    ad = build_ad(rec, length_s=20, allow_long_card=True)
    assert timeline(ad)["end"][1] - timeline(ad)["end"][0] > 8 * 30


def test_a_render_that_fails_qa_is_not_left_looking_finished(ad, tmp_path):
    bad = copy.deepcopy(ad)
    bad["layers"]["end_title"]["pos"] = [1000, 520]  # pushed into the platform's right-hand buttons
    r = render(bad, tmp_path / "g", draft=True)
    assert any("end_title" in f and "safe area" in f for f in r["qa"]["failures"])
    assert (tmp_path / "g" / "ad.FAILED.mp4").exists() and not (tmp_path / "g" / "ad.mp4").exists()
