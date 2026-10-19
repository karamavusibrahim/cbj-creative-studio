"""Designer feedback (feedback.py) and its distillation into lessons (lessons.py): validation, the captured
scene, the listing, the evidence checks, versions, corrections, rollback, and the zero-effect guarantee."""
import json
import re
from pathlib import Path

import pytest

from cbj import feedback, lessons, studio

SRC = Path(__file__).resolve().parents[1] / "src" / "cbj"


class FakeClient:
    def __init__(self, answer):
        self.answer, self.calls, self.last_model = answer, [], "fake/model"

    def complete(self, system, user, schema):
        self.calls.append(user)
        return json.dumps(self.answer)


@pytest.fixture
def small_studio(tmp_path, monkeypatch):
    monkeypatch.setattr(studio, "STUDIO", tmp_path / "studio")
    cid = "1018-120000-a-tense-ad"
    for n, prompt, wf in ((1, "A tense ad, near-fail ending, 30 seconds.", "create"), (2, "Make the hurry caption shorter.", "edit")):
        d = tmp_path / "studio" / cid / f"v{n}"
        d.mkdir(parents=True)
        rec = {"n": n, "id": cid, "prompt": prompt, "workflow": wf, "length_s": 30.0, "created": "2026-10-18 12:00:00", "edit": n > 1,
               "seconds": 40.0, "stages": [{"stage": "level", "seconds": 0.0}, {"stage": "recording", "seconds": 20.0}, {"stage": "compose", "seconds": 5.0}],
               "brief": {"summary": "tense near-fail",
                         "controls": [{"control": "concept", "status": "applied", "asked": "a hurry caption", "plan": "Hurry! in the last seconds", "why": None, "engine": []},
                                      {"control": "level", "status": "default", "asked": None, "plan": "the showcase level", "why": None, "engine": []}],
                         "assumptions": ["the clock starts at 30 s"], "changed": ["concept.hurry"] if n > 1 else [],
                         "planner": {"model": "fake/model", "seconds": 3, "lines": [{"stage": "plan", "text": "reading the prompt as an edit of the current version..."}]}},
               "level": {"file": f"{cid}/v{n}/level.json", "why": "the showcase level", "sha": "abc"}, "recording": {"dir": "recordings/x", "reused": n > 1},
               "checks": [{"check": "Rules: the moves", "status": "pass", "detail": "7 drags replayed"},
                          {"check": "Asked: the hurry caption", "status": "failed" if n == 2 else "pass", "detail": "the caption stays 3.2 s"}],
               "video": f"{cid}/v{n}/ad/ad.mp4", "ad_dir": f"{cid}/v{n}/ad"}
        if n > 1:
            rec["from"] = 1
            rec["proof"] = {"verdict": "Only what was asked changed (Captions); everything else is identical.", "ok": True,
                            "rows": [{"title": "Captions", "status": "asked", "detail": "the hurry caption: 'Hurry up now!' -> 'Hurry!'"},
                                     {"title": "Gameplay", "status": "kept", "detail": "the same recording"}],
                            "pixels": {"frames_changed": 60, "frames": 900, "layers": ["cap_hurry"], "contained": True}}
            rec["review"] = {"overall": "fix", "would_download": "maybe", "why": "the hurry caption still reads long",
                             "match": [{"control": "captions", "verdict": "partial", "seen": "Hurry! shows for three seconds"}], "fixes": ["shorten the hurry caption's time"]}
            rec["revision"] = {"status": "unchanged", "why": "nothing to change"}
            (d / "log.json").write_text(json.dumps({"kind": "make", "started": 0, "seconds": 40,
                                                    "lines": [{"t": 1, "stage": "compose", "text": "the approved video is patched: 840 of 900 frames copied"},
                                                              {"t": 2, "stage": "review", "text": "review: fix; not as asked: captions"}]}))
        (d / "version.json").write_text(json.dumps(rec))
        (d / "level.json").write_text(json.dumps({"gridWidth": 5, "gridHeight": 6, "timerCount": 30, "GridBlockDatas": [{"blockColor": 0}, {"blockColor": 2}],
                                                  "ExitDatas": [{}, {}], "inactiveCells": []}))
    return cid


def test_a_record_captures_the_scene_from_the_studio(small_studio):
    r = feedback.add(designer="  Ayşe  ", area="captions", kind="wrong", wrong="The hurry caption stayed long.",
                     expected="Three words at most.", rating=2, creative_id=small_studio, version=2, page="edit")
    assert r["designer"] == "Ayşe" and r["id"].startswith("fb-") and r["rating"] == 2
    assert r["scene"]["workflow"] == "edit" and r["scene"]["prompt"] == "Make the hurry caption shorter."
    assert [h["n"] for h in r["scene"]["history"]] == [1, 2]
    again = feedback.add(designer=None, area="website", kind="idea", wrong="A dark mode please.")
    assert again["designer"] == "anonymous" and again["scene"] == {}
    assert feedback.all_records()[-1]["id"] == again["id"]


