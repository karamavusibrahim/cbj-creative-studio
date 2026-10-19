// "Your Gemini key" (SPEC-OWN-KEYS §2, SPEC-OWN-ENGINE-2): the user's own Gemini key, kept in this browser and sent only
// to the studio's engine, as one header on the calls that start work and on GET /api/meta (engine: src/cbj/keys.py).
// Never logged, never in a URL. `cbj.keys` lives in sessionStorage ("this tab") or, with "Remember on this device", in
// localStorage. No Anthropic key is ever asked for or sent: a user's own Claude account runs through their own Claude
// Code login, on their own engine (below).
//
// "My own engine" (SPEC-OWN-ENGINE §1): the same record may hold `engine` ({url, token}), the user's own engine (their
// Mac, their Claude CLI login and Gemini key). While it is set, every engine call goes there directly (lib/engine.ts,
// EngineProvider), the passcode is not needed, and the key headers are never sent: that engine has its own keys.

import { useSyncExternalStore } from "react";

export interface OwnKeys {
  gemini?: string;
  engine?: OwnEngine; // set: "My own engine" is on
}

export interface OwnEngine {
  url: string; // no trailing slash
  token?: string; // the engine's CBJ_API_TOKEN, if the user set one
}

export interface KeysState {
  keys: OwnKeys;
  remember: boolean; // true: localStorage (this device); false: sessionStorage (this tab)
}

export const STORAGE_KEY = "cbj.keys";
export const GEMINI_HEADER = "X-CBJ-Gemini-Key";

const EMPTY: KeysState = { keys: {}, remember: false };

function store(kind: "local" | "session"): Storage | null {
  try {
    return kind === "local" ? window.localStorage : window.sessionStorage;
  } catch {
    return null; // private mode, blocked storage, or the server
  }
}

function parse(raw: string | null | undefined): OwnKeys | null {
  if (!raw) return null;
  try {
    const j = JSON.parse(raw) as Record<string, unknown>;
    const s = (v: unknown) => (typeof v === "string" && v.trim() ? v.trim() : undefined);
    const e = j.engine as Record<string, unknown> | undefined;
    const engine = e && typeof e === "object" && s(e.url) ? { url: s(e.url)!, token: s(e.token) } : undefined;
    return clean({ gemini: s(j.gemini), engine }); // anything else an older version stored is dropped
  } catch {
    return null;
  }
}

/** Trimmed, empty fields dropped. */
export function clean(k: OwnKeys): OwnKeys {
  const out: OwnKeys = {};
  if (k.gemini?.trim()) out.gemini = k.gemini.trim();
  const url = k.engine ? engineUrl(k.engine.url) : "";
  if (url) out.engine = k.engine?.token?.trim() ? { url, token: k.engine.token.trim() } : { url };
  return out;
}

/** "127.0.0.1:8765/" → "http://127.0.0.1:8765"; "" when it is not an http(s) address. */
export function engineUrl(raw: string): string {
  let t = raw.trim();
  if (!t) return "";
  if (!/^[a-z][a-z0-9+.-]*:\/\//i.test(t)) t = `${/^(localhost|127\.|\[::1\])/i.test(t) ? "http" : "https"}://${t}`;
  try {
    const u = new URL(t);
    if (u.protocol !== "http:" && u.protocol !== "https:") return "";
    return `${u.origin}${u.pathname.replace(/\/+$/, "")}`;
  } catch {
    return "";
  }
}

const isEmpty = (k: OwnKeys) => !k.gemini && !k.engine;

let snapshot: KeysState | null = null;
const listeners = new Set<() => void>();

function read(): KeysState {
  if (snapshot) return snapshot;
  const local = parse(store("local")?.getItem(STORAGE_KEY));
  if (local) return (snapshot = { keys: local, remember: true });
  const session = parse(store("session")?.getItem(STORAGE_KEY));
  return (snapshot = session ? { keys: session, remember: false } : EMPTY);
}

function changed() {
  snapshot = null;
  listeners.forEach((f) => f());
}

export function getKeys(): KeysState {
  return typeof window === "undefined" ? EMPTY : read();
}

/** Save to the chosen store and remove from the other. Nothing worth keeping: clears both. */
export function saveKeys(keys: OwnKeys, remember: boolean): void {
  const k = clean(keys);
  if (isEmpty(k)) return clearKeys();
  const [to, from] = remember ? [store("local"), store("session")] : [store("session"), store("local")];
  try {
    to?.setItem(STORAGE_KEY, JSON.stringify(k));
  } catch {
    /* storage full or blocked: the keys stay unsaved */
  }
  try {
    from?.removeItem(STORAGE_KEY);
  } catch {
    /* blocked */
  }
  changed();
}

export function clearKeys(): void {
  for (const s of [store("local"), store("session")]) {
    try {
      s?.removeItem(STORAGE_KEY);
    } catch {
      /* blocked */
    }
  }
  changed();
}

// Only an engine that says features.own_keys gets the headers: an older one would refuse them in the CORS preflight.
let supported = false;
export function setKeysSupported(on: boolean): void {
  supported = on;
}
export const keysSupported = () => supported;

/** Does a request carry the Gemini key (the pill's words)? Never while the user's own engine is on (it has its own). */
export function sentKeys(k: OwnKeys): { gemini: boolean } {
  return { gemini: Boolean(k.gemini && !k.engine) };
}

/** The user's own engine, when "My own engine" is saved. */
export function ownEngine(): OwnEngine | null {
  return getKeys().keys.engine ?? null;
}

/** The header for a POST or GET /api/meta: the Gemini key only ({} when none is set or the engine does not take it). */
export function keyHeaders(): Record<string, string> {
  if (!supported || typeof window === "undefined") return {};
  const { keys: k } = read();
  return sentKeys(k).gemini ? { [GEMINI_HEADER]: k.gemini! } : {};
}

function subscribe(f: () => void): () => void {
  listeners.add(f);
  const onStorage = (e: StorageEvent) => {
    if (e.key === null || e.key === STORAGE_KEY) changed(); // another tab saved or cleared (localStorage only)
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(f);
    window.removeEventListener("storage", onStorage);
  };
}

/** The stored keys, re-rendering when they change. */
export function useOwnKeys(): KeysState {
  return useSyncExternalStore(subscribe, getKeys, () => EMPTY);
}
