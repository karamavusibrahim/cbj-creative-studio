"""Structured search for an hourglass level.

Top half rows 5..7, bottom half rows 0..2, waist = columns 2,3 at rows 3,4 (holes elsewhere).
Crossing pairs: a top block whose gate is on the bottom edge in its own column, and a bottom
block whose gate is on the top edge in the same column. They share the lane through the waist,
so one has to step aside. Fillers sit on the halves with side gates. Optional plug in the waist.
"""
from __future__ import annotations

import json
import random
import sys
import time
from collections import Counter

import cbj.describe as describe
from cbj.difficulty import rate
from cbj.level import level_from_dict, validate
from cbj.rules import initial_state, occupancy, can_block_exit
from cbj.solver import SolverLimitError, solve

W, H = 6, 8
WAIST_ROWS = (3, 4)
WAIST_COLS = (2, 3)
HOLES = [(x, y) for y in WAIST_ROWS for x in range(W) if x not in WAIST_COLS]
OUT = "/private/tmp/claude-501/-Users-ibrahimkaramavus/8be11934-ee3a-484b-a53c-3b47fd1092ec/scratchpad/fable-scenario"

V1 = [(0, 0)]
V2 = [(0, 0), (0, -1)]
V3 = [(0, 0), (0, -1), (0, -2)]
H2 = [(0, 0), (1, 0)]
H3 = [(0, 0), (1, 0), (2, 0)]
SQ = [(0, 0), (0, -1), (1, -1), (1, 0)]
L = [(0, 0), (1, 0), (1, -1)]
J = [(0, 0), (0, -1), (1, -1)]
FILLER_SHAPES = [V1, V2, H2, H3, SQ, L, J, V3]


def cells(p, offs):
    return [(p[0] + ox, p[1] + oy) for ox, oy in offs]


def gate(x, y, color, direction, width_offsets):
    return {"exitNumber": 0, "gridPosition": {"x": x, "y": y}, "requiredColor": color,
            "direction": direction, "shapeOffsets": width_offsets}


def build(rng: random.Random):
    holes = set(HOLES)
    occ = set()
    blocks, exits = [], []
    colors = list(range(7))
    rng.shuffle(colors)
    ci = 0

    def place(p, offs, color):
        cs = cells(p, offs)
        if any(not (0 <= x < W and 0 <= y < H) or (x, y) in holes or (x, y) in occ for x, y in cs):
            return False
        occ.update(cs)
        blocks.append({"gridPosition": {"x": p[0], "y": p[1]}, "blockColor": color,
                       "shapeOffsets": [{"x": ox, "y": oy} for ox, oy in offs]})
        return True

    # crossing pairs
    n_pairs = rng.choice([1, 2, 2])
    cols = list(WAIST_COLS)
    rng.shuffle(cols)
    for k in range(n_pairs):
        x = cols[k]
        top_shape = rng.choice([V1, V2, V2, V3])
        bot_shape = rng.choice([V1, V2, V2, V3])
        ty = rng.choice([5, 6, 7]) if top_shape is V1 else (rng.choice([6, 7]) if top_shape is V2 else 7)
        by = rng.choice([0, 1, 2]) if bot_shape is V1 else (rng.choice([1, 2]) if bot_shape is V2 else 2)
        ctop = colors[ci % 7]; ci += 1
        cbot = colors[ci % 7]; ci += 1
        if not place((x, ty), top_shape, ctop) or not place((x, by), bot_shape, cbot):
            return None
        exits.append(gate(x, 0, ctop, 3, [{"x": 0, "y": 0}]))       # bottom gate for the top block
        exits.append(gate(x, H - 1, cbot, 2, [{"x": 0, "y": 0}]))   # top gate for the bottom block

    # optional plug in the waist, gate on the rim of a hole (left or right side of the waist)
    if rng.random() < 0.6:
        px = rng.choice(WAIST_COLS)
        py = rng.choice(WAIST_ROWS)
        c = colors[ci % 7]; ci += 1
        if place((px, py), V1, c):
            if px == WAIST_COLS[0]:
                exits.append(gate(px, py, c, 0, [{"x": 0, "y": 0}]))  # left, onto the hole rim
            else:
                exits.append(gate(px, py, c, 1, [{"x": 0, "y": 0}]))

    # fillers on the halves, side gates on the outer edge of the same half
    n_fill = rng.choice([2, 3, 4, 5])
    tries = 0
    placed = 0
    while placed < n_fill and tries < 200:
        tries += 1
        offs = rng.choice(FILLER_SHAPES)
        half = rng.choice(["top", "bottom"])
        x = rng.randrange(W)
        y = rng.randrange(5, 8) if half == "top" else rng.randrange(0, 3)
        cs = cells((x, y), offs)
        ys = {cy for _, cy in cs}
        if half == "top" and min(ys) < 5 or half == "bottom" and max(ys) > 2:
            continue
        c = colors[ci % 7] if ci < 7 else rng.randrange(7)
        if not place((x, y), offs, c):
            continue
        ci += 1
        placed += 1
        xs = sorted({cx for cx, _ in cs}); ys = sorted(ys)
        side = rng.choice(["left", "right", "top", "bottom", "edge"])
        if side in ("left", "right"):
            gx = 0 if side == "left" else W - 1
            exits.append(gate(gx, ys[0], c, 0 if side == "left" else 1, [{"x": 0, "y": k} for k in range(len(ys))]))
        elif side == "top" and half == "top":
            exits.append(gate(xs[0], H - 1, c, 2, [{"x": k, "y": 0} for k in range(len(xs))]))
        elif side == "bottom" and half == "bottom":
            exits.append(gate(xs[0], 0, c, 3, [{"x": k, "y": 0} for k in range(len(xs))]))
        else:
            # far edge: must pass the waist (only possible if the block is at most 2 wide)
            if len(xs) > 2:
                gx = 0 if rng.random() < 0.5 else W - 1
                exits.append(gate(gx, ys[0], c, 0 if gx == 0 else 1, [{"x": 0, "y": k} for k in range(len(ys))]))
            else:
                gx = rng.choice([2, 3]) if len(xs) == 1 else 2
                if half == "top":
                    exits.append(gate(gx, 0, c, 3, [{"x": k, "y": 0} for k in range(len(xs))]))
                else:
                    exits.append(gate(gx, H - 1, c, 2, [{"x": k, "y": 0} for k in range(len(xs))]))
    return {"gridWidth": W, "gridHeight": H, "timerCount": 60,
            "inactiveCells": [{"x": x, "y": y} for x, y in HOLES],
            "GridBlockDatas": blocks, "ExitDatas": exits}


