import type { PlannedDay, StartPoint, TravelMode } from "./types";

/** Google Maps directions go through at most 9 waypoints between the origin and the destination. */
export const MAX_WAYPOINTS = 9;

/** A place on the day's way: the start point or a stop. */
interface Waypoint {
  lat: number;
  lon: number;
  /** "the start", "stop 3". */
  label: string;
}

/** A Google Maps route of a day: walks in a row, or one ride. */
export interface MapsRoute {
  url: string;
  mode: TravelMode;
  /** Where it begins; null: where the traveller is (Google Maps finds out). */
  from: string | null;
  to: string;
}

function coords({ lat, lon }: Waypoint): string {
  return `${lat.toFixed(6)},${lon.toFixed(6)}`;
}

/** Directions through `points` (the first null: from where the traveller is). */
function directions([origin, ...rest]: (Waypoint | null)[], mode: TravelMode): MapsRoute {
  const destination = rest.at(-1) as Waypoint;
  const waypoints = rest.slice(0, -1) as Waypoint[];
  const params = new URLSearchParams({ api: "1" });
  if (origin) params.set("origin", coords(origin));
  params.set("destination", coords(destination));
  if (waypoints.length > 0) params.set("waypoints", waypoints.map(coords).join("|"));
  params.set("travelmode", mode === "transit" ? "transit" : "walking");
  return {
    url: `https://www.google.com/maps/dir/?${params}`,
    mode,
    from: origin?.label ?? null,
    to: destination.label,
  };
}

/**
 * A day as Google Maps directions, from the start point (if any) through its stops in order,
 * back to it on round trips. Google Maps takes one way of travelling per route, and cannot
 * ride through waypoints: walks in a row are one route (in parts past MAX_WAYPOINTS),
 * each ride a route of its own. A day under way (some stops `visited`) goes from where the
 * traveller is through the stops left; a day without a start point or any stop left before
 * its first one, likewise.
 */
export function googleMapsRoutes(
  day: Pick<PlannedDay, "stops" | "return_mode">,
  start: StartPoint | null,
  visited: ReadonlySet<number> = new Set(),
): MapsRoute[] {
  const left = day.stops
    .map((stop, i) => ({ stop, n: i + 1 }))
    .filter(({ stop }) => !visited.has(stop.place_id));
  if (left.length === 0) return [];
  const underWay = left.length < day.stops.length;
  const home = start && { lat: start.lat, lon: start.lon, label: "the start" };

  // path[i] to path[i + 1] is travelled by legs[i]; null is where the traveller is.
  const path: (Waypoint | null)[] = [];
  const legs: TravelMode[] = [];
  if (underWay || (!home && left.length === 1)) path.push(null);
  else if (home) path.push(home);
  for (const { stop, n } of left) {
    if (path.length > 0) legs.push(stop.travel_mode ?? "walk");
    path.push({ lat: stop.lat, lon: stop.lon, label: `stop ${n}` });
  }
  if (home && start?.round_trip) {
    legs.push(day.return_mode ?? "walk");
    path.push(home);
  }

  const routes: MapsRoute[] = [];
  for (let i = 0; i < legs.length;) {
    const mode = legs[i];
    let j = i + 1;
    while (mode === "walk" && j < legs.length && legs[j] === "walk") j++;
    // Walks too long for one route come in parts of about the same length.
    const parts = Math.ceil((j - i) / (MAX_WAYPOINTS + 1));
    const size = Math.ceil((j - i) / parts);
    for (let k = i; k < j; k += size) {
      routes.push(directions(path.slice(k, Math.min(k + size, j) + 1), mode));
    }
    i = j;
  }
  return routes;
}

/** "Stop 2 to stop 5, on foot", "Where you are to stop 3, by public transport". */
export function mapsRouteLabel({ from, to, mode }: MapsRoute): string {
  const origin = from ?? "where you are";
  const way = from === to ? `${origin} and back` : `${origin} to ${to}`;
  const by = mode === "transit" ? "by public transport" : "on foot";
  return `${way.charAt(0).toUpperCase()}${way.slice(1)}, ${by}`;
}
