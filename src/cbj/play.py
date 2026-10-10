"""Scenario scripts: turn a level and a requested ending into human-looking play.

The solver gives the shortest solution, which plays like a robot. A scenario adds what a
real player does and what an ad needs:
- believable mistakes (legal drags that do not help), after which the solver re-plans;
- hesitations (picking a block up and putting it down again);
- a pacing curve;
- a clock set so the game itself shows the ending: 0:01 left on a near-fail win, 0:00 with
  one block left on a time-out.

Every script is checked with `replay` before Unity sees it. The clock is fitted from a dry
run of the real game (`capture=False`), so the timing is exact rather than estimated.
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .describe import block_labels, color_name
from .level import Level
from .render import DragPacing, Pacing, make_job, run_player
from .rules import State, initial_state, occupancy
from .solver import Drag, apply_drag, drag_outcomes, replay, solve

ENDINGS = ("win", "near_fail", "cliffhanger", "time_out")
END_MODE = {"win": "win", "near_fail": "win", "cliffhanger": "cut", "time_out": "fail"}

# Pacing, in seconds and cells per second.
STEADY = DragPacing(0.6, 0.12, 7.0)  # a confident player
THINK = DragPacing(1.1, 0.25, 5.0)  # a slower, deliberate move
MISTAKE = DragPacing(0.5, 0.10, 7.0)  # made confidently, as real mistakes are
REALIZE = DragPacing(1.2, 0.20, 6.0)  # the move after a mistake: a beat to "notice"
RUSH = DragPacing(0.25, 0.08, 11.0)  # the closing drags of a near-fail
HESITATE_HOLD_S = 0.9  # lift a block, hold, put it down
NEAR_FAIL_REMAINING_S = 1.5  # clock left when the last block starts leaving: shows 0:01
TIME_OUT_HOLD_S = 2.5  # the final hold on the last block in a time-out
MAX_MISTAKE_COST = 2  # a mistake may add at most this many drags to the solution
MISTAKE_MAX_CELLS = 4  # mistakes are short drags
DRY_TIMER_S = 999  # clock for dry runs, long enough never to run out


@dataclass(frozen=True)
class Beat:
    kind: str  # "solve", "mistake", "hesitate"
    drag: Drag
    pacing: DragPacing
    note: str


@dataclass
class PlayScript:
    level_name: str
    ending: str
    seed: int
    beats: list[Beat]
    timer_s: int | None = None
    measured: dict = field(default_factory=dict)

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
            "timer_s": self.timer_s,
            "beats": [
                {
                    "kind": b.kind,
                    "block": b.drag.block,
                    "label": labels[b.drag.block],
                    "path": [list(c) for c in b.drag.path],
                    "exits": b.drag.exits,
                    "exit_index": b.drag.exit_index,
                    "pacing": asdict(b.pacing),
                    "note": b.note,
                }
                for b in self.beats
            ],
            "measured": self.measured,
        }


# ---------- mistakes ----------

def _gate_at(level: Level, block_id: int, pivot) -> int | None:
    """Index of a gate whose cells the block overlaps at this pivot, if any."""
    cells = set(level.blocks[block_id].cells_at(pivot))
    for i, e in enumerate(level.exits):
        if cells & e.cells:
            return i
    return None


def _gate_distance(level: Level, block_id: int, pivot) -> int:
    """Manhattan distance from the block's pivot to the nearest gate cell of its colour."""
    color = level.blocks[block_id].color
    cells = [c for e in level.exits if e.color == color for c in e.cells]
    if not cells:
        return 99
    return min(abs(pivot[0] - x) + abs(pivot[1] - y) for x, y in cells)


def mistake_options(level: Level, state: State) -> list[tuple[float, Drag, str]]:
    """Legal drags that do not help, scored by how believable they look in an ad.

    Highest first:
    - a block that cannot leave yet, dragged onto its own gate ("tried too early");
    - a block parked on a gate of another colour ("wrong gate");
    - a block dragged toward its own gate.
    Short drags score higher. Each option keeps the level solvable with at most
    MAX_MISTAKE_COST extra drags.
    """
    base = solve(level, start=state)
    if base is None:
        return []
    labels = block_labels(level)
    occ = occupancy(level, state)
    options = []
    for bid, pivot in enumerate(state):
        if pivot is None:
            continue
        before = _gate_distance(level, bid, pivot)
        for o in drag_outcomes(level, state, bid, occ, paths=True):
            if o.exits or not 1 <= o.cells_moved <= MISTAKE_MAX_CELLS:
                continue
            after = solve(level, start=apply_drag(state, o))
            if after is None or after.min_drags + 1 - base.min_drags > MAX_MISTAKE_COST:
                continue
            name = f"{labels[bid]} ({color_name(level.blocks[bid].color)})"
            gate = _gate_at(level, bid, o.end)
            score = -0.3 * o.cells_moved
            if gate is not None and level.exits[gate].color == level.blocks[bid].color:
                score += 3.0
                note = f"{name} reaches its gate too early: the way out is still blocked"
            elif gate is not None:
                score += 2.0
                gcol = color_name(level.exits[gate].color)
                note = f"{name} goes to the {gcol} gate by mistake"
            elif _gate_distance(level, bid, o.end) < before:
                score += 1.0
                note = f"{name} heads for its gate, but the path is blocked"
            else:
                note = f"{name} is moved out of the way, which does not help"
            options.append((score, o, note))
    options.sort(key=lambda t: -t[0])
    return options


