"""Level generator: a level built to a spec (shape, size, blocks, piece shapes, looks, colours,
difficulty, gameplay events), solvable, valid for the game's Level Editor, rated, and reproducible
from its seed.

Search, not construction. Candidates are made by placing polyomino blocks at random on a board of
the requested shape, with gates of their colour on the board's rim. Each candidate is checked by
the game's rules (validate), solved exactly (A*, with a state cap), rated (the simulated naive
player in difficulty.py) and scored: the difficulty band first, then the requested events, a
satisfying finish and the looks. The best candidates are then improved by local search (move a
block, move a gate, swap two colours, change a piece; a change is kept when the score improves),
within a time budget.

Why gates go to the far side for hard levels: a block whose gate is across the board must cross
the paths of other blocks, which is what makes repositioning drags necessary. A random gate is
usually reachable at once, so random boards are almost always easy.

Difficulty bands, from the existing measures (descriptive, not calibrated on player data):
- easy: no repositioning drag, at least half the blocks can leave at once, the naive player
  needs at most 1.1x the minimum;
- medium: one repositioning drag, or a naive ratio of 1.1-1.3, and at most a third of the blocks
  can leave at once;
- hard: no block can leave at the start, at least two repositioning drags, a naive ratio of
  1.2-4 (beyond that the board reads as a maze), and the naive player almost always finishes
  (more than 5 % of its runs giving up means the board is unfair).

Looks (a "visually interesting board"): touching blocks of different colours, gates on several
sides, the board's fill near its target, and mirror symmetry when asked; packed boards (55-75 %
of the cells hold blocks) have the real game's "jam" look and share one gate per colour.
"""

from __future__ import annotations

import hashlib
import json
import random
import time
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from .difficulty import Difficulty, rate
from .level import level_from_dict, validate
from .solver import SolverLimitError, solve_fast

