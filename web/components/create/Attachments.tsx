"use client";

import { Film, ImagePlus, Info, Music, Paperclip, Plus, Trash2, UploadCloud } from "lucide-react";
import { useRef, useState } from "react";
import { AUDIO_EXT, VIDEO_EXT, roleOf } from "@/lib/words";
import SampleAssets from "../SampleAssets";
import { useSource } from "../SourceProvider";
import { Badge, Card, CardTitle, Muted, cx } from "../ui";

// The attachments card (create-brief / create-refs): drop zone, attached files with their role as the
// engine will read them, and the files uploaded before.

export interface Attached {
  name: string; // the engine's name for it (returned by /api/upload)
  size?: number;
  local?: string; // an object URL for a picture uploaded from this tab
}

// Broad on purpose: the picker must not grey out a user's own files (HEIC photos, .mov clips, odd MIME types); the engine
// checks every file by its content and answers with a clear message for one it cannot use.
const ACCEPT = "image/*,video/*,audio/*,.png,.jpg,.jpeg,.webp,.heic,.mp4,.mov,.m4v,.webm,.wav,.mp3,.m4a,.aac,.ogg,.flac";

function mb(n?: number) {
  return n ? `${(n / 1024 / 1024).toFixed(n > 10 * 1024 * 1024 ? 0 : 1)} MB` : "";
}

