# Designer feedback and the owner's lessons (2026-10-18)

Two additions to `cbj-creative`, both with zero effect on the agentic workflows: a feedback mechanism for the
designers who will use the site, and a distillation of that feedback into a versioned document for the owner,
after reading COLLEAGUE.SKILL (Zhou, Liu, Yuan, Shao, Hu; Shanghai AI Laboratory; arXiv:2605.31264, 29 May 2026).

## 1. The paper, and whether it fits the brief

**What it proposes.** Person-grounded *skill distillation*: take heterogeneous traces of a person or role (chat
logs, documents, reviews, incident notes), run two extraction tracks, and write a versioned package an agent can
load: a **capability track** (`work.md`: procedures, standards, decision heuristics) and a bounded **behaviour
track** (`persona.md`: communication style, interaction rules, a correction log). The package is *portable,
inspectable, composable, correctable, governable* (§2). Corrections arrive in natural language ("he would not say
that") and become either a Markdown patch to a section or a normalized correction record `{scene, wrong, correct}`
(§4.2); every correction increments the version, archives the previous one, and can be rolled back (Fig. 3). The
paper claims only the artifact format and lifecycle, not behavioural fidelity (§8, "Behavioral fidelity frontier").

**What fits here.** The brief tool will be used by many designers and its workflows are prompt-as-contract code the
owner tunes by hand. What the owner needs from the designers is exactly the paper's correction record: the scene
(which creative, which version, which prompt, which workflow), what was wrong, what was expected. And what the owner
needs from a pile of such records is the paper's dual track: *what the system should do differently* (capability)
kept apart from *how each person asks* (behaviour), because a complaint can be a system fault or one designer's
taste, and the two call for different changes. The lifecycle (versions, corrections in plain words, rollback, the
evidence ids visible) is cheap with files and gives the owner provenance for every workflow change.

**What does not fit, and was left out.** Simulating a designer (a persona skill), installing the package into an
agent host, galleries and distribution, the celebrity and relationship presets. Also any *automatic* use of the
distilled preferences: pre-filling a designer's habitual asks into a prompt would break the prompt-as-contract
design (the planner fills only what the prompt says) and the user's rule that the workflows stay untouched.

**Verdict.** Logical in a bounded form: the correction record *is* the feedback mechanism, and the distillation
makes the feedback actionable for the owner. Implemented with zero effect: no workflow, planner, enhancer or studio
module imports either new module (a test checks the import lines of every source file), and the document is never
placed in a prompt.

## 2. What was built

### 2.1 Feedback records (`src/cbj/feedback.py`)
- `POST /api/feedback {area, kind, wrong, expected?, rating?, designer?, creative_id?, version?, page}` → the record.
  Areas (13): level, ending, captions, tempo, look, sound, hud, hands, edit, understanding, speed, website, other.
  Kinds: wrong, missing, good, idea. Pages: create, edit, showcase, general.
- The **scene is captured by the engine** from the studio, never trusted from the browser: workflow, prompt, summary,
  length, created, the edit flag and the prompts of the earlier versions of that creative. Unknown creative or version
  → 400. The designer's name is what they typed (≤40 chars; "anonymous" when empty); there are no accounts.
- Storage: append-only `studio/_feedback/records.jsonl`. The open `/studio/*` file route refuses every folder starting
  with `_` (feedback, lessons, the trend cache), so this data is reachable only through the token- and passcode-gated API. `GET /api/feedback` lists newest first with filters and facets;
  `GET /api/feedback.md` exports Markdown. CLI `cbj feedback [--designer N --creative ID --area A --kind K --md]`.

### 2.2 Lessons (`src/cbj/lessons.py`)
- `distill()`: all records (newest 200) rendered as traces (id, designer, kind, area, scene, the prompt, the earlier
  prompts, what happened, expected) → one planner-model call with a strict JSON schema → **checks in code** →
  `studio/_lessons/v<N>/{lessons.json, LESSONS.md, meta.json}`, and `current.json` points at it.
- The package: `summary`; **Part A** per workflow (create, guided, image_guided, edit, website, general) with lessons
  `{lesson, evidence: [record ids], suggested_change, confidence}`; **Part B** per designer `{asks_for, phrasing,
  evidence}`; `open_questions`. `meta` has the version, time, record ids, the model, the seconds, the corrections
  applied and `dropped`.
- The checks (`_checked`): a lesson citing no existing record is dropped and listed; unknown ids are removed; a lesson
  is `thin` with one record, or with fewer than three records from fewer than two designers, whatever the model said;
  a designer entry is kept only with that designer's own records, under the stored spelling.
- `correct(text)`: the owner's sentence is appended to `corrections.jsonl` (with the version it was written against)
  and a new version is distilled with all corrections passed as outranking the records; they are listed in the
  document. `rollback(N)` moves the pointer; nothing is deleted. `GET /api/lessons[?version=N]`, `POST /api/lessons
  {action: distill | correct | rollback}`, CLI `cbj lessons [--distill | --correct TEXT | --rollback N | --version N]`.

### 2.3 The site (`web/`, spec `web/SPEC-FEEDBACK.md`)
- A **Give feedback** dialog from four places (the finished creative on Create, the edit workspace, a showcase page,
  the header), with the honesty line "What you write here is read by the person who tunes the engine. Nothing
  changes automatically.", the name remembered in the browser, kind and area chips, what happened / what you
  expected, an optional 1-5 rating. Needs the passcode like Generate.
- An owner's page **/feedback**: a Records tab (filters, the scene's prompt, links to the version, a Markdown
  download) and a Lessons tab (Distill now, the two tracks rendered from the structured fields, evidence chips that
  jump to the record, versions with rollback, "Correct a lesson in your words", the dropped lines as the honesty
  proof). The relay gates the GETs as well as the POSTs behind the passcode: designers' names and complaints are the
  owner's data.