def pick_mistake(level: Level, state: State, rng: random.Random) -> tuple[Drag, str] | None:
    """One of the three most believable mistakes, chosen with the seed."""
    options = mistake_options(level, state)
    if not options:
        return None
    _, drag, note = rng.choice(options[:3])
    return drag, note


def hesitation(level: Level, state: State, block_id: int) -> Drag:
    """Pick the block up and put it down where it is (a legal no-op drag)."""
    return Drag(block_id, (state[block_id],), False)


# ---------- planning ----------

def _optimal(level: Level, state: State) -> list[Drag]:
    sol = solve(level, start=state)
    if sol is None:
        raise ValueError(f"{level.name}: unsolvable from this position")
    return sol.drags


def _solve_note(level: Level, d: Drag) -> str:
    label = block_labels(level)[d.block]
    name = f"{label} ({color_name(level.blocks[d.block].color)})"
    return f"{name} leaves through its gate" if d.exits else f"{name} is moved out of the way"


def plan(level: Level, ending: str, mistakes: int = 1, seed: int = 0, left: int = 1) -> PlayScript:
    """Beats for the requested ending (before the clock is fitted)."""
    if ending not in ENDINGS:
        raise ValueError(f"ending must be one of {', '.join(ENDINGS)}, got {ending!r}")
    if not isinstance(mistakes, int) or isinstance(mistakes, bool) or not 0 <= mistakes <= 3:
        raise ValueError(f"mistakes must be 0 to 3, got {mistakes!r}")
    rng = random.Random(seed)
    state = initial_state(level)
    beats: list[Beat] = []
    n_blocks = len(level.blocks)

    if ending == "win":
        for d in _optimal(level, state):
            beats.append(Beat("solve", d, STEADY, _solve_note(level, d)))
        return PlayScript(level.name, ending, seed, _first_pause_zero(beats))

    if ending in ("near_fail", "time_out") and mistakes:
        # Mistakes come early, while several blocks remain: a believable "wrong start".
        plan_now = _optimal(level, state)
        # The first mistake comes after the opening drag; later ones spread over the first half.
        slots = [1 + 2 * i for i in range(mistakes)]
        made = 0
        k = 0
        while plan_now:
            if made < mistakes and k in slots and sum(p is not None for p in state) >= 2:
                picked = pick_mistake(level, state, rng)
                if picked is not None:
                    drag, note = picked
                    beats.append(Beat("mistake", drag, MISTAKE, note))
                    state = apply_drag(state, drag)
                    made += 1
                    plan_now = _optimal(level, state)
                    nxt = plan_now[0]
                    beats.append(Beat("solve", nxt, REALIZE, _solve_note(level, nxt)))
                    state = apply_drag(state, nxt)
                    plan_now = plan_now[1:]
                    k += 1
                    continue
            d = plan_now.pop(0)
            beats.append(Beat("solve", d, THINK if k == 0 else STEADY, _solve_note(level, d)))
            state = apply_drag(state, d)
            k += 1
        if made < mistakes:
            raise ValueError(f"{level.name}: found only {made} believable mistake(s) of {mistakes}")
    else:
        for i, d in enumerate(_optimal(level, state)):
            beats.append(Beat("solve", d, THINK if i == 0 else STEADY, _solve_note(level, d)))

    solves = [i for i, b in enumerate(beats) if b.kind == "solve"]
    if ending == "near_fail":
        # The closing drags are rushed, after one last hesitation on the final block.
        for i in solves[-2:]:
            beats[i] = Beat("solve", beats[i].drag, RUSH, beats[i].note)
        last = solves[-1]
        pre_state = initial_state(level)
        for b in beats[:last]:
            pre_state = apply_drag(pre_state, b.drag)
        hold = DragPacing(0.4, HESITATE_HOLD_S, 6.0)
        beats.insert(last, Beat("hesitate", hesitation(level, pre_state, beats[last].drag.block), hold,
                                "a moment of doubt on the last block"))
    elif ending in ("cliffhanger", "time_out"):
        if not 1 <= left < n_blocks:
            raise ValueError(f"left must be 1 to {n_blocks - 1} for this level, got {left}")
        # Drop the closing exits so `left` blocks stay on the board, then hold the next one.
        while sum(1 for b in beats if b.drag.exits) > n_blocks - left:
            beats.pop()
        end_state = initial_state(level)
        for b in beats:
            end_state = apply_drag(end_state, b.drag)
        target = next(i for i, p in enumerate(end_state) if p is not None)
        hold_s = TIME_OUT_HOLD_S if ending == "time_out" else HESITATE_HOLD_S + 0.6
        beats.append(Beat("hesitate", hesitation(level, end_state, target), DragPacing(0.7, hold_s, 6.0),
                          "the finger hovers over the last block"))
    return PlayScript(level.name, ending, seed, _first_pause_zero(beats))


