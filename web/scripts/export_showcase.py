"""Export a curated set of finished creatives from studio/ into web/public/showcase/ so the
deployed site can show real results (video, brief, checks, viewer review, edit proof) when the
engine on the Mac is offline.

Run from the repo root:  uv run python web/scripts/export_showcase.py

Paths inside public/showcase/ keep the studio-relative layout (<id>/v<n>/ad/ad.mp4, <id>/v<n>/board.png,
recordings/<hash>/play.json, uploads/<file>, sprites/<file>) so the web app resolves one path either as
<engine>/studio/<path> (online) or /showcase/<path> (offline). Videos are re-encoded to 720x1280 for the web;
the originals stay in studio/.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parents[2]
STUDIO = REPO / "studio"
OUT = REPO / "web" / "public" / "showcase"
sys.path.insert(0, str(REPO / "src"))
from cbj import studio  # noqa: E402
from cbj.draw import PROJECT, SPRITES  # noqa: E402

# (creative id, versions, title, kind, tagline)
SHOWCASE = [
    # text-driven
    ("1012-235537-create-a-difficult-color-block", [1], "The case's own prompt", "create",
     "The example prompt from the case brief: a difficult narrow-centre level where the player almost fails before solving it."),
    ("1017-231258-an-hourglass-board-7x9-10", [3, 4, 5], "Hourglass board with caption edits", "create",
     "A hard hourglass board that ends on a question, then two compose-tier edits: a new caption at the cut, and lime-green captions."),
    # image-driven
    ("1019-085427-create-a-similar-game-concept", [1], "Inspired by this image", "image_guided",
     "A picture read for its concept, colours and composition; a new solvable level is generated and played to a near-fail."),
    ("1019-101154-the-same-two-room-board", [1, 2], "The picture's board, copied cell by cell", "image_guided",
     "The board in the picture is read cell by cell, verified against the pixels, solved and drawn by the game itself; a cliffhanger ending."),
    ("1017-195834-create-a-color-block-jam", [1], "Dark neon look from an image", "image_guided",
     "An image reference gives the look only: dark neon background and captions, no level badge or timer, on a generated level."),
    # video-reference-driven
    ("1019-113515-use-same-game-design-same", [1, 4], "Same design as this video, fewer blocks", "guided",
     "The trailer's own board is copied from its first frame of play with two blocks fewer; then one edit puts a picture on the wall cells and proves nothing else changed."),
    ("1019-141354-take-the-board-from-this", [1, 2], "A Turkish request on a video: mirrored, harder, time-out", "guided",
     "The request is translated once; the video's board is copied, mirrored left to right, one block added in the way, and played to a time-out in the game's own look."),
    # controlled modification
    ("1019-125939-the-board-exactly-as-shown", [1, 3], "Keep everything, replace this object with the attached asset", "edit",
     "The case's own editing sentence: the end card's picture replaced from an attached file; 1,336 of 1,440 frames reused byte for byte, the changed pixels inside the end card's box."),
    ("1019-130745-same-board-as-this-ad", [1, 4], "A picture behind the board: re-filmed, game state identical", "edit",
     "A background change re-films the same level and the same drags in the game; the report shows the game state equal on every frame and the timing pinned."),
    ("1015-074810-create-a-hard-color-block", [1, 12, 13, 14, 15, 16, 17], "The editing ladder", "edit-ladder",
     "One hard level, five controlled edits in a row: a picture swap, pastel blocks, a second mistake, blue to red, "
     "a harder board. Each edit re-runs only the tier it needs and proves what it kept."),
]

FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"


def encode_video(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
        return
    cmd = [FFMPEG, "-y", "-loglevel", "error", "-i", str(src), "-vf", "scale=720:-2", "-c:v", "libx264",
           "-preset", "veryfast", "-crf", "26", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k",
           "-movflags", "+faststart", str(dst)]
    subprocess.run(cmd, check=True)


def copy_image(src: Path, dst: Path, max_w: int) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
        return
    im = Image.open(src)
    if im.width > max_w:
        im = im.resize((max_w, round(im.height * max_w / im.width)), Image.LANCZOS)
    if dst.suffix.lower() in (".jpg", ".jpeg"):
        im.convert("RGB").save(dst, quality=82, optimize=True)
    else:
        im.save(dst, optimize=True)


def copy_file(rel: str, max_w: int | None = None) -> bool:
    src = STUDIO / rel
    if not src.is_file():
        return False
    dst = OUT / rel
    if max_w and src.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
        copy_image(src, dst, max_w)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime:
            shutil.copy2(src, dst)
    return True


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    index = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S"), "creatives": []}
    sprites_used: set[str] = set()
    t0 = time.time()
    for cid, ns, title, kind, tagline in SHOWCASE:
        versions = {v["n"]: v for v in studio.versions(cid)}
        full, light = [], []
        for n in ns:
            v = versions.get(n)
            if v is None:
                print(f"!! {cid} v{n}: no such version", file=sys.stderr)
                continue
            v = json.loads(json.dumps(v))  # a copy
            # media
            encode_video(STUDIO / v["video"], OUT / v["video"])
            copy_file(v["poster"], max_w=540)
            if v.get("board"):
                copy_file(v["board"], max_w=600)
            vdir = f"{cid}/v{n}"
            copy_file(f"{vdir}/review.json")
            copy_file(f"{vdir}/brief.json")
            copy_file(v["level"]["file"])
            rec = v["recording"]["dir"]
            copy_file(f"{rec}/play.json")
            # the viewer's review and its contact sheet
            rj = STUDIO / vdir / "review.json"
            review = None
            if rj.is_file():
                review = json.loads(rj.read_text())
                if review.get("sheet"):
                    copy_file(review["sheet"], max_w=1200)
            v["review"] = review
            # references (images are copied; videos are named only)
            refs = (v["brief"].get("planner") or {}).get("references") or []
            for r in refs:
                if r.get("kind") == "image" and r.get("file"):
                    r["copied"] = copy_file(f"uploads/{r['file']}", max_w=768)
            # the inventory ("things in this ad") for the Edit workspace in offline mode
            try:
                inv = studio.inventory(cid, n)
            except Exception as e:  # noqa: BLE001
                inv = []
                print(f"   {cid} v{n}: inventory failed: {e}", file=sys.stderr)
            for t in inv:
                f = t.get("file") or ""
                name = f.split("/")[-1]
                if "/uploads/" in f:
                    copy_file(f"uploads/{name}", max_w=512)
                elif name and name in studio.sprite_names():
                    sprites_used.add(name)
            (OUT / vdir / "inventory.json").write_text(json.dumps(inv, indent=1))
            size_mb = round((OUT / v["video"]).stat().st_size / 1e6, 2)
            full.append(v)
            light.append({"n": n, "from": v.get("from"), "edit": bool(v.get("edit")), "prompt": v["prompt"],
                          "length_s": v["length_s"], "workflow": v.get("workflow") or (v["brief"].get("planner") or {}).get("workflow") or "create",
                          "video": v["video"], "poster": v["poster"], "summary": v["brief"].get("summary"),
                          "review_overall": (review or {}).get("overall"), "would_download": (review or {}).get("would_download"),
                          "video_mb": size_mb})
            print(f"   {cid} v{n}: {size_mb} MB")
        (OUT / cid / "showcase.json").write_text(json.dumps({"id": cid, "title": title, "kind": kind, "tagline": tagline,
                                                               "versions": full}, indent=1))
        index["creatives"].append({"id": cid, "title": title, "kind": kind, "tagline": tagline, "prompt": full[0]["prompt"] if full else "",
                                   "versions": light})
    for name in sorted(sprites_used):
        src = PROJECT / SPRITES / name
        if src.is_file():
            copy_image(src, OUT / "sprites" / name, 256)
    (OUT / "index.json").write_text(json.dumps(index, indent=1))
    total = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file()) / 1e6
    print(f"showcase: {len(index['creatives'])} creatives, {sum(len(c['versions']) for c in index['creatives'])} versions, "
          f"{total:.1f} MB in {OUT} ({time.time() - t0:.0f} s)")


if __name__ == "__main__":
    main()
