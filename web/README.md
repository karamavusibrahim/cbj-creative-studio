# Color Block Jam Studio — web front end

The public face of the `cbj-creative` engine: create an ad from text, from a reference image or from a
reference video; edit a finished ad one change at a time and read the report that proves what changed; browse
finished creatives with their evidence. The web app does not run any workflow itself: the Python engine
(`src/cbj/app.py`, `uv run cbj ui`) does, on a Mac with Unity and ffmpeg. This app is a client of its HTTP API,
plus a static showcase that works when the engine is offline.

## Run locally

```bash
cd web
npm i
printf 'ENGINE_URL=http://127.0.0.1:8765\nENGINE_TOKEN=\n' > .env.local   # git-ignored
npm run dev                     # http://localhost:3000
```

Start the engine in another terminal from the repo root (`uv run cbj ui`). For the browser to call the engine
directly, start it with this site's origin allowed, e.g. `CBJ_CORS_ORIGINS=http://localhost:3000 uv run cbj ui`.
Without that the app still works: it sends engine calls through its own relay (see below).

Production check: `npm run build && npm start -- -p 3105`.

## Pages

| Route | What it does |
|---|---|
| `/` | Create: prompt, attachments, prompt helpers, *Generate creative* (plan, then make with review and revise on), *Plan only*, *Level only*; then the plan ("What the tool understood"), the reference card, live progress, the finished creative, level and moves, checks, the viewer's review. |
| `/edit` | Choose a creative (the engine's list, or the showcase's when offline). |
| `/edit?c=<id>&v=<n>` | The Edit workspace, for a designer: describe one change (three example chips, Enhance, attach), or make an exact change from "Things in this ad" (music folded under *More: music*); the player (this version / before-after), the version timeline, *Was this what you asked?*, and one **What changed** card (the verdict, Locked / Allowed / Forbidden, the viewer's verdict in a line, *Download report*, *Details*). **Details** (also a switch in the header; remembered in `localStorage` `cbj.edit.details`) brings back the full edit report (checklist, rows, pixel facts), the brief, the level and moves, Compare, the viewer's review, metadata and the files. |
| `/showcase`, `/showcase/<id>` | Finished creatives exported with their evidence. Static: works with the engine offline. With `NEXT_PUBLIC_CATALOGUE_URL` set, the catalogue's creatives follow the curated ten (see "The catalogue on Cloudflare R2"). |
| `/feedback?tab=records\|lessons` | The owner's page (passcode): the designers' feedback records with filters, and the distilled Lessons. Needs the engine. |
| (every page) | **Your engine and keys**: the header's key icon (and "Optional: use your own engine or your own Gemini key" in the Unlock dialog) opens a dialog with two modes: *My own engine* (the default: your own Claude account through your own Claude Code login, no API key; see "Use the site with your own engine" below), and *This studio's engine, with my Gemini key*: one field, your Gemini API key, which reads reference videos on your own quota. Optional: with nothing entered everything runs as before. See "Your Gemini key" below. |

## Enhance prompt and ideas from trends

**Enhance prompt** (Create's prompt card and the Edit workspace's change card). The engine
(`src/cbj/enhance.py`, `POST /api/enhance`, synchronous, 10-25 s, not a job) rewrites the request in the words
its planner reads reliably and adds nothing: translations, clarifications and replacements of things the game
cannot do are listed one per row (the user's words struck through, the engine's words after them, the reason),
and anything the engine would like to add comes back as questions whose options are sentences the user may tap
to append (a second tap removes exactly that sentence). On Create the merged prompt (text plus helper chips) is
sent and the chips are cleared after a rewrite, since their sentences are now in the text; *Undo* restores the
text and the chips. On Edit the call carries `creative_id` and the version shown, so the rewrite starts with
what to keep. The card ends with how the engine will read the request ("Will be read as: …"). It needs the
engine and an unlocked session; offline the button is disabled ("Needs the engine").

**Start from a trend (optional)** (Create, between the prompt and the attachments). On *Get ideas* the engine
(`src/cbj/trends.py`, `POST /api/trends`, 20-40 s the first time, then cached for 6 hours per theme) reads Google's
trending searches and news search and writes 4-6 Color Block Jam ad ideas, each with its trend, why it is current,
its source (a link, or the search term), how it maps to the game's levers, a hook, and a full prompt. *Use this
prompt* puts it in the textarea (asking first if there is text) and focuses it. The footer says when it was
generated, from how many signals, and lists the skipped trends with the reason (the brand-safety rules). The
card never fetches on its own, and it is hidden when the engine is offline or has no `TAVILY_API_KEY`
(`/api/meta` → `features.trends`). Under the theme field, *Read link* sends a pasted public link to the same
endpoint (`url`), and the engine turns that page alone into 1-3 ideas that appear above the feed's, each marked "From your link" with the
URL as its source; an engine refusal (private address, unreadable page, unsafe topic) is shown word for word under the field.

## Feedback and the owner's page

Under every result, **Was this what you asked?** (`components/FeedbackPanel.tsx`: under the player of a finished
creative on Create, of the version shown in the Edit workspace and of a showcase creative): *Yes, as asked* / *Something
is off* (and *Something is missing*, *I have an idea*) open the note in place, with **Which step is it about?** (the
engine's stages, `/api/meta` `features.feedback_steps`: the whole result, how the request was read, the level, the
gameplay, the video, the viewer's review, the revision, the edit report on an edit, something else), the exact thing
(a row, a check, a caption), and the area picked from the step (changeable). A small flag on a row (the controls of
*What the tool understood*, the edit report's rows, a failed check, the viewer's "not as asked" lines) opens it with
that step and item filled in. The engine stores the step, the item and its own capture of the process.
Notes about the site itself still use **Give feedback** (next to *Create another* on a finished creative, and the
speech-bubble button in the header). The dialog says plainly that a person reads it and nothing changes automatically; it
posts `POST /api/feedback` (passcode), the engine captures which creative, version, prompt and workflow it was about,
and the name is remembered in `localStorage` (`cbj.designer`). **Feedback** in the nav (`/feedback`, passcode) is for
the studio's owner: *Records* lists them newest first with designer / area / kind / creative filters in the query
string and a Markdown download; each record shows its step and item, and opens to the engine's evidence for that step
(the stored facts and the engine's own lines, `GET /api/feedback/<id>`) and **Analyze what happened** (`POST
/api/feedback/<id>/analyze`, one model call, 10-30 s: what happened, why, system / taste / unclear, the quoted evidence,
the smallest change, and any quote that is not in the evidence); *Lessons* shows the engine's distilled, versioned LESSONS document (per-workflow
lessons with their evidence records, how each designer asks, open questions, the owner's corrections, what the
checks dropped) with *Distill now*, a version picker with rollback, *Correct a lesson in your words* and a
LESSONS.md download. Both need the engine; an engine without `features.feedback` hides all of it (an engine without
`features.feedback_steps` keeps the panel without its step chips and flags).

**Download report** (next to *Edit this creative* on Create, and in the Edit workspace's *What changed* card): the
engine's report of the version (`GET /api/report/<id>?version=N&format=html|md`, `src/cbj/report.py`: the request, how
it was read, every step with its seconds and lines, the level and the play, the checks, the edit report, the review, the
revision, the feedback left on it, the files), HTML by default or Markdown, saved as `<id>-vN-report.<ext>`. Hidden
offline and on an engine without `features.report`.

## Soundtrack (optional)

A **Soundtrack (optional)** card sits under the finished creative's player on Create and below *Things in this ad* in the
Edit workspace. *Make the soundtrack* calls `POST /api/soundtrack` (passcode; synchronous, 1-6 s; `src/cbj/soundtrack.py`):
the engine writes a music bed from the version's own concept (look, tempo, block exits, ending, clock), optionally with
the creative's own captions narrated by NVIDIA Magpie as they appear (*Narrate the captions*: All captions / Hook only, a *Different first line*), as a WAV in `studio/uploads/`. The card plays it (`<audio>` from `<engine>/studio/uploads/…`),
shows the engine's description and what the bed follows, and *Use as the music* runs the existing music edit
(`/api/direct {op: {music: file}}`), so a new version with its edit report appears; nothing changes before that. A TTS failure
(502) is shown verbatim with *Make it without the voice*. Hidden offline, on showcase copies and on an engine without
`features.soundtrack`; *Narrate the captions* is disabled when `features.soundtrack.voice` is false.

On Create, an **Audio (optional)** row in the Generate card (a bed from the concept and/or the narrated captions, kept for
the session) sends `audio` on `/api/make`, so the job ends with an `audio` stage and returns the version with the audio
already applied as a music edit (`audio_added`). The ready page then shows a *With audio* chip, the description and the
spoken lines under the player, and the viewer's review of the version before the audio (`audio_added.from_version`).

## Your Gemini key (optional; the dialog's second mode, *This studio's engine, with my Gemini key*)

The planner runs on the studio's Claude account; to use your own Claude account, use your own engine (next section).
On the studio's engine you may add one thing of your own: a Gemini API key, so reference videos are read on your own
quota. The browser keeps it in `cbj.keys`: `sessionStorage` (this tab) by default, `localStorage` with *Remember on this
device* (and removed from the other store); *Clear* empties both. `lib/engine.ts` sends it only to the engine, as
`X-CBJ-Gemini-Key`, on every POST and on `GET /api/meta`, on the direct path and through the relay; reads of creatives,
studio files and jobs never carry it, and it is never logged or put in a URL. The engine holds it in memory for that job
only (`src/cbj/keys.py`). The header pill then reads *Your Gemini key*, and Create's line "Planner: … · your Gemini
key". The passcode is still needed. Offline, or on an engine without `features.own_keys`, there is no pill and no header
is sent (an older engine would refuse it in the CORS preflight); the key icon still opens the dialog (its first mode,
*My own engine*, needs no studio engine), and this mode says the key would stay in the browser, unsent.

## Use the site with your own engine

The hosted site can run on **your own** engine instead of the studio's: your Mac, your Claude account (the Claude Code
CLI, logged in; no API key) and your Gemini key. The key icon opens **Your engine and keys**; *My own engine (my Claude
CLI, my Gemini key)* is the first, recommended mode:

1. On your Mac: `claude` once to log in, then in `cbj-creative/.env`: `CBJ_PLANNER=claude` and `GEMINI_API_KEY=...`;
   `uv run cbj setup-check --live` proves it.
2. Start it for this site: `CBJ_CORS_ORIGINS=https://cbj-creative-studio.vercel.app uv run cbj ui`
3. Paste the URL here and press Check.

*Check* asks the engine's `/api/health` and `/api/meta` from the browser (with the *Engine token*, the engine's
`CBJ_API_TOKEN`, as `Authorization: Bearer` if you set one) and says either "Reachable · planner: claude-cli/opus ·
voice: yes" or exactly what failed: not reachable (is `uv run cbj ui` running?), blocked by CORS (start it with
`CBJ_CORS_ORIGINS=<this site>`), a wrong token (401), or mixed content. *Save* is enabled only after a successful Check,
so a broken address is never saved; *Remember on this device* and *Clear* work as for the keys (`cbj.keys`, field
`engine`).

Once saved, the whole site uses it: every engine call (reads and writes, uploads, job polls, feedback, lessons, reports,
soundtrack, enhance, trends, meta and health) goes **directly** from the browser to your engine with your token; the
relay is not used, so uploads over 4.5 MB are fine. Media point at `<your engine>/studio/<path>`. No passcode is needed
(it protects the owner's engine only), the status pill says "Your engine online / busy / offline: check `uv run cbj ui`",
the header pill "Your engine: 127.0.0.1:8765 · claude-cli/opus", Create's line "Planner: claude-cli/opus · your
engine", and the owner's Feedback page reads your engine's records. The Showcase stays static. If your engine goes
offline the site behaves as offline and keeps the setting; *Clear*, or saving *This studio's engine, with my Gemini key*,
returns to the studio's engine and its passcode. No `X-CBJ-*` key headers are sent to your own engine.

**Browsers.** Chrome, Edge and Firefox let this https page call `http://127.0.0.1` / `http://localhost` (Chrome may ask
to allow local network access: allow it). Safari does not (mixed content): use another browser, or a tunnel URL
(`cloudflared tunnel --url http://127.0.0.1:8765` gives an `https://….trycloudflare.com` address; start the engine with
`CBJ_ALLOWED_HOSTS=*.trycloudflare.com` too), which works everywhere.

**What travels.** Nothing but your own calls to your own machine: this site's server sees none of them, the studio's
engine is not contacted, and the URL and token stay in your browser (this tab, or this device with *Remember*).

## How it talks to the engine

```
browser ──(same origin)──> Next.js: pages, /api/session, /api/engine/health, /api/engine/relay/*
browser ──(direct, CORS)──> engine: /api/* workflow calls and uploads, /studio/* and /api/sprite/* media
```

- `GET /api/engine/health` asks the engine's `/api/health` (falls back to `/api/meta` for an older engine), with a
  4 s timeout, and never throws: `{online, busy, backend, models, effort, url, cors}`. `cors` says whether the
  engine allows this site's origin. The header pill polls it every 10 s (3 s while a job runs).
- Workflow calls (`plan`, `make`, `preview`, `review`, `direct`, `enhance`, `trends`, `soundtrack`) and uploads go **directly** from the browser
  to the engine when CORS allows it and the session is unlocked. This is because Vercel caps function bodies at
  4.5 MB, and reference videos can be 80 MB.
- `/api/engine/relay/<path>` is a same-origin fallback. It adds `ENGINE_TOKEN` on the server and only passes
  `/api/*` and `/studio/*.json` through; POSTs need an unlocked session. It is used for reads while the session is
  locked, and for everything when the engine sends no CORS headers. (Uploads over 4.5 MB through the relay will
  fail on Vercel, so run the deployed engine with `CBJ_CORS_ORIGINS`.)
- Media is never relayed. `<video>` and `<img>` point at `${ENGINE_URL}/studio/<path>` (online) or
  `/showcase/<path>` (offline / showcase pages). The engine serves those paths without a token.
- Jobs are polled every 700 ms. The running job id is kept in `localStorage`, so a reload picks it up again.
  The engine makes one creative at a time; while another page's job runs, the action buttons are disabled.

## Environment variables

| Name | Where | Meaning |
|---|---|---|
| `ENGINE_URL` | server | The engine's base URL: `http://127.0.0.1:8765` in dev, the tunnel URL in production. |
| `ENGINE_TOKEN` | server | The engine's `CBJ_API_TOKEN`, if any. Given to the browser only after unlocking. |
| `STUDIO_PASSCODE` | server | Optional. When set, Generate / Apply / Review / uploads need the passcode once (an httpOnly cookie). Browsing never does. |
| `SESSION_SECRET` | server | Optional. HMAC key for the session cookie (otherwise the cookie is the passcode's sha256). |
| `NEXT_PUBLIC_CATALOGUE_URL` | browser (build time) | Optional. The R2 catalogue's public base URL; see "The catalogue on Cloudflare R2". |

Nothing else is sent to the client (the catalogue URL is public by design). The engine side of a deployment needs
`CBJ_ALLOWED_HOSTS=<tunnel host>`, `CBJ_CORS_ORIGINS=<site origin>` and `CBJ_API_TOKEN=<token>`.

## Refresh the showcase

From the repo root: `uv run python web/scripts/export_showcase.py`. This writes `public/showcase/index.json`,
`<id>/showcase.json` and the files at their studio-relative paths (720p videos). Rebuild afterwards: the detail
pages are generated from `index.json` at build time.

## The catalogue on Cloudflare R2

More finished creatives than the ten curated ones, visible with the Mac off and without a redeploy: a catalogue of about
100 creatives (the ten curated first, every kind of the case present) lives in a public Cloudflare R2 bucket, in exactly
the static showcase's layout (`index.json`, `<id>/showcase.json`, `<id>/v<n>/ad/ad.mp4` at 720p, posters, boards,
`brief.json`, `level.json`, `review.json` and its sheet, `inventory.json`, `uploads/…`, `sprites/…`).

- **Turn it on**: set `NEXT_PUBLIC_CATALOGUE_URL` to the bucket's public base URL (no trailing slash; one is dropped)
  in the Vercel project (or `.env.local`) and build. It is read at build time into the browser bundle; unset, the site
  is exactly as before. The bucket's CORS must allow GET from any origin.
- **Publish it**, from the repo root: `uv run python scripts/r2_publish.py export && uv run python scripts/r2_publish.py upload`
  (`select` prints the choice first; `upload` needs `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` in `.env`).
  Re-publishing changes what the site shows on the next page load: `index.json` and `showcase.json` are uploaded
  `no-cache` and fetched with `cache: "no-store"`.
- **What the site does** (`lib/catalogue.ts`): `/showcase` renders the curated ten at once, then fetches
  `<base>/index.json` once per session and appends the creatives that are not curated, in the catalogue's order, each
  card badged *catalogue*; a creative in both is always the static copy, so the ten stay first and unchanged. The line
  under the heading says "10 curated · N more in the catalogue" ("10 curated" alone when the catalogue is off,
  unreachable or adds nothing). The filters count both; *Edits* includes catalogue creatives with an edited version.
  An unreachable bucket logs one console warning and leaves the static showcase as it is.
- **A catalogue creative's page** (`/showcase/<id>` for any id that is not curated): rendered in the browser from
  `<base>/<id>/showcase.json` by the same component as the curated pages, with a short loading state and a plain "Not
  in the catalogue" on a 404. Its media and file links resolve to `<base>/<path>` (a third media source next to the
  engine's and the static showcase's), even with the engine online, because the engine may not hold that creative any
  more. *Open in the Edit workspace* appears only when the engine is online and holds the creative (one GET; the same
  rule now applies to the curated pages); the feedback panel's rule is unchanged.
- Posters and videos are plain `<img>` and `<video>` elements (no `next/image`), so no host list is needed;
  `next.config.ts` only normalises the URL.
- **Sample assets** (`components/SampleAssets.tsx`, `lib/catalogue.ts`): the files the tool was built and tested with
  (the trailers, reference pictures, objects, textures, logos, stickers, a music track) are published with the catalogue
  at `<base>/assets/index.json` (`{note, groups: [{title, items: [{file, path, about, bytes, kind: image|video|audio}]}]}`).
  When that index loads (asked once per page session; silent when it fails, and never asked without the catalogue URL), a
  **Sample assets** link with the hint "The files the tool was built and tested with; attach one and describe what to do
  with it." appears in Create's *Attachments (optional)* card and under the Edit workspace's *Attach the asset the edit
  uses* zone (disabled while attaching is, e.g. offline). It opens a sheet of the groups, each file a row with a thumbnail
  (the picture itself; a film or a note icon), its name, its *about*, its size and **Attach**. Attach downloads
  `<base>/<path>`, wraps it as a `File` with its name and type and hands it to the page's own upload, exactly as a dropped
  file (the same `POST /api/upload`, role badge or chip, and limits): the button says *Downloading…*, *Attaching…*, then
  *Attached*; a failed download shows an error line under the row and *Try again*. Several can be attached in a row.

## Deploy

```bash
cd web
vercel --prod     # set ENGINE_URL, ENGINE_TOKEN, STUDIO_PASSCODE, SESSION_SECRET in the Vercel project first
```

## QA scripts

- `node scripts/qa.mjs <label> [base] [--real-enhance] [--real-feedback] [--feedback-only] [--inline-only] [--real-soundtrack] [--soundtrack-only] [--no-feedback] [--keys-only] [--no-relay] [--sample-assets-only]`: Playwright at 1440×900 and 390×844 (fresh context each).
  Checks horizontal overflow, page errors and console errors, and saves full-page screenshots to `qa/`. Then the
  Enhance / trends checks: with label `offline`, Enhance is disabled and there is no trend card; otherwise the
  button states, the collapsed trend card, the Enhanced card (rewrite applied, chips cleared, options append and
  remove, Undo), the idea cards, *Use this prompt*, and the keyboard path (Tab reaches Enhance, Undo, every option
  and *Use this prompt*). Those responses come from `scripts/fixtures/` (real engine answers saved once) through
  Playwright routing, so the run spends no model call. `--real-enhance` adds one real `/api/enhance` call (~15 s).
- Feedback checks (`scripts/qa-feedback.mjs`, run by `qa.mjs`; `--feedback-only` skips the rest): online, the Give
  feedback entry points (header, Create; Edit and the showcase now carry the inline panel), the dialog (opened from Create) (defaults, focus kept inside, Escape, the remembered name, the thanks line),
  the Records tab from the live engine (newest first, filters, Download .md) and the Lessons tab from
  `scripts/fixtures/lessons.json` (a real `GET /api/lessons` answer, extended) by interception: every `POST
  /api/lessons` is answered in the browser, never by the engine. With `--feedback-only --real-feedback` it sends
  the one real qa record (`{page: "general", area: "website", kind: "idea", designer: "qa"}`); otherwise that POST is
  intercepted (a plain `--real-feedback` run gives its one real record to the inline checks below).
  Label `offline`: no enabled feedback button, `/feedback` says "Needs the engine". Label `locked` (the session is
  answered as locked): the owner card, and Give feedback opens the unlock dialog first.
- Soundtrack checks (`scripts/qa-soundtrack.mjs`, run by `qa.mjs`; `--soundtrack-only` runs just these): the card in Edit
  (creative `1018-110841-an-easy-color-block-jam` v3) and on a ready Create page, the 502 path, an engine with `voice: false`
  or without the feature (both by intercepting `/api/meta`), *Use as the music* (its `/api/direct` answered in the browser,
  body asserted), keyboard, screenshots. Answers come from `scripts/fixtures/soundtrack.json`; `--real-soundtrack` sends ONE
  real `POST /api/soundtrack` without voice. A voiced request never reaches the engine in qa (the first gets a 502 here,
  later ones `scripts/fixtures/soundtrack-voice.json`, hand-written with 3 spoken lines). Offline: no card.
- Audio-at-creation checks (`scripts/qa-audio.mjs`, run by `qa.mjs` after the soundtrack ones): the Audio section collapsed
  and open, the session memory, Generate and Plan only → Make it with `/api/plan`, `/api/make` and the job all answered in the
  browser from `scripts/fixtures/job-make-audio.json` (no real make), the ready state with audio, voice-less and draft cases.
  `--no-feedback` skips the feedback checks (their Records list needs at least one record on the engine).
- Inline feedback checks (`scripts/qa-feedback-inline.mjs`, run by `qa.mjs`; `--inline-only` runs just these): the panel
  on a ready Create page (the make answered in the browser) and in the Edit workspace (`1019-113515-…` v4, `1019-125939-…`
  v3), the flags of a failed check, a control row, a review line and an edit-report row filling the step and item, the
  designer's default Edit view and Details (hides, shows, remembered after a reload), *Download report* (its
  `/api/report/…` answered in the browser; format, version and file name asserted), and the owner's record with its
  evidence and *Analyze* (answered from `scripts/fixtures/analysis.json`). With `--real-feedback` the ONE real
  `POST /api/feedback` is this script's (designer `qa-inline`); every other one is answered in the browser. Offline: the
  panel says "Needs the engine" and there are no flags. Screenshots `qa/inline-*`. The scripts read the engine for
  their fixtures from `ENGINE_URL` / `ENGINE_TOKEN` (environment, else `.env.local`; `scripts/qa-engine.mjs`).
