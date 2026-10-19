"""Core requirements 3 and 4, 2026-10-15: a picture on the board's walls ("use this object instead of the
current obstacle"), measured facts of a reference video, and the obstacle slot in the brief."""
import json
from pathlib import Path

import numpy as np
from PIL import Image

from cbj import brief as B
from cbj.compose import _perspective_coeffs, cell_homography, cell_quads, draw_on_quad, wall_rects

REC = Path(__file__).resolve().parents[1] / "studio" / "recordings" / "8e9b30915d138d9f"


def test_wall_rects_merge_rectangles_and_keep_odd_groups_per_cell():
    assert wall_rects({(2, 2), (2, 3), (3, 2), (3, 3)}) == [(2, 2, 3, 3)]
    assert wall_rects({(0, 0), (0, 1), (1, 1)}) == [(0, 0, 0, 0), (0, 1, 0, 1), (1, 1, 1, 1)]  # an L is not a box
    assert wall_rects(set()) == []


def test_perspective_coeffs_map_the_corners_exactly():
    dst = [(10, 10), (110, 12), (112, 100), (8, 98)]
    c = _perspective_coeffs(dst, [(0, 0), (50, 0), (50, 50), (0, 50)])
    for (X, Y), (x, y) in zip(dst, [(0, 0), (50, 0), (50, 50), (0, 50)]):
        d = c[6] * X + c[7] * Y + 1
        assert abs((c[0] * X + c[1] * Y + c[2]) / d - x) < 1e-6 and abs((c[3] * X + c[4] * Y + c[5]) / d - y) < 1e-6


def test_draw_on_quad_changes_only_the_quad_box():
    frame = np.zeros((200, 200, 3), dtype=np.uint8)
    img = Image.new("RGBA", (20, 20), (255, 0, 0, 255))
    box = draw_on_quad(frame, img, [(50, 50), (90, 52), (92, 90), (48, 88)])
    assert box and box[0] >= 47 and box[1] >= 49 and box[2] <= 94 and box[3] <= 92
    assert frame[70, 70].tolist() == [255, 0, 0] and frame[10, 10].tolist() == [0, 0, 0]


def test_cell_homography_fits_the_recorded_board_exactly():
    if not (REC / "frames.json").is_file():
        import pytest
        pytest.skip("the sample recording is not in this studio")
    from cbj.ad import Recording
    rec = Recording.load(REC)
    H = cell_homography(rec)
    assert H is not None
    pts = rec.frames[0]["blocks"]
    for i, b in enumerate(rec.level.blocks):
        v = H @ np.array([b.pivot[0], b.pivot[1], 1.0])
        assert abs(v[0] / v[2] - pts[2 * i]) < 0.5 and abs(v[1] / v[2] - pts[2 * i + 1]) < 0.5
    quads = cell_quads(rec)
    assert len(quads) == len(wall_rects(set(rec.level.inactive)))
    assert all(len(q) == 4 for q in quads)


def test_obstacle_is_its_own_picture_slot():
    assert B.asset_slot({"file": "boulder.png", "role": "obstacle", "when": "whole", "where": "auto"}) == "obstacle"
    assert "obstacle" in B.ASSET_ROLES
    from cbj.edits import PICTURES, REMOVABLE
    assert "obstacle" in PICTURES and "obstacle" in REMOVABLE


def test_video_facts_measure_cuts_and_motion(tmp_path):
    import shutil, subprocess
    from cbj.reference import video_facts
    if not shutil.which("ffmpeg"):
        import pytest
        pytest.skip("ffmpeg")
    clip = tmp_path / "clip.mp4"
    # 2 s of a still colour then 2 s of another: one cut, little motion
    subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=160x90:d=2",
                    "-f", "lavfi", "-i", "color=c=blue:s=160x90:d=2", "-filter_complex", "[0][1]concat=n=2:v=1:a=0",
                    "-r", "8", "-pix_fmt", "yuv420p", str(clip)], check=True)
    f = video_facts(clip)
    assert f["pacing"] == "calm" and len(f["motion_per_s"]) >= 3
    assert any(1.5 <= c <= 2.5 for c in f["cuts_s"])


