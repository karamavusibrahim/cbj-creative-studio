# Case-requirement test of the CBJ Creative Studio UI (2026-10-13)

What was tested: the running tool at http://127.0.0.1:8765 (commit 9c90b63, server started 11:24 on
2026-10-12), against the five core requirements of Rollic's "AI Engineer, Creative" case
(~/Downloads/AI Engineer, Creative Case Study.pdf, 14 pages). Every scenario below was run for
real through the UI's own API (the same calls the page makes), with the real planner
(nemotron-3-ultra) and real game recordings. A few checks were done in a browser (Playwright).

Runner and raw results (re-runnable): `~/rollic-case/case-test-2026-10-13/`
(`scenarios.py` = the 75 scenarios, `extra.py` = 7 follow-ups, `results/*.json` = one file per
scenario with the brief, the log lines, the version record and the edit report).
Run: `cd ~/rollic-case/cbj-creative && uv run python ~/rollic-case/case-test-2026-10-13/scenarios.py [ids]`
(the UI must be running). Total wall time: 61 min for the 75, plus ~10 min for the extras.

## 1. The case, read as requirements

| # | Core requirement (PDF page) | What a reviewer will type / do |
|---|---|---|
| R1 | Text-to-creative (p.3): prompts about the level's structure, gameplay behaviour, difficulty or pacing, visual elements, creative concept, sequence of events, assets to use, elements that must stay unchanged | the p.4 prompt; one prompt per control; several controls in one prompt; odd prompts |
| R2 | Level & gameplay generation (p.5): a specific type of level, a visually interesting board, difficult or easy, a progression, a near-fail, a satisfying solve, a specific sequence of interactions | each item, checked against the recording, not the plan |
| R3 | Image inputs (p.6): visual reference, asset to insert, style or composition reference, input for modifying an existing creative; "use this object instead of the current obstacle"; "a creative inspired by this image" | both p.6 prompts verbatim, an asset, a style reference, bad files |
| R4 | Video inputs (p.6): "Create a Color Block Jam version of this concept" from a creative of another game, an ad, or an existing CBJ creative | attach an mp4; the p.4/p.6 prompts |
| R5 | Controlled editing (p.7, "one of the most important parts"): preserve gameplay, timing, camera, composition, sequence, visual structure, other assets; only the requested element changes | the p.4/p.7 "keep everything, replace this asset"; copy, sound, language, theme, length, difficulty edits; edits of older versions; conflicts; concurrency |

Cross-cutting constraints: 30-60 s output (p.2 twice), a non-technical user (p.2, p.10), the
workflow prompt > generate > review > modify > regenerate (p.10), honesty about limitations (p.13).

## 2. Results at a glance

| Requirement | Scenarios | Pass | Fail | Verdict |
|---|---|---|---|---|
| R1 text-to-creative | 24 | 18 | 6 | works for English prompts; length and non-English prompts break |
| R2 level & gameplay | 17 | 15 | 2 | strongest part; every recorded ending verified in-game |
| R3 image inputs | 15 | 11 | 4 | assets work; "reference" and "style" images are NOT seen (text-only planner) |
| R4 video inputs | 3 | 0 | 3 | not implemented: videos are refused at upload |
| R5 controlled editing | 23 | 19 | 4 | strong, with one real regression on shipped levels and a length problem |
| UI / UX checks (browser) | 8 | 4 | 4 | jargon leaks, no busy state, duplicate names |

The harness's own verdicts were corrected by hand where my expectation was too strict
(T5.01, T5.04, T5.05, T5.08, T5.12, T5.15: a longer or translated caption re-wraps, so the edit
report rightly lists Composition alongside Captions) or too lenient (T3.04, T3.02, T4.02: the
tool "passed" by writing something, but what it wrote was wrong or useless). The table above
uses the corrected verdicts.

## 3. Failure parts, ranked

### F1 (high) Ads come out shorter than 30 s, and shorter than asked
Case: "30-60 second" (p.2). Observed: 4 of 27 finished ads were under 30 s, and length requests
were missed every time the recording was short.

| Scenario | Asked | Got | Why (from the log) |
|---|---|---|---|
| T1.04 "easy level, calm pace, 45 seconds" | 45 s | 18 s | planner picked the game's Level 1 (2 blocks, 5 s of play); end card may not exceed 8 s, so the ad was cut to 18 s |
| T1.08 "a quick clean win" + logo | 30 s (default) | 29 s | "quick" = fast tempo = 15 s recording; cap on the end card |
| T1.12 UI example "20 seconds" | 20 s | 15 s | the UI's own example chip asks for a length outside the case; engine shrank it further |
| T2.09 "one move frees everything" | 30 s | 27 s | short win recording |
| T5.11 edit "keep everything, make it 45 s" | 45 s | 41 s | re-recorded with longer pauses, still 27.6 s of play |
| X5.19 edit "without the replay" on the 18 s ad | 18 s | 12 s | the replay's time was dropped, not given to the card |
| X1.26 "a 60 second ad, hard, almost fails" | 60 s | 47 s | the biggest level the generator makes (8x9, 10 blocks, 13 drags) records 32.7 s of play; the case's upper bound is unreachable |

