# Core requirement 5: analysis of the research document and the final approach (2026-10-17)

Inputs: ~/Downloads/Core_Requirement_5_Controlled_Creative_Editing_Research.md (the research document, 13 sections),
the case PDF (p.7, p.8, p.10-13), the game (~/Downloads/CBJ, every script), the tool as it stands today (cbj-creative:
workflows/edit.py, route.py, edits.py, editreport.py, compose.py, ad.py, CreativeRunner.cs, the stored creatives in
studio/), REQ5-UNITY-CONTROLLED-EDITING-2026-10-17.md (this morning's Unity feasibility note) and the Oct 12 / Oct 15
editing reports.

## 1. Verdict on the research document

The document's thesis is right and is already the tool's architecture: "an invariant-first, non-destructive editor;
no text-to-video generator in the edit loop; a request is a constrained, versioned patch; preservation is proven, not
promised." Its value today is vocabulary and two small additions, not new building. Three of its proposals do not fit
this game or this submission and should be named as non-goals rather than built.

| research proposal | status in the tool | decision |
|---|---|---|
| Strategy 1: source-aware scene patching; the creative kept as complete editable state (level, moves, timeline, camera, assets, seeds) | BUILT. Each version folder holds brief.json (what was asked, as data), level.json (the game's own LevelData), the recorder job (drags with per-cell paths and per-drag timing, camera keys, visuals, hide list, clock), the recording's result.json and frames.json (every drag, every frame: clock, finger, block positions, hash), ad.json (segments, layers, audio, locked parts), version.json (parent, proof, review). Recordings are content-addressed and reused | keep; present it as the "Creative Project Manifest" the document describes, in its words |
| "Store the actual state/action trajectory, not just a seed" (§3.3) | BUILT. The drag script is cell by cell; the recorder checks the cells the block really entered against the script; Time.captureDeltaTime fixed step; Random.InitState; particles seeded; DOTween on scaled time (verified: no unscaled tweens); the button fade that runs on real time is zeroed | keep; this is the sentence for "deterministic replay" in the write-up |
| Typed patches with an allowlist; the LLM cannot mutate unrelated fields (§3.2) | BUILT. The planner declares field groups; brief.merge takes only declared groups whose change the prompt's words support; route.verify restores play fields a plan drifted; exact edits (pictures, captions, sound, music) are made in code with no model (direct_edit) | keep |
| Edit contract: locked / allowed / forbidden (§2) | BUILT as brief["keep"] / brief["changed"], ad.json "locked" with origin hashes, and the edit report's statuses kept / changed as asked / changed because of the asked change / CHANGED WITHOUT BEING ASKED (fails the edit) | adopt the three words in the write-up; they are clearer than the current four statuses for a reader |
| Mode A1: patch the asset in Unity, re-render the whole video from the frozen timeline, frame-diff for drift (§3.4) | BUILT as the re-film tier: colours, background, camera, HUD, clock; proof = game state identical on every frame (the recorder's own log), pixel drift tolerance measured from the pipeline (about 1 % of frames differ by a few pixels from the graphics driver, never the state) | keep |
| Mode A2: delta-only render; composite only the changed pixels into the approved video; prove outside-ROI pixels unchanged (§3.4) | BUILT for every compositor layer: the recording's frames reused byte for byte, changed pixels measured inside the edited layer's box, the delivered MP4 patched at the GOP level (untouched GOPs are the approved file's bytes, IDR at every boundary) | keep |
| Object-ID mattes, clean-plate passes, Unity Recorder, URP Render Objects for in-game delta renders (§3.4, S1, S2) | NOT APPLICABLE. The project is the built-in pipeline (no URP); Unity Recorder does not run in batch mode (verified Oct 10), the runner captures through a RenderTexture; and the re-film tier already gives exactness with depth, light and particles right. A delta pass would add machinery to reach a weaker proof | do not build; one sentence in "decisions" |
| Replacement variant 1: texture / material change (§3.5) | BUILT twice: in-game colours per slot (shared materials repainted before the board is built) and a compositor "skin" layer that draws a picture on one block of a colour on every gameplay frame from the recorded positions. NOT built: an in-game texture (`_MainTex` on the slot's materials; the shader has it; the Lego pieces' UVs are unverified) | keep; in-game texture = next step unless an hour is free (REQ5-UNITY note §3) |
| Variant 2: prefab of comparable geometry (§3.5) | NOT BUILT. Possible: BlockPieceConfig's prefabs are swappable in the player and the game re-materials and re-colliders them; a user GLB via Unity's glTFast | next step, with the mechanism named |
| Variant 3: a fundamentally different shape (§3.5) | NOT APPLICABLE as a visual edit: a block's shape IS gameplay. The document's own rule applies ("a visual change must preserve the collision footprint or be rejected as a visual-only edit"), and the game enforces it: colliders come from the pivot, not the visual | say so in one line |
| "obstacle_04 … traffic cone … orange decorative obstacle beside the centre passage" (§3.1, Demo 1) | MISMATCH. Color Block Jam has no decorative obstacles: only blocks, holes (inactive cells), borders and gates (verified in every script). "Use this object instead of the current obstacle" maps to the walls (built: the picture drawn on the wall cells in perspective, proof tier 1) or to a block (the skin slot) | keep the mapping; the write-up states what an "obstacle" is in this game |
| Approach B: independent compositing layers; "change just the hook" (§4) | BUILT (ad.json layers; ffmpeg; Remotion not used, by decision) | keep; the hook edit is one of the examples |
| Approach C: source-blind MP4 surgery with SAM 2/3, tracking, clean plate, inpainting (§5) | NOT BUILT, by decision. The case's loop (p.10) edits the tool's own creatives, which carry their source; an uploaded video that is one of the tool's own is matched by bytes and edited from its data; a foreign video is routed to "adapt the concept" (requirement 4) with a plain message. The document's own cautions decide the rest: no proof possible outside the mask, hidden background unrecoverable, ProPainter / E2FGVI non-commercial | non-goal in the write-up, two sentences; the better fallback for THIS game is reconstruction into the document (board + drags read from the video and validated by the solver), REQ5-UNITY note §5 |
| Patch compiler + evidence report; typed tools; the agent never issues raw ffmpeg/Unity commands (§6) | BUILT: route (code) → planner or direct edit → brief.check → studio.make (stages re-run only when inputs changed) → edit report → viewer review → feedback → up to two revisions that must return unasked changes to the base version | keep; the write-up's diagram |
| Provenance DAG, undo, compare any two, cached unchanged layers (§6.2) | BUILT: "from" per version, edit from any version, compare any two, content-addressed recordings | keep |
| Three-panel playback: original / revised / change heatmap (§7) | NOT BUILT. The report gives numbers (frames changed, the changed-pixel box, GOP bytes copied) and the review sheet, no picture of the difference | ADD today: cheap and it is what a reviewer looks at first |
| Outside-ROI and inside-ROI metrics reported separately; tolerances derived from measured pipeline behaviour, not chosen (§7) | BUILT (the box containment check; the measured drift tolerance) | keep; say where the tolerance comes from |
| Release policy: hard fail / review / pass (§7) | BUILT as the verdict line and the revise loop | keep |
| Demo 4: a rejected semantic contradiction ("recolour the blue block red") (§8) | PARTLY BUILT: a repainted colour that comes within MIN_COLOUR_DISTANCE of another slot or of the background is deepened or reverted with the reason written; a no-op edit is refused | ADD as a shown example (no code): it is the "control, not creativity" signal the document describes |
| 10-day roadmap, repo structure, API (§9) | moot: day 10 is today; P0 and P1 exist | ignore |

Net: adopt the vocabulary (manifest, edit contract, tiers, evidence report), add the heatmap strip and the rejected-edit
example, name Approach C and the delta render as non-goals with reasons, and spend the rest of the day on the write-up
and the fresh-clone test.

## 2. The final approach (the write-up's "How controlled editing works", one page)

**The creative is a document, the video is a view of it.** A creative is stored as its stages, each a file the next
stage is a pure function of: the brief (every control of the case as data), the level (the game's own JSON), the play
(the drag script, cell by cell, with per-drag timing), the film (the real game recorded at a fixed step, with its own
log of every frame), the ad (segments, layers, audio), the video. Nothing in the video exists outside these files.

**An edit is a change to the document, routed in code before any model reads it.** The route decides from the
version's own parts manifest whether the request is an exact operation (a picture, a caption, the sound, the music:
made in code, no model) or needs the planner. The planner then sees the current brief, the inventory of things in this
ad and the ad's parts, and may change only the field groups it declares, and only those the request's words support.

**The edit contract.** Locked: everything the request did not name (the level, the drags, the camera, the ad's parts
and their timing, every other layer, the sound). Allowed: the named element, in its own box and window. Forbidden: any
other difference; one fails the edit and is sent back to the loop.

**Four tiers of preservation, lowest sufficient tier wins, each with its own proof:**

| tier | used for | what re-runs | proof |
|---|---|---|---|
| 1 compose | captions, pictures (logo, stickers, end card, button, the walls' picture, a block's skin), sound, music | the compositor only | gameplay frames reused byte for byte; changed pixels inside the edited layer's box; the delivered MP4 keeps the approved file's bytes in every untouched GOP |
| 2 re-film | colours, background, camera, HUD, the clock, the level number | the same level and drags filmed again in the game | the game's log: state identical on every frame; the ad's timing pinned |
| 3 re-plan | a second mistake, another order, pacing that needs new moves | the closest of 24 plays | "the first K of M moves are the same, N in common" |
| 4 re-generate | harder, easier, a different board | the closest board (at most 3 changes), the HUD number kept | the two boards side by side, the changes listed |

**The evidence report.** Nine rows (the case's seven items plus captions and sound), each measured from the stored
files, never from the plan: kept / changed as asked / changed because of the asked change (reason written) / changed
without being asked (fails). Then the pixels: frames changed, the box, bytes of the approved video kept. Then the
picture: original, revised and the difference heatmap at the most-changed frame (added today).

**The loop.** After the proof, a viewer review against the request; the report's unasked changes, the audit's
missed facts and the viewer's first fix become one feedback line; at most two revisions, each itself an edit of the
version it criticises under the same contract.

**What is refused, and said.** A recolour that makes two gates look alike (deepened or reverted, reason written); a
no-op edit; an edit of a video the tool did not make (routed to "adapt the concept" with a plain message); a block
shape change dressed as a visual edit (it is a level edit, tier 4, and the report says so).

**Deterministic and generative parts.** Deterministic: the route, the exact edits, the solver, the generator, the
game, the compositor, the report. Generative: reading the request into the brief (an LLM with a schema), reading an
attached picture or video, the viewer's review. The generative parts write data; they never draw a gameplay pixel.

## 3. Today (submission day), in order, time-boxed

| # | step | time | why first |
|---|---|---|---|
| 1 | Commit the working tree. `git status` shows 27 modified files and 9 new modules since the last commit of Oct 13 (edit.py, imageplan.py, llm.py, boardedit.py ...). A fresh-clone test of an uncommitted repo tests the wrong thing | 15 min | the submission is the repo |
| 2 | The heatmap strip: for an edit version, decode the base and the new video (compose.diff already decodes and finds the changed frames), take the most-changed frame, write `diff.png` = original / revised / abs-difference heat (changed box drawn), store it beside version.json, show it in the UI's report card and in Compare | 45-60 min | the reviewer's first look; the one thing the research document adds that is missing |
| 3 | The examples for p.12. One chain on the final code from one base creative: (a) "Keep everything exactly the same, but replace this asset" with an attached picture (tier 1, the p.4 sentence), (b) "make the blocks pastel" (tier 2), (c) "add a second mistake" (tier 3), (d) the refused recolour (two gates alike) and the no-op, with their messages. Each with its report and heatmap. Reuse studio/1015-074810 if time is short: its eleven edits are proven | 60 min | the required "controlled modification" deliverable, shown as a ladder |
| 4 | The write-up section from §2 above, plus the Creative Document table (REQ5-UNITY note §2: element, owner, field, what re-runs, proof) and the non-goals with reasons (delta render, SAM/inpainting, generative video, arbitrary geometry) | 60 min | p.12 asks for exactly these headings |
| 5 | Fresh-clone test from the README on a clean folder; fix; submit | 60 min | p.12: "source code and necessary setup instructions" |
| 6 | Only if hours remain: in-game block texture (`_MainTex`, one render to check the UVs, quad fallback). Otherwise it is the first item of next steps with the mechanism named | 60 min | upgrade of the skin slot from one block to all blocks, lit and clipped by the game |

Not today, and not touched: the proof logic, the pin, the closest-play and closest-board searches, the text, image
and video workflows.

## 4. Next steps for the write-up (each with the mechanism, none as a promise)

1. In-game textures on the slot's materials (`Material.SetTexture("_MainTex")`, pictures via ImageConversion.LoadImage).
2. A user 3D object as the block piece (BlockPieceConfig prefabs swapped in the player; glTFast runtime import; orientation and scale per piece type).
3. The walls as an in-game quad per inactive cell (depth-correct occlusion; proof tier 2).
4. HUD sprites as slots (Image.sprite from a loaded texture).
5. Reconstruction of an external Color Block Jam creative into the document (grid from the board's box, per-cell colour classifier, drags from rest-state differences, every candidate validated by the solver; chess and Go video-transcription precedent), so a foreign creative becomes editable under the same contract. Source-blind masking and inpainting stay out: no proof outside the mask, non-commercial licences.
6. Exact edits in the UI for the game-owned elements (colours, background, camera zoom, clock, level number), today planner-only.

## 5. Risks in the demo and what to say

- The planner takes 15-45 s per edit; exact edits take none. Show an exact edit first.
- One job at a time (one game player process).
- "This asset" with nothing named is a written assumption with the alternative; "Things in this ad" is exact.
- The skin slot covers one block of a colour, drawn by the compositor from the recorded positions; the game's
  lighting is not on it (multiply blend keeps the shading). The in-game texture is the upgrade (§4.1).
- A logo spans the whole play, so a logo swap re-encodes most GOPs; the proof is still pixel-local.
