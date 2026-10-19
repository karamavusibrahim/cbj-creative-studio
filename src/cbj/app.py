"""The test UI: `cbj ui` serves one page at http://127.0.0.1:8765.

Type a prompt (and attach images), see what the planner understood for each of the case's eight
prompt controls, make the creative, watch it, then write a follow-up prompt to edit it. Every
version keeps its brief, its recording and the proof of what an edit changed.

Jobs run one at a time in a background thread (the game player is a single process); the page
polls their progress.
"""

from __future__ import annotations

import hmac
import json
import os
import re
import threading
import time
import traceback
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel

from . import brief as B
from . import enhance, feedback, keys, lessons, llm, planner, reference, review, route, soundtrack, studio, trends
from .workflows import create as create_wf
from .workflows import edit as edit_wf
from .workflows import guided as guided_wf
from .workflows import image_guided as image_wf

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="CBJ Creative Studio")
# Local only by default: requests must name this machine, so a web page cannot reach the API through a
# hostname it controls (DNS rebinding). For the deployed site (web/, 2026-10-18) the same engine is reached
# through a tunnel: CBJ_ALLOWED_HOSTS adds the tunnel's host names (comma-separated, "*.trycloudflare.com"),
# CBJ_CORS_ORIGINS lets the site's origin call the API from the browser, and CBJ_API_TOKEN makes every /api
# call except /api/health and /api/sprite/* require "Authorization: Bearer <token>". /studio/* files (videos,
# posters, json) stay open so <video> and <img> tags can load them. Nothing changes when the variables are unset.
_HOSTS = ["127.0.0.1", "localhost", "testserver"] + [h.strip() for h in os.environ.get("CBJ_ALLOWED_HOSTS", "").split(",") if h.strip()]
app.add_middleware(TrustedHostMiddleware, allowed_hosts=_HOSTS)
OPEN_PATHS = ("/api/health", "/api/sprite/")


def api_token() -> str:
    return os.environ.get("CBJ_API_TOKEN", "")


@app.middleware("http")
async def require_token(request, call_next):
    token = api_token()
    path = request.url.path
    if token and path.startswith("/api/") and not path.startswith(OPEN_PATHS) and request.method != "OPTIONS":
        auth = request.headers.get("authorization", "")
        if not (auth.startswith("Bearer ") and hmac.compare_digest(auth[7:], token)):
            return JSONResponse({"detail": "this engine needs its access token (Authorization: Bearer ...)"}, status_code=401)
    return await call_next(request)


_ORIGINS = [o.strip() for o in os.environ.get("CBJ_CORS_ORIGINS", "").split(",") if o.strip()]
if _ORIGINS:  # added last, so it is the outermost layer and a 401 still carries the CORS headers
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(CORSMiddleware, allow_origins=_ORIGINS, allow_methods=["GET", "POST"],
                       allow_headers=["Authorization", "Content-Type", "X-CBJ-Gemini-Key", "X-CBJ-Anthropic-Key", "X-CBJ-Planner"], max_age=600)
JOBS: dict[str, dict] = {}
LOCK = threading.Lock()  # one job at a time
UPLOAD_EXT = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_EXT = {".mp4", ".mov", ".webm", ".m4v"}  # reference videos (case p.6): analysed, never placed in the ad
AUDIO_EXT = set(B.AUDIO_EXT)  # music for the ad
MAX_IMAGE_MB, MAX_VIDEO_MB = 15, 80


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
    review: bool = False  # after making: the viewer's review (review.py), stored with the version
    without_files: bool = False  # make it although the request names files that are not attached
    revise: bool = True  # the loop: evaluate, feed the misses back, make a revised version (up to MAX_REVISIONS rounds)
    audio: dict | None = None  # optional: {"bed": bool, "voice": bool, "voice_name": str|None, "line": str|None} -> soundtrack.add_audio after the make


class EnhanceRequest(BaseModel):
    prompt: str
    creative_id: str | None = None
    base: int | None = None
    uploads: list[str] = []


class TrendsRequest(BaseModel):
    theme: str | None = None
    region: str = "US"
    n: int = 4
    refresh: bool = False
    url: str | None = None  # a link: the page behind it is the only signal (trends.from_link)


