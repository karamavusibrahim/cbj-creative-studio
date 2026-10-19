"""Guided creative generation: a prompt plus media in, a new creative out (the case's core
requirements 3 and 4, case p.6), with its own evaluate / feed back / revise loop. See
workflows/__init__.py.

The input is always a prompt AND media: a reference video with a prompt, or a reference image with
a prompt. The prompt drives the reading (what the media is read for) and every value it states
itself (length, ending, captions, look), which always wins over the reference; the media is what
gets read. A video attached with a prompt that says nothing about it is read for its concept.

plan: the request first, then the media. Each video goes through reference.read_video: the reading
plan (the planner's own text model decides what to look for, from the request and the file's format
facts; the word table is the fallback and the check), the format step (the whole clip, any format,
one small H.264 copy), the whole-clip reading by NVIDIA's multimodal model with the prompt composed
from the plan, the checks in code with one re-ask, and the parts snapped to measured cuts only when
the reading needs it. Each reference image is measured and described (reference.analyse). Then the
planner plans with those readings and code applies what each gives (imageref: the image's role;
videoref: only what the video's focus allows). make and revise_once run the shared engine (studio,
review, audit) exactly as create.py does; the evaluation adds the reference rows to the text rows
(audit.reference_rows), and their misses are fed back like the others.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from .. import brief as B
from .. import llm, planner, reference, review, route, studio, videocells

MAX_REVISIONS = 2  # evaluate, feed back, make again: at most two rounds after the first version
WORKFLOW = "guided"


def applies(prompt: str, uploads: list[str]) -> bool:
    """Whether a new creative is guided: a video is attached (a video is always a reference), or an
    image is attached and the request's words make it a reference ("inspired by this", "a level like
    this board": reference.is_reference_prompt). Both the uploads and the words decide."""
    vids, ups = studio.videos(), studio.uploads()
    if any(n in vids for n in uploads):
        return True
    images = [n for n in uploads if n in ups and not B.is_audio(n)]
    return bool(images) and reference.is_reference_prompt(prompt, edit=False)


def media(prompt: str, uploads: list[str]) -> tuple[dict, dict, dict]:
    """The attached files: (every upload offered to the planner, the videos to read, the images to read)."""
    all_ups, vids = studio.uploads(), studio.videos()
    ups = {n: all_ups[n] for n in uploads if n in all_ups}
    videos = {n: vids[n] for n in uploads if n in vids}
    images = {n: p for n, p in ups.items() if not B.is_audio(n)} if reference.is_reference_prompt(prompt, edit=False) else {}
    return ups, videos, images


def plan(log: studio.Log, prompt: str, uploads: list[str]) -> dict:
    """The brief of a guided creative: the media read for the request, then planned (see the module note)."""
    if not prompt.strip():
        raise ValueError("write a prompt first: it says what to take from the attached media")
    ups, videos, images = media(prompt, uploads)
    log.begin("plan", "a guided creative: reading the request, then the attached media...")
    rt = route.decide(prompt, manifest=None, uploads=sorted(ups), videos=sorted(videos))
    log("route: " + route.summary(rt))
    client = llm.planner_client()  # one client: the reading plan and the brief come from the same planner model
    from .image_guided import english_prompt  # the parsers are English (2026-10-19): a Turkish request is translated once
    original, prompt = prompt, english_prompt(prompt, client, log)
    read: dict[str, dict] = {}
    for name, path in sorted(videos.items()):
        log(f"reading the reference video {name} for the request...")
        read[name] = reference.read_video(path, prompt, planner=client, log=log)
        log("  " + reference.summary(read[name]))
        if videocells.copy_asked(prompt) and not read[name].get("error"):
            # the video's own board (2026-10-19): its first frame of play read cell by cell, as a picture (videocells)
            read[name]["cells_copy"] = videocells.read_board(path, read[name], log=log)
    for name, path in sorted(images.items()):
        read[name] = reference.analyse(path, log=log)
        log("  " + reference.summary(read[name]))
    brief = planner.plan(prompt, client=client, uploads=ups, sprites=studio.sprite_names(), current=None,
                         available=studio.uploads(), inventory=None, references={**videos, **images},
                         analyser=lambda p: read[Path(p).name], log=None, history=None, parts=None, route=None)
    brief["planner"]["route"] = rt
    brief["planner"]["workflow"] = WORKFLOW
    if prompt != original:
        brief["planner"]["prompt_original"], brief["planner"]["prompt_english"] = original, prompt
    from .. import videoref
    for note in videoref.fit_captions(brief, prompt, chain=True):  # no caption may claim what the ending does not show (round 2)
        log(f"captions: {note}")
    try:  # "the clock runs out with two blocks left" (V5, 2026-10-19): the engine's time-out ends with one; said in the plan
        from ..imageaudit import blocks_left_asked
        n_left = blocks_left_asked(prompt)
        if n_left not in (None, 1) and brief["gameplay"].get("ending") == "time_out":
            B.adjust(brief, "gameplay", f"a time-out ends with exactly one block, one cell from its gate (the play engine's race); "
                                        f"the {n_left} blocks left asked are not played.")
            log(f"plan: a time-out ends with one block left, not {n_left}: said in the plan")
    except Exception:
        pass
    ref = brief.get("reference")
    if ref:
        log(f"reference to creative: {ref['file']} read for {reference.focus_text(ref.get('focus'))} ({ref.get('level')}); "
            f"adapted: {', '.join(ref.get('adapted') or []) or 'nothing'}; not copied: {', '.join(ref.get('not_copied') or [])}")
    log(f"planned by {brief['planner']['model']} in {brief['planner']['seconds']} s")
    return brief


def video_ref(brief: dict) -> bool:
    """Whether a version was made from a reference video (the video-reference workflow). image_guided.py calls some of
    the functions below too; the round-3 rules (the case's range as no length, the solve and breathe words, the pinned
    mistakes) apply only when this holds, so the image workflow keeps its behaviour (the owner, 2026-10-17)."""
    return any(isinstance(r, dict) and r.get("kind") == "video" for r in (brief.get("planner") or {}).get("references") or [])


