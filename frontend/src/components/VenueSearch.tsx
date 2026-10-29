"use client";

import { useEffect, useId, useState, type ReactNode } from "react";

import { searchVenues } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { PlannedDay, Venue, VenueKind, VenuePage } from "@/lib/types";
import {
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
  /** The day is under way: an added place is the next stop, from the search point now. */
  live: boolean;
  /** Add a venue to the day for a stay of `stayMin`, as a draft; resolves to whether it did. */
  onAdd: (venue: Venue, stayMin: number) => Promise<boolean>;
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
  open: "text-emerald-700",
  closed: "text-red-700",
  unknown: "text-zinc-500",
};

/** How long to stay, and the button that adds the venue to the day. */
function AddToRoute({
  venue,
  day,
  live,
  onAdd,
  onCancel,
  adding,
}: {
  venue: Venue;
  day: number;
  live: boolean;
  onAdd: (stayMin: number) => void;
  onCancel: () => void;
  adding: boolean;
}) {
  const stayId = useId();
  const [stay, setStay] = useState(venue.stay_min);
  return (
    <div className="mt-2 space-y-2 rounded-md bg-orange-50 p-2.5 text-xs text-zinc-700">
      <label htmlFor={stayId} className="flex items-center gap-2">
        Stay for
        <select
          id={stayId}
          value={stay}
          onChange={(event) => setStay(Number(event.target.value))}
          disabled={adding}
          className="rounded-md border border-zinc-300 bg-white px-2 py-1 text-sm"
        >
          {stayOptions(venue.stay_min).map((option) => (
            <option key={option.minutes} value={option.minutes}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <p>
        {live
          ? `It becomes your next stop: day ${day} is planned again from here, now.`
          : `Day ${day} is planned again with it, when it suits the day (restaurants and bars in the evening).`}{" "}
        You see the changes before they are saved.
      </p>
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => onAdd(stay)}
          disabled={adding}
          className="rounded-lg bg-orange-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-orange-700 disabled:cursor-wait disabled:bg-orange-400"
        >
          {adding ? "Planning the day…" : live ? "Go here next" : `Add to day ${day}`}
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={adding}
          className="text-sm text-zinc-600 hover:text-zinc-900"
        >
          Cancel
        </button>
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
  const details = [
    ...dietLabels(venue.diets),
    ...(venue.outdoor_seating ? ["Outdoor seating"] : []),
  ];
  return (
    <article
      id={venueCardId(venue.id)}
      onMouseEnter={() => onHover(venue.id)}
      onMouseLeave={() => onHover(null)}
      className={`scroll-mt-40 rounded-lg border bg-white p-3 shadow-sm transition ${
        highlighted ? "border-orange-400 ring-2 ring-orange-500/20" : "border-zinc-200"
      }`}
    >
      <div className="flex items-start gap-3">
        <span className="text-2xl leading-none" aria-hidden>
          {venueIcon(venue.venue_type)}
        </span>
        <div className="min-w-0 flex-1 space-y-0.5">
          <div className="flex items-start justify-between gap-2">
            <h3 className="leading-snug font-medium text-zinc-900">{venue.name}</h3>
            {plannedDay !== undefined && (
              <span className="shrink-0 rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] text-zinc-600">
                On day {plannedDay}
              </span>
            )}
          </div>
          <p className="text-xs text-zinc-600">
            {venueTypeLabel(venue.venue_type)}
            {venue.cuisines.length > 0 && ` · ${venue.cuisines.map(cuisineLabel).join(", ")}`}
          </p>
          <p className="text-xs">
            <span className={OPEN_STYLES[opening.state]}>{opening.text}</span>
            <span className="text-zinc-500"> · {walkLabel(venue)}</span>
          </p>
          {details.length > 0 && <p className="text-xs text-zinc-600">{details.join(" · ")}</p>}
          {(venue.website || venue.phone) && (
            <p className="flex gap-3 text-xs">
              {venue.website && (
                <a
                  href={venue.website}
                  target="_blank"
                  rel="noreferrer"
                  className="text-blue-700 hover:underline"
                >
                  Website
                </a>
              )}
              {venue.phone && (
                <a href={`tel:${venue.phone}`} className="text-blue-700 hover:underline">
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
  live,
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
    ? { lat: point.lat, lon: point.lon, radius_m: radius, ...filters, limit }
    : null;
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
    <section className="space-y-4" aria-label="Places to eat and drink">
      <div className="sticky top-0 z-10 -mx-4 -mt-4 space-y-1 border-b border-zinc-200 bg-zinc-50/95 px-4 pt-4 pb-3 backdrop-blur lg:-mx-6 lg:-mt-6 lg:px-6 lg:pt-6">
        <button
          type="button"
          onClick={onBack}
          className="text-sm font-medium text-blue-700 hover:text-blue-900"
        >
          ← Back to route
        </button>
        <h2 className="text-lg font-semibold tracking-tight text-zinc-900">
          Places to eat &amp; drink
        </h2>
        <p className="text-xs text-zinc-500">
          For day {day.day}
          {day.date && ` · ${formatDate(day.date)}`}
        </p>
      </div>

      <div className="space-y-2 rounded-lg border border-zinc-200 bg-white p-3 text-sm">
        <p className="text-zinc-800">
          <span aria-hidden>📍 </span>
          {point ? `Near ${point.label}` : "Where are you? Use your location or pin it."}
        </p>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={locate}
            disabled={locating}
            className="rounded-md bg-zinc-100 px-2.5 py-1 text-xs font-medium text-zinc-700 hover:bg-zinc-200 disabled:cursor-wait"
          >
            {locating ? "Locating…" : "Use my location"}
          </button>
          <button
            type="button"
            onClick={onTogglePicking}
            aria-pressed={picking}
            className={`rounded-md px-2.5 py-1 text-xs font-medium ${
              picking ? "bg-blue-600 text-white" : "bg-zinc-100 text-zinc-700 hover:bg-zinc-200"
            }`}
          >
            {picking ? "Click the map…" : "Pin on the map"}
          </button>
        </div>
        {locateError && <p className="text-xs text-red-700">{locateError}</p>}
      </div>

      <div className="space-y-3">
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Kind of place">
          {KINDS.map(({ kind, label }) => (
            <button
              key={label}
              type="button"
              aria-pressed={filters.kind === kind}
              onClick={() => change({ kind, cuisine: null })}
              className={`rounded-full border px-3 py-1 text-xs font-medium ${
                filters.kind === kind
                  ? "border-zinc-900 bg-zinc-900 text-white"
                  : "border-zinc-300 bg-white text-zinc-700 hover:border-zinc-400"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap gap-x-4 gap-y-2 text-sm">
          <label htmlFor={radiusId} className="flex items-center gap-2 text-zinc-700">
            Within
            <select
              id={radiusId}
              value={radius}
              onChange={(event) => {
                onRadiusChange(Number(event.target.value));
                setLimit(PAGE_SIZE);
              }}
              className="rounded-md border border-zinc-300 bg-white px-2 py-1 text-sm"
            >
              {RADIUS_OPTIONS.map((meters) => (
                <option key={meters} value={meters}>
                  {radiusLabel(meters)}
                </option>
              ))}
            </select>
          </label>
          <label htmlFor={cuisineId} className="flex items-center gap-2 text-zinc-700">
            Cuisine
            <select
              id={cuisineId}
              value={filters.cuisine ?? ""}
              onChange={(event) => change({ cuisine: event.target.value || null })}
              className="max-w-44 rounded-md border border-zinc-300 bg-white px-2 py-1 text-sm"
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
        <div className="flex flex-wrap gap-x-4 gap-y-1.5 text-sm text-zinc-700">
          {TOGGLES.map(({ key: toggle, label }) => (
            <label key={toggle} className="flex items-center gap-1.5">
              <input
                type="checkbox"
                checked={filters[toggle]}
                onChange={(event) => change({ [toggle]: event.target.checked })}
                className="h-4 w-4 rounded border-zinc-300"
              />
              {label}
            </label>
          ))}
        </div>
      </div>

      <div aria-live="polite" className="text-xs text-zinc-500">
        {loading && "Searching…"}
        {failed && (
          <span className="text-red-700">The search is unavailable right now. Try again.</span>
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
        <ul className={`space-y-2 ${loading ? "opacity-60" : ""}`}>
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
                    live={live}
                    onAdd={(stay) => onAdd(venue, stay)}
                    onCancel={() => setChoosing(null)}
                    adding={adding}
                  />
                ) : (
                  <div className="mt-2 flex justify-end">
                    <button
                      type="button"
                      onClick={() => setChoosing(venue.id)}
                      disabled={adding}
                      className="rounded-md bg-orange-100 px-2.5 py-1 text-xs font-medium text-orange-900 hover:bg-orange-200"
                    >
                      Add to route
                    </button>
                  </div>
                )}
                {choosing === venue.id && error && (
                  <p role="alert" className="mt-2 text-xs text-red-700">
                    {error}
                  </p>
                )}
              </VenueCard>
            </li>
          ))}
        </ul>
      )}
      {page && page.items.length < page.total && limit < MAX_RESULTS && (
        <button
          type="button"
          onClick={() => setLimit((l) => Math.min(l + PAGE_SIZE, MAX_RESULTS))}
          className="w-full rounded-lg border border-zinc-300 bg-white py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50"
        >
          Show more
        </button>
      )}
      <p className="text-[11px] text-zinc-400">
        Venues from OpenStreetMap, which has no ratings or prices. Opening hours as mapped: check
        before you go.
      </p>
    </section>
  );
}
