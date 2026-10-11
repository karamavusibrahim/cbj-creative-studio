"""The studio: a prompt in, a finished creative out, and edits that change only what was asked.

Each creative is a folder of versions (studio/<id>/v1, v2, ...). A version holds the prompt, the
checked brief, the level, the recording it used, the ad (ad.json, ad.mp4, compose.json) and,
for an edit, the proof of what changed.

The engine is deterministic, so its stages are content-addressed: a recording is stored under a
hash of everything that decides it (studio/recordings/<hash>). An edit that does not touch the
gameplay finds the same recording and only composes again. That is the minimal re-run, and
ad-diff then proves it frame by frame.

Everything the engine had to change in a request is written back into the brief's control rows,
so the UI can show it next to what was asked.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
from pathlib import Path

from . import brief as B
from .ad import END_CARD_S, END_CARD_MAX_S, FPS, Recording, build_ad
from .draw import PROJECT, SPRITES

REPO = Path(__file__).resolve().parents[2]
STUDIO = REPO / "studio"
LEVELS = REPO / "data" / "levels"
NARROW = LEVELS / "gen" / "narrow_center_01.json"
SLOT_ENUM = {"Green": "GREEN", "Yellow": "YELLOW", "Blue": "BLUE", "Red": "RED", "Orange": "ORANGE",
             "Purple": "PURPLE", "DarkGreen": "DARK_GREEN"}
# The HUD's parts, by GameObject name (GameScene: GameCanvas/MainCanvas/MainBar/...). The win
# screen has another "TimeText (1)", which stays.
HUD_TIMER = ("TimerBackground", "TimerImage", "TimeText")
HUD_LEVEL = ("LevelCircle",)


def hud_hide(visuals: dict) -> list[str]:
    if not visuals["hud_timer"] and not visuals["hud_level"]:
        return ["MainBar"]  # the whole bar
    return [*(HUD_TIMER if not visuals["hud_timer"] else ()), *(HUD_LEVEL if not visuals["hud_level"] else ())]
REPLAY_EST_S = 3.0  # room an ad keeps for a replay when it picks the recording's length


def sprite_names() -> set[str]:
    folder = PROJECT / SPRITES
    return {p.name for p in folder.glob("*.png")} if folder.is_dir() else set()


def uploads() -> dict[str, Path]:
    folder = STUDIO / "uploads"
    return {p.name: p for p in sorted(folder.iterdir()) if p.is_file()} if folder.is_dir() else {}


def _sha(data: bytes | str) -> str:
    return hashlib.sha256(data.encode() if isinstance(data, str) else data).hexdigest()


class Log:
    """Progress lines for the UI, with the stage each belongs to."""

    def __init__(self, on_line=None):
        self.lines: list[dict] = []
        self.stage = ""
        self.on_line = on_line
        self.t0 = time.time()

    def __call__(self, text: str) -> None:
        line = {"t": round(time.time() - self.t0, 1), "stage": self.stage, "text": text}
        self.lines.append(line)
        if self.on_line:
            self.on_line(line)

    def begin(self, stage: str, text: str) -> None:
        self.stage = stage
        self(text)


# ---------- level ----------

def resolve_level(brief: dict, log: Log) -> tuple[Path, str]:
    """The level file for the brief, and what was chosen. A prompt that says anything about the
    level (shape, size, blocks, colours, difficulty) gets a generated one; a prompt that says
    nothing gets the showcase: the hand-checked hard narrow-centre level."""
    from .generate import generate_for_brief
    lv = brief["level"]
    if lv["source"] == "shipped" and lv["shipped"]:
        return LEVELS / f"Level_{lv['shipped']:02d}.json", f"the game's own Level {lv['shipped']}"
    described = (any(lv[k] is not None for k in ("width", "height", "blocks")) or lv["colours"]
                 or lv["shape"] != "any" or lv["difficulty"] != "any")
    if lv["source"] == "generate" or described:
        return generate_for_brief(brief, STUDIO / "levels", log)
    return NARROW, "the hand-checked hard narrow-centre level (6x8, 7 blocks)"


# ---------- recording ----------

LOOK = ("hide", "zoom", "label", "visuals")  # recording fields that change the look, not the play


def game_visuals(brief: dict) -> dict:
    """The recorder's visuals for a brief: repainted colour slots, the board, the background."""
    shown = B.display_colours(brief)
    bg = B.background(brief)
    return {"blocks": [{"slot": s, "hex": v["hex"]} for s, v in shown.items() if v["repainted"]],
            "grid": brief["visuals"]["board"] or "", "background_top": bg[0] if bg else "",
            "background_bottom": bg[-1] if bg else ""}


