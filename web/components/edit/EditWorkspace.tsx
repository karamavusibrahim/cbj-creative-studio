"use client";

import { ArrowLeftRight, ChevronDown, Eye, FileClock, GitCompare, ImagePlus, Info, PanelLeft, Paperclip, SlidersHorizontal, Wand2, X } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { EngineError, engineGet, showcaseSource, uploadFiles } from "@/lib/engine";
import { fetchDetail } from "@/lib/showcase";
import type { Brief, InventoryItem, Proof, Review, Version } from "@/lib/types";
import { truncate } from "@/lib/text";
import { EDIT_EXAMPLES, WORKFLOW_WORDS } from "@/lib/words";
import { EnhanceButton, EnhancedCard, useEnhance } from "../Enhance";
import FeedbackPanel, { FeedbackPanelProvider } from "../FeedbackPanel";
import { useEngine } from "../EngineProvider";
import EditReport from "../EditReport";
import VersionGameplay from "../Gameplay";
import Inventory, { type DirectOp } from "../Inventory";
import OfflineBanner from "../OfflineBanner";
import { Pair, PhoneFrame, VersionVideo } from "../Player";
import Progress from "../Progress";
import ReportButton from "../ReportButton";
import ReviewCard, { reviewLine, useReview } from "../ReviewCard";
import SampleAssets from "../SampleAssets";
import SoundtrackCard from "../Soundtrack";
import { PinnedSource, useSource } from "../SourceProvider";
import Understood from "../Understood";
import useJob from "../useJob";
import { DownloadLink, VersionLinks, boardSize } from "../VersionBits";
import { Button, Card, CardTitle, ErrorBox, Muted, cx } from "../ui";
import Picker from "./Picker";

// The Edit workspace (edit-workspace): describe one change or make an exact one, and read the report
// that proves what changed and what was kept. A designer sees only what a designer needs (SPEC-FEEDBACK-INLINE §4):
// the change, the things in the ad, the player and the versions, "Was this what you asked?", and one "What changed"
// card. "Details" (remembered in this browser) brings back the full report, Compare, the level and moves, Metadata,
// the files and the brief; the report of any version can be downloaded with every intermediate step.

const DETAILS_KEY = "cbj.edit.details";

function savedDetails(): boolean {
  try {
    return localStorage.getItem(DETAILS_KEY) === "1";
  } catch {
    return false;
  }
}

interface Loaded {
  cid: string;
  versions: Version[];
  from: "engine" | "showcase";
}

export default function EditWorkspace({ cid, n, prefill, matched }: { cid?: string; n?: number; prefill?: string; matched?: boolean }) {
  if (!cid) {
    return (
      <div>
        <OfflineBanner />
        <div className="mb-6 flex flex-col gap-1">
          <h1 className="font-headline text-headline-xl-mobile text-on-surface sm:text-headline-xl">Edit a creative</h1>
          <p className="max-w-2xl text-body-md text-on-surface-variant">
            Choose a finished creative. Then describe one change, or make an exact one from the things in the ad; everything you do not mention stays as it is,
            and the edit report proves it.
          </p>
        </div>
        <Picker />
      </div>
    );
  }
  // a navigation to another creative, version or suggested edit starts a fresh workspace
  return <Workspace key={`${cid}:${n ?? ""}:${prefill ?? ""}`} cid={cid} n={n} prefill={prefill} matched={matched} />;
}

