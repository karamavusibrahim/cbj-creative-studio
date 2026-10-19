"use client";

import { Paperclip, Route as RouteIcon, ScanSearch } from "lucide-react";
import type { Brief, Meta } from "@/lib/types";
import { briefFacts, refSummary, routeSummary } from "@/lib/text";
import { CONTROL_TITLES } from "@/lib/words";
import { FlagButton } from "./FeedbackPanel";
import { Badge, Button, Card, CardTitle, Fold, Pre, type Tone } from "./ui";

// "What the tool understood" (renderBrief): one row per prompt control with its status.

const CONTROL_TONE: Record<string, Tone> = { applied: "mint", default: "grey", adjusted: "amber", not_supported: "error" };

export function ControlStatus({ status }: { status: string }) {
  return <Badge tone={CONTROL_TONE[status] || "grey"}>{status.replace("_", " ")}</Badge>;
}

export default function Understood({
  brief,
  title,
  meta,
  onAttach,
  onMakeWithout,
  busy,
  heading = "What the tool understood",
  flags = true,
}: {
  brief: Brief;
  title?: string;
  meta?: Meta | null;
  onAttach?: () => void;
  onMakeWithout?: () => void;
  busy?: boolean;
  heading?: string;
  /** the rows' "about this row" flags (off for a planned brief: it is no made version's reading yet) */
  flags?: boolean;
}) {
  const b = brief;
  const controls = meta?.controls || CONTROL_TITLES;
  const groups = meta?.groups || {};
  const changedBy = (control: string) => (b.changed || []).filter((g) => (groups[g] || "") === control);
  const p = b.planner || {};
  const gname = (r: string) => {
    const g = r.split(":")[0];
    return meta?.group_names?.[g] || g.replace(/^assets\./, "the picture: ").replace(/_/g, " ");
  };
  const restored = [...new Set((p.restored || []).map(gname))];
  const rt = p.route;
  const assumptions = (b.assumptions || []).filter((a) => a && a.length > 2);
  const facts = briefFacts(b);

  return (
    <Card label={heading}>
      <CardTitle icon={ScanSearch}>{heading}</CardTitle>
      {(b.needs || []).length ? (
        <div role="alert" className="mb-4 rounded-xl bg-error-container/60 p-4 text-on-error-container">
          <p className="text-body-md">
            <b>This request uses files that are not attached:</b> {(b.needs || []).join(" and ")}.
          </p>
          <p className="mt-1 text-body-sm">Attach them and generate again, or make the ad without them.</p>
          {onAttach || onMakeWithout ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {onAttach ? (
                <Button size="sm" variant="ghost" icon={Paperclip} onClick={onAttach} disabled={busy}>
                  Attach the files
                </Button>
              ) : null}
              {onMakeWithout ? (
                <Button size="sm" variant="ghost" onClick={onMakeWithout} disabled={busy}>
                  Make it without them
                </Button>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
      {title ? <p className="mb-1 text-label-sm font-semibold uppercase tracking-wider text-outline">{title}</p> : null}
      <p className="text-body-lg text-on-surface">{b.summary}</p>
      {facts.length ? <p className="mt-2 text-body-sm text-on-surface-variant">{facts.join(" · ")}</p> : null}

      <div className="mt-4 overflow-hidden rounded-xl ring-1 ring-surface-variant">
        <table className="w-full border-collapse text-left text-body-md">
          <thead className="hidden bg-surface-container-low @2xl:table-header-group">
            <tr className="text-label-sm text-on-surface-variant">
              <th scope="col" className="w-[22%] px-3 py-2 font-semibold">Prompt control</th>
              <th scope="col" className="w-[24%] px-3 py-2 font-semibold">Asked</th>
              <th scope="col" className="px-3 py-2 font-semibold">What the tool does</th>
              <th scope="col" className="w-28 px-3 py-2 font-semibold">Status</th>
            </tr>
          </thead>
          <tbody>
            {b.controls.map((c) => {
              const set = changedBy(c.control);
              return (
                <tr key={c.control} className="block border-t border-surface-variant px-3 py-3 first:border-t-0 @2xl:table-row @2xl:p-0">
                  <th scope="row" className="block pb-1 align-top font-semibold text-on-surface @2xl:table-cell @2xl:px-3 @2xl:py-3">
                    <span className="flex items-start justify-between gap-2">
                      <span className="flex items-start gap-1">
                        {controls[c.control] || c.control}
                        {flags ? <FlagButton title={controls[c.control] || c.control} step="plan" className="-my-1.5" /> : null}
                      </span>
                      <span className="@2xl:hidden">
                        <ControlStatus status={c.status} />
                      </span>
                    </span>
                  </th>
                  <td className="block pb-1 align-top @2xl:table-cell @2xl:px-3 @2xl:py-3">
                    {c.asked ? <span className="italic text-on-surface">“{c.asked}”</span> : <span className="text-outline">not mentioned</span>}
                  </td>
                  <td className="block align-top text-on-surface-variant @2xl:table-cell @2xl:px-3 @2xl:py-3">
                    <span className="text-on-surface">{c.plan}</span>
                    {set.length ? <span className="mt-1 block text-body-sm text-on-surface-variant">Set by the prompt: {[...new Set(set.map(gname))].join(", ")}</span> : null}
                    {c.why ? (
                      <span className={`mt-1 block text-body-sm ${c.status === "not_supported" ? "text-error" : "text-amber"}`}>{c.why}</span>
                    ) : null}
                    {(c.engine || []).map((n, i) => (
                      <span key={i} className="mt-1 block text-body-sm text-amber">
                        While making it: {n}
                      </span>
                    ))}
                  </td>
                  <td className="hidden align-top @2xl:table-cell @2xl:px-3 @2xl:py-3">
                    <ControlStatus status={c.status} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {rt && rt.intent === "edit" ? (
        <div className="mt-4 flex gap-2 rounded-xl bg-surface-container-low p-3 text-body-md">
          <RouteIcon aria-hidden className="mt-0.5 size-4 shrink-0 text-secondary" />
          <div>
            <b>Route</b> (decided in code from the creative&apos;s metadata before planning): {routeSummary(rt)}
            {(rt.notes || []).length ? (
              <div className="mt-1 text-body-sm text-on-surface-variant">
                {(rt.notes || []).map((n, i) => (
                  <div key={i}>{n}</div>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      {(p.references || []).length || assumptions.length ? (
        <ul className="mt-4 flex list-disc flex-col gap-1 pl-5 text-body-sm text-on-surface-variant">
          {(p.references || []).map((r, i) => (
            <li key={`r${i}`}>
              Read from the attached {r.kind || "file"} {r.file}: {r.error ? `could not be read (${r.error})` : refSummary(r)}
            </li>
          ))}
          {assumptions.map((a, i) => (
            <li key={`a${i}`}>Assumed: {a}</li>
          ))}
        </ul>
      ) : null}
      {restored.length ? (
        <p className="mt-3 text-body-sm text-on-surface-variant">
          {p.edit ? "Kept as it was (the edit did not ask about it)" : "Left at the tool's default (the prompt did not ask about it)"}: {restored.join(", ")}
        </p>
      ) : null}
      <p className="mt-3 text-body-sm text-outline">
        {p.model ? `Planner: ${p.model}, ${p.seconds} s` : p.direct ? "Made in code from the route: no planner model was called" : ""}
      </p>
      <Fold summary="Brief as data (what the engine executes)">
        <Pre>{JSON.stringify(b, null, 1)}</Pre>
      </Fold>
    </Card>
  );
}
