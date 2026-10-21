# The text-to-creative agentic workflow (create side), as it runs on 2026-10-16

Code: `cbj-creative/src/cbj/workflows/create.py` (orchestration), `planner.py` (the LLM brief), `studio.py` (the
engine: level, play, recording, ad), `audit.py` + `checks.py` (the measured evaluation), `review.py` (the viewer),
`parts.py` (the metadata of a finished creative). The edit side (`workflows/edit.py`) is a separate workflow and is
not described here. The user sees one box: a prompt, optional files, Generate; the rest below is hidden from them
(brief p.10).

## 1. Understand (one LLM call, about 20 s with the Claude CLI)

Input: the prompt, the attached files. Attached videos are always references; attached images are references when
the prompt says so ("inspired by", "like this") and assets otherwise; each reference is analysed first (NVIDIA
vision, `reference.py`, `imageref.py`: role = style, composition, asset or modify; the board's facts when the
picture is a puzzle board).

The planner writes a typed brief: one row per case control (p.3: level, gameplay behaviour, difficulty or pacing,
visual elements, creative concept, sequence of events, assets, elements to keep), each with what was asked, what the
tool will do, and a status (asked / default / adjusted / not supported, with the reason). Then code checks the brief
against the engine's limits (`brief.check`): a 30-60 s length, a near-fail ending with 1-3 s left, a time-out
leaving one block, a cliffhanger cutting with 1-3 blocks left, at most 3 mistakes or 2 hesitations, a clock value
only on a win, events the engine knows (first, next, last; stuck by a colour; moved into a colour's way), and so
on. Every adjustment is written into the brief, so the user reads why in plain words. Post-rules fix what the
model reads loosely: the blocking move, the mistake count from the words, the image's role.

## 2. Build the level (code, no model)

`resolve_level`: a shipped level when the prompt names one, else the generator (`generate.py`) searches boards to
the spec (shape: open, narrow centre, walled with several separate walls, ring; size; block count; colours, spread
and kept apart; piece kinds; difficulty band from a solver rating; the first interaction the prompt asks for, such
as "yellow stopped by green" or "yellow moved into green's way", which the board must offer at the start). Every
candidate is solved (A* with the game's exact rules) and rated: minimum drags, repositioning drags, blocks that can
leave at once, a casual player's ratio, looks.

**Level gate**: the asked-facts audit runs on the board alone (block count, colours, a named colour's count, the
blocked attempt or blocking move offered). A miss the generator can fix makes it generate again with another seed,
up to the gate's tries, and the board with the fewest misses is used; what is still missed is reported.

## 3. Plan the play (code)

`play.plan`: a believable human play toward the asked ending on that board: the drags from the solver's solution,
the mistakes (blocked, wrong way, fidget, a stuck attempt by the named block, a block moved into the named victim's
way), the hesitations, the pacing curve (even, speeds up, slows down), fitted frame by frame so the clock lands on
the planned second (00:02 at the last exit for a near-fail; one block one cell short at 00:00 for a time-out; a
block pushed into its blocker at the cut for a cliffhanger). A dry run predicts every frame.

## 4. Record in the real game (Unity, deterministic)

`ensure_recording`: the Unity CreativeRunner plays the planned drags in the real game, which enforces its own rules
at every frame (one block per drag, continuous collision, the exit rule while dragging), and writes result.json
(each drag's block, cells, outcome, the clock), play.json (the beats), frames.json (the timer per frame), the
frames, the HUD label. A recording is cached by its spec: the same spec gives the same film.

## 5. Compose the ad (code)

`build_and_render`: the hook and the captions (from the concept, on the moments the play has: the mistake, the
fix, the hurry, the result; fallbacks to the nearest moment), the cursor, the replay, the result screen or the
cliffhanger's question, the held result, the end card, the sound effects on events, the music if asked, the
camera's punch-ins, the background and the block colours if asked. Render QA refuses a layer outside its segment,
a caption that does not fit the band, a changed source. Then the parts manifest (`parts.json`): every part, every
layer with its seconds and box, every moment on the ad's clock, every whole second of the game's timer, so the
edit side later needs no video analysis.

## 6. Evaluate (code, measured, and a vision model, judged)

Profile "text" (`audit.workflow`): the board, the play, the rules, the asked facts, the brief's rows.

- Level and play checks (`checks.py`): the planned drags played as planned; the ending from the game's status and
  clock; mistakes and who stopped whom; the order of interactions; the satisfying finish; the pacing curve;
  difficulty, block count, shapes, looks, a named block.
- Rules rows (`audit.rules_rows`): the recorder's drags replayed through the Python port of the game's C#.
- Asked facts (`audit.asked`, read from the prompt itself, never the plan): counts, colours, difficulty, shape,
  style, length and the brief's 30-60 s, seconds left, mistakes, hesitations, the clock, walls, the HUD number,
  blocks per colour, the blocked attempt, the blocking move, the order, the ending, the satisfying finish, each
  quoted caption and its moment, the cursor, the background, the music, the sequence (win first, replay, end
  card, result screen), the game's own look, "gameplay at the centre" (p.2). Each row says pass or failed and which
  stage missed it (plan, level, play, ad); a "facts read" row lists what the audit recognised.
- The viewer's review (`review.py`): a contact sheet (one frame a second) with the measured facts (first move,
  dead time, each caption's time on screen) given to a vision model, which answers per control match / partial /
  no, scores pace, readability, clarity, call to action, would download, up to three fixes, and one edit prompt.

## 7. Feed back and revise (up to 2 rounds, on by default)

`create.feedback`: the measured misses first (facts), then the viewer's first fix when a control was marked no or
partial. The feedback is an edit request in the marketer's voice ("Revise this version so the original request is
met; change only what these points need. The original request was ... What the made version missed: ..."). The
planner reads it against the current brief; if it changes nothing, the version stands with its report. A miss in
the board, the play or the length makes the revised version a new take (another seed, the level gate again); a
miss in the ad only re-composes. Every version is kept (v1, v2, v3) with its own checks, review and manifest. The
loop stops when nothing measurable is missed, when the planner finds nothing to change, or after two rounds.

## What a run produces (per version, in studio/<creative>/vN/)

brief.json, level.json, board.png, the recording (result.json, play.json, frames.json, gameplay.mp4), ad/ad.json,
ad/compose.json, ad.mp4, poster.png, parts.json, review.json, review_sheet.png, version.json (checks, stages,
evaluation profile, revision record).

## Changed on 2026-10-16 from the scenario batch (12 prompts, Claude planner, loop on)

- step 2: the generator fits the time-out's hidden step ("an unnamed block leaves last") and rejects boards where the
  asked order only works with a named block last; a stuck step that names the blocker is honoured by relabelling two
  colours on the blocks and their doors (the same puzzle) when the board offers the attempt with another colour;
- step 3: the order search tries 8x deeper before giving up; when only the time-out's last step fails, the order is
  kept and the last named block is cut short; a clock the request names runs as named (the red HUD under 0:50 is
  noted, not avoided);
- step 7: a revision keeps the asked length and ending; a round whose change made no difference is "unchanged", not
  "failed"; a length miss forces a new take;
- caches: the generator's and the play planner's versions are part of the level and recording keys;
- evaluation: the clock row reads the recording the game ran (and reports an engine adjustment with its reason), the
  length regex ignores "60-second clock", "gives the red block room to move" is not a spacious board, "the clock runs
  out" is a time-out.

## Known limits (as of this morning's runs)

- A blocking move the prompt names ("yellow into green's way") must be offered by the generated board; the search
  penalises boards that cannot show it, but it is not guaranteed on packed boards.
- Small boards in 40-45 s ads leave play at a third of the ad; the "gameplay at the centre" row now flags it and the
  loop shortens held screens, but a 4-block board cannot fill 45 s of play.
- The viewer's model sometimes answers in prose instead of JSON; that review is stored as an error, not a verdict.
- The audit's regexes decide what is measured; a phrasing they miss gives no row (visible in "facts read").

## Modules, prompts, skills and files, step by step (paths under ~/cbj-work/)

Models: the planner is chosen by `CBJ_PLANNER` (`cbj-creative/src/cbj/llm.py`): `claude` = the Claude Code CLI on
this machine (`claude -p --json-schema`, opus, low effort, about 20 s a brief; `ClaudeCliVision` reads images
through the CLI) or `nvidia` = Nemotron through NVIDIA build (`NVIDIA_API_KEY` in `cbj-creative/.env`; planner
`planner.NvidiaClient`). Vision for references, the review sheet and the locate step: `reference.VisionClient`
over `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning`, falling back to `nvidia/nemotron-nano-12b-v2-vl`
(`reference.py:30`). Start the UI with `CBJ_PLANNER=claude uv run cbj ui` from `cbj-creative/`.

| step | code (cbj-creative/src/cbj/) | prompts the model sees | other files it reads or writes |
|---|---|---|---|
| 0 dispatch | `app.py` (`/api/plan`, `/api/make`, jobs one at a time), `workflows/__init__.py`, `workflows/create.py` (this side), `workflows/edit.py` (the other side, not used here) | none | `static/index.html` (the UI, "Create a creative" side) |
| 1 understand | `planner.py` (`plan`, `SYSTEM` at line 31 to 119: the brief's schema in words, the eight controls, the engine's limits, the "blocks" and "stuck" actions; `_blocking_move`, `_mistake_count_from_words`, `_reference_files` post-rules), `brief.py` (`SCHEMA`, `check`, `default_brief`, `CONTROLS`, `ENDINGS`, `MAX_HESITATIONS`, `CLOCK_LEFT_RANGE`, `LENGTH_RANGE_S`), `reference.py` (`IMAGE_ASK` line 156, `VIDEO_ASK` line 160, `is_reference_prompt`, `NAMED` colours), `imageref.py` (`role`, `style_kit`, `board_facts`, `apply`), `llm.py` | `planner.SYSTEM` + the request + the route text (edit side only) + the manifest text (edit side only); `reference.IMAGE_ASK` / `VIDEO_ASK` per attached file | uploads in `cbj-creative/studio/uploads/`; game sprites listed from `CBJ/Assets/Sprites/UI` (`draw.PROJECT`, `draw.SPRITES`); music by extension (`brief.AUDIO_EXT`) |
| 2 level | `studio.py` (`resolve_level`, `_level_gate`, `hud_label`), `generate.py` (`Spec`, `generate_for_brief`, `holes_for`, `_assign_colours`, `_events_fit`, `GATES_VERSION`), `solver.py` (`solve_fast`, A*), `difficulty.py` (`rate`, bands), `rules.py` (the C# port), `level.py` (`load_level`, `validate`, `LevelData` fields), `boardedit.py` (a gate moved, a wall added when asked), `audit.level_misses`, `checks.level_checks` | none | shipped levels `cbj-creative/data/levels/Level_01..06.json` (copies of `CBJ/Assets/Levels/`), their solutions `data/solutions/`, generated boards `studio/levels/`, the brief's example `data/levels/gen/narrow_center_01.json` |
| 3 play | `play.py` (`plan`, `blocking_moves`, `blocked_attempts`, `hesitation`, `PACING_VERSION`), `events.py` (`from_brief`, `check_events`, `ACTIONS`), `describe.py` (block labels, colour names, the move script) | none | `play.json`, `spec.json` in the recording folder |
| 4 record | `render.py` (`Camera`, `level_label`, the job for the runner; `RUNNER_SRC = cbj-creative/unity/CreativeRunner`), `studio.ensure_recording` (cache by spec) | none | the Unity project `CBJ/` (scripts `Assets/Scripts/`: `GameManager.cs`, `GridManager.cs`, `Block.cs`, `LevelManager.cs`, `Camera/CameraController.cs`, `UI/WinMenu.cs`, `UI/FailMenu.cs`); the built player; output `studio/recordings/<sha>/` (`job.json`, `level.json`, `result.json`, `play.json`, `frames.json`, `gameplay.mp4`, `NN_drag.png`) |
| 5 compose | `ad.py` (`build_ad`, `AD_OPTIONS`, captions and their moments, `reading_s`), `compose.py` (`build_and_render`, render QA, `diff`), `draw.py` (the game's font and sprites), `sound.py` (effects synthesized in code, the music track), `video.py` (ffmpeg), `formats.py` (1:1, 4:5, 16:9 from the 9:16 master), `parts.py` (`build`, `write`, `text`: the manifest), `edits.py` (`inventory`: what an ad contains) | none | `studio/<creative>/vN/ad/ad.json`, `compose.json`, `ad.mp4`, `poster.png`, `audio.wav`; `vN/parts.json`; sprites from `CBJ/Assets/Sprites/UI` (coin pile, stopwatch, buttons, `StartBACKGROUND.png`); fonts from the project |
| 6 evaluate | `checks.py` (`gameplay_checks`, `level_checks`), `audit.py` (`asked`, `level_rows`, `ad_rows`, `rules_rows`, `workflow`, `rows`, `misses`, `facts_read`, `_caption_moment_rows`), `review.py` (`facts`, `measured_scores`, `contact_sheet`, `question`, `review`, `RUBRIC` line 36) | `review.RUBRIC` + the request + the brief's control rows + the measured facts + the contact sheet image (and `route.LOCATE_ASK` line 630 only on the edit side) | `vN/review.json`, `vN/review_sheet.png`; the checks in `vN/version.json` |
| 7 feed back, revise | `workflows/create.py` (`feedback`, `revise_once`, `MAX_REVISIONS`), `audit.feedback`, `planner.plan` with `current=` (the brief being revised, no route), `studio.make(..., asked=<original prompt>, workflow="create")` | `planner.SYSTEM` + the feedback text ("Revise this version so the original request is met ...") + the current brief + the inventory + the history of versions | the next `vN+1/` folder; `version.json` carries `revision` (of, status, feedback) |

Skills (for Claude Code when it works on the repo; the product does not read them): `cbj-creative/.claude/skills/`
- `cbj-prompt-controls/SKILL.md` (+ `references/full-prompt-examples.md`): the eight controls, what each phrasing maps to, the audit's facts;
- `cbj-level-gameplay/SKILL.md`: core requirement 2, the generator, the play planner, the endings;
- `cbj-game-rules/SKILL.md` (+ `references/mechanics.md`, `references/level-format.md`): the Unity rules and the level JSON;
- `cbj-creative-review/SKILL.md`: the viewer's review and the loop;
- `cbj-creative-evidence/SKILL.md`: where every fact of a made creative lives and how to verify it;
- `cbj-controlled-editing/SKILL.md` (+ `references/acceptance-rules.md`): the edit side;
- `scripts/validate_skills.py`: the skills' validator.

Tests: `cbj-creative/tests/` (29 files; the ones for this side: `test_rules.py`, `test_solver.py`, `test_generate*.py`,
`test_play*.py`, `test_ad.py`, `test_compose*.py`, `test_audit.py`, `test_audit_fixes.py`, `test_eval_case.py`,
`test_review*.py`, `test_app.py`, `test_case_fixes.py`, `test_unity_render.py` which starts Unity).

Docs: `cbj-creative/README.md` (sections "Text to creative", "Level & gameplay generation", "The viewer's review",
"Two workflows, one evaluation each", "Reference images and videos"); the brief mapping `EVAL-COVERAGE-2026-10-16.md`;
the test folders `t2c-audit-2026-10-15/`, `t2c-variants-2026-10-15/`, `t2c-scenarios-2026-10-16/` (each with
`PROMPTS.md`, `run.py`, `analyze.py`, `REPORT.md`, `creatives*/`, `results*/`), the harness
`case-test-2026-10-13/harness.py` they share.
