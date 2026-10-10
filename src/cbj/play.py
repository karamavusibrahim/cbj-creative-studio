"""Scenario scripts: turn a level and a requested ending into human-looking play.

The solver gives the shortest solution, which plays like a robot. A scenario adds what a
real player does and what an ad needs:
- believable mistakes, modelled on the "I can't reach <colour>" ads: a trapped block dragged
  toward its gate until a blocker stops it, a blocker moved the wrong way, or at most one
  short fidget. Each costs the player 1-2 extra drags; the solver re-plans after it;
- hesitations: a block picked up, held, and put down again;
- pauses chosen by what the player is doing (seeing an exit, thinking, stuck, recovering
  from a mistake, the quick closing drags), in whole frames;
- a clock set so the game itself shows the ending: 0:01 left on a near-fail win, 0:08 at a
  cliffhanger's cut, 0:00 one cell short of the gate on a time-out.

Timing is exact, not estimated. One dry run of the real game (`capture=False`) logs every
frame. A pause shifts every later frame by exactly its length, so the clock and the video
length are fitted by changing pauses only, never finger speeds, and the recording must land
on the predicted frames. The seed chooses the mistakes and hesitations, nothing else, so the
same level, ending and seed always give the same play.json.
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from .describe import block_labels, color_name
from .difficulty import Difficulty
from .level import Level
from .render import DragPacing, Pacing, make_job, run_player
from .rules import State, initial_state, is_position_valid, occupancy
from .solver import Drag, _with_full_path, apply_drag, drag_outcomes, replay, solve_fast as solve

FPS = 30
ENDINGS = ("win", "near_fail", "cliffhanger", "time_out")
END_MODE = {"win": "win", "near_fail": "win", "cliffhanger": "cut", "time_out": "fail"}

# Finger speed as whole frames per cell (the runner moves the finger one cell per this many
# frames), so a speed never changes the timing by part of a frame.
CONFIDENT, NORMAL, CAREFUL, TENTATIVE = 4, 5, 6, 8  # 7.5, 6, 5 and 3.75 cells per second
PICKUP_QUICK, PICKUP_NORMAL, PICKUP_CAREFUL = 3, 4, 5  # finger down before the block moves

# Pause before a drag, in frames: (shortest, usual, longest). Fitting stays inside these.
PAUSES = {
    "start": (0, 0, 0),  # the first touch; the board is already on screen (start hold)
    "confident": (11, 14, 18),  # 0.35-0.6 s: an exit the player can see
    "thinking": (27, 36, 48),  # 0.9-1.6 s: a block has to be moved out of the way first
    "stuck": (54, 63, 75),  # 1.8-2.5 s: after the last mistake, or before a time-out's last drag
    "before_mistake": (18, 24, 30),  # 0.6-1.0 s: mistakes are made with confidence
    "after_mistake": (36, 48, 60),  # 1.2-2.0 s: noticing it did not help
    "cascade": (9, 11, 14),  # 0.3-0.45 s: the quick closing drags of a win
    "hesitate": (11, 14, 18),  # reaching for a block the player then doubts
}
MIN_PAUSE_F = 5  # shorter than this and two drags read as one
TRAVEL_CELLS_PER_F = 2  # a pause grows a frame per two cells the finger travels to the next block
HESITATE_HOLD_F = 21  # lift, hold 0.7 s, put down
MISTAKE_PUSH_CELLS, MISTAKE_HOLD_F = 0.3, 8  # a blocked attempt presses into the blocker
BUMP_PUSH_CELLS, BUMP_HOLD_F = 0.35, 24  # the cliffhanger's last beat: 0.8 s against the blocker
LIFT_HOLD_F = 45  # a time-out on a one-cell exit: the clock runs out with the block in hand
CASCADE_DRAGS = 3

NEAR_FAIL_LEFT_S = 1.5  # clock left when the last block starts leaving: the HUD shows 00:01
NEAR_FAIL_RANGE_S = (1.3, 1.7)
CLIFF_LEFT_S = 8  # clock left at a cliffhanger's cut: the HUD shows 00:08
CLIFF_RANGE_S = (5, 12)
CALM_MARGIN_S = 55  # a plain win keeps the clock above 0:50, where the HUD flashes red
CALM_FLOOR_S = 50
END_HOLD_S = {"win": 2.5, "near_fail": 2.5, "cliffhanger": 1.0, "time_out": 2.5}
START_HOLD_S = 1.0

MAX_MISTAKE_COST = 2  # a mistake adds 1-2 drags to the solution (0 would be progress)
MISTAKE_MAX_CELLS = 4  # mistakes are short drags
CLIFF_MAX_STATES = 50_000  # search limit for a cliffhanger position
DRY_TIMER_S = 999  # clock for dry runs, long enough never to run out

# A time-out only reads as real on a level that is actually hard (policy: opt-in, social tests).
TIME_OUT_MIN_EXTRA_DRAGS = 1
TIME_OUT_MIN_NAIVE_RATIO = 1.1


@dataclass(frozen=True)
class Beat:
    kind: str  # "solve", "mistake", "hesitate", "bump" (cliffhanger), "short" (time-out)
    drag: Drag
    pause: str  # a PAUSES key: why the player waits before this drag
    pause_f: int  # frames before the drag
    pickup_f: int  # frames with the finger down before the block moves
    frames_per_cell: int
    note: str
    push_cells: float = 0.0
    hold_f: int = 0
    push_dir: tuple[int, int] | None = None  # None: the way the path last moved

    def pacing(self, fps: int = FPS) -> DragPacing:
        return DragPacing(self.pause_f / fps, self.pickup_f / fps, fps / self.frames_per_cell,
                          self.push_cells, self.hold_f / fps, self.push_dir)


@dataclass
class PlayScript:
    level_name: str
    ending: str
    seed: int
    beats: list[Beat]
    left: int = 0  # blocks still on the board at the end
    timer_s: int | None = None  # the clock for the recording; None keeps the level's own
    fit: dict = field(default_factory=dict)
    measured: dict = field(default_factory=dict)
    difficulty: dict | None = None
    hud_label: int | None = None
    notes: list[str] = field(default_factory=list)  # what the plan had to change from the request

    @property
    def drags(self) -> list[Drag]:
        return [b.drag for b in self.beats]

    def to_dict(self, level: Level) -> dict:
        labels = block_labels(level)
        return {
            "level": self.level_name,
            "ending": self.ending,
            "end_mode": END_MODE[self.ending],
            "seed": self.seed,
            "left": self.left,
            "fps": FPS,
            "timer_s": self.timer_s,
            "hud_label": self.hud_label,
            "notes": self.notes,
            "difficulty": self.difficulty,
            "beats": [
                {
                    "kind": b.kind,
                    "block": b.drag.block,
                    "label": labels[b.drag.block],
                    "path": [list(c) for c in b.drag.path],
                    "exits": b.drag.exits,
                    "exit_index": b.drag.exit_index,
                    "pause": b.pause,
                    "pause_f": b.pause_f,
                    "pickup_f": b.pickup_f,
                    "frames_per_cell": b.frames_per_cell,
                    "push_cells": b.push_cells,
                    "push_dir": list(b.push_dir) if b.push_dir else None,
                    "hold_f": b.hold_f,
                    "note": b.note,
                }
                for b in self.beats
            ],
            "fit": self.fit,
            "measured": self.measured,
        }

    @staticmethod
    def from_dict(d: dict) -> "PlayScript":
        beats = [Beat(b["kind"], Drag(b["block"], tuple(tuple(c) for c in b["path"]), b["exits"], b["exit_index"]),
                      b["pause"], b["pause_f"], b["pickup_f"], b["frames_per_cell"], b["note"],
                      b["push_cells"], b["hold_f"], tuple(b["push_dir"]) if b.get("push_dir") else None)
                 for b in d["beats"]]
        return PlayScript(d["level"], d["ending"], d["seed"], beats, d["left"], d["timer_s"], d.get("fit", {}),
                          d.get("measured", {}), d.get("difficulty"), d.get("hud_label"), d.get("notes", []))


# ---------- mistakes ----------

@dataclass(frozen=True)
class Mistake:
    kind: str  # "blocked", "wrong_way", "fidget"
    drag: Drag
    cost: int | None  # extra drags it adds to the solution (None: not measured)
    score: float
    note: str


def _name(level: Level, bid: int) -> str:
    return f"{block_labels(level)[bid]} ({color_name(level.blocks[bid].color)})"


def _gate_distance(level: Level, block_id: int, pivot) -> int:
    """Manhattan distance from the block's pivot to the nearest gate cell of its colour."""
    color = level.blocks[block_id].color
    cells = [c for e in level.exits if e.color == color for c in e.cells]
    if not cells:
        return 99
    return min(abs(pivot[0] - x) + abs(pivot[1] - y) for x, y in cells)


