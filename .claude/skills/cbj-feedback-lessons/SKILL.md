---
name: cbj-feedback-lessons
description: How cbj-creative collects designers' feedback (src/cbj/feedback.py) and distils it into a versioned, correctable LESSONS document for the owner (src/cbj/lessons.py) - the record shape (scene captured by code), the two tracks of the lessons (what the workflows should do differently; how each designer asks), the evidence checks, versions, corrections and rollback, and the zero-effect rule (no workflow reads any of it). Use when reading or triaging feedback, when deciding what to change in a workflow from the lessons, when judging whether a lesson is backed by records, or when touching either module.
metadata:
  spec-version: "1"
  last-verified: "2026-10-19"
---

# Designer feedback and the owner's lessons

## 1. Purpose
Many designers use the studio; the owner tunes the agentic workflows by hand. Feedback is collected as structured
correction records (what happened, what was expected, about which creative and version, by whom) and distilled on
request into one inspectable, versioned, correctable document (LESSONS) the owner reads before changing code or a
skill. The design follows COLLEAGUE.SKILL (Zhou et al., 2026, arXiv:2605.31264): traces in, a dual-track package out,
correction records, versions with rollback. Nothing here changes a creative or a workflow: that is the contract.

## 2. Source of truth
- `src/cbj/feedback.py`: `AREAS`, `AREA_WORDS`, `KINDS`, `PAGES`, `scene_of()` (the scene read from the studio),
  `add()`, `listing()`, `markdown()`; storage `studio/_feedback/records.jsonl`.
- `src/cbj/lessons.py`: `SYSTEM`, `SCHEMA`, `traces()`, `_checked()` (the evidence rules), `render()`, `distill()`,
  `correct()`, `rollback()`, `load()`; storage `studio/_lessons/v<N>/{lessons.json, LESSONS.md, meta.json}`,
  `studio/_lessons/corrections.jsonl`, `studio/_lessons/current.json`.
- `src/cbj/app.py`: `POST/GET /api/feedback`, `GET /api/feedback.md`, `GET/POST /api/lessons`; `src/cbj/cli.py`:
  `cbj feedback`, `cbj lessons`. Tests: `tests/test_feedback.py`. The site: `web/SPEC-FEEDBACK.md`.
- Why, with the paper's reading and the live result: `~/rollic-case/FEEDBACK-AND-LESSONS-2026-10-18.md`.

## 3. Facts
**A record** is `{id "fb-<date>-<time>-<hex>", created, designer (≤40 chars, "anonymous" when empty), page (create |
edit | showcase | general), area (one of 13: level, ending, captions, tempo, look, sound, hud, hands, edit,
understanding, speed, website, other), kind (wrong | missing | good | idea), wrong (what happened, ≥3 chars unless
kind is good), expected, rating 1-5 or null, scene}`. The scene is captured by the engine from the version the designer
looked at (creative id, version, workflow, prompt, summary, length, created, edit flag, the prompts of the earlier
versions), never trusted from the browser; an unknown creative or version is a 400. Records are append-only.

**The lessons package** has two tracks. Part A (capability): per workflow (create, guided, image_guided, edit, website,
general), lessons `{lesson, evidence: [record ids], suggested_change, confidence: strong | thin}`. Part B (behaviour):
per designer, `asks_for` (habitual asks) and `phrasing` (words the tool may read badly), with evidence ids. Then
`open_questions` for the designers. `meta` holds version, time, counts, the record ids used, the model, the seconds,
the corrections applied and `dropped` (what the checks removed).

**The evidence rules, in code.** A lesson citing no existing record id is dropped and listed in `meta.dropped`; a cited
id that does not exist is removed from the list; a lesson is `thin` whatever the model said when it has one record, or
fewer than three records from fewer than two designers. A designer entry is kept only with records of that designer
(name matched case-insensitively) and is renamed to the stored spelling.

**Versions.** Every distillation writes the next `v<N>` and makes it current; `rollback(N)` only moves the pointer,
nothing is deleted. A correction is one sentence from the owner, appended to `corrections.jsonl` with the version it
was written against; the next distillation (run at once by `correct()`) passes all corrections to the model as
outranking the records and lists them in the document.

