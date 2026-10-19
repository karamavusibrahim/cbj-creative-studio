"use client";

import { ArrowLeft, FileClock, Loader2, SquarePen } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { catalogueSource, fetchCatalogueDetail, type CatalogueDetail } from "@/lib/catalogue";
import { engineGet, showcaseSource } from "@/lib/engine";
import type { ShowcaseDetail as Detail } from "@/lib/types";
import { KIND_WORDS } from "@/lib/words";
import { useEngine } from "../EngineProvider";
import EditReport from "../EditReport";
import VersionGameplay from "../Gameplay";
import { Pair, PhoneFrame, VersionVideo } from "../Player";
import ReferenceCard from "../ReferenceCard";
import ReviewCard from "../ReviewCard";
import { PinnedSource } from "../SourceProvider";
import Understood from "../Understood";
import FeedbackPanel, { FeedbackPanelProvider } from "../FeedbackPanel";
import { DownloadLink, VersionFacts, VersionLinks, versionLine } from "../VersionBits";
import { Badge, Card, CardTitle, Muted, cx } from "../ui";

// One showcase creative with its full evidence, version by version. Works with the engine offline. A catalogue creative
// (SPEC-R2-CATALOGUE) is the same page fed from the R2 bucket, its media and files read from there even with the engine
// online (the engine may not hold it any more).

export default function ShowcaseDetail({ detail, catalogue = false }: { detail: Detail; catalogue?: boolean }) {
  const { status, meta, conn } = useEngine();
  const versions = detail.versions;
  const [n, setN] = useState(versions[versions.length - 1]?.n);
  // whether the engine holds this creative (the showcase ids are studio ids; an engine elsewhere may not have it)
  const [held, setHeld] = useState<{ url: string; ok: boolean } | null>(null);

  useEffect(() => {
    if (status !== "online") return;
    let live = true;
    engineGet<unknown[]>(conn, `/api/creatives/${encodeURIComponent(detail.id)}`)
      .then((vs) => live && setHeld({ url: conn.url, ok: Array.isArray(vs) && vs.length > 0 }))
      .catch(() => live && setHeld({ url: conn.url, ok: false }));
    return () => {
      live = false;
    };
  }, [status, conn, detail.id]);

  useEffect(() => {
    // ?v=<n> opens a given version
    const want = Number(new URLSearchParams(window.location.search).get("v"));
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (want && versions.some((x) => x.n === want)) setN(want);
  }, [versions]);

  const v = versions.find((x) => x.n === n) || versions[versions.length - 1];
  if (!v) return null;
  const engineHolds = status === "online" && held?.url === conn.url && held.ok;
  const prev = v.edit ? versions.find((x) => x.n === (v.from ?? v.n - 1)) || null : null;

  function pick(k: number) {
    setN(k);
    window.history.replaceState(null, "", `?v=${k}`);
  }

  return (
    <PinnedSource source={catalogue ? catalogueSource() : showcaseSource()}>
      <div className="mb-6 flex flex-col gap-4">
        <Link href="/showcase" className="inline-flex min-h-10 items-center gap-1.5 self-start text-label-md font-semibold text-primary hover:underline">
          <ArrowLeft aria-hidden className="size-4" /> All finished creatives
        </Link>
        <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
          <div className="flex flex-col gap-1">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone="violet" className="uppercase tracking-wider">
                {KIND_WORDS[detail.kind] || detail.kind}
              </Badge>
              <span className="text-label-sm text-outline">{catalogue ? "Catalogue" : "Showcase"} · exported from the studio</span>
            </div>
            <h1 className="font-headline text-headline-xl-mobile text-on-surface sm:text-headline-xl">{detail.title}</h1>
            <p className="max-w-3xl text-body-md text-on-surface-variant">{detail.tagline}</p>
          </div>
          {engineHolds ? (
            <Link
              href={`/edit?c=${encodeURIComponent(detail.id)}&v=${v.n}`}
              className="inline-flex min-h-10 shrink-0 items-center gap-2 self-start rounded-xl bg-primary-container px-4 py-2 text-label-md font-semibold text-on-primary shadow-sm hover:bg-primary md:self-auto"
            >
              <SquarePen aria-hidden className="size-[18px]" /> Open in the Edit workspace
            </Link>
          ) : null}
        </div>
      </div>

      {versions.length > 1 ? (
        <div role="tablist" aria-label="Versions" className="mb-6 flex gap-1.5 overflow-x-auto pb-1">
          {versions.map((x) => (
            <button
              key={x.n}
              type="button"
              role="tab"
              aria-selected={x.n === v.n}
              onClick={() => pick(x.n)}
              title={x.prompt}
              className={cx(
                "min-h-10 shrink-0 whitespace-nowrap rounded-full px-4 text-label-md transition-all",
                x.n === v.n ? "bg-primary-container font-semibold text-on-primary shadow-sm" : "bg-surface-container text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface",
              )}
            >
              v{x.n}
              {x.edit ? <span className="opacity-75"> ← v{x.from ?? x.n - 1}</span> : null}
            </button>
          ))}
        </div>
      ) : null}

      <FeedbackPanelProvider
        context={{ page: "showcase", creative_id: detail.id, version: v.n, title: detail.title, workflow: v.workflow || (v.edit ? "edit" : "create") }}
        edit={Boolean(v.edit)}
        unavailable={!engineHolds}
      >
      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-12 lg:gap-8">
        {/* not sticky: the feedback panel under the player can be taller than the window */}
        <div className="flex min-w-0 flex-col gap-6 lg:col-span-5">
          <Card label="Creative" className="flex flex-col items-center">
            <PhoneFrame label={`v${v.n}`}>
              <VersionVideo v={v} />
            </PhoneFrame>
            <div className="mt-5 w-full">
              <VersionFacts v={v} />
              <p className="mt-3 text-body-md text-on-surface">
                <b>v{v.n} prompt:</b> {v.prompt}
              </p>
              <p className="mt-2 text-body-sm text-on-surface-variant">{versionLine(v)}</p>
              <div className="mt-4 flex flex-wrap items-center gap-3">
                <DownloadLink v={v} />
              </div>
              <VersionLinks v={v} />
            </div>
          </Card>
          <FeedbackPanel />
        </div>
        <div className="flex min-w-0 flex-col gap-6 lg:col-span-7">
          {prev ? (
            <Card label="Before and after">
              <CardTitle icon={FileClock}>
                What v{v.n} changed from v{prev.n}
              </CardTitle>
              <Pair before={prev} after={v} />
              {v.proof ? (
                <div className="mt-6">
                  <EditReport pr={v.proof} />
                </div>
              ) : null}
            </Card>
          ) : v.edit && v.proof ? (
            <Card label="Edit report">
              <CardTitle icon={FileClock}>What v{v.n} changed from v{v.from ?? v.n - 1}</CardTitle>
              <EditReport pr={v.proof} />
            </Card>
          ) : null}
          {v.brief ? <Understood brief={v.brief} meta={meta} title={`Brief of v${v.n}, after the engine's checks`} /> : null}
          {v.brief ? <ReferenceCard brief={v.brief} /> : null}
          <VersionGameplay v={v} />
          <ReviewCard v={v} />
        </div>
      </div>
      </FeedbackPanelProvider>
    </PinnedSource>
  );
}

