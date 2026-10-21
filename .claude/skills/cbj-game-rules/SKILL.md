---
name: cbj-game-rules
description: CBJ as implemented in the provided Unity project (~/cbj-work/CBJ) and ported to cbj-creative/src/cbj/rules.py - the board, polyomino blocks, the seven colours, colour gates and the exact exit rule, free 2D drag and collision, the countdown clock, win and fail, the camera, the level JSON, the six shipped levels, and the list of mechanics the game does NOT have (no boosters, bombs, ice, keys, chains, locks, hints, undo, audio). Use when deciding whether a prompt, a level, a move, an edit or a test expectation is possible in this game, before planning gameplay, and before judging a recording for gameplay consistency.
metadata:
  spec-version: "1"
  last-verified: "2026-10-14"
  game-version: "CBJ Unity 6000.3.5f1, six levels"
---

# CBJ: the rules as implemented

## 1. Purpose
One set of facts about the game, taken from its C# source, so that every agent plans, generates, edits and judges
against the same mechanics. If a prompt or an expectation needs something not listed here, it is not in the game:
say so, do not invent it (see section 5).

## 2. Source of truth
- Unity project `~/cbj-work/CBJ` (not part of this repo): `Assets/Scripts/**` (movement, exits, grid, input, timer,
  UI), `Assets/Levels/Level_01..06.json`. Line-cited extract: [references/mechanics.md](references/mechanics.md).
- Port, tested against the C#: `src/cbj/rules.py` (occupancy, valid position, exit check), `src/cbj/level.py` (the level
  file), `src/cbj/solver.py`, `src/cbj/difficulty.py`. `docs/ENGINE-NOTES.md` (the former root README) section "Rules as implemented".
- Level JSON fields: [references/level-format.md](references/level-format.md).

## 3. Facts
**Board.** A rectangular grid `gridWidth x gridHeight` (shipped 4-9 wide, 4-10 tall is what the tool allows). Cells listed in
`inactiveCells` are holes: they are the game's only obstacle, drawn as walls. A gate may sit on the outer edge or on the rim
of a hole. One gate per cell side.

**Blocks.** A block is a polyomino: a pivot cell plus `shapeOffsets`; an empty list means one cell. Seven colours, the enum
order `Green 0, Yellow 1, Blue 2, Red 3, Orange 4, Purple 5, DarkGreen 6`, one material per colour for blocks and for
gates. No other colour exists in the game; a "pink" block is a colour slot repainted by the recorder.

