"""Designer feedback (2026-10-18): what the people using the studio say went wrong, kept as
structured records the owner reads to adjust the agentic workflows by hand.

Why. The case tool will be used by many designers. The workflows are prompt-as-contract code the
owner tunes; the fastest way to find what to tune is to hear, per creative and per version, what a
designer expected and what they got. So every record is a correction record in the sense of
COLLEAGUE.SKILL (Zhou et al., 2026, arXiv:2605.31264, section 4.2): {scene, wrong, correct}, where
the scene is captured by code from the version the designer was looking at (its prompt, workflow,
summary, length), not retyped.

Zero effect, by construction: nothing in the planner, the workflows, the enhancer or the studio
imports this module; a record changes no creative. `tests/test_feedback.py` checks that the pipeline
sources never mention it. The distilled, versioned reading of the records lives in lessons.py.

Storage: one JSON-lines file, studio/_feedback/records.jsonl (append-only; newest last).
API: POST /api/feedback, GET /api/feedback; CLI `cbj feedback [--creative ID] [--designer N] [--md]`.
"""
from __future__ import annotations

import json
import re
import secrets
import time
from pathlib import Path

from . import studio

AREAS = ("level", "ending", "captions", "tempo", "look", "sound", "hud", "hands", "edit", "understanding", "speed",
         "website", "other")
AREA_WORDS = {
    "level": "the level or the board", "ending": "the ending", "captions": "the captions or the hook",
    "tempo": "the tempo or the length", "look": "the look, colours or background", "sound": "the sound or the music",
    "hud": "the HUD (timer, moves, labels)", "hands": "the hand or the pointer", "edit": "an edit that changed too much or too little",
    "understanding": "how the prompt was understood", "speed": "waiting time", "website": "the website itself", "other": "something else",
}
KINDS = ("wrong", "missing", "good", "idea")
PAGES = ("create", "edit", "showcase", "general")
# The step of the process a note is about (2026-10-19): the ids are the engine's own stage names, so a record lines up
# with the stage strip, the log lines and the version's facts; "result" is the whole creative, "other" anything else.
STEPS = ("plan", "level", "recording", "compose", "review", "revise", "proof", "result", "other")
STEP_WORDS = {
    "plan": "how the request was read", "level": "the level (the board)", "recording": "the gameplay (the moves and the clock)",
    "compose": "the video (captions, pictures, end card, sound)", "review": "the viewer's review", "revise": "the automatic revision",
    "proof": "the edit report (what changed, what was kept)", "result": "the whole result", "other": "something else",
}
MAX_TEXT = 1000
MAX_NAME = 40
MAX_ITEM = 200
MAX_LIST = 500
MAX_LINES = 80
MAX_LINE = 240


def folder() -> Path:
    return studio.STUDIO / "_feedback"


def records_path() -> Path:
    return folder() / "records.jsonl"


def clean_name(name: str | None) -> str:
    """A designer's name as they typed it, trimmed to one line; "anonymous" when empty."""
    n = re.sub(r"\s+", " ", (name or "")).strip()[:MAX_NAME]
    return n or "anonymous"


def _text(s: str | None) -> str:
    return re.sub(r"[ \t]+", " ", (s or "")).strip()[:MAX_TEXT]


def scene_of(creative_id: str | None, version: int | None) -> dict:
    """What the designer was looking at, read from the studio (never trusted from the browser)."""
    if not creative_id:
        return {}
    try:
        v = studio.parent(creative_id, version)
    except ValueError:
        v = None
    if v is None:
        raise ValueError(f"no creative {creative_id}" + (f" v{version}" if version else ""))
    history = [{"n": h["n"], "prompt": h["prompt"], "workflow": h.get("workflow", "create")} for h in studio.versions(creative_id)
               if h["n"] <= v["n"]]
    return {"creative_id": creative_id, "version": v["n"], "workflow": v.get("workflow", "create"), "prompt": v["prompt"],
            "summary": (v.get("brief") or {}).get("summary", ""), "length_s": v.get("length_s"), "created": v.get("created"),
            "edit": bool(v.get("edit")), "history": history}


def _short(x, n: int = MAX_LINE) -> str:
    t = re.sub(r"\s+", " ", str(x if x is not None else "")).strip()
    return t if len(t) <= n else t[:n - 1] + "…"


