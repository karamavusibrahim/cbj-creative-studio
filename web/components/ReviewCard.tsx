"use client";

import { ArrowRight, Eye } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import type { Review, Version } from "@/lib/types";
import { SCORE_WORDS } from "@/lib/words";
import { useSource } from "./SourceProvider";
import { FlagButton } from "./FeedbackPanel";
import { Badge, Button, Card, CardTitle, Muted, type Tone } from "./ui";

// "As a viewer" (renderReview): a multimodal model watches the finished ad as a person scrolling a feed.

const MEASURED = new Set(["first_second", "dead_time"]);

function scoreTone(n: number): Tone {
  return n >= 4 ? "mint" : n === 3 ? "grey" : "amber";
}

export function useReview(v: Version | null, override?: Review | null, of?: number): { review: Review | null; loaded: boolean } {
  const source = useSource();
  const [state, setState] = useState<{ key: string; review: Review | null } | null>(null);
  const n = of ?? v?.n;
  const key = v ? `${source.live}:${v.id}:${n}` : "";
  // another version's review (`of`) is always read from its file: the inline one, if any, is this version's
  const inline = of === undefined ? v?.review : undefined;
  const id = v?.id;
  useEffect(() => {
    if (!id || inline !== undefined) return;
    let live = true;
    source.json<Review>(`${id}/v${n}/review.json`).then((r) => {
      if (live) setState({ key, review: r });
    });
    return () => {
      live = false;
    };
  }, [source, id, n, key, inline]);
  if (override) return { review: override, loaded: true };
  if (!v) return { review: null, loaded: false };
  if (inline !== undefined) return { review: inline ?? null, loaded: true };
  return state && state.key === key ? { review: state.review, loaded: true } : { review: null, loaded: false };
}

export function reviewLine(rev: Review | null): string {
  if (!rev || rev.error || !rev.overall) return "";
  const bad = (rev.match || []).filter((m) => m.verdict === "no" || m.verdict === "partial");
  return `As a viewer: ${rev.overall === "ship" ? "ready to ship" : "worth a fix"} · would download: ${rev.would_download}${
    bad.length ? ` · not as asked: ${bad.map((m) => `${m.control} (${m.verdict})`).join(", ")}` : ""
  }`;
}

