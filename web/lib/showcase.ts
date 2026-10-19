// The static showcase under public/showcase/ (written by scripts/export_showcase.py).
// Server components read it from disk; client components fetch it.

import type { ShowcaseDetail, ShowcaseIndex } from "./types";

export async function readIndex(): Promise<ShowcaseIndex> {
  const { readFile } = await import("node:fs/promises");
  const { join } = await import("node:path");
  try {
    const raw = await readFile(join(process.cwd(), "public", "showcase", "index.json"), "utf8");
    return JSON.parse(raw) as ShowcaseIndex;
  } catch {
    return { generated: "", creatives: [] };
  }
}

export async function readDetail(id: string): Promise<ShowcaseDetail | null> {
  if (!/^[A-Za-z0-9_-]+$/.test(id)) return null;
  const { readFile } = await import("node:fs/promises");
  const { join } = await import("node:path");
  try {
    const raw = await readFile(join(process.cwd(), "public", "showcase", id, "showcase.json"), "utf8");
    return JSON.parse(raw) as ShowcaseDetail;
  } catch {
    return null;
  }
}

/** Client side: the index, or an empty one when it is missing. */
export async function fetchIndex(): Promise<ShowcaseIndex> {
  try {
    const r = await fetch("/showcase/index.json");
    if (!r.ok) throw new Error();
    return (await r.json()) as ShowcaseIndex;
  } catch {
    return { generated: "", creatives: [] };
  }
}

export async function fetchDetail(id: string): Promise<ShowcaseDetail | null> {
  try {
    const r = await fetch(`/showcase/${encodeURIComponent(id)}/showcase.json`);
    if (!r.ok) return null;
    return (await r.json()) as ShowcaseDetail;
  } catch {
    return null;
  }
}
