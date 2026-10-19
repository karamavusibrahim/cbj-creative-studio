"""Core requirement 5, İbrahim's control & consistency scenarios (CC-01..CC-44): the pieces they
needed. Board edits that keep the still-legal moves, music as its own stem, a picture behind the
board, other formats from the master, asked timing, one caption's colour, timed punch-ins, undo,
and honest refusals (block art, borders, self-contradicting locks, earlier uploads)."""

import copy
import json
import math
import wave
from pathlib import Path

import numpy as np
import pytest

from cbj import brief as B
from cbj import planner
from cbj.level import level_from_dict
from cbj.play import plan
from cbj.solver import solve_fast

from test_text_to_creative import FakeModel, raw_brief


# ---------- a small board, its play ----------

def _board() -> dict:
    """6x6, a 2x2 wall in the middle; blue (2 cells, left) must pass green to reach its right gate."""
    blk = lambda c, x, y, offs: {"gridPosition": {"x": x, "y": y}, "blockColor": c,
                                 "shapeOffsets": [{"x": a, "y": b} for a, b in offs]}
    gate = lambda c, x, y, d, offs: {"exitNumber": 0, "requiredColor": c, "gridPosition": {"x": x, "y": y}, "direction": d,
                                     "shapeOffsets": [{"x": a, "y": b} for a, b in offs]}
    return {"gridWidth": 6, "gridHeight": 6, "timerCount": 60,
            "inactiveCells": [{"x": 2, "y": 2}, {"x": 3, "y": 2}, {"x": 2, "y": 3}, {"x": 3, "y": 3}],
            "GridBlockDatas": [blk(1, 5, 1, [(0, 0), (0, 1)]),            # yellow, beside its gate
                               blk(2, 0, 4, [(0, 0), (1, 0)]),            # blue, h2
                               blk(3, 1, 0, [(0, 0), (0, 1)]),            # red, v2
                               blk(0, 3, 4, [(0, 0), (1, 0), (0, 1)])],   # green, L
            "ExitDatas": [gate(1, 5, 1, 1, [(0, 0), (0, 1), (0, 2)]),
                          gate(2, 5, 4, 1, [(0, 0)]),
                          gate(3, 1, 5, 2, [(0, 0)]),
                          gate(0, 0, 0, 3, [(0, 0), (1, 0)])]}


def _beats(d: dict) -> list[dict]:
    L = level_from_dict(d, name="t")
    return plan(L, "win").to_dict(L)["beats"]


def test_moving_a_gate_keeps_every_move_that_still_works():
    from cbj.boardedit import apply
    d = _board()
    beats = _beats(d)
    new, info = apply(d, [{"op": "move_gate", "colour": "Blue", "side": "top"}], beats)
    gate = new["ExitDatas"][1]
    assert gate["direction"] == 2 and all(o["y"] == 0 for o in gate["shapeOffsets"])  # on the top edge now
    assert gate["gridPosition"]["y"] == 5
    L = level_from_dict(new, name="t")
    assert solve_fast(L) is not None
    assert 0 < info["kept"] < info["of"]  # the start of the play stays; the blue exit is planned again
    assert "blue door moved from the right edge to the top edge" in info["what"]
    # the rest is planned from where the kept moves leave the board
    script = plan(L, "win", prefix=info["prefix"])
    first = [(b.drag.block, b.drag.path) for b in script.beats[:info["kept"]]]
    assert first == [(s[1].block, s[1].path) for s in info["prefix"]]


def test_a_door_cannot_be_moved_where_it_already_is_or_with_no_colour():
    from cbj.boardedit import apply
    d = _board()
    with pytest.raises(ValueError, match="already on the right edge"):
        apply(d, [{"op": "move_gate", "colour": "Blue", "side": "right"}], _beats(d))
    with pytest.raises(ValueError, match="no orange door"):
        apply(d, [{"op": "move_gate", "colour": "Orange", "side": "top"}], _beats(d))


def test_a_wall_goes_on_the_named_route_or_is_refused_with_the_reason():
    from cbj.boardedit import apply
    d = _board()
    beats = _beats(d)
    new, info = apply(d, [{"op": "add_wall", "colour": "Red"}], beats)
    added = {(c["x"], c["y"]) for c in new["inactiveCells"]} - {(c["x"], c["y"]) for c in d["inactiveCells"]}
    assert len(added) == 1 and "on the red block's route" in info["what"]
    assert solve_fast(level_from_dict(new, name="t")) is not None
    # yellow only steps into its own gate: its route has no empty tile
    with pytest.raises(ValueError, match="no empty tile for a wall"):
        apply(d, [{"op": "add_wall", "colour": "Yellow"}], beats)


