# Text to creative: what was done, why, and how to check it (2026-10-11)

## In one paragraph

The case's first core requirement is natural-language input: a prompt goes in, a final Color
Block Jam creative comes out. A prompt may give instructions about eight things: the level,
the gameplay, difficulty or pacing, visuals, the concept, the sequence of events, the assets,
and what must stay unchanged. Until this step the tool could do much of this, but only through
command-line flags, and three of the eight had no engine behind them. Now:
- **`cbj ui` opens a test page.** You write a prompt (and attach images). An LLM turns it into a
  **brief**, and the page shows how each of the eight controls was read. The engine makes the ad
  from the brief.
- **Edits are proven.** A follow-up prompt edits the ad into a new version, changes only what it
  asks about, and shows the proof.
- **New engine pieces** fill the gaps:
  - a level generator;
  - recolouring inside the real game;
  - more options in the ad builder.

Fable 5.1 discussed the plan, then checked the result twice. Everything it found is fixed except two
partial items, listed under the limits.

---

## 1. Why this step

- **p.3:** "The tool should accept natural-language prompts describing the desired creative.
  The system should translate these requests into a final Color Block Jam creative." Prompts
  may give instructions about the eight controls.
- **p.4:** "describe what they want in natural language and receive a usable creative". The
  examples are "illustrative rather than exhaustive": the tool must handle what a UA team would
  really ask for.
- **p.7:** "keep everything exactly the same, but replace this asset". The eighth control and the
  case's most important part.
- **You asked for a UI** to test these with your own prompts, and pointed out that the workflow
  did not cover them yet. That was right: the engine only listened to CLI flags.

## 2. What was built, and why

### 2.1 The split: the LLM writes a brief, the engine makes the ad

The LLM never makes levels, moves or pixels. It fills a typed **brief** (a JSON schema), and the
deterministic engine makes everything from it. **Why:**
- the gameplay stays real and solvable (the solver checks it, the real game plays it);
- the same brief always gives the same ad, so an edit can be proven;
- the brief is something you can read: the page shows it, control by control.

### 2.2 "What I understood"

Each of the eight controls gets a row with:
- the prompt's own words for it;
- what the tool will do;
- a status:
  - **applied**: asked, and done;
  - **default**: not mentioned;
  - **adjusted**: asked, but changed to something the game can do, with the reason;
  - **not supported**: impossible here, with the reason.

Notes from making the ad ("this gameplay fills 33 s, so the ad is 37 s") are added under the
row. Nothing a prompt asks for is dropped silently. Unsupported requests, such as "turn the
blocks into 3D cats", are named, never ignored.

### 2.3 The planner, and checks in code

- **The model:** NVIDIA Nemotron 3 Ultra, in JSON-schema mode with its reasoning turned off. With
  reasoning, a brief took 30-180 s; without it, 15-40 s, and the JSON stayed valid. Nemotron 3
  Super is the fallback; it is faster (5-15 s) but misread endings and colours in a 14-prompt
  comparison.
- **What the model kept getting wrong:** in that comparison it wrote copy nobody asked for,
  invented facts ("Solved in 3 moves"), used uploaded images the prompt never mentioned, and
  guessed a HUD level number.
- **So the rules are enforced in code, not left to the prompt:**
  - a control the prompt does not mention keeps its default (a new ad) or its previous value
    (an edit);
  - an upload is used only if the prompt refers to it;
  - a level number only if the prompt gives one;
  - every text goes through the copy guard and may only use measured facts;
  - repainted colours must stay easy to tell apart;
  - a time-out is a social-channel ending on a medium or hard level;
  - only 9:16 is rendered, and the tool says so.
- **Non-English ads:** the default captions are translated too, so an ad never mixes
  languages.

### 2.4 The eight controls, and what each one drives

| Control | Engine piece | New in this step |
|---|---|---|
| Level type or structure | the level generator: open, narrow centre (hourglass), door (two rooms), holes (pillars); size, blocks, colours | the generator |
| Gameplay behaviour | the scenario planner: ending, mistakes (and their kind), hesitations; recorded in the real game | mistake kinds |
| Difficulty or pacing | easy / medium / hard bands; the ad's length; the tempo of the pauses | the bands, tempo, length sizing |
| Visual elements | themes or per-colour paint, background, board, caption colours, zoom, cursor (ring or hand), HUD | recolouring inside the game |
| Creative concept | the angle, the hook, every caption, the end-card texts, the language | copy from the prompt, translation |
| Sequence of events | standard or result-first, replay, result screen | the teaser, no-replay, no result screen |
| Assets | uploaded images or game sprites by role: logo, mascot, sticker, cursor, end-card art or background; sound on or off | uploads, roles, the band beside a logo |
| Keep unchanged | edits change only what they ask about, with proof | the edit flow and its three proofs |

### 2.5 The level generator

It places polyomino blocks at random on a board of the requested shape, each with a gate of its
colour. It then keeps only the boards that:
- the game's rules accept;
- the exact solver can solve;
- the difficulty measure puts in the requested band.

