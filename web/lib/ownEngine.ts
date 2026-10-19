// "My own engine" (SPEC-OWN-ENGINE §1, §3): the dialog's Check, the status poll and the words for an engine the user
// runs on their own Mac (`uv run cbj ui` with CBJ_PLANNER=claude and their GEMINI_API_KEY). Every call here goes from
// this browser straight to that engine; nothing passes through this site's server.

import type { Meta } from "./types";
import type { OwnEngine } from "./keys";

export const SITE = "https://cbj-creative-studio.vercel.app";

/** This site's origin, as the engine's CBJ_CORS_ORIGINS must name it. */
export function siteOrigin(): string {
  return typeof window === "undefined" ? SITE : window.location.origin;
}

export type CheckFail = "invalid" | "unreachable" | "cors" | "token" | "mixed" | "http" | "foreign";

export type CheckResult =
  | { ok: true; line: string; meta: Meta }
  | { ok: false; reason: CheckFail; message: string };

const LOOPBACK = /^(localhost|127\.\d+\.\d+\.\d+|\[::1\])$/i;

/** Safari (desktop or iOS), not a Chromium or Firefox that also says "Safari" in its user agent. */
export function isSafari(ua = typeof navigator === "undefined" ? "" : navigator.userAgent): boolean {
  return /Safari\//.test(ua) && !/Chrome\/|Chromium\/|CriOS\/|FxiOS\/|EdgiOS\/|Edg\/|OPR\/|Android/.test(ua);
}

/** Would this browser block an http engine from this page before any request leaves it? */
function mixedBlocked(url: URL): "safari" | "remote" | null {
  if (typeof window === "undefined" || window.location.protocol !== "https:" || url.protocol !== "http:") return null;
  if (!LOOPBACK.test(url.hostname)) return "remote"; // every browser blocks plain http to another machine
  return isSafari() ? "safari" : null; // Chrome, Edge and Firefox allow http://127.0.0.1 and http://localhost
}

export const MIXED_SAFARI =
  "Blocked by the browser (mixed content): Safari blocks http://127.0.0.1 from an https page. Use Chrome, Edge or Firefox, or a tunnel URL (https://…).";
const MIXED_REMOTE =
  "Blocked by the browser (mixed content): an https page cannot call a plain http address on another machine. Use a tunnel URL (https://…), or http://127.0.0.1 in Chrome, Edge or Firefox.";

const unreachable = (url: string) =>
  `Not reachable: nothing answered at ${url}. Is \`uv run cbj ui\` running on your Mac? (Chrome may ask to allow access to your local network: allow it.)`;
const corsBlocked = () =>
  `Blocked by CORS: the engine answered but does not allow this site. Start it with \`CBJ_CORS_ORIGINS=${siteOrigin()} uv run cbj ui\`.`;
const WRONG_TOKEN = "Wrong token (401): the engine refused it. Paste the value of CBJ_API_TOKEN from the engine's .env, or leave the field empty if you set none.";

const auth = (token?: string): Record<string, string> => (token ? { Authorization: `Bearer ${token}` } : {});

/** A failed fetch (no answer at all): mixed content, CORS, or nothing listening. A no-cors request tells the last two
 *  apart: it resolves (opaquely) whenever something answered, CORS or not. */
async function whyFailed(href: string, base: URL): Promise<CheckResult & { ok: false }> {
  const mixed = mixedBlocked(base);
  if (mixed) return { ok: false, reason: "mixed", message: mixed === "safari" ? MIXED_SAFARI : MIXED_REMOTE };
  try {
    await fetch(href, { mode: "no-cors", cache: "no-store", signal: AbortSignal.timeout(5000) });
    return { ok: false, reason: "cors", message: corsBlocked() };
  } catch {
    // Safari on an https page fails both requests the same way: say what to do instead
    if (isSafari() && typeof window !== "undefined" && window.location.protocol === "https:" && base.protocol === "http:") {
      return { ok: false, reason: "mixed", message: MIXED_SAFARI };
    }
    return { ok: false, reason: "unreachable", message: unreachable(base.origin) };
  }
}

async function detail(r: Response): Promise<string> {
  const text = await r.text().catch(() => "");
  try {
    const d = (JSON.parse(text) as { detail?: unknown }).detail;
    if (typeof d === "string") return d;
  } catch {
    /* not JSON */
  }
  return text.slice(0, 200) || r.statusText;
}

/** "claude-cli/opus": the planner as <backend>/<model> (the engine's first model usually already says both). */
export function plannerLabel(models: string[] | undefined, backend: string | null | undefined): string {
  const m = models?.[0];
  if (!m) return backend || "";
  return m.includes("/") || !backend ? m : `${backend}/${m}`;
}

