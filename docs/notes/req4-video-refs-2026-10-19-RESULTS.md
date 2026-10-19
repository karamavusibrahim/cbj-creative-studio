# Video-guided test set 3: the owner's three reference videos, seven hard asks (2026-10-19 afternoon)

Why: the owner's creative of 10:37 ("use same game design, same scenario just use fewer blocks" on Color Block Jam
Trailer 2) came back as a board of the trailer's TYPE, and he reported "two different blues through one gate, one colour
with no gate". Replaying that creative through the game's rules found one blue, every colour with a door and every exit
legal, so the report could not be reproduced on that file; what WAS found: the evaluation's "Rules: the level" row claimed
"every block has a door of its colour" without any check, and the video workflow never copied a board.

Runs: `run-r1.log` (V0-V6 on the first build of the afternoon), `run-r2.log` (V1 rerun), `run-r3.log` (V2 rerun),
`run-r4.log` (V3 rerun), `run-r5.log` (V6 rerun), `run-r6.log` (V1 second rerun), `run-r7.log` (V2 third), `run-r8.log` (V3 third), `run-r9.log` (V6 third), `run-r10.log` (V2 fourth), `run-r11.log` (V6 fourth), `run-r12.log` (V2 fifth, after the copy words were widened). Per case: `results/<id>.json`,
`creatives/<id>/` (every version's ad, board, level, brief, review sheet), `COMPARE.png` (the video's frame beside the
board played). The videos, frame by frame: `REFERENCE-VIDEOS-ANALYSIS.md`. The prompts: `PROMPTS.md`. The check
contract: `../IMAGE-GUIDED-EVAL-CHECKS-2026-10-19.md` (rows B', C1-C1d added today).

## 1. What changed in the system today (afternoon)

| change | where | why |
|---|---|---|
| the game's door and colour rules measured on EVERY workflow: every block colour has a door, every door a block, every block fits through a door of its colour; the shown colours at least 40 apart and no two slots with one name; doors used (info) | `level.door_problems`, `audit.door_rows`, `audit.colour_rows` | the owner's report; the old row's false claim |
| the video's own board copied cell by cell from its first frame of play when the words ask for THE board ("same game design", "this board", "exactly as shown") | `videocells.py`, `videoref._copy_board`, `guided.plan` | the type path was the root cause of "not the same design" |
| changes on a copied board: fewer or more blocks, half the blocks, easier; a copied board keeps every colour a door | `imagecells.remove_blocks`, `add_blocks`; `imageplan.BLOCKS_REL` | the owner's "fewer blocks" |
| the game's own footage shown in its measured colours (the live game's palette is not the build's) | `videoref._copy_board` + `imageplan.repaint` | V0 v1: the viewer called the build's colours "swapped" |
| colour mapping: hue counts outside a name's family, the family's first slot is preferred inside it; a new colour comes from a family the board does not show | `imageplan.colour_map`, `copy_spec` | V0: the violet went to dark green; V1: a bright green beside the lime green |
| the reader: a colour count cross-check and a split of one name over two hue clusters; bubbles, covers and counters are not blocks | `imagecells.verify`, `split_hues`, `NOT_BLOCK` | V3: yellow and orange both "orange"; V6: LolTap's bubbles read as blocks |
| a cliffhanger keeps an asked starting clock; a copied board's play is checked against the stated length at plan time; a time-out's one-block limit is said; "two blocks fewer" and "a mirror image" are changes, not a count or a symmetric-board ask | `brief.check`, `play.fit_clock`, `videoref.copied_board_pace`, `audit.asked` | V1 (01:05), V3 (45 s), V5 (two left), V1/V2 false misses |
| shared rows "blocks left at the cut", "the end card is a card, not padding", "a real choice at the cut" on every workflow | `audit.rows` | V5, V6 |
| a Turkish request translated once for the video path's parsers | `guided.plan` | V2 |

## 2. The table (final version of each case; the first-pass result where it differs)

| case | video | ask (short) | board | rows that matter | misses | viewer |
|---|---|---|---|---|---|---|
| V0 | Trailer 2 | the owner's prompt: same design, same scenario, fewer blocks | **copied** 5x7 + 2 hole cells, 9 -> 7 blocks (a magenta 2x1 and a purple 1x2 gone), the footage's teal/magenta/violet/lime on the blocks and doors | the board is the video's: pass; fewer blocks: pass; doors and colours: pass; colours tell apart: pass; likeness: partly (the hole drawn as a frame) | 0 | ship |
| V1 | Trailer 2 | same design + 2 fewer + 1 more colour, Level 25 and the clock kept, cliffhanger with "Can you see the move?", 30 s | first pass: **type** ("two blocks fewer" read as a count); rerun: **copied**, but the new row FAILED it: the added bright green beside the lime green, both named "green"; final (run-r6): **copied**, 9 -> 7 blocks, a YELLOW added with its own gate, the footage's colours, Level 25 and the 1:05 clock on screen (a cliffhanger now keeps an asked clock) | the board is the video's: pass; fewer blocks: pass; more colours: pass; colours tell apart: pass; the end card 3.5 s: pass | 0 | ship |
| V2 | Trailer 2 (Turkish) | the board exactly, mirrored L-R, one more block in the way, the game's look, time-out, 35 s | first pass: **type** ("add one more block" read as a count; "mirror image" as a symmetric-board ask); second (run-r3): **copied**, mirrored, +1 blocking block, time-out: the viewer's likeness "yes: the reference mirrored"; one miss: the footage colours painted although "the game's own look" was asked (fixed); third (run-r7): the translation's "the time should run out" was not read as a time-out, the reference's cliffhanger filled it (words widened); fourth (run-r10): **type** again: this time the translation came out as "Take the board from this video exactly, but mirror it" (no "as it is"), which the copy words did not cover (`videocells.BOARD_FROM`: a copy verb on THE board of THIS video is a copy now, tested); fifth (run-r12, final): **copied** 5x7, mirrored left to right, one more purple one-cell block in the way (13 -> 14 drags), the game's own colours and HUD, a time-out at 35 s; v2 after one revision round | the board is the video's: pass; mirrored: pass; one more block: pass; doors and colours: pass; colours tell apart: pass; the game's own look: pass; time-out: pass | 0 | ship |
| V3 | Trailer 3 | the board exactly with its colours, no HUD, two mistakes, near-fail, 45 s | **copied** 7x7, 16 blocks, 8 gates, all SEVEN colours distinct in the final run (the yellow plus was "orange" in the first two: hue split + a wider yellow band fixed it); the plan says at plan time that 22 drags need about 42 s of play and the 45 s ad will run about 51 s; it ran 48 s; the loop stopped after one revision ("a copied board cannot be shortened") | the board is the video's: pass; likeness: yes; colours tell apart: pass (7); length: FAILED and said | 1 | ship |
| V4 | Trailer 3 | half the blocks, its colours and framing, the clock shown, a clean win, 30 s | **copied**, 16 -> 8 blocks, every colour keeps a door, the clock shown | all pass; likeness partly (the same yellow/orange read) | 0 | ship |
| V5 | LolTap | the board exactly, bubbles if possible, quick cut to a play-now card, 30 s, time-out with two left | **copied** 6x6 from another game's frame (bubbles read as floor, said; one dark-green gate repaired); the time-out ends with ONE block (the engine's limit, now said in the plan and a row) | all pass; the viewer caught the one-vs-two (now a row) | 0 | fix |
| V6 | LolTap | same board mirrored T-B, one colour fewer, the game's look, cliffhanger with one move left and a question, 40 s | **type** three times, each for a different reading fault, each fixed: the bubbles read as "clear bubble" blocks (NOT_BLOCK); the whole-frame read called the wooden board no game (a video's frame is a game board now); the shade splits under the bubbles made eight colours (the reader's names stand past seven); fourth run (run-r11): **copied** 7x7, 12 blocks, 6 gates, the blue blocks and their gate became red (one colour fewer), mirrored top to bottom, the game's own colours, 40 s, a cliffhanger with one block left and "Which one goes first?" | the board is the video's: pass; mirrored: pass; one colour fewer: pass; doors and colours: pass (5 colours, every one with a door); colours tell apart: pass; likeness (viewer): no, because it counted the dropped bubbles and the colour mapping as differences (the question now tells the viewer both do not count); a real choice at the cut: FAILED (one block left: the prompt's own flaw, said) | 2 (both said) | ship |

