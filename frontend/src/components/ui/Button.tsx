import type { ButtonHTMLAttributes } from "react";

import type { IconName } from "@/lib/icons";

import { cn } from "./cn";
import { Icon } from "./Icon";

export type ButtonVariant = "primary" | "dark" | "secondary" | "quiet" | "danger";
export type ButtonSize = "sm" | "md" | "lg";

const BASE =
  "inline-flex select-none items-center justify-center whitespace-nowrap rounded-control transition-[background-color,border-color,color,transform] duration-150 ease-out enabled:active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-45";

const VARIANTS: Record<ButtonVariant, string> = {
  primary:
    "bg-signal font-bold text-ink enabled:hover:bg-signal-hover disabled:bg-line disabled:text-ink-3 disabled:opacity-100 aria-busy:disabled:bg-signal aria-busy:disabled:text-ink",
  dark: "bg-ink font-semibold text-white enabled:hover:bg-ink/88",
  secondary:
    "border border-line-strong bg-surface font-semibold text-ink enabled:hover:border-ink-3 enabled:hover:bg-canvas",
  quiet: "font-semibold text-ink-2 enabled:hover:bg-canvas enabled:hover:text-ink",
  danger: "bg-stop font-bold text-white enabled:hover:bg-stop/90",
};

const SIZES: Record<ButtonSize, string> = {
  sm: "h-9 gap-1.5 px-3 text-small",
  md: "h-10 gap-2 px-3.5 text-sm",
  lg: "h-11 gap-2 px-4 text-body",
};

const ICON_SIZES: Record<ButtonSize, number> = { sm: 16, md: 17, lg: 18 };

/** Button classes, for links that look like buttons. */
export function buttonClass({
  variant = "secondary",
  size = "md",
  block = false,
}: { variant?: ButtonVariant; size?: ButtonSize; block?: boolean } = {}): string {
  return cn(BASE, VARIANTS[variant], SIZES[size], block && "w-full");
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Fill the width of the container. */
  block?: boolean;
  icon?: IconName;
}

export function Button({
  variant = "secondary",
  size = "md",
  block = false,
  icon,
  className,
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      type="button"
      {...props}
      className={cn(buttonClass({ variant, size, block }), className)}
    >
      {icon && <Icon name={icon} size={ICON_SIZES[size]} />}
      {children}
    </button>
  );
}
