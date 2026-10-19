"use client";

import { Hand, ImageIcon, Music, Type, Volume2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { InventoryItem, Version } from "@/lib/types";
import { useSource } from "./SourceProvider";
import { Button, Card, CardTitle, Muted, cx } from "./ui";

// "Things in this ad" (loadThings / thingAction): every picture, caption, the sound and the music, each
// with the exact action the engine supports. No prompt needed; everything else stays as it is.

export type DirectOp =
  | { picture: string; file: string | null; block?: string }
  | { caption: string; text: string }
  | { sound: boolean }
  | { music: string | null };

export interface InventoryActions {
  direct: (op: DirectOp, label: string) => void;
  upload: (file: File) => Promise<string | null>;
  disabled: boolean;
}

const BLOCK_COLOURS = ["Green", "Yellow", "Blue", "Red", "Orange", "Purple", "DarkGreen"]; // the game's enum order

function Thumb({ t }: { t: InventoryItem }) {
  const source = useSource();
  const f = t.file || "";
  const box = "flex size-14 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-inverse-surface text-[10px] text-inverse-on-surface";
  if (t.kind === "caption") return <div className={box}><Type aria-hidden className="size-5" /></div>;
  if (t.kind === "sound") return <div className={box}><Volume2 aria-hidden className="size-5" /></div>;
  if (t.kind === "music") return <div className={box}><Music aria-hidden className="size-5" /></div>;
  if (!f) return <div className={box}><ImageIcon aria-hidden className="size-5 opacity-50" /></div>;
  if (f.startsWith("gradient")) {
    const c = f.split(" ").filter((x) => x.startsWith("#"));
    return <div className={box} style={{ background: `linear-gradient(${c[0]}, ${c[1] || c[0]})` }} aria-hidden />;
  }
  if (f === "tap ring") return <div className={box}><span className="size-7 rounded-full border-2 border-white/80" aria-hidden /></div>;
  if (f === "builtin:hand") return <div className={box}><Hand aria-hidden className="size-6" /></div>;
  const name = f.split("/").pop() || f;
  const src = f.includes("/uploads/") ? source.media(`uploads/${name}`) : source.sprite(name);
  return (
    <div className={box}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={src} alt="" loading="lazy" className="max-h-full max-w-full object-contain" onError={(e) => (e.currentTarget.style.visibility = "hidden")} />
    </div>
  );
}

function CaptionEditor({ t, onSave, onCancel, disabled }: { t: InventoryItem; onSave: (text: string) => void; onCancel: () => void; disabled: boolean }) {
  const [text, setText] = useState(t.text || "");
  return (
    <form
      className="col-span-full flex flex-wrap items-end gap-2 pb-1"
      onSubmit={(e) => {
        e.preventDefault();
        if (text !== t.text) onSave(text);
      }}
    >
      <label className="flex min-w-0 flex-1 flex-col gap-1 text-label-sm text-on-surface-variant">
        New text for {t.name}
        <input
          autoFocus
          value={text}
          onChange={(e) => setText(e.target.value)}
          className="min-h-10 rounded-lg bg-surface-container-low px-3 text-body-md text-on-surface outline-none ring-1 ring-outline-variant/50 focus:ring-2 focus:ring-primary-container"
        />
      </label>
      <Button size="sm" variant="primary" type="submit" disabled={disabled || text === t.text}>
        Apply
      </Button>
      <Button size="sm" variant="quiet" onClick={onCancel}>
        Cancel
      </Button>
    </form>
  );
}

export default function Inventory({ v, items, actions }: { v: Version; items: InventoryItem[] | null; actions: InventoryActions | null }) {
  const source = useSource();
  const file = useRef<HTMLInputElement>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [skin, setSkin] = useState<{ upload: string; colours: string[] } | null>(null);
  const [replacing] = useState<InventoryItem | null>(null);
  const [note, setNote] = useState("");

  useEffect(() => {
    // a new version: close any open editor
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setEditing(null);
    setSkin(null);
  }, [v.id, v.n]);

  async function boardColours(): Promise<string[]> {
    const lv = await source.json<{ GridBlockDatas?: { blockColor: number }[] }>(v.level.file);
    const got = [...new Set((lv?.GridBlockDatas || []).map((b) => BLOCK_COLOURS[b.blockColor]).filter(Boolean))];
    return got.length ? got : BLOCK_COLOURS;
  }


  async function picked(files: FileList | null, item?: InventoryItem) {
    const t = item || replacing;
    if (!actions || !t || !files?.length) return;
    setNote("Uploading…");
    const name = await actions.upload(files[0]);
    setNote("");
    if (!name) return;
    if (t.id === "skin") {
      setSkin({ upload: name, colours: await boardColours() });
      return;
    }
    if (t.kind === "music") actions.direct({ music: name }, `Music: ${name}`);
    else actions.direct({ picture: t.id, file: name }, `${t.name}: ${name}`);
  }

  return (
    <Card label="Things in this ad">
      <CardTitle icon={ImageIcon} tone="secondary">
        Things in this ad
      </CardTitle>
      <Muted className="mb-3">
        {actions
          ? "Replace, remove or rewrite one thing; everything else stays exactly as it is. No prompt needed."
          : "Every picture, caption and sound in this version, with when it shows."}
      </Muted>
      {items === null ? (
        <Muted>Loading…</Muted>
      ) : !items.length ? (
        <Muted>Nothing listed for this version.</Muted>
      ) : (
        <ul className="flex flex-col divide-y divide-surface-variant">
          {items.map((t) => {
            const when = t.when ? `${t.when[0]}-${t.when[1]} s` : "";
            return (
              <li key={t.id} className="grid grid-cols-[3.5rem_1fr] items-center gap-x-3 gap-y-2 py-2.5 @md:grid-cols-[3.5rem_1fr_auto]">
                <Thumb t={t} />
                <div className="min-w-0 text-body-sm">
                  <p className="font-semibold text-on-surface">
                    {t.name} {when ? <span className="font-normal text-outline">{when}</span> : null}
                  </p>
                  <p className="break-words text-on-surface-variant">
                    {t.kind === "caption" ? <i>“{t.text}”</i> : t.empty ? "none" : t.shows}
                  </p>
                </div>
                {actions ? (
                  <div className="col-span-full flex flex-wrap gap-1.5 @md:col-span-1 @md:justify-end">
                    {t.kind === "picture" || t.kind === "music" ? (
                      <label
                        className={cx(
                          "inline-flex min-h-9 cursor-pointer items-center rounded-lg px-3 text-label-md font-semibold text-primary hover:bg-surface-container focus-within:ring-2 focus-within:ring-primary-container",
                          actions.disabled && "pointer-events-none opacity-50",
                        )}
                      >
                        {t.empty || (t.kind === "music" && !t.file) ? "Add" : "Replace"}
                        <input
                          type="file"
                          className="sr-only"
                          disabled={actions.disabled}
                          accept={t.kind === "music" ? "audio/*,.wav,.mp3,.m4a,.aac,.ogg,.flac" : "image/*,.png,.jpg,.jpeg,.webp,.heic"}
                          onChange={(e) => {
                            const list = e.target.files;
                            e.target.value = "";
                            void picked(list, t);
                          }}
                        />
                      </label>
                    ) : null}
                    {t.kind === "caption" ? (
                      <Button size="sm" variant="ghost" disabled={actions.disabled} onClick={() => setEditing(editing === t.id ? null : t.id)}>
                        Edit text
                      </Button>
                    ) : null}
                    {t.kind === "sound" ? (
                      <Button size="sm" variant="ghost" disabled={actions.disabled} onClick={() => actions.direct({ sound: t.shows !== "on" }, t.shows === "on" ? "Sound off" : "Sound on")}>
                        {t.shows === "on" ? "Turn off" : "Turn on"}
                      </Button>
                    ) : null}
                    {t.can_remove && t.kind !== "sound" ? (
                      <Button
                        size="sm"
                        variant="quiet"
                        disabled={actions.disabled}
                        onClick={() =>
                          t.kind === "caption"
                            ? actions.direct({ caption: t.id, text: "" }, `Remove ${t.name}`)
                            : t.kind === "music"
                              ? actions.direct({ music: null }, "Remove the music")
                              : actions.direct({ picture: t.id, file: null }, `Remove ${t.name}`)
                        }
                      >
                        Remove
                      </Button>
                    ) : null}
                  </div>
                ) : null}
                {actions && editing === t.id ? (
                  <CaptionEditor
                    t={t}
                    disabled={actions.disabled}
                    onCancel={() => setEditing(null)}
                    onSave={(text) => {
                      setEditing(null);
                      actions.direct({ caption: t.id, text }, `${t.name}: “${text}”`);
                    }}
                  />
                ) : null}
                {actions && skin && t.id === "skin" ? (
                  <div className="col-span-full rounded-xl bg-surface-container-low p-3">
                    <p className="mb-2 text-label-md">Which block gets the texture?</p>
                    <div className="flex flex-wrap gap-1.5">
                      {skin.colours.map((c) => (
                        <Button
                          key={c}
                          size="sm"
                          variant="ghost"
                          disabled={actions.disabled}
                          onClick={() => {
                            const up = skin.upload;
                            setSkin(null);
                            actions.direct({ picture: "skin", file: up, block: c }, `Texture on the ${c} block`);
                          }}
                        >
                          {c}
                        </Button>
                      ))}
                      <Button size="sm" variant="quiet" onClick={() => setSkin(null)}>
                        Cancel
                      </Button>
                    </div>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
      {note ? <Muted className="mt-2">{note}</Muted> : null}
      <input ref={file} type="file" className="hidden" aria-hidden tabIndex={-1} onChange={(e) => void picked(e.target.files)} />
    </Card>
  );
}
