# Rollic CBJ case: repos, papers, MCPs and skills worth using

Research run on 2026-10-09 (day 2 of 10). It has three parts:
- a deep-research workflow: 105 agents, 23 sources, 25 claims checked by 3-vote adversarial verification (23 kept, 2 refuted);
- four targeted follow-up agents that checked repos through the GitHub API, papers on arXiv, and docs at the source;
- direct checks on the CBJ project folder.

Star counts and dates are as of 2026-10-09. Anything not confirmed at the source is marked UNVERIFIED.
Companion to `CASE-ANALYSIS-AND-WORKFLOW.md`. Section 1 lists what this research changes in that plan.

---

## 0. Bottom line

The research supports the "deterministic core, generative shell" architecture. Three kinds of evidence point the same way:
- **LLMs make poor puzzle levels.** Only 20-47% of LLM-written puzzle levels were solvable (ScriptDoctor), and LLMs hit a target solution length 17% of the time (Todd et al.).
- **Generative editing of gameplay is not reliable.** Every "replace this object" video model needs CUDA, takes minutes per 5 s clip, and still flickers or leaves shadows behind.
- **The case itself rules out fakes.** Color Block Jam's own ads are 100% real gameplay, and the UK ASA has ruled that gameplay ads must show the real game.

So the plan stands. The useful output of the research is:
- a short list of tools to install;
- a better generator design;
- a concept library grounded in CBJ's actual ads;
- about 35 citable papers for the technical write-up.

**Adopt now (ranked):**

| # | What | For which component | Why |
|---|---|---|---|
| 1 | Hand-rolled capture: `Time.captureDeltaTime` + RenderTexture + `AsyncGPUReadback` (Unity Recorder as fallback) | Unity renderer | About 80 lines of C#, no package, works in a windowed standalone player. CBJ uses the built-in pipeline and all its timing reads `Time.deltaTime`, so every frame is reproducible (checked in the code) |
| 2 | Solver/generator design from section 3 (flood-fill drag moves, greedy exit closure, farthest-state generation, Jarušek–Pelánek difficulty) | Solver/generator | Grounded in the only Color Block Jam-style prior art and in human-difficulty studies |
| 3 | `ffmpeg psnr/ssim stats_file` + numpy diff bounding box + scikit-image SSIM map | Controlled editing proof | Tested on this machine: unedited frames give PSNR inf and SSIM 1.000000, and the changed box is located exactly |
| 4 | PySceneDetect (AdaptiveDetector) + Gemini video, static mode at raised fps | Reference analysis | Cuts come from the detector, accurate to the frame. The VLM only labels shots, because VLM timestamps are still unreliable |
| 5 | Remotion (already installed as skills) driven by JSON props; HyperFrames as the Apache-2.0 swap | Compositor | You know Remotion. Its license is free for you but not for Rollic; say so in the roadmap |
| 6 | pydantic v2 + `jsonpatch` + segments keyed by id (dict, not array) | Planner + controlled editing | RFC 6902 addresses array items by index, so keying by id keeps patch paths stable |
| 7 | Gradio + Huey (SQLite) or a plain asyncio subprocess queue | UI | Built-in drop zones, video and JSON components. Unity renders one job at a time anyway |
| 8 | rembg with `birefnet-general` (MIT) | Asset generation | Not BRIA RMBG-2.0, which is CC BY-NC (non-commercial) |
| 9 | CoplayDev unity-mcp | Build-time tooling | Free, MIT, Unity 6 + Claude Code confirmed. Use it to author scripts and scenes, not to render |
| 10 | Kling MCP (already connected) with `first_image` + `tail_image` | AI hook/outro | Start and end frame confirmed on kling-video v3.0, v2.6 and v2.5 |

---

## 1. Changes to the plan in CASE-ANALYSIS-AND-WORKFLOW.md

1. **Generator (section 4.1).** Replace "take a solved empty board and run the solution backwards".
   - The closest prior art (nna774/iro-nuke) found that random backward scrambling "only produced easy boards".
   - Use this instead: pack blocks densely at random → full BFS → start from the reachable state that is farthest from the goal with every block still on the board → reject if outside the target difficulty window, or anneal.
   - Sources: Taylor & Parberry 2011; the CAST repo's IDA* window rejection; the energy function in fogleman/rush.
2. **Difficulty metric.** Use the minimum number of drags `D`.
   - In base CBJ rules, moves are reversible and an exit never hurts, so there are no dead ends. The timer is the only way to fail.
   - Shortest-solution length predicts human solve time on Rush Hour with Spearman 0.90 (Jarušek & Pelánek 2011). CBJ is a reversible transport puzzle like Rush Hour, so this should carry over (an inference).
   - Add a simulated-human difficulty `M` as a second metric (section 3).