def test_a_caption_edit_patches_the_approved_video_and_decodes_identically(tmp_path):
    """Core requirement 5: a layer-only edit copies the untouched GOPs of the approved MP4 byte for
    byte and renders only the changed ones; the result decodes frame for frame like a full render."""
    import json, shutil, subprocess
    from cbj import compose
    from cbj.ad import Recording, build_ad
    from test_ad import make_recording
    if not shutil.which("ffmpeg"):
        import pytest
        pytest.skip("ffmpeg")
    rec = Recording.load(make_recording(tmp_path / "rec"))
    ad = build_ad(rec, length_s=30)
    r1 = compose.render(json.loads(json.dumps(ad)), tmp_path / "v1")
    assert r1["rendered"] and "patched" not in r1
    ad["layers"]["hook"]["text"] = "Can you beat it?"
    r2 = compose.render(json.loads(json.dumps(ad)), tmp_path / "v2", patch_from=tmp_path / "v1")
    assert r2["rendered"] and r2["patched"]["changed_layers"] == ["hook"]
    assert 0 < r2["patched"]["gops_rendered"] < r2["patched"]["gops"]
    assert r2["patched"]["frames_copied"] + r2["patched"]["frames_rendered"] == r2["frames"]
    r3 = compose.render(json.loads(json.dumps(ad)), tmp_path / "v2full")
    assert r2["frame_sha256"] == r3["frame_sha256"] and r2["wav_sha256"] == r3["wav_sha256"]

    def md5s(p):
        out = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-an", "-f", "framemd5", "-"],
                             capture_output=True, text=True).stdout
        return [l.split(",")[-1].strip() for l in out.splitlines() if l and not l.startswith("#")]
    assert md5s(tmp_path / "v2" / "ad.mp4") == md5s(tmp_path / "v2full" / "ad.mp4")
    # the mix is identical, so the approved video's audio stream is copied byte for byte (2026-10-15)
    assert r2["patched"]["audio_copied"] is True

    def audio_md5(p):
        return subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-vn", "-c:a", "copy", "-f", "md5", "-"],
                              capture_output=True, text=True).stdout.strip()
    assert audio_md5(tmp_path / "v2" / "ad.mp4") == audio_md5(tmp_path / "v1" / "ad.mp4")
    # a timing edit (a part's length changed) is not patched: rendered in full
    ad["segments"]["end"]["frames"] += 30
    ad["length_s"] += 1
    r4 = compose.render(json.loads(json.dumps(ad)), tmp_path / "v3", patch_from=tmp_path / "v1")
    assert "patched" not in r4  # (the locked segment also fails QA, as it should)


def test_cutout_makes_a_plain_background_transparent_and_keeps_real_alpha():
    from cbj.draw import cutout
    im = Image.new("RGB", (100, 100), (255, 255, 255))
    d = __import__("PIL.ImageDraw", fromlist=["Draw"]).Draw(im)
    d.ellipse((20, 20, 80, 80), fill=(200, 30, 30))
    c = cutout(im)
    assert c.mode == "RGBA" and c.size == (61, 61)  # trimmed to the sticker
    assert c.getpixel((30, 30))[3] == 255 and c.getpixel((0, 0))[3] == 0
    already = Image.new("RGBA", (50, 50), (0, 0, 0, 0))
    assert cutout(already) is already or cutout(already).getpixel((0, 0))[3] == 0
    tile = Image.new("RGB", (40, 40), (120, 80, 30))  # a full tile: nothing to cut
    assert cutout(tile).getchannel("A").getextrema() == (255, 255)


# ---------- a texture on one block (the skin layer, 2026-10-15) ----------

def test_block_quads_follow_the_recorded_block_and_vanish_at_its_exit():
    """The quads of a block's cells come from its logged position on each frame through the inverse
    cell homography: as many quads as cells, moving with the block, none once it has left."""
    from cbj.ad import Recording
    from cbj.compose import block_quads
    rec = Recording.load(REC)
    bid = next(i for i, b in enumerate(rec.level.blocks) if len(b.offsets) > 1)
    q0 = block_quads(rec, bid, 0)
    assert len(q0) == len(rec.level.blocks[bid].offsets)
    gone = next(t for t in range(len(rec.frames)) if rec.frames[t]["blocks"][2 * bid] < 0)
    assert block_quads(rec, bid, gone) == []
    moved = next(t for t in range(gone) if abs(rec.frames[t]["blocks"][2 * bid] - rec.frames[0]["blocks"][2 * bid])
                 + abs(rec.frames[t]["blocks"][2 * bid + 1] - rec.frames[0]["blocks"][2 * bid + 1]) > 40)
    qm = block_quads(rec, bid, moved)
    assert len(qm) == len(q0) and qm[0][0] != q0[0][0]
    # the quad sits on the block: its centre is within a cell of the logged position
    cx = sum(p[0] for p in q0[0]) / 4
    cy = sum(p[1] for p in q0[0]) / 4
    sx, sy = rec.frames[0]["blocks"][2 * bid], rec.frames[0]["blocks"][2 * bid + 1]
    assert abs(cx - sx) < 120 and abs(cy - sy) < 120