**Zero effect.** No module of the pipeline (workflows, planner, enhancer, trends, studio, review, audit) imports
`feedback` or `lessons`; `tests/test_feedback.py::test_nothing_in_the_pipeline_imports_feedback_or_lessons` checks the
import lines of every source file. The package is never placed in a prompt. On the site, the feedback dialog says so.

**Access.** Writing a record and reading records or lessons need the passcode on the site (the relay gates `feedback`,
`feedback.md` and `lessons` for GET as well as POST); the engine's bearer token applies as to every `/api/*` route, and the
open `/studio/*` file route refuses every `_` folder, so the stores are never served as files.

## 4. Procedure
1. **Triage feedback**: `cbj feedback [--designer N] [--creative ID] [--area A] [--kind K]`, or `--md` for a file. Read
   the scene's prompt before the complaint: the prompt is the contract the creative was measured against.
2. **Distil**: `cbj lessons --distill` (one planner-model call, 15-60 s). Read Part A per workflow; take only `strong`
   lessons as system faults, treat `thin` ones as leads; check Part B to see whether a complaint is one designer's taste.
3. **Verify a lesson** before acting: open each evidence id's record and its creative version
   (`studio/<id>/v<N>/version.json`, the proof and the review) and confirm the complaint against the evidence
   (`cbj-creative-evidence`). A lesson the evidence does not support gets a correction, not a code change.
4. **Correct**: `cbj lessons --correct "…"` in plain words; a new version is distilled; `--rollback N` returns to an
   earlier one; `--version N` prints any version.
5. **Act by hand**: change the workflow, the planner vocabulary or the skill the lesson points at, with the record ids in
   the commit message; then re-run the relevant tests and the affected skill's change rules.

## 5. Not possible here
- No automatic effect: lessons never alter a brief, a plan, an enhancement or a creative; a designer's "asks_for" is
  never pre-filled into anyone's prompt.
- No persona: Part B describes asks and words, not a person; nothing is installed as an agent skill or shared.
- No identity: the designer's name is what they typed; there is no account, so names are not verified.
- The model may miss a lesson; the checks only remove unbacked ones, they do not add missing ones.

## 6. Evidence
- `studio/_feedback/records.jsonl`: every record with its captured scene and time.
- `studio/_lessons/v<N>/meta.json`: the record ids a version was distilled from, the model, the seconds, `dropped`;
  `LESSONS.md` is the readable form; `corrections.jsonl` the owner's words with the version they corrected.
- `tests/test_feedback.py`: validation, the scene, the listing, the evidence checks, versions, correction, rollback,
  the zero-effect import check.

## 7. Change rules
- A new area or kind: add it to `AREAS`/`KINDS` and `AREA_WORDS`, to `web/lib/words.ts`, to this file and the spec.
- Any change to `SCHEMA` or `_checked()` needs a test in `tests/test_feedback.py` and a note in `render()` when the
  document's sections change.
- Never make a pipeline module import `feedback` or `lessons`; the zero-effect test must stay.
- Bump `last-verified` with every edit.


## Added 2026-10-19: the step, the process, the analysis, the report
- A record has `step` (`feedback.STEPS` = the engine's stage names + result/other) and `item`; the engine captures `process`
  (`feedback.process_of`: stages, planner/route, non-default control rows, failed checks, proof rows + pixels, review, revision,
  the kept log lines from `studio/<id>/v<n>/log.json` and `brief.planner.lines`). `step_evidence` is the slice a note points at.
- `feedback.analyze(id)` (owner-triggered; `POST /api/feedback/<id>/analyze`, `cbj analyze-feedback`): one model call over the
  note and its evidence → what happened, why, verdict system/taste/unclear, quoted lines (only lines the evidence holds count;
  the rest are listed as unbacked), the smallest change, confidence (thin when nothing is backed). Stored in
  `studio/_feedback/analyses/<id>.json`; `lessons.traces` carry the step, the version's own misses and the analysis.
- `report.py` (`GET /api/report/<id>?version=N&format=md|html`, `cbj report`): the version's full story for anyone who wants
  the intermediate steps; the web's Edit workspace hides them by default (SPEC-FEEDBACK-INLINE.md).
- Judging: an analysis that calls a note "system" must quote a line or a fact of that step; "taste" must point at the control
  row that shows the request was met as written. Never let an analysis change a creative: it is a reading for the owner.
