# cbj-creative skills

Portable [Agent Skills](https://agentskills.io/specification) for the CBJ creative tool. Claude Code discovers
them from `.claude/skills/`; other agents find the same directory through the `.agents/skills` symlink. Each skill is one
directory with a `SKILL.md` (frontmatter + instructions) and, where needed, `references/` loaded on demand.

They exist so that every agent in the workflow (the one that improves a user's prompt, the one that plans the brief, the
one that edits an approved creative, the one that audits a result) works from the same facts: the game as it is
implemented in the provided Unity project, the eight prompt controls, and what this tool can and cannot do.

| skill | covers | read it when |
|---|---|---|
| `cbj-game-rules` | the game as implemented: board, blocks, gates, exit rule, timer, win/fail, camera, the level file, what does not exist | any question about what is possible in the game; before judging a level, a move or a mechanic |
| `cbj-prompt-controls` | the eight prompt controls, their vocabulary, defaults and limits; how to write or improve a prompt the planner reads well | improving a user's prompt; reading a prompt into a brief; explaining a plan row |
| `cbj-level-gameplay` | core requirement 2: level shapes, pieces, looks, difficulty bands, endings, orders of interactions, pacing, and the checks on the recording | a prompt about the level or the play; judging whether generated gameplay matches the ask |
| `cbj-controlled-editing` | core requirement 5: how an edit changes only what it asks, the smallest re-run, board edits, timing, undo, A/B, refusals, the edit report | any follow-up prompt on an existing creative; judging an edit |
| `cbj-creative-review` | the viewer's review: the rubric, what is measured, the loop (make, review, edit, review) | judging a finished creative from the viewer's side; closing the loop |
| `cbj-video-guided` | core requirement 4: a prompt plus a video or image, the reading plan, the whole-clip reading on NVIDIA build, what each focus may change, the provenance, the reference rows, the measured reliability | any creative made from an attached video or image; judging what was taken from a reference |
| `cbj-image-guided` | core requirement 3: a prompt plus a reference picture, the role first (style, board, asset, modify), the whole-picture and board readings with code measures, the colours to the seven rendered slots, the board clamped and said, nothing copied, the image rows and the measured reliability | any new creative made from an attached picture; judging what was taken from it or what was not |
| `cbj-prompt-enhancement` | the prompt enhancer (the planner's vocabulary in, nothing added, questions for the rest; the code checks and the fallback) and the optional trend ideas (signals, safety, checks) | enhancing or judging an enhanced prompt; reviewing a trend idea before it is used |
| `cbj-feedback-lessons` | designers' feedback records (the scene captured by code) and the owner's versioned LESSONS (two tracks, evidence checks, corrections, rollback); the zero-effect rule | triaging feedback; deciding what to change in a workflow from a lesson; judging whether a lesson is backed by records |
| `cbj-soundtrack` | the optional soundtrack: a bed synthesised from a version's facts (theme, tempo, parts, exits, ending, clock) and the hook spoken by NVIDIA Magpie; delivered as an upload the music edit places; what NVIDIA build has and lacks for audio | making or judging a soundtrack; any question about audio or music generation on NVIDIA build |
| `cbj-creative-evidence` | where every fact of a version lives and how to verify a creative or an edit by hand or with the harness | auditing a result; writing a report; reproducing a case |

Standard for every skill here (checked by `python .claude/skills/scripts/validate_skills.py --strict`):
frontmatter `name` (= directory), `description` with a "Use when" trigger, `metadata.spec-version` and
`metadata.last-verified`; seven sections in this order: 1 Purpose, 2 Source of truth, 3 Facts, 4 Procedure,
5 Not possible here, 6 Evidence, 7 Change rules; body under 500 lines; links that resolve.

Keep a skill in the same edit as any change to the rule, field or behaviour it describes, and bump `last-verified`.
