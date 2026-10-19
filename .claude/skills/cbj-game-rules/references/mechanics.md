# Mechanics as implemented, with source lines

Extracted 2026-10-14 from `~/rollic-case/CBJ/Assets/` (paths relative to `Assets/`). Inspector values in
`Scenes/GameScene.unity` and `Scripts/MovementSettings.asset` override the defaults written in code.

## Board
- Width and height come only from the level JSON `gridWidth`, `gridHeight` (Scripts/LevelData.cs:7-8, Scripts/GridManager.cs:33-36).
- Cell size 1.28 world units (Scenes/GameScene.unity:2308); cell (x, y) at `origin + (x*1.28, 0, y*1.28)`: x to the right,
  y away from the camera, so y=0 is the bottom row (Scripts/GridManager.cs:88). World to grid uses RoundToInt (GridManager.cs:782-788).
- Two kinds of cell only: active (`Cell` with an occupancy slot, Scripts/Cell.cs:5-20) and inactive (listed in `inactiveCells`;
  no object, `grid[x,y] = null`, GridManager.cs:81-86; `IsCellActive` false, GridManager.cs:213-217). No wall or obstacle type
  exists: holes and the boundary are the only static blockers. Occupancy is logical: every covered cell holds the block
  (Scripts/ItemFactory.cs:34-51, Scripts/Services/Grid/BlockGridService.cs:16-34).
- Borders are drawn on every active edge touching the boundary or a hole unless an exit covers it (GridManager.cs:471-483);
  corners at convex, concave and diagonal vertices (GridManager.cs:553-641). Block visuals are clipped to the active area plus
  0.5 by a mask (GridManager.cs:116-208, Shaders/StandardPBS_Clipped.shader:137-140), which is why a block seems to slide
  into its exit.

## Level JSON (parsed with JsonUtility, Scripts/LevelManager.cs:196-197)
| field | meaning |
|---|---|
| `gridWidth`, `gridHeight` | columns, rows (LevelData.cs:7-8) |
| `timerCount` | seconds (LevelData.cs:9, GameManager.cs:310) |
| `inactiveCells[{x,y}]` | holes (LevelData.cs:10, GridManager.cs:38-45) |
| `GridBlockDatas[].gridPosition` | the block's pivot cell (LevelData.cs:17) |
| `GridBlockDatas[].blockColor` | BlockColor int (LevelData.cs:18) |
| `GridBlockDatas[].shapeOffsets` | cells relative to the pivot; empty = 1x1; (0,0) added if missing (Scripts/Block.cs:49-60) |
| `ExitDatas[].exitNumber` | ignored, overwritten with index+1 (GridManager.cs:49-53) |
| `ExitDatas[].gridPosition` | an in-grid cell; the exit sits on its outer edge (LevelData.cs:27) |
| `ExitDatas[].requiredColor` | BlockColor int (LevelData.cs:28) |
| `ExitDatas[].direction` | 0 Left, 1 Right, 2 Top (+y), 3 Bottom (-y) (LevelData.cs:33-39) |
| `ExitDatas[].shapeOffsets` | the span, relative to the pivot; the pivot always included (ExitService.cs:41-46, GridManager.cs:233-234) |

All six shipped levels: `timerCount` 300, no holes, exits on the outer boundary spanning 2 or 3 cells. Level_01 is 4x5 with a
blue 2x2 and a purple 2x2, solved in two drags. Level_06 is 6x6 with 8 blocks (1x3 bars, 1x2 bars, 3-cell L shapes), two
yellow and two blue blocks sharing one exit per colour: several blocks may share one gate.

## Blocks
- Any polyomino through `shapeOffsets`; visuals from modular pieces chosen by neighbour analysis (Block.cs:119-179, 284-338).
  Blocks never rotate (no rotation code). `CanMove()` is always true (Block.cs:343-346).
- `BlockColor`: Green 0, Yellow 1, Blue 2, Red 3, Orange 4, Purple 5, DarkGreen 6 (Scripts/BlockData/BlockData.cs:5-14); all
  seven wired into ItemFactory (GameScene.unity:1608-1615, ItemFactory.cs:56-59).

## Dragging (free 2D, continuous)
- Pick up: raycast on `blockLayer` (Scripts/Services/Input/InputHandler.cs:61-74); outline width 5; lift 0.3 over 0.15 s
  (InputHandler.cs:99-100, MovementSettings.asset:21-22).
- Drag: pointer on a horizontal plane with the grab offset kept (InputHandler.cs:88-94, 105-113). Movement is capped at 1.5
  cells per frame (Scripts/Services/Movement/BlockMovementService.cs:18-22); the farthest valid point along the straight
  line is found by 0.1-cell steps, 8 binary-search iterations and a 0.005 safety buffer (BlockMovementService.cs:51-113); if
  blocked it slides along X or Z, whichever ends closer to the pointer (BlockMovementService.cs:35-49). Diagonal moves are
  allowed when clear. The transform lerps toward that point with factor dt*20 (InputHandler.cs:120-124).
- Logical position: the pivot's world position rounded to a cell; when that cell changes, occupancy moves (InputHandler.cs:127-133,
  BlockGridService.cs:16-54). Release snaps to the rounded pivot cell in 0.1 s (InputHandler.cs:163-180).
