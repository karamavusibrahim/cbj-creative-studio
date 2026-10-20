# cbj-creative

Tooling for generating Color Block Jam ad creatives. This first part is the
deterministic gameplay core: a level model that reads the game's own JSON, the
game's exit and movement rules ported from the Unity C#, and a solver that finds
the minimum number of drags that clears a level.

## Setup

```
uv sync
uv run pytest
```

Python 3.12. Recording videos also needs ffmpeg on PATH and Unity 6000.3.5f1 (see
"Recording in the real game"). The prompt planner needs an NVIDIA API key (build.nvidia.com),
in the environment or in a `.env` file in this folder (git-ignored): `NVIDIA_API_KEY=...`. A reference video is
read by Gemini first (`GEMINI_API_KEY=...`, a Google AI Studio key; see "Video-guided generation" for its free-tier
terms); without that key, or when Gemini fails, NVIDIA build reads it.

**Planning with Claude Code instead.** On a machine where the Claude Code CLI is installed and
logged in, `CBJ_PLANNER=claude` (in the environment or in `.env`) makes the planner run
`claude -p` as a subprocess, with structured output against the same brief schema, on the CLI's
own login and usage limit: no API key. Default `claude` is Opus at low effort (a brief in about
15-25 s); `CBJ_PLANNER=claude:sonnet` or `claude:opus:medium` pick another model or effort.
Reference images are read by the CLI too (its Read tool); a reference video is read by Gemini
(`GEMINI_API_KEY`) or NVIDIA build (`NVIDIA_API_KEY`), since the CLI does not read video. Each call runs bare: no MCP servers,
settings or memory of the machine's Claude Code setup go in (their tool catalogue alone would be
200k+ tokens a call). The UI footer says which planner is on. `llm.py` holds the switch.

## Commands

Agent skills (the game's rules, the eight prompt controls, level and gameplay generation, controlled
editing, evidence) live in `.claude/skills/`; see `AGENTS.md`.

```
uv run cbj show  data/levels/Level_03.json                  # draw the board
uv run cbj solve data/levels/Level_03.json                  # minimum-drag solution, step by step
uv run cbj solve data/levels/Level_03.json --json out.json  # also write the move script
uv run cbj table data/levels --md reports/solve_table.md --scripts data/solutions
uv run cbj difficulty data/levels                           # how hard: minimum solution + a naive player
uv run cbj check data/levels/Level_03.json data/solutions/Level_03.moves.json  # verify a move script
uv run cbj build-player                                     # once: build the Unity recording player
uv run cbj render data/levels/Level_03.json data/solutions/Level_03.moves.json  # record it in the game
uv run cbj compare renders/Level_03 renders/Level_03_b       # how close two recordings are
uv run cbj scenario data/levels/gen/narrow_center_01.json --ending near_fail   # human play toward an ending
uv run cbj scenario data/levels/gen/narrow_center_01.json --ending win --finish streak --plan-only  # one key move, then all leave
uv run cbj generate --shape ring --difficulty hard --pieces big -o levels/ring.json   # a level to a spec, plus a picture
uv run cbj rerun renders/nc01_near_fail -o renders/nc01_again   # record a folder again from its files, and compare
uv run cbj ad renders/nc01_near_fail                          # a finished 30 s ad from a recording
uv run cbj compose ads/nc01_near_fail_30s/ad.json -o ads/edited  # render an (edited) ad.json
uv run cbj ad-diff ads/nc01_near_fail_30s ads/edited             # what the edit changed, and nothing else
uv run cbj ui                                                 # the test UI: prompts in, ads out (port 8765)
scripts/engine-online.sh                                      # put the engine behind the deployed site (tunnel + Vercel env), see "The website"
uv run cbj plan "a hard level with a narrow centre, the player almost fails"   # what a prompt means
uv run cbj make "the same prompt"                             # plan it and make the ad (studio/<id>/v1)
uv run cbj make "keep everything, but the hook says 'Beat this!'" --edit <id>  # an edit: v2, with the proof
uv run cbj enhance "a tense ad, a bomb clears the red blocks"   # the prompt in the planner's words + questions, nothing added
uv run cbj trends --theme halloween -n 4                      # optional: ideas from today's trends, as prompts
uv run cbj feedback --md > feedback.md                        # what designers reported (records with the scene they looked at)
uv run cbj lessons --distill                                  # the records distilled into a versioned LESSONS.md for the owner
uv run cbj soundtrack <id> --voice                            # optional: a music bed from the version's own concept, the hook spoken (Magpie)
```

Errors print one line, `cbj: <reason>`, and exit with code 1.

Boards print with 1-based columns (`c1..`) and rows (`r1..`) from the bottom-left,
matching what you see in Unity. Gates are drawn on the edges: `^B` is a blue gate
on the top edge, `vY` yellow on the bottom, `R<` red on the left, `>O` orange on the right.

## Results on the six shipped levels

| level | grid | blocks | min drags | extra drags | cells dragged |
|---|---|---|---|---|---|
| Level_01 | 4x5 | 2 | 2 | 0 | 2 |
| Level_02 | 5x5 | 2 | 2 | 0 | 4 |
| Level_03 | 5x6 | 3 | 3 | 0 | 5 |
| Level_04 | 5x6 | 3 | 4 | 1 | 16 |
| Level_05 | 5x6 | 5 | 5 | 0 | 15 |
| Level_06 | 6x6 | 8 | 8 | 0 | 24 |

"Extra drags" are drags that move a block out of the way instead of exiting it.

## Difficulty

`cbj difficulty` adds two kinds of numbers. From the solver: minimum drags,
repositioning drags, how many blocks can leave with their first drag, and how
many different first drags there are. From a simulated naive player (the
"simulated human" idea used to rate puzzle difficulty): it takes an exit
whenever one is available, otherwise drags a random block to a random reachable
cell where the board has not been before (a person does not go back to a position
they already tried), 200 seeded runs. It gives up after 12 drags per block; the mean
is over the runs that finished, and the ones that gave up are counted apart.

| level | min drags | extra drags | exits at start | naive player mean (p90) |
|---|---|---|---|---|
| Level_01 | 2 | 0 | 2 | 2.0 (2) |
| Level_02 | 2 | 0 | 2 | 2.0 (2) |
| Level_03 | 3 | 0 | 2 | 3.0 (3) |
| Level_04 | 4 | 1 | 0 | 5.0 (6) |
| Level_05 | 5 | 0 | 2 | 5.0 (5) |
| Level_06 | 8 | 0 | 4 | 8.0 (8) |

The shipped levels are tutorial-easy: on five of them an exit is always
available, so even the naive player never wastes a drag. Only Level 4 needs a
block moved out of the way first. A "difficult level" request therefore needs
generated levels. No easy/hard labels are assigned; those need calibration
against real player data. The naive player's wasted drags are also the
believable mistakes a near-fail creative can show. `solve(level, start=...)`
solves from any mid-game position.

## Rules as implemented (from the Unity source)

| Rule | C# source |
|---|---|
| A block covers its pivot plus its shape offsets; an empty offset list means one cell, and (0,0) is always added | `Block.Initialize` |
| A position is valid when every block cell is on the board, active, and not held by another block | `BlockMovementService.IsPositionValid` |
| Exit check: the first gate in list order with the block's colour that overlaps the block is chosen; every block cell then needs a clear straight lane to the edge, leaving through the gate's columns (top/bottom) or rows (left/right) | `ExitService.FindMatchingExit`, `IsPathClear` |
| Inactive cells do not block an exit lane | `IsPathClear` only fails on a cell holding another block; inactive cells are null |
| The exit check runs only while a block is dragged, each time its pivot enters a different cell; the first such cell where it passes ends the drag | `InputHandler.DragBlock` |
| A block already standing at its gate does not leave by itself | same; releasing never triggers an exit |
| The order of gates in the file matters: a block touching two gates of its colour is only tested against the first | `FindMatchingExit` (test: `test_gate_order_in_the_file_changes_the_minimum`) |
| A gate may sit on the outer edge or on the rim of a hole | `GridManager.NeedsBorder` treats an inactive neighbour as an edge |
| One gate per cell side (`validate` rejects two) | the Level Editor's `ToggleExitCell` replaces an existing gate on that side |

A move in the solver is one drag: the block's pivot walks through 4-adjacent valid
positions and either stops anywhere or exits at the first cell where the check passes.
The game's collision box is 0.8 of a cell (`collisionPadding` 0.4), so 1-cell
corridors are passable and corners cannot be cut; the cell model reaches exactly
the positions the game reaches.

The solver is breadth-first search with one shortcut: when a block can exit, it
takes that exit first. This is safe because removing a block never blocks anything
else. The tests compare it against the full search on the shipped levels and on
637 random boards, all buildable in the Level Editor: 250 simple ones and 387 richer
ones (206 with holes, 73 with a gate on the rim of a hole, 273 with a repeated colour).

**Rule for the Unity replay.** The game checks for an exit once per frame, when the
block's rounded pivot cell changes, so a fast or diagonal drag can skip a cell.
A scripted replay must move one cell at a time along an axis and let the pivot
settle on each cell before the next step. After an exit, the block's cells are
freed when the 0.1 s snap ends (`PerformExit`), so the next drag must start after
that; the slide out takes longer but only delays the win screen.

## Failure handling

Fable 5.1 attacked the system with 101 bad inputs (broken files, impossible and
unsolvable levels, edge sizes, huge boards, illegal and tampered move scripts,
CLI misuse). The fixes that came out of it:

- Level files are parsed strictly. Missing fields, wrong types (`"4"`, `4.5`,
  `true`), unknown colours or directions, and non-JSON files raise a `ValueError`
  that names the file and the field. Nothing is silently coerced.
- `validate` also rejects boards larger than the Level Editor's 12x12.
- `solve` rejects a bad `max_states`, and stops with `SolverLimitError` when more
  than `max_states` positions are stored or a single drag reaches more than
  max(`max_states`, 144) cells. 144 is a full 12x12 board, so the second limit
  never changes a real level's result; it only stops a huge board from stalling.
- `replay` rejects anything that is not a well-formed drag; `script_to_drags`
  reads a saved move script.
- Files with a UTF-8 byte-order mark load; JSON nested too deeply or with
  integers too long to parse is a `ValueError` naming the file.
- `cbj check` refuses a move script made for a different level.
- The CLI never shows a Python traceback for bad input. `cbj table` reports a
  bad file as an `ERROR` row and keeps going, and prints the table before
  writing any files.

`tests/test_failure_modes.py` holds 71 tests. The first 60 came from the
adversarial run: 38 failed on the code before the fixes, and 6 more test the
move-script reader that did not exist yet. A third Fable review found a crash on
deeply nested JSON and five smaller issues; the last 11 tests cover those, and
10 of them fail on the code before that round.

## Recording in the real game (Unity CreativeRunner)

`cbj render` plays a move script in the real game and records it as a 1080x1920,
30 fps video. The game's rule code is untouched: the level is the game's own
LevelData, and every drag goes through the game's own `BlockMovementService`,
`BlockGridService` and `ExitService`, one frame at a time, exactly as
`InputHandler` drives them from the mouse. What the runner does change is
listed here:
- the mouse is a scripted finger;
- the camera is re-fitted for the 9:16 frame;
- the HUD is drawn through the camera at a phone's scale;
- button fades are instant and particle seeds fixed, for repeatability;
- the level badge shows the level's number.

The build also applies a small game patch (below) to its copy of the project.

```
uv run cbj build-player     # ~35 s; needs Unity 6000.3.5f1 and the project at ../CBJ
uv run cbj render data/levels/Level_03.json data/solutions/Level_03.moves.json
uv run cbj render data/levels/Level_05.json                  # no script: solve, then record
uv run cbj render LEVEL MOVES --end cut --drags 2            # stop after drag 2 (cliffhanger)
uv run cbj render LEVEL MOVES --end fail --drags 2           # wait for the timer to run out
uv run cbj render LEVEL MOVES --speed 2 --pause 1.6 --start-hold 2.5 --end-hold 3   # slower, longer
uv run cbj render LEVEL MOVES --zoom 1.1 --pan-y -0.5 --intro  # framing; --intro eases in from pulled back
uv run cbj render LEVEL MOVES --timer 20 --hide RestartButton  # clock override, hide a HUD part
uv run cbj build-player --stock && uv run cbj render LEVEL MOVES --stock  # the game as shipped, unpatched
```

Length: the shipped levels record in 5-13 s at the default pacing; Level 6 at
`--speed 2 --pause 1.6` records 29.3 s (in 42 s). A 30-60 s ad comes from slower
pacing, bigger generated levels, several levels, and the hook and end card.

Camera: zoom 1 is the game's own framing. Above about 1.1, a board that already
fills the width loses its side gates. Changing only the camera leaves the game
identical: `cbj compare` then reports the same game state with a different
finger path on screen and different pixels.

**The game patch.** The game as shipped has two ways to show both endings:
1. It keeps its clock running while the last block slides out, and counts the
   win only when the slide ends. If time runs out during that half second, it
   shows "Out of Time!" and then "Level Completed".
2. It still accepts drags after the fail screen, because input raycasts the 3D
   board rather than the UI.

`unity/game-patch` fixes both in the game's own code:
- the clock stops when every block left on the board has started its exit
  (`GameManager.OnBlockExitStarted`, called from `ExitService.PerformExit`);
- once one ending has shown, no other ending can follow;
- the board takes no input after either ending.

That is 31 added lines in three files, each marked `cbj-creative patch`.
`game.patch` is the readable diff, and `original/` holds Rollic's files byte for
byte. `build-player` applies the patch to its copy only, so Rollic's project is
never changed, and it refuses to patch files that differ from those originals.

For a before/after, `cbj build-player --stock` builds the game exactly as
shipped and `cbj render --stock` records with it. On a stock build, the
recorder stops the clock itself unless asked not to. `cbj render` rejects any
recording that shows both screens.

Event data for the compositor: `result.json` has each drag's frames, cells and
gate number, the first touch, the clock stop, win or fail frame, the frame
each block disappears, and the HUD's rectangles (caption safe zones).
`frames.json` has, per frame, the timer, the finger and every block's position
in video pixels, and a pixel hash. The game itself has no audio; sound effects
are added by the compositor at these frames.

`build-player` copies the Unity project into `build/unity-project`, adds
`unity/CreativeRunner`, and builds `build/CBJRunner.app`. The original project
is never modified, so it can stay open in the editor. The runner script does
nothing unless the player is started with `-cbjJob <job.json>`.

How a recording works:

1. `make_job` checks the script with `replay` first, so an illegal script is
   refused before Unity starts, and writes `job.json` (level path, timings, drags).
2. The player loads the level, fits the camera to a 9:16 frame with the game's
   own fit formula, and draws the UI through the camera at the scale a 1080-wide
   phone uses.
3. Time runs on a fixed step (`Time.captureDeltaTime`), so a frame is always
   1/30 s of game time however long it takes to render. The timer, the exit
   slide and the win animation all run on that clock.
4. For each drag the finger picks the block up, moves one cell at a time along
   the planned pivot path, and waits at corners until the block catches up, so
   the game's per-frame exit check sees the same cells the solver planned.
5. After each drag the runner compares the cells the block actually entered, and
   whether it exited, with the script. Any difference stops the recording with
   status `mismatch` and the reason.
6. Frames are read back from the GPU and piped to ffmpeg. `frames.json` stores,
   for every frame, the MD5 of the raw pixels, the game timer and the finger's
   position in video pixels (for a hand overlay later). `result.json` stores the
   status, the frame of the first touch, each drag's frames, the win or fail
   frame, and the timer at each point.

Statuses: `cleared` (win screen), `unresolved` (`--end cut`), `failed` (the
game's fail screen; play stops there, as it does for a player, and a drag cut
short by it is marked `interrupted`), `mismatch`, `timeout`, `error`. A broken
job, a path cell off the board, or ffmpeg dying mid-recording ends the run with
`error` or `mismatch` and a reason; the player never hangs. `cbj render` then
cross-checks `result.json`, `frames.json` and an ffprobe of the video, and
prints any problem.

`make_job` refuses scripts that cannot give the asked ending (`win` needs a
cleared board, `cut` and `fail` need a block left) and a finger faster than
half a cell per frame (15 cells/s at 30 fps), the limit above which the block
could land on a cell boundary when the game checks for an exit.

Results: the solver's scripts clear all six shipped levels in the game, with
every drag entering exactly the planned cells.

