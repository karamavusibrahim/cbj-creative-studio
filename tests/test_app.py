"""The test UI's web API, without Unity or the network: the planner and the studio are replaced
by small fakes, and the studio folder points at a temporary one."""

import io
import time

import pytest
from fastapi.testclient import TestClient

from cbj import app as A
from cbj import brief as B
from cbj import studio


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(studio, "STUDIO", tmp_path / "studio")
    (tmp_path / "studio").mkdir()
    A.JOBS.clear()
    return TestClient(A.app)


def wait(client, jid, timeout=10):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/jobs/{jid}").json()
        if j["status"] in ("done", "failed"):
            return j
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_page_and_meta(client):
    assert "CBJ Creative Studio" in client.get("/").text
    meta = client.get("/api/meta").json()
    assert list(meta["controls"]) == list(B.CONTROLS) and meta["busy"] is False


def test_upload_names_are_safe_and_kept_apart(client):
    from PIL import Image
    def tiny(colour):
        buf = io.BytesIO()
        Image.new("RGB", (2, 2), colour).save(buf, "PNG")
        return buf.getvalue()
    png = tiny("red")
    r = client.post("/api/upload", files=[("files", ("../../evil name!.png", io.BytesIO(png), "image/png"))])
    assert r.status_code == 200
    name = r.json()["uploaded"][0]
    assert "/" not in name and ".." not in name and name.endswith(".png")
    assert (studio.STUDIO / "uploads" / name).read_bytes() == png
    # the same name with other bytes does not overwrite the first file
    r2 = client.post("/api/upload", files=[("files", ("evil name!.png", io.BytesIO(tiny("blue")), "image/png"))])
    assert r2.json()["uploaded"][0] != name
    bad = client.post("/api/upload", files=[("files", ("x.svg", io.BytesIO(b"<svg/>"), "image/svg+xml"))])
    assert bad.status_code == 400


def test_studio_files_cannot_escape_the_folder(client):
    (studio.STUDIO / "a.txt").write_text("ok")
    assert client.get("/studio/a.txt").text == "ok"
    assert client.get("/studio/../pyproject.toml").status_code == 404
    assert client.get("/studio/%2e%2e/pyproject.toml").status_code == 404
    # the engine's own stores (feedback, lessons, trend cache) are private: API only
    (studio.STUDIO / "_feedback").mkdir()
    (studio.STUDIO / "_feedback" / "records.jsonl").write_text("{}")
    assert client.get("/studio/_feedback/records.jsonl").status_code == 404
    assert client.get("/studio/x/../_feedback/records.jsonl").status_code == 404


def test_plan_job_reports_the_brief(client, monkeypatch):
    def fake_plan(prompt, uploads=None, sprites=None, current=None, available=None, **kw):
        b = B.check(B.default_brief())
        b["planner"] = {"model": "fake", "seconds": 0.0, "prompt": prompt, "edit": current is not None,
                        "restored": []}
        return b
    monkeypatch.setattr(A.planner, "plan", fake_plan)
    assert client.post("/api/plan", json={"prompt": "  "}).status_code == 400
    jid = client.post("/api/plan", json={"prompt": "a near-fail"}).json()["job"]
    j = wait(client, jid)
    assert j["status"] == "done" and j["result"]["planner"]["prompt"] == "a near-fail"
    assert any("planned by fake" in line["text"] for line in client.get(f"/api/jobs/{jid}").json()["lines"])


def test_a_failed_make_shows_the_engine_message(client, monkeypatch):
    def boom(prompt, brief, cid, log, draft=False, **kw):
        log("trying...")
        raise ValueError("no ad length fits this recording")
    monkeypatch.setattr(A.studio, "make", boom)
    jid = client.post("/api/make", json={"prompt": "x", "brief": B.default_brief()}).json()["job"]
    j = wait(client, jid)
    assert j["status"] == "failed" and "no ad length fits" in j["error"]


