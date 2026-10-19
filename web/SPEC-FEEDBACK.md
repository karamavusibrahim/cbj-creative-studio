# Addendum to SPEC.md (2026-10-18, evening): designer feedback and the owner's Lessons page

Read `SPEC.md` first (architecture, design, flows) and `SPEC-ENHANCE.md` (how the last two features were added);
nothing there changes. The engine is the source of truth: `../src/cbj/feedback.py` and `../src/cbj/lessons.py`
(read both module docstrings), the endpoints in `../src/cbj/app.py`. The relay (`app/api/engine/relay/[...path]/route.ts`)
is ALREADY updated: `feedback` and `lessons` are allowed POSTs behind the passcode, and the GETs `feedback`,
`feedback.md`, `lessons` need the passcode too (they show what designers wrote). Do not change the relay.

Why this exists. Many designers will use the site; the owner adjusts the agentic workflows by hand from what they
report. So the site collects structured feedback records (what happened, what was expected, about which creative and
version, by whom) and, for the owner, a distilled, versioned, correctable "Lessons" document made from the records.
Nothing here changes any creative or any workflow: the records are read by a person. Say so in the UI, once, where
the designer sends feedback.

## 1. Engine API

`GET /api/meta` → `features: {enhance, trends, feedback: true, lessons: true}` (an older engine has no `feedback` key: hide everything below).

`POST /api/feedback` (passcode) body:
```
{ area: "level"|"ending"|"captions"|"tempo"|"look"|"sound"|"hud"|"hands"|"edit"|"understanding"|"speed"|"website"|"other",
  kind: "wrong"|"missing"|"good"|"idea",
  wrong: string,            // what happened; required (≥3 chars) unless kind = "good"
  expected?: string,        // what they expected instead
  rating?: 1..5,            // "how close to what you asked?" (optional)
  designer?: string,        // ≤40 chars; empty → "anonymous"
  creative_id?: string, version?: number,   // the creative and version they were looking at (engine creatives only)
  page: "create"|"edit"|"showcase"|"general" }
```
→ 200 the stored record `{id: "fb-…", created, designer, page, area, kind, wrong, expected, rating, scene}` where `scene`
is captured BY THE ENGINE from the studio: `{creative_id, version, workflow, prompt, summary, length_s, created, edit,
history:[{n, prompt, workflow}]}` (empty `{}` without a creative). 400 `{detail}` on bad input (show it under the form).
Area words for the UI are in `feedback.AREA_WORDS` (copy them into `lib/words.ts`):
level "the level or the board", ending "the ending", captions "the captions or the hook", tempo "the tempo or the length",
look "the look, colours or background", sound "the sound or the music", hud "the HUD (timer, moves, labels)",
hands "the hand or the pointer", edit "an edit that changed too much or too little", understanding "how the prompt was understood",
speed "waiting time", website "the website itself", other "something else".

`GET /api/feedback?creative_id=&designer=&area=&kind=&limit=100` (passcode) →
`{count, total, records:[…newest first], designers:[…], areas:[…], kinds:[…], creatives:[…]}`.
`GET /api/feedback.md` (passcode) → the records as Markdown (text/markdown) for download.