**Repeatability.** The same job gives the same game every time: the timer,
finger position, cells entered, exit frames and ending are identical frame for
frame. The pixels are identical in nearly every frame, but not all: across
repeated 270x480 renders of Level 6, one or two frames per run differed by a
few pixels (worst frame about 45 dB PSNR, invisible to the eye), at random
positions. Logging every particle's state showed the simulation identical in
those frames, and the difference stayed with MSAA off and shaders warmed up,
so it comes from below the game, in the graphics driver. Full-size renders
usually match on every frame. `cbj compare A B` therefore reports the game
state, the count of identical frames and the lowest frame PSNR, and the
controlled-editing proof will compare with that tolerance rather than demand
bit-identical frames. Two real sources of variation were fixed on the way:
particle systems picked a new random seed every run (the runner fixes each
seed), and Unity UI button fades run on real time (the runner makes them
instant).

**Known differences from a phone.** The drag follows the game's own
`Lerp(..., deltaTime * dragSpeed)`, so at 30 fps the block trails the finger a
little more tightly than on a 60 Hz phone; render with `--fps 60` for the
phone's feel. The game's 1.5 s camera glide at level start is not played: the
video opens on the fitted board. `build-player` copies the project's
`Library/` folder to keep builds at about 35 s; if a build fails while the
editor is busy importing, close the editor or delete `build/unity-project` and
build again.

`tests/test_render.py` checks jobs, recordings and comparisons without Unity.
`tests/test_unity_render.py` has 28 tests and starts the player about 35 times (about
5 minutes; the two stock-game tests need `cbj build-player --stock` first):
- six levels cleared;
- a repeat render;
- a camera-only change;
- a blocked drag, an unplanned exit, a path off the board;
- a dead ffmpeg, a bad job, bad camera keys, an unknown object to hide;
- the fail screen between drags and in the middle of one;
- the stock game's fail-then-win bug; the patched game stopping its own clock;
  the recorder stopping it on a stock game;
- the compositor event data;
- the four scenario endings on the narrow level, each landing on the dry run's predicted frames:

```
CBJ_UNITY=1 uv run pytest tests/test_unity_render.py
```

## Scenario scripts: human play toward an ending

`cbj render` plays the solver's shortest solution, which looks like a robot. `cbj scenario`
plays the level the way a person does in the ads, toward a requested ending, and records it:

```
uv run cbj scenario LEVEL --ending win|near_fail|cliffhanger|time_out --plan-only   # print the beats
uv run cbj scenario LEVEL --ending near_fail [--mistakes 1] [--hesitations 2] [--seed 0] [--length 22] [--label 147]
uv run cbj scenario LEVEL --ending time_out --allow-fail      # opt-in; refused on easy levels
uv run cbj rerun FOLDER -o NEW_FOLDER                         # the folder alone reproduces the recording
```

| ending | what the viewer sees | clock |
|---|---|---|
| `win` (S3) | a clean solve; the closing drags speed up | kept above 0:50 (no red flashing); on a hard level a tight clock, about 00:08 at the last exit |
| `near_fail` (S4) | 1 mistake, 2 hesitations (one on the last block), a quick finish | 00:01 left when the last block starts leaving |
| `cliffhanger` (S1) | clear the easy blocks, try the last two and get blocked; the final one is pushed into its blocker; cut | 00:08 at the cut |
| `time_out` (S5) | 1 mistake; the last block is grabbed with 00:01 on the HUD (shown for about half a second), races for its gate under 00:00, and time runs out one cell short | fail screen |

**Mistakes** follow the winning "I can't reach <colour>" ads: a trapped block dragged toward
its gate until another block stops it, and the finger keeps pressing (`blocked`); a block that
must move, moved somewhere that does not help (`wrong_way`); or at most one one-cell nudge of a
block that cannot leave yet (`fidget`). Every mistake costs the player 1 or 2 extra drags
(measured by the solver; 0 would be progress), comes in drags 1-3 when the board offers one
there (otherwise at the next drag that does), and never in the last two drags. A block parked
at a gate of another colour is never used: it reads as not knowing the rules. After a mistake
the solver re-plans, and the drag right after it always carries a reaction: a 1.8-2.5 s "stuck"
pause if it is the real fix after the last mistake, otherwise 1.2-2.0 s (never a long stare
before an obvious exit). In a
cliffhanger, the set-up drags that run a block into another one are played the same way
(pushed and held), so the final push reads as the second try.

**Easy boards degrade instead of failing.** If a board has no believable mistake (every block can
just leave) or no room for a hesitation, the plan plays on without it and records why in
`play.json` (`notes`); `cbj scenario` prints the notes. A cliffhanger on a two-block level keeps
one block. A time-out is refused on easy levels (policy: at least one repositioning drag and a
naive player at 1.1x the minimum; of the shipped levels only Level_04 passes), and on a level
whose last exit is a single cell (there is no race to cut short).

**Pacing** is in whole frames, chosen by what the player is doing: confident 0.35-0.6 s before
an exit they can see, thinking 0.9-1.6 s before a repositioning drag, stuck 1.8-2.5 s after
the last mistake, 0.3-0.45 s for the closing drags. Finger speeds are exact (4, 5, 6 or 8
frames per cell). Each pause grows by a frame per two cells the finger travels to the next
block.

**Exact timing, pauses only.** A dry run of the real game (`capture=False`, about 4 s) logs every
frame. A pause shifts every later frame by exactly its length, so the clock and `--length` are
fitted by moving pauses inside their ranges, never by changing speeds (slow fingers read as slow
motion). `--length` therefore only trims or stretches a script by a few seconds (about 14-23 s
on the narrow level, depending on the ending) and refuses anything outside that; a longer ad
needs more mistakes or hesitations, a bigger level, or several gameplay segments joined by the
compositor. The recording must then land on the predicted frame for every drag; `cbj scenario`
reports a problem if it does not. The fitted values, the predicted and measured frames, and the
level's difficulty numbers go into `play.json` next to the video, and `level.json` is the level
with the clock the ad used. With the runner's input (`job.json`), the folder alone reproduces
the recording: `cbj rerun FOLDER -o NEW` records it again and compares the two. With `--length`,
the clock fit takes the smallest pause change that still shows 00:01, so the length holds to
within a third of a second.

**Repeatable.** The seed picks the mistakes and hesitations; the pacing rules stay the same
(the rest of the plan follows from the solver's re-plan after the chosen mistake). The same
level, ending and seed give the same `play.json`.

**Runner support.** A drag can end with the finger pressing on past its last cell
(`push_cells`, at most 0.45 so the block's cell cannot change; the game holds the block at the
blocker) and staying down (`hold_s`). `push_dir` lets a block that cannot move at all be pressed
into its neighbour. The runner logs the frame on which each cell was entered (`cell_frames`).

**The narrow-centre level.** `data/levels/gen/narrow_center_01.json` is the case's example
prompt ("a difficult level with a narrow center section... the player almost fails"): a 6x8
hourglass with a two-lane waist, 7 blocks, 9 minimum drags (2 repositioning), naive player 1.26x
the minimum. Its cliffhanger is two blocks head-on in the waist.

**Finding a cliffhanger.** For each pair of blocks to keep, a greedy search clears the other
blocks first (as players do) until only the pair is left with one of them trapped and the
position still a puzzle. It prefers real puzzles (a repositioning drag is still needed; tests
check this on Levels 4-6 and the narrow level), then fewer drags; it is not guaranteed to be the
shortest route, and if no such position turns up it ends on a hesitation and says so.

**Speed.** Planning solves many positions, so it uses `solve_fast`, an A* search (lower bound:
blocks left), which gives the same minimum as `solve` (tests compare them on every level and on
365 random boards, 121 of them solvable, against the full unpruned search) while searching 589
positions instead of 43,446 on the narrow level.

## Finished ads: the compositor

`cbj ad RECORDING` turns a `cbj scenario` recording into a finished 30 s ad (`--length` for
others). The defaults depend on the recording's ending:
- a hook on frame 0, which is also the poster;
- a caption on the mistake: "I can't reach dark green!", with the colour taken from the block;
- "Aha! Move red first" on the fix that follows the mistake;
- "Hurry!" with a red edge pulse on the last five clock seconds;
- a slow-motion replay of the last one or two beats (at most 5 s), with a REPLAY tag over the HUD's
  level badge, the one spot of a full-size frame that never hides the play;
- the game's own result screen;
- an end card: the game's background, a fact from the recording ("Cleared with 00:01 left"),
  the game's art and its green "PLAY NOW" button.

On top of that, a tap ring follows the recorded finger, and synthesized sound effects fall on
gameplay events: taps, exit pops rising over the last three exits, clock ticks (not repeated in
slow motion), a bump, a success chord or a fail sound, and whooshes.

**Sizing.** The ad is exactly its length. The end card takes what is left: at least 3 s, ideally
up to 5 s. When the recording is short, a frozen first frame of up to 2 s gives the hook room. An
end card over 8 s is refused, because the recording is too short for the length; use a longer
scenario, a shorter ad, or `--allow-long-card`. Captions get their reading time (0.4 s plus 0.3 s
a word). One that would overlap a more important caption moves later, keeping its gameplay
anchor; one that cannot be read in the time left is left out, with a note in `ad.json`.

**The ad is data.** `ad.json` holds named segments (clips of recordings at any speed, frozen
frames, cards) and named layers (text, tags, images, the button, the cursor, the edge pulse).
Each layer starts and ends either at a time or at a **gameplay event**: `beat.1.start`,
`clock<=5`, `win`, `fail`, `clock_second`. Texts may only use facts from the recording
(`{clock_left}`, `{colour}`, `{timer}`, `{blocks}`, `{blocks_left}`, `{blocks_left_phrase}`,
`{time_used}`). A copy guard refuses invented odds ("only 1%", "IQ 140"), which ad rules forbid.

`locked` lists what an edit may not change. It holds the gameplay sources, the segments (timing
and camera fit) and the cursor. Their digests are written when the ad is made, and an edit that
changes a locked part fails QA. To change one on purpose, remove it from `locked` first;
`cbj ad-diff` then reports it as unlocked. Edit the file and run `cbj compose` to render it again.

**Layout.** The whole recorded frame is scaled to 75% and placed on the recording's own background
gradient (letterboxing; the game camera is untouched). This leaves:
- one text band above the HUD (y 250-476), with one caption at a time;
- a bottom that stays clear for the platform's buttons (the "social" safe area keeps 250 px top,
  420 px bottom and 130 px right free).

The replay and the result screens play full size. Texts are fitted to the band.

**The proof of what changed.** Every render writes `compose.json`:
- the tool versions;
- the gameplay file's SHA-256 and each segment's fit;
- every layer's resolved frames and pixel box;
- a SHA-256 of every composited frame;
- the WAV and MP4 hashes;
- the QA results.

The encode is bit-exact, so the same `ad.json` gives a byte-identical MP4.

**Edits stay local in the delivered video too.** Every segment and layer boundary starts a new
GOP: an IDR frame, placed by frame number (given as times, ffmpeg put some keyframes one frame
late). The encoder runs with a constant quantizer, no look-ahead and no B-frames. So with the
same keyframes, only the GOPs that hold a changed frame can decode differently. A text, style or
image edit keeps the keyframes: the decoded MP4 then differs exactly in the edited layer's
frames. A timing edit (moving, adding or removing a layer) moves keyframes, so the video can
differ from the first moved keyframe on, and `ad-diff` says so. With default x264 settings, rate
control and inter-frame prediction spread any edit into neighbouring frames. The price is file
size: about 10 MB for 30 s instead of about 6 MB, well inside platform limits.

`cbj ad-diff ORIGINAL EDITED` is the proof for one edit. It compares the frame hashes, then
composites both versions of every changed frame again and measures the changed pixels. It
reports:
- which layers changed, and which frames;
- the measured pixel box, against the boxes of the changed layers (every change must be inside
  them);
- whether the gameplay sources, timeline, camera fit, sound and locked parts stayed the same.

`--decode` also decodes both MP4s and checks that every differing frame lies in those GOPs. The
command exits 1 if a change escaped its layers, a locked part changed, or a render failed QA (a
failed render is refused). Tests check the keyframe positions with ffprobe and the locality on
the decoded files.

**QA, on every render.** Problems found before drawing stop the render at once (nothing is
encoded, exit 1). A render that fails a later check is saved as `ad.FAILED.mp4`, never as
`ad.mp4`. The checks:
- exact length;
- the hook on frame 0;
- every text inside the safe area and on screen for its reading time;
- every layer inside its segment;
- no two captions at once;
- the call to action held to the last frame (the frame a feed shows when the ad ends or loops);
- an end card of at least 3 s (a warning above 6 s);
- every anchor resolvable;
- locked parts unchanged;
- the copy guard;
- the audio peak and length.

**Assets.** The game's font (Tobi) and UI sprites are read from the Unity project at run time
(`../CBJ`, or set `CBJ_PROJECT`) and never copied into this repo; the font is "all rights reserved"
and licensed to Rollic. Without the project, an open fallback font is used. The sound effects are
synthesized in code, because the project ships no audio; they stand in for the game's own sound
bank.

**Colour.** Frames are decoded and re-encoded with BT.709, TV range and swscale's accurate
rounding. ffmpeg's default darkened a decode and re-encode by about 2 levels; now the drift is
about 0.

## Text to creative: prompts in, ads out

`uv run cbj ui` opens a local page (http://127.0.0.1:8765). You write what you want; the page
shows how each of the case's eight prompt controls was read, makes the ad, and plays it. A
follow-up prompt edits it into a new version, with the proof of what changed.

**The split.** An LLM turns the prompt into a typed **brief** (`brief.py`) and nothing else: it
never makes levels, moves or pixels. The deterministic engine makes the ad from the brief, so
the gameplay is real and solvable and an edit can be proven. The planner (`planner.py`) uses
NVIDIA's Nemotron 3 Ultra through its JSON-schema mode, with reasoning off (a brief takes 15-40
s; with reasoning on, up to 3 minutes), and falls back to Nemotron 3 Super. With `CBJ_PLANNER=claude` the
same system prompt and schema go to the Claude Code CLI instead (see "Planning with Claude Code").

**What I understood.** Each control gets a row: the prompt's own words, what the tool will do,
and a status. *applied*: done as asked. *default*: not mentioned. *adjusted*: asked, but changed
to something the game can do, with the reason. *not supported*: impossible here, with the
reason (for example "turn the blocks into 3D cats"). Nothing is dropped silently.

**Checks in code, not in the prompt.** The model is told the rules, but the code enforces them:
- the model declares which field groups the prompt changes (`changed` in the brief); only those
  are taken, and every other field keeps its default (a new ad) or its previous value (an edit);
- copy, board size, block count, colours, the HUD level number and uploads are also taken only
  when the prompt's own words ask for them, so the model cannot add copy, sizes or images
  nobody asked for (an edit keeps the images its version already uses);
- every text goes through the copy guard and may only use measured facts;
- repainted colours must stay easy to tell apart (each colour has its own gate);
- a time-out is a social-channel ending on a medium or hard level; the clock of a near-fail is
  set by the ending; only 9:16 is rendered.

**The eight controls, and what each one drives.**

| Control | In the brief | What the engine does with it |
|---|---|---|
| Type or structure of the level | shape (open, narrow centre, door, several walls, cross, ring, lanes), size, blocks, piece shapes, looks (symmetric, packed, colourful, spacious), colours, HUD number | the level generator (`generate.py`), or a shipped level |
| Gameplay behaviour | ending, mistakes and their kind, hesitations, the order of interactions, a satisfying finish, seconds left at a near-fail | the scenario planner (`play.py`, `events.py`), recorded in the real game |
| Difficulty or pacing | easy / medium / hard, length, tempo, pacing curve | the generator's difficulty band; the recording's pauses; the ad's sizing |
| Visual elements | theme or per-colour paint (with names), background, board, caption colours, zoom, cursor, HUD | the recorder repaints the game's own materials; the compositor styles the captions |
| Creative concept | angle, hook, every caption, end-card texts, language | the ad's texts (non-English: the defaults are translated too) |
| Sequence of events | standard or result-first, replay, result screen | the ad's segments |
| Assets to use | uploaded images or game sprites, by role: logo, mascot, sticker, cursor, end-card art or background; sound on or off | image layers, the cursor image, the end card |
| Elements that should remain unchanged | keep list; edits | an edit changes only what it asks about (below) |

**The level generator** places polyomino blocks at random on a board of the requested shape,
each with a gate of its colour, then keeps the candidates that the game's rules accept, the
exact solver can solve, and the difficulty measure puts in the requested band (easy: nothing to
reposition, most blocks can leave at once; hard: no block can leave at the start, two or more
repositioning drags, a naive player needs 1.2-4x the minimum and gives up on at most 5 % of its runs). Harder levels
put gates across the board, so blocks must cross each other's paths. When the prompt gives no
block count, the level is sized to the ad's length. The same spec and seed give the same level,
and levels are cached. A hard narrow centre that the search cannot find in its time budget falls
back to the hand-checked one, and the brief says so.

