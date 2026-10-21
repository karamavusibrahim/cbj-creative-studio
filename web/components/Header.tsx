"use client";

import { CircleHelp, KeyRound, Laptop, Lock, LockOpen } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { sentKeys, useOwnKeys } from "@/lib/keys";
import { engineHost, plannerLabel } from "@/lib/ownEngine";
import { useEngine } from "./EngineProvider";
import { FeedbackButton, useFeedbackState } from "./FeedbackDialog";
import HelpSheet from "./HelpSheet";
import LogoMark from "./Logo";
import StatusPill from "./StatusPill";
import { cx } from "./ui";

const NAV = [
  { href: "/", label: "Create" },
  { href: "/edit", label: "Edit" },
  { href: "/showcase", label: "Showcase" },
  { href: "/feedback", label: "Feedback" },
];

function Nav({ className }: { className?: string }) {
  const path = usePathname();
  const hidden = useFeedbackState() === "hidden"; // an engine without feedback: no owner's page
  return (
    <nav aria-label="Main" className={cx("flex items-center rounded-full bg-surface-container-low p-1", className)}>
      {NAV.filter((n) => !(hidden && n.href === "/feedback")).map((n) => {
        const on = n.href === "/" ? path === "/" : path.startsWith(n.href);
        return (
          <Link
            key={n.href}
            href={n.href}
            aria-current={on ? "page" : undefined}
            className={cx(
              "flex min-h-9 flex-1 items-center justify-center rounded-full px-3 py-1.5 sm:px-5 text-label-md transition-all duration-150",
              on ? "bg-primary-container font-semibold text-on-primary shadow-sm" : "text-on-surface-variant hover:text-on-surface",
            )}
          >
            {n.label}
          </Link>
        );
      })}
    </nav>
  );
}

/** The key icon (opens "Your engine and keys", always: it is also the way back from an own engine) and its pill: with an
 *  own engine "Your engine: 127.0.0.1:8765 · claude-cli/opus" (SPEC-OWN-ENGINE §2), with a Gemini key sent to the studio's
 *  engine "Your Gemini key" (SPEC-OWN-ENGINE-2 §3). At phone width the pill folds into the icon (its label and a dot). */
function KeysButton() {
  const { keysAvailable, openKeys, own, models, backend, meta } = useEngine();
  const sent = sentKeys(useOwnKeys().keys);
  const on = keysAvailable && sent.gemini;
  if (own) {
    const planner = meta ? plannerLabel(models, backend) : "";
    const words = `Your engine: ${engineHost(own.url)}${planner ? ` · ${planner}` : ""}`;
    return (
      <>
        <button
          type="button"
          onClick={openKeys}
          title="Running on your own Claude account"
          className="hidden min-h-8 min-w-0 max-w-[13rem] items-center gap-1.5 rounded-full bg-tertiary-fixed/35 px-3 py-1 text-body-sm font-semibold text-tertiary transition-colors hover:bg-tertiary-fixed/60 sm:inline-flex lg:max-w-[18rem] xl:max-w-[26rem]"
        >
          <Laptop aria-hidden className="size-3.5 shrink-0" />
          <span className="truncate">{words}</span>
        </button>
        <span title="Your engine and keys" className="inline-flex">
          <button
            type="button"
            aria-label={`Your engine and keys (running on your own engine: ${words.slice("Your engine: ".length)})`}
            onClick={openKeys}
            className="relative flex size-10 items-center justify-center rounded-lg text-tertiary transition-colors hover:bg-surface-container-high hover:text-on-surface"
          >
            <KeyRound aria-hidden className="size-[18px]" />
            <span aria-hidden className="absolute right-2 top-2 size-2 rounded-full bg-tertiary-fixed-dim ring-2 ring-surface-container-lowest sm:hidden" />
          </button>
        </span>
      </>
    );
  }
  return (
    <>
      {on ? (
        <button
          type="button"
          onClick={openKeys}
          title="Running on your own Gemini key"
          className="hidden min-h-8 items-center gap-1.5 rounded-full bg-tertiary-fixed/35 px-3 py-1 text-body-sm font-semibold text-tertiary transition-colors hover:bg-tertiary-fixed/60 sm:inline-flex"
        >
          <KeyRound aria-hidden className="size-3.5" />
          Your Gemini key
        </button>
      ) : null}
      <span title={on ? "Running on your own Gemini key" : "Your engine and keys"} className="inline-flex">
        <button
          type="button"
          aria-label={on ? "Your engine and keys (running on your own Gemini key)" : "Your engine and keys"}
          onClick={openKeys}
          className={cx(
            "relative flex size-10 items-center justify-center rounded-lg transition-colors hover:bg-surface-container-high hover:text-on-surface",
            on ? "text-tertiary" : "text-on-surface-variant",
          )}
        >
          <KeyRound aria-hidden className="size-[18px]" />
          {on ? <span aria-hidden className="absolute right-2 top-2 size-2 rounded-full bg-tertiary-fixed-dim ring-2 ring-surface-container-lowest sm:hidden" /> : null}
        </button>
      </span>
    </>
  );
}

