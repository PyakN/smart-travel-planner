import type { ReactNode } from "react";

import type { IconName } from "@/lib/icons";

import { cn } from "./cn";
import { Icon } from "./Icon";
import type { Tone } from "./Tag";

const TONES: Record<Tone, { box: string; icon: string; glyph: IconName }> = {
  neutral: { box: "bg-canvas", icon: "text-ink-2", glyph: "sparkle" },
  signal: { box: "bg-signal-soft", icon: "text-signal-ink", glyph: "sparkle" },
  go: { box: "bg-go-soft", icon: "text-go", glyph: "check" },
  stop: { box: "bg-stop-soft", icon: "text-stop", glyph: "warning" },
  caution: { box: "bg-caution-soft", icon: "text-caution", glyph: "warning" },
  info: { box: "bg-info-soft", icon: "text-info", glyph: "cloud" },
  evening: { box: "bg-evening-soft", icon: "text-evening", glyph: "moon" },
};

/** A note on a tinted ground: what changed, what to watch for, what failed. */
export function Notice({
  tone = "neutral",
  icon,
  title,
  action,
  role,
  children,
  className,
}: {
  tone?: Tone;
  icon?: IconName;
  title?: ReactNode;
  /** A button or link at the end of the first line (Undo). */
  action?: ReactNode;
  role?: "alert" | "status";
  children?: ReactNode;
  className?: string;
}) {
  const style = TONES[tone];
  return (
    <div
      role={role}
      className={cn(
        "flex gap-2.5 rounded-panel px-3 py-2.5 text-small text-ink",
        style.box,
        className,
      )}
    >
      <Icon name={icon ?? style.glyph} size={17} className={cn("mt-px", style.icon)} />
      <div className="min-w-0 flex-1 space-y-1">
        {(title || action) && (
          <div className="flex items-start justify-between gap-3">
            {title && <p className="font-bold">{title}</p>}
            {action}
          </div>
        )}
        {children}
      </div>
    </div>
  );
}
