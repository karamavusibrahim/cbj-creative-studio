# cbj-creative

Tooling for generating Color Block Jam ad creatives. This first part is the
deterministic gameplay core: a level model that reads the game's own JSON, the
game's exit and movement rules ported from the Unity C#, and a solver that finds
the minimum number of drags that clears a level.

## Setup

```
uv sync
uv run pytest
```

Python 3.12, no runtime dependencies.

## Commands

```
uv run cbj show  data/levels/Level_03.json                  # draw the board
uv run cbj solve data/levels/Level_03.json                  # minimum-drag solution, step by step
uv run cbj solve data/levels/Level_03.json --json out.json  # also write the move script
uv run cbj table data/levels --md reports/solve_table.md --scripts data/solutions
```

Boards print with 1-based columns (`c1..`) and rows (`r1..`) from the bottom-left,
matching what you see in Unity. Gates are drawn on the edges: `^B` is a blue gate
on the top edge, `vY` yellow on the bottom, `R<` red on the left, `>O` orange on the right.

## Results on the six shipped levels

| level | grid | blocks | min drags | extra drags | cells dragged |
|---|---|---|---|---|---|
| Level_01 | 4x5 | 2 | 2 | 0 | 2 |
| Level_02 | 5x5 | 2 | 2 | 0 | 4 |
| Level_03 | 5x6 | 3 | 3 | 0 | 5 |
| Level_04 | 5x6 | 3 | 4 | 1 | 16 |
| Level_05 | 5x6 | 5 | 5 | 0 | 15 |
| Level_06 | 6x6 | 8 | 8 | 0 | 24 |

"Extra drags" are drags that move a block out of the way instead of exiting it.

## Rules as implemented (from the Unity source)

| Rule | C# source |
|---|---|
| A block covers its pivot plus its shape offsets; an empty offset list means one cell, and (0,0) is always added | `Block.Initialize` |
| A position is valid when every block cell is on the board, active, and not held by another block | `BlockMovementService.IsPositionValid` |
| Exit check: the first gate in list order with the block's colour that overlaps the block is chosen; every block cell then needs a clear straight lane to the edge, leaving through the gate's columns (top/bottom) or rows (left/right) | `ExitService.FindMatchingExit`, `IsPathClear` |
| Inactive cells do not block an exit lane | `IsPathClear` only fails on a cell holding another block; inactive cells are null |
| The exit check runs only while a block is dragged, each time its pivot enters a different cell; the first such cell where it passes ends the drag | `InputHandler.DragBlock` |
| A block already standing at its gate does not leave by itself | same; releasing never triggers an exit |

A move in the solver is one drag: the block's pivot walks through 4-adjacent valid
positions and either stops anywhere or exits at the first cell where the check passes.

## Layout

```
src/cbj/level.py     LevelData model, JSON round-trip, validation
src/cbj/rules.py     occupancy, valid positions, exit check
src/cbj/solver.py    drag outcomes, BFS solver, replay checker
src/cbj/describe.py  ASCII boards, plain-English steps, move-script JSON
src/cbj/cli.py       command line
data/levels/         the six shipped levels (copied unchanged from the Unity project)
data/solutions/      move scripts for the Unity replay
tests/               rule tests, level round-trip, solver and replay tests
```