class ReviewRequest(BaseModel):
    creative_id: str
    n: int


class FeedbackRequest(BaseModel):
    area: str
    kind: str
    wrong: str = ""
    expected: str | None = None
    rating: int | None = None
    designer: str | None = None
    creative_id: str | None = None
    version: int | None = None
    page: str = "general"
    step: str | None = None  # the step of the process the note is about (feedback.STEPS)
    item: str | None = None  # the exact thing on the page (a control row, a report row, a check, a caption)


class SoundtrackRequest(BaseModel):
    creative_id: str
    version: int | None = None
    voice: bool = False  # speak the hook with NVIDIA Magpie (the `voice` extra + NVIDIA_API_KEY)
    voice_name: str | None = None
    line: str | None = None  # the words to speak instead of the hook caption
    narration: str = "captions"  # "captions": every caption as it appears; "hook": the hook alone


class LessonsRequest(BaseModel):
    action: str  # distill | correct | rollback
    text: str | None = None  # correct: the owner's words
    version: int | None = None  # rollback: the version to return to


class DirectRequest(BaseModel):
    creative_id: str
    base: int | None = None
    op: dict  # {"picture": slot, "file": name | None[, "block": colour for the skin slot]} | {"caption": layer, "text": str} | {"sound": bool} | {"music": name | None}
    draft: bool = False


class _own:
    """The request's own keys (keys.py) set for the model clients while a call runs, then dropped."""

    def __init__(self, request: Request | None):
        self.keys = keys.from_headers(request.headers) if request is not None else {}

    def __enter__(self):
        keys.set_current(self.keys)
        return self.keys

    def __exit__(self, *a):
        keys.clear()


def _job(kind: str, fn, *args, own: dict | None = None) -> str:
    jid = uuid.uuid4().hex[:10]
    job = {"id": jid, "kind": kind, "status": "queued", "stage": "", "lines": [], "result": None, "error": None,
           "started": time.time(), "finished": None, "keys": dict(own or {}), "own_keys": keys.summary(own or {})}
    JOBS[jid] = job

    def on_line(line):
        job["lines"].append(line)
        job["stage"] = line["stage"]

    def work():
        with LOCK:
            job["status"] = "running"
            keys.set_current(job.get("keys"))  # the user's own keys, for this thread and this job only
            try:
                job["result"] = fn(studio.Log(on_line), *args)
                job["status"] = "done"
                _keep_log(job)
            except Exception as e:  # shown in the page, with the engine's own message
                job["status"] = "failed"
                job["error"] = str(e)
                job["trace"] = traceback.format_exc()[-2000:]
            finally:
                keys.clear()
                job.pop("keys", None)  # never kept past the job, never served
            job["finished"] = time.time()
    threading.Thread(target=work, daemon=True).start()
    return jid


def _keep_log(job: dict) -> None:
    """The engine's lines of a job that made a version are kept beside it (studio/<id>/v<n>/log.json), so a feedback
    record can be analysed against what the engine said at each step, and the report can list it (2026-10-19). A plan
    job's lines travel in the brief (`planner.lines`) and reach the version's brief.json through the make."""
    r = job.get("result")
    try:
        if job["kind"] == "plan" and isinstance(r, dict) and isinstance(r.get("planner"), dict):
            r["planner"]["lines"] = [{"stage": ln.get("stage", ""), "text": str(ln.get("text", ""))[:300]} for ln in job["lines"][-60:]]
            return
        if not (isinstance(r, dict) and r.get("id") and r.get("n")):
            return
        vdir = studio.creative_dir(r["id"]) / f"v{r['n']}"
        if not vdir.is_dir():
            return
        (vdir / "log.json").write_text(json.dumps({"kind": job["kind"], "started": job["started"], "seconds": round(time.time() - job["started"], 1),
                                                   "lines": job["lines"]}, ensure_ascii=False))
    except Exception:  # never fail a made version over its log
        pass


