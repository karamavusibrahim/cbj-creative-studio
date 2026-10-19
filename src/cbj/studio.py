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
import copy
import json
import re
import shutil
import time
from pathlib import Path

from . import brief as B
from .ad import END_CARD_S, END_CARD_MAX_S, FPS, TEXT_LAYERS, Recording, build_ad
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
    if not visuals["hud_timer"]:
        # the clock's panel goes too ("MainBar:image": the bar's own graphic, not its children), so
        # the Level badge does not sit on an empty purple bar
        return [*HUD_TIMER, "MainBar:image"]
    return [*(HUD_LEVEL if not visuals["hud_level"] else ())]
REPLAY_EST_S = 3.0  # room an ad keeps for a replay when it picks the recording's length


def sprite_names() -> set[str]:
    folder = PROJECT / SPRITES
    return {p.name for p in folder.glob("*.png")} if folder.is_dir() else set()


IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_EXT = {".mp4", ".mov", ".webm", ".m4v"}


def uploads() -> dict[str, Path]:
    """Uploaded images and music, by name: the files an ad may place or play (the brief checks a
    picture is an image and the music a sound file)."""
    folder = STUDIO / "uploads"
    return ({p.name: p for p in sorted(folder.iterdir()) if p.is_file() and (p.suffix.lower() in IMAGE_EXT
                                                                             or B.is_audio(p.name))}
            if folder.is_dir() else {})


def videos() -> dict[str, Path]:
    """Uploaded reference videos, by name (never placed in an ad; analysed for the planner)."""
    folder = STUDIO / "uploads"
    return ({p.name: p for p in sorted(folder.iterdir()) if p.is_file() and p.suffix.lower() in VIDEO_EXT}
            if folder.is_dir() else {})


def looks_like_video(data: bytes) -> bool:
    """The container's magic: an MP4/MOV 'ftyp' box or a WebM/Matroska EBML header."""
    head = data[:64]
    return b"ftyp" in head or head.startswith(b"\x1a\x45\xdf\xa3")


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
    level (shape, size, blocks, piece shapes, looks, colours, difficulty) gets a generated one; a
    prompt that says nothing gets the showcase: the hand-checked hard narrow-centre level, if it
    can play the requested order of events, else a generated level that can."""
    from .generate import generate_for_brief
    lv, gp = brief["level"], brief["gameplay"]
    if lv.get("source") == "picture" and lv.get("file"):
        # the board read cell by cell from a reference picture (imagecells, 2026-10-19): played as read. The name comes
        # from a brief a client may have edited: only the tool's own picture_<hash>.json names, inside studio/levels.
        import re
        base = (STUDIO / "levels").resolve()
        name = str(lv["file"])
        path = (base / name).resolve() if re.fullmatch(r"picture_[0-9a-f]{12}\.json", name) else None
        if path is not None and path.parent == base and path.is_file():
            return path, "the board read from the picture, cell by cell"
        log(f"the picture's level file {name[:40]!r} is not one of the tool's; a board of its type is generated instead")
        lv["source"], lv["file"] = "generate", None
    if lv["source"] == "shipped" and lv["shipped"]:
        path = LEVELS / f"Level_{lv['shipped']:02d}.json"
        short = _too_short(brief, path)
        if short and not _asked_level_number(brief):
            # "an easy level" with a long ad: the game's own levels are tutorial-size, so one is
            # generated to the ad's length instead (the case asks for 30-60 s)
            log(f"the game's Level {lv['shipped']} {short}; generating a level sized to the ad instead...")
            B.engine_note(brief, "level", f"the game's own Level {lv['shipped']} {short}, so a level of the same "
                                          f"difficulty is generated to fill the {brief['pacing']['length_s']:g} s ad.")
            lv["source"], lv["shipped"] = "generate", None
            if lv["difficulty"] == "any":
                lv["difficulty"] = "easy"
            return generate_for_brief(brief, STUDIO / "levels", log)
        if short:
            B.engine_note(brief, "difficulty_pacing", f"the game's own Level {lv['shipped']} {short}; the ad is filled "
                                                      f"with a longer replay and a held result.")
        return path, f"the game's own Level {lv['shipped']}"
    described = (any(lv[k] is not None for k in ("width", "height", "blocks")) or lv["colours"]
                 or lv["shape"] != "any" or lv["difficulty"] != "any" or lv["pieces"] != "mixed" or lv["style"])
    if lv["source"] == "generate" or described:
        _more_play_for_a_long_ad(brief)
        return generate_for_brief(brief, STUDIO / "levels", log)
    if gp["events"]:
        why = _cannot_play(brief, NARROW)
        if why:
            log(f"the showcase level cannot play this order ({why}); generating a level that can...")
            return generate_for_brief(brief, STUDIO / "levels", log)
    short = _too_short(brief, NARROW)
    if short:
        log(f"the showcase level {short}; generating a hard narrow-centre level sized to the ad...")
        B.engine_note(brief, "level", f"the showcase level {short}, so a hard narrow-centre level is generated to "
                                      f"fill the {brief['pacing']['length_s']:g} s ad.", status=None)
        lv["source"], lv["shape"], lv["difficulty"] = "generate", "narrow_center", "hard"
        _more_play_for_a_long_ad(brief)
        return generate_for_brief(brief, STUDIO / "levels", log)
    if lv["difficulty"] == "any":
        B.engine_note(brief, "difficulty_pacing", "no difficulty was asked: the showcase level is used, and it is hard "
                                                  "(a near-fail needs a board where a wrong move is possible).", status=None)
    if gp["events"]:
        return NARROW, "the hand-checked hard narrow-centre level (6x8, 7 blocks), which can play the requested order"
    return NARROW, "the hand-checked hard narrow-centre level (6x8, 7 blocks)"


LONG_AD_S = 50.0


def _more_play_for_a_long_ad(brief: dict) -> None:
    """One level gives at most about 33 s of play (10 blocks, 13-14 drags); a 50-60 s ad with a
    mistake-based ending shows two mistakes unless the prompt set the count, and says so."""
    gp = brief["gameplay"]
    if brief["pacing"]["length_s"] >= LONG_AD_S and gp["mistakes"] is None and gp["ending"] in ("near_fail", "time_out"):
        gp["mistakes"] = 2
        B.engine_note(brief, "gameplay", f"a {brief['pacing']['length_s']:g} s ad needs more play than one level's "
                                         f"moves give, so two mistakes are shown (say 'one mistake' to keep one).",
                      status=None)


def _asked_level_number(brief: dict) -> bool:
    """Whether the prompt named one of the game's own levels ("level 4", "the game's level 2")."""
    text = (brief.get("planner") or {}).get("prompt") or ""
    return re.search(r"\b(level|lvl)\s*0?\d\b", text.lower()) is not None


def _too_short(brief: dict, level_path: Path) -> str | None:
    """Why this level cannot fill the ad's length (None if it can): its minimum drags are well
    under what the length needs (generate._target_drags), so even long pauses leave an ad that
    is mostly end card."""
    from .generate import _target_drags
    from .level import load_level
    from .solver import solve_fast
    drags = solve_fast(load_level(level_path)).min_drags
    target = _target_drags(brief)
    if brief["gameplay"]["ending"] == "cliffhanger":
        target -= 2
    if drags >= target - 3:
        return None
    return f"plays about {drags} drags (roughly {drags * 1.6 + 3:.0f} s), far too little for a {brief['pacing']['length_s']:g} s ad"


def _cannot_play(brief: dict, level_path: Path) -> str | None:
    """Why this level cannot play the brief's events (None if it can, at most one drag longer)."""
    from .events import SOLVER_ACTIONS, from_brief, try_solve_events
    from .level import load_level
    from .solver import solve_fast
    level = load_level(level_path)
    evs, notes = from_brief(level, brief["gameplay"]["events"])
    if len(evs) < len(brief["gameplay"]["events"]):
        return next((n for n in notes if "no such block" in n), notes[0])
    solver = [e for e in evs if e.action in SOLVER_ACTIONS]
    if solver:
        sol = try_solve_events(level, solver)
        if sol is None:
            return "the steps cannot happen in that order"
        if sol.min_drags > solve_fast(level).min_drags + 1:
            return f"that order costs {sol.min_drags - solve_fast(level).min_drags} extra drags"
    try:
        script = _plan(brief, level, 0)
    except ValueError as e:
        return str(e)
    missed = [n for n in script.notes if "not shown" in n or "not played" in n or "cannot happen" in n]
    return missed[0] if missed else None