def _lines_of(v: dict) -> list[dict]:
    """The log lines of the job that made this version (studio/<id>/v<n>/log.json, written by the web API when the job
    ends) and the planner's lines kept in the brief (`planner.lines`): what the engine said at every step."""
    out = []
    for ln in ((v.get("brief") or {}).get("planner") or {}).get("lines") or []:
        out.append({"stage": ln.get("stage") or "plan", "text": _short(ln.get("text"))})
    try:
        d = json.loads((studio.STUDIO / v["id"] / f"v{v['n']}" / "log.json").read_text())
        for ln in d.get("lines") or []:
            out.append({"stage": ln.get("stage") or "", "text": _short(ln.get("text"))})
    except (OSError, ValueError, KeyError):
        pass
    if len(out) > MAX_LINES:  # the first and the last lines: the reading and the result
        out = out[:MAX_LINES // 2] + [{"stage": "", "text": f"… {len(out) - MAX_LINES} lines left out …"}] + out[-MAX_LINES // 2:]
    return out


def review_of(v: dict) -> dict:
    """The viewer's review of a version: inline in the record when the workflow attached it, else the version folder's
    review.json (the review is written there first; some records are saved before it is attached)."""
    rv = v.get("review")
    if rv:
        return rv
    try:
        return json.loads((studio.STUDIO / v["id"] / f"v{v['n']}" / "review.json").read_text())
    except (OSError, ValueError, KeyError):
        return {}


def process_of(v: dict | None) -> dict:
    """What the engine did for this version, step by step, captured from the stored version (never from the browser):
    the stages and their seconds, how the request was read (the route, the planner, the control rows that are not
    default, the assumptions), the checks that failed, the edit report's rows and pixel facts, the viewer's review, the
    revision, and the log lines. This is what a feedback record is analysed against (`analyze`)."""
    if not v:
        return {}
    b = v.get("brief") or {}
    pl = b.get("planner") or {}
    rt = pl.get("route") or {}
    proof = v.get("proof") or {}
    rv = review_of(v)
    px = proof.get("pixels") or {}
    checks = v.get("checks") or []
    out = {
        "workflow": v.get("workflow"), "seconds": v.get("seconds"),
        "stages": [{"stage": s.get("stage"), "seconds": s.get("seconds")} for s in v.get("stages") or []],
        "planner": {"model": pl.get("model"), "seconds": pl.get("seconds"), "direct": bool(pl.get("direct")),
                    "route": rt.get("edit_type"), "route_level": rt.get("level_name"),
                    "changed": [str(g) for g in b.get("changed") or []], "restored": pl.get("restored") or []},
        "summary": _short(b.get("summary"), 400),
        "controls": [{"control": r.get("control"), "status": r.get("status"), "asked": _short(r.get("asked")),
                      "plan": _short(r.get("plan"), 400), "why": _short(r.get("why"), 400), "engine": [_short(x) for x in r.get("engine") or []]}
                     for r in b.get("controls") or [] if r.get("status") != "default" or r.get("engine")],
        "assumptions": [_short(a, 400) for a in b.get("assumptions") or []][:12],
        "level": {"why": _short((v.get("level") or {}).get("why"), 400), "edit": (v.get("level") or {}).get("edit")},
        "recording": {"reused": (v.get("recording") or {}).get("reused")},
        "checks": {"passed": sum(1 for c in checks if c.get("status") == "pass"), "failed": sum(1 for c in checks if c.get("status") == "failed"),
                   "misses": [{"check": c.get("check"), "detail": _short(c.get("detail"), 400)} for c in checks if c.get("status") == "failed"]},
        "proof": {"verdict": proof.get("verdict"), "ok": proof.get("ok"),
                  "rows": [{"title": r.get("title"), "status": r.get("status"), "detail": _short(r.get("detail"), 300)} for r in proof.get("rows") or []],
                  "pixels": {k: px.get(k) for k in ("frames_changed", "frames", "layers", "contained", "note", "copied") if k in px}} if proof else None,
        "review": {"overall": rv.get("overall"), "would_download": rv.get("would_download"), "why": _short(rv.get("why"), 400),
                   "not_as_asked": [{"control": m.get("control"), "verdict": m.get("verdict"), "seen": _short(m.get("seen"), 300)}
                                    for m in rv.get("match") or [] if m.get("verdict") in ("no", "partial")],
                   "fixes": [_short(f, 300) for f in rv.get("fixes") or []][:3]} if rv and not rv.get("error") else None,
        "revision": {k: _short((v.get("revision") or {}).get(k), 400) for k in ("status", "why", "error", "feedback")} if v.get("revision") else None,
        "lines": _lines_of(v),
    }
    return out


def add(*, designer: str | None, area: str, kind: str, wrong: str, expected: str | None = None, rating: int | None = None,
        creative_id: str | None = None, version: int | None = None, page: str = "general", step: str | None = None,
        item: str | None = None) -> dict:
    """Validate, capture the scene and the process, append. Returns the stored record. `step`: the part of the process
    the note is about (STEPS); `item`: the exact thing, as the page names it (a control row, a report row, a check, a
    caption), so the analysis knows where to look."""
    if area not in AREAS:
        raise ValueError(f"area must be one of {', '.join(AREAS)}")
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    if page not in PAGES:
        raise ValueError(f"page must be one of {', '.join(PAGES)}")
    if step is not None and step not in STEPS:
        raise ValueError(f"step must be one of {', '.join(STEPS)}")
    wrong, expected = _text(wrong), _text(expected)
    item = _short(item, MAX_ITEM) or None
    if kind != "good" and len(wrong) < 3:
        raise ValueError("say what happened in a few words")
    if rating is not None and not 1 <= int(rating) <= 5:
        raise ValueError("rating is 1 to 5")
    scene = scene_of(creative_id, version)
    process = {}
    if creative_id:
        try:
            process = process_of(studio.parent(creative_id, version))
        except Exception:  # a version with a broken folder: the scene is enough
            process = {}
    rec = {"id": f"fb-{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(2)}", "created": time.strftime("%Y-%m-%d %H:%M:%S"),
           "designer": clean_name(designer), "page": page, "area": area, "kind": kind, "wrong": wrong, "expected": expected,
           "rating": int(rating) if rating is not None else None, "step": step or ("result" if creative_id else None), "item": item,
           "scene": scene, "process": process}
    folder().mkdir(parents=True, exist_ok=True)
    with records_path().open("a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def all_records() -> list[dict]:
    p = records_path()
    if not p.is_file():
        return []
    out = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def listing(creative_id: str | None = None, designer: str | None = None, area: str | None = None, kind: str | None = None,
            limit: int = 100) -> dict:
    """Newest first, with the filters applied and the facets of the whole store (for the owner's page)."""
    recs = all_records()
    facets = {"designers": sorted({r["designer"] for r in recs}), "areas": sorted({r["area"] for r in recs}),
              "kinds": sorted({r["kind"] for r in recs}), "creatives": sorted({r["scene"].get("creative_id") for r in recs if r["scene"].get("creative_id")})}
    if creative_id:
        recs = [r for r in recs if r["scene"].get("creative_id") == creative_id]
    if designer:
        recs = [r for r in recs if r["designer"].lower() == designer.lower()]
    if area:
        recs = [r for r in recs if r["area"] == area]
    if kind:
        recs = [r for r in recs if r["kind"] == kind]
    recs = list(reversed(recs))
    n = len(recs)
    return {"count": n, "total": len(all_records()), "records": recs[:max(1, min(int(limit), MAX_LIST))], **facets}


def markdown(recs: list[dict]) -> str:
    """The records as one Markdown file the owner can read or paste anywhere."""
    lines = [f"# Designer feedback ({len(recs)} records, exported {time.strftime('%Y-%m-%d %H:%M')})", ""]
    for r in recs:
        s = r.get("scene") or {}
        where = f"{s['creative_id']} v{s['version']} ({s.get('workflow', '?')})" if s.get("creative_id") else r.get("page", "general")
        lines.append(f"## {r['id']} · {r['designer']} · {r['kind']} · {AREA_WORDS.get(r['area'], r['area'])}")
        lines.append(f"- when: {r['created']} · about: {where}" + (f" · rating {r['rating']}/5" if r.get("rating") else "")
                     + (f" · step: {STEP_WORDS.get(r['step'], r['step'])}" if r.get("step") else "") + (f" · item: {r['item']}" if r.get("item") else ""))
        an = analysis_of(r["id"])
        if an:
            lines.append(f"- analysis: {an.get('what_happened', '')} Why: {an.get('why', '')} ({an.get('verdict', '')})")
        if s.get("prompt"):
            lines.append(f"- the prompt: {s['prompt']}")
        if r.get("wrong"):
            lines.append(f"- what happened: {r['wrong']}")
        if r.get("expected"):
            lines.append(f"- expected: {r['expected']}")
        lines.append("")
    return "\n".join(lines)


# ── one record against its process: what happened, and why (2026-10-19) ───────────────────────────────────────

def record(record_id: str) -> dict | None:
    return next((r for r in all_records() if r.get("id") == record_id), None)


def analyses_folder() -> Path:
    return folder() / "analyses"


def analysis_of(record_id: str) -> dict | None:
    p = analyses_folder() / f"{record_id}.json"
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


STEP_FACTS = {  # which parts of the process answer a note about each step
    "plan": ("planner", "summary", "controls", "assumptions"), "level": ("level", "checks"), "recording": ("recording", "checks"),
    "compose": ("stages", "checks", "proof"), "review": ("review",), "revise": ("revision", "review"), "proof": ("proof", "planner"),
    "result": ("summary", "controls", "checks", "proof", "review", "revision"), "other": ("stages",),
}
STAGE_OF_STEP = {"plan": ("plan",), "level": ("level",), "recording": ("recording", "play", "moves"), "compose": ("compose",),
                 "review": ("review",), "revise": ("revise",), "proof": ("proof",), "result": (), "other": ()}


def step_evidence(rec: dict) -> dict:
    """The slice of the stored process a note points at: the facts of its step and the engine's lines of that stage
    (all the lines for the whole result). Deterministic; what `analyze` shows the model and what the owner's page lists."""
    pr = rec.get("process") or {}
    step = rec.get("step") or "result"
    facts = {k: pr.get(k) for k in STEP_FACTS.get(step, ()) if pr.get(k) not in (None, [], {}, "")}
    stages = STAGE_OF_STEP.get(step, ())
    lines = [ln for ln in pr.get("lines") or [] if not stages or ln.get("stage") in stages]
    item = (rec.get("item") or "").lower()
    if item:  # the rows that name the item come first
        words = [w for w in re.findall(r"[a-z0-9']+", item) if len(w) > 2]
        hit = lambda t: any(w in str(t).lower() for w in words)  # noqa: E731
        for key in ("controls", "rows"):
            rows = facts.get(key) if key == "controls" else (facts.get("proof") or {}).get("rows") if facts.get("proof") else None
            if rows:
                rows.sort(key=lambda r: 0 if hit(json.dumps(r)) else 1)
        lines = [ln for ln in lines if hit(ln.get("text"))] + [ln for ln in lines if not hit(ln.get("text"))]
    return {"step": step, "words": STEP_WORDS.get(step, step), "item": rec.get("item"), "facts": facts, "lines": lines[:MAX_LINES]}


ANALYSIS_SYSTEM = """You explain, to the owner of an AI tool that makes playable-looking ads for the mobile puzzle game Color Block
Jam, what happened behind one designer's feedback note. The tool reads a prompt into a brief (level, ending, captions, tempo,
look, sound, HUD, hand), builds or copies a level, records the play in the real game, composes the video, has a viewer model
review it, may revise it once or twice, and for an edit writes a report of what changed and what was kept.

How the tool is built (so you do not guess): the recording holds only the gameplay frames, filmed in the real game from a
level file and a list of drags; the captions, the pictures (a logo, the icon beside the hook, the end card's picture and
button, the walls' picture, a block's texture, the cursor), the end card and the sound are composited over those frames
afterwards, so a caption or picture edit reuses the recording and changes only the composited layers; a colour or
background change films the same drags again; only a level or play change records new play. The edit report compares a
version with its parent in nine rows and a frame diff.

You get the note (what the designer saw, what they expected, which step and item it is about) and the EVIDENCE: the stored
facts of that step and the engine's own log lines. Answer from the evidence only; quote the lines you rely on by their text.
Say what happened (the engine's decision or result at that step), why (the rule, the reading or the limit that produced it),
whether it is a SYSTEM fault (the tool did something the request did not ask, or missed something it asked), the designer's
TASTE (the tool did what was asked; the designer wanted something else) or UNCLEAR (the evidence does not say), and the
smallest change that would answer the note, in the owner's terms (which step, which control or rule). confidence is "strong"
when the evidence names the cause, else "thin". Plain words, no marketing, nothing the evidence does not say."""

ANALYSIS_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["what_happened", "why", "verdict", "evidence", "suggested_change", "confidence"],
    "properties": {"what_happened": {"type": "string"}, "why": {"type": "string"},
                   "verdict": {"type": "string", "enum": ["system", "taste", "unclear"]},
                   "evidence": {"type": "array", "items": {"type": "string"}}, "suggested_change": {"type": "string"},
                   "confidence": {"type": "string", "enum": ["strong", "thin"]}},
}


def analyze(record_id: str, client=None, log=None) -> dict:
    """One model call over the record and its step's evidence: what happened, why, system or taste, the smallest change.
    Saved beside the records (studio/_feedback/analyses/<id>.json); the owner asks for it (nothing runs by itself).
    A record without a creative (a note about the website) is explained from its words alone."""
    from . import llm
    from .planner import _parse
    rec = record(record_id)
    if rec is None:
        raise ValueError(f"no feedback record {record_id}")
    ev = step_evidence(rec)
    quoted = [ln["text"] for ln in ev["lines"]]
    t0 = time.time()
    client = client or llm.planner_client()
    s = rec.get("scene") or {}
    user = (f"THE NOTE [{rec['id']}] by {rec['designer']} · kind: {rec['kind']} · area: {AREA_WORDS.get(rec['area'], rec['area'])} · "
            f"step: {ev['words']}" + (f" · item: {rec['item']}" if rec.get("item") else "") + "\n"
            + (f"the request: {s.get('prompt')}\nthe workflow: {s.get('workflow')}\n" if s.get("prompt") else "")
            + f"what happened (the designer): {rec.get('wrong') or '-'}\nexpected: {rec.get('expected') or '-'}\n\n"
            + "EVIDENCE, the stored facts of that step:\n" + json.dumps(ev["facts"], ensure_ascii=False, indent=0)[:9000]
            + "\n\nEVIDENCE, the engine's lines of that stage:\n" + "\n".join(f"- [{ln['stage']}] {ln['text']}" for ln in ev["lines"]))
    if log:
        log(f"analysing {rec['id']} against its {ev['words']}...")
    raw = _parse(client.complete(ANALYSIS_SYSTEM, user, ANALYSIS_SCHEMA))
    cited = [x for x in (raw.get("evidence") or []) if isinstance(x, str)]
    # a quoted line must be one the evidence holds: a line of the log, or words of the facts (the model restates a row as
    # "Gameplay: the same recording": nearly every word of the quote must be in the evidence)
    pool = (json.dumps(ev["facts"], ensure_ascii=False) + " " + " ".join(quoted)).lower()
    pool_words = set(re.findall(r"[a-z0-9']+", pool))

    def _backed(x: str) -> bool:
        if any(q.startswith(x[:60]) or x[:60] in q for q in quoted):
            return True
        words = [w for w in re.findall(r"[a-z0-9']+", x.lower()) if len(w) > 3]
        return bool(words) and sum(w in pool_words for w in words) >= max(2, round(0.8 * len(words)))
    backed = [x for x in cited if _backed(x)]
    out = {"record": rec["id"], "step": ev["step"], "item": rec.get("item"), "what_happened": _short(raw.get("what_happened"), 800),
           "why": _short(raw.get("why"), 800), "verdict": raw.get("verdict") if raw.get("verdict") in ("system", "taste", "unclear") else "unclear",
           "evidence": backed[:8], "unbacked": [x for x in cited if x not in backed][:8],
           "suggested_change": _short(raw.get("suggested_change"), 600), "confidence": raw.get("confidence") if raw.get("confidence") in ("strong", "thin") else "thin",
           "model": getattr(client, "last_model", None), "seconds": round(time.time() - t0, 1), "created": time.strftime("%Y-%m-%d %H:%M:%S")}
    if not backed:
        out["confidence"] = "thin"
    analyses_folder().mkdir(parents=True, exist_ok=True)
    (analyses_folder() / f"{rec['id']}.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    return out


def get(record_id: str) -> dict:
    """One record with its step's evidence and its analysis, if any (the owner's page)."""
    rec = record(record_id)
    if rec is None:
        raise ValueError(f"no feedback record {record_id}")
    return {**rec, "evidence": step_evidence(rec), "analysis": analysis_of(record_id)}
