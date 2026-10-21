---
name: cbj-image-guided
description: Core requirement 3 of the CBJ brief in cbj-creative - how a prompt PLUS a reference image becomes a new creative in its own workflow (workflows/image_guided.py) - the image's role decided first (style, board, asset, modify), the whole-picture reading and the board read on a crop with code measures (symmetry by mirror mask, colour clusters, median size, fill), the prompt's values winning, "take what is named, fill only the board, only X means only X", the mapping of every read colour to the game's seven rendered block colours, counting the board and never the caption, clamping to what the generator builds and saying so, never copying pixels, cells or caption text, the image evaluation rows and the loop, and the measured reliability of the reading on four pictures with a hand truth. Use when planning, building, testing or judging any new creative made from an attached picture, when writing an image test prompt, and when deciding whether a result took too much or too little from its picture.
metadata:
  spec-version: "1"
  last-verified: "2026-10-19"
  game-version: "CBJ Unity 6000.3.5f1, six levels"
---

## 1. Purpose

The brief (p.6) says images may be used as visual references, assets to insert, style or composition references, or
inputs for modifying an existing creative ("Use this object instead of the current obstacle", "Create a CBJ
creative inspired by this image"), and that "the system should understand the role of the provided image and
incorporate it appropriately". This skill fixes how the image-guided workflow decides that role, what each role may take
from the picture, what it never takes, how the result is judged, and how reliable the reading is known to be. The full
rules (I1-I16, each tied to a PDF page and to a game file) are in `~/cbj-work/REQ3-IMAGE-GUIDED-RULES-2026-10-17.md`.

## 2. Source of truth

- The brief pages 2, 3, 5, 6, 7, 8, 10, 11, 12, 13 (quoted in the rules document, section 0).
- The game: `~/Downloads/CBJ/Assets` (`Scripts/LevelData.cs`, `Scripts/BlockData/BlockData.cs`, `Materials/BlockMaterials/*.mat`,
  `Materials/GroundMaterial.mat`, `Scripts/Services/Exit/ExitService.cs`, `Scripts/GameManager.cs`, `Scripts/UIManager.cs`),
  summarised with the consequences for a picture in the rules document, section 0b; [cbj-game-rules](../cbj-game-rules/SKILL.md).
- The generator's vocabulary: [cbj-level-gameplay](../cbj-level-gameplay/SKILL.md) (shapes, pieces, looks, size and block ranges).
- The code: `src/cbj/workflows/image_guided.py` (the workflow: `applies`, `plan`, `make`, `revise_once`, `pin_look`, `pin_level`, `with_facts`, `real_cut`, `fit_fill`, `keep_steps`, `asked_misses`,
  `feedback`, `best_version`; the loop's helpers are imported from `workflows/guided.py`, never copied),
  `src/cbj/imageread.py` (the reading: `GENERAL_ASK` and its schema `GENERAL_SCHEMA`, `still_clip` so that
  `reference.read_board` reads the picture as the still, `count_on_crop`, `margins`, `caption_colours`, `pair_colours`,
  `board_of_reading`, `caption_claims`, `hud_of`, `ClaudeImageReader`, `image_reader`, `reading_plan`, `PLAN_SCHEMA`,
  `general_ask`, `validate_general`, `read_one`, `read_multi`, `measure_named`, `apply_named`, `disagreements`, `read`), `src/cbj/imageplan.py` (the decisions: `is_image_reference`,
  `decide`, `reconcile`, `RENDERED`, `colour_map`, `repaint`, `board_shape`, `board_spec`, `style_kit`, `planner_view`, `card_view`,
  `apply`, `fit_board`, `size_from_fill`, `request_values`, `keep_quoted`, `fill_play`, `expected_play`, `name_stuck`,
  `dark_plate`, `honest_cascade`, `restore_repaint`, `palette_choice`, `review_facts`, `sequence_matches`,
  `cliffhanger_replay`, `cut_choice`, `cut_choice_planned`, `extra_beat`, `play_levers_left`), `src/cbj/imageaudit.py` (the image rows:
  `rows`, `board_rows`, `look_rows`, `screen_row`, `copied_row`, `counted_row`, `board_not_taken_row`, `blocks_left_row`,
  `fast_finish_row`, `quoted_row`, `play_fills_row`, `stuck_visible_row`, `question_row`, `real_choice_row`, `rejudge`, `made_level`, `RELIABLE`), `src/cbj/app.py` (`workflow_of`), `src/cbj/imageref.py` (`luminance`,
  `contrast`), `src/cbj/reference.py` (`read_board`, `measure_board`, `mirror_iou`, `cluster_colours`, `palette`,
  `video_client`), `src/cbj/videoref.py` (`stated`, `board_size`, `board_blocks`, `board_colours`, `fit_captions`,
  `mechanic_lines`).
- The test set and its truth: `~/cbj-work/req3-image-guided-2026-10-17/` (`TRUTH.md`, `PROMPTS.md`, `inputs/pic_w..pic_z.png`).

## 3. Facts

### 3.1 Input and dispatch
- A prompt plus at least one picture, no video. The words make the picture a reference ("inspired by", "like this",
  "this image / picture / screenshot / board", "take / use the ... of / from this", "the same ... as this") → this workflow.
- A picture only to place (logo, sticker, end card) with no reference words → the text workflow (create.py), unchanged.
- A picture with edit words on an existing creative → the edit workflow (edit.py), unchanged.
- A video, with or without a picture → the video-guided workflow (guided.py), unchanged.
- create.py, edit.py and guided.py are never edited for this workflow (md5 checked).

### 3.2 The role (decided first, shown on the card)
| role | the words | what it takes |
|---|---|---|
| style | look, style, palette, colours of/from, theme, mood, vibe, night/neon look, "inspired by" a non-board picture | the background pair, the caption fill + outline; the block colours ONLY when asked ("the blocks too", "on everything", "the same block colours") |
| board | a level / board like this, shaped like, the same number of blocks, as crowded as, the same grid, big blocks like these, "inspired by" a board screenshot | the level's type: shape, size, blocks, colours (slots), pieces, symmetric / packed look; each part only where the words state nothing |
| asset | put / place / use as the logo / sticker / end card / button / cursor | the picture in that slot (the text workflow's placement rules) |
| modify | instead of the obstacle, on the walls, as a block's texture | the picture on the walls or a block (the edit side's rules) |
Two roles at once are normal ("its dark neon look and a board split into rooms").

### 3.3 What is never taken
- No reference pixel in the gameplay or the frame outside an asset / modify slot; the board is generated, solved by the
  tool's own rules and filmed by Unity (p.8).
- No caption text from the picture unless the request quotes it or asks for "the same words".
- No ending, length, difficulty or tempo from a picture: those are the prompt's (or the defaults).
- No exact cell layout; no gate placement (the generator places gates where the block can reach).
- Nothing the game does not have: "<it>: not used: not in CBJ".

### 3.4 Colours
- The seven rendered block colours: Red #FF3B2A, Orange #FF8000, Yellow #FFCC04, Green #14FF17, DarkGreen #065C13,
  Blue #146AFF, Purple #D007FD (violet-magenta). The game's background is #ADD1E9, its cells #5E6A94.
- Each distinct block colour read on the board → the nearest free slot by distance to the rendered colours, shown as
  "pink -> purple: the game has no pink". At most seven.
- A repaint (display colours) keeps the picture's hue and is contrast-checked; only when the request asks for it.
- Captions: contrast at least 3:1 against the background they sit on.

### 3.5 The reading and the board
- The request first: the planner's text model writes the image reading plan from the words and the picture's format
  only (focus style / board / asset / modify, the questions, what to ignore, what the request fixes); the word table is
  the fallback. The plan's focus decides the roles applied; the words the parts inside each; never what is read.
- The reader is Opus through the Claude CLI (CBJ_IMAGE_READER, or the planner being Claude): the whole picture once,
  strict JSON, the plan's questions on top, one re-ask with the problems quoted; Gemini 3.5 Flash-Lite then NVIDIA
  build when Opus fails (they also read the board again with read_board and count it twice on its crop).
- Beside every reader, the code measures: the palette, the margins, the caption box, and on the board's crop the
  symmetry from the block mask against its mirrors, the fill, the colour clusters; a disagreement is written down and
  the measure wins.
- Counted on the board, never from a caption (pic_x's caption says 12, its board has 14).
- Map to the generator: hourglass → narrow_center; two rooms → door; more rooms split by walls → door or holes (said);
  separate wall cells → holes; plus → cross (a centre wall on a cross is not combined: said); ring → ring; columns → lanes;
  rectangle → open. Width 4-9, height 4-10, blocks 2-10 asked (12 packed): beyond is clamped and said.

### 3.6 What the 12-case run fixed (2026-10-17, F1-F13)
- The board not taken: the planner gets no board description (only the look and the mood), and the row "the board is
  not taken" fails when the level's plan cites the picture (a sentence saying it is not used is fine).
- Every block colour has a hex from the reader, confirmed on the board crop's pixels (each pixel counts for the nearest
  hex); a repaint shows every slot in its measured colour, even a colour named with a game word.
- The blocks: at most 10 (brief.check and generate_for_brief; MAX_BLOCKS 12 is never reached from a brief), fitted with
  the pieces (read approximately, so free unless the words state them) and a size the request leaves open (a cell a
  side), so a packed board is packed like the picture (fit_board, PACK_MARGIN); the blocks row judges against
  min(seen, 10), not against what was built, unless the plan says why it built fewer.
- A filled size the reads disagree on (spread over 2 cells) takes the read the block count and the fill agree with; a
  read size the count would fill far more or less than the picture is sized for the blocks (size_from_fill); a wide
  spread makes the size row info.
- The request's own values the planner may miss: the blocks left at a cliffhanger's cut, a "fast cascade" (fast tempo,
  streak finish), a quoted caption (never dropped by the shared caption fit: moved to the slot the ending shows), a
  "which one" question cutting with 2 blocks or more.
- The shared text audit's "almost runs out of time" (read as a time-out) and "the last three blocks" (read as a count) are
  judged here against the words (info, with the reason); the shared audit itself is the owner's.
- A revision never changes the level for a look miss, never changes the difficulty unless asked, and answers a packed
  miss with the board's levers (fit_board at PACK_MARGIN_RETRY), never an easier board.
- A shape named from the picture and stated by the words ("shaped like this one, a plus shape"; "split into rooms") is
  judged.

### 3.7 What round 2 fixed (2026-10-17, G1-G12)
- Gameplay at the centre: before the first take the play the tool expects (videoref.expected_play) is set against the
  stated length; under 60 %, a count the picture filled rises by 2 (twice at most, up to 10, the size a cell a side),
  a count the request names gets one more wrong move when the request allows it, and the limit is said. Never the
  difficulty. A thin take (the row "the play fills the ad", under 50 %) gets the same levers in the revision.
- The viewer is given what the picture gave as measured facts (written into the plan rows it reads), and a viewer point
  on a control whose image rows all pass starts no revision (its words are kept).
- A stuck moment points at one piece (a single-block mover, a blocker of another colour); its hold is measured (each
  wrong drag at least 0.8 s). The hold itself (play.MISTAKE_HOLD_F, 0.6 s) is the shared player's: not changed here.
- Plain words to the user: no file names, no constant names, no "brief"; "the tool builds at most 10 blocks in one level".
- A night background (luminance under 0.2) is drawn as a flat, tool-made plate behind the board (unlit), not on the
  game's lit ground, which lifts dark colours by about 25.
- A "fast cascade" is said as the game plays it (one drag frees one block; the finish at about 0.3 s between drags); no
  planned caption claims one move frees them all (the tool writes it only when a drag really frees three or more).
- The picture's block colours survive the shared colour check: a colour moved only for the background gets its measured
  shade back; two colours too close to tell their gates apart keep the smallest step that separates them, said.
- A palette word on the blocks says which colours it gives (the picture's own block colours, not the background's).
- A cliffhanger plays no slow-motion replay before its question unless the request asks for one (the replay showed the
  block the question asks about); the sequence's words and fields always agree; the row "the question follows the live
  cut" reads the parts.
- No planned caption promises pairs, chains or clears together (one drag frees one block); the planner is told so up
  front. A caption the request quotes stays.
- A cliffhanger's cut is a real choice: before the first take the take's own planned path is walked (studio's play
  planner with the wrong moves and hesitations; the bare solve as the fallback) and the cut moved to the latest
  position where a remaining block is trapped (1-3 blocks left); with none, two more blocks once on a filled count, else
  said. A count the request names stays. The row "the cliffhanger is a real choice" rebuilds the cut from the
  recording's drags; a miss raises the blocks left by one in the revision.
- Colours filled from the picture that the level uses fewer of are said ("6 colours allowed from the picture, the
  level uses 3 of them").
- A thin play at the block limit (or on a named count) gets one early wrong move or hesitation, whichever the tool
  expects to lengthen it (a streak finish keeps its fast run); the fast tempo's estimate is the table's times 0.75
  (measured on B2, rounds 2 and 4). With no lever left (the request forbids mistakes and hesitations, the count at the
  limit), "the play fills the ad" is info with the limit said, and no revision is started for it.
- The stuck row judges only the planned stuck drags (the play's own mistake beats), never an ordinary move aside.
- A packed board is measured on the level the take will use (generated before the take through studio's cached
  generator); under the bar, once more with the pieces a class bigger or one more block, if the planned steps still
  play. A count clamped below the picture's is judged against that measured fill (within 5 points), the clamp said.
- A revision lever that changes the level keeps the planned steps playable (studio's own cannot-play check): another
  board once, else the board before is kept. With equal misses, the version missing less of what the request asks wins.

### 3.8 What round 3 fixed (2026-10-18, H1-H16, the edited screens)
- The piece class the picture shows (small, long, big) is built first; only when the generated board cannot place the
  count with it is it one class smaller, said (checked on the level the take uses). A unanimous size read (three reads,
  no spread) stands; the fill measure then only picks the pieces.
- "The blocks too", "on everything", "blocks included" switch the block colours on (the picture's measured ones). A
  role-free "inspired by this image" takes them too. A block repaint the planner invents while the blocks are not
  taken is cleared (in the plan and in every revision), said; block colours the words name themselves stay and their
  row is info.
- A colour's named family wins over the RGB distance when a slot of that family is free ("light green" goes to green,
  never yellow); the shade still comes from the pixels; the row "the colours keep their family" flags a cross mapping
  (info, only when the family's slots are taken).
- The badge and the timer are read apart, clause by clause ("hide the level badge but keep the timer").
- Colours the request names itself are judged as the request's list (or info), never against the empty map.
- The words that describe the picture's own background in a sentence about the picture ("the arcade purple-to-pink glow
  for the background" of "this picture's board") turn the style role on for the background, measured. A background the
  words set themselves (not taken) is judged against the plan, "set by the words", not the game's own.
- "As crowded as this picture" on a board under the packed bar is the picture's fill as the target (the image row "as
  crowded as the picture", within 10 points; info at the 10-block limit); the shared "packed board" row is info with
  the numbers, and no revision runs for it.
- Before the take, the player's plan is dry-run on the generated level with the planned ending; when it cannot play
  (a time-out needs a last exit of at least two cells), three more seeds, then one more block, else the nearest ending
  that plays (a time-out or cliffhanger becomes a near-fail), said. Never an exception. A revision is checked the same.
- When the picture has no caption to measure and the captions take its look, its most saturated measured colour that
  reads on the background is the caption accent; white stays the fallback.
- A cliffhanger's play aims at about 70 % of the ad (no replay or result screen comes before its question).
- A shared row missed twice with the same detail ends the loop: the limit is said on the kept version (`limit_note`).
- The plan's words say the picture's numbers: a planner sentence naming another size or count is left out.
- A stated length beyond what one level of 10 blocks plays (over 45 s) is said in the plan; the fill row is info, and
  no revision runs for it.

### 3.9 What the round-3 rerun fixed (2026-10-18, H3b-H20)
- Every planned step plays on the board the take uses: studio's cannot-play check runs before the first take and
  before every revision's take; a step that cannot play gets three more seeds, then the stuck step is re-planned with
  this board's own colours (a single-block mover first), then dropped with its wrong move kept, said.
- The loop compares a shared row's verdict (the text after "->", or the "(asked: ...)" clause, digits dropped) and the
  10-block limit state: the same verdict twice ends it, with the limit said.
- A time-out's blocks left come from the words; the game's time-out ends with exactly one block one cell from its gate,
  so another count is said as the limit, and "blocks left at the cut" judges time-outs too (info on that limit).
- The length limit follows the predicted play: when the play expected at the best count this board reaches stays under
  50 % of the stated length, it is said, the fill row is info and no revision runs for it.
- Hues the words give the background that match the picture's measured background (within 40 degrees) take the
  background from the picture, measured, even when the reading plan did not focus on the look; said.
- Two of three agreeing size reads stand over a fill measured under 30 % on a themed render (top margin over 40 from
  the game's poster background).
- A cliffhanger whose predicted end card runs over 6 s holds its question longer (sequence.hold_s, at most 6 s), said;
  a hold the request states is kept.
- The reader names an accent colour (look.accent, with its box); measured on those pixels, it colours captions the
  picture has none of; white stays the fallback.
- A plate is a "night" background only for navy or black; otherwise "dark".

### 3.10 The prompt wins
A stated length, ending, difficulty, block count, colours, caption, look, HUD choice or tempo is never replaced by the
picture. "Keep the game's own ..." keeps it. "Only X" takes X alone. What the words leave open about the board is
filled from the picture and marked "filled from the image" (info rows, never misses).

**A colour count relative to the picture** (2026-10-19). "One more colour", "an extra colour", "two fewer colours", "more colours" (`imageplan.relative_colours`, `RELATIVE_COLOURS`) make the colours a stated part: the board gets the picture's mapped colours plus the asked count (the planner's own extra colour first, then the game's order) or minus it (never below two), listed in `took` with a clamp line "N colours in the picture (…) + 1 as asked: Blue". Before this, the +1 was lost: the picture's colours were filled in because the request "said nothing" about colours.


## 3b. The board IS the picture's (2026-10-19)
**Reading.** `imagecells.read_cells` runs after the type reading when the picture is a CBJ board (`imageread.with_cells`):
the grid's four corners (Opus), a perspective warp to a square grid with one cell of margin, a lettered overlay (columns
A.., rows 1.. from the top), one strict-JSON ask for every block (colour + cells), hole, empty cell, gate (board cells +
the way out) and thin wall line; code verifies every cell against the warped pixels (the floor is what the reader called
empty; a claimed block cell that looks like the floor, an empty cell that holds a block, a gate not on an edge, a block
count off the whole-picture read) and asks once more with the doubts quoted; more than `CELL_DOUBTS` (2) left refuses the
reading. The cells become the game's level JSON (viewer row 1 = the top = y rows-1), validated and solved (`SOLVE_STATES`
250k; a board the solver cannot settle is said, not guessed). Evidence: `studio/_cells/<stem>.json`, `_grid.png`, `_warp.png`.

**Plan.** `imageplan.copy_spec`: with the board role and a read level, unless the words ask for a new board (`NEW_BOARD`:
"a new/different/another board", "of this type", "a different arrangement") or state a conflicting part (a count, a size,
a shape of their own, colours the board lacks), the level is the picture's: `level.source "picture"`, `level.file` in
`studio/levels/picture_<hash>.json` (`studio.resolve_level` plays it; `brief.check` leaves its numbers alone). Transforms
from the words, in code, each solver-checked and said: `recolour` ("make the yellow blocks blue": blocks AND gates),
`colours` ("one more / fewer colour": `imagecells.add_colour` recolours one block of the commonest colour and adds a gate of
its own on the nearest edge the solver accepts, the planner's suggested colour first; `remove_colour` merges the rarest
colour, gates too), `mirror` (left-right or top-bottom), `harder` ("harder", "one more block in the way": `imagecells.add_blocker` places one one-cell
block of an existing colour where the solver's minimum drags rise; "easier" is said as not done). A board drawn unplayable (the pictures are renders) gets
`imagecells.repair`: the smallest added gate that makes it solvable, said as "the board as drawn could not be played;
repaired: ...". Thin wall lines become an inserted line of wall cells with the same gaps (`walls_note`). The planner is
told the board is copied (`planner_view`); a revision never changes a picture level (`revise_once`).

**Rows.** `imageaudit.copied_board_rows`: `Image: the board is the picture's` (cell-for-cell identity with the read board
after the transforms, plus the reading's doubts), `more or fewer colours than the picture`, `a colour became another`,
`the board mirrored`, `harder than the picture's board` (the solver's drags), `the level number`, `the board as drawn was repaired` (info), `thin walls as wall cells` (info); `likeness_row`: the
viewer model compares the picture and the first play frame side by side (`likeness_sheet.png`); `coverage_rows`: every
ask the parsers read has a row, else `Coverage: not measured` names it. The loop (`image_guided.feedback`,
`loop_verdict`) drops a viewer's point only when every ask is measured and that control's rows pass. The full contract:
`~/cbj-work/IMAGE-GUIDED-EVAL-CHECKS-2026-10-19.md`. Tests: `tests/test_imagecells.py`.

**Common to every workflow (2026-10-19).** The translation once, the rules rows and the shared case rows on every version,
the best version kept, the stated values kept, the length guard, the viewer-only rule, the repeated-miss limit, the fixed
board's pace said at plan time, the kept log lines, the feedback step and the report: listed once in `cbj-creative-evidence`
section 3 ("Common to every workflow") and in `src/cbj/workflows/__init__.py`.

## 4. Procedure

1. Read the request: the role words, the parts it names, what it fixes itself, "only" scopes.
2. Write the reading plan from the request, then read the picture (Opus, or the fallback chain) with the plan's
   questions on top and the code's measures beside; a failed read is said ("not read") and the creative is planned
   from the words alone.
3. Decide the role(s) from the words and the reading; write the plan line "the picture is used as ...: takes ...; not taken ...".
4. Plan the brief with the planner (the readings as notes), then apply in code exactly what the roles allow, with the
   colour mapping and every clamp written in the assumptions.
5. Make the creative with the shared engine (level generated and solved, Unity film, compositor), review it as a viewer.
6. Evaluate: the text profile + the image rows (section 6); feed the misses back; at most two revisions; keep the best.

## 5. Not possible here

- A thin wall line as the game draws none (it becomes a line of wall cells); a board the solver cannot settle in 250k positions copied as it is (its type is built instead, said); "harder/easier" on a copied board; a board with more than seven colours. (Until 2026-10-19 the board was never copied cell by cell; it is now, see 3b.)
- A picture's mechanic the game lacks (bubbles, ice, keys, boosters, characters on the board, opening doors).
- More than seven block colours, or two read colours in one slot told apart by shade alone.
- Drawing the picture's style onto the gameplay frames (no image or video model restyles the game).
- A centre wall inside a cross board, or more than two rooms, as an exact shape (the closest shape is built and said).

## 6. Evidence

- Per version: `version.json` → `workflow` "image_guided", `brief.planner.workflow` "image_guided",
  `brief.reference` (kind "image", `file`, `plan` (the reading plan: focus, level, questions, ignore, constraints,
  why, source, checks; the reference card shows it), `reader` (reader, model, seconds, fell_back), `disagreements`,
  `roles`, `why`, `named`, `filled`, `taken`, `not_taken`, `colour_map`,
  `clamps`, `look` (the kit: background, caption fill and outline, contrast), `board` (`seen`, `built`, `named`,
  `filled`, `kept`, `fit`), `not_copied`, `not_used`, `mechanics`, `set`, `reading` (the compact reading)),
  `brief.planner.references[0]` (the card's view: kind "image", palette, notes, role), `checks` (the image rows,
  `from` "reference"), `evaluation.groups` with "image", `review`; the made `level.json`, `ad/poster.png`, `ad/ad.mp4`
  (the hook's frame), `parts.json` (the hook's box) and the recording's `job.json` (its hidden HUD parts) are what the
  rows measure.
- Image rows (`imageaudit.rows`, all "Image: ..."): `the role` and `what was taken` (info); `the board's shape`, `the
  board's size`, `the board's blocks`, `the board's colours` (the request's own list when it names the colours), `mirror-symmetric`,
  `packed` or `as crowded as the picture` (a relative crowdedness), `the pieces`, `the colours keep their family` (info on a
  cross mapping) (when the
  board is taken; a filled part is info; a part not in `RELIABLE` is info), `what the tool cannot build` (info, the
  clamp lines); `the background`, `the caption colours`, `the block colours` (when taken), `not taken stays the
  game's own` (the background and captions by their own fields, not the theme flag); `the board is not taken` (when the
  picture has a board the request does not take); `blocks left at the cut` (a cliffhanger whose words state N, on the
  recording's blocks that never left); `the fast finish` (a "fast cascade": the plan and the last third's pauses, at most
  0.5 s, with the game's limit said); `the quoted captions` (each quoted caption drawn, on parts.json); `the play fills
  the ad` (the live play over the ad's length, at least 50 % when the board is the picture's; info with the stated limit
  on a named count); `the stuck moment is visible` (each wrong drag at least 0.8 s, when the request asks for a stuck
  moment); `the question follows the live cut` (a cliffhanger: no replay part between the play and the question;
  info when a replay is asked); `the cliffhanger is a real choice` (a remaining block blocked at the cut, rebuilt from
  the level and the recording's drags; info when the request names the blocks left); `blocks left at the cut`
  also for a time-out (info when the words ask another count than the game's one); `the screen`; `nothing copied`; `counted on the board` (when a caption claims a block
  count). The shared rows "Asked: ending" and "Asked: block count" are
  re-judged against the words (`imageaudit.rejudge`) when the shared reading misreads them, and "Asked: packed board"
  is info with the numbers when the crowdedness is the picture's ("as crowded as this picture").
- Pre-take notes in the log: `level:` (the pieces check, the playable-ending dry run), `fill:`, `cut:`; a stopped loop
  writes `limit_note` on the versions it compared.
- The reading's accuracy on the four test pictures: `~/cbj-work/req3-image-guided-2026-10-17/READING-ACCURACY.md`.
- The end-to-end set and the findings: `~/cbj-work/req3-image-guided-2026-10-17/REPORT.md`.

## 7. Change rules

Any change to a role word list, a colour slot value, the board map, a clamp or an image row changes sections 3 and 6 in
the same edit and bumps `last-verified`. A change that needs create.py, edit.py or guided.py is not made here: it is
proposed to the owner first. Rules I1-I16 in the rules document win over this skill if they ever differ.