def _recording_spec(brief: dict, level_path: Path) -> dict:
    from .level import load_level
    gp, pc, vs = brief["gameplay"], brief["pacing"], brief["visuals"]
    hide = ["RestartButton"] + hud_hide(vs)
    label = brief["level"]["label"] or hud_label(load_level(level_path), level_path)
    return {"level_sha": _sha(level_path.read_bytes()), "ending": gp["ending"], "mistakes": gp["mistakes"],
            "kinds": gp["mistake_kinds"], "hesitations": gp["hesitations"], "seed": gp["seed"] or 0,
            "tempo": pc["tempo"], "length_s": pc["length_s"], "label": label, "hide": hide,
            "zoom": vs["camera_zoom"] or 1.0, "timer_s": gp["timer_s"], "visuals": game_visuals(brief)}


def _usable(folder: Path) -> bool:
    """A finished recording that passed its checks (a failed one is never reused)."""
    try:
        play = json.loads((folder / "play.json").read_text())
    except (OSError, ValueError):
        return False
    return ((folder / "spec.json").is_file() and (folder / "gameplay.mp4").is_file()
            and not play.get("measured", {}).get("problems"))


def _play_key(spec: dict) -> str:
    return _sha(json.dumps({k: v for k, v in spec.items() if k not in LOOK}, sort_keys=True))[:16]


def _refilm(src: Path, out: Path, spec: dict, log: Log) -> None:
    """Film a cached recording again with a new look: the same job (drags, pauses, clock), only
    the look fields changed, then check the game state matched on every frame."""
    from .render import Camera, compare_recordings, rerun, visuals_job
    changes = {"visuals": visuals_job(spec["visuals"]), "hide": spec["hide"],
               "camera": Camera(zoom=spec["zoom"]).to_job(), "level_label": spec["label"]}
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    log("same gameplay, new look: the stored job is filmed again (same moves, same timing)...")
    result = rerun(src, out, changes)
    if result["problems"]:
        raise ValueError(f"re-filming failed: {result['problems'][0]}")
    for name in ("play.json", "level.json"):
        shutil.copy(src / name, out / name)
    c = compare_recordings(src, out)
    if not c.get("state_equal"):
        raise ValueError("re-filmed with a new look, but the game state differs from the original; not used")
    log(f"re-filmed {result['frames']} frames; game state identical to the original on every frame")


def _length_pick(spec: dict):
    """Chooses the recording's length from the tempo, inside what the ad's length leaves room for."""
    L = spec["length_s"]
    tail = 2.0 if spec["ending"] == "cliffhanger" else 0.0  # the question hold after the cut

    def pick(lo, hi, planned):
        upper = L - END_CARD_S[0] - REPLAY_EST_S - tail  # room for a short replay and the end card
        lower = L - END_CARD_MAX_S - 5.0 - 2.0 - tail  # less, and the ad would be mostly end card
        if spec["tempo"] == "normal" and lower <= planned <= upper:
            return None  # the planned pauses fit: no refit (fewer changes, the tested path)
        want = {"calm": hi, "fast": lo}.get(spec["tempo"], planned)
        return min(max(want, lower), upper)
    return pick


