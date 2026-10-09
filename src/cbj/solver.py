"""Minimum-drag solver for Color Block Jam levels.

A move is one drag: the player picks a block and slides it through free cells.
On whole cells that is a walk of the block's pivot through 4-adjacent valid
positions (the movement code slides blocks along axes and the collision box is
0.7 of a cell, so any free 1-cell corridor is passable).

While dragging, the game runs the exit check each time the pivot enters a
different cell (rules.py). So a drag ends in one of two ways:

* exit: the first entered cell where the check passes. The block leaves and
  the drag is over, so cells beyond it are not reachable in this drag.
* stop: the player releases the block on any other reachable cell.

The starting cell is not checked when the drag begins, but re-entering it
later is a cell change, so "step away and come back" can trigger an exit there.

Exit-first pruning: if some block can exit now, there is an optimal solution
that starts with that exit. Removing a block never makes another position
invalid, never blocks an exit path, and an early exit only removes a block
sooner. So BFS expands a single exit when one exists, which keeps the result
optimal and cuts branching. `solve(..., prune_exits=False)` turns this off,
and the tests check that both modes agree on every shipped level.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .level import Level, Vec
from .rules import (
    State,
    can_block_exit,
    initial_state,
    is_position_valid,
    matching_exit_index,
    occupancy,
)

STEPS: tuple[Vec, ...] = ((0, 1), (0, -1), (-1, 0), (1, 0))  # up, down, left, right


class SolverLimitError(RuntimeError):
    pass


class ReplayError(ValueError):
    pass


@dataclass(frozen=True)
class Drag:
    block: int
    path: tuple[Vec, ...]  # pivot cells from start (inclusive) to end, 4-adjacent steps
    exits: bool
    exit_index: int | None = None  # index into level.exits when exits is True

    @property
    def start(self) -> Vec:
        return self.path[0]

    @property
    def end(self) -> Vec:
        return self.path[-1]

    @property
    def cells_moved(self) -> int:
        return len(self.path) - 1


@dataclass
class Solution:
    level_name: str
    drags: list[Drag]
    states_explored: int
    blocks: int

    @property
    def min_drags(self) -> int:
        return len(self.drags)

    @property
    def extra_drags(self) -> int:
        """Drags spent repositioning blocks instead of exiting them."""
        return self.min_drags - self.blocks

    @property
    def cells_dragged(self) -> int:
        return sum(d.cells_moved for d in self.drags)


def _path_to(parent: dict[Vec, Vec | None], end: Vec) -> tuple[Vec, ...]:
    out = [end]
    while parent[out[-1]] is not None:
        out.append(parent[out[-1]])  # type: ignore[arg-type]
    return tuple(reversed(out))


def drag_outcomes(level: Level, state: State, block_id: int, occ: dict[Vec, int] | None = None) -> list[Drag]:
    """Every distinct result of dragging one block, with a shortest path to each."""
    start = state[block_id]
    if start is None:
        return []
    if occ is None:
        occ = occupancy(level, state)

    parent: dict[Vec, Vec | None] = {start: None}
    queue: deque[Vec] = deque([start])
    outcomes: list[Drag] = []
    start_exit_found = False

    while queue:
        p = queue.popleft()
        for dx, dy in STEPS:
            n = (p[0] + dx, p[1] + dy)
            if n == start:
                # Coming back to the start cell is a cell change, so it is checked.
                if not start_exit_found and can_block_exit(level, block_id, start, occ):
                    start_exit_found = True
                    outcomes.append(
                        Drag(block_id, _path_to(parent, p) + (start,), True,
                             matching_exit_index(level, block_id, start))
                    )
                continue
            if n in parent or not is_position_valid(level, block_id, n, occ):
                continue
            parent[n] = p
            if can_block_exit(level, block_id, n, occ):
                outcomes.append(Drag(block_id, _path_to(parent, n), True, matching_exit_index(level, block_id, n)))
            else:
                outcomes.append(Drag(block_id, _path_to(parent, n), False))
                queue.append(n)
    return outcomes


def apply_drag(state: State, drag: Drag) -> State:
    s = list(state)
    s[drag.block] = None if drag.exits else drag.end
    return tuple(s)


def _is_goal(state: State) -> bool:
    return all(p is None for p in state)


def solve(level: Level, max_states: int = 2_000_000, prune_exits: bool = True) -> Solution | None:
    """Breadth-first search over drags. Returns a minimum-drag solution, or None if unsolvable."""
    start = initial_state(level)
    if _is_goal(start):
        return Solution(level.name, [], 1, 0)

    parent: dict[State, tuple[State, Drag] | None] = {start: None}
    queue: deque[State] = deque([start])

    while queue:
        s = queue.popleft()
        occ = occupancy(level, s)
        candidates: list[Drag] = []
        for bid, pivot in enumerate(s):
            if pivot is None:
                continue
            outs = drag_outcomes(level, s, bid, occ)
            if prune_exits:
                exits = [o for o in outs if o.exits]
                if exits:
                    candidates = [min(exits, key=lambda o: len(o.path))]
                    break
            candidates.extend(outs)

        for d in candidates:
            ns = apply_drag(s, d)
            if ns in parent:
                continue
            parent[ns] = (s, d)
            if _is_goal(ns):
                drags: list[Drag] = []
                cur = ns
                while parent[cur] is not None:
                    prev, drag = parent[cur]  # type: ignore[misc]
                    drags.append(drag)
                    cur = prev
                drags.reverse()
                return Solution(level.name, drags, len(parent), len(level.blocks))
            queue.append(ns)
        if len(parent) > max_states:
            raise SolverLimitError(f"{level.name}: more than {max_states} states")
    return None


def replay(level: Level, drags: list[Drag]) -> State:
    """Re-check a drag list cell by cell against the rules. Raises ReplayError on any violation.

    This is the same check the Unity replay will enforce: every entered cell is a
    valid position, the exit check fails on every entered cell except the last
    one of an exiting drag, and passes there.
    """
    state = initial_state(level)
    for k, d in enumerate(drags, start=1):
        pivot = state[d.block]
        if pivot is None:
            raise ReplayError(f"drag {k}: block {d.block} already exited")
        if d.path[0] != pivot:
            raise ReplayError(f"drag {k}: path starts at {d.path[0]}, block is at {pivot}")
        if len(d.path) < 2:
            raise ReplayError(f"drag {k}: empty drag")
        occ = occupancy(level, state)
        for i in range(1, len(d.path)):
            a, b = d.path[i - 1], d.path[i]
            if abs(a[0] - b[0]) + abs(a[1] - b[1]) != 1:
                raise ReplayError(f"drag {k}: step {a}->{b} is not one cell")
            if not is_position_valid(level, d.block, b, occ):
                raise ReplayError(f"drag {k}: cell {b} is blocked or off the board")
            exits_here = can_block_exit(level, d.block, b, occ)
            last = i == len(d.path) - 1
            if exits_here and not last:
                raise ReplayError(f"drag {k}: block would exit early at {b}")
            if last and exits_here != d.exits:
                want = "exit" if d.exits else "stop"
                raise ReplayError(f"drag {k}: expected to {want} at {b}, game says exit={exits_here}")
        state = apply_drag(state, d)
    return state
