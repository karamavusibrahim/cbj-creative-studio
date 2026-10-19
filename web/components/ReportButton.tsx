"use client";

import { Download, Loader2 } from "lucide-react";
import { useState } from "react";
import { engineText, saveText } from "@/lib/engine";
import { useEngine } from "./EngineProvider";
import { cx } from "./ui";

// "Download report" (SPEC-FEEDBACK-INLINE §1, §4): the engine's report of one version (report.py: the request, how it
// was read, every step with its lines, the level and the play, the checks, the edit report, the review, the revision,
// the feedback, the files). A split: HTML by default, Markdown beside it. Read through the normal engine client, so it
// works through the relay too, and saved under the engine's own file name. Hidden offline and on an older engine.

const FORMATS = { html: "text/html", md: "text/markdown" } as const;

export default function ReportButton({ cid, n, className, block = false }: { cid: string; n: number; className?: string; block?: boolean }) {
  const engine = useEngine();
  const [busy, setBusy] = useState<keyof typeof FORMATS | null>(null);
  const [error, setError] = useState("");
  if (engine.status !== "online" || !engine.meta?.features?.report) return null;

  async function get(fmt: keyof typeof FORMATS) {
    setBusy(fmt);
    setError("");
    try {
      const text = await engineText(engine.conn, `/api/report/${encodeURIComponent(cid)}?version=${n}&format=${fmt}`);
      saveText(text, `${cid}-v${n}-report.${fmt}`, FORMATS[fmt]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const part =
    "inline-flex min-h-10 items-center justify-center gap-2 whitespace-nowrap px-3.5 py-2 text-label-md font-semibold transition-colors hover:bg-surface-container-low hover:text-on-surface disabled:cursor-not-allowed disabled:opacity-45";
  return (
    <div className={cx("flex flex-col gap-1", className)}>
      {/* block: the full width of a narrow card, the two parts stacked until the card has room for one row */}
      <div
        role="group"
        aria-label="Download report"
        className={cx(
          "overflow-hidden rounded-xl bg-surface-container-lowest text-on-surface-variant shadow-sm ring-1 ring-outline-variant/40",
          block ? "grid w-full grid-cols-1 @[19rem]:grid-cols-[1fr_auto]" : "inline-flex self-start",
        )}
      >
        <button type="button" disabled={busy !== null} aria-busy={busy === "html"} title="The report of this version as a web page" onClick={() => void get("html")} className={part}>
          {busy === "html" ? <Loader2 aria-hidden className="size-[18px] animate-spin motion-reduce:animate-none" /> : <Download aria-hidden className="size-[18px]" />}
          Download report
          <span className="rounded-md bg-surface-container px-1.5 py-0.5 text-[10.5px] font-semibold uppercase tracking-wider text-outline">HTML</span>
        </button>
        <button
          type="button"
          disabled={busy !== null}
          aria-busy={busy === "md"}
          aria-label="Download report as Markdown"
          title="The same report as Markdown"
          onClick={() => void get("md")}
          className={cx(part, block ? "border-t border-outline-variant/40 @[19rem]:border-l @[19rem]:border-t-0" : "border-l border-outline-variant/40")}
        >
          {busy === "md" ? <Loader2 aria-hidden className="size-4 animate-spin motion-reduce:animate-none" /> : null}
          Markdown
        </button>
      </div>
      {error ? (
        <p role="alert" className="text-body-sm font-semibold text-error">
          {error}
        </p>
      ) : null}
    </div>
  );
}
