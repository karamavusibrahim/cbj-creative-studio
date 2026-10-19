"use client";

import {
  ArrowLeft,
  AudioLines,
  Brain,
  ChevronDown,
  Clock,
  Flag,
  Gauge,
  Layers,
  Plus,
  Smartphone,
  SlidersHorizontal,
  SquarePen,
  Sparkles,
  Wand2,
  X,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { uploadFiles } from "@/lib/engine";
import { sentKeys, useOwnKeys } from "@/lib/keys";
import { plannerLabel } from "@/lib/ownEngine";
import type { Brief, Preview, Version } from "@/lib/types";
import { HELPERS, IDEAS, helperSentences, mergePrompt, type HelperChoice, type HelperKey } from "@/lib/words";
import { plannerName, useEngine } from "../EngineProvider";
import { GameplayCard } from "../Gameplay";
import VersionGameplay from "../Gameplay";
import OfflineBanner from "../OfflineBanner";
import { PhoneFrame, VersionVideo } from "../Player";
import Progress from "../Progress";
import Recent, { useRecent } from "../Recent";
import ReferenceCard from "../ReferenceCard";
import ReviewCard from "../ReviewCard";
import SoundtrackCard, { SpokenLines } from "../Soundtrack";
import Understood from "../Understood";
import useJob from "../useJob";
import { DownloadLink, VersionFacts, VersionLinks, versionLine } from "../VersionBits";
import { Badge, Button, Card, CardTitle, Fact, Muted, Segmented, cx } from "../ui";
import { EnhanceButton, EnhancedCard, useEnhance } from "../Enhance";
import { FeedbackButton } from "../FeedbackDialog";
import FeedbackPanel, { FeedbackPanelProvider } from "../FeedbackPanel";
import ReportButton from "../ReportButton";
import Attachments, { type Attached } from "./Attachments";
import AudioOptions, { NO_AUDIO, audioRequest, audioWords, type AudioChoice } from "./AudioOptions";
import TrendCard from "./TrendCard";

type Phase = "compose" | "working" | "planned" | "ready";

// the Audio (optional) choice is remembered for the session (SPEC-SOUNDTRACK §5): kept in memory across pages, not stored
let rememberedAudio: AudioChoice = NO_AUDIO;

const TONE_DOT: Record<string, string> = {
  error: "bg-error",
  secondary: "bg-secondary-container",
  outline: "bg-outline",
  tertiary: "bg-tertiary-fixed-dim",
  primary: "bg-primary-fixed-dim",
};

export default function CreateStudio() {
  const engine = useEngine();
  const ownKeys = useOwnKeys();
  const router = useRouter();
  const { job, run, resume, fail } = useJob("create");
  const [phase, setPhase] = useState<Phase>("compose");
  const [prompt, setPrompt] = useState("");
  const [helpers, setHelpers] = useState<HelperChoice>({});
  const [files, setFiles] = useState<Attached[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [brief, setBrief] = useState<Brief | null>(null);
  const [briefPrompt, setBriefPrompt] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [version, setVersion] = useState<Version | null>(null);
  const [opts, setOpts] = useState({ draft: false, review: true, revise: true });
  const [more, setMore] = useState(false);
  const [audio, setAudioState] = useState<AudioChoice>(() => rememberedAudio);
  const [audioAsked, setAudioAsked] = useState(false);
  const [nonce, setNonce] = useState(0);
  const [notice, setNotice] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const top = useRef<HTMLDivElement>(null);

  const online = engine.status === "online";
  const working = job.running || uploading;
  const blocked = !online || engine.otherBusy;
  const full = mergePrompt(prompt, helpers);
  const sentences = helperSentences(helpers);
  const { items: latest } = useRecent(1, nonce);
  const enh = useEnhance<{ prompt: string; helpers: HelperChoice }>();
  const hasVoice = engine.meta?.features?.soundtrack?.voice === true;

  function setAudio(c: AudioChoice) {
    rememberedAudio = c;
    setAudioState(c);
  }

  async function enhance() {
    const r = await enh.enhance({ prompt: full, uploads: files.map((f) => f.name) }, { prompt, helpers });
    if (r?.changed) {
      // the helper sentences are inside the rewrite now: clear the chips so they are not appended twice
      setPrompt(r.prompt);
      setHelpers({});
    }
  }

  function undoEnhance() {
    if (enh.snapshot) {
      setPrompt(enh.snapshot.prompt);
      setHelpers(enh.snapshot.helpers);
    }
    enh.clear();
    textarea.current?.focus();
  }

  function applyTrend(p: string) {
    setPrompt(p);
    enh.clear();
    textarea.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    textarea.current?.focus({ preventScroll: true });
  }

  // after a reload: pick up a plan or make that was running
  const resumed = useRef(false);
  useEffect(() => {
    if (!online || resumed.current) return;
    resumed.current = true;
    void (async () => {
      const r = await resume();
      if (!r) return;
      const p = String(r.stored.context?.prompt || "");
      if ((r.stored.kind === "make" || r.stored.kind === "direct") && r.result) {
        setVersion(r.result as Version);
        setBrief((r.result as Version).brief);
        setPhase("ready");
        setNonce((n) => n + 1);
      } else if (r.stored.kind === "plan" && r.result) {
        setBrief(r.result as Brief);
        setBriefPrompt(p);
        setPhase("planned");
      }
    })();
  }, [online, resume]);

  // while our job runs after a reload, show the working view
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (job.running && phase === "compose") setPhase("working");
  }, [job.running, phase]);

  async function ready(): Promise<boolean> {
    if (!online) {
      setNotice("The studio engine is offline: nothing can be made right now. The Showcase has finished creatives.");
      return false;
    }
    if (engine.otherBusy) {
      setNotice("The engine is making another creative; one at a time.");
      return false;
    }
    setNotice("");
    return engine.ensureUnlocked();
  }

  async function upload(list: File[]): Promise<boolean> {
    if (!list.length || !(await ready())) return false;
    setUploading(true);
    setUploadError("");
    try {
      const names = await uploadFiles(engine.conn, list);
      setFiles((fs) => {
        const out = [...fs];
        names.forEach((n, i) => {
          if (out.some((x) => x.name === n)) return;
          const f = list[i];
          out.push({ name: n, size: f?.size, local: f && f.type.startsWith("image/") ? URL.createObjectURL(f) : undefined });
        });
        return out;
      });
      void engine.refreshMeta();
      return true;
    } catch (e) {
      setUploadError((e as Error).message);
      return false;
    } finally {
      setUploading(false);
    }
  }

  async function make(b: Brief, p: string, withoutFiles = false) {
    if ((b.needs || []).length && !withoutFiles) {
      fail(`Attach ${(b.needs || []).join(" and ")} and generate again, or choose "Make it without them".`);
      return;
    }
    setPhase("working");
    // the optional audio, only when a box is on (a draft is made without it: the engine skips it)
    const a = opts.draft || !engine.meta?.features?.soundtrack ? null : audioRequest(audio, hasVoice);
    setAudioAsked(Boolean(a));
    try {
      const v = await run<Version>(
        "/api/make",
        { prompt: p, brief: b, draft: opts.draft, review: opts.review, revise: opts.revise, without_files: withoutFiles, ...(a ? { audio: a } : {}) },
        "make",
        { prompt: p },
        true,
      );
      setVersion(v);
      setBrief(v.brief);
      setPhase("ready");
      setPrompt("");
      setHelpers({});
      setFiles([]);
      enh.clear();
      setNonce((n) => n + 1);
      void engine.refreshMeta();
      top.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch {
      setPhase("planned");
    }
  }

  // the soundtrack card's "Use as the music": the same direct music edit the Edit workspace runs, on the version shown
  async function putMusic(file: string): Promise<number | null> {
    const base = version;
    if (!base || !(await ready())) return null;
    try {
      const nv = await run<Version>("/api/direct", { creative_id: base.id, base: base.n, op: { music: file }, draft: false }, "direct", { prompt: `Music: ${file}` });
      setVersion(nv);
      setBrief(nv.brief);
      setNonce((n) => n + 1);
      return nv.n;
    } catch {
      return null; // the progress card shows the error
    }
  }

  async function plan(thenMake: boolean) {
    if (!full) {
      textarea.current?.focus();
      return;
    }
    if (!(await ready())) return;
    setPhase("working");
    setBrief(null);
    setVersion(null);
    setPreview(null);
    try {
      const b = await run<Brief>("/api/plan", { prompt: full, uploads: files.map((f) => f.name) }, "plan", { prompt: full });
      setBrief(b);
      setBriefPrompt(full);
      const matched = b.planner?.route?.matched;
      if (matched && matched.creative_id) {
        // the attached MP4 is one of this tool's own versions: the change is an edit of it
        router.push(`/edit?c=${encodeURIComponent(matched.creative_id)}&v=${matched.n}&prompt=${encodeURIComponent(full)}&matched=1`);
        return;
      }
      if ((b.needs || []).length || !thenMake) {
        setPhase("planned");
        return;
      }
      await make(b, full);
    } catch {
      setPhase((p) => (p === "working" ? "planned" : p));
    }
  }

  async function levelOnly() {
    if (!(await ready())) return;
    const p = brief && briefPrompt ? briefPrompt : full;
    if (!p) {
      textarea.current?.focus();
      return;
    }
    setPhase("working");
    try {
      let b = brief;
      if (!b || briefPrompt !== p) {
        b = await run<Brief>("/api/plan", { prompt: p, uploads: files.map((f) => f.name) }, "plan", { prompt: p });
        setBrief(b);
        setBriefPrompt(p);
      }
      const d = await run<Preview>("/api/preview", { prompt: p, brief: b }, "preview", { prompt: p }, true);
      const nb = { ...b, controls: d.controls || b.controls };
      setBrief(nb);
      setPreview(d);
      setPhase("planned");
    } catch {
      setPhase("planned");
    }
  }

  function startOver() {
    setPhase("compose");
    setBrief(null);
    setPreview(null);
    setVersion(null);
    setNotice("");
  }

  function setHelper(k: HelperKey, v: string | undefined) {
    setHelpers((h) => ({ ...h, [k]: v }));
  }

  // with an own engine the planner is named as that engine says it (SPEC-OWN-ENGINE §2: "claude-cli/opus · your engine")
  const planner = engine.own ? (engine.meta ? plannerLabel(engine.models, engine.backend) : "") : plannerName(engine.models, engine.backend);
  const sent = sentKeys(ownKeys.keys);
  const mine = engine.own ? " · your engine" : engine.keysAvailable && sent.gemini ? " · your Gemini key" : "";
  const showWork = phase !== "compose";

  return (
    <div ref={top} className="scroll-mt-24">
      <OfflineBanner />
      {/* page header */}
      <div className="mb-8 flex flex-col justify-between gap-4 md:flex-row md:items-end">
        <div className="flex flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-primary-fixed px-2.5 py-0.5 text-label-sm font-semibold uppercase tracking-wider text-on-primary-fixed">
              <span aria-hidden className="size-1.5 rounded-full bg-primary" />
              {online && planner ? `Planner: ${planner}${mine} · one job at a time` : online ? "One job at a time" : engine.status === "checking" ? "Connecting…" : "Engine offline"}
            </span>
            {phase === "ready" && version ? (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-tertiary-fixed px-3 py-0.5 text-label-sm text-on-tertiary-fixed shadow-sm">
                <span aria-hidden className="size-1.5 rounded-full bg-tertiary" />
                Generation complete · {Math.round(version.length_s)} s ad created
              </span>
            ) : null}
          </div>
          <h1 className="font-headline text-headline-xl-mobile text-on-surface sm:text-headline-xl">Create a new creative</h1>
          <p className="max-w-2xl text-body-md text-on-surface-variant">
            {phase === "ready"
              ? "Your creative is made and checked. Review it, download it, or change one thing in the Edit workspace."
              : "Describe the gameplay and the hook you want. Add a reference image or video if you have one."}
          </p>
        </div>
        {showWork && !job.running ? (
          <div className="flex shrink-0 flex-wrap items-center gap-3">
            <Button variant="ghost" icon={phase === "ready" ? Plus : ArrowLeft} onClick={startOver}>
              {phase === "ready" ? "Create another" : "Back to the prompt"}
            </Button>
            {phase === "ready" && version ? (
              <FeedbackButton
                context={{ page: "create", creative_id: version.id, version: version.n, title: version.prompt, workflow: version.workflow || "create" }}
              />
            ) : null}
            {phase === "ready" && version ? <ReportButton cid={version.id} n={version.n} /> : null}
            {phase === "ready" && version ? (
              <Link
                href={`/edit?c=${encodeURIComponent(version.id)}&v=${version.n}`}
                className="inline-flex min-h-10 items-center gap-2 rounded-xl bg-primary-container px-4 py-2 text-label-md font-semibold text-on-primary shadow-sm transition-colors hover:bg-primary"
              >
                <SquarePen aria-hidden className="size-[18px]" /> Edit this creative
              </Link>
            ) : null}
          </div>
        ) : null}
      </div>

      <FeedbackPanelProvider
        context={
          version && phase === "ready"
            ? { page: "create", creative_id: version.id, version: version.n, title: version.prompt, workflow: version.workflow || "create" }
            : { page: "create" }
        }
        edit={Boolean(version?.edit)}
      >
      <div className="mb-12 grid grid-cols-1 items-start gap-6 lg:grid-cols-12 lg:gap-8">
        {/* LEFT: the prompt, or the plan and the progress */}
        <div className="flex min-w-0 flex-col gap-6 lg:col-span-7">
          {!showWork ? (
            <>
              <Card label="Prompt">
                <div className="mb-4 flex items-center justify-between gap-2">
                  <label htmlFor="prompt" className="flex items-center gap-2 text-title-sm text-on-surface">
                    <Brain aria-hidden className="size-5 text-primary-container" />
                    What would you like to create?
                  </label>
                  <span className="font-mono text-code-sm text-outline" aria-live="off">
                    {prompt.length} chars
                  </span>
                </div>
                <div className="rounded-xl bg-surface-container-low p-1 transition-all focus-within:bg-primary-fixed/40">
                  <textarea
                    id="prompt"
                    ref={textarea}
                    rows={5}
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && !working) void plan(true);
                    }}
                    placeholder="e.g. Create a difficult Color Block Jam level with a narrow center section and show gameplay where the player almost fails before solving it."
                    className="block w-full resize-y rounded-lg bg-surface-container-lowest p-4 text-body-md text-on-surface shadow-inner outline-none placeholder:text-outline"
                  />
                  <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
                    <div className="flex min-w-0 flex-wrap gap-1.5">
                      {sentences.length ? (
                        sentences.map((s) => (
                          <span key={s.key} className="inline-flex max-w-full items-center gap-1 rounded-full bg-primary-fixed py-0.5 pl-2.5 pr-1 text-label-sm text-on-primary-fixed">
                            <span className="truncate">+ {s.sentence}</span>
                            <button
                              type="button"
                              aria-label={`Remove “${s.sentence}”`}
                              onClick={() => setHelper(s.key, undefined)}
                              className="flex size-6 items-center justify-center rounded-full hover:bg-primary-fixed-dim"
                            >
                              <X aria-hidden className="size-3.5" />
                            </button>
                          </span>
                        ))
                      ) : (
                        <span className="text-code-sm text-outline">⌘/Ctrl + Enter to generate</span>
                      )}
                    </div>
                    <div className="flex items-center gap-1">
                    <EnhanceButton loading={enh.loading} available={enh.available} hasText={Boolean(full)} onClick={() => void enhance()} />
                    {prompt ? (
                      <button
                        type="button"
                        onClick={() => {
                          setPrompt("");
                          enh.clear();
                          textarea.current?.focus();
                        }}
                        className="flex size-9 items-center justify-center rounded-lg text-outline hover:bg-surface-container hover:text-on-surface"
                        aria-label="Clear the prompt"
                      >
                        <X aria-hidden className="size-[18px]" />
                      </button>
                    ) : null}
                    </div>
                  </div>
                </div>
                <div className="mt-5 flex flex-col gap-2.5">
                  <span className="text-label-sm font-medium uppercase tracking-wide text-outline">Try an idea (a full test-case prompt):</span>
                  <div className="flex flex-wrap gap-2">
                    {IDEAS.map((idea) => (
                      <button
                        key={idea.label}
                        type="button"
                        title={idea.prompt}
                        onClick={() => {
                          setPrompt(idea.prompt);
                          textarea.current?.focus();
                        }}
                        className="inline-flex min-h-9 items-center gap-1.5 rounded-full bg-surface-container px-3 py-1.5 text-label-sm text-on-surface-variant transition-all hover:bg-surface-container-high hover:text-on-surface"
                      >
                        <span aria-hidden className={cx("size-1.5 rounded-full", TONE_DOT[idea.tone])} />
                        {idea.label}
                      </button>
                    ))}
                  </div>
                </div>
              </Card>
              {enh.result || enh.error ? (
                <div className="-mt-2">
                  <EnhancedCard
                    result={enh.result}
                    error={enh.error}
                    added={enh.added}
                    onToggle={(o) => setPrompt(enh.toggle(prompt, o))}
                    onUndo={undoEnhance}
                  />
                </div>
              ) : null}

              <Attachments
                files={files}
                prompt={full}
                earlier={[...(engine.meta?.uploads || []), ...(engine.meta?.videos || [])]}
                onUpload={(l) => void upload(l)}
                onSample={upload}
                onAdd={(n) => setFiles((fs) => (fs.some((f) => f.name === n) ? fs : [...fs, { name: n }]))}
                onRemove={(n) => setFiles((fs) => fs.filter((f) => f.name !== n))}
                disabled={!online || working}
                uploading={uploading}
                error={uploadError}
                inputRef={fileInput}
              />

              <TrendCard hasText={Boolean(prompt.trim())} onUse={applyTrend} />

              <Card label="Creative specifications">
                <CardTitle icon={SlidersHorizontal} tone="tertiary" right={<span className="text-label-sm text-on-surface-variant">Optional</span>}>
                  Creative specifications
                </CardTitle>
                <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
                  <Segmented label={HELPERS.length.label} options={HELPERS.length.options} value={helpers.length} onChange={(v) => setHelper("length", v)} />
                  <Segmented
                    label={HELPERS.format.label}
                    options={HELPERS.format.options}
                    value={helpers.format}
                    onChange={(v) => setHelper("format", v)}
                  />
                  <Segmented
                    label={HELPERS.difficulty.label}
                    options={HELPERS.difficulty.options}
                    value={helpers.difficulty}
                    onChange={(v) => setHelper("difficulty", v)}
                  />
                  <div className="flex flex-col gap-2">
                    <label htmlFor="ending" className="text-label-md text-on-surface">
                      {HELPERS.ending.label}
                    </label>
                    <div className="relative">
                      <select
                        id="ending"
                        value={helpers.ending || ""}
                        onChange={(e) => setHelper("ending", e.target.value || undefined)}
                        className="min-h-12 w-full cursor-pointer appearance-none rounded-xl bg-surface-container-low px-3.5 py-2.5 pr-10 text-label-md text-on-surface outline-none transition-colors focus:bg-surface-container-high"
                      >
                        <option value="">From the prompt</option>
                        {HELPERS.ending.options.map((o) => (
                          <option key={o.id} value={o.id}>
                            {o.text}
                          </option>
                        ))}
                      </select>
                      <ChevronDown aria-hidden className="pointer-events-none absolute right-3 top-1/2 size-5 -translate-y-1/2 text-on-surface-variant" />
                    </div>
                  </div>
                </div>
                <Muted className="mt-4">These add words to your prompt; the plan below shows how they were read.</Muted>
              </Card>

              <ActionPanel
                busy={working}
                blocked={blocked}
                notice={notice || (engine.otherBusy ? "The engine is making another creative; one at a time." : !online && engine.status !== "checking" ? "The engine is offline: making is paused." : "")}
                onGenerate={() => void plan(true)}
                onPlan={() => void plan(false)}
                onLevel={() => void levelOnly()}
                more={more}
                setMore={setMore}
                opts={opts}
                setOpts={setOpts}
                audio={<AudioOptions value={audio} onChange={setAudio} disabled={working} draft={opts.draft} className="mt-4" />}
              />
            </>
          ) : (
            <>
              {phase !== "ready" ? (
                <Card label="Your request" className="!p-5">
                  <p className="mb-1 text-label-sm font-semibold uppercase tracking-wider text-outline">Your request</p>
                  <p className="text-body-md text-on-surface">{briefPrompt || full}</p>
                  {files.length ? <Muted className="mt-1">Attached: {files.map((f) => f.name).join(", ")}</Muted> : null}
                  {phase === "planned" && !opts.draft && audioRequest(audio, hasVoice) && engine.meta?.features?.soundtrack ? (
                    <Muted className="mt-1">Audio after the make: {audioWords(audio, hasVoice)}.</Muted>
                  ) : null}
                  {phase === "planned" && brief && !job.running ? (
                    <div className="mt-4 flex flex-wrap gap-2">
                      <Button variant="primary" icon={Sparkles} disabled={blocked} onClick={() => void make(brief, briefPrompt)}>
                        Make it
                      </Button>
                      {!preview ? (
                        <Button variant="ghost" icon={Layers} disabled={blocked} onClick={() => void levelOnly()}>
                          Level only
                        </Button>
                      ) : null}
                    </div>
                  ) : null}
                </Card>
              ) : null}
              {brief ? (
                <Understood
                  brief={brief}
                  meta={engine.meta}
                  title={version ? `Brief of v${version.n}, after the engine's checks` : "Planned (not made yet)"}
                  busy={job.running}
                  onAttach={() => setPhase("compose")}
                  onMakeWithout={() => void make(brief, briefPrompt, true)}
                />
              ) : null}
              {brief ? <ReferenceCard brief={brief} /> : null}
              {phase !== "ready" || job.lines.length || job.running || job.error ? (
                <Progress
                  stage={job.stage}
                  done={job.done}
                  lines={job.lines}
                  elapsed={job.elapsed}
                  error={job.error}
                  trace={job.trace}
                  live={job.running}
                  audio={audioAsked || job.lines.some((l) => l.stage === "audio")}
                />
              ) : null}
              {preview && !version ? (
                <GameplayCard
                  title="Preview: the level and the planned moves, not recorded yet. Make it to record it."
                  data={{ board: preview.board, level_why: preview.level_why, beats: preview.beats || [], notes: preview.notes, frames: preview.frames, checks: preview.checks }}
                />
              ) : null}
              {version ? <VersionGameplay v={version} /> : null}
              {version ? <ReviewCard v={version} reviewOf={version.audio_added?.from_version} /> : null}
            </>
          )}
        </div>

        {/* RIGHT: the preview, or the creative */}
        <div className="flex min-w-0 flex-col gap-6 lg:col-span-5">
          {version && phase === "ready" ? (
            <>
              <Card label="Creative" className="flex flex-col items-center">
                <PhoneFrame label={`v${version.n}, ${version.length_s} seconds`}>
                  <VersionVideo v={version} />
                </PhoneFrame>
                <div className="mt-5 w-full">
                  {version.audio_added ? (
                    <div className="mb-4 flex flex-col gap-1.5 border-b border-outline-variant/30 pb-4">
                      <span className="inline-flex items-center gap-1.5 self-start rounded-full bg-secondary-fixed px-2.5 py-0.5 text-label-sm font-semibold text-on-surface">
                        <AudioLines aria-hidden className="size-3.5 text-secondary" /> With audio
                      </span>
                      <p className="text-body-sm text-on-surface-variant">{version.audio_added.description}</p>
                      {version.audio_added.voice_skipped ? <p className="text-body-sm text-amber">Voice skipped: {version.audio_added.voice_skipped}</p> : null}
                      <SpokenLines voice={version.audio_added.voice} />
                    </div>
                  ) : null}
                  <VersionFacts v={version} />
                  <p className="mt-3 text-body-sm text-on-surface-variant">{versionLine(version)}</p>
                  {version.qa?.warnings?.length ? <p className="mt-1 text-body-sm text-amber">QA: {version.qa.warnings.join("; ")}</p> : null}
                  <div className="mt-4 flex flex-col gap-2 sm:flex-row">
                    <Link
                      href={`/edit?c=${encodeURIComponent(version.id)}&v=${version.n}`}
                      className="inline-flex min-h-12 flex-1 items-center justify-center gap-2 rounded-xl bg-primary-container px-5 py-3 text-label-md font-semibold text-on-primary shadow-sm transition-colors hover:bg-primary"
                    >
                      <SquarePen aria-hidden className="size-[18px]" /> Edit this creative
                    </Link>
                    <DownloadLink v={version} className="flex-1" />
                  </div>
                  <VersionLinks v={version} />
                </div>
              </Card>
              <FeedbackPanel />
              <SoundtrackCard v={version} useDisabled={blocked || job.running} onUse={putMusic} />
              <section className="relative flex flex-col gap-3 overflow-hidden rounded-2xl bg-gradient-to-br from-surface-container to-surface-container-high p-6 shadow-sm">
                <span aria-hidden className="pointer-events-none absolute -bottom-6 -right-6 size-32 rounded-full bg-primary-fixed-dim/30 blur-2xl" />
                <h2 className="flex items-center gap-2 text-title-sm text-primary">
                  <Wand2 aria-hidden className="size-5" /> Need to tweak something?
                </h2>
                <p className="text-body-md text-on-surface-variant">
                  Open it in the <b className="text-on-surface">Edit workspace</b> and describe one change: a caption, the background, a picture,
                  the music, a second mistake. Everything you do not mention stays as it is, and the edit report proves it.
                </p>
                <Link
                  href={`/edit?c=${encodeURIComponent(version.id)}&v=${version.n}`}
                  className="inline-flex min-h-10 items-center gap-1 self-start text-label-md font-semibold text-primary hover:underline"
                >
                  Edit this creative →
                </Link>
              </section>
            </>
          ) : (
            <Card label="Your preview" className="flex flex-col items-center">
              <div className="mb-4 flex w-full items-center justify-between">
                <span className="flex items-center gap-2 text-title-sm text-on-surface">
                  <span aria-hidden className={cx("size-2.5 rounded-full", job.running ? "animate-pulse bg-amber" : "bg-tertiary-fixed-dim")} />
                  Your preview
                </span>
                <Badge tone={job.running ? "amber" : "grey"}>
                  {job.running ? (job.kind === "plan" ? "Planning…" : job.lines.some((l) => l.stage === "audio") ? "Adding the audio…" : "Making…") : "Ready"}
                </Badge>
              </div>
              <Muted className="mb-5 w-full">
                {job.running
                  ? "The finished ad plays here when it is made. Meanwhile, the latest creative:"
                  : "The finished ad plays here. Until then, the latest creative made with this tool:"}
              </Muted>
              <PhoneFrame label="The latest creative's poster">
                {latest?.[0]?.poster ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={latest[0].poster} alt="" className={cx("absolute inset-0 h-full w-full object-cover", job.running && "opacity-60")} />
                ) : null}
                <span className="absolute left-3 top-3 inline-flex items-center gap-1 rounded-full bg-black/60 px-2 py-0.5 text-label-sm text-white backdrop-blur-md">
                  <span aria-hidden className="size-2 rounded-full bg-tertiary-fixed-dim" />
                  {latest?.[0] ? "Latest creative" : "No creative yet"}
                </span>
                {job.running ? (
                  <span className="absolute inset-x-3 bottom-3 rounded-xl bg-black/70 p-2.5 text-label-sm text-white backdrop-blur-md">
                    {job.lines.length ? job.lines[job.lines.length - 1].text.slice(0, 120) : "Starting…"}
                  </span>
                ) : null}
              </PhoneFrame>
              <div className="mt-6 flex w-full flex-wrap items-center justify-center gap-2">
                <Fact icon={Smartphone}>{helpers.format ? `${helpers.format} format` : "Format: from the prompt"}</Fact>
                <Fact icon={Clock} tone="secondary">
                  {helpers.length ? `${helpers.length} seconds` : "Length: from the prompt"}
                </Fact>
                <Fact icon={helpers.ending ? Flag : Gauge} tone="tertiary">
                  {helpers.difficulty
                    ? `${HELPERS.difficulty.options.find((o) => o.id === helpers.difficulty)?.text} difficulty`
                    : helpers.ending
                      ? HELPERS.ending.options.find((o) => o.id === helpers.ending)?.text
                      : "Pacing: from the prompt"}
                </Fact>
              </div>
            </Card>
          )}
          <Recent nonce={nonce} />
        </div>
      </div>
      </FeedbackPanelProvider>
    </div>
  );
}

