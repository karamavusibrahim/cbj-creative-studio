"""How hard a level is: the minimum solution, plus how a naive player fares.

Two kinds of numbers:
- From the solver: minimum drags, drags spent repositioning instead of exiting, and how
  many blocks can leave at the very start.
- From a simulated naive player (the "simulated human" idea used to rate puzzle
  difficulty): it takes an exit whenever one is available, otherwise drags a random block
  to a random reachable cell it has not had the board in before (a person does not go back
  to a position they already tried). The more drags it needs compared with the minimum, the
  easier it is to go wrong on that board. The same naive moves are the believable
  mistakes a near-fail creative can show. It gives up after 12 drags per block; a board it
  often gives up on is a maze, not a puzzle (the generator's fairness rule).

The numbers are descriptive. Bands like "easy" or "hard" need calibration against real
player data, so none are assigned here.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .level import Level
from .rules import initial_state, occupancy
from .solver import Solution, apply_drag, drag_outcomes, solve_fast


@dataclass(frozen=True)
class Difficulty:
    level_name: str
    blocks: int
    min_drags: int
    extra_drags: int  # repositioning drags in the minimum solution
    exits_at_start: int  # blocks that can leave with their first drag
    first_moves: int  # distinct results of the first drag
    naive_mean: float  # average drags the naive player needs
    naive_p90: int  # 90th percentile
    naive_capped: int  # runs that hit the cap without clearing
    runs: int

    @property
    def naive_ratio(self) -> float:
        return self.naive_mean / self.min_drags if self.min_drags else 1.0


CAP_PER_BLOCK = 12


def naive_play(level: Level, rng: random.Random, cap: int = 200) -> int | None:
    """Drags a naive player uses to clear the level, or None if it hits the cap. It never drags
    into a position it has had before, unless every drag leads back to one."""
    state = initial_state(level)
    seen = {state}
    for used in range(cap):
        if all(p is None for p in state):
            return used
        occ = occupancy(level, state)
        moves = []
        for bid, pivot in enumerate(state):
            if pivot is not None:
                moves.extend(drag_outcomes(level, state, bid, occ, paths=False))
        exits = [m for m in moves if m.exits]
        if exits:
            state = apply_drag(state, rng.choice(exits))
        else:
            fresh = [m for m in moves if apply_drag(state, m) not in seen]
            state = apply_drag(state, rng.choice(fresh or moves))
        seen.add(state)
    return used + 1 if all(p is None for p in state) else None


def rate(level: Level, runs: int = 200, seed: int = 0, cap: int | None = None,
         solution: Solution | None = None) -> Difficulty | None:
    """Difficulty numbers for a level, or None if it is unsolvable. The minimum comes from the A*
    solver (the same minimum as the BFS one, about 100x faster on hard boards), or from a solution
    already found. extra_drags is the minimum minus the blocks, so it does not depend on which
    shortest solution is found."""
    sol = solution or solve_fast(level)
    if sol is None:
        return None
    state = initial_state(level)
    occ = occupancy(level, state)
    exits_at_start = 0
    first_moves = 0
    for bid in range(len(level.blocks)):
        outs = drag_outcomes(level, state, bid, occ, paths=False)
        first_moves += len(outs)
        exits_at_start += any(o.exits for o in outs)
    rng = random.Random(seed)
    cap = cap or CAP_PER_BLOCK * max(1, len(level.blocks))
    results = [naive_play(level, rng, cap) for _ in range(runs)]
    done = sorted(r for r in results if r is not None)
    capped = runs - len(done)
    # The mean is over the runs that finished; the ones that gave up are counted apart
    # (naive_capped), and the generator refuses boards where more than a few do.
    counted = done or [cap]
    return Difficulty(
        level_name=level.name,
        blocks=len(level.blocks),
        min_drags=sol.min_drags,
        extra_drags=sol.extra_drags,
        exits_at_start=exits_at_start,
        first_moves=first_moves,
        naive_mean=sum(counted) / len(counted),
        naive_p90=counted[min(len(counted) - 1, int(0.9 * len(counted)))],
        naive_capped=capped,
        runs=runs,
    )
