# Color Block Jam Creative Studio

A tool that turns a sentence, optionally with a picture or a video, into a 30-60 second **Color Block Jam** ad
creative whose gameplay is played and recorded inside the real Unity game, and that edits a finished creative one
change at a time with a measured proof of what was kept. Built for Rollic's "AI Engineer, Creative" case.

- **Live app:** https://cbj-creative-studio.vercel.app
- **Passcode** (needed once per browser to make or edit; browsing needs none): `geV0rjLVte`
- **Technical explanation:** [docs/REPORT.pdf](docs/REPORT.pdf) (also as [Markdown](docs/REPORT.md))
- **How to use the app, page by page:** [docs/HOW-TO-USE.md](docs/HOW-TO-USE.md)
- **Example creatives:** the Showcase on the live app (one text-driven, image-driven, video-driven and
  controlled-edit example each, with their evidence pages), and `docs/examples/INDEX.md`

The large language model writes only data (a typed brief, a reading of a reference, a review). Every gameplay pixel
is produced by the game itself from a level an exact solver proved solvable and a drag script the game replayed one
frame at a time. A follow-up request is a patch to that data, never a new generation, and a nine-row report measured
from the stored files proves what changed and what stayed.

---

## 1. Using the app (no install)

Open https://cbj-creative-studio.vercel.app. The header says whether the engine (a Mac with the Unity game behind the
site) is **online**. When it is offline, the Showcase still works; making and editing wait for it.

1. **Create.** Type what you want in plain words (English or Turkish). Optionally attach a reference picture, a
   reference video, or an asset to place. Press **Enhance prompt** to see your request rewritten in the words the
   planner reads best (nothing is added; suggestions come as questions you can tap), or open **Start from a trend**
   for prompts written from today's trends. Press **Generate creative**. The first time, enter the passcode.
2. **Read what the tool understood.** A table of the case's eight prompt controls shows how each was read
   (applied, default, adjusted, not supported), then the progress through plan, level, play, record, compose, review.