`GET /api/lessons[?version=N]` (passcode) → the package, or `{empty: true, versions: [], current: null, corrections: []}`
before the first distillation. The package:
```
{ summary: string,
  workflows: [{workflow: "create"|"guided"|"image_guided"|"edit"|"website"|"general",
               lessons: [{lesson, evidence: [feedback ids], suggested_change, confidence: "strong"|"thin"}]}],
  designers: [{designer, asks_for: [string], phrasing: [string], evidence: [ids]}],
  open_questions: [string],
  meta: {version, generated, records, designers, record_ids, corrections, previous, model, seconds, dropped: [string], note},
  markdown: string,                 // LESSONS.md, the same content rendered by the engine
  versions: [{version, generated, records, designers, …meta}],   // all versions, oldest first
  current: number, corrections: [{id, created, text, version_before}] }
```
`POST /api/lessons` (passcode) `{action: "distill"}` (one model call, 20-60 s) | `{action: "correct", text}` (records the
owner's correction and distils a new version with it applied) | `{action: "rollback", version}` → the package. 400 `{detail}`
("no feedback records yet: nothing to distil", "write the correction in a sentence", "no lessons version N").

Workflow words: create "text to creative", guided "video-guided creative", image_guided "image-guided creative",
edit "controlled editing", website "the website", general "the whole tool".

## 2. Giving feedback (every designer)

A **Feedback** dialog (one component, `components/FeedbackDialog.tsx`), opened from four places, each passing its context:
1. Create page, phase `ready` (the finished version is shown): a secondary button **Give feedback** (MessageSquare icon)
   in the result header row near "Create another" → `{page: "create", creative_id, version}` of the version shown.
2. Edit workspace: the same button near the version shown (the versions strip / the player header) → `{page: "edit",
   creative_id, version}` of the version currently shown.
3. Showcase detail page: the same button under the player → `{page: "showcase", creative_id, version}`. The showcase ids
   are real studio ids, so the engine resolves them; when the engine is offline the button is disabled with the tooltip
   "Needs the engine".
4. Header: a small icon button (MessageSquare, aria-label "Feedback about the studio") right of the status pill →
   `{page: "general"}`, for website issues and ideas; same disabled rule offline.

The dialog (a modal like `UnlockDialog`, focus trapped, Esc closes, mobile = full-width sheet):
- Title "Tell the studio owner" and one line: "What you write here is read by the person who tunes the engine. Nothing
  changes automatically." (that is the honesty line; keep it.)
- Context line (read only) when a creative is given: "About: <the creative's title (from its prompt, as Recent does)> ·
  v<N> · <workflow word>". General: "About: the studio".
- **Your name** (text, remembered in `localStorage` key `cbj.designer`, pre-filled next time; placeholder "optional").
- **What kind of note?** segmented chips: Something's wrong (wrong) · Something's missing (missing) · This was good (good) ·
  An idea (idea). Default "wrong" when opened from a creative, "idea" from the header.
- **What is it about?** chips with the area words; default "other"; from the header default "website".
- **What happened?** textarea (required unless kind = good; label becomes "What did you like?" for good).
- **What did you expect instead?** textarea (optional; hidden for good).
- **How close to what you asked?** five star-like buttons 1-5 (optional; hidden for general and for good/idea).
- **Send** (primary) → needs the passcode (unlock dialog first, as Generate). Spinner "Sending…". On 200: the dialog body
  turns into "Thanks — saved as <id>." with a **Close** button and a small "Send another" link. On 400: the detail under the
  form, verbatim. Offline / engine error: the generic message the other dialogs use.
- Keyboard: Tab reaches everything; the chips are buttons with `aria-pressed`.
No auto-open, no nag; one button per place.

## 3. The owner's page: `/feedback`

Add **Feedback** to the header nav (4th item, after Showcase). The page is for the studio owner and needs the passcode:
when locked, show the page shell with one card "This page is for the studio's owner." and the Unlock button (the same
dialog); when the engine is offline, a card "Needs the engine" (the showcase has no feedback data). Two tabs
(segmented control, `?tab=records|lessons`, default records):

**Records** tab:
- A header line: "<total> records from <designers.length> designers" and a **Download .md** link (fetches `/api/feedback.md`
  through the normal engine client and saves it as `feedback-<date>.md`; the relay carries the passcode).
- Filters: designer (select from facets), area (select), kind (select), and a "this creative only" select of `creatives`
  (show each as the creative title from the Recent list when it is known, else the id). Filters go in the query string.
- The list, newest first: each record is a row/card with: designer · when · kind chip (wrong amber, missing amber,
  good mint, idea grey) · area word · the prompt of the scene (muted, one line, truncated) · "what happened" in ink ·
  "expected" in muted · rating as "3/5" when present · a link "Open v<N>" to `/edit?id=<creative_id>&v=<version>`
  (how the Edit page addresses a version today; check `app/edit/page.tsx` and use exactly its parameters) when a creative
  is given. Empty state: "No feedback yet. Designers send it from the Give feedback button next to a creative."
- Phone width: cards stack; the filters wrap.

**Lessons** tab:
- Header: "Lessons v<current> · distilled <generated> from <records> records by <designers> designers" and three controls:
  **Distill now** (primary; disabled with a tooltip "No feedback yet" when `total` is 0; while running, spinner + "Reading
  the records… writing lessons" (aria-live), 20-60 s), a version `<select>` of `versions` (choosing an old one shows it;
  a **Make this the current version** button appears when it is not the current one → `rollback`), and **Download
  LESSONS.md** (the `markdown` field, client-side download).
- Empty state (`empty: true`): one card "No lessons yet. Distill once there is feedback." with the Distill button.
- The package rendered from the structured fields (do NOT render the markdown string as HTML; use it only for the download):
  Summary paragraph · "Part A · What the workflows should do differently" with one card per workflow (workflow word as
  title) and each lesson as: the lesson in ink, a confidence chip (strong mint / thin grey), the suggested change in a
  "Suggested change:" line, and the evidence ids as small chips that, when clicked, switch to the Records tab filtered to
  show that record (simplest: `?tab=records&id=<fb-id>`; the records tab then shows the one record and a "Show all" link —
  add that one-record filter to the list client-side from the full listing) · "Part B · How each designer asks" with a
  card per designer (asks for by default; phrasing to watch; evidence chips) · "Open questions for the designers" list ·
  "Owner corrections applied" (the `corrections` list, when any) · "Dropped by the checks" (meta.dropped, in muted, when any:
  this is the honesty proof that the model did not get to invent lessons).
- **Correct a lesson in your words**: a textarea + button **Apply correction** under the package: posts `{action:
  "correct", text}`; while running, the same spinner line; on success the new version shows and the version select grows.
- Keyboard and aria like the rest of the site.

## 4. Showcase / offline
The showcase export does not include feedback. Offline: the Give feedback buttons are disabled with "Needs the engine";
the `/feedback` page shows the "Needs the engine" card.

## 5. Verification to add to `scripts/qa.mjs`
- Online (local engine on :8765, no passcode locally): the four Give feedback entry points exist; the dialog opens,
  traps focus, remembers the name; ONE real `POST /api/feedback` with `{page: "general", area: "website", kind: "idea",
  designer: "qa", wrong: "qa run: a test idea"}` (cheap: no model) and assert the thanks line with the id; the
  `/feedback` Records tab lists it (newest first) and the filters work; Download .md produces a non-empty file.
- Lessons tab: do NOT run a real distill in qa (it is a model call). Render it from a fixture object written from the
  shape above (`scripts/fixtures/lessons.json`: 1 summary, 2 workflows with 3 lessons, 2 designers, 2 open questions,
  1 correction, 1 dropped line) by intercepting `GET /api/lessons`; assert the parts, the evidence chip → Records tab
  switch, the version select, the rollback button on an old version (intercept the POST and assert the body), the
  correction textarea posting `{action: "correct"}` (intercepted). Also assert the empty state from `{empty: true}`.
- Offline: no enabled feedback buttons, `/feedback` shows "Needs the engine".
- Locked (set `STUDIO_PASSCODE` for one run, or intercept `/api/session` to say locked): `/feedback` shows the owner card,
  Give feedback opens the unlock dialog first.
- Screenshots at 1440 and 390 of the dialog and of both tabs.
