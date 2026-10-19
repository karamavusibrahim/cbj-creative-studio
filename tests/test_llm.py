"""The planner backend switch (llm.py): NVIDIA by default, the Claude Code CLI on request. The
CLI is a fake executable here: it records its arguments and answers what the test sets."""
import json
import os
import stat
from pathlib import Path

import pytest

from cbj import llm


@pytest.fixture
def fake_claude(tmp_path, monkeypatch):
    """A `claude` on PATH that writes its argv and stdin to files and prints $FAKE_CLAUDE_OUT."""
    exe = tmp_path / "claude"
    exe.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$FAKE_CLAUDE_ARGS\"\ncat > \"$FAKE_CLAUDE_IN\"\n"
                   "printf '%s' \"$FAKE_CLAUDE_OUT\"\n")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_CLAUDE_ARGS", str(tmp_path / "args"))
    monkeypatch.setenv("FAKE_CLAUDE_IN", str(tmp_path / "in"))
    monkeypatch.setenv("CLAUDECODE", "1")  # as inside a Claude Code terminal: must not be passed on

    def answer(obj: dict) -> None:
        monkeypatch.setenv("FAKE_CLAUDE_OUT", json.dumps(obj))

    def args() -> list[str]:
        return (tmp_path / "args").read_text().splitlines()

    return answer, args, tmp_path


def test_backend_setting(monkeypatch):
    monkeypatch.setenv("CBJ_PLANNER", "nvidia")
    assert llm.describe_backend()["backend"] == "nvidia"
    assert not llm.is_claude()
    monkeypatch.setenv("CBJ_PLANNER", "claude")
    assert llm.describe_backend() == {"backend": "claude", "models": ["claude-cli/opus"], "effort": "low",
                                      "own_keys": {"gemini": False, "anthropic": False, "planner": "studio"}}
    monkeypatch.setenv("CBJ_PLANNER", "Claude:sonnet:medium")
    c = llm.planner_client()
    assert isinstance(c, llm.ClaudeCliClient) and (c.model, c.effort) == ("sonnet", "medium")
    assert isinstance(llm.vision_client(), llm.ClaudeCliVision)


def test_complete_uses_structured_output_and_a_bare_cli(fake_claude):
    answer, args, tmp = fake_claude
    answer({"type": "result", "is_error": False, "result": "{\"a\": 1}", "structured_output": {"a": 1},
            "usage": {"input_tokens": 3, "output_tokens": 9}})
    c = llm.ClaudeCliClient("opus", "low")
    text = c.complete("SYSTEM", "USER", {"type": "object", "properties": {"a": {"type": "integer"}}})
    assert json.loads(text) == {"a": 1}
    assert c.last_model == "claude-cli/opus" and c.usage == [{"input_tokens": 3, "output_tokens": 9}]
    a = args()
    assert a[:2] == ["-p", "--no-session-persistence"]
    assert "--strict-mcp-config" in a and "--setting-sources" in a and a[a.index("--setting-sources") + 1] == ""
    assert a[a.index("--tools") + 1] == "" and a[a.index("--model") + 1] == "opus" and a[a.index("--effort") + 1] == "low"
    assert a[a.index("--system-prompt") + 1] == "SYSTEM" and "--json-schema" in a
    assert a[-2:] == ["--output-format", "json"]
    assert (tmp / "in").read_text() == "USER"


def test_cli_errors_are_explained(fake_claude, monkeypatch):
    answer, args, tmp = fake_claude
    answer({"type": "result", "is_error": True, "result": "Not logged in · Please run /login"})
    with pytest.raises(ValueError, match="log in"):
        llm.ClaudeCliClient().complete("s", "u", {})
    monkeypatch.setenv("FAKE_CLAUDE_OUT", "boom, not json")
    with pytest.raises(ValueError, match="failed"):
        llm.ClaudeCliClient().complete("s", "u", {})
    monkeypatch.setenv("PATH", str(tmp / "nowhere"))
    with pytest.raises(ValueError, match="not on PATH"):
        llm.ClaudeCliClient().complete("s", "u", {})


def test_vision_reads_an_image_with_the_read_tool(fake_claude, tmp_path):
    answer, args, tmp = fake_claude
    answer({"type": "result", "is_error": False, "result": "{\"subject\": \"a teal tile\"}"})
    img = tmp_path / "pic.png"
    img.write_bytes(b"\x89PNG")
    v = llm.ClaudeCliVision()
    out = v.describe("Describe it.", {"type": "image_url", "image_url": {"url": "data:..."}}, img)
    assert json.loads(out)["subject"] == "a teal tile"
    a = args()
    assert a[a.index("--tools") + 1] == "Read" and a[a.index("--add-dir") + 1] == str(img.resolve().parent)
    assert str(img.resolve()) in (tmp / "in").read_text()


def test_vision_video_is_read_as_a_contact_sheet(fake_claude, monkeypatch, tmp_path):
    """A video reference on the Claude backend: a contact sheet (one frame a second) read with the
    Read tool, like the viewer's review; no NVIDIA key needed (2026-10-15)."""
    import shutil, subprocess
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg")
    clip = tmp_path / "v.mp4"
    subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=160x90:d=3", "-r", "8",
                    "-pix_fmt", "yuv420p", str(clip)], check=True)
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    seen = {}

    def fake_run(args, user):
        seen["args"], seen["user"] = args, user
        return {"result": '{"what_it_shows": "red"}'}
    monkeypatch.setattr(llm, "_run", fake_run)
    out = llm.ClaudeCliVision().describe("Describe it.", {"type": "video_url", "video_url": {"url": "data:..."}}, clip)
    assert out == '{"what_it_shows": "red"}'
    assert "Read" in seen["args"] and "contact sheet" in seen["user"] and "reference_sheet.png" in seen["user"]
    sheet = Path(seen["user"].split("Read the file ")[1].split(" (")[0])
    assert sheet.is_file()