def waist_crossings(lvl, sol):
    n = 0
    for d in sol.drags:
        if any(y in WAIST_ROWS for _, y in d.path[1:]):
            n += 1
    return n


def main():
    budget = float(sys.argv[1]) if len(sys.argv) > 1 else 90
    seed0 = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    rng = random.Random(seed0)
    t0 = time.time()
    stats = Counter()
    best = []
    n = 0
    while time.time() - t0 < budget:
        n += 1
        d = build(rng)
        if d is None:
            stats["build_fail"] += 1
            continue
        try:
            lvl = level_from_dict(d, name=f"nc{seed0}_{n}")
        except ValueError:
            stats["parse"] += 1
            continue
        if validate(lvl):
            stats["invalid"] += 1
            continue
        st0 = initial_state(lvl); occ0 = occupancy(lvl, st0)
        if any(can_block_exit(lvl, b, p, occ0) for b, p in enumerate(st0)):
            stats["start_on_gate"] += 1
            continue
        try:
            sol = solve(lvl, max_states=200_000)
        except SolverLimitError:
            stats["limit"] += 1
            continue
        if sol is None:
            stats["unsolvable"] += 1
            continue
        stats[f"extra{sol.extra_drags}"] += 1
        if sol.extra_drags < 1 or sol.min_drags < 7:
            continue
        r = rate(lvl, runs=40, seed=1, cap=80)
        wc = waist_crossings(lvl, sol)
        score = (min(r.extra_drags, 4), -r.exits_at_start, round(r.naive_ratio, 1), wc)
        best.append((score, r, d, lvl, wc, sol))
        best.sort(key=lambda t: t[0], reverse=True)
        best = best[:6]
    print(f"{n} candidates in {time.time() - t0:.0f}s; {dict(stats)}")
    for score, r, d, lvl, wc, sol in best:
        print("----", r.level_name, "blocks", r.blocks, "min", r.min_drags, "extra", r.extra_drags,
              "exits_at_start", r.exits_at_start, "first_moves", r.first_moves,
              f"naive {r.naive_mean:.1f} p90 {r.naive_p90} capped {r.naive_capped} ratio {r.naive_ratio:.2f}",
              "waist crossings", wc, "states", sol.states_explored)
        print(describe.render(lvl, initial_state(lvl)))
        json.dump(d, open(f"{OUT}/{r.level_name}.json", "w"), indent=2)


if __name__ == "__main__":
    main()