def test_removing_a_wall_keeps_the_whole_old_solve():
    from cbj.boardedit import apply
    d = _board()
    beats = _beats(d)
    new, info = apply(d, [{"op": "remove_wall"}], beats, easier=True)
    assert len(new["inactiveCells"]) == 3 and info["kept"] == info["of"]
    open_board = {**d, "inactiveCells": []}
    with pytest.raises(ValueError, match="no walls to remove"):
        apply(open_board, [{"op": "remove_wall"}], _beats(open_board))


# ---------- the brief ----------

def test_music_and_a_background_picture_must_be_uploaded_files():
    ups = {"track.wav": Path("x.wav"), "bg.png": Path("bg.png")}
    b = B.check(raw_brief(audio={"sfx": True, "music": "track.wav"}, visuals={"background_image": "bg.png"}), ups)
    assert b["audio"]["music"] == "track.wav" and b["visuals"]["background_image"] == "bg.png"
    b = B.check(raw_brief(audio={"sfx": True, "music": "bg.png"}, visuals={"background_image": "track.wav"}), ups)
    assert b["audio"]["music"] is None and b["visuals"]["background_image"] is None
    b = B.check(raw_brief(assets=[{"file": "track.wav", "role": "logo", "when": "whole", "where": "auto"}]), ups)
    assert b["assets"] == [] and "sound file" in B.control(b, "assets")["why"]


def test_new_timing_and_camera_fields_are_clamped():
    b = B.check(raw_brief(sequence={"intro_s": 12, "hold_s": -1, "caption_times": [{"caption": "hook", "start_s": 1, "end_s": 0}]},
                          visuals={"camera_zoom": 1.0, "punch_ins": [{"from_s": 7, "to_s": 8.5, "zoom": 0.08, "toward": "Red"}],
                                   "caption_colours": [{"caption": "hook", "fill": "#ffe600"}]}))
    assert b["sequence"]["intro_s"] == 6.0 and b["sequence"]["hold_s"] == 0.0
    assert b["sequence"]["caption_times"] == [{"caption": "hook", "start_s": 1.0, "end_s": 0.0}]
    assert b["visuals"]["camera_zoom"] is None  # 1.0 is the game's own framing: no fake change
    assert b["visuals"]["punch_ins"] == [{"from_s": 7.0, "to_s": 8.5, "zoom": 1.08, "toward": "Red"}]
    assert b["visuals"]["caption_colours"] == [{"caption": "hook", "fill": "#FFE600"}]


def test_a_corner_sticker_is_the_corner_picture():
    assert B.asset_slot({"role": "sticker", "when": "whole", "where": "top_left"}) == "logo"
    assert B.asset_slot({"role": "sticker", "when": "hook", "where": "beside_hook"}) == "hook_icon"


# ---------- planner rules ----------

def _cur(**sections):
    return B.check(raw_brief(**sections))


def test_a_picture_on_a_block_is_refused_and_nothing_is_repainted():
    from cbj.planner import _block_art
    cur = _cur()
    b = copy.deepcopy(cur)
    b["visuals"]["blocks"] = [{"slot": "Red", "hex": "#FF8915", "name": "gold-edged red"}]
    b["assets"] = [{"file": "gold.png", "role": "sticker", "when": "whole", "where": "auto"}]
    b["changed"] = ["visuals.colours", "assets"]
    _block_art(b, "There are two red blocks on the board. Replace the red block with the gold-edged version. Keep "
                  "everything else exactly the same.", cur, ["gold.png"])
    # since 2026-10-15 a picture on a block of a colour is the skin slot (composited on the block's cells on
    # every frame); the block itself is still never repainted or replaced
    assert b["visuals"]["blocks"] == [] and "visuals.colours" not in b["changed"]
    assert b["assets"] == [{"file": "gold.png", "role": "skin", "when": "whole", "where": "auto", "block": "Red"}]
    assert B.control(b, "assets")["status"] == "applied"
    b2 = copy.deepcopy(cur); b2["changed"] = []
    _block_art(b2, "Use the supplied L-shaped graphic to replace this small rectangular blue block", cur, ["l.png"])
    assert next(a for a in b2["assets"] if a.get("role") == "skin")["block"] == "Blue"
    door = copy.deepcopy(cur); door["assets"] = [{"file": "gold.png", "role": "sticker", "when": "whole", "where": "auto"}]; door["changed"] = ["assets"]
    _block_art(door, "Put the attached gold texture on the red door.", cur, ["gold.png"])
    assert door["assets"] == [] and B.control(door, "visuals")["status"] == "not_supported"
    b3 = copy.deepcopy(cur); b3["visuals"]["blocks"] = [{"slot": "Red", "hex": "#9B30FF", "name": "purple"}]
    _block_art(b3, "I want the red block to be purple instead.", cur, [])
    assert b3["visuals"]["blocks"]  # a colour change is not block art


def test_a_border_request_is_answered_and_the_picture_not_put_elsewhere():
    from cbj.planner import _no_border
    cur = _cur()
    b = copy.deepcopy(cur)
    b["assets"] = [{"file": "border.png", "role": "end_background", "when": "end_card", "where": "auto"}]
    b["changed"] = ["assets"]
    _no_border(b, "Set the decorative border to the supplied blue border.", cur, ["border.png"])
    assert b["assets"] == [] and "no decorative border" in B.control(b, "assets")["why"]


