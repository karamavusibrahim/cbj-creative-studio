"use client";

import { ChevronDown, Music } from "lucide-react";
import { useState } from "react";
import type { AudioRequest } from "@/lib/types";
import { useEngine } from "../EngineProvider";
import { NO_VOICE, VoiceOptions, voiceBody, type VoiceChoice } from "../Soundtrack";
import { cx } from "../ui";

// "Audio (optional)" inside the Generate card (SPEC-SOUNDTRACK §5, §6): a soundtrack bed from the concept and/or the
// captions narrated, made by the engine after the creative and applied as the existing music edit. Collapsed to one
// row; hidden offline or on an engine without the soundtrack.

export interface AudioChoice {
  bed: boolean;
  voice: VoiceChoice;
}

export const NO_AUDIO: AudioChoice = { bed: false, voice: NO_VOICE };

/** `audio` for /api/make, or null when no box is on (then nothing is sent). */
export function audioRequest(c: AudioChoice, hasVoice: boolean): AudioRequest | null {
  const voice = c.voice.on && hasVoice;
  if (!c.bed && !voice) return null;
  return { bed: c.bed, voice, ...voiceBody({ ...c.voice, on: voice }) };
}

/** In a few words, for the plan's "Audio after the make" line. */
export function audioWords(c: AudioChoice, hasVoice: boolean): string {
  const voice = c.voice.on && hasVoice ? (c.voice.narration === "hook" ? "the hook narrated" : "the captions narrated") : "";
  return [c.bed ? "a soundtrack bed from the concept" : "", voice].filter(Boolean).join(" and ");
}

function summary(c: AudioChoice, hasVoice: boolean): string {
  const voice = c.voice.on && hasVoice;
  if (c.bed && voice) return "Bed + narration";
  if (c.bed) return "Bed";
  if (voice) return "Narration";
  return "Off";
}

export default function AudioOptions({
  value,
  onChange,
  disabled,
  draft,
  className,
}: {
  value: AudioChoice;
  onChange: (c: AudioChoice) => void;
  disabled?: boolean;
  /** a draft is made without the audio (the engine skips it) */
  draft?: boolean;
  className?: string;
}) {
  const engine = useEngine();
  const [open, setOpen] = useState(false);
  const feature = engine.meta?.features?.soundtrack;
  if (engine.status !== "online" || !feature) return null;
  const hasVoice = feature.voice === true;
  const state = summary(value, hasVoice);

  return (
    <div role="group" aria-label="Audio (optional)" className={cx("@container rounded-xl bg-surface-container-lowest/70", className)}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls="audio-options"
        onClick={() => setOpen(!open)}
        className="flex min-h-11 w-full items-center gap-2 rounded-xl px-3 py-2 text-left"
      >
        <Music aria-hidden className="size-4 shrink-0 text-secondary" />
        <span className="text-label-md font-semibold text-on-surface">Audio (optional)</span>
        <span className={cx("ml-auto rounded-full px-2 py-0.5 text-label-sm", state === "Off" ? "text-outline" : "bg-secondary-fixed text-on-surface")}>{state}</span>
        <ChevronDown aria-hidden className={cx("size-4 shrink-0 text-on-surface-variant transition-transform", open && "rotate-180")} />
      </button>
      {open ? (
        <div id="audio-options" className="flex flex-col gap-1 px-3 pb-3">
          <label className="flex min-h-10 cursor-pointer items-center gap-2 self-start text-body-md text-on-surface" title="A music bed written from the creative's own concept">
            <input
              type="checkbox"
              checked={value.bed}
              disabled={disabled}
              onChange={(e) => onChange({ ...value, bed: e.target.checked })}
              className="size-4 accent-primary-container"
            />
            Soundtrack bed from the concept
          </label>
          <VoiceOptions
            value={value.voice}
            onChange={(voice) => onChange({ ...value, voice })}
            hasVoice={hasVoice}
            disabled={disabled}
            placeholder="the hook caption"
            id="make-audio"
          />
          <p className="mt-1 text-body-sm text-on-surface-variant">
            Added after the creative is made, as a music edit you can see in the version history. Nothing else changes.
          </p>
          {draft && state !== "Off" ? <p className="text-body-sm text-amber">A draft is made without the audio; turn Draft off to add it.</p> : null}
        </div>
      ) : null}
    </div>
  );
}