3. **Near-fail script.** Build it from evidence instead of ad-hoc detours:
   - a human-like random walk with a low greediness bonus;
   - wrong moves from Bockholt et al.'s 11 Rush Hour error types;
   - the final exit lands at about T−1 s;
   - **only on medium-hard levels.** Moon et al. 2026 found fail ads on "reasonably challenging" levels drive more download intent than extreme ones.
4. **Concept library.**
   - Demote `fail_bait`. SocialPeta's CBJ report says the game "avoids intentional failures or fake ads". A real near-fail on a real level is on-brand; staged incompetence is not.
   - Add **Brain Age Meter**, CBJ's main live hook per Insightrackr.
   - Section 5 has the merged eight-template library.
5. **Capture.**
   - The project uses the **built-in render pipeline**: `m_CustomRenderPipeline: {fileID: 0}`, no URP asset, Post Processing v2. Recorder's URP/HDRP camera limits therefore don't apply.
   - **Unity Recorder is not installed** (not in `Packages/manifest.json`). The project has **no capture code**.
   - Never use `-nographics` (no graphics device). Treat `-batchmode` + Metal capture as untested; forum threads report black RenderTextures.
   - Run a windowed player or Editor with `Application.runInBackground = true`. Unity's own CLI docs warn that an unfocused Editor throttles and can freeze at frame 1.
6. **Reference video.**
   - Primary pipeline: PySceneDetect cut times → Gemini labels each shot (hook, on-screen text, camera move, role, ending type) → beats snapped to the cuts.
   - Nemotron Nano Omni becomes the cross-check, mainly for audio/VO, because it reports no temporal-grounding benchmark.
   - Lower PySceneDetect's `min_scene_len` below 0.6 s, since ad hooks cut faster than that.
7. **QA judge.** Ask atomic yes/no questions derived from the CreativeDoc, not 1-10 scores. Compare versions pairwise (A/B). Burn the timestamp and beat ID into each montage tile. Anything measurable is checked in code.
8. **Formats.** CBJ's preferred Android size is 720×900 (4:5) per SocialPeta, and AppLovin and Unity Ads cap video at 60 s. A 9:16 master plus a re-laid-out 4:5 export is a cheap, credible extra.
9. **Originality risk.** Other candidates' Rollic case repos are public: `RojenOnat/ColorBlockJam-Rollic-Case` and `bugrahnd/Rollic_Color_Block_Jam_Case`. Do not open them.
10. **Still open from day 1.** Unity is **not installed** on this Mac (no Hub editors, no `unity` CLI). That is the first blocker.

---

## 2. Component map

| Component | Adopt | Cite in write-up | Skip |
|---|---|---|---|
| Planner (intent → CreativeDoc / patch) | pydantic `model_json_schema()`, jsonpatch, segments keyed by id; copy the TimelineSpec shape from `@json-render/remotion` (stable clip ids, typed tracks) | VideoDirectorGPT 2309.15091, MovieAgent 2503.07314, VC-LLM 2504.05673, Aurora 2605.18748, LAVE 2402.10294 | A multi-agent planner (the MovieAgent role-split claim was refuted 1-2) |
| Solver / generator | Own Python BFS with bitboards (+ numba if slow), CAST window rejection, ideas from iro-nuke / brick-escape | ScriptDoctor 2506.06524, Todd 2302.05817, SokoBench 2601.20856, Baghal 2608.15958, Enigmata 2505.19914, Jarušek & Pelánek 2011 | PCGRL / RL generators (too heavy), python-astar / simpleai (slow) |
| Unity renderer | captureDeltaTime + RT + AsyncGPUReadback; file contract + `-executeMethod`; Recorder fallback | — | keijiro/FFmpegOut (2020, macOS bugs), ML-Agents, the Unity Python Scripting package (ends at Unity 6.1) |
| Compositor | Remotion (JSON props); ffmpeg filtergraphs for final assembly | — | Editly, FFCreator, Motion Canvas (stale or no headless mode), Kinocut as a dependency |
| Reference analysis | PySceneDetect + ffmpeg `scdet`; Gemini static mode, fps 4-10; Nemotron Omni cross-check | Decoding the Hook 2602.22299, VideoAds 2504.09282, AdsQA 2509.08621, AD-MIR 2602.07625, 2605.21954 (timestamps unreliable), CameraBench 2504.15376 | TransNetV2 (TF 2.1 pin), AutoShot (Baidu-only weights), Cosmos-Reason2 (404 on your key, end of life) |
| Asset generation | Nano Banana Pro (existing wrapper), rembg birefnet, Apple Vision foreground mask as a free fallback | — | BRIA RMBG-2.0 (non-commercial) |
| Controlled editing | JSON Patch + path whitelist + re-render + per-frame PSNR/SSIM + bbox proof | Generative Omnimatte 2411.16683, VACE 2503.07598, BeyondMasks 2608.20107, SVOR 2603.09283 (why not generative editing) | VACE / ProPainter / MiniMax-Remover on gameplay |
| QA judge | Gemini or Nemotron on a labelled montage, atomic questions, pairwise | ETVA 2503.16867, MLLM-as-a-Judge 2402.04788, IG-VLM 2403.18406, VideoScore2 2509.22799, Timeline-Bench 2609.35143 | VBench (a GPU benchmark, not a QA gate) |
| AI hook/outro | Kling MCP first+tail frame; fal Seedance `end_image_url` as provider 2 | VideoPhy-2 2503.06800 (physics failures in generated video) | AI video anywhere inside the gameplay segment |
| UI | Gradio (queue, drop zones, `gr.JSON`, `gr.HTML` diff view) | — | FastAPI + Next.js (too much for 8 days) |

