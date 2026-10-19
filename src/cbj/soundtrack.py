"""Soundtrack (2026-10-18, optional): a music bed written from the creative's own concept, and an optional
spoken hook, delivered as an ordinary uploaded sound file the workflows already know how to use.

Why. The ads have sound effects and, when the user attaches one, a music file. Nothing writes music for a
concept. NVIDIA build has no music or sound-generation model (its audio functions are text-to-speech:
Magpie, Chatterbox; Fugatto was never released), so this does what the aiforgift reels do: the bed is
synthesised procedurally, here from the facts of the finished version, and the voice is NVIDIA Magpie TTS
over NVCF gRPC (the `voice` extra: nvidia-riva-client).

What the bed follows, read from the version's parts manifest (parts.json) and brief, never guessed:
  * the look (theme)           -> the mode and root (bright major for game/candy/pastel, minor for neon/dark);
  * the tempo and curve        -> the pulse (84 / 104 / 124 bpm, ramping when the play speeds up or slows);
  * the parts                  -> a stinger under the hook, the pulse only while the play runs, a pad under
                                  the end card, the whole thing exactly the ad's length;
  * every block exit (moments) -> a pluck one scale step higher each time, at the exit's second;
  * the ending                 -> a resolve chord at a win, a riser and hurry ticks into a near-fail, an
                                  unresolved chord held for a cliffhanger, a low drop at a time-out;
  * the clock                  -> ticks when it shows five seconds or less.

Zero effect: this module writes a WAV into studio/uploads/ (plus a sidecar JSON in studio/_soundtracks/)
and returns its name. Putting it in the ad is the existing controlled edit {"music": name} (a new version
with the edit report) or a mention in a new prompt. No workflow, planner or compositor imports this module.

The voice narrates the creative's own captions as they appear on screen (the hook, the play captions, the end
card's fact and call to action; `narration="hook"` for the hook alone; a typed line replaces the hook's words), so what
is said is always what the creative shows, at the second it shows it. English only here (Magpie's voices on build are
EN-US plus a few European names). It is mixed into the same file, ducking the bed, so the compositor's one music
channel carries both.

API: POST /api/soundtrack {creative_id, version?, voice?, voice_name?, line?}; CLI `cbj soundtrack ID [--base N] [--voice]`.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import numpy as np

from . import brief as B
from . import studio

SR = 48_000
BPM = {"calm": 84, "normal": 104, "fast": 124}
CURVE_RATIO = {"even": 1.0, "speeds_up": 1.25, "slows_down": 0.85}
MAJOR_PENT = (0, 2, 4, 7, 9)
MINOR_PENT = (0, 3, 5, 7, 10)
# theme -> (mood word, mode, root Hz, pad gain)
THEME = {"game": ("bright", "major", 261.63, 0.11), "candy": ("playful", "major", 293.66, 0.12),
         "pastel": ("soft", "major", 349.23, 0.09), "neon": ("electric", "minor", 220.00, 0.12),
         "dark": ("tense", "minor", 164.81, 0.10), "custom": ("bright", "major", 261.63, 0.11)}
DEFAULT_VOICE = "Magpie-Multilingual.EN-US.Mia"
VOICE_BY_TEMPO = {"calm": "Magpie-Multilingual.EN-US.Mia.Calm", "normal": "Magpie-Multilingual.EN-US.Mia",
                  "fast": "Magpie-Multilingual.EN-US.Jason.Happy"}
GRPC = "grpc.nvcf.nvidia.com:443"
FN_MAGPIE = "877104f7-e885-42b9-8de8-f6e4c6303969"
MAX_LINE_WORDS = 14


# ── synthesis helpers (numpy, additive) ─────────────────────────────────────────────────────────

def _env(n: int, attack_s: float, decay_s: float) -> np.ndarray:
    t = np.arange(n) / SR
    a = np.minimum(1.0, t / max(attack_s, 1e-4))
    d = np.exp(-np.maximum(0.0, t - attack_s) / max(decay_s, 1e-4))
    return a * d


def _add(buf: np.ndarray, at_s: float, x: np.ndarray) -> None:
    i = int(round(at_s * SR))
    if i >= len(buf) or i + len(x) <= 0:
        return
    if i < 0:
        x, i = x[-i:], 0
    n = min(len(x), len(buf) - i)
    buf[i:i + n] += x[:n]


def tone(buf, at_s, freq, dur_s, gain, decay_s=0.4, attack_s=0.005, harmonics=(1.0, 0.35, 0.12), glide=0.0):
    n = int(dur_s * SR)
    t = np.arange(n) / SR
    f = freq * (1 + glide * t)
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = sum(h * np.sin((k + 1) * ph) for k, h in enumerate(harmonics))
    _add(buf, at_s, x * gain * _env(n, attack_s, decay_s))


def noise(buf, at_s, dur_s, lo, hi, gain, attack_s=0.01, decay_s=0.2, seed=0):
    """Band-limited noise by FFT masking: the ticks, the riser's air."""
    n = int(dur_s * SR)
    if n < 8:
        return
    rng = np.random.default_rng(seed)
    spec = np.fft.rfft(rng.uniform(-1, 1, n))
    f = np.fft.rfftfreq(n, 1 / SR)
    spec[(f < lo) | (f > hi)] = 0
    x = np.fft.irfft(spec, n)
    x /= max(1e-9, np.max(np.abs(x)))
    _add(buf, at_s, x * gain * _env(n, attack_s, decay_s))


