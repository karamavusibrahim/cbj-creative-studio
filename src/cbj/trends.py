"""Ideas from trends (2026-10-18, an optional extra beyond the brief): what is trending right now,
turned into Color Block Jam ad prompts the engine can make.

Why. A performance-marketing team starts many creatives from a current moment (a season, a game
release, a viral sound, a sport final). The engine is prompt-driven, so a trend is useful only as
a prompt in its vocabulary. This module gathers live signals (Google Trends daily searches, no key;
Tavily news search, TAVILY_API_KEY), asks the planner's model to write a few ad ideas that map a
trend to the levers the game has (look, colours, background, caption tone, hook, ending, pace),
and checks each prompt with the same code the prompt enhancer uses (no technical names, captions
under 6 words, no statistics). Nothing is made: an idea is a prompt the user may edit and send.

Honesty rules, enforced in the prompt and in code: ideas come only from the signals given (never
the model's memory), each idea names its trend and source and the day, and a trend that is unsafe
for an ad (tragedy, politics, religion, sex, violence, crime, a named real person) is dropped. The
ad's own copy never names a brand, title, team or person: the trend is the mood, the colours and
the moment, not a licence to use someone's name.

Results are cached per day, theme and region in studio/_trends/ (TTL below).

A link works the same way: the page behind a public URL is
read (Tavily extract, else a direct fetch with the tags stripped), becomes the only signal, and the same
model writes 1-3 ideas from it with the same checks; the URL is the source. Only public http(s) hosts are
fetched (no local or private addresses), at most 200 KB of text.

`cbj trends [--theme X] [--region US] [-n 4] [--refresh] [--link URL]`, POST /api/trends (with "url" for a
link), the web app's "Ideas from trends" card.
"""
from __future__ import annotations

import json
import os
import re
import time
import hashlib
import html as html_mod
import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import enhance, llm, studio

TTL_S = 6 * 3600
TAVILY_URL = "https://api.tavily.com/search"
TAVILY_EXTRACT_URL = "https://api.tavily.com/extract"
MAX_PAGE_CHARS = 6000
MAX_FETCH_BYTES = 200_000
GOOGLE_RSS = "https://trends.google.com/trending/rss?geo={geo}"
TIMEOUT_S = 12
MAX_IDEAS = 6
DEFAULT_N = 4

# Trends an ad must not ride (whole words; a match drops the signal before the model sees it).
UNSAFE = re.compile(r"\b(dead|death|dies|died|dying|kill\w*|murder|shooting|shot|stab|war|attack|bomb(ing)?|terror\w*|"
                    r"election|vote|president|minister|senate|congress|parliament|protest|riot|crash|abuse|rape|porn\w*|sex\w*|"
                    r"nude|drugs?|overdose|suicide|cancer|hospital|funeral|lawsuit|arrest(ed)?|court|trial|racis\w*|nazi|"
                    r"hamas|israel|gaza|ukraine|russia|putin|trump|biden|erdogan|netanyahu|church|mosque|religio\w*|"
                    r"earthquake|flood|hurricane|wildfire|tornado|missing|kidnap\w*|scandal|divorce|affair|gun|police)\b", re.I)
# Headlines that are not trends (listicles and evergreen pages).
GENERIC = re.compile(r"^(the\s+|a\s+)?(\d+\s+)?(best|top\s*\d*|what to (watch|play|do)|how to|guide|review|tips?|ultimate|"
                     r"free|new (movies|shows|games)|this (week|weekend)|trends? to watch|everything you need)\b", re.I)

QUERIES = [
    ("gaming", "mobile and video game releases, events and viral gaming moments trending this week"),
    ("culture", "viral pop culture, film, music and TV moments trending this week"),
    ("season", "seasonal events, holidays and celebrations coming up in the next two weeks"),
    ("sport", "major sports finals, tournaments and viral sports moments this week"),
]


REGION = re.compile(r"^[A-Za-z]{2}(-[A-Za-z0-9]{1,3})?$")  # a Google Trends geo code: "US", "TR", "GB-ENG"


def region_code(region: str | None) -> str:
    """The region as a safe upper-case code; anything else is refused before it reaches a URL or a file name."""
    r = (region or "US").strip()
    if not REGION.match(r):
        raise ValueError("the region must be a two-letter code such as US, TR or GB")
    return r.upper()


