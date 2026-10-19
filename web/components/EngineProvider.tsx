"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { engineGet, engineSource, showcaseSource, type EngineConn, type MediaSource } from "@/lib/engine";
import { getKeys, keysSupported, sentKeys, setKeysSupported, useOwnKeys, type OwnEngine } from "@/lib/keys";
import { ownHealth } from "@/lib/ownEngine";
import type { Meta } from "@/lib/types";
import KeysDialog from "./KeysDialog";
import UnlockDialog from "./UnlockDialog";

// One place for the engine's state (SPEC §2): where it is, whether it is up or busy, whether this
// session may start work, the meta (controls, uploads), and the media source the pages render with.
// With "My own engine" saved (SPEC-OWN-ENGINE §2) all of it is the user's own engine: polled directly, called directly
// with their token, its media, and no passcode (the gate protects the owner's engine only).

export type EngineStatus = "checking" | "online" | "offline";

interface Health {
  online: boolean;
  busy?: boolean;
  backend?: string | null;
  models?: string[];
  effort?: string | null;
  url?: string;
  cors?: boolean;
}

interface Session {
  unlocked: boolean;
  required: boolean;
  engine?: { url: string; token: string };
}

export interface EngineCtx {
  status: EngineStatus;
  busy: boolean; // the engine runs a job (ours or another page's)
  ours: boolean; // a job started from this tab runs
  otherBusy: boolean; // busy with a job that is not ours: "one at a time"
  models: string[];
  backend: string | null;
  conn: EngineConn;
  unlocked: boolean;
  required: boolean;
  meta: Meta | null;
  source: MediaSource; // engine when online, the static showcase otherwise
  setOurs: (on: boolean) => void;
  refreshMeta: () => Promise<void>;
  refreshHealth: () => Promise<void>;
  /** Resolves true when the session may start work (opens the passcode dialog when needed). */
  ensureUnlocked: () => Promise<boolean>;
  lock: () => Promise<void>;
  /** The studio's engine takes the user's own Gemini key (online, features.own_keys; never with an own engine on). */
  keysAvailable: boolean;
  /** The user's own engine, when "My own engine" is saved: every call goes there. */
  own: OwnEngine | null;
  openKeys: () => void;
}

const Ctx = createContext<EngineCtx | null>(null);

export function useEngine(): EngineCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error("useEngine outside EngineProvider");
  return c;
}

const never = () => () => {};

