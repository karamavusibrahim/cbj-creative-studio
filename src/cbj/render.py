"""Record a move script in the real game.

The Unity side is unity/CreativeRunner: it loads the level, replays each drag through the
game's own movement, grid and exit code on a fixed time step, and pipes the frames to ffmpeg.
This module checks the script against the rules, writes the runner's job file, starts the
player, and checks what came back.

    uv run cbj build-player     # once: copy of the Unity project + macOS player in build/
    uv run cbj render data/levels/Level_03.json data/solutions/Level_03.moves.json
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .level import Level
from .solver import Drag, replay

REPO = Path(__file__).resolve().parents[2]
RUNNER_SRC = REPO / "unity" / "CreativeRunner"
BUILD_DIR = REPO / "build"
BUILD_PROJECT = BUILD_DIR / "unity-project"
PLAYER_APP = BUILD_DIR / "CBJRunner.app"
PLAYER_STOCK = BUILD_DIR / "CBJRunner-stock.app"  # Rollic's game without the game patch
GAME_PATCH = REPO / "unity" / "game-patch"
# The game patch (unity/game-patch/game.patch) stops the clock when the last block starts to
# leave and keeps a second ending from showing after the first. These are the files it changes.
PATCHED_FILES = (
    "Assets/Scripts/GameManager.cs",
    "Assets/Scripts/Services/Exit/ExitService.cs",
    "Assets/Scripts/Services/Input/InputHandler.cs",
)
DEFAULT_PROJECT = REPO.parent / "CBJ"
DEFAULT_UNITY = "/Applications/Unity/Hub/Editor/6000.3.5f1/Unity.app/Contents/MacOS/Unity"
END_MODES = ("win", "cut", "fail")
EXPECTED_STATUS = {"win": "cleared", "cut": "unresolved", "fail": "failed"}


@dataclass(frozen=True)
class Pacing:
    """Plain, steady play. Scenario pacing (hesitation, wrong moves) builds on this later."""

    fps: int = 30
    start_hold_s: float = 1.0  # board on screen before the first touch
    pause_before_s: float = 0.45  # between drags
    pickup_s: float = 0.12  # finger down before the block moves
    cells_per_s: float = 6.0  # finger speed while dragging
    end_hold_s: float = 2.5  # after the win screen (or after the last drag for "cut")

    def check(self) -> None:
        if not isinstance(self.fps, int) or isinstance(self.fps, bool) or not 1 <= self.fps <= 120:
            raise ValueError(f"fps must be an integer from 1 to 120, got {self.fps!r}")
        if not 0 < self.cells_per_s <= self.fps / 2:
            # Faster than half a cell per frame and the block can land on a cell boundary,
            # where the game's per-frame exit check may see a different cell.
            raise ValueError(f"cells_per_s must be above 0 and at most fps/2 ({self.fps / 2:g}), "
                             f"got {self.cells_per_s!r}")
        for name in ("start_hold_s", "pause_before_s", "pickup_s", "end_hold_s"):
            v = getattr(self, name)
            if not v >= 0:
                raise ValueError(f"{name} must be zero or more, got {v!r}")


@dataclass(frozen=True)
class DragPacing:
    """Pacing for one drag, overriding the Pacing defaults (scenario scripts set these per beat).

    push_cells: after the last cell, the finger presses on this far (0-0.45 cells). Against a
    block in the way, the game holds the block where it is: a player pushing into a blocker.
    push_dir: (dx, dy), one cell along an axis; None pushes the way the path last moved.
    hold_s: the finger stays down at the end of the drag before letting go."""

    pause_before_s: float
    pickup_s: float
    cells_per_s: float
    push_cells: float = 0.0
    hold_s: float = 0.0
    push_dir: tuple[int, int] | None = None

    def check(self, fps: int, k: int) -> None:
        for name in ("pause_before_s", "pickup_s", "hold_s"):
            v = getattr(self, name)
            if not (isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v < float("inf")):
                raise ValueError(f"drag {k}: {name} must be zero or more, got {v!r}")
        if not (isinstance(self.cells_per_s, (int, float)) and 0 < self.cells_per_s <= fps / 2):
            raise ValueError(f"drag {k}: cells_per_s must be above 0 and at most fps/2 ({fps / 2:g}), "
                             f"got {self.cells_per_s!r}")
        # Past half a cell the pivot would round into the next cell, which the script did not plan.
        if not (isinstance(self.push_cells, (int, float)) and 0 <= self.push_cells <= 0.45):
            raise ValueError(f"drag {k}: push_cells must be 0 to 0.45, got {self.push_cells!r}")
        if self.push_dir is not None and (len(self.push_dir) != 2 or sorted(map(abs, self.push_dir)) != [0, 1]):
            raise ValueError(f"drag {k}: push_dir must be one cell along an axis, got {self.push_dir!r}")


@dataclass(frozen=True)
class Camera:
    """Framing on top of the game's own fit. zoom 1 = the game's framing, 1.2 = 20% closer;
    pan in cells (+x right, +y up the board). keys: (t_seconds, zoom, pan_x, pan_y) tuples,
    eased between, held before the first and after the last."""

    zoom: float = 1.0
    pan_x: float = 0.0
    pan_y: float = 0.0
    keys: tuple[tuple[float, float, float, float], ...] = ()

    def check(self) -> None:
        def finite(v):
            return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != float("inf")
        if not (finite(self.zoom) and self.zoom > 0 and finite(self.pan_x) and finite(self.pan_y)):
            raise ValueError("camera zoom must be a positive number and pans finite numbers")
        last = -1.0
        for k, key in enumerate(self.keys, start=1):
            if len(key) != 4 or not all(finite(v) for v in key):
                raise ValueError(f"camera key {k} must be (t, zoom, pan_x, pan_y) numbers")
            t, zoom = key[0], key[1]
            if t < 0 or zoom <= 0 or t <= last:
                raise ValueError(f"camera key {k}: t must be zero or more and increasing, zoom positive")
            last = t

    def to_job(self) -> dict:
        return {"zoom": self.zoom, "pan_x": self.pan_x, "pan_y": self.pan_y,
                "keys": [{"t": t, "zoom": z, "pan_x": x, "pan_y": y} for t, z, x, y in self.keys]}

    @staticmethod
    def intro(zoom: float = 1.0, pan_x: float = 0.0, pan_y: float = 0.0, seconds: float = 1.0) -> "Camera":
        """Start pulled back and ease into the framing, like the game's level-start glide."""
        return Camera(zoom, pan_x, pan_y, ((0.0, zoom * 0.75, pan_x, pan_y), (seconds, zoom, pan_x, pan_y)))


