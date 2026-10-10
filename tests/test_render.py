"""Render jobs for the Unity CreativeRunner, and the checks on what it recorded.
These tests do not start Unity; tests/test_unity_render.py does (opt-in)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from cbj import cli, render
from cbj.describe import script_to_drags
from cbj.level import load_level
from cbj.render import (Camera, Pacing, check_render, compare_recordings, level_label, make_job, player_binary,
                        run_player)
from cbj.solver import Drag, ReplayError

PROJ = Path(__file__).parent.parent
LEVEL_03 = PROJ / "data/levels/Level_03.json"
MOVES_03 = PROJ / "data/solutions/Level_03.moves.json"
FFMPEG = shutil.which("ffmpeg")


def level3():
    level = load_level(LEVEL_03)
    drags = script_to_drags(json.loads(MOVES_03.read_text()))
    return level, drags


def job3(tmp_path, **kw):
    level, drags = level3()
    return make_job(level, LEVEL_03, drags, tmp_path / "out", ffmpeg="/usr/bin/true", **kw)


def walk(value):
    yield value
    if isinstance(value, dict):
        for v in value.values():
            yield from walk(v)
    elif isinstance(value, list):
        for v in value:
            yield from walk(v)


def test_job_for_level_3(tmp_path):
    job = job3(tmp_path)
    assert job["level_label"] == 3
    assert job["end_mode"] == "win"
    assert (job["width"], job["height"], job["fps"]) == (1080, 1920, 30)
    assert Path(job["level_path"]).is_absolute() and Path(job["out_dir"]).is_absolute()
    assert [d["block"] for d in job["drags"]] == [0, 1, 2]
    assert job["drags"][0]["path"] == [{"x": 3, "y": 3}, {"x": 3, "y": 2}, {"x": 4, "y": 2}]
    assert all(d["exits"] for d in job["drags"])
    assert job["drags"][0]["pause_before_s"] == 0.0  # the start hold covers the first drag
    assert job["drags"][1]["pause_before_s"] == Pacing().pause_before_s
    assert job["max_seconds"] > 30


def test_job_has_only_shapes_unity_jsonutility_can_read(tmp_path):
    # JsonUtility cannot read nested arrays or nulls into the runner's classes.
    job = job3(tmp_path)
    for v in walk(job):
        assert v is not None
        if isinstance(v, list):
            assert all(not isinstance(item, list) for item in v)


def test_job_rejects_a_drag_that_breaks_a_rule(tmp_path):
    level, drags = level3()
    # Yellow (pivot 3,3) cannot step left: the red block holds (2,3).
    bad = [Drag(0, ((3, 3), (2, 3)), False)] + drags[1:]
    with pytest.raises(ReplayError):
        make_job(level, LEVEL_03, bad, tmp_path, ffmpeg="/usr/bin/true")


def test_win_ending_needs_a_cleared_board(tmp_path):
    level, drags = level3()
    with pytest.raises(ValueError, match="use end mode 'cut'"):
        make_job(level, LEVEL_03, drags[:2], tmp_path, ffmpeg="/usr/bin/true")
    job = make_job(level, LEVEL_03, drags[:2], tmp_path, end_mode="cut", ffmpeg="/usr/bin/true")
    assert len(job["drags"]) == 2


def test_cut_ending_needs_a_block_left(tmp_path):
    level, drags = level3()
    with pytest.raises(ValueError, match="use end mode 'win'"):
        make_job(level, LEVEL_03, drags, tmp_path, end_mode="cut", ffmpeg="/usr/bin/true")


def test_fail_ending_needs_a_block_left_and_waits_for_the_timer(tmp_path):
    level, drags = level3()
    with pytest.raises(ValueError, match="at least one block left"):
        make_job(level, LEVEL_03, drags, tmp_path, end_mode="fail", ffmpeg="/usr/bin/true")
    job = make_job(level, LEVEL_03, drags[:2], tmp_path, end_mode="fail", ffmpeg="/usr/bin/true")
    assert job["max_seconds"] > level.timer


@pytest.mark.parametrize("kw, msg", [
    ({"end_mode": "lose"}, "end must be one of"),
    ({"pacing": Pacing(fps=0)}, "fps"),
    ({"pacing": Pacing(fps=True)}, "fps"),
    ({"pacing": Pacing(fps=24.0)}, "fps"),
    ({"pacing": Pacing(cells_per_s=0)}, "cells_per_s"),
    ({"pacing": Pacing(cells_per_s=16)}, "at most fps/2"),
    ({"pacing": Pacing(fps=10, cells_per_s=6)}, "at most fps/2"),
    ({"pacing": Pacing(cells_per_s=float("nan"))}, "cells_per_s"),
    ({"pacing": Pacing(pause_before_s=-1)}, "pause_before_s"),
    ({"pacing": Pacing(end_hold_s=float("nan"))}, "end_hold_s"),
    ({"size": (1081, 1920)}, "even"),
    ({"size": (8, 8)}, "at least 16x16"),
])
def test_job_rejects_bad_settings(tmp_path, kw, msg):
    with pytest.raises(ValueError, match=msg):
        job3(tmp_path, **kw)


def test_finger_speed_up_to_half_a_cell_per_frame_is_allowed(tmp_path):
    assert job3(tmp_path, pacing=Pacing(cells_per_s=15))["drags"][0]["cells_per_s"] == 15


def test_job_needs_drags(tmp_path):
    level, _ = level3()
    with pytest.raises(ValueError):
        make_job(level, LEVEL_03, [], tmp_path, end_mode="cut", ffmpeg="/usr/bin/true")


def test_level_label():
    level, _ = level3()
    assert level_label(level) == 3
    assert level_label(load_level(PROJ / "data/levels/Level_06.json")) == 6


def test_missing_player_says_how_to_build_it(tmp_path):
    with pytest.raises(ValueError, match="cbj build-player"):
        player_binary(tmp_path / "nothing.app")


def test_run_removes_old_stills_but_not_other_files(tmp_path):
    job = job3(tmp_path)
    out = Path(job["out_dir"])
    out.mkdir(parents=True)
    (out / "03_drag.png").write_bytes(b"old")
    (out / "my_notes.png").write_bytes(b"keep")
    with pytest.raises(ValueError, match="cbj build-player"):
        run_player(job, app=tmp_path / "nothing.app")
    assert not (out / "03_drag.png").exists()
    assert (out / "my_notes.png").exists()


def test_cli_render_without_a_player_prints_one_line(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(render, "PLAYER_APP", tmp_path / "nothing.app")
    code = cli.main(["render", str(LEVEL_03), str(MOVES_03), "-o", str(tmp_path / "out")])
    err = capsys.readouterr().err
    assert code == 1 and err.startswith("cbj: ") and "cbj build-player" in err


@pytest.mark.parametrize("args, msg", [
    (["--drags", "0"], "--drags must be 1 or more"),
    (["--end", "win", "--drags", "2"], "use end mode 'cut'"),
])
def test_cli_render_rejects_bad_options(tmp_path, monkeypatch, capsys, args, msg):
    monkeypatch.setattr(render, "PLAYER_APP", tmp_path / "nothing.app")
    code = cli.main(["render", str(LEVEL_03), str(MOVES_03), "-o", str(tmp_path / "o")] + args)
    assert code == 1 and msg in capsys.readouterr().err


def test_cli_render_bad_size_is_a_usage_error(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["render", str(LEVEL_03), "--size", "1080x"])
    assert e.value.code == 2 and "1080x1920" in capsys.readouterr().err


# ---------- check_render on recordings written by hand ----------

def fake_recording(out: Path, frames=6, status="cleared", end_mode="win", drag_result="exit",
                   video_frames=None, size=(64, 112), color="blue", timer=300.0):
    out.mkdir(parents=True, exist_ok=True)
    w, h = size
    result = {
        "status": status, "message": "", "end_mode": end_mode, "frames": frames, "fps": 30,
        "width": w, "height": h, "video": str(out / "gameplay.mp4"),
        "drags": [{"index": 0, "result": drag_result}],
    }
    (out / "result.json").write_text(json.dumps(result))
    log = {"frames": [{"frame": i, "hash": f"{i:032x}", "timer": timer, "finger": False,
                       "finger_x": 0, "finger_y": 0} for i in range(frames)]}
    (out / "frames.json").write_text(json.dumps(log))
    n = frames if video_frames is None else video_frames
    if n:
        subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={color}:s={w}x{h}:r=30",
                        "-frames:v", str(n), "-pix_fmt", "yuv420p", str(out / "gameplay.mp4")], check=True)
    return out


needs_ffmpeg = pytest.mark.skipif(not FFMPEG, reason="ffmpeg not installed")


@needs_ffmpeg
def test_check_render_accepts_a_consistent_recording(tmp_path):
    r = check_render(fake_recording(tmp_path / "ok"))
    assert r["problems"] == []
    assert r["probe"]["frames"] == 6


@needs_ffmpeg
@pytest.mark.parametrize("kw, msg", [
    ({"status": "mismatch"}, "status is 'mismatch'"),
    ({"status": "unresolved"}, "expected 'cleared'"),
    ({"end_mode": "fail", "status": "failed"}, None),
    ({"end_mode": "cut", "status": "unresolved"}, None),
    ({"end_mode": "fail", "status": "failed", "drag_result": "interrupted"}, None),
    ({"drag_result": "mismatch: block 0 entered no new cell"}, "drag 1: mismatch"),
    ({"video_frames": 5}, "video has 5 frames"),
    ({"video_frames": 0}, "no video"),
])
def test_check_render_reports_what_is_wrong(tmp_path, kw, msg):
    r = check_render(fake_recording(tmp_path / "rec", **kw))
    if msg is None:
        assert r["problems"] == []
    else:
        assert any(msg in p for p in r["problems"]), r["problems"]


@needs_ffmpeg
def test_check_render_notices_a_frame_log_gap(tmp_path):
    out = fake_recording(tmp_path / "gap")
    log = json.loads((out / "frames.json").read_text())
    del log["frames"][2]
    (out / "frames.json").write_text(json.dumps(log))
    problems = check_render(out)["problems"]
    assert any("frames.json has 5 frames" in p for p in problems)
    assert any("not numbered" in p for p in problems)


@needs_ffmpeg
def test_compare_identical_recordings(tmp_path):
    a = fake_recording(tmp_path / "a")
    b = fake_recording(tmp_path / "b")
    c = compare_recordings(a, b)
    assert c["state_equal"] and c["identical_frames"] == 6
    assert c["min_psnr_db"] == float("inf")


@needs_ffmpeg
def test_compare_finds_a_state_difference_and_a_pixel_difference(tmp_path):
    a = fake_recording(tmp_path / "a")
    b = fake_recording(tmp_path / "b", timer=299.0, color="red")
    c = compare_recordings(a, b)
    assert not c["state_equal"] and c["state_diff_frames"][:2] == [0, 1]
    assert c["min_psnr_db"] < 20


@needs_ffmpeg
def test_cli_compare(tmp_path, capsys):
    a = fake_recording(tmp_path / "a")
    b = fake_recording(tmp_path / "b")
    assert cli.main(["compare", str(a), str(b)]) == 0
    out = capsys.readouterr().out
    assert "game state (timer, finger, drags, ending): identical" in out
    assert "finger on screen: same path" in out
    assert cli.main(["compare", str(a), str(tmp_path / "nothing")]) == 1
    assert "no recording" in capsys.readouterr().err


@needs_ffmpeg
def test_compare_separates_the_finger_on_screen_from_the_game_state(tmp_path):
    a = fake_recording(tmp_path / "a")
    b = fake_recording(tmp_path / "b")
    log = json.loads((b / "frames.json").read_text())
    for f in log["frames"]:
        f["finger_x"] = 40  # same game, different framing
    (b / "frames.json").write_text(json.dumps(log))
    c = compare_recordings(a, b)
    assert c["state_equal"] and not c["finger_path_equal"]


def test_job_carries_the_camera(tmp_path):
    job = job3(tmp_path, camera=Camera(zoom=1.1, pan_y=-0.5, keys=((0, 0.8, 0, 0), (1.5, 1.1, 0, -0.5))))
    cam = job["camera"]
    assert (cam["zoom"], cam["pan_x"], cam["pan_y"]) == (1.1, 0.0, -0.5)
    assert cam["keys"][1] == {"t": 1.5, "zoom": 1.1, "pan_x": 0, "pan_y": -0.5}
    assert job3(tmp_path)["camera"] == {"zoom": 1.0, "pan_x": 0.0, "pan_y": 0.0, "keys": []}


def test_intro_camera_eases_in_from_pulled_back():
    cam = Camera.intro(1.0, seconds=1.0)
    assert cam.keys == ((0.0, 0.75, 0.0, 0.0), (1.0, 1.0, 0.0, 0.0))


@pytest.mark.parametrize("cam", [
    Camera(zoom=0), Camera(zoom=-1), Camera(zoom=float("nan")), Camera(pan_y=float("inf")),
    Camera(keys=((1, 1, 0, 0), (0.5, 1, 0, 0))),   # keys out of order
    Camera(keys=((0, 0, 0, 0),)),                   # zero zoom in a key
    Camera(keys=((0, 1, 0),)),                      # too short
])
def test_bad_camera_is_refused(tmp_path, cam):
    with pytest.raises(ValueError, match="camera"):
        job3(tmp_path, camera=cam)


def test_cli_pacing_and_camera_flags_reach_the_job(tmp_path, monkeypatch):
    seen = {}

    def fake_run(job, app=None, timeout=900):
        seen.update(job)
        raise ValueError("stop here")

    monkeypatch.setattr(render, "run_player", fake_run)
    cli.main(["render", str(LEVEL_03), str(MOVES_03), "-o", str(tmp_path / "o"), "--pause", "1.5",
              "--start-hold", "2", "--end-hold", "3", "--speed", "4", "--zoom", "1.1", "--intro"])
    assert seen["start_hold_s"] == 2 and seen["end_hold_s"] == 3
    assert [d["pause_before_s"] for d in seen["drags"]] == [0.0, 1.5, 1.5]
    assert seen["drags"][0]["cells_per_s"] == 4
    assert seen["camera"]["keys"][0]["zoom"] == pytest.approx(0.825)
    assert seen["camera"]["keys"][-1]["t"] == 2


def test_job_timer_override_and_hide(tmp_path):
    job = job3(tmp_path, timer=12, hide=("RestartButton",))
    assert job["timer_s"] == 12 and job["hide"] == ["RestartButton"]
    assert job3(tmp_path)["timer_s"] == -1 and job3(tmp_path)["hide"] == []
    assert [d["exit_index"] for d in job["drags"]] == [3, 0, 1]


@pytest.mark.parametrize("kw, msg", [
    ({"timer": 0}, "timer must be"), ({"timer": 2.5}, "timer must be"), ({"timer": True}, "timer must be"),
    ({"hide": ("",)}, "hide must be"),
])
def test_bad_timer_or_hide_is_refused(tmp_path, kw, msg):
    with pytest.raises(ValueError, match=msg):
        job3(tmp_path, **kw)


def test_fail_ending_waits_for_the_overridden_timer(tmp_path):
    level, drags = level3()
    job = make_job(level, LEVEL_03, drags[:2], tmp_path, end_mode="fail", ffmpeg="/usr/bin/true", timer=600)
    assert job["max_seconds"] > 600


@needs_ffmpeg
def test_check_render_rejects_a_video_with_both_endings(tmp_path):
    out = fake_recording(tmp_path / "both", status="failed", end_mode="fail")
    r = json.loads((out / "result.json").read_text())
    r.update(fail_frame=3, win_frame=5)
    (out / "result.json").write_text(json.dumps(r))
    assert any("both the fail screen and the win screen" in p for p in check_render(out)["problems"])


def test_stock_flag_records_with_the_stock_player_and_leaves_the_clock_alone(tmp_path, monkeypatch):
    seen = {}

    def fake_run(job, app=None, timeout=900):
        seen.update(job, app=app)
        raise ValueError("stop here")

    monkeypatch.setattr(render, "run_player", fake_run)
    cli.main(["render", str(LEVEL_03), str(MOVES_03), "-o", str(tmp_path / "o"), "--stock"])
    assert seen["stop_clock_on_last_exit"] is False and seen["app"] == render.PLAYER_STOCK
    assert job3(tmp_path)["stop_clock_on_last_exit"] is True


def test_fail_ending_needs_a_clock(tmp_path):
    import dataclasses
    level, drags = level3()
    no_clock = dataclasses.replace(level, timer=0)
    with pytest.raises(ValueError, match="needs a clock"):
        make_job(no_clock, LEVEL_03, drags[:2], tmp_path, end_mode="fail", ffmpeg="/usr/bin/true")
    job = make_job(no_clock, LEVEL_03, drags[:2], tmp_path, end_mode="fail", ffmpeg="/usr/bin/true", timer=5)
    assert job["timer_s"] == 5