function ActionPanel({
  busy,
  blocked,
  notice,
  onGenerate,
  onPlan,
  onLevel,
  more,
  setMore,
  opts,
  setOpts,
  audio,
}: {
  busy: boolean;
  blocked: boolean;
  notice: string;
  onGenerate: () => void;
  onPlan: () => void;
  onLevel: () => void;
  more: boolean;
  setMore: (b: boolean) => void;
  opts: { draft: boolean; review: boolean; revise: boolean };
  setOpts: (o: { draft: boolean; review: boolean; revise: boolean }) => void;
  /** the Audio (optional) section, above the Generate button */
  audio: React.ReactNode;
}) {
  const check = (k: keyof typeof opts, label: string, title: string) => (
    <label className="flex min-h-10 cursor-pointer items-center gap-2 text-body-md text-on-surface-variant" title={title}>
      <input
        type="checkbox"
        checked={opts[k]}
        onChange={(e) => {
          const on = e.target.checked;
          // a draft is the quick look: no viewer review on it
          setOpts(k === "draft" && on ? { ...opts, draft: true, review: false } : { ...opts, [k]: on });
        }}
        className="size-4 accent-primary-container"
      />
      {label}
    </label>
  );
  return (
    <section aria-label="Generate" className="rounded-2xl bg-surface-container-high p-6 shadow-sm">
      <div className="flex flex-col gap-0.5">
        <span className="text-title-sm font-bold text-on-surface">Ready to generate</span>
        <span className="text-body-sm text-on-surface-variant">
          Plans the request, builds the level, records it in the game, composes the ad and reviews it as a viewer. A few minutes; one creative at a time.
        </span>
      </div>
      {audio}
      <Button variant="primary" size="lg" icon={Sparkles} onClick={onGenerate} disabled={busy || blocked} className="mt-4 w-full whitespace-nowrap sm:ml-auto sm:flex sm:w-auto">
        Generate creative
      </Button>
      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-outline-variant/30 pt-4">
        <Button variant="ghost" size="sm" onClick={onPlan} disabled={busy || blocked}>
          Plan only
        </Button>
        <button
          type="button"
          aria-expanded={more}
          aria-controls="more-options"
          onClick={() => setMore(!more)}
          className="inline-flex min-h-9 items-center gap-1 rounded-lg px-2 text-label-sm font-semibold text-on-surface-variant hover:text-on-surface"
        >
          <ChevronDown aria-hidden className={cx("size-4 transition-transform", more && "rotate-180")} /> More
        </button>
        {notice ? (
          <span role="status" className="flex items-center gap-1.5 text-body-sm text-amber">
            {notice}
          </span>
        ) : null}
      </div>
      {more ? (
        <div id="more-options" className="mt-3 flex flex-col gap-1 rounded-xl bg-surface-container-lowest/70 p-3">
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="ghost" size="sm" icon={Layers} onClick={onLevel} disabled={busy || blocked} title="Plan, build the level and plan the moves, without recording (about 30 s)">
              Level only
            </Button>
            <span className="text-body-sm text-on-surface-variant">The level and the planned moves in about 30 s, without recording.</span>
          </div>
          {check("draft", "Draft: a faster, lower-quality encode, without the review", "Faster, lower-quality encode")}
          {check("review", "Review as a viewer after making", "A multimodal model watches the finished ad as a viewer: match with the prompt, scores, fixes")}
          {check(
            "revise",
            "Revise if the checks miss something (up to 2 rounds)",
            "After making, the tool measures the result against the request and the viewer's review; if something asked for is missed, it makes a revised version. Every version is kept.",
          )}
        </div>
      ) : null}
    </section>
  );
}