SHAPES = ("open", "narrow_center", "door", "holes", "cross", "ring", "lanes")
BANDS = ("easy", "medium", "hard")
COLOURS = ("Green", "Yellow", "Blue", "Red", "Orange", "Purple", "DarkGreen")  # enum BlockColor order
PIECES = {
    "1x1": [(0, 0)], "h2": [(0, 0), (1, 0)], "v2": [(0, 0), (0, -1)], "h3": [(0, 0), (1, 0), (2, 0)],
    "v3": [(0, 0), (0, -1), (0, -2)], "sq": [(0, 0), (0, -1), (1, -1), (1, 0)], "L": [(0, 0), (1, 0), (1, -1)],
    "J": [(0, 0), (0, -1), (1, -1)], "T": [(0, 0), (1, 0), (2, 0), (1, -1)],
    "h4": [(0, 0), (1, 0), (2, 0), (3, 0)], "v4": [(0, 0), (0, -1), (0, -2), (0, -3)],
    "L4": [(0, 0), (0, -1), (0, -2), (1, -2)], "J4": [(0, 0), (0, -1), (0, -2), (-1, -2)],
    "plus": [(0, 0), (-1, 0), (1, 0), (0, 1), (0, -1)],
    "r23": [(0, 0), (1, 0), (0, -1), (1, -1), (0, -2), (1, -2)],
    "r32": [(0, 0), (1, 0), (2, 0), (0, -1), (1, -1), (2, -1)],
}
PIECE_SETS = {
    "mixed": ("1x1", "h2", "v2", "h3", "v3", "sq", "L", "J", "T"),
    "small": ("1x1", "h2", "v2"),
    "long": ("h3", "v3", "h4", "v4"),
    "big": ("sq", "T", "L4", "J4", "plus", "r23", "r32"),
}
STYLES = ("symmetric", "packed", "colourful")
DEFAULTS = {  # (width, height, blocks) when the spec leaves them open
    ("open", "easy"): (6, 6, 5), ("open", "medium"): (6, 7, 6), ("open", "hard"): (7, 8, 7),
    ("narrow_center", "easy"): (6, 8, 5), ("narrow_center", "medium"): (6, 8, 6), ("narrow_center", "hard"): (6, 8, 7),
    ("door", "easy"): (7, 6, 5), ("door", "medium"): (7, 7, 6), ("door", "hard"): (7, 8, 7),
    ("holes", "easy"): (6, 6, 5), ("holes", "medium"): (7, 7, 6), ("holes", "hard"): (7, 8, 7),
    ("cross", "easy"): (7, 7, 5), ("cross", "medium"): (7, 7, 6), ("cross", "hard"): (8, 8, 7),
    ("ring", "easy"): (7, 8, 5), ("ring", "medium"): (7, 8, 6), ("ring", "hard"): (8, 8, 7),
    ("lanes", "easy"): (8, 7, 5), ("lanes", "medium"): (8, 7, 6), ("lanes", "hard"): (8, 8, 7),
}
DIR = {"left": 0, "right": 1, "top": 2, "bottom": 3}
SIDES = {"left": (-1, 0), "right": (1, 0), "top": (0, 1), "bottom": (0, -1)}
MIRROR_SIDE = {"left": "right", "right": "left", "top": "top", "bottom": "bottom"}
TIMER_S = 60
MAX_STATES = 12_000  # boards needing more positions are slow to search and hard to read in an ad
MAX_STATES_HARD = 40_000  # hard boards need more: a lower cap was most of the "2 repositioning" ceiling
MAX_BLOCKS = 12
FAIR_CAPPED = 0.05  # at most this share of the naive player's runs may give up
PACKED_FILL = (0.58, 0.72)


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
    pieces: str = "mixed"  # mixed, small, big, long
    style: list[str] = field(default_factory=list)  # symmetric, packed, colourful
    events: list[dict] = field(default_factory=list)  # the brief's gameplay events (raw)
    finish: str = "auto"  # streak: prefer boards where one move frees every block

    def resolved(self) -> "Spec":
        """Open fields filled in: the shape and band the search will use."""
        band = self.difficulty if self.difficulty in BANDS else "medium"
        # The showcase shape for a plain hard level; a board asked for by its pieces or looks is open.
        plain = self.pieces in ("mixed", "") and not self.style
        shape = self.shape if self.shape in SHAPES else ("narrow_center" if band == "hard" and plain else "open")
        w, h, n = DEFAULTS[(shape, band)]
        w, h = self.width or w, self.height or h
        if "symmetric" in self.style and not _symmetric_mask(holes_for(shape, w, h), w):
            w = w + 1 if w < 9 else w - 1  # e.g. a door down the middle needs an odd width to mirror
        budget = self.budget_s or (40.0 if (shape, band) == ("narrow_center", "hard") else 25.0)
        packed = "packed" in self.style
        return Spec(shape, w, h, self.blocks if packed else (self.blocks or n), list(self.colours), band,
                    self.target_drags, self.seed, budget,
                    self.pieces if self.pieces in PIECE_SETS else "mixed",
                    [s for s in self.style if s in STYLES], list(self.events), self.finish)

    def key(self) -> str:
        """The cache key. Fields at their default are left out, so a spec written before they
        existed keeps its key (and its cached level)."""
        d = asdict(self)
        for k, default in (("pieces", "mixed"), ("style", []), ("events", []), ("finish", "auto")):
            if d[k] == default:
                del d[k]
        return hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()[:12]


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
    if shape == "cross":  # a plus-shaped board: the four corners cut away
        c = max(1, min(w, h) * 2 // 7)
        return {(x, y) for x in range(w) for y in range(h) if (x < c or x >= w - c) and (y < c or y >= h - c)}
    if shape == "ring":  # a big hole in the middle, a band two cells wide all round
        return {(x, y) for x in range(2, w - 2) for y in range(2, h - 2)}
    if shape == "lanes":  # walls between two-cell lanes, joined by two open rows at the top and the bottom
        return {(x, y) for x in range(2, w - 1, 3) for y in range(2, h - 2)}
    return set()


def _symmetric_mask(holes, w: int) -> bool:
    return all((w - 1 - x, y) in holes for x, y in holes)


def band_of(d: Difficulty, fair_capped: float = FAIR_CAPPED) -> str:
    """fair_capped: the share of naive runs allowed to give up. The search uses half of it, so a
    board it picks on a 40-run sample stays fair on the final 200-run rating."""
    fair = d.naive_capped <= fair_capped * d.runs
    if d.exits_at_start == 0 and d.extra_drags >= 2 and 1.2 <= d.naive_ratio <= 4.0 and fair:
        return "hard"
    if d.extra_drags == 0 and d.exits_at_start >= max(2, d.blocks // 2) and d.naive_ratio <= 1.1:
        return "easy"
    if (d.extra_drags == 1 or 1.1 <= d.naive_ratio <= 1.3) and d.exits_at_start <= max(1, d.blocks // 3) and fair:
        return "medium"
    return "between"


# ---------- a board: blocks and gates ----------

@dataclass
class Board:
    w: int
    h: int
    holes: set
    blocks: list  # [(piece name, pivot, colour slot index)]
    gates: list  # [(colour slot index, side, cells)]

    def cells(self, i: int) -> list[tuple[int, int]]:
        name, (px, py), _ = self.blocks[i]
        return [(px + ox, py + oy) for ox, oy in PIECES[name]]

    def to_dict(self) -> dict:
        exits = []
        for colour, side, cells in self.gates:
            x0, y0 = cells[0]
            exits.append({"exitNumber": 0, "requiredColor": colour,
                          "gridPosition": {"x": x0, "y": y0}, "direction": DIR[side],
                          "shapeOffsets": [{"x": x - x0, "y": y - y0} for x, y in cells]})
        return {"gridWidth": self.w, "gridHeight": self.h, "timerCount": TIMER_S,
                "inactiveCells": [{"x": x, "y": y} for x, y in sorted(self.holes)],
                "GridBlockDatas": [{"gridPosition": {"x": p[0], "y": p[1]}, "blockColor": c,
                                    "shapeOffsets": [{"x": ox, "y": oy} for ox, oy in PIECES[name]]}
                                   for name, p, c in self.blocks],
                "ExitDatas": exits}


def _rim(active: set, w: int, h: int, side: str, inner: bool) -> set:
    """Cells whose `side` faces no active cell: the board's edge, a cut-away corner, or (inner)
    the rim of a hole inside the board. The game draws a gate on any of them."""
    dx, dy = SIDES[side]
    out = set()
    for x, y in active:
        nx, ny = x + dx, y + dy
        if (nx, ny) in active:
            continue
        if not inner:
            cx, cy = nx, ny
            while 0 <= cx < w and 0 <= cy < h and (cx, cy) not in active:
                cx, cy = cx + dx, cy + dy
            if 0 <= cx < w and 0 <= cy < h:
                continue  # beyond the hole is more board: an inner rim
        out.add((x, y))
    return out


def _span(cells, side: str) -> int:
    """How wide a gate on `side` must be for these cells to pass it."""
    return len({x for x, _ in cells}) if side in ("top", "bottom") else len({y for _, y in cells})


def _windows(rim: set, side: str, width: int, used: set) -> list[list]:
    out = []
    for x, y in sorted(rim):
        cells = [(x + k, y) if side in ("top", "bottom") else (x, y + k) for k in range(width)]
        if all(c in rim and (c, side) not in used for c in cells):
            out.append(cells)
    return out


def _reach(active: set, cells) -> list[frozenset]:
    """Every placement this block can slide to on the empty board (other blocks ignored)."""
    start = frozenset(cells)
    seen, todo = {start}, [start]
    while todo:
        cur = todo.pop()
        for dx, dy in SIDES.values():
            nxt = frozenset((x + dx, y + dy) for x, y in cur)
            if nxt not in seen and nxt <= active:
                seen.add(nxt)
                todo.append(nxt)
    return list(seen)


def _passes(placements: list, window, side: str) -> bool:
    """Can the block stand on the gate and go through it from some placement it can reach? It must
    cover a gate cell, and every cell's column (top, bottom) or row (left, right) must be the
    gate's (rules.is_path_clear); other blocks are not considered."""
    win = set(window)
    axis = 0 if side in ("top", "bottom") else 1
    lanes = {c[axis] for c in window}
    # the game checks for an exit only when the block enters a cell, so a block that cannot move
    # at all never leaves, even standing on its gate
    return len(placements) > 1 and any(pl & win and all(c[axis] in lanes for c in pl) for pl in placements)


def _side_order(rng, cells, w: int, h: int, far: float) -> list[str]:
    cx = sum(x for x, _ in cells) / len(cells)
    cy = sum(y for _, y in cells) / len(cells)
    sides = sorted(SIDES, key=lambda s: {"left": cx, "right": w - 1 - cx, "bottom": cy, "top": h - 1 - cy}[s])
    order = list(reversed(sides)) if rng.random() < far else sides
    return order[:2] + rng.sample(order[2:], 2)


def _touching(board: Board) -> list[tuple[int, int]]:
    owner = {c: i for i in range(len(board.blocks)) for c in board.cells(i)}
    pairs = set()
    for c, i in owner.items():
        for dx, dy in ((1, 0), (0, 1)):
            j = owner.get((c[0] + dx, c[1] + dy))
            if j is not None and j != i:
                pairs.add((min(i, j), max(i, j)))
    return sorted(pairs)


def _assign_colours(board: Board, rng, slots: list[int], spread: bool) -> None:
    """spread: every slot used and touching blocks kept apart (greedy); else round robin."""
    if not spread:
        for i, (name, p, _) in enumerate(board.blocks):
            board.blocks[i] = (name, p, slots[i % len(slots)])
        return
    nbrs = {i: set() for i in range(len(board.blocks))}
    for i, j in _touching(board):
        nbrs[i].add(j)
        nbrs[j].add(i)
    used = {s: 0 for s in slots}
    colour = {}
    for i in sorted(nbrs, key=lambda i: -len(nbrs[i])):
        near = {colour[j] for j in nbrs[i] if j in colour}
        pick = min(slots, key=lambda s: (s in near, used[s], rng.random()))
        colour[i] = pick
        used[pick] += 1
    for i, (name, p, _) in enumerate(board.blocks):
        board.blocks[i] = (name, p, colour[i])


def _place_gate(rng, board: Board, rims: dict, used: set, cells, colour: int, far: float, reach=None) -> bool:
    for side in _side_order(rng, cells, board.w, board.h, far):
        wins = _windows(rims[side], side, _span(cells, side), used)
        if reach is not None:
            wins = [w_ for w_ in wins if _passes(reach, w_, side)]
        if wins:
            win = rng.choice(wins)
            used.update((c, side) for c in win)
            board.gates.append((colour, side, win))
            return True
    return False


def _board(spec: Spec, rng: random.Random) -> Board | None:
    """One random board for the spec."""
    w, h = spec.width, spec.height
    holes = holes_for(spec.shape, w, h)
    active = {(x, y) for x in range(w) for y in range(h)} - holes
    names = list(PIECE_SETS[spec.pieces])
    packed = "packed" in spec.style
    symmetric = "symmetric" in spec.style
    fill = rng.uniform(*PACKED_FILL) if packed else None
    limit = MAX_BLOCKS if packed and spec.blocks is None else spec.blocks
    board = Board(w, h, holes, [], [])
    occ: set = set()
    pairs: list = []  # symmetric: (i, j) mirror pairs; (i, i) a block on the axis
    for _ in range(900 if packed else 600):
        if len(board.blocks) >= limit or (packed and len(occ) >= fill * len(active)):
            break
        name = rng.choice(names)
        px, py = rng.randrange(w), rng.randrange(h)
        cs = [(px + ox, py + oy) for ox, oy in PIECES[name]]
        if any(c not in active or c in occ for c in cs):
            continue
        if not symmetric:
            board.blocks.append((name, (px, py), 0))
            occ.update(cs)
            continue
        mirror = [(w - 1 - x, y) for x, y in cs]
        if set(mirror) == set(cs):  # on the axis and symmetric itself
            board.blocks.append((name, (px, py), 0))
            occ.update(cs)
            pairs.append((len(board.blocks) - 1,) * 2)
            continue
        if set(mirror) & set(cs) or any(c not in active or c in occ for c in mirror):
            continue
        if "colourful" in spec.style and any(abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1 for a in cs for b in mirror):
            continue  # a mirror pair shares a colour, so on a colourful board it must not touch
        mname = _mirror_piece(name)
        if mname is None or len(board.blocks) + 2 > limit + 1:
            continue
        mx = w - 1 - px
        board.blocks += [(name, (px, py), 0), (mname, (mx, py), 0)]
        occ.update(cs + mirror)
        pairs.append((len(board.blocks) - 2, len(board.blocks) - 1))
    if len(board.blocks) < 2:
        return None
    # colours
    if spec.colours:
        slots = [COLOURS.index(c) for c in spec.colours]
    elif "colourful" in spec.style:
        slots = list(range(7))
    elif packed:
        slots = rng.sample(range(7), rng.choice((4, 5, 6)))
    else:
        slots = list(range(7))
    rng.shuffle(slots)
    if symmetric:
        for k, (i, j) in enumerate(pairs):
            for b in {i, j}:
                name, p, _ = board.blocks[b]
                board.blocks[b] = (name, p, slots[k % len(slots)])
    else:
        _assign_colours(board, rng, slots, spread=packed or "colourful" in spec.style)
    # gates: one per block, or one per colour on a packed board (as in the real game)
    far = {"easy": 0.15, "medium": 0.55, "hard": 0.85}[spec.difficulty]
    rims = {s: _rim(active, w, h, s, inner=spec.shape == "ring") for s in SIDES}
    used: set = set()
    if symmetric:
        keep = []
        for i, j in pairs:
            if i == j:
                if _axis_gate(rng, board, rims, used, i):
                    keep.append(i)
                continue
            n_before = len(board.gates)
            if _place_gate(rng, board, rims, used, board.cells(i), board.blocks[i][2], far,
                           _reach(active, board.cells(i))):
                colour, side, win = board.gates[-1]
                msid = MIRROR_SIDE[side]
                mwin = sorted((w - 1 - x, y) for x, y in win)
                if all(c in rims[msid] and (c, msid) not in used for c in mwin):
                    used.update((c, msid) for c in mwin)
                    board.gates.append((colour, msid, mwin))
                    keep += [i, j]
                    continue
                board.gates = board.gates[:n_before]
                used.difference_update((c, side) for c in win)
        if len(keep) < len(board.blocks):
            return None  # a symmetric board must stay symmetric: no block without its gate
        return board
    if packed:
        by_colour: dict[int, list[int]] = {}
        for i, (_, _, c) in enumerate(board.blocks):
            by_colour.setdefault(c, []).append(i)
        for colour, ids in by_colour.items():
            cells = [c for i in ids for c in board.cells(i)]
            span_of = lambda s: max(_span(board.cells(i), s) for i in ids)  # noqa: E731
            reaches = [_reach(active, board.cells(i)) for i in ids]
            placed = False
            for side in _side_order(rng, cells, w, h, far):
                wins = [w_ for w_ in _windows(rims[side], side, span_of(side), used)
                        if all(_passes(rc, w_, side) for rc in reaches)]
                if wins:
                    win = rng.choice(wins)
                    used.update((c, side) for c in win)
                    board.gates.append((colour, side, win))
                    placed = True
                    break
            if not placed:
                return None
        return board
    kept_blocks = []
    for i in range(len(board.blocks)):
        if _place_gate(rng, board, rims, used, board.cells(i), board.blocks[i][2], far, _reach(active, board.cells(i))):
            kept_blocks.append(board.blocks[i])
    board.blocks = kept_blocks
    return board


def _mirror_piece(name: str) -> str | None:
    offs = sorted((-ox, oy) for ox, oy in PIECES[name])
    for other, o2 in PIECES.items():
        if sorted(o2) == offs:
            return other
    # the same cells about another pivot: register the mirrored offsets as their own piece
    mname = f"{name}~"
    if mname not in PIECES:
        PIECES[mname] = offs
    return mname


def _axis_gate(rng, board: Board, rims: dict, used: set, i: int) -> bool:
    """A gate for a block on the mirror axis: top or bottom, centred, so it mirrors onto itself."""
    cells = board.cells(i)
    w = board.w
    for side in rng.sample(["top", "bottom"], 2):
        width = _span(cells, side)
        if (w - width) % 2:
            width += 1
        x0 = (w - width) // 2
        ys = sorted({y for x, y in rims[side]}, reverse=side == "top")
        for y in ys:
            win = [(x0 + k, y) for k in range(width)]
            if all(c in rims[side] and (c, side) not in used for c in win):
                used.update((c, side) for c in win)
                board.gates.append((board.blocks[i][2], side, win))
                return True
    return False


def candidate(spec: Spec, rng: random.Random) -> dict:
    """One random level for the spec, as the game's level JSON (an empty level if none fits)."""
    b = _board(spec, rng)
    if b is None:
        return Board(spec.width, spec.height, holes_for(spec.shape, spec.width, spec.height), [], []).to_dict()
    return b.to_dict()


# ---------- local search ----------

def _mutate(board: Board, spec: Spec, rng: random.Random) -> Board | None:
    """A copy with one change: a block moved, a gate moved, two colours swapped, or a piece changed."""
    b = Board(board.w, board.h, board.holes, list(board.blocks), list(board.gates))
    active = {(x, y) for x in range(b.w) for y in range(b.h)} - b.holes
    op = rng.choice(("move", "gate", "swap", "piece"))
    n = len(b.blocks)
    if op in ("move", "piece"):
        i = rng.randrange(n)
        occ = {c for j in range(n) if j != i for c in b.cells(j)}
        name, (px, py), colour = b.blocks[i]
        if op == "piece":
            name = rng.choice(PIECE_SETS[spec.pieces])
        for _ in range(40):
            if op == "move":
                px, py = rng.randrange(b.w), rng.randrange(b.h)
            cs = [(px + ox, py + oy) for ox, oy in PIECES[name]]
            if all(c in active and c not in occ for c in cs):
                b.blocks[i] = (name, (px, py), colour)
                return b
            if op == "piece":
                name = rng.choice(PIECE_SETS[spec.pieces])
        return None
    if op == "swap":
        i, j = rng.sample(range(n), 2) if n >= 2 else (0, 0)
        if b.blocks[i][2] == b.blocks[j][2]:
            return None
        (ni, pi, ci), (nj, pj, cj) = b.blocks[i], b.blocks[j]
        b.blocks[i], b.blocks[j] = (ni, pi, cj), (nj, pj, ci)
        return b
    # gate: one gate to another side or place, as wide as its blocks need there
    k = rng.randrange(len(b.gates))
    colour, side, win = b.gates[k]
    ids = [i for i in range(n) if b.blocks[i][2] == colour]
    if not ids:
        return None
    used = {(c, s) for g, (_, s, cells) in enumerate(b.gates) if g != k for c in cells}
    rims = {s: _rim(active, b.w, b.h, s, inner=spec.shape == "ring") for s in SIDES}
    s2 = rng.choice(list(SIDES))
    wins = _windows(rims[s2], s2, max(_span(b.cells(i), s2) for i in ids), used)
    if not wins:
        return None
    b.gates[k] = (colour, s2, rng.choice(wins))
    return b


# ---------- scoring ----------

def looks(level, spec: Spec) -> dict:
    """How the board looks, each part 0-1: touching blocks of different colours, gates on several
    sides, the fill near its target, and (when asked) mirror symmetry."""
    from .level import ExitDirection
    owner = {}
    for i, b in enumerate(level.blocks):
        for c in b.cells_at(b.pivot):
            owner[c] = i
    pairs = set()
    for c, i in owner.items():
        for dx, dy in ((1, 0), (0, 1)):
            j = owner.get((c[0] + dx, c[1] + dy))
            if j is not None and j != i:
                pairs.add((min(i, j), max(i, j)))
    contrast = (sum(level.blocks[i].color != level.blocks[j].color for i, j in pairs) / len(pairs)) if pairs else 1.0
    sides = len({e.direction for e in level.exits}) / 4
    free = level.width * level.height - len(level.inactive)
    fill = len(owner) / max(1, free)
    target = 0.65 if "packed" in spec.style else 0.45
    out = {"contrast": round(contrast, 2), "sides": round(sides, 2),
           "fill": round(fill, 2), "fill_score": round(max(0.0, 1 - abs(fill - target) / 0.3), 2)}
    if "symmetric" in spec.style:
        colour_at = {c: level.blocks[i].color for c, i in owner.items()}
        same = sum(colour_at.get((level.width - 1 - x, y)) == col for (x, y), col in colour_at.items())
        mirror_side = {ExitDirection.LEFT: ExitDirection.RIGHT, ExitDirection.RIGHT: ExitDirection.LEFT,
                       ExitDirection.TOP: ExitDirection.TOP, ExitDirection.BOTTOM: ExitDirection.BOTTOM}
        gates = {(c, e.direction, e.color) for e in level.exits for c in e.cells}
        g_same = sum(((level.width - 1 - c[0], c[1]), mirror_side[d], col) in gates for c, d, col in gates)
        out["symmetry"] = round((same + g_same) / max(1, len(colour_at) + len(gates)), 2)
    parts = [out["contrast"], out["sides"], out["fill_score"]] + ([out["symmetry"]] if "symmetry" in out else [])
    out["score"] = round(sum(parts) / len(parts), 2)
    return out


def _events_fit(lvl, spec: Spec, min_drags: int) -> dict | None:
    """How the requested events fit this board: None if they cannot happen in order, else the
    drags they add, the events left out, and stuck events with no trapped block at the start."""
    from .events import SOLVER_ACTIONS, from_brief, solve_events
    from .play import blocked_attempts
    from .rules import initial_state
    evs, notes = from_brief(lvl, spec.events)
    solver = [e for e in evs if e.action in SOLVER_ACTIONS]
    cost = 0
    if solver:
        try:
            sol = solve_events(lvl, solver, max_states=20_000)
        except SolverLimitError:
            return None
        if sol is None:
            return None
        cost = sol.min_drags - min_drags
    start = initial_state(lvl)
    stuck_missing = sum(1 for e in evs if e.action == "stuck"
                        and not any(d.block in e.blocks for d, _ in blocked_attempts(lvl, start)))
    return {"cost": cost, "dropped": len(spec.events) - len(evs), "ties": sum("equally" in n for n in notes),
            "stuck_missing": stuck_missing}


def _score(spec: Spec, d: Difficulty, band: str, look: dict | None = None, ev: dict | None = None,
           streak: float | None = None) -> float:
    """Higher is better: the right band first, then how well it shows that band, then the events,
    a satisfying finish and the looks when they are asked for."""
    s = 100.0 if band == spec.difficulty else (40.0 if band == "between" else 0.0)
    if spec.difficulty == "hard":
        s += 6 * min(d.extra_drags, 4) + 20 * (d.naive_ratio - 1) - 4 * d.exits_at_start
    elif spec.difficulty == "easy":
        s += 2 * d.exits_at_start - 10 * abs(d.naive_ratio - 1)
    else:
        s += 4 * (d.extra_drags == 1) - 5 * abs(d.naive_ratio - 1.2)
    if spec.target_drags:
        s -= 1.5 * abs(d.min_drags - spec.target_drags)
    if spec.blocks is not None:
        s -= 3 * abs(d.blocks - spec.blocks)
    s -= 60 * d.naive_capped / max(1, d.runs)  # a board the naive player cannot finish is unfair
    s -= 4 * max(0.0, d.naive_ratio - 2.0)  # and one that far beyond the minimum reads as a maze
    if look is not None:
        s += (30 if spec.style else 5) * look["score"]
    if ev is not None:
        s -= 8 * ev["cost"] + 40 * ev["dropped"] + 15 * ev["ties"] + 15 * ev["stuck_missing"]
    if streak is not None:
        s += 25 * streak
    return s


def _evaluate(spec: Spec, d: dict, cap: int):
    """(score, rating, band, details) for a candidate, or None if it is invalid, unsolvable, too
    big to search, or cannot play the requested events."""
    try:
        lvl = level_from_dict(d, name="generated")
    except ValueError:
        return None
    if len(lvl.blocks) < 2 or validate(lvl):
        return None
    try:
        sol = solve_fast(lvl, max_states=cap)
    except SolverLimitError:
        return None
    if sol is None:
        return None
    r = rate(lvl, runs=40, seed=1, solution=sol)
    band = band_of(r, FAIR_CAPPED / 2)
    details = {"looks": looks(lvl, spec)}
    if spec.events:
        ev = _events_fit(lvl, spec, sol.min_drags)
        if ev is None:
            return None
        details["events"] = ev
    if spec.finish == "streak" and band == spec.difficulty:
        from .events import best_finish
        f = best_finish(lvl, prefix_cap=3000, dp_cap=4000)
        details["streak"] = round(f.streak / len(lvl.blocks), 2)
    sc = _score(spec, r, band, details["looks"], details.get("events"), details.get("streak"))
    return sc, r, band, details, sol


def generate(spec: Spec, log=None) -> tuple[dict, Difficulty, dict]:
    """The best level for the spec found within its budget: (level JSON, its rating, stats)."""
    spec = spec.resolved()
    rng = random.Random(spec.seed)
    t0 = time.time()
    cap = MAX_STATES_HARD if spec.difficulty == "hard" else MAX_STATES
    pool: list = []  # (score, n, board, rating, band, details), best first
    stats = {"tried": 0, "valid": 0, "solvable": 0, "rated": 0, "in_band": 0, "improved": 0}
    n = 0
    min_blocks = 2 if spec.blocks is None else max(2, spec.blocks - 1)

    def consider(board: Board, how: str) -> bool:
        nonlocal n
        n += 1
        d = board.to_dict()
        if len(d["GridBlockDatas"]) < min_blocks:
            return False
        got = _evaluate(spec, d, cap)
        if got is None:
            return False
        sc, r, band, details, _ = got
        stats["solvable"] += 1
        stats["rated"] += 1
        stats["in_band"] += band == spec.difficulty
        better = not pool or sc > pool[0][0]
        pool.append((sc, n, board, r, band, details))
        pool.sort(key=lambda t: (-t[0], t[1]))
        del pool[4:]
        if better and log:
            extra = ""
            if "events" in details:
                extra += f", events +{details['events']['cost']} drags"
            if "streak" in details:
                extra += f", finish {details['streak']:.0%} in a row"
            log(f"  {how} {stats['tried']}: {r.min_drags} drags ({r.extra_drags} repositioning), "
                f"{r.exits_at_start} can leave at once, naive {r.naive_ratio:.2f}x -> {BAND_WORDS[band]}, "
                f"looks {details['looks']['score']:.2f}{extra}")
        return better

    def good_enough() -> bool:
        if not pool:
            return False
        sc, _, board, r, band, details = pool[0]
        reachable = min(spec.target_drags or 0, len(board.blocks) + {"easy": 0, "medium": 1, "hard": 3}[spec.difficulty])
        if "packed" in spec.style and details["looks"]["fill"] < PACKED_FILL[0] - 0.05:
            return False
        return (band == spec.difficulty and stats["in_band"] >= 3
                and (not spec.target_drags or r.min_drags >= reachable - 1)
                and (not spec.style or details["looks"]["score"] >= 0.75)
                and (not spec.events or details["events"]["cost"] <= 1 and not details["events"]["stuck_missing"]
                     and not details["events"]["dropped"] and not details["events"]["ties"])
                and (spec.finish != "streak" or details.get("streak", 0) >= 0.8))

    # 1. Random boards, for at most 60 % of the budget.
    while time.time() - t0 < 0.6 * spec.budget_s and not good_enough():
        stats["tried"] += 1
        board = _board(spec, rng)
        if board is not None:
            stats["valid"] += 1
            consider(board, "candidate")
    # 2. Local search from the best boards (a symmetric board would lose its symmetry).
    if "symmetric" not in spec.style:
        while pool and time.time() - t0 < spec.budget_s and not good_enough():
            stats["tried"] += 1
            base = pool[min(len(pool) - 1, int(rng.random() * 2))][2]
            child = _mutate(base, spec, rng)
            if child is not None and consider(child, "improved"):
                stats["improved"] += 1
    while not pool and time.time() - t0 < spec.budget_s:  # nothing yet: keep sampling
        stats["tried"] += 1
        board = _board(spec, rng)
        if board is not None:
            consider(board, "candidate")
    if not pool:
        raise ValueError(f"no valid, solvable {spec.shape} {spec.width}x{spec.height} level with {spec.blocks} "
                         f"blocks found in {spec.budget_s:g} s ({stats['tried']} tried)")
    # The final rating uses the full naive-player sample; a pick that falls out of band on it gives
    # way to the next best board that stays in band.
    chosen = None
    for _, _, board, _, band, details in pool:
        d = board.to_dict()
        full = rate(level_from_dict(d, name="generated"))
        if chosen is None:
            chosen = (d, full, details)
        if band_of(full) == spec.difficulty:
            chosen = (d, full, details)
            break
    d, full, details = chosen
    stats.update(seconds=round(time.time() - t0, 1), band=band_of(full), spec=asdict(spec), **details)
    return d, full, stats


SHAPE_WORDS = {"open": "open", "narrow_center": "narrow-centre (hourglass)", "door": "two-room (door)",
               "holes": "pillared", "cross": "cross-shaped", "ring": "ring-shaped", "lanes": "three-lane"}
BAND_WORDS = {"easy": "easy", "medium": "medium", "hard": "hard", "between": "medium-to-hard"}
PIECE_WORDS = {"mixed": "", "small": "small blocks", "big": "big blocks", "long": "long bars"}


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


def board_colours(colours: list[str], events: list[dict], seed: int) -> list[str]:
    """The colours a level uses. A colour an event names must be on the board; colours named only
    to point at a block ("the red block gets stuck") are not the only ones: others join them,
    chosen by the seed."""
    named = list(dict.fromkeys(e["block"]["colour"] for e in events if e["block"].get("colour")))
    pointing = not any(e["block"].get("all") for e in events) and len(named) < 3  # not "colour by colour"
    if named and pointing and set(colours) <= set(named):
        rest = [c for c in COLOURS if c not in named]
        random.Random(seed).shuffle(rest)
        return named + rest[:max(0, 4 - len(named))]
    return colours + [c for c in named if c not in colours]


AVG_CELLS = {"mixed": 2.3, "small": 1.5, "long": 3.3, "big": 4.5}  # measured: big pieces fit less often as a board fills


def _packed_size(blocks: int, pieces: str, shape: str) -> tuple[int, int]:
    """The smallest board on which `blocks` blocks fill about 65 % of the cells."""
    want = blocks * AVG_CELLS[pieces] / 0.65
    sizes = [(5, 5), (5, 6), (6, 6), (6, 7), (7, 7), (7, 8), (8, 8), (8, 9)]
    for w, h in sizes:
        if w * h - len(holes_for(shape, w, h)) >= want:
            return w, h
    return sizes[-1]


def generate_for_brief(brief: dict, cache: Path, log) -> tuple[Path, str]:
    """A generated level for a brief, cached by its spec (the same brief gives the same level)."""
    from . import brief as B
    lv = brief["level"]
    gp = brief["gameplay"]
    difficulty = lv["difficulty"]
    if difficulty == "any":
        difficulty = {"near_fail": "hard", "time_out": "medium", "cliffhanger": "medium", "win": "medium"}[gp["ending"]]
    if difficulty == "hard" and any(e["action"] == "leaves" and e["when"] == "first" for e in gp.get("events") or []):
        difficulty = "medium"
        B.engine_note(brief, "difficulty_pacing", "a hard level has no block that can leave at the start, but the first "
                                                  "move is asked to be an exit; the level is medium.")
    target = _target_drags(brief)
    pieces = lv.get("pieces") or "mixed"
    style = list(lv.get("style") or [])
    events = list(gp.get("events") or [])
    finish = gp.get("finish") or "auto"
    shape = lv["shape"] if lv["shape"] in SHAPES or lv["shape"] == "any" else "any"
    colours = board_colours(list(lv["colours"]), events, gp["seed"] or 0)
    blocks = lv["blocks"]
    if blocks is None:
        # Each block leaves once, so the minimum is the blocks plus the repositioning drags: size the
        # level to the ad's length when the prompt does not give a block count.
        blocks = max(4, min(10, target - {"easy": 0, "medium": 1, "hard": 2}[difficulty]))
    width, height = lv["width"], lv["height"]
    if "packed" in style and width is None and height is None:
        width, height = _packed_size(blocks, pieces, shape if shape != "any" else "open")
    if width is None and height is None and shape in ("any", "open", "holes", "door", "cross", "lanes"):
        width, height = next(wh for n, wh in ((5, (6, 6)), (7, (7, 7)), (9, (7, 9)), (10, (8, 9))) if blocks <= n)
        if shape in ("cross", "lanes") and width < 7:
            width = height = 7
    if lv["blocks"] is None and "packed" not in style:
        # and never more than a board's free space holds with room to move (about 5 free cells a block)
        probe = Spec(shape, width, height, None, [], difficulty).resolved()
        free = probe.width * probe.height - len(holes_for(probe.shape, probe.width, probe.height))
        per = {"mixed": 5, "small": 4, "long": 6, "big": 8}[pieces]
        blocks = max(4 if pieces == "mixed" else 3, min(blocks, free // per))  # 4: as before, so cache keys hold
    spec = Spec(shape=shape, width=width, height=height, blocks=blocks, colours=colours, difficulty=difficulty,
                target_drags=target, seed=gp["seed"] or 0, pieces=pieces, style=style, events=events, finish=finish)
    r = spec.resolved()
    if r.shape == "narrow_center" and (r.width < 4 or r.height < 6):
        r.height = max(r.height, 6)
        B.engine_note(brief, "level", "a narrow centre needs at least 6 rows; 6 are used.")
    if r.shape == "lanes" and (r.width < 7 or r.height < 6):
        r.width, r.height = max(r.width, 7), max(r.height, 6)
        B.engine_note(brief, "level", f"lanes need a board at least 7 wide and 6 tall (two-cell lanes with walls "
                                      f"between them); {r.width}x{r.height} is used.")
    if r.shape in ("ring",) and (r.width < 6 or r.height < 6):
        r.width, r.height = max(r.width, 6), max(r.height, 6)
        B.engine_note(brief, "level", "a ring needs at least 6x6 cells; 6x6 is the smallest used.")
    if "symmetric" in style and r.width != (width or r.width):
        B.engine_note(brief, "level", f"a mirror-symmetric {SHAPE_WORDS[r.shape]} board needs a width of "
                                      f"{r.width}.", status=None)
    if len(r.colours) and r.blocks > len(r.colours) * 2 and "packed" not in style:
        B.engine_note(brief, "level", f"{r.blocks} blocks in {len(r.colours)} colours would repeat colours a lot; "
                                 f"blocks share the requested colours.")
    key = r.key()
    cache.mkdir(parents=True, exist_ok=True)
    path, meta_path = cache / f"gen_{key}.json", cache / f"gen_{key}.meta.json"
    if path.is_file() and meta_path.is_file():
        meta = json.loads(meta_path.read_text())
        log(f"same level spec as before: level {key} reused")
    else:
        kind = " ".join(x for x in (", ".join(style), PIECE_WORDS[r.pieces]) if x)
        log(f"generating {'an' if r.difficulty == 'easy' else 'a'} {r.difficulty} {SHAPE_WORDS[r.shape]} "
            f"{r.width}x{r.height} level{' (' + kind + ')' if kind else ''} with "
            f"{'about ' + str(round(r.width * r.height * 0.65 / AVG_CELLS[r.pieces])) if 'packed' in style else r.blocks}"
            f" blocks (about {r.target_drags} drags for {brief['pacing']['length_s']:g} s)...")
        d = None
        tries = [r]
        if lv["blocks"] is None and "packed" not in style:
            tries.append(replace(r, blocks=max(3, r.blocks - 1), budget_s=12.0))
        easier = {"hard": "medium", "medium": "easy"}.get(r.difficulty)
        if easier:
            tries.append(replace(r, difficulty=easier, budget_s=12.0))
        if events:
            tries.append(replace(r, events=[], budget_s=12.0))
        # Last resorts, so a creative is always made: ordinary pieces and looks, then an open board.
        if r.pieces != "mixed" or r.style:
            tries.append(replace(r, pieces="mixed", style=[], events=[], budget_s=12.0))
        if r.shape != "open":
            tries.append(replace(r, shape="open", pieces="mixed", style=[], events=[], difficulty="medium",
                                 budget_s=12.0))
        for k, t in enumerate(tries):
            try:
                d, full, stats = generate(t, log)
                break
            except ValueError as e:
                if k == len(tries) - 1:
                    raise
                log(f"  {e}; relaxing the spec...")
        if k > 0:
            t = tries[k]
            parts = [f"{t.difficulty}", f"{t.blocks} blocks" if t.blocks else "packed"]
            if t.shape != r.shape:
                parts.append(f"an {SHAPE_WORDS[t.shape]} board")
            if t.pieces != r.pieces or t.style != r.style:
                parts.append("ordinary blocks and looks")
            if events and not t.events:
                parts.append("without the requested order of events")
            what = ", ".join(parts)
            B.engine_note(brief, "level", f"no level of exactly the requested kind could be built in time, so the "
                                          f"closest one was made instead ({what}).")
        path.write_text(json.dumps(d, indent=2))
        meta = {"rating": asdict(full) | {"naive_ratio": round(full.naive_ratio, 3)}, "stats": stats}
        meta_path.write_text(json.dumps(meta, indent=1))
        log(f"generated in {stats['seconds']} s ({stats['tried']} tried, {stats['solvable']} solvable, "
            f"{stats['improved']} improvements): {full.min_drags} drags, {full.extra_drags} repositioning, "
            f"naive {full.naive_ratio:.2f}x -> {BAND_WORDS[stats['band']]}")
    rt, band = meta["rating"], meta["stats"]["band"]
    if lv["blocks"] is not None and rt["blocks"] != lv["blocks"]:
        B.engine_note(brief, "level", f"{lv['blocks']} blocks were asked for; {rt['blocks']} fit on this {r.width}x"
                                      f"{r.height} board{' with ' + PIECE_WORDS[r.pieces] if PIECE_WORDS[r.pieces] else ''} "
                                      f"with room to move.")
    hand = Path(__file__).resolve().parents[2] / "data" / "levels" / "gen" / "narrow_center_01.json"
    plain = r.pieces == "mixed" and not r.style and not r.events and r.finish == "auto"
    if (band != r.difficulty and r.shape == "narrow_center" and r.difficulty == "hard" and plain
            and (r.width, r.height) == (6, 8) and lv["blocks"] is None and not lv["colours"] and hand.is_file()):
        B.engine_note(brief, "level", "the generator's best narrow-centre board in the time budget was not a fair hard "
                                 "level, so the hand-checked one of the same shape (6x8, 7 blocks) is used.")
        return hand, ("the hand-checked hard narrow-centre level, 6x8, 7 blocks: 9 drags minimum, 2 repositioning, "
                      "naive player 1.26x")
    if band != r.difficulty:
        B.engine_note(brief, "difficulty_pacing", f"no {r.difficulty} level of this shape and size turned up in the time "
                                             f"budget; the closest one rates {BAND_WORDS[band]} ({rt['min_drags']} drags, "
                                             f"{rt['extra_drags']} repositioning).")
    kind = ", ".join(x for x in (", ".join(r.style), PIECE_WORDS[r.pieces]) if x)
    why = (f"a generated {BAND_WORDS[band]} {SHAPE_WORDS[r.shape]} level{' (' + kind + ')' if kind else ''}, "
           f"{r.width}x{r.height}, {rt['blocks']} blocks: {rt['min_drags']} drags minimum, {rt['extra_drags']} "
           f"repositioning, naive player {rt['naive_ratio']:.2f}x")
    return path, why