/** A creative that is not one of the curated ten: read from the catalogue in the browser. */
export function CatalogueCreative({ id }: { id: string }) {
  const [got, setGot] = useState<{ id: string; answer: CatalogueDetail } | null>(null);
  useEffect(() => {
    let live = true;
    void fetchCatalogueDetail(id).then((answer) => live && setGot({ id, answer }));
    return () => {
      live = false;
    };
  }, [id]);
  const answer = got?.id === id ? got.answer : null;
  if (answer?.state === "ok") return <ShowcaseDetail detail={answer.detail} catalogue />;
  return (
    <div className="flex flex-col gap-4">
      <Link href="/showcase" className="inline-flex min-h-10 items-center gap-1.5 self-start text-label-md font-semibold text-primary hover:underline">
        <ArrowLeft aria-hidden className="size-4" /> All finished creatives
      </Link>
      {!answer ? (
        <p role="status" className="inline-flex items-center gap-2 text-body-md text-on-surface-variant">
          <Loader2 aria-hidden className="size-4 animate-spin motion-reduce:animate-none" /> Loading from the catalogue…
        </p>
      ) : (
        <div role="status" className="flex flex-col gap-1">
          <h1 className="font-headline text-headline-xl-mobile text-on-surface sm:text-headline-xl">
            {answer.state === "missing" ? "Not in the catalogue" : "The catalogue could not be reached"}
          </h1>
          <Muted>
            {answer.state === "missing"
              ? `No finished creative “${id}” is published there.`
              : "Try again in a moment; the curated creatives are always on the showcase."}
          </Muted>
        </div>
      )}
    </div>
  );
}
