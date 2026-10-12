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
in the environment or in a `.env` file in this folder (git-ignored): `NVIDIA_API_KEY=...`.

## Commands

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
uv run cbj plan "a hard level with a narrow centre, the player almost fails"   # what a prompt means
uv run cbj make "the same prompt"                             # plan it and make the ad (studio/<id>/v1)
uv run cbj make "keep everything, but the hook says 'Beat this!'" --edit <id>  # an edit: v2, with the proof
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
| `win` (S3) | a clean solve; the closing drags speed up | kept above 0:50 (no red flashing) |
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
s; with reasoning on, up to 3 minutes), and falls back to Nemotron 3 Super.

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
| Type or structure of the level | shape (open, narrow centre, door, pillars, cross, ring, lanes), size, blocks, piece shapes, looks (symmetric, packed, colourful), colours, HUD number | the level generator (`generate.py`), or a shipped level |
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
| A visually interesting board | `level.style`: symmetric (blocks, colours and gates mirrored), packed (55-75 % of the cells hold blocks, one gate per colour, as in the real game), colourful (every colour, touching blocks differ) | a looks score (contrast, gate sides, fill, symmetry) in the generator's ranking |
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

**Exact edits without a prompt.** The UI's *Things in this ad* card replaces, removes or
rewrites one thing (a picture, a caption, the sound) by changing the brief in code: no planner,
the same proofs. **Any version can be edited** (the new version records which one it came from),
and any two versions can be compared (`cbj edit-report <id> A B`, or *Compare* in the UI).

```
uv run cbj make "Same ad without the slow-motion replay." --edit <id>          # edit the latest version
uv run cbj make "Keep everything, but the button says 'SOLVE IT'" --edit <id> --base 2  # edit v2
uv run cbj edit-report <id> 1 3                                               # what v3 changed from v1
```

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
src/cbj/generate.py  the level generator: shape, size, blocks, pieces, looks, colours, difficulty band, events fit
src/cbj/events.py    gameplay events (an order of interactions), their solver and check; the satisfying finish
src/cbj/checks.py    what was asked, checked on the recording and the level file
src/cbj/preview.py   a picture of a level, drawn from its file
src/cbj/studio.py    brief -> level -> recording -> ad, versions, cached stages, edits (pin, closest play)
src/cbj/edits.py     what an edit can point at (the inventory) and exact edits without the planner
src/cbj/editreport.py the edit report: the case's seven preserve items, captions and sound, one by one
src/cbj/app.py       the test UI (FastAPI); the page is src/cbj/static/index.html
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
