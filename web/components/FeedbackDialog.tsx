"use client";

import { Check, Loader2, MessageSquare, Star, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { enginePost } from "@/lib/engine";
import { truncate } from "@/lib/text";
import type { FeedbackArea, FeedbackBody, FeedbackKind, FeedbackPage, FeedbackRecord } from "@/lib/types";
import { AREA_WORDS, FEEDBACK_KINDS, LESSON_WORKFLOW_WORDS } from "@/lib/words";
import { useEngine } from "./EngineProvider";
import { Button, cx } from "./ui";

// Designer feedback (SPEC-FEEDBACK §2): one dialog, opened from the Create result, the Edit workspace, a
// showcase creative and the header. The record goes to the engine, which captures the scene (the version's
// prompt, workflow, summary) itself; nothing changes automatically: a person reads it.

export interface FeedbackContext {
  page: FeedbackPage;
  creative_id?: string;
  version?: number;
  title?: string; // the creative's title (its first prompt, or the showcase title)
  workflow?: string; // the version's workflow (create, guided, image_guided, edit)
}

const NAME_KEY = "cbj.designer";

/** The designer's name, remembered in this browser (the dialog and the inline panel share it). */
export function savedName(): string {
  try {
    return localStorage.getItem(NAME_KEY) || "";
  } catch {
    return "";
  }
}

export function saveName(name: string): void {
  try {
    localStorage.setItem(NAME_KEY, name);
  } catch {
    /* private mode */
  }
}

/** "on": the engine takes feedback; "off": offline (or not known yet): the buttons are disabled; "hidden": an older engine. */
export function useFeedbackState(): "on" | "off" | "hidden" {
  const { status, meta } = useEngine();
  if (status === "online" && meta && !meta.features?.feedback) return "hidden";
  return status === "online" && meta?.features?.feedback ? "on" : "off";
}

/** The "Give feedback" button (or the header's icon button): unlocks first, then opens the dialog. */
export function FeedbackButton({
  context,
  variant = "button",
  className,
  unavailable,
}: {
  context: FeedbackContext;
  variant?: "button" | "icon";
  className?: string;
  unavailable?: boolean; // e.g. a showcase copy the engine does not hold
}) {
  const engine = useEngine();
  const state = useFeedbackState();
  const [open, setOpen] = useState(false);
  if (state === "hidden") return null;
  const disabled = state !== "on" || Boolean(unavailable);

  async function openIt() {
    if (disabled) return;
    if (await engine.ensureUnlocked()) setOpen(true);
  }

  return (
    <>
      <span title={disabled ? "Needs the engine" : variant === "icon" ? "Feedback about the studio" : "Tell the studio owner what worked or what did not"} className={cx("inline-flex", className)}>
        {variant === "icon" ? (
          <button
            type="button"
            aria-label="Feedback about the studio"
            disabled={disabled}
            onClick={() => void openIt()}
            className="flex size-10 items-center justify-center rounded-lg text-on-surface-variant transition-colors hover:bg-surface-container-high hover:text-on-surface disabled:cursor-not-allowed disabled:opacity-45 disabled:hover:bg-transparent"
          >
            <MessageSquare aria-hidden className="size-[18px]" />
          </button>
        ) : (
          <Button variant="ghost" icon={MessageSquare} disabled={disabled} onClick={() => void openIt()}>
            Give feedback
          </Button>
        )}
      </span>
      {open ? <FeedbackDialog context={context} onClose={() => setOpen(false)} /> : null}
    </>
  );
}

export const chip = (on: boolean) =>
  cx(
    "inline-flex min-h-10 items-center gap-1.5 rounded-full px-3.5 py-1.5 text-left text-label-md transition-all",
    on ? "bg-primary-container font-semibold text-on-primary shadow-sm" : "bg-surface-container-low text-on-surface-variant ring-1 ring-outline-variant/40 hover:bg-surface-container hover:text-on-surface",
  );

export const field =
  "w-full rounded-xl bg-surface-container-low px-3.5 py-2.5 text-body-md text-on-surface outline-none ring-1 ring-outline-variant/50 placeholder:text-outline focus:ring-2 focus:ring-primary-container";

export default function FeedbackDialog({ context, onClose }: { context: FeedbackContext; onClose: () => void }) {
  const engine = useEngine();
  const ref = useRef<HTMLDialogElement>(null);
  const general = context.page === "general";
  const [designer, setDesigner] = useState(savedName);
  const [kind, setKind] = useState<FeedbackKind>(general ? "idea" : "wrong");
  const [area, setArea] = useState<FeedbackArea>(general ? "website" : "other");
  const [wrong, setWrong] = useState("");
  const [expected, setExpected] = useState("");
  const [rating, setRating] = useState<number | undefined>();
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState<FeedbackRecord | null>(null);

  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal();
  }, []);

  const good = kind === "good";
  const showRating = !general && (kind === "wrong" || kind === "missing");
  const valid = good || wrong.trim().length >= 3;

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!valid || sending) return;
    if (!(await engine.ensureUnlocked())) return;
    setSending(true);
    setError("");
    const name = designer.trim();
    saveName(name);
    const body: FeedbackBody = {
      page: context.page,
      area,
      kind,
      wrong: wrong.trim(),
      ...(!good && expected.trim() ? { expected: expected.trim() } : {}),
      ...(showRating && rating ? { rating } : {}),
      ...(name ? { designer: name } : {}),
      ...(context.creative_id ? { creative_id: context.creative_id, version: context.version } : {}),
    };
    try {
      setSaved(await enginePost<FeedbackRecord>(engine.conn, "/api/feedback", body));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSending(false);
    }
  }

  function another() {
    setSaved(null);
    setWrong("");
    setExpected("");
    setRating(undefined);
    setError("");
  }

  const about = context.creative_id
    ? [truncate(context.title || context.creative_id, 80), context.version ? `v${context.version}` : "", LESSON_WORKFLOW_WORDS[context.workflow || ""] || context.workflow || ""]
        .filter(Boolean)
        .join(" · ")
    : "the studio";

  return (
    <dialog
      ref={ref}
      aria-labelledby="feedback-title"
      aria-describedby="feedback-honest"
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      className={cx(
        "m-0 mt-auto max-h-[92dvh] w-full max-w-none overflow-y-auto rounded-t-2xl bg-surface-container-lowest p-0 text-on-surface shadow-xl backdrop:bg-inverse-surface/40",
        "sm:m-auto sm:max-h-[90dvh] sm:w-[min(92vw,600px)] sm:rounded-2xl",
      )}
    >
      <div className="flex flex-col gap-5 p-5 sm:p-6">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary-fixed text-primary">
              <MessageSquare aria-hidden className="size-5" />
            </span>
            <h2 id="feedback-title" className="font-headline text-headline-md text-on-surface">
              Tell the studio owner
            </h2>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="flex size-10 shrink-0 items-center justify-center rounded-lg text-outline hover:bg-surface-container hover:text-on-surface">
            <X aria-hidden className="size-5" />
          </button>
        </div>
        <p id="feedback-honest" className="-mt-2 text-body-md text-on-surface-variant">
          What you write here is read by the person who tunes the engine. Nothing changes automatically.
        </p>
        <p className="rounded-xl bg-surface-container-low px-3.5 py-2.5 text-body-sm text-on-surface-variant">
          <b className="text-on-surface">About:</b> {about}
        </p>

        {saved ? (
          <div className="flex flex-col gap-4" role="status">
            <p className="flex items-start gap-2 text-body-lg text-on-surface">
              <Check aria-hidden className="mt-0.5 size-5 shrink-0 text-tertiary" />
              <span>
                Thanks — saved as <span className="font-mono text-code-sm">{saved.id}</span>.
              </span>
            </p>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <button type="button" onClick={another} className="min-h-10 text-label-md font-semibold text-primary hover:underline">
                Send another
              </button>
              <Button autoFocus variant="primary" onClick={onClose}>
                Close
              </Button>
            </div>
          </div>
        ) : (
          <form onSubmit={send} className="flex flex-col gap-5" noValidate>
            <label className="flex flex-col gap-1.5 text-label-md text-on-surface">
              Your name
              <input
                value={designer}
                maxLength={40}
                autoComplete="nickname"
                placeholder="optional"
                onChange={(e) => setDesigner(e.target.value)}
                className={cx(field, "min-h-11")}
              />
            </label>

            <fieldset className="flex flex-col gap-2">
              <legend className="mb-2 text-label-md text-on-surface">What kind of note?</legend>
              <div className="flex flex-wrap gap-2">
                {FEEDBACK_KINDS.map((k) => (
                  <button key={k.id} type="button" aria-pressed={kind === k.id} onClick={() => setKind(k.id)} className={chip(kind === k.id)}>
                    {k.text}
                  </button>
                ))}
              </div>
            </fieldset>

            <fieldset className="flex flex-col gap-2">
              <legend className="mb-2 text-label-md text-on-surface">What is it about?</legend>
              <div className="flex flex-wrap gap-2">
                {Object.entries(AREA_WORDS).map(([id, words]) => (
                  <button key={id} type="button" aria-pressed={area === id} onClick={() => setArea(id as FeedbackArea)} className={chip(area === id)}>
                    {words}
                  </button>
                ))}
              </div>
            </fieldset>

            <label className="flex flex-col gap-1.5 text-label-md text-on-surface">
              <span>
                {good ? "What did you like?" : "What happened?"}
                {good ? <span className="font-normal text-outline"> (optional)</span> : null}
              </span>
              <textarea
                rows={3}
                value={wrong}
                required={!good}
                aria-required={!good}
                maxLength={1000}
                onChange={(e) => setWrong(e.target.value)}
                className={cx(field, "resize-y")}
              />
            </label>

            {!good ? (
              <label className="flex flex-col gap-1.5 text-label-md text-on-surface">
                <span>
                  What did you expect instead? <span className="font-normal text-outline">(optional)</span>
                </span>
                <textarea rows={2} value={expected} maxLength={1000} onChange={(e) => setExpected(e.target.value)} className={cx(field, "resize-y")} />
              </label>
            ) : null}

            {showRating ? <RatingStars value={rating} onChange={setRating} /> : null}

            {error ? (
              <p role="alert" className="whitespace-pre-wrap rounded-xl bg-error-container/60 p-3 text-body-md font-semibold text-on-error-container">
                {error}
              </p>
            ) : null}

            <div className="flex flex-wrap items-center justify-end gap-2">
              {!valid ? <span className="mr-auto text-body-sm text-on-surface-variant">Say what happened in a few words.</span> : null}
              <Button variant="quiet" onClick={onClose}>
                Cancel
              </Button>
              <Button variant="primary" type="submit" disabled={!valid || sending} aria-busy={sending}>
                {sending ? <Loader2 aria-hidden className="size-4 animate-spin motion-reduce:animate-none" /> : null}
                <span aria-live="polite">{sending ? "Sending…" : "Send"}</span>
              </Button>
            </div>
          </form>
        )}
      </div>
    </dialog>
  );
}

/** "How close to what you asked?": five star buttons, a second press on the chosen one clears it. */
export function RatingStars({ value, onChange }: { value: number | undefined; onChange: (n: number | undefined) => void }) {
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-2 text-label-md text-on-surface">
        How close to what you asked? <span className="font-normal text-outline">(optional)</span>
      </legend>
      <div className="flex flex-wrap items-center gap-1">
        {[1, 2, 3, 4, 5].map((i) => {
          const lit = value !== undefined && i <= value;
          return (
            <button
              key={i}
              type="button"
              aria-pressed={value === i}
              aria-label={`${i} of 5`}
              onClick={() => onChange(value === i ? undefined : i)}
              className="flex size-10 items-center justify-center rounded-lg transition-colors hover:bg-surface-container"
            >
              <Star aria-hidden className={cx("size-6", lit ? "fill-amber text-amber" : "text-outline-variant")} />
            </button>
          );
        })}
        <span className="ml-2 text-body-sm text-on-surface-variant">{value ? `${value}/5` : "not rated"}</span>
      </div>
    </fieldset>
  );
}