export default function ReviewCard({
  v,
  override,
  reviewOf,
  onRun,
  running,
  disabled,
}: {
  v: Version;
  override?: Review | null;
  /** show the review of this version of the same creative (a make with audio: the version before the music edit) */
  reviewOf?: number;
  onRun?: () => void;
  running?: boolean;
  disabled?: boolean;
}) {
  const source = useSource();
  const { review: rev, loaded } = useReview(v, override, reviewOf);
  const reviewed = reviewOf ?? v.n;
  const runButton = onRun ? (
    <Button size="sm" variant="ghost" icon={Eye} onClick={onRun} disabled={disabled || running}>
      {running ? "Reviewing…" : rev && !rev.error ? "Review again" : "Review this version"}
    </Button>
  ) : null;

  let body: React.ReactNode;
  if (!loaded) body = <Muted>Loading the review…</Muted>;
  else if (!rev || rev.error || !rev.viewer) {
    body = (
      <Muted>
        {rev?.error
          ? `The review failed: ${rev.error}`
          : onRun
            ? "Not reviewed yet. Press \"Review this version\": a multimodal model watches the finished ad as a person scrolling a feed and says whether it matches the prompt and whether they would tap."
            : "This version was not reviewed as a viewer."}
      </Muted>
    );
  } else {
    const f = rev.facts || {};
    body = (
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={rev.overall === "ship" ? "mint" : "amber"} className="!text-label-md">
            {rev.overall === "ship" ? "Ready to ship" : "Worth a fix"}
          </Badge>
          <span className="text-body-md">
            would download: <b>{rev.would_download}</b>
          </span>
        </div>
        {rev.why ? <p className="text-body-md text-on-surface">{rev.why}</p> : null}
        <ul className="grid grid-cols-2 gap-2 @md:grid-cols-3" aria-label="Viewer scores, out of 5">
          {Object.entries(rev.viewer || {}).map(([k, n]) => (
            <li key={k} className="flex flex-col rounded-xl bg-surface-container-low px-3 py-2">
              <span className="text-label-sm text-on-surface-variant">{SCORE_WORDS[k] || k}</span>
              <span className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-0.5">
                <span className="font-headline text-headline-md text-on-surface">
                  {n}
                  <span className="text-label-sm text-outline">/5</span>
                </span>
                <Badge tone={scoreTone(n)} className="!px-2 !text-[10.5px]">
                  {MEASURED.has(k) ? "measured" : "model"}
                </Badge>
              </span>
            </li>
          ))}
        </ul>
        <Muted>
          Measured: the game first moves at {f.first_move_s} s; held screens {Math.round((f.static_share || 0) * 100)}% of {f.length_s} s
          {(f.captions || []).some((c) => !c.readable) ? "; a caption is on screen for less than its reading time" : ""}. Reviewed by {rev.model} in {rev.seconds} s.
        </Muted>
        {rev.match?.length ? (
          <div>
            <h3 className="mb-2 text-label-md font-semibold">Does it match the request?</h3>
            <ul className="flex flex-col divide-y divide-surface-variant overflow-hidden rounded-xl ring-1 ring-surface-variant">
              {rev.match.map((m, i) => (
                <li key={i} className="grid grid-cols-[auto_1fr] gap-3 px-3 py-2.5">
                  <Badge tone={m.verdict === "match" ? "mint" : m.verdict === "not asked" ? "grey" : "amber"} className="self-start">{m.verdict}</Badge>
                  <div className="min-w-0">
                    <span className="flex items-start gap-1">
                      <b className="text-body-md">{m.control}</b>
                      {m.verdict === "no" || m.verdict === "partial" ? <FlagButton title={m.control} step="review" className="-my-1.5" /> : null}
                    </span>
                    <p className="text-body-sm text-on-surface-variant">{m.seen}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {rev.fixes?.length ? (
          <div>
            <h3 className="mb-1 text-label-md font-semibold">Fixes, best first</h3>
            <ol className="flex list-decimal flex-col gap-1 pl-5 text-body-md">
              {rev.fixes.map((x, i) => (
                <li key={i}>{x}</li>
              ))}
            </ol>
          </div>
        ) : null}
        {rev.suggested_edit ? (
          <div className="rounded-xl bg-surface-container-low p-3">
            <p className="text-body-md">
              <b>Suggested edit:</b> {rev.suggested_edit}
            </p>
            {source.live ? (
              <Link
                href={`/edit?c=${encodeURIComponent(v.id)}&v=${v.n}&prompt=${encodeURIComponent(rev.suggested_edit)}`}
                className="mt-2 inline-flex min-h-10 items-center gap-1 text-label-md font-semibold text-primary hover:underline"
              >
                Use it as the next edit <ArrowRight aria-hidden className="size-4" />
              </Link>
            ) : null}
          </div>
        ) : null}
        <div className="flex flex-wrap gap-4 text-label-sm">
          {rev.sheet ? (
            <a className="font-semibold text-primary hover:underline" href={source.link(rev.sheet)} target="_blank" rel="noreferrer">
              Contact sheet
            </a>
          ) : null}
          {source.live ? (
            <a className="font-semibold text-primary hover:underline" href={source.link(`${v.id}/v${reviewed}/review.json`)} target="_blank" rel="noreferrer">
              review.json
            </a>
          ) : null}
        </div>
      </div>
    );
  }
  return (
    <Card label="As a viewer">
      <CardTitle icon={Eye} tone="secondary" right={runButton}>
        As a viewer
      </CardTitle>
      {reviewOf !== undefined && reviewOf !== v.n ? (
        <p className="-mt-2 mb-3 text-body-sm text-on-surface-variant">Reviewed as v{reviewOf}, before the audio was added (the audio edit kept every frame)</p>
      ) : null}
      {body}
    </Card>
  );
}
