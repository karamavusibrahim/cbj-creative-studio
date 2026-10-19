"""Creative generation: text, image or video in, a new creative out (the case's core requirements
1-4), with its own evaluate / feed back / revise loop. See workflows/__init__.py."""
from __future__ import annotations

import json

from .. import brief as B
from .. import planner, reference, review, route, studio

MAX_REVISIONS = 2  # evaluate, feed back, make again: at most two rounds after the first version
WORKFLOW = "create"


def plan(log: studio.Log, prompt: str, uploads: list[str]) -> dict:
    """The brief of a new creative. Attached videos are always references; attached images are when
    the prompt says so ("inspired by", "like this"); both are analysed before planning (case p.6)."""
    all_ups, vids = studio.uploads(), studio.videos()
    ups = {n: all_ups[n] for n in uploads if n in all_ups}
    refs = {n: vids[n] for n in uploads if n in vids}
    if reference.is_reference_prompt(prompt, edit=False):
        refs.update({n: p for n, p in ups.items() if not B.is_audio(n)})
    log.begin("plan", "a new creative: reading the request...")
    from .image_guided import english_prompt  # common to every workflow (2026-10-19): the parsers are English, a request is translated once
    original, prompt = prompt, english_prompt(prompt, None, log)
    rt = route.decide(prompt, manifest=None, uploads=sorted(ups), videos=sorted(n for n in refs if n in vids))
    log("route: " + route.summary(rt))
    brief = planner.plan(prompt, uploads=ups, sprites=studio.sprite_names(), current=None, available=all_ups,
                         inventory=None, references=refs, log=log, history=None, parts=None, route=None)
    brief["planner"]["route"] = rt
    brief["planner"]["workflow"] = WORKFLOW
    if prompt != original:
        brief["planner"]["prompt_original"], brief["planner"]["prompt_english"] = original, prompt
    time_out_limit(log, prompt, brief)
    log(f"planned by {brief['planner']['model']} in {brief['planner']['seconds']} s")
    return brief


def time_out_limit(log: studio.Log, prompt: str, brief: dict) -> None:
    """"The clock runs out with two blocks left": the engine's time-out ends with exactly one block; said in the plan
    (common to every creation workflow, 2026-10-19; first in guided.plan after V5)."""
    try:
        from ..imageaudit import blocks_left_asked
        n_left = blocks_left_asked(prompt)
        if n_left not in (None, 1) and brief["gameplay"].get("ending") == "time_out":
            B.adjust(brief, "gameplay", f"a time-out ends with exactly one block, one cell from its gate (the play engine's race); "
                                        f"the {n_left} blocks left asked are not played.")
            log(f"plan: a time-out ends with one block left, not {n_left}: said in the plan")
    except Exception:
        pass


def make(log: studio.Log, prompt: str, brief: dict, draft: bool = False, review_on: bool = False,
         without_files: bool = False, revise: bool = True) -> dict:
    """Make the creative, review it as a viewer, then run the loop until nothing measurable is
    missed, nothing can be changed, or MAX_REVISIONS rounds are done. Every version is kept."""
    from .image_guided import is_english
    if (brief.get("planner") or {}).get("prompt_english") and not is_english(prompt):
        prompt = brief["planner"]["prompt_english"]  # the rows, the review and the loop read the translation the plan used
    checked = B.check(brief, studio.uploads(), studio.sprite_names())
    checked["planner"] = brief.get("planner", {})
    checked["changed"] = brief.get("changed", [])
    checked["needs"] = brief.get("needs", [])
    v = studio.make(prompt, checked, None, log, draft=draft, allow_missing=without_files, workflow=WORKFLOW)
    if review_on and not draft:
        v = _reviewed(log, prompt, v)
    if revise and not draft:
        from .. import audit
        from . import guided
        from .image_guided import repeated_miss
        made = [v]
        for _ in range(MAX_REVISIONS):
            v = revise_once(log, prompt, v, review_on)
            if (v.get("revision") or {}).get("status") != "made":
                guided.save_record(v)  # the loop's verdict on this version is kept with it (common, 2026-10-19)
                break
            made.append(v)
            if not audit.misses(v.get("checks") or []):
                break
            same = repeated_miss(made[-2], made[-1])
            if same:  # the same row missed twice with the same measure: the board's limit, said; no more revisions (common)
                log(f"revision: {same['check']} missed twice with the same measure ({str(same.get('detail'))[:160]}): that is "
                    f"the limit of this board, so no more revisions")
                for x in made[-2:]:
                    x["limit_note"] = f"{same['check']}: {same.get('detail')}"
                break
        v = guided.best_version(log, made)  # the best version is final, not the last (common, 2026-10-19)
    return v


