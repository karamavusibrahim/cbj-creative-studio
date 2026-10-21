"""The image evaluation (core requirement 3, rule I13; 2026-10-17): the rows the image-guided workflow adds to the
text-to-creative profile, measured on what was made, never on the plan's words alone:

- the role and what was taken / not taken (info);
- the board, when the picture's board was taken: the shape class, the size within one cell, the blocks within two, each
  read colour present by slot, mirror-symmetric when the picture is, packed when the picture's fill is 60 % or more, the
  pieces' size class; measured on the made level.json against what the tool built from the reading (the clamps
  included). A part the request named is judged; a part filled from the picture (the request left it open) is info;
  a part the reading does not get reliably (READING-ACCURACY.md, rule I14) is info, "read approximately";
- the look, when taken: the made background on the poster's margins (audit.poster_background) against the kit, the kit
  against the picture's measured margins, the caption fill and outline on the hook's frame inside its box, and the
  caption's contrast; when the look (or a part of it) is not taken, the game's own (the poster's margins against the
  game's own background as rendered, the captions and blocks unchanged);
- the screen: the HUD shown or hidden as asked, read from the recording's job (its hidden HUD parts);
- nothing copied: no layer of the ad uses the picture outside an asset or modify slot, no planned caption is the
  picture's own words unless the request quotes them;
- counted on the board: the block count came from the board, not from a number a caption claims.
Rows use audit.py's format ({check, status, detail, from, where}); from "reference", so their misses feed the loop
(audit.misses). `where` is "plan" when the brief did not carry the value, "level" when the generator built another
board (a new take fixes it), "ad" or "play" when the made frames do not show it.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import brief as B

# The parts of the board read reliably on the four test pictures by the workflow's reader, Opus prompt-driven
# (READING-ACCURACY.md, 2026-10-17: 3 or 4 of 4 each); the pieces' class read 0 of 2 (pic_x's small and pic_z's big pieces
# both read "varied"), so the pieces row is info, "read approximately".
RELIABLE = frozenset({"shape", "size", "blocks", "colours", "symmetric", "packed"})
SIZE_CELLS, BLOCKS_WITHIN = 1, 2
SIZE_SPREAD_MAX = 2  # imageplan.SIZE_SPREAD_MAX
SYMMETRIC_SHARE = 0.9  # the made board's occupancy equals its mirror's in this share of cells: mirror-symmetric
FILL_NEAR = 0.1  # "as crowded as the picture": the made fill at least this close under the picture's
FILL_SLACK = 0.05  # a clamped board's made fill may fall this far under the fill measured on its pre-take build
PACKED_MADE = 0.58  # generate.PACKED_FILL[0]: a made board this full (block cells over playable cells) is packed
SMALL_MEAN, BIG_MEAN = 2.0, 3.8  # the made pieces' mean cells: small at most, big at least
CAPTION_SHARE = 0.02  # this share of the caption box's pixels near a colour: the colour is on screen
LOOK_RGB = 48.0  # audit.LOOK_RGB


def _row(check: str, ok: bool | None, detail: str, where: str | None = None) -> dict:
    return {"check": f"Image: {check}", "status": "pass" if ok else "info" if ok is None else "failed",
            "detail": detail, "from": "reference", "where": None if ok or ok is None else where}


def _filled(row: dict, why: str) -> dict:
    was = {"pass": "it matches", "failed": "it differs", "info": None}[row["status"]]
    row.update(status="info", where=None, detail=f"{why}; not judged" + (f" ({was})" if was else "") + f": {row['detail']}")
    return row


def made_level(level_path: Path) -> dict | None:
    """The made board: {columns, rows, blocks, colours (slots), shape, walls, fill, mean_cells, bars, symmetric, mirror}."""
    from . import audit
    from .level import load_level
    if not Path(level_path).is_file():
        return None
    made = audit.made_board(Path(level_path), {})
    lv = load_level(level_path)
    cells = set()
    for b in lv.blocks:
        cells |= set(b.cells_at(b.pivot))
    free = lv.width * lv.height - len(lv.inactive)
    sizes = [b.size for b in lv.blocks]

    def bar(b):
        xs, ys = {o[0] for o in b.offsets}, {o[1] for o in b.offsets}
        return b.size >= 3 and (len(xs) == 1 or len(ys) == 1)
    lr = sum((x, y) in cells and (lv.width - 1 - x, y) in cells or (x, y) not in cells and (lv.width - 1 - x, y) not in cells
             for x in range(lv.width) for y in range(lv.height)) / (lv.width * lv.height)
    tb = sum((x, y) in cells and (x, lv.height - 1 - y) in cells or (x, y) not in cells and (x, lv.height - 1 - y) not in cells
             for x in range(lv.width) for y in range(lv.height)) / (lv.width * lv.height)
    made.update(fill=round(len(cells) / free, 2) if free else 0.0, mean_cells=round(sum(sizes) / len(sizes), 2) if sizes else 0.0,
                bars=all(bar(b) for b in lv.blocks) if lv.blocks else False, mirror=[round(lr, 2), round(tb, 2)],
                symmetric=max(lr, tb) >= SYMMETRIC_SHARE)
    return made


def board_rows(prov: dict, made: dict | None) -> list[dict]:
    """One row per board part taken or filled, measured on the made level against what the tool built."""
    bd = prov.get("board") or {}
    if not bd:
        return []
    if made is None:
        return [_row("the board", None, "the made level could not be read")]
    built, seen = bd.get("built") or {}, bd.get("seen") or {}
    named, filled = set(bd.get("named") or []), set(bd.get("filled") or [])
    out = []
    word = lambda s: str(s or "any").replace("_", " ")  # noqa: E731
    for part in ("shape", "size", "blocks", "colours", "symmetric", "packed", "pieces"):
        if part not in named | filled:
            continue
        if part == "shape":
            r = _row("the board's shape", made["shape"] == built.get("shape"),
                     f"the picture shows {seen.get('shape') or '?'}; the tool builds {word(built.get('shape'))}; the made level is "
                     f"{word(made['shape'])}", "level")
        elif part == "size":
            w, h = (built.get("size") or [None, None])[:2]
            ok = bool(w and h) and abs(made["columns"] - w) <= SIZE_CELLS and abs(made["rows"] - h) <= SIZE_CELLS
            sz = seen.get("size") or ["?", "?"]
            r = _row("the board's size", ok, f"{sz[0]}x{sz[1]} read" + (f", {w}x{h} built" if [w, h] != sz else "") +
                     (f" ({seen['size_decided_by']})" if seen.get("size_decided_by") else "") +
                     f", {made['columns']}x{made['rows']} made (within {SIZE_CELLS} cell a side)", "level")
            if (seen.get("size_spread") or 0) > SIZE_SPREAD_MAX:
                _filled(r, f"read approximately: the size reads spread over {seen['size_spread']} cells")
                out.append(r)
                continue
        elif part == "blocks":
            # against the count the brief can take (the seen count, at most its limit), not against what was built: a
            # build cut short is a miss unless the plan says why (F4, F8, 2026-10-17: 14 seen, 8 built, the row passed)
            target = built.get("blocks_target", built.get("blocks"))
            cut = built.get("blocks_cut")
            want = built.get("blocks") if cut else target
            ok = want is not None and abs(made["blocks"] - want) <= BLOCKS_WITHIN
            r = _row("the board's blocks", ok, f"{seen.get('blocks')} counted on the board" +
                     (f", {target} the most one level takes" if target != seen.get("blocks") else "") +
                     (f", {built.get('blocks')} built ({cut})" if cut else "") +
                     f", {made['blocks']} made (within {BLOCKS_WITHIN} of {want})", "level")
        elif part == "colours":
            want = built.get("colours") or []
            have = [c for c in want if c in made["colours"]]
            if built.get("colours_by") == "request" or not want:
                # the request names the colours itself (H6, 2026-10-18: S4's "only blue and orange" was judged against an empty
                # map, "0 of 0", and a revision ran): its own list, or info when it gave none the row can read
                if want:
                    r = _row("the board's colours", len(have) == len(want),
                             f"the request names {', '.join(B.COLOUR_WORDS[c] for c in want)}; the made board has "
                             f"{', '.join(B.COLOUR_WORDS.get(c, c) for c in made['colours'])}", "level")
                else:
                    r = _row("the board's colours", None, f"the request sets the colours itself; the made board has "
                                                          f"{', '.join(B.COLOUR_WORDS.get(c, c) for c in made['colours'])}")
                out.append(r)
                continue
            r = _row("the board's colours", bool(want) and len(have) == len(want),
                     f"read {', '.join(seen.get('colours') or [])} -> {', '.join(B.COLOUR_WORDS[c] for c in want)}; "
                     f"{len(have)} of {len(want)} on the made board ({', '.join(B.COLOUR_WORDS.get(c, c) for c in made['colours'])})"
                     + (f"; {len(want)} colours allowed from the picture, the level uses {len(have)} of them ({made['blocks']} "
                        f"blocks on {made['columns']}x{made['rows']})" if len(have) < len(want) else ""), "level")
        elif part == "symmetric":
            if not built.get("symmetric"):
                continue
            r = _row("mirror-symmetric", made["symmetric"], f"the picture's board is mirror-symmetric (measured); the made board "
                                                            f"equals its mirror in {max(made['mirror']):.0%} of its cells (at "
                                                            f"least {SYMMETRIC_SHARE:.0%})", "level")
        elif part == "packed":
            if built.get("fill_target") is not None:
                # "as crowded as this picture" (H10): the picture's fill is the target, within FILL_NEAR; at the block limit
                # a board that cannot reach it is info, said
                tgt = built["fill_target"]
                ok = made["fill"] >= tgt - FILL_NEAR
                r = _row("as crowded as the picture", ok, f"the picture's board is about {tgt:.0%} full (measured); the made board "
                                                          f"{made['fill']:.0%} (at least {tgt - FILL_NEAR:.0%})", "level")
                if not ok and (built.get("blocks") or 0) >= 10:
                    r.update(status="info", where=None, detail=r["detail"] + "; 10 blocks is the most one level takes")
                if part in filled and part not in named:
                    _filled(r, "filled from the image (the request left it open)")
                out.append(r)
                continue
            if not built.get("packed"):
                continue
            fill = seen.get("fill")
            gen = built.get("fill_generated")
            clamped = (seen.get("blocks") or 0) > (built.get("blocks") or 0)
            if clamped and isinstance(gen, (int, float)) and gen < PACKED_MADE:
                # the count was cut below the picture's (14 -> 9 on 5x6): the fill the tool measured on the board it built
                # before the take is the bar, within FILL_SLACK, and the clamp is said (G17, 2026-10-17)
                r = _row("packed", made["fill"] >= gen - FILL_SLACK,
                         f"the picture's {seen.get('blocks')} blocks fill {fill:.0%}" if isinstance(fill, (int, float)) else
                         f"the picture's {seen.get('blocks')} blocks", "level")
                r["detail"] += (f"; the tool's {built.get('blocks')} fill {gen:.0%} of {made['columns']}x{made['rows']} before the "
                                f"take, the most it builds here; the made board {made['fill']:.0%} (at least {gen - FILL_SLACK:.0%})")
            else:
                r = _row("packed", made["fill"] >= PACKED_MADE,
                         ("the picture's board is " + (f"{fill:.0%} under blocks (measured)" if isinstance(fill, (int, float)) else
                                                       "asked to be as crowded (its fill was not measured reliably)")) +
                         f"; the made board {made['fill']:.0%} (at least {PACKED_MADE:.0%})", "level")
        else:
            p = (prov.get("reading") or {}).get("board", {}).get("pieces")
            if p == "small":
                ok = made["mean_cells"] <= SMALL_MEAN
            elif p == "big":
                ok = made["mean_cells"] >= BIG_MEAN
            elif p == "long":
                ok = made["bars"]
            else:
                ok = None
            r = _row("the pieces", ok, f"the picture's pieces are {p or '?'}; the made pieces average {made['mean_cells']:g} cells"
                     + ("" if ok is not None else " (a mixed or varied set is not judged)"), "level")
        if part in filled and part not in named:
            _filled(r, "filled from the image (the request left it open)")
        elif part not in RELIABLE:
            _filled(r, "read approximately (the picture's piece sizes are not read reliably)")
        out.append(r)
    cross = [m for m in prov.get("colour_map") or [] if m.get("cross")]
    if prov.get("colour_map"):
        # a read colour mapped outside its own family (H16, 2026-10-18: "light green" went to the yellow slot): only when
        # its family's slots were all taken by other read colours
        out.append(_row("the colours keep their family", None if cross else True,
                        "; ".join(f"{m['read']} -> {B.COLOUR_WORDS[m['slot']]}: its family's slots "
                                  f"({', '.join(B.COLOUR_WORDS[x] for x in m['family'])}) are taken" for m in cross)
                        if cross else "each read colour is in a slot of its own family: " +
                        ", ".join(f"{m['read']} -> {B.COLOUR_WORDS[m['slot']]}" for m in prov["colour_map"])))
    if prov.get("clamps"):
        out.append(_row("what the tool cannot build", None, "; ".join(prov["clamps"])))
    return out


def _frame_at(video: Path, at_s: float, out: Path) -> Path | None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not Path(video).is_file():
        return None
    r = subprocess.run([ffmpeg, "-v", "error", "-y", "-ss", f"{max(0.0, at_s):.2f}", "-i", str(video), "-frames:v", "1", str(out)],
                       capture_output=True, text=True)
    return out if r.returncode == 0 and out.is_file() else None


def colour_share(image: Path, box, colour: str) -> float:
    """The share of the box's pixels within LOOK_RGB of a colour."""
    import numpy as np
    from PIL import Image
    with Image.open(image) as im:
        a = np.asarray(im.convert("RGB").crop(tuple(int(v) for v in box))).astype(float)
    if not a.size:
        return 0.0
    c = np.array([int(colour[i:i + 2], 16) for i in (1, 3, 5)], float)
    return float((np.sqrt(((a - c) ** 2).sum(-1)) <= LOOK_RGB).mean())


