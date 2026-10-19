"""Which model plans the brief.

The planner's whole contract with a model is one call: a system prompt, a user prompt and a JSON
schema in, the JSON text out (`complete`). The reference reader adds one more: a file and a
question in, a description out (`describe`). Two backends meet that contract:

- `nvidia` (default): NVIDIA's hosted Nemotron models (NVIDIA_API_KEY), see planner.NvidiaClient
  and reference.VisionClient.
- `claude`: the Claude Code CLI already logged in on this machine (`claude -p`), run as a
  subprocess with structured output. No API key: it uses the CLI's own login and its usage limit.
  Images are read through the CLI's Read tool; a video still needs the NVIDIA multimodal model.

- `anthropic` (2026-10-19, optional): the Anthropic API with an API key (ANTHROPIC_API_KEY in .env for a
  self-hosted engine, or the user's own key sent per request: keys.py). The same contract, JSON through a
  forced tool call; pictures and video contact sheets as image blocks.

Chosen by CBJ_PLANNER in the environment or in cbj-creative/.env:
    CBJ_PLANNER=nvidia              (default)
    CBJ_PLANNER=claude              (opus, low effort: a brief in about 20 s)
    CBJ_PLANNER=claude:sonnet       (another model alias or id)
    CBJ_PLANNER=claude:opus:medium  (and an effort: low, medium, high)
    CBJ_PLANNER=anthropic           (claude-opus-5-5 on the Anthropic API)
    CBJ_PLANNER=anthropic:claude-sonnet-5-5
A request that brings its own Anthropic key (keys.current()) runs on the API whatever CBJ_PLANNER says.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

DEFAULT_MODEL = "opus"
DEFAULT_EFFORT = "low"
TIMEOUT_S = 400
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
ANTHROPIC_MODEL = "claude-opus-5-5"
ANTHROPIC_MAX_TOKENS = 8000
# Nothing of the machine's Claude Code setup goes into a call: no MCP servers (their tool
# catalogue alone is 200k+ tokens a call), no settings, no memory, no session on disk.
BARE = ("--no-session-persistence", "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
        "--setting-sources", "")


def setting() -> str:
    from . import keys
    from .planner import load_env
    load_env()
    own = keys.anthropic_choice()
    if own:  # this request's own Anthropic key: the API, whatever the studio runs on
        return "anthropic" + (f":{own[1]}" if own[1] else "")
    return (os.environ.get("CBJ_PLANNER") or "nvidia").strip().lower()


def is_anthropic(value: str | None = None) -> bool:
    return (value if value is not None else setting()).startswith("anthropic")


def _anthropic_parts(value: str) -> tuple[str, str]:
    """'anthropic', 'anthropic:claude-sonnet-5-5' -> (key, model). The key: this request's own, else ANTHROPIC_API_KEY."""
    from . import keys
    own = keys.anthropic_choice()
    key = own[0] if own else (os.environ.get("ANTHROPIC_API_KEY") or "")
    if not key:
        raise ValueError("CBJ_PLANNER=anthropic but no ANTHROPIC_API_KEY: set it in the environment or in cbj-creative/.env, "
                         "or send your own key with the request")
    model = value.split(":", 1)[1] if ":" in value and value.split(":", 1)[1] else ANTHROPIC_MODEL
    return key, model


def _claude_parts(value: str) -> tuple[str, str]:
    """'claude', 'claude:sonnet', 'claude:opus:medium' -> (model, effort)."""
    parts = value.split(":")
    model = parts[1] if len(parts) > 1 and parts[1] else DEFAULT_MODEL
    effort = parts[2] if len(parts) > 2 and parts[2] else DEFAULT_EFFORT
    return model, effort


def is_claude(value: str | None = None) -> bool:
    return (value if value is not None else setting()).startswith("claude")


def describe_backend() -> dict:
    """For /api/meta and the UI's footer: {"backend", "models"}."""
    from . import keys
    s = setting()
    own = keys.summary()
    if is_anthropic(s):
        model = s.split(":", 1)[1] if ":" in s and s.split(":", 1)[1] else ANTHROPIC_MODEL
        return {"backend": "anthropic", "models": [f"anthropic/{model}"], "effort": None, "own_keys": own}
    if is_claude(s):
        model, effort = _claude_parts(s)
        return {"backend": "claude", "models": [f"claude-cli/{model}"], "effort": effort, "own_keys": own}
    from .planner import MODELS
    return {"backend": "nvidia", "models": list(MODELS), "own_keys": own}


