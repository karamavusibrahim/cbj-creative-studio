# Rollic "AI Engineer, Creative" case: analysis and 10-day workflow

Prepared 2026-10-08 from the PDF in ~/Downloads ("AI Engineer, Creative Case Study.pdf", 14 pages),
the CBJ Unity project in the Drive folder (downloaded to ~/rollic-case/CBJ), and research on
Rollic's live creatives, Higgsfield, NVIDIA build and Unity tooling. Everything marked VERIFIED was
read in the code or tested on your machine today. The deadline is 10 days from receipt; the PDF
landed 2026-10-08 00:02, so plan for submission on 2026-10-17 and confirm the exact date from the
email.

---

## 1. What they are actually asking

Build a tool where a marketer types a sentence (optionally drops an image or a video) and gets a
30-60 s Color Block Jam (CBJ) ad creative back, then asks for one change and gets a revised version
where only that one thing changed.

The PDF repeats one idea on five of its fourteen pages: consistency and controlled editing matter
more than visual spectacle. Page 8 says it openly: pure generative video drifts, so use Unity for
gameplay and AI around it. Page 13 says a focused, reliable tool beats a broad, flaky one. Page 11
lists ten grading criteria. Read together, the hidden rubric is:

| Criterion (p.11) | What will actually score |
|---|---|
| Creative quality | Looks like a real CBJ ad: real gameplay, tactile pacing, a hook, an unresolved or satisfying ending |
| Controllability | "Replace this asset" changes only that asset; show it with a diff, not a promise |
| Gameplay consistency | Blocks obey the game rules at every frame. Only a real engine gives you this |
| Multimodal understanding | Image: knows if it is a reference, a style or an asset to insert. Video: extracts structure and pacing, not pixels |
| System design | Deterministic core, generative shell. Explain why |
| AI usage | AI where it adds value (intent, planning, level generation, asset generation, reference analysis, QA), not where it hurts (rendering gameplay) |
| Engineering quality | Typed spec, tests for the solver, reproducible renders, clear repo |
| User experience | One prompt box, one drop zone, Generate, Review, Request change |
| Extensibility | The same spec and pipeline could serve other Rollic games and playables |
| Decision making | Honest limitations and a production roadmap |

Required deliverables (p.12): working prototype, source + setup, at least one text-driven, one
image-driven, one video-reference-driven and one controlled-modification example, plus a short
technical explanation covering architecture, components, why, deterministic vs generative parts,
consistency, controlled editing, limitations and production next steps.

---

## 2. What is in the Unity project (VERIFIED from code)

Location: ~/rollic-case/CBJ. Core scripts: 3,784 lines of C# in Assets/Scripts plus a
1,100-line Level Editor window. Six example levels in Assets/Levels.

