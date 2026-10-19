"use client";

import { createContext, useContext, type ReactNode } from "react";
import { showcaseSource, type MediaSource } from "@/lib/engine";
import { useEngine } from "./EngineProvider";

// Which store a component reads studio paths from: the live engine, or the static showcase.
// Live pages use the engine's source (the showcase's when offline); showcase pages pin the showcase.

const Ctx = createContext<MediaSource | null>(null);

export function ShowcaseSource({ children }: { children: ReactNode }) {
  return <Ctx.Provider value={showcaseSource()}>{children}</Ctx.Provider>;
}

export function PinnedSource({ source, children }: { source: MediaSource; children: ReactNode }) {
  return <Ctx.Provider value={source}>{children}</Ctx.Provider>;
}

export function useSource(): MediaSource {
  const pinned = useContext(Ctx);
  const { source } = useEngine();
  return pinned || source;
}
