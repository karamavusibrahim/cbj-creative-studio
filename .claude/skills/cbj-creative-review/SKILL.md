---
name: cbj-creative-review
description: The viewer's review of a finished CBJ creative in cbj-creative (review.py, `cbj review`, the UI's "As a viewer" card, the "review after making" option) - a multimodal model looks at a contact sheet of the finished ad as a person scrolling a feed and judges, against the prompt and the plan, whether what is seen matches each of the eight controls, scores pace, readability, clarity and the call to action (the first second and dead time are measured in code and final), says whether it would download and why, and proposes up to three fixes plus one edit prompt that applies the best one. Use when judging a finished creative from the viewer's side, when deciding whether a result matches its prompt beyond the deterministic checks, when closing the loop (review, edit, review), and when writing or changing the review rubric.
metadata:
  spec-version: "1"
  last-verified: "2026-10-19"
---

# The viewer's review

## 1. Purpose
The deterministic checks prove the gameplay and the edit report proves an edit, but neither says whether the ad
reads well to a person who sees it once, sound off, thumb ready to scroll. This review is that person's verdict, in
a fixed form, so the loop can close: make, review, apply the suggested edit, review again. It never replaces the
checks (a model's eyes can be wrong about a frame); it adds the one thing they cannot measure.

## 2. Source of truth
- `src/cbj/review.py`: `RUBRIC` (the exact instructions the model gets; section 3 quotes it), `facts()` (what is
  measured), `measured_scores()`, `contact_sheet()`, `question()`, `review()`, `_complete()`, `summary()`.
- `src/cbj/app.py` `/api/review`, `MakeRequest.review`; `src/cbj/cli.py` `cbj review <creative> [n]`;
  `src/cbj/static/index.html` the "As a viewer" card. Tests: `tests/test_review.py`.
- The model: `llm.vision_client()` (NVIDIA Nemotron omni by default, the Claude Code CLI with `CBJ_PLANNER=claude`).

## 3. Facts
**What the model sees.** A contact sheet: one frame per second of the finished ad in a grid, the second written under
each frame (`review_sheet.png` next to the version). Plus the marketer's request, the tool's eight plan rows (asked,
status, plan), and the measured facts.

**What is measured in code and given as final** (never re-estimated by the model):
- the second the game first moves (frozen opening + the recording's lead-in): score 5 at 1.5 s or less, 4 to 2.5 s,
  3 to 3.5 s, 2 to 5 s, else 1;
- dead time: the share of the ad that is a held screen (frozen opening, held result, end card): 5 at 25 % or less,
  4 to 35 %, 3 to 45 %, 2 to 55 %, else 1;
- each caption's time on screen against its reading time (0.4 s + 0.3 s a word, at least 0.8 s), marked TOO SHORT
  when under;
- the game's own record of the drags (which colour moved, was stopped or left, and when in the ad), so a drag that falls between the sheet's frames is not reported as missing;
- the checks that did not pass and the QA notes (the asked-facts audit and the game's rules rows among them);
- for an edit: the edit report's verdict and, measured, which layer(s) the changed pixels sit in and their box, so a
  small change (a texture on a block, a colour) is judged present from the fact, not from the thumbnails (a 1 fps
  sheet missed a crate texture on a blue block, 2026-10-15).

**The rubric** (verbatim from `review.RUBRIC`, kept identical by a test):

> You are a person scrolling a social feed who likes casual puzzle games. You see this ad once, with the sound off.
> Judge it as that person, strictly, against what the marketer asked for.
>
> MATCH, one verdict per control the marketer mentioned ("match", "partial", "no"; "not asked" when the prompt says
> nothing about it): the level's type or structure; the gameplay behaviour (the ending, mistakes, the order of moves);
> difficulty or pacing; visual elements; the creative concept (hook and captions); the sequence of events (what comes
> after what); the assets used (pictures, music); what had to remain unchanged. For each, say what you SEE in the
> frames (name the seconds) against what was asked. A plan row says what the tool meant to do; judge the frames, not
> the plan.
>
> VIEWER SCORES 1-5 (5 = excellent). Measured scores are given to you and are final: the first second (does the game
> move at once?) and dead time (held screens). You score: pace (does the play keep moving at a rate a viewer follows,
> neither racing nor dragging?), readability (can each caption be read in the time it shows, over what is behind it?),
> clarity (is it obvious what the game is and what the player must do, from the first seconds?), cta (does the end
> card make the next step obvious, and is it on screen long enough but not too long?).
>
> WOULD YOU DOWNLOAD: "yes", "maybe" or "no", and why in one sentence from the viewer's seat.
>
> FIXES: up to three concrete, plain-words changes that would most improve the ad, in order of effect; each must be
> something an edit prompt can ask this tool for (a caption, a colour, the hook, the pace, the length of a part, a
> picture, the music, the ending, the level's difficulty or size). Then ONE edit prompt, in the marketer's voice, that
> applies the best fix and keeps everything else ("Keep everything, but ..."); empty if nothing is worth changing.
>
> Write plain words a marketer reads: no field names, no JSON keys, no hex codes.

**The answer** (`review.json`): `match` (control, verdict, seen), `viewer` (pace, readability, clarity, cta from the
model; first_second, dead_time measured), `would_download`, `why`, `fixes`, `suggested_edit`, `overall` ("fix" when any
control is "no" or any score is 2 or less, else "ship"), `low` (the scores at 2 or less), `model`, `seconds`, `sheet`,
`facts`.

**Common to every workflow (2026-10-19).** The translation once, the rules rows and the shared case rows on every version,
the best version kept, the stated values kept, the length guard, the viewer-only rule, the repeated-miss limit, the fixed
board's pace said at plan time, the kept log lines, the feedback step and the report: listed once in `cbj-creative-evidence`
section 3 ("Common to every workflow") and in `src/cbj/workflows/__init__.py`.

## 4. Procedure
1. Make the version; in the UI leave "review as a viewer after making" on, or run `cbj review <creative> [n]`, or
   press "Review this version" on the card.
2. Read `overall` and `would_download` first, then the controls marked "no" or "partial" (with the seconds the model
   names), then the low scores.
3. Check the model against the facts before acting: a "no" on a control the prompt never mentioned is the model's
   error, not the ad's; a readability complaint should match a TOO SHORT caption in the facts.
4. Apply the suggested edit with one click (it is an edit prompt, so the edit report proves what it changed), then
   review again. Stop when `overall` is "ship" or the remaining fixes are outside the tool (section 5).
5. In a test report, quote the review's verdicts next to the deterministic checks; never let the review alone decide
   a pass, and never let the checks alone decide attractiveness.

## 5. Not possible here
The model does not hear the sound (the sheet is silent) and sees one frame a second: a half-second caption or a quick
bump can fall between frames, so motion facts come from the measured side. It cannot judge the real game's feel in
the hand. A fix it proposes may be outside the tool (a new mechanic, a different game, voice-over): such a fix is
reported, not applied. Two runs of the review can differ in wording and by a point; the measured scores do not.

## 6. Evidence
- `studio/<id>/v<n>/review.json` and `review_sheet.png`; `cbj review` prints the verdicts and the suggested edit.
- `tests/test_review.py`: facts, the contact sheet, the question (facts and rubric present), the completed answer.

## 7. Change rules
A change to `RUBRIC`, the measured thresholds, the answer's keys or the overall rule changes section 3 in the same
edit (the rubric here is checked against the code by a test). Bump `last-verified`.