---

## 3. Solver and generator design (what the evidence supports)

1. **State.** Holes are a static bitmask. Each block is `(type, x, y)`; occupancy is a Python-int bitmask.
   - Use a canonical hash that treats identical shape+colour blocks as interchangeable (the brick-escape trick), or incremental Zobrist hashing (jeantimex/klotski).
2. **Move.** One drag = moving a block to any position reachable by a 4-neighbour flood fill through free active cells.
   - A bent drag counts as one move. This models free 2D dragging on the grid, and the flood-fill path is what Unity replays.
3. **Exit check.** Reimplement `ExitService.CanBlockExit`.
   - Colour matches.
   - Every row (for Left/Right gates) or column (for Top/Bottom gates) the block occupies is inside the gate span.
   - The lane to the edge is clear: `lane_mask & occupancy == 0`.
   - Precompute lane masks per gate.
4. **Greedy exit closure.** After each drag, remove every block that can exit.
   - In base rules this never hurts, so there are no dead ends. Both iro-nuke and brick-escape do this.
   - Count exits separately for timer pacing.
5. **Search.**
   - BFS over drags gives the exact minimum `D`, capped at about 200k states.
   - Above the cap, fall back to weighted A* with h = blocks remaining.
   - Enumerate everything reachable, then run BFS backwards from the goal. That gives cost-to-go for every state, which steps 6-9 need.
   - Solver speed is the bottleneck iro-nuke hit (seconds per evaluation in JS). Use bitboards first and numba only if needed.
6. **Difficulty.**
   - Primary: `D`.
   - Secondary: simulated-human mean steps `M` from the Jarušek & Pelánek model. At each state, pick a successor with probability proportional to its score, adding a bonus B when it gets closer to the goal; B ≈ 25 fit humans on Rush Hour, Sokoban and a third transport puzzle. Run it 1,000 times.
   - Also report: narrowness (share of opening drags that reduce distance), branching factor, number of optimal first moves.
   - "Blocker depth" and "aha moves" are UNVERIFIED as predictors; use them only for exploration.
7. **Timer.** Start from brick-escape's `clamp(45, 300, 25 + 2.5·exits + 7·D)` seconds, then calibrate against `M × seconds per drag` from your own Unity replays.
8. **Generator.**
   - The LLM outputs only a spec: grid size, hole template (e.g. "narrow centre"), colours, block-size mix, 1-2 gates per colour, a target D window, a theme.
   - Code does the rest: dense pack → BFS → farthest state with all blocks present → reject or anneal if D is outside the window → prune gates no block can use → verify with a second solver and a Unity replay.
   - iro-nuke: too many gates per colour makes boards easy, and exactly one is too strict. Its yield for 25+ move boards was 0-3 per 4,000 attempts, so keep the D window modest for 30-60 s ads.
9. **Satisfying solve.** Among optimal solutions, prefer the one with the most exit cascades and steady pacing.
10. **Near-fail.**
    - Generate the play with the human walk at a low bonus (B ≈ 5-10).
    - Inject 1-3 Bockholt error types: Undo, Border Attraction (drag as far as possible), Equivalence Trap (a move that changes nothing), Early Unblock. Label each by how it changes cost-to-go, which is the useful idea in CAST 2607.25308.
    - Add pick-up-and-put-back hesitations.
    - Then play optimally, timed so the last exit lands at T−1 s.
