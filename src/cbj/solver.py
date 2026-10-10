"""Minimum-drag solver for Color Block Jam levels.

A move is one drag: the player picks a block and slides it through free cells.
On whole cells that is a walk of the block's pivot through 4-adjacent valid
positions. BlockMovementService samples the corners of a 0.8-cell box per block
cell (collisionPadding 0.4 in MovementSettings.asset), so a free 1-cell corridor
is passable, corners cannot be cut, and every cell the game assigns to a block
is a position this model also calls valid.

The game checks for an exit once per frame, when the block's rounded pivot cell
differs from the last one. A fast or diagonal drag can skip a cell, so the game
may skip a check this model makes. That only removes forced exits, which never
help, so the minimum drag count is unaffected. A scripted Unity replay must
still move one cell at a time along an axis and let the pivot settle on each
cell, or it can exit somewhere the script did not plan.

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

from .level import MAX_GRID, Level, Vec
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


def drag_outcomes(
    level: Level,
    state: State,
    block_id: int,
    occ: dict[Vec, int] | None = None,
    paths: bool = True,
    first_exit_only: bool = False,
    cell_limit: int | None = None,
) -> list[Drag]:
    """Every distinct result of dragging one block, in breadth-first order.

    With paths=True each Drag carries a shortest cell path. With paths=False the
    path is just (start, end): the search uses this, because building every path
    costs time proportional to the board size squared. Outcomes come out in order
    of path length, so the first exit is always a shortest one.

    first_exit_only: return [that first exit] as soon as it is found (the solver
    takes only that one). cell_limit: raise SolverLimitError if one drag reaches
    more cells than this, so a huge board cannot stall the search.
    """
    start = state[block_id]
    if start is None:
        return []
    if occ is None:
        occ = occupancy(level, state)

    def path(end: Vec, via: Vec | None = None) -> tuple[Vec, ...]:
        if not paths:
            return (start, end)
        return (_path_to(parent, via) + (end,)) if via is not None else _path_to(parent, end)

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
                    outcomes.append(Drag(block_id, path(start, via=p), True, matching_exit_index(level, block_id, start)))
                    if first_exit_only:
                        return outcomes[-1:]
                continue
            if n in parent or not is_position_valid(level, block_id, n, occ):
                continue
            parent[n] = p
            if cell_limit is not None and len(parent) > cell_limit:
                raise SolverLimitError(
                    f"{level.name or 'level'}: one drag reaches more than {cell_limit} cells, stopped")
            if can_block_exit(level, block_id, n, occ):
                outcomes.append(Drag(block_id, path(n), True, matching_exit_index(level, block_id, n)))
                if first_exit_only:
                    return outcomes[-1:]
            else:
                outcomes.append(Drag(block_id, path(n), False))
                queue.append(n)
    return outcomes


def _with_full_path(level: Level, state: State, drag: Drag) -> Drag:
    """Rebuild the shortest cell path for a drag found with paths=False."""
    for o in drag_outcomes(level, state, drag.block, paths=True):
        if o.end == drag.end and o.exits == drag.exits:
            return o
    raise AssertionError(f"drag of block {drag.block} to {drag.end} is no longer reachable")


def apply_drag(state: State, drag: Drag) -> State:
    s = list(state)
    s[drag.block] = None if drag.exits else drag.end
    return tuple(s)


def _is_goal(state: State) -> bool:
    return all(p is None for p in state)


def solve(level: Level, max_states: int = 2_000_000, prune_exits: bool = True) -> Solution | None:
    """Breadth-first search over drags. Returns a minimum-drag solution, or None if unsolvable.

    Raises SolverLimitError as soon as more than `max_states` positions are stored.
    """
    if not isinstance(max_states, int) or isinstance(max_states, bool) or max_states < 1:
        raise ValueError(f"max_states must be a positive integer, got {max_states!r}")
    # Real boards are at most 12x12, so this cap never changes a real result.
    cell_limit = max(max_states, MAX_GRID * MAX_GRID)
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
            outs = drag_outcomes(level, s, bid, occ, paths=False, first_exit_only=prune_exits,
                                 cell_limit=cell_limit)
            if prune_exits:
                exits = [o for o in outs if o.exits]
                if exits:
                    candidates = [exits[0]]  # shortest exit: outcomes are in path-length order
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
                    drags.append(_with_full_path(level, prev, drag))
                    cur = prev
                drags.reverse()
                return Solution(level.name, drags, len(parent), len(level.blocks))
            queue.append(ns)
            if len(parent) > max_states:
                raise SolverLimitError(f"{level.name or 'level'}: more than {max_states} states, stopped")
    return None


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _checked_drag(d, k: int) -> Drag:
    """Reject anything that is not a well-formed Drag; accept [x, y] lists as cells."""
    if not isinstance(d, Drag):
        raise ReplayError(f"drag {k}: expected a Drag, got {type(d).__name__}")
    if not _is_int(d.block):
        raise ReplayError(f"drag {k}: block must be an integer, got {d.block!r}")
    if not isinstance(d.exits, bool):
        raise ReplayError(f"drag {k}: exits must be true or false, got {d.exits!r}")
    if d.exit_index is not None and not _is_int(d.exit_index):
        raise ReplayError(f"drag {k}: exit_index must be an integer, got {d.exit_index!r}")
    if not isinstance(d.path, (list, tuple)):
        raise ReplayError(f"drag {k}: path must be a list of cells")
    cells = []
    for c in d.path:
        if not (isinstance(c, (list, tuple)) and len(c) == 2 and _is_int(c[0]) and _is_int(c[1])):
            raise ReplayError(f"drag {k}: path cell {c!r} is not [x, y] with integers")
        cells.append((c[0], c[1]))
    return Drag(d.block, tuple(cells), d.exits, d.exit_index)


def replay(level: Level, drags: list[Drag]) -> State:
    """Re-check a drag list cell by cell against the rules. Raises ReplayError on any violation.

    This is the same check the Unity replay will enforce: every entered cell is a
    valid position, the exit check fails on every entered cell except the last
    one of an exiting drag, and passes there.
    """
    state = initial_state(level)
    for k, d in enumerate(drags, start=1):
        d = _checked_drag(d, k)
        if not 0 <= d.block < len(level.blocks):
            raise ReplayError(f"drag {k}: no block {d.block}")
        pivot = state[d.block]
        if pivot is None:
            raise ReplayError(f"drag {k}: block {d.block} already exited")
        if not d.path or d.path[0] != pivot:
            raise ReplayError(f"drag {k}: path does not start at the block's cell {pivot}")
        if len(d.path) == 1:
            # Picking a block up and putting it back is legal in the game and changes nothing.
            if d.exits:
                raise ReplayError(f"drag {k}: a block cannot exit without moving")
            continue
        if d.exits and d.exit_index != matching_exit_index(level, d.block, d.end):
            raise ReplayError(f"drag {k}: exit_index {d.exit_index} is not the gate the game picks at {d.end}")
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