def look_rows(prompt: str, brief: dict, prov: dict, vdir: Path) -> list[dict]:
    from . import audit
    vs = brief.get("visuals") or {}
    kit = prov.get("look") or {}
    poster = vdir / "ad" / "poster.png"
    out = []
    parts = list(kit.get("parts") or [])
    seen_bg = None
    if poster.is_file():
        seen_bg = "#%02X%02X%02X" % tuple(audit.poster_background(poster))
    if "background" in parts and kit.get("background"):
        bg = kit["background"]
        plan_ok = [h.upper() for h in vs.get("background") or []] == [h.upper() for h in bg]
        pic = ((prov.get("reading") or {}).get("margins") or {})
        follows = pic.get("top") and audit._rgb_dist(bg[0], pic["top"]) <= LOOK_RGB
        if seen_bg is None:
            out.append(_row("the background", None if plan_ok else False, f"the picture's background {bg[0]} to {bg[1]}; the made frame could not be read",
                            "plan"))
        else:
            d = audit._gradient_dist(seen_bg, bg)
            ok = plan_ok and d <= LOOK_RGB and bool(follows)
            out.append(_row("the background", ok, f"the picture's margins {pic.get('top')} to {pic.get('bottom')}; the look taken {bg[0]} to "
                                                 f"{bg[1]} ({'follows them' if follows else 'does not follow them'}); the plan's "
                                                 f"{' to '.join(vs.get('background') or []) or 'none'}; the made frame's margins "
                                                 f"{seen_bg}, {d:.0f} from it (within {LOOK_RGB:g})"
                                                 + ("; drawn as a flat plate behind the board (the game's lit ground lifts "
                                                    "dark colours)" if str(vs.get("background_image") or "").startswith("cbj_plate_") else ""),
                            "plan" if not plan_ok else "ad"))
    if "captions" in parts and kit.get("caption_fill"):
        fill, outline = kit["caption_fill"], kit["caption_outline"]
        plan_ok = (str(vs.get("caption_fill") or "").upper(), str(vs.get("caption_outline") or "").upper()) == (fill, outline)
        c = kit.get("contrast") or {}
        legible = bool(kit.get("legible"))
        shown, bit = None, "the hook's frame could not be read"
        try:
            manifest = json.loads((vdir / "parts.json").read_text())
            hook = next((L for L in manifest.get("layers") or [] if L.get("id") == "hook" and L.get("box") and L.get("from_s") is not None), None)
        except (OSError, ValueError):
            hook = None
        if hook:
            with tempfile.TemporaryDirectory() as tmp:
                at = (float(hook["from_s"]) + float(hook["to_s"] or hook["from_s"])) / 2
                fr = _frame_at(vdir / "ad" / "ad.mp4", at, Path(tmp) / "hook.png")
                if fr:
                    sf, so = colour_share(fr, hook["box"], fill), colour_share(fr, hook["box"], outline)
                    shown = sf >= CAPTION_SHARE and so >= CAPTION_SHARE
                    bit = (f"in the hook's box at {at:.1f} s, {sf:.0%} of the pixels are the fill and {so:.0%} the outline "
                           f"(at least {CAPTION_SHARE:.0%} each)")
        ok = plan_ok and legible and shown is not False
        out.append(_row("the caption colours", ok if shown is not None or not plan_ok else None,
                        f"the picture's captions {fill} with a {outline} outline ({kit.get('caption_source')}); the plan's "
                        f"{vs.get('caption_fill')} / {vs.get('caption_outline')}; contrast {c.get('fill')}:1 (fill) and "
                        f"{c.get('outline')}:1 (outline) on {c.get('against')} ({'legible' if legible else 'under 3:1'}); {bit}",
                        "plan" if not plan_ok else "ad"))
    if "visuals.colours" in prov.get("set", []):  # the blocks repainted in the picture's colours
        want = {m["slot"]: m for m in prov.get("colour_map") or []}
        have = {e["slot"]: e for e in vs.get("blocks") or []}
        # the shown colour against the picture's measured one (G11: brick #BB554C passed for coral #F06D62 at 40); a repair
        # the plan states (two colours too close to tell apart) is the shown colour it gave
        from .imageplan import SAME_SHADE
        repaired = {sl for sl in want if any(n_.startswith(f"{want[sl]['read']} and ") for n_ in brief.get("assumptions") or [])}
        miss = [B.COLOUR_WORDS[s] for s, m in want.items() if s in have and s not in repaired
                and B.colour_distance(have[s]["hex"], "#%02X%02X%02X" % tuple(int(v) for v in m["rgb"])) > SAME_SHADE]
        out.append(_row("the block colours", not miss,
                        "; ".join(f"{m['read']} -> {B.COLOUR_WORDS[s]}" + (f" shown {have[s]['hex']}" if s in have else " (the game's own)")
                                  for s, m in want.items()) + (f"; moved away from the picture's colour: {', '.join(miss)}" if miss else ""),
                        "plan"))
    # what is not taken stays the game's own
    from . import audit as A
    own = A.asked(prompt)
    taken = set(parts) if prov.get("look") else set()
    if "visuals.colours" in prov.get("set", []):
        taken.add("blocks")
    checks = []
    stated_bg = own.get("background") is not None
    if "background" not in taken:
        # the background's own fields (F11, 2026-10-17: a block repaint sets the theme "custom", which is no background);
        # a named theme other than custom paints its own background (brief.PALETTES)
        ok_plan = not vs.get("background") and not vs.get("background_image") and vs.get("theme") in ("game", "custom", None)
        d = A._rgb_dist(seen_bg, GAME_POSTER_BG) if seen_bg else None
        words_bg = re.search(r"\b(background|backdrop)\b", prompt or "", re.I) and vs.get("background") and \
            not re.search(r"\bthe game'?s (own |standard |original |usual )?(look|background)\b", prompt or "", re.I)
        if stated_bg:
            checks.append((None, f"the background is the request's own ({own['background']})"))
        elif words_bg:
            # the words set a background of their own (H9, 2026-10-18: "the arcade purple-to-pink glow" failed against the
            # game's own): the made frame against what the plan set
            dd = audit._gradient_dist(seen_bg, [h.upper() for h in vs["background"]]) if seen_bg else None
            checks.append((dd is None or dd <= LOOK_RGB,
                           f"the background is set by the words: the plan's {' to '.join(vs['background'])}"
                           + (f"; the made frame's margins {seen_bg}, {dd:.0f} from it" if dd is not None else "")))
        else:
            checks.append((ok_plan and (d is None or d <= LOOK_RGB),
                           f"the background: the plan's {' to '.join(vs.get('background') or []) or GAME_OWN}"
                           + (f"; the made frame's margins {seen_bg}, {d:.0f} from the game's own {GAME_POSTER_BG}" if d is not None else "")))
    if "captions" not in taken:
        caption_words = re.search(r"\bcaptions?\b[^.;]{0,30}\b(colou?rs?|white|yellow|black|outline)\b", prompt or "", re.I)
        if caption_words:
            checks.append((None, "the captions' colours are the request's own"))
        else:
            checks.append((vs.get("caption_fill") is None and vs.get("caption_outline") is None,
                           f"the captions: the plan's {vs.get('caption_fill') or GAME_OWN} / {vs.get('caption_outline') or GAME_OWN}"))
    if "blocks" not in taken and vs.get("blocks") and imageplan_words_name_blocks(prompt):
        checks.append((None, "the block colours are the request's own: " + ", ".join(e["name"] or e["slot"] for e in vs["blocks"])))
    elif "blocks" not in taken:
        checks.append((not vs.get("blocks"), "the blocks: " + ("the game's own colours" if not vs.get("blocks") else
                                                                 "repainted " + ", ".join(e["name"] or e["slot"] for e in vs["blocks"]))))
    judged = [c for c in checks if c[0] is not None]
    if checks:
        out.append(_row("not taken stays the game's own", all(c[0] for c in judged) if judged else None,
                        "; ".join(t for _, t in checks), "plan"))
    return out