**Gates (doors, exits).** A gate is colour + edge (Left/Right/Top/Bottom) + span (one or more border cells). A block may only
leave through a gate of its own colour; several blocks of one colour may share one gate (shipped Level 6 does). There
is no door that opens, closes, changes colour or is locked. A wrong-colour gate is skipped and its edge acts as a wall.
Design rules every shipped level keeps, measured on every version since 2026-10-19 (`level.door_problems`, rows "Rules: doors
and colours" and "Rules: colours tell apart"): every block colour has a gate of its colour, every gate's colour has a block,
every block fits through a gate of its colour (a 2-wide bar needs a 2-cell gate on a top or bottom edge, or a side gate), and
the colours shown stay apart (no two blues through one gate; the runner repaints a slot's block and gate materials together).

**Dragging.** Free 2D drag with continuous collision (collision box 0.8 of a cell): a block moves anywhere every one of its
cells is on the board, active, and not held by another block. Blocks never pass through walls or through each other; a
1-cell corridor is passable, corners cannot be cut. One drag moves one block. The solver discretises this to one pivot
move per cell step; a scripted replay moves one cell at a time along an axis.

**The exit rule (exact).** Checked only while a block is being dragged, each time its pivot enters a different cell:
1. the FIRST gate in the file's list order whose colour matches and whose cells overlap the block is chosen; later gates
   are never tried, even if that one's lane is blocked;
2. every cell of the block needs a clear straight lane to the edge in the gate's direction, leaving through the gate's
   columns (top/bottom) or rows (left/right); another block on the lane fails it; holes do not block the lane;
3. if it passes, the block snaps (0.1 s), its cells are freed, and it slides out at 0.1 s per cell over the cells to the far
   edge plus two, then it is gone. Letting go never makes a block leave; a block resting at its gate must be dragged into
   a cell where the check passes.

**Clock.** `timerCount` whole seconds (300 in every shipped level), starts on the first touch anywhere on the screen,
counts down; below 50 s every new second punches the clock and flashes it red; at zero the fail screen ("Out of Time!").
The win ("Level Completed") counts when the last block's exit slide ends; the clock keeps running during that slide. The
HUD rounds down (shows 00:00 during the last second). The tool stops the clock when the last block starts to leave, so a
near-fail is "the last block starts leaving with 1-3 s showing".

**Win and fail.** Win = every block has left. Fail = clock at zero with a block still on the board. Nothing else ends a
level, and nothing locks input after either. No moves counter, stars or score; coins are +50 per win in the menu only,
never spent (CoinBar/CoinPile are UI pictures).

**Camera.** Perspective (FOV 60, pitched 75 degrees), fixed; fitted to the board at level start with a 1.5 s glide. The tool's recorder adds its own zoom, pan and
punch-ins on top; the game has none.

**Shipped levels.** Six tutorial-size levels, all easy: minimum drags 2, 2, 3, 4, 5, 8; only Level 4 needs a block moved
aside first. A "difficult level" request therefore needs a generated level.

**Audio.** The game has no sound. Every effect and every music track in an ad is the tool's.

## 4. Procedure
When a request, a test case or a plan mentions a mechanic, run it through this list in order:
1. Is it blocks, colour gates, holes/walls or the clock? Then it is in the game; check the exact rule above.
2. Is it a look (colour, background, captions, stickers, cursor, music)? Then it is the tool's layer, not the game: see
   `cbj-prompt-controls`.
3. Is it in section 5? Then it is not possible; answer with the closest thing that is, and say what was changed.
4. For a move: one block per drag; it must reach the target through valid positions; it leaves only at a cell where the
   exit rule passes. For an order of exits, remember rule 1 of the exit check (file order of gates).
5. For a level: every gate must be reachable by a block of its colour, the solver must find a solution, and the clock must
   allow it; a level the solver cannot solve is not a level.

## 5. Not possible here
Searched for in the C# and absent: boosters, power-ups, hints, undo, bombs or countdown tiles, ice or frozen blocks,
keys and chained or locked blocks, hidden blocks, teleports, arrow or one-way blocks, neutral blocks that cannot exit,
doors that open/close or change colour, a second level in the same scene, a moves counter, stars, coins earned in play,
characters, enemies, items, textures or sprites per block (blocks are coloured meshes; their shape is their collision),
voice-over, any audio. Two blocks cannot leave at the same moment (one drag moves one block); a block cannot choose
which gate side to leave from (the rule decides); "regions" of the board are not a thing the game knows.

## 6. Evidence
- `uv run cbj show <level.json>` draws a board; `uv run cbj solve <level.json>` prints the minimum solution step by step;
  `uv run cbj check <level.json> <moves>` checks a move script cell by cell against these rules.
- `uv run pytest tests/test_rules.py tests/test_solver.py tests/test_level.py` (the port against 637 random boards and the
  six shipped levels; `test_gate_order_in_the_file_changes_the_minimum` is the file-order rule).
- A recording's `result.json` (`studio/recordings/<hash>/`) lists every drag the game actually played (`drags`,
  `block_gone_frames`, `win_frame`, `fail_frame`, `timer_start`, `timer_end`): the game's own record, not the plan.

## 7. Change rules
This skill describes the provided game, which does not change. If the port in `rules.py` is corrected, correct section 3
and `references/mechanics.md` in the same edit and bump `last-verified`. Never add a mechanic here because a prompt asked
for it.
