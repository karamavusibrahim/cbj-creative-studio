"use client";

import { ArrowRight, ChevronDown, Download, Inbox, Loader2, ScanSearch } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { engineGet, enginePost, engineText, saveText } from "@/lib/engine";
import { truncate } from "@/lib/text";
import type { CreativeSummary, FeedbackAnalysis, FeedbackDetail, FeedbackListing, FeedbackRecord } from "@/lib/types";
import { AREA_WORDS, FEEDBACK_KINDS, STEP_WORDS, stampWords } from "@/lib/words";
import { useEngine } from "../EngineProvider";
import { Badge, Button, Card, ErrorBox, Muted, cx, type Tone } from "../ui";
import type { OwnerQuery } from "./OwnerPage";

// The Records tab: every feedback record, newest first, with the filters in the query string.

const KIND = Object.fromEntries(FEEDBACK_KINDS.map((k) => [k.id, k]));

const selectCls =
  "min-h-10 w-full rounded-lg bg-surface-container-low px-2.5 text-body-md text-on-surface outline-none ring-1 ring-outline-variant/40 focus:ring-2 focus:ring-primary-container";

function Filter({ label, value, onChange, options }: { label: string; value: string; onChange: (v: string) => void; options: [string, string][] }) {
  return (
    <label className="flex min-w-0 flex-1 basis-40 flex-col gap-1 text-label-sm text-on-surface-variant">
      {label}
      <select value={value} onChange={(e) => onChange(e.target.value)} className={selectCls}>
        <option value="">All</option>
        {/* keep a filter from the URL selectable even when the store no longer has it */}
        {value && !options.some(([v]) => v === value) ? <option value={value}>{value}</option> : null}
        {options.map(([v, text]) => (
          <option key={v} value={v}>
            {text}
          </option>
        ))}
      </select>
    </label>
  );
}

