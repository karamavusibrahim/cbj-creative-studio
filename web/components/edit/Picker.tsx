"use client";

import { Search } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { engineGet, idTime, posterOf } from "@/lib/engine";
import { fetchIndex } from "@/lib/showcase";
import type { CreativeSummary } from "@/lib/types";
import { truncate } from "@/lib/text";
import { useEngine } from "../EngineProvider";
import { Muted, cx } from "../ui";

// Choosing a creative to edit: the engine's creatives (newest first, a page at a time), or the
// showcase's when the engine is offline (read-only).

interface Row {
  id: string;
  prompt: string;
  versions: number;
  last: number;
  poster: string;
  when: string;
}

const PAGE = 24;

export default function Picker({ current, onPick, compact }: { current?: string; onPick?: () => void; compact?: boolean }) {
  const { status, conn, source } = useEngine();
  const [rows, setRows] = useState<{ key: string; rows: Row[] } | null>(null);
  const [q, setQ] = useState("");
  const [shown, setShown] = useState(PAGE);
  const key = status;

  useEffect(() => {
    if (status === "checking") return;
    let live = true;
    (async () => {
      let out: Row[] = [];
      if (status === "online") {
        try {
          const list = await engineGet<CreativeSummary[]>(conn, "/api/creatives");
          out = list.map((c) => ({ id: c.id, prompt: c.prompt, versions: c.versions, last: c.last, poster: source.media(posterOf(c.id, c.last)), when: idTime(c.id) }));
        } catch {
          out = [];
        }
      } else {
        const ix = await fetchIndex();
        out = ix.creatives.map((c) => {
          const last = c.versions[c.versions.length - 1];
          return { id: c.id, prompt: c.title, versions: c.versions.length, last: last?.n ?? 1, poster: last ? `/showcase/${last.poster}` : "", when: "Showcase" };
        });
      }
      if (live) setRows({ key, rows: out });
    })();
    return () => {
      live = false;
    };
  }, [status, conn, source, key]);

  const list = rows && rows.key === key ? rows.rows : null;
  const filtered = useMemo(() => {
    if (!list) return null;
    const w = q.trim().toLowerCase();
    return w ? list.filter((r) => r.prompt.toLowerCase().includes(w) || r.id.includes(w)) : list;
  }, [list, q]);

  return (
    <div className="flex flex-col gap-3">
      <label className="relative block">
        <span className="sr-only">Search creatives</span>
        <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-outline" />
        <input
          type="search"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setShown(PAGE);
          }}
          placeholder={status === "online" ? `Search ${list?.length ?? ""} creatives by their prompt` : "Search the showcase"}
          className="min-h-11 w-full rounded-xl bg-surface-container-low pl-9 pr-3 text-body-md outline-none ring-1 ring-outline-variant/40 focus:ring-2 focus:ring-primary-container"
        />
      </label>
      {status === "offline" ? <Muted>The engine is offline: these are the showcase&apos;s creatives, read-only.</Muted> : null}
      {filtered === null ? (
        <ul className={cx("grid gap-3", compact ? "grid-cols-1" : "sm:grid-cols-2 xl:grid-cols-3")} aria-hidden>
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <li key={i} className="h-24 animate-pulse rounded-2xl bg-surface-container-lowest shadow-sm" />
          ))}
        </ul>
      ) : !filtered.length ? (
        <Muted>{q ? "No creative matches." : "No creatives yet."}</Muted>
      ) : (
        <>
          <ul className={cx("grid gap-3", compact ? "grid-cols-1" : "sm:grid-cols-2 xl:grid-cols-3")}>
            {filtered.slice(0, shown).map((r) => (
              <li key={r.id}>
                <Link
                  href={`/edit?c=${encodeURIComponent(r.id)}&v=${r.last}`}
                  onClick={onPick}
                  aria-current={r.id === current ? "true" : undefined}
                  className={cx(
                    "group flex items-center gap-3.5 rounded-2xl bg-surface-container-lowest p-3 shadow-sm transition-shadow hover:shadow-md",
                    r.id === current && "ring-2 ring-primary-container/50",
                  )}
                >
                  <span className="h-[4.5rem] w-[2.53rem] shrink-0 overflow-hidden rounded-lg bg-inverse-surface">
                    {r.poster ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={r.poster} alt="" loading="lazy" className="h-full w-full object-cover" onError={(e) => (e.currentTarget.style.visibility = "hidden")} />
                    ) : null}
                  </span>
                  <span className="flex min-w-0 flex-col gap-1">
                    <span className="line-clamp-2 text-label-md font-semibold text-on-surface">{truncate(r.prompt, 140)}</span>
                    <span className="text-body-sm text-outline">
                      {r.when} · {r.versions} version{r.versions > 1 ? "s" : ""}
                    </span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
          {filtered.length > shown ? (
            <button
              type="button"
              onClick={() => setShown(shown + PAGE)}
              className="mx-auto min-h-10 rounded-xl bg-surface-container-high px-4 text-label-md font-semibold text-on-surface hover:bg-surface-variant"
            >
              Show more ({filtered.length - shown} left)
            </button>
          ) : null}
        </>
      )}
    </div>
  );
}