def _first_pause_zero(beats: list[Beat]) -> list[Beat]:
    if beats:
        b = beats[0]
        beats[0] = Beat(b.kind, b.drag, DragPacing(0.0, b.pacing.pickup_s, b.pacing.cells_per_s), b.note)
    return beats


# ---------- clock fitting and running ----------

def fit_timer(script: PlayScript, dry: dict, frames: list[dict]) -> int | None:
    """The level timer that puts the game's clock where the ending needs it, from a dry run
    made with DRY_TIMER_S on the clock. None keeps the level's own timer."""
    def elapsed_at(frame: int) -> float:
        return DRY_TIMER_S - frames[frame]["timer"]

    if script.ending == "near_fail":
        if dry.get("clock_stopped_frame", -1) < 0:
            raise ValueError("the dry run never stopped the clock; the script does not clear the board")
        e = elapsed_at(dry["clock_stopped_frame"])
        # Clock left when it stops = timer - e; floor shows 0:01 for anything in [1, 2).
        return max(2, math.floor(e + NEAR_FAIL_REMAINING_S + 0.5))
    if script.ending == "time_out":
        hold = dry["drags"][-1]
        e0 = elapsed_at(hold["start_frame"])
        # Run out a little after the final pick-up, inside the hold.
        return max(1, math.ceil(e0 + 0.4))
    return None


def check_ending(script: PlayScript, result: dict, n_blocks: int, left: int) -> list[str]:
    """What must be true of the recording for this ending."""
    problems = list(result.get("problems", []))
    gone = sum(1 for g in result.get("block_gone_frames", []) if g >= 0)
    if script.ending == "near_fail":
        rem = result.get("timer_end", -1)
        if not 1.0 <= rem < 2.0:
            problems.append(f"near-fail: the clock stopped with {rem:.2f} s left; it must show 0:01 (1-2 s)")
    if script.ending == "cliffhanger" and n_blocks - gone != left:
        problems.append(f"cliffhanger: {n_blocks - gone} block(s) left, expected {left}")
    if script.ending == "time_out":
        if result.get("status") != "failed":
            problems.append(f"time-out: status {result.get('status')!r}, expected 'failed'")
        if n_blocks - gone != left:
            problems.append(f"time-out: {n_blocks - gone} block(s) left at the fail screen, expected {left}")
    return problems


def run(level: Level, level_path: str | Path, script: PlayScript, out_dir: str | Path, left: int = 1,
        pacing: Pacing = Pacing(), **job_kw) -> dict:
    """Dry run, fit the clock, record, and check. Writes play.json next to the video."""
    drags = script.drags
    replay(level, drags)  # every beat must be legal before Unity sees it
    out = Path(out_dir)
    dry_mode = {"near_fail": "win", "time_out": "cut"}.get(script.ending, END_MODE[script.ending])
    dry = run_player(make_job(level, level_path, drags, out / "dry", pacing, end_mode=dry_mode,
                              size=(270, 480), capture=False, timer=DRY_TIMER_S,
                              drag_pacing=[b.pacing for b in script.beats]))
    if dry["problems"]:
        raise ValueError(f"dry run failed: {dry['problems']}")
    frames = json.loads((out / "dry" / "frames.json").read_text())["frames"]
    script.timer_s = fit_timer(script, dry, frames)
    result = run_player(make_job(level, level_path, drags, out, pacing, end_mode=END_MODE[script.ending],
                                 timer=script.timer_s, drag_pacing=[b.pacing for b in script.beats],
                                 **job_kw))
    problems = check_ending(script, result, len(level.blocks), left)
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
    (out / "play.json").write_text(json.dumps(script.to_dict(level), indent=2))
    result["problems"] = problems
    return result
