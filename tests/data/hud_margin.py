"""Measure where the game's HUD bar ends and where the board's top edge is, on the tool's own recordings
(studio/*/v*/), to derive videoref.SAFE_ZOOM_BY_EXTRA_ROWS (2026-10-17: "zoom in closer" put the HUD on a 4x9 board).

For every version with the HUD shown, no punch-in and a known zoom, it takes the first frame of play (0.5 s into the
play part of ad/ad.mp4), runs audit.hud_measure on it and prints, per board size (columns x rows) and zoom, the HUD's
bottom edge, the board's top edge, the margin between them (negative: the board's top is under the HUD) and whether the
bar covers the board. Run: uv run python tests/data/hud_margin.py [max versions per size and zoom, default 3]
"""
from __future__ import annotations

import json
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from cbj import audit  # noqa: E402


def main(per: int = 3) -> None:
    seen: dict = defaultdict(list)
    for vj in sorted((ROOT / "studio").glob("*/v*/version.json")):
        vdir = vj.parent
        try:
            brief = json.loads((vdir / "brief.json").read_text())
            level = json.loads((vdir / "level.json").read_text())
            manifest = json.loads((vdir / "parts.json").read_text())
        except (OSError, ValueError):
            continue
        vs = brief.get("visuals") or {}
        if not (vs.get("hud_level") and vs.get("hud_timer")) or vs.get("punch_ins"):
            continue
        key = (level["gridWidth"], level["gridHeight"], float(vs.get("camera_zoom") or 1.0))
        if len(seen[key]) >= per:
            continue
        with tempfile.TemporaryDirectory() as tmp:
            # play_frame writes hud_frame.png next to the version; measure a copy so the studio stays untouched
            t = Path(tmp)
            (t / "ad").mkdir()
            (t / "ad" / "ad.mp4").symlink_to(vdir / "ad" / "ad.mp4")
            frame = audit.play_frame(t, manifest)
            if frame is None:
                continue
            m = audit.hud_measure(frame)
        if m["size"] != [1080, 1920] or not m["shown"]:
            continue
        seen[key].append((f"{vdir.parent.name}/{vdir.name}", m))
    print("cols x rows\tzoom\trows-cols\thud_bottom\tboard_top\tmargin\tcovered\tversion")
    for (w, h, z), ms in sorted(seen.items(), key=lambda kv: (kv[0][1] - kv[0][0], kv[0])):
        for name, m in ms:
            print(f"{w}x{h}\t{z:g}\t{h - w}\t{m['hud_bottom']}\t{m['board_top']}\t{m['margin']}\t{m['covered']}\t{name}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 3)
