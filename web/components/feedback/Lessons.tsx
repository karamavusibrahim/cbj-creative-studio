"use client";

import { BookOpenCheck, Download, Eraser, HelpCircle, History, Loader2, PenLine, Sparkles, UserRound, Workflow } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { engineGet, enginePost, saveText } from "@/lib/engine";
import type { LessonsEmpty, LessonsPackage } from "@/lib/types";
import { LESSON_WORKFLOW_WORDS, stampWords } from "@/lib/words";
import { useEngine } from "../EngineProvider";
import { Badge, Button, Card, CardTitle, ErrorBox, Muted } from "../ui";

// The Lessons tab: the records distilled into a versioned, correctable document (lessons.py). Rendered from
// the structured fields; the Markdown is only for the download. Distil and correct are one model call each.

type Pkg = LessonsPackage | LessonsEmpty;
const isEmpty = (p: Pkg): p is LessonsEmpty => "empty" in p && p.empty === true;

function Evidence({ ids, onEvidence }: { ids: string[]; onEvidence: (id: string) => void }) {
  if (!ids.length) return null;
  return (
    <ul className="flex flex-wrap items-center gap-1.5" aria-label="Evidence">
      {ids.map((id) => (
        <li key={id}>
          <button
            type="button"
            onClick={() => onEvidence(id)}
            title="Show this record"
            className="inline-flex min-h-8 items-center rounded-full bg-surface-container px-2.5 font-mono text-[11px] text-on-surface-variant ring-1 ring-outline-variant/40 transition-colors hover:bg-primary-fixed hover:text-on-primary-fixed"
          >
            {id}
          </button>
        </li>
      ))}
    </ul>
  );
}

function Running() {
  return (
    <p role="status" aria-live="polite" className="flex items-center gap-2 text-body-md text-on-surface-variant">
      <Loader2 aria-hidden className="size-4 animate-spin text-primary-container motion-reduce:animate-none" />
      Reading the records… writing lessons
    </p>
  );
}