**Colours in the game.** The recorder repaints the game's own materials before the board is
built (block, gate and exit-particle colour per colour slot, the cells), and replaces the
ground's gradient. The puzzle is unchanged: only the look. Captions name the shown colour
("I can't reach mint!"), and the end card follows the background.

**Edits change only what they ask about.** A follow-up prompt is planned against the current
brief; the fields of every control it does not mention are restored. Then the smallest re-run:
- copy, captions, sequence, assets or caption colours: the same recording is reused and only the
  ad is composed again; `ad-diff` proves which frames and pixels changed;
- colours, HUD, zoom or the level number in the game: the stored job (the same moves and timing)
  is filmed again with the new look, and the game state is checked identical on every frame;
- gameplay or level: recorded again, and the proof says so.

Recordings and levels are stored under a hash of everything that decides them
(`studio/recordings`, `studio/levels`), so asking for the same thing twice never re-records.
Each version (`studio/<id>/v<n>`) keeps its prompt, brief, level, the recording it used, the
ad and its proof.

## Level & gameplay generation (core requirement 2)

The case asks for gameplay "appropriate for the requested concept": a specific type of level, a
visually interesting board, a difficult or easy level, a gameplay progression, a near-fail moment,
a satisfying solve, a specific sequence of interactions. The LLM still only writes the brief;
each of these is a brief field that deterministic code builds, plays in the real game and then
checks on the recording.

| Asked for | Brief field | How it is made |
|---|---|---|
| A specific type of level | `level.shape` (7 shapes), `level.pieces` (small, big: plus, 2x3, L4; long: 3-4 bars), size, blocks, colours | the generator places those pieces on that board; every gate is one its block can actually reach |
| A visually interesting board | `level.style`: symmetric (blocks, colours and gates mirrored; the local search moves mirror pairs, so a hard symmetric board is reachable), packed (55-75 % of the cells hold blocks, one gate per colour, as in the real game), colourful (every colour, touching blocks differ), spacious ("enough free space", "room to move": at most 5-7 blocks, none touching, 35 % of the cells or fewer) | a looks score (contrast, gate sides, fill, symmetry) in the generator's ranking |
| Difficult or easy | `level.difficulty` | bands from the exact solver and a naive player that never repeats a position; boards where it gives up more than 5 % of the time are unfair and rejected; local search (move a block, move a gate, swap colours, change a piece) improves the best boards |
| A gameplay progression | `pacing.curve` (speeds up, slows down), and colour-by-colour orders | pauses and finger speeds follow the curve; one level per ad in this version |
| A near-fail moment | `gameplay.ending` near-fail, `gameplay.clock_left_s` 1-3, mistakes | the clock shows 00:01-00:03 as the last block leaves |
| A satisfying solve | `gameplay.finish: streak` | the shortest solution with the longest final run of exits: one key move, then every block leaves one after another ("One move frees them all!") |
| A specific sequence of interactions | `gameplay.events`: leaves / moves / stuck / hesitates, for a colour and any / biggest / smallest / longest, all, first / next / last | an exact A* search over (position, steps done) finds the fewest drags that do the steps in order; "stuck" is a blocked attempt by that block, "hesitates" a pick-up-and-put-back |

The events solver (`events.py`) does not use the free solver's "take any open exit first" shortcut:
with a requested order, an early exit can make a later step impossible, so the order of exits is
part of the search (it agrees with the free solver on 122 random boards when no steps are given).
An order that cannot happen on a level is said so, and the play goes on without it.

**Checks from the recording.** Each version gets a list of checks (`checks.py`), shown in the UI
under *Level & gameplay* with where each was measured. From the recording (`result.json`): every
drag moved the planned block through the planned cells to the planned outcome; the ending and
the clock; the mistakes; each step of the order and the drag that did it; the final run of exits
and its key move; the pauses in the first and last third. From the level file: the difficulty
numbers, block count, block shapes, board shape and looks.

**Level only.** The UI's *Level only* button plans the prompt, builds the level and plans the
moves without recording (seconds instead of minutes), with the board picture and the move list.

## Common to all four workflows (2026-10-19)

The four workflows (text, video-guided, image-guided, edit) were tested in turn today, and a lesson learnt in one holds in
every one. Each workflow now does these, importing the helper rather than copying it (the list, with the helpers' names, is
the docstring of `src/cbj/workflows/__init__.py`): the request is translated once for the route and the parsers; the game's
rules and the shared case rows are measured on every version; the loop keeps the best version rather than the last, keeps
every value the request states, never plans a longer play for a take that ran over, makes no version for a viewer-only remark
that changes nothing the viewer pointed at, and stops when the same row misses twice with the same measure (the board's
limit, said); a board copied from a picture or a video has the play it has, said at plan time when the stated length cannot
hold it or leaves a long end card; a time-out's one-block limit is said when more are asked; every version keeps the engine's
lines for the feedback analysis and the report. Tests: `tests/test_workflows_common.py`.

## Controlled editing (core requirement 5)

The case: "If a user likes an existing creative and asks for one specific change, the system
should avoid unnecessarily changing everything else ... preserve gameplay, timing, camera,
composition, sequence, visual structure and other assets." An edit here is a change to the
stored creative, not a new generation:

1. **Only the asked fields change.** The planner reads the edit against the version being edited
   and declares the field groups it changes; `brief.merge` takes only those (and, for groups a
   model tends to over-fill, only with words in the prompt that ask for them). Pictures merge
   slot by slot, so replacing one never drops another.
2. **Each stage re-runs only if its inputs changed.** The level is kept unless the edit is about
   the level; the recording is reused (an overlay edit) or the stored job is filmed again with
   the new look (a colour edit: the same moves on the same frames); only a gameplay edit records
   new play, and on a kept level it picks the play closest to the original (of up to 24 plans, the
   one with the most moves in common; the report says how many).
3. **"Harder" or "easier" edits the board, not replaces it.** The closest board that rates so: at
   most three small changes (a block moved, a gate moved, two colours swapped), the shape, size and
   pieces kept, fair and solvable on the full rating; the HUD's level number stays. "Make the hook
   harder to ignore" is about the hook, not the level (difficulty words count only in a clause
   without copy words).
4. **The ad keeps its timing.** An edit that keeps the gameplay frames pins the original's intro,
   replay and length (`build_ad(pin=...)`): removing the replay gives its time to the end card
   instead of shifting the gameplay; freed time never becomes a replay the user did not see;
   past 10 s of end card the ad ends earlier, with a note.
5. **Replacements keep the composition.** A new picture is drawn inside the box of the one it
   replaces (the end-card picture, the icon beside the hook, the button), in the same place (a
   logo stays in its corner).
