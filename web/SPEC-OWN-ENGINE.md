# SPEC: "Your engine" — use the hosted site with your own engine (your own Claude CLI login and Gemini key)

## Why
The owner promised that another user can run the system on their OWN Claude account (the Claude Code CLI, logged in)
and their own Gemini key, with no API key. Today the site's *Your keys* dialog asks for an Anthropic API key, which is
the opposite of that promise. A remote user's CLI cannot be used by the owner's engine (the CLI runs where the engine
runs), so the only way to honour the promise on the hosted site is: the user runs the engine on their own Mac
(`CBJ_PLANNER=claude`, their `GEMINI_API_KEY`, verified by `uv run cbj setup-check --live`) and points THIS site at it.
The engine already supports it: `CBJ_CORS_ORIGINS=https://cbj-creative-studio.vercel.app` lets the browser call it
directly, `CBJ_API_TOKEN` is optional, `/api/health` and `/api/meta` describe the backend.

## What to build (web/ only; nothing under ../src changes)

### 1. The dialog becomes "Your engine and keys" (components/KeysDialog.tsx, lib/keys.ts)
Two modes, as a segmented choice at the top; the first is the default and the recommended one:

**A. "My own engine (my Claude CLI, my Gemini key)"**
- Fields: *Engine URL* (placeholder `http://127.0.0.1:8765`), *Engine token (optional)* (password field; the value of
  `CBJ_API_TOKEN` if the user set one).
- A *Check* button: GET `<url>/api/health` and `<url>/api/meta` directly from the browser (with the token as
  `Authorization: Bearer` when given). On success show one line: "Reachable · planner: <backend>/<model> · Gemini key:
  yes/no · voice: yes/no" (from meta: `backend`, `models`, `features.soundtrack.voice`, and whatever meta says about the
  Gemini key — read the shape from a live `/api/meta`; if it is not there, show only what is). On failure show the
  exact reason with the fix: not reachable (is `uv run cbj ui` running?), CORS blocked (start it with
  `CBJ_CORS_ORIGINS=https://cbj-creative-studio.vercel.app`), 401 (wrong token), mixed content blocked (Safari blocks
  http://127.0.0.1 from an https page; use Chrome, Edge or Firefox, or a tunnel URL).
- Help text under the fields, exactly these three steps:
  1. On your Mac: `claude` once to log in, then in `cbj-creative/.env`: `CBJ_PLANNER=claude` and `GEMINI_API_KEY=...`;
     `uv run cbj setup-check --live` proves it.
  2. Start it for this site: `CBJ_CORS_ORIGINS=https://cbj-creative-studio.vercel.app uv run cbj ui`
  3. Paste the URL here and press Check.
- *Remember on this device* switch as today (session vs localStorage), *Clear*, *Cancel*, *Save*. Save is enabled only
  after a successful Check (so a broken URL is never saved).

**B. "This studio's engine, with my keys"** (the existing content, re-worded)
- First line: "The studio's planner runs on the owner's Claude account. Add a Gemini key for reading reference videos
  on your own quota. An Anthropic API key is only for those who prefer the API to the studio's planner; it is never
  needed to use your own Claude account — for that, choose *My own engine*."
- Then the existing Gemini key field, the planner radios and the Anthropic key field, unchanged in behaviour.

### 2. When an own engine is saved, the whole site uses it
- Every engine call (reads and writes, uploads, job polling, feedback, lessons, report downloads, soundtrack, enhance,
  trends, meta/health) goes **directly** to the saved URL with the saved token as Bearer; the relay is not used at all.
- Media (`<video>`, `<img>`, file links) point at `<own url>/studio/<path>`.
- The passcode gate is **not** required (it protects the owner's engine only): with an own engine active, making and
  editing are allowed without Unlock; the lock button is hidden or shows "Your engine" with the tooltip "Making and
  editing run on your own engine; no passcode needed."
- The status pill polls the own engine's `/api/health` and reads "Your engine online" / "Your engine busy …" /
  "Your engine offline: check `uv run cbj ui`"; the header pill next to the key icon reads "Your engine: <host> ·
  <backend>/<model>" (e.g. "Your engine: 127.0.0.1:8765 · claude-cli/opus"), tooltip "Running on your own Claude account".
- The Create page's planner chip reads the own engine's meta (so it says "Planner: claude-cli/opus · your engine").
- The Showcase stays static. The Feedback (owner) page works against the own engine without the passcode.
- Switching back (Clear, or mode B) returns to the studio's engine and the passcode gate.
- The X-CBJ-* key headers are still sent in mode B only (unchanged); in mode A they are not sent.

### 3. Edge cases
- Mixed content: Chrome, Edge and Firefox allow fetches and media from `http://127.0.0.1` / `http://localhost` on an
  https page; Safari does not. Detect a fetch failure in Safari and show the Safari sentence from §1.
- A tunnel URL (https://….trycloudflare.com) is accepted as an own engine too; same fields.
- Uploads over 4.5 MB: fine, because they go directly to the engine (no relay).
- If the own engine goes offline mid-session, behave like today's offline state but keep the own-engine setting.

### 4. QA (scripts/qa-own-engine.mjs, run from qa.mjs, with a `--own-engine-only` flag)
Use Playwright routing to fake an own engine at `http://127.0.0.1:8765` (health, meta, creatives list, one job, one
feedback POST) — no real engine call. Check: the dialog's two modes, Check success and the three failure messages,
Save disabled before Check, the pill text, that a POST (e.g. /api/enhance) went to the own URL with the token and
NOT to the relay, that the lock is not required, media src on the own host, Clear restores the studio engine. Both
1440 and 390 widths, no overflow, no console errors. Screenshots to qa/own-engine-*.

### 5. Docs
- web/README.md: a section "Use the site with your own engine" (the three steps, the browsers, what travels: nothing
  but your own calls to your own machine).
- The root README's section "Run it on your own accounts (optional)" gets a short paragraph "On the hosted site: Your
  engine" pointing to the same three steps (edit only that section).

Constraints: `npm run lint` and `npm run build` clean; no file under ../src or the relay's engine-token logic for the
studio engine changes; do not commit; do not deploy; write one short report of what was built and what was not.
