---
name: cbj-controlled-editing
description: Core requirement 5 of the Color Block Jam case in cbj-creative - how a follow-up prompt on an approved creative changes only what it asks: the edit whitelist of declared field groups, the smallest re-run (compose only, the same job filmed again with a new look, a board edit keeping the maximum valid prefix of moves, or new play closest to the original), pinned timing, replacements drawn in the replaced thing's box, the asset inventory, undo by version history, A/B variants and branches from one base, idempotence, the identical-result guard, honest refusals, and the nine-row edit report with its kept / asked / side-effect / NOT ASKED statuses. Use when planning, writing or judging any edit of an existing creative, when a test expects preservation, and when deciding whether a change must be refused.
metadata:
  spec-version: "1"
  last-verified: "2026-10-19"
---

# Controlled editing

## 1. Purpose
"If a user likes an existing creative and asks for one specific change, the system should avoid unnecessarily changing
everything else ... preserve gameplay, timing, camera, composition, sequence, visual structure and other assets."
An edit here is a change to the stored creative, not a new generation, and the result is proven item by item. This
skill is the contract an editing agent and an auditing agent share.

## 2. Source of truth
- `src/cbj/studio.py` `make()` (the stages and what re-runs), `_changes_only`, `board_edit`, `_same_moves_new_board`,
  `history()`, `part_lengths()`; `src/cbj/brief.py` `merge` + `GROUPS` + `PRONE`; `src/cbj/planner.py` edit post-rules
  (`_undo`, `_no_timing_drift`, `_timing_by_numbers`, `_recolour_keeps_board`, `_no_obstacles_to_remove`,
  `_relative_difficulty`, `_impossible_locks`, `_one_background`, `_missing_attachment`, `_place_unplaced`);
  `src/cbj/boardedit.py`; `src/cbj/editreport.py`; `src/cbj/edits.py` (inventory, direct edits); `src/cbj/ad.py` (pins);
  `src/cbj/parts.py` (the parts manifest every version writes) and `src/cbj/route.py` (the edit's type and analysis
  level, decided before planning; `verify` after it; `match_upload` for an attached MP4; `locate_with_vision` optional).
- `docs/ENGINE-NOTES.md` (the former root README) "Controlled editing"; reports `~/rollic-case/CONTROLLED-EDITING-REPORT-2026-10-12.md` and
  `~/rollic-case/CC-SCENARIOS-REPORT-2026-10-14.md` (45 scenarios: 34 tested, 34 pass, 11 skipped).
- Acceptance rules an auditor applies: [references/acceptance-rules.md](references/acceptance-rules.md).

## 3. Facts
**Only the asked groups change.** The planner reads the edit against the current brief, the list of things in the ad
(inventory with plain names and screen times), the ad's parts and their lengths, and what each earlier version changed.
It declares the field groups the request changes; `merge` takes only those, and for groups a model over-fills only with
words in the prompt that ask for them. Pictures merge slot by slot, so replacing one never drops another. Everything
not mentioned keeps its current value, including the level file by name (the HUD number stays).

**An edit keeps the version's own film.** `_same_play` ignores the recording key's version fields (`play`, `deliberate`):
an edit whose ask does not change the play reuses the approved recording even after the player or the pacing changed
(a picture edit once re-recorded a whole ad and the report said timing and sound changed, 2026-10-15).

**Route first, then plan.** Every version writes `parts.json` (parts, captions, pictures, sound, music with seconds,
boxes and fields; the gameplay's moments on the ad's clock; when the timer shows each whole second). `route.decide`
reads the request against it before any model: Level 0 direct (a known layer; with the value in the request the edit
is made in code, no planner), Level 1 targeted (a moment placed from the clock readings, moments and parts; a
multimodal contact-sheet read only when the metadata cannot place it, optional), Level 2 full (a video the tool did not
make). A play change is a retake; a play change plus "keep every frame" is a conflict. After the planner, `verify`
restores level, move, clock and length changes on a route that does not change the play (and upgrades a "planner"
route to a retake when the planner read a play change in an unrecognised clause). The report's `route` chip says
whether the result followed the route. An attached MP4 that is one of the tool's versions is matched by its bytes and
edited from its metadata; no video analysis is run on the tool's own creatives (2026-10-15).

**The smallest re-run.**
| what changed | what runs | proof |
|---|---|---|
| copy, captions, caption colours, sequence, assets, music, format | compose only, same recording; when every changed layer keeps its frame window, the approved MP4 is patched: only the GOPs holding a changed frame are drawn and encoded again, the rest are its bytes (`compose.render(patch_from=)`, `compose.json` `patched`) | frame diff: changed frames inside the edited layers' boxes; sound-effect stem hash identical for music-only; the report adds "N of M frames are the approved video's bytes" |
| colours, background (colours or picture), HUD, zoom, level number | the stored job (same moves, same frames) filmed again with the new look | game state identical on every frame; rendering noise is not a change |
| board edit (move a door, add or remove a wall) | the longest start of the old play still legal on the new board is kept move for move; the rest re-solved; if every move survives, the same job is replayed on the new board and the timing is pinned | `level_edit`: what changed, kept N of M moves, replay proves no overlap |
| gameplay, difficulty | recorded again; on a kept level the play closest to the original (of up to 24 plans, most moves in common); "harder / easier" edits the same board with at most 3 small changes | the report says how many moves were kept; gameplay row asked, timing/sound side effects explained |

