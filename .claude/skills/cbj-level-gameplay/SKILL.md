---
name: cbj-level-gameplay
description: Core requirement 2 of the CBJ brief in cbj-creative - how a prompt about the level or the play becomes a generated, solvable level and a recorded playthrough in the real game: the seven board shapes, piece sets, looks (symmetric, packed, colourful), size and block ranges, the easy/medium/hard bands from the exact solver and a naive player, the four endings and their defaults, mistakes, hesitations, the grammar of an order of interactions, the streak finish, near-fail seconds, pacing tempo and curve, one level per ad, and the checks measured on the recording. Use when a prompt asks for a type of level, a visually interesting board, a difficulty, a progression, a near-fail, a satisfying solve or a specific sequence of interactions, and when judging whether generated gameplay matches what was asked.
metadata:
  spec-version: "1"
  last-verified: "2026-10-19"
---

# Level and gameplay generation

## 1. Purpose
The brief asks for gameplay "appropriate for the requested concept". Here the model never makes a level or a move: it
fills brief fields; the generator builds a board the game's rules accept, the solver proves it, the scenario planner
plans human-looking play toward the asked ending, the real game records it, and checks measure the result. This skill
lists what can be asked, what each ask produces, and how to tell that it did.

## 2. Source of truth
- `src/cbj/generate.py` (SHAPES, PIECES, PIECE_SETS, STYLES, size tables, local search, `band_of`), `src/cbj/difficulty.py`,
  `src/cbj/solver.py`, `src/cbj/events.py` (ordered steps, A* over position + steps done), `src/cbj/play.py` (endings,
  mistakes, hesitations, pacing), `src/cbj/checks.py` (`gameplay_checks`, `level_checks`).
- `docs/ENGINE-NOTES.md` (the former root README) "Level & gameplay generation", "Difficulty", "Length". Reports: `~/cbj-work/LEVEL-GAMEPLAY-REPORT-2026-10-11.md`,
  `~/cbj-work/LG-SCENARIOS-REPORT-2026-10-13.md` (30 scenarios, 19 run, 11 skipped as not in the game).
- Rules of the game: `cbj-game-rules`.

## 3. Facts
**Level source.** `auto` = the tool's hand-checked hard 6x8 narrow-centre showcase; `shipped` = the game's levels 1-6 (all
easy, tutorial size); `generate` = a new board to the spec. Any ask about structure, shape, size, block count, colours
or difficulty means generate.

**Shapes (7).** open (plain rectangle), narrow_center (hourglass / waist / bottleneck), door (two rooms joined by a gap),
holes (several separate wall cells spread inside the board: a mirror pair low down, one or two in the middle higher up, a second pair on tall boards; "several fixed walls / obstacles"; a 2x2 pillar read as "only one obstacle" in nine of nine viewer reviews, 2026-10-15), cross (corners cut away), ring (a big hole in the middle), lanes (walled lanes joined
along the bottom). Default size per shape and band, from 6x6 (open, easy) to 8x8 (hard cross, ring, lanes); width 4-9,
height 4-10, blocks 2-10 only when the prompt gives them, else sized to the ad's length.

**Pieces.** mixed (default: 1x1, 2-bars, 3-bars, square, L, J, T), small (1-2 cells), long (bars of 3-4), big (square, T,
L4, J4, plus, 2x3, 3x2), varied (a small, a long and a corner piece together).

**Looks.** symmetric (blocks, colours and gates mirrored; searched by mirror-pair moves, gate re-placements and colour swaps, so a hard symmetric board is reachable, `_mutate_symmetric`), packed (55-75 % of cells hold blocks, one gate per colour, as in
the real game), colourful (every colour, touching blocks differ), spacious (room to move: at most 5 / 6 / 7 blocks for
easy / medium / hard when no count is given, no two blocks touching, no two blocks of one colour touching even at a
corner (they read as one piece: a viewer counted 4 blocks on a 5-block board, 2026-10-15; `looks()["merged"]`; since v7 every board that is not packed is searched until no two blocks of one colour touch: colours are spread greedily (`_assign_colours(spread=True)`), mirror pairs get colours their touching neighbours do not have (`_assign_pair_colours`), a pair that would touch itself at the axis is not placed, and a merged pair costs 25 points),
35 % of the cells or fewer; read from "enough / plenty of free space", "room to move", "not crowded", "spacious"). Packed and spacious never together. "A visually
interesting / eye-catching board" = symmetric + colourful. Mirror pairs share a colour and a size, so a mirrored board
needs 2C-1 blocks to show C requested colours (the count is raised with a note), and a block a superlative names
("the biggest / longest yellow block") is placed on the axis, bigger / longer than every pair, in that colour
(`_star`, only when the events name one; a 5-block mirrored board had no yellow at all, 2026-10-15). A requested
colour missing from the board or a named block that is not the one of its kind is never good enough. A looks score (contrast, gate sides, fill, symmetry, spacing)
ranks candidates, and a spacious board that fails its rule is never good enough.

