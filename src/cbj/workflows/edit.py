"""Controlled editing: an existing creative and a request in, a new version of that creative out,
with the edit report as its proof and its own evaluate / feed back / revise loop (the brief's core
requirement 5, p.7). See workflows/__init__.py."""
from __future__ import annotations

import json

from .. import brief as B
from .. import planner, reference, review, route, studio
from ..edits import direct_edit

MAX_REVISIONS = 2
WORKFLOW = "edit"


def match(uploads: list[str]) -> dict | bool | None:
    """An attached MP4 that is one of the tool's own versions (the same bytes) routes the edit to
    that version's metadata, with no video analysis. None: no video attached; False: a video that
    matches none; a dict: the match."""
    vids = studio.videos()
    matched = None
    for n in uploads:
        if n in vids:
            m = route.match_upload(vids[n], studio.STUDIO)
            if m:
                return {**m, "upload": n}
            matched = False
    return matched


def plan(log: studio.Log, prompt: str, creative_id: str, base: int | None, uploads: list[str],
         matched: dict | bool | None = None) -> dict:
    """Route first, then plan. The route (route.py) is decided in code from the version's parts
    manifest: a direct edit is made with no planner at all; otherwise the planner gets the route
    with the edit and is checked against it afterwards (drift in the play is restored)."""
    v = studio.parent(creative_id, base)
    if v is None:
        raise ValueError(f"no creative {creative_id}")
    all_ups, vids = studio.uploads(), studio.videos()
    current = {k: x for k, x in v["brief"].items() if k != "planner"}
    inventory = studio.planner_context(creative_id, v["n"])
    past = studio.history(creative_id, v["n"])
    parts = studio.part_lengths(creative_id, v["n"])
    manifest = None
    try:
        manifest = studio.parts(creative_id, v["n"])
    except Exception as e:  # an old version with a broken folder: the planner works from the inventory alone
        log(f"parts manifest unavailable: {e}")
    ups = {n: all_ups[n] for n in uploads if n in all_ups}
    refs = {n: vids[n] for n in uploads if n in vids and not (isinstance(matched, dict) and matched.get("upload") == n)}
    if reference.is_reference_prompt(prompt, edit=True):
        refs.update({n: p for n, p in ups.items() if not B.is_audio(n)})
    log.begin("plan", "routing the request as an edit of the current version...")
    from .image_guided import english_prompt  # common to every workflow (2026-10-19): the route and the row parsers are English
    original, prompt = prompt, english_prompt(prompt, None, log)
    locate = None
    if manifest is not None:
        video = studio.STUDIO / v["video"]
        locate = lambda clause: route.locate_with_vision(video, clause, manifest.get("duration_s"))  # noqa: E731
    used = None
    try:  # the slots on this version's board: a colour word names one of them (brief.slot_of_colour_word)
        lv = json.loads((studio.STUDIO / v["level"]["file"]).read_text())
        used = {B.COLOURS[int(d["blockColor"])] for d in lv.get("GridBlockDatas", [])}
    except Exception:
        used = None
    colour_of = lambda w: B.slot_of_colour_word(w, current, used)  # noqa: E731
    rt = route.decide(prompt, manifest=manifest, uploads=sorted(ups), videos=sorted(n for n in refs if n in vids),
                      matched=matched if matched else (False if matched is False else None), locate=locate, colour_of=colour_of)
    log("route: " + route.summary(rt))
    if rt.get("direct_op"):
        brief, words = direct_edit(current, rt["direct_op"], all_ups, studio.sprite_names())
        brief["planner"] = {"model": None, "seconds": 0, "prompt": prompt.strip(), "edit": True, "restored": [],
                            "direct": rt["direct_op"], "route": rt, "words": words, "workflow": WORKFLOW}
        if prompt != original:
            brief["planner"]["prompt_original"], brief["planner"]["prompt_english"] = original, prompt
        log(f"a direct edit, made in code with no planner: {words}")
        return brief
    log("reading the prompt as an edit of the current version...")
    brief = planner.plan(prompt, uploads=ups, sprites=studio.sprite_names(), current=current, available=all_ups,
                         inventory=inventory, references=refs, log=log, history=past, parts=parts, route=route.text(rt))
    restored = route.verify(brief, rt, current)
    if restored:
        log("route check: restored " + ", ".join(B.GROUP_NAMES.get(g, g) for g in restored) + " (the route does not change the play)")
    brief["planner"]["route"] = rt
    brief["planner"]["workflow"] = WORKFLOW
    if prompt != original:
        brief["planner"]["prompt_original"], brief["planner"]["prompt_english"] = original, prompt
    log(f"planned by {brief['planner']['model']} in {brief['planner']['seconds']} s")
    return brief