def ensure_recording(brief: dict, level_path: Path, log: Log) -> tuple[Path, bool]:
    """The recording for the brief: found by its spec's hash, or made in the real game."""
    from .difficulty import rate
    from .level import load_level
    from .play import END_MODE, plan, run, time_out_allowed
    from .render import Camera, level_label
    spec = _recording_spec(brief, level_path)
    key = _sha(json.dumps(spec, sort_keys=True))[:16]
    out = STUDIO / "recordings" / key
    if _usable(out):
        log(f"same gameplay as before: recording {key} reused (nothing re-recorded)")
        return out, True
    play = _play_key(spec)
    for other in sorted((STUDIO / "recordings").glob("*/spec.json")) if (STUDIO / "recordings").is_dir() else []:
        o = json.loads(other.read_text())
        if _play_key(o) == play and _usable(other.parent):
            _refilm(other.parent, out, spec, log)
            (out / "spec.json").write_text(json.dumps(spec, indent=1))
            return out, False
    level = load_level(level_path)
    gp = brief["gameplay"]
    d = rate(level)
    if gp["ending"] == "time_out":
        ok, why = time_out_allowed(d)
        if not ok:
            B.engine_note(brief, "gameplay", f"this level is too easy for a believable time-out ({why}); a near-fail is "
                                        f"recorded instead.")
            gp["ending"] = "near_fail"
            return ensure_recording(brief, level_path, log)
    script = plan(level, gp["ending"], mistakes=gp["mistakes"], seed=spec["seed"], hesitations=gp["hesitations"],
                  kinds=tuple(gp["mistake_kinds"]) or None)
    for n in script.notes:
        B.engine_note(brief, "gameplay", n + ".")
    n_m = sum(b.kind == "mistake" for b in script.beats)
    log(f"planned {len(script.beats)} beats ({n_m} mistake(s)); dry run, then recording in the real game...")
    if out.exists():
        shutil.rmtree(out)
    label = spec["label"]
    kw = dict(difficulty=d, label=label, hide=tuple(spec["hide"]), camera=Camera(zoom=spec["zoom"]),
              visuals=spec["visuals"])
    result = run(level, level_path, script, out, length_pick=_length_pick(spec), **kw)
    for p in result["problems"]:
        log(f"  problem: {p}")
    if result["problems"]:
        # A length fit can leave the clock fit no room; record again with the planned pauses.
        log("recording again with the planned pauses (no length fit)...")
        script = plan(level, gp["ending"], mistakes=gp["mistakes"], seed=spec["seed"],
                      hesitations=gp["hesitations"], kinds=tuple(gp["mistake_kinds"]) or None)
        shutil.rmtree(out)
        result = run(level, level_path, script, out, **kw)
        for p in result["problems"]:
            log(f"  problem: {p}")
        if result["problems"]:
            shutil.rmtree(out, ignore_errors=True)  # never reused
            raise ValueError(f"the recording did not match its plan: {result['problems'][0]}")
        B.engine_note(brief, "difficulty_pacing", "the requested pace could not be fitted exactly, so the planned "
                                                  "pauses are used.")
    m = script.measured
    log(f"recorded {m['frames']} frames ({m['duration_s']:.1f} s), {m['clock_left_s']:.2f} s left on the clock")
    (out / "spec.json").write_text(json.dumps(spec, indent=1))
    return out, False


def hud_label(level, level_path: Path) -> int:
    """The number in the HUD's Level badge: the game's own for its levels, else a stable number
    from the level file (a generated level is not "Level 0"). A prompt can set it ("level 47")."""
    m = re.fullmatch(r"Level_(\d+)", level.name or "")
    return int(m.group(1)) if m else 12 + int(_sha(level_path.read_bytes())[:6], 16) % 150


# ---------- the ad ----------

def _asset_path(name: str, ups: dict[str, Path]) -> str:
    if name in ups:
        return str(ups[name])
    return name  # a game sprite, or builtin:hand


