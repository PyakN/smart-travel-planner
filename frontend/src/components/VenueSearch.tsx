"use client";

import { useEffect, useId, useState, type ReactNode } from "react";

import { Button } from "@/components/ui/Button";
import { cn } from "@/components/ui/cn";
import { SELECT } from "@/components/ui/Field";
import { Icon } from "@/components/ui/Icon";
import { Checkbox, OptionChip } from "@/components/ui/Toggle";
import { searchVenues } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { PlannedDay, Venue, VenueKind, VenuePage } from "@/lib/types";
import {
  type Placement,
  type Placements,
  RADIUS_OPTIONS,
  type SearchPoint,
  cuisineLabel,
  dietLabels,
  openingLabel,
  stayOptions,
  venueIcon,
  venueTypeLabel,
  walkLabel,
} from "@/lib/venues";

const DEBOUNCE_MS = 200;
const PAGE_SIZE = 30;
const MAX_RESULTS = 100;

export interface VenueSearchProps {
  /** The trip day the search is for. */
  day: PlannedDay;
  /** Where to search; null while it is not known. */
  point: SearchPoint | null;
  onPointChange: (point: SearchPoint) => void;
  radius: number;
  onRadiusChange: (radius: number) => void;
  /** The traveller is pinning the point on the map. */
  picking: boolean;
  onTogglePicking: () => void;
  initialKind: VenueKind | null;
  /** The venues found, for the map. */
  onResults: (venues: Venue[]) => void;
  highlighted: number | null;
  onHover: (venueId: number | null) => void;
  /** Places on the trip already, and their day. */
  planned: ReadonlyMap<number, number>;
  onBack: () => void;
  /** Where in the day a venue can go, and where it goes by default: the next stop. */
  placements: Placements;
  /** When the traveller sets off for it by default, in the city's time ("YYYY-MM-DDTHH:MM"):
   * venues are open or closed then. Null: now. */
  at: string | null;
  /** Add a venue to the day for a stay of `stayMin` at `placement`, as a draft; resolves to
   * whether it did. */
  onAdd: (venue: Venue, stayMin: number, placement: Placement) => Promise<boolean>;
  /** The day is being planned again with a venue. */
  adding: boolean;
  /** Why adding a venue failed. */
  error: string | null;
}

interface Filters {
  kind: VenueKind | null;
  cuisine: string | null;
  vegetarian: boolean;
  vegan: boolean;
  open_now: boolean;
  outdoor_seating: boolean;
}

const KINDS: { kind: VenueKind | null; label: string }[] = [
  { kind: null, label: "All" },
  { kind: "food", label: "Food" },
  { kind: "drinks", label: "Drinks & nightlife" },
];

const TOGGLES: { key: "open_now" | "vegetarian" | "vegan" | "outdoor_seating"; label: string }[] = [
  { key: "open_now", label: "Open now" },
  { key: "vegetarian", label: "Vegetarian" },
  { key: "vegan", label: "Vegan" },
  { key: "outdoor_seating", label: "Outdoor seating" },
];

/** The element id of a venue's card, so a click on its marker can scroll to it. */
export function venueCardId(venueId: number): string {
  return `venue-card-${venueId}`;
}

function radiusLabel(meters: number): string {
  return meters < 1000 ? `${meters} m` : `${meters / 1000} km`;
}

const OPEN_STYLES = {
  open: { text: "text-go", dot: "bg-go" },
  closed: { text: "text-stop", dot: "bg-stop" },
  unknown: { text: "text-ink-2", dot: "bg-line-strong" },
};

