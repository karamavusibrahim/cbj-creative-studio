# Agents working in this repo

Skills for every agent in the workflow (prompt improvement, planning, editing, auditing) live in `.claude/skills/`
(also reachable as `.agents/skills/`). Read `.claude/skills/README.md` first; load `cbj-game-rules` before judging
anything about the game, `cbj-prompt-controls` before touching a prompt, `cbj-controlled-editing` before any edit of
an existing creative, `cbj-creative-evidence` before writing a report. Validate after editing a skill:
`python .claude/skills/scripts/validate_skills.py --strict`.