def imageplan_words_name_blocks(prompt: str) -> bool:
    """The words name block colours of their own ("coral blocks"): a repaint the request asks, not one the picture set."""
    from .imageplan import BLOCK_COLOUR_ASK, _words
    return bool(BLOCK_COLOUR_ASK.search(_words(prompt)))


GAME_POSTER_BG = "#E4F0FE"  # imageplan.GAME_POSTER_BG
GAME_OWN = "the game's own"
NO_HUD = re.compile(r"\b(no|without|hide|hidden|remove)\b[^.;]{0,30}\b(hud|level badge|badge|timer|clock|level number)\b", re.I)
KEEP_HUD = re.compile(r"\b(keep|show|with)\b[^.;]{0,40}\b(the )?(timer|clock|hud)\b", re.I)


BADGE_WORDS = re.compile(r"\b(badge|level number|level label)\b", re.I)
TIMER_WORDS = re.compile(r"\b(timer|clock|countdown)\b", re.I)
HIDE_VERB = re.compile(r"\b(no|without|hide|hides|hidden|remove|drop)\b", re.I)
SHOW_VERB = re.compile(r"\b(keep|keeps|show|shows|showing|visible)\b", re.I)


def expected_hud(prompt: str, prov: dict) -> tuple[tuple[bool, bool], str]:
    """(level shown, clock shown) the request and the picture ask, and why. The badge and the timer are read apart, clause
    by clause (H2, 2026-10-18: "hide the level badge as the picture does but keep the timer" was read as "no HUD"): a
    clause that hides the badge hides the badge, one that keeps the timer keeps it; "no HUD" hides both."""
    level, clock, said = True, True, False
    for clause in re.split(r"[.;,]|\bbut\b", prompt or ""):
        hide, show = HIDE_VERB.search(clause), SHOW_VERB.search(clause)
        if re.search(r"\bhud\b", clause, re.I) and hide:
            level, clock, said = False, False, True
            continue
        b, t = BADGE_WORDS.search(clause), TIMER_WORDS.search(clause)
        if hide and (b or t):
            level, clock, said = (False if b else level), (False if t else clock), True
        elif show and (b or t):
            level, clock, said = (True if b else level), (True if t else clock), True
    if said:
        return (level, clock), "the request says it"
    if any(t.startswith("the screen: no HUD") for t in prov.get("taken") or []):
        return (False, False), "the picture's look shows none"
    return (True, True), "the game's own screen (not asked)"


