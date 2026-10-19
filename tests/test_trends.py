"""Ideas from trends (trends.py): the safety filters, the idea checks, the cache, and that nothing
reaches the network or the planner (both are fakes here)."""
import json

import pytest

from cbj import studio, trends


class FakeClient:
    def __init__(self, answer):
        self.answer, self.calls, self.last_model = answer, [], "fake/model"

    def complete(self, system, user, schema):
        self.calls.append(user)
        return json.dumps(self.answer)


GOOD_PROMPT = ("Concept: 'final-play comeback'. A hard narrow-centre level on a medium-sized board. The ending is a near-fail "
               "solved with two seconds left, the tempo speeds up toward the end. Hook: \"Down to the wire\". The hurry caption "
               "is \"Clock's running out!\". Use only red, blue and yellow blocks on a dark theme. 30 seconds.")


def idea(**kw):
    base = {"title": "Last-second comeback", "trend": "A college football game decided on the last play", "category": "sport",
            "source": "college football scores", "why_now": "Top search today.", "mapping": "A near-fail with two seconds left.",
            "hook": "Down to the wire", "prompt": GOOD_PROMPT}
    base.update(kw)
    return base


@pytest.fixture
def offline(tmp_path, monkeypatch):
    monkeypatch.setattr(studio, "STUDIO", tmp_path / "studio")
    (tmp_path / "studio").mkdir()
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    monkeypatch.setattr(trends, "google_trends", lambda geo="US": [
        {"term": "college football scores", "traffic": "20000+", "news": "Last-play finish", "url": "https://x/1"},
        {"term": "hurricane damage", "traffic": "5000+", "news": "Storm kills", "url": "https://x/2"},
    ])
    monkeypatch.setattr(trends, "tavily_search", lambda q, key, days=10, max_results=5: [
        {"title": "Fall festivals and pumpkin spice everywhere", "url": "https://x/3", "published": "2026-10-17", "content": "cosy"},
        {"title": "Best new games this week", "url": "https://x/4", "published": "2026-10-17", "content": "listicle"},
        {"title": "Election day protests", "url": "https://x/5", "published": "2026-10-17", "content": "politics"},
    ])
    return tmp_path


def test_safety_and_listicle_filters():
    assert trends.safe("pumpkin spice season") and not trends.safe("storm kills three") and not trends.safe("Election results")
    assert trends.GENERIC.search("Best new games this week") and trends.GENERIC.search("What to watch tonight")
    assert not trends.GENERIC.search("Grand Rapids Marathon weekend")


def test_signals_drop_unsafe_and_generic_items(offline):
    s = trends.signals(None, "US", "k")
    assert [t["term"] for t in s["google"]] == ["college football scores"]
    assert [n["title"] for n in s["news"]] == ["Fall festivals and pumpkin spice everywhere"]


def test_idea_checks():
    assert trends._check_idea(idea()) is None
    assert trends._check_idea(idea(hook="A hook that is far too long for the screen")) == "the hook is over 6 words"
    assert "statistics" in trends._check_idea(idea(prompt=GOOD_PROMPT + " Only 1% can solve it."))
    assert trends._check_idea(idea(trend="a shooting at a game")) == "an unsafe trend"
    assert "technical names" in trends._check_idea(idea(prompt=GOOD_PROMPT + " Set ending near_fail and finish streak."))
    assert "too short" in trends._check_idea(idea(prompt="A short one."))


def test_discover_filters_caches_and_never_hits_the_network(offline):
    client = FakeClient({"ideas": [idea(), idea(title="Bad", hook="one two three four five six seven")],
                         "skipped": [{"trend": "x", "why": "unsafe"}]})
    r = trends.discover(n=4, client=client)
    assert [i["title"] for i in r["ideas"]] == ["Last-second comeback"] and r["cached"] is False
    assert {"trend": "Bad", "why": "the hook is over 6 words"} in r["skipped"] and r["signals"] == {"google": 1, "news": 1}
    assert "GOOGLE TRENDING SEARCHES" in client.calls[0] and "college football scores" in client.calls[0]
    assert "hurricane" not in client.calls[0] and "Election" not in client.calls[0]
    # cached: no second model call
    r2 = trends.discover(n=1, client=client)
    assert r2["cached"] is True and len(r2["ideas"]) == 1 and len(client.calls) == 1
    assert trends.cache_path(None, "US").is_file()
    # refresh calls again; a theme has its own cache file
    trends.discover(n=4, client=client, refresh=True)
    trends.discover(theme="Halloween", client=client)
    assert len(client.calls) == 3 and "THE USER'S THEME: Halloween" in client.calls[2]
    assert trends.cache_path("Halloween", "US").name.endswith("-us-halloween.json")


def test_no_key_and_no_signals_are_plain_errors(offline, monkeypatch):
    monkeypatch.setattr(trends, "google_trends", lambda geo="US": [])
    monkeypatch.setattr(trends, "tavily_search", lambda *a, **k: [])
    with pytest.raises(ValueError, match="no trend signals"):
        trends.discover(client=FakeClient({"ideas": [], "skipped": []}), refresh=True)
    monkeypatch.setenv("TAVILY_API_KEY", "")
    monkeypatch.setattr(trends, "tavily_key", lambda: "")
    assert trends.available() is False
    with pytest.raises(ValueError, match="TAVILY_API_KEY"):
        trends.discover(client=FakeClient({"ideas": [], "skipped": []}))


