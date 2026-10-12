"""What an edit can point at, and exact edits that need no planner.

The inventory lists everything in a finished ad that a user may want to swap or rewrite: the
pictures (logo, the icon beside the hook, the end-card picture, the button, the end card's
background, the cursor), the sound, and every caption, each with a plain name, when it is on
screen and where. The planner gets it with an edit prompt, so "the coin pile" or "the clock
icon" is resolved against what the ad really holds; the UI shows it as "Things in this ad", with
Replace, Remove and text edits that change the brief in code (no model in the loop).
"""

from __future__ import annotations

import copy
from pathlib import Path

from . import brief as B

# Picture slots: the brief asset that fills each one (role, when) and its plain name.
PICTURES = {
    "logo": {"role": "logo", "when": "whole", "name": "the logo in a top corner"},
    "hook_icon": {"role": "sticker", "when": "hook", "name": "the icon beside the hook"},
    "end_art": {"role": "end_art", "when": "end_card", "name": "the picture on the end card"},
    "button": {"role": "button", "when": "end_card", "name": "the PLAY NOW button"},
    "end_background": {"role": "end_background", "when": "end_card", "name": "the end card's background"},
    "cursor": {"role": "cursor", "when": "whole", "name": "the tap cursor"},
}
DEFAULT_FILES = {"CoinPile.png": "a coin pile", "stopwatch.png": "a stopwatch", "StartBACKGROUND.png":
                 "the game's purple start background", "ContinueButtonEmpty.png": "the game's green button",
                 "builtin:hand": "a pointing hand"}
CAPTIONS = {"hook": ("concept.hook", "the hook (first words on screen)"),
            "cap_mistake": ("concept.mistake", "the caption on the mistake"),
            "cap_fix": ("concept.fix", "the caption on the fix"),
            "cap_hurry": ("concept.hurry", "the 'hurry' caption"),
            "cap_cascade": ("concept.cascade", "the caption on the fast finish"),
            "cap_result": ("concept.result", "the caption on the result screen"),
            "end_title": ("concept.end_title", "the end card's title"),
            "end_fact": ("concept.end_fact", "the end card's line under the title"),
            "end_cta": ("concept.cta", "the button's text")}
REMOVABLE = {"logo", "hook_icon", "end_art"}  # the button and the backgrounds always have something


def _file_of(ad: dict, slot: str):
    L, end = ad.get("layers", {}), ad.get("segments", {}).get("end", {})
    if slot == "logo":
        return (L.get("logo") or {}).get("image")
    if slot == "hook_icon":
        return (L.get("hook") or {}).get("icon")
    if slot == "end_art":
        return (L.get("end_art") or {}).get("image")
    if slot == "button":
        return (L.get("end_cta") or {}).get("image")
    if slot == "end_background":
        return end.get("background") or (f"gradient {' to '.join(end['gradient'])}" if end.get("gradient") else None)
    if slot == "cursor":
        c = L.get("cursor")
        return None if c is None else (c.get("image") or "tap ring")
    return None


def _describe(f) -> str:
    if f is None:
        return "none"
    name = Path(str(f)).name
    return DEFAULT_FILES.get(name, DEFAULT_FILES.get(str(f), name))