def workflow_of(prompt: str, uploads: list[str], creative_id: str | None = None) -> str:
    """Which workflow a new request goes to, from the uploads AND the prompt's words: "edit" when it
    names a creative; "image_guided" when a picture (and no video) is attached and the words make it a
    reference ("inspired by this image", "take the board from this screenshot": image_guided.applies,
    2026-10-17); "guided" when a video is attached to be read; "create" for a prompt alone (or with
    pictures only to place)."""
    if creative_id:
        return "edit"
    if image_wf.applies(prompt, uploads):
        return image_wf.WORKFLOW
    if not any(n in studio.videos() for n in uploads):
        return create_wf.WORKFLOW  # pictures with no reference words are placed (the text workflow), never read by guided
    return guided_wf.WORKFLOW if guided_wf.applies(prompt, uploads) else create_wf.WORKFLOW


def _plan(log: studio.Log, req: PlanRequest) -> dict:
    """Dispatch (2026-10-16): a request that names a creative, or attaches one of the tool's own
    videos with words that ask to change it, is an edit (workflows/edit.py); a new creative with
    media to read (a video, or a reference image) is guided (workflows/guided.py); a prompt alone is
    a creation (workflows/create.py). Since 2026-10-17 a new creative with a reference picture and no
    video is image-guided (workflows/image_guided.py; a video still goes to guided). One of the tool's own MP4s with words that ask for a new
    creative from it ("a version of this concept") is read as a reference (route.upload_intent)."""
    matched = None
    if not req.creative_id:
        matched = edit_wf.match(req.uploads)
        if isinstance(matched, dict) and route.upload_intent(req.prompt) == "create":
            log(f"{matched['upload']} is v{matched['n']} of {matched['creative_id']}, but the request asks for a new creative "
                f"from it, so it is read as a reference")
            matched = None
        elif isinstance(matched, dict):
            req.creative_id, req.base = matched["creative_id"], matched["n"]
            log(f"{matched['upload']} is v{matched['n']} of {matched['creative_id']} (the same bytes): the edit is routed to "
                f"that version's metadata, no video analysis")
    wf = workflow_of(req.prompt, req.uploads, req.creative_id)
    if wf == "edit":
        return edit_wf.plan(log, req.prompt, req.creative_id, req.base, req.uploads, matched=matched)
    if wf == image_wf.WORKFLOW:
        return image_wf.plan(log, req.prompt, req.uploads)
    if wf == guided_wf.WORKFLOW:
        return guided_wf.plan(log, req.prompt, req.uploads)
    return create_wf.plan(log, req.prompt, req.uploads)


def _make(log: studio.Log, req: MakeRequest) -> dict:
    v = _make_version(log, req)
    if req.audio and not req.draft and (req.audio.get("bed", True) or req.audio.get("voice")):
        v = soundtrack.add_audio(log, v, req.audio)  # the optional audio: a soundtrack, then the existing music edit
    return v


def _make_version(log: studio.Log, req: MakeRequest) -> dict:
    if not isinstance(req.brief, dict) or not req.brief.get("controls") or "level" not in req.brief:
        # an empty or half brief (a failed plan posted on) must never become a creative of defaults
        raise ValueError("no plan to make: plan the prompt first (the brief is empty or incomplete)")
    if req.creative_id:
        return edit_wf.make(log, req.prompt, req.brief, req.creative_id, req.base, draft=req.draft, review_on=req.review,
                            without_files=req.without_files, revise=req.revise)
    if (req.brief.get("planner") or {}).get("workflow") == image_wf.WORKFLOW:  # planned by the image-guided workflow
        return image_wf.make(log, req.prompt, req.brief, draft=req.draft, review_on=req.review,
                             without_files=req.without_files, revise=req.revise)
    if (req.brief.get("planner") or {}).get("workflow") == guided_wf.WORKFLOW:  # planned by the guided workflow
        return guided_wf.make(log, req.prompt, req.brief, draft=req.draft, review_on=req.review,
                              without_files=req.without_files, revise=req.revise)
    return create_wf.make(log, req.prompt, req.brief, draft=req.draft, review_on=req.review,
                          without_files=req.without_files, revise=req.revise)


MAX_REVISIONS = create_wf.MAX_REVISIONS


