"""Human-readable boards and drag instructions, plus the JSON move script.

Columns and rows are 1-based from the bottom-left, as the board appears on
screen in Unity (the camera looks at the board with grid +y pointing up).
"""

from __future__ import annotations

from .level import BlockColor, ExitDirection, Level, Vec
from .rules import State
from .solver import Drag, Solution

COLOR_LETTER = {
    BlockColor.GREEN: "G",
    BlockColor.YELLOW: "Y",
    BlockColor.BLUE: "B",
    BlockColor.RED: "R",
    BlockColor.ORANGE: "O",
    BlockColor.PURPLE: "P",
    BlockColor.DARK_GREEN: "D",
}

STEP_WORD = {(0, 1): "up", (0, -1): "down", (-1, 0): "left", (1, 0): "right"}


def color_name(c: BlockColor) -> str:
    return c.name.replace("_", " ").lower()


def block_labels(level: Level) -> list[str]:
    """Colour letter plus a number when a colour appears more than once (Y1, Y2)."""
    counts: dict[BlockColor, int] = {}
    for b in level.blocks:
        counts[b.color] = counts.get(b.color, 0) + 1
    seen: dict[BlockColor, int] = {}
    labels = []
    for b in level.blocks:
        letter = COLOR_LETTER[b.color]
        if counts[b.color] > 1:
            seen[b.color] = seen.get(b.color, 0) + 1
            labels.append(f"{letter}{seen[b.color]}")
        else:
            labels.append(letter)
    return labels


def shape_name(level: Level, block_id: int) -> str:
    offs = set(level.blocks[block_id].offsets)
    xs = [o[0] for o in offs]
    ys = [o[1] for o in offs]
    w, h = max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
    n = len(offs)
    if n == 1:
        return "single cell"
    if n == w * h:
        if w == 1 or h == 1:
            return f"{n}-long {'vertical' if h > w else 'horizontal'} bar"
        return f"{w}x{h} {'square' if w == h else 'rectangle'}"
    return f"{n}-cell piece ({w} wide, {h} tall)"


def cell_text(c: Vec) -> str:
    return f"col {c[0] + 1} row {c[1] + 1}"


def cells_text(cells) -> str:
    cols = sorted({c[0] + 1 for c in cells})
    rows = sorted({c[1] + 1 for c in cells})

    def span(v):
        return f"{v[0]}" if len(v) == 1 else f"{v[0]}-{v[-1]}"

    return f"columns {span(cols)}, rows {span(rows)}"


def exit_text(level: Level, exit_index: int) -> str:
    e = level.exits[exit_index]
    return f"the {color_name(e.color)} gate on the {e.direction.name.lower()} edge ({cells_text(e.cells)})"


def path_segments(path: tuple[Vec, ...]) -> str:
    segs: list[list] = []
    for a, b in zip(path, path[1:]):
        word = STEP_WORD[(b[0] - a[0], b[1] - a[1])]
        if segs and segs[-1][0] == word:
            segs[-1][1] += 1
        else:
            segs.append([word, 1])
    return ", then ".join(f"{w} {n}" for w, n in segs)


def describe_drag(level: Level, drag: Drag, labels: list[str]) -> str:
    b = level.blocks[drag.block]
    start_cells = b.cells_at(drag.start)
    who = f"{color_name(b.color).upper()} {shape_name(level, drag.block)} [{labels[drag.block]}]"
    where = cells_text(start_cells)
    how = path_segments(drag.path)
    if drag.exits:
        assert drag.exit_index is not None
        end = f"it exits through {exit_text(level, drag.exit_index)}"
    else:
        end = f"release it; it now covers {cells_text(b.cells_at(drag.end))}"
    return f"Drag the {who} at {where}: {how} -> {end}."


def render(level: Level, state: State) -> str:
    """ASCII board. Gates are drawn on the edges with arrows and the colour letter."""
    labels = block_labels(level)
    grid: dict[Vec, str] = {}
    for i, p in enumerate(state):
        if p is None:
            continue
        for c in level.blocks[i].cells_at(p):
            grid[c] = labels[i]

    top = {x: "  " for x in range(level.width)}
    bottom = {x: "  " for x in range(level.width)}
    left = {y: " " for y in range(level.height)}
    right = {y: " " for y in range(level.height)}
    for e in level.exits:
        letter = COLOR_LETTER[e.color]
        for (x, y) in e.cells:
            if e.direction == ExitDirection.TOP:
                top[x] = "^" + letter
            elif e.direction == ExitDirection.BOTTOM:
                bottom[x] = "v" + letter
            elif e.direction == ExitDirection.LEFT:
                left[y] = letter
            else:
                right[y] = letter

    cw = 3
    lines = []
    lines.append("      " + "".join(f"{top[x]:>{cw}}" for x in range(level.width)))
    lines.append("     +" + "-" * (cw * level.width + 1) + "+")
    for y in range(level.height - 1, -1, -1):
        row = []
        for x in range(level.width):
            if (x, y) in level.inactive:
                row.append("##".rjust(cw))
            else:
                row.append(grid.get((x, y), ".").rjust(cw))
        lg = f"{left[y]}<" if left[y] != " " else "  "
        rg = f">{right[y]}" if right[y] != " " else ""
        lines.append(f"r{y + 1:<2}{lg}|" + "".join(row) + f" |{rg}")
    lines.append("     +" + "-" * (cw * level.width + 1) + "+")
    lines.append("      " + "".join(f"{bottom[x]:>{cw}}" for x in range(level.width)))
    lines.append("      " + "".join(f"{'c' + str(x + 1):>{cw}}" for x in range(level.width)))
    return "\n".join(lines)


def solution_to_script(level: Level, sol: Solution) -> dict:
    """Move script for the Unity replay: pivot paths in grid coordinates (0-based)."""
    return {
        "level": level.name,
        "grid": {"width": level.width, "height": level.height},
        "timer": level.timer,
        "min_drags": sol.min_drags,
        "drags": [
            {
                "block": d.block,
                "color": level.blocks[d.block].color.name.lower(),
                "path": [list(p) for p in d.path],
                "exits": d.exits,
                "exit_index": d.exit_index,
            }
            for d in sol.drags
        ],
    }
