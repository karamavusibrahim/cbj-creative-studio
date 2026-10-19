"use client";

import { CircleCheck, CircleAlert, Eye, EyeOff, KeyRound, Loader2, X } from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { clean, clearKeys, engineUrl, getKeys, saveKeys, sentKeys, useOwnKeys } from "@/lib/keys";
import { checkEngine, siteOrigin, type CheckResult } from "@/lib/ownEngine";
import { useEngine } from "./EngineProvider";
import { field } from "./FeedbackDialog";
import { Button, cx } from "./ui";

// "Your engine and keys" (SPEC-OWN-ENGINE §1, SPEC-OWN-ENGINE-2). Two modes:
//  A. "My own engine": the URL (and optional token) of an engine the user runs on their own Mac, with their own Claude
//     CLI login and Gemini key. Checked from this browser before it can be saved; once saved, the whole site uses it.
//  B. "This studio's engine, with my Gemini key": the user's own Gemini key, sent only to the studio's engine
//     (lib/keys.ts). No Anthropic key anywhere: a user's own Claude account means their own engine (mode A).
// Kept in this tab (sessionStorage) or on this device (localStorage). A native modal <dialog>, like UnlockDialog and
// FeedbackDialog: focus stays inside, Escape closes. It can open over the Unlock dialog.

export const HONEST_KEYS =
  "Your key is used only for the reference-video reads of your own jobs, held in the engine's memory while the job runs, and never stored or logged by it. The passcode is still needed: the studio's computer still records the game.";

type Mode = "own" | "studio";

function SecretField({
  label,
  hint,
  value,
  onChange,
  invalid,
  describedBy,
  placeholder = "optional",
  name = label,
}: {
  label: string;
  name?: string; // what Show / Hide name ("the engine token")
  hint?: string;
  value: string;
  onChange: (v: string) => void;
  invalid?: boolean;
  describedBy?: string;
  placeholder?: string;
}) {
  const [shown, setShown] = useState(false);
  const id = useId();
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-label-md text-on-surface">
        {label} {hint ? <span className="font-normal text-on-surface-variant">· {hint}</span> : null}
      </label>
      <div className="relative">
        <input
          id={id}
          type={shown ? "text" : "password"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          autoComplete="off"
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          placeholder={placeholder}
          aria-invalid={invalid || undefined}
          aria-describedby={describedBy}
          data-1p-ignore
          data-lpignore="true"
          className={cx(field, "min-h-11 pr-12 font-mono", invalid && "ring-2 ring-error")}
        />
        <button
          type="button"
          onClick={() => setShown((s) => !s)}
          aria-label={shown ? `Hide the ${name}` : `Show the ${name}`}
          aria-pressed={shown}
          className="absolute inset-y-0 right-0.5 my-auto flex size-10 items-center justify-center rounded-lg text-outline hover:bg-surface-container hover:text-on-surface"
        >
          {shown ? <EyeOff aria-hidden className="size-[18px]" /> : <Eye aria-hidden className="size-[18px]" />}
        </button>
      </div>
    </div>
  );
}

const Code = ({ children }: { children: ReactNode }) => (
  <code className="rounded-md bg-surface-container px-1.5 py-0.5 font-mono text-code-sm text-on-surface [overflow-wrap:anywhere] box-decoration-clone">{children}</code>
);

