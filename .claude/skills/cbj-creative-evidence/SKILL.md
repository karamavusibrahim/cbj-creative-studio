---
name: cbj-creative-evidence
description: Where every fact about a CBJ creative made by cbj-creative lives and how to verify it - the studio layout (studio/ID/vN: version.json, brief.json, level.json, board.png, ad/ad.json, ad.mp4, compose.json, audio.wav, poster.png), the recording folder and its result.json, the checks, the edit proof, the UI's API, the CLI commands, the unit-test suite and the two case-test harnesses - plus the reporting standard (baseline, fixes, final table, honest limits). Use when auditing a creative or an edit, reproducing a test case, writing a test report, or answering "how do we know" about any claim the tool makes.
metadata:
  spec-version: "1"
  last-verified: "2026-10-19"
---

# Evidence: where the facts are and how to check them

## 1. Purpose
Every claim the tool makes (the level is solvable, the play is legal, only the asked thing changed, three runs are
identical) is backed by a stored file or a measured number. An auditing agent reads those, never the prompt or the
plan's prose, to decide pass or fail.

## 2. Source of truth
- `src/cbj/studio.py` (what a version stores), `src/cbj/checks.py`, `src/cbj/editreport.py`, `src/cbj/compose.py`
  (`compose.json`), `src/cbj/render.py` (the recording and `result.json`), `src/cbj/app.py` (the API).
- Reports and harnesses in `~/cbj-work/`: `CASE-TEST-REPORT-2026-10-13.md` (82 scenarios), `USER-CASES-REPORT-2026-10-13.md`,
  `LG-SCENARIOS-REPORT-2026-10-13.md`, `CC-SCENARIOS-REPORT-2026-10-14.md`; `case-test-2026-10-13/harness.py`,
  `case-test-2026-10-14/{fixtures.py, cc_cases.py, summarize.py, make_cc_assets.py}`.

## 3. Facts
**A version** `studio/<id>/v<n>/`: `version.json` (n, id, prompt, edit, from, brief, level, recording, board, checks,
ad_dir, video, poster, length_s, qa, stages, seconds, created; for an edit also proof, proof_rows, level_edit),
`brief.json` (the brief; `planner` holds model, seconds, prompt, references), `level.json` (the board it played),
`board.png`, `ad/ad.json` (the composition: parts, captions, pictures, cursor, sound, pins), `ad/compose.json`
(what was rendered: part frame windows, sfx_sha256, music, camera, format; `patched` when the approved MP4 was patched:
changed_layers, gops, gops_rendered, frames_rendered, frames_copied), `ad/ad.mp4` (9:16 master; derived
`ad_1x1.mp4` etc. when asked), `ad/audio.wav`, `ad/poster.png`.

**A recording** `studio/recordings/<hash>/`: `result.json` (status, frames, fps, first_touch_frame,
clock_stopped_frame, win_frame, fail_frame, timer_start, timer_end, drags, block_gone_frames, stills), the stills
`NN_drag.png`, the raw video. The hash is of everything that decides the film (level, job, look), so the same ask never
re-records. A board edit writes `studio/levels/board_<key>.json`.

**Checks** (`version.checks`): rows {check, status pass/info/failed/adjusted, detail, from level/recording/prompt/rules}:
Difficulty, Block shapes, Board shape, looks, every drag, ending and clock, mistakes (with the asked blocker), each
ordered step, the final run, the pauses; then the **asked-facts audit** (`audit.py`, from "prompt", 2026-10-15): facts
read from the prompt itself, never from the plan (block count, colours, blocks a viewer can tell apart, named colours,
board shape, difficulty, looks, the blocked attempt and who stops it, 30-60 s, length, seconds left, mistakes, order,
satisfying finish, ending, each quoted caption), each pass or failed with `where` (plan / level / play / ad) saying
which stage missed it; and the **game's rules replayed** (from "rules"): the level valid, every recorded drag legal
under the Unity project's rules (one block a drag, the pivot through neighbouring free active cells, an exit only
through the first door of its colour it touches with a clear lane, during the drag), the clock only counting down,
the result consistent with the blocks gone. The rules were re-read in the C# (InputHandler, BlockMovementService,
ExitService, GameManager) on 2026-10-15.

