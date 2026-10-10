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
from cbj.render import Pacing, check_render, level_label, make_job, player_binary
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
    ({"pacing": Pacing(pause_before_s=-1)}, "pause_before_s"),
    ({"pacing": Pacing(end_hold_s=float("nan"))}, "end_hold_s"),
    ({"size": (1081, 1920)}, "even"),
    ({"size": (8, 8)}, "at least 16x16"),
])
def test_job_rejects_bad_settings(tmp_path, kw, msg):
    with pytest.raises(ValueError, match=msg):
        job3(tmp_path, **kw)


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
                   video_frames=None, size=(64, 112)):
    out.mkdir(parents=True, exist_ok=True)
    w, h = size
    result = {
        "status": status, "message": "", "end_mode": end_mode, "frames": frames, "fps": 30,
        "width": w, "height": h, "video": str(out / "gameplay.mp4"),
        "drags": [{"index": 0, "result": drag_result}],
    }
    (out / "result.json").write_text(json.dumps(result))
    log = {"frames": [{"frame": i, "hash": f"{i:032x}"} for i in range(frames)]}
    (out / "frames.json").write_text(json.dumps(log))
    n = frames if video_frames is None else video_frames
    if n:
        subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=blue:s={w}x{h}:r=30",
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
