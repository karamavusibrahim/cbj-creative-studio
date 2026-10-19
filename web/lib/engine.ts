// The browser side of the engine API: fetch helpers, job polling, uploads and the one media resolver.
//
// Two ways to reach the engine:
//  - direct: the browser calls `${url}/api/...` itself (the engine allows this site's origin with CORS).
//    Workflow calls and uploads go this way: Vercel functions cap bodies at 4.5 MB, reference videos are 80 MB.
//  - relay: `/api/engine/relay/<path>` on this site, which adds the engine token on the server. Used for reads
//    when the browser has no token (locked), for everything when the site has no passcode and the engine needs a
//    token (the token is handed out only behind a passcode, SPEC-HARDENING §1), and for everything when the engine
//    sends no CORS headers (an engine started without CBJ_CORS_ORIGINS, e.g. the local dev engine).
// Media (<video>, <img>) never needs either: the engine serves /studio/* and /api/sprite/* openly.
// With "My own engine" saved (SPEC-OWN-ENGINE §2) the connection is the user's own engine: always direct, with their
// token, never the relay, and no key headers (lib/keys.ts sends none while it is on).

import { keyHeaders } from "./keys";
import type { Job } from "./types";

export interface EngineConn {
  url: string; // ENGINE_URL, no trailing slash ("" when not known yet)
  token: string; // "" when the engine has none, the session is locked, or the site has no passcode
  direct: boolean; // the engine answers this origin with CORS and the session may call it
  own?: boolean; // the user's own engine (SPEC-OWN-ENGINE): direct always, the relay never
}

const unreachable = (conn: EngineConn) => `${conn.own ? "Your engine" : "The studio engine"} could not be reached.`;

export class EngineError extends Error {
  status: number;
  trace?: string;
  constructor(message: string, status = 0, trace?: string) {
    super(message);
    this.status = status;
    this.trace = trace;
  }
}

/** Where a call goes and its headers. The user's own keys (lib/keys.ts) ride on every POST and on GET /api/meta, on
 *  both paths (the relay forwards them); reads of creatives, studio files and jobs never carry them. */
function target(conn: EngineConn, path: string, method: "GET" | "POST" = "GET"): { href: string; headers: Record<string, string> } {
  const p = path.startsWith("/") ? path : `/${path}`;
  const own = method === "POST" || p.split("?")[0] === "/api/meta" ? keyHeaders() : {};
  if ((conn.direct || conn.own) && conn.url) {
    return { href: `${conn.url}${p}`, headers: { ...(conn.token ? { Authorization: `Bearer ${conn.token}` } : {}), ...own } };
  }
  return { href: `/api/engine/relay${p}`, headers: own };
}

async function readError(r: Response): Promise<string> {
  const text = await r.text().catch(() => "");
  try {
    const j = JSON.parse(text) as { detail?: unknown };
    if (typeof j.detail === "string") return j.detail;
    if (j.detail) return JSON.stringify(j.detail);
  } catch {
    /* not JSON */
  }
  return text.slice(0, 300) || r.statusText || `HTTP ${r.status}`;
}

export async function engineGet<T>(conn: EngineConn, path: string, signal?: AbortSignal): Promise<T> {
  const { href, headers } = target(conn, path);
  let r: Response;
  try {
    r = await fetch(href, { headers, cache: "no-store", signal });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new EngineError(unreachable(conn), 0);
  }
  if (!r.ok) throw new EngineError(await readError(r), r.status);
  return (await r.json()) as T;
}

/** A text answer (the Markdown exports), through the same direct-or-relay path as engineGet. */
export async function engineText(conn: EngineConn, path: string): Promise<string> {
  const { href, headers } = target(conn, path);
  let r: Response;
  try {
    r = await fetch(href, { headers, cache: "no-store" });
  } catch {
    throw new EngineError(unreachable(conn), 0);
  }
  if (!r.ok) throw new EngineError(await readError(r), r.status);
  return r.text();
}

