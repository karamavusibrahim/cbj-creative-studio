"""The optional soundtrack (soundtrack.py): the concept read from the brief and the parts manifest, the bed's
length and level, the file landing in uploads, the voice gate, and the text. No network: the TTS is faked."""
import json
import wave

import numpy as np
import pytest

from cbj import brief as B
from cbj import soundtrack, studio


def parts(ending="near_fail", duration=30.0, exits=3, hurry=True):
    play_to = duration - 9.0
    return {"creative": "c", "version": 1, "fps": 30, "duration_s": duration,
            "parts": [{"id": "intro", "from_s": 0.0, "to_s": 0.5}, {"id": "play", "from_s": 0.5, "to_s": play_to},
                      {"id": "end", "from_s": duration - 4.0, "to_s": duration}],
            "layers": [{"id": "hook", "kind": "caption", "text": "Can you beat it?", "from_s": 0.0, "to_s": 2.0},
                       {"id": "cap_result", "kind": "caption", "text": "Phew! 00:03 left", "from_s": play_to, "to_s": play_to + 2.0},
                       {"id": "end_title", "kind": "caption", "text": "Color Block Jam", "from_s": duration - 4.0, "to_s": duration},
                       {"id": "end_cta", "kind": "caption", "text": "PLAY NOW", "from_s": duration - 4.0, "to_s": duration}],
            "moments": [{"id": f"drag_{i}", "kind": "exit", "block": "red", "at_s": 1.0 + 3 * i, "exit_s": 1.3 + 3 * i} for i in range(exits)],
            "clock": [{"clock_s": 5, "at_s": play_to - 5}, {"clock_s": 4, "at_s": play_to - 4}] if hurry else [],
            "gameplay": {"ending": ending}}


def brief(theme="game", tempo="normal", curve="even", language="en"):
    b = B.default_brief()
    b["visuals"]["theme"], b["pacing"]["tempo"], b["pacing"]["curve"], b["language"] = theme, tempo, curve, language
    return b


@pytest.fixture
def small_studio(tmp_path, monkeypatch):
    monkeypatch.setattr(studio, "STUDIO", tmp_path / "studio")
    cid = "1018-120000-a-tense-ad"
    d = tmp_path / "studio" / cid / "v1"
    (d / "ad").mkdir(parents=True)
    b = brief("neon", "fast", "speeds_up")
    (d / "version.json").write_text(json.dumps({"n": 1, "id": cid, "prompt": "p", "brief": b, "workflow": "create", "ad_dir": f"{cid}/v1/ad",
                                                "parts": f"{cid}/v1/parts.json"}))
    (d / "parts.json").write_text(json.dumps(parts("near_fail", 30.0)))
    return cid


def test_concept_follows_the_brief_and_the_manifest():
    c = soundtrack.concept(brief("dark", "calm", "slows_down"), parts("win", 45.0, exits=5, hurry=False))
    assert c["mode"] == "minor" and c["mood"] == "tense" and c["bpm"] == 84 and c["bpm_ratio"] == 0.85
    assert c["ending"] == "win" and c["duration_s"] == 45.0 and c["play"] == {"from_s": 0.5, "to_s": 36.0}
    assert len(c["exits"]) == 5 and c["exits"][0]["at_s"] == 1.3 and c["hurry_ticks"] == [] and c["hook"]["text"] == "Can you beat it?"
    c2 = soundtrack.concept(brief("candy"), parts("near_fail"))
    assert c2["mode"] == "major" and c2["hurry_ticks"] == [16.0, 17.0] and c2["end_from_s"] == 26.0
    # the manifest's ending wins over the brief's; a missing manifest still gives a usable concept
    assert soundtrack.concept(brief(), {})["play"]["to_s"] == 22.0


def test_the_bed_is_exactly_the_ad_length_and_peaks_safely():
    for ending in ("win", "near_fail", "cliffhanger", "time_out"):
        c = soundtrack.concept(brief("pastel", "normal", "speeds_up"), parts(ending, 30.0))
        x = soundtrack.render_bed(c)
        assert len(x) == 30 * soundtrack.SR + 1
        assert 0.80 <= float(np.max(np.abs(x))) <= 0.86
        assert float(np.sqrt(np.mean(x ** 2))) > 0.02  # not silence
    # the ending differs between endings
    a = soundtrack.render_bed(soundtrack.concept(brief(), parts("win")))
    b = soundtrack.render_bed(soundtrack.concept(brief(), parts("time_out")))
    tail = slice(int(20.5 * soundtrack.SR), int(23 * soundtrack.SR))
    assert not np.allclose(a[tail], b[tail])


def test_beats_ramp_with_the_curve():
    even = soundtrack.beats(0, 10, 120, 1.0)
    fast = soundtrack.beats(0, 10, 120, 1.5)
    assert len(even) == 20 and len(fast) > len(even) and fast[1] == pytest.approx(0.5, abs=1e-3)


