"use client";

import { Check, CircleAlert, Loader2, Plus, Sparkles, Undo2 } from "lucide-react";
import { useState } from "react";
import { EngineError, enginePost } from "@/lib/engine";
import type { Enhanced } from "@/lib/types";
import { READ_AS, appendSentence, removeInserted } from "@/lib/words";
import { useEngine } from "./EngineProvider";
import { Badge, ErrorBox, cx, type Tone } from "./ui";

// "Enhance prompt" (SPEC-ENHANCE §1): the engine rewrites the request in the words its planner reads
// reliably and adds nothing; whatever it would like to add comes back as questions the user may tap.
// Used by the Create page's prompt card and the Edit workspace's change card.

export interface EnhanceBody {
  prompt: string;
  uploads: string[];
  creative_id?: string;
  base?: number;
}

interface State<S> {
  loading: boolean;
  error: string;
  result: Enhanced | null;
  key: string; // what the result was asked for (the Edit workspace drops it when another version is shown)
  snapshot: S | null; // what Undo restores
  added: Record<string, string>; // option sentence → exactly what was appended to the text
}

/** Enhance state for one prompt box. `S` is what Undo restores (the text, and on Create the helper chips). */
export function useEnhance<S>() {
  const engine = useEngine();
  const [st, setSt] = useState<State<S>>({ loading: false, error: "", result: null, key: "", snapshot: null, added: {} });
  const available = engine.status === "online" && engine.meta?.features?.enhance !== false;

  /** Ask the engine; resolves the result (the caller applies `prompt` when `changed`), or null. */
  async function enhance(body: EnhanceBody, snapshot: S, key = ""): Promise<Enhanced | null> {
    if (!available || !body.prompt.trim() || st.loading) return null;
    if (!(await engine.ensureUnlocked())) return null;
    setSt((s) => ({ ...s, loading: true, error: "" }));
    try {
      const r = await enginePost<Enhanced>(engine.conn, "/api/enhance", body);
      setSt({ loading: false, error: "", result: r, key, snapshot, added: {} });
      return r;
    } catch (e) {
      const msg = e instanceof EngineError && e.status === 404 ? "This engine has no prompt enhancement yet (it needs a restart with the new version)." : (e as Error).message;
      setSt((s) => ({ ...s, loading: false, error: msg }));
      return null;
    }
  }

  function clear() {
    setSt({ loading: false, error: "", result: null, key: "", snapshot: null, added: {} });
  }

  /** Tap an option: append its sentence, or (second tap) remove exactly what was appended. */
  function toggle(text: string, sentence: string): string {
    const was = st.added[sentence];
    if (was !== undefined) {
      const { [sentence]: _drop, ...rest } = st.added;
      void _drop;
      setSt((s) => ({ ...s, added: rest }));
      return removeInserted(text, was, sentence);
    }
    const { text: next, inserted } = appendSentence(text, sentence);
    setSt((s) => ({ ...s, added: { ...s.added, [sentence]: inserted } }));
    return next;
  }

  return { ...st, available, enhance, clear, toggle };
}

export function EnhanceButton({
  loading,
  available,
  hasText,
  onClick,
}: {
  loading: boolean;
  available: boolean;
  hasText: boolean;
  onClick: () => void;
}) {
  const title = !available ? "Needs the engine" : !hasText ? "Write a request first" : "Rewrite the request in the words the planner reads; nothing is added";
  return (
    <span title={title} className="inline-flex">
      <button
        type="button"
        disabled={!available || !hasText || loading}
        aria-busy={loading}
        onClick={onClick}
        className="inline-flex min-h-9 items-center gap-1.5 rounded-xl bg-surface-container-high px-3 py-1.5 text-label-sm font-semibold text-on-surface transition-all hover:bg-surface-variant disabled:cursor-not-allowed disabled:opacity-45"
      >
        {loading ? <Loader2 aria-hidden className="size-4 animate-spin motion-reduce:animate-none" /> : <Sparkles aria-hidden className="size-4 text-primary-container" />}
        <span aria-live="polite">{loading ? "Reading your request…" : "Enhance prompt"}</span>
      </button>
    </span>
  );
}

const KIND_TONE: Record<string, Tone> = { clarified: "violet", translated: "sky", replaced: "amber", removed: "grey", reordered: "grey" };

