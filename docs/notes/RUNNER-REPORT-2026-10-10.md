# Day 4 report: recording the real game (Unity CreativeRunner), 2026-10-10

## Aim

Turn a level file plus a move script into a 9:16 gameplay video **with no human
input**, using the real game rather than a re-drawing of it. That was the "done
when" line for this step of the plan: *Level 3 + its moves JSON → 9:16 MP4.*

**Which part of the brief this covers.** Every example the brief asks for needs
real gameplay video: text-driven, image-driven, video-reference-driven and the
controlled edit. Two of the grading criteria hinge on it:
- **Gameplay consistency:** blocks obey the game's rules in every frame. This is
  guaranteed because the game's own code moves them.
- **Controlled editing:** "change one thing, keep the rest". This needs renders
  that repeat, so a difference can be traced to the edit.

It also finishes the open item from day 3, checking the solver's solutions in
Unity. The game now does that check itself, for all six levels.

## What was built

| Piece | What it does |
|---|---|
| `unity/CreativeRunner/CreativeRunner.cs` | Runs inside the game only when started with a job file. Loads the level, places the camera for 9:16 with the game's own fit formula, and plays each drag with a scripted finger. Every frame it makes the same calls the game's mouse handler makes. Records 1080x1920 frames with the HUD into ffmpeg and checks each drag against the script. |
| `unity/CreativeRunner/Editor/CreativeRunnerBuild.cs` | Builds the recording player in batch mode. |
| `src/cbj/render.py` | Checks the script with the rule replay first, writes the job, runs the player, cross-checks the logs against the video, and compares two recordings. |
| CLI | `cbj build-player`, `cbj render LEVEL [MOVES] [--end win\|cut\|fail] [--drags N]`, `cbj compare A B` |

Your Unity project is never modified. The build works on a copy in
`cbj-creative/build/`, so the editor can stay open.

Each recording writes:
- `gameplay.mp4`;
- full-size stills;
- `result.json`: the status, the frame of the first touch, each drag's frames
  and cells, the win or fail frame, and the timer at each point;
- `frames.json`: for every frame, the timer, the finger position in video
  pixels (for a hand cursor later) and a pixel hash.

## What was tested, and the results

| Test | Expected | Result |
|---|---|---|
| Level 3 from the solver's script | 3 exits, win screen | Cleared: 186 frames, 6.2 s, win at 3.67 s with 04:57 left |
| All six shipped levels | Every drag enters exactly the planned cells | **6/6 cleared.** Level 4's repositioning drag shows as `placed`, as the solver predicted |
| Same job twice | Same game, same pictures | Game state identical every time. Pixels identical in nearly every frame (see limits) |
| Cliffhanger (`--end cut --drags 2`) | Ends with a block on the board | `unresolved`, 4.87 s, red block left |
| Time-out (timer set to 4 s, `--end fail`) | The game's own fail screen | "Out of Time!" exactly 4 s after the first touch, one block left |
| Wrong scripts fed to the runner | Caught, with the reason | Wrong start cell, a drag into another block, an unplanned exit, a missed exit, a path off the board: all caught as `mismatch` |
| Broken runs | End cleanly, never hang | Missing level, bad job, ffmpeg dying: all end as `error` with a reason |
| Tests | All pass | 158 fast tests and 14 Unity tests at this point; after the re-check and decisions below, 195 fast tests and 22 Unity tests (24 player runs, about 4 min) |

Picture strips are in `cbj-creative/reports/runner/`: Level 3, Level 6, and the
Level 3 time-out.

## Fable 5.1 review

Fable reviewed the runner independently and made 29 player runs of its own. It
found 2 major issues, 7 minor ones and 2 nits. What was done about each:

