// The catalogue (SPEC-R2-CATALOGUE): more finished creatives in a public Cloudflare R2 bucket, in exactly the static
// showcase's layout (index.json, <id>/showcase.json, <id>/v<n>/ad/ad.mp4, posters, boards, sprites/, uploads/…),
// published by ../scripts/r2_publish.py. Read client-side only, so it grows without a redeploy and with the Mac off.
// Off when NEXT_PUBLIC_CATALOGUE_URL is not set. The ten curated creatives of the static showcase stay first and
// unchanged: a creative in both is taken from the static copy.

import type { MediaSource } from "./engine";
import type { ShowcaseDetail, ShowcaseIndex, ShowcaseIndexEntry } from "./types";

/** The bucket's public base URL, no trailing slash ("" when the catalogue is off). */
export const CATALOGUE_URL = (process.env.NEXT_PUBLIC_CATALOGUE_URL || "").trim().replace(/\/+$/, "");

export const catalogueOn = () => CATALOGUE_URL !== "";

const enc = (path: string) => path.split("/").map(encodeURIComponent).join("/");

let index: Promise<ShowcaseIndexEntry[] | null> | null = null;
let logged = false;

function warnOnce(what: string) {
  if (logged) return;
  logged = true;
  console.warn(`The catalogue could not be read (${what}); showing the curated showcase only.`);
}

/** The catalogue's creatives, in its order: [] when it is off, null when it could not be read (logged once). Asked once
 *  per page session. */
