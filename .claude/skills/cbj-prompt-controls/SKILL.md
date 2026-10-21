---
name: cbj-prompt-controls
description: The brief's eight prompt controls for a CBJ ad (type or structure of the level, gameplay behaviour, difficulty or pacing, visual elements, creative concept, sequence of events, assets to use, elements that should remain unchanged) as cbj-creative reads them into a brief - the vocabulary each control understands, its defaults, the concept-to-gameplay mapping, what must not be invented, and the limits the tool answers with "adjusted" or "not supported". Use when improving or completing a user's prompt before planning, when reading a prompt into a brief, when explaining a plan row to a marketer, or when writing test prompts that the game and the tool can honour.
metadata:
  spec-version: "1"
  last-verified: "2026-10-19"
---

# The eight prompt controls

## 1. Purpose
A prompt is read by a language model into a typed brief, and code makes the ad from the brief. The model may only fill
what the prompt says; everything else keeps a default (a new ad) or its current value (an edit). An agent that improves
a user's prompt must therefore (a) say the things the user means in words the planner reads reliably and (b) add
nothing the user did not ask for. This skill is the shared vocabulary.

## 2. Source of truth
- `src/cbj/planner.py` `SYSTEM` (the planner's instructions; the vocabulary below is a digest of it) and the post-rules
  in `plan()`; `src/cbj/brief.py` `SCHEMA`, `GROUPS`, `PRONE`, `check()`.
- `docs/ENGINE-NOTES.md` (the former root README) "Text to creative" (the controls table) and "Length".
- Full example prompts that cover all eight controls: [references/full-prompt-examples.md](references/full-prompt-examples.md).
- Rules of the game: `cbj-game-rules`. Gameplay vocabulary in depth: `cbj-level-gameplay`. Edits: `cbj-controlled-editing`.

## 3. Facts
**The controls and what each one drives**

| # | control | words the planner reads | brief fields | engine |
|---|---|---|---|---|
| 1 | type or structure of the level | board shape (open, narrow centre / hourglass / bottleneck, two rooms with a door, holes / pillars, cross, ring, lanes), size ("6x8", "big board"), number of blocks, piece shapes (small, big / chunky, long bars, varied / L-shaped), looks (symmetric, packed / crowded, colourful, spacious: "enough free space", "room to move"), the colours the board may use, the HUD level number, how many moves the solution takes | `level.*` | the level generator, or a shipped level (1-6, all easy) |
| 2 | gameplay behaviour | the ending (clean win, near-fail, cliffhanger, time-out), mistakes and their kind (blocked, wrong way, fidget), hesitations, an ORDER of interactions with a sequencing word (first, then, last, before), a satisfying finish / cascade / "one move frees everything", seconds left at a near-fail | `gameplay.*`, `channel` | the scenario planner, recorded in the real game |
| 3 | difficulty or pacing | easy / medium / hard, relaxing / rage / speedrun, length in seconds (30-60), tempo (calm, normal, fast), a pacing curve (speeds up, slows down), the clock's start value | `level.difficulty`, `pacing.*`, `gameplay.timer_s` | difficulty band of the generator; pauses in the recording |
| 4 | visual elements | a theme (game, candy, pastel, neon, dark, custom), block colours by name ("pink blocks"), the background behind the board (colours or an attached picture), the board's cell colour, caption colours (all or one caption), a zoom, a timed punch-in, the cursor (ring, hand, none), hiding the clock or level badge, the aspect ratio | `visuals.*`, `format` | the recorder repaints the game's materials; the compositor styles the rest |
| 5 | creative concept | the angle, the hook, each caption (mistake, fix, hurry, cascade, result), the end card's title, fact and button text, the language | `concept.*`, `language` | the ad's texts (defaults translated in other languages) |
| 6 | sequence of events | standard or result-first, with or without the slow-motion replay, the game's result screen, the length of the still opening frame and of the held result, moving a caption's entrance or exit | `sequence.*` | the ad's parts |
| 7 | assets to use | an attached picture and where it goes (a logo or sticker in the top-left corner, a sticker in the top-right corner, the icon beside the hook, end-card picture, end-card background, button, cursor), the game's own pictures by file name (coin pile, stopwatch, the blue toy-brick start background behind the board or on the end card, the green button, the banners), removing a picture, sound effects on/off, an attached music file | `assets[]`, `audio.*` | image layers, cursor, end card, the music stem |
| 8 | elements that should remain unchanged | "keep everything else", a list of what must stay (level, gameplay, timing, camera, visuals, copy, sequence, assets, sound) | `keep[]` + the edit whitelist | an edit changes only the groups the prompt asks about |

**Defaults when the prompt says nothing.** Channel network; English; 9:16; the tool's showcase level (hard narrow
centre) unless structure, size, colours or difficulty are given (then generated); ending near-fail; 30 s; tempo normal;
curve even; the game's own look; white captions with a purple outline; ring cursor; HUD shown; standard sequence with
replay, result screen and end card; no uploads used; sound effects on; no music. The ad always opens on motion: at most 0.5 s of frozen first frame.

