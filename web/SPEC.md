# CBJ Creative Studio — web app spec (Vercel front end for the cbj-creative engine)

Written 2026-10-18. This folder (`cbj-creative/web/`) is a Next.js app deployed to Vercel. It is the public,
user-friendly face of the tool in this repo: a Color Block Jam ad-creative generator with four agentic
workflows (create from text, create guided by a reference video, create guided by a reference image,
controlled edit of an existing creative). The workflows run in the Python engine (`src/cbj/app.py`, FastAPI,
started with `uv run cbj ui`) on a Mac that has Unity and ffmpeg. The web app does NOT reimplement any
workflow. It is a client of the engine's HTTP API, re-skinned to the Stitch design, plus an offline
showcase of real finished creatives.

Readers: an engineer (or a coding model) building this app with no other context. Everything needed is in
this file or in the files it names. Do not change anything outside `web/`.

## 1. What the site must do

1. **Create** (home, `/`): a prompt, optional attachments (images, a reference video, a music file), a few
   prompt helpers (length, format, difficulty, ending), then one button: *Generate creative*. The page shows,
   live: the plan ("What the tool understood": one row per prompt control, with status), the progress of the
   make (stages: level, play, recording in the game, compose, review, revise), and then the finished creative:
   the video, the brief, the level and the moves, the checks measured from the recording, the viewer's review,
   downloads. Then *Edit this creative* leads to the Edit workspace.
2. **Edit** (`/edit`, optionally `/edit?c=<creative id>&v=<n>`): pick a creative (left rail: recent creatives),
   see its versions, describe ONE change in words (or make an exact change from "Things in this ad": replace a
   picture, edit a caption, turn sound off, add music), apply, and read the edit report: the edit contract
   (kept / changed as asked / changed because of the asked change / changed without being asked = fail), the
   checklist (level, moves, timing, render reused, duration, camera, HUD, captions, pictures, audio), the pixel
   facts, and before/after players. Compare any two versions.
3. **Showcase** (`/showcase`, `/showcase/<id>`): a gallery of curated finished creatives with their full
   evidence (video, prompt, brief rows, checks, viewer review, edit proofs, reference images). This works with
   the engine OFFLINE: everything is static under `public/showcase/`.
4. **Engine status** in the header: Online / Offline / Busy (one job at a time: the game player is a single
   process). When offline, Create and Edit say so plainly and point to the Showcase; the Showcase also feeds
   "Recently created" so the pages never look empty.
5. **Passcode**: the site is public; running the engine costs the owner time and model credits. If the env var
   `STUDIO_PASSCODE` is set, Generate / Apply / Review / uploads require unlocking once (a small dialog; a
   cookie). Browsing (Showcase, reading finished creatives) never needs it.

## 2. Architecture (decided; do not change)

```
browser ──(same origin)──> Next.js on Vercel: pages, /api/session (passcode), /api/engine/health
browser ──(direct, CORS)──> engine via a Cloudflare tunnel: /api/*, /studio/*, uploads, videos
```

- The browser talks to the engine DIRECTLY for every workflow call, upload and media file. Reason: Vercel
  functions cap request bodies at 4.5 MB (reference videos are up to 80 MB), and video playback needs range
  requests. The engine adds CORS for the site's origin (engine side, already planned; not your job).
