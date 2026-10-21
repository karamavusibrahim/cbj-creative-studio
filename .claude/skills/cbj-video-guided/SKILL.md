---
name: cbj-video-guided
description: Core requirement 4 of the CBJ brief in cbj-creative - how a prompt PLUS a reference video (or image) becomes a new creative - the reading plan written from the request before the file is read, the whole-clip reading (Gemini 3.5 Flash-Lite first, NVIDIA build as the fallback), the checks in code, the parts snapped to measured cuts, what each reading focus may change in the brief and what it never may (no frame, asset or caption text copied; the look only when asked; another game's mechanic never used), the level's type taken from the reference's board when the request says nothing of the level, the own-creative words rule, the provenance record and the "Reference to creative" card, the nine reference rows and which of them may fail, and the measured reliability of the reading per field. Use when planning, building, testing or judging any creative made from an attached video or image, when writing a test prompt, and when deciding whether a result took too much or too little from its reference.
metadata:
  spec-version: "1"
  last-verified: "2026-10-19"
  game-version: "CBJ Unity 6000.3.5f1, six levels"
---

## 1. Purpose

The brief (p.6) says: a user may provide a creative from another game, an advertisement, or an existing Color
Block Jam creative and ask the system to adapt its concept; the goal is not to reproduce the reference frame by
frame but to understand its creative structure, idea, pacing or visual concept and translate it into a Color
Block Jam creative. This skill fixes how `workflows/guided.py` does that, what it may take from a reference,
what it never takes, how the result is judged, and how reliable the reading is known to be. The rules are in
`~/cbj-work/REQ4-WORKFLOW-RULES-2026-10-16.md` (R1-R14) with the PDF page each one comes from.

## 2. Source of truth

- The brief pages 2, 4, 6, 7, 8, 10, 11, 12, 13 (quoted in the rules document, section 0).
- `src/cbj/workflows/guided.py` (the workflow), `src/cbj/reference.py` (the reading: plan, format step, composed
  prompt, the reader `video_client`/`VideoReader`, checks, parts), `src/cbj/gemini.py` (the Gemini reader), `src/cbj/videoref.py` (what the reading changes in the brief), `src/cbj/audit.py`
  (`reference_rows`), `src/cbj/route.py` (`upload_intent`), `src/cbj/app.py` (`workflow_of`, `_too_long`),
  `src/cbj/static/index.html` (`renderReference`).
- The measured reading accuracy: `~/cbj-work/req4-e2e-2026-10-16/READING-ACCURACY*.md` and `readings*/`.
- The game itself: [cbj-game-rules](../cbj-game-rules/SKILL.md); the controls: [cbj-prompt-controls](../cbj-prompt-controls/SKILL.md).

## 3. Facts

### 3.1 Input and dispatch
- The input is always a prompt plus a file. A video, or an image with reference words ("inspired by this", "a
  level like this board"), goes to the guided workflow; a prompt alone, or with pictures only to place, goes to
  the raw text workflow; a request that names a creative goes to the edit workflow (`app.workflow_of`).
- One of the tool's own MP4s is matched by its bytes. With reference words ("a version of this concept", "from
  this video", "the way this video ends", "like this", "inspired", "take only the hook", a prompt that states its
  own length and ending with no edit word) it is a reference; with edit words ("same ad but", "keep", "change",
  "replace", "swap") it is an edit; with neither it is an edit (`route.upload_intent`).
- A video over 120 s is refused at upload with the reason (`app._too_long`, `reference.MAX_VIDEO_S`).

### 3.2 The reading, in order
1. Format step (`reference.normalise_video`): ffprobe facts (duration, size, orientation with rotation applied,
   codec), then one 360p H.264 copy of the WHOLE clip at `fps = max(2, min(8, 200 / duration))`, no audio.
2. Reading plan (`reference.reading_plan`): the planner's text model (the same client as the brief) gets the
   request and the file's format facts only, and returns focus, level, questions, required fields, ignore,
   constraints, why. A valid plan wins outright; the word table (`focus_words`) is the fallback when there is no
   plan or an invalid one, and otherwise only logs what it would have read. The plan narrows what is APPLIED, never
   what is read (2026-10-17, the owner): every reference is read in full (`read_all: true`, `applied`: the focus),
   a level "none" one too (then nothing is applied). What the request leaves open is filled from the general
   reading after the focus (3.3, `videoref.open_aspects`).
3. Composed prompt (`reference.video_ask`): preamble (the game, adapt not copy, measured timestamps only, no
   invented mechanics, seen apart from inferred), the request quoted, the general reading always
   (`GENERAL_QUESTIONS`: what it shows and what happens in order; which game; the concept; the board; the ending,
   with the fifth wording "it stops mid-level" = cliffhanger; the hook; the captions word for word; the HUD at the
   first frame of play; the mechanics and what the game does not have), then the plan's questions under "THE USER
   ASKS IN PARTICULAR" as priorities, the ignore list, the clip's length as the only time reference, the schema with
   `GENERAL_FIELDS` (what_it_shows, game_or_product, concept_in_one_line, structure, hook, ending, captions_seen,
   screen_text, hud, board, mechanics_seen, extras_seen) and the plan's fields marked REQUIRED. The board field: columns and rows at the first frame of play, the shape (open, narrow_center, door,
   holes, cross, ring, lanes, each in one sentence: an hourglass has the middle rows walled across the whole width
   but a two-cell passage, a door a left and a right room, holes one or a few separate wall pieces; read from the
   outline and the wall cells only), the blocks (only those that leave through gates, never an obstacle), each
   distinct colour once, named as seen (purple and magenta, blue and light blue are different names), the pieces (small,
   long, big, varied, mixed), the sides with gates, the obstacles that are neither a block nor a wall, how busy it
   looks. The board is no longer in `DEFAULT_IGNORE`.
4. The whole clip read once (`reference.video_client`, a `VideoReader`): Gemini first (`gemini.GeminiVideoClient`:
   `gemini-3.5-flash-lite` only by default, `GEMINI_MODELS` / `CBJ_GEMINI_MODELS`; the copy inline, JSON out, low
   thinking, temperature 0.2, 300 s; 429/500/502/503/504 retried after 10, 20, 40 s; key `GEMINI_API_KEY`), and
   NVIDIA build when Gemini raises (no key, or no Gemini model answered: super-vl first, the omni model second, 8000
   tokens, 300 s, a "length" answer re-asked with the budget doubled). `CBJ_VIDEO_READER` ("nvidia,gemini" or
   "gemini,nvidia"; default gemini first) sets the readers' order (`reference.reader_order`, `VideoReader.order`); the
   log ("readers: nvidia first, then gemini (CBJ_VIDEO_READER)"), `analysis.reader_order` and the card say it. The
   analysis stores `reader` ("gemini" or "nvidia"), `model`, Gemini's `usage` (prompt, candidates, thoughts tokens) and
   every failure of both readers in `errors`. A broken JSON answer is asked again strictly.