/** How long to stay and when, and the button that adds the venue to the day. */
function AddToRoute({
  venue,
  day,
  placements,
  onAdd,
  onCancel,
  adding,
}: {
  venue: Venue;
  day: number;
  placements: Placements;
  onAdd: (stayMin: number, placement: Placement) => void;
  onCancel: () => void;
  adding: boolean;
}) {
  const stayId = useId();
  const placementId = useId();
  const [stay, setStay] = useState(venue.stay_min);
  const [key, setKey] = useState(placements.chosen.key);
  const placement = placements.options.find((o) => o.key === key) ?? placements.chosen;
  return (
    <div className="mt-3 animate-rise space-y-3 rounded-control bg-canvas p-3 text-small text-ink-2">
      <div className="grid grid-cols-[auto_minmax(0,1fr)] items-center gap-x-2.5 gap-y-2 font-bold text-ink">
        <label htmlFor={stayId}>Stay for</label>
        <select
          id={stayId}
          value={stay}
          onChange={(event) => setStay(Number(event.target.value))}
          disabled={adding}
          className={cn(SELECT, "justify-self-start")}
        >
          {stayOptions(venue.stay_min).map((option) => (
            <option key={option.minutes} value={option.minutes}>
              {option.label}
            </option>
          ))}
        </select>
        <label htmlFor={placementId}>Visit</label>
        <select
          id={placementId}
          value={placement.key}
          onChange={(event) => setKey(event.target.value)}
          disabled={adding}
          className={cn(SELECT, "w-full")}
        >
          {placements.options.map((option) => (
            <option key={option.key} value={option.key}>
              {option.label}
            </option>
          ))}
        </select>
      </div>
      <p>{placement.effect} You see the changes before they are saved.</p>
      <div className="flex items-center gap-2">
        <Button
          variant="primary"
          onClick={() => onAdd(stay, placement)}
          disabled={adding}
          className="flex-1"
        >
          {adding
            ? "Planning the day…"
            : placement.key === "here"
              ? "Go here next"
              : `Add to day ${day}`}
        </Button>
        <Button variant="quiet" onClick={onCancel} disabled={adding}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

function VenueCard({
  venue,
  highlighted,
  plannedDay,
  onHover,
  children,
}: {
  venue: Venue;
  highlighted: boolean;
  plannedDay: number | undefined;
  onHover: (venueId: number | null) => void;
  /** The add-to-route controls. */
  children: ReactNode;
}) {
  const opening = openingLabel(venue);
  const open = OPEN_STYLES[opening.state];
  const details = [
    ...dietLabels(venue.diets),
    ...(venue.outdoor_seating ? ["Outdoor seating"] : []),
  ];
  const drinks = venue.category === "nightlife";
  return (
    <article
      id={venueCardId(venue.id)}
      onMouseEnter={() => onHover(venue.id)}
      onMouseLeave={() => onHover(null)}
      className={cn(
        "scroll-mt-44 rounded-panel border bg-surface p-3.5 transition-colors duration-200",
        highlighted ? "border-ink" : "border-line hover:border-line-strong",
      )}
    >
      <div className="flex items-start gap-3">
        <span
          className={cn(
            "flex size-10 shrink-0 items-center justify-center rounded-full text-white",
            drinks ? "bg-evening" : "bg-ink",
          )}
          aria-hidden
        >
          <Icon name={venueIcon(venue.venue_type)} size={20} />
        </span>
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex items-start justify-between gap-2">
            <h3 className="text-base leading-snug font-bold text-ink">{venue.name}</h3>
            {plannedDay !== undefined && (
              <span className="inline-flex h-6 shrink-0 items-center rounded-tag bg-canvas px-1.5 text-meta font-bold text-ink-2">
                On day {plannedDay}
              </span>
            )}
          </div>
          <p className="text-small text-ink-2">
            {venueTypeLabel(venue.venue_type)}
            {venue.cuisines.length > 0 && `, ${venue.cuisines.map(cuisineLabel).join(", ")}`}
          </p>
          <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-small">
            <span className={cn("inline-flex items-center gap-1.5 font-bold", open.text)}>
              <span className={cn("size-2 rounded-full", open.dot)} aria-hidden />
              {opening.text}
            </span>
            <span className="inline-flex items-center gap-1 text-ink-2 tabular-nums">
              <Icon name="walk" size={15} className="text-ink-3" />
              {walkLabel(venue)}
            </span>
          </p>
          {details.length > 0 && <p className="text-small text-ink-2">{details.join(", ")}</p>}
          {(venue.website || venue.phone) && (
            <p className="flex flex-wrap gap-x-4 gap-y-1 pt-0.5 text-small">
              {venue.website && (
                <a
                  href={venue.website}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 font-bold text-ink underline-offset-3 hover:underline"
                >
                  <Icon name="globe" size={15} className="text-ink-3" />
                  Website
                </a>
              )}
              {venue.phone && (
                <a
                  href={`tel:${venue.phone}`}
                  className="inline-flex items-center gap-1 font-bold text-ink underline-offset-3 hover:underline"
                >
                  <Icon name="phone" size={15} className="text-ink-3" />
                  {venue.phone}
                </a>
              )}
            </p>
          )}
        </div>
      </div>
      {children}
    </article>
  );
}

interface Results {
  key: string;
  page: VenuePage | null;
  failed: boolean;
}

/**
 * Places to eat and drink around a point, in the sidebar instead of the plan: where (the
 * traveller's location, a pin, a stop), filters, and the venues as cards.
 */
export default function VenueSearch({
  day,
  point,
  onPointChange,
  radius,
  onRadiusChange,
  picking,
  onTogglePicking,
  initialKind,
  onResults,
  highlighted,
  onHover,
  planned,
  onBack,
  placements,
  at,
  onAdd,
  adding,
  error,
}: VenueSearchProps) {
  const radiusId = useId();
  const cuisineId = useId();
  const [filters, setFilters] = useState<Filters>({
    kind: initialKind,
    cuisine: null,
    vegetarian: false,
    vegan: false,
    open_now: false,
    outdoor_seating: false,
  });
  const [limit, setLimit] = useState(PAGE_SIZE);
  const [results, setResults] = useState<Results>({ key: "", page: null, failed: false });
  const [locating, setLocating] = useState(false);
  const [locateError, setLocateError] = useState<string | null>(null);
  // The venue whose stay is being chosen.
  const [choosing, setChoosing] = useState<number | null>(null);

  const query = point
    ? { lat: point.lat, lon: point.lon, radius_m: radius, ...filters, limit, at }
    : null;
  // "HH:MM" of `at`: the venues' hours are judged then.
  const setOffTime = at?.slice(11) ?? null;
  const key = JSON.stringify(query);
  useEffect(() => {
    if (!query) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      searchVenues(query, { signal: controller.signal })
        .then((page) => {
          setResults({ key, page, failed: false });
          onResults(page.items);
        })
        .catch(() => {
          if (!controller.signal.aborted) setResults({ key, page: null, failed: true });
        });
    }, DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
    // `key` stands for the query: a new object every render, the same search.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  // The last results stay on screen, dimmed, while the next search runs.
  const loading = query !== null && results.key !== key;
  const page = results.page;
  const failed = results.failed && !loading;

  function change(update: Partial<Filters>) {
    setFilters((f) => ({ ...f, ...update }));
    setLimit(PAGE_SIZE);
  }

  function locate() {
    if (!navigator.geolocation) {
      setLocateError("This browser cannot tell your location. Pin it on the map instead.");
      return;
    }
    setLocating(true);
    setLocateError(null);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLocating(false);
        onPointChange({
          lat: position.coords.latitude,
          lon: position.coords.longitude,
          label: "your location",
          here: true,
        });
      },
      () => {
        setLocating(false);
        setLocateError("Your location is not available. Pin it on the map instead.");
      },
      { enableHighAccuracy: true, timeout: 10_000, maximumAge: 60_000 },
    );
  }

  const cuisines = page?.cuisines ?? [];
  const chosen = filters.cuisine;
  const cuisineOptions =
    chosen && !cuisines.some((c) => c.cuisine === chosen)
      ? [{ cuisine: chosen, count: 0 }, ...cuisines]
      : cuisines;

  return (
    <section className="space-y-5" aria-label="Places to eat and drink">
      <div className="sticky top-0 z-10 -mx-5 -mt-6 space-y-2 border-b border-line bg-surface px-5 pt-4 pb-4 lg:-mx-8 lg:-mt-8 lg:px-8 lg:pt-6">
        <button
          type="button"
          onClick={onBack}
          className="-ml-2 inline-flex h-9 items-center gap-1.5 rounded-control px-2 text-sm font-bold text-ink transition-colors hover:bg-canvas"
        >
          <Icon name="arrow-left" size={17} />
          Back to route
        </button>
        <div>
          <h2 className="font-display text-title font-semibold text-ink">
            Places to eat &amp; drink
          </h2>
          <p className="text-small text-ink-2">
            For day {day.day}
            {day.date && `, ${formatDate(day.date)}`}
          </p>
        </div>
      </div>

      <div className="space-y-3 rounded-panel border border-line bg-surface p-3.5">
        <p className="flex items-start gap-2 text-sm text-ink">
          <Icon name="pin" size={18} className="mt-px text-ink-3" />
          <span className="font-bold">
            {point ? `Near ${point.label}` : "Where are you? Use your location or pin it."}
          </span>
        </p>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" icon="locate" onClick={locate} disabled={locating}>
            {locating ? "Locating…" : "Use my location"}
          </Button>
          <Button
            size="sm"
            variant={picking ? "dark" : "secondary"}
            icon="pin"
            onClick={onTogglePicking}
            aria-pressed={picking}
          >
            {picking ? "Click the map…" : "Pin on the map"}
          </Button>
        </div>
        {locateError && (
          <p role="alert" className="text-small font-bold text-stop">
            {locateError}
          </p>
        )}
        {setOffTime && (
          <p className="flex items-start gap-2 text-small text-ink-2">
            <Icon name="clock" size={16} className="mt-px text-ink-3" />
            <span>
              Open or closed as of{" "}
              <span className="font-bold text-ink tabular-nums">{setOffTime}</span>,{" "}
              {placements.chosen.setOff}.
            </span>
          </p>
        )}
      </div>

      <div className="space-y-4">
        <div className="flex flex-wrap gap-2" role="group" aria-label="Kind of place">
          {KINDS.map(({ kind, label }) => (
            <OptionChip
              key={label}
              pressed={filters.kind === kind}
              onClick={() => change({ kind, cuisine: null })}
            >
              {label}
            </OptionChip>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-3">
          <label htmlFor={radiusId} className="block space-y-1.5">
            <span className="block text-small font-bold text-ink-2">Within</span>
            <select
              id={radiusId}
              value={radius}
              onChange={(event) => {
                onRadiusChange(Number(event.target.value));
                setLimit(PAGE_SIZE);
              }}
              className={cn(SELECT, "w-full")}
            >
              {RADIUS_OPTIONS.map((meters) => (
                <option key={meters} value={meters}>
                  {radiusLabel(meters)}
                </option>
              ))}
            </select>
          </label>
          <label htmlFor={cuisineId} className="block min-w-0 space-y-1.5">
            <span className="block text-small font-bold text-ink-2">Cuisine</span>
            <select
              id={cuisineId}
              value={filters.cuisine ?? ""}
              onChange={(event) => change({ cuisine: event.target.value || null })}
              className={cn(SELECT, "w-full")}
            >
              <option value="">Any</option>
              {cuisineOptions.map(({ cuisine, count }) => (
                <option key={cuisine} value={cuisine}>
                  {cuisineLabel(cuisine)} ({count})
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="flex flex-wrap gap-x-5 gap-y-2.5">
          {TOGGLES.map(({ key: toggle, label }) => (
            <Checkbox
              key={toggle}
              checked={filters[toggle]}
              onChange={(event) => change({ [toggle]: event.target.checked })}
            >
              {toggle === "open_now" && setOffTime ? `Open at ${setOffTime}` : label}
            </Checkbox>
          ))}
        </div>
      </div>

      <div aria-live="polite" className="text-small text-ink-2">
        {loading && "Searching…"}
        {failed && (
          <span className="font-bold text-stop">
            The search is unavailable right now. Try again.
          </span>
        )}
        {page &&
          !loading &&
          (page.total === 0
            ? `Nothing matches within ${radiusLabel(radius)}. Search wider, or turn a filter off.`
            : `${page.total} ${page.total === 1 ? "place" : "places"} within ${radiusLabel(radius)}, closest first${
                page.items.length < page.total ? ` (showing ${page.items.length})` : ""
              }.`)}
      </div>

      {page && page.items.length > 0 && (
        <ul className={cn("space-y-2.5 transition-opacity", loading && "opacity-55")}>
          {page.items.map((venue) => (
            <li key={venue.id}>
              <VenueCard
                venue={venue}
                highlighted={highlighted === venue.id}
                plannedDay={planned.get(venue.id)}
                onHover={onHover}
              >
                {planned.has(venue.id) ? null : choosing === venue.id ? (
                  <AddToRoute
                    venue={venue}
                    day={day.day}
                    placements={placements}
                    onAdd={(stay, placement) => onAdd(venue, stay, placement)}
                    onCancel={() => setChoosing(null)}
                    adding={adding}
                  />
                ) : (
                  <div className="mt-3 flex justify-end">
                    <Button
                      size="sm"
                      icon="plus"
                      onClick={() => setChoosing(venue.id)}
                      disabled={adding}
                    >
                      Add to route
                    </Button>
                  </div>
                )}
                {choosing === venue.id && error && (
                  <p role="alert" className="mt-2 text-small font-bold text-stop">
                    {error}
                  </p>
                )}
              </VenueCard>
            </li>
          ))}
        </ul>
      )}
      {page && page.items.length < page.total && limit < MAX_RESULTS && (
        <Button block onClick={() => setLimit((l) => Math.min(l + PAGE_SIZE, MAX_RESULTS))}>
          Show more
        </Button>
      )}
      <p className="text-meta text-ink-3">
        Venues from OpenStreetMap, which has no ratings or prices. Opening hours as mapped: check
        before you go.
      </p>
    </section>
  );
}