def inventory(ad: dict, compose: dict | None = None) -> list[dict]:
    """Every picture slot and caption of a finished ad: {id, kind, name, file, shows, when, box,
    can_remove}. when: [start s, end s] on screen; box: [x0, y0, x1, y1] in the 1080x1920 frame."""
    shown = (compose or {}).get("layers", {})
    lid_of = {"logo": "logo", "hook_icon": "hook", "end_art": "end_art", "button": "end_cta", "cursor": "cursor"}
    out = []
    for slot, info in PICTURES.items():
        f = _file_of(ad, slot)
        if f is None and slot not in ("logo", "hook_icon", "end_art"):
            continue
        if slot == "end_art" and f is None and "thumb" in ad.get("segments", {}).get("end", {}):
            continue  # a cliffhanger's end card shows the unsolved board there
        lay = shown.get(lid_of.get(slot, ""), {})
        when = [round(x / 30, 2) for x in lay["frames"]] if lay.get("frames") else None
        if slot == "logo" and shown.get("logo_end", {}).get("frames") and when:  # the gameplay and the end card
            when = [when[0], round(shown["logo_end"]["frames"][1] / 30, 2)]
        if slot == "end_background" and compose and "end" in compose.get("timeline", {}):
            when = [round(x / 30, 2) for x in compose["timeline"]["end"]["frames"]]
        if slot == "cursor" and compose and f is not None:  # on the gameplay parts only
            segs = [compose["timeline"][x]["frames"] for x in ad["layers"]["cursor"].get("segments", [])
                    if x in compose.get("timeline", {})]
            when = [round(min(a for a, _ in segs) / 30, 2), round(max(b for _, b in segs) / 30, 2)] if segs else None
        out.append({"id": slot, "kind": "picture", "name": info["name"], "file": f, "shows": _describe(f),
                    "when": when, "box": lay.get("box"), "can_remove": slot in REMOVABLE and f is not None})
    sound = bool(ad.get("audio", {}).get("events"))
    out.append({"id": "sound", "kind": "sound", "name": "the sound effects", "file": None,
                "shows": "on" if sound else "off", "when": None, "box": None, "can_remove": sound})
    # empty slots first-class too: the UI offers "Add" for them
    for x in out:
        x["empty"] = x["kind"] == "picture" and x["file"] is None
    for lid, (group, name) in CAPTIONS.items():
        lay = shown.get(lid)
        if lid not in ad.get("layers", {}) or not lay:
            continue
        out.append({"id": lid, "kind": "caption", "name": name, "group": group, "text": lay.get("text"),
                    "when": [round(x / 30, 2) for x in lay["frames"]], "box": lay.get("box"),
                    "can_remove": lid not in ("end_cta", "hook")})  # the hook is frame 0's text; the button needs one
    return out


def describe_for_planner(inv: list[dict]) -> str:
    """The inventory as lines for the planner's edit prompt."""
    lines = []
    for s in inv:
        when = f" ({s['when'][0]:g}-{s['when'][1]:g} s)" if s.get("when") else ""
        if s.get("empty"):
            role = PICTURES[s["id"]]
            lines.append(f"- picture {s['id']} = {s['name']}: none now (an upload adds it as an asset with role "
                         f"{role['role']!r}, when {role['when']!r})")
        elif s["kind"] == "caption":
            lines.append(f"- caption {s['id']} = {s['name']}{when}: {s['text']!r} (field {s['group']})")
        elif s["kind"] == "sound":
            lines.append(f"- sound effects: {s['shows']} (field audio)")
        else:
            role = PICTURES[s["id"]]
            lines.append(f"- picture {s['id']} = {s['name']}{when}: shows {s['shows']} (an upload replaces it as an "
                         f"asset with role {role['role']!r}, when {role['when']!r})")
    return "\n".join(lines)


PART_NAMES = {"teaser": "the result shown first", "intro": "a frozen first frame under the hook",
              "play": "the gameplay", "replay": "a slow-motion replay of the last moves",
              "result": "the game's result screen", "question": "the cliffhanger question on the frozen board",
              "end": "the end card"}


def outline(ad: dict, compose: dict | None = None) -> str:
    """The ad's parts in order, with their lengths, and the optional parts it does not have, for
    the planner (so "remove the replay" on an ad without one is answered, not guessed)."""
    tl = (compose or {}).get("timeline", {})
    parts = []
    for sid in ad.get("order", []):
        f = tl.get(sid, {}).get("frames")
        parts.append(f"{sid} = {PART_NAMES.get(sid, sid)}" + (f" ({(f[1] - f[0]) / 30:.1f} s)" if f else ""))
    short = {"replay": "slow-motion replay", "result": "result screen", "intro": "frozen intro"}
    missing = [short[x] for x in ("replay", "result", "intro") if x not in ad.get("order", [])
               and not (x == "result" and "question" in ad.get("order", []))]
    out = f"- the ad's parts, in order: {'; '.join(parts)}; {ad.get('length_s', 0):g} s in all"
    if missing:
        out += f"\n- this ad has no {', no '.join(missing)}"
    return out


