"use client";

import { useCallback, useRef, useState } from "react";
import { EngineError, engineGet, pollJob, startJob } from "@/lib/engine";
import { useEngine } from "./EngineProvider";
import type { LogLine } from "./Progress";

// Running one engine job from a page: start it, poll it every 700 ms, keep the log and the stage, and
// remember it in localStorage so a reload picks it up again (the engine page's poll / resumeJob).

const KEY = "cbjStudioJob";

export interface StoredJob {
  id: string;
  kind: string; // plan | make | preview | review | direct
  page: "create" | "edit";
  context?: Record<string, unknown>;
}

export interface JobState {
  running: boolean;
  kind: string;
  stage: string;
  lines: LogLine[];
  elapsed?: number;
  error?: string;
  trace?: string;
  done: boolean;
}

const IDLE: JobState = { running: false, kind: "", stage: "", lines: [], done: false };

export function storedJob(): StoredJob | null {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as StoredJob) : null;
  } catch {
    return null;
  }
}

function store(j: StoredJob | null) {
  try {
    if (j) localStorage.setItem(KEY, JSON.stringify(j));
    else localStorage.removeItem(KEY);
  } catch {
    /* private mode */
  }
}

export default function useJob(page: "create" | "edit") {
  const engine = useEngine();
  const [job, setJob] = useState<JobState>(IDLE);
  const abort = useRef<AbortController | null>(null);

  const follow = useCallback(
    async <R,>(id: string, kind: string, context?: Record<string, unknown>, keepLog = false): Promise<R> => {
      abort.current?.abort();
      const ctl = new AbortController();
      abort.current = ctl;
      store({ id, kind, page, context });
      engine.setOurs(true);
      setJob((s) => ({ running: true, kind, stage: kind === "plan" ? "plan" : s.stage, lines: keepLog ? s.lines : [], done: false }));
      try {
        const r = await pollJob<R>(
          engine.conn,
          id,
          ({ job: j, newLines }) =>
            setJob((s) => ({
              ...s,
              stage: j.stage || s.stage,
              lines: newLines.length ? [...s.lines, ...newLines] : s.lines,
              elapsed: j.elapsed,
            })),
          ctl.signal,
        );
        setJob((s) => ({ ...s, running: false, done: kind !== "plan", stage: kind === "plan" ? "plan" : "done" }));
        return r;
      } catch (e) {
        if ((e as Error).name !== "AbortError") {
          setJob((s) => ({ ...s, running: false, error: (e as Error).message, trace: e instanceof EngineError ? e.trace : undefined }));
        }
        throw e;
      } finally {
        store(null);
        engine.setOurs(false);
        void engine.refreshHealth();
      }
    },
    [engine, page],
  );

  /** Start a job (POST path) and follow it to its result. */
  const run = useCallback(
    async <R,>(path: string, body: unknown, kind: string, context?: Record<string, unknown>, keepLog = false): Promise<R> => {
      setJob((s) => ({ ...s, running: true, kind, error: undefined, trace: undefined, done: false, lines: keepLog ? s.lines : [] }));
      let id: string;
      try {
        id = await startJob(engine.conn, path, body);
      } catch (e) {
        setJob((s) => ({ ...s, running: false, error: (e as Error).message }));
        throw e;
      }
      return follow<R>(id, kind, context, keepLog);
    },
    [engine.conn, follow],
  );

  /** After a reload: if this page's job still runs on the engine, follow it again. */
  const resume = useCallback(async (): Promise<{ stored: StoredJob; result: unknown } | null> => {
    const s = storedJob();
    if (!s || s.page !== page) return null;
    let jobs: { id: string; status: string }[] = [];
    try {
      jobs = await engineGet<{ id: string; status: string }[]>(engine.conn, "/api/jobs");
    } catch {
      return null;
    }
    const j = jobs.find((x) => x.id === s.id);
    if (!j) {
      store(null);
      return null;
    }
    try {
      const result = await follow(s.id, s.kind, s.context);
      return { stored: s, result };
    } catch {
      return null;
    }
  }, [engine.conn, follow, page]);

  const fail = useCallback((message: string) => setJob((s) => ({ ...s, running: false, error: message })), []);
  const reset = useCallback(() => setJob(IDLE), []);

  return { job, run, resume, fail, reset };
}
