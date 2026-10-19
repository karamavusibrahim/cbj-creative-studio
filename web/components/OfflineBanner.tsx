"use client";

import { CloudOff, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useEngine } from "./EngineProvider";

// Shown on Create and Edit when the engine is offline (SPEC §6). Dismissible for this visit.

export default function OfflineBanner() {
  const { status, own } = useEngine();
  const [hidden, setHidden] = useState(false);
  if (status !== "offline" || hidden) return null;
  return (
    <div role="status" className="mb-6 flex items-start gap-3 rounded-2xl bg-surface-container-high p-4 text-body-md text-on-surface">
      <CloudOff aria-hidden className="mt-0.5 size-5 shrink-0 text-outline" />
      <p className="flex-1">
        {own ? (
          <>
            Your engine is offline right now: check that <code className="font-mono text-code-sm">uv run cbj ui</code> is still running on your Mac (or switch back
            in Your engine and keys).{" "}
          </>
        ) : (
          "The studio engine is offline right now. "
        )}
        You can browse finished creatives in the{" "}
        <Link href="/showcase" className="font-semibold text-primary underline-offset-2 hover:underline">
          Showcase
        </Link>
        .
      </p>
      <button
        type="button"
        onClick={() => setHidden(true)}
        aria-label="Dismiss"
        className="-m-1.5 flex size-9 shrink-0 items-center justify-center rounded-lg text-outline hover:bg-surface-container hover:text-on-surface"
      >
        <X aria-hidden className="size-4" />
      </button>
    </div>
  );
}