export default function Lessons({ total, onEvidence }: { total: number | null; onEvidence: (id: string) => void }) {
  const { conn } = useEngine();
  const [pkg, setPkg] = useState<Pkg | null>(null);
  const [error, setError] = useState("");
  const [errorAt, setErrorAt] = useState<"top" | "correct">("top"); // where the last error shows
  const [busy, setBusy] = useState<"" | "distill" | "correct" | "rollback" | "load">("");
  const [text, setText] = useState("");

  const load = useCallback(
    async (version?: number) => {
      setBusy("load");
      setError("");
      setErrorAt("top");
      try {
        setPkg(await engineGet<Pkg>(conn, version ? `/api/lessons?version=${version}` : "/api/lessons"));
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setBusy("");
      }
    },
    [conn],
  );

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  async function act(action: "distill" | "correct" | "rollback", extra: Record<string, unknown> = {}) {
    setBusy(action);
    setError("");
    setErrorAt(action === "correct" ? "correct" : "top");
    try {
      const next = await enginePost<LessonsPackage>(conn, "/api/lessons", { action, ...extra });
      setPkg(next);
      if (action === "correct") setText("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  const noRecords = total === 0;
  const distill = (
    <span title={noRecords ? "No feedback yet" : "One model call, 20-60 s; makes a new version"} className="inline-flex">
      <Button variant="primary" icon={Sparkles} disabled={noRecords || Boolean(busy)} onClick={() => void act("distill")}>
        Distill now
      </Button>
    </span>
  );

  if (!pkg) {
    return error ? (
      <ErrorBox message={error} />
    ) : (
      <div className="h-48 animate-pulse rounded-2xl bg-surface-container-lowest shadow-sm" aria-hidden />
    );
  }

  if (isEmpty(pkg)) {
    return (
      <Card className="flex flex-col items-center gap-4 py-10 text-center">
        <BookOpenCheck aria-hidden className="size-8 text-outline" />
        <p className="text-body-md text-on-surface-variant">No lessons yet. Distill once there is feedback.</p>
        {distill}
        {busy === "distill" ? <Running /> : null}
        {error ? <ErrorBox message={error} /> : null}
      </Card>
    );
  }

  const m = pkg.meta;
  const shown = m.version;
  const isCurrent = shown === pkg.current;
  const dropped = m.dropped ?? [];

  return (
    <div className="flex flex-col gap-6">
      <Card label="Lessons" className="flex flex-col gap-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex min-w-0 flex-col gap-1">
            <h2 className="flex flex-wrap items-center gap-2 font-headline text-headline-md text-on-surface">
              Lessons v{shown}
              {isCurrent ? <Badge tone="mint">current</Badge> : <Badge tone="amber">an older version · current is v{pkg.current}</Badge>}
            </h2>
            <p className="text-body-md text-on-surface-variant">
              distilled {stampWords(m.generated)} from {m.records} record{m.records === 1 ? "" : "s"} by {m.designers} designer{m.designers === 1 ? "" : "s"}
              {m.model ? ` · ${m.model}` : ""}
              {m.corrections ? ` · ${m.corrections} owner correction${m.corrections === 1 ? "" : "s"} applied` : ""}
            </p>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            {distill}
            <label className="flex flex-col gap-1 text-label-sm text-on-surface-variant">
              Version
              <select
                value={shown}
                disabled={Boolean(busy)}
                onChange={(e) => void load(Number(e.target.value))}
                className="min-h-10 rounded-lg bg-surface-container-low px-2.5 text-body-md text-on-surface outline-none ring-1 ring-outline-variant/40 focus:ring-2 focus:ring-primary-container"
              >
                {[...pkg.versions].reverse().map((v) => (
                  <option key={v.version} value={v.version}>
                    v{v.version} · {stampWords(v.generated)}
                    {v.version === pkg.current ? " (current)" : ""}
                  </option>
                ))}
              </select>
            </label>
            {!isCurrent ? (
              <Button icon={History} disabled={Boolean(busy)} onClick={() => void act("rollback", { version: shown })}>
                Make this the current version
              </Button>
            ) : null}
            <Button variant="ghost" icon={Download} onClick={() => saveText(pkg.markdown, `LESSONS-v${shown}.md`)}>
              Download LESSONS.md
            </Button>
          </div>
        </div>
        {busy === "distill" ? <Running /> : null}
        {error && errorAt === "top" ? <ErrorBox message={error} /> : null}
        {pkg.summary ? <p className="text-body-lg text-on-surface">{pkg.summary}</p> : null}
        {m.note ? <Muted>{m.note}</Muted> : null}
      </Card>

      <section aria-labelledby="part-a" className="flex flex-col gap-4">
        <h2 id="part-a" className="font-headline text-headline-md text-on-surface">
          Part A · What the workflows should do differently
        </h2>
        {!pkg.workflows.length ? <Muted>No workflow lessons in this version.</Muted> : null}
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          {pkg.workflows.map((w) => (
            <Card key={w.workflow} label={LESSON_WORKFLOW_WORDS[w.workflow] || w.workflow}>
              <CardTitle icon={Workflow} as="h3">
                <span className="first-letter:uppercase">{LESSON_WORKFLOW_WORDS[w.workflow] || w.workflow}</span>
              </CardTitle>
              <ol className="flex flex-col divide-y divide-surface-variant">
                {w.lessons.map((l, i) => (
                  <li key={i} className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0">
                    <div className="flex items-start justify-between gap-3">
                      <p className="text-body-md font-semibold text-on-surface">{l.lesson}</p>
                      <Badge tone={l.confidence === "strong" ? "mint" : "grey"} title={l.confidence === "strong" ? "two or more designers, or three or more records" : "one record or one designer"}>
                        {l.confidence}
                      </Badge>
                    </div>
                    {l.suggested_change ? (
                      <p className="text-body-md text-on-surface-variant">
                        <span className="font-semibold text-on-surface">Suggested change:</span> {l.suggested_change}
                      </p>
                    ) : null}
                    <Evidence ids={l.evidence} onEvidence={onEvidence} />
                  </li>
                ))}
              </ol>
            </Card>
          ))}
        </div>
      </section>

      <section aria-labelledby="part-b" className="flex flex-col gap-4">
        <h2 id="part-b" className="font-headline text-headline-md text-on-surface">
          Part B · How each designer asks
        </h2>
        {!pkg.designers.length ? <Muted>No designer entries in this version.</Muted> : null}
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          {pkg.designers.map((d) => (
            <Card key={d.designer} label={d.designer}>
              <CardTitle icon={UserRound} tone="secondary" as="h3">
                {d.designer}
              </CardTitle>
              {d.asks_for.length ? (
                <>
                  <h4 className="mb-1 text-label-md font-semibold text-on-surface">Asks for by default</h4>
                  <ul className="mb-3 list-disc pl-5 text-body-md text-on-surface">
                    {d.asks_for.map((x, i) => (
                      <li key={i}>{x}</li>
                    ))}
                  </ul>
                </>
              ) : null}
              {d.phrasing.length ? (
                <>
                  <h4 className="mb-1 text-label-md font-semibold text-on-surface">Phrasing to watch</h4>
                  <ul className="mb-3 list-disc pl-5 text-body-md text-on-surface-variant">
                    {d.phrasing.map((x, i) => (
                      <li key={i}>{x}</li>
                    ))}
                  </ul>
                </>
              ) : null}
              <Evidence ids={d.evidence} onEvidence={onEvidence} />
            </Card>
          ))}
        </div>
      </section>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card label="Open questions for the designers">
          <CardTitle icon={HelpCircle} tone="secondary">
            Open questions for the designers
          </CardTitle>
          {pkg.open_questions.length ? (
            <ol className="list-decimal pl-5 text-body-md text-on-surface">
              {pkg.open_questions.map((x, i) => (
                <li key={i} className="py-1">
                  {x}
                </li>
              ))}
            </ol>
          ) : (
            <Muted>None in this version.</Muted>
          )}
        </Card>
        <div className="flex flex-col gap-4">
          {pkg.corrections.length ? (
            <Card label="Owner corrections applied">
              <CardTitle icon={PenLine} tone="tertiary">
                Owner corrections applied
              </CardTitle>
              <ul className="flex flex-col gap-2">
                {pkg.corrections.map((c) => (
                  <li key={c.id} className="rounded-xl bg-surface-container-low p-3">
                    <p className="text-body-md text-on-surface">{c.text}</p>
                    <p className="mt-1 text-body-sm text-outline">
                      {stampWords(c.created)}
                      {c.version_before ? ` · written on v${c.version_before}` : ""}
                    </p>
                  </li>
                ))}
              </ul>
            </Card>
          ) : null}
          {dropped.length ? (
            <Card label="Dropped by the checks">
              <CardTitle icon={Eraser} tone="outline">
                Dropped by the checks
              </CardTitle>
              <Muted className="mb-2">What the model wrote that the engine&apos;s checks removed: a lesson must cite records that exist.</Muted>
              <ul className="list-disc pl-5 text-body-md text-on-surface-variant">
                {dropped.map((x, i) => (
                  <li key={i}>{x}</li>
                ))}
              </ul>
            </Card>
          ) : null}
        </div>
      </div>

      <Card label="Correct a lesson">
        <CardTitle icon={PenLine}>
          <label htmlFor="lesson-correction">Correct a lesson in your words</label>
        </CardTitle>
        <Muted className="mb-3">
          Your correction is kept and outranks the records: a new version is distilled with it applied (one model call, 20-60 s). Nothing else changes.
        </Muted>
        <textarea
          id="lesson-correction"
          rows={3}
          value={text}
          maxLength={1000}
          onChange={(e) => setText(e.target.value)}
          placeholder="e.g. The lesson about speed-ups is wrong: designers meant the hurry caption."
          className="w-full resize-y rounded-xl bg-surface-container-low px-3.5 py-2.5 text-body-md text-on-surface outline-none ring-1 ring-outline-variant/50 placeholder:text-outline focus:ring-2 focus:ring-primary-container"
        />
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
          {busy === "correct" ? <Running /> : <span />}
          <Button variant="primary" icon={PenLine} disabled={!text.trim() || Boolean(busy)} onClick={() => void act("correct", { text: text.trim() })}>
            Apply correction
          </Button>
        </div>
        {error && errorAt === "correct" ? <ErrorBox message={error} /> : null}
      </Card>
    </div>
  );
}