def tavily_key() -> str:
    from .planner import load_env
    load_env()
    return os.environ.get("TAVILY_API_KEY", "").strip()


def available() -> bool:
    return bool(tavily_key())


def _post_json(url: str, body: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        return json.load(r)


def tavily_search(query: str, key: str, days: int = 10, max_results: int = 5) -> list[dict]:
    """News results for a query; [] on any failure (a failed search never kills the run)."""
    try:
        j = _post_json(TAVILY_URL, {"api_key": key, "query": query, "max_results": max_results, "topic": "news",
                                    "days": days, "search_depth": "basic", "include_answer": False})
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return []
    return [{"title": r.get("title") or "", "url": r.get("url") or "", "published": r.get("published_date") or "",
             "content": (r.get("content") or "")[:320]} for r in j.get("results") or []]


def google_trends(geo: str = "US") -> list[dict]:
    """Google's daily trending searches (RSS, no key): [{term, traffic, news, url}]; [] on failure."""
    try:
        req = urllib.request.Request(GOOGLE_RSS.format(geo=urllib.parse.quote(region_code(geo), safe="")), headers={"User-Agent": "Mozilla/5.0", "Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            xml = r.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError):
        return []
    clean = lambda s: re.sub(r"<!\[CDATA\[|\]\]>", "", s or "").strip()  # noqa: E731
    pick = lambda block, tag: clean((re.search(rf"<{tag}>([\s\S]*?)</{tag}>", block) or [None, ""])[1])  # noqa: E731
    out = []
    for m in re.finditer(r"<item>([\s\S]*?)</item>", xml):
        b = m.group(1)
        term = pick(b, "title")
        if term:
            out.append({"term": term, "traffic": pick(b, "ht:approx_traffic"), "news": pick(b, "ht:news_item_title"),
                        "url": pick(b, "ht:news_item_url")})
    return out


def safe(text: str) -> bool:
    return not UNSAFE.search(text or "")


def signals(theme: str | None, region: str, key: str) -> dict:
    """The live material, already filtered for safety and listicles."""
    g = [t for t in google_trends(region) if safe(t["term"] + " " + t["news"])][:25]
    queries = list(QUERIES)
    if theme:
        queries.insert(0, ("theme", f"{theme} trending this week"))
    news = []
    seen = set()
    for cat, q in queries:
        for r in tavily_search(q, key):
            if r["url"] in seen or GENERIC.search(r["title"]) or not safe(r["title"] + " " + r["content"]):
                continue
            seen.add(r["url"])
            news.append({"category": cat, **r})
    return {"google": g, "news": news[:24]}


TREND_SYSTEM = f"""You write ideas for Color Block Jam video ads from what is trending RIGHT NOW. You are given live signals: (A) Google's top trending searches today, (B) news results. Use ONLY these signals, never your own memory of what is popular. Each idea maps ONE trend to the levers the game and the tool actually have.

{enhance.VOCABULARY}

HOW A TREND BECOMES AN AD HERE. The gameplay is always the real game: blocks, gates, the clock. A trend can change: the look (a theme: candy, pastel, neon, dark; block colours by name; the background behind the board: two colours), the caption tone and the hook (quoted, under 6 words), the concept line, the ending (a near-fail for suspense, a clean fast solve for satisfaction, a cliffhanger for a challenge, a time-out only for a fail story), the tempo and the curve, the length (30-60 s), the format. It can suggest an attached sticker or logo ("attach a pumpkin sticker for the top-left corner" as a note, never as a given). It cannot add characters, items, other games' mechanics or any object on the board.

BRAND SAFETY. The ad's copy and theme words never name a brand, film, series, team, athlete, artist, politician or any real person; the trend is the mood, the colours, the moment and the feeling ("final-minute football drama" -> a near-fail with two seconds left and a hurry caption; "a candy-coloured pop album" -> candy theme, pink and mint blocks). Skip trends about tragedy, politics, religion, sex, violence, crime or health. Skip listicle headlines ("Best new games", "What to watch").

OUTPUT (JSON following the schema). ideas: {DEFAULT_N} to {MAX_IDEAS} ideas, most current first, each with: title (3-6 words), trend (the trend in one line, named plainly), category (gaming | culture | season | sport | viral), source (the URL or the exact search term from the signals), why_now (one sentence: what in the signals makes it current), mapping (one sentence: which levers of the game the trend sets and why), hook (the hook caption, under 6 words, no names), prompt (the complete request a marketer would type: 50-90 words, one paragraph, plain English, stating the concept and 3-5 controls from the vocabulary, with the hook quoted; the length in seconds; no names, no statistics, no field names). skipped: trends you left out for safety or vagueness, each with a reason."""

TREND_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["ideas", "skipped"],
    "properties": {
        "ideas": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["title", "trend", "category", "source", "why_now", "mapping", "hook", "prompt"],
            "properties": {"title": {"type": "string"}, "trend": {"type": "string"},
                           "category": {"type": "string", "enum": ["gaming", "culture", "season", "sport", "viral"]},
                           "source": {"type": "string"}, "why_now": {"type": "string"}, "mapping": {"type": "string"},
                           "hook": {"type": "string"}, "prompt": {"type": "string"}}}},
        "skipped": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["trend", "why"],
            "properties": {"trend": {"type": "string"}, "why": {"type": "string"}}}},
    },
}


