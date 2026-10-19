"""`cbj setup-check` (setup_check.py): the readiness of a machine for the studio on its own accounts."""
import json
import subprocess

from cbj import setup_check as S


def test_checks_name_what_is_missing_and_what_to_do(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    for k in ("CBJ_PLANNER", "GEMINI_API_KEY", "NVIDIA_API_KEY", "ANTHROPIC_API_KEY", "TAVILY_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(S.shutil, "which", lambda name: None)
    rows = {r["id"]: r for r in S.checks(env_path=env)}
    assert not rows["env"]["ok"] and "GEMINI_API_KEY" in rows["env"]["do"]
    assert not rows["planner"]["ok"] and "CBJ_PLANNER=claude" in rows["planner"]["do"]  # nvidia by default, no key
    assert not rows["reader"]["ok"] and "aistudio" in rows["reader"]["do"]
    assert not rows["ffmpeg"]["ok"] and rows["ffmpeg"]["do"] == "brew install ffmpeg"
    assert not rows["nvidia"]["required"] and not rows["tavily"]["required"]
    assert not S.ok(list(rows.values())) and "not ready" in S.text(list(rows.values()))


def test_a_logged_in_claude_cli_and_a_gemini_key_make_it_ready(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("CBJ_PLANNER=claude\nGEMINI_API_KEY=g-1\n")
    for k in ("CBJ_PLANNER", "GEMINI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(S.shutil, "which", lambda name: f"/usr/local/bin/{name}")

    def run(args, **kw):
        if args[1:] == ["--version"]:
            return subprocess.CompletedProcess(args, 0, "2.1.283 (Claude Code)\n", "")
        return subprocess.CompletedProcess(args, 0, json.dumps({"loggedIn": True, "authMethod": "claude.ai"}), "")
    monkeypatch.setattr(S.subprocess, "run", run)
    monkeypatch.setattr("cbj.render.PLAYER_APP", tmp_path / "CBJRunner.app")
    (tmp_path / "CBJRunner.app").mkdir()
    rows = {r["id"]: r for r in S.checks(env_path=env)}
    assert rows["planner"]["ok"] and "logged in" in rows["planner"]["what"]
    assert rows["reader"]["ok"] and rows["ffmpeg"]["ok"] and rows["player"]["ok"]
    assert S.ok(list(rows.values())) and "ready: everything" in S.text(list(rows.values()))

    def not_logged(args, **kw):
        if args[1:] == ["--version"]:
            return subprocess.CompletedProcess(args, 0, "2.1.283 (Claude Code)\n", "")
        return subprocess.CompletedProcess(args, 0, json.dumps({"loggedIn": False}), "")
    monkeypatch.setattr(S.subprocess, "run", not_logged)
    rows = {r["id"]: r for r in S.checks(env_path=env)}
    assert not rows["planner"]["ok"] and "log in with your account" in rows["planner"]["do"]