export default function Attachments({
  files,
  prompt,
  earlier,
  onUpload,
  onSample,
  onAdd,
  onRemove,
  disabled,
  uploading,
  error,
  inputRef,
  title = "Attachments (optional)",
  hint,
}: {
  files: Attached[];
  prompt: string;
  earlier: string[];
  onUpload: (files: File[]) => void;
  /** the same upload, awaited (resolves true when attached): for the catalogue's sample assets */
  onSample?: (files: File[]) => Promise<boolean>;
  onAdd: (name: string) => void;
  onRemove: (name: string) => void;
  disabled: boolean;
  uploading: boolean;
  error: string;
  inputRef: React.RefObject<HTMLInputElement | null>;
  title?: string;
  hint?: string;
}) {
  const source = useSource();
  const [over, setOver] = useState(false);
  const [all, setAll] = useState(false);
  const [openEarlier, setOpenEarlier] = useState(false);
  const rest = earlier.filter((f) => !files.some((x) => x.name === f));
  const shown = all ? rest : rest.slice(0, 12);
  const dropRef = useRef<HTMLDivElement>(null);

  return (
    <Card label={title}>
      <CardTitle
        icon={Paperclip}
        tone="secondary"
        right={
          files.length ? <Badge tone="grey">{files.length} {files.length === 1 ? "file" : "files"}</Badge> : <span className="text-label-sm text-outline">Images, a video or music</span>
        }
      >
        {title}
      </CardTitle>

      {files.length ? (
        <ul className="mb-4 flex flex-col gap-2.5">
          {files.map((f) => {
            const role = roleOf(f.name, prompt);
            const video = VIDEO_EXT.test(f.name);
            const audio = AUDIO_EXT.test(f.name);
            return (
              <li key={f.name} className="flex items-center justify-between gap-3 rounded-xl bg-surface-container-low p-3 transition-colors hover:bg-surface-container">
                <div className="flex min-w-0 items-center gap-3.5">
                  <span
                    className={cx(
                      "relative flex size-14 shrink-0 items-center justify-center overflow-hidden rounded-lg",
                      video || audio ? "bg-inverse-surface text-secondary-container" : "bg-surface-container-highest",
                    )}
                  >
                    {video ? (
                      <Film aria-hidden className="size-6" />
                    ) : audio ? (
                      <Music aria-hidden className="size-6" />
                    ) : (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={f.local || source.media(`uploads/${f.name}`)} alt="" className="h-full w-full object-cover" />
                    )}
                  </span>
                  <span className="flex min-w-0 flex-col">
                    <span className="truncate text-body-md font-semibold text-on-surface">{f.name}</span>
                    <span className="text-body-sm text-on-surface-variant">
                      {[mb(f.size), video ? "Video" : audio ? "Music" : "Image"].filter(Boolean).join(" · ")}
                    </span>
                    <span className="mt-1 sm:hidden">
                      <Badge tone={role.tone === "primary" ? "violet" : role.tone === "tertiary" ? "mint" : "sky"} className="!whitespace-normal">
                        {role.word}
                      </Badge>
                    </span>
                  </span>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <span className="hidden max-w-[16rem] sm:block">
                    <Badge tone={role.tone === "primary" ? "violet" : role.tone === "tertiary" ? "mint" : "sky"} className="!whitespace-normal text-right">
                      {role.word}
                    </Badge>
                  </span>
                  <button
                    type="button"
                    onClick={() => onRemove(f.name)}
                    aria-label={`Remove ${f.name}`}
                    className="flex size-10 items-center justify-center rounded-lg text-on-surface-variant transition-colors hover:bg-error-container/40 hover:text-error"
                  >
                    <Trash2 aria-hidden className="size-[18px]" />
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      ) : null}

      <div
        ref={dropRef}
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-disabled={disabled}
        aria-label="Attach files: drop them here or press to choose"
        onClick={() => !disabled && inputRef.current?.click()}
        onKeyDown={(e) => {
          if (!disabled && (e.key === "Enter" || e.key === " ")) {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          if (!disabled && e.dataTransfer.files.length) onUpload([...e.dataTransfer.files]);
        }}
        className={cx(
          "group relative flex flex-col items-center justify-center rounded-xl p-5 text-center transition-all",
          disabled ? "cursor-not-allowed bg-surface-container-low/50 opacity-70" : "cursor-pointer bg-surface-container-low/70 hover:bg-surface-container-high/60",
          over && "bg-primary-fixed/50 ring-2 ring-primary-container",
        )}
      >
        {!disabled ? (
          <input
            type="file"
            multiple
            accept={ACCEPT}
            title="Choose files from your computer"
            aria-label="Choose files from your computer"
            className="absolute inset-0 z-10 h-full w-full cursor-pointer opacity-0"
            onClick={(e) => e.stopPropagation()}
            onChange={(e) => {
              if (e.target.files?.length) onUpload([...e.target.files]);
              e.target.value = "";
            }}
          />
        ) : null}
        <span className="mb-3 flex size-12 items-center justify-center rounded-full bg-surface-container-lowest text-primary shadow-sm transition-transform group-hover:scale-105">
          {files.length ? <Plus aria-hidden className="size-6" /> : <UploadCloud aria-hidden className="size-6" />}
        </span>
        <p className="mb-1 text-body-md font-medium text-on-surface">
          {uploading ? "Uploading…" : disabled ? "Attachments need the engine" : "Drop images, a reference video or music here"}
        </p>
        {disabled && !uploading ? (
          <p role="status" className="mb-2 text-body-sm font-semibold text-error">
            The studio engine is offline or busy with your creative right now, so files cannot be attached. Try again when the header says Engine online.
          </p>
        ) : null}
        {!disabled ? (
          <label
            className="relative z-20 mb-2 inline-flex min-h-10 cursor-pointer items-center gap-2 rounded-full bg-primary px-4 text-label-md font-semibold text-on-primary shadow-sm hover:bg-primary/90 focus-within:ring-2 focus-within:ring-primary-container"
            onClick={(e) => e.stopPropagation()}
          >
            <Paperclip aria-hidden className="size-4" />
            Choose files from your computer
            <input
              type="file"
              multiple
              accept={ACCEPT}
              className="sr-only"
              onChange={(e) => {
                if (e.target.files?.length) onUpload([...e.target.files]);
                e.target.value = "";
              }}
            />
          </label>
        ) : null}
        <p className="max-w-md text-body-sm text-outline">
          {hint ||
            "A logo, a mascot or end-card art to place; or a reference image or video (“inspired by this”, “a Color Block Jam version of this concept”). Say in the prompt how to use them."}
        </p>
        <p className="mt-2 flex flex-wrap justify-center gap-x-3 text-body-sm text-on-surface-variant">
          <span className="inline-flex items-center gap-1">
            <ImagePlus aria-hidden className="size-3.5 text-secondary" /> PNG, JPG, WebP ≤ 15 MB
          </span>
          <span className="inline-flex items-center gap-1">
            <Film aria-hidden className="size-3.5 text-primary" /> MP4, MOV, WebM ≤ 80 MB
          </span>
          <span className="inline-flex items-center gap-1">
            <Music aria-hidden className="size-3.5 text-tertiary" /> WAV, MP3, M4A, AAC, OGG, FLAC
          </span>
        </p>
      </div>
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={ACCEPT}
        className="hidden"
        tabIndex={-1}
        aria-hidden
        onChange={(e) => {
          if (e.target.files?.length) onUpload([...e.target.files]);
          e.target.value = "";
        }}
      />
      {onSample ? <SampleAssets onAttach={onSample} disabled={disabled} className="mt-3" /> : null}
      {error ? (
        <p role="alert" className="mt-3 text-body-sm font-semibold text-error">
          {error}
        </p>
      ) : null}

      {rest.length ? (
        <div className="mt-3">
          <button
            type="button"
            aria-expanded={openEarlier}
            onClick={() => setOpenEarlier(!openEarlier)}
            className="inline-flex min-h-9 items-center gap-1 rounded-lg text-label-sm font-semibold text-on-surface-variant hover:text-on-surface"
          >
            <Plus aria-hidden className={cx("size-4 transition-transform", openEarlier && "rotate-45")} />
            Use a file uploaded before ({rest.length})
          </button>
          {openEarlier ? (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {shown.map((f) => (
              <button
                key={f}
                type="button"
                disabled={disabled}
                onClick={() => onAdd(f)}
                className="inline-flex min-h-8 max-w-full items-center gap-1 truncate rounded-full bg-surface-container px-3 py-1 text-label-sm text-on-surface-variant transition-colors hover:bg-surface-container-high hover:text-on-surface disabled:opacity-50"
              >
                <Plus aria-hidden className="size-3.5 shrink-0" /> <span className="truncate">{f}</span>
              </button>
            ))}
            {rest.length > 12 ? (
              <button type="button" onClick={() => setAll(!all)} className="min-h-8 rounded-full px-3 py-1 text-label-sm font-semibold text-primary hover:underline">
                {all ? "Show fewer" : `Show all ${rest.length}`}
              </button>
            ) : null}
          </div>
          ) : null}
        </div>
      ) : null}

      <div className="mt-4 flex items-start gap-3 rounded-xl bg-surface-container-high/60 p-3.5">
        <Info aria-hidden className="mt-0.5 size-5 shrink-0 text-primary" />
        <Muted className="leading-relaxed">
          Attachments guide the look, the board and the pacing. Color Block Jam&apos;s rules and block mechanics are always preserved.
        </Muted>
      </div>
    </Card>
  );
}
