"""The report of one version, for a person who wants the intermediate steps (2026-10-19): the request, how it was
read, every step with its seconds and the engine's lines, the level and the play, the checks, the edit report, the
viewer's review, the revision, the feedback left on it, the files. Markdown, or the same as a standalone HTML page.

Why. The Edit workspace shows a designer only what a designer needs (the video, the change, what changed, what was
kept); everything else is here, on demand: `GET /api/report/<creative>?version=N&format=md|html`, CLI `cbj report`.
Zero effect: nothing in the workflows imports this module; it only reads a stored version."""
from __future__ import annotations

import html
import json
import re
import time
from pathlib import Path

from . import brief as B
from . import studio

ROW_WORDS = {"kept": "kept", "asked": "changed, as asked", "side_effect": "changed because of the asked change",
             "not_asked": "CHANGED WITHOUT BEING ASKED", "changed": "differs"}
STAGE_WORDS = {"plan": "Reading the request", "level": "The level", "recording": "The gameplay (recorded in the game)",
               "play": "The moves", "compose": "The video", "proof": "The edit report", "review": "The viewer's review",
               "revise": "The revision", "audio": "The audio", "done": "Done", "": "Notes"}
FORMATS = ("md", "html")


def _lines(v: dict) -> list[dict]:
    from .feedback import _lines_of
    return _lines_of(v)


def _parts(v: dict) -> dict:
    try:
        return json.loads((studio.STUDIO / v["id"] / f"v{v['n']}" / "parts.json").read_text())
    except (OSError, ValueError):
        return {}


def _level_facts(v: dict) -> list[str]:
    out = [f"level: {(v.get('level') or {}).get('why', '')}"]
    try:
        lv = json.loads((studio.STUDIO / v["level"]["file"]).read_text())
        blocks = lv.get("GridBlockDatas") or []
        colours = sorted({B.COLOURS[int(d["blockColor"])].lower() for d in blocks if 0 <= int(d["blockColor"]) < len(B.COLOURS)})
        out.append(f"board: {lv.get('gridWidth')} x {lv.get('gridHeight')}, {len(blocks)} blocks in {len(colours)} colours ({', '.join(colours)}), "
                   f"{len(lv.get('ExitDatas') or [])} doors, {len(lv.get('inactiveCells') or [])} wall cells, the clock {lv.get('timerCount')} s")
    except (OSError, ValueError, KeyError, TypeError):
        pass
    le = (v.get("level") or {}).get("edit")
    if le:
        out.append("the board edit: " + json.dumps(le, ensure_ascii=False)[:300])
    return out


def _md_table(head: list[str], rows: list[list[str]]) -> list[str]:
    esc = lambda x: str(x if x is not None else "").replace("|", "\\|").replace("\n", " ")  # noqa: E731
    return ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(esc(c) for c in r) + " |" for r in rows]


