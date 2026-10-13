"""Gameplay checks: did the recording do what the brief asked for?

Everything about the play is read from the recording (result.json: which block each drag moved,
the cells it entered, whether it left; the clock; the frames), not from the plan. Facts about the
board (difficulty, shape, looks) are read from the level file. Each check says where it was
measured: "recording" or "level".

Status: pass (done as asked), adjusted (done differently, with the reason), failed (asked for and
not done), info (a measured fact, nothing was asked).
"""

from __future__ import annotations

import json
from pathlib import Path

from .describe import block_labels, color_name
from .events import SOLVER_ACTIONS, check_events, from_brief, trailing_exits
from .level import Level, load_level
from .rules import initial_state
from .solver import Drag, apply_drag

FPS = 30


def _recorded_drags(level: Level, result: dict) -> list[Drag]:
    """The drags as the game played them: each block's path from where it stood through the cells
    it entered, and whether it left."""
    state = initial_state(level)
    out = []
    for d in result["drags"]:
        b = d["block"]
        start = state[b]
        cells = tuple((c["x"], c["y"]) for c in d.get("cells", []))
        drag = Drag(b, (start,) + cells, d.get("result") == "exit", d.get("exit_index") if d.get("exit_index", -1) >= 0 else None)
        out.append(drag)
        state = apply_drag(state, drag) if d.get("result") != "interrupted" else state
    return out


