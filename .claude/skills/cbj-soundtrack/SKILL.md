---
name: cbj-soundtrack
description: The optional soundtrack of cbj-creative (src/cbj/soundtrack.py) - a music bed synthesised from a finished version's own concept (look, tempo and curve, parts, every block exit, ending, clock) and an optional spoken hook by NVIDIA Magpie TTS, delivered as an uploaded sound file that the existing music edit places. Use when making or judging a soundtrack, when deciding what the bed may follow, when the voice is skipped, or when touching the module; also when someone asks for music or audio generation on NVIDIA build.
metadata:
  spec-version: "1"
  last-verified: "2026-10-19"
---

# The optional soundtrack

## 1. Purpose
An ad has sound effects and, when a file is attached, music. Nothing wrote music for a concept. The soundtrack step
writes a bed from the facts of a finished version and, if asked, speaks the hook; the result is an ordinary uploaded
sound file. Putting it in the ad is the existing controlled music edit, so the workflows, the planner and the compositor
are untouched and the edit report proves what changed.

## 2. Source of truth
- `src/cbj/soundtrack.py`: `THEME`, `BPM`, `CURVE_RATIO` (the mapping), `concept()` (what is read), `render_bed()` (what
  is played), `synthesize()` / `mix_voice()` (the voice), `make()` (files), `describe()` (the sentence shown).
- The inputs: the version's brief (`visuals.theme`, `pacing.tempo`, `pacing.curve`, `language`) and its parts manifest
  `parts.json` (`duration_s`, `parts`, `layers[hook]`, `moments[kind=exit]`, `clock`, `gameplay.ending`); see
  `cbj-controlled-editing` for the manifest.
- `src/cbj/app.py`: `POST /api/soundtrack`, `features.soundtrack`; `src/cbj/cli.py`: `cbj soundtrack`. Tests:
  `tests/test_soundtrack.py`. The site: `web/SPEC-SOUNDTRACK.md`. Why and the measurements:
  `~/rollic-case/SOUNDTRACK-2026-10-18.md`.

## 3. Facts
**What the bed follows, and nothing else.** Theme → mode and root (game, candy, pastel, custom: major pentatonic; neon,
dark: minor); tempo → 84 / 104 / 124 bpm; curve → the pulse ramps ×1.25 (speeds up) or ×0.85 (slows down) across the
play; the parts → a stinger under the hook, the pulse only while the play runs, a half-level pulse through the replay
and the result, a soft pad under the end card, the file exactly `duration_s` long; each block exit → a pluck one scale
step higher at `exit_s`; the ending → a resolve chord (win), a 3 s riser plus hurry ticks (near-fail), an unresolved
sus4 chord held (cliffhanger), a low drop (time-out); the clock → a tick at every second it shows 5 or less.
Everything is additive synthesis in numpy, 48 kHz mono, peak 0.85 before the voice. No licensed music is used.

**The voice.** NVIDIA Magpie TTS over NVCF gRPC (`nvidia-riva-client`, the `voice` extra; function
`877104f7-e885-42b9-8de8-f6e4c6303969`; `NVIDIA_API_KEY`; one channel per process). By default it **narrates the
creative's own captions as they appear** (`narration="captions"`: the hook, the play captions, the end card's fact and
call to action, never the game's title; at most 5 lines), each line 0.15 s after its caption appears and never
overlapping the previous one (a line with no room is dropped); `00:03` is spoken as "3 seconds", shouting capitals are
lowered. `narration="hook"` speaks the hook alone; a typed line (≤14 words) replaces the hook's words only. So what is
said is always what the creative shows, when it shows it. English only here (the voices on build are `EN-US.Mia/Jason/Aria/Leo/Sofia/Ray` with
`.Calm/.Neutral/...` variants; there is no Turkish voice). The default voice follows the tempo (calm → Mia.Calm, normal
→ Mia, fast → Jason.Happy). Each line peaks at 0.95 and the bed is ducked to 40 % under it with 120 ms ramps. Skipped, with the reason returned, when the version has no hook caption, when the
creative's captions are not English and no line was typed, when the extra is missing or the key unset.

**At creation time.** `POST /api/make {..., audio: {bed, voice, voice_name?, line?, narration?}}` runs the workflow
unchanged and then `soundtrack.add_audio()`: the soundtrack for the version just made, then the existing music edit, so
the job's result is the version WITH audio (`audio_added: {file, description, voice, voice_skipped, bed, from_version}`).
`bed=False` with the voice keeps the creative's own music (if the prompt attached one) or leaves silence under the
lines. CLI: `cbj make "..." --audio bed,voice`. The viewer's review belongs to `from_version` (the audio edit keeps
every frame).

**The file.** `studio/uploads/soundtrack-<slug>-v<N>[-nobed][-voice].wav` plus `studio/_soundtracks/<same>.json` (the concept,
the voice, the description). It passes the brief's music check (`brief.is_audio`) and appears in `studio.uploads()`.
The compositor mixes a music file at `MUSIC_GAIN` 0.35 (about −9 dB) under the effects with a fade-out; measured on the
test creative: the bed alone −22 LUFS, the composed ad with bed and voice −22.6 LUFS, the voice clearly audible in the
first second.

**NVIDIA build and audio (checked 2026-10-18 with the key).** The NVCF catalogue has text-to-speech
(`ai-magpie-tts-multilingual`, `ai-magpie-tts-zeroshot`, `ai-chatterbox-multilingual-tts`), speech enhancement
(`ai-studiovoice`) and voice chat; no music or sound-effect generation model. Fugatto was never released. Hence the
synthesised bed.

## 4. Procedure
1. `uv run cbj soundtrack <creative_id> [--base N]` for the bed; add `--voice` (and `--line "..."`, `--voice-name ...`)
   for the spoken hook. The output names the file and the sentence describing it.
2. Listen, or measure: `ffmpeg -i studio/uploads/<file> -af ebur128 -f null -` (expect about −22 LUFS, peak ≤ −0.2 dBFS).
3. Put it in the ad with the music edit (`{"music": "<file>"}` on `/api/direct`, or the site's *Use as the music*):
   a new version with the edit report; the gameplay, timing and captions stay on the same frames.
4. Judging a soundtrack: compare `describe()` with the parts manifest (the exits' seconds, the ending, the clock) and
   check that every event in the bed has a fact behind it.

## 5. Not possible here
- No generated music from a text prompt: there is no such model on NVIDIA build; the bed is synthesised from facts.
- No Turkish (or other non-English) voice; no SSML (Magpie rejects it; "..." makes a pause).
- The voice shares the one music channel, so it sits at the music level the compositor applies; it is not a separate,
  louder voice-over track.
- Nothing automatic: no version changes until the music edit is applied.

## 6. Evidence
- `studio/_soundtracks/<name>.json`: the concept the bed was written from, the voice line and model, the time taken.
- The new version's edit report and `compose.json` (`audio.music.file`, `sha256`) after the music edit.
- `tests/test_soundtrack.py`: the concept per theme/tempo/curve/ending, the length and peak, the file in uploads, the
  voice gate and ducking (the TTS is faked).

## 7. Change rules
- A new theme, tempo or ending must get a row in `THEME` / `BPM` / `render_bed()` and a test.
- Never import this module from a workflow, the planner or the compositor (`tests/test_feedback.py` checks the import lines).
- A change to the voice placement or ducking needs the measurement in §3 redone and the number updated here.
- Bump `last-verified` with every edit.