def pad(buf, from_s, to_s, freqs, gain, fade_s=1.0):
    n = int((to_s - from_s) * SR)
    if n <= 0:
        return
    t = np.arange(n) / SR
    x = np.zeros(n)
    for k, f in enumerate(freqs):
        lfo = 1 + 0.08 * np.sin(2 * np.pi * (0.11 + 0.03 * k) * t + k)
        x += np.sin(2 * np.pi * f * t + k) * lfo / len(freqs)
    fi = np.minimum(1.0, t / fade_s)
    fo = np.minimum(1.0, (t[-1] - t) / fade_s) if n > 1 else 1.0
    _add(buf, from_s, x * gain * fi * fo)


def beats(from_s: float, to_s: float, bpm: float, ratio: float) -> list[float]:
    """Beat times across [from_s, to_s] with the tempo moving linearly from bpm to bpm*ratio."""
    out, t = [], from_s
    span = max(1e-6, to_s - from_s)
    while t < to_s:
        out.append(round(t, 4))
        frac = (t - from_s) / span
        t += 60.0 / (bpm * (1 + (ratio - 1) * frac))
    return out


# ── the concept ─────────────────────────────────────────────────────────────────────────────────

def _part(parts: dict, pid: str) -> dict | None:
    return next((p for p in parts.get("parts") or [] if p.get("id") == pid), None)


