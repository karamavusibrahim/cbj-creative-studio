"""Gemini as the reader of a reference video (2026-10-16): the request the client sends, the tool's data-URL part
as inline data, the backoff, the usage record, the missing key, and reference.video_client's fallback to NVIDIA
build when Gemini fails. HTTP is mocked everywhere: no test reaches the network."""
import io
import json
import shutil
import subprocess
import urllib.error

import pytest

from cbj import gemini as G
from cbj import reference as R

PART = {"type": "video_url", "video_url": {"url": "data:video/mp4;base64,AAAA"}}


def _answer(text='{"ending": "win"}', usage=None):
    return {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}],
            "usageMetadata": usage or {"promptTokenCount": 2600, "candidatesTokenCount": 900, "thoughtsTokenCount": 300}}


def _client(replies, models=("m1", "m2")):
    """A Gemini client whose calls get the replies in order: a dict (the API's JSON) or an int (an HTTP error)."""
    c = G.GeminiVideoClient(models=models, key="test")
    c.calls, c.waits = [], []
    c.sleep = c.waits.append
    replies = list(replies)

    def call(model, body):
        c.calls.append((model, body))
        r = replies.pop(0)
        if isinstance(r, int):
            raise urllib.error.HTTPError("u", r, "busy", {}, io.BytesIO(b'{"error": "high demand"}'))
        return r
    c._call = call
    return c


def test_the_default_order_is_flash_lite_alone(monkeypatch):
    assert G.GEMINI_MODELS == ("gemini-3.5-flash-lite",)  # the owner's order: Flash-Lite, then NVIDIA build
    assert G.GeminiVideoClient(key="test").models == ("gemini-3.5-flash-lite",)
    monkeypatch.setenv("CBJ_GEMINI_MODELS", "gemini-3.5-flash-lite, gemini-3.5-flash")
    assert G.GeminiVideoClient(key="test").models == ("gemini-3.5-flash-lite", "gemini-3.5-flash")


def test_the_request_sends_the_video_inline_with_low_thinking_and_json(monkeypatch):
    seen = {}

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(req, timeout=None):
        seen.update(url=req.full_url, key=req.get_header("X-goog-api-key"), body=json.loads(req.data), timeout=timeout)
        return Response(json.dumps(_answer()).encode())
    monkeypatch.setattr(G.urllib.request, "urlopen", urlopen)
    c = G.GeminiVideoClient(key="secret")
    assert c.describe("Return ONLY JSON", PART) == '{"ending": "win"}' and c.last_model == "gemini-3.5-flash-lite"
    assert seen["url"].endswith("/models/gemini-3.5-flash-lite:generateContent") and seen["key"] == "secret"
    assert seen["timeout"] == 300
    parts = seen["body"]["contents"][0]["parts"]
    assert parts[0] == {"inline_data": {"mime_type": "video/mp4", "data": "AAAA"}} and parts[1] == {"text": "Return ONLY JSON"}
    cfg = seen["body"]["generationConfig"]
    assert cfg == {"responseMimeType": "application/json", "temperature": 0.2, "thinkingConfig": {"thinkingLevel": "low"}}


def test_the_data_url_part_becomes_inline_data():
    assert G.GeminiVideoClient.inline(PART) == {"inline_data": {"mime_type": "video/mp4", "data": "AAAA"}}
    img = {"type": "image_url", "image_url": {"url": "data:image/png;base64,iVBOR"}}
    assert G.GeminiVideoClient.inline(img) == {"inline_data": {"mime_type": "image/png", "data": "iVBOR"}}
    with pytest.raises(ValueError, match="not a base64 data URL"):
        G.GeminiVideoClient.inline({"type": "video_url", "video_url": {"url": "https://example.com/a.mp4"}})


def test_a_busy_model_is_retried_with_backoff_then_answers():
    c = _client([503, _answer()])
    assert c.describe("ask", PART) == '{"ending": "win"}' and c.waits == [10] and c.last_model == "m1"
    assert any("m1: HTTP 503" in e for e in c.errors)
    assert c.usage == [{"model": "m1", "prompt": 2600, "candidates": 900, "thoughts": 300}]
    c = _client([429, 500, 503, 504, _answer()])  # four failures on m1 (three waits), then m2
    assert c.describe("ask", PART) and c.waits == [10, 20, 40] and c.last_model == "m2"
    c = _client([400, _answer()])  # a refusal is not retried: the next model
    assert c.describe("ask", PART) and c.waits == [] and c.last_model == "m2"
    c = _client([_answer(text=""), _answer()])  # an empty answer: the next model
    assert c.describe("ask", PART) and c.last_model == "m2" and any("empty answer" in e for e in c.errors)