def _plan(brief: dict, level, seed: int):
    """The play script for the brief on a level (events resolved on it)."""
    from .events import from_brief
    from .play import plan
    gp, pc = brief["gameplay"], brief["pacing"]
    evs, notes = from_brief(level, gp["events"])
    kw = dict(mistakes=gp["mistakes"], seed=seed, hesitations=gp["hesitations"],
              kinds=tuple(gp["mistake_kinds"]) or None, clock_left=gp["clock_left_s"] or 1, left=gp.get("blocks_left"),
              finish=gp["finish"], curve=pc["curve"])
    if gp.get("prefix"):  # the moves a board edit kept from the version it edits
        from .boardedit import prefix_from_json
        kw["prefix"] = prefix_from_json(gp["prefix"])
    try:
        script = plan(level, gp["ending"], events=evs, **kw)
    except ValueError as e:
        if not evs:
            raise
        why = "" if "events cannot" in str(e) else f": {str(e).split(': ', 1)[-1]}"
        notes.append(f"the requested order cannot happen on this level ({'; '.join(x.text for x in evs)}){why}; the "
                     f"steps that need it are played without it")
        try:
            script = plan(level, gp["ending"], events=[x for x in evs if x.action in ("stuck", "hesitates", "blocks")], **kw)
        except ValueError:
            script = plan(level, gp["ending"], events=[], **kw)
    script.notes[:0] = notes
    return script


# ---------- recording ----------

LOOK = ("hide", "zoom", "label", "visuals")  # recording fields that change the look, not the play


def game_visuals(brief: dict) -> dict:
    """The recorder's visuals for a brief: repainted colour slots, the board, the background."""
    shown = B.display_colours(brief)
    bg = B.background(brief)
    out = {"blocks": [{"slot": s, "hex": v["hex"]} for s, v in shown.items() if v["repainted"]],
           "grid": brief["visuals"]["board"] or "", "background_top": bg[0] if bg else "",
           "background_bottom": bg[-1] if bg else ""}
    pic = brief["visuals"].get("background_image")
    if pic:  # written only when set, so a recording made before this field keeps its key
        from .draw import PROJECT, SPRITES
        out["background_image"] = str(uploads().get(pic) or (PROJECT / SPRITES / pic))  # an upload, or a game sprite
    return out


def _recording_spec(brief: dict, level_path: Path) -> dict:
    from .level import load_level
    gp, pc, vs = brief["gameplay"], brief["pacing"], brief["visuals"]
    hide = ["RestartButton"] + hud_hide(vs)
    label = brief["level"]["label"] or hud_label(load_level(level_path), level_path)
    from .play import PLAY_VERSION
    spec = {"play": PLAY_VERSION,
            "level_sha": _sha(level_path.read_bytes()), "ending": gp["ending"], "mistakes": gp["mistakes"],
            "kinds": gp["mistake_kinds"], "hesitations": gp["hesitations"], "seed": gp["seed"] or 0,
            "tempo": pc["tempo"], "length_s": pc["length_s"], "label": label, "hide": hide,
            "zoom": vs["camera_zoom"] or 1.0, "timer_s": gp["timer_s"], "visuals": game_visuals(brief)}
    # Written only when set, so a recording made before these existed keeps its key.
    if gp["events"]:
        spec["events"] = gp["events"]
    if gp["finish"] != "auto":
        spec["finish"] = gp["finish"]
    if gp["clock_left_s"] not in (None, 1):
        spec["clock_left"] = gp["clock_left_s"]
    if gp.get("blocks_left") is not None:
        spec["blocks_left"] = gp["blocks_left"]  # part of the recording's identity: a 1-block cut is another take
    if pc["curve"] != "even":
        spec["curve"] = pc["curve"]
    if gp.get("prefix"):
        spec["prefix"] = gp["prefix"]
    if gp["ending"] == "win" and gp["timer_s"] is None and brief["level"]["difficulty"] == "hard" and pc["tempo"] != "calm":
        spec["clock"] = "tight"  # part of the identity: a hard win filmed with a calm clock is another recording
    if gp.get("events"):
        # part of the identity: how the asked order is fitted is the play planner's version (2026-10-16)
        from .play import PACING_VERSION as _PV
        spec["order"] = _PV
    grade = _short_solve(brief, level_path)
    if grade:
        # part of the identity: the same level paced two ways is two recordings; the value names the
        # pacing version and grade (play.deliberate), so a change of pacing never reuses an older film
        from .play import PACING_VERSION
        spec["deliberate"] = f"{PACING_VERSION}/{grade}"
    return spec


PACE_EXTRA_S = {"deliberate": 2.0, "thinking": 1.0, "calm": 1.6}  # about what each slowed drag adds over its usual pace


def _set_clock(script, spec: dict) -> None:
    """The recording's clock from the brief: an asked number of seconds (the fit keeps it when it
    stays calm), or "tight" on a hard level's win (the clock runs low, as a hard level should feel)."""
    if spec.get("timer_s") is not None:
        script.timer_s = int(spec["timer_s"])
    script.clock = spec.get("clock") or "calm"


def _keep_run(beats) -> int | None:
    """How many closing drags keep their own pace under deliberate pacing: a satisfying finish's run
    of exits after the key move (the payoff stays quick), at most the closing cascade (a run that is the
    whole play would leave nothing to pace); otherwise play.deliberate's default."""
    from .play import CASCADE_DRAGS
    key = next((i for i, b in enumerate(beats) if getattr(b, "tag", None) == "key"), None)
    return None if key is None else max(1, min(CASCADE_DRAGS, len(beats) - key - 1))


