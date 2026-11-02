// Mirrors backend/app/schemas/plan.py (POST /plan, GET /plans/{id}, POST /plans/{id}/replace),
// backend/app/schemas/place.py (GET /places), backend/app/schemas/account.py (/auth),
// backend/app/schemas/saved_trip.py (/trips, POST /trips/{id}/edit) and
// backend/app/schemas/venue.py (GET /venues).

export type TravelMode = "walk" | "transit";
export type TransitVehicle =
  "metro" | "tram" | "bus" | "train" | "ferry" | "funicular" | "cable_car" | "other";
export type Pace = "relaxed" | "moderate" | "intense";
export type WeatherCondition =
  "clear" | "clouds" | "fog" | "drizzle" | "rain" | "snow" | "thunderstorm";
/** When a place can be visited: by day (until 20:00), in daylight, at night (from 20:00), any time. */
export type VisitHours = "any" | "day" | "daylight" | "night";
/** [lon, lat], GeoJSON order. */
export type LonLat = [number, number];

export interface StartPoint {
  lat: number;
  lon: number;
  round_trip: boolean;
}

/** A day's hours, "HH:MM" in the city's time; an end not after the start is the next morning. */
export interface DayHours {
  start: string;
  end: string;
}

/** A city plans can be made for (GET /cities). */
export interface City {
  /** `city` in POST /plan and GET /places. */
  slug: string;
  name: string;
  /** IANA time zone: trip dates and hours are the city's. */
  timezone: string;
  /** Where its places are: west, south, east, north. */
  bbox: [number, number, number, number];
}

export interface PlanRequest {
  text: string;
  /** A slug from GET /cities; a text that names another city is refused (422). Unset: the
   * city the text names. */
  city?: string | null;
  start?: StartPoint | null;
  /** Place ids from GET /places. */
  must_visit?: number[];
  modes?: TravelMode[];
  /** "YYYY-MM-DD"; the backend takes tomorrow when it is missing. */
  start_date?: string | null;
  /** Plan with the forecast of the days' hours; without it no forecast is fetched. */
  weather_aware?: boolean;
  /** "HH:MM", the city's local time: when each day starts (09:30 by default). */
  day_start?: string;
  /** "HH:MM": when each day ends (21:30); not after day_start means the next morning. */
  day_end?: string;
  /** "HH:MM": when the first day starts, if not at day_start (today: from now). */
  first_day_start?: string | null;
  /** Number of days (1–7), in place of the one the text gives. */
  day_count?: number | null;
  /** Each day's own hours, day 1 first, in place of day_start, day_end and first_day_start. */
  day_hours?: DayHours[];
}

export interface ReplaceRequest {
  day: number;
  place_ids: number[];
}

export interface PlaceRef {
  place_id: number;
  name: string;
}

/** A search result from GET /places. */
export interface Place {
  id: number;
  name: string;
  category: string;
  lat: number;
  lon: number;
}

export interface PlacePage {
  items: Place[];
  total: number;
}

export interface StopPhoto {
  url: string;
  /** Wikimedia Commons file page: author and licence. */
  page_url: string | null;
  credit: string | null;
}

/** Data credit a transit operator requires next to its routes. */
export interface Attribution {
  text: string;
  url: string | null;
}

export interface TransitRide {
  vehicle: TransitVehicle;
  /** "28E", "Verde" (metro), "Linha de Cascais". */
  line: string;
  /** Where the vehicle is going. */
  headsign: string | null;
  /** The line's own colour, "#RRGGBB". */
  color: string | null;
  board: string | null;
  alight: string | null;
  /** Number of stops ridden. */
  stops: number;
  minutes: number;
  attributions: Attribution[];
}

export interface ForecastSlot {
  /** "HH:MM": the forecast holds for the 3 hours around it. */
  time: string;
  temp_c: number;
  condition: WeatherCondition;
  /** e.g. "light rain". */
  description: string;
  /** OpenWeatherMap icon code, e.g. "10d" ("n" at night). */
  icon: string;
  /** Chance of rain or snow, %. */
  pop: number;
}

/** The forecast at the stop's arrival. */
export interface StopForecast extends ForecastSlot {
  /** Outdoor stops only: what spoils the visit (rain, fog, darkness). */
  warning: string | null;
}

/** The weather of a day's sightseeing hours, headed by its worst bad spell. */
export interface DayForecast {
  condition: WeatherCondition;
  description: string;
  icon: string;
  temp_min_c: number;
  temp_max_c: number;
  /** Highest chance of rain or snow, %. */
  pop: number;
  sunrise: string;
  sunset: string;
  slots: ForecastSlot[];
}