def markdown(cid: str, version: int | None = None) -> str:
    """The report as Markdown (the source of the HTML too)."""
    v = studio.parent(cid, version)
    if v is None:
        raise ValueError(f"no creative {cid}")
    b = v.get("brief") or {}
    pl = b.get("planner") or {}
    parent = studio.parent(cid, v["from"]) if v.get("edit") and v.get("from") else None
    L = [f"# {cid} · version {v['n']}", "",
         f"Made {v.get('created', '')} by the {v.get('workflow', 'create')} workflow in {v.get('seconds', 0):g} s · {v.get('length_s', 0):g} s long"
         + (f" · an edit of v{v['from']}" if v.get("edit") else "") + f" · report written {time.strftime('%Y-%m-%d %H:%M')}", "",
         "## 1. The request", "", f"> {v.get('prompt', '')}", ""]
    if parent:
        L += [f"The version it edits, v{parent['n']}, was made from: \"{parent.get('prompt', '')}\"", ""]
    if pl.get("prompt_english") and pl.get("prompt_original"):
        L += [f"Read through this translation: \"{pl['prompt_english']}\"", ""]
    L += ["## 2. How the request was read", "", b.get("summary", ""), ""]
    rt = pl.get("route") or {}
    if rt.get("edit_type"):
        L += [f"- route: {rt.get('edit_type')} · {rt.get('level_name', '')}" + (f" · {'; '.join(rt.get('notes') or [])}" if rt.get("notes") else ""),
              f"- planned by {pl.get('model') or 'the engine (no planner)'} in {pl.get('seconds', 0)} s" + ("; a direct edit, made in code" if pl.get("direct") else ""),
              f"- field groups the edit declared: {', '.join(B.GROUP_NAMES.get(g, g) for g in b.get('changed') or []) or 'none'}"
              + (f"; restored by the route check: {', '.join(B.GROUP_NAMES.get(g, g) for g in pl.get('restored') or [])}" if pl.get("restored") else ""), ""]
    rows = [[B.CONTROL_TITLES.get(r["control"], r["control"]), r.get("asked") or "not mentioned", r.get("plan") or "", r.get("status", "").replace("_", " "),
             " ".join([r.get("why") or ""] + [f"While making it: {x}" for x in r.get("engine") or []]).strip()] for r in b.get("controls") or []]
    L += _md_table(["prompt control", "asked", "what the tool does", "status", "notes"], rows) + [""]
    if b.get("assumptions"):
        L += ["Assumptions the engine wrote down:", ""] + [f"- {a}" for a in b["assumptions"]] + [""]
    L += ["## 3. The steps", ""]
    L += _md_table(["step", "seconds"], [[STAGE_WORDS.get(s.get("stage"), s.get("stage")), f"{s.get('seconds', 0):g}"] for s in v.get("stages") or []]) + [""]
    rec = v.get("recording") or {}
    L += [f"- the gameplay recording: {'reused from the version before (nothing re-recorded)' if rec.get('reused') else 'recorded in the game for this version'}", ""]
    lines = _lines(v)
    if lines:
        L += ["What the engine said, step by step:", ""]
        stage = None
        for ln in lines:
            if ln.get("stage") != stage:
                stage = ln.get("stage")
                L += ["", f"**{STAGE_WORDS.get(stage, stage or 'notes')}**", ""]
            L.append(f"- {ln.get('text', '')}")
        L.append("")
    else:
        L += ["(The engine's lines were not kept for this version: it was made before the log was stored.)", ""]
    L += ["## 4. The level and the play", ""] + [f"- {x}" for x in _level_facts(v)]
    pm = _parts(v)
    gp = pm.get("gameplay") or {}
    if gp:
        L += [f"- the play: {gp.get('drags')} drags, the game reports '{gp.get('status')}', the ending {gp.get('ending')}, the clock from "
              f"{gp.get('timer_start_s')} s to {gp.get('timer_end_s') if gp.get('timer_end_s') is None else round(gp['timer_end_s'], 1)} s"]
    if pm.get("parts"):
        L += ["- the parts: " + "; ".join(f"{p.get('name')} {p.get('from_s')}-{p.get('to_s')} s" for p in pm["parts"])]
    if pm.get("moments"):
        L += ["", "The moments, in order:", ""] + [f"- {m.get('at_s')} s: {m.get('what')}" for m in pm["moments"][:40]]
    L.append("")
    checks = v.get("checks") or []
    if checks:
        L += ["## 5. The checks", ""] + _md_table(["check", "status", "detail"], [[c.get("check"), c.get("status"), c.get("detail", "")] for c in checks]) + [""]
    proof = v.get("proof") or {}
    if proof:
        L += ["## 6. The edit report (what changed, what was kept)", "", f"**{proof.get('verdict', '')}**", ""]
        L += _md_table(["item", "status", "detail"], [[r.get("title"), ROW_WORDS.get(r.get("status"), r.get("status")), r.get("detail", "")
                                                       + ("" if not r.get("reasons") else " · engine: " + "; ".join(r["reasons"]))] for r in proof.get("rows") or []]) + [""]
        px = proof.get("pixels") or {}
        if px:
            if px.get("frames_changed") is not None:
                L.append(f"- frames: {px['frames_changed']} of {px.get('frames')} changed; layers {', '.join(px.get('layers') or []) or 'none'}; "
                         + ("every changed pixel inside the edited layers' boxes" if px.get("contained") else "SOME CHANGED PIXELS OUTSIDE THE EDITED LAYERS" if px.get("contained") is False else "pixels not compared"))
            if px.get("copied"):
                cp = px["copied"]
                L.append(f"- the video was patched: {cp['frames']} of {cp['of']} frames are the approved video's bytes ({cp['gops_rendered']} of {cp['gops']} GOPs rendered again)")
            if px.get("note"):
                L.append(f"- {px['note']}")
        if proof.get("route"):
            L.append(f"- the route check: {proof['route'].get('evidence', '')}")
        L.append("")
    from .feedback import review_of
    rv = review_of(v)
    if rv and not rv.get("error"):
        L += ["## 7. The viewer's review", "", f"- verdict: {rv.get('overall')} · would download: {rv.get('would_download')}", f"- why: {rv.get('why', '')}"]
        bad = [m for m in rv.get("match") or [] if m.get("verdict") in ("no", "partial")]
        if bad:
            L += ["- not as asked: " + "; ".join(f"{m.get('control')} ({m.get('verdict')}): {m.get('seen', '')}" for m in bad)]
        if rv.get("fixes"):
            L += ["- suggested: " + "; ".join(rv["fixes"][:3])]
        L.append("")
    rev = v.get("revision") or {}
    if rev:
        L += ["## 8. The revision", "", f"- status: {rev.get('status')}" + (f" · {rev.get('why')}" if rev.get("why") else "") + (f" · {rev.get('error')}" if rev.get("error") else "")]
        if rev.get("feedback"):
            L.append(f"- what it was asked to fix: {rev['feedback']}")
        L.append("")
    try:
        from .feedback import STEP_WORDS, all_records, analysis_of
        notes = [r for r in all_records() if (r.get("scene") or {}).get("creative_id") == cid and (r.get("scene") or {}).get("version") == v["n"]]
    except Exception:
        notes = []
    if notes:
        L += ["## 9. Feedback left on this version", ""]
        for r in notes:
            L.append(f"- {r['created']} · {r['designer']} · {r['kind']}" + (f" · {STEP_WORDS.get(r.get('step'), r.get('step'))}" if r.get("step") else "")
                     + (f" · {r['item']}" if r.get("item") else "") + f": {r.get('wrong') or ''}" + (f" (expected: {r['expected']})" if r.get("expected") else ""))
            an = analysis_of(r["id"])
            if an:
                L.append(f"  - the analysis: {an.get('verdict')} ({an.get('confidence')}). {an.get('what_happened', '')} Why: {an.get('why', '')}")
        L.append("")
    L += ["## 10. Files", "", f"- the video: {v.get('video')}", f"- the brief: {cid}/v{v['n']}/brief.json", f"- the level: {v.get('level', {}).get('file')}",
          f"- the recording: {rec.get('dir')}", f"- the ad and its proof: {v.get('ad_dir')}/ad.json, {v.get('ad_dir')}/compose.json", ""]
    return "\n".join(L)


