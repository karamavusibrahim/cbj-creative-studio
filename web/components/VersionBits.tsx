"use client";

import { Clock, Download, Flag, Gauge, Smartphone } from "lucide-react";
import type { Version } from "@/lib/types";
import { difficultyWord } from "@/lib/text";
import { ENDINGS } from "@/lib/words";
import { useSource } from "./SourceProvider";
import { Fact, Fold, cx } from "./ui";

// Small pieces of a finished version: the facts chips, the download, the file links.

export function VersionFacts({ v }: { v: Version }) {
  const b = v.brief;
  const diff = difficultyWord(b?.level?.difficulty);
  return (
    <div className="flex flex-wrap gap-2">
      <Fact icon={Clock} tone="secondary">
        {v.length_s} s
      </Fact>
      <Fact icon={Smartphone}>{b?.format || "9:16"}</Fact>
      {diff ? (
        <Fact icon={Gauge} tone="error">
          {diff}
        </Fact>
      ) : null}
      {b?.gameplay?.ending ? (
        <Fact icon={Flag} tone="tertiary">
          {ENDINGS[b.gameplay.ending] || b.gameplay.ending.replace("_", " ")}
        </Fact>
      ) : null}
    </div>
  );
}

export function DownloadLink({ v, label = "Download MP4", className, primary }: { v: Version; label?: string; className?: string; primary?: boolean }) {
  const source = useSource();
  return (
    <a
      href={source.media(v.video)}
      download={`${v.id}-v${v.n}.mp4`}
      target="_blank"
      rel="noreferrer"
      className={cx(
        "inline-flex min-h-10 items-center justify-center gap-2 rounded-xl px-4 py-2 text-label-md font-semibold transition-colors",
        primary ? "bg-primary text-on-primary shadow-sm hover:bg-primary-container" : "bg-surface-container-high text-on-surface hover:bg-surface-variant",
        className,
      )}
    >
      <Download aria-hidden className="size-[18px]" />
      {label}
    </a>
  );
}

export function VersionLinks({ v }: { v: Version & { parts?: string } }) {
  const source = useSource();
  const links: [string, string][] = source.live
    ? [
        [`${v.ad_dir}/ad.json`, "ad.json"],
        [`${v.ad_dir}/compose.json`, "compose.json (the proof)"],
        [`${v.id}/v${v.n}/brief.json`, "brief.json"],
        [v.level.file, "level.json"],
        ...(v.parts ? ([[v.parts, "parts (metadata)"]] as [string, string][]) : []),
      ]
    : [
        [`${v.id}/v${v.n}/brief.json`, "brief.json"],
        [`${v.id}/v${v.n}/level.json`, "level.json"],
        [`${v.id}/v${v.n}/inventory.json`, "inventory.json"],
      ];
  return (
    <Fold summary="Files of this version">
      <ul className="flex flex-wrap gap-x-4 gap-y-1">
        {links.map(([p, l]) => (
          <li key={p}>
            <a href={source.link(p)} target="_blank" rel="noreferrer" className="text-label-sm font-semibold text-primary hover:underline">
              {l}
            </a>
          </li>
        ))}
      </ul>
    </Fold>
  );
}

export function versionLine(v: Version): string {
  return `${v.length_s} s · level: ${v.level.why} · gameplay ${v.recording.reused ? "reused (not re-recorded)" : "recorded in the game"} · made in ${v.seconds} s`;
}

/** Board size from the level file's gridWidth x gridHeight, else from the why text ("…, 5x6, …"). */
export function boardSize(level: { gridWidth?: number; gridHeight?: number; GridWidth?: number; GridHeight?: number } | null, why: string): string {
  const w = level?.gridWidth ?? level?.GridWidth;
  const h = level?.gridHeight ?? level?.GridHeight;
  if (w && h) return `${w} × ${h}`;
  const m = /(\d+)\s*x\s*(\d+)/.exec(why || "");
  return m ? `${m[1]} × ${m[2]}` : "";
}