def test_every_model_failing_raises_with_the_reasons():
    c = _client([503] * 4, models=("m1",))
    with pytest.raises(ValueError, match="no Gemini model answered"):
        c.describe("ask", PART)
    assert len(c.errors) == 4 and c.waits == [10, 20, 40]


def test_a_missing_key_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr("cbj.planner.load_env", lambda *a, **k: None)
    with pytest.raises(ValueError, match="no GEMINI_API_KEY"):
        G.GeminiVideoClient()


class FakeNvidia:
    def __init__(self, text='{"ending": "near-fail"}'):
        self.text, self.errors, self.last_model, self.asks = text, [], "nvidia/nemotron-3.5-super-vl-120b-a12b", []

    def describe(self, ask, part, path=None):
        self.asks.append(ask)
        return self.text


def test_the_reader_falls_back_to_nvidia_when_every_gemini_model_fails():
    gem = _client([503] * 4, models=("gemini-3.5-flash-lite",))
    nv = FakeNvidia()
    reader = R.VideoReader(gemini=lambda: gem, nvidia=lambda: nv)
    assert reader.describe("ask", PART) == '{"ending": "near-fail"}'
    assert (reader.reader, reader.last_model) == ("nvidia", "nvidia/nemotron-3.5-super-vl-120b-a12b")
    assert len(reader.errors) == 4 and all(e.startswith("gemini-3.5-flash-lite: HTTP 503") for e in reader.errors)
    # Gemini answering: no NVIDIA call, Gemini's usage on the reader
    gem2, nv2 = _client([_answer()], models=("gemini-3.5-flash-lite",)), FakeNvidia()
    reader = R.VideoReader(gemini=lambda: gem2, nvidia=lambda: nv2)
    assert reader.describe("ask", PART) and reader.reader == "gemini" and nv2.asks == [] and reader.usage[0]["thoughts"] == 300


