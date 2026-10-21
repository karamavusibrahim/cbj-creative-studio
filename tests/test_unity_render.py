"""Recordings in the real game. Opt-in, because each one starts the Unity player:

    uv run cbj build-player
    uv run cbj build-player --stock     # optional: the game as shipped, for the before/after tests
    CBJ_UNITY=1 uv run pytest tests/test_unity_render.py
"""

import copy
import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from cbj.describe import script_to_drags
from cbj.level import load_level
from cbj.render import (PLAYER_APP, PLAYER_STOCK, Camera, check_render, compare_recordings, make_job, player_binary,
                        run_player)

PROJ = Path(__file__).parent.parent

pytestmark = pytest.mark.skipif(
    not os.environ.get("CBJ_UNITY") or not PLAYER_APP.is_dir(),
    reason="set CBJ_UNITY=1 and run `cbj build-player` first",
)


def job_for(n: str, out: Path, **kw):
    path = PROJ / f"data/levels/Level_{n}.json"
    level = load_level(path)
    drags = script_to_drags(json.loads((PROJ / f"data/solutions/Level_{n}.moves.json").read_text()))
    return make_job(level, path, drags, out, **kw)


def run_raw(job: dict, out: Path) -> dict:
    """Run a job without make_job's rule check, to test the runner's own checks."""
    out.mkdir(parents=True, exist_ok=True)
    job = copy.deepcopy(job)
    job["out_dir"] = str(out.resolve())
    (out / "job.json").write_text(json.dumps(job))
    subprocess.run([str(player_binary()), "-cbjJob", str((out / "job.json").resolve()),
                    "-screen-fullscreen", "0", "-screen-width", "270", "-screen-height", "480",
                    "-logFile", str(out / "player.log")], timeout=300, capture_output=True)
    return check_render(out)


@pytest.mark.parametrize("n", ["01", "02", "03", "04", "05", "06"])
def test_solver_script_clears_the_level_in_the_game(tmp_path, n):
    r = run_player(job_for(n, tmp_path / "out"))
    assert r["problems"] == [], r["problems"]
    assert r["status"] == "cleared"
    assert all(d["result"] in ("exit", "placed") for d in r["drags"])


def test_same_job_gives_the_same_game_and_near_identical_pixels(tmp_path):
    # The game state repeats exactly. Pixels repeat in nearly every frame; a few frames per
    # run differ by a few pixels below the game (the graphics driver), so they are held to PSNR.
    runs = [run_player(job_for("06", tmp_path / k, size=(540, 960))) for k in "ab"]
    assert all(r["problems"] == [] for r in runs)
    c = compare_recordings(tmp_path / "a", tmp_path / "b")
    n = c["frames"][0]
    assert c["state_equal"], c
    assert c["identical_frames"] >= 0.97 * n, c
    assert c["min_psnr_db"] >= 40, c


def test_runner_reports_a_block_the_game_stops(tmp_path):
    job = job_for("03", tmp_path / "x")
    job["drags"][0]["path"] = [{"x": 3, "y": 3}, {"x": 2, "y": 3}]  # red holds (2,3)
    job["drags"][0]["exits"] = False
    r = run_raw(job, tmp_path / "blocked")
    assert r["status"] == "mismatch"
    assert "entered no new cell" in r["message"]


def test_runner_reports_an_exit_the_script_did_not_plan(tmp_path):
    job = job_for("03", tmp_path / "x")
    job["drags"][0]["exits"] = False
    r = run_raw(job, tmp_path / "unplanned")
    assert r["status"] == "mismatch"
    assert "did not plan an exit" in r["message"]


def test_play_stops_at_the_fail_screen(tmp_path):
    level = json.loads((PROJ / "data/levels/Level_03.json").read_text())
    level["timerCount"] = 2
    lp = tmp_path / "Level_03.json"
    lp.write_text(json.dumps(level))
    job = job_for("03", tmp_path / "x")
    job["level_path"] = str(lp)
    job["drags"][1]["pause_before_s"] = 3.0  # the timer runs out before drag 2
    r = run_raw(job, tmp_path / "fail")
    assert r["status"] == "failed"
    assert r["fail_frame"] > 0 and r["win_frame"] == -1
    assert len(r["drags"]) == 1  # nothing is played after the fail screen


def test_runner_reports_a_path_off_the_board(tmp_path):
    job = job_for("03", tmp_path / "x")
    job["drags"][0]["path"] = [{"x": 3, "y": 3}, {"x": 3, "y": 2}, {"x": 3, "y": 1}, {"x": 3, "y": 0},
                               {"x": 3, "y": -1}]
    job["drags"][0]["exits"] = False
    r = run_raw(job, tmp_path / "off")
    assert r["status"] == "mismatch"
    assert "(3,-1) is not an active cell" in r["message"]