def screen_row(prompt: str, brief: dict, prov: dict, record: dict) -> dict:
    from . import studio
    (want_level, want_clock), why = expected_hud(prompt, prov)
    vs = brief.get("visuals") or {}
    plan = (bool(vs.get("hud_level", True)), bool(vs.get("hud_timer", True)))
    words = lambda lv, ck: "no HUD" if not (lv or ck) else f"{'the level' if lv else 'no level'} and {'the clock' if ck else 'no clock'}"  # noqa: E731
    made, bit = None, "the recording's job could not be read"
    try:
        job = json.loads((studio.STUDIO / record["recording"]["dir"] / "job.json").read_text())
        hide = set(job.get("hide") or [])
        made = ("MainBar" not in hide and "LevelCircle" not in hide, "MainBar" not in hide and "TimeText" not in hide)
        bit = f"the recording shows {words(*made)}"
    except (OSError, ValueError, KeyError, TypeError):
        pass
    ok = plan == (want_level, want_clock) and (made is None or made == plan)
    return _row("the screen", ok, f"asked: {words(want_level, want_clock)} ({why}); planned: {words(*plan)}; {bit}",
                "plan" if plan != (want_level, want_clock) else "play")


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(t or "").lower()).strip()


END_CARD_MAX_S = 8.0  # IMAGE-GUIDED-EVAL-CHECKS D5: an end card of 3-6 s; past this it is padding (S3, 2026-10-19: 15.5 s of 40)


def end_card_row(vdir: Path) -> dict | None:
    """D5: the end card is a card, not padding: its part in parts.json at most END_CARD_MAX_S. A longer one means the play
    was too short for the stated length on this board (a copied board has the blocks it has): said, so the owner sees it."""
    import json
    try:
        manifest = json.loads((vdir / "parts.json").read_text())
    except (OSError, ValueError):
        return None
    parts = {p.get("id"): p for p in manifest.get("parts") or [] if isinstance(p, dict)}
    end = parts.get("end")
    if not end or end.get("from_s") is None or end.get("to_s") is None:
        return None
    length = float(end["to_s"]) - float(end["from_s"])
    total = float(manifest.get("duration_s") or 0)
    play = parts.get("play") or {}
    play_s = (float(play["to_s"]) - float(play["from_s"])) if play.get("to_s") is not None and play.get("from_s") is not None else None
    ok = length <= END_CARD_MAX_S
    return _row("the end card is a card, not padding", ok,
                f"the end card holds {length:.1f} s of the {total:g} s ad (at most {END_CARD_MAX_S:g} s)" +
                (f"; the play is {play_s:.1f} s" if play_s is not None else "") +
                ("" if ok else ": the board's blocks fill less of the ad than the stated length needs; a shorter ad, more mistakes or a calmer tempo would fill it honestly"),
                "plan")


def label_row(brief: dict, prov: dict) -> dict | None:
    """A10 (2026-10-19): "the same level number" asked: the badge the game rendered is the picture's number (the brief's
    label is what the recorder hands the game; the shared "HUD level number" row measures a number the request types)."""
    hud = prov.get("hud") or {}
    if not hud.get("took"):
        return None
    pic = ((prov.get("reading") or {}).get("hud") or {}).get("level")
    have = (brief.get("level") or {}).get("label")
    return _row("the level number", str(have) == str(pic) if pic is not None else None,
                f"the picture's badge reads level {pic}; the creative's badge is set to {have}" + ("" if str(have) == str(pic) else " (differs)"), "plan")


def copied_row(prompt: str, brief: dict, prov: dict, vdir: Path) -> dict:
    file = prov.get("file")
    roles = set(prov.get("roles") or [])
    try:
        ad = json.loads((vdir / "ad" / "ad.json").read_text())
    except (OSError, ValueError):
        ad = {}
    uses = sorted({lid for lid, L in (ad.get("layers") or {}).items() if file and file in json.dumps(L)}
                  | {a["file"] for a in brief.get("assets") or [] if a.get("file") == file}
                  | ({"the background picture"} if (brief.get("visuals") or {}).get("background_image") == file else set()))
    seen = {_norm(c): c for c in ((prov.get("reading") or {}).get("captions") or [])}
    quoted = {_norm(q[0] or q[1]) for q in B.QUOTED.findall(prompt or "")}
    same_words = re.search(r"\bsame (words?|captions?|text|wording)\b", prompt or "", re.I)
    copied = [f"{k} \"{t}\"" for k in B.CONCEPT_TEXTS for t in [(brief.get("concept") or {}).get(k)]
              if t and _norm(t) in seen and _norm(t) not in quoted and not same_words]
    bad = []
    if uses and not roles & {"asset", "modify"}:
        bad.append(f"the picture itself is used by {', '.join(uses)}")
    if copied:
        bad.append("the picture's own caption words: " + "; ".join(copied))
    detail = ("; ".join(bad) if bad else
              "no layer uses the picture itself" + (f" outside its slot ({', '.join(uses)})" if uses else "") +
              "; no planned caption is the picture's own" + (f" (the quoted {', '.join(seen[q] for q in quoted & set(seen))} is "
                                                             f"the request's)" if quoted & set(seen) else "") +
              "; not copied: " + "; ".join(prov.get("not_copied") or []))
    return _row("nothing copied", not bad, detail, "plan" if copied else "ad")


def counted_row(prov: dict) -> dict | None:
    """The board counted on the board, never from a caption (I7): only when a caption claims a block count."""
    reading = prov.get("reading") or {}
    claims = [x for x in reading.get("caption_claims") or [] if x.get("what") == "blocks"]
    bd = prov.get("board") or {}
    if not claims or not bd:
        return None
    seen = (bd.get("seen") or {}).get("blocks")
    c = claims[0]
    if seen is None:
        return _row("counted on the board", None, f"the caption says {c['n']} blocks; the board's blocks were not counted")
    took = "blocks" in (bd.get("named") or []) + (bd.get("filled") or [])
    return _row("counted on the board", took and seen != c["n"] if seen != c["n"] else None,
                f"the caption says {c['n']} blocks (\"{c['caption']}\"); the board shows {seen}"
                + (f"; the plan takes {seen} from the board ({(bd.get('built') or {}).get('blocks')} built)" if took else
                   "; the block count is not taken"), "plan")


PICTURE_WORDS = re.compile(r"\b(picture|image|screenshot|reference|the photo)\b", re.I)
NEGATED = re.compile(r"\b(not|never|no|nothing|isn't|aren't|ignored|left out|instead of)\b", re.I)


def board_not_taken_row(brief: dict, prov: dict, made: dict | None) -> dict | None:
    """When the board is not a role and the picture has one: the level's plan does not cite the picture (F1, 2026-10-17:
    "it suits the picture's idea of the narrow neck" for a request that took only the colours); the made shape is info."""
    seen = ((prov.get("reading") or {}).get("board")) or {}
    if "board" in (prov.get("roles") or []) or not seen:
        return None
    from .imageplan import board_shape
    row = next((r for r in brief.get("controls") or [] if r.get("control") == "level"), {}) or {}
    texts = [row.get("plan") or "", row.get("why") or ""] + [str((brief.get("concept") or {}).get(k) or "") for k in B.CONCEPT_TEXTS]
    # a sentence that takes from the picture, not one that says it is not used ("The board in the picture is not copied")
    cited = [x for t in texts for x in re.split(r"(?<=[.!?])\s+", t)
             if PICTURE_WORDS.search(x) and not NEGATED.search(x)]
    pic_shape = board_shape(seen)[0]
    shape_bit = f"the made level is {(made or {}).get('shape') or '?'}, the picture's board {pic_shape}" + (
        " (the same shape, from the words or the tool's default)" if made and made.get("shape") == pic_shape else "")
    return _row("the board is not taken", not cited, ("the level's plan cites the picture: " + " | ".join(t[:160] for t in cited))
                if cited else f"the level's plan does not cite the picture; {shape_bit} (info)", "plan")


LEFT_WORDS = re.compile(r"\b(?:last|final)\s+(one|two|three|1|2|3)\s+(?:\w+\s+)?(?:blocks?|pieces?)\b|"
                        r"\b(one|two|three|1|2|3)\s+(?:\w+\s+)?(?:blocks?|pieces?)\s+(?:left|remaining|still on)\b", re.I)
NUMBER = {"one": 1, "two": 2, "three": 3, "1": 1, "2": 2, "3": 3}


def blocks_left_asked(prompt: str) -> int | None:
    m = LEFT_WORDS.search(prompt or "")
    return NUMBER[(m.group(1) or m.group(2)).lower()] if m else None


