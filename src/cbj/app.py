"""The test UI: `cbj ui` serves one page at http://127.0.0.1:8765.

Type a prompt (and attach images), see what the planner understood for each of the case's eight
prompt controls, make the creative, watch it, then write a follow-up prompt to edit it. Every
version keeps its brief, its recording and the proof of what an edit changed.

Jobs run one at a time in a background thread (the game player is a single process); the page
polls their progress.
"""

from __future__ import annotations

import json
import re
import threading
import time
import traceback
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from . import brief as B
from . import planner, studio
from .edits import direct_edit

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="CBJ Creative Studio")
# Local only: requests must name this machine, so a web page cannot reach the API through a
# hostname it controls (DNS rebinding).
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
JOBS: dict[str, dict] = {}
LOCK = threading.Lock()  # one job at a time
UPLOAD_EXT = {".png", ".jpg", ".jpeg", ".webp"}


class PlanRequest(BaseModel):
    prompt: str
    creative_id: str | None = None
    base: int | None = None  # the version to edit (default: the latest)
    uploads: list[str] = []


class MakeRequest(BaseModel):
    prompt: str
    brief: dict
    creative_id: str | None = None
    base: int | None = None
    draft: bool = False


class DirectRequest(BaseModel):
    creative_id: str
    base: int | None = None
    op: dict  # {"picture": slot, "file": name | None} | {"caption": layer, "text": str} | {"sound": bool}
    draft: bool = False


def _job(kind: str, fn, *args) -> str:
    jid = uuid.uuid4().hex[:10]
    job = {"id": jid, "kind": kind, "status": "queued", "stage": "", "lines": [], "result": None, "error": None,
           "started": time.time(), "finished": None}
    JOBS[jid] = job

    def on_line(line):
        job["lines"].append(line)
        job["stage"] = line["stage"]

    def work():
        with LOCK:
            job["status"] = "running"
            try:
                job["result"] = fn(studio.Log(on_line), *args)
                job["status"] = "done"
            except Exception as e:  # shown in the page, with the engine's own message
                job["status"] = "failed"
                job["error"] = str(e)
                job["trace"] = traceback.format_exc()[-2000:]
            job["finished"] = time.time()
    threading.Thread(target=work, daemon=True).start()
    return jid


def _plan(log: studio.Log, req: PlanRequest) -> dict:
    current, inventory = None, None
    if req.creative_id:
        v = studio.parent(req.creative_id, req.base)
        if v is None:
            raise ValueError(f"no creative {req.creative_id}")
        current = {k: x for k, x in v["brief"].items() if k != "planner"}
        inventory = studio.planner_context(req.creative_id, v["n"])
    all_ups = studio.uploads()
    ups = {n: all_ups[n] for n in req.uploads if n in all_ups}
    log.begin("plan", "reading the prompt" + (" as an edit of the current version" if current else "") + "...")
    # the files attached to this prompt are offered to the planner; every upload stays valid, so
    # an edit keeps the images its version already uses
    brief = planner.plan(req.prompt, uploads=ups, sprites=studio.sprite_names(), current=current, available=all_ups,
                         inventory=inventory)
    log(f"planned by {brief['planner']['model']} in {brief['planner']['seconds']} s")
    return brief


def _make(log: studio.Log, req: MakeRequest) -> dict:
    brief = B.check(req.brief, studio.uploads(), studio.sprite_names())
    brief["planner"] = req.brief.get("planner", {})
    brief["changed"] = req.brief.get("changed", [])
    return studio.make(req.prompt, brief, req.creative_id, log, draft=req.draft, base=req.base)


def _preview(log: studio.Log, req: MakeRequest) -> dict:
    brief = B.check(req.brief, studio.uploads(), studio.sprite_names())
    return studio.preview(brief, req.creative_id, log, base=req.base)


def _direct(log: studio.Log, req: DirectRequest) -> dict:
    """An exact edit (a picture, a caption, the sound): the brief is changed in code, no planner."""
    v = studio.parent(req.creative_id, req.base)
    if v is None:
        raise ValueError(f"no creative {req.creative_id}")
    log.begin("plan", "an exact edit: the brief is changed in code (no planner)...")
    brief, words = direct_edit({k: x for k, x in v["brief"].items() if k != "planner"}, req.op, studio.uploads(),
                               studio.sprite_names())
    brief["planner"] = {"model": None, "seconds": 0, "prompt": words, "edit": True, "restored": [], "direct": req.op}
    log(words)
    return studio.make(words, brief, req.creative_id, log, draft=req.draft, base=v["n"])


