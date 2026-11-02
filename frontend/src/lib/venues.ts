import {
  addDays,
  clockMinutes,
  clockTime,
  dayLength,
  formatDistance,
  formatDuration,
} from "./format";
import type { IconName } from "./icons";
import type {
  OpenState,
  PlannedDay,
  PlannedStop,
  StartPoint,
  TripVisit,
  Venue,
  VenueType,
} from "./types";

const VENUE_TYPES: Record<VenueType, { label: string; icon: IconName }> = {
  restaurant: { label: "Restaurant", icon: "utensils" },
  fast_food: { label: "Fast food", icon: "burger" },
  cafe: { label: "Café", icon: "coffee" },
  ice_cream: { label: "Ice cream", icon: "ice-cream" },
  pastry: { label: "Pastry shop", icon: "pastry" },
  bar: { label: "Bar", icon: "cocktail" },
  pub: { label: "Pub", icon: "beer" },
  nightclub: { label: "Club", icon: "music" },
  music_venue: { label: "Live music", icon: "music" },
};

export function venueTypeLabel(type: VenueType): string {
  return VENUE_TYPES[type]?.label ?? "Venue";
}

export function venueIcon(type: VenueType): IconName {
  return VENUE_TYPES[type]?.icon ?? "pin";
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
  /** The stop of the day the point is, if it is one: a place found goes right after it. */
  stop?: number;
  /** The traveller is there (their location, a pin, the stop they visited last, the start
   * point before any visit): on a day under way, a place found is next from there, now. */
  here?: boolean;
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
  if (last) {
    const label = `${last.name}, last visited`;
    return { lat: last.lat, lon: last.lon, label, stop: last.place_id, here: true };
  }
  if (start) return { lat: start.lat, lon: start.lon, label: "your start point", here: true };
  const first = day.stops[0];
  return first
    ? {
        lat: first.lat,
        lon: first.lon,
        label: `${first.name}, the first stop`,
        stop: first.place_id,
      }
    : null;
}

/** Search radius choices, in metres (the backend takes 250 m to 2 km). */
export const RADIUS_OPTIONS = [250, 500, 1000, 2000];
export const DEFAULT_RADIUS_M = 500;

const MINUTES_PER_DAY = 24 * 60;

/** Days between two "YYYY-MM-DD" dates. */
function daysBetween(from: string, to: string): number {
  const utc = (date: string) => {
    const [year, month, day] = date.split("-").map(Number);
    return Date.UTC(year, month - 1, day);
  };
  return Math.round((utc(to) - utc(from)) / (MINUTES_PER_DAY * 60_000));
}

/**
 * Whether trip day `day` is today and not over yet (it may not have begun): then a place
 * added to it is the next stop, from where the traveller is now. `now` is the city's.
 */
export function dayUnderWay(
  day: Pick<PlannedDay, "date" | "start" | "end">,
  now: { date: string; minutes: number },
): boolean {
  if (!day.date || !day.start || !day.end) return false;
  const elapsed = daysBetween(day.date, now.date) * MINUTES_PER_DAY + now.minutes;
  return elapsed >= 0 && elapsed < clockMinutes(day.start) + dayLength(day.start, day.end);
}

/** Where in the day a place found goes, as the day edit asks for it. */
export interface Placement {
  /** Tells the choices apart: "here", "first", or the id of the stop it follows. */
  key: string;
  label: string;
  /** The stop it follows; null: first, after any visited stops. */
  after: PlannedStop | null;
  /** From the search point, now: the day is under way and the traveller is there. */
  fromHere: boolean;
  /** When the traveller sets off for it as the day is planned, in minutes since the day's
   * midnight; null: now, or not known. */
  setOffMin: number | null;
  /** When that is: "when you leave Castelo", "as the day begins", "now". */
  setOff: string;
  /** What adding it does to the day, for the traveller to read first. */
  effect: string;
}

/** Minutes since the day's midnight of a stop's "HH:MM"; before the day starts: the next morning. */
function minuteOfDay(day: Pick<PlannedDay, "start">, time: string): number {
  const minute = clockMinutes(time);
  return day.start && minute < clockMinutes(day.start) ? minute + MINUTES_PER_DAY : minute;
}

/** Squared distance, in degrees of latitude: enough to tell which point is nearest. */
function nearness(a: { lat: number; lon: number }, b: { lat: number; lon: number }): number {
  const east = (a.lon - b.lon) * Math.cos((((a.lat + b.lat) / 2) * Math.PI) / 180);
  return (a.lat - b.lat) ** 2 + east ** 2;
}

