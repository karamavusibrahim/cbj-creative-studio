# A designer's edits on one creative, proven end to end (2026-10-15)

Question: a designer has a creative they like and asks for one change ("change this asset", "change this sentence",
"change the background colour"). Does the tool do it without regenerating, and does it prove that nothing else moved?

## 1. Set-up
- Base creative `1015-074810-create-a-hard-color-block` v1: "Create a hard Color Block Jam level on a crowded board with
  several walls and red, blue, green and yellow blocks. The player makes one wrong move, then clears the board with one
  second left on the clock. A 30-second portrait creative with our logo asset_a_logo.png in the top-left corner and the
  stopwatch icon beside the hook. Keep the game's own look." Made in 49 s; viewer review: ship.
- Four pictures generated with Higgsfield (gpt_image_2_5, 1:1, 0.25 credit each, 1 credit in all), chosen to fit the
  game's slots: a bricks app-icon logo, a red-brick mascot sticker on white, a wooden crate tile for the walls, a blank
  orange pill button on white. They are in `case-test-2026-10-15/hf_assets/` and `cbj-creative/studio/uploads/`.
- Each edit was a plain-words prompt on the version before, through the UI's API (`case-test-2026-10-15/edits.py`);
  every plan, proof and review is in `edits_results.json`.

## 2. Results, one row per request

| v | request | what ran | edit report | bytes of the approved video kept | viewer |
|---|---|---|---|---|---|
| 2 | Replace our logo with hf_logo_bricks.png | compose only | Only what was asked changed (Other assets); pixels inside the logo's box | 76 of 900 frames (the logo spans the whole play) | ship |
| 3 | Use this object instead of the current obstacle (crate) | compose only; the crate drawn on the wall cells in perspective | Only what was asked changed (Composition, Other assets); pixels inside the walls' box | 231 of 900 | ship |
| 4 | Put hf_mascot_brick.png on the end card instead of the coin pile | compose only | Only what was asked changed (Composition, Other assets) | 745 of 900, 1 of 10 GOPs rendered | ship |
| 5 | Use hf_button_orange.png as the button | compose only | Only what was asked changed (Composition, Other assets); the button's text stays | 745 of 900, 1 of 10 GOPs rendered | ship |
| 6 | Change the hook to "Beat the clock!" | compose only | Only what was asked changed (Timing, Composition, Captions) | rendered in full (the hook's window moved; fixed after, see v10) | ship |
| 7 | Make the background behind the board light mint | the same job filmed again with the new look | Only what was asked changed (Visual structure); game state identical on every frame | re-filmed by design | ship |
| 8 | Make the red blocks pink | the same job filmed again | Only what was asked changed (Visual structure); captions now say "pink" | re-filmed by design | ship |
| 9 | Keep everything, but remove the logo | compose only | Changed as asked: Other assets; also changed because of it: Composition (the caption band widens back) | 76 of 900 | ship |
| 10 | Change the hook to "Can you make it?" | compose only | Only what was asked changed (Timing, Composition, Captions): the longer sentence keeps its reading time, 1.5 s -> 1.6 s | rendered in full | - |
| 11 | Change the mistake caption to "Oops, blocked!" | compose only | Only what was asked changed (Composition, Captions) | 840 of 900, 1 of 10 GOPs rendered | - |

Every request re-used the base recording: nothing was regenerated. The two colour requests re-film the same drags and
timing in the real game, because the game draws the blocks and the background; the proof there is the game state,
identical frame for frame.

## 3. What the test changed in the tool
- A generated picture on a plain background becomes a sticker on its way in (`draw.cutout`, a corner flood fill, no
  model): the mascot and the button arrived on white and sit clean on the end card; a full tile (the crate) is untouched.
- The obstacle rule read "on a crowded board with several walls ... our logo" as a picture for the walls: it now needs
  the obstacle, a picture word and a placing verb in one sentence.
- A failed plan posted to /api/make once made a creative of defaults: an empty brief is refused.
- The hook keeps its approved time on screen in every edit (a shorter sentence had shortened it and moved a keyframe).
- A patched render carried the approved render's layer boxes into layers it had redrawn differently (the caption band
  after a logo left), which made the next edit report a false "changed without being asked": the old box is kept only
  for frames the patch did not render.

## 4. Limits seen
- A logo in a corner spans the whole play, so a logo swap re-encodes most GOPs (the proof is still pixel-local).
- A sentence that needs more reading time than the old one lengthens its caption; the report lists Timing as asked.
- The viewer still answers "maybe" on every version: the edits do not touch what makes a viewer tap.
