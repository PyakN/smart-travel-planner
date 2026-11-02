import type { ReactNode } from "react";

import { cn } from "./cn";

/** Text inputs: 16px on phones so the browser never zooms in. */
export const INPUT =
  "h-11 w-full rounded-control border border-field bg-surface px-3 text-base text-ink transition-colors placeholder:text-ink-3 enabled:hover:border-ink-3 focus-visible:border-ink disabled:cursor-not-allowed disabled:bg-canvas disabled:text-ink-3 lg:text-body";

const COMPACT =
  "h-10 rounded-control border border-field bg-surface text-base text-ink tabular-nums transition-colors enabled:hover:border-ink-3 focus-visible:border-ink disabled:cursor-not-allowed disabled:bg-canvas disabled:text-ink-3 lg:text-sm";

/** Compact inputs for times, dates and selects that sit inside a row. */
export const INPUT_COMPACT = cn(COMPACT, "px-2.5");

/** A native select with the app's chevron: long options stop short of it. */
export const SELECT = cn(COMPACT, "select pr-9 pl-2.5");

export function Label({
  htmlFor,
  children,
  optional = false,
  className,
}: {
  htmlFor?: string;
  children: ReactNode;
  /** Adds a quiet "optional". */
  optional?: boolean;
  className?: string;
}) {
  return (
    <label htmlFor={htmlFor} className={cn("block text-sm font-bold text-ink", className)}>
      {children}
      {optional && <span className="ml-1.5 font-normal text-ink-3">optional</span>}
    </label>
  );
}

/** Help text under a field or a group. */
export function Hint({ children, className }: { children: ReactNode; className?: string }) {
  return <p className={cn("text-small text-ink-2", className)}>{children}</p>;
}

/** An inline error that names the problem and how to fix it. */
export function FieldError({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <p role="alert" className={cn("text-small font-bold text-stop", className)}>
      {children}
    </p>
  );
}
