"""The evaluation rows added on 2026-10-16 for the brief's controls the audit did not measure (p.3:
visual elements, assets, the sequence of events, what should remain unchanged; p.5: a visually
interesting board; p.2: gameplay at the centre), the hesitations, the clock, the walls, the HUD
number, per-colour counts, a caption's moment, and the one-evaluation-per-workflow rule."""
import json
from pathlib import Path

import pytest

from cbj import audit
from cbj import brief as B

STUDIO = Path(__file__).parent.parent / "studio"


@pytest.mark.parametrize("prompt, key, want", [
    ("No wrong moves, but the player pauses twice while reading the passage.", "hesitations", 2),
    ("the player hesitates before the green move and again before the red move", "hesitations", 2),
    ("The player hesitates, corrects it and finishes cleanly.", "hesitations", 1),
    ("A clean solve with no hesitation and a 60-second clock.", "hesitations", 0),
    ("A clean solve with no hesitation and a 60-second clock.", "timer_s", 60),
    ("steady pacing, a generous 90-second clock and the win screen", "timer_s", 90),
    ("the last block leaves with two seconds on the clock", "timer_s", None),
    ("A clean solve with a 60-second clock and the win screen. 45-second portrait creative.", "length_s", 45.0),
    ("steady pacing, a generous 90-second clock and the win screen. 40-second portrait creative", "length_s", 40.0),
    ("a compact board with six colored blocks, several separate fixed walls and little free space", "walls", "several"),
    ("a compact board with six colored blocks, several separate fixed walls and little free space", "walls_separate", True),
    ("an open board with no walls in the way", "walls", 0),
    ("a 6x8 board with chunky mixed pieces, one wall tile in the middle", "walls", 1),
    ("Show level 47 in the HUD.", "label", 47),
    ("a 45-second portrait creative", "label", None),
    ("one block each of red, blue, green and yellow", "colour_counts", {"Red": 1, "Blue": 1, "Green": 1, "Yellow": 1}),
    ("two red blocks and one larger yellow block", "colour_counts", {"Red": 2, "Yellow": 1}),
    ("one red block is trapped near the centre", "colour_counts", {}),
    ("a pointing-hand cursor instead of the tap ring", "cursor", "hand"),
    ("no cursor at all", "cursor", "none"),
    ("Game assets and sound effects only, no music.", "music", False),
    ("upbeat music under the gameplay", "music", True),
    ("a soft beige background behind the board", "background", "beige"),
    ("a dark blue background", "background", "blue"),
    ("Show the win first, then how it happened, no slow-motion replay.", "sequence", {"result_first": True, "replay": False}),
    ("then the game's result screen and the end card", "sequence", {"end_card": True}),
    ("Cut the video there, no result screen, ending on the question", "sequence", {"result_screen": False}),
    ("Preserve the original game rules, HUD and block assets.", "original", True),
    ("clears the blue block, which gives the red block room to move", "style", []),
    ("an open board with room to move", "style", ["spacious"]),
    ("the game's own rules, HUD and block assets", "original", True),
    ("Keep the timer consistent and the game's rules and HUD unchanged.", "original", True),
])
def test_asked_reads_the_new_facts(prompt, key, want):
    assert audit.asked(prompt)[key] == want


def test_caption_moments_are_read_after_the_quote_first():
    a = audit.asked('caption "Wait... that\'s wrong!" on that move and "Found it!" on the correction. '
                    'Opening caption "Think ahead". Show the Out of Time screen with the caption "So close!". '
                    'Caption "Phew!" when the red block leaves and "Hurry!" in the last seconds; ending on the question "Can you finish it?"')
    got = {c["text"]: (c["moment"], c["colour"]) for c in a["caption_moments"]}
    assert got == {"Wait... that's wrong!": ("wrong_move", None), "Found it!": ("fix", None), "Think ahead": ("start", None),
                   "So close!": ("result", None), "Phew!": ("exit", "Red"), "Hurry!": ("end", None), "Can you finish it?": ("question", None)}