**The loop** (brief p.10: generate, review, request a modification, generate the revised version):
1. the level gate (`studio._level_gate`): a level-stage miss the generator can fix makes it generate again with
   other seeds (2 tries, 20 s each) and use the board with the fewest misses; the log says so;
2. the audit rows and the rules rows join the checks, so the UI shows them and the review gets them as facts;
3. The loop is on by default on POST /api/make (`revise`, the UI's "evaluate, feed back, revise"; `revise: false` turns it off; up to `app.MAX_REVISIONS` = 2 rounds, stopping when nothing measurable is missed, 2026-10-15): `audit.feedback` turns the misses
   and the viewer's verdict into an edit request, the planner plans it as an edit of the made version, a revised
   version is made and reviewed; `version.revision` {status made/unchanged/failed, of, feedback, original_prompt}.
   A miss in the board or the play makes the revised version a new take (another seed, so the level gate tries
   other boards; the same spec would only reuse the cached board and film). The audit of a revised version measures
   the marketer's original request (`studio.make(asked=...)`), not the feedback text. The first version is never lost.

**A video-guided version** (core requirement 4, 2026-10-16; `version.workflow` is "guided"). The reading is in
`brief.planner.references[i]`: `plan` (the reading plan: focus, level, questions, required_fields, ignore, constraints,
why, source planner/words, checks), `ask` (the exact prompt the NVIDIA multimodal model saw), `focus`, `level`,
`analysed_s` (the clip's whole length), `facts` (duration, size, orientation, rotation, codec, the copy's fps and frames;
`cuts_s`, `pace_change`, `pace_change_model` when the parts were measured), `reader` ("gemini" or "nvidia": Gemini 3.5
Flash-Lite reads first, NVIDIA build when Gemini fails), `model` (the multimodal model that answered the whole-clip
read), `ending_read` (the ending read a second time on the last 10 s at 8 fps: ending, last_clock, win_screen,
out_of_time_screen, question_caption, why, from_s, to_s, fps, frames, model, reader, seconds, `overrode` when it
disagreed with the whole clip; or skipped under 12 s, or error), `board_read` (2026-10-17, when the focus covers the
board: the board read a second time on one full-resolution still of the first frame of play: board, at_s, width,
height, model, reader, seconds; or error, and the whole clip's board stands), `usage` (Gemini's
prompt, candidates and thoughts tokens), `errors` (what failed on the way, reader by reader and model by model), `notes` (the model's answer: `structure` with each part's
purpose, from hook / gameplay / mistake / near_fail / fail / victory / replay / payoff / question / end_card / other,
`purpose_raw` = the model's own label when it differs, captions, emphasis, evidence_s, confidence; `structure_model` =
the model's own seconds when snapped; `captions_seen` word for word, end card included, and `screen_text` the gameplay
HUD only; `ending` (the last seconds' ending when the second read ran) and `ending_whole` (the whole clip's word it
replaced), `ending_read` (its ending and transcribed clock and screens, which `videoref.mapped_ending` checks);
`board` (the board the level's type is taken from: the still's when it was read: columns, rows, shape, blocks,
colours as read, pieces, gates_sides, obstacles, busy; `videoref.board_of` maps it to the game's terms, the colours to
the game's seven and the game's own grey wall cells to walls) and `board_whole` (the whole clip's board it replaced);
`mistakes` [{at_s, what}] beside the model's own `mistakes_shown`; `moves_by_third`; `pacing` / `pace_change`
decided in code with the model's words in `pacing_said` / `pace_change_said`; mechanics_seen, adaptation, confidence),
`pacing` {moves_by_third, gameplay_s, dps, tempo, tempo_source counts / model, change, source motion / model, said, motion,
counts_dropped}, `validation` {status passed / passed after one re-ask / rejected, problems, relabelled, captions_moved;
only the seconds and an empty structure reject a reading, never a label or the confidence},
`separated` {ran, why, boundaries, snapped, at_a_cut}, `confidence`, `low_confidence`, or `error` / `skipped`. The
provenance is `brief.reference` {file, focus, level, analysed_s, adapted, not_copied, stated, mechanics (the game's own
under another name), not_used (another game's mechanics and obstacles: "<it>: not used: not in CBJ", never
created, drawn or simulated), board {read, text, took, kept, busy (info only, never the difficulty)}}; the board taken
shows in `brief.level` (source generate, shape, width, height, blocks, colours, pieces) and the level row's plan. The checks gain
the **reference rows** (from "reference", `audit.reference_rows`): Reference: the ending, the pacing (drags per second
over the play, first third against last), the hook, the purposes in order, the part lengths (share error at most 0.2),
the captions, the look, the board (the version's `level.json` and the brief's shape against the board read, clamped
as the brief was: shape equal, size within a cell a side, blocks within two, at least half the colours; only the parts
in `audit.BOARD_RELIABLE` can fail, the request's own parts are info, busy shown as info), nothing copied, read with
confidence; info when the reading's focus does not cover the aspect,
and the pacing row info unless the request's words ask about the pacing (a sampled read gets it only approximately).
Their misses feed the loop like the others. The UI shows it all in the Create side's "Reference to creative" card
(plan, timeline, confidence, adapted, not copied, "What the model was asked"); the progress log has the format line,
the reading plan's checks, "reading X for ... (level)", the validation, the ending, the board ("board: an open 6x6
board, ... (read on a still at 0.3 s, 1280x720)") and the parts lines.

**Edit proof** (`version.proof`): asked, asked_names, rows (nine: Gameplay, Timing, Camera, Composition, Sequence, Visual
structure, Other assets, Captions, Sound; each kept / asked / side_effect / not_asked with its explanation), `changes` +
`preserves` (the same in the brief's words: "changes the hook; preserves Gameplay, Timing, ..."), `checklist` (ten flat
facts, each {ok, evidence}: level_unchanged, moves_unchanged, move_timing_unchanged, gameplay_render_reused (with the
recording hash), duration_unchanged, camera_unchanged, hud_unchanged, captions_unchanged, pictures_unchanged,
audio_unchanged; 2026-10-15), the Timing row's `numbers` {before, after}: fps, duration, the play window, the first
move, drags, the clock at the first and last drag, ok, pixels
{frames_changed, frames, ranges, layers, same_sound, note}, verdict. `level_edit` {what, kept_moves, of_moves}.
`qa` {failures, warnings} (reading time of a moved caption, hook not on frame 0, long end card). `proof.pixels.copied`
{frames, of, gops_rendered, gops}: the byte-level fact of a patched edit; `compose.json` `patched.audio_copied` when the
mix was identical and the approved video's audio stream was copied byte for byte (`video.mux(audio_from=...)`). A video
reference's notes carry `structure` [{from_s, to_s, purpose (hook / gameplay / mistake / near_fail / fail / victory /
end_card / other), what}] (`reference.structure`), shown in the plan's reference line. `stages` says which
stage ran (level, recording, compose, proof) and for how long: a compose-only edit shows level and recording at 0 s.

**API** (`uv run cbj ui`, http://127.0.0.1:8765): POST /api/plan, /api/make, /api/preview (level only), /api/direct (exact
edits), /api/upload; GET /api/meta (backend, models, busy), /api/creatives, /api/creatives/{id}, /api/inventory/{id},
/api/compare/{id}?a=&b=, /api/jobs/{jid}, /studio/{path}. One job at a time (one game player): `busy` is true while a
job runs and the UI's buttons grey out. /api/upload refuses a video longer than 120 s with the reason; /api/plan sends a
new request with a video (or a reference image) to the guided workflow (`app.workflow_of`). POST /api/make refuses an empty or incomplete brief (a failed plan posted on
once made a creative of defaults, 2026-10-15).

**CLI**: show, solve, difficulty, check, generate, scenario, render, ad, compose, ad-diff, rerun, compare, plan, make,
edit-report, ui, table (`uv run cbj --help`).

**Tests**: `uv run pytest` (621 passed, 28 Unity-only skipped on 2026-10-14; `-q -p no:cacheprovider`). Unity ones need
the built player (`uv run cbj build-player`).

**Planner backend**: `/api/meta` says `backend` nvidia or claude and the model; `brief.planner.model` records what planned
each version (e.g. `nvidia/nemotron-3-ultra-550b-a55b` or `claude-cli/opus`).

**The audit's counts (fixed 2026-10-15).** `audit.asked` never reads "three blocks remain", "two blocks left", "one green block
close to its door" or "one red block is trapped" as a block count (6 false flags in 48 prompts), nor "almost fails",
"near-fail" or "one second left" as a mistake count (3 false flags); it reads "two wrong moves" as 2, "one unhelpful
repositioning move", "into an unhelpful position" and "a move that blocks the green block's route" as 1, and the
blocking move's mover and victim (`blocks_by`). A named palette ("red, blue, green and yellow blocks") is exclusive: a
board that also shows orange fails "named colours" (P6-a had 7 colours for 4 named).

**Common to every workflow (2026-10-19; `workflows/__init__.py`, "Common to all four").** Whatever made a version, the same
things hold and the same evidence exists:
- the request is translated once for the route and the parsers (`brief.planner.prompt_original` / `prompt_english`);
- `audit.rows` runs the game's rules on every version ("Rules: the level", "Rules: doors and colours", "Rules: colours tell
  apart", "Rules: the moves", "Rules: the clock", "Rules: the result", "Rules: doors used") and the shared case rows
  ("blocks left at the cut", "the end card is a card, not padding", "a real choice at the cut");
- the loop keeps the best version, not the last (`final.version` / `final.of` in version.json), keeps every value the
  request states, never plans a longer play for a take that ran over, makes no version for a viewer-only remark that
  changes nothing the viewer pointed at, and stops when the same row misses twice with the same measure (`limit_note`);
- a fixed board's pace is said at plan time (the overrun, or the long card it leaves: `reference.play_overrun` /
  `reference.play_short`); a time-out's one-block limit is said when more are asked;
