"""`cbj setup-check`: is this machine ready to run the studio on its own accounts? (2026-10-19)

The engine's planner is whichever `claude` command is logged in on the machine that runs it (CBJ_PLANNER=claude), and
the reference-video reader is the GEMINI_API_KEY in cbj-creative/.env. So a new owner needs: Claude Code installed and
logged in with their own account, their own Gemini key in .env, ffmpeg, and the game player built once. This command
checks each one and says what to do; `--live` also makes one tiny call to the planner and to Gemini to prove the login
and the key work. Nothing here changes a file."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REQUIRED = ("env", "planner", "reader", "ffmpeg", "player", "studio")


def _claude_status() -> dict:
    exe = shutil.which("claude")
    if not exe:
        return {"ok": False, "what": "`claude` is not on PATH", "do": "install Claude Code (https://claude.com/claude-code) and run `claude` once to log in"}
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}
    try:
        ver = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=20, env=env).stdout.strip()
        st = subprocess.run([exe, "auth", "status"], capture_output=True, text=True, timeout=30, env=env)
        info = json.loads(st.stdout) if st.stdout.strip().startswith("{") else {}
    except (subprocess.TimeoutExpired, OSError, ValueError) as e:
        return {"ok": False, "what": f"`claude` did not answer: {e}", "do": "run `claude` in a terminal once"}
    if not info.get("loggedIn"):
        return {"ok": False, "what": f"Claude Code {ver} is installed but not logged in", "do": "run `claude` in a terminal and log in with your account"}
    return {"ok": True, "what": f"Claude Code {ver}, logged in ({info.get('authMethod', 'account')})", "do": ""}


def checks(live: bool = False, env_path: Path | None = None) -> list[dict]:
    """Each check: {id, required, ok, what, do}."""
    from .planner import load_env
    env_path = env_path or REPO / ".env"
    load_env(env_path)
    out = []
    out.append({"id": "env", "required": True, "ok": env_path.is_file(), "what": f"{env_path} {'found' if env_path.is_file() else 'missing'}",
                "do": "" if env_path.is_file() else "create cbj-creative/.env with GEMINI_API_KEY=... (and CBJ_PLANNER=claude)"})
    planner = (os.environ.get("CBJ_PLANNER") or "nvidia").strip().lower()
    if planner.startswith("claude"):
        c = _claude_status()
        out.append({"id": "planner", "required": True, "ok": c["ok"], "what": f"CBJ_PLANNER={planner}: {c['what']}", "do": c["do"]})
    elif planner.startswith("anthropic"):
        ok = bool(os.environ.get("ANTHROPIC_API_KEY"))
        out.append({"id": "planner", "required": True, "ok": ok, "what": f"CBJ_PLANNER={planner}: ANTHROPIC_API_KEY {'set' if ok else 'missing'}",
                    "do": "" if ok else "put ANTHROPIC_API_KEY=... in .env, or use your Claude account with CBJ_PLANNER=claude"})
    else:
        ok = bool(os.environ.get("NVIDIA_API_KEY"))
        out.append({"id": "planner", "required": True, "ok": ok, "what": f"CBJ_PLANNER={planner}: NVIDIA_API_KEY {'set' if ok else 'missing'}",
                    "do": "" if ok else "put NVIDIA_API_KEY=... in .env, or set CBJ_PLANNER=claude to use your Claude account"})
    g = bool(os.environ.get("GEMINI_API_KEY"))
    out.append({"id": "reader", "required": True, "ok": g, "what": f"GEMINI_API_KEY {'set' if g else 'missing'} (the reference-video reader)",
                "do": "" if g else "get a key at https://aistudio.google.com/apikey and put GEMINI_API_KEY=... in .env"})
    n = bool(os.environ.get("NVIDIA_API_KEY"))
    out.append({"id": "nvidia", "required": False, "ok": n, "what": f"NVIDIA_API_KEY {'set' if n else 'not set'} (optional: the fallback reader and the voice)", "do": ""})
    t = bool(os.environ.get("TAVILY_API_KEY"))
    out.append({"id": "tavily", "required": False, "ok": t, "what": f"TAVILY_API_KEY {'set' if t else 'not set'} (optional: ideas from trends)", "do": ""})
    ff = shutil.which("ffmpeg")
    out.append({"id": "ffmpeg", "required": True, "ok": bool(ff), "what": f"ffmpeg {ff or 'missing'}", "do": "" if ff else "brew install ffmpeg"})
    try:
        from .render import PLAYER_APP
        built = Path(PLAYER_APP).exists()
        out.append({"id": "player", "required": True, "ok": built, "what": f"the game player {'built' if built else 'not built'} ({PLAYER_APP})",
                    "do": "" if built else "uv run cbj build-player (Unity 6000.3.5f1 installed once; see README)"})
    except Exception as e:
        out.append({"id": "player", "required": True, "ok": False, "what": f"the game player: {e}", "do": "see README, Setup"})
    try:
        from . import studio
        studio.STUDIO.mkdir(parents=True, exist_ok=True)
        ok = os.access(studio.STUDIO, os.W_OK)
        out.append({"id": "studio", "required": True, "ok": ok, "what": f"studio folder {studio.STUDIO} {'writable' if ok else 'not writable'}", "do": ""})
    except Exception as e:
        out.append({"id": "studio", "required": True, "ok": False, "what": f"studio folder: {e}", "do": ""})
    web_env = REPO / "web" / ".env.local"
    out.append({"id": "web", "required": False, "ok": web_env.is_file(), "what": f"web/.env.local {'found' if web_env.is_file() else 'not set'} (optional: the site, ENGINE_URL=http://127.0.0.1:8765)", "do": ""})
    if live:
        out += live_checks()
    return out


def live_checks() -> list[dict]:
    """One tiny call each: the planner answers a JSON object; Gemini answers a word."""
    from . import llm
    out = []
    try:
        c = llm.planner_client()
        ans = json.loads(c.complete("Answer with JSON only.", "Return {\"ok\": true}.", {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}))
        out.append({"id": "planner_live", "required": True, "ok": bool(ans.get("ok")), "what": f"the planner answered ({c.last_model})", "do": ""})
    except Exception as e:
        out.append({"id": "planner_live", "required": True, "ok": False, "what": f"the planner did not answer: {str(e)[:200]}", "do": "fix the planner check above"})
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        import urllib.error
        import urllib.request
        from .gemini import URL, models_from_env
        model = models_from_env()[0]
        body = {"contents": [{"parts": [{"text": "Answer with the single word ok."}]}], "generationConfig": {"maxOutputTokens": 5}}
        try:
            req = urllib.request.Request(URL.format(model=model), data=json.dumps(body).encode(), headers={"x-goog-api-key": key, "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                j = json.loads(r.read())
            text = "".join(p.get("text", "") for c in j.get("candidates") or [] for p in (c.get("content") or {}).get("parts") or [])
            out.append({"id": "reader_live", "required": True, "ok": bool(text.strip()), "what": f"Gemini answered ({model})", "do": ""})
        except urllib.error.HTTPError as e:
            out.append({"id": "reader_live", "required": True, "ok": False, "what": f"Gemini answered HTTP {e.code}", "do": "check the key, or the model's quota"})
        except Exception as e:
            out.append({"id": "reader_live", "required": True, "ok": False, "what": f"Gemini did not answer: {str(e)[:200]}", "do": "check the network and the key"})
    return out


def text(rows: list[dict]) -> str:
    lines = []
    for r in rows:
        mark = "ok     " if r["ok"] else ("MISSING" if r["required"] else "-      ")
        lines.append(f"{mark} {r['what']}" + (f"\n          -> {r['do']}" if r["do"] and not r["ok"] else ""))
    missing = [r for r in rows if r["required"] and not r["ok"]]
    lines.append("")
    lines.append("ready: everything required is in place" if not missing else f"not ready: {len(missing)} required item(s) missing (see the arrows)")
    return "\n".join(lines)


def ok(rows: list[dict]) -> bool:
    return not any(r["required"] and not r["ok"] for r in rows)
