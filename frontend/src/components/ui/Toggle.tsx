import type { InputHTMLAttributes, ReactNode } from "react";

import { cn } from "./cn";
import { Icon } from "./Icon";

type InputProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "className">;

/** A square check box drawn in ink; label it with `children` or `aria-label`. */
export function Checkbox({
  children,
  className,
  ...props
}: InputProps & { children?: ReactNode; className?: string }) {
  return (
    <label
      className={cn(
        "inline-flex cursor-pointer items-center gap-2.5 text-sm text-ink has-disabled:cursor-not-allowed has-disabled:opacity-55",
        className,
      )}
    >
      <span className="relative inline-flex size-[18px] shrink-0">
        <input
          type="checkbox"
          {...props}
          className="peer size-[18px] cursor-[inherit] appearance-none rounded-[5px] border border-field bg-surface transition-colors checked:border-ink checked:bg-ink enabled:hover:border-ink-3"
        />
        <Icon
          name="check"
          size={14}
          strokeWidth={2.6}
          className="pointer-events-none absolute inset-0 m-auto text-white opacity-0 transition-opacity peer-checked:opacity-100"
        />
      </span>
      {children}
    </label>
  );
}

/** An on/off switch: a check box with `role="switch"`, for settings that apply at once. */
export function Switch({
  children,
  className,
  ...props
}: InputProps & { children: ReactNode; className?: string }) {
  return (
    <label
      className={cn(
        "flex cursor-pointer items-center justify-between gap-4 text-sm text-ink has-disabled:cursor-not-allowed has-disabled:opacity-55",
        className,
      )}
    >
      <span className="min-w-0">{children}</span>
      <span className="relative inline-flex h-6 w-10 shrink-0">
        <input
          type="checkbox"
          role="switch"
          {...props}
          className="peer h-6 w-10 cursor-[inherit] appearance-none rounded-full bg-line-strong transition-colors duration-200 checked:bg-ink"
        />
        <span
          aria-hidden
          className="pointer-events-none absolute top-[3px] left-[3px] size-[18px] rounded-full bg-white shadow-[0_1px_2px_rgb(20_32_43/0.3)] transition-transform duration-200 ease-[var(--ease-out-expo)] peer-checked:translate-x-4"
        />
      </span>
    </label>
  );
}

/** A pill that is pressed or not: a check box under the hood, for picking options. */
export function ToggleChip({
  children,
  className,
  ...props
}: InputProps & { children: ReactNode; className?: string }) {
  return (
    <label
      className={cn(
        "relative inline-flex h-9 cursor-pointer items-center gap-1.5 rounded-full border border-line-strong bg-surface px-3.5 text-sm font-semibold text-ink transition-colors select-none hover:border-ink-3 has-checked:border-ink has-checked:bg-ink has-checked:text-white has-disabled:cursor-not-allowed has-disabled:opacity-55 has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-ink",
        className,
      )}
    >
      <input type="checkbox" {...props} className="peer sr-only" />
      <Icon name="check" size={15} className="hidden peer-checked:block" />
      {children}
    </label>
  );
}

/** A pill button for one of a few exclusive options (`aria-pressed`). */
export function OptionChip({
  pressed,
  onClick,
  children,
  className,
}: {
  pressed: boolean;
  onClick: () => void;
  children: ReactNode;
  className?: string;
}) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      className={cn(
        "inline-flex h-9 items-center rounded-full border px-3.5 text-sm font-semibold transition-colors",
        pressed
          ? "border-ink bg-ink text-white"
          : "border-line-strong bg-surface text-ink hover:border-ink-3",
        className,
      )}
    >
      {children}
    </button>
  );
}
