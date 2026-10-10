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

Python 3.12, no runtime dependencies. Recording videos also needs ffmpeg on PATH
and Unity 6000.3.5f1 (see "Recording in the real game").

## Commands

```
uv run cbj show  data/levels/Level_03.json                  # draw the board
uv run cbj solve data/levels/Level_03.json                  # minimum-drag solution, step by step
uv run cbj solve data/levels/Level_03.json --json out.json  # also write the move script
uv run cbj table data/levels --md reports/solve_table.md --scripts data/solutions
uv run cbj difficulty data/levels                           # how hard: minimum solution + a naive player
uv run cbj check data/levels/Level_03.json data/solutions/Level_03.moves.json  # verify a move script
uv run cbj build-player                                     # once: build the Unity recording player
uv run cbj render data/levels/Level_03.json data/solutions/Level_03.moves.json  # record it in the game
uv run cbj compare renders/Level_03 renders/Level_03_b       # how close two recordings are
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

## Difficulty

`cbj difficulty` adds two kinds of numbers. From the solver: minimum drags,
repositioning drags, how many blocks can leave with their first drag, and how
many different first drags there are. From a simulated naive player (the
"simulated human" idea used to rate puzzle difficulty): it takes an exit
whenever one is available, otherwise drags a random block to a random reachable
cell, 200 seeded runs.

| level | min drags | extra drags | exits at start | naive player mean (p90) |
|---|---|---|---|---|
| Level_01 | 2 | 0 | 2 | 2.0 (2) |
| Level_02 | 2 | 0 | 2 | 2.0 (2) |
| Level_03 | 3 | 0 | 2 | 3.0 (3) |
| Level_04 | 4 | 1 | 0 | 5.0 (7) |
| Level_05 | 5 | 0 | 2 | 5.0 (5) |
| Level_06 | 8 | 0 | 4 | 8.0 (8) |

The shipped levels are tutorial-easy: on five of them an exit is always
available, so even the naive player never wastes a drag. Only Level 4 needs a
block moved out of the way first. A "difficult level" request therefore needs
generated levels. No easy/hard labels are assigned; those need calibration
against real player data. The naive player's wasted drags are also the
believable mistakes a near-fail creative can show. `solve(level, start=...)`
solves from any mid-game position.

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

## Recording in the real game (Unity CreativeRunner)

`cbj render` plays a move script in the real game and records it as a 1080x1920,
30 fps video. The game's rule code is untouched: the level is the game's own
LevelData, and every drag goes through the game's own `BlockMovementService`,
`BlockGridService` and `ExitService`, one frame at a time, exactly as
`InputHandler` drives them from the mouse. What the runner does change is
listed here:
- the mouse is a scripted finger;
- the camera is re-fitted for the 9:16 frame;
- the HUD is drawn through the camera at a phone's scale;
- button fades are instant and particle seeds fixed, for repeatability;
- the level badge shows the level's number.

The build also applies a small game patch (below) to its copy of the project.

```
uv run cbj build-player     # ~35 s; needs Unity 6000.3.5f1 and the project at ../CBJ
uv run cbj render data/levels/Level_03.json data/solutions/Level_03.moves.json
uv run cbj render data/levels/Level_05.json                  # no script: solve, then record
uv run cbj render LEVEL MOVES --end cut --drags 2            # stop after drag 2 (cliffhanger)
uv run cbj render LEVEL MOVES --end fail --drags 2           # wait for the timer to run out
uv run cbj render LEVEL MOVES --speed 2 --pause 1.6 --start-hold 2.5 --end-hold 3   # slower, longer
uv run cbj render LEVEL MOVES --zoom 1.1 --pan-y -0.5 --intro  # framing; --intro eases in from pulled back
uv run cbj render LEVEL MOVES --timer 20 --hide RestartButton  # clock override, hide a HUD part
uv run cbj build-player --stock && uv run cbj render LEVEL MOVES --stock  # the game as shipped, unpatched
```

Length: the shipped levels record in 5-13 s at the default pacing; Level 6 at
`--speed 2 --pause 1.6` records 29.3 s (in 42 s). A 30-60 s ad comes from slower
pacing, bigger generated levels, several levels, and the hook and end card.

Camera: zoom 1 is the game's own framing. Above about 1.1, a board that already
fills the width loses its side gates. Changing only the camera leaves the game
identical: `cbj compare` then reports the same game state with a different
finger path on screen and different pixels.

**The game patch.** The game as shipped has two ways to show both endings:
1. It keeps its clock running while the last block slides out, and counts the
   win only when the slide ends. If time runs out during that half second, it
   shows "Out of Time!" and then "Level Completed".
2. It still accepts drags after the fail screen, because input raycasts the 3D
   board rather than the UI.

`unity/game-patch` fixes both in the game's own code:
- the clock stops when every block left on the board has started its exit
  (`GameManager.OnBlockExitStarted`, called from `ExitService.PerformExit`);
- once one ending has shown, no other ending can follow;
- the board takes no input after either ending.

That is 31 added lines in three files, each marked `cbj-creative patch`.
`game.patch` is the readable diff, and `original/` holds Rollic's files byte for
byte. `build-player` applies the patch to its copy only, so Rollic's project is
never changed, and it refuses to patch files that differ from those originals.

For a before/after, `cbj build-player --stock` builds the game exactly as
shipped and `cbj render --stock` records with it. On a stock build, the
recorder stops the clock itself unless asked not to. `cbj render` rejects any
recording that shows both screens.

Event data for the compositor: `result.json` has each drag's frames, cells and
gate number, the first touch, the clock stop, win or fail frame, the frame
each block disappears, and the HUD's rectangles (caption safe zones).
`frames.json` has, per frame, the timer, the finger and every block's position
in video pixels, and a pixel hash. The game itself has no audio; sound effects
are added by the compositor at these frames.

`build-player` copies the Unity project into `build/unity-project`, adds
`unity/CreativeRunner`, and builds `build/CBJRunner.app`. The original project
is never modified, so it can stay open in the editor. The runner script does
nothing unless the player is started with `-cbjJob <job.json>`.

How a recording works:

1. `make_job` checks the script with `replay` first, so an illegal script is
   refused before Unity starts, and writes `job.json` (level path, timings, drags).
2. The player loads the level, fits the camera to a 9:16 frame with the game's
   own fit formula, and draws the UI through the camera at the scale a 1080-wide
   phone uses.
3. Time runs on a fixed step (`Time.captureDeltaTime`), so a frame is always
   1/30 s of game time however long it takes to render. The timer, the exit
   slide and the win animation all run on that clock.
4. For each drag the finger picks the block up, moves one cell at a time along
   the planned pivot path, and waits at corners until the block catches up, so
   the game's per-frame exit check sees the same cells the solver planned.
5. After each drag the runner compares the cells the block actually entered, and
   whether it exited, with the script. Any difference stops the recording with
   status `mismatch` and the reason.
6. Frames are read back from the GPU and piped to ffmpeg. `frames.json` stores,
   for every frame, the MD5 of the raw pixels, the game timer and the finger's
   position in video pixels (for a hand overlay later). `result.json` stores the
   status, the frame of the first touch, each drag's frames, the win or fail
   frame, and the timer at each point.

Statuses: `cleared` (win screen), `unresolved` (`--end cut`), `failed` (the
game's fail screen; play stops there, as it does for a player, and a drag cut
short by it is marked `interrupted`), `mismatch`, `timeout`, `error`. A broken
job, a path cell off the board, or ffmpeg dying mid-recording ends the run with
`error` or `mismatch` and a reason; the player never hangs. `cbj render` then
cross-checks `result.json`, `frames.json` and an ffprobe of the video, and
prints any problem.

`make_job` refuses scripts that cannot give the asked ending (`win` needs a
cleared board, `cut` and `fail` need a block left) and a finger faster than
half a cell per frame (15 cells/s at 30 fps), the limit above which the block
could land on a cell boundary when the game checks for an exit.

Results: the solver's scripts clear all six shipped levels in the game, with
every drag entering exactly the planned cells.

**Repeatability.** The same job gives the same game every time: the timer,
finger position, cells entered, exit frames and ending are identical frame for
frame. The pixels are identical in nearly every frame, but not all: across
repeated 270x480 renders of Level 6, one or two frames per run differed by a
few pixels (worst frame about 45 dB PSNR, invisible to the eye), at random
positions. Logging every particle's state showed the simulation identical in
those frames, and the difference stayed with MSAA off and shaders warmed up,
so it comes from below the game, in the graphics driver. Full-size renders
usually match on every frame. `cbj compare A B` therefore reports the game
state, the count of identical frames and the lowest frame PSNR, and the
controlled-editing proof will compare with that tolerance rather than demand
bit-identical frames. Two real sources of variation were fixed on the way:
particle systems picked a new random seed every run (the runner fixes each
seed), and Unity UI button fades run on real time (the runner makes them
instant).

**Known differences from a phone.** The drag follows the game's own
`Lerp(..., deltaTime * dragSpeed)`, so at 30 fps the block trails the finger a
little more tightly than on a 60 Hz phone; render with `--fps 60` for the
phone's feel. The game's 1.5 s camera glide at level start is not played: the
video opens on the fitted board. `build-player` copies the project's
`Library/` folder to keep builds at about 35 s; if a build fails while the
editor is busy importing, close the editor or delete `build/unity-project` and
build again.

`tests/test_render.py` checks jobs, recordings and comparisons without Unity.
`tests/test_unity_render.py` has 22 tests and starts the player 24 times (about
4 minutes; the two stock-game tests need `cbj build-player --stock` first):
- six levels cleared;
- a repeat render;
- a camera-only change;
- a blocked drag, an unplanned exit, a path off the board;
- a dead ffmpeg, a bad job, bad camera keys, an unknown object to hide;
- the fail screen between drags and in the middle of one;
- the stock game's fail-then-win bug; the patched game stopping its own clock;
  the recorder stopping it on a stock game;
- the compositor event data:

```
CBJ_UNITY=1 uv run pytest tests/test_unity_render.py
```

## Layout

```
src/cbj/level.py     LevelData model, JSON round-trip, validation
src/cbj/rules.py     occupancy, valid positions, exit check
src/cbj/solver.py    drag outcomes, BFS solver, replay checker
src/cbj/describe.py  ASCII boards, plain-English steps, move-script JSON
src/cbj/difficulty.py difficulty numbers and the simulated naive player
src/cbj/render.py    render jobs, camera, running the Unity player, checking and comparing recordings
src/cbj/cli.py       command line
unity/CreativeRunner Unity scripts copied into the project copy by build-player
unity/game-patch     the game fix: Rollic's originals, the patched files, game.patch
data/levels/         the six shipped levels (copied unchanged from the Unity project)
data/solutions/      move scripts for the Unity replay
reports/             solve table and the Level 3 walkthrough
tests/               rule, level, solver, replay, failure-mode and render tests
build/, renders/     player build and recordings (not in git)
```