**Difficulty bands.** Measured, not labelled by hand: the exact minimum solution (drags, repositioning drags, blocks that
can leave at the start) plus a naive player (takes an exit when one is open, else a random drag to a position it has not
seen; 200 seeded runs; gives up after 12 drags per block). easy: nothing to reposition, most blocks can leave at once.
hard: no block can leave at the start, two or more repositioning drags, the naive player needs 1.2-4x the minimum.
medium: one repositioning drag (or a naive ratio of 1.1-1.3). So "medium with at least two repositioning moves" is
a contradiction in the tool's bands: the level row says a medium board has one and a hard level gives two or more
(`planner._repositioning_count`).
Boards where the naive player gives up more than 5 % of the time are unfair and rejected. Gates sit across the board on
hard levels so routes cross. Local search (move a block, move a gate, swap colours, change a piece) improves the best
boards. Same spec + seed = same level; levels are cached by their spec hash.

**Moves.** `level.moves` 4-16 sets the length of the shortest solution when the prompt gives a number ("solved in 10-15
moves" = 12); repositioning drags count.

**Endings.** win (clean solve), near_fail (a mistake, a stuck moment, then solved with 00:01-00:03 showing; the default
when nothing is said), cliffhanger (stops with 1-3 blocks left and asks for the move), time_out (one move short at zero;
only when a fail is asked; social channel, medium or hard). The clock of a near-fail is set by the ending (1-3 s,
`clock_left_s` when given).

**Mistakes and hesitations.** mistakes 0-3 of kinds blocked (drags toward its gate, another block stops it), wrong_way,
fidget; hesitations 0-3 (pick up, put back); null = the ending's default; clamped per ending.

**Orders of interactions (events).** Steps in order, other moves may come between: block = a colour or null, which = any /
biggest / smallest / longest, all = every block of that colour; action = leaves / moves (aside) / stuck / hesitates / blocks (moved into another block's way: a wrong move the player then undoes; `by` = the colour it then blocks when named; `play.blocking_moves`: a legal non-exiting drag after which the victim cannot leave and could without the mover; the search wants a board that offers it at the start; "an early move sends the yellow block into a position that blocks the green block's route" = [{yellow, blocks, first, by: green}], read by `planner._blocking_move` from the words when the model did not);
when = first (the video's first move) / next / last (the last block to leave). Needs a sequencing word in the prompt.
Examples: "first move the yellow block aside, then the blue one escapes" = [{yellow, moves, first}, {blue, leaves,
next}]; "clear it colour by colour: blue, then red" = [{blue, all, leaves}, {red, all, leaves}]; "the biggest block
leaves last" = [{null, biggest, leaves, last}]; "the red block gets stuck first" = [{red, stuck, first}] (one of the
mistakes). An exact A* search over (position, steps done) finds the fewest drags that do the steps in order, without the
free solver's exit-first shortcut. An order that cannot happen on the level is said so and the play goes on without it.

**Satisfying finish.** `finish: streak` = the shortest solution with the longest final run of exits: one key move, then
every block leaves one after another ("One move frees them all!").

**Camera.** The game's own fit is kept (zoom 1.0) unless a zoom is asked: the game's camera already fits the board's width, so any automatic zoom crops the sides (tried and reverted 2026-10-14); a square board simply sits short in a tall frame.

**Clock.** A win on an easy or medium level keeps the clock above 0:50 (the HUD flashes red under it); a win on a hard level gets a tight clock, landing with about 8 s left (`play.TIGHT_LEFT_S`, part of the recording's key), unless the prompt asks a clock ("generous timer" plans a number of seconds, kept when it stays calm) or the tempo is calm. The end card then says "Cleared with 00:08 left"; a win in under 15 s of play says "Can you do it faster?" instead of its seconds (they read as easy).

**Pacing.** length 30-60 s (shorter is raised to 30 with a note); tempo calm / normal / fast (pauses between moves);
curve even / speeds_up / slows_down (pauses and finger speed follow it). A level that plays too few drags for the length
is swapped for a generated one of the same difficulty sized to the length (unless a level number was asked). A solve
that is still short for the ad (drags x 1.6 s + 3 s + 3.5 s a mistake under the length minus 15 s) is paced deliberately (grade "slow" when the play would still fall short by more than a drag: a long look before every other drag and a thought (0.9-1.6 s) before the rest; a new creative also gets the hesitations its ending allows, `studio._breathe_short_play`, never an edit; the play filled about 60 % of the 48 audited ads, 2026-10-15) (a long look of 1.6-2.2 s before each drag (1.8-2.8 s and a gliding finger at a calm tempo; a 3-4 drag solve keeps one quick closing drag), the slowest finger, the last two drags keep the closing cascade and a streak finish keeps its whole run of exits after the key move; the stuck moment after a mistake gets its longest pause; real time, the clock stays true; not for a fast tempo or a time-out; a cliffhanger's play is paced too); only then is the ad filled, replay first (never before a cliffhanger's question: the cut stays live) and held screens last: the replay may show the whole solve at half speed (up to 8 beats, 16 s), the result is held to 2.5 s (a 5 s finish); the end card, which carries the button, may run to 10 s before the result is held longer (4 s, then 12 s for a very short play); an end card beyond 6 s is filler. An asked block count that caps the play (4+ drags under the length's target) is said in the plan. The opening is never frozen for more than 0.5 s: the game
moves within the first second, because that is when a viewer decides. The primary play is never slowed in post: the
HUD clock is on screen and must tick in real time; only the replay is a screen-time device, and it is labelled.

**Checks on the recording** (per version, `checks`): every drag moved the planned block through the planned cells to the
planned outcome; the ending and the clock; the mistakes; each step of the order and the drag that did it; the final run
of exits and its key move; the pauses in the first and last third. From the level: difficulty numbers, block count,
block shapes, board shape, looks.

**Common to every workflow (2026-10-19).** The translation once, the rules rows and the shared case rows on every version,
the best version kept, the stated values kept, the length guard, the viewer-only rule, the repeated-miss limit, the fixed
board's pace said at plan time, the kept log lines, the feedback step and the report: listed once in `cbj-creative-evidence`
section 3 ("Common to every workflow") and in `src/cbj/workflows/__init__.py`.

## 4. Procedure
Reading a level/gameplay ask:
1. Map structure words to shape, pieces, looks, size, blocks, colours (limiting colours only); keep the rest null.
2. Map mood words with the concept table in `cbj-prompt-controls`; set the ending; near_fail if nothing is said.
3. Write orders only when a sequencing word is present; one step per clause; "then the rest" needs no step.
4. Put difficulty in the band; "harder / easier" in an edit edits the same board (at most 3 small changes, HUD number
   kept), never a new board.
5. Length 30-60; tempo and curve only when asked.
Judging the result:
6. Open the version's checks: every row pass or info; a fail names what the recording did not do.
7. Open the board picture and the move list (*Level only* in the UI, or `uv run cbj solve`): the asked shape, pieces,
   colours and blocks are visible; the minimum solution is in the band.
8. For an order: the drags that did each step are named in the check; they appear in the asked order in `result.json`.
9. For a near-fail: the clock shows 1-3 s as the last block starts to leave; for a time-out: the fail screen; for a
   cliffhanger: the asked number of blocks still on the board at the cut.

## 5. Not possible here
Mechanics the game lacks (`cbj-game-rules` section 5: ice, keys, chains, bombs, hidden/arrow/neutral blocks, opening
doors, teleports). More than one level in one ad (one level per ad in this version; a multi-level ad is designed, not
built). Two exits at the same moment. Choosing which side a block leaves through. Regions of the board. A guaranteed
exact move count on a shipped level (their minima are 2-8). Hand-calibrated difficulty labels: bands are measured, and
the write-up says they need real player data to calibrate.

## 6. Evidence
- `uv run cbj generate --shape narrow_center --difficulty hard` builds and rates a level; `uv run cbj difficulty <level>`
  prints the numbers; `uv run cbj scenario` records human-looking play toward an ending.
- Version files: `level.json`, `board.png`, `checks` in `version.json`; the recording's `result.json` (`drags`,
  `block_gone_frames`, `win_frame`, `fail_frame`, `timer_*`).
- Tests: `tests/test_level_gameplay.py`, `tests/test_events.py`, `tests/test_play.py`, `tests/test_difficulty.py`,
  `tests/test_solver.py`. Generator 24/24 boards in band on the 2026-10-11 run.

## 7. Change rules
A new shape, piece set, look, band rule, ending, event action or check changes section 3 in the same edit. If the
generator's size tables or the fill order change, update the Pacing paragraph. Bump `last-verified`.