export default function EngineProvider({ children }: { children: ReactNode }) {
  // The stored engine is read from the browser's storage, which the hydration render cannot see: nothing is asked of
  // any engine until it can, or a page load with an own engine saved would first poll and read the studio's.
  const hydrated = useSyncExternalStore(never, () => true, () => false);
  const own = useOwnKeys().keys.engine ?? null;
  const ownUrl = own?.url ?? "";
  const ownToken = own?.token ?? "";
  const which = ownUrl ? `${ownUrl}\n${ownToken}` : ""; // the engine an answer belongs to ("": the studio's)
  // health and meta are kept per engine, so a late answer from the engine left behind never shows after a switch
  const [healthOf, setHealthOf] = useState<Record<string, Health>>({});
  const [session, setSession] = useState<Session>({ unlocked: false, required: false });
  const [sessionKnown, setSessionKnown] = useState(false);
  const [metaOf, setMetaOf] = useState<Record<string, Meta>>({});
  const health = healthOf[which] ?? null;
  const meta = metaOf[which] ?? null;
  const setHealth = (of: string, h: Health) => setHealthOf((all) => ({ ...all, [of]: h }));
  const setMeta = (of: string, m: Meta) => setMetaOf((all) => ({ ...all, [of]: m }));
  const [ours, setOurs] = useState(false);
  const [dialog, setDialog] = useState(false);
  const [keysDialog, setKeysDialog] = useState(false);
  const waiters = useRef<((ok: boolean) => void)[]>([]);

  const refreshHealth = useCallback(async () => {
    if (ownUrl) {
      const h = await ownHealth({ url: ownUrl, token: ownToken });
      setHealth(`${ownUrl}\n${ownToken}`, h);
      return;
    }
    try {
      const r = await fetch("/api/engine/health", { cache: "no-store" });
      setHealth("", (await r.json()) as Health);
    } catch {
      setHealth("", { online: false });
    }
  }, [ownUrl, ownToken]);

  const refreshSession = useCallback(async () => {
    try {
      const r = await fetch("/api/session", { cache: "no-store" });
      setSession((await r.json()) as Session);
    } catch {
      setSession({ unlocked: false, required: true });
    }
    setSessionKnown(true);
  }, []);

  useEffect(() => {
    // first reads on mount; the state updates land after the awaits
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refreshSession();
  }, [refreshSession]);

  useEffect(() => {
    // on mount and whenever the engine changes (own engine saved or cleared)
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (hydrated) void refreshHealth();
  }, [hydrated, refreshHealth]);

  const busy = Boolean(health?.online && health.busy);
  // poll every 10 s; every 3 s while a job runs (for "busy")
  useEffect(() => {
    if (!hydrated) return;
    const ms = busy || ours ? 3000 : 10000;
    const t = setInterval(() => void refreshHealth(), ms);
    return () => clearInterval(t);
  }, [hydrated, busy, ours, refreshHealth]);

  const status: EngineStatus = health === null || (!ownUrl && !sessionKnown) ? "checking" : health.online ? "online" : "offline";
  const url = ownUrl || health?.url || session.engine?.url || "";
  // the passcode protects the owner's engine only: with an own engine, making and editing need no Unlock
  const unlocked = Boolean(ownUrl) || session.unlocked;

  const conn = useMemo<EngineConn>(
    () =>
      ownUrl
        ? { url: ownUrl, token: ownToken, direct: true, own: true }
        : {
            url,
            token: session.unlocked ? session.engine?.token || "" : "",
            direct: Boolean(health?.cors && session.unlocked),
          },
    [ownUrl, ownToken, url, session.unlocked, session.engine?.token, health?.cors],
  );

  const refreshMeta = useCallback(async () => {
    if (conn.own) {
      try {
        setKeysSupported(false); // no key headers to an own engine; the studio's meta finds out again after a switch
        setMeta(`${conn.url}\n${conn.token}`, await engineGet<Meta>(conn, "/api/meta"));
      } catch {
        /* the pill already says offline */
      }
      return;
    }
    try {
      // the keys ride on this call only once the engine says it takes them (an older one refuses them in the
      // preflight): when it first says so, ask again with it, so meta answers as this user's requests run
      let m = await engineGet<Meta>(conn, "/api/meta");
      const takes = Boolean(m.features?.own_keys);
      const first = takes && !keysSupported();
      setKeysSupported(takes);
      const k = sentKeys(getKeys().keys);
      if (first && k.gemini) m = await engineGet<Meta>(conn, "/api/meta");
      setMeta("", m);
    } catch {
      /* the pill already says offline */
    }
  }, [conn]);

  useEffect(() => {
    // meta (controls, uploads) once the engine is known to be up
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (status === "online") void refreshMeta();
  }, [status, refreshMeta]);

  const source = useMemo(() => (status === "online" && url ? engineSource(conn) : showcaseSource()), [status, url, conn]);

  const ensureUnlocked = useCallback(async () => {
    if (unlocked) return true;
    setDialog(true);
    return new Promise<boolean>((resolve) => waiters.current.push(resolve));
  }, [unlocked]);

  const closeDialog = useCallback(
    async (ok: boolean) => {
      if (ok) await refreshSession();
      setDialog(false);
      const w = waiters.current;
      waiters.current = [];
      w.forEach((f) => f(ok));
    },
    [refreshSession],
  );

  useEffect(() => {
    // "My own engine" saved from over the Unlock dialog: no passcode is needed any more. The waiting action is not run
    // (it holds the studio's connection); the user starts it again, on their own engine.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (ownUrl && dialog) void closeDialog(false);
  }, [ownUrl, dialog, closeDialog]);

  const lock = useCallback(async () => {
    await fetch("/api/session", { method: "DELETE" }).catch(() => null);
    await refreshSession();
  }, [refreshSession]);

  const value: EngineCtx = {
    status,
    busy,
    ours,
    otherBusy: busy && !ours,
    // the planner words as this user's requests run (meta answers with their key); health is the studio's
    models: meta?.models ?? health?.models ?? [],
    backend: meta?.backend ?? health?.backend ?? null,
    conn,
    unlocked,
    required: !ownUrl && session.required,
    meta,
    source,
    setOurs,
    refreshMeta,
    refreshHealth,
    ensureUnlocked,
    lock,
    keysAvailable: !ownUrl && status === "online" && Boolean(meta?.features?.own_keys),
    own,
    openKeys: () => setKeysDialog(true),
  };

  return (
    <Ctx.Provider value={value}>
      {children}
      {dialog ? <UnlockDialog onClose={closeDialog} /> : null}
      {keysDialog ? <KeysDialog onClose={() => setKeysDialog(false)} /> : null}
    </Ctx.Provider>
  );
}

/** "claude-cli/opus" → "Claude opus"; the Anthropic API names itself: "anthropic/claude-opus-5-5" */
export function plannerName(models: string[], backend: string | null): string {
  const m = models[0];
  if (!m) return "";
  if (backend === "anthropic" || m.startsWith("anthropic/")) return m;
  const name = m.split("/").pop() || m;
  const fam = backend === "claude" || m.startsWith("claude") ? "Claude " : backend === "gemini" || m.includes("gemini") ? "" : "";
  return `${fam}${name}`;
}
