# Addendum to SPEC.md (2026-10-19): feedback under every result, a designer's edit workspace, a downloadable report

Read `SPEC.md` first (architecture, design, flows), then `SPEC-FEEDBACK.md` (the feedback dialog and the owner's page:
they stay) and `SPEC-ENHANCE.md` (how additions are made). The engine is the source of truth: `../src/cbj/feedback.py`
(read its module docstring and the new `STEPS`, `process_of`, `step_evidence`, `analyze`, `get`), `../src/cbj/report.py`,
and the endpoints in `../src/cbj/app.py`. The relay (`app/api/engine/relay/[...path]/route.ts`) needs NO change: the new
POST is `/api/feedback/<id>/analyze` (second segment `feedback`, already an allowed write behind the passcode) and the new
GET `/api/report/<id>` is an ordinary read. Keep the honesty line of the feedback dialog wherever feedback is sent.

Why this exists. The owner asked for three things after testing the edit workflow:
1. Feedback **under the created or edited result**, not only behind a button: when a designer dislikes something *in the
   process*, they say it right there, and the note is tied to the step it is about (how the request was read, the level,
   the gameplay, the video, the viewer's review, the revision, the edit report) and, when they point at a row, to that
   exact item. The engine captures the process itself (stages, seconds, the route, the planner's groups, the control rows,
   the checks, the edit report, the review, the revision, its own log lines), so later the owner can ask "what happened and
   why" per note (`analyze`) and distil lessons that cite the step.
2. The Edit workspace **for a designer**: only what a designer needs; everything else goes.
3. Anyone who wants the intermediate steps **downloads a report** (Markdown or HTML) of a version.

## 1. Engine API (new or changed)

`GET /api/meta` → `features.feedback_steps` = `{plan, level, recording, compose, review, revise, proof, result, other}` →
plain words (copy into `lib/words.ts` as `STEP_WORDS`, 1:1; the keys are the engine's stage names, the same ones the
Progress strip uses); `features.report: true`. An older engine lacks both keys: hide the inline panel's step chips and the
report button (the old dialog still works).

`POST /api/feedback` (passcode) takes two more optional fields: `step` (one of the keys above) and `item` (≤200 chars,
the exact thing as the page names it: a control row's title, an edit-report row's title, a check's name, a caption's
name). The stored record now has `step`, `item` and `process` (the engine's capture; the UI never sends it). With a
creative and no `step`, the engine stores `step: "result"`.

`GET /api/feedback/<id>` (passcode) → the record plus `evidence: {step, words, item, facts, lines:[{stage, text}]}` (the
slice of the process the note points at) and `analysis` (null until asked).

`POST /api/feedback/<id>/analyze` (passcode, synchronous, 10-30 s, one model call) →
`{record, step, item, what_happened, why, verdict: "system"|"taste"|"unclear", evidence:[quoted lines], unbacked:[...],
suggested_change, confidence: "strong"|"thin", model, seconds, created}`. The engine keeps it; a second call replaces it.

`GET /api/report/<creative>?version=N&format=md|html[&download=1]` → the report as text (`text/markdown` or `text/html`);
with `download=1` the engine sets a `Content-Disposition: attachment; filename=<creative>-vN-report.<ext>`. Sections:
the request; how it was read (route, planner, the controls table, the assumptions); the steps with seconds and the
engine's own lines; the level and the play; the checks; the edit report; the viewer's review; the revision; the feedback
left on that version (with its analysis); the files. Use `engineText` (lib/engine.ts) + `saveText` for the download, so
it works through the relay too; name the file as the engine does.

## 2. The inline feedback panel: `components/FeedbackPanel.tsx`

One component, used in three places:
- **Create**, under the finished creative (phase "ready"), below the player and above the checks.
- **Edit**, under the player / before-after pair (replacing the line "Something off in v{n}, or just right?" and its
  Give feedback button).
- **Showcase detail**: the same panel, disabled with "Needs the engine" when the engine does not hold the creative (as the
  button is today).

Behaviour:
- Title: "Was this what you asked?" Two large choices first: **Yes, as asked** (kind `good`) and **Something is off**
  (kind `wrong`); a third quiet link "Something is missing" (kind `missing`) and "I have an idea" (kind `idea`).
- On any choice the panel opens below it (no modal): the **step chips** from `STEP_WORDS` in this order: result, plan,
  level, recording, compose, review, revise, proof (proof only when the version is an edit), other; the default is
  `result`. Under the chips, an optional **item** field pre-filled when the panel was opened from a row (see §3), editable,
  with the hint "the exact thing (a caption, a row, a check)". Then "What happened?" (required unless `good`), "What did
  you expect instead?" (optional, hidden for `good`), the name field (remembered as today), the 1-5 rating for `wrong` and
  `missing`, Send. Area: pick it automatically from the step (plan → understanding, level → level, recording → tempo,
  compose → captions, review → other, revise → edit, proof → edit, result → other, other → other) and show it as a small
  changeable chip row ("about: the captions or the hook · change") so the record keeps the area the owner's page filters on.
- After Send: "Thanks, saved as fb-… · it is tied to {step words}{, item}" with "Send another". Nothing else changes.
- The honesty line, once, under the title, smaller: "Read by the person who tunes the engine. Nothing changes automatically."
- Unlock first (`engine.ensureUnlocked()`), as the dialog does; offline or older engine: the panel shows its title and
  "Needs the engine" and nothing clickable.

## 3. Flag buttons on the rows ("about this row")

A small ghost icon button (lucide `Flag`, aria-label "Feedback about {title}") on:
- each row of **What the tool understood** (`Understood.tsx`) → opens the panel with `step: "plan"`, `item: <the control's title>`;
- each row of the **edit report** (`EditReport.tsx`, the nine rows) → `step: "proof"`, `item: <row title>`;
- each failed check in the checks list on Create (`Gameplay.tsx` or wherever the checks render) → `step` from the check's
  prefix ("Rules: the moves" → recording, "Asked: …" → result, "Video: …"/"Image: …"/"Reference: …" → plan), `item: <check name>`;
- the viewer's "not as asked" lines in `ReviewCard.tsx` → `step: "review"`, `item: <control>`.
Clicking scrolls to the panel (it is on the same page) and opens it with `kind: "wrong"`, the step and the item set; the
designer can change both. Implement with a tiny context (`FeedbackPanelProvider` with `open({step, item, kind})`) so rows
do not need props threaded through. Where the panel is not on the page (the owner's page), the flag buttons are not shown.

## 4. The Edit workspace, for a designer (`components/edit/EditWorkspace.tsx`)

Keep the three-column grid and the Stitch look. What a designer sees by default:
- **Left**: the change card (prompt, Enhance, attach, Apply) and **Things in this ad** (`Inventory`). Cut: the long
  "Preserved by default" list → one line under the textarea: "Everything you do not mention stays as it is; the report
  proves it." Cut: "Try an edit" → keep three chips and "more". Soundtrack: fold under "More: music" (collapsed).
- **Centre**: the player (This version / Before-after), the version timeline (ONE list: keep the horizontal timeline, drop
  the right-hand "Versions" card), the prompt line, the **FeedbackPanel**, the Progress card while a job runs, and the
  planned edit's "What the tool understood" only while the make runs or when it asked a question (the `needs` case).
  Cut from the default view: `VersionGameplay` (the level and moves).
- **Right**: ONE card "What changed" with the verdict line and the Locked / Allowed / Forbidden contract (`EditReport`
  without rows), the viewer's one-line verdict (`reviewLine`) with "Review as a viewer" when there is none, and two
  buttons: **Download report** (a split: "HTML" default, "Markdown") and **Details**. Cut from the default view: Compare,
  Metadata, Files, the checklist, the nine rows, the pixel facts.
- **Details** (a toggle, remembered in `localStorage` key `cbj.edit.details`): when on, the hidden things come back where
  they were: the full edit report (rows, checklist, pixels), Compare, the level and moves, Metadata, Files, the planned
  brief table. Default off. The header gets a small "Details" switch too, so the owner can leave it on.
- The breadcrumb, the Creatives button and Export video stay.
On Create, the finished creative's area gets the same **Download report** button next to "Edit this creative" (the
report of the version just made), and the FeedbackPanel; nothing else moves on Create.

## 5. The owner's page (`components/feedback/Records.tsx`)

Each record shows its step as a chip (`STEP_WORDS`) and its item in monospace when present. A record opens (click) to
show `evidence` from `GET /api/feedback/<id>`: the facts as a compact definition list (only the keys present) and the
engine's lines of that stage; a button **Analyze what happened** (POST, 10-30 s, a spinner; the button says "Analyze
again" when an analysis exists) → the analysis card: the verdict chip (system = amber, taste = grey, unclear = grey) with
its confidence, "What happened", "Why", the quoted evidence lines, "Smallest change", and the unbacked quotes under
"not in the evidence" when any. The Lessons tab needs no change (the engine's traces now carry the step and the analysis).
The Markdown download (`/api/feedback.md`) already includes the step, the item and the analysis.

## 6. Types, words, QA

- `lib/types.ts`: `FeedbackBody` + `step?`, `item?`; `FeedbackRecord` + `step`, `item`, `process?` (type it loosely:
  `Record<string, unknown>`); `FeedbackEvidence`, `FeedbackAnalysis`, `FeedbackDetail = FeedbackRecord & {evidence, analysis}`;
  `Meta.features.feedback_steps?: Record<string,string>`, `report?: boolean`.
- `lib/words.ts`: `STEP_WORDS` (1:1 with `feedback.STEP_WORDS`), `STEP_AREA` (the mapping in §2), `STEP_ORDER`.
- `scripts/qa-feedback-inline.mjs`, run from `qa.mjs` like the others: online: the panel on Create's finished creative and
  on Edit (open with "Something is off", the chips, a flag button on an edit-report row pre-fills step and item, ONE real
  POST with `--real-feedback` else intercepted), the Details toggle hides and shows the cards (and is remembered after a
  reload), the Download report button fetches `/api/report/...?format=html` (intercept and check the href/filename), the
  owner's page record opens with evidence and the Analyze button (intercept the POST with `scripts/fixtures/analysis.json`);
  offline: the panel says "Needs the engine", no flag buttons act; 1440 and 390 widths, no horizontal overflow, no console
  errors. Screenshots to `qa/` with the prefix `inline-`.
- `npm run lint` and `npm run build` clean. Update `README.md` (Pages table: Edit; the Feedback section) in a few lines.

## 7. Words (keep them)
"Was this what you asked?" · "Yes, as asked" · "Something is off" · "Something is missing" · "I have an idea" ·
"Which step is it about?" · "the exact thing (a caption, a row, a check)" · "Read by the person who tunes the engine.
Nothing changes automatically." · "What changed" · "Download report" · "Details" · "Analyze what happened" ·
"not in the evidence". No marketing words, no exclamation marks except the game's own captions.
