import { type IconName, iconMarkup } from "@/lib/icons";

import { cn } from "./cn";

export interface IconProps {
  name: IconName;
  /** Width and height in pixels. */
  size?: number;
  className?: string;
  /** Spoken name; icons without one are decorative and hidden from screen readers. */
  label?: string;
  strokeWidth?: number;
}

/** One of the app's authored SVG icons, drawn in the current text colour. */
export function Icon({ name, size = 18, className, label, strokeWidth = 1.75 }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      className={cn("shrink-0", className)}
      // The markup is the app's own constant icon set, never user content.
      dangerouslySetInnerHTML={{ __html: iconMarkup(name) }}
    />
  );
}