def level_label(level: Level) -> int:
    """The number the game shows in its "Level" badge: Level_03 -> 3."""
    m = re.search(r"(\d+)$", level.name)
    return int(m.group(1)) if m else 1


def make_job(
    level: Level,
    level_path: str | Path,
    drags: list[Drag],
    out_dir: str | Path,
    pacing: Pacing = Pacing(),
    end_mode: str = "win",
    label: int | None = None,
    size: tuple[int, int] = (1080, 1920),
    ffmpeg: str | None = None,
    camera: Camera = Camera(),
    timer: int | None = None,
    hide: tuple[str, ...] = (),
    stop_clock_on_last_exit: bool = True,
    capture: bool = True,
    drag_pacing: list[DragPacing] | None = None,
    visuals: dict | None = None,
) -> dict:
    """Job file for CreativeRunner. Raises ValueError if the drags break a rule, or if
    end_mode is "win" and the drags do not clear the board.

    timer: seconds on the game clock instead of the level's own (the level file is unchanged).
    hide: GameObject names to hide, e.g. ("RestartButton",).
    stop_clock_on_last_exit: False keeps the game's own clock, which can show "Out of Time!"
    and then "Level Completed" when time runs out during the last exit slide.
    capture: False makes a dry run: the game plays and logs its timing, but nothing is filmed.
    drag_pacing: one DragPacing per drag, replacing the uniform pause/pickup/speed."""
    if end_mode not in END_MODES:
        raise ValueError(f"end must be one of {', '.join(END_MODES)}, got {end_mode!r}")
    pacing.check()
    camera.check()
    if drag_pacing is not None:
        if len(drag_pacing) != len(drags):
            raise ValueError(f"drag_pacing has {len(drag_pacing)} entries for {len(drags)} drags")
        for k, (d, dp) in enumerate(zip(drags, drag_pacing), start=1):
            dp.check(pacing.fps, k)
            if dp.push_cells and (d.exits or (len(d.path) < 2 and dp.push_dir is None)):
                raise ValueError(f"drag {k}: push_cells needs a drag that does not exit, and a direction "
                                 f"(a path that moves, or push_dir)")
    else:
        drag_pacing = [DragPacing(pacing.pause_before_s if k else 0.0, pacing.pickup_s, pacing.cells_per_s)
                       for k in range(len(drags))]
    if timer is not None and (not isinstance(timer, int) or isinstance(timer, bool) or timer < 1):
        raise ValueError(f"timer must be a whole number of seconds, 1 or more, got {timer!r}")
    if not all(isinstance(h, str) and h for h in hide):
        raise ValueError("hide must be a list of object names")
    final = replay(level, drags)
    left = sum(p is not None for p in final)
    if end_mode == "win" and left:
        raise ValueError(f"the drags leave {left} block(s) on the board, so there is no win "
                         f"to wait for; use end mode 'cut'")
    if end_mode == "cut" and not left:
        raise ValueError("the drags clear the board, so the video would end on the win screen; "
                         "use end mode 'win', or fewer drags for a cliffhanger")
    if end_mode == "fail" and (timer or level.timer) < 1:
        # GameManager.StartTimer only starts a clock with time on it, so it could never run out.
        raise ValueError("a fail ending needs a clock, but the level's timer is 0; set a timer")
    if end_mode == "fail" and not left:
        raise ValueError("the drags clear the board, so the timer cannot run out; "
                         "a fail ending needs at least one block left")
    if not drags:
        raise ValueError("no drags to play")
    w, h = size
    if w < 16 or h < 16 or w % 2 or h % 2:
        raise ValueError(f"video size must be even and at least 16x16, got {w}x{h}")
    ffmpeg = ffmpeg or shutil.which("ffmpeg")
    if not ffmpeg:
        raise ValueError("ffmpeg not found on PATH")
    return {
        "level_path": str(Path(level_path).resolve()),
        "level_label": level_label(level) if label is None else label,
        "out_dir": str(Path(out_dir).resolve()),
        "ffmpeg": ffmpeg,
        "video_name": "gameplay.mp4",
        "fps": pacing.fps,
        "width": w,
        "height": h,
        "msaa": 4,
        "crf": 16,
        "frame_hashes": True,
        "start_hold_s": pacing.start_hold_s,
        "end_hold_s": pacing.end_hold_s,
        "max_seconds": round(estimate_seconds(level, drags, pacing, drag_pacing) * 2 + 30
                             + ((timer or level.timer) if end_mode == "fail" else 0), 1),
        "timer_s": -1 if timer is None else timer,
        "stop_clock_on_last_exit": bool(stop_clock_on_last_exit),
        "capture": bool(capture),
        "hide": list(hide),
        "visuals": visuals_job(visuals),
        "end_mode": end_mode,
        "camera": camera.to_job(),
        "drags": [
            {
                "block": d.block,
                "path": [{"x": x, "y": y} for x, y in d.path],
                "exits": d.exits,
                "exit_index": d.exit_index if d.exit_index is not None else -1,
                "pause_before_s": dp.pause_before_s,
                "pickup_s": dp.pickup_s,
                "cells_per_s": dp.cells_per_s,
                "push_cells": dp.push_cells,
                "push_dx": dp.push_dir[0] if dp.push_dir else 0,
                "push_dy": dp.push_dir[1] if dp.push_dir else 0,
                "hold_s": dp.hold_s,
            }
            for d, dp in zip(drags, drag_pacing)
        ],
    }