def ad_options(brief: dict, ups: dict[str, Path]) -> dict:
    sq, vs, cc = brief["sequence"], brief["visuals"], brief["concept"]
    o = {"replay": sq["replay"], "result_screen": sq["result_screen"], "teaser": sq["style"] == "result_first",
         "clock_visible": vs["hud_timer"],
         "texts": {k: cc[k] for k in B.CONCEPT_TEXTS if cc[k] is not None},
         "fill": vs["caption_fill"], "stroke": vs["caption_outline"], "cursor": vs["cursor"],
         "sfx": brief["audio"]["sfx"]}
    shown = B.display_colours(brief)
    translated = brief["visuals"].get("names") or {}
    o["colour_names"] = {SLOT_ENUM[s]: v["name"] for s, v in shown.items() if v["repainted"] or s in translated}
    for a in brief["assets"]:
        path = _asset_path(a["file"], ups)
        role = a["role"]
        if role == "logo":
            o["logo"] = {"file": path, "where": "top_right" if a["where"] == "top_right" else "top_left"}
        elif role == "cursor" and a["file"] != "builtin:hand":
            o["cursor_image"] = path
        elif role == "end_art" or (role in ("mascot", "sticker") and a["when"] == "end_card"):
            o["end_art"] = path
        elif role in ("mascot", "sticker"):
            o["hook_icon"] = path
        elif role == "end_background":
            o["end_background"] = path
    bg = B.background(brief)
    if bg and not o.get("end_background"):
        o["end_gradient"] = [bg[0], bg[-1]]
    return o


def build_and_render(brief: dict, rec_dir: Path, out: Path, log: Log, draft: bool = False) -> dict:
    from .compose import render
    rec = Recording.load(rec_dir)
    ups = uploads()
    options = ad_options(brief, ups)
    L = brief["pacing"]["length_s"]
    ad, err = None, None
    for d in [0] + [s * k for k in range(1, 31) for s in (1, -1)]:
        length = L + d
        if not B.LENGTH_RANGE_S[0] <= length <= B.LENGTH_RANGE_S[1]:
            continue
        try:
            ad = build_ad(rec, length, options=options)
            break
        except ValueError as e:
            err = err or str(e)
            if d == 0:
                log(f"a {L:g} s ad does not fit this gameplay: {e}")
    if ad is None:
        raise ValueError(f"no ad length fits this recording: {err}")
    if ad["length_s"] != L:
        B.engine_note(brief, "difficulty_pacing", f"this gameplay fills {rec.n / FPS:.1f} s, so the ad is "
                                             f"{ad['length_s']:g} s instead of {L:g} s "
                                             f"({'a bigger level or more mistakes would fill more' if ad['length_s'] < L else 'it cannot be shorter with a readable end card'}).")
    for n in ad.get("brief_notes", []):
        B.engine_note(brief, n["control"], n["text"] + ".", status=n["status"])
    for k in ("logo", "hook_icon", "end_art", "end_background", "cursor_image"):
        if options.get(k):
            log(f"asset: {k.replace('_', ' ')} = {Path(str(options[k]['file'] if k == 'logo' else options[k])).name}")
    out.mkdir(parents=True, exist_ok=True)
    (out / "ad.json").write_text(json.dumps(ad, indent=2))
    log(f"composing {ad['length_s']:g} s: {', '.join(ad['order'])}...")
    result = render(ad, out, draft=draft)
    if not result.get("rendered"):
        raise ValueError("QA stopped the render: " + "; ".join(result["qa"]["failures"][:3]))
    for w in result["qa"]["warnings"]:
        log(f"  QA warning: {w}")
    if result["qa"]["failures"]:
        raise ValueError("QA failed: " + "; ".join(result["qa"]["failures"][:3]))
    return result


# ---------- versions ----------

def _new_id(prompt: str) -> str:
    words = re.findall(r"[a-z0-9]+", prompt.lower())[:5]
    return time.strftime("%m%d-%H%M%S") + ("-" + "-".join(words) if words else "")


CID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}")