def test_bad_input_is_refused(small_studio):
    with pytest.raises(ValueError, match="area"):
        feedback.add(designer="a", area="colour", kind="wrong", wrong="x y z")
    with pytest.raises(ValueError, match="kind"):
        feedback.add(designer="a", area="look", kind="meh", wrong="x y z")
    with pytest.raises(ValueError, match="few words"):
        feedback.add(designer="a", area="look", kind="wrong", wrong="x")
    with pytest.raises(ValueError, match="rating"):
        feedback.add(designer="a", area="look", kind="wrong", wrong="too dark", rating=9)
    with pytest.raises(ValueError, match="no creative"):
        feedback.add(designer="a", area="look", kind="wrong", wrong="too dark", creative_id="nope")
    with pytest.raises(ValueError, match="no creative"):
        feedback.add(designer="a", area="look", kind="wrong", wrong="too dark", creative_id=small_studio, version=9)
    assert feedback.add(designer="a", area="look", kind="good", wrong="")["kind"] == "good"  # praise needs no text


def test_listing_filters_and_facets_and_markdown(small_studio):
    feedback.add(designer="Ayşe", area="captions", kind="wrong", wrong="caption long", creative_id=small_studio, page="edit")
    feedback.add(designer="Ben", area="tempo", kind="missing", wrong="no speed-up", creative_id=small_studio, version=1, page="create")
    feedback.add(designer="Ben", area="website", kind="idea", wrong="dark mode")
    r = feedback.listing()
    assert r["count"] == 3 and r["records"][0]["wrong"] == "dark mode" and r["designers"] == ["Ayşe", "Ben"]
    assert r["creatives"] == [small_studio] and set(r["kinds"]) == {"wrong", "missing", "idea"}
    assert feedback.listing(designer="ben")["count"] == 2 and feedback.listing(creative_id=small_studio, area="tempo")["count"] == 1
    assert feedback.listing(limit=1)["count"] == 3 and len(feedback.listing(limit=1)["records"]) == 1
    md = feedback.markdown(r["records"])
    assert "## fb-" in md and "the prompt: Make the hurry caption shorter." in md and "expected" not in md.split("dark mode")[0]


def _records(cid):
    a = feedback.add(designer="Ayşe", area="captions", kind="wrong", wrong="The hurry caption is too long.", creative_id=cid, version=2, page="edit")
    b = feedback.add(designer="Ben", area="captions", kind="wrong", wrong="Hurry caption runs off the screen.", creative_id=cid, version=1, page="create")
    c = feedback.add(designer="Ben", area="tempo", kind="missing", wrong="I asked for a speed-up and got none.", creative_id=cid, version=1, page="create")
    return a, b, c


def test_distill_checks_evidence_versions_and_renders(small_studio):
    a, b, c = _records(small_studio)
    answer = {"summary": "Captions run long.",
              "workflows": [{"workflow": "create", "lessons": [
                  {"lesson": "Hurry captions must stay under four words.", "evidence": [a["id"], b["id"]], "suggested_change": "cap the hurry caption", "confidence": "strong"},
                  {"lesson": "Speed-ups are missed.", "evidence": [c["id"], "fb-fake"], "suggested_change": "read speed-up", "confidence": "strong"},
                  {"lesson": "Invented lesson.", "evidence": ["fb-nope"], "suggested_change": "x", "confidence": "strong"}]}],
              "designers": [{"designer": "ben", "asks_for": ["a speed-up near the end"], "phrasing": ["'runs off the screen'"], "evidence": [c["id"], a["id"]]},
                            {"designer": "Zed", "asks_for": ["x"], "phrasing": [], "evidence": [a["id"]]}],
              "open_questions": ["Which length counts as long?"]}
    client = FakeClient(answer)
    pkg = lessons.distill(client=client)
    assert "FEEDBACK RECORDS" in client.calls[0] and a["id"] in client.calls[0] and "the prompt: Make the hurry caption shorter." in client.calls[0]
    les = pkg["workflows"][0]["lessons"]
    assert [x["confidence"] for x in les] == ["strong", "thin"] and les[1]["evidence"] == [c["id"]]  # fake id dropped, one record = thin
    assert pkg["designers"] == [{"designer": "Ben", "asks_for": ["a speed-up near the end"], "phrasing": ["'runs off the screen'"], "evidence": [c["id"]]}]
    assert any("Invented lesson" in d for d in pkg["meta"]["dropped"]) and any("Zed" in d for d in pkg["meta"]["dropped"])
    assert pkg["meta"]["version"] == 1 and pkg["current"] == 1 and pkg["meta"]["records"] == 3 and pkg["meta"]["designers"] == 2
    md = pkg["markdown"]
    assert md.startswith("# LESSONS v1") and "## Part A" in md and "### text to creative (`create`)" in md and "## Part B" in md
    assert "no workflow, planner or prompt reads this file" in md and "Which length counts as long?" in md
    assert (studio.STUDIO / "_lessons" / "v1" / "LESSONS.md").is_file() and lessons.load()["meta"]["version"] == 1