- The server side of the Next app does two small things:
  - `GET /api/engine/health` → fetches `${ENGINE_URL}/api/health` (no auth; 4 s timeout; fall back to
    `${ENGINE_URL}/api/meta` for an older engine) → `{online: boolean, busy, backend, models, effort}`.
    Never throws; offline = `{online:false}`. `cache: "no-store"`.
  - `POST /api/session {passcode}` → if it equals `STUDIO_PASSCODE`, set an httpOnly cookie (an HMAC of the
    passcode with `SESSION_SECRET`, or the passcode's sha256 when no secret is set) and return `{unlocked:true}`.
    `GET /api/session` → `{unlocked, engine: {url: ENGINE_URL, token: ENGINE_TOKEN}}` when unlocked, else
    `{unlocked:false}`. If `STUDIO_PASSCODE` is unset, everyone is unlocked. `DELETE /api/session` locks again.
- The client keeps `{engineUrl, token, online, busy, unlocked}` in one React context (`EngineProvider`), polls
  health every 10 s (and `/api/meta` on the engine every 3 s while a job runs, for `busy`).
- Every engine call from the browser sends `Authorization: Bearer <token>` when a token is known. Media URLs
  (`<video src>`, `<img src>`) carry no header: the engine serves `/studio/*` and `/api/sprite/*` openly.
- **One media resolver**: engine paths are studio-relative (`"<id>/v1/ad/ad.mp4"`, `"<id>/v1/board.png"`,
  `"recordings/<hash>/play.json"`, `"uploads/<file>"`). `mediaUrl(path)` = online ? `${engineUrl}/studio/${path}`
  : `/showcase/${path}`. Sprites: `spriteUrl(name)` = online ? `${engineUrl}/api/sprite/${name}` :
  `/showcase/sprites/${name}`. The showcase exporter keeps the same relative layout on purpose.
- Env vars (Vercel + `.env.local` for dev): `ENGINE_URL` (e.g. `https://xxxx.trycloudflare.com`, or
  `http://127.0.0.1:8765` in dev), `ENGINE_TOKEN` (may be empty in dev: the local engine has no token),
  `STUDIO_PASSCODE` (optional), `SESSION_SECRET` (optional). Also expose nothing else to the client.

## 3. The engine API (source of truth: `../src/cbj/app.py`; read it)

All JSON unless noted. Long operations are **jobs**: the POST returns `{job: "<id>"}` at once; poll
`GET /api/jobs/<id>?since=<n>` every 700 ms → `{id, kind, status: queued|running|done|failed, stage, lines:[{t, stage, text}],
n_lines, result, error, trace?, elapsed}`. Show `lines` as a live log (the existing page prints
`${t.toFixed(1)} s [stage] text`). `GET /api/jobs` lists recent jobs (resume after reload: the existing page
keeps the running job id in localStorage and picks it up).

| call | body / params | result |
|---|---|---|
| `GET /api/health` (new engine) | | `{ok, busy, backend, models, effort}`; older engine: use `GET /api/meta` |
| `GET /api/meta` | | `{controls:{control:title}, uploads:[names], videos:[names], sprites:[names], backend, models, effort, busy, groups:{field:control}, group_names:{field:words}}` |
| `POST /api/plan` | `{prompt, creative_id?, base?, uploads:[names]}` | job → the **brief** (see §4) |
| `POST /api/make` | `{prompt, brief, creative_id?, base?, draft, review, without_files, revise}` | job → the **version** (see §4) |
| `POST /api/preview` | `{prompt, brief, creative_id?, base?}` | job → `{controls, board, level_why, beats, notes, frames, checks}` (level + planned moves, ~30 s, no recording) |
| `POST /api/review` | `{creative_id, n}` | job → the **review** |
| `POST /api/direct` | `{creative_id, base?, op, draft}`; op = `{picture: slot, file: name|null[, block]}` \| `{caption: layer, text}` \| `{sound: bool}` \| `{music: name|null}` | job → version |
| `GET /api/inventory/<cid>?base=<n>` | | `[{id, kind: picture|caption|sound|music, name, file, shows, text?, when:[a,b]|null, box, can_remove, empty}]` |
| `GET /api/parts/<cid>?base=<n>` | | the parts manifest (link only) |
| `GET /api/compare/<cid>?a=<n>&b=<n>` | | an **edit report** between any two versions |
| `GET /api/creatives` | | `[{id, prompt, versions, last, summary}]` newest first (hundreds; show a page) |
| `GET /api/creatives/<cid>` | | `[version, ...]` oldest first |
| `POST /api/upload` | multipart `files` (PNG/JPG/WebP ≤ 15 MB; MP4/MOV/WebM ≤ 80 MB and ≤ the reference limit; WAV/MP3/M4A/AAC/OGG/FLAC) | `{uploaded:[names]}`; 400 with `{detail}` on refusal |
| `GET /studio/<path>` | | a file (video, poster, board, json) |
| `GET /api/sprite/<name>` | | a game sprite PNG |

Errors: non-2xx with `{detail: "..."}`; show the detail verbatim (the engine writes plain-English messages).
A failed job has `error` (and `trace`): show `error`, keep `trace` under a fold.

Workflow routing is the engine's business (`workflow_of` in app.py): a `creative_id` means an edit; an
attached video means guided; a picture with reference words ("inspired by this image", "like this picture")
means image-guided; otherwise create. The web app just passes `prompt`, `uploads` (file names returned by
upload) and, on the Edit side, `creative_id` + `base`.

Live shape examples (read them, they are real): `../studio/1015-074810-create-a-hard-color-block/v13/version.json`
(an edited version with `proof`), `../studio/1015-074810-create-a-hard-color-block/v1/version.json`,
`../studio/1015-074810-create-a-hard-color-block/v13/review.json`, `../studio/recordings/0a1cb62e06cb5cc4/play.json`.
After the exporter has run, `public/showcase/index.json` and `public/showcase/<id>/showcase.json` hold the same
objects. You may also GET the live engine at `http://127.0.0.1:8765` (meta, creatives, inventory, compare) while
building. **Do not POST plan/make/direct/review/upload to it**: each make takes minutes and spends model
credits; the owner tests those.

## 4. Data shapes the UI renders (port the semantics of `../src/cbj/static/index.html` 1:1)

The existing single-page UI is the functional source of truth: its functions `renderBrief`, `renderReference`,
`renderGameplay`, `renderVersion`, `renderProof`, `renderReview`, `loadThings`/`thingAction`, `renderPair`,
`compareVersions`, `plan`/`make`/`poll`/`resumeJob`/`watchServer` define exactly which fields are shown and
with which words. Read the whole file first. Re-skin, do not re-invent; keep its plain-English labels (the
owner removed jargon on purpose: no raw field names like `cap_mistake`, no hashes in the main view, raw JSON
only under a fold).

- **Brief** `b`: `summary`, `controls:[{control, asked, plan, status: applied|default|adjusted|not_supported, why, engine:[notes]}]`,
  `assumptions:[str]`, `needs:[str]` (files the request names but that are not attached: a question, not an ad),
  `planner:{model, seconds, workflow, route, references:[...], restored:[fields], direct?}`, `gameplay.ending`
  (`win|near_fail|time_out|cliffhanger`), `gameplay.clock_left_s`, `gameplay.events`, `pacing.{length_s,tempo,curve}`,
  `level.{source,shape,difficulty,pieces,style}`, `visuals.theme`, `sequence.{style,replay}`, `channel`, `language`,
  `changed:[fields]`, `keep`, `reference` (image provenance). The eight control titles come from `/api/meta.controls`
  (offline: hardcode the same eight: level, gameplay, difficulty_pacing, visuals, concept, sequence, assets, unchanged).
- **Version** `v`: `id, n, from, edit, prompt, length_s, seconds, created, video, poster, board, ad_dir, level:{file, why, sha},
  recording:{dir, reused}, brief, checks:[{check, status: pass|fail|info|adjusted, detail, from}], qa:{failures, warnings},
  stages:[{stage, seconds}], proof?, review?, revision?, workflow?`.
- **Edit report / proof** `pr`: `verdict, ok, asked, asked_names, changes, preserves, rows:[{item, title, status: kept|asked|side_effect|not_asked|changed, detail, numbers?, reasons?}],
  checklist:{level_unchanged|moves_unchanged|move_timing_unchanged|gameplay_render_reused|duration_unchanged|camera_unchanged|hud_unchanged|captions_unchanged|pictures_unchanged|audio_unchanged: {ok, evidence}},
  pixels:{frames, frames_changed, ranges, contained, note}, route?`. Status words: kept → "kept", asked → "changed, as asked",
  side_effect → "changed, because of it", not_asked → "CHANGED WITHOUT BEING ASKED" (red, fails), changed → "differs" (compare mode).
  Present the contract in the research document's three words too: **Locked** (kept rows), **Allowed** (asked rows), **Forbidden** (not_asked rows).
- **Review** `rev`: `overall: ship|fix, would_download, why, viewer:{first_second, dead_time, pace, readability, clarity, cta} (1-5; the first two are measured, the rest the model's),
  match:[{control, verdict: match|partial|no|not asked, seen}], fixes:[str], suggested_edit, facts:{first_move_s, static_share, length_s, captions:[{readable}]}, model, seconds, sheet` (a contact-sheet image path).
- **Play** (`recordings/<dir>/play.json`): `beats:[{note, kind, tag, exits}]`, `notes`, `measured.beat_frames` (30 fps).
- **Inventory** item: see §3. Picture thumbnails: `file` containing `/uploads/` → `mediaUrl("uploads/<name>")`;
  a sprite name → `spriteUrl(name)`; `"gradient #a #b"`, `"tap ring"`, `"builtin:hand"` → drawn placeholders (see `thumb()`).

## 5. Design: the Stitch screens are the visual source of truth

Stitch project "Color Block Jam Studio" (`projects/7494116701124235404`), four desktop screens. Their HTML and
screenshots are saved in `design/` next to this file (`create-brief.html/.png` = the Create page before
generating; `create-refs.html/.png` = Create with two references attached; `create-ready.html/.png` = Create
after generation; `edit-workspace.html/.png` = the Edit workspace). Read the HTML: it carries the exact
Tailwind token config (colours, type scale, radius, spacing) in its `tailwind.config` block, and the layout.

Tokens (from the Stitch config; map 1:1 into Tailwind v4 `@theme` in `app/globals.css`):
- Surfaces: background/surface `#f9f9ff`, surface-container-lowest `#ffffff`, -low `#f1f3ff`, container `#e9edff`,
  -high `#e1e8fd`, -highest/surface-variant `#dce2f7`, surface-dim `#d3daef`, inverse-surface `#293040`.
- Ink: on-surface `#141b2b`, on-surface-variant `#4a4455`, outline `#7b7486`, outline-variant `#ccc3d7`.
- Primary (violet): primary `#5300b7`, primary-container `#6d28d9`, on-primary `#fff`, primary-fixed `#ebddff`,
  primary-fixed-dim `#d3bbff`, on-primary-fixed `#250059`, surface-tint `#7331df`.
- Secondary (sky): secondary `#006591`, secondary-container `#39b8fd`, secondary-fixed `#c9e6ff`, -dim `#89ceff`.
- Tertiary (mint): tertiary `#004b31`, tertiary-container `#006544`, tertiary-fixed `#6ffbbe`, -dim `#4edea3`.
- Error: `#ba1a1a`, error-container `#ffdad6`, on-error-container `#93000a`.
- Radius: default 4px, lg 8px, xl 12px, 2xl 16px (cards use `rounded-2xl`), pills `9999px`.
- Type: headline = Plus Jakarta Sans (xl 2.25rem/2.75rem −0.025em 700; lg 1.5rem 600; md 1.25rem 600);
  body/label = Inter (body-md .875rem/1.375rem; body-sm .75rem; label-sm .75rem 500 +0.01em; label-md .875rem 500;
  title-sm 1rem 600 −0.01em); code = JetBrains Mono .75rem 500. Load all three with `next/font/google`.
- Icons: use `lucide-react` (the Stitch HTML uses Material Symbols; map by meaning).
- Depth: white cards on the pale blue-violet background with `shadow-sm` at most; pills for nav and chips;
  violet only for the primary action and the active nav pill; status colours: pass/kept = tertiary (mint),
  adjusted/side-effect = amber (`#a86400` on `#fff1d9`), fail/not-asked = error, default/info = outline grey.

Layout per screen (keep the composition; the content comes from the engine, not from the mock):
- **Header** (all pages): logo mark + "Color Block Jam Studio / CREATIVE STUDIO", a pill nav **Create · Edit ·
  Showcase**, right side: the engine status pill (replaces the mock's "All changes saved": green dot "Engine online",
  amber "Engine busy: making another creative", grey "Engine offline: showcase only"), a Help button that opens a
  short "How it works" sheet (the four workflows in one paragraph each, what the edit contract means), and the
  passcode lock/unlock. No fake avatar.
- **Create, before generating** (`create-brief`): eyebrow pill (use the engine's planner name from meta, e.g.
  "Planner: Claude opus · one job at a time" instead of the mock's "Studio Generative V2.4"), H1 "Create a new
  creative", subline. Left column (7/12): the prompt card (textarea, char count, clear; the "Try an idea" chips =
  the five full test-case prompts from `NEW_EXAMPLES` in index.html, not the mock's texts), the attachments card
  (drop zone; accepted types; attached file chips with remove; "Uploaded before" chips from `/api/meta.uploads`
  like the existing page), the **Creative specifications** card = prompt helpers: Video duration 30/45/60 s,
  Format 9:16 / 1:1 / 16:9, Difficulty easy/balanced(medium)/hard, Hook & ending arc (near-fail clutch win /
  calm clean solve / cliffhanger cut / time-out fail with one block left / a mistake then the fix). These helpers
  **append plain sentences to the prompt** (e.g. "45 seconds.", "Square 1:1 format.", "A hard level.", "The player
  almost fails and wins with two seconds left.") shown as removable chips under the textarea and merged into the
  prompt that is sent; the brief then shows what the planner understood. State this in a one-line hint ("These
  add words to your prompt; the plan below shows how they were read."). Then the action row: primary **Generate
  creative** (= plan, then make, with review on and the revise loop on, like the existing "Plan & make"),
  secondary **Plan only** (shows the brief and a *Make it* button) and, under a "More" disclosure, *Level only*
  (preview), *Draft* (faster, no review), *Review as a viewer after making* (on), *Revise if the checks miss
  something* (on). Right column (5/12): the preview card: before generation it shows a phone frame with the
  poster of the latest creative (or the showcase's) and the three facts (format, length, pacing) read from the
  helpers; below it "Recently created" (3-4 cards with poster, prompt, length, time) linking to `/edit?c=…`.
  Drop the mock's "Recommended UA archetypes", "Auto-Optimize Prompt", "Version History", "4 variations", CTR
  numbers, "Interactive simulation" claims: nothing the engine does not do.
- **Create, references attached** (`create-refs`): the attachments card lists each file with a small thumbnail
  (video: a film icon + name + size), its role as the engine will read it (image: "asset to place" unless the
  prompt has reference words, then "reference image"; video: "reference video, read whole, never placed in the
  ad"; audio: "music for the ad"), and a delete. The info line: "Attachments guide the look, the board and the
  pacing. Color Block Jam's rules and block mechanics are always preserved."
- **Create, generation running / ready** (`create-ready`): on Generate, the left column becomes the
  **plan + progress**: "What the tool understood" (summary line, the facts line, the eight-row table Prompt
  control / Asked / What the tool does / Status; assumptions; "Read from the attached …" lines; the
  `needs` block as a red question with *Attach the files* / *Make it without them*), the **Reference to creative**
  card when a video/image reference was read (port `renderReference`: focus, what was looked for, the reference's
  timeline strip, adapted / not copied), and the **Progress** card: a stage strip (plan → level → play → record →
  compose → review → revise → done) and the live log in a mono box, with the elapsed time. When the version
  arrives: the summary banner ("Generation complete · 30 s ad created"), the **Creative** card = phone-frame video
  player (poster, controls, length), facts chips (length, format, difficulty, ending, level why), download MP4
  (studio path), links under a fold (ad.json, compose.json, brief.json, level.json, parts), **Level & gameplay**
  (board image, level why, the moves list with kind badges from `play.json`, the checks table from the
  recording), **As a viewer** (verdict, would download, the six scores, the match table, the fixes, the suggested
  edit with *Use it as the next edit* which carries it to `/edit?c=…&v=…` with the prompt prefilled), and the
  "Need to tweak something?" card → **Edit this creative**. The mock's "Predicted retention score 87.4" becomes
  the real viewer scores; no invented numbers anywhere.
- **Edit workspace** (`edit-workspace`): breadcrumb "Edit / <creative prompt, truncated> / v<n>"; left column:
  "What would you like to change?" (textarea; chips = `EDIT_EXAMPLES` from index.html; the attachments drop for
  an asset the edit uses; **Preserved by default** list = the engine's actual contract words: the level and the
  board, the moves and their timing, the camera, the HUD and the clock, every other picture, the captions, the
  sound; "Everything you do not mention stays as it is, and the edit report proves it."), primary **Apply change**
  (= plan the edit, show the understood table and the route line, then make with review on; if the plan has
  `needs`, stop and ask), and **Things in this ad** (the inventory list with thumbnails and the exact actions
  Replace / Add / Edit text / Turn off / Remove, as `thingAction` does; replacing the block texture asks which
  colour, from the level file's colours). Centre: the player for the selected version with a before/after toggle
  (two players, *Play both*) when the version is an edit; under it the version timeline (tabs v1 … vN with "←
  v3" for edits). Right rail: **Versions** (list; current highlighted; "v<N+1> will appear here after Apply"),
  **Change summary** = the edit report of the selected version (verdict line in mint or red; the Locked /
  Allowed / Forbidden contract; the checklist chips with evidence on hover; the nine rows; the pixel facts;
  "Asked to change: …"), **Compare** (two selects + button → the report between any two versions), **As a
  viewer** (same component as Create), **Metadata** (level: why; board size and shape from the level file:
  `GridWidth x GridHeight` if present, else from the why text; format; length; made in N s; recording reused or
  recorded). The mock's undo/redo, "Select an object in the preview", "Zero gameplay drift" claim and the
  canvas selection tools are dropped; the "Export video" button = download MP4 of the selected version.
- **Showcase** (`/showcase`): H1 "Finished creatives", one line on what the showcase is (real outputs of this
  tool, exported with their evidence; the videos are 720p web copies). A filter row by kind (All · Text · Image
  reference · Video reference · Edits). Cards: poster (9:16, lazy), title, tagline, chips (versions count, length,
  workflow, viewer verdict), link to `/showcase/<id>`. The detail page: the version tabs, the player, the prompt
  of that version, the "What the tool understood" table, Level & gameplay (board + moves + checks), As a viewer,
  and, for edited versions, the before/after players and the full edit report; the reference image when there
  is one ("Reference" with the picture and what was taken from it, from `brief.reference`/`planner.references`).
  An "Open in the Edit workspace" button appears only when the engine is online.

Responsive: the two/three-column layouts stack under 1024 px; the phone frame scales (`aspect-ratio: 9/16`,
max-height 70vh); no horizontal overflow at 390 px; tap targets ≥ 40 px. Respect `prefers-reduced-motion`.
Motion: `motion` (framer-motion's package) for card entrances and the progress strip; keep it light.

## 6. Flows (port from index.html, exact semantics)

- **Generate**: `POST /api/plan` → poll → brief. If `brief.planner.route.matched` names a creative (the
  attached MP4 is one of the tool's own versions), switch to Edit with that creative. If `brief.needs` is
  non-empty: stop, show the question. Else `POST /api/make {prompt, brief, review:true, revise:true, draft:false}`
  → poll (the progress log) → version → show it, clear the prompt and attachments, refresh "Recently created".
  Store the running job id in localStorage; on load, if a job is running, resume polling (`/api/jobs`).
- **Plan only**: plan → show the brief and a *Make it* button (and *Level only* → `/api/preview`).
- **Edit / Apply**: `POST /api/plan {prompt, creative_id, base, uploads}` → brief (with `planner.route`) → show →
  `POST /api/make {…, creative_id, base}` → the new version → select it, show its report and the pair.
- **Direct edits**: `POST /api/direct` with the op from the inventory item → poll → select the new version.
- **Review**: `POST /api/review {creative_id, n}` → poll → render.
- **Uploads**: `POST ${engineUrl}/api/upload` (multipart, header Authorization) → names → chips. Show the
  engine's refusal text on 400. Images, videos and audio go to the same endpoint.
- **Busy**: while a job runs anywhere (meta.busy true and it is not ours), disable the action buttons and show
  "The engine is making another creative; one at a time." like `watchServer`.
- **Offline**: health says offline → status pill grey; Create/Edit show a dismissible banner "The studio engine is
  offline right now. You can browse finished creatives in the Showcase." and the Edit picker lists showcase
  creatives (read-only, from `index.json`), the Create page's Recently created shows showcase cards.
- **Locked** (passcode set, cookie absent): the action buttons open the unlock dialog; after unlocking, the
  client fetches the engine url/token from `/api/session` and continues.

## 7. Showcase data (`public/showcase/`, produced by `scripts/export_showcase.py`; do not edit the exporter)

- `index.json`: `{generated, creatives:[{id, title, kind: create|image_guided|guided|edit|edit-ladder, tagline, prompt,
  versions:[{n, from, edit, prompt, length_s, workflow, video, poster, summary, review_overall, would_download, video_mb}]}]}`.
- `<id>/showcase.json`: `{id, title, kind, tagline, versions:[full version objects (§4) with review inlined]}`.
- Files at their studio-relative paths: `<id>/v<n>/ad/ad.mp4` (720p), `<id>/v<n>/ad/poster.png`, `<id>/v<n>/board.png`,
  `<id>/v<n>/review.json`, `<id>/v<n>/inventory.json`, `<id>/v<n>/brief.json`, `<id>/v<n>/level.json`,
  `recordings/<hash>/play.json`, `uploads/<reference image>`, `sprites/<name>.png`, the review contact sheets.
- Load showcase JSON client-side with `fetch("/showcase/...")` or at build time with `fs` in server components; the
  detail page may be statically generated from `index.json` (`generateStaticParams`). Next's `public/` serves it.

## 8. Stack and conventions

- Next.js 16 (App Router, TypeScript), React 19, Tailwind v4 (`@tailwindcss/postcss`, tokens as `@theme` vars in
  `app/globals.css`), `motion`, `lucide-react`. Scaffold by writing the files yourself (no `create-next-app`
  prompts): use `~/stitch-build/ortopedi-studyo/` as the reference for `package.json` versions (`next 16.3.4`,
  `react 19.2.8`, `@tailwindcss/postcss ^4`, `tailwindcss ^4`, `motion ^13`, `lucide-react ^1`), `postcss.config.mjs`,
  `next.config.ts`, `tsconfig.json`, `eslint.config.mjs`. Read `node_modules/next/dist/docs/` for Next 16 breaking
  changes after installing (async `params`/`searchParams`/`cookies()`; `proxy.ts` instead of middleware).
- Client components for anything with state; one `lib/engine.ts` (fetch helpers, `pollJob`, `mediaUrl`,
  `spriteUrl`, types), one `lib/showcase.ts` (load index/detail), `components/` for Brief table, Checks table,
  Moves list, Proof/Edit report, Review, Player, PhoneFrame, Inventory, Progress, StatusPill, UnlockDialog, etc.
  Same components render live data and showcase data.
- Media: plain `<video>` and `<img>` (remote engine host is dynamic; do not use `next/image` for engine media).
  Reserve aspect ratios (9:16) to avoid layout shift; `preload="metadata"`; posters always set.
- Accessibility: labelled form controls, keyboard-usable chips and tabs, focus rings, `aria-live="polite"` on
  the progress log and the status pill, colour never the only signal (status words are always written).
- Page `<title>`: "Color Block Jam Studio"; description: "Text, image or video in, a 30-60 second Color Block Jam
  ad out: a deterministic game pipeline with an agentic planner and controlled, proven edits." Favicon: an SVG
  mark (four coloured blocks).
- Write `web/README.md`: how to run locally (`npm i`, `.env.local` with `ENGINE_URL=http://127.0.0.1:8765`, `npm run
  dev`), how it talks to the engine, the env vars, how to refresh the showcase, how to deploy (`vercel --prod`).
- No git commits (the owner commits). No secrets in the repo (`.env.local` is git-ignored; add `web/.gitignore`
  with `node_modules`, `.next`, `.env*.local`, `.vercel`).

## 9. Verification you must do before reporting done

1. `npm run lint` and `npx tsc --noEmit` clean; `npm run build` clean.
2. Serve the production build on port 3105 (`lsof -ti :3105 | xargs kill -9; nohup npm start -- -p 3105 &`).
3. With `.env.local` → `ENGINE_URL=http://127.0.0.1:8765` (the owner's engine is running there, no token, no
   passcode): the header must say Online; `/edit` must list the live creatives and open
   `1015-074810-create-a-hard-color-block` v13 with its edit report, before/after players, Things in this ad.
4. With `ENGINE_URL=http://127.0.0.1:9` (nothing there): Offline pill, banners, Showcase works, Edit picker shows
   showcase creatives read-only, `/showcase/1015-074810-create-a-hard-color-block` renders every tab.
5. Playwright (`npm i -D playwright`; browsers are in `~/Library/Caches/ms-playwright`, use `chromium`): fresh
   context per check; viewports 1440×900 and 390×844; assert `document.documentElement.scrollWidth -
   window.innerWidth === 0`, zero `pageerror`, zero console errors (ignore the video `play()` autoplay rejection);
   screenshot each page at each viewport into `web/qa/` (`scale: "css"`), and look at them: compare the Create
   page composition with `design/create-brief.png`, the Edit page with `design/edit-workspace.png`.
6. Keyboard: tab through the Create page; every chip/button reachable; the unlock dialog traps focus.
7. Report: what was built, the exact file list, what differs from the Stitch mock and why (the honest-content
   rule), anything not verified.