def _review(log: studio.Log, req: ReviewRequest) -> dict:
    v = studio.parent(req.creative_id, req.n)
    if v is None or v.get("n") != req.n:
        raise ValueError(f"no version {req.n} of {req.creative_id}")
    log.begin("review", f"reviewing v{req.n} as a viewer...")
    return review.review(v, v["prompt"], studio.STUDIO, log=log, edit_of=v.get("proof"))


def _preview(log: studio.Log, req: MakeRequest) -> dict:
    brief = B.check(req.brief, studio.uploads(), studio.sprite_names())
    return studio.preview(brief, req.creative_id, log, base=req.base)


def _direct(log: studio.Log, req: DirectRequest) -> dict:
    return edit_wf.direct(log, req.creative_id, req.base, req.op, draft=req.draft)


@app.get("/", response_class=HTMLResponse)
def index():
    return (STATIC / "index.html").read_text()


@app.post("/api/plan")
def api_plan(req: PlanRequest, request: Request):
    if not req.prompt.strip():
        raise HTTPException(400, "write a prompt first")
    return {"job": _job("plan", _plan, req, own=keys.from_headers(request.headers))}


@app.post("/api/make")
def api_make(req: MakeRequest, request: Request):
    return {"job": _job("make", _make, req, own=keys.from_headers(request.headers))}


@app.post("/api/review")
def api_review(req: ReviewRequest, request: Request):
    """The viewer's review of a finished version: does it match the prompt, would a viewer tap."""
    return {"job": _job("review", _review, req, own=keys.from_headers(request.headers))}


@app.post("/api/preview")
def api_preview(req: MakeRequest, request: Request):
    return {"job": _job("preview", _preview, req, own=keys.from_headers(request.headers))}


@app.post("/api/direct")
def api_direct(req: DirectRequest, request: Request):
    return {"job": _job("make", _direct, req, own=keys.from_headers(request.headers))}


@app.post("/api/enhance")
def api_enhance(req: EnhanceRequest, request: Request):
    """The request rewritten in the planner's vocabulary with nothing added (enhance.py). Synchronous: one
    model call, about 10-25 s; it does not take the job lock, so it runs while a creative is being made."""
    with _own(request):
        if not req.prompt.strip():
            raise HTTPException(400, "write a prompt first")
        try:
            return enhance.enhance(req.prompt, req.uploads, req.creative_id, req.base)
        except ValueError as e:
            raise HTTPException(400, str(e))


@app.post("/api/trends")
def api_trends(req: TrendsRequest, request: Request):
    """Ideas from what is trending now, as prompts the engine can make (trends.py). Cached for a few hours."""
    with _own(request):
        try:
            if req.url and req.url.strip():
                return trends.from_link(req.url, req.theme, min(req.n or 2, 3), refresh=req.refresh)
            return trends.discover(req.theme, req.region or "US", req.n, refresh=req.refresh)
        except ValueError as e:
            raise HTTPException(400, str(e))


@app.post("/api/feedback")
def api_feedback(req: FeedbackRequest):
    """A designer's feedback record (feedback.py): the scene is captured from the studio, nothing else changes."""
    try:
        return feedback.add(designer=req.designer, area=req.area, kind=req.kind, wrong=req.wrong, expected=req.expected,
                            rating=req.rating, creative_id=req.creative_id, version=req.version, page=req.page, step=req.step,
                            item=req.item)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/feedback/{fid}")
def api_feedback_one(fid: str):
    """One record with its step's evidence (the stored facts and the engine's lines) and its analysis, if any."""
    try:
        return feedback.get(fid)
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.post("/api/feedback/{fid}/analyze")
def api_feedback_analyze(fid: str, request: Request):
    """The owner asks what happened behind one note: one model call over the record and its step's evidence (10-30 s),
    saved beside the records. Synchronous; nothing runs by itself."""
    with _own(request):
        try:
            return feedback.analyze(fid)
        except ValueError as e:
            raise HTTPException(400, str(e))