def test_no_gemini_key_reads_with_nvidia_and_says_why(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr("cbj.planner.load_env", lambda *a, **k: None)
    nv = FakeNvidia()
    reader = R.VideoReader(gemini=G.GeminiVideoClient, nvidia=lambda: nv)
    assert reader.describe("ask", PART) and reader.reader == "nvidia"
    assert reader.errors[0].startswith("gemini: no GEMINI_API_KEY")
    reader.describe("ask again", PART)  # the missing key is said once, not on every call
    assert sum(1 for e in reader.errors if "GEMINI_API_KEY" in e) == 1
    nothing = R.VideoReader(gemini=lambda: (_ for _ in ()).throw(ValueError("no key")), nvidia=lambda: (_ for _ in ()).throw(ValueError("no NVIDIA key")))
    with pytest.raises(ValueError, match="no video reader answered"):
        nothing.describe("ask", PART)


def test_read_video_records_the_reader_the_model_and_the_usage(tmp_path, monkeypatch):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg")
    clip = tmp_path / "clip.mp4"
    subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=10:duration=4",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(clip)], check=True)
    notes = {"hook": "Can you clear it?", "ending": "win", "structure": [{"from_s": 0, "to_s": 4, "purpose": "gameplay"}],
             "captions_seen": ["Can you clear it?"], "confidence": 0.9}
    gem = _client([503, _answer(json.dumps(notes))], models=("gemini-3.5-flash-lite",))
    monkeypatch.setattr(R, "_gemini_client", lambda: gem)
    monkeypatch.setattr(R, "nvidia_video_client", lambda: FakeNvidia())
    a = R.read_video(clip, "Make a version of this concept.", measure=lambda p: {"cuts_s": []})
    assert not a.get("error") and a["reader"] == "gemini" and a["model"] == "gemini-3.5-flash-lite"
    assert a["usage"][0] == {"model": "gemini-3.5-flash-lite", "prompt": 2600, "candidates": 900, "thoughts": 300}
    mimes = [c[1]["contents"][0]["parts"][0]["inline_data"]["mime_type"] for c in gem.calls]
    assert any("HTTP 503" in e for e in a["errors"]) and mimes[-2:] == ["video/mp4", "image/jpeg"]  # the clip, then the board's still



def test_the_reader_is_recorded_with_the_model_that_read_the_whole_clip(tmp_path, monkeypatch):
    """v8 (2026-10-16): Gemini read the whole clip, then hit its quota on the ending's second read and NVIDIA answered
    it; the analysis said reader nvidia with model gemini. The reader goes with the whole clip's model; the second read
    keeps its own."""
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg")
    clip = tmp_path / "clip.mp4"
    subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=10:duration=14",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(clip)], check=True)
    notes = {"hook": "Can you clear it?", "ending": "win", "captions_seen": ["Level Completed"], "confidence": 0.9,
             "structure": [{"from_s": 0, "to_s": 10, "purpose": "gameplay"}, {"from_s": 10, "to_s": 14, "purpose": "end_card"}]}
    gem = _client([_answer(json.dumps(notes))] + [429] * 4, models=("gemini-3.5-flash-lite",))
    nv = FakeNvidia(json.dumps({"ending": "win", "last_clock": "00:08", "win_screen": True, "out_of_time_screen": False,
                                "question_caption": "", "why": "Level Completed"}))
    monkeypatch.setattr(R, "_gemini_client", lambda: gem)
    monkeypatch.setattr(R, "nvidia_video_client", lambda: nv)
    a = R.read_video(clip, "Make a version of this concept.", measure=lambda p: {"cuts_s": []})
    assert (a["reader"], a["model"]) == ("gemini", "gemini-3.5-flash-lite")
    assert (a["ending_read"]["reader"], a["ending_read"]["model"]) == ("nvidia", "nvidia/nemotron-3.5-super-vl-120b-a12b")


def _quota_body(quota_id: str, value: str, delay: str) -> bytes:
    """A 429 as the Gemini API sends it (2026-10-17, gemini-3.5-flash-lite's free tier)."""
    return json.dumps({"error": {
        "code": 429, "status": "RESOURCE_EXHAUSTED",
        "message": "You exceeded your current quota, please check your plan and billing details.",
        "details": [
            {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
             "violations": [{"quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests",
                             "quotaId": quota_id, "quotaDimensions": {"location": "global", "model": "gemini-3.5-flash-lite"},
                             "quotaValue": value}]},
            {"@type": "type.googleapis.com/google.rpc.Help", "links": [{"description": "Learn more", "url": "https://ai.google.dev/"}]},
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": delay}]}}).encode()


def _quota_client(replies, models=("gemini-3.5-flash-lite", "gemini-3.5-flash")):
    c = G.GeminiVideoClient(models=models, key="test")
    c.calls, c.waits = [], []
    c.sleep = c.waits.append
    replies = list(replies)

    def call(model, body):
        c.calls.append(model)
        r = replies.pop(0)
        if isinstance(r, bytes):
            raise urllib.error.HTTPError("u", 429, "Too Many Requests", {}, io.BytesIO(r))
        return r
    c._call = call
    return c


def test_a_daily_quota_429_marks_the_model_used_up_for_the_process():
    """2026-10-17: Flash-Lite's free daily quota (500) ran out; every call then waited 10/20/40 s before NVIDIA answered
    and one reading took 27 minutes. A per-day 429 marks the model used up: no backoff, no further calls to it."""
    day = _quota_body("GenerateRequestsPerDayPerProjectPerModel-FreeTier", "500", "79200s")
    c = _quota_client([day, _answer("ok")])
    assert c.describe("ask", PART) == "ok" and c.calls == ["gemini-3.5-flash-lite", "gemini-3.5-flash"] and c.waits == []
    assert c.last_model == "gemini-3.5-flash" and G.EXHAUSTED == {
        "gemini-3.5-flash-lite": "gemini-3.5-flash-lite: daily free quota used up (500 requests)"}
    assert c.errors == ["gemini-3.5-flash-lite: daily free quota used up (500 requests)"]
    # the next reading's client never calls it again, and says so once per reading
    c2 = _quota_client([_answer("two"), _answer("three")])
    assert c2.describe("ask", PART) == "two" and c2.describe("ask", PART) == "three"
    assert c2.calls == ["gemini-3.5-flash", "gemini-3.5-flash"] and c2.errors == [G.EXHAUSTED["gemini-3.5-flash-lite"]]
    # with every model used up, Gemini raises at once and the reader goes to NVIDIA without a wait
    c3 = _quota_client([day], models=("gemini-3.5-flash-lite",))
    with pytest.raises(ValueError, match="daily free quota used up"):
        c3.describe("ask", PART)
    assert c3.calls == [] and c3.waits == []


def test_a_per_minute_429_keeps_the_backoff():
    minute = _quota_body("GenerateRequestsPerMinutePerProjectPerModel-FreeTier", "15", "20s")
    c = _quota_client([minute, minute, _answer("ok")])
    assert c.describe("ask", PART) == "ok" and c.waits == [10, 20] and G.EXHAUSTED == {}
    assert c.calls == ["gemini-3.5-flash-lite"] * 3 and all("HTTP 429" in e for e in c.errors)
    assert G.daily_quota(minute.decode()) is None and G.daily_quota('{"error": "high demand"}') is None
    assert G.daily_quota(_quota_body("GenerateRequestsPerDayPerProjectPerModel-FreeTier", "500", "1s").decode()) == "500 requests"
