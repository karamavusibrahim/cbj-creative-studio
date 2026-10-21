# What an image-guided creative is checked on, and how (2026-10-19)

Written after re-reading the brief (14 pages), the Unity project
(`~/Downloads/CBJ/Assets`: `Scripts/*`, `Levels/Level_01..06.json`, `Materials/{Block,Exit}Materials/*.mat`,
`Sprites/UI/*`) and the competitor-ad research (`COMPETITOR-ADS-2026-10-10.md`). It is general: it does not depend on
any test prompt. It is the contract the evaluation code (`audit.py`, `imageaudit.py`, `review.py`, the loop in
`workflows/image_guided.py`) must meet, and the report of each test run states, row by row, that it did.

## 0. Why this document exists

The owner's creative of 2026-10-19 06:49 ("create a similar game concept, just use one more color", on an underwater
reef screenshot) came out with the picture's three colours and a different board. Its record shows the failure of the
evaluation, not only of the generation:
- every measured "Image:" row passed or was "info (filled from the image)": the rows measure the board's TYPE (a ring,
  8x8, 9 blocks, 3 colours), so a different ring with the same numbers passes;
- "Asked: facts read from the prompt: none the audit measures": the one thing the request asked ("one more colour")
  had no row, and that absence was reported as info, not as a gap;
- the viewer's review saw it ("no blue (or any fourth colour) appears anywhere") and still said "ship", because the
  overall verdict turns to "fix" only on a "no", not on a "partial";
- the loop drops a viewer's point when the control's measured rows all pass, so the one correct signal was discarded.

If the evaluation cannot see a miss, the loop cannot correct it. Hence: define what is checked, make every item
measured, and never let an unmeasured ask pass silently.

## 1. Where the checks come from

| source | what it fixes |
|---|---|
| brief p.2 | 30-60 s; CBJ gameplay at the centre; different creative concepts |
| brief p.3 (prompt controls) | the level's type or structure; gameplay behaviour; difficulty or pacing; visual elements; creative concept; sequence of events; assets to use; elements that remain unchanged |
| brief p.5 (requested gameplay) | a specific type of level; a visually interesting board; difficult or easy; a progression; a near-fail; a satisfying solve; a specific sequence of interactions |
| brief p.6 (image roles) | visual reference; asset to insert; style or composition reference; input for modifying a creative; "the system should understand the role of the provided image and incorporate it appropriately" |
| brief p.7 (preserve) | gameplay, timing, camera, composition, sequence, visual structure, other assets stay unless asked |
| brief p.11 (criteria) | creative quality (coherent, engaging, usable); controllability; gameplay consistency ("behave like a game"); multimodal understanding ("meaningfully use ... image inputs") |
| the game (`cbj-game-rules`) | 7 block colours and their gates (`BlockMaterials`, `ExitMaterials`); polyomino blocks on a grid up to 12x12; holes (`inactiveCells`) are the only obstacle; one gate per cell side; the exit rule; the clock; "Level n" badge and "Time" bar (`MainBarCircle`, `TimerBackground`, `stopwatch`); the win and fail screens (`LevelCompleted.png`, `OutOfTimeText.png`); no sound, no boosters, no characters in play |
| the ads (competitor research) | the hook in 0-3 s; a readable caption at a time; the ending beat (win / near-fail / fail / cliffhanger) in the last seconds before the end card; a CTA on the end card; the real timer and the real result screen |

## 2. The check list

Legend for `status`: **pass** / **failed** (measured against a bar), **info** (measured, nothing to judge: the request did
not ask it and the picture filled it in), **not measured** (the tool knows the request asked it and has no measure:
reported as a gap, never silent). `where` names the stage that missed (plan / level / play / ad). A row marked *loop*
feeds the revision when it fails.