def test_editing_an_unknown_creative_fails_cleanly(client):
    jid = client.post("/api/plan", json={"prompt": "change the hook", "creative_id": "nope"}).json()["job"]
    j = wait(client, jid)
    assert j["status"] == "failed" and "no creative nope" in j["error"]
    assert client.get("/api/creatives/nope").status_code == 404


@pytest.mark.parametrize("cid", ["../outside", "..", "a/b", "/abs", "x" * 101, ""])
def test_creative_ids_cannot_reach_outside_the_studio(client, tmp_path, cid):
    victim = tmp_path / "outside" / "v1"
    victim.mkdir(parents=True)
    if cid:
        jid = client.post("/api/make", json={"prompt": "x", "brief": B.default_brief(), "creative_id": cid}).json()["job"]
        j = wait(client, jid)
        assert j["status"] == "failed" and "not a creative id" in j["error"]
    with pytest.raises(ValueError):
        studio.creative_dir(cid)
    assert victim.is_dir()  # nothing outside studio/ was touched


def test_only_local_host_names_are_served(client):
    assert client.get("/api/meta", headers={"host": "evil.example"}).status_code == 400
    assert client.get("/api/meta", headers={"host": "127.0.0.1:8765"}).status_code == 200


def test_level_only_preview_runs_without_recording(client, monkeypatch):
    seen = {}

    def fake_preview(brief, cid, log, **kw):
        seen["brief"] = brief
        log("planned 9 moves")
        return {"level_why": "x", "board": "previews/a.png", "beats": [], "notes": [], "checks": [],
                "controls": brief["controls"]}
    monkeypatch.setattr(A.studio, "preview", fake_preview)
    jid = client.post("/api/preview", json={"prompt": "x", "brief": B.default_brief()}).json()["job"]
    j = wait(client, jid)
    assert j["status"] == "done" and j["result"]["board"] == "previews/a.png"
    assert seen["brief"]["gameplay"]["events"] == []  # the brief went through the engine's checks


# ---- dispatch (2026-10-16): the uploads and the prompt's words decide the workflow

def _dispatch(client, monkeypatch, prompt, uploads):
    called = []
    monkeypatch.setattr(A.create_wf, "plan", lambda log, p, ups: called.append("create") or _planned(p, "create"))
    monkeypatch.setattr(A.guided_wf, "plan", lambda log, p, ups: called.append("guided") or _planned(p, "guided"))
    monkeypatch.setattr(A.image_wf, "plan", lambda log, p, ups: called.append("image_guided") or _planned(p, "image_guided"))
    j = wait(client, client.post("/api/plan", json={"prompt": prompt, "uploads": uploads}).json()["job"])
    assert j["status"] == "done", j.get("error")
    return called


def _planned(prompt, workflow):
    b = B.check(B.default_brief())
    b["planner"] = {"model": "fake", "seconds": 0.0, "prompt": prompt, "edit": False, "restored": [], "workflow": workflow}
    return b


def _uploads(names):
    folder = studio.STUDIO / "uploads"
    folder.mkdir(parents=True, exist_ok=True)
    for n in names:
        (folder / n).write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64 if n.endswith(".mp4") else b"\x89PNG")


def test_a_video_with_a_prompt_goes_to_the_guided_workflow(client, monkeypatch):
    _uploads(["ref.mp4"])
    assert _dispatch(client, monkeypatch, "Based on this video, create a Color Block Jam version of this concept.", ["ref.mp4"]) == ["guided"]
    # a prompt that says nothing about the video still sends it to be read (for its concept)
    assert _dispatch(client, monkeypatch, "A 40-second near-fail ad.", ["ref.mp4"]) == ["guided"]
    assert A.workflow_of("A 40-second near-fail ad.", ["ref.mp4"]) == "guided"


def test_an_image_with_a_reference_prompt_goes_to_image_guided_and_a_picture_to_place_to_create(client, monkeypatch):
    # 2026-10-17 (core requirement 3, rule I2): a reference picture with no video is the image-guided workflow's
    _uploads(["ref.png", "logo.png"])
    assert _dispatch(client, monkeypatch, "Create a Color Block Jam creative inspired by this image.", ["ref.png"]) == ["image_guided"]
    assert _dispatch(client, monkeypatch, "Put our logo (attached) on the end card.", ["logo.png"]) == ["create"]