def blocks_left_row(prompt: str, brief: dict, record: dict) -> dict | None:
    """The blocks still on the board at the cut, as the request states them ("before the last three blocks leave"),
    measured on the recording (its blocks that never left). For a cliffhanger (F5, 2026-10-17) and a time-out (H20,
    2026-10-18: "the clock runs out with two blocks left" stopped with one, unjudged): a time-out plays exactly one, so
    another count asked is info with the limit the plan states."""
    from . import studio
    from .imageplan import TIME_OUT_LEFT
    n = blocks_left_asked(prompt)
    ending = (brief.get("gameplay") or {}).get("ending")
    if n is None or ending not in ("cliffhanger", "time_out"):
        return None
    planned = (brief.get("gameplay") or {}).get("blocks_left") if ending == "cliffhanger" else TIME_OUT_LEFT
    try:
        res = json.loads((studio.STUDIO / record["recording"]["dir"] / "result.json").read_text())
        left = sum(1 for f in res.get("block_gone_frames") or [] if f is None or f < 0)
    except (OSError, ValueError, KeyError, TypeError):
        return _row("blocks left at the cut", None, f"{n} asked; the recording could not be read")
    detail = f"{n} asked; planned {planned if planned is not None else 'the default'}; the recording stops with {left} on the board"
    if ending == "time_out" and n != TIME_OUT_LEFT:
        return _row("blocks left at the cut", None, detail + f"; the game's time-out ends with exactly {TIME_OUT_LEFT} block one "
                                                            f"cell from its gate (the limit, said in the plan)")
    return _row("blocks left at the cut", left == n, detail, "plan" if planned not in (None, n) else "play")


FAST_WORDS = re.compile(r"\b(fast|quick|rapid|speedy)\s+(cascade|chain|finish|streak|clear)\b", re.I)
FAST_LAST_PAUSE_S = 0.5  # the last third's pauses between drags at most this: a fast finish (the tool's own fast streak
# recordings: median 0.30 s, 75th percentile 0.50 s; normal tempo 0.59 s, calm 1.0 s; 2026-10-17)


def fast_finish_row(prompt: str, brief: dict, record: dict) -> dict | None:
    """"A fast cascade": the fast tempo and the streak finish planned, and the last third of the play's pauses short,
    measured on the recording (F7, 2026-10-17)."""
    from . import audit, studio
    if not FAST_WORDS.search(prompt or ""):
        return None
    pc, gp = brief.get("pacing") or {}, brief.get("gameplay") or {}
    try:
        res = json.loads((studio.STUDIO / record["recording"]["dir"] / "result.json").read_text())
        pauses = audit.pause_pace(res.get("drags") or [])
    except (OSError, ValueError, KeyError, TypeError):
        pauses = None
    plan_ok = pc.get("tempo") == "fast" and (gp.get("finish") == "streak" or gp.get("ending") not in ("win", "near_fail"))
    from .imageplan import PAIR_CLAIM
    claims = [k for k in ("hook", "mistake", "cascade", "result") if PAIR_CLAIM.search(str((brief.get("concept") or {}).get(k) or ""))]
    if claims:  # a caption promising clears the game never plays (G14)
        plan_ok = False
    if pauses is None:
        return _row("the fast finish", None if plan_ok else False, f"planned {pc.get('tempo')} tempo, finish {gp.get('finish')}; "
                                                                   "fewer than 6 drags recorded, so the pace is not measured", "plan")
    ok = plan_ok and pauses["last"] <= FAST_LAST_PAUSE_S
    from .imageplan import CASCADE_NOTE
    return _row("the fast finish", ok, f"planned {pc.get('tempo')} tempo, finish {gp.get('finish')}; the last third's pauses "
                                       f"average {pauses['last']:.2f} s (at most {FAST_LAST_PAUSE_S:g} s; the first third "
                                       f"{pauses['first']:.2f} s); {CASCADE_NOTE}", "plan" if not plan_ok else "play")


def quoted_row(prompt: str, vdir: Path) -> dict | None:
    """Each caption the request quotes is drawn in the ad: its text among the parts manifest's caption layers (F12)."""
    quotes = [(m.group(1) or m.group(2)).strip() for m in B.QUOTED.finditer(prompt or "")]
    if not quotes:
        return None
    try:
        layers = json.loads((vdir / "parts.json").read_text()).get("layers") or []
    except (OSError, ValueError):
        return _row("the quoted captions", None, "the parts manifest could not be read")
    drawn = {_norm(L.get("text")): L for L in layers if L.get("text") and L.get("from_s") is not None}
    missing = [q for q in quotes if _norm(q) not in drawn]
    return _row("the quoted captions", not missing,
                "; ".join(f"\"{q}\" " + (f"drawn as {drawn[_norm(q)]['id']} at {drawn[_norm(q)]['from_s']:g}-{drawn[_norm(q)]['to_s']:g} s"
                                           if _norm(q) in drawn else "not drawn") for q in quotes), "plan")


def play_fills_row(prov: dict, record: dict, vdir: Path) -> dict | None:
    """The play fills the ad (the brief, p.2; G1, 2026-10-17): the live play, from the first drag to the last exit or the
    cut (the parts manifest's play part), against the ad's length, at least PLAY_SHARE_ROW when the board is the
    picture's. A count the request names that cannot fill makes the row info, with the limit the plan stated."""
    from .imageplan import PLAY_SHARE_ROW
    if "board" not in (prov.get("roles") or []) or not prov.get("board"):
        return None
    try:
        man = json.loads((vdir / "parts.json").read_text())
    except (OSError, ValueError):
        return _row("the play fills the ad", None, "the parts manifest could not be read")
    play = next((x for x in man.get("parts") or [] if x.get("id") == "play" and x.get("from_s") is not None), None)
    total = float(man.get("duration_s") or record.get("length_s") or 0)
    if not play or not total:
        return _row("the play fills the ad", None, "no play part was measured")
    secs = float(play["to_s"]) - float(play["from_s"])
    share = secs / total
    pf = prov.get("play_fill") or {}
    named = "blocks" in ((prov.get("board") or {}).get("named") or [])
    detail = (f"live play {secs:.1f} s of the {total:g} s ad ({share:.0%}; at least {PLAY_SHARE_ROW:.0%} when the board is the "
              f"picture's); expected before the take {pf.get('expected_s', '?')} s" +
              (f"; {'; '.join(pf['levers'])}" if pf.get("levers") else ""))
    if share < PLAY_SHARE_ROW and pf.get("limit") and (named or not pf.get("levers_left")):
        # nothing is left that lengthens this play (G16, 2026-10-17: B2's 10 blocks at a fast tempo, revised twice for
        # nothing): the limit the plan states, not a miss
        return _row("the play fills the ad", None, detail + f"; the limit, said in the plan: {pf['limit']}")
    return _row("the play fills the ad", share >= PLAY_SHARE_ROW, detail, "level")


STUCK_MIN_S = 0.8  # a stopped or wrong drag held at least this long reads as a stop (G3: a few frames were never seen)


def stuck_visible_row(prompt: str, brief: dict, record: dict) -> dict | None:
    """The stuck moment is visible (G3, 2026-10-17): when the request asks for a stuck moment or wrong moves, each wrong
    drag of the recording (one that does not leave: placed, bumped or stopped, before the last) lasts STUCK_MIN_S or more."""
    from . import studio
    from .imageplan import STUCK_WORDS
    gp = brief.get("gameplay") or {}
    if not STUCK_WORDS.search(prompt or "") or not (gp.get("mistakes") or any(
            e.get("action") in ("stuck", "blocks") for e in gp.get("events") or [])):
        return None
    try:
        res = json.loads((studio.STUDIO / record["recording"]["dir"] / "result.json").read_text())
    except (OSError, ValueError, KeyError, TypeError):
        return _row("the stuck moment is visible", None, "the recording could not be read")
    fps = float(res.get("fps") or 30)
    drags = res.get("drags") or []
    # the planned stuck drags only: the play's own mistake beats (play.json, one beat a drag), never an ordinary move
    # aside (G17, 2026-10-17: B3's 0.5 s repositioning drags failed the row beside two 1.0-1.6 s stuck moments)
    try:
        beats = json.loads((studio.STUDIO / record["recording"]["dir"] / "play.json").read_text()).get("beats") or []
    except (OSError, ValueError, KeyError, TypeError):
        beats = []
    if beats and len(beats) == len(drags):
        wrong = [d for d, bt in list(zip(drags, beats))[:-1] if bt.get("kind") in ("mistake", "bump", "attempt")]
    else:
        wrong = [d for d in drags[:-1] if d.get("result") != "exit"]
    if not wrong:
        return _row("the stuck moment is visible", False, "no wrong or stopped drag was recorded before the end", "play")
    secs = [(d["end_frame"] - d["start_frame"]) / fps for d in wrong]
    ok = all(x >= STUCK_MIN_S for x in secs)
    return _row("the stuck moment is visible", ok, "the planned stuck drags last " + ", ".join(f"{x:.1f} s" for x in secs) +
                f" (each at least {STUCK_MIN_S:g} s); planned {gp.get('mistakes') or 0} wrong move(s)", "play")