| Finding | Done |
|---|---|
| **MAJOR:** if ffmpeg died mid-recording, the player hung until a 15-minute timeout | Fixed. Capture errors end the run with `error`, plus a safety net that always writes the result. Covered by a test |
| **MAJOR:** "same job → identical frame hashes" did not hold; 1–4 frames of 385 differed between runs | Investigated (below). The claim is now honest, and comparison uses a tolerance |
| `--end cut` with a script that clears the board was always flagged | Now refused up front with a clear message |
| A path cell off the board crashed instead of being reported | Now reported as `mismatch: path cell (3,-1) is not an active cell` |
| The runner accepted nonsense hand-written jobs | Now checked at start: end mode, empty drags, negative or invalid timings, fps, size |
| The timer running out mid-drag was labelled a mismatch | Now `interrupted`; the fail ending passes |
| Old stills survived a re-render | Removed before each run (only the runner's own file names) |
| A finger faster than one cell per frame was silently capped | `make_job` refuses more than half a cell per frame (15 cells/s at 30 fps) |
| Block lag differs at 30 fps from a 60 Hz phone; the 1.5 s camera glide is not played; the project's `Library/` folder is copied while the editor is open | Written in the README. `--fps 60` gives the phone's feel |

Fable confirmed as correct:
- The drag code matches the game's mouse handler line by line.
- The pivot cannot skip a cell at any tested speed (5 to 120 fps).
- Frame numbers line up with the video.
- Colours, image orientation, UI scale and camera framing are right.
- Exceptions in the script end cleanly.

**The repeatability investigation.** I ran Level 6 four times on each variant:
- Particle seeds fixed: still 1–3 frames differed per pair.
- Every particle's position, size and lifetime logged per frame: identical in all runs.
- One particle step per frame, MSAA off, and shader warm-up: each tried in turn, no change.

So the leftover differences come from the graphics driver, not the game. They
are a few pixels in about 1% of frames, at random positions; the worst frame
scored about 45 dB PSNR, which looks identical to the eye. Full-size renders
usually match on every frame. The experiments that didn't help were taken out
again.

## Honest limits

- **Pixels are near-identical, not guaranteed identical.** The controlled-editing
  proof on Oct 13 will compare in three parts: game state exact, the count of
  identical frames, and the lowest frame PSNR. That's what `cbj compare` reports.
- **There's no sound yet.** The game has no audio at all: no sound files and no
  sound code. The compositor will add sound effects at the exit and win frames
  from `result.json`.
- **There's no hand cursor yet.** The finger position is logged per frame for the
  compositor to draw one.
- **It records at about 2x real time** (a 6 s video takes about 13 s), so a 40 s
  creative should take about 1.5 minutes.
- **The game rounds the clock down,** so it shows 00:00 during the last second.
  A "won at 0:01" ending needs the last block to start leaving with 1–2 s left
  (the recorder stops the clock at that moment; see the re-check below).

## Case re-check (later on Oct 10)

You asked me to check days 3 and 4 against the brief and fix anything missing
or wrong, with Fable 5.1. I re-read all 14 pages; Fable checked the plan, the
reports and the code independently against the PDF and the game's C#.

**Missing for these two components, now added:**

| The PDF asks for | What was missing | Added |
|---|---|---|
| "A difficult or easy level" | Only drag counts | `cbj difficulty`: board numbers plus a simulated naive player. Finding: the shipped levels are tutorial-easy. On 5 of 6, an exit is always available, so even the naive player never wastes a drag; only Level 4 needs a block moved first. "Difficult" needs generated levels |
| Camera and composition as controls that an edit must keep | Fixed camera only | Zoom, pan and eased camera keys; `--intro` replays a level-start glide. Changing only the camera leaves the game identical, and `cbj compare` shows it |
| 30–60 s creatives | Recordings were 5–13 s | Pacing flags (`--speed --pause --start-hold --end-hold`); Level 6 now records at 29.3 s |
| Timing control for near-fail and time-out ads | The timer could only change by writing a new level file | `--timer` overrides the clock in the job |
| A clean, ad-ready frame | The restart button is part of every recording | `--hide RestartButton` |
| Sound effects, captions, hand cursor (compositor) | Missing event data | Per-frame block positions, the frame each block disappears, gate numbers, HUD rectangles, the clock-stop frame |

**A logic error in the game, found by you in the video and by Fable in the code.**
The game keeps its clock running while the last block slides out, and counts
the win only when the slide ends. If time runs out in that half second, it
shows "Out of Time!" and then "Level Completed". It's now fixed in the game
code (see "Decisions" below). `cbj render` rejects any video that shows both
screens. The strip is
`cbj-creative/reports/runner/clock_bug_top_vs_fixed_bottom.jpg`: top is the game
as shipped, bottom is fixed.

**Wrong or outdated statements, corrected:**
- The plan, sections 2–4:
  - The exit rule: it is checked only during a drag, uses the first gate in file order, and never fires on release.
  - The render scene is GameScene, not LevelTestScene.
  - The clock behaviour and near-fail timing.
  - The solver is plain BFS with exit-first, not A*.
  - The generator approach, and its speed on dense boards.
  - The recorder as actually built: it pipes frames to ffmpeg rather than writing PNGs, and the batch-mode wording.
- The solver report and guide: test and commit counts, and "44 failed" (really 38, plus 6 tests of a reader that didn't exist yet).
- This report: the "game sounds" line.
- The README: "only the mouse is replaced" now lists everything the runner changes.
- The competitor-ads report: the exit-slide timing formula.

**Scheduled, not built (Fable's points):**
- The compositor had no day; it is now on Oct 12, next to the generator.
- The asset slots the game can actually swap are decided and written into the plan (block colour materials, gates, cells, background, HUD); they get built on Oct 13. The game has no "obstacles" other than holes and borders.
- The generator must build levels forward with a state cap, because a full search on dense 6x6 boards can pass 60,000 states.
- Generated levels get a spot check in Unity, since the recorder's cell-by-cell check is the only guard between the Python rules and the game.

## Decisions (with Fable 5.1, after re-reading the brief and the ad research)

**1. The game bug: fix it in the game code, applied to our build copy only.**
- **What:** `cbj-creative/unity/game-patch` is a small patch to the publisher's game:
  31 added lines in `GameManager.cs`, `ExitService.cs` and `InputHandler.cs`,
  each marked `cbj-creative patch`. It does three things:
  - the clock stops when the last block starts its exit;
  - once one ending has shown, no other can follow;
  - the board takes no drags after an ending.
- **A second path, found by Fable:** after "Out of Time!" the game still
  accepted drags, so a player could clear the board behind the fail screen and
  get both screens that way too. The patch closes it.
- **How it's applied:** `cbj build-player` applies the patch to its copy of the
  project. Your `~/cbj-work/CBJ` stays byte-identical to what the publisher sent, and
  a test checks that.
- **Why not leave it in the recorder only?** The brief grades "does Color Block
  Jam behave like a game" and engineering quality. A fix inside the game's own
  logic is cleaner than the recorder reaching into a private field, and it also
  closes the second path, which only the game can fix.
- **Why not edit your project directly?** the publisher's files stay untouched, so they
  can see exactly what we changed (`game.patch`, plus the originals saved next
  to it). If they meant the behaviour, they drop one folder.
- **The proof:** `cbj build-player --stock` builds the game as shipped, and
  `cbj render --stock` shows the bug. The normal build ends cleanly: the clock
  stops 0.1 s after the last block starts leaving, at the end of its snap. Four
  Unity tests cover the stock game, the patched game, and the recorder's own
  clock stop on a stock game.

**2. Fail endings: S5 opt-in, S6 only if time allows, near-fail win as the showcase.**
- **Default endings:**
  - the clean win (S3);
  - the near-fail win (S4) when the prompt asks for "difficult" or "almost fails";
  - the cliffhanger (S1) on request.
- **Why:**
  - The brief's own example asks for "almost fails before solving it", never a fail.
  - CBJ's own ads avoid staged fails: none of its ads among the
    roughly 136 ads we pulled (CBJ and rivals) shows one.
  - Most of its ads run on ad networks (Insightrackr: AppLovin 26%, Mintegral
    23%, Facebook 10%), where success endings did better (AppsFlyer: +33% installs
    per thousand impressions for casual games).
  - S4 is the gap nobody runs.
- **S5 (time-out with one block left, the game's real "Out of Time!" screen):**
  - It ships as an opt-in variant, chosen only when the prompt explicitly asks
    for a fail, or for a social-media test where fail endings did better
    (AppsFlyer: +65%).
  - It costs almost nothing: it's the same level and moves as the win version,
    with a shorter clock. The edit is one number, which is itself a clean
    controlled-editing demo.
  - It waits for medium-hard generated levels. On the tutorial-easy shipped
    levels, a time-out would look staged.
  - A "fake fail" request becomes a real time-out, and the tool says so.
- **S6 (fail, "try again", then win):** built only if the clip-joining in the
  compositor (needed anyway for the hook and end card) is done on Oct 12, with
  2 hours at most. Otherwise it goes under "next steps" in the write-up.
- **For the write-up:** "Fail endings are a channel variant, off by default,
  because your own ads avoid them; when used, they are real time-outs on real
  levels, and the proof shows the same level and moves as the success version."

## What's next (Oct 11 in the revised plan)

Scenario scripts on top of this recorder (the generator and compositor follow on Oct 12):
- a timing model;
- believable wrong moves and hesitations;
- a level timer chosen so the clock lands on 0:01 (near-fail win) or 0:00 with
  one block left (time-out);
- cliffhanger cut points.

The first target is S4, the near-fail win, from the brief's own example prompt,
on a hand-made narrow-centre level until the generator exists.

## Files

- Repo: `~/cbj-work/cbj-creative`. New: `unity/CreativeRunner/`,
  `src/cbj/render.py`, `tests/test_render.py`, `tests/test_unity_render.py`,
  `reports/runner/`.
- Step-by-step check: `~/cbj-work/RUNNER-CHECK-STEPS.md`.
- Videos: `cbj-creative/renders/` (not in git).