**Timing is pinned.** An edit that keeps the gameplay frames pins the original's intro, replay and length. Removing the
replay gives its time to the end card instead of shifting the gameplay; freed time never becomes a replay nobody saw.
The still opening frame and the held result have lengths an edit can set (the ad's end moves by the same time); a
caption's entrance or exit can move; a punch-in can run for a stretch (eased, never cropping the HUD or the board).
Numbers that only restate the current lengths (2.57 s written as 2.6 s) are not a change.

**Picture slots.** The logo or sticker in the top-left corner, the sticker in the top-right corner (its own slot, so two
corner stickers coexist), the icon beside the hook, the end-card picture, the end card's background, the button, the
cursor, and the obstacle (a picture drawn on the board's walls in perspective during the play: "use this object instead
of the current obstacle"; `compose.cell_quads` fits the cells to the screen from the recorded block positions; on a
board without walls it goes beside the hook with a note), and the skin (a texture on ONE block of a colour: "apply this
ice texture to the blue block"; `compose.block_quads` maps the block's logged screen position on every frame back to
cells through the inverse homography and `draw_on_quad(mode="multiply")` draws the lightened texture on its cells, so it
follows the block, its lift and its exit; `planner._skin_on_a_block`; a door or gate stays refused; 2026-10-15). The
inventory names each; a replacement fills the same slot.

**Colour words resolve on the creative (2026-10-19).** `brief.slot_of_colour_word(word, brief, used)`: the name a slot is
shown in first ("the cyan block" on a footage-coloured copy = the green slot), then the game's own name when that slot is
shown as itself, then the nearest shown shade (videoref.COLOUR_RGB: teal, magenta, light blue), only among the slots on the
board. `route.decide(colour_of=...)` and `planner._skin_on_a_block` use it; `workflows/edit.plan` builds it from the version's
brief and level. A colour word that names nothing shown is refused as before.

**The object and the texture are on every board part (2026-10-19).** `ad.BOARD_PARTS` = intro, play, replay, teaser,
question, result_hold; `compose.card_base` draws them on a cliffhanger end card's board picture too and appends the boxes,
so the pixel proof stays inside the layer (E2: the wall "turned back" on the frozen question and the end card).

**A plain-background picture becomes a sticker.** `draw.cutout` (a corner flood fill, no model) makes a generated picture's
white or flat background transparent and trims it, for every slot but the wall tile and the backgrounds; the slot then
sizes it by what is drawn.

**Replacements keep the composition.** A new picture is drawn inside the box of the one it replaces (end-card picture,
icon beside the hook, button, logo in its corner); a wide logo is fitted into the square slot. "This asset", "the coin
pile", "the clock icon", "the button" resolve through the inventory; "everywhere it appears" replaces every slot showing
it; "the closing logo" on an ad whose only logo is the end-card picture is that picture.

**A prompt that describes another board** (its blocks, size, shape, pieces, look or difficulty) while naming colours
gets a new board in those colours; only a colour change alone ("make the red block purple") is a repaint that keeps
the board.

**History.** Undo / revert a change = the value it had before that change, taken from the version history; "do not
undo X" is not an undo; undoing one edit never reverts another. Any version can be edited (`--base`), so A/B variants
and branches are two requests from the same base, each carrying only its own change. The same absolute request sent
twice changes nothing (refused as already applied). A result identical to its parent is detected after it is made and
not kept as a version.

**Refusals (honest, with the reason and what to change instead).** A request that changes the puzzle while locking the
board, the moves and every frame (a contradiction); a picture, texture or sprite on a block or a door; a decorative
border or frame; a dissolve or wipe the ad does not have; a file that is not attached (asked for, never guessed from
earlier uploads); a board change that would leave the level unwinnable or has no tile to use; "which of the two red
blocks" when the ask cannot apply anyway.

**The edit report** (`editreport.py`): nine rows, Gameplay, Timing, Camera, Composition, Sequence, Visual structure,
Other assets, Captions, Sound. Each row is kept; changed, as asked; changed because of the asked change (only when a
check on the measured difference proves the reason, e.g. "every drag on the same frame; the win screen comes N frames
earlier", "the effects follow the parts the asked change moved"); or CHANGED WITHOUT BEING ASKED, which fails the edit.
Exact facts first (level hash, every move, frame windows, file hashes), then the frame diff (frames changed, which
layers, every changed pixel inside the edited layers' boxes). Verdict: "Only what was asked changed (...); everything
else is identical", or the side effects named, or the failure.

**A designer's edits, proven 2026-10-15** (base: a hard level with walls, a logo top-left, a stopwatch icon beside the
hook, a near-fail, 30 s; four pictures generated with Higgsfield and dropped in as uploads):

| the request | what runs | what the report says |
|---|---|---|
| "Replace our logo with X.png" | compose only, the approved MP4 patched (the logo spans the play, so most GOPs are redrawn) | Only what was asked changed (Other assets); changed pixels inside the logo's box |
| "Use this object instead of the current obstacle" | compose only: the picture drawn on the wall cells; patched | Only what was asked changed (Composition, Other assets); pixels inside the walls' box |
| "Apply this ice texture to the blue block" | compose only: the texture drawn on that block's cells on every gameplay frame, following the recorded block | Only what was asked changed (Composition, Other assets); the block's moves, shape and exit untouched |
| "Put X.png on the end card instead of the coin pile" / "Use X.png as the button" | compose only; 1 of 10 GOPs rendered, 745 of 900 frames copied | Only what was asked changed (Composition, Other assets) |
| "Change the hook to ..." / "Change the mistake caption to ..." | compose only; patched when the new words fit the old window; a longer sentence keeps its reading time and the Timing row says so, as asked | Only what was asked changed (Captions, Composition [, Timing]) |
| "Make the background behind the board light mint" / "Make the red blocks pink" | the same job filmed again with the new look (35 s); game state identical on every frame | Only what was asked changed (Visual structure) |
| "Keep everything, but remove the logo" | compose only; the caption band widens back | Changed as asked: Other assets; also changed because of it: Composition |

Results: `~/rollic-case/case-test-2026-10-15/` (base.py, edits.py, edits_results.json, hf_assets/), creative
`1015-074810-create-a-hard-color-block` v1-v11.

**Common to every workflow (2026-10-19).** The translation once, the rules rows and the shared case rows on every version,
the best version kept, the stated values kept, the length guard, the viewer-only rule, the repeated-miss limit, the fixed
board's pace said at plan time, the kept log lines, the feedback step and the report: listed once in `cbj-creative-evidence`
section 3 ("Common to every workflow") and in `src/cbj/workflows/__init__.py`.

## 4. Procedure
Writing an edit prompt: name the one change; say "keep everything else exactly as it is"; point at things by the
inventory's names; attach the file and refer to it; for timing give the number or the direction ("two seconds longer");
for a board edit name the door's colour and side, or the tile by column and row (1-based from the bottom-left).

Judging an edit (an auditor):
1. Read `version.json`: `from` (the base), `edit` true, `proof.verdict`, `proof.rows`, `proof.pixels`, `level_edit`.
2. No row may be CHANGED WITHOUT BEING ASKED. Every asked row matches the request; every side-effect row carries an
   explanation that a check proved.
3. For a look-only edit: `pixels.frames_changed` and `layers` match the edited thing; for music-only: 0 frames and
   `same_sound` (effects stem) true; for a re-filmed look: the note says the frames differ by design and the game state
   was checked identical.
4. For a board edit: `level_edit.kept` of `of` moves, the change named; replay the move list against the new board.
5. For a refusal: no new version, the reason names the conflict or the missing thing, the parent is untouched.
6. Compare any two versions with `uv run cbj edit-report <id> A B`; `uv run cbj ad-diff` for the frame proof.

## 5. Not possible here
Everything in `cbj-prompt-controls` section 5. In addition, one request makes one version (A/B = two requests); a
sound effect cannot be swapped for a file; no voice-over; no per-block art; other aspect ratios are derived from the
9:16 master (captions keep their 9:16 places); a no-op that the planner does not catch costs one render before it is
refused; "the marked tile" has no marker, so the tool picks the tile on the route that keeps the most play (or the wall
whose removal eases the level most) and names it.

## 6. Evidence
- `uv run cbj make "<edit>" --edit <id> [--base N]`; `uv run cbj edit-report <id> A B`; `uv run cbj ad-diff`; the UI's
  *Compare* and *Things in this ad* (exact edits with no planner, same proofs; `/api/direct`).
- Harness: `~/rollic-case/case-test-2026-10-14/cc_cases.py` (`CC_TAG=<n> CBJ_OUT=<folder> uv run python cc_cases.py [ids]`,
  UI must run), `summarize.py <folder>`; results `results_cc6/` = the final 34/34 pass.
- Tests: `tests/test_editing.py`, `tests/test_control_cases.py`, `tests/test_case_fixes.py`, `tests/test_route.py`.
- The route of a planned edit: "What I understood" (the Route line) and `brief.planner.route`; the manifest:
  `/api/parts/<id>?base=N` or `studio/<id>/vN/parts.json`.

## 7. Change rules
A new planner post-rule, a new row explanation in `editreport.py`, a new refusal, or a new re-run path changes section 3
in the same edit and bumps `last-verified`. Keep [references/acceptance-rules.md](references/acceptance-rules.md) in step
with `editreport.py`'s rows.
