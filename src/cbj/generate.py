"""Level generator: a level built to a spec (shape, size, blocks, colours, difficulty), solvable,
valid for the game's Level Editor, rated, and reproducible from its seed.

Search, not construction. Candidates are made by placing polyomino blocks at random on a board
of the requested shape, each with a gate of its colour on the board's edge. Each candidate is
checked by the game's rules (validate), solved exactly (A*, with a state cap), and rated (the
simulated naive player in difficulty.py). The best match to the target band within a time
budget is kept.

Why gates go to the far side for hard levels: a block whose gate is across the board must cross
the paths of other blocks, which is what makes repositioning drags necessary. A random gate is
usually reachable at once, so random boards are almost always easy.

Difficulty bands, from the existing measures (descriptive, not calibrated on player data):
- easy: no repositioning drag, at least half the blocks can leave at once, the naive player
  needs at most 1.1x the minimum;
- medium: one repositioning drag, or a naive ratio of 1.1-1.3, and at most a third of the blocks
  can leave at once;
- hard: no block can leave at the start, at least two repositioning drags, a naive ratio of
  1.2-4 (beyond that the board reads as a maze), and the naive player always finishes (a level
  it cannot finish is unfair).
"""

from __future__ import annotations

import hashlib
import json
import random
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .difficulty import Difficulty, rate
from .level import level_from_dict, validate
from .solver import SolverLimitError, solve_fast

SHAPES = ("open", "narrow_center", "door", "holes")
BANDS = ("easy", "medium", "hard")
COLOURS = ("Green", "Yellow", "Blue", "Red", "Orange", "Purple", "DarkGreen")  # enum BlockColor order
PIECES = {
    "1x1": [(0, 0)], "h2": [(0, 0), (1, 0)], "v2": [(0, 0), (0, -1)], "h3": [(0, 0), (1, 0), (2, 0)],
    "v3": [(0, 0), (0, -1), (0, -2)], "sq": [(0, 0), (0, -1), (1, -1), (1, 0)], "L": [(0, 0), (1, 0), (1, -1)],
    "J": [(0, 0), (0, -1), (1, -1)], "T": [(0, 0), (1, 0), (2, 0), (1, -1)],
}
DEFAULTS = {  # (width, height, blocks) when the spec leaves them open
    ("open", "easy"): (6, 6, 5), ("open", "medium"): (6, 7, 6), ("open", "hard"): (7, 8, 7),
    ("narrow_center", "easy"): (6, 8, 5), ("narrow_center", "medium"): (6, 8, 6), ("narrow_center", "hard"): (6, 8, 7),
    ("door", "easy"): (7, 6, 5), ("door", "medium"): (7, 7, 6), ("door", "hard"): (7, 8, 7),
    ("holes", "easy"): (6, 6, 5), ("holes", "medium"): (7, 7, 6), ("holes", "hard"): (7, 8, 7),
}
DIR = {"left": 0, "right": 1, "top": 2, "bottom": 3}
TIMER_S = 60
MAX_STATES = 12_000  # boards needing more positions are slow to search and hard to read in an ad


@dataclass
class Spec:
    shape: str = "any"
    width: int | None = None
    height: int | None = None
    blocks: int | None = None
    colours: list[str] = field(default_factory=list)
    difficulty: str = "any"
    target_drags: int | None = None  # a preference for longer play, from the ad's length
    seed: int = 0
    budget_s: float | None = None  # seconds of search; None: 40 for a hard narrow centre, else 25

    def resolved(self) -> "Spec":
        """Open fields filled in: the shape and band the search will use."""
        band = self.difficulty if self.difficulty in BANDS else "medium"
        shape = self.shape if self.shape in SHAPES else ("narrow_center" if band == "hard" else "open")
        w, h, n = DEFAULTS[(shape, band)]
        budget = self.budget_s or (40.0 if (shape, band) == ("narrow_center", "hard") else 25.0)
        return Spec(shape, self.width or w, self.height or h, self.blocks or n, list(self.colours), band,
                    self.target_drags, self.seed, budget)


