"use client";

import type { LucideIcon } from "lucide-react";
import { ChevronDown } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import type { ButtonHTMLAttributes, ReactNode } from "react";

export function cx(...c: (string | false | null | undefined)[]) {
  return c.filter(Boolean).join(" ");
}

/** A white card on the pale ground (Stitch: rounded-2xl p-6 shadow-sm). Enters with a short rise. */
export function Card({
  children,
  className,
  as = "section",
  id,
  label,
}: {
  children: ReactNode;
  className?: string;
  as?: "section" | "div";
  id?: string;
  label?: string;
}) {
  const reduce = useReducedMotion();
  const Comp = as === "section" ? motion.section : motion.div;
  return (
    <Comp
      id={id}
      aria-label={label}
      initial={reduce ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
      className={cx("@container rounded-2xl bg-surface-container-lowest p-5 shadow-sm sm:p-6", className)}
    >
      {children}
    </Comp>
  );
}

export function CardTitle({
  icon: Icon,
  tone = "primary",
  children,
  right,
  as: As = "h2",
}: {
  icon?: LucideIcon;
  tone?: "primary" | "secondary" | "tertiary" | "outline";
  children: ReactNode;
  right?: ReactNode;
  as?: "h2" | "h3";
}) {
  const color = { primary: "text-primary-container", secondary: "text-secondary", tertiary: "text-tertiary", outline: "text-outline" }[tone];
  return (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
      <As className="flex items-center gap-2 text-title-sm text-on-surface">
        {Icon ? <Icon aria-hidden className={cx("size-5", color)} strokeWidth={2} /> : null}
        {children}
      </As>
      {right}
    </div>
  );
}

export type Tone = "mint" | "amber" | "error" | "grey" | "sky" | "violet";

const TONES: Record<Tone, string> = {
  mint: "bg-tertiary-fixed/35 text-tertiary",
  amber: "bg-amber-container text-amber",
  error: "bg-error-container text-on-error-container",
  grey: "bg-surface-container text-on-surface-variant",
  sky: "bg-secondary-fixed/70 text-on-secondary-fixed",
  violet: "bg-primary-fixed text-on-primary-fixed",
};

export function Badge({ tone = "grey", children, title, className }: { tone?: Tone; children: ReactNode; title?: string; className?: string }) {
  return (
    <span
      title={title}
      className={cx(
        "inline-flex max-w-full items-center gap-1 whitespace-nowrap rounded-full px-2.5 py-0.5 text-label-sm font-semibold",
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

/** A soft chip with an icon (facts under the player, Stitch "9:16 Vertical"). */
export function Fact({ icon: Icon, children, tone = "primary" }: { icon?: LucideIcon; children: ReactNode; tone?: "primary" | "secondary" | "tertiary" | "error" }) {
  const color = { primary: "text-primary", secondary: "text-secondary", tertiary: "text-tertiary", error: "text-error" }[tone];
  return (
    <span className="inline-flex max-w-full items-center gap-1.5 rounded-full bg-surface-container px-3 py-1 text-label-sm text-on-surface">
      {Icon ? <Icon aria-hidden className={cx("size-3.5 shrink-0", color)} /> : null}
      <span className="truncate">{children}</span>
    </span>
  );
}

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" | "quiet"; icon?: LucideIcon; size?: "md" | "lg" | "sm" };

export function Button({ variant = "secondary", icon: Icon, size = "md", className, children, ...rest }: BtnProps) {
  const v = {
    primary: "bg-primary-container text-on-primary shadow-sm hover:bg-primary active:scale-[0.98]",
    secondary: "bg-surface-container-high text-on-surface hover:bg-surface-variant",
    ghost: "bg-surface-container-lowest text-on-surface-variant shadow-sm ring-1 ring-outline-variant/40 hover:text-on-surface hover:bg-surface-container-low",
    quiet: "text-on-surface-variant hover:text-on-surface hover:bg-surface-container",
  }[variant];
  const s = { sm: "min-h-9 px-3 py-1.5 text-label-sm", md: "min-h-10 px-4 py-2 text-label-md", lg: "min-h-12 px-7 py-3 text-label-md" }[size];
  return (
    <button
      type="button"
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-xl font-semibold transition-all disabled:cursor-not-allowed disabled:opacity-45 disabled:active:scale-100",
        v,
        s,
        className,
      )}
      {...rest}
    >
      {Icon ? <Icon aria-hidden className={size === "sm" ? "size-4" : "size-[18px]"} /> : null}
      {children}
    </button>
  );
}

/** A segmented choice (Stitch: grid of buttons in a surface-container-low track). Clicking the chosen one clears it. */
export function Segmented<T extends string>({
  label,
  options,
  value,
  onChange,
  columns,
}: {
  label: string;
  options: readonly { id: T; text: string; icon?: LucideIcon }[];
  value: T | undefined;
  onChange: (v: T | undefined) => void;
  columns?: number;
}) {
  return (
    <fieldset className="flex min-w-0 flex-col gap-2">
      <legend className="mb-2 text-label-md text-on-surface">{label}</legend>
      <div
        className="grid gap-1.5 rounded-xl bg-surface-container-low p-1"
        style={{ gridTemplateColumns: `repeat(${columns ?? options.length}, minmax(0, 1fr))` }}
      >
        {options.map((o) => {
          const on = o.id === value;
          const Icon = o.icon;
          return (
            <button
              key={o.id}
              type="button"
              aria-pressed={on}
              onClick={() => onChange(on ? undefined : o.id)}
              className={cx(
                "flex min-h-10 items-center justify-center gap-1.5 rounded-lg px-2 py-2 text-center text-label-md transition-all",
                on ? "bg-primary-container font-semibold text-on-primary shadow-sm" : "text-on-surface-variant hover:bg-surface-container hover:text-on-surface",
              )}
            >
              {Icon ? <Icon aria-hidden className="size-4 shrink-0" /> : null}
              {o.text}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}

/** Raw data, links, traces: under a fold. */
export function Fold({ summary, children, className }: { summary: ReactNode; children: ReactNode; className?: string }) {
  return (
    <details className={cx("group mt-3 text-body-sm", className)}>
      <summary className="inline-flex min-h-8 items-center gap-1 rounded-lg text-label-sm font-semibold text-on-surface-variant hover:text-on-surface">
        <ChevronDown aria-hidden className="size-4 transition-transform group-open:rotate-180" />
        {summary}
      </summary>
      <div className="mt-2">{children}</div>
    </details>
  );
}

export function Pre({ children }: { children: ReactNode }) {
  return (
    <pre className="max-h-80 overflow-auto rounded-xl bg-surface-container-low p-3 font-mono text-[11px] leading-4 text-on-surface-variant">
      {children}
    </pre>
  );
}

export function Muted({ children, className }: { children: ReactNode; className?: string }) {
  return <p className={cx("text-body-sm text-on-surface-variant", className)}>{children}</p>;
}

export function Eyebrow({ children }: { children: ReactNode }) {
  return <span className="text-label-sm font-semibold uppercase tracking-wider text-outline">{children}</span>;
}

export function ErrorBox({ message, trace }: { message: string; trace?: string }) {
  return (
    <div role="alert" className="mt-3 rounded-xl bg-error-container/60 p-3 text-body-md text-on-error-container">
      <p className="whitespace-pre-wrap font-semibold">{message}</p>
      {trace ? (
        <Fold summary="Technical trace">
          <Pre>{trace}</Pre>
        </Fold>
      ) : null}
    </div>
  );
}
