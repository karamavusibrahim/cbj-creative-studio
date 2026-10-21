# Controlled creative editing (core requirement 5): report

Date: 2026-10-12. Plan, with Fable 5.1's decisions: `CONTROLLED-EDITING-PLAN-2026-10-12.md`.
How to try it yourself: `CONTROLLED-EDITING-CHECK-STEPS.md`.

The brief (p.7): "If a user likes an existing creative and asks for one specific change, the
system should avoid unnecessarily changing everything else ... Preserve the original: Gameplay,
Timing, Camera, Composition, Sequence, Visual structure, Other assets. Only the requested element
should change where reasonably possible." And on p.10: "Controllability: can the user make
targeted changes without destroying the rest of the creative?"

## 1. The idea in one paragraph

An edit is a change to the stored creative, not a new generation. A creative is kept as stages:
the brief (what was asked, as data), the level file, the play script, the recording of the real
game, ad.json (the ad's parts and layers) and the video. An edit changes the brief only where the
prompt asks; each stage then runs again only if its inputs changed, and a stage that must run
again picks the result closest to the original (the closest board, the closest play). The ad
keeps the original's timing. Then an edit report checks the brief's seven items one by one and
fails the edit if anything changed that was not asked for.

## 2. What was built

(sections 2.1-2.7 below; numbers from the live runs in section 3)

### 2.1 The edit report: the brief's seven items, plus captions and sound

`src/cbj/editreport.py`. For each edit, nine rows. Each row has a status and the measured facts:

| Row | Measured from |
|---|---|
| Gameplay | the level file's hash; every drag from the game's own log (block, cells, outcome); "the first K of M moves are the same, N in common" |
| Timing | when each drag starts; each part of the ad (frames); when each caption is on screen |
| Camera | the in-game camera in the recorder's job; how each part is framed; the finger's path |
| Composition | where each layer sits and how big it is (the compositor's record of every layer) |
| Sequence | the ad's parts in order; the play's moments in order (mistake, hesitation, solve) |
| Visual structure | theme, block colours, background, board, HUD; the recorded frames' hashes |
| Other assets | every picture by the hash of its file (a re-upload with other pixels counts) |
| Captions | every text as shown, with the facts filled in |
| Sound | the sound track's hash |

Statuses: **kept**; **changed, as asked**; **changed, because of the asked change** (the reason
is written, and the engine's own note when there is one, e.g. "cap_mistake starts at 3.40 s so
it does not overlap another caption"); **CHANGED WITHOUT BEING ASKED**, which fails the edit.
Captions and placement are judged layer by layer: asking for a new hook is not asking for a new
button text. Then the frames: how many changed, which, and whether every changed pixel is inside
the boxes of the layers that changed.

### 2.2 "Replace this asset": the inventory

`src/cbj/edits.py`. Every version lists what it holds: the logo, the icon beside the hook, the
end-card picture, the button, the end card's background, the cursor, the sound and every caption,
each with a plain name, when it is on screen and where. Empty slots are listed too (no logo yet).
The planner gets this list, and the ad's parts ("this ad has no slow-motion replay"), with every
edit prompt, so "the coin pile", "the clock icon" or "this object" resolve to a slot.

- **Slot by slot.** Pictures merge per slot: replacing the end-card picture can no longer drop
  the logo (before, the assets were one all-or-nothing field).
- **An unplaced attachment** (the planner did not use it) goes to the slot the prompt names, else
  to the end-card picture, written as an assumption with the alternatives.
- **The same box.** A new picture is drawn inside the box of the one it replaces (the end-card
  picture: the default's drawn size; the hook icon: 110x110; a new button: the game button's box,
  with its text on top), so the layout stays.
- **Remove** works for the logo, the hook icon and the end-card picture.

### 2.3 Exact edits without a prompt

The UI's *Things in this ad* card: each picture with Replace (or Add) and Remove, each caption
with Edit, the sound with on/off. These change the brief in code: no model, no reading, the same
make and the same report. A picture swap takes about a minute (composing 900 frames plus the
proof), with no planner wait.

### 2.4 The ad keeps its timing (the pin)

`build_ad(pin=...)`. An edit that keeps the gameplay frames (the same recording, or the same job
filmed again with a new look) keeps the original's frozen intro, replay and length. A removed part
gives its time to the end card; an added part takes it from there. Beyond the end card's limits
(3 s, 10 s) the ad's end moves, never its gameplay, and the brief says so.

Before: removing the replay turned the freed time into a 2 s frozen intro, so every gameplay frame
moved 2 s, and on three of the four stored recordings the ad's length also changed (26-29 s)
without being asked.

### 2.5 Gameplay edits keep the moves (the closest play)

A gameplay edit on a kept level ("add a second mistake") re-plans the moves. Of up to 24 plans
(one per seed) it keeps the one closest to the original: the longest run of identical moves from
the start, then the most moves in common in order. The seed goes into the brief, so the recording
can be made again. Solved positions are now cached in the planner, so the search is cheap: on the
live level the first two plans took 7-8 s each and the next ten about 0 s.

### 2.6 Difficulty edits keep the board (the closest board)

"Make it harder" or "easier" edits the board the user is looking at: a search over small changes
(move a block, move a gate, swap two blocks' colours; at most 3), keeping the shape, size, pieces
and number of blocks. Fewest changes first, then reaching the asked band, then the biggest step.
The result must stay fair and solvable on the full 200-run rating. The report says what moved
("the same board with 1 gate moved (7 of 7 blocks as they were)").

"Harder" is read relative to the version being edited, so it works on a level whose brief already
says hard. Before, the planner turned it into a new take of the same level: a different play,
not harder. A new take now needs words that ask for one ("another take", "different moves").

### 2.7 Edit any version, compare any two

An edit applies to the version on screen; the new version records which one it came from
("v8 ← v2"). Any two versions can be compared (`cbj edit-report <id> A B`, or *Compare* in the UI).

## 3. Results (live: real planner, real game)

Three edit chains were run through the UI's API, as the page does it (plan, then make). Chains 1
and 2 found defects (section 4); chain 3 is the final code. All on the brief's own p.4 prompt as
the starting creative.

### 3.1 Chain 3 (final code): one creative, 12 versions

`studio/1012-104647-create-a-difficult-color-block`. Total time per edit includes 15-45 s of
planning (the LLM), the stages that had to run, and the proof.

| v | The edit (prompt or exact edit) | Re-run | The report's verdict | Frames changed | Time |
|---|---|---|---|---|---|
| 1 | the p.4 prompt (hard, narrow centre, almost fails) | everything: level, recording, ad | - | - | 69 s |
| 2 | "I like this creative. Keep everything exactly the same, but replace this asset." + an image | the ad only | only what was asked: the end-card picture (assumption written: "could also be the hook icon...") | 105 of 900, inside its box | 79 s |
| 3 | "...put the attached picture on the end card instead of the stopwatch" | the ad only | nothing changed (it was already there) | 0 | 75 s |
| 4 | "...add our logo (test_logo.png) in the top right corner" | the ad only | asked: the logo; because of it: captions re-laid in the narrower band | 706, inside the changed layers | 106 s |
| 5 | *Things in this ad*: replace the logo | the ad only | only what was asked: the logo, still top right | 706, inside the logo's two layers | 88 s |
| 6 | "...remove the game's result screen" | the ad only (pinned) | asked: the result removed; because of it: the end card takes its 2.5 s; no replay added; gameplay frames unchanged | the timeline changed | 73 s |
| 7 | "Make the blocks pastel, keep everything else." | the stored job filmed again (state identical on all 677 frames) | asked: the colours; because of it: "red" -> "rose" in a caption (same template, new colour name) | all (the new look) | 46 s |
| 8 | "...make the hook harder to ignore: 'Bet you can't beat this clock'" | the ad only | only what was asked: the hook (not a level edit) | 72, inside the hook | 76 s |
| 9 | "Same ad, but add a second mistake before the solve." | new recording, closest play (24 tried in 0.6 s) | asked: gameplay (first 2 of 12 moves the same, 8 in common); because of it: timing, the cursor, the fix caption, sound | the timeline changed | 76 s |
| 10 | "Keep everything, but make the level harder." | board edit (54 boards tried, 29 s), new recording | asked: the same board with 1 gate moved, 8 -> 9 drags, 2 -> 3 repositioning; the HUD number kept | the timeline changed | 133 s |
| 11 | "Keep everything, but make the level a bit easier." | board edit (40 tried), new recording | asked: the same board with 1 block moved, 9 -> 7 drags, 3 -> 1 repositioning | the timeline changed | 134 s |
| 12 | *Things in this ad*: the 'hurry' caption -> "Quick!" | the ad only, no planner | only what was asked | 83, inside the caption | 66 s |

No version reported a change that was not asked. Overlay edits (2-5, 8, 12) reused the recording
and kept every frame outside the edited layer byte for byte.

### 3.2 What chains 1 and 2 caught (fixed before chain 3)

| Found live | Fix |
|---|---|
| The brief's p.4 prompt got a "packed, symmetric, colourful" board: the evidence check read "jam" in "Color Block **Jam**" as asking for a packed board (and "color", "block" for colours and events). A requirement-2 bug | the game's name is removed before the word checks |
| "Make the level harder" on a level already rated hard became a new take of the same level (a different play, not harder), reported as "as asked" | "harder"/"easier" edit the board itself (2.6); a new take needs words that ask for one |
| The closest-play search tried 1 plan in 9 s | solved positions cached in the planner: 24 plans in under 1 s once warm |
| Two different "moves in common" counts for one edit | one definition (block, last cell, leaves) for the search and the report |
| "Keep everything, but change X" added "asked to keep the copy, but..." notes | a keep conflict is noted only when the prompt names what to keep |
| A colour edit's proof took 74 s (pixel boxes measured on a re-filmed recording) | no pixel boxes when the gameplay was filmed again (its frames differ by design) |
| "Without the slow-motion replay" on an ad that has none: no explanation | the planner is told the ad's parts ("this ad has no slow-motion replay") |

## 4. Fable 5.1: plan discussion, check, confirmation

**Plan discussion.** Fable read the code and measured the gaps on the stored recordings before
anything was built. It confirmed the ripples (a 9-word hook pushes the mistake caption by 0.9 s;
removing the replay inserted a 2 s frozen intro and on three of four recordings silently changed
the ad's length) and found a worse one (the assets were one all-or-nothing field, so an
undeclared replacement was dropped without a word and a declared one could drop the logo). It
argued against patching the stored ad.json (the unasked changes come from two places only, so pin
those) and for a seed search over re-planning around kept moves. Its decisions are section 6 of
the plan.

**Check (adversarial, 9 live jobs + offline probes).** 11 real defects, all fixed:

| # | Defect | Fix |
|---|---|---|
| 1 | A pinned edit could ADD a replay the user never saw (freed time went to the replay search), and the report called it "as asked" | the pin never adds a replay unless the brief turns it on; the report judges the ad's parts one by one |
| 2 | Side-effect reasons were not checked: with gameplay asked, every other row could be excused, with a reason that did not apply ("a hidden clock also hides the stopwatch" when the clock was never hidden) | the report was rewritten: each difference is explained only by a check on the measured difference (section 2.1) |
| 3 | "Easier" changed the HUD's level number (56 -> 30 -> 57): the number came from the level file's hash | an edit that changes the level keeps the number the user saw unless a new one is asked |
| 4 | Replacing a logo moved it to the other corner (and re-laid every caption) | a replacement keeps the role, timing and place of the picture it replaces |
| 5 | "Make the hook harder to ignore" became a level edit | difficulty words count only in a clause without copy words |
| 6 | "Hide the timer, keep our logo" could delete the logo | a removal needs the remove word and the picture in one clause, with no "keep" there |
| 7 | "Harder" found nothing on the live level in 20 s (it needed about 45 s), and the result depended on machine load | the search is bounded by boards tried (120), with its own seed and gate moves weighted for "harder"; the same edit finds the same board |
| 8 | Two different "moves in common" counts in one report | one definition for the search and the report |
| 9 | "Turn the replay back on" that cannot fit left no note | a note says there is no room for a replay |
| 10 | A note gave the remaining intro instead of the cut | fixed |
| 11 | A file attached to a caption edit was placed beside the hook without saying so | an attachment is placed only when the prompt talks about a picture |

Plus its smaller points: the hook cannot be removed (it is the poster frame's text), the logo's
screen time includes the end card, unknown creatives give 404, a failed proof never loses a made
version, the report's rows are shorter (same reasons said once) and readable in the narrow column.

**Confirmation.** Fable re-ran its probes on the final code: all 11 fixed, with evidence; every
version of the three creatives recomputed (35 edits): no lie and no false alarm. The only failing
reports are three versions made by the pre-fix code, and each names the real defect ("added: the
replay (NOT ASKED)", "the HUD level number: 56 -> 30 (NOT ASKED)"). It found four predicate edge
cases, fixed after: a shorter hook letting the next caption go back to its moment was flagged
(now explained); a play edit could excuse a new button text (default captions now follow only
what they are written from: the ending, the mistake or the finish); a play edit could excuse a new
level; the cursor's excuse was too broad. Its verdict: "Requirement 5 is done."

## 5. Honest limits

- **An edit still needs the planner's reading, 15-45 s.** The exact edits in *Things in this ad*
  avoid it for pictures, captions and the sound.
- **"This asset" is a guess when the prompt names nothing.** The tool writes the guess and the
  alternatives; the same prompt read twice picked the end-card picture once and the hook icon
  once. Naming the thing, or using *Things in this ad*, is exact.
- **A gameplay edit changes the play from the first move that differs.** Of 24 plans the closest
  is kept (8 of 12 moves in common in the live run), but the moves after the first change are
  re-planned, so their timing differs. The ad's structure is rebuilt for a new recording (a
  frozen intro may come or go).
- **A difficulty edit needs a few seconds of search per board (about 30 s in all)** and is limited
  to three changes. When none works, the level is kept (or, for a named band, a new level is
  made) and the brief says so. Symmetric boards are not edited (a change would break the mirror).
- **The edit report judges what it can measure.** Its checks cover the brief's fields, the moves,
  the ad's parts and layers, the pictures by file hash and the sound by hash. A change inside a
  layer's own pixels that the compositor did not record (none known) would show only in the frame
  diff.
- **In-game pictures (block skins, the game's background as an image) are not slots yet.** The
  game's colours and background colours are; images inside the game are the image-input step's
  job (Oct 14).
- **One job at a time** (the game player is one process): a 1-2 minute edit blocks the next.

## 6. Numbers

- Tests: 538 fast + 28 Unity (`CBJ_UNITY=1`), all passing. New: `tests/test_editing.py` (45).
- Live: 3 chains plus Fable's own runs, 37 versions in 3 creatives; chain 3 (final code) 12 versions, no unasked change.
- Code: `editreport.py` and `edits.py` new; `ad.py` (pin, boxes, removals, button), `brief.py`
  (slot merge, clauses, relative difficulty, retake evidence, the game's name), `planner.py`
  (inventory and parts in the edit prompt, unplaced attachments), `studio.py` (base versions,
  closest play, board edits, the HUD number, the report), `generate.py` (board edits), `play.py`
  (solver cache), `app.py` and the page (Things in this ad, the report, compare), `cli.py`
  (`--base`, `edit-report`).
