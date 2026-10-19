"""Lessons (2026-10-18): the designers' feedback distilled into one inspectable, versioned, correctable
document the owner reads before adjusting the agentic workflows by hand.

The idea is COLLEAGUE.SKILL's (Zhou et al., 2026, arXiv:2605.31264) applied to this tool, with its scope
cut to what fits a creative studio used by many designers:

* traces in: the feedback records (feedback.py) and the prompts of the creatives they point at;
* two tracks out, as in the paper's dual representation: Part A, the capability track, is what the
  workflows should do differently, per workflow and control, each lesson citing the records that
  back it; Part B, the behaviour track, is how each designer asks (what they want by default and the
  words they use), which tells the owner whether a complaint is a system fault or one person's taste;
* a versioned package (studio/_lessons/v<N>/: lessons.json, LESSONS.md, meta.json) with rollback;
* natural-language corrections from the owner ("the lesson about speed-ups is wrong: designers meant
  the hurry caption"), kept as correction records that outrank the records at the next distillation.

What was left out on purpose: persona simulation, installing the package into an agent, galleries.

Zero effect, by construction: no workflow, the planner, the enhancer or the studio imports this module,
and the package is never put in a prompt (tests/test_feedback.py checks the sources). The document is
for a person; the owner changes code or skills after reading it, with the evidence ids in hand.

Honesty rules in code: a lesson that cites no existing record is dropped; a lesson with one record is
marked "thin" whatever the model said; a designer entry needs at least one record from that designer.

API: GET /api/lessons[?version=N], POST /api/lessons {action: distill|correct|rollback, text?, version?}.
CLI: `cbj lessons [--distill] [--correct TEXT] [--rollback N]`.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from . import feedback, llm, studio

MAX_RECORDS = 200
MAX_PROMPT_CHARS = 300
WORKFLOWS = ("create", "guided", "image_guided", "edit", "website", "general")
WORKFLOW_WORDS = {"create": "text to creative", "guided": "video-guided creative", "image_guided": "image-guided creative",
                  "edit": "controlled editing", "website": "the website", "general": "the whole tool"}

SYSTEM = """You distil designers' feedback about an AI tool that makes playable-looking ads for the mobile puzzle game
Color Block Jam. The tool reads a prompt into a brief (level, ending, captions, tempo, look, sound, HUD, hand), records the
play, composes the video, and edits an approved creative on request. Designers used it and left feedback records; each record
has an id, a designer, an area, a kind (wrong, missing, good, idea), what happened, what they expected, and the scene (the
prompt and the workflow of the version they looked at).

Write LESSONS for the owner, who will change the workflows by hand. Two parts.

PART A, the capability track: per workflow (create, guided, image_guided, edit, website, general), the lessons: what the
tool should do differently, as a one-sentence rule, with the record ids that are the evidence and a suggested change in the
owner's terms (which control, which step). Group repeated complaints into one lesson. Never invent a lesson the records do
not contain. confidence is "strong" when two or more designers or three or more records agree, else "thin".

PART B, the behaviour track: per designer, what they ask for by default (their habitual asks, from the prompts and the
records) and the phrasing they use that the tool may read badly, each with record ids. Do not describe personality; only
asks and words.

Then open_questions: what the owner should ask the designers because the records are ambiguous.

