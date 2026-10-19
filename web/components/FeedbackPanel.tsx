"use client";

import { Check, CloudOff, Flag, Lightbulb, Loader2, MessageSquare, PackageOpen, ThumbsDown, ThumbsUp } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { enginePost } from "@/lib/engine";
import type { FeedbackArea, FeedbackBody, FeedbackKind, FeedbackRecord, FeedbackStep } from "@/lib/types";
import { AREA_WORDS, STEP_AREA, STEP_ORDER, STEP_WORDS } from "@/lib/words";
import { useEngine } from "./EngineProvider";
import { RatingStars, chip, field, saveName, savedName, useFeedbackState, type FeedbackContext } from "./FeedbackDialog";
import { Button, Card, cx } from "./ui";

// The inline feedback panel (SPEC-FEEDBACK-INLINE §2-§3): "Was this what you asked?" under a finished or edited
// creative, tied to the step of the process (and the exact row) the note is about. The rows of the page (the
// controls, the edit report, the failed checks, the viewer's "not as asked" lines) open it through a small context,
// FeedbackPanelProvider, so nothing is threaded through props. The engine captures the process itself; nothing
// changes automatically: a person reads the note.

interface Choice {
  key: string; // the creative and version the choice belongs to: another version shown starts afresh
  kind: FeedbackKind | null;
  step: FeedbackStep;
  item: string;
  area: FeedbackArea;
  areaPicked: boolean; // the designer chose the area: a new step no longer moves it
  seq: number; // bumped by a row's flag: the panel scrolls into view and takes the focus
  saved: FeedbackRecord | null;
}

interface PanelCtx {
  context: FeedbackContext;
  available: boolean; // the engine takes feedback about this creative
  steps: boolean; // the engine knows the steps (an older one: no step chips, no step or item sent)
  edit: boolean; // the version is an edit: the edit report is a step
  shown: boolean; // a panel is on the page (the flags only show then)
  register: () => () => void;
  choice: Choice;
  update: (patch: Partial<Choice>) => void;
  open: (o: { step: FeedbackStep; item?: string; kind?: FeedbackKind }) => Promise<void>;
}

const Ctx = createContext<PanelCtx | null>(null);

const fresh = (key: string): Choice => ({ key, kind: null, step: "result", item: "", area: STEP_AREA.result, areaPicked: false, seq: 0, saved: null });

export function FeedbackPanelProvider({
  context,
  edit = false,
  unavailable = false,
  children,
}: {
  context: FeedbackContext;
  edit?: boolean;
  unavailable?: boolean; // e.g. a showcase creative the engine does not hold
  children: ReactNode;
}) {
  const engine = useEngine();
  const state = useFeedbackState();
  const key = `${context.creative_id ?? ""}:${context.version ?? ""}`;
  const [raw, setRaw] = useState<Choice>(() => fresh(key));
  const [panels, setPanels] = useState(0);
  const choice = raw.key === key ? raw : fresh(key);
  const available = state === "on" && !unavailable && Boolean(context.creative_id);
  const steps = Boolean(engine.meta?.features?.feedback_steps);

  const register = useCallback(() => {
    setPanels((n) => n + 1);
    return () => setPanels((n) => n - 1);
  }, []);
  const update = useCallback((patch: Partial<Choice>) => setRaw((c) => ({ ...(c.key === key ? c : fresh(key)), ...patch })), [key]);
  const { ensureUnlocked } = engine;
  const open = useCallback(
    async ({ step, item, kind = "wrong" }: { step: FeedbackStep; item?: string; kind?: FeedbackKind }) => {
      if (!(await ensureUnlocked())) return;
      setRaw((c) => {
        const cur = c.key === key ? c : fresh(key);
        return { ...cur, kind, step, item: item ?? "", area: cur.areaPicked ? cur.area : STEP_AREA[step], saved: null, seq: cur.seq + 1 };
      });
    },
    [ensureUnlocked, key],
  );

  return (
    <Ctx.Provider value={{ context, available, steps, edit, shown: panels > 0, register, choice, update, open }}>{children}</Ctx.Provider>
  );
}

/** "About this row": a small flag on a row of the page. Hidden where no panel is on the page, or it cannot send. */
export function FlagButton({ title, step, className }: { title: string; step: FeedbackStep; className?: string }) {
  const ctx = useContext(Ctx);
  if (!ctx || !ctx.available || !ctx.steps || !ctx.shown) return null;
  return (
    <button
      type="button"
      aria-label={`Feedback about ${title}`}
      title={`Something off here? Tell the studio owner about “${title}”`}
      onClick={() => void ctx.open({ step, item: title, kind: "wrong" })}
      className={cx(
        "inline-flex size-8 shrink-0 items-center justify-center rounded-lg text-outline transition-colors hover:bg-surface-container hover:text-primary",
        className,
      )}
    >
      <Flag aria-hidden className="size-4" />
    </button>
  );
}