@app.get("/api/report/{cid}")
def api_report(cid: str, version: int | None = None, format: str = "md", download: bool = False):
    """The report of one version (report.py): the request, how it was read, every step and its lines, the level and the
    play, the checks, the edit report, the review, the revision, the feedback. Markdown or a standalone HTML page."""
    from fastapi.responses import Response
    from . import report as R
    try:
        v = studio.parent(cid, version)
        if v is None:
            raise HTTPException(404, "no such creative")
        text, media = R.report(cid, version, format)
    except ValueError as e:
        raise HTTPException(400, str(e))
    headers = {"Content-Disposition": f'attachment; filename="{R.filename(cid, v["n"], format)}"'} if download else {}
    return Response(content=text, media_type=media + "; charset=utf-8", headers=headers)


@app.get("/api/feedback")
def api_feedback_list(creative_id: str | None = None, designer: str | None = None, area: str | None = None,
                      kind: str | None = None, limit: int = 100):
    """The owner's list, newest first, with facets."""
    return feedback.listing(creative_id, designer, area, kind, limit)


@app.get("/api/feedback.md")
def api_feedback_md():
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(feedback.markdown(list(reversed(feedback.all_records()))), media_type="text/markdown")


@app.post("/api/soundtrack")
def api_soundtrack(req: SoundtrackRequest, request: Request):
    """A music bed from the version's own concept (soundtrack.py), optionally with the hook spoken. Writes a WAV
    into studio/uploads/ and returns its name; nothing is changed until the music edit uses it. Synchronous, 1-6 s."""
    with _own(request):
        try:
            return soundtrack.make(req.creative_id, req.version, req.voice, req.voice_name, req.line, narration=req.narration)
        except ValueError as e:
            raise HTTPException(400, str(e))
        except Exception as e:  # the TTS service: say what it said
            raise HTTPException(502, f"the voice could not be made: {type(e).__name__}: {str(e)[:200]}")


@app.get("/api/lessons")
def api_lessons(version: int | None = None):
    """The distilled lessons package (lessons.py); {"empty": true} before the first distillation."""
    try:
        return lessons.load(version) or {"empty": True, "versions": [], "current": None, "corrections": lessons.corrections()}
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.post("/api/lessons")
def api_lessons_act(req: LessonsRequest, request: Request):
    """distill (one model call, 20-60 s), correct {text}, rollback {version}. Synchronous; no job lock."""
    with _own(request):
        try:
            if req.action == "distill":
                return lessons.distill()
            if req.action == "correct":
                return lessons.correct(req.text or "")
            if req.action == "rollback":
                if req.version is None:
                    raise ValueError("rollback needs a version")
                return lessons.rollback(req.version)
            raise ValueError("action must be distill, correct or rollback")
        except ValueError as e:
            raise HTTPException(400, str(e))


@app.get("/api/inventory/{cid}")
def api_inventory(cid: str, base: int | None = None):
    try:
        if studio.parent(cid, base) is None:
            raise ValueError(f"no creative {cid}")
        return studio.inventory(cid, base)
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.get("/api/parts/{cid}")
def api_parts(cid: str, base: int | None = None):
    """The parts manifest a version's edits are routed on (parts.py)."""
    try:
        m = studio.parts(cid, base)
    except ValueError as e:
        raise HTTPException(404, str(e))
    if m is None:
        raise HTTPException(404, f"no creative {cid}")
    return m


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
    out = {k: v for k, v in job.items() if k not in ("lines", "keys")}
    out["lines"] = job["lines"][since:]
    out["n_lines"] = len(job["lines"])
    out["elapsed"] = round((job["finished"] or time.time()) - job["started"], 1)
    return out


@app.get("/api/jobs")
def api_jobs():
    """Recent jobs, newest first (the page resumes a running one after a reload)."""
    out = []
    for job in sorted(JOBS.values(), key=lambda j: j["started"], reverse=True)[:20]:
        out.append({k: job[k] for k in ("id", "kind", "status", "stage", "started", "finished")})
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


@app.get("/api/health")
def api_health():
    """Open (no token): is the engine up, is it busy, which planner. The deployed site polls it."""
    return {"ok": True, "busy": LOCK.locked(), **llm.describe_backend()}


