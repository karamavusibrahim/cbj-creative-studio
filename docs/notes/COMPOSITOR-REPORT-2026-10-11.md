# Compositor step: what was done, why, and how to check it (2026-10-11)

## In one paragraph

Until this step the tool made **gameplay clips**: real Color Block Jam play with a planned
mistake and ending, recorded frame-exact. A clip is not an ad. This step adds the
**compositor**, which turns a recording into a finished 30 s ad:
- a hook on the first frame;
- captions on the story's moments;
- a tap ring that follows the recorded finger;
- a slow-motion replay;
- the game's own result screen;
- an end card with the game's green "PLAY NOW" button;
- sound effects on every tap, exit and clock tick.

The ad is not a flat video. It is a file, `ad.json`, that lists named segments and named
layers. Editing one layer and rendering again changes only that layer's frames, inside that
layer's box. `cbj ad-diff` proves this for every edit, both on the composited frames and on the
delivered MP4. The four endings are rendered as 30 s ads. Fable 5.1 discussed the plan,
checked the code twice, then confirmed the fixes; everything it found is fixed.

---

## 1. Why this step

- **The case asks for finished ads.** p.2: "30-60 second Color Block Jam creatives", "a final
  creative". p.4: "receive a usable creative". p.11 scores "creative quality: visually coherent,
  engaging, usable" on finished ads, and until today there were none.
- **The split the case describes.** p.5 asks for "deterministic gameplay rendering combined with
  generative visual elements". The game makes the gameplay; the compositor builds everything
  around it.
- **Controlled editing**, which the case calls one of the most important parts (p.7): "keep
  everything exactly the same, but replace this asset", while gameplay, timing, camera,
  composition and the other assets stay. A flat video cannot do that. A layered ad, where every
  element is a named slot, can, and it never records the gameplay again.
- **The deliverables** (p.12): "several example creatives", then one "controlled modification".
  Both need this step.

## 2. What was built, and why each piece

### 2.1 The ad as data: `ad.json`

`cbj ad RECORDING` writes an `ad.json` for the recording's ending and renders it.
`cbj compose AD.json -o OUT` renders any `ad.json`, including one you edited by hand (and, from
Oct 13, one the language planner writes).

An `ad.json` holds:
- **segments**, in an `order` list. Each is one of:
  - a **clip**: a frame range of a recording, at any speed, with a camera fit;
  - a **hold**: one frozen frame;
  - a **card**: a background image.
- **layers** on top: text, tag, image, button, cursor, and an edge pulse (vignette). Each layer
  starts and ends **at a gameplay event**, with an optional offset, or at a time. Events include:
  - `beat.N.start`, `drag.N.exit`;
  - `clock<=5`, `clock_second`;
  - `win`, `fail`, `cut`.

  **Why events:** a caption stays on its moment even if the gameplay is planned again.
- **audio** events, anchored the same way.
- **locked**: what an edit may not change (2.10).
- **notes**: anything the builder had to leave out, and why.

Segments and layers are keyed by **name**, not by position. An edit says "change `end_fact`",
and nothing else moves.

### 2.2 Layout: the whole game frame, letterboxed

During gameplay the recorded 1080x1920 frame is scaled to 75% and placed at x 135, y 318. It
sits on a canvas filled with the recording's own background gradient, so the join is invisible.
This is letterboxing: the game camera is never re-framed.

**Why.** At full size the board reaches almost to the bottom of the frame. Captions there
covered blocks, and the bottom of a feed is under the platform's buttons. The 75% fit leaves:
- **one text band above the HUD** (y 250-476), holding one caption at a time;
- **the "social" safe area** clear: 250 px at the top, 420 px at the bottom, 60 px on the left
  and 130 px on the right.

The replay and the result screen play at **full size**, which reads as a zoom-in.

### 2.3 The story on screen

What `cbj ad` builds for each ending:

| Moment | Near-fail | Time-out | Cliffhanger | Win |
|---|---|---|---|---|
| Hook, frame 0 (the poster) | "Can you beat the clock?" + stopwatch | same | "Can you clear it?" | same |
| The mistake | "I can't reach dark green!" | same | "I can't reach green!" | — |
| The fix | "Aha! Move red first" | same | — | — |
| The last 5 clock seconds | "Hurry!" + red edge pulse on each second | same | — | — |
| The closing cascade | — | — | — | "So satisfying!" |
| Slow-motion replay (0.5x) | the last 1-2 beats, at most 5 s, with a REPLAY badge | same | same | same |
| Result | the game's win screen + "Phew! 00:01 left" | the game's "Out of Time!" + "So close!" | a 2 s hold + "Can you see the move?" | the game's win screen |
| End card | "Cleared with 00:01 left", stopwatch | "Out of time with one block left!" | "Your move: two blocks to go!" + the unsolved board | "Cleared in 12 seconds", coins |

Details, and why:
- **The colour in "I can't reach dark green!" comes from the block** the mistake dragged, never
  typed by hand. "I can't reach <colour>" is the line CBJ's own winning ads use.
- **The REPLAY badge** is round and sits exactly over the HUD's Level circle. On a full-size
  frame, that is the one spot that never hides the play.
- **"Phew! 00:01 left"** sits under the game's "+50" button, clear of its "Level Completed"
  banner. Result captions wait 0.3 s for the game's dimming to settle.
- **The end card** uses the game's own background (`StartBACKGROUND.png`), its art (stopwatch or
  coin pile) and its green button with "PLAY NOW", pulsing. It is held to the last frame,
  because a feed shows the last frame when the ad ends or loops.
- **The cursor** is a tap ring drawn from the recorded finger position. A press shrinks it, a
  real lift sends out a ripple, and between drags it glides to the next block, arriving two
  frames early. It has an image slot for a hand picture, which the image-input step (Oct 14) can
  fill.
- **Captions** are fitted to the band (one or two lines, balanced) in the game's font, white with
  the game's purple outline. A fact like "dark green" never splits across two lines.

### 2.4 Facts only, and a copy guard

Texts may only use facts measured in the recording:
- `{clock_left}`, `{time_used}`, `{timer}`;
- `{colour}`;
- `{blocks}`, `{blocks_left}`, `{blocks_left_phrase}`.

An unknown fact fails QA. The **copy guard** refuses claims about players that the tool cannot
back up. It catches:
- percentages: "only 1% can", "99 percent fail";
- "only N" about players: "only 3 players can solve it";
- IQ claims;
- odds: "1 in 100", "1/100", "one in a hundred".

The UK ASA has ruled against "only 5% can solve this" style claims. Measured facts pass: "Only
00:01 to spare!", "Only one block left", "Level 3 in 12 seconds".

### 2.5 Sound

The project ships no audio, so the effects are **synthesized in code**. They are deterministic
and raise no licensing questions:
- a click on each touch;
- a pop on each block exit, rising in pitch over the closing cascade;
- tick and tock on each of the last 10 clock seconds, but not during the slow-motion replay,
  where the clock is not running in real time;
- a bump when a blocked block is pushed;
- a chord on the win, a soft "womp" on the fail screen;
- a whoosh on the replay and the end card.

There is **no music**: CBJ's own ads use tactile effects, not music. The mix is limited below
-1 dBFS; the four ads measure -19 to -17 LUFS, with peaks around -3 dBFS.

### 2.6 Exact length

The ad is exactly its length, to the frame. The parts are sized like this:
- the **replay** is at most 2 beats and 5 s;
- the **end card** takes what is left: at least 3 s, ideally up to 5 s;
- when the recording is short, a **frozen first frame** of up to 2 s gives the hook room;
- an end card **over 8 s is refused**: the recording is too short for that length. Use a longer
  scenario, a shorter ad, or `--allow-long-card`.

Captions get a reading time of 0.4 s plus 0.3 s per word (at least 0.8 s). If two would overlap,
the less important one moves later, keeping its gameplay anchor. A caption that can no longer be
read in the time left is dropped, with a note in `ad.json`.

### 2.7 The renderer, and colour