def estimate_seconds(level: Level, drags: list[Drag], pacing: Pacing,
                     drag_pacing: list[DragPacing] | None = None) -> float:
    """Rough video length: holds, pauses and finger travel, plus a second for the last exit."""
    if drag_pacing is None:
        drag_pacing = [DragPacing(pacing.pause_before_s if k else 0.0, pacing.pickup_s, pacing.cells_per_s)
                       for k in range(len(drags))]
    t = pacing.start_hold_s + pacing.end_hold_s + 1.0
    for d, dp in zip(drags, drag_pacing):
        t += dp.pause_before_s + dp.pickup_s + d.cells_moved / dp.cells_per_s + dp.hold_s + 0.2
    return t


def player_binary(app: Path | None = None) -> Path:
    app = Path(app or PLAYER_APP)
    macos = app / "Contents" / "MacOS"
    bins = sorted(p for p in macos.iterdir() if p.is_file()) if macos.is_dir() else []
    if not bins:
        raise ValueError(f"{app}: no player build; run `cbj build-player` first")
    return bins[0]


def run_player(job: dict, app: Path | None = None, timeout: float = 900) -> dict:
    """Write job.json, run the player, and return the checked result."""
    out = Path(job["out_dir"])
    out.mkdir(parents=True, exist_ok=True)
    for stale in ("result.json", "frames.json", job["video_name"]):
        (out / stale).unlink(missing_ok=True)
    for still in out.glob("[0-9][0-9]_*.png"):  # 00_start.png, 01_drag.png, ..., 99_end.png
        still.unlink()
    job_path = out / "job.json"
    job_path.write_text(json.dumps(job, indent=2))
    cmd = [str(player_binary(app)), "-cbjJob", str(job_path),
           "-screen-fullscreen", "0", "-screen-width", "270", "-screen-height", "480",
           "-logFile", str(out / "player.log")]
    try:
        proc = subprocess.run(cmd, timeout=timeout, capture_output=True, text=True)
    except subprocess.TimeoutExpired:
        raise ValueError(f"the player did not finish within {timeout:.0f} s; see {out / 'player.log'}") from None
    if not (out / "result.json").is_file():
        raise ValueError(f"the player exited with {proc.returncode} and wrote no result; "
                         f"see {out / 'player.log'}")
    return check_render(out)


