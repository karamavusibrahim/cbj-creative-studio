# Edit test set 2: five one-change requests on today's video-reference creatives (2026-10-19 afternoon)

Why: the owner's next test is the edit workflow (case p.7, "controlled creative editing: one of the most important parts
of the case"). The creatives made this afternoon from the three reference videos had never been edited; the case's own
example wordings were put on them, one change each, one asset slot or re-run tier each. Everything below was run
in-process through the edit workflow (`run.py`: `edit.plan`, then `edit.make` with the viewer's review and the loop on),
and every intermediate step is in `results/<id>.json`: the route decided in code, the planner's declared groups and what
the route check restored, the brief's assumptions and control rows, the stages and their seconds, whether the recording and
the level were reused, the drags compared with the parent's, the nine rows of the edit report, the frame diff and the
patched byte count, the viewer's review, any revision, and the invariants every case must hold. `creatives/<id>/` holds the
parent's and the new versions' ad, poster, brief, level and edit report; `COMPARE.png` the parent beside the edit at the
moment the edit shows. The prompts: `PROMPTS.md`. Runs: `plan-r1.log` (all five planned, no make), `run-r1.log` (E1 E2 E3),
`run-r2.log` (E2 again, E4, E5 on the fixed code), `run-r3.log` (the final pass of all five on the final code).

## 1. What the case asks, and what the workflow does with a request (read before the table)

p.4 "Keep this creative exactly the same, but replace this object with the attached asset"; p.6 "Use this object instead of
the current obstacle"; p.7 "I like this creative. Keep everything exactly the same, but replace this asset ... preserve
gameplay, timing, camera, composition, sequence, visual structure, other assets ... rather than regenerating an entirely
different video after every request".

1. **Route, in code, before any model** (`route.decide`): the request against the version's parts manifest (every part,
   caption, picture slot, moment and clock reading with its seconds). A known slot with its new value in the request is a
   *direct edit*: the brief is changed in code, no planner at all (E2, E3, E4). Otherwise the planner reads the request
   against the current brief, the inventory, the history and the route, and declares only the field groups the request
   asks for. The merge applies those groups and nothing else: every unrelated field keeps the value the user approved
   (`brief.merge`; the whitelist is the guarantee, not a repair). A dependent change (a caption that waits for a longer
   hook, a win screen that comes earlier) is accepted only when a measured check proves the reason (`editreport`); the
   route check is a second, deterministic verification that no level, move, clock or length changed on a route that does
   not change the play (`route.verify`).
2. **The smallest re-run** (`studio.make`): the level is kept by file when the edit is not about it; the recording is reused
   when the play is the same; a look change films the same job again with the same drags. Captions, pictures, sound and
   music are updated by layer-based compositing on the same recording, never by regenerating gameplay: the unaffected
   layers, the timing and the camera stay exactly as approved. The delivered MP4 is rebuilt only in the GOPs that hold a
   changed frame; the other GOPs are copied from the approved file (every segment and layer boundary starts a GOP, so this
   holds by construction, and the report counts the copied frames).
3. **The proof** (`editreport.report`): nine rows against the parent, each kept / asked / explained by a measured check /
   CHANGED WITHOUT BEING ASKED; then the frame diff: which frames, which layers, and whether every changed pixel is inside
   the edited layers' boxes.
4. **The viewer and the loop**: the viewer reviews the edit against the request; a revision runs at most twice and may
   only touch the asked groups or put an unasked change back.

The invariants the harness checks on every case (nothing regenerated): the level's sha is the parent's; the drags are the
parent's; the recording folder is the parent's (or, for the re-film tier, a new film with the same drags on the same
frames); no row changed without being asked; the asked row changed; the length, the captions and the colours are the
parent's; for a compose-only edit the changed pixels are inside the edited layer's box and the approved video's bytes are
kept where nothing changed (a layer on every frame, the cursor, leaves no GOP to copy: not required there).

## 2. Each case, step by step (what the workflow did, what the proof measured, what the viewer said)

**E1. "Keep this creative exactly the same, but replace this object with the attached asset." (toy_dice.png on the
trailer 3 copy, 48 s, 16 blocks, a stopwatch on the end card).** Route: nothing named, so the planner (Level 0, no video
analysis) with the inventory. The planner read "this object" as the stopwatch on the end card, "the only object picture in
the ad", and wrote the alternatives (the walls, which this board does not have; the hand cursor); declared group:
pictures. Route check: nothing restored. Stages: level 0 s (the parent's file kept), recording 0.4 s (the parent's
recording reused, 27 drags identical), compose 3.3 s, proof 5.6 s. Report: Other assets asked (stopwatch -> dice), the
other eight rows kept; 104 of 1440 frames changed, all inside the end-card picture's box; 1336 frames are the approved
video's bytes (1 of 8 GOPs rendered). Viewer: ship, nothing "not as asked"; its taste remark (a dice does not connect to a
near-miss) is about the asset chosen, not the edit. No revision. (This run wrote the guess twice, once by the planner and
once by the code's own "this object" note; the code's note now stands down when the planner has explained it.)

