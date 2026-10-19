# Solver report: level model, exit rules, minimum-drag solver (2026-10-10)

Day 3 of 10. This builds the deterministic gameplay core of the case. The code is
in `~/rollic-case/cbj-creative/` and is committed (4 commits, author
karamavusibrahim, no AI attribution). Fable 5.1 reviewed it independently. Its
findings and what was done about each are in section 4.

> **Status note (added later on 2026-10-10).** This report records day 3 as it was. Since then
> the repo has grown with the Unity recorder and the case re-check (see
> RUNNER-REPORT-2026-10-10.md). When you redo the steps below, expect today's numbers: step 2
> ends with `195 passed, 22 skipped`, and step 8 shows more commits (10 or more), all by
> karamavusibrahim. The recorder has since replayed all six solutions in the real game and
> confirmed every cell.

---

## 1. Result in one table

All six shipped levels solve, and each solution passes a cell-by-cell check against the game's rules.

| level | grid | blocks | min drags | extra drags | cells dragged | timer |
|---|---|---|---|---|---|---|
| Level_01 | 4x5 | 2 | 2 | 0 | 2 | 300 s |
| Level_02 | 5x5 | 2 | 2 | 0 | 4 | 300 s |
| Level_03 | 5x6 | 3 | 3 | 0 | 5 | 300 s |
| Level_04 | 5x6 | 3 | **4** | **1** | 16 | 300 s |
| Level_05 | 5x6 | 5 | 5 | 0 | 15 | 300 s |
| Level_06 | 6x6 | 8 | 8 | 0 | 24 | 300 s |

- **min drags**: the fewest drags that clear the level. It's proven minimal: breadth-first search for levels 1-5, and for level 6 because it equals the block count, the lowest possible.
- **extra drags**: drags that only move a block out of the way. Level 4 is the only shipped level that needs one, so it's the most "puzzle-like" of the six.
- All six levels are easy. The 300 s timer is far more than any solution needs, so the timer only matters once we generate harder levels for near-fail ads.

---

## 2. Redo it yourself, step by step

Run everything in Terminal. Each step says what to run and what you should see.

### Step 1. Go to the project and install

```
cd ~/rollic-case/cbj-creative
uv sync
```
**Check:** no errors. It uses Python 3.12 and needs nothing beyond pytest for tests.

### Step 2. Run the tests

```
uv run pytest -q
```
**Check:** on day 3 the last line read `47 passed`; today it reads `195 passed, 22 skipped` (about 12 s; the 20 skipped tests start Unity).

What the 47 tests cover:
- **Level file reading:** all six JSON files load and write back identically. Bad levels are reported, such as overlapping blocks, cells off the board, or a gate on a hole.
- **Exit rule:** 11 tests on tiny boards. Each pins one behaviour of the C# code, named in the test.
- **Solver:**
  - the six levels solve with the expected minimum;
  - the search shortcut gives the same answer as a full search on levels 1-5 and on 637 random boards that the Level Editor could build;
  - the replay checker rejects broken solutions;
  - a level where the order of gates in the file changes the answer (2 vs 3 drags).

### Step 3. Draw a level and compare it with Unity

```
uv run cbj show data/levels/Level_04.json
```
You should see:
```
Level_04: 5x6, timer 300s, 3 blocks, 4 gates
       ^Y ^Y
     +----------------+
r6 O<|  .  .  .  .  . |
r5 O<|  B  B  .  .  . |
r4   |  B  B  O  .  . |
r3   |  .  .  O  Y  Y |
r2   |  .  .  .  Y  Y |>O
r1   |  .  .  .  .  . |>O
     +----------------+
                vB vB
       c1 c2 c3 c4 c5
```
How to read it:
- Columns `c1..` run left to right; rows `r1..` count up from the bottom, the same way the board looks in Unity.
- Letters are block colours: B blue, Y yellow, O orange, R red, G green, P purple, D dark green.
- Gates are on the edges: `^Y` is a yellow gate on the top edge, `vB` blue on the bottom, `O<` orange on the left, `>O` orange on the right.