def visuals_job(visuals: dict | None) -> dict:
    """The job's visuals section: {"blocks": [{"slot", "hex"}], "grid", "background_top",
    "background_bottom"}; empty fields keep the game's look."""
    v = visuals or {}
    out = {"blocks": [{"slot": b["slot"], "hex": b["hex"]} for b in v.get("blocks", [])],
           "grid": v.get("grid") or "", "background_top": v.get("background_top") or "",
           "background_bottom": v.get("background_bottom") or ""}
    if v.get("background_image"):
        out["background_image"] = str(Path(v["background_image"]).resolve())
    return out


def rerun(folder: str | Path, out_dir: str | Path, changes: dict | None = None) -> dict:
    """Record a finished recording again, into another folder, from the folder alone: job.json
    is the runner's exact input and level.json (written by `cbj scenario`) the level with the
    clock the ad used. Uses the stock player if the original was recorded with it.
    changes: job fields to replace that do not touch the play (visuals, hide, camera, label), for
    an edit that keeps the gameplay: the same drags with the same timing, filmed again."""
    folder, out = Path(folder).resolve(), Path(out_dir).resolve()
    if not (folder / "job.json").is_file() or not (folder / "result.json").is_file():
        raise ValueError(f"{folder}: no recording (job.json and result.json) there")
    if out == folder:
        raise ValueError("rerun into a different folder, so the two recordings can be compared")
    job = json.loads((folder / "job.json").read_text())
    if (folder / "level.json").is_file():
        job["level_path"] = str(folder / "level.json")
    job["out_dir"] = str(out)
    for k, v in (changes or {}).items():
        if k not in ("visuals", "hide", "camera", "level_label"):
            raise ValueError(f"rerun can change only the look ({k} would change the play)")
        job[k] = v
    stock = json.loads((folder / "result.json").read_text()).get("game_patched") is False
    return run_player(job, app=PLAYER_STOCK if stock else None)


def rerun_on(folder: str | Path, out_dir: str | Path, level: dict) -> dict:
    """The same job (the same drags, the same timing) played again on a changed board: a board
    edit that every move survives (a wall removed, a door moved where the play still uses it).
    The clock the ad used is kept; the game itself checks every move again."""
    folder, out = Path(folder).resolve(), Path(out_dir).resolve()
    if not (folder / "job.json").is_file():
        raise ValueError(f"{folder}: no recording (job.json) there")
    job = json.loads((folder / "job.json").read_text())
    used = json.loads((folder / "level.json").read_text()) if (folder / "level.json").is_file() else {}
    lv = {**level, "timerCount": used.get("timerCount", level.get("timerCount"))}
    out.mkdir(parents=True, exist_ok=True)
    (out / "level.json").write_text(json.dumps(lv, indent=2))
    job["level_path"] = str(out / "level.json")
    job["out_dir"] = str(out)
    stock = json.loads((folder / "result.json").read_text()).get("game_patched") is False
    return run_player(job, app=PLAYER_STOCK if stock else None)


