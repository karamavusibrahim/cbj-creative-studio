"use client";

import { ArrowRight, SquarePen } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { engineGet, idTime, posterOf, type EngineConn, type MediaSource } from "@/lib/engine";
import { fetchIndex } from "@/lib/showcase";
import type { CreativeSummary, Version } from "@/lib/types";
import { truncate } from "@/lib/text";
import { useEngine } from "./EngineProvider";
import { Eyebrow, Muted } from "./ui";

// "Recently created": the engine's newest creatives, or the showcase's when the engine is offline.

export interface RecentItem {
  id: string;
  n: number;
  prompt: string;
  poster: string; // a full URL
  length_s?: number;
  when: string;
  versions: number;
  href: string;
}

const CACHE = new Map<string, Promise<RecentItem[]>>();

async function load(status: string, conn: EngineConn, source: MediaSource): Promise<RecentItem[]> {
  let items: RecentItem[] = [];
  if (status === "online") {
    try {
      const list = (await engineGet<CreativeSummary[]>(conn, "/api/creatives")).slice(0, 4);
      items = list.map((c) => ({
        id: c.id,
        n: c.last,
        prompt: c.prompt,
        poster: source.media(posterOf(c.id, c.last)),
        when: idTime(c.id),
        versions: c.versions,
        href: `/edit?c=${encodeURIComponent(c.id)}&v=${c.last}`,
      }));
      // the length is on the version: one small read each
      const lengths = await Promise.all(
        list.map((c) =>
          engineGet<Version[]>(conn, `/api/creatives/${encodeURIComponent(c.id)}`)
            .then((vs) => vs.find((v) => v.n === c.last)?.length_s)
            .catch(() => undefined),
        ),
      );
      items = items.map((it, i) => ({ ...it, length_s: lengths[i] }));
    } catch {
      items = [];
    }
  }
  if (!items.length) {
    const ix = await fetchIndex();
    items = ix.creatives.slice(0, 4).map((c) => {
      const last = c.versions[c.versions.length - 1];
      return {
        id: c.id,
        n: last?.n ?? 1,
        prompt: c.title,
        poster: last ? `/showcase/${last.poster}` : "",
        length_s: last?.length_s,
        when: "Showcase",
        versions: c.versions.length,
        href: `/showcase/${encodeURIComponent(c.id)}`,
      };
    });
  }
  return items;
}

export function useRecent(count: number, nonce = 0): { items: RecentItem[] | null; live: boolean } {
  const { status, conn, source } = useEngine();
  const [state, setState] = useState<{ key: string; items: RecentItem[] } | null>(null);
  const key = `${status}:${nonce}`;
  useEffect(() => {
    if (status === "checking") return;
    let live = true;
    // one read per state change, shared by the preview poster and the list
    const cacheKey = `${key}:${conn.url}:${conn.direct}`;
    let job = CACHE.get(cacheKey);
    if (!job) {
      job = load(status, conn, source);
      CACHE.set(cacheKey, job);
      setTimeout(() => CACHE.delete(cacheKey), 30_000); // fresh again on a later visit
    }
    job.then((all) => {
      const items = all.slice(0, count);
      if (live) setState({ key, items });
    });
    return () => {
      live = false;
    };
  }, [status, conn, source, count, key]);
  return { items: state && state.key === key ? state.items : null, live: status === "online" };
}

export default function Recent({ nonce = 0 }: { nonce?: number }) {
  const { items, live } = useRecent(4, nonce);
  return (
    <section aria-labelledby="recent-title" className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h2 id="recent-title">
            <Eyebrow>{live ? "Recently created" : "From the showcase"}</Eyebrow>
          </h2>
          {items ? (
            <span className="rounded-full bg-surface-container-high px-2 py-0.5 font-mono text-code-sm text-on-surface-variant">{items.length}</span>
          ) : null}
        </div>
        <Link href={live ? "/edit" : "/showcase"} className="inline-flex min-h-10 items-center gap-1 text-label-md font-semibold text-primary hover:underline">
          View all <ArrowRight aria-hidden className="size-4" />
        </Link>
      </div>
      {items === null ? (
        <ul className="flex flex-col gap-3" aria-hidden>
          {[0, 1, 2].map((i) => (
            <li key={i} className="h-[6.5rem] animate-pulse rounded-2xl bg-surface-container-lowest shadow-sm" />
          ))}
        </ul>
      ) : !items.length ? (
        <Muted>Nothing made yet.</Muted>
      ) : (
        <ul className="flex flex-col gap-3">
          {items.map((it) => (
            <li key={it.id}>
              <Link
                href={it.href}
                className="group flex items-center justify-between gap-3 rounded-2xl bg-surface-container-lowest p-3 shadow-sm transition-shadow hover:shadow-md"
              >
                <span className="flex min-w-0 items-center gap-3.5">
                  <span className="relative h-20 w-[2.8125rem] shrink-0 overflow-hidden rounded-xl bg-inverse-surface">
                    {it.poster ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={it.poster} alt="" loading="lazy" className="h-full w-full object-cover transition-transform group-hover:scale-105" />
                    ) : null}
                    {it.length_s ? (
                      <span className="absolute bottom-1 right-1 rounded bg-black/70 px-1 font-mono text-[10px] text-white">{Math.round(it.length_s)}s</span>
                    ) : null}
                  </span>
                  <span className="flex min-w-0 flex-col gap-1">
                    <span className="line-clamp-2 text-label-md font-semibold text-on-surface">{truncate(it.prompt, 120)}</span>
                    <span className="text-body-sm text-outline">
                      {it.when}
                      {it.versions > 1 ? ` · ${it.versions} versions` : ""}
                    </span>
                  </span>
                </span>
                <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-surface-container-low text-on-surface transition-colors group-hover:bg-primary-container group-hover:text-on-primary">
                  <SquarePen aria-hidden className="size-[18px]" />
                  <span className="sr-only">{live ? "Open in the Edit workspace" : "Open in the showcase"}</span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