def gameplay_checks(brief: dict, rec_dir: Path, level_path: Path) -> list[dict]:
    rec_dir, level_path = Path(rec_dir), Path(level_path)
    level = load_level(level_path)
    play = json.loads((rec_dir / "play.json").read_text())
    result = json.loads((rec_dir / "result.json").read_text())
    beats, rdrags = play["beats"], result["drags"]
    labels = block_labels(level)
    gp, pc, lv = brief["gameplay"], brief["pacing"], brief["level"]
    out: list[dict] = []

    def add(check, status, detail, source="recording"):
        out.append({"check": check, "status": status, "detail": detail, "from": source})

    def name(bid):
        return f"{labels[bid]} ({color_name(level.blocks[bid].color)})"

    # 1. The game played the planned drags: the same block, the same cells, the same outcome.
    wrong = []
    for k, (b, r) in enumerate(zip(beats, rdrags), start=1):
        want = "interrupted" if b["kind"] == "short" else ("exit" if b["exits"] else "placed")
        cells = [[c["x"], c["y"]] for c in r.get("cells", [])]
        planned_cells = b["path"][1:]
        if r["block"] != b["block"] or r.get("result") != want or (want != "interrupted" and cells != planned_cells):
            wrong.append(k)
    if len(rdrags) != len(beats):
        add("Planned moves", "failed", f"{len(rdrags)} drags recorded, {len(beats)} planned; nothing else can be "
                                       f"checked against this recording")
        return out
    elif wrong:
        add("Planned moves", "failed", f"drag(s) {', '.join(map(str, wrong[:5]))} differ from the plan")
    else:
        add("Planned moves", "pass", f"all {len(beats)} drags played as planned: the same block, cells and outcome")

    drags = _recorded_drags(level, result)
    kinds = [b["kind"] for b in beats]
    gone = sum(1 for g in result.get("block_gone_frames", []) if g >= 0)
    left = len(level.blocks) - gone
    clock = result.get("timer_end", -1)

    # 2. The ending, from the game's own status and clock.
    ending = gp["ending"]
    status = result.get("status")
    if ending in ("win", "near_fail"):
        ok = status == "cleared" and left == 0
        detail = f"the game shows a cleared board with {int(clock) // 60:02d}:{int(clock) % 60:02d} on the clock"
        if ending == "near_fail":
            want_s = gp.get("clock_left_s") or 1
            ok = ok and int(clock) == want_s
            detail += f" (asked: 00:0{want_s} at the last exit)"
        add("Ending", "pass" if ok else "failed", detail)
    elif ending == "cliffhanger":
        add("Ending", "pass" if status == "unresolved" and left == play.get("left") else "failed",
            f"the video stops with {left} block(s) left and {clock:.0f} s on the clock")
    else:
        add("Ending", "pass" if status == "failed" and left == 1 else "failed",
            f"the clock runs out with {left} block(s) left; the last drag "
            f"{'was cut short' if rdrags and rdrags[-1].get('result') == 'interrupted' else 'was not cut short'}")

    # 3. Mistakes and hesitations, as played.
    made = [k for k, b in enumerate(beats) if b["kind"] == "mistake" and rdrags[k].get("result") == "placed"]
    asked = gp["mistakes"]
    if asked is not None or made:
        want = asked if asked is not None else "the ending's default"
        st = "pass" if asked is None or len(made) == asked else "adjusted"
        detail = f"{len(made)} mistake(s) played (asked: {want})"
        if made:
            detail += ": " + "; ".join(f"drag {k + 1}, {beats[k]['note']}" for k in made[:3])
        add("Mistakes", st, detail)

    # 4. The requested order of interactions.
    if gp["events"]:
        from dataclasses import replace
        evs, notes = from_brief(level, gp["events"])
        if ending in ("time_out", "cliffhanger"):  # as play.plan: these endings never show the last exit
            evs = [replace(e, when="next") if e.when == "last" else e for e in evs]
        solver = [e for e in evs if e.action in SOLVER_ACTIONS]
        c = check_events(level, solver, drags, kinds)
        done = {id(e): k for e, k in zip(solver, c.done_at)}
        rows = []
        # a step that adds nothing ("all the blocks leave") does not count as one left out
        all_ok = c.ok and not any("no such block" in n for n in notes)
        for e in evs:
            if e.action in SOLVER_ACTIONS:
                k = done.get(id(e))
                rows.append(f"{e.text}: {'drag ' + str(k + 1) if k is not None else 'NOT DONE'}")
            elif e.action == "stuck":
                k = next((i for i in made if beats[i]["block"] in e.blocks and "in the way" in beats[i]["note"]), None)
                all_ok &= k is not None
                rows.append(f"{e.text}: {'drag ' + str(k + 1) if k is not None else 'NOT SHOWN'}")
            else:
                k = next((i for i, b in enumerate(beats) if b["kind"] == "hesitate" and b["block"] in e.blocks), None)
                all_ok &= k is not None
                rows.append(f"{e.text}: {'drag ' + str(k + 1) if k is not None else 'NOT SHOWN'}")
        detail = "; ".join(rows)
        if notes:
            detail = (detail + ". " if detail else "") + " ".join(n + "." for n in notes)
        if not c.ok:
            detail += f" ({c.problem})"
        add("Order of interactions", "pass" if all_ok else ("adjusted" if c.ok else "failed"), detail)

    # 5. The finish: one key move, then blocks leaving in a row.
    real = [i for i, k in enumerate(kinds) if k != "hesitate"]
    run = trailing_exits([drags[i] for i in real])
    key = real[-run - 1] if run < len(real) else None
    if gp["finish"] == "streak":
        n = len(level.blocks)
        cleared = ending in ("win", "near_fail") and left == 0
        if key is not None and kinds[key] != "solve":
            add("Satisfying finish", "adjusted", f"the last {run} block(s) leave one after another, but the move "
                                                 f"before them (drag {key + 1}) is a mistake, not a key move")
        elif key is not None:
            ok = cleared and run >= max(2, n // 2)
            add("Satisfying finish", "pass" if ok else "adjusted",
                f"drag {key + 1} ({name(drags[key].block)} moves) lets the last {run} of {n} blocks leave one after "
                f"another")
        else:
            add("Satisfying finish", "pass" if cleared else "adjusted", f"all {run} blocks leave one after another")
    elif ending in ("win", "near_fail"):
        add("Finish", "info", f"the play ends with {run} exit(s) in a row")

    # 6. Pacing over the video: pauses before drags in the first and last third.
    if pc["curve"] != "even" and len(rdrags) >= 6:
        gaps = [(rdrags[i]["start_frame"] - rdrags[i - 1]["end_frame"]) / FPS for i in range(1, len(rdrags))]
        third = max(1, len(gaps) // 3)
        a, b = sum(gaps[:third]) / third, sum(gaps[-third:]) / third
        want_faster = pc["curve"] == "speeds_up"
        ok = (b < a) if want_faster else (b > a)
        add("Pacing curve", "pass" if ok else "failed",
            f"average pause {a:.2f} s in the first third, {b:.2f} s in the last third "
            f"(asked: {pc['curve'].replace('_', ' ')})")
    return out


def _dims(level: Level, i: int) -> tuple[int, int]:
    offs = level.blocks[i].offsets
    return (max(o[0] for o in offs) - min(o[0] for o in offs) + 1, max(o[1] for o in offs) - min(o[1] for o in offs) + 1)


def level_checks(brief: dict, level_path: Path, meta: dict | None = None) -> list[dict]:
    """Facts about the board, against what the brief asked for."""
    from .difficulty import rate
    from .generate import BAND_WORDS, Spec, band_of, looks
    level = load_level(level_path)
    lv = brief["level"]
    out = []
    r = rate(level, runs=100)
    band = band_of(r)
    detail = (f"{r.min_drags} drags minimum, {r.extra_drags} repositioning, {r.exits_at_start} block(s) can leave at "
              f"once, a casual player needs about {r.naive_ratio:.1f}x the minimum -> {BAND_WORDS[band]}")
    if lv["difficulty"] != "any":
        ok = band == lv["difficulty"]
        out.append({"check": "Difficulty", "status": "pass" if ok else "adjusted",
                    "detail": detail + f" (asked: {lv['difficulty']})", "from": "level"})
    else:
        out.append({"check": "Difficulty", "status": "info", "detail": detail, "from": "level"})
    sizes = sorted(b.size for b in level.blocks)
    if lv["blocks"] is not None:
        n = len(level.blocks)
        out.append({"check": "Block count", "status": "pass" if n == lv["blocks"] else "adjusted",
                    "detail": f"{n} blocks (asked: {lv['blocks']})" + ("" if n == lv["blocks"] else
                              "; no more fit with room to move"), "from": "level"})
    if lv["pieces"] != "mixed":
        want = {"small": (1, 2), "big": (4, 6), "long": (3, 4)}[lv["pieces"]]
        fit = sum(want[0] <= n <= want[1] for n in sizes)
        long_ok = lv["pieces"] != "long" or all(min(_dims(level, i)) == 1 for i in range(len(level.blocks)))
        ok = fit == len(sizes) and long_ok
        out.append({"check": "Block shapes", "status": "pass" if ok else "adjusted",
                    "detail": f"block sizes {sizes} cells (asked: {lv['pieces']}, {want[0]}-{want[1]} cells"
                              f"{', one cell wide' if lv['pieces'] == 'long' else ''})", "from": "level"})
    if lv["shape"] != "any":
        from .generate import SHAPE_WORDS
        out.append({"check": "Board shape", "status": "info",
                    "detail": f"{SHAPE_WORDS.get(lv['shape'], lv['shape'])}, {level.width}x{level.height}, "
                              f"{len(level.inactive)} cells cut out", "from": "level"})
    if lv["style"]:
        lk = looks(level, Spec(style=list(lv["style"])))
        rows, ok = [], True
        if "symmetric" in lv["style"]:
            rows.append(f"mirror symmetry {lk['symmetry']:.0%} (blocks, colours and gates)")
            ok &= lk["symmetry"] >= 0.95
        if "packed" in lv["style"]:
            rows.append(f"{lk['fill']:.0%} of the cells hold blocks (packed: 55 % or more)")
            ok &= lk["fill"] >= 0.55
        if "colourful" in lv["style"]:
            n_col = len({b.color for b in level.blocks})
            # mirror pairs share a colour, so a symmetric board shows at most one colour per pair
            most = min(7, (len(level.blocks) + 1) // 2 if "symmetric" in lv["style"] else len(level.blocks))
            rows.append(f"{n_col} colours" + (f" (a mirror pair shares one, so {most} at most)"
                                              if "symmetric" in lv["style"] else "")
                        + f"; touching blocks in different colours {lk['contrast']:.0%}")
            ok &= n_col >= most - 1 and lk["contrast"] >= 0.85
        rows.append(f"gates on {round(lk['sides'] * 4)} sides")
        out.append({"check": "Board looks", "status": "pass" if ok else "adjusted", "detail": "; ".join(rows),
                    "from": "level"})
    return out