def test_a_blocking_arrangement_at_the_start_is_not_a_played_move():
    a = audit.asked("At the start the green block sits in the red block's route to its door. The player first moves the yellow block aside.")
    assert a["blocks_by"] is None and a["mistakes"] is None
    a = audit.asked("The red block cannot reach its door because a green block is in the way. No mistakes.")
    assert a["stuck_by"] is None and a["mistakes"] == 0
    a = audit.asked("The player first tries to drag the red block and it is stopped by the green block.")
    assert a["stuck_by"] == ("Red", "Green")
    a = audit.asked("The first tempting move puts the yellow block in the green block's way.")
    assert a["blocks_by"] == ("Yellow", "Green") and a["mistakes"] == 1


def _level(walls=(), timer=60, colours=(0, 1, 2, 3)):
    return {"gridWidth": 6, "gridHeight": 6, "timerCount": timer, "inactiveCells": [{"x": x, "y": y} for x, y in walls],
            "GridBlockDatas": [{"gridPosition": {"x": x, "y": 2}, "blockColor": c, "shapeOffsets": [{"x": 0, "y": 0}]}
                               for x, c in zip(range(len(colours)), colours)],
            "ExitDatas": [{"exitNumber": i, "requiredColor": c, "gridPosition": {"x": x, "y": 0}, "direction": 3,
                           "shapeOffsets": [{"x": 0, "y": 0}]} for i, (x, c) in enumerate(zip(range(len(colours)), colours))]}


def test_level_rows_walls_clock_and_colour_counts(tmp_path):
    path = tmp_path / "lvl.json"
    path.write_text(json.dumps(_level(walls=((0, 5), (5, 5)), timer=60)))
    b = B.check(B.default_brief())
    b["gameplay"].update(ending="win", timer_s=60)
    rows = {r["check"]: r for r in audit.level_rows(
        "several separate walls, a 60-second clock, one block each of green, yellow, blue and red, a clean solve", b, path)}
    assert rows["Asked: walls"]["status"] == "pass" and "2 separate group" in rows["Asked: walls"]["detail"]
    assert "Asked: the clock" not in rows  # the clock is read from the recording (ad rows), not the level file
    assert rows["Asked: blocks per colour"]["status"] == "pass"
    assert rows["Asked: a visually interesting board (the brief)"]["status"] == "info"
    path.write_text(json.dumps(_level(walls=((0, 5), (1, 5)), timer=45, colours=(0, 0, 2, 3))))
    rows = {r["check"]: r for r in audit.level_rows(
        "several separate walls, a 60-second clock, one block each of green, yellow, blue and red, a clean solve", b, path)}
    assert rows["Asked: walls"]["status"] == "failed"  # two cells, one group: not separate
    assert rows["Asked: blocks per colour"]["status"] == "failed" and "2 green" in rows["Asked: blocks per colour"]["detail"]


def _manifest():
    return {"duration_s": 40.0, "fps": 30,
            "parts": [{"id": "intro", "name": "opening", "kind": "still", "from_s": 0.0, "to_s": 0.5, "gameplay": False},
                      {"id": "play", "name": "gameplay", "kind": "gameplay", "from_s": 0.5, "to_s": 20.0, "gameplay": True},
                      {"id": "result", "name": "result", "kind": "result", "from_s": 20.0, "to_s": 22.5, "gameplay": False},
                      {"id": "end", "name": "end card", "kind": "card", "from_s": 22.5, "to_s": 40.0, "gameplay": False}],
            "layers": [{"id": "hook", "kind": "caption", "text": "Think ahead", "from_s": 0.0, "to_s": 2.0},
                       {"id": "cap_mistake", "kind": "caption", "text": "Wait... that's wrong!", "from_s": 3.0, "to_s": 5.0},
                       {"id": "cap_fix", "kind": "caption", "text": "Found it!", "from_s": 6.4, "to_s": 8.4},
                       {"id": "cap_hurry", "kind": "caption", "text": "Hurry!", "from_s": 15.0, "to_s": 19.5},
                       {"id": "cap_result", "kind": "caption", "text": "So close!", "from_s": 20.3, "to_s": 22.5}],
            "moments": [{"id": "drag_0", "kind": "mistake", "block": "yellow", "at_s": 3.2, "to_s": 3.6, "exit_s": None, "also": "wrong_move"},
                        {"id": "drag_1", "kind": "move", "block": "yellow", "at_s": 6.5, "to_s": 7.0, "exit_s": None},
                        {"id": "drag_2", "kind": "exit", "block": "red", "at_s": 10.0, "to_s": 10.6, "exit_s": 10.6},
                        {"id": "time_out", "kind": "time_out", "block": None, "at_s": 20.0, "to_s": None, "exit_s": None}]}