| Fact | Detail | Why it matters for you |
|---|---|---|
| Unity version | 6000.3.5f1 (Unity 6.3) in ProjectSettings/ProjectVersion.txt | Install exactly this version |
| Packages | com.unity.mathematics, com.unity.postprocessing, ugui; plugins DOTween (Demigiant), Toony Colors Pro, QuickOutline, Epic Toon FX, ParticleImage, TextMesh Pro | All bundled in Assets/Plugins; no store purchase needed |
| Level format | Plain JSON (LevelData): gridWidth, gridHeight, timerCount (seconds), inactiveCells, GridBlockDatas[gridPosition, blockColor, shapeOffsets], ExitDatas[gridPosition, requiredColor, direction, shapeOffsets] | A level is text. An LLM or a procedural generator can write it, a solver can verify it, and the game loads it without touching Unity |
| Colours | enum BlockColor: Green 0, Yellow 1, Blue 2, Red 3, Orange 4, Purple 5, DarkGreen 6 | Seven colours, materials already set up per colour |
| Blocks | Arbitrary polyominoes (shapeOffsets); rendered from modular corner/edge/straight/end pieces | "Visually interesting board" means interesting shapes, and the renderer handles any shape |
| Exits | Sit on a border cell with a direction (Left/Right/Top/Bottom) and a span (shapeOffsets); exit numbers auto-assigned | Exit = colour + edge + span |
| Exit rule | ExitService.CanBlockExit, checked only while a block is dragged, each time its pivot enters a new cell. The FIRST gate in file order with the block's colour that overlaps the block is chosen; every block cell then needs a clear straight lane to the edge through that gate's rows or columns. Releasing never exits; a block resting at its gate must step away and back (corrected 2026-10-10, verified in the C#) | Implemented exactly in cbj-creative/src/cbj/rules.py |
| Movement | Free 2D drag (BlockMovementService) with continuous collision and axis sliding, not row-locked sliding | For the solver, discretise to cell positions; for playback, drive the same service with scripted targets |
| Timer | Counts down from timerCount (whole seconds), starts on first touch (GameManager.StartTimer), fail at 0. The win counts only when the last block's exit slide ends, and the clock keeps running during that slide, so the game can show "Out of Time!" and then "Level Completed". The HUD rounds down (00:00 during the last second) | The recorder stops the clock when the last block starts to leave (stop_clock_on_last_exit). Near-fail = the last block starts leaving with 1-2 s showing, set by pacing (corrected 2026-10-10) |
| Level loading | LevelManager reads Application.dataPath/Levels/<name>.json, also LoadLevelFromTextAsset and a PlayerPrefs "Editor_TestJSON" path | Three ways to inject a generated level without rebuilding |
| Camera | CameraController fits the board for orthographic or perspective camera with padding and a vertical offset, with a 1.5 s glide at level start | The recorder uses the same fit for 9:16 and adds zoom, pan and eased keyframes; tilt stays the scene's |
| Scenes | GameScene, LevelTestScene, MenuScene, Visuals | GameScene is the render scene (it has the HUD, win and fail screens); LevelTestScene is the editor's test scene |

Rules in one paragraph (for prompts and for the technical write-up; corrected 2026-10-10): a
rectangular grid with optional holes holds coloured polyomino blocks. Coloured gates sit on the
border or on the rim of a hole. The player drags a block anywhere it fits. While dragging, each time
the block's pivot enters a new cell, the game checks the first gate of the block's colour that the
block touches: if every block cell has a clear straight lane to the edge through that gate, the block
snaps, slides out and disappears. Letting go never makes a block leave. Clear every block before the
timer ends. The game has no audio.

---

## 3. The architecture to build: deterministic core, generative shell

```
                 user prompt + optional image/video
                                │
                     ┌──────────▼──────────┐
                     │  Intent + Planner   │  LLM (Nemotron on NVIDIA build, Claude optional)
                     │  → CreativeDoc JSON │  picks a concept template, fills parameters,
                     └──────────┬──────────┘  or emits a DIFF against an existing CreativeDoc
          ┌─────────────────────┼──────────────────────┐
┌─────────▼────────┐  ┌─────────▼─────────┐  ┌─────────▼─────────┐
│ Level generator  │  │ Reference analyst │  │ Asset generator   │
│ + Solver (Python)│  │ frames → VLM      │  │ Nano Banana Pro   │
│ difficulty, near-│  │ structure, pacing │  │ bg, props, chars, │
│ fail, solve path │  │ hook, text, end   │  │ "replace object"  │
└─────────┬────────┘  └─────────┬─────────┘  └─────────┬─────────┘
          └─────────────────────┼──────────────────────┘
                     ┌──────────▼──────────┐
                     │ Unity CreativeRunner│  deterministic: loads level JSON, plays the
                     │ fixed timestep 30fps│  scripted move list through the game's own
                     │ PNG frames + events │  services, drives camera, dumps frames + event log
                     └──────────┬──────────┘
                     ┌──────────▼──────────┐
                     │ Compositor (ffmpeg) │  overlays, captions, SFX, optional AI hook/outro
                     │ + QA judge (VLM)    │  clips (Seedance/Kling) stitched with matched frames
                     └──────────┬──────────┘
                                │
                   MP4 9:16 + CreativeDoc + render manifest (hashes)
```

**The single idea that wins the case:** every creative is fully described by one typed document,
the CreativeDoc. Generation writes a CreativeDoc. Editing writes a diff to the CreativeDoc.
Rendering is a pure function of the CreativeDoc. So "keep everything the same but replace this
asset" is a one-field change followed by a re-render in which every untouched layer is
bit-identical. You can prove it with per-segment frame hashes or PSNR, and you should show that
proof in the UI and in the write-up.

### CreativeDoc (sketch)

```jsonc
{
  "id": "crt_0012", "parent": "crt_0011", "duration_s": 32, "aspect": "9:16",
  "concept": "near_fail_solve",                 // from the concept library
  "level": { /* LevelData JSON exactly as the game reads it */ },
  "play": { "moves": [{"block": 3, "to": [2,1], "t": 1.2}, ...],  // from the solver
            "pacing": "hesitant_then_fast", "finish_margin_s": 1.5 },
  "shots": [{"t0": 0, "t1": 3, "camera": "tilt_in", "zoom": 1.15}, ...],
  "overlays": [{"t0": 0, "t1": 3, "text": "Can you beat this level?", "style": "ua_bold"}],
  "assets": { "background": "asset_bg_01.png", "mascot": null, "block_skin": "default" },
  "audio": { "sfx_pack": "tactile_clicks", "music": null, "vo": null },
  "segments": { "hook": {"source": "unity"}, "gameplay": {"source": "unity"},
                "outro": {"source": "unity"} }                          // or "ai_video" for hook/outro
}
```

### Concept library (makes text-to-creative reliable)

Build six to eight named templates and let the planner choose and parameterise one. Based on what
Rollic's own CBJ ads do (Segwise teardown: unresolved level endings, "no ads" message in text and
voice-over, tactile click SFX instead of music, low-poly characters walking in, slight camera shakes
and zooms) and what UA teams ask for:

1. near_fail_solve: hesitation, wrong moves, timer under 3 s, last block exits at 1 s.
2. unresolved_cliffhanger: cut before the last two blocks (Zeigarnik ending Rollic uses).
3. satisfying_clear: clean, fast solve, exit particles, "satisfying" pacing.
4. fail_bait: a deliberately wrong move sequence that jams the board, "can you do better?".
5. level_reveal: camera tilts from top-down to the game angle while the board builds.
6. no_ads_promise: gameplay plus the "no ads" text and VO hook.
7. mascot_react: a generated character sprite reacts at the corner of the frame (image-driven).
8. reference_adapt: structure cloned from a reference video (video-driven).

