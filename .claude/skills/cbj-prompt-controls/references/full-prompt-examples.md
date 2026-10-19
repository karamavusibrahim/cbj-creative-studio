# Example prompts: 4-5 controls each, all eight across a set

The case's eight prompt controls: (1) the type or structure of the level, (2) gameplay behaviour, (3) difficulty or
pacing, (4) visual elements, (5) creative concept, (6) sequence of events, (7) assets to use, (8) elements that should
remain unchanged. Each prompt below states four or five of them; across the five prompts of a set every control
appears at least once (some twice). Whatever a prompt does not mention, the system takes as its default and the plan
row says "default". Lengths are 30 s (the case asks for 30-60 s). The five editing scenarios (CC-10, 18, 26, 33, 42)
are unchanged: an edit prompt names one change and says everything else stays, which is control 8 in full.

## Core requirement 1: text-to-creative

### TC-01 — Easy beginner level   (controls 1, 2, 3, 8)
**Prompt:** Create a beginner-friendly Color Block Jam level on a small open board: only 1x1 and 1x2 blocks in red, green and blue, each with a matching exit door on the board edge, and plenty of empty cells so every block has room to move. The player solves it in one clean pass with no wrong moves. Easy difficulty, a calm pace with a generous clock, a 30-second portrait ad. Do not change the game's rules, HUD or block shapes.

**Expected result:** A small, solvable three-colour level, few blocks, none touching, every block reaching its own door in one pass with no bumps and a comfortable clock; the look, captions, sequence and sound are the tool's defaults and the plan says so; the game moves within the first second.

### TC-14 — Relaxed gameplay   (controls 1, 2, 3, 4, 6)
**Prompt:** Generate a relaxing 30-second Color Block Jam creative for casual players: a medium-sized open board with four blocks in three colours (blue, yellow, purple), short straight routes to their doors and no walls in the way. Every drag is slow and deliberate with a pause between moves, no mistakes, and the clock never gets close to zero. Easy difficulty, calm tempo. The game's own blocks on a light mint background, white captions with a soft outline. No slow-motion replay: the gameplay, the game's result screen, then the end card.

**Expected result:** An easy clean win with visible pauses, a mint background behind the board, no replay part; the hook text, assets and sound are defaults.

### TC-18 — Toy-themed creative   (controls 1, 4, 5, 7, 8)
**Prompt:** Create a playful toy-themed Color Block Jam level, 30 seconds portrait: a 6x8 board with chunky mixed pieces in pastel red, yellow, green and blue, matching doors, one wall tile in the middle. Light blue background behind the board, bright pastel block colours, a rounded cheerful caption style. Concept: "playtime puzzle"; hook caption "Toy box jam!". Use the attached toy pictures as stickers in the two top corners and the attached logo on the end card. Keep the game's doors, block shapes, timer and rules exactly as in the real game.

**Expected result:** Pastel blocks on a light blue background, the attached pictures in the top corners, the logo on the end card, the asked hook; the ending (a near-fail by default), the pace and the sequence are defaults and the plan says so. With nothing attached, the plan says so and makes the ad without the pictures.

### TC-26 — Autumn theme transformation (an edit)   (controls 4, 6, 7, 8)
**Prompt:** I like the current Color Block Jam level, but I want an autumn theme. Change only the look: a warm orange background behind the board, the captions in yellow with a brown outline, the end card in the same warm orange, yellow and brown colours, and the attached leaf picture as a sticker in the top right corner. Keep the same hook, replay, result screen and end card order. Keep all blocks, their positions, colours, matching doors, walls, timer and every drag exactly the same. Use the attached leaf picture and nothing else new.

**Expected result:** The same creative with autumn styling only; the edit report shows Visual structure and Other assets changed as asked and Gameplay, Timing, Camera, Sequence and Sound kept.

### TC-36 — Mistake and recovery creative   (controls 1, 2, 5, 6, 7)
**Prompt:** Create a 30-second portrait Color Block Jam gameplay advertisement. Start from a board that looks almost completed: three blocks left in two colours, one narrow corridor to the doors. The player makes a wrong move that blocks the remaining path and gets stuck; then the puzzle replays from the same starting position and shows the correct order of drags that clears every block. Concept: "one wrong move"; caption "Don't do this..." over the mistake and "Do this" over the correct run. Sequence: hook, the mistake, the correct run, the game's win screen, then the end card with PLAY NOW. Game assets and sound effects only, no music.