def test_caption_moment_rows_read_the_manifest():
    asked = audit.asked('Opening caption "Think ahead". Caption "Wait... that\'s wrong!" on that move and "Found it!" on the correction. '
                        'Caption "Phew!" when the red block leaves, "Hurry!" in the last seconds and "So close!" on the Out of Time screen.')
    rows = {r["check"]: r["status"] for r in audit._caption_moment_rows(asked["caption_moments"], _manifest())}
    assert rows == {'Asked: caption "Think ahead" at the start': "pass",
                    'Asked: caption "Wait... that\'s wrong!" on the wrong move': "pass",
                    'Asked: caption "Found it!" on the move after the wrong one (the correction)': "pass",
                    'Asked: caption "Hurry!" in the last seconds': "pass",
                    'Asked: caption "So close!" on the result': "pass"}  # "Phew!" is not on screen: its presence row says so
    m = _manifest()
    m["layers"][2]["from_s"], m["layers"][2]["to_s"] = 10.0, 12.0  # "Found it!" lands on red's exit, not on the correction
    rows = {r["check"]: r["status"] for r in audit._caption_moment_rows(asked["caption_moments"], m)}
    assert rows['Asked: caption "Found it!" on the move after the wrong one (the correction)'] == "failed"


def test_ad_rows_cursor_music_sequence_original_and_the_case(tmp_path):
    vdir = tmp_path / "v1"
    (vdir / "ad").mkdir(parents=True)
    (vdir / "parts.json").write_text(json.dumps(_manifest()))
    ad = {"order": ["intro", "play", "result", "end"], "audio": {"music": None},
          "layers": {"cursor": {"type": "cursor", "image": "builtin:hand"}, "hook": {"type": "text", "text": "Think ahead"}}}
    (vdir / "ad" / "ad.json").write_text(json.dumps(ad))
    (vdir / "ad" / "compose.json").write_text(json.dumps({"layers": {"hook": {"type": "text", "text": "Think ahead"}}}))
    rec = tmp_path / "rec"
    rec.mkdir()
    (rec / "play.json").write_text(json.dumps({"beats": [{"kind": "hesitate"}, {"kind": "solve"}, {"kind": "hesitate"}]}))
    (rec / "job.json").write_text(json.dumps({"level_label": 47}))
    (rec / "result.json").write_text(json.dumps({"timer_start": 90.0, "timer_end": 79.3}))
    b = B.check(B.default_brief())
    b["visuals"].update(cursor="hand")
    b["gameplay"].update(hesitations=2, ending="near_fail")
    b["level"].update(label=47)
    record = {"checks": [], "length_s": 40.0}
    prompt = ("a hand cursor, no music, no replay, with the end card, level 47, the player pauses twice; "
              "preserve the original game rules, HUD and block assets")
    rows = {r["check"]: r for r in audit.ad_rows(prompt, b, record, vdir, rec)}
    for k in ("Asked: cursor", "Asked: music", "Asked: the replay", "Asked: the end card", "Asked: HUD level number",
              "Asked: hesitations", "Asked: the game's own look", "Asked: gameplay at the centre (the brief)"):
        assert rows[k]["status"] == "pass", (k, rows[k])
    assert "55%" in rows["Asked: gameplay at the centre (the brief)"]["detail"]
    # the same ad against the opposite asks
    b["visuals"].update(cursor="ring", theme="neon", blocks=[{"slot": "Red", "hex": "#FF0000", "name": "red"}])
    b["sequence"].update(replay=True)
    prompt2 = "the tap ring cursor is fine, but add upbeat music and the slow-motion replay; level 12; the game's own look"
    rows = {r["check"]: r for r in audit.ad_rows(prompt2, b, record, vdir, rec)}
    assert rows["Asked: music"]["status"] == "failed" and rows["Asked: the replay"]["status"] == "failed"
    assert rows["Asked: HUD level number"]["status"] == "failed"
    assert rows["Asked: the game's own look"]["status"] == "failed" and "repainted" in rows["Asked: the game's own look"]["detail"]
    assert "Asked: cursor" not in rows  # "tap ring" alone asks nothing
    # the clock: read from the recording the game ran, and only measured on a win (2-clean, 2026-10-16)
    b["gameplay"].update(ending="win", timer_s=90)
    rows = {r["check"]: r for r in audit.ad_rows("a generous 90-second clock and the win screen", b, record, vdir, rec)}
    assert rows["Asked: the clock"]["status"] == "pass" and "90" in rows["Asked: the clock"]["detail"]
    b["gameplay"].update(timer_s=60)
    rows = {r["check"]: r for r in audit.ad_rows("a 60-second clock", b, record, vdir, rec)}
    assert rows["Asked: the clock"]["status"] == "failed" and rows["Asked: the clock"]["where"] == "play"
    # the play raised the clock for a stated reason (the HUD turns red under 0:50): reported, not a miss
    (rec / "play.json").write_text(json.dumps({"beats": [], "fit": {"why": "a clock of 60 s would show red for the whole play"}}))
    rows = {r["check"]: r for r in audit.ad_rows("a 60-second clock", b, record, vdir, rec)}
    assert rows["Asked: the clock"]["status"] == "info" and "red" in rows["Asked: the clock"]["detail"]
    (rec / "play.json").write_text(json.dumps({"beats": [{"kind": "hesitate"}, {"kind": "solve"}, {"kind": "hesitate"}]}))
    b["gameplay"].update(ending="near_fail", timer_s=None)
    rows = {r["check"]: r for r in audit.ad_rows("a 60-second clock", b, record, vdir, rec)}
    assert rows["Asked: the clock"]["status"] == "info"