Mechanism: `ensure_recording` fits the clock and the pacing, but the ad's length is fitted only
by the end card (3-8 s) and an intro hold (up to 2 s). When the recording is short the compositor
logs "a 45 s ad does not fit this gameplay" and composes a shorter one (the stored brief's pacing
row does say "adjusted: the ad is 18 s instead of 45 s"; the plan-time table does not).
Fix direction: size the level/mistake count to the requested length before recording (the
planner already knows the length), or stretch with hesitations/pauses on the same recording, and
mark the pacing row "adjusted" with the real length.

### F2 (high) Image inputs: the planner cannot see images, and says it can
Case p.6: images as visual references, style or composition references.
- T3.03 "Create a Color Block Jam creative inspired by this image" (candy_reference.jpg, pink/mint/lemon):
  the brief says "derive the candy colour palette from candy_reference.jpg" and picks #4ECDC4, #FFE66D,
  #FF6B6B. None of those is in the image; the words "candy" came from the FILE NAME. It also
  pasted the reference photo itself onto the end card.
- T3.04 "Match the colours of the attached image": plan text "Extract the dominant palette from
  candy_reference.jpg", result: a lemon-to-blue background (#FFE66D, #6A89CC). The image is pink
  and has no blue.
- X3.11 (control): the same image renamed ref_01.jpg: theme "game", no colours, "no colours or
  style cues were given". Identical pixels, opposite answer: only the file name was read.
The planner is text-only (`planner.py` sends only the file names). The UI's drop zone says
"Attach images (logo, mascot, hand, end-card art)", which is honest, but the planner then claims
to have sampled pixels. A multimodal pass (e.g. the NVIDIA omni model already verified for the
case, or a local palette extraction with PIL for colours) is needed for the "reference" and
"style" bullets of p.6; until then the brief must say "the image was not analysed".

### F3 (high) Video inputs (core requirement 4) do not exist
- T4.01 / browser: an mp4 is refused: "reference_clip.mp4: only PNG, JPG or WebP images".
- T4.02 "Create a Color Block Jam version of this concept": made the default ad, no word that no
  concept was given.
- T4.03 "Create a creative similar to this reference video, but adapt the concept to Color Block
  Jam" (the p.4 prompt): assumption "No reference video was provided", then a default ad anyway.
The case asks for at least one video-reference-driven example (p.12). Planned for Oct 14.

### F4 (high) Controlled edit regression on the game's own levels: the HUD badge changes and the play is re-filmed
X5.19: on the creative made from the game's Level 1, "Same ad without the slow-motion replay"
re-filmed all 152 frames and the HUD changed from "Level 1" to "Level 97". The tool's own report
caught it: "Changed without being asked: Visual structure ... the HUD level number: 1 -> 97 (NOT
ASKED)". Root cause (`studio.hud_label`): the badge number comes from the level FILE NAME; v1 read
`data/levels/Level_01.json` (name Level_01 -> 1), the edit reads the version's copy
`studio/<id>/v1/level.json` (name "level" -> hash -> 97). The changed label changes the recording
spec, so every edit of a shipped-level creative re-films and shows a new level number. Generated
levels are not affected (T5.12 kept 56). Fix: carry `level_label` from the parent's job.json
whenever the level sha is unchanged, not only when it changed.

### F5 (medium) A valid prompt crashes the tool: "hesitating twice ... before winning"
T1.03: `brief.check` allows 0-3 hesitations, `play.plan` allows at most 1 for a win. The user
sees a red error "hesitations must be 0 to 1 for win, got 2" (Level only and Plan & make both
fail) instead of an adjustment to 1 with a reason. Same pattern risk for mistakes on tiny levels.

### F6 (medium) The word-list "evidence" filter overrides correct understanding, and the UI still shows "applied"
The merge step only accepts a planner change for prone fields when the prompt contains words
from an English allow-list (`brief.PRONE`, `_evidence`). Two real misses:
- T1.10 "40 seconds, speeding up": the planner set curve=speeds_up (row says "applied"), the
  filter dropped it ("the prompt asks for no change of pace"), the brief has curve=even. The
  table shows a promise the engine does not keep; only a grey footnote says it was "kept at default".