def test_make_writes_the_file_into_uploads_and_a_sidecar(small_studio):
    r = soundtrack.make(small_studio)
    p = studio.STUDIO / "uploads" / r["file"]
    assert r["file"].startswith("soundtrack-atensead-v1") and p.is_file() and r["path"] == f"uploads/{r['file']}"
    with wave.open(str(p)) as w:
        assert w.getframerate() == soundtrack.SR and abs(w.getnframes() / soundtrack.SR - 30.0) < 0.01
    assert r["file"] in studio.uploads() and B.is_audio(r["file"])  # the brief's music check accepts it
    assert (studio.STUDIO / "_soundtracks" / f"{r['file'][:-4]}.json").is_file()
    assert "Electric minor pentatonic" in r["description"] and "speeding up to 155" in r["description"] and "near-fail" in r["description"]
    assert r["voice"] is None and r["voice_skipped"] is None
    assert "music edit" in soundtrack.text(r)
    with pytest.raises(ValueError, match="no creative"):
        soundtrack.make("nope")


def test_voice_is_gated_and_mixed_without_the_network(small_studio, monkeypatch):
    monkeypatch.setattr(soundtrack, "voice_available", lambda: {"client": False, "key": False})
    r = soundtrack.make(small_studio, voice=True)
    assert r["voice"] is None and "voice extra" in r["voice_skipped"]
    monkeypatch.setattr(soundtrack, "voice_available", lambda: {"client": True, "key": True})
    monkeypatch.setenv("NVIDIA_API_KEY", "k")
    calls = []

    def fake(text, voice, key):
        calls.append((text, voice))
        t = np.arange(int(1.2 * soundtrack.SR)) / soundtrack.SR
        return np.sin(2 * np.pi * 220 * t) * 0.5

    monkeypatch.setattr(soundtrack, "synthesize", fake)
    r = soundtrack.make(small_studio, voice=True)
    # the creative's own captions, as they appear, in speakable words; the end title is not read
    assert [c[0] for c in calls] == ["Can you beat it?", "Phew! 3 seconds left", "Play now"] and calls[0][1] == "Magpie-Multilingual.EN-US.Jason.Happy"
    assert [l["layer"] for l in r["voice"]["lines"]] == ["hook", "cap_result", "end_cta"]
    assert r["voice"]["lines"][0]["at_s"] == 0.15 and r["voice"]["lines"][1]["at_s"] == 21.15 and r["voice"]["lines"][2]["at_s"] == 26.15
    assert r["voice"]["seconds"] == 3.6 and r["file"].endswith("-voice.wav") and "narrates the creative's own captions" in r["description"]
    calls.clear()
    r = soundtrack.make(small_studio, voice=True, narration="hook")
    assert [c[0] for c in calls] == ["Can you beat it?"] and "The hook is spoken by" in r["description"]
    # a typed line and a named voice win; a non-English creative is skipped unless a line is typed
    r = soundtrack.make(small_studio, voice=True, line="  “Beat the clock, friends”  ", voice_name="Magpie-Multilingual.EN-US.Mia.Calm")
    assert calls[-3] == ("Beat the clock, friends", "Magpie-Multilingual.EN-US.Mia.Calm")  # the typed line replaces the hook's words only
    v = json.loads((studio.STUDIO / small_studio / "v1" / "version.json").read_text())
    v["brief"]["language"] = "tr"
    (studio.STUDIO / small_studio / "v1" / "version.json").write_text(json.dumps(v))
    r = soundtrack.make(small_studio, voice=True)
    assert r["voice"] is None and "English" in r["voice_skipped"]


def test_mix_voice_ducks_the_bed_and_keeps_the_peak():
    bed = np.ones(soundtrack.SR * 3) * 0.5
    voice = np.ones(soundtrack.SR) * 0.3
    out = soundtrack.mix_voice(bed, voice, 1.0)
    scale = 0.98 / (0.5 * 0.4 + 0.95)  # the sum peaks over 0.98, so the whole mix is scaled once
    assert out[int(0.5 * soundtrack.SR)] == pytest.approx(0.5 * scale) and float(np.max(np.abs(out))) == pytest.approx(0.98)
    assert out[int(1.5 * soundtrack.SR)] == pytest.approx((0.5 * 0.4 + 0.95) * scale)  # the bed ducked to 40 % under the voice