## 3. First live run (local engine, planner = Claude CLI)
Four test records on one real creative (two designers; a long hurry caption reported twice, a Turkish tempo ask
that was not acted on, a website idea) → `POST /api/lessons {distill}` → **v1 in 16.5 s**:
- Part A: `create`: hurry caption short and brief near the end (**strong**, 2 records, 2 designers); a Turkish
  speed-up phrase should produce a last-third tempo rise (thin); `edit`: a revise round must re-check caption timing
  (thin); `website`: duplicate a creative with a different ending (thin).
- Part B: each designer's habitual asks and phrasing, with their own record ids only.
- Open questions: the model noticed that the Turkish phrase was *not* in the recorded prompt and asked where it was
  written, rather than inventing a prompt fact. `dropped: []`.
The test records and v1 were removed afterwards so the owner starts from an empty store.

## 4. Files
- Engine: `src/cbj/feedback.py`, `src/cbj/lessons.py` (new); `src/cbj/app.py` (routes, `features.feedback/lessons`);
  `src/cbj/cli.py` (`feedback`, `lessons`); `tests/test_feedback.py` (8 tests incl. the zero-effect import check).
- Skill: `.claude/skills/cbj-feedback-lessons/SKILL.md`; `README.md` section "Designer feedback and the owner's lessons".
- Web: `web/SPEC-FEEDBACK.md`; relay gating; the dialog, the page and the qa additions (built by Opus 5.5, reviewed).

## 5. Limits, stated
- The model may miss a lesson; the checks only remove unbacked ones. Thin evidence stays thin until more designers report.
- Names are self-declared; two people can use the same name and one person two names.
- The distillation is one model call over at most the newest 200 records; beyond that, older records are not read.
- Nothing is automatic by design: the owner reads, verifies against the evidence (`cbj-creative-evidence`), then
  changes code or a skill by hand.
