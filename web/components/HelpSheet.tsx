"use client";

import { X } from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";
import { siteOrigin } from "@/lib/ownEngine";

// "How it works": the four workflows, the edit contract and how to run it on your own account, in the engine's own
// plain words.

const Code = ({ children }: { children: ReactNode }) => (
  <code className="rounded-md bg-surface-container px-1.5 py-0.5 font-mono text-code-sm text-on-surface [overflow-wrap:anywhere] box-decoration-clone">{children}</code>
);

const WORKFLOWS: [string, string][] = [
  [
    "Create from text",
    "Write the ad you want. A planner model reads the prompt into a brief: one row for each of the eight prompt controls (level, gameplay, difficulty and pacing, visuals, concept, sequence, assets, what stays unchanged), each marked applied, default, adjusted or not supported. The engine then builds and checks a level, plans the moves, records them in the real game, composes the ad and checks the result against the request.",
  ],
  [
    "Guided by a reference video",
    "Attach an ad (30-60 s) with words like \"inspired by this\". The video is read whole for its idea: the hook, the structure, the pace and the ending. It is never placed in the ad. The plan says what was adapted and what was not copied; Color Block Jam's rules and block mechanics always stay the game's own.",
  ],
  [
    "Guided by a reference image",
    "Attach a picture and say what to take from it (\"this picture's colours\", \"a board like this one\"). The picture is read for its look or its board; a new, solvable level is generated, its cells are not copied. A picture without reference words is an asset to place, like a logo or a sticker.",
  ],
  [
    "Controlled edit",
    "Pick a finished creative and describe one change, or make an exact change from \"Things in this ad\". The route is decided in code from the creative's own metadata, and only the part that needs it is made again: a caption change does not re-film the game.",
  ],
];

export default function HelpSheet({ onClose }: { onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal();
  }, []);
  return (
    <dialog
      ref={ref}
      aria-labelledby="help-title"
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
      className="m-0 ml-auto h-dvh max-h-dvh w-[min(100vw,480px)] max-w-none overflow-y-auto bg-surface-container-lowest p-0 text-on-surface shadow-xl backdrop:bg-inverse-surface/40"
    >
      <div className="flex flex-col gap-5 p-6">
        <div className="flex items-start justify-between gap-3">
          <h2 id="help-title" className="font-headline text-headline-lg text-on-surface">
            How it works
          </h2>
          <button type="button" autoFocus onClick={onClose} aria-label="Close" className="flex size-10 items-center justify-center rounded-lg text-outline hover:bg-surface-container hover:text-on-surface">
            <X aria-hidden className="size-5" />
          </button>
        </div>
        <p className="text-body-md text-on-surface-variant">
          Text, an image or a video in; a 30-60 second Color Block Jam ad out. The level, the moves and the recording come
          from a deterministic game pipeline; a planner model reads the request; every result is checked from the recording.
          The engine makes one creative at a time.
        </p>
        {WORKFLOWS.map(([t, d]) => (
          <section key={t} className="flex flex-col gap-1">
            <h3 className="text-title-sm text-on-surface">{t}</h3>
            <p className="text-body-md text-on-surface-variant">{d}</p>
          </section>
        ))}
        <section className="flex flex-col gap-2 rounded-2xl bg-surface-container-low p-4">
          <h3 className="text-title-sm text-on-surface">The edit contract</h3>
          <p className="text-body-md text-on-surface-variant">
            Every edit comes with a report that compares the new version with the one it came from, item by item:
          </p>
          <ul className="flex flex-col gap-1.5 text-body-md">
            <li>
              <b className="text-tertiary">Locked</b>: kept exactly as it was (the level, the moves and their timing, the camera, the HUD, the other pictures, the sound…).
            </li>
            <li>
              <b className="text-secondary">Allowed</b>: changed, as asked; and what had to change because of it, named with the reason.
            </li>
            <li>
              <b className="text-error">Forbidden</b>: anything changed without being asked. One such row fails the edit.
            </li>
          </ul>
          <p className="text-body-sm text-on-surface-variant">
            A checklist backs it with evidence (the level file&apos;s hash, the drags block by block, every caption&apos;s text, the sound mix),
            and a frame comparison counts which frames changed.
          </p>
        </section>
        <section className="flex flex-col gap-2">
          <h3 className="text-title-sm text-on-surface">Your own account</h3>
          <p className="text-body-md text-on-surface-variant">
            Run the engine on your own Mac with your own Claude account (the Claude Code CLI, logged in; no API key) and use this site with it:
          </p>
          <ol className="flex list-decimal flex-col gap-1.5 pl-6 text-body-md text-on-surface-variant marker:font-semibold marker:text-on-surface">
            <li>
              On your Mac: <Code>claude</Code> once to log in, then in <Code>cbj-creative/.env</Code>: <Code>CBJ_PLANNER=claude</Code> and{" "}
              <Code>GEMINI_API_KEY=...</Code>; <Code>uv run cbj setup-check --live</Code> proves it.
            </li>
            <li>
              Start it for this site: <Code>CBJ_CORS_ORIGINS={siteOrigin()} uv run cbj ui</Code>
            </li>
            <li>Open the key icon, choose <b className="text-on-surface">My own engine</b>, paste the URL and press Check.</li>
          </ol>
          <p className="text-body-sm text-on-surface-variant">
            Or, on the studio&apos;s engine, add only your Gemini key (the key icon, <i>This studio&apos;s engine, with my Gemini key</i>): reference videos are then read on your own quota.
          </p>
        </section>
      </div>
    </dialog>
  );
}
