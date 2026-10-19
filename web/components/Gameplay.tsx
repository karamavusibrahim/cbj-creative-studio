"use client";

import { Grid3x3 } from "lucide-react";
import { useEffect, useState } from "react";
import type { Beat, Check, Play, Version } from "@/lib/types";
import { useSource } from "./SourceProvider";
import { checkStep } from "@/lib/words";
import { FlagButton } from "./FeedbackPanel";
import { Badge, Card, CardTitle, Muted, type Tone } from "./ui";

// "Level & gameplay" (renderGameplay): the board, why this level, the moves with their kind, and the
// checks read from the recording and the level file.

export interface GameplayData {
  board?: string | null;
  level_why: string;
  beats: Beat[];
  notes?: string[];
  frames?: [number, number][];
  checks?: Check[];
}

function kindOf(b: Beat): [Tone, string] {
  if (b.tag === "key") return ["mint", "key move"];
  if (b.kind === "mistake") return ["error", "mistake"];
  if (b.kind === "hesitate") return ["amber", "hesitates"];
  if (b.kind === "short") return ["error", "cut short"];
  if (b.kind === "bump" || b.kind === "attempt") return ["error", "blocked"];
  if (b.exits) return ["sky", "leaves"];
  return ["grey", "moves"];
}

const CHECK_TONE: Record<string, Tone> = { pass: "mint", fail: "error", failed: "error", info: "grey", adjusted: "amber" };

export function ChecksTable({ checks }: { checks: Check[] }) {
  if (!checks.length) return null;
  return (
    <div className="mt-5">
      <h3 className="mb-2 text-label-md font-semibold text-on-surface">Checks from the recording and the level file</h3>
      <ul className="flex flex-col divide-y divide-surface-variant overflow-hidden rounded-xl ring-1 ring-surface-variant">
        {checks.map((c, i) => (
          <li key={i} className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 px-3 py-2.5 @md:grid-cols-[5.5rem_1fr_auto]">
            <span className="row-span-2 @md:row-span-1">
              <Badge tone={CHECK_TONE[c.status] || "grey"}>{c.status}</Badge>
            </span>
            <div className="min-w-0">
              <span className="flex items-start gap-1">
                <b className="text-body-md">{c.check}</b>
                {c.status === "failed" || c.status === "fail" ? <FlagButton title={c.check} step={checkStep(c.check)} className="-my-1.5" /> : null}
              </span>
              <p className="text-body-sm text-on-surface-variant">{c.detail}</p>
            </div>
            <span className="text-body-sm text-outline @md:text-right">{c.from}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function GameplayCard({ data, title }: { data: GameplayData; title: string }) {
  const source = useSource();
  return (
    <Card label="Level and gameplay">
      <CardTitle icon={Grid3x3} tone="tertiary">
        Level &amp; gameplay
      </CardTitle>
      <Muted className="mb-4">{title}</Muted>
      <div className="grid gap-5 @lg:grid-cols-[minmax(160px,260px)_1fr]">
        <div>
          {data.board ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={source.media(data.board)} alt="The level's board" loading="lazy" className="w-full rounded-xl bg-surface-container-low" />
          ) : (
            <Muted>(made before the board picture existed)</Muted>
          )}
          <p className="mt-2 text-body-sm text-on-surface-variant">{data.level_why}</p>
        </div>
        <div className="min-w-0">
          <h3 className="mb-2 text-label-md font-semibold text-on-surface">Moves</h3>
          {data.beats.length ? (
            <ol className="flex max-h-[340px] flex-col gap-1.5 overflow-auto pr-1 text-body-sm">
              {data.beats.map((b, i) => {
                const [tone, word] = kindOf(b);
                const f = data.frames?.[i];
                return (
                  <li key={i} className="flex items-start gap-2">
                    <span className="w-5 shrink-0 pt-0.5 text-right font-mono text-[11px] text-outline">{i + 1}</span>
                    <Badge tone={tone} className="shrink-0 uppercase !text-[10.5px]">
                      {word}
                    </Badge>
                    <span className="min-w-0">
                      {b.note}
                      {f ? <span className="ml-1 text-outline">{(f[0] / 30).toFixed(1)} s</span> : null}
                    </span>
                  </li>
                );
              })}
            </ol>
          ) : (
            <Muted>The moves are not available for this version.</Muted>
          )}
          {data.notes?.length ? (
            <div className="mt-3 text-body-sm text-amber">
              {data.notes.map((n, i) => (
                <p key={i}>{n}</p>
              ))}
            </div>
          ) : null}
        </div>
      </div>
      <ChecksTable checks={data.checks || []} />
    </Card>
  );
}

/** The gameplay of a finished version: its board and checks, and the moves from its recording's play.json. */
export default function VersionGameplay({ v }: { v: Version }) {
  const source = useSource();
  const [play, setPlay] = useState<{ key: string; play: Play | null } | null>(null);
  const key = `${source.live}:${v.recording.dir}`;
  useEffect(() => {
    let live = true;
    source.json<Play>(`${v.recording.dir}/play.json`).then((p) => {
      if (live) setPlay({ key, play: p });
    });
    return () => {
      live = false;
    };
  }, [source, v.recording.dir, key]);
  const p = play && play.key === key ? play.play : null;
  return (
    <GameplayCard
      title={`v${v.n}: recorded in the game. Checks read from the recording and the level file.`}
      data={{ board: v.board, level_why: v.level.why, checks: v.checks || [], beats: p?.beats || [], notes: p?.notes || [], frames: p?.measured?.beat_frames }}
    />
  );
}
