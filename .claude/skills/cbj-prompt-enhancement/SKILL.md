---
name: cbj-prompt-enhancement
description: How cbj-creative improves a user's request before planning (src/cbj/enhance.py) and how the optional trend ideas are made (src/cbj/trends.py) - the contract (the planner's vocabulary in, nothing added, questions for the rest), the code checks that enforce it against the engine's own readers, the fallback to the user's words, the workflow line, and the brand-safety rules of the trend step. Use when enhancing or judging an enhanced prompt, when writing options for a question, when deciding whether a rewrite added an ask, or when reviewing a trend idea before it becomes a prompt.
metadata:
  spec-version: "1"
  last-verified: "2026-10-18"
---

# Prompt enhancement and ideas from trends

## 1. Purpose
A prompt is a contract: the planner fills only what it says, the engine makes exactly the brief, and the evaluator
measures every fact the prompt states. Improving a prompt therefore means saying what the user said in the words the
planner and the game understand, and adding nothing; everything the enhancer would like to add is a question the user
may accept. Trend ideas are prompts written from live signals; they never touch the workflows.

## 2. Source of truth
- `src/cbj/enhance.py`: `VOCABULARY` (the digest the model writes with), `SYSTEM` (the rewrite rules), `violations()`
  and `added_facts()` (the code checks), `enhance()` (the loop and the fallback), `workflow_for()`.
- `src/cbj/trends.py`: `UNSAFE`, `GENERIC`, `TREND_SYSTEM`, `_check_idea()`, `discover()` (signals, cache).
- The readers the checks reuse: `audit.asked` (the measurable facts of a prompt), `brief.QUOTED`, `brief.plain_text`.
- Why it is built this way, with live results: `~/rollic-case/PROMPT-ENHANCEMENT-AND-TRENDS-2026-10-18.md`.
- Vocabulary in depth: `cbj-prompt-controls`; the game's limits: `cbj-game-rules`; edits: `cbj-controlled-editing`.

## 3. Facts
**The contract of a rewrite.** Keep the intent and every concrete ask; keep every quoted caption word for word and
every number exactly; one plain paragraph in English, no field names, tokens, hex codes or bullets; legal gameplay (one
block per drag, exits through the block's own gate, orders with first / then / last, mistakes 0-3, near-fail 1-3 s, one
level, 30-60 s); impossible asks replaced with the closest possible thing and listed as a "replaced" change; attached
files named as the user did, with their place; vague mood words kept only when tied to something concrete, otherwise a
question; an edit starts with what to keep and names the one change; a clear request is returned unchanged.

**Added asks.** `added_facts` compares `audit.asked` of the original and of the rewrite over 21 keys (blocks, colours,
colour names, difficulty, length, seconds left, mistakes, shape, looks, ending, stuck-by, blocks-by, hesitations, the
clock, walls, level number, blocks per colour, cursor, music, background, blocks left) plus new quoted captions. An
added fact is allowed only when a change entry justifies it: its `before` is in the user's text (3+ characters) and
its `after` carries the fact (a translation, or a declared replacement). A `before` that is not in the request
justifies nothing. A quoted claim of the user's may disappear only when a removed/replaced change names it.

**The loop and the fallback.** One model call; on violations one re-ask with the list; if the rewrite still breaks a
rule, the user's words are returned unchanged (`changed: false`) with the violations in `warnings` ("Kept your
wording: ...") and the model's questions kept: a wrong enhancement is worse than none.

**Questions.** At most three, each with 1-3 options; an option is ONE sentence that can be appended to the prompt as
it is. A request written in another language always gets the captions-language question unless it says which.

**The workflow line.** `workflow_for` calls `app.workflow_of` on the (enhanced) request and its attachments, so the
result says how the engine will read it: create, image_guided (a picture plus reference words), guided (a video), edit.

**Trend ideas.** Signals: Google's daily trending searches (RSS, region code) and Tavily news (four fixed queries plus
the theme), filtered in code (`UNSAFE`: tragedy, politics, religion, sex, violence, crime, health, named politicians;
`GENERIC`: listicles). The model writes 4-6 ideas from those signals only, each mapping one trend to the game's
levers (look, colours, background, caption tone, hook, ending, tempo, curve, length, format; a sticker as a note);
the ad's copy never names a brand, title, team or person. `_check_idea` drops an idea whose prompt is too short, whose
hook or captions exceed 6 words, that contains statistics or technical names, or whose trend is unsafe; dropped ideas
are listed with reasons. Cached 6 h per day, region and theme in `studio/_trends/`.

**Ideas from a link** (`from_link`). The page behind one public http(s) URL is the only signal: `public_url` refuses
non-http schemes and any host that resolves to a loopback, private, link-local or reserved address; `read_link` tries
Tavily extract, then a direct fetch with scripts, styles, navigation and tags stripped (at most 200 KB, 6000 characters
kept); a page that is too short, or unsafe by `UNSAFE`, is a plain error. The same model, schema and `_check_idea`
apply; the idea's source is forced to the URL. Cached per URL and theme.

## 4. Procedure
To enhance a request by hand (or to judge an enhanced one):
1. Read the request as the planner would: which of the eight controls does it touch, in which words?
2. For each touched control, restate the ask in the vocabulary (keep quotes and numbers); for untouched controls write
   nothing.
3. Run the asks through `cbj-game-rules` section 5; replace what is impossible and keep a note (before -> after, why).
4. Check: `audit.asked(original)` vs `audit.asked(rewrite)`; every new fact must be tied to the user's words by a change
   entry, else it becomes a question. `brief.plain_text(rewrite) == rewrite`.
5. For an edit, resolve pointers through the inventory (`studio.planner_context`); when two things fit, ask.
6. Read the result back: could any sentence be read as a second ask? Remove the ambiguity.

To review a trend idea before it is used: the trend must be in the day's signals, the source must be a real URL or
search term from them, the copy must name no person, brand or title, and the prompt must plan cleanly (`cbj plan`).

## 5. Not possible here
The enhancer cannot verify a translation's facts in code (the original is read by English tables; a translated fact is
accepted on the strength of the change entry quoting the user's words). It does not run automatically before Generate.
It cannot make the planner read a mechanic the game lacks; it only replaces the ask. Trend ideas depend on two free
feeds; with both down the call returns an error and the site hides the card. Nothing here changes the planner, the
brief schema, the workflows or the evaluation.

## 6. Evidence
- `uv run pytest tests/test_enhance.py tests/test_trends.py -q` (no network, no model: fakes).
- `CBJ_PLANNER=claude uv run cbj enhance "<prompt>" [--edit ID --base N --upload NAME]` prints the rewrite, the changes,
  the questions, the notes and the workflow line; `--json` writes the result.
- `CBJ_PLANNER=claude uv run cbj trends -n 4 [--theme X] [--refresh]` prints the ideas, the skipped trends and the
  signal counts; the cache file is `studio/_trends/<date>-<region>-<theme>.json`.
- Live cases of 2026-10-18 (bomb, Turkish, the case prompt, an edit pointer, an image reference) are in the design
  document named in section 2.

## 7. Change rules
Any change to `audit.asked`'s keys, to `brief.QUOTED`, to the controls' vocabulary (`cbj-prompt-controls`) or to the
game's limits (`cbj-game-rules`) must be mirrored in `enhance.VOCABULARY`, `FACT_KEYS` and this skill in the same
edit; bump `last-verified`. New kinds of change or question need a schema change in `enhance.SCHEMA` and a test.