**E3. "I like this creative. Keep everything exactly the same, but replace the pointing hand with the attached pointer."
(blue_fingertip_pointer.png on the trailer 2 copy with Level 25, the 1:05 clock, the footage colours and a cliffhanger).**
Route: the tap cursor, the new value attached: a direct edit, no planner (0.0 s). Stages: level 0 s, recording 0 s
(reused, 8 drags identical), compose 35 s (the cursor is on every play frame, so every GOP is rendered: nothing to copy),
proof 71 s. Report: Other assets asked (hand -> the pointer), Composition asked (the cursor placed or sized differently:
the new picture's own size), seven rows kept; 705 of 900 frames changed, all inside the cursor's box; the hook, the
question, the clock, the colours and the length untouched. Viewer: ship, nothing "not as asked". No revision.

**E4 (hard). "Apply the attached ice texture to the cyan block. Everything else stays as it is." (hf_ice_texture_tile.png
on the trailer 3 half-board, whose green slot is painted the footage's cyan).** First plan (`plan-r1.log`): the planner
understood ("the cyan block is the green slot, which this ad shows in cyan") but the code did not: the route's and the
planner's colour regex knew only the game's seven names, so no texture was placed and the visuals row said "a picture
cannot be put on a block", the old refusal. Fixed: `brief.slot_of_colour_word` resolves a colour word on the creative's own
shown colours (the shown name, then the game's name when the slot is shown as itself, then the nearest shown shade, only
among the slots on the board); the route and the planner use it. Second run: a direct edit, no planner; recording reused
(12 drags identical); compose 36 s; report: Composition asked (added: skin), Other assets asked (none -> the ice tile),
seven rows kept; 659 of 900 frames changed inside the texture's box; 241 frames the approved bytes. The texture is on the
cyan L block and follows it (checked by eye at full size, `_frames/E4_crop.png`); the colours row is unchanged. Viewer:
ship, nothing "not as asked", "the barely visible ice": the multiply blend keeps the block's colour identity by design
(a crate texture once made a blue block read black), so a pale tile on a pale block is faint. A limit, said below.

**E2. "Use this object instead of the current obstacle." (boulder_object.png on the owner's trailer 2 copy: 5x7 with a
real two-cell wall, footage colours, Level 25, a cliffhanger).** Route: the obstacle slot named, the file attached: a direct
edit, no planner. Recording reused (7 drags identical), compose 31-40 s, the boulder drawn on the wall cells in perspective
from the recorded camera. First run (`run-r1.log`, v2): the report said "only what was asked changed" and every pixel was
inside the walls' box, yet the viewer saw the flaw the report could not: from 0 to 21 s the wall is the stone, then on the
frozen question (22-23 s) and in the board picture on the end card it "goes back to the old plain dark pillar ... feels like
a glitch". The object layer ran on the play only. Fixed in two places: the layer covers every part that shows the board
(`ad.BOARD_PARTS`: the still opening, the play, the replay, the teaser, the frozen question, the held result), and the end
card's board picture is drawn with the object and texture layers too (`compose.card_base`, boxes recorded). Second run
(`run-r2.log`, v3): the question showed the stone, the end card still did not: the patched render had copied the end card's
GOP from the approved video because no layer window touched it. Fixed: a changed wall picture or texture marks the GOP of a
card with a board picture dirty (`compose.patch_plan`, tested). Third run (`run-r2b.log`, v4): the stone on the play, the
question and the end card's picture (`_frames/E2_v4_check.png`); 900 of 900 frames changed (the end card too), all inside
the layer's boxes; Composition and Other assets asked, seven rows kept; the viewer: ship, nothing "not as asked". The
proof's 1577 s is contention: it composited both versions frame by frame while the unit suite and E5's film ran.

**E5 (re-film tier). "Keep the board, the moves, the clock and the captions exactly as they are; only put the attached
picture behind the board." (hf_autumn_forest_style.png on the LolTap copy, 45 s, a cliffhanger with "Which one goes
first?").** Route: the planner (Level 0): the picture goes to the background behind the board (an assumption says it is not
the end card's background); declared group: the background; nothing restored. The level kept by file; the stored job
filmed again by the game with the picture behind the board (66 s): "re-filmed 1200 frames; game state identical to the
original on every frame"; the same 11 drags on the same frames, so the ad's timing is pinned; compose 1555 s (the same
contention). Report: Visual structure asked ("the game's own -> the picture ...; recorded frames: 0 of 1200 identical", by
design), eight rows kept; frames not compared pixel by pixel (a re-film differs everywhere by design; the game state is the
proof). Viewer: ship, nothing "not as asked". The one measured miss, "a real choice at the cut: 1 block left", is the parent's
(V6's prompt asked for one move left); the loop put it to the planner, which rightly found nothing to change in an edit
about the background, so no revision was made: the edit did not touch the play to fix a flaw it was not asked about.

## 3. The table (final version of each case; E1 from run-r1, E3 and E4 from run-r2's code state, E2 from run-r2b, E5 from run-r2)

| case | creative | request | how it was read | what ran | the report | verdict | invariants | viewer |
|---|---|---|---|---|---|---|---|---|
| E1 | 1019-125939-the-board-exactly-as-shown v1 -> v3 | Keep this creative exactly the same, but replace this object with the attached asset. | planner (claude-cli/opus), route planner; declared: the pictures | recording reused; recording 0.4 s, compose 3.3 s, proof 5.6 s | Other assets: asked; 104 of 1440 frames, layers ['end_art'], inside the box: True; 1336 of 1440 frames the approved bytes | Only what was asked changed (Other assets); everything else is identical. The video itself was patched: 1336 of 1440 frames are the approved video's bytes, 1 of 8 GOPs were rendered again. | 11/11 | ship: as asked |
| E2 | 1019-113515-use-same-game-design-same v1 -> v4 | Use this object instead of the current obstacle. | direct, no planner; declared: the pictures | recording reused; recording 0 s, compose 40 s, proof 1576.7 s | Composition: asked, Other assets: asked; 900 of 900 frames, layers ['obstacle'], inside the box: True | Only what was asked changed (Composition, Other assets); everything else is identical. | 10/10 | ship: as asked |
| E3 | 1019-124726-use-the-same-game-design v1 -> v2 | I like this creative. Keep everything exactly the same, but replace the pointing hand with the attached pointer. | direct, no planner; declared: the pictures | recording reused; recording 0 s, compose 35.3 s, proof 71 s | Composition: asked, Other assets: asked; 705 of 900 frames, layers ['cursor'], inside the box: True | Only what was asked changed (Composition, Other assets); everything else is identical. | 10/11 (broken: the approved video's bytes kept where unchanged (patched)) | ship: as asked |
| E4 | 1019-120353-take-only-half-the-blocks v1 -> v2 | Apply the attached ice texture to the cyan block. Everything else stays as it is. | direct, no planner; declared: the pictures | recording reused; recording 2.1 s, compose 35.7 s, proof 71.9 s | Composition: asked, Other assets: asked; 659 of 900 frames, layers ['skin'], inside the box: True; 241 of 900 frames the approved bytes | Only what was asked changed (Composition, Other assets); everything else is identical. The video itself was patched: 241 of 900 frames are the approved video's bytes, 5 of 7 GOPs were rendered again. | 11/11 | ship: as asked |
| E5 | 1019-130745-same-board-as-this-ad v1 -> v4 | Keep the board, the moves, the clock and the captions exactly as they are; only put the attached picture behind the board. | planner (claude-cli/opus), route planner; declared: the background | filmed again, same drags on the same frames; recording 65.6 s, compose 1554.8 s | Visual structure: asked; the gameplay was filmed again with the new look, so its frames differ by design | Only what was asked changed (Visual structure); everything else is identical. | 10/10 | ship: as asked |

The per-stage seconds above were measured while the unit suite, E5's film and E2's proof shared the machine: E1's 3 s
compose and 6 s proof are the uncontended numbers; the 1555 s compose and 1577 s proof are contention, not the edit.

## 4. What the test caught that the proof alone did not, and what changed in the tool

| defect | seen by | fixed in |
|---|---|---|
| a texture asked on "the cyan block" of a footage-coloured copy refused as "a picture cannot be put on a block" (the colour regex knew the game's seven names only) | the plan-only pass (E4): declared groups empty, visuals row not_supported | `brief.slot_of_colour_word` (shown name, then the game's name when shown as itself, then the nearest shown shade, among the board's slots); `route._target_picture(colour_of)`; `planner._skin_on_a_block`; `workflows/edit.plan` builds colour_of from the version's brief and level; tests |
| the wall picture on the play only: the plain wall came back on the frozen question and on the end card's board picture | the viewer (E2 v2): "feels like a glitch"; the report's rows and pixel box were all green | `ad.BOARD_PARTS` for the object and skin layers; `compose.card_base` draws both on a card's board picture and records the boxes; test |
| the patched render copied the end card's GOP, so the fixed layer still did not reach the end card | the frame check by eye (E2 v3: `_frames/E2_check.png`) | `compose.patch_plan`: a changed object or skin layer marks a card with a board picture dirty; test |
| "this object" explained twice (the planner's reading and the code's note) | the plan record (E1) | `planner._note_guessed_slot` stands down when the planner has said how it read "this object" |
| the likeness viewer of the video workflow counted dropped bubbles and the colour mapping as differences (V6) | the video run r11 | `imageaudit.LIKENESS_ASK` says both do not count |
| V2's fourth video run built a board of the type: the translation dropped "as it is" | the video run r10 | `videocells.BOARD_FROM`: a copy verb on THE board of THIS video is a copy; test |

What the harness measured on every final version: the level sha identical to the parent's (5 of 5), the drags identical (5
of 5), the recording reused (4 of 5) or filmed again with the game state identical on every frame (E5), no row CHANGED
WITHOUT BEING ASKED (5 of 5), the changed pixels inside the edited layer's box (4 of 4 compose-only edits), the length, the
captions and the colours identical (5 of 5), no revision needed (5 of 5). Nothing was regenerated: no new level, no new
plan of moves, no new play.

## 5. Limits, stated
- A texture is a multiply blend that keeps the block's colour identity on purpose; a pale tile on a pale block (ice on cyan)
  is faint, and it is drawn cell by cell, so a faint seam shows between cells at full size. A stronger blend would make a
  dark texture turn a block black again (the 2026-10-15 finding). The viewer says "barely visible"; the report says what
  was drawn and where.
- A layer on every play frame (the cursor) leaves no GOP to copy: the edit is still pixel-local, but the MP4 is re-encoded.
- A re-filmed look (a picture behind the board) is proved by the game state per frame, never by pixels; its compose took
  26 minutes here only because three heavy jobs shared the machine.
- A flaw the parent had (one block left at a "which one goes first" cut) stays in an edit that did not ask about it; the
  loop names it and the planner rightly changes nothing.
- The edit workflow's viewer gives taste remarks ("a dice does not connect to a near-miss"); they are info, never a change.

## 6. Rerun of all five on the final code (`run-r3.log`, `results-r3/`, `creatives-r3/`, `_frames-r3/`)

The code had changed after the per-case runs above (the wall and skin layers on every board part and on the end card's
board picture, the GOP marking, the colour-word resolver); the five requests were run again, unchanged, on the final code,
with nothing else on the machine. Every case kept its result; no code was changed after this pass.

| case | version | route | ran | report | invariants | viewer | eye check (`_frames-r3/`) |
|---|---|---|---|---|---|---|---|
| E1 | v1 -> v4 | planner (the stopwatch read as "this object", said once) | recording reused; compose 3.6 s, proof 5.8 s | Other assets asked; 104 of 1440 frames in the end-art box; 1336 frames the approved bytes (1 of 8 GOPs) | 11/11 | ship, as asked | the dice replaces only the stopwatch |
| E2 | v1 -> v5 | direct, no planner | recording reused; compose 36.8 s, proof 78.6 s | Composition + Other assets asked; 900 of 900 frames in the obstacle box | 10/10 | ship, as asked | the boulder on the wall cells in the play, the frozen question and the end card's board picture |
| E3 | v1 -> v3 | direct, no planner | recording reused; compose 35.8 s, proof 73.4 s | Composition + Other assets asked; 705 of 900 frames in the cursor box | 10/11 (the cursor is on every frame: no GOP to copy, the documented limit) | ship, as asked | the pointer replaces the hand; Level 25, the clock, the colours untouched |
| E4 | v1 -> v3 | direct, no planner (cyan -> the green slot shown as cyan) | recording reused, 12 drags identical; compose 36.4 s, proof 69.9 s | Composition + Other assets asked; 659 of 900 frames in the skin box; 241 frames the approved bytes | 11/11 | ship, as asked | the ice on the cyan L block, faint by design |
| E5 | v1 -> v5 | planner, declared: the background | the same job filmed again (the earlier re-film with this look reused: same frames, 11 drags identical); compose 56.2 s | Visual structure asked, eight rows kept | 10/10 | ship, as asked | the forest behind the board on the play, the question and the end card's picture; "Which one goes first?" and the end card kept |

The one measured miss is E5's parent flaw (one block left at the cut), named and left alone as before. Uncontended, the
whole set took 9 minutes (the earlier 26-minute composes were machine contention).