def question_row(prompt: str, brief: dict, vdir: Path) -> dict | None:
    """A cliffhanger's question follows the live cut (G13c): no replay part between the gameplay and the question, as
    the parts manifest has them. Info when the request asks for a replay."""
    from .imageplan import REPLAY_ASKED
    if (brief.get("gameplay") or {}).get("ending") != "cliffhanger":
        return None
    try:
        parts = json.loads((vdir / "parts.json").read_text()).get("parts") or []
    except (OSError, ValueError):
        return _row("the question follows the live cut", None, "the parts manifest could not be read")
    timed = [x for x in parts if x.get("from_s") is not None and x.get("to_s") is not None]
    words = "; ".join(f"{x.get('name') or x.get('id')} {float(x['to_s']) - float(x['from_s']):.1f} s" for x in timed)
    ids = [x.get("id") for x in timed]
    play_i = next((i for i, x in enumerate(timed) if x.get("kind") == "gameplay"), None)
    q_i = next((i for i, x in enumerate(timed) if x.get("id") == "question"), None)
    between = [x for x in timed[(play_i or 0) + 1:q_i if q_i is not None else len(timed)] if x.get("kind") == "replay"] \
        if play_i is not None else []
    if REPLAY_ASKED.search(prompt or ""):
        return _row("the question follows the live cut", None, f"the request asks for a replay; the parts: {words}")
    if q_i is None:
        return _row("the question follows the live cut", False, f"no question part was made; the parts: {words}", "ad")
    return _row("the question follows the live cut", not between,
                (f"a replay plays before the question and can show the move it asks about; " if between else
                 "the question comes straight after the live play; ") + f"the parts: {words}",
                "plan" if (brief.get("sequence") or {}).get("replay") else "ad")


def real_choice_row(prompt: str, brief: dict, record: dict, vdir: Path) -> dict | None:
    """A cliffhanger's question is a real choice (G15): at the cut, as the recording played it (the level and the drags
    before the last one, the final push or pick-up), some remaining block is blocked. Info when the request names the
    blocks left itself and none is blocked (its count wins)."""
    from . import studio
    from .level import load_level
    from .play import _can_exit_now
    from .rules import occupancy
    from .solver import Drag, replay
    if (brief.get("gameplay") or {}).get("ending") != "cliffhanger":
        return None
    try:
        level = load_level(vdir / "level.json")
        job = json.loads((studio.STUDIO / record["recording"]["dir"] / "job.json").read_text())
        drags = [Drag(int(d["block"]), tuple((c["x"], c["y"]) for c in d["path"]), bool(d.get("exits")), d.get("exit_index"))
                 for d in job.get("drags") or []]
        state = replay(level, drags[:-1])
    except Exception as e:
        return _row("the cliffhanger is a real choice", None, f"the cut could not be rebuilt ({str(e)[:100]})")
    from .imageplan import _block_word
    occ = occupancy(level, state)
    left = [i for i, p in enumerate(state) if p is not None]
    blocked = [i for i in left if not _can_exit_now(level, state, i, occ)]
    words = ", ".join(_block_word(level, i).replace("the ", "") for i in left)
    detail = (f"at the cut {len(left)} blocks are left ({words}); " +
              (f"{' and '.join(_block_word(level, i) for i in blocked)} cannot leave yet" if blocked else "every one could leave at once"))
    if not blocked and blocks_left_asked(prompt) is not None:
        return _row("the cliffhanger is a real choice", None, detail + "; the request names the blocks left itself")
    return _row("the cliffhanger is a real choice", bool(blocked), detail, "play")


NEAR_FAIL_WORDS = re.compile(r"\b(almost|nearly|barely|just about|close to|on the verge of)\b[^.;]{0,25}\b(runs?|running|ran) out of "
                             r"time\b|\b(almost|nearly)\b[^.;]{0,15}\b(times? out|out of time)\b", re.I)


def rejudge(prompt: str, brief: dict, checks: list[dict]) -> list[dict]:
    """Two rows of the shared text audit judged against the request's own words in this workflow: "almost runs out of
    time before clearing it" is a near-fail, not a time-out (F3); "before the last three blocks leave" is the blocks
    left at the cut, not the board's count (F5). Since 2026-10-17 (the owner's decision) audit.py reads both correctly
    itself (audit._ALMOST_OUT, audit._LAST_N and its "Asked: blocks left at the cut" row), so these two branches no
    longer fire; they stay as a harmless second guard. Each becomes info with the reason. Returns the checks."""
    from .imageplan import transforms_asked
    gp = brief.get("gameplay") or {}
    left = blocks_left_asked(prompt)
    mirrored = any(t["kind"] == "mirror" for t in transforms_asked(prompt))
    out = []
    for c in checks:
        c = dict(c)
        if c.get("status") == "failed" and str(c.get("check", "")).startswith("Asked: symmetric") and mirrored:
            c.update(status="info", where=None, detail="judged against the words here: \"mirrored\" asks for the picture's board "
                                                       "mirrored (see Image: the board mirrored), not for a symmetric board: " + str(c.get("detail")))
        elif c.get("status") == "failed" and c.get("check") == "Asked: ending" and NEAR_FAIL_WORDS.search(prompt or "") \
                and gp.get("ending") == "near_fail" and "time-out" in str(c.get("detail")):
            c.update(status="info", where=None, detail=f"judged against the words here: \"{NEAR_FAIL_WORDS.search(prompt).group(0)}\" "
                                                       f"is a near-fail, and the plan is a near-fail (the shared reading took "
                                                       f"'runs out of time' alone as a time-out): {c.get('detail')}")
        elif c.get("status") == "failed" and str(c.get("check", "")).startswith("Asked: block") and left is not None \
                and re.match(rf"\s*{left} asked\b", str(c.get("detail") or "")):
            c.update(status="info", where=None, detail=f"judged against the words here: \"{LEFT_WORDS.search(prompt).group(0)}\" "
                                                       f"is the blocks left at the cut (see Image: blocks left at the cut), not "
                                                       f"the board's count: {c.get('detail')}")
        elif c.get("status") == "failed" and str(c.get("check", "")).startswith("Asked: packed") and \
                (((brief.get("reference") or {}).get("board") or {}).get("built") or {}).get("fill_target") is not None:
            # H10 (2026-10-18, S10): "as crowded as this picture" is the picture's fill, judged by the image row; the
            # shared reading took "crowded" alone as a packed board
            tgt = brief["reference"]["board"]["built"]["fill_target"]
            c.update(status="info", where=None, detail=f"judged against the picture here: \"as crowded\" as this picture is "
                                                       f"about {tgt:.0%} of the board under blocks, not a packed board (see "
                                                       f"Image: as crowded as the picture): {c.get('detail')}")
        out.append(c)
    return out


