import { cn } from "@/components/ui/cn";
import { Icon } from "@/components/ui/Icon";
import { DAY_COLORS } from "@/lib/format";

// Seven places, schematic: the same set drawn in two orders.
const PLACES: [number, number][] = [
  [26, 110],
  [50, 60],
  [98, 32],
  [160, 28],
  [216, 48],
  [254, 92],
  [234, 128],
];
// The order an AI lists places in, before the optimizer: it crosses itself.
const AI_ORDER = [0, 4, 1, 6, 2, 5, 3];
const ROUTE_ORDER = [0, 1, 2, 3, 4, 5, 6];

function path(order: number[]): string {
  return order
    .map((i, step) => `${step === 0 ? "M" : "L"}${PLACES[i][0]} ${PLACES[i][1]}`)
    .join(" ");
}

/**
 * What the optimizer does, shown rather than claimed: the same places in the AI's order and
 * in the optimized order, with the benchmark's result (docs/benchmark.md).
 */
export default function ProofCard({
  onDismiss,
  className,
}: {
  onDismiss?: () => void;
  className?: string;
}) {
  const route = DAY_COLORS[0];
  return (
    <figure
      className={cn("rounded-panel border border-line bg-surface p-4 shadow-float", className)}
    >
      <div className="flex items-start justify-between gap-3">
        <h2 className="font-display text-[19px] leading-tight font-semibold text-ink">
          Same places, shorter walk
        </h2>
        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            aria-label="Hide this explanation"
            className="-mt-1 -mr-1 flex size-8 shrink-0 items-center justify-center rounded-control text-ink-3 transition-colors hover:bg-canvas hover:text-ink"
          >
            <Icon name="x" size={16} />
          </button>
        )}
      </div>
      <svg viewBox="0 0 280 150" className="mt-2 h-auto w-full" aria-hidden>
        <path
          d={path(AI_ORDER)}
          pathLength={1}
          className="proof-path proof-path-ai stroke-line-strong"
          fill="none"
          strokeWidth={2.5}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        <path
          d={path(ROUTE_ORDER)}
          pathLength={1}
          className="proof-path proof-path-route stroke-surface"
          fill="none"
          strokeWidth={9}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        <path
          d={path(ROUTE_ORDER)}
          pathLength={1}
          className="proof-path proof-path-route"
          fill="none"
          stroke={route}
          strokeWidth={4.5}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        {PLACES.map(([x, y], i) => (
          <circle
            key={i}
            cx={x}
            cy={y}
            r={6}
            strokeWidth={2.5}
            className="fill-surface stroke-ink"
          />
        ))}
      </svg>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-meta text-ink-2" aria-hidden>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-[3px] w-4 rounded-full bg-line-strong" />
          The AI&apos;s own order
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-[3px] w-4 rounded-full" style={{ background: route }} />
          Optimized route
        </span>
      </div>
      <figcaption className="mt-2.5 text-small text-ink-2">
        On five benchmark trips, the optimizer walked{" "}
        <strong className="font-bold text-ink">55% less</strong> than the order the AI listed the
        places in, with no legs crossing (13 before).
      </figcaption>
    </figure>
  );
}