def concept(brief: dict, parts: dict) -> dict:
    """Everything the bed will do, as data: read from the brief and the parts manifest."""
    theme = (brief.get("visuals") or {}).get("theme") or "game"
    mood, mode, root, pad_gain = THEME.get(theme, THEME["game"])
    pacing = brief.get("pacing") or {}
    tempo = pacing.get("tempo") or "normal"
    curve = pacing.get("curve") or "even"
    ending = (parts.get("gameplay") or {}).get("ending") or (brief.get("gameplay") or {}).get("ending") or "near_fail"
    duration = float(parts.get("duration_s") or pacing.get("length_s") or 30.0)
    play = _part(parts, "play") or {"from_s": 0.5, "to_s": max(1.0, duration - 8.0)}
    end = _part(parts, "end")
    hook = next((l for l in parts.get("layers") or [] if l.get("id") == "hook"), None)
    exits = [m for m in parts.get("moments") or [] if m.get("kind") == "exit"]
    hurry = [c["at_s"] for c in parts.get("clock") or [] if c.get("clock_s") is not None and c["clock_s"] <= 5]
    scale = MAJOR_PENT if mode == "major" else MINOR_PENT
    after = [p for p in parts.get("parts") or [] if p.get("id") in ("replay", "result", "result_hold") and p.get("to_s")]
    return {"theme": theme, "mood": mood, "mode": mode, "root_hz": root, "pad_gain": pad_gain, "scale": list(scale),
            "tempo": tempo, "bpm": BPM.get(tempo, 104), "curve": curve, "bpm_ratio": CURVE_RATIO.get(curve, 1.0),
            "ending": ending, "duration_s": duration, "play": {"from_s": float(play["from_s"]), "to_s": float(play["to_s"])},
            "after": {"from_s": float(min(p["from_s"] for p in after)), "to_s": float(max(p["to_s"] for p in after))} if after else None,
            "end_from_s": float(end["from_s"]) if end else None,
            "hook": {"text": (hook or {}).get("text") or "", "from_s": float((hook or {}).get("from_s") or 0.0),
                     "to_s": float((hook or {}).get("to_s") or 2.0)},
            "exits": [{"at_s": float(m.get("exit_s") or m.get("at_s")), "block": m.get("block")} for m in exits],
            "hurry_ticks": [float(x) for x in hurry], "language": brief.get("language") or "en"}


def describe(c: dict, voice: dict | None, bed: bool = True, base: str | None = None) -> str:
    if not bed:
        head = f"The creative's own music ({base}) kept" if base else "No music bed"
        return head + ("; " + _voice_words(voice) if voice else ".")
    bpm = f"{c['bpm']} bpm" + (f" ({'speeding up' if c['bpm_ratio'] > 1 else 'slowing'} to {round(c['bpm'] * c['bpm_ratio'])})"
                               if c["bpm_ratio"] != 1 else "")
    endings = {"win": "a resolve chord at the win", "near_fail": "a riser and hurry ticks into the near-fail",
               "cliffhanger": "an unresolved chord held where the play stops", "time_out": "a low drop at the time-out"}
    bits = [f"a stinger under the hook", f"a pulse through the play at {bpm}"]
    if c["exits"]:
        bits.append(f"a pluck one step higher as each block leaves ({len(c['exits'])})")
    bits.append(endings.get(c["ending"], ""))
    if c["end_from_s"] is not None:
        bits.append("a soft pad under the end card")
    s = f"{c['mood'].capitalize()} {c['mode']} pentatonic: " + ", ".join(b for b in bits if b) + f". {c['duration_s']:.0f} s, synthesised (no licensed music)."
    if voice:
        s += " " + _voice_words(voice)
    return s


def _voice_words(voice: dict) -> str:
    who = voice["voice"].split(".", 1)[-1]
    lines = voice.get("lines") or []
    if len(lines) > 1:
        return f"{who} narrates the creative's own captions as they appear: " + "; ".join(f"“{l['text']}” at {l['at_s']:.0f} s" for l in lines) + "."
    return f"The hook is spoken by {who}: “{voice['text']}”."


# ── the bed ─────────────────────────────────────────────────────────────────────────────────────