**Check:** open Level 4 in Unity (step 6 explains how) and confirm the picture matches.

### Step 4. Solve all six levels

```
uv run cbj table data/levels
```
**Check:** the same numbers as the table in section 1. The `states` and `ms` columns show how much searching was needed: Level 4 needed 856 states, the others under 10.

### Step 5. Read the Level 3 solution

```
uv run cbj solve data/levels/Level_03.json
```
It prints the start board and then a board after every drag. The start board:
```
       ^B ^B ^B
     +----------------+
r6   |  .  .  .  .  . |
r5   |  .  B  B  .  . |
r4 R<|  .  B  R  Y  . |>R
r3 R<|  .  B  R  Y  . |>R
r2   |  .  .  Y  Y  . |
r1   |  .  .  .  .  . |
     +----------------+
                vY vY
       c1 c2 c3 c4 c5
```
The three steps:
1. **Yellow** 4-cell piece (columns 3-4, rows 2-4): drag **down 1, then right 1**. It exits through the yellow gate at the bottom (columns 4-5).
2. **Blue** 4-cell piece (columns 2-3, rows 3-5): drag **up 1**. It exits through the blue gate at the top (columns 1-3).
3. **Red** 2-long vertical bar (column 3, rows 3-4): drag **left 2**. It exits through the red gate on the left (rows 3-4).

The same solution is saved for the Unity replay as `data/solutions/Level_03.moves.json`.

### Step 6. Replay Level 3 by hand in Unity (the "done" check)

1. Open the CBJ project in Unity.
2. Menu: **Tools → CBJ Level Editor**.
3. In the left panel under **File**, set **Level Number** to **3** and check the path box says **Assets/Levels**.
4. Click **Load JSON**. No file window opens: it loads `Level_<number>.json` from that folder.
5. Click **Test Current Level** (under **Playtest**). Unity opens LevelTestScene and starts Play mode with Level 3.
6. **Don't click Save JSON.** It would overwrite the level file.
7. Do the three drags from step 5, slowly and in straight lines.

What you should see, and why each one is a real test of the rules:

| Drag | What happens | Rule it proves |
|---|---|---|
| Yellow **down 1** | It moves down and does **not** exit, even though it now touches the yellow gate | Every cell of the block must leave through the gate's columns. The yellow piece's left foot is in column 3, outside the gate (columns 4-5) |
| keep dragging **right 1** | It exits through the bottom gate | All its cells are now inside columns 4-5 and the path down is clear |
| Blue **up 1** | It exits through the top gate | Gate columns 1-3 contain both of its columns |
| Red **left 2** | It exits through the left gate. After left 1 it must **not** exit | A block must touch a gate cell to exit: after left 1 the bar is not yet in column 1, so no gate is touched |

**Pass:** all three exit at the moments described, the win screen appears, and nothing exits earlier than described.

**Optional harder check:** Level 4, which needs one repositioning drag. Run `uv run cbj solve data/levels/Level_04.json`, load Level Number **4** in the Level Editor, and follow the four steps. The first drag moves yellow **up 1** and it must **not** exit. That drag only clears a path for the orange bar.

**If something differs**, write down which drag, where you started, and what happened, and send it to me. A mismatch means either the rule copy is wrong or the drag in Unity went diagonally and skipped a cell (section 3, point 6).

### Step 7. See the gate-order quirk proven

```
uv run pytest -q tests/test_solver.py::test_gate_order_in_the_file_changes_the_minimum
```
**Check:** `1 passed`. The test builds this 3x3 board, which the Level Editor can also build (`##` is a hole):
```
     +----------+
r3   |  .  .  . |
r2   | ##  .  . |
r1 R<| R1 R2 R2 |>R
     +----------+
       vR vR
       c1 c2 c3
```
The red bar R2 touches two red gates: the bottom one (columns 1-2) and the right one.
- **Bottom gate first in the file: 3 drags.** The game tests only the bottom gate. That test fails, because R2's right cell is in column 3, so R2 can never use the right gate; it has to wait for R1 to leave.
- **Right gate first: 2 drags.** R2 steps up and back down and exits right, then R1 exits.

