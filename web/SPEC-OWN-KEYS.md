# Addendum to SPEC.md (2026-10-19, evening): "Your keys" — run the studio on your own Gemini and Anthropic keys

Read `SPEC.md` first and `SPEC-FEEDBACK-INLINE.md` for how the last addition was made. The engine is the source of
truth: `../src/cbj/keys.py` (read its docstring), `llm.describe_backend` and `/api/meta` in `../src/cbj/app.py`, and the
README section "Run it on your own accounts". Nothing in the engine changes for this addition; the relay DOES change this
time (one small, specified change, §3).

Why this exists. The studio as delivered runs on the owner's Claude account and Gemini key. A reviewer or a team may want
to run it on their own keys instead, without a self-hosted engine. The engine already accepts them per request; this
addition lets a user enter them in the browser and sends them along. Optional: with nothing entered, everything works as
today.

## 1. Engine API
- Requests that start work accept the headers `X-CBJ-Gemini-Key`, `X-CBJ-Anthropic-Key`, `X-CBJ-Planner`
  (`studio` | `anthropic` | `anthropic:<model id>`). The engine uses them for that job only and never returns them.
- `GET /api/meta` with the same headers answers as the request would run: `backend` (`claude` | `anthropic` | `nvidia`),
  `models`, and `own_keys: {gemini: bool, anthropic: bool, planner: "studio" | "anthropic"}`; `features.own_keys: true`
  (an older engine lacks it: hide the dialog and the pill).
- CORS allows the three headers on direct calls.

## 2. The browser: `lib/keys.ts` + `components/KeysDialog.tsx`
- Storage: `cbj.keys` in `sessionStorage` by default ("this tab"); with the switch "Remember on this device" in
  `localStorage` instead (and removed from the other). Shape `{gemini?: string, anthropic?: string, planner?: "studio" |
  "anthropic", model?: string}`. Never sent anywhere but the engine calls; never logged; never put in a URL.
- `lib/engine.ts`: `target()` adds the three headers (when set) to every POST and to `GET /api/meta`, both on the direct
  path and on the relay path (the relay forwards them, §3). Reads of creatives, studio files and jobs do not carry them.
- The dialog (opened from a key icon in the header, next to the feedback icon, and from a link in the Unlock dialog
  "Optional: use your own keys"): title "Your keys"; one line of honesty: "Your keys are used only for the model calls of
  your own jobs, held in the engine's memory while the job runs, and never stored or logged by it. The passcode is still
  needed: the studio's computer still records the game."; a Gemini API key field (password type, show/hide) with "the
  reference-video reader"; an Anthropic API key field with "the planner and the picture reader"; a planner choice: "This
  studio's planner (the owner's Claude account)" / "My Anthropic key" with an optional model id (default
  `claude-opus-5-5`, placeholder shows it; also offer `claude-sonnet-5-5` as a chip); the Remember switch; Save, Clear,
  Cancel. Validation: an Anthropic key is required when "My Anthropic key" is chosen; keys are trimmed; nothing else.
- After Save, `engine.refreshMeta()` so the header's planner pill updates.
- Header pill: when any key is set, a small pill "Your keys: Gemini · Claude" (only the ones set), title "Running on your
  own keys"; the existing planner words (`plannerName`) come from `meta.backend/models` and so already reflect the
  choice ("Planner: anthropic/claude-opus-5-5"). Create's status line shows it the same way.
- Offline or an older engine: the icon is shown disabled with "Needs the engine".

## 3. The relay (`app/api/engine/relay/[...path]/route.ts`), the one change
Forward the three request headers `x-cbj-gemini-key`, `x-cbj-anthropic-key`, `x-cbj-planner` to the engine when present,
on POSTs and on `GET api/meta` only. Nothing else changes: the passcode checks stay, the allow lists stay.

## 4. QA and docs
- `scripts/qa-keys.mjs` run from `qa.mjs` (`--keys-only`): open the dialog from the header and from the Unlock dialog,
  save keys ("this tab"), check `sessionStorage` has them and `localStorage` does not, flip Remember and check the
  reverse, check an intercepted `POST /api/plan` carries the three headers and an intercepted `GET /api/meta` too, and
  that `GET /api/creatives` does not; the pill text; Clear empties both stores and the pill goes; offline: the icon
  disabled. Use intercepted engine responses for meta (`{..., backend: "anthropic", models: ["anthropic/claude-opus-5-5"],
  own_keys: {gemini: true, anthropic: true, planner: "anthropic"}}`); never send a real key anywhere. 1440 and 390,
  no overflow, no console errors; screenshots `qa/keys-*`.
- `npm run lint`, `npm run build` clean; README.md: a short "Your keys" paragraph in the Pages/feature list.

## 5. Words (keep them)
"Your keys" · "Optional: use your own keys" · "Remember on this device" · "This studio's planner (the owner's Claude
account)" · "My Anthropic key" · "Running on your own keys" · the honesty line above, verbatim.
