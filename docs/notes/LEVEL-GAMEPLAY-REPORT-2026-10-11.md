# Core requirement 2: level & gameplay generation (report)

Step done 2026-10-11/12. Repo `~/cbj-work/cbj-creative`. Plan and decisions:
`LEVEL-GAMEPLAY-PLAN-2026-10-11.md`. How to test it in the UI: `LEVEL-GAMEPLAY-CHECK-STEPS.md`.

## 1. What the brief asks, and where it stands now

"The creative should contain CBJ gameplay that is appropriate for the requested
concept" (p.5), with seven examples of what a user may ask for.

| Case item | Before this step | Now | Shown by (real runs) |
|---|---|---|---|
| A specific type of level | 4 board shapes, size, block count, colours | 7 shapes (adds cross, ring, lanes); block shapes (small, big: plus, 2x3, L4; long bars); every gate reachable by its block | "A two-room level with a narrow door and lots of long bars": six 3-cell bars on a hard door board |
| A visually interesting board | nothing measured | symmetric (blocks, colours, gates mirrored), packed (55-75 % full, one gate per colour, like the real game), colourful; a looks score in the ranking; a board picture | "A symmetric, colourful board...": mirror symmetry 100 %, touching blocks always different colours, gates on 4 sides |
| Difficult or easy | 3 bands; hard capped at 2 repositioning drags; the hard narrow centre sometimes needed the hand-made fallback | fairer naive player, a fairness margin, local search, a larger search cap for hard: 24/24 levels in band (23/24 before), up to 3 repositioning drags | "A really hard level where nothing can leave at the start": hard, 0 blocks can leave at once, 2 blocked mistakes |
| A gameplay progression | nothing | a pacing curve (speeds up, slows down); orders such as colour by colour | "Start slow and speed up": pauses 1.28 s in the first third, 0.33 s in the last |
| A near-fail moment | 00:01 left, fixed | 00:01-00:03, as asked | "...wins with 3 seconds left": the clock shows 00:03 at the last exit, 2 blocked mistakes |
| A satisfying solve | the solver's first shortest solution | the shortest solution with the longest final run of exits; a key move; "One move frees them all!" | "A satisfying solve: one move frees everything": drag 1, then all 10 blocks leave in a row |
| A specific sequence of interactions | nothing | ordered steps: leaves / moves / stuck / hesitates, for a colour and any / biggest / smallest / longest, all, first / next / last | "Red leaves first and purple leaves last": drag 1 and drag 9; "The red block gets stuck first": drag 1 |

Every one of these is measured on the recording afterwards and shown in the UI (section 4).

## 2. What was built, and why

The split stays the same as in the text-to-creative step: **the LLM writes the brief; code
builds, plays and checks**. The new brief fields are data, so the engine can execute them
exactly and an edit can prove what it changed.

**Ordered steps (`events.py`).** A request like "first move the yellow block out of the way, then
the blue one escapes" becomes steps that name blocks by colour and size. The solver is an exact
A* search over (board position, steps done): it finds the fewest drags that do the steps in
order. It does not use the free solver's shortcut "take any open exit first", because with an
order to keep, an early exit can make a later step impossible (Fable 5.1 built a 3x3 board that
proves it). With no steps it gives the same minimum as the free solver on 122 random boards.
"Stuck" (a block dragged toward its gate and stopped by another block) is not a solver step: it
is played as a targeted mistake where the board offers one, like the planned mistakes before.

**A satisfying finish.** Among the shortest solutions, the one whose final run of exits is
longest: all repositioning drags first, then every block leaves one after another. It never adds
a drag (allowing one more drag gained almost nothing and cost up to 85 s of search). On the
showcase level, the default solution ends with 6 exits in a row; the satisfying one with all 7.

**Board structure and looks (`generate.py`).** New shapes, piece sets and three styles. Two
changes made the generator much better at every shape:
- *Gates a block can reach.* Each block's gate is placed only where that block, alone on the
  board, can slide onto it and pass through it. Before, a vertical bar could get a gate behind a
  2-cell door it can never pass: on door boards with long bars, solvable candidates went from 2
  of 40 to 19 of 25.
- *Local search.* The best boards are changed one step at a time (move a block, move a gate, swap
  two colours, change a piece), and a change is kept if the board scores better.

**Fair difficulty (`difficulty.py`).** The simulated naive player now never goes back to a
position it has already been in, and gives up after 12 drags per block. A board where it gives up
on more than 5 % of its runs reads as a maze, not a puzzle, and is rejected (the search uses
2.5 %, so a board stays fair on the final 200-run rating). Packed boards made the old player
wander for 80 drags; now they rate fairly. Existing numbers barely moved (the hourglass: 1.29x to
1.26x the minimum).

**Checks (`checks.py`).** See section 4.