def copied_board_rows(prompt: str, prov: dict, vdir: Path) -> list[dict]:
    """The rows of a board copied from the picture (IMAGE-GUIDED-EVAL-CHECKS B2, A6, A7, A8, 2026-10-19): the made level
    against the board read cell by cell (with the asked transforms), the reading's own verification, and one row per
    transform the request asked (done or not)."""
    import json
    from . import imagecells as IC
    bd = prov.get("board") or {}
    want, pic = bd.get("level"), bd.get("picture_level")
    path = vdir / "level.json"
    if not want or not path.is_file():
        return [_row("the board is the picture's", None, "the made level could not be read")]
    made = json.loads(path.read_text())
    same, what = IC.same_board(want, made)
    ver = bd.get("verify") or {}
    doubts = ver.get("doubts") or []
    detail = (f"the picture's board: {bd.get('text')}; made: {IC.describe(made)}; {what}. The reading checked {ver.get('checked')} cells "
              f"against the picture's pixels in {ver.get('asks')} ask(s)" + (f"; {len(doubts)} doubt(s): " + "; ".join(doubts[:3]) if doubts else "; no doubt left")
              + (f"; solvable in {ver.get('solve')}" if ver.get("solve") else ""))
    out = [_row("the board is the picture's", bool(same), detail, "level")]
    made_cols, pic_cols = IC.colours_of(made), IC.colours_of(pic or want)
    for t in bd.get("transforms") or []:
        if t["kind"] == "colours":
            n = int(t["n"])
            target = max(2, min(7, len(pic_cols) + n))
            out.append(_row("more or fewer colours than the picture", len(made_cols) == target,
                            f"the picture's board has {len(pic_cols)} colours ({', '.join(B.COLOUR_WORDS[c] for c in pic_cols)}); asked "
                            f"{'+' if n > 0 else ''}{n}; the made board has {len(made_cols)} ({', '.join(B.COLOUR_WORDS[c] for c in made_cols)}); {t.get('note')}", "level"))
        elif t["kind"] == "recolour":
            gates = {B.COLOURS[e["requiredColor"]] for e in made.get("ExitDatas") or []}
            ok = t["from"] not in made_cols and t["to"] in made_cols and t["from"] not in gates and t["to"] in gates
            out.append(_row("a colour became another", ok, f"asked: the {B.COLOUR_WORDS[t['from']]} blocks become {B.COLOUR_WORDS[t['to']]}; the made "
                            f"board's blocks: {', '.join(B.COLOUR_WORDS[c] for c in made_cols)}; its gates: {', '.join(sorted(B.COLOUR_WORDS[c] for c in gates))}", "level"))
        elif t["kind"] == "mirror":
            others = [x for x in bd.get("transforms") or [] if x["kind"] != "mirror"]
            if pic and not others:
                ok, how = IC.same_board(IC.mirror(pic, t["axis"]), made)
                out.append(_row("the board mirrored", ok, f"the picture's board mirrored {'top to bottom' if t['axis'] == 'tb' else 'left to right'} "
                                f"against the made level: {how}", "level"))
            else:
                out.append(_row("the board mirrored", None, f"mirrored {'top to bottom' if t['axis'] == 'tb' else 'left to right'} together with other "
                                "changes; judged by the row 'the board is the picture's'"))
        elif t["kind"] == "harder":
            a, b = IC.min_drags(pic) if pic else None, IC.min_drags(made)
            ok = a is not None and b is not None and b > a
            out.append(_row("harder than the picture's board", ok, f"the picture's board solves in {a} drags, the made board in {b}; {t.get('note')}", "level"))
        elif t["kind"] == "blocks":
            a, b, n = len((pic or want)["GridBlockDatas"]), len(made["GridBlockDatas"]), int(t["n"])
            ok = (b < a) if t.get("half") or n < 0 else (b > a)
            if not t.get("half") and abs(b - a) != abs(n):
                ok = ok and "could" in str(t.get("note") or "") or ok and "only" in str(t.get("note") or "")
            out.append(_row("more or fewer blocks than the picture", ok, f"the picture's board has {a} blocks; asked {'half' if t.get('half') else f'{n:+d}'}; "
                            f"the made board has {b}; {t.get('note')}", "level"))
        elif t["kind"] == "easier":
            a, b = IC.min_drags(pic) if pic else None, IC.min_drags(made)
            ok = (a is not None and b is not None and b < a) or len(made["GridBlockDatas"]) < len((pic or want)["GridBlockDatas"])
            out.append(_row("easier than the picture's board", ok, f"the picture's board solves in {a} drags with {len((pic or want)['GridBlockDatas'])} blocks, "
                            f"the made board in {b} with {len(made['GridBlockDatas'])}; {t.get('note')}", "level"))
        elif t["kind"] == "repair":
            out.append(_row("the board as drawn was repaired", None, t.get("note") or "repaired"))
        elif t["kind"] == "walls":
            out.append(_row("thin walls as wall cells", None, t.get("note") or ""))
    for f in bd.get("transforms_failed") or []:
        name = {"colours": "more or fewer colours than the picture", "recolour": "a colour became another", "mirror": "the board mirrored",
                "harder": "harder than the picture's board", "easier": "easier than the picture's board",
                "blocks": "more or fewer blocks than the picture"}[f["kind"]]
        out.append(_row(name, False, f"asked, not done: {f.get('why')}", "plan"))
    return out


LIKENESS_ASK = ("Two pictures side by side. LEFT: a reference screenshot of a Color Block Jam level. RIGHT: a frame of a video ad made "
                "from it (its look may differ on purpose: background, captions, the HUD). Compare ONLY the game board: the grid, the "
                "holes, every block's place, shape and colour, every gate's place and colour. Items on the LEFT that are not "
                "blocks of this game (bubbles, counters, numbered covers, boosters, a hand) were left out on purpose and do not "
                "count. The RIGHT is drawn by the game, so a colour may be the nearest of its seven (teal as blue, magenta as "
                "purple, light blue as green): count a colour difference only when a block's colour family changes. {expected}"
                'Return ONLY JSON: {{"same_board": "yes|partly|no", "differences": ["one line each, naming the place: e.g. top-left 2x2 is red on '
                'the left and blue on the right; a gate is missing on the right edge"], "note": "one line"}}')


LIKENESS_TIMEOUT_S = 150.0


def likeness_row(prov: dict, vdir: Path) -> dict | None:
    """B10 (2026-10-19): the viewer model's own eye on the picture's board against the made board's first play frame, a
    second opinion beside the cell comparison. Pass on "yes", failed on "no" (where level), info on "partly" with the
    differences; None when the picture's crop or the frame is missing."""
    import base64
    import json
    from PIL import Image
    from . import audit, llm, studio
    from .reference import _ask_json
    bd = prov.get("board") or {}
    ev = bd.get("evidence") or {}
    ref = studio.STUDIO / "_cells" / str(ev.get("crop") or "")
    if not ev.get("crop") or not ref.is_file():
        ref = Path(str(bd.get("frame") or "")) if bd.get("frame") else studio.STUDIO / "uploads" / str(prov.get("file") or "")
    try:
        manifest = json.loads((vdir / "parts.json").read_text())
    except (OSError, ValueError):
        manifest = {}
    frame = audit.play_frame(vdir, manifest)
    if not ref.is_file() or frame is None:
        return None
    try:
        a, b = Image.open(ref).convert("RGB"), Image.open(frame).convert("RGB")
        h = 900
        a = a.resize((max(1, round(a.width * h / a.height)), h))
        b = b.resize((max(1, round(b.width * h / b.height)), h))
        sheet = Image.new("RGB", (a.width + b.width + 30, h), (255, 255, 255))
        sheet.paste(a, (0, 0))
        sheet.paste(b, (a.width + 30, 0))
        out = vdir / "likeness_sheet.png"
        sheet.save(out)
        expected = ""
        if bd.get("transforms"):
            expected = ("These differences are ASKED FOR and do not count: " + "; ".join(t["note"] for t in bd["transforms"]) + ". ")
        client = llm.vision_client()
        if hasattr(client, "timeout"):
            client.timeout = LIKENESS_TIMEOUT_S  # an optional second opinion: never the job's long wait (S2, 2026-10-19: a hung CLI call)
        part = {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(out.read_bytes()).decode()}}
        ans = _ask_json(client, LIKENESS_ASK.format(expected=expected), part, out)
    except Exception as e:  # a judge that fails is said, never a pass
        return _row("looks like the picture (viewer)", None, f"the viewer model could not compare them ({str(e)[:120]})")
    same = str(ans.get("same_board") or "").lower()
    diffs = [str(x)[:160] for x in (ans.get("differences") or [])][:5]
    detail = (f"the viewer model says {same or '?'}" + (": " + "; ".join(diffs) if diffs else "") + (f" ({ans.get('note')})" if ans.get("note") else "")
              + f"; model {getattr(client, 'last_model', None)}")
    return _row("looks like the picture (viewer)", True if same == "yes" else None if same == "partly" else False, detail, "level")


# what a parsed ask is measured by: the words in the rows' names (lower-cased substrings) that judge it
COVERAGE = {
    "blocks": ("block count", "the board's blocks", "the board is the picture's"), "colours": ("colours",), "difficulty": ("difficulty",),
    "length_s": ("length",), "clock_left_s": ("seconds left",), "mistakes": ("mistakes",), "hesitations": ("hesitations",),
    "timer_s": ("the clock",), "label": ("level number",), "shape": ("board shape", "the board's shape", "the board is the picture's"),
    "ending": ("ending",), "cursor": ("cursor",), "background": ("background",), "colour_names": ("named colours", "colours"),
    "colour_counts": ("blocks per colour",), "walls": ("walls", "board shape", "the board is the picture's"), "style": ("board",),
    "stuck_by": ("the block in the way", "stuck"), "blocks_by": ("the blocking move",), "music": ("music",),
    "original": ("the game's own look", "not taken stays the game's own"), "satisfying": ("satisfying finish",),
    "captions": ('asked: "', "quoted", "caption"), "caption_moments": ("caption",), "blocks_left": ("blocks left at the cut",),
}
SEQUENCE_ROWS = {"replay": "the replay", "end_card": "the end card", "result_screen": "the result screen", "result_first": "the win first"}


