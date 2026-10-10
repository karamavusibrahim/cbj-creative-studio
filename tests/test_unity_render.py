"""Recordings in the real game. Opt-in, because each one starts the Unity player:

    uv run cbj build-player
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
from cbj.render import PLAYER_APP, Camera, check_render, compare_recordings, make_job, player_binary, run_player

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