A Python frame loop: ffmpeg decodes the gameplay, Pillow and NumPy draw the layers, and ffmpeg
encodes H.264 + AAC. Alpha blending uses integer maths, so every frame is exact and repeatable.
- **Why not ffmpeg filters alone:** this ffmpeg has no text filter, and per-frame cursor motion
  and animated captions are clumsy in filter graphs.
- **Why not Remotion:** it adds Node and Chromium, is slower, and makes exact per-frame hashing
  harder.

**Colour.** ffmpeg's default conversion darkened every decode and re-encode by about 2 levels.
Frames are now converted with BT.709, TV range and swscale's accurate rounding, and the drift is
about 0 (48.3 dB against the source).

A 30 s ad renders in about 30 s on this Mac. `--draft` is faster, but a draft can never be
compared with a final render.

### 2.8 The proof: `compose.json`

Every render writes `compose.json` next to the MP4. It holds:
- the tool versions (ffmpeg, Pillow, NumPy);
- the SHA-256 of each gameplay source;
- the timeline, with each segment's frames and camera fit;
- every layer's resolved frames and pixel box (the predicted change set);
- the keyframe list;
- a SHA-256 of every composited frame;
- the WAV and MP4 hashes;
- the QA results.

The encode is bit-exact, so the same `ad.json` gives a **byte-identical MP4**. Today's re-run of
the near-fail ad, hours after the first one, gave the same SHA-256 (`6b697344...`).

### 2.9 Edits stay local, in the delivered MP4 too

Composited frames are easy to keep local: an edit only redraws its own layer. The **MP4** is
harder. With default x264 settings, rate control and inter-frame prediction spread any change
into neighbouring frames. So the encoder now runs like this:
- **an IDR keyframe at every segment and layer boundary**, placed by frame number. When they
  were given as times, ffmpeg put some keyframes one frame late;
- **a constant quantizer**, with no look-ahead, no macroblock tree and no B-frames.

With the same keyframes, only the GOPs (groups of frames between two keyframes) that hold a
changed frame can decode differently. Two kinds of edit, two honest claims:
- **A text, style or image edit** keeps the keyframes. The decoded MP4 then differs exactly in
  the edited layer's frames.
- **A timing edit** (moving, adding or removing a layer) moves keyframes, so the video can differ
  from the first moved keyframe on. `ad-diff` names it a timing edit and says so.

**The price is file size:** the near-fail ad is 10.7 MB, about 6 MB with default settings. The
four ads are 5-11 MB, well inside platform limits.

`cbj ad-diff ORIGINAL EDITED [--decode]` is the proof for one edit. It:
- compares the frame hashes;
- composites both versions of every changed frame again, and measures the changed pixels
  against the boxes of the changed layers;
- reports whether the sources, timeline, camera fit, sound and locked parts stayed the same;
- with `--decode`, decodes both MP4s and checks that every differing frame lies where it may.

It exits 1 if a change escaped its layers or a locked part changed. It refuses a render that
failed QA, and refuses to compare a draft with a final render.

### 2.10 Locked parts

`locked` names what an edit may not change. By default that is:
- the gameplay **sources**;
- the **segments** (timing and camera fit);
- the **cursor**.

Their digests are written when the ad is made. An edit that changes a locked part fails QA
before anything is drawn. To change one on purpose, remove it from `locked` first; `ad-diff` then
reports it as unlocked. **Why:** the case's "keep everything exactly the same" (p.7) has to be
something the tool enforces, not a promise.

### 2.11 QA on every render

Problems found before drawing stop the render at once: nothing is encoded, and the command exits
1. A render that fails a later check is saved as `ad.FAILED.mp4`, never as `ad.mp4`. The checks:
- the exact length;
- the hook on frame 0;
- every text inside the safe area and on screen for its reading time;
- every layer inside its segment;
- no two captions at once;
- the call to action held to the last frame;
- an end card of at least 3 s (a warning above 6 s);
- every anchor resolvable, and every fact known;
- locked parts unchanged;
- the copy guard;
- the audio peak and length.

---

