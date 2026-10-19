# SPEC follow-up: no Anthropic API key anywhere in the user-facing site

The owner's rule: a user who wants their own Claude account connects through their own Claude Code CLI, on their own
engine (SPEC-OWN-ENGINE §1 mode A). Nobody uses an Anthropic API key. Apply on top of SPEC-OWN-ENGINE:

1. **The dialog** keeps two modes, but mode B is now only "This studio's engine, with my Gemini key": one field,
   *Gemini API key · reads reference videos on your own quota*, with the remember switch. Remove the Anthropic key
   field, the planner radios and the model-id chips from the dialog entirely. Mode B's first line: "The planner runs on
   the studio's Claude account. To use your own Claude account, choose *My own engine*: it runs through your own
   Claude Code login, no API key."
2. **Headers**: in mode B send only `X-CBJ-Gemini-Key`; never send `X-CBJ-Anthropic-Key` or `X-CBJ-Planner` from the
   site any more. Remove their names from lib/keys.ts and the relay's forwarded-header list is left as is (harmless).
3. **The header pill** in mode B reads "Your Gemini key"; in mode A "Your engine: <host> · <backend>/<model>".
4. **Unlock dialog** link text: "Optional: use your own engine or your own Gemini key".
5. **Help sheet** gets a short fifth section "Your own account": the three steps of mode A, one line on the Gemini key.
6. **README (web/README.md and the root README section "Run it on your own accounts (optional)")**: remove the API-key
   alternative and the X-CBJ-Anthropic-Key / X-CBJ-Planner mentions from the user-facing text; describe only: (a) own
   engine with own CLI login + own Gemini key, verified by `uv run cbj setup-check --live`, pointed at from the site
   (three steps), (b) a Gemini key alone on the hosted site. The engine's `CBJ_PLANNER=anthropic` support may stay in
   code but is not documented for users.
7. **QA**: update qa-keys.mjs and qa-own-engine.mjs for the removed fields; lint and build clean; do not commit or
   deploy; a short report at the end.