def _signal_text(s: dict) -> str:
    a = "\n".join(f"- {t['term']}" + (f" ({t['traffic']} searches)" if t.get("traffic") else "") +
                  (f": {t['news']}" if t.get("news") else "") + (f" [{t['url']}]" if t.get("url") else "")
                  for t in s["google"]) or "- (not available today)"
    b = "\n".join(f"- [{r['category']}] {r['title']} ({r['published'][:10] or 'date unknown'}) {r['url']}\n  {r['content']}"
                  for r in s["news"]) or "- (no news results)"
    return f"(A) GOOGLE TRENDING SEARCHES NOW:\n{a}\n\n(B) NEWS THIS WEEK:\n{b}"


def _check_idea(i: dict) -> str | None:
    """Why an idea is dropped (a rule of the ad or the tool broken), or None."""
    p, hook = i.get("prompt") or "", i.get("hook") or ""
    if len(p.split()) < 25:
        return "the prompt is too short to plan from"
    if len(hook.strip("\"“”' ").split()) > enhance.MAX_CAPTION_WORDS:
        return "the hook is over 6 words"
    if enhance.STATS.search(p) or enhance.STATS.search(hook):
        return "statistics or claims in the copy"
    if not safe(i.get("trend", "") + " " + i.get("title", "") + " " + p):
        return "an unsafe trend"
    from . import brief as B
    if B.plain_text(p) != p:
        return "technical names in the prompt"
    for q in enhance.quotes(p):
        if len(q.split()) > enhance.MAX_CAPTION_WORDS:
            return f"the caption “{q}” is over 6 words"
    return None


def public_url(url: str) -> str:
    """The URL if it is a public http(s) address; ValueError otherwise (no local or private hosts, so a
    pasted link can never make the engine read its own machine or network)."""
    u = (url or "").strip()
    parts = urllib.parse.urlsplit(u)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("paste a public http(s) link")
    host = parts.hostname.lower()
    if host in ("localhost",) or host.endswith(".local") or host.endswith(".internal"):
        raise ValueError("that link points at a local address")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise ValueError("that host name cannot be resolved") from None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise ValueError("that link points at a private address")
    return u


