# Image-guided creative generation: constraints and rules of the fourth workflow (2026-10-17)

Written after reading the brief page by page (14 pages), the Unity project
the publisher sent (`~/Downloads/CBJ`: `LevelData.cs`, `BlockData.cs` 7 colours, `ExitService.cs`, six levels, `Sprites/UI`), the
analysis `CASE-ANALYSIS-AND-WORKFLOW.md` §1 and §4.4, and the code as it stands (`imageref.py`, `reference.read_board`,
`workflows/guided.py`, `audit.reference_rows`). These rules govern a NEW workflow, `workflows/image_guided.py`: a prompt
plus a reference image becomes a new creative. The text workflow (`create.py`), the edit workflow (`edit.py`) and the
video-guided workflow (`guided.py`) are not changed by any of this (md5 before the work:
create ebb322d518d3a20c754e23832e6e5008, edit c92754cce2e1bbcf36dbc6a79a300f45, guided be50be32df27e7b49c2e98a1f670974f).

## 0. What the brief asks, in its own words

| page | what it says | what it means here |
|---|---|---|
| p.2 | "turns text, image, and video inputs into controllable 30-60 second CBJ creatives"; "keeping CBJ gameplay at the center"; the user "should not need to understand generative AI models" | always a 30-60 s creative played and filmed by the real game; one sentence plus one dropped picture |
| p.3 | prompt controls: level type, gameplay, difficulty/pacing, visual elements, concept, sequence, assets, elements that stay | the prompt's own controls always win over the picture |
| p.5 | "a visually interesting board", "a specific type of level" | a board in a picture is a legitimate source for the level's type |
| p.6 | images may be "visual references, assets to insert, style or composition references, inputs for modifying an existing creative"; "Use this object instead of the current obstacle"; "Create a CBJ creative inspired by this image"; "The system should understand the role of the provided image and incorporate it appropriately" | the FIRST decision is the image's role; each role takes something different; the role and what it gave are shown |
| p.7 | controlled editing: one change, nothing else | "use this object instead of the obstacle" on an EXISTING creative is the edit workflow, not this one |
| p.8 | "Consistency comes first": Unity for gameplay; AI for intent, planning, reference analysis, asset generation, visual transformation | the picture is read by a multimodal model; the board is generated and solved by the tool and played by Unity; no pixel of a reference picture is drawn into gameplay |
| p.10 | prompt + optional image → generate → review → modify → revised version | one prompt box, one drop zone, a result, the loop |
| p.11 | multimodal understanding; gameplay consistency; controllability; decision making | what the picture gave must be visible and explained; limits stated |
| p.12 | "at least one image-driven example"; "main limitations" | the 12-case set produces real examples; the reading's limits go in the report |
| p.13 | design around unreliable AI; focused > broad | measure the reading on images with a known truth before trusting it; judge only what is read reliably |

## 0b. The game, verified in `~/Downloads/CBJ/Assets` (2026-10-17), and what it means for a picture

| fact (file) | consequence for image-guided |
|---|---|
| `LevelData.cs`: `gridWidth`, `gridHeight`, `timerCount`, `inactiveCells`, `GridBlockDatas` (position, colour, `shapeOffsets`), `ExitDatas` (colour, pivot, `direction` Left/Right/Top/Bottom, span) | a board in a picture can only become: a grid size, wall/hole cells, polyomino blocks, coloured gates on the edges, a clock. Nothing else is a level field. |
| `BlockData.cs`: exactly 7 colours `Green, Yellow, Blue, Red, Orange, Purple, DarkGreen` | every colour read in a picture maps to one of these 7 slots; an 8th colour cannot exist; two read colours may not share a slot unless the request accepts it |
| block materials `Materials/BlockMaterials/*.mat` `_Color`: Red #FF3B2A, Orange #FF8000, Yellow #FFCC04, Green #14FF17, DarkGreen #065C13, Blue #146AFF, Purple #D007FD (violet-magenta) | colour mapping is by distance to THESE rendered colours (not to textbook names): pink/magenta is closest to Purple or Red, teal/mint to Green or DarkGreen, coral to Red, lavender to Purple; the mapping is shown |
| `GroundMaterial.mat` #ADD1E9 (pale blue background), `gridColors` #5E6A94 (cells) | "the game's own look" = this background; a look row for "not taken" measures against it |
| `ExitService.CanBlockExit` / `IsPathClear`: a block leaves only through a gate of ITS colour, only while dragged onto the gate's line, with a clear path; first matching gate in file order | gates in a picture are evidence of colours and sides only; the generator places gates where the block can reach (solvability is the tool's job, never the picture's) |
| `BlockMovementService` + `MovementSettings.asset` (`collisionPadding` 0.4 = 0.8-cell box, `dragSpeed` 20, `snapDuration` 0.1): free 2D drag, blocks never pass through each other or walls | a picture's "stuck" or "blocked" look is the game's own blocking; nothing to translate |
| `GameManager.HandleTimer` / `StartTimer`: the clock starts at the first touch, `ShowFail` at 0; `OnBlockExited` → `ShowWin` when no block is left | the ending is a game event, never a picture; a clock shown in a screenshot is a value, not an ending |
| `UIManager.UpdateTimer`: below 0:50 the clock punches red each second; `UpdateLevel` shows the level number | a HUD read in a screenshot gives a level number and a clock value only |
| `LevelManager`: levels from `Levels/*.json`; a level not loaded by number shows `-1` | a generated level needs a label; a badge number read in a picture can be that label only when asked |
| `Levels/Level_01..06.json`: 4x5 to 6x6, 2-8 blocks, all timers 300 s, no holes, pieces of 2-4 cells | the shipped levels are small; a picture's 14-block board is beyond them and beyond the generator's spoken range (below) |
| `CameraController.FitBoardToScreen`: the camera fits the whole board with padding | a picture's zoom/framing is not copied; the board is always fully visible |
| no other mechanic exists in the scripts (no ice, keys, chains, bubbles, boosters, bombs, moving walls, characters on the board, doors that open) | anything like that in a picture is listed "not used: not in CBJ" |