## 3. What the evaluation caught today that it could not before
| defect | caught by | fixed in |
|---|---|---|
| "every block has a door of its colour" claimed, never checked | reading the code (the owner's report) | `door_rows` on every workflow |
| two slots named "green" beside each other (V1 rerun) | `Rules: colours tell apart` | the new colour from an unused family; the family's first slot preferred |
| the trailer's violet shown as dark green (V0, plan-only) | the plan's own colour list | hue in the mapping |
| yellow and orange read as one colour (V3, V4) | `looks like the video's frame (viewer)`: partly | colour-count cross-check + hue split |
| a 16-block board's play longer than the stated 45 s (V3) | `Asked: length` failed three times | `copied_board_pace` says it; the loop stops |
| "two blocks left" at a time-out played as one (V5) | the viewer only | the limit said in the plan; the shared row |
| a 40 s ad on a 10-block board: 11 s of frozen screen (V6) | the viewer only | the shared end-card row |
| LolTap's bubbles read as blocks (V6) | the cell reading's doubts (copy refused) | `NOT_BLOCK` + the prompt |

## 3b. Tally
Boards copied cell for cell from the video's frame in the final runs: V0, V1, V2 (run-r12, after run-r10 fell back to the type on a
translation variant), V3, V4, V5, V6 (seven of seven). Measured misses on the finals: V0 0, V1 0, V2 0
(r12), V3 1 (the length, said in the plan), V4 0, V5 0, V6 2 (the likeness verdict and the
one-block choice, both said).
Every miss that remained is one the plan states before the recording. Unit tests: 1458+ passing after every change
(`cbj-creative/logs/pytest-video-copy-*.log`).

## 4. Limits, stated
- The video's board is read from ONE frame (the first of play); a board that changes before the first drag, or a frame
  with the hand over it, reads worse (every case here read with 0 doubts).
- The live game's palette has colours the build lacks (teal, magenta, a violet, two blues): the copy maps each to a game
  slot and says it; the game's own footage is shown in its measured colours; two reference blues cannot both be blue.
- A copied board has the blocks it has: a long solution overruns a short stated length (V3) and a short one leaves an end
  card too long (V6); both are said, never silently fixed.
- A time-out ends with exactly one block, one cell from its gate (the engine's race).

- A translation is not stable word for word: the same Turkish request came back once with "exactly as it is" and once with
  "exactly, but" (V2, runs r7 and r10); every parser that reads the translation needs the plain forms too (`BOARD_FROM`).
- The likeness viewer judges a mirrored, recoloured copy of a board with foreign items (bubbles) poorly unless told what
  was dropped and how colours map; the question says so now (V6, run-r11).