def _short_solve(brief: dict, level_path: Path) -> str | None:
    """Whether the level's solve is short for the ad, so the play should be paced deliberately
    (play.deliberate) rather than the ad padded with a long end card: "deliberate" (a 1.6-2.2 s look
    before each drag, the slowest finger) when the solve so paced still fits the length, "thinking"
    (0.9-1.6 s, a careful finger) when only that fits, None when the play already fills the ad or no
    slower pace would fit (the ad would run over its length, as a 13-drag near-fail did on 2026-10-14).
    A fast tempo keeps its pace; a streak finish keeps its last drags (play.deliberate's keep_last)."""
    from .level import load_level
    from .solver import solve_fast
    gp, pc = brief["gameplay"], brief["pacing"]
    if pc["tempo"] == "fast" or gp["ending"] not in ("win", "near_fail", "cliffhanger"):
        return None  # a cliffhanger's play is paced too (its final bump keeps its own pauses); a time-out is timed
    drags = solve_fast(load_level(level_path)).min_drags - (gp.get("blocks_left") or 2 if gp["ending"] == "cliffhanger" else 0)
    mistakes = gp["mistakes"] if gp["mistakes"] is not None else {"near_fail": 1}.get(gp["ending"], 0)
    estimate = drags * 1.6 + 3 + 3.5 * mistakes  # the play at its usual pace
    fits = pc["length_s"] - END_CARD_S[0] - 2.5 - 1.0  # the shortest card, the result and the lead-in after the play
    if pc["tempo"] == "calm":
        # an asked calm tempo always breathes (play.PAUSES "calm"): before every drag when that fits the
        # length, else before every other drag ("thinking" = the alternating rhythm here; P6-b, 2026-10-14)
        if estimate + PACE_EXTRA_S["calm"] * max(0, drags - 1) <= fits:
            return "deliberate"
        return "thinking" if estimate + PACE_EXTRA_S["calm"] * max(0, (drags - 1 + 1) // 2) <= fits else None
    room = pc["length_s"] - END_CARD_MAX_S - 7.0  # less play than this and the ad is mostly card and holds
    if estimate >= room:
        return None
    slowed = max(0, (drags - 2 + 1) // 2)  # every other drag gets the look; the closing drags keep their pace
    rest = max(0, drags - 2 - slowed)  # the drags in between
    # "slow" (2026-10-15): the look before every other drag and a thought before the rest, when the play
    # would still fall short of the room by more than a drag (the play filled about 60 % of the audited ads)
    if estimate + PACE_EXTRA_S["deliberate"] * slowed + PACE_EXTRA_S["thinking"] * rest <= fits and \
            estimate + PACE_EXTRA_S["deliberate"] * slowed < room - 2.0:
        return "slow"
    for grade, extra in (("deliberate", PACE_EXTRA_S["deliberate"]), ("thinking", PACE_EXTRA_S["thinking"])):
        if estimate + extra * slowed <= fits:
            return grade
    return None


def _breathe_short_play(brief: dict, level_path: Path) -> None:
    """A new creative whose solve is short for the ad: the human beats the ending allows (a pick-up
    and put-back) are added when the prompt set no hesitation count, so more of the ad is play. Never
    on an edit: an edit keeps its version's play."""
    from .level import load_level
    from .solver import solve_fast
    gp, pc = brief["gameplay"], brief["pacing"]
    if gp["hesitations"] is not None or pc["tempo"] == "fast" or gp["ending"] not in ("win", "near_fail", "cliffhanger"):
        return
    drags = solve_fast(load_level(level_path)).min_drags
    mistakes = gp["mistakes"] if gp["mistakes"] is not None else {"near_fail": 1}.get(gp["ending"], 0)
    estimate = drags * 1.6 + 3 + 3.5 * mistakes + PACE_EXTRA_S["deliberate"] * max(0, (drags - 1) // 2)
    room = pc["length_s"] - END_CARD_MAX_S - 7.0
    if estimate + 3.0 >= room:
        return
    most = {"win": 1, "near_fail": 2, "cliffhanger": 1}[gp["ending"]]
    gp["hesitations"] = most
    B.engine_note(brief, "gameplay", f"the solve is short for a {pc['length_s']:g} s ad, so the player also "
                                     f"{'hesitates once' if most == 1 else 'hesitates twice'} (a block picked up and put "
                                     f"back) and takes a look before the drags; say 'no hesitation' to keep it straight.",
                  status=None)


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
    from .play import run, time_out_allowed
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
    script = _plan(brief, level, spec["seed"])
    _set_clock(script, spec)
    for n in script.notes:
        B.engine_note(brief, "gameplay", n + ".")
    if spec.get("clock") == "tight":
        B.engine_note(brief, "difficulty_pacing", "a hard level: the clock is set so the win lands with a few seconds "
                                                  "left (a tight clock reads as hard); ask for a generous clock to keep "
                                                  "it calm.", status=None)
    if spec.get("deliberate"):
        from .play import deliberate
        grade = spec["deliberate"].split("/")[-1]
        script.beats = deliberate(script.beats, keep_last=_keep_run(script.beats), tempo=spec["tempo"], grade=grade)
        B.engine_note(brief, "difficulty_pacing", f"the solve is short for a {spec['length_s']:g} s ad, so the player "
                                                  f"moves {'deliberately (a long look before every other drag and a thought before the rest, a careful finger)' if grade == 'slow' else 'deliberately (a long look before each drag, a careful finger)' if grade == 'deliberate' else 'with a thought before each drag'} "
                                                  "instead of the ad opening on a long frozen frame.", status=None)
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
        script = _plan(brief, level, spec["seed"])
        _set_clock(script, spec)
        if spec.get("deliberate"):
            script.beats = deliberate(script.beats, keep_last=_keep_run(script.beats), tempo=spec["tempo"],
                                      grade=spec["deliberate"].split("/")[-1])
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
    if (script.fit or {}).get("why"):
        B.engine_note(brief, "difficulty_pacing", script.fit["why"] + ".")
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
         "sfx": brief["audio"]["sfx"],
         "music": _asset_path(brief["audio"]["music"], ups) if brief["audio"].get("music") else None,
         "intro_s": sq.get("intro_s"), "hold_s": sq.get("hold_s"),
         "caption_shifts": [{"layer": TEXT_LAYERS[t["caption"]], "start_s": t["start_s"], "end_s": t["end_s"]}
                            for t in sq.get("caption_times") or []],
         "caption_style": {TEXT_LAYERS[c["caption"]]: {"fill": c["fill"]} for c in vs.get("caption_colours") or []},
         "camera": list(vs.get("punch_ins") or [])}
    shown = B.display_colours(brief)
    translated = brief["visuals"].get("names") or {}
    o["colour_names"] = {SLOT_ENUM[s]: v["name"] for s, v in shown.items() if v["repainted"] or s in translated}
    for a in brief["assets"]:
        none = a["file"] == "builtin:none"  # a picture removed on purpose
        path = "" if none else _asset_path(a["file"], ups)
        slot = B.asset_slot(a)
        if slot == "logo" and not none:
            o["logo"] = {"file": path, "where": "top_right" if a["where"] == "top_right" else "top_left"}
        elif slot == "logo2" and not none:
            o["logo2"] = {"file": path, "where": "top_right"}
        elif slot == "cursor" and not none and a["file"] != "builtin:hand":
            o["cursor_image"] = path
        elif slot == "end_art":
            o["end_art"] = path
        elif slot == "hook_icon":
            o["hook_icon"] = path
        elif slot == "end_background" and not none:
            o["end_background"] = path
        elif slot == "button" and not none:
            o["button_image"] = path
        elif slot == "obstacle":
            o["obstacle"] = path  # "" removes it
        elif slot == "skin" and not none:
            o["skin"] = {"file": path, "colour": a.get("block"), "which": "any"}
    bg = B.background(brief)
    if bg and not o.get("end_background"):
        o["end_gradient"] = [bg[0], bg[-1]]
    return o


def build_and_render(brief: dict, rec_dir: Path, out: Path, log: Log, draft: bool = False,
                     pin: dict | None = None, patch_from: Path | None = None, keep_length: bool = False) -> dict:
    """Build the ad for a recording and render it. pin: the parent version's structure, for an
    edit that keeps the recording's frames (its intro, replay and length stay; see build_ad).
    keep_length: the brief's length wins over the pin when the pinned build cannot reach it (a
    revision inside a creation that dropped the replay must still be the length the request asked;
    2026-10-16: a 40 s time-out's revision came out 30 s)."""
    from .compose import render
    rec = Recording.load(rec_dir)
    ups = uploads()
    options = ad_options(brief, ups)
    L = brief["pacing"]["length_s"]
    ad, err = None, None
    if pin is not None:
        ad = build_ad(rec, pin["length_s"], options=options, pin=pin)
        log(f"the edit keeps the gameplay frames: v{pin['n']}'s timing is kept (intro, replay, length)")
        if keep_length and abs(ad["length_s"] - L) > 0.5:
            log(f"the kept timing gives {ad['length_s']:g} s, not the {L:g} s asked (a part was removed); the ad is built "
                f"to the asked length instead")
            ad, pin = None, None
    for d in ([] if pin is not None else [0] + [s * k for k in range(1, 31) for s in (1, -1)]):
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
    if pin is None and ad["length_s"] != L:
        B.engine_note(brief, "difficulty_pacing", f"this gameplay fills {rec.n / FPS:.1f} s, so the ad is "
                                             f"{ad['length_s']:g} s instead of {L:g} s "
                                             f"({'a bigger level or more mistakes would fill more' if ad['length_s'] < L else 'it cannot be shorter with a readable end card'}).")
    for n in ad.get("brief_notes", []):
        B.engine_note(brief, n["control"], n["text"] + ".", status=n["status"])
    for k in ("logo", "logo2", "hook_icon", "end_art", "end_background", "cursor_image"):
        if options.get(k):
            log(f"asset: {k.replace('_', ' ')} = {Path(str(options[k]['file'] if k in ('logo', 'logo2') else options[k])).name}")
    out.mkdir(parents=True, exist_ok=True)
    (out / "ad.json").write_text(json.dumps(ad, indent=2))
    log(f"composing {ad['length_s']:g} s: {', '.join(ad['order'])}...")
    result = render(ad, out, draft=draft, patch_from=patch_from)
    if result.get("patched", {}).get("frames_copied"):
        pt = result["patched"]
        log(f"the approved video is patched, not rendered again: {pt['frames_copied']} of {result['frames']} frames copied "
            f"byte for byte, {pt['gops_rendered']} of {pt['gops']} GOPs rendered ({', '.join(pt['changed_layers'])})")
    if not result.get("rendered"):
        raise ValueError("QA stopped the render: " + "; ".join(result["qa"]["failures"][:3]))
    for w in result["qa"]["warnings"]:
        log(f"  QA warning: {w}")
    if result["qa"]["failures"]:
        raise ValueError("QA failed: " + "; ".join(result["qa"]["failures"][:3]))
    if brief["format"] != "9:16":
        from .formats import derive
        f = derive(out, brief["format"])
        result["format"] = f
        log(f"{brief['format']} version: the 9:16 ad's content area {f['window']} scaled {f['scale']:g} into "
            f"{f['size'][0]}x{f['size'][1]}, blurred side extensions")
    return result


# ---------- checks ----------

def board_picture(brief: dict, level_path: Path, out: Path) -> None:
    """The level drawn from its file, in the colours the ad shows (for the UI and reports)."""
    from .level import load_level
    from .preview import save_board
    shown = B.display_colours(brief)
    save_board(load_level(level_path), out, colours={s: v["hex"] for s, v in shown.items() if v["repainted"]})


LEVEL_GATE_TRIES = 2  # boards generated again (other seeds) when the first misses a measurable ask


def _level_gate(prompt: str, brief: dict, level_path: Path, why: str, log: Log) -> tuple[Path, str]:
    """The asked-facts audit on the generated level (audit.level_misses): a miss the generator could
    fix (the block count, the colours, a named block, the first blocked attempt) makes it generate
    again with another seed, and the board with the fewest misses is used (2026-10-15)."""
    from . import audit
    from .checks import level_checks
    from .generate import generate_for_brief
    try:
        miss = audit.level_misses(prompt, brief, level_path, level_checks(brief, level_path))
    except Exception as e:  # the gate must never lose a level
        log(f"level gate skipped: {e}")
        return level_path, why
    if not miss:
        return level_path, why
    best = (len(miss), level_path, why, brief["controls"])
    for k in range(1, LEVEL_GATE_TRIES + 1):
        log(f"the level misses what was asked ({'; '.join(m['check'][7:] + ': ' + m['detail'] for m in miss)}); "
            f"generating again (try {k + 1})...")
        trial = copy.deepcopy(brief)
        try:
            alt_path, alt_why = generate_for_brief(trial, STUDIO / "levels", log, seed_offset=k, budget_s=20.0)
            alt_miss = audit.level_misses(prompt, trial, alt_path, level_checks(trial, alt_path))
        except Exception as e:
            log(f"  try {k + 1} failed: {e}")
            continue
        if len(alt_miss) < best[0]:
            best = (len(alt_miss), alt_path, alt_why, trial["controls"])
            miss = alt_miss
        if not alt_miss:
            break
    if best[1] != level_path:
        brief["controls"] = best[3]
        log(f"a board that {'meets what was asked' if best[0] == 0 else 'misses less'} is used: {best[2]}")
        return best[1], best[2]
    log("no other board did better; the first is used and the misses are reported")
    return level_path, why


def gameplay_and_level_checks(brief: dict, rec_dir: Path, level_path: Path, log: Log) -> list[dict]:
    """What the brief asked for, checked on the level file and on the recording."""
    from .checks import gameplay_checks, level_checks
    out = level_checks(brief, level_path) + gameplay_checks(brief, rec_dir, level_path)
    for c in out:
        if c["status"] != "info":
            log(f"check: {c['check']}: {c['status']} ({c['detail']})")
    return out


def preview(brief: dict, cid: str | None, log: Log, base: int | None = None) -> dict:
    """The level and the planned moves for a brief, without recording (seconds, not minutes): the
    board picture, the move list, and what the plan had to change."""
    from .level import load_level
    for row in brief["controls"]:
        row["engine"] = []
    prev = parent(cid, base)
    log.begin("level", "choosing the level...")
    if prev is not None and prev["brief"]["level"] == brief["level"]:
        level_path, why = STUDIO / prev["level"]["file"], prev["level"]["why"]
        log(f"the edit does not touch the level: v{prev['n']}'s level is kept")
    else:
        level_path, why = resolve_level(brief, log)
    log(f"level: {why}")
    level = load_level(level_path)
    log.begin("recording", "planning the moves (no recording)...")
    script = _plan(brief, level, brief["gameplay"]["seed"] or 0)
    out = STUDIO / "previews" / f"{_sha(level_path.read_bytes() + json.dumps(game_visuals(brief)).encode())[:16]}.png"
    board_picture(brief, level_path, out)
    log(f"planned {len(script.beats)} moves" + (f"; {'; '.join(script.notes)}" if script.notes else ""))
    from .checks import level_checks
    return {"level_why": why, "board": str(out.resolve().relative_to(STUDIO.resolve())),
            "beats": script.to_dict(level)["beats"], "notes": script.notes, "checks": level_checks(brief, level_path),
            "controls": brief["controls"]}


# ---------- edits: keep what was not asked about ----------

REPLAN = ("ending", "mistakes", "mistake_kinds", "hesitations", "events", "finish")
BAND_ORDER = ("easy", "medium", "hard")


def _difficulty_only(old: dict, new: dict) -> bool:
    """Whether a level edit is only about difficulty (then the board is edited, not replaced)."""
    keys = set(old) | set(new)
    return any(old.get(k) != new.get(k) for k in ("difficulty", "edit")) and \
        all(old.get(k) == new.get(k) for k in keys - {"difficulty", "edit"})


def edit_level(brief: dict, prev: dict, log: Log) -> tuple[Path, str, dict | None]:
    """"Harder" or "easier": the closest board to the version's own that rates so (a few blocks or
    gates moved, colours swapped), not a new level. If no such board turns up, a new level is
    generated for an absolute difficulty; for "harder than now" on the hardest band, the level
    is kept and the brief says so."""
    from dataclasses import asdict
    from .generate import SHAPES, Spec, describe_changes, edit_board
    lv, gp = brief["level"], brief["gameplay"]
    old_d, new_d = prev["brief"]["level"]["difficulty"], lv["difficulty"]
    rel = (lv.get("edit") or {}).get("dir")
    if rel is None:
        if old_d in BAND_ORDER and new_d in BAND_ORDER:
            rel = "harder" if BAND_ORDER.index(new_d) > BAND_ORDER.index(old_d) else "easier"
        else:
            return (*resolve_level(brief, log), None)
    target = new_d if new_d in BAND_ORDER and new_d != old_d else None
    parent_path = STUDIO / prev["level"]["file"]
    parent = json.loads(parent_path.read_text())
    spec = Spec(shape=lv["shape"] if lv["shape"] in SHAPES else "open", width=parent["gridWidth"],
                height=parent["gridHeight"], blocks=len(parent["GridBlockDatas"]), colours=[],
                difficulty=target or ("hard" if rel == "harder" else "easy"), seed=gp["seed"] or 0, budget_s=20.0,
                pieces=lv["pieces"], style=list(lv["style"]), events=list(gp["events"]), finish=gp["finish"])
    key = _sha(json.dumps({"parent": prev["level"]["sha"], "dir": rel, "target": target, "spec": asdict(spec)},
                          sort_keys=True))[:12]
    folder = STUDIO / "levels"
    folder.mkdir(parents=True, exist_ok=True)
    path, meta_path = folder / f"edit_{key}.json", folder / f"edit_{key}.meta.json"
    if path.is_file() and meta_path.is_file():
        meta = json.loads(meta_path.read_text())
        log(f"the same level edit as before: level edit_{key} reused")
    else:
        log(f"editing v{prev['n']}'s board: the closest one that rates {rel}" + (f" (aiming for {target})" if target else "")
            + "...")
        got = edit_board(parent, spec, rel, target=target, log=log)
        if got is None:
            if target is None:
                B.engine_note(brief, "difficulty_pacing", f"no board within 3 small changes of this one rates {rel} and "
                                                          f"stays fair, so the level is kept")
                return parent_path, prev["level"]["why"], None
            B.engine_note(brief, "difficulty_pacing", f"no board within 3 small changes of this one rates {rel}; a new "
                                                      f"{target} level was generated instead")
            return (*resolve_level(brief, log), None)
        d, full, stats = got
        path.write_text(json.dumps(d, indent=2))
        meta = {"rating": asdict(full) | {"naive_ratio": round(full.naive_ratio, 3)}, "stats": stats}
        meta_path.write_text(json.dumps(meta, indent=1))
    rt, ed = meta["rating"], meta["stats"]["edit"]
    before = ed["from"]
    what = describe_changes(ed, rt["blocks"])
    if target and meta["stats"]["band"] != target:
        B.engine_note(brief, "difficulty_pacing", f"{what} rates {rel}, but not {target} ({meta['stats']['band']}); a "
                                                  f"new {target} board would change everything", status="adjusted")
    why = (f"v{prev['n']}'s level, made {rel}: {what}; {before['min_drags']} -> {rt['min_drags']} drags, "
           f"{before['extra_drags']} -> {rt['extra_drags']} repositioning, a casual player "
           f"{before['naive_mean'] / max(1, before['min_drags']):.2f}x -> {rt['naive_ratio']:.2f}x")
    edit = {"from_version": prev["n"], "direction": rel, "what": what, "blocks_moved": ed["blocks_moved"],
            "gates_moved": ed["gates_moved"], "blocks_recoloured": ed["blocks_recoloured"],
            "before": {k: before[k] for k in ("min_drags", "extra_drags", "exits_at_start")} | {"band": before["band"]},
            "after": {k: rt[k] for k in ("min_drags", "extra_drags", "exits_at_start")} | {"band": meta["stats"]["band"]}}
    return path, why, edit


def _changes_only(old: dict, new: dict) -> bool:
    """Whether a level edit names changes to the board itself (move a door, add or remove a wall),
    and nothing else about the level but, at most, its difficulty."""
    keys = (set(old) | set(new)) - {"changes", "edit", "difficulty"}
    return bool(new.get("changes")) and old.get("changes") != new.get("changes") and \
        all(old.get(k) == new.get(k) for k in keys)


def board_edit(brief: dict, prev: dict, log: Log) -> tuple[Path, str, dict]:
    """The board the version shows, with the changes the prompt names (boardedit), keeping the
    moves that are still legal on it. Raises ValueError, with the reason, when it cannot be done."""
    from .boardedit import apply, prefix_to_json
    from .difficulty import rate
    from .level import level_from_dict
    lv = brief["level"]
    done = prev["brief"]["level"].get("changes") or []
    todo = [c for c in lv["changes"] if c not in done]  # a change already made stays made
    parent = json.loads((STUDIO / prev["level"]["file"]).read_text())
    beats = json.loads((STUDIO / prev["recording"]["dir"] / "play.json").read_text())["beats"]
    easier = (lv.get("edit") or {}).get("dir") == "easier" or (
        BAND_ORDER.index(lv["difficulty"]) < BAND_ORDER.index(prev["brief"]["level"]["difficulty"])
        if lv["difficulty"] in BAND_ORDER and prev["brief"]["level"]["difficulty"] in BAND_ORDER else False)
    log(f"changing v{prev['n']}'s board: " + "; ".join(f"{c['op'].replace('_', ' ')}"
                                                        + (f" {c['colour'].lower()}" if c.get("colour") else "")
                                                        + (f" to the {c['side']}" if c.get("side") else "") for c in todo))
    d, info = apply(parent, todo, beats, easier=easier, log=log)
    key = _sha(json.dumps({"parent": prev["level"]["sha"], "changes": todo}, sort_keys=True))[:12]
    folder = STUDIO / "levels"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"board_{key}.json"
    path.write_text(json.dumps(d, indent=2))
    before, after = rate(level_from_dict(parent, name="before")), rate(level_from_dict(d, name="after"))
    k, n = info["kept"], info["of"]
    gp = brief["gameplay"]
    gp["prefix"] = prefix_to_json(info["prefix"]) if k else None
    B.engine_note(brief, "gameplay", f"the first {k} of {n} moves are kept exactly (still legal on the changed "
                                     f"board); only {'the rest is' if k < n else 'the ending is'} planned again", status=None)
    lv["difficulty"] = prev["brief"]["level"]["difficulty"]  # the board change decides it, and says how
    lv["edit"] = None
    why = (f"v{prev['n']}'s level with {info['what']}: {before.min_drags} -> {after.min_drags} drags, "
           f"{before.extra_drags} -> {after.extra_drags} repositioning, a casual player {before.naive_ratio:.2f}x -> "
           f"{after.naive_ratio:.2f}x")
    log(f"{info['what']}; the first {k} of {n} moves still work on it")
    edit = {"from_version": prev["n"], "direction": "as asked", "what": info["what"], "kept_moves": k, "of_moves": n,
            "before": {"min_drags": before.min_drags, "extra_drags": before.extra_drags,
                       "exits_at_start": before.exits_at_start},
            "after": {"min_drags": after.min_drags, "extra_drags": after.extra_drags,
                      "exits_at_start": after.exits_at_start}}
    return path, why, edit


def _replans(old: dict, new: dict) -> bool:
    """Whether an edit changes what the moves are (not only their pauses), on purpose or not, and
    did not ask for a new take."""
    o, n = old["gameplay"], new["gameplay"]
    return any(o[k] != n[k] for k in REPLAN) and o["seed"] == n["seed"]


def closest_seed(brief: dict, level_path: Path, prev_rec: Path, prev_n: int, log: Log,
                 seeds: int = 24, budget_s: float = 20.0) -> None:
    """A gameplay edit on a kept level re-plans the moves. Of the plays the planner can make for
    the new brief (one per seed), keep the one closest to the version being edited: the longest
    run of identical moves from the start, then the most moves in common, in order. The seed goes
    into the brief, so the recording can be made again."""
    from dataclasses import replace
    from .editreport import beat_key as _beat_key, common_moves
    from .events import SOLVER_ACTIONS, check_events, from_brief
    from .level import load_level
    level = load_level(level_path)
    target = [_beat_key(b) for b in json.loads((prev_rec / "play.json").read_text())["beats"]]
    # the asked order of interactions comes first: a plan that drops it (the planner falls back to no events
    # when a seed cannot do them) must not win on similarity (2026-10-18: "the purple block should leave first"
    # kept the closest play, where dark green left first)
    evs_all, _ = from_brief(level, brief["gameplay"]["events"])
    if brief["gameplay"]["ending"] in ("time_out", "cliffhanger"):
        evs_all = [replace(e, when="next") if e.when == "last" else e for e in evs_all]
    solver_evs = [e for e in evs_all if e.action in SOLVER_ACTIONS]
    cur = brief["gameplay"]["seed"] or 0
    t0, best, tried = time.time(), None, 0
    for s in [cur] + [x for x in range(seeds) if x != cur]:
        if best is not None and time.time() - t0 > budget_s:
            break
        try:
            script = _plan(brief, level, s)
        except ValueError:
            continue
        tried += 1
        sd = script.to_dict(level)
        mine = [_beat_key(b) for b in sd["beats"]]
        k, lcs = common_moves(target, mine)
        meets = not any("cannot happen" in n for n in script.notes)
        if meets and solver_evs:
            try:
                meets = check_events(level, solver_evs, script.drags, [b["kind"] for b in sd["beats"]]).ok
            except Exception:  # the check is a preference, never a crash
                pass
        score = (meets, k, lcs, s == cur)
        if best is None or score > best[0]:
            best = (score, s, len(mine))
    if best is None:
        return
    (meets, k, lcs, _), s, m = best
    if s != cur:
        brief["gameplay"]["seed"] = s
    B.engine_note(brief, "gameplay", f"of {tried} plays tried, the one closest to v{prev_n} is used: the first {k} "
                                     f"of {m} moves are the same, {lcs} of {m} in common"
                                     + ("" if meets else "; none of them does the asked order of moves on this level"), status=None)
    log(f"closest play to v{prev_n}: seed {s}, the first {k} of {m} moves the same, {lcs} in common ({tried} tried"
        + (")" if meets else "; none meets the asked order)"))


def same_frames(a: Path, b: Path) -> bool:
    """Whether two recordings show the same play on the same frames (the same recording, or the
    stored job filmed again with a new look)."""
    if a.resolve() == b.resolve():
        return True
    try:
        ra, rb = (json.loads((d / "result.json").read_text()) for d in (a, b))
    except (OSError, ValueError):
        return False
    keys = ("block", "cells", "result", "start_frame", "exit_frame", "end_frame")
    drags = lambda r: [{k: d.get(k) for k in keys} for d in r["drags"]]
    return (ra.get("frames") == rb.get("frames") and ra.get("status") == rb.get("status")
            and ra.get("win_frame") == rb.get("win_frame") and drags(ra) == drags(rb))


def same_drags(a: Path, b: Path, slack: int = 6) -> bool:
    """Whether two recordings play the same drags on the same frames, the end allowed to differ by a
    few frames: a door moved to another edge changes how long its block's exit slide takes before
    the win screen, not when anything is played."""
    try:
        ra, rb = (json.loads((d / "result.json").read_text()) for d in (a, b))
    except (OSError, ValueError):
        return False
    keys = ("block", "cells", "result", "start_frame", "exit_frame", "end_frame")
    drags = lambda r: [{k: d.get(k) for k in keys} for d in r["drags"]]
    return (drags(ra) == drags(rb) and ra.get("status") == rb.get("status")
            and abs(ra.get("frames", 0) - rb.get("frames", 0)) <= slack
            and abs((ra.get("win_frame") or 0) - (rb.get("win_frame") or 0)) <= slack)


def pin_of(prev: dict, brief: dict | None = None) -> dict:
    """The structure of a version's ad that an edit keeping its frames keeps: length, intro, replay,
    and how long the hook stayed on screen. add_replay: the edit turns the replay on (only then may
    a replay the user never saw appear)."""
    from .ad import seg_frames
    ad = json.loads((STUDIO / prev["ad_dir"] / "ad.json").read_text())
    seg = ad["segments"]
    hook_end = (ad.get("layers", {}).get("hook") or {}).get("end") or {}
    hold = 0
    if "result_hold" in ad["order"]:
        hold = seg_frames(seg["result_hold"])
    elif "question" in ad["order"]:
        hold = max(0, seg_frames(seg["question"]) - 2 * 30)  # the cliffhanger's question is 2 s plus any fill
    return {"n": prev["n"], "length_s": ad["length_s"], "hold": hold,
            "card": seg_frames(seg["end"]) if "end" in ad["order"] else 0,  # the end card the user saw is never "freed time"
            "intro": seg_frames(seg["intro"]) if "intro" in ad["order"] else 0,
            "replay_from": seg["replay"]["from"] if "replay" in ad["order"] else None,
            "hook_at": hook_end.get("at") if hook_end.get("seg") == "play" and "event" not in hook_end else None,
            "add_replay": bool(brief and brief["sequence"]["replay"] and not prev["brief"]["sequence"]["replay"])}


def _level_source(prev: dict) -> Path:
    """The file a version's level was made from, when it still exists unchanged (the game's own
    levels keep their name, and with it the HUD's number); else the version's copy."""
    src = prev["level"].get("source")
    copy = STUDIO / prev["level"]["file"]
    if not src:
        return copy
    p = Path(src) if Path(src).is_absolute() else REPO / src
    try:
        if p.is_file() and p.resolve() != copy.resolve() and _sha(p.read_bytes()) == prev["level"]["sha"]:
            return p
    except OSError:
        pass
    return copy


def _same_play(brief: dict, level_path: Path, prev: dict, log: Log) -> Path | None:
    """The parent's recording when this brief plans the very same moves on the same level, with
    the same look and pace (an edit whose only request could not change the play): nothing to
    record again, and nothing to compare frame by frame."""
    prev_dir = STUDIO / prev["recording"]["dir"]
    if not _usable(prev_dir) or prev["level"]["sha"] != _sha(level_path.read_bytes()):
        return None
    spec = _recording_spec(brief, level_path)
    try:
        pspec = json.loads((prev_dir / "spec.json").read_text())
        play = json.loads((prev_dir / "play.json").read_text())
    except (OSError, ValueError):
        return None
    plan_keys = ("events", "finish")
    versions = ("play", "deliberate")  # how the tool filmed, not what was asked: an edit keeps the version's own film
    core = lambda d: {k: v for k, v in d.items() if k not in plan_keys and k not in versions}  # noqa: E731
    if core(spec) != core(pspec) or any(k in pspec and k not in spec for k in plan_keys):
        return None
    if all(spec.get(k) == pspec.get(k) for k in plan_keys):
        if all(spec.get(k) == pspec.get(k) for k in versions):
            return None  # the same spec: ensure_recording finds it by its key
        # the same ask, filmed before a change to how the tool paces or presses: the approved film stays
        # (a picture edit re-recorded a whole ad and the report said timing and sound changed, 2026-10-15)
        log(f"the same play as v{prev['n']} (filmed with an earlier version of the player): its recording is reused")
        return prev_dir
    from .level import load_level
    try:
        script = _plan(brief, load_level(level_path), spec["seed"])
    except ValueError:
        return None
    moves = lambda beats: [(b.get("kind"), b.get("block"), tuple(map(tuple, b.get("path") or [])), bool(b.get("exits")))
                           for b in beats]
    if moves(script.to_dict(load_level(level_path))["beats"]) != moves(play.get("beats", [])):
        return None
    log(f"the same moves as v{prev['n']} on the same level: its recording is reused (nothing re-recorded)")
    return prev_dir


def _same_moves_new_board(brief: dict, level_path: Path, prev: dict, log: Log) -> Path | None:
    """A board edit that every move survives: the version's own job (the same drags, the same
    timing) played again on the changed board, so the ad keeps its timing frame for frame. None
    if the game does not play it the same way (then the play is planned again)."""
    from .render import compare_recordings, rerun_on
    src = STUDIO / prev["recording"]["dir"]
    if not _usable(src):
        return None
    spec = _recording_spec(brief, level_path)
    spec["job_of"] = src.name  # this recording replays that job: not the same thing as a new plan of these moves
    key = _sha(json.dumps(spec, sort_keys=True))[:16]
    out = STUDIO / "recordings" / key
    if _usable(out):
        log(f"same moves on the changed board: recording {key} (the job of {src.name} on it) reused")
        return out
    if out.exists():
        shutil.rmtree(out)
    log("every move still works on the changed board: the same job is played again on it (same drags, same timing)...")
    result = rerun_on(src, out, json.loads(level_path.read_text()))
    if result["problems"]:
        log(f"  the game did not play it the same way ({result['problems'][0]}); the play is planned again")
        shutil.rmtree(out, ignore_errors=True)
        return None
    shutil.copy(src / "play.json", out / "play.json")
    c = compare_recordings(src, out)
    # a moved door changes how its block slides out, not when: every drag must start, leave and
    # end on the same frame as before (same_frames), and then the ad keeps its timing
    if not (c.get("state_equal") or same_drags(src, out)):
        log("  the moves did not land on the same frames on the changed board; the play is planned again")
        shutil.rmtree(out, ignore_errors=True)
        return None
    (out / "spec.json").write_text(json.dumps(spec, indent=1))
    log(f"filmed {result['frames']} frames: every drag on the same frames as before"
        + ("" if c.get("state_equal") else " (a block leaves through its moved door)"))
    return out


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
        rec = json.loads(v.read_text())
        rec["brief"] = B._complete(rec["brief"])  # a version made before a field existed has its default
        out.append(rec)
    return out


def parent(cid: str | None, base: int | None = None) -> dict | None:
    """The version an edit follows: version `base`, or the latest; None for a new creative."""
    if not cid or not creative_dir(cid).is_dir():
        return None
    vs = versions(cid)
    if not vs:
        return None
    if base is None:
        return vs[-1]
    v = next((x for x in vs if x["n"] == base), None)
    if v is None:
        raise ValueError(f"{cid} has no version {base}")
    return v


def planner_context(cid: str, base: int | None = None) -> str:
    """What the planner is told about the version an edit starts from: its parts and the things
    in it (pictures, captions, sound)."""
    from .edits import describe_for_planner, outline
    v = parent(cid, base)
    if v is None:
        return ""
    d = STUDIO / v["ad_dir"]
    j = lambda f: json.loads((d / f).read_text()) if (d / f).is_file() else {}
    return outline(j("ad.json"), j("compose.json")) + "\n" + describe_for_planner(inventory(cid, v["n"]))


def part_lengths(cid: str, base: int | None = None) -> dict[str, float]:
    """How long each part of a version's ad runs, in seconds (0 for a part it does not have)."""
    v = parent(cid, base)
    if v is None:
        return {}
    c = STUDIO / v["ad_dir"] / "compose.json"
    tl = json.loads(c.read_text()).get("timeline", {}) if c.is_file() else {}
    out = {k: 0.0 for k in ("intro", "result_hold", "question", "end")}
    out.update({sid: round((t["frames"][1] - t["frames"][0]) / FPS, 2) for sid, t in tl.items()})
    return out


def history(cid: str, base: int | None = None) -> list[dict]:
    """The versions an edit of `base` descends from, newest first: {n, from, prompt, brief}."""
    vs = {v["n"]: v for v in versions(cid)}
    v = parent(cid, base)
    out = []
    while v is not None:
        out.append({"n": v["n"], "from": v.get("from"), "prompt": v["prompt"], "brief": v["brief"]})
        v = vs.get(v.get("from")) if v.get("from") else None
    return out


def parts(cid: str, base: int | None = None) -> dict | None:
    """A version's parts manifest (parts.json, or built now for a version made before it existed)."""
    from . import parts as P
    v = parent(cid, base)
    return None if v is None else P.load(v, STUDIO)


def inventory(cid: str, base: int | None = None) -> list[dict]:
    """The pictures, captions and sound of a version (the latest by default), for the planner and
    the UI's "Things in this ad"."""
    from .edits import inventory as inv
    v = parent(cid, base)
    if v is None:
        return []
    d = STUDIO / v["ad_dir"]
    j = lambda f: json.loads((d / f).read_text()) if (d / f).is_file() else {}
    return inv(j("ad.json"), j("compose.json"))


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


def _proof(prev: dict, cur: dict, groups: list[str], notes: list[str], asked_notes: list[str] | None = None) -> dict:
    """What an edit kept and changed, item by item (editreport), with the frame-level diff of the
    two renders when their timelines match."""
    from .compose import diff
    from .editreport import report
    pixels = None
    try:
        # a re-filmed recording differs everywhere by design: no pixel boxes to measure
        d = diff(STUDIO / prev["ad_dir"], STUDIO / cur["ad_dir"], boxes=prev["recording"]["dir"] == cur["recording"]["dir"])
    except ValueError as e:
        d = {"error": str(e)}
    if d.get("error"):
        pixels = {"note": f"not compared: {d['error']}"}
    elif d.get("changed_frames") is None:
        pixels = {"note": "the timeline changed, so frames are not compared one to one"}
    else:
        rs = d["changed_frames"]
        n = sum(b - a + 1 for a, b in rs)
        pixels = {"frames_changed": n, "frames": d["frames"][0], "ranges": rs[:8], "layers": d["layers_changed"],
                  "same_sound": d["same_sound"]}
        if d["same_sources"]:
            pixels["contained"] = d["contained"]
            pixels["box"] = d.get("measured_box")
        else:
            pixels["note"] = "the gameplay was filmed again with the new look, so its frames differ by design"
    try:  # the byte-level fact: how much of the approved video the new one carries unchanged
        pt = json.loads((STUDIO / cur["ad_dir"] / "compose.json").read_text()).get("patched") or {}
        if pt.get("frames_copied"):
            pixels = pixels or {}
            pixels["copied"] = {"frames": pt["frames_copied"], "of": pt["frames_copied"] + pt["frames_rendered"],
                                "gops_rendered": pt["gops_rendered"], "gops": pt["gops"]}
    except (OSError, ValueError):
        pass
    return report(prev, cur, STUDIO, groups, pixels=pixels, notes=notes, asked_notes=asked_notes)


KEEP_GROUPS = {"level": ("level.",), "gameplay": ("gameplay.",), "timing": ("pacing.",), "camera": ("visuals.zoom",),
               "visuals": ("visuals.",), "copy": ("concept.", "language"), "sequence": ("sequence",),
               "assets": ("assets",), "sound": ("audio",)}


KEEP_NAMES = {"level": ("level", "board"), "gameplay": ("gameplay", "moves", "play"),
              "timing": ("timing", "pace", "pacing", "length"), "camera": ("camera", "zoom", "framing"),
              "visuals": ("visuals", "look", "colours", "colors", "style"),
              "copy": ("copy", "text", "texts", "captions", "caption", "hook", "wording"),
              "sequence": ("sequence", "order", "structure"), "assets": ("assets", "logo", "pictures", "images"),
              "sound": ("sound", "audio")}


def _keep_conflicts(old: dict, new: dict, prompt: str = "") -> None:
    """A prompt can ask to keep something and change it in the same breath ("keep the level but
    make it harder": a harder level is a new level). The change wins; the brief says so. Only
    for what the prompt names ("keep the level"): "keep everything, but change X" is no conflict."""
    text = prompt.lower()
    for k in new.get("keep", []):
        names = "|".join(KEEP_NAMES.get(k, (k,)))
        clauses = re.split(r"[.,;!?]|\b(?:but|except|however|and then|then)\b", text)
        if not any(re.search(rf"\b(keep|same|preserve|unchanged|don't change|do not change)\b.*\b({names})\b", cl)
                   for cl in clauses):
            continue
        hit = [g for g, (_, paths) in B.GROUPS.items() if g.startswith(KEEP_GROUPS.get(k, ("-",)))
               and any(B._get(old, p) != B._get(new, p) for p in paths)]
        if hit:
            B.engine_note(new, "unchanged", f"asked to keep the {k}, but the prompt also changes it "
                                            f"({', '.join(hit)}); the change wins")


def go_without(brief: dict) -> list[str]:
    """The files the request named but did not attach (`needs`), dropped on the user's say-so: the
    assets row records that the ad was made without them. Returns what was dropped."""
    needs = list(brief.get("needs") or [])
    if needs:
        brief["needs"] = []
        B.engine_note(brief, "assets", f"made without {' and '.join(needs)} (not attached; the request said to go on "
                                       "without them).", status=None)
    return needs


def make(prompt: str, brief: dict, cid: str | None = None, log: Log | None = None, draft: bool = False,
         base: int | None = None, allow_missing: bool = False, asked: str | None = None,
         workflow: str | None = None) -> dict:
    """Make a version of a creative from a checked brief. With cid, the new version follows that
    creative's version `base` (default: the latest): an edit. Returns the version record (also
    saved as version.json). A brief that needs files the request did not attach (`needs`) is
    refused with the question, unless allow_missing: then the ad is made without them and says so.
    `asked`: the request the asked-facts audit measures against when it is not `prompt` itself (a
    revision round's feedback text is the prompt; the marketer's original request is what is audited)."""
    asked = asked or prompt
    if brief.get("needs") and not allow_missing:
        raise ValueError(f"this request uses files that are not attached: {' and '.join(brief['needs'])}. Attach them "
                         "and plan again, or say to make the ad without them.")
    log = log or Log(lambda line: print(f"[{line['stage']}] {line['text']}"))
    cid = cid or _new_id(prompt)
    folder = creative_dir(cid)
    prev = parent(cid, base)
    n = (versions(cid)[-1]["n"] + 1) if prev else 1
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
    go_without(brief)  # files the request named but did not attach: made without them, and the row says so
    if prev is not None:
        _keep_conflicts(prev["brief"], brief, prompt)
        if not B.changed_groups(prev["brief"], brief) and not (brief.get("planner") or {}).get("direct"):
            shutil.rmtree(vdir, ignore_errors=True)
            # what could not be done first: the engine's own refusals, then the planner's other reasons
            reasons = [r["why"] for r in brief["controls"] if r.get("why") and r["status"] == "not_supported"] or \
                [r["why"] for r in brief["controls"] if r.get("why")] + [a for a in brief.get("assumptions", [])
                                                                      if "no " in a.lower() or "not " in a.lower()]
            raise ValueError(f"nothing in this request changes v{prev['n']}, so no new version was made"
                             + (f" ({' '.join(reasons[:2])})" if reasons else "") + ". Say what to change: the hook "
                             f"or a caption, a picture (the logo, the icon beside the hook, the end card), the colours, "
                             f"the level, the ending, the mistakes, the length, the sound, or the language.")
    log.begin("level", "choosing the level...")
    level_edit = None
    lv = brief["level"]
    kept_prefix = brief["gameplay"].pop("prefix", None)  # valid only on the level it was kept for
    if prev is not None and lv.get("edit") and lv["edit"].get("of") is None:
        lv["edit"] = {**lv["edit"], "of": prev["n"]}  # relative to the version it is made from
    if prev is not None and prev["brief"]["level"] == brief["level"]:
        # An edit that does not ask about the level keeps the previous version's level exactly:
        # the file it was made from (its name gives the game's own levels their HUD number).
        level_path = _level_source(prev)
        level_why = prev["level"]["why"]
        stages.append({"stage": "level", "seconds": 0.0})
        log(f"the edit does not touch the level: v{prev['n']}'s level is kept")
        if kept_prefix and not _replans(prev["brief"], brief):
            brief["gameplay"]["prefix"] = kept_prefix  # the same play as before
    elif prev is not None and _changes_only(prev["brief"]["level"], brief["level"]):
        level_path, level_why, level_edit = stage("level", board_edit, brief, prev, log)
    elif prev is not None and _difficulty_only(prev["brief"]["level"], brief["level"]):
        level_path, level_why, level_edit = stage("level", edit_level, brief, prev, log)
        if level_edit is None and level_path == STUDIO / prev["level"]["file"] and \
                set(B.changed_groups(prev["brief"], brief)) <= {"level.difficulty"}:
            rel = (lv.get("edit") or {}).get("dir")
            if rel is None:  # the same difficulty and no direction: the F7 refusal, in its words
                raise ValueError(f"nothing in this request changes v{prev['n']}, so no new version was made. Say what "
                                 f"to change: the hook or a caption, a picture, the colours, the level, the ending, "
                                 f"the mistakes, the length, the sound, or the language.")
            from .difficulty import rate
            from .level import load_level
            r = rate(load_level(level_path), runs=40)
            floor = rel == "easier" and r.extra_drags == 0 and r.naive_ratio <= 1.02
            why = ("every block already leaves directly, so it is as easy as a level gets" if floor else
                   f"no board within 3 small changes of it rates {rel} and stays fair")
            raise ValueError(f"v{prev['n']}'s level cannot be made {rel} by small changes ({why}), and nothing else "
                             f"was asked, so no new version was made. Ask for a new level ('a new "
                             f"{('easy' if rel == 'easier' else 'hard')} level') to replace it.")
    else:
        level_path, level_why = stage("level", resolve_level, brief, log)
        if brief["level"]["source"] == "generate" and not draft:
            level_path, level_why = stage("level gate", _level_gate, asked, brief, level_path, level_why, log)
    if prev is not None and brief["level"]["label"] is None:
        # The HUD's "Level N" is part of the look: an edit keeps the number the user saw (a harder
        # board too), unless the prompt sets one.
        job = STUDIO / prev["recording"]["dir"] / "job.json"
        if job.is_file() and json.loads(job.read_text()).get("level_label"):
            brief["level"]["label"] = json.loads(job.read_text())["level_label"]
    shutil.copy(level_path, vdir / "level.json")
    log(f"level: {level_why}")
    if prev is None and not draft:
        _breathe_short_play(brief, level_path)  # a new creative only: an edit keeps its version's play
    board_picture(brief, level_path, vdir / "board.png")
    log.begin("recording", "gameplay...")
    if prev is not None and not brief["gameplay"].get("prefix") and (
            level_edit is not None or (prev["level"]["sha"] == _sha(level_path.read_bytes())
                                       and _replans(prev["brief"], brief))):
        stage("closest play", closest_seed, brief, level_path, STUDIO / prev["recording"]["dir"], prev["n"], log)
    same = _same_play(brief, level_path, prev, log) if prev is not None else None
    refilmed = False
    if same is None and level_edit and level_edit.get("kept_moves") and level_edit["kept_moves"] == level_edit.get("of_moves"):
        same = stage("recording", _same_moves_new_board, brief, level_path, prev, log)
        refilmed = same is not None
        if not refilmed:
            stages.pop()
    if same is not None:
        rec_dir, reused = same, not refilmed
        if not refilmed:
            stages.append({"stage": "recording", "seconds": 0.0})
    else:
        rec_dir, reused = stage("recording", ensure_recording, brief, level_path, log)
    checks = gameplay_and_level_checks(brief, rec_dir, level_path, log)
    log.begin("compose", "the ad...")
    ad_dir = vdir / "ad"
    timing = prev is not None and any(g in brief.get("changed", []) for g in ("sequence.timing",))
    if timing and "pacing.length" in brief["changed"]:
        # an asked opening or held result sets the length itself: the rest of the ad keeps its timing
        brief["pacing"]["length_s"] = prev["brief"]["pacing"]["length_s"]
        brief["changed"].remove("pacing.length")
    pin = None
    if (prev is not None and "pacing.length" not in brief.get("changed", [])
            and (same_frames(STUDIO / prev["recording"]["dir"], rec_dir)
                 or (refilmed and same_drags(STUDIO / prev["recording"]["dir"], rec_dir)))):
        pin = pin_of(prev, brief)
    patch_from = STUDIO / prev["ad_dir"] if (prev is not None and pin is not None and not draft) else None
    result = stage("compose", build_and_render, brief, rec_dir, ad_dir, log, draft, pin, patch_from,
                   (workflow or ("edit" if prev is not None else "create")) in ("create", "guided", "image_guided"))
    if timing and abs(result["duration_s"] - brief["pacing"]["length_s"]) > 1e-6:
        B.engine_note(brief, "difficulty_pacing", f"the ad is now {result['duration_s']:g} s "
                                                  f"(was {brief['pacing']['length_s']:g} s): only the asked part changed "
                                                  f"length", status=None)
        brief["pacing"]["length_s"] = result["duration_s"]
    rel = lambda p: str(Path(p).resolve().relative_to(STUDIO.resolve()))
    record = {
        "n": n, "id": cid, "prompt": prompt, "edit": prev is not None, "from": prev["n"] if prev else None,
        "brief": brief,
        "level": {"file": rel(vdir / "level.json"), "source": str(level_path.resolve().relative_to(REPO.resolve()))
                  if level_path.resolve().is_relative_to(REPO.resolve()) else str(level_path),
                  "why": level_why, "sha": _sha(level_path.read_bytes()),
                  **({"edit": level_edit} if level_edit else {})},
        "recording": {"dir": rel(rec_dir), "reused": reused},
        "board": rel(vdir / "board.png"), "checks": checks,
        "ad_dir": rel(ad_dir), "video": rel(ad_dir / (result.get("format") or {}).get("file", "ad.mp4")),
        "poster": rel(ad_dir / (result.get("format") or {}).get("poster", "poster.png")),
        **({"master": rel(ad_dir / "ad.mp4")} if result.get("format") else {}),
        "length_s": result["duration_s"], "qa": result["qa"], "stages": stages,
        "seconds": round(time.time() - t0, 1), "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "workflow": workflow or ("edit" if prev is not None else "create"),
    }
    try:  # the parts manifest: what an edit of this version is routed on (parts.py)
        from . import parts as P
        P.write(vdir, record, STUDIO)
        record["parts"] = rel(vdir / "parts.json")
    except Exception as e:  # never lose a made version over its manifest
        log(f"parts manifest skipped: {e}")
    try:  # the asked-facts audit and the game's rules, as checks the UI and the review see
        from . import audit
        record["evaluation"] = audit.workflow(brief, record)
        log(f"evaluation: {record['evaluation']['kind']} ({', '.join(record['evaluation']['groups'])})")
        extra = audit.rows(asked, brief, level_path, record, vdir, rec_dir)
        record["checks"] = checks + extra
        for c in extra:
            if c["status"] == "failed":
                log(f"{c['from']}: {c['check']}: {c['status']} ({c['detail']})")
        miss = audit.misses(extra)
        log(f"asked-facts audit: {len(extra) - len(miss)} of {len(extra)} measured points met" +
            (f"; missed: {', '.join(c['check'].split(': ', 1)[1] for c in miss)}" if miss else ""))
    except Exception as e:  # never lose a made version over the audit
        log(f"audit skipped: {e}")
    if prev is not None:
        log.begin("proof", "comparing with the previous version...")
        s0 = time.time()
        notes = [x for row in brief["controls"] for x in row.get("engine", [])]
        asked_ctl = {B.GROUPS[g][0] for g in brief.get("changed", []) if g in B.GROUPS}
        asked_notes = [x for row in brief["controls"] if row["control"] in asked_ctl for x in row.get("engine", [])]
        try:
            record["proof"] = _proof(prev, record, brief.get("changed", []), notes, asked_notes)
        except Exception as e:  # the version is made; a broken proof must not lose it
            record["proof"] = {"verdict": f"The edit report could not be made: {e}", "rows": [], "ok": False,
                               "asked": brief.get("changed", [])}
        try:  # did the result follow the route decided before planning (route.py)?
            from . import route as R
            rc = R.check((brief.get("planner") or {}).get("route"), record["proof"])
            if rc is not None:
                record["proof"]["route"] = rc
                log(f"route: {rc['evidence']}")
        except Exception as e:
            log(f"route check skipped: {e}")
        stages.append({"stage": "proof", "seconds": round(time.time() - s0, 1)})
        for row in record["proof"]["rows"]:
            log(f"  {row['title']}: {row['status'].replace('_', ' ')}")
        log(f"proof: {record['proof']['verdict']}")
        px = record["proof"].get("pixels") or {}
        if record["proof"]["rows"] and all(r["status"] == "kept" for r in record["proof"]["rows"]) and \
                px.get("frames_changed", 0) == 0 and not (brief.get("planner") or {}).get("keep_identical"):
            # Made, compared, and nothing differs: what was asked could not be done (the engine
            # says why), so no duplicate version is kept.
            shutil.rmtree(vdir, ignore_errors=True)
            why = [x for row in brief["controls"] for x in row.get("engine", [])] + \
                  [row["why"] for row in brief["controls"] if row.get("why") and row["status"] in ("not_supported", "adjusted")]
            raise ValueError(f"the result came out identical to v{prev['n']} in every item, so no new version was "
                             f"kept" + (f": {' '.join(dict.fromkeys(why))[:700]}" if why else ""))
    record["seconds"] = round(time.time() - t0, 1)
    (vdir / "brief.json").write_text(json.dumps(brief, indent=1))
    (vdir / "version.json").write_text(json.dumps(record, indent=1))
    log.begin("done", f"done in {record['seconds']:.0f} s")
    return record
