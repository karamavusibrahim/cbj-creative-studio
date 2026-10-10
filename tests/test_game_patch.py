"""The game patch (unity/game-patch): small, written against Rollic's files, applied only to copies."""

import shutil
import subprocess
from pathlib import Path

import pytest

from cbj.render import DEFAULT_PROJECT, GAME_PATCH, PATCHED_FILES, apply_game_patch

ORIGINAL = GAME_PATCH / "original"
PATCHED = GAME_PATCH / "patched"


def fake_project(tmp_path: Path, source: Path) -> Path:
    for rel in PATCHED_FILES:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(source / rel, tmp_path / rel)
    return tmp_path


@pytest.mark.skipif(not (DEFAULT_PROJECT / "Assets").is_dir(), reason="the Unity project is not at ../CBJ")
def test_rollics_project_is_untouched_and_matches_the_saved_originals():
    for rel in PATCHED_FILES:
        assert (DEFAULT_PROJECT / rel).read_bytes() == (ORIGINAL / rel).read_bytes(), rel


def test_patch_applies_to_the_originals_and_can_be_undone(tmp_path):
    project = fake_project(tmp_path, ORIGINAL)
    apply_game_patch(project)
    assert all((project / r).read_bytes() == (PATCHED / r).read_bytes() for r in PATCHED_FILES)
    apply_game_patch(project)  # applying twice is harmless
    apply_game_patch(project, stock=True)
    assert all((project / r).read_bytes() == (ORIGINAL / r).read_bytes() for r in PATCHED_FILES)


def test_patch_refuses_a_file_it_was_not_written_for(tmp_path):
    project = fake_project(tmp_path, ORIGINAL)
    (project / PATCHED_FILES[0]).write_text("// someone else's GameManager\n")
    with pytest.raises(ValueError, match="differs from the version the game patch was written for"):
        apply_game_patch(project)


def test_the_patch_is_small_marked_and_matches_game_patch_file():
    diff = subprocess.run(["diff", "-ru", "original", "patched"], cwd=GAME_PATCH,
                          capture_output=True, text=True).stdout
    assert diff == (GAME_PATCH / "game.patch").read_text()
    added = [ln for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++")]
    removed = [ln for ln in diff.splitlines() if ln.startswith("-") and not ln.startswith("---")]
    assert len(added) <= 40 and len(removed) <= 5
    patched_text = "".join((PATCHED / r).read_text() for r in PATCHED_FILES)
    assert patched_text.count("cbj-creative patch") >= 6
    assert "public void OnBlockExitStarted(GameObject blockObj)" in patched_text
    assert "_gameManager.OnBlockExitStarted(block.gameObject);" in patched_text
