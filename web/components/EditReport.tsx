"use client";

import { Ban, CheckCircle2, Lock, PencilLine, XCircle } from "lucide-react";
import type { Proof } from "@/lib/types";
import { numText } from "@/lib/text";
import { CHECKLIST, ROUTE_TYPES, ROW_STATUS } from "@/lib/words";
import { FlagButton } from "./FeedbackPanel";
import { Badge, Muted, cx, type Tone } from "./ui";

// The edit report (renderProof): the verdict, the contract in three words (Locked / Allowed / Forbidden),
// the checklist with its evidence, the rows item by item, the pixel facts.

const ROW_TONE: Record<string, Tone> = { kept: "mint", asked: "sky", side_effect: "amber", not_asked: "error", changed: "sky" };

function pixelsLine(pr: Proof): string {
  const px = pr.pixels || {};
  if (px.frames_changed === undefined) return px.note || "";
  const ranges = (px.ranges || []).map((r) => (r[0] === r[1] ? `${r[0]}` : `${r[0]}-${r[1]}`)).join(", ");
  return (
    `${px.frames_changed} of ${px.frames} frames changed${ranges ? ` (${ranges})` : ""}` +
    (px.contained === true
      ? "; every changed pixel is inside the changed layers' boxes"
      : px.contained === false
        ? "; SOME CHANGED PIXELS ARE OUTSIDE THE CHANGED LAYERS"
        : "") +
    (px.note ? `; ${px.note}` : "")
  );
}

function Contract({ pr }: { pr: Proof }) {
  const rows = pr.rows || [];
  const locked = rows.filter((r) => r.status === "kept").map((r) => r.title);
  const asked = rows.filter((r) => r.status === "asked").map((r) => r.title);
  const side = rows.filter((r) => r.status === "side_effect").map((r) => r.title);
  const forbidden = rows.filter((r) => r.status === "not_asked").map((r) => r.title);
  const cell = (icon: React.ReactNode, word: string, sub: string, body: React.ReactNode, cls: string) => (
    <div className={cx("flex min-w-0 flex-col gap-1 rounded-xl p-3", cls)}>
      <span className="flex items-center gap-1.5 text-label-md font-bold">
        {icon}
        {word}
      </span>
      <span className="text-[11px] leading-tight opacity-80">{sub}</span>
      <div className="text-body-sm">{body}</div>
    </div>
  );
  return (
    <div className="grid gap-2 @lg:grid-cols-3">
      {cell(<Lock aria-hidden className="size-4" />, "Locked", "kept as it was", locked.join(", ") || "nothing", "bg-tertiary-fixed/25 text-tertiary")}
      {cell(
        <PencilLine aria-hidden className="size-4" />,
        "Allowed",
        "changed, as asked (and because of it)",
        <>
          {asked.join(", ") || "nothing"}
          {side.length ? <span className="block opacity-80">because of it: {side.join(", ")}</span> : null}
        </>,
        "bg-secondary-fixed/50 text-on-secondary-fixed",
      )}
      {cell(
        <Ban aria-hidden className="size-4" />,
        "Forbidden",
        "changed without being asked",
        forbidden.length ? <b>{forbidden.join(", ")}</b> : "none",
        forbidden.length ? "bg-error-container text-on-error-container" : "bg-surface-container-low text-on-surface-variant",
      )}
    </div>
  );
}

