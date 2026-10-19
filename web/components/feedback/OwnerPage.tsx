"use client";

import { BookOpenCheck, CloudOff, KeyRound, ListChecks } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { engineGet } from "@/lib/engine";
import type { FeedbackListing } from "@/lib/types";
import { useEngine } from "../EngineProvider";
import { useFeedbackState } from "../FeedbackDialog";
import { Button, Card, cx } from "../ui";
import Lessons from "./Lessons";
import Records from "./Records";

// The owner's page (SPEC-FEEDBACK §3): what designers reported (Records) and the lessons distilled from it
// (Lessons). Needs the engine and the passcode: the records carry designers' names and words.

export interface OwnerQuery {
  tab: "records" | "lessons";
  designer: string;
  area: string;
  kind: string;
  creative: string;
  id: string; // one record (an evidence chip on the Lessons tab)
}

const TABS = [
  { id: "records", text: "Records", icon: ListChecks },
  { id: "lessons", text: "Lessons", icon: BookOpenCheck },
] as const;

function href(q: OwnerQuery): string {
  const p = new URLSearchParams();
  p.set("tab", q.tab);
  if (q.tab === "records") {
    if (q.id) p.set("id", q.id);
    for (const k of ["designer", "area", "kind", "creative"] as const) if (q[k]) p.set(k, q[k]);
  }
  return `/feedback?${p.toString()}`;
}

function Gate({ icon: Icon, title, children }: { icon: typeof CloudOff; title: string; children: React.ReactNode }) {
  return (
    <Card className="mx-auto flex w-full max-w-xl flex-col items-center gap-3 py-10 text-center">
      <span className="flex size-12 items-center justify-center rounded-2xl bg-surface-container text-outline">
        <Icon aria-hidden className="size-6" />
      </span>
      <h2 className="font-headline text-headline-md text-on-surface">{title}</h2>
      {children}
    </Card>
  );
}

export default function OwnerPage({ initial }: { initial: OwnerQuery }) {
  const engine = useEngine();
  const state = useFeedbackState();
  const [q, setQState] = useState<OwnerQuery>(initial);
  const [total, setTotal] = useState<number | null>(null);
  const open = engine.status === "online" && state === "on" && engine.unlocked;

  const setQ = useCallback((patch: Partial<OwnerQuery>) => {
    setQState((cur) => {
      const next = { ...cur, ...patch };
      window.history.replaceState(null, "", href(next));
      return next;
    });
  }, []);

  // how many records exist at all (the Lessons tab's Distill needs at least one)
  const { conn } = engine;
  const refreshTotal = useCallback(async () => {
    try {
      setTotal((await engineGet<FeedbackListing>(conn, "/api/feedback?limit=1")).total);
    } catch {
      setTotal(null);
    }
  }, [conn]);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (open) void refreshTotal();
  }, [open, refreshTotal]);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
        <div className="flex flex-col gap-1">
          <span className="self-start rounded-full bg-primary-fixed px-2.5 py-0.5 text-label-sm font-semibold uppercase tracking-wider text-on-primary-fixed">
            For the studio&apos;s owner
          </span>
          <h1 className="font-headline text-headline-xl-mobile text-on-surface sm:text-headline-xl">Feedback</h1>
          <p className="max-w-3xl text-body-md text-on-surface-variant">
            What designers reported, creative by creative, and the lessons distilled from it. Read before tuning a workflow by hand: nothing
            here changes a creative or a workflow.
          </p>
        </div>
        {open ? (
          <div role="tablist" aria-label="Feedback views" className="flex shrink-0 self-start rounded-full bg-surface-container-low p-1 md:self-auto">
            {TABS.map((t) => {
              const on = q.tab === t.id;
              return (
                <button
                  key={t.id}
                  type="button"
                  role="tab"
                  id={`tab-${t.id}`}
                  aria-selected={on}
                  aria-controls={`panel-${t.id}`}
                  onClick={() => setQ({ tab: t.id })}
                  className={cx(
                    "flex min-h-10 items-center gap-1.5 rounded-full px-5 text-label-md transition-all",
                    on ? "bg-primary-container font-semibold text-on-primary shadow-sm" : "text-on-surface-variant hover:text-on-surface",
                  )}
                >
                  <t.icon aria-hidden className="size-4" />
                  {t.text}
                </button>
              );
            })}
          </div>
        ) : null}
      </div>

      {engine.status === "checking" ? (
        <div className="h-48 animate-pulse rounded-2xl bg-surface-container-lowest shadow-sm" aria-hidden />
      ) : engine.status === "offline" ? (
        <Gate icon={CloudOff} title="Needs the engine">
          <p className="text-body-md text-on-surface-variant">
            The feedback records and the lessons live on the studio engine, which is offline right now. The showcase holds no feedback.
          </p>
          <Link href="/showcase" className="min-h-10 content-center text-label-md font-semibold text-primary hover:underline">
            Browse the showcase
          </Link>
        </Gate>
      ) : state === "hidden" ? (
        <Gate icon={CloudOff} title="This engine takes no feedback yet">
          <p className="text-body-md text-on-surface-variant">It needs a restart with the newer version of the engine.</p>
        </Gate>
      ) : !engine.unlocked ? (
        <Gate icon={KeyRound} title="This page is for the studio's owner.">
          <p className="text-body-md text-on-surface-variant">It shows what designers wrote, with their names. Enter the passcode to read it.</p>
          <Button variant="primary" icon={KeyRound} onClick={() => void engine.ensureUnlocked()}>
            Unlock
          </Button>
        </Gate>
      ) : state !== "on" ? (
        <div className="h-48 animate-pulse rounded-2xl bg-surface-container-lowest shadow-sm" aria-hidden />
      ) : q.tab === "records" ? (
        <div role="tabpanel" id="panel-records" aria-labelledby="tab-records">
          <Records q={q} setQ={setQ} />
        </div>
      ) : (
        <div role="tabpanel" id="panel-lessons" aria-labelledby="tab-lessons">
          <Lessons
            total={total}
            onEvidence={(id) => {
              setQ({ tab: "records", id, designer: "", area: "", kind: "", creative: "" });
              window.scrollTo({ top: 0 });
            }}
          />
        </div>
      )}
    </div>
  );
}
