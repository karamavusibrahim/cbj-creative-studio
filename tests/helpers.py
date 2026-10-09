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