/** Where a place found can go in a day, and where it goes unless the traveller says. */
export interface Placements {
  options: Placement[];
  chosen: Placement;
}

/**
 * Where a place found can go in day `day`, and where it goes unless the traveller says
 * otherwise: the next stop. On a day under way, from where the traveller is now, when the
 * search is around them; else right after the stop searched around, or after the stop (or
 * the start point) nearest to the point searched around.
 */
export function placements(
  day: PlannedDay,
  visits: TripVisit[],
  start: StartPoint | null,
  point: SearchPoint | null,
  live: boolean,
): Placements {
  const visited = new Set(visits.map((v) => v.place_id));
  const done = day.stops.filter((s) => visited.has(s.place_id));
  const ahead = day.stops.filter((s) => !visited.has(s.place_id));
  const fromHere = live && point?.here === true;
  const last = done.at(-1);
  // The planned times say when the traveller would go, except from where they are now.
  const time = (minute: number | null) => (minute === null ? "" : ` · ${clockTime(minute)}`);
  const rest = "the rest of the day is planned again from it.";

  let head: Placement;
  if (fromHere) {
    head = {
      key: "here",
      label: "Next, from where you are now",
      after: null,
      fromHere,
      setOffMin: null,
      setOff: "now",
      effect: `It becomes your next stop: day ${day.day} is planned again from here, now.`,
    };
  } else {
    const setOffMin = last
      ? minuteOfDay(day, last.leave)
      : day.start
        ? clockMinutes(day.start)
        : null;
    head = {
      key: "first",
      label: `${last ? "Next, after the stops you visited" : "First, as the day begins"}${time(setOffMin)}`,
      after: null,
      fromHere,
      setOffMin,
      setOff: last ? "after the stops you visited" : "as the day begins",
      effect: last
        ? `It comes right after the stops you visited; ${rest}`
        : `It becomes the first stop of day ${day.day}; ${rest}`,
    };
  }
  const options = [
    head,
    ...ahead.map((stop): Placement => {
      const setOffMin = fromHere ? null : minuteOfDay(day, stop.leave);
      return {
        key: String(stop.place_id),
        label: `After ${stop.name}${time(setOffMin)}`,
        after: stop,
        fromHere,
        setOffMin,
        setOff: fromHere ? "now" : `when you leave ${stop.name}`,
        effect: fromHere
          ? `From here, now: the stops up to ${stop.name}, then this place; ${rest}`
          : `Day ${day.day} stays as planned up to ${stop.name}, then this place; ${rest}`,
      };
    }),
  ];

  if (fromHere || !point) return { options, chosen: head };
  const searched = options.find((o) => o.after !== null && o.after.place_id === point.stop);
  if (searched) return { options, chosen: searched };
  // Not a stop still ahead: after the stop nearest to the point, or first if where the day
  // goes on from (the last visited stop, else the start point) is nearer.
  const origin = last ?? start;
  const located = [
    ...(origin ? [{ option: head, place: origin }] : []),
    ...options.flatMap((o) => (o.after ? [{ option: o, place: o.after }] : [])),
  ];
  let nearest = head;
  let best = Infinity;
  for (const { option, place } of located) {
    const d = nearness(point, place);
    if (d < best) [nearest, best] = [option, d];
  }
  return { options, chosen: nearest };
}

/**
 * When to tell whether venues are open, for a place put at `placement`: the city's
 * "YYYY-MM-DDTHH:MM" when the traveller sets off for it, or null for now (it is next from
 * here, that time has passed, or the plan has no dates).
 */
export function setOffMoment(
  day: Pick<PlannedDay, "date">,
  placement: Pick<Placement, "setOffMin">,
  now: { date: string; minutes: number },
): string | null {
  const minute = placement.setOffMin;
  if (!day.date || minute === null) return null;
  if (minute <= daysBetween(day.date, now.date) * MINUTES_PER_DAY + now.minutes) return null;
  return `${addDays(day.date, Math.floor(minute / MINUTES_PER_DAY))}T${clockTime(minute)}`;
}

const STAYS = [15, 30, 45, 60, 75, 90, 120, 150, 180];

/** Stays to choose from, with the venue's usual one among them. */
export function stayOptions(usual: number): { minutes: number; label: string }[] {
  const minutes = [...new Set([...STAYS, usual])].sort((a, b) => a - b);
  return minutes.map((m) => ({ minutes: m, label: formatDuration(m) }));
}