11. **QA.** Replay-verify every script in the engine. Log D, M and the time left at the end in the render manifest.

---

## 4. Repos

**Prior art specific to Color Block Jam.** None of these has a license, so they are all-rights-reserved: read for ideas, copy no code.

| Repo | What to take |
|---|---|
| [nna774/iro-nuke](https://github.com/nna774/iro-nuke) (0★, 2026-09-29, JS + Python) | Negative results: backward scrambles are easy, gate count matters, solver speed is the bottleneck. Farthest-state generation |
| [HankHsu1969/brick-escape](https://github.com/HankHsu1969/brick-escape) (0★, 2026-10-08) | Flood-fill "placement" moves, canonical key, timer formula, autoplay through real drag events |
| [batuhanh/ColorBlockJamClone](https://github.com/batuhanh/ColorBlockJamClone) (0★, Unity 6 C#) | A recorder that feeds solver moves through the game's real move resolver with a synthetic pointer and saves 1080×1920 video |

**Licensed, reusable:**

| Repo | Stars / date / license | Use |
|---|---|---|
| [Wloner0809/CAST](https://github.com/Wloner0809/CAST) | 11★, 2026-07-30, Apache-2.0 | IDA* window-rejection generator pattern |
| [fogleman/rush](https://github.com/fogleman/rush) | 339★, master last touched 2024-06, MIT | `Energy = −(solver moves)` annealing + unsolve, a design reference (Rush Hour cars move on one axis only, so this is not drop-in) |
| [jeantimex/klotski](https://github.com/jeantimex/klotski) | 51★, 2026-07, MIT | Zobrist + mirror hash, bucket queue |
| [mpSchrader/gym-sokoban](https://github.com/mpSchrader/gym-sokoban) | 409★, 2023, MIT | Reverse-play reference only |
| [numba](https://github.com/numba/numba) | 11.2k★, 0.68.0 (2026-09-30), BSD-2 | Speed up BFS if needed |
| [Breakthrough/PySceneDetect](https://github.com/Breakthrough/PySceneDetect) | 5.2k★, v0.7.1, BSD-3 | Reference-video cuts. Best swept settings `adaptive_threshold=3.5, window_width=3`; lower `min_scene_len` for ads |
| [UVA-Computer-Vision-Lab/OmniShotCut](https://github.com/UVA-Computer-Vision-Lab/OmniShotCut) | 321★, 2026-09, MIT, arXiv 2604.24762 | Only if PySceneDetect misses transitions. Hard-codes CUDA, needs a patch for MPS |
| [slhck/ffmpeg-quality-metrics](https://github.com/slhck/ffmpeg-quality-metrics) | 561★, v3.12.4, MIT | Per-frame PSNR/SSIM/VMAF to JSON for the diff report |
| [remotion-dev/remotion](https://github.com/remotion-dev/remotion) | 62.6k★, v4.0.534 (2026-10-07), source-available | Compositor. Free for individuals, companies of up to 3 people, and evaluation; Rollic would need a Company License |
| [vercel-labs/json-render](https://github.com/vercel-labs/json-render/tree/main/packages/remotion) | 18.6k★, v0.21 (pre-1.0), Apache-2.0 | Copy the TimelineSpec schema shape. Its built-in prompt hardcodes 1920×1080 |
| [heygen-com/hyperframes](https://github.com/heygen-com/hyperframes) | 59.4k★, v0.8.143, Apache-2.0, Node 22+ | Remotion swap: HTML compositions, deterministic frame seeking, `--variables-file x.json`. Pin the version; it releases daily |
| [Zulko/moviepy](https://github.com/Zulko/moviepy) | 15.0k★, v2.2.1, MIT | Pure-Python fallback, slow |
| [danielgatis/rembg](https://github.com/danielgatis/rembg) | 25.0k★, v2.0.85, MIT | Background removal with `birefnet-general` |
| [gradio-app/gradio](https://github.com/gradio-app/gradio) | 43.7k★, 6.30.0, Apache-2.0 | UI |
| jsonpatch 1.33 / pydantic 2.14 / Huey 3.4 | BSD-3 / MIT / MIT | Patches, schema, SQLite job queue |

**Skip:**
- Editly (stale, native gl builds), FFCreator (abandoned), Motion Canvas (no first-party headless CLI found).
- Kinocut as a dependency (one maintainer, 7 months old, 203 tools would flood an agent's context). Its SHA-256 receipt idea is worth copying.
- keijiro/FFmpegOut (2020, open macOS issues; its own README points to Recorder).
- ML-Agents.
- TransNetV2 / AutoShot (setup cost).
- ProPainter (non-commercial).
- OpenMontage (AGPL).

---

## 5. Concept library (merged: your plan + CBJ ad evidence)

**What CBJ's real ads look like:**
- **Gameplay and audio** (Segwise 2025-04): 100% gameplay, unresolved endings, tactile SFX instead of music, a "no ads" claim in VO and text, light low-poly characters, small camera shakes.
- **Volume and format** (SocialPeta via Mobidictum 2025-08): about 6,300 creatives a month, 85.7% video, 4:5 preferred on Android, 93% English, and the game avoids intentional-fail or fake ads.
- **Hook and network mix** (Insightrackr 2026-04): the main hook is a live "Your Brain Age" counter. Networks: AppLovin 26%, Mintegral 23%, Facebook 10%.
- **Puzzle ads in general** (corrected 2026-10-10; these are two different reports measuring two different things):
  - **AppsFlyer 2025 (performance):** in Casual, which includes Puzzle, "Pure Success" endings get 33% higher installs per 1,000 impressions on ad networks. On social and search the result flips: "Pure Failure" gets 65% higher.
  - **AppsFlyer 2026 via GameDevReports (share of spend only, no performance data):** in "Puzzle & Lifestyle", 54.5% of ad-network spend goes to videos where the player loses.
  - CBJ's own brand stance (no intentional fails) overrides these genre averages.

Slots shared by all templates: `level`, `move_script`, `ending_state`, `skin/palette`, `sfx_pack`, `music_bed`, `vo_line`, `text_overlays`, `hand_cursor`, `camera_fx`, `end_card`, `format`, `duration`, `locale`.

| # | Template | Hook (0-3 s) | Body | Ending | Extra slots |
|---|---|---|---|---|---|
| 1 | Unfinished Board (Zeigarnik) | Dense board, first exit pops, "No ads. Just blocks." | 8-12 exits, quickening, micro-zoom on each | Freeze one move before the clear: "Can you finish it?" | — |
| 2 | Brain Age Meter | "Your Brain Age: 72" | Each exit lowers the number | Stalls at "25?", unsolved | `meter_label`, `meter_curve` |
| 3 | Near-Fail Timer | Timer 0:03 in red, 2 blocks left | "10 s earlier…" then the close call | A/B: win with confetti vs freeze at 0:01 | `timer_start`, `ending_state` |
| 4 | Satisfying Clear | Instant cascade of exits | Optimal solve with the most cascades, ASMR SFX | Board empties, logo | `sfx_pack` |
| 5 | No-Ads ASMR Loop | VO "Finally, a puzzle with no ads" | Close-up montage across 3 levels, each cut just before it is solved | Logo + "No Wi-Fi needed" | `claim_text`, `vo_voice`. Check the claim against the build |
| 6 | Low-Poly Companion (image-driven) | Character walks in and gasps | Reacts in a corner; camera shake on big exits | Points at the stuck block: "Your turn." | `character`, `emote_set`, `position` |
| 7 | Reference Adapt (video-driven) | Taken from the reference's beat sheet | Beats mapped onto CBJ gameplay events | Reference's ending type | `reference_beats` |
| 8 | Which First? (exploration) | Hand hovers over two blocks: "Which first?" | One real wrong move (an Equivalence Trap or Border Attraction from section 3), rewind, correct order | Last 2 moves left to the viewer | `bait_move`. Flag as off-brand risk: CBJ avoids staged fails |

Every template renders a real, solver-verified level in the engine. Default length is 30 s, extendable to 45-60 s, with a 3-4 s end card.

---

## 6. Papers to cite (grouped by write-up section)

All IDs were checked on arXiv or with the publisher by the research agents on 2026-10-09.

**Why the solver, not the LLM, owns the level**
- ScriptDoctor, arXiv 2506.06524 (IEEE CoG 2025). LLM-written PuzzleScript games: o3-mini 93% compile, 47% any level solvable, 20% all levels solvable.
- Todd et al., arXiv 2302.05817 (FDG 2023). Fine-tuned LLM Sokoban levels: 17% accuracy on target solution length (chance level), 3% when combined with a second target.
- SokoBench, arXiv 2601.20856. Reasoning models degrade past about 25 moves.
- Baghal, arXiv 2608.15958. A solver-free diffusion generator reaches 77.4% solvable levels.
- Practical PCG through LLMs, arXiv 2305.18243 (CoG 2023): 37% playable and novel.
- Word2World, arXiv 2405.06686: 9 of 10 playable only with A* verifier feedback.
- Enigmata, arXiv 2505.19914 (NeurIPS 2025 spotlight). The generator-plus-verifier pattern with controllable difficulty.
- Siper, Khalifa & Togelius, arXiv 2608.17947 (CoG 2026). The LLM evolves generator programs, not levels; the closest to your split.
- Surveys: Gallotta et al. 2402.18659 (IEEE ToG), Maleki & Zhao 2410.15644.
- No paper uses exactly "LLM picks constraints, solver owns solvability" for sliding puzzles. Say so, and argue from the negative results above.

**Difficulty and human play**
- Jarušek & Pelánek, "What Determines Difficulty of Transport Puzzles?" (FLAIRS 2011). Shortest path vs human solve time: Rush Hour Spearman 0.90, Sokoban 0.41. Also the human-play simulation model.
- Bockholt et al. (CogSci 2018). 11 human error types in Rush Hour.
- Taylor & Parberry, "Procedural Generation of Sokoban Levels" (2011). Farthest state; count "box lines", not raw moves.
- Kartal, Sohre & Guy (AIIDE 2016), MCTS Sokoban generation; Bento et al. arXiv 1907.02548; Kristensen et al. arXiv 2306.14626 (Lily's Garden completion-rate prediction); Roohi et al. arXiv 2008.12937.
- CAST, arXiv 2607.25308. Solver cost-to-go as per-turn credit (note: it is not a reverse-play generator, as one first-pass note claimed).

**Why a near-fail ending works**
- Larche, Musielak & Dixon 2017, *J Gambling Studies* 33(2). Candy Crush near-misses (losing by 1-2 moves) gave the strongest urge to keep playing.
- Clark et al. 2009, *Neuron* 61(3). Near-misses recruit the same brain circuitry as wins.
- Moon et al. 2026, *Psychology & Marketing* 43(7), doi 10.1002/mar.70130. In fail ads, schadenfreude drives download intent, and "reasonably challenging" scenarios beat extreme ones.
- UK ASA ruling against Playrix (30 Sep 2020) and ASA guidance (2024-08-22). Ads must reflect the core gameplay. A constraint the architecture satisfies by design.

**LLM plans, something else renders**
- VideoDirectorGPT 2309.15091 (COLM 2024), MovieAgent 2503.07314, VC-LLM 2504.05673 (ByteDance; ad video from clips as (clip, script, subtitle) tuples), Aurora 2605.18748, LAVE 2402.10294 (IUI 2024), Text-to-Edit 2501.05884.
- AgenticGen 2609.09187 (TikTok). Ad video generation trained on online feedback, +2.72% CTR. Cite in the roadmap for the performance feedback loop.
- None of these does localized patch edits. Your controllability proof rests on your own diffs.

**Reference-video understanding**
- Decoding the Hook 2602.22299. The first 3 s as the hook; MLLM hook features correlate with conversion.
- VideoAds 2504.09282 (ICCV 2025). Ads are fast: humans 94% vs the best model 73%; call for high-FPS sampling.
- AdsQA 2509.08621 (ICCV 2025); AD-MIR 2602.07625 (evidence-checked ad insights); Tencent AVS 2212.04700 (ad shot taxonomy).
- Editing-style transfer 2105.06988. The closest prior work to "adapt this reference".
- VLM timestamp weakness: 2605.21954 ("timestamp predictions remain unreliable"), TimeLens 2512.14698, CameraBench 2504.15376 (camera-move confusion), CamChoreo 2608.10932.
- Shot detection: OmniShotCut 2604.24762, TransNetV2 2008.04838, AutoShot 2304.06116 (its dataset includes game ads).

**QA judge**
- ETVA 2503.16867 (ICCV 2025). Atomic yes/no questions reach Spearman 58.5 vs 31.0 for earlier metrics.
- MLLM-as-a-Judge 2402.04788 (ICML 2024). Pairwise comparison is close to humans; absolute scores diverge.
- IG-VLM 2403.18406. A frame grid as input works.
- VideoScore2 2509.22799. Even a purpose-built judge is about 44-50% accurate.
- Judge Anything 2503.17489.
- Timeline-Bench 2609.35143. The best editing agent solves 26.8% of tasks; most failures are quality, not mechanics ("agents check renders for defects, not craft").

**Why not generative editing on gameplay**
- Methods: Omnimatte 2105.06993, Layered Neural Atlases 2109.11418, Generative Omnimatte 2411.16683, VACE 2503.07598 (about 81 frames per clip; ComfyUI docs report about 40 min for 81 frames at 720p on an RTX 4090), DiffuEraser 2501.10018, MiniMax-Remover 2505.24873, VideoPainter 2503.05639.
- Failures: BeyondMasks 2608.20107 (shadows and reflections left behind), SVOR 2603.09283 (temporal instability).

**Refuted, keep out of the write-up**
- "Layout2Vid shows the renderer obeys the plan" (0-3).
- "Borrow MovieAgent's multi-agent role split" (1-2).

---

## 7. MCP servers

| Server | Verdict | Notes |
|---|---|---|
| [CoplayDev/unity-mcp](https://github.com/CoplayDev/unity-mcp) | **Adopt (dev)** | 14.8k★, MIT, v10.3.0 (2026-10-04), about 49 tools, Unity 2021.3-6.x, Python 3.10+ via uv. 86 open issues: avoid spaces in the project path, and keep only one Editor open |
| [IvanMurzak/Unity-MCP](https://github.com/IvanMurzak/Unity-MCP) | Alternative | 4.4k★, Apache-2.0, pre-1.0. Roslyn C# execution + Game View screenshots, but its screenshot tools ship disabled |
| Unity official CLI + `unity` plugin ([unity-agent-plugin](https://github.com/Unity-Technologies/unity-agent-plugin)) | Optional | Beta, needs the `com.unity.pipeline` package. The plugin is 34 mostly-markdown skills. Whether its `unity mcp` needs the AI subscription is UNVERIFIED; the first pass found the AI Assistant MCP needs a trial or $10/month plus Unity Cloud |
| Kling (connected) | **Adopt** | First+tail frame on v3.0 / v2.6 / v2.5, not on v3.0 turbo. The connector reports v1.3.3 and asks for a reconnect to get new tools. v3.0 image-to-video has no aspect_ratio argument, so feed it 9:16 frames |
| [fal.ai MCP](https://fal.ai/docs/documentation/setting-up/mcp) | Optional provider 2 | `claude mcp add --transport http --scope user fal https://mcp.fal.ai/mcp-relay`. Seedance v1-pro/1.5-pro/2.0 have `end_image_url` |
| Higgsfield hosted MCP (`mcp.higgsfield.ai/mcp`) | Fallback | Live, needs auth. Your past Higgsfield credentials kept dying |
| Comfy Cloud MCP | Skip | Public beta since 2026-06-30; nothing in this pipeline needs ComfyUI |
| ffmpeg MCPs, Kinocut | Skip | Bash + your `ffmpeg` skill + ffmpeg 8.1.1 already cover this |
| Blender MCP (now `ahujasid/mcp-for-blender`) | Skip | Only if you need a 3D mascot; it runs arbitrary Python |
| ElevenLabs | Use the SDK, not the MCP | The local MCP is archived. `/v1/sound-generation` makes SFX up to 30 s |
| Runway, Replicate, Luma | Skip | Archived, replaced by hosted servers, or stale |

Not available until authorized via claude.ai connector settings or `/mcp`: apify, figma, shaders.

---

## 8. Claude Code skills and plugins

- **Already installed and relevant:** `remotion-best-practices`, `remotion-create`, `remotion-render`, `remotion-captions`, `ffmpeg`, `motion-design`, `viral-hook-creator`, `find-skills`, `frontend-design`, `anthropic-skills:skill-creator`.
- **Add:**
  - `unity@claude-plugins-official`. Unity-authored and low risk; its `unity-cli` skill documents the focus-throttling and `runInBackground` gotchas.
  - `pyright-lsp@claude-plugins-official`.
  - `hyperframes@claude-plugins-official`, only if you switch compositors.
- **Write your own (best value):** two or three project skills built with `skill-creator`:
  - `creativedoc-edit`: schema, path whitelist, patch rules;
  - `cbj-render`: build → run → frames → manifest;
  - `cbj-level`: generator spec → solver → verify.
  These double as evidence for the "extensibility" and "engineering quality" criteria.
- **Skip:** Besty0728/Unity-Skills (another in-editor REST server), Donchitos/Claude-Code-Game-Studios, awesome-gamedev packs (generic process), OpenMontage (AGPL).
- **Vet before enabling anything third-party.** Snyk's Feb 2026 audit of 3,984 marketplace skills found critical issues in 13.4% and 76 malicious payloads. Run `uvx mcp-scan@latest --skills`, and check a SKILL.md for external downloads and base64 or Unicode-encoded shell commands.
- **None of Anthropic's own 19 skills** covers Unity, video or level design.

---

## 9. Industry facts for the "production roadmap" section

- **How Rollic works:** ideates "more than a thousand games a month" and tests hundreds of prototypes monthly (PocketGamer 2025-07-16). CBJ's success is credited to "consistent creative rigor" (Mobidictum 2025-06-16).
- **Not public:** Rollic's in-house creative tooling and team. Don't claim to know them.
- **Nearby Istanbul job posts describe your tool.**
  - Dream Games, AI Engineer, Performance Marketing: agentic creative workflows, playables from code generation plus multimodal assets, evaluation pipelines with human-in-the-loop review.
  - Bigger Games: "multiple creative routes per brief" plus "smart iterations" from performance signals.
- **Other studios:**
  - **Voodoo:** about 30 of 85 growth staff on creatives; video first, playables only if the video works; job posts list Seedance, Kling, Veo and Runway, with After Effects required and Unity a plus.
  - **AppLovin** (2026-03): a multi-agent pipeline (brand context → concepts → image/video models → quality validation); automated 60 s video is in limited tests.
  - **Reforged Labs** (an AI ad startup) shut down in 2026-08 because studios now build in-house. This supports building the tool inside Rollic.
- **Volume:** top spenders made 3,977 variants per app in Q1 2026, about 300 a week (AppsFlyer 2026-10-07). The top 2% of game videos take 60.7% of spend, so cloning a winner and changing one slot is the economical workflow. That is exactly the controllability requirement.
- **Diversity:** Meta Andromeda rewards distinct concepts, and copycats fade in about 7 days (AppAgent). The roadmap needs a quota of new concepts next to variant cloning.
- **Network specs:**
  - AppLovin: 9:16, at most 60 s, encourages 30 s or more.
  - Unity Ads: at most 60 s, end card required.
  - TikTok: 21-34 s recommended (secondary source).
  - Meta: 4:5 feed + 9:16 with a unified safe zone (secondary source).
- **AI labelling:** Meta "AI info" label; TikTok realistic-AI label from 2026-07-21 (secondary source); EU AI Act Art. 50 from 2026-08-02. Your generated mascots/hooks need an `ai_generated` flag in the asset registry.

**Roadmap bullets this supports:**
1. An asset and rights registry (licence, territory, expiry, AI flag) that blocks expired assets.
2. A representativeness guard: engine-only gameplay, solver-verified levels, claims validated against the build.
3. Spec-native tagging: slot values become performance tags joined to IPM/CTR/D7 ROAS, with no vision tagger needed.
4. Winner cloning plus a diversity quota.
5. A format matrix: 9:16 / 4:5 / 1:1 / 16:9 × 15 / 30 / 60 s per network preset.
6. An automated checks → VLM judge → human approval queue.
7. A playable branch from the same CreativeDoc (Playworks/Luna/HTML5; CBJ's mix is 13% playable).
8. Localisation as slots.
9. Throughput KPIs: cost per approved variant, approval rate.
10. Render farm: windowed Linux or macOS players.

---

## 10. Install list (priority order; nothing has been installed)

1. **Unity 6000.3.5f1 via Unity Hub** (still the day-1 blocker). Then add `com.unity.recorder` only if you take the Recorder fallback.
2. `uv add pydantic jsonpatch gradio huey scenedetect scikit-image numpy ffmpeg-quality-metrics`
3. `uv add "rembg[cpu,cli]"`; on first run, `rembg i -m birefnet-general in.png out.png`
4. **CoplayDev unity-mcp**, per its README (uv + the Unity package), with the project path free of spaces.
5. `claude plugin install unity@claude-plugins-official` and `pyright-lsp@claude-plugins-official`
6. Reconnect the Kling MCP to pick up v1.3.x tools.
7. Optional: the fal MCP (Seedance end-frame), `uv add elevenlabs` (VO/SFX), `numba` if the BFS is slow.
8. Before enabling any third-party skill or MCP: `uvx mcp-scan@latest --skills`

---

## 11. Gaps and unverified items

- How Rollic's creative team works and which tools it uses: not public.
- Whether `-batchmode` + Metal can capture frames on macOS: untested. Assume a windowed process.
- How the hosted Nemotron Omni samples frames, and whether Kling v3.0 output follows the input aspect: unverified.
- Platform crackdowns on fake ads in 2025-26, and the "9.2 vs 15.4 day" fatigue figures: secondary sources only.
- Whether the official Unity `unity mcp` needs the paid AI tier: unverified.
- Remotion's Company License cost for Rollic: not checked.