def coverage_rows(prompt: str, brief: dict, checks: list[dict]) -> list[dict]:
    """A13 (2026-10-19): every ask the tool parsed in the request has a row that measures it; one that has none is a
    'not measured' row naming the phrase (a gap of the tool, never silent). Info rows: the loop cannot act on them."""
    from . import audit
    from .imageplan import BOARD_ALL, LABEL_WORDS, NO_HUD as _NO_HUD, PART_WORDS, SAME_WORDS, STRONG_CUES, DEICTIC, _words, transforms_asked
    a = audit.asked(prompt)
    names = [str(c.get("check") or "").lower() for c in checks]
    asks: list[tuple[str, tuple]] = []
    for key, kws in COVERAGE.items():
        v = a.get(key)
        if v in (None, [], {}, False):
            continue
        asks.append((f"{key.replace('_', ' ')} {v}" if not isinstance(v, (list, dict)) else key.replace("_", " "), kws))
    for k, v in (a.get("sequence") or {}).items():
        if k in SEQUENCE_ROWS:
            asks.append((f"sequence: {k} {'yes' if v else 'no'}", (SEQUENCE_ROWS[k],)))
    text = _words(prompt)
    for t in transforms_asked(prompt):
        phrase = (f"{int(t.get('n') or 0):+d} colour(s) against the picture" if t["kind"] == "colours" else
                  "a colour becomes another" if t["kind"] == "recolour" else "the board mirrored" if t["kind"] == "mirror" else
                  ("half the blocks" if t.get("half") else f"{int(t.get('n') or 0):+d} block(s) against the picture") if t["kind"] == "blocks" else
                  f"{t['kind']} than the picture's board")
        asks.append((phrase, {"colours": ("more or fewer colours",), "recolour": ("a colour became another",), "mirror": ("the board mirrored",),
                              "harder": ("harder than the picture",), "easier": ("easier than the picture",),
                              "blocks": ("more or fewer blocks",)}[t["kind"]]))
    if BOARD_ALL.search(text) or re.search(r"\b(this|that|the) (exact |same )?(board|level)\b", text, re.I):
        asks.append(("the picture's board", ("the board is the picture's", "the board's shape", "the board's size")))
    from .imageplan import BOARD_PART, NEW_BOARD
    part_rows = {"shape": ("the board's shape", "the board is the picture's"), "size": ("the board's size", "the board is the picture's"),
                 "blocks": ("the board's blocks", "the board is the picture's"), "colours": ("the board's colours", "the board is the picture's"),
                 "pieces": ("the pieces", "the board is the picture's"), "packed": ("packed", "as crowded as the picture"), "symmetric": ("mirror-symmetric",)}
    for part, rx in BOARD_PART.items():
        if rx.search(text):
            asks.append((f"the picture's board: its {part}", part_rows[part]))
    if NEW_BOARD.search(text):
        asks.append(("a new board of the picture's type (not a copy)", ("the board's shape", "the board's size", "the board's blocks", "the board's colours", "nothing copied")))
    if LABEL_WORDS.search(text):
        asks.append(("the same level number", ("level number",)))  # imageaudit.label_row / audit's HUD level number
    if _NO_HUD.search(text) or re.search(r"\b(hud|timer|clock|badge)\b[^.;]{0,20}\b(shown|on screen|visible|kept)\b", text, re.I):
        asks.append(("the screen (HUD)", ("the screen", "hud")))
    if SAME_WORDS.search(text):
        asks.append(("the picture's own words", ("nothing copied", "quoted")))
    for part, row in (("background", "the background"), ("captions", "the caption colours"), ("blocks", "the block colours")):
        if PART_WORDS[part].search(text) and (STRONG_CUES.search(text) or DEICTIC.search(text) or re.search(r"\bits\b", text, re.I)):
            asks.append((f"the picture's {part}", (row, "not taken stays the game's own", "the game's own look")))
    missing = [phrase for phrase, kws in asks if not any(k in n for n in names for k in kws)]
    covered = [phrase for phrase, kws in asks if phrase not in missing]
    if missing:
        return [{"check": "Coverage: not measured", "status": "info", "from": "prompt", "where": None,
                 "detail": "NOT MEASURED (a gap of the tool, not of the creative): " + "; ".join(missing)
                           + (f". Measured: {'; '.join(covered)}" if covered else "")}]
    return [{"check": "Coverage: every ask has a measured row", "status": "info", "from": "prompt", "where": None,
             "detail": ("; ".join(covered) if covered else "the request states nothing the audit parses; the viewer's review and the image rows cover it")}]


def rows(prompt: str, brief: dict, record: dict, vdir: Path) -> list[dict]:
    """The image rows for a made version (see the module note)."""
    prov = brief.get("reference") or {}
    if prov.get("kind") != "image":
        return []
    rd, plan = prov.get("reader") or {}, prov.get("plan") or {}
    out = [_row("the role", None, f"the picture: {' and '.join(prov.get('roles') or []) or 'no role'}"
                                  + (f" ({'; '.join(prov.get('why') or [])})" if prov.get("why") else "")
                                  + (f"; the reading plan ({plan.get('source')}): {', '.join(plan.get('focus') or []) or 'nothing'}"
                                     if plan else "")
                                  + (f"; read by {rd.get('reader')} {rd.get('model')} in {rd.get('seconds')} s" if rd.get("reader") else "")
                                  + (f" (fell back: {rd['fell_back'][:80]})" if rd.get("fell_back") else "")),
           _row("what was taken", None, "taken: " + ("; ".join(prov.get("taken") or []) or "nothing") +
                " | not taken: " + ("; ".join(prov.get("not_taken") or []) or "nothing"))]
    if (prov.get("reading") or {}).get("error"):
        out.append(_row("not read", None, "the picture could not be read; the creative follows the words"))
        return out
    made = made_level(vdir / "level.json")
    if (prov.get("board") or {}).get("copied"):
        out += copied_board_rows(prompt, prov, vdir)  # B2, A6-A8 (2026-10-19): the board IS the picture's, with its changes
        lk = likeness_row(prov, vdir)
        if lk:
            out.append(lk)  # B10: the viewer model's eye on picture vs made
    else:
        out += board_rows(prov, made)
        from .imageplan import transforms_asked
        rel = next((t for t in transforms_asked(prompt) if t["kind"] == "colours"), None)
        bd = prov.get("board") or {}
        if rel and made and bd.get("seen", {}).get("colours"):
            pic_n, n = len(bd["seen"]["colours"]), int(rel["n"])
            target = max(2, min(7, pic_n + n))
            out.append(_row("more or fewer colours than the picture", len(made["colours"]) == target,
                            f"the picture's board has {pic_n} colours ({', '.join(bd['seen']['colours'])}); asked {'+' if n > 0 else ''}{n}; the made "
                            f"board (of the picture's type) has {len(made['colours'])} ({', '.join(B.COLOUR_WORDS.get(c, c) for c in made['colours'])})", "level"))
    nt = board_not_taken_row(brief, prov, made)
    if nt:
        out.append(nt)
    out += look_rows(prompt, brief, prov, vdir)
    for extra in (blocks_left_row(prompt, brief, record), fast_finish_row(prompt, brief, record), quoted_row(prompt, vdir),
                  play_fills_row(prov, record, vdir), stuck_visible_row(prompt, brief, record), question_row(prompt, brief, vdir),
                  real_choice_row(prompt, brief, record, vdir)):
        if extra:
            out.append(extra)
    out.append(screen_row(prompt, brief, prov, record))
    ec = end_card_row(vdir)
    if ec:
        out.append(ec)
    lab = label_row(brief, prov)
    if lab:
        out.append(lab)
    out.append(copied_row(prompt, brief, prov, vdir))
    c = counted_row(prov)
    if c:
        out.append(c)
    return out
