import { formatDistance } from "./format";
import type { OpenState, PlannedDay, StartPoint, TripVisit, Venue, VenueType } from "./types";

const VENUE_TYPES: Record<VenueType, { label: string; icon: string }> = {
  restaurant: { label: "Restaurant", icon: "🍽️" },
  fast_food: { label: "Fast food", icon: "🍔" },
  cafe: { label: "Café", icon: "☕" },
  ice_cream: { label: "Ice cream", icon: "🍦" },
  pastry: { label: "Pastry shop", icon: "🥐" },
  bar: { label: "Bar", icon: "🍸" },
  pub: { label: "Pub", icon: "🍺" },
  nightclub: { label: "Club", icon: "🪩" },
  music_venue: { label: "Live music", icon: "🎵" },
};

export function venueTypeLabel(type: VenueType): string {
  return VENUE_TYPES[type]?.label ?? "Venue";
}

export function venueIcon(type: VenueType): string {
  return VENUE_TYPES[type]?.icon ?? "📍";
}

/** OSM cuisine values for people: "coffee_shop" -> "Coffee shop". */
export function cuisineLabel(cuisine: string): string {
  const words = cuisine.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

const DIETS: Record<string, string> = {
  vegetarian: "Vegetarian",
  vegan: "Vegan",
  gluten_free: "Gluten-free",
  halal: "Halal",
  kosher: "Kosher",
};

/** "Vegetarian only", "Vegan options": what a venue serves for diets. */
export function dietLabels(diets: Venue["diets"]): string[] {
  return Object.entries(diets).map(([diet, level]) => {
    const name = DIETS[diet] ?? cuisineLabel(diet);
    return level === "only" ? `${name} only` : `${name} options`;
  });
}

/**
 * Whether a venue is open, now and when the traveller gets there: "Open until 23:00",
 * "Opens at 19:00, by the time you get there", "Closes at 15:00, before you get there".
 */
export function openingLabel(venue: Pick<Venue, "open_now" | "open_on_arrival" | "changes_at">): {
  text: string;
  state: OpenState;
} {
  const { open_now: now, open_on_arrival: arrival, changes_at: at } = venue;
  if (now === "unknown") return { text: "Opening hours unknown", state: "unknown" };
  if (now === "open" && arrival === "closed") {
    return { text: `Closes at ${at}, before you get there`, state: "closed" };
  }
  if (now === "closed" && arrival === "open") {
    return { text: `Opens at ${at}, by the time you get there`, state: "open" };
  }
  if (now === "open") return { text: at ? `Open until ${at}` : "Open", state: "open" };
  return { text: at ? `Closed · opens at ${at}` : "Closed", state: "closed" };
}

/** "350 m · 6 min walk". */
export function walkLabel(venue: Pick<Venue, "distance_m" | "walk_min">): string {
  return `${formatDistance(venue.distance_m)} · ${venue.walk_min} min walk`;
}

/** Where the search looks around, and how to say it after "Near": "Castelo, last visited". */
export interface SearchPoint {
  lat: number;
  lon: number;
  label: string;
}

/**
 * Where to search when the traveller has not said: the day's last visited stop (the most
 * recently ticked), else the hotel, else the day's first stop.
 */
export function defaultSearchPoint(
  day: PlannedDay,
  visits: TripVisit[],
  start: StartPoint | null,
): SearchPoint | null {
  const stops = new Map(day.stops.map((s) => [s.place_id, s]));
  const visited = [...visits].reverse().find((v) => stops.has(v.place_id));
  const last = visited && stops.get(visited.place_id);
  if (last) return { lat: last.lat, lon: last.lon, label: `${last.name}, last visited` };
  if (start) return { lat: start.lat, lon: start.lon, label: "your start point" };
  const first = day.stops[0];
  return first ? { lat: first.lat, lon: first.lon, label: `${first.name}, the first stop` } : null;
}

/** Search radius choices, in metres (the backend takes 250 m to 2 km). */
export const RADIUS_OPTIONS = [250, 500, 1000, 2000];
export const DEFAULT_RADIUS_M = 500;
