"""The viewer's review (review.py): measured facts, the contact sheet, the question and the
completed answer, with a fake multimodal client."""
import json
import subprocess
from pathlib import Path

from cbj import brief as B
from cbj import review
from cbj.video import ffmpeg_bin


def _version(tmp_path: Path) -> tuple[dict, Path]:
    studio = tmp_path / "studio"
    vdir = studio / "c1" / "v1" / "ad"
    vdir.mkdir(parents=True)
    rec = studio / "recordings" / "r1"
    rec.mkdir(parents=True)
    subprocess.run([ffmpeg_bin(), "-v", "error", "-f", "lavfi", "-i", "color=c=0x3355aa:s=108x192:d=4", "-r", "30",
                    "-pix_fmt", "yuv420p", str(vdir / "ad.mp4")], check=True)
    fps = 30
    compose = {"frames": 120, "fps": fps,
               "timeline": {"intro": {"frames": [0, 15]}, "play": {"frames": [15, 75]}, "result": {"frames": [75, 90]},
                            "result_hold": {"frames": [90, 100]}, "end": {"frames": [100, 120]}},
               "layers": {"hook": {"type": "text", "frames": [0, 60], "text": "Can you clear it?"},
                          "cap_hurry": {"type": "text", "frames": [60, 66], "text": "Hurry, only a moment left now"},
                          "cursor": {"type": "cursor", "frames": [0, 120], "text": None}}}
    (vdir / "compose.json").write_text(json.dumps(compose))
    (rec / "result.json").write_text(json.dumps({"first_touch_frame": 30, "frames": 85}))
    b = B.default_brief()
    B.control(b, "level")["asked"] = "a small open board"
    B.control(b, "level")["plan"] = "A small open board."
    v = {"id": "c1", "n": 1, "video": "c1/v1/ad/ad.mp4", "recording": {"dir": "recordings/r1"}, "brief": b,
         "checks": [{"check": "Difficulty", "status": "adjusted", "detail": "medium, asked easy"}],
         "qa": {"warnings": ["end card 8.0 s is long"]}, "prompt": "A small open board, easy."}
    return v, studio


def test_facts_measure_the_first_move_dead_time_and_captions(tmp_path):
    v, studio = _version(tmp_path)
    f = review.facts(v, studio)
    assert f["length_s"] == 4.0 and f["parts"]["play"] == 2.0
    assert f["first_move_s"] == 1.5  # 0.5 s frozen intro + 1.0 s lead-in in the recording
    assert f["static_s"] == 1.5 and f["static_share"] == 0.38  # intro + held result + end card
    caps = {c["id"]: c for c in f["captions"]}
    assert caps["hook"]["readable"] and not caps["cap_hurry"]["readable"]  # 6 words in 0.2 s
    assert f["checks"][0]["check"] == "Difficulty" and f["qa"] == ["end card 8.0 s is long"]
    assert review.measured_scores(f) == {"first_second": 5, "dead_time": 3}


def test_contact_sheet_has_one_tile_a_second_with_its_time(tmp_path):
    v, studio = _version(tmp_path)
    sheet = review.contact_sheet(studio / v["video"], tmp_path / "sheet.png")
    from PIL import Image
    im = Image.open(sheet)
    assert im.size[0] == 4 * review.TILE_W and im.size[1] > 400  # 4 frames for a 4 s video, one row


class FakeEyes:
    last_model = "fake/eyes"

    def __init__(self):
        self.asked = None

    def describe(self, ask, part, path=None):
        self.asked = ask
        assert part["type"] == "image_url" and path.suffix == ".png"
        return json.dumps({"match": [{"control": "the type or structure of the level", "verdict": "Match", "seen": "a small open board at 1-3 s"},
                                     {"control": "the creative concept", "verdict": "no", "seen": "the hook is the default one"}],
                           "viewer": {"pace": 4, "readability": 2, "clarity": 5, "cta": 3},
                           "would_download": "maybe", "why": "The puzzle reads, the hurry caption flashes by.",
                           "fixes": ["Keep the hurry caption on screen longer", "A hook that names the challenge"],
                           "suggested_edit": "Keep everything, but keep the hurry caption on screen for two seconds."})


def test_review_asks_with_the_measured_facts_and_completes_the_answer(tmp_path):
    v, studio = _version(tmp_path)
    eyes = FakeEyes()
    r = review.review(v, v["prompt"], studio, client=eyes, log=lambda m: None)
    assert "first-second score 5/5" in eyes.asked and "TOO SHORT" in eyes.asked and v["prompt"] in eyes.asked
    assert review.RUBRIC in eyes.asked and "a small open board" in eyes.asked
    assert r["viewer"] == {"pace": 4, "readability": 2, "clarity": 5, "cta": 3, "first_second": 5, "dead_time": 3}
    assert [m["verdict"] for m in r["match"]] == ["match", "no"]
    assert r["overall"] == "fix" and r["low"] == ["readability"] and r["would_download"] == "maybe"
    assert r["suggested_edit"].startswith("Keep everything") and r["model"] == "fake/eyes"
    stored = json.loads((studio / "c1" / "v1" / "review.json").read_text())
    assert stored["facts"]["first_move_s"] == 1.5 and (studio / "c1" / "v1" / "review_sheet.png").is_file()
    assert "fix" in review.summary(r) and "not as asked: the creative concept" in review.summary(r)


def test_the_skill_quotes_the_rubric_verbatim():
    skill = Path(__file__).parent.parent / ".claude" / "skills" / "cbj-creative-review" / "SKILL.md"
    quoted = "\n".join(line[2:] if line.startswith("> ") else line[1:] for line in skill.read_text().splitlines() if line.startswith(">"))
    assert " ".join(review.RUBRIC.split()) == " ".join(quoted.split())