### A. The request's own asks (every control of brief p.3), measured on the made files, never on the plan's prose
| # | check | measured on | bar | loop |
|---|---|---|---|---|
| A1 | length | `parts.json` duration | within 0.5 s of a stated length; 30-60 s always | yes |
| A2 | ending | recording `result.json` (win / fail frame, clock) | the stated ending played; near-fail = last exit with 1-3 s showing; time-out = clock 0 with blocks left; cliffhanger = cut with the stated blocks left | yes |
| A3 | mistakes, hesitations, order of interactions, the block in the way | the play script + the recording's drags | the stated count and order, the named blocker | yes |
| A4 | difficulty | the solver's rating of `level.json` | the stated band (easy / medium / hard) | yes |
| A5 | board shape, size, block count, colours, named colours, walls | `level.json` | the stated values (size within 1, count within 2, every named colour present) | yes |
| A6 | **relative colour count** ("one more / two fewer colours than the picture") | `level.json` distinct colours vs the picture's | exactly picture + n (clamped to 2..7, said) | yes |
| A7 | **a named recolour** ("make the yellow blocks blue") | `level.json` blocks and gates | no block or gate of the old colour; the new one present | yes |
| A8 | **a transform of the board** ("mirrored left to right") | `level.json` vs the transformed picture board | identical | yes |
| A8b | **harder / easier than the picture's board** ("harder: one more block in the way") | the solver's minimum drags of the made level vs the picture's | harder: more drags with one added one-cell block of an existing colour; easier: not made here, said as a failed row | yes |
| A9 | captions quoted or asked ("the same words", a caption text) | `parts.json` layers | the quoted text on screen, at the asked moment | yes |
| A10 | HUD: badge and timer shown or hidden; the same level number / clock (`Image: the level number` when the picture's number is asked) | the play frame (pixels) + the job's label | as asked; the number equals the picture's when asked | yes |
| A11 | looks the request names (a background colour, caption colours, a cursor, music, a picture to place) | the poster / frames / `compose.json` | the named value within the shared colour distance | yes |
| A12 | tempo and pacing words | the play's drags per second, the parts' lengths | calm < 0.25 drags/s, fast > 0.6 | yes |
| A13 | **coverage**: every phrase of the request the tool parsed as an ask has one of the rows above | the set of asks vs the rows | a missing row is a `not measured` row naming the phrase | report |

### B. What the picture gave (brief p.6), only when its role took it
| # | check | measured on | bar | loop |
|---|---|---|---|---|
| B1 | the role | the decision + the reading plan | info: the roles, why, which reader, the seconds | no |
| B2 | **the board is the picture's** (board role, copied; with `the board as drawn was repaired` and `thin walls as wall cells` as info rows when the picture needed them, and the solver's limit said when it could not settle the board) | `level.json` vs the board read cell by cell (`studio/_cells/<picture>.json`) | identical cells, colours and gates after the asked transforms; the read itself verified on the pixels (every claimed block cell block-coloured, every empty cell floor) with the count of disagreements | yes |
| B3 | the board's type (board role, generated: "a new board like this") | `level.json` | shape class, size within 1, count within 2 (or the said clamp), each read colour present, symmetric when the picture is, packed when the picture is (fill >= 58 %), piece class | yes |
| B4 | the background (style role) | the poster's margins | within the shared distance of the picture's measured margins (dark ones drawn as a plate) | yes |
| B5 | the caption colours (style role) | the caption box in a frame | the measured fill and outline present; contrast >= 3:1 on the background | yes |
| B6 | the block colours (style role, "the blocks too") | the play frame's block pixels | the picture's measured shades, mapped to free game slots, families kept | yes |
| B7 | not taken stays the game's own | the poster's margins, the blocks' pixels | the game's own background `#E4F0FE` and block colours when the look was not asked | yes |
| B8 | the screen | the play frame | HUD as in the picture only when its screen was asked | yes |
| B9 | nothing copied | `ad.json` layers, the captions | no pixel of the picture outside an asset slot; no caption of the picture unless quoted | yes |
| B10 | **likeness, by eye** | a side-by-side of the picture's board and the made board's first play frame, judged by the viewer model | "same layout" when B2 claims a copy; otherwise info with the differences listed | yes (copy claimed and "no") |

