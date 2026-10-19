"""Prompt enhancement (enhance.py): the code checks that keep a rewrite honest, the fallback to the
user's own words, and the workflow line. The model is a fake that answers what each test sets."""
import json

import pytest

from cbj import enhance, studio


class FakeClient:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []
        self.last_model = "fake/model"

    def complete(self, system, user, schema):
        self.calls.append(user)
        a = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        return json.dumps(a)


def rewrite(prompt, changed=True, changes=(), questions=(), warnings=()):
    return {"prompt": prompt, "changed": changed, "changes": list(changes), "questions": list(questions), "warnings": list(warnings)}


@pytest.fixture
def no_studio(tmp_path, monkeypatch):
    monkeypatch.setattr(studio, "STUDIO", tmp_path / "studio")
    (tmp_path / "studio" / "uploads").mkdir(parents=True)
    return tmp_path / "studio"


# ── the code checks ──────────────────────────────────────────────────────────────────────────────

def test_quoted_captions_must_stay_word_for_word():
    orig = 'A near-fail with the hook "Can you beat the clock?" and 30 seconds.'
    v = enhance.violations(orig, rewrite('A near-fail, 30 seconds, hook "Beat the clock".'))
    assert "these quoted words of the request must stay word for word: “Can you beat the clock?”" in v
    assert any("adds a caption (“Beat the clock”)" in x for x in v)
    assert enhance.violations(orig, rewrite('A near-fail ending, hook caption "Can you beat the clock?", 30 seconds long.')) == []


def test_an_added_ask_is_a_violation_unless_a_change_entry_ties_it_to_the_users_words():
    orig = "a calm ad on a small board"
    bad = rewrite("A calm ad on a small open board, hard difficulty, 45 seconds long.")
    v = enhance.violations(orig, bad)
    assert any("adds a difficulty" in x for x in v) and any("adds a length" in x for x in v)
    # the same facts, justified: the user's words are quoted in `before`
    ok = rewrite("A calm ad on a small open board, hard difficulty, 45 seconds long.",
                 changes=[{"kind": "translated", "before": "small board", "after": "a small open board, hard difficulty, 45 seconds long", "why": "x"}])
    assert enhance.violations(orig, ok) == []
    # a `before` that is not in the request justifies nothing
    fake = rewrite("A calm ad, hard difficulty.",
                   changes=[{"kind": "clarified", "before": "really tough", "after": "hard difficulty", "why": "x"}])
    assert any("adds a difficulty" in x for x in enhance.violations(orig, fake))


def test_translation_counts_as_justification():
    orig = "Zor bir seviye, 45 saniye"
    out = rewrite("A hard level, 45 seconds long.",
                  changes=[{"kind": "translated", "before": "Zor bir seviye", "after": "A hard level", "why": "t"},
                           {"kind": "translated", "before": "45 saniye", "after": "45 seconds long", "why": "t"}])
    assert enhance.violations(orig, out) == []


def test_new_captions_and_technical_words_and_stats_and_bullets_are_caught():
    orig = "a satisfying solve"
    v = enhance.violations(orig, rewrite('A satisfying solve with the hook "One move frees them all today, friends".'))
    assert any("more than 6 words" in x for x in v) and any("adds a caption" in x for x in v)
    v = enhance.violations(orig, rewrite("A satisfying solve with ending near_fail and the end_art kept."))
    assert any("technical names" in x for x in v)
    v = enhance.violations(orig, rewrite("A satisfying solve that only 1% can do."))
    assert any("statistic" in x for x in v)
    v = enhance.violations(orig, rewrite("- a satisfying solve\n- a clean win"))
    assert any("bullet" in x for x in v)
    assert enhance.violations(orig, rewrite("")) == ["the rewrite is empty"]


def test_a_replaced_quoted_claim_may_go_when_the_change_says_so():
    orig = 'The hook says "Only 1% can solve this".'
    out = rewrite('The hook says "Can you beat it?".',
                  changes=[{"kind": "replaced", "before": 'Only 1% can solve this', "after": 'the hook says "Can you beat it?"', "why": "ad rules"}])
    assert enhance.violations(orig, out) == []


# ── enhance(): the loop, the fallback, the result ─────────────────────────────────────────────────

