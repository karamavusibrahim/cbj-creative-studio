"""Level model matching the Unity project's LevelData.

Source of truth: CBJ/Assets/Scripts/LevelData.cs, BlockData.cs, Block.cs.
JSON is what Unity's JsonUtility writes: Vector2Int as {"x":..,"y":..} and enums as ints.

Coordinates: x grows to the right, y grows upward on screen (Unity +z). (0, 0) is the
bottom-left cell. Human-facing text uses 1-based "column" and "row" from the bottom-left.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path

Vec = tuple[int, int]


class BlockColor(IntEnum):
    # Order matches `enum BlockColor` in BlockData.cs.
    GREEN = 0
    YELLOW = 1
    BLUE = 2
    RED = 3
    ORANGE = 4
    PURPLE = 5
    DARK_GREEN = 6


class ExitDirection(IntEnum):
    # Order matches `enum ExitDirection` in LevelData.cs. Top is +y, Bottom is -y.
    LEFT = 0
    RIGHT = 1
    TOP = 2
    BOTTOM = 3


DIRECTION_VECTOR: dict[ExitDirection, Vec] = {
    ExitDirection.LEFT: (-1, 0),
    ExitDirection.RIGHT: (1, 0),
    ExitDirection.TOP: (0, 1),
    ExitDirection.BOTTOM: (0, -1),
}


def normalize_block_offsets(raw: list[Vec]) -> tuple[Vec, ...]:
    """Mirror Block.Initialize: empty -> [(0,0)]; (0,0) is appended if missing."""
    offsets = list(raw) if raw else [(0, 0)]
    if (0, 0) not in offsets:
        offsets.append((0, 0))
    return tuple(offsets)


@dataclass(frozen=True)
class BlockSpec:
    color: BlockColor
    pivot: Vec
    offsets: tuple[Vec, ...]
    raw_offsets: tuple[Vec, ...]  # exactly as stored in the JSON, for round-tripping

    def cells_at(self, pivot: Vec) -> tuple[Vec, ...]:
        px, py = pivot
        return tuple((px + ox, py + oy) for ox, oy in self.offsets)

    @property
    def size(self) -> int:
        return len(set(self.offsets))


@dataclass(frozen=True)
class ExitSpec:
    color: BlockColor
    direction: ExitDirection
    pivot: Vec
    raw_offsets: tuple[Vec, ...]
    exit_number: int  # as stored; Unity overwrites it with list index + 1 at load time

    @property
    def cells(self) -> frozenset[Vec]:
        """ExitService: {gridPosition} plus gridPosition + each shape offset."""
        px, py = self.pivot
        return frozenset({self.pivot} | {(px + ox, py + oy) for ox, oy in self.raw_offsets})


@dataclass(frozen=True)
class Level:
    width: int
    height: int
    timer: int
    inactive: frozenset[Vec]
    blocks: tuple[BlockSpec, ...]
    exits: tuple[ExitSpec, ...]
    name: str = ""
    inactive_order: tuple[Vec, ...] = ()  # JSON order, kept so a round trip does not reorder the file

    def in_bounds(self, cell: Vec) -> bool:
        x, y = cell
        return 0 <= x < self.width and 0 <= y < self.height

    def is_active(self, cell: Vec) -> bool:
        return self.in_bounds(cell) and cell not in self.inactive


def _vec(d: dict) -> Vec:
    return (int(d["x"]), int(d["y"]))


def _vec_dict(v: Vec) -> dict:
    return {"x": v[0], "y": v[1]}


def level_from_dict(d: dict, name: str = "") -> Level:
    blocks = []
    for b in d.get("GridBlockDatas", []) or []:
        raw = tuple(_vec(o) for o in b.get("shapeOffsets", []) or [])
        blocks.append(
            BlockSpec(
                color=BlockColor(int(b["blockColor"])),
                pivot=_vec(b["gridPosition"]),
                offsets=normalize_block_offsets(list(raw)),
                raw_offsets=raw,
            )
        )
    exits = []
    for e in d.get("ExitDatas", []) or []:
        exits.append(
            ExitSpec(
                color=BlockColor(int(e["requiredColor"])),
                direction=ExitDirection(int(e["direction"])),
                pivot=_vec(e["gridPosition"]),
                raw_offsets=tuple(_vec(o) for o in e.get("shapeOffsets", []) or []),
                exit_number=int(e.get("exitNumber", 0)),
            )
        )
    inactive_list = tuple(_vec(c) for c in d.get("inactiveCells", []) or [])
    return Level(
        width=int(d["gridWidth"]),
        height=int(d["gridHeight"]),
        timer=int(d.get("timerCount", 0)),
        inactive=frozenset(inactive_list),
        blocks=tuple(blocks),
        exits=tuple(exits),
        name=name,
        inactive_order=inactive_list,
    )


def level_to_dict(level: Level) -> dict:
    """Same field names and order as the shipped JSON files."""
    return {
        "gridWidth": level.width,
        "gridHeight": level.height,
        "timerCount": level.timer,
        "inactiveCells": [_vec_dict(c) for c in (level.inactive_order or sorted(level.inactive))],
        "GridBlockDatas": [
            {
                "gridPosition": _vec_dict(b.pivot),
                "blockColor": int(b.color),
                "shapeOffsets": [_vec_dict(o) for o in b.raw_offsets],
            }
            for b in level.blocks
        ],
        "ExitDatas": [
            {
                "exitNumber": e.exit_number,
                "gridPosition": _vec_dict(e.pivot),
                "requiredColor": int(e.color),
                "direction": int(e.direction),
                "shapeOffsets": [_vec_dict(o) for o in e.raw_offsets],
            }
            for e in level.exits
        ],
    }


def validate(level: Level) -> list[str]:
    """Problems that would make Unity misbehave or that break solver assumptions."""
    problems: list[str] = []
    if level.width <= 0 or level.height <= 0:
        problems.append(f"grid must be positive, got {level.width}x{level.height}")
    for c in level.inactive:
        if not level.in_bounds(c):
            problems.append(f"inactive cell {c} is out of bounds")
    seen: dict[Vec, int] = {}
    for i, b in enumerate(level.blocks):
        for c in b.cells_at(b.pivot):
            if not level.in_bounds(c):
                problems.append(f"block {i} cell {c} is out of bounds")
            elif c in level.inactive:
                problems.append(f"block {i} cell {c} is on an inactive cell")
            elif c in seen:
                problems.append(f"block {i} overlaps block {seen[c]} at {c}")
            else:
                seen[c] = i
    for j, e in enumerate(level.exits):
        dx, dy = DIRECTION_VECTOR[e.direction]
        for c in e.cells:
            if not level.in_bounds(c):
                problems.append(f"exit {j} cell {c} is out of bounds")
                continue
            if c in level.inactive:
                problems.append(f"exit {j} cell {c} is on an inactive cell, so no block can reach it")
                continue
            # GridManager.NeedsBorder: a side is an edge when it faces the outside of the
            # grid or an inactive cell, so gates may also sit on the rim of a hole.
            beyond = (c[0] + dx, c[1] + dy)
            if level.is_active(beyond):
                problems.append(f"exit {j} cell {c} does not face an edge on its {e.direction.name.lower()} side")
    return problems


def load_level(path: str | Path, strict: bool = True) -> Level:
    path = Path(path)
    level = level_from_dict(json.loads(path.read_text()), name=path.stem)
    if strict:
        problems = validate(level)
        if problems:
            raise ValueError(f"{path.name}: " + "; ".join(problems))
    return level