### B'. What a VIDEO gave when its board is copied (2026-10-19, videocells.py)
| id | check | measured on | pass when |
|---|---|---|---|
| B'1 | the board is the video's | `level.json` against the cell reading of the video's first frame of play (`studio/_cells/<video>_t<s>.png`) | the same grid, holes, blocks and gates, up to the asked changes (row "Video: the board is the video's"); the B2-B10 rows of a picture apply, named "Video:" |
| B'2 | fewer or more blocks | `level.json` against the frame's board | the asked count fewer or more, every colour left keeping a door (`imagecells.remove_blocks` / `add_blocks`; rows "more or fewer blocks than the video's frame"); "half the blocks" and "easier" likewise |
| B'3 | the copy is asked, not assumed | the words | "the same game design", "this board", "exactly as shown" copy; "a level like this", "the same kind of level", "a new board of this type" build the type (`videocells.copy_asked`); the control row says which |

| B'4 | another game's board | the cell reading | transparent bubbles, glass or ice covers, counters and numbers are not blocks: their cells are floor, said (`imagecells.NOT_BLOCK`; V5/V6, LolTap) |
| B'5 | the colours read are all the colours | the cell reading against the whole-frame read | fewer colour names than colours counted is a doubt and a re-ask; one name over two hue clusters is split by the nearest free game colour (`imagecells.split_hues`; V3: the yellow plus among the orange) |
| B'6 | a copied board's play fits the stated length | the plan | the solution's drags at the planner's tempo against the room the length leaves; the fastest fitting tempo is set, or the overrun is said and the loop does not try to shorten a fixed board (`videoref.copied_board_pace`) |

### C. The game behaves like the game (brief p.11, every version)
| # | check | measured on | bar |
|---|---|---|---|
| C1 | the level loads | `level.json` | a grid the Level Editor allows, blocks on active cells, no overlaps, every door on an edge, one door per cell side (`level.validate`; row "Rules: the level"). Until 2026-10-19 12:00 this row's text CLAIMED "every block has a door of its colour" without a check |
| C1b | doors and colours | `level.json` | every block colour has a door of its colour, every door's colour has a block, every block fits through a door of its colour (`level.door_problems`, kept by all six shipped levels; row "Rules: doors and colours", every workflow) |
| C1c | the colours tell apart | the brief's display colours for the slots the level uses | every pair at least `MIN_COLOUR_DISTANCE` (40) apart on the game's scale (red and orange are about 50), no two slots with one caption name; a block and its door share one material (the runner repaints both). Two blues through one door fail here (row "Rules: colours tell apart", every workflow) |
| C1d | doors used | the recording's drags | info: doors no block left through, with the blocks still on the board (row "Rules: doors used") |
| C2 | every drag is legal | the recording's drags replayed through the port of the C# rules | one block a drag, the pivot through neighbouring free active cells, an exit only through the first gate of its colour with a clear lane |
| C3 | the clock | the recording | counts down only, never below zero; the result matches the blocks gone |
| C4 | the planned moves were played | the play script vs the recording | the same block, cells and outcome for every drag |
| C5 | nothing the game does not have | `ad.json`, the plan | boosters, bombs, ice, keys, characters on the board, doors that change: listed as "not used", never drawn |

### D. The ad works as an ad (brief p.2, p.11; the research)
| # | check | measured on | bar |
|---|---|---|---|
| D1 | gameplay at the centre | `parts.json` | play + replay + result >= 60 % of the ad |
| D2 | the first second | the recording | the game moves within 1.5 s; the hook caption on by 0-3 s |
| D3 | readable captions | `parts.json` | each caption on screen at least its reading time (0.3 s a word + 0.8 s), one at a time |
| D4 | the ending beat is seen | the recording + layers | the result screen or the question held >= 1.5 s before the end card |
| D5 | the end card and CTA | `ad.json` | an end card with a button, 3-6 s |
| D6 | no caption promises what the game does not play | the concept texts | no "pairs", "chains", "all at once" |
| D7 | the viewer's review | the contact sheet, judged by the viewer model against the request | per control: match / partial / no; scores; would download |