- Your-Gemini-key checks (`scripts/qa-keys.mjs`, run by `qa.mjs online`; `--keys-only` runs just these): the dialog's
  second mode from the header and from the Unlock dialog (a locked session answered in the browser, so meta goes through
  the relay): one field, no Anthropic key, planner or model id; Save to this tab (`sessionStorage` only), *Remember*
  (`localStorage` only) and back, `X-CBJ-Gemini-Key` alone on `POST /api/plan` and `GET /api/meta` (no other key
  header, even from a record an older version stored) and none on `GET /api/creatives`
  or the job polls, the pill ("Your Gemini key") and Create's planner line, a reload, *Clear*, an older engine (no header
  sent), offline (the icon opens *My own engine*) and the help sheet's "Your own account". Only a fake key
  (`test-gemini-key`); `/api/meta` is answered like the engine, `/api/plan` and its job in the browser, every other
  workflow POST aborted. Then the relay itself: a second `next start` on :3106 against a recording stand-in engine on
  :8799 (its forwarded-header list is unchanged: POST and `api/meta` forward them, reads do not, the allow list and the
  passcode check stay); `--no-relay` skips that. Screenshots `qa/keys-*`.
- Own-engine checks (`scripts/qa-own-engine.mjs`, run by `qa.mjs online`; `--own-engine-only` runs just these): *My own
  engine* against a fake engine at `http://127.0.0.1:8765` answered by routing (the two modes, Check and its failures,
  Save after a good Check, the pills, every call on the own URL with its token and none through the relay, no passcode,
  media on the own host, offline mid-session, Clear). Screenshots `qa/own-engine-*`.