def check_render(out_dir: str | Path) -> dict:
    """Read result.json and frames.json and cross-check them with each other and the video.
    Adds a "problems" list; an empty list means the recording is consistent."""
    out = Path(out_dir)
    result = json.loads((out / "result.json").read_text())
    frames = json.loads((out / "frames.json").read_text()).get("frames", [])
    problems = []
    if len(frames) != result.get("frames"):
        problems.append(f"frames.json has {len(frames)} frames, result.json says {result.get('frames')}")
    if [f.get("frame") for f in frames] != list(range(len(frames))):
        problems.append("frames.json is not numbered 0, 1, 2, ...")
    expected = EXPECTED_STATUS.get(result.get("end_mode"))
    if result.get("status") != expected:
        problems.append(f"status is {result.get('status')!r} ({result.get('message')}), "
                        f"expected {expected!r}")
    if result.get("win_frame", -1) >= 0 and result.get("fail_frame", -1) >= 0:
        problems.append("the game showed both the fail screen and the win screen; never use this video")
    for d in result.get("drags", []):
        if d.get("result") not in ("exit", "placed", "interrupted"):
            problems.append(f"drag {d.get('index', 0) + 1}: {d.get('result')}")
    video = out / Path(result.get("video") or "gameplay.mp4").name
    if result.get("captured") is False:
        pass  # a dry run films nothing
    elif not video.is_file():
        problems.append(f"no video at {video}")
    else:
        probe = probe_video(video)
        result["probe"] = probe
        if probe.get("frames") != result.get("frames"):
            problems.append(f"video has {probe.get('frames')} frames, the runner wrote {result.get('frames')}")
        if (probe.get("width"), probe.get("height")) != (result.get("width"), result.get("height")):
            problems.append(f"video is {probe.get('width')}x{probe.get('height')}, "
                            f"expected {result.get('width')}x{result.get('height')}")
    result["problems"] = problems
    return result


def probe_video(path: Path) -> dict:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {}
    cmd = [ffprobe, "-v", "error", "-select_streams", "v:0", "-count_frames",
           "-show_entries", "stream=width,height,nb_read_frames,r_frame_rate,codec_name,pix_fmt",
           "-of", "json", str(path)]
    stream = json.loads(subprocess.run(cmd, capture_output=True, text=True, check=True).stdout)["streams"][0]
    num, den = (int(v) for v in stream["r_frame_rate"].split("/"))
    return {
        "width": stream["width"],
        "height": stream["height"],
        "frames": int(stream["nb_read_frames"]),
        "fps": num / den,
        "codec": stream["codec_name"],
        "pix_fmt": stream["pix_fmt"],
    }