def test_a_dead_ffmpeg_ends_the_run_instead_of_hanging(tmp_path):
    job = job_for("03", tmp_path / "x")
    job["ffmpeg"] = "/usr/bin/false"
    t0 = time.perf_counter()
    r = run_raw(job, tmp_path / "ffdead")
    assert time.perf_counter() - t0 < 60
    assert r["status"] == "error" and "ffmpeg" in r["message"]


def test_a_bad_end_mode_is_refused_at_start(tmp_path):
    job = job_for("03", tmp_path / "x")
    job["end_mode"] = "wn"
    r = run_raw(job, tmp_path / "badend")
    assert r["status"] == "error" and "end_mode" in r["message"] and r["frames"] == 0


def test_timer_running_out_mid_drag_interrupts_the_drag(tmp_path):
    level = json.loads((PROJ / "data/levels/Level_03.json").read_text())
    level["timerCount"] = 1
    lp = tmp_path / "Level_03.json"
    lp.write_text(json.dumps(level))
    job = job_for("03", tmp_path / "x")
    job["level_path"] = str(lp)
    job["end_mode"] = "fail"
    job["drags"][0]["pickup_s"] = 1.5  # finger down past the 1 s timer
    r = run_raw(job, tmp_path / "middrag")
    assert r["status"] == "failed"
    assert r["drags"][0]["result"] == "interrupted"
    assert r["problems"] == []


def test_changing_only_the_camera_keeps_the_game_identical(tmp_path):
    # A small controlled edit: the framing changes every frame, the gameplay does not.
    base = run_player(job_for("03", tmp_path / "base", size=(540, 960)))
    zoom = run_player(job_for("03", tmp_path / "zoom", size=(540, 960), camera=Camera(zoom=1.1)))
    assert base["problems"] == [] and zoom["problems"] == []
    c = compare_recordings(tmp_path / "base", tmp_path / "zoom")
    assert c["state_equal"] and not c["finger_path_equal"]
    assert c["min_psnr_db"] < 30


def test_bad_camera_keys_are_refused_at_start(tmp_path):
    job = job_for("03", tmp_path / "x")
    job["camera"]["keys"] = [{"t": 1, "zoom": 1, "pan_x": 0, "pan_y": 0}, {"t": 0.5, "zoom": 1, "pan_x": 0, "pan_y": 0}]
    r = run_raw(job, tmp_path / "badcam")
    assert r["status"] == "error" and "increasing time order" in r["message"]


def slide_job(tmp_path, name):
    # Timer 3 s; the last exit starts about 0.3 s before the clock would end, and its slide
    # out takes 0.5 s, so on the stock game the clock runs out mid-slide.
    job = job_for("03", tmp_path / name, timer=3)
    job["drags"][2]["pause_before_s"] = 1.05
    return job


def test_the_patched_game_stops_its_own_clock(tmp_path):
    # The recorder leaves the clock alone here; the game patch alone must end it cleanly.
    job = slide_job(tmp_path, "patched")
    job["stop_clock_on_last_exit"] = False
    r = run_player(job)
    assert r["game_patched"] is True
    assert r["problems"] == [], r["problems"]
    assert r["status"] == "cleared" and r["fail_frame"] == -1
    exit_frame = r["drags"][2]["exit_frame"]
    assert exit_frame <= r["clock_stopped_frame"] <= exit_frame + 4  # after the 0.1 s snap
    assert 0 < r["timer_end"] < 1


def test_the_default_recording_ends_cleanly_with_little_time_left(tmp_path):
    r = run_player(slide_job(tmp_path, "default"))
    assert r["problems"] == [], r["problems"]
    assert r["status"] == "cleared" and r["fail_frame"] == -1 and 0 < r["timer_end"] < 1


needs_stock = pytest.mark.skipif(not PLAYER_STOCK.is_dir(), reason="run `cbj build-player --stock` first")


@needs_stock
def test_the_stock_game_shows_out_of_time_then_level_completed(tmp_path):
    # the publisher's game as shipped: the clock runs on during the last exit slide.
    job = slide_job(tmp_path, "stock")
    job["stop_clock_on_last_exit"] = False
    r = run_player(job, app=PLAYER_STOCK)
    assert r["game_patched"] is False
    assert r["drags"][2]["exit_frame"] < r["fail_frame"] < r["win_frame"]
    assert any("both the fail screen and the win screen" in p for p in r["problems"])


@needs_stock
def test_on_the_stock_game_the_recorder_stops_the_clock_itself(tmp_path):
    r = run_player(slide_job(tmp_path, "stockfix"), app=PLAYER_STOCK)
    assert r["problems"] == [], r["problems"]
    assert r["status"] == "cleared" and r["clock_stopped_frame"] == r["drags"][2]["exit_frame"]


