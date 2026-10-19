"use client";

import { KeyRound, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useEngine } from "./EngineProvider";
import { Button } from "./ui";

// The passcode dialog (SPEC §1.5): a native modal <dialog>, so focus stays inside it and Escape closes it.

export default function UnlockDialog({ onClose }: { onClose: (ok: boolean) => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  const { openKeys } = useEngine();

  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal();
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!code.trim()) return;
    setSending(true);
    setError("");
    try {
      const r = await fetch("/api/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ passcode: code.trim() }),
      });
      const j = (await r.json()) as { unlocked?: boolean; detail?: string };
      if (j.unlocked) onClose(true);
      else setError(j.detail || "That passcode is not right.");
    } catch {
      setError("The site could not be reached.");
    } finally {
      setSending(false);
    }
  }

  return (
    <dialog
      ref={ref}
      aria-labelledby="unlock-title"
      onCancel={(e) => {
        e.preventDefault();
        onClose(false);
      }}
      className="m-auto w-[min(92vw,420px)] rounded-2xl bg-surface-container-lowest p-0 text-on-surface shadow-xl backdrop:bg-inverse-surface/40"
    >
      <form onSubmit={submit} className="flex flex-col gap-4 p-6">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="flex size-9 items-center justify-center rounded-xl bg-primary-fixed text-primary">
              <KeyRound aria-hidden className="size-5" />
            </span>
            <h2 id="unlock-title" className="font-headline text-headline-md text-on-surface">
              Unlock the studio
            </h2>
          </div>
          <button type="button" onClick={() => onClose(false)} aria-label="Close" className="flex size-10 items-center justify-center rounded-lg text-outline hover:bg-surface-container hover:text-on-surface">
            <X aria-hidden className="size-5" />
          </button>
        </div>
        <p className="text-body-md text-on-surface-variant">
          Making, editing and reviewing run the studio engine on the owner&apos;s machine, which costs time and model credits.
          Enter the passcode once; browsing finished creatives never needs it.
        </p>
        <label className="flex flex-col gap-1.5 text-label-md">
          Passcode
          <input
            autoFocus
            type="password"
            autoComplete="current-password"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            className="min-h-11 rounded-xl bg-surface-container-low px-3.5 text-body-md outline-none ring-1 ring-outline-variant/50 focus:ring-2 focus:ring-primary-container"
          />
        </label>
        <button type="button" onClick={openKeys} className="-mt-1 self-start text-left text-label-md font-semibold text-primary hover:underline">
          Optional: use your own engine or your own Gemini key
        </button>
        {error ? (
          <p role="alert" className="text-body-sm font-semibold text-error">
            {error}
          </p>
        ) : null}
        <div className="flex justify-end gap-2">
          <Button variant="quiet" onClick={() => onClose(false)}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" disabled={sending || !code.trim()}>
            {sending ? "Checking…" : "Unlock"}
          </Button>
        </div>
      </form>
    </dialog>
  );
}