# ---------- exact edits (no planner) ----------

def replace_picture(brief: dict, slot: str, file: str | None) -> tuple[dict, str]:
    """The brief with one picture slot set to an uploaded file (None removes it). Returns the
    brief and the prompt line that describes the edit."""
    if slot not in PICTURES:
        raise ValueError(f"no picture slot {slot!r}; the slots are {', '.join(PICTURES)}")
    if file is None and slot not in REMOVABLE:
        raise ValueError(f"{PICTURES[slot]['name']} cannot be removed (the ad needs one); replace it instead")
    b = copy.deepcopy(brief)
    info = PICTURES[slot]
    old = next((a for a in b["assets"] if B.asset_slot(a) == slot), None)
    b["assets"] = [a for a in b["assets"] if B.asset_slot(a) != slot]
    # A replacement takes the place of the old one (a logo stays in its corner).
    b["assets"].append({"file": file if file is not None else "builtin:none",
                        "role": old["role"] if old else info["role"], "when": old["when"] if old else info["when"],
                        "where": old["where"] if old else ("auto" if slot != "logo" else "top_left")})
    if slot == "cursor" and file is not None:
        b["visuals"]["cursor"] = "ring"  # the image replaces the ring
    b["changed"] = ["assets"]
    words = f"Replace {info['name']} with {file}" if file else f"Remove {info['name']}"
    return b, words + "; keep everything else exactly the same."


def set_caption(brief: dict, lid: str, text: str) -> tuple[dict, str]:
    """The brief with one caption rewritten ("" removes it, except the button's text)."""
    if lid not in CAPTIONS:
        raise ValueError(f"no caption {lid!r}")
    group, name = CAPTIONS[lid]
    if lid == "end_cta" and not text.strip():
        raise ValueError("the button needs a text")
    b = copy.deepcopy(brief)
    b["concept"][group.split(".", 1)[1]] = text.strip()
    b["changed"] = [group]
    return b, (f"Change {name} to {text.strip()!r}" if text.strip() else f"Remove {name}") + \
        "; keep everything else exactly the same."


def set_sound(brief: dict, on: bool) -> tuple[dict, str]:
    b = copy.deepcopy(brief)
    b["audio"]["sfx"] = bool(on)
    b["changed"] = ["audio"]
    return b, ("Turn the sound effects on" if on else "Turn the sound effects off") + \
        "; keep everything else exactly the same."


def direct_edit(brief: dict, op: dict, uploads: dict, sprites: set[str]) -> tuple[dict, str]:
    """An exact edit from the UI: {"picture": slot, "file": name | None} or {"caption": layer,
    "text": str} or {"sound": bool}. The brief is checked like any other, and `changed` names the
    one group the edit touches."""
    if "picture" in op:
        f = op.get("file")
        if f is not None and f not in uploads and f not in sprites:
            raise ValueError(f"{f!r} is not an uploaded file")
        b, words = replace_picture(brief, op["picture"], f)
    elif "caption" in op:
        b, words = set_caption(brief, op["caption"], str(op.get("text", "")))
    elif "sound" in op:
        b, words = set_sound(brief, bool(op["sound"]))
    else:
        raise ValueError("an exact edit names a picture, a caption or the sound")
    changed = b["changed"]
    b = B.check(b, uploads, sprites)
    b["changed"] = changed
    for row in b["controls"]:
        row["asked"], row["engine"] = None, []
    return b, words
