import type { ReactNode } from "react";

import { cn } from "./cn";

/** A station roundel: a numbered stop, or a day, in its line colour. */
export function Roundel({
  color,
  size = 28,
  ring = true,
  children,
  className,
}: {
  color: string;
  size?: number;
  /** A white ring, for roundels that sit on a line or on the map. */
  ring?: boolean;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-full font-display font-semibold text-white tabular-nums",
        ring && "ring-2 ring-white",
        className,
      )}
      style={{
        background: color,
        width: size,
        height: size,
        fontSize: Math.round(size * 0.52),
      }}
    >
      {children}
    </span>
  );
}