def test_background_is_measured_on_the_poster(tmp_path):
    from PIL import Image
    vdir = tmp_path / "v1"
    (vdir / "ad").mkdir(parents=True)
    im = Image.new("RGB", (108, 192), (245, 245, 220))  # beige margins
    im.paste((30, 30, 30), (20, 40, 88, 150))  # a dark board in the middle
    im.save(vdir / "ad" / "poster.png")
    b = B.check(B.default_brief())
    b["visuals"]["background"] = ["#F5F5DC"]
    rows = {r["check"]: r for r in audit.ad_rows("a soft beige background behind the board", b, {"checks": [], "length_s": 30.0}, vdir)}
    assert rows["Asked: background"]["status"] == "pass" and "beige" in rows["Asked: background"]["detail"]
    rows = {r["check"]: r for r in audit.ad_rows("a dark blue background behind the board", b, {"checks": [], "length_s": 30.0}, vdir)}
    assert rows["Asked: background"]["status"] == "failed"


def test_one_evaluation_per_workflow():
    b = B.check(B.default_brief())
    b["planner"] = {"references": []}
    assert audit.workflow(b, {"workflow": "create", "edit": False})["groups"] == ["board", "play", "rules", "asked facts", "case"]
    b["planner"] = {"references": [{"file": "ref.mp4", "role": "reference"}]}
    wf = audit.workflow(b, {"workflow": "create"})
    assert wf["kind"] == "video" and "reference" in wf["groups"]
    wf = audit.workflow(b, {"workflow": "edit", "edit": True, "recording": {"reused": True}})
    assert wf["kind"] == "edit" and "rules" not in wf["groups"] and "case" not in wf["groups"]
    wf = audit.workflow(b, {"workflow": "edit", "edit": True, "recording": {"reused": False}})
    assert "rules" in wf["groups"]
    # a revision made inside a creation stays a creation (it is a new take, not an edit)
    assert audit.workflow(b, {"workflow": "create", "edit": True})["kind"] == "video"
    assert audit.misses([{"check": "Asked: gameplay at the centre (the brief)", "status": "failed", "from": "case"}])


# ---- the time-out's hidden last step (2026-10-16): the generator must fit it, the play must not drop the order