def _note(c: dict, degree: int, octave: int = 0) -> float:
    scale = c["scale"]
    return c["root_hz"] * 2 ** ((scale[degree % len(scale)] + 12 * (degree // len(scale) + octave)) / 12)


def render_bed(c: dict) -> np.ndarray:
    d = c["duration_s"]
    buf = np.zeros(int(d * SR) + 1)
    root = c["root_hz"]
    third = root * 2 ** ((4 if c["mode"] == "major" else 3) / 12)
    fifth = root * 2 ** (7 / 12)
    # the pad: a soft triad the whole way, an octave down, breathing
    pad(buf, 0.0, d, (root / 2, fifth / 2, third, root), c["pad_gain"], fade_s=1.0)
    # the hook stinger: root then fifth, quick
    tone(buf, 0.02, root, 0.6, 0.20, decay_s=0.25)
    tone(buf, 0.14, fifth, 0.9, 0.16, decay_s=0.35)
    # the pulse through the play
    p = c["play"]
    bt = beats(p["from_s"], p["to_s"], c["bpm"], c["bpm_ratio"])
    thump_every = 2 if c["tempo"] == "calm" else 1
    for i, t in enumerate(bt):
        if i % thump_every == 0:
            tone(buf, t, 58.0, 0.16, 0.22, decay_s=0.07, harmonics=(1.0,), glide=-1.8)
        if c["tempo"] != "calm" and i % 2 == 1:
            noise(buf, t, 0.03, 5500, 9500, 0.05, attack_s=0.002, decay_s=0.012, seed=i)
    # the replay and the result: the same pulse at half level, so the tail is not the pad alone
    if c.get("after"):
        a = c["after"]
        for i, t in enumerate(beats(a["from_s"] + 0.4, a["to_s"], c["bpm"] * c["bpm_ratio"] * 0.5, 1.0)):
            tone(buf, t, 58.0, 0.16, 0.11, decay_s=0.07, harmonics=(1.0,), glide=-1.8)
    # a pluck one step higher for every block that leaves
    for i, e in enumerate(c["exits"]):
        tone(buf, e["at_s"], _note(c, i), 0.7, 0.20, decay_s=0.30, harmonics=(1.0, 0.5, 0.2, 0.08))
    # hurry ticks when the clock shows five seconds or less
    for t in c["hurry_ticks"]:
        tone(buf, t, 1046.5, 0.08, 0.10, decay_s=0.03, harmonics=(1.0, 0.3))
    # the ending at the end of the play
    end_s = p["to_s"]
    if c["ending"] == "win":
        for k, f in enumerate((root, third, fifth, root * 2)):
            tone(buf, end_s + 0.03 * k, f, 1.6, 0.14, decay_s=0.7)
    elif c["ending"] == "near_fail":
        noise(buf, end_s - 3.0, 3.2, 300, 4000, 0.12, attack_s=2.6, decay_s=0.25, seed=7)
        tone(buf, end_s - 3.0, root, 3.0, 0.07, decay_s=4.0, attack_s=2.5, glide=0.33)
        for k, f in enumerate((root, fifth, root * 2)):
            tone(buf, end_s + 0.05 + 0.03 * k, f, 1.4, 0.13, decay_s=0.6)
    elif c["ending"] == "cliffhanger":
        sus4 = root * 2 ** (5 / 12)
        pad(buf, end_s, min(d, end_s + 4.0), (root, sus4, fifth), 0.16, fade_s=0.6)
    elif c["ending"] == "time_out":
        tone(buf, end_s, root / 2, 1.8, 0.18, decay_s=0.9, glide=-0.12)
    # the end card: a soft swell
    if c["end_from_s"] is not None:
        pad(buf, c["end_from_s"], d, (root, third, fifth, root * 2), 0.06, fade_s=0.8)
    peak = float(np.max(np.abs(buf))) or 1.0
    return buf / peak * 0.85


# ── the voice (NVIDIA Magpie over NVCF) ─────────────────────────────────────────────────────────

def voice_available() -> dict:
    try:
        import riva.client  # noqa: F401
        have = True
    except ImportError:
        have = False
    return {"client": have, "key": bool(os.environ.get("NVIDIA_API_KEY"))}


def clean_line(text: str) -> str:
    t = re.sub(r"\s+", " ", (text or "")).strip().strip("“”\"'")
    words = t.split(" ")
    return " ".join(words[:MAX_LINE_WORDS])


_SERVICE: dict = {}


def _service(key: str):
    """One gRPC channel per process (a new Auth per call is a new TLS handshake, far slower than the synthesis)."""
    import riva.client
    if _SERVICE.get("key") != key:
        auth = riva.client.Auth(use_ssl=True, uri=GRPC, metadata_args=[["function-id", FN_MAGPIE], ["authorization", f"Bearer {key}"]])
        _SERVICE.update(key=key, svc=riva.client.SpeechSynthesisService(auth))
    return _SERVICE["svc"]


def synthesize(text: str, voice: str, key: str) -> np.ndarray:
    """Magpie TTS -> mono float at SR."""
    import riva.client
    r = _service(key).synthesize(text=text, voice_name=voice, language_code="en-US", encoding=riva.client.AudioEncoding.LINEAR_PCM,
                                 sample_rate_hz=SR)
    return np.frombuffer(r.audio, dtype="<i2").astype(np.float64) / 32768.0


TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})\b")
NARRATED = ("hook", "cap_mistake", "cap_fix", "cap_hurry", "cap_cascade", "cap_result", "end_fact", "end_cta")
MAX_LINES = 5


def speakable(text: str) -> str:
    """A caption as words to say: 00:03 -> '3 seconds', shouting capitals lowered, at most MAX_LINE_WORDS words."""
    t = clean_line(text)

    def tm(m):
        mins, secs = int(m.group(1)), int(m.group(2))
        parts = ([f"{mins} minute" + ("s" if mins != 1 else "")] if mins else []) + ([f"{secs} second" + ("s" if secs != 1 else "")] if secs or not mins else [])
        return " ".join(parts)
    t = TIME_RE.sub(tm, t)
    if t.isupper() and len(t) > 3:
        t = t.capitalize()
    return t


def narration_lines(c: dict, parts: dict, narration: str, line: str | None) -> list[dict]:
    """What to say and when: the creative's own captions in the order they appear (narration='captions'), or the hook
    alone (narration='hook'); `line` replaces the hook's words. Lines never overlap: a line waits for the one before."""
    layers = [l for l in parts.get("layers") or [] if l.get("kind") == "caption" and (l.get("text") or "").strip() and l.get("from_s") is not None]
    if not layers and c["hook"]["text"]:
        layers = [{"id": "hook", "text": c["hook"]["text"], "from_s": c["hook"]["from_s"], "to_s": c["hook"]["to_s"]}]
    wanted = ("hook",) if narration == "hook" else NARRATED
    out = []
    for l in sorted(layers, key=lambda x: (x["from_s"], x["id"] != "hook")):
        if l["id"] not in wanted or len(out) >= MAX_LINES:
            continue
        text = speakable(line) if l["id"] == "hook" and line else speakable(l["text"])
        if not text:
            continue
        out.append({"layer": l["id"], "text": text, "from_s": float(l["from_s"]), "to_s": float(l.get("to_s") or c["duration_s"])})
    if narration == "hook" and not out and line:
        out = [{"layer": "hook", "text": speakable(line), "from_s": c["hook"]["from_s"], "to_s": c["hook"]["to_s"]}]
    return out


def place(lines: list[dict], audio: list[np.ndarray], duration_s: float) -> list[dict]:
    """Start times: 0.15 s after the caption appears, after the previous line has ended; a line with no room before
    its caption leaves (or the ad ends) is dropped."""
    placed, prev_end = [], -1.0
    for l, x in zip(lines, audio):
        secs = len(x) / SR
        at = max(l["from_s"] + 0.15, prev_end + 0.3)
        if at + secs > duration_s - 0.2 or at > l["to_s"] - 0.3:
            continue
        placed.append({**l, "at_s": round(at, 2), "seconds": round(secs, 2), "audio": x})
        prev_end = at + secs
    return placed


def mix_voice(bed: np.ndarray, voice: np.ndarray, at_s: float) -> np.ndarray:
    """The voice over the bed, the bed ducked to 40 % under it with 120 ms ramps; the voice peaks at 0.95."""
    out = bed.copy()
    i0 = max(0, int(at_s * SR))
    i1 = min(len(out), i0 + len(voice))
    if i1 <= i0:
        return out
    ramp = int(0.12 * SR)
    duck = np.ones(len(out))
    duck[i0:i1] = 0.4
    a, b = max(0, i0 - ramp), min(len(out), i1 + ramp)
    duck[a:i0] = np.linspace(1.0, 0.4, i0 - a)
    duck[i1:b] = np.linspace(0.4, 1.0, b - i1)
    out *= duck
    v = voice[: i1 - i0] / (float(np.max(np.abs(voice))) or 1.0) * 0.95
    out[i0:i1] += v
    peak = float(np.max(np.abs(out))) or 1.0
    return out / max(1.0, peak / 0.98)


# ── the lifecycle ───────────────────────────────────────────────────────────────────────────────

def folder() -> Path:
    return studio.STUDIO / "_soundtracks"


def write_wav(path: Path, x: np.ndarray) -> None:
    import wave
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def load_audio(path: Path, seconds: float) -> np.ndarray:
    """An uploaded sound file as mono float at SR, exactly `seconds` long (trimmed or padded with silence)."""
    import shutil
    import subprocess
    r = subprocess.run([shutil.which("ffmpeg") or "ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                       capture_output=True)
    if r.returncode != 0:
        raise ValueError(f"the music {path.name} could not be read: {r.stderr.decode()[:200]}")
    x = np.frombuffer(r.stdout, dtype="<f4").astype(np.float64)
    n = int(seconds * SR) + 1
    return x[:n] if len(x) >= n else np.concatenate([x, np.zeros(n - len(x))])


def make(creative_id: str, version: int | None = None, voice: bool = False, voice_name: str | None = None,
         line: str | None = None, log=None, bed: bool = True, narration: str = "captions") -> dict:
    """The soundtrack for a version: a WAV in studio/uploads/, a sidecar in studio/_soundtracks/, the concept.
    `bed=False` keeps the creative's own music (when it has one) or leaves silence under the voice."""
    if not bed and not voice:
        raise ValueError("nothing to make: ask for the bed, the voice, or both")
    v = studio.parent(creative_id, version)
    if v is None:
        raise ValueError(f"no creative {creative_id}")
    parts = studio.parts(creative_id, v["n"]) or {}
    t0 = time.time()
    c = concept(v["brief"], parts)
    own = (v["brief"].get("audio") or {}).get("music")
    base = None
    if bed:
        if log:
            log(f"writing a {c['mood']} {c['mode']} bed, {c['duration_s']:.0f} s...")
        bed_x = render_bed(c)
    elif own and own in studio.uploads():
        base = own
        bed_x = load_audio(studio.uploads()[own], c["duration_s"])
        if log:
            log(f"keeping the creative's own music ({own}) under the voice")
    else:
        bed_x = np.zeros(int(c["duration_s"] * SR) + 1)
    spoken, skipped = None, None
    if voice:
        lines = narration_lines(c, parts, narration if narration in ("hook", "captions") else "captions", line)
        avail = voice_available()
        if not lines:
            skipped = "the version has no caption to speak; type a line"
        elif c["language"] != "en" and not line:
            skipped = f"Magpie's voices here are English; the creative's captions are '{c['language']}' (type an English line to speak)"
        elif not avail["client"]:
            skipped = "the voice extra is not installed (uv sync --extra voice)"
        elif not avail["key"]:
            skipped = "NVIDIA_API_KEY is not set"
        else:
            name = voice_name or VOICE_BY_TEMPO.get(c["tempo"], DEFAULT_VOICE)
            if log:
                log(f"Magpie ({name.split('.', 1)[-1]}) says {len(lines)} line(s): " + " / ".join(l["text"] for l in lines))
            audio, failure = [], None
            for l in lines:
                for attempt in (1, 2):  # the service is remote: one retry, then the voice is skipped, never the job failed
                    try:
                        audio.append(synthesize(l["text"], name, os.environ["NVIDIA_API_KEY"]))
                        failure = None
                        break
                    except Exception as e:  # noqa: BLE001 - any transport error (DNS, TLS, gRPC status) is a skip reason
                        failure = e
                        time.sleep(1.5)
                if failure is not None:
                    break
            if failure is not None:
                detail = getattr(failure, "details", None)
                detail = detail() if callable(detail) else str(failure)
                detail = re.sub(r"\s+", " ", str(detail)).strip()[:160]
                skipped = f"the voice service did not answer ({detail}); the soundtrack is kept without the voice"
                if log:
                    log(f"voice skipped: {skipped}")
                placed = []
            else:
                placed = place(lines, audio, c["duration_s"])
            if placed:
                for l in placed:
                    bed_x = mix_voice(bed_x, l["audio"], l["at_s"])
                spoken = {"text": " / ".join(l["text"] for l in placed), "voice": name, "at_s": placed[0]["at_s"],
                          "seconds": round(sum(l["seconds"] for l in placed), 2), "model": "nvidia/magpie-tts-multilingual",
                          "narration": narration, "lines": [{k: l[k] for k in ("layer", "text", "at_s", "seconds")} for l in placed]}
            elif skipped is None:
                skipped = "no caption leaves room for a spoken line"
    short = re.sub(r"[^a-z0-9]+", "", creative_id.split("-", 2)[-1].lower())[:12] or "ad"
    if not bed and not spoken:
        raise ValueError("no voice could be made (" + (skipped or "unknown reason") + ") and no bed was asked for")
    stem = f"soundtrack-{short}-v{v['n']}" + ("" if bed else "-nobed") + ("-voice" if spoken else "")
    ups = studio.STUDIO / "uploads"
    ups.mkdir(parents=True, exist_ok=True)
    path = ups / f"{stem}.wav"
    write_wav(path, bed_x)
    result = {"file": path.name, "path": f"uploads/{path.name}", "creative_id": creative_id, "version": v["n"],
              "seconds": round(c["duration_s"], 2), "concept": c, "voice": spoken, "voice_skipped": skipped, "bed": bed, "base_music": base,
              "description": describe(c, spoken, bed, base), "made": time.strftime("%Y-%m-%d %H:%M:%S"), "took_s": round(time.time() - t0, 1)}
    folder().mkdir(parents=True, exist_ok=True)
    (folder() / f"{stem}.json").write_text(json.dumps(result, indent=1, ensure_ascii=False))
    return result


def add_audio(log, v: dict, audio: dict) -> dict:
    """The make job's optional last step: the soundtrack for the version just made, then the existing music edit,
    so the creative comes out with audio in one job. Returns the new version with `audio_added`."""
    from .workflows import edit as edit_wf  # lazy: the edit workflow is called, never changed
    want_voice, want_bed = bool(audio.get("voice")), bool(audio.get("bed", True))
    if not (want_voice or want_bed):
        return v
    log.begin("audio", "the optional audio: " + (" and ".join(x for x, on in (("a soundtrack from the concept", want_bed), ("the hook spoken", want_voice)) if on)) + "...")
    r = make(v["id"], v["n"], voice=want_voice, voice_name=audio.get("voice_name"), line=audio.get("line"), log=log, bed=want_bed,
             narration=audio.get("narration") or "captions")
    if r.get("voice_skipped"):
        log(f"voice skipped: {r['voice_skipped']}")
    log(f"{r['file']}: {r['description']}")
    nv = edit_wf.direct(log, v["id"], v["n"], {"music": r["file"]}, draft=False)
    nv["audio_added"] = {"file": r["file"], "description": r["description"], "voice": r["voice"], "voice_skipped": r["voice_skipped"],
                         "bed": r["bed"], "from_version": v["n"]}
    return nv


def text(r: dict) -> str:
    lines = [f"Soundtrack: studio/{r['path']} ({r['seconds']} s)", r["description"]]
    if r.get("voice_skipped"):
        lines.append(f"Voice skipped: {r['voice_skipped']}")
    lines.append(f"Use it: the music edit {{\"music\": \"{r['file']}\"}} on {r['creative_id']} v{r['version']}, or mention {r['file']} in a prompt.")
    return "\n".join(lines)