def tavily_extract(url: str, key: str) -> str:
    """The main text of a page through Tavily; "" on any failure."""
    try:
        j = _post_json(TAVILY_EXTRACT_URL, {"api_key": key, "urls": [url]})
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return ""
    first = (j.get("results") or [{}])[0]
    return (first.get("raw_content") or first.get("content") or "").strip()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Redirects are not followed automatically: every hop goes through public_url again (a public page
    must not be able to bounce the fetch to a private address)."""

    def redirect_request(self, *a, **k):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)
MAX_HOPS = 3


def fetch_text(url: str) -> str:
    """The page fetched directly with its tags stripped (the fallback when Tavily cannot read it); "" on failure.
    Each redirect hop is validated like the first URL."""
    raw = None
    try:
        for _ in range(MAX_HOPS + 1):
            url = public_url(url)
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (cbj-creative trends)"})
            try:
                with _OPENER.open(req, timeout=TIMEOUT_S) as r:
                    ctype = r.headers.get("Content-Type", "")
                    if "html" not in ctype and "text" not in ctype:
                        return ""
                    raw = r.read(MAX_FETCH_BYTES).decode("utf-8", "replace")
                break
            except urllib.error.HTTPError as e:
                if e.code in (301, 302, 303, 307, 308) and e.headers.get("Location"):
                    url = urllib.parse.urljoin(url, e.headers["Location"])
                    continue
                return ""
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return ""
    if raw is None:
        return ""
    raw = re.sub(r"(?is)<(script|style|noscript|svg|nav|footer|header)[^>]*>.*?</\1>", " ", raw)
    title = re.search(r"(?is)<title[^>]*>(.*?)</title>", raw)
    text = re.sub(r"(?s)<[^>]+>", " ", raw)
    text = html_mod.unescape(re.sub(r"[ \t\r\f\v]+", " ", text))
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    return ((html_mod.unescape(title.group(1)).strip() + "\n") if title else "") + text


def read_link(url: str, key: str) -> str:
    """The page's text, at most MAX_PAGE_CHARS, by Tavily first and the direct fetch second."""
    text = tavily_extract(url, key) if key else ""
    if len(text) < 200:
        text = fetch_text(url) or text
    return text[:MAX_PAGE_CHARS]


def from_link(url: str, theme: str | None = None, n: int = 2, refresh: bool = False, client=None, log=None) -> dict:
    """Ideas from one link: the page is the only signal. Raises ValueError for a bad or unreadable link."""
    from .planner import _parse
    url = public_url(url)
    key = tavily_key()
    n = max(1, min(int(n or 2), 3))
    theme = (theme or "").strip()[:80] or None
    folder = (studio.STUDIO / "_trends").resolve()
    path = folder / f"link-{hashlib.sha256((url + '|' + (theme or '')).encode()).hexdigest()[:16]}.json"
    if not refresh and path.is_file() and time.time() - path.stat().st_mtime < TTL_S:
        cached = json.loads(path.read_text())
        cached["cached"] = True
        cached["ideas"] = cached["ideas"][:n]
        return cached
    t0 = time.time()
    if log:
        log(f"reading {url}...")
    text = read_link(url, key)
    if len(text) < 200:
        raise ValueError("that page could not be read (paywalled, login-only, a social feed or heavy scripts); try a public article link")
    if not safe(text[:1500]):
        raise ValueError("that page is about a topic an ad should not ride (tragedy, politics, violence or the like)")
    client = client or llm.planner_client()
    user = (f"TODAY: {time.strftime('%A %d %B %Y')}. THE USER PASTED ONE LINK; its page is the only signal. WRITE {n} IDEA(S) "
            f"from it (fewer if the page gives only one trend)." + (f" THE USER'S THEME: {theme}." if theme else "") +
            f"\n\n(C) THE USER'S LINK: {url}\nPAGE TEXT:\n{text}")
    out = _parse(client.complete(TREND_SYSTEM, user, TREND_SCHEMA))
    ideas, skipped = [], list(out.get("skipped") or [])
    for i in out.get("ideas") or []:
        why = _check_idea(i)
        if why:
            skipped.append({"trend": i.get("title") or i.get("trend") or "?", "why": why})
            continue
        idea = {k: (i.get(k) or "").strip() for k in ("title", "trend", "category", "source", "why_now", "mapping", "hook", "prompt")}
        idea["source"] = url  # the link is the source, whatever the model wrote
        ideas.append(idea)
    if not ideas:
        raise ValueError("no usable idea came out of that page: " + ("; ".join(f"{s_['trend']} ({s_['why']})" for s_ in skipped[:3]) or "it gave no trend"))
    result = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S"), "region": None, "theme": theme, "link": url, "ideas": ideas,
              "skipped": skipped[:8], "signals": {"google": 0, "news": 0, "link": 1}, "sources": [{"title": text.split("\n", 1)[0][:120], "url": url, "published": ""}],
              "model": getattr(client, "last_model", None), "seconds": round(time.time() - t0, 1), "cached": False}
    folder.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=1))
    result["ideas"] = ideas[:n]
    return result