6. **The edit report proves it, item by item** (`editreport.py`): gameplay, timing, camera,
   composition, sequence, visual structure, other assets (the case's seven), captions and sound.
   Each difference is classified on its own: *asked*; *explained*, only when a check on the
   measured difference proves the reason (a caption "names the colours as shown" only if its
   template is the same and only its filled-in facts changed; a caption "waits for the longer
   hook" only if the hook was asked and got longer); or unexplained, which makes the row
   *CHANGED WITHOUT BEING ASKED* and fails the edit. Exact facts first (level hash, every move,
   frame windows, file hashes), then the frame diff: which frames changed and whether every
   changed pixel is inside the edited layers' boxes.

**"Replace this asset."** Every version has an inventory (`edits.py`): the logo, the icon beside
the hook, the end-card picture, the button, the end card's background, the cursor, the sound and
every caption, with plain names and screen times. The planner gets it with an edit prompt, so
"the coin pile" or "this object" resolves to a slot. An attached picture the model does not place
goes to the slot the prompt names, else to the end-card picture, written as an assumption.

**Added 2026-10-19 (edit test set 2, five one-change requests on video-reference creatives, `~/rollic-case/req5-edits-2026-10-19/`).**
A colour word in an edit names the slot *as this creative shows it* (`brief.slot_of_colour_word`): "apply this texture to
the cyan block" on a trailer copy whose green slot is painted cyan goes on that block (the shown name first, then the game's
own name when the slot is shown as itself, then the nearest shown shade for "teal", "magenta", "light blue"; restricted to
the slots on the board). The route and the planner both use it, so the request is a direct edit with no planner. A picture
on the walls and a texture on a block are drawn on *every* part that shows the board (the still opening, the play, the
replay, the frozen question, the held result) and on the end card's board picture, with their boxes recorded, so the object
never turns back into the plain wall at the cut (a viewer caught it on the question frames). "This object" with nothing
named is explained once (the planner's reading, with the alternatives).

**Exact edits without a prompt.** The UI's *Things in this ad* card replaces, removes or
rewrites one thing (a picture, a caption, the sound) by changing the brief in code: no planner,
the same proofs. **Any version can be edited** (the new version records which one it came from),
and any two versions can be compared (`cbj edit-report <id> A B`, or *Compare* in the UI).

```
uv run cbj make "Same ad without the slow-motion replay." --edit <id>          # edit the latest version
uv run cbj make "Keep everything, but the button says 'SOLVE IT'" --edit <id> --base 2  # edit v2
uv run cbj edit-report <id> 1 3                                               # what v3 changed from v1
```

**More things an edit can change on its own** (from the 45 control & consistency scenarios, see
`~/rollic-case/CC-SCENARIOS-REPORT-2026-10-14.md`):

- **Music** is its own stem: an uploaded WAV/MP3/M4A/AAC/OGG/FLAC (`audio.music`), mixed under the
  effects (about -9 dB, looped or trimmed, faded out over the last second). compose.json keeps a
  hash of the effects stem and of the music, so replacing the music changes zero video frames and
  the report says only "the music" changed. Undo: "undo the music replacement" restores the music
  it replaced (the planner sees what each earlier version changed), and nothing else.
- **A picture behind the board** (`visuals.background_image`): the recorder hides the game's ground
  and draws the picture behind everything, so the board, blocks and HUD are the game's own; the
  game state is checked identical on every frame.
- **The board itself** (`level.changes`, `boardedit.py`): move a door to an edge, add a wall on a
  tile or on a block's route, remove a wall. The longest start of the old play that is still legal
  on the new board is kept move for move (`play.plan(prefix=...)`); when every move survives, the
  stored job is played again on the changed board and the ad keeps its timing. A change that would
  leave the level unwinnable, or has no tile to use, is refused with the reason.
- **Timing**: the still opening frame and the held result have lengths an edit can set (the ad's
  end moves by the same time, nothing else); a caption's entrance or exit can move; a camera
  punch-in can run for a stretch of time (eased, anchored on a named block, never cropping the HUD
  or the board).
- **One caption's colour**, and **1:1, 4:5, 16:9** versions made from the 9:16 master (cropped to
  the area where anything is shown, blurred side extensions, the board never cut).
- **Files the request names but did not attach** ("the attached toy pictures", "the supplied logo") stop the
  make with a question (the brief's `needs`): attach them and plan again, or say to make the ad without them
  (the UI's button, `cbj make --without-files`); the version then says it was made without them.
- **Honest refusals**: a result identical to its parent is not kept; a request that changes the
  puzzle while locking every frame is refused as a contradiction; a picture on a block or a door,
  a decorative border, or a dissolve the ad does not have is answered so; a file that is not
  attached is asked for, never guessed from earlier uploads; the same absolute request sent twice
  changes nothing.

## Layout

```
src/cbj/level.py     LevelData model, JSON round-trip, validation
src/cbj/rules.py     occupancy, valid positions, exit check
src/cbj/solver.py    drag outcomes, BFS solver, replay checker
src/cbj/describe.py  ASCII boards, plain-English steps, move-script JSON
src/cbj/difficulty.py difficulty numbers and the simulated naive player
src/cbj/render.py    render jobs, camera, running the Unity player, checking and comparing recordings
src/cbj/play.py      scenario scripts: mistakes, hesitations, pacing, endings, pause-only fitting
src/cbj/ad.py        the ad as data: recordings, gameplay events, ad.json, the default ad per ending
src/cbj/compose.py   renders ad.json: layout, layers, cursor, sound, QA, compose.json
src/cbj/draw.py      text in the game's style, sprites, easing, exact alpha blending
src/cbj/sound.py     synthesized sound effects and the mix
src/cbj/video.py     frame-exact decode and bit-exact encode with matched colour
src/cbj/brief.py     the creative brief: schema, checks, edit merging, colours
src/cbj/planner.py   prompt -> brief with an LLM (NVIDIA Nemotron), with checks in code
src/cbj/llm.py       which model plans: NVIDIA (default) or the Claude Code CLI (CBJ_PLANNER)
src/cbj/reference.py reference images and videos read for the request: reading plan, format step, checks, parts
src/cbj/gemini.py    the video reader tried first (Gemini 3.5 Flash-Lite); NVIDIA build is the fallback
src/cbj/imageref.py  what an attached image is for (style, composition, asset, modify) and what it gives
src/cbj/videoref.py  what a reference video's reading focus lets into the brief, and the provenance
src/cbj/workflows/   the three workflows: create (text), guided (prompt plus media), edit
src/cbj/generate.py  the level generator: shape, size, blocks, pieces, looks, colours, difficulty band, events fit
src/cbj/events.py    gameplay events (an order of interactions), their solver and check; the satisfying finish
src/cbj/checks.py    what was asked, checked on the recording and the level file
src/cbj/preview.py   a picture of a level, drawn from its file
src/cbj/studio.py    brief -> level -> recording -> ad, versions, cached stages, edits (pin, closest play)
src/cbj/edits.py     what an edit can point at (the inventory) and exact edits without the planner
src/cbj/editreport.py the edit report: the case's seven preserve items, captions and sound, one by one
src/cbj/app.py       the test UI (FastAPI); the page is src/cbj/static/index.html
src/cbj/enhance.py   prompt enhancement: the request in the planner's words, nothing added, questions for the rest
src/cbj/trends.py    optional ideas from what is trending (Google Trends + Tavily), as prompts; never touches the workflows
src/cbj/feedback.py  designers' feedback records with the scene captured from the studio; read by the owner, never by a workflow
src/cbj/lessons.py   the records distilled into a versioned, correctable LESSONS.md (two tracks, evidence-checked); zero effect
src/cbj/soundtrack.py optional music bed synthesised from a version's own concept (+ the hook spoken by NVIDIA Magpie); an upload the music edit places
web/                 the website (Next.js, deployed on Vercel): the same engine API behind the Stitch design, plus an offline showcase
scripts/             engine-online.sh: the public engine (:8766, token), the Cloudflare tunnel, the Vercel env update
src/cbj/cli.py       command line
unity/CreativeRunner Unity scripts copied into the project copy by build-player
unity/game-patch     the game fix: Rollic's originals, the patched files, game.patch
data/levels/         the six shipped levels (copied unchanged from the Unity project)
data/levels/gen/     generated levels (the narrow-centre hourglass)
data/solutions/      move scripts for the Unity replay
reports/             solve table and the Level 3 walkthrough
tests/               rule, level, solver, replay, failure-mode and render tests
build/, renders/     player build and recordings (not in git)
studio/              the UI's creatives, recordings, levels and uploads (not in git)
```

## Image-guided fix (2026-10-19): a colour count relative to the picture

"Create a similar game concept, just use one more colour" on a three-colour screenshot produced three colours: the planner
had planned the fourth, but the board step filled the colours from the picture because the request "said nothing" about
them. `imageplan.relative_colours` now reads "one more / an extra / two fewer / more colours" as a stated part relative to
the picture: the picture's mapped colours plus or minus the asked count (the planner's own extra colour first, then the
game's order; never below two), shown as taken with a clamp line. Test: `test_one_more_colour_than_the_picture_adds_one_to_the_pictures_colours`.

## Prompt enhancement and ideas from trends (2026-10-18)

Two steps in front of the workflows, never inside them (the planner, the engine and the evaluation are unchanged).

**Prompt enhancement.** `uv run cbj enhance "<prompt>" [--edit ID --base N] [--upload NAME]`, `POST /api/enhance`, the
site's *Enhance prompt* button. The planner's own model rewrites the request in the words the planner reads reliably
(the eight controls' vocabulary, legal gameplay, English), replaces what the game cannot do with the closest thing it
can and lists the swap, and adds NOTHING: every concrete ask in the rewrite must come from the user's words (a change
entry quotes them), and anything it would like to add comes back as a question with tap-able sentences. Code checks
the rewrite with the engine's own readers (`audit.asked` facts, quoted captions kept, `brief.plain_text`, caption
length, no statistics); a rewrite that breaks a rule is re-asked once and then the user's own words stand. The result
also says which workflow will read it (`app.workflow_of`). Module `src/cbj/enhance.py`; tests `tests/test_enhance.py`;
why it is built this way: `~/rollic-case/PROMPT-ENHANCEMENT-AND-TRENDS-2026-10-18.md`.

**Ideas from trends (optional).** `uv run cbj trends [--theme X] [--region US] [-n 4] [--refresh]`, `POST /api/trends`,
the site's *Start from a trend* card. Google's trending searches (RSS) and Tavily news (`TAVILY_API_KEY` in `.env`),
filtered in code for safety and listicles, then the planner's model writes 4-6 ad ideas that map one trend each to the
levers the game has (look, colours, caption tone, hook, ending, tempo, length), with the source and why it is current;
the ad's copy never names a brand, title or person. Each idea is a prompt text; nothing is made until the user sends
it, and then it goes through the same planner, checks and review as any typed prompt. Cached 6 h in `studio/_trends/`.
A pasted link works the same way (`--link URL`, `{"url": ...}` on the endpoint, the card's *Read link*): the page
behind a public http(s) URL is read (Tavily extract, else a direct fetch with the tags stripped; local and private
addresses are refused) and is the only signal for 1-3 ideas whose source is the URL.
Module `src/cbj/trends.py`; tests `tests/test_trends.py`.

## Run it on your own accounts (optional, 2026-10-19)

The studio as delivered runs on the owner's accounts: the planner through the owner's Claude account (the Claude Code
CLI logged in on the Mac, `CBJ_PLANNER=claude`) and the reference-video reader on the owner's Gemini key. Both can be
yours instead, with nothing else changed; the default stays as it is.

**Your own Claude CLI and your own Gemini key (the intended way).** On the machine that runs the engine:

1. Install Claude Code and run `claude` once to log in with your account (the engine calls `claude -p`; it uses that
   login and its usage limit, no API key).
2. Put your keys in `cbj-creative/.env`:
   ```
   CBJ_PLANNER=claude                      # your Claude account through the CLI (opus, low effort)
   GEMINI_API_KEY=...                      # the reference-video reader (https://aistudio.google.com/apikey)
   NVIDIA_API_KEY=...                      # optional: the fallback reader and the spoken hook
   ```
3. `uv run cbj setup-check` says what is in place and what to do (the CLI login, the keys, ffmpeg, the game player, the
   studio folder); `uv run cbj setup-check --live` also makes one tiny call to the planner and to Gemini to prove the
   login and the key work. Then `uv run cbj ui` as usual.

**On the hosted site: your Gemini key.** A remote user's Claude CLI cannot be used by the owner's engine (the CLI runs
on the engine's machine), so the site's key dialog (*This studio's engine, with my Gemini key*) takes only a Gemini API
key, for reading reference videos on your own quota; the planner stays the studio's. The browser keeps it (this tab, or
this device if you say so) and sends it only with the calls that start work, as the header `X-CBJ-Gemini-Key`; the
engine holds it in memory for that job alone, never writes it to disk or to a log, never returns it, and falls back to
its own key when you give none (`src/cbj/keys.py`; `/api/meta` answers with `own_keys`). The passcode is still needed:
the owner's Mac still records the game. To use your own Claude account, run your own engine (next paragraph).

**On the hosted site: Your engine.** To use the site with your own Claude account (no API key, no passcode), run the
engine on your own Mac and point the site at it: open the key icon's *Your engine and keys* dialog, keep *My own engine*,
and follow its three steps: (1) `claude` once to log in, then `CBJ_PLANNER=claude` and `GEMINI_API_KEY=...` in
`cbj-creative/.env`, proved by `uv run cbj setup-check --live`; (2) start it for the site with
`CBJ_CORS_ORIGINS=https://cbj-creative-studio.vercel.app uv run cbj ui`; (3) paste `http://127.0.0.1:8765` (or a tunnel
URL) and press *Check*. From then on the browser calls your engine directly for everything (the site's relay and the
owner's engine are not used); Chrome, Edge and Firefox allow it, Safari needs a tunnel URL. See web/README.md, "Use the
site with your own engine".

## Designer feedback and the owner's lessons (2026-10-18, evening)

The site will be used by many designers and the workflows are tuned by hand, so the tool collects what designers
report and turns it into a document the owner reads before changing anything. Nothing in it touches a creative or a
workflow (`tests/test_feedback.py` checks that no pipeline module imports either part).

**Feedback** (`src/cbj/feedback.py`, `POST/GET /api/feedback`, `GET /api/feedback.md`, `uv run cbj feedback`, the site's
*Give feedback* button next to a creative, in the edit workspace, on a showcase page and in the header). A record is
`{designer, page, area (13 words: level, ending, captions, tempo, look, sound, hud, hands, edit, understanding, speed,
website, other), kind (wrong, missing, good, idea), what happened, what was expected, rating 1-5}` plus the **scene**
the engine captures itself from the version the designer looked at (workflow, prompt, summary, length, the earlier
prompts of that creative): a correction record in the sense of COLLEAGUE.SKILL (arXiv:2605.31264, §4.2). Append-only in
`studio/_feedback/records.jsonl`.

**Lessons** (`src/cbj/lessons.py`, `GET/POST /api/lessons`, `uv run cbj lessons [--distill | --correct TEXT | --rollback N]`,
the site's `/feedback` page, Lessons tab). The planner's model reads all records and the prompts behind them and writes
one package with two tracks, the paper's dual representation cut to this tool: Part A, per workflow, what the workflows
should do differently (lesson, evidence ids, suggested change, strong or thin); Part B, per designer, what they ask for
by default and the phrasing the tool may read badly (so the owner can tell a system fault from one person's taste);
then open questions for the designers. Code keeps it honest: a lesson without an existing record id is dropped and
listed, one-record lessons are `thin` whatever the model said, a designer entry needs that designer's records. Every
distillation is a new version in `studio/_lessons/v<N>/` (`lessons.json`, `LESSONS.md`, `meta.json` with the record ids
and the model); a correction in the owner's words is recorded and applied in the next version; rollback moves the
pointer and deletes nothing. First live run: 4 test records → LESSONS v1 in 16.5 s with one strong and three thin
lessons and four open questions. Design and the paper's reading: `~/rollic-case/FEEDBACK-AND-LESSONS-2026-10-18.md`.

**Added 2026-10-19: feedback under every result, tied to the step; the analysis; the report.** A record now carries
`step` (the engine's own stage names: plan, level, recording, compose, review, revise, proof, result, other; words in
`feedback.STEP_WORDS`, served as `features.feedback_steps`) and `item` (the exact row or caption the designer pointed at),
and the engine captures `process` from the stored version: the stages and seconds, the route and the planner's declared
groups, the control rows that are not default, the checks that failed, the edit report's rows and pixel facts, the viewer's
review, the revision, and the engine's own log lines (the web API keeps every finished job's lines in
`studio/<id>/v<n>/log.json`; a plan job's lines travel in `brief.planner.lines`). `GET /api/feedback/<id>` returns the
record with the slice of the process its step points at; `POST /api/feedback/<id>/analyze` (owner-triggered, one model
call) explains what happened and why from that evidence only, with a verdict *system / taste / unclear*, the quoted lines
(unbacked quotes are listed apart) and the smallest change; the lessons' traces carry the step and the analysis. The
report of a version, `GET /api/report/<id>?version=N&format=md|html` / `cbj report <id> [--base N] [--format html] [--out F]`
(`report.py`), lists the request, how it was read, every step with its seconds and lines, the level and the play, the
checks, the edit report, the review, the revision, the feedback left on it and the files; the site's Edit workspace shows a
designer only the video, the change, what changed and what was kept, and offers the report for the rest
(`web/SPEC-FEEDBACK-INLINE.md`). Still zero effect on the workflows (`tests/test_feedback.py`).

## The optional soundtrack (2026-10-18, night)

`uv run cbj soundtrack <creative_id> [--base N] [--voice] [--line "..."]`, `POST /api/soundtrack`, the site's *Soundtrack
(optional)* card. NVIDIA build has no music-generation model (checked with the key: its audio functions are
text-to-speech), so the bed is **synthesised from facts**: the version's theme sets the mode
(major for game, candy, pastel; minor for neon, dark), the tempo and curve set the pulse (84/104/124 bpm, ramping when the
play speeds up or slows), the parts manifest places a stinger under the hook, the pulse only while the play runs, a pad
under the end card and the exact length, every block exit gets a pluck one scale step higher at its second, the ending
gets a resolve chord (win), a riser with hurry ticks (near-fail), an unresolved chord (cliffhanger) or a low drop
(time-out), and the clock ticks at five seconds or less. With `--voice` **NVIDIA Magpie TTS** (`uv sync --extra voice`, `NVIDIA_API_KEY`; English voices only) narrates the
creative's own captions as they appear on screen (the hook, the play captions, the end card's fact and call to action;
`00:03` is said as "3 seconds"; `--narration hook` for the hook alone; `--line` replaces the hook's words), each line
placed at its caption's second and mixed in, ducking the bed. At creation time, `cbj make "..." --audio bed,voice` (the
site's *Audio (optional)* section before Generate) runs the workflow unchanged and then adds the soundtrack through the
same music edit, so the creative comes out with audio in one job (the result is v2; v1 is the silent original).
The result is an ordinary uploaded sound file (`studio/uploads/soundtrack-*.wav`); putting it in the ad is the existing
music edit (`{"music": name}`), a new version with the edit report. No workflow or compositor code changes. Module
`src/cbj/soundtrack.py`; tests `tests/test_soundtrack.py`; design and measurements: `~/rollic-case/SOUNDTRACK-2026-10-18.md`.

## The website (web/, on Vercel)

`web/` is a Next.js app, live at https://cbj-creative-studio.vercel.app, that puts the same four workflows
behind the Stitch design ("Color Block Jam Studio": Create, Edit, Showcase). It reimplements nothing: the
browser calls this engine's HTTP API (`/api/plan`, `/api/make`, `/api/direct`, `/api/review`, `/api/upload`,
the jobs, the files under `/studio/`) directly, through a tunnel to the Mac that runs `cbj ui`. The web app's
own server does two things only: the passcode (`STUDIO_PASSCODE`: Generate, Apply, Review and uploads need it
once; browsing never does) and the engine health check. Design, data shapes and flows: `web/SPEC.md`; how to
run and deploy: `web/README.md`.

- **Showcase** (`/showcase`): ten finished creatives exported from `studio/` with their evidence (video, the
  brief's eight rows, level and moves, the checks, the viewer's review, the edit reports), so the site demonstrates
  the tool when the Mac is off. `uv run python web/scripts/export_showcase.py` refreshes it (the list of
  creatives is at the top of that script; videos are re-encoded to 720p for the web).
  More finished creatives, about 100, can follow them from a public Cloudflare R2 bucket with the Mac off and no
  redeploy (`scripts/r2_publish.py`, `NEXT_PUBLIC_CATALOGUE_URL`): see web/README.md, "The catalogue on Cloudflare R2".
- **Putting the engine online**: `scripts/engine-online.sh` starts a second engine instance on :8766 with an
  access token (`CBJ_API_TOKEN`, kept in `.engine-token`), the tunnel host allowed (`CBJ_ALLOWED_HOSTS`) and the
  site's origin allowed for browser calls (`CBJ_CORS_ORIGINS`), opens a Cloudflare quick tunnel to it, writes the
  tunnel URL and the token into the Vercel project's env (`ENGINE_URL`, `ENGINE_TOKEN`) and redeploys. The header
  of the site then says "Engine online"; `scripts/engine-online.sh stop` takes it down and the site falls back
  to the showcase. The quick tunnel gets a new name on every start, which is why the script redeploys.
- **Engine side** (all env-gated, nothing changes when the variables are unset): with `CBJ_API_TOKEN` every `/api`
  call except `/api/health` and `/api/sprite/*` needs `Authorization: Bearer <token>`; `/studio/*` files stay open
  so `<video>` and `<img>` can load them. `GET /api/health` is new (up, busy, which planner).

## The viewer's review (the evaluation loop)

The checks prove the gameplay and the edit report proves an edit; the viewer's review (`review.py`) is the
third judgement: a multimodal model looks at a contact sheet of the finished ad (one frame a second, the
second under each) as a person scrolling a feed, sound off, and answers a fixed rubric against the prompt
and the plan: does what is seen match each of the eight controls (match / partial / no, with the seconds);
scores for pace, readability, clarity and the call to action; would it download and why; up to three fixes
and one edit prompt that applies the best one. Two scores are measured in code and given as final, never
estimated: the second the game first moves, and the share of the ad that is a held screen; each caption's
time on screen is checked against its reading time. The UI's "As a viewer" card shows the review (made
with the version when "review as a viewer after making" is on, or on demand) and applies the suggested
edit with one click, so the loop is: make, review, edit, review. `uv run cbj review <creative> [n]`
prints it; `review.json` and `review_sheet.png` sit next to the version. The rubric is in the skill
`.claude/skills/cbj-creative-review/` and checked against the code by a test.

### The asked-facts audit, the game's rules, and the revision round

A viewer's review judges the soft side; the countable side is measured (`audit.py`, 2026-10-15). The audit reads
the measurable facts from the prompt itself, never from the plan, so a plan that quietly dropped something is
caught: the block count, how many colours ("six colored blocks" is six colours), how many pieces a viewer can tell
apart (blocks of one colour that touch read as one), the colours named, the board shape and looks, the difficulty,
the blocked attempt and which colour stops it, the case's 30-60 s, the asked length, the seconds left, the mistakes,
the order of interactions, the satisfying finish, the ending, and every quoted caption. Each row says whether it was
met and, when not, which stage missed it (the plan, the level, the play or the ad). The game's rules are then
replayed on the game's own record of the drags, as the Unity project defines them (`InputHandler`,
`BlockMovementService`, `ExitService`, `GameManager`, re-read on 2026-10-15): one block a drag, the pivot through
neighbouring free active cells, an exit only through the first door of its own colour it touches with a clear lane
and only during a drag, the clock counting down and never below zero, the result consistent with the blocks gone.
All of these rows join the version's checks, so the UI shows them and the review gets them as facts.

The loop closes in two places. At the level stage, a miss the generator can fix (the count, the colours, a named
block, the first blocked attempt) makes the studio generate again with other seeds and use the board with the
fewest misses. After the make, the loop runs by default ("evaluate, feed back, revise", `revise` on `/api/make`, off with `revise: false`; up to two rounds, stopping when nothing measurable is missed): it turns the
measured misses and the viewer's verdict into an edit request, plans it as an edit of the made version, makes and
reviews the revised version, and records what it fixed (`version.revision`). The first version is never lost; the
case's own workflow (generate, review, request a modification, generate the revised version) is run once by the
tool itself.

## Two workflows, one evaluation each (2026-10-16)

Creating a creative and editing one are separate agentic workflows, in separate modules, so a change to one cannot
touch the other (`src/cbj/workflows/create.py`, `src/cbj/workflows/edit.py`; `app.py` only dispatches: a request that
names a creative, or attaches one of the tool's own videos, is an edit). The UI has the same two sides ("Create a
creative", "Edit a creative"); the Edit side needs a creative chosen from the list.

- **create**: plan (references analysed), level, play, ad, the viewer's review, then the loop: the measured misses and
  the viewer's first fix go back to the planner and a revised take is made (another seed when the board, the play or
  the length missed), up to two rounds. Its evaluation is the text-to-creative profile: the board, the play, the
  rules, every fact the prompt asks for, the case's rows.
- **edit**: the route from the version's parts manifest, a direct edit in code or the planner with the route, the edit
  report, the viewer's review against the edit, then its own loop: items the report says changed without being asked,
  the facts the edit asks for that are not so, and the viewer's fix. The rules are re-checked only when the play was
  re-filmed; the case's rows are not repeated on an edit.

A third workflow was split off the same day for a prompt plus media (`src/cbj/workflows/guided.py`): a new creative with
a video attached, or with an image the words make a reference ("inspired by this image"), is guided; a prompt alone stays
with create. It reads the media for the request first and is evaluated with the reference rows on top of the
text-to-creative profile (see "Video-guided generation (core requirement 4)").

Each version records its workflow and its evaluation profile (`version.json`: `workflow`, `evaluation`), and the
checks show a "facts read from the prompt" row, so what was audited is visible. Rows added on 2026-10-16 for the
case's controls the audit did not measure: the hesitations (counted from the play's beats), the clock (a win's start
value from the level), the walls (count, "several separate" = two or more groups), the HUD level number, blocks per
colour, the cursor, the background (the poster's margin pixels against the named colour's family), the music, the
sequence (the win first, the replay, the end card, the result screen), the game's own look when the prompt asks for
the original rules, HUD or assets, each quoted caption's moment (at the start, on the wrong move, on the correction,
when a colour leaves, on the result, in the last seconds, at the cut) read from the parts manifest, and the case's
"gameplay at the centre" (p.2: the share of the ad that is play, replay or the result clip; under 40 % fails). The
check of this coverage against the case and the game's rules is in `../EVAL-COVERAGE-2026-10-16.md`.

### What the 2026-10-16 scenario batch changed in the create workflow

Twelve prompts (three puzzles x clean solve, near-fail, out of time, cliffhanger; `../t2c-scenarios-2026-10-16/`)
run on the Claude planner with the loop on. The real misses were all in the time-outs, and the causes are fixed:

- the play planner adds a hidden step to a time-out ("a block no step names leaves last", the one the clock cuts
  short) that the level generator never checked, so it accepted boards on which the asked order was impossible
  with that step and the play dropped the whole order; `generate._events_fit` now fits it (50k states), and the play
  keeps the order and cuts the last named block short when only that step fails;
- the play's order search gave up at 50k states on a 6x8 board whose order solves at 200k; it now tries 8x deeper
  once before giving up;
- a stuck step that names who is in the way ("red stopped by a green block") on a board that offers the attempt
  with another colour: the generator relabels the two colours on the blocks and their doors (the same puzzle) so the
  asked blocker is the one in the way (`generate.named_blocker_swap`);
- a clock the request names is used as named (`play.ASKED_CLOCK_MARGIN_S`); the HUD turning red under 0:50 is noted,
  not avoided by raising the clock;
- a revision round keeps the asked length and ending (`workflows.create.keep_asked`), and a round whose change made
  no difference is recorded as "unchanged" with the engine's reason;
- the level and recording caches carry the generator's and the play planner's versions, so a fix produces new boards
  and films instead of reusing old ones.

## Editing the delivered video, not regenerating it (case p.7)

An edit is a change to the stored creative (`ad.json`), rendered again from the same cached recording. For an edit
that only changes layers inside their existing frame windows (a caption's words or colours, a picture swapped in its
slot, a picture put on the walls), the compositor does not even render the whole ad again: `compose.render(...,
patch_from=<the approved ad's folder>)` finds the GOPs of the approved MP4 that hold a changed frame, draws and
encodes only those (the same encoder, the same keyframes), cuts every other GOP out of the approved file without
decoding it, and joins them. The result decodes frame for frame like a full render (the encoder is bit-exact, so a
test checks `framemd5` of both); `compose.json` records `patched` (GOPs rendered, frames copied) and the edit report
says it in words: "1278 of 1350 frames are the approved video's bytes, 1 of 10 GOPs were rendered again". When the
sound mix is identical, the approved video's audio stream is copied byte for byte as well (`patched.audio_copied`).
The report also carries a ten-point preservation checklist (level, moves, move timing, gameplay render reused with the
recording hash, duration, camera, HUD, captions, pictures, audio; each a fact with its evidence), the edit's "changes
X; preserves Y" line in the case's words, and the Timing row's numbers before and after (fps, length, the play window,
the first move, the drags, the clock). A test runs three edits in a row and proves nothing unrelated drifts. An edit
that moves a boundary (timing, a part's length) or re-films the play is rendered in full, as before. Generative video
editors (Runway Aleph, Kling object replacement, open-source inpainting such as ProPainter or EffectErase) were
considered and not used for gameplay: they re-synthesise every pixel, cannot keep the game's rules or the HUD clock
true, and offer no proof of what changed; they remain an option for a hook or outro clip outside the gameplay.

### The 48-prompt audit of 2026-10-15 and what it changed

`~/rollic-case/t2c-audit-2026-10-15/` (28 prompts from the case's author plus 20 time-out, near time-out and length
scenarios, all made and reviewed, nothing edited) found seven things, fixed the same day: the audit's count regexes
(counts of blocks left and near-fail words were read as asks: 9 false flags); an asked caption whose moment the ad
does not draw (the result caption after a clean win, the fix caption) now goes on the nearest moment the ad has
(`ad.py`); "several fixed walls" are several separate wall cells, not one pillar (`generate.holes_for`, GATES v7);
two blocks of one colour never touch on a board that is not packed (colours spread, mirror pairs coloured apart,
searched until clean); a solve short for a long ad is paced "slow" and the player hesitates (`studio._short_solve`,
`_breathe_short_play`); a wrong move by a named block that gets in another block's way is an event (`blocks`, with
`by`; `play.blocking_moves`) read from the words when the model misses it, and a mistake count in words ("one
unhelpful move", "two wrong moves") is applied; a named palette is exclusive, and when every named colour is pointed
at as one block the board has one block per colour. Tests: `tests/test_audit_fixes.py`.

### Routing an edit: the parts manifest, three analysis levels, no video analysis for our own creatives

Every version is written with `parts.json` (`src/cbj/parts.py`), the metadata an edit is routed on: the ad's parts in
order with their seconds and the brief field that controls each, every caption and picture with its seconds on screen,
its box, its text or file and its field, the sound and the music, the gameplay's moments on the ad's clock (the first
move, each drag with the block's colour, the wrong move, each exit, the win or the time-out) and when the game's timer
shows each whole second. It is built from the files the tool already keeps (ad.json, compose.json, the recorder's
result, play and frame logs, the level) with no model and no look at the pixels, and the UI links it as "parts
(metadata)" (`/api/parts/<id>?base=N`).

Before an edit is planned, `src/cbj/route.py` decides its type and analysis level in code from that manifest, in the
research note's terms (analyse only what is necessary, modify only what is requested, preserve everything else):
- **Level 0, direct**: the target is a known layer (the hook, the logo, the music, the texture on a block, the end
  card's title). No video analysis. When the request carries the new value itself (a quoted text, an attached file,
  "turn the sound off"), the brief is changed in code with no planner at all (`edits.direct_edit`, "a direct edit,
  made in code"); otherwise the planner gets the route with the edit ("change the background behind the board...":
  the field is named, the value is the model's reading) and is checked against it afterwards: on a route that does
  not change the play, `route.verify` restores any level, move, clock or length change the planner made and says so.
- **Level 1, targeted**: the target is a moment ("the caption that appears when the timer reaches five seconds",
  "the caption just before the win", "at 0:12"). It is placed on the timeline from the manifest's clock readings,
  moments and parts, and the caption on screen then is the target; when the ad has no such moment or no caption
  there, the route says so with the captions it does have. Only when the metadata cannot place the moment, and only if
  a multimodal model is available, a contact sheet of the ad is read to find the second (`route.locate_with_vision`,
  the NVIDIA omni model or the Claude backend; off with `CBJ_LOCATE_BY_VISION=0`). This is the optional use of video
  analysis: for a creative the tool made, the metadata is enough.
- **Level 2, full**: a video the tool did not make is read as a whole with the multimodal model: a reference video
  (case p.6) or an uploaded MP4 that matches none of the tool's versions. An uploaded MP4 that *is* one of the tool's
  versions (the test folder's base creatives, for example) is recognised by its bytes (`route.match_upload`) and the
  edit is routed to that version's metadata: the UI opens it and plans the edit from there, with no analysis.
A request that changes the puzzle or the play (a second mistake, a harder level, another ending) is routed as a
retake (the game films it again, keeping what still fits); one that changes the play and asks to keep every frame is a
contradiction and is refused as such. The route is shown in "What I understood" (type, level, target with its seconds,
whether the gameplay render is reused, whether any video analysis runs, what is preserved), the planner's edit prompt
carries it as the minimal edit plan, and the edit report ends with a route chip: did the result follow the route (the
gameplay render reused as routed, or a retake as routed). Tests: `tests/test_route.py`.

## Pictures an ad can use

Three sources, all by file name in the prompt: files dropped into the UI (`studio/uploads/`, listed as "Uploaded
before"), the game's own 2D art from the case folder (`Assets/Sprites/UI`: the coin pile, the stopwatch, the blue
toy-brick start background usable behind the board or on the end card, the green button, the Level Completed and
Out Of Time banners, the icons), and the test pictures in `~/rollic-case/case-test-2026-10-14/assets/` (drawn by a
script, plus twelve OpenMoji pictures under CC BY-SA 4.0 for the toy-themed prompts, with the licence next to them).
Slots: a logo or sticker in the top-left corner, a sticker in the top-right corner, the icon beside the hook, the
end-card picture, the end card's background, the button, the cursor, and the obstacle: "use this object instead of
the current obstacle" draws the picture on the board's walls (the game's holes) in perspective during the play. The
cells are fitted to the screen from the recorded block positions (an exact homography: the board is a plane under
a fixed camera), one picture per rectangular wall group, so the game itself is untouched and the edit report proves
the changed pixels sit inside the walls' box. On a board without walls the picture goes beside the hook, and the
plan says so. A texture on one block ("apply this ice texture to the blue block", 2026-10-15) is the `skin` slot:
the recorder logs every block's screen position on every frame, so the compositor maps that position back to board
cells through the inverse homography and draws the texture on the block's cells frame by frame, following the block
through its drags and its lift and vanishing at its exit, with a multiply blend (the texture is lightened first) so
the brick keeps its studs, its light and its colour identity. The game, the block's shape and its moves are untouched;
the edit report proves the changed pixels follow the block. A texture on a door or a gate is still refused. A request
that names files it did not attach
stops with a question (see "Controlled editing").

A generated or scanned picture on a plain background (a Higgsfield or GPT image on white) becomes a sticker on its way
in: `draw.cutout` floods the background from the four corners and trims to what is drawn, deterministically, for the
logo, sticker, icon, end-card picture, button and cursor slots (never for a wall tile or a background, which fill
their box). A picture that already has transparency is left as it is.

## Reference images and videos (case p.6)

The planner is a text model and sees only file names, so a reference file is analysed first
(`reference.py`): an image gets a measured palette (PIL, no model) and a multimodal model's
description; a video is read for the request, whole, by Gemini (NVIDIA build as the fallback) on both planner backends, and its
parts are measured afterwards only when the reading needs it (2026-10-16; see "Video-guided generation (core
requirement 4)" below: the reading plan, the format step, the checks in code, the parts snapped to cuts). A prose
answer is asked again strictly; a fail screen seen in the clip makes the ending a
fail even when the model wrote near-fail. The notes go to the planner, are
written into the brief (`planner.references`) and shown on the page ("Read from the attached
image ..."). A video is never placed in the ad; an image is placed only when the prompt asks
to put it somewhere. A file that could not be read is said so, never guessed about. Uploads are
checked by content (PNG, JPG, WebP; MP4, MOV, WebM up to 80 MB).

**The role of an image** (`imageref.py`, 2026-10-15). The case names four roles for an image, and the tool decides which
from the request's words and from what the model saw (its `kind`: photo, illustration, game screenshot, logo,
character, pattern; and a `board` object it is asked to fill when the picture shows a puzzle board):
- *style* ("inspired by this image", "use its colours", "design transfer", "same style", a reference prompt with no
  placement words): a style kit is measured from the image's palette in code: the background behind the board (the two
  dominant soft colours, lighter at the top; the darkest two on a dark image), the captions' fill and outline checked
  for contrast against that background, the blocks mapped to the game's seven colour slots by hue (only when the
  request mentions the blocks, the pieces, the whole look or a design transfer, never when it says to keep the game's
  block colours, and only when the image has two or more distinct saturated hues), and the end card's gradient, which
  follows the background. The visuals row says what was taken and the assumptions list it ("ref.png is used as a style
  reference: background #F7EDE3 to #E9D4C0; captions ...; blocks red as crimson ...").
- *composition* ("a game like that", "a level like this board", "recreate this layout", or a reference prompt with a
  board the model read): the board's grid, block count, colours, crowdedness, walls and symmetry become the level spec
  (size, blocks, colours, packed / spacious / symmetric, the walled shape) and a similar level is generated in that
  spirit. The exact layout is not copied cell by cell: the doors and the solution are the generator's, so the puzzle
  is always playable, and the level row says so. A "game like that" prompt with a picture that is not a board falls
  back to the style role.
- *asset* ("put our logo", "this mascot beside the hook", a logo the model recognised with "our" or "brand"): placed by
  the planner's placement rules, as before.
- *modify* ("use this object instead of the current obstacle", "apply this texture to the blue block"): the walls or a
  block's texture, as before (case p.4 and p.6).
An image can carry two roles at once. The page shows the role under "Read from the attached image" and the UI's test
folder has a set for each role (`~/rollic-case/test-assets-2026-10-15/req3-images/`, plus the image-role set made on
2026-10-15). Tests: `tests/test_imageref.py`.

## Video-guided generation (core requirement 4)

The case (p.6) asks that a reference video's concept, structure and pacing be understood and adapted, "e.g. based on
this video, create a Color Block Jam version of this concept". The tool generates and edits no image and no video: the
reference is read and understood according to the request, the findings become inputs to the plan (the level spec,
the play, the captions, the look, the timeline), and the ad is still the Unity recording composed by the tool's own
compositor. The contract is `../REQ4-SPEC-2026-10-16.md`.

**Its own workflow.** A prompt plus media is the guided workflow (`src/cbj/workflows/guided.py`, `WORKFLOW = "guided"`):
`app.workflow_of` sends a new request there when a video is attached, or when an image is attached and the words make it
a reference (`reference.is_reference_prompt`); a prompt alone goes to create, a named creative to edit. The prompt is
never optional and drives everything: what the video is read for and every value it states itself. One of the tool's
own MP4s attached with words that point at it as a source ("a version of this concept", "same idea", "inspired", "the
hook from this video", "the pacing of this clip", "the way this video ends", "like this", "match the look of this",
"take ... from", "only the hook"), or with a request that describes a creative of its own (its length and its ending)
and no edit word, is guided too; with "same ad but", "keep everything", or "keep", "change", "replace" before any source
word it is an edit as before (`route.upload_intent`, checked before the bytes route it). `guided.make` runs the shared engine as `create.make` does and records `workflow: guided`.

**The reading, in this order** (`reference.read_video`). Every reference is read in full (2026-10-17, the owner: "the
video model always analyses the general concept of the reference; when the user says specific things, the model
focuses on them as well"); the reading plan's focus and level decide what is applied to the brief first (the analysis
records `read_all: true` and `applied`: the focus), and what the request leaves open is filled from the general reading
(2026-10-17, round 2 case 14: the board, the ending, the flow, and the screen of a Color Block Jam reference, each only
when the request states nothing about it and has no "only", "just the", "nothing else", "everything else is mine" or
"the rest is mine"; never the look; `videoref.open_aspects`). The pacing is applied only when the request asks about it,
and the play is one decision (`videoref.play_levers`): the play seconds first, then the tempo and the moves (the pacing's
rate kept in the reference's class, or a calm fill), the blocks raised to supply them; a guided revision restores what
the request states (`guided.keep_stated`), keeps what the reference set (`guided.pin_reference`) and re-derives the play
from the take's measure (`guided.play_again`); a viewer's note on what was not asked starts no revision, and the final
version is the best one (`guided.best_version`); with the clock hidden the result caption carries a near-fail's seconds
in one line (`videoref.hidden_clock_captions`); a hook is taken by its kind (`videoref.hook_kind`, `audit.hook_row`); a
restored field takes its plan text back (`guided.restore_texts`); a stuck moment names one piece (`videoref.stuck_step`,
info row `audit.stuck_row`); a wall cell off the reading never cuts the blocks read (`videoref.WALL_SLACK`); the play
decision turns the hesitations too and names the limit that stops a short play; a revision never lengthens a take
that ran over the stated length (`guided.length_guard`), and one the viewer alone started must change what the viewer
pointed at (`guided.viewer_points`); a taken pace wins over the fill, and a rule that changes a planned value removes the
plan's words for the old one (`videoref.correct_texts`). Each filled line is marked "filled from the reference
(the request left it open)" in `brief.reference.adapted` and `filled`, shown on the card, and its rows in the
reference group are info, not failures. The request's own words always win, its ending words too ("before solving
it", `videoref.ENDING_STATED`); a request naming the cursor alone takes only the cursor (`videoref.cursor_only`):
1. *The request first.* One call to the planner's own model (the Claude CLI or NVIDIA text, the client `planner.plan`
   uses), with the request's words and the file's format facts (name, length, size, orientation; nothing about its
   content), returns a reading plan (`reference.ReadingPlan`): the focus (concept, hook, pacing, captions, ending, look,
   structure, board, board_colours, screen), the level (none, targeted, full), the questions, the fields required, what to ignore, what the request
   already fixes, and why. The focus is checked against the allowed set; an empty or invalid plan falls back to the word
   table (`reference.focus_words`: "version of this concept", "adapt", "same idea" or no words at all = concept, full;
   "hook", "opening" = hook; "pacing", "tempo" = pacing; "board", "level", "grid", "layout", "blocks", "pieces" = board;
   and so on), and says so. The table also checks a good plan: a
   focus the words name and the plan lacks is added; one the plan has and the words do not is kept and logged.
2. *The format step.* Any container, codec, orientation, frame rate or size becomes one small copy
   (`reference.normalise_video`): ffprobe for the facts, ffmpeg to H.264, 360 px on the short side, the rotation
   applied, no audio, the whole clip at `max(2, min(8, 200 / length))` fps (about 200 frames). The 24 s cut is gone:
   `analysed_s` is the clip's length. Uploads over 120 s are refused with the reason (the case's references are 30-60 s).
3. *The prompt the model sees* (`reference.video_ask`): a fixed preamble (adapt, never copy frames; only the clip's
   clock; no invented mechanics; what is seen apart from what is inferred), the request quoted, the plan's questions
   and ignore list, the clip's length as the only time reference (no cuts, no motion: the understanding comes first),
   and the schema with the general fields and the plan's required fields marked REQUIRED (plus `moves_by_third`,
   `mistakes` and `mistakes_shown` whenever the focus covers the pacing or the ending: the code computes from them).
   **The general reading, always** (`reference.GENERAL_QUESTIONS`, `GENERAL_FIELDS`): what the video shows and what
   happens, in order; which game it is (Color Block Jam itself or another); the concept in one line; the board
   (`reference.BOARD_QUESTION`); the ending, with a fifth wording, "it stops mid-level (no result, no question)", read as
   the game's cliffhanger; the hook; the captions word for word; the HUD at the first frame of play (`hud`: the level
   label, the clock, the last clock); the mechanics and anything on screen the game does not have (`extras_seen`:
   booster buttons, power-ups, other menus). The plan's own questions follow under "THE USER ASKS IN PARTICULAR", as
   priorities. The schema's `board` field asks
   for the columns and rows at the first frame of play, the shape (open, narrow_center, door, holes, cross, ring,
   lanes, each described in one sentence; read from the outline and the wall cells only), the blocks (only the coloured
   blocks that leave through gates, never another game's obstacle), each distinct colour once, named as seen (two
   colours that look different get different names: telling the reader to name them as the game's seven turned the
   trailer's magenta into purple and its teal into blue), the pieces (small, long, big, varied, mixed), how many sides have
   gates, the obstacles inside the board that are neither a block nor a wall, and how busy it looks. The board is no
   longer in the default ignore list (the other game's art and its exact caption wording still are).
   The schema (v2, after the accuracy measurement on the tool's own 12 creatives,
   `../req4-e2e-2026-10-16/READING-ACCURACY.md`): the structure example has no numbers to copy (`<seconds>`; every
   reading had put the hook at 0-3 s), a part ends where what is on screen changes and the hook part when the opening
   caption leaves; `captions_seen` are the ad's captions word for word, the end card's title, line and button included,
   and `screen_text` is the gameplay's HUD only (v3: any `screen_text` entry that is not HUD by pattern, such as a level
   label, a clock, "+50", REPLAY, Continue, Level Completed / Failed, Out of time, is moved back into the captions in
   code, `reference.captions_from_screen_text`, recorded as `validation.captions_moved`); the four endings are named
   (near-fail = a win with 5 s or less on the clock); wrong moves are a list (`mistakes: [{at_s, what}]`, only moves
   the player visibly corrects or a block stopped by another, never a drag the clock cuts short or a hesitation) beside
   the model's own yes/no (`mistakes_shown`); the moves counted in each third of the gameplay (`moves_by_third`).
   It goes with the copy to Gemini first, NVIDIA build second (`reference.video_client`, a `VideoReader`, on either
   planner backend):
   - Gemini (`src/cbj/gemini.py`): `gemini-3.5-flash-lite` (`GEMINI_MODELS`, overridable with `CBJ_GEMINI_MODELS`),
     the copy sent inline, the answer asked as JSON (`responseMimeType`), low thinking (`thinkingLevel: low`),
     temperature 0.2, 300 s; HTTP 429/500/502/503/504 retried after 10, 20 and 40 s, except a 429 whose quota is per
     day (`quotaId` with "PerDay"): that model is used up for the rest of the process, never called or waited on
     again, and "gemini-3.5-flash-lite: daily free quota used up (500 requests)" is said once per reading, in
     `errors`, `quota` and on the card (2026-10-17: with the daily quota gone, every call had waited 70 s before
     NVIDIA answered).
   - NVIDIA build when Gemini raises (no `GEMINI_API_KEY`, or no Gemini model answered): `nemotron-3.5-super-vl`
     first, the 30b omni model second, 8000 tokens and 300 s, an answer cut off by the reasoning asked again with
     twice the budget, the same backoff.
   - `CBJ_VIDEO_READER=nvidia,gemini` (or `gemini,nvidia`, the default) sets the readers' order
     (`reference.reader_order`); the log ("readers: nvidia first, then gemini (CBJ_VIDEO_READER)"), the analysis
     (`reader_order`) and the card say which order was used. NVIDIA build's reasoning cannot be switched off (every
     reasoning switch gives HTTP 500), so its board stills have their own budget (step 3c).
   The analysis records the reader (`reader`: gemini or nvidia), the model, Gemini's token counts (`usage`: prompt,
   candidates, thoughts) and every failure on the way, from both readers (`errors`). A broken JSON answer is asked
   again strictly, as before. The shared client (images, the viewer's review, `route.locate_with_vision`) is
   unchanged: NVIDIA, omni first, 1500 tokens.

   **Why Gemini first: measured on the tool's own 12 creatives** (all four endings, neutral file names, the same
   reading pipeline and the same truth: `../req4-e2e-2026-10-16/READING-ACCURACY-gemini.md`, fraction right):

   | field | Gemini 3.5 Flash-Lite, low thinking | NVIDIA super-vl |
   |---|---|---|
   | ending (whole clip only) | 12/12 | 9/12 |
   | hook, call to action, captions | 12/12 each | 11/12 each |
   | mechanics (no false claim) | 12/12 | 12/12 |
   | mistakes | 9/12 | 7/12 |
   | structure (parts right) | 8/12; 37 of 44 boundaries within 1 s, mean error 0.5 s | 5/12; 32 of 59, 1.3 s |
   | pacing | 5/12 | 6/12 |
   | time per reading | 4-26 s, no errors | 50-250 s, with HTTP 500s and reasoning loops |

   Through the tool's own reader the ending was 9-10 of 12 (v5, v5b, v6: the whole-clip read samples thinly at the end,
   and two cliffhangers and a clean win were misread), so the ending is now read a second time on the last seconds
   (step 3b below). With it, the latest pass (`READING-ACCURACY-v8.md`, a fresh pass after the rules were fixed) reads:
   ending, hook, call to action, captions and mechanics 12/12; mistakes 8/12; structure 9/12 (40 of 45 boundaries
   within 1 s, mean error 0.4 s); pacing 5/12. Every reading was answered; 503 and 429 under 12 parallel reads on the
   free tier were absorbed by the backoff, and once the second read fell back to NVIDIA (110 s).