def planner_client():
    """The brief-planning client for the configured backend."""
    s = setting()
    if is_anthropic(s):
        return AnthropicClient(*_anthropic_parts(s))
    if is_claude(s):
        return ClaudeCliClient(*_claude_parts(s))
    from .planner import NvidiaClient
    return NvidiaClient()


def vision_client():
    """The reference-reading client for the configured backend."""
    s = setting()
    if is_anthropic(s):
        return AnthropicVision(*_anthropic_parts(s))
    if is_claude(s):
        return ClaudeCliVision(*_claude_parts(s))
    from .reference import VisionClient
    return VisionClient()


def _run(args: list[str], user: str, timeout: float = TIMEOUT_S) -> dict:
    """One `claude -p` call; the CLI's result JSON. Errors become ValueError with the CLI's words."""
    exe = shutil.which("claude")
    if not exe:
        raise ValueError("CBJ_PLANNER=claude but the `claude` command is not on PATH (install Claude Code, "
                         "or set CBJ_PLANNER=nvidia)")
    # Not inherited: the variables Claude Code sets in its own terminal, which make a nested
    # `claude` refuse to start.
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}
    try:
        p = subprocess.run([exe, "-p", *BARE, *args, "--output-format", "json"], input=user, capture_output=True,
                           text=True, env=env, timeout=timeout, cwd=str(Path.home()), check=False)
    except subprocess.TimeoutExpired:
        raise ValueError(f"the claude command gave no answer in {timeout:.0f} s") from None
    try:
        out = json.loads(p.stdout)
    except json.JSONDecodeError:
        raise ValueError(f"the claude command failed: {(p.stderr or p.stdout).strip()[:300]!r}") from None
    if out.get("is_error"):
        msg = str(out.get("result") or "")[:300]
        if "login" in msg.lower():
            msg += " (run `claude` once in a terminal and log in, or set CBJ_PLANNER=nvidia)"
        raise ValueError(f"the claude command answered with an error: {msg}")
    return out


class ClaudeCliClient:
    """Chat completion with a JSON schema through `claude -p --json-schema`, no tools."""

    def __init__(self, model: str = DEFAULT_MODEL, effort: str = DEFAULT_EFFORT):
        self.model, self.effort = model, effort
        self.last_model = None
        self.usage: list[dict] = []

    def complete(self, system: str, user: str, schema: dict) -> str:
        out = _run(["--tools", "", "--model", self.model, "--effort", self.effort, "--system-prompt", system,
                    "--json-schema", json.dumps(schema)], user)
        self.last_model = f"claude-cli/{self.model}"
        self.usage.append(out.get("usage") or {})
        structured = out.get("structured_output")
        return json.dumps(structured) if structured is not None else str(out.get("result") or "")


class ClaudeCliVision:
    """A reference image described by the CLI (it reads the file with its Read tool). A video goes
    to the NVIDIA multimodal model when NVIDIA_API_KEY is set; otherwise it is reported unread."""

    SYSTEM = ("You describe one attached file for an ad planner. Read the file with the Read tool, "
              "then answer with the JSON asked for and nothing else.")

    def __init__(self, model: str = DEFAULT_MODEL, effort: str = DEFAULT_EFFORT, timeout: float = TIMEOUT_S):
        self.model, self.effort = model, effort
        self.timeout = timeout  # an optional reading (the likeness row) sets a shorter one: a hung CLI call then costs minutes, not the job
        self.last_model = None

    def describe(self, ask: str, part: dict, path: Path | None = None) -> str:
        if part.get("type") != "image_url" or path is None:
            # a video: a contact sheet (one frame a second, the second under each frame) read with the
            # Read tool, the way the viewer's review reads a finished ad; no video tokens, no second API
            from .review import contact_sheet
            import tempfile
            path = Path(path).resolve()
            tmp = Path(tempfile.mkdtemp(prefix="cbj_ref_"))
            sheet = contact_sheet(path, tmp / "reference_sheet.png", every_s=1.0)
            out = _run(["--tools", "Read", "--add-dir", str(sheet.parent), "--max-turns", "3", "--model", self.model,
                        "--effort", self.effort, "--system-prompt", self.SYSTEM],
                       f"Read the file {sheet} (a contact sheet of the video: one frame per second, left to right, "
                       f"top to bottom, the second written under each frame) and then: {ask}")
            self.last_model = f"claude-cli/{self.model}"
            return str(out.get("result") or "")
        path = Path(path).resolve()
        out = _run(["--tools", "Read", "--add-dir", str(path.parent), "--max-turns", "3", "--model", self.model,
                    "--effort", self.effort, "--system-prompt", self.SYSTEM],
                   f"Read the file {path} and then: {ask}", timeout=self.timeout)
        self.last_model = f"claude-cli/{self.model}"
        return str(out.get("result") or "")


