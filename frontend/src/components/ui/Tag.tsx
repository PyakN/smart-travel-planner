import type { ReactNode } from "react";

import type { IconName } from "@/lib/icons";

import { cn } from "./cn";
import { Icon } from "./Icon";

export type Tone = "neutral" | "signal" | "go" | "stop" | "caution" | "info" | "evening";

export const TONE_SOFT: Record<Tone, string> = {
  neutral: "bg-canvas text-ink-2",
  signal: "bg-signal-soft text-signal-ink",
  go: "bg-go-soft text-go",
  stop: "bg-stop-soft text-stop",
  caution: "bg-caution-soft text-caution",
  info: "bg-info-soft text-info",
  evening: "bg-evening-soft text-evening",
};

/** A small sign plate: a fact about a place (must-visit, outdoors, new). */
export function Tag({
  tone = "neutral",
  icon,
  children,
  className,
}: {
  tone?: Tone;
  icon?: IconName;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex h-6 items-center gap-1 rounded-tag px-1.5 text-meta font-bold whitespace-nowrap",
        TONE_SOFT[tone],
        className,
      )}
    >
      {icon && <Icon name={icon} size={13} />}
      {children}
    </span>
  );
}