export default function EditReport({
  pr,
  compact = false,
  rows: withRows = true,
  flags = true,
}: {
  pr: Proof;
  compact?: boolean;
  /** false: only the verdict and the Locked / Allowed / Forbidden contract (the designer's view) */
  rows?: boolean;
  /** the rows' "about this row" flags (off for a comparison: it is no version's own report) */
  flags?: boolean;
}) {
  if (!pr.rows && !withRows) return pr.verdict ? <p className="text-body-md font-semibold text-on-surface">{pr.verdict}</p> : <Muted>Asked to change: {(pr.changed_controls || []).join(", ") || "nothing"}</Muted>;
  if (!pr.rows) {
    // a version made before the edit report existed
    const items: [string, string | undefined][] = [
      ["Asked to change", (pr.changed_controls || []).join(", ") || "nothing"],
      ["Gameplay", pr.gameplay],
      ["Frames", pr.frames],
      ["Pixels", typeof pr.pixels === "string" ? pr.pixels : undefined],
    ];
    return (
      <dl className="grid grid-cols-[8rem_1fr] gap-x-3 gap-y-1 text-body-md">
        {items
          .filter(([, x]) => x)
          .map(([k, x]) => (
            <div key={k} className="contents">
              <dt className="text-on-surface-variant">{k}</dt>
              <dd>{x}</dd>
            </div>
          ))}
      </dl>
    );
  }
  const compare = pr.rows.some((r) => r.status === "changed");
  const px = pixelsLine(pr);
  const verdict = pr.verdict ? (
    <p className={cx("flex items-start gap-2 text-body-md font-semibold", pr.ok === false ? "text-error" : "text-tertiary")}>
      {pr.ok === false ? <XCircle aria-hidden className="mt-0.5 size-4 shrink-0" /> : <CheckCircle2 aria-hidden className="mt-0.5 size-4 shrink-0" />}
      {pr.verdict}
    </p>
  ) : null;
  if (!withRows) {
    return (
      <div className="flex flex-col gap-4">
        {verdict}
        {!compare ? <Contract pr={pr} /> : null}
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-4">
      {verdict}
      {!compare ? <Contract pr={pr} /> : null}
      {pr.checklist || pr.route ? (
        <div>
          <p className="mb-1.5 text-label-sm font-semibold uppercase tracking-wider text-outline">Checklist</p>
          <ul className="flex flex-wrap gap-1.5">
            {Object.entries(pr.checklist || {}).map(([k, x]) => (
              <li key={k}>
                <Badge tone={x.ok ? "mint" : "sky"} title={x.evidence || ""}>
                  <span aria-hidden>{x.ok ? "✓" : "≠"}</span> {CHECKLIST[k] || k}
                  <span className="sr-only">{x.ok ? ": the same" : ": changed"}. {x.evidence}</span>
                </Badge>
              </li>
            ))}
            {pr.route ? (
              <li>
                <Badge tone={pr.route.ok ? "mint" : "amber"} title={pr.route.evidence || ""} className="!whitespace-normal">
                  <span aria-hidden>{pr.route.ok ? "✓" : "✗"}</span> route: level {pr.route.level}, {ROUTE_TYPES[pr.route.edit_type || ""] || pr.route.edit_type}
                  <span className="sr-only">. {pr.route.evidence}</span>
                </Badge>
              </li>
            ) : null}
          </ul>
          {!compact ? (
            <details className="mt-2 text-body-sm">
              <summary className="inline-flex min-h-8 items-center text-label-sm font-semibold text-on-surface-variant hover:text-on-surface">Show the evidence</summary>
              <dl className="mt-1 grid grid-cols-[minmax(7rem,auto)_1fr] gap-x-3 gap-y-1 text-on-surface-variant">
                {Object.entries(pr.checklist || {}).map(([k, x]) => (
                  <div key={k} className="contents">
                    <dt className="font-semibold text-on-surface">{CHECKLIST[k] || k}</dt>
                    <dd className="break-words">{x.evidence}</dd>
                  </div>
                ))}
                {pr.route ? (
                  <div className="contents">
                    <dt className="font-semibold text-on-surface">route</dt>
                    <dd className="break-words">{pr.route.evidence}</dd>
                  </div>
                ) : null}
              </dl>
            </details>
          ) : null}
        </div>
      ) : null}
      <ul className="flex flex-col divide-y divide-surface-variant">
        {pr.rows.map((r, i) => (
          <li key={i} className="py-2.5 first:pt-0">
            <div className="flex flex-wrap items-center gap-2">
              <b className="text-body-md">{r.title}</b>
              <Badge tone={ROW_TONE[r.status] || "grey"}>{ROW_STATUS[r.status] || r.status}</Badge>
              {flags ? <FlagButton title={r.title} step="proof" className="-my-1 ml-auto" /> : null}
            </div>
            <p className={cx("mt-0.5 break-words text-body-sm", r.status === "kept" ? "text-on-surface-variant" : "text-on-surface")}>{r.detail}</p>
            {r.numbers ? (
              <p className="mt-0.5 text-body-sm text-on-surface-variant">
                before: {numText(r.numbers.before)}
                <br />
                after: {numText(r.numbers.after)}
              </p>
            ) : null}
            {(r.reasons || []).map((n, j) => (
              <p key={j} className="text-body-sm text-on-surface-variant">
                engine: {n}
              </p>
            ))}
          </li>
        ))}
      </ul>
      {px ? <Muted>Frames: {px}</Muted> : null}
      {pr.changes ? (
        <Muted>
          <b>Changes:</b> {(pr.changes || []).join(", ") || "nothing"}. <b>Preserves:</b> {(pr.preserves || []).join(", ") || "nothing"}.
        </Muted>
      ) : null}
      <Muted>Asked to change: {(pr.asked_names || pr.asked || []).join(", ") || "nothing"}</Muted>
    </div>
  );
}