def holes_for(shape: str, w: int, h: int) -> set[tuple[int, int]]:
    if shape == "narrow_center":  # an hourglass: the middle rows cut to a two-lane waist
        rows = (h // 2 - 1, h // 2) if h >= 6 else (h // 2,)
        lanes = {w // 2 - 1, w // 2} if w >= 4 else {w // 2}
        return {(x, y) for y in rows for x in range(w) if x not in lanes}
    if shape == "door":  # two rooms: a wall down the middle with a two-cell door
        x = w // 2
        door = {h // 2 - 1, h // 2}
        return {(x, y) for y in range(h) if y not in door}
    if shape == "holes":  # a 2x2 pillar in the middle (two on wide, tall boards)
        cx, cy = w // 2 - 1, h // 2 - 1
        cells = {(cx + dx, cy + dy) for dx in (0, 1) for dy in (0, 1)}
        if w >= 8 and h >= 8:
            cells = {(x - 2, y) for x, y in cells} | {(x + 2, y) for x, y in cells}
        return cells
    return set()


def band_of(d: Difficulty) -> str:
    if d.exits_at_start == 0 and d.extra_drags >= 2 and 1.2 <= d.naive_ratio <= 4.0 and d.naive_capped == 0:
        return "hard"
    if d.extra_drags == 0 and d.exits_at_start >= max(2, d.blocks // 2) and d.naive_ratio <= 1.1:
        return "easy"
    if (d.extra_drags == 1 or 1.1 <= d.naive_ratio <= 1.3) and d.exits_at_start <= max(1, d.blocks // 3):
        return "medium"
    return "between"


def _edge_gate(rng, active, w, h, cells, side, used):
    """A gate on `side` as wide as the block across it, on active cells that face the outside and
    carry no other gate on that side (the Level Editor keeps one gate per cell side)."""
    xs = sorted({x for x, _ in cells})
    ys = sorted({y for _, y in cells})
    if side in ("top", "bottom"):
        y = h - 1 if side == "top" else 0
        width = len(xs)
        starts = [x for x in range(w - width + 1)
                  if all((x + k, y) in active and ((x + k, y), side) not in used for k in range(width))]
        if not starts:
            return None
        x0 = rng.choice(starts)
        used.update(((x0 + k, y), side) for k in range(width))
        return {"gridPosition": {"x": x0, "y": y}, "direction": DIR[side],
                "shapeOffsets": [{"x": k, "y": 0} for k in range(width)]}
    x = 0 if side == "left" else w - 1
    height = len(ys)
    starts = [y for y in range(h - height + 1)
              if all((x, y + k) in active and ((x, y + k), side) not in used for k in range(height))]
    if not starts:
        return None
    y0 = rng.choice(starts)
    used.update(((x, y0 + k), side) for k in range(height))
    return {"gridPosition": {"x": x, "y": y0}, "direction": DIR[side],
            "shapeOffsets": [{"x": 0, "y": k} for k in range(height)]}


def candidate(spec: Spec, rng: random.Random) -> dict:
    """One random level for the spec, as the game's level JSON."""
    w, h, n = spec.width, spec.height, spec.blocks
    holes = holes_for(spec.shape, w, h)
    active = {(x, y) for x in range(w) for y in range(h)} - holes
    occ: set = set()
    placed = []
    names = list(PIECES)
    for _ in range(600):
        if len(placed) >= n:
            break
        offs = PIECES[rng.choice(names)]
        px, py = rng.randrange(w), rng.randrange(h)
        cs = [(px + ox, py + oy) for ox, oy in offs]
        if any(c not in active or c in occ for c in cs):
            continue
        placed.append(((px, py), offs, cs))
        occ.update(cs)
    slots = [COLOURS.index(c) for c in spec.colours] or list(range(7))
    rng.shuffle(slots)
    far = {"easy": 0.15, "medium": 0.55, "hard": 0.85}[spec.difficulty]
    blocks, exits, used = [], [], set()
    for i, (pivot, offs, cs) in enumerate(placed):
        colour = slots[i % len(slots)]
        cx = sum(x for x, _ in cs) / len(cs)
        cy = sum(y for _, y in cs) / len(cs)
        # far side (across the board) for harder levels, the nearest side for easy ones
        sides = sorted(("left", "right", "top", "bottom"),
                       key=lambda s: {"left": cx, "right": w - 1 - cx, "bottom": cy, "top": h - 1 - cy}[s])
        order = list(reversed(sides)) if rng.random() < far else sides
        order = order[:2] + rng.sample(order[2:], 2)
        gate = None
        for side in order:
            gate = _edge_gate(rng, active, w, h, cs, side, used)
            if gate:
                break
        if gate is None:
            continue
        blocks.append({"gridPosition": {"x": pivot[0], "y": pivot[1]}, "blockColor": colour,
                       "shapeOffsets": [{"x": ox, "y": oy} for ox, oy in offs]})
        exits.append({"exitNumber": 0, "requiredColor": colour, **gate})
    return {"gridWidth": w, "gridHeight": h, "timerCount": TIMER_S,
            "inactiveCells": [{"x": x, "y": y} for x, y in sorted(holes)],
            "GridBlockDatas": blocks, "ExitDatas": exits}


def _score(spec: Spec, d: Difficulty, band: str) -> float:
    """Higher is better: the right band first, then how well it shows that band."""
    s = 100.0 if band == spec.difficulty else (40.0 if band == "between" else 0.0)
    if spec.difficulty == "hard":
        s += 6 * min(d.extra_drags, 4) + 20 * (d.naive_ratio - 1) - 4 * d.exits_at_start
    elif spec.difficulty == "easy":
        s += 2 * d.exits_at_start - 10 * abs(d.naive_ratio - 1)
    else:
        s += 4 * (d.extra_drags == 1) - 5 * abs(d.naive_ratio - 1.2)
    if spec.target_drags:
        s -= 1.5 * abs(d.min_drags - spec.target_drags)
    s -= 3 * abs(d.blocks - spec.blocks)
    s -= 60 * d.naive_capped / max(1, d.runs)  # a board the naive player cannot finish is unfair
    s -= 4 * max(0.0, d.naive_ratio - 2.0)  # and one that far beyond the minimum reads as a maze
    return s


def generate(spec: Spec, log=None) -> tuple[dict, Difficulty, dict]:
    """The best level for the spec found within its budget: (level JSON, its rating, stats)."""
    spec = spec.resolved()
    rng = random.Random(spec.seed)
    t0 = time.time()
    best = None
    spare = None  # the best board a cheap screen turned down, rated only if nothing passed
    stats = {"tried": 0, "valid": 0, "solvable": 0, "rated": 0, "in_band": 0}
    while time.time() - t0 < spec.budget_s:
        stats["tried"] += 1
        d = candidate(spec, rng)
        if len(d["GridBlockDatas"]) < max(2, spec.blocks - 1):
            continue
        try:
            lvl = level_from_dict(d, name="generated")
        except ValueError:
            continue
        if validate(lvl):
            continue
        stats["valid"] += 1
        try:
            sol = solve_fast(lvl, max_states=MAX_STATES)
        except SolverLimitError:
            continue
        if sol is None:
            continue
        stats["solvable"] += 1
        # Cheap screens before the naive-player rating.
        off = (spec.difficulty == "hard" and sol.extra_drags < 2) or (spec.difficulty == "easy" and sol.extra_drags > 0)
        if off:
            cheap = -abs(sol.min_drags - (spec.target_drags or sol.min_drags)) + (sol.extra_drags if spec.difficulty == "hard" else -sol.extra_drags)
            if spare is None or cheap > spare[0]:
                spare = (cheap, d, sol)
            continue
        r = rate(lvl, runs=40, seed=1, cap=80, solution=sol)
        stats["rated"] += 1
        band = band_of(r)
        stats["in_band"] += band == spec.difficulty
        sc = _score(spec, r, band)
        if best is None or sc > best[0]:
            best = (sc, d, r, band)
            if log:
                log(f"  candidate {stats['tried']}: {r.min_drags} drags ({r.extra_drags} repositioning), "
                    f"{r.exits_at_start} can leave at once, naive {r.naive_ratio:.2f}x -> {band}")
        # Good enough: in band, and as close to the preferred length as this many blocks can get.
        reachable = min(spec.target_drags or 0, spec.blocks + {"easy": 0, "medium": 1, "hard": 3}[spec.difficulty])
        if band == spec.difficulty and stats["in_band"] >= 3 and (
                not spec.target_drags or best[2].min_drags >= reachable - 1):
            break
    if best is None and spare is not None:
        _, d, sol = spare
        r = rate(level_from_dict(d, name="generated"), runs=40, seed=1, cap=80, solution=sol)
        best = (0.0, d, r, band_of(r))
    if best is None:
        raise ValueError(f"no valid, solvable {spec.shape} {spec.width}x{spec.height} level with {spec.blocks} "
                         f"blocks found in {spec.budget_s:g} s ({stats['tried']} tried)")
    _, d, _, band = best
    lvl = level_from_dict(d, name="generated")
    full = rate(lvl)  # the final rating, with the full naive-player sample
    stats.update(seconds=round(time.time() - t0, 1), band=band_of(full), spec=asdict(spec))
    return d, full, stats


SHAPE_WORDS = {"open": "open", "narrow_center": "narrow-centre (hourglass)", "door": "two-room (door)",
               "holes": "pillared"}
BAND_WORDS = {"easy": "easy", "medium": "medium", "hard": "hard", "between": "medium-to-hard"}


def _target_drags(brief: dict) -> int:
    """How many drags fill the ad: its length minus about 12 s (hook hold, replay, result, end card),
    minus what each mistake (~3.5 s: the wrong drag, the stuck stare, the extra drag) and each
    hesitation (~1.2 s) take, at ~1.5 s a drag. A cliffhanger stops two blocks early."""
    gp = brief["gameplay"]
    ending = gp["ending"]
    mistakes = gp["mistakes"] if gp["mistakes"] is not None else {"near_fail": 1, "time_out": 1}.get(ending, 0)
    hes = gp["hesitations"] if gp["hesitations"] is not None else {"near_fail": 2}.get(ending, 0)
    per = 1.4 if ending == "win" else 1.6
    play = brief["pacing"]["length_s"] - 12 - 3.5 * mistakes - 1.2 * hes
    return max(4, min(14, round(play / per) + (2 if ending == "cliffhanger" else 0)))


def generate_for_brief(brief: dict, cache: Path, log) -> tuple[Path, str]:
    """A generated level for a brief, cached by its spec (the same brief gives the same level)."""
    from . import brief as B
    lv = brief["level"]
    gp = brief["gameplay"]
    difficulty = lv["difficulty"]
    if difficulty == "any":
        difficulty = {"near_fail": "hard", "time_out": "medium", "cliffhanger": "medium", "win": "medium"}[gp["ending"]]
    target = _target_drags(brief)
    blocks = lv["blocks"]
    if blocks is None:
        # Each block leaves once, so the minimum is the blocks plus the repositioning drags: size the
        # level to the ad's length when the prompt does not give a block count.
        blocks = max(4, min(10, target - {"easy": 0, "medium": 1, "hard": 2}[difficulty]))
    width, height = lv["width"], lv["height"]
    if width is None and height is None and lv["shape"] in ("any", "open", "holes", "door"):
        width, height = next(wh for n, wh in ((5, (6, 6)), (7, (7, 7)), (9, (7, 9)), (10, (8, 9))) if blocks <= n)
    if lv["blocks"] is None:
        # and never more than a board's free space holds with room to move (about 5 free cells a block)
        probe = Spec(lv["shape"], width, height, None, [], difficulty).resolved()
        free = probe.width * probe.height - len(holes_for(probe.shape, probe.width, probe.height))
        blocks = max(4, min(blocks, free // 5))
    spec = Spec(shape=lv["shape"], width=width, height=height, blocks=blocks,
                colours=list(lv["colours"]), difficulty=difficulty, target_drags=target, seed=gp["seed"] or 0)
    r = spec.resolved()
    if r.shape == "narrow_center" and (r.width < 4 or r.height < 6):
        r.height = max(r.height, 6)
        B.engine_note(brief, "level", "a narrow centre needs at least 6 rows; 6 are used.")
    if len(r.colours) and r.blocks > len(r.colours) * 2:
        B.engine_note(brief, "level", f"{r.blocks} blocks in {len(r.colours)} colours would repeat colours a lot; "
                                 f"blocks share the requested colours.")
    key = hashlib.sha256(json.dumps(asdict(r), sort_keys=True).encode()).hexdigest()[:12]
    cache.mkdir(parents=True, exist_ok=True)
    path, meta_path = cache / f"gen_{key}.json", cache / f"gen_{key}.meta.json"
    if path.is_file() and meta_path.is_file():
        meta = json.loads(meta_path.read_text())
        log(f"same level spec as before: level {key} reused")
    else:
        log(f"generating {'an' if r.difficulty == 'easy' else 'a'} {r.difficulty} {SHAPE_WORDS[r.shape]} {r.width}x{r.height} level with {r.blocks} blocks"
            f" (about {r.target_drags} drags for {brief['pacing']['length_s']:g} s)...")
        d = None
        tries = [r]
        if lv["blocks"] is None:
            tries.append(Spec(**{**asdict(r), "blocks": max(3, r.blocks - 1), "budget_s": 12.0}))
        easier = {"hard": "medium", "medium": "easy"}.get(r.difficulty)
        if easier:
            tries.append(Spec(**{**asdict(r), "difficulty": easier, "budget_s": 12.0}))
        for k, t in enumerate(tries):
            try:
                d, full, stats = generate(t, log)
                break
            except ValueError as e:
                if k == len(tries) - 1:
                    raise
                log(f"  {e}; relaxing the spec...")
        if k > 0:
            B.engine_note(brief, "level", f"no level of exactly the requested kind could be built in time, so the "
                                          f"closest one was made instead ({tries[k].difficulty}, {tries[k].blocks} "
                                          f"blocks).")
        path.write_text(json.dumps(d, indent=2))
        meta = {"rating": asdict(full) | {"naive_ratio": round(full.naive_ratio, 3)}, "stats": stats}
        meta_path.write_text(json.dumps(meta, indent=1))
        log(f"generated in {stats['seconds']} s ({stats['tried']} tried, {stats['solvable']} solvable): "
            f"{full.min_drags} drags, {full.extra_drags} repositioning, naive {full.naive_ratio:.2f}x -> {BAND_WORDS[stats['band']]}")
    rt, band = meta["rating"], meta["stats"]["band"]
    hand = Path(__file__).resolve().parents[2] / "data" / "levels" / "gen" / "narrow_center_01.json"
    if (band != r.difficulty and r.shape == "narrow_center" and r.difficulty == "hard"
            and (r.width, r.height) == (6, 8) and lv["blocks"] is None and not lv["colours"] and hand.is_file()):
        B.engine_note(brief, "level", "the generator's best narrow-centre board in the time budget was not a fair hard "
                                 "level, so the hand-checked one of the same shape (6x8, 7 blocks) is used.")
        return hand, ("the hand-checked hard narrow-centre level, 6x8, 7 blocks: 9 drags minimum, 2 repositioning, "
                      "naive player 1.29x")
    if band != r.difficulty:
        B.engine_note(brief, "difficulty_pacing", f"no {r.difficulty} level of this shape and size turned up in the time "
                                             f"budget; the closest one rates {BAND_WORDS[band]} ({rt['min_drags']} drags, "
                                             f"{rt['extra_drags']} repositioning).")
    why = (f"a generated {BAND_WORDS[band]} {SHAPE_WORDS[r.shape]} level, {r.width}x{r.height}, {rt['blocks']} blocks: "
           f"{rt['min_drags']} drags minimum, {rt['extra_drags']} repositioning, naive player "
           f"{rt['naive_ratio']:.2f}x")
    return path, why