## 3. Results

### 3.1 Four finished 30 s ads

From the four recordings of the narrow-centre level (the scenario step):

| Ad | Timeline | QA | Size | Loudness |
|---|---|---|---|---|
| Near-fail | gameplay 0-18.9 s, replay 18.9-23.9 s, win screen 23.9-26.4 s, end card 3.6 s | clean | 10.7 MB | -18.8 LUFS |
| Time-out | hold 0-2 s, gameplay 2-19.0 s, replay 19.0-22.0 s, "Out of Time!" 22.0-24.7 s, end card 5.3 s | clean | 6.7 MB | -19.0 LUFS |
| Cliffhanger | hold 0-2 s, gameplay 2-18.5 s, replay 18.5-22.7 s, question 22.7-24.7 s, end card 5.3 s | clean | 5.0 MB | -17.9 LUFS |
| Win | hold 0-2 s, gameplay 2-15.5 s, replay 15.5-20.2 s, win screen 20.2-22.7 s, end card 7.3 s | one warning: the end card is long | 10.7 MB | -16.9 LUFS |

Videos: `cbj-creative/ads/nc01_{near_fail,time_out,cliffhanger,win}_30s/ad.mp4`.
Picture strips (one frame per moment): `cbj-creative/reports/compositor/`.

### 3.2 Edits on the real near-fail ad

Each edit was composed and compared with `ad-diff --decode`:

| Edit | Composited frames changed | Changed pixels inside the layer's box | Decoded MP4 differs in | Exit |
|---|---|---|---|---|
| End-card fact text | 792-899 (108) | yes | 792-899 | 0 |
| Hook text | 0-61 (62) | yes | 0-61 | 0 |
| End-card image (stopwatch → coins) | 792-899 (108) | yes | 792-899 | 0 |
| Hook ends at 1.95 s (timing) | 55-61 (7) | yes | 55-64; "keyframes moved" stated | 0 |
| "Hurry!" removed (timing) | 451-531 (81) | yes | 451-567; "keyframes moved" stated | 0 |
| Tap sound louder (sound only) | none | — | none: "the video is identical; only the sound changed" | 0 |
| Camera fit moved, still locked | refused before rendering | — | — | 1 |

`reports/compositor/edit_demo_end_fact.jpg` shows the last frame before and after the first edit.

### 3.3 Tests

- **50 compositor tests** (`tests/test_ad.py`, counting each copy-guard case) on a synthetic recording, so they run without
  Unity. Among them:
  - determinism: the same frames, WAV and MP4 bytes;
  - edit locality, on composited frames and on the decoded MP4;
  - keyframe positions checked with ffprobe;
  - `ad-diff` and its exit codes, including a locked change hidden behind a timeline change;
  - locked parts, the copy guard, reading time, the scheduler, the two-recording join, sound
    events, the cursor and colour round trips.
- **Full suite:** 359 passed, 28 skipped (the 28 start Unity).

---

## 4. Fable 5.1: the plan discussion and three checks

### 4.1 Plan discussion

Fable read the plan and the case, and five decisions came out of it:
- **Layout:** letterbox the whole frame at 75% and put all text in one top band. My plan had
  captions below the board, but the board reaches too far down. I sent Fable that correction
  with measured positions, and we settled on the band.
- **Facts only:** every number and colour in a text comes from the recording.
- **Locked parts and anchors:** a `locked` list, and event anchors on every time.
- **Bit-exact proof:** `compose.json` with a hash per frame.
- **Endings:** all four rendered today; the 60 s ad waits for a generated easy level (Oct 12),
  because joining today's clips would jump in level badge and clock.

The full list is in `COMPOSITOR-PLAN-2026-10-11.md`, under "Decisions after the Fable 5.1
discussion".

### 4.2 First check (code, the four ads, the case)

