// Mirrors backend/app/schemas/plan.py (POST /plan, GET /plans/{id})
// and backend/app/schemas/place.py (GET /places).

export type TravelMode = "walk" | "transit";
export type Pace = "relaxed" | "moderate" | "intense";
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
}

export interface RouteSegment {
  mode: TravelMode;
  geometry: LonLat[];
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

export interface PlanResponse {
  id: number;
  request_text: string;
  city: string;
  trip: TripRequest;
  rationale: string;
  days: PlannedDay[];
  total_distance_m: number;
  distance_source: string;
  strategy: string;
  dropped: PlaceRef[];
  warnings: string[];
  timings_ms: Record<string, number>;
  modes: TravelMode[];
  must_visit: PlaceRef[];
}
