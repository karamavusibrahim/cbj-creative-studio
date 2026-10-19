"use client";

import { useEngine } from "./EngineProvider";
import { cx } from "./ui";

// The engine status (replaces the mock's "All changes saved"): online, busy, offline; with an own engine
// (SPEC-OWN-ENGINE §2) "Your engine online / busy / offline", polled from that engine's /api/health.

export default function StatusPill() {
  const { status, busy, ours, own } = useEngine();
  const state = own
    ? status === "checking"
      ? { dot: "bg-outline-variant", word: "Checking your engine…", short: "Checking" }
      : status === "offline"
        ? { dot: "bg-error", word: "Your engine offline: check `uv run cbj ui`", short: "Offline" }
        : busy
          ? { dot: "bg-amber animate-pulse", word: ours ? "Your engine busy: making your creative" : "Your engine busy: making another creative", short: "Busy" }
          : { dot: "bg-tertiary-fixed-dim", word: "Your engine online", short: "Online" }
    : status === "checking"
      ? { dot: "bg-outline-variant", word: "Checking the engine…", short: "Checking" }
      : status === "offline"
        ? { dot: "bg-outline", word: "Engine offline: showcase only", short: "Offline" }
        : busy
          ? { dot: "bg-amber animate-pulse", word: ours ? "Engine busy: making your creative" : "Engine busy: making another creative", short: "Busy" }
          : { dot: "bg-tertiary-fixed-dim", word: "Engine online", short: "Online" };
  return (
    <div
      role="status"
      aria-live="polite"
      title={state.word.replaceAll("`", "")}
      className="flex min-h-8 items-center gap-2 rounded-full bg-surface-container-low/80 px-3 py-1"
    >
      <span aria-hidden className={cx("size-2 shrink-0 rounded-full", state.dot)} />
      <span className="hidden text-body-sm text-on-surface-variant lg:inline">
        {state.word.split(/`([^`]+)`/).map((part, i) => (i % 2 ? <code key={i} className="font-mono text-code-sm">{part}</code> : part))}
      </span>
      <span className="text-body-sm text-on-surface-variant lg:hidden">{state.short}</span>
    </div>
  );
}