export default function Records({ q, setQ }: { q: OwnerQuery; setQ: (p: Partial<OwnerQuery>) => void }) {
  const { conn } = useEngine();
  const [data, setData] = useState<{ key: string; list: FeedbackListing } | null>(null);
  const [error, setError] = useState("");
  const [titles, setTitles] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

  // one record (an evidence chip): read the full listing and pick it here; else the engine filters
  const key = q.id ? `id:${q.id}` : `${q.designer}|${q.area}|${q.kind}|${q.creative}`;
  useEffect(() => {
    const ctl = new AbortController();
    const p = new URLSearchParams();
    if (!q.id) {
      if (q.designer) p.set("designer", q.designer);
      if (q.area) p.set("area", q.area);
      if (q.kind) p.set("kind", q.kind);
      if (q.creative) p.set("creative_id", q.creative);
    }
    p.set("limit", q.id ? "500" : "200");
    engineGet<FeedbackListing>(conn, `/api/feedback?${p.toString()}`, ctl.signal)
      .then((list) => {
        setData({ key, list });
        setError("");
      })
      .catch((e: Error) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => ctl.abort();
  }, [conn, key, q.id, q.designer, q.area, q.kind, q.creative]);

  // the creatives' titles (their first prompts), as the Recent list shows them
  useEffect(() => {
    let live = true;
    engineGet<CreativeSummary[]>(conn, "/api/creatives")
      .then((list) => live && setTitles(Object.fromEntries(list.map((c) => [c.id, c.prompt]))))
      .catch(() => null);
    return () => {
      live = false;
    };
  }, [conn]);

  async function download() {
    setSaving(true);
    setSaveError("");
    try {
      const md = await engineText(conn, "/api/feedback.md");
      saveText(md, `feedback-${new Date().toISOString().slice(0, 10)}.md`);
    } catch (e) {
      setSaveError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  const list = data && data.key === key ? data.list : null;
  const records: FeedbackRecord[] | null = list ? (q.id ? list.records.filter((r) => r.id === q.id) : list.records) : null;
  const filtered = Boolean(q.designer || q.area || q.kind || q.creative);

  return (
    <div className="flex flex-col gap-5">
      <Card label="Records" className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-title-sm text-on-surface" aria-live="polite">
            {list ? `${list.total} record${list.total === 1 ? "" : "s"} from ${list.designers.length} designer${list.designers.length === 1 ? "" : "s"}` : "Reading the records…"}
          </p>
          <button
            type="button"
            onClick={() => void download()}
            disabled={saving}
            className="inline-flex min-h-10 items-center gap-1.5 text-label-md font-semibold text-primary hover:underline disabled:opacity-50"
          >
            <Download aria-hidden className="size-4" />
            {saving ? "Preparing…" : "Download .md"}
          </button>
        </div>
        {saveError ? <ErrorBox message={saveError} /> : null}
        {q.id ? (
          <p className="flex flex-wrap items-center gap-2 text-body-md text-on-surface-variant">
            Showing one record: <span className="font-mono text-code-sm text-on-surface">{q.id}</span>
            <button type="button" onClick={() => setQ({ id: "" })} className="min-h-10 font-semibold text-primary hover:underline">
              Show all
            </button>
          </p>
        ) : (
          <div className="flex flex-wrap gap-3" role="group" aria-label="Filters">
            <Filter label="Designer" value={q.designer} onChange={(v) => setQ({ designer: v })} options={(list?.designers ?? []).map((d) => [d, d])} />
            <Filter label="About" value={q.area} onChange={(v) => setQ({ area: v })} options={(list?.areas ?? []).map((a) => [a, AREA_WORDS[a] || a])} />
            <Filter label="Kind" value={q.kind} onChange={(v) => setQ({ kind: v })} options={(list?.kinds ?? []).map((k) => [k, KIND[k]?.text || k])} />
            <Filter
              label="This creative only"
              value={q.creative}
              onChange={(v) => setQ({ creative: v })}
              options={(list?.creatives ?? []).map((c) => [c, titles[c] ? truncate(titles[c], 70) : c])}
            />
          </div>
        )}
        {list && filtered && !q.id ? (
          <p className="text-body-sm text-on-surface-variant">
            {list.count === 1 ? "1 record matches" : `${list.count} records match`} the filters
            {list.count > list.records.length ? `; the newest ${list.records.length} are shown` : ""}.{" "}
            <button type="button" onClick={() => setQ({ designer: "", area: "", kind: "", creative: "" })} className="font-semibold text-primary hover:underline">
              Clear the filters
            </button>
          </p>
        ) : null}
      </Card>

      {error ? <ErrorBox message={error} /> : null}

      {records === null ? (
        error ? null : (
          <ul className="flex flex-col gap-3" aria-hidden>
            {[0, 1, 2].map((i) => (
              <li key={i} className="h-28 animate-pulse rounded-2xl bg-surface-container-lowest shadow-sm" />
            ))}
          </ul>
        )
      ) : !records.length ? (
        <Card className="flex flex-col items-center gap-2 py-10 text-center">
          <Inbox aria-hidden className="size-8 text-outline" />
          <p className="text-body-md text-on-surface-variant">
            {q.id
              ? "That record is not in the store."
              : filtered
                ? "No record matches these filters."
                : "No feedback yet. Designers send it from the Give feedback button next to a creative."}
          </p>
        </Card>
      ) : (
        <ul className="flex flex-col gap-3" aria-label="Feedback records, newest first">
          {records.map((r) => (
            <RecordRow key={r.id} r={r} opened={Boolean(q.id)} title={r.scene.creative_id ? titles[r.scene.creative_id] : undefined} />
          ))}
        </ul>
      )}
    </div>
  );
}

function RecordRow({ r, title, opened = false }: { r: FeedbackRecord; title?: string; opened?: boolean }) {
  const [open, setOpen] = useState(opened);
  const k = KIND[r.kind];
  const s = r.scene || {};
  return (
    <li className="flex flex-col gap-2 rounded-2xl bg-surface-container-lowest p-4 shadow-sm sm:p-5">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
        <span className="text-label-md font-semibold text-on-surface">{r.designer}</span>
        <span aria-hidden className="text-outline">
          ·
        </span>
        <time dateTime={r.created.replace(" ", "T")} className="text-body-sm text-on-surface-variant">
          {stampWords(r.created)}
        </time>
        <Badge tone={k?.tone ?? "grey"}>{k?.short ?? r.kind}</Badge>
        <span className="text-body-sm text-on-surface-variant">{AREA_WORDS[r.area] || r.area}</span>
        {r.rating ? <Badge tone="violet" title="How close to what they asked">{r.rating}/5</Badge> : null}
        {r.step ? (
          <Badge tone="sky" title="The step of the process the note is about">
            {STEP_WORDS[r.step as keyof typeof STEP_WORDS] || r.step}
          </Badge>
        ) : null}
        <span className="ml-auto font-mono text-[11px] text-outline">{r.id}</span>
      </div>
      {s.prompt ? (
        <p className="truncate text-body-sm text-on-surface-variant" title={s.prompt}>
          {s.prompt}
        </p>
      ) : (
        <p className="text-body-sm text-outline">{r.page === "general" ? "About the studio" : `From the ${r.page} page`}</p>
      )}
      {r.item ? (
        <p className="break-words font-mono text-code-sm text-on-surface" title="The exact thing on the page">
          {r.item}
        </p>
      ) : null}
      {r.wrong ? <p className="whitespace-pre-wrap text-body-md text-on-surface">{r.wrong}</p> : null}
      {r.expected ? (
        <p className="whitespace-pre-wrap text-body-md text-on-surface-variant">
          <span className="font-semibold">Expected:</span> {r.expected}
        </p>
      ) : null}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1">
        <button
          type="button"
          aria-expanded={open}
          aria-controls={`ev-${r.id}`}
          onClick={() => setOpen(!open)}
          className="inline-flex min-h-9 items-center gap-1 text-label-md font-semibold text-on-surface-variant hover:text-on-surface"
        >
          <ChevronDown aria-hidden className={cx("size-4 transition-transform", open && "rotate-180")} />
          {open ? "Hide what the engine did" : "What the engine did"}
        </button>
        {s.creative_id && s.version ? (
          <Link
            href={`/edit?c=${encodeURIComponent(s.creative_id)}&v=${s.version}`}
            title={title || s.creative_id}
            className="inline-flex min-h-9 items-center gap-1 text-label-md font-semibold text-primary hover:underline"
          >
            Open v{s.version} <ArrowRight aria-hidden className="size-4" />
          </Link>
        ) : null}
      </div>
      {open ? <Evidence id={r.id} /> : null}
    </li>
  );
}

const VERDICT: Record<string, { tone: Tone; text: string }> = {
  system: { tone: "amber", text: "the system" },
  taste: { tone: "grey", text: "taste" },
  unclear: { tone: "grey", text: "unclear" },
};

/** A fact's value in a line: text as it is, a list one item per line, an object as "key: value" pairs. */
function factText(x: unknown): string {
  if (x === null || x === undefined) return "";
  if (typeof x !== "object") return String(x);
  if (Array.isArray(x)) return x.map((i) => (i && typeof i === "object" ? pairs(i as Record<string, unknown>) : String(i))).join("\n");
  return pairs(x as Record<string, unknown>);
}

function pairs(o: Record<string, unknown>): string {
  return Object.entries(o)
    .filter(([, v]) => v !== null && v !== undefined && v !== "" && !(Array.isArray(v) && !v.length))
    .map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : String(v)}`)
    .join(" · ");
}

/** One record's evidence (GET /api/feedback/<id>: the facts of its step and the engine's lines) and its analysis. */
function Evidence({ id }: { id: string }) {
  const { conn } = useEngine();
  const [d, setD] = useState<FeedbackDetail | null>(null);
  const [error, setError] = useState("");
  const [analysis, setAnalysis] = useState<FeedbackAnalysis | null>(null);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState("");

  useEffect(() => {
    const ctl = new AbortController();
    engineGet<FeedbackDetail>(conn, `/api/feedback/${encodeURIComponent(id)}`, ctl.signal)
      .then((x) => {
        setD(x);
        setAnalysis(x.analysis);
      })
      .catch((e: Error) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => ctl.abort();
  }, [conn, id]);

  async function analyze() {
    setRunning(true);
    setRunError("");
    try {
      setAnalysis(await enginePost<FeedbackAnalysis>(conn, `/api/feedback/${encodeURIComponent(id)}/analyze`, {}));
    } catch (e) {
      setRunError((e as Error).message);
    } finally {
      setRunning(false);
    }
  }

  if (error) return <ErrorBox message={error} />;
  if (!d) return <div id={`ev-${id}`} aria-busy="true" className="h-24 animate-pulse rounded-xl bg-surface-container-low" />;
  const ev = d.evidence;
  const facts = Object.entries(ev.facts || {});
  return (
    <div id={`ev-${id}`} className="flex flex-col gap-4 rounded-xl bg-surface-container-low/60 p-3.5 sm:p-4">
      <div className="flex flex-col gap-2">
        <p className="text-label-md font-semibold text-on-surface">
          The engine at this step: {ev.words}
          {ev.item ? (
            <>
              {" "}
              · <span className="font-mono text-code-sm font-normal">{ev.item}</span>
            </>
          ) : null}
        </p>
        {facts.length ? (
          <dl className="grid grid-cols-1 gap-x-3 gap-y-1.5 text-body-sm sm:grid-cols-[minmax(6.5rem,auto)_1fr]">
            {facts.map(([k, x]) => (
              <div key={k} className="contents">
                <dt className="font-semibold text-on-surface">{k}</dt>
                <dd className="max-h-40 min-w-0 overflow-y-auto whitespace-pre-wrap break-words text-on-surface-variant">{factText(x)}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <Muted>No stored facts for this step (a note about the website, or a version made before the capture).</Muted>
        )}
        {ev.lines?.length ? (
          <ol aria-label="The engine's lines of this stage" className="max-h-56 overflow-y-auto rounded-lg bg-surface-container-lowest p-2.5 font-mono text-[11px] leading-4 text-on-surface-variant">
            {ev.lines.map((ln, i) => (
              <li key={i} className="break-words">
                {ln.stage ? <span className="text-outline">[{ln.stage}] </span> : null}
                {ln.text}
              </li>
            ))}
          </ol>
        ) : null}
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Button size="sm" variant="ghost" icon={running ? undefined : ScanSearch} disabled={running} aria-busy={running} onClick={() => void analyze()}>
          {running ? <Loader2 aria-hidden className="size-4 animate-spin motion-reduce:animate-none" /> : null}
          {analysis ? "Analyze again" : "Analyze what happened"}
        </Button>
        <span aria-live="polite" className="text-body-sm text-on-surface-variant">
          {running ? "Reading the evidence… (10-30 s)" : ""}
        </span>
      </div>
      {runError ? <ErrorBox message={runError} /> : null}
      {analysis ? <AnalysisCard a={analysis} /> : null}
    </div>
  );
}

function AnalysisCard({ a }: { a: FeedbackAnalysis }) {
  const v = VERDICT[a.verdict] || VERDICT.unclear;
  return (
    <section aria-label="Analysis" className="flex flex-col gap-3 rounded-xl bg-surface-container-lowest p-3.5 shadow-sm ring-1 ring-surface-variant sm:p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={v.tone} title="Whose fault: the system, the designer's taste, or the evidence does not say">
          {v.text}
        </Badge>
        <Badge tone={a.confidence === "strong" ? "mint" : "grey"}>{a.confidence}</Badge>
        <span className="ml-auto text-body-sm text-outline">
          {[a.model, a.seconds ? `${a.seconds} s` : "", a.created ? stampWords(a.created) : ""].filter(Boolean).join(" · ")}
        </span>
      </div>
      <div>
        <h4 className="text-label-md font-semibold text-on-surface">What happened</h4>
        <p className="text-body-md text-on-surface">{a.what_happened}</p>
      </div>
      <div>
        <h4 className="text-label-md font-semibold text-on-surface">Why</h4>
        <p className="text-body-md text-on-surface">{a.why}</p>
      </div>
      {a.evidence?.length ? (
        <ul aria-label="The evidence it quotes" className="flex flex-col gap-1.5">
          {a.evidence.map((x, i) => (
            <li key={i}>
              <blockquote className="break-words border-l-2 border-primary-container bg-surface-container-low px-3 py-1.5 font-mono text-[11.5px] leading-4 text-on-surface-variant">{x}</blockquote>
            </li>
          ))}
        </ul>
      ) : null}
      {a.suggested_change ? (
        <div>
          <h4 className="text-label-md font-semibold text-on-surface">Smallest change</h4>
          <p className="text-body-md text-on-surface">{a.suggested_change}</p>
        </div>
      ) : null}
      {a.unbacked?.length ? (
        <div>
          <h4 className="text-label-sm font-semibold text-outline">not in the evidence</h4>
          <ul className="flex list-disc flex-col gap-0.5 pl-5 text-body-sm text-outline">
            {a.unbacked.map((x, i) => (
              <li key={i} className="break-words">
                {x}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