**Concept to gameplay (the planner's own table).** relaxing / calm / ASMR / oddly satisfying: clean win, easy, streak
finish, calm tempo. "a satisfying solve": win + streak. rage / frustrating / almost impossible: hard, near-fail, 2
mistakes. speedrun / pro player / fast: win, fast, streak, 0 mistakes. "can you solve it?" / "what's the move?":
cliffhanger. tension / against the clock: near-fail, speeds up. for beginners or kids: easy, win, calm. The planner
writes which words it read that way in its assumptions.

**Reading rules that decide a lot**
- A colour that LIMITS the board ("only red, blue and yellow") is a level colour; a colour that POINTS at a block ("the
  red block gets stuck") belongs to the event, not to the board's colours.
- A colour the game does not have (pink, teal, mint) is the nearest slot repainted and named; captions then use the name.
- An order of interactions needs a sequencing word; "first-time player", "exit doors", "blocks" are not an order.
- Words about free space ("enough free space for movement", "room to move", "plenty of empty space") are the board's
  look (spacious: few blocks, none touching), not only a difficulty cue; code adds the look even if the model forgot.
- "Five colored blocks" is five blocks, in any colours; but "colored / colourful blocks" is talk about colours, so in
  an edit it releases an earlier palette limit instead of keeping it (`brief._evidence`, 2026-10-15). A prompt that
  starts "Create a ... level" typed into an open creative is still an EDIT: everything it does not mention stays
  (the UI's banner says so); press New for a fresh creative.
- A stuck step may name the block in the way: "blue stops because a red block blocks the route" -> {blue, stuck,
  first, by: red}; the play picks the attempt a red block stops when the board offers one, the board search wants
  one, and the Mistakes check says "asked: stopped by a red block" (`events.Event.by`, 2026-10-15).
- "Six colored blocks" with no palette named = six blocks, each its own colour (`planner._coloured_count`); on a
  mirrored board pairs share a colour, so the row says how many colours it can show instead.
- An EDIT that opens "Create / make / build a ... level" describes a new level: level settings it does not mention
  (size, colours, pieces, look, moves) go back to defaults and a look word the prompt lacks (symmetric, packed) is
  dropped (`planner._fresh_level`); captions, pictures and the ad's other parts still stay.
- "First moving a blocking piece aside, then clearing the blocks": the move aside is the video's FIRST drag
  (`when: first`), not a move somewhere before the exits (`planner._first_aside`).
- "Harder" / "easier" is difficulty, never a board change list; "make the hook harder to ignore" is about the hook.
- "The background behind the board" is never the board's cells; the end card's background is a separate asset role.
- "Use this object instead of the current obstacle" / "put this on the walls": the attached picture gets the obstacle
  role and is drawn on the board's walls (the game's holes) in perspective during the play; a board without walls puts
  it beside the hook and says so (`planner._obstacle_picture`, `compose.cell_quads`).
- "Apply this texture / picture to the blue block": the attached picture gets the skin role with that block colour and
  is composited on that block on every gameplay frame (`planner._skin_on_a_block`, `compose.block_quads`); on a door
  or a gate it stays refused, and without a block colour nothing is placed.
- A reference video is read for the request (see "A reference video" below); the game's name stays the end card's
  title and a level number seen in the clip goes to the badge (`planner._reference_carries`).
- "Still / static / frozen opening frame" is the intro length, not the result-first sequence.
- Shorter than 30 s is raised to 30 with a note; 30-60 s is honoured.
- Captions under 6 words; numbers in copy only from measured facts ({clock_left}, {time_used}, {blocks_left}...); no
  statistics, odds, percentages, rankings or IQ claims (ad rules): the planner writes the closest honest dare instead.
- An uploaded file is used only when the prompt refers to it (by name, "our logo", "the attached picture"); a file the
  prompt names but did not attach stops the make with a question (`needs`: attach, or make without), never guessed
  from earlier uploads; a reference video is never an asset.
- "CBJ" in a prompt is the game's name, not a request for a jam-packed board.

**An attached image's role (brief p.6, `imageref.py`, 2026-10-15).** style (a measured style kit: background from the two
dominant soft colours, captions contrast-checked, blocks mapped to the game's slots by hue only when the words want the
blocks or the whole look and the image has 2+ distinct hues; "inspired by", "use its colours", "design transfer", "same
style"), composition (a board the model read becomes the level spec: size, blocks, colours, packed/spacious/symmetric,
walled; generated in that spirit, never copied cell by cell; "a game like that", "a level like this board"; a picture
that is not a board falls back to style), asset (placement rules), modify (obstacle, texture). The role and what was
taken are in `planner.references[i].role` and the assumptions; the visuals / level row says it.

**A reference video (core requirement 4, `videoref.py`, 2026-10-16).** A prompt plus a video (or a reference image) is
the guided workflow (`workflows/guided.py`). The prompt's words decide what the video is read for (the focus): "version of
this concept", "adapt", "same idea" or no words about it = concept (everything but the look); "hook", "opening" = hook;
"pacing", "tempo", "speed" = pacing; "captions", "what it says" = captions; "ending", "how it ends", "the payoff" =
ending; "look", "style", "colours", "palette", "mood" = look; "structure", "sequence", "the parts" = structure. Only the
fields of the focus are taken (concept: ending, mistakes, finish, tempo, curve, length, replay, end card, the hook's
function and the captions' functions in the tool's own words; look: background and caption colours, never the blocks;
the pacing is read only approximately, from a sampled reading, and its row is judged only when the request asks about
the pacing),
and anything the prompt states itself wins (a length, an ending, "no replay", a quoted hook). To keep the reference's
exact caption text, say "same text" / "same captions". Mechanics the game lacks are translated (ice, keys, merge,
boosters or bombs) and listed in the assumptions. After planning, the Create side's "Reference to creative" card shows
the reading plan, the parts timeline, the confidence, what was adapted and what was not copied; the version is then
judged with the "Reference: ..." rows (`audit.reference_rows`: ending, pacing, hook, purposes in order, part lengths,
captions, look, nothing copied, confidence). To get a targeted read, name the aspect ("use its hook and pacing");
"ignore the video" makes the planner read nothing from it.

**Statuses a plan row can have.** applied (asked and done), default (not mentioned), adjusted (asked, changed to what the
game can do, with the reason), not_supported (asked, impossible here, with the reason). Nothing is dropped silently.

**Common to every workflow (2026-10-19).** The translation once, the rules rows and the shared case rows on every version,
the best version kept, the stated values kept, the length guard, the viewer-only rule, the repeated-miss limit, the fixed
board's pace said at plan time, the kept log lines, the feedback step and the report: listed once in `cbj-creative-evidence`
section 3 ("Common to every workflow") and in `src/cbj/workflows/__init__.py`.

## 4. Procedure
To improve a user's prompt before it is planned:
1. Keep the user's own words for everything they did ask; the plan's "asked" column quotes the request.
2. Walk the eight controls. For each one the user touched, restate it in the vocabulary above (one short sentence each,
   in the table's order). For each one they did not touch, write nothing: a default is not an ask, and adding one
   changes what the user gets.
3. Replace game-impossible asks (section 5 and `cbj-game-rules` section 5) with the closest possible thing and keep a
   note of the swap for the user; never silently drop the ask.
4. Make the gameplay ask legal: one block per drag, exits only through matching gates, an order expressed with
   sequencing words, mistakes 0-3, near-fail seconds 1-3, one level per ad.
5. Name attached files as the prompt refers to them and say where each goes; say "no music" or attach a track.
6. Keep every caption under 6 words and free of statistics; give the length in seconds if the user cares (30-60).
7. For an edit, start with what to keep ("keep everything else exactly as it is") and name only the change; see
   `cbj-controlled-editing`.
8. Read the result back as the planner would: could any sentence be read as a second ask? Remove the ambiguity.

To judge a plan: every row's status must be one of the four, "asked" must be an excerpt of the request, and no field
outside the declared groups may differ from the default (new ad) or the parent (edit).

## 5. Not possible here
Anything in `cbj-game-rules` section 5 (mechanics the game lacks). Also, in the tool: more than one level in one ad;
two blocks leaving at once; choosing a gate side; board regions ("clear the left half first"); 3D characters or
real people; another game; voice-over; a sound effect replaced by a file (effects are made in code); a texture, sprite
or picture on a block or a door; an icon inside the button (the button is replaced whole); confetti art; a ribbon or
border overlay; dissolves or wipes between parts (parts cut directly). The planner marks these not_supported with the
reason and still makes the rest of the ad.

## 6. Evidence
- `uv run cbj plan "<prompt>"` prints the eight rows, the assumptions and the summary without making the ad; in the UI
  the *Plan* button does the same, *Level only* also builds the level and the move list in seconds.
- `brief.json` of a version holds the brief; `brief.planner` holds the model, time, prompt and reference notes.
- Tests: `tests/test_text_to_creative.py`, `tests/test_case_fixes.py` (the 36 natural-language cases of 2026-10-13),
  `tests/test_control_cases.py` (the 34 control cases of 2026-10-14), `tests/test_videoref.py` (the video's focus words,
  what each focus sets, the request winning, the reference rows).

## 7. Change rules
When a field, a group, a default or a reading rule changes in `brief.py` or `planner.SYSTEM`, change the matching line
here (and the example prompts if they use it) in the same edit and bump `last-verified`. The five example prompts are
the ones shown as chips in the UI (`src/cbj/static/index.html`): keep both copies identical.