**Expected result:** A near-finished board, one legal wrong drag that jams the corridor, the correct sequence from the same start, the two captions in place, the board empty at the win screen; difficulty, pace and look are defaults.

## Core requirement 2: level & gameplay generation

### LG-02 — Intermediate rearrangement puzzle   (controls 1, 2, 3, 6)
**Prompt:** Create a 30-second Color Block Jam gameplay creative on an open 7x7 board with five blocks of mixed shapes in four colours, laid out so that two blocks cannot reach their matching doors at the start because another block lies across their route. The player first moves that obstructing block aside without clearing it, which frees the corridor, then clears the board in the right order with no wrong moves. Medium difficulty, normal tempo. Show a slow-motion replay of the key move and the exits after it, then the game's result screen and the end card.

**Expected result:** A genuine blockage (at least one repositioning drag in the difficulty numbers), one aside move that creates a legal path, a coherent solve, the replay on the key move; look, captions and assets are defaults.

### LG-05 — Symmetrical board with asymmetric solution   (controls 1, 2, 4, 5)
**Prompt:** Generate a visually striking 30-second portrait Color Block Jam creative: a mirror-symmetric narrow-centre (hourglass) board with red blocks on the left half and blue blocks on the right, their matching doors near their own edges, and the shared bottleneck in the middle. All the red blocks leave first, then all the blue ones, so one side is cleared before the other and the symmetry breaks naturally; no wrong moves. The game's own look, blocks in the game's red and blue. Concept: "which side first?"; hook caption "Which side goes first?".

**Expected result:** A mirrored start with readable doors; every red block leaves before any blue one; difficulty, pace, sequence and assets are defaults.

### LG-08 — Exact ordered actions   (controls 1, 2, 7, 8)
**Prompt:** Generate a 30-second Color Block Jam gameplay creative with this exact order of interactions on a level built for it: first move the yellow block aside without clearing it; then the green block exits through its green door; then the red block moves into the space the green block left; then the yellow block exits; finally the red block and any remaining blocks exit. Use an open board of medium size with four or five blocks, one yellow, one green and one red among them. Game assets and sound effects only, no music. Keep the game's rules and HUD unchanged.

**Expected result:** A board designed to support the order, played in that order with persistent state; each ordered step check passes with the drag that did it; difficulty, look, captions and sequence are defaults.

### LG-13 — One-second timer comeback   (controls 2, 3, 4, 5, 6)
**Prompt:** Make a dramatic 30-second portrait Color Block Jam creative: a near-fail where the player makes one wrong move, gets stuck for a moment, then recovers and the last block starts leaving with one second showing on the clock, followed by the win. Hard difficulty; the pace speeds up toward the end as the clock runs down. The game's own look with the clock visible. Concept: "beat the clock"; hook caption "Can you beat the clock?", a hurry caption in the last seconds, result caption "Just in time!". Sequence: hook, gameplay, slow-motion replay of the last moves, the game's Level Completed screen, end card.

**Expected result:** A hard generated level (the tool's choice of board), clock and play coherent, the final clearance starting at 00:01, the asked captions, the win screen; assets are defaults.

### LG-18 — Rapid final clear   (controls 1, 2, 3, 5, 7)
**Prompt:** Build a 30-second Color Block Jam creative whose first half sets up a clever solution on a medium board where one central blocking block holds four other blocks back from their doors. A satisfying solve: a few set-up moves, then the key move frees everything and the four remaining blocks leave through their correct doors one after another in quick succession; no wrong moves. Medium difficulty; the pace speeds up from the set-up to the cascade. Concept: "one move frees them all"; hook caption "One move frees them all", a cascade caption on the quick finish. Game assets and sound effects only.

**Expected result:** Slow set-up then a genuine run of at least four legal exits after one key move; the asked captions; look and sequence are defaults, so the replay and the result screen are shown.