_INLINE = ((re.compile(r"\*\*(.+?)\*\*"), r"<b>\1</b>"), (re.compile(r"`([^`]+)`"), r"<code>\1</code>"))


def _inline(t: str) -> str:
    t = html.escape(t, quote=False)
    for rx, rep in _INLINE:
        t = rx.sub(rep, t)
    return t


def to_html(md: str, title: str) -> str:
    """A small Markdown to HTML: headings, bullet lists, tables, quotes, paragraphs. No dependency, no script."""
    out, i, lines = [], 0, md.splitlines()
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("|") and i + 1 < len(lines) and re.match(r"^\|(---\|)+$", lines[i + 1].replace(" ", "")):
            head = [c.strip() for c in ln.strip("|").split("|")]
            i += 2
            body = []
            while i < len(lines) and lines[i].startswith("|"):
                body.append([c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", lines[i].strip("|"))])
                i += 1
            out.append("<table><thead><tr>" + "".join(f"<th>{_inline(h)}</th>" for h in head) + "</tr></thead><tbody>"
                       + "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>" for r in body) + "</tbody></table>")
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", ln)
        if m:
            out.append(f"<h{len(m.group(1))}>{_inline(m.group(2))}</h{len(m.group(1))}>")
        elif ln.startswith("- ") or ln.startswith("  - "):
            items = []
            while i < len(lines) and (lines[i].startswith("- ") or lines[i].startswith("  - ")):
                sub = lines[i].startswith("  - ")
                items.append(("<li class=sub>" if sub else "<li>") + _inline(lines[i].lstrip()[2:]) + "</li>")
                i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue
        elif ln.startswith("> "):
            out.append(f"<blockquote>{_inline(ln[2:])}</blockquote>")
        elif ln.strip():
            out.append(f"<p>{_inline(ln)}</p>")
        i += 1
    css = ("body{font:15px/1.5 -apple-system,Segoe UI,Helvetica,Arial,sans-serif;max-width:960px;margin:32px auto;padding:0 20px;color:#1b1b1f}"
           "h1{font-size:22px}h2{font-size:17px;margin-top:28px;border-bottom:1px solid #ddd;padding-bottom:4px}table{border-collapse:collapse;width:100%;font-size:13px;margin:8px 0}"
           "th,td{border:1px solid #ddd;padding:5px 7px;vertical-align:top;text-align:left}th{background:#f3f3f7}blockquote{margin:0;padding:8px 12px;background:#f3f3f7;border-left:3px solid #7a5cf0}"
           "li.sub{margin-left:20px;list-style:circle}code{background:#f3f3f7;padding:1px 4px;border-radius:3px}@media print{body{margin:0}}")
    return (f"<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{html.escape(title)}</title><style>{css}</style></head><body>" + "\n".join(out) + "</body></html>")


def report(cid: str, version: int | None = None, fmt: str = "md") -> tuple[str, str]:
    """(text, media type) of the report in `fmt`."""
    if fmt not in FORMATS:
        raise ValueError(f"format must be one of {', '.join(FORMATS)}")
    md = markdown(cid, version)
    if fmt == "md":
        return md, "text/markdown"
    return to_html(md, md.splitlines()[0].lstrip("# ")), "text/html"


def filename(cid: str, version: int, fmt: str) -> str:
    return f"{cid}-v{version}-report.{fmt}"