def keep_asked_guided(prompt: str, before: dict, after: dict) -> list[str]:
    """create.keep_asked for the guided workflow: the asked length and the asked ending stay through a revision, the length
    read with the case's 30-60 s range as no length (audit.asked(..., case_range=True); round 3, case 18: create's reading
    restored "30–60 second" as 60 s in the revision). create.keep_asked itself is unchanged for the text workflow."""
    from .. import audit
    a = audit.asked(prompt, case_range=True)
    notes = []
    if a.get("length_s") and abs(after["pacing"]["length_s"] - a["length_s"]) > 0.5:
        notes.append(f"the request asks for {a['length_s']:g} s; the revised plan said {after['pacing']['length_s']:g} s, restored")
        after["pacing"]["length_s"] = float(a["length_s"])
        if "pacing.length" in after.get("changed", []):
            after["changed"].remove("pacing.length")
    if a.get("ending") and after["gameplay"]["ending"] != a["ending"] and before["gameplay"]["ending"] == a["ending"]:
        notes.append(f"the request asks for a {a['ending'].replace('_', '-')}; the revised plan said {after['gameplay']['ending'].replace('_', '-')}, restored")
        after["gameplay"]["ending"] = a["ending"]
    return notes


def _carried(brief: dict, checked: dict) -> dict:
    """What B.check does not own and a version must keep: the planner's notes (the readings), the
    declared groups, the files still needed, and the reference's provenance."""
    for k in ("planner", "changed", "needs", "reference"):
        if k in brief:
            checked[k] = brief[k]
    checked.setdefault("planner", {})
    checked.setdefault("changed", [])
    checked.setdefault("needs", [])
    return checked


def make(log: studio.Log, prompt: str, brief: dict, draft: bool = False, review_on: bool = False,
         without_files: bool = False, revise: bool = True) -> dict:
    """Make the creative, review it as a viewer, then run the loop until nothing measurable is
    missed (the text rows and the reference rows), nothing can be changed, or MAX_REVISIONS rounds
    are done. Every version is kept."""
    from .image_guided import is_english
    if (brief.get("planner") or {}).get("prompt_english") and not is_english(prompt):
        prompt = brief["planner"]["prompt_english"]  # the rows, the review and the loop read the translation the plan used
    checked = _carried(brief, B.check(brief, studio.uploads(), studio.sprite_names()))
    v = studio.make(prompt, checked, None, log, draft=draft, allow_missing=without_files, workflow=WORKFLOW)
    if review_on and not draft:
        v = _reviewed(log, prompt, v)
    if revise and not draft:
        from .. import audit
        from .image_guided import repeated_miss
        made = [v]
        for _ in range(MAX_REVISIONS):
            v = revise_once(log, prompt, v, review_on)
            if (v.get("revision") or {}).get("status") != "made":
                save_record(v)  # the loop's verdict on this version (unchanged, failed, nothing missed) is kept with it
                break
            made.append(v)
            if not audit.misses(v.get("checks") or []):
                break
            same = repeated_miss(made[-2], made[-1])
            if same:  # the same row missed twice with the same measure: the board's limit, said; no more revisions (common, 2026-10-19)
                log(f"revision: {same['check']} missed twice with the same measure ({str(same.get('detail'))[:160]}): that is "
                    f"the limit of this board, so no more revisions")
                for x in made[-2:]:
                    x["limit_note"] = f"{same['check']}: {same.get('detail')}"
                break
        v = best_version(log, made)
    return v


VERDICT_RANK = {"ship": 0, "fix": 1}


def best_version(log: studio.Log, made: list[dict]) -> dict:
    """The final version is the best one, not the last (round 2 rerun, case 03: v1 met 20 of 20 and the viewer said
    ship; the revisions it started missed the part lengths and the last became final): the fewest measured misses
    first, then the viewer's verdict (ship before fix), then the later version. Every version is kept."""
    from .. import audit

    def key(v):
        verdict = ((v.get("review") or {}).get("overall") or "fix") if not (v.get("review") or {}).get("error") else "fix"
        return (len(audit.misses(v.get("checks") or [])), VERDICT_RANK.get(verdict, 1), -int(v.get("n") or 0))
    best = min(made, key=key)
    if len(made) > 1:
        why = (f"{len(audit.misses(best.get('checks') or []))} measured miss(es), the viewer's "
               f"{(best.get('review') or {}).get('overall') or 'no'} verdict")
        best["final"] = {"version": best.get("n"), "of": [x.get("n") for x in made], "why": why}
        if best is not made[-1]:
            log(f"final: v{best.get('n')} is kept as the final version ({why}); "
                f"v{made[-1].get('n')} has {len(audit.misses(made[-1].get('checks') or []))} miss(es) and the viewer's "
                f"{(made[-1].get('review') or {}).get('overall') or 'no'} verdict")
        save_record(best)
    return best


def _reviewed(log: studio.Log, prompt: str, v: dict) -> dict:
    log.begin("review", "the viewer's review...")
    try:
        v["review"] = review.review(v, prompt, studio.STUDIO, log=log)
    except Exception as e:  # a review that fails never loses the version
        log(f"review failed: {e}")
        v["review"] = {"error": str(e)[:300]}
    save_record(v)
    return v