/** Where and when the way to a stop starts, when not at the stop before it. */
export interface Departure {
  lat: number;
  lon: number;
  /** "HH:MM". */
  time: string;
}

export interface PlannedStop {
  place_id: number;
  name: string;
  category: string;
  lat: number;
  lon: number;
  arrive: string;
  leave: string;
  travel_mode: TravelMode | null;
  travel_min: number;
  distance_from_previous_m: number;
  /** The rides of a transit leg; empty for walks and estimated rides. */
  rides: TransitRide[];
  must_visit: boolean;
  /** Why this place suits the traveller (from the AI). */
  note: string | null;
  description: string | null;
  photo: StopPhoto | null;
  /** OpenStreetMap opening_hours syntax, e.g. "Tu-Su 10:00-18:00". */
  opening_hours: string | null;
  website: string | null;
  /** Visited in the open air. */
  outdoor: boolean;
  /** Null without a forecast for its time. */
  weather: StopForecast | null;
  hours: VisitHours;
  /** Free time before setting off for it, in minutes: it opens later. */
  wait_min: number;
  /** The traveller's location, on a day re-planned from it; null: from the stop before. */
  departure: Departure | null;
}

export interface RouteSegment {
  mode: TravelMode;
  /** Along the streets or the line; a straight line for an estimated ride. */
  geometry: LonLat[];
  ride: TransitRide | null;
}

export interface PlannedDay {
  day: number;
  stops: PlannedStop[];
  distance_m: number;
  walking_m: number;
  transit_legs: number;
  duration_min: number;
  self_intersections: number;
  segments: RouteSegment[];
  /** "YYYY-MM-DD"; null on plans saved before trips had dates. */
  date: string | null;
  /** Null past the forecast's reach. */
  weather: DayForecast | null;
  /** The day's hours, "HH:MM" (`end` may be the next morning), and its daylight. */
  start: string | null;
  end: string | null;
  sunrise: string | null;
  sunset: string | null;
  /** "HH:MM": when the stops are done and a free evening begins; null without one. */
  free_from: string | null;
  /** How the day gets back to the start point on round trips; null without a way back. */
  return_mode: TravelMode | null;
}

export interface TripRequest {
  city: string | null;
  days: number;
  interests: string[];
  avoid: string[];
  pace: Pace;
  keywords: string[];
  notes: string;
}

export interface Adjustment {
  removed: PlaceRef | null;
  added: PlaceRef | null;
  reason: string;
}

/** A planned stop a change leaves out, and why. */
export interface DroppedStop extends PlaceRef {
  reason: string;
}

/** How a version was made: AI replacements, or a day edit of a saved trip. */
export interface PlanEdit {
  day: number;
  kind: "replace" | "edit";
  /** Stops the traveller asked the AI to replace. */
  replaced: PlaceRef[];
  /** Stops the traveller took out (day edits). */
  removed: PlaceRef[];
  /** Replacements, or places the traveller added. */
  added: PlaceRef[];
  /** The stop the traveller visits next (day edits). */
  next: PlaceRef | null;
  /** The stop the next one follows; null: it comes first, after any visited stops. */
  after: PlaceRef | null;
  /** Last-resort changes to stops the traveller did not tick. */
  adjustments: Adjustment[];
  /** Planned stops the change leaves out: shown before a draft is saved. */
  dropped: DroppedStop[];
  warnings: string[];
}

export interface PlanResponse {
  id: number;
  request_text: string;
  city: string;
  trip: TripRequest;
  rationale: string;
  days: PlannedDay[];
  total_distance_m: number;
  distance_source: string;
  /** "here" (real timetables), "estimate" or "mixed"; null when nothing is ridden. */
  transit_source: string | null;
  strategy: string;
  dropped: PlaceRef[];
  warnings: string[];
  timings_ms: Record<string, number>;
  modes: TravelMode[];
  must_visit: PlaceRef[];
  start: StartPoint | null;
  /** Set on versions made by replacing stops or editing a day: the version before. */
  parent_id: number | null;
  edit: PlanEdit | null;
  start_date: string | null;
  weather_aware: boolean;
  /** Outdoor picks the forecast left no room for, and their indoor replacements. */
  weather_swaps: Adjustment[];
  /** Picks the days' hours had no room for (dark or closed then), and what replaced them. */
  hours_swaps: Adjustment[];
  day_start: string;
  day_end: string;
  first_day_start: string | null;
  /** Each day's own hours as asked for; empty when every day has day_start to day_end. */
  day_hours: DayHours[];
  /** The number of days asked for; null: the text's. */
  day_count: number | null;
  /**
   * Made without the AI, which was unavailable: the request read by rules and the
   * best-ranked places chosen, without notes. The rationale says so.
   */
  ai_fallback: boolean;
}