# ── the Anthropic API (an API key: a self-hosted engine's, or the request's own) ─────────────────────────────────

def _anthropic_call(key: str, body: dict, timeout: float = TIMEOUT_S) -> dict:
    import urllib.error
    import urllib.request
    req = urllib.request.Request(ANTHROPIC_URL, data=json.dumps(body).encode(),
                                 headers={"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        text = e.read()[:300].decode(errors="replace")
        if e.code == 401:
            raise ValueError("the Anthropic API refused the key (401): check ANTHROPIC_API_KEY or the key you sent") from None
        raise ValueError(f"the Anthropic API answered HTTP {e.code}: {text}") from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise ValueError(f"the Anthropic API could not be reached: {e}") from None


def _data_url_block(url: str) -> dict:
    import re
    m = re.match(r"data:([^;,]+);base64,(.*)$", url, re.S)
    if not m:
        raise ValueError("the picture is not a base64 data URL")
    return {"type": "image", "source": {"type": "base64", "media_type": m.group(1), "data": m.group(2)}}


class AnthropicClient:
    """Chat completion with a JSON schema through the Messages API: the schema is a tool the model must call, so
    the answer is the tool's input, valid against the schema. No thinking, temperature 0."""

    def __init__(self, key: str, model: str = ANTHROPIC_MODEL):
        self.key, self.model = key, model
        self.last_model = None
        self.usage: list[dict] = []

    def complete(self, system: str, user: str, schema: dict) -> str:
        body = {"model": self.model, "max_tokens": ANTHROPIC_MAX_TOKENS, "temperature": 0, "system": system,
                "messages": [{"role": "user", "content": user}],
                "tools": [{"name": "answer", "description": "The answer, in the shape asked for.", "input_schema": schema}],
                "tool_choice": {"type": "tool", "name": "answer"}}
        out = _anthropic_call(self.key, body)
        self.last_model = f"anthropic/{out.get('model') or self.model}"
        self.usage.append(out.get("usage") or {})
        for block in out.get("content") or []:
            if block.get("type") == "tool_use":
                return json.dumps(block.get("input") or {})
        text = "".join(b.get("text", "") for b in out.get("content") or [] if b.get("type") == "text")
        if not text:
            raise ValueError(f"the Anthropic API gave no answer (stop_reason {out.get('stop_reason')!r})")
        return text


class AnthropicVision:
    """A reference picture (or a video's contact sheet) read through the Messages API as an image block; the
    answer is asked as text (the callers parse the JSON they asked for)."""

    SYSTEM = "You describe one attached picture for an ad planner. Answer with the JSON asked for and nothing else."

    def __init__(self, key: str, model: str = ANTHROPIC_MODEL, timeout: float = TIMEOUT_S):
        self.key, self.model, self.timeout = key, model, timeout
        self.last_model = None

    def describe(self, ask: str, part: dict, path: Path | None = None) -> str:
        import base64
        if part.get("type") == "image_url":
            block = _data_url_block((part.get("image_url") or {}).get("url", ""))
            text = ask
        else:  # a video: a contact sheet, one frame a second with the second under each frame
            import tempfile
            from .review import contact_sheet
            tmp = Path(tempfile.mkdtemp(prefix="cbj_ref_"))
            sheet = contact_sheet(Path(path).resolve(), tmp / "reference_sheet.png", every_s=1.0)
            block = {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                 "data": base64.b64encode(sheet.read_bytes()).decode()}}
            text = ("This is a contact sheet of the video: one frame per second, left to right, top to bottom, the second "
                    "written under each frame. " + ask)
        body = {"model": self.model, "max_tokens": ANTHROPIC_MAX_TOKENS, "temperature": 0, "system": self.SYSTEM,
                "messages": [{"role": "user", "content": [block, {"type": "text", "text": text}]}]}
        out = _anthropic_call(self.key, body, timeout=self.timeout)
        self.last_model = f"anthropic/{out.get('model') or self.model}"
        return "".join(b.get("text", "") for b in out.get("content") or [] if b.get("type") == "text")