def test_draw_on_quad_multiply_darkens_only_inside_and_a_dark_texture_is_lightened():
    import numpy as np
    from cbj.compose import draw_on_quad, texture_for_multiply
    frame = np.full((200, 200, 3), 200, np.uint8)
    tex = Image.new("RGBA", (16, 16), (128, 128, 128, 255))
    box = draw_on_quad(frame, tex, [(50, 50), (150, 50), (150, 150), (50, 150)], mode="multiply")
    assert box == (50, 50, 151, 151)
    assert frame[100, 100, 0] == 100 and frame[10, 10, 0] == 200  # 200 * 128/255, outside untouched
    light = texture_for_multiply(Image.new("RGBA", (8, 8), (40, 40, 40, 255)))
    assert light.getpixel((0, 0))[0] >= 200
    lines = texture_for_multiply(Image.new("RGBA", (8, 8), (0, 0, 0, 255)))  # black lines become mid-grey
    assert 100 <= lines.getpixel((0, 0))[0] <= 160
    already = texture_for_multiply(Image.new("RGBA", (8, 8), (230, 230, 230, 255)))
    assert already.getpixel((0, 0))[0] >= 230


def test_a_texture_on_a_block_is_the_skin_slot_and_builds_a_skin_layer(tmp_path):
    from cbj.ad import Recording, build_ad
    from cbj.edits import PICTURES, REMOVABLE
    from cbj.planner import _block_art
    assert B.asset_slot({"file": "t.png", "role": "skin", "when": "whole", "where": "auto", "block": "Blue"}) == "skin"
    assert "skin" in B.ASSET_ROLES and "skin" in PICTURES and "skin" in REMOVABLE
    b = B.check(B.default_brief())
    b["assets"] = [{"file": "ice.png", "role": "sticker", "when": "hook", "where": "beside_hook"}]
    b["changed"] = ["assets"]
    _block_art(b, "Keep everything the same, but apply this ice texture to the blue block.", None, ["ice.png"])
    assert b["assets"] == [{"file": "ice.png", "role": "skin", "when": "whole", "where": "auto", "block": "Blue"}]
    assert next(r for r in b["controls"] if r["control"] == "assets")["status"] == "applied"
    d = B.check(B.default_brief()); d["assets"] = [{"file": "ice.png", "role": "sticker", "when": "hook", "where": "beside_hook"}]; d["changed"] = ["assets"]
    _block_art(d, "Put this ice texture on the blue door.", None, ["ice.png"])
    assert d["assets"] == [] and next(r for r in d["controls"] if r["control"] == "visuals")["status"] == "not_supported"
    rec = Recording.load(REC)
    tex = tmp_path / "ice.png"
    Image.new("RGBA", (32, 32), (180, 220, 255, 255)).save(tex)
    ad = build_ad(rec, length_s=45, options={"skin": {"file": str(tex), "colour": "Blue", "which": "any"}})
    lay = ad["layers"]["skin"]
    assert lay["type"] == "skin" and lay["blend"] == "multiply" and rec.level.blocks[lay["block"]].color.name == "BLUE"
    assert "play" in lay["segments"]
    none = build_ad(rec, length_s=45, options={"skin": {"file": str(tex), "colour": "Purple", "which": "any"}})
    assert "skin" not in none["layers"]


def test_an_exact_texture_edit_needs_and_keeps_the_block_colour():
    from cbj.edits import direct_edit, replace_picture
    b = B.check(B.default_brief())
    b2, words = replace_picture(b, "skin", "ice.png", "Blue")
    a = next(x for x in b2["assets"] if x["role"] == "skin")
    assert a["block"] == "Blue" and "blue block" in words and b2["changed"] == ["assets"]
    b3, _ = replace_picture(b2, "skin", "snow.png")  # a replacement keeps the block
    assert next(x for x in b3["assets"] if x["role"] == "skin")["block"] == "Blue"
    import pytest
    with pytest.raises(ValueError, match="colour"):
        replace_picture(b, "skin", "ice.png")
    b4, _ = replace_picture(b2, "skin", None)  # removed
    assert not any(x.get("role") == "skin" and x["file"] != "builtin:none" for x in b4["assets"])
    b5, _ = direct_edit(b, {"picture": "skin", "file": "ice.png", "block": "Red"}, {"ice.png": Path("ice.png")}, set())
    assert next(x for x in b5["assets"] if x.get("role") == "skin")["block"] == "Red"


def _cyan_green_brief():
    """A trailer-3 copy's look: the game's green slot painted cyan, orange painted amber (2026-10-19)."""
    b = B.check(B.default_brief())
    b["visuals"]["blocks"] = [{"slot": "Green", "hex": "#029EE9", "name": "cyan"}, {"slot": "Orange", "hex": "#FBB230", "name": "orange"},
                              {"slot": "Blue", "hex": "#1438F8", "name": "blue"}]
    return b


