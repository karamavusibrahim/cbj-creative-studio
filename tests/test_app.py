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
    png = b"\x89PNG fake"
    r = client.post("/api/upload", files=[("files", ("../../evil name!.png", io.BytesIO(png), "image/png"))])
    assert r.status_code == 200
    name = r.json()["uploaded"][0]
    assert "/" not in name and ".." not in name and name.endswith(".png")
    assert (studio.STUDIO / "uploads" / name).read_bytes() == png
    # the same name with other bytes does not overwrite the first file
    r2 = client.post("/api/upload", files=[("files", ("evil name!.png", io.BytesIO(b"other"), "image/png"))])
    assert r2.json()["uploaded"][0] != name
    bad = client.post("/api/upload", files=[("files", ("x.svg", io.BytesIO(b"<svg/>"), "image/svg+xml"))])
    assert bad.status_code == 400


def test_studio_files_cannot_escape_the_folder(client):
    (studio.STUDIO / "a.txt").write_text("ok")
    assert client.get("/studio/a.txt").text == "ok"
    assert client.get("/studio/../pyproject.toml").status_code == 404
    assert client.get("/studio/%2e%2e/pyproject.toml").status_code == 404


def test_plan_job_reports_the_brief(client, monkeypatch):
    def fake_plan(prompt, uploads=None, sprites=None, current=None, available=None):
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
    def boom(prompt, brief, cid, log, draft=False):
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