**UI.** A *Level & gameplay* card (board picture, move list, checks) and a *Level only* button
that builds the level and plans the moves without recording (about 30 s instead of 2 minutes).
Terminal: `cbj generate`, and `cbj scenario --events/--finish/--curve/--clock-left`.

**Planner.** The new fields, a table from concepts to gameplay (relaxing: easy, a satisfying
finish, calm; rage: hard, two mistakes, near-fail; "can you solve it?": a cliffhanger), and what to
refuse with a reason (two blocks leaving at once, choosing a gate side, board regions, several
levels in one ad). The code still decides what the prompt may change: the new fields, the board
shape, the difficulty and the ad length are taken only when the prompt's own words ask for
them (the end-to-end run caught the model adding an unasked hourglass, an unasked "hard" and an
unasked 35 s).

**Nothing old changed by accident.** With none of the new fields, plans are byte-identical to
before (80 plans compared), the level cache keys are the same, and recording keys only gain the
new fields when they are set, so existing creatives, cached recordings and edit proofs still work.

## 3. How it was checked

1. **Plan review with Fable 5.1** (before building). Main decisions: "stuck" goes through the
   mistake planner, not the solver (the solver version failed on 7 of 20 random cases); no exit
   shortcut in the ordered solver; no extra drags for the satisfying finish; the default play
   stays as it was (cache consistency); fix the naive player before packed boards; multi-level
   ads cut from this step.
2. **Measurements.** The generator baseline before and after (section 5); the satisfying-finish
   search costs; the ordered solver against the free solver.
3. **The real game.** One level of each new kind recorded with the recorder's cell-by-cell
   check: big blocks (plus, 2x3, 3x2, L4, J4), long bars, a ring with gates on the hole's inner
   rim, a packed board with shared gates, symmetric, cross, lanes. All cleared, no mismatch.