def save_record(v: dict) -> None:
    """Write the version record again after the review or the loop's verdict (2026-10-17: studio.make writes version.json
    before the review, and the guided workflow never wrote it again, so the owner's v1 had review.json beside it but no
    review, no review error and no revision status in version.json; image_guided.py already does this)."""
    if not v.get("id") or v.get("n") is None:
        return
    vdir = studio.STUDIO / v["id"] / f"v{v['n']}"
    if not vdir.is_dir():
        return
    rec = v
    try:
        disk = json.loads((vdir / "version.json").read_text())
    except (OSError, ValueError):
        disk = {}
    made = (disk.get("revision") or {}).get("status") == "made"
    if made and (v.get("revision") or {}).get("status") != "made":
        # a revised version keeps how it was made; the loop's later verdict on it goes beside that
        rec = {**v, "revision": disk["revision"], "loop": v.get("revision")}
    (vdir / "version.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False))


def feedback(prompt: str, v: dict) -> str | None:
    """What the made version missed of the request and of the reference, as a request for a revised
    take: the measured misses (the text rows and the reference rows) first, then the viewer's first fix. With nothing
    measured missed, the viewer's "not as asked" starts a revision only about what the request asks or the reading set
    (round 2 rerun, case 03: "difficulty or pacing" on "create a similar game in Color Block Jam", whose pacing the
    request never asks, turned a 20-of-20 version the viewer would ship into two worse ones)."""
    from .. import audit
    checks, rv = v.get("checks") or [], v.get("review")
    if rv and not rv.get("error") and not audit.misses(checks):
        asked = asked_controls(prompt, v.get("brief") or {})
        bad = [m for m in rv.get("match") or [] if m.get("verdict") in ("no", "partial")]
        unasked = [m for m in bad if control_of(m.get("control")) not in asked]
        if unasked:
            v["review_not_asked"] = [f"{m.get('control')}: {m.get('seen')}" for m in unasked]
            rv = {**rv, "match": [m for m in rv.get("match") or [] if m not in unasked]}
    return audit.feedback(prompt, checks, rv)


# The viewer's controls (review.CONTROL_WORDS, answered in its own words) and the brief's controls they are about.
REVIEW_CONTROLS = (("unchanged", re.compile(r"unchanged|remain", re.I)), ("assets", re.compile(r"asset|picture|music|image", re.I)),
                   ("sequence", re.compile(r"sequence|order of|events|flow", re.I)),
                   ("difficulty_pacing", re.compile(r"difficult|pacing|\bpace|tempo|speed", re.I)),
                   ("gameplay", re.compile(r"gameplay|behaviou?r|ending|mistake", re.I)),
                   ("level", re.compile(r"level|board|structure", re.I)), ("visuals", re.compile(r"visual|look|colou?r", re.I)),
                   ("concept", re.compile(r"concept|hook|caption", re.I)))
FOCUS_CONTROLS = {"concept": "concept", "hook": "concept", "captions": "concept", "ending": "gameplay", "structure": "sequence",
                  "board": "level", "board_colours": "level", "look": "visuals", "screen": "visuals"}


def control_of(name: str | None) -> str | None:
    return next((c for c, rx in REVIEW_CONTROLS if rx.search(str(name or ""))), None)


def asked_controls(prompt: str, brief: dict) -> set[str]:
    """The brief's controls the request asks about (its stated values, its quoted captions, the aspects a targeted
    reading plan names, the pacing only when audit.pacing_asked) or the reading set (brief.reference.set). The play
    levers' tempo and moves made to fill the ad (no pacing taken) belong to the flow, not to the pacing; the length too."""
    from .. import audit
    from .. import videoref as V
    a = next((r for r in (brief.get("planner") or {}).get("references") or [] if isinstance(r, dict) and r.get("kind") == "video"), None)
    constraints = ((a or {}).get("plan") or {}).get("constraints") or []
    out: set[str] = set()
    for name in V.stated(prompt, constraints, video=video_ref(brief)):
        for sec, key in STATED_FIELDS.get(name, ([], None))[0]:
            g = next((g for g, (_, paths) in B.GROUPS.items() if (sec, key) in [tuple(x) for x in paths]), None)
            if g:
                out.add(B.GROUPS[g][0])
    if audit.asked(prompt).get("captions"):
        out.add("concept")
    prov = brief.get("reference") or {}
    paced = (prov.get("play") or {}).get("mode") == "pace"
    flow = {"pacing.length", "pacing.tempo", "level.moves", "gameplay.hesitations"} if not paced else {"pacing.length"}
    for g in prov.get("set") or []:
        out.add("sequence" if g in flow else B.GROUPS.get(g, ("",))[0])
    if a is not None:
        plan = a.get("plan") or {}
        if plan.get("level") == "targeted":
            out |= {FOCUS_CONTROLS[x] for x in a.get("focus") or [] if x in FOCUS_CONTROLS}
        if audit.pacing_asked(prompt, a):
            out.add("difficulty_pacing")
    out.discard("")
    return out


# What the reference set in the brief (videoref records the groups in brief.reference.set), and the rows whose miss
# may change it. Round 1 (2026-10-17): trailer 2's open board from the reference was re-planned as holes and packed
# after the viewer's "keep the board full longer", undoing the reference's board.
# The values are the base version's brief, as videoref adapted them (after the wall choice, the growth, the fill, the
# colour mapping), never the raw reading. A miss of "Reference: the board" does not unpin the board: that row measures
# the made level against those adapted values, so its miss is the generator's, fixed by a new take (round 2, case 04:
# the row compared the raw "holes 4x7" read, failed, and the revisions re-planned the board from the reading).
PINNED = {
    "pacing.length": (),  # the reference's length: never chased by a part-length miss (round 1, third run: 30 s to 45 s)
    "level.source": (),
    "level.shape": ("Asked: board shape", "Asked: walls"),
    "level.size": (),
    "level.blocks": ("Asked: block count", "Asked: blocks a viewer can count"),
    "level.colours": ("Asked: colours", "Asked: named colours", "Asked: blocks per colour"),
    "level.pieces": (),
    "level.style": (),
    "gameplay.ending": ("Reference: the ending", "Asked: ending", "Asked: the replay"),
    "level.label": ("Asked: HUD level number",),
    # round 2, case 05 (2026-10-17): the pure-play and stretch rules' fields (v1 passed at 78% play; the revision turned
    # the calm tempo to normal and the play fell to 51%), and the pacing levers' fields: never the planner's to change;
    # a miss of the pacing row re-runs the same levers after the pins (play_again)
    "pacing.tempo": (),
    "sequence.timing": (),
    "gameplay.blocks_left": ("Asked: the replay",),  # round 4, case 30: a cut kept against an asked replay
    "level.moves": (),
    "gameplay.hesitations": (),
    # case 09: the screen as asked (the revision answered "the 2 seconds cannot be seen" by turning the clock back on);
    # the hidden clock's seconds stay on the captions
    "visuals.hud": (),
    "visuals.zoom": (),
    "visuals.cursor": (),
    "gameplay.events": (),  # the guided stuck step (two colours, one piece): the request named none (rerun 3, case 14)
    # round 3, case 16: trailer 2 has no wrong move and v1 had none; the revisions added one, then two, to fill a 60 s ad
    "gameplay.mistakes": ("Asked: mistakes", "Reference: the ending"),
    "concept.hurry": ("Reference: the captions",),
    "concept.result": ("Reference: the captions",),
}
PINNED_WORDS = {"gameplay.ending": "ending", "level.label": "HUD level", "pacing.length": "length",
                "pacing.tempo": "pacing", "level.moves": "pacing", "gameplay.hesitations": "pacing",
                "sequence.timing": "timing", "gameplay.blocks_left": "cut", "visuals.hud": "screen", "visuals.zoom": "screen",
                "visuals.cursor": "screen", "concept.hurry": "captions", "concept.result": "captions",
                "gameplay.events": "stuck moment", "gameplay.mistakes": "mistakes"}

# What the request states (videoref.stated() and the asked facts audit.asked reads), the brief fields that hold it, and
# the asked row whose miss at the plan lets a revision change it (round 2, case 14, 2026-10-17: "show the player stuck
# once" was planned with one mistake, and the revision followed the viewer's "the stuck moment is short" to two).
STATED_FIELDS = {
    "length": ([("pacing", "length_s")], "Asked: length"),
    "ending": ([("gameplay", "ending")], "Asked: ending"),
    "mistakes": ([("gameplay", "mistakes"), ("gameplay", "mistake_kinds")], "Asked: mistakes"),
    "difficulty": ([("level", "difficulty")], "Asked: difficulty"),
    "finish": ([("gameplay", "finish")], "Asked: satisfying finish"),
    "tempo": ([("pacing", "tempo")], None),
    "curve": ([("pacing", "curve")], None),
    "moves": ([("level", "moves")], "Asked: block count"),
    "replay": ([("sequence", "replay")], "Asked: the replay"),
    "end_card": ([("sequence", "end_card")], "Asked: the end card"),
    "result_screen": ([("sequence", "result_screen")], "Asked: the result screen"),
    "result_first": ([("sequence", "style")], "Asked: the win first"),
    "hold": ([("sequence", "hold_s")], None),
    "intro": ([("sequence", "intro_s")], None),
    "background": ([("visuals", "background")], "Asked: background"),
    "caption_colours": ([("visuals", "caption_fill"), ("visuals", "caption_outline")], None),
    "shape": ([("level", "shape")], "Asked: board shape"),
    "size": ([("level", "width"), ("level", "height")], None),
    "blocks": ([("level", "blocks")], "Asked: block count"),
    "colours": ([("level", "colours")], "Asked: colours"),
    "pieces": ([("level", "pieces")], None),
    "style": ([("level", "style")], None),
    "level": ([("level", "source"), ("level", "shipped"), ("level", "label")], "Asked: HUD level number"),
    "blocks_left": ([("gameplay", "blocks_left")], None),
    "clock_left_s": ([("gameplay", "clock_left_s")], "Asked: seconds left"),
    "timer_s": ([("gameplay", "timer_s")], "Asked: the clock"),
    "hesitations": ([("gameplay", "hesitations")], "Asked: hesitations"),
    "hud": ([("visuals", "hud_timer"), ("visuals", "hud_level")], None),
    "zoom": ([("visuals", "camera_zoom")], None),
    "cursor": ([("visuals", "cursor")], "Asked: cursor"),
}


def keep_stated(prompt: str, before: dict, after: dict, misses: list[dict], video: bool | None = None) -> list[str]:
    """A revision restores every value the request states (videoref.stated() and the asked clock, seconds left and
    hesitations) to the base version's, as create's keep_asked does for the length and the ending, unless that fact's own
    asked row failed at the plan (the base planned it wrong). Returns the notes of what was restored."""
    from .. import audit
    from .. import videoref as V
    constraints = []
    for r in ((before.get("planner") or {}).get("references") or []):
        if isinstance(r, dict) and r.get("kind") == "video":
            constraints = (r.get("plan") or {}).get("constraints") or []
            break
    video = video_ref(before) if video is None else video  # the video workflow's words (image_guided calls this too)
    names = set(V.stated(prompt, constraints, video=video))
    asked_ = audit.asked(prompt)
    names |= {k for k in ("clock_left_s", "timer_s", "hesitations") if asked_.get(k) is not None}
    names |= {k for k, rx in (("hud", V.HUD_STATED), ("zoom", V.ZOOM_STATED), ("cursor", V.CURSOR_STATED)) if rx.search(prompt or "")}
    planned_wrong = {c.get("check") for c in misses if c.get("where") == "plan"}
    notes = []
    for name in sorted(names):
        paths, row = STATED_FIELDS.get(name, ([], None))
        if row and row in planned_wrong:
            continue
        moved = [f"{a}.{b}" for a, b in paths if b in after.get(a, {}) and after[a][b] != before.get(a, {}).get(b)]
        if not moved:
            continue
        for a, b in paths:
            if b in after.get(a, {}):
                after[a][b] = copy.deepcopy(before.get(a, {}).get(b))
        groups = {g for g, (_, gp) in B.GROUPS.items() if any(tuple(x) in [tuple(y) for y in gp] for x in paths)}
        after["changed"] = [g for g in after.get("changed") or [] if g not in groups]
        restore_texts(before, after, sorted(groups))
        notes.append(f"the request states the {name.replace('_', ' ')} itself; the revised plan changed {', '.join(moved)}, restored")
    return notes


SHORT_PLAY = re.compile(r"play (\d+)% of the reference, (\d+)% of the ad|play ([\d.]+) s expected, ([\d.]+) s in the ad")
MORE_BLOCKS = 3  # a revision whose play is too short raises the reference's block count by this much (at most 10)
SHORT_SHARE = 0.6  # the ad's play under this share of the reference's play is too short (the case's own rule is 40%)


def play_too_short(misses: list[dict]) -> str | None:
    """Why the play is too short, from the misses fed back: "gameplay at the centre" failed, or the part-length row
    shows less play in the ad than the reference has. None otherwise."""
    for c in misses:
        if c.get("check") == "Asked: gameplay at the centre (the case)":
            return "the case's gameplay at the centre failed"
        if c.get("check") == "Reference: the part lengths":
            # only a clearly short play (under SHORT_SHARE of what the reference asks): an all-play reference's ad is
            # capped near 80% play by the engine, and raising its blocks there changed the board in every revision and
            # did not lengthen the play (round 2, case 05: 72% became 50% on the bigger board)
            m = SHORT_PLAY.search(c.get("detail") or "")
            if m:
                ad, ref = (float(m.group(2)), float(m.group(1))) if m.group(1) else (float(m.group(4)), float(m.group(3)))
                if ref and ad < SHORT_SHARE * ref:
                    return "the ad has well under the reference's play"
    return None


def pin_reference(before: dict, after: dict, misses: list[dict]) -> list[str]:
    """A revision keeps what the reference gave (the board's type, the ending, the HUD label, the length, the pure-play
    and stretch rules' tempo, intro, hold and blocks left, the play levers' tempo, moves and hesitations, the screen
    and the hidden clock's captions) unless the miss fed back is that field's own reference row or an asked fact about
    it (PINNED); the length and the timing always (round 2, case 05: a revision's normal tempo cut a 78% play to 51%;
    the request's own length is kept by keep_asked, its other stated values by keep_stated). When the play is too short
    for the case or the reference (round 1, third run: a 4-block board gave 3.5 s of play and both revisions kept it),
    the block count may rise above the reference's, and the size by a cell a side to hold it. Restores the pinned fields
    in `after` and returns what it kept and why, in words."""
    from .. import videoref as V
    missed = {c.get("check") for c in misses}
    short = play_too_short(misses)
    kept, notes = [], []
    video = video_ref(before)
    for g in (before.get("reference") or {}).get("set") or []:
        if g not in PINNED or missed & set(PINNED[g]) or (g == "gameplay.mistakes" and not video):
            continue  # the mistakes pin is the video workflow's (round 3); image_guided calls this too
        if short and g in ("level.blocks", "level.size"):
            continue  # raised below
        for path in B.GROUPS[g][1]:
            if B._get(after, path) != B._get(before, path):
                B._set(after, path, copy.deepcopy(B._get(before, path)))
                if g not in kept:
                    kept.append(g)
    if short and "level.blocks" in ((before.get("reference") or {}).get("set") or []):
        lb, la = before["level"], after["level"]
        want = min(V.BLOCKS_RANGE[1], max(la.get("blocks") or 0, (lb.get("blocks") or 0) + MORE_BLOCKS))
        w, h = lb.get("width"), lb.get("height")
        if w and h:
            # the size moves at most a cell a side from the reference's, as much as the blocks need
            grown = V.grow_for_blocks(want, lb.get("shape") if lb.get("shape") != "any" else None, w, h, lb.get("pieces"))
            la["width"], la["height"] = (grown[0], grown[1]) if grown else (w, h)
            want = min(want, grown[2]) if grown else want
        if want > (lb.get("blocks") or 0):
            la["blocks"] = want
            if la.get("moves") is not None and la["moves"] < want:  # each block leaves once: never fewer moves
                la["moves"] = want
                kept = [g for g in kept if g != "level.moves"]
                if "level.moves" not in after.setdefault("changed", []):
                    after["changed"].append("level.moves")
            for g in ("level.blocks", "level.size"):
                if g not in after.setdefault("changed", []):
                    after["changed"].append(g)
            notes.append(f"the reference's board was too small to fill the play ({short}): {lb.get('blocks')} blocks become "
                         f"{want}, on {la.get('width')}x{la.get('height')}")
    if kept:
        after["changed"] = [g for g in after.get("changed") or [] if g not in kept]
        restore_texts(before, after, kept)
    words = sorted({PINNED_WORDS.get(g, "board") for g in kept})
    return [f"the reference's {w} is kept ({', '.join(g for g in kept if PINNED_WORDS.get(g, 'board') == w)})" for w in words] + notes


# Words a control's plan text uses for a field (round 2 rerun 3, case 09: the visuals text said "the clock is now shown"
# after the pin had put the hidden clock back): a sentence naming a restored field is dropped from the revised text.
GROUP_WORDS = {
    "visuals.hud": r"clock|timer|hud|level badge|level number", "visuals.zoom": r"zoom|framing|close|camera",
    "visuals.cursor": r"cursor|hand|pointer|tap ring", "pacing.tempo": r"tempo|pace|calm|fast|slow|quick",
    "pacing.length": r"\b\d+ ?s(econds)?\b|length|long|short", "gameplay.hesitations": r"hesitat|pick(s|ed)? up|put back",
    "gameplay.mistakes": r"mistake|wrong|stuck|blocked", "gameplay.ending": r"ending|near-?fail|win|cliffhanger|time-?out",
    "sequence.timing": r"opening|still|hold|held", "gameplay.blocks_left": r"blocks? left|cut",
    "level.moves": r"moves?|drags?", "level.blocks": r"blocks?", "level.size": r"\d+ ?x ?\d+|size|bigger|smaller",
    "level.shape": r"shape|walls?|holes|open|narrow|lanes|ring|cross", "concept.hurry": r"hurry|seconds left",
    "concept.result": r"result|phew", "level.colours": r"colou?rs?",
}


def restore_texts(before: dict, after: dict, restored: list[str]) -> list[str]:
    """The plan text of each control a restore touched, made true again: when every field of that control is the base
    version's once more, its row (plan, status, why) is the base's; otherwise the revised text loses the sentences that
    name a restored field and says what was kept. Returns the controls rewritten."""
    out = []
    by_control: dict[str, list[str]] = {}
    for g in restored:
        if g in B.GROUPS:
            by_control.setdefault(B.GROUPS[g][0], []).append(g)
    for name, groups in by_control.items():
        mine = [g for g, (c, _) in B.GROUPS.items() if c == name]
        row, base = B.control(after, name), B.control(before, name)
        if all(B._get(after, path) == B._get(before, path) for g in mine for path in B.GROUPS[g][1]):
            if (row.get("plan"), row.get("status"), row.get("why")) != (base.get("plan"), base.get("status"), base.get("why")):
                row.update({k: copy.deepcopy(base.get(k)) for k in ("plan", "status", "why", "asked")})
                out.append(name)
            continue
        rx = re.compile("|".join(GROUP_WORDS.get(g, re.escape(B.GROUP_NAMES.get(g, g))) for g in groups), re.I)
        kept = [s for s in re.split(r"(?<=[.!?])\s+", row.get("plan") or "") if s and not rx.search(s)]
        note = "Kept as in the version before: " + ", ".join(B.GROUP_NAMES.get(g, g) for g in groups) + "."
        row["plan"] = " ".join(kept + [note])
        if row.get("why") and rx.search(row["why"]):
            row["why"] = None
        out.append(name)
    return out


def unchanged_texts(before: dict, after: dict) -> list[str]:
    """A revised plan's text for a control none of whose fields changed is the base version's (the revision planner
    may describe a change a pin or a restore then took back, or one it never made). Returns the controls rewritten."""
    out = []
    names = {c.get("control") for c in after.get("controls") or []} if isinstance(after.get("controls"), list) else set()
    for name in sorted(n for n in names if n):
        mine = [g for g, (c, _) in B.GROUPS.items() if c == name]
        if not mine or any(B._get(after, path) != B._get(before, path) for g in mine for path in B.GROUPS[g][1]):
            continue
        row, base = B.control(after, name), B.control(before, name)
        if row.get("plan") != base.get("plan"):
            row.update({k: copy.deepcopy(base.get(k)) for k in ("plan", "status", "why", "asked")})
            out.append(name)
    return out


PLAY_SHORT_S = 1.5  # a take whose play is this much under the planned play seconds re-runs the play levers


def play_again(v: dict, brief2: dict, prompt: str, misses: list[dict]) -> str | None:
    """The same play levers as the first plan (videoref.play_levers), corrected by what the last take measured (round 2
    rerun): when the pacing was taken and its row missed, or when the take's play fell PLAY_SHORT_S or more under the
    planned play seconds (cases 05 and 14: the end card absorbed it), the drag rate the take showed against the one
    expected corrects the table, and the tempo, moves and blocks are chosen again (the rate is pinned, the moves are
    not). None when the plan made no play decision, nothing was measured, or nothing calls for it."""
    from .. import audit
    from .. import reference as R
    from .. import videoref as V
    rec = (v["brief"].get("reference") or {}).get("play")
    a = next((r for r in (v["brief"].get("planner") or {}).get("references") or [] if r.get("kind") == "video"), None)
    if not rec or a is None:
        return None
    vdir = studio.STUDIO / v["id"] / f"v{v['n']}"
    try:
        manifest = json.loads((vdir / "parts.json").read_text())
    except (OSError, ValueError):
        return None
    pace = audit.pace_of_play(manifest)
    play = next((p for p in manifest.get("parts") or [] if p.get("id") == "play" and p.get("from_s") is not None), None)
    if pace is None or play is None:
        return None
    played_s = play["to_s"] - play["from_s"]
    paced_miss = rec.get("mode") == "pace" and any(c.get("check") == "Reference: the pacing" for c in misses)
    short = played_s < float(rec.get("target_s") or 0) - PLAY_SHORT_S
    if not (paced_miss or short):
        return None
    fixed = set(V.stated(prompt, (a.get("plan") or {}).get("constraints") or [], video=True))
    notes = a.get("notes") or {}
    segs = R.structure(notes.get("structure"), (a.get("facts") or {}).get("duration_s"))
    expected = V.expected_dps(v["brief"], v["brief"]["pacing"]["tempo"], int(v["brief"]["level"].get("moves") or rec["moves"]))
    scale = pace["dps"] / expected if expected else 1.0
    if isinstance(brief2.get("reference"), dict):
        brief2["reference"] = copy.deepcopy(brief2["reference"])  # the base version's provenance stays as it was
    bd = V.board_of(notes)
    read_size = (bd["columns"], bd["rows"]) if bd and bd.get("columns") and bd.get("rows") else None
    why = (f"; the last take played {played_s:.1f} s of the planned {rec.get('target_s')} s" if short else "")
    levers = lambda b: (b["pacing"]["tempo"], b["level"].get("moves"), b["gameplay"].get("hesitations"),  # noqa: E731
                        b["level"].get("blocks"), b["level"].get("width"), b["level"].get("height"))
    was = levers(brief2)
    line, new = V.play_levers(brief2, fixed, segs, rate=rec.get("reference_rate") if rec.get("mode") == "pace" else None,
                              scale=scale, why=why, read_size=read_size)
    if levers(brief2) == was:
        # nothing left to turn: say which limit stops the play (rerun 4, case 05: "the play again" chose the same levers
        # and the revision ended as "nothing is left to change")
        because = new.get("cap") or "the same levers are still the best estimate with the last take's measure"
        line = (f"nothing is left to change for the play ({was[0]} tempo, {was[1]} moves, {was[2] or 0} hesitations); "
                f"it stops at about {new['expected_s']:g} of {new['target_s']:g} s because {because}{why}")
    if isinstance(brief2.get("reference"), dict):
        brief2["reference"]["play"] = {**new, "measured_dps": pace["dps"], "measured_s": round(played_s, 1)}
    # the pacing row's text says what the play now is: the revised plan's sentences about the tempo or the moves go
    row = B.control(brief2, "difficulty_pacing")
    rx = re.compile(GROUP_WORDS["pacing.tempo"] + "|" + GROUP_WORDS["level.moves"] + "|" + GROUP_WORDS["gameplay.hesitations"], re.I)
    kept = [s for s in re.split(r"(?<=[.!?])\s+", row.get("plan") or "") if s and not rx.search(s)]
    row["plan"] = " ".join(kept + [line[0].upper() + line[1:] + "."])
    return line


def viewer_points(prompt: str, v: dict) -> set[str]:
    """The controls the viewer's "not as asked" is about (its partial or failed matches the request asks or the reading
    set, and its first fix when it names one)."""
    rv = v.get("review") or {}
    if rv.get("error"):
        return set()
    asked = asked_controls(prompt, v.get("brief") or {})
    out = {control_of(m.get("control")) for m in rv.get("match") or [] if m.get("verdict") in ("no", "partial")}
    fix = control_of((rv.get("fixes") or [""])[0])
    return {c for c in out if c in asked} | ({fix} if fix else set())


def length_guard(v: dict, brief2: dict, prompt: str) -> str | None:
    """A revision of a take that ran over the stated length never plans a longer play (rerun 4, case 09: 44.4 s of
    recording in a 45 s ad ran the ad to 48 s; the revision added a speeds-up curve, whose careful early pauses made it
    45.4 s and 49 s). Its lengthening changes (a new curve, a calm tempo, more hesitations or mistakes) go back to the
    take's, unless the request states them; then, with the take's own measure, the tempo whose play fits the room the
    stated length leaves (the length minus the shortest end card, the result and a replay) and fills it most is chosen,
    unless the request states the tempo or the reference's pace was taken. None when the take fitted."""
    from .. import audit
    from .. import videoref as V
    from ..ad import END_CARD_S, RESULT_HOLD_S
    video = video_ref(v["brief"])  # image_guided calls this too: its reading of the length is unchanged
    asked = audit.asked(prompt, case_range=video).get("length_s")
    vdir = studio.STUDIO / v["id"] / f"v{v['n']}"
    try:
        manifest = json.loads((vdir / "parts.json").read_text())
    except (OSError, ValueError):
        return None
    ad_s = float(manifest.get("duration_s") or 0)
    if asked is None or ad_s <= asked + 0.5:
        return None
    base, gp2, pc2 = v["brief"], brief2["gameplay"], brief2["pacing"]
    a = next((r for r in (base.get("planner") or {}).get("references") or [] if r.get("kind") == "video"), None)
    fixed = set(V.stated(prompt, ((a or {}).get("plan") or {}).get("constraints") or [], video=video))
    notes = []
    if pc2["curve"] != base["pacing"]["curve"] and "curve" not in fixed:
        pc2["curve"] = base["pacing"]["curve"]
        notes.append(f"the change of pace stays {pc2['curve'].replace('_', ' ')} (a new curve's careful pauses lengthen the play)")
    for key, word in (("hesitations", "hesitations"), ("mistakes", "mistakes")):
        if (gp2.get(key) or 0) > (base["gameplay"].get(key) or 0) and key not in fixed:
            gp2[key] = base["gameplay"].get(key)
            notes.append(f"no more {word} than the take had")
    paced = ((base.get("reference") or {}).get("play") or {}).get("mode") == "pace"
    play = next((p for p in manifest.get("parts") or [] if p.get("id") == "play" and p.get("from_s") is not None), None)
    drags = int((manifest.get("gameplay") or {}).get("drags") or 0)
    if "tempo" not in fixed and not paced and play and drags:
        g = base["gameplay"]
        mistakes = g["mistakes"] if g.get("mistakes") is not None else {"near_fail": 1, "time_out": 1}.get(g["ending"], 0)
        hes = g["hesitations"] if g.get("hesitations") is not None else {"near_fail": 2}.get(g["ending"], 0)
        left = (g.get("blocks_left") or 2) if g["ending"] == "cliffhanger" else 0
        moves = max(1, drags - mistakes - hes) + left
        measured = play["to_s"] - play["from_s"]
        scale = V.expected_play(base, base["pacing"]["tempo"], moves)[0] / measured if measured else 1.0
        sq = brief2["sequence"]
        room = asked - END_CARD_S[0] - (2.0 if g["ending"] == "cliffhanger" else RESULT_HOLD_S) - \
            (studio.REPLAY_EST_S if sq.get("replay") else 0.0) - float(sq.get("intro_s") or 0)
        fits = [(V.expected_play(brief2, tp, moves, scale)[0], tp) for tp in ("calm", "normal", "fast")]
        best = max((x for x in fits if x[0] <= room), default=min(fits))
        if best[1] != pc2["tempo"]:
            pc2["tempo"] = best[1]
            notes.append(f"a {best[1]} tempo: about {best[0]:.0f} s of play for the {room:g} s the stated {asked:g} s leaves "
                         f"(the take played {measured:.1f} s)")
    if not notes:
        return None
    for g in ("pacing.curve", "pacing.tempo", "gameplay.hesitations", "gameplay.mistakes"):
        if any(B._get(brief2, path) != B._get(base, path) for path in B.GROUPS[g][1]) and g not in brief2.setdefault("changed", []):
            brief2["changed"].append(g)
    return (f"the take ran {ad_s:g} s for the stated {asked:g} s, so the revision does not lengthen the play: "
            + "; ".join(notes))


def replay_fix(prompt: str, brief2: dict, misses: list[dict]) -> list[str]:
    """The revision of a take that missed an asked replay (round 4, case 30: the reference's cut was pinned and a
    cliffhanger plays no replay, so the revision could change nothing): the replay is on and a cliffhanger becomes a win
    (a near-fail when the words speak of a close call), its cut's blocks cleared. Returns the notes."""
    from .. import audit
    from .. import videoref as V
    if not any(c.get("check") == "Asked: the replay" for c in misses):
        return []
    if (audit.asked(prompt).get("sequence") or {}).get("replay") is not True:
        return []
    gp, sq, notes = brief2["gameplay"], brief2["sequence"], []
    if sq.get("replay") is not True:
        sq["replay"] = True
        notes.append("the request asks for a replay: the replay is on")
        if "sequence" not in brief2.setdefault("changed", []):
            brief2["changed"].append("sequence")
    if gp["ending"] == "cliffhanger":
        gp["ending"] = "near_fail" if V.CLOSE_CALL.search(prompt or "") else "win"
        gp["blocks_left"] = None
        for g in ("gameplay.ending", "gameplay.blocks_left"):
            if g not in brief2["changed"]:
                brief2["changed"].append(g)
        notes.append(f"a cliffhanger plays no replay, so the level is solved: a {V.ENDING_WORDS[gp['ending']]} (the asked "
                     f"replay missed)")
    return notes


HUD_GUARD_ROWS = ("Reference: the screen: the HUD over the board", "Asked: the zoom")


def hud_fix(prompt: str, before: dict, brief2: dict, misses: list[dict]) -> list[str]:
    """The revision of a take whose HUD bar covered the board's top row (audit.hud_row, measured on its first frame of
    play; 2026-10-17): the HUD is hidden when the request does not ask for it (videoref.hud_asked), else the zoom is
    lowered to the safe zoom for the board (videoref.safe_zoom; 1 when the table says the take's zoom was safe, since the
    measure wins). Then videoref.hud_clear keeps the revised plan clear too (its board may differ). Returns the notes."""
    from .. import videoref as V
    notes = []
    vs, lv = brief2["visuals"], brief2["level"]
    if any(c.get("check") in HUD_GUARD_ROWS for c in misses):
        z = float(vs.get("camera_zoom") or 1.0)
        if not V.hud_asked(prompt) and (vs.get("hud_level") or vs.get("hud_timer")):
            vs["hud_level"] = vs["hud_timer"] = False
            notes.append("the HUD covered the board's top row in the take (measured on its first frame of play); the "
                         "request does not ask for the HUD, so it is hidden")
            group = "visuals.hud"
        elif z > 1.0 + 1e-6:
            safe, _ = V.safe_zoom(V._int(lv.get("width")), V._int(lv.get("height")))
            new = safe if safe is not None and safe < z - 1e-6 else 1.0
            vs["camera_zoom"] = None if new <= 1.0 + 1e-6 else new
            notes.append(f"the HUD covered the board's top row in the take (measured); the request names the HUD, so the "
                         f"zoom is lowered from {z:g} to {new:g}")
            group = "visuals.zoom"
        else:
            group = None
        if group:
            if group not in brief2.setdefault("changed", []):
                brief2["changed"].append(group)
            B.adjust(brief2, "visuals", notes[-1][0].upper() + notes[-1][1:] + ".")
            if not vs.get("hud_timer") and brief2["gameplay"]["ending"] in ("near_fail", "time_out"):
                V.hidden_clock_captions(brief2, prompt)
    if video_ref(before):
        line = V.hud_clear(brief2, prompt)
        if line:
            notes.append(line)
    return notes


def revise_once(log: studio.Log, prompt: str, v: dict, review_on: bool) -> dict:
    """One round of the loop (the case p.10), as create.revise_once, with the reference kept: the
    revised brief carries the readings and the provenance, so its evaluation still has the
    reference rows. The media are not read again."""
    text = feedback(prompt, v)
    if text is None:
        if v.get("review_not_asked"):
            log("revision: nothing measurable was missed, and the viewer's \"not as asked\" is about what the request does "
                f"not ask and the reading did not set ({'; '.join(x.split(':')[0] for x in v['review_not_asked'])}); "
                "no revised version")
        else:
            log("revision: nothing measurable was missed; no revised version is needed")
        return v
    log.begin("revise", "the result missed part of the request or the reference; planning a revised take...")
    try:
        from .. import audit
        current = {k: x for k, x in v["brief"].items() if k != "planner"}
        brief2 = planner.plan(text, uploads={}, sprites=studio.sprite_names(), current=current, available=studio.uploads(),
                              inventory=studio.planner_context(v["id"], v["n"]), references={}, log=log,
                              history=studio.history(v["id"], v["n"]), parts=studio.part_lengths(v["id"], v["n"]), route=None)
        if not B.changed_groups(v["brief"], brief2):
            log("revision: the planner found nothing to change; the version stands with its report")
            v["revision"] = {"status": "unchanged", "feedback": text}
            return v
        brief2 = _carried(brief2, B.check(brief2, studio.uploads(), studio.sprite_names()))
        brief2["planner"]["workflow"] = WORKFLOW
        brief2["planner"]["references"] = (v["brief"].get("planner") or {}).get("references") or []
        if v["brief"].get("reference"):
            brief2["reference"] = v["brief"]["reference"]
        for note in keep_asked_guided(prompt, v["brief"], brief2):
            log(f"revision: {note}")
        misses = audit.misses(v.get("checks") or [])
        for note in pin_reference(v["brief"], brief2, misses):
            log(f"revision: {note}")
        for note in keep_stated(prompt, v["brief"], brief2, misses, video=True):
            log(f"revision: {note}")
        from .. import videoref
        if video_ref(v["brief"]) and not videoref.BLOCK_COLOUR_WORDS.search(prompt) and \
                brief2["visuals"].get("blocks") != v["brief"]["visuals"].get("blocks"):
            brief2["visuals"]["blocks"] = copy.deepcopy(v["brief"]["visuals"].get("blocks") or [])
            log("revision: the blocks' colours stay the plan's (a video's colours repaint the blocks only when the request names them, or "
                "when the board is copied from the game's own footage)")
        if (v["brief"].get("level") or {}).get("source") == "picture":
            # a board copied from the video stays that board (2026-10-19): a revision changes the play and the look, never it
            for k, val in v["brief"]["level"].items():
                brief2["level"][k] = copy.deepcopy(val)
            log("revision: the board stays the video's, copied cell by cell; the revision changes the play and the look only")
        from .. import videoref
        planned = copy.deepcopy({k: brief2.get(k) for k in ("gameplay", "pacing", "visuals", "level", "controls", "assumptions")})
        paced = play_again(v, brief2, prompt, misses)
        if paced:
            log(f"revision: the play again: {paced}")
        guarded = length_guard(v, brief2, prompt)
        if guarded:
            log(f"revision: {guarded}")
        if (v["brief"].get("level") or {}).get("source") == "picture" and misses and \
                all(c["check"] == "Asked: length" for c in misses) and brief2["pacing"].get("tempo") == v["brief"]["pacing"].get("tempo") \
                and (v["brief"].get("reference") or {}).get("play_overrun"):
            # V3 (2026-10-19): a copied board's play cannot be shortened; the plan said the overrun; a revision would film the same
            log("revision: the only miss is the length, and the plan said the video's board needs more play than the stated length "
                "holds; a copied board cannot be shortened, so no revised version is made")
            v["revision"] = {"status": "unchanged", "feedback": text, "why": "a copied board's play cannot be shortened (said in the plan)"}
            return v
        for note in replay_fix(prompt, brief2, misses):
            log(f"revision: {note}")
        for note in hud_fix(prompt, v["brief"], brief2, misses):
            log(f"revision: {note}")
        videoref.correct_texts(planned, brief2)  # the revised plan's words for a value these rules changed go
        for note in videoref.fit_captions(brief2, prompt, chain=True):
            log(f"revision: captions: {note}")
        texts = unchanged_texts(v["brief"], brief2)
        if texts:
            log(f"revision: the plan's text for {', '.join(texts)} is the version before's (none of their fields changed)")
        if not misses:
            # a revision the viewer alone started changes something the viewer's points are about, or no version is
            # made (rerun 4, case 14: a punch-in for "the stuck moment is quick" re-used the same recording)
            points = viewer_points(prompt, v)
            changed = set(B.changed_controls(v["brief"], brief2))
            if points and not changed & points:
                log(f"revision: the revised plan changes {', '.join(sorted(changed)) or 'nothing'}, nothing the viewer's points "
                    f"are about ({', '.join(sorted(points))}); no new version")
                v["revision"] = {"status": "unchanged", "feedback": text, "why": "nothing the viewer's points are about changed"}
                return v
        if not B.changed_groups(v["brief"], brief2):
            log("revision: with the reference's fields kept, nothing is left to change; the version stands with its report")
            v["revision"] = {"status": "unchanged", "feedback": text}
            return v
        if any(c.get("where") in ("level", "play") for c in misses) or any(c["check"] == "Asked: length" for c in misses):
            # the same spec gives the same cached board and film: a miss in the board, the play or the length
            # makes the revised version a new take
            brief2["gameplay"]["seed"] = (v["brief"]["gameplay"].get("seed") or 0) + 1
            if "gameplay.retake" not in brief2["changed"]:
                brief2["changed"].append("gameplay.retake")
        v2 = studio.make(text, brief2, v["id"], log, base=v["n"], allow_missing=True, asked=prompt, workflow=WORKFLOW)
        v2["revision"] = {"status": "made", "of": v["n"], "feedback": text, "original_prompt": prompt}
        if review_on:
            log.begin("review", "the viewer's review of the revised version...")
            try:
                v2["review"] = review.review(v2, prompt, studio.STUDIO, log=log)
            except Exception as e:
                log(f"review failed: {e}")
                v2["review"] = {"error": str(e)[:300]}
        miss2 = audit.misses(v2.get("checks") or [])
        log(f"revision: v{v2['n']} made; {'everything measurable met' if not miss2 else 'still missed: ' + ', '.join(c['check'] for c in miss2)}")
        vdir = studio.STUDIO / v2["id"] / f"v{v2['n']}"
        (vdir / "version.json").write_text(json.dumps(v2, indent=1, ensure_ascii=False))
        return v2
    except Exception as e:  # a failed revision never loses the first version
        if "identical to v" in str(e):
            log(f"revision: {e}")
            v["revision"] = {"status": "unchanged", "feedback": text, "why": str(e)[:300]}
            return v
        log(f"revision failed: {e}")
        v["revision"] = {"status": "failed", "error": str(e)[:300], "feedback": text}
        return v