def direct(log: studio.Log, creative_id: str, base: int | None, op: dict, draft: bool = False) -> dict:
    """An exact edit (a picture, a caption, the sound, the music): the brief is changed in code."""
    v = studio.parent(creative_id, base)
    if v is None:
        raise ValueError(f"no creative {creative_id}")
    log.begin("plan", "an exact edit: the brief is changed in code (no planner)...")
    brief, words = direct_edit({k: x for k, x in v["brief"].items() if k != "planner"}, op, studio.uploads(), studio.sprite_names())
    files = [op.get("file") or op.get("music")] if (op.get("file") or op.get("music")) else []
    rt = route.decide(words, manifest=studio.parts(creative_id, v["n"]), uploads=files)
    rt["direct_op"], rt["edit_type"] = op, "direct"
    brief["planner"] = {"model": None, "seconds": 0, "prompt": words, "edit": True, "restored": [], "direct": op, "route": rt,
                        "workflow": WORKFLOW}
    log(words)
    return studio.make(words, brief, creative_id, log, draft=draft, base=v["n"], workflow=WORKFLOW)


def make(log: studio.Log, prompt: str, brief: dict, creative_id: str, base: int | None, draft: bool = False,
         review_on: bool = False, without_files: bool = False, revise: bool = True) -> dict:
    """Make the new version, prove the edit (the edit report), review it as a viewer against the edit,
    then run the loop on what the report and the audit say the edit missed."""
    from .image_guided import is_english
    if (brief.get("planner") or {}).get("prompt_english") and not is_english(prompt):
        prompt = brief["planner"]["prompt_english"]  # the rows, the review and the loop read the translation the plan used
    checked = B.check(brief, studio.uploads(), studio.sprite_names())
    checked["planner"] = brief.get("planner", {})
    checked["changed"] = brief.get("changed", [])
    checked["needs"] = brief.get("needs", [])
    v = studio.make(prompt, checked, creative_id, log, draft=draft, base=base, allow_missing=without_files, workflow=WORKFLOW)
    if review_on and not draft:
        v = _reviewed(log, prompt, v)
    if revise and not draft:
        for _ in range(MAX_REVISIONS):
            v = revise_once(log, prompt, v, review_on)
            if (v.get("revision") or {}).get("status") != "made" or feedback(prompt, v) is None:
                break
    return v


def _reviewed(log: studio.Log, prompt: str, v: dict) -> dict:
    log.begin("review", "the viewer's review of the edit...")
    try:
        v["review"] = review.review(v, prompt, studio.STUDIO, log=log, edit_of=v.get("proof"))
    except Exception as e:
        log(f"review failed: {e}")
        v["review"] = {"error": str(e)[:300]}
    return v


def feedback(prompt: str, v: dict) -> str | None:
    """What the edit missed, for a second round: items the edit report says changed without being
    asked (they must go back to the base version), what the edit asked for and the audit says is not
    so, and the viewer's first fix when it is about the edit."""
    from .. import audit
    proof = v.get("proof") or {}
    lines = []
    for r in proof.get("rows") or []:
        if r.get("status") == "not_asked":
            lines.append(f"{r['title']} changed although the request did not ask for it ({r.get('detail', '')[:200]}); keep it as in v{v.get('from')}")
    px = proof.get("pixels") or {}
    if px.get("contained") is False:
        lines.append("pixels changed outside the layer the edit names; keep the rest of the frame as it was")
    for c in audit.misses(v.get("checks") or []):
        lines.append(f"{c['check'][7:] if c['check'].startswith('Asked: ') else c['check']}: {c['detail']}")
    rv = v.get("review") or {}
    if rv and not rv.get("error"):
        bad = [m for m in rv.get("match", []) if m.get("verdict") in ("no", "partial")]
        if bad and rv.get("fixes"):
            lines.append("the viewer saw: " + "; ".join(f"{m['control']}: {m['seen']}" for m in bad[:2]))
            lines.append("suggested fix: " + rv["fixes"][0])
    if not lines:
        return None
    return ("Revise this version so the edit request is met and nothing else changes; change only what these points need. "
            "The edit request was: \"" + prompt.strip() + "\". What the made version missed: " + " | ".join(lines))


