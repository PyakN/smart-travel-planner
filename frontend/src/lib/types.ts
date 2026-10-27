// Mirrors backend/app/schemas/plan.py (POST /plan, GET /plans/{id}, POST /plans/{id}/replace)
// and backend/app/schemas/place.py (GET /places).

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

export interface PlanRequest {
  text: string;
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

export interface PlanEdit {
  day: number;
  replaced: PlaceRef[];
  added: PlaceRef[];
  /** Last-resort changes to stops the traveller did not tick. */
  adjustments: Adjustment[];
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
  /** Set on versions made by replacing stops. */
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
}