function Workspace({ cid, n, prefill, matched }: { cid: string; n?: number; prefill?: string; matched?: boolean }) {
  const engine = useEngine();
  const { job, run, resume } = useJob("edit");
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [loadError, setLoadError] = useState("");
  const [selected, setSelected] = useState<number | undefined>(n);
  const [prompt, setPrompt] = useState(prefill || "");
  const [files, setFiles] = useState<string[]>([]);
  const [uploadError, setUploadError] = useState("");
  const [planned, setPlanned] = useState<Brief | null>(null);
  const [plannedPrompt, setPlannedPrompt] = useState("");
  const [pairPref, setPairView] = useState<boolean | null>(null); // null: before/after for an edit
  const [inventory, setInventory] = useState<{ key: string; items: InventoryItem[] } | null>(null);
  const [reviews, setReviews] = useState<Record<number, Review>>({});
  const [picker, setPicker] = useState(false);
  const [notice, setNotice] = useState(matched ? "The attached MP4 is one of this tool's own versions: the change is an edit of it. Press Apply change to plan it." : "");
  const [lastAction, setLastAction] = useState("");
  const [allExamples, setAllExamples] = useState(false);
  const [details, setDetailsState] = useState(savedDetails);
  const fileRef = useRef<HTMLInputElement>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const enh = useEnhance<string>();

  const online = engine.status === "online";
  const fromShowcase = loaded?.from === "showcase";
  const source = fromShowcase ? showcaseSource() : engine.source;
  const canAct = online && !fromShowcase;
  const disabled = !canAct || engine.otherBusy || job.running;

  const load = useCallback(
    async (pick?: number) => {
      if (engine.status === "checking") return;
      setLoadError("");
      try {
        if (engine.status === "online") {
          const vs = await engineGet<Version[]>(engine.conn, `/api/creatives/${encodeURIComponent(cid)}`);
          setLoaded({ cid, versions: vs, from: "engine" });
        } else {
          const d = await fetchDetail(cid);
          if (!d) throw new EngineError("The engine is offline and this creative is not in the showcase.");
          setLoaded({ cid, versions: d.versions, from: "showcase" });
        }
        if (pick !== undefined) setSelected(pick);
      } catch (e) {
        setLoadError((e as Error).message);
      }
    },
    [engine.status, engine.conn, cid],
  );

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  const versions = useMemo(() => loaded?.versions ?? [], [loaded]);
  const last = versions[versions.length - 1];
  const v = versions.find((x) => x.n === selected) || last || null;
  const prev = v && v.edit ? versions.find((x) => x.n === (v.from ?? v.n - 1)) || null : null;
  const pairView = pairPref ?? Boolean(prev);

  // keep the URL on the version shown
  useEffect(() => {
    if (!v) return;
    const want = `/edit?c=${encodeURIComponent(cid)}&v=${v.n}`;
    if (typeof window !== "undefined" && window.location.pathname + window.location.search !== want && !prefill) {
      window.history.replaceState(null, "", want);
    }
  }, [v, cid, prefill]);

  // things in this ad: the engine's inventory, or the exported inventory.json
  const invKey = v ? `${loaded?.from}:${v.id}:${v.n}` : "";
  useEffect(() => {
    if (!v || !loaded) return;
    let live = true;
    (async () => {
      let items: InventoryItem[] = [];
      try {
        items =
          loaded.from === "engine"
            ? await engineGet<InventoryItem[]>(engine.conn, `/api/inventory/${encodeURIComponent(cid)}?base=${v.n}`)
            : ((await showcaseSource().json<InventoryItem[]>(`${v.id}/v${v.n}/inventory.json`)) ?? []);
      } catch {
        items = [];
      }
      if (live) setInventory({ key: invKey, items });
    })();
    return () => {
      live = false;
    };
  }, [v, loaded, engine.conn, cid, invKey]);

  // after a reload: follow an edit job that was running
  const resumed = useRef(false);
  useEffect(() => {
    if (!online || resumed.current) return;
    resumed.current = true;
    void (async () => {
      const r = await resume();
      if (!r || r.stored.context?.cid !== cid) return;
      const res = r.result as Version & Brief;
      if ((r.stored.kind === "make" || r.stored.kind === "direct") && res && "n" in res) await load(res.n);
      else if (r.stored.kind === "plan") {
        setPlanned(res as Brief);
        setPlannedPrompt(String(r.stored.context?.prompt || ""));
      }
    })();
  }, [online, resume, cid, load]);

  async function ready(): Promise<boolean> {
    if (!canAct) {
      setNotice(fromShowcase ? "This is a read-only showcase copy: editing needs the studio engine online." : "The studio engine is offline.");
      return false;
    }
    if (engine.otherBusy) {
      setNotice("The engine is making another creative; one at a time.");
      return false;
    }
    setNotice("");
    return engine.ensureUnlocked();
  }

  // the rewrite belongs to the version it was asked for; another version shown drops it
  const enhKey = v ? `${cid}:${v.n}` : "";
  const enhanced = enh.key === enhKey ? enh.result : null;

  async function enhance() {
    if (!v || !canAct) return;
    const r = await enh.enhance({ prompt: prompt.trim(), uploads: files, creative_id: cid, base: v.n }, prompt, enhKey);
    if (r?.changed) setPrompt(r.prompt);
  }

  function undoEnhance() {
    if (enh.snapshot !== null) setPrompt(enh.snapshot);
    enh.clear();
    textarea.current?.focus();
  }

  async function makeEdit(b: Brief, p: string, base: number, withoutFiles = false) {
    const nv = await run<Version>(
      "/api/make",
      { prompt: p, brief: b, creative_id: cid, base, draft: false, review: true, revise: true, without_files: withoutFiles },
      "make",
      { cid, prompt: p },
      true,
    );
    setPlanned(null);
    setPrompt("");
    setFiles([]);
    enh.clear();
    await load(nv.n);
    setPairView(true);
  }

  async function apply() {
    if (!v) return;
    const p = prompt.trim();
    if (!p) {
      textarea.current?.focus();
      return;
    }
    if (!(await ready())) return;
    setLastAction(p);
    setPlanned(null);
    try {
      const b = await run<Brief>("/api/plan", { prompt: p, creative_id: cid, base: v.n, uploads: files }, "plan", { cid, prompt: p });
      setPlanned(b);
      setPlannedPrompt(p);
      if ((b.needs || []).length) return; // a question, not an edit without the files
      await makeEdit(b, p, v.n);
    } catch {
      /* the progress card shows the error */
    }
  }

  async function direct(op: DirectOp, label: string): Promise<number | null> {
    if (!v || !(await ready())) return null;
    setLastAction(label);
    setPlanned(null);
    try {
      const nv = await run<Version>("/api/direct", { creative_id: cid, base: v.n, op, draft: false }, "direct", { cid, prompt: label });
      await load(nv.n);
      setPairView(true);
      return nv.n;
    } catch {
      /* shown in the progress card */
      return null;
    }
  }

  async function upload(list: File[]): Promise<string[] | null> {
    if (!(await ready())) return null;
    setUploadError("");
    try {
      const names = await uploadFiles(engine.conn, list);
      void engine.refreshMeta();
      return names;
    } catch (e) {
      setUploadError((e as Error).message);
      return null;
    }
  }

  /** A sample asset from the catalogue: the same upload as a dropped file (true when attached). */
  async function attachSample(list: File[]): Promise<boolean> {
    const names = await upload(list);
    if (names) setFiles((f) => [...new Set([...f, ...names])]);
    return Boolean(names);
  }

  async function review() {
    if (!v || !(await ready())) return;
    setLastAction(`Review v${v.n} as a viewer`);
    try {
      const r = await run<Review>("/api/review", { creative_id: cid, n: v.n }, "review", { cid });
      setReviews((m) => ({ ...m, [v.n]: r }));
    } catch {
      /* shown in the progress card */
    }
  }

  function setDetails(on: boolean) {
    setDetailsState(on);
    try {
      localStorage.setItem(DETAILS_KEY, on ? "1" : "0");
    } catch {
      /* private mode */
    }
  }

  if (loadError) {
    return (
      <div>
        <OfflineBanner />
        <Card>
          <CardTitle icon={Info}>This creative could not be opened</CardTitle>
          <ErrorBox message={loadError} />
          <div className="mt-4 flex gap-3">
            <Link href="/edit" className="inline-flex min-h-10 items-center rounded-xl bg-surface-container-high px-4 text-label-md font-semibold">
              Choose another creative
            </Link>
            <Link href="/showcase" className="inline-flex min-h-10 items-center rounded-xl px-4 text-label-md font-semibold text-primary">
              Open the Showcase
            </Link>
          </div>
        </Card>
      </div>
    );
  }

  if (!loaded || !v) {
    return (
      <div aria-busy="true">
        <OfflineBanner />
        <div className="mb-6 h-10 w-2/3 animate-pulse rounded-xl bg-surface-container" />
        <div className="grid gap-6 lg:grid-cols-12">
          <div className="h-96 animate-pulse rounded-2xl bg-surface-container-lowest shadow-sm lg:col-span-4" />
          <div className="h-[32rem] animate-pulse rounded-2xl bg-surface-container-lowest shadow-sm lg:col-span-5" />
          <div className="h-80 animate-pulse rounded-2xl bg-surface-container-lowest shadow-sm lg:col-span-3" />
        </div>
      </div>
    );
  }

  const title = versions[0]?.prompt || cid;
  const isOlder = last && v.n !== last.n;
  const items = inventory && inventory.key === invKey ? inventory.items : null;
  const showPair = pairView && prev;

  return (
    <PinnedSource source={source}>
      <OfflineBanner />
      {/* top workspace bar */}
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4 border-b border-surface-variant pb-4">
        <div className="flex min-w-0 flex-wrap items-center gap-3">
          <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-2 font-headline text-headline-md text-on-surface">
            <Link href="/edit" className="hover:text-primary">
              Edit
            </Link>
            <span aria-hidden className="text-on-surface-variant/50">
              /
            </span>
            <span className="min-w-0 max-w-[60vw] truncate sm:max-w-[28rem]" title={title}>
              {truncate(title, 60)}
            </span>
            <span aria-hidden className="text-on-surface-variant/50">
              /
            </span>
            <span>v{v.n}</span>
          </nav>
          <span className="inline-flex items-center gap-2 rounded-full bg-surface-container px-3 py-1">
            <span aria-hidden className={cx("size-2 rounded-full", v.edit ? "bg-secondary-container" : "bg-tertiary")} />
            <span className="text-label-sm font-medium text-on-surface-variant">
              {v.edit ? `Edit of v${v.from ?? v.n - 1}` : "Original"} · Version {v.n}
              {fromShowcase ? " · showcase copy" : ""}
            </span>
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <DetailsSwitch on={details} onChange={setDetails} />
          <Button variant="ghost" icon={PanelLeft} onClick={() => setPicker(true)}>
            Creatives
          </Button>
          <DownloadLink v={v} label="Export video" primary />
        </div>
      </div>

      <FeedbackPanelProvider
        context={{ page: "edit", creative_id: cid, version: v.n, title, workflow: v.workflow || (v.edit ? "edit" : "create") }}
        edit={Boolean(v.edit)}
        unavailable={fromShowcase}
      >
      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-12">
        {/* LEFT: the request and the things in the ad */}
        <div className="flex min-w-0 flex-col gap-5 lg:col-span-5 xl:col-span-4">
          <Card label="What would you like to change?" className="flex flex-col gap-5 border border-surface-variant">
            <div>
              <h1 className="font-headline text-headline-md font-bold text-on-surface">
                <label htmlFor="edit-prompt">What would you like to change?</label>
              </h1>
              <p className="mt-1 text-body-md text-on-surface-variant">
                Describe one change to <b>v{v.n}</b>.
                {isOlder && canAct ? ` An earlier version: the new version starts from v${v.n}, not from v${last.n}.` : ""}
              </p>
            </div>
            <textarea
              id="edit-prompt"
              ref={textarea}
              rows={4}
              value={prompt}
              disabled={!canAct}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && !disabled) void apply();
              }}
              placeholder="e.g. Keep everything exactly the same, but change the hook to 'Can you solve this?'"
              className="w-full resize-y rounded-xl border border-outline-variant/50 bg-surface-container-low/40 p-3.5 text-body-md text-on-surface outline-none transition-all placeholder:text-on-surface-variant/50 focus:border-primary focus:ring-2 focus:ring-primary/20 disabled:opacity-60"
            />
            <p className="-mt-3 text-body-sm text-on-surface-variant">Everything you do not mention stays as it is; the report proves it.</p>
            <div className="-mt-3 flex flex-wrap items-center justify-between gap-2">
              <span className="text-code-sm text-outline">⌘/Ctrl + Enter to apply</span>
              <EnhanceButton loading={enh.loading} available={enh.available && canAct} hasText={Boolean(prompt.trim())} onClick={() => void enhance()} />
            </div>
            {enhanced || enh.error ? (
              <EnhancedCard
                result={enhanced}
                error={enh.error}
                added={enh.added}
                onToggle={(o) => setPrompt(enh.toggle(prompt, o))}
                onUndo={undoEnhance}
              />
            ) : null}
            <div className="flex flex-col gap-2">
              <span className="text-label-sm font-medium uppercase tracking-wide text-outline">Try an edit:</span>
              <div className="flex flex-wrap gap-1.5">
                {(allExamples ? EDIT_EXAMPLES : EDIT_EXAMPLES.slice(0, 3)).map((e) => (
                  <button
                    key={e}
                    type="button"
                    title={e}
                    disabled={!canAct}
                    onClick={() => {
                      setPrompt(e);
                      textarea.current?.focus();
                    }}
                    className="min-h-8 max-w-full truncate rounded-lg bg-surface-container-low px-3 py-1.5 text-left text-label-sm text-on-surface-variant transition-colors hover:bg-surface-container hover:text-on-surface disabled:opacity-50"
                  >
                    {truncate(e, 52)}
                  </button>
                ))}
                <button
                  type="button"
                  aria-expanded={allExamples}
                  onClick={() => setAllExamples(!allExamples)}
                  className="min-h-8 rounded-lg px-2 text-label-sm font-semibold text-primary hover:underline"
                >
                  {allExamples ? "Fewer" : `+ ${EDIT_EXAMPLES.length - 3} more`}
                </button>
              </div>
            </div>
            {/* the asset the edit uses */}
            <div>
              <div
                role="button"
                tabIndex={canAct ? 0 : -1}
                aria-disabled={!canAct}
                onClick={() => canAct && fileRef.current?.click()}
                onKeyDown={(e) => {
                  if (canAct && (e.key === "Enter" || e.key === " ")) {
                    e.preventDefault();
                    fileRef.current?.click();
                  }
                }}
                onDragOver={(e) => e.preventDefault()}
                onDrop={async (e) => {
                  e.preventDefault();
                  if (!canAct || !e.dataTransfer.files.length) return;
                  const names = await upload([...e.dataTransfer.files]);
                  if (names) setFiles((f) => [...new Set([...f, ...names])]);
                }}
                className={cx(
                  "relative flex items-center justify-between gap-3 rounded-xl border border-dashed border-outline-variant/60 p-3.5 transition-colors",
                  canAct ? "cursor-pointer hover:bg-surface-container-low/40" : "cursor-not-allowed opacity-60",
                )}
              >
                {canAct ? (
                  <input
                    type="file"
                    multiple
                    accept="image/*,video/*,audio/*,.png,.jpg,.jpeg,.webp,.heic,.mp4,.mov,.m4v,.webm,.wav,.mp3,.m4a,.aac,.ogg,.flac"
                    title="Choose files from your computer"
                    aria-label="Choose files from your computer"
                    className="absolute inset-0 z-10 h-full w-full cursor-pointer opacity-0"
                    onClick={(e) => e.stopPropagation()}
                    onChange={async (e) => {
                      const list = e.target.files ? [...e.target.files] : [];
                      e.target.value = "";
                      if (!list.length) return;
                      const names = await upload(list);
                      if (names) setFiles((f) => [...new Set([...f, ...names])]);
                    }}
                  />
                ) : null}
                <span className="flex items-center gap-3">
                  <span className="flex size-8 items-center justify-center rounded-lg bg-surface-container text-primary">
                    <ImagePlus aria-hidden className="size-[18px]" />
                  </span>
                  <span className="flex flex-col">
                    <span className="text-label-md font-medium text-on-surface">Attach the asset the edit uses</span>
                    <span className="text-body-sm text-on-surface-variant">A picture, a texture, a music track, or an MP4 this tool made</span>
                  </span>
                </span>
                <span className="rounded-md bg-surface-container px-2.5 py-1 text-label-sm text-on-surface-variant">Browse</span>
              </div>
              <SampleAssets onAttach={attachSample} disabled={!canAct} className="mt-2" />
              <input
                ref={fileRef}
                type="file"
                multiple
                className="hidden"
                tabIndex={-1}
                aria-hidden
                accept="image/*,video/*,audio/*,.png,.jpg,.jpeg,.webp,.heic,.mp4,.mov,.m4v,.webm,.wav,.mp3,.m4a,.aac,.ogg,.flac"
                onChange={async (e) => {
                  const list = e.target.files ? [...e.target.files] : [];
                  e.target.value = "";
                  if (!list.length) return;
                  const names = await upload(list);
                  if (names) setFiles((f) => [...new Set([...f, ...names])]);
                }}
              />
              {files.length ? (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {files.map((f) => (
                    <span key={f} className="inline-flex max-w-full items-center gap-1 rounded-full bg-secondary-fixed/50 py-0.5 pl-3 pr-1 text-label-sm text-on-secondary-fixed">
                      <Paperclip aria-hidden className="size-3.5 shrink-0" />
                      <span className="truncate">{f}</span>
                      <button type="button" aria-label={`Remove ${f}`} onClick={() => setFiles((x) => x.filter((y) => y !== f))} className="flex size-6 items-center justify-center rounded-full hover:bg-secondary-fixed">
                        <X aria-hidden className="size-3.5" />
                      </button>
                    </span>
                  ))}
                </div>
              ) : null}
              {uploadError ? (
                <p role="alert" className="mt-2 text-body-sm font-semibold text-error">
                  {uploadError}
                </p>
              ) : null}
            </div>
            <div className="flex flex-col items-center gap-2">
              <Button variant="primary" size="lg" icon={Wand2} className="w-full" disabled={disabled} onClick={() => void apply()}>
                {job.running && job.kind !== "review" ? "Working…" : "Apply change"}
              </Button>
              {notice || engine.otherBusy || !canAct ? (
                <p role="status" className="text-center text-body-sm text-amber">
                  {notice ||
                    (engine.otherBusy
                      ? "The engine is making another creative; one at a time."
                      : fromShowcase
                        ? "A read-only showcase copy: editing needs the studio engine online."
                        : "The engine is offline.")}
                </p>
              ) : null}
              {prompt || files.length ? (
                <button
                  type="button"
                  onClick={() => {
                    setPrompt("");
                    setFiles([]);
                    setPlanned(null);
                  }}
                  className="min-h-9 px-2 text-label-sm text-on-surface-variant hover:text-on-surface"
                >
                  Reset request
                </button>
              ) : null}
            </div>
          </Card>
          <Inventory
            v={v}
            items={items}
            actions={
              canAct
                ? {
                    disabled,
                    direct: (op, label) => void direct(op, label),
                    upload: async (f) => (await upload([f]))?.[0] ?? null,
                  }
                : null
            }
          />
          {canAct ? (
            <details className="group">
              <summary className="inline-flex min-h-10 cursor-pointer items-center gap-1.5 rounded-lg px-1 text-label-md font-semibold text-on-surface-variant hover:text-on-surface">
                <ChevronDown aria-hidden className="size-4 transition-transform group-open:rotate-180" />
                More: music
              </summary>
              <div className="mt-3">
                <SoundtrackCard v={v} useDisabled={disabled} onUse={(file) => direct({ music: file }, `Music: ${file}`)} />
              </div>
            </details>
          ) : null}
        </div>

        {/* CENTRE: the player, the versions timeline, the work in progress */}
        <div className="flex min-w-0 flex-col gap-4 lg:col-span-7 xl:col-span-5">
          <div className="mx-auto flex w-full max-w-[420px] flex-wrap items-center justify-between gap-2 px-1">
            {prev ? (
              <div role="tablist" aria-label="Player view" className="flex rounded-full bg-surface-container-low p-1">
                {[
                  [false, "This version"],
                  [true, "Before / after"],
                ].map(([on, label]) => (
                  <button
                    key={String(on)}
                    type="button"
                    role="tab"
                    aria-selected={pairView === on}
                    onClick={() => setPairView(on as boolean)}
                    className={cx(
                      "min-h-9 rounded-full px-3.5 text-label-sm transition-all",
                      pairView === on ? "bg-primary-fixed font-semibold text-on-primary-fixed shadow-xs" : "text-on-surface-variant hover:text-on-surface",
                    )}
                  >
                    {on ? <ArrowLeftRight aria-hidden className="mr-1 inline size-3.5" /> : null}
                    {label as string}
                  </button>
                ))}
              </div>
            ) : (
              <span className="text-label-sm text-on-surface-variant">The first version</span>
            )}
            <span className="text-label-sm text-on-surface-variant">
              {v.brief?.format || "9:16"} · {v.length_s} s
            </span>
          </div>
          {showPair && prev ? (
            <Card label="Before and after" className="!p-4">
              <Pair before={prev} after={v} />
            </Card>
          ) : (
            <PhoneFrame label={`v${v.n} of this creative`} className="!max-w-[380px] [max-width:min(380px,calc(70vh*9/16))]">
              <VersionVideo v={v} />
            </PhoneFrame>
          )}
          {/* version timeline */}
          <div className="mx-auto w-full max-w-[420px] rounded-xl border border-surface-variant bg-surface-container-lowest p-3">
            <div className="mb-2 flex items-center justify-between text-label-sm font-semibold text-on-surface-variant">
              <span>Version timeline</span>
              <span className="font-mono text-code-sm text-primary">{versions.length} total</span>
            </div>
            <div role="tablist" aria-label="Versions" className="flex gap-1.5 overflow-x-auto pb-1">
              {versions.map((x) => (
                <button
                  key={x.n}
                  type="button"
                  role="tab"
                  aria-selected={x.n === v.n}
                  title={x.edit ? `an edit of v${x.from ?? x.n - 1}: ${x.prompt}` : `the first version: ${x.prompt}`}
                  onClick={() => setSelected(x.n)}
                  className={cx(
                    "min-h-9 shrink-0 whitespace-nowrap rounded-lg px-2.5 text-label-sm transition-colors",
                    x.n === v.n ? "bg-primary-fixed font-semibold text-on-primary-fixed ring-1 ring-primary/20" : "bg-surface-container-low text-on-surface-variant hover:bg-surface-container",
                  )}
                >
                  v{x.n}
                  {x.edit ? <span className="opacity-70"> ← v{x.from ?? x.n - 1}</span> : null}
                </button>
              ))}
            </div>
          </div>
          <p className="mx-auto w-full max-w-[420px] text-body-sm text-on-surface-variant">
            <b className="text-on-surface">v{v.n} prompt:</b> {v.prompt}
          </p>
          <FeedbackPanel />
          {job.running || job.error || (details && job.lines.length) ? (
            <Progress
              title={lastAction ? `Progress: ${truncate(lastAction, 48)}` : "Progress"}
              stage={job.stage}
              done={job.done}
              lines={job.lines}
              elapsed={job.elapsed}
              error={job.error}
              trace={job.trace}
              live={job.running}
            />
          ) : null}
          {planned && (details || job.running || (planned.needs || []).length) ? (
            <Understood
              heading="What the tool understood"
              brief={planned}
              meta={engine.meta}
              title={job.running ? "Planned edit (being made)" : "Planned edit (not made yet)"}
              busy={job.running}
              flags={false}
              onAttach={() => fileRef.current?.click()}
              onMakeWithout={() => void makeEdit(planned, plannedPrompt, v.n, true).catch(() => null)}
            />
          ) : details && v.brief ? (
            <Understood heading="What the tool understood" brief={v.brief} meta={engine.meta} title={`Brief of v${v.n}, after the engine's checks`} />
          ) : null}
          {details ? <VersionGameplay v={v} /> : null}
        </div>

        {/* RIGHT: what changed; with Details, compare, the viewer, metadata, the files */}
        <div className="flex min-w-0 flex-col gap-5 lg:col-span-12 xl:col-span-3">
          <WhatChanged
            v={v}
            last={last}
            canAct={canAct}
            details={details}
            onDetails={() => setDetails(!details)}
            review={reviews[v.n]}
            onReview={() => void review()}
            reviewing={job.running && job.kind === "review"}
            disabled={disabled}
          />
          {details ? (
            <>
              <Compare cid={cid} versions={versions} v={v} enabled={canAct} />
              <ReviewCard
                v={v}
                override={reviews[v.n]}
                onRun={canAct ? () => void review() : undefined}
                running={job.running && job.kind === "review"}
                disabled={disabled}
              />
              <Metadata v={v} />
              <VersionLinks v={v} />
            </>
          ) : null}
        </div>
      </div>
      </FeedbackPanelProvider>

      {picker ? <PickerSheet current={cid} onClose={() => setPicker(false)} /> : null}
    </PinnedSource>
  );
}

