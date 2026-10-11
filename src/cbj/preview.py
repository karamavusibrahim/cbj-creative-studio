"""A picture of a level, drawn from the level file: the board, its holes, the blocks in their
display colours with their labels (R, Y1, Y2...), and the gates on the edges.

Used by the UI to show the level before (and beside) the recording, and by the reports. It is a
diagram, not the game's look: the video is the game itself.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from .describe import block_labels
from .draw import font
from .level import BlockColor, ExitDirection, Level
from .rules import State, initial_state

GAME_HEX = {"GREEN": "#14FF17", "YELLOW": "#FFCC04", "BLUE": "#1469FF", "RED": "#FF3B2A", "ORANGE": "#FF8000",
            "PURPLE": "#D007FD", "DARK_GREEN": "#065C13"}
SLOT = {"Green": "GREEN", "Yellow": "YELLOW", "Blue": "BLUE", "Red": "RED", "Orange": "ORANGE", "Purple": "PURPLE",
        "DarkGreen": "DARK_GREEN"}
BG, CELL, HOLE = (36, 22, 74), (226, 222, 240), (36, 22, 74)


def _rgb(h: str) -> tuple[int, int, int]:
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def _text_colour(rgb) -> tuple[int, int, int]:
    return (20, 20, 30) if 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2] > 160 else (255, 255, 255)


def board_image(level: Level, state: State | None = None, colours: dict[str, str] | None = None,
                cell: int = 56, marks: dict[int, str] | None = None) -> Image.Image:
    """The board at `state` (the start by default). colours: display hex per slot name ("Red") for
    repainted slots. marks: a short tag per block id drawn under its label (e.g. "key")."""
    state = initial_state(level) if state is None else state
    hexes = {c: GAME_HEX[c.name] for c in BlockColor}
    for slot, h in (colours or {}).items():
        if slot in SLOT:
            hexes[BlockColor[SLOT[slot]]] = h
    m = cell // 2 + 6  # room for the gates around the board
    W, H = level.width * cell + 2 * m, level.height * cell + 2 * m
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    def box(x, y):  # screen box of cell (x, y); y grows upward in the level
        x0 = m + x * cell
        y0 = m + (level.height - 1 - y) * cell
        return x0, y0, x0 + cell, y0 + cell

    for x in range(level.width):
        for y in range(level.height):
            x0, y0, x1, y1 = box(x, y)
            if level.is_active((x, y)):
                d.rounded_rectangle((x0 + 2, y0 + 2, x1 - 2, y1 - 2), radius=cell // 8, fill=CELL)
    # gates: a bar on the outer side of each gate cell, in the gate's colour
    t = max(6, cell // 6)
    for e in level.exits:
        rgb = _rgb(hexes[e.color])
        for (x, y) in e.cells:
            x0, y0, x1, y1 = box(x, y)
            if e.direction == ExitDirection.TOP:
                r = (x0 + 3, y0 - t - 2, x1 - 3, y0 - 2)
            elif e.direction == ExitDirection.BOTTOM:
                r = (x0 + 3, y1 + 2, x1 - 3, y1 + t + 2)
            elif e.direction == ExitDirection.LEFT:
                r = (x0 - t - 2, y0 + 3, x0 - 2, y1 - 3)
            else:
                r = (x1 + 2, y0 + 3, x1 + t + 2, y1 - 3)
            d.rounded_rectangle(r, radius=t // 2, fill=rgb)
    # blocks: each cell filled, joined to its neighbours of the same block
    labels = block_labels(level)
    pad = max(3, cell // 12)
    for i, p in enumerate(state):
        if p is None:
            continue
        rgb = _rgb(hexes[level.blocks[i].color])
        cells = set(level.blocks[i].cells_at(p))
        for (x, y) in cells:
            x0, y0, x1, y1 = box(x, y)
            d.rounded_rectangle((x0 + pad, y0 + pad, x1 - pad, y1 - pad), radius=cell // 6, fill=rgb)
            if (x + 1, y) in cells:
                d.rectangle((x1 - pad - 1, y0 + pad, x1 + pad + 1, y1 - pad), fill=rgb)
            if (x, y - 1) in cells:
                d.rectangle((x0 + pad, y1 - pad - 1, x1 - pad, y1 + pad + 1), fill=rgb)
            if {(x + 1, y), (x, y - 1), (x + 1, y - 1)} <= cells:  # where four cells of the block meet
                d.rectangle((x1 - pad - 1, y1 - pad - 1, x1 + pad + 1, y1 + pad + 1), fill=rgb)
        px, py = p
        x0, y0, x1, y1 = box(px, py)
        f = font(max(14, cell // 3))
        d.text(((x0 + x1) / 2, (y0 + y1) / 2), labels[i], fill=_text_colour(rgb), font=f, anchor="mm")
        if marks and i in marks:
            d.text(((x0 + x1) / 2, y1 - pad - 2), marks[i], fill=_text_colour(rgb),
                   font=font(max(11, cell // 5)), anchor="md")
    return img


def save_board(level: Level, path: str | Path, **kw) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    board_image(level, **kw).save(path)
    return path