| Found | Fixed |
|---|---|
| The MP4 was not local: one edit changed bytes across the whole file | IDR keyframes at every boundary, a constant quantizer, no look-ahead or B-frames |
| No way to prove an edit | `cbj ad-diff` |
| `locked` was only a list, never enforced | Digests written when the ad is made; QA refuses a locked change |
| The end card faded out, so the last frame had no call to action | Held to the last frame; QA checks it |
| End-card facts were written by hand | `{blocks_left}`, `{blocks_left_phrase}` and other facts |
| The result caption covered the HUD; the REPLAY tag covered the play | Moved (finished in the second check) |
| The replay padded the ad with filler | At most 2 beats and 5 s; a frozen intro for the hook; a long end card is refused |
| A mistake early in the play lost its caption | A scheduler that keeps anchors and length, and drops only what cannot be read |
| "dark green" could split across two lines | Facts never split; balanced two-line wrap |
| QA gaps (windows, fit, failed renders) | Each one checked; failed renders saved as `ad.FAILED.mp4` |
| Exit pitch broke with many exits; clock ticks played in slow motion | Fixed for any number of exits; no ticks in the replay |
| A draft could be compared with a final render | Refused |

### 4.3 Second check (the fixes, attacked on the real ad)

| Found | Fixed |
|---|---|
| Keyframes given as times landed one frame late | Placed by frame number; checked with ffprobe in a test |
| `ad-diff` claimed more locality than the MP4 has | GOP-aware wording, timing edits named, and `--decode` to measure the MP4 itself |
| `ad-diff` exited 0 on a locked change hidden behind a timeline change | The result is computed before that early return; exit 1 (tested) |
| `ad-diff` accepted a render that had failed QA | Refused (tested) |
| A layer could end past its segment | A QA failure |
| A moved caption with a fixed end got the wrong end | Only captions with a duration move their end |
| The copy guard flagged "Level 3 in 12 seconds" and missed "1/100" and "one in a hundred" | Rewritten around who the claim is about and its units (tested both ways) |
| "Phew!" touched the game's "Level Completed" banner | Moved under the "+50" button |
| The REPLAY pill was smaller than the Level badge it covered | A round badge sized from the badge's measured box |
| "Only the sound changed" was unclear about the video | "The video is identical; only the sound changed" |
| Source paths in `ad.json` were relative | Absolute |
| The reading time was defined in two places | One place |

I also caught one problem myself: the narrower copy guard first refused "Only 00:01 to
spare!", which is a measured fact.

### 4.4 Confirmation check

Fable checked each of the 12 fixes above on the real renders, read-only, and confirmed all 12.
Its evidence included:
- ffprobe keyframes equal to `compose.json` on all five rendered ads;
- a fake locked change hidden behind a timeline change, which exits 1;
- a fake failed render, which is refused;
- the REPLAY badge's box covering the HUD circle completely;
- one formula for reading time.

It also re-rendered the near-fail ad from its `ad.json` and got the same MP4 bytes as the
delivered file. Its verdict: **the step is done.**

It found two small new problems, both fixed in `9d15c8a`:

| Found | Fixed |
|---|---|
| Moving a layer that draws nothing (an edge pulse with zero strength) changed no composited frame, so `ad-diff` printed "the video is identical". But the moved boundary is a new keyframe, and 51 decoded frames did differ. The exit code was right; the printed proof was wrong | "Identical" only when no frame changed **and** the keyframes stayed; otherwise it is reported as a timing edit, and the `--decode` result is always printed. On the real ad it now says "keyframes moved ... frames 481-899" and "decoded: 481-531" (a test fails without the fix) |
| Copy-guard edges: "Level 10/12" flagged as odds, "1/5 of players" missed, "2 in 1 puzzle" flagged | Odds are now a fraction (the first number smaller), not a counter, a time or "2 in 1" (6 more test cases) |

---

## 5. Honest limits

- **The win ad's end card is 7.3 s.** The win's gameplay lasts only 13.5 s, so even after the
  hold and the replay there is time left. QA warns above 6 s. A longer level from the generator
  (Oct 12) fixes this.
- **No 60 s ad yet.** Joining two recordings is built and tested (on synthetic recordings). The
  60 s ad is rendered on Oct 12 from a generated easy level plus the near-fail, because today's
  four clips come from one level and would jump in clock and level badge.