3b. *The ending, read a second time on the last seconds* (`reference.read_ending`; skipped for clips under 12 s). After
   the whole-clip read passes the checks, the last 10 s are cut from the copy at 8 fps (`tail_copy`) and the same reader
   gets one short question (`ending_ask`): which of the four endings, the last clock reading as MM:SS, whether a win
   screen, an out-of-time screen or a question caption is shown, as JSON. It is stored as `analysis.ending_read`
   (ending, last_clock, win_screen, out_of_time_screen, question_caption, why, the cut, model, reader, seconds): median 14 s on the v8
   pass, 3.9-111 s with 12 clips read in parallel on the free tier. When it disagrees with the whole clip's ending it wins: `notes.ending` becomes its ending, the
   whole clip's word is kept as `notes.ending_whole`, the disagreement is logged and kept (`ending_read.overrode`). Its
   transcription (the clock, the screens) was right in every reading measured; its ending word not always, so
   `videoref.mapped_ending` checks it against that transcription: a near-fail whose last clock is over 5 s is a win,
   and a cliffhanger with a win screen transcribed falls back to the whole clip's ending. Every reading prompt also
   carries one fixed question naming the game's four endings (`reference.ENDING_QUESTION`).
3c. *The board, read a second time on a still* (`reference.read_board`, on every reading). The whole
   clip is read at 360p, where another game's board is a few hundred pixels: on the owner's test (a 15 s landscape ad of
   another block game) the whole-clip read gave a 5x5 board with 7 blocks and no obstacles, for a board of about 12
   blocks with four bubble obstacles. So one still of the original file at the first frame of play (0.3 s into the
   first part with play on screen, `board_at`; at the source's resolution, at most 1920 px on the long side, 1280 px
   when NVIDIA reads first, `board_still`, `still_px`) goes to the same reader with the board question, the board's box (x, y, w, h, normalised) and what
   else is on screen that the game does not have (`board_ask`). When the box is under a quarter of the frame (the
   owner's trailer: a portrait game window in a 1920x1080 frame), the still is cropped to the box with a 10% margin,
   enlarged to 1024 px when smaller (`crop_to_box`), and the board is read once more on the crop, which wins only
   when it agrees with the full frame's reading (size within 2 cells a side, blocks within 40%, half the colours;
   `crop_disagrees`, else "the crop disagreed: kept the full frame's reading" and no code measure on it); a box whose
   width:height is more than 40% off the board's columns:rows is not cropped at all (`box_disagrees`; round 1, third
   run: LolTap's 6x6 board boxed as a tall strip read as 6x10 with 4 blocks). The
   board wins over the whole clip's (kept as `notes.board_whole`); the full frame's extras join `notes.extras_seen`;
   the read is stored as `analysis.board_read` (board, at_s, width, height, box, board_frame and crop when cropped,
   extras_seen, model, reader, seconds, or error, when the whole clip's board stands) and logged ("board: ... (read on
   a still at 0.3 s, 1920x1080, then on a 848x1024 crop of its box)"). Then the board is measured on its crop, in code
   and by the reader (round 1, 2026-10-17: the reader could not see trailer 3's symmetry or trailer 2's fourth
   colour). `reference.measure_board` divides the grid (the longest run of rows and columns that are mostly block or
   grey-blue floor, so the buttons under the board fall outside) into the columns x rows read and calls each cell block
   (saturated) or floor. The symmetry is decided on the block mask itself, not the cell grid (the grid's match depended
   on the size read: trailer 3 was 0.95 on 6x7 and 0.69 on 8x8): the mask, scaled to 64x64, against its left-right and
   top-bottom mirrors about the best axis near the middle, intersection over union 0.8 or more is symmetric (trailer 3
   0.85-0.88 in every pass, the other two at most 0.59), colours ignored; the cell grid's match is kept beside it (`left_right`,
   `top_bottom`); the reader is no longer asked (its three votes said "not symmetric" every time). The block cells' median colours are clustered by hue (24 degrees) and lightness (0.3), so dark
   green and green, purple and magenta, blue and light blue stay apart; clusters of three cells or more count. The
   reader is asked once for the number of distinct block colours and their names; the code's count is the board's
   own colour names its clusters confirm (one cluster each, `confirmed_names`), and the count is the larger of that
   and the reader's, at most 7, so a colour the code confirms is never merged away and a colour no reader named is
   never added (round 1, third run: a cluster from the booster buttons under a cut board had become "blue"), and a colour the code found and the reader did not is named from
   its cluster (`colours_added`). When the board read gives more names than the count, a name the count does not have
   and that is close to one it has (cyan to blue, magenta to purple) is that colour; a name far from all of them is a
   colour the count missed and stays. The size is read three more times on the crop and the median per side is kept
   (`size_reads`; trailer 3 had read 10x10 for about 8x8), and the code's grid gives the share of cells under blocks
   (`occupancy`). Every ask of the board step is a still's short ask (`describe_still`: 4000 tokens with no doubling,
   150 s, one try per model, a model that answered nothing on a still not asked again in that read; round 3: super-vl
   had reasoned 16000 tokens on a 1920 px still and the board step took 1379-2413 s): the frame's ask always runs, the
   crop's ask, the colour count and the size re-asks only within `BOARD_READ_BUDGET_S` (300 s) of wall clock, else
   "skipped: budget" in `board_read.skipped` and the log line (the code's measure on the crop still runs). The board also gives its inner
   wall cells (`wall_cells`): a board read as open or holes becomes the closest board the generator builds, open or
   its holes board with the fewest walls (3, on an odd width under 8 rows), within a cell a side of the size read
   (`videoref.wall_choice`; round 1: ONE 2-cell wall had become five wall cells in a V), said on the card.
   The tool's own grey wall cells, which the still read sometimes lists as obstacles ("4 dark grey fixed obstacles"),
   are the game's walls: a grey, dark, fixed or barrier cell that is no other game's thing makes an "open" board a
   holes board and is never "not used" (`videoref.board_of`, `WALL_LIKE`); another game's bubbles stay obstacles.
   **Measured** on the 12 own creatives (`../req4-e2e-2026-10-16/READING-ACCURACY-v9.md` and `-v9b.md`, the second a
   fresh pass after the last rule; truth from each creative's `level.json` and brief): the shape 12 and 10 of 12
   (before the shape sentences were sharpened every hourglass read as a door: 4 of 12, `-v9-first.md`), the size
   within a cell 10 and 12, the blocks within two 11 and 12, the colours (at least half each way) 12 and 12; the
   sides with gates 7 of 12 and how busy it looks against the level's difficulty 1-2 of 12 (not judged; busy is not
   applied). On the
   portrait own creatives the whole clip already reads the board about as well; the still is what fixes another game's
   landscape board: the owner's 15 s ad went from 5x5, 7 blocks, 5 colours, no obstacles (whole clip) to 6x6, 13
   blocks, 6 colours, bubbles (the still; about 12 blocks and four bubbles on the first frame). The still read takes
   1-72 s (median 1.5 s on one pass and 31.5 s on the next, 13 readings in parallel on the free tier, the long ones
   waiting out HTTP 429).
   **The owner's three references** (`../req4-e2e-2026-10-16/READING-ACCURACY-refs-v1.md`; two Color Block Jam
   trailers and another game's ad, each read with "create a similar game in Color Block Jam", against a truth written
   by hand from frames): the ending, the structure, the captions, the HUD's level and clock, the board's shape, size,
   blocks, colours and gates, and what the game does not have are right on all three (the structure and the captions
   are judged on the two trailers only); which game it is, 2 of 3 (the HUD-less close-up of the game was read as "a
   brick puzzle game"). The trailer that failed before (one gameplay part) now reads: Color Block Jam, Level 25, 01:05
   on the clock, a 4x7 board with one inner wall, 10 blocks in teal, magenta, purple and green (to blue, red, purple,
   green), gates on two sides, the booster buttons not used, stopping mid-level. The colours are the weakest part: the
   reader lists more names than there are colours (twelve for seven on the close-up, "cyan" beside "blue" on the other
   game), so a surplus name can take an odd free colour ("cyan -> dark green").
4. *Checks in code, per section* (`reference.validate_notes`): only the parts' time is checked: a part outside the
   clip, a part that ends before it starts, parts out of order, no usable parts, or the wrong-unit signature (the long
   last part is an end card, a result or "other", over 60% of the clip, with under 30% before it; a single gameplay part
   over the whole clip, or a long last gameplay part, is valid). Rejected parts are asked once more with the problems
   quoted; a second rejection drops the parts alone (`notes.structure` empty, the model's kept as
   `notes.structure_rejected`, `parts_dropped: "the parts were not usable: ..."` in the analysis, on the card and in
   the assumptions, the part rows info) and the rest of the reading (the concept, the board, the ending, the hook, the
   captions, the HUD, the mechanics) is kept and applied. (2026-10-17, the owner's trailer: one true gameplay part
   0-28.86 s was rejected twice by the old rule and the whole reading was lost; an answer that is not JSON still drops
   the reading, with `error`.) A part's label never rejects it: `reference.purpose_of` reads every label as one of the
   purposes ("identity", "product info", "ad_end_card" as the end card; "result", "reveal" as the victory; "tension",
   "close call" as the near-fail; "failure", "game over" as the fail; anything with "mistake" or "wrong" as a mistake;
   an unknown label as "other"; "replay", "again", "slow-mo" as the replay; "cascade", "satisfying" as the payoff;
   "question", "cliffhanger" as the question) and keeps the model's own beside it (`purpose_raw`, shown on the card); a
   confidence outside 0-1 is clamped. (The live run of 2026-10-16 lost two confident readings to labels before this.)
   A "hook" part longer than max(3 s, 25% of the clip) is play after its first 1.5 s (`reference.long_hooks`, marked
   `split`; round 3, case 18: another game's 15 s ad read "0-12 s hook; 12-14.9 s end card", and the ad took a 12 s
   hook, a 13 s play and a 41 s end card).
   The model's confidence decides nothing (it was 0.9-1.0 on every reading of the tool's own creatives, the wrong ones
   too); it is shown on the card and in the confidence row.