def test_a_good_rewrite_is_returned_with_its_changes_and_questions(no_studio):
    client = FakeClient(rewrite("One key move frees all the red blocks, which leave one after another.",
                                changes=[{"kind": "replaced", "before": "a bomb clears the red blocks",
                                          "after": "one key move frees all the red blocks", "why": "no bombs"}],
                                questions=[{"question": "How should it end?", "options": ["End with a clean win.", "End with a near-fail."]}],
                                warnings=["Bombs do not exist in the game."]))
    r = enhance.enhance("make an ad where a bomb clears the red blocks", client=client)
    assert r["changed"] and r["prompt"].startswith("One key move") and r["original"].startswith("make an ad")
    assert r["changes"][0]["kind"] == "replaced" and r["questions"][0]["options"] == ["End with a clean win.", "End with a near-fail."]
    assert r["warnings"] == ["Bombs do not exist in the game."] and r["workflow"] == "create" and r["mode"] == "new"
    assert "MODE: NEW" in client.calls[0] and "ATTACHED FILES: none" in client.calls[0]


def test_a_rewrite_that_keeps_adding_asks_falls_back_to_the_users_words(no_studio):
    bad = rewrite("A hard near-fail level, 45 seconds.", questions=[{"question": "Length?", "options": ["Make it 45 seconds long."]}])
    client = FakeClient(bad, bad)
    r = enhance.enhance("a tense ad", client=client)
    assert r["changed"] is False and r["prompt"] == "a tense ad" and r["changes"] == []
    assert len(client.calls) == 2 and "BROKE THESE RULES" in client.calls[1]
    assert any(w.startswith("Kept your wording:") and "adds a difficulty" in w for w in r["warnings"])
    assert r["questions"][0]["options"] == ["Make it 45 seconds long."]  # the model's additions survive as questions


def test_the_second_try_may_fix_it(no_studio):
    bad = rewrite("A hard level.")
    good = rewrite("A tense ad.", changes=[{"kind": "clarified", "before": "tense", "after": "tense", "why": "kept"}])
    r = enhance.enhance("a tense ad", client=FakeClient(bad, good))
    assert r["prompt"] == "A tense ad." and r["changed"] and len(r["changes"]) == 1


def test_unchanged_when_the_model_says_so_or_only_whitespace_differs(no_studio):
    r = enhance.enhance("A hard level, 30 seconds.", client=FakeClient(rewrite("A  hard level, 30 seconds.", changed=True)))
    assert r["changed"] is False and r["prompt"] == "A hard level, 30 seconds."
    r = enhance.enhance("A hard level, 30 seconds.", client=FakeClient(rewrite("A hard level, 30 seconds.", changed=False)))
    assert r["changed"] is False and r["changes"] == []


def test_own_warnings_long_caption_stats_and_length(no_studio):
    r = enhance.enhance('A 20 second ad, hook "This is a very long caption nobody reads", only 1% win.',
                        client=FakeClient(rewrite("x", changed=False)))
    w = " ".join(r["warnings"])
    assert "over 6 words" in w and "Statistics" in w and "30-60 second" in w


def test_an_empty_prompt_and_an_unknown_creative_are_errors(no_studio):
    with pytest.raises(ValueError):
        enhance.enhance("   ", client=FakeClient(rewrite("x")))
    with pytest.raises(ValueError, match="no creative"):
        enhance.enhance("change the hook", creative_id="nope", client=FakeClient(rewrite("x")))


def test_the_workflow_follows_the_attachments_and_the_words(no_studio):
    from PIL import Image
    Image.new("RGB", (8, 8), "red").save(no_studio / "uploads" / "ref.png")
    client = FakeClient(rewrite("x", changed=False))
    assert enhance.enhance("a calm ad", uploads=["ref.png"], client=client)["workflow"] == "create"
    assert enhance.enhance("a calm ad inspired by this image", uploads=["ref.png"], client=client)["workflow"] == "image_guided"
    assert "ref.png (image)" in client.calls[-1]


def test_text_rendering(no_studio):
    r = enhance.enhance("a tense ad", client=FakeClient(rewrite("A tense ad.", changes=[{"kind": "clarified", "before": "tense", "after": "tense", "why": "k"}],
                                                                questions=[{"question": "Q?", "options": ["Opt."]}])))
    t = enhance.text(r)
    assert "Changes (1)" in t and "You may want to add" in t and "Read as: a new creative" in t