def _can_exit_now(level: Level, state: State, bid: int, occ) -> bool:
    return any(o.exits for o in drag_outcomes(level, state, bid, occ, paths=False, first_exit_only=True))


def _blocker_ahead(level: Level, bid: int, drag: Drag, occ) -> int | None:
    """The block that stops this drag going one cell further the way it was heading, if the
    only thing in the way is a block (not the edge or a hole)."""
    if len(drag.path) < 2:
        return None
    (ax, ay), (bx, by) = drag.path[-2], drag.path[-1]
    nxt = (2 * bx - ax, 2 * by - ay)
    cells = level.blocks[bid].cells_at(nxt)
    if not all(level.is_active(c) for c in cells):
        return None
    holders = {occ.get(c) for c in cells} - {None, bid}
    return min(holders) if holders else None


def blocked_attempts(level: Level, state: State) -> list[tuple[Drag, int]]:
    """A trapped block (it cannot leave yet) dragged toward its gate until another block stops
    it: the canonical mistake in the winning ads. Returns (drag, blocker) pairs."""
    occ = occupancy(level, state)
    out = []
    for bid, pivot in enumerate(state):
        if pivot is None or _can_exit_now(level, state, bid, occ):
            continue
        before = _gate_distance(level, bid, pivot)
        for o in drag_outcomes(level, state, bid, occ, paths=True):
            if o.exits or not 1 <= o.cells_moved <= MISTAKE_MAX_CELLS:
                continue
            closer = _gate_distance(level, bid, o.end) < before
            last_step_closer = _gate_distance(level, bid, o.path[-1]) < _gate_distance(level, bid, o.path[-2])
            blocker = _blocker_ahead(level, bid, o, occ)
            if closer and last_step_closer and blocker is not None:
                out.append((o, blocker))
    return out


def bumps(level: Level, state: State) -> list[tuple[Drag, int, tuple[int, int] | None]]:
    """Ways to show a trapped block that cannot get to its gate: (drag, blocker, push_dir).
    Moving attempts first (blocked_attempts, pushed the way they moved), then a block pushed
    straight into a blocker next to it (one-cell drag, push_dir set)."""
    out = [(d, blocker, None) for d, blocker in
           sorted(blocked_attempts(level, state), key=lambda t: (t[0].cells_moved, t[0].block, t[0].path))]
    occ = occupancy(level, state)
    for bid, pivot in enumerate(state):
        if pivot is None or _can_exit_now(level, state, bid, occ):
            continue
        here = _gate_distance(level, bid, pivot)
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            nxt = (pivot[0] + dx, pivot[1] + dy)
            if _gate_distance(level, bid, nxt) >= here:
                continue
            blocker = _blocker_ahead(level, bid, Drag(bid, ((pivot[0] - dx, pivot[1] - dy), pivot), False), occ)
            if blocker is not None:
                out.append((Drag(bid, (pivot,), False), blocker, (dx, dy)))
    return out