If OWNER CORRECTIONS are given, they outrank the records: apply each one and never restate what a correction retracted.
Plain words, no marketing, no statistics the records do not state. Every id you cite must be one of the given ids."""

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["summary", "workflows", "designers", "open_questions"],
    "properties": {
        "summary": {"type": "string"},
        "workflows": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["workflow", "lessons"],
            "properties": {"workflow": {"type": "string", "enum": list(WORKFLOWS)},
                           "lessons": {"type": "array", "items": {
                               "type": "object", "additionalProperties": False,
                               "required": ["lesson", "evidence", "suggested_change", "confidence"],
                               "properties": {"lesson": {"type": "string"}, "evidence": {"type": "array", "items": {"type": "string"}},
                                              "suggested_change": {"type": "string"},
                                              "confidence": {"type": "string", "enum": ["strong", "thin"]}}}}}}},
        "designers": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["designer", "asks_for", "phrasing", "evidence"],
            "properties": {"designer": {"type": "string"}, "asks_for": {"type": "array", "items": {"type": "string"}},
                           "phrasing": {"type": "array", "items": {"type": "string"}},
                           "evidence": {"type": "array", "items": {"type": "string"}}}}},
        "open_questions": {"type": "array", "items": {"type": "string"}},
    },
}


def folder() -> Path:
    return studio.STUDIO / "_lessons"


def corrections_path() -> Path:
    return folder() / "corrections.jsonl"


def corrections() -> list[dict]:
    p = corrections_path()
    if not p.is_file():
        return []
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


def version_dirs() -> list[Path]:
    if not folder().is_dir():
        return []
    return sorted((p for p in folder().glob("v*") if p.is_dir() and (p / "lessons.json").is_file()), key=lambda p: int(p.name[1:]))


def current_version() -> int | None:
    p = folder() / "current.json"
    if p.is_file():
        try:
            n = int(json.loads(p.read_text())["version"])
            if (folder() / f"v{n}" / "lessons.json").is_file():
                return n
        except (ValueError, KeyError):
            pass
    dirs = version_dirs()
    return int(dirs[-1].name[1:]) if dirs else None


def _set_current(n: int) -> None:
    (folder() / "current.json").write_text(json.dumps({"version": n, "set": time.strftime("%Y-%m-%d %H:%M:%S")}))


def load(version: int | None = None) -> dict | None:
    """The package (lessons.json + meta + the Markdown) of a version; the current one by default."""
    n = version if version is not None else current_version()
    if n is None:
        return None
    d = folder() / f"v{int(n)}"
    if not (d / "lessons.json").is_file():
        raise ValueError(f"no lessons version {n}")
    out = json.loads((d / "lessons.json").read_text())
    out["meta"] = json.loads((d / "meta.json").read_text())
    out["markdown"] = (d / "LESSONS.md").read_text()
    out["versions"] = [{"version": int(p.name[1:]), **json.loads((p / "meta.json").read_text())} for p in version_dirs()]
    out["current"] = current_version()
    out["corrections"] = corrections()
    return out


# ── the traces ──────────────────────────────────────────────────────────────────────────────────

def _record_text(r: dict) -> str:
    s = r.get("scene") or {}
    where = f"{s.get('workflow', '?')} · {s['creative_id']} v{s['version']}" if s.get("creative_id") else r.get("page", "general")
    lines = [f"[{r['id']}] designer: {r['designer']} · kind: {r['kind']} · area: {r['area']} · about: {where}" +
             (f" · rating {r['rating']}/5" if r.get("rating") else "")]
    if s.get("prompt"):
        lines.append(f"  the prompt: {s['prompt'][:MAX_PROMPT_CHARS]}")
    earlier = [h for h in (s.get("history") or []) if h["n"] < (s.get("version") or 0)]
    if earlier:
        lines.append("  earlier prompts of the same creative: " + " | ".join(f"v{h['n']}: {h['prompt'][:120]}" for h in earlier[-3:]))
    if r.get("step"):
        lines.append(f"  about the step: {feedback.STEP_WORDS.get(r['step'], r['step'])}" + (f" · item: {r['item']}" if r.get("item") else ""))
    if r.get("wrong"):
        lines.append(f"  what happened: {r['wrong']}")
    if r.get("expected"):
        lines.append(f"  expected: {r['expected']}")
    pr = r.get("process") or {}
    facts = []
    if pr.get("checks", {}).get("misses"):
        facts.append("the engine's own checks missed: " + "; ".join(m["check"] for m in pr["checks"]["misses"][:3]))
    if (pr.get("proof") or {}).get("verdict"):
        facts.append("the edit report: " + pr["proof"]["verdict"][:160])
    if (pr.get("review") or {}).get("not_as_asked"):
        facts.append("the viewer saw not as asked: " + "; ".join(m["control"] for m in pr["review"]["not_as_asked"][:3]))
    if facts:
        lines.append("  the engine's record of that version: " + " | ".join(facts))
    an = feedback.analysis_of(r["id"])
    if an:
        lines.append(f"  the owner's analysis of this note: {an.get('verdict')} ({an.get('confidence')}): {an.get('what_happened', '')[:200]} "
                     f"Why: {an.get('why', '')[:200]}")
    return "\n".join(lines)


def traces(records: list[dict]) -> str:
    return "\n".join(_record_text(r) for r in records)


# ── the checks ──────────────────────────────────────────────────────────────────────────────────

def _checked(out: dict, records: list[dict]) -> tuple[dict, list[str]]:
    """Drop what the records do not back; mark thin evidence thin; report what was dropped."""
    ids = {r["id"] for r in records}
    by_designer = {r["designer"].lower(): r["designer"] for r in records}
    designers_of = {r["id"]: r["designer"].lower() for r in records}
    dropped: list[str] = []
    workflows = []
    for w in out.get("workflows") or []:
        kept = []
        for les in w.get("lessons") or []:
            ev = [e for e in dict.fromkeys(les.get("evidence") or []) if e in ids]
            if not ev:
                dropped.append(f"lesson without evidence: {les.get('lesson', '')[:80]}")
                continue
            conf = les.get("confidence", "thin")
            if len(ev) < 2 or len({designers_of[e] for e in ev}) < 2 and len(ev) < 3:
                conf = "thin"
            kept.append({"lesson": les.get("lesson", "").strip(), "evidence": ev, "suggested_change": les.get("suggested_change", "").strip(),
                         "confidence": conf})
        if kept:
            workflows.append({"workflow": w.get("workflow", "general"), "lessons": kept})
    designers = []
    for d in out.get("designers") or []:
        name = by_designer.get((d.get("designer") or "").strip().lower())
        ev = [e for e in dict.fromkeys(d.get("evidence") or []) if e in ids and designers_of[e] == (name or "").lower()]
        if not name or not ev:
            dropped.append(f"designer entry without that designer's records: {d.get('designer', '?')}")
            continue
        designers.append({"designer": name, "asks_for": [a.strip() for a in d.get("asks_for") or [] if a.strip()],
                          "phrasing": [p.strip() for p in d.get("phrasing") or [] if p.strip()], "evidence": ev})
    return ({"summary": (out.get("summary") or "").strip(), "workflows": workflows, "designers": designers,
             "open_questions": [q.strip() for q in out.get("open_questions") or [] if q.strip()]}, dropped)


# ── the document ────────────────────────────────────────────────────────────────────────────────

def render(pkg: dict, meta: dict, corr: list[dict]) -> str:
    L = [f"# LESSONS v{meta['version']} · Color Block Jam creative tool", "",
         f"Distilled {meta['generated']} from {meta['records']} feedback records by {meta['designers']} designer(s)"
         f" and the prompts behind them (model: {meta.get('model') or '?'}).",
         "Read by the owner before changing a workflow; no workflow, planner or prompt reads this file.", ""]
    if pkg.get("summary"):
        L += ["## Summary", "", pkg["summary"], ""]
    L += ["## Part A · What the workflows should do differently (capability track)", ""]
    if not pkg["workflows"]:
        L += ["No lesson has evidence yet.", ""]
    for w in pkg["workflows"]:
        L += [f"### {WORKFLOW_WORDS.get(w['workflow'], w['workflow'])} (`{w['workflow']}`)", ""]
        for les in w["lessons"]:
            L += [f"- **{les['lesson']}** ({les['confidence']}; evidence: {', '.join(les['evidence'])})",
                  f"  - suggested change: {les['suggested_change']}"]
        L.append("")
    L += ["## Part B · How each designer asks (behaviour track)", ""]
    if not pkg["designers"]:
        L += ["No designer has enough records yet.", ""]
    for d in pkg["designers"]:
        L += [f"### {d['designer']}", ""]
        if d["asks_for"]:
            L += ["- asks for by default: " + "; ".join(d["asks_for"])]
        if d["phrasing"]:
            L += ["- phrasing to watch: " + "; ".join(d["phrasing"])]
        L += [f"- evidence: {', '.join(d['evidence'])}", ""]
    if pkg["open_questions"]:
        L += ["## Open questions for the designers", ""] + [f"- {q}" for q in pkg["open_questions"]] + [""]
    if corr:
        L += ["## Owner corrections applied", ""] + [f"- {c['created']}: {c['text']}" for c in corr] + [""]
    if meta.get("dropped"):
        L += ["## Dropped by the checks (no evidence in the records)", ""] + [f"- {d}" for d in meta["dropped"]] + [""]
    return "\n".join(L)


# ── the lifecycle ───────────────────────────────────────────────────────────────────────────────

def distill(client=None, log=None, note: str = "") -> dict:
    """Read the records and the corrections, ask the model, check, render, save as the next version."""
    records = feedback.all_records()[-MAX_RECORDS:]
    if not records:
        raise ValueError("no feedback records yet: nothing to distil")
    t0 = time.time()
    client = client or llm.planner_client()
    from .planner import _parse
    corr = corrections()
    user = (f"TODAY: {time.strftime('%A %d %B %Y')}. {len(records)} FEEDBACK RECORDS (ids in brackets):\n\n{traces(records)}")
    if corr:
        user += "\n\nOWNER CORRECTIONS (they outrank the records):\n" + "\n".join(f"- {c['created']}: {c['text']}" for c in corr)
    if log:
        log(f"distilling {len(records)} records...")
    pkg, dropped = _checked(_parse(client.complete(SYSTEM, user, SCHEMA)), records)
    prev = current_version()
    n = (max((int(p.name[1:]) for p in version_dirs()), default=0)) + 1
    meta = {"version": n, "generated": time.strftime("%Y-%m-%d %H:%M:%S"), "records": len(records),
            "designers": len({r["designer"] for r in records}), "record_ids": [r["id"] for r in records],
            "corrections": len(corr), "previous": prev, "model": getattr(client, "last_model", None),
            "seconds": round(time.time() - t0, 1), "dropped": dropped, "note": note}
    d = folder() / f"v{n}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "lessons.json").write_text(json.dumps(pkg, indent=1, ensure_ascii=False))
    (d / "meta.json").write_text(json.dumps(meta, indent=1))
    (d / "LESSONS.md").write_text(render(pkg, meta, corr))
    _set_current(n)
    return load(n)


def correct(text: str, client=None, log=None) -> dict:
    """The owner's correction in plain words: recorded, then a new version distilled with it applied."""
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) < 5:
        raise ValueError("write the correction in a sentence")
    folder().mkdir(parents=True, exist_ok=True)
    with corrections_path().open("a") as f:
        f.write(json.dumps({"id": f"corr-{time.strftime('%Y%m%d-%H%M%S')}", "created": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "text": text[:1000], "version_before": current_version()}, ensure_ascii=False) + "\n")
    return distill(client, log, note=f"correction: {text[:80]}")


def rollback(version: int) -> dict:
    """Make an earlier version the current one; nothing is deleted."""
    if not (folder() / f"v{int(version)}" / "lessons.json").is_file():
        raise ValueError(f"no lessons version {version}")
    _set_current(int(version))
    return load(int(version))


def text(pkg: dict | None) -> str:
    return pkg["markdown"] if pkg else "No lessons yet: run `cbj lessons --distill` once there is feedback."
