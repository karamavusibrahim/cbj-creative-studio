# Scenario step: what was done, why, and how to check it (2026-10-10)

## In one paragraph

Until this step the tool could record the real game playing a level, but only the solver's
perfect solution: every drag correct, every pause the same. That looks like a robot, not a
player, and an ad needs a story. This step adds `cbj scenario`. It takes a level and a requested
**ending** (win, near-fail, cliffhanger or time-out) and plans how a person would play toward
that ending:
- a believable mistake;
- a moment of being stuck;
- a hesitation;
- a quick finish.

It sets the game clock so the game itself shows the ending (00:01 left, 00:08 at the cut, "Out
of Time!"), records it in the real game, and checks the recording frame by frame. Fable 5.1
checked the step twice, and everything it found is fixed.

---

## 1. Why this step

The case asks for gameplay "appropriate for the requested concept" (p.5): a near-fail moment, a
satisfying solve, a specific sequence of moves. Its own example prompt is "a difficult level with
a narrow center section... where the player almost fails before solving it" (p.4). The ad research
(COMPETITOR-ADS-2026-10-10.md) showed what works:
- the winning puzzle ads show a player who **can't reach** a colour and gets stuck;
- most ads end **unresolved** (a cliffhanger);
- a **near-fail win** is a gap nobody runs.

So the gameplay layer must produce these on demand, and they must stay **exact and repeatable**.
The case's most important point is controlled editing (p.7), and that only works if the same
request gives the same video.

## 2. What was built, and why each piece

### 2.1 Four endings

| Ending | What the viewer sees | Why |
|---|---|---|
| **Win (S3)** | A clean solve; the last drags speed up | The plain "satisfying solve" |
| **Near-fail (S4)** | A mistake, a stuck moment, a hesitation, then a fast finish with **00:01** left | The case's p.4 example, and the gap in competitors' ads |
| **Cliffhanger (S1)** | The easy blocks are cleared, the last two get in each other's way, cut with "Can you see the move?" | What most winning ads do |
| **Time-out (S5)**, opt-in | The last block races for its gate; "Out of Time!" lands one cell short | Fail endings do well on social channels, but CBJ's own ads avoid them, so this is opt-in and refused on easy levels |

### 2.2 Believable mistakes

A mistake is a real, legal drag that does not help. Three kinds, modelled on the winning ads:
- **blocked** (the main one): a block that cannot leave yet is dragged toward its gate until
  another block stops it. The finger keeps pressing for a moment, so the viewer sees "I can't get
  there".
- **wrong way**: a block that has to move is moved somewhere that does not help.
- **fidget**: a one-cell nudge, at most once per ad, and only of a block that cannot leave.

Rules, and why:
- **It must cost the player 1 or 2 extra drags.** The solver measures this. A "mistake" that
  costs nothing is really progress; one that costs more looks clumsy.
- **It comes in the first three drags** when the board offers one. The story needs a wrong start.
- **It never comes in the last two drags.** The player needs room to recover.
- **After it, the solver plans again** from the new position, so the rest of the play is always
  a correct, shortest recovery.
- **The drag right after a mistake always shows a reaction.** That is a 1.8-2.5 s "stuck" stare
  when it is the real fix, or a shorter 1.2-2.0 s "noticing" pause before an obvious exit.
- **Parking a block at a gate of the wrong colour is never used.** It reads as not knowing the
  rules.

### 2.3 Hesitations

A block is picked up, held for about 0.7 s, and put back. A near-fail has two:
- one mid-game, on a block the player considers and leaves;
- one on the very last block, just before it leaves ("a moment of doubt").

### 2.4 Pacing in whole frames

Every pause is chosen by what the player is doing:

| Pause | Length | When |
|---|---|---|
| confident | 0.35-0.6 s | before an exit the player can see |
| thinking | 0.9-1.6 s | before moving a block out of the way |
| stuck | 1.8-2.5 s | before the fix after the last mistake |
| cascade | 0.3-0.45 s | the quick closing drags |

Finger speeds are whole frames per cell: 4, 5, 6 or 8 frames, that is 7.5 down to 3.75 cells per
second. **Why whole frames:** the video runs at 30 frames per second, so this makes every timing
exact, with nothing falling between two frames.

### 2.5 Exact timing: one dry run, then pauses only

This is the core idea. A **dry run** plays the plan in the real game and logs every frame without
filming, in about 4 s. A pause shifts every later frame by exactly its own length. So, from the
dry run alone, the planner can work out the clock and the length:
- **Near-fail:** pick a whole-second clock and move one or two pauses by a few frames, so 1.5 s is
  left when the last block starts leaving. The HUD then shows 00:01.
- **Cliffhanger:** set the clock so 00:08 shows at the cut.
- **Time-out:** move the pause before the last drag, so the clock hits zero on the exact frame the
  last block enters the cell next to its gate.
- **`--length`:** stretch or shrink all pauses a little, in proportion.

Finger speed is never changed: a slow finger reads as slow motion. Then the real recording is
made, and **every drag must start and end on the predicted frame**. If one does not,
`cbj scenario` reports it.

### 2.6 Finding a cliffhanger

A cliffhanger needs two blocks left, one of them trapped, and the position must still be a puzzle
(a block has to be moved first). The optimal solution rarely passes through such a position, so a
search looks for it. For each pair of blocks to keep, it clears the other blocks first, as players
do, and stops when the pair is trapped and still a puzzle. On the narrow level the result is green
and red head-on in the waist; the answer is one sideways move.

### 2.7 A faster solver

Planning solves hundreds of positions (every candidate mistake is measured), and on the narrow
level one solve took 2.1 s. A second solver, `solve_fast`, uses A*: every block left needs at
least one more drag, which lets the search skip positions that cannot be part of a shortest
solution. It searches 589 positions in 13 ms instead of 43,446 in 2.1 s, and a near-fail plan
dropped from 30 s to 0.2 s. It always gives the same minimum as the first solver. Fable proved
this, and tests compare the two on every level and on 365 random boards (121 of them solvable).

### 2.8 Small runner additions

The Unity runner got three per-drag options and one log:
- **push:** the finger presses on past the last cell, into the blocker;
- **push direction:** a block that cannot move at all can still be pressed into its neighbour;
- **hold:** the finger stays down;
- **cell frames:** the runner logs the frame on which each cell was entered (needed for the
  time-out).

The game holds a pushed block at the blocker, so its cell never changes. The runner's drag loops
now stop the moment the fail screen appears.

### 2.9 Records you can reproduce

Each recording folder holds:
- `gameplay.mp4`, the video;
- `play.json`, every beat, the fit, the prediction, the result and the level's difficulty;
- `level.json`, the level with the clock the ad used;
- `job.json`, the runner's exact input.

`cbj rerun FOLDER -o NEW` records the folder again from these files alone and compares the two
recordings. The **seed** chooses which mistakes and hesitations to use, nothing else, so the same
level, ending and seed always give the same plan.

### 2.10 Easy levels degrade instead of failing

On a level where every block can just leave, there is no believable mistake. The plan then plays
without one and writes the reason into `play.json`; `cbj scenario` prints it. A time-out is refused
on easy levels: of the shipped levels only Level 4 qualifies. It is also refused when the last
block is a single cell from its gate, because there is no race to cut short.

### 2.11 The narrow-centre level

`data/levels/gen/narrow_center_01.json` came from Fable's search for the case's example prompt.
- A 6x8 hourglass with a two-lane waist and 7 blocks.
- 9 drags minimum, 2 of them repositioning.
- A simulated naive player needs 1.29 times the minimum. Every shipped level is at 1.25 or below.

---

## 3. Results

| Ending | Video | Clock | What the recording shows |
|---|---|---|---|
| Win | 16.1 s | 68 s, 55.9 s left | Clean solve; the clock stays above 0:50, where the game's HUD starts flashing red |
| Near-fail | 21.5 s | 19 s, **1.50 s left** | Dark green blocked by purple at 0:02, stuck until 0:05, purple doubted at 0:11, orange doubted at 0:16.5, orange leaves at 0:18.5 with the HUD at 00:01, win screen at 0:19 |
| Cliffhanger | 16.5 s | 24 s, **8.6 s left** | Red into the waist at 0:07, green blocked by red at 0:10, green pressed into red at 0:14, cut at 0:16.5 |
| Time-out | 19.7 s | 16 s | Orange grabbed at 0:15.5 with 1.5 s left (00:01), the HUD turns 00:00 at 0:16.0, the race starts at 0:16.4, "Out of Time!" at 0:17.0, one cell from the gate |

- **Every recording landed on its predicted frames.**
- **Recording the near-fail again** from its folder gave the same game state on every frame.
  644 of 644 frames were pixel-identical in my run; in Fable's run 1 frame differed by a few
  pixels (57.6 dB), which is the graphics driver and is invisible.
- **`--length 20.5`** gives exactly 20.50 s; `--length 60` is refused with the reachable range
  (19.2-22.7 s).
- **Tests:** 309 fast tests and 28 Unity tests pass. Among them:
  - the four endings;
  - a rerun from a folder;
  - the time-out's 00:01 at the grab;
  - mistakes on Levels 4-6;
  - cliffhanger puzzles on Levels 4-6;
  - the clock fit on a real dry run's clock.

Picture strips: `cbj-creative/reports/scenario/`. Videos: `cbj-creative/renders/nc01_*/gameplay.mp4`.

---

## 4. Two checks by Fable 5.1, and what changed

**First check** (code, videos, case PDF). All its earlier rules were applied except the level
generator, which is planned for Oct 12. Nine findings were fixed:
- **Time-out:** the stare before the race is gone.
- **Cliffhanger:** the set-up drags into a blocker are now played as attempts, pressed and held.
- **Clock fit:** it tries both nearby clock values before giving up.
- **Runner:** it stops at the fail screen.
- **Easy levels:** they degrade instead of crashing.
- **Fidgets:** only on blocks that cannot leave.
- **Notes:** written from the geometry.
- **`level.json`:** written next to the video.
- **Wording:** corrected.

Then a `--length` bug turned up while I was writing the guide. Two clocks fitted equally well, and
floating-point noise picked the one that undid the length. Options are now compared in whole
frames.

**Second check** (fixes, plus following this guide step by step). It confirmed most fixes and
determinism across three separate processes, and found:

| Found | Fixed |
|---|---|
| The cliffhanger search skipped the real puzzles it was meant to prefer, so on Levels 4-6 the "Can you see the move?" cut needed no move | Corrected; Levels 4-6 now cut on a real puzzle (tested) |
| A mistake could be followed by a calm 0.5 s exit, with no reaction | The drag right after a mistake always carries a reaction pause (tested on 4 levels x 5 seeds) |
| Time-out: 00:01 was on screen for only one frame | The grab now comes with 1.5 s left, so 00:01 shows for half a second (checked on the real frames) |
| The time-out's `play.json` had a wrong predicted length | Set to none; the fail frame is what is predicted and checked |
| An untested one-cell time-out branch | Removed; such levels are refused with a clear reason |
| `--length` could drift by a few frames | The smallest pause change that still shows 00:01 is taken |
| "The folder reproduces the video" had no command | `cbj rerun` |
| Small items: hesitations could be dropped, `--left` was silently ignored on a win, `--length` with `--plan-only`, a runner hold guard | All fixed |
| Docs: "1,500 random boards" was the number generated, not compared; two guide rows were inexact | Corrected (365 compared) |

---

## 5. Honest limits

- **These are gameplay clips, not finished ads.** The hook, captions, sound, hand cursor and end
  card come from the compositor, the next step.
- **Length.** With human pauses this level plays 14-23 s, depending on the ending. That suits a
  30 s ad (a 2-3 s hook, about 20 s of gameplay, a 4-5 s end card). A 60 s ad needs two clips
  joined together, or a bigger level.
- **The game rounds its clock down.** The last second always shows 00:00, so a time-out race
  always runs under 00:00. The viewer sees 00:01 at the grab.
- **One hard level.** There is one hand-searched hard level. The generator, as a command, comes
  next.
- **The HUD badge says "Level 1"**, taken from the file name. `--label` sets the number the ad
  should show.
- **The cliffhanger search is greedy.** It is deterministic and checked, but not guaranteed to
  find the shortest route.
- **No AI yet.** Everything so far is the deterministic core. The AI half (the language planner,
  image and video inputs) is planned for Oct 13-14 and must not slip.

## 6. Case fit (Fable's view)

This step delivers the case's example 1 (p.4) as gameplay: a narrow-centre level, a believable
blocked attempt and a visible 00:01 recovery, recorded in the real game. Consistency (p.8) is
proven: identical game state across recordings, and every predicted frame hit. "Appropriate
gameplay" (p.5) is a real control: ending, mistakes, hesitations, seed and length. Fable's main
warning was that the believability rules held only on the hand-made level. That is now fixed and
tested on Levels 4-6 too, which matters because the generator will feed this planner many new
boards.

## 7. Plan

This step was planned for Oct 11 and was done on Oct 10, so Oct 11 goes to the **compositor and
the first finished 30 s ad** (the near-fail above). The generator becomes a command on Oct 12.
After that:
- Oct 13: CreativeDoc, the language planner and editing;
- Oct 14: image and video inputs;
- Oct 15: UI and QA;
- Oct 16: write-up;
- Oct 17: fresh-clone test and submit.

## 8. How to reproduce

The full guide is `~/rollic-case/SCENARIO-CHECK-STEPS.md`: 14 steps, each with the exact output
to expect. The short version:

```
cd ~/rollic-case/cbj-creative
uv run pytest -q
uv run cbj build-player
uv run cbj scenario data/levels/gen/narrow_center_01.json --ending near_fail -o renders/my_near_fail
open renders/my_near_fail/gameplay.mp4
uv run cbj rerun renders/my_near_fail -o renders/my_near_fail_again
```

## 9. Files

- **Code:**
  - `cbj-creative/src/cbj/play.py` (the planner);
  - `solver.py` (`solve_fast`);
  - `render.py` (push and hold, `rerun`);
  - `cli.py` (`scenario`, `rerun`, `render --dry-run`);
  - `unity/CreativeRunner/CreativeRunner.cs`.
- **Tests:** `tests/test_play.py` (93), and new tests in `test_solver.py`, `test_render.py` and
  `test_unity_render.py`; one real dry run in `tests/data/`.
- **Commits:**
  - `5c9e4fa`: scenario scripts;
  - `06fa5f7`: first review fixes;
  - `4beea67`: stuck beat;
  - `aa9f5c3`: `--length` tie;
  - `8dd6f72`: second review fixes.
- **Videos and data:** `cbj-creative/renders/nc01_{win,near_fail,cliffhanger,time_out}/`.
- **Strips:** `cbj-creative/reports/scenario/`.
- **Earlier notes:** `SCENARIO-STATE-2026-10-10.md`, with Fable's original numbers.