/** The Enhanced card under the prompt box: what changed, the questions, how the request will be read. */
export function EnhancedCard({
  result,
  error,
  added,
  onToggle,
  onUndo,
}: {
  result: Enhanced | null;
  error: string;
  added: Record<string, string>;
  onToggle: (sentence: string) => void;
  onUndo?: () => void;
}) {
  if (!result) return error ? <ErrorBox message={error} /> : null;
  const r = result;
  return (
    <section aria-label="Enhanced request" className="rounded-2xl bg-surface-container-lowest p-5 shadow-sm ring-1 ring-primary-fixed-dim/60">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-title-sm text-on-surface">
          <Sparkles aria-hidden className="size-5 text-primary-container" />
          {r.changed ? "Enhanced" : "Checked"}
        </h3>
        {r.changed && onUndo ? (
          <button
            type="button"
            onClick={onUndo}
            className="inline-flex min-h-9 items-center gap-1.5 rounded-lg px-2 text-label-sm font-semibold text-primary hover:bg-primary-fixed/50 hover:underline"
          >
            <Undo2 aria-hidden className="size-4" /> Undo
          </button>
        ) : null}
      </div>
      <p className="mt-1 text-body-md text-on-surface-variant">
        {r.changed ? "Rewritten so the planner reads it as you meant; nothing was added." : "Your request is already clear."}
      </p>

      {r.changed && r.changes.length ? (
        <ul className="mt-4 flex flex-col divide-y divide-surface-container" aria-label="What was changed">
          {r.changes.map((c, i) => (
            <li key={i} className="flex flex-col gap-1 py-2.5 first:pt-0 last:pb-0">
              <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                <Badge tone={KIND_TONE[c.kind] || "grey"}>{c.kind}</Badge>
                {c.before ? <s className="break-words text-body-md text-on-surface-variant/80 decoration-outline">{c.before}</s> : null}
                {c.before && c.after ? <span aria-hidden className="text-outline">→</span> : null}
                {c.after ? <span className="break-words text-body-md text-on-surface">{c.after}</span> : null}
              </div>
              {c.why ? <p className="text-body-sm text-on-surface-variant">{c.why}</p> : null}
            </li>
          ))}
        </ul>
      ) : null}

      {r.questions.length ? (
        <div className="mt-4 rounded-xl bg-surface-container-low p-4">
          <p className="mb-2 text-label-sm font-semibold uppercase tracking-wider text-outline">You may want to add</p>
          <div className="flex flex-col gap-3">
            {r.questions.map((q, qi) => (
              <div key={qi} className="flex flex-col gap-1.5">
                <p className="text-label-md text-on-surface">{q.question}</p>
                <div className="flex flex-wrap gap-1.5">
                  {q.options.map((o) => {
                    const on = added[o] !== undefined;
                    return (
                      <button
                        key={o}
                        type="button"
                        aria-pressed={on}
                        title={on ? "Added to your request; tap again to take it out" : "Add this sentence to your request"}
                        onClick={() => onToggle(o)}
                        className={cx(
                          "inline-flex min-h-9 max-w-full items-center gap-1.5 rounded-full px-3 py-1.5 text-left text-label-sm transition-all",
                          on ? "bg-primary-container font-semibold text-on-primary shadow-sm" : "bg-surface-container-lowest text-on-surface-variant ring-1 ring-outline-variant/50 hover:text-on-surface",
                        )}
                      >
                        {on ? <Check aria-hidden className="size-3.5 shrink-0" /> : <Plus aria-hidden className="size-3.5 shrink-0" />}
                        <span className="min-w-0 break-words">{o}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {r.warnings.length ? (
        <ul className="mt-3 flex flex-col gap-1" aria-label="Notes">
          {r.warnings.map((w, i) => (
            <li key={i} className="flex items-start gap-1.5 text-body-sm text-amber">
              <CircleAlert aria-hidden className="mt-0.5 size-3.5 shrink-0" />
              {w}
            </li>
          ))}
        </ul>
      ) : null}

      <p className="mt-3 text-body-sm text-on-surface-variant">
        <span className="font-semibold text-on-surface">Will be read as:</span> {READ_AS[r.workflow] || r.workflow}
        {r.model ? <span className="text-outline"> · {r.model}, {r.seconds} s</span> : null}
      </p>
      {error ? <ErrorBox message={error} /> : null}
    </section>
  );
}
