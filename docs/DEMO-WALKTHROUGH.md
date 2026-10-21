# Recording script: every function of CBJ Studio, with narration

For the demo video that accompanies the technical report. Site: https://cbj-creative-studio.vercel.app with the Mac
engine online (header pill "Engine online"). Record at 1440×900, 30 fps. Browser recordings carry no sound, so the
narration is recorded separately (or read live over a screen recording with system audio) and the ad's own audio is
spliced in from the MP4 at scene 5.

Two ways to record:
- **Automated (used for take 3)**: `cd cbj-creative/web && node scripts/record-demo-v2.mjs https://cbj-creative-studio.vercel.app <out-dir>`
  drives the site with a visible cursor, makes real engine calls (three creatives, two edits, one feedback record, one
  analysis, one distillation) and writes `demo-raw.webm` + `chapters.json`; `demo/make-cut.py` then writes the full
  and the cut MP4 with a chapter list. It covers every scene below except the hand-typed Turkish Generate (scene 5
  uses an English prompt) and the optional re-film edit (11b). The older `record-demo.mjs` is the seven-scene first take.
- **By hand**: follow the scenes in order; the "Say" lines are the narration.

Total real time about 18-22 min; cut the waits (model calls, the Unity recording) to 8× as in the first take and the
film lands near 8-9 min.

Before recording: the engine online (`scripts/engine-online.sh status`), the owner's feedback store empty or holding
only real records, one finished creative of each kind in *Recently created*, the passcode at hand, the test assets
ready (a sticker PNG, a texture PNG, a reference picture of a board, the Trailer 2 reference MP4).

---

## Scene 1 · The studio and its header (0:30)

**Show** the Create page. Hover the header: nav (Create, Edit, Showcase, Feedback), the engine pill, the feedback
bubble, the key icon, **Help**, the lock. Open **Help → "How it works"** and scroll its four sections and "The edit
contract" (Locked / Allowed / Forbidden). Close it. Click the lock, type the passcode (masked), Unlock.

**Say** "This is CBJ Studio. The website is a thin client; the engine behind it runs on a Mac with the
provided Unity game and ffmpeg. The header shows whether that engine is online or busy. Making and editing are behind a
passcode. The Help sheet states the one rule every edit obeys: what is not named is locked."

## Scene 2 · Prompt enhancement, with a Turkish request (1:30)

**Do** type: `Zor bir seviye yap, bir bomba kırmızı blokları temizlesin, sadece %1 çözebilir, 45 saniye` → **Enhance
prompt**. Show the Enhanced card: the *translated* rows, the bomb *replaced* by a legal key move with the reason, the
statistics claim *removed*, the "You may want to add" questions. Tap one option; show it appended as a chip. Press
**Undo**, then redo it.

**Say** "The enhancer rewrites a request in the words the planner reads reliably. It translates, it replaces what the
game does not have with the closest legal thing and says so, and it removes claims the ad rules forbid. It never adds
an ask of its own: what it thinks is missing becomes a question the user may tap. Every change is shown next to the
user's words and can be undone."

## Scene 3 · Ideas from trends and from a link (1:00)

**Do** open **Start from a trend (optional)** → **Get ideas**. Show 2-4 idea cards (trend, why now, mapping, hook,
source), the **Skipped** fold with reasons. Paste an article URL → **Read link**; show the "From your link" idea.
Press **Use this prompt** on one, cancel the replace (keep the enhanced Turkish prompt).

**Say** "Optionally the day's trending searches and news, or a pasted link, are turned into complete prompts in the
house style, each with its source and the reason it is current. Brand-bound or unsafe trends are skipped and the
reason is listed. An idea becomes a creative only when it is put in the box and generated like any other request."

## Scene 4 · Creative specifications and audio options (0:40)

**Do** open **Creative specifications**: duration 45 s, format 9:16, difficulty Hard, arc "Near-fail clutch win".
Open **Audio (optional)**: tick "Soundtrack bed from the concept" and "Narrate the captions", voice Mia. Open
**More**: show "Review as a viewer after making" and "Revise if the checks miss something (up to 2 rounds)" both on.

**Say** "The optional specifications add words to the prompt; the plan will show how they were read. Audio is added
after the creative is made, as an ordinary music edit, so the silent original is kept as version one. Review and
revision are on by default."

## Scene 5 · Generate: plan, record in Unity, compose, review (4-5 min real, cut to ~1:30)