3. **Review the result.** The player, the level and its checks (measured from the game's own log), and the viewer's
   review (a model's opinion, its measured scores marked apart). Under it, **Was this what you asked?** sends feedback
   tied to the step it concerns; **Download report** gives every intermediate step as one file.
4. **Edit.** Press **Edit this creative**. Replace, rewrite or remove one thing from **Things in this ad** with no
   prompt, or describe one change. The new version's card shows what was **Locked**, what was **Allowed** to change,
   and whether anything changed without being asked (that box must be empty). **Details** opens the full checklist,
   the frames that changed, and **Compare** between any two versions.
5. **Showcase.** Finished creatives with their full evidence, available with the engine off.

Test inputs (the Color Block Jam trailers, reference pictures, objects, textures, logos, stickers) can be attached from
the Create page's sample assets; they are also listed in `docs/TEST-ASSETS.md`.

## 2. Using the app with your own Claude account

The studio runs on its owner's Claude account by default. To run it on **yours**, use your own Claude Code login on
your own machine; no API key is involved:

1. Clone this repository and install (section 3). Log in once with `claude`. In `.env` set `CBJ_PLANNER=claude` and
   `GEMINI_API_KEY=...` (a free Google AI Studio key, used to read reference videos). Prove it with
   `uv run cbj setup-check --live`.
2. Start the engine for the hosted site:
   ```
   CBJ_CORS_ORIGINS=https://cbj-creative-studio.vercel.app uv run cbj ui
   ```
3. On https://cbj-creative-studio.vercel.app open the key icon → **My own engine**, paste `http://127.0.0.1:8765`,
   press **Check**, then **Save**. From then on the site talks to your engine only: every call and every video goes to
   your machine, no passcode is needed, and the header reads "Your engine · claude-cli/opus".

Chrome, Edge and Firefox allow the site to reach your local engine; Safari does not, so use a tunnel address instead
(`cloudflared tunnel --url http://127.0.0.1:8765`, and start the engine with `CBJ_ALLOWED_HOSTS=*.trycloudflare.com`).
If you only want reference videos read on your own Gemini quota while keeping the studio's planner, the same dialog
takes a Gemini key alone.

## 3. Running everything yourself

Requirements: macOS, [Unity](https://unity.com) 6000.3.5f1 (the version of the provided project), `ffmpeg`,
[`uv`](https://docs.astral.sh/uv/), Node 20+, and the Color Block Jam Unity project from the case placed next to this
folder as `../CBJ` (it is Rollic's material and is not part of this repository).

```bash
uv sync                                   # the Python engine
uv run cbj build-player                   # builds the game player with the recorder (about 35 s)
cp .env.example .env                      # then fill CBJ_PLANNER=claude and GEMINI_API_KEY=...
uv run cbj setup-check --live             # proves the login, the key, ffmpeg, the player
uv run cbj ui                             # the engine on http://127.0.0.1:8765
cd web && npm i && npm run dev            # the site on http://localhost:3000, pointed at that engine
uv run pytest -q                          # 1,481 tests
```

Command line without the site: `uv run cbj plan "..."`, `uv run cbj make ...`, `uv run cbj review <id>`,
`uv run cbj report <id> --format html`, `uv run cbj enhance "..."`, `uv run cbj trends`, `uv run cbj feedback`,
`uv run cbj lessons --distill`. `uv run cbj --help` lists all 27 commands. The full engine notes are in
[docs/ENGINE-NOTES.md](docs/ENGINE-NOTES.md).

## 4. How it works, in one picture

```
request (+ picture / video)
   → route in code → planner LLM writes the brief (8 controls, forced schema; nothing else)
   → level generator + exact solver (the game's own LevelData JSON)
   → play script (mistakes, hesitations, the clock fitted to the ending)
   → the real Unity game plays and records it (fixed step, 1080×1920 @ 30 fps, its own log of every frame)
   → compositor (hook, captions, end card, layers; per-frame hashes; GOP-level patching for edits)
   → evaluation: checks from the recording · the prompt's facts measured · the game's rules replayed ·
                 the viewer's review (a model) → revision loop (at most two rounds, best version kept)
```

Four workflows share this spine and one evaluation vocabulary: text, image-guided (the picture's role is decided
first: style, board to copy, asset, modification), video-guided (the clip read whole for structure, pace, hook,
ending; its board copied cell by cell when asked), and the controlled edit (route → whitelist → the smallest re-run →
the nine-row proof). Designers' feedback is tied to the step it concerns and distilled, with the evidence, into a
versioned lessons document for the owner, after COLLEAGUE.SKILL (arXiv 2605.31264). The report explains each part,
why this architecture, what is deterministic and what is generative, consistency, controlled editing, limitations and
the production roadmap.

## 5. For evaluators: where to look

1. [docs/REPORT.pdf](docs/REPORT.pdf): the technical explanation (architecture, components, why, deterministic vs
   generative, consistency, controlled editing, limitations, production).
2. The live app: one creative of each kind in the Showcase with its evidence page; make one yourself with the passcode.
3. [.claude/skills/](.claude/skills/README.md): the rules every agent works from (the game as implemented, the eight
   prompt controls, each workflow's contract).
4. [docs/README.md](docs/README.md): the working notes in order, from the case analysis and the competitor-ad study to
   the component reports, the evaluation coverage and the last test sets.
5. `src/cbj/workflows/`: the four agentic workflows; `src/cbj/audit.py`, `checks.py`, `editreport.py`: the evaluation;
   `tests/`: 1,481 tests.

## 6. Repository layout

| path | what |
|---|---|
| `src/cbj/` | the engine: brief, planner, level, solver, rules, play, render, compose, audit, review, route, edits, feedback, lessons, report, enhance, trends, soundtrack, keys; `workflows/` the four agentic workflows |
| `unity/` | the CreativeRunner script and the game patch added to a copy of the provided project at build time |
| `web/` | the Next.js site (Create, Edit, Showcase, Feedback), its relay and QA scripts. The finished creatives are not in git: the Showcase is exported from the engine (`web/scripts/export_showcase.py`) into the deployment, and the larger catalogue is published to Cloudflare R2 (`scripts/r2_publish.py`) |
| `.claude/skills/` | eleven Agent Skills that fix the game's rules, the prompt controls and each workflow's contract for every agent that touches a request |
| `tests/` | the unit suite |
| `docs/` | the technical report, the engine notes, the example index, the test assets list, the working notes |

## 7. Notes

- Nothing is changed automatically from feedback: the owner reads, verifies against the evidence and edits code or a
  skill by hand; the lessons document keeps versions and can be rolled back.
- The engine makes one creative at a time (one game player). A creative takes a few minutes with the review and the
  revision loop on.
- The passcode above protects the owner's engine; it can be rotated at any time in the site's settings.