def test_a_plain_text_prompt_goes_to_the_create_workflow(client, monkeypatch):
    assert _dispatch(client, monkeypatch, "A hard level with a narrow centre and a near-fail.", []) == ["create"]
    assert A.workflow_of("anything", [], creative_id="c") == "edit"


def test_make_follows_the_workflow_that_planned_the_brief(client, monkeypatch):
    made = []
    monkeypatch.setattr(A.create_wf, "make", lambda log, p, b, **kw: made.append("create") or {"id": "x", "n": 1})
    monkeypatch.setattr(A.guided_wf, "make", lambda log, p, b, **kw: made.append("guided") or {"id": "x", "n": 1})
    for wf in ("guided", "create"):
        j = wait(client, client.post("/api/make", json={"prompt": "x", "brief": _planned("x", wf)}).json()["job"])
        assert j["status"] == "done", j.get("error")
    assert made == ["guided", "create"]


def test_a_video_longer_than_120_s_is_refused_at_upload(client, tmp_path):
    import shutil
    import subprocess
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg")
    clip = tmp_path / "long.mp4"
    subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=32x32:r=1:d=125",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(clip)], check=True)
    r = client.post("/api/upload", files=[("files", ("long.mp4", io.BytesIO(clip.read_bytes()), "video/mp4"))])
    assert r.status_code == 400 and "125 s long" in r.json()["detail"] and "120 s" in r.json()["detail"]


def test_make_with_audio_runs_the_soundtrack_step_after_the_workflow(client, monkeypatch):
    from cbj import soundtrack
    from cbj.workflows import create as create_wf
    seen = []
    monkeypatch.setattr(create_wf, "make", lambda log, prompt, brief, **kw: {"id": "c1", "n": 1, "prompt": prompt})
    monkeypatch.setattr(soundtrack, "add_audio", lambda log, v, audio: (seen.append(audio) or {**v, "n": 2, "audio_added": {"file": "s.wav"}}))
    body = {"prompt": "p", "brief": {**B.default_brief(), "controls": [{"control": "x"}]}, "audio": {"bed": True, "voice": True, "line": None}}
    jid = client.post("/api/make", json=body).json()["job"]
    j = wait(client, jid)
    assert j["status"] == "done" and j["result"]["n"] == 2 and j["result"]["audio_added"]["file"] == "s.wav" and seen == [body["audio"]]
    # without audio, or as a draft, the step does not run
    seen.clear()
    jid = client.post("/api/make", json={**body, "audio": None}).json()["job"]
    assert wait(client, jid)["result"]["n"] == 1 and seen == []
    jid = client.post("/api/make", json={**body, "draft": True}).json()["job"]
    assert wait(client, jid)["result"]["n"] == 1 and seen == []


def test_feedback_takes_a_step_and_the_report_endpoint_serves_markdown_and_html(client, tmp_path):
    import json
    cid = "1019-150000-a-test-ad"
    d = tmp_path / "studio" / cid / "v1"
    d.mkdir(parents=True)
    (d / "version.json").write_text(json.dumps({"n": 1, "id": cid, "prompt": "An easy level.", "brief": {"summary": "easy", "controls": [], "planner": {}},
                                                "workflow": "create", "length_s": 30.0, "created": "2026-10-19 12:00:00", "edit": False, "seconds": 10,
                                                "stages": [{"stage": "level", "seconds": 1.0}], "level": {"file": f"{cid}/v1/level.json", "why": "generated", "sha": "x"},
                                                "recording": {"dir": "recordings/x", "reused": False}, "checks": [], "video": f"{cid}/v1/ad/ad.mp4", "ad_dir": f"{cid}/v1/ad"}))
    r = client.post("/api/feedback", json={"area": "level", "kind": "wrong", "wrong": "Too many blocks.", "creative_id": cid, "version": 1,
                                           "page": "create", "step": "level", "item": "Type or structure of the level"})
    assert r.status_code == 200 and r.json()["step"] == "level" and r.json()["process"]["stages"][0]["stage"] == "level"
    fid = r.json()["id"]
    one = client.get(f"/api/feedback/{fid}").json()
    assert one["evidence"]["step"] == "level" and one["analysis"] is None
    assert client.post("/api/feedback", json={"area": "level", "kind": "wrong", "wrong": "x y z", "page": "create", "step": "moon"}).status_code == 400
    assert client.get("/api/feedback/fb-nope").status_code == 404
    md = client.get(f"/api/report/{cid}?version=1")
    assert md.status_code == 200 and md.headers["content-type"].startswith("text/markdown") and "## 1. The request" in md.text and "An easy level." in md.text
    h = client.get(f"/api/report/{cid}?format=html&download=1")
    assert h.status_code == 200 and h.headers["content-type"].startswith("text/html") and "attachment" in h.headers["content-disposition"]
    assert client.get(f"/api/report/{cid}?format=pdf").status_code == 400 and client.get("/api/report/nope").status_code == 404
    meta = client.get("/api/meta").json()["features"]
    assert meta["report"] is True and meta["feedback_steps"]["plan"] == "how the request was read"


