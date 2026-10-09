"""Game rules ported from the Unity C# source, on whole cells.

State = one pivot per block (None once the block has exited), indexed like
level.blocks. Everything here is a pure function of (level, state).

Ported behaviour, with the C# it comes from:

* Occupancy (ItemFactory.SpawnBlock, BlockGridService.UpdateBlockPosition):
  every cell a block covers holds that block.
* Valid position (BlockMovementService.IsPositionValid): every block cell is in
  bounds, active, and not held by another block.
* Exit check (ExitService.CanBlockExit):
  1. FindMatchingExit takes the FIRST exit in list order whose colour matches and
     whose cells overlap the block. Later exits are never tried, even if the
     first one's path is blocked.
  2. IsPathClear walks each block cell toward the exit direction. Another block
     on the way fails. On leaving the grid, that cell's column (Top/Bottom) or
     row (Left/Right) must be one of the exit's columns/rows.
     Inactive cells do not block the walk: GridManager.GetCell returns null for
     them and the C# only fails on a non-null cell holding another block.
* When the exit check runs (InputHandler.DragBlock): only while a block is being
  dragged, each time its pivot enters a different cell. A block standing at a
  gate does not leave on its own; it has to be dragged into a cell where the
  check passes. Releasing the block never triggers an exit.
"""

from __future__ import annotations

from .level import DIRECTION_VECTOR, BlockSpec, ExitDirection, ExitSpec, Level, Vec

State = tuple[Vec | None, ...]

# ExitService.IsPathClear stops after 50 steps; kept for fidelity (grids here are < 50).
PATH_SAFETY_STEPS = 50


def initial_state(level: Level) -> State:
    return tuple(b.pivot for b in level.blocks)


def occupancy(level: Level, state: State) -> dict[Vec, int]:
    occ: dict[Vec, int] = {}
    for i, pivot in enumerate(state):
        if pivot is None:
            continue
        for c in level.blocks[i].cells_at(pivot):
            if level.in_bounds(c):
                occ[c] = i
    return occ


def is_position_valid(level: Level, block_id: int, pivot: Vec, occ: dict[Vec, int]) -> bool:
    for c in level.blocks[block_id].cells_at(pivot):
        if not level.is_active(c):
            return False
        holder = occ.get(c)
        if holder is not None and holder != block_id:
            return False
    return True


def find_matching_exit(level: Level, block: BlockSpec, pivot: Vec) -> ExitSpec | None:
    block_cells = set(block.cells_at(pivot))
    for e in level.exits:
        if e.color != block.color:
            continue
        if block_cells & e.cells:
            return e
    return None


def is_path_clear(
    level: Level, block_id: int, pivot: Vec, exit_spec: ExitSpec, occ: dict[Vec, int]
) -> bool:
    dx, dy = DIRECTION_VECTOR[exit_spec.direction]
    horizontal = exit_spec.direction in (ExitDirection.LEFT, ExitDirection.RIGHT)
    exit_indices = {c[1] if horizontal else c[0] for c in exit_spec.cells}

    for part in level.blocks[block_id].cells_at(pivot):
        check = (part[0] + dx, part[1] + dy)
        steps = 0
        while steps < PATH_SAFETY_STEPS:
            steps += 1
            if not level.in_bounds(check):
                index = part[1] if horizontal else part[0]
                if index not in exit_indices:
                    return False
                break
            holder = occ.get(check)  # inactive cells are never in occ -> they do not block
            if holder is not None and holder != block_id:
                return False
            check = (check[0] + dx, check[1] + dy)
    return True


def can_block_exit(level: Level, block_id: int, pivot: Vec, occ: dict[Vec, int]) -> bool:
    """ExitService.CanBlockExit with the dragged block already moved to `pivot`.

    `occ` may still hold the dragged block at its old cells; those are ignored
    because the walk skips cells held by the block itself.
    """
    exit_spec = find_matching_exit(level, level.blocks[block_id], pivot)
    if exit_spec is None:
        return False
    return is_path_clear(level, block_id, pivot, exit_spec, occ)


def matching_exit_index(level: Level, block_id: int, pivot: Vec) -> int | None:
    e = find_matching_exit(level, level.blocks[block_id], pivot)
    return None if e is None else level.exits.index(e)
