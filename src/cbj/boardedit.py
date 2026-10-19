"""Edits of the board that a prompt names: move a gate to an edge, add a wall on a tile or on a
block's route, remove a wall.

The game's only obstacles are holes (inactive cells: the walls a block cannot enter). An edit of
the board keeps everything else as it was, and keeps the play's moves too, as far as they are
still legal: the longest start of the old play that replays cell by cell on the new board (and
leaves a position that can still be won) is kept, and only the rest is planned again
(play.plan(prefix=...)). When no change of the kind asked for leaves a winnable level, the edit is
refused with the reason, never faked (a block never passes through a wall).
"""

from __future__ import annotations

import copy

from .generate import DIR, SIDES, _rim, _span, _windows
from .level import level_from_dict, validate
from .solver import Drag, ReplayError, replay, solve_fast

OPS = ("move_gate", "add_wall", "remove_wall")
SIDE_OF = {v: k for k, v in DIR.items()}
OPPOSITE = {"top": "bottom", "bottom": "top", "left": "right", "right": "left"}
SLOT = {"Green": 0, "Yellow": 1, "Blue": 2, "Red": 3, "Orange": 4, "Purple": 5, "DarkGreen": 6}
WORD = {0: "green", 1: "yellow", 2: "blue", 3: "red", 4: "orange", 5: "purple", 6: "dark green"}


def _level(d: dict):
    L = level_from_dict(d, name="edited")
    problems = validate(L)
    if problems:
        raise ValueError(problems[0])
    return L


def _steps(beats: list[dict]) -> list[tuple]:
    """A recorded play's beats as play.plan steps (kind, drag, role, note); hesitations are put
    back in by the planner, and a cut ending (a bump, a short race) is never kept."""
    out = []
    for b in beats:
        if b["kind"] == "hesitate":
            continue
        if b["kind"] not in ("solve", "mistake"):
            break
        d = Drag(b["block"], tuple(tuple(c) for c in b["path"]), bool(b["exits"]), b.get("exit_index"))
        if b["kind"] == "mistake":
            role = "blocked" if b.get("push_cells") else "mistake"
        else:
            role = "realize" if b.get("pause") in ("after_mistake", "stuck") else "solve"
        out.append((b["kind"], d, role, b.get("note", "")))
    return out


def kept_prefix(level, beats: list[dict]) -> list[tuple]:
    """The longest start of the play that is still legal on `level` and after which the level can
    still be won."""
    steps, drags = [], []
    for st in _steps(beats):
        try:
            replay(level, drags + [st[1]])
        except ReplayError:
            break
        drags.append(st[1])
        steps.append(st)
    while steps:
        state = replay(level, [s[1] for s in steps])
        if all(p is None for p in state) or solve_fast(level, start=state) is not None:
            break
        steps.pop()
    return steps


def _route_cells(level, beats: list[dict], colour: int | None) -> list[tuple]:
    """The cells the blocks of a colour (any block when None) pass through in the play, in order."""
    out = []
    for b in beats:
        if b["kind"] not in ("solve", "mistake"):
            continue
        blk = level.blocks[b["block"]]
        if colour is not None and int(blk.color) != colour:
            continue
        for pivot in b["path"]:
            for c in blk.cells_at(tuple(pivot)):
                if c not in out:
                    out.append(c)
    return out


def _with_gate(d: dict, k: int, side: str, cells: list) -> dict:
    e = copy.deepcopy(d)
    x0, y0 = cells[0]
    e["ExitDatas"][k] = {**e["ExitDatas"][k], "gridPosition": {"x": x0, "y": y0}, "direction": DIR[side],
                         "shapeOffsets": [{"x": x - x0, "y": y - y0} for x, y in cells]}
    return e


def _cell_name(c) -> str:
    return f"column {c[0] + 1}, row {c[1] + 1}"