def compare_recordings(a: str | Path, b: str | Path) -> dict:
    """How close two recordings are. The game state (timer, finger down or up, drags, ending)
    must match exactly; the finger's position on screen is reported separately, since a camera
    or size change moves it without changing the game.
    Pixels match in nearly every frame; the rest differ by a few pixels from the graphics
    driver, so pixel closeness is measured as PSNR (identical frames count as infinite)."""
    a, b = Path(a), Path(b)
    ra = json.loads((a / "result.json").read_text())
    rb = json.loads((b / "result.json").read_text())
    fa = json.loads((a / "frames.json").read_text())["frames"]
    fb = json.loads((b / "frames.json").read_text())["frames"]
    state_diff = [x["frame"] for x, y in zip(fa, fb)
                  if abs(x.get("timer", 0) - y.get("timer", 0)) > 1e-4 or x.get("finger") != y.get("finger")]
    finger_moved = [x["frame"] for x, y in zip(fa, fb)
                    if any(abs(x.get(k, 0) - y.get(k, 0)) > 0.5 for k in ("finger_x", "finger_y"))]
    drag_keys = ("block", "cells", "result", "start_frame", "exit_frame", "end_frame")
    drags_equal = [{k: d.get(k) for k in drag_keys} for d in ra["drags"]] == \
                  [{k: d.get(k) for k in drag_keys} for d in rb["drags"]]
    same_length = len(fa) == len(fb)
    out = {
        "frames": (len(fa), len(fb)),
        "state_equal": same_length and not state_diff and drags_equal and ra["status"] == rb["status"]
                       and ra.get("win_frame") == rb.get("win_frame") and ra.get("fail_frame") == rb.get("fail_frame"),
        "state_diff_frames": state_diff[:20],
        "finger_path_equal": same_length and not finger_moved,
        "identical_frames": sum(x.get("hash") == y.get("hash") for x, y in zip(fa, fb)),
        "min_psnr_db": None,
        "worst_frames": [],
    }
    va, vb = a / Path(ra["video"]).name, b / Path(rb["video"]).name
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg and va.is_file() and vb.is_file() and same_length:
        stats = b / "psnr.log"
        subprocess.run([ffmpeg, "-v", "error", "-i", str(va), "-i", str(vb),
                        "-lavfi", f"psnr=stats_file={stats}", "-f", "null", "-"], check=True)
        psnr = []
        for line in stats.read_text().splitlines():
            m = re.search(r"n:(\d+).*psnr_avg:(\S+)", line)
            if m:
                psnr.append((int(m.group(1)) - 1, float(m.group(2))))  # "inf" parses as inf
        stats.unlink()
        worst = sorted(psnr, key=lambda t: t[1])
        out["min_psnr_db"] = worst[0][1] if worst else None
        out["worst_frames"] = [(n, round(v, 1)) for n, v in worst[:3] if v != float("inf")]
    return out


def apply_game_patch(project: Path, stock: bool = False) -> None:
    """Write the patched game files (or, with stock, Rollic's originals) into a project.
    Refuses a project whose files are neither, since the patch was written against the originals."""
    project = Path(project)
    for rel in PATCHED_FILES:
        target = project / rel
        original = (GAME_PATCH / "original" / rel).read_bytes()
        patched = (GAME_PATCH / "patched" / rel).read_bytes()
        current = target.read_bytes() if target.is_file() else None
        if current not in (original, patched):
            raise ValueError(f"{target}: differs from the version the game patch was written for "
                             f"(unity/game-patch/original); update the patch before building")
        target.write_bytes(original if stock else patched)


def build_player(project: Path = DEFAULT_PROJECT, unity: str = DEFAULT_UNITY, stock: bool = False) -> Path:
    """Copy the Unity project into build/, add the runner scripts and the game patch, and build the
    macOS player. stock=True leaves the game as Rollic shipped it (to show its original behaviour).
    The original project is never modified, so it can stay open in the editor."""
    project = Path(project).expanduser().resolve()
    if not (project / "Assets").is_dir() or not (project / "ProjectSettings").is_dir():
        raise ValueError(f"{project}: not a Unity project")
    if not Path(unity).is_file():
        raise ValueError(f"{unity}: Unity editor not found")
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    excludes = ["Temp/", "Logs/", "UserSettings/", "Builds/", "Assets/CreativeRunner/", "Assets/CreativeRunner.meta"]
    cmd = ["rsync", "-a", "--delete"] + [f"--exclude={e}" for e in excludes] + [f"{project}/", f"{BUILD_PROJECT}/"]
    subprocess.run(cmd, check=True)
    dst = BUILD_PROJECT / "Assets" / "CreativeRunner"
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(RUNNER_SRC, dst, ignore=shutil.ignore_patterns("*.meta"))
    apply_game_patch(BUILD_PROJECT, stock=stock)
    app = PLAYER_STOCK if stock else PLAYER_APP
    log = BUILD_DIR / ("build-stock.log" if stock else "build.log")
    shutil.rmtree(app, ignore_errors=True)
    cmd = [unity, "-batchmode", "-quit", "-projectPath", str(BUILD_PROJECT),
           "-executeMethod", "CreativeRunnerBuild.BuildMac", "-cbjOut", str(app), "-logFile", str(log)]
    proc = subprocess.run(cmd)
    if proc.returncode != 0 or not app.is_dir():
        errors = [ln for ln in log.read_text(errors="replace").splitlines() if "error CS" in ln][:10]
        detail = ("\n" + "\n".join(errors)) if errors else ""
        raise ValueError(f"Unity build failed (exit {proc.returncode}); see {log}{detail}")
    return app
