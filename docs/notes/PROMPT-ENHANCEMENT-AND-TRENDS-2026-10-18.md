# Prompt enhancement and ideas from trends (2026-10-18)

Two additions to cbj-creative, both in front of the agentic workflows and never inside them: a **prompt enhancer** that
rewrites a request in the words the planner reads reliably without adding asks, and an optional **ideas from trends**
step that turns what is trending today into prompts the engine can make. Built after reading the brief (14 pages),
the game's C# (`~/Downloads/CBJ`, line-cited in the game-rules skill), the planner (`planner.py` SYSTEM and the 40
post-rules), the brief schema and word tables (`brief.py`), the evaluator's prompt reader (`audit.asked`), the four
workflows (`workflows/*.py`), the routing words (`route.py`, `reference.py`), the prompt-controls skill, and the trend
step (Google Trends RSS + Tavily news → LLM).

## 1. What the analysis found (why the enhancer is shaped the way it is)

**A prompt is a contract, not a wish.** The planner fills only what the request says (SYSTEM: "Only fill a field from
what the request says; leave the default when it says nothing"), `brief.merge` takes only the declared field groups the
prompt's words support, and `audit.asked` measures every fact the PROMPT states (block count, colours, difficulty,
length, ending, mistakes, shape, looks, seconds left, clock, walls, level number, cursor, music, background, blocks at
the cut, quoted captions) and feeds misses back into the revise loop. Consequences:

- Anything the enhancer ADDS becomes an "asked" row and a measured fact. An enhancer that "completes" a prompt with
  an ending, a length or a difficulty changes what the user gets and what the evaluator demands. So the enhancer may
  not add asks; it offers them as **questions** the user taps (each option is one sentence appended verbatim).
- The engine's readers are **English word tables** (`audit._LENGTH`, `_DIFFICULTY`, `ORDER_WORDS`, `REFERENCE_WORDS`,
  `image_guided.applies`, `route.upload_intent` …) on top of the LLM planner. A Turkish prompt is planned by the model
  but not measured or routed by the tables: "45 saniye" is no length to the audit, "bu resimden ilham al" does not
  route to the image-guided workflow. Translation to English is therefore the single most valuable rewrite, and it
  must keep the facts exactly (every number, every quoted caption).