def _candidates(d: dict, op: dict, beats: list[dict]):
    """(new level dict, what changed in words) for every way to do one change, best guess first."""
    L = level_from_dict(d, name="parent")
    holes = {(c["x"], c["y"]) for c in d.get("inactiveCells", [])}
    active = {(x, y) for x in range(L.width) for y in range(L.height)} - holes
    col = SLOT.get(op.get("colour") or "", None)
    at = (op["column"] - 1, op["row"] - 1) if op.get("column") and op.get("row") else None
    gate_cells = {c for e in L.exits for c in e.cells}
    if op["op"] == "move_gate":
        if col is None:
            raise ValueError("which door to move is not named (say its colour)")
        ks = [k for k, e in enumerate(L.exits) if int(e.color) == col]
        if not ks:
            raise ValueError(f"this level has no {WORD[col]} door")
        used_k = [b.get("exit_index") for b in beats if b.get("exits") and int(L.blocks[b["block"]].color) == col]
        k = next((x for x in used_k if x in ks), ks[0])
        cur = SIDE_OF[int(L.exits[k].direction)]
        side = op.get("side") or ""
        side = OPPOSITE[cur] if side == "opposite" else side
        if side not in SIDES:
            raise ValueError(f"which edge the {WORD[col]} door goes to is not named (top, bottom, left, right)")
        if side == cur and at is None:
            raise ValueError(f"the {WORD[col]} door is already on the {side} edge")
        used = {(c, SIDE_OF[int(e.direction)]) for j, e in enumerate(L.exits) if j != k for c in e.cells}
        rim = _rim(active, L.width, L.height, side, inner=False)
        span = max(_span(list(b.cells_at(b.pivot)), side) for b in L.blocks if int(b.color) == col)
        wins = _windows(rim, side, span, used)
        if at is not None:
            wins = [w for w in wins if at in w]
        old = sorted(L.exits[k].cells)
        mid = lambda w: sum(x for x, _ in w) / len(w) if side in ("top", "bottom") else sum(y for _, y in w) / len(w)
        near = sum(x for x, _ in old) / len(old) if side in ("top", "bottom") else sum(y for _, y in old) / len(old)
        wins.sort(key=lambda w: (abs(mid(w) - near), w))
        for w in wins:
            yield _with_gate(d, k, side, w), (f"the {WORD[col]} door moved from the {cur} edge to the {side} edge "
                                              f"({_cell_name(w[0])}{' to ' + _cell_name(w[-1]) if len(w) > 1 else ''})")
        return
    if op["op"] == "add_wall":
        start = {c for b in L.blocks for c in b.cells_at(b.pivot)}
        if at is not None:
            cells = [at]
        else:
            cells = _route_cells(L, beats, col)
            if not cells:
                raise ValueError(f"no {WORD[col] + ' ' if col is not None else ''}block moves in this play, so it has "
                                 f"no route to put a wall on")
        free = [c for c in cells if c in active and c not in start and c not in gate_cells]
        if at is not None and not free:
            raise ValueError(f"{_cell_name(at)} is not an empty tile (a block, a gate or a wall is there)")
        if not free:
            raise ValueError(f"every tile the {WORD[col] + ' ' if col is not None else ''}block passes on its way out is "
                             f"its own starting place or a gate tile, so its route has no empty tile for a wall")
        for c in free:
            e = copy.deepcopy(d)
            e["inactiveCells"] = sorted([*e.get("inactiveCells", []), {"x": c[0], "y": c[1]}], key=lambda v: (v["x"], v["y"]))
            route = f" on the {WORD[col]} block's route" if col is not None and at is None else ""
            yield e, f"a wall added at {_cell_name(c)}{route}"
        return
    if op["op"] == "remove_wall":
        cands = [at] if at is not None else sorted(holes)
        if at is not None and at not in holes:
            raise ValueError(f"there is no wall at {_cell_name(at)}")
        if not cands:
            raise ValueError("this board has no walls to remove (it is an open board)")
        for c in cands:
            e = copy.deepcopy(d)
            e["inactiveCells"] = [v for v in e.get("inactiveCells", []) if (v["x"], v["y"]) != c]
            yield e, f"the wall at {_cell_name(c)} removed"
        return
    raise ValueError(f"unknown board change {op['op']!r}")


def apply(parent: dict, changes: list[dict], beats: list[dict], easier: bool = False, log=None) -> tuple[dict, dict]:
    """The parent level with the changes, one after another, each done the way that keeps the most
    of the play (then, for a removed wall asked to make it easier, the easiest board). Returns the
    level dict and {"what", "kept", "of", "prefix"}; raises ValueError with the reason when no way
    leaves a valid, winnable level."""
    from .difficulty import rate
    d = copy.deepcopy(parent)
    whats = []
    n_moves = len(_steps(beats))
    for op in changes:
        best, why = None, None
        tried = 0
        for cand, what in _candidates(d, op, beats):
            tried += 1
            try:
                L = _level(cand)
            except ValueError as e:
                why = why or str(e)
                continue
            if solve_fast(L) is None:
                why = why or "the level could not be won"
                continue
            k = len(kept_prefix(L, beats))
            score = [k]
            if op["op"] == "remove_wall" and easier:
                r = rate(L, runs=60)
                score.append(-(2.0 * r.extra_drags + 0.6 * min(r.naive_ratio, 4.0)))
            if best is None or score > best[0]:
                best = (score, cand, what)
            if op["op"] == "add_wall" and k < n_moves and best[0] == score and tried >= 12:
                break
        if best is None:
            raise ValueError(f"{op['op'].replace('_', ' ')}: no way to do it leaves a level that can be won"
                             + (f" ({why})" if why else "") if tried else f"{op['op'].replace('_', ' ')}: nothing to change")
        d = best[1]
        whats.append(best[2])
        if log:
            log(f"  {best[2]} ({tried} way(s) tried)")
    L = _level(d)
    prefix = kept_prefix(L, beats)
    return d, {"what": "; ".join(whats), "kept": len(prefix), "of": n_moves, "prefix": prefix}


def prefix_to_json(prefix: list[tuple]) -> list[dict]:
    return [{"kind": k, "block": dr.block, "path": [list(c) for c in dr.path], "exits": dr.exits,
             "exit_index": dr.exit_index, "role": role, "note": note} for k, dr, role, note in prefix]


def prefix_from_json(items: list[dict]) -> list[tuple]:
    return [(x["kind"], Drag(x["block"], tuple(tuple(c) for c in x["path"]), x["exits"], x.get("exit_index")),
             x["role"], x["note"]) for x in items]