- **The sounds stand in for the game's own.** They are synthesized because the project ships no
  audio. A real sound bank would replace them through the same events.
- **The font and sprites are read from the Unity project** at run time, never copied into the
  repo: the font is "all rights reserved" and licensed to Rollic. Without the project, an open
  fallback font is used, so a fresh clone without `CBJ` looks different.
- **The cursor is a ring, not a hand.** Its image slot is ready for Oct 14.
- **Caption copy comes from templates** per ending. The language planner writes it from Oct 13.
- **Timing edits are only local up to a point.** They move keyframes, so the MP4 can differ
  from the first moved keyframe on. In the tests above it differed for at most 3 s.
  `ad-diff` says this instead of over-claiming.
- **The files are larger** (about 10 MB instead of 6 MB per 30 s) because of the locality
  settings.
- **No AI yet.** This step is still the deterministic core. The AI half (planner, image and
  video inputs) is Oct 13-14 and must not slip.

## 6. Case fit

- **A usable, finished creative** (p.2, p.4, p.11): four 30 s ads with a hook on frame 0,
  captions, sound, a replay and a "PLAY NOW" end card, inside the social safe area.
- **Deterministic gameplay plus a generated shell** (p.5): the gameplay pixels come only from the
  real game; everything the compositor adds is a separate, named layer.
- **Controlled editing** (p.7): "keep everything, replace X" is now something the tool does and
  proves. Locked parts are enforced, and `ad-diff` shows that only X's frames and box changed,
  in the delivered MP4 too.
- **Consistency** (p.8): the same `ad.json` gives the same bytes, so any difference is an edit.
- **The examples** (p.12): this is the base for the controlled-modification example on Oct 13.

## 7. Plan

The compositor was planned for Oct 11 and is done. Next:
- **Oct 12:** the level generator as a command, a clean-win concept from a generated level, and
  the 60 s ad;
- **Oct 13:** the CreativeDoc, the language planner, and editing through `ad.json`;
- **Oct 14:** image and video inputs;
- **Oct 15:** UI and the QA loop;
- **Oct 16:** the write-up;
- **Oct 17:** a fresh-clone test, and submit.

## 8. How to reproduce

The full guide is `~/rollic-case/COMPOSITOR-CHECK-STEPS.md`: each step with the exact output to
expect. The short version:

```
cd ~/rollic-case/cbj-creative
uv run pytest -q
uv run cbj ad renders/nc01_near_fail -o ads/check_near_fail
open ads/check_near_fail/ad.mp4
jq '.layers.end_fact.text = "Only {clock_left} to spare!"' ads/check_near_fail/ad.json > ads/check_edit_text.json
uv run cbj compose ads/check_edit_text.json -o ads/check_edit_text
uv run cbj ad-diff ads/check_near_fail ads/check_edit_text --decode
```

## 9. Files

- **Code** (`cbj-creative/src/cbj/`):
  - `ad.py`: `ad.json`, its builder, events, facts, the copy guard;
  - `compose.py`: the renderer, the proof, QA and `ad-diff`;
  - `draw.py`: text, sprites, easing and blending;
  - `sound.py`: the synthesized effects;
  - `video.py`: frame-exact decode and encode;
  - `cli.py`: `cbj ad`, `cbj compose`, `cbj ad-diff`.
- **Tests:** `tests/test_ad.py` (50).
- **Docs:** the README section "Finished ads: the compositor".
- **Commits:**
  - `c0f746b`: the compositor;
  - `e5686bb`: first-check fixes and `ad-diff`;
  - `4c11e49`: second-check fixes;
  - `9d15c8a`: confirmation fixes and the picture strips.
- **Ads:** `cbj-creative/ads/nc01_*_30s/`, each with `ad.json`, `ad.mp4`, `compose.json`,
  `poster.png` and `audio.wav`. The `ads/` folder is not in git.
- **Strips:** `cbj-creative/reports/compositor/`.
- **Plan:** `COMPOSITOR-PLAN-2026-10-11.md`.