def test_a_colour_word_names_the_slot_as_this_creative_shows_it():
    b = _cyan_green_brief()
    used = {"Green", "Orange", "Blue", "Red", "Purple", "DarkGreen"}
    assert B.slot_of_colour_word("cyan", b, used) == "Green"          # the shown name
    assert B.slot_of_colour_word("light blue", b, used) == "Green"    # the nearest shown shade
    assert B.slot_of_colour_word("teal", b, used) == "Green"
    assert B.slot_of_colour_word("blue", b, used) == "Blue"           # the game's name, shown as itself
    assert B.slot_of_colour_word("red", b, used) == "Red"
    assert B.slot_of_colour_word("dark green", b, used) == "DarkGreen"
    assert B.slot_of_colour_word("yellow", b, used) == "Orange"       # no yellow on the board: the amber one is nearest
    assert B.slot_of_colour_word("yellow", b, {"Green", "Blue"}) is None
    assert B.slot_of_colour_word("ice", b, used) is None and B.slot_of_colour_word("", b) is None
    assert B.slot_of_colour_word("Green", None) == "Green"            # no brief: the game's own names


def test_a_texture_on_the_cyan_block_goes_on_the_slot_shown_cyan():
    """E4 (2026-10-19): "apply the attached ice texture to the cyan block" on a footage-coloured copy was refused as a
    picture on a block; the colour word resolves on the creative's own shown colours now."""
    from cbj.planner import _block_art
    cur = _cyan_green_brief()
    b = json.loads(json.dumps(cur))
    b["assets"] = [{"file": "ice.png", "role": "sticker", "when": "hook", "where": "beside_hook"}]
    b["changed"] = ["assets"]
    _block_art(b, "Apply the attached ice texture to the cyan block. Everything else stays as it is.", cur, ["ice.png"])
    skin = next((a for a in b["assets"] if a.get("role") == "skin"), None)
    assert skin is not None and skin["block"] == "Green" and skin["file"] == "ice.png"
    assert b["visuals"]["blocks"] == cur["visuals"]["blocks"]  # the colours stay
    assert next(r for r in b["controls"] if r["control"] == "assets")["status"] == "applied"
    assert next(r for r in b["controls"] if r["control"] == "visuals")["status"] != "not_supported"


def test_a_texture_and_a_wall_picture_cover_every_part_that_shows_the_board(tmp_path):
    """E2 (2026-10-19): the obstacle picture was on the play only; on the frozen question and the end card's board
    picture the wall turned back into the plain pillar ("feels like a glitch", the viewer). Now every board part."""
    from cbj.ad import BOARD_PARTS, Recording, build_ad
    rec = Recording.load(REC)
    tex = tmp_path / "ice.png"
    Image.new("RGBA", (32, 32), (180, 220, 255, 255)).save(tex)
    ad = build_ad(rec, length_s=45, options={"skin": {"file": str(tex), "colour": "Blue", "which": "any"}})
    lay = ad["layers"]["skin"]
    want = [sid for sid in ad["order"] if sid in BOARD_PARTS]
    assert lay["segments"] == want and lay["end"]["seg"] == want[-1]
    assert "question" in BOARD_PARTS and "result_hold" in BOARD_PARTS and "end" not in BOARD_PARTS


def test_a_wall_picture_edit_marks_the_end_card_with_the_board_picture_dirty():
    """E2 (2026-10-19): the patched render copied the end card's GOP, so its board picture kept the plain wall."""
    from cbj.compose import patch_plan

    class _Prep:
        total = 300
        tl = {"play": (0, 200), "end": (200, 300)}
        layers = {"obstacle": {"f0": 0, "f1": 200}}

        def keyframes(self):
            return [0, 200]
    prev_ad = {"order": ["play", "end"], "segments": {"play": {}, "end": {"thumb": {"src": "main", "frame": 1}}}, "layers": {}}
    ad = json.loads(json.dumps(prev_ad))
    ad["layers"]["obstacle"] = {"type": "object", "image": "x.png"}
    prev = {"rendered": True, "draft": False, "frames": 300, "keyframes": [0, 200], "layers": {}}
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "compose.json").write_text(json.dumps(prev))
        (d / "ad.json").write_text(json.dumps(prev_ad))
        (d / "ad.mp4").write_bytes(b"x")
        plan = patch_plan(ad, _Prep(), d)
    assert plan is not None and plan["dirty"] == [(0, 200), (200, 300)]
    prev_ad["segments"]["end"].pop("thumb"); ad["segments"]["end"].pop("thumb")
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "compose.json").write_text(json.dumps(prev))
        (d / "ad.json").write_text(json.dumps(prev_ad))
        (d / "ad.mp4").write_bytes(b"x")
        plan = patch_plan(ad, _Prep(), d)
    assert plan["dirty"] == [(0, 200)]  # no board picture on the card: its GOP is copied