The tool's generator (`cbj-creative/src/cbj/generate.py`, skill `cbj-level-gameplay`): 7 shapes `open, narrow_center
(hourglass), door (two rooms joined by a gap), holes (separate wall cells), cross (corners cut away), ring (a big hole in
the middle), lanes`; pieces `small, long, big, mixed, varied`; looks `symmetric, packed (55-75 % filled), colourful,
spacious`; width 4-9, height 4-10; blocks 2-10 when asked, up to `MAX_BLOCKS` 12 on a packed board with no count. So the
picture-to-level map is: hourglass/waist → narrow_center; two rooms → door; rooms split by walls (more than two) → door or
holes, said; separate wall cells → holes; plus/cross → cross (a centre wall cell on a cross is not a shape the generator
combines: said); ring/frame → ring; columns → lanes; plain rectangle → open. A count, size or shape beyond these is clamped
and the plan says "<seen> -> <built>: <why>".

## 1. The rules

I1. **Input is a prompt plus an image; the prompt says what to take.** A picture is never read without words (p.10).
A prompt that names nothing about the picture ("inspired by this image") reads it for its concept: for a board
screenshot that is the board's type and the look; for any other picture (a photo, an illustration) the look only.

I2. **The role comes first, decided from the words and the reading together, and is shown.** Roles (p.6): `style`
(the look: background, captions, optionally block colours), `board` (composition: the level's type from a board in
the picture), `asset` (the picture is placed: logo, sticker, end card, button, cursor), `modify` (the picture replaces
the obstacle or skins a block). A picture can have two roles ("its neon look and a board like this"). A picture with
edit words on an existing creative goes to the edit workflow; a picture only to place, with no reference words, stays in
the text workflow (as today). Everything else with a picture and reference words ("like this", "inspired by", "this
image/picture/screenshot/board", "take/use the ... of/from this") comes here. A video, with or without a picture, stays
in the video-guided workflow.

I3. **Plan the reading from the prompt, read with Opus, then the board on its own** (the owner, 2026-10-17). Before the picture is read, the planner's text model writes an image reading plan from the prompt alone (focus, the questions the request needs answered, what to ignore, what the prompt fixes); Opus (Claude, `llm.ClaudeCliVision`) then reads the picture with the general reading plus the plan's questions as the user's priorities, in strict JSON; Gemini 3.5 Flash-Lite, then NVIDIA, are the fallback when Claude is not available. The plan narrows what is applied, never what is read. The general reading: what it shows, whether it is Color
Block Jam (its HUD: "Level n", "Time mm:ss"), the board, the look (background top/bottom, board, caption colours), the
captions' text, the HUD shown or not, anything the game does not have. Then the board is read on a full-resolution
crop with code measures beside the model (the video path's `read_board` rules, applied to the picture as the still):
symmetry by the block mask against its mirrors, the colour count from clusters confirmed by read names, the size as
the median of several reads, the fill as the share of cells under blocks. The palette is measured in code (PIL), never
taken from the model's words alone.

I4. **The prompt's own values win.** A stated length, ending, difficulty, block count, colours, caption text, look,
HUD choice or tempo is never replaced by the picture (p.3, p.11).

I5. **Take what the request names; fill only the board; "only X" takes just X.** When the role includes `board`, the
level's type (shape, size, blocks, colours, pieces, symmetric/packed look) comes from the board part by part, each only
where the request states nothing. The look is taken only when the request asks for it (style words). "Keep the game's
own colours/look/background" keeps them. "Only the background" takes the background alone: no captions, no blocks.
What was filled (not asked) is marked "filled from the image" and its rows are info, not misses.

I6. **Colours go to the game's seven slots; the mapping is shown.** Each distinct block colour read on the board is
mapped to the nearest free game colour ("pink -> red: the game has no pink"). Repainting the blocks (display colours)
happens only when the request asks for the picture's block colours or its palette "on everything / the blocks too";
then the display colour keeps the picture's hue and is contrast-checked against the board and the background. Caption
colours are contrast-checked (>= 3:1) against the background they sit on.

I7. **The board is counted on the board, never from the caption.** Caption text in the picture is evidence of the
creative's idea, not a fact about the board (pic_x says "12 blocks" and shows 14). When they disagree, the board wins
and the plan says so.

I8. **Clamp to what the generator builds, and say it.** Sizes 3..12 a side, blocks up to `generate.MAX_BLOCKS` and what
fits the ad's length; a shape the generator has no word for (four rooms split by walls) goes to the closest shape it
builds (walls / holes / cross / two rooms), with the line "<what the picture shows> -> <what the tool builds>: <why>".

I9. **Translate, never copy.** No pixel of a reference picture enters the creative (unless its role is asset or modify,
then only in that slot); the caption text is not reused unless the request quotes it or asks for "the same words"; the
exact cells are never copied (the level is generated in that spirit, solved by the tool's own rules and filmed by Unity).
Things the game does not have are listed as "<it>: not used: not in CBJ".

I9b. **The board itself, when the picture is the game (2026-10-19).** The owner's test ("create a similar game concept, just
use one more color" on a level screenshot) showed that a designer who attaches a board expects THAT board, not a new one
of its type. So, when the picture is a CBJ board and the board role is on, the board is read cell by cell
(`imagecells`), verified against the pixels, built into the game's level JSON, solved, and played as read; the request's
changes on it (a colour more or fewer, a recolour, a mirror) are applied in code and said; a board drawn unplayable gets
the smallest gate repair, said; thin walls become wall cells. "A new board of this type" keeps I9's type generation. I9's
"never copy" still holds for the picture's pixels and its captions' words.

I10. **The screen.** The HUD is hidden only when the request asks for it or asks for the picture's screen/look and the
picture shows none. For a CBJ screenshot, the badge's level number and the clock go to the creative only when
the request asks for "the same level number/clock" or leaves the label open and asks for the screen.

I11. **The ending is the prompt's.** A picture has no ending. The ending, mistakes, finish and length come from the
words (defaults as in the text workflow). No caption may claim what the ending does not show (the guided workflow's
caption fit is reused).

I12. **30-60 s, gameplay at the centre.** The shared engine's filling rules apply as in the text workflow.

I13. **One evaluation for this workflow, one loop.** The image profile = the text profile + the image rows:
- the role (info) and what was taken / not taken (info);
- the board (when taken): shape class, size within one cell (or the stated clamp), blocks within two (or the clamp),
  each read colour present (by slot), symmetric when the picture is, packed when the fill is >= 60 %, piece size class
  (small / big) - measured on the made `level.json`;
- the look (when taken): the made background and caption colours, measured on the made poster/first frame pixels, match
  the kit (each colour within a small distance) and the kit follows the picture's measured palette; caption contrast;
  when the look is NOT taken, the background is the game's own;
- the screen: HUD shown/hidden as asked;
- nothing copied: no reference pixels outside an asset slot, no caption text reused unless asked.
Misses feed the revise loop at most twice; the final version is the best one (fewest misses, then the viewer's ship),
not the last. A row the loop cannot fix is reported.

I14. **Only what is read reliably is judged.** The reading's accuracy is measured on the four test pictures against the
hand truth (`req3-image-guided-2026-10-17/TRUTH.md`) before the creative set runs. A field that is not reliable is info
only and said so in the report.

I15. **Nothing is generated by a media model inside the workflow.** The four test pictures were made with Higgsfield
outside the tool, from the tool's own creatives (8 credits). The workflow's only model calls are the planner's text
model (the brief), the image reader (Opus first, reading for the prompt's plan; Gemini 3.5 Flash-Lite, then NVIDIA build's
multimodal model as the fallback) and the viewer's review.

I16. **Kept apart.** New files only for the logic (`workflows/image_guided.py`, an image-reading module, an image
evaluation module, a skill `cbj-image-guided`); shared files get additive changes only (the dispatch in `app.py` and
the workflows note). The three existing workflows stay byte-identical (md5 above), the existing tests stay green.

## 2. The test (brief p.12 + the owner's ask)

Four pictures made from the tool's own creatives, one change each (colours, block count, board design, look + screen),
neutral names `pic_w..pic_z`; 12 prompts, 3 per picture, the four endings 3 times each
(`req3-image-guided-2026-10-17/PROMPTS.md`). Order: (1) reading accuracy on the four pictures vs TRUTH.md; (2) the
12 cases end to end with the review and the loop on; (3) findings, fixes, rerun of the failed cases; (4) the report.