5. *The parts, only when needed* (`reference.separate_parts`): for a hook, pacing or structure read, or a concept read
   that asks about the pacing, the cuts and the motion per second are measured on the copy (`reference.video_facts`),
   each model boundary snaps to the nearest cut within 1.5 s (on the 12 own creatives: the moved boundaries' mean error
   fell from 0.54 s to 0.07 s) and the pace change is measured over the gameplay parts only (the whole clip's last third
   is replay, confetti and end card; its value is kept as `facts.pace_change_clip`). The model's own seconds
   (`notes.structure_model`), the cuts (`facts.cuts_s`) and the measured pace change (`facts.pace_change`) are kept
   beside the refined parts. A concept read with no pacing question is not measured.
6. *The pacing, approximately* (`reference.pacing_from`; a sampled read cannot count moves, as two accuracy rounds
   showed): the tempo word from the moves counted over the gameplay parts' length (calm under 0.25 a second, fast over
   0.6) only when the total is plausible (at least one, at most about one a second), else the model's own word; the
   pace change from the motion measured over the gameplay parts, else the model's word; never from the counts. The
   model's words are kept (`notes.pacing_said`, `notes.pace_change_said`); the result is `analysis.pacing` and
   `notes.pacing`, and the brief's assumptions say the pacing was read approximately.