### Step 8. Look at the history

```
git log --format='%h %an | %s'
```
**Check:** four commits on day 3 (10 or more today), all by `karamavusibrahim`.

---

## 3. What the Unity code actually does (things that were not obvious)

Each item below was read in the C# source and is pinned by a test.

1. **A block exits only while it's being dragged**, at the moment its pivot cell changes (`InputHandler.DragBlock`). The pivot is the block's anchor cell from the level file (shape offset 0,0), not necessarily its middle.
   - A block that already sits at its gate does not leave when its path clears; it has to be dragged into an exit position. Stepping away and back counts.
   - Releasing the mouse never triggers an exit.
   - So each block needs at least one drag, which is why "min drags ≥ number of blocks".
2. **The first exit position along a drag ends the drag.** You can't drag a block over a cell where it would exit; it leaves there.
3. **Only the first matching gate in the level file is tested** (`ExitService.FindMatchingExit`). If a block touches two gates of its colour, the second is never tried (step 7).
4. **Every cell of the block must have a clear straight lane out**, and it must leave through the gate's columns (top and bottom gates) or rows (left and right gates). A block that's wider than the gate never exits through it.
5. **Holes don't block the exit lane**, and a gate may sit on the rim of a hole, not only on the outer edge (`GridManager.NeedsBorder`).
6. **The game checks once per frame**, so a fast or diagonal drag can skip a cell. This doesn't change the minimum drag count. It does give the Unity replay (day 4) a hard rule: move one cell at a time along an axis and let the block settle before the next step, and after an exit, start the next drag only after the 0.1 s snap, which is when the exiting block's cells are freed. The slide out takes longer but only delays the win screen.
7. **Collision box:** 0.8 of a cell (`collisionPadding` 0.4 in `MovementSettings.asset`). Blocks pass through 1-cell corridors but can't cut corners. On whole cells, the solver reaches exactly the positions the game reaches.

---

## 4. Fable 5.1 review: findings and what was done

Fable 5.1 read the Unity C# and the Python independently. It wrote its own copy of the rules and a brute-force solver, compared them on 2,000 random boards with its own scripts (outside the repo), and simulated the game's continuous drag movement frame by frame. It changed no project files. Result: **no blockers, 40/40 tests passing at the time**. All 9 claims were confirmed or partly confirmed, and the two "partly" verdicts are addressed below.

| # | Finding | Severity | What I did |
|---|---|---|---|
| 1 | The validator rejected gates on the rim of a hole, which Unity supports | Major | **Fixed.** I checked `GridManager.NeedsBorder` myself: a hole counts as an edge. The validator now accepts these gates; there's a test |
| 2 | The game can skip a cell on fast or diagonal drags, so it can skip an exit check the model makes | Major | **Documented**; the minimum drag count isn't affected (Fable showed skipped checks only remove forced exits). Recorded as a hard rule for the Unity replay in `solver.py` and the README |
| 3 | The random test lacked repeated colours, holes, hole-rim gates and L/T/2x2 shapes | Minor | **Fixed.** Added a second random test and the gate-order test (step 7). After the second review it compares 387 boards: 206 with holes, 73 with hole-rim gates, 273 with repeated colours |
| 4 | `replay()` accepted a wrong gate index and raised the wrong error for an unknown block | Minor | **Fixed**, with tests. A pick-up-and-put-back no-op is now accepted, as in the game |
| 5 | A gate placed on a hole wasn't flagged | Minor | **Fixed.** Now reported as "no block can reach it" |
| 6 | The docstring said a 0.7-cell box; the project's asset says 0.8 | Nit | **Fixed.** I checked `MovementSettings.asset` myself (`collisionPadding: 0.4`) |
| 7 | Hole order changed on save | Nit | **Fixed.** Order is kept; there's a test |
| 8 | "columns 1" wording | Nit | **Fixed** ("column 1") |