/** Does meta say whether the engine has a Gemini key of its own? Older and current engines do not; a later one may. */
function geminiKey(meta: Meta): boolean | null {
  const m = meta as unknown as Record<string, unknown>;
  const f = (meta.features || {}) as Record<string, unknown>;
  for (const v of [f.gemini, f.video_reader, f.reader, m.gemini, m.gemini_key]) {
    if (typeof v === "boolean") return v;
    if (v && typeof v === "object" && typeof (v as { key?: unknown }).key === "boolean") return (v as { key: boolean }).key;
  }
  return null;
}

/** The one line a successful Check shows: "Reachable · planner: claude-cli/opus · voice: yes" (and the Gemini key when
 *  meta says it). */
export function reachableLine(meta: Meta): string {
  const parts = ["Reachable"];
  const planner = plannerLabel(meta.models, meta.backend);
  if (planner) parts.push(`planner: ${planner}`);
  const g = geminiKey(meta);
  if (g !== null) parts.push(`Gemini key: ${g ? "yes" : "no"}`);
  const voice = meta.features?.soundtrack?.voice;
  if (typeof voice === "boolean") parts.push(`voice: ${voice ? "yes" : "no"}`);
  return parts.join(" · ");
}

/** The dialog's Check: GET /api/health and /api/meta from this browser, with the token as Bearer when given. */
export async function checkEngine(e: OwnEngine): Promise<CheckResult> {
  let base: URL;
  try {
    base = new URL(e.url);
    if (base.protocol !== "http:" && base.protocol !== "https:") throw new Error();
  } catch {
    return { ok: false, reason: "invalid", message: "Enter the engine's address, like http://127.0.0.1:8765." };
  }
  const headers = auth(e.token);
  const health = `${e.url}/api/health`;
  let r: Response;
  try {
    r = await fetch(health, { headers, cache: "no-store", signal: AbortSignal.timeout(6000) });
  } catch {
    return whyFailed(health, base);
  }
  if (r.status === 401) return { ok: false, reason: "token", message: WRONG_TOKEN };
  // an older engine has no /api/health: meta alone answers
  if (!r.ok && r.status !== 404 && r.status !== 405) return { ok: false, reason: "http", message: `The engine answered ${r.status}: ${await detail(r)}` };
  let m: Response;
  try {
    m = await fetch(`${e.url}/api/meta`, { headers, cache: "no-store", signal: AbortSignal.timeout(8000) });
  } catch {
    return whyFailed(`${e.url}/api/meta`, base);
  }
  if (m.status === 401) return { ok: false, reason: "token", message: WRONG_TOKEN };
  if (!m.ok) return { ok: false, reason: "http", message: `The engine answered ${m.status} on /api/meta: ${await detail(m)}` };
  let meta: Meta | null = null;
  try {
    meta = (await m.json()) as Meta;
  } catch {
    /* not JSON: not the engine */
  }
  if (!meta || typeof meta !== "object" || !meta.controls || typeof meta.controls !== "object") {
    return { ok: false, reason: "foreign", message: `Something answered at ${base.origin}, but it is not the cbj engine (no /api/meta controls).` };
  }
  return { ok: true, line: reachableLine(meta), meta };
}

export interface OwnHealth {
  online: boolean;
  busy?: boolean;
  backend?: string | null;
  models?: string[];
  effort?: string | null;
  url?: string;
  cors?: boolean;
}

/** The status poll for the user's own engine (open /api/health; an older engine's /api/meta). Never throws. */
export async function ownHealth(e: OwnEngine): Promise<OwnHealth> {
  const get = (path: string, token?: string) =>
    fetch(`${e.url}${path}`, { headers: auth(token), cache: "no-store", signal: AbortSignal.timeout(4000) }).catch(() => null);
  let r = await get("/api/health"); // open on the engine: no token, so no preflight every few seconds
  if (r && (r.status === 404 || r.status === 405)) r = await get("/api/meta", e.token);
  if (!r || !r.ok) return { online: false, url: e.url, cors: true };
  try {
    const j = (await r.json()) as { busy?: boolean; backend?: string; models?: string[]; effort?: string };
    return { online: true, busy: Boolean(j.busy), backend: j.backend ?? null, models: j.models ?? [], effort: j.effort ?? null, url: e.url, cors: true };
  } catch {
    return { online: false, url: e.url, cors: true };
  }
}

/** "127.0.0.1:8765" or "abc-def.trycloudflare.com": the engine's host for the header pill. */
export function engineHost(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}
