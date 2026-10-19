"use client";

import { CircleAlert, Download, Loader2, Music, SquarePen } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { EngineError, enginePost } from "@/lib/engine";
import type { Narration, Soundtrack, SoundtrackVoice, Version } from "@/lib/types";
import { ENDINGS, NARRATE_TIP, NARRATIONS, NO_VOICE_TIP, VOICES } from "@/lib/words";
import { useEngine } from "./EngineProvider";
import { Button, Card, CardTitle, ErrorBox, Muted, cx } from "./ui";

// "Soundtrack (optional)" (SPEC-SOUNDTRACK §2): a music bed written by the engine from the version's own
// concept, the creative's own captions narrated if asked (§6). The result is an ordinary uploaded WAV; putting it in the ad is the
// existing music edit (`onUse` → /api/direct {music: file}), which makes a new version with its report.
// Used on the Create page (ready) and in the Edit workspace; hidden offline or on an engine without it.

function follows(s: Soundtrack): string[] {
  const c = s.concept;
  const out = [`${c.mood} ${c.mode}, ${c.bpm} bpm${c.bpm_ratio !== 1 ? `, ${c.bpm_ratio > 1 ? "speeding up" : "slowing"} to ${Math.round(c.bpm * c.bpm_ratio)}` : ""}`];
  const n = c.exits.length;
  if (n) out.push(n === 1 ? "1 block exit → a pluck" : `${n} block exits → plucks`);
  out.push(`ending: ${ENDINGS[c.ending] || c.ending.replace(/_/g, " ")}`);
  const ticks = c.hurry_ticks.length;
  if (ticks) out.push(ticks === 1 ? "1 hurry tick" : `${ticks} hurry ticks`);
  out.push(`${s.seconds} s`);
  return out;
}

/** The voice's choices, shared by this card and the Create page's Audio section (SPEC-SOUNDTRACK §6). */
export interface VoiceChoice {
  on: boolean;
  narration: Narration;
  voice: string;
  line: string;
}

export const NO_VOICE: VoiceChoice = { on: false, narration: "captions", voice: VOICES[0].name, line: "" };

/** What the engine takes for the voice: nothing when it is off. */
export function voiceBody(c: VoiceChoice): { voice_name?: string; narration?: Narration; line?: string } {
  return c.on ? { voice_name: c.voice, narration: c.narration, ...(c.line.trim() ? { line: c.line.trim() } : {}) } : {};
}

const field = "min-h-10 w-full rounded-xl bg-surface-container-low px-3 py-2 text-body-md text-on-surface outline-none placeholder:text-outline focus:bg-surface-container-high";