def _reviewed(log: studio.Log, prompt: str, v: dict) -> dict:
    log.begin("review", "the viewer's review...")
    try:
        v["review"] = review.review(v, prompt, studio.STUDIO, log=log)
    except Exception as e:  # a review that fails never loses the version
        log(f"review failed: {e}")
        v["review"] = {"error": str(e)[:300]}
    return v


def feedback(prompt: str, v: dict) -> str | None:
    """What the made version missed of the request, as a request for a revised take: the measured
    misses (facts) first, then the viewer's first fix when it is about something asked for."""
    from .. import audit
    return audit.feedback(prompt, v.get("checks") or [], v.get("review"))


def keep_asked(prompt: str, before: dict, after: dict) -> list[str]:
    """A revision changes what the feedback names and nothing the original request fixed: the asked
    length and the asked ending stay (2026-10-16: a 40 s time-out's third round came back planned at
    30 s after feedback about held screens). Returns the notes of what was restored."""
    from .. import audit
    a = audit.asked(prompt)
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


def revise_once(log: studio.Log, prompt: str, v: dict, review_on: bool) -> dict:
    """One round of the loop (the case p.10: generate, review, request a modification, generate
    the revised version), run by the tool itself. A miss in the board or the play makes the revised
    version a new take (another seed); a miss in the ad changes the ad only. The planner reads the
    feedback against the current brief; no edit routing is involved (that is the edit workflow)."""
    text = feedback(prompt, v)
    if text is None:
        log("revision: nothing measurable was missed; no revised version is needed")
        return v
    log.begin("revise", "the result missed part of the request; planning a revised take...")
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
        brief2 = B.check(brief2, studio.uploads(), studio.sprite_names()) | {k: brief2[k] for k in ("planner", "changed", "needs") if k in brief2}
        brief2["planner"]["workflow"] = WORKFLOW
        for note in keep_asked(prompt, v["brief"], brief2):
            log(f"revision: {note}")
        misses = audit.misses(v.get("checks") or [])
        from . import guided
        for note in guided.keep_stated(prompt, v["brief"], brief2, misses, video=False):  # every value the request states stays (common)
            log(f"revision: {note}")
        guarded = guided.length_guard(v, brief2, prompt)  # a take that ran over never plans a longer play (common)
        if guarded:
            log(f"revision: {guarded}")
        texts = guided.unchanged_texts(v["brief"], brief2)
        if texts:
            log(f"revision: the plan's text for {', '.join(texts)} is the version before's (none of their fields changed)")
        if not misses:
            # a revision the viewer alone started changes something the viewer's points are about, or no version is made
            # (common, 2026-10-19: the guided loops learnt it on a punch-in that re-used the same recording)
            points = guided.viewer_points(prompt, v)
            changed = set(B.changed_controls(v["brief"], brief2))
            if points and not changed & points:
                log(f"revision: the revised plan changes {', '.join(sorted(changed)) or 'nothing'}, nothing the viewer's points "
                    f"are about ({', '.join(sorted(points))}); no new version")
                v["revision"] = {"status": "unchanged", "feedback": text, "why": "nothing the viewer's points are about changed"}
                return v
        if not B.changed_groups(v["brief"], brief2):
            log("revision: after the kept values nothing is left to change; the version stands with its report")
            v["revision"] = {"status": "unchanged", "feedback": text}
            return v
        if any(c.get("where") in ("level", "play") for c in misses) or any(c["check"] == "Asked: length" for c in misses):
            # the same spec gives the same cached board and film, so a miss in the board, the play or
            # the length (which an ad edit keeps) makes the revised version a new take
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
                v2["review"] = {"error": str(e)[:300]}
        miss2 = audit.misses(v2.get("checks") or [])
        log(f"revision: v{v2['n']} made; {'everything measurable met' if not miss2 else 'still missed: ' + ', '.join(c['check'] for c in miss2)}")
        vdir = studio.STUDIO / v2["id"] / f"v{v2['n']}"
        (vdir / "version.json").write_text(json.dumps(v2, indent=1, ensure_ascii=False))
        return v2
    except Exception as e:  # a failed revision never loses the first version
        if "identical to v" in str(e):
            # the planner's change made no difference (the engine says why): the version stands, nothing failed
            log(f"revision: {e}")
            v["revision"] = {"status": "unchanged", "feedback": text, "why": str(e)[:300]}
            return v
        log(f"revision failed: {e}")
        v["revision"] = {"status": "failed", "error": str(e)[:300], "feedback": text}
        return v