Each template is a CreativeDoc with holes. The planner fills the holes from the prompt
("narrow center section", "difficult", "almost fails") and the solver validates the result.

---

## 4. Components in detail

### 4.1 Level generator and solver (Python, no AI required, the heart of "gameplay consistency")

* State: tuple of block pivot positions. Moves: slide one block to any reachable cell position
  (BFS over the block's own free movement, respecting other blocks and inactive cells). Exit check:
  reimplement ExitService.CanBlockExit and IsPathClear exactly (colour match, overlap with the exit
  span, straight clear path for every part). Unit-test your solver against the six shipped levels
  (all six must be solvable, and solutions must replay correctly in Unity).
* Solver (built): breadth-first search over drags with one shortcut, take an available exit first
  (proved safe, cross-checked on 637 random boards); no heuristic. Fast on the shipped levels (at
  most 856 states). Fable's scaling test: dense 6x6 boards with 7-8 blocks often pass 60,000
  states (1.6-4 s each), so generated boards need a state cap.
* Difficulty (built, `cbj difficulty`): minimum drags, repositioning drags, blocks that can leave
  at the start, first-drag options, and a simulated naive player (takes any exit, else a random
  drag). On the shipped levels only Level 4 makes the naive player waste drags. To add: time slack
  from the recorder.
* Generator (Oct 12): the research replaced backward scrambling with dense pack → BFS → farthest
  state, but a full BFS per candidate is too slow for hundreds of dense candidates. Build forward
  instead: start from an easy base, add one blocking block at a time, re-solve with
  `solve(start=...)`, cap `max_states` at about 50,000 and treat the cap as "too hard", and spot-check
  a sample in Unity at small size (the recorder's cell-by-cell check is the oracle).
* Play script (Oct 11): the solver's solution plus believable detours from the naive player, with
  hesitations and a pacing curve. The clock rule: the recorder stops the clock when the last block
  starts to leave, so a near-fail win has its last exit start with 1-2 s showing. (Without that
  fix, the last exit would need to start at least its slide before the end: 0.1 s snap + 0.1 s gate
  dip + (cells to the edge + 2) x 0.1 s.) The level timer is whole seconds, so the margin is set
  with pauses, and `timer_s` in the job overrides the level's timer without a new level file.

### 4.2 Unity CreativeRunner (deterministic renderer) — as built on 2026-10-10

One runtime script and one editor build script in `cbj-creative/unity/CreativeRunner`; the game's
own files are not changed (the build works on a copy of the project):

* `CreativeRunner` reads a job file (`-cbjJob`), injects the level through
  `LevelManager.EditorTestLevelData` (optional `timer_s` override), disables `InputHandler` and
  `CameraController`, and re-implements `InputHandler`'s per-frame drag with a scripted finger
  through the game's own `BlockMovementService`, `BlockGridService` and `ExitService`. After each
  drag it checks the cells the block really entered against the script.
* Fixed timestep with `Time.captureDeltaTime`. The camera renders into a 1080x1920 sRGB render
  texture, overlay canvases are moved to ScreenSpaceCamera at a phone's scale, and frames are read
  with `ReadPixels` and piped as raw video to ffmpeg (PNG only for a few stills). Logs:
  `result.json` (status, drags with gate numbers, first touch, win/fail, clock stop, block gone
  frames, HUD rectangles) and `frames.json` (timer, finger and block positions in pixels, hash).
* Camera: the game's fit formula plus zoom, pan and eased keyframes (`--intro` replays a
  level-start glide). A `hide` list removes HUD parts such as the restart button.
* Run: the player is built in batch mode from the project copy and records in a small window
  (Unity Recorder is not used; it does not support batch mode). About 2x real time: a 29 s video
  took 42 s. Repeat renders give the same game exactly and near-identical pixels (about 1% of
  frames differ by a few pixels from the graphics driver), compared with `cbj compare`.
* Fallback if Unity blocks you for more than one day: a Python or Canvas "twin renderer" that draws
  the same LevelData and move list in a flat CBJ-like style. You lose some "creative quality" but
  keep every other criterion, and the solver and spec are engine-agnostic. State this trade-off in
  the write-up only if you had to use it.

### 4.3 Intent, planning and editing (LLM)

* Default model at demo time must be callable from the tool: use NVIDIA build
  (`nvidia/nemotron-3-super-120b-a12b` for planning, `nvidia/nemotron-3.5-lightning-30b-a3b` for
  cheap classification), with fallbacks, exactly the pattern you run in aiforgift. Offer Claude
  (`claude-opus-5-5` or `claude-sonnet-5-5`) behind an env var as the premium planner; mention both
  in the write-up.
* Structured output: the planner returns a CreativeDoc or a JSON Patch against the parent
  CreativeDoc. Validate with a schema (pydantic). Reject and retry on invalid output. The patch
  model is the controlled-editing story: "replace the blue blocks with the attached asset" becomes
  `{"op":"replace","path":"/assets/block_skin","value":"asset_user_01"}` and nothing else.
* Guard rails: a whitelist of editable paths per edit type; the planner cannot touch `level` or
  `play` unless the user asks about gameplay. Show the user the patch in plain words before
  rendering ("Only the block skin changes. Level, moves, camera and timing stay the same.").

### 4.4 Image inputs

* Role classification first (VLM: `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning`, fallback
  `meta/llama-3.2-11b-vision-instruct`): is this a style reference, a composition reference, an
  asset to insert, or a screenshot of an existing creative to modify? Confirm the guess in the UI
  with one line the user can override.
* Asset insertion: background-remove (Higgsfield `image_background_remover`), fit to a slot
  (mascot corner, background plane, block skin texture), store as a named asset referenced by the
  CreativeDoc. Insert in Unity as a sprite or quad, or in the compositor as an overlay layer. Both
  keep gameplay untouched.
* Style reference: extract palette and mood with the VLM, map onto allowed knobs (background
  colour, cell colour, light tint, overlay font style). Do not restyle gameplay frames with AI
  video; it breaks consistency.
* Generation: Higgsfield Nano Banana Pro (`nano_banana_pro`, 2 credits per image at 2k, up to 14
  reference images) for backgrounds, props and characters. Your aiforgift wrapper around the CLI
  already does this.

### 4.5 Video reference inputs

* Sample frames with ffmpeg (1 fps plus scene-cut frames), transcribe audio if any (Whisper
  locally or skip), and send a labelled contact sheet to the VLM with a fixed extraction schema:
  hook type and first-3-second content, on-screen text, pacing beats with timestamps, camera moves,
  whether the level is resolved at the end, presence of characters or VO, aspect ratio. Output
  becomes `reference_adapt` template parameters. This is exactly the "understand structure, not
  pixels" behaviour the PDF asks for on page 6.
* VERIFIED today: the hosted `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` endpoint accepts a
  video directly as a `video_url` content part with a `data:video/mp4;base64,...` URL (a 2 s test
  clip was described correctly on the second attempt; the first attempt hit a 503 capacity error,
  so keep retries with backoff). The model card lists mp4 up to 2 minutes, sampled at about 1 fps
  up to 128 frames. `nvidia/cosmos-reason2-8b` returned 404 for your account, so do not plan on it.
  Build both paths: direct video for structure extraction, and the frame-sampled contact sheet as
  the fallback and as the input for the per-frame judge.

### 4.6 Optional AI video, bounded on purpose

Higgsfield account today: plus plan, 656.5 credits (VERIFIED). Costs (VERIFIED with
`higgsfield generate cost`): Seedance 2.0 5 s 720p = 22.5 credits; Nano Banana Pro 2k = 2 credits.
Available and relevant: Seedance 2.0/2.5, Kling 3.0 Omni with start and end frames
(`kling_o3_flf`), Kling 3.0 Omni Edit (`kling_video_edit`), Genjutsu object swap and restyle
(`hf_mult_replace_object`, source clip 4-30 s), FLUX 3 Video Edit, Video Background Remover, Topaz
upscale.

Use AI video only for the hook (0-3 s) and outro (last 2-3 s), generated from the first or last
Unity frame as the start/end image so the cut is seamless, and only when the concept asks for it
(a mascot walking in, a dramatic reveal). Gameplay stays Unity. Evaluate Genjutsu object swap on
a gameplay clip once, keep the result as an appendix showing drift, and write one paragraph on why
you rejected it for the gameplay segment. That paragraph is worth more than the clip.

Budget: cap at about 150 credits for the whole case (6 clips plus 20 images). Confirm with yourself
before each paid batch; one sample first.

### 4.7 QA and regeneration loop

Reuse your aiforgift pattern: deterministic checks first (solver says solvable, playback event log
shows every expected exit, timer never negative, duration within 30-60 s, aspect 9:16), then a VLM
judge on a labelled frame montage for the soft criteria (hook present, text legible, no overlapping
UI, concept matches the prompt), then auto-fix by patching the CreativeDoc and re-rendering only the
failing layer. Log every judgement; show the last one in the UI.

### 4.8 User interface

One page: prompt box, drop zone (image or video), Generate. Result card with the video, a
plain-language summary of what was built ("Hard 6x6 level with a narrow centre, player hesitates,
solves with 1.4 s left"), and a "Request a change" box. Versions listed on the left; each shows the
one-line diff from its parent and a "what changed" strip (frame-diff heatmap or PSNR per segment).
No model names, no graphs, no parameters by default; an "Advanced" drawer can expose the CreativeDoc
for the reviewer.

Stack: FastAPI backend (Python, because the solver is Python) + a small Next.js page, or Gradio if
you are behind on day 7. Job queue in-process; renders run as subprocesses.

---

## 5. Scope: build deep, not wide

Build fully: text-to-creative for the eight templates, level generator + solver, Unity renderer,
CreativeDoc patch editing with proof, image role classification + asset insertion, video reference
analysis via frames, QA loop, simple UI, four required examples, technical explanation.

Build lightly: AI hook/outro clips (one or two examples), style transfer from an image (palette
only), VO (one TTS line if cheap, otherwise skip).

Do not build: generative gameplay video, free-form video editing, multi-game support, playable
ads, audio generation. Name each in "limitations and next steps".

---

## 6. 10-day plan (2026-10-08 → 2026-10-17)

| Day | Goal | Done when |
|---|---|---|
| 1 (Oct 8) | Environment. Install Unity 6000.3.5f1 (Unity Hub or `brew install --cask unity-cli` then `unity install 6000.3.5f1`), Personal licence, open CBJ, play the six levels, record a screen capture of each. Finish the project download (background job writes to ~/rollic-case/download-full.log; check all folders including .meta files exist). Repo skeleton, CreativeDoc schema v0. | Game runs on your Mac; schema committed |
| 2 | Solver. Port the exit and movement rules to Python, BFS solver, tests on the six levels, difficulty metrics. | All six shipped levels solve and the solution replays in the editor by hand |
| 3 | Unity CreativeRunner. Scripted move playback, fixed timestep, PNG capture, event log, CLI args, standalone build. ffmpeg assembly to MP4. | A level JSON + moves JSON → 9:16 MP4 with no human input |
| 4 | Generator + planner. Procedural level generator with constraints, planner prompt → CreativeDoc, three templates working end to end (near_fail_solve, satisfying_clear, unresolved_cliffhanger). | Prompt from p.4 ("difficult, narrow center, almost fails") produces a correct video |
| 5 | Controlled editing. JSON Patch flow, path whitelist, re-render with layer caching, frame-hash/PSNR diff report, versions in the data model. | "Keep everything, replace X" changes only X and the report proves it |
| 6 | Image inputs. Role classifier, background removal, asset slots (mascot, background, block skin), Nano Banana Pro generation for props. One sample before any batch. | Image-driven example rendered |
| 7 | Video inputs. Frame sampling, VLM structure extraction schema, reference_adapt template. UI first pass (FastAPI + page). | Video-reference example rendered; UI runs the full loop |
| 8 | QA loop, remaining templates, optional AI hook/outro via Kling frames or Seedance with matched start frame. Polish SFX pack and captions. | Four required examples final, plus two extras |
| 9 | Technical explanation (2-4 pages, mirrors their eight headings), README with setup, architecture diagram, limitations and production roadmap, 2-3 minute walkthrough video of the UI. | Someone else can run it from the README |
| 10 (Oct 17) | Buffer. Fresh-clone test on a clean folder, fix, submit with one day in hand. | Submitted |

Kill criteria: if Unity capture is not producing frames by the end of day 3, switch to the twin
renderer for day 4 and come back to Unity on day 8 only if everything else is done.

### 6a. Status and revised plan (updated 2026-10-11)

Done so far:

| Day | Done | Files |
|---|---|---|
| 1 (Oct 8) | Case analysed, Unity project downloaded, this plan | this file |
| 2 (Oct 9) | Research on repos, papers, MCPs and skills; Unity 6000.3.5f1 installed and licensed | RESEARCH-TOOLS-PAPERS-2026-10-09.md |
| 3 (Oct 10) | Project fixed and running, standalone build works. Solver repo: exact game rules, minimum-drag solver, replay checker, 3 Fable 5.1 reviews plus adversarial failure testing. Competitor ad research | cbj-creative/, SOLVER-REPORT-2026-10-10.md, SOLVER-CHECK-STEPS.md, COMPETITOR-ADS-2026-10-10.md |
| 4 (also Oct 10) | Unity CreativeRunner: `cbj render` records a move script in the real game as 1080x1920 video (win / cut / fail endings), all six levels cleared in-game, `cbj compare`, Fable 5.1 review fixed | cbj-creative/unity/, RUNNER-REPORT-2026-10-10.md, RUNNER-CHECK-STEPS.md |
| 4c (also Oct 10) | Decisions with Fable 5.1. (1) The game's fail-then-win bug is fixed in the game code by a 31-line patch (`unity/game-patch`) that `build-player` applies to its copy only; Rollic's project stays byte-identical, and `--stock` builds and records the unpatched game for a before/after. (2) Fail endings: S5 opt-in, S6 timeboxed, default endings S3/S4/S1. 195 fast tests + 22 that start Unity | RUNNER-REPORT "Decisions" |
| 4b (also Oct 10) | Case re-check with Fable 5.1: difficulty rating (`cbj difficulty`), camera zoom/pan/keys, pacing flags, timer override, HUD hiding, compositor event data, the game's fail-then-win bug fixed in the recorder, stale statements in these documents corrected. 190 fast tests + 20 that start Unity at that point | same files, updated |
| 5 (also Oct 10, planned for Oct 11) | Scenario scripts: `cbj scenario LEVEL --ending win\|near_fail\|cliffhanger\|time_out`. Believable mistakes (blocked, wrong way, one fidget; each costs 1-2 drags), hesitations, frame-exact pacing, clock and length fitted by moving pauses only from one dry run; every recording lands on the predicted frames. All four endings recorded on the narrow-centre level (the p.4 example as a near-fail with 00:01 left). A* solver (`solve_fast`, same minimum, 160x faster there). Two Fable 5.1 checks: all its rules applied; 9 + 10 findings fixed (incl. cliffhanger puzzles and mistake reactions on Levels 4-6, time-out 00:01 at the grab, `cbj rerun FOLDER` reproduces a recording), plus a --length bug found while writing the check guide. 309 fast tests + 28 that start Unity | SCENARIO-REPORT-2026-10-10.md, SCENARIO-CHECK-STEPS.md |
| 6 (Oct 11) | Compositor: `cbj ad RECORDING` makes a finished 30 s ad (hook on frame 0, captions from recorded facts only, tap ring from the finger log, synthesized sound effects, a slow-motion replay, the game's result screen, a "PLAY NOW" end card) as editable data (`ad.json`: named segments and layers anchored to gameplay events, a `locked` list that QA enforces, a copy guard against invented odds). `cbj compose` renders any `ad.json` byte-identically; `cbj ad-diff A B --decode` proves an edit stays in its layer's frames and box, in the delivered MP4 too (an IDR keyframe at every boundary, constant quantizer). All four endings rendered as 30 s ads, QA clean (the win's end card is long: 7.3 s). Fable 5.1: plan discussion, two checks, one confirmation; 12 + 12 + 2 findings fixed. 359 fast tests + 28 that start Unity | COMPOSITOR-REPORT-2026-10-11.md, COMPOSITOR-CHECK-STEPS.md, COMPOSITOR-PLAN-2026-10-11.md |
| 7 (also Oct 11, planned for Oct 13) | Text to creative + the test UI (asked for by the user): `cbj ui` (http://127.0.0.1:8765): a prompt (plus images) -> an LLM brief (NVIDIA Nemotron 3 Ultra, JSON schema) shown control by control for the case's 8 prompt controls (applied / default / adjusted / not supported, with reasons) -> the engine makes the ad. New engine pieces: a level generator (open, narrow centre, door, pillars; easy/medium/hard bands; sized to the ad), recolouring inside the real game, ad options (result first, no replay/result screen, copy, caption colours, logo/mascot/end-card art, hand cursor, no sound, hidden HUD). Edits change only what they ask about, with three proofs (recording reused + ad-diff; the stored job re-filmed + identical game state; new gameplay said plainly). Unity MCP not used at run time (Fable agreed). Fable 5.1: plan discussion, a check (20 defects fixed), a confirmation (keep fixed). 420 fast + 28 Unity tests | TEXT-TO-CREATIVE-REPORT-2026-10-11.md, TEXT-TO-CREATIVE-CHECK-STEPS.md, TEXT-TO-CREATIVE-PLAN-2026-10-11.md |
| 8 (Oct 11-12, asked for by the user) | Core requirement 2, level & gameplay generation: the case's seven asks each a brief field that code builds, plays and checks on the recording. Ordered steps (leaves/moves/stuck/hesitates, first/last/all, biggest/smallest/longest) with an exact A* solver; a satisfying finish (one key move, then every block in a row, never longer than the minimum); near-fail 00:01-00:03; pacing curves; shapes cross/ring/lanes, piece sets, symmetric/packed/colourful boards; gates only where their block can reach; local search; a fairer naive player. Checks per version from result.json; UI card with board picture, moves and checks; Level only button; `cbj generate`. Generator 24/24 in band (23/24 before), hard up to 3 repositioning. 20 prompts end to end: all made creatives played as planned; 2 honest adjustments, 1 refusal. Fable 5.1: plan review, a check (15 findings fixed), a confirmation (its 7 follow-ups fixed). 493 fast + 28 Unity tests. Multi-level ads cut (designed, not built) | LEVEL-GAMEPLAY-REPORT-2026-10-11.md, LEVEL-GAMEPLAY-CHECK-STEPS.md, LEVEL-GAMEPLAY-PLAN-2026-10-11.md |
| 9 (Oct 12, asked for by the user) | Core requirement 5, controlled editing: an edit changes the stored creative, not a new generation. The edit report checks the case's seven preserve items plus captions and sound, each difference asked / explained by a check on the measured difference / NOT ASKED (fails the edit). The pin keeps the original's intro, replay and length when the gameplay frames are kept. Asset inventory ("this asset", the coin pile...) for the planner and the UI's *Things in this ad* (Replace / Add / Remove / Edit, no planner); replacements drawn in the original's box and place; assets merged per slot. Gameplay edits keep the closest play (24 plans, solver cache); "harder"/"easier" edit the same board (at most 3 changes) and keep the HUD number. Edit any version, compare any two. Fable 5.1: plan discussion, check (11 defects fixed), confirmation ("done"; 4 edge cases fixed). Also fixed a requirement-2 bug found live: "Color Block Jam" in a prompt read as asking for a jam-packed board. 538 fast + 28 Unity tests | CONTROLLED-EDITING-REPORT-2026-10-12.md, CONTROLLED-EDITING-CHECK-STEPS.md, CONTROLLED-EDITING-PLAN-2026-10-12.md |

Days 3, 4 and the scenario step were all done on Oct 10, so Oct 11 is free. Fable's first priority
for it: the compositor and the first finished 30 s ad (the compositor is where "creative quality"
is scored, and nothing yet is a finished ad). The generator becomes a real command on Oct 12.

| Date | Goal | Done when |
|---|---|---|
| ~~Oct 11~~ Oct 10 | Scenario scripts: DONE (row 5 above) | The p.4 prompt's gameplay as an S4 video: done |
| ~~Oct 11~~ | DONE (row 6 above). Planned as: Compositor v1: hook card, captions from the beat notes, sound effects at exit and win frames, hand cursor from the finger log, end card, HUD clean-up, and a **segment list** so a 60 s ad can join two gameplay parts (e.g. an easy clean win, then the hard near-fail). S6 (fail, "try again", win) only if the join is done, at most 2 h | The first finished 30 s ad: the narrow-centre near-fail |
| Oct 12 | (Level generator command, Unity spot check and requirement 2: DONE, row 8.) The 60 s ad (generated easy win + the narrow-centre near-fail, joined; the join is built and tested): moved after Oct 14. Level generator as a command (`cbj generate --shape narrow_center\|open --difficulty hard`), wrapping Fable's search with its rules (no block that can leave at the start, at least 2 repositioning drags, at least 4 waist crossings, 200k state cap), writing the HUD label and the timer into the level; Unity spot check of a sample | A second concept (clean win) recorded from a generated level |
| ~~Oct 13~~ | DONE early (row 7 above: the brief is the CreativeDoc, declared field groups are the edit whitelist). Planned as: CreativeDoc schema, LLM planner (Nemotron, Claude optional), JSON Patch editing with an editable-path whitelist. Asset slots in the runner. The proof leads with what is exact (level, moves, camera, asset hashes, event log) and pixels last; overlay-only edits reuse the recorded gameplay | Text example and controlled-modification example done |
| Oct 14 | Image inputs (role classifier, background removal, asset slots, one Nano Banana Pro sample before any batch) and video references (frame sampling, Nemotron Omni structure extraction; competitor ads as test references) | Image example and video-reference example done |
| Oct 15 | UI (FastAPI + one page) and QA loop (deterministic checks, then VLM judge). Optional AI hook/outro, one sample + a yes first | The UI runs the whole loop |
| Oct 16 | Technical write-up (mirrors p.12), README, architecture diagram, 2-3 min walkthrough video | Someone else can run it from the README |
| Oct 17 | Fresh-clone test, fix, submit | Submitted |

Asset slots, decided now so the CreativeDoc can carry them. What the game can actually swap (from
Fable's read of the C#): the material per block colour (`BlockData.colorMaterial`), the gate
material, the exit particle material, the cell colours (`GameManager.gridColors`), the camera
background and the `Ground` object, and the HUD sprites. The game has no obstacles other than
holes and borders, so "use this object instead of the current obstacle" maps to block skins,
the background or the board. Mascots, captions and logos are overlays in the compositor (no
rebuild).

Risks: the generator's BFS cost on dense boards (see 4.1); two rule implementations (the Python
port and the game), guarded by the recorder's cell-by-cell check, so generated levels get a
Unity spot check.

Concept library after the competitor research (COMPETITOR-ADS-2026-10-10.md, section 6): the
gameplay templates become S1 cliffhanger, S2 "can't reach <colour>", S3 clean win, S4 near-fail win
(the gap nobody runs), S5 time-out fail and S6 fail-then-win (social A/B only, not CBJ's style),
S7 Brain Age overlay and S8 level montage. fail_bait is dropped. level_reveal, no_ads_promise,
mascot_react and reference_adapt stay as presentation layers on top of any scenario.

Ending policy (decided 2026-10-10 with Fable 5.1):
- **Default endings:** a win (S3), the near-fail win (S4) when the prompt says
  difficult or almost fails, and the cliffhanger (S1) on request.
- **S5 time-out:** opt-in only. The planner picks it on an explicit fail request,
  or for a social channel when fail endings are allowed. Never for ad-network
  channels. Only on medium-hard levels. A "fake fail" request becomes a real
  time-out, and the tool says so.
- **S6:** timeboxed on Oct 12.
- **Reasons:** CBJ's own ads avoid staged fails; most of its ads run on ad
  networks, where success endings did better; S4 is the unused gap; and the
  case's example asks for a near-fail.

Risk to watch (Fable, case re-check): "AI usage" is zero so far. The planner, image and video
inputs (Oct 13-14) are the AI half of the role and must not slip.

Open items: none from the user. (S5/S6 and the game bug were decided on 2026-10-10, see 4c.
The Level 3 hand replay is no longer needed: the recorder replays all six levels in the game and
checks every cell.)

---

## 7. Tool roles

| Tool | Use it for | Do not use it for |
|---|---|---|
| Claude Code (Fable 5.1) | Writing the solver, the Unity scripts, the API, tests, docs; reviewing the Unity code with you; the Unity MCP server (open beta, Unity 6, needs a Unity AI trial) if you want agent control of the editor | Being the in-product planner unless you also wire the Claude API; the tool must run without your IDE |
| NVIDIA build | In-product LLM planner and patcher (Nemotron Super/Lightning), VLM classifier and judge (Nemotron Nano Omni, Llama 3.2 Vision fallback), embeddings for a concept-template retriever if you add one. Free tier; your key already lists 80 models | Image or video generation (none on your key); treat 503s as normal and keep fallbacks |
| Higgsfield | Nano Banana Pro images (assets, backgrounds, mascots), background remover, optional Seedance/Kling hook and outro clips with start/end frames, Topaz upscale for the final | Gameplay video, object swap on gameplay (test once, reject in writing) |
| Kling MCP (also connected) | Alternative for start/end-frame clips if Higgsfield queues are slow | Same restrictions |
| ffmpeg / Remotion | Assembly, overlays, captions, SFX timing from the event log, PSNR diff maps | |

---

## 8. Technical explanation: outline that mirrors their list (p.12)

1. Architecture: one diagram (section 3), one paragraph on "deterministic core, generative shell".
2. Components: planner, generator + solver, CreativeRunner, asset layer, reference analyst,
   compositor, QA judge, UI.
3. Why this approach: cite the PDF's own page 8 concern, show one Genjutsu/Seedance gameplay
   attempt and its drift, then the Unity result for the same spec.
4. Deterministic vs generative: a two-column table per component.
5. Consistency between generations: everything derives from the CreativeDoc; same doc, same bytes;
   seeds for the generator; versioned templates; asset hashes.
6. Controlled editing: JSON Patch, path whitelist, layer caching, diff report with numbers from
   your example (for instance, "1,180 of 1,200 frames identical; changed region 3.2% of pixels").
7. Limitations: no obstacles beyond holes (the simplified project has none), solver limits on large
   boards, VLM judgement variance, Unity render time, AI clips only at the edges, no audio
   generation, English prompts only.
8. Production roadmap: render farm (Linux builds with Xvfb or cloud GPUs), per-network variants
   (sizes, durations, end cards), playable export via Unity Playworks, creative-performance
   feedback loop (tag winning templates, re-weight the planner), designer review queue, asset
   library with rights metadata, multi-game template packs.

---

## 9. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Unity install or capture eats days | Day 1 is only environment; the twin renderer fallback; standalone build so renders do not need the editor |
| Solver mismatch with real game physics (free drag) | Solver works in cell space; playback uses the game's own services, so if the solver is right in cell space the game confirms it; test on six shipped levels |
| LLM returns invalid specs | Schema validation, retries, templates with defaults, never render an unvalidated doc |
| Paid generations wasted | One sample, then batch; cap 150 credits; everything deterministic is free |
| NVIDIA 503s during the demo | Fallback chain plus a cached "last good plan"; the deterministic path needs no model at all |
| Scope creep | Section 5 list; anything new goes in "next steps" |

---

## 10. Research notes and sources

* Rollic CBJ creative strategy (Segwise teardown): unresolved levels as the ending, "no ads" hook
  in VO and text, tactile SFX over music, low-poly characters, light camera shakes and zooms;
  fail offers are about a fifth of revenue but ads do not show failing or monetisation.
  https://segwise.ai/blog/color-block-jam-creative-strategy-breakdown
* Industry context: 56% of top-100 grossing games used AI for ad creatives in 2025; UA teams ship
  10+ variants a week; Unity Playworks (ex Luna) exports Unity projects as playables.
  https://segwise.ai/blog/produce-playable-ads-at-scale ,
  https://segwise.ai/blog/ai-mobile-game-marketing-playbook-2026
* Higgsfield API docs: Genjutsu object swap (video 4-30 s, 1-8 reference images, 480p-1080p),
  restyle pricing per second ($0.318 480p, $0.681 720p, $1.632 1080p), billing per successful
  request, outputs kept at least 7 days. https://docs.higgsfield.ai/docs/models/genjutsu ,
  https://docs.higgsfield.ai/docs/concepts/billing-and-retention.md
* Unity Recorder does not work in -batchmode (graphics pipeline not initialised); use a windowed
  process or your own capture. https://docs.unity3d.com/Packages/com.unity.recorder@5.1/manual/KnownIssues.html
* Time.captureFramerate for frame-exact capture. https://docs.unity3d.com/Manual/time-capture-frame-rate.html
* Unity CLI (experimental, macOS 14+): `brew install --cask unity-cli`, `unity install <version>`,
  `unity open ./Project`. https://docs.unity.com/en-us/unity-cli/use-unity-cli
* Unity AI MCP server, open beta for Unity 6, works with Claude Code, needs AI Assistant package
  and a Unity AI trial. https://unity.com/blog/unity-ai-mcp-how-to-get-started
* NVIDIA Cosmos Reason 2 model card lists video input; not available on your key today (404).
  Nemotron Nano Omni accepts base64 mp4 on the hosted endpoint (tested); model card lists mp4 up
  to 2 minutes.
  https://build.nvidia.com/nvidia/cosmos-reason2-8b , https://build.nvidia.com/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning
* Rollic company and interview notes you already have: ~/Downloads/rollic_interview_prep_2026-10-06.md