TIME_OUT_BOARD = {"gridWidth": 5, "gridHeight": 5, "timerCount": 60, "inactiveCells": [], "GridBlockDatas": [
    {"gridPosition": {"x": 1, "y": 4}, "blockColor": 2, "shapeOffsets": [{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 2, "y": 0}, {"x": 1, "y": -1}]},
    {"gridPosition": {"x": 0, "y": 2}, "blockColor": 3, "shapeOffsets": [{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 1, "y": -1}]},
    {"gridPosition": {"x": 0, "y": 0}, "blockColor": 0, "shapeOffsets": [{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 2, "y": 0}]},
    {"gridPosition": {"x": 2, "y": 2}, "blockColor": 1, "shapeOffsets": [{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 2, "y": 0}, {"x": 1, "y": -1}]}],
    "ExitDatas": [
    {"exitNumber": 0, "requiredColor": 2, "gridPosition": {"x": 1, "y": 0}, "direction": 3, "shapeOffsets": [{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 2, "y": 0}]},
    {"exitNumber": 0, "requiredColor": 3, "gridPosition": {"x": 0, "y": 4}, "direction": 2, "shapeOffsets": [{"x": 0, "y": 0}, {"x": 1, "y": 0}]},
    {"exitNumber": 0, "requiredColor": 0, "gridPosition": {"x": 0, "y": 2}, "direction": 0, "shapeOffsets": [{"x": 0, "y": 0}]},
    {"exitNumber": 0, "requiredColor": 1, "gridPosition": {"x": 4, "y": 0}, "direction": 1, "shapeOffsets": [{"x": 0, "y": 1}, {"x": 0, "y": 0}]}]}
TIME_OUT_EVENTS = [{"block": {"colour": "Red", "which": "any", "all": False}, "action": "stuck", "when": "first", "by": "Blue"},
                   {"block": {"colour": "Green", "which": "any", "all": False}, "action": "leaves", "when": "next"},
                   {"block": {"colour": "Blue", "which": "any", "all": False}, "action": "leaves", "when": "next"},
                   {"block": {"colour": "Red", "which": "any", "all": False}, "action": "leaves", "when": "next"}]


def _time_out_level():
    from cbj.level import level_from_dict
    return level_from_dict(TIME_OUT_BOARD, name="t2c_2_time_out_v2")


def test_generator_fits_the_time_out_last_step():
    """The real 2-time-out board: green, blue, red can leave in that order only if yellow leaves
    before red, so a time-out (which cuts an unnamed block short at the end) cannot show the order.
    The generator now rejects it for a time-out and still accepts it for a win."""
    from cbj.generate import Spec, _events_fit
    from cbj.solver import solve_fast
    lvl = _time_out_level()
    min_drags = solve_fast(lvl).min_drags
    assert _events_fit(lvl, Spec(events=TIME_OUT_EVENTS, time_out=False), min_drags) is not None
    assert _events_fit(lvl, Spec(events=TIME_OUT_EVENTS, time_out=True), min_drags) is None


def test_play_keeps_the_order_when_only_the_last_step_fails():
    """On that board the play used to drop the whole order (yellow first, then red, then green). Now it
    keeps green before blue before red and says which step is cut short."""
    from cbj.events import from_brief
    from cbj.play import plan
    lvl = _time_out_level()
    evs, _ = from_brief(lvl, TIME_OUT_EVENTS)
    script = plan(lvl, "time_out", mistakes=1, seed=1, events=evs)
    from cbj.describe import color_name
    exits = [color_name(lvl.blocks[b.drag.block].color).lower() for b in script.beats if b.drag.exits]
    assert exits.index("green") < exits.index("blue")
    assert any("cut short" in n for n in script.notes)


# ---- the named blocker (2026-10-16): a colour relabel makes the asked block the one in the way

