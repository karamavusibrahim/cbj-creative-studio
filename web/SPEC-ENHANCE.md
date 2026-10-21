# Addendum to SPEC.md (2026-10-18): prompt enhancement and ideas from trends

Two engine features were added today; the web app gets their UI. Read `SPEC.md` first (architecture, design,
flows): nothing there changes. The engine is the source of truth: `../src/cbj/enhance.py` and
`../src/cbj/trends.py` (read their module docstrings), the endpoints in `../src/cbj/app.py`.

## 1. Prompt enhancement ("Enhance prompt")

**What it is.** The engine rewrites the user's request in the words its planner reads reliably and adds
nothing: every concrete ask in the rewrite comes from the user's own words (translated or clarified), game-impossible
asks are replaced with the closest possible thing and listed, and anything the engine would like to add is returned
as a *question* with tap-able options. It is the "Enhance" / "Auto-Optimize Prompt" button of the Stitch mock, built
honestly.

**Endpoint.** `POST /api/enhance {prompt, uploads:[names], creative_id?, base?}` → synchronous (10-25 s; NOT a job;
it does not wait for a running make). Response:
```
{ prompt: string,            // the text to put in the textarea (unchanged copy of the original when changed=false)
  original: string, changed: boolean, mode: "new"|"edit",
  workflow: "create"|"image_guided"|"guided"|"edit",   // how the engine will read it, decided by the engine
  changes: [{kind: "clarified"|"translated"|"replaced"|"removed"|"reordered", before, after, why}],
  questions: [{question, options: [sentence, ...]}],  // ≤3; an option is one sentence to APPEND to the prompt
  warnings: [string], model: string|null, seconds: number }
```
Errors: 400 `{detail}` (empty prompt, unknown creative, model unreachable). Needs the passcode session like Generate
(it runs a model on the owner's machine). `GET /api/meta` now has `features: {enhance: true, trends: boolean}`.

**UI, Create page** (the prompt card):
- A secondary button **Enhance prompt** (sparkles icon) in the prompt card's footer row, next to the ⌘+Enter hint,
  enabled when the textarea has text and the engine is online. It sends the MERGED prompt (the textarea plus the
  helper-chip sentences, `mergePrompt`) and the attached file names. While waiting: the button shows a spinner and
  "Reading your request…" (aria-live).
- On a result with `changed: true`: the textarea's text becomes `prompt`; the helper chips are cleared (their
  sentences are now inside the text, so they must not be appended twice); a small **Enhanced** card appears under the
  prompt card with: one line "Rewritten so the planner reads it as you meant; nothing was added." · an **Undo** link
  (restores the original text and the chips exactly) · the change list, each row: a kind chip (clarified / translated
  / replaced / removed / reordered; "replaced" in amber), `before` struck through in muted ink, `after` in ink, `why`
  in small text · the questions block (below) · the workflow line: "Will be read as: <WORKFLOW_WORDS from
  enhance.py>" · warnings in amber.
- On `changed: false`: no text change; a quiet line "Your request is already clear." plus the questions block and
  warnings if any (the questions are the useful part then).
- **Questions block** ("You may want to add"): each question with its options as chips; tapping an option appends
  that sentence to the textarea (with a space, after a full stop), marks the chip as added (filled) and lets a second
  tap remove exactly that sentence again. Never auto-append.
- Keyboard: the Enhance button is reachable by Tab; the change list is a `<ul>`; the Undo is a button.
- Phase: available only in the compose phase (before Generate). After Generate the card disappears like the prompt.

**UI, Edit workspace** (the "What would you like to change?" card): the same button and the same Enhanced card,
posting `creative_id` + `base` (the version shown) and the attached asset names; the engine then starts the rewrite
with what to keep and resolves pointers ("this asset") to the names in *Things in this ad* or asks. No helper chips
here. The workflow line reads "Will be read as: an edit of this creative…".

## 2. Ideas from trends ("Start from a trend", optional)

**What it is.** Live signals (Google's trending searches, news search) turned by the planner's model into 4-6
CBJ ad ideas, each a complete prompt in the engine's vocabulary with its trend, why it is current, its
source URL or search term, how the trend maps to the game's levers, and a hook. Brand-safe by rule (no names of
people, brands, titles; tragic or political trends skipped). Cached on the engine for 6 hours per theme and region.