def keep_to_asked(brief2: dict, v_brief: dict, base_brief: dict | None, asked: set[str]) -> list[str]:
    """A revision may change only the groups the edit request asked for, or put a group back to what
    the base version had (an unasked change the report found). Any other group the revision's plan
    changed is restored from the version being revised; the groups held back are returned.
    2026-10-18: on an open board, "use this object instead of the current obstacle" was revised by
    adding a wall to the level because the viewer saw no obstacle, a gameplay change for an asset
    request; the next round took the wall out again."""
    held = []
    for g in B.changed_groups(v_brief, brief2):
        if g in asked:
            continue
        paths = B.GROUPS[g][1]
        if base_brief is not None and all(B._get(brief2, p) == B._get(base_brief, p) for p in paths):
            continue  # back to what the user saw: allowed
        for p in paths:
            B._set(brief2, p, json.loads(json.dumps(B._get(v_brief, p))))
        if g in brief2.get("changed", []):
            brief2["changed"].remove(g)
        held.append(g)
    return held


def revise_once(log: studio.Log, prompt: str, v: dict, review_on: bool) -> dict:
    """One round of the edit loop: the feedback is routed and planned as an edit of the version it
    criticises (the same route rules apply: the play is kept unless the edit needs it), and it may
    change only what the edit request asked for (keep_to_asked)."""
    text = feedback(prompt, v)
    if text is None:
        log("revision: the edit report and the audit find nothing missed; no revised version is needed")
        return v
    log.begin("revise", "the edit missed part of the request; planning a revised version...")
    try:
        brief2 = plan(log, text, v["id"], v["n"], uploads=[])
        asked = set((v.get("revision") or {}).get("asked_groups") or v["brief"].get("changed") or [])
        if any(g.startswith(route.GAME_GROUPS) for g in asked):
            # a new play or board: the captions and parts that describe it may follow (a Turkish end-card line
            # read "0 blocks left" after a cliffhanger became a win, 2026-10-18)
            asked |= {g for g in B.GROUPS if g.startswith(("concept.", "sequence"))}
        base = studio.parent(v["id"], v["from"]) if v.get("from") else None
        held = keep_to_asked(brief2, v["brief"], base["brief"] if base else None, asked)
        if held:
            log("revision kept to the asked groups: " + ", ".join(B.GROUP_NAMES.get(g, g) for g in held)
                + f" stay as in v{v['n']} (the revision had changed them)")
        if not brief2.get("planner", {}).get("direct") and not B.changed_groups(v["brief"], brief2):
            log("revision: the planner found nothing to change; the version stands with its report")
            v["revision"] = {"status": "unchanged", "feedback": text}
            return v
        brief2 = B.check(brief2, studio.uploads(), studio.sprite_names()) | {k: brief2[k] for k in ("planner", "changed", "needs") if k in brief2}
        v2 = studio.make(text, brief2, v["id"], log, base=v["n"], allow_missing=True, asked=prompt, workflow=WORKFLOW)
        v2["revision"] = {"status": "made", "of": v["n"], "feedback": text, "original_prompt": prompt,
                          "asked_groups": sorted(asked), "held": held}
        if review_on:
            v2 = _reviewed(log, prompt, v2)
        left = feedback(prompt, v2)
        log(f"revision: v{v2['n']} made; {'the edit is met and nothing else changed' if left is None else 'still open: ' + left[-300:]}")
        vdir = studio.STUDIO / v2["id"] / f"v{v2['n']}"
        (vdir / "version.json").write_text(json.dumps(v2, indent=1, ensure_ascii=False))
        return v2
    except Exception as e:
        if "identical to v" in str(e):
            log(f"revision: {e}")
            v["revision"] = {"status": "unchanged", "feedback": text, "why": str(e)[:300]}
            return v
        log(f"revision failed: {e}")
        v["revision"] = {"status": "failed", "error": str(e)[:300], "feedback": text}
        return v