- Catalogue checks (`scripts/qa-catalogue.mjs`, run by `qa.mjs online|offline`; `--catalogue-only` runs just these).
  Build for them with `NEXT_PUBLIC_CATALOGUE_URL=https://catalogue.test npm run build`; `https://catalogue.test/*` is
  answered by routing from `scripts/fixtures/catalogue/` (an `index.json` of 3 creatives, one of them curated, and one
  `showcase.json`; their media are the bytes under `public/showcase/`), and every other qa context serves the same
  fixture bucket. Checks: the ten first and unchanged, the appended cards with the badge, the heading's count, the
  filters, a catalogue page with every medium and file link on the bucket, the 404 state, an unreachable bucket (the
  static showcase intact, one warning). The browser's own "Failed to load resource" lines for the catalogue URLs the
  test makes fail on purpose are not counted as console errors; nothing else is excused. On a build without the
  catalogue only the "off" checks run. Screenshots `qa/catalogue-*`.
- Sample-asset checks (`scripts/qa-sample-assets.mjs`, run by `qa.mjs online|offline`; `--sample-assets-only` runs just
  these). Same catalogue build; `https://catalogue.test/assets/index.json` is `scripts/fixtures/catalogue/assets/index.json`
  (3 items in 2 groups: a PNG, a one-second MP4, a WAV tone; their bytes sit next to it). Every `POST /api/upload` is
  answered in the browser (the multipart file's name, type and size asserted) and every other workflow POST aborted.
  Checks at both widths: the link and hint on Create and Edit, the sheet (groups, rows, thumbnails, sizes), the
  downloading state, three attached (two in a row) with their role badges on Create and as chips on Edit, a failed
  download's error line, no link when the index answers 404, the link disabled offline (also simulated in an online run),
  no overflow and no console errors. On a build without the catalogue only the "off" checks run. Screenshots
  `qa/sample-assets-*`.
- `node scripts/keyboard.mjs [base]`: the tab order of the Create page and the unlock dialog's focus trap. It
  aborts every workflow POST in the browser and skips the dialog step when no passcode is set.

Stack: Next.js 16 (App Router), React 19, Tailwind v4 (Stitch tokens in `app/globals.css`), `motion`,
`lucide-react`. The design source is in `design/`; the contract is `SPEC.md`.