def creative_dir(cid: str) -> Path:
    """The folder of a creative. Ids come from the UI's requests, so they are checked before any
    file use: letters, digits, '-' and '_' only, and the folder must be inside studio/."""
    if not isinstance(cid, str) or not CID.fullmatch(cid):
        raise ValueError(f"not a creative id: {cid!r}")
    folder = (STUDIO / cid).resolve()
    if not folder.is_relative_to(STUDIO.resolve()):
        raise ValueError(f"not a creative id: {cid!r}")
    return folder


def versions(cid: str) -> list[dict]:
    folder = creative_dir(cid)
    out = []
    for v in sorted(folder.glob("v*/version.json"), key=lambda p: int(p.parent.name[1:])):
        out.append(json.loads(v.read_text()))
    return out


def creatives() -> list[dict]:
    out = []
    if not STUDIO.is_dir():
        return out
    for folder in sorted(STUDIO.iterdir(), reverse=True):
        if folder.is_dir() and (folder / "v1" / "version.json").is_file():
            vs = versions(folder.name)
            out.append({"id": folder.name, "prompt": vs[0]["prompt"], "versions": len(vs),
                        "last": vs[-1]["n"], "summary": vs[-1]["brief"].get("summary", "")})
    return out


def _proof(prev: dict, cur: dict) -> dict:
    """What changed between two versions, with the strongest proof each case allows."""
    from .compose import diff
    changed = B.changed_controls(prev["brief"], cur["brief"])
    if prev["level"]["sha"] != cur["level"]["sha"] and "level" not in changed:
        changed = ["level", *changed]  # a new level, even if only its difficulty was asked for
    proof = {"changed_controls": [B.CONTROL_TITLES[c] for c in changed]}
    if prev["recording"]["dir"] == cur["recording"]["dir"]:
        proof["gameplay"] = "identical: the same recording was reused (not re-recorded)"
        try:
            d = diff(STUDIO / prev["ad_dir"], STUDIO / cur["ad_dir"])
        except ValueError as e:
            proof["frames"] = f"not compared: {e}"
            return proof
        rs = d.get("changed_frames")
        if rs is None:
            proof["frames"] = "the timeline changed (a length or sequence edit), so frames are not compared one to one"
        else:
            n = sum(b - a + 1 for a, b in rs)
            proof["frames"] = (f"{n} of {d['frames'][0]} frames changed"
                               + (f" ({', '.join(f'{a}-{b}' for a, b in rs[:6])})" if rs else ""))
            if d.get("measured_box"):
                proof["pixels"] = ("every changed pixel is inside the changed layers' boxes" if d["contained"]
                                   else "SOME CHANGED PIXELS ARE OUTSIDE THE CHANGED LAYERS")
        proof["layers_changed"] = d["layers_changed"]
        proof["sound"] = "same" if d["same_sound"] else "changed"
        proof["ok"] = d["ok"]
    else:
        from .render import compare_recordings
        a, b = STUDIO / prev["recording"]["dir"], STUDIO / cur["recording"]["dir"]
        c = compare_recordings(a, b)
        moves = lambda d: [(x["block"], x["cells"]) for x in json.loads((d / "result.json").read_text())["drags"]]
        same_level = prev["level"]["sha"] == cur["level"]["sha"]
        if c.get("state_equal"):
            proof["gameplay"] = "re-recorded with identical game state on every frame (the same moves and timing)"
        elif same_level and moves(a) == moves(b):
            proof["gameplay"] = "re-recorded: the same moves, with different pauses"
        else:
            proof["gameplay"] = ("new gameplay on the same level" if same_level else "new gameplay on a new level")
        proof["ok"] = True
    return proof


KEEP_GROUPS = {"level": ("level.",), "gameplay": ("gameplay.",), "timing": ("pacing.",), "camera": ("visuals.zoom",),
               "visuals": ("visuals.",), "copy": ("concept.", "language"), "sequence": ("sequence",),
               "assets": ("assets",), "sound": ("audio",)}