export function fetchCatalogue(): Promise<ShowcaseIndexEntry[] | null> {
  if (!catalogueOn()) return Promise.resolve([]);
  if (index) return index;
  index = (async () => {
    try {
      const r = await fetch(`${CATALOGUE_URL}/index.json`, { cache: "no-store" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const j = (await r.json()) as Partial<ShowcaseIndex>;
      if (!Array.isArray(j.creatives)) throw new Error("no creatives");
      return j.creatives.filter((c): c is ShowcaseIndexEntry => Boolean(c && typeof c.id === "string" && Array.isArray(c.versions)));
    } catch (e) {
      warnOnce((e as Error).message || "unreachable");
      index = null; // a later visit to the gallery may try again
      return null;
    }
  })();
  return index;
}

export interface CatalogueEntry extends ShowcaseIndexEntry {
  catalogue?: boolean; // true: from the bucket (its media resolve there)
}

/** The static items first and unchanged, then the catalogue's others in its order. */
export function mergeCatalogue(curated: ShowcaseIndexEntry[], more: ShowcaseIndexEntry[]): CatalogueEntry[] {
  const seen = new Set(curated.map((c) => c.id));
  const extra: CatalogueEntry[] = [];
  for (const c of more) {
    if (seen.has(c.id)) continue;
    seen.add(c.id);
    extra.push({ ...c, catalogue: true });
  }
  return [...curated, ...extra];
}

export type CatalogueDetail = { state: "ok"; detail: ShowcaseDetail } | { state: "missing" } | { state: "error" };

/** One creative's <id>/showcase.json from the bucket. */
export async function fetchCatalogueDetail(id: string): Promise<CatalogueDetail> {
  if (!catalogueOn() || !/^[A-Za-z0-9_-]+$/.test(id)) return { state: "missing" };
  try {
    const r = await fetch(`${CATALOGUE_URL}/${encodeURIComponent(id)}/showcase.json`, { cache: "no-store" });
    if (r.status === 404 || r.status === 403) return { state: "missing" }; // R2 answers a missing key with 404 (403 when listing is off)
    if (!r.ok) return { state: "error" };
    const d = (await r.json()) as ShowcaseDetail;
    return d && Array.isArray(d.versions) ? { state: "ok", detail: d } : { state: "missing" };
  } catch {
    return { state: "error" };
  }
}

/** A studio-relative path in the bucket. */
export const catalogueMedia = (path: string) => `${CATALOGUE_URL}/${enc(path)}`;

let SOURCE: MediaSource | null = null;

/** The third media source, next to the engine's and the static showcase's: a catalogue creative's files are always read
 *  from the bucket, even with the engine online (it may not hold that creative any more). */
export function catalogueSource(): MediaSource {
  if (SOURCE) return SOURCE;
  return (SOURCE = {
    live: false,
    media: catalogueMedia,
    sprite: (n) => `${CATALOGUE_URL}/sprites/${encodeURIComponent(n)}`,
    link: catalogueMedia,
    json: async <T>(p: string) => {
      try {
        const r = await fetch(catalogueMedia(p));
        if (!r.ok) return null;
        return (await r.json()) as T;
      } catch {
        return null;
      }
    },
  });
}

// ── sample assets (SPEC-SAMPLE-ASSETS) ─────────────────────────────────────────────────────────────
// The files the tool was built and tested with (trailers, reference pictures, objects, textures, logos, stickers, a music
// track), published with the catalogue at <base>/assets/index.json. Offered where files are attached; an attached one
// goes through the same upload as a dropped file.

export type SampleKind = "image" | "video" | "audio";

export interface SampleAsset {
  file: string; // the file name it is attached under
  path: string; // bucket-relative
  about: string;
  bytes: number;
  kind: SampleKind;
}

export interface SampleAssets {
  note: string;
  groups: { title: string; items: SampleAsset[] }[];
}

const MIME: Record<string, string> = {
  png: "image/png",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  webp: "image/webp",
  gif: "image/gif",
  heic: "image/heic",
  mp4: "video/mp4",
  m4v: "video/mp4",
  mov: "video/quicktime",
  webm: "video/webm",
  wav: "audio/wav",
  mp3: "audio/mpeg",
  m4a: "audio/mp4",
  aac: "audio/aac",
  ogg: "audio/ogg",
  flac: "audio/flac",
};

const extOf = (name: string) => (/\.([a-z0-9]+)$/i.exec(name)?.[1] || "").toLowerCase();

function kindOf(name: string, said: unknown): SampleKind {
  if (said === "image" || said === "video" || said === "audio") return said;
  const t = MIME[extOf(name)] || "";
  return t.startsWith("video/") ? "video" : t.startsWith("audio/") ? "audio" : "image";
}

/** A bucket-relative path that stays in the bucket (no scheme, no leading slash, no "..", no backslash). */
const safePath = (p: string) => p !== "" && !/^\/|:\/\/|\\/.test(p) && !p.split("/").some((s) => s === ".." || s === "." || s === "");

let samples: Promise<SampleAssets | null> | null = null;

/** The sample assets' index: null when the catalogue is off or the index could not be read (silently: the link is
 *  simply not shown). Asked once per page session. */
export function fetchSampleAssets(): Promise<SampleAssets | null> {
  if (!catalogueOn()) return Promise.resolve(null);
  if (samples) return samples;
  samples = (async () => {
    try {
      const r = await fetch(`${CATALOGUE_URL}/assets/index.json`, { cache: "no-store" });
      if (!r.ok) return null;
      const j = (await r.json()) as { note?: unknown; groups?: unknown };
      if (!Array.isArray(j.groups)) return null;
      const groups = j.groups
        .map((g: { title?: unknown; items?: unknown }) => ({
          title: typeof g?.title === "string" ? g.title : "",
          items: (Array.isArray(g?.items) ? g.items : [])
            .filter((i: Partial<SampleAsset>) => i && typeof i.path === "string" && safePath(i.path))
            .map((i: Partial<SampleAsset>) => {
              const path = i.path as string;
              const file = ((typeof i.file === "string" && i.file) || path).split("/").pop() || path;
              return {
                file,
                path,
                about: typeof i.about === "string" ? i.about : "",
                bytes: typeof i.bytes === "number" && i.bytes > 0 ? i.bytes : 0,
                kind: kindOf(file, i.kind),
              };
            }),
        }))
        .filter((g) => g.items.length);
      return groups.length ? { note: typeof j.note === "string" ? j.note : "", groups } : null;
    } catch {
      return null;
    }
  })();
  return samples;
}

/** A sample asset's bytes from the bucket, as a File with its name and type (exactly what a drop hands over). Throws
 *  with a sentence for the error line. */
export async function sampleAssetFile(a: SampleAsset): Promise<File> {
  let r: Response;
  try {
    r = await fetch(catalogueMedia(a.path));
  } catch {
    throw new Error(`${a.file} could not be downloaded: the catalogue could not be reached.`);
  }
  if (!r.ok) throw new Error(`${a.file} could not be downloaded from the catalogue (HTTP ${r.status}).`);
  const blob = await r.blob();
  const sent = (blob.type || "").split(";")[0];
  const type = sent && sent !== "application/octet-stream" && sent !== "binary/octet-stream" ? sent : MIME[extOf(a.file)] || sent;
  return new File([blob], a.file, { type });
}
