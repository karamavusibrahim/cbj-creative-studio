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
uv run cbj check data/levels/Level_03.json data/solutions/Level_03.moves.json  # verify a move script
```

Errors print one line, `cbj: <reason>`, and exit with code 1.

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
| The order of gates in the file matters: a block touching two gates of its colour is only tested against the first | `FindMatchingExit` (test: `test_gate_order_in_the_file_changes_the_minimum`) |
| A gate may sit on the outer edge or on the rim of a hole | `GridManager.NeedsBorder` treats an inactive neighbour as an edge |
| One gate per cell side (`validate` rejects two) | the Level Editor's `ToggleExitCell` replaces an existing gate on that side |

A move in the solver is one drag: the block's pivot walks through 4-adjacent valid
positions and either stops anywhere or exits at the first cell where the check passes.
The game's collision box is 0.8 of a cell (`collisionPadding` 0.4), so 1-cell
corridors are passable and corners cannot be cut; the cell model reaches exactly
the positions the game reaches.

The solver is breadth-first search with one shortcut: when a block can exit, it
takes that exit first. This is safe because removing a block never blocks anything
else. The tests compare it against the full search on the shipped levels and on
637 random boards, all buildable in the Level Editor: 250 simple ones and 387 richer
ones (206 with holes, 73 with a gate on the rim of a hole, 273 with a repeated colour).

**Rule for the Unity replay.** The game checks for an exit once per frame, when the
block's rounded pivot cell changes, so a fast or diagonal drag can skip a cell.
A scripted replay must move one cell at a time along an axis and let the pivot
settle on each cell before the next step. After an exit, the block's cells are
freed when the 0.1 s snap ends (`PerformExit`), so the next drag must start after
that; the slide out takes longer but only delays the win screen.

## Failure handling

Fable 5.1 attacked the system with 101 bad inputs (broken files, impossible and
unsolvable levels, edge sizes, huge boards, illegal and tampered move scripts,
CLI misuse). The fixes that came out of it:

- Level files are parsed strictly. Missing fields, wrong types (`"4"`, `4.5`,
  `true`), unknown colours or directions, and non-JSON files raise a `ValueError`
  that names the file and the field. Nothing is silently coerced.
- `validate` also rejects boards larger than the Level Editor's 12x12.
- `solve` rejects a bad `max_states`, and stops with `SolverLimitError` when more
  than `max_states` positions are stored or a single drag reaches more than
  max(`max_states`, 144) cells. 144 is a full 12x12 board, so the second limit
  never changes a real level's result; it only stops a huge board from stalling.
- `replay` rejects anything that is not a well-formed drag; `script_to_drags`
  reads a saved move script.
- Files with a UTF-8 byte-order mark load; JSON nested too deeply or with
  integers too long to parse is a `ValueError` naming the file.
- `cbj check` refuses a move script made for a different level.
- The CLI never shows a Python traceback for bad input. `cbj table` reports a
  bad file as an `ERROR` row and keeps going, and prints the table before
  writing any files.

`tests/test_failure_modes.py` holds 71 tests. The first 60 came from the
adversarial run: 38 failed on the code before the fixes, and 6 more test the
move-script reader that did not exist yet. A third Fable review found a crash on
deeply nested JSON and five smaller issues; the last 11 tests cover those, and
10 of them fail on the code before that round.

## Layout

```
src/cbj/level.py     LevelData model, JSON round-trip, validation
src/cbj/rules.py     occupancy, valid positions, exit check
src/cbj/solver.py    drag outcomes, BFS solver, replay checker
src/cbj/describe.py  ASCII boards, plain-English steps, move-script JSON
src/cbj/cli.py       command line
data/levels/         the six shipped levels (copied unchanged from the Unity project)
data/solutions/      move scripts for the Unity replay
reports/             solve table and the Level 3 walkthrough
tests/               rule tests, level round-trip, solver and replay tests
```