def cache_path(theme: str | None, region: str) -> Path:
    """The cache file; both parts of the name are slugs, and the result must stay inside studio/_trends."""
    slug = re.sub(r"[^a-z0-9]+", "-", (theme or "general").lower()).strip("-")[:40] or "general"
    geo = region_code(region).lower()
    folder = (studio.STUDIO / "_trends").resolve()
    path = (folder / f"{time.strftime('%Y-%m-%d')}-{geo}-{slug}.json").resolve()
    if not path.is_relative_to(folder):
        raise ValueError("bad cache path")
    return path


def discover(theme: str | None = None, region: str = "US", n: int = DEFAULT_N, refresh: bool = False, client=None,
             log=None) -> dict:
    """The ideas, cached. Raises ValueError when no TAVILY_API_KEY is set or the model fails."""
    from .planner import _parse
    key = tavily_key()
    if not key:
        raise ValueError("trend ideas need a TAVILY_API_KEY in cbj-creative/.env (free tier is enough)")
    region = region_code(region)
    theme = (theme or "").strip()[:80] or None
    n = max(1, min(int(n or DEFAULT_N), MAX_IDEAS))
    path = cache_path(theme, region)
    if not refresh and path.is_file() and time.time() - path.stat().st_mtime < TTL_S:
        cached = json.loads(path.read_text())
        cached["cached"] = True
        cached["ideas"] = cached["ideas"][:n]
        return cached
    t0 = time.time()
    if log:
        log("checking Google Trends and the news...")
    s = signals(theme, region, key)
    if not s["google"] and not s["news"]:
        raise ValueError("no trend signals could be fetched (Google Trends and the news search both failed); try again later")
    if log:
        log(f"{len(s['google'])} trending searches, {len(s['news'])} news items; writing ideas...")
    client = client or llm.planner_client()
    user = (f"TODAY: {time.strftime('%A %d %B %Y')}. REGION: {region}." + (f" THE USER'S THEME: {theme} (prefer trends that fit it)." if theme else "") +
            f" WRITE {min(MAX_IDEAS, max(n, DEFAULT_N))} IDEAS.\n\n" + _signal_text(s))
    out = _parse(client.complete(TREND_SYSTEM, user, TREND_SCHEMA))
    ideas, skipped = [], list(out.get("skipped") or [])
    for i in out.get("ideas") or []:
        why = _check_idea(i)
        if why:
            skipped.append({"trend": i.get("title") or i.get("trend") or "?", "why": why})
            continue
        ideas.append({k: (i.get(k) or "").strip() for k in ("title", "trend", "category", "source", "why_now", "mapping", "hook", "prompt")})
    result = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S"), "region": region, "theme": theme or None, "ideas": ideas,
              "skipped": skipped[:8], "signals": {"google": len(s["google"]), "news": len(s["news"])},
              "sources": [{"title": r["title"], "url": r["url"], "published": r["published"][:10]} for r in s["news"][:12]] +
                         [{"title": t["term"], "url": t["url"], "published": time.strftime("%Y-%m-%d")} for t in s["google"][:8]],
              "model": getattr(client, "last_model", None), "seconds": round(time.time() - t0, 1), "cached": False}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=1))
    result["ideas"] = ideas[:n]
    return result


def text(result: dict) -> str:
    where = f"link {result['link']}" if result.get("link") else str(result.get("region"))
    lines = [f"Ideas from trends, {result['generated'][:16]} ({where}{', theme: ' + result['theme'] if result.get('theme') else ''})"
             + (" [cached]" if result.get("cached") else "")]
    for k, i in enumerate(result["ideas"], 1):
        lines += ["", f"{k}. {i['title']}  [{i['category']}]", f"   trend: {i['trend']}", f"   why now: {i['why_now']}",
                  f"   source: {i['source']}", f"   mapping: {i['mapping']}", f"   hook: {i['hook']}", f"   prompt: {i['prompt']}"]
    if result.get("skipped"):
        lines += ["", "Skipped: " + "; ".join(f"{s['trend']} ({s['why']})" for s in result["skipped"])]
    lines.append(f"\n{result['signals'].get('google', 0)} trending searches, {result['signals'].get('news', 0)} news items"
                 + (", 1 link" if result.get("link") else "") + "; "
                 f"{result.get('model') or 'no model'}, {result.get('seconds')} s.")
    return "\n".join(lines)