def test_event_data_for_the_compositor(tmp_path):
    r = run_player(job_for("03", tmp_path / "ev", size=(540, 960), timer=60, hide=("RestartButton",)))
    assert r["problems"] == []
    assert r["timer_start"] == pytest.approx(60, abs=0.05)
    assert [d["exit_index"] for d in r["drags"]] == [3, 0, 1]
    # every block leaves, after the frame its exit started
    assert all(g > d["exit_frame"] for g, d in zip(r["block_gone_frames"], r["drags"]))
    names = {u["name"] for u in r["ui_rects"]}
    assert "MainBar" in names and "RestartButton" not in names
    frames = json.loads((tmp_path / "ev/frames.json").read_text())["frames"]
    assert len(frames[0]["blocks"]) == 6
    assert all(0 <= v <= 960 for v in frames[0]["blocks"])
    assert frames[-1]["blocks"] == [-1, -1, -1, -1, -1, -1]


def test_hiding_an_unknown_object_is_an_error(tmp_path):
    r = run_player(job_for("03", tmp_path / "nohide", hide=("NoSuchThing",)))
    assert r["status"] == "error" and "NoSuchThing" in r["message"]


def test_a_dry_run_has_the_same_timing_as_a_recording(tmp_path):
    # The game state does not depend on filming, so a dry run gives the exact frames to plan with.
    full = run_player(job_for("03", tmp_path / "full"))
    dry = run_player(job_for("03", tmp_path / "dry", size=(270, 480), capture=False))
    assert dry["problems"] == [] and dry["captured"] is False
    keys = ("frames", "first_touch_frame", "clock_stopped_frame", "win_frame", "block_gone_frames")
    assert {k: dry[k] for k in keys} == {k: full[k] for k in keys}
    assert [(d["start_frame"], d["exit_frame"], d["end_frame"]) for d in dry["drags"]] == \
           [(d["start_frame"], d["exit_frame"], d["end_frame"]) for d in full["drags"]]
    assert not (tmp_path / "dry" / "gameplay.mp4").exists()


NARROW = PROJ / "data/levels/gen/narrow_center_01.json"


@pytest.mark.parametrize("ending", ["win", "near_fail", "cliffhanger", "time_out"])
def test_scenario_endings_land_on_the_predicted_frames(tmp_path, ending):
    # Dry run, pause-only fit, recording; the recording must match the prediction frame for frame.
    from cbj.play import plan, run
    level = load_level(NARROW)
    script = plan(level, ending)
    r = run(level, NARROW, script, tmp_path / ending, size=(270, 480), hide=("RestartButton",))
    assert r["problems"] == []
    m = script.measured
    play = json.loads((tmp_path / ending / "play.json").read_text())
    assert play["measured"]["problems"] == [] and play["fit"]["dry_frames"] > 0
    recorded = json.loads((tmp_path / ending / "level.json").read_text())  # the level with the ad's clock
    assert recorded["timerCount"] == (script.timer_s or level.timer)
    if ending == "win":
        assert r["status"] == "cleared" and m["clock_left_s"] >= 50  # never in the red
    if ending == "near_fail":
        assert r["status"] == "cleared" and 1.3 <= m["clock_left_s"] <= 1.7  # the HUD shows 00:01
        mistake = next(d for d, b in zip(r["drags"], script.beats) if b.kind == "mistake")
        assert mistake["result"] == "placed"  # pushed into its blocker, still on its planned cell
    if ending == "cliffhanger":
        assert r["status"] == "unresolved" and 5 <= m["clock_left_s"] <= 12
        assert r["drags"][-1]["result"] == "placed" and r["drags"][-1]["cells"] == []  # the push moved no cell
    if ending == "time_out":
        assert r["status"] == "failed" and r["drags"][-1]["result"] == "interrupted"
        last = r["drags"][-1]
        assert last["cell_frames"] and abs(r["fail_frame"] - last["cell_frames"][-1]) <= 2
        frames = json.loads((tmp_path / ending / "frames.json").read_text())["frames"]
        assert frames[last["start_frame"]]["timer"] >= 1.4  # the HUD shows 00:01 for ~0.5 s at the grab
        assert play["fit"]["predicted_frames"] is None  # the fail screen, not the dry run, ends it


def test_rerun_from_the_folder_alone_gives_the_same_game(tmp_path):
    from cbj.render import rerun
    first = run_player(job_for("03", tmp_path / "first", size=(270, 480)))
    again = rerun(tmp_path / "first", tmp_path / "again")
    assert first["problems"] == [] and again["problems"] == []
    assert compare_recordings(tmp_path / "first", tmp_path / "again")["state_equal"]