- every version made through the site keeps the engine's lines (`v<n>/log.json`; a plan's in `brief.planner.lines`),
  feedback records point at a step of it, and `cbj report <id>` writes the whole story.

## 4. Procedure
Auditing a new creative:
1. `version.json`: `checks` all pass/info; `qa.failures` empty; `length_s` 30-60.
2. The plan: eight rows, statuses valid, every "asked" an excerpt of the prompt, assumptions plain.
3. The play: `level.json` + `result.json` drags: legal and in the asked order; the ending on the right frame.
4. The ad: `compose.json` parts and captions; watch `ad.mp4` once at least for the hook, the captions and the end card.
Auditing a video-guided creative: read `brief.planner.references[i].plan` and `.ask` (was the reading for what the
request asked?), `.validation` and `.separated`, then `brief.reference` (adapted, not_copied) against the brief's fields,
then the "Reference: ..." rows in `checks`; screenshot the "Reference to creative" card.
Auditing an edit: `cbj-controlled-editing` section 4 plus `references/acceptance-rules.md` there.
Reproducing a case: `CBJ_OUT=<folder> uv run python <harness>.py <ids>` with the UI running; read `<folder>/<id>.json`;
`python3 summarize.py <folder>` prints one fact line per case.
Reporting (the standard of the four reports in `~/cbj-work/`): 1 which cases fit the game and the tool, skipped with
reasons, expectations corrected with reasons; 2 baseline on the code as it was (right / could not / wrong); 3 what was
built and fixed, per case; 4 final run, one row per case with its proof; 5 honest limits still open. Counts in tables,
never in prose; file paths once.

## 5. Not possible here
Pixel-exact equality between two films of the same job (about 1 % of frames differ by a few pixels; look edits are
proved by game state). A difficulty label calibrated on real players (bands are measured from the solver and a naive
player). Reading the planner's mind: a wording the post-rules do not cover can still be read differently between runs;
the edit report is the net that catches it (NOT ASKED fails the edit). A Mac that sleeps mid-pass stalls the player and
the brief reports a timeout (keep the lid open or run `caffeinate`).

## 6. Evidence
This skill is the evidence index; the files it names are the evidence. Spot checks done by hand on 2026-10-14 and
recorded in `CC-SCENARIOS-REPORT-2026-10-14.md` section 4: music-only edit 0 frames changed and sfx stem hash identical;
1:1 version shows the full board; a wall visible at the named tile; three repeated renders compare pairwise identical.

## 7. Change rules
When `version.json`, `proof`, `compose.json` or `result.json` gain or lose a field, when a route is added or renamed, or
when a harness moves, change section 3 in the same edit and bump `last-verified`.