**Endpoint.** `POST /api/trends {theme?: string, region?: "US", n?: 4, refresh?: false}` → synchronous (first call
20-40 s; cached calls instant). Response:
```
{ generated: iso, region, theme|null, cached: boolean, model, seconds,
  ideas: [{title, trend, category: gaming|culture|season|sport|viral, source, why_now, mapping, hook, prompt}],
  skipped: [{trend, why}], signals: {google: n, news: n}, sources: [{title, url, published}] }
```
Errors: 400 `{detail}` when the engine has no `TAVILY_API_KEY` (then `meta.features.trends` is false: hide the card),
or when no signal could be fetched. Passcode session required (it runs a model).

**UI, Create page**, a new collapsed card **Start from a trend (optional)** placed between the prompt card and the
Attachments card. Collapsed state: one line "What is trending today, as prompts the engine can make. Optional."
and a **Get ideas** button; an optional small text field "Theme (optional)", placeholder "e.g. autumn, football,
a game launch". Hidden when `meta.features.trends` is false or the engine is offline; locked session → the unlock
dialog first (like Generate).
- Loading: skeleton of 4 idea cards, status text "Checking Google Trends and the news… writing ideas" (aria-live).
- Result: a horizontal row (wraps at phone width) of idea cards: category chip, title, the trend line, "why now" in
  small text with the source as a link (an URL opens in a new tab; a bare search term is shown as text with a
  search icon), the mapping line, the hook in quotes, and a primary small button **Use this prompt** that puts
  `prompt` in the textarea (replacing it; if the textarea already has text, ask inline "Replace your text?" with
  Replace / Cancel), scrolls to the prompt and focuses it. The Enhance button then works on it as on any text.
  A footer line: "Generated <time> · <n> trending searches, <m> news items · cached" and a **Refresh** link
  (`refresh: true`) and a "Skipped (n)" disclosure listing `skipped` with reasons (this is the brand-safety proof).
- The card never auto-fetches: ideas cost a model call and the user chose "optional".

## 3. Showcase / offline
Both features need the engine; offline they are hidden (trends) or disabled with a tooltip "Needs the engine"
(enhance). Nothing is exported to the showcase.

## 4. Verification to add to `scripts/qa.mjs`
- Online: the Create page shows the Enhance button and the trend card; clicking Get ideas is NOT part of the
  automated run (it spends a model call); instead mock-free checks: the button states, the collapsed card, and the
  questions block rendering from a fixture object (write one small fixture in the test from the response shape
  above, render the Enhanced card component with it in isolation, e.g. a `?demo=enhanced` dev-only query handled in
  the component, or a Storybook-free route under `app/dev/` that is excluded from production by an env check).
  Simplest acceptable: a unit-style Playwright check that posts a real `/api/enhance` to the local engine ONCE with
  the prompt "An easy level, calm, 30 seconds." (that is allowed: it is cheap, ~15 s) and asserts the card renders.
- Offline: no Enhance button enabled, no trend card.
- Keyboard: Tab reaches Enhance, the Undo, every option chip, Use this prompt.

## 2b. Ideas from a link (added 2026-10-18, later)

The same endpoint takes a link: `POST /api/trends {url, theme?, n?: 2, refresh?}` → the page behind the URL is the
only signal; the response has the same shape as §2 with `link: url`, `region: null`, `signals: {google:0, news:0,
link:1}`, 1-3 ideas whose `source` is the URL. Errors 400 `{detail}`: not a public http(s) link, a local or private
address, a page that could not be read (paywall, login, social feed), a page about a topic an ad should not ride, or no
usable idea; show the detail verbatim under the field.

**UI, in the same trend card**, under the theme field: a second row "Or paste a link to an article, a post or a trend
page" with a URL field (type url, placeholder "https://…") and a button **Read link** (enabled when the field has text
and the engine is online; passcode like Get ideas). Loading: the same skeleton with status "Reading the page… writing
ideas". Result: the idea cards from the link are shown in the same grid, each with a small "From your link" chip and
the URL as its source link; they appear ABOVE any feed ideas already shown and do not replace them. The footer line
for a link result says "From <host> · read <time>" with Refresh. Keep everything else (Use this prompt, Skipped,
Replace your text?) identical. Phone width: the URL row stacks.