const KINDS: { id: FeedbackKind; text: string }[] = [
  { id: "good", text: "Yes, as asked" },
  { id: "wrong", text: "Something is off" },
  { id: "missing", text: "Something is missing" },
  { id: "idea", text: "I have an idea" },
];

/** The panel itself. Inside a FeedbackPanelProvider. */
export default function FeedbackPanel({ className }: { className?: string }) {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("FeedbackPanel needs a FeedbackPanelProvider");
  const { register } = ctx;
  useEffect(() => register(), [register]);
  return (
    <Card id="feedback-panel" label="Was this what you asked?" className={cx("scroll-mt-24 border border-surface-variant", className)}>
      <h2 className="flex items-center gap-2 text-title-sm text-on-surface">
        <MessageSquare aria-hidden className="size-5 text-primary-container" />
        Was this what you asked?
      </h2>
      {ctx.available ? (
        // a version shown afresh starts with empty fields
        <PanelBody key={ctx.choice.key} ctx={ctx} />
      ) : (
        <p className="mt-3 flex items-center gap-2 text-body-md text-on-surface-variant">
          <CloudOff aria-hidden className="size-4 shrink-0 text-outline" /> Needs the engine
        </p>
      )}
    </Card>
  );
}

function PanelBody({ ctx }: { ctx: PanelCtx }) {
  const engine = useEngine();
  const { choice, update, context, steps } = ctx;
  const [designer, setDesigner] = useState(savedName);
  const [wrong, setWrong] = useState("");
  const [expected, setExpected] = useState("");
  const [rating, setRating] = useState<number | undefined>();
  const [areas, setAreas] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const box = useRef<HTMLDivElement>(null);
  const text = useRef<HTMLTextAreaElement>(null);

  // a row's flag opened the panel: bring it into view and put the cursor in "What happened?"
  useEffect(() => {
    if (!choice.seq) return;
    const el = box.current?.closest("section");
    el?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
    const t = setTimeout(() => text.current?.focus({ preventScroll: true }), 350);
    return () => clearTimeout(t);
  }, [choice.seq]);

  const kind = choice.kind;
  const good = kind === "good";
  const showRating = kind === "wrong" || kind === "missing";
  const valid = good || wrong.trim().length >= 3;
  const stepList = STEP_ORDER.filter((s) => s !== "proof" || ctx.edit);

  async function pick(k: FeedbackKind) {
    if (k === kind) return;
    if (!kind && !(await engine.ensureUnlocked())) return;
    update({ kind: k, saved: null });
  }

  function setStep(s: FeedbackStep) {
    update({ step: s, ...(choice.areaPicked ? {} : { area: STEP_AREA[s] }) });
  }

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!kind || !valid || sending) return;
    if (!(await engine.ensureUnlocked())) return;
    setSending(true);
    setError("");
    const name = designer.trim();
    saveName(name);
    const item = choice.item.trim().slice(0, 200);
    const body: FeedbackBody = {
      page: context.page,
      area: choice.area,
      kind,
      wrong: wrong.trim(),
      ...(!good && expected.trim() ? { expected: expected.trim() } : {}),
      ...(showRating && rating ? { rating } : {}),
      ...(name ? { designer: name } : {}),
      ...(context.creative_id ? { creative_id: context.creative_id, version: context.version } : {}),
      ...(steps ? { step: choice.step, ...(item ? { item } : {}) } : {}),
    };
    try {
      update({ saved: await enginePost<FeedbackRecord>(engine.conn, "/api/feedback", body) });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSending(false);
    }
  }

  function another() {
    update({ saved: null, kind: null, item: "", step: "result", area: STEP_AREA.result, areaPicked: false });
    setWrong("");
    setExpected("");
    setRating(undefined);
    setAreas(false);
    setError("");
  }

  if (choice.saved) {
    const s = choice.saved;
    const step = (s.step || (steps ? choice.step : "")) as FeedbackStep | "";
    const item = s.item ?? (steps ? choice.item.trim() : "");
    return (
      <div ref={box} role="status" className="mt-3 flex flex-col gap-3">
        <p className="flex items-start gap-2 text-body-md text-on-surface">
          <Check aria-hidden className="mt-0.5 size-5 shrink-0 text-tertiary" />
          <span>
            Thanks, saved as <span className="font-mono text-code-sm">{s.id}</span>
            {step ? (
              <>
                {" "}
                · it is tied to {STEP_WORDS[step] || step}
                {item ? (
                  <>
                    , <span className="font-mono text-code-sm">{item}</span>
                  </>
                ) : null}
              </>
            ) : null}
          </span>
        </p>
        <button type="button" onClick={another} className="min-h-10 self-start text-label-md font-semibold text-primary hover:underline">
          Send another
        </button>
      </div>
    );
  }

  return (
    <div ref={box} className="mt-1 flex flex-col gap-4">
      <p className="text-body-sm text-on-surface-variant">Read by the person who tunes the engine. Nothing changes automatically.</p>
      <div className="grid grid-cols-2 gap-2">
        {KINDS.slice(0, 2).map((k) => {
          const on = kind === k.id;
          const Icon = k.id === "good" ? ThumbsUp : ThumbsDown;
          return (
            <button
              key={k.id}
              type="button"
              aria-pressed={on}
              onClick={() => void pick(k.id)}
              className={cx(
                "flex min-h-12 items-center justify-center gap-2 rounded-xl px-3 py-2.5 text-label-md font-semibold transition-all",
                on
                  ? k.id === "good"
                    ? "bg-tertiary-fixed text-on-tertiary-fixed shadow-sm ring-1 ring-tertiary/30"
                    : "bg-primary-container text-on-primary shadow-sm"
                  : "bg-surface-container-low text-on-surface ring-1 ring-outline-variant/40 hover:bg-surface-container",
              )}
            >
              <Icon aria-hidden className="size-[18px] shrink-0" />
              {k.text}
            </button>
          );
        })}
      </div>
      <div className="-mt-1 flex flex-wrap items-center gap-x-4 gap-y-1">
        {KINDS.slice(2).map((k) => {
          const on = kind === k.id;
          const Icon = k.id === "missing" ? PackageOpen : Lightbulb;
          return (
            <button
              key={k.id}
              type="button"
              aria-pressed={on}
              onClick={() => void pick(k.id)}
              className={cx(
                "inline-flex min-h-9 items-center gap-1.5 rounded-lg px-1 text-label-md transition-colors",
                on ? "font-semibold text-primary underline underline-offset-4" : "text-on-surface-variant hover:text-on-surface",
              )}
            >
              <Icon aria-hidden className="size-4" />
              {k.text}
            </button>
          );
        })}
      </div>

      {kind ? (
        <form onSubmit={send} noValidate className="flex flex-col gap-4 border-t border-surface-variant pt-4">
          {steps ? (
            <fieldset className="flex flex-col gap-2">
              <legend className="mb-2 text-label-md text-on-surface">Which step is it about?</legend>
              <div className="flex flex-wrap gap-1.5">
                {stepList.map((s) => (
                  <button key={s} type="button" aria-pressed={choice.step === s} onClick={() => setStep(s)} className={cx(chip(choice.step === s), "!min-h-9 !px-3 !py-1")}>
                    {STEP_WORDS[s]}
                  </button>
                ))}
              </div>
            </fieldset>
          ) : null}
          {steps ? (
            <label className="flex flex-col gap-1.5 text-label-md text-on-surface">
              <span>
                Which thing? <span className="font-normal text-outline">(optional)</span>
              </span>
              <input
                value={choice.item}
                maxLength={200}
                aria-describedby="feedback-item-hint"
                onChange={(e) => update({ item: e.target.value })}
                className={cx(field, "min-h-11 font-mono !text-code-sm")}
              />
              <span id="feedback-item-hint" className="text-body-sm font-normal text-on-surface-variant">
                the exact thing (a caption, a row, a check)
              </span>
            </label>
          ) : null}
          <div className="flex flex-col gap-2">
            <p className="text-body-sm text-on-surface-variant">
              about: <b className="font-semibold text-on-surface">{AREA_WORDS[choice.area]}</b> ·{" "}
              <button type="button" aria-expanded={areas} onClick={() => setAreas(!areas)} className="min-h-8 font-semibold text-primary hover:underline">
                change
              </button>
            </p>
            {areas ? (
              <div role="group" aria-label="What is it about?" className="flex flex-wrap gap-1.5">
                {(Object.keys(AREA_WORDS) as FeedbackArea[]).map((a) => (
                  <button
                    key={a}
                    type="button"
                    aria-pressed={choice.area === a}
                    onClick={() => update({ area: a, areaPicked: true })}
                    className={cx(chip(choice.area === a), "!min-h-9 !px-3 !py-1")}
                  >
                    {AREA_WORDS[a]}
                  </button>
                ))}
              </div>
            ) : null}
          </div>
          <label className="flex flex-col gap-1.5 text-label-md text-on-surface">
            <span>
              {good ? "What did you like?" : "What happened?"}
              {good ? <span className="font-normal text-outline"> (optional)</span> : null}
            </span>
            <textarea
              ref={text}
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
          {showRating ? <RatingStars value={rating} onChange={setRating} /> : null}
          {error ? (
            <p role="alert" className="whitespace-pre-wrap rounded-xl bg-error-container/60 p-3 text-body-md font-semibold text-on-error-container">
              {error}
            </p>
          ) : null}
          <div className="flex flex-wrap items-center justify-end gap-2">
            {!valid ? <span className="mr-auto text-body-sm text-on-surface-variant">Say what happened in a few words.</span> : null}
            <Button variant="primary" type="submit" disabled={!valid || sending} aria-busy={sending}>
              {sending ? <Loader2 aria-hidden className="size-4 animate-spin motion-reduce:animate-none" /> : null}
              <span aria-live="polite">{sending ? "Sending…" : "Send"}</span>
            </Button>
          </div>
        </form>
      ) : null}
    </div>
  );
}