The bands, from measures the tool already had:

| Band | Repositioning drags | Blocks that can leave at once | Naive player |
|---|---|---|---|
| easy | none | most of them | close to the minimum |
| hard | two or more | none | 1.2-4x the minimum, and always finishes |

Medium lies between the two.

**How it gets hard levels:** harder levels put each gate across the board, so the blocks must
cross each other's paths. Random gates make almost every board easy.

**Size and repeatability:**
- When the prompt gives no block count, the level is sized to the ad's length, minus the time
  that mistakes and hesitations take.
- The same spec and seed give the same level, and every level is cached.

**Speed:**
- The difficulty rating now uses the A* solver: 0.4 s a board instead of up to 5 s.
- A state cap stops slow boards.
- Easy and medium levels take 3-5 s; hard ones 10-40 s.
- A hard narrow centre that the search cannot find in 40 s falls back to the hand-checked one,
  and the brief says so.

### 2.6 Colours inside the real game

The recorder repaints the game's own materials before the board is built:
- per colour slot: the block, its gate and its exit particles;
- the cells' colour;
- the ground's gradient, replaced by the brief's colours.

**The puzzle is unchanged; only the look changes.** A colour has two sides:
- its **slot**, which the gates and the solver use;
- its **display** colour and name, which the viewer sees.

Captions use the display name ("I can't reach mint!"), and the end card follows the background.
Rollic's project is untouched: the recolouring code lives in our recorder, built into the copy.

### 2.7 Edits: only what was asked, and proof

A follow-up prompt is planned against the current brief. The fields of every control it does
not mention are restored. Then the engine takes the smallest re-run:

| The edit touches | Re-run | Proof |
|---|---|---|
| copy, captions, sequence, assets, caption colours | none: the same recording; the ad is composed again | `ad-diff`: which frames and layers changed, and that every changed pixel is inside the changed layers' boxes |
| colours, HUD, zoom, level number in the game | the stored job (the same moves and timing) filmed again with the new look | the game state (blocks, clock, finger) identical on every frame |
| gameplay or level | recorded again | said plainly: new gameplay, on the same or a new level |

Recordings and levels are stored under a hash of everything that decides them. Asking for the
same thing twice never records it again.

### 2.8 Unity MCP: not used at run time

The UI already runs the real game: our built player records it headless and frame-exact, with
no editor open. Unity MCP drives an open editor, which here is Rollic's project and must stay
untouched. It is also slower, not repeatable, and would not run on a reviewer's machine. What
the visual controls needed was runtime recolouring in our recorder, and that is now built.
Fable agreed. Unity MCP stays useful as a development tool, for example to author new block
meshes, which is out of scope.

## 3. Results

### 3.1 The case's own prompt (p.4)

> Create a difficult Color Block Jam level with a narrow center section and show gameplay where
> the player almost fails before solving it.

| What happened | Detail | Time |
|---|---|---|
| The planner read it | Level: "a difficult level with a narrow center section", applied. Gameplay: "almost fails before solving it", applied. The other six controls: default | 41 s |
| The generator built a level | Hard narrow-centre, 6x8, 8 blocks: 10 drags minimum, 2 repositioning; a naive player needs 3.2x the minimum | 32 s |
| The real game recorded the play | A mistake, a stuck stare, hesitations; the last block leaves with 1.67 s on the clock (00:01) | 40 s |
| The ad was composed | 30.0 s: hook, captions, cursor, sound, result screen, end card | 31 s |

### 3.2 Edits on that ad

| Edit | Re-run | Proof | Time |
|---|---|---|---|
| "Keep everything exactly the same, but make the hook say 'Beat this in 20 seconds'." | none recorded; composed again | the same recording reused; 57 of 900 frames changed (0-56); every changed pixel inside the hook's box | 33 s + 24 s proof |
| "Same ad, but make the blocks pastel." | the stored job filmed again | game state identical on every frame | 67 s |
| "Same ad, but in Turkish." | none recorded; composed again | the same recording reused; only the caption and end-card layers changed | 32 s + 58 s proof |
| "Keep everything, but switch to the dark theme." (an ad with a logo) | the stored job filmed again | the logo kept, the level kept, game state identical on every frame | 52 s |

### 3.3 The other controls

Seventeen creatives (24 versions) were made through the UI today, by me and by Fable's check.
Each of the eight controls changed the real creative at least once:
- three generated shapes besides the narrow centre (door, pillars, open), each played in the
  real game;
- the four endings;
- 15 s and 30 s lengths, and calm and fast tempos;
- repainted blocks and backgrounds (candy, pastel, neon, dark, and a custom pink, teal and gold
  on black);
- caption colours, a hand cursor, a hidden clock;
- copy edits, removals and translation;
- result first, no replay, no result screen;
- logos and sprites, no sound.

The guide lists the prompts and what came out.

### 3.4 Tests

- **New tests:** 55 for the brief, the planner (with a fake model), the generator and the ad
  options; 6 for the web API.
