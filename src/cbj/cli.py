"""Command line: `cbj show|solve|table|difficulty|check|build-player|render|scenario|rerun|compare|ad|compose|
ad-diff|plan|make|ui`.

    uv run cbj show  data/levels/Level_03.json
    uv run cbj solve data/levels/Level_03.json [--json out.json]
    uv run cbj table data/levels [--md reports/solve_table.md]
    uv run cbj difficulty data/levels
    uv run cbj check data/levels/Level_03.json data/solutions/Level_03.moves.json
    uv run cbj build-player
    uv run cbj render data/levels/Level_03.json data/solutions/Level_03.moves.json
    uv run cbj plan "a difficult level with a narrow centre where the player almost fails"
    uv run cbj make "the same prompt"   # plan, then make the creative (studio/<id>/v1)
    uv run cbj ui                       # the test UI at http://127.0.0.1:8765

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
          f"random reachable cell it has not had the board in before; {args.runs} runs, seed {args.seed}, gives up "
          f"after 12 drags per block (capped). The mean is over the runs that finished.")
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


def _print_compose(result: dict, out: Path) -> int:
    if not result.get("rendered", True):
        for f in result["qa"]["failures"]:
            print(f"  QA FAILED: {f}")
        print("Nothing was rendered; fix the ad.json and compose again.")
        return 1
    print(f"Ad: {out / 'ad.mp4'} ({result['frames']} frames, {result['duration_s']:.2f} s"
          f"{', draft' if result['draft'] else ''})")
    for sid, seg in result["timeline"].items():
        a, b = seg["frames"]
        print(f"  {sid:9s} {a / 30:6.2f}-{b / 30:6.2f} s  {seg['kind']}")
    for lid, layer in result["layers"].items():
        if layer["text"]:
            a, b = layer["frames"]
            print(f"  {lid:12s} {a / 30:6.2f}-{b / 30:6.2f} s  {layer['text']}")
    print(f"Proof: {out / 'compose.json'} (frame hashes, layer boxes, source hash); poster: {out / 'poster.png'}")
    for w in result["qa"]["warnings"]:
        print(f"  warning: {w}")
    for f in result["qa"]["failures"]:
        print(f"  QA FAILED: {f}")
    return 0 if not result["qa"]["failures"] else 1


def _cmd_ad(args) -> int:
    from .ad import Recording, build_ad
    from .compose import render as compose
    rec = Recording.load(args.recording)
    ad = build_ad(rec, length_s=args.length, allow_long_card=args.allow_long_card)
    out = Path(args.out or f"ads/{rec.path.name}_{args.length:g}s")
    print(f"{rec.path.name}: {ad['concept']} ad, {args.length:g} s. Composing...")
    return _print_compose(compose(ad, out, draft=args.draft), out)


def _cmd_compose(args) -> int:
    from .ad import load_ad
    from .compose import render as compose
    ad = load_ad(args.ad)
    out = Path(args.out)
    if out.resolve() == Path(args.ad).resolve().parent:
        raise ValueError("write the new render to another folder, so the two can be compared")
    print(f"Composing {args.ad}...")
    return _print_compose(compose(ad, out, draft=args.draft), out)


def _cmd_ad_diff(args) -> int:
    from .compose import diff
    d = diff(args.a, args.b, decode=args.decode)
    yes = lambda v: "same" if v else "CHANGED"
    print(f"gameplay sources: {yes(d['same_sources'])}; timeline and camera fit: {yes(d['same_timeline'])}; "
          f"sound: {yes(d['same_sound'])}")
    if d["locked_changed"]:
        print(f"locked parts changed: {', '.join(d['locked_changed'])}"
              + (f" (unlocked on purpose: {', '.join(d['unlocked'])})" if d["unlocked"] else ""))
        if d["locked_violation"]:
            print(f"  NOT ALLOWED: {', '.join(d['locked_violation'])} changed while still locked")
    else:
        print("locked parts: same")
    print(f"layers changed: {', '.join(d['layers_changed']) or 'none'}")
    if d["changed_frames"] is None:
        print(d["note"])
        return 0 if d["ok"] else 1
    fmt = lambda rs: ", ".join(f"{a}-{b}" if a != b else f"{a}" for a, b in rs) or "none"
    n = sum(b - a + 1 for a, b in d["changed_frames"])
    print(f"frames changed: {n} of {d['frames'][0]} ({fmt(d['changed_frames'])})")
    if d["measured_box"]:
        print(f"pixels changed inside {d['measured_box']}; the changed layers cover {d['predicted_box']}: "
              + ("every change is inside them" if d["contained"] else "SOME CHANGES ARE OUTSIDE THEM"))
    if d["same_mp4"]:
        print("MP4: identical files")
        return 0 if d["ok"] else 1
    if n == 0 and d["same_keyframes"]:
        # No frame drew differently and every GOP starts where it did: the encoder saw the same input.
        print("MP4: the video is identical" + ("" if d["same_sound"] else "; only the sound changed"))
    else:
        # A keyframe that moves re-encodes its GOP even when no composited frame changed.
        how = ("same keyframes, so only the GOPs holding a changed frame can differ"
               if d["same_keyframes"] else "keyframes moved (a timing edit), so the video can differ from there on")
        print(f"MP4: {how}: frames {fmt(d['mp4_may_differ'])}")
    if "mp4_differs" in d:
        print(f"MP4 decoded: frames that differ {fmt(d['mp4_differs'])}: "
              + ("all inside those GOPs" if d["mp4_local"] else "SOME OUTSIDE THEM"))
    return 0 if d["ok"] else 1


def _cmd_generate(args) -> int:
    from .generate import BAND_WORDS, Spec, generate
    from .preview import save_board
    spec = Spec(shape=args.shape, width=args.width, height=args.height, blocks=args.blocks, colours=args.colour,
                difficulty=args.difficulty, seed=args.seed, budget_s=args.budget, pieces=args.pieces,
                style=args.style, finish=args.finish)
    d, r, stats = generate(spec, log=print)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(d, indent=2))
    pic = save_board(load_level(out), out.with_suffix(".png"))
    lk = stats["looks"]
    print(f"{out}: {stats['spec']['shape']} {d['gridWidth']}x{d['gridHeight']}, {r.blocks} blocks, {r.min_drags} drags "
          f"minimum ({r.extra_drags} repositioning), {r.exits_at_start} can leave at once, naive player "
          f"{r.naive_ratio:.2f}x -> {BAND_WORDS[stats['band']]}; looks {lk['score']:.2f} (fill {lk['fill']:.0%}"
          f"{', symmetry %.0f%%' % (100 * lk['symmetry']) if 'symmetry' in lk else ''})"
          + (f"; finish {stats['streak']:.0%} of the blocks in a row" if "streak" in stats else "")
          + f"; {stats['seconds']} s, {stats['tried']} tried")
    print(f"Picture: {pic}")
    return 0


def _print_brief(b: dict) -> None:
    from .brief import CONTROL_TITLES
    print(f"Summary: {b['summary']}")
    for c in b["controls"]:
        asked = f'"{c["asked"]}"' if c["asked"] else "(not mentioned)"
        print(f"  {CONTROL_TITLES[c['control']]:40s} {c['status']:13s} {asked}")
        print(f"      -> {c['plan']}")
        if c.get("why"):
            print(f"      why: {c['why']}")
    for a in b.get("assumptions") or []:
        if a and len(a) > 2:
            print(f"  assumed: {a}")
    lv, gp, pc = b["level"], b["gameplay"], b["pacing"]
    print(f"Level: {lv['source']}, shape {lv['shape']}, difficulty {lv['difficulty']}, pieces {lv.get('pieces', 'mixed')}, "
          f"style {lv.get('style') or '-'}; gameplay: {gp['ending']}, finish {gp.get('finish', 'auto')}, "
          f"clock left {gp.get('clock_left_s') or '-'}; pacing: {pc['tempo']}, curve {pc.get('curve', 'even')}")
    if gp.get("events"):
        from .events import describe
        print("Order of interactions: " + " -> ".join(describe(e) for e in gp["events"]))
    p = b.get("planner", {})
    print(f"Planner: {p.get('model')}, {p.get('seconds')} s")


def _cmd_enhance(args) -> None:
    from . import enhance, planner
    planner.load_env()
    r = enhance.enhance(args.prompt, args.upload or [], args.edit, args.base, log=lambda m: print(f"  {m}", file=sys.stderr))
    if args.json:
        Path(args.json).write_text(json.dumps(r, indent=1))
    print(enhance.text(r))


def _cmd_trends(args) -> None:
    from . import planner, trends
    planner.load_env()
    say = lambda m: print(f"  {m}", file=sys.stderr)  # noqa: E731
    if args.link:
        r = trends.from_link(args.link, args.theme, min(args.n, 3), refresh=args.refresh, log=say)
    else:
        r = trends.discover(args.theme, args.region, args.n, refresh=args.refresh, log=say)
    if args.json:
        Path(args.json).write_text(json.dumps(r, indent=1))
    print(trends.text(r))


def _cmd_feedback(args) -> None:
    from . import feedback
    r = feedback.listing(args.creative, args.designer, args.area, args.kind, args.limit)
    if args.md:
        print(feedback.markdown(r["records"]))
        return
    print(f"{r['count']} of {r['total']} records · designers: {', '.join(r['designers']) or '-'}")
    for x in r["records"]:
        s = x.get("scene") or {}
        where = f"{s['creative_id']} v{s['version']}" if s.get("creative_id") else x["page"]
        print(f"  {x['id']}  {x['designer']:<14} {x['kind']:<7} {x['area']:<13} {where}\n      {x['wrong']}" +
              (f"\n      expected: {x['expected']}" if x.get("expected") else ""))


def _cmd_setup_check(args) -> None:
    from . import setup_check
    rows = setup_check.checks(live=args.live)
    print(setup_check.text(rows))
    if not setup_check.ok(rows):
        sys.exit(1)


def _cmd_report(args) -> None:
    from . import report
    text, _ = report.report(args.creative_id, args.base, args.format)
    if args.out:
        Path(args.out).write_text(text)
        print(args.out)
    else:
        print(text)


def _cmd_analyze(args) -> None:
    from . import feedback, planner
    planner.load_env()
    an = feedback.analyze(args.record, log=lambda m: print(f"  {m}", file=sys.stderr))
    print(f"{an['verdict']} ({an['confidence']}) · {an['what_happened']}\nwhy: {an['why']}\nchange: {an['suggested_change']}")
    for e in an["evidence"]:
        print(f"  evidence: {e}")


def _cmd_lessons(args) -> None:
    from . import lessons, planner
    planner.load_env()
    say = lambda m: print(f"  {m}", file=sys.stderr)  # noqa: E731
    if args.correct:
        pkg = lessons.correct(args.correct, log=say)
    elif args.rollback is not None:
        pkg = lessons.rollback(args.rollback)
    elif args.distill:
        pkg = lessons.distill(log=say)
    else:
        pkg = lessons.load(args.version)
    print(lessons.text(pkg))


def _cmd_soundtrack(args) -> None:
    from . import planner, soundtrack
    planner.load_env()
    say = lambda m: print(f"  {m}", file=sys.stderr)  # noqa: E731
    r = soundtrack.make(args.creative_id, args.base, args.voice, args.voice_name, args.line, log=say, narration=args.narration)
    print(soundtrack.text(r))


def _cmd_plan(args) -> int:
    from . import planner, studio
    current, inv = _edit_context(args)
    ups = {n: p for n, p in studio.uploads().items() if n in (args.upload or [])}
    b = planner.plan(args.prompt, uploads=ups, sprites=studio.sprite_names(), current=current,
                     available=studio.uploads(), inventory=inv)
    _print_brief(b)
    if args.json:
        Path(args.json).write_text(json.dumps(b, indent=1))
        print(f"Brief: {args.json}")
    return 0


def _cmd_make(args) -> int:
    from . import planner, studio
    current, inv = _edit_context(args)
    ups = {n: p for n, p in studio.uploads().items() if n in (args.upload or [])}
    if args.brief:
        b = json.loads(Path(args.brief).read_text())
    else:
        b = planner.plan(args.prompt, uploads=ups, sprites=studio.sprite_names(), current=current,
                         available=studio.uploads(), inventory=inv)
    _print_brief(b)
    v = studio.make(args.prompt, b, args.edit, draft=args.draft, base=args.base, allow_missing=args.without_files)
    if getattr(args, "audio", None):
        from . import soundtrack
        parts = {x.strip() for x in args.audio.split(",")}
        v = soundtrack.add_audio(studio.Log(lambda l: print(f"  {l['text']}", file=sys.stderr)), v,
                                 {"bed": "bed" in parts, "voice": "voice" in parts, "line": args.line})
    print(f"Version: studio/{v['id']}/v{v['n']} ({v['length_s']:.2f} s, made in {v['seconds']:.0f} s)")
    print(f"Video: studio/{v['video']}")
    if v.get("proof"):
        _print_report(v["proof"])
    return 0


def _edit_context(args):
    """The brief and the inventory of the version an edit starts from (none for a new ad)."""
    from . import studio
    if not args.edit:
        return None, None
    v = studio.parent(args.edit, args.base)
    if v is None:
        raise ValueError(f"no creative {args.edit}")
    return v["brief"], studio.planner_context(args.edit, v["n"])


def _print_report(r: dict) -> None:
    from .editreport import STATUS_WORDS
    print(r["verdict"])
    for row in r["rows"]:
        print(f"  {row['title']:17} {STATUS_WORDS[row['status']]}: {row['detail']}")
        for n in row.get("reasons", []):
            print(f"  {'':17}   engine: {n}")
    px = r.get("pixels") or {}
    if "frames_changed" in px:
        print(f"  frames changed: {px['frames_changed']} of {px['frames']} {px.get('ranges', '')}"
              + ("" if px.get("contained") is not False else " (SOME PIXELS OUTSIDE THE CHANGED LAYERS)"))
    elif px.get("note"):
        print(f"  frames: {px['note']}")


def _cmd_review(args) -> int:
    from . import review, studio
    v = studio.parent(args.creative, args.n)
    if v is None or (args.n is not None and v.get("n") != args.n):
        print(f"no version {args.n} of {args.creative}")
        return 1
    r = review.review(v, v["prompt"], studio.STUDIO, log=lambda m: print("  " + m), edit_of=v.get("proof"))
    print(f"Review of v{v['n']} ({r['model']}, {r['seconds']} s): {review.summary(r)}")
    for m in r["match"]:
        print(f"  {m['verdict']:9} {m['control']}: {m['seen']}")
    print(f"  Would download: {r['would_download']}: {r['why']}")
    for i, fx in enumerate(r["fixes"], 1):
        print(f"  Fix {i}: {fx}")
    if r["suggested_edit"]:
        print(f"  Suggested edit: {r['suggested_edit']}")
    print(f"  Written: studio/{v['id']}/v{v['n']}/review.json (sheet: {r['sheet']})")
    return 0


def _cmd_edit_report(args) -> int:
    from . import brief as B
    from . import studio
    from .editreport import report
    va, vb = studio.parent(args.creative, args.a), studio.parent(args.creative, args.b)
    if va is None or vb is None:
        raise ValueError(f"no creative {args.creative}")
    direct = vb.get("from") == va["n"]
    _print_report(report(va, vb, studio.STUDIO, vb["brief"].get("changed", []) if direct
                         else B.changed_groups(va["brief"], vb["brief"]), compare=not direct))
    return 0


def _cmd_ui(args) -> int:
    from .app import serve
    serve(port=args.port)
    return 0


def _cmd_rerun(args) -> int:
    from .render import compare_recordings, rerun
    print(f"Recording {args.folder} again into {args.out} from its job.json and level.json...")
    result = rerun(args.folder, args.out)
    print(f"Status: {result['status']} {result['message']}".rstrip())
    print(f"Video: {result['video']} ({result['frames']} frames, {result['duration_s']:.2f} s)")
    c = compare_recordings(args.folder, args.out)
    print("game state against the original: " + ("identical" if c["state_equal"] else
          f"DIFFERENT (first frames: {c['state_diff_frames']})"))
    print(f"identical frames: {c['identical_frames']} of {min(c['frames'])}")
    for p in result["problems"]:
        print(f"  PROBLEM: {p}")
    return 0 if c["state_equal"] and not result["problems"] else 1


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
    from .events import from_brief
    events, ev_notes = from_brief(level, json.loads(args.events)) if args.events else ([], [])
    script = plan(level, args.ending, mistakes=args.mistakes, seed=args.seed, left=args.left,
                  hesitations=args.hesitations, events=events, finish=args.finish, curve=args.curve,
                  clock_left=args.clock_left)
    script.notes[:0] = ev_notes
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
        if args.length is not None:
            print("  note: --length is fitted after the dry run, so these are the pauses before fitting")
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
    p = argparse.ArgumentParser(prog="cbj", description="CBJ level tools")
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
                   help="build the game as shipped, without the game patch (build/CBJRunner-stock.app)")
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
    s.add_argument("--events", help='the order of interactions, as in the brief: a JSON list like '
                                    '\'[{"block": {"colour": "Red", "which": "any", "all": false}, "action": "moves", '
                                    '"when": "first"}]\'')
    s.add_argument("--finish", choices=["auto", "streak"], default="auto",
                   help="streak: one key move, then every block leaves one after another")
    s.add_argument("--curve", choices=["even", "speeds_up", "slows_down"], default="even", help="pacing over the video")
    s.add_argument("--clock-left", type=int, default=1, help="near_fail: seconds on the clock at the last exit (1-3)")
    s.add_argument("--plan-only", action="store_true", help="print the beats, do not start Unity")
    s.add_argument("--hide", action="append", metavar="NAME",
                   help="hide another game object (RestartButton is always hidden)")
    s.add_argument("-o", "--out", help="output folder (default: renders/<level>_<ending>)")
    s.set_defaults(func=_cmd_scenario)

    s = sub.add_parser("generate", help="generate a level to a spec: shape, size, pieces, looks, difficulty")
    s.add_argument("--shape", default="any", choices=["any", "open", "narrow_center", "door", "holes", "cross", "ring",
                                                      "lanes"])
    s.add_argument("--difficulty", default="medium", choices=["easy", "medium", "hard"])
    s.add_argument("--width", type=int)
    s.add_argument("--height", type=int)
    s.add_argument("--blocks", type=int)
    s.add_argument("--pieces", default="mixed", choices=["mixed", "small", "big", "long"])
    s.add_argument("--style", action="append", choices=["symmetric", "packed", "colourful"], default=[])
    s.add_argument("--colour", action="append", default=[], help="a game colour the level uses (repeatable)")
    s.add_argument("--finish", choices=["auto", "streak"], default="auto",
                   help="streak: prefer boards where one move lets every block leave in a row")
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--budget", type=float, default=25.0, help="seconds of search")
    s.add_argument("-o", "--out", required=True, help="the level file to write (.json); a picture is written next to it")
    s.set_defaults(func=_cmd_generate)

    s = sub.add_parser("ad", help="make a finished ad (hook, captions, cursor, replay, sound, end card) from a recording")
    s.add_argument("recording", help="a `cbj scenario` folder")
    s.add_argument("--length", type=float, default=30, help="ad length in seconds (default 30)")
    s.add_argument("--draft", action="store_true", help="fast, lower-quality encode for checking")
    s.add_argument("--allow-long-card", action="store_true",
                   help="accept an end card over 8 s when the recording is short for the length")
    s.add_argument("-o", "--out", help="output folder (default: ads/<recording>_<length>s)")
    s.set_defaults(func=_cmd_ad)

    s = sub.add_parser("compose", help="render an ad.json (for example an edited one) into a finished ad")
    s.add_argument("ad", help="an ad.json")
    s.add_argument("-o", "--out", required=True, help="output folder")
    s.add_argument("--draft", action="store_true")
    s.set_defaults(func=_cmd_compose)

    s = sub.add_parser("ad-diff", help="what changed between two renders of an ad (the edit proof)")
    s.add_argument("a", help="the original render folder")
    s.add_argument("b", help="the edited render folder")
    s.add_argument("--decode", action="store_true", help="also decode both MP4s and check the video itself")
    s.set_defaults(func=_cmd_ad_diff)

    s = sub.add_parser("rerun", help="record a finished recording again from its folder, and compare")
    s.add_argument("folder", help="a recording folder (job.json, result.json, level.json)")
    s.add_argument("-o", "--out", required=True, help="a new folder for the second recording")
    s.set_defaults(func=_cmd_rerun)

    s = sub.add_parser("compare", help="compare two recordings: game state, frames, PSNR")
    s.add_argument("a")
    s.add_argument("b")
    s.set_defaults(func=_cmd_compare)

    s = sub.add_parser("plan", help="read a prompt into a creative brief (the LLM planner), and print it")
    s.add_argument("prompt")
    s.add_argument("--edit", metavar="CREATIVE", help="plan an edit of this creative's latest version")
    s.add_argument("--base", type=int, metavar="N", help="edit version N instead of the latest")
    s.add_argument("--upload", action="append", metavar="NAME", help="an uploaded file (studio/uploads) to offer")
    s.add_argument("--json", help="also write the brief to this file")
    s.set_defaults(func=_cmd_plan)

    s = sub.add_parser("enhance", help="rewrite a prompt in the planner's words, adding nothing (questions for the rest)")
    s.add_argument("prompt")
    s.add_argument("--edit", metavar="CREATIVE", help="the prompt is an edit of this creative's latest version")
    s.add_argument("--base", type=int, metavar="N", help="edit version N instead of the latest")
    s.add_argument("--upload", action="append", metavar="NAME", help="an uploaded file (studio/uploads) the prompt attaches")
    s.add_argument("--json", help="also write the result to this file")
    s.set_defaults(func=_cmd_enhance)

    s = sub.add_parser("trends", help="ideas from what is trending now, as prompts the engine can make (needs TAVILY_API_KEY)")
    s.add_argument("--theme", help="prefer trends that fit this theme (e.g. 'halloween', 'football')")
    s.add_argument("--region", default="US", help="Google Trends region code (default US)")
    s.add_argument("-n", type=int, default=4, help="how many ideas (1-6)")
    s.add_argument("--refresh", action="store_true", help="ignore the cache")
    s.add_argument("--link", metavar="URL", help="ideas from one public link instead of the trend feeds (the page is the only signal)")
    s.add_argument("--json", help="also write the result to this file")
    s.set_defaults(func=_cmd_trends)

    s = sub.add_parser("feedback", help="designers' feedback records (feedback.py): list or export")
    s.add_argument("--creative"); s.add_argument("--designer"); s.add_argument("--area"); s.add_argument("--kind")
    s.add_argument("--limit", type=int, default=100); s.add_argument("--md", action="store_true", help="print as Markdown")
    s.set_defaults(func=_cmd_feedback)

    s = sub.add_parser("setup-check", help="is this machine ready to run the studio on its own accounts? (Claude CLI login, Gemini key, ffmpeg, the player)")
    s.add_argument("--live", action="store_true", help="also make one tiny call to the planner and to Gemini")
    s.set_defaults(func=_cmd_setup_check)
    s = sub.add_parser("report", help="the report of one version: the request, how it was read, every step, the checks, the edit report (report.py)")
    s.add_argument("creative_id")
    s.add_argument("--base", type=int, default=None, help="the version (default: the latest)")
    s.add_argument("--format", choices=("md", "html"), default="md")
    s.add_argument("--out", default=None, help="write the report to this file instead of stdout")
    s.set_defaults(func=_cmd_report)
    s = sub.add_parser("analyze-feedback", help="what happened behind one feedback record, from the version's own process (feedback.analyze)")
    s.add_argument("record", help="the record id (fb-...)")
    s.set_defaults(func=_cmd_analyze)
    s = sub.add_parser("lessons", help="the feedback distilled into a versioned LESSONS.md (lessons.py)")
    s.add_argument("--distill", action="store_true", help="distil a new version from the records")
    s.add_argument("--correct", metavar="TEXT", help="record a correction in your words and distil again")
    s.add_argument("--rollback", type=int, metavar="N", help="make version N the current one")
    s.add_argument("--version", type=int, help="print version N instead of the current one")
    s.set_defaults(func=_cmd_lessons)

    s = sub.add_parser("soundtrack", help="optional: a music bed from a version's own concept (+ the hook spoken by NVIDIA Magpie)")
    s.add_argument("creative_id"); s.add_argument("--base", type=int, help="the version (default: the latest)")
    s.add_argument("--voice", action="store_true", help="speak the hook (needs `uv sync --extra voice` and NVIDIA_API_KEY)")
    s.add_argument("--voice-name", help="a Magpie voice, e.g. Magpie-Multilingual.EN-US.Jason.Happy")
    s.add_argument("--line", help="the words to speak instead of the hook caption")
    s.add_argument("--narration", choices=("captions", "hook"), default="captions", help="every caption as it appears (default) or the hook alone")
    s.set_defaults(func=_cmd_soundtrack)

    s = sub.add_parser("make", help="plan a prompt and make the creative (or edit one with --edit)")
    s.add_argument("prompt")
    s.add_argument("--edit", metavar="CREATIVE", help="make a new version of this creative")
    s.add_argument("--base", type=int, metavar="N", help="edit version N instead of the latest")
    s.add_argument("--upload", action="append", metavar="NAME")
    s.add_argument("--brief", help="use this brief.json instead of planning (no LLM call)")
    s.add_argument("--draft", action="store_true")
    s.add_argument("--without-files", action="store_true", help="make it although the prompt names files that are not attached")
    s.add_argument("--audio", metavar="bed,voice", help="optional: add a soundtrack after the make ('bed', 'voice' or 'bed,voice'; the hook spoken by NVIDIA Magpie)")
    s.add_argument("--line", help="with --audio voice: the words to speak instead of the hook caption")
    s.set_defaults(func=_cmd_make)

    s = sub.add_parser("edit-report", help="what changed between two versions of a creative, item by item")
    s.add_argument("creative")
    s.add_argument("a", type=int, help="the earlier version (number)")
    s.add_argument("b", type=int, help="the later version")
    s.set_defaults(func=_cmd_edit_report)

    s = sub.add_parser("review", help="the viewer's review of a version: does it match the prompt, would a viewer tap")
    s.add_argument("creative")
    s.add_argument("n", type=int, nargs="?", help="the version (default: the latest)")
    s.set_defaults(func=_cmd_review)

    s = sub.add_parser("ui", help="the test UI: prompts in, creatives out (http://127.0.0.1:8765)")
    s.add_argument("--port", type=int, default=8765)
    s.set_defaults(func=_cmd_ui)

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