/** "Narrate the captions": the checkbox, All captions / Hook only, the voice, a different first line. */
export function VoiceOptions({
  value,
  onChange,
  hasVoice,
  disabled,
  placeholder,
  id,
}: {
  value: VoiceChoice;
  onChange: (c: VoiceChoice) => void;
  hasVoice: boolean;
  disabled?: boolean;
  placeholder: string;
  /** keeps the help text's id unique when two of these are on a page */
  id: string;
}) {
  const set = (p: Partial<VoiceChoice>) => onChange({ ...value, ...p });
  const on = value.on && hasVoice;
  return (
    <>
      <span title={hasVoice ? NARRATE_TIP : NO_VOICE_TIP} className="inline-flex self-start">
        <label className={cx("flex min-h-10 items-center gap-2 text-body-md", hasVoice ? "cursor-pointer text-on-surface" : "cursor-not-allowed text-on-surface-variant/60")}>
          <input
            type="checkbox"
            checked={on}
            disabled={!hasVoice || disabled}
            onChange={(e) => set({ on: e.target.checked })}
            className="size-4 accent-primary-container"
          />
          Narrate the captions
        </label>
      </span>
      {on ? (
        <div className="flex flex-col gap-2 pl-6">
          <div role="group" aria-label="What is narrated" className="inline-flex self-start rounded-xl bg-surface-container-low p-1">
            {NARRATIONS.map((o) => (
              <button
                key={o.id}
                type="button"
                aria-pressed={value.narration === o.id}
                disabled={disabled}
                onClick={() => set({ narration: o.id })}
                className={cx(
                  "min-h-9 rounded-lg px-3 text-label-sm transition-colors disabled:opacity-50",
                  value.narration === o.id ? "bg-primary-container font-semibold text-on-primary shadow-sm" : "text-on-surface-variant hover:bg-surface-container hover:text-on-surface",
                )}
              >
                {o.text}
              </button>
            ))}
          </div>
          <div className="grid gap-2 @md:grid-cols-[minmax(0,10rem)_minmax(0,1fr)]">
            <label className="flex min-w-0 flex-col gap-1">
              <span className="text-label-sm text-on-surface-variant">Voice</span>
              <select value={value.voice} onChange={(e) => set({ voice: e.target.value })} disabled={disabled} className={cx(field, "cursor-pointer")}>
                {VOICES.map((o) => (
                  <option key={o.name} value={o.name}>
                    {o.text}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex min-w-0 flex-col gap-1">
              <span className="text-label-sm text-on-surface-variant">Different first line</span>
              <input
                value={value.line}
                onChange={(e) => set({ line: e.target.value })}
                disabled={disabled}
                maxLength={120}
                placeholder={placeholder}
                aria-describedby={`${id}-line-help`}
                className={field}
              />
            </label>
          </div>
          <p id={`${id}-line-help`} className="text-body-sm text-on-surface-variant">
            Replaces the hook&apos;s words; the other captions are read as written.
          </p>
        </div>
      ) : null}
    </>
  );
}

/** One row per spoken line: "0.2 s · “Can you beat the clock?”", so the designer sees what is said and when. */
export function SpokenLines({ voice, className }: { voice: SoundtrackVoice | null | undefined; className?: string }) {
  const lines = voice?.lines || [];
  if (!lines.length) return null;
  return (
    <ol aria-label="What is said" className={cx("flex flex-col gap-1", className)}>
      {lines.map((l, i) => (
        <li key={i} className="flex gap-2 text-body-sm text-on-surface">
          <span className="w-16 shrink-0 whitespace-nowrap text-right font-mono text-code-sm leading-5 text-outline">{Math.round(l.at_s * 10) / 10} s ·</span>
          <span className="min-w-0">“{l.text}”</span>
        </li>
      ))}
    </ol>
  );
}

export default function SoundtrackCard({
  v,
  onUse,
  useDisabled,
}: {
  v: Version;
  /** the music edit on this version; resolves the new version's number, or null when it did not happen */
  onUse: (file: string) => Promise<number | null>;
  useDisabled?: boolean;
}) {
  const engine = useEngine();
  const [choice, setChoice] = useState<VoiceChoice>(NO_VOICE);
  const [making, setMaking] = useState<"bed" | "voice" | null>(null);
  const [error, setError] = useState<{ message: string; voice: boolean } | null>(null);
  const [result, setResult] = useState<Soundtrack | null>(null);
  const [using, setUsing] = useState(false);
  const [used, setUsed] = useState<number | null>(null);

  const feature = engine.meta?.features?.soundtrack;
  if (engine.status !== "online" || !feature) return null;
  const hasVoice = feature.voice === true;
  const hook = v.brief?.concept?.hook?.trim() || "";

  // a result belongs to the version it was made from (or the one it was used in); another version shown starts over
  const shown = result && result.creative_id === v.id && (result.version === v.n || used === v.n) ? result : null;

  async function make(withVoice: boolean) {
    if (making || !(await engine.ensureUnlocked())) return;
    setMaking(withVoice ? "voice" : "bed");
    setError(null);
    try {
      const body = withVoice ? { creative_id: v.id, version: v.n, voice: true, ...voiceBody(choice) } : { creative_id: v.id, version: v.n, voice: false };
      setResult(await enginePost<Soundtrack>(engine.conn, "/api/soundtrack", body));
      setUsed(null);
    } catch (e) {
      const message =
        e instanceof EngineError && e.status === 404 ? "This engine has no soundtrack yet (it needs a restart with the new version)." : (e as Error).message;
      setError({ message, voice: withVoice && e instanceof EngineError && e.status === 502 });
    } finally {
      setMaking(null);
    }
  }

  async function apply(file: string) {
    if (using) return;
    setUsing(true);
    try {
      const n = await onUse(file);
      if (n !== null) setUsed(n);
    } finally {
      setUsing(false);
    }
  }

  return (
    <Card label="Soundtrack">
      <CardTitle icon={Music} tone="secondary">
        Soundtrack (optional)
      </CardTitle>
      <Muted>A music bed written from this version&apos;s own concept, and its captions narrated if you want. Nothing changes until you use it.</Muted>

      <div className="mt-3 flex flex-col gap-2">
        <VoiceOptions value={choice} onChange={setChoice} hasVoice={hasVoice} disabled={!!making} placeholder={hook || "Type the words to speak"} id={`st-${v.id}-${v.n}`} />
      </div>

      {shown ? (
        <div className="mt-4 flex flex-col gap-3 rounded-xl bg-surface-container-low p-4">
          <audio controls preload="metadata" src={engine.source.media(shown.path)} className="w-full" aria-label={`Soundtrack ${shown.file}`} />
          <a
            href={engine.source.media(shown.path)}
            download={shown.file}
            target="_blank"
            rel="noreferrer"
            className="inline-flex min-h-9 max-w-full items-center gap-1.5 self-start break-all text-label-sm font-semibold text-secondary hover:underline"
          >
            <Download aria-hidden className="size-4 shrink-0" /> {shown.file}
          </a>
          <p className="text-body-md text-on-surface">{shown.description}</p>
          <SpokenLines voice={shown.voice} />
          {shown.voice_skipped ? (
            <p className="flex items-start gap-1.5 text-body-sm text-amber">
              <CircleAlert aria-hidden className="mt-0.5 size-3.5 shrink-0" />
              {shown.voice_skipped}
            </p>
          ) : null}
          <div>
            <p className="mb-1.5 text-label-sm font-semibold uppercase tracking-wider text-outline">What it follows</p>
            <ul aria-label="What it follows" className="flex flex-wrap gap-1.5">
              {follows(shown).map((f) => (
                <li key={f} className="rounded-full bg-surface-container-lowest px-3 py-1 text-label-sm text-on-surface ring-1 ring-outline-variant/40">
                  {f}
                </li>
              ))}
            </ul>
          </div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            {used !== null ? (
              <p role="status" className="flex flex-wrap items-center gap-x-2 text-label-md font-semibold text-tertiary">
                Used in v{used}
                <Link href={`/edit?c=${encodeURIComponent(v.id)}&v=${used}`} className="inline-flex min-h-9 items-center gap-1 text-primary hover:underline">
                  <SquarePen aria-hidden className="size-4" /> Open v{used}
                </Link>
              </p>
            ) : (
              <Button size="sm" variant="primary" icon={using ? undefined : Music} disabled={useDisabled || using} onClick={() => void apply(shown.file)}>
                {using ? <Loader2 aria-hidden className="size-4 animate-spin motion-reduce:animate-none" /> : null}
                {using ? "Making the new version…" : "Use as the music"}
              </Button>
            )}
            <button
              type="button"
              disabled={using}
              onClick={() => {
                setResult(null);
                setUsed(null);
              }}
              className="min-h-9 px-1 text-label-sm font-semibold text-primary hover:underline disabled:opacity-50"
            >
              Make another
            </button>
          </div>
        </div>
      ) : (
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Button size="sm" variant="primary" icon={making ? undefined : Music} disabled={!!making} aria-busy={!!making} onClick={() => void make(choice.on && hasVoice)}>
            {making ? <Loader2 aria-hidden className="size-4 animate-spin motion-reduce:animate-none" /> : null}
            Make the soundtrack
          </Button>
          <span aria-live="polite" className="text-body-sm text-on-surface-variant">
            {making ? (making === "voice" ? "Writing the bed… and the voice" : "Writing the bed…") : ""}
          </span>
        </div>
      )}

      {error ? (
        <div>
          <ErrorBox message={error.message} />
          {error.voice ? (
            <Button size="sm" variant="ghost" className="mt-2" disabled={!!making} onClick={() => void make(false)}>
              Make it without the voice
            </Button>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}