/** The header's small "Details" switch (the same state as the What changed card's Details button). */
function DetailsSwitch({ on, onChange }: { on: boolean; onChange: (on: boolean) => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      onClick={() => onChange(!on)}
      title="Show the full edit report, Compare, the level and moves, metadata and files"
      className="inline-flex min-h-10 items-center gap-2 rounded-xl px-2 text-label-md text-on-surface-variant hover:text-on-surface"
    >
      <span aria-hidden className={cx("relative inline-flex h-5 w-9 shrink-0 rounded-full transition-colors", on ? "bg-primary-container" : "bg-surface-container-high ring-1 ring-outline-variant/50")}>
        <span className={cx("absolute top-0.5 size-4 rounded-full bg-surface-container-lowest shadow-sm transition-all", on ? "left-[18px]" : "left-0.5")} />
      </span>
      Details
    </button>
  );
}

/** ONE card for a designer: the verdict and the Locked / Allowed / Forbidden contract (with Details, the full report),
 * the viewer's verdict in a line, Download report and Details. */
function WhatChanged({
  v,
  last,
  canAct,
  details,
  onDetails,
  review,
  onReview,
  reviewing,
  disabled,
}: {
  v: Version;
  last: Version | undefined;
  canAct: boolean;
  details: boolean;
  onDetails: () => void;
  review?: Review;
  onReview: () => void;
  reviewing: boolean;
  disabled: boolean;
}) {
  const { review: rev, loaded } = useReview(v, review);
  const line = reviewLine(rev);
  return (
    <Card label="What changed" className="border border-surface-variant !p-5">
      <CardTitle icon={FileClock} as="h2">
        What changed
      </CardTitle>
      {v.proof ? (
        <>
          <p className="mb-3 text-label-sm font-semibold uppercase tracking-wider text-outline">
            What v{v.n} changed from v{v.from ?? v.n - 1}
          </p>
          <EditReport pr={v.proof as Proof} rows={details} />
        </>
      ) : (
        <div className="rounded-xl border border-outline-variant/30 bg-surface-container-low/50 p-3.5">
          <p className="flex items-center gap-2 text-label-sm font-semibold text-primary">
            <Info aria-hidden className="size-4" /> The first version
          </p>
          <p className="mt-1 text-body-sm leading-relaxed text-on-surface-variant">
            {canAct
              ? `Describe a change on the left and press Apply: v${(last?.n ?? 0) + 1} is made from v${v.n}, and its report lists every item kept and changed.`
              : "Pick an edited version to read what it changed."}
          </p>
        </div>
      )}
      <div className="mt-4 border-t border-surface-variant pt-4">
        {line ? (
          <p className="flex items-start gap-2 text-body-sm text-on-surface">
            <Eye aria-hidden className="mt-0.5 size-4 shrink-0 text-secondary" />
            <span>{line}</span>
          </p>
        ) : (
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-body-sm text-on-surface-variant">{loaded ? (rev?.error ? `The review failed: ${rev.error}` : "Not reviewed as a viewer yet.") : "Loading the review…"}</span>
            {canAct && loaded ? (
              <Button size="sm" variant="ghost" icon={Eye} onClick={onReview} disabled={disabled || reviewing}>
                {reviewing ? "Reviewing…" : "Review as a viewer"}
              </Button>
            ) : null}
          </div>
        )}
      </div>
      <div className="mt-4 flex flex-col gap-2">
        {canAct ? <ReportButton cid={v.id} n={v.n} block /> : null}
        <Button variant="ghost" icon={SlidersHorizontal} aria-pressed={details} onClick={onDetails} className="w-full">
          Details
        </Button>
      </div>
    </Card>
  );
}

