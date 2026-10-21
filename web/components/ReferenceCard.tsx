"use client";

import { Clapperboard, ImageIcon } from "lucide-react";
import type { Brief, ReferenceRead } from "@/lib/types";
import { useSource } from "./SourceProvider";
import { Card, CardTitle, Fold, Pre, cx } from "./ui";

// "Reference to creative" (renderReference): what the attached video or image was read for, what was
// taken from it and what was not.

const SEG_TONE: Record<string, string> = {
  hook: "bg-primary-fixed",
  mistake: "bg-error-container",
  fail: "bg-error-container",
  near_fail: "bg-amber-container",
  victory: "bg-tertiary-fixed/40",
  end_card: "bg-secondary-fixed/70",
};

function List({ title, items }: { title: string; items?: string[] }) {
  if (!items?.length) return null;
  return (
    <div>
      <b className="text-label-md">{title}</b>
      <ul className="mt-1 flex list-disc flex-col gap-0.5 pl-5 text-body-sm text-on-surface-variant">
        {items.map((x, i) => (
          <li key={i}>{x}</li>
        ))}
      </ul>
    </div>
  );
}

export function hasReference(b?: Brief | null): boolean {
  if (!b) return false;
  return Boolean((b.planner?.references || []).find((r) => r && r.kind === "video") || b.reference);
}

export default function ReferenceCard({ brief }: { brief: Brief }) {
  const source = useSource();
  const p = brief.planner || {};
  const a = (p.references || []).find((r) => r && r.kind === "video");
  const prov = brief.reference || null;
  if (!a && !prov) return null;
  const r: ReferenceRead = a || {};
  const plan = r.plan || (prov && prov.kind === "image" ? prov.plan : undefined) || {};
  const n = r.notes || {};
  const segs = n.structure || [];
  const file = r.file || prov?.file || "";
  const isImage = !a && (prov?.kind === "image" || /\.(png|jpe?g|webp)$/i.test(file));
  const focus = (r.focus || prov?.focus || []).join(", ") || "nothing";
  const head = [
    `read in full · applied: ${focus} (${r.level || prov?.level || "none"})`,
    prov?.named?.length ? `named by the request: ${prov.named.join(", ")}` : "",
    prov?.filled?.length ? `filled from the reference (the request left it open): ${prov.filled.join(", ")}` : "",
    `${r.analysed_s ?? prov?.analysed_s ?? 0} s analysed`,
    r.confidence != null ? `confidence ${r.confidence}` : "",
  ].filter(Boolean);

  return (
    <Card label="Reference to creative">
      <CardTitle icon={isImage ? ImageIcon : Clapperboard} tone="secondary">
        Reference to creative
      </CardTitle>
      <div className={cx("flex flex-col gap-4", isImage && "@lg:flex-row")}>
        {isImage && file ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={source.media(`uploads/${file}`)}
            alt={`The reference picture ${file}`}
            className="h-auto w-full max-w-[220px] self-start rounded-xl bg-surface-container-low object-contain"
            loading="lazy"
          />
        ) : null}
        <div className="flex min-w-0 flex-1 flex-col gap-3 text-body-md">
          <p>
            <b className="break-all">{file}</b>
            <span className="text-on-surface-variant"> · {head.join(" · ")}</span>
          </p>
          {r.low_confidence ? <p className="text-body-sm text-error">Read with low confidence ({String(r.confidence)}): what was taken from it is only a hint.</p> : null}
          {r.error ? (
            <p className="text-body-sm text-error">Not read: {r.error}. The ad was planned without it.</p>
          ) : r.skipped ? (
            <p className="text-body-sm text-amber">Not read: {r.skipped}.</p>
          ) : r.parts_dropped ? (
            <p className="text-body-sm text-amber">{r.parts_dropped}. The rest of the reading (the concept, the board, the ending, the hook, the captions) is used.</p>
          ) : null}
          {n.concept_in_one_line ? <p className="text-body-lg">{n.concept_in_one_line}</p> : null}
          {plan.level ? (
            <div className="flex flex-col gap-2">
              <p>
                <b>Why</b>: {plan.why || ""}{" "}
                <span className="text-on-surface-variant">({plan.source === "words" ? "read by the word table" : "the planner's reading plan"})</span>
              </p>
              <List title="Looked for" items={plan.questions} />
              {plan.ignore?.length ? (
                <p>
                  <b>Ignored</b>: {plan.ignore.join("; ")}
                </p>
              ) : null}
              {plan.constraints?.length ? (
                <p>
                  <b>Fixed by the request</b>: {plan.constraints.join("; ")}
                </p>
              ) : null}
            </div>
          ) : null}
          {segs.length ? (
            <div>
              <p className="mb-1 text-label-sm font-semibold text-on-surface-variant">The reference&apos;s timeline</p>
              <div className="flex gap-0.5 overflow-hidden rounded-lg">
                {segs.map((s, i) => (
                  <span
                    key={i}
                    title={`${s.from_s}-${s.to_s} s ${s.purpose}: ${s.what || ""}`}
                    style={{ flex: Math.max(0.6, s.to_s - s.from_s) }}
                    className={cx(
                      "min-w-0 overflow-hidden text-ellipsis whitespace-nowrap px-1 py-1.5 text-center text-[11px] leading-tight",
                      SEG_TONE[s.purpose] || "bg-surface-container",
                    )}
                  >
                    {String(s.purpose).replace("_", "-")}
                    <br />
                    <small className="text-on-surface-variant">
                      {s.from_s}-{s.to_s} s
                    </small>
                  </span>
                ))}
              </div>
            </div>
          ) : null}
          <div className="grid gap-3 @lg:grid-cols-2">
            <List title="Adapted" items={prov?.adapted} />
            <List title="Not copied" items={prov?.not_copied} />
          </div>
          {prov?.hud?.took?.length ? (
            <p>
              <b>From its HUD</b> (the reference is CBJ): {prov.hud.took.join("; ")}
            </p>
          ) : null}
          {prov?.board?.text ? (
            <p>
              <b>Board read</b>: {prov.board.text}
              {prov.board.fit ? <i>; {prov.board.fit}</i> : null}
              {prov.board.took?.length ? (
                <span className="text-on-surface-variant">
                  {" "}
                  (taken: {prov.board.took.join(", ")}; a new board of this type is generated, its cells are not copied)
                </span>
              ) : null}
            </p>
          ) : null}
          <List title="Mechanics translated" items={prov?.mechanics} />
          <List title="Not used: not in CBJ" items={prov?.not_used} />
        </div>
      </div>
      {"ask" in r && typeof (r as { ask?: unknown }).ask === "string" ? (
        <Fold summary="What the model was asked">
          <Pre>{(r as { ask: string }).ask}</Pre>
        </Fold>
      ) : null}
    </Card>
  );
}