def test_x_before_y_is_an_order_between_blocks_not_the_first_move():
    from cbj.planner import _relative_order
    b = _cur(gameplay={"events": [{"block": {"colour": "Blue", "which": "any", "all": False}, "action": "leaves", "when": "first"},
                                  {"block": {"colour": "Yellow", "which": "any", "all": False}, "action": "leaves", "when": "next"}]})
    _relative_order(b, "I want the blue block to exit before the yellow block.")
    assert b["gameplay"]["events"][0]["when"] == "next"
    b2 = _cur(gameplay={"events": [{"block": {"colour": "Yellow", "which": "any", "all": False}, "action": "moves", "when": "first"}]})
    _relative_order(b2, "Start by moving yellow aside before the blue one leaves.")
    assert b2["gameplay"]["events"][0]["when"] == "first"


def test_changing_the_puzzle_while_locking_every_frame_is_a_contradiction():
    from cbj.planner import _impossible_locks
    cur = _cur()
    b = copy.deepcopy(cur)
    b["level"]["changes"] = [{"op": "move_gate", "colour": "Blue", "side": "opposite", "column": None, "row": None}]
    b["changed"] = ["level.changes"]
    _impossible_locks(b, "Move the blue door to the opposite side of the puzzle, but keep every block trajectory, every "
                         "gameplay pixel, all object coordinates, the win state, and the complete video exactly identical.", cur)
    assert b["level"]["changes"] == [] and b["changed"] == []
    assert "contradicts itself" in B.control(b, "unchanged")["why"]
    b2 = copy.deepcopy(cur); b2["level"]["difficulty"] = "hard"; b2["changed"] = ["level.difficulty"]
    _impossible_locks(b2, "Make the puzzle significantly harder, but do not change the board, obstacles, doors, timer, "
                          "allowed movements, solution sequence, pacing, or any frame of the creative.", cur)
    assert b2["level"]["difficulty"] == cur["level"]["difficulty"] and b2["changed"] == []
    b3 = copy.deepcopy(cur); b3["level"]["changes"] = b["level"]["changes"] or [{"op": "move_gate", "colour": "Blue",
                                                                                 "side": "top", "column": None, "row": None}]
    b3["changed"] = ["level.changes"]
    _impossible_locks(b3, "Move only the blue exit door to the top edge. Keep the other blocks, doors, colors and camera.", cur)
    assert b3["changed"] == ["level.changes"]  # a plain edit is not a contradiction


def test_a_colour_swap_repaints_and_keeps_the_board():
    from cbj.planner import _recolour_keeps_board
    cur = _cur(level={"colours": ["Red", "Blue", "Yellow", "Green"]})
    b = copy.deepcopy(cur)
    b["level"]["colours"] = ["Purple", "Blue", "Yellow", "Green"]
    b["changed"] = ["level.colours"]
    _recolour_keeps_board(b, "I want the red block to be purple instead.", cur)
    assert b["level"]["colours"] == cur["level"]["colours"] and "level.colours" not in b["changed"]
    assert b["visuals"]["blocks"] == [{"slot": "Red", "hex": B.GAME_HEX["Purple"], "name": "purple"}]


def test_undo_restores_only_the_named_change_from_the_version_chain():
    from cbj.planner import _undo
    v1 = B.check(raw_brief(audio={"sfx": True, "music": "a.wav"}, concept={"end_title": "Can you solv it?"}),
                 {"a.wav": Path("a.wav"), "b.wav": Path("b.wav")})
    v2 = copy.deepcopy(v1); v2["assets"] = [{"file": "logo_a.png", "role": "end_art", "when": "end_card", "where": "end_card"}]
    v3 = copy.deepcopy(v2); v3["concept"]["end_title"] = "Try This Puzzle"
    v4 = copy.deepcopy(v3); v4["audio"]["music"] = "b.wav"
    hist = [{"n": 4, "brief": v4, "prompt": "music B"}, {"n": 3, "brief": v3, "prompt": "title"},
            {"n": 2, "brief": v2, "prompt": "logo"}, {"n": 1, "brief": v1, "prompt": "original"}]
    b = copy.deepcopy(v4); b["changed"] = []
    _undo(b, "Undo only the music replacement from the most recent version. Keep the new logo and corrected headline.", v4, hist)
    assert b["audio"]["music"] == "a.wav" and b["changed"] == ["audio.music"]
    assert b["assets"] == v4["assets"] and b["concept"]["end_title"] == "Try This Puzzle"
    lines = planner._history_lines(hist)
    assert "v4 (from v3)" in lines and "the music" in lines