- **Full fast suite:** 420 passed.
- **With the Unity tests:** 419 passed, including all 28 that run the real game (run after the
  recorder's C# change).

## 4. Fable 5.1: the plan discussion and the check

### 4.1 Plan discussion

Fable agreed with the split (the LLM writes a brief, the engine makes the ad) and with keeping
Unity MCP out of run time. It changed:
- **colour slots vs display colours,** with names, so captions follow a repaint;
- **three kinds of edit proof,** and re-filming the stored job, not re-planning, for a new look;
- **the generator:** the rating on the fast solver (it was 20-50x slower), gates across the
  board for hard levels, a state cap, four shapes, difficulty bands, sizing to the ad;
- **schema additions:** channel, language, format, sound, HUD, clock, mistake kinds, named
  sequences, assumptions.

It also measured exactly where each colour lives in the game (materials, grid, ground), which
the recorder now uses.

### 4.2 The check (17 creatives made through the live UI)

Fable confirmed that specific prompts really change the creative and that the proofs are
honest. It found 20 defects; the main ones, all fixed:

| Found | Fixed |
|---|---|
| The planner invented board sizes and block counts; one vague prompt failed outright (no hard 9x10 board with 6 blocks) | The planner now declares the field groups a prompt changes; sizes, counts, colours, copy, level numbers and uploads also need the prompt's own words. The generator degrades instead of failing, and says so |
| Every edit dropped uploaded images | All uploads stay valid; an edit keeps the images its version uses |
| "No result screen" crashed near-fail and time-out ads | The result caption only with a result screen |
| Zoom cropped the side gates out of frame | Zoom capped at 1.12x, with the reason |
| "No sound" was silently undone when the model filed it under another control | Declared changes replace the per-row rule |
| "Hide the timer" left an empty bar, and the end card still quoted the clock | The whole clock group hidden; the copy stops quoting the clock |
| A re-filmed edit showed "Level 1" | The HUD number always goes to the recorder |
| A near-fail recording failed on float noise (1.2999 s against a 1.3 s limit) | The clock fit stays 0.05 s inside its range; the check allows half a frame |
| A failed recording could be reused | Only recordings that passed their checks are reused |
| The teaser's hook covered the game's banner | The teaser is letterboxed, with the hook above it |
| Smaller ones: engine notes on the wrong row, a loose upload check, stale translation notes, proof time not counted, UI gaps (errors, a busy guard, re-attaching uploads) | All fixed |

### 4.3 Confirmation

Fable confirmed 17 of the 20 fixes live, two of them partly (zoom, statuses). It found one new
problem: the "keep" list was dropped by the new merge, so "keep the level, but make it
harder" replaced the level without saying so. Fixed:
- keep is now always the prompt's own list;
- a contradicting change is reported ("asked to keep the level, but the prompt also changes it;
  the change wins");
- the proof names the level whenever the level changed.

Re-run live on such an edit. Also fixed:
- the evidence checks match whole words: "cleared" is not a colour, "20-second" is not a board
  size;
- earlier colour translations are kept across edits;
- the planner is told the real zoom range.

## 5. Honest limits

- **Planning takes 15-45 s.** Nemotron 3 Ultra is the better reader, and its reasoning is off
  already. The 5 s model (Super) misread endings and colours.
- **"Hard" is best-effort.** Hard boards are rare, mostly on sparse or very small boards. When
  the search cannot hit the band in its time budget, it uses the closest board and says so
  ("medium-to-hard"). A hard narrow centre falls back to the hand-checked level.
- **Short gameplay makes long end cards.** Easy levels play fast, so a 30 s easy win can end on
  a 6-7 s end card. QA warns, and the brief says what the gameplay filled. The 60 s ad with a
  warm-up level is still to come.
- **Only colours change in the game, not shapes.** "Make the blocks into 3D cats" is reported as
  not supported.
- **Zoom stops at 1.12x.** Closer cuts the side gates out of frame on a typical board; the tool
  does not yet frame per board.
- **Hidden clock.** The empty purple bar stays when only the clock is hidden; hiding the level
  number as well hides the whole bar.
- **Translated grammar.** Captions are translated, but suffixes after a colour name can be off
  ("sage'a" in Turkish).
- **One job at a time.** The game player is a single process.
- **The planner's own words are not always perfect.** The status and "fields set by the
  prompt" come from code and are reliable; the planner's plan sentences are its own.
- **Partly fixed after Fable's checks:**
  - a zoom request is always shown as *adjusted* (capped);
  - the planner's own status words can still be imprecise. The "fields set by the prompt" line
    is the reliable one.
- **Mistakes on a small board.** The generator does not yet size a board for the number of
  mistakes asked for; a small board may offer fewer believable mistakes, and the brief says so.
- **No image references or video references yet.** Those are the next core requirements
  (Oct 14).

## 6. How to test it

The guide is `~/rollic-case/TEXT-TO-CREATIVE-CHECK-STEPS.md`. In short:
```
cd ~/rollic-case/cbj-creative
uv run cbj ui        # then open http://127.0.0.1:8765
```
