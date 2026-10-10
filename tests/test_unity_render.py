"""Recordings in the real game. Opt-in, because each one starts the Unity player:

    uv run cbj build-player
    CBJ_UNITY=1 uv run pytest tests/test_unity_render.py
"""

import copy
import json
import os
import subprocess
from pathlib import Path

import pytest

from cbj.describe import script_to_drags
from cbj.level import load_level
from cbj.render import PLAYER_APP, check_render, make_job, player_binary, run_player

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


def test_same_job_gives_the_same_frames(tmp_path):
    a = run_player(job_for("03", tmp_path / "a"))
    b = run_player(job_for("03", tmp_path / "b"))
    fa = json.loads((tmp_path / "a/frames.json").read_text())["frames"]
    fb = json.loads((tmp_path / "b/frames.json").read_text())["frames"]
    assert a["frames"] == b["frames"] == len(fa) == len(fb)
    assert [f["hash"] for f in fa] == [f["hash"] for f in fb]


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