def mistake_options(level: Level, state: State, allow_fidget: bool = True) -> list[Mistake]:
    """Legal drags that cost the player 1-2 extra drags, most believable first:
    - blocked: a trapped block dragged toward its gate until a blocker stops it;
    - wrong_way: a block the solution has to move, moved somewhere that does not help;
    - fidget: a one-cell nudge of a block that cannot leave yet (at most one per ad).
    A block parked at a gate of another colour is never used: it reads as not knowing the rules."""
    base = solve(level, start=state)
    if base is None:
        return []
    occ = occupancy(level, state)
    to_move = {d.block for d in base.drags if not d.exits}  # blocks the solution repositions
    trapped = {bid for bid, p in enumerate(state) if p is not None and not _can_exit_now(level, state, bid, occ)}

    def cost_of(drag: Drag) -> int | None:
        after = solve(level, start=apply_drag(state, drag))
        if after is None:
            return None
        c = after.min_drags + 1 - base.min_drags
        return c if 1 <= c <= MAX_MISTAKE_COST else None

    options = []
    blocked = set()
    for o, blocker in blocked_attempts(level, state):
        cost = cost_of(o)
        if cost is None:
            continue
        blocked.add((o.block, o.end))
        options.append(Mistake("blocked", o, cost, 3.0 - 0.3 * o.cells_moved - 0.2 * (cost - 1),
                               f"{_name(level, o.block)} heads for its gate, but {_name(level, blocker)} "
                               f"is in the way"))
    for bid, pivot in enumerate(state):
        if pivot is None:
            continue
        for o in drag_outcomes(level, state, bid, occ, paths=True):
            if o.exits or (bid, o.end) in blocked or not 1 <= o.cells_moved <= MISTAKE_MAX_CELLS:
                continue
            if bid in to_move:
                kind, score = "wrong_way", 2.0
                if _gate_distance(level, bid, o.end) < _gate_distance(level, bid, pivot):
                    note = f"{_name(level, bid)} moves toward its gate but stops short, which does not help"
                else:
                    note = f"{_name(level, bid)} is moved the wrong way, which does not help"
            elif allow_fidget and o.cells_moved == 1 and bid in trapped:
                # Only a block that cannot leave: nudging one that could would read as "why not exit?".
                kind, score = "fidget", 1.0
                note = f"{_name(level, bid)} is nudged one cell, which does not help"
            else:
                continue
            cost = cost_of(o)
            if cost is None:
                continue
            options.append(Mistake(kind, o, cost, score - 0.3 * o.cells_moved - 0.2 * (cost - 1), note))
    options.sort(key=lambda m: (-m.score, m.drag.block, m.drag.path))
    return options


def pick_mistake(level: Level, state: State, rng: random.Random, allow_fidget: bool = True) -> Mistake | None:
    """One of the three most believable mistakes, chosen with the seed."""
    options = mistake_options(level, state, allow_fidget)
    return rng.choice(options[:3]) if options else None


def hesitation(state: State, block_id: int) -> Drag:
    """Pick the block up and put it down where it is (a legal no-op drag)."""
    return Drag(block_id, (state[block_id],), False)


# ---------- planning ----------

def _optimal(level: Level, state: State) -> list[Drag]:
    sol = solve(level, start=state)
    if sol is None:
        raise ValueError(f"{level.name}: unsolvable from this position")
    return sol.drags