function Compare({ cid, versions, v, enabled }: { cid: string; versions: Version[]; v: Version; enabled: boolean }) {
  const { conn } = useEngine();
  const [a, setA] = useState<number>(v.from ?? versions[0]?.n ?? v.n);
  const [b, setB] = useState<number>(v.n);
  const [res, setRes] = useState<{ a: number; b: number; pr: Proof } | null>(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    // follow the selected version
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setA(v.from ?? versions[0]?.n ?? v.n);
    setB(v.n);
    setRes(null);
  }, [v.n, v.from, versions]);
  if (versions.length < 2) return null;
  async function go() {
    setErr("");
    setLoading(true);
    try {
      setRes({ a, b, pr: await engineGet<Proof>(conn, `/api/compare/${encodeURIComponent(cid)}?a=${a}&b=${b}`) });
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setLoading(false);
    }
  }
  const sel = (value: number, set: (n: number) => void, label: string) => (
    <label className="flex flex-1 flex-col gap-1 text-label-sm text-on-surface-variant">
      {label}
      <select
        value={value}
        onChange={(e) => set(Number(e.target.value))}
        className="min-h-10 rounded-lg bg-surface-container-low px-2 text-body-md text-on-surface outline-none focus:ring-2 focus:ring-primary-container"
      >
        {versions.map((x) => (
          <option key={x.n} value={x.n}>
            v{x.n}
          </option>
        ))}
      </select>
    </label>
  );
  return (
    <Card label="Compare" className="border border-surface-variant !p-5">
      <CardTitle icon={GitCompare} as="h2">
        Compare
      </CardTitle>
      <div className="flex items-end gap-2">
        {sel(a, setA, "Version")}
        {sel(b, setB, "with")}
        <Button size="sm" variant="ghost" onClick={() => void go()} disabled={!enabled || loading || a === b} className="!min-h-10">
          {loading ? "…" : "Compare"}
        </Button>
      </div>
      {!enabled ? <Muted className="mt-2">Comparing any two versions needs the studio engine online.</Muted> : null}
      {err ? <ErrorBox message={err} /> : null}
      {res ? (
        <div className="mt-4">
          <p className="mb-3 text-label-sm font-semibold uppercase tracking-wider text-outline">
            v{res.a} compared with v{res.b}
          </p>
          <EditReport pr={res.pr} compact flags={false} />
        </div>
      ) : null}
    </Card>
  );
}

