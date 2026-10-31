/** The mark: three stops on one line, the last in tram yellow. */
export function LogoMark({ size = 26 }: { size?: number }) {
  return (
    <svg viewBox="0 0 28 28" width={size} height={size} aria-hidden className="shrink-0">
      <path
        d="M5 20.5 13 8.5l10 9"
        fill="none"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity="0.55"
      />
      <circle cx="5" cy="20.5" r="3.4" fill="currentColor" />
      <circle cx="13" cy="8.5" r="3.4" fill="currentColor" />
      <circle cx="23" cy="17.5" r="4.4" fill="var(--color-signal)" />
    </svg>
  );
}