Claims Fable confirmed, with no change needed:
- The exit check matches the C# line for line.
- The exit timing and the step-away-and-back rule are right.
- The search shortcut is optimal: its proof was checked, and a brute-force comparison over 2,000 boards gave 0 mismatches.
- Level 6's 8 drags is a valid lower bound.
- The screen orientation is right: grid +y is screen up, checked against the camera at rotation (75, 0, 0) in GameScene.
- The Level 3 solution was re-derived by hand from the JSON.

After the fixes: 46 tests passed and the six solutions were byte-identical to before.

### 4b. Second Fable 5.1 review (the fixes and the documents)

The second pass checked every fix against the C# and ran every command in the checking guide. It also checked each Unity claim in step 6 against the code and the scene files.

**The fixes: all 6 confirmed.**
- The hole-rim gate rule agreed with `GridManager.NeedsBorder` on 20,000 random gate layouts.
- `replay()` was probed with negative and empty inputs and exits at a re-entered start cell; no hole was found.
- The six solutions were still byte-identical, and 46 tests passed.

**Document errors it found, and what I did:**

| # | Error | Severity | Fix |
|---|---|---|---|
| 1 | "Load JSON → choose the file" is wrong. Load JSON opens no file window: it loads `Level_<number>.json` using the **Level Number** field (default 1), so the old steps would have loaded Level 1 | Wrong | **Fixed** in the report and the guide: set Level Number to 3 (or 4), then Load JSON. Checked in `LevelEditorWindow.LoadLevel` myself |
| 2 | "Press R to restart" is wrong in the test scene. R reloads by build index, and LevelTestScene is not in the build list, so nothing happens | Wrong | **Fixed**: use the round-arrow Restart button next to the timer, which is enabled after the first move, or click Test Current Level again. Checked `EditorBuildSettings.asset` and `RestartButton.cs` myself |
| 3 | The red bar's "left 1 does not exit" was explained as gate order. It's really the overlap rule (no gate touched yet) | Misleading | **Fixed** |
| 4 | The old gate-order board hid one gate in the drawing (two gates on the same cell side), and the Level Editor can't build such a board | Misleading | **Replaced** with a 3x3 board the editor can build (step 7). `validate()` now rejects two gates on one cell side, and the random generators only make buildable boards |
| 5 | The README's random-board wording implied every board had holes, rim gates and repeated colours | Misleading | **Fixed** with exact counts |
| 6 | "Wait for the exit animation" was imprecise: cells are freed after the 0.1 s snap, and the slide only delays the win screen | Misleading | **Fixed** in the code docs, the README and section 3 |
| 7 | "Centre cell" should be "pivot cell" | Misleading | **Fixed** |
| 8-10 | A missing first output line in step 3, `reports/` missing from the README layout, and the 2,000-board figure coming from Fable's own scripts | Nit | **Fixed** / noted |

**After the second round:**
- 47 tests pass.
- The random tests compare 637 editor-buildable boards against the full search: 250 simple, and 387 richer ones with 206 that have holes, 73 with gates beside holes and 273 with a repeated colour.
- The six solutions are still byte-identical.
- There are 4 commits.

**Not reviewed by anyone yet:** running the solutions inside Unity. That's your step 6.

### 4c. Failure testing (Fable 5.1 tried to break the system)

**Aim:** check that bad input makes the system refuse clearly. That means a precise error naming the file and field, "unsolvable" when there is no solution, and never a silent wrong answer, a raw Python crash or a hang.

**Fable 5.1 ran 101 bad inputs in 7 groups:**
- broken files;
- levels the game cannot build;
- valid but unsolvable levels;
- edge sizes;
- huge boards;
- illegal or edited move scripts;
- command-line misuse.

