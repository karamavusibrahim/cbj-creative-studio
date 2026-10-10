"""Command line: `cbj show|solve|table|difficulty|check|build-player|render|compare`.

    uv run cbj show  data/levels/Level_03.json
    uv run cbj solve data/levels/Level_03.json [--json out.json]
    uv run cbj table data/levels [--md reports/solve_table.md]
    uv run cbj difficulty data/levels
    uv run cbj check data/levels/Level_03.json data/solutions/Level_03.moves.json
    uv run cbj build-player
    uv run cbj render data/levels/Level_03.json data/solutions/Level_03.moves.json

Errors print one line, "cbj: <reason>", and exit with code 1.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

from .describe import block_labels, describe_drag, render, script_to_drags, shape_name, solution_to_script
from .level import load_level
from .rules import initial_state
from .solver import SolverLimitError, apply_drag, replay, solve


def _cmd_show(args) -> int:
    level = load_level(args.level)
    print(f"{level.name}: {level.width}x{level.height}, timer {level.timer}s, "
          f"{len(level.blocks)} blocks, {len(level.exits)} gates")
    print(render(level, initial_state(level)))
    return 0


def _cmd_solve(args) -> int:
    level = load_level(args.level)
    t0 = time.perf_counter()
    sol = solve(level)
    dt = time.perf_counter() - t0
    if sol is None:
        print(f"{level.name}: UNSOLVABLE")
        return 1
    replay(level, sol.drags)  # raises if the solution breaks any rule
    labels = block_labels(level)
    print(f"{level.name}: solved in {sol.min_drags} drags "
          f"({sol.blocks} blocks + {sol.extra_drags} repositioning), "
          f"{sol.states_explored} states, {dt * 1000:.1f} ms. Replay check: OK")
    state = initial_state(level)
    print("\nStart:")
    print(render(level, state))
    for k, d in enumerate(sol.drags, start=1):
        print(f"\nStep {k}. {describe_drag(level, d, labels)}")
        state = apply_drag(state, d)
        print(render(level, state))
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(solution_to_script(level, sol), indent=2))
        print(f"\nMove script written to {args.json}")
    return 0


def _cmd_table(args) -> int:
    folder = Path(args.dir)
    if not folder.is_dir():
        raise ValueError(f"{folder}: no such folder")
    rows = []
    scripts = []
    failed = False
    for path in sorted(folder.glob("*.json")):
        try:
            level = load_level(path)
            t0 = time.perf_counter()
            sol = solve(level)
        except (ValueError, SolverLimitError) as e:
            # One bad file must not hide the results for the others.
            print(f"cbj: {e}", file=sys.stderr)
            rows.append((path.stem, "-", "-", "ERROR", "-", "-", "-", "-", "-"))
            failed = True
            continue
        dt = (time.perf_counter() - t0) * 1000
        if sol is None:
            rows.append((level.name, f"{level.width}x{level.height}", len(level.blocks), "UNSOLVABLE",
                         "-", "-", level.timer, "-", f"{dt:.0f}"))
            continue
        replay(level, sol.drags)
        shapes = ", ".join(sorted({shape_name(level, i) for i in range(len(level.blocks))}))
        rows.append((level.name, f"{level.width}x{level.height}", len(level.blocks), sol.min_drags,
                     sol.extra_drags, sol.cells_dragged, level.timer, sol.states_explored, f"{dt:.0f}"))
        scripts.append((level, sol))
    header = ("level", "grid", "blocks", "min drags", "extra drags", "cells dragged", "timer (s)",
              "states", "ms")
    md = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    md += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    text = "\n".join(md)
    print(text)
    # Files are written after the table is printed, so a write error cannot hide the results.
    if args.scripts:
        for level, sol in scripts:
            out = Path(args.scripts) / f"{level.name}.moves.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(solution_to_script(level, sol), indent=2))
    if args.md:
        Path(args.md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.md).write_text(text + "\n")
    if not rows:
        print(f"cbj: no .json level files in {folder}", file=sys.stderr)
    return 0 if not failed and all(r[3] != "UNSOLVABLE" for r in rows) else 1


def _load_moves(level, moves_path) -> list:
    path = Path(moves_path)
    if not path.is_file():
        raise ValueError(f"{path}: no such file")
    try:
        script = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise ValueError(f"{path.name}: not valid JSON ({e.msg}, line {e.lineno})") from None
    if isinstance(script, dict):
        want = {"width": level.width, "height": level.height}
        if script.get("level") not in (None, level.name) or script.get("grid", want) != want:
            g = script.get("grid") or {}
            raise ValueError(f"{path.name}: this script is for {script.get('level')} "
                             f"({g.get('width')}x{g.get('height')}), not {level.name} ({level.width}x{level.height})")
    try:
        return script_to_drags(script)
    except ValueError as e:
        raise ValueError(f"{path.name}: {e}") from None


def _cmd_difficulty(args) -> int:
    from .difficulty import rate
    target = Path(args.path)
    paths = sorted(target.glob("*.json")) if target.is_dir() else [target]
    if not paths or not paths[0].exists():
        raise ValueError(f"{target}: no such level file or folder")
    header = ("level", "blocks", "min drags", "extra drags", "exits at start", "first-drag options",
              "naive player: mean drags", "p90", "capped", "mean / min")
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for path in paths:
        level = load_level(path)
        d = rate(level, runs=args.runs, seed=args.seed)
        if d is None:
            lines.append(f"| {level.name} | {len(level.blocks)} | UNSOLVABLE |" + " - |" * 7)
            continue
        lines.append(f"| {d.level_name} | {d.blocks} | {d.min_drags} | {d.extra_drags} | {d.exits_at_start} | "
                     f"{d.first_moves} | {d.naive_mean:.1f} | {d.naive_p90} | {d.naive_capped} | {d.naive_ratio:.2f} |")
    print("\n".join(lines))
    print(f"\nNaive player: takes an exit when one is available, otherwise drags a random block to a "
          f"random reachable cell; {args.runs} runs, seed {args.seed}, capped at 200 drags.")
    return 0


def _cmd_check(args) -> int:
    level = load_level(args.level)
    drags = _load_moves(level, args.moves)
    final = replay(level, drags)
    left = sum(p is not None for p in final)
    if left:
        print(f"{level.name}: {len(drags)} drags are legal, but {left} block(s) are still on the board")
        return 1
    print(f"{level.name}: {len(drags)} drags, all legal, board cleared")
    return 0


def _cmd_build_player(args) -> int:
    from .render import build_player
    kind = "the stock game (no game patch)" if args.stock else "the runner player"
    print(f"Copying {args.project} into build/ and building {kind} (about a minute)...")
    app = build_player(Path(args.project), args.unity, stock=args.stock)
    print(f"Player built: {app}")
    return 0


def _size(text: str) -> tuple[int, int]:
    try:
        w, h = (int(v) for v in text.lower().split("x"))
    except ValueError:
        raise argparse.ArgumentTypeError(f"size must look like 1080x1920, got {text!r}") from None
    return w, h


def _cmd_render(args) -> int:
    from .render import PLAYER_STOCK, Camera, Pacing, make_job, run_player
    level = load_level(args.level)
    if args.moves:
        drags = _load_moves(level, args.moves)
    else:
        sol = solve(level)
        if sol is None:
            raise ValueError(f"{level.name}: unsolvable, nothing to render")
        drags = sol.drags
    if args.drags is not None:
        if args.drags < 1:
            raise ValueError("--drags must be 1 or more")
        drags = drags[: args.drags]
    out = Path(args.out or f"renders/{level.name}")
    pacing = Pacing(fps=args.fps, cells_per_s=args.speed, start_hold_s=args.start_hold,
                    pause_before_s=args.pause, end_hold_s=args.end_hold)
    camera = (Camera.intro(args.zoom, 0.0, args.pan_y, seconds=args.start_hold or 1.0)
              if args.intro else Camera(args.zoom, 0.0, args.pan_y))
    job = make_job(level, args.level, drags, out, pacing, end_mode=args.end, size=args.size, camera=camera,
                   timer=args.timer, hide=tuple(args.hide or ()), stop_clock_on_last_exit=not args.stock,
                   capture=not args.dry_run)
    doing = "Dry run (timing only, no video)" if args.dry_run else "Recording"
    print(f"{level.name}: {len(drags)} drags, end mode '{args.end}'. {doing} in Unity...")
    t0 = time.perf_counter()
    result = run_player(job, app=PLAYER_STOCK if args.stock else None)
    dt = time.perf_counter() - t0
    print(f"Status: {result['status']} {result['message']}".rstrip())
    if args.dry_run:
        print(f"Dry run: {result['frames']} frames, {result['duration_s']:.2f} s at {result['fps']} fps "
              f"(the same frames a recording would have), in {dt:.0f} s; timing in {out / 'frames.json'}")
    else:
        print(f"Video: {result['video']} ({result['frames']} frames, {result['duration_s']:.2f} s "
              f"at {result['fps']} fps, {result['width']}x{result['height']}), recorded in {dt:.0f} s")
    labels = block_labels(level)
    for d in result["drags"]:
        start, end = d["start_frame"] / result["fps"], max(d["end_frame"], 0) / result["fps"]
        print(f"  drag {d['index'] + 1}: block {labels[d['block']]}, {len(d['cells'])} cells, "
              f"{d['result']}, {start:.2f}-{end:.2f} s, timer {_clock(d['timer_start'])} -> {_clock(d['timer_end'])}")
    if result["win_frame"] >= 0:
        print(f"  win screen at {result['win_frame'] / result['fps']:.2f} s, timer {_clock(result['timer_end'])}")
    for p in result["problems"]:
        print(f"  PROBLEM: {p}")
    return 0 if not result["problems"] else 1


def _cmd_compare(args) -> int:
    from .render import compare_recordings
    for d in (args.a, args.b):
        if not (Path(d) / "result.json").is_file():
            raise ValueError(f"{d}: no recording (result.json) there")
    c = compare_recordings(args.a, args.b)
    na, nb = c["frames"]
    print(f"frames: {na} vs {nb}")
    print("game state (timer, finger, drags, ending): " + ("identical" if c["state_equal"] else
          f"DIFFERENT (first frames: {c['state_diff_frames']})"))
    print("finger on screen: " + ("same path" if c["finger_path_equal"] else
          "different path (the camera or video size changed)"))
    print(f"identical frames: {c['identical_frames']} of {min(na, nb)}")
    if c["min_psnr_db"] is not None:
        low = "inf (all identical)" if c["min_psnr_db"] == float("inf") else f"{c['min_psnr_db']:.1f} dB"
        print(f"lowest frame PSNR: {low}" + (f", worst frames {c['worst_frames']}" if c["worst_frames"] else ""))
    return 0 if c["state_equal"] else 1


def _cmd_scenario(args) -> int:
    from .difficulty import rate
    from .play import END_MODE, plan, run, time_out_allowed
    from .render import level_label
    level = load_level(args.level)
    d = rate(level)
    if args.ending == "time_out":
        if not args.allow_fail:
            raise ValueError("a time-out ending is opt-in (social tests or an explicit fail request); "
                             "add --allow-fail")
        ok, why = time_out_allowed(d)
        if not ok:
            raise ValueError(f"{level.name} is too easy for a believable time-out: {why}")
    script = plan(level, args.ending, mistakes=args.mistakes, seed=args.seed, left=args.left,
                  hesitations=args.hesitations)
    labels = block_labels(level)
    n_mistakes = sum(b.kind == "mistake" for b in script.beats)
    print(f"{level.name}: {args.ending} ({END_MODE[args.ending]} ending), {n_mistakes} mistake(s), seed {args.seed}")
    if d is not None:
        print(f"  difficulty: {d.min_drags} drags minimum ({d.extra_drags} repositioning), naive player "
              f"{d.naive_mean:.1f} drags ({d.naive_ratio:.2f}x)")
    for k, b in enumerate(script.beats, start=1):
        extra = f", push {b.push_cells} + hold {b.hold_f} f" if b.push_cells else ""
        print(f"  {k:2d}. {b.kind:8s} {labels[b.drag.block]:3s} pause {b.pause:14s} {b.pause_f:2d} f, "
              f"{b.frames_per_cell} f/cell{extra}  {b.note}")
    label = args.label if args.label is not None else level_label(level)
    for n in script.notes:
        print(f"  note: {n}")
    if args.label is None and not re.fullmatch(r"Level_\d+", level.name):
        print(f"  note: the HUD will show \"Level {label}\" (from the file name); set --label for the "
              f"number the ad should show")
    if args.plan_only:
        return 0
    out = Path(args.out or f"renders/{level.name}_{args.ending}")
    print("Dry run, fit (pauses only), then recording in Unity...")
    result = run(level, args.level, script, out, length_s=args.length, difficulty=d, label=label,
                 hide=("RestartButton", *(args.hide or ())))
    m, fit = script.measured, script.fit
    timer = f"{script.timer_s} s" if script.timer_s is not None else "the level's own"
    print(f"Status: {result['status']} {result['message']}".rstrip())
    print(f"Video: {result['video']} ({m['frames']} frames, {m['duration_s']:.2f} s); clock {timer}, "
          f"{m['clock_left_s']:.2f} s left at the end")
    changed = sum(1 for c in fit["pause_changes_f"] if c)
    print(f"Fit: dry run {fit['dry_frames']} frames, {changed} pause(s) changed "
          f"({sum(fit['pause_changes_f']):+d} frames); recording matched the prediction"
          if not any("predicted" in p for p in result["problems"]) else "Fit: see problems")
    print(f"Script: {out / 'play.json'}")
    for p in result["problems"]:
        print(f"  PROBLEM: {p}")
    return 0 if not result["problems"] else 1


def _clock(seconds: float) -> str:
    s = max(0, int(seconds))
    return f"{s // 60:02d}:{s % 60:02d}"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="cbj", description="Color Block Jam level tools")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("show", help="draw a level")
    s.add_argument("level")
    s.set_defaults(func=_cmd_show)

    s = sub.add_parser("solve", help="minimum-drag solution with step-by-step boards")
    s.add_argument("level")
    s.add_argument("--json", help="write the move script for the Unity replay")
    s.set_defaults(func=_cmd_solve)

    s = sub.add_parser("difficulty", help="how hard a level is: minimum solution and a simulated naive player")
    s.add_argument("path", help="a level file or a folder of them")
    s.add_argument("--runs", type=int, default=200)
    s.add_argument("--seed", type=int, default=0)
    s.set_defaults(func=_cmd_difficulty)

    s = sub.add_parser("check", help="check a move script against a level, cell by cell")
    s.add_argument("level")
    s.add_argument("moves")
    s.set_defaults(func=_cmd_check)

    s = sub.add_parser("build-player", help="build the Unity player that records move scripts")
    s.add_argument("--project", default=str(Path(__file__).resolve().parents[3] / "CBJ"),
                   help="the Unity project to copy (default: ../CBJ)")
    s.add_argument("--unity", default="/Applications/Unity/Hub/Editor/6000.3.5f1/Unity.app/Contents/MacOS/Unity")
    s.add_argument("--stock", action="store_true",
                   help="build the game as Rollic shipped it, without the game patch (build/CBJRunner-stock.app)")
    s.set_defaults(func=_cmd_build_player)

    s = sub.add_parser("render", help="record a move script in the real game as a 9:16 video")
    s.add_argument("level")
    s.add_argument("moves", nargs="?", help="move script (default: solve the level)")
    s.add_argument("-o", "--out", help="output folder (default: renders/<level>)")
    s.add_argument("--end", choices=["win", "cut", "fail"], default="win",
                   help="win: play to the win screen; cut: stop after the last drag; "
                        "fail: wait for the timer to run out")
    s.add_argument("--drags", type=int, help="play only the first N drags (use with --end cut)")
    s.add_argument("--fps", type=int, default=30)
    s.add_argument("--speed", type=float, default=6.0, help="finger speed in cells per second")
    s.add_argument("--size", type=_size, default=(1080, 1920), help="video size, default 1080x1920")
    s.add_argument("--start-hold", type=float, default=1.0, help="seconds on the board before the first touch")
    s.add_argument("--pause", type=float, default=0.45, help="seconds between drags")
    s.add_argument("--end-hold", type=float, default=2.5, help="seconds after the ending")
    s.add_argument("--zoom", type=float, default=1.0, help="1 = the game's framing, 1.2 = 20%% closer")
    s.add_argument("--pan-y", type=float, default=0.0, help="move the view up (+) or down (-) the board, in cells")
    s.add_argument("--intro", action="store_true", help="start pulled back and ease in, like the game's level start")
    s.add_argument("--timer", type=int, help="seconds on the game clock (default: the level's own)")
    s.add_argument("--stock", action="store_true",
                   help="record with the stock game (cbj build-player --stock), which keeps its clock "
                        "running during the last exit slide and can show both endings")
    s.add_argument("--hide", action="append", metavar="NAME",
                   help="hide a game object by name, e.g. RestartButton (repeatable)")
    s.add_argument("--dry-run", action="store_true",
                   help="play and log the timing (frames.json, result.json) without filming; a few seconds")
    s.set_defaults(func=_cmd_render)

    s = sub.add_parser("scenario", help="human-looking play toward an ending (win, near-fail, ...), recorded")
    s.add_argument("level")
    s.add_argument("--ending", choices=["win", "near_fail", "cliffhanger", "time_out"], default="near_fail")
    s.add_argument("--mistakes", type=int, help="believable mistakes, 0-3 (default 1 for near_fail and time_out)")
    s.add_argument("--hesitations", type=int, help="pick a block up and put it back (default 2 for near_fail)")
    s.add_argument("--seed", type=int, default=0, help="picks the mistakes and hesitations; nothing else")
    s.add_argument("--left", type=int, help="blocks left at a cliffhanger's cut (default 2)")
    s.add_argument("--length", type=float, help="video length in seconds, reached by changing pauses only")
    s.add_argument("--label", type=int, help="the number in the HUD's Level badge (default: from the file name)")
    s.add_argument("--allow-fail", action="store_true",
                   help="required for time_out (opt-in, social tests; hard levels only)")
    s.add_argument("--plan-only", action="store_true", help="print the beats, do not start Unity")
    s.add_argument("--hide", action="append", metavar="NAME",
                   help="hide another game object (RestartButton is always hidden)")
    s.add_argument("-o", "--out", help="output folder (default: renders/<level>_<ending>)")
    s.set_defaults(func=_cmd_scenario)

    s = sub.add_parser("compare", help="compare two recordings: game state, frames, PSNR")
    s.add_argument("a")
    s.add_argument("b")
    s.set_defaults(func=_cmd_compare)

    s = sub.add_parser("table", help="solve every level in a folder")
    s.add_argument("dir")
    s.add_argument("--md", help="also write the table as markdown")
    s.add_argument("--scripts", help="folder for <level>.moves.json move scripts")
    s.set_defaults(func=_cmd_table)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, OSError, SolverLimitError, RecursionError, subprocess.SubprocessError) as e:
        print(f"cbj: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
