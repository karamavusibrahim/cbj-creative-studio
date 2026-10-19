# Addendum to SPEC.md (2026-10-18, night): the optional soundtrack

Read `SPEC.md`, `SPEC-ENHANCE.md` and `SPEC-FEEDBACK.md` first; nothing there changes. The engine is the source of
truth: `../src/cbj/soundtrack.py` (read its module docstring) and the endpoint in `../src/cbj/app.py`. Do not edit the
engine. The relay already allows `soundtrack` as a POST behind the passcode.

**What it is.** A music bed written from the finished version's own concept (its look, tempo, parts, every block exit,
its ending and its clock), synthesised in a second, plus an optional spoken hook (NVIDIA Magpie TTS: the hook caption's
own words, or a line the user types). The result is an ordinary uploaded sound file in `studio/uploads/`; putting it in
the ad is the EXISTING music edit (`actions.direct({ music: name })` in `Inventory.tsx`, which makes a new version with the
edit report). Nothing else in the engine changes; say so in the UI once ("Made from this version's own concept; nothing
changes until you use it.").

## 1. Engine API

`GET /api/meta` → `features.soundtrack: {bed: true, voice: boolean}` (absent on an older engine: hide the card; `voice:
false` → the voice option is shown disabled with the tooltip "The engine has no voice (NVIDIA key or the voice extra)").

`POST /api/soundtrack {creative_id, version?, voice?: false, voice_name?: string, line?: string}` (passcode; synchronous,
1-6 s) →
```
{ file: "soundtrack-<slug>-v<N>[-voice].wav", path: "uploads/<file>",   // play it from <engine>/studio/<path>
  creative_id, version, seconds,
  description: string,     // one paragraph in plain words: what the bed does and why ("Bright major pentatonic: a stinger…")
  concept: { theme, mood, mode, bpm, bpm_ratio, curve, tempo, ending, duration_s, exits: [{at_s, block}], hurry_ticks: [s], … },
  voice: {text, voice, at_s, seconds, model} | null,
  voice_skipped: string | null,   // why no voice although asked (no hook caption; a non-English creative; no key / extra)
  made, took_s }
```
Errors: 400 `{detail}` (unknown creative or version), 502 `{detail}` when the TTS service failed (show verbatim; offer
"Make it without the voice").

Voice names the UI may offer (Magpie, English): `Magpie-Multilingual.EN-US.Mia` (default; `.Calm` is picked for a calm
tempo, `EN-US.Jason.Happy` for a fast one when `voice_name` is empty), `EN-US.Aria`, `EN-US.Leo`, `EN-US.Sofia`,
`EN-US.Ray`, `EN-US.Jason`, each with `.Calm` / `.Neutral` variants. Show them as short names ("Mia, calm"); send the
full name.

## 2. UI: a **Soundtrack (optional)** card

Where: (a) the Create page in phase `ready`, under the finished version's player, above the viewer's review card; (b)
the Edit workspace, in the right column below "Things in this ad" (the card acts on the version shown). Hidden when the
engine is offline or has no `features.soundtrack`; on a read-only showcase copy in Edit it is hidden.

Collapsed state: title "Soundtrack (optional)", one line "A music bed written from this version's own concept, and the
hook spoken if you want. Nothing changes until you use it." and:
- a checkbox **Speak the hook** (off by default; disabled with the tooltip when `features.soundtrack.voice` is false),
  and, when it is on, a small voice `<select>` (the short names above, default "Mia") and an optional text field
  **Say this instead** (placeholder: the version's hook caption text when the brief has one, else "Type the words to speak");
- a primary small button **Make the soundtrack** (passcode like Generate). While running: spinner + "Writing the bed…" /
  "…and the voice" (aria-live).
Result state (replaces the button area; a **Make another** link returns to the collapsed state and keeps the checkbox):
- an `<audio controls>` element with the file from `<engine>/studio/<path>` (the engine serves `/studio/uploads/*`), a
  download link with the file name;
- the `description` as a paragraph; when `voice_skipped` is set, an amber line with it verbatim;
- a short "What it follows" list from `concept`: "<mood> <mode>, <bpm> bpm<, speeding up to N>", "<n> block exits →
  plucks", "ending: <ending word>", "<n> hurry ticks" (only when > 0), "<seconds> s";
- the primary button **Use as the music** → exactly `actions.direct({ music: file }, "Music: <file>")` as Inventory does
  (a new version appears through the normal job flow; the card then shows "Used in v<N+1>" with the version link and stays).
  On the Create page, use the same direct call the Edit workspace uses (`/api/direct` with `creative_id`, `base`, `op`) and
  then show the new version as the page does after any edit.
Phone width: the card stacks; the audio element is full width.

## 3. Showcase / offline
Nothing is exported; offline the card is hidden.

## 4. Verification for `scripts/qa.mjs` (or a `qa-soundtrack.mjs` run from it)
- Online: the card renders on a ready Create page (from the intercepted finished job, as the feedback checks do) and in
  Edit; ONE real `POST /api/soundtrack` without voice on the creative `1018-110841-an-easy-color-block-jam` v3 (cheap, ~1 s)
  and assert the audio element's `src` ends with `.wav`, the description paragraph and the follow list; the **Use as the
  music** button posts `/api/direct` with `{op: {music: <file>}}` — INTERCEPT that POST (do not make a real version) and
  assert the body. Voice checkbox: default off; when `features.soundtrack.voice` is false (intercept `/api/meta`), it is
  disabled with the tooltip. The 502 path: intercept `/api/soundtrack` → 502 and assert the detail and the "without the
  voice" offer. Never POST `/api/soundtrack` with `voice: true` in qa (it calls the TTS service).
- Offline: no card. Keyboard: Tab reaches the checkbox, the select, both buttons. Screenshots at 1440 and 390.

## 5. Audio at creation time (added 2026-10-19): a video with audio in one flow

**Engine.** `POST /api/make` now takes `audio?: {bed: boolean, voice: boolean, voice_name?: string, line?: string}`. When
given (and not a draft), the job runs the workflow as before and then, as a last stage named `audio`, makes the
soundtrack for the version just made and applies it with the existing music edit. The job's result is therefore the
NEW version (v2 of a new creative) and carries `audio_added: {file, description, voice, voice_skipped, bed, from_version}`.
`bed: false` with `voice: true` keeps the creative's own music (when the prompt attached one) or leaves silence under the
voice. The progress lines of the `audio` stage read "the optional audio: …", "<file>: <description>", and the music edit's
own lines. The version made by the music edit has no viewer's review of its own: the review belongs to `from_version`
(the audio edit kept every frame, so it is the same picture).

**UI, Create page, compose phase.** A small section **Audio (optional)** inside the Generate card (under the prompt,
above the Generate button), collapsed to one row by default:
- checkbox **Soundtrack bed from the concept** (off by default);
- checkbox **Speak the hook** (off; disabled with the tooltip when `features.soundtrack.voice` is false); when on, the
  voice `<select>` (short names, default Mia) and the field **Say this instead** (placeholder "the hook caption");
- one line of help: "Added after the creative is made, as a music edit you can see in the version history. Nothing
  else changes."
The choice is remembered for the session (state, not storage). On Generate → Make it, send `audio` on `/api/make` only
when at least one box is on. The progress card shows the `audio` stage like the others ("Adding the audio…").
On ready: the version shown is the result (the one WITH audio); under the player a small chip **With audio** and the
`audio_added.description` in one muted line; if `voice_skipped` is set, show it in amber. The viewer's review card
loads the review of `audio_added.from_version` and says "Reviewed as v<N>, before the audio was added (the audio edit
kept every frame)". The versions strip (if shown) lists both versions. The Soundtrack card from §2 stays available for
"Make another".

**Edit workspace.** Unchanged (the §2 card is the way to add or replace audio there).

**Verification.** `scripts/qa.mjs`: the Audio section renders collapsed; opening it shows the two boxes; with voice
unavailable the second is disabled; the Generate → Make it flow posts `/api/make` with `audio` (INTERCEPT `/api/make`
and `/api/jobs/*`; never run a real make in qa) and the ready state renders from a fixture job result that has
`audio_added` (write `scripts/fixtures/job-make-audio.json` from the shape above: a v2 with `audio_added.from_version: 1`);
assert the With audio chip, the description line, the review line naming v1. Offline: section hidden. Screenshots at
1440 and 390.

## 6. Narration = the creative's own captions (added 2026-10-19, supersedes "Speak the hook" wording)

The voice no longer speaks the hook alone by default: it **narrates the creative's own captions as they appear** (the
hook, the play captions such as the mistake or the result, the end card's fact and call to action; the game's title is not
read), each line placed 0.15 s after its caption appears and never overlapping the previous line; times like `00:03`
are spoken as "3 seconds". So what is said is always what the creative shows, when it shows it. The engine returns
`voice: {text (all lines joined with " / "), voice, at_s, seconds, model, narration: "captions"|"hook", lines: [{layer,
text, at_s, seconds}]}`; `description` ends with "<Voice> narrates the creative's own captions as they appear: “…” at 0 s;
“…” at 21 s; …". `POST /api/soundtrack` and the `audio` object of `/api/make` take `narration: "captions"` (default) |
`"hook"`; `line` still replaces the hook's words only.

**UI changes (both the §2 card and the §5 section):**
- The checkbox label becomes **Narrate the captions** (tooltip "NVIDIA Magpie speaks each caption of this creative as it
  appears"); under it a small segmented choice **All captions** (default) / **Hook only** → `narration`.
- "Say this instead" becomes **Different first line** (placeholder: the hook caption; help "replaces the hook's words; the
  other captions are read as written").
- In the result, under the description, list the lines as small rows: "0.2 s · “Can you beat the clock?”", one per
  `voice.lines` entry, so the designer sees exactly what is said and when.
- qa fixtures: refresh `scripts/fixtures/soundtrack.json` from one real call WITHOUT voice (unchanged), and write the
  voice shape by hand into the fixture used for the result state (3 lines) — never call the TTS in qa.
