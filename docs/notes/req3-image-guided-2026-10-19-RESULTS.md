# Image-guided test set 2: ten hard asks on the owner's ten renders (2026-10-19)

Runs: `run-r1.log` (S1-S6 on the first build of the day), `run-r1b.log` (S2 S3 S5 S7-S10 after the coverage-row crash
fix), `run-r1c.log` (S2 S3 S6 S8 reruns with the repair-in-reading, stranded-gate, level-number and "stuck twice" fixes),
`run-r1d.log` (S10 with the "harder" transform and the shade split). Per case: `results/<id>.json` (every row, every
version, the log), `creatives/<id>/` (ad.mp4, board.png, level.json per version), `COMPARE.png` (reference beside the
board played). The check contract: `../IMAGE-GUIDED-EVAL-CHECKS-2026-10-19.md`. The owner's own creative that started this
(06:49, "create a similar game concept, just use one more color"): a different ring, 3 colours, every row passing.

## 1. The table (final version of each case)

| case | picture | ask (short) | board | what the rows measured | misses | viewer |
|---|---|---|---|---|---|---|
| S1 | T10 reef | the owner's prompt: similar concept, one more colour | **copied** cell for cell (8x8 ring, 9 blocks); one yellow block -> blue with a blue gate | the board is the picture's: pass; +1 colour: pass; likeness: yes; coverage: complete | 0 | ship |
| S2 | T1 candy (Turkish) | this board, one colour fewer, candy look, one stuck, 45 s | **copied** after a gate repair (the render was unsolvable); -1 colour **not done** (yellow->red unsolvable) | the board is the picture's: pass; -1 colour: FAILED and said; the stuck moment: fixed in v2 | 1 | ship |
| S3 | T9 mirror world | same two-room board mirrored L-R, cliffhanger "Which one goes first?", 40 s | **copied** and mirrored (the layout is itself symmetric) after a stranded-gate repair | the board is the picture's: pass; mirrored: pass; likeness: yes | 0 | fix (6 blocks cannot fill 40 s; 15 s end card) |
| S4 | T5 space station | this exact board, +1 colour, space look on everything, time-out, 50 s | **type** (the solver cannot settle the 7x10 lane board in 20 s), said in the plan | +1 colour measured on the type path; coverage flagged it first | 0 | ship |
| S5 | T7 wooden photo | only the board, blue -> green, clean win, 30 s | **copied** from a perspective photo; blue -> green on blocks and gates | the board is the picture's: pass; a colour became another: pass; likeness: yes | 0 | fix (4 blocks: 9 s of play in 30 s) |
| S6 | T3 garden | inspired by this image, same level number and clock, stuck twice, near-fail, 60 s | **copied** (plus-shaped rooms), level 103 kept, garden look | the board is the picture's: pass; the level number: pass; mistakes 2: pass; likeness: partly (the render's ledges vs walls) | 0 | ship |
| S7 | T4 cargo cross | a NEW level shaped like this cross, same colours, picture's background, calm win | **type** by request (cells read, not copied) | the board's shape/colours: pass; nothing copied: pass | 0 | ship |
| S8 | T8 neon arcade | exactly as shown but flipped T-B, neon captions only, no HUD, time-out, 35 s | **copied** (7 colours, the game's maximum) and mirrored T-B after a gate repair | the board is the picture's: pass; mirrored: pass; the screen: pass | 0 | ship |
| S9 | T6 construction | this board, yellow -> blue, +1 colour, game's own look, two mistakes, near-fail, 45 s | **copied**; yellow -> blue on blocks and gates; one blue block -> green with a green gate | all three transform rows: pass; likeness: yes ("only the asked changes differ") | 0 | ship |
| S10 | T2 neon lab | this exact level, same colours, harder: one more block in the way, near-fail, 30 s | first run: **copied** but "harder" neither done nor flagged (the silent pass the owner feared); rerun: **copied**, two greens split, a missing dark-green gate repaired, one blue one-cell block added in the way | harder than the picture's board: pass (9 drags against 8); likeness: partly (the gate shade); coverage: complete | 0 | ship ("harder shows only as one small block") |

Totals: 8 of 10 boards copied cell for cell (S1 S2 S3 S5 S6 S8 S9 S10), 1 built as its type by request (S7), 1 built as its type because the solver could not settle the render (S4). Every case ends with a coverage row and no `not measured` ask; the one failed request row left standing (S2's -1 colour) is said in the plan and fixed in code for the next run.

## 2. What the evaluation caught today that it could not before
| defect | caught by | fixed in |
|---|---|---|
| "+1 colour" lost on the owner's creative | nothing (every row passed) | the copy path + `more or fewer colours than the picture` row + coverage |
| "+1 colour" lost on the type fallback (S4) | `Coverage: not measured` | the row now runs on the type path too |
| "gets stuck twice" read as one mistake (S6) | `Asked: mistakes` failed against the plan's 2 | `audit.asked` |
| "the same level number" had no row (S6) | `Coverage: not measured` | `Image: the level number` |
| "harder: one more block in the way" neither done nor flagged (S10) | the viewer only ("the level doesn't look harder") | `imagecells.add_blocker` + `harder than the picture's board` row + coverage ask |
| a merge of the rarest colour left the board unsolvable (S2) | `more or fewer colours` failed, said in the plan | `remove_colour` tries every pair with the gate repair |
| a 15.5 s end card on a 6-block board at 40 s (S3) | the viewer only | `the end card is a card, not padding` row (D5) |
| two shades of "green" merged (S10) | `looks like the picture (viewer)`: partly | `split_shades` |
| a gate named "purple" beside "magenta" blocks (S8) | `no gate was read for the magenta blocks` doubt -> repair | gate names take the block name of their family |
| a 20-minute hung CLI call in the likeness reading (S2) | the stage timing | 150 s timeout on that optional reading |

## 3. Reading accuracy on the ten renders (cell by cell)
| picture | read | verified | playable as drawn | result |
|---|---|---|---|---|
| T10 reef | 8x8 ring, 9 blocks, 9 gates | 64/64 cells, 0 doubts | yes, 12 drags (the real minimum) | exact copy |
| T1 candy | 9x10 ring, 10 blocks | 90/90, 0 doubts | no: a 2-cell red gate added (14 drags) | copy with a said repair |
| T9 mirror world | 7x7, 6 blocks, the divider as a column of wall cells | 49/49 | no: the green blocks fit no green gate; two gates added (6 drags) | copy with a said repair |
| T5 space station | 7x10, 10 long bars, 14 wall cells | 70/70, 1 doubt | the solver gives up at 250k positions (3M positions, 7 min offline: still no answer) | type fallback, said |
| T7 wooden photo | 5x7, 4 blocks (perspective) | 35/35 | yes, 4 drags | exact copy |
| T3 garden | 7x9, 10 blocks, 5 wall cells | 63/63 (muted greens needed the adaptive floor rule) | yes, 11 drags | copy; the viewer sees ledges the pixels cannot |
| T4 cargo cross | 8x8 plus, 8 blocks | 64/64 | yes, 9 drags | not copied (a new board was asked) |
| T8 neon arcade | 9x10, 10 blocks, 7 colours | 90/90, 1-2 doubts | no: a dark-green gate missed by the reader; repaired | copy with a said repair |
| T6 construction | 8x9, 7 blocks, 6 wall cubes | 72/72 | yes, 9 drags | exact copy + transforms |
| T2 neon lab | 6x8, 8 blocks, 6 wall cells | 48/48 | yes, 8 drags | exact copy (shades split in the rerun) |

The renders are not the game's own levels: 4 of 10 cannot be played as drawn (a gate missing or too narrow). The
repair adds the smallest gate and the plan says so; that is the honest translation of a picture into a playable level.

## 4. Limits, stated
- A board the solver cannot settle in 250k positions (T5's lanes) is built as its type, and the plan says why.
- "Harder" is one added one-cell block that raises the solver's minimum; "easier" is not made (said as a failed row).
- A copied board has the blocks it has: a 4- or 6-block board does not fill 30-45 s of play; the end-card row now says
  so, and the viewer does too. The remedy is the request's (a shorter ad, a near-fail with mistakes, a calmer tempo).
- The viewer model's likeness judgement is a second opinion; "partly" on T3 and T6 points at ledges and corridors the
  pixel check cannot read. It is info, never silent.
- Non-English requests are translated once for the parsers (S2); the planner always read them.
- The quick tunnel died on its own at 09:21 and the live site was offline for an hour until `engine-online.sh start`.