- T1.13 Turkish prompt "Zor bir seviye ... son saniyede": language and near-fail were taken, but
  "zor" (hard) and "son saniyede" (last second) were dropped by the English list. The level row
  still says "applied: Generate a hard level". Any non-English prompt loses difficulty, shape,
  length, events, copy.
Fix: when a declared change is dropped, set that control row to "adjusted" with the reason, and
either extend evidence to the prompt's language or trust the planner for non-English prompts.

### F7 (medium) Silent misreads of the case's own wording
- T3.02 "Use this object instead of the current obstacle" (p.6 verbatim): the game has no
  obstacles. The planner mapped "obstacle" to the hook sticker, which already held the same
  file, and reported "Nothing changed". Nothing tells the user that Color Block Jam has no
  obstacle to replace, or offers the two places the object could go.
- T5.09 "Change this." and T5.10 (a repeated edit): a new, byte-identical version is made
  (51 s each, "Nothing changed") instead of asking what to change. Versions pile up.
- T1.15 garbage prompt: honest ("contains no actionable instructions") but "Plan & make" still
  spends a minute making the default ad.

### F8 (medium) Upload accepts a non-image; the failure surfaces as a raw traceback much later
T3.05f: a text file named `fake.png` is accepted (extension check only). X3.10: a prompt that
uses it as the logo plans for 37 s, then dies in compose with "cannot identify image file
'/Users/ibrahimkaramavus/rollic-case/cbj-creative/studio/uploads/fake.png'": a filesystem path
and a PIL message shown to a marketing user. Fix: `Image.open().verify()` at upload.

### F9 (medium) Non-technical UX: internals leak into "What I understood" and the edit report
Case p.2/p.10: "The complexity of the underlying system should be hidden". Seen in the browser:
- control rows: "Replace the end_art asset (role 'end_art', when 'end_card')", "cap_mistake starts
  at 2.20 s", "the existing seed", "level.difficulty: not among the changes the prompt asked for";
- the level line: "naive player 3.34x -> 1.08x", "9 -> 7 drags, 3 -> 1 repositioning";
- the edit report: "end_art placed or sized differently", asset hashes "(32f6f4b643ef98be)",
  and in T5.15 a raw JSON dump "blocks: [] -> [{'slot': 'Red', 'hex': '#FF1493', ...";
- the summary line "level: generate / narrow_center / medium", "ending: near-fail", "draft render".
These are fine for the author's own QA; a creative-team user needs plain names (the picture on
the end card, the caption on the mistake) everywhere, with the data behind a "details" toggle.

### F10 (medium) The page does not know the server is busy, and loses a job on reload
- Jobs are serialised server-side (one game player). A second tab, or a page opened while a job
  runs, shows "Idle." and enabled buttons; its job silently queues (T5.18: two edits submitted
  together both completed, v19 and v20, no corruption, but no feedback). `/api/meta` already
  returns `busy`; the page ignores it.
- A reload during a 1-2 minute make forgets the job (no job list endpoint, no resume); the
  version appears later in the history with no progress shown.

### F11 (low) Smaller creative-quality defects seen in the frames
- Hiding the HUD timer (T1.05) leaves the purple HUD panel empty beside "Level 47" (a blank bar
  for the whole ad).
