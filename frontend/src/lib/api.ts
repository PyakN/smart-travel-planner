import type {
  LoginRequest,
  PlacePage,
  PlanRequest,
  PlanResponse,
  ReplaceRequest,
  SignupRequest,
  Trip,
  TripSummary,
  TripUpdate,
  TripVisit,
  User,
} from "./types";

/** Same-origin prefix; next.config.ts proxies it to the FastAPI backend. */
export const API_BASE = "/api";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const FALLBACK_MESSAGES: Record<number, string> = {
  404: "This plan does not exist.",
  429: "Planning capacity for today is used up. Try again tomorrow.",
  502: "The AI planner failed. Try again.",
  503: "The AI planner is temporarily unavailable. Try again shortly.",
  504: "Planning took too long. Try a shorter trip.",
};

/** FastAPI errors carry `detail`: a string, or a list of validation errors. */
export function errorMessage(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail) && typeof detail[0]?.msg === "string") {
    return `Invalid request: ${detail[0].msg}`;
  }
  return FALLBACK_MESSAGES[status] ?? `Something went wrong (HTTP ${status}).`;
}

async function request<T>(path: string, init: RequestInit, fetchImpl: typeof fetch): Promise<T> {
  let response: Response;
  try {
    response = await fetchImpl(`${API_BASE}${path}`, init);
  } catch {
    throw new ApiError(0, "Cannot reach the planner. Is the backend running?");
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, errorMessage(response.status, body));
  return body as T;
}

/** Request options that send `body` as JSON. */
function sendJson(method: string, body: unknown): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

export function createPlan(body: PlanRequest, fetchImpl: typeof fetch = fetch) {
  return request<PlanResponse>("/plan", sendJson("POST", body), fetchImpl);
}

export function getPlan(id: number, fetchImpl: typeof fetch = fetch) {
  return request<PlanResponse>(`/plans/${id}`, { method: "GET" }, fetchImpl);
}

/** Replaces stops of one day; resolves to a new plan version. */
export function replaceStops(
  planId: number,
  body: ReplaceRequest,
  fetchImpl: typeof fetch = fetch,
) {
  return request<PlanResponse>(`/plans/${planId}/replace`, sendJson("POST", body), fetchImpl);
}

/** Places whose name contains `query` (accents ignored), for the must-visit picker. */
export function searchPlaces(
  query: string,
  {
    city = "lisbon",
    limit = 8,
    signal,
  }: { city?: string; limit?: number; signal?: AbortSignal } = {},
  fetchImpl: typeof fetch = fetch,
) {
  const params = new URLSearchParams({ q: query, city, limit: String(limit) });
  return request<PlacePage>(`/places?${params}`, { method: "GET", signal }, fetchImpl);
}

/** Creates an account and logs in: the backend sets an HttpOnly session cookie. */
export function signUp(body: SignupRequest, fetchImpl: typeof fetch = fetch) {
  return request<User>("/auth/signup", sendJson("POST", body), fetchImpl);
}

export function logIn(body: LoginRequest, fetchImpl: typeof fetch = fetch) {
  return request<User>("/auth/login", sendJson("POST", body), fetchImpl);
}

export async function logOut(fetchImpl: typeof fetch = fetch): Promise<void> {
  await request<null>("/auth/logout", { method: "POST" }, fetchImpl);
}

/** Deletes the account and its saved trips; plans stay reachable by their share links. */
export async function deleteAccount(fetchImpl: typeof fetch = fetch): Promise<void> {
  await request<null>("/auth/me", { method: "DELETE" }, fetchImpl);
}

/** The logged-in user, or null when nobody is. */
export async function getMe(fetchImpl: typeof fetch = fetch): Promise<User | null> {
  try {
    return await request<User>("/auth/me", { method: "GET" }, fetchImpl);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}

/** Saves a plan to My trips; a plan saved already resolves to that trip. */
export function saveTrip(planId: number, fetchImpl: typeof fetch = fetch) {
  return request<Trip>("/trips", sendJson("POST", { plan_id: planId }), fetchImpl);
}

export function listTrips(fetchImpl: typeof fetch = fetch) {
  return request<TripSummary[]>("/trips", { method: "GET" }, fetchImpl);
}

export function getTrip(id: number, fetchImpl: typeof fetch = fetch) {
  return request<Trip>(`/trips/${id}`, { method: "GET" }, fetchImpl);
}

/** Renames a trip, or switches it to another version of its plan. */
export function updateTrip(id: number, body: TripUpdate, fetchImpl: typeof fetch = fetch) {
  return request<Trip>(`/trips/${id}`, sendJson("PATCH", body), fetchImpl);
}

export async function deleteTrip(id: number, fetchImpl: typeof fetch = fetch): Promise<void> {
  await request<null>(`/trips/${id}`, { method: "DELETE" }, fetchImpl);
}

/** Ticks a stop of the trip visited (again: it keeps the first time). */
export function markVisited(tripId: number, placeId: number, fetchImpl: typeof fetch = fetch) {
  return request<TripVisit>(`/trips/${tripId}/visits/${placeId}`, { method: "PUT" }, fetchImpl);
}

export async function unmarkVisited(
  tripId: number,
  placeId: number,
  fetchImpl: typeof fetch = fetch,
): Promise<void> {
  await request<null>(`/trips/${tripId}/visits/${placeId}`, { method: "DELETE" }, fetchImpl);
}
