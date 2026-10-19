"use client";

import { Play } from "lucide-react";
import { useRef } from "react";
import type { Version } from "@/lib/types";
import { useSource } from "./SourceProvider";
import { Button, cx } from "./ui";

// The phone frame (Stitch's device bezel, 9:16) and the before/after pair.

export function PhoneFrame({ children, className, label }: { children: React.ReactNode; className?: string; label?: string }) {
  return (
    <div
      aria-label={label}
      className={cx(
        "relative mx-auto aspect-[9/16] w-full max-w-[340px] rounded-[2.25rem] bg-inverse-surface p-2.5 shadow-xl ring-1 ring-outline-variant/30",
        "max-h-[70vh] [max-width:min(340px,calc(70vh*9/16))]",
        className,
      )}
    >
      <div className="relative h-full w-full overflow-hidden rounded-[1.75rem] bg-black">{children}</div>
    </div>
  );
}

export function VersionVideo({ v, className, muted }: { v: Version; className?: string; muted?: boolean }) {
  const source = useSource();
  return (
    <video
      key={`${v.id}/${v.n}/${source.live}`}
      src={source.media(v.video)}
      poster={source.media(v.poster)}
      controls
      playsInline
      muted={muted}
      preload="metadata"
      className={cx("h-full w-full object-contain", className)}
    >
      <track kind="captions" />
    </video>
  );
}

export function Pair({ before, after }: { before: Version; after: Version }) {
  const a = useRef<HTMLDivElement>(null);
  const b = useRef<HTMLDivElement>(null);
  function playBoth() {
    const va = a.current?.querySelector("video");
    const vb = b.current?.querySelector("video");
    if (!va || !vb) return;
    va.pause();
    vb.pause();
    va.currentTime = 0;
    vb.currentTime = 0;
    Promise.all([va.play(), vb.play()]).catch(() => {});
  }
  return (
    <div>
      <div className="grid grid-cols-2 gap-3">
        <figure ref={a} className="flex min-w-0 flex-col gap-1.5">
          <figcaption className="text-label-sm font-semibold text-on-surface-variant">v{before.n} (before)</figcaption>
          <div className="aspect-[9/16] max-h-[52vh] overflow-hidden rounded-xl bg-black">
            <VersionVideo v={before} muted />
          </div>
        </figure>
        <figure ref={b} className="flex min-w-0 flex-col gap-1.5">
          <figcaption className="text-label-sm font-semibold text-on-surface-variant">v{after.n} (after)</figcaption>
          <div className="aspect-[9/16] max-h-[52vh] overflow-hidden rounded-xl bg-black">
            <VersionVideo v={after} />
          </div>
        </figure>
      </div>
      <div className="mt-3 flex justify-center">
        <Button size="sm" variant="ghost" icon={Play} onClick={playBoth}>
          Play both
        </Button>
      </div>
    </div>
  );
}