**Do** **Generate creative**. Show, as they appear: **What the tool understood** (the table of the eight prompt
controls with applied / default / adjusted / not supported, "Planner: … N s", the "Brief as data" fold); then
**Progress** stages (plan, level, play, record, compose, review, revise, audio, done) with the live log; then the
result: the phone player (play 10 s with sound in the final cut), "With audio" and the narrated lines with their
seconds, the fact chips; **Level & gameplay**: the board picture, the moves list (key move, mistake, hesitates), the
**Checks** rows with where each was measured; **As a viewer**: Ready to ship / Worth a fix, the score tiles marked
*measured* or *model*, "Does it match the request?" rows, the fixes, the suggested edit.

**Say** "The planner writes only data: one row per control of the brief, nothing else. The level is generated and
proved solvable by an exact solver; the play is scripted for a near-fail; then the real game plays it, frame by frame,
at a fixed time step, and records itself. The compositor adds the hook, the captions and the end card. Every check is
measured from the game's own log: each drag, the clock, the rules. The viewer's review is the one opinion from a
model, and its measured scores are marked apart from its judged ones. If a measurable fact was missed, the loop
revised it; the first version is kept either way."

## Scene 6 · Feedback under the result, tied to a step (0:50)

**Do** click the flag on a "partial" row of the review (or on a failed check). Show the panel **Was this what you
asked?** pre-filled with the step chip and the item. Choose "Something is off", write one sentence, name, Send. Show
"Thanks, saved as fb-… · it is tied to …".

**Say** "Under every result a designer can say whether it was what they asked, tied to the step it concerns: how the
request was read, the level, the gameplay, the video, the review or the revision. A flag on any row pre-fills that.
The engine captures the scene itself, so the owner later sees exactly what the system did at that step. Nothing
changes automatically."

## Scene 7 · The report (0:30)

**Do** **Download report** (HTML). Open the file: sections 1-10 (the request, how it was read, the steps with
seconds, the level and the play, the checks, the review, the revision, the feedback left, the files).

**Say** "Anyone who needs the intermediate steps downloads them as one report: what was asked, how it was read, every
stage with its seconds, every check, the review and the revision."

## Scene 8 · Image-guided creative (3 min real, cut to ~1:00)

**Do** **Create another**. Attach the reference picture of a board; type `Use the board in this picture, make it a
little easier, clean win, 30 seconds`. Show the role badge "reference image". Generate. Show the **Reference to
creative** card: Board read, Adapted / Not copied, confidence; then the result's **Image:** rows (the board is the
picture's, colours, likeness) in the checks.

**Say** "A picture is first given a role: a style, a board to copy, an asset to place, or a change to an existing
creative. Here the board is read cell by cell, verified against the pixels, solved, and then drawn by the game itself
in its own colours. The rows prove the board is the picture's."

## Scene 9 · Video-guided creative (4 min real, cut to ~1:15)

**Do** attach the Trailer 2 MP4; type `Use the same game design and the same scenario, just use fewer blocks`. Show the
badge "reference video, read whole, never placed in the ad". Generate. Show the Reference card with **The
reference's timeline** (hook / gameplay / near-fail / end card), "Board read", "Mechanics translated", "Not used: not
in CBJ"; then the result and the **Reference:** rows (the ending, the pacing, the hook, the part lengths,
nothing copied).

**Say** "A reference video is reduced to one small copy and read whole for its structure, hook, ending, pacing and
captions; the part boundaries are snapped to real scene cuts. The words asked for the same design, so the first frame
of play was read cell by cell and the board was copied with two blocks fewer. Another game's mechanics are never
borrowed; what was not used is listed."

## Scene 10 · Controlled editing, the designer's view (1:30)

**Do** on the first creative press **Edit this creative**. Show the workspace: **Things in this ad** (pictures,
captions, sound, music with times). **Edit text** on the hook → `Beat the clock!` → Apply. While it works, the
**Progress** card. Then **What changed**: the verdict line, **Locked / Allowed / Forbidden** boxes, "As a viewer" line.
Play **Before / after → Play both**. Show the **Version timeline** (v2 ← v1).

**Say** "Editing never regenerates. An exact thing, a caption here, is changed in code with no model at all. The new
version's report lists what was locked, what was allowed to change, and whether anything changed without being asked;
that last box must be empty. The gameplay frames of the approved video were copied byte for byte."

## Scene 11 · A prompt edit with an asset, and the details (1:30)