5. Checks in code, per section (`reference.validate_notes(..., general=True)`): only the parts are checked: a part
   outside the clip, ending before it starts, out of order, no usable parts, or the wrong-unit signature (the long
   last part an end card, a result or "other", over 60% of the clip, with under 30% before it; one gameplay part over
   the whole clip, or a long last gameplay part, is valid). A label is never a reason to reject: `purpose_of` maps
   synonyms and unknown labels to "other", keeping `purpose_raw`. A "hook" part longer than max(3 s, 25% of the clip)
   is play (`reference.long_hooks`, in `structure` and `videoref._segs`; round 3 case 18: "0-12 s hook" on a 15 s ad):
   its first 1.5 s stay the hook with its captions, the rest is gameplay, both marked `split`. One re-ask with the problems quoted, then the parts
   alone are dropped (`notes.structure` = [], `notes.structure_rejected`, `parts_dropped` "the parts were not usable:
   ..." on the analysis, the card and the assumptions; the part rows info) and everything else is kept and applied.
   Only an answer that is not JSON loses the reading ("not read").
5b. The ending read a second time (`reference.read_ending`, skipped under 12 s): the last 10 s cut from the copy at
   8 fps (`tail_copy`), one short JSON question to the same reader (`ending_ask`: the four endings, the last clock
   reading MM:SS, win screen, out-of-time screen, question caption). Stored as `analysis["ending_read"]` (ending,
   last_clock, win_screen, out_of_time_screen, question_caption, why, from_s, to_s, fps, frames, model, reader,
   seconds; `overrode` when it disagreed). It wins over the whole clip's ending: `notes.ending` becomes its ending
   and the whole clip's word is kept as `notes.ending_whole`. Every reading prompt also carries the fixed question
   naming the four endings (`reference.ENDING_QUESTION`).
5c. The board read a second time (`reference.read_board`, on every reading): one still of the ORIGINAL file at the
   first frame of play (`board_at`: 0.3 s into the first part with play on screen; the source's resolution, at most
   1920 px on the long side, 1280 px when NVIDIA is the first reader, `BOARD_STILL_PX_NVIDIA`, `still_px`,
   `board_still`). Every ask of this step is a still's short ask (`describe_still`: `STILL_MAX_TOKENS` 4000 with no
   doubling, `STILL_TIMEOUT_S` 150 s, one try per model, a model that answered nothing on a still skipped for the read's
   later stills; round 3: super-vl had reasoned 16000 tokens per still, 1379-2413 s per board step); the frame's ask
   always runs, and the crop's ask, the colour count and the size re-asks only while `BOARD_READ_BUDGET_S` (300 s) of
   wall clock remains (else `board_read.skipped` "... : skipped: budget", in the log line too; the code's measure on the
   crop still runs). The whole clip and the ending keep their budgets and retries. The board question, the board's box and the extras on screen
   (`board_ask`), the same reader; a box under 25% of the frame is cropped with a 10% margin (enlarged to 1024 px,
   `crop_to_box`) and read once more (`board_ask(crop=True)`); the crop wins only when it agrees with the frame
   (`crop_disagrees`: size within 2 a side, blocks within 40%, half the colours), and a box more than 40% off the
   board's columns:rows is not cropped (`box_disagrees`). Its board wins (`notes.board`);
   the whole clip's is kept as `notes.board_whole`; the frame's extras join `notes.extras_seen`; stored as
   `analysis["board_read"]` (board, at_s, width, height, box, board_frame, crop, extras_seen, model, reader,
   seconds, or error, when the whole clip's board stands). Then on the crop: the board measured in code
   (`measure_board`: block/floor cells on the read grid; the block mask against its mirrors, best axis near the
   middle, intersection over union 0.8, decides the symmetry (`mirror_iou`; the cell grid's match is info: it
   depended on the size read); the block cells' colours clustered by hue 24 degrees and lightness 0.3, three cells or more), the reader
   asked once for the colour count (the symmetry is the code's alone: the reader's votes said "not symmetric" every
   time, and the free daily quota counts every call); the count is the larger of the read names the code's clusters confirm (`confirmed_names`, one cluster each) and the
   reader's, at most 7; a colour no reader named is never added; a colour only the code found named from its cluster
   (`colours_added`); a surplus read name merges into a counted colour only when close to it (`COUNT_MERGE_MAX`).
   The size is asked three times more there and the median per side kept (`median_size`, `size_reads`); the code's
   grid gives `occupancy` (the share of cells under blocks).
   The board's `wall_cells` turn an open or holes board into the closest one the generator builds
   (`videoref.wall_choice`: open, or holes with the fewest walls, within a cell a side), said on the card. Reason: at 360p
   another game's landscape board is a few hundred pixels (the owner's test: 12 blocks read as 7 on 5x5, its
   bubbles missed; on the still 13 on 6x6 with the bubbles).
6. Parts (`reference.separate_parts`): only when the focus is structure, pacing or hook, or a concept read asks
   about the pacing: cuts measured on the copy, every model boundary snapped to the nearest cut within 1.5 s, the
   model's own seconds kept beside it; the pace change measured over the gameplay parts only. The model's
   confidence never triggers it.
7. The analysis stores the plan, the prompt, the facts, the notes (structure with purposes, captions_seen,
   screen_text for the HUD, hook, ending, ending_whole and ending_read when the second read ran, mistakes list,
   moves_by_third, cta, dominant_colours, mechanics_seen, adaptation, board and board_whole, confidence), the
   computed pacing, the validation, the separation record, the ending read, the board read, seconds, reader and model.

### 3.3 What a focus may change in the brief (`videoref.apply`)
| focus | sets | never |
|---|---|---|
| concept | everything below except the look | the look |
| ending | gameplay.ending from `videoref.mapped_ending`: the last seconds' read first, checked against its own transcription (a near-fail whose last clock is over 5 s = win; a cliffhanger with a win screen transcribed falls back to the whole clip's ending); a question (a part, or the last seconds' question caption) = cliffhanger unless a win or out-of-time screen was transcribed anywhere; victory with a near-fail part = near-fail; fail = time-out; gameplay.mistakes: a targeted ending read the larger of the list and the mistake parts, max 3; a concept (full) read or a filled ending the mistake PARTS only, at most 1, never the free list (`videoref.mistake_parts`; round 3 case 16), none seen leaving a near-fail's or time-out's own as planned; a revision keeps it (`guided.PINNED`); gameplay.finish streak on a fast finish; level.difficulty hard for a near-fail when not stated | |
| structure | pacing.length_s (the reference's into 30-60; then `videoref.fit_length` shortens it from the play, below), sequence.replay (only if the reference repeats a moment, and not when the stated length is under 40 s), sequence.hold_s, sequence.end_card, the parts' proportions for the row; a reference that is play from start to end (>= 90% play, no end card) or shorter than 90% of the ad (`videoref._pure_play`): sequence.intro_s 0, sequence.hold_s 0, pacing.tempo calm (studio then records the longest play that fits) | the request's own intro, hold or tempo; the play engine (only the brief's fields) |
| pacing | only when the request asks about the pacing (`audit.pacing_asked`: a targeted plan naming it, else the words; round 2 case 03: a concept read's "slows down" made the ad's own Pacing curve check fail): pacing.curve (the measured motion over the play, else the model's word) and the reference's drags a second (`target_dps`: counted, else the middle of its tempo word's class) for the play decision below; not asked: "read but not applied" in the assumptions; level.moves for a long play only when no length is stated and no play decision is made; always with the assumption "read approximately" | the request's own tempo, curve, moves or blocks |
| the play (pacing taken, or a pure-play or shorter reference) | ONE decision (`videoref.play_levers`, after the board and the flow; round 2 rerun case 05: the stretch rule and the pacing levers both wrote the tempo, the play was 19.9 s of 30 s): the play seconds first (`play_target`: the ad minus the end card the reference keeps, 3-4 s, the result or the question, a still opening and a replay, capped by what studio records, which keeps REPLAY_EST_S for a replay and the shortest card: `studio._length_pick`), then pacing.tempo and level.moves from `SEC_PER_DRAG` (seconds a drag by tempo and studio's pacing grade, fitted on the tool's recordings; `solve_pace` is studio._short_solve's arithmetic, checked against it by a test): with the pacing taken the rate is pinned to the reference's class (calm/normal/fast) and the best fill inside it wins; without it a calm tempo and the moves that fill (with a speeds-up curve a normal tempo and more moves when that play comes within `RISING_FILL_SLACK_S` 2.5 s of the seconds, calm only otherwise, said in the line and `prov["play"]["curve"]`; round 3 case 16); level.blocks raised (at most 10) and the board grown a cell a side from the read when the moves need more blocks than it supplies; gameplay.hesitations 0 (studio's pick-ups are quick drags); pacing.tempo always recorded in brief.reference.set (pinned, even when the planner had set it); `prov["play"]` {mode, target_s, expected_s, rate, tempo, moves, blocks, grade, scale}; one line "the play fills about N of M s ..."; the length from the play (`videoref.fit_length`, round 3 case 17: 60 s, a 37 s play, a 21 s end card): with no single length stated and the play short of its seconds with no lever left, the ad's length drops (to 30 s at the least) by what the play misses and the levers run again there, a few times, the length whose play misses least kept; it never rises above the reference's own length in the range (or the plan's); "the ad is N s, not M s: ..." in the line and `prov["play"]["length"]` {from, to, why}; a stated single length is the brief's before the play is planned | the request's own tempo, moves, blocks, size or hesitations |
| hook | concept.hook from the hook's function (question, challenge, dare) in the tool's own words | the reference's words unless "same words" is asked |
| captions | one caption per function the reference has (challenge, wrong, instruction, urgency, result, cta), own words | the reference's words unless asked |
| look | visuals.background and the caption colours from the dominant colours through `imageref.style_kit` | the blocks' colours, ever |
| board_colours | level.colours only, mapped to the game's own (`_apply_board_colours`); the board row judges the colours alone | the board's shape, size, blocks; the background |
| the board itself (2026-10-19, `videocells.copy_asked`: "the same game design", "this video's board", "exactly as shown"; not "a level like this", "the same kind of level", "a new board of this type", "a similar game") | the first frame of play (`videocells.frame_time`, `studio/_cells/<video>_t<s>.png`) read cell by cell as a picture (`imageread.read` + `imagecells`, verified on the pixels, solved, repaired if drawn unplayable, said); level.source "picture" + level.file (`imageplan.copy_spec` via `videoref._copy_board`), with the asked changes in code and said: fewer/more blocks, half the blocks, easier (`imagecells.remove_blocks`, `add_blocks`), one more/fewer colour, a recolour, a mirror, harder; the control row's plan text is the code's line alone; a revision keeps the copied level (`guided.revise_once`); a frame that cannot be read, a board the solver cannot settle or a new-board ask falls back to the type path with the reason noted When the video is CBJ itself, the copied board is shown in the colours the footage shows (the live game's palette differs from the build's: teal, magenta, violet, lime in trailer 2), each slot's block and door repainted together and the mapping said; a request naming block colours keeps its own, and a revision never repaints from a viewer's remark. A cliffhanger keeps an asked starting clock (the trailer's 01:05 with "keep its clock"; brief.check and play.fit_clock, 2026-10-19): the cut comes wherever the clock stands; a near-fail and a time-out still land on their planned second. The cell reading cross-checks the colour count against the whole-frame read and splits one name over two hue clusters (V3: the yellow plus and the orange cubes were both "orange"); a copied board's play is estimated against the stated length at plan time, the fastest fitting tempo is set, and when none fits the plan says the length the ad will need and the loop does not try to shorten what cannot be shortened (videoref.copied_board_pace). | the generator's type path for that board; the video's look (the blocks are never repainted from a video) |
| screen (or look) | visuals.camera_zoom from the board's share (`zoom_for`, within brief.ZOOM_RANGE), visuals.hud_level / hud_timer as the reference shows them, visuals.cursor hand or none; with the clock hidden on a near-fail or time-out (`videoref.hidden_clock_captions`, round 2 case 09: ad.py shows the hurry caption from the clock's 5 s to the last drag, 0.93 s there, and left out "2 seconds left!"), the hurry caption is "Hurry!" and the result caption carries the seconds ("Phew! 2 seconds left!"; a time-out "Out of time!"); a quoted caption stays | the request's own zoom, HUD or cursor |
| board (HUD) | a CBJ reference (it says so, or its HUD reads "LEVEL n" with a clock above 00:00 and no other game is NAMED: "Wood Color Jam" blocks it, "another puzzle game" does not; `videoref.hud_of`, `named_game`): level.label from the HUD's level number, gameplay.timer_s from its first clock, each only when the request does not state its own; the clock for a win and a cliffhanger, for a near-fail or time-out only when the play can bring it down to the ending's seconds (`clock_unreachable`), and always when the request asks for the video's starting time (`START_TIME_WISH`; the row says when impossible); brief.validate keeps a starting clock for a win only (unchanged), so a cliffhanger's clock is dropped there | a clock the ending cannot reach (said in the assumptions) |
| board | the level's type part by part, where the request states nothing about it: level.source generate, level.shape, level.width/height clamped to what the generator builds for that shape (4-9 x 4-10; narrow_center >= 6 rows, lanes 7x6, ring 6x6, cross 5x5, door 5x4), level.blocks (2-10, and at most the free cells at the generator's packed fill for those pieces; blocks that do not fit the size read first grow the board a cell a side within the generator's sizes, `grow_for_blocks`, then are cut; `brief.reference.board.fit` and the card say which), level.style "symmetric" when the board reads mirror-symmetric (`board.symmetric`) and "packed" when it is full (the code's measured `occupancy` 60% or more, `board_full`; never from "busy"), when the request states no look of the level; a capped block count (over 10) shrinks the board to keep the reference's blocks per cell (`keep_fill`); a cliffhanger that stops with 3+ blocks on the board (`ending_read.blocks_left`) gets gameplay.blocks_left 3, level.colours (each distinct reference colour to its own game colour at the least total distance, `board_colours`: purple and magenta give purple and red; the notes "magenta -> red: the game has no magenta, purple is taken by purple" on the card and in the assumptions; over seven names, the closest two merge, never two game colours), level.pieces; `busy` is recorded and shown only (1-2 of 12 against the difficulty, below R10), the difficulty stays the request's, the ending rule's or the generator's default; plan row "a new board of this type is generated and solved, its cells are not copied"; "its exact layout" to not_copied | the cells (never copied); a block, wall or shape from another game's obstacle; the difficulty; a request's own shape, size, blocks, colours or pieces; anything when the request names the game's own level ("level 3", "a shipped level") |
- The request's own values always win: `videoref.stated()` lists what the prompt fixes (length, ending,
  mistakes, difficulty, finish, tempo, curve, moves, replay, end card, result screen, hold, background,
  caption colours, no captions; and for the board: shape words such as narrow, hourglass, holes, walls, ring,
  lanes, "open board"; a size such as 7x9 or "a big board"; a block count; colours for the blocks; piece words;
  difficulty words; the game's own level or "level N"; the level's look: symmetric, mirror, packed, spacious,
  colourful; a still opening; "the result held ..."). A plan constraint that cites the reference ("Length around
  30 s, matching the source": round 1) is the reference's value and fixes nothing (`videoref.own_constraints`).
  "How fast" is a question, not a stated tempo, and "the
  same layout" or "doors" (the gates) are not a stated shape.
- What the request leaves open is filled from the general reading (2026-10-17, round 2 case 14, the owner's rule:
  "what the request names is taken first; what it leaves open is filled from the video's general reading; 'only X'
  takes just X; the request's own values always win"; `videoref.open_aspects`): besides the plan's focus, the board
  (type, size, blocks, pieces, colours, its look from the measured fill), the ending, the flow (structure) and, when
  the reference is CBJ (`hud_of(...)["cbj"]`), the screen, each only when the focus does not cover it
  and `stated()` has nothing for it (the board: no shape, size, blocks, moves, colours, pieces, style, level or
  difficulty word; the flow: no length, replay, end card, result screen or hold). Nothing is filled when the
  request says "only", "just the", "nothing else", "everything else is mine" or "the rest is mine"
  (`videoref.EXCLUSIVE`). The look (the background) is never filled: it needs the request's words. Each line it
  adds ends "(filled from the reference (the request left it open))" (`videoref.FILLED`); `prov["filled"]` lists
  the aspects, and the card shows them next to the applied focus. A screen the request's words name and the plan
  missed ("its cursor") is asked, not filled: `prov["named"]`. A request that names the cursor and nothing else of
  the screen (`videoref.cursor_only`) takes only the cursor (from the framing answer, or a hand the reading lists
  as seen when there is none), never the zoom or the HUD. The ending words of the request are its own
  (`videoref.ENDING_STATED` in `stated()`: "before solving it", "stop before the level is solved", "lose the
  level", "a cliffhanger", "the win screen", "unsolved", and `SOLVE_PHRASES`: "the (final) solution", "the solve",
  "the solved board", "a satisfying solve/solution/finish/clear", "clears the (whole) board", "the last move clears",
  "finishes the level", read with `stated(..., video=True)` only), so the video's cut never replaces "stuck once before
  solving it".
- The round-3 rules below are the video workflow's alone (the owner, 2026-10-17: the text and image workflows keep their
  behaviour): `audit.asked(..., case_range=True)`, `videoref.stated(..., video=True)`, `fit_captions(..., chain=True)`
  from guided.py's two calls, and `guided.video_ref(brief)` in the helpers image_guided.py shares (`keep_stated`,
  `length_guard`, `asked_controls`, `pin_reference`'s mistakes pin); a guided revision uses `guided.keep_asked_guided`,
  create's `keep_asked` stays the text workflow's (it still reads "30-60 second" as 60 s).
- A range inside the brief's 30-60 s ("a new 30–60 second ad", "30-60s", "30 to 60 seconds", "between 30 and 60
  seconds") is no stated length on the video path (`audit.asked(..., case_range=True)`: `length_range`, info row "Asked: length range"; round 3 cases 16-18
  were made 60 s with 10-41 s end cards); a single number ("a 45 second ad") stays a stated length. The reference's
  length then decides in the range (28.9 s and 15 s give 30 s), the plan's 30 s otherwise.
- "A moment to breathe", "breathe", "linger", "let it land", "hold the solved board" (`videoref.BREATHE`, `breathe`):
  the result held `BREATHE_HOLD_S` 1.5 s longer (sequence.hold_s, never lowered) and no replay of the play unless the
  request asks for one; `stated()` names hold and replay, so a revision keeps them (round 3 case 19).
- The owner's trailer-2 creative (2026-10-17, video path only): the board's top row is never under the HUD
  (`videoref.hud_clear`, last in `_apply_one` and in every guided revision via `guided.hud_fix`). The board's top at
  zoom 1 depends on its rows beyond its columns, the zoom scales about y 1020 of 1080x1920, the HUD's bottom edge is at
  y 636 (measured with `tests/data/hud_margin.py` on 58 own recordings): `SAFE_ZOOM_BY_EXTRA_ROWS` {-1: 1.12, 0: 1.12,
  1: 1.1, 2: 1.0}, 3 or more rows beyond the columns under the HUD at zoom 1 already; `SAFE_ZOOM_BY_ROWS` {4: 1.12, 5:
  1.1, 6+: 1.0} when the columns are unknown; no size at plan time and a stated zoom: the cap 1. A zoom the request
  states (`zoom_stated`: "zoom in", "closer", "close-up", "fill the screen") with a HUD it does not ask for
  (`hud_asked`: HUD, clock, timer, level badge, the seconds on the clock) hides the HUD ("the HUD is hidden: the closer
  zoom would put it over the board's top row; the request asked for the zoom, the HUD came from the reference"); an
  asked HUD caps the zoom; neither asked caps the zoom and a board covered at zoom 1 hides an unasked HUD;
  `prov["hud_clear"]`.
- Relative words for the moves or blocks ("fewer moves", "a few moves", "fewer blocks": `RELATIVE_MOVES`,
  `RELATIVE_BLOCKS`) are stated with `stated(..., video=True)` ("moves", and "blocks" for the blocks): the play levers
  keep the planner's count, never raise it, accept the shorter play and say the cause first in the play line and
  `prov["play"]["cap"]` ("the request asks for fewer moves: 6 kept; the play fills 15 of 21 s"; `prov["moves_asked"]`). When the planner gives no number (round 4, case 28), the count comes from the reading
  (`videoref.relative_count`): "fewer" about 70% of the reference's counted moves (`reference_moves`: moves_by_third,
  else the gameplay parts' moves) at least 4, "a few" 4-5, "more" about 130% at most 14; no usable count: calm/normal/
  fast 7/9/11, estimated; a cliffhanger's board gets the moves minus its cut's blocks (2-10); the arithmetic in
  `prov["moves_asked"]`, the assumptions and the play line; the levers never raise those blocks.
- On a cliffhanger the line the request asks for at the end (`videoref.end_line`: a quoted line in a sentence about the
  end, "End unsolved with a 'your turn' line", "stop ... and ask 'X'"; unquoted "a your-turn line" gives "Your turn!") is
  the question caption (`concept.result`), or `concept.end_title` when its sentence names the end card; never dropped
  (`fit_captions(..., chain=True)` only).
- Round 4 (2026-10-17, video path only): the play decision runs for every guided creative (case 29: a screen, look and
  colours read made none; a 40 s win played 20.6 s and studio added an 11 s slow replay): with no pace taken and no
  pure-play or shorter-reference fill, `play_levers` fills the play seconds for the brief's length (mode "fill", one play
  line, `fit_length` when no single length is stated); a replay neither the request nor the reference has (no replay
  part, no repeat words) is turned off while the play can fill, and comes back, said, when it cannot; the request's own
  size caps it ("the request's own 5x5 board holds at most N blocks"); not for the game's own level, or a plan that
  takes nothing from the clip.
- Round 4, case 30: words that imply a win ("the winning move", "after the win", "a replay of the solve/last move", "once
  it's solved", "the level completed screen") are in `SOLVE_PHRASES` (the request's ending, a plain solve); an asked
  replay (`audit.asked` sequence.replay) is stated, sets sequence.replay, and turns a cliffhanger into a win (a near-fail
  with close-call words: `videoref.replay_ending`); a planner assumption that cites the request about the ending
  ("because you asked ...", `planner_ending`) makes the ending the request's; the reference's ending is then "read, not
  applied (the request sets its own ending)". A quoted line followed by "card" goes to the end card's title for any
  ending, and the same line elsewhere is cleared; a revision whose "Asked: the replay" missed unpins the ending and the
  cut (`guided.PINNED`) and `guided.replay_fix` turns the replay on and the cliffhanger into a win. Round 4 rerun: with the pace taken and the moves the request's own, the levers keep the reference's tempo class with no
  added hesitation and a shorter play, said (`prov["play"]["own_moves"]`; case 28's calm stretch made the gaps 0.60 s to
  1.60 s); the end card's fact line is never the asked title's text (the planner's different fact stays, else
  ad.END_FACTS for the ending; a matching cta goes; case 30 showed "Can you do it faster?" twice).
- A mechanic the game lacks (another game's bubbles, ice, keys, locks, boosters, bombs, any other obstacle) is
  never created, drawn, simulated or used (the owner's rule, 2026-10-17): no block, no wall, no shape comes from
  it; one line "<it>: not used: not in CBJ" in the assumptions and on the card (`prov["not_used"]`),
  and "its <it>" in not_copied. The board's obstacles are listed the same way (a mechanics_seen entry about the
  same thing gives way to them). A `MECHANICS` row only adds the game's own parameter the brief already has
  ("; the ad keeps the game's own near-fail" for a booster, "...own fast finish" for a merge). The game's own
  things (drags, gates, the clock, the result screen, the HUD, wall cells, the grid, the hand cursor) are native and
  never "not copied"; booster buttons and anything else on screen the build lacks (`extras_seen`) are "not used"
  too, once per thing;
  a grey, dark, fixed or barrier cell named among the obstacles that is no other game's thing is a wall cell
  (`WALL_LIKE`), and an "open" board with such cells is a holes board; a level map is "not used: an ad shows
  one level".
- The hook's kind (`videoref.hook_kind`, round 2 rerun case 14: "starts directly with a puzzle board and a hand cursor
  pointing at a block" was taken by its timing alone and the ad opened on a headline): "caption" (a question,
  challenge or dare in words) or "gameplay" (no caption, the play from the first frame). A gameplay hook gives no still
  opening (sequence.intro_s 0) and `prov["hook_kind"]`; ad.py still draws a hook caption on frame 0 (the poster) and
  play.py's start hold puts the first touch at 1 s, so "no headline, cursor on the first block at 0 s" needs an owner
  decision on those protected files.
- The hidden clock's result caption is one line (`videoref.one_line`, measured with draw.wrap and ad.STYLES/BAND, never
  changed): "Phew! 2 s left!" (round 2 rerun case 09: "Phew! 2 seconds left!" wrapped and sat on the "+50" button).
- The play decision also turns the hesitations (a pick-up and put-back, `HESITATION_S` 1.5 s, its own pace in any
  grade, at most `MAX_HESITATIONS` for the ending; rerun 4 case 05: six played drags is the most studio paces with a
  long look in a 30 s ad, and a cut plays its moves minus the blocks it leaves); when the best still falls short its
  line and `prov["play"]["cap"]` say which limit stops it (studio's recording cap, studio's pacing grade, the board's
  blocks within a cell a side, the ending's hesitations, the request's own values). A revision whose play levers
  change nothing says so with that limit (`guided.play_again`).
- The taken pace wins over the fill (rerun 5 case 05: a calm 0.24 reference, no option in the calm class, and the
  fill won at 0.5 drags a second): in the reference's class the best fill; with none in it, the nearest rate (fewer
  moves, no hesitation, a shorter play), and the play line says the cause (slower than play.py's longest look).
- A rule that changes a field the planner set (plain_solve's ending, the play levers' tempo, the screen's clock, a
  revision's guard) takes the planner's words for the old value with it (`videoref.correct_texts`, `OLD_VALUE_WORDS`;
  rerun 5 case 14: "solve the level with a second left on the clock" over a plain win): those sentences of the
  control's text and the planner's assumptions that argued for it go; the reference's own lines stay.
- A revision of a take that ran over the stated length never lengthens the play (`guided.length_guard`, rerun 4
  case 09: a speeds-up curve's careful pauses took 48 s to 49 s): a new curve, a calm tempo, more hesitations or
  mistakes go back, and the tempo whose play fits the room left (the length minus the shortest end card, the result
  and a replay) is chosen with the take's measure, unless stated or the pace was taken.
- A revision the viewer alone started must change a control the viewer's points are about (`guided.viewer_points`),
  or no version is made (rerun 4 case 14: a punch-in for "the stuck moment is quick" re-used the same recording).
  The press into the blocker (play.MISTAKE_HOLD_F, 0.6 s) and the look after it are play.py's own: no brief field.
- The stuck moment points at one piece (`videoref.stuck_step`, rerun 3 case 14: "O1 (orange) ... O2 (orange) is in the
  way" under "I can't reach orange!"): with a blocked move planned (not a cliffhanger), no colour named and no stuck
  step of the request's own, a stuck step with two different colours of the board's palette is added
  (gameplay.events; an event's colour is one block on the generated board, generate's singles, and the blocker's colour
  goes through its named-blocker swap); with no palette known it is left to the generator, said. Info row
  "Reference: the stuck moment" (`audit.stuck_row`): the first played "mistake" beat, numbered as the Mistakes check
  names it (never a hesitation or a cliffhanger's bump; no mistake, no row), the mover's colour count on the made level
  and the blocker's colour.
- A wall cell off is within the reading's error (`videoref.WALL_SLACK`, rerun 3 case 05: 4 wall cells read kept the
  4x7 holes board and cut 9 blocks to 6): `wall_choice` ranks walls off beyond one cell, then blocks short (grow before
  cut, both sides), then walls off; 4x7 read with 4 walls and 9 blocks gives holes 5x8, 5 walls, 9 blocks.
- A plain solve is a win (`videoref.plain_solve`, round 2 case 14: "show the player stuck once before solving it" was
  planned as a near-fail): the request names a solve, says nothing about the clock or a close call, does not stop
  before it, and the reference's own ending is no near-fail. A cliffhanger or a time-out, from the plan or the
  reference, becomes a win too (round 3 case 19: "give the final solution a satisfying moment to breathe" kept the
  reference's cliffhanger), its blocks left cleared. "Stuck", "wrong move", "mistake" state the mistakes
  (`MISTAKES_STATED` in `stated()`).
- `fit_captions` also clears a mistake caption when no wrong move is planned (a cliffhanger's blocked attempt is one),
  and, with `chain=True` (guided.py only), a caption promising a chain of exits (`CHAIN_CLAIM`: "flies", "all leave", "one after another", "chain",
  "cascade") is kept only with gameplay.finish "streak", otherwise the tool's own words ("Almost there!", the ending's
  result line, "Can you clear it?"); a caption the request quotes stays (round 3 case 19: "One move. Everything
  flies!").
- The look guard: when the look is not a focus and the prompt names no colours, anything the planner's model
  took from the video's colours is put back to the game's own; the blocks are never repainted from a video.
- Only the first video steers the brief; further videos are noted.
- `brief["reference"]` is the provenance: file, focus, level, analysed_s, confidence, adapted, not_copied
  (always the gameplay, the characters and assets, the exact frames, the caption text unless asked; the exact
  layout when the board was taken; each mechanic not used), stated, mechanics (native only), not_used, board
  (read, text, took, kept), filled (the aspects the request left open, filled from the reading), named (a screen
  the words name and the plan missed), not_read when the reading failed.

### 3.4 The evaluation (`audit.reference_rows`, group "reference")
| row | can fail | judged when |
|---|---|---|
| Video: the board is the video's (+ one row per change, + looks like the picture (viewer)) | yes | the board was copied (brief.reference.board.copied): `imageaudit.copied_board_rows` and `likeness_row` against the frame, named "Video:" (2026-10-19) |
| Rules: doors and colours, Rules: colours tell apart (group "rules", every workflow) | yes | always: `level.door_problems` (every block colour has a door, every door a block, every block fits through a door of its colour) and the shown colours at least 40 apart with distinct names (`audit.door_rows`, `audit.colour_rows`, 2026-10-19) |
| the ending | yes | the focus covers the ending and the prompt does not state it |
| the pacing | yes, with tolerance | only when the request asks about the pacing (a targeted plan naming it, `audit.pacing_asked`; else the words); the ad's change by the same pause measure as the "Pacing curve" check, "even" within the reference's own band (`audit.EVEN_RATIO` 1.3: the reading calls thirds within that ratio even; it was 15 % of the larger, stricter than the reading; round 2 rerun case 05's 1.20 s against 0.92 s, 1.30, still fails); the tempo only when it came from counted moves |
| the hook | yes | the focus covers the hook (`audit.hook_row`): its kind and its start. A caption hook: the ad's hook caption starts within the reference's hook length + 1 s and has its function (question, challenge, dare); a gameplay hook: the ad opens on the play (a still opening fails), and ad.py's own hook caption is shown, info |
| the purposes in order | yes | the focus covers the structure; compared without gameplay as a stage; win and fail both "result" when the prompt states the ending; the reference's replay optional under 40 s |
| the part lengths | yes | the focus covers the structure; normalised mean absolute error of the shares at most 0.2; with no end card in the reference the ad's first 3 s of end card are not counted, with no hook part the hook caption over the play is play; a reference shorter than 90% of the ad: hook (at most 4 s, `STRETCHED_HOOK_MAX_S`), result and end card (3-4 s) in seconds, the play the rest (`audit._stretched_lengths`) |
| the captions | yes | the focus covers the captions: one caption per function the reference has |
| the look | yes | the look is a focus: the brief's background within a family or 48 RGB of a dominant colour (plan), the poster's margins within 48 of the brief's background (ad) |
| the board | yes, only for the parts in `audit.BOARD_RELIABLE` (shape, size, blocks, colours) | the focus covers the board and a board was read: the made level (`level.json` in the version folder, its shape from its walls, `made_shape`) against the board as the brief took it (videoref's adapted values, not the raw reading; round 2 case 04): shape equal, size within 1 cell a side, blocks within 2, at least half the reference's colours present; a part the request states is its own (info); "level N" or the game's own level: info; a part not reliable would be info, "read approximately" |
| nothing copied | yes | always: no layer of the ad uses the file |
| the screen | yes, the HUD part only (at the plan) | the screen or the look is a focus and the HUD was read: the HUD shown or hidden as the reference; the zoom is info (`audit.screen_row`); a HUD `videoref.hud_clear` hid for the board's top row is info, not a miss |
| Reference: the screen: the HUD over the board (Asked: the zoom when the request states the zoom) | yes, when the brief has a lever: an unasked HUD or a zoom above 1 | always in the video workflow with a parts manifest: `audit.hud_measure` on the first frame of play (`hud_frame.png`): the HUD shown (30% of its bar purple), the board's top (6 rows of 12 board-coloured pixels outside the HUD's box, away from each row's margin colour) above the HUD's bottom edge less 10 px, a top cut by the edge within the HUD's width, or the cells' floor right under the bar; the revision hides an unasked HUD or lowers the zoom (`guided.hud_fix`); an asked HUD at zoom 1 is info (the game's framing) |
| Asked: the captions fit the ending | yes (from "reference") | always in the guided workflow: no caption claims a clear, win or beaten clock on a cliffhanger, a win on a time-out, a fail on a win or near-fail, and a mistake caption needs a wrong move among the play's moments (mistake, attempt, bump; round 2 case 09) (`audit.captions_fit_row`); the plan side is `videoref.fit_captions`, run after planning and after each revision |
| read with confidence | info | always: level, focus, the aspects filled from the reference, seconds, confidence, low confidence said |
- The guided version record is written again after the review (or its error) and with the loop's verdict
  (`guided.save_record`; the owner's v1 of 2026-10-17 had review.json but no review in version.json); a revised
  version keeps its "made" record, the later verdict goes in `loop`.
- A field a pin or keep_stated restores takes its plan text with it (`guided.restore_texts`, rerun 3 case 09: the
  final version's visuals text said "the clock is now shown" over a hidden clock): every field of the control the
  base's again, its row is the base's; otherwise the sentences naming the restored field go and "Kept as in the
  version before: ..." is added. A control none of whose fields changed keeps the base's text (`unchanged_texts`); a
  play re-run rewrites the pacing text with its line.
- With nothing measured missed, the viewer's "not as asked" starts a revision only about what the request asks (its
  stated values, quoted captions, a targeted plan's focus, the pacing only when `pacing_asked`) or the reading set
  (brief.reference.set; the fill's tempo and moves count as the flow, not the pacing) (`guided.feedback`,
  `asked_controls`; round 2 rerun case 03: "difficulty or pacing" on "create a similar game" undid a 20-of-20 ship).
  The final version is the best, not the last (`guided.best_version`): fewest measured misses, then ship before fix,
  then the later; `final` on the chosen version.
- A guided revision restores every value the request states (`guided.keep_stated`: `stated()`, the asked clock,
  seconds left and hesitations, the request's own HUD, zoom or cursor) to the base version's, unless that fact's own
  asked row failed at the plan (round 2 case 14: the viewer's "the stuck moment is short" made 1 mistake 2). It keeps
  the pure-play and stretch rules' tempo, intro, hold and blocks left, the levers' tempo, moves and hesitations, the
  screen (HUD, zoom, cursor) and the hidden clock's captions (round 2 case 05: a revision's normal tempo cut 78% play
  to 51%; case 09: "the 2 seconds cannot be seen" turned the clock back on); a pacing miss re-runs the same levers,
  corrected by the take's measured rate, and so does a take whose play fell 1.5 s or more under the planned seconds
  (`guided.play_again`: the rate stays pinned, the moves and blocks are derived again).
- A guided revision keeps what the reference set (`brief.reference.set`; `guided.pin_reference`) unless the miss
  fed back is that field's own reference row or an asked fact about it, and logs "the reference's board is kept";
  the length always (a part-length miss is fixed with the timing fields); the values are the base version's adapted
  ones, and a "Reference: the board" miss does not unpin them (a new take fixes it); when the play is too short
  (`guided.play_too_short`: "gameplay at the centre" failed, or under 60% of the reference's play) the blocks rise by 3
  (at most 10) and the size by up to a cell a side: "the reference's board was too small to fill the play".
- The rows of an aspect the request left open and the reference filled (`prov["filled"]`: the ending, the purposes
  in order, the part lengths, the board, the screen) are computed as for a focus and then turned to `info`
  (`audit._as_filled`): "filled from the reference (the request left it open); not judged (it matches / it differs):
  ..."; they were not asked, so they never fail. A request naming the cursor alone gets an info screen row.
- A row an aspect of the focus does not cover is `info`; with the parts dropped (`parts_dropped`), the purposes and
  part-length rows are `info` with the reason. The misses feed the revise loop (`MAX_REVISIONS = 2`)
  like the text rows; a revision that comes out identical is "unchanged", never a failure.

### 3.5 The measured reliability of the reading (12 own creatives, neutral names, 2026-10-16)
The tool's reader as it is now (Gemini first, the ending's second read, `mapped_ending`'s checks), on a fresh pass
(`READING-ACCURACY-v8.md`): ending 12/12 (also 12/12 on v7), hook, call to action, captions and mechanics 12/12,
mistakes 8/12, structure 9/12 (40 of 45 boundaries within 1 s, mean error 0.4 s), pacing 5/12; second read median
14 s (3.9-111 s, 12 clips in parallel on the free tier), every reading answered. Without the second read the ending was 9-10 of 12 (v5, v5b, v6).
The choice of reader, whole-clip read only: Gemini 3.5 Flash-Lite with low thinking (`READING-ACCURACY-gemini.md`)
against NVIDIA super-vl (`READING-ACCURACY-v4.md`), the same pipeline and truth:
| field | Gemini | NVIDIA |
|---|---|---|
| ending (whole clip only) | 12/12 (9-10 on later passes) | 9/12 |
| hook, call to action, captions | 12/12 | 11/12 |
| mechanics (no false claim) | 12/12 | 12/12 |
| mistakes | 9/12 | 7/12 |
| structure | 8/12; 37 of 44 boundaries within 1 s, mean error 0.5 s | 5/12; 1.3 s |
| pacing | 5/12 | 6/12 |
| time per reading | 4-26 s, no errors | 50-250 s, HTTP 500s and reasoning loops |
- The board (2026-10-17, `READING-ACCURACY-v9.md` re-scored and `-v9b.md` a fresh pass after the last rule; the
  truth from each creative's level.json and brief; the still's board): shape 12 and 10 of 12, size within a cell
  10 and 12, blocks within two 11 and 12, colours (at least half each way) 12 and 12; gates' sides 7 of 12; busy
  against the level's difficulty 1-2 of 12. Before the hourglass and door sentences were sharpened, every
  hourglass read as a door (shape 4 of 12, `-v9-first.md`). The rest of the reading held: ending, hook, CTA,
  captions, mechanics 12/12; mistakes 10 and 7, structure 10 and 7 of 12 (37-39 boundaries of 46-50 within 1 s),
  pacing 2 and 4 of 12. The still read takes 1-2 s, 31 or 72 s when it waits out HTTP 429 on the free tier.
- The owner's test reference (another game's 15 s landscape ad, about 12 blocks on a 6x6-7x7 open board, six
  colours, four bubbles): the whole clip read 5x5 or 6x6 with 7 blocks and no obstacles; the still 6x6, 13
  blocks, six colours, the bubbles (not used). The brief: an open 6x6 board, 9 blocks (the most a 6x6 board
  takes with varied pieces), six colours, varied pieces; the difficulty is the generator's default for its ending.
- The owner's three references (`READING-ACCURACY-refs-v1.md`, 2026-10-17: cbj_trailer_2, cbj_trailer_3 and
  another game's ad, each with "create a similar game in CBJ", hand truth from frames): ending,
  structure, captions, HUD level and clock, board shape, size, blocks, colours, gates and "not used" right on all
  three (structure and captions judged on the trailers only); which game, 2 of 3 (the HUD-less close-up read as "a
  brick puzzle game"). The reader lists more colour names than colours (twelve for seven; "cyan" beside "blue"),
  so a surplus name can take an odd free colour. The trailer that lost its whole reading before now reads in full:
  CBJ, Level 25, 01:05, a 4x7 board with one inner wall, 10 blocks, teal/magenta/purple/green to
  blue/red/purple/green, gates on two sides, boosters not used, stopping mid-level.
- Reliable (rows that can fail): the ending, the hook, the call to action, the captions, the mechanics, and the
  board's shape, size, blocks and colours.
- Approximate (informational unless asked, then judged with tolerance): the mistakes, the part timings (snapping
  to cuts moved boundaries to 0.07 s mean error with NVIDIA), the pacing; the board's gates and busy (never
  judged; busy is shown as info and never sets the difficulty).
- Useless as a gate: the confidence (0.9-1.0 on every reading, wrong ones included).
- Free tier: Google may use free-tier content to improve its products (not for UK/EEA accounts); 3.7 and 3.8 Flash
  answered 503 "high demand" and 3.6 Flash hit the free quota on 2026-10-16, hence Flash-Lite alone, then NVIDIA.
- The file name is part of the format facts the plan sees: test inputs carry neutral names.

**Common to every workflow (2026-10-19).** The translation once, the rules rows and the shared case rows on every version,
the best version kept, the stated values kept, the length guard, the viewer-only rule, the repeated-miss limit, the fixed
board's pace said at plan time, the kept log lines, the feedback step and the report: listed once in `cbj-creative-evidence`
section 3 ("Common to every workflow") and in `src/cbj/workflows/__init__.py`.

## 4. Procedure

1. Confirm the input: a prompt and a file. No prompt: ask for one. A video over 120 s: refuse with the reason.
2. Decide the workflow by the uploads and the words (3.1). Log the decision.
3. Read the file for the request (3.2), logging the format, the plan with its why, the validation, the parts.
4. Plan the brief with the reading, then apply the focus rules (3.3) in code; write the provenance.
5. Make the creative with the shared engine (level, solve, play in Unity, compose), review as a viewer, run the
   guided evaluation, feed the misses back at most twice.
6. Show the "Reference to creative" card: file, focus and level, seconds analysed, confidence, validation, the
   plan (why, looked for, ignored, fixed by the request), the timeline with the model's own seconds and the cuts,
   adapted, not copied, the board read and what was taken, mechanics translated, "Not used: not in Color Block
   Jam", the composed prompt in a fold.
7. For a test: measure the reading on the 12 own creatives first (`req4-e2e-2026-10-16/reading_accuracy.py`,
   neutral names); only then run the creative set; use own creatives and synthetic footage only.

## 5. Not possible here

- Reading a link (a Facebook Ads Library page, a YouTube URL): uploads only; the link input is a deferred
  appendix of the spec.
- Copying the reference's frames, assets, sound or exact captions into the creative; repainting the blocks from
  a video; any image or video generation or editing in this workflow. (The BOARD of the video is copied since
  2026-10-19 when asked: a cell reading of its first frame, never its pixels.)
- A copied board the solver cannot settle in its budget (about 20 s; a 16-block 8x7 close-up may exceed it): the type
  path with the reason said. A colour the game lacks takes the nearest free slot by RGB and hue, said; two reference
  blues cannot both be blue.
- Exact timings from the model: the server samples a fixed set of frames (about 2.6k prompt tokens for 30, 65
  and 130 s alike), so part boundaries are within about 1-2 s and the pacing is approximate.
- Counting moves from the video: the per-third counts are plausible only sometimes; they set the tempo word
  only when plausible and never the pace change.
- A reading of a second attached video: noted, not applied.
- Reading a video with the Claude CLI contact sheet: videos are read by Gemini, then NVIDIA build.

## 6. Evidence

- The version record: `studio/<id>/v<N>/version.json` (`workflow: guided`, `brief.reference`,
  `brief.planner.references[i]` with plan, ask, notes (with ending_whole and ending_read when the second read ran),
  facts, pacing, validation (status "passed without the parts" when they were dropped), parts_dropped, read_all,
  applied, separated, ending_read, board_read (with notes.board, notes.board_whole, notes.hud, notes.extras_seen),
  reader, model, usage, errors, seconds; `brief.reference.board` and `not_used`; `checks` with the "Reference: ..." rows,
  "Reference: the board" among them; `evaluation.groups` including "reference").
- The job log lines: "reading plan: ...", "format: ...", "validation: ... (read by gemini: ...)", "ending: the last
  10 s read agree ..." or "... say X ...; the whole clip said Y: the last seconds win" or "ending: not read again
  (...)", "board: an open 6x6 board, 13 blocks in 6 colours (...), ...; obstacles (not used: not in Color Block
  Jam): ... (read on a still at 0.3 s, 1280x720)" or "(the whole clip's; the still: <error>)", "parts: separated
  ..." or "not separated", "reference to creative: ... adapted ...; not copied ...".
- The reading accuracy tables and the raw readings: `~/cbj-work/req4-e2e-2026-10-16/READING-ACCURACY*.md`,
  `readings*/<case>.json`.
- The end-to-end run: `~/cbj-work/req4-e2e-2026-10-16/PROMPTS.md`, `run.py`, `results/<case>.json`,
  `creatives/<case>/` (every version's ad, poster, board, brief, version record, `checks.md` with the reference
  block), `INPUT-NAMES.md` (the neutral names).
- Unit tests: `tests/test_videoref.py` (the plan, the format step, the checks, the parts, the ending's second read
  and `mapped_ending`'s rules, each focus, the words rule, the rows, the client split; the board: the fixed question,
  the word table, `stated()`'s level words, the colour mapping, the clamping, the apply with nothing stated and with
  the request's own shape/size/difficulty, another game's bubbles as 0 blocks, no wall and three "not used" lines,
  the own grey walls as walls, the still's second read, the board row; 2026-10-17: the trailer fixture
  `tests/data/trailer2_rejected_reading.json` now accepted and the brief-10 wrong unit still rejected, the parts
  dropped alone, a level-none request read and nothing applied, the general questions, the crop of a small board,
  the box in any unit, distinct colours, the HUD's label and clock, boosters not used; round 3: the brief's range as no
  length, the length from the play, a long hook as play, the solve and breathe words, chain captions, mistakes from the
  parts only, the speeds-up fill, the reader order, the still's budget and the board step's wall clock), `tests/test_gemini.py` (the Gemini request, the backoff, the usage, the missing
  key, the fallback to NVIDIA), the dispatch tests in `tests/test_app.py`; `tests/conftest.py` keeps every unit test
  off the real Gemini API.

## 7. Change rules

- A change to what a focus may take, to a row's rule, to the reading schema or to the models is made in the
  code, its unit test, this skill (3.3, 3.4, 3.5) and the rules document in the same edit; bump `last-verified`.
- A schema or prompt change is followed by a new reading pass on the 12 own creatives and a new accuracy table
  (v-next) before the creative set is run again; a field's row may be made failing only when the field is
  reliable on that table.
- `workflows/create.py`, `workflows/edit.py`, `rules.py`, `solver.py`, `render.py` and the compositor's patching
  are never changed by work on this workflow; the shared vision client keeps the edit side's model order and
  budgets, and only `reference.video_client` differs.
- No material from any other project is used as a reference or an input in the brief's tests.
