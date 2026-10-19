# Color Block Jam: 7 hard test prompts for core requirements 1 and 2, four endings (2026-10-16)

Seven hard test prompts for **Req 1, Text-to-Creative** and **Req 2, Level & gameplay generation** (case PDF pages 3-5).
Each case has a prompt to type into the tool as written, the ending it must reach, and the checks that decide pass or fail.

**Hard** means two things here. The gameplay is a hard level, and the prompt stacks several constraints the tool has to
meet together (exact clock, exact order, a frozen board with exactly one answer, a shape plus a difficulty).

Every case uses only what the provided Unity game can actually do (checked in `~/Downloads/CBJ/Assets/Scripts` and
the six shipped levels). The game has no keys, ice, bombs, boosters, rotating blocks, moving walls or colour-changing
gates, so no prompt asks for them. Board size is 1-12 by 1-12 (the level editor's limit), and blocks come in the
game's seven colours: red, blue, yellow, green, dark green, orange and purple.

## The four endings, spread over seven prompts

| Ending | What the game shows at the end | Prompts |
|---|---|---|
| **Clean win** | every block has left, the win screen shows, and the clock stops well above zero | H-01, H-02 |
| **Near-fail win** | the last block leaves with 00:01-00:03 on the clock, then the win screen | H-03, H-04 |
| **Time-out fail** | the clock hits 00:00 with one block still on the board, then the fail screen | H-05 |
| **Unresolved (cliffhanger)** | the video stops with blocks left and the clock still running; no win or fail screen | H-06, H-07 |

## What "hard" means for a generated board (HB1-HB3)

Every generated board (all prompts except H-04, which uses the shipped Level 6) must meet all three:

- **HB1.** At least 7 blocks at the start (more where the prompt says so).
- **HB2.** At least half of the playable cells are filled at the start.
- **HB3.** The solver finds no way to clear the board with fewer than 2 setup moves (a drag that moves a block without
  it leaving). So a player who only ever takes a block that can leave right now gets stuck.

## Checks that apply to every prompt (G1-G7)

These come straight from the game code. A creative that breaks any of them fails, whatever the prompt said.

- **G1 Legal movement.** Blocks move only over playable, empty cells. They never overlap, never pass through another
  block or a hole, never rotate, and never change shape or colour. No block jumps between frames.
  *(BlockMovementService.IsPositionValid)*
- **G2 Legal exits.** A block leaves only while it is being dragged, at the moment it steps onto a gate of its own colour.
  Each of its cells must line up with the gate's span, and the straight line from each cell to the board edge on that
  side must have no other block in it (holes don't block). A block that is dropped on its gate, or that starts on
  it, does not leave until it is dragged off and back on. A block wider than the gate can never use it.
  *(InputHandler.DragBlock, ExitService.CanBlockExit / IsPathClear)*
- **G3 Clock.** The clock shows its start value until the first touch, then counts down one second per second of
  gameplay with no jumps. Below 0:50 it pulses red every second; that is the game's own behaviour, not a defect. It
  stops when the board is cleared. *(GameManager.StartTimer / HandleTimer, UIManager.UpdateTimer)*
- **G4 End screens.** The win screen appears only after the last block's exit slide has finished, and the fail screen
  only at 00:00. The two never appear together. The clock keeps running during exit slides, so if it reaches 00:00
  mid-slide the game shows both screens; that counts as a fail of the test.
  *(GameManager.OnBlockExited / HandleTimer)*
- **G5 HUD.** The level number, coins, timer and restart button look as they do in the game. A level must not show
  level "-1", which the game prints for a level that wasn't loaded by number. *(LevelManager, GameManager.GenerateBoard)*
- **G6 Format.** The video is 1080x1920 portrait, and its length is the requested length within ±1 s, always inside
  30-60 s.
- **G7 Plain-language plan.** Whatever the tool chose or reinterpreted (clock start, board size, block count, length)
  is stated in plain words with the result.

---

## Clean win (2 prompts)

### H-01. A hard heart for Valentine's Day
**Covers:** Req 1 (level structure, visual elements, creative concept, assets to use, difficulty) and Req 2 (visually interesting board, difficult level, satisfying solve).
**Ending:** clean win.

**Prompt**
> Valentine's Day ad, 45 seconds. Make the board itself heart-shaped and pack it tight: at least eight blocks, only
> red and purple, with red and purple gates around the heart's edge. It should be a hard puzzle where the player has
> to slide blocks out of the way before anything can leave, but the player never makes a wrong move. Open with the
> caption "Clear the heart" and end on the win screen.

**Pass checks**
1. The heart is cut from the board with holes (removed cells) on a grid no bigger than 12x12. It is mirror-symmetric
   left to right, and recognisable as a heart in the first frame without the caption: a person or VLM shown the
   frame names the shape.
2. The board has at least 8 blocks and meets HB2 and HB3. Every block and every gate is red or purple, and each
   colour has at least one gate.
3. Every gate sits on an outer side of a playable cell (the board edge or the rim of a hole, such as the notch at the
   top of the heart), never between two playable cells.
4. Every exit follows G2. This matters for gates on the heart's inner rims, because their line to the edge crosses the
   holes and must have no block in it.
5. No wrong moves: the drags played equal the solver's shortest solution, including its setup moves.
6. "Clear the heart" shows at the start. The clock starts at 1:00 or more, so it never turns red. The win screen
   comes at the end, and the length is 45 s ±1.

**Fails if:** the shape isn't read as a heart without the caption, any other colour appears, the board can be
cleared with fewer than 2 setup moves, extra drags are played, a gate sits between two playable cells, or anything
breaks G1-G7.

---

### H-02. Think slow, finish fast
**Covers:** Req 1 (difficulty and pacing, gameplay behaviour, sequence of events) and Req 2 (particular gameplay progression, difficult level, satisfying solve).
**Ending:** clean win.

**Prompt**
> 50-second ad with a "think slow, finish fast" rhythm on a hard board with eight blocks. In the first part the player
> plans: exactly three blocks are slid aside to make room (they don't leave yet), with a short pause before each move.
> Then it all flows: all eight blocks leave one after another with no more setup moves, faster and faster, until the
> board is clear. End on the win screen.

**Pass checks**
1. There are 8 blocks and HB2 holds. The setup is real: the solver confirms the board can't be cleared with fewer than
   2 setup moves (HB3), and the 3 played setup moves are enough for the cascade that follows.
2. The drags are exactly 3 setup moves (each block moves and stays on the board) followed by 8 drags that each end in
   an exit, with nothing else in between.
3. The slow part has a pause of at least 1 s before each setup move.
4. In the fast part, each exit starts no more than about 2 s after the previous one, and the gaps never grow toward
   the end.
5. The win screen appears, the clock never jumps, and the length is 50 s ±1.

**Fails if:** the board can be cleared without setup moves, the number of setup moves isn't 3, any exit drag needs a
correction, the gaps grow, or anything breaks G1-G7.

---

## Near-fail win (2 prompts)

### H-03. Narrow centre, almost fails (the case PDF's own prompt)
**Covers:** Req 1 (level structure, difficulty, sequence of events) and Req 2 (difficult level, specific level type, near-fail moment).
**Ending:** near-fail win.

**Prompt** (word for word from the case PDF, page 4)
> Create a difficult Color Block Jam level with a narrow center section and show gameplay where the player almost
> fails before solving it.

The prompt gives no length, clock or block count. The tool must choose them inside 30-60 s and say what it chose (G7).

**Pass checks**
1. **"Difficult":** the board meets HB1-HB3.
2. **"Narrow center section":** holes pinch the middle rows down to a passage 1-2 cells wide, visible in the first
   frame. At least two blocks go through that passage in the solve, and every block that does fits its width.
3. **"Almost fails":** the clock really runs down. The last block's exit slide finishes with 00:01-00:03 left, the
   clock stays frozen at that value under the win screen, and the red pulse is visible for the last stretch.
4. The plan leaves time for the final slide. No fail screen appears at any point, so this G4 failure mode doesn't occur.
5. The clock never jumps: no cut skips gameplay time while the clock is on screen.
6. If the tool adds a struggle moment (a blocked attempt or a wasted move), it is a legal move and the tool names it in the plan.

**Fails if:** the passage is wider than 2 cells or not in the middle, fewer than two blocks use it, the board fails
HB1-HB3, the win comes with more than 3 s left, the fail screen shows, or anything breaks G1-G7.

---

### H-04. Shipped Level 6, board unchanged, clock cut to 0:30
**Covers:** Req 1 (elements that remain unchanged, assets to use, sequence of events, pacing) and Req 2 (specific sequence of interactions, near-fail moment).
**Ending:** near-fail win.

This prompt uses the hardest of the six shipped levels (8 blocks, 6 gates, minimum 8 drags) instead of a generated
board. It is hard because the tool has to keep the board exact, change only the clock, play a fixed order and land
the finish on a fixed second.

**Prompt**
> Take the game's Level 6 and keep the board exactly as it is: same blocks, same colours, same gates. Change only the
> clock: start it at 0:30 instead of 5:00. First the player tries the green bar and it bumps into the blue bar on the
> right, so they let go. Then they clear the level in this order: purple out the top-left gate, red out the top-right
> gate, the blue L-shaped block, the yellow L-shaped block, the short yellow bar, dark green, the short blue bar, and
> green last, leaving with one second on the clock. 40 seconds, ending on the win screen.

**Pass checks**
1. The first frame matches `Assets/Levels/Level_06.json` exactly: a 6x6 board with no holes, the same 8 blocks with the
   same cells and colours, and the same 6 gates (colour, side and span). The only change is the clock start.
2. The HUD shows level **6** (not -1) and **00:30** before the first touch.
3. The bump is legal. The green bar is picked up and pushed right, but it cannot move right because the blue bar fills
   the cell next to it (up and down are blocked too; only left is open, and the push must not go there). It is released
   on its own cells and does not leave. This first touch starts the clock.
4. The blocks then leave in exactly this order: purple (top-left gate), red (top-right gate), blue L, yellow L, yellow
   bar, dark green, blue bar, green. That is 8 exits and no other drags. This order is legal: `cbj check` on 2026-10-16
   replayed it as "8 drags, all legal, board cleared", which equals the level's minimum.
5. Green's exit slide finishes with **00:01** on the clock, and the clock freezes there under the win screen. No fail
   screen appears, and the red pulse runs the whole time (the clock starts under 0:50; see G3).
6. The length is 40 s ±1.

**Fails if:** any block, gate or colour differs from the shipped level, the HUD shows -1 or a clock other than 00:30,
the green bar moves or leaves during the bump, the order differs, the finish isn't at 00:01, the fail screen shows, or
anything breaks G1-G7.

---

## Time-out fail (1 prompt)

### H-05. "So close!", one cell short
**Covers:** Req 1 (creative concept, sequence of events, gameplay behaviour, difficulty) and Req 2 (particular gameplay progression, specific sequence of interactions, difficult level).
**Ending:** time-out fail.

**Prompt**
> Make a 45-second "so close!" ad on a hard, crowded board with eight blocks and 35 seconds on the clock. The player
> plays well at first, but late in the level drags a block the wrong way into a dead end and has to bring it back.
> The clock hits zero with only the last block left, one cell from its gate. Show the game's fail screen, then an
> end card that says "Can you beat it?".

**Pass checks**
1. The board has 8 blocks and meets HB2 and HB3. The clock starts at 00:35 and pulses red the whole time (it starts
   under 0:50; see G3).
2. The fail is fair: the solver's shortest solution, played at the ad's own average time per drag, finishes before
   00:00. The fail must come from the mistake shown, not from a board that can't be won in time.
3. The wrong-way move comes in the second half of play and is legal. The block slides into a pocket closed off by the
   board edge, holes or other blocks, then comes back out, without passing through anything.
4. At 00:00 exactly one block is left. It rests one cell from a gate of its own colour, so one more cell of dragging
   would have let it out under G2. It is not partway through an exit slide.
5. The fail screen appears at 00:00, nothing moves after 00:00, and the win screen never appears.
6. The "Can you beat it?" end card comes after the fail screen, and the length is 45 s ±1.

**Fails if:** more than one block is left at 00:00, the last block is further than one cell from its gate, the
shortest solution wouldn't fit in 35 s at the ad's pace, the wrong-way move happens early or isn't brought back, the
win screen appears, or anything breaks G1-G7.

---

## Unresolved cliffhanger (2 prompts)

### H-06. "Which block goes first?"
**Covers:** Req 1 (creative concept, visual elements, sequence of events, difficulty) and Req 2 (difficult level, specific sequence of interactions).
**Ending:** unresolved.

**Prompt**
> Make a 40-second "test your brain" ad on a hard, crowded board with at least nine blocks. Play the first moves,
> including at least one block slid aside, until only three blocks are left. Then freeze the board, put big A, B and
> C labels on those three blocks, and ask "Which block goes first?". Only one of the three should be able to get out
> right now. Don't show the answer; end on the question.

**Pass checks**
1. The board starts with at least 9 blocks and meets HB2 and HB3.
2. Before the freeze, the play includes at least one setup move, and every drag is legal.
3. The video ends with exactly 3 blocks left, no win or fail screen, and time still on the clock in the last frame.
4. The freeze happens on a settled board. No block is lifted, mid-drag or mid-exit in any frozen frame.
5. The question has exactly one answer. From the frozen board, the solver finds that exactly one labelled block can
   leave in a single drag and the other two can't. The board is still solvable from there.
6. The A, B and C labels sit on the right blocks, are readable, and don't cover any gate. No block moves after the
   question appears. The length is 40 s ±1.

**Fails if:** the start has fewer than 9 blocks, no setup move is played, more or fewer than 3 blocks are left, zero
or two-plus labelled blocks can leave in one drag, the frozen board can't be solved, any end screen shows, or anything
breaks G1-G7.

---

### H-07. "How do you free the big one?"
**Covers:** Req 1 (level structure, creative concept, visual elements, sequence of events) and Req 2 (specific level type, difficult level, specific sequence of interactions).
**Ending:** unresolved.

**Prompt**
> Make a 40-second ad on a hard board built around one big block, the biggest on the board, boxed in by holes and
> other blocks, with its gate on the far side. Play the level fast and clean until only the big block and two others
> are left, with the big block still stuck. Freeze there with the caption "How do you free the big one?" and end
> without showing the answer.

**Pass checks**
1. The board meets HB1-HB3. The big block has at least 5 cells, is clearly the largest block, and fits the span of a
   gate of its own colour (otherwise it could never leave).
2. In the first frame, the big block sits in a pocket closed off by holes and other blocks, and its gate is on the
   other side of the board from it.
3. Play is fast and clean: the drags before the freeze are a prefix of a shortest solution, with no wasted moves.
4. The video ends with exactly 3 blocks left (the big block plus two others), no win or fail screen, and time still on
   the clock. The freeze is on a settled board.
5. The big block really is stuck: from the frozen board it can't leave in a single drag, at least one other block has
   to move or leave first, and the solver still finds a solution.
6. The caption reads "How do you free the big one?". No block moves after it appears, and the length is 40 s ±1.

**Fails if:** the big block isn't the largest or has fewer than 5 cells, it can leave in one drag from the frozen
board, the frozen board can't be solved, wasted moves are played before the freeze, any end screen shows, or anything
breaks G1-G7.

---

## Coverage against the case PDF

| | H-01 | H-02 | H-03 | H-04 | H-05 | H-06 | H-07 |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| **Req 1:** type / structure of the level | ✓ | | ✓ | | | | ✓ |
| **Req 1:** gameplay behaviour | | ✓ | | ✓ | ✓ | | |
| **Req 1:** difficulty or pacing | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Req 1:** visual elements | ✓ | | | | | ✓ | ✓ |
| **Req 1:** creative concept | ✓ | | | | ✓ | ✓ | ✓ |
| **Req 1:** sequence of events | | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Req 1:** assets to use | ✓ | | | ✓ | | | |
| **Req 1:** elements that remain unchanged | | | | ✓ | | | |
| **Req 2:** specific type of level | ✓ | | ✓ | | | | ✓ |
| **Req 2:** visually interesting board | ✓ | | | | | | |
| **Req 2:** difficult level | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Req 2:** particular gameplay progression | | ✓ | | | ✓ | | |
| **Req 2:** near-fail moment | | | ✓ | ✓ | ✓ | | |
| **Req 2:** satisfying solve | ✓ | ✓ | | | | | |
| **Req 2:** specific sequence of interactions | | | | ✓ | ✓ | ✓ | ✓ |
| **Ending** | win | win | near-fail win | near-fail win | time-out fail | unresolved | unresolved |
