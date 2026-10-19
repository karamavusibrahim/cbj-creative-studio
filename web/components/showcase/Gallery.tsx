"use client";

import { Clock, CloudDownload, Eye, Layers } from "lucide-react";
import Link from "next/link";
import { motion, useReducedMotion } from "motion/react";
import { useEffect, useMemo, useState } from "react";
import { catalogueMedia, catalogueOn, fetchCatalogue, mergeCatalogue, type CatalogueEntry } from "@/lib/catalogue";
import type { ShowcaseIndex, ShowcaseIndexEntry } from "@/lib/types";
import { KIND_WORDS, WORKFLOW_WORDS } from "@/lib/words";
import { Badge, Muted, cx } from "../ui";

// The showcase gallery: real outputs of this tool, exported with their evidence. The curated ones (the static export) at
// once; then, when NEXT_PUBLIC_CATALOGUE_URL is set, the catalogue's others from the R2 bucket (SPEC-R2-CATALOGUE).

const FILTERS = [
  { id: "all", label: "All" },
  { id: "text", label: "Text" },
  { id: "image", label: "Image reference" },
  { id: "video", label: "Video reference" },
  { id: "edits", label: "Edits" },
] as const;

type Filter = (typeof FILTERS)[number]["id"];

function matches(c: ShowcaseIndexEntry, f: Filter): boolean {
  if (f === "all") return true;
  if (f === "text") return c.kind === "create";
  if (f === "image") return c.kind === "image_guided";
  if (f === "video") return c.kind === "guided";
  return c.kind === "edit" || c.kind === "edit-ladder" || c.versions.some((v) => v.edit);
}

/** "loading" until the catalogue answers; null: off or unreachable (the static showcase alone). */
type More = ShowcaseIndexEntry[] | "loading" | null;

export default function Gallery({ index }: { index: ShowcaseIndex }) {
  const [filter, setFilter] = useState<Filter>("all");
  const reduce = useReducedMotion();
  const [more, setMore] = useState<More>(() => (catalogueOn() ? "loading" : null));
  useEffect(() => {
    if (!catalogueOn()) return;
    let live = true;
    void fetchCatalogue().then((c) => live && setMore(c));
    return () => {
      live = false;
    };
  }, []);
  const all: CatalogueEntry[] = useMemo(() => mergeCatalogue(index.creatives, Array.isArray(more) ? more : []), [index.creatives, more]);
  const extra = all.length - index.creatives.length;
  const list = all.filter((c) => matches(c, filter));
  return (
    <div>
      <div className="mb-6 flex flex-col gap-1">
        <h1 className="font-headline text-headline-xl-mobile text-on-surface sm:text-headline-xl">Finished creatives</h1>
        <p className="max-w-3xl text-body-md text-on-surface-variant">
          Real outputs of this tool, exported with their evidence: the prompt, what the planner understood, the level and the moves, the checks
          measured from the recording, the viewer&apos;s review and, for edits, the report of what changed. The videos are 720p web copies.
        </p>
        <p aria-live="polite" className="text-label-md font-semibold text-on-surface">
          {index.creatives.length} curated
          {more === "loading" ? <span className="font-normal text-on-surface-variant"> · loading the catalogue…</span> : extra > 0 ? ` · ${extra} more in the catalogue` : null}
        </p>
      </div>
      <div role="group" aria-label="Filter by kind" className="mb-6 flex flex-wrap gap-2">
        {FILTERS.map((f) => {
          const n = all.filter((c) => matches(c, f.id)).length;
          return (
            <button
              key={f.id}
              type="button"
              aria-pressed={filter === f.id}
              onClick={() => setFilter(f.id)}
              className={cx(
                "inline-flex min-h-10 items-center gap-1.5 rounded-full px-4 text-label-md transition-all",
                filter === f.id ? "bg-primary-container font-semibold text-on-primary shadow-sm" : "bg-surface-container text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface",
              )}
            >
              {f.label}
              <span className={cx("text-label-sm", filter === f.id ? "text-on-primary/80" : "text-outline")}>{n}</span>
            </button>
          );
        })}
      </div>
      {!all.length ? (
        <Muted>The showcase has not been exported yet.</Muted>
      ) : !list.length ? (
        <Muted>Nothing of this kind in the showcase.</Muted>
      ) : (
        <ul className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {list.map((c, i) => {
            const last = c.versions[c.versions.length - 1];
            const first = c.versions[0];
            const reviewed = [...c.versions].reverse().find((v) => v.review_overall);
            const poster = last ? (c.catalogue ? catalogueMedia(last.poster) : `/showcase/${last.poster}`) : "";
            return (
              <motion.li
                key={c.id}
                initial={reduce ? false : { opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: reduce ? 0 : Math.min(i, 8) * 0.04 }}
              >
                <Link
                  href={`/showcase/${encodeURIComponent(c.id)}`}
                  prefetch={c.catalogue ? false : undefined}
                  className="group flex h-full flex-col overflow-hidden rounded-2xl bg-surface-container-lowest shadow-sm transition-shadow hover:shadow-md"
                >
                  <span className="relative block aspect-[9/16] max-h-[440px] w-full overflow-hidden bg-inverse-surface">
                    {last ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={poster}
                        alt={`Poster of “${c.title}”`}
                        loading="lazy"
                        className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
                      />
                    ) : null}
                    <span className="absolute bottom-3 left-3 rounded-full bg-black/60 px-2.5 py-0.5 text-label-sm text-white backdrop-blur-md">
                      {KIND_WORDS[c.kind] || c.kind}
                    </span>
                    {c.catalogue ? (
                      <span
                        title="From the catalogue: published to the bucket, not part of the curated ten"
                        className="absolute bottom-3 right-3 inline-flex items-center gap-1 rounded-full bg-surface-container-lowest/90 px-2.5 py-0.5 text-label-sm font-semibold text-on-surface shadow-sm backdrop-blur-md"
                      >
                        <CloudDownload aria-hidden className="size-3" />
                        catalogue
                      </span>
                    ) : null}
                  </span>
                  <span className="flex flex-1 flex-col gap-2 p-4">
                    <span className="text-title-sm text-on-surface">{c.title}</span>
                    <span className="line-clamp-3 text-body-sm text-on-surface-variant">{c.tagline}</span>
                    <span className="mt-auto flex flex-wrap gap-1.5 pt-2">
                      <Badge tone="grey">
                        <Layers aria-hidden className="size-3" />
                        {c.versions.length} version{c.versions.length > 1 ? "s" : ""}
                      </Badge>
                      {last ? (
                        <Badge tone="grey">
                          <Clock aria-hidden className="size-3" />
                          {Math.round(last.length_s)} s
                        </Badge>
                      ) : null}
                      {first?.workflow ? <Badge tone="sky">{WORKFLOW_WORDS[first.workflow] || first.workflow}</Badge> : null}
                      {reviewed ? (
                        <Badge tone={reviewed.review_overall === "ship" ? "mint" : "amber"}>
                          <Eye aria-hidden className="size-3" />
                          {reviewed.review_overall === "ship" ? "ready to ship" : "worth a fix"}
                        </Badge>
                      ) : null}
                    </span>
                  </span>
                </Link>
              </motion.li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