- Collision `IsPositionValid` (BlockMovementService.cs:115-154): for each block part four corner points at +-0.4 cell, each
  rounded to a cell; invalid if out of bounds, inactive, or occupied by another block. So blocks never pass through other
  blocks, holes or the edge; dragging alone never leaves the grid; a 1-cell gap is passable only within about +-0.1 cell of
  alignment; partial moves stop flush against an obstacle.
- MovementSettings in use: dragSpeed 20, maxMovePerFrame 1.5, collisionPadding 0.4, pathCheckStep 0.1, binarySearch 8,
  safetyBuffer 0.005, lift 0.3/0.15 s, snap 0.1 s (MovementSettings.asset:15-23).

## Exits
- An exit sits on one side of one or more in-grid cells, its visual outside that edge (GridManager.cs:227-228, 335-353). The
  level editor only allows exposed edges (the boundary or next to a hole) and merges adjacent same-colour same-side cells
  (Editor/LevelEditorWindow.cs:532-543, 637-691).
- The check runs only during a drag and only when the rounded pivot cell changes (InputHandler.cs:130-138); never on pick-up
  or release.
- `CanBlockExit` (Scripts/Services/Exit/ExitService.cs:16-25): `FindMatchingExit` takes the FIRST exit in `ExitDatas` order
  whose colour matches and which overlaps at least one block cell (ExitService.cs:27-64); only that one is evaluated.
  `IsPathClear` (ExitService.cs:67-122) marches every block cell in the exit direction to the edge: another block on the way
  fails (112-116); on leaving the grid the cell's lane (y for Left/Right, x for Top/Bottom) must be one of the exit's lanes
  (71-84, 98-110); inactive cells do not block (GetCell returns null).
- Net rule: colour matches, at least one cell on the exit's edge cells, the block's extent across the exit within the span,
  no other block between any cell and the edge. A wrong-colour exit is skipped; the edge acts as a wall; no penalty.
- Sequence: drag stops, snap 0.1 s (InputHandler.cs:143-161); `PerformExit` frees the cells and disables colliders
  (ExitService.cs:136-137, 320-347); the bar sinks 0.6 over 0.1 s (210-217); the block moves out by (cells to the far edge + 2)
  at 0.1 s per cell, linear (161-202); particles while aligned (220-227, 256-318); on completion `OnBlockExited`, the block is
  destroyed, the bar rises back over 0.2 s (232-253).

## Timer, win, fail
- Duration `timerCount` seconds (GameManager.cs:310). Starts on the first mouse-down anywhere, block or not
  (InputHandler.cs:43-48, GameManager.cs:384-392), which also fires `OnGameStarted`. Counts down by deltaTime (164-184).
  Display `MM:SS` floored (UIManager.cs:50-56); below 50 s every new second punches the clock and flashes red (UIManager.cs:57-66).
- Fail: at `remainingTime <= 0` the timer stops and `ShowFail` runs (GameManager.cs:170-178, UIManager.cs:76-79); the fail
  menu fades in, "out of time" scales in over 0.3 s, then Continue (FailCanvasAnimation.cs:25-35), which loads MenuScene.
- Win: when `spawnedBlocks` is empty after an exit completes, the timer stops and `ShowWin` runs (GameManager.cs:394-418);
  background, text, Continue, coin pile about 0.3 s apart (WinCanvasAnimation.cs:20-36). Continue adds +50 coins and level+1
  in PlayerPrefs and loads MenuScene (WinMenu.cs:8-29). Coins are never spent and only show in the menu.
- No input lock after win or fail (InputHandler.cs:41-59). Restart rebuilds the board and resets the clock
  (RestartButton.cs:56-63, GameManager.cs:264-331). Levels load from `Application.dataPath/Levels/Level_NN.json`
  (LevelManager.cs:144-153, 184-197); above 6 a random existing file is chosen (155-179).

## Camera
- Perspective, FOV 60, pitched 75 degrees down, start (0, 15, -4.2) (GameScene.unity:1475-1477, 1502, 1507).
  `CameraController` re-fits only when the board is generated: fixed rotation, distance to show the board plus 1.5 units of
  padding, clamped 5-50, animated over 1.5 s ease-out-cubic (Scripts/Camera/CameraController.cs:46-53, 63-83, 149-206). No
  zoom input, pan or follow.

## Absent (whole-word search of all game and editor scripts)
booster, bomb, ice/frozen/freeze, key(s), chain(s), lock(ed), hint(s), undo (only the editor's Undo.RecordObject), moves /
moveCounter, star(s), hammer, vacuum, magnet, shuffle, lives/heart, revive, extra time, pause, sound/audio/AudioSource,
haptic, score, rotate, obstacle, wall(s). Also absent: block rotation, a move limit, star ratings, continue-for-coins,
special cells beyond holes, multi-colour or layered blocks.

## Quirks
- A block on an inactive cell would null-reference at spawn (GameManager.cs:362-365, ItemFactory.cs:48-49); no shipped level
  has holes, so this never triggers (the tool's validator rejects it).
- Colliders are disabled only when `PerformExit` starts, after the 0.1 s snap (ExitService.cs:137).
- Dead code, not rules: `GridManager.ClampPositionToGrid`, `IsExitPosition`, `Block.Update`, `SpawnConnectors`,
  `GameManager.LoadNextLevel/LoadLevel/LoadLevelByName`.