def test_text_rendering(offline):
    r = trends.discover(client=FakeClient({"ideas": [idea()], "skipped": []}), refresh=True)
    t = trends.text(r)
    assert "1. Last-second comeback" in t and "prompt: Concept" in t


def test_region_is_validated_before_urls_and_file_names(offline):
    assert trends.region_code("tr") == "TR" and trends.region_code(None) == "US" and trends.region_code("GB-ENG") == "GB-ENG"
    for bad in ("../../etc", "US/..", "a", "US;rm", "https://x"):
        with pytest.raises(ValueError, match="region"):
            trends.region_code(bad)
        with pytest.raises(ValueError):
            trends.discover(region=bad, client=FakeClient({"ideas": [], "skipped": []}))
    assert trends.cache_path("../../x", "US").parent.name == "_trends"


def test_public_url_refuses_local_and_private_links(monkeypatch):
    for bad in ("ftp://x", "not a url", "http://localhost/", "http://127.0.0.1:8765/api/meta", "http://10.0.0.5/", "http://box.local/"):
        with pytest.raises(ValueError):
            trends.public_url(bad)
    monkeypatch.setattr(trends.socket, "getaddrinfo", lambda host, port: [(None, None, None, None, ("93.184.216.34", 0))])
    assert trends.public_url("https://example.com/article ") == "https://example.com/article"
    monkeypatch.setattr(trends.socket, "getaddrinfo", lambda host, port: [(None, None, None, None, ("192.168.1.9", 0))])
    with pytest.raises(ValueError, match="private"):
        trends.public_url("https://evil.example/")


def test_fetch_text_strips_tags(monkeypatch):
    import io

    class R(io.BytesIO):
        headers = {"Content-Type": "text/html; charset=utf-8"}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(trends, "public_url", lambda u: u)
    monkeypatch.setattr(trends._OPENER, "open", lambda req, timeout=0: R(
        b"<html><head><title>Fall fest &amp; more</title><script>x()</script></head><body><nav>menu</nav><p>Pumpkin spice is back.</p></body></html>"))
    t = trends.fetch_text("https://example.com/a")
    assert t.startswith("Fall fest & more") and "Pumpkin spice is back." in t and "x()" not in t and "menu" not in t


def test_fetch_text_revalidates_every_redirect_hop(monkeypatch):
    import email

    seen = []

    def fake_public(u):
        seen.append(u)
        if "127.0.0.1" in u or "10.0." in u:
            raise ValueError("private")
        return u

    def fake_open(req, timeout=0):
        h = email.message_from_string("Location: http://127.0.0.1:8765/api/meta\n")
        raise trends.urllib.error.HTTPError(req.full_url, 302, "Found", h, None)

    monkeypatch.setattr(trends, "public_url", fake_public)
    monkeypatch.setattr(trends._OPENER, "open", fake_open)
    assert trends.fetch_text("https://example.com/bounce") == ""
    assert seen == ["https://example.com/bounce", "http://127.0.0.1:8765/api/meta"]
    assert trends._NoRedirect().redirect_request(None, None, None, None, None, None) is None


def test_from_link_uses_the_page_as_the_only_signal_and_caches(offline, monkeypatch):
    monkeypatch.setattr(trends, "public_url", lambda u: u.strip())
    page = "Fall fest weekend\n" + "Pumpkin spice is back and the fall festivals are filling the parks this weekend. " * 8
    monkeypatch.setattr(trends, "read_link", lambda url, key: page)
    client = FakeClient({"ideas": [idea(source="something else")], "skipped": []})
    r = trends.from_link("https://example.com/fall", n=2, client=client)
    assert r["link"] == "https://example.com/fall" and r["ideas"][0]["source"] == "https://example.com/fall"
    assert "THE USER'S LINK: https://example.com/fall" in client.calls[0] and "Pumpkin spice" in client.calls[0]
    assert "GOOGLE TRENDING" not in client.calls[0] and r["signals"] == {"google": 0, "news": 0, "link": 1}
    r2 = trends.from_link("https://example.com/fall", n=2, client=client)
    assert r2["cached"] is True and len(client.calls) == 1
    # an unreadable page, an unsafe page, and no usable idea are plain errors
    monkeypatch.setattr(trends, "read_link", lambda url, key: "short")
    with pytest.raises(ValueError, match="could not be read"):
        trends.from_link("https://example.com/x", client=client)
    monkeypatch.setattr(trends, "read_link", lambda url, key: "A shooting at the stadium " * 20)
    with pytest.raises(ValueError, match="should not ride"):
        trends.from_link("https://example.com/y", client=client)
    monkeypatch.setattr(trends, "read_link", lambda url, key: page)
    with pytest.raises(ValueError, match="no usable idea"):
        trends.from_link("https://example.com/z", client=FakeClient({"ideas": [idea(hook="one two three four five six seven")], "skipped": []}))
    assert "link" in trends.text(r)
