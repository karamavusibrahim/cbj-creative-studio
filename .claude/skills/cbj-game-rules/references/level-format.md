# Level file format (LevelData JSON)

One level is one JSON file, as the game loads it from `Assets/Levels/<name>.json` (and as `src/cbj/level.py` reads and
writes it). Coordinates are grid cells, origin bottom-left, x to the right, y up (the tool's prompts say "column, row",
1-based from the bottom-left, and convert).

| field | type | meaning |
|---|---|---|
| `gridWidth`, `gridHeight` | int | board size in cells |
| `timerCount` | int | seconds on the clock at the start (whole seconds) |
| `inactiveCells` | list of `{x, y}` | holes: cells that are not part of the board (the only obstacle; drawn as walls) |
| `GridBlockDatas[]` | list | the blocks: `gridPosition {x, y}` (the pivot cell), `blockColor` (enum int: Green 0, Yellow 1, Blue 2, Red 3, Orange 4, Purple 5, DarkGreen 6), `shapeOffsets` (list of `{x, y}` relative to the pivot; empty = one cell; (0,0) is always part of the block) |
| `ExitDatas[]` | list | the gates: `gridPosition {x, y}` (a border cell, or a cell on the rim of a hole), `requiredColor` (same enum), `direction` (Left/Right/Top/Bottom: the side the block leaves through), `shapeOffsets` (the span: more cells of the same edge) |

Rules the file must obey (checked by `level.py`'s `validate`): blocks inside the board and on active cells, no two blocks
overlapping, one gate per cell side, a gate's cells on the edge they face. The ORDER of `ExitDatas` matters for play: a
block touching two gates of its colour is only tested against the first one in this list.

The tool's own levels live in `studio/levels/<hash>.json` (generated) and `studio/<id>/v<n>/level.json` (the copy a version
used). A board edit writes `levels/board_<key>.json`. The HUD's "Level N" badge is the `label` the tool passes, not a
field of this file.
