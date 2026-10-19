"use client";

import { Check, Film, Library, Loader2, Music, Plus, RotateCcw, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { catalogueMedia, fetchSampleAssets, sampleAssetFile, type SampleAsset, type SampleAssets as Index } from "@/lib/catalogue";
import { cx } from "./ui";

// "Sample assets" (SPEC-SAMPLE-ASSETS): the files the tool was built and tested with, from the catalogue's
// assets/index.json, offered where files are attached (Create's attachments card, the Edit workspace's attach zone).
// Attach downloads one from the bucket and hands it to the page's own upload, exactly as a dropped file. Nothing shows
// without the catalogue or when its index cannot be read.

type Row = { state: "down" | "up" | "done" | "error"; error?: string };

function size(n: number) {
  if (!n) return "";
  if (n < 1024 * 1024) return `${Math.max(1, Math.round(n / 1024))} KB`;
  return `${(n / 1024 / 1024).toFixed(n > 10 * 1024 * 1024 ? 0 : 1)} MB`;
}

const KIND = { image: "Image", video: "Video", audio: "Music" } as const;

function Thumb({ a }: { a: SampleAsset }) {
  return (
    <span
      className={cx(
        "flex size-12 shrink-0 items-center justify-center overflow-hidden rounded-lg",
        a.kind === "image" ? "bg-surface-container-highest" : "bg-inverse-surface text-secondary-container",
      )}
    >
      {a.kind === "video" ? (
        <Film aria-hidden className="size-5" />
      ) : a.kind === "audio" ? (
        <Music aria-hidden className="size-5" />
      ) : (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={catalogueMedia(a.path)} alt="" loading="lazy" className="h-full w-full object-cover" />
      )}
    </span>
  );
}

function Sheet({ index, onAttach, onClose }: { index: Index; onAttach: (files: File[]) => Promise<boolean>; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [rows, setRows] = useState<Record<string, Row>>({});
  const set = (path: string, r: Row) => setRows((m) => ({ ...m, [path]: r }));
  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal();
  }, []);
  // closed before it unmounts, so the page is no longer inert and focus can go back to the link
  const close = () => {
    ref.current?.close();
    onClose();
  };

  async function attach(a: SampleAsset) {
    set(a.path, { state: "down" });
    let file: File;
    try {
      file = await sampleAssetFile(a);
    } catch (e) {
      set(a.path, { state: "error", error: (e as Error).message });
      return;
    }
    set(a.path, { state: "up" });
    const ok = await onAttach([file]);
    set(a.path, ok ? { state: "done" } : { state: "error", error: `${a.file} was downloaded but not attached: the reason is shown on the page.` });
  }

  return (
    <dialog
      ref={ref}
      aria-labelledby="samples-title"
      onCancel={(e) => {
        e.preventDefault();
        close();
      }}
      onClick={(e) => {
        if (e.target === ref.current) close();
      }}
      className="m-0 ml-auto h-dvh max-h-dvh w-[min(100vw,480px)] max-w-none overflow-y-auto bg-surface-container-lowest p-0 text-on-surface shadow-xl backdrop:bg-inverse-surface/40"
    >
      <div className="flex flex-col gap-5 p-5 sm:p-6">
        <div className="flex items-start justify-between gap-3">
          <h2 id="samples-title" className="font-headline text-headline-lg text-on-surface">
            Sample assets
          </h2>
          <button type="button" autoFocus onClick={close} aria-label="Close" className="flex size-10 shrink-0 items-center justify-center rounded-lg text-outline hover:bg-surface-container hover:text-on-surface">
            <X aria-hidden className="size-5" />
          </button>
        </div>
        {index.note ? <p className="text-body-md text-on-surface-variant">{index.note}</p> : null}
        {index.groups.map((g, gi) => (
          <section key={`${gi}-${g.title}`} aria-labelledby={`samples-g${gi}`} className="flex flex-col gap-2">
            <h3 id={`samples-g${gi}`} className="text-title-sm text-on-surface">
              {g.title || "Files"}
            </h3>
            <ul className="flex flex-col gap-2">
              {g.items.map((a) => {
                const r = rows[a.path];
                const busy = r?.state === "down" || r?.state === "up";
                const word = r?.state === "down" ? "Downloading…" : r?.state === "up" ? "Attaching…" : r?.state === "done" ? "Attached" : r?.state === "error" ? "Try again" : "Attach";
                const Icon = busy ? Loader2 : r?.state === "done" ? Check : r?.state === "error" ? RotateCcw : Plus;
                return (
                  <li key={a.path} className="flex flex-col gap-1.5 rounded-xl bg-surface-container-low p-3">
                    <div className="flex items-center gap-3">
                      <Thumb a={a} />
                      <span className="flex min-w-0 flex-1 flex-col">
                        <span className="truncate text-body-md font-semibold text-on-surface" title={a.file}>
                          {a.file}
                        </span>
                        {a.about ? <span className="line-clamp-2 text-body-sm text-on-surface-variant">{a.about}</span> : null}
                        <span className="text-label-sm text-outline">{[size(a.bytes), KIND[a.kind]].filter(Boolean).join(" · ")}</span>
                      </span>
                      <button
                        type="button"
                        aria-label={`${word} ${a.file}`}
                        aria-busy={busy || undefined}
                        disabled={busy || r?.state === "done"}
                        onClick={() => void attach(a)}
                        className={cx(
                          "inline-flex min-h-9 shrink-0 items-center gap-1.5 rounded-full px-3.5 text-label-sm font-semibold transition-colors disabled:cursor-default",
                          r?.state === "done" ? "bg-tertiary-container/40 text-on-surface" : "bg-primary text-on-primary hover:bg-primary/90 disabled:opacity-80",
                        )}
                      >
                        <Icon aria-hidden className={cx("size-4", busy && "animate-spin motion-reduce:animate-none")} />
                        {word}
                      </button>
                    </div>
                    {r?.state === "error" ? (
                      <p role="alert" className="text-body-sm font-semibold text-error">
                        {r.error}
                      </p>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
      </div>
    </dialog>
  );
}

/** The "Sample assets" link, its hint and its sheet; renders nothing until the catalogue's assets index has loaded.
 *  `onAttach` is the page's own upload path; it resolves true when the file was attached. */
export default function SampleAssets({ onAttach, disabled, className }: { onAttach: (files: File[]) => Promise<boolean>; disabled?: boolean; className?: string }) {
  const [index, setIndex] = useState<Index | null>(null);
  const [open, setOpen] = useState(false);
  const link = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    let live = true;
    void fetchSampleAssets().then((x) => live && setIndex(x));
    return () => {
      live = false;
    };
  }, []);
  if (!index) return null;
  return (
    <div className={cx("flex flex-col items-start gap-0.5", className)}>
      <button
        ref={link}
        type="button"
        aria-haspopup="dialog"
        disabled={disabled}
        onClick={() => setOpen(true)}
        className="-mx-1.5 inline-flex min-h-9 items-center gap-1.5 rounded-lg px-1.5 text-label-md font-semibold text-primary hover:underline disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:no-underline"
      >
        <Library aria-hidden className="size-4" />
        Sample assets
      </button>
      <p className="text-body-sm text-on-surface-variant">The files the tool was built and tested with; attach one and describe what to do with it.</p>
      {open ? (
        <Sheet
          index={index}
          onAttach={onAttach}
          onClose={() => {
            setOpen(false);
            link.current?.focus();
          }}
        />
      ) : null}
    </div>
  );
}
