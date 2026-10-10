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


# The Level Editor's width and height sliders run 1..12 (LevelEditorWindow IntSlider).
MAX_GRID = 12


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _int(d: dict, key: str, where: str, default: int | None = None) -> int:
    """An int field. JsonUtility never writes strings, floats or booleans into an int field."""
    if key not in d:
        if default is not None:
            return default
        raise ValueError(f"{where}{key} is missing")
    v = d[key]
    if not _is_int(v):
        raise ValueError(f"{where}{key} must be an integer, got {v!r}")
    return v


def _vec(v, where: str) -> Vec:
    if not (isinstance(v, dict) and _is_int(v.get("x")) and _is_int(v.get("y"))):
        raise ValueError(f"{where} needs integer x and y, got {v!r}")
    return (v["x"], v["y"])


def _list(d: dict, key: str, where: str) -> list:
    """A list field; missing or null means empty, as JsonUtility leaves the default list."""
    v = d.get(key)
    if v is None:
        return []
    if not isinstance(v, list):
        raise ValueError(f"{where}{key} must be a list, got {type(v).__name__}")
    return v


def _obj(v, where: str) -> dict:
    if not isinstance(v, dict):
        raise ValueError(f"{where} must be an object, got {v!r}")
    return v


def _enum(enum_type, value: int, where: str):
    try:
        return enum_type(value)
    except ValueError:
        names = ", ".join(f"{m.value} {m.name.lower()}" for m in enum_type)
        raise ValueError(f"{where} {value} is not one of: {names}") from None


def _vec_dict(v: Vec) -> dict:
    return {"x": v[0], "y": v[1]}


def level_from_dict(d: dict, name: str = "") -> Level:
    """Parse level JSON. Raises ValueError naming the field for anything malformed."""
    if not isinstance(d, dict):
        raise ValueError(f"level JSON must be an object, got {type(d).__name__}")
    blocks = []
    for i, b in enumerate(_list(d, "GridBlockDatas", "")):
        w = f"GridBlockDatas[{i}]."
        b = _obj(b, w.rstrip("."))
        raw = tuple(_vec(o, f"{w}shapeOffsets[{k}]") for k, o in enumerate(_list(b, "shapeOffsets", w)))
        if "gridPosition" not in b:
            raise ValueError(f"{w}gridPosition is missing")
        blocks.append(
            BlockSpec(
                color=_enum(BlockColor, _int(b, "blockColor", w), f"{w}blockColor"),
                pivot=_vec(b["gridPosition"], f"{w}gridPosition"),
                offsets=normalize_block_offsets(list(raw)),
                raw_offsets=raw,
            )
        )
    exits = []
    for j, e in enumerate(_list(d, "ExitDatas", "")):
        w = f"ExitDatas[{j}]."
        e = _obj(e, w.rstrip("."))
        if "gridPosition" not in e:
            raise ValueError(f"{w}gridPosition is missing")
        exits.append(
            ExitSpec(
                color=_enum(BlockColor, _int(e, "requiredColor", w), f"{w}requiredColor"),
                direction=_enum(ExitDirection, _int(e, "direction", w), f"{w}direction"),
                pivot=_vec(e["gridPosition"], f"{w}gridPosition"),
                raw_offsets=tuple(_vec(o, f"{w}shapeOffsets[{k}]") for k, o in enumerate(_list(e, "shapeOffsets", w))),
                exit_number=_int(e, "exitNumber", w, default=0),
            )
        )
    inactive_list = tuple(_vec(c, f"inactiveCells[{k}]") for k, c in enumerate(_list(d, "inactiveCells", "")))
    return Level(
        width=_int(d, "gridWidth", ""),
        height=_int(d, "gridHeight", ""),
        timer=_int(d, "timerCount", "", default=0),
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
        return problems
    if level.width > MAX_GRID or level.height > MAX_GRID:
        problems.append(f"grid {level.width}x{level.height} is larger than the Level Editor's {MAX_GRID}x{MAX_GRID}")
        return problems
    for c in level.inactive:
        if not level.in_bounds(c):
            problems.append(f"inactive cell {c} is out of bounds")
    seen: dict[Vec, int] = {}
    for i, b in enumerate(level.blocks):
        # dict.fromkeys: a repeated offset is the same cell (ItemFactory writes it twice), not an overlap.
        for c in dict.fromkeys(b.cells_at(b.pivot)):
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
    # The Level Editor keeps at most one gate per cell side (ToggleExitCell replaces it).
    sides: dict[tuple[Vec, ExitDirection], int] = {}
    for j, e in enumerate(level.exits):
        for c in e.cells:
            key = (c, e.direction)
            if key in sides:
                problems.append(f"exits {sides[key]} and {j} share cell {c} on the {e.direction.name.lower()} side")
            else:
                sides[key] = j
    return problems


def load_level(path: str | Path, strict: bool = True) -> Level:
    """Read a level file. Every problem is raised as ValueError starting with the file name."""
    path = Path(path)
    if not path.exists():
        raise ValueError(f"{path}: no such file")
    if not path.is_file():
        raise ValueError(f"{path}: not a file")
    try:
        # utf-8-sig also accepts a file saved with a byte-order mark by a text editor.
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except UnicodeDecodeError:
        raise ValueError(f"{path.name}: not a text file") from None
    except json.JSONDecodeError as e:
        raise ValueError(f"{path.name}: not valid JSON ({e.msg}, line {e.lineno})") from None
    except (ValueError, RecursionError) as e:
        # e.g. integers longer than Python's digit limit, or nesting deeper than the parser allows
        raise ValueError(f"{path.name}: not valid JSON ({type(e).__name__}: {str(e)[:120]})") from None
    try:
        level = level_from_dict(data, name=path.stem)
    except ValueError as e:
        raise ValueError(f"{path.name}: {e}") from None
    if strict:
        problems = validate(level)
        if problems:
            raise ValueError(f"{path.name}: " + "; ".join(problems))
    return level
