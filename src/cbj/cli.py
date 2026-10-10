"""Command line: `cbj show|solve|table`.

    uv run cbj show  data/levels/Level_03.json
    uv run cbj solve data/levels/Level_03.json [--json out.json]
    uv run cbj table data/levels [--md reports/solve_table.md]
    uv run cbj check data/levels/Level_03.json data/solutions/Level_03.moves.json

Errors print one line, "cbj: <reason>", and exit with code 1.
"""

from __future__ import annotations

import argparse
import json
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
        if args.scripts:
            out = Path(args.scripts) / f"{level.name}.moves.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(solution_to_script(level, sol), indent=2))
    header = ("level", "grid", "blocks", "min drags", "extra drags", "cells dragged", "timer (s)",
              "states", "ms")
    md = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    md += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    text = "\n".join(md)
    print(text)
    if args.md:
        Path(args.md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.md).write_text(text + "\n")
    if not rows:
        print(f"cbj: no .json level files in {folder}", file=sys.stderr)
    return 0 if not failed and all(r[3] != "UNSOLVABLE" for r in rows) else 1


def _cmd_check(args) -> int:
    level = load_level(args.level)
    path = Path(args.moves)
    if not path.is_file():
        raise ValueError(f"{path}: no such file")
    try:
        script = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise ValueError(f"{path.name}: not valid JSON ({e.msg}, line {e.lineno})") from None
    try:
        drags = script_to_drags(script)
    except ValueError as e:
        raise ValueError(f"{path.name}: {e}") from None
    final = replay(level, drags)
    left = sum(p is not None for p in final)
    if left:
        print(f"{level.name}: {len(drags)} drags are legal, but {left} block(s) are still on the board")
        return 1
    print(f"{level.name}: {len(drags)} drags, all legal, board cleared")
    return 0


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

    s = sub.add_parser("check", help="check a move script against a level, cell by cell")
    s.add_argument("level")
    s.add_argument("moves")
    s.set_defaults(func=_cmd_check)

    s = sub.add_parser("table", help="solve every level in a folder")
    s.add_argument("dir")
    s.add_argument("--md", help="also write the table as markdown")
    s.add_argument("--scripts", help="folder for <level>.moves.json move scripts")
    s.set_defaults(func=_cmd_table)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, OSError, SolverLimitError) as e:
        print(f"cbj: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
