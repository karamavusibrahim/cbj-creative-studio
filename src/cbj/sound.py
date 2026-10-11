"""Sound effects synthesized in code, and the ad's sound track.

The Unity project ships no audio, and CBJ's ads use short tactile sounds rather than music, so
every effect is made here from oscillators, noise and envelopes. That keeps the track
deterministic (the same ad.json gives the same samples) and free of licensing questions.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

RATE = 48_000


def _t(seconds: float) -> np.ndarray:
    return np.arange(int(round(seconds * RATE))) / RATE


def _env(n: int, attack_s: float, decay_s: float) -> np.ndarray:
    """Linear attack, then exponential decay to about -60 dB over decay_s."""
    a = max(1, int(attack_s * RATE))
    t = np.arange(n) / RATE
    env = np.exp(-6.9 * np.clip(t - attack_s, 0, None) / max(decay_s, 1e-4))
    env[:a] *= np.linspace(0, 1, a, endpoint=False) if a < n else 1
    return env


def _noise(n: int, seed: int) -> np.ndarray:
    return np.random.default_rng(seed).uniform(-1, 1, n)


def click(gain: float = 0.5) -> np.ndarray:
    """A short finger tap: filtered noise burst plus a high blip."""
    n = int(0.03 * RATE)
    t = np.arange(n) / RATE
    noise = np.convolve(_noise(n, 1), np.ones(6) / 6, mode="same")
    blip = np.sin(2 * np.pi * 2400 * t)
    return gain * (0.6 * noise + 0.4 * blip) * _env(n, 0.001, 0.025)


def pop(pitch: float = 1.0, gain: float = 0.6) -> np.ndarray:
    """A block leaving: a quick downward pitch sweep with a soft body."""
    t = _t(0.16)
    f0, f1 = 900 * pitch, 380 * pitch
    freq = f1 + (f0 - f1) * np.exp(-t / 0.03)
    phase = 2 * np.pi * np.cumsum(freq) / RATE
    body = np.sin(phase) + 0.3 * np.sin(2 * phase)
    return gain * body * _env(len(t), 0.002, 0.14)


def tick(gain: float = 0.35) -> np.ndarray:
    """A clock tick: a short woodblock-like tone."""
    t = _t(0.06)
    tone = np.sin(2 * np.pi * 1700 * t) + 0.5 * np.sin(2 * np.pi * 3400 * t)
    return gain * tone * _env(len(t), 0.001, 0.05)


def chord(notes_hz=(523.25, 659.25, 783.99, 1046.5), spread_s: float = 0.06, gain: float = 0.45) -> np.ndarray:
    """A bright success arpeggio (C major by default), each note a bell-like tone."""
    length = spread_s * len(notes_hz) + 0.9
    out = np.zeros(int(length * RATE))
    for k, f in enumerate(notes_hz):
        t = _t(0.9)
        note = (np.sin(2 * np.pi * f * t) + 0.25 * np.sin(2 * np.pi * 2 * f * t)) * _env(len(t), 0.004, 0.8)
        i = int(k * spread_s * RATE)
        out[i:i + len(note)] += note
    return gain * out / len(notes_hz) * 2


def womp(gain: float = 0.5) -> np.ndarray:
    """A soft fail sound: two falling tones."""
    out = []
    for f0, f1, d in ((392, 370, 0.22), (330, 220, 0.5)):
        t = _t(d)
        freq = f0 + (f1 - f0) * t / d
        phase = 2 * np.pi * np.cumsum(freq) / RATE
        out.append((np.sin(phase) + 0.2 * np.sin(3 * phase)) * _env(len(t), 0.01, d))
    return gain * np.concatenate(out)


def whoosh(seconds: float = 0.45, gain: float = 0.35) -> np.ndarray:
    """Air rushing past: noise through a sweeping one-pole low-pass, rising then falling."""
    n = int(seconds * RATE)
    x = _noise(n, 7)
    t = np.arange(n) / n
    cutoff = 300 + 5000 * np.sin(np.pi * t) ** 2
    alpha = 1 - np.exp(-2 * np.pi * cutoff / RATE)
    y = np.zeros(n)
    acc = 0.0
    for i in range(n):
        acc += alpha[i] * (x[i] - acc)
        y[i] = acc
    return gain * y * np.sin(np.pi * t) ** 1.5 / max(1e-9, np.abs(y).max()) * 2


def bump(gain: float = 0.4) -> np.ndarray:
    """A block pushed into another: a low thud with a little grit."""
    t = _t(0.09)
    thud = np.sin(2 * np.pi * 110 * t) * _env(len(t), 0.002, 0.08)
    grit = np.zeros_like(thud)
    k = int(0.008 * RATE)
    grit[:k] = _noise(k, 3) * np.linspace(1, 0, k)
    return gain * (thud + 0.35 * grit)


EFFECTS = {"click": click, "pop": pop, "tick": tick, "chord": chord, "womp": womp, "whoosh": whoosh,
           "bump": bump}


def render_track(events: list[dict], duration_s: float) -> np.ndarray:
    """Mix events [{"sound": name, "t": seconds, "gain": g, "pitch": p}] into a mono track,
    limited so the peak stays below -1 dBFS."""
    track = np.zeros(int(round(duration_s * RATE)) + 1)
    for e in events:
        fn = EFFECTS.get(e["sound"])
        if fn is None:
            raise ValueError(f"unknown sound {e['sound']!r}; known: {', '.join(sorted(EFFECTS))}")
        kw = {k: e[k] for k in ("gain", "pitch") if k in e and k in fn.__code__.co_varnames}
        s = fn(**kw)
        i = int(round(e["t"] * RATE))
        if i >= len(track):
            continue
        s = s[: len(track) - i]
        track[i:i + len(s)] += s
    peak = np.abs(track).max()
    limit = 10 ** (-1 / 20)  # -1 dBFS
    if peak > limit:
        track *= limit / peak
    return track


def write_wav(track: np.ndarray, path: str | Path) -> None:
    """16-bit stereo WAV (the mono track on both channels)."""
    pcm = np.clip(np.round(track * 32767), -32768, 32767).astype("<i2")
    stereo = np.repeat(pcm[:, None], 2, axis=1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(stereo.tobytes())
