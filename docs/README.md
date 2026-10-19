# Documents: where to look

Start with the report, then the skills, then the workflow rules and the test results.

| read | what it is |
|---|---|
| [REPORT.pdf](REPORT.pdf) / [REPORT.md](REPORT.md) | the technical explanation asked for by the case: architecture, components, why this approach, deterministic vs generative, consistency, controlled editing, limitations, production roadmap |
| [../.claude/skills/README.md](../.claude/skills/README.md) | the eleven Agent Skills: the game's rules as implemented, the eight prompt controls, and each workflow's contract (level and gameplay, controlled editing, the viewer's review, video-guided, image-guided, prompt enhancement, feedback and lessons, soundtrack, evidence) |
| [ENGINE-NOTES.md](ENGINE-NOTES.md) | the engine's own notes, section by section, as they were written while building (setup, commands, rules, recording, scenarios, compositor, text-to-creative, level generation, editing, references, video-guided, length) |
| [examples/INDEX.md](examples/INDEX.md) | the example creatives of the submission (text, image-guided, video-guided, controlled edits) and what each shows; the creatives themselves are on the live app's Showcase |
| [TEST-ASSETS.md](TEST-ASSETS.md) | the test inputs anyone can attach (trailers, reference pictures, objects, textures, logos, stickers, a music track) |
| [DEMO-WALKTHROUGH.md](DEMO-WALKTHROUGH.md) | a scene-by-scene walkthrough of every function of the site, with narration |

## Working notes (`notes/`), in the order the work was done

| file | about |
|---|---|
| CASE-ANALYSIS-AND-WORKFLOW | the case read against its rubric, the game's C# facts, the plan |
| RESEARCH-TOOLS-PAPERS | the papers and tools that decided the architecture |
| COMPETITOR-ADS | about 136 real ads of Color Block Jam and its rivals, tagged by ending |
| SOLVER-REPORT, RUNNER-REPORT, SCENARIO-REPORT, COMPOSITOR-REPORT, LEVEL-GAMEPLAY-REPORT, TEXT-TO-CREATIVE-REPORT, CONTROLLED-EDITING-REPORT | one report per component as it was built and checked |
| CASE-TEST-REPORT | the 82-scenario run against the whole case and the failure groups it found |
| DESIGNER-EDITS-REPORT, TEST-CASES-REQ1-REQ2-ENDINGS | the 48-prompt edit audit; the ending test sets |
| EVAL-COVERAGE | every point the case highlights mapped to the row that measures it |
| T2C-AGENTIC-WORKFLOW, REQ3-IMAGE-GUIDED-RULES, REQ4-WORKFLOW-RULES, IMAGE-GUIDED-EVAL-CHECKS | the rules of the text, image-guided and video-guided workflows and their check contracts |
| REQ5-FINAL-APPROACH | the final approach to controlled editing (the document, the contract, the tiers, the proof) |
| PROMPT-ENHANCEMENT-AND-TRENDS, SOUNDTRACK, FEEDBACK-AND-LESSONS | the parts around the workflows, and the COLLEAGUE.SKILL reading |
| req3-…-RESULTS, req4-…-RESULTS, req5-…-RESULTS | the last three test sets: image-guided S1-S10, video-guided V0-V6, controlled edits E1-E5 |

Paths inside the notes that start with `~/rollic-case/` refer to the author's working folder; the files they name are
either in this repository or are generated data (creatives, recordings) that stays with the engine.