def test_correct_makes_a_new_version_and_rollback_switches_current(small_studio):
    _records(small_studio)
    base = {"summary": "s", "workflows": [], "designers": [], "open_questions": []}
    client = FakeClient(base)
    lessons.distill(client=client)
    pkg = lessons.correct("The speed-up complaint means the hurry caption, not the tempo.", client=client)
    assert pkg["meta"]["version"] == 2 and pkg["meta"]["corrections"] == 1 and pkg["meta"]["previous"] == 1
    assert "OWNER CORRECTIONS" in client.calls[1] and "hurry caption, not the tempo" in client.calls[1] and "OWNER CORRECTIONS" not in client.calls[0]
    assert "## Owner corrections applied" in pkg["markdown"] and len(pkg["versions"]) == 2
    back = lessons.rollback(1)
    assert back["current"] == 1 and back["meta"]["version"] == 1 and lessons.load()["meta"]["version"] == 1
    assert len(lessons.version_dirs()) == 2  # nothing deleted
    with pytest.raises(ValueError, match="no lessons version"):
        lessons.rollback(7)
    with pytest.raises(ValueError, match="sentence"):
        lessons.correct("no", client=client)


def test_no_records_is_a_plain_error_and_text_without_lessons(small_studio):
    assert lessons.load() is None and "No lessons yet" in lessons.text(None)
    with pytest.raises(ValueError, match="no feedback records"):
        lessons.distill(client=FakeClient({}))


def test_nothing_in_the_pipeline_imports_feedback_or_lessons():
    # report.py reads a version too and is as foreign to the pipeline as feedback.py
    """Zero effect: the workflows, the planner, the studio, the enhancer and the trends never touch these modules."""
    pipeline = [p for p in SRC.rglob("*.py") if p.name not in ("app.py", "cli.py", "feedback.py", "lessons.py", "soundtrack.py", "report.py")]
    assert len(pipeline) > 10
    imp = re.compile(r"^\s*(from \. import [^\n]*\b(feedback|lessons|soundtrack|report)\b|from \.(feedback|lessons|soundtrack|report)\b|from cbj import [^\n]*\b(feedback|lessons|soundtrack|report)\b|"
                     r"from cbj\.(feedback|lessons|soundtrack|report)\b|import cbj\.(feedback|lessons|soundtrack|report)\b)", re.M)
    for p in pipeline:
        assert not imp.search(p.read_text()), f"{p.name} imports feedback, lessons or soundtrack"


def test_a_record_points_at_a_step_and_captures_the_process(small_studio):
    r = feedback.add(designer="Ayşe", area="captions", kind="wrong", wrong="The hurry caption stayed long.", creative_id=small_studio,
                     version=2, page="edit", step="compose", item="the 'hurry' caption")
    assert r["step"] == "compose" and r["item"] == "the 'hurry' caption"
    pr = r["process"]
    assert [s["stage"] for s in pr["stages"]] == ["level", "recording", "compose"] and pr["recording"]["reused"] is True
    assert pr["controls"][0]["control"] == "concept" and all(c["status"] != "default" for c in pr["controls"])
    assert pr["checks"]["failed"] == 1 and pr["checks"]["misses"][0]["check"] == "Asked: the hurry caption"
    assert pr["proof"]["rows"][0]["status"] == "asked" and pr["review"]["not_as_asked"][0]["control"] == "captions"
    assert [ln["stage"] for ln in pr["lines"]] == ["plan", "compose", "review"]  # the planner's lines, then the make's
    with pytest.raises(ValueError, match="step must be"):
        feedback.add(designer=None, area="other", kind="wrong", wrong="xyz", page="general", step="nowhere")
    default = feedback.add(designer=None, area="other", kind="good", wrong="", creative_id=small_studio, version=1, page="create")
    assert default["step"] == "result" and default["process"]["stages"]
    general = feedback.add(designer=None, area="website", kind="idea", wrong="a dark mode", page="general")
    assert general["step"] is None and general["process"] == {}