/** The logged-in user (GET /auth/me). */
export interface User {
  id: number;
  email: string;
  display_name: string;
  created_at: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface SignupRequest extends LoginRequest {
  display_name: string;
}

/** A stop of a saved trip the traveller has visited. */
export interface TripVisit {
  place_id: number;
  name: string;
  visited_at: string;
}

/** A saved trip with its current plan (GET /trips/{id}). */
export interface Trip {
  id: number;
  title: string;
  /** The current version of the plan. */
  plan: PlanResponse;
  /** Stops visited so far, in visiting order. */
  visits: TripVisit[];
  created_at: string;
  updated_at: string;
}

/** A saved trip in My trips (GET /trips). */
export interface TripSummary {
  id: number;
  title: string;
  /** The current version of the plan. */
  plan_id: number;
  city: string;
  request_text: string;
  days: number;
  start_date: string | null;
  created_at: string;
  updated_at: string;
}

/** POST /trips/{id}/edit: a change to one day, answered with a draft (a new plan version). */
export interface DayEditRequest {
  day: number;
  /** Stops of the day to take out. */
  remove?: number[];
  /** Places to add (ids from GET /places). */
  add?: number[];
  /** Visit this place next: a stop of the day, or a place to add. */
  next?: number | null;
  /** A stop of the day to visit `next` right after: the stops planned up to it keep their
   * order. By default `next` comes first, after the visited stops. */
  after?: number | null;
  /** Where the traveller is: the rest of the day is planned from there (from now, today). */
  start?: { lat: number; lon: number } | null;
  /** Minutes to stay at the added places and the next stop; by default, by kind of place. */
  stay_min?: number | null;
}

export interface TripUpdate {
  title?: string;
  /** Another version of the trip's plan: a draft made from it (save), or an earlier one (undo). */
  plan_id?: number;
}

/** Food: restaurants, fast food, cafés, ice cream, pastry shops. Drinks: bars, pubs, clubs. */
export type VenueKind = "food" | "drinks";
/** The OSM amenity (or shop) a venue is. */
export type VenueType =
  | "restaurant"
  | "fast_food"
  | "cafe"
  | "ice_cream"
  | "pastry"
  | "bar"
  | "pub"
  | "nightclub"
  | "music_venue";
export type OpenState = "open" | "closed" | "unknown";

/** A place to eat or drink from GET /venues (backend/app/schemas/venue.py). */
export interface Venue {
  /** Place id: add it to a day with POST /trips/{id}/edit. */
  id: number;
  name: string;
  /** "restaurant", "cafe" or "nightlife". */
  category: string;
  venue_type: VenueType;
  lat: number;
  lon: number;
  /** Straight-line distance from the search point. */
  distance_m: number;
  /** Estimated walk from the search point. */
  walk_min: number;
  /** OSM cuisine values, e.g. "portuguese", "coffee_shop". */
  cuisines: string[];
  /** Diets catered for: "only" means nothing else is served. */
  diets: Record<string, "yes" | "only">;
  /** Null when unknown. */
  outdoor_seating: boolean | null;
  /** OSM opening_hours syntax, as mapped. */
  opening_hours: string | null;
  open_now: OpenState;
  /** When the walk from the search point ends. */
  open_on_arrival: OpenState;
  /** "HH:MM": when it opens or closes next, if within a day. */
  changes_at: string | null;
  website: string | null;
  phone: string | null;
  /** A usual stay: café 30 min, bar 60, restaurant 75. */
  stay_min: number;
}

export interface CuisineCount {
  cuisine: string;
  count: number;
}

export interface VenuePage {
  items: Venue[];
  /** Venues that match, before the limit. */
  total: number;
  /** Cuisines in range that the other filters leave, most common first. */
  cuisines: CuisineCount[];
}

/** GET /venues: places to eat and drink within `radius_m` (250 m – 2 km) of a point. */
export interface VenueQuery {
  lat: number;
  lon: number;
  radius_m?: number;
  /** Null or missing: both. */
  kind?: VenueKind | null;
  cuisine?: string | null;
  vegetarian?: boolean;
  vegan?: boolean;
  /** Open by the time you walk there. */
  open_now?: boolean;
  outdoor_seating?: boolean;
  limit?: number;
  /** When you set off from the point, in the city's time ("YYYY-MM-DDTHH:MM"); default: now. */
  at?: string | null;
}