@app.get("/", response_class=HTMLResponse)
def index():
    return (STATIC / "index.html").read_text()


@app.post("/api/plan")
def api_plan(req: PlanRequest):
    if not req.prompt.strip():
        raise HTTPException(400, "write a prompt first")
    return {"job": _job("plan", _plan, req)}


@app.post("/api/make")
def api_make(req: MakeRequest):
    return {"job": _job("make", _make, req)}


@app.post("/api/preview")
def api_preview(req: MakeRequest):
    return {"job": _job("preview", _preview, req)}


@app.post("/api/direct")
def api_direct(req: DirectRequest):
    return {"job": _job("make", _direct, req)}


@app.get("/api/inventory/{cid}")
def api_inventory(cid: str, base: int | None = None):
    try:
        if studio.parent(cid, base) is None:
            raise ValueError(f"no creative {cid}")
        return studio.inventory(cid, base)
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.get("/api/compare/{cid}")
def api_compare(cid: str, a: int, b: int):
    """The edit report between any two versions of a creative."""
    from .editreport import report
    try:
        va, vb = studio.parent(cid, a), studio.parent(cid, b)
    except ValueError as e:
        raise HTTPException(404, str(e))
    if va is None or vb is None:
        raise HTTPException(404, "no such creative")
    groups = B.changed_groups(va["brief"], vb["brief"])
    # Any two versions: one may not be an edit of the other, so the rows say kept or differs
    # (asked / not asked belongs to an edit and its parent).
    direct = vb.get("from") == va["n"]
    return report(va, vb, studio.STUDIO, vb["brief"].get("changed", []) if direct else groups, compare=not direct)


@app.get("/api/sprite/{name}")
def api_sprite(name: str):
    """A game sprite, for the thumbnails of "Things in this ad"."""
    if name not in studio.sprite_names():
        raise HTTPException(404, "not a game sprite")
    from .draw import PROJECT, SPRITES
    return FileResponse(PROJECT / SPRITES / name)


@app.get("/api/jobs/{jid}")
def api_job(jid: str, since: int = 0):
    job = JOBS.get(jid)
    if not job:
        raise HTTPException(404, "no such job")
    out = {k: v for k, v in job.items() if k != "lines"}
    out["lines"] = job["lines"][since:]
    out["n_lines"] = len(job["lines"])
    out["elapsed"] = round((job["finished"] or time.time()) - job["started"], 1)
    return out


@app.get("/api/creatives")
def api_creatives():
    return studio.creatives()


@app.get("/api/creatives/{cid}")
def api_creative(cid: str):
    try:
        vs = studio.versions(cid)
    except ValueError:
        raise HTTPException(404, "no such creative")
    if not vs:
        raise HTTPException(404, "no such creative")
    return vs


@app.get("/api/meta")
def api_meta():
    return {"controls": B.CONTROL_TITLES, "uploads": sorted(studio.uploads()), "sprites": sorted(studio.sprite_names()),
            "models": list(planner.MODELS), "busy": LOCK.locked(),
            "groups": {g: ctl for g, (ctl, _) in B.GROUPS.items()}}


@app.post("/api/upload")
async def api_upload(files: list[UploadFile] = File(...)):
    folder = studio.STUDIO / "uploads"
    folder.mkdir(parents=True, exist_ok=True)
    names = []
    for f in files:
        ext = Path(f.filename or "").suffix.lower()
        if ext not in UPLOAD_EXT:
            raise HTTPException(400, f"{f.filename}: only PNG, JPG or WebP images")
        stem = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(f.filename).stem)[:40] or "image"
        data = await f.read()
        if len(data) > 15 * 1024 * 1024:
            raise HTTPException(400, f"{f.filename}: larger than 15 MB")
        name = f"{stem}{ext}"
        if (folder / name).exists() and (folder / name).read_bytes() != data:
            name = f"{stem}_{uuid.uuid4().hex[:4]}{ext}"
        (folder / name).write_bytes(data)
        names.append(name)
    return {"uploaded": names}


@app.get("/studio/{path:path}")
def studio_file(path: str):
    p = (studio.STUDIO / path).resolve()
    if not p.is_relative_to(studio.STUDIO.resolve()) or not p.is_file():
        raise HTTPException(404, "not found")
    return FileResponse(p)


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    import uvicorn
    planner.load_env()
    studio.STUDIO.mkdir(exist_ok=True)
    print(f"CBJ Creative Studio: http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="warning")