class _FakeHTTP:
    """A stand-in for urllib.request.urlopen on the Anthropic API: records the request, answers what the test sets."""

    def __init__(self, answer: dict):
        self.answer, self.requests = answer, []

    def __call__(self, req, timeout=None):
        import io
        self.requests.append({"url": req.full_url, "headers": dict(req.header_items()), "body": json.loads(req.data)})
        return io.BytesIO(json.dumps(self.answer).encode())


def test_anthropic_backend_from_env_and_from_the_requests_own_key(monkeypatch):
    from cbj import keys
    keys.clear()
    monkeypatch.setenv("CBJ_PLANNER", "anthropic:claude-sonnet-5-5")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-env")
    d = llm.describe_backend()
    assert d["backend"] == "anthropic" and d["models"] == ["anthropic/claude-sonnet-5-5"] and d["own_keys"]["planner"] == "studio"
    c = llm.planner_client()
    assert isinstance(c, llm.AnthropicClient) and (c.key, c.model) == ("sk-test-env", "claude-sonnet-5-5")
    assert isinstance(llm.vision_client(), llm.AnthropicVision)
    # no key at all: a plain error, not a crash
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        llm.planner_client()
    # the studio runs on the CLI, but THIS request brings its own Anthropic key: the API, the default model
    monkeypatch.setenv("CBJ_PLANNER", "claude")
    keys.set_current({"anthropic": "sk-user", "gemini": "g-user"})
    try:
        assert llm.setting() == "anthropic"
        c = llm.planner_client()
        assert isinstance(c, llm.AnthropicClient) and (c.key, c.model) == ("sk-user", llm.ANTHROPIC_MODEL)
        assert llm.describe_backend()["own_keys"] == {"gemini": True, "anthropic": True, "planner": "anthropic"}
        # the user keeps the studio's planner but brings a Gemini key: the CLI plans, Gemini reads with their key
        keys.set_current({"anthropic": "sk-user", "gemini": "g-user", "planner": "studio"})
        assert isinstance(llm.planner_client(), llm.ClaudeCliClient)
        from cbj.gemini import GeminiVideoClient
        monkeypatch.setenv("GEMINI_API_KEY", "g-studio")
        assert GeminiVideoClient().key == "g-user"
        keys.set_current({"planner": "anthropic:claude-sonnet-5-5", "anthropic": "sk-user"})
        assert llm.planner_client().model == "claude-sonnet-5-5"
    finally:
        keys.clear()
    assert GeminiVideoClient().key == "g-studio"


def test_anthropic_client_asks_through_a_forced_tool_and_reads_images(monkeypatch, tmp_path):
    fake = _FakeHTTP({"model": "claude-opus-5-5", "content": [{"type": "tool_use", "name": "answer", "input": {"hook": "Beat it!"}}],
                      "usage": {"input_tokens": 10, "output_tokens": 4}})
    monkeypatch.setattr("urllib.request.urlopen", fake)
    c = llm.AnthropicClient("sk-x")
    out = c.complete("SYS", "USER", {"type": "object", "properties": {"hook": {"type": "string"}}})
    assert json.loads(out) == {"hook": "Beat it!"} and c.last_model == "anthropic/claude-opus-5-5" and c.usage[0]["output_tokens"] == 4
    r = fake.requests[0]
    assert r["headers"]["X-api-key"] == "sk-x" and r["body"]["tool_choice"] == {"type": "tool", "name": "answer"}
    assert r["body"]["system"] == "SYS" and r["body"]["messages"][0]["content"] == "USER" and r["body"]["tools"][0]["input_schema"]["properties"]["hook"]
    fake.answer = {"model": "claude-opus-5-5", "content": [{"type": "text", "text": "{\"board\": \"5x6\"}"}]}
    v = llm.AnthropicVision("sk-x")
    txt = v.describe("What board?", {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}, tmp_path / "a.png")
    assert txt == '{"board": "5x6"}'
    blk = fake.requests[1]["body"]["messages"][0]["content"][0]
    assert blk == {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "AAAA"}}
    # errors are words, not tracebacks
    import urllib.error
    def refuse(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 401, "unauthorized", {}, __import__("io").BytesIO(b"{}"))
    monkeypatch.setattr("urllib.request.urlopen", refuse)
    with pytest.raises(ValueError, match="refused the key"):
        c.complete("s", "u", {"type": "object"})


def test_keys_from_headers_are_bounded_and_never_a_planner_the_engine_lacks():
    from cbj import keys
    assert keys.from_headers({"x-cbj-gemini-key": " g1 ", "x-cbj-anthropic-key": "a1", "x-cbj-planner": "studio"}) == {"gemini": "g1", "anthropic": "a1"}
    assert keys.from_headers({"x-cbj-planner": "openai", "x-cbj-anthropic-key": "a1"}) == {"anthropic": "a1"}
    assert keys.from_headers({"x-cbj-planner": "Anthropic:claude-sonnet-5-5"}) == {"planner": "Anthropic:claude-sonnet-5-5"}
    assert keys.from_headers({}) == {} and keys.from_headers(None) == {}
    assert keys.anthropic_choice({"anthropic": "a", "planner": "anthropic:m"}) == ("a", "m")
    assert keys.anthropic_choice({"anthropic": "a", "planner": "studio"}) is None and keys.anthropic_choice({}) is None
    assert keys.summary({"gemini": "g"}) == {"gemini": True, "anthropic": False, "planner": "studio"}