| | Correct | Ugly crash | Wrong accept | Wrong reject | Hang |
|---|---|---|---|---|---|
| Before fixes | 73 | 19 | 7 | 1 | 1 |
| After fixes | 99 | 1* | 1* | 0 | 0 |

\* Both are outdated expectations in the test harness, not defects:
- `max_states=0` now gives a clear "must be a positive integer" error, as Fable itself recommended.
- A legal move whose cells are written as JSON lists is now accepted. The old code wrongly rejected it.

**The core rules were already right before any fix.** Every unsolvable level, illegal move and edited move script was handled correctly. All the problems were at the edges:
- **File reading:** missing fields and wrong types gave raw Python errors. `"4"`, `4.5` and `1.9` were silently turned into integers, which could move a block. Grids larger than the editor's 12x12 were accepted.
- **Command line:** bad files printed Python crash dumps. `cbj table` stopped at the first bad file, and returned "success" for a folder that doesn't exist.
- **Solver:** a 10-million-cell board hung, because one drag walked the whole board before any limit was checked. It now stops in 0.05 s.

**What changed:**
- Strict parsing.
- A 12x12 limit.
- Per-drag and per-search limits.
- Type checks in `replay`.
- `script_to_drags`, plus a new `cbj check` command that validates a move script against a level.
- One-line CLI errors with exit code 1.

**Tests:** 60 new failure-mode tests (`tests/test_failure_modes.py`). 38 of them failed on the code before the fixes and 6 more test the move-script reader, which did not exist yet; all pass now, for 107 tests in total. The six solutions are byte-identical after every change, and there are 5 commits.

---

## 5. How the solver works (short)

- **State:** where each remaining block is.
- **Move:** one drag. The block slides cell by cell through free cells. The drag either stops wherever the player releases it, or ends at the first cell where the exit check passes.
- **Search:** breadth-first, so the first solution found has the fewest drags.
- **Shortcut:** if some block can exit right now, take that exit first. This can't make things worse, because a removed block never blocks anything. The tests check it against the full search.
- **Replay checker:** re-walks any move list cell by cell against the rules. Day 4's Unity replay will enforce exactly the same checks.

**Output for day 4:** `data/solutions/Level_0N.moves.json`. Each drag is a list of cells for the block's pivot, plus whether it exits and through which gate. This is the script the Unity CreativeRunner will play.

---

## 6. Files

```
cbj-creative/
  src/cbj/level.py     reads/writes the level JSON, validation
  src/cbj/rules.py     the exit rule and valid positions, ported from C#
  src/cbj/solver.py    drag outcomes, minimum-drag search, replay checker
  src/cbj/describe.py  ASCII boards, plain-English steps, move-script JSON
  src/cbj/cli.py       `cbj show | solve | table`
  data/levels/         the six shipped levels (unchanged copies)
  data/solutions/      move scripts for Unity
  reports/             solve_table.md, Level_03_walkthrough.txt
  tests/               47 tests on day 3 (195 + 22 Unity tests today)
```

---

## 7. Limits and what comes next

**Limits:**
- Difficulty is measured only by minimum drags and extra drags. The simulated-human difficulty model from the research report is not built yet; it belongs with the level generator (day 5).
- The search is exact but plain Python. It handles the shipped levels in milliseconds. A full search without the shortcut doesn't finish on Level 6 (over 2 million states), which is fine because the shortcut is proven safe.
- Nothing here has run inside Unity yet. That's step 6 (your manual check) and day 4.

**Next (day 4): the Unity CreativeRunner.**
1. Load a level plus its `.moves.json` file.
2. Drive the game's own movement and exit code one cell at a time, at a fixed 30 fps.
3. Save the frames and turn them into a 9:16 MP4 with ffmpeg.

The replay rule from section 3, point 6 is built in from the start.