def test_without_the_bed_the_voice_sits_on_the_creatives_own_music_or_on_silence(small_studio, monkeypatch):
    monkeypatch.setattr(soundtrack, "voice_available", lambda: {"client": True, "key": True})
    monkeypatch.setenv("NVIDIA_API_KEY", "k")
    t = np.arange(int(1.0 * soundtrack.SR)) / soundtrack.SR
    monkeypatch.setattr(soundtrack, "synthesize", lambda text, voice, key: np.sin(2 * np.pi * 220 * t) * 0.5)
    with pytest.raises(ValueError, match="nothing to make"):
        soundtrack.make(small_studio, bed=False, voice=False)
    # silence under the voice when the creative has no music
    r = soundtrack.make(small_studio, bed=False, voice=True)
    assert r["file"].endswith("-nobed-voice.wav") and r["bed"] is False and r["base_music"] is None and r["description"].startswith("No music bed")
    with wave.open(str(studio.STUDIO / "uploads" / r["file"])) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    assert abs(len(x) / soundtrack.SR - 30.0) < 0.01 and np.abs(x[3 * soundtrack.SR:20 * soundtrack.SR]).max() == 0 and np.abs(x[: soundtrack.SR]).max() > 1000
    # the creative's own music is kept under the voice
    own = studio.STUDIO / "uploads" / "mine.wav"
    soundtrack.write_wav(own, np.ones(soundtrack.SR * 2) * 0.2)
    v = json.loads((studio.STUDIO / small_studio / "v1" / "version.json").read_text())
    v["brief"]["audio"]["music"] = "mine.wav"
    (studio.STUDIO / small_studio / "v1" / "version.json").write_text(json.dumps(v))
    r = soundtrack.make(small_studio, bed=False, voice=True)
    assert r["base_music"] == "mine.wav" and "own music (mine.wav) kept" in r["description"]
    with wave.open(str(studio.STUDIO / "uploads" / r["file"])) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    assert abs(x[int(1.6 * soundtrack.SR)] / 32767 - 0.2) < 0.02  # the own music, unducked after the voice
    # a voice that cannot be made and no bed is an error, not a silent file
    monkeypatch.setattr(soundtrack, "voice_available", lambda: {"client": False, "key": False})
    with pytest.raises(ValueError, match="no voice could be made"):
        soundtrack.make(small_studio, bed=False, voice=True)


def test_add_audio_makes_the_soundtrack_then_the_music_edit(small_studio, monkeypatch):
    from cbj.workflows import edit as edit_wf
    calls = []
    monkeypatch.setattr(soundtrack, "make", lambda cid, n, **kw: (calls.append(("make", cid, n, kw)) or
                        {"file": "s.wav", "description": "d", "voice": None, "voice_skipped": "no key", "bed": True}))
    monkeypatch.setattr(edit_wf, "direct", lambda log, cid, n, op, draft=False: (calls.append(("direct", cid, n, op)) or {"id": cid, "n": n + 1}))
    log = studio.Log()
    nv = soundtrack.add_audio(log, {"id": small_studio, "n": 1}, {"bed": True, "voice": True, "line": "Go!"})
    assert nv["n"] == 2 and nv["audio_added"]["file"] == "s.wav" and nv["audio_added"]["from_version"] == 1 and nv["audio_added"]["voice_skipped"] == "no key"
    assert calls[0][0] == "make" and calls[0][3]["voice"] is True and calls[0][3]["line"] == "Go!" and calls[1] == ("direct", small_studio, 1, {"music": "s.wav"})
    assert any("voice skipped" in l["text"] for l in log.lines) and log.lines[0]["stage"] == "audio"
    assert soundtrack.add_audio(log, {"id": small_studio, "n": 1}, {"bed": False, "voice": False}) == {"id": small_studio, "n": 1}


def test_speakable_and_placement():
    assert soundtrack.speakable("Phew! 00:03 left") == "Phew! 3 seconds left" and soundtrack.speakable("01:00 left") == "1 minute left"
    assert soundtrack.speakable("PLAY NOW") == "Play now" and soundtrack.speakable("  “Go!”  ") == "Go!"
    one = np.zeros(soundtrack.SR * 2)
    lines = [{"layer": "hook", "text": "a", "from_s": 0.0, "to_s": 2.0}, {"layer": "cap_mistake", "text": "b", "from_s": 1.0, "to_s": 1.5},
             {"layer": "cap_result", "text": "c", "from_s": 20.0, "to_s": 25.0}, {"layer": "end_cta", "text": "d", "from_s": 29.5, "to_s": 30.0}]
    placed = soundtrack.place(lines, [one, one, one, one], 30.0)
    assert [(l["layer"], l["at_s"]) for l in placed] == [("hook", 0.15), ("cap_result", 20.15)]  # b has no room after a; d would run past the end


def test_a_voice_service_failure_skips_the_voice_and_keeps_the_bed(small_studio, monkeypatch):
    """A transport error at Magpie (DNS, TLS, a gRPC status) must not fail the make job: the bed is written, the voice
    is skipped with the reason, and the call was retried once (the demo of 2026-10-19 failed a whole make on a DNS blip)."""
    monkeypatch.setattr(soundtrack, "voice_available", lambda: {"client": True, "key": True})
    monkeypatch.setenv("NVIDIA_API_KEY", "k")
    monkeypatch.setattr(soundtrack.time, "sleep", lambda s: None)
    calls = []

    def broken(text, voice, key):
        calls.append(text)
        raise RuntimeError("errors resolving grpc.nvcf.nvidia.com:443: DNS query cancelled")

    monkeypatch.setattr(soundtrack, "synthesize", broken)
    r = soundtrack.make(small_studio, voice=True)
    assert r["voice"] is None and "did not answer" in r["voice_skipped"] and "DNS query cancelled" in r["voice_skipped"]
    assert len(calls) == 2 and r["bed"] and r["file"].endswith(".wav") and not r["file"].endswith("-voice.wav")
    # without a bed either, the failure is still a plain reason, not a crash
    with pytest.raises(ValueError, match="did not answer"):
        soundtrack.make(small_studio, voice=True, bed=False)