def test_a_finished_job_keeps_its_lines_beside_the_version(client, tmp_path, monkeypatch):
    import json
    cid = "1019-150001-a-test-ad"
    d = tmp_path / "studio" / cid / "v1"
    d.mkdir(parents=True)

    def fake_make(log, req):
        log.begin("level", "choosing the level...")
        log("level: generated")
        return {"id": cid, "n": 1, "prompt": req.prompt}
    monkeypatch.setattr(A, "_make", fake_make)
    j = wait(client, client.post("/api/make", json={"prompt": "x", "brief": {"controls": [{}], "level": {}}}).json()["job"])
    assert j["status"] == "done"
    kept = json.loads((d / "log.json").read_text())
    assert kept["kind"] == "make" and [ln["text"] for ln in kept["lines"]] == ["choosing the level...", "level: generated"]

    def fake_plan(log, req):
        log.begin("plan", "reading the prompt...")
        return {"controls": [{}], "level": {}, "planner": {"model": "fake"}}
    monkeypatch.setattr(A, "_plan", fake_plan)
    j = wait(client, client.post("/api/plan", json={"prompt": "x"}).json()["job"])
    assert j["result"]["planner"]["lines"] == [{"stage": "plan", "text": "reading the prompt..."}]


def test_the_requests_own_keys_reach_the_job_and_never_leave_the_engine(client, monkeypatch):
    from cbj import keys
    seen = {}

    def fake_plan(log, req):
        seen.update(keys.current())
        return {"controls": [{}], "level": {}, "planner": {"model": "fake"}}
    monkeypatch.setattr(A, "_plan", fake_plan)
    j = wait(client, client.post("/api/plan", json={"prompt": "x"}, headers={"X-CBJ-Gemini-Key": "g-user", "X-CBJ-Anthropic-Key": "sk-user"}).json()["job"])
    assert j["status"] == "done" and seen == {"gemini": "g-user", "anthropic": "sk-user"}
    assert "keys" not in j and j["own_keys"] == {"gemini": True, "anthropic": True, "planner": "anthropic"}
    assert "g-user" not in client.get(f"/api/jobs/{j['id']}").text and keys.current() == {}
    # without headers: the studio's own configuration, and meta says so
    seen.clear()
    wait(client, client.post("/api/plan", json={"prompt": "x"}).json()["job"])
    assert seen == {}
    meta = client.get("/api/meta").json()
    assert meta["own_keys"] == {"gemini": False, "anthropic": False, "planner": "studio"} and meta["features"]["own_keys"] is True
    mine = client.get("/api/meta", headers={"X-CBJ-Anthropic-Key": "sk-user"}).json()
    assert mine["own_keys"]["anthropic"] is True and mine["backend"] == "anthropic" and mine["models"] == ["anthropic/claude-opus-5-5"]
    assert "sk-user" not in client.get("/api/meta", headers={"X-CBJ-Anthropic-Key": "sk-user"}).text