function Metadata({ v }: { v: Version }) {
  const source = useSource();
  const [lv, setLv] = useState<{ key: string; level: Record<string, number> | null } | null>(null);
  const key = `${source.live}:${v.level.file}`;
  useEffect(() => {
    let live = true;
    source.json<Record<string, number>>(v.level.file).then((l) => {
      if (live) setLv({ key, level: l });
    });
    return () => {
      live = false;
    };
  }, [source, v.level.file, key]);
  const level = lv && lv.key === key ? lv.level : null;
  const size = boardSize(level, v.level.why);
  const rows: [string, string][] = [
    ["Level", v.level.why],
    ...(size ? ([["Board size", size]] as [string, string][]) : []),
    ["Format", v.brief?.format || "9:16"],
    ["Length", `${v.length_s} s`],
    ["Made in", `${v.seconds} s`],
    ["Gameplay", v.recording.reused ? "recording reused (not re-filmed)" : "recorded in the game"],
    ...(v.workflow ? ([["Workflow", WORKFLOW_WORDS[v.workflow] || v.workflow]] as [string, string][]) : []),
    ...(v.created ? ([["Made", v.created]] as [string, string][]) : []),
  ];
  return (
    <Card label="Metadata" className="border border-surface-variant !p-5">
      <p className="mb-2 text-label-sm font-semibold uppercase tracking-wider text-on-surface-variant">Metadata</p>
      <dl className="flex flex-col">
        {rows.map(([k, x]) => (
          <div key={k} className="flex justify-between gap-4 border-b border-surface-variant/60 py-1.5 last:border-b-0">
            <dt className="shrink-0 text-body-sm text-on-surface-variant">{k}</dt>
            <dd className="min-w-0 text-right text-label-sm font-semibold text-on-surface">{x}</dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}

function PickerSheet({ current, onClose }: { current: string; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal();
  }, []);
  return (
    <dialog
      ref={ref}
      aria-labelledby="picker-title"
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
      className="m-0 mr-auto h-dvh max-h-dvh w-[min(100vw,440px)] max-w-none overflow-y-auto bg-background p-0 text-on-surface shadow-xl backdrop:bg-inverse-surface/40"
    >
      <div className="flex flex-col gap-4 p-5">
        <div className="flex items-center justify-between">
          <h2 id="picker-title" className="font-headline text-headline-md">
            Creatives
          </h2>
          <button type="button" onClick={onClose} aria-label="Close" className="flex size-10 items-center justify-center rounded-lg text-outline hover:bg-surface-container hover:text-on-surface">
            <X aria-hidden className="size-5" />
          </button>
        </div>
        <Picker current={current} onPick={onClose} compact />
      </div>
    </dialog>
  );
}