The plan, the final prompt, the focus, the level, the seconds analysed, the validation result and what the separation
did are stored with the analysis (`brief.planner.references[i]`) and written to the progress log.

**From the reading to the brief** (`src/cbj/videoref.py`, run by `planner.plan` right after `imageref.apply`). Only what
the focus allows is written, and only where the request does not state it itself (its words and the plan's
constraints: a 45 s request stays 45 s, "no replay" stays, a quoted hook stays):

| Focus | What it sets |
|---|---|
| concept | everything below except the look (a "version of this concept" keeps the game's own look) |
| hook | `concept.hook` from the hook's function (a question, a challenge, a dare) in the tool's own words, never its text unless the request says "same text" |
| pacing | `pacing.tempo` (from plausible counts, else the model's word), `pacing.curve` (the gameplay's measured motion, else the model's word), `level.moves` raised for a long play; with "read approximately" in the assumptions |
| captions | the concept texts by function (challenge, instruction, urgency, result, call to action), in the tool's own words |
| ending | `gameplay.ending` (`videoref.mapped_ending`: the last seconds' read first, checked against its own clock and screens; a question, as a part or as the last seconds' caption, is a cliffhanger unless a win or out-of-time screen was transcribed; a victory with a near-fail part is a near-fail; a fail is a time-out), a hard level for a near-fail, `gameplay.mistakes` (an ending read targeted: the larger of the wrong moves listed and the mistake parts, at most 3, the model's yes/no when both are empty; a concept read or a filled ending: the mistake parts only, at most 1, never the free list, round 3 case 16), a streak finish for a payoff part |
| look | `imageref.style_kit` fed with the dominant colours: the background and contrast-checked captions; the blocks are never repainted from a video |
| structure | the length (brought into 30-60 s, then from the play: `videoref.fit_length` below), `sequence.replay` only when the reference has a replay part or repeats a moment, `sequence.hold_s` from a result part, `sequence.end_card`; a reference that is play from start to end (90% or more play, no end card: round 1's trailers) keeps the ad play: `sequence.intro_s` 0 (the hook caption over the play), `sequence.hold_s` 0 (the question or result held as briefly as the engine allows), `pacing.tempo` calm (studio then records the longest play that fits) and the long play's `level.moves`; the end card keeps what is left; the same for a reference shorter than 90% of the ad (LolTap, 15 s into 30 s): its hook and end card keep their own seconds and the play takes the extra time |
| board_colours | `level.colours` only: the blocks' colours read, mapped to the game's own (round 2, case 10: "take only the block colours" had been read as the look, its palette put into the background); nothing else of the board |
| screen (also covered by look) | `visuals.camera_zoom` from the board's share of the frame (none at 55% or less, the most `brief.ZOOM_RANGE` allows, 1.12, at 75% or more), `visuals.hud_level` and `visuals.hud_timer` shown or hidden as the reference shows them, `visuals.cursor` the hand or none as seen; with the clock hidden, a near-fail's or a time-out's seconds go into the hurry caption ("2 seconds left!") and an assumption says so (round 2, case 09: trailer 3's close-up with no HUD) |
| board, HUD | when the reference is Color Block Jam itself (it says so, or its HUD reads "LEVEL n" with the game's clock and no other game is named: a proper name such as "Wood Color Jam" blocks it, a description such as "another puzzle game" does not, `videoref.named_game`): `level.label` from the HUD's level number and `gameplay.timer_s` from the clock at the first frame of play, each only when the request does not state its own: the clock for a win and a cliffhanger (which stops mid-level), for a near-fail or a time-out only when about the ad's length less 8 s of play can bring it down to the ending's seconds (else an assumption says why); a request that asks for "the same starting time as this video" has it set whatever the ending, the row saying when the ending makes it impossible. brief.validate (not changed) keeps a starting clock for a win only and drops it for the other endings with its own note, so a cliffhanger's 01:05 does not reach the recording (round 2, case 05: result.json `timer_start` 27-28 s) |
| board | the level's type, part by part, where the request states nothing about it (`videoref.stated`: board shape words, a size, a block count, colours for the blocks, piece words, difficulty words; "the game's own level" or "level 3" takes nothing): `level.source` generate, `level.shape`, `level.width`/`height` clamped to what the generator builds for that shape (4-9 by 4-10; a narrow centre at least 6 rows, lanes 7x6, a ring 6x6, a cross 5x5, a door 5x4), `level.blocks` (2-10, and no more than the board's free cells hold at the generator's packed fill; when the blocks read do not fit the size read, the board first grows a cell a side within what the generator builds for the shape, then the blocks are cut, and the card says which: "the board read 4x7 holds 6; 5x8 is used so 9 fit"), `level.style` "symmetric" when the layout is mirror-symmetric and the request says nothing about the level's look, `level.colours` (each distinct reference colour to its own game colour, at the least total distance: a colour takes its nearest free one, so purple and magenta give purple and red, and the mapping is on the card and in the assumptions, "magenta -> red: the game has no magenta, purple is taken by purple"; more than seven names: the closest two are one colour, never two of the game's own), `level.pieces`. When the block count is capped (more than 10 read), the board shrinks within the shape's sizes so the made board keeps the reference's blocks per cell ("the reference has 16 blocks on 8x8 (0.25 a cell); the brief takes 10 at most, so the board is 7x6"), and a full reference (60% or more of its cells under blocks, as the code measures it on the crop; never from the "busy" word, which scored 2 of 12) takes the generator's packed look when the request says nothing about the look. A cliffhanger reference that stops with 3 or more blocks still on the board (`ending_read.blocks_left`) cuts with 3 blocks left, the most the game's cliffhanger allows (`gameplay.blocks_left`). How busy it looks is recorded and shown, never applied (against the level's difficulty it read 1-2 of 12): the difficulty stays the request's, the ending rule's (hard for a near-fail) or the generator's default. The level is then generated and solved by the generator's own rules; the plan row says "a new board of this type is generated and solved, its cells are not copied", and "its exact layout" goes to not copied |

A mechanic the game does not have (another game's bubbles, ice, keys, locks, boosters, bombs, any other obstacle) is
never created, drawn, simulated or used (the owner's rule, 2026-10-17): it adds no block, no wall and no shape, the
level is built only from the shape, size, block count, colours and pieces, and each one is one line "<it>: not used:
not in Color Block Jam" in the assumptions and on the card, and goes to not copied. The board's obstacles are listed
the same way (a mechanics entry about the same thing gives way to them). A row of `videoref.MECHANICS` only names the
game's own parameter that the moment shares, when the brief has it ("a hammer booster: not used: not in Color Block
Jam; the ad keeps the game's own near-fail"; a merge, the game's own fast finish). The game's own things under other
names stay native: drags, gates, the clock, the result screens, the HUD, wall cells (the board's shape), the grid, the
hand cursor; a level map or chapters are "not used: an ad shows one level". Booster buttons and anything else on
screen the build does not have (`extras_seen`, from the whole clip and from the full-resolution still) are "not used:
not in Color Block Jam" too, once per thing. What the planner's model took from a video's colours
on its own, when the look was not the focus and the request names no colours, is put back to the game's own look.
`brief.reference` is the provenance, written by code: `file`, `focus`, `level`, `analysed_s`, `adapted` (in words: "the
challenge hook", "a near-fail ending", "the pacing (normal, speeds up)", "the board (an open 6x6 board with 10 blocks in
6 colours)"...), `not_copied` (always the reference's gameplay, its characters and assets, its exact frames, and its
caption text unless asked; its exact layout when the board was taken; each mechanic not used), `mechanics` (the game's
own under another name), `not_used` and `board` (the board as read, in words, what was taken and what the request kept).

**Captions fit the ending.** After planning (and after each revision's planning), `videoref.fit_captions` clears a
cliffhanger's result line (its question is the result moment) and replaces any concept text that claims a clear, a win
or a beaten clock on a cliffhanger ("cleared", "solved", "done", "you did it", "beat the clock", "level complete") with
"Can you finish it?", and a time-out's win claims with its own lines; each change is an assumption (round 2: LolTap's
unfinished board showed "Board cleared!", trailer 2's "Can you beat the clock?"). A caption promising a chain of exits
("Everything flies!", "one after another") needs the streak finish, else the tool's own words; a quoted caption stays
(round 3, case 19).

**Round 3 (2026-10-17): the length, the ending and the result as the request words them** (the video workflow only:
`audit.asked(..., case_range=True)`, `videoref.stated(..., video=True)`, `fit_captions(..., chain=True)`,
`guided.video_ref`; the text and image workflows keep their behaviour, and create's `keep_asked` still reads "30-60
second" as 60 s). A range inside the case's 30-60 s ("a new 30–60 second ad", "30-60s", "30 to 60 seconds") is no
stated length (`audit.asked` records it as `length_range`, an info row in the guided evaluation; three ads had been made 60 s long with 10-41 s end cards); a single number ("a 45 second
ad") is, and is the brief's before the play is planned. With no single length, the length comes from the play
(`videoref.fit_length`): the reference's own length in the range (or the plan's) is the most, and when the play levers
cannot fill it, the length drops (to 30 s at the least) by what the play misses instead of the end card growing ("the ad
is 47 s, not 60 s: ..." in the play line, `prov["play"]["length"]`). The request's solve words ("the final solution",
"the solve", "a satisfying clear", "clears the whole board", "finishes the level") make the ending a win, also over the
reference's cliffhanger (`videoref.SOLVE_PHRASES`, `plain_solve`), and "a moment to breathe", "linger", "let it land",
"hold the solved board" hold the result 1.5 s longer with no replay (`videoref.breathe`). A speeds-up curve fills the
play with more moves at a normal tempo, calm only when nothing else fills. A revision keeps the reference's mistake
count (`guided.PINNED`).

**The owner's trailer-2 creative (2026-10-17): the HUD, "fewer moves", the asked end line** (the video workflow only,
behind the same switches). The prompt "I like this video's pace. Keep it, zoom in closer on the board, and use fewer
moves so each one matters. End unsolved with a 'your turn' line." gave a 4x9 board at zoom 1.1 under the HUD, 10 moves
and the stock "Can you see the move?". Now:
- **The board's top row is never under the HUD** (`videoref.hud_clear`, at the end of `_apply_one` and in every guided
  revision). The HUD bar is a fixed canvas; FitCamera frames the board and the zoom scales about y 1020 of the
  1080x1920 frame, so the board's top at zoom 1 depends on its rows beyond its columns. Measured with
  `tests/data/hud_margin.py` (`audit.hud_measure` on the first frame of play of 58 own recordings; the HUD's bottom
  edge at y 636): rows - cols -1: y 736-750; 0: 708-721; 1: 673-680; 2: 627-636; 3 and more: under the HUD at zoom 1
  already (4x7 567, 5x8 581, 4x8 523, 6x10 553, 4x9 and 4x10 hidden under the bar); the owner's 4x9 at 1.1: y 451.
  `SAFE_ZOOM_BY_EXTRA_ROWS` {-1: 1.12, 0: 1.12, 1: 1.1, 2: 1.0}, `SAFE_ZOOM_BY_ROWS` (the columns unknown: the
  narrowest board, 4 columns) {4: 1.12, 5: 1.1, 6+: 1.0}. A zoom the request states ("zoom in", "closer",
  "close-up", "fill the screen") with a HUD it does not ask for (`hud_asked`: the HUD, the clock, the timer, the level
  badge, the seconds on the clock) hides the HUD: "the HUD is hidden: the closer zoom would put it over the board's top
  row; the request asked for the zoom, the HUD came from the reference". An asked HUD caps the zoom at the safe zoom;
  neither asked caps the zoom, and a board the HUD covers at zoom 1 hides an unasked HUD. A size generated later (no
  width or height in the brief) takes the cap 1 when the zoom is stated. `brief.reference.hud_clear` records it.
- **The measured guard** (`audit.hud_row`, in the reference rows): on the version's first frame of play
  (`hud_frame.png`, 0.5 s into the play part), "Asked: the zoom" when the request states the zoom, else "Reference: the
  screen: the HUD over the board". It fails when the bar covers the board's top and the brief has a lever (an unasked
  HUD, or a zoom above 1); a revision then hides the HUD or lowers the zoom (`guided.hud_fix`). An asked HUD at zoom 1
  is info: the game's framing does it (CreativeRunner.FitCamera, not a brief field).
- **"Fewer moves" is the request's own** (`videoref.RELATIVE_MOVES`, `RELATIVE_BLOCKS` in `stated(..., video=True)`:
  "fewer/more/a few moves", "fewer blocks"): the play levers keep the planner's count, never raise it, accept the
  shorter play and say the cause first in the play line and `prov["play"]["cap"]` ("the request asks for fewer moves: 6
  kept; the play fills 15 of 21 s"); the hesitations may still fill within `MAX_HESITATIONS`. With no number from the planner
  (round 4, case 28: the fill played 10), `videoref.relative_count` derives it from the reading: "fewer" about 70% of the
  reference's counted moves (at least 4), "a few" 4-5, "more" about 130% (at most 14), the tempo class (7/9/11,
  estimated) with no count; a cliffhanger's board holds the moves minus its cut's blocks.
- **The asked end line is the cliffhanger's question** (`videoref.end_line` in `fit_captions(..., chain=True)`): a
  quoted line in a sentence about the end ("End unsolved with a 'your turn' line", "ends with 'X'", "stop ... and ask
  'X'") or an unquoted "a your-turn line" (the tool's words "Your turn!") becomes `concept.result`, the question ad.py
  draws on a cliffhanger, or `concept.end_title` when the sentence names the end card; it is never dropped.
- **Round 4 (2026-10-17): the play for every guided creative, a win the request implies.** The play decision
  (`play_levers`, mode "fill") now runs for every guided creative, not only with a pacing or structure focus (case 29:
  a 40 s win from a screen/look/colours read played 20.6 s, and studio filled the rest with an 11 s slow replay); a
  replay neither the request nor the reference has stays off while the play fills; a size the request states caps it and
  the play line says so. Words implying a win ("the winning move", "after the win", "once it's solved", "the level
  completed screen") and an asked replay are the request's ending: a cliffhanger becomes a win (`replay_ending`), a
  planner assumption that cites the request keeps its ending over the reference's (`planner_ending`), a quoted line
  "... card" goes to the end card for any ending, and a revision can fix an asked-replay miss (`guided.replay_fix`; case
  30: "end with a replay of the winning move and a 'Can you do it faster?' card" had ended on the reference's cut). Rerun:
  with the pace taken and the request's own moves, the reference's tempo class and no added hesitation (a calm stretch
  made case 28's gaps uneven); the end card never shows the asked line twice (its fact line becomes the ending's own).
- **The version record keeps its review.** `studio.make` writes version.json before the review; `guided.save_record`
  now writes it again after the review (or its error) and with the loop's verdict (a revised version keeps its "made"
  record and gets the later verdict as `loop`). The owner's v1 had review.json beside it (claude-cli/opus, 45.9 s,
  written in the same make job) but no `review` in version.json.

**Revisions keep the reference.** A guided revision (`workflows/guided.revise_once`) pins the fields the reference set
(videoref records them in `brief.reference.set`: the board's shape, size, blocks, colours, pieces and look, the ending,
the HUD label) unless the miss fed back is that field's own reference row or an asked fact about it, and says so in the
log ("revision: the reference's board is kept (level.shape, level.style)"). Round 1: the viewer's "keep the board full
longer" had re-planned trailer 2's open board as a walled, packed one. The values restored are the base version's brief as videoref adapted them, never re-derived from the reading, and a
miss of "Reference: the board" does not unpin the board (that row now measures the adapted board, so its miss is the
generator's, fixed by a new take; round 2, case 04 had re-planned the raw "holes 4x7"). The reference's length is kept
whatever the miss
(a part-length miss is fixed with the timing fields; round 1's third run had gone 30 s to 45 s). When the play is too
short (the case's "gameplay at the centre" fails, or the ad has under 60% of the reference's play: an all-play
reference's ad sits near 80% by the engine's cap, and raising its board there only changed the board, round 2 case 05),
the reference's board yields: the revision raises its blocks by 3 (at most 10) and the size by up to a cell a side to hold them, and says
"the reference's board was too small to fill the play".

**On the page.** After planning, the Create side shows a "Reference to creative" card: the file, the reading plan (the
focus, the level, the questions, what was ignored, the why), the parts as a short timeline with their seconds (and the
model's own seconds when they were snapped, and the model's own label beside a relabelled purpose), the confidence (a
one-line warning when low; it decides nothing), what was adapted and what
was not copied, the board read and what was taken from it (with the colour mapping), the HUD's level and clock taken
from a Color Block Jam reference, the mechanics translated and the list "Not used: not in Color Block Jam", and "the
parts were not usable" when they were dropped; the prompt the model saw is under "What the model was asked".

**Evaluation: the reference rows** (`audit.reference_rows`, group "reference", from "reference"; fed to the loop like the
others). Measured from the finished ad's `parts.json` against the stored reading. A row whose aspect the focus does not
cover is info; `where` is `plan` when the brief did not carry the reference's value, `play` or `ad` when it did and the
result does not show it.

| Row | Pass when |
|---|---|
| Reference: the ending | the reference's ending, mapped as above, is the ending played (info when the request sets the ending) |
| Reference: the pacing | judged only when the request asks about the pacing (a targeted reading plan that names it, as "take only how fast the moves come"; for a full concept read or with no plan, the request's words; else info: a sampled read gets it approximately): the ad's drags per second over the play are in the reference's class (calm under 0.25, fast over 0.6) and the first-third against last-third change matches |
| Reference: the hook | the ad's hook caption starts within the reference's hook length + 1 s (3 s when it has none) |
| Reference: the purposes in order | (info when the parts were dropped) every purpose the tool can stage (hook, gameplay, mistake, near-fail or fail, victory, replay, question, end card) appears in the ad's moments and parts in the same order |
| Reference: the part lengths | a reference shorter than 90% of the ad: the hook (at most 4 s), the result and the end card in seconds (the end card 3-4 s) and the play as the rest, each part's error in seconds over the ad's length; otherwise the mean absolute error between the reference's and the ad's part shares (hook, play with the replay, result with the question, end card) is at most 0.2; with no end card in the reference the ad's end card up to the engine's shortest (3 s, its call to action) is not counted, and with no hook part the hook caption over the play counts as play (both said in the detail) |
| Reference: the captions | the ad has a caption for each function the reference's captions (`captions_seen`) have (captions or concept focus) |
| Reference: the look | the poster's margins and the caption fill are in the families of the reference's dominant colours (look focus) |
| Reference: the board | the made level (`level.json` in the version folder; its shape read from its wall cells, `audit.made_shape`) against the board as the brief took it (videoref's adapted shape, size, blocks and colours: after the wall choice, the growth, the fill and the colour mapping; the raw reading shown beside it, round 2 case 04), each part clamped as the brief was: the shape equal, the size within a cell a side, the blocks within two, at least half of the reference's colours in the level; parts the request states are its own. Only the parts the accuracy pass reads reliably (10 of 12 or better, `audit.BOARD_RELIABLE`) can fail the row; the rest are info, "read approximately" (concept or board focus) |
| Reference: nothing copied | the provenance lists what was not copied and no layer of the ad uses the reference file |
| Reference: the screen | the HUD shown or hidden as the reference shows it (can fail, at the plan; a HUD `videoref.hud_clear` hid for the board's top row is info); the zoom from the board's share is info (screen or look focus) |
| Reference: the screen: the HUD over the board (or Asked: the zoom) | measured on the first frame of play (`audit.hud_measure`): the HUD bar over the board's top row fails when the brief has a lever (an unasked HUD, a zoom above 1), feeding `guided.hud_fix`; an asked HUD at zoom 1 is info |
| Asked: the captions fit the ending | (in the reference group, so the create workflow is unchanged) no caption the ad shows claims what the ending played does not: no clear, win or beaten clock on a cliffhanger, no win on a time-out, no fail on a win or a near-fail; fails at the plan, so the loop feeds it back |
| Reference: read with confidence | info: the level, the focus, the seconds analysed, the confidence |

**Limitations of the reading.**
- The Gemini key is a free-tier AI Studio key. Google's terms say free-tier content may be used to improve Google's
  products, except for accounts in the UK and the EEA: a reference video sent this way is sent under those terms. A
  paid key, or `NVIDIA_API_KEY` alone (no `GEMINI_API_KEY`), avoids it.
- The free tier has a quota and the hosted models report "high demand" at times: Gemini 3.7 and 3.8 Flash answered
  HTTP 503 all evening on 2026-10-16 and 3.6 Flash hit the free quota (429), so the default order is Flash-Lite alone,
  then NVIDIA build.
- The pacing and the part timings are read approximately by either reader (see the table): they are judged only
  when the request asks for them, with tolerance, and labelled approximate.

**Where this differs from the spec, and why.** `sequence.intro_s` is not set from the hook's length: in this engine it
is a frozen first frame, capped at 0.5 s since viewers left on a 3 s frozen opening (2026-10-14), so the hook's length is
matched by the hook caption over moving play (the hook row and the part-length row measure it). A concept read leaves
the look alone, as the spec's worked example does. A "long gameplay segment" (more moves) is one gameplay part of at
least half the clip, which keeps the worked example on the engine's block count. Bombs are mapped with the boosters,
as in the worked example. Part
lengths are compared as shares of each video's length, so a 38 s reference and a 30 s ad can match. A part may end up
to 0.5 s past the clip (the model's rounding) before it is rejected. A purpose outside the list and a confidence
outside 0-1 do not reject a reading (the label is mapped, the confidence clamped): on the live run they threw good
readings away.

Tests: `tests/test_videoref.py` (the reading plan and its fallback, the word table, the format step on a 70 s clip, a
rotated MOV and a WebM, the checks, the part separation on a clip with hard cuts, each focus and the worked example
through `videoref.apply`, the mechanics table, the provenance, the own-creative words, each reference row passing and
failing, the guided plan end to end with a fake planner and a fake multimodal model) and the dispatch tests in
`tests/test_app.py`.

## Length (case p.2: 30-60 s)

Ads are 30-60 s; a shorter request is raised to 30 with a reason. When a level plays too few
drags for the length, the showcase or the game's own level is swapped for a generated one of
the same difficulty, sized to the length (unless the prompt named a level number). When the
recording is still short (drags x 1.6 s + 3 s + 3.5 s a mistake under the length minus 15 s), the play is paced deliberately first (grade "slow" when it would still fall short by more than a drag: a long look before every other drag and a thought before the rest, plus the hesitations the ending allows on a new creative; the play filled about 60 % of the 48 audited ads, 2026-10-15) (a long look of 1.6-2.2 s before each
drag (1.8-2.8 s and a gliding finger at a calm tempo), the slowest finger, the closing cascade or a streak's run of exits kept, the stuck moment after a mistake at its longest; `play.deliberate`; real time, so the clock stays
true), and only then is the ad filled, replay first (never before a cliffhanger's question) and held screens last: the replay may show the whole
solve at half speed (up to 16 s), then the result is held up to 2.5 s (a 5 s finish with the game's own
screen), and only past an 8 s end card up to 4 s, 12 s for a very short play; the end card is filler
beyond 6 s and the brief says what filled it. An asked block count that caps the play is said in the plan. The opening is never frozen for more than 0.5 s: the game
must be moving within the first second (viewers decide then). The primary play is never slowed in
post: the HUD clock is on screen and must tick in real time.

Fixes from the case-requirement test of 2026-10-13 (see ../CASE-TEST-REPORT-2026-10-13.md):
an edit keeps the game's own level file by name (the HUD number stays); an edit that plans the
same moves reuses the parent's recording; rendering noise on a re-filmed recording with the same
game state is not a change; hesitations are clamped per ending; "speeding up" and prompts in
other languages keep what the planner read; a change the merge drops is shown as adjusted;
hiding the clock also hides the HUD bar's panel ("MainBar:image"); an edit that changes nothing
is refused instead of making a duplicate version; the page shows when another job runs and
resumes its own job after a reload.

Fixes from the 36 natural-language cases of 2026-10-13 (see ../USER-CASES-REPORT-2026-10-13.md):
"first-time player" and "exit doors" no longer count as an order of moves (a leaving order needs
a sequencing word); a board size, block count, length or clock figure the planner wrote but the
prompt never gave is taken out of the words too, not only out of the brief; field names and enum
tokens a model lets slip into the plan are rewritten in plain words; "square", "spacious",
"plenty of empty space" are board sizes; "out of the way", "rearrange", "make room", "obvious",
"first-time" are difficulty cues; "clustered", "tightly", "few empty" are a packed board;
"L-shaped blocks" is about the pieces, not the board's shape; a new pieces value "varied" puts a
small, a long and a corner piece on the board together (checked); a board for a play with a
mistake is chosen among boards that offer a believable wrong move; where a gate sits (opposite
sides, the top edge) is told to be out of the tool's control instead of claimed; a change the
request never asked about (the planner's own taste, such as a pastel theme for "relaxing") is
shown as adjusted, with a note on how to undo it; "a few colours" is not a block count.

Fixes from the level & gameplay scenarios of 2026-10-13 (see ../LG-SCENARIOS-REPORT-2026-10-13.md):
a leaving order needs a sequencing word on the text with lengths removed ("15-second" is not the
ordinal "second"; "start with a board" is not an order); "all the red blocks leave first" is solvable
(the first drag starts the event); an order no board could play is cleared from the play with a note;
a named longest/biggest block is the one of its kind on the board and a colour an order points at is
one block ("Named block" check); "this exact sequence" makes a level of exactly the named blocks; a
time-out is generated on a board hard enough for a believable fail; "designed to end in failure" is
told that the clock is the only failure; gameplay.blocks_left (1-3) sets a cliffhanger's cut and is
part of the recording's identity; a calm asked clock is honoured on a win, otherwise the reason is
written; "without text narration" removes the captions over the play (the hook stays as the poster
text); a placed caption that wraps is moved up inside the safe area; {fact} placeholders are never
rewritten; Spec.resolved() carries every request field (the generator rules were not reaching the
search before).

### Video-guided: the video's own board, and the door and colour rules (2026-10-19, afternoon)

The owner's creative of 10:37 ("use same game design, same scenario just use fewer blocks" on the game's own trailer) got a
board of the trailer's TYPE, because the video workflow took only the shape, the size, the block count and the colours
and the generator built a new board. Now, when the words ask for THE board ("the same game design", "this board", "exactly
as shown"; `videocells.copy_asked`), the first frame of play is taken as a still (`studio/_cells/<video>_t<s>.png`) and read
cell by cell with the image path (`imageread.read` + `imagecells`), verified on the pixels, solved and played as read; the
asked changes apply in code (`imageplan.copy_spec`): fewer or more blocks, half the blocks, easier (new today:
`imagecells.remove_blocks`, `add_blocks`), one more or fewer colour, a recolour, a mirror, harder. "A level like this",
"the same kind of level" and "a new board of this type" keep the type path. The control row says which, in one line, and
a revision never changes a copied board. A Turkish request is translated once for the parsers (as the image path does). When the video is Color Block Jam itself, the copied board is shown in the colours the footage shows (the live game's palette differs from the build's: teal, magenta, violet, lime in trailer 2), each slot's block and door repainted together and the mapping said; a request naming block colours keeps its own, and a revision never repaints from a viewer's remark. A cliffhanger keeps an asked starting clock (the trailer's 01:05 with "keep its clock"; brief.check and play.fit_clock, 2026-10-19): the cut comes wherever the clock stands; a near-fail and a time-out still land on their planned second. The cell reading cross-checks the colour count against the whole-frame read and splits one name over two hue clusters (V3: the yellow plus and the orange cubes were both "orange"); a copied board's play is estimated against the stated length at plan time, the fastest fitting tempo is set, and when none fits the plan says the length the ad will need and the loop does not try to shorten what cannot be shortened (videoref.copied_board_pace). Another game's bubbles, covers and counters are not blocks to the reader (their cells are floor, said). Two rows of the image path now run on every workflow: "blocks left at the cut" (a time-out's one-block limit is said in the plan and the row, never silent) and "the end card is a card, not padding" (at most 8 s).

The evaluation gained the game's design rules on EVERY workflow (`audit.door_rows`, `audit.colour_rows`): "Rules: the
level" no longer claims a door rule it never checked; "Rules: doors and colours" fails a block colour with no door, a
door with no block, or a block that fits through no door of its colour (`level.door_problems`, kept by all six shipped
levels); "Rules: colours tell apart" fails two used colours shown closer than the game's red and orange, or two slots
with one caption name (two blues through one door); "Rules: doors used" is info. The slot mapping of a read colour now
weighs the hue too (trailer 2's violet went to dark green by RGB alone; by hue the magenta becomes red and the violet
stays purple), and a violet at 245-262 degrees counts as blue or purple to the pixel check. Test set:
`~/rollic-case/req4-video-refs-2026-10-19/` (PROMPTS.md, REFERENCE-VIDEOS-ANALYSIS.md, RESULTS.md).

### Image-guided: the board IS the picture's (2026-10-19)
A Color Block Jam board in the reference picture is now read **cell by cell** (`src/cbj/imagecells.py`: the grid's corners,
a perspective warp with a lettered grid, every block, hole, gate and thin wall line in strict JSON, verified against the
picture's pixels, built into the game's level JSON and solved by the tool's solver). With the board role on, the level
is that board (`level.source = "picture"`, `level.file` under `studio/levels/picture_*.json`), with the request's own
changes applied in code and said: one more or fewer colour (a block recoloured with a gate of its own), a named recolour
(blocks and gates), a mirror. A board the picture draws unplayable (the pictures are renders) gets the smallest gate
repair, said in the plan; a thin wall between rooms becomes a line of wall cells; "a new board of this type" keeps the
old type-generation path. Evidence: `studio/_cells/<picture>.json` + the grid overlay PNG.

The evaluation now measures what it could not before (`~/rollic-case/IMAGE-GUIDED-EVAL-CHECKS-2026-10-19.md`):
`Image: the board is the picture's` (the made level against the read board, cell for cell), `more or fewer colours than
the picture`, `a colour became another`, `the board mirrored`, `looks like the picture (viewer)` (the viewer model on a
side-by-side), and `Coverage: ...` (every parsed ask has a row, or a `not measured` row names the gap). The loop drops a
viewer's complaint only when every ask is measured and passing (E2); a viewer "partial" on an asked control with a gap
counts as "fix" (E3).

Routing (2026-10-19): a screenshot-sized picture attached with words that do not place it ("put our logo on the end
card" still goes to the text workflow) is a reference in any language, so it reaches the image-guided workflow; a request
that is not in English is translated once by the planner model for the code's parsers (the original stays in the brief
as `planner.prompt_original`).