export default function Header() {
  const [help, setHelp] = useState(false);
  const { required, unlocked, ensureUnlocked, lock } = useEngine();
  return (
    <header className="sticky top-0 z-40 border-b border-outline-variant/30 bg-surface-container-lowest shadow-[0_1px_8px_rgba(0,0,0,0.02)]">
      <div className="mx-auto flex h-16 max-w-[1560px] items-center justify-between gap-3 px-4 sm:px-6">
        <div className="flex min-w-0 items-center gap-6 lg:gap-8">
          <Link href="/" className="flex min-w-0 select-none items-center gap-3" aria-label="CBJ Studio, home">
            <LogoMark className="size-8 shrink-0" />
            <span className="flex min-w-0 flex-col">
              <span className="truncate font-headline text-[1.05rem] font-bold leading-tight tracking-tight text-on-surface sm:text-headline-md sm:font-bold">
                CBJ Studio
              </span>
              <span className="truncate text-[0.65rem] font-semibold uppercase leading-none tracking-wider text-outline sm:text-label-sm sm:font-semibold">
                Creative Studio
              </span>
            </span>
          </Link>
          <span aria-hidden className="hidden h-6 w-px bg-outline-variant/40 md:block" />
          <Nav className="hidden md:flex" />
        </div>
        <div className="flex shrink-0 items-center gap-0.5 sm:gap-3">
          <StatusPill />
          <FeedbackButton variant="icon" context={{ page: "general" }} />
          <KeysButton />
          <button
            type="button"
            onClick={() => setHelp(true)}
            className="flex min-h-10 items-center gap-1.5 rounded-lg px-2.5 text-label-md text-on-surface-variant transition-colors hover:bg-surface-container-high hover:text-on-surface sm:px-3"
          >
            <CircleHelp aria-hidden className="size-[18px]" />
            <span className="hidden sm:inline">Help</span>
            <span className="sr-only sm:hidden">Help</span>
          </button>
          {required ? (
            <button
              type="button"
              onClick={() => (unlocked ? void lock() : void ensureUnlocked())}
              title={unlocked ? "Unlocked: making and editing are on. Click to lock." : "Locked: enter the passcode to make or edit."}
              className="flex min-h-10 items-center gap-1.5 rounded-lg px-2.5 text-label-md text-on-surface-variant transition-colors hover:bg-surface-container-high hover:text-on-surface"
            >
              {unlocked ? <LockOpen aria-hidden className="size-[18px] text-tertiary" /> : <Lock aria-hidden className="size-[18px]" />}
              <span className="hidden xl:inline">{unlocked ? "Unlocked" : "Unlock"}</span>
              <span className="sr-only xl:hidden">{unlocked ? "Lock the studio" : "Unlock the studio"}</span>
            </button>
          ) : null}
        </div>
      </div>
      <div className="border-t border-outline-variant/20 px-4 py-2 md:hidden">
        <Nav />
      </div>
      {help ? <HelpSheet onClose={() => setHelp(false)} /> : null}
    </header>
  );
}