/** A message with `backticked` commands set as code. */
function Words({ text }: { text: string }) {
  return (
    <>
      {text.split(/(`[^`]+`)/).map((part, i) => (part.startsWith("`") && part.endsWith("`") ? <Code key={i}>{part.slice(1, -1)}</Code> : part))}
    </>
  );
}

export default function KeysDialog({ onClose }: { onClose: () => void }) {
  const engine = useEngine();
  const ref = useRef<HTMLDialogElement>(null);
  const stored = useOwnKeys();
  const [initial] = useState(getKeys);
  const ik = initial.keys;
  // My own engine is the default; a user who saved keys for the studio's engine comes back to them
  const [mode, setMode] = useState<Mode>(ik.engine || !ik.gemini ? "own" : "studio");
  const [url, setUrl] = useState(ik.engine?.url || "");
  const [token, setToken] = useState(ik.engine?.token || "");
  const [checking, setChecking] = useState(false);
  const [checked, setChecked] = useState<{ url: string; token: string; result: CheckResult } | null>(null);
  const [gemini, setGemini] = useState(ik.gemini || "");
  const [remember, setRemember] = useState(initial.remember);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const checkId = useId();
  const origin = siteOrigin();

  const target = { url: engineUrl(url), token: token.trim() };
  const current = checked && checked.url === target.url && checked.token === target.token ? checked.result : null;
  const ready = Boolean(current?.ok);

  async function runCheck() {
    const t = { url: engineUrl(url), token: token.trim() };
    setNote("");
    setChecking(true);
    const result: CheckResult = t.url
      ? await checkEngine(t)
      : { ok: false, reason: "invalid", message: "Enter the engine's address, like http://127.0.0.1:8765." };
    setChecked({ ...t, result });
    if (t.url && t.url !== url.trim()) setUrl(t.url); // show the address as it will be used
    setChecking(false);
  }

  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal();
    // a saved engine is checked again on open, so the line says how it is now
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (ik.engine) void runCheck();
    // once, on open
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const has = sentKeys(stored.keys);
  const holds = Boolean(stored.keys.gemini || stored.keys.engine);
  // the studio's engine says whether it takes keys only while it is the one in use
  const studioCannot = !engine.own && engine.status !== "checking" && !engine.keysAvailable;

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (mode === "own") {
      if (!ready) return; // Save turns on after a good Check
      setSaving(true);
      saveKeys(clean({ gemini, engine: target }), remember);
      setSaving(false);
      onClose();
      return;
    }
    setSaving(true);
    const switching = Boolean(engine.own);
    saveKeys(clean({ gemini }), remember);
    if (!switching) await engine.refreshMeta(); // a switch back refreshes on its own (EngineProvider)
    setSaving(false);
    onClose();
  }

  async function clear() {
    const hadEngine = Boolean(engine.own);
    clearKeys();
    setGemini("");
    setUrl("");
    setToken("");
    setChecked(null);
    setNote(`Cleared: this browser holds no keys now.${hadEngine ? " Back to the studio's engine." : ""}`);
    if (!hadEngine) await engine.refreshMeta();
  }

  const modes: [Mode, string, string][] = [
    ["own", "My own engine (my Claude CLI, my Gemini key)", "Recommended"],
    ["studio", "This studio's engine, with my Gemini key", ""],
  ];

  return (
    <dialog
      ref={ref}
      aria-labelledby="keys-title"
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      className={cx(
        "m-0 mt-auto max-h-[92dvh] w-full max-w-none overflow-y-auto overflow-x-hidden rounded-t-2xl bg-surface-container-lowest p-0 text-on-surface shadow-xl backdrop:bg-inverse-surface/40",
        "sm:m-auto sm:max-h-[90dvh] sm:w-[min(92vw,580px)] sm:rounded-2xl",
      )}
    >
      <form onSubmit={save} noValidate className="flex flex-col gap-5 p-5 sm:p-6">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary-fixed text-primary">
              <KeyRound aria-hidden className="size-5" />
            </span>
            <h2 id="keys-title" className="font-headline text-headline-md text-on-surface">
              Your engine and keys
            </h2>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="flex size-10 shrink-0 items-center justify-center rounded-lg text-outline hover:bg-surface-container hover:text-on-surface">
            <X aria-hidden className="size-5" />
          </button>
        </div>

        <div role="radiogroup" aria-label="Which engine runs your work" className="grid grid-cols-1 gap-1 rounded-2xl bg-surface-container-low p-1 sm:grid-cols-2">
          {modes.map(([id, words, badge]) => (
            <label
              key={id}
              className={cx(
                "relative flex min-h-12 cursor-pointer items-center gap-2.5 rounded-xl px-3.5 py-2.5 text-label-md transition-colors has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-primary-container",
                mode === id ? "bg-surface-container-lowest font-semibold text-on-surface shadow-sm" : "text-on-surface-variant hover:bg-surface-container hover:text-on-surface",
              )}
            >
              <input
                type="radio"
                name="keys-mode"
                value={id}
                checked={mode === id}
                onChange={() => {
                  setMode(id);
                  setNote("");
                }}
                className="size-4 shrink-0 accent-primary-container"
              />
              <span className="flex min-w-0 flex-col">
                <span>{words}</span>
                {badge ? <span className="text-label-sm font-semibold uppercase tracking-wider text-tertiary">{badge}</span> : null}
              </span>
            </label>
          ))}
        </div>

        {mode === "own" ? (
          <div className="flex flex-col gap-4">
            <p className="-mt-1 text-body-md text-on-surface-variant">
              Run the studio on your own Mac, with your own Claude account (the Claude Code CLI, logged in) and your own Gemini key, and use this site with it.
              No API key, and no passcode: the calls go from this browser straight to your engine.
            </p>
            <div className="flex flex-col gap-1.5">
              <label htmlFor="own-engine-url" className="text-label-md text-on-surface">
                Engine URL
              </label>
              <input
                id="own-engine-url"
                type="url"
                inputMode="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !ready) {
                    e.preventDefault(); // Save waits for a good Check: Enter checks
                    if (!checking && url.trim()) void runCheck();
                  }
                }}
                placeholder="http://127.0.0.1:8765"
                autoComplete="off"
                autoCapitalize="none"
                autoCorrect="off"
                spellCheck={false}
                aria-describedby={checkId}
                aria-invalid={current && !current.ok && (current.reason === "invalid" || current.reason === "unreachable") ? true : undefined}
                className={cx(field, "min-h-11 font-mono")}
              />
            </div>
            <SecretField label="Engine token (optional)" name="engine token" value={token} onChange={setToken} placeholder="only if you set CBJ_API_TOKEN" describedBy={checkId} />
            <div className="flex flex-col gap-2">
              <div className="flex flex-wrap items-center gap-3">
                <Button variant="secondary" onClick={() => void runCheck()} disabled={checking || !url.trim()} aria-busy={checking}>
                  {checking ? <Loader2 aria-hidden className="size-4 animate-spin motion-reduce:animate-none" /> : null}
                  {checking ? "Checking…" : "Check"}
                </Button>
                {!ready && !checking ? <span className="text-body-sm text-on-surface-variant">Save turns on after a successful Check.</span> : null}
              </div>
              <div id={checkId}>
                {current && !checking ? (
                  current.ok ? (
                    <p role="status" className="flex items-start gap-2 rounded-xl bg-tertiary-fixed/35 px-3.5 py-2.5 text-body-md font-semibold text-on-tertiary-fixed">
                      <CircleCheck aria-hidden className="mt-0.5 size-[18px] shrink-0 text-tertiary" />
                      <span className="min-w-0 break-words">{current.line}</span>
                    </p>
                  ) : (
                    <p role="alert" className="flex items-start gap-2 rounded-xl bg-error-container/60 px-3.5 py-2.5 text-body-md text-on-error-container">
                      <CircleAlert aria-hidden className="mt-0.5 size-[18px] shrink-0" />
                      <span className="min-w-0 break-words">
                        <Words text={current.message} />
                      </span>
                    </p>
                  )
                ) : null}
              </div>
            </div>
            <ol className="flex list-decimal flex-col gap-2 rounded-xl bg-surface-container-low py-3 pl-8 pr-3.5 text-body-sm text-on-surface-variant marker:font-semibold marker:text-on-surface">
              <li>
                On your Mac: <Code>claude</Code> once to log in, then in <Code>cbj-creative/.env</Code>: <Code>CBJ_PLANNER=claude</Code> and{" "}
                <Code>GEMINI_API_KEY=...</Code>; <Code>uv run cbj setup-check --live</Code> proves it.
              </li>
              <li>
                Start it for this site: <Code>CBJ_CORS_ORIGINS={origin} uv run cbj ui</Code>
              </li>
              <li>Paste the URL here and press Check.</li>
            </ol>
          </div>
        ) : (
          <div className="flex flex-col gap-5">
            <p className="-mt-1 text-body-md text-on-surface-variant">
              The planner runs on the studio&apos;s Claude account. To use your own Claude account, choose{" "}
              <button type="button" onClick={() => setMode("own")} className="font-semibold text-primary underline-offset-2 hover:underline">
                My own engine
              </button>
              : it runs through your own Claude Code login, no API key.
            </p>
            <p id="keys-honest" className="-mt-3 text-body-sm text-on-surface-variant">
              {HONEST_KEYS}
            </p>
            {studioCannot ? (
              <p className="rounded-xl bg-surface-container-high px-3.5 py-2.5 text-body-sm text-on-surface">
                The studio&apos;s engine is offline or does not take your own key right now: a key saved here stays in this browser, unsent.
              </p>
            ) : null}

            <SecretField label="Gemini API key" name="Gemini API key" hint="reads reference videos on your own quota" value={gemini} onChange={setGemini} />
          </div>
        )}

        <div className="flex items-start justify-between gap-4 rounded-xl bg-surface-container-low px-3.5 py-3">
          <span className="flex flex-col">
            <span id="keys-remember" className="text-label-md text-on-surface">
              Remember on this device
            </span>
            <span className="text-body-sm text-on-surface-variant">{remember ? "Kept in this browser until you clear them." : "Off: this tab only, gone when it closes."}</span>
          </span>
          <button
            type="button"
            role="switch"
            aria-checked={remember}
            aria-labelledby="keys-remember"
            onClick={() => setRemember((r) => !r)}
            className={cx("relative mt-0.5 inline-flex h-7 w-12 shrink-0 items-center rounded-full transition-colors", remember ? "bg-primary-container" : "bg-outline-variant")}
          >
            <span aria-hidden className={cx("absolute left-1 size-5 rounded-full bg-surface-container-lowest shadow-sm transition-transform motion-reduce:transition-none", remember && "translate-x-5")} />
          </button>
        </div>

        <p role="status" className={cx("text-body-sm text-on-surface-variant", !note && "sr-only")}>
          {note || (engine.own ? "Running on your own engine" : has.gemini ? "Running on your own Gemini key" : "")}
        </p>

        <div className="flex flex-wrap items-center justify-end gap-2">
          <Button variant="quiet" onClick={() => void clear()} disabled={!holds && !gemini && !url.trim() && !token.trim()} className="mr-auto">
            Clear
          </Button>
          <Button variant="quiet" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            type="submit"
            disabled={saving || (mode === "own" && !ready)}
            aria-busy={saving}
            title={mode === "own" && !ready ? "Check the engine first" : undefined}
          >
            {saving ? <Loader2 aria-hidden className="size-4 animate-spin motion-reduce:animate-none" /> : null}
            {saving ? "Saving…" : "Save"}
          </Button>
        </div>
      </form>
    </dialog>
  );
}