/** Save a text as a file in the browser's downloads. */
export function saveText(text: string, filename: string, type = "text/markdown"): void {
  const url = URL.createObjectURL(new Blob([text], { type: `${type};charset=utf-8` }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function enginePost<T>(conn: EngineConn, path: string, body: unknown): Promise<T> {
  const { href, headers } = target(conn, path, "POST");
  let r: Response;
  try {
    r = await fetch(href, {
      method: "POST",
      headers: { ...headers, "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new EngineError(unreachable(conn), 0);
  }
  if (!r.ok) throw new EngineError(await readError(r), r.status);
  return (await r.json()) as T;
}

export async function uploadFiles(conn: EngineConn, files: File[]): Promise<string[]> {
  const fd = new FormData();
  for (const f of files) fd.append("files", f);
  const { href, headers } = target(conn, "/api/upload", "POST");
  let r: Response;
  try {
    r = await fetch(href, { method: "POST", headers, body: fd });
  } catch {
    throw new EngineError(conn.own ? "The upload could not reach your engine." : "The upload could not reach the studio engine.", 0);
  }
  if (!r.ok) throw new EngineError(await readError(r), r.status);
  const j = (await r.json()) as { uploaded: string[] };
  return j.uploaded;
}

export interface JobUpdate {
  job: Job;
  newLines: Job["lines"];
}

/** Poll a job every 700 ms until it is done (returns its result) or failed (throws with its error). */
export async function pollJob<R>(
  conn: EngineConn,
  jid: string,
  onUpdate: (u: JobUpdate) => void,
  signal?: AbortSignal,
): Promise<R> {
  let since = 0;
  let misses = 0;
  for (;;) {
    if (signal?.aborted) throw new DOMException("stopped", "AbortError");
    let j: Job<R>;
    try {
      j = await engineGet<Job<R>>(conn, `/api/jobs/${encodeURIComponent(jid)}?since=${since}`, signal);
      misses = 0;
    } catch (e) {
      if ((e as Error).name === "AbortError") throw e;
      if (e instanceof EngineError && e.status === 404) throw new EngineError("The engine no longer knows this job (it was restarted).", 404);
      // a dropped poll (tunnel hiccup) is not a failed job: try again a few times
      if (++misses > 8) throw e;
      await sleep(1500);
      continue;
    }
    onUpdate({ job: j as Job, newLines: j.lines });
    since = j.n_lines;
    if (j.status === "done") return j.result as R;
    if (j.status === "failed") throw new EngineError(j.error || "The job failed.", 0, j.trace);
    await sleep(700);
  }
}

export const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Start a job and return its id. */
export async function startJob(conn: EngineConn, path: string, body: unknown): Promise<string> {
  const { job } = await enginePost<{ job: string }>(conn, path, body);
  return job;
}

// ── media ──────────────────────────────────────────────────────────────────────────────────────

/** Where a studio-relative path ("<id>/v1/ad/ad.mp4", "recordings/<hash>/play.json") is served from. */
export interface MediaSource {
  live: boolean; // true: the engine; false: the static showcase under /showcase/
  media: (path: string) => string;
  sprite: (name: string) => string;
  json: <T>(path: string) => Promise<T | null>;
  /** where a link to a studio file opens (a new tab) */
  link: (path: string) => string;
}

const enc = (path: string) => path.split("/").map(encodeURIComponent).join("/");

let SHOWCASE: MediaSource | null = null;

export function showcaseSource(): MediaSource {
  if (SHOWCASE) return SHOWCASE;
  return (SHOWCASE = {
    live: false,
    media: (p) => `/showcase/${enc(p)}`,
    sprite: (n) => `/showcase/sprites/${encodeURIComponent(n)}`,
    link: (p) => `/showcase/${enc(p)}`,
    json: async <T>(p: string) => {
      try {
        const r = await fetch(`/showcase/${enc(p)}`);
        if (!r.ok) return null;
        return (await r.json()) as T;
      } catch {
        return null;
      }
    },
  });
}

export function engineSource(conn: EngineConn): MediaSource {
  return {
    live: true,
    media: (p) => `${conn.url}/studio/${enc(p)}`,
    sprite: (n) => `${conn.url}/api/sprite/${encodeURIComponent(n)}`,
    link: (p) => `${conn.url}/studio/${enc(p)}`,
    json: async <T>(p: string) => {
      try {
        return await engineGet<T>(conn, `/studio/${enc(p)}`);
      } catch {
        return null;
      }
    },
  };
}

/** "1015-074810-create-a-hard-color-block" → "Oct 15, 07:48" (the id starts with the month, day and time it was made). */
export function idTime(id: string): string {
  const m = /^(\d{2})(\d{2})-(\d{2})(\d{2})/.exec(id);
  if (!m) return "";
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const mon = months[Number(m[1]) - 1];
  return mon ? `${mon} ${Number(m[2])}, ${m[3]}:${m[4]}` : "";
}

export function posterOf(id: string, n: number): string {
  return `${id}/v${n}/ad/poster.png`;
}