- Cliffhanger (T2.13): during the 2 s intro hold the clock is drawn in red "00:27", then turns
  white when play starts (the hold uses a frame before the timer's style settles).
- T1.04's end card reads "Cleared in 1 seconds" (grammar) on an 18 s ad whose card is 8 s long.
- T5.15 "pink blocks on a black background": the planner also set the board cells to #111111,
  so the grid disappears into the background; three pinks sit close in hue on the bottom gates
  (the tool reverted three other repaints with a correct reason).
- T5.08: shortening the hook also shortened its on-screen time (1.90 s -> 1.67 s, reading-time
  rule): a copy edit moves timing (disclosed in the report).
- T1.13: machine-translated Turkish "Saatı yenebilir misin?" (should be "Saati") and
  "{clock_left} kaldı temizlendi" (garbled); the T5.04 edit's translations were correct.
- The history list shows three creatives with the same first prompt and only an id to tell them
  apart.

### F13 (medium) A dropped edit still re-records, and render drift then fails the proof
X5.20 "Keep everything, but let the purple block leave first" on a level with no purple block:
the Order check honestly says "this level has no such block, so the event is left out", but the
tool still planned a "closest play" (the same 11 moves) and recorded it again. The new recording
differs from the old in 1 of 677 frames (the known ~1 % driver drift, see RUNNER-REPORT), and
the edit report calls that "recorded frames: 676 of 677 identical (NOT ASKED)": a red verdict
for an edit that changed nothing. Two fixes: when the resolved plan equals the parent's, reuse
the parent's recording; and compare re-recordings with the tolerance `cbj compare` uses, not
exact identity.

### F12 (low) "Packed" and "hard" cannot be met on a big board, and the tool says so
T2.14 "a hard 9x10 board packed with 10 blocks": 10 blocks is the generator's cap, so a 90-cell
board is 31 % full and rates medium-to-hard. Both checks say "adjusted" honestly; the generator
could have shrunk the board instead.

## 4. What passed (evidence the reviewer will see)

R1: the p.4 prompt (hard narrow-centre, near-fail at 00:01, 30 s, all checks pass); ring 7x7 /
6 blocks / 3 colours; neon + hidden timer + hand cursor + zoom; the "only 1 %" claim refused with
a dare; result-first + no replay, end card kept with a reason; a logo top-left; "keep the game's
look"; 90 s clamped to 60 with a reason; 3D cats / voice-over / music / 16:9 all marked not
supported; empty prompt refused; contradiction surfaced; 12x12 / 20 blocks / 5 mistakes clamped
with reasons; "the game's own level 4" chosen; prompt injection ignored; 4:5 refused + German
copy; a 2,000-word prompt; a staged fail moved to the social channel with the reason.

R2: holes, door, lanes, cross, ring, symmetric + colourful boards all generated and checked;
easy and hard bands hit; "yellow moves first, blue leaves, biggest last" recorded and verified
from the game's own drag log; near-fail with exactly 00:03; one-move streak finish; colour by
colour; "two blocks at once / left half first" and "two levels" marked not supported; TikTok
time-out with one block left; cliffhanger with two blocks left; three mistakes of three kinds.
Every recorded ad: "Planned moves: all N drags played as planned" (the game played the script).

R3: the p.4 "replace this object with the attached asset" (assumption written, 72 frames
changed, inside the icon's box); two attachments routed to logo and end card; unmentioned upload
left out with a reason; a named-but-missing attachment not invented; Unicode/space file names;
mp4, gif, pdf, svg and a 21 MB png refused.

R5: direct caption and sound edits (no planner, exact); "in Turkish" (every caption, nothing
else); editing an older version branches from it and keeps that version's copy; "keep the
gameplay but add a mistake" flags the conflict and applies the change; "remove the music and the
logo" says the ad has neither; coin-pile swap; pink/black with reverted clashes explained;
compare any two versions; unknown ids 404, path traversal blocked; concurrent edits serialised.
Edit reports were correct in all 20 edits; proofs with pixel boxes in 11 of them.

Timings (this Mac): planner 14-61 s (median 28 s); a new ad 48-93 s; an edit that reuses the
recording 30-81 s; a re-filmed edit 63-85 s.

## 5. Follow-up scenarios (extra.py)

| Id | Scenario | Result |
|---|---|---|
| X3.10 | use the accepted `fake.png` as the logo | crash in compose with a raw path (F8) |
| X5.19 | on the Level-1 creative: "without the replay" | HUD 1 -> 97, re-filmed, 12 s (F4, F1) |
| X5.20 | "let the purple block leave first" (no purple block) | event dropped with a reason, but the play was re-recorded and 1 drifted frame became "NOT ASKED" (F13) |
| X1.24 | new creative: "Same as the last one, but candy" | candy applied; assumption invents "the previous ad's configuration is available" on a new creative (F7) |
| X1.25 | draft render of a hook edit | pass; compose 17 s instead of ~30 s, proof identical |
| X1.26 | "A 60 second ad: a hard level, almost fails" | 47 s delivered after 171 s (level 55 s, recording 70 s): "the end card would run 20.7 s (at most 8)"; level rated medium-to-hard (F1) |
| X3.11 | the candy image renamed ref_01.jpg | theme "game", no colours, assumption "no colours or style cues were given"; the file was put on the end card as a background. Same pixels as T3.03: the planner reads file names only (F2) |

## 6. Suggested order of fixes before submission (Oct 17)

1. F4 label carry-over (one line in `studio.make`): without it, any edit of a shipped-level
   creative fails the case's headline requirement.
2. F1 length: refuse to go under the requested length; size the play to it; mark adjustments.
3. F5 hesitation crash: clamp in `brief.check` per ending.
4. F6: mark dropped changes "adjusted"; non-English evidence.
5. F3/F2: video and image understanding (Oct 14 plan) with honest "not analysed" wording until done.
6. F8, F9, F10: upload verify, plain-language rows, busy state and job resume.


## 7. Fixes made on 2026-10-13 (after the test), and what the re-run showed

All fixes are in `cbj-creative` (14 files changed, `reference.py` and `tests/test_case_fixes.py`
new; 559 fast tests pass, 28 Unity tests skipped as usual). The UI was restarted and the failed
scenarios re-run (`case-test-2026-10-13/rerun.py`, results in `results_rerun/`). No Higgsfield
credit was used: the image and video reading runs on the NVIDIA key the planner already uses.

| Finding | Fix | Re-run |
|---|---|---|
| F1 length | Ads are 30-60 s (`LENGTH_RANGE_S`), shorter asks raised to 30 with a reason; the UI example now says 30 s. A level too short for the length is swapped for a generated one of the same difficulty sized to it (unless the prompt named a level number). A short recording is filled before the card may grow: longer replay (to 8 s), first-frame hold (to 3 s), result held (to 4 s), card to 10 s. Ads of 50 s or more with a mistake ending plan two mistakes and say so. | T1.08 29 s -> 30 s; T1.12 15 s -> 30 s; T2.09 27 s -> 30 s; T5.11 41 s -> 45 s; T1.04 18 s -> 38 s (an easy, calm, mistake-free play of 10 drags records 14 s; 45 s is out of reach with one level, and the brief says so); X1.26 47 s -> 57 s (see the second re-run below) |
| F2 images | `reference.py`: a reference image gets a measured palette (PIL) and a multimodal description (nemotron omni, about 11 s); the notes go to the planner and into the brief, shown on the page as "Read from the attached image ...". The image is placed only when asked to; a failed read is said so. A repainted block the colour of the background keeps the game's colour. | T3.03: palette light pink, mint, lilac, lemon read from the pixels, blocks repainted with them, nothing pasted; X3.11 (neutral file name): the same palette, so pixels are read, not names; T3.04 and V3.12: colours from the image |
| F3 videos | MP4/MOV/WebM accepted (content-checked, 80 MB); shrunk with ffmpeg and described by the multimodal model (structure, hook, ending, pacing, look); never placed in the ad | V4.01: the existing time-out creative, uploaded as the reference with "Create a Color Block Jam version of this concept": read as a time-out concept and remade as a 30-60 s ad; V4.02: a meaningless clip handled without guessing |
| F4 shipped-level edits | An edit keeps the level FILE the version was made from (`_level_source`), so the game's own levels keep their name and HUD number; the parent's HUD number is carried on every edit | N5.19: recording reused, "Visual structure: kept", HUD unchanged (first re-run); the same edit also exposed that the pinned path shortened the ad to 16.5 s, fixed next (second re-run: fixed, see below) |
| F5 hesitation crash | Clamped per ending in `brief.check` with a reason | T1.03: "a win shows at most 1 hesitation (more looks staged); 1 is used, not 2", level-only runs |
| F6 evidence filter | "speeding up", "slowing down", "faster", "slower" added; a prompt in another language skips the English word lists; a declared change the merge drops is shown as "adjusted" with the reason | T1.10: curve kept; T1.13: Turkish "zor" and "son saniyede" kept |
| F7 misreads | The planner is told the game has no obstacles, enemies or characters, that a new ad has no earlier version, and to write for a marketing person; an edit that changes nothing is refused with a list of what can be changed (and the planner's reason) instead of a duplicate version | T3.02: "the game itself has no obstacles on the board"; X1.24: no invented previous ad; T5.09, N5.20, N5.21: refused with the message |
| F8 uploads | Verified by content at upload (PIL verify; video magic); the compositor's error names the file in plain words | T3.05f: refused |
| F9 jargon | Plain names in the edit report (layers, colours, HUD), no asset hashes, group names in the footnote, "a casual player needs about 1.2x the minimum" | seen in the re-run reports |
| F10 page | Polls `/api/meta`: "Another creative is being made on this machine right now" and disabled buttons; a running job is resumed after a reload (`/api/jobs`, localStorage) | checked in the browser |
| F11 visuals | Hiding the clock also hides the HUD bar's own panel (runner: "Name:image" hides a graphic, children stay; player rebuilt); the intro hold shows frame 9 (after the clock's tick flash); "Cleared in 1 second"; a board colour that vanishes into the background is dropped; an edit keeps the hook on screen as long as before | unit-tested; the hidden-clock look needs a new recording to be seen |
| F13 drift | An edit that plans the same moves reuses the parent's recording; a re-filmed recording with an identical game state is never "NOT ASKED" for rendering noise | N5.20 (refused before recording); unit-tested |
| F12 packed big boards | not changed (honest adjustment stays) | - |

Second re-run (pinned-path fix, two-mistake rule, contrast rule):

| Id | Result |
|---|---|
| N5.19 on D v1 (Level 4): "Same ad without the slow-motion replay" | recording reused, HUD "Level 4" kept, 30 s kept, "Changed as asked: Sequence; also changed because of it: Timing, Composition, Captions, Sound" (the freed time went to a held result and a 14 s card: Level 4 plays 12 s) |
| X1.26 "A 60 second ad" | 60.0 s (two mistakes planned and said so), all gameplay checks pass; the generator's honest "medium-to-hard" and a 9 s card remain |
| T3.03 candy reference | palette read from the pixels; the light-pink block was reverted ("would vanish into the background") |
| T1.03 | runs, hesitations clamped to 1 with the reason |
| N5.20 "let the purple block leave first" (no purple block) | refused before recording, with the reason |
| N5.21 "Change this." | refused with the list of what can be changed |

Still open after the fixes: "easy + calm + 45 s" reaches 38 s (one easy level cannot carry 45 s;
a two-level ad would); the generator's hard band on big boards; the planner's own translations
(Turkish) are not proofread; the two assumptions in T3.02 name different places for the object.

## 8. Page-by-page check of the case (every requirement, every "should not" and "avoid")

Status: MET (with evidence), PART (works with a stated limit), OPEN (not done), N/A (not a requirement).

### p.2 The challenge
| Case text | Status | Evidence |
|---|---|---|
| turns text, image and video inputs into creatives | MET | R1 (24 scenarios), R3 (image references and assets), R4 (video references, V4.01, the reel check below) |
| controllable 30-60 second creatives | MET | every ad made after the fixes is 30-60 s; shorter asks are raised to 30 with a reason; 60 s reached (X1.26) |
| one or more of the inputs | MET | text alone, text + image (T3.03, T1.08), text + video (V4.01) |
| different creative concepts, gameplay at the centre | MET | four endings (win, near-fail, cliffhanger, time-out), result-first, themes, hooks; the gameplay is the real game recorded (every ad: "Planned moves: all N drags played as planned") |
| end user need not understand generative AI, video editing or workflows | PART | one prompt box, one button, plain-word rows; the planner model name in the header and the "draft render" checkbox are the two technical items left on the page (harmless, but could be hidden) |
| the interface should be simple | PART | prompt > Plan & make > review > edit prompt > Plan & make; "Plan only" and "Level only" are extra buttons for checking a plan without recording (useful, but a reviewer may see them as extra steps) |

### p.3 Core requirement 1: text-to-creative, the eight prompt controls
| Control | Status | Evidence |
|---|---|---|
| type or structure of the level | MET | ring/holes/door/lanes/cross/narrow/open, sizes, block counts, colours (T1.02, T2.01-04, T2.14) |
| gameplay behaviour | MET | mistakes, hesitations, stuck, order of moves (T1.03 after the clamp, T2.07, T2.10, T2.16) |
| difficulty or pacing | MET | easy/medium/hard bands checked on the level; tempo; curve (T2.05, T2.06, T1.10); length 30-60 |
| visual elements | MET | themes, repaints, background, board, captions' colours, zoom, cursor, HUD (T1.05, T5.15) |
| creative concept | MET | angle + every caption; copy guard refuses odds claims with a dare (T1.06) |
| sequence of events | MET | result-first, replay on/off, result screen on/off; the end card always stays, with a reason (T1.07) |
| assets to use | MET | uploaded images in six slots, the game's own sprites, removal (T1.08, T3.07, T5.14) |
| elements that should remain unchanged | MET | "keep" list on new ads and edits; conflicts surfaced (T1.09, T5.06) |
| "translate these requests into a final creative" | MET | 27 + 12 ads made in the two runs |

### p.4 Example requests
| Request | Status | Evidence |
|---|---|---|
| difficult level, narrow centre, almost fails before solving | MET | T1.01: hard hourglass, 00:01 left, all checks pass |
| similar to this reference video, adapt the concept | MET | V4.01 (a CBJ creative), reel check below (an advertisement); T4.03 without a video says so |
| keep exactly the same, replace this object with the attached asset | MET | T3.01: 72 frames changed inside the icon's box, everything else identical |
| think about what a creative or performance marketing team would realistically ask | MET | 75 + 7 + 25 scenarios built from that question (channels, lengths, languages, hooks, logos, retakes) |

### p.5 Core requirement 2: level and gameplay
| Asked | Status | Evidence |
|---|---|---|
| a specific type of level | MET | shapes, pieces, styles (T2.01-03, T2.17) |
| a visually interesting board | MET | symmetric + colourful checked on the level file (T2.04) |
| a difficult or easy level | MET | bands measured (minimum drags, repositioning, a casual player's ratio); honest "adjusted" when the generator cannot reach a band (T2.14, X1.26) |
| a particular gameplay progression | MET | ordered steps verified from the game's drag log (T2.07) |
| a near-fail moment | MET | 00:01-00:03 left, exact (T1.01, T2.08) |
| a satisfying solve | MET | one key move, then a streak (T2.09) |
| a specific sequence of interactions | MET | first/next/last, colour by colour, stuck/hesitate steps (T2.10, T2.16, T2.17); impossible ones refused (T2.11) |
| the Unity project is a tool, not a restriction | MET | used for recording only; levels, moves and the ad are built outside it |

### p.6 Core requirements 3 and 4: image and video inputs
| Asked | Status | Evidence |
|---|---|---|
| images as visual references | MET | palette measured + multimodal description, applied to colours, mood and hook (T3.03, X3.11) |
| images as assets to insert | MET | T1.08, T3.01, T3.07 |
| images as style or composition references | PART | style (colours, mood): MET; composition: the model describes the layout but the engine only maps it to a board shape through the planner (one case seen: "vertical stack" -> narrow centre); no layout-level compositing from a reference |
| images as inputs for modifying an existing creative | MET | T3.01, T5.13, T5.14 |
| "Use this object instead of the current obstacle" | MET with honesty | the planner now says the game has no obstacles and places the object (T3.02); the two assumptions should name one place, not two (open, small) |
| "a creative inspired by this image" | MET | T3.03; the image example creative is listed in section 9 |
| understand the role of the image | MET | reference vs asset decided from the words (reference.is_reference_prompt / asks_placement), and said in the rows |
| video: a creative from another game, an advertisement, or an existing CBJ creative | PART | existing CBJ creative: MET (V4.01); an advertisement: see the reel check below; another game's ad: not tested with a real sample (none on this machine; the path is the same) |
| "Create a Color Block Jam version of this concept" | MET | V4.01 |
| not frame by frame; understand structure, idea, pacing, visual concept | MET | the model returns structure (from/to seconds), hook, ending, pacing, pace change, mood, colours, CTA, "how to adapt"; the planner maps them to ending, mistakes, tempo, curve, theme and copy |

### p.7 Core requirement 5: controlled editing
| Asked | Status | Evidence |
|---|---|---|
| one specific change, avoid changing everything else | MET | 20 + 8 edits; the edit report proves each row |
| "I like this creative. Keep everything exactly the same, but replace this asset." | MET | T3.01, T5.13 |
| controlled editing rather than regenerating an entirely different video | MET | recordings reused (same spec, or the same planned moves); look-only edits re-film the same job with identical game state; proof by pixel boxes |
| preserve gameplay, timing, camera, composition, sequence, visual structure, other assets | MET | the nine rows of the edit report, with "kept / as asked / because of it / NOT ASKED"; the shipped-level regression fixed (N5.19) |
| only the requested element changes where reasonably possible | MET | 11 proofs with every changed pixel inside the edited layers' boxes; side effects (re-wrapped captions, a colour name in a caption) explained |

### p.8 The technical challenge: what to avoid
| Case text | Status | How |
|---|---|---|
| objects changing between frames, inconsistent rules, layout drift | AVOIDED | gameplay is the real game at a fixed timestep; no generative video in the gameplay; the drag log is checked against the plan |
| think beyond a single generative model | MET | solver + generator + Unity recorder + compositor are deterministic; LLM for intent, multimodal model for references, deterministic checks around them |
| AI roles: intent, level generation, asset generation, planning, reference analysis, visual transformation, editing, compositing, orchestration | PART | intent, planning, reference analysis, editing (planner-driven), orchestration: AI; level generation, compositing, visual transformation: deterministic by design; asset generation: not in the tool (the Higgsfield/Nano Banana test of 2026-10-12 was a manual experiment; nothing in the UI generates pictures) |

### p.9 Implementation freedom
| Case text | Status | Note |
|---|---|---|
| explain why you chose the architecture | OPEN (write-up) | the plan documents (CASE-ANALYSIS-AND-WORKFLOW.md, the step reports) hold the reasons; the submission's technical explanation is not written yet (planned Oct 16) |

### p.10 A simple user experience: "they should not need to"
| Case text | Status | Evidence |
|---|---|---|
| configure AI models | MET | nothing to configure; the model name is shown as information only |
| edit workflow graphs | MET | none exist |
| write code | MET | none; exact edits are buttons ("Things in this ad") |
| manually combine multiple outputs | MET | one finished MP4 per version |
| workflow: prompt (+ image or video) > generate > review > request a modification > generate the revised version | MET | exactly the page's flow; versions kept side by side; reload resumes a running job; another user's job is announced |
| complexity hidden | PART | plain words everywhere the user reads; the data (brief.json, ad.json, compose.json) stays behind links and a collapsed "Brief as data" |

### p.11 What they evaluate
| Criterion | Status | Evidence / gap |
|---|---|---|
| creative quality | PART | coherent, game-centred ads with hook, captions, replay, result, end card and sound; gaps: the end card is long on tiny levels (up to 10 s, 14 s on an edit of Level 4), the bottom third of the frame is empty, machine translations are not proofread |
| controllability | MET | R5 above |
| gameplay consistency | MET | the game itself plays; every drag checked |
| multimodal understanding | MET after the fixes | text, image (pixels), video (structure); before the fixes the planner only read file names |
| system design | MET | deterministic core, generative shell (plan documents) |
| AI usage | MET | LLM for intent and copy, multimodal model for references, deterministic everywhere consistency matters |
| engineering quality | MET | 559 tests, typed brief, content-addressed recordings, proofs |
| user experience | PART | see p.2 and p.10 |
| extensibility | PART | new shapes, endings, slots and checks are data-driven; multi-level ads and asset generation are designed, not built |
| decision making | OPEN (write-up) | to be written for the submission |

### p.12 Expected output
| Deliverable | Status | Where |
|---|---|---|
| a working prototype | MET | `uv run cbj ui` |
| source code and setup instructions | MET | cbj-creative, README (setup, commands, the Unity player build) |
| several example creatives | MET | studio/: 39 ads from the two runs; a curated set is listed in section 9 |
| at least one text-driven example | MET | section 9 |
| at least one image-driven example | MET | section 9 (made 06:18, candy reference: mint, lemon, lilac blocks on pink) |
| at least one video-reference-driven example | MET | section 9 (V4.01) |
| at least one controlled modification | MET | section 9 (T3.01 and N5.19) |
| technical explanation: architecture, components, why, deterministic vs generative, consistency between generations, how controlled editing works, limitations, improvements | OPEN | the material exists in the step reports; the single document for the submission is not written (planned Oct 16) |

### p.13 Final note
| Case text | Status | Evidence |
|---|---|---|
| identify where generative AI is unreliable and design around it | MET | gameplay never generated; the planner's output is merged field by field with evidence; references are measured (palette) as well as described; every adjustment is written into the brief |
| you do not need to solve every request | MET | clear "not supported" rows (3D cats, voice-over, two blocks at once, two levels, 4:5) |
| focused and reliable over broad and unreliable | MET | one level per ad, four endings, 9:16 only, all verified |

### Live checks added for this section
| Check | Result |
|---|---|
| hidden clock with the rebuilt player ("Hide the clock. A clean win on a medium level.") | the purple HUD bar is gone, only the Level badge remains (studio/1013-061404-hide-the-clock-a-clean/v1), QA clean |
| an advertisement from another product as the video reference (his pet-portrait reel PetBath-tub-dog.mp4, 16 s) with "Create a Color Block Jam version of this concept." | read in 69 s: structure in four parts with seconds, hook "He hates bath time.", seven captions, ending win, calm, heartwarming, CTA "link in bio"; adapted as "One move unlocks a calm cascade" with hook "So satisfying to watch.", end title "Oddly satisfying.", a calm win with a cascade, nothing from the reel placed in the ad. (The first pass kept the default captions; a reference's idea now counts as a request for copy in its spirit, re-planned: results_rerun/reel_plan2.json) |
| the page resumes a running job after a reload | "Picking up the plan that was running before the page was reloaded…" with the log streaming |
| image-driven example made | 30 s, QA clean, blocks repainted mint, lemon, lilac on the reference's pink; see section 9 |

## 9. Example creatives for the submission (as they stand now)

| Type | Prompt | File (under cbj-creative/studio/) | Length |
|---|---|---|---|
| text-driven (the case's p.4 prompt) | Create a difficult Color Block Jam level with a narrow center section and show gameplay where the player almost fails before solving it. | 1012-235537-create-a-difficult-color-block/v1/ad/ad.mp4 | 30 s |
| text-driven, 60 s | A 60 second ad: a hard level where the player almost fails before solving it. | 1013-055745-a-60-second-ad-a/v1/ad/ad.mp4 | 60 s |
| image-driven | Create a Color Block Jam creative inspired by this image. (candy_reference.jpg) | 1013-061812-create-a-color-block-jam/v1/ad/ad.mp4 | 30 s |
| video-reference-driven | Create a Color Block Jam version of this concept. (an existing time-out creative) | 1013-054739-create-a-color-block-jam/v1/ad/ad.mp4 | 30 s |
| controlled modification | Keep this creative exactly the same, but replace this object with the attached asset. | 1012-235537-create-a-difficult-color-block/v2/ad/ad.mp4 (v1 -> v2, 72 frames inside the icon's box) | 30 s |
| controlled modification, sequence | Same ad without the slow-motion replay. (on the game's Level 4) | 1013-054422-use-the-game-s-own/v3/ad/ad.mp4 (v1 -> v3, recording reused, HUD kept) | 30 s |
| controlled modification, length | Keep everything, but make it 45 seconds long. | 1012-235537-create-a-difficult-color-block/v23/ad/ad.mp4 | 45 s |