def test_step_evidence_is_the_slice_of_the_process_the_note_points_at(small_studio):
    r = feedback.add(designer="Ayşe", area="captions", kind="wrong", wrong="The hurry caption stayed long.", creative_id=small_studio,
                     version=2, page="edit", step="review", item="captions")
    ev = feedback.step_evidence(r)
    assert ev["step"] == "review" and set(ev["facts"]) == {"review"} and [ln["stage"] for ln in ev["lines"]] == ["review"]
    r2 = feedback.add(designer="Ayşe", area="captions", kind="wrong", wrong="It read my words wrong.", creative_id=small_studio,
                      version=2, page="edit", step="plan")
    ev2 = feedback.step_evidence(r2)
    assert "controls" in ev2["facts"] and "assumptions" in ev2["facts"] and [ln["stage"] for ln in ev2["lines"]] == ["plan"]
    whole = feedback.step_evidence(feedback.add(designer=None, area="other", kind="wrong", wrong="meh", creative_id=small_studio, version=2, page="edit"))
    assert len(whole["lines"]) == 3  # the whole result: every line


def test_analyze_explains_a_note_from_its_evidence_and_keeps_only_backed_quotes(small_studio):
    r = feedback.add(designer="Ayşe", area="captions", kind="wrong", wrong="The hurry caption stayed long.", expected="Three words at most.",
                     creative_id=small_studio, version=2, page="edit", step="review", item="captions")
    fake = FakeClient({"what_happened": "The viewer saw the hurry caption for three seconds.", "why": "The caption keeps its reading time.",
                       "verdict": "system", "evidence": ["review: fix; not as asked: captions", "a line the evidence does not hold"],
                       "suggested_change": "cap the hurry caption's time on screen", "confidence": "strong"})
    an = feedback.analyze(r["id"], client=fake)
    assert an["verdict"] == "system" and an["evidence"] == ["review: fix; not as asked: captions"] and an["unbacked"] == ["a line the evidence does not hold"]
    assert an["confidence"] == "strong" and "EVIDENCE" in fake.calls[0] and "Hurry! shows for three seconds" in fake.calls[0]
    got = feedback.get(r["id"])
    assert got["analysis"]["what_happened"].startswith("The viewer saw") and got["evidence"]["step"] == "review"
    # an unbacked analysis is thin whatever the model said
    fake2 = FakeClient({"what_happened": "x", "why": "y", "verdict": "taste", "evidence": ["nothing like this"], "suggested_change": "", "confidence": "strong"})
    assert feedback.analyze(r["id"], client=fake2)["confidence"] == "thin"
    with pytest.raises(ValueError, match="no feedback record"):
        feedback.analyze("fb-nope", client=fake)
    # the lessons' traces carry the step and the analysis
    text = lessons.traces([feedback.record(r["id"])])
    assert "about the step: the viewer's review" in text and "the owner's analysis of this note" in text
    md = feedback.markdown(feedback.all_records())
    assert "step: the viewer's review" in md and "analysis:" in md


def test_the_report_lists_every_step_as_markdown_and_html(small_studio):
    from cbj import report
    feedback.add(designer="Ayşe", area="captions", kind="wrong", wrong="The hurry caption stayed long.", creative_id=small_studio, version=2,
                 page="edit", step="compose")
    md, media = report.report(small_studio, 2, "md")
    assert media == "text/markdown"
    for part in ("## 1. The request", "Make the hurry caption shorter.", "## 2. How the request was read", "| prompt control |", "## 3. The steps",
                 "reading the prompt as an edit", "the approved video is patched", "## 4. The level and the play", "5 x 6, 2 blocks in 2 colours",
                 "## 5. The checks", "## 6. The edit report", "Only what was asked changed", "CHANGED WITHOUT BEING ASKED" if False else "changed, as asked",
                 "## 7. The viewer's review", "## 8. The revision", "## 9. Feedback left on this version", "the video (captions, pictures, end card, sound)", "## 10. Files"):
        assert part in md, part
    html_text, media2 = report.report(small_studio, 2, "html")
    assert media2 == "text/html" and html_text.startswith("<!doctype html>") and "<table>" in html_text and "<script" not in html_text
    assert "Make the hurry caption shorter." in html_text
    first, _ = report.report(small_studio, 1, "md")
    assert "## 6. The edit report" not in first and "The engine's lines were not kept" not in first  # v1 has the planner's lines
    assert "## 7. The viewer's review" not in first
    (studio.STUDIO / small_studio / "v1" / "review.json").write_text(json.dumps({"overall": "ship", "would_download": "yes", "why": "crisp"}))
    assert "verdict: ship" in report.report(small_studio, 1, "md")[0]  # a review kept only in its file is read too
    assert feedback.process_of(studio.parent(small_studio, 1))["review"]["overall"] == "ship"
    with pytest.raises(ValueError, match="format"):
        report.report(small_studio, 1, "pdf")
    assert report.filename(small_studio, 2, "html").endswith("-v2-report.html")
