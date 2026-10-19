# Acceptance rules for an edit (what an auditor compares)

Adapted from the case's control-and-consistency scenarios (2026-10-14) to what this tool stores. Apply every rule to the
version against its immediate parent (`from`), and for a multi-step chain also against the original base.

1. **Target correctness.** The requested element changed in the requested way. Lookalike things (a second picture of the
   same role, the other red block) did not change unless the request said "everywhere".
2. **Non-target preservation.** Outside the edited layers and the edited time window: the same recording (or the same
   job re-filmed with identical game state), the same parts and lengths, the same camera, the same pictures (file hashes),
   the same captions, the same sound-effect stem, the same music unless asked.
3. **Gameplay consistency.** When the play changed: every drag legal on the (new) board, no block through a wall or
   another block, no exit through a wrong gate, the ending as asked; a board edit's kept prefix identical move for move.
4. **Locality.** For a look-only edit the frame diff is confined to the edited layers' boxes and to the frames where
   they show; a re-filmed look is proved by game state per frame, not pixels (about 1 % of frames differ by a few pixels
   between two films of the same job).
5. **Honest feasibility.** Mutually incompatible asks are refused with the conflict named; a locked invariant is never
   changed silently; a missing file is asked for, never substituted.
6. **Repeatability.** The same request on the same base gives the same plan (planner_same) and the same frames (the
   three-run case compares pairwise "the same"); the same absolute request sent twice is refused the second time.

What to read, in this order: `proof.verdict`, `proof.rows` (nine, none NOT ASKED), `proof.pixels` (frames_changed,
ranges, layers, same_sound, note), `level_edit` (what, kept, of), `stages` (which stage actually ran and for how long),
`qa.warnings` (reading time, hook not on frame 0), then `compose.json` (sfx_sha256, music, camera, format) and the
inventory (`/api/inventory/<id>`) for the names.