4. **20 test prompts end to end** (Fable's list; real planner, real recordings), all seven case
   items, two edits and a refusal. Round 1 found 9 problems (below); rounds 2 and 3 re-ran the
   affected prompts.
5. **Fable 5.1 check of the code**: 15 findings (2 high), all fixed with tests.
6. **Fable 5.1 confirmation** of the fixes: section 7.
7. **Tests**: 493 fast tests pass (66 new), plus the 28 that drive the real game.

**Problems the end-to-end run found, and the fixes:**
- door board with long bars failed: gates only where the block can reach them (above);
- the planner added an unasked hourglass, "hard" and 35 s: shape, difficulty and length need the
  prompt's own words now;
- "all the yellow blocks leave last" was always impossible (Fable found the cause): fixed;
- "red leaves first" with a near-fail: a hard level lets no block leave at the start, so the level
  is made medium and the brief says why;
- "the red block gets stuck first" made an all-red board: a colour named to point at a block is
  no longer the board's only colour;
- "then the rest" became an impossible step: such a step is dropped with a note;
- a search limit crashed an impossible order: now the play goes on without the order and says so;
- five big blocks on a small board silently became four: the brief and the checks say so;
- the satisfying finish was slowed by a pacing curve: the key move and its run keep their pace.

## 4. Checks: what is measured, and from where

Each version keeps a list of checks (`version.json`), shown in the UI with its source.

| Check | Measured from | What it compares |
|---|---|---|
| Planned moves | recording | every drag: the block, the cells it entered, the outcome (left, stopped, cut short) |
| Ending | recording | the game's status and its clock (00:0N for a near-fail) |
| Mistakes | recording | mistakes played against the number asked |
| Order of interactions | recording | each step, and the drag that did it; "first" and "last" |
| Satisfying finish | recording | the key move (never a mistake) and the run of exits after it |
| Pacing curve | recording | average pause in the first and last third |
| Difficulty, block count, block shapes, board shape, board looks | level file | the solver and naive-player numbers; sizes; symmetry, fill, colours, gate sides |

A check can only pass if the recording did the thing: the "Planned moves" check ties every plan
note to the cells the game logged, and a recording with a different number of drags stops all
further checks.

## 5. Results

**Generator, the same 24 runs before and after** (4 shapes x 3 bands x 2 seeds, 20 s budget):
23/24 in band before, 24/24 after. Hard levels now reach 3 repositioning drags (the ceiling was
2), and the hard hourglass no longer needs the hand-made fallback (before: one of two seeds came
out unfair, the naive player needing 10x the minimum).

**New options** (15 runs): 14/15 hit their target. Cross, ring and lanes in band; big blocks,
long bars, small blocks; packed 64-67 % full; symmetric 100 %; colourful; the satisfying finish
100 % of the blocks in a row; two ordered-step lists at no extra drags. The miss: a hard
symmetric pillared board rated medium-to-hard (a symmetric board cannot use the local search
without losing its symmetry).

**20 prompts end to end** (final round for each; about 1.5-2.5 minutes a prompt):

| # | Prompt | Result |
|---|---|---|
| 1 | A level with big chunky blocks, only 5 of them, on a small board | big blocks, hard; Block count adjusted: 4 fit (asked 5), said so |
| 2 | A two-room level with a narrow door and lots of long bars | six 3-cell bars, hard: pass |
| 3 | Make it packed like a real jam level, 9 blocks | 9 blocks, 61 % full: pass |
| 4 | A symmetric, colourful board using every colour, gates on all four sides | 100 % mirror, gates on 4 sides: pass (4 colours: a mirror pair shares one) |
| 5 | A ring-shaped board with a hole in the middle | ring with inner-rim gates: pass |
| 6 | An easy level a child could solve, calm pace | easy, clean win: pass |
| 7 | A really hard level where nothing can leave at the start | hard, 0 can leave at once, 2 mistakes: pass |
| 8 | Medium level, 7 blocks, only blue, red and yellow | medium, 7 blocks, 3 colours: pass |
| 9 | Start slow and speed up until the end | pauses 1.28 s to 0.33 s: pass |
| 10 | Clear the board colour by colour: blue, then red, then yellow | drags 1, 8, 11: pass |
| 11 | Near-fail: stuck twice, wins with 3 seconds left | 2 mistakes, 00:03: pass |
| 12 | The red block gets stuck first, then the player figures it out | drag 1: pass |
| 13 | A satisfying solve: one move frees everything | 1 key move, 10 in a row: pass |
| 14 | The biggest block leaves last, clean win, no mistakes | drag 11: pass (4 tied for biggest, the first used, said so; ties are now avoided by the generator) |
| 15 | First move the yellow block out of the way, then the blue one escapes, then the rest | drags 1 and 5: pass |
| 16 | Red leaves first and purple leaves last | drags 1 and 9: pass |
| 17 | Edit: make the level harder, keep everything else | new hard level, "new gameplay on a new level": pass |
| 18 | Edit: keep the level, stuck on the green block instead | the kept level has no green block: adjusted, said so |
| 19 | Two blocks leave at the same time | not supported, with the reason |
| 20 | Relaxing ASMR-style ad | easy, calm, all 10 in a row: pass |

Every recording played exactly as planned (Planned moves: pass on all 19 made).

## 6. Known limits

- One level per ad. A progression across levels (level 1 easy, level 2 hard) needs the
  compositor to join recordings; designed, not built (next step after the image and video
  inputs if time allows).
- A hard symmetric board is harder to find (no local search for it) and may rate medium-to-hard.
- An easy level gives a short play, so a 30-35 s ad shrinks to about 27 s (the brief says so).
- A level kept by an edit can lack a block an ordered step names; the step is left out, said so.
- Difficulty bands are descriptive (solver and simulated player), not calibrated on player data.
- The planner takes 15-45 s; making an ad 1.5-2.5 minutes; *Level only* about 30 s.

## 7. Fable 5.1 confirmation

Fable re-ran its probes on the fixed code: 12 of its 15 findings fixed, 3 partly. It found one
regression from the fixes and six smaller defects; all are fixed, and its own probe scripts were
re-run on the result:

| Found | Fix | Re-checked with Fable's probe |
|---|---|---|
| R1 (medium-high). The time-out fix ("the cut-short block is one no step names") was written as a full "last" step, which also blocked other exits: 7 of 42 two-step orders on the hourglass fell back, and the level choice and the plan disagreed | the step now restricts only the final exit (`final_only`); an order the play cannot keep, for any reason, falls back with its reason, and the level choice reads the same note | 42 orders with a time-out: 7 at no extra drag, 33 at one (keeping the cut-short block out of the order), 2 fall back with the reason; the level choice and the plan agree on all 42 |
| R2. A block that cannot move at all could get a gate (the game checks for an exit only when a block enters a cell) | a gate needs at least two placements of its block | the jammed plus piece is refused |
| R3. The evidence rules dropped natural asks ("make it intense", "a gorgeous board", "keep it snappy", "rise"), and "2 seconds left" counted as an ad length | more words; "N seconds left / remaining / on the clock" is the clock, not the length | 27 phrasings accepted, the 2 that should be dropped are dropped |
| R4. "Colour by colour: blue, red, yellow" got a fourth colour | extra colours only when a colour just points at one block | exactly the three colours |
| R5. Lanes on a short board had no walls | lanes need 7x6 at least, with a note | |
| R6. "The red block leaves last" with two red blocks marked the first red exit | a single-block "last" step completes on the final exit; the other red may leave earlier | done at the final exit |
| R7. A note written twice on a direct `plan()` call | harmless (the brief converts it first); left | |

Verified by Fable with no regression: plans without the new fields unchanged; the ordered
solver on all 42 pair orders, 7 "first", 7 "last" and 42 "moves then leaves" on the hourglass;
the satisfying finish equal to a brute-force optimum on 25 boards; 2131 local-search changes all
valid; 79 symmetric colourful boards with no touching same-colour pair; 3927 gates with no
false refusals against the solver; the level cache keys and recording keys unchanged.