@app.get("/api/meta")
def api_meta(request: Request):
    with _own(request) as own:  # the backend as this request would run it (its own keys, or the studio's)
        backend = llm.describe_backend()
    return {"controls": B.CONTROL_TITLES, "uploads": sorted(studio.uploads()), "videos": sorted(studio.videos()),
            "sprites": sorted(studio.sprite_names()), **backend, "busy": LOCK.locked(), "own_keys": keys.summary(own),
            "features": {"enhance": True, "trends": trends.available(), "feedback": True, "lessons": True, "report": True,
                         "own_keys": True,
                         "feedback_steps": feedback.STEP_WORDS,
                         "soundtrack": {"bed": True, "voice": all(soundtrack.voice_available().values())}},
            "groups": {g: ctl for g, (ctl, _) in B.GROUPS.items()}, "group_names": B.GROUP_NAMES}


@app.post("/api/upload")
async def api_upload(files: list[UploadFile] = File(...)):
    folder = studio.STUDIO / "uploads"
    folder.mkdir(parents=True, exist_ok=True)
    names = []
    for f in files:
        ext = Path(f.filename or "").suffix.lower()
        if ext not in UPLOAD_EXT | VIDEO_EXT | AUDIO_EXT:
            raise HTTPException(400, f"{f.filename}: only PNG, JPG or WebP images, an MP4, MOV or WebM video, or "
                                     f"music (WAV, MP3, M4A, AAC, OGG, FLAC)")
        video, audio = ext in VIDEO_EXT, ext in AUDIO_EXT
        stem = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(f.filename).stem)[:40] or ("video" if video else "image")
        data = await f.read()
        limit = MAX_VIDEO_MB if video or audio else MAX_IMAGE_MB
        if len(data) > limit * 1024 * 1024:
            raise HTTPException(400, f"{f.filename}: larger than {limit} MB")
        if audio:
            from .compose import music_seconds
            if music_seconds(data, ext) is None:
                raise HTTPException(400, f"{f.filename}: not a readable sound file")
        elif video:
            if not studio.looks_like_video(data):
                raise HTTPException(400, f"{f.filename}: not a readable video file")
            too_long = _too_long(data, ext, f.filename)
            if too_long:
                raise HTTPException(400, too_long)
        else:
            try:  # the content, not the name: a text file named .png would break the compositor later
                from io import BytesIO
                from PIL import Image
                Image.open(BytesIO(data)).verify()
            except Exception:
                raise HTTPException(400, f"{f.filename}: not a readable image (PNG, JPG or WebP)")
        name = f"{stem}{ext}"
        if (folder / name).exists() and (folder / name).read_bytes() != data:
            name = f"{stem}_{uuid.uuid4().hex[:4]}{ext}"
        (folder / name).write_bytes(data)
        names.append(name)
    return {"uploaded": names}


def _too_long(data: bytes, ext: str, name: str) -> str | None:
    """Why a video upload is refused for its length (a reference is read whole: at most
    reference.MAX_VIDEO_S), or None. A clip ffprobe cannot read is left to the reading, which says so."""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=ext) as tmp:
        tmp.write(data)
        tmp.flush()
        try:
            d = reference.probe_video(Path(tmp.name))["duration_s"]
        except Exception:
            return None
    if d > reference.MAX_VIDEO_S:
        return (f"{name}: the video is {d:.0f} s long; a reference video is read whole and may be at most "
                f"{reference.MAX_VIDEO_S:.0f} s (the case's references are 30-60 s ads): trim it and upload it again")
    return None


@app.get("/studio/{path:path}")
def studio_file(path: str):
    """A creative's files (videos, pictures, JSON) for the pages. Folders starting with "_" (_feedback, _lessons,
    _trends) are the engine's own stores and never served here: their data goes through the token-gated API."""
    p = (studio.STUDIO / path).resolve()
    root = studio.STUDIO.resolve()
    if not p.is_relative_to(root) or not p.is_file() or any(part.startswith("_") for part in p.relative_to(root).parts):
        raise HTTPException(404, "not found")
    return FileResponse(p)


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    import uvicorn
    planner.load_env()
    studio.STUDIO.mkdir(exist_ok=True)
    print(f"CBJ Creative Studio: http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="warning")
