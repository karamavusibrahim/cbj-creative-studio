"use client";

import { Activity } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { useEffect, useRef } from "react";
import { Card, CardTitle, ErrorBox, cx } from "./ui";

// The Progress card: the stage strip and the live log, like the engine page's poll().

export const STAGES = ["plan", "level", "play", "recording", "compose", "review", "revise", "done"] as const;
// a make with `audio` (SPEC-SOUNDTRACK §5) ends with one more stage before done
const AUDIO_STAGES = [...STAGES.slice(0, -1), "audio", "done"] as const;
const STAGE_WORDS: Record<string, string> = { recording: "record" };
const STAGE_ON: Record<string, string> = { audio: "Adding the audio…" };

/** Map the engine's stage names onto the strip. */
export function stripIndex(stage: string, stages: readonly string[] = STAGES): number {
  const s = (stage || "").toLowerCase();
  const alias: Record<string, string> = { proof: "compose", preview: "level", moves: "play", record: "recording", evaluate: "review", revision: "revise" };
  return stages.indexOf(alias[s] || s);
}

export interface LogLine {
  t: number;
  stage: string;
  text: string;
}

export default function Progress({
  stage,
  done,
  lines,
  elapsed,
  error,
  trace,
  live,
  audio,
  title = "Progress",
}: {
  stage: string;
  done: boolean;
  lines: LogLine[];
  elapsed?: number;
  error?: string;
  trace?: string;
  live: boolean;
  /** the make adds audio at the end: show its stage */
  audio?: boolean;
  title?: string;
}) {
  const reduce = useReducedMotion();
  const box = useRef<HTMLDivElement>(null);
  const stages: readonly string[] = audio ? AUDIO_STAGES : STAGES;
  // the audio stage runs the music edit, whose own lines name earlier stages: once it has begun, the strip stays on it
  const idx = audio && lines.some((l) => l.stage === "audio") ? stages.indexOf("audio") : stripIndex(stage, stages);
  useEffect(() => {
    const el = box.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines.length]);
  const at = done ? stages.length - 1 : idx;
  return (
    <Card label="Progress" className={cx(live && "ring-2 ring-primary-fixed-dim")}>
      <CardTitle
        icon={Activity}
        right={elapsed != null ? <span className="font-mono text-code-sm text-outline">{elapsed.toFixed(1)} s</span> : null}
      >
        {title}
      </CardTitle>
      <ol className="mb-3 flex flex-wrap gap-1.5" aria-label="Stages">
        {stages.map((s, i) => {
          const state = done || i < at ? "done" : i === at ? "on" : "todo";
          return (
            <motion.li
              key={s}
              layout={!reduce}
              aria-current={state === "on" ? "step" : undefined}
              className={cx(
                "rounded-full px-2.5 py-1 text-label-sm",
                state === "done" && "bg-tertiary-fixed/35 text-tertiary",
                state === "on" && "bg-primary-container font-semibold text-on-primary",
                state === "todo" && "bg-surface-container text-on-surface-variant",
              )}
            >
              {(state === "on" && live && STAGE_ON[s]) || STAGE_WORDS[s] || s}
            </motion.li>
          );
        })}
      </ol>
      <div
        ref={box}
        role="log"
        aria-live="polite"
        aria-label="Live log"
        className="max-h-60 overflow-auto whitespace-pre-wrap rounded-xl bg-surface-container-low p-3 font-mono text-[12px] leading-5 text-on-surface-variant"
      >
        {lines.length
          ? lines.map((l, i) => (
              <div key={i}>
                {l.t.toFixed(1).padStart(6)} s [{l.stage}] {l.text}
              </div>
            ))
          : live
            ? "Starting…"
            : "Idle."}
      </div>
      {error ? <ErrorBox message={error} trace={trace} /> : null}
    </Card>
  );
}