def _keep_conflicts(old: dict, new: dict) -> None:
    """A prompt can ask to keep something and change it in the same breath ("keep the level but
    make it harder": a harder level is a new level). The change wins; the brief says so."""
    for k in new.get("keep", []):
        hit = [g for g, (_, paths) in B.GROUPS.items() if g.startswith(KEEP_GROUPS.get(k, ("-",)))
               and any(B._get(old, p) != B._get(new, p) for p in paths)]
        if hit:
            B.engine_note(new, "unchanged", f"asked to keep the {k}, but the prompt also changes it "
                                            f"({', '.join(hit)}); the change wins")


def make(prompt: str, brief: dict, cid: str | None = None, log: Log | None = None, draft: bool = False) -> dict:
    """Make a version of a creative from a checked brief. With cid, the new version follows that
    creative's latest one (an edit). Returns the version record (also saved as version.json)."""
    log = log or Log(lambda line: print(f"[{line['stage']}] {line['text']}"))
    cid = cid or _new_id(prompt)
    folder = creative_dir(cid)
    prev = versions(cid)[-1] if folder.is_dir() and versions(cid) else None
    n = (prev["n"] + 1) if prev else 1
    vdir = folder / f"v{n}"
    if vdir.exists():
        shutil.rmtree(vdir)
    vdir.mkdir(parents=True)
    t0 = time.time()
    stages = []

    def stage(name, fn, *a):
        s0 = time.time()
        r = fn(*a)
        stages.append({"stage": name, "seconds": round(time.time() - s0, 1)})
        return r

    for row in brief["controls"]:  # engine notes belong to the version that made them
        row["engine"] = []
    if prev is not None:
        _keep_conflicts(prev["brief"], brief)
    log.begin("level", "choosing the level...")
    if prev is not None and prev["brief"]["level"] == brief["level"]:
        # An edit that does not ask about the level keeps the previous version's level exactly.
        level_path = STUDIO / prev["level"]["file"]
        level_why = prev["level"]["why"]
        stages.append({"stage": "level", "seconds": 0.0})
        log(f"the edit does not touch the level: v{prev['n']}'s level is kept")
    else:
        level_path, level_why = stage("level", resolve_level, brief, log)
    shutil.copy(level_path, vdir / "level.json")
    log(f"level: {level_why}")
    log.begin("recording", "gameplay...")
    rec_dir, reused = stage("recording", ensure_recording, brief, level_path, log)
    log.begin("compose", "the ad...")
    ad_dir = vdir / "ad"
    result = stage("compose", build_and_render, brief, rec_dir, ad_dir, log, draft)
    rel = lambda p: str(Path(p).resolve().relative_to(STUDIO.resolve()))
    record = {
        "n": n, "id": cid, "prompt": prompt, "edit": prev is not None, "brief": brief,
        "level": {"file": rel(vdir / "level.json"), "source": str(level_path.resolve().relative_to(REPO.resolve()))
                  if level_path.resolve().is_relative_to(REPO.resolve()) else str(level_path),
                  "why": level_why, "sha": _sha(level_path.read_bytes())},
        "recording": {"dir": rel(rec_dir), "reused": reused},
        "ad_dir": rel(ad_dir), "video": rel(ad_dir / "ad.mp4"), "poster": rel(ad_dir / "poster.png"),
        "length_s": result["duration_s"], "qa": result["qa"], "stages": stages,
        "seconds": round(time.time() - t0, 1), "created": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    if prev is not None:
        log.begin("proof", "comparing with the previous version...")
        s0 = time.time()
        record["proof"] = _proof(prev, record)
        stages.append({"stage": "proof", "seconds": round(time.time() - s0, 1)})
        log(f"proof: {record['proof'].get('gameplay')}; {record['proof'].get('frames', '')}")
    record["seconds"] = round(time.time() - t0, 1)
    (vdir / "brief.json").write_text(json.dumps(brief, indent=1))
    (vdir / "version.json").write_text(json.dumps(record, indent=1))
    log.begin("done", f"done in {record['seconds']:.0f} s")
    return record
