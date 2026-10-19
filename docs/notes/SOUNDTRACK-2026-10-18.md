# The optional soundtrack (2026-10-18)

Request: "audio generation according to the prompt, optional, the way my aiforgift reels do it; the audio follows the
game creative's concept". Built in `cbj-creative` with zero effect on the workflows.

## 1. What the reels do, and what NVIDIA build offers
- The aiforgift reels (`~/aiforgift-reels/narrate.py`, `petbath-foley.py`, `nightsky-foley.py`, `reel-studio/mix-*.sh`)
  use **NVIDIA Magpie TTS** (NVCF gRPC, `nvidia-riva-client`) for narration and **procedurally synthesised ambience
  beds** (pure-Python additive synthesis) because NVIDIA build has no audio-generation model; music beds came from
  outside (Suno) and were mixed with ffmpeg (sidechain ducking, LUFS targets).
- Checked again today with the key: the NVCF catalogue (231 functions) has `ai-magpie-tts-multilingual`,
  `ai-magpie-tts-zeroshot`, `ai-chatterbox-multilingual-tts`, `ai-studiovoice` (speech enhancement) and
  `ai-nemotron-voicechat`; the REST catalogue (81 models) has nothing audio. **No music or sound-effect generation.**
  Fugatto was never released; ETTA is a research listing. Magpie's English voices: Mia, Jason, Aria, Leo, Sofia, Ray with
  Calm/Neutral/Angry/Sad/Happy/Fearful variants; no Turkish voice.

So the same pair was adapted: a synthesised bed, now written from the creative's facts instead of a fixed timeline,
and Magpie for the spoken hook.

## 2. Design (`src/cbj/soundtrack.py`, `POST /api/soundtrack`, `cbj soundtrack`)
**Inputs, never guessed:** the version's brief (theme, tempo, curve, language) and its parts manifest `parts.json`
(duration, parts with their seconds, the hook layer, every block exit with its second, the clock readings, the ending
as played).

**The bed:**
| fact | what it does |
|---|---|
| theme | game/candy/pastel/custom → major pentatonic; neon/dark → minor; root and pad level per theme |
| tempo, curve | 84/104/124 bpm, ramping ×1.25 or ×0.85 across the play |
| parts | stinger under the hook; pulse only during the play; half-level pulse through replay/result; pad under the end card; exact length |
| block exits | a pluck one scale step higher at each exit's second |
| ending | win: resolve chord; near-fail: 3 s riser + hurry ticks; cliffhanger: unresolved sus4 held; time-out: low drop |
| clock ≤ 5 s | a tick per second |
Additive synthesis in numpy (the compositor already depends on numpy), 48 kHz mono WAV, peak 0.85.

**The voice (optional), 2026-10-19 form:** narration of the creative's own captions as they appear (hook, play
captions, end-card fact and call to action; at most 5 lines; `00:03` → "3 seconds"; never the game's title), each line
0.15 s after its caption and never overlapping the previous; `narration=hook` for the hook alone; a typed line replaces
the hook's words. English only; default voice by tempo (Mia.Calm / Mia / Jason.Happy); bed ducked to 40 % with 120 ms
ramps; peak 0.95. Skipped with a reason (no caption; non-English captions; missing extra or key) rather than failing.
His rule behind it: "audio text will be feasible with creative", so nothing is said that the creative does not show.

**At creation time (2026-10-19):** `/api/make` takes `audio {bed, voice, narration, voice_name, line}`; after the
workflow returns, `soundtrack.add_audio()` makes the soundtrack and applies it with the existing music edit, so one job
yields a creative with audio (v2; v1 stays the silent original, and its review is the review). `bed=false` keeps the
prompt's own music under the voice, or silence. Real run: the 60 s near-fail creative got 5 lines at 0, 3, 46, 51 and
53 s.

**Delivery:** `studio/uploads/soundtrack-<slug>-v<N>[-voice].wav` (an ordinary uploaded sound file) + a sidecar JSON
in `studio/_soundtracks/` with the concept. Using it is the **existing** music edit `{"music": name}` → a new version
with the edit report. `features.soundtrack: {bed, voice}` on `/api/meta`. The `voice` extra: `uv sync --extra voice`.

**Zero effect:** no workflow, planner or compositor imports the module (the import check in `tests/test_feedback.py`
now covers `soundtrack` too). Nothing changes until the music edit is applied.

## 3. Measurements (local engine, test creative `1018-110841-an-easy-color-block-jam`)
- Bed for v3 (win, 30 s, calm 84 bpm, 4 exits): 1.0 s to write; −22.3 LUFS, peak −1.4 dBFS.
- Bed for a 60 s near-fail creative (fast 124 bpm, 9 exits): 0.6 s; −21.9 LUFS.
- Bed + Magpie Mia.Calm "Can you beat it?" (0.84 s of speech): 0.9 s in all; −21.3 LUFS, peak −0.2 dBFS.
- Applied with the music edit → v4 in 1.3 s; the proof lists only `audio.music` as asked, gameplay and timing kept on
  the same frames; the composed ad is −22.6 LUFS integrated against v3's −16.1, which is loudness gating on a continuous bed, not a level drop: the win chord peaks at −2.3 dBFS in v4 against −4.2 in v3, the whole mix stays under the compositor's −1 dBFS limit, and the voice is audible in the first second (v3 had silence there).
- Spectrogram checked: voice block at 0.15–1.0 s, plucks at the four exits, the chord at the play's end, the pad after.

## 4. Limits, stated
- The bed is rule-based, not a composed track: it will sound like a game jingle, not a song. That is the honest ceiling
  without a music model.
- The voice shares the music channel and its −9 dB in the compositor; it is audible but not a foreground voice-over.
- English voice only. No prosody control beyond "..." pauses.
- The user's own ears are the last check; the measurements above are levels and placement, not taste.

## 5. Files
`src/cbj/soundtrack.py` (new), `src/cbj/app.py` (route, feature flag), `src/cbj/cli.py`, `pyproject.toml` (`voice`
extra), `tests/test_soundtrack.py` (6), `tests/test_feedback.py` (import check), `.claude/skills/cbj-soundtrack/SKILL.md`,
`README.md`, `web/SPEC-SOUNDTRACK.md` and the card built by Opus 5.5 (reviewed).