def to_cliffhanger(level: Level, start: State, left: int, max_states: int = CLIFF_MAX_STATES) -> list[Drag] | None:
    """Drags to a cliffhanger position: only `left` blocks on the board, one of them trapped
    (a bump shows it), and the position still solvable.

    For each set of blocks to keep, a greedy best-first search: positions with fewer of the
    other blocks left come first, then fewer drags. The other blocks leave as soon as they can
    (exit first, as players clear the easy blocks); the kept ones may move but never leave.
    Across sets, a position that still needs a repositioning drag (a real puzzle) beats one
    that does not, then fewer drags, then the earlier set, so the result is deterministic.
    It is not guaranteed to be the shortest route, and it does not look for positions where a
    kept block must move after the others have gone. None if nothing is found within the
    search budget."""
    import heapq
    from itertools import combinations
    on_board = [i for i, p in enumerate(start) if p is not None]
    if len(on_board) < left:
        return None
    best: tuple[int, int, list[Drag]] | None = None  # (not a puzzle, drags, drags list)
    per_set = max(1000, max_states // max(1, math.comb(len(on_board), left)))
    for keep in combinations(on_board, left):
        keep = set(keep)
        parent: dict[State, tuple[State, Drag] | None] = {start: None}
        depth = {start: 0}
        heap = [(len(on_board) - left, 0, 0, start)]
        tick = 0
        while heap and len(parent) < per_set:
            others, d0, _, s = heapq.heappop(heap)
            if best is not None and d0 >= best[1] + (0 if best[0] else 1):
                continue
            if others == 0:
                if not bumps(level, s):
                    continue
                sol = solve(level, start=s)
                if sol is None:
                    continue
                key = (0 if sol.extra_drags >= 1 else 1, d0)
                if best is None or key < best[:2]:
                    drags = []
                    t = s
                    while parent[t] is not None:
                        prev, d = parent[t]
                        drags.append(_with_full_path(level, prev, d))
                        t = prev
                    best = (key[0], key[1], drags[::-1])
                if key[0] == 0:
                    break  # the shortest puzzle for this set
                continue
            occ = occupancy(level, s)
            moves: list[Drag] = []
            for bid, pivot in enumerate(s):
                if pivot is None:
                    continue
                outs = drag_outcomes(level, s, bid, occ, paths=False, first_exit_only=bid not in keep)
                if bid not in keep and any(o.exits for o in outs):
                    moves = [next(o for o in outs if o.exits)]
                    break
                moves.extend(o for o in outs if not o.exits)
            for o in moves:
                ns = apply_drag(s, o)
                if ns not in parent:
                    parent[ns] = (s, o)
                    tick += 1
                    n_others = sum(1 for i, p in enumerate(ns) if p is not None and i not in keep)
                    heapq.heappush(heap, (n_others, d0 + 1, tick, ns))
    return best[2] if best else None


def _solve_note(level: Level, d: Drag) -> str:
    """What the drag shows, from its geometry (captions are built from these notes)."""
    name = _name(level, d.block)
    if d.exits:
        return f"{name} leaves through its gate"
    if _gate_distance(level, d.block, d.end) < _gate_distance(level, d.block, d.start):
        return f"{name} moves toward its gate"
    return f"{name} is moved out of the way"


def _states(level: Level, drags: list[Drag]) -> list[State]:
    """The board before each drag, and after the last."""
    out = [initial_state(level)]
    for d in drags:
        out.append(apply_drag(out[-1], d))
    return out


def _left(state: State) -> int:
    return sum(p is not None for p in state)


def _beat(kind: str, drag: Drag, pause: str, speed: int, pickup: int, note: str, **kw) -> Beat:
    return Beat(kind, drag, pause, PAUSES[pause][1], pickup, speed, note, **kw)


def plan(level: Level, ending: str, mistakes: int | None = None, seed: int = 0, left: int | None = None,
         hesitations: int | None = None) -> PlayScript:
    """Beats for the requested ending, before the clock and length are fitted.

    Defaults (from what the winning ads show):
    - win: no mistakes, no hesitation, a quick closing cascade;
    - near_fail: 1 mistake, 2 hesitations (one on the last block before its final drag);
    - cliffhanger: 2 blocks left; the last beat pushes a trapped block into its blocker;
    - time_out: 1 mistake; the last block's final drag stops one cell short of its gate."""
    if ending not in ENDINGS:
        raise ValueError(f"ending must be one of {', '.join(ENDINGS)}, got {ending!r}")
    n_blocks = len(level.blocks)
    mistakes = {"win": 0, "near_fail": 1, "cliffhanger": 0, "time_out": 1}[ending] if mistakes is None else mistakes
    hesitations = {"win": 0, "near_fail": 2, "cliffhanger": 0, "time_out": 0}[ending] if hesitations is None \
        else hesitations
    if not isinstance(mistakes, int) or isinstance(mistakes, bool) or not 0 <= mistakes <= 3:
        raise ValueError(f"mistakes must be 0 to 3, got {mistakes!r}")
    max_hes = {"win": 1, "near_fail": 2, "cliffhanger": 1, "time_out": 1}[ending]
    if not isinstance(hesitations, int) or isinstance(hesitations, bool) or not 0 <= hesitations <= max_hes:
        raise ValueError(f"hesitations must be 0 to {max_hes} for {ending}, got {hesitations!r}")
    notes: list[str] = []
    if ending == "cliffhanger":
        left = min(2, n_blocks - 1) if left is None else left
        if not 1 <= left < n_blocks:
            raise ValueError(f"left must be 1 to {n_blocks - 1} for this level, got {left}")
    elif ending == "time_out":
        if left not in (None, 1):
            raise ValueError("a time-out ends with exactly one block left, one cell short of its gate")
        left = 1
    else:
        left = 0
    if n_blocks < 2 and ending != "win":
        raise ValueError(f"{level.name}: a single-block level has no room for {ending}")
    rng = random.Random(seed)

    # 1. The drags: the optimal plan, with mistakes in the opening and a re-plan after each.
    state = initial_state(level)
    steps: list[tuple[str, Drag, str, str]] = []  # (kind, drag, role, note)

    def replan(s: State) -> list[Drag]:
        if ending == "cliffhanger":
            drags = to_cliffhanger(level, s, left)
            if drags is not None:
                return drags
        return _optimal(level, s)

    todo = replan(state)
    made, fidget_used, realize = 0, False, False
    next_slot = rng.choice((0, 1, 2)) if mistakes else 0  # the first mistake is drag 1, 2 or 3
    while todo:
        # Never in the last two drags: after a mistake at least three drags remain.
        if made < mistakes and len(steps) >= next_slot and len(todo) >= 3 and _left(state) >= 2:
            m = pick_mistake(level, state, rng, allow_fidget=not fidget_used)
            if m is not None:
                steps.append(("mistake", m.drag, m.kind, m.note))
                state = apply_drag(state, m.drag)
                made += 1
                fidget_used |= m.kind == "fidget"
                todo = replan(state)
                realize = True
                next_slot = len(steps) + 2  # at least two ordinary drags between mistakes
                continue
        d = todo.pop(0)
        # The player takes any obvious exit first, then stops to work out the real fix: the
        # first repositioning drag after a mistake is the "realize" beat.
        role = "realize" if realize and not d.exits else "solve"
        realize &= d.exits
        steps.append(("solve", d, role, _solve_note(level, d)))
        state = apply_drag(state, d)
    if made < mistakes:
        # An easy board may have no believable mistake (every block can just leave); play on
        # without it and say so, rather than fail the request.
        notes.append(f"asked for {mistakes} mistake(s); this board offers {made} believable one(s)")

    # 2. The ending.
    states = _states(level, [s[1] for s in steps])
    if ending == "cliffhanger":
        steps = _cliffhanger_end(level, steps, states, left, rng)
        if steps[-1][0] != "bump":
            notes.append("no trapped block at the cut; the cliffhanger ends on a hesitation")
        # On the way to the standoff, a kept block that heads for its gate until another block
        # stops it is a blocked attempt, and is played like one (pushed, held), not as parking.
        for i, (kind, d, role, note, *extra) in enumerate(steps):
            if kind == "solve" and role == "solve" and not d.exits:
                hit = [b for a, b in blocked_attempts(level, states[i]) if a.block == d.block and a.end == d.end]
                if hit:
                    steps[i] = ("attempt", d, "blocked", f"{_name(level, d.block)} heads for its gate, but "
                                f"{_name(level, hit[0])} is in the way")
    elif ending == "time_out":
        # Drop the last exit and replace it with the same drag stopping one cell short.
        kind, last, role, _ = steps.pop()
        if not last.exits or _left(states[len(steps)]) != 1:
            raise ValueError(f"{level.name}: the plan does not end with the last block leaving")
        name = _name(level, last.block)
        if last.cells_moved >= 2:
            short = Drag(last.block, last.path[:-1], False)
            steps.append(("short", short, "short", f"{name} races for its gate; time runs out one cell short"))
        else:
            short = Drag(last.block, last.path[:1], False)
            steps.append(("short", short, "lift", f"{name} is picked up, one cell from its gate, as time runs out"))

    # 3. Pacing, chosen by what the player is doing.
    last_realize = max((i for i, s in enumerate(steps) if s[2] == "realize"), default=-1)
    solve_idx = [i for i, s in enumerate(steps) if s[0] == "solve"]
    cascade = set(solve_idx[-CASCADE_DRAGS:]) if ending in ("win", "near_fail") else set()
    beats: list[Beat] = []
    for i, (kind, d, role, note, *extra) in enumerate(steps):
        if kind in ("mistake", "attempt"):
            push = dict(push_cells=MISTAKE_PUSH_CELLS, hold_f=MISTAKE_HOLD_F) if role == "blocked" else {}
            b = _beat(kind, d, "before_mistake", CONFIDENT, PICKUP_QUICK, note, **push)
        elif role == "realize":
            stuck = i == last_realize and ending in ("near_fail", "time_out")
            b = _beat("solve", d, "stuck" if stuck else "after_mistake", CAREFUL, PICKUP_CAREFUL, note)
        elif kind == "bump":
            b = _beat("bump", d, "thinking", CAREFUL, PICKUP_NORMAL, note, push_cells=BUMP_PUSH_CELLS,
                      hold_f=BUMP_HOLD_F, push_dir=extra[0] if extra else None)
        elif kind == "short":
            # The clock reaches zero as the block enters its last cell. Hold the pick-up long
            # enough that the race starts with a second on the clock, so the HUD turns from
            # 00:01 to 00:00 during the race (it shows whole seconds, rounded down).
            race_f = d.cells_moved * NORMAL
            pickup = LIFT_HOLD_F if role == "lift" else max(PICKUP_NORMAL, FPS + 3 - race_f)
            b = _beat("short", d, "thinking", NORMAL, pickup, note)
        elif kind == "hesitate":
            b = _beat("hesitate", d, "hesitate", NORMAL, HESITATE_HOLD_F, note)
        elif i in cascade:
            b = _beat("solve", d, "cascade", CONFIDENT, PICKUP_QUICK, note)
        elif d.exits:
            b = _beat("solve", d, "confident", CONFIDENT, PICKUP_QUICK, note)
        else:
            b = _beat("solve", d, "thinking", NORMAL, PICKUP_NORMAL, note)
        beats.append(b)

    # 4. Hesitations: one on the last block before the final drag (near-fail), others before a
    # drag that needs thought, on a block the player considers and then leaves.
    if hesitations:
        states = _states(level, [b.drag for b in beats])
        inserts: list[tuple[int, Beat]] = []
        n = hesitations
        if ending == "near_fail":
            k = len(beats) - 1
            hb = hesitation(states[k], beats[k].drag.block)
            inserts.append((k, _beat("hesitate", hb, "hesitate", NORMAL, PICKUP_QUICK + HESITATE_HOLD_F,
                                     "a moment of doubt on the last block")))
            n -= 1
        late = len(beats) - CASCADE_DRAGS
        # Before a drag that needs thought; not before a stuck pause, which is already a long stop.
        spots = [k for k in range(1, late) if beats[k].pause == "thinking"]
        if n > len(spots):
            spots += [k for k in range(1, late) if beats[k].pause == "after_mistake"]
        if n > len(spots):
            spots += [k for k in range(1, max(2, late)) if k not in spots and beats[k].pause != "stuck"]
        chosen = sorted(rng.sample(spots, n)) if 0 < n <= len(spots) else []
        final_block = beats[-1].drag.block if ending == "near_fail" else None
        for k in chosen:
            others = [bid for bid, p in enumerate(states[k])
                      if p is not None and bid not in (beats[k].drag.block, final_block)]
            occ = occupancy(level, states[k])
            trapped = [bid for bid in others if not _can_exit_now(level, states[k], bid, occ)]
            bid = rng.choice(trapped or others or [beats[k].drag.block])
            inserts.append((k, _beat("hesitate", hesitation(states[k], bid), "hesitate", NORMAL,
                                     PICKUP_QUICK + HESITATE_HOLD_F, f"{_name(level, bid)} is picked up, "
                                     f"then put back: not yet")))
        if len(inserts) < hesitations:
            notes.append(f"asked for {hesitations} hesitation(s); this plan has room for {len(inserts)}")
        for k, hb in sorted(inserts, key=lambda t: -t[0]):
            beats.insert(k, hb)

    beats = _with_travel(level, beats)
    script = PlayScript(level.name, ending, seed, beats, left, notes=notes)
    final = replay(level, script.drags)  # every beat must be legal before Unity sees it
    if _left(final) != left:
        raise AssertionError(f"plan leaves {_left(final)} blocks, expected {left}")
    return script


def _cliffhanger_end(level: Level, steps, states, left: int, rng: random.Random):
    """Cut where `left` blocks remain and one of them is trapped; end with that block pushed
    toward its gate into its blocker. Without such a moment, end on a hesitation instead."""
    cuts = [k for k in range(len(steps) + 1) if _left(states[k]) == left]
    if not cuts:
        raise ValueError(f"{level.name}: the plan never has exactly {left} block(s) left")
    # Keep a mistake out of the last two drags before the cut, as everywhere else.
    last_mistake = max((i for i, st in enumerate(steps) if st[0] == "mistake"), default=-10)
    cuts = [k for k in cuts if k >= last_mistake + 3] or cuts
    for k in reversed(cuts):
        options = bumps(level, states[k])
        if options:
            drag, blocker, push_dir = rng.choice(options[:3])
            note = (f"{_name(level, drag.block)} is pushed toward its gate, but "
                    f"{_name(level, blocker)} is in the way. Can you see the move?")
            return steps[:k] + [("bump", drag, "bump", note, push_dir)]
    k = cuts[-1]
    bid = next(i for i, p in enumerate(states[k]) if p is not None)
    return steps[:k] + [("hesitate", hesitation(states[k], bid), "hesitate",
                         f"{_name(level, bid)} is picked up and put back: which way?")]


def _with_travel(level: Level, beats: list[Beat]) -> list[Beat]:
    """The first drag starts at once; each later pause grows a little with the distance the
    finger travels from where it let go, inside the pause's range."""
    out = []
    prev = None
    for i, b in enumerate(beats):
        if i == 0:
            out.append(replace(b, pause="start", pause_f=0))
        else:
            lo, base, hi = PAUSES[b.pause]
            travel = abs(b.drag.start[0] - prev[0]) + abs(b.drag.start[1] - prev[1])
            out.append(replace(b, pause_f=max(lo, min(hi, base + travel // TRAVEL_CELLS_PER_F))))
        prev = b.drag.end
    return out


# ---------- fitting: pauses only ----------

FIT_ORDER = ("thinking", "stuck", "after_mistake", "before_mistake", "confident", "hesitate", "cascade")


def spread(beats: list[Beat], delta: int, indices: list[int], proportional: bool = True) -> list[Beat]:
    """Add `delta` frames (negative removes them) to the pauses of beats[indices], keeping each
    inside its PAUSES range. proportional: share by the room each pause has (a uniform change
    of pace); otherwise fill pauses in the given order. Raises ValueError if they cannot absorb it."""
    if delta == 0:
        return list(beats)
    up = delta > 0
    room = []
    for i in indices:
        lo, _, hi = PAUSES[beats[i].pause]
        room.append(hi - beats[i].pause_f if up else beats[i].pause_f - max(lo, MIN_PAUSE_F if i else 0))
    total = sum(max(0, r) for r in room)
    need = abs(delta)
    if need > total:
        raise ValueError(f"the pauses can {'add' if up else 'remove'} only {total} frames, {need} needed")
    give = [0] * len(indices)
    if proportional:
        shares = [need * max(0, r) / total for r in room]
        give = [math.floor(s) for s in shares]
        rest = need - sum(give)
        for j in sorted(range(len(indices)), key=lambda j: (-(shares[j] - give[j]), j))[:rest]:
            give[j] += 1
    else:
        for j, r in enumerate(room):
            give[j] = min(max(0, r), need - sum(give))
    out = list(beats)
    for j, i in enumerate(indices):
        if give[j]:
            out[i] = replace(out[i], pause_f=out[i].pause_f + (give[j] if up else -give[j]))
    return out


def length_range(beats: list[Beat], dry_frames: int, fps: int = FPS) -> tuple[float, float]:
    """Shortest and longest video, in seconds, that pauses alone can give this script."""
    idx = range(1, len(beats))
    down = sum(beats[i].pause_f - max(PAUSES[beats[i].pause][0], MIN_PAUSE_F) for i in idx)
    up = sum(PAUSES[beats[i].pause][2] - beats[i].pause_f for i in idx)
    return (dry_frames - down) / fps, (dry_frames + up) / fps


def fit_length(beats: list[Beat], dry_frames: int, target_s: float, fps: int = FPS) -> list[Beat]:
    """Change pauses (all of them, in proportion) so the video lasts target_s. Speeds never
    change: slow fingers read as slow motion. Refuses targets a human pace cannot reach."""
    lo_s, hi_s = length_range(beats, dry_frames, fps)
    if not lo_s <= target_s <= hi_s:
        raise ValueError(f"with human pauses this script plays {lo_s:.1f}-{hi_s:.1f} s, not {target_s:g} s; "
                         f"for longer, use a bigger level, more mistakes, or a hook and end card around it")
    return spread(beats, round(target_s * fps) - dry_frames, list(range(1, len(beats))))


def _shift(dry_beats: list[Beat], beats: list[Beat], upto: int) -> int:
    """Frames by which beat `upto` (and everything after its pause) moves: the sum of the
    pause changes up to and including it."""
    return sum(b.pause_f - a.pause_f for a, b in zip(dry_beats[: upto + 1], beats[: upto + 1]))


def _fit_indices(beats: list[Beat], upto: int) -> list[int]:
    idx = [i for i in range(1, upto + 1)]
    return sorted(idx, key=lambda i: (FIT_ORDER.index(beats[i].pause) if beats[i].pause in FIT_ORDER else 99, i))


def fit_clock(script: PlayScript, level: Level, dry_beats: list[Beat], dry: dict,
              frames: list[dict]) -> tuple[list[Beat], int | None, dict]:
    """The clock that makes the game show the ending, from a dry run timed with DRY_TIMER_S.
    Returns the beats (some pauses moved by a few frames), the timer, and what was fitted."""
    beats = script.beats
    last = len(beats) - 1

    def elapsed(frame: int) -> float:
        return DRY_TIMER_S - frames[frame]["timer"]

    if script.ending in ("win", "near_fail"):
        if dry.get("clock_stopped_frame", -1) < 0:
            raise ValueError("the dry run never stopped the clock; the script does not clear the board")
        e = elapsed(dry["clock_stopped_frame"]) + _shift(dry_beats, beats, last) / FPS
        if script.ending == "win":
            if level.timer <= 0 or level.timer >= e + CALM_MARGIN_S:
                return beats, None, {"clock_left_s": round(level.timer - e, 3) if level.timer > 0 else None}
            timer = math.ceil(e + CALM_MARGIN_S)
            return beats, timer, {"clock_left_s": round(timer - e, 3),
                                  "why": "the level's clock would drop below 0:50 and flash red"}
        # Any clock left in NEAR_FAIL_RANGE_S shows 00:01. Try both whole-second timers around the
        # target and every shift that lands in the range, closest to 1.5 s first, until the
        # pauses can absorb it (a short script has little room in its pauses).
        lo, hi = NEAR_FAIL_RANGE_S
        options = []
        for timer in {max(2, math.floor(e + NEAR_FAIL_LEFT_S)), max(2, math.ceil(e + NEAR_FAIL_LEFT_S))}:
            for delta in range(math.ceil((timer - e - hi) * FPS - 1e-6), math.floor((timer - e - lo) * FPS + 1e-6) + 1):
                options.append((abs(timer - e - delta / FPS - NEAR_FAIL_LEFT_S), abs(delta), timer, delta))
        return _first_fit(beats, sorted(options), _fit_indices(beats, last),
                          lambda timer, delta: {"delta_f": delta, "clock_left_s": round(timer - e - delta / FPS, 3)})

    if script.ending == "cliffhanger":
        e = elapsed(len(frames) - 1) + _shift(dry_beats, beats, last) / FPS
        timer = math.ceil(e + CLIFF_LEFT_S)
        return beats, timer, {"clock_left_s": round(timer - e, 3)}

    # time_out: the clock reaches zero on the frame the last block enters its final cell (or,
    # for a lift, part-way through the hold).
    d = dry["drags"][last]
    if d.get("cell_frames"):
        target = d["cell_frames"][-1]
    else:
        target = d["start_frame"] + beats[last].pickup_f - 10
    e = elapsed(target) + _shift(dry_beats, beats, last) / FPS
    options = [(abs(round((t - e) * FPS)), 0, t, round((t - e) * FPS)) for t in {max(1, math.floor(e)), math.ceil(e)}]
    order = [last] + [i for i in _fit_indices(beats, last) if i != last]  # the pause before the last drag first
    beats, timer, fit = _first_fit(beats, sorted(options), order, lambda timer, delta: {"delta_f": delta})
    fit["fail_target_frame"] = target + _shift(dry_beats, beats, last)
    return beats, timer, fit


def _first_fit(beats: list[Beat], options: list[tuple], order: list[int], describe):
    """The first (timer, delta) option, in the given order, that the pauses can absorb."""
    for *_, timer, delta in options:
        try:
            return spread(beats, delta, order, proportional=False), timer, describe(timer, delta)
        except ValueError:
            continue
    raise ValueError("the pauses cannot move the clock onto the ending; the script is too short to fit "
                     "(add a hesitation or a mistake)")


# ---------- running ----------

def time_out_allowed(d: Difficulty | None) -> tuple[bool, str]:
    """Policy: a time-out shows a player failing, which reads as real only on a level that is
    actually hard. Easy levels refuse it."""
    if d is None:
        return False, "the level is unsolvable"
    ok = d.extra_drags >= TIME_OUT_MIN_EXTRA_DRAGS and d.naive_ratio >= TIME_OUT_MIN_NAIVE_RATIO
    why = (f"{d.extra_drags} repositioning drag(s), naive player {d.naive_ratio:.2f}x the minimum; a time-out "
           f"needs at least {TIME_OUT_MIN_EXTRA_DRAGS} and {TIME_OUT_MIN_NAIVE_RATIO}x")
    return ok, why


def difficulty_dict(d: Difficulty | None) -> dict | None:
    if d is None:
        return None
    out = asdict(d)
    out["naive_ratio"] = round(d.naive_ratio, 3)
    return out


def predict(dry: dict, dry_beats: list[Beat], beats: list[Beat]) -> list[dict]:
    """Each drag's frames in the recording: the dry run's, moved by the pause changes."""
    out = []
    for i, d in enumerate(dry["drags"]):
        s = _shift(dry_beats, beats, i)
        out.append({k: (d[k] + s if d[k] >= 0 else -1) for k in ("start_frame", "exit_frame", "end_frame")})
    return out


def check_ending(script: PlayScript, result: dict, n_blocks: int, predicted: list[dict] | None = None,
                 fail_target: int | None = None) -> list[str]:
    """What must be true of the recording for this ending."""
    problems = list(result.get("problems", []))
    left = n_blocks - sum(1 for g in result.get("block_gone_frames", []) if g >= 0)
    rem = result.get("timer_end", -1)
    if script.ending == "near_fail":
        lo, hi = NEAR_FAIL_RANGE_S
        if not lo <= rem <= hi:
            problems.append(f"near-fail: the clock stopped with {rem:.2f} s left; it must be {lo}-{hi} s (00:01)")
    if script.ending == "win" and script.timer_s is not None and rem < CALM_FLOOR_S:
        problems.append(f"win: the clock fell to {rem:.1f} s, below 0:50 where it flashes red")
    if script.ending == "cliffhanger":
        lo, hi = CLIFF_RANGE_S
        if not lo <= rem <= hi:
            problems.append(f"cliffhanger: {rem:.1f} s on the clock at the cut, expected {lo}-{hi}")
    if left != script.left:
        problems.append(f"{script.ending}: {left} block(s) left at the end, expected {script.left}")
    if script.ending == "time_out":
        last = result.get("drags", [])[-1:] or [{}]
        if last[0].get("result") != "interrupted":
            problems.append(f"time-out: the last drag was {last[0].get('result')!r}, not cut short by the clock")
        if fail_target is not None and not fail_target - 1 <= result.get("fail_frame", -1) <= fail_target + 2:
            problems.append(f"time-out: the fail screen came at frame {result.get('fail_frame')}, "
                            f"planned {fail_target}")
    if predicted is not None:
        got = result.get("drags", [])
        for k, (p, g) in enumerate(zip(predicted, got), start=1):
            keys = ("start_frame",) if script.ending == "time_out" and k == len(predicted) else \
                ("start_frame", "exit_frame", "end_frame")
            for key in keys:
                if p[key] != g.get(key):
                    problems.append(f"drag {k}: {key} {g.get(key)}, the dry run predicted {p[key]}")
        if len(got) != len(predicted):
            problems.append(f"{len(got)} drags recorded, {len(predicted)} planned")
    return problems


def run(level: Level, level_path: str | Path, script: PlayScript, out_dir: str | Path,
        length_s: float | None = None, difficulty: Difficulty | None = None, label: int | None = None,
        **job_kw) -> dict:
    """Dry run, fit the length and the clock (pauses only), record, check. Writes play.json."""
    replay(level, script.drags)
    out = Path(out_dir)
    pacing = Pacing(fps=FPS, start_hold_s=START_HOLD_S, end_hold_s=END_HOLD_S[script.ending])
    dry_mode = {"time_out": "cut"}.get(script.ending, END_MODE[script.ending])
    dry_beats = list(script.beats)
    dry = run_player(make_job(level, level_path, script.drags, out / "dry", pacing, end_mode=dry_mode,
                              size=(270, 480), capture=False, timer=DRY_TIMER_S, label=label,
                              drag_pacing=[b.pacing() for b in dry_beats]))
    if dry["problems"]:
        raise ValueError(f"dry run failed: {dry['problems']}")
    frames = json.loads((out / "dry" / "frames.json").read_text())["frames"]

    fit: dict = {"dry_frames": dry["frames"]}
    if length_s is not None:
        script.beats = fit_length(script.beats, dry["frames"], length_s)
        fit["length_s"] = length_s
    script.beats, script.timer_s, clock = fit_clock(script, level, dry_beats, dry, frames)
    fit.update(clock)
    fit["pause_changes_f"] = [b.pause_f - a.pause_f for a, b in zip(dry_beats, script.beats)]
    predicted = predict(dry, dry_beats, script.beats)
    fit["predicted_frames"] = dry["frames"] + _shift(dry_beats, script.beats, len(script.beats) - 1)
    script.fit = fit
    script.difficulty = difficulty_dict(difficulty)
    from .render import level_label
    script.hud_label = level_label(level) if label is None else label

    result = run_player(make_job(level, level_path, script.drags, out, pacing, end_mode=END_MODE[script.ending],
                                 timer=script.timer_s, label=label,
                                 drag_pacing=[b.pacing() for b in script.beats], **job_kw))
    problems = check_ending(script, result, len(level.blocks), predicted, fit.get("fail_target_frame"))
    if script.ending != "time_out" and result["frames"] != fit["predicted_frames"]:
        problems.append(f"the video has {result['frames']} frames, the dry run predicted {fit['predicted_frames']}")
    script.measured = {
        "frames": result["frames"],
        "duration_s": result["duration_s"],
        "status": result["status"],
        "first_touch_frame": result["first_touch_frame"],
        "clock_stopped_frame": result["clock_stopped_frame"],
        "clock_left_s": round(result["timer_end"], 3),
        "win_frame": result["win_frame"],
        "fail_frame": result["fail_frame"],
        "beat_frames": [[d["start_frame"], d["end_frame"]] for d in result["drags"]],
        "problems": problems,
    }
    # The level as recorded: the same file with the clock the ad used, so the video can be
    # reproduced from the folder alone (the source level keeps its own timer).
    recorded = json.loads(Path(level_path).read_text())
    if script.timer_s is not None:
        recorded["timerCount"] = script.timer_s
    (out / "level.json").write_text(json.dumps(recorded, indent=2))
    script.fit["recorded_level"] = "level.json"
    (out / "play.json").write_text(json.dumps(script.to_dict(level), indent=2))
    result["problems"] = problems
    return result
