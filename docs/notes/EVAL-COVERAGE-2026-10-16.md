# Evaluation coverage check against the brief and the game's rules (2026-10-16)

Done before the scenario rerun, as asked: every point the brief highlights is mapped to the row that measures it in
the tool's evaluation, with where the fact is read from. "Measured" means read from the game's own record (the
level file, the recorder's result.json and play.json, the ad's compose.json and parts.json, the poster pixels),
never from the plan. The viewer's review (a vision model on a one-frame-per-second sheet) judges the soft side only.

## The brief's controls (p.3, "prompts may contain instructions about")

| control | rows (status from) | added today |
|---|---|---|
| the type or structure of the level | Asked: board shape, packed/spacious/symmetric board, block count, colours, named colours, blocks a viewer can count; **walls**, **blocks per colour**; Difficulty, Block shapes, Board looks, Moves | walls (count, "several separate" = 2+ groups), per-colour counts |
| gameplay behaviour | Asked: ending, mistakes, the blocked attempt, the blocking move (board offers it, played), order of interactions, satisfying finish, seconds left; **hesitations**; Planned moves, Ending, Mistakes, Order of interactions | hesitations counted from the play's beats |
| difficulty or pacing | Asked: difficulty, length, 30-60 s; **the clock** (a win's start value from the level file; other endings: info, the play sets it); Pacing curve | the clock |
| visual elements | **cursor** (ring, hand, none from the ad's layers), **background** (the poster's margin pixels, nearest named colour, colour family); Board looks | both |
| creative concept | each quoted caption on screen; **each caption on its moment** (at the start, on the wrong move, on the correction, when a colour leaves, on the result, in the last seconds, at the cut), read from the parts manifest | caption moments |
| sequence of events | **the win first, the replay, the end card, the result screen** from the ad's part order | all four |
| assets to use | **music** (a track in the ad's audio or none); pictures: the edit report's assets row on edits, the viewer on new creatives | music |
| elements that should remain unchanged | **the game's own look** (theme, block colours, board colour, HUD shown, no skin or object) when the prompt asks for the original rules, HUD or assets; on edits: the edit report (gameplay, timing, camera, composition, sequence, visual structure, assets, captions, sound) and the pixel box | the game's own look |

## The requested gameplay (p.5)

| the brief's example | row |
|---|---|
| a specific type of level | Asked: board shape, walls, packed/spacious/symmetric |
| a visually interesting board | **a visually interesting board (the brief)**: size, blocks, colours, piece kinds, walls, doors (info row, for the reader and the viewer) |
| a difficult or easy level | Difficulty (a solver rating: minimum drags, repositioning, blocks that can leave at once, a casual player's ratio) |
| a particular gameplay progression | Order of interactions, the blocking move, the blocked attempt |
| a near-fail moment | Ending (00:0N on the clock at the last exit), seconds left |
| a satisfying solve | Satisfying finish (a key move, then the last blocks leaving in a row) |
| a specific sequence of interactions | Order of interactions (first, next, last; stuck; blocks; hesitate) |

## Gameplay at the centre (p.2) and 30-60 s

- **gameplay at the centre (the brief)**: the share of the ad that is play, replay or the result clip; fails under 40 %
  and tells the planner what to shorten. Added today.
- 30-60 s (the brief): the finished ad's length. Existed.

## Gameplay consistency (p.11): "does CBJ behave like a game, not an unconstrained animation"

The rules rows replay the recorder's own log of every drag through the Python port of the game's C# (rules.py,
re-read in the Unity scripts on 2026-10-15; 11 tests in tests/test_rules.py plus the solver's):

| rule in the game | what the row checks |
|---|---|
| InputHandler drags one block at a time | one block per drag |
| BlockMovementService.IsPositionValid: every cell in bounds, active, free | the pivot moves through neighbouring free active cells only; no jump, no wall, no overlap |
| ExitService.CanBlockExit: the first door in file order of the block's colour that the block overlaps, a clear straight lane to the edge for every part, checked only while dragging | each exit is through that door with a clear lane, during the drag; a block that left where no exit is allowed fails |
| GameManager: the clock counts down from timerCount, 0 = fail, the win is every block gone | the clock never rises or goes below zero; the reported result matches the blocks gone |
| the level itself | valid board: blocks on active cells, no overlaps, every block has a door of its colour |

Nothing in today's additions touches the rules or the engine; the new rows read more of what the engine already records.

## One evaluation per workflow (the user's point of 2026-10-16)

- creative generation (text, image, video): the board, the play, the rules, every fact the prompt asks for, the
  case's rows; the loop feeds the measured misses and the viewer's first fix back and makes a new take when the
  board, the play or the length missed.
- controlled editing: the edit report (what changed, what was kept, the pixel box), the facts the edit asks for;
  the rules are re-checked only when the play was re-filmed; the loop feeds back items changed without being asked
  and the asked facts that are not so.
- the two are separate modules (src/cbj/workflows/create.py, edit.py) and separate sides of the UI.

## Still judged by the viewer only (not measured)

Pictures and stickers asked on a new creative (which file, where); the captions' wording beyond the quoted text;
how the moves read to a person (a one-cell move on a crowded board can be hard to see). A phrasing the regexes do
not recognise produces no row: the "facts read" are listed in each version's checks so this is visible.
