"use client";

import { ExternalLink, Link2, Loader2, RefreshCw, Search, TrendingUp } from "lucide-react";
import { useState } from "react";
import { EngineError, enginePost } from "@/lib/engine";
import type { TrendIdea, Trends } from "@/lib/types";
import { useEngine } from "../EngineProvider";
import { Badge, Button, Card, CardTitle, ErrorBox, Fold, Muted, cx, type Tone } from "../ui";

// "Start from a trend (optional)" (SPEC-ENHANCE §2): what is trending today, turned by the engine into
// Color Block Jam prompts. Never fetches on its own: an idea costs a model call. A pasted link (§2b) goes to the
// same endpoint with `url`; its ideas are shown above the feed's, each result keeping its own footer.

const CAT_TONE: Record<string, Tone> = { gaming: "violet", culture: "sky", season: "mint", sport: "grey", viral: "grey" };

function when(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false });
}

function host(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function Skeleton({ n }: { n: number }) {
  return (
    <>
      {Array.from({ length: n }, (_, i) => (
        <li key={i} aria-hidden className="flex h-56 animate-pulse flex-col gap-2 rounded-xl bg-surface-container-low p-4 motion-reduce:animate-none">
          <div className="h-4 w-16 rounded-full bg-surface-container-high" />
          <div className="h-5 w-3/4 rounded bg-surface-container-high" />
          <div className="h-3 w-full rounded bg-surface-container" />
          <div className="h-3 w-5/6 rounded bg-surface-container" />
          <div className="mt-auto h-9 w-32 rounded-xl bg-surface-container-high" />
        </li>
      ))}
    </>
  );
}

function Skipped({ items }: { items: Trends["skipped"] }) {
  if (!items.length) return null;
  return (
    <Fold summary={`Skipped (${items.length})`} className="!mt-1">
      <ul className="flex flex-col gap-1">
        {items.map((s, i) => (
          <li key={i} className="text-body-sm text-on-surface-variant">
            <span className="font-semibold text-on-surface">{s.trend}</span>: {s.why}
          </li>
        ))}
      </ul>
    </Fold>
  );
}

export default function TrendCard({ hasText, onUse }: { hasText: boolean; onUse: (prompt: string) => void }) {
  const engine = useEngine();
  const [theme, setTheme] = useState("");
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState<"feed" | "link" | null>(null);
  const [error, setError] = useState("");
  const [linkError, setLinkError] = useState("");
  const [res, setRes] = useState<Trends | null>(null);
  const [linkRes, setLinkRes] = useState<Trends | null>(null);
  const [asking, setAsking] = useState<string | null>(null); // the idea waiting for "Replace your text?" ("link-0", "feed-2")

  if (engine.status !== "online" || engine.meta?.features?.trends !== true) return null;

  async function get(refresh: boolean) {
    if (loading || !(await engine.ensureUnlocked())) return;
    setLoading("feed");
    setError("");
    setAsking(null);
    try {
      setRes(await enginePost<Trends>(engine.conn, "/api/trends", { theme: theme.trim() || null, region: "US", n: 4, refresh }));
    } catch (e) {
      setError(e instanceof EngineError && e.status === 404 ? "This engine has no trend ideas yet (it needs a restart with the new version)." : (e as Error).message);
    } finally {
      setLoading(null);
    }
  }

  // §2b: the page behind the link is the only signal. Refresh re-reads the link shown, not the field.
  async function read(link: string, refresh: boolean) {
    if (loading || !link.trim() || !(await engine.ensureUnlocked())) return;
    setLoading("link");
    setLinkError("");
    setAsking(null);
    try {
      setLinkRes(await enginePost<Trends>(engine.conn, "/api/trends", { url: link.trim(), theme: theme.trim() || null, n: 2, refresh }));
    } catch (e) {
      setLinkError((e as Error).message); // the engine's detail, verbatim
    } finally {
      setLoading(null);
    }
  }

  function use(key: string, idea: TrendIdea) {
    if (hasText && asking !== key) {
      setAsking(key);
      return;
    }
    setAsking(null);
    onUse(idea.prompt);
  }

  function ideaItem(idea: TrendIdea, key: string, fromLink: boolean) {
    const isUrl = /^https?:\/\//i.test(idea.source);
    return (
      <li key={key} className="flex min-w-0 flex-col gap-2 rounded-xl bg-surface-container-low p-4">
        <div className="flex flex-wrap gap-1.5">
          {fromLink ? (
            <Badge tone="amber">
              <Link2 aria-hidden className="size-3" /> From your link
            </Badge>
          ) : null}
          <Badge tone={CAT_TONE[idea.category] || "grey"}>{idea.category}</Badge>
        </div>
        <h3 className="text-title-sm text-on-surface">{idea.title}</h3>
        <p className="text-body-md text-on-surface">
          <span className="text-on-surface-variant">Trend: </span>
          {idea.trend}
        </p>
        <p className="text-body-sm text-on-surface-variant">
          {idea.why_now}{" "}
          {isUrl ? (
            <a href={idea.source} target="_blank" rel="noopener noreferrer" title={idea.source} className="inline-flex max-w-full items-center gap-0.5 break-all font-semibold text-secondary hover:underline">
              {fromLink ? host(idea.source) : "source"} <ExternalLink aria-hidden className="size-3 shrink-0" />
              <span className="sr-only">(opens in a new tab)</span>
            </a>
          ) : idea.source ? (
            <span className="inline-flex items-center gap-1 text-outline">
              <Search aria-hidden className="size-3" /> {idea.source}
            </span>
          ) : null}
        </p>
        {idea.mapping ? <p className="text-body-sm text-on-surface">{idea.mapping}</p> : null}
        {idea.hook ? <p className="text-body-md font-semibold text-primary">“{idea.hook.replace(/^["“']|["”']$/g, "")}”</p> : null}
        <div className="mt-auto pt-1">
          {asking === key ? (
            <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Replace your text?">
              <span className="text-label-sm text-on-surface">Replace your text?</span>
              <Button size="sm" variant="primary" onClick={() => use(key, idea)}>
                Replace
              </Button>
              <Button size="sm" variant="quiet" onClick={() => setAsking(null)}>
                Cancel
              </Button>
            </div>
          ) : (
            <Button size="sm" variant="primary" onClick={() => use(key, idea)} title={idea.prompt}>
              Use this prompt
            </Button>
          )}
        </div>
      </li>
    );
  }

  const refreshBtn = (onClick: () => void, what: string) => (
    <button type="button" onClick={onClick} disabled={!!loading} aria-label={`Refresh ${what}`} className="inline-flex min-h-8 items-center gap-1 font-semibold text-primary hover:underline disabled:opacity-50">
      <RefreshCw aria-hidden className="size-3.5" /> Refresh
    </button>
  );
  const linkIdeas = loading === "link" ? null : linkRes?.ideas || [];
  const feedIdeas = loading === "feed" ? null : res?.ideas || [];
  const showGrid = !!loading || !!linkRes?.ideas.length || !!res?.ideas.length;

  return (
    <Card label="Start from a trend">
      <CardTitle icon={TrendingUp} tone="secondary" right={<span className="text-label-sm text-on-surface-variant">Optional</span>}>
        Start from a trend (optional)
      </CardTitle>
      <Muted>What is trending today, as prompts the engine can make. Optional.</Muted>
      <form
        className="mt-3 flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void get(false);
        }}
      >
        <label className="flex min-w-0 flex-1 basis-56 flex-col gap-1">
          <span className="text-label-sm text-on-surface-variant">Theme (optional)</span>
          <input
            value={theme}
            onChange={(e) => setTheme(e.target.value)}
            placeholder="e.g. autumn, football, a game launch"
            maxLength={80}
            className="min-h-10 w-full rounded-xl bg-surface-container-low px-3 py-2 text-body-md text-on-surface outline-none placeholder:text-outline focus:bg-surface-container-high"
          />
        </label>
        <Button type="submit" variant="secondary" icon={loading === "feed" ? undefined : TrendingUp} disabled={!!loading}>
          {loading === "feed" ? <Loader2 aria-hidden className="size-[18px] animate-spin motion-reduce:animate-none" /> : null}
          {res ? "Get new ideas" : "Get ideas"}
        </Button>
      </form>

      <form
        noValidate // a wrong link gets the engine's own words under the field, not the browser's bubble
        className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-end"
        onSubmit={(e) => {
          e.preventDefault();
          void read(url, false);
        }}
      >
        <label className="flex min-w-0 flex-1 flex-col gap-1">
          <span className="text-label-sm text-on-surface-variant">Or paste a link to an article, a post or a trend page</span>
          <input
            type="url"
            inputMode="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://…"
            maxLength={2000}
            aria-invalid={linkError ? true : undefined}
            aria-describedby={linkError ? "trend-link-error" : undefined}
            className="min-h-10 w-full rounded-xl bg-surface-container-low px-3 py-2 text-body-md text-on-surface outline-none placeholder:text-outline focus:bg-surface-container-high"
          />
        </label>
        <Button type="submit" variant="secondary" icon={loading === "link" ? undefined : Link2} disabled={!!loading || !url.trim()} className="self-start sm:self-auto">
          {loading === "link" ? <Loader2 aria-hidden className="size-[18px] animate-spin motion-reduce:animate-none" /> : null}
          Read link
        </Button>
      </form>
      {linkError ? (
        <p id="trend-link-error" role="alert" className="mt-1.5 whitespace-pre-wrap text-body-sm font-semibold text-error">
          {linkError}
        </p>
      ) : null}

      <p aria-live="polite" className={cx("text-body-sm text-on-surface-variant", loading ? "mt-3" : "sr-only")}>
        {loading === "feed" ? "Checking Google Trends and the news… writing ideas" : loading === "link" ? "Reading the page… writing ideas" : ""}
      </p>
      {error ? <ErrorBox message={error} /> : null}

      {showGrid ? (
        <ul className="mt-4 grid grid-cols-[repeat(auto-fill,minmax(16.5rem,1fr))] gap-3" aria-label="Ideas from trends" aria-busy={loading ? true : undefined}>
          {linkIdeas ? linkIdeas.map((idea, i) => ideaItem(idea, `link-${i}`, true)) : <Skeleton n={2} />}
          {feedIdeas ? feedIdeas.map((idea, i) => ideaItem(idea, `feed-${i}`, false)) : <Skeleton n={4} />}
        </ul>
      ) : null}

      {linkRes && loading !== "link" ? (
        <>
          {!linkRes.ideas.length ? <Muted className="mt-3">No idea came out of that link. Try another page.</Muted> : null}
          <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-body-sm text-on-surface-variant">
            <span>
              From {host(linkRes.link || "")} · read {when(linkRes.generated)}
            </span>
            {refreshBtn(() => void read(linkRes.link || "", true), "the ideas from the link")}
          </div>
          <Skipped items={linkRes.skipped} />
        </>
      ) : null}
      {res && loading !== "feed" ? (
        <>
          {!res.ideas.length ? <Muted className="mt-3">No idea passed the checks this time. Try a theme or refresh.</Muted> : null}
          <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-body-sm text-on-surface-variant">
            <span>
              Generated {when(res.generated)} · {res.signals.google} trending searches, {res.signals.news} news items
              {res.cached ? " · cached" : ""}
            </span>
            {refreshBtn(() => void get(true), "the trend ideas")}
          </div>
          <Skipped items={res.skipped} />
        </>
      ) : null}
    </Card>
  );
}