**Do** attach the sticker PNG; type `Keep everything exactly the same, but replace the end card picture with the
attached asset` → **Enhance prompt** (show the pointer resolved) → **Apply change**. Then switch **Details** on: the
**Checklist** badges (level, moves, move timing, gameplay render reused, duration, camera, HUD, captions, pictures,
audio, route), "Show the evidence", the **Frames** line ("X of Y frames changed … every changed pixel is inside the
changed layers' boxes"), **Compare** v3 with v1, **Metadata**. Flag one report row to show the feedback tie-in.

**Say** "A request that needs reading goes to the planner with the inventory of this ad, and the planner may change
only the field groups it declares and the words support. The proof is measured from the files: nine rows, the frames
that changed, and that every changed pixel sits inside the edited layer's box. Any two versions can be compared."

**11b (optional, 1 min real)** `Make the background autumn orange` → a re-film: the same level and drags filmed again
in the game; the report says the game state was identical on every frame.

## Scene 12 · Soundtrack from the Edit page (0:40)

**Do** open **More: music** → **Make the soundtrack** (bed + hook narrated) → show "What it follows" chips (bpm, block
exits → plucks, ending, ticks) → **Use as the music** → "Used in vN".

**Say** "The music bed is written from the version's own facts: its tempo, each block's exit, its ending. It is
applied through the same edit path, so it comes with the same report."

## Scene 13 · The owner's page: records, evidence, analysis, lessons (1:30)

**Do** nav **Feedback**. Records tab: the record from scene 6 with its step and item; expand **What the engine did**
(facts, log lines); press **Analyze what happened** → verdict (the system / taste / unclear), what, why, quoted
evidence, smallest change. Lessons tab: **Distill now** → LESSONS v1, Part A per workflow with evidence chips, Part B
per designer; type a correction → **Apply correction** → v2; show the version select and rollback.

**Say** "The owner sees every record next to the engine's own account of that step, and can ask for an analysis that
quotes only the evidence and says whether it was the system or a matter of taste. Records are distilled into a
versioned lessons document, kept apart in two tracks: what the workflows should do differently, and how each designer
asks. Corrections in plain words make a new version; any version can be restored. This is how the workflows are tuned
from evidence over time."

## Scene 14 · Showcase, with the engine off the critical path (0:40)

**Do** nav **Showcase**: filters (Text, Image reference, Video reference, Edits), a card → the detail page: player,
"What the tool understood", the reference card, checks, review, and for an edit the before/after pair and the report.

**Say** "Finished creatives are exported with their evidence to a static showcase that works even when the engine is
offline."

## Scene 15 · Your own accounts (0:40)

**Do** click the key icon → **Your keys**: the Gemini key field, the planner choice ("This studio's planner" / "My
Anthropic key" with the model chips), "Remember on this device". Save a Gemini key (masked) → the header pill "Your
keys: Gemini". Optionally a terminal: `uv run cbj setup-check --live`.

**Say** "By default the studio runs on the owner's Claude login and Gemini key. Another team can run the engine on its
own Claude CLI login and Gemini key, checked by one command, or, on the hosted site, send its own keys with each
request. The keys travel in headers for that job only and are never stored."

## Scene 16 · Closing (0:20)

**Show** the folder of one version (`studio/<id>/v2/`: brief.json, level.json, result.json, compose.json, parts.json,
review.json, log.json) and the skills folder.

**Say** "Every creative is a folder of plain files; every claim in the interface can be re-checked from them. The
rules the agents follow are written as skills next to the code."

---

## Checklist of functions covered

| function | scene |
|---|---|
| header: engine status, passcode, Help sheet | 1 |
| prompt enhancer (translation, replacement, removal, questions, undo) | 2 |
| trend ideas, link ideas | 3 |
| specifications, audio options, review and revise switches | 4 |
| text-to-creative: brief table, progress, player, checks, viewer review | 5 |
| feedback panel, step chips, flags | 6, 11 |
| report download | 7 |
| image-guided creative, reference card, Image rows | 8 |
| video-guided creative, timeline, copied board, Reference rows | 9 |
| direct edit, Locked/Allowed/Forbidden, before/after, versions | 10 |
| prompt edit with an asset, Enhance on Edit, Details, checklist, frames, Compare, metadata | 11 |
| re-film edit (optional) | 11b |
| soundtrack and narration from Edit | 12 |
| owner: records, evidence, Analyze, Lessons distill/correct/rollback | 13 |
| showcase gallery and detail, offline | 14 |
| Your keys, setup-check | 15 |
| files and skills | 16 |