Shared since 2026-10-19 afternoon (every workflow, `audit.rows`): "blocks left at the cut" (a cliffhanger's count measured on the
recording; a time-out's one-block limit said, never silent: V5 "two blocks left") and "the end card is a card, not padding"
(D5, at most 8 s), both from `imageaudit`, named without the "Image:" prefix outside the image workflow.

### E. The loop uses the checks (brief p.10)
| # | rule |
|---|---|
| E1 | a failed row with `loop = yes` starts a revision (at most 2 rounds); the revised version is measured against the ORIGINAL request |
| E2 | a viewer "no" or "partial" on a control the request asks is a point for revision even when every measured row passes; a viewer point on a control the request does not ask and the picture set is kept as words, not acted on |
| E3 | the overall verdict for the loop is "fix" when any measured row with `loop = yes` failed, or the viewer says no/partial on an asked control |
| E4 | the final version is the one with the fewest failed rows, then the fewest failed asked rows, then the viewer's verdict |
| E5 | a `not measured` row never starts a revision (the tool cannot judge what it cannot measure) but is reported as a gap of the tool, in the log, in the version and in the test report |

## 3. What was missing before today, and what is added
| gap found | row added | where |
|---|---|---|
| "one more colour" had no row | A6 | `imageaudit.relative_colours_row` |
| "make the yellow blocks blue" had no row | A7 | `imageaudit.recolour_row` |
| "mirrored" had no row | A8 | `imageaudit.copied_board_rows` |
| "harder: one more block in the way" was neither done nor flagged (S10) | A8b | `imagecells.add_blocker`, `imageplan.HARDER`, `imageaudit.copied_board_rows` |
| "the same level number" had no row (S6) | A10 | `imageaudit.label_row` |
| "gets stuck twice" was read as one mistake (S6) | A3 | `audit.asked` |
| a gate named "purple" beside "magenta" blocks left the blocks without a gate (S8) | B2 | `imagecells.parse_answer` |
| two shades of "green" merged into one colour (S10) | B2 | `imagecells.split_shades` |
| a 6-block copied board asked at 40 s ended with a 15.5 s end card and nothing said (S3) | D5 | `imageaudit.end_card_row` (at most 8 s) |
| a merge of the rarest colour left the board unsolvable and the -1 colour failed (S2) | A6 | `imagecells.remove_colour` tries every pair, with the gate repair |
| a hung CLI call in the optional likeness reading cost 20 minutes (S2) | B10 | `LIKENESS_TIMEOUT_S` 150 s |
| the board's identity was never judged; only its type | B2 + the cell-by-cell reading and the copied level (with gate repair of boards drawn unplayable, thin walls as wall cells, transforms) | `imagecells.py`, `imageplan.copy_spec`, `studio.resolve_level` (source "picture") |
| no judgement by eye of picture vs made | B10 | `imageaudit.likeness_row` (the viewer model on a side-by-side) |
| an unparsed ask was "info: none the audit measures" | A13 | `imageaudit.coverage_rows` (`not measured`, named) |
| a viewer "partial" on the asked control was dropped | E2, E3 | `image_guided.feedback`, `image_guided.verdict_for_loop` |

## 4. How a test run proves it
`req3-image-guided-2026-10-19/run.py` saves, per case, every version's rows. `summ.py` prints, per case, the rows of
A-E that apply, their status, and lists every `not measured` row: a run is accepted only when no row that the
request asked is missing, and every failed row either led to a revision or carries the tool's stated limit.
