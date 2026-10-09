from cbj.level import level_from_dict


def v(x, y):
    return {"x": x, "y": y}


def make_level(width, height, blocks, exits, inactive=(), timer=60, name="test"):
    """blocks: [(color, (px, py), [(ox, oy), ...])]; exits: [(color, direction, (px, py), [(ox, oy), ...])]."""
    d = {
        "gridWidth": width,
        "gridHeight": height,
        "timerCount": timer,
        "inactiveCells": [v(*c) for c in inactive],
        "GridBlockDatas": [
            {"gridPosition": v(*p), "blockColor": int(c), "shapeOffsets": [v(*o) for o in offs]}
            for c, p, offs in blocks
        ],
        "ExitDatas": [
            {"exitNumber": 0, "gridPosition": v(*p), "requiredColor": int(c), "direction": int(dr),
             "shapeOffsets": [v(*o) for o in offs]}
            for c, dr, p, offs in exits
        ],
    }
    return level_from_dict(d, name=name)


# Shapes as offsets added to (0,0): single, bars, 2x2, L, T and a 4-cell L.
RICH_SHAPES = [
    [], [(1, 0)], [(0, 1)], [(1, 0), (2, 0)], [(0, 1), (0, 2)], [(1, 0), (0, 1), (1, 1)],
    [(0, 1), (1, 0)], [(1, 0), (1, 1)], [(-1, 0), (1, 0), (0, 1)], [(0, 1), (0, 2), (1, 0)],
]


def rich_random_level(rng):
    """Small boards with holes, repeated colours, 1-3 cell gates on outer edges or hole rims."""
    from cbj.level import BlockColor as C
    from cbj.level import DIRECTION_VECTOR
    from cbj.level import ExitDirection as D

    w, h = rng.randint(3, 4), rng.randint(3, 4)
    inactive = {(rng.randrange(w), rng.randrange(h)) for _ in range(rng.randint(0, 2))}
    colors = [rng.choice([C.RED, C.BLUE, C.GREEN]) for _ in range(rng.randint(2, 4))]
    blocks, taken = [], set(inactive)
    for col in colors:
        for _ in range(40):
            offs = rng.choice(RICH_SHAPES)
            p = (rng.randrange(w), rng.randrange(h))
            cells = {(p[0] + ox, p[1] + oy) for ox, oy in [(0, 0)] + offs}
            if all(0 <= x < w and 0 <= y < h for x, y in cells) and not cells & taken:
                blocks.append((col, p, offs))
                taken |= cells
                break
    exits, used = [], set()  # one gate per cell side, as in the Level Editor
    for col in sorted(set(colors)):
        for _ in range(rng.randint(1, 3)):
            d = rng.choice(list(D))
            dx, dy = DIRECTION_VECTOR[d]
            along = (1, 0) if d in (D.TOP, D.BOTTOM) else (0, 1)
            starts = [
                (x, y) for x in range(w) for y in range(h)
                if (x, y) not in inactive
                and not (0 <= x + dx < w and 0 <= y + dy < h and (x + dx, y + dy) not in inactive)
            ]
            if starts:
                n = rng.randint(1, 3)
                p = rng.choice(starts)
                offs = [(along[0] * k, along[1] * k) for k in range(1, n)]
                cells = [p] + [(p[0] + ox, p[1] + oy) for ox, oy in offs]
                if not any((c, d) in used for c in cells):
                    used |= {(c, d) for c in cells}
                    exits.append((col, d, p, offs))
    return make_level(w, h, blocks, exits, inactive=sorted(inactive))