STUCK_BOARD = {"gridWidth": 6, "gridHeight": 8, "timerCount": 60,
               "inactiveCells": [{"x": 0, "y": 3}, {"x": 0, "y": 4}, {"x": 1, "y": 3}, {"x": 1, "y": 4}, {"x": 4, "y": 3}, {"x": 4, "y": 4}, {"x": 5, "y": 3}, {"x": 5, "y": 4}],
               "GridBlockDatas": [
                   {"gridPosition": {"x": 5, "y": 7}, "blockColor": 4, "shapeOffsets": [{"x": 0, "y": 0}]},
                   {"gridPosition": {"x": 4, "y": 2}, "blockColor": 2, "shapeOffsets": [{"x": 0, "y": 0}, {"x": 0, "y": -1}, {"x": 1, "y": -1}]},
                   {"gridPosition": {"x": 2, "y": 5}, "blockColor": 0, "shapeOffsets": [{"x": 0, "y": 0}, {"x": 0, "y": -1}, {"x": 1, "y": -1}]},
                   {"gridPosition": {"x": 1, "y": 7}, "blockColor": 1, "shapeOffsets": [{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 2, "y": 0}, {"x": 1, "y": -1}]},
                   {"gridPosition": {"x": 2, "y": 3}, "blockColor": 5, "shapeOffsets": [{"x": 0, "y": 0}, {"x": 0, "y": -1}]},
                   {"gridPosition": {"x": 0, "y": 1}, "blockColor": 3, "shapeOffsets": [{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 1, "y": -1}]}],
               "ExitDatas": [
                   {"exitNumber": 0, "requiredColor": 4, "gridPosition": {"x": 3, "y": 0}, "direction": 3, "shapeOffsets": [{"x": 0, "y": 0}]},
                   {"exitNumber": 0, "requiredColor": 2, "gridPosition": {"x": 5, "y": 5}, "direction": 1, "shapeOffsets": [{"x": 0, "y": 0}, {"x": 0, "y": 1}]},
                   {"exitNumber": 0, "requiredColor": 0, "gridPosition": {"x": 0, "y": 0}, "direction": 3, "shapeOffsets": [{"x": 0, "y": 0}, {"x": 1, "y": 0}]},
                   {"exitNumber": 0, "requiredColor": 1, "gridPosition": {"x": 3, "y": 7}, "direction": 2, "shapeOffsets": [{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 2, "y": 0}]},
                   {"exitNumber": 0, "requiredColor": 5, "gridPosition": {"x": 0, "y": 7}, "direction": 2, "shapeOffsets": [{"x": 0, "y": 0}]},
                   {"exitNumber": 0, "requiredColor": 3, "gridPosition": {"x": 5, "y": 0}, "direction": 1, "shapeOffsets": [{"x": 0, "y": 0}, {"x": 0, "y": 1}]}]}
STUCK_EVENTS = [{"block": {"colour": "Red", "which": "any", "all": False}, "action": "stuck", "when": "first", "by": "Green"},
                {"block": {"colour": "Yellow", "which": "any", "all": False}, "action": "moves", "when": "next"},
                {"block": {"colour": "Green", "which": "any", "all": False}, "action": "leaves", "when": "next"},
                {"block": {"colour": "Blue", "which": "any", "all": False}, "action": "moves", "when": "next"},
                {"block": {"colour": "Red", "which": "any", "all": False}, "action": "leaves", "when": "next"}]


def test_the_named_blocker_is_made_by_a_colour_relabel():
    """The real 1-time-out board offers red stopped by blue when the request said green: swapping
    blue and green on the blocks and their doors keeps the puzzle and gives the asked blocker."""
    from cbj.generate import Spec, named_blocker_swap, relabel_colours
    from cbj.level import level_from_dict
    from cbj.play import blocked_attempts
    from cbj.rules import initial_state
    lvl = level_from_dict(STUCK_BOARD, name="t2c_1_time_out_v1")
    spec = Spec(events=STUCK_EVENTS, time_out=True)
    swap = named_blocker_swap(lvl, spec)
    assert swap == (2, 0)  # blue stops red; green was asked
    lvl2 = level_from_dict(relabel_colours(STUCK_BOARD, *swap), name="relabelled")
    red = next(i for i, b in enumerate(lvl2.blocks) if int(b.color) == 3)
    blockers = {int(lvl2.blocks[b].color) for d, b in blocked_attempts(lvl2, initial_state(lvl2)) if d.block == red}
    assert 0 in blockers  # green is now the block in red's way
    assert named_blocker_swap(lvl2, spec) is None
    assert len(lvl2.exits) == len(lvl.exits) and {int(e.color) for e in lvl2.exits} == {int(e.color) for e in lvl.exits}


def test_a_revision_keeps_the_asked_length_and_ending():
    """A revised plan may not drift off what the request fixed (2-time-out's third round came back at 30 s)."""
    from cbj.workflows.create import keep_asked
    before = B.check(B.default_brief()); before["pacing"]["length_s"] = 40.0; before["gameplay"]["ending"] = "time_out"
    after = B.check(B.default_brief()); after["pacing"]["length_s"] = 30.0; after["gameplay"]["ending"] = "near_fail"
    after["changed"] = ["pacing.length"]
    notes = keep_asked("a 40-second portrait creative where the clock runs out", before, after)
    assert after["pacing"]["length_s"] == 40.0 and after["gameplay"]["ending"] == "time_out" and len(notes) == 2
    assert "pacing.length" not in after["changed"]
    after["pacing"]["length_s"] = 30.0
    assert keep_asked("a creative with no length given", before, after) == [] and after["pacing"]["length_s"] == 30.0