def test_attached_files_are_used_and_earlier_uploads_are_not_guessed():
    from cbj.planner import _music_from_attachment, _only_mentioned_uploads
    raw = raw_brief(assets=[{"file": "blue_fingertip_pointer.png", "role": "cursor", "when": "whole", "where": "auto"},
                            {"file": "logo_square.png", "role": "logo", "when": "whole", "where": "auto"}])
    ups = {"blue_fingertip_pointer.png": Path("a"), "logo_square.png": Path("b")}
    _only_mentioned_uploads(raw, "replace the hand cursor with the supplied blue fingertip pointer", ups, None,
                            attached=["blue_fingertip_pointer.png"])
    assert [a["file"] for a in raw["assets"]] == ["blue_fingertip_pointer.png"]  # the earlier upload was a guess
    assert "uploaded earlier" in B.control(raw, "assets")["why"]
    b = _cur(); b["changed"] = []
    _music_from_attachment(b, "Replace only the background music with the supplied upbeat track.", ["up.wav"])
    assert b["audio"]["music"] == "up.wav" and "audio.music" in b["changed"]


# ---------- the ad ----------

def _wav(path: Path, seconds: float, hz: float = 440.0) -> Path:
    t = np.arange(int(seconds * 48000)) / 48000
    x = (0.5 * np.sin(2 * np.pi * hz * t) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(48000); w.writeframes(x.tobytes())
    return path


def test_music_is_mixed_under_the_effects_trimmed_looped_and_faded(tmp_path):
    from cbj.compose import mix_music, music_seconds
    f = _wav(tmp_path / "m.wav", 1.5)
    assert abs(music_seconds(f.read_bytes(), ".wav") - 1.5) < 0.01
    assert music_seconds(b"not audio", ".wav") is None
    effects = np.zeros(int(4 * 48000) + 1)
    track = mix_music(effects, {"file": str(f), "gain": 0.35, "fade_out_s": 1.0})
    assert len(track) == len(effects)  # looped to the ad's length
    assert abs(track[-1]) < 1e-3 and np.abs(track[48000:96000]).max() > 0.1  # faded at the end, heard before


def test_zoom_keeps_the_anchor_and_the_cursor_follows():
    from cbj.compose import _Zoomed, zoom_frame
    f = np.zeros((200, 100, 3), np.uint8)
    f[100, 50] = 255
    z = zoom_frame(f, 1.5, 50, 100)
    assert z[100, 50].max() > 100  # the anchor stays where it was
    z[0, 0] = 1  # writable: the layers are drawn into it
    class P:  # a placer at scale 1
        fit = {"scale": 1.0, "x": 0, "y": 0}
        def point(self, x, y): return x, y
    zp = _Zoomed(P(), 2.0, 50, 100)
    assert zp.point(60, 100) == (70, 100) and zp.fit["scale"] == 2.0


def test_another_format_crops_to_the_content_and_never_cuts_the_board():
    from cbj.formats import plan as fplan
    compose = {"layers": {"hook": {"box": [221, 258, 859, 468]}},
               "timeline": {"play": {"fit": {"scale": 0.75, "x": 135, "y": 318}}, "replay": {"fit": {"scale": 1.0, "x": 0, "y": 0}}}}
    p = fplan(compose, "1:1")
    x0, y0, x1, y1 = p["window"]
    assert y0 <= 217 and y1 >= 1573 and x0 == 0 and x1 == 1080  # the full-size replay's board and HUD are inside
    assert p["size"] == [1080, 1080] and p["content"][3] <= 1080 and p["content"][2] < 1080


def test_a_still_opening_frame_is_not_the_result_shown_first():
    from cbj.planner import _still_opening
    b = _cur(sequence={"style": "result_first"}); b["changed"] = ["sequence"]
    _still_opening(b, "Make a 35-second ad: open on a still frame with the headline 'Can you beat this level?', then the gameplay.")
    assert b["sequence"]["style"] == "standard" and b["sequence"]["intro_s"] == 2.5 and "sequence.timing" in b["changed"]
    b2 = _cur(sequence={"style": "result_first"}); b2["changed"] = ["sequence"]
    _still_opening(b2, "Show the win first, then open on a still frame of the board.")
    assert b2["sequence"]["style"] == "result_first"


def test_a_file_that_is_not_attached_is_asked_for():
    from cbj.planner import _missing_attachment
    cur = _cur(assets=[{"file": "CoinPile.png", "role": "end_art", "when": "end_card", "where": "end_card"}])
    b = copy.deepcopy(cur)
    b["assets"] = [{"file": "logo_square.png", "role": "end_art", "when": "end_card", "where": "end_card"}]
    b["changed"] = ["assets"]
    _missing_attachment(b, "Keep this approved creative unchanged and replace the logo with the image I uploaded "
                           "yesterday. I have not attached the image to this request.", [], cur)
    assert b["assets"] == cur["assets"] and "not attached" in B.control(b, "assets")["why"] and b["needs"] == ["image"]


def test_a_transition_request_is_answered():
    from cbj.planner import _no_transitions
    b = _cur()
    _no_transitions(b, "Change only the transition from gameplay to the final CTA from a dissolve to a direct cut.")
    assert "cut directly" in B.control(b, "sequence")["why"]
    b2 = _cur()
    _no_transitions(b2, "Trim or fade the new music at the same endpoints.")
    assert not B.control(b2, "sequence")["why"]


def test_the_same_absolute_request_twice_changes_nothing():
    cur = _cur(visuals={"background": ["#BFD7FF"]})
    hist = [{"n": 2, "prompt": "Set the background behind the board to light blue.", "brief": cur}]
    model = FakeModel(raw_brief(visuals={"background": ["#C0D8FF"]}, changed=["visuals.background"]))
    b = planner.plan("Set the background behind the board to light blue.", client=model, current=cur, history=hist)
    assert b["changed"] == [] and not model.calls and "already applied" in B.control(b, "unchanged")["why"]
    assert planner._repeat_of("Make it harder.", [], cur, [{"n": 2, "prompt": "Make it harder.", "brief": cur}]) is False


def test_a_picture_is_replaced_everywhere_it_appears():
    from cbj.planner import _replace_everywhere
    cur = B.check(raw_brief(assets=[{"file": "play_now_badge_red.png", "role": "sticker", "when": "hook", "where": "beside_hook"},
                                    {"file": "play_now_badge_red.png", "role": "button", "when": "end_card", "where": "end_card"},
                                    {"file": "logo_square.png", "role": "end_art", "when": "end_card", "where": "end_card"}]),
                  {"play_now_badge_red.png": Path("a"), "logo_square.png": Path("b")})
    b = copy.deepcopy(cur); b["changed"] = []
    assert _replace_everywhere(b, "Replace the same red Play Now badge everywhere it appears: in the opening hook and on "
                                  "the final end card.", ["play_now_badge_gold.png"], cur)
    slots = {B.asset_slot(a): a["file"] for a in b["assets"]}
    assert slots == {"hook_icon": "play_now_badge_gold.png", "button": "play_now_badge_gold.png", "end_art": "logo_square.png"}


def test_a_still_frame_is_not_a_border():
    from cbj.planner import _no_border
    cur = _cur()
    b = copy.deepcopy(cur)
    b["assets"] = [{"file": "logo_square.png", "role": "end_art", "when": "end_card", "where": "end_card"}]
    _no_border(b, "Make a 35-second ad: open on a still frame with the headline, then the gameplay. Use the attached "
                  "logo as the picture on the end card.", None, ["logo_square.png"])
    assert b["assets"] and not B.control(b, "assets")["why"]


def test_a_pictures_place_decides_its_slot():
    assert B.asset_slot({"role": "logo", "when": "hook", "where": "beside_hook"}) == "hook_icon"
    assert B.asset_slot({"role": "logo", "when": "whole", "where": "top_right"}) == "logo"
    assert B.asset_slot({"role": "logo", "when": "whole", "where": "auto"}) == "logo"
    assert B.asset_slot({"role": "sticker", "when": "end_card", "where": "end_card"}) == "end_art"
    assert B.asset_slot({"role": "button", "when": "end_card", "where": "end_card"}) == "button"


def test_a_board_background_is_not_also_the_end_cards():
    from cbj.planner import _one_background
    cur = _cur(assets=[{"file": "builtin:hand", "role": "cursor", "when": "whole", "where": "auto"}])
    b = copy.deepcopy(cur)
    b["visuals"]["background_image"] = "winter.png"
    b["assets"] = cur["assets"] + [{"file": "winter.png", "role": "end_background", "when": "whole", "where": "auto"}]
    b["changed"] = ["visuals.background", "assets"]
    _one_background(b, "Replace only the image behind the puzzle board with the supplied pastel winter background.", cur)
    assert b["assets"] == cur["assets"] and b["changed"] == ["visuals.background"]
    b2 = copy.deepcopy(b); b2["assets"].append({"file": "winter.png", "role": "end_background", "when": "end_card", "where": "auto"})
    _one_background(b2, "Use the winter picture behind the board and on the end card too.", cur)
    assert any(a["role"] == "end_background" for a in b2["assets"])


def test_timing_by_numbers_uses_the_real_part_lengths():
    from cbj.planner import _timing_by_numbers
    b = _cur(); b["changed"] = ["sequence.timing", "pacing.length"]; b["sequence"]["hold_s"] = 4.5
    _timing_by_numbers(b, "Extend the final completed-board victory hold by two seconds after the last block exits.",
                       {"intro": 2.8, "result_hold": 0.0, "result": 2.53})
    assert b["sequence"]["hold_s"] == 2.0 and b["changed"] == ["sequence.timing"]
    b2 = _cur(); b2["changed"] = []
    _timing_by_numbers(b2, "Remove one second of static opening hook before the first block movement.", {"intro": 3.0})
    assert b2["sequence"]["intro_s"] == 2.0 and "sequence.timing" in b2["changed"]


def test_copied_part_lengths_are_no_change():
    from cbj.planner import _no_timing_drift
    cur = _cur()
    b = copy.deepcopy(cur); b["sequence"]["intro_s"] = 3.0; b["sequence"]["hold_s"] = 2.6; b["changed"] = ["sequence.timing"]
    _no_timing_drift(b, cur, {"intro": 3.0, "result_hold": 2.57})
    assert b["sequence"]["intro_s"] is None and b["sequence"]["hold_s"] is None and b["changed"] == []
    b2 = copy.deepcopy(cur); b2["sequence"]["hold_s"] = 4.57; b2["changed"] = ["sequence.timing"]
    _no_timing_drift(b2, cur, {"intro": 3.0, "result_hold": 2.57})
    assert b2["sequence"]["hold_s"] == 4.57 and b2["changed"] == ["sequence.timing"]


def test_do_not_undo_is_a_keep():
    from cbj.planner import _undo
    v1 = B.check(raw_brief(audio={"sfx": True, "music": "a.wav"}, concept={"end_title": "Can you solv it?"}),
                 {"a.wav": Path("a.wav"), "b.wav": Path("b.wav")})
    v2 = copy.deepcopy(v1); v2["concept"]["end_title"] = "Try This Puzzle"
    hist = [{"n": 2, "brief": v2, "prompt": "title"}, {"n": 1, "brief": v1, "prompt": "original"}]
    b = copy.deepcopy(v2); b["assets"] = [{"file": "alt.png", "role": "end_art", "when": "end_card", "where": "end_card"}]
    b["changed"] = ["assets"]
    _undo(b, "Replace that new logo with the supplied alternative logo, but do not undo the caption correction or "
             "change the gameplay, music, or ending timing.", v2, hist)
    assert b["concept"]["end_title"] == "Try This Puzzle" and b["changed"] == ["assets"] and b["assets"][0]["file"] == "alt.png"


def test_background_music_is_not_a_background_picture():
    from cbj.planner import _place_unplaced
    cur = B.check(raw_brief(assets=[{"file": "logo_square.png", "role": "end_art", "when": "end_card", "where": "end_card"}]),
                  {"logo_square.png": Path("x")})
    b = copy.deepcopy(cur); b["changed"] = []
    _place_unplaced(b, "Starting from the same approved original, create one variant with the new logo and a separate "
                       "variant with the new background music.", ["logo_new.png"], cur)
    assert b["visuals"]["background_image"] is None
    assert {B.asset_slot(a): a["file"] for a in b["assets"]}.get("end_art") == "logo_new.png"


def test_a_broken_planner_reply_is_asked_again():
    class Flaky(FakeModel):
        def complete(self, system, user, schema):
            self.calls.append((system, user))
            return '{"summary": "cut off' if len(self.calls) == 1 else json.dumps(self.raw)
    model = Flaky(raw_brief())
    b = planner.plan("a clean win", client=model)
    assert len(model.calls) == 2 and b["gameplay"]["ending"]


def test_a_logo_role_beside_the_hook_is_stored_as_a_sticker():
    b = B._complete(raw_brief(assets=[{"file": "badge.png", "role": "logo", "when": "hook", "where": "beside_hook"},
                                      {"file": "brand.png", "role": "logo", "when": "end_card", "where": "end_card"}]))
    assert [a["role"] for a in b["assets"]] == ["sticker", "end_art"]


def test_same_drags_allows_only_a_slightly_different_end(tmp_path):
    from cbj.studio import same_drags
    drag = lambda s: {"block": 0, "cells": [], "result": "exit", "start_frame": s, "exit_frame": s + 30, "end_frame": s + 33}
    for name, frames, win, start in (("a", 350, 274, 31), ("b", 347, 271, 31), ("c", 340, 264, 31), ("d", 350, 274, 40)):
        (tmp_path / name).mkdir()
        (tmp_path / name / "result.json").write_text(json.dumps({"frames": frames, "win_frame": win, "status": "win",
                                                                  "drags": [drag(start)]}))
    assert same_drags(tmp_path / "a", tmp_path / "b")  # the win 3 frames earlier: a shorter exit slide
    assert not same_drags(tmp_path / "a", tmp_path / "c")  # 10 frames: more than an exit slide
    assert not same_drags(tmp_path / "a", tmp_path / "d")  # a drag on another frame


def test_liking_the_creative_being_edited_is_not_a_reference():
    from cbj.reference import is_reference_prompt
    p = "I like this creative. Replace only the image behind the puzzle board with the supplied pastel winter background."
    assert is_reference_prompt(p) and not is_reference_prompt(p, edit=True)
    assert is_reference_prompt("Keep everything, but match the colours of this image.", edit=True)


def test_an_edit_that_describes_another_board_keeps_its_own_colours():
    """TC-14 typed as an edit of a red/green/blue creative: "four blocks in three colours (blue,
    yellow, purple)" is a new board with those colours, not a repaint of the old one (2026-10-14)."""
    from cbj.planner import _recolour_keeps_board
    cur = B.default_brief(); cur["level"]["colours"] = ["Red", "Green", "Blue"]
    b = B.default_brief(); b["level"]["colours"] = ["Blue", "Yellow", "Purple"]; b["level"]["blocks"] = 4
    b["changed"] = ["level.blocks", "level.colours"]
    _recolour_keeps_board(b, "a medium-sized open board with four blocks in three colours (blue, yellow, purple)", cur)
    assert b["level"]["colours"] == ["Blue", "Yellow", "Purple"] and "level.colours" in b["changed"]
    b2 = B.default_brief(); b2["level"]["colours"] = ["Yellow", "Green", "Blue"]; b2["changed"] = ["level.colours"]
    _recolour_keeps_board(b2, "I want the red block to be yellow instead", cur)
    assert b2["level"]["colours"] == ["Red", "Green", "Blue"] and "visuals.colours" in b2["changed"]  # a repaint


def test_a_request_that_names_files_not_attached_is_a_question_not_an_ad():
    """TC-18 with nothing attached: the plan lists what is needed, studio.make refuses until the files
    are attached or the user says to go without them (2026-10-14)."""
    from cbj import studio
    from cbj.planner import _missing_attachment, needs_files
    prompt = ("Use the attached toy pictures as stickers in the two top corners and the attached logo on the end card. "
              "Keep the game's doors as in the real game.")
    assert needs_files(prompt, []) == ["toy pictures", "logo"]
    assert needs_files(prompt, ["toys.png"]) == []
    assert needs_files("Replace the logo with the image I uploaded yesterday.", []) == ["the file the request refers to"]
    assert needs_files("Make the hook say 'Toy box jam!'", []) == []
    b = B.check(B.default_brief()); b["changed"] = ["assets"]
    _missing_attachment(b, prompt, [], None)
    assert b["needs"] == ["toy pictures", "logo"] and B.control(b, "assets")["status"] == "not_supported"
    with pytest.raises(ValueError, match="toy pictures and logo"):
        studio.make(prompt, b)
    b2 = copy.deepcopy(b)
    assert studio.go_without(b2) == ["toy pictures", "logo"]
    assert b2["needs"] == [] and any("made without toy pictures and logo" in n for n in B.control(b2, "assets").get("engine", []))


def test_first_moving_a_piece_aside_is_the_videos_first_drag():
    """"first moving a blocking piece aside, then clearing the blocks": the move aside is the first
    drag, not a move somewhere before the exits (an edit put it at drag 3, two exits in; 2026-10-15)."""
    from cbj.planner import _first_aside
    p = ("Show an experienced player solving the puzzle efficiently without mistakes, first moving a blocking "
         "piece aside, then clearing the available blocks one after another.")
    b = B.check(B.default_brief())
    b["gameplay"]["events"] = [{"block": {"colour": None, "which": "any", "all": False}, "action": "moves", "when": "next"}]
    _first_aside(b, p)
    assert b["gameplay"]["events"][0]["when"] == "first" and "gameplay.events" in b["changed"]
    b2 = B.check(B.default_brief())
    _first_aside(b2, p)  # the model gave no steps: the move aside is added
    assert b2["gameplay"]["events"][0] == {"block": {"colour": None, "which": "any", "all": False}, "action": "moves", "when": "first"}
    b3 = B.check(B.default_brief())
    b3["gameplay"]["events"] = [{"block": {"colour": "Blue", "which": "any", "all": False}, "action": "leaves", "when": "next"}]
    _first_aside(b3, "The blue block leaves, and the player moves the rest aside first.")
    assert b3["gameplay"]["events"][0]["action"] == "leaves"  # a move aside after a named step: left alone
    b4 = B.check(B.default_brief())
    _first_aside(b4, "The blue block exits before the yellow one.")
    assert b4["gameplay"]["events"] == []


def test_two_repositioning_moves_on_a_medium_level_is_said_plainly():
    """"At least two repositioning moves" on a medium level: the row says a medium board has one
    and a hard level gives two or more, instead of a vague promise (2026-10-15)."""
    from cbj.planner import _repositioning_count
    b = B.check(B.default_brief()); b["level"]["difficulty"] = "medium"
    _repositioning_count(b, "a narrow central corridor that requires at least two repositioning moves")
    row = next(r for r in b["controls"] if r["control"] == "level")
    assert "hard band" in (row["why"] or "") and "one" in row["why"] and row["status"] == "adjusted"
    h = B.check(B.default_brief()); h["level"]["difficulty"] = "hard"
    _repositioning_count(h, "requires at least two repositioning moves")
    assert next(r for r in h["controls"] if r["control"] == "level")["status"] == "default"


_WRONG_BLOCK = ('Create a difficult Color Block Jam level with six colored blocks, a narrow central passage and limited space '
                'for repositioning. Show the player first attempting to slide the blue block toward its matching door, but its '
                'movement stops because a red block blocks the route. The player then moves the yellow block aside, clears the '
                'red block and opens a valid path for the blue block. Finish with a quick sequence of successful exits and '
                'approximately three seconds remaining on the timer.')


def test_a_create_a_level_edit_does_not_carry_the_old_level_over():
    """Typed into an open mirrored creative, "Create a difficult level with six colored blocks ..." kept
    the mirror style, the four-colour palette and the piece set, and showed four colours (2026-10-15).
    A request that describes a new level resets what it does not mention; the ad's other parts stay."""
    from cbj.planner import _fresh_level, _coloured_count
    cur = B.check(B.default_brief())
    cur["level"].update(colours=["Red", "Blue", "Green", "Yellow"], style=["symmetric"], pieces="varied", width=6, height=6, blocks=6)
    cur["concept"]["hook"] = "Keep me"
    b = copy.deepcopy(cur)
    b["level"].update(difficulty="hard", shape="narrow_center", style=["symmetric", "packed"])
    b["changed"] = ["level.difficulty", "level.shape", "level.style", "level.blocks"]
    b["gameplay"]["events"] = [{"block": {"colour": "Blue", "which": "any", "all": False}, "action": "stuck", "when": "first", "by": "Red"},
                               {"block": {"colour": "Yellow", "which": "any", "all": False}, "action": "moves", "when": "next"}]
    _fresh_level(b, _WRONG_BLOCK, cur)
    lv = b["level"]
    # "six colored blocks" speaks of colours, so the palette is not reset here; _coloured_count settles it below
    assert lv["style"] == ["packed"] and lv["pieces"] == "mixed" and lv["width"] is None
    assert lv["difficulty"] == "hard" and lv["shape"] == "narrow_center" and lv["blocks"] == 6
    # a kept setting the request asks for stays even when the model did not re-declare it
    b1 = copy.deepcopy(cur); b1["level"].update(shape="narrow_center"); b1["changed"] = ["level.style"]
    _fresh_level(b1, _WRONG_BLOCK, cur)
    assert b1["level"]["shape"] == "narrow_center" and b1["level"]["pieces"] == "mixed" and b1["level"]["style"] == []
    assert b["concept"]["hook"] == "Keep me" and "level.style" in b["changed"] and "level.pieces" in b["changed"]
    _coloured_count(b, _WRONG_BLOCK)  # six coloured blocks: six colours, the named ones first
    assert lv["colours"][:3] == ["Blue", "Yellow", "Red"] and len(lv["colours"]) == 6
    # a plain edit ("make it harder") is not a new level
    b2 = copy.deepcopy(cur); b2["level"]["difficulty"] = "hard"; b2["changed"] = ["level.difficulty"]
    _fresh_level(b2, "Make it harder.", cur)
    assert b2["level"]["style"] == ["symmetric"] and b2["level"]["colours"] == ["Red", "Blue", "Green", "Yellow"]
    # on a mirrored board asked for, six coloured blocks cannot be six colours: said, not forced
    b3 = B.check(B.default_brief()); b3["level"]["style"] = ["symmetric"]
    _coloured_count(b3, "A symmetric board with six colored blocks.")
    assert b3["level"]["colours"] == [] and any("at most" in (r.get("why") or "") for r in b3["controls"])


def test_a_quick_sequence_of_exits_is_a_finish():
    assert B._evidence("gameplay.finish", "Finish with a quick sequence of successful exits.", B.default_brief()) is None
    assert B._evidence("gameplay.finish", "Finish with three seconds left.", B.default_brief()) is not None


def test_a_stuck_step_can_name_the_block_in_the_way():
    """"Blue stops because a red block blocks the route": the stuck step carries the blocker's colour,
    the level's events resolve it to the red blocks, and the board rating wants an attempt a red
    block stops (2026-10-15)."""
    from cbj.events import from_brief
    from cbj.level import load_level
    raw = B.default_brief()
    raw["gameplay"]["events"] = [{"block": {"colour": "Blue", "which": "any", "all": False}, "action": "stuck", "when": "first", "by": "Red"},
                                 {"block": {"colour": "Red", "which": "any", "all": False}, "action": "leaves", "when": "next", "by": None}]
    evs = B.check(raw)["gameplay"]["events"]
    assert evs[0]["by"] == "Red" and "by" not in evs[1]
    level = load_level(Path(__file__).resolve().parents[1] / "data" / "levels" / "gen" / "narrow_center_01.json")
    reds = {i for i, bl in enumerate(level.blocks) if bl.color.name == "RED"}
    blues = {i for i, bl in enumerate(level.blocks) if bl.color.name == "BLUE"}
    if reds and blues:
        resolved, notes = from_brief(level, evs)
        assert resolved[0].by == frozenset(reds) and "stopped by a red block" in resolved[0].text