- Routing is decided from words + attachments (`app.workflow_of`): a picture with reference words → image-guided; a
  video → guided; a creative id → edit; otherwise create (a picture without reference words is an asset to place).
  The enhancer makes the reference words explicit when the user meant a reference ("same vibe as this pic" → "the
  attached image is a reference for its look and colours") and reports which workflow will read the result.
- The game has a short, closed list of things: blocks, colour gates, holes/walls, the clock (game-rules skill §5 lists
  what is absent: boosters, bombs, ice, keys, chains, characters, items, two blocks leaving together, gate sides,
  regions, a second level). The planner already answers such asks with "not_supported" rows; the enhancer replaces
  them BEFORE planning with the closest possible thing and lists the swap (bomb → one key move that frees several
  blocks, which then leave one after another; ice/locks → a block in the way moved aside first; "only 1% can solve
  this" → an honest dare, because ad rules forbid statistics, odds and IQ claims).
- Vague mood words ("make it pop", "super engaging", "premium") are not measurable: the planner's CONCEPT TO GAMEPLAY
  table maps a few (relaxing, rage, speedrun, "can you solve it?", tension, beginners); the rest are read loosely. The
  enhancer keeps the mapped words, and turns the unmapped ones into a question with concrete options from the vocabulary.
- An order of interactions needs sequencing words (first / then / last); captions must be quoted and under 6 words;
  near-fail seconds 1-3; mistakes 0-3; 30-60 s; one block per drag; a block leaves only through its own gate. The
  enhancer writes the gameplay in that legal form.
- Edits (core requirement 5): the planner reads an edit against the current brief, "THINGS IN THIS AD NOW" and the
  parts; pointers ("this asset", "swap this") resolve through the inventory or become an assumption. The enhancer gets
  the same inventory (`studio.planner_context`), starts the rewrite with what to keep, resolves an unambiguous pointer
  to the inventory's plain name, and asks when two things fit (never guesses).

**Case fit.** The PDF asks for a simple experience ("provide a prompt … generate … request a modification"), prompt
controls across eight areas, consistency and control, and it says the end user "should not need to understand
generative AI models". The enhancer is the honest version of the mock's "Auto-Optimize Prompt": it shows every change
with the user's words next to its own, never adds, and can always be undone. The trend ideas are an optional extra
(the PDF's "Extensibility: could this evolve into a larger creative production system?"); they do not touch the
workflows: an idea is a prompt text the user may edit and send, and that prompt goes through the same planner, the
same checks and the same review as any typed prompt.

## 2. The enhancer (`src/cbj/enhance.py`, `POST /api/enhance`, `cbj enhance`)

Pipeline: one model call (the planner's own backend, `llm.planner_client()`: Claude CLI or NVIDIA) with a system prompt
made of (a) the game in one paragraph and the list of what it does not have, (b) the eight controls with the words the
planner reads reliably (a digest of the prompt-controls skill and `planner.SYSTEM`), (c) the reference rules, (d) the
defaults, (e) the rewrite rules; then **checks in code** against the original with the engine's own readers:

| check | how | on failure |
|---|---|---|
| quoted captions kept word for word | `brief.QUOTED` on both texts; a quote may go only if a change entry of kind removed/replaced names it | re-ask once, then fall back |
| no added ask | `audit.asked(original)` vs `audit.asked(rewrite)` over 21 fact keys + new quotes; an added fact is allowed only when a change entry's `before` is in the user's text and its `after` carries the fact (a translation or a declared replacement) | re-ask once with the list, then fall back: the user's words stand, the model's additions survive as questions |
| no technical names | `brief.plain_text(rewrite) == rewrite` (field names, enum tokens, hex) | re-ask, fall back |
| model-added captions ≤ 6 words; no statistics / odds / IQ claims; no bullets | regex | re-ask, fall back |

Output: `prompt`, `changed`, `changes[{kind: clarified|translated|replaced|removed|reordered, before, after, why}]`,
`questions[{question, options}]` (≤ 3), `warnings`, `workflow` (from `app.workflow_of`, so the UI can say "will be read
as an image-guided creative"), `model`, `seconds`. The engine's planner and workflows are unchanged; the enhancer is a
pure function of the text plus, for an edit, the version's inventory.

**Live results (Claude opus, low effort, 7-20 s each):**

| request | result |
|---|---|
| "make a cool ad where a bomb explodes and clears the red blocks, super engaging, only 1% can solve it" | "Make an ad where one key move frees all the red blocks at once, so they leave one after another through their red gate, and the hook caption is "Can you beat it?"." Changes: bomb → key move (replaced, no bombs); 1% claim → dare (replaced, ad rules); "cool … super engaging" → questions (ending? pacing? look?). |
| "Zor bir seviye olsun, oyuncu son saniyede kazansın, 45 saniye, pembe bloklar" (Turkish) | "A hard level, with a near-fail ending where the player wins at the last second, solved with one second left. The ad is 45 seconds long, with pink blocks." Four translated changes, each quoting the Turkish words; questions: captions in Turkish or English? all blocks pink or one colour? |
| the brief's own prompt (narrow centre, almost fails) | unchanged; questions: how close the near-fail (1/2/3 s), the length, a hook of your own. |
| edit "swap this for the attached one" + hf_mascot_brick.png on 1015-074810 v1 | "Keep everything else exactly as it is (…), and replace one picture in the ad with the attached hf_mascot_brick.png." Question: which picture (the stopwatch beside the hook, the logo top-left, the stopwatch on the end card), read from the inventory. Read as an edit. |
| "same vibe as this pic, hard, 45s, make the blocks pop" + T8_retro_neon_arcade.png | "A hard level, 45 seconds long, with the same look and mood as the attached image …, used as a reference for its look and colours." "pop" → question (neon theme / colourful chunky blocks / zoom); read as image-guided. |

Before the justification rule, the Turkish request fell back to "unchanged" because the English audit could not see
its facts in the original; tying every added fact to a change entry whose `before` quotes the user's words fixed it
without opening the door to inventions (a `before` not in the request justifies nothing: tested).

## 3. Ideas from trends (`src/cbj/trends.py`, `POST /api/trends`, `cbj trends`) — optional

Signals: Google's daily trending searches (RSS, no key, region code) and Tavily news (`TAVILY_API_KEY`, four fixed
queries: gaming, culture, season, sport, plus the user's theme). Code filters first: an unsafe-word list (tragedy,
politics, religion, sex, violence, crime, health, named politicians) and a listicle filter. Then the planner's model
writes 4-6 ideas with the same vocabulary digest as the enhancer, under rules: use only the signals given; the ad's
copy never names a brand, title, team or person (the trend is the mood, the colours, the moment); map the trend to
the levers the game has (look, colours, background, caption tone, hook, ending, tempo, curve, length, format; a
sticker only as a note); skip unsafe and vague trends and say why. Each idea: title, trend, category, source (URL or
the exact search term), why now, mapping, hook, prompt (50-90 words, house style). Code checks every idea's prompt
like the enhancer does (no technical names, captions ≤ 6 words, no statistics, safe). Cached 6 h per day, region and
theme in `studio/_trends/`.

**Live run (18 Oct 2026, US, 31.6 s):** 8 trending searches + 14 news items → 4 ideas: a last-play college-football
finish → a hard narrow-centre near-fail with two seconds left and a hurry caption ("Down to the final seconds"); NFL
gameday → a fast clean cascade in black and gold ("Gameday speedrun. Ready?"); fall festivals / pumpkin spice → an
easy spacious calm solve in autumn colours with a note to attach a pumpkin sticker; a marathon weekend → a long
lanes board that speeds up and stops as a cliffhanger ("Can you finish strong?"). Skipped with reasons: a named
athlete's trade rumour, a named TV series, a hurricane, a gang-violence game, listicles.

**From a link (added later the same day).** `trends.from_link(url)`: the page
behind a public http(s) URL is the only signal (Tavily extract first, then a direct fetch with the tags stripped; local
and private addresses are refused before any fetch; 200 KB cap, 6000 characters kept; an unsafe page is refused), the
same model writes 1-3 ideas with the same checks, the source is forced to the URL, cached per URL. `cbj trends --link URL`,
`POST /api/trends {url}`, the card's *Read link*.

Nothing in the planner, `brief.py`, `studio.py`, the workflows or the evaluation changed for this feature. An idea only
becomes a creative when the user puts its prompt in the box and presses Generate; it is then planned, checked and
reviewed exactly like a typed prompt.

## 4. Files

- `src/cbj/enhance.py`, `src/cbj/trends.py`; `app.py` (`/api/enhance`, `/api/trends`, `meta.features`); `cli.py`
  (`cbj enhance`, `cbj trends`); `tests/test_enhance.py` (12), `tests/test_trends.py` (7); README sections; the skill
  `.claude/skills/cbj-prompt-enhancement`.
- Web (`web/`): the "Enhance prompt" button and the Enhanced card on Create and Edit; the collapsed "Start from a
  trend (optional)" card on Create; spec in `web/SPEC-ENHANCE.md`.
- `.env` needs `TAVILY_API_KEY` for the trends (the free tier is enough). Without it the
  trend card is hidden and `meta.features.trends` is false; the enhancer needs nothing new.

## 5. How to check

```
cd ~/cbj-work/cbj-creative
uv run pytest tests/test_enhance.py tests/test_trends.py -q          # 19 tests, no network, no model
CBJ_PLANNER=claude uv run cbj enhance "make a cool ad where a bomb clears the red blocks, only 1% can solve it"
CBJ_PLANNER=claude uv run cbj enhance "swap this for the attached one" --edit 1015-074810-create-a-hard-color-block --base 1 --upload hf_mascot_brick.png
CBJ_PLANNER=claude uv run cbj trends -n 4 [--theme halloween] [--refresh]
curl -s -X POST http://127.0.0.1:8765/api/enhance -H 'content-type: application/json' -d '{"prompt":"Zor bir seviye, 45 saniye"}'
```
On the site: type a prompt, press **Enhance prompt**, read the change list, tap a question option, press Generate;
open **Start from a trend (optional)**, press **Get ideas**, **Use this prompt**, then Enhance or Generate.

## 6. Limits, stated

- The facts guard reads the ORIGINAL with English tables; a translation is accepted on the model's word (its
  `before` must quote the user's text). A model that mistranslates a number would pass the guard only if the number
  also appears in its `before`; numbers are checked separately by the quote/number rule in the system prompt, not by
  code. Next step if it matters: a second cheap model pass that back-translates the rewrite and diffs the facts.
- Questions are the model's judgement of what matters; they are optional by design and capped at three.
- Trends depend on two free feeds; when both fail the call returns a plain error and the UI hides the card. Google
  Trends has no API: the RSS is undocumented and may change; the Tavily news search covers the gap.
- The link reader refuses local and private addresses, follows redirects by hand (each hop re-checked, three at most)
  and caps the download; it does not pin the connection to the resolved IP, so a hostile host that changes its DNS
  answer between the check and the fetch (DNS rebinding) is the remaining theoretical gap. The engine's own API is
  token-protected and the fetch only returns page text to the model, never to the caller.
- The enhancer does not run automatically before Generate (the user asked for an explicit step): a request that
  skips it is planned as before.
